---
name: collection-pilot-model
description: >
  Build complete financial projection spreadsheets (.xlsx) for collection operation pilots.
  Use this skill whenever the user asks to: criar projeção de remuneração de cobrança,
  build a pilot model for a delinquency band, add a cost block or tax block to a collection
  projection, create a new version (V2/V3/V4/V5…) of a projection model, add a new
  delinquency band to an existing pilot, calculate collection margins, or any variation of
  "modelo de projeção para piloto de cobrança". Also use when the user asks to update,
  expand or version an existing .xlsx collection model. The skill covers: revenue projection
  by delinquency band with 3 efficiency scenarios, operational costs (human operators,
  voice bots, telecom, CRM, bulk messaging, platform, support staff), Brazilian tax block
  (Lucro Presumido), and net margin demonstration.
---

# Collection Pilot Financial Model — Skill Guide

## Overview

This skill produces a fully-formula-driven `.xlsx` projection model for collection
operation pilots. A **bundled script** (`scripts/build_model.py`) handles all the
openpyxl complexity — read the API below, call it with the user's data, validate with
`recalc.py`, and deliver the file. No need to write spreadsheet code from scratch.

**Always clarify with the user before writing code:**
1. Which delinquency bands are in scope (e.g., 91–120, 121–150, 151–180 days)?
2. Portfolio data for each band: total CPFs, total wallet value (R$), current efficiency
   rate (%/month), success fee (%).
3. Pilot percentage (e.g., 10% of each band).
4. Which blocks to include: revenue only? + costs? + taxes?
5. If extending an existing file: path to the current `.xlsx`.

---

## Using the Bundled Script (PREFERRED APPROACH)

The script lives at `scripts/build_model.py` relative to this SKILL.md.
**Use it for all new builds.** Only write custom openpyxl code when you need to extend
an existing file that was built outside this skill.

```python
import sys
sys.path.insert(0, '<path-to-skill-directory>')
from scripts.build_model import build_model

result = build_model(
    bands=[
        # Each band: label, valor (R$ total portfolio), cpfs, efic (%/month), fee (decimal)
        {"label": "91–120",  "valor": 207_611_875, "cpfs": 79_722,
         "efic": 0.0107, "fee": 0.1392},
        {"label": "121–150", "valor": 205_193_318, "cpfs": 79_326,
         "efic": 0.0072, "fee": 0.1463},
        # add more bands as needed — script is fully generic for N bands
    ],
    pilot_pct=0.10,          # pilot allocation (10% of each band)
    output_path="/path/to/Projecao_Piloto_VN.xlsx",
    title="CoralAi × Casas Bahia — Projeção de Remuneração — Piloto 10%",
    subtitle="Base: Indicadores operacionais Casas Bahia (mar/2026) — CONFIDENCIAL",
    include_costs=False,     # True → adds the 8-section operational costs block
    include_taxes=False,     # True → adds Lucro Presumido tax + margin blocks
                             #         (requires include_costs=True)
    band_noun="DIAS",        # suffix after each band label; "" for product bands (QV, Escriturado…)
    costs_overrides=None,    # dict overriding lean/default cost inputs (see Extended parameters)
    fixed_monthly_fee=0.0,   # >0 → hybrid model: adds a fixed monthly piso to receita
)

# result dict — use these for any custom code you add after the build:
# {
#   "REM_ROW": 49,          # row of ★★ REMUNERAÇÃO TOTAL
#   "H_TOTAL_CPFS": "H13", # cell of total pilot CPFs
#   "row_total_cost": 97,  # row of CUSTO OPERACIONAL TOTAL (0 if costs not included)
#   "row_total_taxes": 127, # row of TOTAL DE TRIBUTOS (0 if taxes not included)
# }
```

**Always validate immediately after building:**
```bash
python mnt/.claude/skills/xlsx/scripts/recalc.py "path/to/file.xlsx" 60
# Expected: {"status": "success", "total_errors": 0}
```

### Row anchor formulas (for reference / extension code)

The script computes all row numbers dynamically from B = number of bands:

| Anchor          | Formula           | B=2 | B=3 | B=4 |
|-----------------|-------------------|-----|-----|-----|
| H_TOTAL_CPFS    | H(7+2B)           | H11 | H13 | H15 |
| r_uplift_base   | 7+4B              | 15  | 19  | 23  |
| r_proj (header) | 4B+12             | 20  | 24  | 28  |
| REM_ROW         | 11B+16            | 38  | 49  | 60  |
| r_costs_start   | max(54, REM+4)    | 54  | 54  | 64  |
| row_total_cost  | r_costs_start+43  | 97  | 97  | 107 |

Premissas block (col C):
- C6 = % piloto
- C(7..6+B) = valor por faixa
- C(7+B..6+2B) = CPFs por faixa
- C(7+2B..6+3B) = eficiência por faixa ← starts here for `efic_cell`
- C(7+3B..6+4B) = success fee por faixa ← starts here for `fee_cell`
- C(7+4B), C(8+4B), C(9+4B) = uplift 0%, +30%, +50%

---

## Extended parameters — product bands · lean costs · hybrid piso

