"""
Coleta de interações do OCS Sinergytech via HTTP (sem browser).

CORREÇÃO (20/07/2026): o filtro de CAMPANHA e o de ÚLTIMA INTERAÇÃO funcionam
server-side — mas só se postados nos HIDDEN que o botão Buscar sincroniza por JS
(o servidor IGNORA os controles `ddlCampaigns`/`ddlInteractionsFinal` diretos):
  • Campanha       → hidden `hdListCpnId`      (ex.: Bronze = 1737)
  • Última Interação → hidden `hdInteracaoFinal` (interactionID do getInteraction)
  • Interações (multi) → `hdInteractions` · Lote → `hdListIdLot`
As opções de Última Interação vêm do PageMethod `callResultInteractions.aspx/getInteraction`
com body `{campaigns: <id>}` (retorna [{interactionID, interactionName}]).

Antes disso a coleta baixava TODAS as campanhas e filtrava no cliente (frágil: paginava
por todas as campanhas e o casamento por regex escapava linhas). Agora a campanha é
server-side → menos volume, sem vazamento de outras campanhas.

Uso:
  python collect_day.py <YYYY-MM-DD> <saida.json> [cpnId=1737] [interacaoFinalId] [hIni=10] [hFim=12]
    cpnId            — id da campanha (1737 Bronze · 1673 Ouro · 1741 PrincipiaPay)
    interacaoFinalId — (opcional) filtra por uma última interação específica
Requer ~/.ocs.env com OCS_USER/OCS_PASS. Nunca imprime a senha.
"""
import re, os, sys, time, json, requests
from collections import Counter

BASE="https://ocs.sinergytech.com.br/"; URL=BASE+"callResultInteractions.aspx"
LOGIN=BASE+"Login.aspx?o=%2fcallResultInteractions.aspx"; P="ctl00$ContentPlaceHolder1$"
AH={"X-MicrosoftAjax":"Delta=true","X-Requested-With":"XMLHttpRequest",
    "Content-Type":"application/x-www-form-urlencoded; charset=utf-8"}
JH={"Content-Type":"application/json; charset=utf-8","X-Requested-With":"XMLHttpRequest"}
log=lambda m: print(m, flush=True)
env={}
for line in open(os.path.expanduser("~/.ocs.env")):
    if "=" in line: k,v=line.strip().split("=",1); env[k]=v
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0","Connection":"close"})

day=sys.argv[1]; OUT=sys.argv[2]
CPN=sys.argv[3] if len(sys.argv)>3 else "1737"
IFINAL=sys.argv[4] if len(sys.argv)>4 else ""     # última interação (opcional)
HINI=int(sys.argv[5]) if len(sys.argv)>5 else 10
HFIM=int(sys.argv[6]) if len(sys.argv)>6 else 12

def hid(h):
    d={}
    for t in re.findall(r'<input[^>]*type="hidden"[^>]*>',h,re.I):
        n=re.search(r'name="([^"]+)"',t); v=re.search(r'value="([^"]*)"',t)
        if n: d[n.group(1)]=v.group(1) if v else ""
    return d
def login():
    r=S.get(LOGIN,timeout=40); d=hid(r.text)
    d.update({"txtUsuario":env["OCS_USER"],"txtSenha":env["OCS_PASS"],
              "btnLogar":(re.search(r'name="btnLogar"[^>]*value="([^"]*)"',r.text) or [None,"Entrar"])[1]})
    S.post(LOGIN,data=d,timeout=40,allow_redirects=True)
    ok="ddlCampaigns" in S.get(URL,timeout=40).text
    log("  login "+("OK" if ok else "FALHOU")); return ok
def get_page():
    r=S.get(URL,timeout=40)
    if "txtSenha" in r.text or "ddlCampaigns" not in r.text:
        log("  sessao caiu -> relogin"); login(); r=S.get(URL,timeout=40)
    return r.text
def post(data,tries=4):
    for i in range(tries):
        try:
            r=S.post(URL,data=data,headers=AH,timeout=90)
            if "txtSenha" in r.text: log("  postback deslogado -> relogin"); login(); continue
            return r
        except Exception:
            if i==tries-1: raise
            time.sleep(1.5*(i+1))
