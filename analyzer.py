"""
Module d'analyse IA des bilans de coaching avec Claude
"""

import os
import base64
import json
import io
from typing import List, Dict, Any, Optional
from anthropic import Anthropic
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MAX_IMAGE_SIZE = 4 * 1024 * 1024  # 4 MB (marge sous les 5 MB de Claude)


def compress_image_if_needed(b64_data: str, media_type: str) -> tuple:
    raw_size = len(base64.b64decode(b64_data))
    if raw_size <= MAX_IMAGE_SIZE:
        return b64_data, media_type
    try:
        img_bytes = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(img_bytes))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        quality = 85
        max_dimension = 2000
        while True:
            if max(img.size) > max_dimension:
                ratio = max_dimension / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img_resized = img.resize(new_size, Image.LANCZOS)
            else:
                img_resized = img
            buffer = io.BytesIO()
            img_resized.save(buffer, format='JPEG', quality=quality, optimize=True)
            compressed_data = buffer.getvalue()
            if len(compressed_data) <= MAX_IMAGE_SIZE:
                return base64.b64encode(compressed_data).decode('utf-8'), 'image/jpeg'
            quality -= 10
            max_dimension -= 200
            if quality < 30 or max_dimension < 800:
                img_resized = img.resize((800, int(800 * img.size[1] / img.size[0])), Image.LANCZOS)
                buffer = io.BytesIO()
                img_resized.save(buffer, format='JPEG', quality=30, optimize=True)
                return base64.b64encode(buffer.getvalue()).decode('utf-8'), 'image/jpeg'
    except Exception as e:
        print(f"Erreur compression: {e}")
        return b64_data, media_type


def detect_image_type(b64_data: str) -> Optional[str]:
    try:
        raw = base64.b64decode(b64_data[:32])
        if raw[0] == 0xFF and raw[1] == 0xD8 and raw[2] == 0xFF:
            return 'image/jpeg'
        if raw[0] == 0x89 and raw[1] == 0x50 and raw[2] == 0x4E and raw[3] == 0x47:
            return 'image/png'
        if raw[0] == 0x47 and raw[1] == 0x49 and raw[2] == 0x46 and raw[3] == 0x38:
            return 'image/gif'
        if raw[0] == 0x52 and raw[1] == 0x49 and raw[2] == 0x46 and raw[3] == 0x46:
            if len(raw) > 11 and raw[8] == 0x57 and raw[9] == 0x45:
                return 'image/webp'
    except:
        pass
    return None


