"""Impressão digital do fluxo de voz — detecta regressão de script e mede falha de ASR por nó.

QA passivo (Fase 0). Lê um corpus de logs já baixados e produz:

  1. FINGERPRINT — por nó: falas do bot, parâmetros de captura, se chama o ASR,
     volume e taxa de falha. É o retrato do fluxo naquele dia/campanha.
  2. DIFF — compara com um fingerprint anterior e aponta o que mudou: nó novo/
     removido, texto trocado, janela de captura alterada, nó que passou a (ou
     deixou de) chamar o ASR, e variação de falha ESTATISTICAMENTE significativa.

Motivação (28/07/2026): o fluxo do PrincipiaPay subiu trocando textos SEM mudar
um único ID de nó. Nada alertou — a mudança só apareceu porque alguém foi olhar.

REGRA DE ATRIBUIÇÃO (a que erramos antes e custou um número errado):
o nó de uma gravação é o `Process node` IMEDIATAMENTE ANTERIOR ao `RecordTemp
audio`, não o seguinte. No log:

    09:39:38.810  Process node '(288) Menu - Anunciadora'
    09:39:38.811  RecordTemp audio          <- gravação do 288
    09:39:42.283  Process node '(5) GPT - Valida Cliente'
    09:39:42.284  RecordTemp audio          <- essa sim é do 5

E gravação SEM linha `Transcription` no bloco não é falha de ASR: pode ser nó de
VAD puro (o (288) grava toda chamada e nunca transcreve). Por isso `chama_asr`
existe — sem ele a falha global dobra.

Uso:
  # retrato de um dia
  python fingerprint_fluxo.py --logs ./logs --saida fp/ [--campanha OURO] [--data 2026-07-23]

  # retrato + comparação com o baseline
  python fingerprint_fluxo.py --logs ./logs_tarde --saida fp/ --comparar fp/PPAY_2026-07-23.json

  # só comparar dois fingerprints já gravados
  python fingerprint_fluxo.py --diff fp/PPAY_2026-07-23.json fp/PPAY_2026-07-28.json

Saída: relatório em texto no stdout e o JSON do fingerprint. Código de saída 2
quando há regressão de script (para encadear em alerta/CI). Só stdlib.

PII: as falas são CANONIZADAS antes de gravar — nome resolvido ("oi BRUNO") e
números viram marcador ({X}/{N}), então o fingerprint é versionável em git.
"""
import argparse, json, math, os, re, sys
from collections import Counter, defaultdict

SPLIT = re.compile(r"(?=<span class='spanTime'>[^<]*</span>,\s*(?:AfterEndCall )?Process node\.)")
NODE  = re.compile(r"Process node\.\s*'\((\d+)\)\s*([^']*)'")
TR    = re.compile(r'Transcription\s+\w+,\s*Response\s*(\[.*?\])\.', re.S)
QV    = re.compile(r'qtdVoice (\d+)')
PARAM = re.compile(r'TerminationMaxSeconds (\d+), TerminationBySilenceMilisec (\d+)')
TTS   = re.compile(r"TextToPlay '([^']{1,300})'")
CAMP  = re.compile(r'Audio\.(\d+)\.')
DATA  = re.compile(r"<span class='spanTime'>(\d\d)/(\d\d)/(\d{4})")
CPN   = {"1673": "OURO", "1737": "BRONZE", "1741": "PPAY"}

# siglas que devem sobreviver à canonização (senão viram {X} e o texto fica ilegível)
SIGLAS = {"CPF", "CNPJ", "RG", "SMS", "PIX", "TTS", "URA", "OK"}
VAZIO  = ("[silêncio]", "[silencio]", "[ruído]", "[ruido]", "[música]", "[musica]", "...")


def canonizar(t):
    """Colapsa a fala para uma forma sem PII: '{@nome}' e 'BRUNO' viram '{X}'.

    Serve a dois propósitos de uma vez — tira o dado pessoal do artefato
    versionado E faz a fala com variável resolvida cair no mesmo balde da
    fala-template, senão cada nome vira uma 'fala diferente' no diff.
    """
    t = re.sub(r'\{@?\w+\}', '{X}', t)
    t = re.sub(r'\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ]+\b',
               lambda m: m.group(0) if m.group(0) in SIGLAS else '{X}', t)
    t = re.sub(r'\d+(?:[.,]\d+)*', '{N}', t)
    return re.sub(r'\s+', ' ', t).strip().lower()


