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


# elasticidade de canal: fração da recuperação perdida ao tirar UM toque da base inteira.
# ⚠️ PREMISSA, não medição nossa — a operação que medimos é predominantemente de voz.
ELAST = {"wa": 0.03, "sms": 0.01, "email": 0.002}


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
        if "cpfs" not in f or not f.get("cpfs"):
            raise SystemExit(
                f"⛔ faixa {i} ({f.get('nome','sem nome')}) sem CPFs. O custo escala com CPF e a "
                "variável com reais — os dois números são entrada obrigatória, e derivar um do "
                "outro por ticket médio uniforme assume algo que o aging costuma desmentir.")
        faixas.append({
            "nome": f.get("nome", f"faixa {i}"),
            "cpfs": float(f["cpfs"]), "carteira": float(f.get("carteira", 0)),
            "entrada_mes": float(f.get("entrada_mes", 0) or 0),
            "carteira_entrada": (float(f["carteira_entrada"])
                                 if f.get("carteira_entrada") is not None else None),
            "meta": float(f.get("meta", 0)) / 100, "aliq": float(f.get("aliq", 0)) / 100,
            "base_meta": str(f.get("base_meta", "trabalhado")).strip().lower(),
            "regua": float(f.get("regua", padrao["regua"])),
            "wa": float(f.get("wa", padrao["wa"])), "sms": float(f.get("sms", padrao["sms"])),
            "email": float(f.get("email", padrao["email"])),
        })
    return faixas


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
    return {**f, "entrada_mes": ent, "carteira_entrada": ce, "base_meta": base,
            "trabalhado": cpfs + ent, "carteira_trab": cart + ce,
            "carteira_meta": carteira_meta, "carteira_entrada_lacuna": lacuna}


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
                "ancora", "transbordo")


def _ficha(cpfs, regua, telefones, wa, sms, email, lf, ancora_propria, transbordo,
           entrada_sem_valor):
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
    }


