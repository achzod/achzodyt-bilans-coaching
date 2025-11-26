"""
Module d'envoi d'emails via Gmail SMTP
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from typing import Optional, List, Dict
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
MAIL_USER = os.getenv("MAIL_USER")
MAIL_PASS = os.getenv("MAIL_PASS")
FROM_NAME = "Achzod Coaching"


def send_email(
    to_email: str,
    subject: str,
    body: str,
    reply_to_message_id: Optional[str] = None,
    original_subject: Optional[str] = None
) -> Dict[str, any]:
    """
    Envoie un email de reponse

    Args:
        to_email: Destinataire
        subject: Sujet (si None, utilise Re: + original_subject)
        body: Corps du message (texte brut)
        reply_to_message_id: Message-ID pour threading
        original_subject: Sujet original pour le Re:
    """
    try:
        # Preparation du sujet
        if not subject and original_subject:
            if not original_subject.lower().startswith("re:"):
                subject = f"Re: {original_subject}"
            else:
                subject = original_subject
        elif not subject:
            subject = "Reponse coaching"

        # Creation du message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{FROM_NAME} <{MAIL_USER}>"
        msg['To'] = to_email

        # Headers pour le threading (reponse dans le meme fil)
        if reply_to_message_id:
            msg['In-Reply-To'] = reply_to_message_id
            msg['References'] = reply_to_message_id

        # Corps en texte brut
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # Version HTML basique
        html_body = body.replace('\n', '<br>')
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            {html_body}
            <br><br>
            <p style="color: #666; font-size: 12px;">
                --<br>
                Achzod Coaching<br>
                Excellence en coaching personnalise
            </p>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        # Envoi
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(msg)

        return {
            "success": True,
            "message": f"Email envoye a {to_email}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def preview_email(
    to_email: str,
    subject: str,
    body: str
) -> str:
    """
    Genere un apercu HTML de l'email
    """
    html_body = body.replace('\n', '<br>')

    preview = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
            .email-container {{ background: white; padding: 20px; border-radius: 8px; max-width: 600px; margin: auto; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .email-header {{ border-bottom: 1px solid #eee; padding-bottom: 15px; margin-bottom: 15px; }}
            .email-field {{ margin: 5px 0; }}
            .email-label {{ font-weight: bold; color: #666; }}
            .email-body {{ line-height: 1.8; }}
            .email-signature {{ color: #666; font-size: 12px; margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="email-header">
                <div class="email-field"><span class="email-label">De:</span> Achzod Coaching &lt;{MAIL_USER}&gt;</div>
                <div class="email-field"><span class="email-label">A:</span> {to_email}</div>
                <div class="email-field"><span class="email-label">Sujet:</span> {subject}</div>
            </div>
            <div class="email-body">
                {html_body}
            </div>
            <div class="email-signature">
                --<br>
                Achzod Coaching<br>
                Excellence en coaching personnalise
            </div>
        </div>
    </body>
    </html>
    """
    return preview


# Test
if __name__ == "__main__":
    # Test preview
    preview = preview_email(
        to_email="test@example.com",
        subject="Re: Bilan semaine 3",
        body="""Salut Marc,

Merci pour ton bilan!

Super progression sur le poids (-2kg en une semaine, c'est top).

Pour les genoux, on va remplacer les squats par des leg press et du goblet squat.

On continue comme ca!

Achzod"""
    )
    print("Preview generee")
