---
name: qa-speech-analytics
description: >
  QA e Speech Analytics do voice bot de cobrança da CoralAi (operação HIB Principia,
  plataforma OCS Sinergytech). Use SEMPRE que o contexto envolver: avaliar a performance
  do voice bot de cobrança, analisar logs/transcrições de chamadas, "por que não fechou/
  não converteu", falhas de ASR/entendimento, NO_MATCH, funil de negociação, hotwords,
  A/B de mudança do fornecedor de ASR, acurácia de reconhecimento, auditoria de áudio,
  aceites perdidos, objeções, pedido de atendente humano, ou chamado técnico ao fornecedor.
  Também acione para métricas de conversão/oferta/acordo do bot, coleta de logs no OCS
  Sinergytech, ou qualquer pergunta sobre "o bot entendeu certo?". Campanhas: Principia
  Ouro (1673), Bronze (1737), PrincipiaPay (1741). Regra máxima: nunca reportar número que
  não seja estatisticamente honesto (controlado por viés, normalizado por etapa).
---

# QA & Speech Analytics — Voice Bot de Cobrança (Coral AI / Principia)

Avalia a performance do voice bot e transforma logs (e, sob demanda, áudio) em **insights
de produto** (falhas de ASR/fluxo), **insights de negócio** (conversão/objeções/aceites
perdidos) e **evidência acionável** (chamados ao fornecedor, recomendações priorizadas).

> **Referência completa** (seletores do OCS, regexes, snippets de coleta testados, pipeline
> diário, diretórios): **`references/knowledge-base.md`** — leia antes de coletar ou parsear.

## Prime directive — número honesto ou nada
Nunca apresente um número que não seja **estatisticamente honesto**: controlado por viés,
normalizado por etapa e, quando possível, validado contra o áudio. **É preferível dizer
"indeterminado" a inflar.**

## Passo 0 — qual camada?
| Pergunta é sobre… | Camada | Mede |
|---|---|---|
| volume / jornada / funil / tendência / hotwords | **A — LOG** | output do ASR + etapa alcançada (escala: centenas/dia) |
| "o bot **entendeu** certo?" / acurácia do ASR | **B — ÁUDIO** | cliente disse × ASR captou (on-prem, dezenas/dia) |

## Não-negociáveis (é o que torna o número defensável)
1. **Campanha SEMPRE por `@CAMPAIGNID`** (1673/1737/1741), **nunca** pelo credor.
2. **Determinismo onde dá:** acordo (gatilho de texto), campanha (ID), aceite perdido
   (derivado), NO_MATCH (transcrição vazia) = **REGRA, não LLM**. LLM só para ambiguidade
   semântica (causa-raiz, intenção, acurácia).
3. **Normalização por etapa (anti-mix):** comparação entre dias só vale no **mesmo cohort do
   funil**. O mix de categorias muda todo dia e engana o número bruto. (Caso real: NO_MATCH
   "caiu" 1,96→1,52 só por mix; no cohort "chegou à oferta" ficou igual — o ganho real estava
   na captura limpa do termo decisivo 21%→40% e conversão 14%→23%.)
4. **Variância × viés:** variância resolve com volume; **viés NÃO** — resolve com os fixes de
   diarização/prompt (Camada B). Mais volume não conserta medição torta.
5. **"Indeterminado" é resposta válida** — áudio mono deixa ~metade sem julgamento: excluir,
   não chutar.
6. **Sem cap silencioso:** se limitar cobertura (top-N, amostra, sem retry), **registrar o que
   ficou de fora**.
7. **Todo achado tem trecho-prova:** `CASE_ID` + citação real.

## Achado estrutural conhecido — CHECAR ANTES DE CULPAR O ASR
**O fluxo NÃO tem nó de fechamento/entrega** (nada de boleto/link/PIX/SMS/WhatsApp). Quando o
cliente escolhe à vista ou parcelar — mesmo confirmando ("Sim, confirmo, sim!") — o bot
**registra o desfecho e desliga**. As categorias "CLIENTE DESEJA PARCELAR" e "OFERECE
PAGAMENTO À VISTA" são **becos sem saída**: 100% de intenção, 0% de conversão. Por isso
`acordo_fechado` é **0 por construção** nessas trilhas.
→ Ao investigar "por que não fecha", **primeiro verifique se existe nó de fechamento** (§9 da
KB). Não presuma que é ASR/entendimento.

## Coleta (resumo — mecânica detalhada na KB §3–5)
- Fonte: **OCS Sinergytech** (`callResultInteractions.aspx`), ASP.NET WebForms.
- Via **Chrome MCP** (usuário logado) + **carrier `window.name → localhost:8090`** (PII nunca
  volta pelo assistente; tools retornam só agregados/metadados/`CASE_ID`/primeiro nome).
- Armadilhas: UpdatePanel (esperar ~3,5 s pós-Buscar), multiselect jQuery (marcar via
  `checkbox.click()`), paginar **todas** as páginas, modal stale (esperar `CASE_ID` novo).
- Robô agendado usa **conta de serviço** (o OCS bloqueia sessão concorrente).

