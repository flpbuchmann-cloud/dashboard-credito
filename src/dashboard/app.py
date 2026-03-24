"""
Dashboard de Crédito - Análise Financeira de Empresas Brasileiras (B3).

Streamlit app que exibe indicadores financeiros, múltiplos e gráficos
de evolução a partir dos dados coletados da CVM e do Buscador RI.

Uso:
    streamlit run src/dashboard/app.py
"""

import os
import sys
import json
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as st_components

# Adicionar raiz do projeto ao path
PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, PROJECT_ROOT)
from src.calculo.indicadores import (
    calcular_indicadores,
    formatar_tabela_dre,
    formatar_tabela_fluxo_caixa,
    formatar_tabela_estrutura_capital,
    formatar_tabela_capital_giro,
    formatar_tabela_multiplos,
    formatar_tabela_fleuriet,
)
from src.dashboard.auth import (
    show_login,
    show_registration_form,
    show_admin_panel,
    show_logout,
)

# Detectar se está rodando em deploy (Streamlit Cloud) ou local
# No deploy, os dados ficam em data/empresas/ dentro do repo
# Localmente, ficam no Google Drive
DEPLOY_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "empresas")
IS_DEPLOYED = os.path.exists(DEPLOY_DATA_DIR) and not os.path.exists("G:/Meu Drive/Análise de Crédito")


def _pasta_empresa(nome_pasta: str) -> str:
    """Retorna o caminho correto da pasta da empresa (local ou deploy)."""
    if IS_DEPLOYED:
        return os.path.join(DEPLOY_DATA_DIR, nome_pasta)
    return f"G:/Meu Drive/Análise de Crédito/{nome_pasta}"


# Mapeamento nome da empresa → nome da pasta no deploy
_PASTA_DEPLOY = {
    "CSN Mineração": "CSN Mineração",
    "CSN - Companhia Siderurgica Nacional": "CSN Siderurgica",
    "Minerva Foods": "Minerva",
    "Plano & Plano": "Plano e Plano",
    "Klabin": "Klabin",
    "Eneva": "Eneva",
    "Cemig": "Cemig",
    "Equatorial": "Equatorial",
    "Brava Energia": "Brava Energia",
    "Raízen": "Raizen",
    "Rede D'Or": "Rede Dor",
    "Movida": "Movida",
    "Vamos": "Vamos",
    "JSL": "JSL",
}


def _sync_para_deploy(caminho_local: str, empresa_selecionada: str):
    """
    Copia arquivo salvo localmente para o diretório de deploy (data/empresas/)
    e faz commit+push automático para o dashboard hospedado.
    """
    if IS_DEPLOYED:
        return  # No deploy, não precisa sincronizar

    nome_pasta = _PASTA_DEPLOY.get(empresa_selecionada)
    if not nome_pasta:
        return

    pasta_local = f"G:/Meu Drive/Análise de Crédito/{nome_pasta}"
    # Determinar caminho relativo dentro da pasta da empresa
    try:
        rel = os.path.relpath(caminho_local, pasta_local)
    except ValueError:
        return

    destino = os.path.join(DEPLOY_DATA_DIR, nome_pasta, rel)
    os.makedirs(os.path.dirname(destino), exist_ok=True)

    import shutil
    shutil.copy2(caminho_local, destino)

    # Auto commit + push
    try:
        import subprocess
        subprocess.run(
            ["git", "add", destino],
            cwd=PROJECT_ROOT, capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Sync {nome_pasta}/{rel} from localhost"],
            cwd=PROJECT_ROOT, capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "push"],
            cwd=PROJECT_ROOT, capture_output=True, timeout=30,
        )
    except Exception:
        pass  # Falha silenciosa — sync local foi feito, push é best-effort


# =========================================================================
# CONFIGURAÇÃO
# =========================================================================
st.set_page_config(
    page_title="Dashboard de Crédito",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Empresas disponíveis (mesma estrutura do main.py)
EMPRESAS = {
    "CSN Mineração": {
        "ticker": "CMIN3",
        "setor": "Mineração",
        "pasta": _pasta_empresa("CSN Mineração"),
    },
    "CSN - Companhia Siderurgica Nacional": {
        "ticker": "CSNA3",
        "setor": "Siderurgia",
        "pasta": _pasta_empresa("CSN Siderurgica"),
    },
    "Minerva Foods": {
        "ticker": "BEEF3",
        "setor": "Alimentos / Frigoríficos",
        "pasta": _pasta_empresa("Minerva"),
    },
    "Plano & Plano": {
        "ticker": "PLPL3",
        "setor": "Construção Civil / Incorporação",
        "pasta": _pasta_empresa("Plano e Plano"),
    },
    "Klabin": {
        "ticker": "KLBN11",
        "setor": "Papel e Celulose",
        "pasta": _pasta_empresa("Klabin"),
    },
    "Eneva": {
        "ticker": "ENEV3",
        "setor": "Energia / Gás e Geração",
        "pasta": _pasta_empresa("Eneva"),
    },
    "Cemig": {
        "ticker": "CMIG4",
        "setor": "Energia Elétrica",
        "pasta": _pasta_empresa("Cemig"),
    },
    "Equatorial": {
        "ticker": "EQTL3",
        "setor": "Energia Elétrica / Distribuição",
        "pasta": _pasta_empresa("Equatorial"),
    },
    "Brava Energia": {
        "ticker": "BRAV3",
        "setor": "Petróleo e Gás",
        "pasta": _pasta_empresa("Brava Energia"),
    },
    "Raízen": {
        "ticker": "RAIZ4",
        "setor": "Energia / Açúcar e Etanol",
        "pasta": _pasta_empresa("Raizen"),
    },
    "Rede D'Or": {
        "ticker": "RDOR3",
        "setor": "Saúde",
        "pasta": _pasta_empresa("Rede Dor"),
    },
    "Movida": {
        "ticker": "MOVI3",
        "setor": "Locação de Veículos",
        "pasta": _pasta_empresa("Movida"),
    },
    "Vamos": {
        "ticker": "VAMO3",
        "setor": "Locação de Caminhões e Máquinas",
        "pasta": _pasta_empresa("Vamos"),
    },
    "JSL": {
        "ticker": "JSLG3",
        "setor": "Logística",
        "pasta": _pasta_empresa("JSL"),
    },
}

CORES = {
    "azul": "#1f77b4",
    "verde": "#2ca02c",
    "vermelho": "#d62728",
    "laranja": "#ff7f0e",
    "roxo": "#9467bd",
    "cinza": "#7f7f7f",
    "azul_claro": "#aec7e8",
    "verde_claro": "#98df8a",
    "vermelho_claro": "#ff9896",
}


# =========================================================================
# FUNÇÕES AUXILIARES
# =========================================================================
def fmt_bilhoes(valor):
    """Formata valor em bilhões."""
    if pd.isna(valor):
        return "-"
    return f"R$ {valor / 1e9:.2f} bi"


def fmt_milhoes(valor):
    """Formata valor em milhões."""
    if pd.isna(valor):
        return "-"
    return f"R$ {valor / 1e6:.0f} mi"


def fmt_pct(valor):
    """Formata percentual."""
    if pd.isna(valor):
        return "-"
    return f"{valor:.1%}"


def fmt_multiplo(valor):
    """Formata múltiplo (ex: 2.5x)."""
    if pd.isna(valor):
        return "-"
    return f"{valor:.2f}x"


def estilo_valor(valor, inverter=False):
    """Retorna cor baseada no valor (positivo=verde, negativo=vermelho)."""
    if pd.isna(valor):
        return ""
    positivo = valor > 0
    if inverter:
        positivo = not positivo
    return "color: #2ca02c" if positivo else "color: #d62728"


def criar_tabela_formatada(df, formato_colunas, titulo=""):
    """Cria tabela com formatação condicional."""
    display_df = df.copy().reset_index(drop=True)

    # Transpor para ter períodos como colunas
    if "Período" in display_df.columns:
        display_df = display_df.set_index("Período").T
    elif "label" in display_df.columns:
        display_df = display_df.set_index("label").T

    return display_df


# =========================================================================
# GRÁFICOS
# =========================================================================
def grafico_barras_evolucao(df, colunas, nomes, cores, titulo, formato="bilhoes"):
    """Gráfico de barras com evolução temporal."""
    fig = go.Figure()
    labels = df["label"].tolist()

    for col, nome, cor in zip(colunas, nomes, cores):
        valores = df[col].tolist()
        if formato == "bilhoes":
            texto = [f"R$ {v/1e9:.1f}bi" if not pd.isna(v) else "" for v in valores]
        else:
            texto = [f"{v:.1%}" if not pd.isna(v) else "" for v in valores]

        fig.add_trace(go.Bar(
            name=nome,
            x=labels,
            y=valores,
            marker_color=cor,
            text=texto,
            textposition="outside",
            textfont=dict(size=9),
        ))

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=16)),
        barmode="group",
        height=400,
        margin=dict(t=50, b=30, l=50, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(gridcolor="#eee"),
        plot_bgcolor="white",
    )
    return fig


def grafico_linhas_multiplos(df, colunas, nomes, cores, titulo):
    """Gráfico de linhas para múltiplos."""
    fig = go.Figure()
    labels = df["label"].tolist()

    for col, nome, cor in zip(colunas, nomes, cores):
        fig.add_trace(go.Scatter(
            name=nome,
            x=labels,
            y=df[col].tolist(),
            mode="lines+markers",
            line=dict(color=cor, width=2),
            marker=dict(size=6),
        ))

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=16)),
        height=350,
        margin=dict(t=50, b=30, l=50, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(gridcolor="#eee"),
        plot_bgcolor="white",
    )
    return fig


