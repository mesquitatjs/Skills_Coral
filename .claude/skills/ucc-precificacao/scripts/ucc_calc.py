#!/usr/bin/env python3
"""
Calculadora da UCC — gera a PLANILHA de precificação em Markdown.

A conta sai daqui, nunca de aritmética feita à mão. Rode, confira a saída e só
então escreva a proposta.

⚠️ FONTE DE VERDADE DOS PARÂMETROS: projetos_coral/comercial/UCC_Modelo_Remuneracao.md
   Mudou parâmetro? Atualiza LÁ primeiro, depois aqui. Duplicar constante sem sincronizar
   já causou drift neste repo antes.

Uso:
    python3 ucc_calc.py --cpfs 12000 --regua 4 --wa 1 --sms 2 --email 0
    python3 ucc_calc.py --cpfs 6000 --regua 10 --telefones 1.6 --recuperacao 117530 \\
                        --fee-variavel 6.27 --saida planilha.md

    # preço DERIVADO do custo, na faixa tributária marginal certa:
    python3 ucc_calc.py --cpfs 12000 --regua 4 --wa 1 --sms 2 --alvo 20 --receita-base 62500

⚠️ O degrau tributário é da PESSOA JURÍDICA. Sem `--receita-base` o contrato é avaliado
   sozinho e, se a Coral já fatura acima de R$ 62.500/mês, o preço sai ~5,3% barato demais.
"""
import argparse
import pathlib
import re
from math import ceil

# ─── parâmetros (espelho do dossiê — calibração 10/09/2026) ──────────────────
P = {
    "tam_ucc":        2_500,    # DECIDIDO — é o break-even
    "preco_ucc":      8_000.0,  # DECIDIDO
    "bot":            1_020.0,  # TABELA (custo real) por unidade
    # "telecom_fixo" (R$ 1.500/unidade) foi APOSENTADO em 14/09/2026. Telecom não é
    # assinatura da unidade: é proporcional à discagem (coef_telecom, MEDIDO nas quatro
    # carteiras). O fixo equivalia a 4,38 tentativas/CPF/dia cobradas de toda a carteira,
    # que não é régua de ninguém — cobrava a mais na carteira leve e escondia prejuízo na
    # intensa. A comparação com ele saiu da tela e da planilha.
    "coef_telecom":   0.137,    # MEDIDO — R$/CPF/mês por tentativa/dia
    "wa":             0.45,     # TABELA por disparo
    "sms":            0.06,     # TABELA
    "email":          0.04,     # TABELA
    "crm_assento":    0.15,     # TABELA por CPF ativo
    "compart":        34_400.0, # TABELA total/mês
    "rateio_piso":    0.03,     # DECIDIDO
    "rateio_por_cpf": 1e-5,     # DECIDIDO — 1% a cada 1.000 CPFs
    "tributo":        0.1633,   # TABELA — Lucro Presumido, faixa BASE
    "teto_tributo":   62_500.0, # = teto_presumido ÷ presumido
    "irpj_adic":      0.10,     # TABELA — adicional de IRPJ sobre o excedente
    "presumido":      0.32,     # TABELA — presunção de lucro, serviços
    "teto_presumido": 20_000.0, # TABELA — lucro presumido/mês a partir do qual o adicional incide
    "ancora":         12_000.0, # DECIDIDO — posição humana + plataforma
    # teto do que o credor paga por R$ 1 recuperado. Estava só no simulador da tela até
    # 14/09; o dossiê já o documentava, então isto é a calculadora alcançando o doc.
    "teto_por_real":  0.30,     # DECIDIDO
    "pa_humana":      10_000.0, # TABELA de mercado — posição humana de transbordo
    "banda_gatilho":  0.15,
}
# realização da régua: contratada ≠ realizada (MEDIDO)
REALIZACAO = {2: 0.93, 10: 0.68}   # interpolado linearmente entre os dois pontos medidos


def realizacao_estimada(regua):
    lo, hi = 2, 10
    if regua <= lo: return REALIZACAO[lo]
    if regua >= hi: return REALIZACAO[hi]
    t = (regua - lo) / (hi - lo)
    return REALIZACAO[lo] + t * (REALIZACAO[hi] - REALIZACAO[lo])


# ── bot × canal: o de-para que a UCC nunca teve (parecer 14/09, item `botcanal`) ──
# A UCC conta BOTS — 2.500 CPFs por unidade, em QUALQUER régua. A operação conta CANAIS,
# e a conta é outra: `canais = régua × base ÷ (throughput por canal-hora × horas)`. Um
# canal cobre 3.461 CPFs a régua 1 e 346 a régua 10, então o mesmo "2.500" vendido pede
# 1,4 canal numa carteira leve e 7,2 numa intensa — 5× de amplitude dentro da mesma
# unidade. Enquanto as duas não conversam, o 2.500 é número comercial sem contrapartida.
THR_CANAL_H = 273.0        # MEDIDO — média das 4 carteiras (Ouro 270 · Bronze 274 ·
                           # PPay 285 · FIDC 264), recalibrado em 10/09 (§12)
JANELA_H = 12 + 40 / 60    # MEDIDO — janela operacional de dia útil


def canais_necessarios(cpfs, regua, thr=None, horas=None):
    """Canais que a operação liga para entregar esta régua nesta base.

    Devolve também quantos canais UMA unidade vendida exige, que é a leitura que falta
    na hora de dimensionar: a unidade é fixa em CPFs e o canal é função da régua.
    """
    thr = THR_CANAL_H if thr is None else float(thr)
    horas = JANELA_H if horas is None else float(horas)
    if not cpfs or not regua or thr <= 0 or horas <= 0:
        return dict(canais=0.0, cpfs_por_canal=0.0, canais_por_ucc=0.0)
    cpfs_canal = thr * horas / regua
    return dict(canais=cpfs * regua / (thr * horas),
                cpfs_por_canal=cpfs_canal,
                canais_por_ucc=P["tam_ucc"] / cpfs_canal)


def regua_fora_da_medida(regua):
    """A régua cotada está fora dos dois pontos que medimos?

    `realizacao_estimada` conhece 93% na régua 2 e 68% na régua 10 e traça uma reta entre
    eles. Régua no meio é interpolação (defensável); fora do intervalo é EXTRAPOLAÇÃO, e o
    γ = 1,00 da escada de voz também só foi medido até 10 tentativas. Quem cota precisa
    ver a diferença — ela não aparece em número nenhum da tela.
    """
    r = float(regua or 0)
    if r <= 0:
        return None
    if r < 2:
        return dict(lado="abaixo", limite=2.0, regua=r)
    if r > 10:
        return dict(lado="acima", limite=10.0, regua=r)
    return None


# item 7 do discovery — como a carteira é repartida entre assessorias
COMPART_MODELOS = ("exclusivo", "aberto", "rotativo")


# elasticidade de canal: fração da recuperação perdida ao tirar UM toque da base inteira.
# ⚠️ PREMISSA, não medição nossa — a operação que medimos é predominantemente de voz.
ELAST = {"wa": 0.03, "sms": 0.01, "email": 0.002}


# ── MATURAÇÃO DA CARTEIRA ────────────────────────────────────────────────────────────
# MEDIDO na operação da Principia (sonda `principia-acionamento/scripts/_q_colchao.py`,
# 14/09/2026, safras de 2025-01 em diante). Fração da recuperação de REGIME que uma
# carteira já entrega no mês N de contrato.
#
# De onde sai: um acordo de k parcelas entrega 1/k do valor no mês em que é fechado e o
# resto nos k-1 seguintes. Com peso w_k (por VALOR, nunca por contagem — o que vence é
# dinheiro), o mês m da carteira entrega `SOMA_k w_k * min(m,k)/k` do regime. Medido:
# 31,5% do R$ prometido fecha à vista, 41,7% em 7 parcelas, 10,2% em 9, e uma cauda em
# 25 que é 5,2% do R$ e segura a rampa por dois anos.
#
# 📌 O primeiro valor É o colchão: se no mês 1 a carteira entrega 41,6% do regime, os
#    outros 58,4% do regime vêm de acordo fechado em mês anterior. Colchão e rampa saem
#    do MESMO vetor, então não podem divergir entre si.
#
# ⛔ É a operação da Principia — PF, educacional, voz, com uma régua de parcelamento que
#    é dela. Outro credor tem outra curva; por isso o vetor é EDITÁVEL e a procedência
#    aparece na ficha.
MATURACAO = (0.416, 0.517, 0.600, 0.682, 0.761, 0.840, 0.917, 0.931, 0.946, 0.952,
             0.956, 0.960)

# Cumprimento MEDIDO só existe à vista (safra madura, 33,1% em R$ · 41,1% por contagem).
# ⛔ O do PARCELADO não é mensurável ainda: um acordo de 7 parcelas entra como quebrado
#    na primeira e só pode ser cumprido quando a última vencer, então numa janela curta
#    ele aparece perto de zero por CENSURA, não por comportamento. E é justamente o
#    parcelado que forma o colchão.
CUMPRIMENTO_AVISTA = 0.331


# ── A CADEIA DO COLCHAO, MEDIDA POR FAIXA (Principia, set/2026) ──────────────────
# Ate aqui o colchao era ENTRADA: o credor declarava saldo a vencer, prazo e eficiencia.
# Isso resolve o colchao HERDADO e pula a cadeia que o PRODUZ — e essa cadeia a operacao
# mede. Sonda: `principia-acionamento/scripts/_q_colchao_faixa.py` (mailing 06-09/2026,
# safras desde jan/2025).
#
#     recuperacao da faixa = carteira x conversao x (1 - desconto) x cumprimento
#
# Serve de CONFERENCIA contra a taxa que o credor informou. O `entra_no_mes` fica
# registrado porque descreve o espalhamento medido, mas NAO entra na conta: partir a
# recuperacao em "safra anterior" e "acordo novo" nao muda custo, preco, margem nem
# variavel, ja' que as duas sao nossas. O tempo entra pela curva de maturacao, na
# projecao de 12 meses.
#
# ⚠️ TRES RESSALVAS, e a primeira invalida uma coluna:
#   1. DESCONTO nao e' mensuravel por esta fonte. O denominador e' o `debt_amount` do
#      mailing, que carrega juros e multa que o acordo tambem cobra: 13% a 30% dos
#      acordos ficam ACIMA da divida de referencia e o "desconto" sai NEGATIVO em 01-30
#      (-3,7%). O valor entra como ~0 e a tela marca lacuna. Pedir ao credor.
#   2. CONVERSAO e' por CASO e a carteira e' em R$. Aplicar uma sobre a outra supoe que
#      quem fecha acordo tem o ticket medio da faixa. Premissa declarada, nao medida.
#   3. CUMPRIMENTO so' sai de coorte MADURA (safra + k meses <= fim). Na imatura o mesmo
#      numero da' 0,2% a 5,4% por CENSURA — o BROKEN chega na 1a parcela e o KEPT so' na
#      ultima. E CANCELED fica fora dos dois: no 361+ ele e' 80,2% do R$ prometido.
#
# ⚠️ Sao numeros da operacao da Principia (PF, educacional, voz). Entram como default
#    MEDIDO e editavel — credor com outro perfil tem outra curva.
PRINCIPIA_FAIXA = {
    #          conversao  parcelas  desconto  cumprimento  entra_no_mes
    "01-30":   (0.0203,   3.64,     0.0,      0.449,       0.694),
    "31-60":   (0.0192,   4.41,     0.0,      0.260,       0.591),
    "61-90":   (0.0185,   5.51,     0.0,      0.235,       0.522),
    "91-180":  (0.0161,   7.38,     0.0,      0.253,       0.298),
    "181-360": (0.0125,   8.01,     0.0,      0.233,       0.217),
    "361+":    (0.0037,   7.60,     0.0,      0.177,       0.373),
}
_FX_TETO = (("01-30", 30), ("31-60", 60), ("61-90", 90), ("91-180", 180),
            ("181-360", 360), ("361+", 10 ** 9))


def faixa_medida(nome):
    """Casa o nome da faixa do credor com a faixa MEDIDA, pelo teto do intervalo.

    O discovery pede 06-30 … +720 e a medicao sai em 6 faixas; casar por texto exigiria
    que o credor usasse os nossos rotulos. O teto e' o que define onde a faixa cai:
    "91-120" tem teto 120 e mora dentro de 91-180.
    """
    t = "".join(ch if ch.isdigit() else " " for ch in str(nome or ""))
    nums = [int(x) for x in t.split() if x]
    if not nums:
        return None
    teto = max(nums)
    if "+" in str(nome) and len(nums) == 1:
        teto = max(teto, 361)
    for chave, lim in _FX_TETO:
        if teto <= lim:
            return chave
    return "361+"


def elos_da_faixa(nome):
    """Os quatro elos medidos da faixa, como dict. `None` quando o nome nao resolve."""
    k = faixa_medida(nome)
    if not k:
        return None
    c, p, d, u, m = PRINCIPIA_FAIXA[k]
    return dict(chave=k, conversao=c, parcelas=p, desconto=d, cumprimento=u,
                entra_no_mes=m, colchao=1 - m)


def meta_derivada(nome):
    """A meta que a cadeia medida implica para a faixa: % da carteira recuperado no mes.

    Serve de CONFERENCIA contra a taxa que o credor informou — divergencia grande e'
    sinal de perfil diferente (ou de denominador diferente), nao de erro de conta.
    """
    e = elos_da_faixa(nome)
    return e["conversao"] * (1 - e["desconto"]) * e["cumprimento"] if e else None


def maturacao_de(mat=None, meses=12):
    """Normaliza o vetor de maturação: monótono, dentro de [0,1], estendido até `meses`.

    Depois do último valor informado a curva fica onde estava — extrapolar uma rampa é
    inventar recuperação que a carteira ainda não mostrou.
    """
    v = [float(x) for x in (mat if mat else MATURACAO)]
    if not v:
        raise SystemExit("⛔ maturação vazia.")
    if any(x < 0 or x > 1 for x in v):
        raise SystemExit(f"⛔ maturação fora de 0-100%: {v}")
    for i in range(1, len(v)):          # uma carteira não desaprende
        v[i] = max(v[i], v[i - 1])
    while len(v) < int(meses):
        v.append(v[-1])
    return v[: int(meses)] if meses else v


def colchao_de_regime(mat=None):
    """Fração da recuperação de regime que vem de acordo fechado em mês anterior.

    É 1 - o primeiro ponto da maturação, por construção: o que não entra no mês do
    acordo entra depois, e o "depois" de hoje é o colchão de amanhã.
    """
    return 1.0 - maturacao_de(mat, 0)[0]


