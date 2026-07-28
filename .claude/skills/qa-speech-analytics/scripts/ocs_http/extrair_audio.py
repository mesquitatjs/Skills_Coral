"""Extrai as gravações das ligações do OCS (WAV 8kHz mono) para montar corpus de QA.

RODE ISTO ON-PREM. O áudio é a voz do devedor e o retorno do OCS traz nome,
telefone e CPF — PII que não deve sair do ambiente controlado de vocês. Este
script já descarta esses campos: grava só um índice analítico (case_id, campanha,
duração). Use --indice-completo apenas se houver necessidade real e o destino for
adequado ao dado.

Uso:
  python extrair_audio.py --lista lista_OURO_2026-07-23.json --saida corpus/
  python extrair_audio.py --lista-dir ./listas --saida corpus/ --limite 200
  python extrair_audio.py --cids cids.txt --saida corpus/ --dry-run

  --lista/--lista-dir  JSON(s) de coleta do collect_day.py (usa o campo `cid`)
  --cids               alternativa: arquivo texto com um callResultId por linha
  --saida              pasta destino (cria audio/ e indice.csv)
  --limite N           extrai no máximo N chamadas (teste)
  --dry-run            só consulta a disponibilidade, não baixa
  --indice-completo    inclui produto/parceiro/aging/valor no índice

Requer ~/.ocs.env com OCS_USER / OCS_PASS. Nunca imprime credenciais nem PII.

SEQUENCIAL DE PROPÓSITO: o OCS derruba a sessão quando há acessos concorrentes
(dois processos = ConnectionReset). Não paralelize; para ir mais rápido, rode em
janelas diferentes de tempo, não em paralelo.

A gravação vive em TempFiles/ no servidor — há expurgo. Extraia o quanto antes
os dias que interessam; ligações antigas podem já não existir (contabilizadas
como `sem_audio`).
"""
import argparse, csv, glob, json, os, re, sys, time
import requests

BASE  = "https://ocs.sinergytech.com.br/"
URL   = BASE + "callResultInteractions.aspx"
LOGIN = BASE + "Login.aspx?o=%2fcallResultInteractions.aspx"
ENV   = os.path.expanduser("~/.ocs.env")
PAUSA = 0.4          # respiro entre chamadas — não martelar o fornecedor
TENTATIVAS = 4

log = lambda m: print(m, flush=True)


def _env():
    env = {}
    for line in open(ENV):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1); env[k] = v
    if not env.get("OCS_USER") or not env.get("OCS_PASS"):
        sys.exit(f"{ENV} sem OCS_USER/OCS_PASS.")
    return env