def grafico_margens(df, titulo="Evolução das Margens"):
    """Gráfico de linhas das margens."""
    fig = go.Figure()
    labels = df["label"].tolist()

    margens = [
        ("margem_bruta", "Margem Bruta", CORES["azul"]),
        ("margem_ebitda", "Margem EBITDA", CORES["verde"]),
        ("margem_liquida", "Margem Líquida", CORES["laranja"]),
    ]

    for col, nome, cor in margens:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                name=nome,
                x=labels,
                y=df[col].tolist(),
                mode="lines+markers",
                line=dict(color=cor, width=2),
                marker=dict(size=6),
            ))

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=16)),
        height=350,
        margin=dict(t=50, b=30, l=50, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(tickformat=".0%", gridcolor="#eee"),
        plot_bgcolor="white",
    )
    return fig


def grafico_divida_alavancagem(df, titulo="Dívida Líquida vs Alavancagem"):
    """Gráfico combo: barras (dívida líquida) + linha (DL/EBITDA)."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    labels = df["label"].tolist()

    # Barras - Dívida Líquida
    fig.add_trace(
        go.Bar(
            name="Dívida Líquida",
            x=labels,
            y=df["divida_liquida"].tolist(),
            marker_color=[
                CORES["vermelho"] if v > 0 else CORES["verde"]
                for v in df["divida_liquida"].fillna(0)
            ],
            opacity=0.7,
        ),
        secondary_y=False,
    )

    # Linha - DL/EBITDA
    fig.add_trace(
        go.Scatter(
            name="Dív.Líq/EBITDA (LTM)",
            x=labels,
            y=df["divida_liq_ebitda"].tolist(),
            mode="lines+markers",
            line=dict(color=CORES["roxo"], width=3),
            marker=dict(size=8),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=16)),
        height=400,
        margin=dict(t=50, b=30, l=50, r=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="white",
    )
    fig.update_yaxes(title_text="R$", gridcolor="#eee", secondary_y=False)
    fig.update_yaxes(title_text="x EBITDA", gridcolor="#eee", secondary_y=True)
    return fig


def _label_vencimento(k: str) -> str:
    """Converte chave de vencimento em label legível."""
    faixas = {
        "ate_1_ano": "< 1 ano", "1_a_2_anos": "1-2 anos",
        "2_a_5_anos": "2-5 anos", "3_a_5_anos": "3-5 anos",
        "acima_5_anos": "> 5 anos",
    }
    if k == "longo_prazo":
        return "Longo Prazo"
    return faixas.get(k, k)


def _fmt_valor_barra(v: float) -> str:
    """Formata valor para exibir em cima da barra. Ex: 'R$1.706mi'."""
    return f"R${v/1e6:,.0f}mi"


def _label_periodo(cronograma: dict) -> str:
    """Ex: '3T24' a partir de data_referencia '2024-09-30'."""
    dr = cronograma.get("data_referencia", "")
    if not dr:
        return cronograma.get("arquivo", "?")
    partes = dr.split("-")
    if len(partes) == 3:
        ano = partes[0][2:]  # '24'
        mes = int(partes[1])
        tri = (mes - 1) // 3 + 1
        return f"{tri}T{ano}"
    return dr


def grafico_cronograma_comparativo(cronogramas: list[dict], empresa: str):
    """
    Gráfico comparativo de cronogramas empilhados verticalmente.

    Cada subplot: Caixa (barra azul) + Vencimentos por ano (barras vermelhas).
    Valores convertidos para milhões (R$ mi).
    """
    recentes = sorted(
        cronogramas,
        key=lambda c: c.get("data_referencia", ""),
        reverse=True,
    )[:3]

    n = len(recentes)
    if n == 0:
        return None

    subtitulos = []
    for i, c in enumerate(recentes):
        label = _label_periodo(c)
        if i == 0:
            subtitulos.append(f"Posição em {label} (Mais Recente)")
        else:
            subtitulos.append(f"Posição em {label}")

    fig = make_subplots(
        rows=n, cols=1,
        subplot_titles=subtitulos,
        vertical_spacing=0.12,
        shared_xaxes=False,
    )

    cor_caixa = "#5b9bd5"
    cor_vencimento = "#c0504d"

    for row_idx, cronograma in enumerate(recentes, start=1):
        vencimentos = cronograma.get("vencimentos", {})
        caixa = cronograma.get("caixa") or 0

        # Ordenar: anos primeiro, longo prazo por último
        chaves_ordenadas = []
        chave_lp = None
        for k in sorted(vencimentos.keys()):
            if k in ("longo_prazo", "acima_5_anos"):
                chave_lp = k
            else:
                chaves_ordenadas.append(k)
        if chave_lp:
            chaves_ordenadas.append(chave_lp)

        # Labels e valores em MILHÕES
        labels = ["Caixa"] + [_label_vencimento(k) for k in chaves_ordenadas]
        valores_mi = [caixa / 1e6] + [vencimentos[k] / 1e6 for k in chaves_ordenadas]
        cores = [cor_caixa] + [cor_vencimento] * len(chaves_ordenadas)

        fig.add_trace(
            go.Bar(
                x=labels,
                y=valores_mi,
                marker_color=cores,
                text=[f"R${v:,.0f}mi" for v in valores_mi],
                textposition="outside",
                textfont=dict(size=11),
                showlegend=False,
                width=0.6,
            ),
            row=row_idx, col=1,
        )

        max_val = max(valores_mi) if valores_mi else 0
        fig.update_yaxes(
            title_text="R$ Milhões",
            gridcolor="#eee",
            range=[0, max_val * 1.3],
            row=row_idx, col=1,
        )

    periodos_str = " vs ".join(_label_periodo(c) for c in recentes)
    titulo = (
        f"Cronograma de Amortização e Liquidez: {empresa}<br>"
        f"<sub>Comparativo {periodos_str}</sub>"
    )
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=18), x=0.5),
        height=400 * n,
        margin=dict(t=100, b=30, l=60, r=20),
        plot_bgcolor="white",
    )
    return fig


def grafico_fluxo_caixa(df, titulo="FCO vs Capex vs FCL"):
    """Gráfico de barras: FCO, Capex, FCL."""
    return grafico_barras_evolucao(
        df,
        colunas=["fco", "capex", "fcl"],
        nomes=["FCO", "Capex (FCI)", "FCL"],
        cores=[CORES["azul"], CORES["vermelho"], CORES["verde"]],
        titulo=titulo,
    )


# =========================================================================
# LAYOUT DO DASHBOARD
# =========================================================================
def main():
    # --- Sidebar ---
    with st.sidebar:
        st.title("Dashboard de Crédito")
        st.markdown("---")

        empresa_selecionada = st.selectbox(
            "Empresa",
            options=list(EMPRESAS.keys()),
        )
        config = EMPRESAS[empresa_selecionada]

        st.markdown(f"**Ticker:** {config['ticker']}")
        st.markdown(f"**Setor:** {config['setor']}")

        st.markdown("---")

        visao = st.radio(
            "Visão",
            ["Trimestral", "Anual"],
            index=0,
        )

        n_periodos = st.slider(
            "Períodos a exibir",
            min_value=4,
            max_value=20,
            value=12,
        )

        st.markdown("---")
        st.caption("Fonte: CVM (Dados Abertos) + Sites de RI")

    # --- Carregar dados ---
    caminho_json = os.path.join(config["pasta"], "Dados_CVM", "contas_chave.json")

    if not os.path.exists(caminho_json):
        st.error(f"Dados não encontrados: {caminho_json}")
        st.info("Execute a coleta primeiro: `python main.py --empresa \"CSN Mineração\"`")
        return

    df = calcular_indicadores(caminho_json)

    # Filtrar por visão
    if visao == "Anual":
        df = df[df["trimestre"] == 4].copy()
        # Para anual, os valores já estão no DFP/Q4 acumulado
        # Recalcular LTM não é necessário (já é anual)

    # Limitar períodos
    df = df.tail(n_periodos)

    # --- Header ---
    st.markdown(f"# {empresa_selecionada} ({config['ticker']})")

    # KPIs no topo
    ultimo = df.iloc[-1] if not df.empty else pd.Series()
    penultimo = df.iloc[-2] if len(df) > 1 else pd.Series()

    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    with col1:
        st.metric(
            "Receita Líquida",
            fmt_bilhoes(ultimo.get("receita_liquida")),
            fmt_pct(ultimo.get("receita_yoy")) if not pd.isna(ultimo.get("receita_yoy")) else None,
        )
    with col2:
        st.metric(
            "EBITDA",
            fmt_bilhoes(ultimo.get("ebitda")),
            fmt_pct(ultimo.get("margem_ebitda")) if not pd.isna(ultimo.get("margem_ebitda")) else None,
        )
    with col3:
        st.metric("Lucro Líquido", fmt_bilhoes(ultimo.get("lucro_liquido")))
    with col4:
        st.metric("Dívida Líquida", fmt_bilhoes(ultimo.get("divida_liquida")))
    with col5:
        st.metric("Dív.Líq/EBITDA", fmt_multiplo(ultimo.get("divida_liq_ebitda")))
    with col6:
        st.metric("Liquidez Corrente", fmt_multiplo(ultimo.get("liquidez_corrente")))
    with col7:
        nota_fl = ultimo.get("fleuriet_nota")
        tipo_fl = ultimo.get("fleuriet_tipo", "")
        st.metric("Nota Fleuriet", f"{nota_fl:.0f}/6" if not pd.isna(nota_fl) else "-")
        if tipo_fl:
            st.caption(f"**{tipo_fl}**")

    st.markdown("---")

    # =====================================================================
    # ANÁLISE QUALITATIVA + ATUALIZAÇÕES
    # =====================================================================
    tab_quant, tab_quali, tab_atualiz = st.tabs([
        "📊 Análise Quantitativa",
        "📝 Análise Qualitativa",
        "📰 Atualizações",
    ])

    # --- Caminhos dos arquivos ---
    pasta_empresa = config["pasta"]
    caminho_quali = os.path.join(pasta_empresa, "analise_qualitativa.md")
    caminho_atualiz = os.path.join(pasta_empresa, "atualizacoes.json")

    # =================================================================
    # TAB: ANÁLISE QUALITATIVA (editor Markdown tipo Notion)
    # =================================================================
    def _slug(texto: str) -> str:
        """Gera um ID de âncora a partir do texto do título."""
        import re
        slug = texto.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s]+', '-', slug)
        return slug

    def _extrair_titulos(conteudo: str) -> list[tuple[str, str, str]]:
        """Extrai títulos H1/H2 e gera (nivel, texto, slug)."""
        titulos = []
        for linha in conteudo.split("\n"):
            stripped = linha.strip()
            if stripped.startswith("## "):
                texto = stripped[3:].strip()
                titulos.append(("h2", texto, _slug(texto)))
            elif stripped.startswith("# "):
                texto = stripped[2:].strip()
                titulos.append(("h1", texto, _slug(texto)))
        return titulos

    def _injetar_ancoras(conteudo: str, titulos: list[tuple[str, str, str]]) -> str:
        """Substitui headings markdown por HTML com data-anchor para scroll via JS."""
        resultado = conteudo
        for nivel, texto, slug in titulos:
            if nivel == "h1":
                md_original = f"# {texto}"
                html_heading = f'<div data-anchor="{slug}"></div>\n\n# {texto}'
            else:
                md_original = f"## {texto}"
                html_heading = f'<div data-anchor="{slug}"></div>\n\n## {texto}'
            resultado = resultado.replace(md_original, html_heading, 1)
        return resultado

    with tab_quali:
        st.subheader("Análise Qualitativa")

        # Carregar conteúdo existente
        conteudo_quali = ""
        if os.path.exists(caminho_quali):
            with open(caminho_quali, "r", encoding="utf-8") as f:
                conteudo_quali = f.read()

        # Editor disponível para admins apenas no localhost
        is_admin = st.session_state.get("user_role") == "admin"
        if is_admin and not IS_DEPLOYED:
            modo_quali = st.radio(
                "Modo",
                ["Visualizar", "Editar"],
                horizontal=True,
                key="modo_quali",
            )
        else:
            modo_quali = "Visualizar"

        if modo_quali == "Editar":
            novo_conteudo = st.text_area(
                "Conteúdo (Markdown)",
                value=conteudo_quali,
                height=500,
                key="editor_quali",
            )
            if st.button("Salvar", key="salvar_quali"):
                os.makedirs(os.path.dirname(caminho_quali), exist_ok=True)
                with open(caminho_quali, "w", encoding="utf-8") as f:
                    f.write(novo_conteudo)
                _sync_para_deploy(caminho_quali, empresa_selecionada)
                st.success("Análise qualitativa salva e sincronizada!")
                st.rerun()
        elif conteudo_quali.strip():
            titulos = _extrair_titulos(conteudo_quali)

            # Sumário clicável via JS que busca headings no DOM pai do Streamlit
            if titulos:
                import json as _json
                titulos_js = _json.dumps([
                    {"nivel": n, "texto": t}
                    for n, t, s in titulos
                ], ensure_ascii=False)

                # Calcular altura do TOC baseado no número de títulos
                toc_height = 60 + len(titulos) * 28

                toc_component = f"""
                <style>
                    body {{ margin: 0; padding: 0; overflow: hidden; }}
                    #toc {{ background:#f8f9fa; padding:12px 20px; border-radius:8px; border-left:4px solid #1f77b4; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
                    #toc p.title {{ font-weight:bold; font-size:16px; margin:0 0 8px 0; }}
                    #toc a {{ text-decoration:none; cursor:pointer; display:block; padding:2px 0; }}
                    #toc a:hover {{ text-decoration: underline; }}
                    #toc .h1-link {{ color:#1f77b4; font-weight:bold; font-size:15px; margin:4px 0; }}
                    #toc .h2-link {{ color:#555; font-size:14px; margin:2px 0; padding-left:20px; }}
                </style>
                <div id="toc">
                    <p class="title">📑 Sumário</p>
                </div>
                <script>
                (function() {{
                    var titulos = {titulos_js};
                    var toc = document.getElementById('toc');

                    function getMainDoc() {{
                        try {{
                            var doc = window.parent.document;
                            return doc;
                        }} catch(e) {{ return null; }}
                    }}

                    function scrollToHeading(texto, tag) {{
                        var doc = getMainDoc();
                        if (!doc) return;

                        var selectors = 'h1, h2, h3, [data-testid="stMarkdown"] h1, [data-testid="stMarkdown"] h2';
                        var headings = doc.querySelectorAll(selectors);

                        for (var i = 0; i < headings.length; i++) {{
                            var hText = headings[i].textContent.trim();
                            if (hText === texto.trim()) {{
                                headings[i].scrollIntoView({{behavior: 'smooth', block: 'start'}});
                                return;
                            }}
                        }}

                        var iframes = doc.querySelectorAll('iframe');
                        for (var j = 0; j < iframes.length; j++) {{
                            try {{
                                var iDoc = iframes[j].contentDocument || iframes[j].contentWindow.document;
                                var iHeadings = iDoc.querySelectorAll('h1, h2, h3');
                                for (var k = 0; k < iHeadings.length; k++) {{
                                    if (iHeadings[k].textContent.trim() === texto.trim()) {{
                                        iframes[j].scrollIntoView({{behavior: 'smooth', block: 'start'}});
                                        return;
                                    }}
                                }}
                            }} catch(e) {{}}
                        }}
                    }}

                    titulos.forEach(function(t) {{
                        var a = document.createElement('a');
                        a.textContent = t.texto;
                        a.className = t.nivel === 'h1' ? 'h1-link' : 'h2-link';
                        a.addEventListener('click', function(e) {{
                            e.preventDefault();
                            scrollToHeading(t.texto, t.nivel === 'h1' ? 'H1' : 'H2');
                        }});
                        toc.appendChild(a);
                    }});
                }})();
                </script>
                """
                st_components.html(toc_component, height=toc_height, scrolling=False)
                st.markdown("---")

            # Renderizar conteúdo via st.markdown (suporta tabelas, negrito, etc.)
            st.markdown(conteudo_quali, unsafe_allow_html=True)
        else:
            st.info("Nenhuma análise qualitativa registrada.")

    # =================================================================
    # TAB: ATUALIZAÇÕES (log cronológico de eventos)
    # =================================================================
    with tab_atualiz:
        st.subheader("Registro de Atualizações")
        st.caption(
            "Registre eventos relevantes sobre a empresa e o setor: "
            "resultados trimestrais, mudanças regulatórias, guidance, M&A, etc."
        )

        # Carregar atualizações existentes
        atualizacoes = []
        if os.path.exists(caminho_atualiz):
            with open(caminho_atualiz, "r", encoding="utf-8") as f:
                atualizacoes = json.load(f)

        # Formulário para nova atualização (só disponível localmente)
        if not IS_DEPLOYED:
            with st.expander("➕ Adicionar nova atualização", expanded=False):
              with st.form("form_atualizacao", clear_on_submit=True):
                col_data, col_cat = st.columns([1, 1])
                with col_data:
                    data_atualiz = st.date_input("Data", value=datetime.now().date())
                with col_cat:
                    categoria = st.selectbox(
                        "Categoria",
                        ["Resultado Trimestral", "Guidance", "Setor / Mercado",
                         "Regulatório", "M&A", "Rating / Crédito", "Outro"],
                    )
                titulo_atualiz = st.text_input("Título")
                corpo_atualiz = st.text_area(
                    "Descrição (Markdown)",
                    height=150,
                    placeholder="Descreva o evento, impacto esperado, fontes...",
                )
                submitted = st.form_submit_button("Salvar atualização")
                if submitted and titulo_atualiz.strip():
                    nova = {
                        "data": str(data_atualiz),
                        "categoria": categoria,
                        "titulo": titulo_atualiz.strip(),
                        "corpo": corpo_atualiz.strip(),
                        "criado_em": datetime.now().isoformat(),
                    }
                    atualizacoes.insert(0, nova)  # Mais recente primeiro
                    os.makedirs(os.path.dirname(caminho_atualiz), exist_ok=True)
                    with open(caminho_atualiz, "w", encoding="utf-8") as f:
                        json.dump(atualizacoes, f, ensure_ascii=False, indent=2)
                    _sync_para_deploy(caminho_atualiz, empresa_selecionada)
                    st.success("Atualização registrada e sincronizada!")
                    st.rerun()

        # Exibir atualizações
        if atualizacoes:
            # Filtro por categoria
            categorias_existentes = sorted(set(a["categoria"] for a in atualizacoes))
            filtro_cat = st.multiselect(
                "Filtrar por categoria",
                categorias_existentes,
                default=categorias_existentes,
            )

            for idx, atualiz in enumerate(atualizacoes):
                if atualiz["categoria"] not in filtro_cat:
                    continue

                # Badge de categoria com cores
                cat_cores = {
                    "Resultado Trimestral": "🟦",
                    "Guidance": "🟩",
                    "Setor / Mercado": "🟧",
                    "Regulatório": "🟥",
                    "M&A": "🟪",
                    "Rating / Crédito": "🟨",
                    "Outro": "⬜",
                }
                badge = cat_cores.get(atualiz["categoria"], "⬜")

                st.markdown(
                    f"### {badge} {atualiz['titulo']}\n"
                    f"**{atualiz['data']}** · {atualiz['categoria']}"
                )
                if atualiz.get("corpo"):
                    st.markdown(atualiz["corpo"])

                # Botão de deletar (só localmente)
                if not IS_DEPLOYED:
                    if st.button("🗑️ Remover", key=f"del_atualiz_{idx}"):
                        atualizacoes.pop(idx)
                        with open(caminho_atualiz, "w", encoding="utf-8") as f:
                            json.dump(atualizacoes, f, ensure_ascii=False, indent=2)
                        _sync_para_deploy(caminho_atualiz, empresa_selecionada)
                        st.rerun()

                st.markdown("---")
        else:
            st.info("Nenhuma atualização registrada. Use o formulário acima para adicionar.")

    # =================================================================
    # TAB: ANÁLISE QUANTITATIVA (todo o conteúdo existente)
    # =================================================================
    with tab_quant:

        # =====================================================================
        # 1. DEMONSTRAÇÃO DE RESULTADOS
        # =====================================================================
        st.header("Demonstração de Resultados")

        tab_dre = formatar_tabela_dre(df)
        display_dre = tab_dre.set_index("Período").T

        # Formatar valores
        formato_rows = {
            "Receita Líquida": fmt_bilhoes,
            "CPV": fmt_bilhoes,
            "Resultado Bruto": fmt_bilhoes,
            "Despesas com Vendas": fmt_bilhoes,
            "Despesas G&A": fmt_bilhoes,
            "EBIT": fmt_bilhoes,
            "D&A": fmt_bilhoes,
            "EBITDA": fmt_bilhoes,
            "Resultado Financeiro": fmt_bilhoes,
            "Receitas Financeiras": fmt_bilhoes,
            "Despesas Financeiras": fmt_bilhoes,
            "Lucro Antes IR": fmt_bilhoes,
            "IR/CSLL": fmt_bilhoes,
            "Lucro Líquido": fmt_bilhoes,
            "Growth YoY": fmt_pct,
            "EBITDA YoY": fmt_pct,
            "Margem Bruta": fmt_pct,
            "Margem EBIT": fmt_pct,
            "Margem EBITDA": fmt_pct,
            "Margem Líquida": fmt_pct,
        }

        for row_name, fmt_fn in formato_rows.items():
            if row_name in display_dre.index:
                display_dre.loc[row_name] = display_dre.loc[row_name].apply(fmt_fn)

        # Ocultar linhas intermediárias (mantidas nos cálculos)
        ocultar_dre = [
            "CPV", "Resultado Bruto", "Despesas com Vendas", "Despesas G&A",
            "D&A", "Lucro Antes IR", "IR/CSLL",
        ]
        display_dre = display_dre.drop(
            [r for r in ocultar_dre if r in display_dre.index], axis=0
        )

        st.dataframe(display_dre, use_container_width=True, height=500)

        # Gráficos DRE
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig_receita = grafico_barras_evolucao(
                df,
                ["receita_liquida", "ebitda", "lucro_liquido"],
                ["Receita", "EBITDA", "Lucro Líquido"],
                [CORES["azul"], CORES["verde"], CORES["laranja"]],
                "Receita, EBITDA e Lucro Líquido",
            )
            st.plotly_chart(fig_receita, use_container_width=True)

        with col_g2:
            fig_margens = grafico_margens(df)
            st.plotly_chart(fig_margens, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 2. FLUXO DE CAIXA
        # =====================================================================
        st.header("Fluxo de Caixa")

        tab_fc = formatar_tabela_fluxo_caixa(df)
        display_fc = tab_fc.set_index("Período").T

        formato_fc = {
            "FCO": fmt_bilhoes,
            "FCO/EBITDA": fmt_pct,
            "FCO/Receita": fmt_pct,
            "Capex": fmt_bilhoes,
            "Capex/Receita": fmt_pct,
            "FCL": fmt_bilhoes,
            "FCL/Receita": fmt_pct,
            "Juros Pagos": fmt_bilhoes,
            "Amortiz. Dívida": fmt_bilhoes,
            "Captação": fmt_bilhoes,
            "Dividendos Pagos": fmt_bilhoes,
            "FC Financiamento": fmt_bilhoes,
        }
        for row_name, fmt_fn in formato_fc.items():
            if row_name in display_fc.index:
                display_fc.loc[row_name] = display_fc.loc[row_name].apply(fmt_fn)

        st.dataframe(display_fc, use_container_width=True, height=420)

        col_fc1, col_fc2 = st.columns(2)
        with col_fc1:
            fig_fc = grafico_fluxo_caixa(df)
            st.plotly_chart(fig_fc, use_container_width=True)

        with col_fc2:
            fig_fc_pct = grafico_linhas_multiplos(
                df,
                ["fco_receita", "capex_receita", "fcl_receita"],
                ["FCO/Receita", "Capex/Receita", "FCL/Receita"],
                [CORES["azul"], CORES["vermelho"], CORES["verde"]],
                "FCO, Capex e FCL como % da Receita",
            )
            fig_fc_pct.update_layout(yaxis=dict(tickformat=".0%"))
            st.plotly_chart(fig_fc_pct, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 3. ESTRUTURA DE CAPITAL
        # =====================================================================
        st.header("Estrutura de Capital")

        tab_ec = formatar_tabela_estrutura_capital(df)
        display_ec = tab_ec.set_index("Período").T

        formato_ec = {
            "Caixa": fmt_bilhoes,
            "Aplicações Fin. CP": fmt_bilhoes,
            "Liquidez Total": fmt_bilhoes,
            "Dívida CP": fmt_bilhoes,
            "Dívida LP": fmt_bilhoes,
            "Dívida Bruta": fmt_bilhoes,
            "Dívida Líquida": fmt_bilhoes,
            "Patrimônio Líquido": fmt_bilhoes,
            "Dív.Líq/EBITDA": fmt_multiplo,
            "Dív.Líq/FCO": fmt_multiplo,
        }
        for row_name, fmt_fn in formato_ec.items():
            if row_name in display_ec.index:
                display_ec.loc[row_name] = display_ec.loc[row_name].apply(fmt_fn)

        st.dataframe(display_ec, use_container_width=True, height=340)

        fig_divida = grafico_divida_alavancagem(df)
        st.plotly_chart(fig_divida, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 4. CAPITAL DE GIRO
        # =====================================================================
        st.header("Capital de Giro")

        tab_cg = formatar_tabela_capital_giro(df)
        display_cg = tab_cg.set_index("Período").T

        formato_cg = {
            "Contas a Receber": fmt_bilhoes,
            "Estoques": fmt_bilhoes,
            "Fornecedores": fmt_bilhoes,
            "Capital de Giro": fmt_bilhoes,
            "DSO (dias)": lambda v: f"{v:.0f}" if not pd.isna(v) else "-",
            "DIO (dias)": lambda v: f"{v:.0f}" if not pd.isna(v) else "-",
            "DPO (dias)": lambda v: f"{v:.0f}" if not pd.isna(v) else "-",
            "Ciclo de Caixa (dias)": lambda v: f"{v:.0f}" if not pd.isna(v) else "-",
        }
        for row_name, fmt_fn in formato_cg.items():
            if row_name in display_cg.index:
                display_cg.loc[row_name] = display_cg.loc[row_name].apply(fmt_fn)

        st.dataframe(display_cg, use_container_width=True, height=340)

        col_cg1, col_cg2 = st.columns(2)
        with col_cg1:
            fig_cg = grafico_barras_evolucao(
                df,
                ["contas_a_receber", "estoques", "fornecedores"],
                ["Contas a Receber", "Estoques", "Fornecedores"],
                [CORES["azul"], CORES["laranja"], CORES["vermelho"]],
                "Componentes do Capital de Giro",
            )
            st.plotly_chart(fig_cg, use_container_width=True)

        with col_cg2:
            if "ciclo_caixa" in df.columns:
                fig_ciclo = grafico_linhas_multiplos(
                    df,
                    ["dso", "dio", "dpo", "ciclo_caixa"],
                    ["DSO", "DIO", "DPO", "Ciclo de Caixa"],
                    [CORES["azul"], CORES["laranja"], CORES["vermelho"], CORES["roxo"]],
                    "Ciclo de Conversão de Caixa (dias)",
                )
                fig_ciclo.update_layout(yaxis=dict(tickformat=".0f"))
                st.plotly_chart(fig_ciclo, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 5. MÚLTIPLOS DE ALAVANCAGEM E LIQUIDEZ
        # =====================================================================
        st.header("Múltiplos de Alavancagem e Liquidez")

        tab_mult = formatar_tabela_multiplos(df)
        display_mult = tab_mult.set_index("Período").T

        formato_mult = {
            "Dív.Líq/EBITDA": fmt_multiplo,
            "Dív.Líq/FCO": fmt_multiplo,
            "EBITDA/Desp.Fin (LTM)": fmt_multiplo,
            "EBIT/Desp.Fin (LTM)": fmt_multiplo,
            "DSCR": fmt_multiplo,
            "Equity Multiplier": fmt_multiplo,
            "Debt-to-Assets": fmt_pct,
            "Dív.CP / Dív.Total": fmt_pct,
            "Liquidez Corrente": fmt_multiplo,
            "Liquidez Seca": fmt_multiplo,
            "Cash Ratio": fmt_multiplo,
            "Solvência Geral": fmt_multiplo,
            "Dív.Total / PL": fmt_multiplo,
            "Custo da Dívida": fmt_pct,
            "Capex/EBITDA (LTM)": fmt_pct,
            "Payout (LTM)": fmt_pct,
        }
        for row_name, fmt_fn in formato_mult.items():
            if row_name in display_mult.index:
                display_mult.loc[row_name] = display_mult.loc[row_name].apply(fmt_fn)

        st.dataframe(display_mult, use_container_width=True, height=500)

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            fig_liq = grafico_linhas_multiplos(
                df,
                ["liquidez_corrente", "liquidez_seca", "cash_ratio"],
                ["Liquidez Corrente", "Liquidez Seca", "Cash Ratio"],
                [CORES["azul"], CORES["laranja"], CORES["verde"]],
                "Liquidez",
            )
            st.plotly_chart(fig_liq, use_container_width=True)

        with col_m2:
            fig_alav = grafico_linhas_multiplos(
                df,
                ["divida_liq_ebitda", "divida_total_pl", "interest_coverage_ebitda"],
                ["Dív.Líq/EBITDA", "Dív.Total/PL", "EBITDA/Desp.Fin"],
                [CORES["roxo"], CORES["vermelho"], CORES["azul"]],
                "Alavancagem e Cobertura de Juros",
            )
            st.plotly_chart(fig_alav, use_container_width=True)

        col_m3, col_m4 = st.columns(2)
        with col_m3:
            fig_solv = grafico_linhas_multiplos(
                df,
                ["solvencia"],
                ["Solvência Geral (Ativo Total / Passivo Total)"],
                [CORES["azul"]],
                "Evolução da Solvência",
            )
            st.plotly_chart(fig_solv, use_container_width=True)

        with col_m4:
            fig_custo = grafico_linhas_multiplos(
                df,
                ["custo_divida"],
                ["Custo da Dívida (|Desp.Fin| LTM / Dív.Bruta)"],
                [CORES["vermelho"]],
                "Evolução do Custo da Dívida",
            )
            fig_custo.update_layout(yaxis=dict(tickformat=".1%"))
            st.plotly_chart(fig_custo, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 5b. MODELO FLEURIET (Análise Dinâmica de Capital de Giro)
        # =====================================================================
        st.header("Modelo Fleuriet — Análise Dinâmica")

        # Tabela Fleuriet
        tab_fleuriet = formatar_tabela_fleuriet(df)
        display_fl = tab_fleuriet.set_index("Período").T

        formato_fl = {
            "CDG (Capital de Giro)": fmt_bilhoes,
            "NCG (Nec. Capital de Giro)": fmt_bilhoes,
            "Saldo de Tesouraria (T)": fmt_bilhoes,
            "CDG / NCG": fmt_multiplo,
            "T / Receita": fmt_pct,
            "Nota Fleuriet": lambda v: f"{v:.0f}/6" if not pd.isna(v) else "-",
        }
        for row_name, fmt_fn in formato_fl.items():
            if row_name in display_fl.index:
                display_fl.loc[row_name] = display_fl.loc[row_name].apply(fmt_fn)

        st.dataframe(display_fl, use_container_width=True, height=320)

        # Gráficos Fleuriet
        col_fl_g1, col_fl_g2 = st.columns(2)
        with col_fl_g1:
            fig_fleuriet = grafico_barras_evolucao(
                df,
                ["fleuriet_cdg", "fleuriet_ncg", "fleuriet_t"],
                ["CDG", "NCG", "Saldo de Tesouraria (T)"],
                [CORES["azul"], CORES["laranja"], CORES["verde"]],
                "CDG, NCG e Saldo de Tesouraria",
            )
            st.plotly_chart(fig_fleuriet, use_container_width=True)

        with col_fl_g2:
            # Gráfico de evolução da Nota Fleuriet
            fig_nota = go.Figure()
            labels = df["label"].tolist()
            notas = df["fleuriet_nota"].tolist()
            tipos = df["fleuriet_tipo"].tolist() if "fleuriet_tipo" in df.columns else [""] * len(labels)

            # Cores por nota
            cores_nota = []
            for n in notas:
                if pd.isna(n):
                    cores_nota.append(CORES["cinza"])
                elif n >= 5:
                    cores_nota.append(CORES["verde"])
                elif n >= 4:
                    cores_nota.append(CORES["azul"])
                elif n >= 3:
                    cores_nota.append(CORES["laranja"])
                else:
                    cores_nota.append(CORES["vermelho"])

            fig_nota.add_trace(go.Bar(
                x=labels,
                y=notas,
                marker_color=cores_nota,
                text=[f"{n:.0f} - {t}" if not pd.isna(n) else "" for n, t in zip(notas, tipos)],
                textposition="outside",
                textfont=dict(size=9),
            ))
            fig_nota.update_layout(
                title=dict(text="Evolução da Nota Fleuriet (1-6)", font=dict(size=16)),
                height=400,
                margin=dict(t=50, b=30, l=50, r=20),
                yaxis=dict(range=[0, 7], dtick=1, gridcolor="#eee"),
                plot_bgcolor="white",
                showlegend=False,
            )
            # Faixas de referência
            fig_nota.add_hrect(y0=4.5, y1=6.5, fillcolor="green", opacity=0.05, line_width=0)
            fig_nota.add_hrect(y0=3.5, y1=4.5, fillcolor="blue", opacity=0.05, line_width=0)
            fig_nota.add_hrect(y0=2.5, y1=3.5, fillcolor="orange", opacity=0.05, line_width=0)
            fig_nota.add_hrect(y0=0, y1=2.5, fillcolor="red", opacity=0.05, line_width=0)
            st.plotly_chart(fig_nota, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 6. CRONOGRAMA DE AMORTIZAÇÃO E LIQUIDEZ (dados do PDF)
        # =====================================================================
        st.header("Cronograma de Amortização e Liquidez")

        pasta_itr = os.path.join(config["pasta"], "ITR_DFP")
        if not os.path.isdir(pasta_itr):
            pasta_itr = config["pasta"]

        # Carregar de JSON pré-extraído (rápido); botão para re-extrair
        caminho_cronogramas = os.path.join(config["pasta"], "Dados_CVM", "cronogramas.json")

        cronogramas = []
        if os.path.exists(caminho_cronogramas):
            with open(caminho_cronogramas, "r", encoding="utf-8") as f:
                cronogramas = json.load(f)

        # Botão de extração automática (local) + input manual (admin)
        is_admin_cron = st.session_state.get("user_role") == "admin"

        if not IS_DEPLOYED:
            col_btn1, col_btn2 = st.columns([1, 5])
            with col_btn1:
                re_extrair = st.button("Extrair/Atualizar cronogramas dos PDFs")

            if re_extrair:
                with st.spinner("Extraindo cronogramas dos PDFs... (pode levar alguns minutos)"):
                    from src.coleta.pdf_parser import extrair_cronogramas_pasta, salvar_cronogramas
                    cronogramas = extrair_cronogramas_pasta(pasta_itr)
                    if cronogramas:
                        salvar_cronogramas(cronogramas, caminho_cronogramas)
                        _sync_para_deploy(caminho_cronogramas, empresa_selecionada)
                        st.success(f"{len(cronogramas)} cronogramas extraídos e sincronizados.")
                    else:
                        st.warning("Nenhum cronograma extraído.")

        # Input manual de cronograma (admin, apenas localhost)
        if is_admin_cron and not IS_DEPLOYED:
            with st.expander("Inserir/Editar cronograma manualmente", expanded=False):
                st.caption(
                    "Use quando o cronograma não pode ser extraído automaticamente dos PDFs "
                    "(ex: dados em formato de imagem). Valores em **R$ milhões**."
                )
                col_ref, col_caixa = st.columns(2)
                with col_ref:
                    data_ref_input = st.text_input(
                        "Data de referência (AAAA-MM-DD)",
                        value="2025-12-31",
                        key="cron_data_ref",
                    )
                with col_caixa:
                    caixa_input = st.number_input(
                        "Caixa (R$ mi)", value=0.0, step=100.0, key="cron_caixa"
                    )

                st.markdown("**Vencimentos por ano** (preencha os anos relevantes):")
                ano_base = int(data_ref_input[:4]) + 1 if len(data_ref_input) >= 4 else 2026
                cols_anos = st.columns(5)
                venc_inputs = {}
                for j in range(10):
                    ano = ano_base + j
                    with cols_anos[j % 5]:
                        val = st.number_input(
                            f"{ano}", value=0.0, step=100.0,
                            key=f"cron_{ano}", min_value=0.0,
                        )
                        if val > 0:
                            venc_inputs[str(ano)] = val

                arquivo_input = st.text_input(
                    "Fonte (ex: Release_4T25.pdf pag.27)",
                    value="Input manual",
                    key="cron_arquivo",
                )

                if st.button("Salvar cronograma", key="btn_salvar_cron"):
                    if venc_inputs:
                        novo = {
                            "data_referencia": data_ref_input,
                            "caixa": caixa_input * 1_000_000,
                            "vencimentos": {k: v * 1_000_000 for k, v in venc_inputs.items()},
                            "divida_total": sum(v * 1_000_000 for v in venc_inputs.values()),
                            "arquivo": arquivo_input,
                        }
                        # Substituir se já existe para mesma data, senão adicionar
                        cronogramas = [c for c in cronogramas if c.get("data_referencia") != data_ref_input]
                        cronogramas.append(novo)
                        os.makedirs(os.path.dirname(caminho_cronogramas), exist_ok=True)
                        with open(caminho_cronogramas, "w", encoding="utf-8") as f:
                            json.dump(cronogramas, f, ensure_ascii=False, indent=2, default=str)
                        _sync_para_deploy(caminho_cronogramas, empresa_selecionada)
                        st.success(f"Cronograma {data_ref_input} salvo e sincronizado!")
                        st.rerun()
                    else:
                        st.warning("Preencha ao menos um ano de vencimento.")

        if cronogramas:
            recentes = sorted(cronogramas, key=lambda c: c.get("data_referencia", ""), reverse=True)[:3]

            # Sobrescrever caixa do PDF com o valor da API CVM (mais confiável)
            for cronograma in recentes:
                dr = cronograma.get("data_referencia", "")
                if dr and "caixa" in df.columns:
                    match = df[df.index == pd.Timestamp(dr)]
                    if not match.empty and not pd.isna(match["caixa"].iloc[0]):
                        cronograma["caixa"] = match["caixa"].iloc[0]

            cor_caixa = "#5b9bd5"
            cor_vencimento = "#c0504d"
            N_ANOS = 5  # próximos 5 anos

            for idx, cronograma in enumerate(recentes):
                label = _label_periodo(cronograma)
                sufixo = " (Mais Recente)" if idx == 0 else ""
                vencimentos = cronograma.get("vencimentos", {})
                caixa = cronograma.get("caixa") or 0

                # Determinar ano de referência (ano seguinte ao da data do relatório)
                dr = cronograma.get("data_referencia", "")
                if dr:
                    ano_ref = int(dr.split("-")[0])
                else:
                    ano_ref = 2025
                primeiro_ano = ano_ref + 1  # ex: 4T25 -> olhar a partir de 2026

                # Separar anos numéricos vs faixas
                anos_numericos = {}
                valor_lp = 0
                tem_faixas = False
                for k, v in vencimentos.items():
                    if k in ("longo_prazo", "acima_5_anos"):
                        valor_lp += v
                    elif k.startswith("ate_") or k.endswith("_anos"):
                        tem_faixas = True
                    else:
                        try:
                            ano = int(k)
                            if ano >= primeiro_ano:
                                anos_numericos[ano] = v
                            # Anos passados: ignorar (dívida já venceu)
                        except ValueError:
                            pass

                if tem_faixas:
                    # Formato faixas: usar como está (não tem anos específicos)
                    chaves_faixa = []
                    for k in ["ate_1_ano", "1_a_2_anos", "2_a_5_anos", "3_a_5_anos", "acima_5_anos"]:
                        if k in vencimentos:
                            chaves_faixa.append(k)

                    bar_labels = ["Caixa"] + [_label_vencimento(k) for k in chaves_faixa]
                    bar_valores = [caixa / 1e6] + [vencimentos[k] / 1e6 for k in chaves_faixa]
                else:
                    # Formato por ano: pegar próximos N_ANOS, acumular resto como "XXXX+"
                    anos_futuros = sorted(anos_numericos.keys())

                    # Próximos N_ANOS-1 individualmente + último ano acumula tudo restante
                    anos_individuais = anos_futuros[:N_ANOS - 1]
                    anos_acumulados = anos_futuros[N_ANOS - 1:]

                    bar_labels = ["Caixa"]
                    bar_valores = [caixa / 1e6]

                    for ano in anos_individuais:
                        bar_labels.append(str(ano))
                        bar_valores.append(anos_numericos[ano] / 1e6)

                    # Última barra: acumula anos restantes + longo_prazo
                    if anos_acumulados or valor_lp > 0:
                        acum = sum(anos_numericos[a] for a in anos_acumulados) + valor_lp
                        ultimo_ano_ind = anos_acumulados[0] if anos_acumulados else (anos_individuais[-1] + 1 if anos_individuais else primeiro_ano)
                        bar_labels.append(f"{ultimo_ano_ind}+")
                        bar_valores.append(acum / 1e6)

                cores = [cor_caixa] + [cor_vencimento] * (len(bar_labels) - 1)

                # Formatar texto: usar "bi" se > 1000 mi
                textos = []
                for v in bar_valores:
                    if v >= 1000:
                        textos.append(f"R${v/1000:.1f}bi")
                    else:
                        textos.append(f"R${v:,.0f}mi")

                fig = go.Figure(go.Bar(
                    x=bar_labels,
                    y=bar_valores,
                    marker_color=cores,
                    text=textos,
                    textposition="outside",
                    textfont=dict(size=12),
                    width=0.6,
                ))

                max_val = max(bar_valores) if bar_valores else 0
                fig.update_layout(
                    title=dict(text=f"Posição em {label}{sufixo}", font=dict(size=15)),
                    height=350,
                    margin=dict(t=50, b=30, l=60, r=20),
                    plot_bgcolor="white",
                    xaxis=dict(type="category"),
                    yaxis=dict(title="R$ Milhões", gridcolor="#eee", range=[0, max_val * 1.3]),
                    showlegend=False,
                )

                st.plotly_chart(fig, use_container_width=True, key=f"amort_{idx}")

        else:
            st.info(
                "Nenhum cronograma disponível. Clique em **Extrair/Atualizar cronogramas dos PDFs** "
                "para processar os ITRs/DFPs."
            )

        st.markdown("---")

        # =====================================================================
        # 6. METODOLOGIA E GLOSSÁRIO
        # =====================================================================
        with st.expander("Metodologia e Glossário de Indicadores", expanded=False):

            st.markdown("""
