"""
Dashboard de Crédito - Script principal de coleta.

Orquestra a coleta de dados financeiros de empresas listadas na B3:
  1. Buscador RI → PDFs (Release, ITR, DFP) via API MZ
  2. API CVM → Dados estruturados (DRE, Balanço, DFC) via dados.cvm.gov.br

Uso:
    python main.py --empresa "CSN Mineração" --ano-inicio 2021

    # Apenas PDFs do RI:
    python main.py --empresa "CSN Mineração" --apenas-ri

    # Apenas dados CVM:
    python main.py --empresa "CSN Mineração" --apenas-cvm
"""

import os
import sys
import argparse
import json
from datetime import datetime

# Adicionar src ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.coleta.buscador_ri import BuscadorRI, EMPRESAS_MZ
from src.coleta.api_cvm import ColetorCVM


# ---- Configurações de empresas ----
# Cada empresa precisa de: nome, URL do RI, categorias, e pasta destino
EMPRESAS = {
    "CSN Mineração": {
        "nome_cvm": "CSN MINERAÇÃO",
        "url_ri": "https://ri.csnmineracao.com.br/informacoes-financeiras/central-de-resultados/",
        "categorias_release": ["central-release"],
        "categorias_dfp_itr": ["itr-dfp"],
        "pasta_pdfs": "G:/Meu Drive/Análise de Crédito/CSN Mineração",
    },
    "Raízen": {
        "nome_cvm": "RAÍZEN S.A.",
        "url_ri": "https://ri.raizen.com.br/informacoes-financeiras/central-de-resultados/",
        "categorias_release": ["apresentacao_resultados"],
        "categorias_dfp_itr": ["cr-grupo-raizen-itr", "cr-relatorio-resultados-grupo-raizen-dfp"],
        "pasta_pdfs": "G:/Meu Drive/Análise de Crédito/Raizen",
    },
    "Minerva Foods": {
        "nome_cvm": "MINERVA S/A",
        "url_ri": "https://ri.minervafoods.com/central-de-downloads-2/",
        "categorias_release": ["central_de_downloads_central_de_downloads"],
        "categorias_dfp_itr": ["central_de_downloads_central_de_downloads"],
        "pasta_pdfs": "G:/Meu Drive/Análise de Crédito/Minerva",
    },
    "Equatorial": {
        "nome_cvm": "EQUATORIAL S.A.",
        "url_ri": "",
        "categorias_release": [],
        "categorias_dfp_itr": [],
        "pasta_pdfs": "G:/Meu Drive/Análise de Crédito/Equatorial",
    },
    "Brava Energia": {
        "nome_cvm": "BRAVA ENERGIA S.A.",
        "url_ri": "",
        "categorias_release": [],
        "categorias_dfp_itr": [],
        "pasta_pdfs": "G:/Meu Drive/Análise de Crédito/Brava Energia",
    },
    "Plano & Plano": {
        "nome_cvm": "PLANO & PLANO DESENVOLVIMENTO IMOBILIÁRIO S.A.",
        "url_ri": "https://ri.planoeplano.com.br/informacoes-financeiras/central-de-resultados/",
        "categorias_release": ["central_de_resultados_release"],
        "categorias_dfp_itr": ["central_de_resultados_itr", "central_de_resultados_dfp"],
        "pasta_pdfs": "G:/Meu Drive/Análise de Crédito/Plano e Plano",
    },
    "CSN - Companhia Siderurgica Nacional": {
        "nome_cvm": "CIA SIDERURGICA NACIONAL",
        "url_ri": "https://ri.csn.com.br/informacoes-financeiras/central-de-resultados/",
        "categorias_release": ["central-release"],
        "categorias_dfp_itr": ["central-itr-dfp"],
        "pasta_pdfs": "G:/Meu Drive/Análise de Crédito/CSN Siderurgica",
    },
}


