"""
SKAB Bank Statement Extractor - Version Finale pour Odoo 18
Optimisée avec Graphiques pour le DAF et Correction de Date
"""

import streamlit as st
import pandas as pd
import requests
import io
import plotly.express as px  # Pour les graphiques interactifs
from datetime import datetime

# Modules personnalisés
from extractor_gemini import GeminiExtractor
from cleaner import DataCleaner

# ====================== CONFIGURATION ======================
st.set_page_config(page_title="SKAB Bank Extractor", page_icon="🏦", layout="wide")

st.markdown("""
<style>
    .main-header { background: linear-gradient(135deg, #1B3A5C, #2E75B6); padding: 2rem; border-radius: 16px; color: white; margin-bottom: 2rem; }
    .stMetric { background: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0; }
</style>
""", unsafe_allow_html=True)

def get_gemini_key():
    return st.secrets.get("GEMINI_API_KEY", "") or st.session_state.get("gemini_key_input", "")

def get_odoo_webhook_url():
    return st.secrets.get("ODOO_WEBHOOK_URL", "")

if "extraction_done" not in st.session_state:
    st.session_state.update({
        "extraction_done": False,
        "show_confirm": False,
        "df_clean": None,
        "stats": None,
        "banque_selectionnee": "UNICS",
        "pdf_bytes_cache": None,
    })

# ====================== SIDEBAR ======================
with st.sidebar:
    st.title("🏦 SKAB Extractor")
    uploaded_file = st.file_uploader("📄 Relevé PDF", type=["pdf"])
    
    banque_sel = st.selectbox("Banque", [
        "Financial House S.A", "BGFI Bank", "UNICS", "CEPAC", "ADVANS",
        "MUPECI", "SCB Cameroun", "BICEC", "UBA Cameroun", "Autre banque"
    ])
    st.session_state.banque_selectionnee = banque_sel
    
    method = st.radio("Méthode", ["vision", "hybrid"])
    
    if st.button("🔄 Nouvelle extraction", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k not in ["gemini_key_input"]: del st.session_state[k]
        st.rerun()

# ====================== HEADER ======================
st.markdown('<div class="main-header"><h1>🏦 SKAB Bank Statement Extractor</h1><p>Analyse Financière & Intégration Odoo 18</p></div>', unsafe_allow_html=True)

# ====================== EXTRACTION ======================
if uploaded_file and not st.session_state.extraction_done and not st.session_state.show_confirm:
    if st.button("Lancer l'analyse", type="primary", use_container_width=True):
        st.session_state.pdf_bytes_cache = uploaded_file.read()
        st.session_state.show_confirm = True
        st.rerun()

if st.session_state.show_confirm:
    if st.button("✅ Confirmer l'extraction", type="primary", use_container_width=True):
        with st.spinner("Analyse IA en cours..."):
            try:
                extractor = GeminiExtractor(api_key=get_gemini_key(), mode=method, banque_nom=st.session_state.banque_selectionnee)
                df_raw = extractor.extract(st.session_state.pdf_bytes_cache)
                
                cleaner = DataCleaner()
                df_clean = cleaner.clean(df_raw, banque_nom=st.session_state.banque_selectionnee)
                
                st.session_state.df_clean = df_clean
                st.session_state.stats = cleaner.get_statistics(df_clean)
                st.session_state.extraction_done = True
                st.session_state.show_confirm = False
                st.rerun()
            except Exception as e:
                st.error(f"Erreur : {str(e)}")

# ====================== TABLEAU DE BORD DAF ======================
if st.session_state.extraction_done and st.session_state.df_clean is not None:
    df = st.session_state.df_clean.copy()
    
    # 1. Nettoyage des dates pour l'affichage et les graphiques
    df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
    df = df.dropna(subset=['Date'])
    
    # 2. Métriques principales
    stats = st.session_state.stats
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Crédits", f"{stats.get('total_credit', 0):,.0f} FCFA")
    m2.metric("Total Débits", f"{stats.get('total_debit', 0):,.0f} FCFA")
    m3.metric("Solde Net Flux", f"{(stats.get('total_credit', 0) - stats.get('total_debit', 0)):,.0f} FCFA")

    # 3. GRAPHIQUE POUR LE DAF
    st.subheader("📊 Analyse visuelle des flux")
    tab1, tab2 = st.tabs(["📈 Courbe des flux", "💰 Répartition Débit/Crédit"])
    
    with tab1:
        # Evolution temporelle
        df_daily = df.groupby('Date')[['Débit', 'Crédit']].sum().reset_index()
        fig_line = px.line(df_daily, x='Date', y=['Débit', 'Crédit'], 
                           title="Évolution des mouvements bancaires",
                           color_discrete_map={"Débit": "#E74C3C", "Crédit": "#2ECC71"},
                           markers=True)
        st.plotly_chart(fig_line, use_container_width=True)
        
    with tab2:
        # Graphique en barres comparatif
        flux_totals = pd.DataFrame({
            'Type': ['Débits', 'Crédits'],
            'Montant': [stats.get('total_debit', 0), stats.get('total_credit', 0)]
        })
        fig_bar = px.bar(flux_totals, x='Type', y='Montant', color='Type',
                         color_discrete_map={"Débits": "#E74C3C", "Crédits": "#2ECC71"},
                         text_auto='.2s')
        st.plotly_chart(fig_bar, use_container_width=True)

    # 4. TABLEAU DE DONNÉES
    st.subheader("📋 Détail des transactions")
    st.dataframe(df.sort_values('Date'), use_container_width=True)

    # 5. ENVOI VERS ODOO
    st.divider()
    st.subheader("🔗 Exportation vers Odoo 18")
    
    c1, c2 = st.columns(2)
    with c1: 
        odoo_url = get_odoo_webhook_url() or st.text_input("URL Webhook Odoo")
    with c2: 
        journal_id = st.number_input("ID Journal Odoo", value=8)

    if st.button("🚀 Synchroniser avec Odoo", type="primary", use_container_width=True):
        if not odoo_url:
            st.error("URL manquante.")
        else:
            with st.spinner("Envoi..."):
                try:
                    # Préparation finale : Formatage ISO pour Odoo
                    export_df = df.copy()
                    export_df = export_df.rename(columns={
                        'Date': 'date', 'Libellé': 'name', 'Référence': 'ref',
                        'Débit': 'amount_debit', 'Crédit': 'amount_credit'
                    })
                    export_df['date'] = export_df['date'].dt.strftime('%Y-%m-%d')
                    
                    # Envoi en texte brut pour éviter les erreurs d'import Odoo
                    payload = {
                        "journal_id": journal_id,
                        "csv_data": export_df.to_csv(index=False),
                        "bank_name": st.session_state.banque_selectionnee
                    }
                    
                    res = requests.post(odoo_url, json=payload, timeout=30)
                    if res.status_code in (200, 201):
                        st.success("✅ Données transmises à Odoo !")
                        st.balloons()
                    else:
                        st.error(f"Erreur Odoo : {res.text}")
                except Exception as e:
                    st.error(f"Échec : {str(e)}")
