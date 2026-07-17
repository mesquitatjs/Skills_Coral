# Coleta OCS via HTTP (sem browser) — recibo do que funciona no sandbox

Descoberto em produção (17/07/2026) rodando o A/B de fornecedor de ASR direto do sandbox
(sem `claude-in-chrome`). Vale quando não há browser, só `requests` + proxy.

## O que FUNCIONA por HTTP
- **Login** (ASP.NET WebForms): `GET Login.aspx` → extrair `__VIEWSTATE/__VIEWSTATEGENERATOR/__EVENTVALIDATION`
  → `POST` com `txtUsuario/txtSenha/btnLogar`. Cookie de sessão autentica o resto. Ver `scripts/ocs_http/ocs_login.py`.
- **Filtro de PERÍODO** (`txtDtIni/txtDtFim`, `datetime-local` `yyyy-MM-ddTHH:mm`): **funciona** no postback.
- **Log por chamada:** PageMethod **`callResultInteractions.aspx/GetLogComplete`**, `POST` JSON
  `{callResultId, bytesIni}` → `{log, ended, nextBytes}` (paginar por bytes até `ended`). Rápido e limpo.
- **Lista de chamadas:** a grade traz `callResultId="..."` por linha; `Campanha` e `Última Interação` em `<td>`.

## O que NÃO funciona por HTTP (armadilha)
- **Filtro de CAMPANHA (`ddlCampaigns`) e de LOTE (`ddlLot`) NÃO colam** postando o valor do `<select>`.
  É widget **jQuery `multipleSelect`**; a seleção é client-side e o servidor ignora o valor postado
  (testado: POST do select, async postback UpdatePanel, e disparar os AJAX `getInteraction`/`GetLotsByCampaign`
  antes — todos voltam TODAS as campanhas). No browser funciona (por isso a coleta oficial usa Chrome).
- **Workaround que funciona:** **fatiar o período em blocos curtos** (30 min — dados passados são imutáveis,
  sem o problema do "ao vivo"), paginar cada fatia e **filtrar a campanha no cliente** pela coluna Campanha.
  Ver `scripts/ocs_http/collect_day.py` (auto-relogin embutido; a sessão expira em runs longos).

## Achados de QA (17/07/2026)
- **O log NÃO carimba o fornecedor de ASR.** A transcrição vem via `api.coralai.com.br/api/provider/...`
  (abstração `provider` da CoralAI) e o payload é **Whisper-style** (`avg_logprob/compression_ratio/
  no_speech_prob/confidence/start/end/text`) — **idêntico** em dias com fornecedores supostamente diferentes.
  → Para A/B de fornecedor ser auto-validável, pedir **tag de `engine`/`model`/`version`** na resposta.
- **⚠️ Segredo vazando:** uma chave **`pk_live_…` (X-Provider-Key)** aparece em texto no log de chamada.
  Recomendação: **mascarar no log e rotacionar**.
- **Contactabilidade varia MUITO por dia** no mesmo horário (ex.: 16/07 10–12h = 99% "Abandonada - Sem Resposta";
  15 e 17/07 ~75%). É sinal de atendimento/mailing, **não** de ASR (ASR só existe pós-atendimento).
  → Escolher dia-controle com volume de conexão comparável (16/07 não serviu; 15/07 sim).

## Métrica de ASR usada (cohort pequeno → indicativo)
Primária: **NO_MATCH rate** = transcrições vazias / total de turnos do cliente, no cohort **conectadas**
(exclui abandonadas). Secundária (sub-cohort da oferta): captura limpa do termo decisivo. Ver `scripts/ocs_http/metrics.py`.
2h/dia dá cohort de dezenas → sem significância; para detectar ~4pp precisa **dia inteiro / vários dias**.
