"""
Models Database - Schema pour la plateforme client coaching
Tables: users, messages, bilans, metrics, sessions
"""

import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json

# Chemin DB
DB_PATH = "/data/coaching.db" if os.path.exists("/data") else "coaching.db"


def get_db():
    """Connexion DB avec row factory"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_platform_db():
    """Initialise les nouvelles tables pour la plateforme"""
    conn = get_db()
    c = conn.cursor()

    # Table Users (Clients + Coach)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT,
        role TEXT DEFAULT 'client',  -- 'client' ou 'coach'
        phone TEXT,
        objectif TEXT,
        date_debut TEXT,
        duree_semaines INTEGER DEFAULT 12,
        photo_url TEXT,
        is_active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    )''')

    # Table Sessions (Auth tokens)
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # Table Messages (Messagerie interne)
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER NOT NULL,
        to_user_id INTEGER NOT NULL,
        subject TEXT,
        body TEXT NOT NULL,
        is_read BOOLEAN DEFAULT 0,
        is_bilan BOOLEAN DEFAULT 0,
        parent_id INTEGER,  -- Pour les reponses
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(from_user_id) REFERENCES users(id),
        FOREIGN KEY(to_user_id) REFERENCES users(id),
        FOREIGN KEY(parent_id) REFERENCES messages(id)
    )''')

    # Table Message Attachments
    c.execute('''CREATE TABLE IF NOT EXISTS message_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        filepath TEXT NOT NULL,
        content_type TEXT,
        size INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(message_id) REFERENCES messages(id)
    )''')

    # Table Bilans (Formulaires hebdo)
    c.execute('''CREATE TABLE IF NOT EXISTS bilans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        week_number INTEGER,
        date_submitted TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        -- Metrics
        poids REAL,
        tour_taille REAL,
        tour_hanches REAL,
        tour_bras REAL,
        tour_cuisses REAL,

        -- Scores /10
        energie INTEGER,
        sommeil_qualite INTEGER,
        sommeil_heures REAL,
        stress INTEGER,
        motivation INTEGER,
        faim INTEGER,
        digestion INTEGER,
        libido INTEGER,

        -- Training
        seances_prevues INTEGER,
        seances_faites INTEGER,
        intensite_moyenne INTEGER,
        exercice_favori TEXT,
        difficultes_training TEXT,

        -- Nutrition
        respect_calories INTEGER,
        respect_macros INTEGER,
        nombre_ecarts INTEGER,
        hydratation_litres REAL,
        supplements_pris TEXT,

        -- Texte libre
        victoires TEXT,
        difficultes TEXT,
        questions TEXT,
        notes_libres TEXT,

        -- AI Analysis (JSON)
        analysis_json TEXT,
        coach_response TEXT,

        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # Table Daily Metrics (tracking quotidien rapide)
    c.execute('''CREATE TABLE IF NOT EXISTS daily_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        poids REAL,
        calories INTEGER,
        proteines INTEGER,
        pas INTEGER,
        sommeil_heures REAL,
        energie INTEGER,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        UNIQUE(user_id, date)
    )''')

    # Table Photos Progress
    c.execute('''CREATE TABLE IF NOT EXISTS progress_photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        bilan_id INTEGER,
        photo_type TEXT,  -- 'front', 'side', 'back'
        filepath TEXT NOT NULL,
        date_taken TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(bilan_id) REFERENCES bilans(id)
    )''')

    # Table Notifications
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,  -- 'message', 'bilan_reminder', 'response', 'achievement'
        title TEXT NOT NULL,
        body TEXT,
        is_read BOOLEAN DEFAULT 0,
        link TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # Table AI Drafts (brouillons IA pour le coach)
    c.execute('''CREATE TABLE IF NOT EXISTS ai_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bilan_id INTEGER,
        message_id INTEGER,
        draft_content TEXT NOT NULL,
        analysis_json TEXT,
        is_used BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(bilan_id) REFERENCES bilans(id),
        FOREIGN KEY(message_id) REFERENCES messages(id)
    )''')

    conn.commit()
    conn.close()
    print("[DB] Platform tables initialized")


# ============ USER FUNCTIONS ============

def hash_password(password: str) -> str:
    """Hash password with salt"""
    salt = "achzod_coaching_2024"  # Fixed salt for simplicity
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def create_user(email: str, password: str, name: str = "", role: str = "client",
                objectif: str = "", duree_semaines: int = 12) -> Optional[int]:
    """Cree un nouvel utilisateur"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO users (email, password_hash, name, role, objectif, duree_semaines, date_debut)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (email.lower(), hash_password(password), name, role, objectif, duree_semaines,
                   datetime.now().strftime('%Y-%m-%d')))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None  # Email deja existe