def carregar_faixas(caminho, padrao):
    """Lê as faixas de um JSON. Campos de cadência ausentes herdam o contrato.

    Formato (lista de objetos):
      [{"nome":"01-30","cpfs":619,"carteira":1703233.98,"meta":93.2,"aliq":0,
        "regua":3,"wa":5,"sms":2,"email":1}, ...]

    `meta` é a recuperação OBSERVADA daquela faixa sobre a carteira DELA, em %.
    `aliq` é a alíquota da tabela do credor para a faixa, em %.
    """
    import json
    dados = json.loads(pathlib.Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(dados, list) or not dados:
        raise SystemExit(f"⛔ {caminho}: esperava uma lista não-vazia de faixas.")
    faixas = []
    for i, f in enumerate(dados, 1):
        # ⚠️ O guard recusa a AUSÊNCIA do campo, não o zero (15/09/2026). A intenção é a
        # mesma de sempre — CPFs e reais são entrada obrigatória, e derivar um do outro por
        # ticket médio uniforme assume algo que o aging costuma desmentir. Mas recusar um
        # zero DECLARADO fazia a calculadora e a bancada divergirem no mesmo dado: a tela
        # aceita (o campo fica vazio enquanto se digita) e o arquivo estourava. Agora as
        # duas aceitam, a faixa recupera ZERO e a linha sai marcada — conservador e visível,
        # em vez de generoso e silencioso.
        if "cpfs" not in f:
            raise SystemExit(
                f"⛔ faixa {i} ({f.get('nome','sem nome')}) sem CPFs. O custo escala com CPF e a "
                "variável com reais — os dois números são entrada obrigatória, e derivar um do "
                "outro por ticket médio uniforme assume algo que o aging costuma desmentir.")
        faixas.append({
            "nome": f.get("nome", f"faixa {i}"),
            "cpfs": float(f["cpfs"] or 0), "carteira": float(f.get("carteira", 0)),
            "entrada_mes": float(f.get("entrada_mes", 0) or 0),
            "carteira_entrada": (float(f["carteira_entrada"])
                                 if f.get("carteira_entrada") is not None else None),
            "meta": float(f.get("meta", 0)) / 100, "aliq": float(f.get("aliq", 0)) / 100,
            "base_meta": str(f.get("base_meta", "trabalhado")).strip().lower(),
            # item 5: faixa marcada como FORA do escopo continua na tela com os números que
            # teria, mas não dimensiona, não custa e não recupera
            "fora": bool(f.get("fora", False)),
            # item 14: política do credor. Efeito real e NÃO medido (promessa parcelada quebra
            # mais, mas temos um ponto e não uma curva) → premissa escrita, fora da conta
            "parcelas": float(f.get("parcelas", 0) or 0),
            "entrada_pct": float(f.get("entrada_pct", 0) or 0),
            # item 9 do discovery: saldo de parcelas a vencer de acordos já firmados
            "colchao": float(f.get("colchao", 0) or 0),
            # item 13 do discovery: desconto máximo no principal aceito na faixa
            "desconto": float(f.get("desconto", 0) or 0) / 100,
            # sobre QUAL valor a taxa de recuperação do item 8 foi medida
            "meta_base_valor": str(f.get("meta_base_valor", "liquida")).strip().lower(),
            "regua": float(f.get("regua", padrao["regua"])),
            "wa": float(f.get("wa", padrao["wa"])), "sms": float(f.get("sms", padrao["sms"])),
            "email": float(f.get("email", padrao["email"])),
        })
    return faixas


def rateio_de(cpfs):
    """Fração do compartilhado que ESTE contrato paga.

    ⛔ O teto de 100% não existia até 15/09/2026. `max(3%; 1% a cada 1.000 CPFs)` cresce
    sem parar: a 200.000 CPFs um contrato sozinho pagaria R$ 68.800 de um pool de
    R$ 34.400 — o dobro do que existe para ratear. Ninguém tinha cotado carteira desse
    tamanho, então o furo nunca apareceu num número publicado; mas ele mora na fórmula, e
    a fórmula é o que vai para a próxima cotação.

    O teto morde a partir de 100.000 CPFs, que é exatamente onde o rateio fecha o pool.
    """
    return min(1.0, max(P["rateio_piso"], cpfs * P["rateio_por_cpf"]))


def tributo_de(receita, base=0.0):
    """Tributo de uma receita quando a Coral já fatura `base` por mês.

    O adicional de IRPJ é da PESSOA JURÍDICA, não do contrato: um deal novo entra na
    faixa MARGINAL em que ele de fato cai. Com base=0 o contrato é avaliado sozinho,
    que é o comportamento anterior a 11/09/2026.
    """
    dentro = max(0.0, (receita + base) * P["presumido"] - P["teto_presumido"])
    antes = max(0.0, base * P["presumido"] - P["teto_presumido"])
    return receita * P["tributo"] + P["irpj_adic"] * (dentro - antes)


def preco_do_alvo(custo, uccs, alvo, base=0.0):
    """Preço por unidade que entrega exatamente `alvo` de margem sobre a receita.

    margem = 1 − tributo(R)/R − custo/R. Como o tributo tem degrau, resolve em duas
    faixas; se nenhuma das duas fecha, a solução é o próprio degrau. Com alvo=0 devolve
    o equilíbrio (reproduz os R$ 7.980 do §4 a partir do custo de R$ 6.677).
    """
    if not uccs or custo <= 0:
        return 0.0
    folga = max(0.0, P["teto_tributo"] - base)          # receita ainda na faixa base
    lo = (1 - P["tributo"]) - alvo
    hi = (1 - P["tributo"] - P["irpj_adic"] * P["presumido"]) - alvo
    r_lo = custo / lo if lo > 0 else float("inf")
    if r_lo <= folga:
        return r_lo / uccs
    r_hi = ((custo - P["irpj_adic"] * P["presumido"] * folga) / hi
            if hi > 0 else float("inf"))
    return (r_hi if r_hi >= folga else folga) / uccs


def br(v, casas=0):
    s = f"{abs(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if v < 0 else "") + "R$ " + s


def pct(v, casas=1):
    sinal = "+" if v >= 0 else "\u2212"          # menos tipográfico, não hífen
    return sinal + f"{abs(v)*100:.{casas}f}%".replace(".", ",")


def num(v, casas=0):
    """Número em pt-BR. Use SEMPRE isto — nunca .replace() numa f-string inteira,
    que corrompe os separadores de milhar dos outros números da mesma linha."""
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _normalizar_faixa(f):
    """Resolve ESTOQUE + ENTRADA MENSAL da faixa.

    A faixa curta é FLUXO: o caso entra, é trabalhado e sai no mesmo mês. Dimensionar pela foto
    subestima quem mais recupera — na Cayena a 01-30 tem 619 parados contra ~3.400 entrando por
    mês, e a foto erra por 5×, para baixo, justamente na faixa onde mora 98,6% da recuperação.

    Faixa sem `entrada_mes` se comporta exatamente como antes (trabalhado = estoque).

    ⛔ O R$ da entrada NÃO é derivado do ticket do estoque. Quarenta linhas acima o carregador já
    recusa derivar CPFs de reais por ticket médio uniforme; o inverso tem o mesmo defeito e morde
    mais forte, porque os CPFs parados numa faixa são justamente os que NÃO pagaram. Derivando na
    Cayena, a 01-30 passava a "recuperar" R$ 8,7M/mês numa carteira de R$ 22,6M — o credor giraria
    o livro inteiro a cada 2,6 meses. Sem `carteira_entrada` informada, a entrada entra no CUSTO
    (os CPFs são trabalhados de verdade) e fica FORA da recuperação, declarada como lacuna. O
    preço que sai daí é teto: custo cheio contra receita só do que foi medido.

    ⛔ `base_meta` declara **sobre qual denominador a meta de recuperação foi medida** —
    `estoque` | `entrada` | `trabalhado` (default). Sem isso o número do credor entra sobre o que
    o simulador tiver à mão, e uma taxa medida sobre o que vence no mês aplicada sobre
    estoque+entrada infla a recuperação em múltiplos. Na Cayena a 01-30 recuperava R$ 10,3M numa
    carteira de R$ 22,6M porque a taxa de 93,2% (fatia do que venceu) foi lida como se fosse taxa
    sobre tudo que a faixa carrega.
    """
    cpfs = float(f["cpfs"])
    ent = float(f.get("entrada_mes", 0) or 0)
    cart = float(f.get("carteira", 0) or 0)
    ce = f.get("carteira_entrada")
    lacuna = ce is None and ent > 0
    ce = 0.0 if ce is None else float(ce)
    base = str(f.get("base_meta", "trabalhado")).strip().lower()
    if base not in ("estoque", "entrada", "trabalhado"):
        raise SystemExit(f"⛔ faixa {f.get('nome','sem nome')}: base_meta inválida ({base!r}). "
                         "Use estoque | entrada | trabalhado.")
    carteira_meta = {"estoque": cart, "entrada": ce, "trabalhado": cart + ce}[base]
    # ⛔ A taxa do credor pode já vir LÍQUIDA (R$ recebido ÷ carteira, desconto dentro) ou de
    # FACE (valor negociado, antes do abatimento). Aplicar (1 − desconto) sobre uma taxa já
    # líquida desconta DUAS vezes; não aplicar sobre uma de face superestima pelo tamanho do
    # desconto. Numa faixa de 40% isso é 40% de erro nos dois sentidos — por isso a faixa
    # DECLARA, do mesmo jeito que `base_meta` declara o denominador.
    val = str(f.get("meta_base_valor", "liquida")).strip().lower()
    if val not in ("liquida", "face"):
        raise SystemExit(f"⛔ faixa {f.get('nome','sem nome')}: meta_base_valor inválida "
                         f"({val!r}). Use liquida | face.")
    desc = float(f.get("desconto", 0) or 0)
    if not 0 <= desc < 1:
        raise SystemExit(f"⛔ faixa {f.get('nome','sem nome')}: desconto fora de 0-100% ({desc}).")
    return {**f, "entrada_mes": ent, "carteira_entrada": ce, "base_meta": base,
            "trabalhado": cpfs + ent, "carteira_trab": cart + ce,
            "carteira_meta": carteira_meta, "carteira_entrada_lacuna": lacuna,
            "desconto": desc, "meta_base_valor": val,
            "fator_desconto": (1 - desc) if val == "face" else 1.0}


def resolver_realizacao(regua, cenario=None, override=None):
    """Régua REALIZADA de um bloco, sob o cenário da banda.

    ⛔ A realização depende da RÉGUA do bloco (93% na 2, 68% na 10), então tem de ser
    resolvida por bloco — não achatada na régua do contrato. Uma faixa que corre régua 4
    dentro de um contrato de régua 10 realiza 87%, não 68%.
    O cenário `teto` é a exceção legítima: 100% é 100% em qualquer régua.
    """
    if override is not None:
        return override                    # --realizacao: override plano, deliberado
    if cenario == "teto":
        return 1.0
    r = realizacao_estimada(regua)
    return r * 0.90 if cenario == "medida-10%" else r


def _acionar(cpfs, regua, telefones, wa, sms, email, realizacao=None, cenario=None):
    """Acionamento de um bloco de CPFs sob uma régua e uma cadência."""
    tent_c = regua * telefones
    r = resolver_realizacao(regua, cenario, realizacao)
    tent_e = tent_c * r
    return dict(
        tent_contratada=tent_c, realizacao=r, tent_esperada=tent_e,
        telecom=cpfs * P["coef_telecom"] * tent_e,
        msg=cpfs * (wa * P["wa"] + sms * P["sms"] + email * P["email"]),
        crm=cpfs * P["crm_assento"],
    )


# ── ficha de entrada ─────────────────────────────────────────────────────────
# O VEREDITO de cada entrada — informada, assumida por nós, ou faltando — sai do motor,
# não de quem renderiza. A tela e a planilha só escolhem palavras; o julgamento é um só,
# e por isso o harness consegue compará-lo. Escrito duas vezes, ele divergiria em
# silêncio, e uma planilha que diz "tudo informado" sobre uma cotação furada é pior que
# uma planilha sem ficha.
FICHA_CHAVES = ("cpfs", "faixas", "entrada_mes", "base_meta", "carteira_entrada",
                "regua", "telefones", "cadencia", "carteira_faixa", "meta", "aliq",
                "ancora", "transbordo", "compartilhamento", "desconto", "colchao",
                "escopo", "serie", "parcelamento", "produtos", "maturacao")


def _ficha(cpfs, regua, telefones, wa, sms, email, lf, ancora_propria, transbordo,
           entrada_sem_valor, compart_modelo="exclusivo", captura=1.0,
           colchao_ativo=False, lf_fora=(), serie_stat=None, produtos="",
           maturacao_propria=False):
    aging = bool(lf)
    ent = sum(l["entrada_mes"] for l in lf)
    na = lambda cond, v: v if cond else "na"
    return {
        "cpfs": "ok" if cpfs > 0 else "falta",
        "faixas": "ok" if aging and any(l["cpfs"] > 0 for l in lf) else "falta",
        "entrada_mes": "ok" if ent > 0 else "assumido",
        # com fluxo e meta na faixa, a base default ('trabalhado') é uma escolha NOSSA
        "base_meta": na(ent > 0, "assumido" if any(
            l["entrada_mes"] > 0 and l["meta"] > 0 and l["base_meta"] == "trabalhado"
            for l in lf) else "ok"),
        "carteira_entrada": na(ent > 0, "falta" if entrada_sem_valor else "ok"),
        "regua": "ok" if regua > 0 else "falta",
        "telefones": "ok" if telefones != 1.0 else "assumido",
        "cadencia": "ok" if (wa + sms + email) > 0 else "assumido",
        "carteira_faixa": na(aging, "falta" if any(l["carteira"] <= 0 for l in lf) else "ok"),
        "meta": na(aging, "ok" if any(l["meta"] > 0 for l in lf) else "falta"),
        "aliq": na(aging, "ok" if any(l["aliq"] > 0 for l in lf) else "falta"),
        "ancora": "ok" if ancora_propria else "assumido",
        "transbordo": "ok" if transbordo > 0 else "assumido",
        # declarar "aberto"/"rotativo" e deixar a captura em 100% é premissa otimista:
        # o custo é integral e a recuperação seria toda nossa
        "compartilhamento": ("assumido" if compart_modelo == "exclusivo"
                             else "falta" if captura >= 1 else "ok"),
        # a política de desconto é do credor; sem ela a proposta escreve uma premissa a menos
        "desconto": na(aging, "ok" if any(l["desconto"] > 0 for l in lf) else "assumido"),
        # saldo informado sem prazo/eficiência não vira recuperação do mês: fica declarado e
        # FORA da conta, que é o não-destrutivo — mas a ficha não deixa passar como resolvido
        "colchao": na(aging, "assumido" if not any(l["colchao"] > 0 for l in lf)
                      else "ok" if colchao_ativo else "falta"),
        # escopo é DECISÃO: sem faixa marcada, a cotação cobre a carteira inteira
        "escopo": na(aging, "ok" if lf_fora else "assumido"),
        "serie": "ok" if serie_stat and serie_stat["n"] >= 3 else "assumido",
        "parcelamento": na(aging, "ok" if any(l["parcelas"] > 0 for l in lf) else "assumido"),
        "produtos": "ok" if produtos.strip() else "assumido",
        # a curva é MEDIDA, mas na NOSSA operação: PF, educacional, voz. Transplantá-la
        # para outro credor é premissa, não medição — por isso "assumido" e não "ok"
        "maturacao": "ok" if maturacao_propria else "assumido",
    }


def _serie(txt):
    """Lê a série de entradas do CLI — vírgula ou ponto e vírgula, vazio vira nada."""
    if not txt:
        return None
    return [float(x.strip().replace(".", "").replace(",", "."))
            for x in txt.replace(";", ",").split(",") if x.strip()]


def calcular(cpfs, regua, wa, sms, email, telefones=1.0, realizacao=None, preco=None,
             alvo=None, receita_base=0.0, setup=0.0, setup_meses=12, pas=0, pa_custo=None,
             faixas=None, elast=None, ancora=None, cenario=None,
             compart_modelo="exclusivo", captura=1.0, modalidade="hibrido",
             colchao_meses=0, colchao_efic=0.0, produtos="", entradas=None,
             maturacao=None):
    pa_custo = P["pa_humana"] if pa_custo is None else pa_custo
    elast = elast or ELAST
    # item 7 do discovery. Em mar aberto discamos a base INTEIRA (custo integral) e a
    # recuperação é disputada — só a nossa variável encolhe.
    compart_modelo = str(compart_modelo or "exclusivo").strip().lower()
    if compart_modelo not in COMPART_MODELOS:
        raise SystemExit(f"⛔ compart_modelo inválido ({compart_modelo!r}). "
                         f"Use {' | '.join(COMPART_MODELOS)}.")
    captura = 1.0 if compart_modelo == "exclusivo" else float(captura)
    if not 0 < captura <= 1:
        raise SystemExit(f"⛔ captura fora de 0-100% ({captura}).")
    # itens 9 e 10 do discovery. O colchão só entra na conta com as DUAS pontas: sem prazo
    # e sem eficiência não há como converter saldo em recuperação do mês, e inventar
    # qualquer uma delas é a mesma classe de erro do `base_meta`. Sem elas, o colchão fica
    # DECLARADO e FORA — a conta roda exatamente como antes.
    colchao_meses = float(colchao_meses or 0)
    colchao_efic = float(colchao_efic or 0)
    if colchao_meses < 0 or not 0 <= colchao_efic <= 1:
        raise SystemExit(f"⛔ colchão inválido (meses={colchao_meses}, efic={colchao_efic}).")
    colchao_ativo = colchao_meses > 0 and colchao_efic > 0
    # ── colchão PRÓPRIO: derivado da cadeia, não digitado ────────────────────────────
    # O colchão herdado acima é o que a carteira TRAZ: acordo fechado por outra
    # assessoria, que chega discando ou não. Este aqui é o outro, e ele nunca esteve na
    # conta: o que NÓS fechamos e que continua pingando nos meses seguintes.
    #
    # Ele não muda a recuperação de REGIME (o mês estável recebe parcela de k safras e
    # entrega o mesmo total), e por isso a conta estática não se mexe. O que ele muda é o
    # CAMINHO até o regime — e é lá, na projeção de 12 meses, que a diferença aparece:
    # o custo é integral desde o mês 1 e a receita chega em 41,6%.
    #
    # ⚠️ E a regra da variável vira ao contrário do herdado. Sobre acordo de terceiro a
    # Coral não cobra; sobre o que ela mesma fechou, cobra — a parcela de outubro do
    # acordo que fechamos em maio é recuperação NOSSA, só que atrasada.
    mat = maturacao_de(maturacao, 0)
    colchao_proprio_frac = 1.0 - mat[0]
    # item 6: a conta precisa de UM número por mês, o discovery pede SEIS. A média vira a
    # entrada; a série entrega o que a média esconde — dispersão e tendência.
    serie = [float(x) for x in (entradas or []) if x is not None]
    serie_stat = None
    if serie:
        meia = len(serie) // 2
        ini = sum(serie[:meia]) / meia if meia else 0.0
        fim = sum(serie[len(serie) - meia:]) / meia if meia else 0.0
        serie_stat = dict(
            n=len(serie), media=sum(serie) / len(serie), minimo=min(serie), maximo=max(serie),
            # dispersão sobre a média: é o que diz se dimensionar pela média estoura no pico
            disp=(max(serie) - min(serie)) / (sum(serie) / len(serie)) if sum(serie) else 0.0,
            tendencia=(fim / ini - 1) if ini else 0.0)

    todas = [_normalizar_faixa(f) for f in (faixas or [])]
    if faixas:
        # ⚠️ a conferência de coerência do cadastro usa TODAS as faixas (escopo é decisão,
        # divergência de soma é erro de digitação); a CONTA usa só as de dentro
        faixas = [f for f in todas if not f["fora"]]
        # o TRABALHADO (estoque + entrada do mês) é a verdade da carteira, não a foto
        cpfs = sum(f["trabalhado"] for f in faixas)
    u = ceil(cpfs / P["tam_ucc"])
    # o discador capeia POR LINHA → telefones/CPF multiplicam a tentativa efetiva
    tent_contratada = regua * telefones
    r = resolver_realizacao(regua, cenario, realizacao)
    tent_esperada = tent_contratada * r

    setup_mes = (setup / setup_meses) if setup_meses else 0.0
    transbordo = pas * pa_custo

    # ── faixas: cada uma com a sua régua e cadência; o corte é medido contra a CHEIA ──
    lf = []
    for f in (faixas or []):
        a = _acionar(f["trabalhado"], f["regua"], telefones, f["wa"], f["sms"], f["email"],
                     realizacao, cenario)
        cheia = _acionar(f["trabalhado"], f["regua"], telefones, wa, sms, email,
                         realizacao, cenario)
        perda_frac = (max(0.0, wa - f["wa"]) * elast["wa"]
                      + max(0.0, sms - f["sms"]) * elast["sms"]
                      + max(0.0, email - f["email"]) * elast["email"])
        # ⛔ Faixa com saldo e ZERO CPFs não recupera nada (15/09/2026). A conta antiga
        # multiplicava carteira × meta sem olhar quantos CPFs há para trabalhar, e uma
        # linha com R$ e nenhum CPF produzia recuperação sobre custo zero — R$ 720.000 no
        # caso que a auditoria testou. Não é faixa barata: é entrada inconsistente (ou o
        # CPF está noutra linha, ou o saldo foi digitado errado), e a conta tem de dizer
        # isso em vez de devolver o melhor número possível.
        sem_cpf = f["trabalhado"] <= 0 and f["carteira_meta"] > 0
        rec_base = (0.0 if sem_cpf
                    else f["carteira_meta"] * f["meta"] * f["fator_desconto"])
        # o colchão chega discando ou não: a perda de cadência e a escada de régua só
        # mordem o ACIONÁVEL. Cortar WhatsApp não atrasa parcela de acordo já firmado.
        # ⛔ O colchao so' existe aqui quando ele MUDA a conta, e isso acontece num caso
        # so': o HERDADO, acordo de OUTRA assessoria, que chega cheio e fica fora da nossa
        # variavel. O derivado — safra NOSSA anterior — e' recuperacao nossa e entra na
        # base igual ao acordo novo, entao parti-lo em dois nao alterava custo, preco,
        # margem nem variavel: era descricao vestida de conta. O TEMPO continua tratado
        # onde ele importa: a curva de maturacao, na projecao de 12 meses.
        colchao_bruto = (f["colchao"] / colchao_meses * colchao_efic) if colchao_ativo else 0.0
        colchao_mes = min(colchao_bruto, rec_base)
        acionavel = rec_base - colchao_mes
        acion = a["telecom"] + a["msg"] + a["crm"]
        lf.append(dict(
            **f, **{k: a[k] for k in ("telecom", "msg", "crm", "tent_esperada")},
            acionamento=acion, rec_base=rec_base, perda_frac=perda_frac, sem_cpf=sem_cpf,
            colchao_mes=colchao_mes, colchao_excede=colchao_bruto > rec_base + 1e-9,
            acionavel=acionavel, recuperado_novo=acionavel * (1 - perda_frac),
            perda=acionavel * perda_frac,
            recuperado=colchao_mes + acionavel * (1 - perda_frac),
            # do que NÓS recuperamos no mês, quanto já estava contratado em mês anterior.
            # Não sai do total (regime é regime) — serve para ler a cadência: cortar canal
            # hoje só morde a parte que ainda depende de fechar acordo novo.
            proprio_contratado=acionavel * (1 - perda_frac) * colchao_proprio_frac,
            economia=(cheia["telecom"] + cheia["msg"] + cheia["crm"]) - acion,
        ))
    # o que as faixas FORA do escopo carregam — para o antes-e-depois aparecer na mesma tela
    # ⚠️ só o ACIONAMENTO: capacidade é degrau do contrato inteiro, e dizer quanto a faixa
    # "custaria" em capacidade exigiria recontar as unidades — quem quer o número exato
    # desmarca a faixa e lê a conta inteira
    lf_fora = []
    for f in (x for x in todas if x["fora"]):
        af = _acionar(f["trabalhado"], f["regua"], telefones, f["wa"], f["sms"], f["email"],
                      realizacao, cenario)
        lf_fora.append(dict(
            f, recuperado_potencial=(0.0 if f["trabalhado"] <= 0
                                     else f["carteira_meta"] * f["meta"] * f["fator_desconto"]),
            acionamento_potencial=af["telecom"] + af["msg"] + af["crm"]))
    linhas = [
        ("Bot de voz",                 u * P["bot"],                          "Capacidade"),
        ("Rateio do compartilhado",    rateio_de(cpfs) * P["compart"],        "Capacidade"),
    ]
    if setup_mes:
        linhas.append(("Setup amortizado", setup_mes, "Capacidade"))
    if transbordo:
        linhas.append(("Transbordo humano", transbordo, "Capacidade"))
    linhas += [
        ("WhatsApp",                   cpfs * wa * P["wa"],                   "Acionamento"),
        ("SMS",                        cpfs * sms * P["sms"],                 "Acionamento"),
        ("E-mail",                     cpfs * email * P["email"],             "Acionamento"),
        ("CRM — assento",              cpfs * P["crm_assento"],               "Acionamento"),
    ]
    tel_med = (sum(l["telecom"] for l in lf) if lf
               else cpfs * P["coef_telecom"] * tent_esperada)
    if lf:   # com faixas, mensageria e CRM também saem linha a linha
        for i, (nome, _, nat) in enumerate(linhas):
            if nome == "WhatsApp":  linhas[i] = (nome, sum(l["trabalhado"] * l["wa"] for l in lf) * P["wa"], nat)
            if nome == "SMS":       linhas[i] = (nome, sum(l["trabalhado"] * l["sms"] for l in lf) * P["sms"], nat)
            if nome == "E-mail":    linhas[i] = (nome, sum(l["trabalhado"] * l["email"] for l in lf) * P["email"], nat)

    base = sum(v for _, v, _ in linhas)
    custo_medido = base + tel_med

    capacidade = sum(v for _, v, n in linhas if n == "Capacidade")
    for l in lf:
        l["capacidade"] = capacidade * l["trabalhado"] / cpfs if cpfs else 0.0
        l["custo"] = l["capacidade"] + l["acionamento"]
        l["por_real"] = (l["custo"] / l["recuperado"]) if l["recuperado"] > 0 else None
        # o custo é INTEGRAL (discamos a base toda); só a recuperação é disputada
        # a NOVA é o que depende de nós; a variável cobra sobre ela, não sobre acordo alheio
        # O colchao aqui e' sempre HERDADO — acordo de outra assessoria — e por isso fica
        # fora da base: a assessoria e' paga pelo que ELA recupera.
        l["recuperado_coral"] = l["recuperado_novo"] * captura
        l["por_real_novo"] = (l["custo"] / l["recuperado_novo"]) if l["recuperado_novo"] > 0 else None
        l["variavel"] = l["recuperado_coral"] * l["aliq"]

    # ── a VARIÁVEL entra na conta (15/09/2026) ───────────────────────────────────────
    # Duas correções da auditoria, e as duas saem do mesmo lugar: o que o credor paga não
    # é o fixo, é a FATURA.
    #
    # (1) A âncora e o teto de R$ 0,30 por R$ 1 recuperado são os dois guardas contra
    #     preço fora de mercado, e ambos conferiam só o fixo. No contrato de referência o
    #     preço de R$ 8.464 passava folgado na âncora de R$ 12.000 enquanto o efetivo por
    #     unidade era R$ 22.864 — 90% acima. Guarda que confere a metade menor da conta
    #     não guarda nada.
    # (2) O degrau de IRPJ é da PJ e a receita que cruza os R$ 62.500 inclui o success
    #     fee. Cotando o fixo como se ele entrasse sozinho, a carga saía 17,93% onde a
    #     real é 19,53% — R$ 31.751/ano de tributo subestimado a 30.000 CPFs, e o preço
    #     2,6% abaixo do que deveria.
    #
    # `modalidade` declara o arranjo: no HÍBRIDO ADITIVO (§6.6, o modelo vigente) o credor
    # paga fixo + variável, então a variável ocupa a faixa tributária ANTES do fixo e conta
    # no que ele desembolsa. No VALOR FIXO ela não existe, e a conta volta a ser a antiga.
    # ⚠️ A variável aqui é a da META. O gatilho move ±15% a alíquota, e é o `hibrido()` que
    # abre os cenários — o preço se apoia na meta, não no melhor mês.
    modalidade = str(modalidade or "hibrido").strip().lower()
    if modalidade not in ("hibrido", "fixo"):
        raise SystemExit(f"⛔ modalidade inválida ({modalidade!r}). Use hibrido | fixo.")
    var_total = sum(l["variavel"] for l in lf)
    var_fatura = var_total if modalidade == "hibrido" else 0.0
    base_trib = receita_base + var_fatura
    if alvo is None:
        preco = preco or P["preco_ucc"]
    else:
        preco = preco_do_alvo(custo_medido, u, alvo, base_trib)
    receita = u * preco
    tributo = tributo_de(receita, base_trib)
    liq = receita - tributo
    fatura = receita + var_fatura
    efetivo = fatura / u if u else 0.0
    return dict(
        uccs=u, cpfs=cpfs, preco=preco, receita=receita, liquida=liq,
        linhas=linhas, tel_med=tel_med,
        setup_mes=setup_mes, transbordo=transbordo, capacidade=capacidade,
        faixas=lf, elast=elast,
        carteira=sum(l["carteira_trab"] for l in lf),
        estoque=sum(l["cpfs"] for l in lf), entrada_mes=sum(l["entrada_mes"] for l in lf),
        entrada_sem_valor=[l["nome"] for l in lf if l.get("carteira_entrada_lacuna")],
        recuperado=sum(l["recuperado"] for l in lf),
        recuperado_coral=sum(l["recuperado_coral"] for l in lf),
        recuperado_novo=sum(l["recuperado_novo"] for l in lf),
        colchao_mes=sum(l["colchao_mes"] for l in lf),
        colchao_excede=[l["nome"] for l in lf if l["colchao_excede"]],
        faixas_sem_cpf=[l["nome"] for l in lf if l["sem_cpf"]],
        colchao_meses=colchao_meses, colchao_efic=colchao_efic, colchao_ativo=colchao_ativo,
        # a meta que a cadeia medida implica, para conferir contra a que o credor informou
        meta_derivada={f["nome"]: meta_derivada(f["nome"]) for f in lf},
        maturacao=mat, colchao_proprio_frac=colchao_proprio_frac,
        colchao_proprio=sum(l["proprio_contratado"] for l in lf),
        maturacao_propria=maturacao is not None,
        faixas_fora=lf_fora, produtos=(produtos or "").strip(), serie=serie, serie_stat=serie_stat,
        cpfs_fora=sum(f["trabalhado"] for f in lf_fora),
        carteira_fora=sum(f["carteira_trab"] for f in lf_fora),
        recuperado_fora=sum(f["recuperado_potencial"] for f in lf_fora),
        acionamento_fora=sum(f["acionamento_potencial"] for f in lf_fora),
        # a soma da série × o que foi digitado por faixa: divergência grande é entrada
        # inconsistente, não refinamento
        entrada_divergente=(serie_stat is not None
                            and sum(l["entrada_mes"] for l in lf) > 0
                            and abs(sum(l["entrada_mes"] for l in lf) / serie_stat["media"] - 1) > 0.20
                            if serie_stat and serie_stat["media"] else False),
        compart_modelo=compart_modelo, captura=captura,
        rec_base_total=sum(l["rec_base"] for l in lf),
        # ── o que a curva de maturação espalha no tempo é o valor NEGOCIADO ──────────────
        # A alíquota do credor incide sobre o que foi acordado, não sobre a face: uma faixa
        # que fecha com 40% de desconto entrega 60% do R$ e remunera sobre esses 60%. O
        # `fator_desconto` já entra no `rec_base`, então a conta estava certa — o que
        # faltava era o número aparecer ao lado da curva, que é onde alguém lê "R$ por mês"
        # e precisa saber de qual R$ se trata.
        rec_face_total=sum(0.0 if l["sem_cpf"] else l["carteira_meta"] * l["meta"] for l in lf),
        desconto_efetivo=(1 - (sum(l["rec_base"] for l in lf)
                               / sum(0.0 if l["sem_cpf"] else l["carteira_meta"] * l["meta"]
                                     for l in lf)))
                          if sum(0.0 if l["sem_cpf"] else l["carteira_meta"] * l["meta"]
                                 for l in lf) else 0.0,
        faixas_desconto_face=[l["nome"] for l in lf
                              if l["desconto"] > 0 and l["meta_base_valor"] == "face"],
        # desconto informado que NÃO abate nada — a taxa já era líquida. Não é erro, mas
        # quem informou 40% e vê a recuperação intacta merece saber por quê.
        faixas_desconto_inerte=[l["nome"] for l in lf
                                if l["desconto"] > 0 and l["meta_base_valor"] != "face"],
        perda_total=sum(l["perda"] for l in lf),
        economia_total=sum(l["economia"] for l in lf),
        variavel=sum(l["variavel"] for l in lf),
        tributo=tributo, trib_pct=(tributo / receita if receita else P["tributo"]),
        receita_base=receita_base, alvo=alvo,
        custo_medido=custo_medido,
        margem_medido=(liq - custo_medido) / receita if receita else 0.0,
        equilibrio=preco_do_alvo(custo_medido, u, 0.0, base_trib),
        modalidade=modalidade, var_fatura=var_fatura, base_trib=base_trib,
        fatura=fatura, efetivo=efetivo,
        rateio_frac=rateio_de(cpfs),
        rateio_no_teto=cpfs * P["rateio_por_cpf"] > 1.0,
        # o que o credor paga HOJE é a âncora que vale; sem isso, a genérica
        ancora=(ancora if ancora else P["ancora"]), ancora_propria=bool(ancora),
        **_restricao(preco, u, (ancora if ancora else P["ancora"]),
                     sum(l["recuperado"] for l in lf),
                     sum(l["recuperado_novo"] for l in lf), var_fatura),
        canais=canais_necessarios(cpfs, tent_esperada),
        regua_extrapolada=regua_fora_da_medida(regua),
        tent_contratada=tent_contratada, tent_esperada=tent_esperada, realizacao=r,
        # entradas ecoadas: a proposta escreve as premissas, e elas têm de vir do mesmo
        # objeto que gerou o preço — reescrevê-las à mão é como a premissa e a conta divergem
        tel=telefones, cad=dict(wa=wa, sms=sms, email=email), regua=regua,
        ficha=_ficha(cpfs, regua, telefones, wa, sms, email, lf,
                     bool(ancora), transbordo,
                     [l["nome"] for l in lf if l.get("carteira_entrada_lacuna")],
                     compart_modelo, captura, colchao_ativo, lf_fora, serie_stat,
                     produtos or "", maturacao is not None),
        # ── FIX 5 · a OCUPAÇÃO e o DEGRAU voltam para a superfície (15/09/2026) ────────
        # Ocupação baixa não é prejuízo: com preço travado a margem SOBE (§6.9 f). O risco
        # é o DEGRAU — um CPF a mais depois da unidade cheia abre outra unidade inteira.
        # No contrato de referência, sair de 5.000 para 5.001 CPFs custa R$ 1.022 e cobra
        # R$ 8.000: é a cláusula mais cara do contrato, e ela tinha saído da tela na
        # reconstrução. Por isso a conta devolve quantos CPFs faltam para o degrau e o que
        # ele move dos dois lados — é o número que a minuta precisa (unidades com aviso
        # prévio, nunca ocupação).
        ocupacao=cpfs / (u * P["tam_ucc"]) if u else 0.0,
        degrau_cpfs=max(0, u * P["tam_ucc"] - cpfs),
        degrau_receita=preco,
        degrau_custo=(P["bot"]
                      + ((custo_medido - capacidade) / cpfs if cpfs else 0.0)
                      + (P["rateio_por_cpf"] * P["compart"]
                         if P["rateio_piso"] < cpfs * P["rateio_por_cpf"] < 1.0 else 0.0)),
    )


# ── voz: o que a tentativa a mais faz com a recuperação ──────────────────────
# O corte de CADÊNCIA (WhatsApp/SMS/e-mail) já tinha elasticidade; a RÉGUA não tinha
# nenhuma, então discar mais só aparecia como despesa e discar menos só como economia.
#
#   gamma — retorno da tentativa a mais. 1,0 = a recuperação acompanha a tentativa EFETIVA
#           na proporção. MEDIDO no Ouro: o R$/acordo da faixa cortada é plano de 1 a 10
#           tentativas (79,17 cortando após a 1ª × 79,09 cortando só a 10ª), e o ROI por
#           faixa cortada replicou o mesmo achado por outra medida. gamma < 1 é o que cria
#           ponto de virada; medimos que não há, até 10.
#
# ⛔ O PISO ESPONTÂNEO SAIU DA CONTA (default 0, 15/09/2026 — decisão do Head of Collection).
# Ele era 44,4%, MEDIDO em jul/2026: dos R$ 17,15M recuperados na Receita Garantida, 44,4%
# foram espontâneos. Só que esse número é da carteira INTEIRA do credor, e a conta da UCC
# roda sobre a carteira DISTRIBUÍDA — que já chega sem o espontâneo, porque o credor retira
# o que recupera sozinho antes de terceirizar. Aplicar o piso aqui contava o espontâneo duas
# vezes, e sempre para o mesmo lado: inflava a recuperação que a discagem não precisa
# produzir, fazendo régua baixa parecer barata.
#
# O campo continua editável e existe para a carteira que NÃO foi filtrada — se o credor
# manda a base inteira, parte dela paga sem toque e o piso volta a valer. Quem informar um
# piso aqui está afirmando que a distribuída ainda contém espontâneo, e isso vai para a
# proposta como premissa.
#
# ⚠️ Com piso 0 e gamma 1 a recuperação é PROPORCIONAL à tentativa efetiva: metade da régua,
# metade da recuperação. É mais agressivo do que era, e é a leitura correta de uma carteira
# em que tudo que entra depende de acionamento.
# ⚠️ O retorno decrescente que ESTE modelo tem vem da REALIZAÇÃO (93% na régua 2, 68% na 10):
# subir a régua contratada compra cada vez menos tentativa efetiva.
# ⛔ LACUNA: régua maior exige mais CANAIS, e o de-para bot ↔ canal não existe. A escada
# cobra o telecom da tentativa a mais e NÃO cobra capacidade adicional.
VOZ = {"piso": 0.0, "gamma": 1.0}


def escada_regua(base, passos=2, minimo=0.5):
    """Réguas vizinhas à cadastrada — 'e se eu discar uma a mais, uma a menos'."""
    base = float(base)
    if base <= 0:
        return []
    vals = [round(base + d, 2) for d in range(-passos, passos + 1)]
    vals = [v for v in vals if v >= minimo]
    d = passos + 1
    while len(vals) < 2 * passos + 1:          # base baixa sobe a escada em vez de
        vals.append(round(base + d, 2))        # inventar régua negativa
        d += 1
    return sorted(set(vals))


def sensibilidade_regua(reguas=None, voz=None, **kw):
    """Escada de régua: quanto custa e quanto recupera discar mais ou menos.

    Roda com o PREÇO DA BASE em todas as linhas. A pergunta é gastar mais dentro de um
    preço já acordado, não recotar a cada tentativa — devolver um preço por degrau
    convidaria a escolher o degrau confortável, o mesmo motivo pelo qual a banda cobra um
    preço só. A coluna `preco_alvo` fica ao lado para quem ainda está cotando.

    Faixa que corre a régua do contrato ACOMPANHA a escada; faixa deliberadamente cortada
    fica onde está — a escada pergunta pela régua do contrato, não desfaz a decisão de
    cortar uma faixa.
    """
    voz = {**VOZ, **(voz or {})}
    piso, gamma = float(voz["piso"]), float(voz["gamma"])
    captura = (1.0 if str(kw.get("compart_modelo") or "exclusivo").strip().lower() == "exclusivo"
               else float(kw.get("captura", 1.0)))
    regua_base = float(kw.get("regua") or 0)
    if regua_base <= 0:
        return []
    base = calcular(**kw)
    preco_base, u = base["preco"], base["uccs"]
    alvo, rb = kw.get("alvo"), kw.get("receita_base", 0.0)
    modalidade = str(kw.get("modalidade") or "hibrido").strip().lower()
    if reguas is None:
        reguas = escada_regua(regua_base)

    def rodar(rg):
        k2 = dict(kw, regua=rg, preco=preco_base, alvo=None)
        if k2.get("faixas"):
            k2["faixas"] = [dict(f, regua=(rg if abs(float(f["regua"]) - regua_base) < 1e-9
                                           else f["regua"]))
                            for f in kw["faixas"]]
        c = calcular(**k2)
        rec = var = 0.0
        for l0, l in zip(base["faixas"], c["faixas"]):
            t0 = l0["tent_esperada"]
            mult = (l["tent_esperada"] / t0) if t0 else 1.0
            # discar mais não antecipa parcela contratada: o colchão é PISO da escada,
            # ao lado do piso espontâneo, e só a recuperação NOVA se move com a régua
            nova = l0["recuperado_novo"] * (piso + (1 - piso) * mult ** gamma)
            rec += l0["colchao_mes"] + nova
            var += nova * captura * l["aliq"]
        receita = u * preco_base
        liq = receita - tributo_de(receita, rb)
        liq_var = (receita + var) - tributo_de(receita + var, rb)
        # a escada repetia os mesmos dois furos da conta principal (auditoria 15/09): o
        # preço do alvo nascia como se o fixo entrasse sozinho na faixa tributária, e o
        # teto da régua comparava esse fixo com a âncora. Aqui a régua move a variável
        # degrau a degrau, então o erro cresce junto com a discagem.
        var_fat = var if modalidade == "hibrido" else 0.0
        p_alvo = (preco_do_alvo(c["custo_medido"], u, alvo, rb + var_fat)
                  if alvo is not None else None)
        return dict(
            regua=rg, realizacao=c["realizacao"], tent_esperada=c["tent_esperada"],
            custo=c["custo_medido"], telecom=c["tel_med"],
            recuperado=rec, variavel=var,
            resultado=liq - c["custo_medido"],
            resultado_var=liq_var - c["custo_medido"],
            preco_alvo=p_alvo,
            efetivo_alvo=(p_alvo + var_fat / u) if (p_alvo is not None and u) else None,
        )

    ref = rodar(regua_base)
    carteira = base["carteira"]
    linhas = []
    for rg in reguas:
        l = rodar(rg)
        l["base"] = abs(rg - regua_base) < 1e-9
        l["d_custo"] = l["custo"] - ref["custo"]
        l["d_recuperado"] = l["recuperado"] - ref["recuperado"]
        l["d_resultado_var"] = l["resultado_var"] - ref["resultado_var"]
        # R$ que o credor recupera a mais por R$ 1 a mais de discagem. Sob gamma = 1 é
        # constante ao longo da escada — é o achado, não um arredondamento.
        l["por_real"] = (l["d_recuperado"] / l["d_custo"]) if abs(l["d_custo"]) > 1e-9 else None
        # extrapolar longe da base produz recuperação maior que a carteira — a escada diz
        # quando saiu do plausível em vez de imprimir o número com cara de resultado
        l["acima_da_carteira"] = bool(carteira > 0 and l["recuperado"] > carteira)
        linhas.append(l)
    return linhas


def veredito_regua(voz=None, reguas=None, **kw):
    """Direção, contrapartida e LIMITE da régua — o que a escada conclui, calculado.

    ⛔ **Não existe ponto ótimo interior.** Sob gamma = 1 (o medido) a razão
    `Δrecuperação ÷ Δcusto` é CONSTANTE ao longo da escada — conferido: 598,65 nos quatro
    degraus da carteira de exemplo. Função monótona não tem máximo no meio: o ótimo é
    sempre um CANTO, e qual canto sai de uma comparação só. Pedir para a pessoa deslizar a
    régua procurando o ponto de virada é pedir para procurar o que não está lá.

    Três coisas criariam um ótimo interior, e nenhuma está medida:
      · gamma < 1 forte o bastante para a razão cruzar o ponto de equilíbrio DENTRO da faixa
        (a 0,8 e a 0,5 ela cai, mas segue ordens de grandeza acima de 1 nesta carteira);
      · custo de CANAL em degraus — mais régua pede mais canal, e o de-para bot ↔ canal não
        existe (§6.3 do modelo);
      · dano por sobre-discagem (reclamação, opt-out, reputação do número) — fora do modelo.

    Então o que se calcula não é o ótimo: é a DIREÇÃO e o que a TRAVA. O limite sai por
    bisseção sobre a régua — no modo com alvo, a maior régua cujo preço ainda cabe na
    âncora; com preço fixado, a maior régua que ainda não põe o contrato no negativo.
    """
    deg = sensibilidade_regua(voz=voz, reguas=reguas, **kw)
    if not deg:
        return None
    base = next((l for l in deg if l["base"]), deg[0])
    passo = next((l for l in deg if l["regua"] > base["regua"]), None)
    tem_rec = any(l["recuperado"] > 0 for l in deg)
    alvo = kw.get("alvo")
    ancora = kw.get("ancora") or P["ancora"]

    def cabe(rg):
        l = sensibilidade_regua(reguas=[rg], voz=voz, **kw)[0]
        # ⛔ compara o EFETIVO com a âncora (15/09): o credor desembolsa fixo + variável, e
        # subir a régua move os dois. Contra o fixo sozinho o veredito autorizava régua que
        # a fatura não comporta.
        return (l["efetivo_alvo"] <= ancora) if alvo is not None else (l["resultado"] >= 0)

    lo, hi = 0.5, 20.0
    if not cabe(lo):
        limite = None                 # nem a régua mínima cabe: o problema não é a discagem
    elif cabe(hi):
        limite = hi                   # não morde dentro do alcance que faz sentido
    else:
        for _ in range(20):
            meio = (lo + hi) / 2
            if cabe(meio):
                lo = meio
            else:
                hi = meio
        limite = int(lo * 10) / 10    # trunca: arredondar para cima devolveria régua que NÃO cabe

    return dict(
        regua=base["regua"], tem_recuperacao=tem_rec,
        por_real_credor=(passo["por_real"] if passo and tem_rec else None),
        # R$ que a CORAL ganha por R$ 1 a mais de discagem: negativo = custo puro nosso
        por_real_coral=(passo["d_resultado_var"] / passo["d_custo"]
                        if passo and abs(passo["d_custo"]) > 1e-9 else None),
        d_custo=(passo["d_custo"] if passo else None),
        d_recuperado=(passo["d_recuperado"] if passo else None),
        d_resultado_coral=(passo["d_resultado_var"] if passo else None),
        direcao_credor=("mais" if tem_rec else "indiferente"),
        direcao_coral=("mais" if passo and passo["d_resultado_var"] > 0 else "menos"),
        limite_tipo=("ancora" if alvo is not None else "equilibrio"),
        limite_regua=limite, limite_valor=(ancora if alvo is not None else 0.0),
        sem_otimo_interior=True,
    )


# ── banda de cenários ─────────────────────────────────────────────────────────
# Num contrato de VALOR FIXO o desvio de execução é risco NOSSO: cobramos o mesmo
# todo mês e o custo varia com o que a operação realiza. A banda é o que diz quanto.
#
# ⛔ Três cenários NÃO são três preços. Cobra-se UM preço, e ele sai do cenário BASE;
# os outros dois dizem que margem esse mesmo preço entrega se a realidade for outra.
# Devolver três preços convidaria a escolher o mais confortável, que é o contrário do
# que a banda existe para mostrar.
CENARIOS = (
    # (chave, rótulo, régua realizada, telefones a mais, cadência cheia)
    ("pessimista", "Pessimista", "teto",       0.5, True),
    ("base",       "Base",       "medida",     0.0, False),
    ("otimista",   "Otimista",   "medida-10%", 0.0, False),
)

# o modo de cada cenário é resolvido em `resolver_realizacao`, por BLOCO — ver lá o porquê


def banda(preco_base=None, **kw):
    """Roda os três cenários com o MESMO preço, derivado da base.

    Varia só o que a execução varia:
      · **régua realizada** — pessimista assume o teto contratado (100%), que é o pior
        caso de custo: toda tentativa contratada vira discagem. A base usa a realização
        MEDIDA (93% na régua 2, 68% na 10) e o otimista tira 10% relativos dela.
      · **telefones por CPF** — +0,5 no pessimista, porque o discador capeia por linha e
        mailing com dois telefones dobra a tentativa efetiva sem ninguém pedir.
      · **cadência** — cheia no pessimista: o corte por faixa é uma economia que depende
        de a operação de fato cortar, e num mês ruim ela não corta.

    O otimista é deliberadamente tímido (só a régua, 10% relativos): inflar o lado bom
    com telefone a menos e cadência menor produziria uma banda simétrica e falsa — as
    coisas que dão errado em execução não têm espelho do lado que dá certo.
    """
    faixas = kw.get("faixas")
    tel = kw.get("telefones", 1.0)
    def rodar(modo, dtel, cheia, preco):
        k = dict(kw)
        k["telefones"] = tel + dtel
        # o CENÁRIO desce até a faixa; fixar o escalar aqui achataria a realização de
        # uma faixa de régua própria na régua do contrato
        k["cenario"], k["realizacao"] = modo, None
        if cheia and faixas:
            # cadência cheia = nenhuma faixa cortada; a régua da faixa é preservada
            # porque ela é regra do credor, não economia nossa
            k["faixas"] = [{**f, "wa": kw["wa"], "sms": kw["sms"], "email": kw["email"]}
                           for f in faixas]
        if preco is not None:
            k["alvo"], k["preco"] = None, preco
        return calcular(**k)

    # a BASE primeiro: é dela que sai o preço que os outros dois têm de honrar
    b = rodar("medida", 0.0, False, preco_base)
    return [{**(b if chave == "base" else rodar(modo, dtel, cheia, b["preco"])),
             "chave": chave, "rotulo": rot}
            for chave, rot, modo, dtel, cheia in CENARIOS]


def curva_volume(tamanhos=None, **kw):
    """Preço por unidade e por CPF a margem alvo CONSTANTE, ao longo do volume.

    É a curva que responde "e se forem 40 mil CPFs?" — a pergunta que aparece em toda
    negociação e que era respondida no olho.

    ⛔ **O que ela mostra é que não há ganho de escala.** Acima de 3.000 CPFs o rateio do
    compartilhado é R$ 0,344 por CPF, CONSTANTE, porque `max(3%; 1% a cada 1.000)` cresce
    junto com a base — ele não dilui. O único trecho com ganho real é abaixo de 3.000, onde
    o piso de 3% é maior que o proporcional. Daí para cima o preço por CPF SOBE, porque o
    degrau de IRPJ entra. Quem conceder desconto por volume está concedendo margem, não
    repassando diluição.
    """
    tamanhos = tamanhos or (2_500, 5_000, 10_000, 20_000, 40_000, 60_000, 100_000)
    k = dict(kw)
    k.setdefault("alvo", 0.20)
    k.pop("cpfs", None)
    k.pop("preco", None)
    linhas = []
    for n in tamanhos:
        c = calcular(cpfs=n, **k)
        linhas.append(dict(cpfs=n, uccs=c["uccs"], custo=c["custo_medido"],
                           preco=c["preco"], por_cpf=c["preco"] * c["uccs"] / n,
                           rateio_frac=c["rateio_frac"],
                           rateio_por_cpf=c["rateio_frac"] * P["compart"] / n,
                           trib_pct=c["trib_pct"]))
    ref = linhas[0]["por_cpf"] if linhas else 0
    for l in linhas:
        l["vs_menor"] = (l["por_cpf"] / ref - 1) if ref else 0.0
    return linhas


# alavancas do tornado: (rótulo, chave, valor alternativo, onde vive, procedência).
# "P" = parâmetro nosso (custo de insumo); "kw" = entrada do credor nesta cotação.
TORNADO = (
    ("Preço do disparo de WhatsApp", "wa", 0.25, "P", "tabela"),
    ("Cadência de WhatsApp por CPF/mês", "wa", 1.0, "kw", "decidido"),
    ("Régua de tentativas/dia", "regua", 10.0, "kw", "decidido"),
    ("Telefones por CPF", "telefones", 1.6, "kw", "medido"),
    ("Coeficiente de telecom", "coef_telecom", 0.10, "P", "medido"),
    ("Custo do bot de voz", "bot", 700.0, "P", "tabela"),
    ("CRM — assento por CPF", "crm_assento", 0.08, "P", "tabela"),
    ("Estrutura compartilhada", "compart", 25_000.0, "P", "tabela"),
)


def tornado(alavancas=None, **kw):
    """Quanto cada parâmetro, SOZINHO, move a margem.

    A banda move quatro alavancas ao mesmo tempo e responde "qual é o risco". Esta conta
    responde outra coisa: **qual parâmetro merece atenção**. Foi ela que mostrou que as
    quatro maiores alavancas de margem são todas de acionamento por CPF e que **nenhuma é
    o preço da unidade** — e que a maior delas sob nosso controle é preço de tabela de
    fornecedor que nunca conferimos contra fatura.
    """
    alavancas = alavancas or TORNADO
    k = dict(kw)
    k.pop("alvo", None)
    k.setdefault("preco", P["preco_ucc"])
    base = calcular(**k)["margem_medido"]
    linhas = []
    for rot, chave, para, onde, proc in alavancas:
        if onde == "P":
            de, P[chave] = P[chave], para
            try:
                m = calcular(**k)["margem_medido"]
            finally:
                P[chave] = de
        else:
            de = k.get(chave, 1.0)
            m = calcular(**{**k, chave: para})["margem_medido"]
        linhas.append(dict(rotulo=rot, de=de, para=para, margem=m, delta=m - base,
                           onde=onde, procedencia=proc))
    linhas.sort(key=lambda l: -abs(l["delta"]))
    return dict(base=base, linhas=linhas)


def repactuacao(uccs_assinadas, preco_assinado, **kw):
    """O contrato como ASSINADO ao lado do mesmo escopo recotado com os parâmetros de hoje.

    O contrato de referência roda as unidades 20% acima do tamanho porque foi assinado sob
    a régua antiga de 3.000 CPFs, e a decisão foi mantê-lo como está. Decisão certa — mas
    sem esta leitura a renovação chega sem número pronto, e "quanto custa manter" nunca foi
    calculado. Aqui as duas colunas saem da MESMA carteira: muda só o dimensionamento.
    """
    u_ass = int(uccs_assinadas)
    if u_ass <= 0:
        raise SystemExit("⛔ repactuação precisa do nº de unidades assinadas.")
    k = dict(kw)
    k.pop("alvo", None)
    k["preco"] = preco_assinado
    hoje = calcular(**k)                       # mesmo custo, dimensionamento de hoje
    custo = hoje["custo_medido"]
    rec_ass = u_ass * preco_assinado
    trib_ass = tributo_de(rec_ass, k.get("receita_base", 0.0) or 0.0)
    res_ass = rec_ass - trib_ass - custo
    return dict(
        assinado=dict(uccs=u_ass, preco=preco_assinado, receita=rec_ass,
                      tributo=trib_ass, custo=custo, resultado=res_ass,
                      margem=res_ass / rec_ass if rec_ass else 0.0,
                      cpfs_por_ucc=hoje["cpfs"] / u_ass),
        hoje=dict(uccs=hoje["uccs"], preco=hoje["preco"], receita=hoje["receita"],
                  tributo=hoje["tributo"], custo=custo, resultado=hoje["liquida"] - custo,
                  margem=hoje["margem_medido"], cpfs_por_ucc=P["tam_ucc"]),
        delta_receita=hoje["receita"] - rec_ass,
        delta_margem=hoje["margem_medido"] - (res_ass / rec_ass if rec_ass else 0.0),
        excesso_por_unidade=(hoje["cpfs"] / u_ass) / P["tam_ucc"] - 1 if u_ass else 0.0,
        custo_de_manter=(hoje["liquida"] - custo) - res_ass)


def projecao(meses=12, rampa=None, **kw):
    """Os 12 meses do contrato: maturação da carteira, variável do credor e payback.

    Tudo o mais na bancada é R$ por mês de REGIME — o mês 1 de um contrato novo tratado
    como o mês 12. Aqui a diferença aparece, e ela tem duas pernas.

    **A receita variável entrava zerada.** A conta do mês somava só a fixa, e desde a
    revisão de 10/09 é a variável que paga a margem (só fixa dá −7,6% no contrato de
    referência; com a variável na meta, +21,2%). Uma projeção que ignora a maior das duas
    receitas não projeta o contrato, projeta metade dele.

    **E a carteira não nasce em regime.** Um acordo de k parcelas entrega 1/k no mês em
    que é fechado; o resto pinga depois. Então o mês 1 entrega a fração `maturacao[0]` do
    que o regime entrega — 41,6% na curva medida — enquanto o custo de acionamento é
    INTEGRAL desde o primeiro dia (discamos a base toda no mês 1, não 41,6% dela). O
    descasamento entre custo cheio e receita em rampa é o buraco de caixa da entrada, e
    ele nunca esteve na tela.

    ⚠️ A maturação morde a recuperação que NÓS geramos. O colchão HERDADO (saldo que o
    credor informa, acordo de outra assessoria) chega igual desde o mês 1 — não é nosso e
    não rampa. São dois colchões diferentes e eles entram por portas diferentes.

    `rampa` (multiplicador manual) continua existindo e multiplica por cima, para quem
    quiser modelar ramp-up de operação ou churn. Em branco vale 1,0 — não-destrutivo.
    """
    k = dict(kw)
    setup = float(k.pop("setup", 0.0) or 0.0)
    aliq_ativa = k.pop("variavel_ativa", True)
    k["setup"] = 0.0                            # sai do regime, entra como desembolso
    c = calcular(**k)
    mat = maturacao_de(k.get("maturacao"), meses)
    rampa = list(rampa) if rampa else []

    # o que NÃO rampa: colchão herdado (acordo de terceiro) e o custo (base inteira)
    herdado = c["colchao_mes"]
    nosso = c["recuperado"] - herdado
    var_regime = c["variavel"] if aliq_ativa else 0.0

    linhas, acum = [], -setup
    for m in range(1, int(meses) + 1):
        f = float(rampa[m - 1]) if m <= len(rampa) else 1.0
        mt = mat[m - 1]
        rec = (herdado + nosso * mt) * f
        var = var_regime * mt * f               # a variável cobra sobre a NOSSA recuperação
        bruta = c["receita"] + var
        liq = bruta - tributo_de(bruta, c["receita_base"])
        res = liq - c["custo_medido"]
        acum += res
        linhas.append(dict(mes=m, fator=f, maturacao=mt, recuperado=rec,
                           receita_fixa=c["receita"], variavel=var, bruta=bruta,
                           liquida=liq, custo=c["custo_medido"], resultado=res,
                           acumulado=acum, desembolso=setup if m == 1 else 0.0))
    # o regime é o último mês possível, não o primeiro — é contra ele que a rampa se lê
    bruta_reg = c["receita"] + var_regime
    regime = (bruta_reg - tributo_de(bruta_reg, c["receita_base"])) - c["custo_medido"]
    pay = next((l["mes"] for l in linhas if l["acumulado"] >= 0), None)
    negativos = [l["mes"] for l in linhas if l["resultado"] < 0]
    return dict(setup=setup, regime=regime, linhas=linhas, payback=pay,
                acumulado=linhas[-1]["acumulado"] if linhas else -setup,
                rampa_informada=bool(rampa), maturacao=mat,
                variavel_ativa=aliq_ativa, variavel_regime=var_regime,
                colchao_herdado=herdado, nosso=nosso,
                meses_negativos=negativos,
                # o mês 1 contra o regime: é o tamanho do buraco de entrada
                mes1_vs_regime=(linhas[0]["resultado"] / regime - 1) if linhas and regime else 0.0)


def premio_risco(**kw):
    """Quanto custa cotar no cenário BASE quando o desvio de execução é risco nosso.

    A banda já existia e mostrava três margens. O que faltava era a consequência: num
    contrato de **valor fixo** o desvio não é do credor, é nosso — e o cenário pessimista
    não é exótico (a régua contratada realizada cheia, meio telefone a mais por CPF, a
    cadência sem corte). Cotar no meio é aceitar a distância inteira.

    Devolve o preço que a margem alvo pede sobre o custo da BASE e sobre o custo do
    PESSIMISTA. A diferença é o prêmio — informá-lo ou absorvê-lo é decisão comercial,
    mas ela passa a ser tomada com o número na mesa.
    """
    k = dict(kw)
    alvo = k.pop("alvo", None)
    alvo = 0.20 if alvo is None else alvo
    k.pop("preco", None)
    base = calcular(alvo=alvo, **k)
    cen = {b["chave"]: b for b in banda(preco_base=base["preco"], **k, alvo=None)}
    pes = cen["pessimista"]
    # mesmo alvo, custo do pessimista: é o preço que aguentaria o mau cenário
    preco_pes = preco_do_alvo(pes["custo_medido"], base["uccs"], alvo,
                              k.get("receita_base", 0.0) or 0.0)
    return dict(alvo=alvo, uccs=base["uccs"],
                preco_base=base["preco"], custo_base=base["custo_medido"],
                preco_pessimista=preco_pes, custo_pessimista=pes["custo_medido"],
                premio=preco_pes - base["preco"],
                premio_pct=(preco_pes / base["preco"] - 1) if base["preco"] else 0.0,
                margem_base=base["margem_medido"],
                margem_pessimista_no_preco_base=pes["margem_medido"],
                pontos=base["margem_medido"] - pes["margem_medido"])


def _restricao(preco, u, ancora, recuperado, recuperado_novo=None, variavel=0.0):
    """Qual das três restrições está MORDENDO — e por quanto.

    As três não são do mesmo tipo, e confundi-las é o erro comum:
      · a **margem alvo** empurra o preço PARA CIMA (é o mínimo que a conta pede);
      · a **âncora** e o **teto por R$ 1 recuperado** são TETOS.
    Logo a restrição ativa é o teto mais baixo que o preço do alvo já ultrapassou. Se o
    preço cabe nos dois tetos, quem manda é a própria margem alvo — e aí há folga para
    desconto, que é exatamente a leitura que o comercial precisa antes de negociar.

    ⛔ **Os tetos conferem o EFETIVO, não o fixo** (15/09/2026). Até a auditoria os dois
    comparavam o preço da unidade, que é só a parcela fixa; o credor desembolsa fixo +
    variável. No contrato de referência isso deixava passar um efetivo de R$ 22.864 por
    unidade contra uma âncora de R$ 12.000, e media R$ 0,035 por R$ 1 recuperado onde o
    real é R$ 0,095. Sob `modalidade="fixo"` a variável é zero e nada muda.

    O teto por R$ 1 só existe com recuperação informada; sem ela devolve `None` em vez
    de zero, porque "não sabemos" e "não fura" são coisas diferentes.
    """
    efetivo = preco + (variavel / u if u else 0.0)
    teto_r = (P["teto_por_real"] * recuperado / u) if (recuperado > 0 and u) else None
    # ── a MESMA conta sobre a recuperação NOVA (parecer 14/09, item `tetonovo`) ──
    # O teto de R$ 0,30 é leitura do CREDOR: ele olha tudo que entrou, colchão incluído.
    # Só que o colchão é acordo de outra assessoria, e uma carteira com colchão grande
    # passa no teto por mérito alheio. O merecimento já ganhou a coluna por R$ 1 NOVO em
    # 14/09; a restrição não tinha ganhado. As duas convivem de propósito: a do credor
    # fecha a negociação, a nossa diz se o negócio é bom.
    rn = recuperado if recuperado_novo is None else recuperado_novo
    teto_novo = (P["teto_por_real"] * rn / u) if (rn > 0 and u) else None
    extra = dict(teto_por_real_novo=teto_novo,
                 restricao_efetivo=efetivo,
                 # o quanto a variável acrescenta ao que o credor paga por unidade: é a
                 # diferença entre o que a conta media antes e o que ela mede agora
                 restricao_variavel_un=efetivo - preco,
                 folga_por_real_novo=(teto_novo - efetivo) if teto_novo else None,
                 colchao_segura_o_teto=bool(teto_r and teto_novo and efetivo <= teto_r
                                            and efetivo > teto_novo))
    tetos = [("ancora", ancora)] + ([("teto_por_real", teto_r)] if teto_r else [])
    furados = [(k, v) for k, v in tetos if efetivo > v]
    if furados:
        k, v = min(furados, key=lambda x: x[1])
        return dict(restricao=k, restricao_teto=v, restricao_folga=v - efetivo, **extra)
    menor = min(v for _, v in tetos)
    return dict(restricao="margem_alvo", restricao_teto=menor,
                restricao_folga=menor - efetivo, **extra)


FICHA_LINHAS = (
    ("cpfs", "CPFs na carteira", "sem isto não há dimensionamento"),
    ("faixas", "CPFs por faixa de atraso",
     "saldo em R$ não é proxy de CPF — sem isto não há merecimento nem gatilho"),
    ("entrada_mes", "Entrada mensal por faixa",
     "a faixa curta é fluxo; assumir só o estoque subestima quem mais recupera"),
    ("base_meta", "Denominador da meta",
     "a mesma taxa vale valores muito diferentes conforme a base"),
    ("carteira_entrada", "R$ que entra por mês",
     "entra no custo e fica fora da recuperação — o preço sai como TETO"),
    ("regua", "Régua de tentativas/dia", "dirige telecom e capacidade"),
    ("telefones", "Telefones por CPF",
     "o discador capeia por linha; 2 telefones dobram a tentativa efetiva"),
    ("cadencia", "Cadência por canal", "é a maior linha variável do custo"),
    ("carteira_faixa", "Carteira em R$ por faixa", "sem isto não há variável, só valor fixo"),
    ("meta", "Recuperação observada por faixa",
     "NUNCA usar a declarada: ela crava o gatilho no piso"),
    ("aliq", "Tabela de comissionamento", "sem isto o híbrido com gatilho não existe"),
    ("ancora", "O que o credor paga hoje", "é a âncora competitiva real"),
    ("transbordo", "Transbordo humano", "havendo fila humana, o custo por posição entra aqui"),
    ("compartilhamento", "Modelo de compartilhamento",
     "em mar aberto o custo é integral e a recuperação é disputada"),
    ("desconto", "Desconto no principal por faixa",
     "a alíquota incide sobre o negociado, não sobre a face"),
    ("colchao", "Colchão de acordos — saldo, prazo e eficiência",
     "parcela de acordo já firmado chega sem esforço novo e infla a meta"),
    ("escopo", "Faixas elegíveis para terceirização",
     "sem marcação, a cotação cobre a carteira inteira"),
    ("serie", "Entradas mensais dos últimos 6 meses",
     "a média esconde o pico, e é no pico que a unidade estoura"),
    ("parcelamento", "Parcelamento máximo por faixa",
     "promessa parcelada quebra mais; premissa escrita, fora da conta"),
    ("produtos", "Produtos cobertos por esta cotação",
     "produto com régua ou cadência própria é contrato separado"),
    ("maturacao", "Curva de maturação — como o acordo vira caixa no tempo",
     "o colchão sai dela; sem a do credor, vale a nossa, que é de outra carteira"),
)


def planilha(c, recuperacao=None, fee=None, cliente="—", obs=None, cenarios=None,
             escada=None, curva=None, torn=None, premio=None, repac=None, proj=None):
    L = []
    A = L.append
    sec = iter(range(1, 20))
    def S(titulo):
        A(f"## {next(sec)}. {titulo}")
    A(f"# Planilha de precificação — {cliente}")
    A("")
    A("> **Interno.** Contém custo e margem da Coral. Não é a proposta.")
    A(f"> Cálculo determinístico por `ucc_calc.py`; parâmetros espelham "
      f"`UCC_Modelo_Remuneracao.md` (calibração 10/09/2026).")
    A("")
    S("Entradas")
    A("")
    A("| Entrada | Valor |")
    A("|---|--:|")
    A(f"| Base de CPFs | {num(c['cpfs'])} |")
    A(f"| Régua contratada | {num(c['tent_contratada'], 2)} tentativas/CPF/dia |")
    A(f"| Realização estimada da régua | {c['realizacao']*100:.0f}% |")
    A(f"| **Tentativa esperada** | **{num(c['tent_esperada'], 2)}/CPF/dia** |")
    A("")
    S("Dimensionamento")
    A("")
    A(f"- **{c['uccs']} UCC(s)** — `teto({num(c['cpfs'])} ÷ {num(P['tam_ucc'])})`")
    A(f"- Ocupação da última unidade: **{c['ocupacao']*100:.0f}%** da capacidade vendida")
    ca = c["canais"]
    if ca["canais"]:
        A(f"- **Canais que a operação liga: {num(ca['canais'], 1)}** — "
          f"`{num(c['tent_esperada'], 2)} × {num(c['cpfs'])} ÷ ({num(THR_CANAL_H)} × "
          f"{num(JANELA_H, 2)}h)`. Um canal cobre **{num(ca['cpfs_por_canal'])} CPFs** nesta "
          f"régua, então **uma unidade vendida exige {num(ca['canais_por_ucc'], 1)} canal(is)**.")
        A(f"  > ⛔ A UCC conta **bots** (2.500 CPFs em qualquer régua); a operação conta "
          f"**canais**, e a conta é outra. A régua 2 pede 1,4 canal por unidade e a régua 10 "
          f"pede 7,2 — **5× de amplitude dentro do mesmo tamanho vendido**. Enquanto o de-para "
          f"não fecha, o 2.500 é número comercial sem contrapartida operacional.")
    if c["faixas_sem_cpf"]:
        A("")
        A("> ⚠️ **Faixa com saldo e ZERO CPFs** em "
          + ", ".join(f"**{n}**" for n in c["faixas_sem_cpf"])
          + ". Ela entrou na conta recuperando **nada**: sem CPF não há quem trabalhar, e "
            "carteira × meta sobre uma linha vazia produzia recuperação em cima de custo "
            "zero. Ou o CPF está noutra faixa, ou o saldo foi digitado errado — confira "
            "antes de levar o número.")
    if c["rateio_no_teto"]:
        A("")
        A(f"> ⚠️ **Rateio no teto.** Esta carteira sozinha cobre os "
          f"{br(P['compart'])} do compartilhado inteiro. A fração cresce 1% a cada 1.000 "
          f"CPFs e está **limitada a 100%** — acima de {num(100_000)} CPFs o contrato não "
          f"paga mais do que existe para ratear.")
    if c["regua_extrapolada"]:
        e = c["regua_extrapolada"]
        A("")
        A(f"> ⚠️ **RÉGUA FORA DO QUE MEDIMOS.** A realização da régua conhece **dois** pontos "
          f"(93% na régua 2 · 68% na régua 10) e traça uma reta entre eles. Esta cotação usa "
          f"régua **{num(e['regua'], 2)}**, {e['lado']} do intervalo — o número é "
          f"**extrapolação**, não interpolação. O γ = 1,00 da escada de voz também só foi "
          f"medido até 10 tentativas. Escreva a premissa na proposta.")
    if c["alvo"] is not None:
        A(f"- **Preço calculado: {br(c['preco'])} por unidade** a {num(c['alvo']*100, 0)}% de "
          f"margem alvo · equilíbrio {br(c['equilibrio'])} · tabela {br(P['preco_ucc'])}")
    A(f"- Receita: **{br(c['receita'])}/mês** · tributo {br(c['tributo'])} "
      f"({num(c['trib_pct']*100, 2)}%) · líquida: {br(c['liquida'])}")
    if c["receita_base"]:
        A(f"- Receita que a Coral já fatura: **{br(c['receita_base'])}/mês** — este contrato é "
          "custeado na faixa tributária **marginal** em que ele de fato cai")
    if c["receita"] + c["receita_base"] > P["teto_tributo"]:
        A("")
        A(f"> ⚠️ **DEGRAU TRIBUTÁRIO ATIVO.** Receita de {br(c['receita'])} sobre uma base de "
          f"{br(c['receita_base'])} passa dos {br(P['teto_tributo'])} em que os "
          f"{num(P['tributo']*100, 2)}% valem sozinhos. O adicional de IRPJ de "
          f"{num(P['irpj_adic']*100, 0)}% sobre o lucro presumido excedente **já está na conta** — "
          f"a carga efetiva deste contrato é **{num(c['trib_pct']*100, 2)}%**. O degrau é da "
          "pessoa jurídica: se a Coral fatura por fora e você não informou, o preço está "
          "subestimado (`--receita-base`).")
    A("")
    S("Custo")
    A("")
    A("| Linha | Natureza | Mensal |")
    A("|---|---|--:|")
    for nome, val, nat in c["linhas"]:
        extra = f" <small>({c['rateio_frac']*100:.0f}%)</small>" if nome.startswith("Rateio") else ""
        A(f"| {nome}{extra} | {nat} | {br(val)} |")
    A(f"| **Telecom** <small>0,137 × {num(c['tent_esperada'], 2)} tentativas</small> "
      f"| Acionamento | **{br(c['tel_med'])}** |")
    A(f"| **Custo total** | | **{br(c['custo_medido'])}** |")
    # ── merecimento por faixa ────────────────────────────────────────────────
    if c["faixas"]:
        A("")
        S("Merecimento por faixa")
        A("")
        A("Custo e recuperação na mesma linha. A coluna que decide é **R$ gasto por R$ 1 "
          "recuperado** — cortar cadência numa faixa economiza de um lado e destrói recuperação "
          "do outro, e as duas pontas aparecem juntas.")
        if c["colchao_mes"] > 0:
            A("")
            A("> 📌 **Duas colunas de merecimento, de propósito.** `R$ por R$ 1` é a leitura do "
              "**credor** (custo sobre tudo que a faixa recupera) e reconcilia com o teto de "
              "R$ 0,30. `R$ por R$ 1 NOVO` é a leitura de **esforço**: faixa cuja recuperação é "
              "quase toda colchão merece menos cadência do que o total dela sugere.")
        A("")
        corte = c["economia_total"] > 1
        colch = c["colchao_mes"] > 0
        cab = ("| Faixa | CPFs | Carteira | Recuperado | % recup. | Custo | % custo | R$ por R$ 1 |"
               + (" R$ por R$ 1 NOVO |" if colch else "")
               + (" Economia | Perdido | Perde por R$ 1 |" if corte else ""))
        A(cab)
        A("|---|--:|--:|--:|--:|--:|--:|--:|" + ("--:|" if colch else "")
          + ("--:|--:|--:|" if corte else ""))
        for l in c["faixas"]:
            pr = ("R$ " + num(l["por_real"], 4 if l["por_real"] < 0.1 else 2)
                  if l["por_real"] is not None else "—")
            linha = (f"| {l['nome']} | {num(l['trabalhado'])} | {br(l['carteira_trab'])} | "
                     f"{br(l['recuperado'])} | "
                     f"{num(l['recuperado']/c['recuperado']*100,1) if c['recuperado'] else '0,0'}% | "
                     f"{br(l['custo'])} | {num(l['custo']/c['custo_medido']*100,1)}% | {pr} |")
            if colch:
                prn = l["por_real_novo"]
                # faixa que não recupera nada não é "só colchão" — é nada a medir
                linha += (" " + ("R$ " + num(prn, 4 if prn < 0.1 else 2) if prn is not None
                                 else "só colchão" if l["recuperado"] > 0 else "—") + " |")
            if corte:
                linha += (f" {br(l['economia']) if l['economia'] > 0.5 else '—'} |"
                          f" {br(l['perda']) if l['perda'] > 0.5 else '—'} |"
                          f" {'R$ ' + num(l['perda']/l['economia'],2) if l['economia'] > 0.5 else '—'} |")
            A(linha)
        tot = (f"| **Total** | **{num(c['cpfs'])}** | **{br(c['carteira'])}** | "
               f"**{br(c['recuperado'])}** | 100% | **{br(c['custo_medido'])}** | 100% | "
               f"**{'R$ ' + num(c['custo_medido']/c['recuperado'], 4) if c['recuperado'] else '—'}** |")
        if colch:
            tot += (" **" + ("R$ " + num(c["custo_medido"] / c["recuperado_novo"], 4)
                             if c["recuperado_novo"] > 0 else "—") + "** |")
        if corte:
            tot += (f" **{br(c['economia_total'])}** | **{br(c['perda_total'])}** | "
                    f"**R$ {num(c['perda_total']/c['economia_total'],2)}** |")
        A(tot)
        if c["entrada_mes"] > 0:
            A("")
            A(f"> 📌 **Estoque + fluxo.** A foto da carteira tem **{num(c['estoque'])} CPFs**; "
              f"entram **{num(c['entrada_mes'])}/mês** nas faixas curtas, e esses são trabalhados "
              f"como qualquer outro. O dimensionamento usa o **trabalhado ({num(c['cpfs'])})** — "
              "dimensionar pela foto subestima a faixa onde mora quase toda a recuperação.")
        if c["entrada_sem_valor"]:
            A("")
            A(f"> ⛔ **LACUNA — o R$ da entrada não foi informado** em "
              f"{', '.join(c['entrada_sem_valor'])}. Esses CPFs entram no **custo** (são "
              "trabalhados) e ficam **fora da recuperação**, porque derivar o valor pelo ticket "
              "do estoque assume ticket uniforme — e os CPFs parados numa faixa são justamente os "
              "que não pagaram. **O preço que sai daqui é TETO:** custo cheio contra receita só do "
              "que foi medido. Peça ao credor o valor que entra por mês em cada faixa.")
        mortas = [l for l in c["faixas"] if l["recuperado"] <= 0]
        if mortas:
            peso = sum(l["custo"] for l in mortas)
            A("")
            A(f"> ⛔ **{len(mortas)} faixa(s) com recuperação ZERO** — "
              f"{', '.join(l['nome'] for l in mortas)} — levam **{br(peso)}/mês** "
              f"(**{num(peso/c['custo_medido']*100,1)}% do custo**) e devolvem nada. "
              "Antes de cotar a carteira inteira, pergunte por que elas estão no escopo.")
        if corte:
            razao = c["perda_total"] / c["economia_total"]
            A("")
            A(f"> {'⚠️' if razao > 1 else '✅'} **Corte de cadência:** economiza "
              f"{br(c['economia_total'])}/mês e custa {br(c['perda_total'])} de recuperação ao "
              f"cliente — **R$ {num(razao,2)}** destruídos por R$ 1 economizado, "
              f"{num(c['perda_total']/(c['rec_base_total'] or 1)*100,2)}% da recuperação do mês. "
              + ("Vale para a Coral e não vale para o cliente."
                 if razao > 1 else "Neste recorte o corte destrói menos do que economiza.")
              + " ⚠️ As elasticidades são **premissa**, não medição nossa "
              f"(WA {num(c['elast']['wa']*100,1)}% · SMS {num(c['elast']['sms']*100,1)}% · "
              f"e-mail {num(c['elast']['email']*100,1)}%).")

    # ── DRE ──────────────────────────────────────────────────────────────────
    A("")
    S("DRE")
    A("")
    variavel = c["variavel"]
    bruta = c["receita"] + variavel
    trib = tributo_de(bruta, c["receita_base"])
    liq = bruta - trib
    av = lambda v: f"{num(v/bruta*100,1)}%" if bruta else "—"
    A("| Linha | Mensal | % da receita bruta |")
    A("|---|--:|--:|")
    A(f"| Receita fixa — {c['uccs']} UCC(s) × {br(c['preco'])} | {br(c['receita'])} | {av(c['receita'])} |")
    if variavel:
        A(f"| Receita variável — tabela do credor por faixa | {br(variavel)} | {av(variavel)} |")
    A(f"| **Receita bruta** | **{br(bruta)}** | **100,0%** |")
    A(f"| (−) Tributos sobre a receita <small>{num(trib/bruta*100,2) if bruta else 0}%</small> "
      f"| {br(-trib)} | {av(-trib)} |")
    A(f"| **Receita líquida** | **{br(liq)}** | **{av(liq)}** |")
    for nat in ("Capacidade", "Acionamento"):
        sub = [(n, v) for n, v, x in c["linhas"] if x == nat]
        if nat == "Acionamento":
            sub = [("Telecom — pela medição", c["tel_med"])] + sub
        A(f"| **(−) {nat}** | **{br(-sum(v for _, v in sub))}** | **{av(-sum(v for _, v in sub))}** |")
        for n, v in sub:
            A(f"| ↳ {n} | {br(-v)} | {av(-v)} |")
    A(f"| **(=) Resultado** | **{br(liq - c['custo_medido'])}** | **{av(liq - c['custo_medido'])}** |")
    A("")
    if variavel:
        so_fixo = (c["receita"] - tributo_de(c["receita"], c["receita_base"])
                   - c["custo_medido"]) / c["receita"] if c["receita"] else 0
        A(f"> O preço foi derivado **só do fixo**; a variável entra por cima. Sem ela a margem "
          f"seria {pct(so_fixo)}, com ela é {pct((liq - c['custo_medido'])/bruta)} — "
          f"**{num(abs((liq-c['custo_medido'])/bruta - so_fixo)*100,1)} pontos**. "
          "É a variável que paga a margem; o fixo recupera o custo de ter a unidade ligada.")
    elif c["faixas"]:
        zeradas = [l["nome"] for l in c["faixas"] if l["aliq"] > 0 and l["recuperado"] <= 0]
        A("> Sem receita variável: o resultado é o que o fixo entrega sozinho. "
          + (f"A tabela do credor só tem alíquota em {', '.join(zeradas)}, e essas faixas "
             "recuperam ZERO — o variável existe no papel e nunca ativa. Num modelo aditivo "
             "isso é contrato de valor fixo com tabela decorativa."
             if zeradas else
             "Nenhuma faixa tem alíquota preenchida; some `aliq` às faixas para o variável sair."))
    else:
        A("> Sem receita variável: o resultado é o que o fixo entrega sozinho. Num modelo aditivo "
          "a tabela de êxito do credor entraria aqui por cima — abra as faixas com `--faixas` "
          "para o cálculo sair.")

    if cenarios:
        A("")
        S("Banda de execução")
        A("")
        A("O preço é **um** — o da base. Os três cenários dizem que **margem** esse mesmo preço "
          "entrega se a operação sair do previsto. Num contrato de valor fixo o desvio de "
          "execução é risco **nosso**.")
        A("")
        A("| Cenário | Régua realiza | Tent./CPF/dia | Custo | Resultado | Margem |")
        A("|---|--:|--:|--:|--:|--:|")
        for x in cenarios:
            neg = "**" if x["margem_medido"] < 0 else ""
            marca = "**" if x["chave"] == "base" else ""
            A(f"| {marca}{x['rotulo']}{marca} | {x['realizacao']*100:.0f}% | "
              f"{num(x['tent_esperada'], 2)} | {br(x['custo_medido'])} | "
              f"{br(x['liquida'] - x['custo_medido'])} | "
              f"{neg}{num(x['margem_medido']*100, 1).replace('-', '−')}%{neg} |")
        pior = cenarios[0]
        bom = cenarios[-1]
        A("")
        if pior["liquida"] - pior["custo_medido"] < 0 <= c["liquida"] - c["custo_medido"]:
            A(f"> ⛔ **No pessimista este contrato fica negativo** "
              f"({br(pior['liquida'] - pior['custo_medido'])}/mês). O preço fecha na execução "
              "medida e não sobrevive à execução no teto contratado.")
        else:
            amp = (bom["margem_medido"] - pior["margem_medido"]) * 100
            A(f"> A margem anda de **{num(pior['margem_medido']*100, 1)}%** a "
              f"**{num(bom['margem_medido']*100, 1)}%** — **{num(amp, 1)} p.p.** de amplitude.")
        A("")
        A("O **pessimista** assume a régua realizada no teto contratado, **+0,5 telefone por "
          "CPF** (o discador capeia por linha) e a cadência cheia, sem o corte por faixa. O "
          "**otimista** mexe só na régua, 10% abaixo da medida — o que dá errado em execução "
          "não tem espelho do lado que dá certo, e uma banda simétrica seria uma banda falsa.")

    if c["faixas_fora"]:
        A("")
        S("Escopo — o que ficou de fora")
        A("")
        A(f"**{num(len(c['faixas_fora']))} de "
          f"{num(len(c['faixas_fora']) + len(c['faixas']))} faixas** estão marcadas como fora da "
          f"terceirização: **{num(c['cpfs_fora'])} CPFs** e **{br(c['carteira_fora'])}** de "
          "carteira que a cotação não cobre. Ficam aqui com o que carregariam, porque a decisão "
          "de escopo precisa do antes-e-depois.")
        A("")
        A("| Faixa fora | CPFs | Carteira | Recuperaria | Acionamento que custaria |")
        A("|---|--:|--:|--:|--:|")
        for l in c["faixas_fora"]:
            A(f"| {l['nome']} | {num(l['trabalhado'])} | {br(l['carteira_trab'])} | "
              f"{br(l['recuperado_potencial'])} | {br(l['acionamento_potencial'])} |")
        A(f"| **Total fora** | **{num(c['cpfs_fora'])}** | **{br(c['carteira_fora'])}** | "
          f"**{br(c['recuperado_fora'])}** | **{br(c['acionamento_fora'])}** |")
        A("")
        A("> ⚠️ A coluna de acionamento é **só acionamento**: capacidade é degrau do contrato "
          "inteiro, e recontar unidades por faixa daria número errado. Para o custo exato de "
          "incluir a faixa, tire a marcação e leia a conta inteira.")

    if c["serie_stat"]:
        e = c["serie_stat"]
        A("")
        S("Entradas mensais — o que a média esconde")
        A("")
        A(f"Série de **{num(e['n'])} meses**: média **{num(e['media'])} CPFs/mês**, mínimo "
          f"{num(e['minimo'])}, máximo **{num(e['maximo'])}**. Dispersão de "
          f"**{pct(e['disp'], 0).lstrip('+')}** sobre a média; tendência "
          f"**{pct(e['tendencia'], 0)}** entre a primeira e a segunda metade.")
        if e["disp"] > 0.30:
            A("")
            A(f"> ⚠️ **Dimensionar pela média subdimensiona no pico.** A entrada vai a "
              f"{num(e['maximo'])} CPFs num mês da série — **{pct(e['maximo']/e['media'] - 1, 0)}** "
              "acima da média que a conta usa. A unidade aguenta a média; o mês de pico é risco "
              "que precisa estar escrito.")
        if c["entrada_divergente"]:
            A("")
            A(f"> ⛔ **A entrada digitada por faixa ({num(c['entrada_mes'])}/mês) diverge da média "
              f"da série ({num(e['media'])}/mês)** em mais de 20%. Uma das duas está errada — "
              "entrada inconsistente não é refinamento.")

    tem_colchao = any(l["colchao"] > 0 for l in c["faixas"])
    if (c.get("compart_modelo", "exclusivo") != "exclusivo"
            or any(l["desconto"] > 0 for l in c["faixas"]) or tem_colchao):
        A("")
        S("O que chega sem ser nosso")
        A("")
        A("| Item | Valor | Efeito na conta |")
        A("|---|--:|---|")
        A(f"| Modelo de compartilhamento | {c.get('compart_modelo', 'exclusivo')} "
          "| discamos a base inteira; o custo **não** se divide |")
        A(f"| Recuperação que fica com a Coral | {pct(c.get('captura', 1.0), 0).lstrip('+')} "
          f"| base da nossa variável |")
        A(f"| Recuperação da faixa (total do credor) | {br(c['recuperado'])} "
          "| merecimento e teto de R$ 0,30 leem esta |")
        A(f"| Recuperação NOVA (fora o colchão) | {br(c['recuperado_novo'])} "
          "| o que depende do nosso acionamento |")
        A(f"| **Base da nossa variável** | **{br(c['recuperado_coral'])}** "
          "| **NOVA × captura — a alíquota incide sobre esta** |")
        for l in c["faixas"]:
            if l["desconto"] > 0:
                base_rot = ("de FACE — a conta abate o desconto" if l["meta_base_valor"] == "face"
                            else "já LÍQUIDA — o desconto não abate de novo")
                A(f"| Desconto em {l['nome']} | {pct(l['desconto'], 0).lstrip('+')} "
                  f"| meta {base_rot} |")
        if c.get("compart_modelo", "exclusivo") != "exclusivo" and c.get("captura", 1.0) >= 1:
            A("")
            A("> ⛔ **Carteira declarada não-exclusiva com captura em 100%.** O custo já é "
              "integral; assumir que toda a recuperação vira fatura nossa é a premissa mais "
              "otimista possível. Informe a fração que esperamos capturar.")

        if tem_colchao:
            A("")
            A("**Colchão de acordos** — parcela de acordo já firmado chega discando ou não. A "
              "perda de cadência e a escada de régua só mordem o **acionável**, e a variável "
              "cobra sobre a recuperação **NOVA**: assessoria é paga pelo que ELA recupera.")
            A("")
            if not c.get("colchao_ativo"):
                A(f"> ⛔ **Saldo informado ({br(sum(l['colchao'] for l in c['faixas']))}) sem "
                  "prazo restante e/ou eficiência.** Sem as duas pontas não há como converter "
                  "estoque em recuperação do mês, então o colchão fica **declarado e FORA da "
                  "conta** — inventar prazo ou cumprimento seria erro da mesma classe do "
                  "denominador da meta. Peça os itens 9 e 10 do discovery.")
            else:
                A(f"| Item | Valor |")
                A("|---|--:|")
                A(f"| Saldo a vencer (soma das faixas) | {br(sum(l['colchao'] for l in c['faixas']))} |")
                A(f"| Prazo restante | {num(c['colchao_meses'], 1)} meses |")
                A(f"| Eficiência | {pct(c['colchao_efic'], 0).lstrip('+')} |")
                A(f"| **Colchão no mês** | **{br(c['colchao_mes'])}** |")
                A(f"| Recuperação da faixa (total) | {br(c['recuperado'])} |")
                A(f"| **Recuperação NOVA — a que depende de nós** | **{br(c['recuperado_novo'])}** |")
                if c["colchao_excede"]:
                    A("")
                    A("> ⛔ **Colchão maior que a recuperação observada** em "
                      + ", ".join(f"**{n}**" for n in c["colchao_excede"])
                      + ". O saldo sozinho entregaria mais do que a faixa inteira entrega — "
                      "entrada inconsistente. A conta limitou ao teto da faixa; confira o saldo "
                      "e o prazo antes de usar o número.")

    if escada:
        A("")
        S("Discar mais ou menos")
        A("")
        A("A régua mexia só no custo. Aqui as duas pontas andam juntas: quanto custa a tentativa "
          "a mais e quanto ela devolve — **ao credor** e **à Coral**, que raramente é a mesma "
          "resposta. Todas as linhas rodam com o **preço da base**; `Preço no alvo` fica ao lado "
          "para quem ainda está cotando.")
        A("")
        A("| Régua/dia | Tent. efetiva | Custo | Recuperação | Δ recup. | Nossa variável "
          "| Result. Coral | Δ result. | Preço no alvo |")
        A("|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
        tem_rec = any(l["recuperado"] > 0 for l in escada)
        for l in escada:
            m = "**" if l["base"] else ""
            sinal = lambda v: ("+" if v > 0 else "") + br(v).replace("-", "−")
            A(f"| {m}{num(l['regua'], 0 if float(l['regua']).is_integer() else 1)}{m} "
              f"| {num(l['tent_esperada'], 2)} | {br(l['custo'])} "
              f"| {br(l['recuperado']) if tem_rec else '—'} "
              f"| {'—' if l['base'] or not tem_rec else sinal(l['d_recuperado'])} "
              f"| {br(l['variavel']) if tem_rec else '—'} | {br(l['resultado_var'])} "
              f"| {'—' if l['base'] else sinal(l['d_resultado_var'])} "
              f"| {br(l['preco_alvo']) if l['preco_alvo'] is not None else '—'} |")
        base_l = next((l for l in escada if l["base"]), escada[0])
        acima = [l for l in escada if l["regua"] > base_l["regua"]]
        A("")
        # `por_real` é None quando o degrau não move o custo (régua igual à base, ou
        # carteira sem telecom a acrescentar) — dividir ali seria 0÷0. A conta devolve None
        # de propósito; quem renderiza é que não podia formatar sem olhar.
        if acima and tem_rec and acima[0]["por_real"] is not None:
            pa = acima[0]
            A(f"> Subir a régua de **{num(base_l['regua'], 0)}** para **{num(pa['regua'], 0)}** "
              f"custa **{br(pa['d_custo'])}/mês** e devolve **{br(pa['d_recuperado'])}** de "
              f"recuperação ao credor — **R$ {num(pa['por_real'], 2)}** por R$ 1 gasto. "
              + (f"Para a Coral sobra **{br(pa['d_resultado_var'])}/mês**."
                 if pa["d_resultado_var"] >= 0 else
                 f"Para a Coral **custa {br(-pa['d_resultado_var'])}/mês** — o credor quer "
                 "discar mais e nós não."))
        elif acima:
            A(f"> Sem a carteira aberta por faixa só o **custo** é calculável: uma régua a mais "
              f"custa **{br(acima[0]['d_custo'])}/mês**.")
        if any(l["acima_da_carteira"] for l in escada):
            A("")
            A("> ⛔ Algum degrau projeta recuperação **maior que a carteira inteira**. "
              "Extrapolação longe da régua cadastrada não se sustenta — descarte os extremos.")
        A("")
        A(f"Retorno por tentativa **{num(VOZ['gamma'], 2)}** (1,00 = proporcional, o medido no "
          f"Ouro de 1 a 10 tentativas)"
          + (f" e piso espontâneo **{num(VOZ['piso']*100, 1)}%** — informado, então esta carteira "
             "está declarada como NÃO filtrada pelo credor."
             if VOZ["piso"] > 0 else
             ". **Sem piso espontâneo**: a carteira distribuída já chega sem o que o credor "
             "recupera sozinho, então toda a recuperação aqui depende de acionamento e metade "
             "da régua é metade da recuperação.")
          + " ⚠️ A recuperação de cada faixa foi observada na operação atual do credor, que não é "
            "a nossa. ⛔ A escada cobra o telecom do degrau e **não** cobra capacidade adicional — "
            "o de-para bot ↔ canal não existe.")

    A("")
    S("Ficha de entrada")
    A("")
    A("O que veio do credor, o que **nós** assumimos, e o que falta. Um preço construído sobre "
      "entrada assumida não é errado — é condicional, e a condição tem de estar escrita.")
    A("")
    A("| Entrada | Como está | Sem isso |")
    A("|---|---|---|")
    for chave, rot, sem in FICHA_LINHAS:
        est = c["ficha"][chave]
        if est == "na":
            continue
        marca = {"ok": "informado", "assumido": "**assumido**", "falta": "⛔ **falta**"}[est]
        A(f"| {rot} | {marca} | " + ("" if est == "ok" else sem) + " |")
    faltas = [rot for chave, rot, _ in FICHA_LINHAS if c["ficha"][chave] == "falta"]
    assumidas = [rot for chave, rot, _ in FICHA_LINHAS if c["ficha"][chave] == "assumido"]
    A("")
    if faltas:
        n = len(faltas)
        A(f"> ⛔ **{n} entrada{'' if n == 1 else 's'} "
          f"falta{'' if n == 1 else 'm'}:** {', '.join(faltas)}. "
          "Peça ao credor antes de levar o número.")
        A("")
    if assumidas:
        A(f"> ⚠️ **Assumido por nós:** {', '.join(assumidas)}. Escreva na proposta — é o que "
          "dá base à conversa de reajuste se a realidade vier diferente.")
    if not faltas and not assumidas:
        A("> ✅ Todas as entradas vieram do credor.")

    A("")
    S("Leitura contra as âncoras")
    A("")
    equil = c["equilibrio"]
    A("| Referência | Valor | Leitura |")
    A("|---|--:|---|")
    A(f"| Preço por unidade | {br(c['preco'])} | a parcela FIXA |")
    if c["restricao_variavel_un"] > 0:
        A(f"| Variável por unidade | {br(c['restricao_variavel_un'])} | na meta observada |")
        A(f"| **Efetivo por unidade** | **{br(c['restricao_efetivo'])}** | "
          "é este que os tetos conferem |")
    A(f"| Equilíbrio por unidade | {br(equil)} | preço que zera a conta |")
    A(f"| Âncora de mercado | {br(c['ancora'])} | "
      + ("o que o credor paga hoje |" if c["ancora_propria"]
         else "posição humana + plataforma |"))
    folga = 1 - equil / c["ancora"]
    A(f"| **Folga até a âncora** | **{folga*100:.0f}%** | espaço para margem, desconto e variação |")
    A("")
    rot_r = {"ancora": "a âncora", "teto_por_real": "o teto por R$ 1 recuperado",
             "margem_alvo": "a margem alvo"}[c["restricao"]]
    furou = c["restricao_folga"] < 0
    # ⛔ Os dois tetos conferem o EFETIVO (fixo + variável), não o fixo — auditoria 15/09.
    # O texto tem de dizer qual número está sendo comparado, senão quem lê confere o
    # preço da unidade contra um limite que não é sobre ele.
    _ef = c["restricao_efetivo"]
    _un = c["restricao_variavel_un"]
    _abre = (f"efetivo de {br(_ef)} por unidade"
             + (f" (fixo {br(c['preco'])} + variável {br(_un)})" if _un > 0 else ""))
    if furou:
        A(f"> ⛔ **Restrição ativa: {rot_r}.** O {_abre} está "
          f"**{br(-c['restricao_folga'])} acima** do teto de {br(c['restricao_teto'])}. "
          "É este número que precisa ceder — não o próximo desconto.")
    elif c["restricao"] == "margem_alvo":
        A(f"> ✅ **Restrição ativa: a margem alvo.** O {_abre} cabe nos dois tetos, com "
          f"**{br(c['restricao_folga'])} de folga** até o mais baixo ({br(c['restricao_teto'])}). "
          "É o espaço que existe para desconto.")
    else:
        A(f"> **Restrição ativa: {rot_r}** — {br(c['restricao_folga'])} de folga sobre o "
          f"{_abre}.")
    if c.get("teto_por_real_novo"):
        A("")
        A(f"> **O mesmo teto, medido pelo que depende de nós:** o R$ 0,30 por R$ 1 é leitura "
          f"do CREDOR e inclui o colchão, que é acordo de outra assessoria. Sobre a "
          f"recuperação **NOVA** o teto cai para **{br(c['teto_por_real_novo'])}** por unidade"
          + (f" — e o efetivo de {br(c['restricao_efetivo'])} **passa dele**."
             if c["colchao_segura_o_teto"]
             else f", com {br(c['folga_por_real_novo'])} de folga sobre o efetivo.")
          + (" ⛔ **Uma carteira com colchão grande passa no teto do credor por mérito alheio.**"
             if c["colchao_segura_o_teto"] else ""))
    if equil > c["preco"]:
        A("")
        A(f"> ⛔ **O equilíbrio ({br(equil)}) está ACIMA do preço ({br(c['preco'])}).** "
          "Este deal nasce negativo. Reduza cadência, reduza régua, ou reprecifique.")
    if recuperacao and fee:
        A("")
        S("Custo para o credor, por R$ 1 recuperado")
        A("")
        A("| Cenário | Fixo | Variável | Fatura | Custo/R$1 |")
        A("|---|--:|--:|--:|--:|")
        b = P["banda_gatilho"]
        for lab, d, aj in (("Desempenho −20%", 0.8, -b), ("Na meta", 1.0, 0.0), ("Desempenho +20%", 1.2, b)):
            rec = recuperacao * d
            var = rec * (fee / 100) * (1 + aj)
            fat = c["receita"] + var
            marca = "**" if lab == "Na meta" else ""
            A(f"| {marca}{lab}{marca} | {br(c['receita'])} | {br(var)} | {br(fat)} | "
              f"{marca}R$ {num(fat/rec, 3)}{marca} |")
        A("")
        A("> Compare com o teto que o credor pratica (referência de mercado: **R$ 0,30**). "
          "A soma fixo + variável fica cara justamente quando a operação vai mal, que é quando o "
          "gatilho para baixo já está agindo.")
    if premio:
        A("")
        S("Prêmio de risco — o que custa cotar na base")
        A("")
        A(f"O preço de **{br(premio['preco_base'])}** entrega {premio['alvo']*100:.0f}% no "
          f"cenário BASE. No pessimista, o mesmo preço entrega "
          f"**{premio['margem_pessimista_no_preco_base']*100:+.1f}%** — "
          f"{num(premio['pontos']*100, 1)} pontos a menos.")
        A("")
        A("| | Custo | Preço a este alvo |")
        A("|---|--:|--:|")
        A(f"| Base (realização medida) | {br(premio['custo_base'])} | {br(premio['preco_base'])} |")
        A(f"| Pessimista | {br(premio['custo_pessimista'])} | **{br(premio['preco_pessimista'])}** |")
        A(f"| **Prêmio de risco** | | **{br(premio['premio'])}** "
          f"({premio['premio_pct']*100:+.1f}%) |")
        A("")
        A("> Num contrato de **valor fixo** o desvio de execução é risco NOSSO, e o cenário "
          "pessimista não é exótico: é a régua contratada realizada cheia, meio telefone a "
          "mais por CPF e a cadência sem corte — o que acontece quando o credor usa o que "
          "contratou. Cotar na base é absorver a distância inteira. Num **híbrido** o prêmio "
          "pode ser menor, porque a variável acompanha a execução.")
    if curva:
        A("")
        S("Preço por volume — e por que não há desconto de escala")
        A("")
        A("| CPFs | UCCs | Custo | Preço/unidade | Preço/CPF | Rateio/CPF |")
        A("|--:|--:|--:|--:|--:|--:|")
        for l in curva:
            A(f"| {num(l['cpfs'])} | {l['uccs']} | {br(l['custo'])} | {br(l['preco'])} | "
              f"R$ {num(l['por_cpf'], 2)} | R$ {num(l['rateio_por_cpf'], 3)} |")
        A("")
        A("> ⛔ **O rateio do compartilhado NÃO dilui.** Acima de 3.000 CPFs ele é "
          "**R$ 0,344 por CPF, constante**, porque `max(3%; 1% a cada 1.000 CPFs)` cresce na "
          "mesma proporção da base. O único trecho com ganho real é abaixo de 3.000, onde o "
          "piso de 3% é maior que o proporcional; daí para cima o preço por CPF **sobe**, "
          "porque o degrau de IRPJ entra. Desconto por volume concedido aqui é margem "
          "entregue, não diluição repassada.")
    if torn:
        A("")
        S("O que mais move a margem")
        A("")
        A(f"Margem de partida: **{torn['base']*100:+.1f}%**. Cada linha move **um** parâmetro.")
        A("")
        A("| Alavanca | De | Para | Margem | Δ | Procedência |")
        A("|---|--:|--:|--:|--:|---|")
        for l in torn["linhas"]:
            A(f"| {l['rotulo']} | {num(l['de'], 2)} | {num(l['para'], 2)} | "
              f"{l['margem']*100:+.1f}% | **{l['delta']*100:+.1f} p.p.** | `{l['procedencia']}` |")
        A("")
        A("> A banda move quatro alavancas juntas e responde *qual é o risco*; esta tabela "
          "responde *qual parâmetro merece atenção*. ⛔ Repare que as maiores são todas de "
          "acionamento por CPF e **nenhuma é o preço da unidade** — e a maior sob nosso "
          "controle é `tabela` de fornecedor, nunca conferida contra fatura.")
    if repac:
        A("")
        S("Repactuação — como assinado × recotado hoje")
        A("")
        A("| | Assinado | Recotado hoje |")
        A("|---|--:|--:|")
        a_, h_ = repac["assinado"], repac["hoje"]
        A(f"| Unidades | {a_['uccs']} | {h_['uccs']} |")
        A(f"| CPFs por unidade | {num(a_['cpfs_por_ucc'])} | {num(h_['cpfs_por_ucc'])} |")
        A(f"| Preço por unidade | {br(a_['preco'])} | {br(h_['preco'])} |")
        A(f"| Receita | {br(a_['receita'])} | {br(h_['receita'])} |")
        A(f"| Custo | {br(a_['custo'])} | {br(h_['custo'])} |")
        A(f"| Resultado | {br(a_['resultado'])} | {br(h_['resultado'])} |")
        A(f"| **Margem** | **{a_['margem']*100:+.1f}%** | **{h_['margem']*100:+.1f}%** |")
        A("")
        A(f"> O contrato assinado roda as unidades **{repac['excesso_por_unidade']*100:+.0f}%** "
          f"acima do tamanho de hoje, e **manter como está custa "
          f"{br(repac['custo_de_manter'])}/mês** contra o mesmo escopo redimensionado. "
          "Manter acordo em vigor pode ser a decisão certa — o que não pode é a renovação "
          "chegar sem este número pronto.")
    if proj:
        A("")
        S("Os 12 meses — maturação da carteira e payback")
        A("")
        A(f"Regime: **{br(proj['regime'])}/mês**. Setup: **{br(proj['setup'])}**, desembolso "
          f"único no mês 1.")
        A("")
        A("Um acordo de *k* parcelas entrega 1/*k* do valor no mês em que é fechado e o resto "
          "nos seguintes. A carteira não nasce em regime: ela **matura**. E o custo não espera "
          "— discamos a base inteira já no mês 1.")
        A("")
        # O que a curva espalha é o NEGOCIADO, e é sobre ele que a alíquota incide.
        if c["rec_face_total"]:
            if c["desconto_efetivo"] > 0:
                A(f"O que a curva espalha é o **valor negociado**: de {br(c['rec_face_total'])} "
                  f"de face, o desconto de **{pct(c['desconto_efetivo'], 1).lstrip('+')}** deixa "
                  f"**{br(c['rec_base_total'])}** — e é sobre esses que a alíquota do credor "
                  f"incide. Desconto aplicado em: "
                  + ", ".join(f"**{n}**" for n in c["faixas_desconto_face"]) + ".")
            else:
                A(f"O que a curva espalha é o **valor negociado** — {br(c['rec_base_total'])}, "
                  "a base sobre a qual a alíquota do credor incide. Nenhuma faixa abate "
                  "desconto: as taxas informadas já são líquidas (`meta_base_valor = liquida`), "
                  "então o negociado é a própria recuperação observada.")
            if c["faixas_desconto_inerte"]:
                A("")
                A("> ⚠️ **Desconto informado que não abate nada** em "
                  + ", ".join(f"**{n}**" for n in c["faixas_desconto_inerte"])
                  + ": a taxa dessas faixas foi declarada **líquida**, e abater de novo "
                    "descontaria duas vezes. Se a taxa informada for de FACE, troque "
                    "`meta_base_valor` para `face` — a diferença é do tamanho do desconto.")
            A("")
        cab = "| Mês | Maturação | Recuperado | Fixa | Variável | Custo | Resultado | Acumulado |"
        A(cab)
        A("|--:|--:|--:|--:|--:|--:|--:|--:|")
        for l in proj["linhas"]:
            marca = "**" if l["mes"] == proj["payback"] else ""
            A(f"| {marca}{l['mes']}{marca} | {num(l['maturacao']*100, 0)}% | "
              f"{br(l['recuperado'])} | {br(l['receita_fixa'])} | {br(l['variavel'])} | "
              f"{br(l['custo'])} | {br(l['resultado'])} | {marca}{br(l['acumulado'])}{marca} |")
        A("")
        if proj["meses_negativos"]:
            n = proj["meses_negativos"]
            A(f"> ⛔ **O contrato dá prejuízo {'no mês' if len(n) == 1 else 'nos meses'} "
              f"{', '.join(str(x) for x in n)}** — a receita ainda está maturando e o "
              f"acionamento já roda cheio. É caixa que alguém financia, e a bancada estática "
              f"não mostrava isso: nela todo mês é o mês 12.")
        if proj["linhas"]:
            A(f"> O mês 1 fecha **{pct(proj['mes1_vs_regime'], 0)}** contra o regime "
              f"({br(proj['linhas'][0]['resultado'])} × {br(proj['regime'])}).")
        if proj["payback"]:
            A(f"> O contrato devolve o setup no **mês {proj['payback']}**.")
        elif proj["setup"]:
            A(f"> ⛔ **O setup não se paga em {len(proj['linhas'])} meses** — o acumulado fecha "
              f"em {br(proj['acumulado'])}. A unidade é dimensionada NO break-even, então ela "
              "não gera caixa para amortizar entrada nenhuma: ou o setup é cobrado do cliente, "
              "ou sai da margem de outro contrato.")
        if proj["colchao_herdado"]:
            A(f"> O colchão **herdado** ({br(proj['colchao_herdado'])}/mês) entra cheio desde o "
              "mês 1 — é acordo de outra assessoria, já contratado, e não matura. Só o que "
              f"**nós** recuperamos ({br(proj['nosso'])}/mês em regime) segue a curva.")
        if not proj["variavel_ativa"]:
            A("> ⚠️ Projeção **só com a receita fixa**. É a metade menor: com a variável na "
              "meta, o contrato de referência sai de −7,6% para +21,2%.")
        elif not proj["variavel_regime"]:
            A("> ⚠️ **Variável zerada** — nenhuma faixa tem alíquota com recuperação. A "
              "projeção mostra só o fixo, que é a parte que não paga a margem.")
        if not proj["rampa_informada"]:
            A("")
            A("> ⚠️ A **maturação** da carteira já está na conta (medida na nossa operação). O "
              "que continua fora é o ramp-up da *operação* e o churn — sem série histórica, e "
              "quem tiver uma informa em `--rampa`, que multiplica por cima.")
    A("")
    S("Premissas assumidas — escrever na proposta")
    A("")
    A(f"- Régua de **{num(c['tent_contratada'], 2)} tentativas/CPF/dia** "
      f"(realização estimada {c['realizacao']*100:.0f}%)")
    A(f"- Cadência de texto conforme entradas; canais fora disso são cobrados à parte")
    A(f"- Telefones por CPF já refletidos na tentativa efetiva (o discador capeia por linha)")
    if obs:
        for o in obs: A(f"- {o}")
    A("")
    S("Lacunas — não cobertas por este cálculo")
    A("")
    if c["setup_mes"] or c["transbordo"]:
        A("- ⚠️ Setup e/ou transbordo humano entraram com **valor informado**, não medido — "
          "a referência de PA é tabela de mercado")
    else:
        A("- ⛔ Setup, onboarding e transbordo humano **entraram com zero** — se o deal tem "
          "implantação ou posição humana, informe (`--setup`, `--pas`)")
    A("- ⛔ Prazo de contrato, reajuste, ramp-up da unidade nova e churn — sem série histórica")
    A("- ⛔ Escada de desconto por volume — a justificativa econômica existe, o degrau não")
    if c["alvo"] is None:
        A("- ⚠️ Preço **fixado à mão**; para derivá-lo do custo use `--alvo`")
    if sum(1 for n, v, _ in c["linhas"] if n in ("WhatsApp", "SMS", "E-mail") and v > 0) > 0:
        A("- ⚠️ Preços de mensageria são **tabela de fornecedor**, não medição própria — "
          "a operação medida é predominantemente de voz")
    return "\n".join(L)

# ── proposta ao cliente ───────────────────────────────────────────────────────
# ⛔ A proposta diz PREÇO e ESCOPO. Custo, margem, equilíbrio, rateio e tributo são
# conta nossa e não atravessam para cá. A regra é velha; o que é novo é ela passar a
# ser CONFERIDA — ver `_conferir_proposta`, que recusa o texto em vez de avisar.

# vocabulário que não pode aparecer num documento de cliente: ou expõe a nossa conta,
# ou é identificador técnico (a regra permanente de 18/08 do projetos_coral)
PROIBIDO = (
    "custo", "margem", "break-even", "breakeven", "equilíbrio", "equilibrio",
    "rateio", "compartilhado", "tributo", "tributár", "irpj", "lucro presumido",
    "âncora", "ancora", "capacidade ociosa", "coeficiente",
    "bigquery", "motherduck", "mart_", "fct_", "stg_", "dim_", "sub_portfolio",
    "ucc_calc", "duckdb", "vercel", "verso", "vectra", "sinergytech", "khomp", "vonex",
)


def _conferir_proposta(texto, c):
    """Recusa a proposta se ela vazar a nossa conta. Falha, não avisa.

    Um gerador que PODE vazar é pior que um humano escrevendo à mão, porque o humano
    lê o que escreveu. Duas checagens:
      · vocabulário proibido — custo, margem, tributo, nome de tabela, de fornecedor;
      · os VALORES da conta interna, formatados como aparecem na planilha. O preço e o
        total passam de propósito: são a oferta.
    """
    baixo = texto.lower()
    achados = [t for t in PROIBIDO if t in baixo]

    # o preço e o total SÃO a oferta e aparecem de propósito. Um valor interno que
    # calhe de bater com eles não é vazamento — e acusar isso mataria o guard pelo lado
    # do alarme falso. Acontece de verdade: com 5 unidades a 20%, o resultado do mês dá
    # exatamente o preço de uma unidade, porque 5 × 0,20 = 1.
    permitidos = {br(c["preco"]), br(c["preco"] * c["uccs"])}
    proibidos_num = {
        "o custo medido": c["custo_medido"],
        "a capacidade": c["capacidade"], "o equilíbrio": c["equilibrio"],
        "o tributo": c["tributo"], "o telecom medido": c["tel_med"],
        "o resultado": c["liquida"] - c["custo_medido"],
    }
    for rot, v in proibidos_num.items():
        if v and br(v) in texto and br(v) not in permitidos:
            achados.append(f"{rot} ({br(v)})")

    if achados:
        raise SystemExit(
            "⛔ A proposta vazaria a conta interna e NÃO foi escrita.\n   "
            + "\n   ".join(f"· {a}" for a in achados)
            + "\n   Proposta diz preço e escopo. O resto é planilha.")
    return texto


# ── HÍBRIDO COM GATILHO ──────────────────────────────────────────────────────────
# `fatura = fixo + Σ_faixa(recuperado × alíquota × (1 + ajuste))`, com o gatilho na
# ALÍQUOTA e não no R$ — senão a superação é paga duas vezes, porque o R$ já cresce com
# o volume. Meta = % recuperado sobre a carteira distribuída da faixa, e é a OBSERVADA,
# nunca a declarada (no contrato de referência a declarada é 1,97× a observada, e com ela
# o gatilho nasce cravado no piso todo mês, virando desconto fixo).
#
# ⚠️ Esta conta viveu só no JS do simulador até 15/09/2026 — fora do `ucc_calc.py` e fora
#    do harness. Entrou aqui para ficar sob a mesma regra do resto: escrita duas vezes,
#    conferida por harness, nunca por leitura.
GATILHO = {"banda": 0.15, "piso": 0.85, "teto": 1.15, "morta": 0.0}


def ajuste_gatilho(a, banda=None, piso=None, teto=None, morta=None):
    """Quanto a alíquota se move para um atingimento `a` da meta (1,0 = na meta).

    Dois eixos que não são a mesma coisa: `a` é DESEMPENHO (quanto a recuperação desviou);
    o retorno é o movimento da ALÍQUOTA, limitado a ±`banda`. Entre `piso` e `teto` o
    ajuste é linear; fora deles satura. A `morta` é a banda em torno da meta onde nada se
    move — sem ela, ruído mensal vira dinheiro trocando de mão todo mês.
    """
    b = GATILHO["banda"] if banda is None else banda
    p = GATILHO["piso"] if piso is None else piso
    t = GATILHO["teto"] if teto is None else teto
    m = GATILHO["morta"] if morta is None else morta
    if abs(a - 1) <= m:
        return 0.0
    if a < 1:
        lo = 1 - m
        return -b if a <= p else -b * (lo - a) / (lo - p)
    hi = 1 + m
    return b if a >= t else b * (a - hi) / (t - hi)


def apurar(c, d=1.0, **kw):
    """Apura a variável do credor com o desempenho `d` (1,0 = na meta observada)."""
    lf = c.get("faixas") or []
    linhas = []
    for l in lf:
        rec = l["recuperado"] * d
        aj = ajuste_gatilho(d, **kw) if l["recuperado"] > 0 else 0.0
        linhas.append({**l, "rec": rec, "aj": aj,
                       "var_meta": l["recuperado"] * l["aliq"],
                       "variavel": rec * l["aliq"] * (1 + aj)})
    recuperado = sum(l["rec"] for l in linhas)
    variavel = sum(l["variavel"] for l in linhas)
    carteira = sum(l["carteira"] for l in lf)
    return dict(linhas=linhas, recuperado=recuperado, variavel=variavel, carteira=carteira,
                fee_efetivo=(variavel / recuperado) if recuperado else 0.0,
                nivel=(recuperado / carteira) if carteira else 0.0)


def nivel_que_fura(c, fixo=None, **kw):
    """Abaixo de que nível de recuperação a SOMA fixo+variável fura o teto de R$ 0,30/R$ 1.

    A objeção clássica ao híbrido por soma. Refeita na carteira certa, ela só morde quando
    a operação vai mal — que é exatamente quando o gatilho para baixo já está agindo.
    Devolve `None` quando o teto nunca é furado, ou quando é furado em todo o intervalo.
    """
    f = c["receita"] if fixo is None else fixo

    def custo1(d):
        a = apurar(c, d, **kw)
        return (f + a["variavel"]) / a["recuperado"] if a["recuperado"] > 0 else float("inf")

    if custo1(0.01) < P["teto_por_real"]:
        return None
    lo, hi = 0.01, 20.0
    if custo1(hi) > P["teto_por_real"]:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if custo1(mid) > P["teto_por_real"]:
            lo = mid
        else:
            hi = mid
    return apurar(c, hi, **kw)["nivel"]


def hibrido(c, desempenho=0.0, **kw):
    """Os cenários do híbrido: só fixo · na meta · no desempenho pedido · ±20%.

    Os cenários usam ±20% de desempenho porque, sob a regra sugerida (85% → piso,
    115% → teto), esse desvio já SATURA o gatilho. As duas alavancas multiplicam:
    0,80 × 0,85 = 0,68 (−32%) e 1,20 × 1,15 = 1,38 (+38%).
    """
    # ⚠️ o `calcular` chama o custo de `custo_medido`; o motor do simulador chama `custo`.
    #    Aceitar os dois nomes aqui é o que impede a ponte de virar uma terceira conta.
    fixo = c["receita"]
    custo = c["custo_medido"] if "custo_medido" in c else c["custo"]

    def linha(rec, variavel):
        fat = fixo + variavel
        return dict(rec=rec, variavel=variavel, fatura=fat,
                    margem=((fat - tributo_de(fat, c.get("receita_base", 0.0) or 0.0) - custo) / fat)
                    if fat else 0.0,
                    por_real=(fat / rec) if rec else 0.0)

    M = apurar(c, 1.0, **kw)
    A = apurar(c, 1 + desempenho, **kw)
    Lo = apurar(c, 0.8, **kw)
    Hi = apurar(c, 1.2, **kw)
    return dict(
        fixo=fixo, custo=custo, desempenho=desempenho,
        meta_observada=M["nivel"], fee_efetivo=M["fee_efetivo"],
        so_fixo=linha(M["recuperado"], 0.0),
        na_meta=linha(M["recuperado"], M["variavel"]),
        cenario=linha(A["recuperado"], A["variavel"]),
        abaixo=linha(Lo["recuperado"], Lo["variavel"]),
        acima=linha(Hi["recuperado"], Hi["variavel"]),
        ajuste=ajuste_gatilho(1 + desempenho, **kw),
        nivel_que_fura=nivel_que_fura(c, fixo, **kw),
        # faixa que responde por menos de 1% da recuperação: meta ali não mede nada
        sem_massa=[l["nome"] for l in M["linhas"]
                   if M["recuperado"] > 0 and l["recuperado"] / M["recuperado"] < 0.01],
        linhas=M["linhas"])


def nivel_de_ativacao(c):
    """Sob a regra MAX, em que nível de recuperação o success fee supera o mínimo.

    O furo §5.2 foi descoberto na conta, DEPOIS de assinar: com fee blended de 6,27% e
    `MAX(mínimo; success fee)`, o variável do contrato de referência só passava o mínimo a
    **7,99%** de recuperação sobre a carteira — acima da meta que o próprio credor declara.
    Contrato de valor fixo com tabela decorativa.

    Devolve o nível de ativação e o nível OBSERVADO (a recuperação que as faixas de fato
    entregam), que é a comparação que decide. `None` quando não há carteira nem alíquota
    para calcular — "não sabemos" e "não ativa" são coisas diferentes.
    """
    lf = c.get("faixas") or []
    cart = sum(l["carteira"] for l in lf)
    if not cart:
        return None
    var = sum(l["recuperado_novo"] * c.get("captura", 1.0) * l["aliq"] for l in lf)
    rec = sum(l["recuperado"] for l in lf)
    observado = rec / cart
    fee = (var / rec) if rec else 0.0            # fee blended sobre o recuperado
    minimo = c["receita"]
    if fee <= 0:
        return dict(observado=observado, fee=0.0, ativa_em=None, minimo=minimo, ativa=False)
    ativa_em = minimo / (fee * cart)             # % da carteira em que o variável = mínimo
    return dict(observado=observado, fee=fee, ativa_em=ativa_em, minimo=minimo,
                ativa=ativa_em <= observado,
                razao=(ativa_em / observado) if observado else None)


def _conferir_hibrido(c):
    """O híbrido só se sustenta onde a alíquota encontra recuperação.

    ⛔ Uma tabela de êxito cujas faixas com alíquota recuperam ZERO é decorativa: o
    variável nunca ativa e o contrato é de valor fixo com uma tabela de enfeite. Já
    aconteceu — o contrato de referência foi assinado assim e o furo apareceu depois.
    Oferecer isso é prometer um upside que a própria carteira do credor diz não existir,
    então a proposta não sai; volta para a mesa.
    """
    if not c["faixas"]:
        raise SystemExit(
            "⛔ Híbrido sem a carteira aberta por faixa de atraso. A meta do gatilho é por "
            "faixa — sem o aging não há meta defensável. Use a modalidade fixa ou peça o aging.")
    vivas = [l for l in c["faixas"] if l["aliq"] > 0 and l["meta"] > 0]
    if vivas:
        # ── 2º modo de falha (parecer 14/09, item `variavel`) ──
        # A tabela cruza com recuperação, mas sob MAX o variável só supera o mínimo num
        # nível que a carteira do credor nunca entregou. Foi assim no contrato de
        # referência: ativa a 7,99% contra 3,68% observados. A tabela existe, o upside
        # não — e o furo só apareceu DEPOIS de assinar. Agora aparece antes.
        a = nivel_de_ativacao(c)
        if a and a["ativa_em"] and not a["ativa"]:
            raise SystemExit(
                "⛔ Sob MAX(mínimo; success fee) o variável deste contrato NUNCA ativaria — "
                "a proposta não foi escrita.\n"
                f"   · ativa a partir de {a['ativa_em']*100:.2f}% de recuperação sobre a carteira\n"
                f"   · a carteira do credor entrega {a['observado']*100:.2f}% (observado, por faixa)\n"
                f"   · são {a['razao']:.2f}× o que a operação dele de fato faz\n"
                "   É contrato de valor fixo com tabela de enfeite — o mesmo furo do contrato "
                "de referência, achado depois de assinar.\n   Saídas: modalidade FIXA, ou o "
                "híbrido por SOMA (em que o variável sempre acompanha), ou recalibrar a tabela "
                "com o credor.")
        return
    com_aliq = [l["nome"] for l in c["faixas"] if l["aliq"] > 0]
    com_meta = [l["nome"] for l in c["faixas"] if l["meta"] > 0]
    raise SystemExit(
        "⛔ O variável deste híbrido NUNCA ativaria — a proposta não foi escrita.\n"
        f"   · faixas com alíquota: {', '.join(com_aliq) or 'nenhuma'}\n"
        f"   · faixas que recuperam: {', '.join(com_meta) or 'nenhuma'}\n"
        "   Não há interseção: a tabela de êxito cobre justamente onde a carteira não "
        "devolve nada.\n   Isso é contrato de valor fixo com tabela de enfeite. Leve o "
        "achado ao credor antes de propor — ou proponha a modalidade fixa.")


def proposta(c, cliente="—", modalidade="fixo", validade=None, obs=None):
    """Proposta comercial a partir do MESMO objeto que gerou a planilha.

    Escrever à mão a partir da planilha é como o número diverge: alguém arredonda, alguém
    copia a versão anterior. Aqui a proposta e a planilha saem do mesmo `calcular`.
    """
    L = []
    A = L.append
    sec = iter(range(1, 20))

    def S(titulo):
        A("")
        A(f"## {next(sec)}. {titulo}")
        A("")

    if modalidade != "fixo":
        _conferir_hibrido(c)
    total = c["preco"] * c["uccs"]
    u = c["uccs"]
    un = "unidade" if u == 1 else "unidades"

    A(f"# Proposta comercial — {cliente}")
    A("")
    A(f"**Coral** · operação de cobrança digital ponta a ponta"
      + (f" · validade {validade}" if validade else ""))

    S("O que a unidade entrega")
    A("Cada unidade opera a carteira inteira que ela cobre, do contato à confirmação do acordo:")
    A("")
    A("- **Contato multicanal** — voz com bot próprio, WhatsApp, SMS e e-mail na mesma jornada, "
      "com transbordo para atendimento humano quando o caso pede.")
    A("- **Inteligência de acionamento** — segmentação da carteira, priorização por propensão e "
      "teste A/B contínuo de oferta, horário e cadência.")
    A("- **Operação assistida** — monitoramento do discador em tempo real, com correção "
      "automática de ritmo e de rota ao longo do dia.")
    A("- **Prestação de contas** — painel de acompanhamento e relatório periódico com o funil "
      "aberto: ligações, contato efetivo, acordos e pagamentos.")

    S("Dimensionamento")
    if c["faixas"]:
        A(f"A carteira apresentada tem **{num(c['cpfs'])} CPFs** distribuídos em "
          f"{len(c['faixas'])} faixas de atraso"
          + (f", com **{num(c['entrada_mes'])} entrando por mês** nas faixas curtas"
             if c.get("entrada_mes") else "") + ".")
    else:
        A(f"A carteira apresentada tem **{num(c['cpfs'])} CPFs**.")
    A("")
    A(f"Uma unidade cobre até **{num(P['tam_ucc'])} CPFs** com a jornada completa. "
      f"Esta carteira pede **{u} {un}**.")
    A("")
    A(f"| | |")
    A(f"|---|--:|")
    A(f"| CPFs na carteira | **{num(c['cpfs'])}** |")
    A(f"| Unidades | **{u}** |")
    A(f"| Ocupação | {num(c['ocupacao']*100, 0)}% |")
    A("")
    A("Não vendemos unidade acima do tamanho: acima dele a jornada perde intensidade por CPF "
      "e a carteira passa a ser trabalhada pela metade sem ninguém perceber.")

    S("Investimento")
    A(f"| | |")
    A(f"|---|--:|")
    A(f"| Por unidade | **{br(c['preco'])}** /mês |")
    A(f"| Unidades | {u} |")
    A(f"| **Total mensal** | **{br(total)}** |")
    A("")
    if modalidade == "fixo":
        A("**Valor fixo.** O mesmo valor todo mês, independente do volume recuperado. É a "
          "modalidade indicada para carteira sem histórico de recuperação por faixa — sem essa "
          "série não há meta defensável para um componente variável, e meta mal calibrada vira "
          "desconto disfarçado ou cobrança indevida.")
    else:
        A("**Híbrido.** O valor fixo acima **mais** a remuneração variável que vocês já praticam "
          "por faixa de atraso, com um ajuste de até ±15% na alíquota conforme a recuperação "
          "fique acima ou abaixo da meta da faixa.")
        A("")
        A("A meta de cada faixa é a **recuperação observada** dela, apurada no histórico que "
          "vocês compartilharem — não uma meta declarada. Meta em cima de expectativa deixa o "
          "ajuste cravado no piso todos os meses, o que é desconto fixo e não gatilho.")
        fx = [l for l in c["faixas"] if l["aliq"] > 0]
        if fx:
            A("")
            A("| Faixa | Alíquota | Meta observada |")
            A("|---|--:|--:|")
            for l in fx:
                A(f"| {l['nome']} | {num(l['aliq']*100, 1)}% | "
                  + (f"{num(l['meta']*100, 1)}%" if l["meta"] else "a apurar") + " |")

    S("Premissas")
    A("O preço acima vale sob estas condições. Elas estão escritas porque é o que dá base a uma "
      "conversa de reajuste, para os dois lados — se a intensidade mudar, muda a conta.")
    A("")
    A("| Premissa | Valor |")
    A("|---|--:|")
    A(f"| Tentativas de voz por CPF por dia | **{num(c['regua'], 1)}** |")
    A(f"| Telefones por CPF no mailing | **{num(c.get('tel', 1.0), 1)}** |")
    for rot, v in (("WhatsApp", c["cad"]["wa"]), ("SMS", c["cad"]["sms"]),
                   ("E-mail", c["cad"]["email"])):
        A(f"| {rot} por CPF por mês | " + (f"**{num(v, 1)}**" if v else "não contratado") + " |")
    A("")
    A("O discador aplica o limite de tentativas **por linha**, não por titular. Um CPF com dois "
      "telefones consome o dobro da régua — por isso telefones por CPF é premissa, e não "
      "detalhe. Se o mailing entregue tiver mais telefones que o previsto aqui, revisamos juntos "
      "antes de subir a operação.")

    S("O que está fora")
    A("- **Implantação e integração** — orçadas à parte, conforme o escopo de integração.")
    A("- **Posições humanas dedicadas** — o transbordo previsto atende exceção; operação "
      "assistida por pessoas em volume é escopo separado.")
    fora = [rot for rot, v in (("WhatsApp", c["cad"]["wa"]), ("SMS", c["cad"]["sms"]),
                               ("e-mail", c["cad"]["email"])) if not v]
    if fora:
        A(f"- **{' · '.join(fora)}** — não contratado nesta jornada. Incluir muda a premissa "
          "de cadência e o valor.")
    A("- **Ações judiciais e cobrança presencial.**")

    S("Próximos passos")
    A("1. Validação das premissas de régua, cadência e telefones por CPF sobre o mailing real.")
    A("2. Alinhamento de integração: recebimento da carteira, retorno de acordos e pagamentos.")
    A("3. Piloto com a carteira acordada e leitura conjunta do funil na primeira quinzena.")

    if obs:
        S("Observações")
        A(obs)

    return _conferir_proposta("\n".join(L), c)

# ── registro da cotação ───────────────────────────────────────────────────────
# Um arquivo por cotação, com as entradas, o que saiu, e a VERSÃO DOS PARÂMETROS.
# O parâmetro é a parte que se perde: o contrato de referência foi assinado quando a
# unidade tinha 3.000 CPFs e hoje roda 20% acima do tamanho, e nenhum documento diz
# isso porque o número registrado era "2 unidades", que envelheceu em silêncio.
#
# Por isso o arquivo carrega um bloco legível por máquina e existe o `--reler`: um
# documento que ninguém reabre não previne nada.

REGISTRO_VERSAO = 1


def _slug(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t or "sem-nome"


def _entradas(c, extras=None):
    """As entradas que reproduzem a cotação. Sai do objeto, não de quem chamou."""
    e = dict(cpfs=c["cpfs"], regua=c["regua"], telefones=c["tel"],
             wa=c["cad"]["wa"], sms=c["cad"]["sms"], email=c["cad"]["email"],
             alvo=c["alvo"], preco=c["preco"], receita_base=c["receita_base"],
             ancora=(c["ancora"] if c["ancora_propria"] else None),
             setup_mes=c["setup_mes"], transbordo=c["transbordo"],
             faixas=[{k: l[k] for k in ("nome", "cpfs", "entrada_mes", "carteira",
                                        "carteira_entrada", "base_meta", "meta", "aliq",
                                        "regua", "wa", "sms", "email")}
                     for l in c["faixas"]])
    e.update(extras or {})
    return e


def registro(c, cliente="—", modalidade="fixo", quando=None, decisao=None):
    """Markdown da cotação, com o bloco de reprodução no fim."""
    import json
    from datetime import date
    quando = quando or date.today().isoformat()
    L = []
    A = L.append

    A(f"# Cotação — {cliente}")
    A("")
    A(f"**{quando}** · modalidade {modalidade} · registro v{REGISTRO_VERSAO}")
    A("")
    A("> **Interno.** Contém custo e margem. Releia com "
      "`python3 ucc_calc.py --reler <este arquivo>` — é o `--reler` que acusa parâmetro "
      "movido desde a cotação, não a leitura do texto.")

    A("")
    A("## O que saiu")
    A("")
    A("| | |")
    A("|---|--:|")
    A(f"| Preço por unidade | **{br(c['preco'])}** |")
    A(f"| Unidades | **{c['uccs']}** |")
    A(f"| Total mensal | **{br(c['preco'] * c['uccs'])}** |")
    A(f"| Margem pela medição | **{num(c['margem_medido']*100, 1)}%** |")
    A(f"| Custo pela medição | {br(c['custo_medido'])} |")
    A(f"| Equilíbrio por unidade | {br(c['equilibrio'])} |")
    rot = {"ancora": "âncora", "teto_por_real": "teto por R$ 1 recuperado",
           "margem_alvo": "margem alvo"}[c["restricao"]]
    fura = c["restricao_folga"] < 0
    A(f"| Restrição ativa | **{rot}** — {br(abs(c['restricao_folga']))} "
      + ("acima" if fura else "de folga") + " |")

    A("")
    A("## O que foi informado")
    A("")
    A("| Entrada | Valor |")
    A("|---|--:|")
    A(f"| CPFs | {num(c['cpfs'])} |")
    A(f"| Régua de tentativas/dia | {num(c['regua'], 1)} |")
    A(f"| Telefones por CPF | {num(c['tel'], 2)} |")
    A(f"| WhatsApp · SMS · e-mail por mês | {num(c['cad']['wa'],1)} · "
      f"{num(c['cad']['sms'],1)} · {num(c['cad']['email'],1)} |")
    A(f"| Margem alvo | " + (f"{num(c['alvo']*100, 0)}%" if c["alvo"] is not None
                             else "preço fixado à mão") + " |")
    A(f"| Receita que a Coral já fatura | {br(c['receita_base'])} |")
    A(f"| Âncora | {br(c['ancora'])}"
      + (" (informada pelo credor)" if c["ancora_propria"] else " (genérica)") + " |")
    if c["faixas"]:
        A(f"| Faixas de atraso | {len(c['faixas'])} |")

    assumido = []
    if c["tel"] == 1.0:
        assumido.append("**telefones por CPF = 1,0** — o discador capeia por linha, "
                        "então mailing com 1,6 consome 60% mais régua")
    if not c["ancora_propria"]:
        assumido.append("**âncora genérica** — o que este credor paga hoje não foi informado")
    if c["transbordo"] == 0:
        assumido.append("**transbordo humano = zero**")
    if c["setup_mes"] == 0:
        assumido.append("**sem setup amortizado**")
    if c.get("entrada_sem_valor"):
        assumido.append("**R$ da entrada mensal não informado** em "
                        + ", ".join(c["entrada_sem_valor"])
                        + " — entra no custo e fica fora da recuperação, "
                        "então o preço é teto")
    if assumido:
        A("")
        A("## O que foi assumido, não informado")
        A("")
        for a in assumido:
            A(f"- {a}")

    A("")
    A("## Parâmetros usados nesta cotação")
    A("")
    A("É a parte que envelhece em silêncio. Registrar só \"2 unidades\" não diz nada daqui "
      "a um ano se o tamanho da unidade tiver mudado no meio.")
    A("")
    A("| Parâmetro | Valor |")
    A("|---|--:|")
    for k in ("tam_ucc", "preco_tabela", "bot", "coef_telecom", "wa", "sms", "email",
              "crm_assento", "compart", "rateio_piso", "tributo", "ancora", "teto_por_real"):
        if k in P:
            A(f"| `{k}` | {num(P[k], 4).rstrip('0').rstrip(',') if P[k] < 1 else num(P[k])} |")
    A(f"| realização da régua | {' · '.join(f'{r}→{v*100:.0f}%' for r, v in REALIZACAO.items())} |")

    A("")
    A("## Reprodução")
    A("")
    A("```cotacao")
    A(json.dumps({"versao": REGISTRO_VERSAO, "cliente": cliente, "quando": quando,
                  "modalidade": modalidade,
                  "entradas": _entradas(c),
                  "parametros": {k: P[k] for k in sorted(P)},
                  "realizacao": {str(k): v for k, v in REALIZACAO.items()},
                  "saida": {"preco": c["preco"], "uccs": c["uccs"],
                            "custo_medido": c["custo_medido"],
                            "margem_medido": c["margem_medido"],
                            "restricao": c["restricao"]}},
                 ensure_ascii=False, indent=1))
    A("```")
    if decisao:
        A("")
        A("## Decisão")
        A("")
        A(decisao)
    return "\n".join(L)


def reler(caminho):
    """Roda a cotação de novo com os parâmetros de HOJE e diz o que mudou.

    ⛔ É aqui que o registro deixa de ser documento e vira detector. Um `.md` bonito não
    impede o erro do contrato de referência: impede quem consegue perguntar "se eu
    cotasse isto hoje, sairia o mesmo?" e receber não como resposta.
    """
    import json
    txt = pathlib.Path(caminho).read_text(encoding="utf-8")
    m = re.search(r"```cotacao\n(.*?)\n```", txt, re.S)
    if not m:
        raise SystemExit(f"⛔ {caminho} não tem bloco `cotacao` — não dá para reler.")
    reg = json.loads(m.group(1))
    e = reg["entradas"]

    L = []
    A = L.append
    A(f"# Releitura — {reg['cliente']} (cotado em {reg['quando']})")

    # 1) parâmetros que se moveram
    antes, agora = reg["parametros"], {k: P[k] for k in sorted(P)}
    movidos = [(k, antes[k], agora[k]) for k in sorted(set(antes) | set(agora))
               if antes.get(k) != agora.get(k)]
    A("")
    A("## Parâmetros")
    A("")
    if movidos:
        A("| Parâmetro | Na cotação | Hoje |")
        A("|---|--:|--:|")
        for k, a, b in movidos:
            A(f"| `{k}` | {a if a is not None else '—'} | {b if b is not None else '—'} |")
    else:
        A("Nenhum parâmetro mudou desde a cotação.")

    # 2) o mesmo cálculo, hoje
    fx = [dict(f) for f in e["faixas"]] or None
    c = calcular(cpfs=e["cpfs"], regua=e["regua"], wa=e["wa"], sms=e["sms"], email=e["email"],
                 telefones=e["telefones"], alvo=e["alvo"], preco=e["preco"],
                 receita_base=e["receita_base"], faixas=fx, ancora=e["ancora"])
    s = reg["saida"]
    A("")
    A("## O que sairia hoje")
    A("")
    A("| | Na cotação | Hoje | |")
    A("|---|--:|--:|---|")
    linhas = [("Preço por unidade", s["preco"], c["preco"], br),
              ("Unidades", s["uccs"], c["uccs"], lambda v: num(v)),
              ("Custo pela medição", s["custo_medido"], c["custo_medido"], br),
              ("Margem", s["margem_medido"] * 100, c["margem_medido"] * 100,
               lambda v: num(v, 1) + "%")]
    mudou = False
    for rot, a, b, f in linhas:
        dif = abs(a - b) > max(0.005, abs(a) * 1e-9)
        mudou = mudou or dif
        A(f"| {rot} | {f(a)} | {f(b)} | {'⚠️ mudou' if dif else ''} |")
    if s["restricao"] != c["restricao"]:
        mudou = True
        A(f"| Restrição ativa | {s['restricao']} | {c['restricao']} | ⚠️ mudou |")

    A("")
    if mudou:
        A("> ⚠️ **Esta cotação não se reproduz hoje.** Antes de reusar o número, veja acima o "
          "que se moveu — e se o contrato já foi assinado sob os valores antigos, é o "
          "contrato que está fora do modelo, não o modelo que está errado.")
    else:
        A("> ✅ **Reproduz.** Mesmas entradas, mesmos parâmetros, mesmo número.")
    return "\n".join(L), mudou


def main():
    ap = argparse.ArgumentParser(description="Planilha de precificação UCC")
    ap.add_argument("--cpfs", type=int, default=0,
                    help="base de CPFs; ignorado quando --faixas é usado")
    # obrigatória para cotar, mas não para RELER uma cotação já gravada — ela traz a
    # própria régua no bloco de reprodução. Exigir aqui derrubava o --reler no parser.
    ap.add_argument("--regua", type=float, default=None, help="tentativas/CPF/dia contratadas")
    ap.add_argument("--wa", type=float, default=0, help="disparos WhatsApp por CPF/mês")
    ap.add_argument("--sms", type=float, default=0)
    ap.add_argument("--email", type=float, default=0)
    ap.add_argument("--telefones", type=float, default=1.0, help="telefones por CPF")
    ap.add_argument("--realizacao", type=float, default=None, help="0-1; omite = estimada")
    ap.add_argument("--preco", type=float, default=None, help="preço por UCC (fixado à mão)")
    ap.add_argument("--alvo", type=float, default=None,
                    help="margem alvo em %%; deriva o preço do custo em vez de fixá-lo")
    ap.add_argument("--receita-base", type=float, default=0.0,
                    help="receita mensal que a Coral JÁ fatura — põe o contrato na faixa "
                         "tributária marginal certa (0 = avalia o contrato sozinho)")
    ap.add_argument("--setup", type=float, default=0.0, help="setup/onboarding, valor único")
    ap.add_argument("--setup-meses", type=int, default=12, help="prazo de amortização do setup")
    ap.add_argument("--pas", type=float, default=0, help="posições humanas de transbordo")
    ap.add_argument("--pa-custo", type=float, default=None,
                    help=f"custo por posição (default {P['pa_humana']:.0f})")
    ap.add_argument("--registrar", action="store_true",
                    help="grava a cotação em comercial/cotacoes/<cliente>_<data>.md")
    ap.add_argument("--cotacoes-dir", default="cotacoes",
                    help="pasta do registro (default cotacoes/)")
    ap.add_argument("--decisao", default=None, help="o que foi decidido, para o registro")
    ap.add_argument("--reler", default=None,
                    help="relê uma cotação gravada e diz o que mudou desde então")
    ap.add_argument("--proposta", action="store_true",
                    help="gera a PROPOSTA do cliente (sem custo, sem margem) no lugar da planilha")
    ap.add_argument("--modalidade", choices=("fixo", "hibrido"), default="fixo",
                    help="modalidade da proposta (default fixo)")
    ap.add_argument("--validade", default=None, help="validade da proposta, ex.: '30 dias'")
    # a banda entra por DEFAULT: num contrato de valor fixo o desvio de execução é risco
    # nosso, e um resultado em ponto esconde justamente o que a banda existe para mostrar
    ap.add_argument("--sem-banda", action="store_true",
                    help="omite a banda de execução (ela entra por default)")
    # mesma lógica da banda: discar mais ou menos é decisão recorrente, e esconder a
    # escada atrás de uma flag faz a régua voltar a parecer só despesa
    ap.add_argument("--compart-modelo", default="exclusivo",
                    choices=list(COMPART_MODELOS),
                    help="como a carteira é repartida entre assessorias (default %(default)s)")
    ap.add_argument("--captura", type=float, default=100.0,
                    help="%% da recuperação que esperamos capturar; só vale fora do exclusivo")
    ap.add_argument("--produtos", default="",
                    help="produtos cobertos por esta cotação (item 3 do discovery)")
    ap.add_argument("--entradas", default="",
                    help="entradas mensais dos últimos 6 meses, separadas por vírgula (item 6)")
    ap.add_argument("--colchao-meses", type=float, default=0,
                    help="prazo médio restante das parcelas a vencer (item 9 do discovery)")
    ap.add_argument("--colchao-efic", type=float, default=0,
                    help="%% do colchão que efetivamente entra (item 10); sem os dois o colchão "
                         "fica declarado e FORA da conta")
    ap.add_argument("--curva", action="store_true",
                    help="tabela de preço por volume a margem alvo constante")
    ap.add_argument("--tornado", action="store_true",
                    help="ranking de quanto cada parâmetro, sozinho, move a margem")
    ap.add_argument("--premio-risco", action="store_true",
                    help="preço na base × preço que aguenta o cenário pessimista")
    ap.add_argument("--repactuar", default="",
                    help="compara com o contrato como assinado: UNIDADES:PRECO (ex.: 2:8000)")
    ap.add_argument("--projecao", type=int, default=0,
                    help="meses de projeção com payback do setup (ex.: 12)")
    ap.add_argument("--rampa", default="",
                    help="fatores da rampa por mês, ex.: '0,5;0,8;1' — PREMISSA, não medição")
    ap.add_argument("--maturacao", default="",
                    help="curva de maturação da carteira por mês, ex.: '0,42;0,52;0,60' — "
                         "em branco usa a MEDIDA na Principia. O 1o ponto é o complemento "
                         "do colchão: 41,6%% no mês 1 = 58,4%% de colchão em regime")
    ap.add_argument("--sem-variavel-na-projecao", action="store_true",
                    help="projeta só a receita fixa (o comportamento antigo)")
    ap.add_argument("--sem-escada", action="store_true",
                    help="omite a escada de régua (ela entra por default)")
    ap.add_argument("--voz-piso", type=float, default=VOZ["piso"] * 100,
                    help="%% da recuperação que acontece SEM discagem (default %(default).1f)")
    ap.add_argument("--voz-gamma", type=float, default=VOZ["gamma"],
                    help="retorno por tentativa; 1,0 = proporcional (default %(default).2f)")
    ap.add_argument("--ancora", type=float, default=None,
                    help="o que o credor paga HOJE por unidade equivalente; sem isso, "
                         f"a âncora genérica de R$ {P['ancora']:.0f}")
    ap.add_argument("--recuperacao", type=float, default=None, help="R$ recuperados/mês na meta")
    ap.add_argument("--fee-variavel", type=float, default=None, help="%% blended da tabela do credor")
    ap.add_argument("--faixas", default=None,
                    help="JSON com as faixas de atraso (abre merecimento, DRE com variável e "
                         "corte de cadência por faixa). Ver faixas_exemplo.json")
    ap.add_argument("--elast-wa", type=float, default=ELAST["wa"] * 100,
                    help="%%%% da recuperação perdida ao tirar 1 WhatsApp da base (premissa)")
    ap.add_argument("--elast-sms", type=float, default=ELAST["sms"] * 100)
    ap.add_argument("--elast-email", type=float, default=ELAST["email"] * 100)
    ap.add_argument("--cliente", default="—")
    ap.add_argument("--saida", default=None)
    a = ap.parse_args()

    if a.reler:
        texto, mudou = reler(a.reler)
        print(texto)
        raise SystemExit(1 if mudou else 0)

    if a.regua is None:
        raise SystemExit("⛔ --regua é obrigatória para cotar: é o parâmetro mais pesado do "
                         "modelo, porque dirige telecom e capacidade ao mesmo tempo.")

    faixas = None
    if a.faixas:
        faixas = carregar_faixas(a.faixas, dict(regua=a.regua, wa=a.wa, sms=a.sms, email=a.email))
    c = calcular(a.cpfs, a.regua, a.wa, a.sms, a.email, a.telefones, a.realizacao, a.preco,
                 alvo=(a.alvo / 100 if a.alvo is not None else None),
                 receita_base=a.receita_base, setup=a.setup, setup_meses=a.setup_meses,
                 pas=a.pas, pa_custo=a.pa_custo, faixas=faixas, ancora=a.ancora,
                 compart_modelo=a.compart_modelo, captura=a.captura / 100,
                 colchao_meses=a.colchao_meses, colchao_efic=a.colchao_efic / 100,
                 maturacao=_serie(a.maturacao) or None,
                 produtos=a.produtos, entradas=_serie(a.entradas),
                 elast=dict(wa=a.elast_wa / 100, sms=a.elast_sms / 100, email=a.elast_email / 100))
    cen = None
    if not a.sem_banda:
        cen = banda(preco_base=(a.preco if a.alvo is None else None),
                    cpfs=a.cpfs, regua=a.regua, wa=a.wa, sms=a.sms, email=a.email,
                    telefones=a.telefones,
                    alvo=(a.alvo / 100 if a.alvo is not None else None),
                    receita_base=a.receita_base, setup=a.setup, setup_meses=a.setup_meses,
                    pas=a.pas, pa_custo=a.pa_custo, faixas=faixas, ancora=a.ancora,
                    compart_modelo=a.compart_modelo, captura=a.captura / 100,
                    colchao_meses=a.colchao_meses, colchao_efic=a.colchao_efic / 100,
                    maturacao=_serie(a.maturacao) or None,
                    produtos=a.produtos, entradas=_serie(a.entradas),
                    elast=dict(wa=a.elast_wa / 100, sms=a.elast_sms / 100,
                               email=a.elast_email / 100))
    esc = None
    if not a.sem_escada:
        esc = sensibilidade_regua(
            cpfs=a.cpfs, regua=a.regua, wa=a.wa, sms=a.sms, email=a.email,
            telefones=a.telefones, realizacao=a.realizacao, preco=a.preco,
            alvo=(a.alvo / 100 if a.alvo is not None else None),
            receita_base=a.receita_base, setup=a.setup, setup_meses=a.setup_meses,
            pas=a.pas, pa_custo=a.pa_custo, faixas=faixas, ancora=a.ancora,
            compart_modelo=a.compart_modelo, captura=a.captura / 100,
            colchao_meses=a.colchao_meses, colchao_efic=a.colchao_efic / 100,
            maturacao=_serie(a.maturacao) or None,
            produtos=a.produtos, entradas=_serie(a.entradas),
            elast=dict(wa=a.elast_wa / 100, sms=a.elast_sms / 100, email=a.elast_email / 100),
            voz=dict(piso=a.voz_piso / 100, gamma=a.voz_gamma))

    if a.registrar:
        from datetime import date
        d = pathlib.Path(a.cotacoes_dir)
        d.mkdir(parents=True, exist_ok=True)
        alvo_arq = d / f"{_slug(a.cliente)}_{date.today().isoformat()}.md"
        alvo_arq.write_text(
            registro(c, cliente=a.cliente, modalidade=a.modalidade, decisao=a.decisao) + "\n",
            encoding="utf-8")
        print(f"cotação registrada em {alvo_arq}")

    if a.proposta:
        md = proposta(c, cliente=a.cliente, modalidade=a.modalidade, validade=a.validade)
        rotulo = "proposta"
    else:
        kb = dict(cpfs=a.cpfs, regua=a.regua, wa=a.wa, sms=a.sms, email=a.email,
                  telefones=a.telefones, receita_base=a.receita_base)
        curva = curva_volume(**{k: v for k, v in kb.items() if k != "cpfs"},
                             alvo=(a.alvo / 100 if a.alvo is not None else 0.20)) \
            if a.curva else None
        torn = tornado(**kb) if a.tornado else None
        prem = premio_risco(**kb, alvo=(a.alvo / 100 if a.alvo is not None else 0.20)) \
            if a.premio_risco else None
        rep = None
        if a.repactuar:
            try:
                u_ass, pr_ass = a.repactuar.split(":")
                rep = repactuacao(int(u_ass), float(pr_ass.replace(",", ".")), **kb, faixas=faixas)
            except ValueError:
                raise SystemExit("⛔ --repactuar espera UNIDADES:PRECO, ex.: 2:8000")
        proj = None
        if a.projecao:
            rampa = [float(x.replace(",", ".")) for x in a.rampa.split(";") if x.strip()] \
                if a.rampa else None
            proj = projecao(meses=a.projecao, rampa=rampa, **kb, faixas=faixas,
                            preco=c["preco"], setup=a.setup, setup_meses=a.setup_meses,
                            colchao_meses=a.colchao_meses, colchao_efic=a.colchao_efic / 100,
                            maturacao=_serie(a.maturacao) or None,
                            compart_modelo=a.compart_modelo, captura=a.captura / 100,
                            variavel_ativa=not a.sem_variavel_na_projecao)
        md = planilha(c, a.recuperacao, a.fee_variavel, a.cliente, cenarios=cen, escada=esc,
                      curva=curva, torn=torn, premio=prem, repac=rep, proj=proj)
        rotulo = "planilha"
    if a.saida:
        open(a.saida, "w", encoding="utf-8").write(md + "\n")
        print(f"{rotulo} escrita em {a.saida}")
    else:
        print(md)


if __name__ == "__main__":
    main()