### Como ler este dashboard

Este dashboard mostra a saúde financeira de uma empresa sob a ótica de **crédito** —
ou seja, se a empresa tem capacidade de pagar suas dívidas. Os dados vêm da CVM
(demonstrações financeiras oficiais) e dos sites de Relações com Investidores.

Todos os valores são **trimestrais** (isolados, não acumulados) salvo quando indicado "LTM"
(Last Twelve Months = soma dos últimos 4 trimestres).

---

### 1. Demonstração de Resultados (DRE)

A DRE mostra quanto a empresa **faturou**, quanto **gastou** e quanto **sobrou** em um período.

| Indicador | O que é | Por que importa |
|---|---|---|
| **Receita Líquida** | Tudo que a empresa vendeu no trimestre, já descontados impostos sobre vendas. | É o ponto de partida — se a receita cai, todo o resto tende a piorar. |
| **Resultado Bruto** | Receita menos o custo direto de produção (matéria-prima, mão de obra da fábrica). | Mostra se o negócio principal é rentável antes de despesas administrativas. |
| **EBIT** | Lucro operacional — o que sobra depois de pagar todos os custos e despesas do dia a dia, mas **antes** de juros e impostos. | Mede a eficiência operacional pura, sem influência da estrutura de capital. |
| **EBITDA** | EBIT + depreciação e amortização. É o lucro operacional "caixa" — ignora gastos contábeis que não saem do caixa. | Principal métrica usada por credores para medir capacidade de pagamento. |
| **Resultado Financeiro** | Receitas financeiras (rendimento de aplicações) menos despesas financeiras (juros de dívida). Se negativo, a empresa paga mais juros do que ganha. | Mostra o peso da dívida no resultado. |
| **Lucro Líquido** | O que sobra no final, depois de tudo: custos, despesas, juros, impostos. | É o resultado final para o acionista. |

