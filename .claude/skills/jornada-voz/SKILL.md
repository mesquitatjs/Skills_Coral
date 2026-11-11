---
name: jornada-voz
description: Cria a jornada de voz da Córa para um cliente ou produto NOVO no modelo construído para a Vale Consignado (out–nov/2026), de ponta a ponta: leitura das fontes, desenho no FigJam (3 seções, um cenário por caixa, variáveis em [colchetes] e negrito), regras de fala e de negociação (ofertas fixas, WhatsApp como transbordo, crise), artefato de dúvidas ligado às caixas, demo navegável com link para o prospect (gerador de mapa → prompts no formato da Sinergy → personas → testes sem e com o modelo), geração do .ivr no padrão da Sinergy e homologação do nosso lado antes do chamado. Use quando alguém disser "montar a jornada de voz do cliente X", "desenhar o fluxo da Córa", "levar o fluxo para a demo", "gerar a IVR para a Sinergy" ou "replicar o modelo da Vale".
---

# Jornada de voz da Córa (modelo Vale)

Leva um cliente de "temos a régua e as regras do produto" a "fluxo aprovado pelo cliente, demo no ar e .ivr pronto
para o chamado da Sinergy". A Vale Consignado é o exemplo de referência: tudo o que está aqui foi feito lá uma vez e
conferido com o cliente.

**Ao final, o cliente tem:**

| Entregável | Onde vive | Para quem |
|---|---|---|
| Board no FigJam com as jornadas por situação e as falas da Córa | arquivo do cliente no Figma (modelo: `5YdMILtAH2E1ofoy8ECWX5`, a Vale) | cliente e equipe |
| Artefato de dúvidas, cada dúvida com link para a caixa do board que ela trava | `projetos_coral/<chave>/jornada/duvidas_<chave>.html` + artifact publicado | cliente |
| Mapa do fluxo em JSON (**fonte única** de prompts, nós e desfechos) | `coral-bot/demo_voz/ref/gerar_mapa_<chave>.py` → `mapa_<chave>.json` | demo, IVR e testes |
| Demo de voz navegável, com link de prospect | `coral-bot/demo_voz/` na branch `claude/demo-voz` (Render, deploy manual) | prospect e equipe |
| `.ivr` no padrão da Sinergy, homologado do nosso lado | gerado por `coral-bot/scripts/homologacao/ivr_<chave>.py`, **o arquivo nunca entra no repo** | Sinergy (via chamado) |
| Registro no dossiê | `projetos_coral/<chave>/<CHAVE>_PROJETO.md` | memória |

**Referências** (leia na Fase 0):

| Arquivo | Para quê |
|---|---|
| `references/board-figjam.md` | as 3 seções, os cartões, os códigos, as cores, a tabela "O cliente diz / A Córa responde / Depois", o que nunca entra no board |
| `references/regras-de-fala.md` | as regras de fala e de negociação que valem para toda jornada (as que vieram do cliente e as que vieram do teste com o modelo) |
| `references/demo.md` | como o fluxo vira demo: gerador, mapa, personas, prompts no formato da Sinergy, testes, deploy, teste pelo link |
| `references/ivr-sinergy.md` | como gerar o `.ivr`, o que se homologa aqui e o que fica com a Sinergy (ids, campanha, registro do acordo), chamado e plano de testes |
| `references/licoes.md` | o que deu errado na Vale e como se corrigiu. Ler antes de desenhar |
| `templates/prompt_base.md` | FORMATO, COMUM e DATAS do prompt, extraídos do gerador da Vale |
| `templates/duvidas_cliente.md` | esqueleto do artefato de dúvidas |

---

## Regras que não se quebram

1. **Só voz no board.** WhatsApp, SMS e e-mail são outra jornada e outro material. A ligação termina em acordo, em
   WhatsApp ou em despedida; nunca em "transferir".
2. **Não há humano.** Toda ligação é do voicebot. Transbordo é para o **WhatsApp**. Nunca escrever "atendente",
   "operador" ou "transferência para humano" em fala, caixa, prompt ou doc.
3. **Um cenário por caixa, em toda etapa.** À vista e parcelado, sim e não, demitido e ativo: caixas separadas. Caixa com
   dois cenários é onde o cliente para de entender e a Sinergy constrói errado.
4. **Variável sempre em `[colchetes]` e em negrito**, com um nome só por conceito. Datas são só `[data_curta]` e
   `[data_longa]`. Nunca `(data)`, `{data}`, `[data_max]` e `[data_longa]` para a mesma coisa.
5. **Ofertas fixas.** A Córa oferece o que está no mailing: valores das ofertas e as duas datas. Não negocia data
   livre, não monta parcela com valor que o cliente disse, não pergunta o dia do salário. Valor do cliente abaixo da
   oferta vira a oferta mais próxima, e a conversa continua (não encerra).
6. **Material para o cliente sem termo interno.** Nada de nome de nó, SPT, `node_saida`, Sinergy, OCS, tabela, custo,
   margem ou posição de negociação. No board as etapas têm nome de gente ("Confirmar quem atendeu"), não de sistema.
