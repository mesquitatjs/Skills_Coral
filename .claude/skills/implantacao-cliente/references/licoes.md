# Lições da implantação da Bull (set–out/2026)

Cada lição saiu de um erro real ou de uma decisão do usuário. Leia antes de implementar.

## Dados e custo

1. **Cliente novo vaza para o maior sem avisar.** Até 23/09 o custo da Bull era faturado para a Principia (R$ 9,90 em setembro), porque nenhum consumidor do CDR filtrava por cliente. Cadastrar o cpnId (`CLIENTE_POR_CPN`) é o **primeiro** passo, antes da 1ª ligação de teste. Rodar `criar_views_custo.py` em seguida.
2. **Custo real × contratual.** Sem reembolso de telecom, o orçamento e o pacing usam o `custo_real` do carrier. Billing e post para o cliente da Principia seguem no contratual. Pergunte sempre (questionário B4).
3. **Teste antes do início não consome orçamento.** O painel comparava R$ 15 de teste com orçamento zero e acusava 🔴. O pacing descontava os testes do alvo do mês. A regra vale nas duas pontas: o gasto do mês conta a partir de `max(1º do mês, inicio)`.
4. **Pendente nunca é zero.** Dia em que a fonte não chegou aparece "pendente". A margem só conta os dias fechados. BQ fora do ar não pode virar "receita 0 · prejuízo".
5. **Constantes globais herdadas.** `THR_CANAL_H = 150` foi calibrado para a Bull (TMA de ~2 min); `K_TENT_PADRAO = 0.02`. Um cliente com TMA muito diferente precisa revisar, ou o pacing abre errado nos 3 primeiros dias, até o `k` calibrar.
6. **Três cópias do orçamento** (meta_telecom · pacing_custo · custo_telecom). Mudou num, muda nos três. O verificador confere.
7. **Moeda do `cost_amount` do WhatsApp no BQ parece USD** (0,0078/msg). Por isso o custo de WA usa a tabela da Meta, não o campo. E-mail ainda não aparecia no BQ em out/26.

## Robustez (falhas silenciosas)

8. **Quebrar reportando sucesso** é a patologia recorrente (8 incidentes: `incidentes/FALHAS_SILENCIOSAS_28-29jul2026.md`).
   - `cmd | tee` sem `pipefail`.
   - Detector que lê "zero" quando não conseguiu ler.
   - `exit 0` quando o webhook falta.
   - Toda peça nova tem de falhar **vermelho** quando a fonte falha.
9. **Credencial do BQ (ADC de usuário) dura cerca de 23h40.** Quando vence, derruba 16 workflows. Peça nova que lê o BQ herda essa fragilidade. Ela precisa publicar degradada e sair vermelha, nunca verde com dado vazio.
10. **O schedule do GitHub não é confiável.** Rotina nova vai no cron-job.org ou em `workflow_run` atrás da captura.
11. **A cota do GitHub Actions é apertada** (~3.000 min/mês na conta pessoal). Cada workflow novo custa minutos, faturados por job com piso de 1 min. Estime o custo antes, diga ao usuário e proponha onde cortar.

## Separação entre clientes

12. **Um leitor que não corta por cliente quebra o outro.** O guardrail de volume do mailing bloquearia o plano da Principia num dia sem lote da Bull. Todo leitor corta por credor ou cliente, e os passos do cliente novo rodam com `!cancelled()`, fora do gate da Principia.
13. **Um painel por cliente.** O Operacional da Bull é separado do da Principia, em duas versões:
    - **externa** (vai ao cliente): sem custo, comissão nem margem. O gerador **sai 2** se uma chave interna vazar, e o workflow confere de novo no ar;
    - **interna**: atrás da `HOME_SENHA`, em projeto Vercel de nome não óbvio.
14. **Painel público sem PII.** O QA é público: sem CPF, nome, `case_id` nem transcrição. Sondas e artefatos levam só contagens.
15. **Cliente começa OBSERVADO.** O Control Desk só atua no discador do cliente quando houver régua acordada **e** histórico. A exceção acordada é o pacing por custo, com kill switch.
16. **Alertas em duas fases.** Técnicos a partir do início; relativos depois de 21 dias de medição, que é a janela dos baselines. Sem isso, o 1º dia vira ruído.
17. **`queda de alô` exige ≥ 5.000 ligações.** Com volume pequeno, esse alerta nunca dispara. Revisar o limiar depois da medição.

## Processo

18. **O board do fluxo é a fonte de verdade.** Os geradores de de-para e templates "driftam". Reconcilie contra o board, não contra o arquivo anterior.
19. **A homologação revela o que o board não tem.** Na Bull, 93 ligações de teste deram 43 OK e 50 divergentes: um SPT nunca enviado e SPTs fora do board. Extraia a trilha das ligações de teste antes do go-live.
20. **Escrito à mão é onde se esquece.** Há 6 pontos que são `CASE`/`if` com o nome do cliente: `sql_cliente_campanha`, `ingest_cdr` (aviso), `gerar_home._SQL`, `_FUNIL_SQL`, loader do mailing e passos do workflow. O verificador cobre todos.