def coletar_ri(empresa: str, config: dict, ano_inicio: int, ano_fim: int | None = None):
    """Coleta PDFs via Buscador RI."""
    print("\n" + "=" * 60)
    print("ETAPA 1: Coleta de PDFs via Buscador RI")
    print("=" * 60)

    buscador = BuscadorRI()

    # Release de Resultados
    if config.get("categorias_release"):
        print("\n--- Releases ---")
        buscador.coletar(
            empresa=empresa,
            url_ri=config["url_ri"],
            categorias=config["categorias_release"],
            ano_inicio=ano_inicio,
            ano_fim=ano_fim,
            pasta_destino=os.path.join(config["pasta_pdfs"], "Releases"),
        )

    # ITR e DFP
    if config.get("categorias_dfp_itr"):
        print("\n--- ITR / DFP ---")
        buscador.coletar(
            empresa=empresa,
            url_ri=config["url_ri"],
            categorias=config["categorias_dfp_itr"],
            ano_inicio=ano_inicio,
            ano_fim=ano_fim,
            pasta_destino=os.path.join(config["pasta_pdfs"], "ITR_DFP"),
        )


def coletar_cvm(empresa: str, config: dict, ano_inicio: int, ano_fim: int | None = None):
    """Coleta dados estruturados via API CVM."""
    print("\n" + "=" * 60)
    print("ETAPA 2: Coleta de Dados Estruturados via API CVM")
    print("=" * 60)

    coletor = ColetorCVM(
        cache_dir=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "raw", "cvm_api"
        )
    )

    resultado = coletor.coletar(
        empresa=config["nome_cvm"],
        ano_inicio=ano_inicio,
        ano_fim=ano_fim,
        pasta_destino=os.path.join(config["pasta_pdfs"], "Dados_CVM"),
    )

    # Resumo
    print("\n--- Resumo CVM ---")
    print(f"Empresa: {resultado['cadastro']['razao_social']}")
    print(f"CNPJ: {resultado['cadastro']['cnpj']}")
    print(f"Código CVM: {resultado['cadastro']['cd_cvm']}")
    if resultado.get("b3"):
        print(f"Ticker B3: {resultado['b3'].get('ticker', 'N/A')}")
        print(f"Segmento: {resultado['b3'].get('segmento', 'N/A')}")
    print(f"Registros de contas extraídos: {len(resultado['contas'])}")

    return resultado


def listar_empresas():
    """Lista empresas cadastradas."""
    print("\nEmpresas cadastradas:")
    print("-" * 40)
    for nome, config in EMPRESAS.items():
        print(f"  • {nome}")
        print(f"    CVM: {config['nome_cvm']}")
        print(f"    RI: {config['url_ri']}")
        print(f"    Pasta: {config['pasta_pdfs']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Dashboard de Crédito - Coleta de Dados Financeiros"
    )
    parser.add_argument(
        "--empresa", help="Nome da empresa (deve estar cadastrada em EMPRESAS)"
    )
    parser.add_argument("--ano-inicio", type=int, default=2021)
    parser.add_argument("--ano-fim", type=int, default=None)
    parser.add_argument(
        "--apenas-ri", action="store_true", help="Coletar apenas PDFs do RI"
    )
    parser.add_argument(
        "--apenas-cvm", action="store_true", help="Coletar apenas dados da CVM"
    )
    parser.add_argument(
        "--listar", action="store_true", help="Listar empresas cadastradas"
    )
    args = parser.parse_args()

    if args.listar:
        listar_empresas()
        return

    if not args.empresa:
        parser.error("--empresa é obrigatório (use --listar para ver empresas cadastradas)")

    config = EMPRESAS.get(args.empresa)
    if not config:
        print(f"Empresa '{args.empresa}' não cadastrada.")
        listar_empresas()
        sys.exit(1)

    print(f"Dashboard de Crédito - Coleta de Dados")
    print(f"Empresa: {args.empresa}")
    print(f"Período: {args.ano_inicio} até {args.ano_fim or 'atual'}")
    print(f"Pasta: {config['pasta_pdfs']}")

    # Executar coletas
    if not args.apenas_cvm:
        coletar_ri(args.empresa, config, args.ano_inicio, args.ano_fim)

    if not args.apenas_ri:
        coletar_cvm(args.empresa, config, args.ano_inicio, args.ano_fim)

    print("\n" + "=" * 60)
    print("COLETA CONCLUÍDA")
    print("=" * 60)


if __name__ == "__main__":
    main()
