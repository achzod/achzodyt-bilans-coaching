"""
Module d'analyse IA des bilans de coaching avec Claude
"""

import os
import base64
import json
from typing import List, Dict, Any, Optional
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def detect_image_type(b64_data: str) -> Optional[str]:
    """Detecte le vrai type d'image depuis les magic bytes"""
    try:
        raw = base64.b64decode(b64_data[:32])
        # JPEG: FF D8 FF
        if raw[0] == 0xFF and raw[1] == 0xD8 and raw[2] == 0xFF:
            return 'image/jpeg'
        # PNG: 89 50 4E 47
        if raw[0] == 0x89 and raw[1] == 0x50 and raw[2] == 0x4E and raw[3] == 0x47:
            return 'image/png'
        # GIF: 47 49 46 38
        if raw[0] == 0x47 and raw[1] == 0x49 and raw[2] == 0x46 and raw[3] == 0x38:
            return 'image/gif'
        # WEBP: RIFF...WEBP
        if raw[0] == 0x52 and raw[1] == 0x49 and raw[2] == 0x46 and raw[3] == 0x46:
            if len(raw) > 11 and raw[8] == 0x57 and raw[9] == 0x45:
                return 'image/webp'
    except:
        pass
    return None


def analyze_coaching_bilan(
    current_email: Dict[str, Any],
    conversation_history: List[Dict[str, Any]],
    client_name: str = ""
) -> Dict[str, Any]:
    """Analyse complete d'un bilan de coaching"""

    history_text = _build_history_context(conversation_history)
    photos = [att for att in current_email.get("attachments", []) if att["content_type"].startswith("image/")]
    pdfs = [att for att in current_email.get("attachments", []) if "pdf" in att["content_type"].lower()]

    content = []

    prompt = f"""Tu es Achzod, coach expert en transformation physique.

Tu recois un bilan de coaching. Fais une analyse COMPLETE.

## HISTORIQUE
{history_text}

## BILAN ACTUEL
Date: {current_email['date'].strftime('%d/%m/%Y %H:%M') if current_email.get('date') else 'N/A'}
Sujet: {current_email.get('subject', 'Sans sujet')}

Message:
\"\"\"
{current_email.get('body', '')}
\"\"\"

Pieces jointes: {len(photos)} photo(s), {len(pdfs)} PDF(s)

---

## TA MISSION

1. ANALYSE DES PHOTOS: composition corporelle, masse grasse %, points forts, zones a travailler
2. METRIQUES: poids, energie, sommeil, performances
3. REPONSES AUX QUESTIONS du client
4. KPIs (note sur 10): adherence training, nutrition, sommeil, energie, progression
5. POINTS POSITIFS
6. POINTS A AMELIORER avec solutions
7. EMAIL DE REPONSE complet et personnalise

Style: Direct, expert, bienveillant, tutoiement, emojis ok.

REPONDS EN JSON:
{{
    "resume": "Resume en 2-3 phrases",
    "analyse_photos": {{
        "masse_grasse_estimee": "X%",
        "masse_musculaire": "Description",
        "points_forts": ["zone1"],
        "zones_a_travailler": ["zone1"],
        "evolution_visuelle": "Description",
        "note_physique": 7
    }},
    "metriques": {{"poids": "Xkg", "energie": "X/10", "sommeil": "Xh", "autres": []}},
    "evolution": {{"poids": "...", "energie": "...", "performance": "...", "adherence": "...", "global": "..."}},
    "kpis": {{"adherence_training": 8, "adherence_nutrition": 7, "sommeil": 6, "energie": 7, "progression": 8}},
    "points_positifs": ["Point 1", "Point 2"],
    "points_ameliorer": [{{"probleme": "...", "solution": "...", "priorite": "haute"}}],
    "questions_reponses": [{{"question": "...", "reponse": "..."}}],
    "ajustements": ["Ajustement 1"],
    "draft_email": "Email complet..."
}}"""

    content.append({"type": "text", "text": prompt})

    # Ajout des images (max 5)
    VALID_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    images_added = 0
    for att in current_email.get("attachments", []):
        if att["content_type"].startswith("image/") and images_added < 5:
            try:
                real_type = detect_image_type(att["data"])
                if real_type and real_type in VALID_IMAGE_TYPES:
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": real_type,
                            "data": att["data"]
                        }
                    })
                    images_added += 1
            except Exception as e:
                print(f"Erreur image: {e}")

    if images_added > 0:
        content.append({
            "type": "text",
            "text": f"{images_added} PHOTO(S) - Analyse composition corporelle, masse grasse, zones a travailler."
        })

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{"role": "user", "content": content}]
        )

        response_text = response.content[0].text

        try:
            json_match = response_text
            if "```json" in response_text:
                json_match = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                for part in response_text.split("```"):
                    if "{" in part and "}" in part:
                        json_match = part
                        break

            analysis = json.loads(json_match.strip())

            defaults = {
                "resume": "", "analyse_photos": {}, "metriques": {}, "evolution": {},
                "kpis": {"adherence_training": 7, "adherence_nutrition": 7, "sommeil": 7, "energie": 7, "progression": 7},
                "points_positifs": [], "points_ameliorer": [], "questions_reponses": [], "ajustements": [], "draft_email": ""
            }
            for key, default in defaults.items():
                if key not in analysis:
                    analysis[key] = default

        except:
            analysis = {
                "resume": "Analyse disponible", "analyse_photos": {}, "metriques": {}, "evolution": {},
                "kpis": {"adherence_training": 7, "adherence_nutrition": 7, "sommeil": 7, "energie": 7, "progression": 7},
                "points_positifs": [], "points_ameliorer": [], "questions_reponses": [], "ajustements": [],
                "draft_email": response_text
            }

        return {"success": True, "analysis": analysis, "raw_response": response_text, "photos_analyzed": images_added}

    except Exception as e:
        return {"success": False, "error": str(e), "analysis": None}


def _build_history_context(history: List[Dict[str, Any]]) -> str:
    if not history:
        return "Aucun historique (premier contact)."
    context_parts = [f"=== {len(history)} EMAILS ==="]
    for i, email_data in enumerate(history[-10:], 1):
        direction = "CLIENT" if email_data.get("direction") == "received" else "TOI"
        date = email_data.get("date")
        date_str = date.strftime("%d/%m/%Y") if date else "?"
        body = email_data.get("body", "")[:500]
        context_parts.append(f"--- {direction} ({date_str}) ---\n{body}")
    return "\n".join(context_parts)


def regenerate_email_draft(analysis: Dict[str, Any], instructions: str, current_draft: str) -> str:
    prompt = f"""Tu es Achzod, coach fitness.
Analyse: {json.dumps(analysis, ensure_ascii=False)[:2000]}
Draft: \"\"\"{current_draft}\"\"\"
Instructions: {instructions}
Reecris l'email. Style direct, tutoiement, emojis ok. Retourne UNIQUEMENT le texte."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return f"Erreur: {e}"
