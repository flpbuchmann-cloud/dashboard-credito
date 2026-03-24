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
    for page in pdf.pages[:70]:
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
    # Encontrar páginas candidatas: duas abordagens
    # 1) Páginas com contexto de dívida (keywords) + vizinhas
    # 2) Qualquer página que tenha >= 3 linhas começando com ano + números
    paginas_candidatas = set()
    for i, page in enumerate(pdf.pages):
        text = (page.extract_text() or "").lower()
        has_venc = "vencimento" in text
        has_debt = "empr" in text or "d\xe9bito" in text or "d\xedvida" in text or "debentur" in text
        if (has_venc and has_debt) or (has_debt and "cronograma" in text):
            paginas_candidatas.add(i)
            if i + 1 < len(pdf.pages):
                paginas_candidatas.add(i + 1)
            if i - 1 >= 0:
                paginas_candidatas.add(i - 1)

        # Fallback: detectar diretamente páginas com tabela de anos + valores
        full_text = page.extract_text() or ""
        year_lines = sum(1 for l in full_text.split('\n')
                         if re.match(r'^\s*20[2-4]\d[\s\-–a]', l) and re.search(r'[\d]+(?:\.[\d]{3})', l))
        if year_lines >= 3:
            paginas_candidatas.add(i)

    melhor = None
    melhor_total = 0
    for idx in sorted(paginas_candidatas):
        text = pdf.pages[idx].extract_text() or ""
        lines = text.split('\n')
        vencimentos = {}

        for line in lines:
            # Padrão: ano no início da linha seguido de números
            # Ex: "2026 1 08.615 1 .597.447 1 .706.062"
            match_ano = re.match(r'^\s*(20[2-3]\d)\s+', line)
            match_apos = re.match(r'^\s*[Aa]p[óo]s\s+(20[2-3]\d)\s+', line)

            # Padrão: faixa de anos "2030 - 2033", "2032a 2045", "2031 até 2033"
            match_faixa = re.match(r'^\s*(20[2-3]\d)\s*[-–]\s*(20[2-4]\d)\s+', line)
            if not match_faixa:
                match_faixa = re.match(r'^\s*(20[2-4]\d)\s*(?:a|até)\s+(20[2-5]\d)\s+', line)

            if match_ano or match_apos or match_faixa:
                # Remover o prefixo (ano/faixa) antes de limpar espaços nos números
                # para evitar que o ano se concatene com o valor
                if match_faixa:
                    resto = line[match_faixa.end():]
                    ano_label = match_faixa.group(2)  # último ano da faixa
                elif match_apos:
                    resto = line[match_apos.end():]
                    ano_label = None
                else:
                    resto = line[match_ano.end():]
                    ano_label = match_ano.group(1)

                # Se a linha tem colunas duplicadas (individual + consolidado),
                # pegar apenas a última coluna (após o último ano repetido)
                dup = re.search(r'(20[2-4]\d)\s+', resto)
                if dup:
                    # Há outro ano no resto — usar a parte após ele
                    resto = resto[dup.end():]

                # Também tratar "2032a 2045" como faixa (sem o hífen)
                faixa_a = re.match(r'^a\s+(20[2-4]\d)\s+', resto)
                if faixa_a:
                    ano_label = faixa_a.group(1)
                    resto = resto[faixa_a.end():]

                # Limpar espaços espúrios nos números
                limpo = resto
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
                    elif match_faixa:
                        vencimentos[ano_label] = total * 1000
                    else:
                        vencimentos[ano_label] = total * 1000

        if len(vencimentos) >= 3:
            total_val = sum(vencimentos.values())
            if melhor is None or total_val > melhor_total:
                melhor = vencimentos
                melhor_total = total_val

    return melhor


# ---------------------------------------------------------------------------
# Parser: tabela com header de anos (formato Minerva)
#   Header: "2026 2027 2028 2029 2030 ... Total"
#   Linhas: "Debêntures 391.253 - 2.486.531 ... 14.086.562"
#   Linha Total: "Total 59.910 1.641.964 ... 22.114.338"
# ---------------------------------------------------------------------------

