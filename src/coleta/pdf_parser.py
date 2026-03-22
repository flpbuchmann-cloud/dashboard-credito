"""
Parser de PDF para extração de cronograma de amortização de dívida.

Extrai dados de ITR/DFP da CVM (CSN Mineração e similares).
Usa pdfplumber + regex. Claude API como fallback opcional.

Uso:
    from src.coleta.pdf_parser import extrair_cronogramas_pasta, salvar_cronogramas
    cronogramas = extrair_cronogramas_pasta("pasta/ITR_DFP/", n_recentes=3)
    salvar_cronogramas(cronogramas, "saida/cronogramas.json")
"""

import os
import json
import re
import pdfplumber

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _limpar_numero(s: str) -> float | None:
    """Converte '1.706.062' ou '486.776' para float."""
    if not s:
        return None
    s = re.sub(r'\s+', '', s.strip())
    negativo = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    if s.startswith('-'):
        negativo = True
        s = s[1:]
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        partes = s.split('.')
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
            s = s.replace('.', '')
    try:
        val = float(s)
        return -val if negativo else val
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Extração de caixa
# ---------------------------------------------------------------------------

def _extrair_caixa(pdf: pdfplumber.PDF) -> float | None:
    """Extrai Caixa e Equivalentes do balanço."""
    for page in pdf.pages[:20]:
        text = page.extract_text() or ""
        for line in text.split('\n'):
            # Formato 1: conta "1.01.01" + Caixa
            # Formato 2: "Caixa e equivalentes de caixa" seguido de números
            is_caixa = ("1.01.01" in line and "aixa" in line) or \
                       ("aixa e equivalentes" in line.lower() and re.search(r'[\d]+\.[\d]{3}', line))
            if is_caixa:
                nums = re.findall(r'[\d]+(?:\.[\d]{3})+', line)
                valores = [v for v in (_limpar_numero(n) for n in nums) if v and v > 10000]
                if valores:
                    return valores[0] * 1000
    return None


# ---------------------------------------------------------------------------
# Parser: tabela por ano (formato limpo)
#   "2026 1 08.615 1 .597.447 1 .706.062"
#   "2027 1 8.041 1 .904.137 1 .922.178"
#   "Após 2031 2 .219.571 4 94.795 2 .714.366"
# ---------------------------------------------------------------------------

def _parse_tabela_por_ano(pdf: pdfplumber.PDF) -> dict | None:
    """
    Procura tabela com anos + valores Total na mesma linha.

    Formato típico da DFP (pág de vencimentos das dívidas):
    '2026 1 08.615 1 .597.447 1 .706.062'
    A última coluna é o Total (moeda estrangeira + nacional).
    """
    # Encontrar páginas com contexto de vencimento de dívida
    paginas_candidatas = set()
    for i, page in enumerate(pdf.pages):
        text = (page.extract_text() or "").lower()
        if "vencimento" in text and ("empr" in text or "d\xe9bito" in text or "d\xedvida" in text):
            paginas_candidatas.add(i)
            # A tabela pode estar na próxima página
            if i + 1 < len(pdf.pages):
                paginas_candidatas.add(i + 1)

    for idx in sorted(paginas_candidatas):
        text = pdf.pages[idx].extract_text() or ""
        lines = text.split('\n')
        vencimentos = {}

        for line in lines:
            # Padrão: ano no início da linha seguido de números
            # Ex: "2026 1 08.615 1 .597.447 1 .706.062"
            match_ano = re.match(r'^\s*(20[2-3]\d)\s+', line)
            match_apos = re.match(r'^\s*[Aa]p[óo]s\s+(20[2-3]\d)\s+', line)

            if match_ano or match_apos:
                # Limpar espaços espúrios nos números
                limpo = line
                limpo = re.sub(r'(\d)\s+(\d)', r'\1\2', limpo)
                limpo = re.sub(r'(\d)\s+\.', r'\1.', limpo)
                limpo = re.sub(r'\.\s+(\d)', r'.\1', limpo)
                # Re-limpar (pode ter camadas)
                limpo = re.sub(r'(\d)\s+(\d)', r'\1\2', limpo)

                # Extrair todos os números grandes (formato brasileiro)
                nums = re.findall(r'[\d]+(?:\.[\d]{3})+', limpo)
                valores = [v for v in (_limpar_numero(n) for n in nums) if v and v > 0]

                if valores:
                    # Último valor é o Total (moeda estrangeira + nacional)
                    total = valores[-1]

                    if match_apos:
                        vencimentos["longo_prazo"] = total * 1000
                    else:
                        ano = match_ano.group(1)
                        vencimentos[ano] = total * 1000

        if len(vencimentos) >= 3:
            return vencimentos

    return None


