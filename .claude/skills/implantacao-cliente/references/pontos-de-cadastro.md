# Pontos de cadastro por cliente

Onde um cliente novo precisa estar escrito para cada controle funcionar. Levantado em 01/10/2026,
depois da implantação da Bull. A Bull é o exemplo de cada linha.

- Procure pela **constante**, não pela linha: as linhas mudam.
- `scripts/verificar_cobertura.py` confere automaticamente os pontos marcados com ✔.
- Os marcados com ✋ não são uma entrada num dict. São código escrito à mão (um `CASE`, um `if`, um ramo), revisão manual ou ação operacional.

Para cada ponto, a coluna "Se faltar" diz o que acontece. Quase sempre é silêncio: o painel não mostra o cliente, o alerta não sai ou o custo cai em `desconhecido`. Por isso o verificador existe.

---

## 1. principia-acionamento — telecom, painéis, tema

| # | Arquivo · constante | Exemplo da Bull | Se faltar | |
|---|---|---|---|---|
| 1 | `scripts/clientes_telecom.py` · `CLIENTE_POR_CPN` | `"1824": "bull"` | o custo do CDR cai em `desconhecido` e nenhum painel enxerga o cliente | ✔ |
| 2 | `clientes_telecom.py` · `NOME_CLIENTE` | `"bull": "Bull"` | o cliente não aparece no seletor do Dashboard Telecom | ✔ |
| 3 | `clientes_telecom.py` · `sql_cliente_campanha()` | `WHEN … LIKE '%BULL%' THEN 'bull'` | ✋ é um `CASE` escrito à mão: o acionamento do cliente não é atribuído a ele | ✔ |
| 4 | `clientes_telecom.py` · `CLIENTE_POR_TECHPREFIX` + `TECHPREFIX_DESDE` | `{647884: "bull"}` · `{647884: "2026-10-01"}` | sem checagem cruzada techprefix × campanha (só se o cliente tiver techprefix próprio) | ✔ |
| 5 | `scripts/_dashboard_template.html` · `SEM_REAL` (JS) | `'647884': {nome:'Vonex · Bull', …}` | a aba Qualidade calcula eficiência falsa de 100% na rota Vonex do cliente | ✔ |
| 6 | `scripts/ingest_cdr.py` · aviso "cpnId sem cliente" | `ct.cpns("bull")` | ✋ escrito à mão: cada ingestão gera um `::warning` falso | ✔ |
| 7 | `scripts/criar_views_custo.py` (rodar) | — | ✋ a view `acionamento.custo_telecom_por_cliente` fica **gravada** no MotherDuck com o `CASE` antigo. Rodar `python scripts/criar_views_custo.py` depois de mexer em #1. Nenhum workflow faz isso sozinho | — |
| 8 | `scripts/meta_telecom.py` · `ORCAMENTO_CLIENTE` | `"bull": {"mensal": 2372.00, "inicio": "2026-10-05", "custo": "real"}` | sem orçamento no Telecom e no Operacional. **Fonte** das 3 cópias (#26 e #35) | ✔ |
| 9 | `scripts/coral_tema.py` · `CLIENTE` + `CLIENTE_NOME` + token `--c-<chave>` | `"bull": "#F472B6"` · `"bull": "Bull"` · `--c-bull` | ⚠️ `CLIENTE` sem `CLIENTE_NOME` = **KeyError** no painel de QA | ✔ |
| 10 | `scripts/gerar_controle_tma.py` · `OUTROS` + `BULLC`/`CAMPCOL`/`CAMPNOME` | `{"BULL": ("u", "bull")}` | sem seção do cliente no TMA. ⛔ **Não** pôr em `CAMPS` (é da Principia) | ✔ |
| 11 | `scripts/gerar_home.py` · `CLIENTES`, `INICIO` | `["principia","bull"]` · `{"bull": "2026-10-05"}` | a Home não mostra o cliente, ou mostra 🔴 antes do início | ✔ |
| 12 | `gerar_home.py` · `_SQL` (frescor do TMA) | `CASE WHEN campanha = 'BULL' THEN 'bull' ELSE 'principia'` | ✋ escrito à mão: o cliente novo cai como `principia` | ✔ |
| 13 | `gerar_home.py` · `PAINEIS` | `"clientes"` de telecom/estrategia/tma/qa + card `operacional_bull` com botões Interno/Externo | o card não lista o cliente nem leva ao painel dele | ✔ |
| 14 | `scripts/gerar_painel_qa.py` · `CAMP_ORDEM`, `CAMP_CLIENTE`, `CLIENTES`, `PENDENTE` | `"Bull": "bull"` | o QA do cliente aparece como `desconhecido` | ✔ |
| 15 | `scripts/gerar_operacional_<chave>.py` + `scripts/operacional-<chave>/` + `.github/workflows/operacional-<chave>.yml` | cópia do da Bull: `PORTFOLIO`, `CLIENTE`, `BOTS`, `BOT_PRECO_MES`, `PRECO_*`, `COMISSAO`, projetos Vercel | sem Operacional próprio (cliente + interno) | ✔ |
| 16 | `scripts/cdr_mudou.py` · assinatura | só os cpnIds da Principia | ✋ só mexer se o CDR do cliente tiver de disparar a cascata Principia sozinho (em geral **não**) | — |

**Não cadastrar o cliente** nas peças que são só da Principia: `SO_PRINCIPIA` (views `custo_diario_telecom*`), `producao_bq.PORTFOLIO/SUB2SEG`, faturamento V2, post de telecom, `confirmacao-ptp`, `funil-md-publicar`. Cliente novo que precisar dessas entregas ganha **peça própria**, sem misturar com as da Principia.

## 2. coral-bot — Control Desk, alertas, pacing, QA de acordos

| # | Arquivo · constante | Exemplo da Bull | Se faltar | |
|---|---|---|---|---|
| 17 | `scripts/campanhas.py` · `CAMPANHAS` | `"BULL": {"cpn": "1824", "cliente": "bull"}` | o bot não enxerga a campanha. É a fonte de `CAMP_IDS`, `TODAS`, `OPERADAS`, e a **chave** vira o `ILIKE '%BULL%'` do pacing | ✔ |
| 18 | `campanhas.py` · `OBSERVADAS` | `{"BULL"}` | ⛔ sem isso, o bot **atua** no discador do cliente (pausa por spin, StopLote, troca de rota) sem régua acordada | ✔ |
| 19 | `campanhas.py` · `ALERTAS` | `{"desde": "2026-10-05", "relativos_desde": "2026-10-26"}` | ⛔ sem isso, alerta **tudo e sempre**: inclusive relativos sem baseline, ou seja, ruído no 1º dia | ✔ |
| 20 | `scripts/slack_texto.py` · `NOMES` | `"BULL": "Bull"` | alerta sem o tag `[BULL]` | ✔ |
| 21 | `scripts/monitor_campanhas.py` · `CASE` do `_FUNIL_SQL` | `WHEN campanha ILIKE '%BULL%' THEN 'BULL'` | ✋ escrito à mão: sem funil e sem `bi_snapshots` do cliente | ✔ |
| 22 | `scripts/pacing_custo.py` · `ORCAMENTO_CLIENTE` | `"BULL": {"cliente": "bull", "mensal": 2372.00, "inicio": "2026-10-05", "canais": 16, "bots": 2}` | sem pacing por custo, sem abertura por custo e sem alertas de orçamento e capacidade. ⚠️ Constantes globais herdadas: `SAB_FATOR`, `K_TENT_PADRAO = 0.02` e `THR_CANAL_H = 150`, este último calibrado para TMA de ~2 min. Revisar para cada cliente | ✔ |
| 23 | `scripts/qa_acordos/ocs_lib.py` · `CAMPANHAS` | `"1824": "Bull"` | o juiz de QA não coleta os acordos do cliente | ✔ |
| 24 | `qa_acordos/coletar_acordos.py` · `ACORDO_IDS_EXTRA` + regex de `_rows` | `{"1824": ["1275"]}` · `…\|BULL\|…` | perde os acordos que usam desfecho próprio. Descobrir com `qa-acordos-descobrir.yml` (input `cpns`) | ✔ |
| 25 | `scripts/controldesk_motherduck_sink.py` · `PRODUTO_POR_CPN` | `"1824": "Bull"` | a telemetria grava `produto = "Outro"` | ✔ |
| 26 | `scripts/startup_check.py` · `CAMPS` | `1824: "BULL"` | o cliente não entra no comunicado de abertura | ✔ |
| 27 | `AGRESS_CAMPS` / `_CAMP_ILIKE` (`bot/app.py`) + `config/spin_rules.json` | sem a Bull, **de propósito** | ✋ só entra quando houver régua de spin acordada **e** histórico. Aí sai de `OBSERVADAS` | — |
| 28 | `scripts/relatorio_diario.py` · `CASE` de tentativas | sem a Bull | ✋ só para cliente com pacing de spin | — |
| 29 | `scripts/qa_acordos/capturar_abandonadas.py` · `CPN` | sem a Bull | ✋ o áudio abandonado sai com cpn vazio; cadastrar se o QA de microfone tiver de cobrir o cliente | — |
| 30 | `.github/workflows/control-desk-atuar.yml` · `options` | só as 4 da Principia | ✋ acrescentar se for preciso atuar no cliente pelo workflow (a API já aceita) | — |
| 31 | Render (env) · `PACING_CUSTO_OFF` | vazio | kill switch: `1`/`ALL`/`<CHAVE>` faz o pacing só gravar a proposta, sem atuar | — |

## 3. coralai-mailing — mailing, Coral Desk, heartbeat

| # | Arquivo · constante | Exemplo da Bull | Se faltar | |
|---|---|---|---|---|
| 32 | `scripts/campanhas_coral.py` · `CAMPANHAS` | `{"cpn":"1824","ilike":"%BULL%","produto":"Bull","cliente":"bull"}` | o Coral Desk não gera `custo_cliente`/`funil_cliente`/`base_cliente`. ⚠️ A ordem do dict importa | ✔ |
| 33 | `campanhas_coral.py` · `CREDORES` | `{"ilike":"Bull","cliente":"bull"}` | `sql_credor_apenas` não corta o mailing e o **guardrail da Principia passa a contar o cliente** (bloqueia o plano) | ✔ |
| 34 | `scripts/baixar_acionamento.py` · `CAMPANHA_FILTRO` | `"PRINCIPIA\|BULL"` | o acionamento do cliente não é capturado. Cadastrar **depois** do #32 | ✔ |
| 35 | `scripts/custo_telecom.py` · `ORCAMENTO_CLIENTE` | `"bull": {"mensal":2372.00,"inicio":"2026-10-05","canais":16,"bots":2}` | o cartão de custo fica "sem alvo" no Coral Desk | ✔ |
| 36 | `scripts/baixar_mailing.py` · `CAMPANHAS`, `NOME_ESPERADO`, `FILENAME_SUFIXO`, `LOTE_DA_CAMPANHA` | `r"^HIB - BULL \(CORAL AI\)$"` · `"bull"` · `"_bull"` · `["bull"]` | o lote do cliente não é baixado. ⛔ **Não** pôr em `CAMPANHAS_TODAS` (é da Principia) | ✔ |
| 37 | `scripts/ingest_mailing.py` · `_SEGMENT_MAP` + escolha do loader | `"_bull": "Bull"` · `endswith("_bull") → load_mailing_bull` | ✋ layout próprio exige ramo novo no `if` + loader novo | ✔ (mapa) |
| 38 | `scripts/utils.py` · `<CHAVE>_COLUMN_MAP`, `<CHAVE>_OPCIONAIS`, `load_mailing_<chave>()` | ver `BULL_COLUMN_MAP` | ✋ loader do layout do cliente: CSV com `;`, cabeçalho repetido, decimal BR | — |
| 39 | `ingest_mailing.py` · `col_map` / `_COLUNAS_NOVAS` | `segmento`, `valor_original`, `qtd_pagas` | ✋ coluna nova = ALTER idempotente aqui | — |
| 40 | `scripts/mailing_status.py` · `ESPERADOS_<CHAVE>`, `<CHAVE>_DESDE` (saída `completo_<chave>`) | `["bull"]` · `"2026-10-02"` | o status não cobra o lote. ⛔ O cliente fica **fora** do gate `completo` da Principia | ✔ |
| 41 | `.github/workflows/coralai-mailing-ingest.yml` · passos do cliente | `--campanha BULL` · `--apenas _bull` · `!cancelled()` | ✋ passos próprios; falha do cliente não pode derrubar a Principia | ✔ |
| 42 | `scripts/heartbeat.py` · `<CHAVE>_ALERTA_DESDE` + check `[NOME] Mailing` | `"2026-10-05"` | ✋ sem alerta de lote não entregue (🟠, não crítico) | ✔ |
| 43 | `scripts/estrategia_common.py` · `_SEGMENTOS_<CHAVE>` | `["QUEBRA_DE_VINCULO","ESCRITURADO","NAO_ESCRITURADO"]` | ✋ a Base do dia sai sem ordem de segmento | — |
| 44 | `dashboard/agentes.js` · `NOME_CAMP`, `RODIZIO_MS`, `BASE_SEG` | `BULL:'Bull'` · `bull: 60000` · rótulos/SPT por segmento | sem nome, rodízio padrão de 15 s, e a Base sem rótulo | ✔ (2 de 3) |
| 45 | `dashboard/agentes_tv.html` + `agentes_m.html` · aba `data-cli`, cor, logo, texto "sem leitura" | `data-cli="bull"`, `#F472B6`, `'consignado · sem leitura'` | ✋ não aparece aba do cliente. A cor está **escrita à mão** em vários seletores | ✔ (aba) |
| 46 | `dashboard/assets/coral_tema.css` · `--<chave>` + `assets/<chave>_logo*.png` | `--bull:#F472B6` | sem cor nem logo | ✔ (cor) |
| 47 | `scripts/build_dashboard_data.py` · filtros `'_bull'` | exclui a Bull | ✋ dashboard antigo de mailing: excluir o sufixo do cliente | — |

**Fora do código:** o `/agentes-live` (coral-bot) precisa devolver `cliente` na campanha. Isso já vem de `campanhas.CAMPANHAS` (#17). Sem isso a aba fica "sem leitura" e o rodízio ignora o cliente.

## 4. Fora dos repositórios

| Onde | O quê |
|---|---|
| OCS SinergyTech | campanha (cpnId, rótulo), techprefix na campanha, lote de mailing com nome padronizado, desfechos/SPT do fluxo |
| Vonex (portal) | techprefix na conta já capturada (100777/100778). Conta nova = credencial nova + passo na `captura-cdr-vonex` |
| BigQuery | `portfolio_id` (e sub-portfólios) do cliente em `intermediate.dim_portfolio` |
| Vercel | projetos do Operacional (cliente + interno com nome não óbvio). A senha do interno é a `HOME_SENHA` |
| cron-job.org | job novo só se houver rotina agendada própria do cliente (`config/cron_jobs.json` do principia-acionamento) |
| Slack | canal do cliente, se houver; alertas operacionais seguem no #control-desk com `[NOME]` |
| Meta / WABA | HSMs do cliente aprovados, linha de WhatsApp definida |
| Render | nada por cliente além do kill switch `PACING_CUSTO_OFF` |
