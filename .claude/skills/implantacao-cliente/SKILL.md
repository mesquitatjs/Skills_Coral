---
name: implantacao-cliente
description: Implanta um CLIENTE NOVO de cobrança na stack da Coral, de ponta a ponta. Faz as perguntas necessárias para entender o cliente (identidade, remuneração, discador, telecom, mailing, dados, mensageria, painéis, alertas), registra tudo numa ficha, monta o pacote de implantação e cria todos os controles, automações, painéis e alertas nos repositórios (principia-acionamento, coral-bot, coralai-mailing), com verificação de cobertura antes de publicar e checagens agendadas depois do go-live. Use quando um contrato novo for fechado ou alguém disser "vamos começar a operar o cliente X", "implantar cliente", "incluir cliente novo nos painéis/alertas/controles". Foi construída a partir da implantação da Bull (set–out/2026), que é o exemplo de referência.
---

# Implantação de cliente novo

Leva um cliente de "contrato fechado" a "operando com controle". Ao final da skill, o cliente tem:

- **Dados com dono:** CDR, acionamento e mailing atribuídos a ele, sem vazar para outro cliente.
- **Mailing:** capturado e cobrado todo dia.
- **Telecom sob orçamento**, com pacing por custo quando houver orçamento.
- **QA de acordos** cobrindo as campanhas dele.
- **Painéis:**
  - Operacional próprio, em versão externa (vai ao cliente) e interna (custos e margem);
  - seção no Telecom, no TMA, no QA, na Home e no Coral Desk.
- **Alertas em fases:** técnicos desde o início; relativos depois da medição.
- **Documentação** e checagens pós-go-live agendadas.

**Referências** (leia na Fase 0):

| Arquivo | Para quê |
|---|---|
| `references/questionario.md` | todas as perguntas, classe (bloqueante/importante/opcional), default e onde cada resposta é usada |
| `references/pontos-de-cadastro.md` | os ~47 lugares onde o cliente precisa estar escrito, com o exemplo da Bull e o que acontece se faltar |
| `references/inventario.md` | cardápio de controles, automações, alertas e painéis das duas operações, e o que um cliente novo ganha |
| `references/licoes.md` | 20 lições da implantação da Bull. Ler antes de implementar |
| `templates/ficha_cliente.yaml` | a ficha do cliente (exemplo: a Bull preenchida) |
| `scripts/verificar_cobertura.py` | confere os pontos de cadastro nos repositórios e a consistência do orçamento. **Gate antes de publicar** |

---

## Regras que não se quebram

1. **Nunca inventar valor.** Campo desconhecido fica `null` na ficha e vira pendência. Pendência bloqueante trava só o módulo dela, não a implantação inteira.
2. **Credencial nunca em código nem pela conversa.** Sempre `gh secret set NOME < arquivo`, feito pelo usuário. O agente não renova o ADC do BigQuery.
3. **Mockup antes de qualquer mudança visual.** Painel, card, aba, cor: renderize e mande o print **antes** de implementar, e espere "aprovado".
4. **Publicar só com "pode publicar".** Cada PR é mergeado e publicado depois do ok explícito. Depois do deploy, confira no ar e mande print.
5. **Branch nova por tarefa**, a partir do `main` atualizado de cada repositório. Uma PR por repositório e por onda.
6. **Separação entre clientes.**
   - Todo leitor corta por cliente.
   - O cliente novo fica fora dos gates e das peças da Principia (plano, faturamento, post de telecom).
   - Cliente sem dono vira `desconhecido`, nunca o cliente maior.
7. **Versão de cliente nunca recebe custo, comissão ou margem.** A trava é no gerador (sai com código 2) e no workflow (confere no ar).
8. **Sem PII** em painel público, sonda, artifact ou conversa: só contagens.
9. **Falhar vermelho.** Toda peça nova tem `pipefail`/`2>&1` em `| tee`. Fonte indisponível sai com código ≠ 0. Pendente nunca vira zero.
10. **Cliente começa OBSERVADO.** O Control Desk não atua no discador dele (pausa, spin, rota) sem régua acordada e histórico. Pacing por custo é a exceção, com kill switch `PACING_CUSTO_OFF`.
11. **Português do Brasil**, tom direto. Em material para o cliente, nada de identificador técnico (tabela, UUID, BQ).

---

## Fase 0 — Contexto (antes de perguntar qualquer coisa)