def _parse_tabela_header_anos(pdf: pdfplumber.PDF) -> dict | None:
    """
    Procura tabela onde os anos estão no header e a linha 'Total' tem os valores.
    Usa a tabela CONSOLIDADA (segunda ocorrência) quando disponível.
    """
    for page in pdf.pages:
        text = page.extract_text() or ""
        if "ano de vencimento" not in text.lower():
            continue

        lines = text.split('\n')
        # Procurar linhas de header com anos
        for i, line in enumerate(lines):
            # Header: "2026 2027 2028 ... Total"
            anos_match = re.findall(r'(20[2-4]\d)', line)
            if len(anos_match) < 3 or 'total' not in line.lower():
                continue

            anos = anos_match
            # Procurar linha "Total" nas próximas linhas
            total_line = None
            for j in range(i + 1, min(i + 30, len(lines))):
                if re.match(r'^\s*Total\s', lines[j]):
                    total_line = lines[j]
                    # Continuar procurando — a segunda "Total" é a consolidada
                    for k in range(j + 1, min(j + 30, len(lines))):
                        if re.match(r'^\s*Total\s', lines[k]):
                            total_line = lines[k]
                            break
                    break

            if not total_line:
                continue

            # Limpar e extrair números
            limpo = total_line
            limpo = re.sub(r'(\d)\s+(\d)', r'\1\2', limpo)
            limpo = re.sub(r'(\d)\s+\.', r'\1.', limpo)
            limpo = re.sub(r'\.\s+(\d)', r'.\1', limpo)
            limpo = re.sub(r'(\d)\s+(\d)', r'\1\2', limpo)

            # Números positivos e negativos
            nums_raw = re.findall(r'-?[\d]+(?:\.[\d]{3})*', limpo)
            valores = []
            for n in nums_raw:
                v = _limpar_numero(n)
                if v is not None:
                    valores.append(v)

            if len(valores) >= len(anos):
                vencimentos = {}
                for idx_ano, ano in enumerate(anos):
                    if idx_ano < len(valores) and valores[idx_ano] > 0:
                        vencimentos[ano] = valores[idx_ano] * 1000
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
# Parser: cronograma em Release de Resultados
#   Formato: gráfico de barras com anos e valores em texto
#   Ex: "Caixa⁽²⁾ 23.717"
#       "2026 369"
#       "2027 3.516"
#       "2036-45 2.313"
# ---------------------------------------------------------------------------