def calcular(cpfs, regua, wa, sms, email, telefones=1.0, realizacao=None, preco=None,
             alvo=None, receita_base=0.0, setup=0.0, setup_meses=12, pas=0, pa_custo=None,
             faixas=None, elast=None, ancora=None, cenario=None):
    pa_custo = P["pa_humana"] if pa_custo is None else pa_custo
    elast = elast or ELAST
    if faixas:
        faixas = [_normalizar_faixa(f) for f in faixas]
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
        rec_base = f["carteira_meta"] * f["meta"]
        acion = a["telecom"] + a["msg"] + a["crm"]
        lf.append(dict(
            **f, **{k: a[k] for k in ("telecom", "msg", "crm", "tent_esperada")},
            acionamento=acion, rec_base=rec_base, perda_frac=perda_frac,
            perda=rec_base * perda_frac, recuperado=rec_base * (1 - perda_frac),
            economia=(cheia["telecom"] + cheia["msg"] + cheia["crm"]) - acion,
        ))
    linhas = [
        ("Bot de voz",                 u * P["bot"],                          "Capacidade"),
        ("Rateio do compartilhado",    max(P["rateio_piso"], cpfs * P["rateio_por_cpf"]) * P["compart"], "Capacidade"),
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
        l["variavel"] = l["recuperado"] * l["aliq"]

    if alvo is None:
        preco = preco or P["preco_ucc"]
    else:
        preco = preco_do_alvo(custo_medido, u, alvo, receita_base)
    receita = u * preco
    tributo = tributo_de(receita, receita_base)
    liq = receita - tributo
    return dict(
        uccs=u, cpfs=cpfs, preco=preco, receita=receita, liquida=liq,
        linhas=linhas, tel_med=tel_med,
        setup_mes=setup_mes, transbordo=transbordo, capacidade=capacidade,
        faixas=lf, elast=elast,
        carteira=sum(l["carteira_trab"] for l in lf),
        estoque=sum(l["cpfs"] for l in lf), entrada_mes=sum(l["entrada_mes"] for l in lf),
        entrada_sem_valor=[l["nome"] for l in lf if l.get("carteira_entrada_lacuna")],
        recuperado=sum(l["recuperado"] for l in lf),
        rec_base_total=sum(l["rec_base"] for l in lf),
        perda_total=sum(l["perda"] for l in lf),
        economia_total=sum(l["economia"] for l in lf),
        variavel=sum(l["variavel"] for l in lf),
        tributo=tributo, trib_pct=(tributo / receita if receita else P["tributo"]),
        receita_base=receita_base, alvo=alvo,
        custo_medido=custo_medido,
        margem_medido=(liq - custo_medido) / receita if receita else 0.0,
        equilibrio=preco_do_alvo(custo_medido, u, 0.0, receita_base),
        rateio_frac=max(P["rateio_piso"], cpfs * P["rateio_por_cpf"]),
        # o que o credor paga HOJE é a âncora que vale; sem isso, a genérica
        ancora=(ancora if ancora else P["ancora"]), ancora_propria=bool(ancora),
        **_restricao(preco, u, (ancora if ancora else P["ancora"]),
                     sum(l["recuperado"] for l in lf)),
        tent_contratada=tent_contratada, tent_esperada=tent_esperada, realizacao=r,
        # entradas ecoadas: a proposta escreve as premissas, e elas têm de vir do mesmo
        # objeto que gerou o preço — reescrevê-las à mão é como a premissa e a conta divergem
        tel=telefones, cad=dict(wa=wa, sms=sms, email=email), regua=regua,
        ficha=_ficha(cpfs, regua, telefones, wa, sms, email, lf,
                     bool(ancora), transbordo,
                     [l["nome"] for l in lf if l.get("carteira_entrada_lacuna")]),
        ocupacao=cpfs / (u * P["tam_ucc"]),
    )


# ── voz: o que a tentativa a mais faz com a recuperação ──────────────────────
# O corte de CADÊNCIA (WhatsApp/SMS/e-mail) já tinha elasticidade; a RÉGUA não tinha
# nenhuma, então discar mais só aparecia como despesa e discar menos só como economia.
# Duas premissas, as duas com procedência declarada:
#
#   piso  — fração da recuperação que acontece SEM discagem nenhuma. MEDIDO em jul/2026
#           na operação de Receita Garantida: dos R$ 17,15M recuperados, 44,4% foram
#           espontâneos e 99,4% deles sem nenhum toque nosso. Sem esse piso a conta
#           afirma que régua zero recupera zero, que é falso por quase metade.
#   gamma — retorno da tentativa a mais. 1,0 = a parte acionada acompanha a tentativa
#           EFETIVA na proporção. MEDIDO no Ouro: o R$/acordo da faixa cortada é plano
#           de 1 a 10 tentativas (79,17 cortando após a 1ª × 79,09 cortando só a 10ª),
#           e o ROI por faixa cortada replicou o mesmo achado por outra medida.
#           gamma < 1 é o que cria ponto de virada; medimos que não há, até 10.
#
# ⚠️ O retorno decrescente que ESTE modelo tem vem da REALIZAÇÃO (93% na régua 2, 68%
# na 10): subir a régua contratada compra cada vez menos tentativa efetiva. Por tentativa
# efetiva, custo e recuperação andam no mesmo passo — que é o que foi medido.
# ⛔ LACUNA: régua maior exige mais CANAIS, e o de-para bot ↔ canal não existe. A escada
# cobra o telecom da tentativa a mais e NÃO cobra capacidade adicional.
VOZ = {"piso": 0.444, "gamma": 1.0}


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
    regua_base = float(kw.get("regua") or 0)
    if regua_base <= 0:
        return []
    base = calcular(**kw)
    preco_base, u = base["preco"], base["uccs"]
    alvo, rb = kw.get("alvo"), kw.get("receita_base", 0.0)
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
            r = l0["recuperado"] * (piso + (1 - piso) * mult ** gamma)
            rec += r
            var += r * l["aliq"]
        receita = u * preco_base
        liq = receita - tributo_de(receita, rb)
        liq_var = (receita + var) - tributo_de(receita + var, rb)
        return dict(
            regua=rg, realizacao=c["realizacao"], tent_esperada=c["tent_esperada"],
            custo=c["custo_medido"], telecom=c["tel_med"],
            recuperado=rec, variavel=var,
            resultado=liq - c["custo_medido"],
            resultado_var=liq_var - c["custo_medido"],
            preco_alvo=(preco_do_alvo(c["custo_medido"], u, alvo, rb)
                        if alvo is not None else None),
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


def _restricao(preco, u, ancora, recuperado):
    """Qual das três restrições está MORDENDO — e por quanto.

    As três não são do mesmo tipo, e confundi-las é o erro comum:
      · a **margem alvo** empurra o preço PARA CIMA (é o mínimo que a conta pede);
      · a **âncora** e o **teto por R$ 1 recuperado** são TETOS.
    Logo a restrição ativa é o teto mais baixo que o preço do alvo já ultrapassou. Se o
    preço cabe nos dois tetos, quem manda é a própria margem alvo — e aí há folga para
    desconto, que é exatamente a leitura que o comercial precisa antes de negociar.

    O teto por R$ 1 só existe com recuperação informada; sem ela devolve `None` em vez
    de zero, porque "não sabemos" e "não fura" são coisas diferentes.
    """
    teto_r = (P["teto_por_real"] * recuperado / u) if (recuperado > 0 and u) else None
    tetos = [("ancora", ancora)] + ([("teto_por_real", teto_r)] if teto_r else [])
    furados = [(k, v) for k, v in tetos if preco > v]
    if furados:
        k, v = min(furados, key=lambda x: x[1])
        return dict(restricao=k, restricao_teto=v, restricao_folga=v - preco)
    menor = min(v for _, v in tetos)
    return dict(restricao="margem_alvo", restricao_teto=menor, restricao_folga=menor - preco)


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
)


def planilha(c, recuperacao=None, fee=None, cliente="—", obs=None, cenarios=None,
             escada=None):
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
        A("")
        corte = c["economia_total"] > 1
        cab = ("| Faixa | CPFs | Carteira | Recuperado | % recup. | Custo | % custo | R$ por R$ 1 |"
               + (" Economia | Perdido | Perde por R$ 1 |" if corte else ""))
        A(cab)
        A("|---|--:|--:|--:|--:|--:|--:|--:|" + ("--:|--:|--:|" if corte else ""))
        for l in c["faixas"]:
            pr = ("R$ " + num(l["por_real"], 4 if l["por_real"] < 0.1 else 2)
                  if l["por_real"] is not None else "—")
            linha = (f"| {l['nome']} | {num(l['trabalhado'])} | {br(l['carteira_trab'])} | "
                     f"{br(l['recuperado'])} | "
                     f"{num(l['recuperado']/c['recuperado']*100,1) if c['recuperado'] else '0,0'}% | "
                     f"{br(l['custo'])} | {num(l['custo']/c['custo_medido']*100,1)}% | {pr} |")
            if corte:
                linha += (f" {br(l['economia']) if l['economia'] > 0.5 else '—'} |"
                          f" {br(l['perda']) if l['perda'] > 0.5 else '—'} |"
                          f" {'R$ ' + num(l['perda']/l['economia'],2) if l['economia'] > 0.5 else '—'} |")
            A(linha)
        tot = (f"| **Total** | **{num(c['cpfs'])}** | **{br(c['carteira'])}** | "
               f"**{br(c['recuperado'])}** | 100% | **{br(c['custo_medido'])}** | 100% | "
               f"**{'R$ ' + num(c['custo_medido']/c['recuperado'], 4) if c['recuperado'] else '—'}** |")
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
        if acima and tem_rec:
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
        A(f"Piso espontâneo **{num(VOZ['piso']*100, 1)}%** (MEDIDO — jul/2026, Receita "
          f"Garantida) e retorno por tentativa **{num(VOZ['gamma'], 2)}** (1,00 = proporcional, o medido no Ouro "
          "de 1 a 10 tentativas). ⚠️ A recuperação de cada faixa foi observada na operação atual "
          "do credor, que não é a nossa. ⛔ A escada cobra o telecom do degrau e **não** cobra "
          "capacidade adicional — o de-para bot ↔ canal não existe.")

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
    A(f"| Preço por unidade | {br(c['preco'])} | |")
    A(f"| Equilíbrio por unidade | {br(equil)} | preço que zera a conta |")
    A(f"| Âncora de mercado | {br(c['ancora'])} | "
      + ("o que o credor paga hoje |" if c["ancora_propria"]
         else "posição humana + plataforma |"))
    folga = 1 - equil / c["ancora"]
    A(f"| **Folga até a âncora** | **{folga*100:.0f}%** | espaço para margem, desconto e variação |")
    A("")
    rot_r = {"ancora": "a âncora", "teto_por_real": "o teto por R$ 1 recuperado",
             "margem_alvo": "a margem alvo"}[c["restricao"]]
    if c["restricao_folga"] < 0:
        A(f"> ⛔ **Restrição ativa: {rot_r}.** O preço está "
          f"**{br(-c['restricao_folga'])} acima** do teto de {br(c['restricao_teto'])}. "
          "É este número que precisa ceder — não o próximo desconto.")
    elif c["restricao"] == "margem_alvo":
        A(f"> ✅ **Restrição ativa: a margem alvo.** O preço cabe nos dois tetos, com "
          f"**{br(c['restricao_folga'])} de folga** até o mais baixo ({br(c['restricao_teto'])}). "
          "É o espaço que existe para desconto.")
    else:
        A(f"> **Restrição ativa: {rot_r}** — {br(c['restricao_folga'])} de folga.")
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
                 elast=dict(wa=a.elast_wa / 100, sms=a.elast_sms / 100, email=a.elast_email / 100))
    cen = None
    if not a.sem_banda:
        cen = banda(preco_base=(a.preco if a.alvo is None else None),
                    cpfs=a.cpfs, regua=a.regua, wa=a.wa, sms=a.sms, email=a.email,
                    telefones=a.telefones,
                    alvo=(a.alvo / 100 if a.alvo is not None else None),
                    receita_base=a.receita_base, setup=a.setup, setup_meses=a.setup_meses,
                    pas=a.pas, pa_custo=a.pa_custo, faixas=faixas, ancora=a.ancora,
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
        md = planilha(c, a.recuperacao, a.fee_variavel, a.cliente, cenarios=cen, escada=esc)
        rotulo = "planilha"
    if a.saida:
        open(a.saida, "w", encoding="utf-8").write(md + "\n")
        print(f"{rotulo} escrita em {a.saida}")
    else:
        print(md)


if __name__ == "__main__":
    main()
