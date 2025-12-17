"""
FastAPI Backend - Plateforme Coaching Achzod
- Coach: voit tous emails Gmail, groupés par client, IA intégrée
- Client: accès via magic link, dashboard évolution
"""

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import os
import json
import hashlib
import secrets
import sqlite3
import base64

from models import (
    init_platform_db, create_user, authenticate_user, get_user_by_id, get_user_by_email,
    get_all_clients, create_session, validate_session, delete_session, DB_PATH
)

from analyzer import analyze_coaching_bilan
from email_reader import EmailReader

# ============ INIT ============
init_platform_db()

app = FastAPI(title="Achzod Coaching Platform", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)

# ============ DATABASE SETUP ============
def init_tables():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Emails from Gmail
    c.execute('''
        CREATE TABLE IF NOT EXISTS gmail_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_email TEXT NOT NULL,
            sender_name TEXT,
            message_id TEXT UNIQUE,
            imap_id TEXT,
            direction TEXT DEFAULT 'received',
            subject TEXT,
            body TEXT,
            body_loaded INTEGER DEFAULT 0,
            date_sent TIMESTAMP,
            has_attachments INTEGER DEFAULT 0,
            attachments_json TEXT DEFAULT '[]',
            status TEXT DEFAULT 'new',
            replied_at TIMESTAMP,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Clients (auto-created from emails)
    c.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            phone TEXT,
            objectif TEXT,
            date_debut TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_email_date TIMESTAMP,
            total_emails INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            notes TEXT
        )
    ''')

    # Magic links for client auth
    c.execute('''
        CREATE TABLE IF NOT EXISTS magic_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_email TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            used INTEGER DEFAULT 0
        )
    ''')

    # Client sessions
    c.execute('''
        CREATE TABLE IF NOT EXISTS client_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_email TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP
        )
    ''')

    # KPIs / Metrics tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS client_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_email TEXT NOT NULL,
            date_recorded TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            poids REAL,
            tour_taille REAL,
            tour_hanches REAL,
            tour_poitrine REAL,
            tour_bras REAL,
            tour_cuisses REAL,
            body_fat REAL,
            energie INTEGER,
            sommeil INTEGER,
            stress INTEGER,
            adherence INTEGER,
            notes TEXT,
            source TEXT DEFAULT 'manual',
            email_id INTEGER
        )
    ''')

    # Attachments storage (images as base64)
    c.execute('''
        CREATE TABLE IF NOT EXISTS email_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id INTEGER NOT NULL,
            filename TEXT,
            content_type TEXT,
            data TEXT,
            is_image INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('CREATE INDEX IF NOT EXISTS idx_metrics_client ON client_metrics(client_email)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_metrics_date ON client_metrics(date_recorded DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_attachments_email ON email_attachments(email_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_emails_sender ON gmail_emails(sender_email)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_emails_date ON gmail_emails(date_sent DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_emails_status ON gmail_emails(status)')

    conn.commit()
    conn.close()

init_tables()

# ============ HELPER FUNCTIONS ============

# Spam/useless email filter - AGGRESSIVE
SPAM_DOMAINS = [
    # Transactional/notifications
    'typeform.com', 'typeform.io', 'shopify.com', 'stripe.com', 'paypal',
    'noreply', 'no-reply', 'mailer-daemon', 'postmaster', 'notification',
    'donotreply', 'automated', 'mailer@', 'bounce', 'service@',
    # Marketing
    'newsletter', 'marketing', 'promo', 'pub@', 'info@', 'contact@',
    'support@', 'help@', 'billing@', 'invoice', 'receipt', 'confirmation',
    'mailchimp', 'sendgrid', 'sendinblue', 'brevo', 'klaviyo', 'hubspot',
    'mailjet', 'constantcontact', 'campaign', 'email.', 'mail@',
    # Social/Tech platforms
    'calendly', 'zoom.us', 'zoom.com', 'google.com', 'facebook', 'facebookmail',
    'instagram', 'twitter', 'linkedin', 'youtube', 'tiktok', 'meta.com',
    'metamail', 'business.fb', 'fb.com', 'whatsapp',
    # Dev/hosting
    'render.com', 'github.com', 'gitlab.com', 'vercel.com', 'netlify.com',
    'heroku', 'digitalocean', 'cloudflare',
    # Ecommerce
    'amazon.', 'aws.amazon', 'ebay', 'aliexpress', 'wish.com',
    # Big tech
    'apple.com', 'microsoft.com', 'outlook.com', 'googlemail', 'icloud',
    'account-security', 'security@', 'alerts@', 'updates@',
    # Generic
    'team@', 'hello@', 'bonjour@', 'sales@', 'admin@', 'webmaster@',
    # Specific spam I see
    'theharmonist', 'eklipse', 'zohomail', 'zohocorp',
]

