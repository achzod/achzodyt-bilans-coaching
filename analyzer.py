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
    # Construire l'historique complet avec TOUTES les pièces jointes depuis le début
    history_text = _build_history_context(conversation_history)
    
    # Récupérer TOUTES les photos de TOUT l'historique (pas seulement l'email actuel)
    all_photos = []
    all_pdfs = []
    
    # Photos de l'email actuel
    photos = [att for att in current_email.get("attachments", []) if att.get("content_type", "").startswith("image/")]
    pdfs = [att for att in current_email.get("attachments", []) if "pdf" in att.get("content_type", "").lower()]
    all_photos.extend(photos)
    all_pdfs.extend(pdfs)
    
    # Photos de TOUT l'historique
    for hist_email in conversation_history:
        if not isinstance(hist_email, dict):
            continue
        hist_attachments = hist_email.get("attachments", [])
        for att in hist_attachments:
            if isinstance(att, dict):
                content_type = att.get("content_type", "")
                if content_type.startswith("image/"):
                    # Charger l'image depuis le filepath si disponible
                    filepath = att.get("filepath")
                    if filepath and os.path.exists(filepath):
                        try:
                            with open(filepath, "rb") as f:
                                img_data = base64.b64encode(f.read()).decode('utf-8')
                                all_photos.append({
                                    "data": img_data,
                                    "content_type": content_type,
                                    "filename": att.get("filename", ""),
                                    "from_email": hist_email.get("from_email", ""),
                                    "date": hist_email.get("date")
                                })
                        except:
                            pass
                elif "pdf" in content_type.lower():
                    filepath = att.get("filepath")
                    if filepath and os.path.exists(filepath):
                        all_pdfs.append({
                            "filepath": filepath,
                            "filename": att.get("filename", ""),
                            "from_email": hist_email.get("from_email", ""),
                            "date": hist_email.get("date")
                        })
    
    # Utiliser toutes les photos trouvées
    photos = all_photos
    pdfs = all_pdfs

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

        # Parser le JSON de maniere robuste avec plusieurs strategies
        analysis = None
        json_str = ""

        # Strategy 1: Nettoyer et parser directement
        try:
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

            # Trouver le JSON complet
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_str = text[start:end+1]
                analysis = json.loads(json_str)
                print("JSON parse OK (strategy 1)")
        except json.JSONDecodeError as e:
            print(f"JSON decode error (strategy 1): {e}")
            analysis = None

        # Strategy 2: Fixer les problemes courants de JSON
        if analysis is None and json_str:
            try:
                # Fixer les newlines non echappees dans les strings
                fixed = json_str
                # Remplacer les vrais newlines par \\n dans les valeurs de string
                fixed = re.sub(r'(?<!\\)\n', '\\\\n', fixed)
                # Fixer les guillemets non echappes
                fixed = re.sub(r'(?<!\\)"(?=[^:,\[\]{}]*[,\]}])', '\\"', fixed)
                analysis = json.loads(fixed)
                print("JSON parse OK (strategy 2 - fixed)")
            except:
                analysis = None

        # Strategy 3: Extraire champ par champ avec regex
        if analysis is None:
            print("Fallback: extraction champ par champ")
            analysis = {"resume": "", "analyse_photos": {}, "metriques": {}, "evolution": {},
                       "kpis": {}, "points_positifs": [], "points_ameliorer": [],
                       "questions_reponses": [], "ajustements": [], "draft_email": ""}

            # Extraire resume
            resume_match = re.search(r'"resume"\s*:\s*"([^"]*(?:\\"[^"]*)*)"', response_text)
            if resume_match:
                analysis["resume"] = resume_match.group(1).replace('\\"', '"').replace('\\n', '\n')

            # Extraire KPIs (chercher les nombres)
            for kpi in ["adherence_training", "adherence_nutrition", "sommeil", "energie", "sante", "mindset", "progression"]:
                kpi_match = re.search(rf'"{kpi}"\s*:\s*(\d+)', response_text)
                if kpi_match:
                    analysis["kpis"][kpi] = int(kpi_match.group(1))
                else:
                    analysis["kpis"][kpi] = 7  # default

        # Assurer que analysis est un dict avec tous les champs
        defaults = {
            "resume": "", "analyse_photos": {}, "metriques": {}, "evolution": {},
            "kpis": {"adherence_training": 7, "adherence_nutrition": 7, "sommeil": 7, "energie": 7, "sante": 7, "mindset": 7, "progression": 7},
            "points_positifs": [], "points_ameliorer": [], "questions_reponses": [], "ajustements": [], "draft_email": ""
        }

        if not isinstance(analysis, dict):
            analysis = defaults.copy()

        # Ajouter les champs manquants
        for k, v in defaults.items():
            if k not in analysis:
                analysis[k] = v
            # S'assurer que kpis est un dict avec tous les kpis
            if k == "kpis" and isinstance(analysis.get("kpis"), dict):
                for kpi_key, kpi_default in v.items():
                    if kpi_key not in analysis["kpis"]:
                        analysis["kpis"][kpi_key] = kpi_default

        # Extraire draft_email si manquant ou invalide
        draft = analysis.get("draft_email", "")
        if not draft or not isinstance(draft, str) or len(draft) < 50:
            print("Extraction draft_email depuis reponse brute...")
            # Methode 1: Regex standard
            draft_match = re.search(r'"draft_email"\s*:\s*"((?:[^"\\]|\\.)*)"', response_text, re.DOTALL)
            if draft_match:
                draft = draft_match.group(1)
                draft = draft.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                print(f"Draft extrait (methode 1): {len(draft)} chars")
            else:
                # Methode 2: Chercher entre "draft_email": " et la fin du JSON
                draft_start = response_text.find('"draft_email"')
                if draft_start != -1:
                    after = response_text[draft_start:]
                    # Trouver le debut de la valeur (apres : ")
                    colon_idx = after.find(':')
                    if colon_idx != -1:
                        after_colon = after[colon_idx+1:].lstrip()
                        if after_colon.startswith('"'):
                            # Chercher la fin de la string
                            content = after_colon[1:]  # Apres le premier "
                            # Trouver le " de fermeture (pas precede de \)
                            end_idx = 0
                            while end_idx < len(content):
                                if content[end_idx] == '"' and (end_idx == 0 or content[end_idx-1] != '\\'):
                                    break
                                end_idx += 1
                            if end_idx > 0:
                                draft = content[:end_idx]
                                draft = draft.replace('\\n', '\n').replace('\\"', '"')
                                print(f"Draft extrait (methode 2): {len(draft)} chars")

            if draft and len(draft) > 50:
                analysis["draft_email"] = draft

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
    """Construit le contexte complet depuis le début - TOUT l'historique"""
    if not history:
        return "Aucun historique - premier contact."
    
    # TOUT l'historique depuis le début (pas de limite)
    parts = [f"=== HISTORIQUE COMPLET: {len(history)} EMAILS DEPUIS LE DEBUT ==="]
    
    for i, e in enumerate(history, 1):  # TOUS les emails, pas seulement les 10 derniers
        d = "CLIENT" if e.get("direction") == "received" else "TOI"
        dt = e.get("date").strftime("%d/%m/%Y") if e.get("date") else "?"
        subject = e.get('subject', 'Sans sujet')
        body = e.get('body', '')
        
        # Inclure les infos sur les pièces jointes
        attachments_info = ""
        atts = e.get('attachments', [])
        if atts:
            att_names = [att.get('filename', '') for att in atts if isinstance(att, dict)]
            if att_names:
                attachments_info = f"\n[PIECES JOINTES: {', '.join(att_names)}]"
        
        parts.append(f"--- Email #{i}: {d} ({dt}) - {subject} ---{attachments_info}\n{body[:1000]}")
    
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
