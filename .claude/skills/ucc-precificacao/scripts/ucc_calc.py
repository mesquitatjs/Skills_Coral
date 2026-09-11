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
from math import ceil

# ─── parâmetros (espelho do dossiê — calibração 10/09/2026) ──────────────────
P = {
    "tam_ucc":        2_500,    # DECIDIDO — é o break-even
    "preco_ucc":      8_000.0,  # DECIDIDO
    "bot":            1_020.0,  # TABELA (custo real) por unidade
    "telecom_fixo":   1_500.0,  # DECIDIDO por unidade — premissa do modelo atual
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
            "meta": float(f.get("meta", 0)) / 100, "aliq": float(f.get("aliq", 0)) / 100,
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


def _acionar(cpfs, regua, telefones, wa, sms, email, realizacao=None):
    """Acionamento de um bloco de CPFs sob uma régua e uma cadência."""
    tent_c = regua * telefones
    r = realizacao if realizacao is not None else realizacao_estimada(regua)
    tent_e = tent_c * r
    return dict(
        tent_contratada=tent_c, realizacao=r, tent_esperada=tent_e,
        telecom=cpfs * P["coef_telecom"] * tent_e,
        msg=cpfs * (wa * P["wa"] + sms * P["sms"] + email * P["email"]),
        crm=cpfs * P["crm_assento"],
    )


def calcular(cpfs, regua, wa, sms, email, telefones=1.0, realizacao=None, preco=None,
             alvo=None, receita_base=0.0, setup=0.0, setup_meses=12, pas=0, pa_custo=None,
             faixas=None, elast=None):
    pa_custo = P["pa_humana"] if pa_custo is None else pa_custo
    elast = elast or ELAST
    if faixas:
        cpfs = sum(f["cpfs"] for f in faixas)   # a soma das faixas é a verdade da carteira
    u = ceil(cpfs / P["tam_ucc"])
    # o discador capeia POR LINHA → telefones/CPF multiplicam a tentativa efetiva
    tent_contratada = regua * telefones
    r = realizacao if realizacao is not None else realizacao_estimada(regua)
    tent_esperada = tent_contratada * r

    setup_mes = (setup / setup_meses) if setup_meses else 0.0
    transbordo = pas * pa_custo

    # ── faixas: cada uma com a sua régua e cadência; o corte é medido contra a CHEIA ──
    lf = []
    for f in (faixas or []):
        a = _acionar(f["cpfs"], f["regua"], telefones, f["wa"], f["sms"], f["email"])
        cheia = _acionar(f["cpfs"], f["regua"], telefones, wa, sms, email)
        perda_frac = (max(0.0, wa - f["wa"]) * elast["wa"]
                      + max(0.0, sms - f["sms"]) * elast["sms"]
                      + max(0.0, email - f["email"]) * elast["email"])
        rec_base = f["carteira"] * f["meta"]
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
    tel_fixo = u * P["telecom_fixo"]
    tel_med = (sum(l["telecom"] for l in lf) if lf
               else cpfs * P["coef_telecom"] * tent_esperada)
    if lf:   # com faixas, mensageria e CRM também saem linha a linha
        for i, (nome, _, nat) in enumerate(linhas):
            if nome == "WhatsApp":  linhas[i] = (nome, sum(l["cpfs"] * l["wa"] for l in lf) * P["wa"], nat)
            if nome == "SMS":       linhas[i] = (nome, sum(l["cpfs"] * l["sms"] for l in lf) * P["sms"], nat)
            if nome == "E-mail":    linhas[i] = (nome, sum(l["cpfs"] * l["email"] for l in lf) * P["email"], nat)

    base = sum(v for _, v, _ in linhas)
    custo_medido, custo_modelo = base + tel_med, base + tel_fixo

    capacidade = sum(v for _, v, n in linhas if n == "Capacidade")
    for l in lf:
        l["capacidade"] = capacidade * l["cpfs"] / cpfs if cpfs else 0.0
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
        linhas=linhas, tel_fixo=tel_fixo, tel_med=tel_med,
        setup_mes=setup_mes, transbordo=transbordo, capacidade=capacidade,
        faixas=lf, elast=elast,
        carteira=sum(l["carteira"] for l in lf),
        recuperado=sum(l["recuperado"] for l in lf),
        rec_base_total=sum(l["rec_base"] for l in lf),
        perda_total=sum(l["perda"] for l in lf),
        economia_total=sum(l["economia"] for l in lf),
        variavel=sum(l["variavel"] for l in lf),
        tributo=tributo, trib_pct=(tributo / receita if receita else P["tributo"]),
        receita_base=receita_base, alvo=alvo,
        custo_modelo=custo_modelo, custo_medido=custo_medido,
        margem_modelo=(liq - custo_modelo) / receita if receita else 0.0,
        margem_medido=(liq - custo_medido) / receita if receita else 0.0,
        equilibrio=preco_do_alvo(custo_medido, u, 0.0, receita_base),
        rateio_frac=max(P["rateio_piso"], cpfs * P["rateio_por_cpf"]),
        tent_contratada=tent_contratada, tent_esperada=tent_esperada, realizacao=r,
        ocupacao=cpfs / (u * P["tam_ucc"]),
    )


