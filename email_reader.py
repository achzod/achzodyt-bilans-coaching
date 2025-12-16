"""
Module de lecture des emails Gmail via IMAP
Version robuste avec gestion connexion amelioree
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

# Timeout IMAP plus court pour detecter les deconnexions plus vite
imaplib.IMAP4.timeout = 30


class EmailReader:
    def __init__(self):
        self.connection = None
        self._last_noop = None

    def _fresh_connect(self) -> bool:
        """Cree une NOUVELLE connexion (ferme l'ancienne si existe)"""
        # Fermer proprement l'ancienne connexion
        if self.connection:
            try:
                self.connection.logout()
            except:
                pass
            self.connection = None

        # Nouvelle connexion avec retry
        for attempt in range(3):
            try:
                print(f"[IMAP] Connexion... (tentative {attempt + 1})")
                conn = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
                conn.login(MAIL_USER, MAIL_PASS)
                self.connection = conn
                self._last_noop = time.time()
                print(f"[IMAP] Connecte!")
                return True
            except Exception as e:
                print(f"[IMAP] Erreur connexion: {e}")
                if attempt < 2:
                    time.sleep(2)
        return False

    def connect(self, force: bool = False) -> bool:
        """Connexion (ou reconnexion si force=True)"""
        if force or not self.connection:
            return self._fresh_connect()

        # Test si connexion encore vivante
        try:
            status, _ = self.connection.noop()
            if status == "OK":
                self._last_noop = time.time()
                return True
        except:
            pass

        # Connexion morte, reconnecter
        return self._fresh_connect()

    def ensure_connected(self) -> bool:
        """S'assure qu'on a une connexion valide"""
        if not self.connection:
            return self._fresh_connect()

        # NOOP toutes les 30 secondes max pour garder la connexion vivante
        now = time.time()
        if self._last_noop and (now - self._last_noop) > 30:
            try:
                status, _ = self.connection.noop()
                if status == "OK":
                    self._last_noop = now
                    return True
            except:
                pass
            # Connexion morte
            return self._fresh_connect()

        return True

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
                    result += part
            return result
        except:
            return str(value)

    def _extract_email_address(self, from_header: str) -> str:
        """Extrait l'adresse email du header From"""
        match = re.search(r'<(.+?)>', from_header)
        if match:
            return match.group(1).lower()
        if '@' in from_header:
            return from_header.strip().lower()
        return from_header

    def _get_email_body(self, msg) -> str:
        """Extrait le corps de l'email"""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" not in content_disposition:
                    if content_type == "text/plain":
                        try:
                            charset = part.get_content_charset() or 'utf-8'
                            body = part.get_payload(decode=True).decode(charset, errors='ignore')
                            break
                        except:
                            pass
                    elif content_type == "text/html" and not body:
                        try:
                            charset = part.get_content_charset() or 'utf-8'
                            html = part.get_payload(decode=True).decode(charset, errors='ignore')
                            body = re.sub(r'<[^>]+>', ' ', html)
                            body = re.sub(r'\s+', ' ', body).strip()
                        except:
                            pass
        else:
            try:
                charset = msg.get_content_charset() or 'utf-8'
                body = msg.get_payload(decode=True).decode(charset, errors='ignore')
            except:
                pass
        return body.strip()

    def _get_attachments(self, msg) -> List[Dict[str, Any]]:
        """Extrait les pieces jointes"""
        attachments = []
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
        return attachments

    def mark_as_read(self, email_id: str, folder: str = "INBOX") -> bool:
        """Marque un email comme lu"""
        try:
            if not self.ensure_connected():
                return False
            self.connection.select(folder)
            self.connection.store(email_id.encode(), '+FLAGS', '\\Seen')
            return True
        except Exception as e:
            print(f"Erreur mark_as_read: {e}")
            return False

    def mark_as_unread(self, email_id: str, folder: str = "INBOX") -> bool:
        """Marque un email comme non lu"""
        try:
            if not self.ensure_connected():
                return False
            self.connection.select(folder)
            self.connection.store(email_id.encode(), '-FLAGS', '\\Seen')
            return True
        except Exception as e:
            print(f"Erreur mark_as_unread: {e}")
            return False

    def get_all_emails(self, days: int = 7, folder: str = "INBOX", unread_only: bool = False, max_emails: int = 500) -> List[Dict[str, Any]]:
        """
        Recupere TOUS les emails (sans filtre "sans reponse")
        Mode simple et robuste
        """
        print(f"[GET_ALL] Chargement emails ({days} jours, unread_only={unread_only})...")

        if not self._fresh_connect():  # Toujours nouvelle connexion
            print("[GET_ALL] Echec connexion")
            return []

        emails = []
        try:
            self.connection.select(folder)
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")

            # Construire la requete
            if unread_only:
                search_query = f'(UNSEEN SINCE "{since_date}")'
            else:
                search_query = f'(SINCE "{since_date}")'

            print(f"[GET_ALL] Recherche: {search_query}")
            status, messages = self.connection.search(None, search_query)

            if status != "OK" or not messages[0]:
                print("[GET_ALL] Aucun email trouve")
                return []

            email_ids = messages[0].split()
            total = len(email_ids)
            print(f"[GET_ALL] {total} emails trouves")

            # Prendre les plus recents (limiter si trop)
            if total > max_emails:
                email_ids = email_ids[-max_emails:]
                print(f"[GET_ALL] Limite a {max_emails} emails")

            # Charger les headers de chaque email
            for idx, eid in enumerate(email_ids):
                if idx > 0 and idx % 50 == 0:
                    print(f"[GET_ALL] Progress: {idx}/{len(email_ids)}")
                    # Keepalive
                    try:
                        self.connection.noop()
                    except:
                        if not self._fresh_connect():
                            break
                        self.connection.select(folder)

                try:
                    status, msg_data = self.connection.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
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

                    # Detection bilan
                    text = subject.lower()
                    is_bilan = any(kw in text for kw in ["bilan", "semaine", "update", "suivi", "retour", "feedback", "progression", "photo", "poids"])

                    emails.append({
                        "id": eid.decode() if isinstance(eid, bytes) else str(eid),
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
                except Exception as e:
                    print(f"[GET_ALL] Erreur email {eid}: {e}")
                    continue

        except Exception as e:
            print(f"[GET_ALL] Erreur: {e}")
            import traceback
            traceback.print_exc()

        emails.sort(key=lambda x: x["date"], reverse=True)
        print(f"[GET_ALL] {len(emails)} emails charges")
        return emails

    def get_unanswered_emails(self, days: int = 7, folder: str = "INBOX", progress_callback=None) -> List[Dict[str, Any]]:
        """
        Recupere les emails sans reponse (version simplifiee)
        Utilise le flag IMAP UNANSWERED + verification manuelle
        """
        print(f"[UNANSWERED] Chargement emails sans reponse ({days} jours)...")

        if not self._fresh_connect():
            print("[UNANSWERED] Echec connexion")
            return []

        emails = []
        sent_to = {}  # email -> dernier timestamp d'envoi

        try:
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")

            # 1. Charger les emails ENVOYES pour savoir a qui on a repondu
            print("[UNANSWERED] Chargement emails envoyes...")
            for sent_folder in ["[Gmail]/Sent Mail", "[Gmail]/Messages envoy&AOk-s", "Sent"]:
                try:
                    status, _ = self.connection.select(f'"{sent_folder}"')
                    if status == "OK":
                        status, msgs = self.connection.search(None, f'(SINCE "{since_date}")')
                        if status == "OK" and msgs[0]:
                            sent_ids = msgs[0].split()
                            print(f"[UNANSWERED] {len(sent_ids)} emails envoyes")

                            for eid in sent_ids:
                                try:
                                    status, data = self.connection.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (TO DATE)])")
                                    if status == "OK" and data and data[0]:
                                        m = email.message_from_bytes(data[0][1])
                                        to_email = self._extract_email_address(self._decode_header_value(m["To"] or ""))
                                        if to_email:
                                            try:
                                                ts = parsedate_to_datetime(m["Date"]).timestamp()
                                            except:
                                                ts = time.time()
                                            # Garder le plus recent
                                            if to_email not in sent_to or ts > sent_to[to_email]:
                                                sent_to[to_email] = ts
                                except:
                                    continue
                        break
                except:
                    continue

            print(f"[UNANSWERED] Reponses envoyees a {len(sent_to)} contacts")

            # 2. Charger les emails RECUS
            if not self.ensure_connected():
                return []

            self.connection.select(folder)
            status, msgs = self.connection.search(None, f'(SINCE "{since_date}")')

            if status != "OK" or not msgs[0]:
                print("[UNANSWERED] Aucun email recu")
                return []

            recv_ids = msgs[0].split()
            print(f"[UNANSWERED] {len(recv_ids)} emails recus a verifier")

            for idx, eid in enumerate(recv_ids):
                if idx > 0 and idx % 50 == 0:
                    print(f"[UNANSWERED] Progress: {idx}/{len(recv_ids)}")
                    try:
                        self.connection.noop()
                    except:
                        if not self._fresh_connect():
                            break
                        self.connection.select(folder)

                try:
                    status, data = self.connection.fetch(eid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
                    if status != "OK" or not data or not data[0]:
                        continue

                    m = email.message_from_bytes(data[0][1])
                    from_header = self._decode_header_value(m["From"])
                    from_email = self._extract_email_address(from_header)
                    subject = self._decode_header_value(m["Subject"] or "")

                    try:
                        recv_date = parsedate_to_datetime(m["Date"])
                        recv_ts = recv_date.timestamp()
                    except:
                        recv_date = datetime.now()
                        recv_ts = time.time()

                    # Verifier si on a repondu APRES reception
                    if from_email in sent_to and sent_to[from_email] > recv_ts:
                        continue  # On a repondu, skip

                    is_bilan = any(kw in subject.lower() for kw in ["bilan", "semaine", "update", "suivi", "retour", "feedback", "progression", "photo", "poids"])

                    emails.append({
                        "id": eid.decode() if isinstance(eid, bytes) else str(eid),
                        "from": from_header,
                        "from_email": from_email,
                        "subject": subject,
                        "date": recv_date,
                        "body": "",
                        "attachments": [],
                        "is_potential_bilan": is_bilan,
                        "message_id": m.get("Message-ID", ""),
                        "loaded": False
                    })
                except Exception as e:
                    continue

        except Exception as e:
            print(f"[UNANSWERED] Erreur: {e}")
            import traceback
            traceback.print_exc()

        emails.sort(key=lambda x: x["date"], reverse=True)
        print(f"[UNANSWERED] {len(emails)} emails sans reponse")
        return emails

    def load_email_content(self, email_id: str, folder: str = "INBOX") -> Dict[str, Any]:
        """
        Charge le contenu complet d'un email
        TOUJOURS nouvelle connexion pour eviter les problemes
        """
        print(f"[LOAD] Chargement contenu email {email_id}...")

        for attempt in range(3):
            try:
                # Nouvelle connexion a chaque tentative
                if not self._fresh_connect():
                    print(f"[LOAD] Echec connexion (tentative {attempt + 1})")
                    time.sleep(1)
                    continue

                status, _ = self.connection.select(folder)
                if status != "OK":
                    print(f"[LOAD] Echec select folder")
                    continue

                eid = email_id.encode() if isinstance(email_id, str) else email_id
                status, msg_data = self.connection.fetch(eid, "(BODY.PEEK[])")

                if status != "OK" or not msg_data or not msg_data[0]:
                    print(f"[LOAD] Echec fetch (tentative {attempt + 1})")
                    time.sleep(1)
                    continue

                raw_email = msg_data[0][1]
                if not raw_email:
                    print(f"[LOAD] Email vide")
                    continue

                msg = email.message_from_bytes(raw_email)
                body = self._get_email_body(msg)
                attachments = self._get_attachments(msg)

                print(f"[LOAD] OK: {len(body)} chars, {len(attachments)} pieces jointes")
                return {
                    "body": body,
                    "attachments": attachments,
                    "loaded": True
                }

            except Exception as e:
                print(f"[LOAD] Erreur (tentative {attempt + 1}): {e}")
                time.sleep(1)

        return {"error": "Echec apres 3 tentatives", "loaded": False, "body": "", "attachments": []}

    def get_conversation_history(self, email_address: str, days: int = 90) -> List[Dict[str, Any]]:
        """Recupere l'historique de conversation avec un client"""
        print(f"[HISTORY] Chargement historique avec {email_address}...")

        if not self._fresh_connect():
            return []

        all_emails = []
        since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")

        try:
            # Emails recus
            self.connection.select("INBOX")
            status, messages = self.connection.search(None, f'(FROM "{email_address}" SINCE "{since_date}")')
            if status == "OK" and messages[0]:
                for eid in messages[0].split():
                    email_data = self._fetch_full_email(eid)
                    if email_data:
                        email_data["direction"] = "received"
                        all_emails.append(email_data)

            # Emails envoyes
            for sent_folder in ["[Gmail]/Sent Mail", "[Gmail]/Messages envoy&AOk-s", "Sent"]:
                try:
                    status, _ = self.connection.select(f'"{sent_folder}"')
                    if status == "OK":
                        status, messages = self.connection.search(None, f'(TO "{email_address}" SINCE "{since_date}")')
                        if status == "OK" and messages[0]:
                            for eid in messages[0].split():
                                email_data = self._fetch_full_email(eid)
                                if email_data:
                                    email_data["direction"] = "sent"
                                    all_emails.append(email_data)
                        break
                except:
                    continue

        except Exception as e:
            print(f"[HISTORY] Erreur: {e}")

        all_emails.sort(key=lambda x: x["date"])
        print(f"[HISTORY] {len(all_emails)} emails trouves")
        return all_emails

    def _fetch_full_email(self, email_id) -> Optional[Dict[str, Any]]:
        """Fetch un email complet"""
        try:
            status, msg_data = self.connection.fetch(email_id, "(RFC822)")
            if status != "OK":
                return None

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            return {
                "id": email_id.decode() if isinstance(email_id, bytes) else str(email_id),
                "from": self._decode_header_value(msg["From"]),
                "from_email": self._extract_email_address(self._decode_header_value(msg["From"])),
                "to": self._decode_header_value(msg["To"] or ""),
                "subject": self._decode_header_value(msg["Subject"]),
                "date": parsedate_to_datetime(msg["Date"]) if msg["Date"] else datetime.now(),
                "body": self._get_email_body(msg),
                "attachments": self._get_attachments(msg),
                "message_id": msg.get("Message-ID", "")
            }
        except Exception as e:
            print(f"Erreur fetch: {e}")
            return None

    # Aliases pour compatibilite
    def get_recent_emails(self, days: int = 7, folder: str = "INBOX", unread_only: bool = True, unanswered_only: bool = False) -> List[Dict[str, Any]]:
        """Alias vers get_all_emails pour compatibilite"""
        return self.get_all_emails(days=days, folder=folder, unread_only=unread_only)


# Test
if __name__ == "__main__":
    reader = EmailReader()
    if reader.connect():
        print("Test get_all_emails...")
        emails = reader.get_all_emails(days=7, unread_only=False)
        print(f"Total: {len(emails)} emails")

        print("\nTest get_unanswered_emails...")
        unanswered = reader.get_unanswered_emails(days=7)
        print(f"Sans reponse: {len(unanswered)} emails")

        reader.disconnect()
