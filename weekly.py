import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import yfinance as yf
from pandas.tseries.offsets import BDay
import pandas_market_calendars as mcal 

# Configuração de tema claro para gráficos Plotly
import plotly.io as pio
pio.templates.default = "plotly_white"

# ==============================================================================
# CONFIGURAÇÃO DE CALENDÁRIO BRASILEIRO (ANBIMA) - ALINHAMENTO COM R
# ==============================================================================
# Usa calendário B3 (Bolsa brasileira) que segue feriados ANBIMA
try:
    calendario_br = mcal.get_calendar('B3')
except:
    # Fallback: Se B3 não estiver disponível, usa NYSE e avisa
    calendario_br = mcal.get_calendar('NYSE')
    st.warning("Calendário B3 não disponível. Usando NYSE como alternativa.")

def eh_dia_util_br(data):
    """Verifica se uma data é dia útil no calendário brasileiro (ANBIMA/B3)."""
    try:
        data_norm = pd.Timestamp(data).normalize()
        schedule = calendario_br.schedule(start_date=data_norm, end_date=data_norm)
        return len(schedule) > 0
    except:
        # Fallback: verifica apenas se não é fim de semana
        return data.weekday() < 5

def calcular_sexta_feira_semana_anterior(data_ref):
    """
    Calcula a sexta-feira (ou último dia útil) da semana ANTERIOR.
    Retrocede para a semana anterior e encontra a sexta-feira útil.
    """
    data_aux = pd.Timestamp(data_ref)
    
    # Retrocede para a semana anterior (7 dias ou mais)
    # Se estamos em uma segunda-feira, retroceder 7 dias nos leva para a segunda anterior
    # Queremos a sexta da semana anterior
    
    # Primeiro, vamos para o início desta semana (segunda-feira)
    dias_desde_segunda = data_aux.weekday()  # 0=segunda, 6=domingo
    inicio_semana_atual = data_aux - timedelta(days=dias_desde_segunda)
    
    # Agora retrocedemos 3 dias para chegar na sexta da semana anterior
    sexta_semana_anterior = inicio_semana_atual - timedelta(days=3)
    
    # Garante que é dia útil (retrocede se necessário)
    tentativas = 0
    while not eh_dia_util_br(sexta_semana_anterior) and tentativas < 10:
        sexta_semana_anterior = sexta_semana_anterior - timedelta(days=1)
        tentativas += 1
    
    return sexta_semana_anterior

def calcular_sexta_feira_semana_retrasada(data_ref):
    """
    Calcula a sexta-feira (ou último dia útil) de DUAS semanas atrás.
    Para cálculo da "semana passada completa".
    """
    data_aux = pd.Timestamp(data_ref)
    
    # Primeiro, vamos para o início desta semana (segunda-feira)
    dias_desde_segunda = data_aux.weekday()  # 0=segunda, 6=domingo
    inicio_semana_atual = data_aux - timedelta(days=dias_desde_segunda)
    
    # Retrocedemos 10 dias (7 dias de uma semana + 3 para chegar na sexta anterior)
    sexta_semana_retrasada = inicio_semana_atual - timedelta(days=10)
    
    # Garante que é dia útil (retrocede se necessário)
    tentativas = 0
    while not eh_dia_util_br(sexta_semana_retrasada) and tentativas < 10:
        sexta_semana_retrasada = sexta_semana_retrasada - timedelta(days=1)
        tentativas += 1
    
    return sexta_semana_retrasada

def calcular_sexta_feira_semana_atual(data_ref):
    """
    Calcula a sexta-feira (ou último dia útil) da semana ATUAL.
    Se data_ref é antes da sexta desta semana, usa o último dia útil disponível até data_ref.
    """
    data_aux = pd.Timestamp(data_ref)
    
    # Calcula quantos dias faltam para sexta (4 = sexta-feira)
    dias_ate_sexta = 4 - data_aux.weekday()
    
    if dias_ate_sexta >= 0:
        # Ainda não é sexta, ou é sexta
        sexta_desta_semana = data_aux + timedelta(days=dias_ate_sexta)
    else:
        # Já passou da sexta (é sábado ou domingo)
        # Retrocede para a sexta
        sexta_desta_semana = data_aux - timedelta(days=abs(dias_ate_sexta + 2))
    
    # Se a sexta calculada é posterior a data_ref, usa data_ref
    if sexta_desta_semana > data_aux:
        sexta_desta_semana = data_aux
    
    # Garante que é dia útil (retrocede se necessário)
    tentativas = 0
    while not eh_dia_util_br(sexta_desta_semana) and tentativas < 10:
        sexta_desta_semana = sexta_desta_semana - timedelta(days=1)
        tentativas += 1
    
    return sexta_desta_semana

def calcular_ultimo_dia_util_mes_anterior(data_ref):
    """
    Calcula o último dia útil do mês ANTERIOR.
    Lógica alinhada com script R para cálculo de MTD.
    """
    # Primeiro dia do mês atual
    primeiro_dia_mes = data_ref.replace(day=1)
    
    # Retrocede para o último dia do mês anterior
    ultimo_dia_mes_anterior = primeiro_dia_mes - timedelta(days=1)
    
    # Retrocede até encontrar um dia útil (máximo 31 dias de busca)
    data_aux = ultimo_dia_mes_anterior
    tentativas = 0
    
    while not eh_dia_util_br(data_aux) and tentativas < 31:
        data_aux = data_aux - timedelta(days=1)
        tentativas += 1
    
    return data_aux

def calcular_ultimo_dia_util_ano_anterior(data_ref):
    """
    Calcula o último dia útil do ano ANTERIOR.
    Lógica para cálculo de YTD.
    """
    # Último dia do ano anterior (31 de dezembro)
    ano_anterior = data_ref.year - 1
    ultimo_dia_ano_anterior = datetime(ano_anterior, 12, 31)
    
    # Retrocede até encontrar um dia útil
    data_aux = ultimo_dia_ano_anterior
    tentativas = 0
    
    while not eh_dia_util_br(data_aux) and tentativas < 10:
        data_aux = data_aux - timedelta(days=1)
        tentativas += 1
    
    return data_aux

# ==============================================================================
# 1. CONFIGURAÇÃO VISUAL (IDENTIDADE GHIA - MODO ESCURO SIDEBAR)
# ==============================================================================
st.set_page_config(
    page_title="Weekly Dashboard - Ghia", 
    layout="wide", 
    page_icon="www/favicon.png",
    initial_sidebar_state="expanded",
    menu_items=None
)

