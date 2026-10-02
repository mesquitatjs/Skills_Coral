# Inventário: controles, automações, alertas e painéis das operações

Retrato de 01/10/2026, com duas operações: **Principia** (completa) e **Bull** (estreia em 05/10).

A coluna "Bull" responde a uma pergunta: um cliente novo, implantado como a Bull, ganha esta peça? Ela serve de cardápio para a Fase 2 da skill.

- ✅ ganha a peça.
- 👁 ganha só leitura ou observação.
- — não ganha: a peça é só da Principia (régua, plano, faturamento).

Repositórios: **PA** = principia-acionamento · **CB** = coral-bot (Render) · **CM** = coralai-mailing.

---

## 1. Captura e ingestão de dados

| Peça | Repo | Gatilho | O que faz | Bull |
|---|---|---|---|---|
| `captura-cdr-vonex.yml` | PA | cron-job.org 08:00 e 11:00, todo dia (`modo=full`) | Playwright no portal Vonex: CDR de D-1 → `ingest_cdr.py --allow-empty` → `acionamento.cdr_telecom` (o cliente sai do cpnId; techprefix é checagem cruzada) | ✅ |
| `cdr-diario.yml` | PA | só dispatch | CDR por e-mail (rota Lemit, parada desde 27/07) | — |
| `coralai-mailing-ingest.yml` | CM | schedule 07:43–10:53 seg–sáb + cron-job.org | lote do OCS → `mailing.registros`/`ingestao_log`. **Passos próprios por cliente** com `!cancelled()`; status `completo` (gate da Principia) × `completo_<chave>` | ✅ |
| `coralai-acionamento.yml` | CM | horas pares (schedule) + ímpares (cron-job.org) | relatório de acionamento do OCS (`CAMPANHA_FILTRO`) → `acionamento.interacoes_raw` | ✅ |
| `funil-md-publicar.yml` | PA | cron-job.org 08:50 seg–sáb | funil BQ → `acionamento.funil_diario` | — |
| `pagamentos-ingest.yml` | PA | dispatch (bloqueado pelo Workspace) | Drive → `pagamentos_analitico` | — |

## 2. Control Desk (coral-bot, Render, `_monitor_job` a cada 5 min)

| Peça | O que faz | Bull |
|---|---|---|
| `monitor_discagem.py` | canais, discagem, 8 desfechos, TME → `controldesk.discagem_snapshots`; resumo de 15 min e alerta crítico | ✅ (coleta todas; Slack pelas fases de `ALERTAS`) |
| `monitor_campanhas.py` | funil Alô/CPC/acordo → `controldesk.bi_snapshots` | ✅ (precisa do `CASE`) |
| `_ler_config_campanhas` | qtdChannels/callRatio/techprefix → `campanha_config`; alerta de rota alterada fora do bot | 👁 (lê; alerta de rota só para OPERADAS) |
| `_checar_capacidade_orcada` | canais ≠ contratado → 🔧 | ✅ (com orçamento) |
| `_abertura_custo` + `_pacing_custo` | abre às 08h no ritmo do orçamento; 1×/h ajusta a razão 1..canais; freia no orçamento do dia (alvo rebalanceado pelo gasto do mês) → `controldesk.pacing_custo` | ✅ (**único controle que escreve no discador da Bull**; kill switch `PACING_CUSTO_OFF`) |
| `_abertura_razao_cheia` + `_pacing_spin` + freio | pacing pela régua de spin | — (só com régua) |
| auto-pausa por spin, retomada, troca de rota, StopLote no fechamento, mailing atrasado | atuação no discador | — (só OPERADAS; a Bull é OBSERVADA) |
| relatório de fechamento (`relatorio_diario.py`) | 20:40 / 14:20 → Slack 📋 | ✅ (a partir de `ALERTAS.desde`) |
| `/agentes-live` | estado ao vivo por campanha, com `cliente` e `observada` | ✅ |
| `qa-acordos-piloto.yml` | 07:00 ter–dom: coleta acordos de D-1, transcreve (OpenAI), julga (gpt-4o) → `controldesk.acordo_qa` | ✅ (cpn em `ocs_lib` + desfechos) |
| `qa-vao-microfone.yml` | alarme do vão de microfone | 👁 (amostra todo o `interacoes_raw`) |
| `agentes_live_healthcheck.yml` | GET em `/agentes-live` a cada 10 min (cron-job.org) | ✅ (global) |

## 3. Planejamento e Coral Desk (coralai-mailing)

