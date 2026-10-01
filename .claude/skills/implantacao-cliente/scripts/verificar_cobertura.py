#!/usr/bin/env python3
"""Verificador de cobertura da implantação de um cliente — skill `implantacao-cliente`.

Lê a FICHA do cliente (templates/ficha_cliente.yaml preenchida) e confere, nos repositórios
locais, se cada PONTO DE CADASTRO tem a entrada do cliente. Só lê arquivos — não altera nada.

    python3 verificar_cobertura.py --ficha projetos_coral/bull/FICHA_IMPLANTACAO.yaml \
            --raiz /home/user            # pasta com os clones (principia-acionamento, coral-bot, …)

Saída: uma linha por ponto (✅ tem · ❌ falta · ⏭️ não se aplica pela ficha · ❔ arquivo não
encontrado) + checagem de CONSISTÊNCIA do orçamento nas três cópias. Sai 1 se faltar ponto
obrigatório ou se as cópias divergirem — dá para usar como gate antes de publicar.

Os padrões procuram o NOME DA CONSTANTE + o valor do cliente, não número de linha (linha muda).
Ponto novo descoberto numa implantação = uma entrada em PONTOS (e em references/pontos-de-cadastro.md).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

PA, CB, CM = "principia-acionamento", "coral-bot", "coralai-mailing"

# (repo, arquivo, descrição, regex com {placeholders}, condição de aplicabilidade)
# placeholders: chave, CHAVE, nome, cpn, rotulo, techprefix, sufixo, nome_lote
PONTOS = [
    # ── principia-acionamento: telecom, painéis, tema ──────────────────────────────────────
    (PA, "scripts/clientes_telecom.py", "CLIENTE_POR_CPN (cpnId → cliente; custo do CDR)", r'"{cpn}"\s*:\s*"{chave}"', None),
    (PA, "scripts/clientes_telecom.py", "NOME_CLIENTE (seletor do Telecom)", r'"{chave}"\s*:\s*"{nome}"', None),
    (PA, "scripts/clientes_telecom.py", "sql_cliente_campanha (LIKE no rótulo — escrito à mão)", r"LIKE '%{CHAVE}%'", None),
    (PA, "scripts/clientes_telecom.py", "CLIENTE_POR_TECHPREFIX", r"{techprefix}\s*:\s*\"{chave}\"", "techprefix"),
    (PA, "scripts/clientes_telecom.py", "TECHPREFIX_DESDE", r"{techprefix}\s*:\s*\"\d{{4}}-", "techprefix"),
    (PA, "scripts/_dashboard_template.html", "SEM_REAL (techprefix sem tempo real de conversa)", r"'{techprefix}'\s*:", "techprefix"),
    (PA, "scripts/ingest_cdr.py", "aviso 'cpnId sem cliente' (escrito à mão)", r'cpns\("{chave}"\)', None),
    (PA, "scripts/meta_telecom.py", "ORCAMENTO_CLIENTE (fonte do orçamento)", r'"{chave}"\s*:\s*\{{\s*"mensal"', "orcamento"),
    (PA, "scripts/coral_tema.py", "CLIENTE (cor fixa)", r'"{chave}"\s*:\s*"#[0-9A-Fa-f]{{6}}"', None),
    (PA, "scripts/coral_tema.py", "CLIENTE_NOME", r'"{chave}"\s*:\s*"{nome}"', None),
    (PA, "scripts/coral_tema.py", "token CSS --c-{chave}", r"--c-{chave}\s*:", None),
    (PA, "scripts/gerar_controle_tma.py", "OUTROS (seção própria no TMA)", r'"{CHAVE}"\s*:\s*\(', None),
    (PA, "scripts/gerar_home.py", "INICIO (Home neutra antes do início)", r'"{chave}"\s*:\s*"\d{{4}}-\d\d-\d\d"', None),
    (PA, "scripts/gerar_home.py", "SQL de frescor do TMA (CASE escrito à mão)", r"campanha = '{CHAVE}'", None),
    (PA, "scripts/gerar_home.py", "PAINEIS: card do operacional próprio", r'"operacional_{chave}"', "operacional_proprio"),
    (PA, "scripts/gerar_painel_qa.py", "CAMP_CLIENTE (QA: campanha → cliente)", r'"{nome}"\s*:\s*"{chave}"', None),
    (PA, "scripts/gerar_operacional_{chave}.py", "gerador do Operacional do cliente", r"PORTFOLIO\s*=", "operacional_proprio"),
    (PA, ".github/workflows/operacional-{chave}.yml", "workflow do Operacional do cliente", r"gerar_operacional_{chave}\.py", "operacional_proprio"),
    # ── coral-bot: Control Desk, alertas, pacing, QA ───────────────────────────────────────
    (CB, "scripts/campanhas.py", "CAMPANHAS (fonte única de campanhas do bot)", r'"{CHAVE}"\s*:\s*\{{\s*"cpn"\s*:\s*"{cpn}"', None),
    (CB, "scripts/campanhas.py", "OBSERVADAS (não atua no discador)", r'OBSERVADAS\s*=\s*\{{[^}}]*"{CHAVE}"', "observada"),
    (CB, "scripts/campanhas.py", "ALERTAS (fases técnico/relativo)", r'"{CHAVE}"\s*:\s*\{{\s*"desde"', None),
    (CB, "scripts/slack_texto.py", "NOMES (rótulo [Nome] no Slack)", r'"{CHAVE}"\s*:\s*"{nome}"', None),
    (CB, "scripts/monitor_campanhas.py", "CASE do _FUNIL_SQL (funil/bi_snapshots)", r"ILIKE '%{CHAVE}%'\s+THEN '{CHAVE}'", None),
    (CB, "scripts/pacing_custo.py", "ORCAMENTO_CLIENTE (pacing por custo)", r'"{CHAVE}"\s*:\s*\{{\s*"cliente"\s*:\s*"{chave}"', "orcamento"),
    (CB, "scripts/qa_acordos/ocs_lib.py", "CAMPANHAS do QA de acordos", r'"{cpn}"\s*:\s*"{nome}"', None),
    (CB, "scripts/qa_acordos/coletar_acordos.py", "ACORDO_IDS_EXTRA (desfecho exclusivo)", r'"{cpn}"\s*:\s*\[', "acordo_extra"),
    (CB, "scripts/qa_acordos/coletar_acordos.py", "regex de campanha em _rows", r"re\.search\(r'[^']*{CHAVE}", None),
    (CB, "scripts/controldesk_motherduck_sink.py", "PRODUTO_POR_CPN (telemetria)", r'"{cpn}"\s*:\s*"', None),
    (CB, "scripts/startup_check.py", "CAMPS do comunicado de abertura", r'{cpn}\s*:\s*"{CHAVE}"', None),
    # ── coralai-mailing: mailing, Coral Desk, heartbeat ────────────────────────────────────
    (CM, "scripts/campanhas_coral.py", "CAMPANHAS (rótulo → produto/cliente)", r'"cpn"\s*:\s*"{cpn}"', None),
    (CM, "scripts/campanhas_coral.py", "CREDORES (credor do mailing → cliente)", r'"ilike"\s*:\s*"{nome}"\s*,\s*"cliente"\s*:\s*"{chave}"', None),
    (CM, "scripts/baixar_acionamento.py", "CAMPANHA_FILTRO (captura do acionamento)", r'CAMPANHA_FILTRO\s*=.*{CHAVE}', None),
    (CM, "scripts/baixar_mailing.py", "CAMPANHAS (regex da opção do lote)", r'"{CHAVE}"\s*:\s*r"', "mailing"),
    (CM, "scripts/baixar_mailing.py", "NOME_ESPERADO (termo no nome do lote)", r'"{CHAVE}"\s*:\s*"{nome_lote}"', "mailing"),
    (CM, "scripts/baixar_mailing.py", "FILENAME_SUFIXO", r'"{CHAVE}"\s*:\s*"{sufixo}"', "mailing"),
    (CM, "scripts/baixar_mailing.py", "LOTE_DA_CAMPANHA", r'"{CHAVE}"\s*:\s*\[', "mailing"),
    (CM, "scripts/ingest_mailing.py", "_SEGMENT_MAP (sufixo → credor)", r'"{sufixo}"\s*:\s*"{nome}"', "mailing"),
    (CM, "scripts/mailing_status.py", "{CHAVE}_DESDE (lote cobrado a partir de)", r"{CHAVE}_DESDE\s*=", "mailing"),
    (CM, ".github/workflows/coralai-mailing-ingest.yml", "passos de baixar/ingerir do cliente", r"--apenas {sufixo}", "mailing"),
    (CM, "scripts/custo_telecom.py", "ORCAMENTO_CLIENTE (Coral Desk)", r'"{chave}"\s*:\s*\{{\s*"mensal"', "orcamento"),
    (CM, "scripts/heartbeat.py", "{CHAVE}_ALERTA_DESDE (alerta do mailing)", r"{CHAVE}_ALERTA_DESDE\s*=", "mailing"),
    (CM, "dashboard/agentes.js", "NOME_CAMP", r"{CHAVE}\s*:\s*'{nome}'", None),
    (CM, "dashboard/agentes.js", "RODIZIO_MS (rodízio da TV)", r"RODIZIO_MS\s*=\s*\{{[^}}]*{chave}\s*:", None),
    (CM, "dashboard/agentes_tv.html", "aba do cliente na TV", r'data-cli="{chave}"', None),
    (CM, "dashboard/agentes_m.html", "aba do cliente no celular", r'data-cli="{chave}"', None),
    (CM, "dashboard/assets/coral_tema.css", "token de cor --{chave}", r"--{chave}\s*:", None),
]

# orçamento: as três cópias têm de bater (mensal e início)
COPIAS_ORC = [
    (PA, "scripts/meta_telecom.py", r'"{chave}"\s*:\s*\{{[^}}]*?"mensal"\s*:\s*([\d.]+)[^}}]*?"inicio"\s*:\s*"([\d-]+)"'),
    (CB, "scripts/pacing_custo.py", r'"{CHAVE}"\s*:\s*\{{[^}}]*?"mensal"\s*:\s*([\d.]+)[^}}]*?"inicio"\s*:\s*"([\d-]+)"'),
    (CM, "scripts/custo_telecom.py", r'"{chave}"\s*:\s*\{{[^}}]*?"mensal"\s*:\s*([\d.]+)[^}}]*?"inicio"\s*:\s*"([\d-]+)"'),
]


def contexto(f):
    c, d, t, m, p = f["cliente"], f["discador"], f.get("telecom") or {}, f.get("mailing") or {}, f.get("paineis") or {}
    camp = d["campanhas"][0]
    ctx = {
        "chave": c["chave"], "CHAVE": c["CHAVE"], "nome": c["nome"],
        "cpn": str(camp["cpn"]), "rotulo": camp.get("rotulo") or "",
        "techprefix": str(t.get("techprefix") or ""), "sufixo": m.get("sufixo") or "",
        "nome_lote": m.get("nome_lote_contem") or "",
    }
    aplica = {
        None: True,
        "techprefix": bool(t.get("techprefix")),
        "orcamento": bool(t.get("orcamento_mensal")),
        "operacional_proprio": bool(p.get("operacional_proprio")),
        "observada": not d.get("operada", False),
        "acordo_extra": bool(d.get("desfechos_acordo_extra")),
        "mailing": bool(m.get("sufixo")),
    }
    return ctx, aplica, d["campanhas"]


def fmt(s, ctx):
    return s.format(**{k: (re.escape(v) if k not in ("chave", "CHAVE") else v) for k, v in ctx.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ficha", required=True)
    ap.add_argument("--raiz", default="/home/user", help="pasta com os clones dos repositórios")
    a = ap.parse_args()
    f = yaml.safe_load(open(a.ficha, encoding="utf-8"))
    ctx, aplica, campanhas = contexto(f)
    raiz = Path(a.raiz)
    faltas = 0
    print(f"Cobertura da implantação — {ctx['nome']} (chave {ctx['chave']} · {ctx['CHAVE']} · cpn {ctx['cpn']})\n")
    if len(campanhas) > 1:
        print(f"⚠️  {len(campanhas)} campanhas na ficha: o verificador confere a 1ª ({ctx['cpn']}); "
              "repita a revisão manual dos pontos por cpn para as demais.\n")
    repo_atual = None
    for repo, arq, desc, rx, cond in PONTOS:
        if repo != repo_atual:
            print(f"── {repo}")
            repo_atual = repo
        caminho = raiz / repo / fmt(arq, {k: v for k, v in ctx.items()}).replace("\\", "")
        desc = desc.replace("{chave}", ctx["chave"]).replace("{CHAVE}", ctx["CHAVE"])
        if not aplica.get(cond, True):
            print(f"  ⏭️  {desc}  (não se aplica: {cond})")
            continue
        if not caminho.exists():
            print(f"  ❔ {desc}  — arquivo não encontrado: {caminho.relative_to(raiz)}")
            faltas += 1
            continue
        txt = caminho.read_text(encoding="utf-8", errors="replace")
        if re.search(fmt(rx, ctx), txt):
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ {desc}  — {caminho.relative_to(raiz)}")
            faltas += 1

    if aplica["orcamento"]:
        print("\n── Consistência do orçamento (3 cópias)")
        vals = {}
        for repo, arq, rx in COPIAS_ORC:
            p = raiz / repo / arq
            m = re.search(fmt(rx, ctx), p.read_text(encoding="utf-8")) if p.exists() else None
            vals[repo] = (float(m.group(1)), m.group(2)) if m else None
            print(f"  {repo:24} {vals[repo] if vals[repo] else 'NÃO ENCONTRADO'}")
        ficha = (float(f["telecom"]["orcamento_mensal"]), f["cliente"]["inicio_operacao"])
        if len({v for v in vals.values()} | {ficha}) != 1:
            print(f"  ❌ cópias divergem entre si ou da ficha {ficha}")
            faltas += 1
        else:
            print(f"  ✅ as três cópias batem com a ficha {ficha}")

    print(f"\n{'✅ cobertura completa' if not faltas else f'❌ {faltas} ponto(s) pendente(s)'}")
    sys.exit(1 if faltas else 0)


if __name__ == "__main__":
    main()