1. **Repositórios.** Garanta os repositórios na sessão (`add_repo` se faltar): `mesquitatjs/principia-acionamento`, `mesquitatjs/coral-bot`, `coral-engineering/coralai-mailing`, `mesquitatjs/projetos_coral`.
2. **Instruções.** Leia o `CLAUDE.md` de cada um.
3. **Dossiê.** Procure o dossiê do cliente em `projetos_coral/<chave>/` (proposta, precificação da `ucc-precificacao`, atas, fluxo de voz, homologação) e o canal do cliente no Slack. **Tudo o que já estiver escrito não se pergunta: confirma-se.**
4. **Estado de partida.** Rode o verificador com uma ficha mínima (chave, nome, cpn) para ver o que já existe:
   ```bash
   python3 .claude/skills/implantacao-cliente/scripts/verificar_cobertura.py \
           --ficha projetos_coral/<chave>/FICHA_IMPLANTACAO.yaml --raiz /home/user
   ```

## Fase 1 — Descoberta (questionário → ficha)

1. **Perguntar.** Siga `references/questionario.md` pelos blocos A–I, em rodadas de até 4 perguntas com `AskUserQuestion` quando houver opções. Não pergunte o que o dossiê já responde.
2. **Medir o que der.** Algumas respostas o agente obtém com sonda (via `q-runner.yml`, só contagens), em vez de perguntar:
   - `portfolio_id` no BQ (`intermediate.dim_portfolio`);
   - desfechos de acordo (`qa-acordos-descobrir.yml` com o cpn);
   - rótulo exato da campanha no OCS;
   - layout real do lote de mailing (lido do disco, nunca colado na conversa).
3. **Gravar a ficha** em `projetos_coral/<chave>/FICHA_IMPLANTACAO.yaml`, no formato do template.
4. **Pedir aprovação.** Mostre a ficha em tabela, separando o que veio de documento, de resposta e de medição, e as pendências com o módulo que cada uma trava. **Espere a aprovação.**

## Fase 2 — Pacote de implantação (plano)

Monte o pacote a partir da ficha e do `references/inventario.md`. Cada módulo entra ou sai por uma regra da ficha:

| Módulo | Entra quando | Principais pontos (ver pontos-de-cadastro) |
|---|---|---|
| **M1 · Fundação de dados** | sempre, e **antes da 1ª ligação de teste** | #1–3, #6, #7 (rodar `criar_views_custo.py`) · #17–21 · #25–26 · #32–34 |
| **M2 · Mailing** | `mailing.entrega` conhecido | #36–43, #47 (loader próprio se o layout diferir) |
| **M3 · Telecom e orçamento** | sempre (custo); orçamento se `orcamento_mensal` | #4–5 (techprefix), #8, #22, #35 (3 cópias), capacidade |
| **M4 · Pacing por custo** | `orcamento_mensal` e o usuário aceita atuação no discador | #22 + revisão de `THR_CANAL_H`/`K_TENT_PADRAO` para o TMA do cliente; kill switch |
| **M5 · QA de acordos** | `desfechos_acordo` conhecidos | #14, #23, #24 |
| **M6 · Tema e Home** | sempre | #9, #11–13 |
| **M7 · Painéis existentes** | sempre | Telecom (#2, #5), TMA (#10), QA (#14), Coral Desk (#44–46) |
| **M8 · Operacional próprio** (externo + interno) | `paineis.operacional_proprio` | #15. Copie o gerador da Bull trocando as constantes, ou, se já houver 2 cópias, proponha generalizar para `gerar_operacional_cliente.py --cliente <chave>` |
| **M9 · Alertas** | sempre | #19 (fases), #20, #42; canal #control-desk com `[NOME]` |
| **M10 · Documentação e checagens** | sempre | ver Fase 6 |

Apresente o pacote assim:

1. Módulos que entram e que ficam de fora, com o porquê.
2. O que muda em cada repositório.
3. Os mockups que serão enviados (M6, M7, M8).
4. **Custo de GitHub Actions** estimado: min/run × runs/dia × 30, com sugestão de onde cortar se apertar a cota.
5. A **ordem das ondas**.
6. As pendências.

**Espere a aprovação** antes de escrever código.

## Fase 3 — Implementação em ondas

Ordem recomendada: **M1 → M2 → M3/M4 → M5 → M6/M7/M8 (com mockup) → M9**. M1 vai primeiro sempre: dado sem dono vaza para outro cliente. Isso já aconteceu com a Bull, cujo custo foi faturado à Principia.

Em cada onda, para cada repositório tocado:

1. **Branch.** `git checkout main && git pull`, depois uma branch nova (`feat/<chave>-<modulo>`).
2. **Editar.** Faça as entradas usando a Bull como modelo: procure `bull`/`BULL`/`1824` no repositório e replique o padrão. Nos pontos ✋ (escritos à mão), edite o `CASE`/`if`.
3. **Validar local.**
   - Rode os testes e asserts do arquivo (ex.: `python3 scripts/pacing_custo.py`).
   - Renderize os painéis com dados sintéticos: o caminho feliz **e** o de fonte indisponível.
   - Em consulta nova ao BQ, valide no `q-runner` contra o dado real (só contagens).
4. **Revisar o diff com olhar adversarial:** o que faria o CI ou a operação quebrar? O que faria a Principia mudar sem querer?
5. **Verificar a cobertura.** Rode `verificar_cobertura.py`: os pontos da onda têm de estar ✅.
6. **Commitar e publicar.** Commit, push e mensagem ao usuário com o resumo e os prints. **Só abra PR e mergeie com "pode publicar".**
7. **Conferir no ar.** Depois do merge, confira o deploy (run verde, URL respondendo, 401 onde há senha, ausência de custo na versão externa) e mande o print.

Cuidados que costumam ser esquecidos:
- **Depois do M1**, rode `python scripts/criar_views_custo.py`: a view do MotherDuck é gravada e não se atualiza sozinha.
- **Orçamento:** as três cópias com os mesmos `mensal` e `inicio`. O verificador confere.
- **Datas:** `ALERTAS.desde` = início da operação; `relativos_desde` = início + 21 dias.
- **Agendamento novo** vai no cron-job.org ou em `workflow_run` atrás da captura, nunca em `schedule` do GitHub.

## Fase 4 — Verificação final (gate)

1. `verificar_cobertura.py` **sai 0**: todos os pontos aplicáveis ✅ e as 3 cópias do orçamento iguais à ficha.
2. **Ligações de teste do cliente:**
   - o CDR caiu no cliente certo (não em `desconhecido`, não na Principia);
   - o acionamento aparece com o cliente certo;
   - o lote de teste entrou em `mailing.registros` com o credor certo.
3. **Painéis:**
   - cada um abre;
   - antes do início, a Home e os painéis mostram "operação começa em …", sem 🔴;
   - a versão externa não tem custo.
4. **Homologação do fluxo de voz:** a trilha de SPT das ligações de teste bate com o board. Divergência vira chamado ao fornecedor antes do go-live.

## Fase 5 — Go-live e medição

**No dia do início**, confira:
- a abertura do pacing (🌅 no Slack);
- os canais = contratado;
- o 1º lote de mailing cobrado;
- os alertas técnicos com `[NOME]`.

**Agende checagens** com `send_later`, cada uma com o que conferir escrito na mensagem:

| Quando | O que conferir |
|---|---|
| D+1 | CDR do dia 1 no cliente, Operacional com dado real, mensageria do BQ no formato esperado |
| D+3 | calibração do custo por tentativa (`k_fonte` = CDR), razão de abertura × `THR_CANAL_H` |
| D+7 | 1ª semana: alertas técnicos sem ruído, orçamento × gasto, rodízio da TV |
| `relativos_desde` | os alertas relativos ligam; revisar limiares que não avaliam no volume do cliente (ex.: queda de alô ≥ 5.000 ligações) |
| fim do 1º mês | fechamento × orçamento; constantes globais herdadas (`THR_CANAL_H`, `K_TENT_PADRAO`); se o cliente sai de OBSERVADAS (só com régua e histórico) |

## Fase 6 — Documentação

- **Dossiê do cliente:** `projetos_coral/<chave>/` com a ficha, o pacote aprovado, os PRs, as URLs e as pendências.
- **`projetos_coral/infra/PAINEIS_MULTI_CLIENTE.md`:** uma seção para o cliente.
- **`projetos_coral/CLAUDE.md`:** a linha do índice.
- **`CLAUDE.md` de cada repositório tocado:**
  - tabela de painéis e de workflows;
  - no coral-bot, a tabela "Campanhas Monitoradas" (estava desatualizada para a Bull).
- **Melhorar a skill:**
  - ponto de cadastro novo descoberto na implantação → linha em `references/pontos-de-cadastro.md` **e** em `PONTOS` do `verificar_cobertura.py`;
  - lição nova → `references/licoes.md`.