**Margens** — são os indicadores acima divididos pela receita, em percentual:

| Margem | Fórmula | Interpretação |
|---|---|---|
| **Margem Bruta** | Resultado Bruto / Receita | "De cada R$100 vendidos, quanto sobra após o custo de produção?" |
| **Margem EBITDA** | EBITDA / Receita | "De cada R$100 vendidos, quanto sobra de caixa operacional?" Quanto maior, mais folga para pagar dívidas. |
| **Margem Líquida** | Lucro Líquido / Receita | "De cada R$100 vendidos, quanto sobra de lucro final?" |

**Growth YoY** — variação em relação ao mesmo trimestre do ano anterior (ex: 3T25 vs 3T24).
Mostra se a empresa está crescendo ou encolhendo.

#### Gráfico: Receita, EBITDA e Lucro Líquido (barras)

**O que mostra:** Três barras lado a lado para cada trimestre — a Receita (azul), o EBITDA (verde) e o Lucro Líquido (laranja).

**Como ler:** A Receita é sempre a barra maior. O EBITDA mostra quanto dessa receita virou caixa operacional. O Lucro Líquido é o que sobrou de fato. Compare a altura das barras ao longo do tempo: se a Receita cresce mas o EBITDA e o Lucro encolhem, significa que os custos estão subindo mais rápido que as vendas — sinal de alerta.