SPAM_SUBJECTS = [
    # Orders/payments
    'confirmation de commande', 'order confirmation', 'votre commande',
    'your order', 'receipt', 'reçu', 'facture', 'invoice', 'payment',
    'paiement', 'subscription', 'abonnement', 'your money', 'bank account',
    'transaction', 'purchase', 'achat',
    # Account stuff
    'verify your email', 'vérifiez votre', 'confirm your', 'confirmez votre',
    'password reset', 'réinitialisation', 'security alert', 'alerte sécurité',
    'welcome to', 'bienvenue', 'thank you for signing', 'merci de vous être',
    'your account', 'votre compte', 'account update', 'mise à jour',
    # Notifications
    'notification', 'reminder', 'rappel', 'newsletter', 'unsubscribe',
    'automatic reply', 'réponse automatique', 'out of office', 'absence',
    # Marketing
    'cadeaux', 'promo', 'offre', 'soldes', 'réduction', 'discount',
    'fêtes', 'holidays', 'black friday', 'cyber monday', 'special offer',
    'limited time', 'don\'t miss', 'exclusive', 'gratuit', 'free',
    # Spam patterns
    'contribution à notre plateforme', 'meta for business', 'ad account',
    'boost your', 'grow your', 'increase your',
]

def is_spam_email(email_data: Dict) -> bool:
    """Check if email should be filtered out"""
    sender = (email_data.get('from_email') or email_data.get('from', '')).lower()
    subject = (email_data.get('subject') or '').lower()

    # Check sender domain/address
    for spam in SPAM_DOMAINS:
        if spam in sender:
            return True

    # Check subject
    for spam in SPAM_SUBJECTS:
        if spam in subject:
            return True

    # Filter emails from self (achzodyt or coaching)
    if 'achzodyt@gmail.com' in sender or 'coaching@achzodcoaching.com' in sender:
        return True

    return False

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def save_email(email_data: Dict) -> bool:
    """Save email and auto-create/update client (headers only for fast sync)"""
    conn = get_db()
    c = conn.cursor()

    try:
        # Check if exists
        msg_id = email_data.get('message_id', f"gen_{datetime.now().timestamp()}")
        c.execute('SELECT id FROM gmail_emails WHERE message_id = ?', (msg_id,))
        if c.fetchone():
            conn.close()
            return False

        sender_email = email_data.get('from_email', '').lower()
        sender_name = email_data.get('from', '').split('<')[0].strip()

        # Insert email (body may be empty - loaded on demand)
        attachments = email_data.get('attachments', [])
        body = email_data.get('body', '')
        body_loaded = 1 if body and len(body) > 10 else 0

        c.execute('''
            INSERT INTO gmail_emails
            (sender_email, sender_name, message_id, imap_id, direction, subject, body, body_loaded,
             date_sent, has_attachments, attachments_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            sender_email,
            sender_name,
            msg_id,
            email_data.get('id', ''),  # IMAP ID for on-demand loading
            email_data.get('direction', 'received'),
            email_data.get('subject', ''),
            body,
            body_loaded,
            email_data.get('date').isoformat() if email_data.get('date') else datetime.now().isoformat(),
            1 if attachments else 0,
            json.dumps([{'filename': a.get('filename', 'file')} for a in attachments]) if attachments else '[]',
            'new'
        ))

        # Auto-create/update client
        if sender_email and email_data.get('direction') == 'received':
            c.execute('SELECT id, total_emails FROM clients WHERE email = ?', (sender_email,))
            client = c.fetchone()

            if client:
                c.execute('''
                    UPDATE clients SET
                    name = COALESCE(?, name),
                    last_email_date = ?,
                    total_emails = total_emails + 1
                    WHERE email = ?
                ''', (sender_name if sender_name else None,
                      email_data.get('date').isoformat() if email_data.get('date') else datetime.now().isoformat(),
                      sender_email))
            else:
                c.execute('''
                    INSERT INTO clients (email, name, last_email_date, total_emails)
                    VALUES (?, ?, ?, 1)
                ''', (sender_email, sender_name,
                      email_data.get('date').isoformat() if email_data.get('date') else datetime.now().isoformat()))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving email: {e}")
        conn.close()
        return False

def get_all_emails_grouped() -> Dict:
    """Get all emails grouped by sender"""
    conn = get_db()
    c = conn.cursor()

    # Get clients with their email counts
    c.execute('''
        SELECT c.*,
               (SELECT COUNT(*) FROM gmail_emails WHERE sender_email = c.email AND status = 'new') as unread_count
        FROM clients c
        ORDER BY c.last_email_date DESC
    ''')
    clients = [dict(row) for row in c.fetchall()]

    # Get recent emails
    c.execute('''
        SELECT * FROM gmail_emails
        WHERE direction = 'received'
        ORDER BY date_sent DESC
        LIMIT 100
    ''')
    recent_emails = [dict(row) for row in c.fetchall()]

    conn.close()
    return {"clients": clients, "recent_emails": recent_emails}

def get_client_emails(client_email: str) -> Dict:
    """Get all emails for a specific client"""
    conn = get_db()
    c = conn.cursor()

    # Get client info
    c.execute('SELECT * FROM clients WHERE email = ?', (client_email.lower(),))
    client_row = c.fetchone()
    client = dict(client_row) if client_row else {"email": client_email}

    # Get all emails (received + sent)
    c.execute('''
        SELECT * FROM gmail_emails
        WHERE sender_email = ? OR (direction = 'sent' AND body LIKE ?)
        ORDER BY date_sent DESC
    ''', (client_email.lower(), f'%{client_email}%'))
    emails = [dict(row) for row in c.fetchall()]

    # Mark as read
    c.execute("UPDATE gmail_emails SET status = 'read' WHERE sender_email = ? AND status = 'new'",
              (client_email.lower(),))
    conn.commit()
    conn.close()

    return {"client": client, "emails": emails}

def create_magic_link(client_email: str) -> str:
    """Create magic link for client login"""
    conn = get_db()
    c = conn.cursor()

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=7)).isoformat()

    c.execute('''
        INSERT INTO magic_links (client_email, token, expires_at)
        VALUES (?, ?, ?)
    ''', (client_email.lower(), token, expires_at))

    conn.commit()
    conn.close()

    return token

def validate_magic_link(token: str) -> Optional[str]:
    """Validate magic link and return client email"""
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        SELECT client_email, expires_at, used FROM magic_links WHERE token = ?
    ''', (token,))
    row = c.fetchone()

    if not row:
        conn.close()
        return None

    if row['used']:
        conn.close()
        return None

    if datetime.fromisoformat(row['expires_at']) < datetime.now():
        conn.close()
        return None

    # Mark as used
    c.execute("UPDATE magic_links SET used = 1 WHERE token = ?", (token,))
    conn.commit()
    conn.close()

    return row['client_email']

