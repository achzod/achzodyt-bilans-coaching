"""
Interface Streamlit pour la gestion des bilans coaching
"""

import streamlit as st
import base64
from datetime import datetime
from email_reader import EmailReader
from analyzer import analyze_coaching_bilan, regenerate_email_draft
from email_sender import send_email, preview_email
from clients import get_client, save_client, get_jours_restants

# Config page
st.set_page_config(
    page_title="Achzod - Bilans Coaching",
    page_icon="💪",
    layout="wide"
)

# CSS custom
st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: bold; color: #9990EA; margin-bottom: 1rem; }
    .bilan-card { background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #9990EA; white-space: pre-wrap; }
    .kpi-box { background: linear-gradient(135deg, #9990EA 0%, #8DFFE0 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; }
    .kpi-value { font-size: 2rem; font-weight: bold; }
    .kpi-label { font-size: 0.9rem; opacity: 0.9; }
    .positive { color: #28a745; }
    .negative { color: #dc3545; }
    .email-preview { background: white; padding: 20px; border-radius: 8px; border: 1px solid #ddd; }
    .history-item { padding: 10px; margin: 5px 0; border-radius: 5px; }
    .history-received { background: #e3f2fd; border-left: 3px solid #2196f3; }
    .history-sent { background: #f3e5f5; border-left: 3px solid #9c27b0; }
    .status-ok { color: #28a745; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Init session state
if 'reader' not in st.session_state:
    st.session_state.reader = None
if 'connected' not in st.session_state:
    st.session_state.connected = False
if 'emails' not in st.session_state:
    st.session_state.emails = []
if 'selected_email' not in st.session_state:
    st.session_state.selected_email = None
if 'analysis' not in st.session_state:
    st.session_state.analysis = None
if 'history' not in st.session_state:
    st.session_state.history = []
if 'draft' not in st.session_state:
    st.session_state.draft = ""


def generate_kpi_table(kpis: dict) -> str:
    """Genere un tableau texte des KPIs pour l'email"""
    if not kpis:
        return ""

    kpi_names = {
        "adherence_training": "Entrainement",
        "adherence_nutrition": "Nutrition",
        "sommeil": "Sommeil",
        "energie": "Energie",
        "progression": "Progression"
    }

    lines = [
        "",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📊 TES KPIs DE LA SEMAINE",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ""
    ]

    for key, name in kpi_names.items():
        value = kpis.get(key, 0)
        # Barre de progression en texte
        filled = "█" * value
        empty = "░" * (10 - value)
        bar = filled + empty

        # Emoji selon le score
        if value >= 8:
            emoji = "🟢"
        elif value >= 6:
            emoji = "🟡"
        else:
            emoji = "🔴"

        lines.append(f"{emoji} {name:15} {bar} {value}/10")

    # Moyenne
    values = [kpis.get(k, 0) for k in kpi_names.keys()]
    avg = sum(values) / len(values) if values else 0

    lines.append("")
    lines.append(f"📈 Score global: {avg:.1f}/10")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    return "\n".join(lines)


def display_attachments(attachments):
    """Affiche les pieces jointes"""
    if not attachments:
        return

    cols = st.columns(min(len(attachments), 3))
    for i, att in enumerate(attachments[:6]):
        with cols[i % 3]:
            if att["content_type"].startswith("image/"):
                try:
                    img_data = base64.b64decode(att["data"])
                    st.image(img_data, caption=att["filename"], use_container_width=True)
                except:
                    st.write(f"📷 {att['filename']}")
            else:
                st.write(f"📎 {att['filename']} ({att['size']//1024}KB)")


def display_kpis(kpis):
    """Affiche les KPIs"""
    cols = st.columns(5)
    kpi_labels = {
        "adherence_training": "Training",
        "adherence_nutrition": "Nutrition",
        "sommeil": "Sommeil",
        "energie": "Energie",
        "progression": "Progression"
    }

    for i, (key, label) in enumerate(kpi_labels.items()):
        with cols[i]:
            value = kpis.get(key, 0)
            color = "#28a745" if value >= 7 else "#ffc107" if value >= 5 else "#dc3545"
            st.markdown(f"""
                <div style="text-align: center; padding: 10px; background: #f8f9fa; border-radius: 8px; border-top: 4px solid {color};">
                    <div style="font-size: 1.8rem; font-weight: bold; color: {color};">{value}/10</div>
                    <div style="font-size: 0.85rem; color: #666;">{label}</div>
                </div>
            """, unsafe_allow_html=True)


def main():
    st.markdown('<div class="main-header">💪 Bilans Coaching - Achzod</div>', unsafe_allow_html=True)

    # Sidebar - Connexion et liste emails
    with st.sidebar:
        st.header("📬 Emails")

        # Status connexion
        if st.session_state.connected:
            st.markdown('<span class="status-ok">✅ Gmail connecte</span>', unsafe_allow_html=True)

        # Bouton connexion
        col1, col2 = st.columns(2)
        with col1:
            connect_btn = st.button("🔄 Connecter", use_container_width=True)
        with col2:
            days = st.selectbox("Jours", [3, 7, 14, 30], index=1, label_visibility="collapsed")

        if connect_btn:
            with st.status("Chargement emails...", expanded=True) as status:
                if st.session_state.reader is None:
                    st.session_state.reader = EmailReader()
                    
                st.write("🔌 Connexion Gmail...")
                if st.session_state.reader.connect():
                    st.write("📬 Recherche emails sans reponse...")
                    st.write("⏳ Cela peut prendre 1-2 minutes pour charger tous les emails")
                    st.session_state.emails = st.session_state.reader.get_recent_emails(days=days, unanswered_only=True)
                    st.session_state.connected = True
                    status.update(label=f"✅ {len(st.session_state.emails)} emails charges!", state="complete", expanded=False)
                else:
                    status.update(label="❌ Erreur connexion", state="error")

        # Bouton rafraichir
        if st.session_state.connected:
            if st.button("🔃 Rafraichir", use_container_width=True):
                with st.spinner("Chargement..."):
                    st.session_state.emails = st.session_state.reader.get_recent_emails(days=days, unanswered_only=True)

        st.divider()

        # Liste des bilans (filtrer typeform et newsletters)
        EXCLUDE_PATTERNS = ['typeform', 'newsletter', 'noreply', 'no-reply', 'mailer-daemon', 'notification', 'followup', 'follow-up', 'unsubscribe', 'notifications']
        all_emails = [
            e for e in st.session_state.emails 
            if not any(p in e.get('from_email', '').lower() or p in e.get('subject', '').lower() 
                      for p in EXCLUDE_PATTERNS)
        ]
        st.subheader(f"📋 Sans reponse ({len(all_emails)})")

        for email_data in all_emails:
            date_str = email_data['date'].strftime('%d/%m %H:%M') if email_data.get('date') else ''
            attachments_count = len(email_data.get('attachments', []))
            att_icon = f" 📷{attachments_count}" if attachments_count else ""

            btn_label = f"{email_data['from_email'][:25]}\n{date_str}{att_icon}"

            if st.button(btn_label, key=f"email_{email_data['id']}", use_container_width=True):
                st.session_state.selected_email = email_data
                st.session_state.analysis = None
                st.session_state.draft = ""
                st.rerun()

    # Contenu principal
    if st.session_state.selected_email:
        email_data = st.session_state.selected_email

        # Lazy loading: charger contenu si pas encore fait
        if not email_data.get("loaded", True):
            with st.spinner("Chargement du contenu..."):
                content = st.session_state.reader.load_email_content(email_data["id"])
                if content:
                    email_data["body"] = content.get("body", "")
                    email_data["attachments"] = content.get("attachments", [])
                    email_data["loaded"] = True
                    st.session_state.selected_email = email_data

        # Header
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.subheader(f"📧 {email_data['subject']}")
            st.caption(f"De: {email_data['from']} | {email_data['date'].strftime('%d/%m/%Y %H:%M') if email_data.get('date') else ''}")
            
            # Infos client
            client_info = get_client(email_data['from_email'])
            if client_info:
                jours = get_jours_restants(client_info)
                color = "green" if jours > 14 else "orange" if jours > 0 else "red"
                st.markdown(f"**Commande:** {client_info.get('commande', 'N/A')} | **Jours restants:** :{color}[{jours}j]")
            else:
                st.caption("Client non enregistre")
            
            # Editer client
            with st.expander("Modifier infos client"):
                c_commande = st.text_input("Commande", value=client_info.get('commande', '') if client_info else '', key="c_cmd")
                c_date = st.date_input("Date debut", key="c_date")
                c_duree = st.number_input("Duree (semaines)", min_value=1, max_value=52, value=client_info.get('duree_semaines', 12) if client_info else 12, key="c_dur")
                if st.button("Sauvegarder client"):
                    save_client(email_data['from_email'], c_commande, c_date.strftime('%Y-%m-%d'), c_duree)
                    st.success("Client sauvegarde!")
                    st.rerun()
        with col2:
            if st.button("📜 Historique", use_container_width=True):
                with st.spinner("Chargement historique..."):
                    st.session_state.history = st.session_state.reader.get_conversation_history(
                        email_data['from_email'],
                        days=90
                    )
        with col3:
            if st.button("🤖 Analyser", type="primary", use_container_width=True):
                with st.status("Analyse IA en cours...", expanded=True) as status:
                    st.write("🔄 Chargement du contenu email...")
                    # S'assurer que le contenu est charge
                    if not email_data.get("loaded", True):
                        content_data = st.session_state.reader.load_email_content(email_data["id"])
                        if content_data:
                            email_data["body"] = content_data.get("body", "")
                            email_data["attachments"] = content_data.get("attachments", [])
                            email_data["loaded"] = True
                    
                    st.write(f"📧 Email: {len(email_data.get('body', ''))} chars, {len(email_data.get('attachments', []))} pieces jointes")
                    st.write("🤖 Appel Claude API...")
                    
                    result = analyze_coaching_bilan(
                        email_data,
                        st.session_state.history
                    )
                    
                    if result["success"]:
                        st.session_state.analysis = result["analysis"]
                        st.session_state.draft = result["analysis"].get("draft_email", "")
                        status.update(label="✅ Analyse terminee!", state="complete", expanded=False)
                        st.rerun()
                    else:
                        status.update(label="❌ Erreur", state="error")
                        st.error(f"Erreur: {result.get('error')}")

        # Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["📨 Email", "📜 Historique", "📊 Analyse", "✉️ Reponse"])

        # Tab 1: Email actuel
        with tab1:
            st.markdown(f'<div class="bilan-card">{email_data["body"]}</div>', unsafe_allow_html=True)

            if email_data.get("attachments"):
                st.subheader("📎 Pieces jointes")
                display_attachments(email_data["attachments"])

        # Tab 2: Historique conversation
        with tab2:
            if st.session_state.history:
                st.subheader(f"📜 Historique avec {email_data['from_email']}")
                st.caption(f"{len(st.session_state.history)} emails trouves")

                for hist_email in st.session_state.history:
                    direction = hist_email.get("direction", "received")
                    icon = "📥" if direction == "received" else "📤"
                    date_str = hist_email['date'].strftime('%d/%m/%Y') if hist_email.get('date') else ''

                    with st.expander(f"{icon} {date_str} - {hist_email['subject'][:50]}"):
                        st.write(hist_email.get("body", "")[:1000])
                        if hist_email.get("attachments"):
                            st.caption(f"📎 {len(hist_email['attachments'])} piece(s) jointe(s)")
            else:
                st.info("👆 Clique sur 'Historique' pour charger la conversation")

        # Tab 3: Analyse
        with tab3:
            if st.session_state.analysis:
                analysis = st.session_state.analysis

                # Resume en haut
                st.subheader("📝 Resume")
                st.info(analysis.get("resume", ""))

                # KPIs
                st.subheader("📊 KPIs")
                display_kpis(analysis.get("kpis", {}))

                st.divider()

                # Analyse Photos (si disponible)
                analyse_photos = analysis.get("analyse_photos", {})
                if analyse_photos:
                    st.subheader("📷 Analyse Physique (Photos)")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        mg = analyse_photos.get("masse_grasse_estimee", "N/A")
                        st.metric("Masse Grasse", mg)
                    with col2:
                        note = analyse_photos.get("note_physique", "N/A")
                        st.metric("Note Physique", f"{note}/10" if note != "N/A" else note)
                    with col3:
                        mm = analyse_photos.get("masse_musculaire", "N/A")
                        st.write(f"**Masse Musculaire:** {mm}")

                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**💪 Points forts:**")
                        for pf in analyse_photos.get("points_forts", []):
                            st.markdown(f"- {pf}")
                    with col2:
                        st.write("**🎯 Zones a travailler:**")
                        for zt in analyse_photos.get("zones_a_travailler", []):
                            st.markdown(f"- {zt}")

                    if analyse_photos.get("evolution_visuelle"):
                        st.write(f"**📈 Evolution visuelle:** {analyse_photos.get('evolution_visuelle')}")

                    st.divider()

                # Metriques
                metriques = analysis.get("metriques", {})
                if metriques:
                    st.subheader("📏 Metriques")
                    cols = st.columns(3)
                    with cols[0]:
                        st.write(f"**Poids:** {metriques.get('poids', 'N/A')}")
                    with cols[1]:
                        st.write(f"**Energie:** {metriques.get('energie', 'N/A')}")
                    with cols[2]:
                        st.write(f"**Sommeil:** {metriques.get('sommeil', 'N/A')}")

                    autres = metriques.get("autres", [])
                    if autres:
                        st.write("**Autres:**", ", ".join(autres) if isinstance(autres, list) else autres)

                    st.divider()

                # Evolution + Points
                col1, col2 = st.columns(2)

                with col1:
                    st.subheader("📈 Evolution")
                    evolution = analysis.get("evolution", {})
                    for key, value in evolution.items():
                        st.write(f"**{key.capitalize()}:** {value}")

                    st.subheader("✅ Points positifs")
                    for point in analysis.get("points_positifs", []):
                        st.success(f"✅ {point}")

                with col2:
                    st.subheader("⚠️ A ameliorer")
                    points_ameliorer = analysis.get("points_ameliorer", [])
                    for point in points_ameliorer:
                        if isinstance(point, dict):
                            priorite = point.get("priorite", "moyenne")
                            color = "🔴" if priorite == "haute" else "🟡" if priorite == "moyenne" else "🟢"
                            st.warning(f"{color} **{point.get('probleme', '')}**\n\n→ {point.get('solution', '')}")
                        else:
                            st.warning(f"⚠️ {point}")

                    # Ajustements
                    ajustements = analysis.get("ajustements", [])
                    if ajustements:
                        st.subheader("🔧 Ajustements")
                        for aj in ajustements:
                            st.markdown(f"- 🔧 {aj}")

                st.divider()

                # Questions/Reponses
                questions_reponses = analysis.get("questions_reponses", [])
                if questions_reponses:
                    st.subheader("❓ Questions & Reponses")
                    for qr in questions_reponses:
                        if isinstance(qr, dict):
                            with st.expander(f"❓ {qr.get('question', 'Question')}"):
                                st.write(qr.get("reponse", ""))
                        else:
                            st.info(qr)

            else:
                st.info("👆 Clique sur 'Analyser' pour lancer l'analyse IA")

        # Tab 4: Reponse
        with tab4:
            if st.session_state.analysis:
                st.subheader("✉️ Email de reponse")

                # Zone d'edition
                st.session_state.draft = st.text_area(
                    "Draft (modifiable)",
                    value=st.session_state.draft,
                    height=400
                )

                # Regeneration avec instructions
                with st.expander("🔄 Regenerer avec instructions"):
                    instructions = st.text_input("Instructions de modification")
                    if st.button("Regenerer"):
                        with st.spinner("Regeneration..."):
                            new_draft = regenerate_email_draft(
                                st.session_state.analysis,
                                instructions,
                                st.session_state.draft
                            )
                            st.session_state.draft = new_draft
                            st.rerun()

                st.divider()

                # Preview
                st.subheader("👁️ Preview")
                preview_html = preview_email(
                    email_data["from_email"],
                    f"Re: {email_data['subject']}",
                    st.session_state.draft
                )
                st.components.v1.html(preview_html, height=500, scrolling=True)

                st.divider()

                # Boutons action
                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("📋 Copier", use_container_width=True):
                        st.code(st.session_state.draft)
                        st.success("Copie le texte ci-dessus!")

                with col2:
                    if st.button("💾 Sauvegarder", use_container_width=True):
                        st.success("Sauvegarde!")

                with col3:
                    if st.button("📤 ENVOYER", type="primary", use_container_width=True):
                        with st.spinner("Envoi..."):
                            # Ajouter tableau KPIs en fin d'email
                            kpis = st.session_state.analysis.get("kpis", {})
                            email_body = st.session_state.draft + generate_kpi_table(kpis)

                            result = send_email(
                                to_email=email_data["from_email"],
                                subject=f"Re: {email_data['subject']}",
                                body=email_body,
                                reply_to_message_id=email_data.get("message_id"),
                                original_subject=email_data['subject']
                            )
                            if result["success"]:
                                # Marquer comme lu
                                st.session_state.reader.mark_as_read(email_data["id"])
                                st.success(f"✅ Email envoye a {email_data['from_email']}!")
                                st.balloons()
                                # Retirer de la liste
                                st.session_state.emails = [e for e in st.session_state.emails if e["id"] != email_data["id"]]
                                st.session_state.selected_email = None
                            else:
                                st.error(f"❌ Erreur: {result['error']}")

            else:
                st.info("👆 Lance d'abord l'analyse pour generer la reponse")

    else:
        # Page d'accueil
        if not st.session_state.connected:
            st.info("👈 Clique sur 'Connecter' dans la sidebar")
        else:
            st.info("👈 Selectionne un bilan dans la sidebar")

        st.markdown("""
        ### 🚀 Comment ca marche

        1. **Connecte Gmail** - Clique sur le bouton dans la sidebar
        2. **Selectionne un bilan** - Les bilans sont detectes automatiquement
        3. **Analyse** - L'IA analyse l'evolution, les metriques, genere les KPIs
        4. **Valide & Envoie** - Modifie si besoin, puis envoie la reponse

        ### 📊 Ce que l'IA analyse

        - Evolution poids/metriques
        - Adherence programme (training, nutrition)
        - Qualite sommeil & energie
        - Reponses aux questions du client
        - Points positifs & axes d'amelioration
        """)


if __name__ == "__main__":
    main()