**Por que observar:** Este gráfico responde à pergunta mais básica: "A empresa está vendendo mais e lucrando mais com o passar do tempo?" Se as três barras crescem juntas, o negócio está saudável. Se o Lucro Líquido fica negativo (abaixo de zero), a empresa está dando prejuízo.

#### Gráfico: Evolução das Margens (linhas)

**O que mostra:** Três linhas — Margem Bruta, Margem EBITDA e Margem Líquida — em percentual, ao longo do tempo.

**Como ler:** As linhas mostram "de cada R$100 que a empresa faturou, quanto sobrou em cada etapa". A Margem Bruta é sempre a mais alta (só desconta custos de produção). A Margem Líquida é a mais baixa (desconta tudo). Observe a tendência: linhas subindo = empresa ficando mais eficiente; linhas caindo = custos corroendo o resultado.

**Por que observar:** Margens estáveis ou crescentes indicam poder de precificação e controle de custos. Margens caindo podem indicar competição acirrada, perda de eficiência ou aumento de juros. Para análise de crédito, a Margem EBITDA é a mais importante — é ela que determina quanta geração de caixa a empresa tem para pagar dívidas.

---

### 2. Fluxo de Caixa

A DRE é "contábil" — inclui receitas e custos que ainda não viraram dinheiro.
O fluxo de caixa mostra o **dinheiro real** que entrou e saiu.