def planilha(c, recuperacao=None, fee=None, cliente="—", obs=None):
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
    A(f"| **Telecom — premissa do modelo** <small>fixo/unidade</small> | Capacidade | {br(c['tel_fixo'])} |")
    A(f"| **Telecom — pela medição** <small>0,137 × {num(c['tent_esperada'], 2)}</small> "
      f"| Acionamento | **{br(c['tel_med'])}** |")
    A("")
    A("| Cenário de custeio | Custo | Resultado | Margem |")
    A("|---|--:|--:|--:|")
    A(f"| Pela premissa do modelo | {br(c['custo_modelo'])} | {br(c['liquida']-c['custo_modelo'])} | {pct(c['margem_modelo'])} |")
    A(f"| **Pela medição — use esta** | **{br(c['custo_medido'])}** | **{br(c['liquida']-c['custo_medido'])}** | **{pct(c['margem_medido'])}** |")
    delta = c["tel_med"] - c["tel_fixo"]
    if abs(delta) > 200:
        senso = "SUBESTIMA" if delta > 0 else "superestima"
        A("")
        A(f"> ⚠️ A premissa de telecom fixo **{senso}** o custo em **{br(abs(delta))}/mês** "
          f"({pct(abs(delta)/c['custo_medido'], 1).lstrip('+')} do custo). "
          + ("Cotar pelo modelo antigo aqui é vender no prejuízo." if delta > 0
             else "Há folga que a proposta pode usar."))
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
            linha = (f"| {l['nome']} | {num(l['cpfs'])} | {br(l['carteira'])} | "
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

    A("")
    S("Leitura contra as âncoras")
    A("")
    equil = c["equilibrio"]
    A("| Referência | Valor | Leitura |")
    A("|---|--:|---|")
    A(f"| Preço por unidade | {br(c['preco'])} | |")
    A(f"| Equilíbrio por unidade | {br(equil)} | preço que zera a conta |")
    A(f"| Âncora de mercado | {br(P['ancora'])} | posição humana + plataforma |")
    folga = 1 - equil / P["ancora"]
    A(f"| **Folga até a âncora** | **{folga*100:.0f}%** | espaço para margem, desconto e variação |")
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


def main():
    ap = argparse.ArgumentParser(description="Planilha de precificação UCC")
    ap.add_argument("--cpfs", type=int, default=0,
                    help="base de CPFs; ignorado quando --faixas é usado")
    ap.add_argument("--regua", type=float, required=True, help="tentativas/CPF/dia contratadas")
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

    faixas = None
    if a.faixas:
        faixas = carregar_faixas(a.faixas, dict(regua=a.regua, wa=a.wa, sms=a.sms, email=a.email))
    c = calcular(a.cpfs, a.regua, a.wa, a.sms, a.email, a.telefones, a.realizacao, a.preco,
                 alvo=(a.alvo / 100 if a.alvo is not None else None),
                 receita_base=a.receita_base, setup=a.setup, setup_meses=a.setup_meses,
                 pas=a.pas, pa_custo=a.pa_custo, faixas=faixas,
                 elast=dict(wa=a.elast_wa / 100, sms=a.elast_sms / 100, email=a.elast_email / 100))
    md = planilha(c, a.recuperacao, a.fee_variavel, a.cliente)
    if a.saida:
        open(a.saida, "w", encoding="utf-8").write(md + "\n")
        print(f"planilha escrita em {a.saida}")
    else:
        print(md)


if __name__ == "__main__":
    main()
