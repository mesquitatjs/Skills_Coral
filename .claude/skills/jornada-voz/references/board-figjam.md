# O board no FigJam

Modelo: board da Vale (`figma.com/board/5YdMILtAH2E1ofoy8ECWX5`). Toda escrita é por `use_figma` dentro de uma
sessão (`create_session` com o fileKey). Leia a skill `figma-use` antes do primeiro script.

## As 3 seções, nesta ordem

| Seção | O que tem | Quem lê |
|---|---|---|
| `1 · Como ler e mapa` | legenda de formas, cores e setas · **mapa das situações** (por onde o cliente passa conforme muda a situação, com CPFs por caixa quando houver foto) · o que a Córa nunca diz · regras da conversa · **Variáveis da ligação** (tabela, ver abaixo) | cliente, na primeira leitura |
| `2 · Jornadas por situação` | uma jornada por situação, em **raias** (cliente · ligação da Córa · cliente-empresa · sistema), correndo no tempo da esquerda para a direita | cliente e produto |
| `3 · Falas da Córa na ligação` | tudo o que a Córa fala, palavra por palavra, por etapa e por situação, com as objeções em tabela | cliente, Sinergy (via IVR) e quem escreve os prompts |

Seções antigas (rascunhos, versões, "v1/v2") saem do board quando a versão nova fecha: o cliente abre o link e vê
uma coisa só. Na Vale, as seções 1–7 originais viraram estas três em 06/11.

## Formas e cores (legenda da seção 1)

| Passo | Forma | Fundo / borda |
|---|---|---|
| Fala da Córa | quadrado | `#dcccff` / `#874fff` (roxo) |
| O que o cliente faz ou diz | quadrado | branco / `#757575` |
| Decisão | losango | branco / `#757575` (decisão que o sistema toma: `#c6faf6` / `#5ad8cc`) |
| O que o cliente-empresa ou o sistema faz | quadrado | `#c6faf6` / `#5ad8cc` (azul-água) |
| Depende de confirmação do cliente-empresa | quadrado | `#ffecbd` / `#ffc943` (amarelo) |
| Acordo ou pagamento | retângulo arredondado | `#cdf4d3` / `#66d575` (verde) |
| Sai da cobrança | retângulo arredondado | `#d9d9d9` / `#b3b3b3` (cinza) |
| Vem de ou vai para outra jornada | retângulo arredondado | `#ffe0c2` / `#ff9e42` (laranja) |
| Entrada ou saída da jornada | retângulo arredondado | branco / `#757575` |
| Jornada no mapa (seção 1) | retângulo arredondado | branco / `#1e1e1e`, borda 3 |

Conector do caminho principal: linha **sólida**, cotovelo (`ELBOWED`), `#1e1e1e`, espessura 3, ponta `ARROW_LINES`,
com o rótulo da condição no texto (`é o cliente`, `sim`, `não`, `à vista`). Caminho alternativo: mesma linha com
`dashPattern` (a propriedade é `dashPattern`, não `strokeDashes`). Para clonar um conector tracejado sem um
"modelo" vivo, crie um conector solto com `connectorStart = {position}` e remova no fim.

Texto dos cartões: Inter Medium, 20 na seção 3 (16 na legenda). Borda 4. Largura 420 para fala, 460 para losango.

## Códigos e um cenário por caixa

- Toda caixa da seção 3 começa com **código**: letra do bloco + dois dígitos (`A01`, `B07`, `C04`). Os blocos da
  Vale: **A** abertura e identidade (todas as situações) · **B** demitido · **C** ativo com diferença · **D**
  revinculado · **E** afastado · **F** encerramentos comuns. Cliente novo: A e F ficam, os do meio seguem as
  situações dele.
- O código é o que liga o artefato de dúvidas, o dossiê, o prompt e o chamado da Sinergy à caixa. Não renumere
  depois de publicar; caixa nova ganha o próximo número livre do bloco.
- **Um cenário por caixa.** "À vista ou parcelado", "sim/não", "escolheu data / pediu outra" são caixas separadas,
  ligadas por conector com rótulo. Foi a regra que mais mudou o board da Vale e a que mais ajuda a Sinergy.
- Cada bloco tem título (Inter Medium 48) e uma linha de contexto (Inter Regular 24) dizendo para quem vale.

## Tabela de objeções