| Peça | O que faz | Bull |
|---|---|---|
| `coralai-planejador.yml` | plano do dia (meta, alocação) → `estrategia.plano_dia`; card 🎯 | — (só com plano/régua) |
| `coralai-reconciliador.yml` | realizado × plano → card 🚦 | — |
| `build_estrategia_dashboard.py` | JSON do dia: `custo_cliente`, `funil_cliente`, `base_cliente` | ✅ |
| Coral Desk (TV `agentes_tv.html`, celular `agentes_m.html`, `agentes.js`) | abas por cliente, rodízio na TV com contador, Base do dia, custo × alvo/orçamento, capacidade (bots·canais) | ✅ |
| `coralai-comunicado-principia.yml` | texto de WhatsApp 09:15 | — |

## 4. Painéis (Vercel) — Home: https://coral-paineis.vercel.app (senha `HOME_SENHA`)

| Painel | Gerador / workflow | Multi-cliente | Bull |
|---|---|---|---|
| Telecom (interno) `ptc-interno-9f3k2m` | `gerar_dashboard.py` · `dashboard-refresh.yml` | seletor (`NOME_CLIENTE`) + Total; cliente fora da Principia vê só custo do CDR; visão de orçamento | ✅ |
| Operacional Principia `dashboard-alpha-eight-80` | `gerar_dashboard_operacional_bq.py` | não | — |
| **Operacional <cliente>**: externo (cliente) + interno (senha) | `gerar_operacional_bull.py` · `operacional-bull.yml` (após a captura Vonex) | um por cliente | ✅ (modelo a copiar) |
| Controle TMA (ASR) `controle-tma-asr` | `gerar_controle_tma.py` (live) | seção própria por cliente (`OUTROS`) | ✅ |
| QA de acordos `qa-acordos-painel` | `gerar_painel_qa.py` (live) | filtro por cliente (`CAMP_CLIENTE`) | ✅ |
| Home dos Painéis | `gerar_home.py` · `home-paineis.yml` | chips e frescor por cliente; card com botões Interno/Externo | ✅ |
| Controle de Workflow `coral-automacoes` | `gerar_dashboard_agentes.py` | n/a | ✅ (global) |

## 5. Alertas (Slack)

| Alerta | Origem | Canal | Bull |
|---|---|---|---|
| Técnicos de discagem: parado, mudo, falha técnica, ligação curtíssima, recusa da operadora, falha de leitura | `monitor_discagem.py` | #control-desk | ✅ desde `ALERTAS.desde` |
| Relativos: queda de ritmo, volume baixo, telefone inválido, bot ocioso (baselines p05/p90) | `monitor_discagem.py` | #control-desk | ✅ desde `relativos_desde` (início + 21 dias) |
| Funil: nenhum acordo, nenhum CPC, queda de alô | `monitor_campanhas.py` | #control-desk | ✅ relativos. ⚠️ queda de alô exige ≥ 5.000 ligações (não avalia em volume pequeno) |
| Custo: 🌅 abertura, 🎚️ ajuste, 🟠 orçamento do dia atingido, 🔧 canais ≠ contratado | `app.py` (pacing por custo) | #control-desk `[NOME]` | ✅ desde `ORCAMENTO_CLIENTE.inicio` |
| Spin, mailing atrasado, rota (alerta/troca), fim de volta | `app.py` | #control-desk | — (só OPERADAS) |
| `[NOME] Mailing` (lote não entrou) | `heartbeat.py` 10:47 | #coral-desk | ✅ 🟠 não crítico |
| Frescor do acionamento (≥ 110 min), vão do microfone (≥ 90 min sem medida) | `app.py` | #control-desk | ✅ (global) |
| Credencial do BQ (🔴 vencida, ⏳ > 20h) | `bq-credencial.yml` 08:00/12:00 | #coral-desk | ✅ (global) |
| PTP sem confirmação | `confirmacao-ptp-alarme.yml` 08:40 | #coral-desk | — (só Principia; candidato a peça própria) |
| Post de telecom, faturamento V2 | PA | canal da Principia | — |

## 6. Regras transversais que valem para toda peça nova

- `set -o pipefail` + `2>&1` em todo `cmd | tee`; deploy sem URL derruba o passo.
- Fonte indisponível: publica o que tem e o run sai **vermelho**. Zero não prova sucesso.
- Agendamento novo no **cron-job.org** (`config/cron_jobs.json`), nunca no `schedule` do GitHub (entrega 25–50%, atrasa de 2h a 4h45).
- Anti-duplicata com reserva atômica (PK em `dia_ref`) para tudo que posta 1× por dia.
- Cliente sem dono = `desconhecido`, nunca o cliente maior. Corte por **data**, não por hora.
- `timeout-minutes` do job acima do poll + setup.