def _parse_release_cronograma(pdf: pdfplumber.PDF) -> tuple[dict | None, float | None]:
    """
    Extrai cronograma de amortização de um Release de Resultados.
    Retorna (vencimentos, caixa) — ambos podem ser None.
    """
    for page in pdf.pages:
        text = page.extract_text() or ""
        if "cronograma" not in text.lower() or "amortiza" not in text.lower():
            continue

        lines = text.split('\n')
        vencimentos = {}
        caixa = None

        for line in lines:
            # Caixa: "Caixa⁽²⁾ 23.717" ou "Caixa(2) 23.717"
            match_caixa = re.search(r'[Cc]aixa[^\d]*?([\d]+(?:\.[\d]+)*)\s*$', line)
            if match_caixa:
                v = _limpar_numero(match_caixa.group(1))
                if v and v > 100:
                    caixa = v * 1_000_000  # valores em milhões no release

            # Ano simples (pode estar no meio da linha): "2026 369"
            # Usar findall para pegar todos os pares ano+valor na linha
            for match_ano in re.finditer(r'(20[2-4]\d)\s+([\d]+(?:\.[\d]+)*)', line):
                ano = match_ano.group(1)
                v = _limpar_numero(match_ano.group(2))
                if v and v > 0 and ano not in vencimentos:
                    vencimentos[ano] = v * 1_000_000

            # Faixa de anos: "2036-45 2.313" ou "2036-2045 2.313"
            match_faixa = re.search(
                r'(20[2-4]\d)\s*[-–]\s*(\d{2,4})\s+([\d]+(?:\.[\d]+)*)', line
            )
            if match_faixa:
                ano_fim = match_faixa.group(2)
                if len(ano_fim) == 2:
                    ano_fim = match_faixa.group(1)[:2] + ano_fim
                v = _limpar_numero(match_faixa.group(3))
                if v and v > 0:
                    vencimentos[ano_fim] = v * 1_000_000

        if len(vencimentos) >= 3:
            return vencimentos, caixa

    return None, None


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
    caixa = None
    vencimentos = None
    is_release = any(kw in nome.lower() for kw in ["relat", "release", "resultado"])

    if is_release:
        # Para Releases, tentar parser específico primeiro
        vencimentos, caixa_release = _parse_release_cronograma(pdf)
        if vencimentos:
            print("OK (release)")
            caixa = caixa_release

    if not caixa:
        caixa = _extrair_caixa(pdf)

    # Estratégia 1: tabela por ano (anos no início da linha)
    if not vencimentos:
        vencimentos = _parse_tabela_por_ano(pdf)
        if vencimentos:
            print("OK (tabela por ano)")

    # Estratégia 2: tabela com header de anos (Minerva, etc.)
    if not vencimentos:
        vencimentos = _parse_tabela_header_anos(pdf)
        if vencimentos:
            print("OK (tabela header anos)")

    # Estratégia 3: tabela por faixas
    if not vencimentos:
        vencimentos = _parse_tabela_faixas(pdf)
        if vencimentos:
            print("OK (tabela faixas)")

    # Estratégia 4: cronograma em Release de Resultados (fallback para outros PDFs)
    if not vencimentos:
        vencimentos, caixa_release = _parse_release_cronograma(pdf)
        if vencimentos:
            print("OK (release)")
            if caixa_release and not caixa:
                caixa = caixa_release

    # Estratégia 5: Claude API
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
    """Extrai cronograma dos N PDFs mais recentes (ITR/DFP + Releases)."""
    import glob

    pdfs = sorted(set(
        glob.glob(os.path.join(pasta_pdfs, "ITR*.pdf")) +
        glob.glob(os.path.join(pasta_pdfs, "DFP*.pdf"))
    ))

    # Também incluir Releases na pasta irmã ../Releases/
    pasta_releases = os.path.join(os.path.dirname(pasta_pdfs.rstrip("/\\")), "Releases")
    releases = sorted(glob.glob(os.path.join(pasta_releases, "*.pdf")))
    if releases:
        pdfs = sorted(set(pdfs + releases))

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

    # Agrupar por período (sort_key) — pode haver Release + ITR/DFP para o mesmo trimestre
    from collections import defaultdict
    por_periodo = defaultdict(list)
    for sort_key, dr, path in pdfs_info:
        por_periodo[sort_key].append((dr, path))

    # Pegar os N períodos mais recentes
    periodos_recentes = sorted(por_periodo.keys(), reverse=True)[:n_recentes]

    total_candidatos = sum(len(por_periodo[p]) for p in periodos_recentes)
    print(f"[PDFParser] {total_candidatos} candidatos para {len(periodos_recentes)} períodos")

    cronogramas = []
    for periodo in periodos_recentes:
        melhor = None
        for dr, path in por_periodo[periodo]:
            try:
                r = extrair_cronograma_amortizacao(path, dr)
                if "erro" not in r:
                    n_venc = len(r.get("vencimentos", {}))
                    if melhor is None or n_venc > len(melhor.get("vencimentos", {})):
                        melhor = r
            except Exception as e:
                print(f"[PDFParser] Erro {os.path.basename(path)}: {e}")
        if melhor:
            cronogramas.append(melhor)

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