def entrar(s, env):
    """Autentica. Os campos são planos (txtUsuario/txtSenha), sem prefixo ctl00$."""
    r = s.get(LOGIN, timeout=40)
    hid = lambda n: (re.search(rf'id="{n}"[^>]*value="([^"]*)"', r.text) or [None, ""])[1]
    s.post(LOGIN, timeout=40, data={
        "__VIEWSTATE": hid("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": hid("__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION": hid("__EVENTVALIDATION"),
        "txtUsuario": env["OCS_USER"], "txtSenha": env["OCS_PASS"], "btnLogar": "Entrar"})
    return "ddlCampaigns" in s.get(URL, timeout=40).text


def _com_retry(fn, desc, s, env):
    """Repete em queda de conexão e reautentica se a sessão expirou."""
    for i in range(TENTATIVAS):
        try:
            return fn()
        except (requests.ConnectionError, requests.Timeout) as ex:
            espera = 2 ** i
            log(f"   [{desc}] {type(ex).__name__} — nova tentativa em {espera}s")
            time.sleep(espera)
            try:
                entrar(s, env)
            except Exception:
                pass
    return None


def info_audio(s, env, cid):
    """Consulta o OCS. Devolve (caminho_wav, meta) — meta já SEM nome/telefone/CPF."""
    def _post():
        r = s.post(URL + "/GetAudioUrl", timeout=60,
                   data=json.dumps({"callResultId": str(cid)}),
                   headers={"Content-Type": "application/json; charset=utf-8",
                            "X-Requested-With": "XMLHttpRequest"})
        r.raise_for_status()
        return r.json()["d"]
    d = _com_retry(_post, f"info {cid}", s, env)
    if not d:
        return None, {}
    val = d.get("Value") or {}
    caminho = val.get("Item1") or ""
    disponivel = bool(val.get("Item2"))
    k = d.get("Key") or {}
    extra = {c[0]: c[1] for c in (k.get("contactExtraFieldValues") or []) if len(c) == 2}
    meta = {
        "cid": cid,
        "case_id": extra.get("CASE_ID", ""),
        "campanha": k.get("campaignName", "") or extra.get("CREDOR", ""),
        "data_hora": k.get("callTimeString", ""),
        "duracao_s": k.get("callDuration", ""),
        "produto": extra.get("PRODUTO", ""),
        "parceiro": extra.get("PARCEIRO", ""),
        "aging": extra.get("AGING", ""),
        "valor_divida": extra.get("VALOR_DIVIDA", ""),
    }
    return (caminho if disponivel and caminho else None), meta


def baixar(s, env, caminho, destino):
    """Baixa o WAV. Valida o cabeçalho RIFF — meio-arquivo é pior que arquivo nenhum."""
    def _get():
        r = s.get(BASE + caminho.lstrip("/"), timeout=180, stream=True)
        r.raise_for_status()
        tmp = destino + ".parcial"
        with open(tmp, "wb") as fh:
            for pedaco in r.iter_content(65536):
                fh.write(pedaco)
        with open(tmp, "rb") as fh:
            if fh.read(4) != b"RIFF":
                os.remove(tmp); raise ValueError("resposta não é WAV")
        os.replace(tmp, destino)     # só vira definitivo quando está íntegro
        return os.path.getsize(destino)
    return _com_retry(_get, os.path.basename(destino), s, env)


def carregar_cids(args):
    cids = []
    if args.cids:
        cids = [l.strip() for l in open(args.cids) if l.strip()]
    arquivos = ([args.lista] if args.lista else []) + \
               (sorted(glob.glob(os.path.join(args.lista_dir, "lista_*.json"))) if args.lista_dir else [])
    for f in arquivos:
        for x in json.load(open(f, encoding="utf-8")):
            if x.get("cid"):
                cids.append(str(x["cid"]))
    vistos, saida = set(), []
    for c in cids:                                   # preserva a ordem, remove repetido
        if c not in vistos:
            vistos.add(c); saida.append(c)
    return saida


COLUNAS_MIN = ["cid", "case_id", "campanha", "data_hora", "duracao_s", "arquivo", "bytes"]
COLUNAS_MAX = COLUNAS_MIN + ["produto", "parceiro", "aging", "valor_divida"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lista"); ap.add_argument("--lista-dir"); ap.add_argument("--cids")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--limite", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--indice-completo", action="store_true")
    args = ap.parse_args()

    cids = carregar_cids(args)
    if not cids:
        sys.exit("Nenhum cid. Informe --lista, --lista-dir ou --cids.")
    if args.limite:
        cids = cids[:args.limite]

    pasta_audio = os.path.join(args.saida, "audio")
    os.makedirs(pasta_audio, exist_ok=True)
    indice = os.path.join(args.saida, "indice.csv")
    colunas = COLUNAS_MAX if args.indice_completo else COLUNAS_MIN

    ja = set()
    if os.path.exists(indice):
        # Retomável pelo ARQUIVO em disco, não pela linha do índice: linha sem WAV
        # correspondente não é trabalho feito (ex.: índice de um --dry-run anterior).
        with open(indice, encoding="utf-8") as fh:
            ja = {r["cid"] for r in csv.DictReader(fh)
                  if r.get("arquivo") and os.path.exists(r["arquivo"])}
        log(f"[retomada] {len(ja)} chamadas com áudio já em disco")

    env = _env()
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Connection": "close"})
    if not entrar(s, env):
        sys.exit("login falhou")
    log(f"[ok] autenticado | {len(cids)} chamadas na fila"
        + (" | DRY-RUN (não baixa)" if args.dry_run else ""))

    novo = not os.path.exists(indice)
    fh = open(indice, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=colunas, extrasaction="ignore")
    if novo:
        w.writeheader()

    n_ok = n_sem = n_erro = bytes_tot = 0
    for i, cid in enumerate(cids, 1):
        if cid in ja:
            continue
        caminho, meta = info_audio(s, env, cid)
        if caminho is None:
            n_sem += 1
            if not meta:
                n_erro += 1
        else:
            destino = os.path.join(pasta_audio, f"{cid}.wav")
            if args.dry_run:
                n_ok += 1
            elif os.path.exists(destino) and os.path.getsize(destino) > 44:
                n_ok += 1; meta["arquivo"] = destino; meta["bytes"] = os.path.getsize(destino)
            else:
                tam = baixar(s, env, caminho, destino)
                if tam:
                    n_ok += 1; bytes_tot += tam
                    meta["arquivo"] = destino; meta["bytes"] = tam
                else:
                    n_erro += 1
        # dry-run NÃO escreve o índice: senão a execução real seguinte enxerga
        # essas linhas como já processadas e não baixa nada.
        if meta and not args.dry_run:
            w.writerow(meta); fh.flush()             # grava a cada item: queda não perde nada
        if i % 25 == 0 or i == len(cids):
            log(f"  {i}/{len(cids)} — ok={n_ok} sem_audio={n_sem} erro={n_erro} "
                f"({bytes_tot/1e6:.0f} MB)")
        time.sleep(PAUSA)

    fh.close()
    log(f"\n[fim] ok={n_ok} sem_audio={n_sem} erro={n_erro} | {bytes_tot/1e6:.1f} MB")
    log(f"      áudio: {pasta_audio}")
    log(f"      índice: {indice}")
    if n_sem:
        log(f"      {n_sem} sem gravação — provável expurgo do TempFiles no servidor.")


if __name__ == "__main__":
    main()