| Indicador | O que é | Por que importa |
|---|---|---|
| **FCO (Fluxo de Caixa Operacional)** | Dinheiro gerado pelas operações do dia a dia. | Se o FCO é positivo e consistente, a empresa se sustenta sozinha. |
| **Capex (FCI)** | Investimentos em ativos (máquinas, minas, fábricas). Normalmente negativo. | Empresas precisam investir para manter e crescer. Capex alto pode ser bom (crescimento) ou preocupante (manutenção cara). |
| **FCL (Fluxo de Caixa Livre)** | FCO + Capex. É o dinheiro que sobra depois de operar e investir. | Se positivo, a empresa gera caixa para pagar dívidas, dividendos ou acumular reservas. Se negativo, precisa de financiamento externo. |
| **FC Financiamento** | Entradas e saídas de empréstimos, emissão de ações, pagamento de dividendos. | Mostra se a empresa está captando ou pagando dívida. |
| **FCO / EBITDA** | Razão entre caixa gerado e EBITDA. | Se próximo de 100%, o EBITDA está "virando caixa" de verdade. Se muito abaixo, pode indicar problemas de capital de giro. |

#### Gráfico: FCO vs Capex vs FCL (barras)

**O que mostra:** Três barras para cada trimestre — FCO (azul), Capex (vermelho, normalmente negativo) e FCL (verde).

