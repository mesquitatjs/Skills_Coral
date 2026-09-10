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
"""
import argparse
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
    "tributo":        0.1633,   # TABELA — Lucro Presumido, VÁLIDO ATÉ R$62.500/mês
    "teto_tributo":   62_500.0,
    "ancora":         12_000.0, # DECIDIDO — posição humana + plataforma
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


def calcular(cpfs, regua, wa, sms, email, telefones=1.0, realizacao=None, preco=None):
    preco = preco or P["preco_ucc"]
    u = ceil(cpfs / P["tam_ucc"])
    # o discador capeia POR LINHA → telefones/CPF multiplicam a tentativa efetiva
    tent_contratada = regua * telefones
    r = realizacao if realizacao is not None else realizacao_estimada(regua)
    tent_esperada = tent_contratada * r

    linhas = [
        ("Bot de voz",                 u * P["bot"],                          "Capacidade"),
        ("Rateio do compartilhado",    max(P["rateio_piso"], cpfs * P["rateio_por_cpf"]) * P["compart"], "Capacidade"),
        ("WhatsApp",                   cpfs * wa * P["wa"],                   "Acionamento"),
        ("SMS",                        cpfs * sms * P["sms"],                 "Acionamento"),
        ("E-mail",                     cpfs * email * P["email"],             "Acionamento"),
        ("CRM — assento",              cpfs * P["crm_assento"],               "Acionamento"),
    ]
    tel_fixo = u * P["telecom_fixo"]
    tel_med  = cpfs * P["coef_telecom"] * tent_esperada

    base = sum(v for _, v, _ in linhas)
    receita = u * preco
    liq = receita * (1 - P["tributo"])
    return dict(
        uccs=u, cpfs=cpfs, preco=preco, receita=receita, liquida=liq,
        linhas=linhas, tel_fixo=tel_fixo, tel_med=tel_med,
        custo_modelo=base + tel_fixo, custo_medido=base + tel_med,
        margem_modelo=(liq - base - tel_fixo) / receita,
        margem_medido=(liq - base - tel_med) / receita,
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
    A(f"- Receita: **{br(c['receita'])}/mês** · líquida de tributo "
      f"({num(P['tributo']*100, 2)}%): {br(c['liquida'])}")
    if c["receita"] > P["teto_tributo"]:
        A("")
        A(f"> ⛔ **RECEITA ACIMA DE {br(P['teto_tributo'])}/MÊS.** A alíquota de "
          f"{num(P['tributo']*100, 2)}% vale até esse teto. Acima entra o adicional de IRPJ e a "
          "carga efetiva sobe. **Este número está subestimando o tributo — não cote sem fechar a "
          "alíquota com a contabilidade.**")
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
    A("")
    S("Leitura contra as âncoras")
    A("")
    equil = c["custo_medido"] / (1 - P["tributo"]) / c["uccs"]
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
    A("- ⛔ Setup, onboarding e posição humana de transbordo **não estão precificados**")
    A("- ⛔ Prazo de contrato, reajuste, ramp-up da unidade nova e churn — sem série histórica")
    A("- ⛔ Escada de desconto por volume — a justificativa econômica existe, o degrau não")
    if c["receita"] > P["teto_tributo"]:
        A("- ⛔ **Alíquota tributária acima do teto** (ver Dimensionamento)")
    if sum(1 for n, v, _ in c["linhas"] if n in ("WhatsApp", "SMS", "E-mail") and v > 0) > 0:
        A("- ⚠️ Preços de mensageria são **tabela de fornecedor**, não medição própria — "
          "a operação medida é predominantemente de voz")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Planilha de precificação UCC")
    ap.add_argument("--cpfs", type=int, required=True)
    ap.add_argument("--regua", type=float, required=True, help="tentativas/CPF/dia contratadas")
    ap.add_argument("--wa", type=float, default=0, help="disparos WhatsApp por CPF/mês")
    ap.add_argument("--sms", type=float, default=0)
    ap.add_argument("--email", type=float, default=0)
    ap.add_argument("--telefones", type=float, default=1.0, help="telefones por CPF")
    ap.add_argument("--realizacao", type=float, default=None, help="0-1; omite = estimada")
    ap.add_argument("--preco", type=float, default=None, help="preço por UCC")
    ap.add_argument("--recuperacao", type=float, default=None, help="R$ recuperados/mês na meta")
    ap.add_argument("--fee-variavel", type=float, default=None, help="%% blended da tabela do credor")
    ap.add_argument("--cliente", default="—")
    ap.add_argument("--saida", default=None)
    a = ap.parse_args()

    c = calcular(a.cpfs, a.regua, a.wa, a.sms, a.email, a.telefones, a.realizacao, a.preco)
    md = planilha(c, a.recuperacao, a.fee_variavel, a.cliente)
    if a.saida:
        open(a.saida, "w", encoding="utf-8").write(md + "\n")
        print(f"planilha escrita em {a.saida}")
    else:
        print(md)


if __name__ == "__main__":
    main()
