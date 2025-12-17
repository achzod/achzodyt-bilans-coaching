"""
Generateur de Dashboard HTML Evolution Client
Design moderne avec graphiques et analytics
"""

import json
from datetime import datetime
from typing import Dict, List, Any
import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def generate_improve_list(items):
    """Helper pour generer la liste des points a ameliorer"""
    html = ""
    for item in items[:5]:
        if isinstance(item, dict):
            priority = item.get("priority", "medium")
            priority_class = priority.replace("haute", "high").replace("moyenne", "medium").replace("basse", "low")
            area = item.get("area", str(item))
            html += f'<li><span class="badge badge-{priority_class}">{priority}</span><span>{area}</span></li>'
        else:
            html += f'<li><span>{item}</span></li>'
    return html if html else '<li>Aucun point a ameliorer</li>'


def generate_list_items(items, icon="✓", default="Aucune donnee", limit=5):
    """Helper generique pour generer des items de liste HTML"""
    if not items:
        return f'<li><span class="list-icon">{icon}</span><span>{default}</span></li>'
    html = ""
    for item in items[:limit]:
        html += f'<li><span class="list-icon">{icon}</span><span>{item}</span></li>'
    return html


def generate_client_dashboard(client_email: str, conversation_history: List[Dict], analyses: List[Dict] = None) -> str:
    """
    Genere un dashboard HTML complet d'evolution du client
    Analyse l'historique complet et genere des insights
    """

    # Preparer les donnees pour l'analyse IA
    history_summary = []
    for email in conversation_history[-30:]:  # Max 30 emails
        history_summary.append({
            "date": email.get("date").strftime("%Y-%m-%d") if email.get("date") else "",
            "direction": email.get("direction", "received"),
            "subject": email.get("subject", "")[:100],
            "body_preview": email.get("body", "")[:500]
        })

    # Demander a l'IA d'analyser l'evolution complete
    prompt = f"""Analyse l'historique complet de ce client coaching et genere un rapport JSON detaille.

CLIENT: {client_email}
HISTORIQUE ({len(history_summary)} emails):
{json.dumps(history_summary, ensure_ascii=False, indent=2)}

Genere un JSON avec cette structure EXACTE (tous les champs obligatoires):
{{
    "client_name": "Prenom du client (extrait des emails)",
    "coaching_start": "Date debut estimee (YYYY-MM-DD)",
    "total_weeks": nombre_semaines_de_suivi,
    "objective": "Objectif principal du client",

    "physical_evolution": {{
        "starting_weight": "Poids debut si mentionne",
        "current_weight": "Poids actuel si mentionne",
        "weight_change": "Evolution en kg",
        "body_fat_start": "% masse grasse debut",
        "body_fat_current": "% masse grasse actuel",
        "muscle_mass_evolution": "Description evolution musculaire"
    }},

    "weekly_scores": [
        {{"week": 1, "training": 8, "nutrition": 7, "sleep": 6, "energy": 7, "mindset": 8}},
        ...
    ],

    "key_achievements": [
        "Achievement 1 avec date",
        "Achievement 2 avec date",
        ...
    ],

    "challenges_overcome": [
        "Challenge 1 et comment resolu",
        ...
    ],

    "current_strengths": [
        "Force 1",
        "Force 2",
        ...
    ],

    "areas_to_improve": [
        {{"area": "Zone a ameliorer", "priority": "haute/moyenne/basse", "action": "Action recommandee"}},
        ...
    ],

    "nutrition_habits": {{
        "adherence_score": 8,
        "strengths": ["Point fort 1", "Point fort 2"],
        "weaknesses": ["Point faible 1"],
        "recommendations": ["Recommandation 1"]
    }},

    "training_analysis": {{
        "frequency": "X fois/semaine",
        "consistency_score": 8,
        "favorite_exercises": ["Exo 1", "Exo 2"],
        "progress_areas": ["Zone en progres"],
        "technique_notes": "Notes sur la technique"
    }},

    "lifestyle_factors": {{
        "sleep_quality": 7,
        "stress_level": 5,
        "hydration": 7,
        "recovery": 6
    }},

    "photos_analysis": {{
        "total_photos_received": nombre,
        "visible_changes": ["Changement visible 1", "Changement visible 2"],
        "muscle_groups_improved": ["Groupe 1", "Groupe 2"],
        "areas_needing_work": ["Zone 1"]
    }},

    "motivation_level": {{
        "current": 8,
        "trend": "stable/hausse/baisse",
        "factors": ["Facteur motivant 1"]
    }},

    "predictions": {{
        "expected_results_4_weeks": "Prediction a 4 semaines",
        "expected_results_12_weeks": "Prediction a 12 semaines",
        "potential_obstacles": ["Obstacle potentiel 1"]
    }},

    "coach_recommendations": [
        "Recommandation prioritaire 1",
        "Recommandation 2",
        "Recommandation 3"
    ],

    "overall_progress_score": 7.5,
    "client_engagement_score": 8,
    "transformation_potential": "Description du potentiel"
}}

Base-toi sur les donnees reelles des emails. Si une info n'est pas disponible, fais une estimation raisonnable ou mets "N/A".
Reponds UNIQUEMENT avec le JSON, sans texte avant ou apres."""

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

        data = json.loads(response_text)

    except Exception as e:
        print(f"Erreur analyse dashboard: {e}")
        # Donnees par defaut
        data = {
            "client_name": client_email.split("@")[0].title(),
            "coaching_start": datetime.now().strftime("%Y-%m-%d"),
            "total_weeks": len(conversation_history) // 2,
            "objective": "Transformation physique",
            "physical_evolution": {},
            "weekly_scores": [],
            "key_achievements": [],
            "challenges_overcome": [],
            "current_strengths": [],
            "areas_to_improve": [],
            "nutrition_habits": {"adherence_score": 7, "strengths": [], "weaknesses": [], "recommendations": []},
            "training_analysis": {"frequency": "N/A", "consistency_score": 7},
            "lifestyle_factors": {"sleep_quality": 7, "stress_level": 5, "hydration": 7, "recovery": 6},
            "photos_analysis": {"total_photos_received": 0, "visible_changes": []},
            "motivation_level": {"current": 7, "trend": "stable"},
            "predictions": {},
            "coach_recommendations": [],
            "overall_progress_score": 7,
            "client_engagement_score": 7,
            "transformation_potential": "A evaluer"
        }

    # Generer le HTML
    return _generate_html(data, client_email, len(conversation_history))


