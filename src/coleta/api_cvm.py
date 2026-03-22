"""
API CVM - Coleta de dados financeiros estruturados da CVM (dados.cvm.gov.br).

Baixa e processa os CSVs de DFP (anual) e ITR (trimestral) do Portal de
Dados Abertos da CVM, extraindo DRE, Balanço Patrimonial e Fluxo de Caixa
para a empresa selecionada.

Uso:
    from src.coleta.api_cvm import ColetorCVM

    coletor = ColetorCVM()
    dados = coletor.coletar(
        empresa="CSN MINERAÇÃO S.A.",
        ano_inicio=2021,
    )
    # dados = {
    #   "cadastro": {...},
    #   "dre": DataFrame,
    #   "bpa": DataFrame,
    #   "bpp": DataFrame,
    #   "dfc": DataFrame,
    # }
"""

import os
import io
import zipfile
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime


class ColetorCVM:
    """Coleta dados financeiros estruturados do Portal de Dados Abertos da CVM."""

    BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA"
    CAD_URL = f"{BASE_URL}/CAD/DADOS/cad_cia_aberta.csv"

    # Arquivos dentro do ZIP que interessam (consolidado)
    ARQUIVOS_ITR = {
        "dre": "itr_cia_aberta_DRE_con_{ano}.csv",
        "bpa": "itr_cia_aberta_BPA_con_{ano}.csv",
        "bpp": "itr_cia_aberta_BPP_con_{ano}.csv",
        "dfc": "itr_cia_aberta_DFC_MI_con_{ano}.csv",
        "indice": "itr_cia_aberta_{ano}.csv",
    }

    ARQUIVOS_DFP = {
        "dre": "dfp_cia_aberta_DRE_con_{ano}.csv",
        "bpa": "dfp_cia_aberta_BPA_con_{ano}.csv",
        "bpp": "dfp_cia_aberta_BPP_con_{ano}.csv",
        "dfc": "dfp_cia_aberta_DFC_MI_con_{ano}.csv",
        "indice": "dfp_cia_aberta_{ano}.csv",
    }

    # Contas padronizadas CVM (plano de contas XBRL)
    CONTAS_CHAVE = {
        # ---- DRE ----
        "receita_liquida": "3.01",
        "custo": "3.02",
        "resultado_bruto": "3.03",
        "despesas_operacionais": "3.04",
        "despesas_vendas": "3.04.01",
        "despesas_ga": "3.04.02",
        "resultado_equivalencia": "3.04.06",
        "ebit": "3.05",
        "resultado_financeiro": "3.06",
        "receitas_financeiras": "3.06.01",
        "despesas_financeiras": "3.06.02",
        "lucro_antes_ir": "3.07",
        "ir_csll": "3.08",
        "lucro_liquido": "3.11",
        # ---- Balanço - Ativo ----
        "ativo_total": "1",
        "ativo_circulante": "1.01",
        "caixa": "1.01.01",
        "aplicacoes_financeiras_cp": "1.01.02",
        "contas_a_receber": "1.01.03",
        "estoques_cp": "1.01.04",
        "ativo_nao_circulante": "1.02",
        "investimentos": "1.02.02",
        "imobilizado": "1.02.03",
        "intangivel": "1.02.04",
        # ---- Balanço - Passivo ----
        "passivo_total": "2",
        "passivo_circulante": "2.01",
        "fornecedores": "2.01.02",
        "obrigacoes_fiscais_cp": "2.01.03",
        "emprestimos_cp": "2.01.04",
        "outras_obrigacoes_cp": "2.01.05",
        "provisoes_cp": "2.01.06",
        "passivo_nao_circulante": "2.02",
        "emprestimos_lp": "2.02.01",
        "outras_obrigacoes_lp": "2.02.02",
        "provisoes_lp": "2.02.04",
        "patrimonio_liquido": "2.03",
        "capital_social": "2.03.01",
        # ---- DFC (Método Indireto) ----
        "fco": "6.01",
        "caixa_gerado_operacoes": "6.01.01",
        "depreciacao_amortizacao": "6.01.01.09",
        "juros_emprestimos_dfc": "6.01.01.05",
        "var_ativos_passivos": "6.01.02",
        "juros_pagos": "6.01.02.12",
        "fci": "6.02",
        "capex": "6.02.01",
        "fcf": "6.03",
        "amortizacao_divida": "6.03.01",
        "dividendos_pagos": "6.03.04",
        "captacao_divida": "6.03.05",
    }

    def __init__(self, cache_dir: str | None = None, verbose: bool = True):
        self.verbose = verbose
        self.session = requests.Session()
        self.cache_dir = cache_dir or os.path.join("data", "raw", "cvm_api")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._cadastro_df: pd.DataFrame | None = None

    def _log(self, msg: str):
        if self.verbose:
            try:
                print(f"[ColetorCVM] {msg}")
            except UnicodeEncodeError:
                print(f"[ColetorCVM] {msg.encode('ascii', 'replace').decode()}")

    # -------------------------------------------------------------------------
    # Cadastro de empresas
    # -------------------------------------------------------------------------
    def carregar_cadastro(self) -> pd.DataFrame:
        """Baixa e cacheia o cadastro de companhias abertas."""
        if self._cadastro_df is not None:
            return self._cadastro_df

        cache_path = os.path.join(self.cache_dir, "cad_cia_aberta.csv")

        # Usar cache se tiver menos de 7 dias
        if os.path.exists(cache_path):
            idade_dias = (datetime.now().timestamp() - os.path.getmtime(cache_path)) / 86400
            if idade_dias < 7:
                self._log("Usando cadastro em cache")
                self._cadastro_df = pd.read_csv(
                    cache_path, sep=";", encoding="latin1", dtype=str
                )
                return self._cadastro_df

        self._log("Baixando cadastro de empresas...")
        resp = self.session.get(self.CAD_URL, timeout=30)
        resp.raise_for_status()

        with open(cache_path, "wb") as f:
            f.write(resp.content)

        self._cadastro_df = pd.read_csv(
            io.BytesIO(resp.content), sep=";", encoding="latin1", dtype=str
        )
        return self._cadastro_df

    def buscar_empresa(self, nome: str) -> dict:
        """Busca empresa pelo nome (parcial, case-insensitive). Retorna info do cadastro."""
        df = self.carregar_cadastro()
        nome_upper = nome.upper()

        # Filtrar por nome - busca parcial
        mask = df["DENOM_SOCIAL"].str.upper().str.contains(nome_upper, na=False)
        resultados = df[mask & (df["SIT"] == "ATIVO")]

        if resultados.empty:
            # Tentar pelo nome comercial
            mask = df["DENOM_COMERC"].str.upper().str.contains(nome_upper, na=False)
            resultados = df[mask & (df["SIT"] == "ATIVO")]

        if resultados.empty:
            raise ValueError(f"Empresa não encontrada: {nome}")

        # Pegar a primeira (mais relevante)
        row = resultados.iloc[0]
        info = {
            "cnpj": row["CNPJ_CIA"],
            "razao_social": row["DENOM_SOCIAL"],
            "nome_comercial": row.get("DENOM_COMERC", ""),
            "cd_cvm": row["CD_CVM"],
            "setor": row.get("SETOR_ATIV", ""),
            "situacao": row["SIT"],
        }
        self._log(f"Empresa encontrada: {info['razao_social']} (CVM: {info['cd_cvm']})")
        return info

    # -------------------------------------------------------------------------
    # Busca na B3 (complementar)
    # -------------------------------------------------------------------------
    def buscar_empresa_b3(self, nome: str) -> dict | None:
        """Busca empresa na API da B3 para obter ticker e segmento."""
        import base64
        import json

        params = json.dumps({
            "language": "pt-br",
            "pageNumber": 1,
            "pageSize": 20,
            "company": nome.upper(),
        })
        encoded = base64.b64encode(params.encode()).decode()

        try:
            url = f"https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetInitialCompanies/{encoded}"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if data.get("results"):
                r = data["results"][0]
                return {
                    "ticker": r.get("issuingCompany", ""),
                    "nome": r.get("companyName", ""),
                    "nome_pregao": r.get("tradingName", ""),
                    "segmento": r.get("segment", ""),
                    "mercado": r.get("market", ""),
                    "cd_cvm_b3": r.get("codeCVM", ""),
                }
        except Exception as e:
            self._log(f"Erro ao buscar na B3: {e}")
        return None

    # -------------------------------------------------------------------------
    # Download e parsing dos ZIPs da CVM
    # -------------------------------------------------------------------------
    def _baixar_zip(self, tipo: str, ano: int) -> zipfile.ZipFile | None:
        """Baixa o ZIP do ITR ou DFP de um ano."""
        tipo_lower = tipo.lower()
        url = f"{self.BASE_URL}/DOC/{tipo.upper()}/DADOS/{tipo_lower}_cia_aberta_{ano}.zip"

        cache_path = os.path.join(self.cache_dir, f"{tipo_lower}_{ano}.zip")

        # Cache: reusar se tiver menos de 1 dia
        if os.path.exists(cache_path):
            idade_dias = (datetime.now().timestamp() - os.path.getmtime(cache_path)) / 86400
            if idade_dias < 1:
                self._log(f"Usando cache: {tipo_lower}_{ano}.zip")
                return zipfile.ZipFile(cache_path)

        self._log(f"Baixando {tipo.upper()} {ano}...")
        try:
            resp = self.session.get(url, timeout=120)
            resp.raise_for_status()
            with open(cache_path, "wb") as f:
                f.write(resp.content)
            return zipfile.ZipFile(cache_path)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                self._log(f"  >{tipo.upper()} {ano} não disponível (404)")
            else:
                self._log(f"  >Erro ao baixar {tipo.upper()} {ano}: {e}")
            return None

    def _extrair_csv_empresa(
        self, zf: zipfile.ZipFile, nome_csv: str, cd_cvm: str
    ) -> pd.DataFrame:
        """Extrai e filtra CSV de dentro do ZIP para uma empresa específica."""
        with zf.open(nome_csv) as f:
            df = pd.read_csv(f, sep=";", encoding="latin1", dtype=str)

        # Filtrar pela empresa (CD_CVM)
        # O CD_CVM pode ter zeros à esquerda
        cd_cvm_padded = cd_cvm.zfill(6)
        mask = df["CD_CVM"].str.zfill(6) == cd_cvm_padded
        return df[mask].copy()

    def coletar_demonstracoes(
        self,
        cd_cvm: str,
        tipo: str,  # "ITR" ou "DFP"
        ano: int,
    ) -> dict[str, pd.DataFrame]:
        """Coleta todas as demonstrações de um ano para uma empresa."""
        zf = self._baixar_zip(tipo, ano)
        if zf is None:
            return {}

        tipo_lower = tipo.lower()
        arquivos_map = self.ARQUIVOS_ITR if tipo_lower == "itr" else self.ARQUIVOS_DFP

        resultado = {}
        for chave, template in arquivos_map.items():
            nome_csv = template.format(ano=ano)
            try:
                df = self._extrair_csv_empresa(zf, nome_csv, cd_cvm)
                if not df.empty:
                    resultado[chave] = df
                    self._log(f"  > {chave}: {len(df)} registros")
            except (KeyError, FileNotFoundError):
                self._log(f"  >{chave}: arquivo não encontrado no ZIP")

        zf.close()
        return resultado

    # -------------------------------------------------------------------------
    # Processamento e normalização
    # -------------------------------------------------------------------------
    def normalizar_demonstracao(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normaliza um DataFrame de demonstração financeira."""
        if df.empty:
            return df

        # Converter valor para float
        df = df.copy()
        df["VL_CONTA"] = pd.to_numeric(df["VL_CONTA"], errors="coerce")

        # Converter datas
        for col in ["DT_REFER", "DT_FIM_EXERC"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        if "DT_INI_EXERC" in df.columns:
            df["DT_INI_EXERC"] = pd.to_datetime(df["DT_INI_EXERC"], errors="coerce")

        # Manter apenas a versão mais recente de cada documento
        if "VERSAO" in df.columns:
            df["VERSAO"] = pd.to_numeric(df["VERSAO"], errors="coerce")
            idx = df.groupby(["DT_REFER", "CD_CONTA", "ORDEM_EXERC"])["VERSAO"].idxmax()
            df = df.loc[idx]

        # Aplicar escala da moeda
        if "ESCALA_MOEDA" in df.columns:
            escala_map = {"MIL": 1_000, "UNIDADE": 1}
            df["FATOR_ESCALA"] = df["ESCALA_MOEDA"].map(escala_map).fillna(1)
            df["VL_CONTA_REAL"] = df["VL_CONTA"] * df["FATOR_ESCALA"]
        else:
            df["VL_CONTA_REAL"] = df["VL_CONTA"]

        return df

    def extrair_contas_chave(
        self, df: pd.DataFrame, exercicio: str = "ÚLTIMO"
    ) -> dict[str, float]:
        """Extrai as contas-chave de um DataFrame normalizado."""
        df_norm = self.normalizar_demonstracao(df)
        if df_norm.empty:
            return {}

        # Filtrar pelo exercício (ÚLTIMO = período atual, PENÚLTIMO = comparativo)
        # O encoding pode variar, então fazemos busca parcial
        mask_exerc = df_norm["ORDEM_EXERC"].str.contains("LTIMO", na=False)
        if "PEN" not in exercicio.upper():
            mask_exerc = mask_exerc & ~df_norm["ORDEM_EXERC"].str.contains("PEN", na=False)
        else:
            mask_exerc = df_norm["ORDEM_EXERC"].str.contains("PEN", na=False)

        df_ex = df_norm[mask_exerc]

        resultado = {}
        for nome, cd_conta in self.CONTAS_CHAVE.items():
            mask = df_ex["CD_CONTA"] == cd_conta
            rows = df_ex[mask]
            if not rows.empty:
                resultado[nome] = rows.iloc[0]["VL_CONTA_REAL"]

        return resultado

    # -------------------------------------------------------------------------
    # Fluxo principal
    # -------------------------------------------------------------------------
    def coletar(
        self,
        empresa: str,
        ano_inicio: int = 2021,
        ano_fim: int | None = None,
        salvar_csv: bool = True,
        pasta_destino: str | None = None,
    ) -> dict:
        """
        Fluxo completo: busca empresa, baixa ITR+DFP, normaliza e salva.

        Returns:
            Dict com:
                - cadastro: info da empresa
                - b3: info da B3 (ticker, segmento)
                - itr: {ano: {tipo_dem: DataFrame}}
                - dfp: {ano: {tipo_dem: DataFrame}}
                - contas: [{periodo, tipo, contas_chave}]
        """
        if ano_fim is None:
            ano_fim = datetime.now().year

        self._log(f"=== Coleta CVM: {empresa} ===")

        # 1. Buscar empresa
        cadastro = self.buscar_empresa(empresa)
        cd_cvm = cadastro["cd_cvm"]

        # 2. Buscar na B3
        info_b3 = self.buscar_empresa_b3(empresa)

        # 3. Coletar ITR e DFP
        todos_itr = {}
        todos_dfp = {}
        todas_contas = []

        for ano in range(ano_inicio, ano_fim + 1):
            self._log(f"\n--- {ano} ---")

            # ITR (trimestral)
            itr_data = self.coletar_demonstracoes(cd_cvm, "ITR", ano)
            if itr_data:
                todos_itr[ano] = itr_data
                # Extrair contas de cada trimestre
                for tipo_dem in ["dre", "bpa", "bpp", "dfc"]:
                    if tipo_dem in itr_data:
                        df = itr_data[tipo_dem]
                        df_norm = self.normalizar_demonstracao(df)
                        # Agrupar por DT_REFER (cada trimestre)
                        for dt_ref, grupo in df_norm.groupby("DT_REFER"):
                            contas = self.extrair_contas_chave(grupo)
                            if contas:
                                todas_contas.append({
                                    "periodo": str(dt_ref.date()) if hasattr(dt_ref, "date") else str(dt_ref),
                                    "tipo": f"ITR_{tipo_dem}",
                                    "ano": ano,
                                    "contas": contas,
                                })

            # DFP (anual)
            dfp_data = self.coletar_demonstracoes(cd_cvm, "DFP", ano)
            if dfp_data:
                todos_dfp[ano] = dfp_data
                for tipo_dem in ["dre", "bpa", "bpp", "dfc"]:
                    if tipo_dem in dfp_data:
                        df = dfp_data[tipo_dem]
                        df_norm = self.normalizar_demonstracao(df)
                        for dt_ref, grupo in df_norm.groupby("DT_REFER"):
                            contas = self.extrair_contas_chave(grupo)
                            if contas:
                                todas_contas.append({
                                    "periodo": str(dt_ref.date()) if hasattr(dt_ref, "date") else str(dt_ref),
                                    "tipo": f"DFP_{tipo_dem}",
                                    "ano": ano,
                                    "contas": contas,
                                })

        # 4. Salvar CSVs consolidados
        if salvar_csv:
            if pasta_destino is None:
                pasta_destino = os.path.join(
                    self.cache_dir, cadastro["razao_social"].replace("/", "-")
                )
            os.makedirs(pasta_destino, exist_ok=True)

            for doc_tipo, dados_anos in [("itr", todos_itr), ("dfp", todos_dfp)]:
                for ano, dados in dados_anos.items():
                    for dem_tipo, df in dados.items():
                        if dem_tipo == "indice":
                            continue
                        df_norm = self.normalizar_demonstracao(df)
                        arquivo = os.path.join(
                            pasta_destino, f"{doc_tipo}_{dem_tipo}_{ano}.csv"
                        )
                        df_norm.to_csv(arquivo, index=False, encoding="utf-8-sig")

            # Salvar contas consolidadas
            if todas_contas:
                import json
                arquivo_contas = os.path.join(pasta_destino, "contas_chave.json")
                with open(arquivo_contas, "w", encoding="utf-8") as f:
                    json.dump(todas_contas, f, ensure_ascii=False, indent=2, default=str)
                self._log(f"Contas salvas em {arquivo_contas}")

        resultado = {
            "cadastro": cadastro,
            "b3": info_b3,
            "itr": todos_itr,
            "dfp": todos_dfp,
            "contas": todas_contas,
        }

        self._log(f"\n=== Concluído: {len(todas_contas)} registros de contas extraídos ===")
        return resultado


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Coletor CVM - Dados Financeiros")
    parser.add_argument("--empresa", required=True, help="Nome da empresa")
    parser.add_argument("--ano-inicio", type=int, default=2021)
    parser.add_argument("--ano-fim", type=int, default=None)
    parser.add_argument("--pasta", help="Pasta destino para CSVs")
    args = parser.parse_args()

    coletor = ColetorCVM()
    resultado = coletor.coletar(
        empresa=args.empresa,
        ano_inicio=args.ano_inicio,
        ano_fim=args.ano_fim,
        pasta_destino=args.pasta,
    )

    print(f"\nCadastro: {resultado['cadastro']}")
    print(f"B3: {resultado['b3']}")
    print(f"Total contas extraídas: {len(resultado['contas'])}")
