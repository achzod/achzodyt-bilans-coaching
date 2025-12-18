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
import threading
import time

# --- GESTION DATABASE (Intégré pour eviter erreurs d'import) ---

# Chemin de la DB: toujours local maintenant
DB_PATH = "coaching.db"
ATTACHMENTS_DIR = "attachments"

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
                        imap_uid TEXT, -- ID IMAP pour charger le contenu a la demande
                        FOREIGN KEY(client_email) REFERENCES clients(email))''')
            
            # Migration: s'assurer que imap_uid existe
            try:
                c.execute("ALTER TABLE emails ADD COLUMN imap_uid TEXT")
            except:
                pass # Deja la
            
            try:
                c.execute("ALTER TABLE emails ADD COLUMN body_loaded BOOLEAN DEFAULT 0")
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
            imap_uid = email_data.get('id', '')  # ID IMAP (UID) pour charger a la demande
            
            c.execute("""INSERT OR REPLACE INTO emails 
                         (message_id, client_email, subject, date, body, direction, is_bilan, analysis_json, body_loaded, imap_uid)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (message_id, client_email, subject, date_val, body, direction, is_bilan, analysis_json, body_loaded, imap_uid))
            
            conn.commit()  # FORCER le commit immédiatement
            
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

    def get_client_history(self, client_email: str, limit: int = None, load_attachments: bool = False) -> List[Dict]:
        """Recupere TOUT l'historique d'un client depuis la DB avec toutes les pièces jointes"""
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Recherche flexible (contient) - SANS LIMITE pour avoir tout depuis le début
            if client_email and client_email.strip():
                if limit:
                    c.execute(f"""SELECT * FROM emails 
                                WHERE client_email LIKE ? OR client_email LIKE ?
                                ORDER BY date DESC LIMIT ?""", (f"%{client_email}%", client_email, limit))
                else:
                    # PAS DE LIMITE - TOUT depuis le début
                    c.execute(f"""SELECT * FROM emails 
                                WHERE client_email LIKE ? OR client_email LIKE ?
                                ORDER BY date DESC""", (f"%{client_email}%", client_email))
            else:
                if limit:
                    c.execute(f"SELECT * FROM emails ORDER BY date DESC LIMIT ?", (limit,))
                else:
                    c.execute(f"SELECT * FROM emails ORDER BY date DESC")

            rows = c.fetchall()
            print(f"[DB] get_client_history: {len(rows)} emails trouvés (TOUT depuis le début)")
            
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
                    
                    # CHARGER les attachments si demandé (pour l'analyse IA complète)
                    email_dict['body_loaded'] = email_dict.get('body_loaded', 0)
                    email_dict['imap_uid'] = email_dict.get('imap_uid', '')
                    
                    if load_attachments:
                        # Charger les attachments depuis la DB
                        message_id = email_dict.get('message_id')
                        if message_id:
                            c.execute("SELECT filename, filepath FROM attachments WHERE message_id = ?", (message_id,))
                            attachments = []
                            for att_row in c.fetchall():
                                att_dict = dict(att_row)
                                # Vérifier que le fichier existe
                                if att_dict.get('filepath') and os.path.exists(att_dict['filepath']):
                                    attachments.append({
                                        'filename': att_dict.get('filename', ''),
                                        'filepath': att_dict.get('filepath', ''),
                                        'exists': True
                                    })
                            email_dict['attachments'] = attachments
                        else:
                            email_dict['attachments'] = []
                    else:
                        email_dict['attachments'] = []
                    
                    history.append(email_dict)
                except Exception as e:
                    print(f"[DB] Erreur parsing email: {e}")
                    continue
            
            # Tri final par date (du plus ancien au plus récent pour le contexte)
            try:
                history.sort(key=lambda x: x.get('date', datetime.min) if isinstance(x.get('date'), datetime) else datetime.min)
            except:
                pass
                
            print(f"[DB] Historique complet chargé: {len(history)} emails avec {sum(len(e.get('attachments', [])) for e in history)} pièces jointes")
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
    "typeform", "confirmation", "paiement", "payment", "commande", "order",
    "noreply", "no-reply", "notification", "newsletter", "unsubscribe"
]

# --- CHARGEMENT EN ARRIÈRE-PLAN ---
SYNC_STATS_FILE = "sync_stats.json"

def load_sync_stats():
    """Charge les stats depuis le fichier"""
    try:
        if os.path.exists(SYNC_STATS_FILE):
            with open(SYNC_STATS_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {
        'total_processed': 0,
        'saved': 0,
        'ignored': 0,
        'errors': 0,
        'is_running': False,
        'last_update': None
    }

def save_sync_stats(stats):
    """Sauvegarde les stats dans le fichier"""
    try:
        with open(SYNC_STATS_FILE, 'w') as f:
            json.dump(stats, f)
    except:
        pass

def background_sync_worker(reader, db):
    """Fonction pour charger les emails en arrière-plan (appelée dans un thread)
    Charge UNIQUEMENT les headers des 50 derniers emails non lus (TRÈS RAPIDE)
    L'historique complet sera chargé à la demande quand on clique sur un email
    """
    import gc
    stats = load_sync_stats()
    stats['is_running'] = True
    save_sync_stats(stats)
    
    try:
        # Charger UNIQUEMENT les headers des 50 derniers emails non lus (TRÈS RAPIDE)
        unread_emails = reader.get_recent_emails(days=30, unread_only=True, max_emails=50)
        
        if not unread_emails or not isinstance(unread_emails, list):
            stats['is_running'] = False
            save_sync_stats(stats)
            return
        
        print(f"[BG SYNC] {len(unread_emails)} emails non lus trouvés - chargement headers uniquement")
        
        # Traiter chaque email non lu (seulement headers)
        for email in unread_emails:
            try:
                if not isinstance(email, dict):
                    continue
                
                message_id = email.get('message_id') or email.get('id')
                if not message_id:
                    continue
                
                # Filtre anti-spam
                subject = email.get('subject', '').lower()
                sender = email.get('from_email', '').lower()
                if any(p in subject for p in EXCLUDE_PATTERNS) or any(p in sender for p in EXCLUDE_PATTERNS):
                    stats['ignored'] += 1
                    continue
                
                # Sauvegarder UNIQUEMENT les headers (rapide, pas de body/attachments)
                if not db.email_exists(str(message_id)):
                    email['body'] = ''
                    email['attachments'] = []
                    if db.save_email(email):
                        stats['saved'] += 1
                
                stats['total_processed'] += 1
                stats['last_update'] = datetime.now().isoformat()
            
            except Exception as e:
                stats['errors'] += 1
                print(f"[BG SYNC] Erreur email: {e}")
                continue
        
        # Sauvegarder les stats une seule fois à la fin
        save_sync_stats(stats)
        gc.collect()
        
        stats['is_running'] = False
        save_sync_stats(stats)
        print(f"[BG SYNC] ✅ Synchronisation terminée: {stats['saved']} emails sauvegardés (headers seulement)")
    
    except Exception as e:
        print(f"[BG SYNC] Erreur cycle: {e}")
        import traceback
        traceback.print_exc()
        stats['is_running'] = False
        save_sync_stats(stats)

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
# Init session state
if 'db' not in st.session_state:
    st.session_state.db = DatabaseManager()

is_render = os.getenv("RENDER") is not None
if 'reader' not in st.session_state:
    if is_render:
        st.session_state.reader = None # No instantation on startup for Render
    else:
        st.session_state.reader = EmailReader()

if 'emails' not in st.session_state:
    st.session_state.emails = []
# ... rest of init remains same
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
    st.markdown('<div class="main-header">🚀 Bilans Coaching - Tableau de Bord</div>', unsafe_allow_html=True)

    # Initialiser session state
    if 'reader' not in st.session_state:
        st.session_state.reader = EmailReader()
    if 'db' not in st.session_state:
        st.session_state.db = DatabaseManager()
    
    # Charger les stats depuis le fichier
    st.session_state.sync_stats = load_sync_stats()
    
    # CHARGEMENT AUTOMATIQUE DES EMAILS NON LUS AU DÉMARRAGE
    if 'emails' not in st.session_state or not st.session_state.emails:
        try:
            # Charger depuis DB (très rapide)
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM emails ORDER BY date DESC LIMIT 50")
            rows = c.fetchall()
            conn.close()
            
            if rows:
                emails_from_db = []
                for row in rows:
                    try:
                        email_dict = dict(row)
                        if email_dict.get('date'):
                            try:
                                email_dict['date'] = datetime.fromisoformat(email_dict['date'])
                            except:
                                email_dict['date'] = datetime.now()
                        emails_from_db.append(email_dict)
                    except:
                        continue
                st.session_state.emails = emails_from_db
            else:
                # DB VIDE -> Synchro automatique !
                st.session_state.emails = []
                
                # Sur Render, on évite de bloquer trop longtemps au startup pour la health check
                is_render = os.getenv("RENDER") is not None
                
                if is_render:
                    st.info("ℹ️ Base de données vide. Cliquez sur 'Synchroniser' pour charger les emails.")
                else:
                    st.warning("⚠️ Base de données vide. Synchronisation automatique en cours...")
                    try:
                        if st.session_state.reader is None:
                            st.session_state.reader = EmailReader()
                        
                        # Synchro légère et RAPIDE
                        with st.spinner("🔄 Chargement initial..."):
                            import socket
                            socket.setdefaulttimeout(5) # Très court pour le startup
                            new_emails = st.session_state.reader.get_recent_emails(days=2, unread_only=True, max_emails=10)
                            
                            if new_emails and isinstance(new_emails, list):
                                saved = 0
                                for email in new_emails:
                                    if isinstance(email, dict):
                                        msg_id = email.get('message_id') or email.get('id')
                                        if msg_id and not st.session_state.db.email_exists(str(msg_id)):
                                            email['body'] = ''
                                            email['attachments'] = []
                                            if st.session_state.db.save_email(email):
                                                saved += 1
                                if saved > 0:
                                    st.success(f"✅ {saved} emails chargés !")
                                    st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erreur synchro initiale: {e}")
        except Exception as e:
            st.error(f"Erreur DB: {e}")


    # Sidebar - Synchro
    with st.sidebar:
        st.header("🔄 Synchronisation")
        
        # Afficher les stats du chargement en arrière-plan (recharger depuis fichier)
        stats = load_sync_stats()
        if stats.get('is_running', False):
            st.success("🟢 Chargement automatique actif")
            st.caption(f"✅ {stats.get('saved', 0)} sauvegardés")
            st.caption(f"⏭️ {stats.get('ignored', 0)} ignorés")
            st.caption(f"❌ {stats.get('errors', 0)} erreurs")
            if stats.get('last_update'):
                try:
                    last = datetime.fromisoformat(stats['last_update'])
                    st.caption(f"🕐 Dernière mise à jour: {last.strftime('%H:%M:%S')}")
                except:
                    pass
        else:
            if stats.get('saved', 0) > 0:
                st.info(f"✅ {stats.get('saved', 0)} emails chargés")
            else:
                st.info("⏳ Chargement en cours...")

        days = st.selectbox("Jours a scanner", [1, 3, 7, 30], index=1) # Default 3 jours
        
        if st.button("📥 Synchroniser Gmail", use_container_width=True, type="primary"):
            # S'assurer que reader est initialisé
            if st.session_state.reader is None:
                st.session_state.reader = EmailReader()
                    
            with st.status("Synchronisation en cours...", expanded=True) as status:
                st.write("🔌 Connexion Gmail...")
                
                # 1. Recuperer les emails NON LUS uniquement (LIMITÉ à 20 pour performance)
                try:
                    new_emails = st.session_state.reader.get_recent_emails(days=7, unread_only=True, max_emails=20) # Seulement non lus, limité à 20
                    if new_emails is None:
                        new_emails = []
                    if not isinstance(new_emails, list):
                        new_emails = []
                    st.write(f"📨 {len(new_emails)} emails NON LUS trouves")
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
        st.header("📧 Emails Non Lus")
        
        # Bouton refresh
        if st.button("🔄 Rafraichir", use_container_width=True):
            st.session_state.emails = []
            st.rerun()
        
        # Charger depuis la DB uniquement (RAPIDE, pas de connexion Gmail)
        try:
            # Charger les 20 derniers emails depuis la DB (instantané)
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM emails ORDER BY date DESC LIMIT 20")
            rows = c.fetchall()
            conn.close()
            
            if rows:
                emails_from_db = []
                for row in rows:
                    try:
                        email_dict = dict(row)
                        # Parse date
                        if email_dict.get('date'):
                            try:
                                email_dict['date'] = datetime.fromisoformat(email_dict['date'])
                            except:
                                email_dict['date'] = datetime.now()
                        else:
                            email_dict['date'] = datetime.now()
                        emails_from_db.append(email_dict)
                    except:
                        continue
                
                st.session_state.emails = emails_from_db
                st.info(f"📧 {len(emails_from_db)} email(s) depuis la base de données")
            else:
                st.session_state.emails = []
                st.info("👆 Clique sur 'Synchroniser Gmail' pour charger les emails")
        except Exception as e:
             pass

    # --- NAVIGATION PRINCIPALE ---
    
    # ÉTAT A: AUCUN EMAIL SÉLECTIONNÉ -> TABLEAU DE BORD (LISTE)
    if not st.session_state.selected_email:
        st.subheader("📬 Boîte de Réception (Non Lus & Récents)")
        
        # KPI rapide
        st.metric("Emails en attente", len(st.session_state.emails))
        
        # Liste des emails
        if st.session_state.emails:
            for i, email in enumerate(st.session_state.emails):
                with st.container():
                    # Style Card
                    st.markdown(f"""
                    <div style="background: white; padding: 15px; border-radius: 10px; border: 1px solid #eee; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
                        <div style="font-weight: bold; font-size: 1.1rem; color: #333;">{email.get('subject', 'Sans sujet')}</div>
                        <div style="color: #666; font-size: 0.9rem; margin-bottom: 5px;">
                            👤 <b>{email.get('client_email', 'Inconnu')}</b> | 📅 {email.get('date').strftime('%d/%m/%Y %H:%M') if isinstance(email.get('date'), datetime) else str(email.get('date'))}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Actions
                    c1, c2, c3 = st.columns([1, 1, 4])
                    with c1:
                        if st.button("🔍 Ouvrir & Analyser", key=f"btn_open_{i}_{email.get('message_id')}", use_container_width=True):
                            st.session_state.selected_email = email
                            st.session_state.analysis = None
                            st.session_state.history = [] # Forcer le rechargement de l'historique
                            st.rerun()
                    with c2:
                         if st.button("🗑️ Ignorer", key=f"btn_ignore_{i}_{email.get('message_id')}", use_container_width=True):
                            # TODO: Marquer comme lu en DB
                            st.info("Email ignoré (visuellement)")
        else:
            st.info("📭 Aucun email à afficher. Lance une synchronisation dans la barre latérale !")

    # ÉTAT B: EMAIL SÉLECTIONNÉ -> VUE DÉTAILLÉE AVEC ONGLETS
    else:
        if st.button("⬅️ Retour à la liste", use_container_width=True):
            st.session_state.selected_email = None
            st.session_state.analysis = None
            st.session_state.history = []
            st.rerun()
            
        email = st.session_state.selected_email
        client_email = email.get('client_email', '')
        
        st.header(f"📧 {email.get('subject', 'Sans sujet')}")
        st.caption(f"De: **{client_email}** | Date: {email.get('date')}")
        
        # 1. Charger le contenu complet SI manquant
        if not email.get('body') and email.get('imap_uid'):
            with st.spinner("🔌 Chargement du contenu Gmail..."):
                full_data = st.session_state.reader.load_email_content(email['imap_uid'])
                if full_data.get('loaded'):
                    email['body'] = full_data['body']
                    email['attachments'] = full_data['attachments']
                    # Garder en session
                    st.session_state.selected_email = email
        
        # 2. Charger l'historique complet pour l'IA
        if not st.session_state.history:
            with st.spinner("📜 Récupération de l'historique client..."):
                st.session_state.history = st.session_state.db.get_client_history(client_email, load_attachments=True)
        
        # 3. ONGLETS
        tab1, tab2, tab3, tab4 = st.tabs(["📨 Email Actuel", "📜 Historique Complet", "🤖 Analyse IA", "✉️ Email de Réponse"])
        
        with tab1:
            st.markdown(f'<div class="bilan-card">{html.escape(email.get("body", ""))}</div>', unsafe_allow_html=True)
            if email.get('attachments'):
                st.subheader(f"📎 Pièces jointes ({len(email['attachments'])})")
                display_attachments(email['attachments'])
        
        with tab2:
            st.subheader(f"Historique de {client_email}")
            if st.session_state.history:
                for h_email in reversed(st.session_state.history): # Plus récent en haut
                    direction = "📥" if h_email.get('direction') == 'received' else "📤"
                    with st.expander(f"{direction} {h_email.get('date').strftime('%d/%m/%Y')} - {h_email.get('subject')}"):
                        st.write(h_email.get('body', '')[:1000])
            else:
                st.info("Aucun historique trouvé pour ce client.")
        
        with tab3:
            st.subheader("🤖 Analyse par Claude 3.5 Sonnet")
            
            # Si déjà analysé, afficher
            if st.session_state.analysis:
                res = st.session_state.analysis
                st.info(res.get("resume", ""))
                
                # KPIs
                if res.get("kpis"):
                    display_kpis(res["kpis"])
                
                # Points positifs / améliorations
                c_pos, c_neg = st.columns(2)
                with c_pos:
                    st.success("✅ Points Positifs")
                    for p in res.get("points_positifs", []): st.write(f"- {p}")
                with c_neg:
                    st.error("⚠️ À Améliorer")
                    for p in res.get("points_ameliorer", []): 
                        if isinstance(p, dict): st.write(f"- **{p.get('probleme')}**: {p.get('solution')}")
                        else: st.write(f"- {p}")
            
            # Bouton Lancer Analyse
            if st.button("✨ Lancer l'Analyse IA (Historique + Photos)", type="primary", use_container_width=True):
                with st.status("🧠 Analyse en cours par Claude 3.5...", expanded=True) as status:
                    st.write("Déchiffrage du bilan et analyse de l'historique...")
                    result = analyze_coaching_bilan(email, st.session_state.history, client_email)
                    
                    if result.get("success"):
                        st.session_state.analysis = result["analysis"]
                        st.session_state.draft = result["analysis"].get("draft_email", "")
                        status.update(label="✅ Analyse terminée !", state="complete")
                        st.rerun()
                    else:
                        st.error(f"Erreur IA: {result.get('error')}")
                        status.update(label="❌ Erreur IA", state="error")
        
        with tab4:
            st.subheader("✉️ Brouillon de Réponse")
            if st.session_state.draft:
                draft = st.text_area("Modifier l'email :", value=st.session_state.draft, height=400)
                st.session_state.draft = draft
                
                col_send, col_regen = st.columns(2)
                with col_send:
                    if st.button("📤 Envoyer par Gmail", type="primary", use_container_width=True):
                        st.warning("Fonction d'envoi à configurer (App Password requis)")
                with col_regen:
                    if st.button("🔄 Régénérer", use_container_width=True):
                         # Logique de régénération...
                         pass
            else:
                st.info("Lance l'analyse IA d'abord pour générer un brouillon.")

if __name__ == "__main__":
    main()