`build_model()` accepts three optional params for non-standard pilots:

### `band_noun: str = "DIAS"`
Suffix after each band label. Bands need not be delinquency *days* — they can be
**products / segments / profiles**. Pass `band_noun=""` so labels read "FAIXA QV",
"FAIXA Escriturado" instead of "FAIXA QV DIAS". (Used for the **Bull** pilot: bands = 3
consignado profiles — QV / Escriturado / Não Escriturado.)

### `costs_overrides: dict | None = None`
Overrides the default (large-portfolio) cost inputs so the cost block reflects a
**lean / incremental** operation. Keys (all optional; unset → skill default):
`operators_qty` (0 → 100% voice bot; auto-zeros human staff + human telecom), `operators_cost`,
`cpf_per_bot`, `bot_cost`, `crm_license`, `crm_per_cpf`, `sms_vol`, `rcs_vol`, `wpp_vol`,
`platform_orch`, `platform_cloud`, `support_planning`, `support_controldesk`, `support_mis`.
> The default cost block is calibrated for huge portfolios (~R$80k/mo). For a **small**
> carteira, override to a lean incremental basis (shared stack) or the margin reads absurdly
> negative. Bull lean set ≈ R$6,1k/mo: operators 0, 1 bot @2000, telecom 1186, CRM 0+0,15/CPF,
> comms sms 5000/wpp 3000, platform 0+500, support 0/500/500.

### `fixed_monthly_fee: float = 0.0`
`>0` makes the model **hybrid** (piso fixo + success fee): adds a "Receita fixa mensal — piso"
premissa row, and the consolidado splits into **Receita variável (success fee)** +
**Receita fixa (piso)** = **REMUNERAÇÃO TOTAL**; taxes/margin flow over the total. With the
hybrid, REM_ROW shifts +3 rows (fixo premissa +1, var/fix rows +2) — **always read anchors
from the returned dict, never hardcode.**

---

## Adding a front "Simulador" tab (post-processing pattern)

Gives a workbook a clean front panel where a user edits a few levers and results recalc live —
**without touching the engine**:

1. `load_workbook(file)`; read the current premissa input values from "Projeção Piloto".
2. `wb.create_sheet("Simulador", 0)` (index 0 → first tab; `sheet_view.showGridLines=False`).
3. Put the **levers** on Simulador as blue editable cells: `% piloto`, `piso`, per-product
   `carteira / efic / fee`, and the 3 `uplift` cells (seed with the read values).
4. **Rewire** Projeção premissa cells to *reference* Simulador — Simulador becomes the single
   source of the levers, engine untouched:
   `proj["C6"]="=Simulador!C5"` (% piloto) · `C22`→piso · fees `C16/C17/C18` · efic `C13/C14/C15`
   · uplifts `C19/C20/C21` · carteira `C7/C8/C9`. (Grey-italic the linked cells to signal "driven".)
5. Put the **results** on Simulador as formulas referencing computed Projeção rows (scenario
   cols C/D/E): recuperação (49), receita var (50), fixa (51), total (52), custo (`E101`,
   scenario-independent), tributos (131), margem R$ (138), margem % (139). **Read the actual
   rows from the build — don't assume.**
No circularity: Simulador inputs (constants) → Projeção references them → Projeção computes →
Simulador results reference Projeção. Reference impl: Bull `Simulador_Precificacao_Bull_V3.xlsx`.

---

## Extending an Existing File

When the user wants to add a new band to a file already built with this skill:

```python
import shutil
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border

# 1. Copy old file to new version
shutil.copy2(src_path, dst_path)
wb = load_workbook(dst_path)

# 2. Clear and rebuild "Projeção Piloto" from scratch (NEVER insert rows — formulas won't shift)
ws = wb["Projeção Piloto"]
for mr in list(ws.merged_cells.ranges):
    ws.unmerge_cells(str(mr))
for row in ws.iter_rows():
    for cell in row:
        cell.value = None
        cell.font = Font()
        cell.fill = PatternFill()
        cell.border = Border()
        cell.alignment = Alignment()
        cell.number_format = "General"

# 3. Rebuild using build_model helpers or write the new sheet manually
# Then save and validate with recalc.py
```

The safest approach for extension is: collect the new band data, update the `bands` list
in memory, call `build_model(...)` fresh with all bands + same output path.

---

## Sheet Structure

Every model has two sheets:

**"Dados Base"** — Static reference table with the creditor's full portfolio data.
Primarily informational.

**"Projeção Piloto"** — The financial model:
```
Rows 1–2    : Title + subtitle (merged B:J)
Row  3      : (blank)
Row  4      : Section headers — PREMISSAS (B:E) | RESUMO (G:J)
Row  5      : Column headers for both blocks
Rows 6+     : Premissas inputs (col C, blue) + Summary formulas (col H)
(gap 2 rows): Blank
Row r_proj  : "PROJEÇÃO MENSAL" section header
Row r_ph    : Table header (Baseline / +30% / +50%)
              [one 7-row block per band, then CONSOLIDADO]
Row REM_ROW : ★★ REMUNERAÇÃO TOTAL — KEY ANCHOR for costs + taxes
(gap rows)  :
Row R=54+   : BLOCO DE CUSTOS (if requested, starts at max(54, REM_ROW+4))
Row total_c : ★★ CUSTO OPERACIONAL TOTAL
(gap 2 rows):
Row T       : BLOCO FISCAL (if requested)
Row total_t : TOTAL DE TRIBUTOS
Row T+n     : DEMONSTRATIVO DE MARGEM LÍQUIDA
```

