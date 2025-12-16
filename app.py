"""
Interface Streamlit pour la gestion des bilans coaching
Version Database-First (CRM) - Monolithique
"""

import streamlit as st
import base64
from datetime import datetime
from email_reader import EmailReader
from analyzer import analyze_coaching_bilan, regenerate_email_draft
from email_sender import send_email, preview_email
from clients import get_client, save_client, get_jours_restants
from dashboard_generator import generate_client_dashboard
import html
import json
import sqlite3
import os
from typing import List, Dict, Any, Optional

# --- GESTION DATABASE (Intégré pour eviter erreurs d'import) ---

# Chemin de la DB: sur disque persistant /data si dispo, sinon local
DB_PATH = "/data/coaching.db" if os.path.exists("/data") else "coaching.db"
ATTACHMENTS_DIR = "/data/attachments" if os.path.exists("/data") else "attachments"

class DatabaseManager:
    def __init__(self):
        self._init_db()
        self._init_dirs()

    def _init_db(self):
        """Cree les tables si elles n'existent pas"""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # Table Clients
            c.execute('''CREATE TABLE IF NOT EXISTS clients
                        (email TEXT PRIMARY KEY, 
                        nom TEXT, 
                        objectif TEXT, 
                        date_debut TEXT,
                        duree_semaines INTEGER,
                        notes TEXT,
                        last_updated TIMESTAMP)''')
            
            # Table Emails (Historique complet)
            c.execute('''CREATE TABLE IF NOT EXISTS emails
                        (message_id TEXT PRIMARY KEY,
                        client_email TEXT,
                        subject TEXT,
                        date TIMESTAMP,
                        body TEXT,
                        direction TEXT, -- 'received' ou 'sent'
                        is_bilan BOOLEAN,
                        analysis_json TEXT, -- Resultat analyse IA stocke
                        FOREIGN KEY(client_email) REFERENCES clients(email))''')
                        
            # Table Attachments
            c.execute('''CREATE TABLE IF NOT EXISTS attachments
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT,
                        filename TEXT,
                        filepath TEXT,
                        content_type TEXT,
                        FOREIGN KEY(message_id) REFERENCES emails(message_id))''')
                        
            conn.commit()
            conn.close()
        except Exception as e:
            st.error(f"Erreur init DB: {e}")

    def _init_dirs(self):
        """Cree le dossier pieces jointes"""
        try:
            os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
        except:
            pass

    def get_client(self, email: str) -> Optional[Dict]:
        """Recupere infos client"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM clients WHERE email = ?", (email,))
            row = c.fetchone()
            conn.close()
            return dict(row) if row else None
        except:
            return None

    def save_client(self, email: str, nom: str = "", objectif: str = "", date_debut: str = "", duree: int = 12):
        """Sauvegarde/Update client"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO clients (email, nom, objectif, date_debut, duree_semaines, last_updated)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (email, nom, objectif, date_debut, duree, datetime.now()))
        conn.commit()
        conn.close()

    def save_email(self, email_data: Dict) -> bool:
        """Sauvegarde un email et ses pieces jointes"""
        
        # FILTRE: Ignorer les emails inutiles (spam coaching)
        EXCLUDE_PATTERNS = [
            'typeform', 'followup', 'newsletter', 'noreply', 'no-reply', 
            'stripe', 'paypal', 'billing', 'invoice', 'facture', 'recu', 'receipt',
            'confirmation', 'commande', 'order', 'shipping', 'livraison',
            'publicite', 'promo', 'soldes', 'unsubscribe', 'desinscription',
            'linkedin', 'instagram', 'facebook', 'twitter', 'youtube', 'pinterest',
            'notification', 'alert', 'security', 'securite', 'connexion', 'login'
        ]
        
        subject = email_data.get('subject', '').lower()
        sender = email_data.get('from_email', '').lower()
        
        if any(p in subject for p in EXCLUDE_PATTERNS) or any(p in sender for p in EXCLUDE_PATTERNS):
            # print(f"Email ignore (filtre): {subject}")
            return False
            
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        try:
            # 1. Sauvegarder l'email
            date_val = email_data['date']
            if isinstance(date_val, datetime):
                date_val = date_val.isoformat()
                
            c.execute("""INSERT OR IGNORE INTO emails 
                         (message_id, client_email, subject, date, body, direction, is_bilan, analysis_json)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                      (email_data['message_id'], 
                       email_data.get('from_email') if email_data.get('direction') == 'received' else email_data.get('to_email'),
                       email_data['subject'], 
                       date_val, 
                       email_data.get('body', ''),
                       email_data.get('direction', 'received'),
                       email_data.get('is_potential_bilan', False),
                       json.dumps(email_data.get('analysis', {})) if email_data.get('analysis') else None
                      ))
            
            # 2. Sauvegarder les pieces jointes
            for att in email_data.get('attachments', []):
                safe_filename = "".join([c for c in att['filename'] if c.isalpha() or c.isdigit() or c in '._- ']).strip()
                file_path = os.path.join(ATTACHMENTS_DIR, f"{email_data['message_id']}_{safe_filename}")
                
                if 'data' in att and not os.path.exists(file_path):
                    try:
                        with open(file_path, "wb") as f:
                            f.write(base64.b64decode(att['data']))
                    except:
                        pass
                
                c.execute("""INSERT OR IGNORE INTO attachments (message_id, filename, filepath, content_type)
                             VALUES (?, ?, ?, ?)""",
                          (email_data['message_id'], att['filename'], file_path, att['content_type']))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Erreur save DB: {e}")
            return False
        finally:
            conn.close()

    def get_client_history(self, client_email: str) -> List[Dict]:
        """Recupere tout l'historique d'un client depuis la DB"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Recherche flexible (contient)
        if client_email:
            c.execute("""SELECT * FROM emails 
                        WHERE client_email LIKE ? OR client_email LIKE ?
                        ORDER BY date ASC""", (f"%{client_email}%", client_email))
        else:
            # Si vide, on ne renvoie rien ou les recents (limit 50)
            c.execute("SELECT * FROM emails ORDER BY date DESC LIMIT 50")

        rows = c.fetchall()
        
        history = []
        for row in rows:
            email_dict = dict(row)
            try:
                email_dict['date'] = datetime.fromisoformat(email_dict['date'])
            except:
                pass
                
            c.execute("SELECT * FROM attachments WHERE message_id = ?", (email_dict['message_id'],))
            att_rows = c.fetchall()
            email_dict['attachments'] = [dict(att) for att in att_rows]
            
            history.append(email_dict)
            
        conn.close()
        
        # Tri final par date
        history.sort(key=lambda x: x['date'] if isinstance(x['date'], datetime) else datetime.min)
        return history

    def email_exists(self, message_id: str) -> bool:
        """Verifie si un email est deja en base"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM emails WHERE message_id = ?", (message_id,))
        exists = c.fetchone() is not None
        conn.close()
        return exists

# --- FIN GESTION DB ---

# Liste des patterns a exclure (spam, notifs, etc)
EXCLUDE_PATTERNS = [
    'typeform', 'followup', 'newsletter', 'noreply', 'no-reply', 
    'stripe', 'paypal', 'billing', 'invoice', 'facture', 'recu', 'receipt',
    'confirmation', 'commande', 'order', 'shipping', 'livraison',
    'publicite', 'promo', 'soldes', 'unsubscribe', 'desinscription',
    'linkedin', 'instagram', 'facebook', 'twitter', 'youtube', 'pinterest',
    'notification', 'alert', 'security', 'securite', 'connexion', 'login',
    'calendly', 'google calendar', 'invitation', 'rappel'
]

# Config page
st.set_page_config(
    page_title="Achzod - Bilans Coaching",
    page_icon="💪",
    layout="wide"
)

# CSS custom
st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: bold; color: #9990EA; margin-bottom: 1rem; }
    .bilan-card { background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #9990EA; white-space: pre-wrap; }
    .kpi-box { background: linear-gradient(135deg, #9990EA 0%, #8DFFE0 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; }
    .kpi-value { font-size: 2rem; font-weight: bold; }
    .kpi-label { font-size: 0.9rem; opacity: 0.9; }
    .positive { color: #28a745; }
    .negative { color: #dc3545; }
    .email-preview { background: white; padding: 20px; border-radius: 8px; border: 1px solid #ddd; }
    .history-item { padding: 10px; margin: 5px 0; border-radius: 5px; }
    .history-received { background: #e3f2fd; border-left: 3px solid #2196f3; }
    .history-sent { background: #f3e5f5; border-left: 3px solid #9c27b0; }
    .status-ok { color: #28a745; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Init session state
if 'reader' not in st.session_state:
    st.session_state.reader = None
if 'db' not in st.session_state:
    st.session_state.db = DatabaseManager()
if 'emails' not in st.session_state:
    st.session_state.emails = []
if 'selected_email' not in st.session_state:
    st.session_state.selected_email = None
if 'analysis' not in st.session_state:
    st.session_state.analysis = None
if 'history' not in st.session_state:
    st.session_state.history = []
if 'draft' not in st.session_state:
    st.session_state.draft = ""


def generate_kpi_table(kpis: dict) -> str:
    """Genere un tableau texte des KPIs pour l'email"""
    if not kpis:
        return ""

    kpi_names = {
        "adherence_training": "Entrainement",
        "adherence_nutrition": "Nutrition",
        "sommeil": "Sommeil",
        "energie": "Energie",
        "progression": "Progression"
    }

    lines = [
        "",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📊 TES KPIs DE LA SEMAINE",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ""
    ]

    for key, name in kpi_names.items():
        value = kpis.get(key, 0)
        filled = "█" * int(value)
        empty = "░" * (10 - int(value))
        bar = filled + empty

        if value >= 8:
            emoji = "🟢"
        elif value >= 6:
            emoji = "🟡"
        else:
            emoji = "🔴"

        lines.append(f"{emoji} {name:15} {bar} {value}/10")

    values = [kpis.get(k, 0) for k in kpi_names.keys()]
    avg = sum(values) / len(values) if values else 0

    lines.append("")
    lines.append(f"📈 Score global: {avg:.1f}/10")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    return "\n".join(lines)


def display_attachments(attachments):
    """Affiche les pieces jointes"""
    if not attachments:
        return

    cols = st.columns(min(len(attachments), 3))
    for i, att in enumerate(attachments[:6]):
        with cols[i % 3]:
            # Support Base64 (nouveau) ou Path (DB)
            if "data" in att:
                # Ancienne methode (memoire)
                if att["content_type"].startswith("image/"):
                    try:
                        img_data = base64.b64decode(att["data"])
                        st.image(img_data, caption=att["filename"], use_container_width=True)
                    except:
                        st.write(f"📷 {att['filename']}")
                else:
                    st.write(f"📎 {att['filename']}")
            elif "filepath" in att and att.get("filepath"):
                # Nouvelle methode (DB/Fichier)
                try:
                    if os.path.exists(att["filepath"]):
                        st.image(att["filepath"], caption=att["filename"], use_container_width=True)
                    else:
                        st.write(f"⚠️ Fichier introuvable: {att['filename']}")
                except:
                    st.write(f"📷 {att['filename']}")


def display_kpis(kpis):
    """Affiche les KPIs"""
    cols = st.columns(7)
    kpi_labels = {
        "adherence_training": "Training",
        "adherence_nutrition": "Nutrition",
        "sommeil": "Sommeil",
        "energie": "Energie",
        "sante": "Sante",
        "mindset": "Mindset",
        "progression": "Progression"
    }

    for i, (key, label) in enumerate(kpi_labels.items()):
        with cols[i]:
            value = kpis.get(key, 0)
            color = "#28a745" if value >= 7 else "#ffc107" if value >= 5 else "#dc3545"
            st.markdown(f"""
                <div style="text-align: center; padding: 10px; background: #f8f9fa; border-radius: 8px; border-top: 4px solid {color};">
                    <div style="font-size: 1.8rem; font-weight: bold; color: {color};">{value}/10</div>
                    <div style="font-size: 0.85rem; color: #666;">{label}</div>
                </div>
            """, unsafe_allow_html=True)


def main():
    st.markdown('<div class="main-header">💪 Bilans Coaching - CRM v3.0 (Monolith)</div>', unsafe_allow_html=True)

    # Sidebar - Synchro
    with st.sidebar:
        st.header("🔄 Synchronisation")
        
        # Stats DB
        try:
            # Petite requete rapide pour savoir combien on a d'emails
            pass
        except:
            pass

        days = st.selectbox("Jours a scanner", [1, 3, 7, 30], index=1)
        
        if st.button("📥 Synchroniser Gmail", use_container_width=True, type="primary"):
            if st.session_state.reader is None:
                st.session_state.reader = EmailReader()
            
            with st.status("Synchronisation en cours...", expanded=True) as status:
                st.write("🔌 Connexion Gmail...")
                
                # 1. Recuperer les emails recents
                new_emails = st.session_state.reader.get_recent_emails(days=days, unread_only=False) # On scanne tout
                st.write(f"📨 {len(new_emails)} emails trouves sur Gmail")
                
                # 2. Sauvegarder en DB (uniquement les nouveaux et pertinents)
                saved_count = 0
                ignored_count = 0
                
                for email in new_emails:
                    # Filtre anti-spam AVANT tout traitement lourd
                    subject = email.get('subject', '').lower()
                    sender = email.get('from_email', '').lower()
                    
                    if any(p in subject for p in EXCLUDE_PATTERNS) or any(p in sender for p in EXCLUDE_PATTERNS):
                        # print(f"Ignored: {subject}")
                        ignored_count += 1
                        continue

                    if not st.session_state.db.email_exists(email['message_id']):
                        # Besoin de charger le contenu complet pour sauvegarder
                        st.write(f"📥 Telechargement: {email['subject'][:40]}...")
                        content = st.session_state.reader.load_email_content(email['id'])
                        if content and content.get("loaded"):
                            email['body'] = content.get('body', '')
                            email['attachments'] = content.get('attachments', [])
                            if st.session_state.db.save_email(email):
                                saved_count += 1
                
                status.update(label=f"✅ {saved_count} nouveaux emails sauvegardes ({ignored_count} ignores)", state="complete", expanded=False)
                st.success(f"Base de donnees a jour (+{saved_count} emails)")
                st.rerun()

        st.divider()
        st.header("📂 Clients")
        
        # Vue Inbox / Recherche
        st.subheader("Recherche Client")
        
        client_search = st.text_input("🔍 Email client", placeholder="jean@example.com")
        
        if client_search:
            st.session_state.emails = st.session_state.db.get_client_history(client_search)
            if not st.session_state.emails:
                st.warning("Aucun historique pour ce client")
            else:
                st.success(f"{len(st.session_state.emails)} emails trouves")
        
        # Si pas de recherche, afficher les derniers mails recus (Inbox locale)
        elif not st.session_state.emails:
             st.session_state.emails = st.session_state.db.get_client_history("") # Retourne les 50 derniers
                
        # Liste des emails trouves pour ce client
        for email_data in st.session_state.emails:
            date_str = email_data['date'].strftime('%d/%m %H:%M') if isinstance(email_data.get('date'), datetime) else str(email_data.get('date', ''))
            
            # Icone direction
            icon = "📥" if email_data.get('direction') == 'received' else "📤"
            
            if st.button(f"{icon} {date_str} - {email_data['subject'][:30]}", key=f"sel_{email_data['message_id']}", use_container_width=True):
                st.session_state.selected_email = email_data
                # Pour l'historique, si on a cherche un client, on a deja tout
                # Sinon on recharge l'historique specifique de ce client
                if client_search:
                    st.session_state.history = st.session_state.emails
                else:
                    client_email = email_data.get('client_email')
                    st.session_state.history = st.session_state.db.get_client_history(client_email)
                    
                st.session_state.analysis = None
                st.session_state.draft = ""
                st.rerun()

    # Contenu principal
    if st.session_state.selected_email:
        email_data = st.session_state.selected_email

        # Header
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.subheader(f"📧 {email_data['subject']}")
            client_email = email_data.get('client_email', email_data.get('from_email', ''))
            st.caption(f"Client: {client_email}")
            
            # Infos client
            client_info = get_client(client_email)
            if client_info:
                jours = get_jours_restants(client_info)
                color = "green" if jours > 14 else "orange" if jours > 0 else "red"
                st.markdown(f"**Commande:** {client_info.get('commande', 'N/A')} | **Jours restants:** :{color}[{jours}j]")
            
            with st.expander("Modifier infos client"):
                c_commande = st.text_input("Commande", value=client_info.get('commande', '') if client_info else '', key="c_cmd")
                c_date = st.date_input("Date debut", key="c_date")
                c_duree = st.number_input("Duree (semaines)", min_value=1, max_value=52, value=client_info.get('duree_semaines', 12) if client_info else 12, key="c_dur")
                if st.button("Sauvegarder client"):
                    save_client(client_email, c_commande, c_date.strftime('%Y-%m-%d'), c_duree)
                    st.success("Client sauvegarde!")
                    st.rerun()

        with col2:
            st.metric("Historique", f"{len(st.session_state.history)} emails")

        with col3:
            # Si c'est un mail recu, on peut analyser
            if email_data.get('direction', 'received') == 'received':
                if st.button("🤖 Analyser", type="primary", use_container_width=True):
                    with st.status("Analyse IA en cours...", expanded=True) as status:
                        st.write(f"🧠 Analyse avec {len(st.session_state.history)} emails de contexte...")
                        
                        result = analyze_coaching_bilan(
                            email_data,
                            st.session_state.history # On envoie tout l'historique local !
                        )

                        if result["success"]:
                            analysis = result["analysis"]
                            if isinstance(analysis, str):
                                try:
                                    analysis = json.loads(analysis)
                                except:
                                    pass
                            st.session_state.analysis = analysis
                            
                            # Extraire draft
                            draft = ""
                            if isinstance(analysis, dict):
                                draft = analysis.get("draft_email", "")
                            elif isinstance(analysis, str):
                                import re
                                match = re.search(r'"draft_email"\s*:\s*"(.*?)"(?=\s*[,}])', analysis, re.DOTALL)
                                if match:
                                    draft = match.group(1).replace('\\n', '\n').replace('\\"', '"')
                            
                            st.session_state.draft = draft if draft else "Email a rediger manuellement."
                            
                            status.update(label="✅ Analyse terminee!", state="complete", expanded=False)
                            st.rerun()
                        else:
                            st.error(f"Erreur: {result.get('error')}")

        # Tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📨 Email", "📜 Historique", "📊 Analyse", "✉️ Reponse", "📈 Dashboard"])

        with tab1:
            st.markdown(f'<div class="bilan-card">{html.escape(email_data.get("body", ""))}</div>', unsafe_allow_html=True)
            if email_data.get("attachments"):
                st.subheader("📎 Pieces jointes")
                display_attachments(email_data["attachments"])

        with tab2:
            for hist_email in st.session_state.history:
                direction = hist_email.get("direction", "received")
                icon = "📥" if direction == "received" else "📤"
                date_val = hist_email['date']
                date_str = date_val.strftime('%d/%m/%Y') if isinstance(date_val, datetime) else str(date_val)[:10]

                with st.expander(f"{icon} {date_str} - {hist_email['subject'][:50]}"):
                    st.write(hist_email.get("body", "")[:1000])
                    if hist_email.get("attachments"):
                        st.caption(f"📎 {len(hist_email['attachments'])} piece(s) jointe(s)")
                        display_attachments(hist_email["attachments"])

        with tab3:
            if st.session_state.analysis:
                analysis = st.session_state.analysis
                st.subheader("📝 Resume")
                st.info(analysis.get("resume", ""))
                st.subheader("📊 KPIs")
                display_kpis(analysis.get("kpis", {}))

            else:
                st.info("👆 Clique sur 'Analyser' pour lancer l'analyse IA")

        with tab4:
            if st.session_state.analysis:
                st.subheader("✉️ Email de reponse")
                st.text_area("Draft", value=st.session_state.draft, height=400)
                # ... Boutons d'envoi ...
                if st.button("📤 Envoyer", type="primary"):
                    st.warning("Fonction envoi a reconnecter avec la nouvelle architecture")
            else:
                st.info("Lance l'analyse d'abord")
                
        with tab5:
            if st.button("Generer Dashboard HTML"):
                html_dash = generate_client_dashboard(st.session_state.history)
                st.components.v1.html(html_dash, height=800, scrolling=True)

    else:
        st.info("👈 Synchronise Gmail puis cherche un client dans la sidebar")
        st.markdown("""
        ### 🚀 Nouveau Mode CRM v3.0
        
        1. **Synchroniser** : Telecharge les nouveaux emails et les stocke sur le Disque Persistant.
        2. **Chercher** : Tape l'email d'un client pour voir tout son dossier instantanement.
        3. **Analyser** : L'IA a acces a tout l'historique local ultra-rapidement.
        """)

if __name__ == "__main__":
    main()
