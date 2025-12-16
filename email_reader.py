"""
Module de lecture des emails Gmail via IMAP
Version simple et robuste
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
    """Cree une nouvelle connexion IMAP"""
    try:
        import socket
        socket.setdefaulttimeout(30)  # Timeout 30 secondes
        conn = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        conn.login(MAIL_USER, MAIL_PASS)
        return conn
    except Exception as e:
        print(f"[IMAP] Erreur connexion: {e}")
        return None


class EmailReader:
    def __init__(self):
        self.connection = None

    def connect(self, force: bool = False) -> bool:
        """Connexion au serveur IMAP"""
        if force and self.connection:
            try:
                self.connection.logout()
            except:
                pass
            self.connection = None

        self.connection = create_connection()
        return self.connection is not None

    def disconnect(self):
        """Deconnexion propre"""
        if self.connection:
            try:
                self.connection.logout()
            except:
                pass
            self.connection = None

    def _decode_header_value(self, value: str) -> str:
        """Decode les headers d'email"""
        if value is None:
            return ""
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
        if not from_header:
            return ""
        match = re.search(r'<(.+?)>', from_header)
        if match:
            return match.group(1).lower()
        if '@' in from_header:
            return from_header.strip().lower()
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

                    if "attachment" in content_disposition:
                        continue

                    try:
                        payload = part.get_payload(decode=True)
                        if not payload:
                            continue

                        charset = part.get_content_charset() or 'utf-8'
                        text = payload.decode(charset, errors='ignore')

                        if content_type == "text/plain" and not text_body:
                            text_body = text
                        elif content_type == "text/html" and not html_body:
                            html_body = text
                    except:
                        continue
            else:
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or 'utf-8'
                        content_type = msg.get_content_type()
                        text = payload.decode(charset, errors='ignore')

                        if content_type == "text/html":
                            html_body = text
                        else:
                            text_body = text
                except:
                    pass

            # Priorite au texte plain
            if text_body and len(text_body.strip()) > 10:
                return text_body.strip()

            # Convertir HTML en texte
            if html_body:
                text = html_body
                text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'&nbsp;', ' ', text)
                text = re.sub(r'&amp;', '&', text)
                text = re.sub(r'&lt;', '<', text)
                text = re.sub(r'&gt;', '>', text)
                text = re.sub(r'&quot;', '"', text)
                text = re.sub(r'&#39;', "'", text)
                text = re.sub(r'[ \t]+', ' ', text)
                text = re.sub(r'\n\s*\n', '\n\n', text)
                return text.strip()

            return text_body.strip() if text_body else ""
        except Exception as e:
            print(f"[BODY] Erreur: {e}")
            return ""

    def _get_attachments(self, msg) -> List[Dict[str, Any]]:
        """Extrait les pieces jointes"""
        attachments = []
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    content_disposition = str(part.get("Content-Disposition", ""))
                    content_type = part.get_content_type()

                    is_attachment = "attachment" in content_disposition
                    is_inline_image = content_type.startswith("image/")

                    if is_attachment or is_inline_image:
                        filename = part.get_filename()
                        if filename:
                            filename = self._decode_header_value(filename)
                        else:
                            ext = content_type.split("/")[-1]
                            filename = f"image_{len(attachments)}.{ext}"

                        try:
                            data = part.get_payload(decode=True)
                            if data:
                                attachments.append({
                                    "filename": filename,
                                    "content_type": content_type,
                                    "data": base64.b64encode(data).decode('utf-8'),
                                    "size": len(data)
                                })
                        except:
                            pass
        except:
            pass
        return attachments

    def mark_as_read(self, email_id: str, folder: str = "INBOX") -> bool:
        """Marque un email comme lu"""
        conn = create_connection()
        if not conn:
            return False
        try:
            conn.select(folder)
            conn.store(email_id.encode(), '+FLAGS', '\\Seen')
            conn.logout()
            return True
        except Exception as e:
            print(f"Erreur mark_as_read: {e}")
            try:
                conn.logout()
            except:
                pass
            return False

    def get_unanswered_emails(self, days: int = 7, folder: str = "INBOX", progress_callback=None) -> List[Dict[str, Any]]:
        """
        Recupere les emails sans reponse - utilise le flag IMAP UNANSWERED
        """
        print(f"[EMAILS] Chargement emails sans reponse ({days} jours)...")

        conn = create_connection()
        if not conn:
            print("[EMAILS] Echec connexion")
            return []

        emails = []
        try:
            conn.select(folder)
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")

            # Utiliser UNANSWERED - rapide!
            status, data = conn.search(None, f'(UNANSWERED SINCE "{since_date}")')

            if status != "OK" or not data[0]:
                print("[EMAILS] Aucun email trouve")
                conn.logout()
                return []

            email_ids = data[0].split()
            print(f"[EMAILS] {len(email_ids)} emails trouves, chargement...")

            # Limiter a 200 max
            if len(email_ids) > 200:
                email_ids = email_ids[-200:]

            # Charger par lots (Batch Fetching)
            # On reduit a 10 pour economiser la RAM sur Render (512MB limit)
            batch_size = 10
            total_emails = len(email_ids)
            
            print(f"[EMAILS] Debut chargement batch (Total: {total_emails}, Batch size: {batch_size})")
            
            for i in range(0, total_emails, batch_size):
                batch_ids = email_ids[i:i + batch_size]
                
                # Nettoyage des IDs
                clean_batch_ids = []
                for bid in batch_ids:
                    if isinstance(bid, bytes):
                        clean_batch_ids.append(bid.decode())
                    else:
                        clean_batch_ids.append(str(bid))
                
                # Commande IMAP standard: IDs separes par virgule
                batch_ids_str = ",".join(clean_batch_ids)
                
                print(f"[EMAILS] Batch {i+1}-{min(i+batch_size, total_emails)}...")
                
                try:
                    # FETCH headers essentiels uniquement
                    status, data = conn.fetch(batch_ids_str, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
                    
                    if status != "OK":
                        print(f"[EMAILS] Batch Failed Status: {status}")
                        raise Exception("Batch status not OK")
                        
                    # Traitement reponse
                    count_in_batch = 0
                    for response_part in data:
                        if isinstance(response_part, tuple):
                            try:
                                msg_data = response_part[1]
                                msg = email.message_from_bytes(msg_data)
                                
                                # Recuperation ID un peu tricky en batch
                                # Format: b'123 (BODY...)'
                                raw_response = response_part[0]
                                current_id = ""
                                if isinstance(raw_response, bytes):
                                    current_id = raw_response.split()[0].decode()
                                
                                # Si current_id vide, on prend celui de la liste batch (approximatif mais ca depanne)
                                if not current_id and count_in_batch < len(clean_batch_ids):
                                    # Attention: l'ordre n'est pas garanti a 100% en IMAP mais souvent respecte
                                    pass 
                                
                                subject = self._decode_header_value(msg["Subject"])
                                from_header = self._decode_header_value(msg["From"])
                                from_email = self._extract_email_address(from_header)
                                
                                try:
                                    date = parsedate_to_datetime(msg["Date"])
                                except:
                                    date = datetime.now()
                                    
                                is_bilan = any(kw in subject.lower() for kw in ["bilan", "semaine", "update", "suivi", "retour", "feedback", "progression", "photo", "poids"])
                                
                                emails.append({
                                    "id": current_id,
                                    "from": from_header,
                                    "from_email": from_email,
                                    "subject": subject,
                                    "date": date,
                                    "body": "",
                                    "attachments": [],
                                    "is_potential_bilan": is_bilan,
                                    "message_id": msg.get("Message-ID", ""),
                                    "loaded": False
                                })
                                count_in_batch += 1
                            except Exception as e:
                                print(f"Error parsing in batch: {e}")
                                continue
                                
                except Exception as e:
                    print(f"[EMAILS] CRASH BATCH: {e}")
                    # Fallback: chargement un par un pour ce lot en cas d'erreur
                    for eid in clean_batch_ids:
                        try:
                            status, msg_data = conn.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
                            if status != "OK" or not msg_data or not msg_data[0]:
                                continue
                            
                            header_data = msg_data[0][1]
                            msg = email.message_from_bytes(header_data)
                            
                            subject = self._decode_header_value(msg["Subject"])
                            from_header = self._decode_header_value(msg["From"])
                            from_email = self._extract_email_address(from_header)
                            
                            try:
                                date = parsedate_to_datetime(msg["Date"])
                            except:
                                date = datetime.now()
                            
                            is_bilan = any(kw in subject.lower() for kw in ["bilan", "semaine", "update", "suivi", "retour", "feedback", "progression", "photo", "poids"])
                            
                            emails.append({
                                "id": eid,
                                "from": from_header,
                                "from_email": from_email,
                                "subject": subject,
                                "date": date,
                                "body": "",
                                "attachments": [],
                                "is_potential_bilan": is_bilan,
                                "message_id": msg.get("Message-ID", ""),
                                "loaded": False
                            })
                        except Exception as inner_e:
                            continue

            conn.logout()

        except Exception as e:
            print(f"[EMAILS] Erreur: {e}")
            try:
                conn.logout()
            except:
                pass

        emails.sort(key=lambda x: x["date"], reverse=True)
        print(f"[EMAILS] {len(emails)} emails prets")
        return emails

    def load_email_content(self, email_id: str, folder: str = "INBOX") -> Dict[str, Any]:
        """
        Charge le contenu complet d'un email
        """
        print(f"[LOAD] Chargement email {email_id}...")

        for attempt in range(3):
            conn = create_connection()
            if not conn:
                print(f"[LOAD] Echec connexion (tentative {attempt + 1})")
                time.sleep(0.5)
                continue

            try:
                conn.select(folder)
                eid = email_id.encode() if isinstance(email_id, str) else email_id
                status, msg_data = conn.fetch(eid, "(BODY.PEEK[])")

                if status != "OK" or not msg_data or not msg_data[0]:
                    print(f"[LOAD] Echec fetch (tentative {attempt + 1})")
                    conn.logout()
                    time.sleep(0.5)
                    continue

                raw_email = msg_data[0][1]
                if not raw_email:
                    print(f"[LOAD] Email vide")
                    conn.logout()
                    continue

                msg = email.message_from_bytes(raw_email)
                body = self._get_email_body(msg)
                attachments = self._get_attachments(msg)

                conn.logout()

                print(f"[LOAD] OK: {len(body)} chars, {len(attachments)} PJ")
                return {
                    "body": body,
                    "attachments": attachments,
                    "loaded": True
                }

            except Exception as e:
                print(f"[LOAD] Erreur (tentative {attempt + 1}): {e}")
                try:
                    conn.logout()
                except:
                    pass
                time.sleep(0.5)

        return {"error": "Echec apres 3 tentatives", "loaded": False, "body": "", "attachments": []}

    def _batch_fetch_full_emails(self, conn, email_ids: List[str], max_fetch: int = 500) -> List[Dict[str, Any]]:
        """
        Helper pour fetcher une liste d'emails COMPLETS en batch
        Optimise pour l'historique
        """
        fetched_emails = []
        if not email_ids:
            return []
            
        # Limiter le nombre d'emails a fetcher pour eviter timeouts, mais large (500)
        if len(email_ids) > max_fetch:
            print(f"[HISTORY] Limite a {max_fetch} emails les plus recents (sur {len(email_ids)})")
            # On prend les derniers (les plus recents generalement si tries)
            email_ids = email_ids[-max_fetch:]
            
        batch_size = 10 # Petit batch car contenu complet (RFC822)
        
        for i in range(0, len(email_ids), batch_size):
            batch_ids = email_ids[i:i + batch_size]
            clean_batch_ids = []
            for bid in batch_ids:
                if isinstance(bid, bytes):
                    clean_batch_ids.append(bid.decode())
                else:
                    clean_batch_ids.append(str(bid))
            
            batch_str = ",".join(clean_batch_ids)
            print(f"[HISTORY] Fetching batch {i+1}...")
            
            try:
                status, data = conn.fetch(batch_str, "(RFC822)")
                if status != "OK":
                    continue
                    
                for response_part in data:
                    if isinstance(response_part, tuple):
                        try:
                            # response_part[0] contient l'ID
                            raw_response = response_part[0]
                            current_id = ""
                            if isinstance(raw_response, bytes):
                                current_id = raw_response.split()[0].decode()
                            
                            raw_email = response_part[1]
                            msg = email.message_from_bytes(raw_email)
                            
                            subject = self._decode_header_value(msg["Subject"])
                            from_header = self._decode_header_value(msg["From"])
                            to_header = self._decode_header_value(msg["To"] or "")
                            from_email = self._extract_email_address(from_header)
                            
                            try:
                                date = parsedate_to_datetime(msg["Date"])
                            except:
                                date = datetime.now()
                                
                            body = self._get_email_body(msg)
                            attachments = self._get_attachments(msg)
                            
                            fetched_emails.append({
                                "id": current_id,
                                "from": from_header,
                                "from_email": from_email,
                                "to": to_header,
                                "subject": subject,
                                "date": date,
                                "body": body,
                                "attachments": attachments,
                                "message_id": msg.get("Message-ID", "")
                            })
                        except:
                            continue
            except Exception as e:
                print(f"[HISTORY] Error batch: {e}")
                # Fallback unitaire
                for eid in clean_batch_ids:
                    # Implementer un fetch unitaire simple si besoin
                    pass
                    
        return fetched_emails

    def get_conversation_history(self, email_address: str, days: int = 90) -> List[Dict[str, Any]]:
        """
        Recupere l'historique de conversation avec un client
        Optimise avec batch fetching
        """
        print(f"[HISTORY] Chargement historique avec {email_address}...")

        conn = create_connection()
        if not conn:
                return []

        all_emails = []
        since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")

        try:
            # Emails recus
            conn.select("INBOX")
            status, messages = conn.search(None, f'(FROM "{email_address}" SINCE "{since_date}")')
            if status == "OK" and messages[0]:
                email_ids = messages[0].split()
                print(f"[HISTORY] {len(email_ids)} emails recus trouves")
                
                # Utiliser le nouveau batch fetch
                received_emails = self._batch_fetch_full_emails(conn, email_ids)
                for email_data in received_emails:
                    email_data["direction"] = "received"
                    all_emails.append(email_data)

            # Emails envoyes
            for sent_folder in ["[Gmail]/Sent Mail", "[Gmail]/Messages envoy&AOk-s", "Sent"]:
                try:
                    status, _ = conn.select(f'"{sent_folder}"')
                    if status == "OK":
                        status, messages = conn.search(None, f'(TO "{email_address}" SINCE "{since_date}")')
                        if status == "OK" and messages[0]:
                            email_ids = messages[0].split()
                            print(f"[HISTORY] {len(email_ids)} emails envoyes trouves dans {sent_folder}")
                            
                            sent_emails = self._batch_fetch_full_emails(conn, email_ids)
                            for email_data in sent_emails:
                                email_data["direction"] = "sent"
                                all_emails.append(email_data)
                        break
                except:
                    continue

            conn.logout()

        except Exception as e:
            print(f"[HISTORY] Erreur: {e}")
            try:
                conn.logout()
            except:
                pass

        all_emails.sort(key=lambda x: x["date"])
        print(f"[HISTORY] Total {len(all_emails)} emails charges")
        return all_emails

    def _fetch_full_email(self, conn, email_id) -> Optional[Dict[str, Any]]:
        """Deprecated: utiliser _batch_fetch_full_emails"""
        return None

    # Alias pour compatibilite
    def get_recent_emails(self, days: int = 7, folder: str = "INBOX", unread_only: bool = True, unanswered_only: bool = False) -> List[Dict[str, Any]]:
        if unanswered_only:
            return self.get_unanswered_emails(days=days, folder=folder)
        return self.get_all_emails(days=days, folder=folder, unread_only=unread_only)

    def ensure_connected(self) -> bool:
        return True  # Chaque operation cree sa propre connexion

    def mark_as_unread(self, email_id: str, folder: str = "INBOX") -> bool:
        conn = create_connection()
        if not conn:
            return False
        try:
            conn.select(folder)
            conn.store(email_id.encode(), '-FLAGS', '\\Seen')
            conn.logout()
            return True
        except:
            try:
                conn.logout()
            except:
                pass
            return False
