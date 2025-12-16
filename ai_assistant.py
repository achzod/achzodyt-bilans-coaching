"""
AI Assistant - Module IA pour aider le coach
Genere des analyses, drafts de reponses, et conseils personnalises
"""

import os
import json
from typing import List, Dict, Any, Optional
from anthropic import Anthropic
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# System prompt pour l'assistant
COACH_ASSISTANT_PROMPT = """Tu es l'assistant IA d'Achzod, coach expert en transformation physique avec 10+ ans d'experience.

TON ROLE:
- Analyser les bilans clients en profondeur
- Generer des drafts de reponses personnalisees
- Fournir des insights et recommandations basees sur les donnees
- Aider a identifier les patterns et problemes

STYLE D'ECRITURE:
- JAMAIS d'asterisques ou etoiles (*) dans tes reponses
- Tutoiement obligatoire avec le client
- Ton direct, expert mais bienveillant
- Emojis avec moderation
- Explications basees sur la science (physiologie, nutrition)

FORMAT REPONSES CLIENT:
- 250-400 mots maximum
- Structure claire avec paragraphes
- Commence par reconnaitre les efforts/victoires
- Reponds aux questions specifiques
- Termine par des actions concretes

TU NE DOIS JAMAIS:
- Donner de conseils medicaux specifiques
- Recommander des medicaments
- Faire des promesses de resultats
- Etre condescendant ou negatif"""


def analyze_client_bilan(bilan: Dict, client_info: Dict, history: List[Dict] = None) -> Dict:
    """
    Analyse complete d'un bilan client avec historique
    Retourne: resume, kpis, points forts, a ameliorer, draft reponse
    """

    # Construire le contexte historique
    history_context = ""
    if history:
        history_context = "\n\nHISTORIQUE (derniers bilans):\n"
        for i, h in enumerate(history[-5:], 1):  # 5 derniers bilans max
            history_context += f"\n--- Semaine {h.get('week_number', i)} ---\n"
            if h.get('poids'):
                history_context += f"Poids: {h['poids']} kg\n"
            if h.get('energie'):
                history_context += f"Energie: {h['energie']}/10\n"
            if h.get('sommeil_qualite'):
                history_context += f"Sommeil: {h['sommeil_qualite']}/10\n"
            if h.get('motivation'):
                history_context += f"Motivation: {h['motivation']}/10\n"
            if h.get('victoires'):
                history_context += f"Victoires: {h['victoires'][:200]}\n"

    # Formatter le bilan actuel
    bilan_text = f"""
BILAN SEMAINE {bilan.get('week_number', '?')}
Date: {bilan.get('date_submitted', 'N/A')}

MESURES:
- Poids: {bilan.get('poids', 'N/A')} kg
- Tour de taille: {bilan.get('tour_taille', 'N/A')} cm

RESSENTI (/10):
- Energie: {bilan.get('energie', 'N/A')}
- Sommeil: {bilan.get('sommeil_qualite', 'N/A')} ({bilan.get('sommeil_heures', '?')}h)
- Motivation: {bilan.get('motivation', 'N/A')}
- Stress: {bilan.get('stress', 'N/A')}
- Faim: {bilan.get('faim', 'N/A')}
- Digestion: {bilan.get('digestion', 'N/A')}

ENTRAINEMENT:
- Seances: {bilan.get('seances_faites', 'N/A')}/{bilan.get('seances_prevues', 'N/A')}
- Intensite: {bilan.get('intensite_moyenne', 'N/A')}/10
- Difficultes: {bilan.get('difficultes_training', 'Aucune')}

NUTRITION:
- Respect plan: {bilan.get('respect_calories', 'N/A')}/10
- Ecarts: {bilan.get('nombre_ecarts', 'N/A')}
- Hydratation: {bilan.get('hydratation_litres', 'N/A')}L/jour

FEEDBACK CLIENT:
Victoires: {bilan.get('victoires', 'Non renseigne')}
Difficultes: {bilan.get('difficultes', 'Non renseigne')}
Questions: {bilan.get('questions', 'Aucune')}
Notes: {bilan.get('notes_libres', '')}
"""

    prompt = f"""{COACH_ASSISTANT_PROMPT}

CLIENT: {client_info.get('name', 'Client')}
Objectif: {client_info.get('objectif', 'Transformation')}
Debut: {client_info.get('date_debut', 'N/A')} | Duree: {client_info.get('duree_semaines', 12)} semaines
{history_context}

BILAN A ANALYSER:
{bilan_text}

ANALYSE DEMANDEE:
1. Resume en 3-4 phrases des points cles
2. KPIs extraits avec note /10 et justification courte:
   - adherence_training (respect programme)
   - adherence_nutrition (respect plan)
   - sommeil (qualite + quantite)
   - energie (niveau general)
   - progression (vers objectif)
   - mindset (mental, motivation)
3. Points positifs (minimum 2, sois specifique)
4. Points a ameliorer (max 3, avec solutions concretes)
5. Reponses aux questions du client si presentes
6. Draft email de reponse (250-400 mots, SANS asterisques)

Reponds en JSON valide:
{{
    "resume": "Resume 3-4 phrases",
    "kpis": {{
        "adherence_training": {{"score": 8, "raison": "Courte justification"}},
        "adherence_nutrition": {{"score": 7, "raison": "..."}},
        "sommeil": {{"score": 6, "raison": "..."}},
        "energie": {{"score": 7, "raison": "..."}},
        "progression": {{"score": 7, "raison": "..."}},
        "mindset": {{"score": 8, "raison": "..."}}
    }},
    "points_positifs": ["Point 1 specifique", "Point 2"],
    "points_ameliorer": [
        {{"probleme": "Description", "solution": "Solution concrete", "priorite": "haute"}}
    ],
    "questions_reponses": [
        {{"question": "Question du client", "reponse": "Reponse detaillee"}}
    ],
    "tendances": {{
        "poids": "stable/baisse/hausse",
        "energie": "stable/baisse/hausse",
        "adherence": "stable/baisse/hausse"
    }},
    "alertes": ["Alerte si necessaire"],
    "draft_email": "Email complet 250-400 mots sans asterisques"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Parser le JSON
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        start = response_text.find("{")
        end = response_text.rfind("}")
        if start != -1 and end != -1:
            response_text = response_text[start:end+1]

        analysis = json.loads(response_text)

        return {
            "success": True,
            "analysis": analysis,
            "draft": analysis.get("draft_email", "")
        }

    except json.JSONDecodeError as e:
        # Fallback: extraire ce qu'on peut
        return {
            "success": False,
            "error": f"JSON parse error: {e}",
            "raw_response": response_text if 'response_text' in locals() else ""
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def regenerate_response(analysis: Dict, bilan: Dict, instructions: str) -> str:
    """
    Regenere un draft de reponse avec des instructions specifiques
    """

    prompt = f"""{COACH_ASSISTANT_PROMPT}

