# Do board à demo

Tudo em `mesquitatjs/coral-bot`, pasta `demo_voz/`. Leia o `demo_voz/README.md` e
`projetos_coral/comercial/DEMO_VOZ_CORA.md` antes de mexer. A branch de deploy é **`claude/demo-voz`** (Render,
auto-deploy desligado, deploy manual do usuário). Nunca o `main`.

Ordem de trabalho (cada passo em branch nova a partir da `claude/demo-voz`):

## 1. O gerador de mapa (`ref/gerar_mapa_<chave>.py`), a fonte única

Molde: `ref/gerar_mapa_vale.py` (v2, 06/11/2026). Um script Python que escreve `ref/mapa_<chave>.json` com:

- `nome`, `descricao`, `voz_tts`, `raizes` (nó inicial), `apos_fim` (o nó que grava o resultado), `nos`.
- Nós no formato que o `motor.py`/`simulador.py` executam (os mesmos tipos do `.ivr`): `NodeOCSMultiGetExtraFields`
  (campos do mailing → `@variáveis`, dict `CAMPOS`), `NodeGPT` (um por etapa de conversa), `NodeSetVariableValue`,
  `NodeOCSInteraction` (tabulação), `NodeWebServiceRequestJson` (registro do acordo), `NodeFunction`,
  `NodeTTSAsyncBegin/End`, `NodeOCSMultiResult` (resultado final: OUTCOME, DESFECHO, TELEFONE).
- Helpers: `gpt(i, desc, prompt, saidas)` monta o nó GPT com `saidas = {"node1": id, ...}`; `fim(i, desfecho,
  interacao, prox)` grava desfecho + interação e encerra; `ptp(i, prox, desc)` registra a promessa na API simulada.
- Nós GPT da Vale: **10** quem atendeu · **20** identidade (abre por segmento) · **30** demitido · **31** ativo ·
  **32** revinculado · **33** afastado. Um nó de conversa por situação; as saídas (`SAIDAS_CONVERSA`, node1..node19)
  apontam para os desfechos 110–146. Cliente novo: mesma numeração de A (10, 20) e um nó 3x por situação.
- Os **prompts** são concatenação de blocos de texto: `COMUM + FORMATO + blocos da etapa`. O molde está em
  `templates/prompt_base.md`. Para a negociação, a função `conversa(situacao, goal, objecoes)` monta o prompt a
  partir do bloco do demitido (`P_NEGOCIA`) com `trecho()` recortando as partes comuns (HOJE, WHATS, CANAL, PENSAR,
  VULN, F_COMUM, CONDUTA) e injetando a situação, o goal e as objeções daquela situação. Regra que vale para todas
  as situações se escreve uma vez.
- **Formato de resposta** (contrato com o nó GPT da Sinergy), quatro linhas: `#resposta_ao_usuario`, `#node_saida`
  (`nodeN` ou `null` para continuar na mesma etapa), `#var_@cod_ocorrencia` (SPT, só o número) e
  `#interacoes_ocorridas` (contador da etapa). O nó aceita qualquer
  `#var_@<nome>` (a Bull devolve `@id_oferta`, `@data_proposta`); a Vale ainda não devolve `@data_escolhida` e
  `@oferta` porque o registro do acordo depende da integração.
- Todo exemplo de fala no prompt já vem com SPT e saída; objeção segue o padrão `* <o que o cliente diz> (SPT n):
  "<fala>"` + `#node_saida`. É o mesmo texto da tabela do board.
- SPTs usados na Vale (numeração herdada da Principia/Bull): 3 falecido · 4 silêncio · 6 identidade · 10 número
  errado · 12 fraude · 17 alega pagamento · 19 não validou · 20 quem atendeu · 26 à vista · 28 terceiro · 37
  confirmação · 51/53 opt-out · 54 vulnerabilidade · 56/57 sem condição · 58 ocupado · 61–63 datas · 72 pessoa · 74
  jurídico · 75/76 parcelado · 77 conhece · 93–109 situações e objeções da Vale · 98 crise. Novo SPT só com número
  livre e registro no controle (`projetos_coral/fluxos-voz/CONTROLE_SPT_3Carteiras.md`).

Rode `python demo_voz/ref/gerar_mapa_<chave>.py` e versione o JSON junto com o gerador. **Nunca edite o JSON.**

## 2. Motor, personas e telas