# ---------------------------------------------------------------------------
# Parser: tabela de vencimentos contratuais (faixas)
#   "Empréstimos, financiamentos e debêntures — 12 1.628.732 2.222.564 2.008.413 3.818.909 9.678.618"
# ---------------------------------------------------------------------------

def _parse_tabela_faixas(pdf: pdfplumber.PDF) -> dict | None:
    """
    Procura tabela com faixas: 'Menos de um ano | Entre um e dois | Entre dois e cinco | Acima de cinco'.

    Formato típico de ITR (nota de liquidez):
    Header: 'Menos de um   Entre um e   Entre dois e   Acima de'
    Data:   'Empréstimos... 1.628.732 2.222.564 2.008.413 3.818.909 9.678.618'
    """
    for page in pdf.pages:
        text = page.extract_text() or ""
        if "menos de um" not in text.lower():
            continue

        lines = text.split('\n')
        for i, line in enumerate(lines):
            if "menos de um" not in line.lower():
                continue

            # Procurar linha de empréstimos nas próximas 10 linhas
            for j in range(i + 1, min(i + 10, len(lines))):
                line_j = lines[j]
                if 'empr' not in line_j.lower():
                    continue
                if 'financiamento' not in line_j.lower() and 'deb' not in line_j.lower():
                    continue

                # Extrair números
                nums = re.findall(r'[\d]+(?:\.[\d]{3})+', line_j)
                valores = [v for v in (_limpar_numero(n) for n in nums) if v and v > 0]

                if len(valores) >= 4:
                    # Últimos 5 valores: ate_1_ano, 1_a_2, 2_a_5, acima_5, total
                    # Se tem 5 valores, o último é o total (ignorar)
                    return {
                        "ate_1_ano": valores[0] * 1000,
                        "1_a_2_anos": valores[1] * 1000,
                        "2_a_5_anos": valores[2] * 1000,
                        "acima_5_anos": valores[3] * 1000,
                    }
    return None


# ---------------------------------------------------------------------------
# Claude API fallback
# ---------------------------------------------------------------------------

def _extrair_com_claude(texto: str) -> dict | None:
    """Usa Claude Haiku para interpretar tabela fragmentada."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic()
    prompt = f"""Extraia o cronograma de amortização de dívida do texto abaixo (PDF da CVM).
O texto pode estar fragmentado. Reconstrua os números.
Valores em MILHARES de reais.

Retorne APENAS JSON:
{{"vencimentos": {{"2026": 1706062, "2027": 1922178, ..., "longo_prazo": 2714366}}}}

Use a linha "Total" (soma moeda estrangeira + nacional).
Para "Após 20XX", use "longo_prazo".
Se não encontrar: {{"erro": "nao encontrado"}}

