"""
Module d'analyse IA des bilans de coaching avec Claude
Analyse COMPLETE: photos, metriques, questions, evolution physique, KPIs
"""

import os
import base64
import json
from typing import List, Dict, Any, Optional
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def analyze_coaching_bilan(
    current_email: Dict[str, Any],
    conversation_history: List[Dict[str, Any]],
    client_name: str = ""
) -> Dict[str, Any]:
    """
    Analyse ULTRA COMPLETE d'un bilan de coaching:
    - Analyse des photos (composition corporelle, evolution visuelle)
    - Evolution physique (metriques, poids, mesures)
    - Reponses a TOUTES les questions du client
    - KPIs detailles
    - Points a ameliorer avec conseils precis
    - Email de reponse personnalise
    """

    # Construction du contexte historique
    history_text = _build_history_context(conversation_history)

    # Compter les photos
    photos = [att for att in current_email.get("attachments", []) if att["content_type"].startswith("image/")]
    pdfs = [att for att in current_email.get("attachments", []) if "pdf" in att["content_type"].lower()]

    # Preparation du message avec images
    content = []

    # Prompt ULTRA DETAILLE
    prompt = f"""Tu es Achzod, coach expert reconnu en transformation physique, optimisation hormonale et performance.

Tu recois un bilan de coaching. Tu dois faire une analyse COMPLETE et DETAILLEE.

## HISTORIQUE DE LA CONVERSATION AVEC CE CLIENT
{history_text}

## BILAN ACTUEL
Date: {current_email['date'].strftime('%d/%m/%Y %H:%M') if current_email.get('date') else 'N/A'}
Sujet: {current_email.get('subject', 'Sans sujet')}

Message du client:
\"\"\"
{current_email.get('body', '')}
\"\"\"

Pieces jointes: {len(photos)} photo(s), {len(pdfs)} PDF(s)

---

## TA MISSION - ANALYSE ULTRA COMPLETE

### 1. ANALYSE DES PHOTOS (SI PRESENTES)
Si le client a envoye des photos, analyse EN DETAIL:
- **Composition corporelle**: estimation du taux de masse grasse actuel (%), masse musculaire visible
- **Zones musculaires**: developpement des epaules, pectoraux, bras, dos, abdos, jambes
- **Points forts visuels**: quelles zones sont bien developpees
- **Zones a travailler**: quelles zones manquent de developpement ou de definition
- **Qualite de la peau**: retention d'eau, cellulite, vergetures
- **Posture**: alignement, desequilibres visibles
- **Evolution vs historique**: si tu as des photos precedentes, compare l'evolution
- **Estimation de progression**: X% d'amelioration visuelle depuis le debut

### 2. ANALYSE DES METRIQUES
Extrais TOUTES les donnees mentionnees:
- Poids actuel et evolution
- Mensurations (tour de taille, bras, cuisses, etc.)
- Performances a l'entrainement (charges, reps, PRs)
- Donnees de sommeil (duree, qualite)
- Niveau d'energie
- Faim, digestion, transit
- Libido, humeur, motivation
- Toute autre metrique mentionnee

### 3. REPONSES AUX QUESTIONS
IDENTIFIE et REPONDS a CHAQUE question posee par le client:
- Reponds de maniere precise, technique mais accessible
- Donne des recommandations concretes et actionnables
- Si c'est une question sur un exercice, propose des alternatives
- Si c'est une question sur la nutrition, donne des ajustements precis
- Si c'est une question sur la sante, reste prudent et recommande un medecin si necessaire

### 4. KPIs DETAILLES (note sur 10 avec justification)
- Adherence entrainement: combien de seances faites vs prevues
- Adherence nutrition: respect du plan alimentaire
- Qualite sommeil: duree + qualite du sommeil
- Niveau energie: energie generale au quotidien
- Progression globale: resultat global de la semaine/periode
- Regularite: constance dans l'effort
- Mindset: attitude mentale, motivation

### 5. POINTS POSITIFS A SOULIGNER
Liste TOUS les progres et reussites, meme petits:
- Victoires de la semaine
- Habitudes positives maintenues
- Progres physiques ou mentaux
- Efforts remarquables

### 6. POINTS A AMELIORER (avec solutions concretes)
Pour chaque point faible, donne:
- Le probleme identifie
- Pourquoi c'est important
- La solution concrete a appliquer
- Le resultat attendu

### 7. AJUSTEMENTS PROGRAMME
Si necessaire, propose des ajustements:
- Modifications du programme d'entrainement
- Ajustements nutritionnels
- Changements dans la routine de sommeil/recuperation
- Ajout ou retrait de supplements

### 8. EMAIL DE REPONSE COMPLET
Redige un email de reponse COMPLET et PERSONNALISE:

Structure de l'email:
1. Salutation personnalisee
2. Accuse reception du bilan avec enthousiasme
3. Feedback sur les photos (si presentes) - sois precis sur ce que tu vois
4. Analyse des metriques et de l'evolution
5. Points positifs a celebrer
6. Reponses a TOUTES ses questions (une par une)
7. Points a ameliorer avec conseils actionables
8. Ajustements programme si necessaire
9. Objectifs pour la prochaine periode
10. Motivation et encouragements
11. Signature

Ton style d'ecriture:
- Direct et sans bullshit
- Expert mais accessible
- Bienveillant mais honnete
- Motivant sans etre "cheerleader"
- Tutoiement
- Emojis ok mais pas trop

---

REPONDS EN JSON VALIDE avec cette structure exacte:
{{
    "resume": "Resume complet du bilan en 3-4 phrases",
    "analyse_photos": {{
        "masse_grasse_estimee": "X%",
        "masse_musculaire": "Description",
        "points_forts": ["zone1", "zone2"],
        "zones_a_travailler": ["zone1", "zone2"],
        "evolution_visuelle": "Description de l'evolution",
        "note_physique": 7
    }},
    "metriques": {{
        "poids": "Xkg (evolution)",
        "energie": "X/10",
        "sommeil": "Xh - qualite",
        "autres": ["metrique1", "metrique2"]
    }},
    "evolution": {{
        "poids": "Evolution du poids",
        "energie": "Evolution energie",
        "performance": "Evolution perfs",
        "adherence": "Niveau d'adherence",
        "global": "Evolution globale"
    }},
    "kpis": {{
        "adherence_training": 8,
        "adherence_nutrition": 7,
        "sommeil": 6,
        "energie": 7,
        "progression": 8
    }},
    "points_positifs": ["Point 1 detaille", "Point 2 detaille"],
    "points_ameliorer": [
        {{"probleme": "...", "solution": "...", "priorite": "haute/moyenne/basse"}}
    ],
    "questions_reponses": [
        {{"question": "Question du client", "reponse": "Ta reponse detaillee"}}
    ],
    "ajustements": ["Ajustement 1", "Ajustement 2"],
    "draft_email": "Email complet ici..."
}}"""

    content.append({"type": "text", "text": prompt})

    # Ajout des images (jusqu'a 10 photos) - formats acceptes par Claude
    VALID_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    images_added = 0
    for att in current_email.get("attachments", []):
        if att["content_type"].startswith("image/") and images_added < 10:
            try:
                # Normaliser le media_type (ex: image/jpg -> image/jpeg)
                media_type = att["content_type"].lower()
                if media_type == "image/jpg":
                    media_type = "image/jpeg"
                
                # Skip si type non supporte
                if media_type not in VALID_IMAGE_TYPES:
                    print(f"Image ignoree: {media_type} non supporte")
                    continue
                    
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": att["data"]
                    }
                })
                images_added += 1
            except Exception as img_err:
                print(f"Erreur image: {img_err}")
                pass

    if images_added > 0:
        content.append({
            "type": "text",
            "text": f"""

⬆️ {images_added} PHOTO(S) DU CLIENT CI-DESSUS ⬆️

ANALYSE CES PHOTOS EN DETAIL:
- Evalue la composition corporelle (masse grasse %, masse musculaire)
- Identifie les groupes musculaires bien developpes
- Identifie les zones a travailler
- Note la qualite de la peau, retention d'eau eventuelle
- Compare avec l'historique si disponible
- Donne une note physique sur 10

Sois PRECIS et HONNETE dans ton analyse visuelle."""
        })

    # Appel Claude avec plus de tokens
    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=8000,
            messages=[{"role": "user", "content": content}]
        )

        response_text = response.content[0].text

        # Parse JSON
        try:
            json_match = response_text
            if "```json" in response_text:
                json_match = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                parts = response_text.split("```")
                for part in parts:
                    if "{" in part and "}" in part:
                        json_match = part
                        break

            analysis = json.loads(json_match.strip())

            # S'assurer que toutes les cles existent
            defaults = {
                "resume": "",
                "analyse_photos": {},
                "metriques": {},
                "evolution": {},
                "kpis": {"adherence_training": 7, "adherence_nutrition": 7, "sommeil": 7, "energie": 7, "progression": 7},
                "points_positifs": [],
                "points_ameliorer": [],
                "questions_reponses": [],
                "ajustements": [],
                "draft_email": ""
            }
            for key, default in defaults.items():
                if key not in analysis:
                    analysis[key] = default

        except Exception as parse_error:
            print(f"Erreur parsing JSON: {parse_error}")
            # Fallback: utiliser la reponse brute
            analysis = {
                "resume": "Analyse complete disponible",
                "analyse_photos": {},
                "metriques": {},
                "evolution": {},
                "kpis": {
                    "adherence_training": 7,
                    "adherence_nutrition": 7,
                    "sommeil": 7,
                    "energie": 7,
                    "progression": 7
                },
                "points_positifs": [],
                "points_ameliorer": [],
                "questions_reponses": [],
                "ajustements": [],
                "draft_email": response_text
            }

        return {
            "success": True,
            "analysis": analysis,
            "raw_response": response_text,
            "photos_analyzed": images_added
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "analysis": None
        }