## Parsing determinístico (chaves — regexes completos na KB §6)
- Campanha `@CAMPAIGNID'=>'(\d+)'` · `CASE_ID` `"CASE_ID","([0-9a-f-]{36})"`.
- Fala do cliente: `Transcription Success, Response [...]` → `"text":"..."`; **vazio = NO_MATCH**.
- Nó do fluxo: `Process node. '(\d+) nome'`.
- Derivados: `reached_offer` (texto da oferta), `acordo_fechado` (gatilho de coleta de
  pagamento — **False por construção se não há nó de fechamento**), `aceite_perdido`
  (aceitou E não fechou).
- Reconstruir o **diálogo interleaved** (bot × cliente cronológico) revela onde a chamada morreu.

## Camada B — auditoria de áudio (quando "o bot entendeu?")
On-prem, nunca enviar áudio a serviço externo. `whisperx_diarize.py` (WhisperX medium + pyannote,
VAD **silero**, patch `torch.load weights_only=False`, `HF_TOKEN`) separa por voz; `asr_audit_wx.py`
compara fala real × ASR de produção via Haiku. **Dois fixes de viés:** (1) filtrar vazamento de bot
no lado cliente → se vazio, `indeterminado`; (2) marcar **erro só quando o ASR perdeu o sentido**
(variação fonética que preserva significado = ok).

## Playbook de investigação
- **"Por que não fechou?"** → jornada + **checar nó de fechamento primeiro** (§9), depois ASR.
- **"Melhoria X funcionou?"** → A/B **normalizado por cohort**, nunca bruto; separar **cobertura**
  (volume) de **acurácia** (Camada B).
- **"% de clientes que fazem Y"** → regex nas falas (`text`); reportar na **base limpa** (frase
  inteira) e sinalizar subcontagem se a amostra estiver fragmentada.
- **"Erro real do ASR?"** → Camada B com os 2 fixes; reportar % + turnos julgáveis + indeterminados.
- **Amostra pequena (≤ dezenas):** caso a caso com diálogo interleaved e trechos-prova; não estatística.

## Segurança & LGPD
Áudio on-prem · PII fora do assistente (carrier) · nunca PII em URL/query-string · tokens colados
em chat = **rotacionar** · nunca inserir credenciais em nome do usuário (`~/.coral-sa.env`).

## Entregáveis
Resumo diário (2 vieses, Slack) · Dashboard (Vercel `coral-qa-dashboard` — editar `index.html` **e**
`dashboard.html`, `node --check` antes; **confirmar com o usuário antes de publicar**) · Chamado ao
fornecedor (`.md`+`.docx`, com `CASE_ID`/data/hora/telefone/padrão/trechos-prova) · Resumo de A/B.
Pipeline diário: `run_daily.py` (coletar → analisar → sintetizar → entregar) — scripts em `coral_qa/`
na máquina do operador (não neste sandbox).

## Scripts incluídos
- **`scripts/ocs_http/fingerprint_fluxo.py`** — **QA passivo (Fase 0)**: retrato do fluxo por
  campanha/dia (falas do bot, janela de captura por nó, se o nó chama o ASR, falha por nó) e
  **diff contra o baseline** — acusa deploy de script, nó novo/renomeado/sumido, janela de captura
  alterada e variação de falha **estatisticamente significativa** (z de duas proporções). Sai com
  código 2 quando há regressão, para encadear em alerta. Fingerprint é **PII-safe** (falas
  canonizadas; instância resolvida de template é descartada) → versionável em git.
  `--logs <dir> --saida fp/ [--comparar fp/X.json]` · `--diff ANTES AGORA` · `--contem` para
  recortar pós-deploy.
  > Nasceu do deploy do PPay em 28/07/2026, que trocou textos **sem mudar um único ID de nó** e
  > não disparou nada. Regras que o script embute e que já custaram números errados:
  > (1) o nó de uma gravação é o `Process node` **ANTERIOR** ao `RecordTemp audio`;
  > (2) gravação sem `Transcription` pode ser nó de **VAD puro** (o `(288)` grava toda chamada e
  > nunca transcreve) — contar como falha dobra a taxa global;
  > (3) ausência só é notícia quando havia amostra para ver (corte: esperado ≥ 5 sob a taxa antiga).
- **`scripts/ab_asr_vendor.py`** — A/B do fornecedor de ASR por corte de horário dentro do dia,
  normalizado pelo **cohort da oferta**. **PII-safe** (só agregados + `CASE_ID`). Roda na máquina
  do operador sobre os logs coletados; devolve NO_MATCH/chamada, captura limpa do termo decisivo e
  termo no n-best, OLD×NEW. `--campaign 1737` (Bronze) · `--cutoff 10:00` · `--peek N` (calibrar
  o parser sem expor PII antes de confiar no A/B). Não usa acordo (0 por construção).

## Checklist antes de reportar QUALQUER número
- [ ] Campanha por `@CAMPAIGNID` (não credor)?
- [ ] Métrica determinística feita por regra (não LLM)?
- [ ] Comparação temporal normalizada por etapa (cohort)?
- [ ] Amostra fragmentada sinalizada (possível subcontagem)?
- [ ] "Indeterminado" excluído em vez de chutado?
- [ ] PII fora do que voltou pelo assistente?
- [ ] Achado tem trecho-prova (`CASE_ID` + citação)?
- [ ] Se é "não fecha", verifiquei o nó de fechamento antes de culpar o ASR?
