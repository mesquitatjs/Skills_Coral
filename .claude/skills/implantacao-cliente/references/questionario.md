# Questionário de implantação

Cada pergunta preenche um campo da ficha (`templates/ficha_cliente.yaml`) e diz onde a resposta é usada.

**Como perguntar:**
- Em rodadas de até 4 perguntas, com `AskUserQuestion` quando houver opções claras e em texto livre quando for número ou nome.
- Antes de perguntar, procure a resposta no dossiê do cliente (`projetos_coral/<chave>/`), no canal do cliente e na precificação. Pergunte só o que não estiver escrito.
- Para resposta que já existe num documento, mostre o valor e peça confirmação. Não pergunte de novo como se fosse novidade.

**Classes:**
- **B, bloqueante:** sem a resposta, o módulo correspondente não é implantado. Vira pendência na ficha.
- **I, importante:** use o default indicado, escreva a premissa na ficha e avise.
- **O, opcional.**

---

## A. Identidade e calendário

| # | Pergunta | Campo | Classe | Por que importa |
|---|---|---|---|---|
| A1 | Nome do cliente como deve aparecer nos painéis e no Slack? | `cliente.nome` | B | rótulo `[Nome]`, abas, cards |
| A2 | Chave curta (minúsculas, sem acento)? Sugira a partir do nome | `cliente.chave` / `CHAVE` | B | chave em ~45 pontos de cadastro e no `ILIKE '%CHAVE%'`: precisa ser **única no rótulo** das campanhas |
| A3 | Data do 1º dia de discagem real? | `cliente.inicio_operacao` | B | alertas técnicos, orçamento proporcional, Home neutra, pacing |
| A4 | Data do 1º lote de mailing que deve ser cobrado? | `cliente.inicio_mailing` | I (= início − 3 dias úteis) | status `completo_<chave>` e heartbeat |
| A5 | Descrição curta do produto (ex.: "consignado CLT") | `cliente.produto` | O | aba do Coral Desk |
| A6 | Cor do cliente? Proponha uma que não colida com Ouro, Bronze, PPay, FIDC, semáforo ou o coral, e mostre no mockup | `cliente.cor` | I | todos os painéis |
| A7 | Quem são os contatos no cliente, na Coral e no fornecedor? | `cliente.contatos` | I | dossiê, escalonamento |
| A8 | A operação roda em ponto facultativo e feriado estadual ou municipal? | `discador.opera_facultativo` | I (sim: só feriado **nacional** para) | calendário do orçamento, pacing e alertas |

## B. Comercial e receita

| # | Pergunta | Campo | Classe | Por que importa |
|---|---|---|---|---|
| B1 | Modelo de remuneração: fixo, success fee, híbrido MAX(mínimo; fee) ou 100% variável? | `comercial.modelo` | B | define se há aba de margem e o que é "receita" |
| B2 | Tabela de comissão por faixa de atraso, e qual coluna se aplica (com ou sem transbordo)? | `comercial.comissao` | B se houver fee | receita na aba Custos e margem |
| B3 | Mínimo mensal (se houver)? | `comercial.minimo_mensal` | I | margem e piso |
| B4 | O telecom é reembolsado pelo cliente? | `comercial.reembolso_telecom` | B | ⛔ define **custo real × contratual** em orçamento, pacing e painel |
| B5 | A precificação já passou pela skill `ucc-precificacao`? Onde está o documento? | `comercial.precificacao_doc` | I | número de bots e canais, custo esperado |

## C. Discador e voz

| # | Pergunta | Campo | Classe | Por que importa |
|---|---|---|---|---|
| C1 | cpnId e rótulo **exato** de cada campanha no OCS | `discador.campanhas[]` | B | ✔ cadastro em ~20 pontos; o rótulo vira regex do mailing e `ILIKE` |
| C2 | Quantos bots e quantos canais contratados? | `discador.bots` / `canais` | B se houver pacing | teto da razão, alerta de capacidade, custo do bot |
| C3 | O Control Desk deve **atuar** no discador (pausa, spin, troca de rota) ou só observar no início? | `discador.operada` | B | ⛔ default **observada**. Só sai com régua acordada **e** histórico |
| C4 | Há régua de spin (tentativas por CPF por dia) contratada? | `discador.regua_spin` | I (null) | sem régua não há pacing de spin; com orçamento, há pacing por custo |
| C5 | Quais desfechos (Última Interação) marcam acordo? Algum exclusivo do cliente? | `desfechos_acordo(_extra)` | B para o QA | rodar `qa-acordos-descobrir.yml` com o cpn e confirmar com o usuário |
| C6 | Janela de discagem (seg–sex, sábado, domingo)? | `discador.janela` | I (08:00–20:40 · sáb 08:00–14:20) | fechamento, StopLote, alertas |
| C7 | Fluxo de voz e SPT aprovados? Onde está o board/de-para? | — (dossiê) | I | homologação; o QA lê os SPT |

## D. Telecom