def _build_history_context(history: List[Dict[str, Any]]) -> str:
    """Construit le contexte historique COMPLET pour l'analyse"""
    if not history:
        return "Aucun historique disponible (premier contact ou historique non charge). Traite ce bilan comme un premier contact."

    context_parts = []
    context_parts.append(f"=== {len(history)} EMAILS DANS L'HISTORIQUE ===\n")

    for i, email_data in enumerate(history[-15:], 1):  # Max 15 derniers emails
        direction = "📥 CLIENT" if email_data.get("direction") == "received" else "📤 TOI (Achzod)"
        date = email_data.get("date")
        date_str = date.strftime("%d/%m/%Y %H:%M") if date else "?"
        subject = email_data.get("subject", "Sans sujet")
        body = email_data.get("body", "")[:800]  # Plus de contexte
        attachments = len(email_data.get("attachments", []))
        att_info = f" | {attachments} piece(s) jointe(s)" if attachments else ""

        context_parts.append(f"""
--- EMAIL {i}: {direction} ({date_str}){att_info} ---
Sujet: {subject}
{body}
""")

    return "\n".join(context_parts)


def regenerate_email_draft(
    analysis: Dict[str, Any],
    instructions: str,
    current_draft: str
) -> str:
    """
    Regenere le draft d'email avec des instructions specifiques
    """
    prompt = f"""Tu es Achzod, coach expert en transformation physique.

Voici l'analyse complete du bilan:
{json.dumps(analysis, indent=2, ensure_ascii=False)}

Draft actuel de l'email:
\"\"\"
{current_draft}
\"\"\"

INSTRUCTIONS DE MODIFICATION:
{instructions}

REECRIS l'email en tenant compte des instructions.
Garde le style Achzod: direct, expert, bienveillant, pas de bullshit.
Tutoiement, emojis ok.

Retourne UNIQUEMENT le nouveau texte de l'email, rien d'autre."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return f"Erreur: {e}"


# Test
if __name__ == "__main__":
    test_email = {
        "date": None,
        "subject": "Bilan semaine 3",
        "body": """Salut Achzod,

Voici mon bilan de la semaine:
- Poids: 82kg (vs 84kg semaine derniere)
- 4 seances faites sur 5 prevues
- Sommeil moyen 6h30
- Energie en hausse depuis mercredi

J'ai eu du mal avec le leg day, mes genoux me font un peu mal.
Question: je peux remplacer les squats par autre chose?
Aussi, est-ce que je dois augmenter les proteines?

A+
Marc""",
        "attachments": []
    }

    result = analyze_coaching_bilan(test_email, [])
    print(json.dumps(result, indent=2, ensure_ascii=False))