- `motor.py`: `FLUXOS["<chave>"]` (nome, marca, nota), carga do mapa (`DEMO_MAPA_<CHAVE>` para trocar o mapa, p.ex.
  o extraído do `.ivr`), `_mailing_<chave>(p, pid, hoje)` que monta os campos do mailing a partir da persona (datas
  calculadas: `DATA_CURTA = _util(hoje, 1)`, `DATA_LONGA = DATA_MAXIMA = _util(hoje, 3)`, `_dia_falado`), e
  `_resposta_crise` já cobre o filtro de conteúdo do provedor na fala de crise (devolve a fala fixa, SPT 98 e a saída
  de CRISE do prompt).
- `personas.json`: **uma persona por situação**, fictícia, com `fluxo: "<chave>"`, `segmento`, `resumo` e os campos
  que o mailing usa (valores, datas, empregador, garantia). Na Vale: marcos, juliana, renata, paulo (demitidos em
  variações), luciana (ativo com diferença), rodrigo (revinculado), sandra (afastada).
- `static/index.html` (equipe) e `static/vitrine.html` (prospect): dicionários `SEG`/`SIT`/`NOTA` com o rótulo e a
  explicação de cada situação. Texto de vitrine sem termo interno.
- `links.py`: o link de prospect carrega o `fluxo`; emitir pela tela `/links` da equipe.

## 3. Avaliador (`testes.py`)

- `CONTEXTO["<chave>"]` + `RUBRICA_COMUM` = rubrica do fluxo. A rubrica diz o que é certo **por situação** (ativo
  só cobra a diferença; revinculado e afastado negociam; domingo vira segunda; confirmação dupla é atrito).
- `_situacao_<chave>(d)` injeta no avaliador a **situação do contrato do cadastro** (segmento, parcela, rescisão
  abatida, garantia, resumo). Sem isso o avaliador marca violação onde a Córa seguiu a regra (lição da Vale).
- Ligações gravadas: `/testes/<id>`; agregação por caixa em `/melhorias`.

## 4. Testes

| Teste | O que confere | Quando roda |
|---|---|---|
| `teste_fluxo_<chave>.py` | a **fiação** sem modelo: chat trocado por respostas roteirizadas; persona cai no mapa certo; variáveis chegam ao prompt; acordo vai à API simulada; o fluxo anterior continua no mapa dele | local, a cada mudança |
| `teste_<chave>_modelo.py` | **com o modelo**: N cenários × 2 rodadas (Vale: 18), desfecho esperado por cenário, regras de negociação (data curta/longa, nunca domingo, oferta mais próxima), `PROIBIDO` (negativação, transferir, atendente...), checagens de estilo no fim (nome 2×, sem agradecimento inicial, despedida, ≤45 palavras na abertura, "nenhuma fala com dois Então") | workflow `demo-voz-teste-<chave>.yml`, `workflow_dispatch` e push na branch de teste; **matriz** `mapa: ["", "demo_voz/ref/mapa_<chave>_ivr.json"]` para a mesma conversa passar no mapa da demo e no extraído do `.ivr` |
| `teste_link_<chave>.py` (scratchpad) | liga pelo **link publicado** depois do deploy, cenário a cenário, e confere o fim | depois de cada deploy |
| `teste_ivr_<chave>.py` | ver `ivr-sinergy.md` | antes de entregar o `.ivr` |

Fallback no teste com modelo: quando o mapa é o da IVR, OUTCOME é o SPT numérico e o desfecho se lê de
`vars["@desfecho"]`.

O workflow usa `secrets.OPENAI_API_KEY_POOL`. Falha por `429 no credits remaining` é crédito, não defeito; avisar o
usuário e redisparar depois.

## 5. Merge, deploy e teste pelo link

1. Teste sem modelo verde local → push da branch → workflow com modelo verde nas 2 rodadas.
2. "Pode fazer o merge se passar": merge na `claude/demo-voz` (sem PR, salvo pedido).
3. Deploy no Render é do usuário. Esperar "fiz o deploy" e conferir que o commit subiu (o `/saude` ou a vitrine).
4. Ligar pelo link do prospect com `teste_link_<chave>.py`: todos os cenários têm de chegar ao fim certo (na última
   rodada da Vale, 10/10, crise inclusa).
5. Avaliar as ligações gravadas que o usuário apontar (`/testes/<id>`) e ajustar prompt **e** avaliador quando o
   erro for de leitura, não de fala.

## O que o teste com o modelo ensinou (regras que nasceram dele)

- "amanhã" é sempre a data curta (o modelo tratava como "outra data").
- aceite sem data ("pode confirmar") usa a data curta (o modelo repetia a pergunta).
- confirmação direta, sem repetir a data, sem dois "Então".
- abertura do ativo com ≤45 palavras.
- falecimento: regex `(posso|prefere que eu|quer que eu) mand` em vez de string fixa.
- crise barrada pelo filtro do provedor reserva → `_resposta_crise`.
