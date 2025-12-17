"""
Module d'analyse IA des bilans de coaching avec Claude
"""

import os
import base64
import json
import io
import re
from typing import List, Dict, Any, Optional
from anthropic import Anthropic
from dotenv import load_dotenv
from PIL import Image

# Excel support
try:
    import openpyxl
    EXCEL_SUPPORT = True
except ImportError:
    EXCEL_SUPPORT = False
    print("Warning: openpyxl not installed, Excel parsing disabled")

load_dotenv()

# Client avec timeout explicite pour eviter les 502 sur Render
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    timeout=55.0  # Render a 60s max, on prend 55s pour avoir une marge
)

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


def parse_excel_content(b64_data: str, filename: str = "file.xlsx") -> str:
    """Parse Excel file and return text content for AI analysis"""
    if not EXCEL_SUPPORT:
        return f"[Fichier Excel: {filename} - openpyxl non installe]"

    try:
        # Decode base64 to bytes
        excel_bytes = base64.b64decode(b64_data)
        excel_file = io.BytesIO(excel_bytes)

        # Load workbook
        wb = openpyxl.load_workbook(excel_file, data_only=True)

        result_parts = [f"=== CONTENU FICHIER EXCEL: {filename} ==="]

        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            result_parts.append(f"\n--- Feuille: {sheet_name} ---")

            rows_content = []
            for row in sheet.iter_rows(values_only=True):
                # Filter out completely empty rows
                if any(cell is not None for cell in row):
                    # Convert cells to strings, handle None
                    row_str = " | ".join(str(cell) if cell is not None else "" for cell in row)
                    rows_content.append(row_str)

            if rows_content:
                result_parts.extend(rows_content[:100])  # Limit rows per sheet
                if len(rows_content) > 100:
                    result_parts.append(f"... ({len(rows_content) - 100} lignes supplementaires)")
            else:
                result_parts.append("(Feuille vide)")

        wb.close()
        return "\n".join(result_parts)

    except Exception as e:
        print(f"Erreur parsing Excel {filename}: {e}")
        return f"[Erreur lecture Excel {filename}: {str(e)}]"


def analyze_coaching_bilan(current_email, conversation_history, client_name=""):
    history_text = _build_history_context(conversation_history)
    attachments = current_email.get("attachments", [])
    photos = [att for att in attachments if att.get("content_type", "").startswith("image/")]
    pdfs = [att for att in attachments if "pdf" in att.get("content_type", "").lower()]
    excels = [att for att in attachments if any(ext in att.get("filename", "").lower() for ext in ['.xlsx', '.xls']) or
              any(x in att.get("content_type", "").lower() for x in ['spreadsheet', 'excel'])]

    content = []

    # Parse Excel files first to include in prompt
    excel_content = ""
    for excel_att in excels:
        if excel_att.get("data"):
            parsed = parse_excel_content(excel_att["data"], excel_att.get("filename", "fichier.xlsx"))
            excel_content += "\n\n" + parsed

    date_str = current_email["date"].strftime("%d/%m/%Y %H:%M") if current_email.get("date") else "N/A"

    # Construire le body complet (pas tronque)
    body_text = current_email.get("body", "") or ""

    prompt = f"""Coach ELITE transformation physique. Analyse ce bilan et reponds en JSON.

STYLE: Direct, tutoiement, JAMAIS d'asterisques (*), conseils EXPERTS avec dosages precis.

HISTORIQUE:
{history_text[:3000] if history_text else "Premier contact"}

BILAN ({date_str}):
{body_text[:4000]}

DONNEES: {len(photos)} photos, {len(excels)} Excel
{excel_content[:2000] if excel_content else ""}

ANALYSE:
1. PHOTOS: masse grasse %, description physique zone par zone, points forts, zones a bosser, evolution
2. METABOLIQUE: poids, retention eau, signes hormonaux
3. COMPORTEMENT: adherence diete/training, sommeil, stress
4. RECOMMANDATIONS: diete (calories/macros), training, supplements (produit+dose), lifestyle

EMAIL (400 mots): Analyse photos detaillee, victoires, conseils experts avec POURQUOI, questions si infos manquantes, next steps. Signe "Achzod"

JSON OBLIGATOIRE:
{{"resume":"analyse 4-5 phrases","analyse_photos":{{"masse_grasse":"X%","description":"zone par zone","points_forts":["muscle"],"zones_a_travailler":["zone"],"evolution":"vs avant"}},"kpis":{{"adherence_training":7,"adherence_nutrition":7,"sommeil":7,"energie":7,"sante":7,"mindset":7,"progression":7}},"points_positifs":["victoire"],"points_ameliorer":[{{"probleme":"x","solution":"y","priorite":"haute"}}],"ajustements_proposes":{{"diete":"x","training":"x","supplements":"x","lifestyle":"x"}},"questions_a_poser":["question"],"draft_email":"EMAIL COMPLET 400 mots"}}"""

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
        # Utiliser claude-sonnet-4-20250514 avec assez de tokens pour reponse complete
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=6000,
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
    if not history:
        return ""
    parts = [f"[{len(history)} emails precedents avec ce client]"]
    # Prendre les 15 derniers emails pour contexte complet
    for i, e in enumerate(history[-15:], 1):
        if not e or not isinstance(e, dict):
            continue
        direction = "CLIENT" if e.get("direction") == "received" else "COACH (toi)"
        dt = e.get("date").strftime("%d/%m/%Y") if e.get("date") else "?"
        body = e.get('body', '') or ''
        # Garder plus de contenu par email (1500 chars)
        body_preview = body[:1500] + "..." if len(body) > 1500 else body
        parts.append(f"\n--- Email {i} - {direction} ({dt}) ---\n{body_preview}")
    return chr(10).join(parts)


def regenerate_email_draft(analysis, instructions, current_draft):
    prompt = f"""Tu es Achzod, coach expert. JAMAIS d asterisques.
Analyse: {json.dumps(analysis, ensure_ascii=False)[:3000]}
Draft actuel: {current_draft}
Instructions: {instructions}
Reecris email 250-400 mots MAXIMUM, sans asterisques, style direct expert tutoiement. Va a l'essentiel."""
    try:
        r = client.messages.create(model="claude-sonnet-4-20250514", max_tokens=2000, messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    except Exception as e:
        return f"Erreur: {e}"
