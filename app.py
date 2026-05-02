"""
SKAB Bank Statement Extractor - Version Finale pour Odoo 18
Optimisée pour éviter les erreurs d'importation et de formatage de date
"""

import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime

# Import de vos modules personnalisés (assurez-vous qu'ils sont dans le même dossier)
from extractor_gemini import GeminiExtractor
from cleaner import DataCleaner

# ====================== CONFIG ======================
st.set_page_config(page_title="SKAB Bank Extractor - Odoo 18", page_icon="🏦", layout="wide")

st.markdown("""
<style>
    .main-header { background: linear-gradient(135deg, #1B3A5C, #2E75B6); padding: 2rem; border-radius: 16px; color: white; margin-bottom: 2rem; }
    .stButton>button { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# Fonctions utilitaires pour les secrets
def get_gemini_key():
    return st.secrets.get("GEMINI_API_KEY", "") or st.session_state.get("gemini_key_input", "")

def get_odoo_webhook_url():
    return st.secrets.get("ODOO_WEBHOOK_URL", "")

# Initialisation du Session State
if "extraction_done" not in st.session_state:
    st.session_state.update({
        "extraction_done": False,
        "show_confirm": False,
        "df_clean": None,
        "stats": None,
        "debug_logs": "",
        "banque_selectionnee": "UNICS",
        "pdf_bytes_cache": None,
    })

# ====================== SIDEBAR ======================
with st.sidebar:
    st.title("🏦 SKAB Bank Extractor")
    st.caption("Intégration Directe Odoo 18")

    uploaded_file = st.file_uploader("📄 Charger le relevé PDF", type=["pdf"])

    banque_sel = st.selectbox("Banque", [
        "Financial House S.A", "BGFI Bank", "UNICS", "CEPAC", "ADVANS",
        "MUPECI", "SCB Cameroun", "BICEC", "UBA Cameroun", "Autre banque"
    ])
    st.session_state.banque_selectionnee = banque_sel

    method = st.radio("Méthode d'extraction", ["vision", "hybrid"])

    if st.button("🔄 Réinitialiser", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k not in ["gemini_key_input"]:
                del st.session_state[k]
        st.rerun()

# ====================== HEADER ======================
st.markdown('<div class="main-header"><h1>🏦 SKAB Bank Statement Extractor</h1><p>Traitement IA & Export vers Odoo Enterprise</p></div>', unsafe_allow_html=True)

# ====================== LOGIQUE D'EXTRACTION ======================
if uploaded_file and not st.session_state.extraction_done and not st.session_state.show_confirm:
    if st.button("Lancer l'extraction", type="primary", use_container_width=True):
        st.session_state.pdf_bytes_cache = uploaded_file.read()
        st.session_state.show_confirm = True
        st.rerun()

if st.session_state.show_confirm:
    if st.button("✅ Confirmer le traitement", type="primary", use_container_width=True):
        with st.spinner("Analyse du document par Gemini..."):
            try:
                extractor = GeminiExtractor(
                    api_key=get_gemini_key(),
                    mode=method,
                    banque_nom=st.session_state.banque_selectionnee
                )
                df_raw = extractor.extract(st.session_state.pdf_bytes_cache)

                cleaner = DataCleaner()
                df_clean = cleaner.clean(df_raw, banque_nom=st.session_state.banque_selectionnee)
                
                st.session_state.df_clean = df_clean
                st.session_state.stats = cleaner.get_statistics(df_clean)
                st.session_state.extraction_done = True
                st.session_state.show_confirm = False
                st.success("✅ Analyse terminée avec succès !")
                st.rerun()
            except Exception as e:
                st.error(f"Erreur d'extraction : {str(e)}")

# ====================== AFFICHAGE DES RÉSULTATS ======================
if st.session_state.extraction_done and st.session_state.df_clean is not None:
    df = st.session_state.df_clean
    stats = st.session_state.stats or {}

    # Résumé visuel pour le DAF
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Total Crédits", f"{stats.get('total_credit', 0):,.0f} FCFA")
    with col2: st.metric("Total Débits", f"{stats.get('total_debit', 0):,.0f} FCFA")
    with col3: st.metric("Transactions", len(df))

    st.dataframe(df, use_container_width=True, height=400)

    st.divider()

    # ====================== SECTION ENVOI ODOO ======================
    st.subheader("🔗 Transmission vers Odoo Enterprise")
    
    col_a, col_b = st.columns(2)
    with col_a:
        odoo_url = get_odoo_webhook_url()
        if not odoo_url:
            odoo_url = st.text_input("URL du Webhook Odoo", placeholder="https://...")
    
    with col_b:
        journal_id = st.number_input("ID du Journal Banque Odoo", value=8, min_value=1)

    if st.button("🚀 Envoyer les données vers Odoo", type="primary", use_container_width=True):
        if not odoo_url:
            st.error("❌ L'URL du Webhook Odoo est manquante.")
        else:
            with st.spinner("Synchronisation avec Odoo..."):
                try:
                    # 1. Préparation et Nettoyage des données pour Odoo
                    export_df = df.copy()
                    
                    # On retire les lignes sans date (ex: Opening Balance) pour éviter les erreurs
                    export_df = export_df.dropna(subset=['Date'])
                    export_df = export_df[export_df['Date'].astype(str).str.lower() != 'nan']

                    # Renommage des colonnes pour correspondre au script Odoo
                    export_df = export_df.rename(columns={
                        'Date': 'date',
                        'Libellé': 'name',
                        'Référence': 'ref',
                        'Débit': 'amount_debit',
                        'Crédit': 'amount_credit'
                    })

                    # 2. Conversion format date ISO (AAAA-MM-JJ) exigé par Odoo
                    export_df['date'] = pd.to_datetime(export_df['date'], dayfirst=True, errors='coerce')
                    export_df = export_df.dropna(subset=['date'])
                    export_df['date'] = export_df['date'].dt.strftime('%Y-%m-%d')

                    # 3. Conversion en texte CSV pur (SANS Base64 pour éviter "Forbidden Opcode")
                    csv_text = export_df.to_csv(index=False, encoding='utf-8')

                    # 4. Construction du Payload
                    payload = {
                        "journal_id": journal_id,
                        "csv_data": csv_text,
                        "bank_name": st.session_state.banque_selectionnee
                    }

                    # 5. Appel API
                    response = requests.post(odoo_url, json=payload, timeout=30)

                    if response.status_code in (200, 201):
                        st.success("✅ Les transactions ont été intégrées dans Odoo !")
                        st.balloons()
                    else:
                        st.error(f"Erreur Odoo ({response.status_code}) : {response.text}")
                
                except Exception as e:
                    st.error(f"Erreur technique lors de l'envoi : {str(e)}")

    # Option de téléchargement manuel au cas où
    st.download_button(
        label="📥 Sauvegarder en CSV local",
        data=df.to_csv(index=False).encode('utf-8'),
        file_name=f"backup_releve_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
