# Padrão de variáveis das jornadas (voz e board)

> Cópia para a skill. **Fonte:** `projetos_coral/fluxos-voz/PADRAO_Variaveis_Jornada.md`; mudou lá, copia aqui.

Decisão do Gui, 17/11/2026: **toda jornada nova usa os mesmos nomes de variável, e o padrão é o da Bull.** Vale para o
board no FigJam, a fraseologia, o painel de dúvidas, a demo e o `.ivr` da Sinergy. Primeira jornada migrada: FAZ Cred
(17/11). Fonte dos nomes: board de voz da Bull (`LskRNTWVbUHuzbelCiaIfa`; página v1 para a legenda, página v2 para as
ofertas e as datas) e `bull/DICIONARIO_Variaveis_Jornada.md`.

## Regras

1. **No board, na fraseologia e nos documentos:** `[NOME_EM_MAIUSCULAS]`, entre colchetes e em **negrito**. Ex.: `[VALOR_VISTA]`.
2. **Na demo e no `.ivr`:** o mesmo nome em minúsculas, no formato da Sinergy: `{@valor_vista}`. A coluna do mailing
   (dict `CAMPOS`) é o mesmo nome em maiúsculas, sem colchetes: `VALOR_VISTA`.
3. **Um nome por conceito.** Antes de criar variável, procure o conceito na tabela abaixo. Existe: use o nome. Não
   existe: crie com o mesmo estilo e **inclua aqui no mesmo dia**, com o cliente que criou.
4. **Nome igual só para significado igual.** Se o conceito do cliente é outro, o nome é outro, mesmo que pareça
   parecido (ex.: `[VALOR_ATUALIZADO]` é a dívida com juros e multa; o à vista recalculado no fechamento é
   `[VALOR_VISTA_RECALCULADO]`).
5. **Escopo alternativo da mesma oferta ganha sufixo**, não nome novo: a FAZ Cred oferece quitar tudo (nome base) e
   regularizar só as parcelas em atraso (`_REGULARIZAR`).
6. A tabela **Variáveis da ligação** da seção 1 do board tem 3 colunas: **Variável · O que é · Onde aparece**
   (Gui, 17/11: sem "Nome padrão" e sem "De onde vem"; quem usa cada nome fica neste dicionário).

## Dicionário

| Variável | O que é | Quem usa |
|---|---|---|
| **Identidade** | | |
| `[PRIMEIRO_NOME]` | Primeiro nome do cliente, o que a Córa fala | Bull · FAZ Cred |
| `[NOME]` | Nome completo, só em payload (transbordo, HSM) | Bull |
| `[CPF]` | CPF do titular (payload) | Bull |
| `[PERIODO]` | Saudação por horário (bom dia / boa tarde / boa noite) | Bull |
| **Produto e contrato** | | |
| `[PRODUTO]` | Identificador interno do produto | Bull |
| `[PRODUTO_CANONICO]` | Nome do produto falado ao cliente | Bull |
| `[ORIGEM]` | Marca ou canal onde o cliente contratou | Bull |
| `[SEGMENTO]` | Situação do contrato que decide o ramo da jornada | Bull |
| **Dívida** | | |
| `[DIAS_ATRASO]` | Dias de atraso | Bull |
| `[MES_REFERENCIA]` | Mês de vencimento da parcela | Bull |
| `[VALOR_ORIGINAL]` | Parcela sem encargos | Bull |
| `[VALOR_ATUALIZADO]` | Dívida com juros e multa | Bull |
| `[VALOR_PARCELA_ANTIGA]` | Valor da parcela mais antiga | Bull |
| **Ofertas** | | |
| `[VALOR_VISTA]` | Valor à vista oferecido, já com desconto quando houver | Bull · FAZ Cred |
| `[DESCONTO]` | Percentual de desconto do à vista | FAZ Cred (novo) |
| `[VALOR_ENTRADA]` | Entrada do parcelado | Bull |
| `[QTD_PARCELAS]` | Número de parcelas da opção oferecida | Bull · FAZ Cred |
| `[VALOR_PARCELA]` | Valor de cada parcela da opção oferecida | Bull · FAZ Cred |
| `[DESCONTO_PARCELADO]` | Percentual de desconto do parcelado | FAZ Cred (novo) |
| `[VALOR_VISTA_RECALCULADO]` | À vista recalculado no fechamento, quando mudou desde a oferta | FAZ Cred (novo) |
| `[..._REGULARIZAR]` | A mesma oferta, só sobre as parcelas em atraso: `[VALOR_VISTA_REGULARIZAR]`, `[DESCONTO_REGULARIZAR]`, `[QTD_PARCELAS_REGULARIZAR]`, `[VALOR_PARCELA_REGULARIZAR]` | FAZ Cred |
| **Datas** | | |
| `[DATA_PADRAO]` | Data da oferta: pagamento à vista e entrada do parcelado | Bull · FAZ Cred |
| `[DATA_MAXIMA]` | Segunda data, a mais longa, oferecida quando o cliente pede outra | Bull · FAZ Cred |
| `[DATA_SOLICITADA]` | Data que o cliente pediu, quando cabe até a máxima | Bull |
| `[DATA_RETORNO]` | Data combinada para novo contato (WhatsApp) | Bull |
| **Acordo que o cliente já tem** | | |
| `[VALOR_PARCELA_ACORDO]` | Parcela do acordo em aberto | FAZ Cred (novo) |
| `[VENCIMENTO_ACORDO]` | Vencimento dessa parcela | FAZ Cred (novo) |
| `[DATA_QUEBRA]` | Último dia antes de o acordo ser cancelado | FAZ Cred (novo) |
| `[QTD_PAGAS]` · `[QTD_NEGOCIADAS]` | Parcelas pagas · parcelas em acordo anterior | Bull |
| **Acordo fechado na ligação** | | |
| `[VALOR_ACORDO]` | Valor do acordo fechado | Bull |
| `[DESCRICAO_CONDICAO]` | Descrição neutra da condição (ex.: "parcelamento em 4x") | Bull |
| `[LINK_PAGAMENTO]` | Link do boleto ou Pix | Bull |
| **Canais e transbordo** | | |
| `[TELEFONE]` | Telefone do cliente | Bull |
| `[NUMERO_CENTRAL]` | WhatsApp oficial do credor | Bull |
| `[URL_PORTAL]` | Portal de negociação do credor | Bull |
| `[MOTIVO_TRANSBORDO]` · `[TRANSCRICAO_DA_CONVERSA]` | Payload do transbordo | Bull |
| `[TEXTO_ORIENTACAO_RH]` · `[TENTATIVAS]` | Roteiro do RH · contador de tentativas | Bull |