Depois do caminho principal de cada bloco, uma tabela "**Outras respostas**" com três colunas em texto
(Inter Medium 24): **O cliente diz · A Córa responde · Depois**. Uma linha por objeção, a fala completa na coluna
do meio e o destino na última (`volta para a oferta`, `F03`, `WhatsApp`). Tudo o que está nessa tabela está no
prompt como `* <objeção> (SPT n): "<fala>"`.

## Variáveis

- Sempre `[nome]`, entre colchetes e em **negrito** (Inter Bold via `setRangeFontName` no intervalo). O resto do
  cartão fica Inter Medium.
- Uma variável por conceito, com o mesmo nome em todas as caixas. Na Vale: `[nome] [valor] [empresa] [mes]
  [diferenca] [n] [dia] [data_curta] [data_longa] [vencimento] [contratacao]`.
- Datas: **só** `[data_curta]` e `[data_longa]`. A data máxima do pagamento é a longa; não existe `[data_max]`.
- Um script de varredura ao fim de cada rodada: todas as ocorrências de `[...]` em negrito, nenhuma `(data)`,
  `{x}` ou nome fora da lista.

### Bloco "Variáveis da ligação" (obrigatório na seção 1)

Toda jornada tem, na seção 1, abaixo do mapa, um bloco com **todas** as variáveis que aparecem nas falas. Modelo:
FazCred (`projetos_coral/fazcred/`, board `xRP4BNX9RJ8zxVigDnMQMQ`, 12/11/2026).

- Título `Variáveis da ligação` (Inter Medium 48) e uma linha de contexto (Inter Regular 26): "Tudo o que aparece em
  [colchetes] nas falas. A Córa troca cada variável pelo valor deste cliente, nesta ligação. Valores e datas são
  falados por extenso."
- **Tabela FigJam** (não caixas), cabeçalho escuro, 4 colunas: **Variável** (em negrito) · **O que é** (uma frase,
  em linguagem do cliente, com exemplo quando ajuda: "por extenso (ex.: agosto e setembro)") · **De onde vem**
  (carteira do cliente · consulta da dívida · simulação/oferta · recálculo antes de fechar · calendário · resposta do
  cliente na ligação) · **Onde aparece** (os códigos das caixas, ou "todas as ofertas dos blocos B e C").
- Variável cujo valor ainda depende do cliente leva o número da dúvida na coluna **De onde vem** ("carteira (dúvida D13)").
- Uma linha por variável; par que só existe junto (`[valor_1] · [valor_2]`) pode dividir a linha.
- A coluna **Onde aparece** sai do gerador (varrer as falas das caixas e das tabelas), nunca escrita à mão.
- Larguras de referência: 520 · 1400 · 900 · 1200.
- As mesmas definições vão para o gerador (`variaveis_def` no mapa/JSON: nome → [o que é, de onde vem]), para a
  demo, o prompt e o board usarem o mesmo texto. Variável nova no board = linha nova na tabela e no gerador, na
  mesma rodada.
- Na varredura de variáveis, conferir também: toda variável usada nas falas está na tabela, e a tabela não tem
  variável que nenhuma fala usa.

## O que nunca entra no board

- Nome de nó, SPT, `node_saida`, `#var_`, Sinergy, OCS, CobranSaaS, nome de tabela. Os códigos `A01` são a única
  referência técnica, e são nossos.
- Custo, margem, posição de negociação.
- "Atendente", "transferir", "operador". Transbordo é "a equipe responde pelo WhatsApp".
- Jornada de texto (WhatsApp, SMS, e-mail): é outro material.

## Varreduras antes de mandar ao cliente

1. **Sobreposição:** nenhuma caixa cobrindo outra dentro da seção (comparar os retângulos; a Vale pegou 3 depois da
   reorganização).
2. **Saídas:** toda decisão com os dois ramos ligados; toda fala sem conector de saída é fim e tem despedida.
3. **Termos:** varrer os textos pela lista de termos internos e por "atendente/transferir/humano".
4. **Variáveis:** lista fechada, colchetes, negrito, e a tabela **Variáveis da ligação** da seção 1 bate com as falas
   (nenhuma faltando, nenhuma sobrando).
5. **Leitura de cliente:** nomes de etapa em linguagem de gente ("7 dias do novo emprego", não "R+7"; "com garantia
   do FGTS", não "contrato novo").
6. **Share:** liberar o acesso por link antes de mandar. Quem abre vê a última versão; não há "pinned" no FigJam, mas
   confira que não sobrou seção de rascunho.
