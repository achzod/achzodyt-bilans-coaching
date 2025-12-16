"""
Gestion de la base de donnees locale (SQLite) sur disque persistant
Stocke les clients, emails et analyses pour un acces instantane
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

# Chemin de la DB: sur disque persistant /data si dispo, sinon local
DB_PATH = "/data/coaching.db" if os.path.exists("/data") else "coaching.db"
ATTACHMENTS_DIR = "/data/attachments" if os.path.exists("/data") else "attachments"

class DatabaseManager:
    def __init__(self):
        self._init_db()
        self._init_dirs()

    def _init_db(self):
        """Cree les tables si elles n'existent pas"""
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

    def _init_dirs(self):
        """Cree le dossier pieces jointes"""
        os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

    def get_client(self, email: str) -> Optional[Dict]:
        """Recupere infos client"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM clients WHERE email = ?", (email,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

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
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        try:
            # 1. Sauvegarder l'email
            # Convertir date en string ISO si besoin
            date_val = email_data['date']
            if isinstance(date_val, datetime):
                date_val = date_val.isoformat()
                
            c.execute("""INSERT OR IGNORE INTO emails 
                         (message_id, client_email, subject, date, body, direction, is_bilan, analysis_json)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                      (email_data['message_id'], 
                       email_data.get('from_email') if email_data.get('direction') == 'received' else email_data.get('to_email'), # A ajuster selon logique
                       email_data['subject'], 
                       date_val, 
                       email_data.get('body', ''),
                       email_data.get('direction', 'received'),
                       email_data.get('is_potential_bilan', False),
                       json.dumps(email_data.get('analysis', {})) if email_data.get('analysis') else None
                      ))
            
            # 2. Sauvegarder les pieces jointes
            for att in email_data.get('attachments', []):
                # Sauvegarde fichier sur disque
                safe_filename = "".join([c for c in att['filename'] if c.isalpha() or c.isdigit() or c in '._- ']).strip()
                file_path = os.path.join(ATTACHMENTS_DIR, f"{email_data['message_id']}_{safe_filename}")
                
                # Ecriture fichier si base64 data dispo
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
        
        c.execute("""SELECT * FROM emails 
                     WHERE client_email = ? 
                     ORDER BY date ASC""", (client_email,))
        rows = c.fetchall()
        
        history = []
        for row in rows:
            email_dict = dict(row)
            # Convertir date str -> datetime
            try:
                email_dict['date'] = datetime.fromisoformat(email_dict['date'])
            except:
                pass
                
            # Charger attachments
            c.execute("SELECT * FROM attachments WHERE message_id = ?", (email_dict['message_id'],))
            att_rows = c.fetchall()
            email_dict['attachments'] = [dict(att) for att in att_rows]
            
            history.append(email_dict)
            
        conn.close()
        return history

    def email_exists(self, message_id: str) -> bool:
        """Verifie si un email est deja en base"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM emails WHERE message_id = ?", (message_id,))
        exists = c.fetchone() is not None
        conn.close()
        return exists