| # | Pergunta | Campo | Classe | Por que importa |
|---|---|---|---|---|
| D1 | Qual carrier/rota? Techprefix próprio? Desde quando? | `telecom.techprefix(_desde)` | I | checagem cruzada no ingest; `SEM_REAL` na Qualidade |
| D2 | Na mesma conta Vonex já capturada (100777/100778) ou em conta nova? | `telecom.conta_carrier` | B | conta nova = credencial nova (secret por arquivo) + passo na captura |
| D3 | Orçamento mensal de telecom? Proporcional no mês de início? | `telecom.orcamento_mensal` | I (null = sem pacing por custo) | ⚠️ **três cópias** (meta_telecom · pacing_custo · custo_telecom) |
| D4 | Base de custo: real (carrier) ou contratual (R$ 0,053/min)? | `telecom.custo_base` | B (segue de B4) | painel, pacing e orçamento |

## E. Mailing

| # | Pergunta | Campo | Classe | Por que importa |
|---|---|---|---|---|
| E1 | Como o arquivo chega: lote no portal OCS, e-mail, SFTP ou API? | `mailing.entrega` | B | o OCS já tem coletor; o resto é coletor novo |
| E2 | Nome padrão do lote (termo obrigatório) e frequência? | `nome_lote_contem`, `frequencia` | B | `NOME_ESPERADO`, status, heartbeat |
| E3 | Layout: colunas, separador, decimal, cabeçalho repetido? Peça um arquivo real (sem expor CPF na conversa: o agente lê do disco) | `mailing.colunas`, `separador`, `decimal` | B | loader próprio (`load_mailing_<chave>`) |
| E4 | O cliente tem segmentos? Quais, e em que ordem? | `mailing.segmentos` | I | Base do dia (`_SEGMENTOS_<CHAVE>`, `BASE_SEG`) |
| E5 | O cliente entra no **planejador** (plano do dia com meta)? | `mailing.tem_plano` | I (não) | ⛔ só com régua e meta contratadas. Senão o cliente fica fora do gate da Principia |

## F. Dados (BigQuery) e pagamentos

| # | Pergunta | Campo | Classe | Por que importa |
|---|---|---|---|---|
| F1 | `portfolio_id` do cliente no BQ (e sub-portfólios)? | `dados.bq_portfolio_id` | B para o Operacional | o agente confere com sonda em `intermediate.dim_portfolio` pelo `q-runner` |
| F2 | Onde o pagamento é registrado (sistema do cliente)? O BQ recebe `fct_installments.paid_amount`? | `dados.sistema_cliente` | B para receita | receita = comissão sobre o **pago** |

## G. Mensageria e custos internos

| # | Pergunta | Campo | Classe | Por que importa |
|---|---|---|---|---|
| G1 | Quais canais além da voz (WhatsApp, SMS, e-mail) e com que cadência? | `mensageria` | I | linhas de custo da aba de margem |
| G2 | HSMs aprovados na Meta? Qual linha de WhatsApp? | `mensageria.whatsapp` | I | sem linha não há WhatsApp |
| G3 | Preço da licença do bot por mês? | `custos_internos.bot_preco_mes` | I (pendente) | linha "Licença do bot". Sem preço fica **pendente**, nunca zero |
| G4 | Preços unitários de WhatsApp, SMS e e-mail (se diferentes do padrão) | `custos_internos.preco_*` | O (0,15/0,55 · 0,06 · 0,04) | aba de margem |

## H. Painéis e visibilidade

| # | Pergunta | Campo | Classe | Por que importa |
|---|---|---|---|---|
| H1 | O cliente terá Operacional **próprio** (separado)? | `paineis.operacional_proprio` | I (sim) | ⛔ padrão: um painel por cliente, nunca misturar com a Principia |
| H2 | Haverá versão para enviar ao cliente? | `paineis.versao_cliente` | I (sim) | versão do cliente **sem** custo, comissão nem margem (o gerador sai 2 se vazar) |
| H3 | Nomes dos projetos Vercel (cliente legível; interno com nome **não óbvio**) | `paineis.projeto_vercel_*` | I | o interno fica atrás da `HOME_SENHA` |
| H4 | Tempo do cliente no rodízio da TV do Coral Desk | `paineis.rodizio_tv_ms` | O (60000) | `RODIZIO_MS` |

## I. Alertas

| # | Pergunta | Campo | Classe | Por que importa |
|---|---|---|---|---|
| I1 | Os alertas técnicos começam no início da operação? | `alertas.tecnicos_desde` | I (= início) | `campanhas.ALERTAS.desde` |
| I2 | Período de medição antes dos alertas **relativos**? | `alertas.relativos_desde` | I (início + 21 dias) | baselines precisam de 21 dias. Antes disso o alerta relativo é ruído |
| I3 | Canal dos alertas? | `alertas.canal` | I (#control-desk com `[Nome]`) | um canal único com rótulo, não um canal por cliente |
| I4 | Alerta de lote do mailing não entregue a partir de quando? | `alertas.mailing_desde` | I (= início) | heartbeat 🟠 não crítico |

---

**Fechamento do questionário:**
1. Mostre a ficha preenchida em tabela, separando o que veio de documento do que veio de resposta.
2. Liste as **pendências**, com o módulo que cada uma trava.
3. Peça **aprovação da ficha** antes da Fase 2.