7. **O gerador é a fonte única.** Prompt, nó e desfecho se editam em `gerar_mapa_<chave>.py`; o JSON é saída, a IVR é
   saída, a demo lê o JSON. Editar o JSON à mão é como editar o board e esquecer o doc: a divergência aparece na
   homologação (foi assim na Bull, 4 nós com número diferente entre board e doc).
8. **O `.ivr` nunca entra no repositório** (`*.ivr` no `.gitignore` do `coral-bot`). Molde e saída ficam no scratchpad
   da sessão; o arquivo vai ao usuário por `SendUserFile`.
9. **Branch nova por tarefa** em cada repo, merge na `claude/demo-voz` só "se passar" o teste com o modelo e com o ok
   do usuário; deploy no Render é manual e do usuário. **Nunca o `main` do `coral-bot` para a demo.**
10. **Nada se posta no Slack** por esta skill. Resposta ao cliente é rascunho entregue ao usuário.
11. **Credencial nunca em código nem na conversa.** O `.ivr` gerado não pode carregar senha, usuário, `Data Source`
    nem chave de API do molde (o gerador trava se encontrar).
12. **Português do Brasil, tom direto, sem vício de IA** (`projetos_coral/estilo/GUIA_DE_ESCRITA.md`).

---

## Fase 0 — Contexto

1. **Repositórios na sessão** (`add_repo` se faltar): `mesquitatjs/projetos_coral` (dossiê e material),
   `mesquitatjs/coral-bot` (demo e gerador de IVR). Leia o `CLAUDE.md` dos dois.
2. **Fontes do cliente, nesta ordem:** dossiê em `projetos_coral/<chave>/`, canal do cliente no Slack (ler antes de
   responder qualquer coisa), data request, regras do produto (na Vale: manual do Crédito do Trabalhador,
   `projetos_coral/bull/CREDITO_DO_TRABALHADOR_Mecanica.md`), transcrições das reuniões no Fireflies, régua atual do
   cliente. **O que já está escrito não se pergunta, confirma-se.**
3. **Modelo de referência:** board da Vale (`figma.com/board/5YdMILtAH2E1ofoy8ECWX5`), `coral-bot/demo_voz/ref/gerar_mapa_vale.py`,
   `coral-bot/scripts/homologacao/ivr_vale.py`, `projetos_coral/vale-consignado/VALE_PROJETO.md` §6D e
   `projetos_coral/vale-consignado/jornada/`.
4. **O que trava o desenho** (perguntar antes de desenhar, se o dossiê não responder):
   - as **situações** do cliente que mudam a conversa (na Vale: demitido, ativo com diferença, revinculado, afastado);
   - o que a Córa **pode oferecer** em cada situação (à vista, entrada + parcelas, só a diferença) e de onde vem cada número;
   - as **datas** que valem (regra da data curta e da longa) e a data máxima;
   - o que a Córa **não pode dizer** (negativação, FGTS, RH, promessas que dependem de terceiro);
   - os **campos do mailing** disponíveis (nome, empregador, parcela, valores, datas, situação);
   - como o cliente **registra o acordo** (API, CobranSaaS, arquivo) e o que precisa voltar da ligação.

---

## Fase 1 — Pesquisa e jornada por situação (antes de qualquer fala)

1. Escreva `projetos_coral/<chave>/jornada/PESQUISA_<situacao>.md`: o que a pessoa nessa situação vive, o que a regra
   do produto diz, o que já pagou, o que pode pagar, o que a cobrança costuma errar (na Vale: demitido com rescisão
   abatida, FGTS usado, sem garantia).
2. Monte a **jornada por situação** (raias): o que acontece com o cliente, o que a Córa sabe pelo mailing, o que a
   Córa faz, o que fica para o cliente conferir. Uma raia por situação. É a seção 2 do board.
3. Passe cada jornada pela skill `cx-ux-cobranca-agent` (avaliação de CX) e registre em
   `projetos_coral/<chave>/jornada/AVALIACAO_CX_<situacao>.md`. Corrija antes de escrever as falas.

**Pronto quando:** cada situação tem pesquisa, raia e avaliação de CX, e as dúvidas que travam o desenho estão listadas.

## Fase 2 — Board no FigJam

Siga `references/board-figjam.md`. Resumo:

1. Crie o arquivo (ou duplique o da Vale) e abra sessão com `create_session`. Toda escrita no board é por `use_figma`.
2. **3 seções, nesta ordem:** `1 · Como ler e mapa` · `2 · Jornadas por situação` · `3 · Falas da Córa na ligação`.
3. Na seção 3, blocos por etapa com código (A identificar quem atendeu · B validar identidade e abrir · C/D/E
   negociação por situação · F encerramentos). Cada caixa tem **um** cenário e um código (`C04`).
4. Objeções em tabela "**O cliente diz / A Córa responde / Depois**", uma linha por objeção.
5. Ao fim de cada rodada de edição: varrer sobreposição de caixas, conferir que toda saída tem destino, que não há
   termo interno, que toda variável está em `[colchetes]` e negrito.
