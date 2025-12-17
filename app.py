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
                        body_loaded BOOLEAN DEFAULT 0, -- 1 si body/attachments sont charges
                        email_id TEXT, -- ID IMAP pour charger le contenu a la demande
                        FOREIGN KEY(client_email) REFERENCES clients(email))''')
            
            # Migration: Ajouter les colonnes si elles n'existent pas
            try:
                c.execute("ALTER TABLE emails ADD COLUMN body_loaded BOOLEAN DEFAULT 0")
            except:
                pass  # Colonne existe deja
            try:
                c.execute("ALTER TABLE emails ADD COLUMN email_id TEXT")
            except:
                pass  # Colonne existe deja
                        
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
        
        # Validation: email_data doit etre un dict
        if not isinstance(email_data, dict):
            print(f"[DB] Erreur: email_data n'est pas un dict")
            return False
        
        # Validation: message_id obligatoire
        message_id = email_data.get('message_id') or email_data.get('id')
        if not message_id:
            print(f"[DB] Erreur: message_id manquant")
            return False
        
        message_id = str(message_id)
        
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
            return False
            
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # 1. Sauvegarder l'email
            date_val = email_data.get('date', datetime.now())
            if isinstance(date_val, datetime):
                date_val = date_val.isoformat()
            elif isinstance(date_val, str):
                pass  # Deja string
            else:
                date_val = datetime.now().isoformat()
            
            # Determiner client_email
            direction = email_data.get('direction', 'received')
            if direction == 'received':
                client_email = email_data.get('from_email', '')
            else:
                client_email = email_data.get('to_email', '')
            
            subject = email_data.get('subject', 'Sans sujet')
            body = email_data.get('body', '')
            is_bilan = email_data.get('is_potential_bilan', False)
            
            analysis_json = None
            if email_data.get('analysis'):
                try:
                    analysis_json = json.dumps(email_data.get('analysis', {}))
                except:
                    pass
                
            # Determiner si le body est charge
            body_loaded = 1 if body else 0
            email_id_imap = email_data.get('id', '')  # ID IMAP pour charger a la demande
            
            c.execute("""INSERT OR IGNORE INTO emails 
                         (message_id, client_email, subject, date, body, direction, is_bilan, analysis_json, body_loaded, email_id)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (message_id, client_email, subject, date_val, body, direction, is_bilan, analysis_json, body_loaded, email_id_imap))
            
            # Si body_loaded = 0, on ne sauvegarde pas les attachments (on les chargera a la demande)
            if body_loaded == 0:
                return True
            
            # 2. Sauvegarder les pieces jointes
            for att in email_data.get('attachments', []):
                if not isinstance(att, dict):
                    continue
                    
                filename = att.get('filename', 'unknown')
                if not filename:
                    continue
                    
                safe_filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in '._- ']).strip()
                if not safe_filename:
                    safe_filename = "attachment"
                    
                file_path = os.path.join(ATTACHMENTS_DIR, f"{message_id}_{safe_filename}")
                
                if 'data' in att and att['data']:
                    if not os.path.exists(file_path):
                        try:
                            decoded_data = base64.b64decode(att['data'])
                            with open(file_path, "wb") as f:
                                f.write(decoded_data)
                        except Exception as e:
                            print(f"[DB] Erreur sauvegarde PJ {filename}: {e}")
                    
                    # Liberer memoire
                    att['data'] = None
                
                content_type = att.get('content_type', 'application/octet-stream')
                try:
                    c.execute("""INSERT OR IGNORE INTO attachments (message_id, filename, filepath, content_type)
                                 VALUES (?, ?, ?, ?)""",
                              (message_id, filename, file_path, content_type))
                except Exception as e:
                    print(f"[DB] Erreur insertion PJ: {e}")
                    continue
            
            conn.commit()
            
            # Nettoyage memoire
            if 'attachments' in email_data:
                for att in email_data['attachments']:
                    if isinstance(att, dict) and 'data' in att:
                        att['data'] = None
                        
            return True
        except Exception as e:
            print(f"[DB] Erreur save_email: {e}")
            import traceback
            traceback.print_exc()
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            return False
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def get_client_history(self, client_email: str) -> List[Dict]:
        """Recupere tout l'historique d'un client depuis la DB"""
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Recherche flexible (contient)
            if client_email and client_email.strip():
                c.execute("""SELECT * FROM emails 
                            WHERE client_email LIKE ? OR client_email LIKE ?
                            ORDER BY date ASC""", (f"%{client_email}%", client_email))
            else:
                # Si vide, on ne renvoie rien ou les recents (limit 50)
                c.execute("SELECT * FROM emails ORDER BY date DESC LIMIT 50")

            rows = c.fetchall()
            
            history = []
            for row in rows:
                try:
                    email_dict = dict(row)
                    
                    # Parse date
                    try:
                        if email_dict.get('date'):
                            email_dict['date'] = datetime.fromisoformat(email_dict['date'])
                        else:
                            email_dict['date'] = datetime.now()
                    except:
                        email_dict['date'] = datetime.now()
                    
                    # Recuperer attachments (seulement si body_loaded = 1)
                    email_dict['body_loaded'] = email_dict.get('body_loaded', 0)
                    email_dict['email_id'] = email_dict.get('email_id', '')
                    
                    if email_dict['body_loaded']:
                        try:
                            c.execute("SELECT * FROM attachments WHERE message_id = ?", (email_dict.get('message_id', ''),))
                            att_rows = c.fetchall()
                            email_dict['attachments'] = [dict(att) for att in att_rows]
                        except:
                            email_dict['attachments'] = []
                    else:
                        email_dict['attachments'] = []
                    
                    history.append(email_dict)
                except Exception as e:
                    print(f"[DB] Erreur parsing email: {e}")
                    continue
            
            # Tri final par date
            try:
                history.sort(key=lambda x: x.get('date', datetime.min) if isinstance(x.get('date'), datetime) else datetime.min)
            except:
                pass
                
            return history
        except Exception as e:
            print(f"[DB] Erreur get_client_history: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def email_exists(self, message_id: str) -> bool:
        """Verifie si un email est deja en base"""
        if not message_id:
            return False
            
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT 1 FROM emails WHERE message_id = ?", (str(message_id),))
            exists = c.fetchone() is not None
            return exists
        except Exception as e:
            print(f"[DB] Erreur email_exists: {e}")
            return False
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

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
                if att.get("content_type", "").startswith("image/"):
                    try:
                        img_data = base64.b64decode(att["data"])
                        st.image(img_data, caption=att.get("filename", ""), use_container_width=True)
                    except:
                        st.write(f"📷 {att.get('filename', 'Image')}")
                else:
                    st.write(f"📎 {att.get('filename', 'Fichier')}")
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
    import gc
    st.markdown('<div class="main-header">💪 Bilans Coaching - CRM v3.1 (Low Ram)</div>', unsafe_allow_html=True)

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
                try:
                    new_emails = st.session_state.reader.get_recent_emails(days=days, unread_only=False) # On scanne tout
                    if new_emails is None:
                        new_emails = []
                    if not isinstance(new_emails, list):
                        new_emails = []
                    st.write(f"📨 {len(new_emails)} emails trouves")
                except Exception as e:
                    st.error(f"❌ Erreur connexion Gmail: {e}")
                    import traceback
                    traceback.print_exc()
                    new_emails = []
                
                # 2. Sauvegarder en DB (uniquement les nouveaux et pertinents)
                saved_count = 0
                ignored_count = 0
                error_count = 0
                
                # Progress bar pour le chargement
                progress_bar = st.progress(0)
                total_emails = len(new_emails)
                
                for idx, email in enumerate(new_emails):
                    # Update progress bar
                    if total_emails > 0:
                        progress = (idx + 1) / total_emails
                        progress_bar.progress(progress)
                    try:
                        # Validation: email doit etre un dict avec les champs essentiels
                        if not isinstance(email, dict):
                            error_count += 1
                            continue
                        
                        # Validation: message_id obligatoire
                        message_id = email.get('message_id') or email.get('id')
                        if not message_id:
                            error_count += 1
                            continue
                        
                        # Filtre anti-spam AVANT tout traitement lourd
                        subject = email.get('subject', '').lower()
                        sender = email.get('from_email', '').lower()
                        
                        if any(p in subject for p in EXCLUDE_PATTERNS) or any(p in sender for p in EXCLUDE_PATTERNS):
                            ignored_count += 1
                            continue

                        # Verifier si deja en DB
                        if not st.session_state.db.email_exists(str(message_id)):
                            # OPTIMISATION: Sauvegarder seulement les headers (sans body/attachments)
                            # Le contenu complet sera charge a la demande quand on clique sur l'email
                            email['body'] = ''  # Pas de body pour l'instant
                            email['attachments'] = []  # Pas d'attachments pour l'instant
                            
                            # Sauvegarder en DB (headers seulement)
                            if st.session_state.db.save_email(email):
                                saved_count += 1
                        
                        # Nettoyage memoire (sans clear() qui casse la boucle)
                        if 'attachments' in email:
                            for att in email.get('attachments', []):
                                if 'data' in att:
                                    att['data'] = None
                        
                        # Force garbage collection tous les 10 emails
                        if idx % 10 == 0:
                            gc.collect()
                            
                    except Exception as e:
                        print(f"[SYNC] Erreur traitement email: {e}")
                        error_count += 1
                        continue
                
                progress_bar.empty()
                
                final_msg = f"✅ {saved_count} nouveaux emails sauvegardes"
                if ignored_count > 0:
                    final_msg += f" ({ignored_count} ignores)"
                if error_count > 0:
                    final_msg += f" ({error_count} erreurs)"
                    
                status.update(label=final_msg, state="complete", expanded=False)
                st.success(f"✅ {saved_count} nouveaux emails sauvegardes")
                if error_count > 0:
                    st.warning(f"⚠️ {error_count} erreur(s)")
                # Pas de rerun automatique pour éviter le rechargement
                # st.rerun()

        st.divider()
        st.header("📂 Clients")
        
        # Vue Inbox / Recherche
        st.subheader("Recherche Client")
        
        client_search = st.text_input("🔍 Email client", placeholder="jean@example.com")
        
        if client_search:
            try:
                st.session_state.emails = st.session_state.db.get_client_history(client_search)
                if not st.session_state.emails:
                    st.warning("Aucun historique pour ce client")
                else:
                    st.success(f"{len(st.session_state.emails)} emails trouves")
            except Exception as e:
                st.error(f"Erreur recherche: {e}")
                st.session_state.emails = []
        
        # Si pas de recherche, afficher les derniers mails recus (Inbox locale)
        elif not st.session_state.emails:
            try:
                st.session_state.emails = st.session_state.db.get_client_history("") # Retourne les 50 derniers
            except:
                st.session_state.emails = []
                
        # Liste des emails trouves pour ce client
        if not isinstance(st.session_state.emails, list):
            st.session_state.emails = []
            
        for email_data in st.session_state.emails:
            try:
                if not isinstance(email_data, dict):
                    continue
                    
                # Validation champs essentiels
                message_id = email_data.get('message_id') or email_data.get('id', '')
                if not message_id:
                    continue
                
                # Format date
                date_val = email_data.get('date')
                if isinstance(date_val, datetime):
                    date_str = date_val.strftime('%d/%m %H:%M')
                elif date_val:
                    try:
                        date_str = datetime.fromisoformat(str(date_val)).strftime('%d/%m %H:%M')
                    except:
                        date_str = str(date_val)[:16]
                else:
                    date_str = "Date inconnue"
                
                # Icone direction
                icon = "📥" if email_data.get('direction') == 'received' else "📤"
                
                # Subject - nettoyer "Re:" et autres prefixes
                subject = email_data.get('subject', 'Sans sujet')
                # Enlever les prefixes courants
                subject = subject.replace('Re: ', '').replace('RE: ', '').replace('Fwd: ', '').replace('FWD: ', '')
                subject = subject[:40]  # Limiter la longueur
                
                if st.button(f"{icon} {date_str} | {subject}", key=f"sel_{message_id}", use_container_width=True):
                    st.session_state.selected_email = email_data
                    # Pour l'historique, si on a cherche un client, on a deja tout
                    # Sinon on recharge l'historique specifique de ce client
                    if client_search:
                        st.session_state.history = st.session_state.emails
                    else:
                        client_email = email_data.get('client_email', '')
                        if client_email:
                            try:
                                st.session_state.history = st.session_state.db.get_client_history(client_email)
                            except:
                                st.session_state.history = []
                        else:
                            st.session_state.history = []
                    
                st.session_state.analysis = None
                st.session_state.draft = ""
                st.rerun()
            except Exception as e:
                print(f"[UI] Erreur affichage email: {e}")
                continue

    # Contenu principal
    if st.session_state.selected_email:
        try:
            email_data = st.session_state.selected_email
            if not isinstance(email_data, dict):
                st.error("Erreur: email_data invalide")
                st.session_state.selected_email = None
            else:
                # Header
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    subject = email_data.get('subject', 'Sans sujet')
                    st.subheader(f"📧 {subject}")
                    client_email = email_data.get('client_email', email_data.get('from_email', ''))
                    st.caption(f"Client: {client_email}")
            
            # Infos client
                    try:
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
                    except Exception as e:
                        print(f"[UI] Erreur infos client: {e}")

                with col2:
                    history_len = len(st.session_state.history) if isinstance(st.session_state.history, list) else 0
                    st.metric("Historique", f"{history_len} emails")

                with col3:
                    # Si c'est un mail recu, on peut analyser
                    if email_data.get('direction', 'received') == 'received':
                        if st.button("🤖 Analyser", type="primary", use_container_width=True):
                            with st.status("Analyse IA en cours...", expanded=True) as status:
                                try:
                                    history_len = len(st.session_state.history) if isinstance(st.session_state.history, list) else 0
                                    st.write(f"🧠 Analyse avec {history_len} emails de contexte...")

                                    result = analyze_coaching_bilan(
                                        email_data,
                                        st.session_state.history # On envoie tout l'historique local !
                                    )

                                    if result and result.get("success"):
                                        analysis = result.get("analysis")
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
                                        error_msg = result.get('error', 'Erreur inconnue') if result else 'Erreur: resultat vide'
                                        st.error(f"Erreur: {error_msg}")
                                        st.error(f"Erreur: {error_msg}")
                                    st.error(f"Erreur analyse IA: {e}")
                                    import traceback
                                    traceback.print_exc()
                                    status.update(label="❌ Erreur", state="error", expanded=False)
                                except Exception as e:
                                    st.error(f"Erreur analyse IA: {e}")
                                    import traceback
                                    traceback.print_exc()
                                    status.update(label="❌ Erreur", state="error", expanded=False)
        except Exception as e:
            st.error(f"Erreur affichage email: {e}")
            import traceback
            traceback.print_exc()
            st.session_state.selected_email = None
        else:
            # Tabs (seulement si pas d'erreur)
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["📨 Email", "📜 Historique", "📊 Analyse", "✉️ Reponse", "📈 Dashboard"])

        with tab1:
                try:
                    body = email_data.get("body", "")
                    st.markdown(f'<div class="bilan-card">{html.escape(body)}</div>', unsafe_allow_html=True)
                    if email_data.get("attachments"):
                        st.subheader("📎 Pieces jointes")
                        display_attachments(email_data["attachments"])
                except Exception as e:
                    st.error(f"Erreur affichage email: {e}")

        with tab2:
                try:
                    history = st.session_state.history if isinstance(st.session_state.history, list) else []
                    for hist_email in history:
                        if not isinstance(hist_email, dict):
                            continue
                    direction = hist_email.get("direction", "received")
                    icon = "📥" if direction == "received" else "📤"
                    date_val = hist_email.get('date')
                    if isinstance(date_val, datetime):
                        date_str = date_val.strftime('%d/%m/%Y')
                        date_str = str(date_val)[:10] if date_val else "Date inconnue"

                    subject = hist_email.get('subject', 'Sans sujet')[:50]
                    subject = hist_email.get('subject', 'Sans sujet')[:50]
                    with st.expander(f"{icon} {date_str} - {subject}"):
                        st.write(hist_email.get("body", "")[:1000])
                        if hist_email.get("attachments"):
                            st.caption(f"📎 {len(hist_email['attachments'])} piece(s) jointe(s)")
                            display_attachments(hist_email["attachments"])
                except Exception as e:
                    st.error(f"Erreur affichage historique: {e}")

        with tab3:
            try:
                if st.session_state.analysis:
                    analysis = st.session_state.analysis
                    if isinstance(analysis, dict):
                        st.info(analysis.get("resume", ""))
                        st.subheader("📊 KPIs")
                        display_kpis(analysis.get("kpis", {}))
                    else:
                        st.info("Analyse en format inattendu")
                else:
                    st.info("👆 Clique sur 'Analyser' pour lancer l'analyse IA")
            except Exception as e:
                st.error(f"Erreur affichage analyse: {e}")

        with tab4:
            with tab4:
                try:
                    if st.session_state.analysis:
                        st.subheader("✉️ Email de reponse")
                        draft = st.session_state.draft if st.session_state.draft else ""
                        # ... Boutons d'envoi ...
                        if st.button("📤 Envoyer", type="primary"):
                            st.warning("Fonction envoi a reconnecter avec la nouvelle architecture")
                    else:
                        st.info("Lance l'analyse d'abord")
                except Exception as e:
                    st.error(f"Erreur affichage reponse: {e}")
                    
            with tab5:
                try:
                    if st.button("Generer Dashboard HTML"):
                        history = st.session_state.history if isinstance(st.session_state.history, list) else []
                        html_dash = generate_client_dashboard(history)
                        st.components.v1.html(html_dash, height=800, scrolling=True)
                except Exception as e:
                    st.error(f"Erreur generation dashboard: {e}")

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
