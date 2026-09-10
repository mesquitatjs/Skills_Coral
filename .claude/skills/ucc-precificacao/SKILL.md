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

### Leia a saída com estes olhos

1. **Use a linha "pela medição", não a "premissa do modelo".** A premissa de telecom fixo por
   unidade erra nos dois sentidos, e o script diz de quanto e para que lado.
2. **Se o equilíbrio por unidade passar do preço**, o deal nasce negativo. Não maquie: reduza
   cadência, reduza régua, ou reprecifique.
3. **Folga até a âncora de R$ 12.000** é o espaço que existe para margem, desconto e variação de
   intensidade. Folga curta significa que não cabe desconto por volume.
4. **Receita acima de R$ 62.500/mês** dispara aviso bloqueante: a alíquota de 16,33% não vale mais.
   Feche com a contabilidade antes de cotar.

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

- ⛔ **Tributo acima de R$ 62.500/mês de receita** — a alíquota muda e não está modelada.
  Deal a partir de ~8 unidades cruza a linha.
- ⛔ **Setup, onboarding e posição humana de transbordo** não estão precificados.
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
