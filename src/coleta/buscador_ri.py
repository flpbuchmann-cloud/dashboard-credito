"""
Buscador RI - Download de PDFs (Release, ITR, DFP) via API MZ.

Acessa a API do sistema MZ (usado pela maioria dos sites de RI de empresas
listadas na B3) e faz download dos documentos em PDF para a pasta indicada.

Uso:
    from src.coleta.buscador_ri import BuscadorRI

    buscador = BuscadorRI()
    buscador.coletar(
        empresa="CSN Mineração",
        url_ri="https://ri.csnmineracao.com.br/informacoes-financeiras/central-de-resultados/",
        categorias=["central-release", "itr-dfp"],
        ano_inicio=2021,
        pasta_destino="G:/Meu Drive/Análise de Crédito/CSN Mineração"
    )
"""

import os
import re
import json
import time
import requests
from pathlib import Path
from datetime import datetime


class BuscadorRI:
    """Coleta documentos de sites de RI que usam a plataforma MZ (mziq.com)."""

    MZ_API_BASE = "https://apicatalog.mziq.com/filemanager"

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/html, */*",
        })

    def _log(self, msg: str):
        if self.verbose:
            try:
                print(f"[BuscadorRI] {msg}")
            except UnicodeEncodeError:
                print(f"[BuscadorRI] {msg.encode('ascii', 'replace').decode()}")

    def descobrir_config(self, url_ri: str) -> dict:
        """Acessa a página de RI e extrai company_id e categorias disponíveis."""
        self._log(f"Acessando {url_ri} ...")
        resp = self.session.get(url_ri, timeout=30)
        resp.raise_for_status()
        html = resp.text

        # Extrair filemanager ID (company_id no MZ)
        # Procurar pelo ID associado ao fmBase/filemanager (fmId)
        fm_match = re.search(
            r"(?:fmId|filemanager[^'\"]*?/d/)\s*[:=]\s*['\"]?"
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            html
        )

        company_id = None
        if fm_match:
            company_id = fm_match.group(1)
        else:
            # Fallback: pegar todos os UUIDs e usar o segundo
            # (o primeiro costuma ser stockinfo, o segundo filemanager)
            fm_ids = re.findall(
                r"['\"]([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})['\"]",
                html
            )
            if len(fm_ids) >= 2:
                company_id = fm_ids[1]
            elif fm_ids:
                company_id = fm_ids[0]

        # Extrair categorias (internal_name)
        categorias = re.findall(r"internal_name:\s*['\"]([^'\"]+)['\"]", html)

        if not company_id:
            raise ValueError(f"Não foi possível encontrar o company_id MZ em {url_ri}")

        config = {
            "company_id": company_id,
            "categorias_disponiveis": categorias,
            "url_ri": url_ri,
        }
        self._log(f"Company ID: {company_id}")
        self._log(f"Categorias: {categorias}")
        return config

    def listar_documentos(
        self,
        company_id: str,
        categorias: list[str],
        ano_inicio: int,
        ano_fim: int | None = None,
    ) -> list[dict]:
        """Consulta a API MZ e retorna lista de documentos disponíveis."""
        if ano_fim is None:
            ano_fim = datetime.now().year

        todos_docs = []
        url = f"{self.MZ_API_BASE}/company/{company_id}/filter/categories/year/meta"

        for ano in range(ano_inicio, ano_fim + 1):
            payload = {
                "year": ano,
                "categories": categorias,
                "language": "pt_BR",
                "published": True,
            }
            self._log(f"Buscando documentos de {ano}...")
            try:
                resp = self.session.post(url, json=payload, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                if data.get("success") and data.get("data", {}).get("document_metas"):
                    docs = data["data"]["document_metas"]
                    todos_docs.extend(docs)
                    self._log(f"  → {len(docs)} documentos encontrados em {ano}")
                else:
                    self._log(f"  → Nenhum documento em {ano}")
            except Exception as e:
                self._log(f"  → Erro ao buscar {ano}: {e}")

        return todos_docs

    def baixar_documento(self, doc: dict, pasta_destino: str) -> str | None:
        """Faz download de um documento e salva na pasta destino."""
        url = doc.get("permalink") or doc.get("file_url")
        if not url:
            self._log(f"  → Sem URL para: {doc.get('file_title', '?')}")
            return None

        titulo = doc.get("file_title", "documento").strip()
        trimestre = doc.get("file_quarter", 0)
        ano = doc.get("file_year", 0)
        categoria = doc.get("internal_name", "outro")

        # Montar nome do arquivo padronizado
        nome_arquivo = self._nome_padronizado(titulo, categoria, trimestre, ano)
        caminho = os.path.join(pasta_destino, nome_arquivo)

        if os.path.exists(caminho):
            self._log(f"  → Já existe: {nome_arquivo}")
            return caminho

        try:
            resp = self.session.get(url, timeout=120, stream=True)
            resp.raise_for_status()

            # Detectar extensão pelo content-type
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" in content_type:
                ext = ".pdf"
            elif "spreadsheet" in content_type or "excel" in content_type:
                ext = ".xlsx"
            elif "zip" in content_type:
                ext = ".zip"
            else:
                ext = ".pdf"  # default

            if not caminho.endswith(ext):
                caminho = caminho + ext

            os.makedirs(pasta_destino, exist_ok=True)
            with open(caminho, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            tamanho_mb = os.path.getsize(caminho) / (1024 * 1024)
            self._log(f"  ✓ {os.path.basename(caminho)} ({tamanho_mb:.1f} MB)")
            return caminho

        except Exception as e:
            self._log(f"  → Erro ao baixar {titulo}: {e}")
            return None

    def _nome_padronizado(
        self, titulo: str, categoria: str, trimestre: int, ano: int
    ) -> str:
        """Gera nome padronizado: Tipo_QTaa (ex: Release_4T21, DFP_4T21, ITR_3T24)."""
        titulo_lower = titulo.lower()
        ano_curto = str(ano)[2:]  # 2024 -> 24

        if "release" in titulo_lower:
            tipo = "Release"
        elif "dfp" in titulo_lower or ("demonstra" in titulo_lower and trimestre == 4):
            tipo = "DFP"
        elif "itr" in titulo_lower or "demonstra" in titulo_lower:
            tipo = "ITR"
        elif "apresenta" in titulo_lower:
            tipo = "Apresentacao"
        else:
            # Limpar caracteres inválidos
            tipo = re.sub(r'[<>:"/\\|?*]', '', titulo)[:40]

        return f"{tipo}_{trimestre}T{ano_curto}"

    def coletar(
        self,
        empresa: str,
        url_ri: str,
        categorias: list[str] | None = None,
        ano_inicio: int = 2021,
        ano_fim: int | None = None,
        pasta_destino: str | None = None,
    ) -> list[str]:
        """
        Fluxo completo de coleta.

        Args:
            empresa: Nome da empresa (para log e pasta default)
            url_ri: URL da central de resultados do site de RI
            categorias: Lista de internal_names (ex: ["central-release", "itr-dfp"])
                        Se None, descobre automaticamente
            ano_inicio: Ano inicial da coleta
            ano_fim: Ano final (default: ano atual)
            pasta_destino: Pasta onde salvar os arquivos

        Returns:
            Lista de caminhos dos arquivos baixados
        """
        self._log(f"=== Coleta: {empresa} ===")

        # 1. Descobrir config do site
        config = self.descobrir_config(url_ri)

        # 2. Definir categorias
        if categorias is None:
            categorias = config["categorias_disponiveis"]
        self._log(f"Categorias selecionadas: {categorias}")

        # 3. Listar documentos
        docs = self.listar_documentos(
            config["company_id"], categorias, ano_inicio, ano_fim
        )
        self._log(f"Total de documentos encontrados: {len(docs)}")

        # 4. Baixar
        if pasta_destino is None:
            pasta_destino = os.path.join("data", "raw", "pdfs", empresa)

        arquivos = []
        for doc in sorted(docs, key=lambda d: (d.get("file_year", 0), d.get("file_quarter", 0))):
            caminho = self.baixar_documento(doc, pasta_destino)
            if caminho:
                arquivos.append(caminho)
            time.sleep(0.5)  # rate limit

        self._log(f"=== Concluído: {len(arquivos)} arquivos baixados ===")
        return arquivos


# ---------- Configurações de empresas conhecidas ----------

EMPRESAS_MZ = {
    "CSN Mineração": {
        "url_ri": "https://ri.csnmineracao.com.br/informacoes-financeiras/central-de-resultados/",
        "categorias_release": ["central-release"],
        "categorias_dfp_itr": ["itr-dfp"],
    },
    # Adicionar mais empresas conforme uso
}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Buscador RI - Download de documentos")
    parser.add_argument("--empresa", required=True, help="Nome da empresa")
    parser.add_argument("--url-ri", help="URL da central de resultados")
    parser.add_argument("--categorias", nargs="+", help="Categorias (internal_name)")
    parser.add_argument("--ano-inicio", type=int, default=2021)
    parser.add_argument("--ano-fim", type=int, default=None)
    parser.add_argument("--pasta", help="Pasta destino")
    args = parser.parse_args()

    # Se empresa conhecida, usar config pré-definida
    config_empresa = EMPRESAS_MZ.get(args.empresa, {})
    url_ri = args.url_ri or config_empresa.get("url_ri")
    if not url_ri:
        parser.error(f"URL de RI não fornecida e empresa '{args.empresa}' não está cadastrada")

    categorias = args.categorias
    if not categorias and config_empresa:
        categorias = config_empresa.get("categorias_release", []) + config_empresa.get("categorias_dfp_itr", [])

    buscador = BuscadorRI()
    buscador.coletar(
        empresa=args.empresa,
        url_ri=url_ri,
        categorias=categorias,
        ano_inicio=args.ano_inicio,
        ano_fim=args.ano_fim,
        pasta_destino=args.pasta,
    )