ANALYSE EXISTANTE:
{json.dumps(analysis, ensure_ascii=False)[:2000]}

BILAN CLIENT (resume):
- Poids: {bilan.get('poids', 'N/A')} kg
- Energie: {bilan.get('energie', 'N/A')}/10
- Seances: {bilan.get('seances_faites', 'N/A')}/{bilan.get('seances_prevues', 'N/A')}
- Victoires: {bilan.get('victoires', '')[:200]}
- Questions: {bilan.get('questions', '')[:200]}

INSTRUCTIONS SUPPLEMENTAIRES:
{instructions}

Genere un NOUVEL email de reponse (250-400 mots) en tenant compte des instructions.
SANS asterisques, style direct et expert, tutoiement.

Retourne UNIQUEMENT l'email, pas de JSON ni markdown."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text.strip()

    except Exception as e:
        return f"Erreur generation: {e}"


def generate_quick_response(message: str, client_info: Dict, context: str = "") -> str:
    """
    Genere une reponse rapide a un message client (pas un bilan)
    """

    prompt = f"""{COACH_ASSISTANT_PROMPT}

CLIENT: {client_info.get('name', 'Client')}
Objectif: {client_info.get('objectif', 'Transformation')}

CONTEXTE RECENT:
{context[:1000] if context else 'Pas de contexte'}

MESSAGE DU CLIENT:
{message}

Genere une reponse courte et utile (100-200 mots max).
SANS asterisques, tutoiement, style coach expert.

Retourne UNIQUEMENT la reponse."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text.strip()

    except Exception as e:
        return f"Erreur: {e}"


def analyze_progress(bilans: List[Dict], client_info: Dict) -> Dict:
    """
    Analyse la progression globale d'un client sur plusieurs semaines
    Pour generer un rapport d'evolution
    """

    if not bilans:
        return {"error": "Pas de bilans disponibles"}

    # Preparer les donnees
    data_summary = []
    for b in bilans[-12:]:  # Max 12 semaines
        data_summary.append({
            "semaine": b.get("week_number"),
            "poids": b.get("poids"),
            "energie": b.get("energie"),
            "sommeil": b.get("sommeil_qualite"),
            "motivation": b.get("motivation"),
            "seances": f"{b.get('seances_faites', 0)}/{b.get('seances_prevues', 0)}",
            "nutrition": b.get("respect_calories")
        })

    prompt = f"""Analyse la progression de ce client coaching:

CLIENT: {client_info.get('name', 'Client')}
Objectif: {client_info.get('objectif', 'Transformation')}
Debut: {client_info.get('date_debut', 'N/A')}

DONNEES ({len(data_summary)} semaines):
{json.dumps(data_summary, ensure_ascii=False)}

Genere un rapport JSON avec:
{{
    "resume_evolution": "Resume en 3-4 phrases de l'evolution globale",
    "tendance_poids": "Description tendance poids",
    "tendance_energie": "Description tendance energie",
    "points_forts_globaux": ["Force 1", "Force 2"],
    "axes_amelioration": ["Axe 1", "Axe 2"],
    "predictions": {{
        "4_semaines": "Prediction a 4 semaines",
        "objectif_final": "Probabilite atteinte objectif"
    }},
    "recommandations_coach": ["Reco 1", "Reco 2", "Reco 3"],
    "score_global": 7.5,
    "engagement_score": 8
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Parser JSON
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]

        start = response_text.find("{")
        end = response_text.rfind("}")
        if start != -1 and end != -1:
            response_text = response_text[start:end+1]

        return json.loads(response_text)

    except Exception as e:
        return {"error": str(e)}


def suggest_adjustments(bilan: Dict, client_info: Dict) -> List[str]:
    """
    Suggere des ajustements au programme (entrainement/nutrition)
    Base sur le bilan
    """

    prompt = f"""En tant que coach expert, analyse ce bilan et suggere des ajustements concrets:

CLIENT: {client_info.get('name', 'Client')}
Objectif: {client_info.get('objectif', 'Transformation')}

BILAN:
- Energie: {bilan.get('energie', '?')}/10
- Sommeil: {bilan.get('sommeil_qualite', '?')}/10 ({bilan.get('sommeil_heures', '?')}h)
- Stress: {bilan.get('stress', '?')}/10
- Faim: {bilan.get('faim', '?')}/10
- Seances: {bilan.get('seances_faites', '?')}/{bilan.get('seances_prevues', '?')}
- Difficultes training: {bilan.get('difficultes_training', 'N/A')}
- Respect nutrition: {bilan.get('respect_calories', '?')}/10
- Ecarts: {bilan.get('nombre_ecarts', '?')}

Genere 3-5 ajustements CONCRETS et ACTIONABLES.
Format JSON: {{"adjustements": ["Ajustement 1", "Ajustement 2", ...]}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        if "{" in response_text:
            start = response_text.find("{")
            end = response_text.rfind("}")
            data = json.loads(response_text[start:end+1])
            return data.get("adjustements", [])

        return []

    except Exception as e:
        return [f"Erreur: {e}"]


# Test
if __name__ == "__main__":
    test_bilan = {
        "week_number": 5,
        "poids": 78.5,
        "energie": 7,
        "sommeil_qualite": 6,
        "sommeil_heures": 7,
        "motivation": 8,
        "stress": 4,
        "seances_prevues": 4,
        "seances_faites": 4,
        "respect_calories": 7,
        "victoires": "J'ai tenu toutes mes seances cette semaine malgre la fatigue",
        "questions": "Est-ce normal d'avoir plus faim ces derniers jours?"
    }

    test_client = {
        "name": "Thomas",
        "objectif": "perte_gras",
        "date_debut": "2024-01-15",
        "duree_semaines": 12
    }

    result = analyze_client_bilan(test_bilan, test_client)
    print(json.dumps(result, indent=2, ensure_ascii=False))