def so_script(textos):
    """Separa o SCRIPT do DADO renderizado nele.

    O log traz a fala nas duas formas: o template (`parceiro {@parceiro}.`) e a
    instância já resolvida (`parceiro alura.`). A instância é dado do mailing —
    ~2.400 faculdades viram ~2.400 'falas diferentes' e afogam o diff. Aqui cada
    template vira um regex e tudo que casa com ele é descartado, sobrando só o
    que um deploy de fato muda.
    """
    templates = [t for t in textos if '{@' in t]
    padroes = []
    for t in templates:
        p = '^' + ''.join(r'.+' if x.startswith('{@') else re.escape(x)
                          for x in re.split(r'(\{@\w+\})', t) if x) + '$'
        try:
            padroes.append(re.compile(p, re.I))
        except re.error:
            pass
    saida = []
    for t in textos:
        if '{@' in t or not any(p.match(t) for p in padroes):
            saida.append(t)
    return saida


def texto_vazio(arr, txt):
    return (not arr) or (not txt.strip()) or txt.strip().lower() in VAZIO


def ler(caminho):
    return open(caminho, encoding='utf-8', errors='replace').read()


def fingerprint(pasta, campanha=None, data=None, filtro=None):
    """Percorre os logs e monta o retrato do fluxo.

    `filtro` é uma função opcional (texto_do_log -> bool) para recortar o corpus
    — ex.: só as chamadas depois de um deploy.
    """
    nos = defaultdict(lambda: {"grav": 0, "voz": 0, "asr": 0, "vazio_voz": 0,
                               "voz_com_asr": 0, "sem_asr": 0, "captura": Counter()})
    falas, camps, datas, n = Counter(), Counter(), Counter(), 0

    for fn in sorted(os.listdir(pasta)):
        caminho = os.path.join(pasta, fn)
        if not os.path.isfile(caminho):
            continue
        s = ler(caminho)
        if filtro and not filtro(s):
            continue
        c = CAMP.search(s)
        nome_camp = CPN.get(c.group(1), "?") if c else "?"
        if campanha and nome_camp != campanha:
            continue
        camps[nome_camp] += 1
        d = DATA.search(s)
        if d:
            datas[f"{d.group(3)}-{d.group(2)}-{d.group(1)}"] += 1
        n += 1

        for t in so_script(TTS.findall(s)):
            falas[canonizar(t)] += 1

        for bloco in SPLIT.split(s):
            m = NODE.search(bloco)
            if not m or 'RecordTemp audio' not in bloco:
                continue
            chave = f"({m.group(1)}) {m.group(2).strip()}"
            r = nos[chave]
            r["grav"] += 1
            p = PARAM.search(bloco)
            if p:
                r["captura"][f"{p.group(2)}ms/{p.group(1)}s"] += 1
            qv = QV.findall(bloco)
            voz = max((int(x) for x in qv), default=0)
            if voz:
                r["voz"] += 1
            trs = TR.findall(bloco)
            if not trs:
                r["sem_asr"] += 1
                continue
            r["asr"] += 1
            try:
                arr = json.loads(trs[0])
                txt = (arr[0].get("text") or "") if arr else ""
            except Exception:
                continue
            if voz:
                r["voz_com_asr"] += 1
                if texto_vazio(arr, txt):
                    r["vazio_voz"] += 1

    saida = {
        "campanha": campanha or (camps.most_common(1)[0][0] if camps else "?"),
        "data": data or (datas.most_common(1)[0][0] if datas else "?"),
        "chamadas": n,
        "campanhas_vistas": dict(camps),
        "datas_vistas": dict(sorted(datas.items())),
        "falas": dict(falas.most_common()),
        "nos": {},
    }
    for chave, r in sorted(nos.items(), key=lambda x: -x[1]["grav"]):
        base = r["voz_com_asr"]
        saida["nos"][chave] = {
            "gravacoes": r["grav"],
            "com_voz": r["voz"],
            # nó que NUNCA transcreve é detector de VAD, não falha de ASR
            "chama_asr": r["asr"] > 0,
            "base_asr": base,
            "vazio": r["vazio_voz"],
            "falha_pct": round(100 * r["vazio_voz"] / base, 1) if base else None,
            "captura": r["captura"].most_common(1)[0][0] if r["captura"] else None,
        }
    return saida


