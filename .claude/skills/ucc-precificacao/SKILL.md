---
name: ucc-precificacao
description: Precifica um cliente no modelo UCC (Unidade de Cobrança Coral). Dimensiona as unidades, custeia com o coeficiente de telecom medido, compara contra as âncoras e produz primeiro uma PLANILHA interna para aprovação e, depois de aprovada, a PROPOSTA para o cliente. Use quando aparecer deal novo, repactuação, ou quando alguém pedir "quanto cobrar" de uma carteira.
---

# Precificação UCC

Duas etapas, nesta ordem, **sempre**:

| Etapa | Saída | Para quem | Contém custo/margem? |
|---|---|---|---|
| **1 · Planilha** | `.md` de planilha | Interno (Gui) | **Sim** |
| **2 · Proposta** | `.md` de proposta | Cliente | **Nunca** |

**A etapa 2 só acontece depois de aprovação explícita da etapa 1.** Não escreva proposta junto
com a planilha, nem "já deixando pronta". O número muda na revisão — é a regra, não a exceção.

---

## Etapa 1 — Planilha

### Colete as entradas antes de calcular

**Bloqueantes** (sem elas, não cote — pergunte):

| Entrada | Por quê |
|---|---|
| **Base de CPFs** | Dimensiona as unidades |
| **Régua de tentativas/dia** | É o parâmetro mais pesado: dirige telecom **e** capacidade |
| **Canais contratados** | Define quais linhas de acionamento existem |

**Importantes** (assuma e escreva a premissa se não souber):

| Entrada | Default se ausente |
|---|---|
| Cadência de texto por canal | Só voz (`--wa 0 --sms 0 --email 0`) e mensageria cobrada à parte |
| Telefones por CPF | 1,0 — **e avise**: o discador capeia por linha, então 1,6 telefones consomem 60% mais régua |
| Mix de aging | Sem ele, a modalidade híbrida fica fora |
| Qualidade do mailing | É risco, não preço — registre |

### Rode a calculadora

**A conta sai do script. Nunca faça a aritmética na mão nem "de cabeça".**

```bash
python3 scripts/ucc_calc.py --cpfs 12000 --regua 4 --wa 1 --sms 2 --email 0 \
        --cliente "Nome" --saida planilha.md
```

Opcionais: `--telefones 1.6` · `--realizacao 0.8` · `--preco 8000` ·
`--recuperacao 117530 --fee-variavel 6.27` (liga o bloco de custo por R$ 1 recuperado).

**Deriva o preço do custo em vez de fixá-lo** com `--alvo 20` (margem alvo em %). Com `--alvo 0`
sai o equilíbrio exato. Cada carteira tem o seu preço, porque cada uma custa diferente.

⛔ **Informe `--receita-base` com o que a Coral já fatura por mês.** O degrau tributário é da
pessoa jurídica, não do contrato: se a Coral já passa de R$ 62.500/mês, o deal novo cai inteiro na
faixa marginal e custa ~5,3% mais para entregar. Sem esse número, o contrato é avaliado sozinho e o
preço sai barato demais.

```bash
python3 scripts/ucc_calc.py --cpfs 12000 --regua 4 --wa 1 --sms 2 \
        --alvo 20 --receita-base 62500 --cliente "Nome" --saida planilha.md
```

Se o deal tem implantação ou posição humana: `--setup 60000 --setup-meses 12` (amortiza) e
`--pas 1 --pa-custo 10000` (transbordo). Os dois entram como **capacidade**.

### Abra a carteira por faixa de atraso sempre que o credor mandar o aging

```bash
python3 scripts/ucc_calc.py --faixas scripts/faixas_exemplo.json \
        --regua 3 --wa 5 --sms 2 --email 1 --alvo 20 --cliente "Nome" --saida planilha.md
```

Com `--faixas` a base sai da soma das faixas (o `--cpfs` é ignorado) e a planilha ganha duas
seções: **Merecimento por faixa** e a **DRE** com a receita variável da tabela do credor.

O JSON é uma lista; cada faixa precisa de **`cpfs` e `carteira`**, e aceita `meta` (recuperação
**observada** daquela faixa sobre a carteira dela, em %), `aliq` (alíquota do credor, em %) e
cadência própria (`regua`/`wa`/`sms`/`email`, que herdam o contrato quando ausentes). Modelo em
`scripts/faixas_exemplo.json`; o contrato de referência está em `scripts/faixas_referencia.json`.

⛔ **`cpfs` por faixa é obrigatório e o script recusa sem ele.** O aging costuma vir só com saldo
em R$, e o custo escala com CPF — ratear os CPFs proporcionalmente ao saldo assume ticket médio
uniforme, que o próprio aging desmente (na Cayena o ticket varia 4× entre faixas). **Peça ao
credor.**

⚠️ A **meta é a observada, nunca a declarada**. Meta declarada infla o variável no papel e, num
modelo com gatilho, crava o ajuste no piso todo mês.

⚠️ As elasticidades do corte de cadência (WhatsApp 3,0% · SMS 1,0% · e-mail 0,2% da recuperação
por toque removido) são **premissa**, não medição nossa — ajuste com `--elast-wa` e afins se o
credor tiver número próprio, e diga na planilha que é premissa.

### Leia a saída com estes olhos

1. **Use a linha "pela medição", não a "premissa do modelo".** A premissa de telecom fixo por
   unidade erra nos dois sentidos, e o script diz de quanto e para que lado.
2. **Se o equilíbrio por unidade passar do preço**, o deal nasce negativo. Não maquie: reduza
   cadência, reduza régua, ou reprecifique.
3. **Folga até a âncora de R$ 12.000** é o espaço que existe para margem, desconto e variação de
   intensidade. Folga curta significa que não cabe desconto por volume.
