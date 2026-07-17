#!/usr/bin/env python3
"""
ab_asr_bronze.py — A/B do fornecedor de ASR, campanha BRONZE (1737), dentro do dia.
Compara chamadas ANTES x DEPOIS do corte (default 10:00), normalizado pelo cohort da OFERTA.

PII-SAFE: NÃO imprime fala do cliente/telefone/nome. Só agregados + CASE_ID (chave técnica).
Rode NA MÁQUINA DO OPERADOR sobre os logs já coletados; cole a saída agregada no chat.

Uso:
  python3 ab_asr_bronze.py /caminho/coleta_<DDMM>/registros            # análise A/B
  python3 ab_asr_bronze.py /caminho/registros --cutoff 10:00 --buffer 10
  python3 ab_asr_bronze.py /caminho/registros --peek 3                 # calibrar parser (sem PII)

Entrada: pasta com .txt (um log por CASE_ID) OU arquivos .txt passados direto.
"""
import re, sys, os, glob, argparse
from datetime import datetime

CAMPAIGN_RE = re.compile(r"@CAMPAIGNID'=>'(\d+)'")
CASEID_RE   = re.compile(r'"CASE_ID","([0-9a-f-]{36})"', re.I)
NODE_RE     = re.compile(r"Process node\.\s*'\((\d+)\)\s*([^']+)'")
TRANSC_RE   = re.compile(r"Transcription Success, Response \[(.*?)\]", re.S)
TEXT_RE     = re.compile(r'"text"\s*:\s*"(.*?)"')
OFFER_RE    = re.compile(r"à vista ou parcel|voc[eê] prefere quitar", re.I)
DECISIVE_RE = re.compile(r"(parcelad?o?|parcelar|à\s*vista|a\s*vista|\bsim\b|quitar)", re.I)
# datas: tenta BR (dd/mm/yyyy HH:MM[:SS]) e ISO (yyyy-mm-dd HH:MM[:SS])
DT_BR  = re.compile(r"(\d{2})/(\d{2})/(\d{4})[ T](\d{2}):(\d{2})(?::(\d{2}))?")
DT_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?")

def call_dt(txt):
    m = DT_BR.search(txt)
    if m:
        d,mo,y,h,mi,s = m.groups(); return datetime(int(y),int(mo),int(d),int(h),int(mi),int(s or 0))
    m = DT_ISO.search(txt)
    if m:
        y,mo,d,h,mi,s = m.groups(); return datetime(int(y),int(mo),int(d),int(h),int(mi),int(s or 0))
    return None

def parse(txt):
    camp = CAMPAIGN_RE.search(txt); camp = camp.group(1) if camp else None
    cid  = CASEID_RE.search(txt);   cid  = cid.group(1) if cid else None
    dt   = call_dt(txt)
    reached_offer = bool(OFFER_RE.search(txt))
    no_match = 0; clean_decisive = False; nbest_recover = False
    for resp in TRANSC_RE.findall(txt):
        texts = [t.strip() for t in TEXT_RE.findall(resp)]
        primary = texts[0] if texts else ""
        if not primary:                       # transcrição vazia = NO_MATCH
            no_match += 1
            if any(DECISIVE_RE.search(t) for t in texts[1:]):  # termo já no n-best
                nbest_recover = True
        else:
            if DECISIVE_RE.search(primary):    # ASR devolveu o termo decisivo limpo
                clean_decisive = True
    n_transc = len(TRANSC_RE.findall(txt))
    return dict(cid=cid, camp=camp, dt=dt, reached_offer=reached_offer,
                no_match=no_match, n_transc=n_transc,
                clean_decisive=clean_decisive, nbest_recover=nbest_recover)