def z_duas_proporcoes(k1, n1, k2, n2):
    """z e p bicaudal para duas proporções. None quando não há amostra."""
    if not n1 or not n2:
        return None, None
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (k1 / n1 - k2 / n2) / se
    return z, 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def diff(antes, agora, alfa=0.01, min_falas=5):
    """Compara dois fingerprints. Devolve (linhas_do_relatorio, houve_regressao)."""
    out, regressao = [], False
    cab = (f"{antes['campanha']} {antes['data']} ({antes['chamadas']} chamadas)"
           f"  ->  {agora['campanha']} {agora['data']} ({agora['chamadas']} chamadas)")
    out += [cab, "=" * len(cab), ""]

    # Ausência só é notícia quando havia AMOSTRA PARA VER. Com 22 chamadas novas
    # contra 3.621 antigas, quase tudo "some" por subamostragem — o corte é o
    # esperado sob a taxa antiga (>= 5 ocorrências, onde ver zero é surpresa).
    na_ch, ng_ch = max(1, antes["chamadas"]), max(1, agora["chamadas"])
    esperado = lambda c: c / na_ch * ng_ch

    # --- falas do bot (o sinal de deploy de script) --------------------------
    fa = {t: c for t, c in antes["falas"].items() if c >= min_falas}
    fg = {t: c for t, c in agora["falas"].items() if c >= min_falas}
    novas = sorted(set(fg) - set(fa))
    sumidas = sorted(t for t in set(fa) - set(fg) if esperado(fa[t]) >= 5)
    cegas = len(set(fa) - set(fg)) - len(sumidas)
    if novas or sumidas:
        regressao = True
        out.append("SCRIPT MUDOU")
        for t in novas:
            out.append(f"  + nova   ({fg[t]:>4}x)  {t[:150]}")
        for t in sumidas:
            out.append(f"  - sumiu  (esperava {esperado(fa[t]):.0f}x, veio 0)  {t[:130]}")
        out.append("")
    else:
        out += [f"script: sem mudança de fala (limiar >= {min_falas}x)", ""]
    if cegas:
        out += [f"  ({cegas} fala(s) ausentes sem amostra para concluir — "
                f"esperado < 5x em {ng_ch} chamadas)", ""]

    # --- estrutura de nós ----------------------------------------------------
    na, ng = antes["nos"], agora["nos"]
    # O mesmo ID com nome diferente é RENOMEAÇÃO, não nó novo + nó sumido. Deploy
    # renomeia nó com frequência e o par de falsos positivos esconde o resto.
    ida = {k.split(')')[0] + ')': k for k in na}
    idg = {k.split(')')[0] + ')': k for k in ng}
    renom = sorted(i for i in set(ida) & set(idg) if ida[i] != idg[i])
    if renom:
        regressao = True
        out.append("NÓ RENOMEADO")
        for i in renom:
            out.append(f"  ~ {i}  '{ida[i].split(') ',1)[-1]}' -> '{idg[i].split(') ',1)[-1]}'")
        out.append("")
    vistos = {ida[i] for i in renom} | {idg[i] for i in renom}
    add = sorted(set(ng) - set(na) - vistos)
    rem = sorted(k for k in set(na) - set(ng) - vistos if esperado(na[k]["gravacoes"]) >= 5)
    cegos = len(set(na) - set(ng) - vistos) - len(rem)
    if add or rem:
        regressao = True
        out.append("ESTRUTURA DE NÓS MUDOU")
        for k in add:
            out.append(f"  + nó novo      {k}  ({ng[k]['gravacoes']} gravações)")
        for k in rem:
            out.append(f"  - nó sumiu     {k}  (esperava {esperado(na[k]['gravacoes']):.0f} gravações, veio 0)")
        out.append("")
    if cegos:
        out += [f"  ({cegos} nó(s) ausentes sem amostra para concluir)", ""]

    # --- captura, papel do nó e falha ---------------------------------------
    linhas_par, linhas_falha = [], []
    for k in sorted(set(na) & set(ng)):
        a, g = na[k], ng[k]
        if a["captura"] != g["captura"]:
            regressao = True
            linhas_par.append(f"  janela de captura  {k}: {a['captura']} -> {g['captura']}")
        if a["chama_asr"] != g["chama_asr"]:
            regressao = True
            linhas_par.append(f"  papel do nó        {k}: chama_asr {a['chama_asr']} -> {g['chama_asr']}")
        if a["base_asr"] and g["base_asr"]:
            z, p = z_duas_proporcoes(g["vazio"], g["base_asr"], a["vazio"], a["base_asr"])
            if p is not None and p < alfa:
                seta = "PIOROU" if g["falha_pct"] > a["falha_pct"] else "melhorou"
                linhas_falha.append(
                    f"  {seta:<8} {k}: {a['falha_pct']}% (n={a['base_asr']}) -> "
                    f"{g['falha_pct']}% (n={g['base_asr']})  p={p:.4f}")
    if linhas_par:
        out += ["PARÂMETROS / PAPEL DO NÓ"] + linhas_par + [""]
    if linhas_falha:
        out += [f"FALHA DE ASR — variação significativa (p < {alfa})"] + linhas_falha + [""]
    else:
        out += [f"falha de ASR: nenhuma variação significativa (p < {alfa})", ""]

    # amostra pequena não conclui nada — dizer isso é parte do trabalho
    fracos = [k for k in set(na) & set(ng) if 0 < (ng[k]["base_asr"] or 0) < 250]
    if fracos:
        out.append(f"amostra insuficiente para concluir em {len(fracos)} nó(s) "
                   f"(base < 250): {', '.join(sorted(fracos)[:4])}"
                   + (" ..." if len(fracos) > 4 else ""))
    return out, regressao


