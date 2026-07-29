import os,re,sys,json,time,requests
BASE="https://ocs.sinergytech.com.br/";URL=BASE+"callResultInteractions.aspx"
LOGIN=BASE+"Login.aspx?o=%2fcallResultInteractions.aspx"
ROWS, LABEL, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
env=dict(l.strip().split("=",1) for l in open(os.path.expanduser("~/.ocs.env")) if "=" in l)
S=requests.Session();S.headers.update({"User-Agent":"Mozilla/5.0","Connection":"close"})
JH={"Content-Type":"application/json; charset=utf-8","X-Requested-With":"XMLHttpRequest"}
# Marcador de sessão ativa na monitoração. O portal renomeou o seletor de campanha
# `ddlCampaigns` → `ddlCampanha` (visto em 29/07/2026). Como ele era usado como PROVA de
# login, a renomeação fez o script autenticar com sucesso e mesmo assim reportar
# "login FALHOU" — derrubando 5 campanha-dias de coleta por diagnóstico errado.
# Aceita os dois nomes: se o portal reverter, ou se coexistirem, continua funcionando.
def _logado(html: str) -> bool:
    return ("ddlCampanha" in html) or ("ddlCampaigns" in html)


def hid(h):
    d={}
    for t in re.findall(r'<input[^>]*type="hidden"[^>]*>',h,re.I):
        n=re.search(r'name="([^"]+)"',t);v=re.search(r'value="([^"]*)"',t)
        if n:d[n.group(1)]=v.group(1) if v else ""
    return d
def login():
    r=S.get(LOGIN,timeout=40);d=hid(r.text)
    d.update({"txtUsuario":env["OCS_USER"],"txtSenha":env["OCS_PASS"],"btnLogar":"Entrar"})
    S.post(LOGIN,data=d,timeout=40); return _logado(S.get(URL,timeout=40).text)
def getlog(cid):
    full="";b=0
    for _ in range(50):
        try: r=S.post(URL+"/GetLogComplete",json={"callResultId":cid,"bytesIni":b},headers=JH,timeout=30)
        except Exception: time.sleep(1.2); continue
        if r.status_code!=200:
            login(); continue
        d=r.json().get("d",{}); full+=d.get("log","") or ""
        nb=d.get("nextBytes",0)
        if d.get("ended") or not nb or nb<=b: break
        b=nb
    return full
OFFER=re.compile(r"à vista ou parcel|voc[eê] prefere quitar|CONSULTA DISPONIBILIDADE PARCELAMENTO",re.I)
DECIS=re.compile(r"(parcelad?o?|parcelar|à\s*vista|a\s*vista|\bsim\b|quitar)",re.I)
TRANSC=re.compile(r"Transcription Success, Response \[(.*?)\]",re.S)
TEXT=re.compile(r'"text"\s*:\s*"(.*?)"')
CASEID=re.compile(r'"CASE_ID","([0-9a-f-]{36})"',re.I)
DEAD=re.compile(r'abandonad|sem resposta|caixa postal|nao atende|não atende|ocupad|mudo|inexistente|indispon',re.I)

rows=json.load(open(ROWS))
conn=[r for r in rows if not DEAD.search(r["cat"])]
if not login(): sys.exit("login falhou")
res=[]
for i,row in enumerate(conn):
    txt=getlog(row["cid"])
    turns=0;nm=0;clean=False;nbest=False
    for resp in TRANSC.findall(txt):
        ts=[t.strip() for t in TEXT.findall(resp)]; turns+=1
        prim=ts[0] if ts else ""
        if not prim:
            nm+=1
            if any(DECIS.search(t) for t in ts[1:]): nbest=True
        elif DECIS.search(prim): clean=True
    reached=bool(OFFER.search(txt)); cid_=CASEID.search(txt)
    res.append(dict(cid=row["cid"],case=cid_.group(1) if cid_ else None,cat=row["cat"],
                    turns=turns,nm=nm,reached=reached,clean=clean,nbest=nbest))
    if (i+1)%10==0: print(f"...{i+1}/{len(conn)}",flush=True)
json.dump(res,open(OUT,"w"))

tt=sum(r["turns"] for r in res); tnm=sum(r["nm"] for r in res)
offer=[r for r in res if r["reached"]]
clean=sum(1 for r in offer if r["clean"]); nomc=[r for r in offer if r["nm"]>0]; nbest=sum(1 for r in nomc if r["nbest"])
print(f"@@@ {LABEL} | conectadas={len(res)} turnos={tt} NO_MATCH={tnm} "
      f"nm_rate={100*tnm/tt if tt else 0:.1f}% nm_por_chamada={tnm/len(res) if res else 0:.2f} "
      f"chegou_oferta={len(offer)} clean={clean}/{len(offer)} nbest={nbest}/{len(nomc)}")
