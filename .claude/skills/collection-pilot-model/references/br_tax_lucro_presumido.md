# Brazilian Tax — Regime Lucro Presumido (Serviços de Cobrança)

Applicable to service companies (prestadores de serviço) in Brazil, including collection
outsourcing (BPO cobrança). All rates are adjustable blue input cells in the spreadsheet.

## Tributos sobre Receita Bruta

| Tax     | Rate  | Base          | Notes |
|---------|-------|---------------|-------|
| ISS     | 5.00% | Receita bruta | Municipal; range 2–5%, collection services typically 5% |
| PIS     | 0.65% | Receita bruta | Cumulative regime (Lucro Presumido) |
| COFINS  | 3.00% | Receita bruta | Cumulative regime (Lucro Presumido) |
| **Total** | **8.65%** | Receita bruta | Same rate regardless of scenario |

## Tributos sobre Resultado (Base Presumida)

| Tax           | Rate  | Base                        | Notes |
|---------------|-------|-----------------------------|-------|
| Base presunção | 32%  | Receita bruta               | Standard for "serviços em geral" (RIR/1999) |
| IRPJ          | 15%   | Base presumida              | On the full base |
| Adicional IRPJ | 10%  | Base presumida − R$20k/mth  | Only on the excess above R$20,000/month |
| CSLL          | 9%    | Base presumida              | Social contribution |

## Effective Total Burden (approximate)

With receita bruta = R$X/mês:
```
ISS+PIS+COFINS  = 0.0865 × X
Base presumida  = 0.32   × X
IRPJ            = 0.15   × 0.32 × X  = 0.048X
Adicional IRPJ  = 0.10 × MAX(0, 0.32X - 20000)   (typically ~0.6% of X at pilot scale)
CSLL            = 0.09   × 0.32 × X  = 0.0288X
─────────────────────────────────────────────────
Total burden ≈ 16–17% of receita bruta
```

## Break-even Treatment

At the financial break-even point, there is no profit — so IRPJ and CSLL are
effectively zero (no taxable income). The break-even formula therefore only includes
revenue taxes:

```
break_even_recovery = total_costs / (weighted_fee × (1 − ISS_rate − PIS_rate − COFINS_rate))
```

Where `weighted_fee` across B bands:
```
= (fee_1×carteira_1 + fee_2×carteira_2 + ... + fee_B×carteira_B) / total_carteira_piloto
```

## Spreadsheet Inputs (all in column C, apply to all 3 scenarios)

```
r_iss   : ISS rate          = 0.05
r_pis   : PIS rate          = 0.0065
r_cof   : COFINS rate       = 0.03
r_pres  : Base presunção    = 0.32
r_irpj  : IRPJ rate         = 0.15
r_adic  : Adicional IRPJ    = 0.10
r_lim   : Limite mensal     = 20000  (R$, monetary value)
r_csll  : CSLL rate         = 0.09
```

## Key Formulas (per scenario column, e.g., col C = Baseline)

```python
# ISS/PIS/COFINS: direct multiplication on revenue
f'=C{r_rev_ref}*C{r_iss}'   # → ISS value
f'=C{r_rev_ref}*C{r_pis}'   # → PIS value
f'=C{r_rev_ref}*C{r_cof}'   # → COFINS value

# Base presumida
f'=C{r_rev_ref}*C{r_pres}'

# IRPJ
f'=C{r_base_pres}*C{r_irpj}'

# Adicional IRPJ (MAX prevents negative)
f'=MAX(0,(C{r_base_pres}-C{r_lim})*C{r_adic})'

# CSLL
f'=C{r_base_pres}*C{r_csll}'
```

Note: `r_lim` stores an absolute monetary value (R$20,000) — use `inp_val()` function
with `number_format = 'R$\\ #,##0'`, not a percentage format.