def authenticate_user(email: str, password: str) -> Optional[Dict]:
    """Authentifie un utilisateur et retourne ses infos"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email = ? AND password_hash = ? AND is_active = 1",
              (email.lower(), hash_password(password)))
    row = c.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Recupere un utilisateur par ID"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email: str) -> Optional[Dict]:
    """Recupere un utilisateur par email"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_clients() -> List[Dict]:
    """Recupere tous les clients"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role = 'client' AND is_active = 1 ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_user(user_id: int, **kwargs) -> bool:
    """Update user fields"""
    if not kwargs:
        return False

    allowed = ['name', 'phone', 'objectif', 'duree_semaines', 'photo_url', 'is_active']
    fields = {k: v for k, v in kwargs.items() if k in allowed}

    if not fields:
        return False

    conn = get_db()
    c = conn.cursor()
    set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
    values = list(fields.values()) + [user_id]
    c.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True


# ============ SESSION FUNCTIONS ============

def create_session(user_id: int, days_valid: int = 30) -> str:
    """Cree une session et retourne le token"""
    token = secrets.token_urlsafe(32)
    expires = datetime.now() + timedelta(days=days_valid)

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, ?)",
              (user_id, token, expires))
    # Update last login
    c.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.now(), user_id))
    conn.commit()
    conn.close()

    return token


def validate_session(token: str) -> Optional[Dict]:
    """Valide un token et retourne l'utilisateur"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT u.* FROM sessions s
                 JOIN users u ON s.user_id = u.id
                 WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1""",
              (token, datetime.now()))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_session(token: str) -> bool:
    """Supprime une session (logout)"""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0


# ============ MESSAGE FUNCTIONS ============

def send_message(from_user_id: int, to_user_id: int, body: str,
                subject: str = "", is_bilan: bool = False, parent_id: int = None) -> int:
    """Envoie un message"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO messages (from_user_id, to_user_id, subject, body, is_bilan, parent_id)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (from_user_id, to_user_id, subject, body, is_bilan, parent_id))
    conn.commit()
    msg_id = c.lastrowid

    # Creer notification
    c.execute("""INSERT INTO notifications (user_id, type, title, body, link)
                 VALUES (?, 'message', ?, ?, ?)""",
              (to_user_id, f"Nouveau message: {subject[:30]}...", body[:100], f"/messages/{msg_id}"))
    conn.commit()
    conn.close()
    return msg_id