**Como ler:** O FCO (azul) mostra quanto dinheiro entrou das operações. O Capex (vermelho) mostra quanto a empresa gastou em investimentos — aparece para baixo porque é dinheiro saindo. O FCL (verde) é a soma dos dois: se o FCO é maior que o Capex, o FCL é positivo (barra verde para cima) — a empresa está gerando caixa de verdade.

**Por que observar:** Uma empresa pode parecer lucrativa na DRE mas estar "queimando caixa" na prática (ex: vende a prazo mas não recebe). Este gráfico mostra a realidade do caixa. Se o FCL é consistentemente positivo, a empresa pode pagar dívidas e crescer sem depender de novos empréstimos. Se o FCL é sempre negativo, a empresa precisa se endividar cada vez mais para sobreviver.

#### Gráfico: FCO, Capex e FCL como % da Receita (linhas)

**O que mostra:** As mesmas métricas do gráfico anterior, mas expressas como percentual da receita.

**Como ler:** Se a linha do FCO/Receita está em 20%, significa que a cada R$100 vendidos, R$20 viraram caixa. A linha do Capex/Receita mostra quanto da receita é reinvestido. A linha do FCL/Receita mostra o saldo final.

**Por que observar:** Esse gráfico permite comparar empresas de tamanhos diferentes e ver tendências de eficiência de caixa. Uma empresa que converte 25% da receita em FCO é mais saudável que uma que converte apenas 5%, independentemente do tamanho.

---

### 3. Estrutura de Capital (Balanço)

O balanço é uma "foto" do patrimônio da empresa em uma data específica.

| Indicador | O que é | Por que importa |
|---|---|---|
| **Caixa** | Dinheiro em conta + aplicações de liquidez imediata. | É o colchão de segurança. Quanto mais caixa, mais folga para pagar dívidas de curto prazo. |
| **Dívida CP** | Empréstimos e financiamentos que vencem em até 12 meses. | Dívida de curto prazo exige caixa disponível ou refinanciamento. |
| **Dívida LP** | Empréstimos e financiamentos que vencem após 12 meses. | Dívida de longo prazo dá mais tempo, mas aumenta o custo total de juros. |
| **Dívida Bruta** | Dívida CP + Dívida LP. | Total que a empresa deve aos bancos e mercado de capitais. |
| **Dívida Líquida** | Dívida Bruta - Caixa. Se negativa, a empresa tem mais caixa que dívida (caixa líquido). | Principal indicador de endividamento. Empresas com dívida líquida negativa são consideradas muito seguras. |
| **Patrimônio Líquido (PL)** | Ativo Total - Passivo Total. É o "valor contábil" que pertence aos acionistas. | Se o PL é pequeno em relação à dívida, a empresa está muito alavancada. |

#### Gráfico: Dívida Líquida vs Alavancagem (barras + linha)

**O que mostra:** Barras mostram a Dívida Líquida em R$ bilhões ao longo do tempo. A linha mostra o múltiplo Dívida Líquida / EBITDA (quantos anos de EBITDA a empresa precisaria para pagar toda a dívida).

**Como ler:** As barras indicam o volume absoluto de dívida (depois de descontar o caixa). A linha mostra se essa dívida é "pesada" em relação à capacidade de pagamento. Uma empresa pode ter R$10 bilhões de dívida e estar confortável (se seu EBITDA é R$5 bi = 2,0x), enquanto outra com R$2 bilhões pode estar em risco (se seu EBITDA é R$500 mi = 4,0x).

**Por que observar:** Este é o gráfico mais importante para análise de crédito. Ele responde: "A dívida está crescendo mais rápido que a capacidade de pagamento?" Se a linha (alavancagem) sobe consistentemente, a empresa está se endividando além de suas possibilidades. Se a linha desce, a empresa está desalavancando — bom sinal. Referência: abaixo de 2,5x é confortável; acima de 3,5x é preocupante.

---

### 4. Capital de Giro

#### Gráfico: Componentes do Capital de Giro (barras)

**O que mostra:** Três barras — Contas a Receber (azul), Estoques (laranja) e Fornecedores (vermelho) — para cada trimestre.

**Como ler:** Contas a Receber é dinheiro que a empresa tem a receber de clientes (já vendeu mas ainda não recebeu). Estoques é mercadoria parada no armazém. Fornecedores é dinheiro que a empresa deve a quem lhe vende matéria-prima. Pense assim: Contas a Receber + Estoques = dinheiro "preso" no negócio. Fornecedores = dinheiro que os outros estão financiando para a empresa. Se os dois primeiros crescem muito mais rápido que o terceiro, a empresa precisa de mais capital de giro.

**Por que observar:** Mostra a eficiência operacional. Uma empresa que demora para receber dos clientes e acumula muito estoque precisa de mais caixa para operar — sobra menos para pagar dívidas. Se Fornecedores cresce em relação aos outros, pode ser bom (mais prazo para pagar) ou preocupante (a empresa está atrasando pagamentos).

#### Gráfico: Ciclo de Conversão de Caixa em dias (linhas)

**O que mostra:** Quatro linhas em dias — DSO (dias para receber dos clientes), DIO (dias de estoque), DPO (dias para pagar fornecedores) e Ciclo de Caixa (DSO + DIO − DPO).

**Como ler:** O DSO indica quantos dias em média a empresa leva para receber de seus clientes. O DIO indica quantos dias a mercadoria fica parada no estoque. O DPO indica quantos dias a empresa demora para pagar seus fornecedores. O Ciclo de Caixa é a soma do DSO + DIO menos o DPO — é o número de dias que o dinheiro da empresa fica "preso" entre comprar, produzir e receber a venda.

**Por que observar:** Quanto menor o Ciclo de Caixa, melhor — significa que a empresa transforma suas operações em dinheiro mais rapidamente. Se o Ciclo de Caixa está subindo ao longo do tempo, a empresa está precisando de cada vez mais capital de giro, o que pode pressionar o caixa. Empresas com Ciclo de Caixa negativo (como varejistas que recebem à vista e pagam fornecedores a prazo) têm vantagem financeira.

---

### 5. Múltiplos de Alavancagem e Liquidez

Estes indicadores comparam dívida com a capacidade de pagamento. São os mais usados por analistas de crédito e agências de rating.

| Indicador | Fórmula | O que significa | Referência |
|---|---|---|---|
| **Dív.Líq / EBITDA** | Dívida Líquida / EBITDA (LTM) | "Quantos anos de EBITDA seriam necessários para pagar toda a dívida?" | < 2x: confortável. 2-3x: atenção. > 3x: alto risco. |
| **Dív.Líq / FCO** | Dívida Líquida / FCO (LTM) | Similar, mas usando caixa real em vez de EBITDA. | Mais conservador que Dív.Líq/EBITDA. |
| **Equity Multiplier** | Ativo Total / PL | "Quanto do ativo é financiado por terceiros?" Se = 2x, metade é dívida. | Quanto maior, mais alavancada. |
| **Debt-to-Assets** | Dívida Bruta / Ativo Total | Percentual do ativo financiado por dívida bancária. | > 50%: muito endividada. |
| **Dív.CP / Dív.Total** | Dívida CP / Dívida Bruta | Concentração de dívida no curto prazo. | > 50%: risco de refinanciamento alto. |
| **Liquidez Corrente** | Ativo Circulante / Passivo Circulante | "Para cada R$1 de obrigação de curto prazo, quanto a empresa tem de ativo de curto prazo?" | > 1x: consegue cobrir. < 1x: aperto de liquidez. |
| **Cash Ratio** | Caixa / Passivo Circulante | Versão mais conservadora: só considera caixa, não todo o ativo circulante. | > 0.5x: razoável. > 1x: muito confortável. |
| **Interest Coverage** | EBIT / Despesas Financeiras | "Quantas vezes o lucro operacional cobre os juros?" | > 3x: saudável. < 1.5x: risco de inadimplência. |
| **Dív.Total / PL** | Dívida Bruta / PL | Alavancagem em relação ao capital próprio. | > 2x: alavancagem alta. |

#### Gráfico: Liquidez (linhas)

**O que mostra:** Três linhas — Liquidez Corrente (azul), Liquidez Seca (laranja) e Cash Ratio (verde).

**Como ler:** Todas medem a mesma ideia: "A empresa consegue pagar o que deve no curto prazo?" A diferença é o quão conservador é o cálculo. A Liquidez Corrente usa todos os ativos de curto prazo (caixa + clientes + estoque). A Liquidez Seca exclui os estoques (que podem ser difíceis de vender rápido). O Cash Ratio só usa dinheiro em caixa — é o teste mais rigoroso. O valor 1,0 é a linha crítica: acima de 1,0, a empresa tem mais ativos que dívidas de curto prazo.

**Por que observar:** Se a Liquidez Corrente cai abaixo de 1,0, a empresa tem mais dívidas de curto prazo do que ativos para pagá-las — risco iminente de calote. Se mesmo o Cash Ratio está acima de 1,0, a empresa pode pagar tudo só com o dinheiro em caixa, sem depender de receber de clientes.

#### Gráfico: Alavancagem e Cobertura de Juros (linhas)

**O que mostra:** Três linhas — Dívida Líquida/EBITDA (roxo), Dívida Total/PL (vermelho) e EBITDA/Despesas Financeiras (azul).