def create_client_session(client_email: str) -> str:
    """Create session for client"""
    conn = get_db()
    c = conn.cursor()

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=30)).isoformat()

    c.execute('''
        INSERT INTO client_sessions (client_email, token, expires_at)
        VALUES (?, ?, ?)
    ''', (client_email, token, expires_at))

    conn.commit()
    conn.close()

    return token

def validate_client_session(token: str) -> Optional[Dict]:
    """Validate client session"""
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        SELECT cs.client_email, c.* FROM client_sessions cs
        LEFT JOIN clients c ON cs.client_email = c.email
        WHERE cs.token = ? AND cs.expires_at > ?
    ''', (token, datetime.now().isoformat()))
    row = c.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None

# ============ AUTH ============
async def get_current_coach(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Token manquant")

    user = validate_session(credentials.credentials)
    if not user or user.get('role') != 'coach':
        raise HTTPException(status_code=401, detail="Acces coach requis")

    return user

async def get_current_client(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Token manquant")

    client = validate_client_session(credentials.credentials)
    if not client:
        raise HTTPException(status_code=401, detail="Session invalide")

    return client

# ============ COACH AUTH ============
class CoachLogin(BaseModel):
    email: EmailStr
    password: str

@app.post("/api/auth/login")
async def coach_login(data: CoachLogin):
    user = authenticate_user(data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    token = create_session(user['id'])
    return {"success": True, "token": token, "user": {"id": user['id'], "email": user['email'], "name": user['name'], "role": user['role']}}

@app.get("/api/auth/me")
async def get_me(user: Dict = Depends(get_current_coach)):
    return {"id": user['id'], "email": user['email'], "name": user['name'], "role": user['role']}

# ============ GMAIL SYNC ============

# Gmail credentials - achzodyt@gmail.com
GMAIL_USER = os.getenv("MAIL_USER", "achzodyt@gmail.com")
GMAIL_PASS = os.getenv("MAIL_PASS", "")

@app.post("/api/coach/gmail/sync")
async def sync_all_gmail(user: Dict = Depends(get_current_coach), days: int = 180):
    """
    FAST Sync - Headers only, body loaded on demand when viewing
    """
    reader = EmailReader()

    try:
        print(f"[SYNC] Starting FAST sync for last {days} days (headers only)...")
        emails = reader.get_all_emails(days=days, unread_only=False)
        print(f"[SYNC] Found {len(emails)} emails total")

        synced = 0
        filtered = 0

        for email_data in emails:
            # Filter spam
            if is_spam_email(email_data):
                filtered += 1
                continue

            # NO body loading during sync - just save headers + IMAP ID
            email_data['direction'] = 'received'

            if save_email(email_data):
                synced += 1

        reader.disconnect()

        # Get updated stats
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) as total FROM gmail_emails')
        total = c.fetchone()['total']
        c.execute('SELECT COUNT(DISTINCT sender_email) as clients FROM gmail_emails WHERE direction = "received"')
        clients_count = c.fetchone()['clients']
        c.execute('SELECT COUNT(*) as unread FROM gmail_emails WHERE status = "new"')
        unread = c.fetchone()['unread']
        conn.close()

        print(f"[SYNC] Done: {synced} synced, {filtered} filtered, {total} total")

        return {
            "success": True,
            "synced": synced,
            "filtered": filtered,
            "total_emails": total,
            "total_clients": clients_count,
            "unread": unread
        }
    except Exception as e:
        print(f"[SYNC] Error: {e}")
        try:
            reader.disconnect()
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Erreur sync: {str(e)}")

@app.post("/api/coach/gmail/clean-spam")
async def clean_spam_emails(user: Dict = Depends(get_current_coach)):
    """Remove spam emails from database"""
    conn = get_db()
    c = conn.cursor()

    # Get all emails
    c.execute('SELECT id, sender_email, subject FROM gmail_emails')
    emails = c.fetchall()

    deleted = 0
    deleted_clients = set()

    for email in emails:
        email_data = {'from_email': email['sender_email'], 'subject': email['subject']}
        if is_spam_email(email_data):
            c.execute('DELETE FROM gmail_emails WHERE id = ?', (email['id'],))
            deleted_clients.add(email['sender_email'])
            deleted += 1

    # Remove clients with no emails left
    for client_email in deleted_clients:
        c.execute('SELECT COUNT(*) as cnt FROM gmail_emails WHERE sender_email = ?', (client_email,))
        if c.fetchone()['cnt'] == 0:
            c.execute('DELETE FROM clients WHERE email = ?', (client_email,))

    conn.commit()
    conn.close()

    return {"success": True, "deleted_emails": deleted, "cleaned_clients": len(deleted_clients)}

@app.get("/api/coach/dashboard")
async def coach_dashboard(user: Dict = Depends(get_current_coach)):
    """Get coach dashboard data"""
    data = get_all_emails_grouped()

    # Stats
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as total FROM gmail_emails WHERE direction = "received"')
    total_received = c.fetchone()['total']
    c.execute('SELECT COUNT(*) as total FROM gmail_emails WHERE status = "new"')
    total_new = c.fetchone()['total']
    conn.close()

    return {
        "clients": data['clients'],
        "recent_emails": data['recent_emails'],
        "stats": {
            "total_clients": len(data['clients']),
            "total_emails": total_received,
            "unread_emails": total_new
        }
    }

@app.get("/api/coach/client/{client_email:path}")
async def get_client_detail(client_email: str, user: Dict = Depends(get_current_coach)):
    """Get client details and all emails"""
    return get_client_emails(client_email)

@app.post("/api/coach/email/{email_id}/load-body")
async def load_email_body(email_id: int, user: Dict = Depends(get_current_coach)):
    """Load email body on demand from Gmail with attachments"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM gmail_emails WHERE id = ?', (email_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Email non trouve")

    email_data = dict(row)

    # If body already loaded, get cached attachments too
    if email_data.get('body_loaded') and email_data.get('body'):
        c.execute('SELECT * FROM email_attachments WHERE email_id = ?', (email_id,))
        attachments = [dict(a) for a in c.fetchall()]
        conn.close()
        return {"success": True, "body": email_data['body'], "attachments": attachments, "cached": True}

    # Load from Gmail using IMAP ID
    imap_id = email_data.get('imap_id')
    if not imap_id:
        conn.close()
        return {"success": False, "body": "(Contenu non disponible - ID manquant)", "error": "no_imap_id"}

    try:
        reader = EmailReader()
        full_content = reader.load_email_content(imap_id)
        reader.disconnect()

        if full_content and full_content.get('loaded'):
            body = full_content.get('body', '')
            raw_attachments = full_content.get('attachments', [])

            # Save attachments to database with base64 data
            saved_attachments = []
            for att in raw_attachments:
                filename = att.get('filename', 'file')
                content_type = att.get('content_type', 'application/octet-stream')
                data = att.get('data', b'')

                # Convert to base64 if bytes
                if isinstance(data, bytes):
                    data_b64 = base64.b64encode(data).decode('utf-8')
                else:
                    data_b64 = data

                is_image = 1 if content_type.startswith('image/') else 0

                c.execute('''
                    INSERT INTO email_attachments (email_id, filename, content_type, data, is_image)
                    VALUES (?, ?, ?, ?, ?)
                ''', (email_id, filename, content_type, data_b64, is_image))

                saved_attachments.append({
                    'id': c.lastrowid,
                    'filename': filename,
                    'content_type': content_type,
                    'is_image': is_image,
                    'data': data_b64 if is_image else None  # Only include data for images
                })

            # Save body to database
            c.execute('''
                UPDATE gmail_emails SET body = ?, body_loaded = 1, has_attachments = ?, attachments_json = ?
                WHERE id = ?
            ''', (body, 1 if saved_attachments else 0,
                  json.dumps([{'filename': a['filename'], 'id': a['id']} for a in saved_attachments]),
                  email_id))
            conn.commit()
            conn.close()

            return {"success": True, "body": body, "attachments": saved_attachments, "cached": False}
        else:
            conn.close()
            return {"success": False, "body": "(Erreur chargement)", "error": "load_failed"}

    except Exception as e:
        conn.close()
        print(f"[LOAD] Error: {e}")
        return {"success": False, "body": f"(Erreur: {str(e)})", "error": str(e)}

@app.post("/api/coach/client/{client_email:path}/magic-link")
async def send_magic_link(client_email: str, user: Dict = Depends(get_current_coach)):
    """Generate magic link for client"""
    token = create_magic_link(client_email)

    # In production, send email. For now, return the link
    base_url = os.getenv("BASE_URL", "https://achzod-client-portal.onrender.com")
    link = f"{base_url}/login?token={token}"

    return {"success": True, "magic_link": link, "token": token}

@app.post("/api/coach/email/{email_id}/analyze")
async def analyze_email_ai(email_id: int, user: Dict = Depends(get_current_coach)):
    """Analyze email with AI"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM gmail_emails WHERE id = ?', (email_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Email non trouve")

    email_data = dict(row)

    # Get history
    c.execute('''
        SELECT * FROM gmail_emails WHERE sender_email = ? ORDER BY date_sent DESC LIMIT 10
    ''', (email_data['sender_email'],))
    history = [{"date": datetime.fromisoformat(r['date_sent']) if r['date_sent'] else datetime.now(),
                "direction": r['direction'], "body": r['body']}
               for r in c.fetchall() if r['id'] != email_id]

    # Get REAL attachments with data from database
    c.execute('SELECT * FROM email_attachments WHERE email_id = ?', (email_id,))
    attachments_rows = c.fetchall()
    conn.close()

    # Build attachments list with actual data for analyzer
    attachments = []
    for att in attachments_rows:
        att_dict = dict(att)
        attachments.append({
            "filename": att_dict.get('filename', 'file'),
            "content_type": att_dict.get('content_type', 'application/octet-stream'),
            "data": att_dict.get('data', ''),  # base64 data
            "is_image": att_dict.get('is_image', 0)
        })

    # Format for analyzer
    email_for_analysis = {
        "date": datetime.fromisoformat(email_data['date_sent']) if email_data.get('date_sent') else datetime.now(),
        "subject": email_data.get('subject', ''),
        "body": email_data.get('body', ''),
        "attachments": attachments
    }

    result = analyze_coaching_bilan(email_for_analysis, history, email_data['sender_email'])

    return {
        "success": result.get('success', False),
        "analysis": result.get('analysis', {}),
        "draft": result.get('analysis', {}).get('draft_email', ''),
        "error": result.get('error', '')
    }

@app.post("/api/coach/email/{email_id}/mark-replied")
async def mark_email_replied(email_id: int, user: Dict = Depends(get_current_coach)):
    """Mark email as replied"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE gmail_emails SET status = 'replied', replied_at = ? WHERE id = ?",
              (datetime.now().isoformat(), email_id))
    conn.commit()
    conn.close()
    return {"success": True}

# ============ KPI / METRICS ENDPOINTS ============
class MetricData(BaseModel):
    poids: Optional[float] = None
    tour_taille: Optional[float] = None
    tour_hanches: Optional[float] = None
    tour_poitrine: Optional[float] = None
    tour_bras: Optional[float] = None
    tour_cuisses: Optional[float] = None
    body_fat: Optional[float] = None
    energie: Optional[int] = None
    sommeil: Optional[int] = None
    stress: Optional[int] = None
    adherence: Optional[int] = None
    notes: Optional[str] = None
    date_recorded: Optional[str] = None

@app.get("/api/coach/client/{client_email:path}/metrics")
async def get_client_metrics(client_email: str, user: Dict = Depends(get_current_coach)):
    """Get all metrics for a client"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT * FROM client_metrics
        WHERE client_email = ?
        ORDER BY date_recorded ASC
    ''', (client_email.lower(),))
    metrics = [dict(row) for row in c.fetchall()]
    conn.close()

    # Calculate evolution if we have data
    evolution = {}
    if len(metrics) >= 2:
        first = metrics[0]
        last = metrics[-1]
        for key in ['poids', 'tour_taille', 'tour_hanches', 'tour_poitrine', 'tour_bras', 'tour_cuisses', 'body_fat']:
            if first.get(key) and last.get(key):
                diff = last[key] - first[key]
                pct = (diff / first[key]) * 100 if first[key] != 0 else 0
                evolution[key] = {'diff': round(diff, 2), 'pct': round(pct, 1)}

    return {"metrics": metrics, "evolution": evolution, "count": len(metrics)}

