import re,os,sys,time,json,pickle,requests,datetime
BASE="https://ocs.sinergytech.com.br/";URL=BASE+"callResultInteractions.aspx"
LOGIN=BASE+"Login.aspx?o=%2fcallResultInteractions.aspx"
import sys; day=sys.argv[1];P="ctl00$ContentPlaceHolder1$"
AH={"X-MicrosoftAjax":"Delta=true","X-Requested-With":"XMLHttpRequest",
    "Content-Type":"application/x-www-form-urlencoded; charset=utf-8"}
log=lambda m:print(m,flush=True)
env={}
for line in open(os.path.expanduser("~/.ocs.env")):
    if "=" in line: k,v=line.strip().split("=",1); env[k]=v
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0","Connection":"close"})

def hid(h):
    d={}
    for t in re.findall(r'<input[^>]*type="hidden"[^>]*>',h,re.I):
        n=re.search(r'name="([^"]+)"',t);v=re.search(r'value="([^"]*)"',t)
        if n:d[n.group(1)]=v.group(1) if v else ""
    return d
def login():
    r=S.get(LOGIN,timeout=40)
    d=hid(r.text)
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
            r=S.post(URL,data=data,headers=AH,timeout=60)
            if "txtSenha" in r.text:   # caiu no meio
                log("  postback deslogado -> relogin"); login(); continue
            return r
        except Exception:
            if i==tries-1: raise
            time.sleep(1.5*(i+1))
def rows(h):
    out=[]
    for tr in re.findall(r'<tr[^>]*>.*?</tr>',h,re.S|re.I):
        if 'callResultId="' not in tr:continue
        cid=re.search(r'callResultId="(\d+)"',tr).group(1)
        camp=re.search(r'BRONZE|OURO|PRINCIPIAPAY|NEGOCIADOR|EXEMPLO',tr,re.I)
        dt=re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})',tr)
        tds=[re.sub(r'<[^>]+>','',t).strip() for t in re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)]
        out.append({"cid":cid,"camp":camp.group(0).upper() if camp else "?",
                    "hora":dt.group(1) if dt else None,"cat":tds[-1] if tds else ""})
    return out
def slice_rows(ini,fim):
    h=get_page(); d=hid(h)
    d.update({"ctl00$SM":P+"updpn|"+P+"btnBuscar","__ASYNCPOST":"true",P+"ddlCampaigns":"1737",
              P+"txtDtIni":f"{day}T{ini}",P+"txtDtFim":f"{day}T{fim}",P+"txtPhone":"",
              P+"btnBuscar":"Buscar","__EVENTTARGET":"","__EVENTARGUMENT":""})
    r=post(d);h=r.text
    tg=re.search(r"__doPostBack\('([^']*gvCallResults[^']*)','Page\$\d+'\)",h)
    target=tg.group(1) if tg else P+"gvCallResultsInteractions"
    seen={};cur=1;pg=0
    while True:
        for x in rows(h): seen[x["cid"]]=x
        pg+=1
        avail=sorted({int(x) for x in re.findall(r'Page\$(\d+)',h)})
        nxt=next((n for n in avail if n>cur),None)
        if nxt is None or pg>=40: break
        d=hid(h);d.update({"ctl00$SM":P+"updpn|"+target,"__ASYNCPOST":"true",P+"ddlCampaigns":"1737",
                           P+"txtDtIni":f"{day}T{ini}",P+"txtDtFim":f"{day}T{fim}",P+"txtPhone":"",
                           "__EVENTTARGET":target,"__EVENTARGUMENT":f"Page${nxt}"})
        r=post(d);h=r.text;cur=nxt; time.sleep(0.2)
    return list(seen.values())

login()
slices=[(f"{h:02d}:{m:02d}",f"{h:02d}:{m+29:02d}") for h in range(10,12) for m in (0,30)]
allb={}
for ini,fim in slices:
    rs=slice_rows(ini,fim)
    br=[x for x in rs if x["camp"]=="BRONZE"]
    for x in br: allb[x["cid"]]=x
    json.dump(list(allb.values()),open(sys.argv[2],"w"))
    log(f"fatia {ini}-{fim}: {len(rs)} linhas, {len(br)} bronze | total={len(allb)}")
pickle.dump(S.cookies,open("ocs_session.pkl","wb"))
log(f"DONE bronze 10-12h: {len(allb)}")

