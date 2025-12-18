"""
Module de lecture des emails Gmail via IMAP
Version robuste avec support des UIDs (IDs persistants)
"""

import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import os
import base64
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
import re

load_dotenv()

IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
MAIL_USER = os.getenv("MAIL_USER")
MAIL_PASS = os.getenv("MAIL_PASS")


def create_connection():
    """Cree une nouvelle connexion IMAP avec debugging intense"""
    # imaplib.Debug = 4 # Trop verbeux pour prod, mais utile ici - Activé via env si besoin
    try:
        import socket
        timeout = 30
        socket.setdefaulttimeout(timeout)
        
        print(f"[IMAP] Tentative de connexion vers {IMAP_SERVER}:{IMAP_PORT} (timeout={timeout})...")
        
        # 1. Connexion SSL
        start_time = time.time()
        conn = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        print(f"[IMAP] SSL Connect OK en {time.time() - start_time:.2f}s")
        
        # 2. Login
        print(f"[IMAP] Tentative login pour {MAIL_USER}...")
        start_time = time.time()
        conn.login(MAIL_USER, MAIL_PASS)
        print(f"[IMAP] Login OK en {time.time() - start_time:.2f}s")
        
        return conn
    except Exception as e:
        print(f"[IMAP] ECHEC CRITIQUE: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


class EmailReader:
    def __init__(self):
        self.connection = None

    def _decode_header_value(self, value: str) -> str:
        """Decode les headers d'email"""
        if value is None: return ""
        try:
            decoded_parts = decode_header(value)
            result = ""
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    result += part.decode(encoding or 'utf-8', errors='ignore')
                else:
                    result += str(part)
            return result
        except:
            return str(value) if value else ""

    def _extract_email_address(self, from_header: str) -> str:
        """Extrait l'adresse email du header From"""
        if not from_header: return ""
        match = re.search(r'<(.+?)>', from_header)
        if match: return match.group(1).lower()
        if '@' in from_header: return from_header.strip().lower()
        return from_header

    def _get_email_body(self, msg) -> str:
        """Extrait le corps de l'email"""
        text_body = ""
        html_body = ""
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    if "attachment" in content_disposition: continue
                    try:
                        payload = part.get_payload(decode=True)
                        if not payload: continue
                        charset = part.get_content_charset() or 'utf-8'
                        text = payload.decode(charset, errors='ignore')
                        if content_type == "text/plain": text_body = text
                        elif content_type == "text/html": html_body = text
                    except: continue
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or 'utf-8'
                    text = payload.decode(charset, errors='ignore')
                    if msg.get_content_type() == "text/html": html_body = text
                    else: text_body = text

            if text_body and len(text_body.strip()) > 10: return text_body.strip()
            if html_body:
                text = html_body
                text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'&nbsp;', ' ', text)
                return text.strip()
            return text_body.strip() if text_body else ""
        except: return ""

    def _get_attachments(self, msg) -> List[Dict[str, Any]]:
        """Extrait les pieces jointes"""
        attachments = []
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    content_disposition = str(part.get("Content-Disposition", ""))
                    if "attachment" in content_disposition or part.get_content_type().startswith("image/"):
                        filename = part.get_filename()
                        if filename: filename = self._decode_header_value(filename)
                        else: filename = f"attachment_{len(attachments)}"
                        try:
                            data = part.get_payload(decode=True)
                            if data:
                                attachments.append({
                                    "filename": filename,
                                    "content_type": part.get_content_type(),
                                    "data": base64.b64encode(data).decode('utf-8')
                                })
                        except: pass
        except: pass
        return attachments

    def get_unanswered_emails(self, days: int = 7, folder: str = "INBOX", max_emails: int = 50) -> List[Dict[str, Any]]:
        """Recupere les emails sans reponse via UID"""
        conn = create_connection()
        if not conn: return []
        emails = []
        try:
            conn.select(folder)
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            status, data = conn.uid('search', None, f'(UNANSWERED SINCE "{since_date}")')
            if status != "OK" or not data[0]:
                conn.logout()
                return []
            
            uids = data[0].split()
            if len(uids) > max_emails: uids = uids[-max_emails:]
            
            # Fetch headers in batch
            if uids:
                uids_str = ",".join([u.decode() for u in uids])
                status, fetch_data = conn.uid('fetch', uids_str, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
                if status == "OK":
                    for part in fetch_data:
                        if isinstance(part, tuple):
                            msg = email.message_from_bytes(part[1])
                            # Extraire UID de response_part[0]
                            resp_str = part[0].decode('utf-8', errors='ignore')
                            uid_match = re.search(r'UID\s+(\d+)', resp_str, re.IGNORECASE)
                            uid = uid_match.group(1) if uid_match else ""
                            
                            subject = self._decode_header_value(msg["Subject"])
                            from_email = self._extract_email_address(self._decode_header_value(msg["From"]))
                            try: date = parsedate_to_datetime(msg["Date"])
                            except: date = datetime.now()
                            
                            emails.append({
                                "id": uid, # Persistent UID
                                "message_id": msg.get("Message-ID", f"no-id-{uid}"),
                                "from_email": from_email,
                                "subject": subject,
                                "date": date,
                                "direction": "received",
                                "body": "",
                                "attachments": []
                            })
            conn.logout()
        except Exception as e:
            print(f"Error sync: {e}")
            try: conn.logout()
            except: pass
        return sorted(emails, key=lambda x: x["date"], reverse=True)

    def load_email_content(self, uid: str, folder: str = "INBOX") -> Dict[str, Any]:
        """Charge le contenu complet via UID"""
        conn = create_connection()
        if not conn: return {"loaded": False, "error": "Connexion impossible"}
        try:
            conn.select(folder)
            status, data = conn.uid('fetch', uid.encode(), "(BODY.PEEK[])")
            if status == "OK" and data and data[0]:
                msg = email.message_from_bytes(data[0][1])
                body = self._get_email_body(msg)
                attachments = self._get_attachments(msg)
                conn.logout()
                return {"loaded": True, "body": body, "attachments": attachments}
            conn.logout()
        except Exception as e:
            print(f"Error load: {e}")
            try: conn.logout()
            except: pass
        return {"loaded": False, "error": "Fetch fail"}

    def get_recent_emails(self, days: int = 7, folder: str = "INBOX", unread_only: bool = True, max_emails: int = 50) -> List[Dict[str, Any]]:
        # Version simplifiee UID
        return self.get_unanswered_emails(days=days, folder=folder, max_emails=max_emails)