## Nomes que não se usam mais

| Não usar | Usar | Onde aparece hoje |
|---|---|---|
| `[DATA_LIMITE]` | `[DATA_PADRAO]` | Bull, página v1 e HSM-A |
| `[DATA_LIMITE_MAX]` | `[DATA_MAXIMA]` | Bull, página v1 |
| `[TOTAL_DISCOUNTED_AMOUNT]` | `[VALOR_VISTA]` | Bull, página v1 (SPT 79) |
| `[nome]` | `[PRIMEIRO_NOME]` | Vale |
| `[data_curta]` · `[data_longa]` | `[DATA_PADRAO]` · `[DATA_MAXIMA]` | Vale (skill `jornada-voz` até 17/11) |
| `[n]` | `[QTD_PARCELAS]` | Vale |

⚠️ **O board da Bull ainda mistura v1 e v2** (`[DATA_LIMITE]` × `[DATA_PADRAO]`, `[VALOR_ATUALIZADO]` × `[VALOR_VISTA]`
no lugar do à vista). É da frente Bull: o padrão acima segue a v2 nas ofertas e datas, e a limpeza do board de lá fica
com aquela frente. A **Vale** segue com os nomes em minúsculas (jornada já construída, outra frente); a regra vale para
os fluxos novos e para as migrações que forem pedidas.

## De-para aplicado na FAZ Cred (17/11)

`[nome]`→`[PRIMEIRO_NOME]` · `[valor_avista]`→`[VALOR_VISTA]` · `[n]`→`[QTD_PARCELAS]` · `[valor_parcela]`→`[VALOR_PARCELA]`
· `[data_entrada]`→`[DATA_PADRAO]` · `[data_entrada_2]`→`[DATA_MAXIMA]` · `[desconto]`→`[DESCONTO]` ·
`[desconto_parcelado]`→`[DESCONTO_PARCELADO]` · `[valor_regularizar]`→`[VALOR_VISTA_REGULARIZAR]` ·
`[desconto_regularizar]`→`[DESCONTO_REGULARIZAR]` · `[n_regularizar]`→`[QTD_PARCELAS_REGULARIZAR]` ·
`[parcela_regularizar]`→`[VALOR_PARCELA_REGULARIZAR]` · `[valor_atualizado]`→`[VALOR_VISTA_RECALCULADO]` ·
`[valor_acordo]`→`[VALOR_PARCELA_ACORDO]` · `[vencimento_acordo]`→`[VENCIMENTO_ACORDO]` · `[data_quebra]`→`[DATA_QUEBRA]`.
Aplicado no board, na fraseologia, no painel de dúvidas e na demo (`{@...}` e colunas do mailing simulado).