def interacoes(cpn):
    """{interactionID(str): nome} da campanha (getInteraction)."""
    try:
        d=S.post(URL+"/getInteraction",data="{campaigns: %s}"%cpn,headers=JH,timeout=40).json().get("d",[])
        return {str(it.get("interactionID")):(it.get("interactionName") or it.get("interaction") or "") for it in d}
    except Exception as e:
        log("  getInteraction falhou: %r"%e); return {}
def rows(h):
    out=[]
    for tr in re.findall(r'<tr[^>]*>.*?</tr>',h,re.S|re.I):
        if 'callResultId="' not in tr: continue
        cid=re.search(r'callResultId="(\d+)"',tr).group(1)
        tds=[re.sub(r'<[^>]+>','',t).strip() for t in re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)]
        cn=re.search(r'BRONZE|OURO|PRINCIPIAPAY|NEGOCIADOR|EXEMPLO',tr,re.I)
        out.append({"cid":cid,"camp":cn.group(0).upper() if cn else "?",
                    "hora":(re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})',tr) or [None,None])[0]
                            if re.search(r'\d{2}/\d{2}/\d{4}',tr) else None,
                    "ult_interacao": tds[-1] if tds else "", "tds": tds})
    return out
# A paginação async do GridView do OCS NÃO avança de forma confiável (a "página 2"
# volta um subconjunto da página 1). Em vez de paginar, usamos SUBDIVISÃO ADAPTATIVA
# do tempo: qualquer janela que encoste no teto de página (20) ou exiba pager é
# dividida ao meio recursivamente até caber numa página. Assim cada busca é 1 página
# e nada é truncado — independente da volumetria.
PAGE=20
def fmt(mins): return f"{mins//60:02d}:{mins%60:02d}"
def busca(a,b):
    """Uma busca [a,b) (minutos). Retorna (linhas_pág1, truncou?)."""
    h=get_page()
    d=hid(h)
    d.update({"ctl00$SM":P+"updpn|"+P+"btnBuscar","__ASYNCPOST":"true",
              P+"txtDtIni":f"{day}T{fmt(a)}",P+"txtDtFim":f"{day}T{fmt(b)}",P+"txtPhone":"",
              P+"hdListCpnId":CPN,P+"hdInteractions":"",P+"hdListIdLot":"",
              P+"hdInteracaoFinal":IFINAL,P+"hdExtraFields":"",
              P+"btnBuscar":"Buscar","__EVENTTARGET":"","__EVENTARGUMENT":""})
    h=post(d).text; rs=rows(h)
    trunc = bool(re.search(r'Page\$\d+',h)) or len(rs)>=PAGE
    return rs, trunc
def collect(a,b,depth=0,acc=None):
    acc=acc if acc is not None else {}
    rs,trunc=busca(a,b)
    if trunc and (b-a)>1 and depth<12:
        m=(a+b)//2
        collect(a,m,depth+1,acc); collect(m,b,depth+1,acc)
    else:
        if trunc: log(f"  ⚠ janela {fmt(a)}-{fmt(b)} truncada e não subdividível ({len(rs)} linhas)")
        for x in rs: acc[x["cid"]]=x
    return acc

if not login(): sys.exit("login falhou")
INT=interacoes(CPN)
if IFINAL:
    log(f"  filtro última interação: {IFINAL} = {INT.get(IFINAL,'?')}")
allr={}
for h0 in range(HINI,HFIM):                       # 1 hora por vez, com salvamento incremental
    collect(h0*60,(h0+1)*60,acc=allr)
    json.dump(list(allr.values()),open(OUT,"w"),ensure_ascii=False)
    log(f"até {h0+1:02d}:00 — total acumulado={len(allr)}")
# sanidade: com hdListCpnId a campanha é server-side → deve ser 100% a campanha pedida
alvo={"1737":"BRONZE","1673":"OURO","1741":"PRINCIPIAPAY"}.get(CPN)
leak=[x for x in allr.values() if alvo and x["camp"] not in (alvo,"?")]
log(f"DONE {len(allr)} linhas | vazamento de outra campanha: {len(leak)} (esperado 0)")
if IFINAL:
    alvo_txt=INT.get(IFINAL,"")
    ok=all(x["ult_interacao"]==alvo_txt for x in allr.values())
    log(f"  última interação homogênea ('{alvo_txt}'): {ok}")