def get_user_messages(user_id: int, limit: int = 50) -> List[Dict]:
    """Recupere les messages d'un utilisateur"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT m.*,
                        u_from.name as from_name, u_from.email as from_email,
                        u_to.name as to_name, u_to.email as to_email
                 FROM messages m
                 JOIN users u_from ON m.from_user_id = u_from.id
                 JOIN users u_to ON m.to_user_id = u_to.id
                 WHERE m.from_user_id = ? OR m.to_user_id = ?
                 ORDER BY m.created_at DESC
                 LIMIT ?""",
              (user_id, user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_conversation(user1_id: int, user2_id: int, limit: int = 100) -> List[Dict]:
    """Recupere la conversation entre 2 utilisateurs"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT m.*,
                        u_from.name as from_name
                 FROM messages m
                 JOIN users u_from ON m.from_user_id = u_from.id
                 WHERE (m.from_user_id = ? AND m.to_user_id = ?)
                    OR (m.from_user_id = ? AND m.to_user_id = ?)
                 ORDER BY m.created_at ASC
                 LIMIT ?""",
              (user1_id, user2_id, user2_id, user1_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_messages_read(user_id: int, from_user_id: int) -> int:
    """Marque les messages comme lus"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""UPDATE messages SET is_read = 1
                 WHERE to_user_id = ? AND from_user_id = ? AND is_read = 0""",
              (user_id, from_user_id))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected


def get_unread_count(user_id: int) -> int:
    """Compte les messages non lus"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE to_user_id = ? AND is_read = 0", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


# ============ BILAN FUNCTIONS ============

def submit_bilan(user_id: int, data: Dict) -> int:
    """Soumet un bilan hebdo"""
    conn = get_db()
    c = conn.cursor()

    # Calculer le numero de semaine
    c.execute("SELECT COUNT(*) + 1 FROM bilans WHERE user_id = ?", (user_id,))
    week_num = c.fetchone()[0]

    c.execute("""INSERT INTO bilans (
        user_id, week_number, poids, tour_taille, tour_hanches, tour_bras, tour_cuisses,
        energie, sommeil_qualite, sommeil_heures, stress, motivation, faim, digestion, libido,
        seances_prevues, seances_faites, intensite_moyenne, exercice_favori, difficultes_training,
        respect_calories, respect_macros, nombre_ecarts, hydratation_litres, supplements_pris,
        victoires, difficultes, questions, notes_libres
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (user_id, week_num,
               data.get('poids'), data.get('tour_taille'), data.get('tour_hanches'),
               data.get('tour_bras'), data.get('tour_cuisses'),
               data.get('energie'), data.get('sommeil_qualite'), data.get('sommeil_heures'),
               data.get('stress'), data.get('motivation'), data.get('faim'),
               data.get('digestion'), data.get('libido'),
               data.get('seances_prevues'), data.get('seances_faites'),
               data.get('intensite_moyenne'), data.get('exercice_favori'),
               data.get('difficultes_training'),
               data.get('respect_calories'), data.get('respect_macros'),
               data.get('nombre_ecarts'), data.get('hydratation_litres'),
               data.get('supplements_pris'),
               data.get('victoires'), data.get('difficultes'),
               data.get('questions'), data.get('notes_libres')))

    conn.commit()
    bilan_id = c.lastrowid
    conn.close()
    return bilan_id


def get_user_bilans(user_id: int, limit: int = 20) -> List[Dict]:
    """Recupere les bilans d'un utilisateur"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT * FROM bilans WHERE user_id = ?
                 ORDER BY date_submitted DESC LIMIT ?""",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_bilan_by_id(bilan_id: int) -> Optional[Dict]:
    """Recupere un bilan par ID"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM bilans WHERE id = ?", (bilan_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_bilan_analysis(bilan_id: int, analysis_json: str, coach_response: str = None):
    """Met a jour l'analyse IA d'un bilan"""
    conn = get_db()
    c = conn.cursor()
    if coach_response:
        c.execute("UPDATE bilans SET analysis_json = ?, coach_response = ? WHERE id = ?",
                  (analysis_json, coach_response, bilan_id))
    else:
        c.execute("UPDATE bilans SET analysis_json = ? WHERE id = ?",
                  (analysis_json, bilan_id))
    conn.commit()
    conn.close()


# ============ DAILY METRICS ============

def log_daily_metric(user_id: int, date: str, **kwargs) -> bool:
    """Log une metrique quotidienne"""
    allowed = ['poids', 'calories', 'proteines', 'pas', 'sommeil_heures', 'energie', 'notes']
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}

    if not fields:
        return False

    conn = get_db()
    c = conn.cursor()

    # Upsert
    columns = ['user_id', 'date'] + list(fields.keys())
    placeholders = ', '.join(['?'] * len(columns))
    update_clause = ', '.join([f"{k} = excluded.{k}" for k in fields.keys()])

    sql = f"""INSERT INTO daily_metrics ({', '.join(columns)})
              VALUES ({placeholders})
              ON CONFLICT(user_id, date) DO UPDATE SET {update_clause}"""

    c.execute(sql, [user_id, date] + list(fields.values()))
    conn.commit()
    conn.close()
    return True


def get_daily_metrics(user_id: int, days: int = 30) -> List[Dict]:
    """Recupere les metriques quotidiennes"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT * FROM daily_metrics
                 WHERE user_id = ?
                 ORDER BY date DESC LIMIT ?""",
              (user_id, days))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ============ NOTIFICATIONS ============

def get_notifications(user_id: int, unread_only: bool = False, limit: int = 20) -> List[Dict]:
    """Recupere les notifications"""
    conn = get_db()
    c = conn.cursor()
    if unread_only:
        c.execute("""SELECT * FROM notifications
                     WHERE user_id = ? AND is_read = 0
                     ORDER BY created_at DESC LIMIT ?""",
                  (user_id, limit))
    else:
        c.execute("""SELECT * FROM notifications
                     WHERE user_id = ?
                     ORDER BY created_at DESC LIMIT ?""",
                  (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_notification_read(notification_id: int) -> bool:
    """Marque une notification comme lue"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0


def create_notification(user_id: int, type: str, title: str, body: str = "", link: str = ""):
    """Cree une notification"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO notifications (user_id, type, title, body, link)
                 VALUES (?, ?, ?, ?, ?)""",
              (user_id, type, title, body, link))
    conn.commit()
    conn.close()


