"""
FastAPI Backend - API pour la plateforme coaching
Gere l'auth, messages, bilans, dashboard
"""

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
import os
import json
import base64
import shutil
import sqlite3

from models import (
    init_platform_db, create_user, authenticate_user, get_user_by_id, get_user_by_email,
    get_all_clients, update_user, create_session, validate_session, delete_session,
    send_message, get_user_messages, get_conversation, mark_messages_read, get_unread_count,
    submit_bilan, get_user_bilans, get_bilan_by_id, update_bilan_analysis,
    log_daily_metric, get_daily_metrics, get_notifications, mark_notification_read,
    get_client_stats, get_coach_dashboard, create_notification, DB_PATH
)

# Import AI analyzer
from analyzer import analyze_coaching_bilan

# Init DB
init_platform_db()

# FastAPI App
app = FastAPI(
    title="Achzod Coaching Platform API",
    description="API pour la gestion des clients coaching",
    version="1.0.0"
)

# CORS - Allow all for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer(auto_error=False)

# Upload dir
UPLOAD_DIR = "/data/uploads" if os.path.exists("/data") else "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ============ PYDANTIC MODELS ============

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    objectif: Optional[str] = ""
    duree_semaines: Optional[int] = 12


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    objectif: Optional[str] = None


class MessageCreate(BaseModel):
    to_user_id: int
    subject: Optional[str] = ""
    body: str
    is_bilan: Optional[bool] = False


class BilanSubmit(BaseModel):
    poids: Optional[float] = None
    tour_taille: Optional[float] = None
    tour_hanches: Optional[float] = None
    tour_bras: Optional[float] = None
    tour_cuisses: Optional[float] = None
    energie: Optional[int] = None
    sommeil_qualite: Optional[int] = None
    sommeil_heures: Optional[float] = None
    stress: Optional[int] = None
    motivation: Optional[int] = None
    faim: Optional[int] = None
    digestion: Optional[int] = None
    libido: Optional[int] = None
    seances_prevues: Optional[int] = None
    seances_faites: Optional[int] = None
    intensite_moyenne: Optional[int] = None
    exercice_favori: Optional[str] = None
    difficultes_training: Optional[str] = None
    respect_calories: Optional[int] = None
    respect_macros: Optional[int] = None
    nombre_ecarts: Optional[int] = None
    hydratation_litres: Optional[float] = None
    supplements_pris: Optional[str] = None
    victoires: Optional[str] = None
    difficultes: Optional[str] = None
    questions: Optional[str] = None
    notes_libres: Optional[str] = None


class DailyMetric(BaseModel):
    date: str
    poids: Optional[float] = None
    calories: Optional[int] = None
    proteines: Optional[int] = None
    pas: Optional[int] = None
    sommeil_heures: Optional[float] = None
    energie: Optional[int] = None
    notes: Optional[str] = None


class AIGenerateRequest(BaseModel):
    bilan_id: int
    instructions: Optional[str] = ""


