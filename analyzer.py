"""
Module d'analyse IA des bilans de coaching - GPT-4o + Gemini
"""

import os
import base64
import json
import io
import re
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
import google.generativeai as genai
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

# Clients IA
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=55.0)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

MAX_IMAGE_SIZE = 4 * 1024 * 1024


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
        if raw[0] == 0xFF and raw[1] == 0xD8:
            return 'image/jpeg'
        if raw[0] == 0x89 and raw[1] == 0x50:
            return 'image/png'
        if raw[0] == 0x47 and raw[1] == 0x49:
            return 'image/gif'
        if raw[0] == 0x52 and raw[1] == 0x49:
            return 'image/webp'
    except:
        pass
    return None


def parse_excel_content(b64_data: str, filename: str = "file.xlsx") -> str:
    if not EXCEL_SUPPORT:
        return f"[Fichier Excel: {filename} - openpyxl non installe]"
    try:
        excel_bytes = base64.b64decode(b64_data)
        excel_file = io.BytesIO(excel_bytes)
        wb = openpyxl.load_workbook(excel_file, data_only=True)
        result_parts = [f"=== CONTENU FICHIER EXCEL: {filename} ==="]
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            result_parts.append(f"\n--- Feuille: {sheet_name} ---")
            rows_content = []
            for row in sheet.iter_rows(values_only=True):
                if any(cell is not None for cell in row):
                    row_str = " | ".join(str(cell) if cell is not None else "" for cell in row)
                    rows_content.append(row_str)
            if rows_content:
                result_parts.extend(rows_content[:100])
            else:
                result_parts.append("(Feuille vide)")
        wb.close()
        return "\n".join(result_parts)
    except Exception as e:
        return f"[Erreur lecture Excel {filename}: {str(e)}]"


def build_prompt(history_text, date_str, body_text, photos_count, excel_content):
    return f"""Coach ELITE transformation physique. Analyse ce bilan HONNETEMENT et reponds en JSON.

STYLE: Direct, tutoiement, JAMAIS d'asterisques (*), HONNETE sur le physique, pas de flatterie.

GUIDE MASSE GRASSE (STRICT):
FEMME: 18-20%=fit+abdos visibles | 24-28%=normale, PAS d'abdos, gras hanches/cuisses | 30-35%=surpoids | 35%+=obesite
HOMME: 10-12%=abdos decoupes | 15-18%=fit, abdos peu visibles | 20-25%=gras ventre | 28%+=surpoids
REGLE: Pas d'abdos visibles = MINIMUM 25% femme / 20% homme.

CONSEILS ADAPTES AU PROFIL:
- SURPOIDS: JAMAIS de snacks/barres! Structure et discipline sur les repas.
- SEC en seche: collation de secours OK.

=== HISTORIQUE COMPLET DEPUIS JOUR 1 ===
{history_text[:6000] if history_text else "Premier contact"}

=== BILAN ACTUEL ({date_str}) ===
{body_text[:5000]}

DONNEES: {photos_count} photos, Excel: {bool(excel_content)}
{excel_content[:2000] if excel_content else ""}

EXTRACTION (LIS TOUT L'HISTORIQUE!):
1. POIDS DE DEPART: Premier email client
2. POIDS ACTUEL: Bilan actuel
3. PROGRAMME: Dans les reponses COACH de l'historique
4. NE JAMAIS INVENTER!

CONSEILS ULTRA-SPECIFIQUES (JAMAIS DE VAGUE!):
Tu es un coach EXPERT avec 11 certifications. JAMAIS de conseils generiques!

INTERDIT: "ajoute du volume", "resserre la diet", "fais plus de cardio"
OBLIGATOIRE:
- EXERCICES PRECIS: "4x10 developpe incline + 3x12 ecarte poulie"
- MACROS EXACTES: "200P / 180G / 60L = 2060kcal"
- DUREE/FREQUENCE: "35min LISS, 4x/semaine"

EMAIL HTML OBLIGATOIRE avec:
1. Bloc "Ton Evolution depuis le Jour 1" (gradient violet, boxes blanches)
2. Poids jour1→actuel, Masse grasse, Pas/jour, Energie
3. Ce qui a change (progres concrets)
4. Plan d'action PRECIS
5. Signe "Achzod"

TEMPLATE HTML:
<div style='font-family:Arial,sans-serif;max-width:600px;'>
  <p>Salut [prenom],</p>
  <p>[Intro]</p>
  <div style='background:linear-gradient(135deg,#667eea,#764ba2);border-radius:16px;padding:24px;margin:24px 0;color:white;'>
    <h3 style='margin:0 0 20px 0;text-align:center;'>📈 Ton Evolution depuis le Jour 1</h3>
    <div style='display:flex;flex-wrap:wrap;gap:12px;justify-content:center;'>
      <div style='background:rgba(255,255,255,0.2);border-radius:12px;padding:16px;text-align:center;min-width:120px;'>
        <div style='font-size:14px;opacity:0.9;'>Poids</div>
        <div style='font-size:20px;font-weight:bold;margin:8px 0;'>XXkg → XXkg</div>
        <div style='color:#4ade80;'>-Xkg</div>
      </div>
      <!-- Ajouter Masse Grasse, Pas/jour, Energie -->
    </div>
  </div>
  <h3 style='color:#22c55e;'>✅ Progres</h3>
  <p>[Details]</p>
  <h3 style='color:#f59e0b;'>🎯 Plan d'action</h3>
  <p>[Actions PRECISES]</p>
  <p style='margin-top:30px;'>Achzod</p>
</div>

JSON:
{{"resume":"analyse","analyse_photos":{{"masse_grasse_actuelle":"X%","evolution":"desc"}},"evolution_metriques":{{"poids":{{"jour1":"Xkg","actuel":"Xkg","diff":"-Xkg"}}}},"points_positifs":["x"],"points_ameliorer":[{{"probleme":"x","solution":"y"}}],"plan_action":{{"training":"x","nutrition":"x","cardio":"x"}},"draft_email":"HTML COMPLET"}}"""


