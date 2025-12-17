"""
Module d'envoi d'emails via Gmail SMTP
"""

import os
import smtplib
import re
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


def html_to_plain_text(html: str) -> str:
    """Convertit HTML en texte brut pour la version alternative"""
    text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    return text.strip()


def send_html_email(
    to_email: str,
    subject: str,
    html_body: str,
    reply_to_message_id: Optional[str] = None,
    original_subject: Optional[str] = None
) -> Dict[str, any]:
    """
    Envoie un email HTML avec le design complet

    Args:
        to_email: Destinataire
        subject: Sujet
        html_body: Corps HTML (le beau design)
        reply_to_message_id: Message-ID pour threading
        original_subject: Sujet original pour le Re:
    """
    try:
        if not MAIL_USER or not MAIL_PASS:
            return {"success": False, "error": "SMTP credentials not configured"}

        # Preparation du sujet
        if not subject and original_subject:
            if not original_subject.lower().startswith("re:"):
                subject = f"Re: {original_subject}"
            else:
                subject = original_subject
        elif not subject:
            subject = "Reponse coaching - Achzod"

        # Creation du message multipart
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{FROM_NAME} <{MAIL_USER}>"
        msg['To'] = to_email

        # Headers pour le threading (reponse dans le meme fil)
        if reply_to_message_id:
            msg['In-Reply-To'] = reply_to_message_id
            msg['References'] = reply_to_message_id

        # Version texte brut (fallback)
        plain_text = html_to_plain_text(html_body)
        msg.attach(MIMEText(plain_text, 'plain', 'utf-8'))

        # Version HTML complete avec wrapper
        full_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:#f4f4f4;">
    <table role="presentation" style="width:100%;border-collapse:collapse;border:0;border-spacing:0;background:#f4f4f4;">
        <tr>
            <td align="center" style="padding:20px 0;">
                <table role="presentation" style="width:600px;border-collapse:collapse;border:0;border-spacing:0;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:30px;">
                            {html_body}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:20px 30px;background:#1a1a2e;color:#ffffff;text-align:center;">
                            <p style="margin:0;font-size:14px;color:#a0a0a0;">
                                Achzod Coaching - Excellence en transformation physique
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
        msg.attach(MIMEText(full_html, 'html', 'utf-8'))

        # Envoi
        print(f"[EMAIL] Sending to {to_email}...")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(msg)

        print(f"[EMAIL] Sent successfully to {to_email}")
        return {
            "success": True,
            "message": f"Email envoye a {to_email}"
        }

    except smtplib.SMTPAuthenticationError as e:
        print(f"[EMAIL] Auth error: {e}")
        return {"success": False, "error": "Erreur authentification SMTP - verifier App Password"}
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
        return {"success": False, "error": str(e)}


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