def _generate_html(data: Dict, client_email: str, total_emails: int) -> str:
    """Genere le HTML du dashboard"""

    # Preparer les donnees pour les graphiques
    weekly_scores = data.get("weekly_scores", [])
    weeks_labels = [f"S{s.get('week', i+1)}" for i, s in enumerate(weekly_scores)]
    training_data = [s.get("training", 7) for s in weekly_scores]
    nutrition_data = [s.get("nutrition", 7) for s in weekly_scores]
    energy_data = [s.get("energy", 7) for s in weekly_scores]

    # Lifestyle radar data
    lifestyle = data.get("lifestyle_factors", {})
    radar_data = [
        lifestyle.get("sleep_quality", 7),
        lifestyle.get("stress_level", 5),
        lifestyle.get("hydration", 7),
        lifestyle.get("recovery", 6),
        data.get("motivation_level", {}).get("current", 7)
    ]

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Evolution - {data.get("client_name", client_email)}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f0f1e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }}

        .dashboard {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        .header {{
            text-align: center;
            padding: 30px;
            background: linear-gradient(135deg, rgba(153, 144, 234, 0.2), rgba(141, 255, 224, 0.1));
            border-radius: 20px;
            margin-bottom: 30px;
            border: 1px solid rgba(153, 144, 234, 0.3);
        }}

        .header h1 {{
            font-size: 2.5rem;
            background: linear-gradient(135deg, #9990EA, #8DFFE0);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}

        .header .subtitle {{
            color: #8DFFE0;
            font-size: 1.2rem;
        }}

        .meta-info {{
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-top: 20px;
            flex-wrap: wrap;
        }}

        .meta-item {{
            text-align: center;
        }}

        .meta-value {{
            font-size: 1.8rem;
            font-weight: bold;
            color: #9990EA;
        }}

        .meta-label {{
            font-size: 0.9rem;
            color: #888;
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .card {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
        }}

        .card-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
        }}

        .card-icon {{
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
        }}

        .card-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #fff;
        }}

        .score-big {{
            font-size: 3rem;
            font-weight: bold;
            text-align: center;
            margin: 20px 0;
        }}

        .score-green {{ color: #8DFFE0; }}
        .score-yellow {{ color: #FFD93D; }}
        .score-red {{ color: #FF6B6B; }}

        .progress-bar {{
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            overflow: hidden;
            margin: 10px 0;
        }}

        .progress-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s ease;
        }}

        .progress-green {{ background: linear-gradient(90deg, #8DFFE0, #4CAF50); }}
        .progress-purple {{ background: linear-gradient(90deg, #9990EA, #6B5BEA); }}

        .list {{
            list-style: none;
        }}

        .list li {{
            padding: 12px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            align-items: flex-start;
            gap: 10px;
        }}

        .list li:last-child {{
            border-bottom: none;
        }}

        .list-icon {{
            flex-shrink: 0;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}

        .badge-high {{ background: rgba(255, 107, 107, 0.2); color: #FF6B6B; }}
        .badge-medium {{ background: rgba(255, 217, 61, 0.2); color: #FFD93D; }}
        .badge-low {{ background: rgba(141, 255, 224, 0.2); color: #8DFFE0; }}

        .chart-container {{
            position: relative;
            height: 250px;
            margin-top: 20px;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }}

        .stat-item {{
            background: rgba(255, 255, 255, 0.03);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }}

        .stat-value {{
            font-size: 1.5rem;
            font-weight: bold;
            color: #9990EA;
        }}

        .stat-label {{
            font-size: 0.8rem;
            color: #888;
            margin-top: 5px;
        }}

        .evolution-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
        }}

        .evolution-label {{
            color: #888;
        }}

        .evolution-value {{
            font-weight: bold;
        }}

        .positive {{ color: #8DFFE0; }}
        .negative {{ color: #FF6B6B; }}

        .recommendations {{
            background: linear-gradient(135deg, rgba(153, 144, 234, 0.1), rgba(141, 255, 224, 0.05));
            border-left: 4px solid #9990EA;
        }}

        .wide-card {{
            grid-column: span 2;
        }}

        @media (max-width: 768px) {{
            .wide-card {{
                grid-column: span 1;
            }}
            .header h1 {{
                font-size: 1.8rem;
            }}
            .meta-info {{
                gap: 20px;
            }}
        }}

        .footer {{
            text-align: center;
            padding: 30px;
            color: #666;
            font-size: 0.9rem;
        }}

        .footer strong {{
            color: #9990EA;
        }}
    </style>
</head>
<body>
    <div class="dashboard">
        <!-- Header -->
        <div class="header">
            <h1>🏆 Dashboard Evolution</h1>
            <p class="subtitle">{data.get("client_name", client_email)}</p>
            <div class="meta-info">
                <div class="meta-item">
                    <div class="meta-value">{data.get("total_weeks", "N/A")}</div>
                    <div class="meta-label">Semaines de suivi</div>
                </div>
                <div class="meta-item">
                    <div class="meta-value">{total_emails}</div>
                    <div class="meta-label">Emails echanges</div>
                </div>
                <div class="meta-item">
                    <div class="meta-value">{data.get("overall_progress_score", 7)}/10</div>
                    <div class="meta-label">Score global</div>
                </div>
                <div class="meta-item">
                    <div class="meta-value">{data.get("client_engagement_score", 7)}/10</div>
                    <div class="meta-label">Engagement</div>
                </div>
            </div>
        </div>

        <!-- Main Grid -->
        <div class="grid">
            <!-- Score Global -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(141, 255, 224, 0.2);">📊</div>
                    <div class="card-title">Progression Globale</div>
                </div>
                <div class="score-big {'score-green' if data.get('overall_progress_score', 7) >= 7 else 'score-yellow' if data.get('overall_progress_score', 7) >= 5 else 'score-red'}">
                    {data.get("overall_progress_score", 7)}<span style="font-size: 1.5rem; color: #888;">/10</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill progress-green" style="width: {data.get('overall_progress_score', 7) * 10}%;"></div>
                </div>
                <p style="text-align: center; color: #888; margin-top: 15px;">
                    {data.get("transformation_potential", "Potentiel de transformation excellent")}
                </p>
            </div>

            <!-- Evolution Physique -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(153, 144, 234, 0.2);">💪</div>
                    <div class="card-title">Evolution Physique</div>
                </div>
                <div class="evolution-item">
                    <span class="evolution-label">Poids depart</span>
                    <span class="evolution-value">{data.get("physical_evolution", {}).get("starting_weight", "N/A")}</span>
                </div>
                <div class="evolution-item">
                    <span class="evolution-label">Poids actuel</span>
                    <span class="evolution-value">{data.get("physical_evolution", {}).get("current_weight", "N/A")}</span>
                </div>
                <div class="evolution-item">
                    <span class="evolution-label">Evolution</span>
                    <span class="evolution-value positive">{data.get("physical_evolution", {}).get("weight_change", "N/A")}</span>
                </div>
                <div class="evolution-item">
                    <span class="evolution-label">Masse grasse</span>
                    <span class="evolution-value">{data.get("physical_evolution", {}).get("body_fat_current", "N/A")}</span>
                </div>
            </div>

            <!-- Graphique Evolution -->
            <div class="card wide-card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(255, 217, 61, 0.2);">📈</div>
                    <div class="card-title">Evolution Hebdomadaire</div>
                </div>
                <div class="chart-container">
                    <canvas id="weeklyChart"></canvas>
                </div>
            </div>

            <!-- Achievements -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(141, 255, 224, 0.2);">🏆</div>
                    <div class="card-title">Victoires</div>
                </div>
                <ul class="list">
                    {generate_list_items(data.get("key_achievements", []), "✅", "Aucune victoire", 5)}
                </ul>
            </div>

            <!-- Points Forts -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(76, 175, 80, 0.2);">💚</div>
                    <div class="card-title">Points Forts</div>
                </div>
                <ul class="list">
                    {generate_list_items(data.get("current_strengths", []), "💪", "Aucun point fort", 5)}
                </ul>
            </div>

            <!-- Nutrition -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(255, 152, 0, 0.2);">🍎</div>
                    <div class="card-title">Nutrition</div>
                </div>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value">{data.get("nutrition_habits", {}).get("adherence_score", 7)}/10</div>
                        <div class="stat-label">Adherence</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{len(data.get("nutrition_habits", {}).get("strengths", []))}</div>
                        <div class="stat-label">Points forts</div>
                    </div>
                </div>
                <ul class="list" style="margin-top: 15px;">
                    {generate_list_items(data.get("nutrition_habits", {}).get("strengths", []), "✓", "Aucune donnee", 3)}
                </ul>
            </div>

            <!-- Training -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(233, 30, 99, 0.2);">🏋️</div>
                    <div class="card-title">Entrainement</div>
                </div>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value">{data.get("training_analysis", {}).get("frequency", "N/A")}</div>
                        <div class="stat-label">Frequence</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{data.get("training_analysis", {}).get("consistency_score", 7)}/10</div>
                        <div class="stat-label">Regularite</div>
                    </div>
                </div>
                <p style="margin-top: 15px; color: #888;">
                    {data.get("training_analysis", {}).get("technique_notes", "Continue comme ca!")}
                </p>
            </div>

            <!-- Lifestyle Radar -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(103, 58, 183, 0.2);">🌙</div>
                    <div class="card-title">Mode de Vie</div>
                </div>
                <div class="chart-container" style="height: 200px;">
                    <canvas id="lifestyleChart"></canvas>
                </div>
            </div>

            <!-- Photos Analysis -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(0, 188, 212, 0.2);">📸</div>
                    <div class="card-title">Analyse Photos</div>
                </div>
                <div class="stat-item" style="margin-bottom: 15px;">
                    <div class="stat-value">{data.get("photos_analysis", {}).get("total_photos_received", 0)}</div>
                    <div class="stat-label">Photos recues</div>
                </div>
                <p style="font-weight: 600; margin-bottom: 10px;">Changements visibles:</p>
                <ul class="list">
                    {generate_list_items(data.get("photos_analysis", {}).get("visible_changes", []), "👁️", "Aucun changement", 4)}
                </ul>
            </div>

            <!-- Motivation -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(255, 193, 7, 0.2);">🔥</div>
                    <div class="card-title">Motivation</div>
                </div>
                <div class="score-big score-yellow" style="font-size: 2.5rem;">
                    {data.get("motivation_level", {}).get("current", 7)}<span style="font-size: 1rem; color: #888;">/10</span>
                </div>
                <p style="text-align: center;">
                    Tendance: <span class="{'positive' if data.get('motivation_level', {}).get('trend') == 'hausse' else 'negative' if data.get('motivation_level', {}).get('trend') == 'baisse' else ''}">{data.get("motivation_level", {}).get("trend", "stable")}</span>
                </p>
            </div>

            <!-- A Ameliorer -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(255, 107, 107, 0.2);">🎯</div>
                    <div class="card-title">Points a Ameliorer</div>
                </div>
                <ul class="list">
                    {generate_improve_list(data.get("areas_to_improve", []))}
                </ul>
            </div>

            <!-- Predictions -->
            <div class="card">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(156, 39, 176, 0.2);">🔮</div>
                    <div class="card-title">Predictions</div>
                </div>
                <div style="margin-bottom: 15px;">
                    <p style="color: #9990EA; font-weight: 600;">Dans 4 semaines:</p>
                    <p style="color: #888;">{data.get("predictions", {}).get("expected_results_4_weeks", "N/A")}</p>
                </div>
                <div>
                    <p style="color: #8DFFE0; font-weight: 600;">Dans 12 semaines:</p>
                    <p style="color: #888;">{data.get("predictions", {}).get("expected_results_12_weeks", "N/A")}</p>
                </div>
            </div>

            <!-- Recommandations Coach -->
            <div class="card wide-card recommendations">
                <div class="card-header">
                    <div class="card-icon" style="background: rgba(153, 144, 234, 0.3);">💡</div>
                    <div class="card-title">Recommandations du Coach</div>
                </div>
                <ul class="list">
                    {generate_list_items(data.get("coach_recommendations", []), "➡️", "Aucune recommandation", 6)}
                </ul>
            </div>
        </div>

        <!-- Footer -->
        <div class="footer">
            <p>Dashboard genere le {datetime.now().strftime("%d/%m/%Y a %H:%M")}</p>
            <p>Par <strong>Achzod Coaching</strong></p>
        </div>
    </div>

    <script>
        // Weekly Evolution Chart
        const weeklyCtx = document.getElementById('weeklyChart').getContext('2d');
        new Chart(weeklyCtx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(weeks_labels if weeks_labels else ['S1', 'S2', 'S3', 'S4'])},
                datasets: [
                    {{
                        label: 'Training',
                        data: {json.dumps(training_data if training_data else [7, 7, 8, 8])},
                        borderColor: '#9990EA',
                        backgroundColor: 'rgba(153, 144, 234, 0.1)',
                        fill: true,
                        tension: 0.4
                    }},
                    {{
                        label: 'Nutrition',
                        data: {json.dumps(nutrition_data if nutrition_data else [6, 7, 7, 8])},
                        borderColor: '#8DFFE0',
                        backgroundColor: 'rgba(141, 255, 224, 0.1)',
                        fill: true,
                        tension: 0.4
                    }},
                    {{
                        label: 'Energie',
                        data: {json.dumps(energy_data if energy_data else [7, 6, 7, 8])},
                        borderColor: '#FFD93D',
                        backgroundColor: 'rgba(255, 217, 61, 0.1)',
                        fill: true,
                        tension: 0.4
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        labels: {{ color: '#888' }}
                    }}
                }},
                scales: {{
                    y: {{
                        min: 0,
                        max: 10,
                        grid: {{ color: 'rgba(255,255,255,0.05)' }},
                        ticks: {{ color: '#888' }}
                    }},
                    x: {{
                        grid: {{ color: 'rgba(255,255,255,0.05)' }},
                        ticks: {{ color: '#888' }}
                    }}
                }}
            }}
        }});

        // Lifestyle Radar Chart
        const lifestyleCtx = document.getElementById('lifestyleChart').getContext('2d');
        new Chart(lifestyleCtx, {{
            type: 'radar',
            data: {{
                labels: ['Sommeil', 'Stress (inv)', 'Hydratation', 'Recuperation', 'Motivation'],
                datasets: [{{
                    label: 'Score',
                    data: {json.dumps(radar_data)},
                    borderColor: '#9990EA',
                    backgroundColor: 'rgba(153, 144, 234, 0.2)',
                    pointBackgroundColor: '#9990EA'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    r: {{
                        min: 0,
                        max: 10,
                        grid: {{ color: 'rgba(255,255,255,0.1)' }},
                        angleLines: {{ color: 'rgba(255,255,255,0.1)' }},
                        pointLabels: {{ color: '#888' }},
                        ticks: {{ display: false }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>'''

    return html
