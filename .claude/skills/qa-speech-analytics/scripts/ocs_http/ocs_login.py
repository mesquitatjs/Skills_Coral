"""Login único no OCS via HTTP (sem browser). Imprime só status — nunca credenciais/PII."""
import os, re, sys, requests

BASE  = "https://ocs.sinergytech.com.br/"
LOGIN = BASE + "Login.aspx?o=%2fcallResultInteractions.aspx"
ENV   = os.path.expanduser("~/.ocs.env")

env = {}
for line in open(ENV):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.strip().split("=", 1); env[k] = v
u, p = env.get("OCS_USER"), env.get("OCS_PASS")
if not u or not p:
    sys.exit("faltam OCS_USER/OCS_PASS no ~/.ocs.env")

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (QA collector)"} )

# Marcador de sessão ativa na monitoração. O portal renomeou o seletor de campanha
# `ddlCampaigns` → `ddlCampanha` (visto em 29/07/2026). Como ele era usado como PROVA de
# login, a renomeação fez o script autenticar com sucesso e mesmo assim reportar
# "login FALHOU" — derrubando 5 campanha-dias de coleta por diagnóstico errado.
# Aceita os dois nomes: se o portal reverter, ou se coexistirem, continua funcionando.
def _logado(html: str) -> bool:
    return ("ddlCampanha" in html) or ("ddlCampaigns" in html)


def hid(name, html):
    m = (re.search(r'id="' + name + r'"[^>]*value="([^"]*)"', html) or
         re.search(r'name="' + name + r'"[^>]*value="([^"]*)"', html))
    return m.group(1) if m else ""

# GET login page (viewstate fresco) — não é tentativa de login
r = S.get(LOGIN, timeout=40)
data = {
    "__VIEWSTATE":          hid("__VIEWSTATE", r.text),
    "__VIEWSTATEGENERATOR": hid("__VIEWSTATEGENERATOR", r.text),
    "__EVENTVALIDATION":    hid("__EVENTVALIDATION", r.text),
    "txtUsuario": u,
    "txtSenha":   p,
    "btnLogar":   (re.search(r'name="btnLogar"[^>]*value="([^"]*)"', r.text) or [None, "Entrar"])[1],
}
# >>> ÚNICA tentativa de login (sem retry) <<<
r2 = S.post(LOGIN, data=data, timeout=40, allow_redirects=True)

tgt = S.get(BASE + "callResultInteractions.aspx", timeout=40)
has_campaigns = _logado(tgt.text)
still_login   = ("txtSenha" in tgt.text) or ("txtUsuario" in tgt.text)
ok = has_campaigns and not still_login

print("login_post_status:", r2.status_code, "| final_url:", r2.url.split("//")[-1][:55])
print("auth_ok:", ok, "| ddlCampaigns:", has_campaigns, "| still_login:", still_login)

# persiste cookies da sessão p/ os próximos passos (sem PII)
import pickle
pickle.dump(S.cookies, open("ocs_session.pkl", "wb"))

if ok:
    open("search_page.html", "w", encoding="utf-8").write(tgt.text)
    print("OK — search_page.html salvo (", len(tgt.text), "bytes ). Sessão em ocs_session.pkl")
else:
    print("LOGIN FALHOU — parando sem retry (não vou insistir, p/ não travar a conta).")
    sys.exit(2)