st.markdown("""
<style>
    /* Importar fonte Plus Jakarta Sans do Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
    
    /* Aplicar fonte globalmente */
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    /* Aplicar em todos os elementos principais */
    * {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
    }
    
    /* SIDEBAR: Tema Claro com Azul Ghia - SEMPRE VISÍVEL */
    [data-testid="stSidebar"] { 
        min-width: 250px !important; 
        max-width: 300px !important;
        width: 280px !important;
        background-color: #F8F9FA !important;
        border-right: 2px solid #E9ECEF;
        position: relative !important;
        transform: none !important;
        transition: none !important;
    }
    
    /* Remove botão de colapsar da sidebar - CORRIGIDO */
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapseButton"],
    button[kind="header"],
    button[kind="headerNoPadding"] {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
    }
    
    /* Garante que a sidebar nunca seja colapsada */
    [data-testid="stSidebar"][aria-expanded="false"] {
        transform: none !important;
        margin-left: 0 !important;
    }
    
    /* Ajusta margem do conteúdo principal para compensar sidebar fixa */
    .main .block-container {
        padding-left: 2rem !important;
    }
    
    /* Ajuste de padding do container principal */
    .block-container { 
        padding-top: 2rem; 
        padding-bottom: 3rem;
        background-color: #FFFFFF;
    }
    
    /* Força fundo branco em toda a página */
    .main, .stApp, .appview-container {
        background-color: #FFFFFF !important;
    }
    
    /* Remove qualquer fundo escuro de divs e containers */
    div, section, article, main {
        background-color: transparent !important;
    }
    
    /* Força tema claro em gráficos Plotly */
    .js-plotly-plot .plotly, .plotly {
        background-color: #FFFFFF !important;
    }
    
    /* Força tema claro em tabelas/dataframes - o Streamlit usa canvas virtualizado */
    /* Não forçar cores via CSS pois o dataframe é renderizado em canvas */
    [data-testid="stDataFrame"] {
        background-color: #FFFFFF !important;
    }
    
    /* Força background branco no block-container */
    .block-container {
        background-color: #FFFFFF !important;
    }
    
    /* Garante visibilidade de todos os elementos de texto */
    .stMarkdown, .stMarkdown p, .stMarkdown div, .stMarkdown span {
        color: #2C3E50 !important;
        background-color: transparent !important;
    }
    
    /* Força todos os elementos da área principal com fundo branco */
    [data-testid="stAppViewContainer"],
    [data-testid="stMainBlockContainer"] {
        background-color: #FFFFFF !important;
    }
    
    /* Info boxes e alerts com fundo claro */
    .stAlert, .element-container {
        background-color: transparent !important;
    }
    
    /* Força cor de texto em elementos de texto, preservando ícones */
    .main p, .main label, .main h1, .main h2, .main h3, .main h4, .main h5, .main h6 {
        color: #2C3E50 !important;
    }
    
    /* Preserva ícones e elementos especiais do Streamlit */
    [data-testid*="Icon"],
    [class*="icon"],
    [class*="Icon"],
    .material-icons,
    .material-icons-outlined {
        color: inherit !important;
        font-family: 'Material Icons' !important;
    }
    
    /* Expanders da sidebar - fundo branco, texto azul, negrito */
    [data-testid="stSidebar"] details summary {
        background-color: #FFFFFF !important;
        border: 1px solid #DEE2E6 !important;
        border-radius: 5px !important;
        padding: 0.75rem 1rem !important;
    }
    
    /* Força cor azul no texto do expander - sobrescreve .main p */
    [data-testid="stSidebar"] details summary p,
    [data-testid="stSidebar"] details summary span,
    [data-testid="stSidebar"] details summary div,
    [data-testid="stSidebar"] details summary [data-testid="stMarkdownContainer"] p {
        color: #189CD8 !important;
        font-weight: 700 !important;
        background-color: transparent !important;
    }
    
    /* Oculta ícone keyboard_arrow no expander */
    [data-testid="stSidebar"] details summary span[data-testid="stIconMaterial"] {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        height: 0 !important;
        opacity: 0 !important;
    }

    
    /* Títulos da Sidebar em Azul Ghia */
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3 {
        color: #189CD8 !important;
        font-weight: 700 !important;
    }
    
    /* Labels da Sidebar */
    [data-testid="stSidebar"] label {
        color: #2C3E50 !important;
        font-weight: 500 !important;
    }
    
    /* Textos da Sidebar */
    [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p {
        color: #495057 !important;
    }
    
    /* Captions da Sidebar */
    [data-testid="stSidebar"] .stCaption {
        color: #2C3E50 !important;
    }
    
    /* Inputs da Sidebar */
    [data-testid="stSidebar"] input {
        color: #2C3E50 !important;
        background-color: #FFFFFF !important;
        border: 1px solid #DEE2E6 !important;
        border-radius: 5px !important;
    }
    
    /* Ícone de mostrar/ocultar senha - seletores corretos baseados no HTML real */
    [data-testid="stSidebar"] button[aria-label*="password"],
    [data-testid="stSidebar"] button[title*="password"] {
        opacity: 1 !important;
        visibility: visible !important;
        display: inline-flex !important;
    }
    
    [data-testid="stSidebar"] button[aria-label*="password"] svg,
    [data-testid="stSidebar"] button[title*="password"] svg {
        color: #189CD8 !important;
        fill: #189CD8 !important;
        opacity: 1 !important;
        visibility: visible !important;
    }
    
    [data-testid="stSidebar"] button[aria-label*="password"] svg path,
    [data-testid="stSidebar"] button[title*="password"] svg path {
        fill: #189CD8 !important;
        stroke: #189CD8 !important;
    }
    
    /* Text inputs em toda a página */
    input[type="text"],
    input[type="password"],
    input[type="number"],
    input[type="date"],
    textarea {
        color: #2C3E50 !important;
        background-color: #F8F9FA !important;
        border: 1px solid #DEE2E6 !important;
    }
    
    /* Botões - sempre visíveis e na cor Ghia - seletores corretos */
    button[data-testid="stBaseButton-secondary"],
    [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
        background-color: #189CD8 !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 5px !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
        opacity: 1 !important;
        visibility: visible !important;
        display: block !important;
    }
    
    /* Garante texto branco e negrito em botões - FORÇA MÁXIMA com especificidade */
    [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] *,
    [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] p,
    [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] span,
    [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] div {
        color: #FFFFFF !important;
        font-weight: 700 !important;
        background-color: transparent !important;
    }
    [data-testid="stSidebar"] .stButton > button span,
    [data-testid="stSidebar"] .stButton > button div {
        color: #FFFFFF !important;
        font-weight: 700 !important;
        background-color: transparent !important;
    }
    
    /* Botões primários - texto branco e negrito */
    .stButton > button {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }
    
    .stButton > button span,
    .stButton > button div,
    .stButton > button p {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }
    
    .stButton > button:hover {
        background-color: #1485BA !important;
        box-shadow: 0 2px 8px rgba(24, 156, 216, 0.3) !important;
    }
    
    /* Radio buttons - melhor visibilidade */
    [data-testid="stSidebar"] .stRadio > div {
        background-color: rgba(255, 255, 255, 0.05) !important;
        border-radius: 8px !important;
        padding: 8px !important;
    }
    
    [data-testid="stSidebar"] .stRadio > div label {
        background-color: rgba(255, 255, 255, 0.1) !important;
        border-radius: 6px !important;
        padding: 8px 12px !important;
        margin: 4px 0 !important;
        cursor: pointer !important;
        transition: all 0.2s !important;
    }
    
    [data-testid="stSidebar"] .stRadio > div label:hover {
        background-color: rgba(255, 255, 255, 0.15) !important;
    }
    
    [data-testid="stSidebar"] .stRadio > div label[data-checked="true"],
    [data-testid="stSidebar"] .stRadio > div label:has(input:checked) {
        background-color: rgba(24, 156, 216, 0.3) !important;
        border: 2px solid #189CD8 !important;
        font-weight: 600 !important;
    }
    
    /* Tooltips - maior opacidade e fundo branco */
    [data-testid="stTooltipIcon"] {
        opacity: 0.8 !important;
    }
    
    [role="tooltip"],
    .stTooltip {
        background-color: rgba(255, 255, 255, 0.95) !important;
        color: #2C3E50 !important;
        border: 1px solid #E9ECEF !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
        opacity: 0.95 !important;
    }
    
    /* Títulos principais em Azul Ghia com negrito */
    h1 {
        color: #189CD8 !important;
        font-weight: 800 !important;
    }
    
    h2 {
        color: #189CD8 !important;
        font-weight: 700 !important;
    }
    
    h3 {
        color: #2C3E50 !important;
        font-weight: 700 !important;
    }
    
    h4 {
        color: #189CD8 !important;
        font-weight: 600 !important;
    }
    
    /* Spinner - texto preto */
    .stSpinner > div {
        color: #2C3E50 !important;
    }
    
    .stSpinner > div > div {
        color: #2C3E50 !important;
    }
    
    /* Abas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #F8F9FA;
        padding: 0.5rem;
        border-radius: 10px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: #FFFFFF;
        border-radius: 8px;
        color: #2C3E50;
        font-weight: 500;
        padding: 0.5rem 1.5rem;
        border: 1px solid #DEE2E6;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #189CD8 !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: 1px solid #189CD8 !important;
    }
    
    /* Regra geral: texto sobre fundo azul Ghia sempre branco e negrito */
    [style*="background-color: #189CD8"],
    [style*="background-color:#189CD8"],
    [style*="background: #189CD8"],
    [style*="background:#189CD8"] {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }
    
    [style*="background-color: #189CD8"] *,
    [style*="background-color:#189CD8"] *,
    [style*="background: #189CD8"] *,
    [style*="background:#189CD8"] * {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }
    
    /* Métricas */
    div[data-testid="stMetricValue"] { 
        font-size: 26px; 
        color: #189CD8 !important; 
        font-weight: 700;
    }
    
    div[data-testid="stMetricLabel"] {
        color: #2C3E50 !important;
        font-weight: 600 !important;
    }
    
    /* Força todos os textos comuns para preto/cinza escuro */
    p, span, div, li, td, th {
        color: #2C3E50 !important;
    }
    
    /* Captions e textos secundários */
    .stCaption, [data-testid="stCaptionContainer"], small {
        color: #495057 !important;
    }
    
    /* Info boxes (azul) - para mensagens de boas-vindas */
    [data-testid="stAlert"][data-baseweb="notification"][kind="info"],
    [data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
        background-color: #D1ECF1 !important;
        border-left: 4px solid #189CD8 !important;
        color: #0C5460 !important;
    }
    
    [data-testid="stAlert"][data-baseweb="notification"][kind="info"] *,
    [data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) * {
        color: #0C5460 !important;
    }
    
    /* Botões no dashboard principal (fora da sidebar) */
    .main button[data-testid="stBaseButton-secondary"],
    .main button[kind="secondary"] {
        background-color: #189CD8 !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 5px !important;
        padding: 0.5rem 1rem !important;
    }
    
    .main button[data-testid="stBaseButton-secondary"] *,
    .main button[kind="secondary"] * {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }
    
    /* Tabs do Dashboard - Aba Selecionada */
    button[data-testid="stTab"][aria-selected="true"] {
        background-color: #189CD8 !important;
        color: #FFFFFF !important;
        border-bottom: 3px solid #189CD8 !important;
        font-weight: 700 !important;
    }
    
    button[data-testid="stTab"][aria-selected="true"] *,
    button[data-testid="stTab"][aria-selected="true"] p {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }
    
    /* Tabs do Dashboard - Abas Não Selecionadas */
    button[data-testid="stTab"][aria-selected="false"] {
        background-color: #F8F9FA !important;
        color: #495057 !important;
        border-bottom: 2px solid #DEE2E6 !important;
    }
    
    button[data-testid="stTab"][aria-selected="false"] *,
    button[data-testid="stTab"][aria-selected="false"] p {
        color: #495057 !important;
    }
    
    /* Hover nas tabs */
    button[data-testid="stTab"]:hover {
        background-color: #E9ECEF !important;
    }
    
    button[data-testid="stTab"][aria-selected="true"]:hover {
        background-color: #1589C0 !important;
    }
    
    /* Expanders no dashboard - fundo branco, texto visível */
    .main details summary,
    .main [data-testid="stExpander"] summary,
    .stExpander details summary {
        background-color: #FFFFFF !important;
        color: #189CD8 !important;
        font-weight: 700 !important;
        border: 1px solid #DEE2E6 !important;
        border-radius: 5px !important;
        padding: 0.75rem 1rem !important;
    }
    
    .main details summary *,
    .main [data-testid="stExpander"] summary *,
    .stExpander details summary *,
    [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] p {
        color: #189CD8 !important;
        font-weight: 700 !important;
    }
    
    /* Oculta TODOS os ícones keyboard_arrow em qualquer lugar - CORRIGIDO */
    span[data-testid="stIconMaterial"],
    [data-testid="stSidebarCollapseButton"] span[data-testid="stIconMaterial"],
    .stExpander span[data-testid="stIconMaterial"] {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        height: 0 !important;
        opacity: 0 !important;
        font-size: 0 !important;
        overflow: hidden !important;
    }
    
    /* Oculta texto dentro de ícones Material */
    span[data-testid="stIconMaterial"]::before,
    span[data-testid="stIconMaterial"]::after {
        content: "" !important;
        display: none !important;
    }
    
    /* Selectbox (dropdown) - fundo branco, texto visível */
    [data-baseweb="select"],
    [data-testid="stSelectbox"] > div,
    [data-testid="stSelectbox"] [role="combobox"] {
        background-color: #FFFFFF !important;
        color: #2C3E50 !important;
        border: 1px solid #CED4DA !important;
    }
    
    /* Texto dentro do selectbox */
    [data-baseweb="select"] *,
    [data-testid="stSelectbox"] * {
        color: #2C3E50 !important;
    }
    
    /* Menu dropdown do selectbox */
    [role="listbox"],
    [data-baseweb="popover"] ul {
        background-color: #FFFFFF !important;
        color: #2C3E50 !important;
        border: 1px solid #CED4DA !important;
    }
    
    /* Opções do dropdown */
    [role="option"],
    [data-baseweb="popover"] li {
        background-color: #FFFFFF !important;
        color: #2C3E50 !important;
    }
    
    /* Opção selecionada no dropdown */
    [role="option"][aria-selected="true"],
    [data-baseweb="popover"] li:hover {
        background-color: #E9ECEF !important;
        color: #189CD8 !important;
    }
    
    /* Mantém botão de toggle da sidebar visível */
    header[data-testid="stHeader"] {
        visibility: visible !important;
        background-color: transparent;
    }
    
    /* Oculta apenas o menu hamburguer e outros elementos do header */
    header[data-testid="stHeader"] > div:first-child {
        visibility: hidden;
    }
    
    /* Mantém o botão de colapsar/expandir sidebar sempre visível */
    button[kind="header"] {
        visibility: visible !important;
    }
    
    /* Estilo de Tabelas */
    [data-testid="stDataFrame"] { 
        border: 1px solid #DEE2E6;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    /* Expanders */
    .streamlit-expanderHeader {
        background-color: #F8F9FA !important;
        color: #189CD8 !important;
        font-weight: 600 !important;
        border: 1px solid #DEE2E6 !important;
        border-radius: 5px !important;
    }
    
    /* Selectbox e inputs */
    [data-baseweb="select"] {
        background-color: #F8F9FA !important;
    }
    
    /* Checkbox */
    [data-testid="stCheckbox"] label {
        font-weight: 500 !important;
        color: #495057 !important;
    }
    
    /* Dividers (linhas horizontais) */
    hr {
        border-color: #DEE2E6 !important;
    }
    
    /* Info boxes */
    .stAlert {
        background-color: #E3F2FD !important;
        border-left: 4px solid #189CD8 !important;
        color: #2C3E50 !important;
    }
    
    /* Success boxes */
    .stSuccess {
        background-color: #D4EDDA !important;
        border-left: 4px solid #28A745 !important;
    }
    
    /* Date picker calendars - fundo branco com 80% opacidade */
    [data-baseweb="calendar"],
    [data-baseweb="popover"],
    .stDateInput [data-baseweb="popover"] {
        background-color: rgba(255, 255, 255, 0.8) !important;
        backdrop-filter: blur(10px) !important;
    }
    
    [data-baseweb="calendar"] button,
    [data-baseweb="calendar"] div {
        background-color: transparent !important;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. DEFINIÇÃO DE ATIVOS (ORDEM EXATA DO NOVO PAYLOAD)
# ==============================================================================

# ATENÇÃO: Esta lista deve seguir RIGOROSAMENTE a ordem do parâmetro 'x' da nova URL.
# Sem duplicatas de CDI no meio.
ORDEM_ATIVOS_API = [# Carteiras
    "AD_Agressivo_Modelo",	"AD_Moderado_Modelo",	"AD_Conservador_Modelo",	"AD_Ultra_Modelo",
    "GhiaAAAgressivoIntTot",	"GhiaAAModeradoIntTot",	"GhiaAAConservadorIntTot",	"CDI",	
    
    # FIIs
    "Ghia_FIIs", "ifix",	"HGCR11",	"RBRR11",	"TRXF11",	"PVBI11",	"BRCO11",	"KNCR11",
    "MCRE11",	"RBRX11",	"HSML11",	"KNSC11",	"ALZR11",	"BTLG11",	"MCCI11",	"HGLG11",
    
    # RF
    "43.105.224/0001-70",	"34.431.610/0001-61", "36.352.376/0001-02",	"52.155.414/0001-93", 
    "17.313.316/0001-36_unica", "50.716.952/0001-84_unica",	"32.990.051/0001-02_subclasse1",	
    "32.238.591/0001-26",	"34.583.819/0001-40_unica",	"23.034.819/0001-75",	"60.431.592/0001-28_unica",	
    
    # Multimercados
    "28.947.266/0001-65",	"29.732.926/0001-53",	"38.180.248/0001-54",	"24.193.691/0001-55",
    "30.521.581/0001-78",	"51.133.792/0001-03",	"36.017.731/0001-97",	"52.155.544/0001-26",
    "35.726.908/0001-61",	"41.776.752/0001-26_subclasse1",
    
    # Ações
    "08.830.947/0001-31",	"IBOV",	"26.956.042/0001-94",	"11.145.320/0001-56",	"73.232.530/0001-39",
    "09.412.822/0001-54",	"61.709.249/0001-65",
    
    # Long Horizon
    "lh_income",	"LH_ShortDuration",	"lh_conservative",	"lh_balanced",	"lh_moderate",	"LH_Aggressive",	"LH_Equity"

]

# Mapa DE (Nome API ou CNPJ) -> PARA (Nome Legível no Dashboard)
MAPA_NOMES = {
    # Carteiras Modelo
    "AD_Agressivo_Modelo": "Agressivo (Prod)", "AD_Moderado_Modelo": "Moderado (Prod)",
    "AD_Conservador_Modelo": "Conservador (Prod)", "AD_Ultra_Modelo": "Ultra (Prod)",
    "GhiaAAAgressivoIntTot": "Agressivo (Ind)", "GhiaAAModeradoIntTot": "Moderado (Ind)",
    "GhiaAAConservadorIntTot": "Conservador (Ind)",
    
    # Benchmarks
    "CDI": "CDI", "Ghia_FIIs": "Ghia FIIs", "ifix": "IFIX", "IBOV": "Ibovespa",
    
    # FIIs
    "HGCR11": "HGCR11", "RBRR11": "RBRR11", "TRXF11": "TRXF11", "PVBI11": "PVBI11", 
    "BRCO11": "BRCO11", "KNCR11": "KNCR11", "MCRE11": "MCRE11", "RBRX11": "RBRX11", 
    "HSML11": "HSML11", "KNSC11": "KNSC11", "ALZR11": "ALZR11", "BTLG11": "BTLG11", 
    "MCCI11": "MCCI11", "HGLG11": "HGLG11",
    
    # Renda Fixa (CNPJs com pontos - compatível com ORDEM_ATIVOS_API)
    "43.105.224/0001-70": "Ghia Sul 90", "34.431.610/0001-61": "Root Capital",
    "36.352.376/0001-02": "Sparta Max", "52.155.414/0001-93": "Ghia RF",
    "17.313.316/0001-36_unica": "Valora", "50.716.952/0001-84_unica": "M8",
    "32.990.051/0001-02_subclasse1": "Kinea Oportunidade", "32.238.591/0001-26": "Angá High Yield",
    "34.583.819/0001-40_unica": "Solis Antares", "23.034.819/0001-75": "Angá Crédito",
    "60.431.592/0001-28_unica": "FIDC Kinea",
    
    # Multimercados (CNPJs com pontos - compatível com ORDEM_ATIVOS_API)
    "28.947.266/0001-65": "Vertex", "29.732.926/0001-53": "Ibiuna Long Short", 
    "38.180.248/0001-54": "Ace Capital", "24.193.691/0001-55": "SPX Nimitz", 
    "30.521.581/0001-78": "Zeta", "51.133.792/0001-03": "Mar Absoluto", 
    "36.017.731/0001-97": "Genoa Capital", "52.155.544/0001-26": "Ghia MM", 
    "35.726.908/0001-61": "Capstone", "41.776.752/0001-26_subclasse1": "Zeus", 
    
    # Ações (CNPJs com pontos - compatível com ORDEM_ATIVOS_API)
    "08.830.947/0001-31": "Guepardo", "26.956.042/0001-94": "Oceana", 
    "11.145.320/0001-56": "Atmos", "73.232.530/0001-39": "Dynamo", 
    "09.412.822/0001-54": "Squadra Long Only", "61.709.249/0001-65": "Ghia RV",
    
    # Long Horizon
    "lh_income": "LH Income", "LH_ShortDuration": "LH Short Duration",
    "lh_conservative": "LH Conservative", "lh_balanced": "LH Balanced",
    "lh_moderate": "LH Moderate", "LH_Aggressive": "LH Aggressive", "LH_Equity": "LH Equity"
}

# Categorias Atualizadas (SEM categoria Benchmarks - CDI, IFIX e Ibovespa distribuídos)
CATEGORIAS = {
    "Carteiras Modelo": ["Agressivo (Prod)", "Moderado (Prod)", "Conservador (Prod)", "Ultra (Prod)", "Agressivo (Ind)", "Moderado (Ind)", "Conservador (Ind)"],
    "FIIs": ["Ghia FIIs", "IFIX", "HGCR11", "RBRR11", "TRXF11", "PVBI11", "BRCO11", "KNCR11", "MCRE11", "RBRX11", "HSML11", "KNSC11", "ALZR11", "BTLG11", "MCCI11", "HGLG11"],
    "Renda Fixa": ["CDI", "Ghia Sul 90", "Root Capital", "Sparta Max", "Ghia RF", "Valora", "M8", "Kinea Oportunidade", "Angá High Yield", "Solis Antares", "Angá Crédito", "FIDC Kinea"],
    "Multimercados": ["Vertex", "Ibiuna Long Short", "Ace Capital", "SPX Nimitz", "Zeta", "Mar Absoluto", "Genoa Capital", "Ghia MM", "Capstone", "Zeus"],
    "Ações": ["Ibovespa", "Guepardo", "Oceana", "Atmos", "Dynamo", "Squadra Long Only", "Ghia RV"],
    "Long Horizon": ["LH Income", "LH Short Duration", "LH Conservative", "LH Balanced", "LH Moderate", "LH Aggressive", "LH Equity"],
    "LH Produtos (ETFs)": ["CSPX", "EIMI", "CEUU", "IJPA", "ISFD", "LQDA", "ERNA", "FLOA", "IB01", "CBU0", "IHYA", "JPEA"]
}

# Datas de Inception (ITD - Inception to Date) por categoria
DATAS_INCEPTION = {
    "FIIs": datetime(2024, 8, 30),
    "Renda Fixa": datetime(2025, 1, 17),
    "Multimercados": datetime(2023, 11, 21),
    "Ações": datetime(2025, 8, 7)
}

# Produtos Ghia para destaque
PRODUTOS_GHIA = [
    "Agressivo (Prod)", "Moderado (Prod)", "Conservador (Prod)", "Ultra (Prod)",
    "Agressivo (Ind)", "Moderado (Ind)", "Conservador (Ind)",
    "Ghia FIIs", "Ghia Sul 90", "Ghia RF", "Ghia MM", "Ghia RV"
]

# ==============================================================================
# 3. EXTRAÇÃO DE DADOS (API COMDINHEIRO - PAYLOAD LIMPO)
# ==============================================================================

@st.cache_data(ttl=3600*4, show_spinner=False)
def get_data_comdinheiro(username, password, data_inicio_str, data_fim_str, _cache_version="v2"):
    """
    Executa a requisição POST usando a nova estrutura limpa.
    data_inicio_str e data_fim_str devem estar no formato DDMMYYYY
    _cache_version: parâmetro para forçar limpeza de cache (use _ para ignorar no hash)
    """
    url = "https://api.comdinheiro.com.br/v1/ep1/import-data"
    
    # Payload 'x' - Lista de ativos separados por %2B (codificação URL de +)
    # IMPORTANTE: Todos os ativos devem ter %2B ANTES, inclusive o último (LH_Equity)
    lista_x = "AD_Agressivo_Modelo%2BAD_Moderado_Modelo%2BAD_Conservador_Modelo%2BAD_Ultra_Modelo%2BGhiaAAAgressivoIntTot%2BGhiaAAModeradoIntTot%2BGhiaAAConservadorIntTot%2BCDI%2BGhia_FIIs%2Bifix%2BHGCR11%2BRBRR11%2BTRXF11%2BPVBI11%2BBRCO11%2BKNCR11%2BMCRE11%2BRBRX11%2BHSML11%2BKNSC11%2BALZR11%2BBTLG11%2BMCCI11%2BHGLG11%2B43105224000170%2B34431610000161%2B36352376000102%2B52155414000193%2B17313316000136_unica%2B50716952000184_unica%2B32990051000102_subclasse1%2B32238591000126%2B34583819000140_unica%2B23034819000175%2B60431592000128_unica%2B28947266000165%2B29732926000153%2B38180248000154%2B24193691000155%2B30521581000178%2B51133792000103%2B36017731000197%2B52155544000126%2B35726908000161%2B41776752000126_subclasse1%2B08830947000131%2BIBOV%2B26956042000194%2B11145320000156%2B73232530000139%2B09412822000154%2B61709249000165%2Blh_income%2BLH_ShortDuration%2Blh_conservative%2Blh_balanced%2Blh_moderate%2BLH_Aggressive%2BLH_Equity"
    
    # URL interna montada com datas dinâmicas
    # IMPORTANTE: A API espera url_interna COM codificação URL nos parâmetros
    # Mas as datas devem ser inseridas diretamente (requests fará encoding do payload)
    url_interna = (
        f"HistoricoCotacao002.php?x={lista_x}"
        f"&data_ini={data_inicio_str}&data_fim={data_fim_str}"
        "&pagina=1&d=MOEDA_ORIGINAL&g=1&m=0&info_desejada=retorno&retorno=discreto"
        "&tipo_data=du_br&tipo_ajuste=todosajustes&num_casas=2&enviar_email=0"
        "&ordem_legenda=1&cabecalho_excel=modo1&classes_ativos=z1ci99jj7473"
        "&ordem_data=0&rent_acum=rent_acum&minY=&maxY=&deltaY="
        "&preco_nd_ant=0&base_num_indice=100&flag_num_indice=0"
        "&eixo_x=Data&startX=0&max_list_size=20&line_width=2"
        "&titulo_grafico=&legenda_eixoy=&tipo_grafico=line&script=&tooltip=unica"
    )
    
    payload = {
        'username': username,
        'password': password,
        'format': 'json3',
        'URL': url_interna
    }
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    # Armazena as datas solicitadas para debug
    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = {}
    st.session_state.debug_info['data_inicio_solicitada'] = data_inicio_str
    st.session_state.debug_info['data_fim_solicitada'] = data_fim_str
    st.session_state.debug_info['url_interna'] = url_interna
    
    # Retry automático (máximo 3 tentativas)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=60)
            response.raise_for_status()
            data_json = response.json()
            
            # Localiza dados
            rows = []
            if 'tables' in data_json:
                if 'tab1' in data_json['tables']:
                    rows = data_json['tables']['tab1']
                elif 'tab0' in data_json['tables']:
                    rows = data_json['tables']['tab0']
            
            if not rows:
                return None, "JSON retornado sem dados. Verifique as credenciais."
            
            # Se chegou aqui, sucesso - sai do loop
            break
            
        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries - 1:
                # Tenta novamente
                import time
                time.sleep(2)  # Espera 2 segundos antes de tentar novamente
                continue
            else:
                # Última tentativa falhou
                return None, (f"Erro de Conexão: API Comdinheiro não está respondendo.\n\n"
                            f"Possíveis causas:\n"
                            f"• API pode estar temporariamente fora do ar\n"
                            f"• Verifique sua conexão com a internet\n"
                            f"• Firewall pode estar bloqueando a conexão\n\n"
                            f"Tente novamente em alguns minutos.")
        
        except requests.exceptions.Timeout:
            return None, "Timeout: API não respondeu em 60 segundos. Tente reduzir o período de datas."
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return None, "Erro 401: Usuário ou senha incorretos"
            else:
                return None, f"Erro HTTP {e.response.status_code}: {str(e)}"
        
        except Exception as e:
            return None, f"Erro inesperado: {str(e)}"
    
    # Continua com o processamento normal se sucesso
    try:
            
        df = pd.DataFrame(rows)
        
        # Armazena informações de debug no session_state ANTES de qualquer processamento
        if 'debug_info' not in st.session_state:
            st.session_state.debug_info = {}
        
        # Salva estrutura original da API (transposta)
        st.session_state.debug_info['shape_original'] = df.shape
        st.session_state.debug_info['linhas_recebidas'] = df.shape[0]
        st.session_state.debug_info['colunas_recebidas'] = df.shape[1]
        
        # Salva CSV com dados brutos (sempre salva para análise)
        try:
            debug_file = f"debug_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(debug_file, index=False)
            st.session_state.debug_info['arquivo_salvo'] = debug_file
            st.session_state.debug_info['df_preview'] = df.head(10).copy()
        except Exception as e:
            st.session_state.debug_info['erro_debug'] = str(e)
        
        # TRANSPOSIÇÃO: API retorna transposto (linhas=ativos, cols=datas)
        # Primeira linha contém "Data" e as datas
        # Demais linhas: col[0]=nome_ativo, col[1..N]=valores
        # Precisamos transpor para: cols=[Data, Ativo1, Ativo2, ...], linhas=[data1, data2, ...]
        
        # Define primeira linha como header (datas)
        df_transposto = df.T
        df_transposto.columns = df_transposto.iloc[0]  # Primeira linha ("Data", ativo1, ativo2, ...) vira nome das colunas
        df_transposto = df_transposto.drop(df_transposto.index[0])  # Remove primeira linha
        df_transposto.reset_index(drop=True, inplace=True)
        
        # Limpa sufixos indevidos dos nomes das colunas (remove parâmetros de URL concatenados)
        df_transposto.columns = [col.split('&')[0] if '&' in str(col) else col for col in df_transposto.columns]
        
        # Agora df_transposto tem: colunas = ["Data", nome_ativo1, nome_ativo2, ...]
        # E cada linha é uma data com os valores de cada ativo
        df = df_transposto
        
        # Informações após transposição
        st.session_state.debug_info['shape_transposto'] = df.shape
        st.session_state.debug_info['ativos_encontrados'] = df.shape[1] - 1  # -1 por causa da coluna Data
        st.session_state.debug_info['datas_encontradas'] = df.shape[0]
        st.session_state.debug_info['colunas_apos_limpeza'] = list(df.columns)
        
        # EXEMPLO DE DADOS APÓS LIMPEZA (antes do pct_change)
        st.session_state.debug_info['primeiras_5_linhas_indices'] = df.head(5).to_dict()
            
        # Tratamento de datas e conversão de valores
        df['Data'] = pd.to_datetime(df['Data'], format="%d/%m/%Y", errors='coerce')
        
        # ALINHAMENTO COM R: Remove linhas com data inválida (filter(!is.na(date)))
        linhas_antes = len(df)
        df = df.dropna(subset=['Data'])
        linhas_removidas = linhas_antes - len(df)
        if linhas_removidas > 0:
            st.session_state.debug_info['linhas_data_invalida'] = linhas_removidas
        
        # CONVERSÃO: API Comdinheiro usa formato BR (vírgula decimal)
        # Nota importante: dependendo dos parâmetros da URL, a API pode retornar:
        # - retornos discretos (já em formato de retorno diário), ou
        # - níveis (índice/base 100, preço, etc.).
        # Aqui inferimos automaticamente o tipo para evitar aplicar pct_change() em série que já é retorno.
        # Inicializa dict para logging de valores inválidos
        valores_invalidos = {}
        
        # Armazena amostra ANTES da conversão para pct_change (para debug)
        amostra_antes_pct = {}
        
        # DEBUG CRÍTICO: Amostra do formato BRUTO antes de qualquer conversão
        amostra_valores_brutos = {}
        primeira_coluna_nao_data = [col for col in df.columns if col != 'Data'][0] if len(df.columns) > 1 else None
        
        if primeira_coluna_nao_data:
            valores_brutos = df[primeira_coluna_nao_data].head(5).tolist()
            amostra_valores_brutos[primeira_coluna_nao_data] = {
                'valores_originais': valores_brutos,
                'tipo_original': str(df[primeira_coluna_nao_data].dtype),
                'tem_virgula': any(',' in str(v) for v in valores_brutos if pd.notna(v)),
                'tem_ponto': any('.' in str(v) for v in valores_brutos if pd.notna(v))
            }
            st.session_state.debug_info['formato_bruto_api'] = amostra_valores_brutos
        
        def _inferir_tipo_serie_comdinheiro(serie: pd.Series) -> str:
            """Inferência heurística do tipo da série.

            Retorna um de:
            - 'retorno_decimal': série já é retorno diário em decimal (ex.: 0.002 = 0.2%)
            - 'retorno_percentual': série é retorno em pontos percentuais (ex.: 0.2 = 0.2%)
            - 'nivel': série é nível/índice (ex.: 100, 102.3, ...)
            """
            valores = pd.to_numeric(serie, errors='coerce').dropna()
            if valores.empty:
                return 'retorno_decimal'

            abs_vals = valores.abs()
            med_abs = float(abs_vals.median())
            p95_abs = float(abs_vals.quantile(0.95))

            # Níveis/índices normalmente têm magnitude bem maior que retornos.
            if med_abs > 10 or p95_abs > 50:
                return 'nivel'

            # Se o retorno estiver em "pontos percentuais" (0.5 = 0.5%),
            # a magnitude típica fica bem acima do que esperamos para retorno decimal diário.
            if med_abs > 0.2 and p95_abs <= 50:
                return 'retorno_percentual'

            return 'retorno_decimal'

        tipos_inferidos = {}

        for col in df.columns:
            if col != 'Data':
                # Armazena tipo ANTES da conversão
                tipo_antes = str(df[col].dtype)
                
                # Converte string para numérico
                if df[col].dtype == object:
                    # IMPORTANTE: API COMDINHEIRO usa formato brasileiro (vírgula como decimal)
                    # Remove pontos (separador de milhar) e converte vírgula para ponto (decimal)
                    # Ex: "1.234,56" → "1234.56" ou "100,25" → "100.25"
                    
                    # Armazena amostra ANTES da conversão
                    valores_antes_conversao = df[col].head(3).tolist()
                    
                    df[col] = df[col].astype(str).str.strip()
                    df[col] = df[col].str.replace('.', '', regex=False)  # Remove separador de milhar
                    df[col] = df[col].str.replace(',', '.', regex=False)  # VÍRGULA → PONTO (BR → EN)
                    
                    # Armazena amostra APÓS a conversão de string
                    valores_apos_conversao_string = df[col].head(3).tolist()
                    
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    # Armazena amostra APÓS conversão numérica
                    valores_apos_conversao_num = df[col].head(3).tolist()
                    
                    # Log detalhado da conversão
                    if col == primeira_coluna_nao_data:
                        st.session_state.debug_info['exemplo_conversao_detalhado'] = {
                            'ativo': col,
                            'tipo_antes': tipo_antes,
                            'tipo_depois': str(df[col].dtype),
                            'valores_antes': valores_antes_conversao,
                            'valores_apos_str': valores_apos_conversao_string,
                            'valores_apos_num': valores_apos_conversao_num
                        }
                    
                elif not pd.api.types.is_numeric_dtype(df[col]):
                    # Se não for object nem numérico, tenta converter diretamente
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Log de valores inválidos ANTES do pct_change (alinhamento com R: suppressWarnings)
                n_invalidos_antes = df[col].isna().sum()
                if n_invalidos_antes > 0:
                    valores_invalidos[col] = n_invalidos_antes
                
                # Armazena amostra dos valores numéricos ANTES do pct_change
                valores_validos = df[col].dropna()
                if len(valores_validos) > 0:
                    amostra_antes_pct[col] = {
                        'min': float(valores_validos.min()),
                        'max': float(valores_validos.max()),
                        'mean': float(valores_validos.mean()),
                        'primeiros_3': valores_validos.head(3).tolist()
                    }

                # NORMALIZAÇÃO (alinhamento com o R):
                # - Se a série já for retorno discreto, NÃO aplicar pct_change().
                # - Se a série for nível/índice, aí sim aplicamos pct_change() para obter retorno diário.
                tipo_serie = _inferir_tipo_serie_comdinheiro(df[col])
                tipos_inferidos[col] = tipo_serie

                if tipo_serie == 'nivel':
                    df[col] = df[col].pct_change()  # converte nível -> retorno diário
                elif tipo_serie == 'retorno_percentual':
                    df[col] = df[col] / 100.0  # pontos percentuais -> decimal
                else:
                    # retorno_decimal: mantém como está
                    df[col] = df[col]
            # Pega 3 ativos aleatórios para exibir
            import random
            ativos_sample = random.sample(list(amostra_antes_pct.keys()), min(3, len(amostra_antes_pct)))
            st.session_state.debug_info['amostra_indices_antes_pct'] = {k: amostra_antes_pct[k] for k in ativos_sample}

        if tipos_inferidos:
            # Salva uma amostra pequena para o painel de debug
            try:
                import random
                ativos_sample_tipos = random.sample(list(tipos_inferidos.keys()), min(15, len(tipos_inferidos)))
                st.session_state.debug_info['tipos_series_comdinheiro'] = {k: tipos_inferidos[k] for k in ativos_sample_tipos}
            except Exception:
                st.session_state.debug_info['tipos_series_comdinheiro'] = tipos_inferidos
        
        # Armazena valores inválidos no debug
        if valores_invalidos:
            st.session_state.debug_info['valores_invalidos_por_coluna'] = valores_invalidos
            st.session_state.debug_info['total_valores_invalidos'] = sum(valores_invalidos.values())
        
        # Remove linhas totalmente vazias (após normalização)
        df = df.dropna(subset=df.columns[1:], how='all')
        
        # VALIDAÇÃO: Detecta valores absurdos (retornos diários > 100% ou < -100%)
        # Isso indica erro na conversão numérica
        valores_absurdos = {}
        for col in df.columns:
            if col != 'Data':
                absurdos = df[col][(df[col] > 1.0) | (df[col] < -1.0)]
                if len(absurdos) > 0:
                    valores_absurdos[col] = {
                        'count': len(absurdos),
                        'max': float(absurdos.max()),
                        'min': float(absurdos.min()),
                        'sample': absurdos.head(3).tolist()
                    }
        
        if valores_absurdos:
            st.session_state.debug_info['valores_absurdos_detectados'] = valores_absurdos
            st.session_state.debug_info['warning_valores_absurdos'] = f"ALERTA: {len(valores_absurdos)} ativo(s) com retornos diários absurdos (>100% ou <-100%)"
        
        # EXEMPLO DE RETORNOS CALCULADOS (após pct_change)
        st.session_state.debug_info['primeiras_5_linhas_retornos'] = df.head(5).to_dict()
        
        # Renomeia
        df = df.rename(columns=MAPA_NOMES)
        
        # REMOÇÃO DE DUPLICATAS DE COLUNAS (Prevenção extra)
        df = df.loc[:, ~df.columns.duplicated()]
        
        df_sorted = df.sort_values('Data')
        
        # Informações de sucesso - protege contra datas NaT
        data_min = df_sorted['Data'].min()
        data_max = df_sorted['Data'].max()
        
        if pd.notna(data_min) and pd.notna(data_max):
            msg_sucesso = f"{len(df_sorted)} linhas | {data_min.strftime('%d/%m/%Y')} a {data_max.strftime('%d/%m/%Y')} | {len(df_sorted.columns)-1} ativos"
        else:
            msg_sucesso = f"{len(df_sorted)} linhas | {len(df_sorted.columns)-1} ativos"
        
        return df_sorted, msg_sucesso
        
    except Exception as e:
        return None, f"Erro no processamento dos dados: {str(e)}"

@st.cache_data(ttl=3600*12, show_spinner=False)
def get_data_yahoo(data_inicio, data_fim):
    """
    Extrai dados de ETFs offshore do Yahoo Finance (LH Produtos).
    Mesma lista do script R rentabilidadecarteirasV5.r
    Usa EXATAMENTE o mesmo período definido para a API Comdinheiro.
    Retorna DataFrame com retornos diários.
    """
    debug_yahoo = {}
    
    try:
        # Tickers dos produtos Long Horizon (EXATAMENTE como no script R)
        tickers = {
            "CSPX.L": "CSPX",      # S&P 500 ETF
            "EIMI.L": "EIMI",      # Emerging Markets ETF
            "CEUU.AS": "CEUU",     # Europe ETF
            "IJPA.L": "IJPA",      # Japan ETF
            "ISFD.L": "ISFD",      # Developed Markets ETF
            "LQDA.L": "LQDA",      # Liquid Alternatives ETF
            "ERNA.L": "ERNA",      # ESG ETF
            "FLOA.L": "FLOA",      # Floating Rate ETF
            "IB01.L": "IB01",      # Treasury Bond ETF
            "CBU0.L": "CBU0",      # Corporate Bond ETF
            "IHYA.L": "IHYA",      # High Yield ETF
            "JPEA.L": "JPEA"       # Japan Equity ETF
        }
        
        debug_yahoo['tickers_solicitados'] = list(tickers.keys())
        debug_yahoo['periodo'] = f"{data_inicio.strftime('%Y-%m-%d')} a {data_fim.strftime('%Y-%m-%d')}"
        
        # Baixa dados históricos - MESMO PERÍODO do Comdinheiro
        df = yf.download(
            list(tickers.keys()), 
            start=data_inicio,
            end=data_fim + pd.Timedelta(days=1),  # Yahoo usa end exclusive, então +1 dia
            progress=False,
            group_by='ticker'
        )
        
        debug_yahoo['df_baixado_shape'] = df.shape
        debug_yahoo['df_baixado_empty'] = df.empty
        debug_yahoo['df_columns'] = list(df.columns) if hasattr(df.columns, '__iter__') else str(df.columns)
        
        # Debug adicional: estrutura do MultiIndex
        if hasattr(df.columns, 'levels'):
            debug_yahoo['columns_is_multiindex'] = True
            debug_yahoo['columns_levels'] = [list(level) for level in df.columns.levels]
            debug_yahoo['columns_names'] = df.columns.names
        else:
            debug_yahoo['columns_is_multiindex'] = False
        
        # Debug: primeiras colunas disponíveis
        debug_yahoo['primeiras_colunas'] = [str(col) for col in df.columns[:10]]
        
        if df.empty:
            debug_yahoo['erro'] = "DataFrame vazio após yf.download"
            st.session_state.debug_info['yahoo_debug_detalhado'] = debug_yahoo
            return pd.DataFrame()
        
        # Determina qual coluna usar (Adj Close ou Close)
        # Alguns ETFs não têm Adj Close, então usamos Close como fallback
        if hasattr(df.columns, 'get_level_values'):
            colunas_disponiveis = df.columns.get_level_values(-1).unique().tolist()
        else:
            colunas_disponiveis = df.columns.tolist()
        
        debug_yahoo['colunas_disponiveis'] = colunas_disponiveis
        coluna_preco = 'Adj Close' if 'Adj Close' in colunas_disponiveis else 'Close'
        debug_yahoo['coluna_preco_usada'] = coluna_preco
        
        # Extrai preços e lida com estrutura MultiIndex
        if len(tickers) == 1:
            # Um único ticker: estrutura simples
            ticker = list(tickers.keys())[0]
            try:
                df_close = df[coluna_preco].to_frame()
                df_close.columns = [ticker]
                debug_yahoo['metodo_extracao'] = 'ticker_unico'
            except Exception as e:
                debug_yahoo['erro_ticker_unico'] = str(e)
                st.session_state.debug_info['yahoo_debug_detalhado'] = debug_yahoo
                return pd.DataFrame()
        else:
            # Múltiplos tickers: estrutura MultiIndex
            df_close = pd.DataFrame()
            
            # Tenta método 1: df[ticker][coluna_preco]
            try:
                df_close = pd.DataFrame({ticker: df[ticker][coluna_preco] for ticker in tickers.keys()})
                debug_yahoo['metodo_extracao'] = 'multiindex_ticker_primeiro'
                debug_yahoo['df_close_shape'] = df_close.shape
            except Exception as e:
                debug_yahoo['erro_metodo1'] = str(e)
                
                # Tenta método 2: df[coluna_preco]
                try:
                    df_close = df[coluna_preco]
                    debug_yahoo['metodo_extracao'] = 'multiindex_coluna_direta'
                    debug_yahoo['df_close_shape'] = df_close.shape
                except Exception as e2:
                    debug_yahoo['erro_metodo2'] = str(e2)
                    
                    # Tenta método 3: Itera pelas colunas do MultiIndex
                    try:
                        dados_close = {}
                        for ticker in tickers.keys():
                            # Procura coluna que contém o ticker e a coluna de preço
                            cols_ticker = [col for col in df.columns if ticker in str(col) and coluna_preco in str(col)]
                            if cols_ticker:
                                dados_close[ticker] = df[cols_ticker[0]]
                        
                        if dados_close:
                            df_close = pd.DataFrame(dados_close)
                            debug_yahoo['metodo_extracao'] = 'iteracao_manual'
                            debug_yahoo['df_close_shape'] = df_close.shape
                        else:
                            debug_yahoo['erro_metodo3'] = "Nenhuma coluna encontrada"
                            st.session_state.debug_info['yahoo_debug_detalhado'] = debug_yahoo
                            return pd.DataFrame()
                    except Exception as e3:
                        debug_yahoo['erro_metodo3'] = str(e3)
                        st.session_state.debug_info['yahoo_debug_detalhado'] = debug_yahoo
                        return pd.DataFrame()
        
        if df_close.empty:
            debug_yahoo['erro'] = "df_close vazio após extração"
            st.session_state.debug_info['yahoo_debug_detalhado'] = debug_yahoo
            return pd.DataFrame()
        
        debug_yahoo['df_close_colunas'] = list(df_close.columns)
        debug_yahoo['df_close_linhas'] = len(df_close)
        
        # IMPORTANTE: Yahoo Finance (yfinance) já retorna valores NUMÉRICOS com PONTO como decimal
        # NÃO precisa conversão de formato (diferente da API Comdinheiro que usa vírgula)
        # Exemplo Yahoo: 102.34 (já é float, não string)
        
        # Validação: Verifica se valores estão numéricos
        debug_yahoo['df_close_dtype_sample'] = {col: str(df_close[col].dtype) for col in list(df_close.columns)[:3]}
        
        # Calcula retornos diários (já em formato decimal correto)
        df_ret = df_close.pct_change().dropna()
        debug_yahoo['df_ret_shape'] = df_ret.shape
        
        df_ret.reset_index(inplace=True)
        df_ret = df_ret.rename(columns={"Date": "Data"})
        
        # CORREÇÃO: Remove timezone do yfinance (UTC) para compatibilidade com Comdinheiro (naive)
        # yfinance retorna datetime64[ns, UTC], Comdinheiro usa datetime64[ns] sem timezone
        # Sem isso, o merge cria tipos mistos e as comparações de datas falham
        if df_ret['Data'].dt.tz is not None:
            df_ret['Data'] = df_ret['Data'].dt.tz_localize(None)
        
        # Renomeia para nomes legíveis (remove extensões como .L, .AS)
        rename_map = {ticker: name for ticker, name in tickers.items()}
        df_ret = df_ret.rename(columns=rename_map)
        
        debug_yahoo['df_final_shape'] = df_ret.shape
        debug_yahoo['df_final_colunas'] = list(df_ret.columns)
        debug_yahoo['sucesso'] = True
        
        st.session_state.debug_info['yahoo_debug_detalhado'] = debug_yahoo
        
        return df_ret
        
    except Exception as e:
        debug_yahoo['erro_geral'] = str(e)
        debug_yahoo['erro_tipo'] = type(e).__name__
        st.session_state.debug_info['yahoo_debug_detalhado'] = debug_yahoo
        st.sidebar.warning(f"Yahoo Finance: {str(e)}")
        return pd.DataFrame()

# ==============================================================================
# 4. ENGINE DE CÁLCULO (COM CORREÇÃO DE INDEX)
# ==============================================================================

def calcular_metricas(df, periodo_nome, data_inicio, data_fim):
    # Usa > ao invés de >= para excluir a data de início
    # Os retornos na data_inicio referem-se à variação do dia anterior para data_inicio
    # Queremos apenas os retornos a partir do dia seguinte à data_inicio
    mask = (df['Data'] > data_inicio) & (df['Data'] <= data_fim)
    df_periodo = df.loc[mask].set_index('Data')
    
    if df_periodo.empty: return pd.DataFrame()
    
    # ALINHAMENTO COM R: Remove linhas totalmente vazias (filter(!is.na(Retorno)))
    df_periodo = df_periodo.dropna(how='all')
    
    if df_periodo.empty: return pd.DataFrame()
    
    retorno_cdi = df_periodo['CDI'] if 'CDI' in df_periodo.columns else None
    
    res = []
    for col in df_periodo.columns:
        # Processa CDI separadamente (sem Sharpe contra si mesmo)
        if col == 'CDI':
            serie_cdi = df_periodo[col].dropna()
            if len(serie_cdi) >= 2:
                ret_acum_cdi = np.prod(1 + serie_cdi[~serie_cdi.isna()]) - 1
                vol_cdi = serie_cdi.std(skipna=True) * np.sqrt(252)
                cum_cdi = (1 + serie_cdi).cumprod(skipna=True)
                peak_cdi = cum_cdi.cummax(skipna=True)
                dd_cdi = (cum_cdi - peak_cdi) / peak_cdi
                max_dd_cdi = dd_cdi.dropna().min() if len(dd_cdi.dropna()) > 0 else 0
                
                res.append({
                    "Ativo": col,
                    f"Retorno_{periodo_nome}": ret_acum_cdi,
                    f"Vol_{periodo_nome}": vol_cdi,
                    f"Sharpe_{periodo_nome}": 0,  # CDI não tem Sharpe contra si mesmo
                    f"MaxDD_{periodo_nome}": max_dd_cdi
                })
            continue
        
        # ALINHAMENTO COM R: Remove NAs da série (equivalente a na.rm = TRUE)
        serie = df_periodo[col].dropna()
        
        # Validação extra: verifica se ainda há NaN após dropna
        if serie.isna().any():
            serie = serie.dropna()
        
        if len(serie) < 2: continue
        
        # ALINHAMENTO COM R: prod(..., na.rm = TRUE)
        # Garante que não há NaN no cálculo
        ret_acum = np.prod(1 + serie[~serie.isna()]) - 1
        
        # ALINHAMENTO COM R: sd(..., na.rm = TRUE) * sqrt(252)
        # pandas .std() já ignora NaN por padrão, mas garantimos aqui
        vol = serie.std(skipna=True) * np.sqrt(252)
        
        sharpe = 0
        if retorno_cdi is not None:
            cdi_aligned = retorno_cdi.loc[serie.index]
            excesso = serie - cdi_aligned
            # ALINHAMENTO COM R: Remove NAs do excesso antes de calcular
            excesso = excesso.dropna()
            if len(excesso) > 0 and excesso.std(skipna=True) > 0:
                # Sharpe Ratio anualizado: retorno anualizado / volatilidade anualizada
                # Retorno anualizado = retorno_médio_diário * 252
                # Volatilidade anualizada = std_diário * sqrt(252)
                sharpe = (excesso.mean(skipna=True) * 252) / (excesso.std(skipna=True) * np.sqrt(252))
        
        # ALINHAMENTO COM R: calc_mdd com na.rm = TRUE
        cum = (1 + serie).cumprod(skipna=True)
        peak = cum.cummax(skipna=True)
        dd = (cum - peak) / peak
        # Remove NaNs antes de calcular o mínimo (equivalente a na.rm = TRUE)
        max_dd = dd.dropna().min() if len(dd.dropna()) > 0 else 0
        
        res.append({
            "Ativo": col,
            f"Retorno_{periodo_nome}": ret_acum,
            f"Vol_{periodo_nome}": vol,
            f"Sharpe_{periodo_nome}": sharpe,
            f"MaxDD_{periodo_nome}": max_dd
        })
        
    return pd.DataFrame(res)

def calcular_retornos_mensais(df, ativo):
    """
    Calcula retornos mensais de um ativo específico.
    Retorna DataFrame formatado para heatmap (anos x meses) com colunas de acumulados.
    """
    if ativo not in df.columns:
        return pd.DataFrame()
    
    df_ativo = df[['Data', ativo]].copy()
    
    # ALINHAMENTO COM R: Remove NAs antes de calcular (filter(!is.na(Retorno)))
    df_ativo = df_ativo.dropna(subset=[ativo])
    
    if df_ativo.empty:
        return pd.DataFrame()
    
    df_ativo['Ano'] = df_ativo['Data'].dt.year
    df_ativo['Mês'] = df_ativo['Data'].dt.month
    
    # Calcula retorno acumulado mensal
    retornos_mensais = df_ativo.groupby(['Ano', 'Mês']).apply(
        lambda x: (1 + x[ativo]).prod() - 1
    ).reset_index(name='Retorno')
    
    # Mapeia números de mês para nomes
    meses_nomes = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 
                   'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    retornos_mensais['Mês_Nome'] = retornos_mensais['Mês'].apply(lambda x: meses_nomes[x-1])
    
    # Pivota para formato wide (anos nas linhas, meses nas colunas)
    heatmap_data = retornos_mensais.pivot(index='Ano', columns='Mês_Nome', values='Retorno')
    
    # Reordena colunas na ordem correta dos meses
    heatmap_data = heatmap_data.reindex(columns=meses_nomes)
    
    # Adiciona coluna de Acumulado no Ano (YTD)
    # Para cada ano, multiplica (1 + retorno) de todos os meses disponíveis
    heatmap_data['Acum. Ano'] = heatmap_data.apply(
        lambda row: (1 + row.dropna()).prod() - 1, axis=1
    )
    
    # Adiciona coluna de Acumulado Total (ITD)
    # Calcula o acumulado desde o início até cada ano
    acumulados_totais = []
    acumulado_atual = 0
    for ano in heatmap_data.index:
        acumulado_ano = heatmap_data.loc[ano, 'Acum. Ano']
        if pd.notna(acumulado_ano):
            acumulado_atual = (1 + acumulado_atual) * (1 + acumulado_ano) - 1
        acumulados_totais.append(acumulado_atual)
    
    heatmap_data['Acum. Total'] = acumulados_totais
    
    return heatmap_data

def validar_e_obter_periodo_custom():
    """
    Função centralizada para validar e obter período personalizado do session_state.
    Retorna: (data_ini, data_fim, is_valid, mensagem_erro)
    """
    data_ini = st.session_state.get('data_cust_ini')
    data_fim = st.session_state.get('data_cust_fim')
    
    if not data_ini or not data_fim:
        return None, None, False, "Datas não definidas"
    
    # Converte para date se necessário
    if isinstance(data_ini, datetime):
        data_ini = data_ini.date()
    if isinstance(data_fim, datetime):
        data_fim = data_fim.date()
    
    # Validações
    if data_ini > data_fim:
        return data_ini, data_fim, False, "Data inicial não pode ser maior que data final"
    
    # Verifica se está no range dos dados disponíveis
    # (essa validação pode ser feita no contexto onde df_historico está disponível)
    
    return data_ini, data_fim, True, None

def calcular_retorno_acumulado_robusto(df_retornos: pd.DataFrame) -> pd.DataFrame:
    """Calcula retorno acumulado por ativo a partir de retornos diários.

    - Mantém NaN antes do primeiro ponto válido de cada série (inception).
    - Preenche NaNs APÓS o inception com 0 (sem variação) para não quebrar o cumprod.
    """
    if df_retornos is None or df_retornos.empty:
        return df_retornos

    df = df_retornos.copy()
    df = df.sort_index()

    out = pd.DataFrame(index=df.index)
    for col in df.columns:
        s = pd.to_numeric(df[col], errors='coerce')
        first_valid = s.first_valid_index()
        if first_valid is None:
            out[col] = np.nan
            continue

        s2 = s.copy()
        mask_after = s2.index >= first_valid
        s2.loc[mask_after] = s2.loc[mask_after].fillna(0)
        acc = (1 + s2).cumprod() - 1
        acc.loc[~mask_after] = np.nan
        out[col] = acc

    return out

def processar_mestre(df, data_ref_analise, usar_custom, d_custom_ini, d_custom_fim, calcular_itd=False, tipo_semana="Semana Passada"):
    # Debug entrada da função (salvo em session_state)
    if usar_custom:
        if 'debug_info' not in st.session_state:
            st.session_state.debug_info = {}
        st.session_state.debug_info['processar_mestre_custom'] = {
            'usar_custom': usar_custom,
            'd_custom_ini': str(d_custom_ini),
            'd_custom_ini_type': str(type(d_custom_ini)),
            'd_custom_fim': str(d_custom_fim),
            'd_custom_fim_type': str(type(d_custom_fim))
        }
    
    # Se usar período customizado, a data de referência deve ser a data final do período custom
    if usar_custom and d_custom_fim:
        data_ref = pd.to_datetime(d_custom_fim)
    else:
        data_ref = pd.to_datetime(data_ref_analise)
    
    # Filtra dados até a data de referência
    df_ate_ref = df[df['Data'] <= data_ref]
    
    # --- CORREÇÃO DE SEGURANÇA (Para evitar IndexError) ---
    if df_ate_ref.empty:
        return pd.DataFrame(), {}
    
    # YTD: Usa a ÚLTIMA DATA DISPONÍVEL do ano anterior nos dados
    ano_anterior = data_ref.year - 1
    datas_ano_anterior = df_ate_ref[df_ate_ref['Data'].dt.year == ano_anterior]['Data']
    if not datas_ano_anterior.empty:
        inicio_ano = datas_ano_anterior.max()
    else:
        # Fallback: se não há dados do ano anterior, usa cálculo de calendário
        inicio_ano = calcular_ultimo_dia_util_ano_anterior(data_ref)
    
    # MTD: Usa a ÚLTIMA DATA DISPONÍVEL do mês anterior nos dados
    mes_anterior = (data_ref.replace(day=1) - timedelta(days=1))
    datas_mes_anterior = df_ate_ref[
        (df_ate_ref['Data'].dt.year == mes_anterior.year) & 
        (df_ate_ref['Data'].dt.month == mes_anterior.month)
    ]['Data']
    if not datas_mes_anterior.empty:
        inicio_mtd = datas_mes_anterior.max()
    else:
        # Fallback: se não há dados do mês anterior, usa cálculo de calendário
        inicio_mtd = calcular_ultimo_dia_util_mes_anterior(data_ref)

    # Semana: Calcula baseado na escolha do usuário
    if tipo_semana == "Semana Passada":
        # Semana completa já encerrada: sexta-feira de 2 semanas atrás até sexta-feira da semana passada
        data_semana_inicio = calcular_sexta_feira_semana_retrasada(data_ref)
        data_semana_fim = calcular_sexta_feira_semana_anterior(data_ref)
    else:  # "Semana Corrente"
        # Semana em andamento: sexta-feira da semana anterior até sexta-feira atual (ou último dia útil)
        data_semana_inicio = calcular_sexta_feira_semana_anterior(data_ref)
        data_semana_fim = calcular_sexta_feira_semana_atual(data_ref)
    
    # Pega as datas mais próximas disponíveis no dataset
    datas_disponiveis = df_ate_ref['Data']
    data_semana = datas_disponiveis[datas_disponiveis <= data_semana_inicio].max()
    
    # Fallback: se não houver dados suficientes, usa a primeira data
    if pd.isna(data_semana):
        data_semana = df_ate_ref.iloc[0]['Data']
    
    # Para a data final da semana, usa o menor entre data_ref e data_semana_fim
    data_semana_ref = min(data_ref, data_semana_fim)
        
    df_ytd = calcular_metricas(df, "YTD", inicio_ano, data_ref)
    df_mtd = calcular_metricas(df, "MTD", inicio_mtd, data_ref)
    df_sem = calcular_metricas(df, "Semana", data_semana, data_semana_ref)
    
    df_cust = pd.DataFrame()
    if usar_custom and d_custom_ini and d_custom_fim:
        df_cust = calcular_metricas(df, "Custom", pd.to_datetime(d_custom_ini), pd.to_datetime(d_custom_fim))
        
        # Salva info de debug
        if 'debug_info' not in st.session_state:
            st.session_state.debug_info = {}
        st.session_state.debug_info['df_cust_info'] = {
            'vazio': df_cust.empty,
            'linhas': len(df_cust),
            'colunas': df_cust.columns.tolist() if not df_cust.empty else [],
            'd_custom_ini_convertido': str(pd.to_datetime(d_custom_ini)),
            'd_custom_fim_convertido': str(pd.to_datetime(d_custom_fim))
        }
        
    mestre = df_ytd.copy()
    if not mestre.empty:
        if not df_mtd.empty: mestre = mestre.merge(df_mtd[['Ativo', 'Retorno_MTD']], on='Ativo', how='left')
        if not df_sem.empty: mestre = mestre.merge(df_sem[['Ativo', 'Retorno_Semana']], on='Ativo', how='left')
        if not df_cust.empty: mestre = mestre.merge(df_cust[['Ativo', 'Retorno_Custom', 'Vol_Custom']], on='Ativo', how='left')
    
    # Adiciona categoria primeiro
    cat_map = {}
    for cat, ativos in CATEGORIAS.items():
        for a in ativos: cat_map[a] = cat
    mestre['Categoria'] = mestre['Ativo'].map(cat_map).fillna("Outros")
    
    # Log de ativos sem categoria (alerta sobre possíveis problemas de renomeação)
    ativos_sem_categoria = mestre[mestre['Categoria'] == "Outros"]['Ativo'].tolist()
    if ativos_sem_categoria and 'debug_info' in st.session_state:
        st.session_state.debug_info['ativos_sem_categoria'] = ativos_sem_categoria
        st.session_state.debug_info['warning_categorias'] = f"{len(ativos_sem_categoria)} ativo(s) classificado(s) como 'Outros' (possível problema de renomeação)"
    
    # Calcula ITD se solicitado
    if calcular_itd:
        itd_results = []
        for _, row in mestre.iterrows():
            ativo = row['Ativo']
            categoria = row['Categoria']
            
            # Verifica se categoria tem data de inception
            if categoria in DATAS_INCEPTION:
                data_inception = DATAS_INCEPTION[categoria]
                df_itd_temp = calcular_metricas(df, "ITD", data_inception, data_ref)
                itd_row = df_itd_temp[df_itd_temp['Ativo'] == ativo]
                if not itd_row.empty:
                    itd_results.append({
                        'Ativo': ativo,
                        'Retorno_ITD': itd_row['Retorno_ITD'].values[0],
                        'Vol_ITD': itd_row['Vol_ITD'].values[0]
                    })
        
        if itd_results:
            df_itd = pd.DataFrame(itd_results)
            mestre = mestre.merge(df_itd, on='Ativo', how='left')
    
    # Marca produtos Ghia
    mestre['É_Ghia'] = mestre['Ativo'].isin(PRODUTOS_GHIA)
    
    # Armazena informações de períodos para exibição E debug
    periodos_info = {
        'semana_inicio': data_semana,
        'semana_fim': data_semana_ref,
        'mtd_inicio': inicio_mtd,
        'mtd_fim': data_ref,
        'ytd_inicio': inicio_ano,
        'ytd_fim': data_ref
    }
    
    # Armazena info de períodos para debug
    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = {}
    st.session_state.debug_info['periodos_calculados'] = {
        'YTD_inicio': inicio_ano.strftime('%d/%m/%Y'),
        'YTD_fim': data_ref.strftime('%d/%m/%Y'),
        'MTD_inicio': inicio_mtd.strftime('%d/%m/%Y'),
        'MTD_fim': data_ref.strftime('%d/%m/%Y'),
        'Semana_inicio': data_semana.strftime('%d/%m/%Y') if not pd.isna(data_semana) else 'N/A',
        'Semana_fim': data_semana_ref.strftime('%d/%m/%Y')
    }
    
    return mestre, periodos_info

# ==============================================================================
# 5. UI - BARRA LATERAL (CONFIGURAÇÕES GLOBAIS)
# ==============================================================================

# Fonte única da verdade para período/análise (persistente entre abas)
if 'modo_analise' not in st.session_state:
    st.session_state.modo_analise = "Padrão (YTD/MTD/Sem)"
if 'data_cust_ini' not in st.session_state:
    # Mantém como datetime/date para compatibilidade com st.date_input
    st.session_state.data_cust_ini = datetime(2024, 1, 1)
if 'data_cust_fim' not in st.session_state:
    st.session_state.data_cust_fim = datetime.today()
if 'custom_period_valid' not in st.session_state:
    st.session_state.custom_period_valid = False

with st.sidebar:
    st.markdown("<h3 style='color: #189CD8;'> <strong>        Painel de Controle</strong></h3>", unsafe_allow_html=True)
    st.markdown("---")
    
    # 1. API E EXTRAÇÃO
    with st.expander("Conexão com a API do Comdinheiro", expanded=False):
        # Usa secrets se disponível, senão pede ao usuário
        try:
            default_user = st.secrets.get("api", {}).get("username", "")
            default_pass = st.secrets.get("api", {}).get("password", "")
        except:
            # Se secrets.toml não existir, usa valores vazios
            default_user = ""
            default_pass = ""
        
        # Usa form para permitir submit com Enter
        with st.form(key="form_carregar_dados"):
            api_user = st.text_input("Usuário", value=default_user, help="Login do Comdinheiro (diferencia maiúsculas de minúsculas)", key="api_user_input")
            api_pass = st.text_input("Senha", type="password", value=default_pass, help="Senha do Comdinheiro (diferencia maiúsculas de minúsculas)", key="api_pass_input")
            
            st.caption("Período de Extração dos dados:")
            data_ini_api = st.date_input("Início", value=datetime(2022, 12, 30), format="DD/MM/YYYY", help="Data inicial para extração dos dados")
            st.caption("Fim: último dia útil disponível", help="A data final é calculada automaticamente como o último dia útil anterior à data de hoje")
            
            # Botão dinâmico baseado no estado
            btn_text = "Recarregar Dados" if st.session_state.get('dados_carregados', False) else "Carregar Dados"
            submit_button = st.form_submit_button(btn_text, use_container_width=True)
            
            if submit_button:
                st.session_state.dados_carregados = False
                st.session_state.botao_clicado = True
                st.cache_data.clear()
                st.rerun()

    st.markdown("---")
    
    # 2. CONFIGURAÇÕES GLOBAIS
    st.markdown("<h4 style='color: #189CD8;'> <strong>Data de Referência</strong></h4>", unsafe_allow_html=True)
    data_ref = st.date_input("Selecione a data", value=datetime.today(), format="DD/MM/YYYY", label_visibility="collapsed")

    st.markdown("---")

    # 2.0 PERÍODO DE ANÁLISE (GLOBAL)
    st.markdown("<h4 style='color: #189CD8;'> <strong>Período de Análise</strong></h4>", unsafe_allow_html=True)
    opcoes_modo = ["Padrão (YTD/MTD/Sem)", "Período Personalizado", "Com ITD (Inception to Date)"]
    index_modo = opcoes_modo.index(st.session_state.modo_analise) if st.session_state.modo_analise in opcoes_modo else 0
    st.selectbox(
        "Modo:",
        opcoes_modo,
        index=index_modo,
        key="modo_analise",
        help="Define o modo global. 'Período Personalizado' habilita datas custom. 'Com ITD' adiciona ITD quando disponível."
    )

    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = {}
    st.session_state.debug_info['modo_analise_detectado'] = st.session_state.modo_analise
    st.session_state.debug_info['modo_analise_comparacao'] = {
        'modo_analise_valor': st.session_state.modo_analise,
        'e_igual_periodo_personalizado': st.session_state.modo_analise == "Período Personalizado",
    }

    # Datas do período custom (quando ativo)
    if st.session_state.modo_analise == "Período Personalizado":
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.date_input(
                "Início",
                value=st.session_state.data_cust_ini,
                format="DD/MM/YYYY",
                key="data_cust_ini",
                help="Primeira data do período personalizado"
            )
        with col_c2:
            st.date_input(
                "Fim",
                value=st.session_state.data_cust_fim,
                format="DD/MM/YYYY",
                key="data_cust_fim",
                help="Última data do período personalizado"
            )

        data_ini_v, data_fim_v, is_valid, msg_erro = validar_e_obter_periodo_custom()

        # Valida também contra o range do dataset (se já carregado)
        df_range = st.session_state.get('df_historico')
        if is_valid and isinstance(df_range, pd.DataFrame) and 'Data' in df_range.columns and not df_range.empty:
            data_min = df_range['Data'].min().date()
            data_max = df_range['Data'].max().date()
            if data_ini_v < data_min or data_fim_v > data_max:
                st.warning(
                    f"Dados disponíveis apenas entre {data_min.strftime('%d/%m/%Y')} e {data_max.strftime('%d/%m/%Y')}. "
                    f"O recorte será aplicado dentro desse intervalo."
                )

        st.session_state.custom_period_valid = bool(is_valid)
        if not is_valid:
            st.error(msg_erro if msg_erro else "Período inválido")
        else:
            st.caption(f"Período custom: {data_ini_v.strftime('%d/%m/%Y')} a {data_fim_v.strftime('%d/%m/%Y')}")

        st.session_state.debug_info['analise_categoria_custom'] = {
            'data_cust_ini': str(st.session_state.get('data_cust_ini')),
            'data_cust_fim': str(st.session_state.get('data_cust_fim')),
            'isoformat_ini': data_ini_v.isoformat() if data_ini_v else None,
            'isoformat_fim': data_fim_v.isoformat() if data_fim_v else None,
            'custom_period_valid': bool(is_valid)
        }
    else:
        st.session_state.custom_period_valid = False
    
    st.markdown("---")
    
    # 2.1 CONFIGURAÇÃO DE SEMANA
    st.markdown("<h4 style='color: #189CD8;'> <strong>Período Semanal</strong></h4>", unsafe_allow_html=True)
    tipo_semana = st.radio(
        "Escolha o período:",
        ["Semana Passada", "Semana Corrente"],
        index=0,
        help="Semana Passada: sexta a sexta já encerrada\nSemana Corrente: sexta anterior até hoje",
        key="tipo_semana_radio"
    )
    # Armazena no session_state
    if 'tipo_semana' not in st.session_state:
        st.session_state.tipo_semana = "Semana Passada"
    st.session_state.tipo_semana = tipo_semana
    
    st.markdown("---")
    
    # 4. CACHE
    st.markdown("<h4 style='color: #189CD8;'><strong>Cache</strong></h4>", unsafe_allow_html=True)
    if st.button("Limpar Cache", help="Força o recarregamento dos dados da API"):
        st.cache_data.clear()
        st.success("Cache limpo! Recarregando...")
        st.rerun()
    
    st.markdown("---")
    
    # Info sobre dados
    st.caption("**Status**")
    if st.session_state.get('dados_carregados', False):
        st.caption("Dados carregados e prontos")
    else:
        st.caption("Aguardando carregamento...")

# ==============================================================================
# 6. EXECUÇÃO E TÍTULO PRINCIPAL
# ==============================================================================

# TÍTULO PRINCIPAL
col_titulo, col_logo = st.columns([5, 1])
with col_titulo:
    st.title("Weekly Performance Dashboard")
    st.markdown("<p style='color: #495057; font-size: 16px;'><strong>Análise consolidada</strong> de performance de carteiras e ativos</p>", unsafe_allow_html=True)
with col_logo:
    st.markdown("<div style='display: flex; align-items: center; justify-content: center; height: 100%;'>", unsafe_allow_html=True)
    st.image("www/logo_ghia.png", width=276)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")

# Inicializa session state
if 'dados_carregados' not in st.session_state:
    st.session_state.dados_carregados = False
if 'df_historico' not in st.session_state:
    st.session_state.df_historico = None
if 'botao_clicado' not in st.session_state:
    st.session_state.botao_clicado = False

# Verifica se usuário forneceu credenciais E se ainda não tem dados carregados
if (not api_user or not api_pass) and not st.session_state.dados_carregados:
    st.info("**Bem-vindo!** Por favor, insira suas credenciais na barra lateral para começar.")
    st.markdown("""
    ### Como começar:
    1. Identifique o **Painel de Controle** na barra lateral
    2. Clique em **"Conexão com a API do Comdinheiro"**
    3. Digite seu **usuário** e **senha** do Comdinheiro
    4. Clique em **"Carregar Dados"**
    """)
    st.stop()

# Só carrega dados quando botão foi clicado e ainda não estão carregados
if st.session_state.botao_clicado and not st.session_state.dados_carregados:
    with st.spinner(f"Estabelecendo conexão com o Comdinheiro..."):
        d_ini_payload = data_ini_api.strftime("%d%m%Y")
        
        # Calcula o último dia útil anterior a hoje (D-1 útil) usando calendário ANBIMA
        hoje = datetime.now()
        data_aux = hoje - timedelta(days=1)
        # Retrocede até encontrar um dia útil
        tentativas = 0
        while not eh_dia_util_br(data_aux) and tentativas < 10:
            data_aux = data_aux - timedelta(days=1)
            tentativas += 1
        ultimo_dia_util = data_aux
        
        d_fim_payload = ultimo_dia_util.strftime("%d%m%Y")
        
        df_historico, msg = get_data_comdinheiro(api_user, api_pass, d_ini_payload, d_fim_payload, _cache_version="v2")
    
    if df_historico is None:
        st.error(f"Falha na Extração: {msg}")
        # Só mostra dica de credenciais se for erro 401
        if "401" in msg or "credenciais" in msg.lower():
            st.info("Verifique suas credenciais e tente novamente.")
        st.session_state.botao_clicado = False
        st.stop()
    else:
        # Exibe informações da extração
        st.sidebar.success(msg)
    
    # Extrai dados do Yahoo Finance - USA O MESMO PERÍODO do Comdinheiro
    with st.spinner("Baixando ETFs offshore (Yahoo Finance)..."):
        # IMPORTANTE: Usa data_ini_api e ultimo_dia_util (mesmo período do Comdinheiro)
        # Armazena datas para debug
        st.session_state.debug_info['yahoo_data_inicio'] = data_ini_api.strftime("%d/%m/%Y")
        st.session_state.debug_info['yahoo_data_fim'] = ultimo_dia_util.strftime("%d/%m/%Y")
        
        df_yahoo = get_data_yahoo(data_ini_api, ultimo_dia_util)
        
        if not df_yahoo.empty:
            # Debug: armazena info sobre Yahoo Finance
            st.session_state.debug_info['yahoo_shape'] = df_yahoo.shape
            st.session_state.debug_info['yahoo_colunas'] = list(df_yahoo.columns)
            st.session_state.debug_info['yahoo_datas_min_max'] = (df_yahoo['Data'].min(), df_yahoo['Data'].max())
            
            # Debug: shape ANTES do merge
            st.session_state.debug_info['shape_antes_merge'] = df_historico.shape
            
            # VALIDAÇÃO ANTES DO MERGE: Confirma que ambas as fontes têm valores numéricos
            # Comdinheiro: já convertido (vírgula→ponto)
            # Yahoo: já numérico (ponto decimal nativo)
            comdinheiro_sample = df_historico.select_dtypes(include=['float64', 'int64']).columns[:3].tolist()
            yahoo_sample = df_yahoo.select_dtypes(include=['float64', 'int64']).columns[:3].tolist()
            st.session_state.debug_info['validacao_merge'] = {
                'comdinheiro_tipos': {col: str(df_historico[col].dtype) for col in comdinheiro_sample if col != 'Data'},
                'yahoo_tipos': {col: str(df_yahoo[col].dtype) for col in yahoo_sample if col != 'Data'},
                'merge_compativel': True  # Ambos devem ser float64
            }
            
            # Merge dos dados Yahoo Finance com Comdinheiro
            # Ambos têm formato numérico correto (ponto como decimal)
            df_historico = df_historico.merge(df_yahoo, on='Data', how='outer')
            df_historico = df_historico.sort_values('Data').reset_index(drop=True)
            
            # Debug: shape DEPOIS do merge
            st.session_state.debug_info['shape_depois_merge'] = df_historico.shape
            
            # Forward fill para ETFs (dias sem negociação mantêm valor anterior)
            # Não usar fillna(0) pois isso zeraria retornos em dias sem dados
            etf_cols = ["CSPX", "EIMI", "CEUU", "IJPA", "ISFD", "LQDA", "ERNA", "FLOA", "IB01", "CBU0", "IHYA", "JPEA"]
            etfs_presentes = [col for col in etf_cols if col in df_historico.columns]
            
            if etfs_presentes:
                # Para dias sem dados nos ETFs (feriados diferentes), usa retorno 0 (sem mudança)
                df_historico[etfs_presentes] = df_historico[etfs_presentes].fillna(0)
            
            st.sidebar.success(f"Yahoo Finance: {len(etfs_presentes)} ETFs adicionados")
            st.session_state.debug_info['etfs_adicionados'] = etfs_presentes
        else:
            st.sidebar.info("Yahoo Finance: Dados não disponíveis")
            st.session_state.debug_info['yahoo_error'] = "DataFrame vazio retornado"
    
    # Armazena no session state
    st.session_state.df_historico = df_historico
    st.session_state.dados_carregados = True
else:
    # Usa dados já carregados
    df_historico = st.session_state.df_historico
    st.sidebar.success("Dados prontos para análise!")

# Só processa dados se já foram carregados
if st.session_state.dados_carregados and df_historico is not None:
    
    # Processa dados iniciais com as configurações globais (sidebar)
    tipo_semana = st.session_state.get('tipo_semana', 'Semana Passada')
    modo_analise_global = st.session_state.get('modo_analise', "Padrão (YTD/MTD/Sem)")
    calcular_itd_global = (modo_analise_global == "Com ITD (Inception to Date)")
    usar_custom_global = (modo_analise_global == "Período Personalizado") and st.session_state.get('custom_period_valid', False)

    d_custom_ini_iso, d_custom_fim_iso = None, None
    if usar_custom_global:
        data_ini_v, data_fim_v, is_valid, _ = validar_e_obter_periodo_custom()
        if is_valid and data_ini_v and data_fim_v:
            d_custom_ini_iso = data_ini_v.isoformat()
            d_custom_fim_iso = data_fim_v.isoformat()
        else:
            usar_custom_global = False

    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = {}
    st.session_state.debug_info['modo_analise_detectado'] = modo_analise_global

    df_resumo, periodos_info_global = processar_mestre(
        df_historico,
        str(data_ref),
        usar_custom_global,
        d_custom_ini_iso,
        d_custom_fim_iso,
        calcular_itd=calcular_itd_global,
        tipo_semana=tipo_semana
    )
    
    # Botão de Relatório de Diagnóstico - Colocado após processar_mestre para capturar períodos
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Relatório de Diagnóstico")
    
    # Coleta informações de debug em formato estruturado
    debug = st.session_state.get('debug_info', {})
    
    relatorio_data = []
    
    # Informações gerais
    relatorio_data.append({"Categoria": "Geral", "Item": "Data de Geração", "Valor": datetime.now().strftime('%d/%m/%Y %H:%M:%S')})
    relatorio_data.append({"Categoria": "Geral", "Item": "Data de Referência", "Valor": data_ref.strftime('%d/%m/%Y')})
    
    # Informações da API
    relatorio_data.append({"Categoria": "API", "Item": "Data Início Solicitada", "Valor": debug.get('data_inicio_solicitada', 'N/A')})
    relatorio_data.append({"Categoria": "API", "Item": "Data Fim Solicitada", "Valor": debug.get('data_fim_solicitada', 'N/A')})
    relatorio_data.append({"Categoria": "API", "Item": "Linhas Recebidas", "Valor": debug.get('linhas_recebidas', 'N/A')})
    relatorio_data.append({"Categoria": "API", "Item": "Colunas Recebidas", "Valor": debug.get('colunas_recebidas', 'N/A')})
    
    # Informações do Dataset
    relatorio_data.append({"Categoria": "Dataset", "Item": "Datas Encontradas", "Valor": debug.get('datas_encontradas', 'N/A')})
    relatorio_data.append({"Categoria": "Dataset", "Item": "Ativos Carregados", "Valor": debug.get('ativos_encontrados', 'N/A')})
    relatorio_data.append({"Categoria": "Dataset", "Item": "Valores Inválidos (NaN)", "Valor": debug.get('total_valores_invalidos', 0)})
    
    # Yahoo Finance
    if 'yahoo_shape' in debug:
        relatorio_data.append({"Categoria": "Yahoo Finance", "Item": "ETFs Adicionados", "Valor": debug.get('yahoo_shape', (0,0))[1] - 1})
        relatorio_data.append({"Categoria": "Yahoo Finance", "Item": "Data Início Yahoo", "Valor": debug.get('yahoo_data_inicio', 'N/A')})
        relatorio_data.append({"Categoria": "Yahoo Finance", "Item": "Data Fim Yahoo", "Valor": debug.get('yahoo_data_fim', 'N/A')})
        if 'etfs_adicionados' in debug:
            relatorio_data.append({"Categoria": "Yahoo Finance", "Item": "Lista ETFs", "Valor": ', '.join(debug.get('etfs_adicionados', []))})
    
    # Merge
    if 'shape_antes_merge' in debug:
        relatorio_data.append({"Categoria": "Merge", "Item": "Shape Antes Merge", "Valor": str(debug.get('shape_antes_merge', 'N/A'))})
        relatorio_data.append({"Categoria": "Merge", "Item": "Shape Depois Merge", "Valor": str(debug.get('shape_depois_merge', 'N/A'))})
    
    # Categorias
    if 'ativos_sem_categoria' in debug:
        relatorio_data.append({"Categoria": "Categorias", "Item": "Ativos sem Categoria", "Valor": len(debug.get('ativos_sem_categoria', []))})
        relatorio_data.append({"Categoria": "Categorias", "Item": "Lista Ativos 'Outros'", "Valor": ', '.join(debug.get('ativos_sem_categoria', []))})
    
    # Períodos Calculados
    if 'periodos_calculados' in debug:
        periodos = debug['periodos_calculados']
        relatorio_data.append({"Categoria": "Períodos", "Item": "YTD Início", "Valor": periodos.get('YTD_inicio', 'N/A')})
        relatorio_data.append({"Categoria": "Períodos", "Item": "YTD Fim", "Valor": periodos.get('YTD_fim', 'N/A')})
        relatorio_data.append({"Categoria": "Períodos", "Item": "MTD Início", "Valor": periodos.get('MTD_inicio', 'N/A')})
        relatorio_data.append({"Categoria": "Períodos", "Item": "MTD Fim", "Valor": periodos.get('MTD_fim', 'N/A')})
        relatorio_data.append({"Categoria": "Períodos", "Item": "Semana Início", "Valor": periodos.get('Semana_inicio', 'N/A')})
        relatorio_data.append({"Categoria": "Períodos", "Item": "Semana Fim", "Valor": periodos.get('Semana_fim', 'N/A')})
    
    # Warnings
    if 'warning_valores_absurdos' in debug:
        relatorio_data.append({"Categoria": "Warnings", "Item": "Valores Absurdos", "Valor": debug.get('warning_valores_absurdos', '')})
    if 'warning_categorias' in debug:
        relatorio_data.append({"Categoria": "Warnings", "Item": "Categorias", "Valor": debug.get('warning_categorias', '')})
    
    # Informações do DataFrame atual
    if df_historico is not None:
        relatorio_data.append({"Categoria": "DataFrame Atual", "Item": "Shape", "Valor": str(df_historico.shape)})
        relatorio_data.append({"Categoria": "DataFrame Atual", "Item": "Colunas", "Valor": len(df_historico.columns)})
        relatorio_data.append({"Categoria": "DataFrame Atual", "Item": "Data Min", "Valor": df_historico['Data'].min().strftime('%d/%m/%Y')})
        relatorio_data.append({"Categoria": "DataFrame Atual", "Item": "Data Max", "Valor": df_historico['Data'].max().strftime('%d/%m/%Y')})
    
    # Debug de Modo de Análise (sempre inclui)
    relatorio_data.append({"Categoria": "Debug Modo", "Item": "Modo Detectado", "Valor": debug.get('modo_analise_detectado', 'N/A')})
    
    if 'modo_analise_comparacao' in debug:
        comp = debug['modo_analise_comparacao']
        relatorio_data.append({"Categoria": "Debug Modo", "Item": "modo_analise Valor", "Valor": comp.get('modo_analise_valor', 'N/A')})
        relatorio_data.append({"Categoria": "Debug Modo", "Item": "É Período Personalizado?", "Valor": comp.get('e_igual_periodo_personalizado', 'N/A')})
        relatorio_data.append({"Categoria": "Debug Modo", "Item": "Session State modo", "Valor": comp.get('session_state_modo', 'N/A')})
        relatorio_data.append({"Categoria": "Debug Modo", "Item": "Widget Key", "Valor": comp.get('widget_key', 'N/A')})
    
    # Debug de Período Personalizado
    if 'analise_categoria_custom' in debug:
        custom = debug['analise_categoria_custom']
        relatorio_data.append({"Categoria": "Período Custom", "Item": "Data Inicial", "Valor": custom.get('data_cust_ini', 'N/A')})
        relatorio_data.append({"Categoria": "Período Custom", "Item": "Data Final", "Valor": custom.get('data_cust_fim', 'N/A')})
        relatorio_data.append({"Categoria": "Período Custom", "Item": "ISO Format Ini", "Valor": custom.get('isoformat_ini', 'N/A')})
        relatorio_data.append({"Categoria": "Período Custom", "Item": "ISO Format Fim", "Valor": custom.get('isoformat_fim', 'N/A')})
    
    if 'processar_mestre_custom' in debug:
        pm = debug['processar_mestre_custom']
        relatorio_data.append({"Categoria": "Processar Mestre", "Item": "usar_custom", "Valor": pm.get('usar_custom', 'N/A')})
        relatorio_data.append({"Categoria": "Processar Mestre", "Item": "d_custom_ini", "Valor": pm.get('d_custom_ini', 'N/A')})
        relatorio_data.append({"Categoria": "Processar Mestre", "Item": "d_custom_fim", "Valor": pm.get('d_custom_fim', 'N/A')})
    
    if 'df_cust_info' in debug:
        cust = debug['df_cust_info']
        relatorio_data.append({"Categoria": "df_cust", "Item": "Vazio?", "Valor": cust.get('vazio', 'N/A')})
        relatorio_data.append({"Categoria": "df_cust", "Item": "Linhas", "Valor": cust.get('linhas', 'N/A')})
        relatorio_data.append({"Categoria": "df_cust", "Item": "Colunas", "Valor": ', '.join(cust.get('colunas', []))})
        relatorio_data.append({"Categoria": "df_cust", "Item": "Data Ini Convertida", "Valor": cust.get('d_custom_ini_convertido', 'N/A')})
        relatorio_data.append({"Categoria": "df_cust", "Item": "Data Fim Convertida", "Valor": cust.get('d_custom_fim_convertido', 'N/A')})
    
    if 'analise_categoria_resultado' in debug:
        res = debug['analise_categoria_resultado']
        relatorio_data.append({"Categoria": "Resultado Análise", "Item": "Linhas Retornadas", "Valor": res.get('linhas_retornadas', 'N/A')})
        relatorio_data.append({"Categoria": "Resultado Análise", "Item": "df_resumo Vazio?", "Valor": res.get('df_resumo_vazio', 'N/A')})
        relatorio_data.append({"Categoria": "Resultado Análise", "Item": "Colunas Retornadas", "Valor": ', '.join(res.get('colunas', []))})
    
    if 'graficos_filtro' in debug:
        graf = debug['graficos_filtro']
        relatorio_data.append({"Categoria": "Gráficos", "Item": "Período", "Valor": graf.get('periodo', 'N/A')})
        relatorio_data.append({"Categoria": "Gráficos", "Item": "Ativos Selecionados", "Valor": graf.get('ativos_selecionados', 'N/A')})
        relatorio_data.append({"Categoria": "Gráficos", "Item": "Linhas Após Máscara", "Valor": graf.get('linhas_apos_mascara', 'N/A')})
        relatorio_data.append({"Categoria": "Gráficos", "Item": "Linhas Após Dropna", "Valor": graf.get('linhas_apos_dropna', 'N/A')})
        relatorio_data.append({"Categoria": "Gráficos", "Item": "df_g Vazio?", "Valor": graf.get('df_vazio', 'N/A')})
    
    # Cria DataFrame e CSV
    df_relatorio = pd.DataFrame(relatorio_data)
    csv_relatorio = df_relatorio.to_csv(index=False, encoding='utf-8')
    
    st.sidebar.download_button(
        label="Baixar Relatório de Diagnóstico",
        data=csv_relatorio,
        file_name=f"relatorio_diagnostico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        help="Relatório com informações técnicas para diagnóstico",
        type="secondary"
    )
else:
    # Se não há dados carregados, para por aqui
    st.stop()

# --- DASHBOARD VISUAL ---

st.header("Performance Dashboard")

st.caption("Retornos YTD (Year to Date) - Acumulado desde o início do ano")

# Linha 1: Produtos Ghia
col1, col2, col3, col4, col5 = st.columns(5)

# Produtos fixos para exibição
produtos_fixos = {
    'Moderado (Prod)': 'Carteira Moderada',
    'Ghia RV': 'Ghia RV',
    'Ghia MM': 'Ghia MM',
    'Ghia RF': 'Ghia RF',
    'Ghia FIIs': 'Ghia FIIs'
}

if not df_resumo.empty:
    for idx, (col, (ativo_key, nome_display)) in enumerate(zip([col1, col2, col3, col4, col5], produtos_fixos.items())):
        if ativo_key in df_resumo['Ativo'].values:
            row = df_resumo[df_resumo['Ativo'] == ativo_key].iloc[0]
            ret_ytd = row['Retorno_YTD']
            vol_ytd = row['Vol_YTD'] if 'Vol_YTD' in row else 0
            col.metric(nome_display, f"{ret_ytd:.2%}", f"Vol: {vol_ytd:.2%}")
        else:
            col.metric(nome_display, "N/A", "Sem dados")

# Linha 2: Benchmarks
st.markdown("---")
st.caption("Benchmarks - Retornos YTD")
col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)

benchmarks = {
    'CDI': 'CDI',
    'Ibovespa': 'Ibovespa',
    'IFIX': 'IFIX'
}

if not df_resumo.empty:
    # CDI
    with col_b1:
        if 'CDI' in df_resumo['Ativo'].values:
            row = df_resumo[df_resumo['Ativo'] == 'CDI'].iloc[0]
            ret_ytd = row['Retorno_YTD']
            vol_ytd = row['Vol_YTD'] if 'Vol_YTD' in row else 0
            col_b1.metric("CDI", f"{ret_ytd:.2%}", f"Vol: {vol_ytd:.2%}")
        else:
            col_b1.metric("CDI", "N/A", "Sem dados")
    
    # Ibovespa
    with col_b2:
        if 'Ibovespa' in df_resumo['Ativo'].values:
            row = df_resumo[df_resumo['Ativo'] == 'Ibovespa'].iloc[0]
            ret_ytd = row['Retorno_YTD']
            vol_ytd = row['Vol_YTD'] if 'Vol_YTD' in row else 0
            col_b2.metric("Ibovespa", f"{ret_ytd:.2%}", f"Vol: {vol_ytd:.2%}")
        else:
            col_b2.metric("Ibovespa", "N/A", "Sem dados")
    
    # IFIX
    with col_b3:
        if 'IFIX' in df_resumo['Ativo'].values:
            row = df_resumo[df_resumo['Ativo'] == 'IFIX'].iloc[0]
            ret_ytd = row['Retorno_YTD']
            vol_ytd = row['Vol_YTD'] if 'Vol_YTD' in row else 0
            col_b3.metric("IFIX", f"{ret_ytd:.2%}", f"Vol: {vol_ytd:.2%}")
        else:
            col_b3.metric("IFIX", "N/A", "Sem dados")

# Inicializa session_state para persistência entre abas
if 'categoria_selecionada' not in st.session_state:
    st.session_state.categoria_selecionada = list(CATEGORIAS.keys())[0] if CATEGORIAS else None
if 'periodo_categoria' not in st.session_state:
    st.session_state.periodo_categoria = "Semana"
if 'periodo_categoria_grafico' not in st.session_state:
    st.session_state.periodo_categoria_grafico = "YTD"
if 'periodo_explorador' not in st.session_state:
    st.session_state.periodo_explorador = "YTD"
if 'categorias_selecionadas_grafico' not in st.session_state:
    st.session_state.categorias_selecionadas_grafico = ["Renda Fixa"]
if 'ativos_omitidos_temp' not in st.session_state:
    st.session_state.ativos_omitidos_temp = []
if 'ativos_omitidos_confirmados' not in st.session_state:
    st.session_state.ativos_omitidos_confirmados = []
if 'exibir_so_ghia' not in st.session_state:
    st.session_state.exibir_so_ghia = False

tab_geral, tab_cat, tab_graf, tab_heatmap = st.tabs(["Visão Geral", "Análise por Categoria", "Gráficos", "Histórico Mensal"])

with tab_geral:
    modo_analise = st.session_state.get('modo_analise', "Padrão (YTD/MTD/Sem)")
    calcular_itd = (modo_analise == "Com ITD (Inception to Date)")

    # Banner informativo sobre período custom ativo
    if modo_analise == "Período Personalizado" and st.session_state.get('custom_period_valid', False):
        data_ini_v, data_fim_v, _, _ = validar_e_obter_periodo_custom()
        if data_ini_v and data_fim_v:
            st.info(
                f"Período Personalizado Ativo: {data_ini_v.strftime('%d/%m/%Y')} a {data_fim_v.strftime('%d/%m/%Y')} | Configurações na barra lateral"
            )

    # Reusa o processamento global (evita recomputação e conflitos de session_state)
    df_resumo_temp = df_resumo
    periodos_info = periodos_info_global

    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = {}
    st.session_state.debug_info['analise_categoria_resultado'] = {
        'linhas_retornadas': len(df_resumo_temp),
        'df_resumo_vazio': df_resumo_temp.empty,
        'colunas': df_resumo_temp.columns.tolist() if not df_resumo_temp.empty else [],
        'usar_custom_enviado': (modo_analise == "Período Personalizado" and st.session_state.get('custom_period_valid', False)),
        'calcular_itd': calcular_itd
    }
    
    # Dados processados sem filtros
    
    st.markdown("---")
    
    st.markdown("<h3 style='color: #189CD8;'><strong>Tabela Consolidada de Performance</strong></h3>", unsafe_allow_html=True)
    
    # Adiciona filtro por categoria
    col_filtro1, col_filtro2 = st.columns([3, 1])
    with col_filtro1:
        categorias_opcoes = ["Todas"] + list(CATEGORIAS.keys())
        filtro_categoria = st.selectbox(
            "Filtrar por Categoria:",
            categorias_opcoes,
            index=0,
            key="filtro_categoria_tabela"
        )
    
    with col_filtro2:
        st.write("")  # Espaçamento
    
    # Aplica filtro de categoria
    if filtro_categoria != "Todas":
        df_resumo_filtrado = df_resumo_temp[df_resumo_temp['Categoria'] == filtro_categoria].copy()
    else:
        df_resumo_filtrado = df_resumo_temp.copy()
    
    # Exibe indicadores de período com destaque
    if periodos_info:
        def fmt_date(d):
            if pd.notna(d):
                return pd.to_datetime(d).strftime('%d/%m/%Y')
            return "N/A"
        
        periodo_semana = f"<span style='background-color: #E3F2FD; padding: 4px 8px; border-radius: 4px; margin-right: 10px;'><strong>Semanal:</strong> {fmt_date(periodos_info.get('semana_inicio'))} a {fmt_date(periodos_info.get('semana_fim'))}</span>"
        periodo_mtd = f"<span style='background-color: #E8F5E9; padding: 4px 8px; border-radius: 4px; margin-right: 10px;'><strong>MTD:</strong> {fmt_date(periodos_info.get('mtd_inicio'))} a {fmt_date(periodos_info.get('mtd_fim'))}</span>"
        periodo_ytd = f"<span style='background-color: #FFF9C4; padding: 4px 8px; border-radius: 4px;'><strong>YTD:</strong> {fmt_date(periodos_info.get('ytd_inicio'))} a {fmt_date(periodos_info.get('ytd_fim'))}</span>"
        
        st.markdown(f"<div style='margin-bottom: 15px; font-size: 14px;'>{periodo_semana} {periodo_mtd} {periodo_ytd}</div>", unsafe_allow_html=True)
    
    # Define colunas base
    cols_view = ["Ativo", "Categoria", "Retorno_Semana", "Retorno_MTD", "Retorno_YTD", "Vol_YTD", "Sharpe_YTD", "MaxDD_YTD"]
    
    # Adiciona colunas específicas por modo
    if modo_analise == "Período Personalizado":
        if 'Retorno_Custom' in df_resumo_filtrado.columns:
            cols_view.insert(5, "Retorno_Custom")
            cols_view.insert(6, "Vol_Custom")
        data_ini_v, data_fim_v, is_valid, _ = validar_e_obter_periodo_custom()
        if is_valid and data_ini_v and data_fim_v:
            st.info(
                f"Exibindo dados personalizados de {data_ini_v.strftime('%d/%m/%Y')} até {data_fim_v.strftime('%d/%m/%Y')}"
            )
    
    if calcular_itd and 'Retorno_ITD' in df_resumo_filtrado.columns:
        cols_view.insert(5, "Retorno_ITD")
        st.info("ITD (Inception to Date) disponível para FIIs, Renda Fixa, Multimercados e Ações")
    
    # Filtra apenas colunas existentes
    cols_finais = [c for c in cols_view if c in df_resumo_filtrado.columns]
    
    # Prepara dados para exibição - multiplica valores percentuais por 100
    df_display = df_resumo_filtrado[cols_finais].copy()
    
    # Converte colunas de retorno e volatilidade para percentual (multiplicando por 100)
    colunas_percentuais = ['Retorno_Semana', 'Retorno_MTD', 'Retorno_YTD', 'Retorno_ITD', 'Retorno_Custom', 
                           'Vol_YTD', 'Vol_Custom', 'MaxDD_YTD']
    for col in colunas_percentuais:
        if col in df_display.columns:
            df_display[col] = df_display[col] * 100
    
    df_display = df_display.sort_values("Retorno_YTD", ascending=False)
    
    # Configuração de colunas
    column_cfg = {
        "Ativo": st.column_config.TextColumn("Ativo", width="medium"),
        "Categoria": st.column_config.TextColumn("Categoria", width="small"),
        "Retorno_YTD": st.column_config.ProgressColumn("YTD", format="%.2f%%", min_value=-100.0, max_value=100.0),
        "Retorno_ITD": st.column_config.ProgressColumn("ITD", format="%.2f%%", min_value=-100.0, max_value=200.0),
        "Retorno_Custom": st.column_config.ProgressColumn("Custom", format="%.2f%%", min_value=-100.0, max_value=100.0),
        "Vol_YTD": st.column_config.NumberColumn("Vol (aa)", format="%.2f%%"),
        "Vol_Custom": st.column_config.NumberColumn("Vol Custom", format="%.2f%%"),
        "Retorno_Semana": st.column_config.NumberColumn("Semana", format="%.2f%%"),
        "Retorno_MTD": st.column_config.NumberColumn("Mês", format="%.2f%%"),
        "Sharpe_YTD": st.column_config.NumberColumn("Sharpe", format="%.2f"),
        "MaxDD_YTD": st.column_config.NumberColumn("Max DD", format="%.2f%%"),
    }
    
    st.dataframe(
        df_display,
        column_config=column_cfg,
        use_container_width=True,
        hide_index=True,
        height=600
    )
    
    # Botões de download
    col_dl1, col_dl2 = st.columns(2)
    
    with col_dl1:
        # Download 1: Métricas calculadas (resumo)
        # Converte valores decimais para percentuais antes de exportar
        df_metricas_export = df_display.copy()
        
        # Colunas que devem ser convertidas para percentual (decimal → %)
        colunas_percentuais = ['Retorno_YTD', 'Retorno_MTD', 'Retorno_Semana', 'Retorno_ITD', 
                               'Retorno_Custom', 'Vol_YTD', 'Vol_Custom', 'MaxDD_YTD']
        
        for col in colunas_percentuais:
            if col in df_metricas_export.columns:
                df_metricas_export[col] = (df_metricas_export[col] * 100).round(2)
        
        csv_metricas = df_metricas_export.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Métricas (CSV)",
            data=csv_metricas,
            file_name=f"metricas_performance_{data_ref.strftime('%Y%m%d')}.csv",
            mime="text/csv",
            help="Download das métricas calculadas (YTD, Vol, Sharpe, etc.) - Valores em percentual"
        )
    
    with col_dl2:
        # Download 2: Dados brutos completos (histórico mergeado)
        if df_historico is not None:
            # Converte de formato decimal (ponto) para formato brasileiro (vírgula) para Excel
            df_export = df_historico.copy()
            
            # Formata Data para formato brasileiro
            df_export['Data'] = df_export['Data'].dt.strftime('%d/%m/%Y')
            
            # Converte valores numéricos para formato brasileiro (vírgula como decimal)
            for col in df_export.columns:
                if col != 'Data' and pd.api.types.is_numeric_dtype(df_export[col]):
                    # Multiplica por 100 para converter de decimal para percentual
                    # Ex: 0.0123 → 1.23%
                    df_export[col] = (df_export[col] * 100).round(4)
            
            csv_bruto = df_export.to_csv(index=False, decimal=',', sep=';').encode('utf-8')
            st.download_button(
                label="Download Dados Brutos Completos (CSV)",
                data=csv_bruto,
                file_name=f"dados_brutos_mergeados_{data_ref.strftime('%Y%m%d')}.csv",
                mime="text/csv",
                help="Download do histórico completo mergeado (Comdinheiro + Yahoo Finance) - Formato BR: vírgula decimal, ponto-e-vírgula separador"
            )

with tab_cat:
    st.markdown("<h3 style='color: #189CD8;'><strong>Análise Detalhada por Categoria</strong></h3>", unsafe_allow_html=True)
    
    # Info sobre configurações de período (sempre aponta para sidebar)
    if st.session_state.get('modo_analise') == "Período Personalizado":
        data_ini_v, data_fim_v, is_valid, msg_erro = validar_e_obter_periodo_custom()
        if is_valid and data_ini_v and data_fim_v:
            st.info(f"Período custom ativo: {data_ini_v.strftime('%d/%m/%Y')} a {data_fim_v.strftime('%d/%m/%Y')} | Configurável na barra lateral")
        else:
            st.warning(f"{msg_erro if msg_erro else 'Período custom inválido'} | Configure na barra lateral")
    
    col_cat1, col_cat2, col_cat3 = st.columns([2, 2, 1])
    
    with col_cat1:
        cat_select = st.selectbox(
            "Selecione a Categoria:", 
            list(CATEGORIAS.keys()),
            index=list(CATEGORIAS.keys()).index(st.session_state.categoria_selecionada) if st.session_state.categoria_selecionada in CATEGORIAS.keys() else 0,
            key="cat_select_widget"
        )
        st.session_state.categoria_selecionada = cat_select
    
    with col_cat2:
        # Opções disponíveis dependem se período custom está calculado
        opcoes_periodo = ["MTD", "YTD"]
        # Sempre mostra "Personalizado" se o modo estiver ativo (mesmo que ainda inválido)
        if st.session_state.get('modo_analise') == "Período Personalizado":
            opcoes_periodo.append("Personalizado")
        
        # Ajusta index se Personalizado não estiver disponível
        valor_anterior = st.session_state.periodo_categoria_grafico
        if valor_anterior not in opcoes_periodo:
            valor_anterior = "YTD"
            st.session_state.periodo_categoria_grafico = valor_anterior
        
        periodo_cat_graf = st.selectbox(
            "Período Selecionável:",
            opcoes_periodo,
            index=opcoes_periodo.index(valor_anterior) if valor_anterior in opcoes_periodo else 1,
            key="periodo_cat_graf_widget",
            help="Escolha qual período exibir nos gráficos"
        )
        st.session_state.periodo_categoria_grafico = periodo_cat_graf
        
        # Feedback sobre período personalizado
        if periodo_cat_graf == "Personalizado":
            data_ini_v, data_fim_v, _, _ = validar_e_obter_periodo_custom()
            if data_ini_v and data_fim_v:
                st.caption(f"{data_ini_v.strftime('%d/%m/%Y')} a {data_fim_v.strftime('%d/%m/%Y')}")
    
    with col_cat3:
        incluir_bench = st.checkbox("Incluir CDI", value=True)
    
    st.markdown("---")
    
    # Usa df_resumo_temp da aba geral ou processa novamente se necessário
    try:
        df_cat = df_resumo_temp[df_resumo_temp['Categoria'] == cat_select].copy()
    except (NameError, KeyError):
        # Fallback: processa dados respeitando período personalizado se ativo
        tipo_semana = st.session_state.get('tipo_semana', 'Semana Passada')
        usar_custom = (st.session_state.get('modo_analise') == "Período Personalizado") and st.session_state.get('custom_period_valid', False)
        calcular_itd = (st.session_state.get('modo_analise') == "Com ITD (Inception to Date)")
        
        if usar_custom:
            data_ini_v, data_fim_v, _, _ = validar_e_obter_periodo_custom()
            df_resumo_temp, _ = processar_mestre(
                df_historico, 
                str(data_ref), 
                True, 
                data_ini_v.isoformat(), 
                data_fim_v.isoformat(), 
                calcular_itd,
                tipo_semana
            )
        else:
            df_resumo_temp, _ = processar_mestre(df_historico, str(data_ref), False, None, None, calcular_itd, tipo_semana)
        
        df_cat = df_resumo_temp[df_resumo_temp['Categoria'] == cat_select].copy()
    
    # Adiciona última data disponível para cada ativo
    ultima_data_dict = {}
    for ativo in df_cat['Ativo'].values:
        if ativo in df_historico.columns:
            # Encontra a última data onde o ativo tem valor não-nulo
            df_temp = df_historico[['Data', ativo]].dropna()
            if not df_temp.empty:
                ultima_data_dict[ativo] = df_temp['Data'].max()
            else:
                ultima_data_dict[ativo] = None
        else:
            ultima_data_dict[ativo] = None
    
    # Adiciona coluna de última data ao dataframe
    df_cat['Última Data'] = df_cat['Ativo'].map(ultima_data_dict)
    
    # Adiciona CDI se solicitado (sempre disponível em df_resumo_temp)
    if incluir_bench:
        cdi_row = df_resumo_temp[df_resumo_temp['Ativo'] == 'CDI'].copy()
        if not cdi_row.empty:
            # Adiciona última data para o CDI também
            if 'CDI' in df_historico.columns:
                df_temp_cdi = df_historico[['Data', 'CDI']].dropna()
                if not df_temp_cdi.empty:
                    cdi_row['Última Data'] = df_temp_cdi['Data'].max()
            df_cat = pd.concat([df_cat, cdi_row], ignore_index=True)
    
    # Mapeia período para colunas
    periodo_map_graf = {
        "MTD": "Retorno_MTD",
        "YTD": "Retorno_YTD",
        "Personalizado": "Retorno_Custom"
    }
    col_retorno_graf = periodo_map_graf[periodo_cat_graf]
    
    periodo_map_vol = {
        "MTD": "Vol_MTD",
        "YTD": "Vol_YTD",
        "Personalizado": "Vol_Custom"
    }
    col_vol_graf = periodo_map_vol[periodo_cat_graf]
    
    # SEÇÃO 1: RETORNOS
    st.markdown("### Retornos")
    
    # Cria label combinando ativo e última data
    df_cat['Label_Ativo'] = df_cat.apply(
        lambda row: f"{row['Ativo']} ({row['Última Data'].strftime('%d/%m/%Y')})" 
        if pd.notna(row['Última Data']) else row['Ativo'], 
        axis=1
    )
    
    col_ret1, col_ret2 = st.columns(2)
    
    with col_ret1:
        st.markdown("#### Semanal")
        if not df_cat.empty and 'Retorno_Semana' in df_cat.columns:
            fig1 = px.bar(
                df_cat.sort_values('Retorno_Semana'), 
                x='Retorno_Semana', y='Label_Ativo', 
                orientation='h', 
                text_auto='.2%',
                color_discrete_sequence=['#189CD8'],
                template='plotly_white'
            )
            fig1.update_layout(
                xaxis_tickformat='.0%', 
                height=max(400, len(df_cat) * 40),
                showlegend=False,
                paper_bgcolor='white',
                plot_bgcolor='white',
                font=dict(color='#2C3E50', size=11),
                xaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title=""),
                yaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title="")
            )
            st.plotly_chart(fig1, use_container_width=True, theme="streamlit")
        else:
            st.warning("Sem dados")
    
    with col_ret2:
        st.markdown(f"#### {periodo_cat_graf}")
        
        # Verifica se a coluna existe
        if periodo_cat_graf == "Personalizado" and not st.session_state.get('custom_period_valid', False):
            st.warning("Configure o período personalizado na barra lateral primeiro.")
        elif not df_cat.empty and col_retorno_graf in df_cat.columns:
            fig2 = px.bar(
                df_cat.sort_values(col_retorno_graf), 
                x=col_retorno_graf, y='Label_Ativo', 
                orientation='h', 
                text_auto='.2%',
                color_discrete_sequence=['#28A745'],
                template='plotly_white'
            )
            fig2.update_layout(
                xaxis_tickformat='.0%', 
                height=max(400, len(df_cat) * 40),
                showlegend=False,
                paper_bgcolor='white',
                plot_bgcolor='white',
                font=dict(color='#2C3E50', size=11),
                xaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title=""),
                yaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title="")
            )
            st.plotly_chart(fig2, use_container_width=True, theme="streamlit")
        else:
            st.warning("Sem dados para este período")
    
    # SEÇÃO 2: VOLATILIDADE
    st.markdown("---")
    st.markdown("### Volatilidade")
    col_vol1, col_vol2 = st.columns(2)
    
    with col_vol1:
        st.markdown("#### Semanal")
        if not df_cat.empty and 'Vol_Semana' in df_cat.columns:
            fig_vol1 = px.bar(
                df_cat.sort_values('Vol_Semana', ascending=False), 
                x='Vol_Semana', y='Label_Ativo', 
                orientation='h', 
                text_auto='.2%',
                color_discrete_sequence=['#FFC107'],
                template='plotly_white'
            )
            fig_vol1.update_layout(
                xaxis_tickformat='.0%', 
                height=max(400, len(df_cat) * 40),
                showlegend=False,
                paper_bgcolor='white',
                plot_bgcolor='white',
                font=dict(color='#2C3E50', size=11),
                xaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title=""),
                yaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title="")
            )
            st.plotly_chart(fig_vol1, use_container_width=True, theme="streamlit")
        else:
            st.warning("Sem dados de volatilidade")
    
    with col_vol2:
        st.markdown(f"#### {periodo_cat_graf}")
        
        if periodo_cat_graf == "Personalizado" and not st.session_state.get('custom_period_valid', False):
            st.warning("Configure o período personalizado na barra lateral primeiro.")
        elif not df_cat.empty and col_vol_graf in df_cat.columns:
            fig_vol2 = px.bar(
                df_cat.sort_values(col_vol_graf, ascending=False), 
                x=col_vol_graf, y='Label_Ativo', 
                orientation='h', 
                text_auto='.2%',
                color_discrete_sequence=['#FF6B6B'],
                template='plotly_white'
            )
            fig_vol2.update_layout(
                xaxis_tickformat='.0%', 
                height=max(400, len(df_cat) * 40),
                showlegend=False,
                paper_bgcolor='white',
                plot_bgcolor='white',
                font=dict(color='#2C3E50', size=11),
                xaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title=""),
                yaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title="")
            )
            st.plotly_chart(fig_vol2, use_container_width=True, theme="streamlit")
        else:
            st.warning("Sem dados de volatilidade")
    
    # SEÇÃO 3: SHARPE RATIO
    st.markdown("---")
    st.markdown("### Sharpe Ratio")
    col_sharpe1, col_sharpe2 = st.columns(2)
    
    with col_sharpe1:
        st.markdown("#### Semanal")
        if not df_cat.empty and 'Sharpe_Semana' in df_cat.columns:
            fig_sh1 = px.bar(
                df_cat.sort_values('Sharpe_Semana'), 
                x='Sharpe_Semana', y='Label_Ativo', 
                orientation='h', 
                text_auto='.2f',
                color_discrete_sequence=['#17A2B8'],
                template='plotly_white'
            )
            fig_sh1.update_layout(
                height=max(400, len(df_cat) * 40),
                showlegend=False,
                paper_bgcolor='white',
                plot_bgcolor='white',
                font=dict(color='#2C3E50', size=11),
                xaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title=""),
                yaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title="")
            )
            st.plotly_chart(fig_sh1, use_container_width=True, theme="streamlit")
        else:
            st.warning("Sem dados de Sharpe")
    
    with col_sharpe2:
        sharpe_col = periodo_cat_graf.replace('Retorno_', 'Sharpe_')
        if periodo_cat_graf == "MTD":
            sharpe_col = "Sharpe_MTD"
        elif periodo_cat_graf == "YTD":
            sharpe_col = "Sharpe_YTD"
        else:
            sharpe_col = "Sharpe_Custom"
        
        st.markdown(f"#### {periodo_cat_graf}")
        
        if periodo_cat_graf == "Personalizado" and not st.session_state.get('custom_period_valid', False):
            st.warning("Configure o período personalizado na barra lateral primeiro.")
        elif not df_cat.empty and sharpe_col in df_cat.columns:
            fig_sh2 = px.bar(
                df_cat.sort_values(sharpe_col), 
                x=sharpe_col, y='Label_Ativo', 
                orientation='h', 
                text_auto='.2f',
                color_discrete_sequence=['#6C757D'],
                template='plotly_white'
            )
            fig_sh2.update_layout(
                height=max(400, len(df_cat) * 40),
                showlegend=False,
                paper_bgcolor='white',
                plot_bgcolor='white',
                font=dict(color='#2C3E50', size=11),
                xaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title=""),
                yaxis=dict(gridcolor='#E9ECEF', color='#2C3E50', title="")
            )
            st.plotly_chart(fig_sh2, use_container_width=True, theme="streamlit")
        else:
            st.warning("Sem dados de Sharpe")

with tab_graf:
    st.markdown("<h3 style='color: #189CD8;'><strong>Explorador Visual - Análise por Categorias</strong></h3>", unsafe_allow_html=True)
    
    # Info: aponta para sidebar como fonte única
    if st.session_state.get('modo_analise') == "Período Personalizado":
        if st.session_state.get('custom_period_valid'):
            data_ini_v, data_fim_v, _, _ = validar_e_obter_periodo_custom()
            if data_ini_v and data_fim_v:
                st.info(f"Período custom ativo: {data_ini_v.strftime('%d/%m/%Y')} a {data_fim_v.strftime('%d/%m/%Y')} | Configurável na barra lateral")
        else:
            st.warning("Período custom inválido | Configure na barra lateral")
    
    # Layout principal: Seleção de categorias e período
    col_g1, col_g2 = st.columns([3, 1])
    
    with col_g1:
        # Seleção de categorias (foco principal)
        categorias_disponiveis = list(CATEGORIAS.keys())
        categorias_sel = st.multiselect(
            "Selecione as categorias para exibir:",
            categorias_disponiveis,
            default=st.session_state.categorias_selecionadas_grafico,
            key="cats_graf_widget"
        )
        st.session_state.categorias_selecionadas_grafico = categorias_sel if categorias_sel else st.session_state.categorias_selecionadas_grafico
    
    with col_g2:
        # Opções disponíveis dependem se período custom está calculado
        opcoes_periodo_graf = ["Semanal", "MTD", "YTD", "ITD"]
        # Sempre mostra "Personalizado" se o modo estiver ativo (mesmo que ainda inválido)
        if st.session_state.get('modo_analise') == "Período Personalizado":
            opcoes_periodo_graf.append("Personalizado")
        
        # Ajusta index se Personalizado não estiver disponível
        valor_anterior_graf = st.session_state.periodo_explorador
        if valor_anterior_graf not in opcoes_periodo_graf:
            valor_anterior_graf = "YTD"
            st.session_state.periodo_explorador = valor_anterior_graf
        
        periodo_expl = st.selectbox(
            "Período:",
            opcoes_periodo_graf,
            index=opcoes_periodo_graf.index(valor_anterior_graf) if valor_anterior_graf in opcoes_periodo_graf else 2,
            key="periodo_expl_widget",
            help="Escolha o período para análise gráfica"
        )
        st.session_state.periodo_explorador = periodo_expl
    
    # Opção de exibir somente produto Ghia (para categorias específicas)
    categorias_com_ghia = ["Renda Fixa", "Ações", "Multimercados", "FIIs"]
    categorias_selecionadas_com_ghia = [c for c in st.session_state.categorias_selecionadas_grafico if c in categorias_com_ghia]
    
    if categorias_selecionadas_com_ghia:
        exibir_so_ghia = st.checkbox(
            "Exibir somente o produto Ghia",
            value=st.session_state.exibir_so_ghia,
            key="exibir_ghia_widget"
        )
        st.session_state.exibir_so_ghia = exibir_so_ghia
    else:
        st.session_state.exibir_so_ghia = False
    
    # Obter todos os ativos das categorias selecionadas
    ativos_das_categorias = []
    for cat in st.session_state.categorias_selecionadas_grafico:
        if cat in CATEGORIAS:
            ativos_das_categorias.extend(CATEGORIAS[cat])
    
    # Aplicar filtro Ghia se ativado
    if st.session_state.exibir_so_ghia and categorias_selecionadas_com_ghia:
        produtos_ghia_por_cat = {
            "Renda Fixa": "Ghia RF",
            "Ações": "Ghia RV",
            "Multimercados": "Ghia MM",
            "FIIs": "Ghia FIIs"
        }
        ativos_filtrados = []
        for cat in categorias_selecionadas_com_ghia:
            produto = produtos_ghia_por_cat.get(cat)
            if produto and produto in ativos_das_categorias:
                ativos_filtrados.append(produto)
        # Adicionar ativos de categorias que não têm filtro Ghia
        for cat in st.session_state.categorias_selecionadas_grafico:
            if cat not in categorias_com_ghia and cat in CATEGORIAS:
                ativos_filtrados.extend(CATEGORIAS[cat])
        ativos_das_categorias = ativos_filtrados
    
    # Remover duplicatas mantendo ordem
    ativos_das_categorias = list(dict.fromkeys(ativos_das_categorias))
    
    # Filtrar apenas ativos que existem no DataFrame
    ativos_disponiveis = [a for a in ativos_das_categorias if a in df_historico.columns]
    
    # Aplicar omissões confirmadas
    sel_assets = [a for a in ativos_disponiveis if a not in st.session_state.ativos_omitidos_confirmados]
    
    # Informação sobre ativos selecionados
    if sel_assets:
        st.info(f"Exibindo {len(sel_assets)} ativo(s) de {len(st.session_state.categorias_selecionadas_grafico)} categoria(s)")
    
    # Organizar expanders lado a lado
    col_exp1, col_exp2 = st.columns(2)
    
    # Seleção negativa na coluna esquerda
    with col_exp1:
        if ativos_disponiveis and not st.session_state.exibir_so_ghia:
            with st.expander("Configurações Avançadas - Omitir Ativos Específicos"):
                st.markdown("**Selecione os ativos que deseja OMITIR do gráfico:**")
                
                # Usar variável temporária que só afeta após confirmar
                ativos_omitir = st.multiselect(
                    "Ativos a omitir:",
                    ativos_disponiveis,
                    default=st.session_state.ativos_omitidos_temp,
                    key="ativos_omitir_widget"
                )
                st.session_state.ativos_omitidos_temp = ativos_omitir
                
                col_btn1, col_btn2 = st.columns([1, 1])
                with col_btn1:
                    if st.button("Confirmar", type="primary", key="btn_confirmar_omitir"):
                        st.session_state.ativos_omitidos_confirmados = st.session_state.ativos_omitidos_temp
                with col_btn2:
                    if st.button("Limpar", key="btn_limpar_omitir"):
                        st.session_state.ativos_omitidos_temp = []
                        st.session_state.ativos_omitidos_confirmados = []
    
    # Link para modo de comparação direta na coluna direita
    with col_exp2:
        with st.expander("Modo Avançado: Comparação Direta de Ativos"):
            st.markdown("**Selecione ativos específicos para comparar (até 8):**")
            all_assets = df_historico.columns.drop('Data').tolist()
            all_assets = [a for a in all_assets if "Dup" not in a]
            
            sel_assets_manual = st.multiselect(
                "Ativos para comparação:",
                all_assets,
                default=[],
                max_selections=8,
                key="sel_assets_manual"
            )
            
            if st.button("Usar seleção manual", type="secondary"):
                if sel_assets_manual:
                    sel_assets = sel_assets_manual
                    st.success(f"Usando {len(sel_assets)} ativos selecionados manualmente")
    
    # Seção de datas e configurações
    if periodo_expl == "Personalizado":
        # Usa os valores do session_state (definidos no controle geral)
        data_ini_v, data_fim_v, is_valid, msg_erro = validar_e_obter_periodo_custom()
        
        if not is_valid:
            st.error(f"{msg_erro}. Configure o período na barra lateral primeiro.")
            sel_assets = []  # Impede renderização de gráfico com período inválido
        else:
            st.info(f"Usando período definido: {data_ini_v.strftime('%d/%m/%Y')} a {data_fim_v.strftime('%d/%m/%Y')}")
            # Converte para datetime
            d_graf_ini = pd.to_datetime(data_ini_v)
            d_graf_fim = pd.to_datetime(data_fim_v)
    else:
        # Calcula automaticamente baseado no período E no tipo_semana
        tipo_semana = st.session_state.get('tipo_semana', 'Semana Passada')

        if periodo_expl == "Semanal":
            if tipo_semana == "Semana Passada":
                d_graf_ini = calcular_sexta_feira_semana_retrasada(data_ref)
                d_graf_fim = calcular_sexta_feira_semana_anterior(data_ref)
            else:  # Semana Corrente
                d_graf_ini = calcular_sexta_feira_semana_anterior(data_ref)
                d_graf_fim = calcular_sexta_feira_semana_atual(data_ref)
        elif periodo_expl == "MTD":
            d_graf_ini = calcular_ultimo_dia_util_mes_anterior(data_ref)
            d_graf_fim = data_ref
        elif periodo_expl == "YTD":
            d_graf_ini = calcular_ultimo_dia_util_ano_anterior(data_ref)
            d_graf_fim = data_ref
        else:  # ITD
            d_graf_ini = df_historico['Data'].min()
            d_graf_fim = data_ref

        st.info(f"Período: {pd.to_datetime(d_graf_ini).strftime('%d/%m/%Y')} a {pd.to_datetime(d_graf_fim).strftime('%d/%m/%Y')}")
    
    st.markdown("---")
    
    if sel_assets:
        # Garante que d_graf_ini e d_graf_fim sejam datetime (não date) para comparação com pandas
        d_graf_ini = pd.to_datetime(d_graf_ini)
        d_graf_fim = pd.to_datetime(d_graf_fim)

        # Clampa ao range disponível do dataset (evita períodos vazios por datas fora do intervalo)
        data_min = pd.to_datetime(df_historico['Data'].min())
        data_max = pd.to_datetime(df_historico['Data'].max())
        d_graf_ini_eff = max(d_graf_ini, data_min)
        d_graf_fim_eff = min(d_graf_fim, data_max)

        if d_graf_ini_eff != d_graf_ini or d_graf_fim_eff != d_graf_fim:
            st.caption(
                f"Período ajustado ao range de dados: {d_graf_ini_eff.strftime('%d/%m/%Y')} a {d_graf_fim_eff.strftime('%d/%m/%Y')}"
            )

        d_graf_ini, d_graf_fim = d_graf_ini_eff, d_graf_fim_eff

        if d_graf_ini > d_graf_fim:
            st.warning("Período selecionado não possui dados disponíveis.")
            mask_g = pd.Series(False, index=df_historico.index)
            df_g = pd.DataFrame()
        else:
            mask_g = (df_historico['Data'] >= d_graf_ini) & (df_historico['Data'] <= d_graf_fim)
            df_g = df_historico.loc[mask_g, ['Data'] + sel_assets].set_index('Data').dropna(how='all')
        
        if not df_g.empty:
            df_g = calcular_retorno_acumulado_robusto(df_g)
            # Remove linhas onde TODOS os ativos são NaN (antes do inception)
            df_g = df_g.dropna(how='all')
            
            titulo = "Evolução do Retorno Acumulado no Período"
            y_tickformat = ".2%"
            y_titulo = "Retorno Acumulado"
            
            fig_evolucao = px.line(
                df_g,
                title=titulo,
                labels={'value': 'Performance', 'Data': 'Data', 'variable': 'Ativo'},
                template='plotly_white'
            )
            fig_evolucao.update_layout(
                hovermode='x unified',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color='#2C3E50')),
                yaxis_tickformat=y_tickformat,
                yaxis_title=y_titulo,
                height=550,
                paper_bgcolor='white',
                plot_bgcolor='white',
                font=dict(color='#2C3E50', size=12),
                title_font=dict(color='#2C3E50', size=16),
                xaxis=dict(
                    gridcolor='#E9ECEF', 
                    color='#2C3E50', 
                    tickformat='%d/%m/%Y',
                    rangebreaks=[dict(bounds=["sat", "sun"])]
                ),
                yaxis=dict(gridcolor='#E9ECEF', color='#2C3E50')
            )
            st.plotly_chart(fig_evolucao, use_container_width=True, theme="streamlit")
            
            # Gráficos de Risco
            st.markdown("---")
            st.markdown("### Análise de Risco")
            
            col_risk1, col_risk2 = st.columns(2)
            
            with col_risk1:
                st.markdown("#### Evolução da Volatilidade no Período")
                # Calcula volatilidade acumulada desde o início do período
                df_g_raw = df_historico.loc[mask_g, ['Data'] + sel_assets].set_index('Data')
                # Remove linhas com todos NaN
                df_g_raw = df_g_raw.dropna(how='all')
                # Calcula volatilidade expandindo (desde o início até cada dia)
                df_vol_rolling = df_g_raw.expanding(min_periods=2).std() * np.sqrt(252)
                
                fig_vol = px.line(
                    df_vol_rolling,
                    labels={'value': 'Volatilidade Anualizada', 'Data': 'Data', 'variable': 'Ativo'},
                    template='plotly_white'
                )
                fig_vol.update_layout(
                    hovermode='x unified',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color='#2C3E50')),
                    yaxis_tickformat='.1%',
                    yaxis_title="Volatilidade",
                    height=400,
                    paper_bgcolor='white',
                    plot_bgcolor='white',
                    font=dict(color='#2C3E50', size=11),
                    xaxis=dict(
                        gridcolor='#E9ECEF', 
                        color='#2C3E50', 
                        tickformat='%d/%m/%Y',
                        rangebreaks=[dict(bounds=["sat", "sun"])]
                    ),
                    yaxis=dict(gridcolor='#E9ECEF', color='#2C3E50')
                )
                st.plotly_chart(fig_vol, use_container_width=True, theme="streamlit")
            
            with col_risk2:
                st.markdown("#### Drawdown")
                # Calcula drawdown
                df_cumret = (1 + df_g_raw).cumprod()
                df_drawdown = (df_cumret / df_cumret.cummax() - 1)
                
                fig_dd = px.line(
                    df_drawdown,
                    labels={'value': 'Drawdown', 'Data': 'Data', 'variable': 'Ativo'},
                    template='plotly_white'
                )
                fig_dd.update_layout(
                    hovermode='x unified',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color='#2C3E50')),
                    yaxis_tickformat='.1%',
                    yaxis_title="Drawdown",
                    height=400,
                    paper_bgcolor='white',
                    plot_bgcolor='white',
                    font=dict(color='#2C3E50', size=11),
                    xaxis=dict(
                        gridcolor='#E9ECEF', 
                        color='#2C3E50', 
                        tickformat='%d/%m/%Y',
                        rangebreaks=[dict(bounds=["sat", "sun"])]
                    ),
                    yaxis=dict(gridcolor='#E9ECEF', color='#2C3E50')
                )
                st.plotly_chart(fig_dd, use_container_width=True, theme="streamlit")
        else:
            st.info("Sem dados para o período selecionado.")
    else:
        st.info("Selecione pelo menos um ativo para visualizar.")

with tab_heatmap:
    st.markdown("<h3 style='color: #189CD8;'> <strong>Histórico de retornos mensais</strong></h3>", unsafe_allow_html=True)
    
    col_h1, col_h2 = st.columns([2, 1])
    
    with col_h1:
        # Seleciona categoria
        cat_heatmap = st.selectbox(
            "Categoria:",
            list(CATEGORIAS.keys()),
            key="cat_heatmap"
        )
    
    with col_h2:
        # Opções de visualização
        mostrar_valores = st.checkbox("Mostrar valores (%)", value=True)
    
    st.markdown("---")
    
    # Lista ativos da categoria
    ativos_disponiveis = CATEGORIAS[cat_heatmap]
    ativos_no_df = [a for a in ativos_disponiveis if a in df_historico.columns]
    
    if not ativos_no_df:
        st.warning("Nenhum ativo disponível nesta categoria")
    else:
        ativo_selecionado = st.selectbox(
            "Ativo:",
            ativos_no_df,
            key="ativo_heatmap"
        )
        
        if ativo_selecionado:
            # Calcula retornos mensais
            df_mensal = calcular_retornos_mensais(df_historico, ativo_selecionado)
            
            if not df_mensal.empty:
                # Determina benchmark baseado na categoria
                if cat_heatmap == "Ações":
                    benchmark = "Ibovespa"
                elif cat_heatmap == "FIIs":
                    benchmark = "IFIX"
                else:
                    benchmark = "CDI"
                
                # Calcula retornos do benchmark
                df_bench = calcular_retornos_mensais(df_historico, benchmark)
                
                # SEÇÃO 1: TABELA DE RETORNOS MENSAIS (com % vs benchmark) - POSIÇÃO PRIVILEGIADA
                st.markdown("### Tabela de Retornos Mensais")
                st.caption(f"Retornos do ativo e % vs {benchmark}")
                
                # Cria DataFrame intercalado
                df_mensal = calcular_retornos_mensais(df_historico, ativo_selecionado)
                
                # Cria lista para armazenar linhas intercaladas
                linhas_intercaladas = []
                
                for ano in df_mensal.index:
                    # Linha 1: Retorno do ativo
                    linha_ativo = df_mensal.loc[ano].copy()
                    linhas_intercaladas.append((f"{ano}", linha_ativo))
                    
                    # Linha 2: % vs benchmark (percentual relativo, não diferença)
                    if ano in df_bench.index:
                        linha_bench = df_bench.loc[ano].copy()
                        # Calcula percentual: (retorno_ativo / retorno_benchmark)
                        # Não multiplica por 100 pois a formatação %.2% já faz isso
                        linha_pct = linha_ativo / linha_bench
                        linhas_intercaladas.append((f"% {benchmark}", linha_pct))
                    else:
                        linha_pct = pd.Series([np.nan] * len(linha_ativo), index=linha_ativo.index)
                        linhas_intercaladas.append((f"% {benchmark}", linha_pct))
                
                # Cria DataFrame com índice customizado
                indices = [linha[0] for linha in linhas_intercaladas]
                dados = [linha[1] for linha in linhas_intercaladas]
                df_display = pd.DataFrame(dados, index=indices)
                
                # Formata valores
                for col in df_display.columns:
                    df_display[col] = df_display[col].apply(
                        lambda x: f"{x:.2%}" if pd.notna(x) else "-"
                    )
                
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    height=min(600, 50 + len(df_display) * 35)
                )
                
                # SEÇÃO 2: ÍNDICES DE RENTABILIDADE (TRANSPOSTA: JANELAS COMO COLUNAS)
                st.markdown("---")
                st.markdown("### Índices de Rentabilidade")
                
                # Calcula rentabilidades em diferentes janelas
                hoje_data = df_historico['Data'].max()
                rentabilidades = {}
                
                # No Mês
                mes_inicio = calcular_ultimo_dia_util_mes_anterior(hoje_data)
                mask_mes = (df_historico['Data'] > mes_inicio) & (df_historico['Data'] <= hoje_data)
                if ativo_selecionado in df_historico.columns:
                    ret_mes = (1 + df_historico.loc[mask_mes, ativo_selecionado]).prod() - 1
                    vol_mes = df_historico.loc[mask_mes, ativo_selecionado].std() * np.sqrt(252)
                    rentabilidades['No Mês'] = {'Rentabilidade': ret_mes, 'Volatilidade': vol_mes}
                
                # No Ano
                ano_inicio = calcular_ultimo_dia_util_ano_anterior(hoje_data)
                mask_ano = (df_historico['Data'] > ano_inicio) & (df_historico['Data'] <= hoje_data)
                ret_ano = (1 + df_historico.loc[mask_ano, ativo_selecionado]).prod() - 1
                vol_ano = df_historico.loc[mask_ano, ativo_selecionado].std() * np.sqrt(252)
                rentabilidades['No Ano'] = {'Rentabilidade': ret_ano, 'Volatilidade': vol_ano}
                
                # Janelas de tempo em meses
                for meses in [3, 6, 12, 24, 36, 48, 60]:
                    data_inicio = hoje_data - pd.DateOffset(months=meses)
                    mask = (df_historico['Data'] >= data_inicio) & (df_historico['Data'] <= hoje_data)
                    if mask.sum() > 0:
                        ret = (1 + df_historico.loc[mask, ativo_selecionado]).prod() - 1
                        vol = df_historico.loc[mask, ativo_selecionado].std() * np.sqrt(252)
                        rentabilidades[f'{meses} Meses'] = {'Rentabilidade': ret, 'Volatilidade': vol}
                
                # Total (desde início)
                ret_total = (1 + df_historico[ativo_selecionado]).prod() - 1
                vol_total = df_historico[ativo_selecionado].std() * np.sqrt(252)
                rentabilidades['Total'] = {'Rentabilidade': ret_total, 'Volatilidade': vol_total}
                
                # Cria DataFrame (TRANSPOSTO: Janelas como colunas, Métricas como linhas)
                df_rent = pd.DataFrame(rentabilidades)
                
                # Formata para exibição
                df_rent_display = df_rent.copy()
                for col in df_rent_display.columns:
                    df_rent_display[col] = df_rent_display[col].apply(lambda x: f"{x:.2%}" if pd.notna(x) else "-")
                
                st.dataframe(df_rent_display, use_container_width=True)
                
                # SEÇÃO 3: CONSISTÊNCIA
                st.markdown("---")
                st.markdown("### Consistência")
                
                # Calcula estatísticas mensais
                df_mensal_calc = calcular_retornos_mensais(df_historico, ativo_selecionado)
                retornos_mensais_flat = df_mensal_calc.values.flatten()
                retornos_mensais_flat = retornos_mensais_flat[~pd.isna(retornos_mensais_flat)]
                
                meses_positivos = (retornos_mensais_flat > 0).sum()
                meses_negativos = (retornos_mensais_flat < 0).sum()
                total_meses = len(retornos_mensais_flat)
                
                consistencia_data = {
                    'Meses Positivos': f"{meses_positivos} ({meses_positivos/total_meses*100:.1f}%)" if total_meses > 0 else "-",
                    'Meses Negativos': f"{meses_negativos} ({meses_negativos/total_meses*100:.1f}%)" if total_meses > 0 else "-",
                    'Maior Retorno': f"{retornos_mensais_flat.max():.2%}" if len(retornos_mensais_flat) > 0 else "-",
                    'Menor Retorno': f"{retornos_mensais_flat.min():.2%}" if len(retornos_mensais_flat) > 0 else "-",
                    'Mediana dos Retornos': f"{np.median(retornos_mensais_flat):.2%}" if len(retornos_mensais_flat) > 0 else "-"
                }
                
                df_consistencia = pd.DataFrame([consistencia_data], index=[ativo_selecionado])
                st.dataframe(df_consistencia, use_container_width=True)
                
                # SEÇÃO 4: TABELA DE VOLATILIDADE MENSAL
                st.markdown("---")
                st.markdown("### Volatilidade Mensal")
                
                # Calcula volatilidade por mês/ano
                df_vol_mensal = df_historico[['Data', ativo_selecionado]].copy()
                df_vol_mensal['Ano'] = pd.to_datetime(df_vol_mensal['Data']).dt.year
                df_vol_mensal['Mes'] = pd.to_datetime(df_vol_mensal['Data']).dt.month
                
                # Agrupa e calcula vol
                vol_pivot = df_vol_mensal.groupby(['Ano', 'Mes'])[ativo_selecionado].std() * np.sqrt(252)
                vol_pivot = vol_pivot.reset_index().pivot(index='Ano', columns='Mes', values=ativo_selecionado)
                vol_pivot.columns = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
                
                # Adiciona coluna de Volatilidade Acumulada no Ano (média dos meses disponíveis)
                vol_pivot['Acum. Ano'] = vol_pivot.apply(
                    lambda row: row.dropna().mean() if len(row.dropna()) > 0 else np.nan, axis=1
                )
                
                # Adiciona coluna de Volatilidade Total (média de todos os anos)
                vols_acumuladas = []
                for ano in vol_pivot.index:
                    # Filtra dados até este ano
                    anos_ate_aqui = [a for a in vol_pivot.index if a <= ano]
                    df_ate_ano = df_historico[df_historico['Data'].dt.year.isin(anos_ate_aqui)]
                    vol_total = df_ate_ano[ativo_selecionado].std() * np.sqrt(252)
                    vols_acumuladas.append(vol_total)
                
                vol_pivot['Acum. Total'] = vols_acumuladas
                
                # Formata para exibição
                df_vol_display = vol_pivot.copy()
                for col in df_vol_display.columns:
                    df_vol_display[col] = df_vol_display[col].apply(
                        lambda x: f"{x:.2%}" if pd.notna(x) else "-"
                    )
                
                st.dataframe(
                    df_vol_display,
                    use_container_width=True,
                    height=min(400, 50 + len(df_vol_display) * 35)
                )
                
                # SEÇÃO 5: HEATMAP DE RETORNOS (POSIÇÃO INFERIOR)
                st.markdown("---")
                st.markdown("### Heatmap de Retornos")
                
                # Prepara dados para o heatmap (sem colunas extras de acumulados)
                meses_nomes = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
                df_heatmap_display = df_mensal[meses_nomes].copy()
                
                # Cria heatmap com plotly
                fig_heatmap = px.imshow(
                    df_heatmap_display.values,
                    labels=dict(x="Mês", y="Ano", color="Retorno"),
                    x=df_heatmap_display.columns,
                    y=df_heatmap_display.index,
                    color_continuous_scale='RdYlGn',
                    color_continuous_midpoint=0,
                    aspect='auto',
                    title=f"Retornos Mensais - {ativo_selecionado}",
                    template='plotly_white'
                )
                
                # Adiciona valores nas células se solicitado
                if mostrar_valores:
                    annotations = []
                    for i, ano in enumerate(df_heatmap_display.index):
                        for j, mes in enumerate(df_heatmap_display.columns):
                            valor = df_heatmap_display.iloc[i, j]
                            if pd.notna(valor):
                                annotations.append(
                                    dict(
                                        text=f"{valor:.1%}",
                                        x=mes, y=ano,
                                        xref='x', yref='y',
                                        showarrow=False,
                                        font=dict(size=10, color='black' if abs(valor) < 0.05 else 'white')
                                    )
                                )
                    fig_heatmap.update_layout(annotations=annotations)
                
                fig_heatmap.update_layout(
                    height=400 + (len(df_heatmap_display) * 30),
                    xaxis_title="Mês",
                    yaxis_title="Ano",
                    coloraxis_colorbar=dict(
                        title=dict(text="Retorno", font=dict(color='#2C3E50')),
                        tickformat=".1%",
                        tickfont=dict(color='#2C3E50')
                    ),
                    paper_bgcolor='white',
                    plot_bgcolor='white',
                    font=dict(color='#2C3E50', size=12),
                    title_font=dict(color='#2C3E50', size=16),
                    xaxis=dict(color='#2C3E50'),
                    yaxis=dict(color='#2C3E50')
                )
                
                st.plotly_chart(fig_heatmap, use_container_width=True, theme="streamlit")
                
                # SEÇÃO 3: TABELA DE VOLATILIDADE MENSAL
                st.markdown("---")
                st.markdown("### Volatilidade Mensal")
                
                # Calcula volatilidade por mês/ano
                df_vol_mensal = df_historico[['Data', ativo_selecionado]].copy()
                df_vol_mensal['Ano'] = pd.to_datetime(df_vol_mensal['Data']).dt.year
                df_vol_mensal['Mes'] = pd.to_datetime(df_vol_mensal['Data']).dt.month
                
                # Agrupa e calcula vol
                vol_pivot = df_vol_mensal.groupby(['Ano', 'Mes'])[ativo_selecionado].std() * np.sqrt(252)
                vol_pivot = vol_pivot.reset_index().pivot(index='Ano', columns='Mes', values=ativo_selecionado)
                vol_pivot.columns = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
                
                # Formata para exibição
                df_vol_display = vol_pivot.copy()
                for col in df_vol_display.columns:
                    df_vol_display[col] = df_vol_display[col].apply(
                        lambda x: f"{x:.2%}" if pd.notna(x) else "-"
                    )
                
                st.dataframe(
                    df_vol_display,
                    use_container_width=True,
                    height=min(400, 50 + len(df_vol_display) * 35)
                )
                
                # Botão de download
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    csv_mensal = df_mensal.to_csv().encode('utf-8')
                    st.download_button(
                        label="Download Retornos (CSV)",
                        data=csv_mensal,
                        file_name=f"retornos_mensais_{ativo_selecionado}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                    )
                with col_dl2:
                    csv_vol = vol_pivot.to_csv().encode('utf-8')
                    st.download_button(
                        label="Download Volatilidade (CSV)",
                        data=csv_vol,
                        file_name=f"vol_mensal_{ativo_selecionado}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                    )
            else:
                st.info("Dados insuficientes para gerar histórico mensal.")