def call_gpt4(prompt: str, images: list) -> Dict:
    """Appel GPT-4o (dernier modele OpenAI - decembre 2024)"""
    try:
        content = [{"type": "text", "text": prompt}]
        for img_data, img_type in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img_type};base64,{img_data}", "detail": "high"}
            })

        response = openai_client.chat.completions.create(
            model="gpt-4o",  # GPT-4 Omni - LE PLUS RECENT (dec 2024)
            max_tokens=8000,
            messages=[{"role": "user", "content": content}]
        )
        return {"success": True, "text": response.choices[0].message.content, "model": "GPT-4o (Latest)"}
    except Exception as e:
        return {"success": False, "error": str(e), "model": "GPT-4o"}


def call_gemini(prompt: str, images: list) -> Dict:
    """Appel Gemini 1.5 Pro (dernier modele Google - decembre 2024)"""
    try:
        model = genai.GenerativeModel('gemini-1.5-pro')  # LE PLUS RECENT disponible

        # Construire le contenu
        parts = [prompt]
        for img_data, img_type in images:
            img_bytes = base64.b64decode(img_data)
            parts.append({"mime_type": img_type, "data": img_bytes})

        response = model.generate_content(parts)
        return {"success": True, "text": response.text, "model": "Gemini-1.5-Pro"}
    except Exception as e:
        return {"success": False, "error": str(e), "model": "Gemini-1.5-Pro"}


def parse_json_response(response_text: str) -> Dict:
    """Parse JSON depuis la reponse IA"""
    try:
        text = response_text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            for p in text.split("```"):
                if "{" in p and "draft_email" in p:
                    text = p
                    break

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_str = text[start:end+1]
            return json.loads(json_str)
    except:
        pass

    # Fallback: extraire les champs manuellement
    analysis = {"resume": "", "draft_email": "", "points_positifs": [], "points_ameliorer": []}

    # Extraire draft_email
    draft_match = re.search(r'"draft_email"\s*:\s*"((?:[^"\\]|\\.)*)"', response_text, re.DOTALL)
    if draft_match:
        analysis["draft_email"] = draft_match.group(1).replace('\\n', '\n').replace('\\"', '"')

    return analysis