def analyze_coaching_bilan(current_email, conversation_history, client_name=""):
    history_text = _build_history_context(conversation_history)
    photos = [att for att in current_email.get("attachments", []) if att["content_type"].startswith("image/")]
    pdfs = [att for att in current_email.get("attachments", []) if "pdf" in att["content_type"].lower()]

    content = []

    date_str = current_email["date"].strftime("%d/%m/%Y %H:%M") if current_email.get("date") else "N/A"
    
    prompt = f"""Tu es Achzod, coach de HAUT NIVEAU avec 10+ ans en transformation physique et optimisation hormonale.

REGLES STRICTES:
- JAMAIS d asterisques ou etoiles dans tes reponses
- Sois DETAILLE et EXPERT, explique le POURQUOI de chaque conseil
- Utilise ton expertise: anatomie, physiologie, nutrition, hormones
- Ecris comme un vrai coach humain, pas comme une IA
- Tutoiement obligatoire, emojis ok avec moderation
- Email de reponse: MINIMUM 500 mots, hyper detaille et personnalise

HISTORIQUE CLIENT:
{history_text}

BILAN A ANALYSER:
Date: {date_str}
Sujet: {current_email.get("subject", "Sans sujet")}

Message du client:
{current_email.get("body", "")}

Pieces jointes: {len(photos)} photo(s), {len(pdfs)} PDF(s)

CE QUE TU DOIS FAIRE:

1. PHOTOS (si presentes): estime masse grasse (ex: 14-16 pourcent), decris chaque zone musculaire en detail, points forts avec explications, zones a bosser avec conseils precis

2. METRIQUES: analyse poids, energie, sommeil, perfs avec interpretation et tendances

3. QUESTIONS: reponds a CHAQUE question du client avec PROFONDEUR et expertise, explique les mecanismes physiologiques

4. KPIs sur 10 avec justification pour chaque note:
   - adherence_training: respect du programme entrainement
   - adherence_nutrition: respect du plan alimentaire
   - sommeil: qualite et quantite de sommeil
   - energie: niveau energie ressenti
   - sante: indicateurs sante (digestion, libido, stress, douleurs)
   - mindset: mental, motivation, discipline, confiance
   - progression: evolution globale vers objectifs

5. POINTS POSITIFS: celebre les victoires meme petites, sois specifique sur ce qui est bien

6. A AMELIORER: probleme + pourquoi important physiologiquement + solution detaillee + resultat attendu

7. EMAIL DE REPONSE: 250-400 mots MAXIMUM, structure claire, ZERO asterisque, va a l'essentiel

Reponds en JSON valide avec cette structure:
{{"resume": "Resume detaille 4-5 phrases", "analyse_photos": {{"masse_grasse_estimee": "14-16%", "masse_musculaire": "Description detaillee", "points_forts": ["Zone avec explication"], "zones_a_travailler": ["Zone avec conseil"], "evolution_visuelle": "Comparaison", "note_physique": 7}}, "metriques": {{"poids": "Analyse", "energie": "Analyse", "sommeil": "Analyse", "autres": []}}, "evolution": {{"poids": "Analyse", "energie": "Analyse", "performance": "Analyse", "adherence": "Analyse", "global": "Synthese"}}, "kpis": {{"adherence_training": 8, "adherence_nutrition": 7, "sommeil": 6, "energie": 7, "sante": 7, "mindset": 7, "progression": 8}}, "points_positifs": ["Point detaille"], "points_ameliorer": [{{"probleme": "Description", "solution": "Solution detaillee", "priorite": "haute"}}], "questions_reponses": [{{"question": "Question", "reponse": "Reponse DETAILLEE"}}], "ajustements": ["Ajustement avec raison"], "draft_email": "EMAIL 250-400 mots sans asterisques"}}"""

    content.append({"type": "text", "text": prompt})

    VALID_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    images_added = 0
    for att in current_email.get("attachments", []):
        if att["content_type"].startswith("image/") and images_added < 5:
            try:
                real_type = detect_image_type(att["data"])
                if real_type and real_type in VALID_IMAGE_TYPES:
                    compressed_data, final_type = compress_image_if_needed(att["data"], real_type)
                    content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": final_type, "data": compressed_data}
                    })
                    images_added += 1
            except:
                pass

    if images_added > 0:
        content.append({"type": "text", "text": f"{images_added} PHOTO(S) - Analyse en DETAIL: masse grasse, zones musculaires, points forts, zones a travailler."})

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=8000,
            messages=[{"role": "user", "content": content}]
        )
        response_text = response.content[0].text

        # Parser le JSON de maniere robuste
        analysis = None
        try:
            # Nettoyer la reponse
            text = response_text.strip()

            # Enlever les blocs de code markdown
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                parts = text.split("```")
                for p in parts:
                    if "{" in p and "draft_email" in p:
                        text = p
                        break

            # Trouver le JSON complet avec regex
            import re
            # Trouver le premier { et le dernier }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_str = text[start:end+1]
                analysis = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            analysis = None
        except Exception as e:
            print(f"Erreur parsing: {e}")
            analysis = None

        # Si parsing echoue, extraire draft_email manuellement
        if analysis is None or not isinstance(analysis, dict):
            print("Fallback: extraction manuelle du draft_email")
            import re
            # Chercher draft_email dans le texte brut
            draft_match = re.search(r'"draft_email"\s*:\s*"((?:[^"\\]|\\.)*)"\s*}', response_text, re.DOTALL)
            if draft_match:
                draft = draft_match.group(1)
                # Decoder les escapes
                draft = draft.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
            else:
                # Dernier recours: chercher le texte apres "draft_email":
                draft_start = response_text.find('"draft_email"')
                if draft_start != -1:
                    # Chercher le debut de la valeur
                    colon = response_text.find(':', draft_start)
                    if colon != -1:
                        # Chercher les guillemets
                        quote1 = response_text.find('"', colon + 1)
                        if quote1 != -1:
                            # Trouver la fin (guillemet non escape avant } ou fin)
                            rest = response_text[quote1+1:]
                            # Chercher le pattern de fin: " suivi de } ou fin de JSON
                            end_match = re.search(r'(?<!\\)"\s*}?\s*$', rest)
                            if end_match:
                                draft = rest[:end_match.start()]
                                draft = draft.replace('\\n', '\n').replace('\\"', '"')
                            else:
                                draft = "Email a rediger manuellement."
                        else:
                            draft = "Email a rediger manuellement."
                    else:
                        draft = "Email a rediger manuellement."
                else:
                    draft = "Email a rediger manuellement."

            analysis = {
                "resume": "", "analyse_photos": {}, "metriques": {}, "evolution": {},
                "kpis": {"adherence_training": 7, "adherence_nutrition": 7, "sommeil": 7, "energie": 7, "sante": 7, "mindset": 7, "progression": 7},
                "points_positifs": [], "points_ameliorer": [], "questions_reponses": [], "ajustements": [],
                "draft_email": draft
            }
        else:
            # Ajouter les defaults manquants
            defaults = {"resume": "", "analyse_photos": {}, "metriques": {}, "evolution": {}, "kpis": {"adherence_training": 7, "adherence_nutrition": 7, "sommeil": 7, "energie": 7, "sante": 7, "mindset": 7, "progression": 7}, "points_positifs": [], "points_ameliorer": [], "questions_reponses": [], "ajustements": [], "draft_email": ""}
            for k, v in defaults.items():
                if k not in analysis:
                    analysis[k] = v

        # Verifier que draft_email est une string propre
        draft = analysis.get("draft_email", "")
        if not isinstance(draft, str):
            draft = str(draft) if draft else ""
        if not draft or draft.startswith("{") or draft.startswith("["):
            # Generer email depuis les donnees
            parts = ["Bonjour,", ""]
            if analysis.get("resume"):
                parts.append(analysis["resume"])
                parts.append("")
            parts.append("A bientot,")
            parts.append("Achzod")
            analysis["draft_email"] = chr(10).join(parts)

        print(f"Draft email extrait: {len(analysis.get('draft_email', ''))} chars")

        return {"success": True, "analysis": analysis, "raw_response": response_text, "photos_analyzed": images_added}
    except Exception as e:
        return {"success": False, "error": str(e), "analysis": None}


def _build_history_context(history):
    if not history:
        return "Aucun historique - premier contact."
    parts = [f"=== {len(history)} EMAILS ==="]
    for i, e in enumerate(history[-10:], 1):
        d = "CLIENT" if e.get("direction") == "received" else "TOI"
        dt = e.get("date").strftime("%d/%m/%Y") if e.get("date") else "?"
        parts.append(f"--- {d} ({dt}) ---" + chr(10) + e.get('body', '')[:800])
    return chr(10).join(parts)


def regenerate_email_draft(analysis, instructions, current_draft):
    prompt = f"""Tu es Achzod, coach expert. JAMAIS d asterisques.
Analyse: {json.dumps(analysis, ensure_ascii=False)[:3000]}
Draft actuel: {current_draft}
Instructions: {instructions}
Reecris email 250-400 mots MAXIMUM, sans asterisques, style direct expert tutoiement. Va a l'essentiel."""
    try:
        r = client.messages.create(model="claude-sonnet-4-5-20250929", max_tokens=4000, messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    except Exception as e:
        return f"Erreur: {e}"
