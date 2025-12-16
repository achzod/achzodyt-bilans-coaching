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
import html

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
    cols = st.columns(7)
    kpi_labels = {
        "adherence_training": "Training",
        "adherence_nutrition": "Nutrition",
        "sommeil": "Sommeil",
        "energie": "Energie",
        "sante": "Sante",
        "mindset": "Mindset",
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
            connect_btn = st.button("🔄 Charger", use_container_width=True)
        with col2:
            days = st.selectbox("Jours", [3, 7, 14, 30], index=1, label_visibility="collapsed")

        # Mode de chargement
        load_mode = st.radio(
            "Mode",
            ["Sans reponse", "Non lus", "Tous"],
            horizontal=True,
            help="Sans reponse = emails auxquels tu n'as pas repondu"
        )

        if connect_btn:
            with st.status("Chargement emails...", expanded=True) as status:
                if st.session_state.reader is None:
                    st.session_state.reader = EmailReader()

                st.write("🔌 Connexion Gmail...")

                if load_mode == "Sans reponse":
                    st.write("📬 Recherche emails sans reponse...")
                    st.write("⏳ Comparaison avec emails envoyes...")
                    st.session_state.emails = st.session_state.reader.get_unanswered_emails(days=days)
                elif load_mode == "Non lus":
                    st.write("📬 Recherche emails non lus...")
                    st.session_state.emails = st.session_state.reader.get_all_emails(days=days, unread_only=True)
                else:
                    st.write("📬 Recherche tous les emails...")
                    st.session_state.emails = st.session_state.reader.get_all_emails(days=days, unread_only=False)

                if st.session_state.emails:
                    st.session_state.connected = True
                    status.update(label=f"✅ {len(st.session_state.emails)} emails charges!", state="complete", expanded=False)
                else:
                    status.update(label="⚠️ Aucun email trouve", state="complete", expanded=False)

        # Bouton rafraichir
        if st.session_state.connected:
            if st.button("🔃 Rafraichir", use_container_width=True):
                with st.spinner("Rechargement..."):
                    if load_mode == "Sans reponse":
                        st.session_state.emails = st.session_state.reader.get_unanswered_emails(days=days)
                    elif load_mode == "Non lus":
                        st.session_state.emails = st.session_state.reader.get_all_emails(days=days, unread_only=True)
                    else:
                        st.session_state.emails = st.session_state.reader.get_all_emails(days=days, unread_only=False)
                    st.rerun()

        st.divider()

        # Liste des bilans (filtrer typeform et newsletters)
        EXCLUDE_PATTERNS = ['typeform', 'followups.typeform', 'newsletter', 'noreply', 'no-reply', 'mailer-daemon', 'notification', 'notifications', 'followup', 'follow-up', 'unsubscribe', 'support@', 'info@', 'contact@', 'hello@', 'team@', 'marketing', 'promo', 'sale', 'discount', '@virginmobile', '@forgeeapp', 'donotreply', 'automated', 'invoice', 'receipt', 'paypal', 'stripe', 'anthropic', 'billing', 'payment received']
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

        # Emails du meme client (pour regrouper metriques, photos, questions)
        same_client_emails = [e for e in st.session_state.emails if e['from_email'] == email_data['from_email']]
        
        if len(same_client_emails) > 1:
            st.warning(f"Ce client a {len(same_client_emails)} emails non traites!")
            with st.expander(f"Voir tous les emails de {email_data['from_email']}"):
                for e in same_client_emails:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.write(f"{e['date'].strftime('%d/%m %H:%M') if e.get('date') else ''} - {e['subject'][:50]}")
                    with col2:
                        if st.button("Ajouter", key=f"add_{e['id']}"):
                            # Charger le contenu et fusionner
                            if not e.get("loaded"):
                                c = st.session_state.reader.load_email_content(e["id"])
                                if c:
                                    e["body"] = c.get("body", "")
                                    e["attachments"] = c.get("attachments", [])
                                    e["loaded"] = True
                            # Fusionner avec l'email actuel
                            email_data["body"] += chr(10)*2 + "--- EMAIL SUIVANT ---" + chr(10) + e.get("body", "")
                            email_data["attachments"].extend(e.get("attachments", []))
                            st.success("Email fusionne!")
                            st.rerun()

        # Lazy loading: charger contenu si pas encore fait (avec retry automatique)
        if not email_data.get("loaded", False) or not email_data.get("body"):
            with st.status("Chargement du contenu email...", expanded=True) as load_status:
                st.write("📧 Connexion au serveur...")
                content = st.session_state.reader.load_email_content(email_data["id"])

                if content and content.get("loaded"):
                    email_data["body"] = content.get("body", "")
                    email_data["attachments"] = content.get("attachments", [])
                    email_data["loaded"] = True
                    st.session_state.selected_email = email_data
                    load_status.update(label=f"✅ Charge: {len(email_data['body'])} caracteres", state="complete", expanded=False)
                else:
                    error_msg = content.get("error", "Erreur inconnue") if content else "Pas de reponse serveur"
                    load_status.update(label=f"⚠️ Chargement partiel", state="error", expanded=False)
                    st.warning(f"Le contenu n'a pas pu etre charge completement: {error_msg}. Clique sur 🔄 pour reessayer.")

        # Header
        col1, col2, col3, col4 = st.columns([3, 1, 1, 0.5])
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
            analyze_clicked = st.button("🤖 Analyser", type="primary", use_container_width=True, key=f"analyze_{email_data['id']}")
            if analyze_clicked:
                # Forcer le chargement du contenu d'abord - avec reconnexion
                if not email_data.get("loaded", False) or not email_data.get("body"):
                    with st.spinner("Chargement du contenu email..."):
                        # Reconnexion forcee si besoin
                        if st.session_state.reader:
                            try:
                                st.session_state.reader.connection.noop()
                            except:
                                st.session_state.reader.connect()
                        content_data = st.session_state.reader.load_email_content(email_data["id"])
                        if content_data and content_data.get("body"):
                            email_data["body"] = content_data.get("body", "")
                            email_data["attachments"] = content_data.get("attachments", [])
                            email_data["loaded"] = True
                            st.session_state.selected_email = email_data

                with st.status("Analyse IA en cours...", expanded=True) as status:
                    st.write(f"📧 Email: {len(email_data.get('body', ''))} chars, {len(email_data.get('attachments', []))} pieces jointes")

                    if not email_data.get("body"):
                        status.update(label="❌ Erreur", state="error")
                        st.error("Impossible de charger le contenu de l'email. Clique sur 'Recharger' puis re-essaie.")
                    else:
                        st.write("🤖 Appel Claude API...")

                        result = analyze_coaching_bilan(
                            email_data,
                            st.session_state.history
                        )

                        if result["success"]:
                            analysis = result["analysis"]
                            # S'assurer que c'est un dict, pas une string JSON
                            if isinstance(analysis, str):
                                try:
                                    import json
                                    analysis = json.loads(analysis)
                                except:
                                    pass
                            st.session_state.analysis = analysis
                            # Extraire draft_email proprement
                            draft = ""
                            if isinstance(analysis, dict):
                                draft = analysis.get("draft_email", "")
                            elif isinstance(analysis, str) and "draft_email" in analysis:
                                # Essayer d'extraire le draft_email du JSON string
                                import re
                                match = re.search(r'"draft_email"\s*:\s*"(.*?)"(?=\s*[,}])', analysis, re.DOTALL)
                                if match:
                                    draft = match.group(1).replace('\\n', '\n').replace('\\"', '"')
                            st.session_state.draft = draft if draft else "Email a rediger manuellement."
                            status.update(label="✅ Analyse terminee!", state="complete", expanded=False)
                            st.rerun()
                        else:
                            status.update(label="❌ Erreur", state="error")
                            st.error(f"Erreur: {result.get('error')}")
        with col4:
            col4a, col4b = st.columns(2)
            with col4a:
                if st.button("🔄", help="Recharger contenu email"):
                    with st.status("Rechargement...", expanded=True) as reload_status:
                        st.write("🔌 Force reconnexion...")
                        # Forcer reconnexion
                        if st.session_state.reader:
                            st.session_state.reader.connect(force=True)

                        st.write("📧 Chargement contenu...")
                        content_data = st.session_state.reader.load_email_content(email_data["id"])

                        if content_data and content_data.get("loaded") and content_data.get("body"):
                            email_data["body"] = content_data.get("body", "")
                            email_data["attachments"] = content_data.get("attachments", [])
                            email_data["loaded"] = True
                            st.session_state.selected_email = email_data
                            reload_status.update(label=f"✅ Charge: {len(email_data['body'])} chars, {len(email_data.get('attachments', []))} PJ", state="complete")
                        else:
                            error = content_data.get("error", "Erreur inconnue") if content_data else "Pas de reponse"
                            reload_status.update(label=f"❌ Echec: {error}", state="error")
                    st.rerun()
            with col4b:
                if st.button("❌", help="Ignorer cet email"):
                    st.session_state.emails = [e for e in st.session_state.emails if e["id"] != email_data["id"]]
                    st.session_state.selected_email = None
                    st.rerun()

        # Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["📨 Email", "📜 Historique", "📊 Analyse", "✉️ Reponse"])

        # Tab 1: Email actuel
        with tab1:
            st.markdown(f'<div class="bilan-card">{html.escape(email_data["body"])}</div>', unsafe_allow_html=True)

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

                # === BOUTONS RAPIDES COACH PRO ===
                st.markdown("##### 🎯 Ajouts rapides")

                # Row 1: Motivation & Celebration
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    if st.button("🔥 Motivation", use_container_width=True, help="Ajouter encouragement"):
                        st.session_state.draft += "\n\nContinue comme ca, tu es sur la bonne voie! Chaque effort compte et je vois que tu donnes le meilleur de toi-meme. La regularite paie toujours."
                        st.rerun()
                with col_m2:
                    if st.button("🏆 Bravo!", use_container_width=True, help="Celebrer une victoire"):
                        st.session_state.draft += "\n\nJe tiens a te feliciter pour cette progression! C'est exactement ce type de travail qui fait la difference sur le long terme. Tu peux etre fier de toi."
                        st.rerun()
                with col_m3:
                    if st.button("💪 Push", use_container_width=True, help="Pousser a l'action"):
                        st.session_state.draft += "\n\nC'est le moment de mettre un coup d'accelerateur! Tu as pose les bases, maintenant on passe a la vitesse superieure. Je compte sur toi pour donner 100% cette semaine."
                        st.rerun()
                with col_m4:
                    if st.button("🎯 Focus", use_container_width=True, help="Recentrer sur objectif"):
                        st.session_state.draft += "\n\nGarde ton objectif en tete a chaque instant. Chaque repas, chaque training, chaque nuit de sommeil te rapproche de ta meilleure version. Stay focused!"
                        st.rerun()

                # Row 2: Conseils techniques
                col_t1, col_t2, col_t3, col_t4 = st.columns(4)
                with col_t1:
                    if st.button("😴 Sommeil", use_container_width=True, help="Conseil sommeil"):
                        st.session_state.draft += "\n\nRappel important sur le sommeil: c'est pendant que tu dors que ton corps se repare et construit du muscle. Vise 7-8h minimum, chambre fraiche, pas d'ecran 1h avant. C'est non negociable pour tes resultats."
                        st.rerun()
                with col_t2:
                    if st.button("💧 Hydratation", use_container_width=True, help="Conseil hydratation"):
                        st.session_state.draft += "\n\nN'oublie pas ton hydratation! Minimum 2-3L d'eau par jour, davantage les jours d'entrainement. Une bonne hydratation optimise tes performances et ta recuperation."
                        st.rerun()
                with col_t3:
                    if st.button("🍗 Proteines", use_container_width=True, help="Rappel proteines"):
                        st.session_state.draft += "\n\nAssure-toi d'atteindre ton quota de proteines chaque jour (1.6-2g/kg). Repartis-les sur tes repas pour une meilleure absorption. C'est la base pour construire et maintenir ta masse musculaire."
                        st.rerun()
                with col_t4:
                    if st.button("⚡ Recuperation", use_container_width=True, help="Conseil recup"):
                        st.session_state.draft += "\n\nLa recuperation est aussi importante que l'entrainement! Ecoute ton corps, n'hesite pas a prendre un jour de repos actif si tu sens la fatigue s'accumuler. Mieux vaut un jour de moins que risquer le surentrainement."
                        st.rerun()

                # Row 3: Closings professionnels
                st.markdown("##### ✍️ Signatures")
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    if st.button("📝 Standard", use_container_width=True):
                        st.session_state.draft += "\n\nOn se retrouve au prochain bilan. D'ici la, applique bien les ajustements et n'hesite pas si tu as des questions.\n\nA fond!\nAchzod"
                        st.rerun()
                with col_s2:
                    if st.button("🚀 Motivant", use_container_width=True):
                        st.session_state.draft += "\n\nJe suis convaincu que tu vas tout dechirer cette semaine! Reste focus, reste discipline, et les resultats suivront.\n\nLet's go!\nAchzod 💪"
                        st.rerun()
                with col_s3:
                    if st.button("🤝 Supportif", use_container_width=True):
                        st.session_state.draft += "\n\nJe suis la si tu as besoin de quoi que ce soit. On avance ensemble vers ton objectif, etape par etape.\n\nA tres vite,\nAchzod"
                        st.rerun()

                st.divider()

                # Zone d'edition
                st.session_state.draft = st.text_area(
                    "Draft (modifiable)",
                    value=st.session_state.draft,
                    height=400
                )

                # Bouton ajouter KPIs
                col_kpi1, col_kpi2 = st.columns([1, 3])
                with col_kpi1:
                    if st.button("📊 Ajouter KPIs", use_container_width=True):
                        kpis = st.session_state.analysis.get("kpis", {})
                        kpi_text = generate_kpi_table(kpis)
                        st.session_state.draft = st.session_state.draft + kpi_text
                        st.rerun()
                with col_kpi2:
                    st.caption("Insere le tableau KPIs a la fin de ton email")

                # Ajustement de ton avec IA
                st.markdown("##### 🎨 Ajuster le ton")
                col_tone1, col_tone2, col_tone3, col_tone4 = st.columns(4)
                with col_tone1:
                    if st.button("🦁 Plus direct", use_container_width=True, help="Ton plus cash, coach strict"):
                        with st.spinner("Ajustement..."):
                            new_draft = regenerate_email_draft(
                                st.session_state.analysis,
                                "Rends le ton BEAUCOUP plus direct, cash, coach strict qui ne laisse pas passer les excuses. Style sergent instructeur bienveillant mais ferme.",
                                st.session_state.draft
                            )
                            st.session_state.draft = new_draft
                            st.rerun()
                with col_tone2:
                    if st.button("🤗 Plus doux", use_container_width=True, help="Ton plus encourageant"):
                        with st.spinner("Ajustement..."):
                            new_draft = regenerate_email_draft(
                                st.session_state.analysis,
                                "Rends le ton plus doux, encourageant et bienveillant. Mets l'accent sur le positif et le soutien emotionnel.",
                                st.session_state.draft
                            )
                            st.session_state.draft = new_draft
                            st.rerun()
                with col_tone3:
                    if st.button("🧠 Plus technique", use_container_width=True, help="Plus de details scientifiques"):
                        with st.spinner("Ajustement..."):
                            new_draft = regenerate_email_draft(
                                st.session_state.analysis,
                                "Ajoute plus d'explications techniques et scientifiques. Explique le POURQUOI physiologique de chaque conseil. Montre ton expertise.",
                                st.session_state.draft
                            )
                            st.session_state.draft = new_draft
                            st.rerun()
                with col_tone4:
                    if st.button("🔥 Plus hype", use_container_width=True, help="Plus d'energie"):
                        with st.spinner("Ajustement..."):
                            new_draft = regenerate_email_draft(
                                st.session_state.analysis,
                                "Rends le message BEAUCOUP plus energique et motivant! Style coach americain, hype, qui donne envie de tout casser a la salle!",
                                st.session_state.draft
                            )
                            st.session_state.draft = new_draft
                            st.rerun()

                # Regeneration avec instructions custom
                with st.expander("🔄 Regenerer avec instructions personnalisees"):
                    instructions = st.text_input("Instructions de modification", placeholder="Ex: Insiste plus sur l'importance du sommeil...")
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