@app.post("/api/coach/client/{client_email:path}/metrics")
async def add_client_metric(client_email: str, data: MetricData, user: Dict = Depends(get_current_coach)):
    """Add a new metric entry for a client"""
    conn = get_db()
    c = conn.cursor()

    date_recorded = data.date_recorded or datetime.now().isoformat()

    c.execute('''
        INSERT INTO client_metrics
        (client_email, date_recorded, poids, tour_taille, tour_hanches, tour_poitrine,
         tour_bras, tour_cuisses, body_fat, energie, sommeil, stress, adherence, notes, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual')
    ''', (
        client_email.lower(), date_recorded,
        data.poids, data.tour_taille, data.tour_hanches, data.tour_poitrine,
        data.tour_bras, data.tour_cuisses, data.body_fat,
        data.energie, data.sommeil, data.stress, data.adherence, data.notes
    ))
    conn.commit()
    metric_id = c.lastrowid
    conn.close()

    return {"success": True, "id": metric_id}

@app.delete("/api/coach/client/{client_email:path}/metrics/{metric_id}")
async def delete_client_metric(client_email: str, metric_id: int, user: Dict = Depends(get_current_coach)):
    """Delete a metric entry"""
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM client_metrics WHERE id = ? AND client_email = ?', (metric_id, client_email.lower()))
    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/api/attachment/{attachment_id}")