def load(paths):
    files=[]
    for p in paths:
        if os.path.isdir(p): files += glob.glob(os.path.join(p,"**","*.txt"), recursive=True)
        elif p.endswith(".txt"): files.append(p)
    return files

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--campaign", default="1737", help="ID da campanha (Bronze=1737)")
    ap.add_argument("--cutoff", default="10:00", help="hora do corte OLD/NEW (fornecedor)")
    ap.add_argument("--buffer", type=int, default=0, help="min de transição a excluir em torno do corte")
    ap.add_argument("--peek", type=int, default=0, help="calibração: imprime só tokens estruturais (sem PII)")
    a=ap.parse_args()
    ch,cm = map(int,a.cutoff.split(":")); cutoff_min = ch*60+cm

    files=load(a.paths)
    if not files: sys.exit("Nenhum .txt encontrado em: "+", ".join(a.paths))

    recs=[]
    skipped_camp=skipped_dt=0
    for f in files:
        try: txt=open(f, encoding="utf-8", errors="ignore").read()
        except Exception: continue
        r=parse(txt)
        if a.peek:
            if a.peek>0:
                print(f"[peek] cid={r['cid']} camp={r['camp']} dt={r['dt']} "
                      f"offer={r['reached_offer']} transc={r['n_transc']} nomatch={r['no_match']} "
                      f"clean={r['clean_decisive']} nbest={r['nbest_recover']}")
                a.peek-=1
            continue
        if r["camp"]!=a.campaign: skipped_camp+=1; continue      # campanha por ID (regra)
        if not r["dt"]: skipped_dt+=1; continue
        recs.append(r)
    if a.peek is not None and a.peek==0 and not recs and skipped_camp==0 and skipped_dt==0:
        return  # modo peek puro

    def bucket(r):
        m=r["dt"].hour*60+r["dt"].minute
        if a.buffer and abs(m-cutoff_min)<a.buffer: return None   # zona de transição
        return "NEW" if m>=cutoff_min else "OLD"

    groups={"OLD":[], "NEW":[]}; excl_transition=0
    for r in recs:
        b=bucket(r)
        if b is None: excl_transition+=1; continue
        groups[b].append(r)

    def agg(rs):
        n=len(rs); offer=[r for r in rs if r["reached_offer"]]; no=len(offer)
        nm=sum(r["no_match"] for r in offer)
        clean=sum(1 for r in offer if r["clean_decisive"])
        nomatch_calls=[r for r in offer if r["no_match"]>0]
        nbest=sum(1 for r in nomatch_calls if r["nbest_recover"])
        return dict(n=n, offer=no,
                    nm_per_offer=(nm/no if no else None),
                    clean_pct=(100*clean/no if no else None),
                    nbest_pct=(100*nbest/len(nomatch_calls) if nomatch_calls else None),
                    ex_cids=[r["cid"] for r in offer[:3]])

    O,N=agg(groups["OLD"]),agg(groups["NEW"])
    print("="*66)
    print(f"A/B ASR — BRONZE ({a.campaign}) · corte {a.cutoff} (OLD<corte · NEW>=corte)")
    print(f"arquivos={len(files)} | válidos={len(recs)} | fora-campanha={skipped_camp} | sem-data={skipped_dt} | transição-excl={excl_transition}")
    print("-"*66)
    hdr=f"{'métrica':32s} {'OLD (antigo)':>14s} {'NEW (novo)':>14s}"
    print(hdr)
    def fmt(v,pct=False): return "n/d" if v is None else (f"{v:.1f}%" if pct else f"{v:.2f}")
    print(f"{'chamadas Bronze':32s} {O['n']:>14d} {N['n']:>14d}")
    print(f"{'cohort: chegou à oferta':32s} {O['offer']:>14d} {N['offer']:>14d}")
    print(f"{'NO_MATCH / chamada (cohort)':32s} {fmt(O['nm_per_offer']):>14s} {fmt(N['nm_per_offer']):>14s}")
    print(f"{'captura limpa termo decisivo':32s} {fmt(O['clean_pct'],1):>14s} {fmt(N['clean_pct'],1):>14s}")
    print(f"{'termo no n-best do NO_MATCH':32s} {fmt(O['nbest_pct'],1):>14s} {fmt(N['nbest_pct'],1):>14s}")
    print("-"*66)
    print(f"CASE_IDs prova OLD: {', '.join(c for c in O['ex_cids'] if c)}")
    print(f"CASE_IDs prova NEW: {', '.join(c for c in N['ex_cids'] if c)}")
    if min(O['offer'],N['offer'])<20:
        print("\n⚠ AMOSTRA PEQUENA no cohort da oferta (<20 em algum grupo). A janela pré-10h")
        print("  tem só ~2h de Bronze — trate como indicativo. Para robustez, rode também um")
        print("  dia anterior de Bronze como baseline do fornecedor ANTIGO (mesmo cohort).")
    print("\nNota: 'acordo fechado' NÃO entra — é 0 por construção (fluxo sem nó de fechamento).")
    print("Acurácia real ('o bot entendeu?') exige Camada B (áudio, on-prem) — não sai do log.")
    print("="*66)

if __name__=="__main__":
    main()
