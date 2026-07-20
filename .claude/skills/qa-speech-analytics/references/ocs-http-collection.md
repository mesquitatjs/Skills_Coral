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

## Filtros — o servidor lê HIDDEN, não os controles (CORRIGIDO 20/07/2026)
A armadilha era postar o valor do `<select>` (`ddlCampaigns`/`ddlInteractionsFinal`): o servidor
**ignora os controles**. O botão **Buscar** sincroniza a seleção para **campos hidden** por JS, e é
esses que o servidor lê. Basta postar os hidden certos e o filtro cola **server-side**:

| Filtro | Controle (ignorado) | HIDDEN a postar (funciona) | Valor |
|--------|---------------------|----------------------------|-------|
| **Campanha** | `ddlCampaigns` (widget multipleSelect) | **`hdListCpnId`** | id da campanha — Bronze **1737** · Ouro 1673 · PrincipiaPay 1741 |
| **Última Interação** | `ddlInteractionsFinal` | **`hdInteracaoFinal`** | `interactionID` (ver getInteraction) |
| Interações (multi) | `ddlInteractions` | `hdInteractions` | — |
| Lote | `ddlLot` | `hdListIdLot` | — |

Prova (17/07): `hdListCpnId=1737` → **100% Bronze** (sem vazamento); `hdInteracaoFinal=2439` →
**100% "Ligação Abandonada"**. A coleta antiga postava `ddlCampaigns` (ignorado) e filtrava no
cliente — daí o vazamento de outras campanhas.

**Opções de Última Interação** (dependem da campanha): PageMethod
`POST callResultInteractions.aspx/getInteraction` com body `{campaigns: <id>}` (Content-Type JSON) →
`data.d = [{interactionID, interactionName}]`. Ex. Bronze: 41 opções (1006=VALIDOU CPF,
2439=Ligação Abandonada, 2318=RECUSA TODAS…). A **última coluna** da grade é a "Última Interação".

## Paginação quebrada → subdivisão adaptativa do tempo
A paginação async do GridView **não avança** (a "página 2" volta um subconjunto da página 1). Em vez
de paginar, **subdivide a janela de tempo** recursivamente: qualquer janela que encoste no teto de
página (20 linhas) ou exiba pager é dividida ao meio até caber numa página (1 busca = 1 página, nada
truncado). Bronze roda ~14/10min, ~20/30min. Ver `scripts/ocs_http/collect_day.py` (auto-relogin;
salva incremental por hora; assert de 0-vazamento e de homogeneidade da última interação).

Uso: `python collect_day.py <YYYY-MM-DD> <saida.json> [cpnId=1737] [interacaoFinalId] [hIni=10] [hFim=12]`

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