4. **Merecimento decide escopo antes de decidir preço.** A coluna **R$ por R$ 1 recuperado**
   põe custo e recuperação na mesma linha. Faixa com recuperação zero levando fatia grande do
   custo não é problema de preço — é pergunta ao credor sobre por que ela está no escopo (na
   Cayena, 82% do custo em faixas que devolvem nada).
5. **Cortar cadência por faixa é ordens de grandeza melhor que cortar por canal na base inteira.**
   O rodapé do merecimento imprime quanto se destrói por R$ 1 economizado; acima de R$ 1 o corte
   destrói mais do que gera.
6. **O tributo já é progressivo.** Acima de R$ 62.500/mês de receita (somada à `--receita-base`)
   o adicional de IRPJ entra na conta e a carga efetiva vai de 16,33% para até 19,53%. A planilha
   imprime a alíquota efetiva do contrato — confira se ela bate com a faixa que você esperava.

### Entregue assim

Poste a planilha e, em no máximo cinco linhas, diga: quantas unidades, qual margem pela medição,
qual o maior risco, e o que você precisa que seja decidido. Sem repetir a tabela em prosa.

---

## Etapa 2 — Proposta (só depois de aprovada)

### Regras invioláveis

- ⛔ **Nenhum custo, nenhuma margem, nenhum break-even.** A proposta diz preço e escopo.
- ⛔ **Nenhum identificador técnico** — sem nome de tabela, de fornecedor, de ferramenta interna ou
  UUID. Proveniência, quando precisar citar, é "base oficial da operação".
- ⛔ **Nada de estrutura de custo por linha.** O cliente compra a unidade, não o rateio dela.
- ✅ **As premissas vão escritas**, com régua, cadência e telefones por CPF. Sem isso a variação de
  intensidade vira risco nosso e a conversa de reajuste não tem onde se apoiar.

### Estrutura

1. **O que a unidade entrega** — contato, inteligência, operação, infra. Sem preço ainda.
2. **Dimensionamento** — a base do cliente, quantas unidades, e por quê.
3. **Investimento** — preço por unidade × unidades. Modalidade escolhida.
4. **Premissas** — régua, cadência, canais, telefones/CPF. É a seção que protege os dois lados.
5. **O que está fora** — setup, onboarding, transbordo humano, canais não contratados.
6. **Próximos passos.**

### Tom

Aplique `projetos_coral/estilo/GUIA_DE_ESCRITA.md`. Direto, sem vício de IA, sem tríade retórica,
sem travessão de suspense.

---

## Modalidades

**A — Valor fixo.** Mesmo valor todo mês. Serve para carteira nova, sem histórico para calibrar meta.

**B — Híbrido com gatilho.** Fixo da UCC (100%, sempre) **+** a variável que o credor já pratica.
O gatilho de ±15% incide **na alíquota** de cada faixa de atraso, nunca no R$.

```
fatura = fixo_UCC + Σ_faixa ( recuperado × alíquota × (1 + ajuste) )
```

- **É soma, não MAX.**
- **A meta é a OBSERVADA**, nunca a declarada pelo cliente. Meta em cima de aspiração comercial
  deixa o gatilho cravado no piso todo mês, o que é desconto fixo e não gatilho.
- **Desempenho e gatilho são eixos diferentes** e se multiplicam: 20% acima da meta com alíquota
  15% maior dá +38% na variável, não +35%.
- Só ofereça B com histórico de recuperação por faixa. Sem isso, não há meta defensável.

---

## Guardrails

1. **Nunca precifique só pelo fixo.** A unidade cheia empata por construção: o preço da UCC é
   recuperação do custo de tê-la ligada. A margem vem do acionamento ou do gatilho.
2. **Não venda unidade acima de 2.500 CPFs.** Cada 500 a mais tiram ~8 pontos de margem.
3. **Confira o teto de custo por R$ 1 recuperado** que o credor pratica antes de somar fixo +
   variável. Referência de mercado: R$ 0,30.
4. **Desconto por volume tem justificativa** (o compartilhado dilui) mas só fecha 100% a 100.000
   CPFs. Não entregue a diluição antes de ela existir.
5. **Mudou parâmetro?** Atualize `projetos_coral/comercial/UCC_Modelo_Remuneracao.md` **primeiro**,
   depois o dicionário `P` em `scripts/ucc_calc.py`. Constante duplicada sem sincronizar já causou
   drift neste repo.

---

## Lacunas — declare sempre, não esconda

O script já imprime estas na planilha. Repita as relevantes na conversa:

- ⚠️ **Setup, onboarding e transbordo humano entram com valor que VOCÊ informa**, não medido.
  A referência de R$ 10.000 por posição é tabela de mercado (o que a Cayena paga à Verso), não
  medição nossa. Zerados por default — se o deal tem implantação ou posição, informe.
- ⛔ **Prazo, reajuste, ramp-up e churn** — sem série histórica.
- ⛔ **Escada de desconto por volume** — existe a justificativa, não existe o degrau.
- ⚠️ **Mensageria** vem de tabela de fornecedor, não de medição própria: a operação que medimos é
  predominantemente de voz. É a maior linha variável e a menos calibrada.

---

## Documentos de apoio

| Doc | Para quê |
|---|---|
| `projetos_coral/comercial/UCC_Modelo_Remuneracao.md` | **Fonte de verdade** do modelo: parâmetros, histórico, furos |
| `projetos_coral/comercial/UCC_Precificacao_Referencia.md` | A referência de bolso: parâmetros com origem, checklist de carteira |
| `projetos_coral/estilo/GUIA_DE_ESCRITA.md` | Tom de qualquer texto que sai daqui |