**Como ler:** As duas primeiras linhas medem endividamento: Dív.Líq/EBITDA mostra em quantos anos de lucro operacional a empresa pagaria a dívida; Dív.Total/PL mostra quanto a empresa deve em relação ao patrimônio dos acionistas. A terceira linha (EBITDA/Desp.Fin) mede o oposto — a capacidade de pagar juros: quantas vezes o lucro operacional cobre a despesa financeira. Para as duas primeiras, menor é melhor. Para a terceira, maior é melhor.

**Por que observar:** Estas são as métricas que bancos e agências de rating usam para decidir se concedem crédito. Se Dív.Líq/EBITDA sobe acima de 3,5x, a empresa pode ter dificuldade em conseguir novos empréstimos. Se a cobertura de juros cai abaixo de 1,5x, a empresa mal consegue pagar os juros — situação crítica.

#### Gráfico: Evolução da Solvência (linha)

**O que mostra:** Uma única linha com o índice de solvência (Ativo Total / Passivo Total) ao longo do tempo.

**Como ler:** Se o valor é 2,0, significa que para cada R$1 de dívida total (de curto e longo prazo), a empresa tem R$2 em ativos. Quanto mais alto, mais solvente. O valor 1,0 é o limite: abaixo disso, a empresa deve mais do que possui.

**Por que observar:** É a medida mais ampla de saúde financeira. Diferente da liquidez (que olha só o curto prazo), a solvência olha o balanço inteiro. Uma empresa pode ter boa liquidez de curto prazo mas ser insolvente se as dívidas de longo prazo superam o valor dos ativos.

#### Gráfico: Evolução do Custo da Dívida (linha)

**O que mostra:** Uma linha mostrando o custo médio anual da dívida da empresa (Despesas Financeiras / Dívida Bruta), em percentual.

**Como ler:** Se o custo está em 12%, significa que a empresa paga, em média, 12% ao ano de juros sobre sua dívida. Compare com a taxa Selic: se o custo da dívida está muito acima da Selic, pode indicar que o mercado considera a empresa arriscada (cobra mais caro para emprestar). Se está próximo ou abaixo da Selic, a empresa tem bom rating e consegue condições favoráveis.

**Por que observar:** Mesmo que a dívida fique estável, um aumento no custo da dívida pode deteriorar os resultados. Se a empresa precisa rolar dívidas em um cenário de juros altos, o custo sobe e consome mais do lucro operacional. Esse gráfico ajuda a detectar esse risco antes que ele apareça no Lucro Líquido.

---

### 6. Cronograma de Amortização e Liquidez

| Conceito | Explicação |
|---|---|
| **Barra azul (Caixa)** | Quanto dinheiro a empresa tem disponível hoje. |
| **Barras vermelhas (anos)** | Quanto de dívida vence em cada ano. |
| **Última barra (ex: 2030+)** | Soma de toda a dívida que vence a partir daquele ano em diante. |

#### Gráfico: Cronograma de Amortização (barras horizontais)

**O que mostra:** Uma barra azul no topo representando o caixa disponível, seguida por barras vermelhas para cada ano, mostrando quanto de dívida vence naquele ano. O dashboard mostra esse gráfico para os 3 períodos mais recentes, lado a lado, permitindo ver como o perfil da dívida evoluiu.

**Como ler:** Compare a barra azul (Caixa) com as barras vermelhas dos próximos 2-3 anos. Se o Caixa é maior que a soma dos vencimentos dos próximos 2 anos, a empresa está confortável — pode pagar suas dívidas próximas mesmo sem gerar nenhum caixa novo. Se alguma barra vermelha é gigante comparada às outras, a empresa tem uma "parede de vencimentos" naquele ano e vai precisar refinanciar. Compare os 3 gráficos lado a lado: se o perfil melhora (dívida se espalha, caixa cresce), bom sinal. Se piora, risco crescente.

**Por que observar:** Este gráfico mostra o risco mais concreto de crédito: "Quando as dívidas vencem e a empresa tem caixa para pagá-las?" Uma empresa pode ter bons indicadores de alavancagem mas estar em risco se tem uma concentração grande de vencimentos em um único ano.

---

### 7. Modelo Fleuriet — Nota de Saúde Financeira

O Modelo Fleuriet é uma forma de avaliar se a empresa tem uma estrutura financeira saudável,
olhando para **como ela financia suas operações do dia a dia**. Em vez de olhar apenas se a empresa
tem mais ativos que passivos (análise estática), ele analisa a **dinâmica** do dinheiro dentro da empresa.

O modelo calcula três números e, a partir deles, dá uma **nota de 1 a 6**:

| Sigla | O que significa | Como pensar |
|:------|:----------------|:------------|
| **CDG** (Capital de Giro) | Quanto dinheiro de longo prazo (patrimônio + dívidas longas) sobra depois de pagar os ativos de longo prazo (fábricas, minas, etc.) | "Quanto a empresa tem de folga permanente para financiar o dia a dia?" |
| **NCG** (Necessidade de Capital de Giro) | Quanto a empresa precisa de dinheiro amarrado nas operações (clientes que ainda não pagaram + estoque) menos o que os fornecedores estão financiando | "Quanto de dinheiro fica 'preso' no ciclo operacional?" Se negativo, a empresa recebe antes de pagar — ótimo! |
| **T** (Saldo de Tesouraria) | CDG menos NCG. É o que sobra (ou falta) depois de financiar as operações | "A empresa tem folga de caixa ou está dependendo de empréstimos de curto prazo?" |

**As notas:**

| Nota | Classificação | O que acontece | Em linguagem simples |
|:----:|:-------------|:---------------|:---------------------|
| **6** | Excelente | CDG (+), NCG (−), T (+) | A empresa tem folga de longo prazo E recebe dos clientes antes de pagar fornecedores. Situação ideal. |
| **5** | Sólida | CDG (+), NCG (+), T (+) | A empresa precisa de capital de giro, mas sua folga de longo prazo cobre tudo com sobra. Saudável. |
| **4** | Insatisfatória | CDG (+), NCG (+), T (−) | A empresa tem folga de longo prazo, mas não é suficiente. Precisa de empréstimos de curto prazo para operar. Sinal de atenção. |
| **3** | Alto Risco | CDG (−), NCG (−), T (+) | A empresa investe mais do que tem de recursos permanentes. Só não quebra porque recebe antes de pagar. Instável. |
| **2** | Muito Ruim | CDG (−), NCG (−), T (−) | Tanto a estrutura de longo prazo quanto a tesouraria estão negativas. Vulnerável a qualquer choque. |
| **1** | Péssima | CDG (−), NCG (+), T (−) | A empresa precisa de capital de giro, não tem folga de longo prazo e depende totalmente de crédito de curto prazo. Risco de insolvência. |

#### Gráfico: CDG, NCG e Saldo de Tesouraria (barras)

**O que mostra:** Três barras lado a lado para cada trimestre — CDG (azul), NCG (laranja) e Saldo de Tesouraria (verde).

**Como ler:** O CDG (azul) mostra a folga financeira de longo prazo. O NCG (laranja) mostra quanto a empresa precisa de capital preso nas operações. O T (verde) é a diferença entre os dois. Se a barra verde está positiva (acima de zero), a empresa tem sobra de caixa. Se está negativa (abaixo de zero), ela depende de empréstimos de curto prazo para operar. Observe se a barra verde vai ficando cada vez mais negativa — isso é o **Efeito Tesoura**, um sinal grave de deterioração financeira.

**Por que observar:** Este gráfico revela problemas que não aparecem em indicadores tradicionais. Uma empresa pode ter boa alavancagem e bom EBITDA mas estar financiando operações permanentes com dívida de curto prazo — como uma pessoa que paga o aluguel com cartão de crédito todo mês. O Saldo de Tesouraria caindo é frequentemente o primeiro sinal de uma crise financeira futura.

#### Gráfico: Evolução da Nota Fleuriet (barras coloridas)

**O que mostra:** Uma barra por trimestre com a nota de 1 a 6, colorida de verde (notas 5-6, saudável), azul (nota 4, atenção), laranja (nota 3, risco) a vermelho (notas 1-2, perigo).

**Como ler:** É como um semáforo de saúde financeira. Barras verdes = empresa financeiramente saudável. Barras vermelhas = risco elevado. Observe a tendência: se as barras vão mudando de verde para laranja para vermelho ao longo dos trimestres, a empresa está se deteriorando. O texto acima de cada barra mostra a classificação (ex: "5 - Sólida").

**Por que observar:** Sintetiza toda a análise dinâmica em um único número fácil de entender. É especialmente útil para comparar a saúde financeira de uma empresa ao longo do tempo e detectar tendências de deterioração antes que os problemas se tornem evidentes nos indicadores de alavancagem.

---

### Fonte dos dados

- **Dados estruturados (DRE, Balanço, DFC):** API de Dados Abertos da CVM ([dados.cvm.gov.br](https://dados.cvm.gov.br))
- **Cronograma de amortização:** Extraído dos PDFs de ITR/DFP e Releases de Resultados via notas explicativas
- **Periodicidade:** Trimestral (ITR) e Anual (DFP)
- **Valores:** Em reais (R$), escala de milhares na CVM, convertidos para unidades
            """)


def app():
    """Entry point com autenticação."""
    # Verificar se já está autenticado (sem renderizar formulário)
    if st.session_state.get("authenticated", False):
        show_logout()
        if st.session_state.get("user_role") == "admin":
            show_admin_panel()
        main()
        return

    # Não autenticado — mostrar login e registro
    tab_login, tab_register = st.tabs(["Entrar", "Criar conta"])
    with tab_login:
        authenticated, username, role = show_login()
        if authenticated:
            st.rerun()
    with tab_register:
        show_registration_form()


if __name__ == "__main__":
    app()
