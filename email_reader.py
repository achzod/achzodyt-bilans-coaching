"""
Module de lecture des emails Gmail via IMAP
Recupere les bilans de coaching et l'historique des conversations
"""

import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import os
import base64
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dotenv import load_dotenv
import re

load_dotenv()

IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
MAIL_USER = os.getenv("MAIL_USER")
MAIL_PASS = os.getenv("MAIL_PASS")


class EmailReader:
    def __init__(self):
        self.connection = None

    def connect(self) -> bool:
        """Connexion au serveur IMAP Gmail"""
        try:
            self.connection = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            self.connection.login(MAIL_USER, MAIL_PASS)
            return True
        except Exception as e:
            print(f"Erreur connexion IMAP: {e}")
            return False

    def disconnect(self):
        """Deconnexion propre"""
        if self.connection:
            try:
                self.connection.logout()
            except:
                pass

    def mark_as_read(self, email_id: str, folder: str = "INBOX") -> bool:
        """Marque un email comme lu"""
        try:
            if not self.connection:
                if not self.connect():
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
            if not self.connection:
                if not self.connect():
                    return False
            self.connection.select(folder)
            self.connection.store(email_id.encode(), '-FLAGS', '\\Seen')
            return True
        except Exception as e:
            print(f"Erreur mark_as_unread: {e}")
            return False

    def _decode_header_value(self, value: str) -> str:
        """Decode les headers d'email (sujet, from, etc.)"""
        if value is None:
            return ""
        decoded_parts = decode_header(value)
        result = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(encoding or 'utf-8', errors='ignore')
            else:
                result += part
        return result

    def _extract_email_address(self, from_header: str) -> str:
        """Extrait l'adresse email du header From"""
        match = re.search(r'<(.+?)>', from_header)
        if match:
            return match.group(1).lower()
        # Si pas de <>, c'est peut-etre juste l'email
        if '@' in from_header:
            return from_header.strip().lower()
        return from_header

    def _get_email_body(self, msg) -> str:
        """Extrait le corps de l'email (texte)"""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # On veut le texte, pas les pieces jointes
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
                            # Extraction basique du texte depuis HTML
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
        """Extrait les pieces jointes (images, PDF)"""
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", ""))
                content_type = part.get_content_type()

                # Piece jointe explicite ou image inline
                is_attachment = "attachment" in content_disposition
                is_inline_image = content_type.startswith("image/")

                if is_attachment or is_inline_image:
                    filename = part.get_filename()
                    if filename:
                        filename = self._decode_header_value(filename)
                    else:
                        # Generer un nom pour les images inline
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

    def get_recent_emails(self, days: int = 7, folder: str = "INBOX", unread_only: bool = True) -> List[Dict[str, Any]]:
        """
        Recupere les emails recents NON LUS (potentiels bilans)
        """
        if not self.connection:
            if not self.connect():
                return []

        emails = []
        try:
            self.connection.select(folder)

            # Recherche emails recents NON LUS
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            if unread_only:
                status, messages = self.connection.search(None, f'(UNSEEN SINCE "{since_date}")')
            else:
                status, messages = self.connection.search(None, f'(SINCE "{since_date}")')

            if status != "OK":
                return []

            email_ids = messages[0].split()

            # OPTIMISE: headers seulement pour liste rapide
            for email_id in email_ids[-30:]:
                status, msg_data = self.connection.fetch(email_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
                if status != "OK":
                    continue
                header_data = msg_data[0][1]
                msg = email.message_from_bytes(header_data)
                subject = self._decode_header_value(msg["Subject"])
                from_header = self._decode_header_value(msg["From"])
                from_email = self._extract_email_address(from_header)
                date_str = msg["Date"]
                try:
                    date = parsedate_to_datetime(date_str)
                except:
                    date = datetime.now()
                text = subject.lower()
                is_potential_bilan = any(kw in text for kw in ["bilan", "semaine", "update", "suivi", "retour", "feedback", "progression", "photo", "poids"])
                emails.append({
                    "id": email_id.decode(),
                    "from": from_header,
                    "from_email": from_email,
                    "subject": subject,
                    "date": date,
                    "body": "",
                    "attachments": [],
                    "is_potential_bilan": is_potential_bilan,
                    "message_id": msg["Message-ID"],
                    "loaded": False
                })

        except Exception as e:
            print(f"Erreur lecture emails: {e}")

        # Tri par date decroissante
        emails.sort(key=lambda x: x["date"], reverse=True)
        return emails


    def load_email_content(self, email_id: str, folder: str = "INBOX") -> Dict[str, Any]:
        """Charge le contenu complet d'un email (lazy loading)"""
        if not self.connection:
            if not self.connect():
                return {}
        try:
            self.connection.select(folder)
            status, msg_data = self.connection.fetch(email_id.encode(), "(BODY.PEEK[])")
            if status != "OK":
                return {}
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            return {
                "body": self._get_email_body(msg),
                "attachments": self._get_attachments(msg),
                "loaded": True
            }
        except Exception as e:
            print(f"Erreur chargement contenu: {e}")
            return {}

    def _is_potential_bilan(self, subject: str, body: str, attachments: List) -> bool:
        """
        Detecte si un email est potentiellement un bilan de coaching
        """
        text = (subject + " " + body).lower()

        # Mots-cles positifs (bilan probable)
        positive_keywords = [
            "bilan", "semaine", "update", "suivi", "retour", "feedback",
            "progression", "evolution", "photo", "poids", "mesure",
            "entrainement", "training", "seance", "programme",
            "resultats", "objectif", "coach", "coaching"
        ]

        # Mots-cles negatifs (probablement pas un bilan)
        negative_keywords = [
            "newsletter", "promo", "soldes", "unsubscribe", "desinscription",
            "publicite", "pub", "offre", "reduction"
        ]

        # Score
        score = 0
        for kw in positive_keywords:
            if kw in text:
                score += 1
        for kw in negative_keywords:
            if kw in text:
                score -= 2

        # Bonus si pieces jointes images
        has_images = any(att["content_type"].startswith("image/") for att in attachments)
        if has_images:
            score += 2

        return score >= 2


    def get_unanswered_emails(self, days: int = 14, folder: str = "INBOX", progress_callback=None) -> List[Dict[str, Any]]:
        """
        Recupere les emails auxquels on n'a PAS encore repondu
        (verifie si on a envoye un email au meme expediteur apres reception)
        """
        if not self.connection:
            if not self.connect():
                return []

        emails = []
        answered_senders = set()

        try:
            # D'abord, recuperer les emails envoyes pour savoir a qui on a repondu
            sent_folders = ["[Gmail]/Sent Mail", "[Gmail]/Messages envoy&AOk-s", "Sent", "[Gmail]/Sent"]
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            
            for sent_folder in sent_folders:
                try:
                    status, _ = self.connection.select(f'"{sent_folder}"')
                    if status == "OK":
                        status, messages = self.connection.search(None, f'(SINCE "{since_date}")')
                        if status == "OK":
                            for email_id in messages[0].split():
                                status, msg_data = self.connection.fetch(email_id, "(BODY.PEEK[HEADER.FIELDS (TO)])")
                                if status == "OK":
                                    header = msg_data[0][1]
                                    msg = email.message_from_bytes(header)
                                    to = self._decode_header_value(msg["To"] or "")
                                    to_email = self._extract_email_address(to)
                                    if to_email:
                                        answered_senders.add(to_email.lower())
                        break
                except:
                    continue

            # Maintenant recuperer les emails recus et filtrer ceux sans reponse
            self.connection.select(folder)
            status, messages = self.connection.search(None, f'(SINCE "{since_date}")')

            if status != "OK":
                return []

            email_ids = messages[0].split()

            for email_id in email_ids[-50:]:
                status, msg_data = self.connection.fetch(email_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
                if status != "OK":
                    continue
                header_data = msg_data[0][1]
                msg = email.message_from_bytes(header_data)
                from_header = self._decode_header_value(msg["From"])
                from_email = self._extract_email_address(from_header)
                
                # Skip si on a deja repondu a cet expediteur
                if from_email.lower() in answered_senders:
                    continue
                    
                subject = self._decode_header_value(msg["Subject"])
                date_str = msg["Date"]
                try:
                    date = parsedate_to_datetime(date_str)
                except:
                    date = datetime.now()
                
                text = subject.lower()
                is_potential_bilan = any(kw in text for kw in ["bilan", "semaine", "update", "suivi", "retour", "feedback", "progression", "photo", "poids"])
                
                emails.append({
                    "id": email_id.decode(),
                    "from": from_header,
                    "from_email": from_email,
                    "subject": subject,
                    "date": date,
                    "body": "",
                    "attachments": [],
                    "is_potential_bilan": is_potential_bilan,
                    "message_id": msg["Message-ID"],
                    "loaded": False
                })

        except Exception as e:
            print(f"Erreur get_unanswered: {e}")

        emails.sort(key=lambda x: x["date"], reverse=True)
        return emails

    def get_conversation_history(self, email_address: str, days: int = 90) -> List[Dict[str, Any]]:
        """
        Recupere tout l'historique de conversation avec un client
        (emails envoyes ET recus)
        """
        if not self.connection:
            if not self.connect():
                return []

        all_emails = []

        try:
            # Emails recus de ce client (INBOX)
            self.connection.select("INBOX")
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            status, messages = self.connection.search(None, f'(FROM "{email_address}" SINCE "{since_date}")')

            if status == "OK":
                for email_id in messages[0].split():
                    email_data = self._fetch_email(email_id)
                    if email_data:
                        email_data["direction"] = "received"
                        all_emails.append(email_data)

            # Emails envoyes a ce client (Sent)
            sent_folders = ["[Gmail]/Sent Mail", "[Gmail]/Messages envoy&AOk-s", "Sent", "[Gmail]/Sent"]
            for folder in sent_folders:
                try:
                    status, _ = self.connection.select(f'"{folder}"')
                    if status == "OK":
                        status, messages = self.connection.search(None, f'(TO "{email_address}" SINCE "{since_date}")')
                        if status == "OK":
                            for email_id in messages[0].split():
                                email_data = self._fetch_email(email_id)
                                if email_data:
                                    email_data["direction"] = "sent"
                                    all_emails.append(email_data)
                        break
                except:
                    continue

        except Exception as e:
            print(f"Erreur historique conversation: {e}")

        # Tri chronologique
        all_emails.sort(key=lambda x: x["date"])
        return all_emails

    def _fetch_email(self, email_id) -> Optional[Dict[str, Any]]:
        """Fetch un email par son ID"""
        try:
            status, msg_data = self.connection.fetch(email_id, "(RFC822)")
            if status != "OK":
                return None

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = self._decode_header_value(msg["Subject"])
            from_header = self._decode_header_value(msg["From"])
            from_email = self._extract_email_address(from_header)
            to_header = self._decode_header_value(msg["To"] or "")
            date_str = msg["Date"]

            try:
                date = parsedate_to_datetime(date_str)
            except:
                date = datetime.now()

            body = self._get_email_body(msg)
            attachments = self._get_attachments(msg)

            return {
                "id": email_id.decode() if isinstance(email_id, bytes) else str(email_id),
                "from": from_header,
                "from_email": from_email,
                "to": to_header,
                "subject": subject,
                "date": date,
                "body": body,
                "attachments": attachments,
                "message_id": msg["Message-ID"]
            }
        except Exception as e:
            print(f"Erreur fetch email: {e}")
            return None


# Test rapide
if __name__ == "__main__":
    reader = EmailReader()
    if reader.connect():
        print("Connexion OK!")
        emails = reader.get_recent_emails(days=7)
        print(f"Emails recents: {len(emails)}")

        bilans = [e for e in emails if e["is_potential_bilan"]]
        print(f"Bilans potentiels: {len(bilans)}")

        for b in bilans[:3]:
            print(f"\n- {b['subject']} ({b['from_email']})")
            print(f"  Pieces jointes: {len(b['attachments'])}")

        reader.disconnect()
    else:
        print("Erreur connexion")
