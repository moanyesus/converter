"""
SKAB Bank Statement Extractor - Version Finale pour Odoo 18
Utilise les Secrets Streamlit pour GEMINI_API_KEY et ODOO_WEBHOOK_URL
"""

import streamlit as st
import pandas as pd
import requests
import base64
import io
from datetime import datetime

from extractor_gemini import GeminiExtractor
from cleaner import DataCleaner
from bank_configs import get_bank_config

# ====================== CONFIG ======================
st.set_page_config(page_title="SKAB Bank Extractor - Odoo 18", page_icon="🏦", layout="wide")

st.markdown("""
<style>
    .main-header { background: linear-gradient(135deg, #1B3A5C, #2E75B6); padding: 2rem; border-radius: 16px; color: white; margin-bottom: 2rem; }
    .success-box { background: #d4edda; border-left: 5px solid #28a745; padding: 1rem; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


def get_gemini_key():
    return st.secrets.get("GEMINI_API_KEY", "") or st.session_state.get("gemini_key_input", "")

def get_odoo_webhook_url():
    return st.secrets.get("ODOO_WEBHOOK_URL", "")

def get_odoo_journal_id():
    return st.secrets.get("ODOO_JOURNAL_ID", 8)


# Session State
if "extraction_done" not in st.session_state:
    st.session_state.update({
        "extraction_done": False,
        "show_confirm": False,
        "df_clean": None,
        "stats": None,
        "account_info": None,
        "debug_logs": "",
        "banque_selectionnee": "UNICS",
        "pdf_bytes_cache": None,
    })


# ====================== SIDEBAR ======================
with st.sidebar:
    st.title("🏦 SKAB Bank Extractor")
    st.caption("Odoo 18 Integration")

    uploaded_file = st.file_uploader("📄 Relevé PDF", type=["pdf"])

    banque_sel = st.selectbox("Banque", [
        "Financial House S.A", "BGFI Bank", "UNICS", "CEPAC", "ADVANS",
        "MUPECI", "SCB Cameroun", "BICEC", "UBA Cameroun", "Autre banque"
    ])
    st.session_state.banque_selectionnee = banque_sel

    method = st.radio("Méthode", ["vision", "hybrid"],
                     format_func=lambda x: {"vision": "🔭 Gemini Vision", "hybrid": "⚡ Hybride"}[x])

    if method in ("vision", "hybrid"):
        st.text_input("Clé API Gemini", type="password", key="gemini_key_input")

    if st.button("🔄 Nouvelle extraction", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k not in ["gemini_key_input"]:
                del st.session_state[k]
        st.rerun()


# ====================== HEADER ======================
st.markdown('<div class="main-header"><h1>🏦 SKAB Bank Statement Extractor</h1><p>Export vers Odoo 18</p></div>', unsafe_allow_html=True)


# ====================== EXTRACTION ======================
if uploaded_file and not st.session_state.extraction_done and not st.session_state.show_confirm:
    if st.button("Lancer l'extraction", type="primary", use_container_width=True):
        st.session_state.pdf_bytes_cache = uploaded_file.read()
        st.session_state.show_confirm = True
        st.rerun()

if st.session_state.show_confirm:
    if st.button("✅ Confirmer extraction", type="primary", use_container_width=True):
        with st.spinner("Extraction en cours..."):
            try:
                extractor = GeminiExtractor(
                    api_key=get_gemini_key(),
                    mode=method,
                    banque_nom=st.session_state.banque_selectionnee,
                    verbose_debug=True
                )
                df_raw = extractor.extract(st.session_state.pdf_bytes_cache)

                cleaner = DataCleaner()
                df_clean = cleaner.clean(df_raw, banque_nom=st.session_state.banque_selectionnee)
                stats = cleaner.get_statistics(df_clean)

                st.session_state.df_clean = df_clean
                st.session_state.stats = stats
                st.session_state.account_info = {"banque": st.session_state.banque_selectionnee}
                st.session_state.extraction_done = True
                st.session_state.show_confirm = False
                st.session_state.debug_logs = extractor.get_debug_logs()

                st.success("✅ Extraction terminée !")
                st.rerun()
            except Exception as e:
                st.error(f"Erreur : {str(e)}")


# ====================== RÉSULTATS ======================
if st.session_state.extraction_done and st.session_state.df_clean is not None:
    df = st.session_state.df_clean
    stats = st.session_state.stats or {}

    st.success(f"{len(df)} lignes extraites")

    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Crédits", f"{stats.get('total_credit',0):,.0f} FCFA")
    with col2: st.metric("Débits", f"{stats.get('total_debit',0):,.0f} FCFA")
    with col3: st.metric("Lignes", len(df))

    st.dataframe(df, use_container_width=True, height=500)

    # ====================== EXPORT CSV ODOO ======================
    csv_buffer = io.StringIO()
    export_df = df.rename(columns={
        'Date': 'date', 'Libellé': 'name', 'Référence': 'ref',
        'Débit': 'amount_debit', 'Crédit': 'amount_credit'
    })
    if 'date' in export_df.columns:
        export_df['date'] = pd.to_datetime(export_df['date'], format='%d/%m/%Y', errors='coerce').dt.strftime('%Y-%m-%d')

    export_df.to_csv(csv_buffer, index=False)

    st.download_button(
        label="📥 Télécharger CSV pour Odoo",
        data=csv_buffer.getvalue(),
        file_name=f"releve_{st.session_state.banque_selectionnee}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )

       # ====================== ENVOI VERS ODOO ======================
    st.subheader("🔗 Envoi vers Odoo 18")

    odoo_url = st.secrets.get("ODOO_WEBHOOK_URL", "")
    
    if not odoo_url:
        odoo_url = st.text_input(
            "URL du Webhook Odoo", 
            placeholder="https://votre-odoo.com/webhook/bank-statement-import"
        )

    journal_id = st.number_input("ID du Journal Bancaire dans Odoo", value=8, min_value=1)

   if st.button("🚀 Envoyer vers Odoo", type="primary", use_container_width=True):
    if not odoo_url:
        st.error("❌ Veuillez configurer l'URL du webhook")
    else:
        with st.spinner("Envoi vers Odoo en cours..."):
            try:
                # 1. Préparation propre du DataFrame
                export_df = df.copy()
                export_df = export_df.rename(columns={
                    'Date': 'date',
                    'Libellé': 'name',
                    'Référence': 'ref',
                    'Débit': 'amount_debit',
                    'Crédit': 'amount_credit'
                })
                
                # 2. Formatage strict de la date pour Odoo
                export_df['date'] = pd.to_datetime(export_df['date'], dayfirst=True).dt.strftime('%Y-%m-%d')

                # 3. Conversion en CSV texte (sans encodage base64 pour Odoo)
                csv_data = export_df.to_csv(index=False, encoding='utf-8')

                # 4. Construction du Payload simplifié
                payload = {
                    "journal_id": journal_id,
                    "csv_data": csv_data  # Texte brut pour éviter l'erreur d'import base64
                }

                # 5. Envoi
                response = requests.post(odoo_url, json=payload, timeout=30)

                if response.status_code in (200, 201):
                    st.success("✅ Relevé envoyé avec succès à Odoo !")
                else:
                    st.error(f"Erreur Odoo ({response.status_code}): {response.text}")
            except Exception as e:
                st.error(f"Erreur lors de l'envoi : {str(e)}")