def analyze_coaching_bilan(current_email, conversation_history, client_name=""):
    """Analyse avec GPT-4o ET Gemini - retourne les 2 resultats"""

    history_text = _build_history_context(conversation_history)
    attachments = current_email.get("attachments", [])
    photos = [att for att in attachments if att.get("content_type", "").startswith("image/")]
    excels = [att for att in attachments if any(ext in att.get("filename", "").lower() for ext in ['.xlsx', '.xls'])]

    # Parse Excel
    excel_content = ""
    for excel_att in excels:
        if excel_att.get("data"):
            excel_content += "\n\n" + parse_excel_content(excel_att["data"], excel_att.get("filename", "fichier.xlsx"))

    date_str = current_email["date"].strftime("%d/%m/%Y %H:%M") if current_email.get("date") else "N/A"
    body_text = current_email.get("body", "") or ""

    # Build prompt
    prompt = build_prompt(history_text, date_str, body_text, len(photos), excel_content)

    # Prepare images
    images = []
    VALID_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    for att in photos[:5]:
        try:
            real_type = detect_image_type(att["data"])
            if real_type and real_type in VALID_TYPES:
                compressed, final_type = compress_image_if_needed(att["data"], real_type)
                images.append((compressed, final_type))
        except:
            pass

    print(f"[ANALYZE] Running GPT-4o and Gemini in parallel with {len(images)} images...")

    # Appels en parallele
    results = {"gpt4": None, "gemini": None}

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(call_gpt4, prompt, images): "gpt4",
            executor.submit(call_gemini, prompt, images): "gemini"
        }
        for future in as_completed(futures):
            ai_name = futures[future]
            try:
                results[ai_name] = future.result()
            except Exception as e:
                results[ai_name] = {"success": False, "error": str(e), "model": ai_name}

    # Parser les resultats
    analyses = {}

    for ai_name, result in results.items():
        if result and result.get("success"):
            parsed = parse_json_response(result["text"])
            parsed["_model"] = result["model"]
            parsed["_raw"] = result["text"][:500]
            analyses[ai_name] = parsed
        else:
            analyses[ai_name] = {"error": result.get("error", "Unknown error"), "_model": result.get("model", ai_name)}

    # Retourner les 2 analyses
    return {
        "success": True,
        "gpt4": analyses.get("gpt4", {}),
        "gemini": analyses.get("gemini", {}),
        "photos_analyzed": len(images)
    }


def _build_history_context(history):
    if not history:
        return ""
    parts = [f"[{len(history)} emails precedents]"]
    for i, e in enumerate(history[-15:], 1):
        if not e or not isinstance(e, dict):
            continue
        direction = "CLIENT" if e.get("direction") == "received" else "COACH (toi)"
        dt = e.get("date").strftime("%d/%m/%Y") if e.get("date") else "?"
        body = e.get('body', '') or ''
        body_preview = body[:1500] + "..." if len(body) > 1500 else body
        parts.append(f"\n--- Email {i} - {direction} ({dt}) ---\n{body_preview}")
    return "\n".join(parts)


def regenerate_email_draft(analysis, instructions, current_draft):
    """Regenere le draft avec GPT-4o"""
    prompt = f"""Tu es Achzod, coach expert. JAMAIS d'asterisques.
Analyse: {json.dumps(analysis, ensure_ascii=False)[:3000]}
Draft actuel: {current_draft}
Instructions: {instructions}
Reecris email 250-400 mots MAXIMUM, sans asterisques, style direct expert tutoiement."""

    try:
        r = openai_client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"Erreur: {e}"
