"""
Gestion des clients - commandes et dates de suivi
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

CLIENTS_FILE = "clients_data.json"

def load_clients() -> Dict[str, Any]:
    """Charge les donnees clients"""
    if os.path.exists(CLIENTS_FILE):
        try:
            with open(CLIENTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_clients(data: Dict[str, Any]):
    """Sauvegarde les donnees clients"""
    with open(CLIENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_client(email: str) -> Optional[Dict[str, Any]]:
    """Recupere les infos d'un client"""
    clients = load_clients()
    return clients.get(email.lower())

def save_client(email: str, commande: str, date_debut: str, duree_semaines: int):
    """Sauvegarde un client"""
    clients = load_clients()
    clients[email.lower()] = {
        "email": email.lower(),
        "commande": commande,
        "date_debut": date_debut,
        "duree_semaines": duree_semaines,
        "updated": datetime.now().isoformat()
    }
    save_clients(clients)

def get_jours_restants(client_data: Dict[str, Any]) -> int:
    """Calcule les jours restants de suivi"""
    if not client_data:
        return -1
    try:
        date_debut = datetime.strptime(client_data["date_debut"], "%Y-%m-%d")
        duree = client_data.get("duree_semaines", 12)
        date_fin = date_debut + timedelta(weeks=duree)
        restant = (date_fin - datetime.now()).days
        return max(0, restant)
    except:
        return -1

def delete_client(email: str):
    """Supprime un client"""
    clients = load_clients()
    if email.lower() in clients:
        del clients[email.lower()]
        save_clients(clients)