Texto:
{texto[:6000]}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        resposta = response.content[0].text.strip()
        match = re.search(r'\{.*\}', resposta, re.DOTALL)
        if match:
            dados = json.loads(match.group())
            if "erro" in dados:
                return None
            vencimentos = dados.get("vencimentos", dados)
            return {k: float(v) * 1000 for k, v in vencimentos.items()
                    if isinstance(v, (int, float)) and v > 0}
    except Exception as e:
        print(f"[PDFParser] Claude API: {e}")

    return None


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def extrair_cronograma_amortizacao(
    caminho_pdf: str,
    data_referencia: str = "",
) -> dict:
    """
    Extrai cronograma de amortização de um PDF de ITR/DFP.

    Estratégia:
    1. Tabela por ano (formato DFP limpo)
    2. Tabela por faixas (formato ITR "menos de um ano")
    3. Claude API fallback
    """
    nome = os.path.basename(caminho_pdf)
    print(f"[PDFParser] {nome}...", end=" ")

    pdf = pdfplumber.open(caminho_pdf)
    caixa = _extrair_caixa(pdf)

    # Estratégia 1: tabela por ano
    vencimentos = _parse_tabela_por_ano(pdf)
    if vencimentos:
        print("OK (tabela por ano)")

    # Estratégia 2: tabela por faixas
    if not vencimentos:
        vencimentos = _parse_tabela_faixas(pdf)
        if vencimentos:
            print("OK (tabela faixas)")

    # Estratégia 3: Claude API
    if not vencimentos:
        # Extrair texto das páginas com "vencimento"
        textos = []
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if "vencimento" in text.lower() and ("empr" in text.lower() or "ano de" in text.lower()):
                textos.append(text)
        if textos:
            vencimentos = _extrair_com_claude("\n\n".join(textos[:3]))
            if vencimentos:
                print("OK (Claude API)")

    pdf.close()

    if not vencimentos:
        print("FALHOU")
        return {"erro": "Nao extraido", "arquivo": nome, "caixa": caixa}

    # Converter data
    dt_ref = ""
    if data_referencia:
        parts = data_referencia.split("/")
        if len(parts) == 3:
            dt_ref = f"{parts[2]}-{parts[1]}-{parts[0]}"

    divida_total = sum(v for v in vencimentos.values() if isinstance(v, (int, float)))

    return {
        "data_referencia": dt_ref,
        "caixa": caixa,
        "vencimentos": vencimentos,
        "divida_total": divida_total,
        "arquivo": nome,
    }


# ---------------------------------------------------------------------------
# Batch e utilitários
# ---------------------------------------------------------------------------

def _inferir_data_referencia(nome_arquivo: str) -> str:
    """Infere data de referência do nome do arquivo."""
    match = re.search(r'(\d)T(\d{2})', nome_arquivo)
    if match:
        tri = int(match.group(1))
        ano = int(match.group(2)) + 2000
        meses = {1: "03", 2: "06", 3: "09", 4: "12"}
        dias = {1: "31", 2: "30", 3: "30", 4: "31"}
        return f"{dias[tri]}/{meses[tri]}/{ano}"
    match_dfp = re.search(r'DFP[_\s]*(\d{4})', nome_arquivo)
    if match_dfp:
        return f"31/12/{match_dfp.group(1)}"
    return ""


def extrair_cronogramas_pasta(pasta_pdfs: str, n_recentes: int = 3) -> list[dict]:
    """Extrai cronograma dos N PDFs mais recentes."""
    import glob

    pdfs = sorted(set(
        glob.glob(os.path.join(pasta_pdfs, "ITR*.pdf")) +
        glob.glob(os.path.join(pasta_pdfs, "DFP*.pdf"))
    ))

    if not pdfs:
        print(f"[PDFParser] Nenhum PDF em {pasta_pdfs}")
        return []

    # Ordenar por data e pegar N mais recentes
    pdfs_info = []
    for p in pdfs:
        nome = os.path.basename(p)
        dr = _inferir_data_referencia(nome)
        if dr:
            parts = dr.split("/")
            sort_key = f"{parts[2]}-{parts[1]}-{parts[0]}"
            pdfs_info.append((sort_key, dr, p))

    pdfs_info.sort(key=lambda x: x[0], reverse=True)
    recentes = pdfs_info[:n_recentes]

    print(f"[PDFParser] {len(recentes)}/{len(pdfs)} PDFs")
    cronogramas = []
    for _, dr, path in recentes:
        try:
            r = extrair_cronograma_amortizacao(path, dr)
            if "erro" not in r:
                cronogramas.append(r)
        except Exception as e:
            print(f"[PDFParser] Erro {os.path.basename(path)}: {e}")

    return cronogramas


def salvar_cronogramas(cronogramas: list[dict], caminho_saida: str):
    """Salva cronogramas em JSON."""
    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(cronogramas, f, ensure_ascii=False, indent=2, default=str)
    print(f"[PDFParser] Salvos em {caminho_saida}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        pdf_path = "G:/Meu Drive/Análise de Crédito/CSN Mineração/ITR_DFP/ITR_3T24.pdf"
    r = extrair_cronograma_amortizacao(pdf_path, _inferir_data_referencia(os.path.basename(pdf_path)))
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