# ============ AUTH DEPENDENCY ============

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Valide le token et retourne l'utilisateur"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Token manquant")

    user = validate_session(credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Token invalide ou expire")

    return user


async def get_current_coach(user: Dict = Depends(get_current_user)) -> Dict:
    """Verifie que l'utilisateur est coach"""
    if user.get('role') != 'coach':
        raise HTTPException(status_code=403, detail="Acces reserve au coach")
    return user


# ============ AUTH ROUTES ============

@app.post("/api/auth/register")
async def register(data: UserRegister):
    """Inscription d'un nouveau client"""
    user_id = create_user(
        email=data.email,
        password=data.password,
        name=data.name,
        role="client",
        objectif=data.objectif,
        duree_semaines=data.duree_semaines
    )

    if not user_id:
        raise HTTPException(status_code=400, detail="Email deja utilise")

    token = create_session(user_id)

    # Notifier le coach
    coach = get_user_by_email(os.getenv("COACH_EMAIL", "coach@achzod.com"))
    if coach:
        create_notification(
            coach['id'], 'new_client',
            f"Nouveau client: {data.name}",
            f"{data.email} vient de s'inscrire",
            f"/coach/clients/{user_id}"
        )

    return {"success": True, "token": token, "user_id": user_id}


@app.post("/api/auth/login")
async def login(data: UserLogin):
    """Connexion"""
    user = authenticate_user(data.email, data.password)

    if not user:
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    token = create_session(user['id'])

    return {
        "success": True,
        "token": token,
        "user": {
            "id": user['id'],
            "email": user['email'],
            "name": user['name'],
            "role": user['role']
        }
    }


@app.post("/api/auth/logout")
async def logout(user: Dict = Depends(get_current_user),
                credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Deconnexion"""
    delete_session(credentials.credentials)
    return {"success": True}


@app.get("/api/auth/me")
async def get_me(user: Dict = Depends(get_current_user)):
    """Infos utilisateur connecte"""
    return {
        "id": user['id'],
        "email": user['email'],
        "name": user['name'],
        "role": user['role'],
        "objectif": user.get('objectif'),
        "date_debut": user.get('date_debut'),
        "duree_semaines": user.get('duree_semaines')
    }


# ============ CLIENT ROUTES ============

@app.get("/api/client/dashboard")
async def client_dashboard(user: Dict = Depends(get_current_user)):
    """Dashboard client"""
    stats = get_client_stats(user['id'])
    return stats


@app.get("/api/client/bilans")
async def client_bilans(user: Dict = Depends(get_current_user), limit: int = 20):
    """Liste des bilans du client"""
    bilans = get_user_bilans(user['id'], limit)
    return {"bilans": bilans}


@app.post("/api/client/bilans")
async def submit_client_bilan(data: BilanSubmit, user: Dict = Depends(get_current_user)):
    """Soumet un nouveau bilan"""
    bilan_id = submit_bilan(user['id'], data.dict())

    # Notifier le coach
    coach = get_user_by_email(os.getenv("COACH_EMAIL", "coach@achzod.com"))
    if coach:
        create_notification(
            coach['id'], 'new_bilan',
            f"Nouveau bilan de {user['name']}",
            f"Semaine soumise - A analyser",
            f"/coach/bilans/{bilan_id}"
        )

    return {"success": True, "bilan_id": bilan_id}


@app.get("/api/client/bilans/{bilan_id}")
async def get_client_bilan(bilan_id: int, user: Dict = Depends(get_current_user)):
    """Detail d'un bilan"""
    bilan = get_bilan_by_id(bilan_id)

    if not bilan:
        raise HTTPException(status_code=404, detail="Bilan non trouve")

    if bilan['user_id'] != user['id'] and user['role'] != 'coach':
        raise HTTPException(status_code=403, detail="Acces non autorise")

    return bilan


@app.post("/api/client/daily")
async def log_daily(data: DailyMetric, user: Dict = Depends(get_current_user)):
    """Log metrique quotidienne"""
    success = log_daily_metric(user['id'], data.date, **data.dict(exclude={'date'}))
    return {"success": success}


@app.get("/api/client/daily")
async def get_daily(user: Dict = Depends(get_current_user), days: int = 30):
    """Metriques quotidiennes"""
    metrics = get_daily_metrics(user['id'], days)
    return {"metrics": metrics}


# ============ MESSAGES ROUTES ============

@app.get("/api/messages")
async def get_messages(user: Dict = Depends(get_current_user), limit: int = 50):
    """Liste des messages"""
    messages = get_user_messages(user['id'], limit)
    unread = get_unread_count(user['id'])
    return {"messages": messages, "unread_count": unread}


@app.get("/api/messages/conversation/{other_user_id}")
async def get_conv(other_user_id: int, user: Dict = Depends(get_current_user)):
    """Conversation avec un utilisateur"""
    messages = get_conversation(user['id'], other_user_id)
    # Marquer comme lus
    mark_messages_read(user['id'], other_user_id)
    return {"messages": messages}


@app.post("/api/messages")
async def create_message(data: MessageCreate, user: Dict = Depends(get_current_user)):
    """Envoyer un message"""
    msg_id = send_message(
        from_user_id=user['id'],
        to_user_id=data.to_user_id,
        subject=data.subject,
        body=data.body,
        is_bilan=data.is_bilan
    )
    return {"success": True, "message_id": msg_id}


@app.post("/api/messages/to-coach")
async def send_to_coach(body: str = Form(...), subject: str = Form(""),
                       user: Dict = Depends(get_current_user)):
    """Raccourci pour envoyer au coach"""
    # Try specific coach email first
    coach = get_user_by_email(os.getenv("COACH_EMAIL", "coach@achzod.com"))

    if not coach:
        # Try to find any coach in the system
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE role = 'coach' LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row:
            coach = dict(row)

    if not coach:
        # Creer le coach si n'existe pas
        coach_id = create_user(
            email=os.getenv("COACH_EMAIL", "coach@achzod.com"),
            password=os.getenv("COACH_PASSWORD", "admin123"),
            name="Coach Achzod",
            role="coach"
        )
        coach = get_user_by_id(coach_id)

    msg_id = send_message(
        from_user_id=user['id'],
        to_user_id=coach['id'],
        subject=subject or f"Message de {user['name']}",
        body=body
    )
    return {"success": True, "message_id": msg_id}


# ============ NOTIFICATIONS ROUTES ============

@app.get("/api/notifications")
async def get_notifs(user: Dict = Depends(get_current_user), unread_only: bool = False):
    """Liste des notifications"""
    notifs = get_notifications(user['id'], unread_only)
    return {"notifications": notifs}


@app.post("/api/notifications/{notif_id}/read")
async def mark_read(notif_id: int, user: Dict = Depends(get_current_user)):
    """Marquer notification comme lue"""
    success = mark_notification_read(notif_id)
    return {"success": success}


# ============ COACH ROUTES ============

@app.get("/api/coach/dashboard")
async def coach_dashboard_api(user: Dict = Depends(get_current_coach)):
    """Dashboard coach"""
    return get_coach_dashboard()


@app.get("/api/coach/clients")
async def list_clients(user: Dict = Depends(get_current_coach)):
    """Liste tous les clients"""
    clients = get_all_clients()
    return {"clients": clients}


@app.get("/api/coach/clients/{client_id}")
async def get_client_detail(client_id: int, user: Dict = Depends(get_current_coach)):
    """Detail d'un client"""
    client = get_user_by_id(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client non trouve")

    stats = get_client_stats(client_id)
    bilans = get_user_bilans(client_id, 20)

    return {
        "client": client,
        "stats": stats,
        "bilans": bilans
    }


@app.get("/api/coach/bilans/{bilan_id}")
async def coach_get_bilan(bilan_id: int, user: Dict = Depends(get_current_coach)):
    """Detail bilan pour le coach"""
    bilan = get_bilan_by_id(bilan_id)
    if not bilan:
        raise HTTPException(status_code=404, detail="Bilan non trouve")

    client = get_user_by_id(bilan['user_id'])

    return {
        "bilan": bilan,
        "client": client
    }


@app.post("/api/coach/bilans/{bilan_id}/analyze")
async def analyze_bilan(bilan_id: int, user: Dict = Depends(get_current_coach)):
    """Analyse IA d'un bilan"""
    bilan = get_bilan_by_id(bilan_id)
    if not bilan:
        raise HTTPException(status_code=404, detail="Bilan non trouve")

    client = get_user_by_id(bilan['user_id'])
    history = get_user_bilans(bilan['user_id'], 10)

    # Formater pour l'analyseur
    email_data = {
        "date": datetime.fromisoformat(bilan['date_submitted']) if bilan.get('date_submitted') else datetime.now(),
        "subject": f"Bilan Semaine {bilan.get('week_number', '?')}",
        "body": _format_bilan_as_text(bilan),
        "attachments": []
    }

    # Historique formatte
    history_formatted = []
    for b in history[:-1]:  # Exclure le bilan actuel
        history_formatted.append({
            "date": datetime.fromisoformat(b['date_submitted']) if b.get('date_submitted') else datetime.now(),
            "direction": "received",
            "body": _format_bilan_as_text(b)
        })

    result = analyze_coaching_bilan(email_data, history_formatted, client.get('name', ''))

    if result.get('success'):
        analysis_json = json.dumps(result.get('analysis', {}), ensure_ascii=False)
        draft = result.get('analysis', {}).get('draft_email', '')
        update_bilan_analysis(bilan_id, analysis_json, draft)

        return {
            "success": True,
            "analysis": result.get('analysis'),
            "draft": draft
        }
    else:
        raise HTTPException(status_code=500, detail=result.get('error', 'Erreur analyse'))


@app.post("/api/coach/bilans/{bilan_id}/respond")
async def respond_bilan(bilan_id: int, response: str = Form(...),
                       user: Dict = Depends(get_current_coach)):
    """Repond a un bilan"""
    bilan = get_bilan_by_id(bilan_id)
    if not bilan:
        raise HTTPException(status_code=404, detail="Bilan non trouve")

    # Sauvegarder la reponse
    update_bilan_analysis(bilan_id, bilan.get('analysis_json', '{}'), response)

    # Envoyer comme message
    send_message(
        from_user_id=user['id'],
        to_user_id=bilan['user_id'],
        subject=f"Retour Bilan Semaine {bilan.get('week_number', '?')}",
        body=response
    )

    return {"success": True}


def _format_bilan_as_text(bilan: Dict) -> str:
    """Formatte un bilan en texte pour l'analyse"""
    parts = []

    if bilan.get('poids'):
        parts.append(f"Poids: {bilan['poids']} kg")
    if bilan.get('energie'):
        parts.append(f"Energie: {bilan['energie']}/10")
    if bilan.get('sommeil_qualite'):
        parts.append(f"Sommeil: {bilan['sommeil_qualite']}/10 ({bilan.get('sommeil_heures', '?')}h)")
    if bilan.get('motivation'):
        parts.append(f"Motivation: {bilan['motivation']}/10")
    if bilan.get('stress'):
        parts.append(f"Stress: {bilan['stress']}/10")

    if bilan.get('seances_faites') is not None:
        parts.append(f"Seances: {bilan['seances_faites']}/{bilan.get('seances_prevues', '?')}")
    if bilan.get('respect_calories'):
        parts.append(f"Respect calories: {bilan['respect_calories']}/10")

    if bilan.get('victoires'):
        parts.append(f"\nVictoires: {bilan['victoires']}")
    if bilan.get('difficultes'):
        parts.append(f"Difficultes: {bilan['difficultes']}")
    if bilan.get('questions'):
        parts.append(f"Questions: {bilan['questions']}")
    if bilan.get('notes_libres'):
        parts.append(f"Notes: {bilan['notes_libres']}")

    return "\n".join(parts)


# ============ FILE UPLOAD ============

@app.post("/api/upload/photo")
async def upload_photo(file: UploadFile = File(...), user: Dict = Depends(get_current_user)):
    """Upload photo de progression"""
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Fichier doit etre une image")

    # Creer dossier user
    user_dir = os.path.join(UPLOAD_DIR, str(user['id']))
    os.makedirs(user_dir, exist_ok=True)

    # Nom unique
    ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
    filepath = os.path.join(user_dir, filename)

    # Sauvegarder
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {"success": True, "filepath": filepath, "filename": filename}


# ============ HEALTH CHECK ============

@app.get("/api/health")
async def health():
    """Health check"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ============ STATIC FILES (Client Portal) ============

# Serve static files from 'static' folder
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


# Serve index.html for client portal
@app.get("/", response_class=HTMLResponse)
async def serve_client_portal():
    """Serve client portal"""
    try:
        with open("static/index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Client Portal - Coming Soon</h1>", status_code=200)


# Serve coach dashboard
@app.get("/coach", response_class=HTMLResponse)
async def serve_coach_dashboard():
    """Serve coach dashboard"""
    try:
        with open("static/coach.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Coach Dashboard - Coming Soon</h1>", status_code=200)


# Run with: uvicorn api:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