def relatorio(fp):
    out = [f"{fp['campanha']} · {fp['data']} · {fp['chamadas']} chamadas", ""]
    out.append(f"  {'nó':<46}{'captura':>12}{'grav':>7}{'base':>7}{'falha':>8}")
    out.append("  " + "-" * 80)
    for k, v in fp["nos"].items():
        papel = "  [VAD, não transcreve]" if not v["chama_asr"] else ""
        falha = f"{v['falha_pct']}%" if v["falha_pct"] is not None else "-"
        out.append(f"  {k[:46]:<46}{str(v['captura'] or '-'):>12}{v['gravacoes']:>7}"
                   f"{v['base_asr']:>7}{falha:>8}{papel}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", help="pasta com os logs baixados")
    ap.add_argument("--saida", help="pasta onde gravar o fingerprint JSON")
    ap.add_argument("--campanha"); ap.add_argument("--data")
    ap.add_argument("--comparar", help="fingerprint anterior (JSON) para diff")
    ap.add_argument("--diff", nargs=2, metavar=("ANTES", "AGORA"))
    ap.add_argument("--contem", help="só logs que contenham este texto (recorte pós-deploy)")
    ap.add_argument("--nao-contem", help="só logs que NÃO contenham este texto")
    ap.add_argument("--alfa", type=float, default=0.01)
    a = ap.parse_args()

    if a.diff:
        linhas, reg = diff(json.load(open(a.diff[0], encoding="utf-8")),
                           json.load(open(a.diff[1], encoding="utf-8")), a.alfa)
        print("\n".join(linhas))
        sys.exit(2 if reg else 0)

    if not a.logs:
        sys.exit("informe --logs ou --diff")

    filtro = None
    if a.contem or a.nao_contem:
        def filtro(s):
            if a.contem and a.contem not in s:
                return False
            if a.nao_contem and a.nao_contem in s:
                return False
            return True

    fp = fingerprint(a.logs, a.campanha, a.data, filtro)
    if not fp["chamadas"]:
        sys.exit("nenhum log casou com o recorte pedido")
    print("\n".join(relatorio(fp)))

    if a.saida:
        os.makedirs(a.saida, exist_ok=True)
        destino = os.path.join(a.saida, f"{fp['campanha']}_{fp['data']}.json")
        json.dump(fp, open(destino, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nfingerprint: {destino}")

    if a.comparar:
        print()
        linhas, reg = diff(json.load(open(a.comparar, encoding="utf-8")), fp, a.alfa)
        print("\n".join(linhas))
        sys.exit(2 if reg else 0)


if __name__ == "__main__":
    main()