---

## Color Palette

```python
RED    = "D32F2F"  # headers, section titles, key result rows
CREAM  = "E8E3D8"  # subtitle bar, break-even
LGRAY  = "F2F2F2"  # alternating rows
DGRAY  = "4A4A4A"  # section headers (dark grey)
BLUE   = "0000FF"  # ALL input cells (adjustable by user)
PINK   = "FFE8E8"  # individual band remuneração rows
DPINK  = "FFD0D0"  # total remuneração row
PURPLE = "4A148C"  # tax block theme
LPURP  = "F3E5F5"  # tax data rows
MPURP  = "E1BEE7"  # tax subtotals
GREEN  = "1B5E20"  # margin block theme
LGREEN = "E8F5E9"  # margin result rows
TEAL   = "E3F2FD"  # ebook reference rows (informational, not summed)
```

---

## Common Pitfalls

### 1. The `=` obs-string bug ⚠️
Any cell value starting with `=` is interpreted as a formula by LibreOffice/Excel.
This includes obs/label strings built with f-strings. **The bundled script already
handles this**, but watch out if you write any custom cell values:

```python
# BAD — LibreOffice reads this as a formula → #N/A error
ws['F80'].value = f"={H_TOTAL_CPFS} CPFs piloto × R$0,15"

# GOOD — use a literal string
ws['F80'].value = f"Qtd. vinculada ao total de CPFs piloto ({H_TOTAL_CPFS}) × R$0,15/CPF"
```

### 2. Rebuilding vs. patching
When adding a new delinquency band or a new block, **rebuild the entire
"Projeção Piloto" sheet from scratch** — or better, call `build_model()` again with
the updated `bands` list. Row insertion with openpyxl is unreliable (formulas don't shift).

### 3. Merged cell cleanup before rewriting
Before clearing and rewriting a sheet loaded from an existing file:
```python
for mr in list(ws.merged_cells.ranges):
    ws.unmerge_cells(str(mr))
for row in ws.iter_rows():
    for cell in row:
        cell.value = None
        cell.font = Font()
        cell.fill = PatternFill()
        cell.border = Border()
        cell.alignment = Alignment()
        cell.number_format = 'General'
```

### 4. Fee vs. efficiency references
In the premissas block, efficiency values come before success fees.
With B bands, fees start at row `7+3B+i` (not `7+2B+i`).
The bundled script computes this correctly — beware if writing manual code.

### 5. CRM obs string — always a literal
The CRM "cost per CPF" obs must be a plain Python string, not a formula:
```python
# BAD: f"={H_TOTAL_CPFS} CPFs × R$0,15"   ← starts with '='
# GOOD: f"Qtd. vinculada a {H_TOTAL_CPFS} × R$0,15/CPF"
```

---

## Tax Block — Lucro Presumido (Quick Reference)

See `references/br_tax_lucro_presumido.md` for all parameters. Quick summary:

```
ISS    5.00%  on receita bruta (municipal — adjustable)
PIS    0.65%  on receita bruta (cumulative)
COFINS 3.00%  on receita bruta (cumulative)
Total:  8.65%

Base presunção: 32% of receita bruta
IRPJ  15% + 10% adicional on (base − R$20k/mth)
CSLL   9% on base
Effective burden: ~16–17% of receita bruta
```

---

## Output File Naming Convention
```
Projecao_Remuneracao_Piloto_<Creditor>_V<N>.xlsx
```
Save to the user's workspace folder (`mnt/<folder>/`).

## Validation
```bash
python /root/.claude/skills/xlsx/scripts/recalc.py "path/to/file.xlsx" 60
# Expected: {"status": "success", "total_errors": 0}
```

> **If LibreOffice/recalc is unavailable** (headless `soffice` can be broken or time out in
> some sandboxes — it fails to load even a trivial file), validate with the pure-Python
> **`formulas`** library instead (`pip install formulas`). It recalculates cross-sheet
> references end-to-end (used to verify the Bull Simulador):
> ```python
> import formulas, warnings; warnings.filterwarnings("ignore")
> sol = formulas.ExcelModel().loads(path).finish().calculate()
> for k,v in sol.items():          # keys look like "]SHEETNAME'!C25"
>     if "]SIMULADOR'!C25" in k.upper(): print(v.value[0,0])
> ```
> Perturb an input cell (openpyxl → save → recalc) to prove the model is live, not static.

If errors appear:
- `#N/A` → obs string starts with `=` (pitfall #1)
- `#REF!` → formula references a cleared/missing row
- `#VALUE!` → formula has `==` (f-string already containing `=` then wrapped in `=`)
