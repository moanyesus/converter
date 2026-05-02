"""
SKAB Bank Statement Extractor - Edition Comptabilité Odoo 18
Génère un CSV optimisé pour l'importation manuelle
"""

import streamlit as st
import pandas as pd
import io
import plotly.express as px
from datetime import datetime

# Modules personnalisés
from extractor_gemini import GeminiExtractor
from cleaner import DataCleaner

# ====================== CONFIGURATION ======================
st.set_page_config(page_title="SKAB Extractor - Export Odoo", page_icon="🏦", layout="wide")

st.markdown("""
<style>
    .main-header { background: linear-gradient(135deg, #1B3A5C, #2E75B6); padding: 2rem; border-radius: 16px; color: white; margin-bottom: 2rem; }
    .stMetric { background: #ffffff; padding: 15px; border-radius: 10px; border: 1px dotted #1B3A5C; }
</style>
""", unsafe_allow_html=True)

def get_gemini_key():
    return st.secrets.get("GEMINI_API_KEY", "") or st.session_state.get("gemini_key_input", "")

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
    st.info("Mode : Génération CSV pour Import Manuel Odoo")
    
    uploaded_file = st.file_uploader("📄 Charger le relevé PDF", type=["pdf"])
    
    banque_sel = st.selectbox("Banque", [
        "Financial House S.A", "BGFI Bank", "UNICS", "CEPAC", "ADVANS",
        "MUPECI", "SCB Cameroun", "BICEC", "UBA Cameroun", "Autre banque"
    ])
    st.session_state.banque_selectionnee = banque_sel
    
    method = st.radio("Méthode d'analyse", ["vision", "hybrid"])
    
    if st.button("🔄 Nouvelle extraction", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k not in ["gemini_key_input"]: del st.session_state[k]
        st.rerun()

# ====================== HEADER ======================
st.markdown('<div class="main-header"><h1>🏦 SKAB Bank Statement Extractor</h1><p>Génération de fichiers d\'importation pour la comptabilité</p></div>', unsafe_allow_html=True)

# ====================== EXTRACTION ======================
if uploaded_file and not st.session_state.extraction_done and not st.session_state.show_confirm:
    if st.button("🔍 Analyser le relevé", type="primary", use_container_width=True):
        st.session_state.pdf_bytes_cache = uploaded_file.read()
        st.session_state.show_confirm = True
        st.rerun()

if st.session_state.show_confirm:
    if st.button("✅ Confirmer l'analyse IA", type="primary", use_container_width=True):
        with st.spinner("Extraction des données comptables..."):
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

# ====================== ESPACE COMPTABILITÉ ======================
if st.session_state.extraction_done and st.session_state.df_clean is not None:
    # Travail sur une copie pour le formatage
    df_display = st.session_state.df_clean.copy()
    
    # Nettoyage strict des dates pour Odoo (YYYY-MM-DD)
    df_display['Date'] = pd.to_datetime(df_display['Date'], dayfirst=True, errors='coerce')
    df_display = df_display.dropna(subset=['Date'])
    
    # Métriques pour le DAF
    stats = st.session_state.stats
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Crédits", f"{stats.get('total_credit', 0):,.0f} FCFA")
    m2.metric("Total Débits", f"{stats.get('total_debit', 0):,.0f} FCFA")
    m3.metric("Lignes à importer", len(df_display))

    # --- SECTION GRAPHIQUES ---
    st.subheader("📊 Aperçu des flux de trésorerie")
    df_chart = df_display.groupby('Date')[['Débit', 'Crédit']].sum().reset_index()
    fig = px.area(df_chart, x='Date', y=['Crédit', 'Débit'], 
                  title="Mouvements bancaires cumulés",
                  color_discrete_map={"Débit": "#E74C3C", "Crédit": "#2ECC71"},
                  barmode='group')
    st.plotly_chart(fig, use_container_width=True)

    # --- SECTION EXPORT ---
    st.divider()
    st.subheader("💾 Préparation du fichier Odoo")
    
    # Création du DataFrame spécial Odoo
    # Odoo 18 préfère une colonne unique 'Montant' ou deux colonnes explicites
    odoo_df = df_display.copy()
    odoo_df['Date'] = odoo_df['Date'].dt.strftime('%Y-%m-%d')
    
    # Ajout d'une colonne montant unique (Crédit - Débit) très utile pour Odoo
    odoo_df['Montant_Net'] = odoo_df['Crédit'].fillna(0) - odoo_df['Débit'].fillna(0)
    
    st.info("💡 Le fichier généré inclut une colonne 'Montant_Net' qui combine Débits et Crédits pour faciliter le mapping Odoo.")
    st.dataframe(odoo_df, use_container_width=True)

    # Bouton de téléchargement
    csv_buffer = io.StringIO()
    odoo_df.to_csv(csv_buffer, index=False, encoding='utf-8-sig') # utf-8-sig pour compatibilité Excel
    
    st.download_button(
        label="📥 Télécharger le fichier CSV pour Odoo",
        data=csv_buffer.getvalue(),
        file_name=f"IMPORT_ODOO_{st.session_state.banque_selectionnee}_{datetime.now().strftime('%d_%m_%H%M')}.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True
    )

    st.success("✅ Fichier prêt ! Allez dans Odoo > Comptabilité > Journal Banque > Favoris > Importer des enregistrements.")