6. Revisão final antes de mandar ao cliente: leia o board como ele vai ler. Nomes de etapa em linguagem de gente, os
   códigos ficam. Libere o **Share** do arquivo antes de mandar o link (não é automático).

**Pronto quando:** a varredura passa e o usuário aprovou a leitura.

## Fase 3 — Regras de fala e de negociação

As regras de `references/regras-de-fala.md` entram no prompt COMUM e nos blocos de negociação. As que são do cliente
(ofertas, datas, o que não dizer) entram no board e no prompt ao mesmo tempo, nunca só num lugar.

**Pronto quando:** cada regra do cliente aparece no board e no gerador, e a lista de "o que a Córa nunca diz" está na
seção 1 do board.

## Fase 4 — Dúvidas para o cliente

1. Toda pergunta que o desenho levantou e o dossiê não responde vira dúvida numerada, com **o que muda na fala**
   conforme a resposta e link direto para a caixa do board (`?node-id=`).
2. Gere `projetos_coral/<chave>/jornada/duvidas_<chave>.html` a partir de `templates/duvidas_cliente.md` e publique
   como artifact (compartilhado por link). Dúvida respondida ganha a resposta e a data; nunca some.
3. Perguntas do cliente no canal entram como dúvidas novas no mesmo artefato.

**Pronto quando:** o artefato está publicado e o dossiê tem o link.

## Fase 5 — Demo

Siga `references/demo.md`. Resumo: `gerar_mapa_<chave>.py` escreve o mapa JSON; `motor.py` ganha o mailing fictício
e o `FLUXOS[<chave>]`; `personas.json` ganha uma persona por situação; `testes.py` ganha a rubrica do fluxo;
`teste_fluxo_<chave>.py` confere a fiação sem o modelo; `teste_<chave>_modelo.py` roda os cenários com o modelo e as
checagens de estilo (workflow `demo-voz-teste-<chave>.yml`); telas `index.html` e `vitrine.html` ganham os rótulos das
situações; merge na `claude/demo-voz` se passar; deploy manual; teste pelo link publicado (`teste_link_<chave>.py`,
no scratchpad) e avaliação de ligações gravadas (`/testes/<id>`).

**Pronto quando:** o teste com o modelo passa nas duas rodadas, o teste pelo link chega ao fim certo em todos os
cenários e o avaliador não marca falso positivo na situação do contrato.

## Fase 6 — IVR no padrão da Sinergy

Siga `references/ivr-sinergy.md`. Resumo: `ivr_<chave>.py` monta o grafo a partir do mapa JSON usando o `.ivr` da
Bull como molde (classes e formas), `teste_ivr_<chave>.py` confere formato, estrutura, conteúdo e conversa; o mapa
extraído do `.ivr` gerado entra na matriz do teste com o modelo; o arquivo vai ao usuário. `cpnId`, ids de interação
novos, resultados da campanha e o registro do acordo são da Sinergy e entram como marcadores `[SINERGY: ...]`.

**Pronto quando:** `teste_ivr_<chave>.py` imprime "tudo ok" e a matriz do teste com o modelo passa nos dois mapas.

## Fase 7 — Chamado e homologação com a Sinergy

1. Texto do chamado pelo molde `projetos_coral/bull/CHAMADO_SinergyTech_Jornada_Bull.md` (o que entregar, o que
   pedir, o que está marcado `[SINERGY: ...]`).
2. Plano de testes pelo molde `projetos_coral/bull/PLANO_TESTES_Homologacao_Voz.md`: casos por bloco, SPT esperado,
   o que reprova; **conferir numeração board × doc × bot antes da primeira ligação** (lição da Bull).
3. Depois do build, ouvir ligações tabuladas como abandono/silêncio (lição da Principia: o ASR rotulava atendimento
   real como "sem resposta").

## Fase 8 — Registro

- Dossiê do cliente: o que mudou, decisões, links (board, artefato, demo), o que fica pendente e com quem.
- Commit em branch nova nos repos tocados. PR só com pedido.
- Esta skill: se o cliente novo trouxe regra nova que vale para todos, ela entra em `references/regras-de-fala.md` e
  o aprendizado em `references/licoes.md`.

---

## Checklist do zero ao chamado

- [ ] dossiê, canal, data request e regras do produto lidos; dúvidas que travam o desenho listadas
- [ ] pesquisa + raia + avaliação de CX por situação
- [ ] board em 3 seções; um cenário por caixa; variáveis `[x]` em negrito; varredura de sobreposição e saídas
- [ ] seção 1 com "o que a Córa nunca diz" e o mapa
- [ ] artefato de dúvidas publicado, cada dúvida ligada à caixa
- [ ] gerador de mapa → JSON; personas; rubrica; teste sem modelo; teste com modelo (2 rodadas) verde
- [ ] telas da demo com as situações; merge na `claude/demo-voz`; deploy; teste pelo link em todos os cenários
- [ ] `ivr_<chave>.py` + `teste_ivr_<chave>.py` "tudo ok"; mapa extraído na matriz; `.ivr` entregue, fora do repo
- [ ] chamado e plano de testes prontos; numeração conferida
- [ ] dossiê atualizado, commit feito, Share do Figma liberado
