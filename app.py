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
    
    # On s'assure que les colonnes sont bien au format numérique pour le graphique
    df_display['Débit'] = pd.to_numeric(df_display['Débit'], errors='coerce').fillna(0)
    df_display['Crédit'] = pd.to_numeric(df_display['Crédit'], errors='coerce').fillna(0)
    
    # Groupement par date
    df_chart = df_display.groupby('Date')[['Débit', 'Crédit']].sum().reset_index()
    
    # Utilisation de px.line ou px.area sans barmode
    fig = px.area(df_chart, 
                  x='Date', 
                  y=['Crédit', 'Débit'], 
                  title="Mouvements bancaires cumulés",
                  color_discrete_map={"Débit": "#E74C3C", "Crédit": "#2ECC71"})
    
    # Amélioration du design du graphique
    fig.update_layout(hovermode="x unified", yaxis_title="Montant (FCFA)")
    
    st.plotly_chart(fig, use_container_width=True)
   # --- SECTION EXPORT OPTIMISÉE POUR ODOO ---
    st.divider()
    st.subheader("💾 Exportation prête pour Odoo")
    
    # 1. Préparation du DataFrame avec les noms de champs Odoo standards
    # Cela permet à Odoo de reconnaître automatiquement les colonnes
    odoo_export = df_display.copy()
    
    # Mapping des colonnes vers les termes techniques Odoo
    odoo_export = odoo_export.rename(columns={
        'Date': 'date',            # Reconnu par Odoo
        'Libellé': 'payment_ref',  # Champ standard pour la communication bancaire
        'Référence': 'ref'         # Champ de référence optionnel
    })
    
    # 2. Calcul du montant unique signé (Crucial pour Odoo)
    # Débit (sortie) = Négatif | Crédit (entrée) = Positif
    odoo_export['amount'] = odoo_export['Crédit'].fillna(0) - odoo_export['Débit'].fillna(0)
    
    # 3. Nettoyage de la colonne référence
    # Si c'est 0 ou vide, on laisse vide pour ne pas polluer Odoo
    odoo_export['ref'] = odoo_export['ref'].replace(0, '').replace('0.0', '')

    # 4. Sélection des colonnes essentielles uniquement
    # On ne garde que ce dont Odoo a besoin pour éviter les erreurs de mapping
    final_csv = odoo_export[['date', 'payment_ref', 'amount', 'ref']]
    
    st.dataframe(final_csv, use_container_width=True)

    # Bouton de téléchargement
    csv_buffer = io.StringIO()
    # On utilise l'encodage 'utf-8' simple car Odoo le gère très bien
    final_csv.to_csv(csv_buffer, index=False, encoding='utf-8')
    
    st.download_button(
        label="📥 Télécharger le CSV optimisé pour Odoo",
        data=csv_buffer.getvalue(),
        file_name=f"ODOO_READY_{st.session_state.banque_selectionnee}.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True
    )

    st.success("✅ Fichier prêt ! Allez dans Odoo > Comptabilité > Journal Banque > Favoris > Importer des enregistrements.")
