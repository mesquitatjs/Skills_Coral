# Costs Block Reference — Collection Pilot Model

## Structure (starts at row 54, ends at row 97)

The costs block always has the same 44-row structure. Rows are tracked with Python
variables (`r_op_qty`, `r_bv_qty`, etc.) — never hardcoded.

```
R=54  Header "BLOCO DE CUSTOS OPERACIONAIS"
R=55  Column headers (Item | Qtd | Custo Unit. | Total | Fonte)

R=56  ── Seção 1: Operadores Humanos ──
R=57  r_op_qty  = Qtd. operadores (PA)          default: 10 | R$3,500/PA
R=58  r_op_sub  = subtotal operadores

R=59  ── Seção 2: Staff Operacional (CONDITIONAL) ──
R=60  r_st1  = Coordenador(es)                  default: 1 | R$7,000
R=61  r_st2  = Supervisor(es)                   default: 1 | R$5,500
R=62  r_st3  = Treinamento (amort.)             default: 1 | R$800
R=63  r_st_sub = IF(r_op_qty>0, SUM(st1:st3), 0)

R=64  ── Seção 3: Bot de Voz ──
R=65  r_cpf_per_bot = CPFs por bot              default: 3,000
R=66  Total CPFs piloto (display ref)           =H_TOTAL_CPFS
R=67  r_bv_qty  = CEILING(H_TOTAL_CPFS/C65, 1)
R=68  r_bv_cost = Custo/bot/mês                 default: R$2,000
R=69  r_bv_sub  = subtotal bots

R=70  ── Seção 4: Telecom ──
R=71  📖 Ref ebook: chamadas/PA-mês (humano)    9,084 calls | R$0.004/call
R=72  📖 Ref ebook: custo telefonia/PA-mês      R$872/PA
R=73  r_tc_h_total = IF(r_op_qty>0, r_op_qty×872, 0)
R=74  📖 Ref ebook: chamadas/bot-mês (digital)  12,350 calls | R$0.004/call
R=75  📖 Ref ebook: custo telefonia/bot-mês     R$1,186/bot
R=76  r_tc_d_total = r_bv_qty × 1,186
R=77  r_tc_sub  = subtotal telecom

R=78  ── Seção 5: CRM ──
R=79  r_crm1 = Licença CRM fixo                 default: 1 | R$2,500
R=80  r_crm2 = Custo por CPF ativo              qty=H_TOTAL_CPFS | R$0.15/CPF
R=81  r_crm_sub = subtotal CRM

R=82  ── Seção 6: Massivas (SMS / RCS / WhatsApp) ──
R=83  r_sms = SMS                               default: 40,000 | R$0.085
R=84  r_rcs = RCS                               default: 20,000 | R$0.18
R=85  r_wpp = WhatsApp (HSM/sessão)             default: 25,000 | R$0.25
R=86  r_mass_sub = subtotal massivas

R=87  ── Seção 7: Plataforma ──
R=88  r_p1 = Plataforma de orquestração         default: 1 | R$3,500
R=89  r_p2 = Infraestrutura cloud               default: 1 | R$1,200
R=90  r_plat_sub = subtotal plataforma

R=91  ── Seção 8: Staff Suporte ──
R=92  r_s1 = Planejamento operacional           default: 1 | R$6,000
R=93  r_s2 = Control Desk / Qualidade           default: 1 | R$5,000
R=94  r_s3 = MIS / BI / Dados                   default: 1 | R$6,500
R=95  r_sup_sub = subtotal suporte

R=96  (blank row)
R=97  row_total_cost = ★★ TOTAL CUSTOS  =SUM(all subtotals)
```

## Total formula
```python
formula_total = (
    f'=E{r_op_sub}+E{r_st_sub}+E{r_bv_sub}+'
    f'E{r_tc_sub}+E{r_crm_sub}+E{r_mass_sub}+'
    f'E{r_plat_sub}+E{r_sup_sub}'
)
```

## Telecom sources (Ebook Alavancas, pág. 7 — Matriz de Capacidade Instalada)
| Resource     | Calls/month | Telecom cost/month | Op cost/month |
|---|---|---|---|
| PA humano    | 9,084       | R$872              | —             |
| Agente digital | 12,350    | R$1,186            | R$2,000       |

These are default values — always expose as blue (adjustable) input cells in the spreadsheet.

## CoralAi bot rule
1 voice bot per 3,000 CPFs in the pilot. Expose `CPFs_por_bot = 3000` as an input cell
(r_cpf_per_bot) so the user can adjust if needed.

## Notes on TEAL rows (📖)
Telecom reference rows (ebook data) use TEAL background and italic font. They are
INFORMATIONAL ONLY — their E column shows `'—'` and they are NOT included in any
subtotal formula. They exist to provide auditability for the telecom unit costs.