async def get_attachment(attachment_id: int, user: Dict = Depends(get_current_coach)):
    """Get attachment data"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM email_attachments WHERE id = ?', (attachment_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Attachment non trouve")

    att = dict(row)
    return {
        "id": att['id'],
        "filename": att['filename'],
        "content_type": att['content_type'],
        "is_image": att['is_image'],
        "data": att['data']
    }

# ============ CLIENT AUTH (Magic Link) ============
@app.get("/api/client/auth/magic/{token}")
async def verify_magic_link(token: str):
    """Verify magic link and create session"""
    client_email = validate_magic_link(token)

    if not client_email:
        raise HTTPException(status_code=401, detail="Lien invalide ou expire")

    session_token = create_client_session(client_email)

    return {"success": True, "token": session_token, "email": client_email}

@app.get("/api/client/me")
async def get_client_me(client: Dict = Depends(get_current_client)):
    """Get current client info"""
    return {
        "email": client.get('client_email') or client.get('email'),
        "name": client.get('name'),
        "objectif": client.get('objectif'),
        "date_debut": client.get('date_debut')
    }

@app.get("/api/client/dashboard")
async def client_dashboard(client: Dict = Depends(get_current_client)):
    """Get client dashboard"""
    client_email = client.get('client_email') or client.get('email')

    conn = get_db()
    c = conn.cursor()

    # Get all emails (exchanges with coach)
    c.execute('''
        SELECT * FROM gmail_emails
        WHERE sender_email = ? OR (direction = 'sent' AND body LIKE ?)
        ORDER BY date_sent DESC
    ''', (client_email, f'%{client_email}%'))
    emails = [dict(row) for row in c.fetchall()]

    # Get client info
    c.execute('SELECT * FROM clients WHERE email = ?', (client_email,))
    client_info = c.fetchone()

    conn.close()

    return {
        "client": dict(client_info) if client_info else {"email": client_email},
        "emails": emails,
        "stats": {
            "total_exchanges": len(emails),
            "last_contact": emails[0]['date_sent'] if emails else None
        }
    }

# ============ STATIC FILES ============
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_client_portal():
    try:
        with open("static/index.html", "r") as f:
            return f.read()
    except:
        return HTMLResponse("<h1>Client Portal</h1>")

@app.get("/coach", response_class=HTMLResponse)
async def serve_coach_dashboard():
    try:
        with open("static/coach.html", "r") as f:
            return f.read()
    except:
        return HTMLResponse("<h1>Coach Dashboard</h1>")

@app.get("/login", response_class=HTMLResponse)
async def serve_login_page(token: str = None):
    """Magic link landing page"""
    try:
        with open("static/login.html", "r") as f:
            return f.read()
    except:
        return HTMLResponse("<h1>Login</h1>")

# Auto-register coach on startup
@app.on_event("startup")
async def startup():
    coach_email = os.getenv("COACH_EMAIL", "coaching@achzodcoaching.com")
    coach_pass = os.getenv("COACH_PASSWORD", "achzod2024")

    existing = get_user_by_email(coach_email)
    if not existing:
        create_user(coach_email, coach_pass, "Achzod Coach", role="coach")
        print(f"[STARTUP] Coach account created: {coach_email}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