# ============ STATS & DASHBOARD ============

def get_client_stats(user_id: int) -> Dict:
    """Stats completes d'un client pour son dashboard"""
    conn = get_db()
    c = conn.cursor()

    stats = {}

    # User info
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if user:
        stats['user'] = dict(user)

    # Nombre de bilans
    c.execute("SELECT COUNT(*) FROM bilans WHERE user_id = ?", (user_id,))
    stats['total_bilans'] = c.fetchone()[0]

    # Dernier bilan
    c.execute("SELECT * FROM bilans WHERE user_id = ? ORDER BY date_submitted DESC LIMIT 1", (user_id,))
    last_bilan = c.fetchone()
    stats['last_bilan'] = dict(last_bilan) if last_bilan else None

    # Evolution poids (tous les bilans)
    c.execute("SELECT week_number, poids, date_submitted FROM bilans WHERE user_id = ? AND poids IS NOT NULL ORDER BY date_submitted", (user_id,))
    stats['weight_history'] = [dict(row) for row in c.fetchall()]

    # Moyennes KPIs sur les 4 derniers bilans
    c.execute("""SELECT AVG(energie) as avg_energie, AVG(sommeil_qualite) as avg_sommeil,
                        AVG(motivation) as avg_motivation, AVG(stress) as avg_stress
                 FROM (SELECT * FROM bilans WHERE user_id = ? ORDER BY date_submitted DESC LIMIT 4)""",
              (user_id,))
    avgs = c.fetchone()
    stats['avg_kpis'] = dict(avgs) if avgs else {}

    # Messages non lus
    c.execute("SELECT COUNT(*) FROM messages WHERE to_user_id = ? AND is_read = 0", (user_id,))
    stats['unread_messages'] = c.fetchone()[0]

    # Jours restants
    if user:
        try:
            from datetime import datetime, timedelta
            date_debut = datetime.strptime(dict(user)['date_debut'], '%Y-%m-%d')
            duree = dict(user).get('duree_semaines', 12)
            date_fin = date_debut + timedelta(weeks=duree)
            stats['jours_restants'] = max(0, (date_fin - datetime.now()).days)
        except:
            stats['jours_restants'] = -1

    conn.close()
    return stats


def get_coach_dashboard() -> Dict:
    """Dashboard pour le coach - vue globale"""
    conn = get_db()
    c = conn.cursor()

    dashboard = {}

    # Total clients actifs
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'client' AND is_active = 1")
    dashboard['total_clients'] = c.fetchone()[0]

    # Bilans en attente de reponse (soumis mais pas de coach_response)
    c.execute("""SELECT b.*, u.name, u.email
                 FROM bilans b
                 JOIN users u ON b.user_id = u.id
                 WHERE b.coach_response IS NULL
                 ORDER BY b.date_submitted DESC""")
    dashboard['pending_bilans'] = [dict(row) for row in c.fetchall()]

    # Messages non lus (vers le coach)
    c.execute("""SELECT COUNT(*) FROM messages m
                 JOIN users u ON m.to_user_id = u.id
                 WHERE u.role = 'coach' AND m.is_read = 0""")
    dashboard['unread_messages'] = c.fetchone()[0]

    # Clients actifs cette semaine (ont soumis un bilan)
    c.execute("""SELECT COUNT(DISTINCT user_id) FROM bilans
                 WHERE date_submitted > datetime('now', '-7 days')""")
    dashboard['active_this_week'] = c.fetchone()[0]

    # Liste clients avec leur dernier bilan
    c.execute("""SELECT u.*,
                        (SELECT MAX(date_submitted) FROM bilans WHERE user_id = u.id) as last_bilan_date,
                        (SELECT COUNT(*) FROM bilans WHERE user_id = u.id) as total_bilans
                 FROM users u
                 WHERE u.role = 'client' AND u.is_active = 1
                 ORDER BY last_bilan_date DESC NULLS LAST""")
    dashboard['clients'] = [dict(row) for row in c.fetchall()]

    conn.close()
    return dashboard


# Init au chargement
if __name__ == "__main__":
    init_platform_db()
    print("Database initialized!")
