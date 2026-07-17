"""
build_model.py — Collection Pilot Financial Model Builder
==========================================================
Generic builder for N-band collection pilot projection spreadsheets (.xlsx).
Produces a fully formula-driven file with:
  - Sheet 1: "Dados Base"  (static reference data)
  - Sheet 2: "Projeção Piloto" (premissas + revenue + [costs] + [taxes] + [margin])

USAGE
-----
from scripts.build_model import build_model

result = build_model(
    bands=[
        {"label": "91–120", "valor": 207_611_875, "cpfs": 79_722,
         "efic": 0.0107, "fee": 0.1392},
        {"label": "121–150", "valor": 205_193_318, "cpfs": 79_326,
         "efic": 0.0072, "fee": 0.1463},
        {"label": "151–180", "valor": 200_045_695, "cpfs": 76_852,
         "efic": 0.0055, "fee": 0.1352},
    ],
    pilot_pct=0.10,
    output_path="/path/to/output.xlsx",
    title="CoralAi × Casas Bahia — Projeção de Remuneração — Piloto 10%",
    subtitle="Base: Indicadores operacionais atuais | 3 faixas — CONFIDENCIAL",
    include_costs=True,
    include_taxes=True,
)
# result = {"REM_ROW": 49, "H_TOTAL_CPFS": "H13",
#           "row_total_cost": 97, "row_total_taxes": 127}

COMMAND-LINE (quick test)
--------------------------
python scripts/build_model.py --out /tmp/test_model.xlsx

KEY DESIGN RULES
----------------
1. Never hardcode row numbers — always track with Python variables.
2. All obs/label strings must NEVER start with '=' (LibreOffice formula bug).
3. When adding bands or blocks: rebuild the sheet, don't patch.
4. Uplift references always point to fixed premissas rows
   (r_uplift_base, r_uplift_30, r_uplift_50) — never hardcode 0.30.
5. Fee and efic cells come from different premissas sections:
   efic starts at row 7+2B, fee starts at row 7+3B.
6. CRM obs string must be a plain literal (never f"={H_TOTAL_CPFS}...").
7. Validate with recalc.py after generating — expected: 0 errors.
"""

from __future__ import annotations
import argparse
from math import ceil
from typing import Optional
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── Colour palette ────────────────────────────────────────────────────────────
RED    = "D32F2F"
CREAM  = "E8E3D8"
LGRAY  = "F2F2F2"
DGRAY  = "4A4A4A"
MGRAY  = "888888"
AMBER  = "D68000"
PURPLE = "4A148C"
LPURP  = "F3E5F5"
MPURP  = "E1BEE7"
WHITE  = "FFFFFF"
BLACK  = "1A1A1A"
BLUE   = "0000FF"
PINK   = "FFE8E8"
DPINK  = "FFD0D0"
GREEN  = "1B5E20"
LGREEN = "E8F5E9"
TEAL   = "E3F2FD"

# ── Style helpers ─────────────────────────────────────────────────────────────
def _fill(c: str) -> PatternFill:
    return PatternFill("solid", fgColor=c)

def _font(bold=False, color=BLACK, size=10, italic=False) -> Font:
    return Font(name="Arial", bold=bold, color=color, size=size, italic=italic)

def _border() -> Border:
    t = Side(style="thin", color="CCCCCC")
    return Border(left=t, right=t, top=t, bottom=t)

def _al(h="left") -> Alignment:
    return Alignment(horizontal=h, vertical="center", wrap_text=True)

# ── Low-level cell writers ────────────────────────────────────────────────────
def _head(ws, row, text, col_start="B", col_end="J", bg=DGRAY, size=10):
    """Merged section header row."""
    span = f"{col_start}{row}:{col_end}{row}"
    ws.merge_cells(span)
    c = ws[f"{col_start}{row}"]
    c.value = text
    c.font = _font(bold=True, color=WHITE, size=size)
    c.fill = _fill(bg); c.alignment = _al(); c.border = _border()
    ws.row_dimensions[row].height = 22

def _inp(ws, row, label, qty, unit_cost, obs, bg=WHITE, qty_fmt="n", formula_total=None):
    """Input row for the costs block (B=label, C=qty, D=unit_cost, E=total, F=obs)."""
    ws[f"B{row}"].value = label
    ws[f"B{row}"].font = _font(); ws[f"B{row}"].fill = _fill(bg)
    ws[f"B{row}"].alignment = _al(); ws[f"B{row}"].border = _border()

    ws[f"C{row}"].value = qty
    ws[f"C{row}"].font = _font(color=BLUE); ws[f"C{row}"].fill = _fill(bg)
    ws[f"C{row}"].alignment = _al("right"); ws[f"C{row}"].border = _border()
    ws[f"C{row}"].number_format = "#,##0" if qty_fmt == "n" else "0.00%"

    ws[f"D{row}"].value = unit_cost
    ws[f"D{row}"].font = _font(color=BLUE); ws[f"D{row}"].fill = _fill(bg)
    ws[f"D{row}"].alignment = _al("right"); ws[f"D{row}"].border = _border()
    ws[f"D{row}"].number_format = "R$\\ #,##0.00"

    ws[f"E{row}"].value = formula_total if formula_total else f"=C{row}*D{row}"
    ws[f"E{row}"].font = _font(); ws[f"E{row}"].fill = _fill(bg)
    ws[f"E{row}"].alignment = _al("right"); ws[f"E{row}"].border = _border()
    ws[f"E{row}"].number_format = "R$\\ #,##0"

    ws[f"F{row}"].value = obs
    ws[f"F{row}"].font = _font(italic=True, color=DGRAY, size=9)
    ws[f"F{row}"].fill = _fill(bg); ws[f"F{row}"].alignment = _al(); ws[f"F{row}"].border = _border()
    ws.row_dimensions[row].height = 18

def _subtotal(ws, row, label, formula, bg=CREAM, bold=True, color=BLACK):
    """Subtotal row (cost block): label in B, formula in E."""
    ws[f"B{row}"].value = f"  ↳ {label}"
    ws[f"B{row}"].font = _font(bold=bold, color=color)
    ws[f"B{row}"].fill = _fill(bg); ws[f"B{row}"].alignment = _al(); ws[f"B{row}"].border = _border()
    for col in ["C", "D"]:
        ws[f"{col}{row}"].fill = _fill(bg); ws[f"{col}{row}"].border = _border()
    ws[f"E{row}"].value = formula
    ws[f"E{row}"].font = _font(bold=bold, color=color)
    ws[f"E{row}"].fill = _fill(bg); ws[f"E{row}"].alignment = _al("right"); ws[f"E{row}"].border = _border()
    ws[f"E{row}"].number_format = "R$\\ #,##0"
    ws[f"F{row}"].fill = _fill(bg); ws[f"F{row}"].border = _border()
    ws.row_dimensions[row].height = 18

def _ref_row(ws, row, label, qty, unit_cost, obs, bg=TEAL):
    """Informational reference row (TEAL, not included in totals)."""
    ws[f"B{row}"].value = f"  📖 {label}"
    ws[f"B{row}"].font = _font(italic=True, color="1565C0", size=9)
    ws[f"B{row}"].fill = _fill(bg); ws[f"B{row}"].alignment = _al(); ws[f"B{row}"].border = _border()
    ws[f"C{row}"].value = qty
    ws[f"C{row}"].font = _font(color=BLUE, size=9); ws[f"C{row}"].fill = _fill(bg)
    ws[f"C{row}"].alignment = _al("right"); ws[f"C{row}"].border = _border()
    ws[f"C{row}"].number_format = "#,##0"
    ws[f"D{row}"].value = unit_cost
    ws[f"D{row}"].font = _font(color=BLUE, size=9); ws[f"D{row}"].fill = _fill(bg)
    ws[f"D{row}"].alignment = _al("right"); ws[f"D{row}"].border = _border()
    ws[f"D{row}"].number_format = "R$\\ #,##0.00"
    ws[f"E{row}"].value = "—"
    ws[f"E{row}"].font = _font(color=MGRAY, size=9); ws[f"E{row}"].fill = _fill(bg)
    ws[f"E{row}"].alignment = _al("center"); ws[f"E{row}"].border = _border()
    ws[f"F{row}"].value = obs
    ws[f"F{row}"].font = _font(italic=True, color="1565C0", size=9)
    ws[f"F{row}"].fill = _fill(bg); ws[f"F{row}"].alignment = _al(); ws[f"F{row}"].border = _border()
    ws.row_dimensions[row].height = 16

def _calc_row(ws, row, label, formula, obs="", fmt="R$0", bg=WHITE):
    """Single-column calculated row (value only in C)."""
    ws[f"B{row}"].value = label
    ws[f"B{row}"].font = _font(); ws[f"B{row}"].fill = _fill(bg)
    ws[f"B{row}"].alignment = _al(); ws[f"B{row}"].border = _border()
    ws[f"C{row}"].value = formula
    ws[f"C{row}"].font = _font(color=BLACK); ws[f"C{row}"].fill = _fill(bg)
    ws[f"C{row}"].alignment = _al("right"); ws[f"C{row}"].border = _border()
    if fmt == "n":    ws[f"C{row}"].number_format = "#,##0"
    else:             ws[f"C{row}"].number_format = "R$\\ #,##0"
    for col in ["D", "E"]:
        ws[f"{col}{row}"].fill = _fill(bg); ws[f"{col}{row}"].border = _border()
    ws[f"F{row}"].value = obs
    ws[f"F{row}"].font = _font(italic=True, color=DGRAY, size=9)
    ws[f"F{row}"].fill = _fill(bg); ws[f"F{row}"].alignment = _al(); ws[f"F{row}"].border = _border()
    ws.row_dimensions[row].height = 18

def _inp_rate(ws, row, label, val, obs, bg=WHITE):
    """Rate input cell for the tax block (C = percentage, D/E = '—')."""
    ws[f"B{row}"].value = label
    ws[f"B{row}"].font = _font(); ws[f"B{row}"].fill = _fill(bg)
    ws[f"B{row}"].alignment = _al(); ws[f"B{row}"].border = _border()
    ws[f"C{row}"].value = val
    ws[f"C{row}"].font = _font(color=BLUE); ws[f"C{row}"].fill = _fill(bg)
    ws[f"C{row}"].number_format = "0.00%"
    ws[f"C{row}"].alignment = _al("right"); ws[f"C{row}"].border = _border()
    for col in ["D", "E"]:
        ws[f"{col}{row}"].value = "—"
        ws[f"{col}{row}"].font = _font(color="999999", size=9)
        ws[f"{col}{row}"].fill = _fill(bg)
        ws[f"{col}{row}"].alignment = _al("center"); ws[f"{col}{row}"].border = _border()
    ws[f"F{row}"].value = obs
    ws[f"F{row}"].font = _font(italic=True, color="666666", size=9)
    ws[f"F{row}"].fill = _fill(bg); ws[f"F{row}"].alignment = _al(); ws[f"F{row}"].border = _border()
    ws.row_dimensions[row].height = 17

def _inp_val(ws, row, label, val, obs, bg=WHITE):
    """Monetary input cell for the tax block."""
    ws[f"B{row}"].value = label
    ws[f"B{row}"].font = _font(); ws[f"B{row}"].fill = _fill(bg)
    ws[f"B{row}"].alignment = _al(); ws[f"B{row}"].border = _border()
    ws[f"C{row}"].value = val
    ws[f"C{row}"].font = _font(color=BLUE); ws[f"C{row}"].fill = _fill(bg)
    ws[f"C{row}"].number_format = "R$\\ #,##0"
    ws[f"C{row}"].alignment = _al("right"); ws[f"C{row}"].border = _border()
    for col in ["D", "E"]:
        ws[f"{col}{row}"].value = "—"
        ws[f"{col}{row}"].font = _font(color="999999", size=9)
        ws[f"{col}{row}"].fill = _fill(bg)
        ws[f"{col}{row}"].alignment = _al("center"); ws[f"{col}{row}"].border = _border()
    ws[f"F{row}"].value = obs
    ws[f"F{row}"].font = _font(italic=True, color="666666", size=9)
    ws[f"F{row}"].fill = _fill(bg); ws[f"F{row}"].alignment = _al(); ws[f"F{row}"].border = _border()
    ws.row_dimensions[row].height = 17

def _calc3(ws, row, label, cf, df, ef, bg=WHITE, bold=False, color=BLACK, fmt="R$0"):
    """Three-scenario calculation row (C=Baseline, D=+30%, E=+50%)."""
    ws[f"B{row}"].value = label
    ws[f"B{row}"].font = _font(bold=bold, color=color)
    ws[f"B{row}"].fill = _fill(bg); ws[f"B{row}"].alignment = _al(); ws[f"B{row}"].border = _border()
    for col, formula in zip(["C", "D", "E"], [cf, df, ef]):
        ws[f"{col}{row}"].value = formula
        ws[f"{col}{row}"].font = _font(bold=bold, color=color)
        ws[f"{col}{row}"].fill = _fill(bg)
        ws[f"{col}{row}"].alignment = _al("right"); ws[f"{col}{row}"].border = _border()
        ws[f"{col}{row}"].number_format = "R$\\ #,##0" if fmt == "R$0" else "0.00%"
    ws[f"F{row}"].fill = _fill(bg); ws[f"F{row}"].border = _border()
    ws.row_dimensions[row].height = 18

def _subtotal3(ws, row, label, cf, df, ef, bg=MPURP, color=PURPLE, bold=True):
    """Three-scenario subtotal row for the tax block."""
    ws[f"B{row}"].value = f"  ↳ {label}"
    ws[f"B{row}"].font = _font(bold=bold, color=color)
    ws[f"B{row}"].fill = _fill(bg); ws[f"B{row}"].alignment = _al(); ws[f"B{row}"].border = _border()
    for col, formula in zip(["C", "D", "E"], [cf, df, ef]):
        ws[f"{col}{row}"].value = formula
        ws[f"{col}{row}"].font = _font(bold=bold, color=color)
        ws[f"{col}{row}"].fill = _fill(bg)
        ws[f"{col}{row}"].alignment = _al("right"); ws[f"{col}{row}"].border = _border()
        ws[f"{col}{row}"].number_format = "R$\\ #,##0"
    ws[f"F{row}"].fill = _fill(bg); ws[f"F{row}"].border = _border()
    ws.row_dimensions[row].height = 18


# ── Revenue band block ────────────────────────────────────────────────────────
def _faixa_block(ws, r_start, faixa_label, cart_label,
                 efic_cell, fee_cell, carteira_ref,
                 r_uplift_base, r_uplift_30, r_uplift_50):
    """
    Write a 7-row delinquency band block.
    Returns (r_recup, r_rem, next_row).

    Row layout:
      r_start+0 : section header
      r_start+1 : uplift (references r_uplift_base / _30 / _50)
      r_start+2 : adjusted efficiency
      r_start+3 : pilot wallet (R$)
      r_start+4 : monthly recovery (R$)
      r_start+5 : success fee (%)
      r_start+6 : ★ Remuneração CoralAi  ← r_rem
    """
    # Header
    ws.merge_cells(f"B{r_start}:E{r_start}")
    ws[f"B{r_start}"].value = faixa_label
    ws[f"B{r_start}"].font = _font(bold=True, color=WHITE)
    ws[f"B{r_start}"].fill = _fill(DGRAY)
    ws[f"B{r_start}"].alignment = _al(); ws[f"B{r_start}"].border = _border()
    ws.row_dimensions[r_start].height = 18
    r = r_start + 1

    # Uplift
    ws[f"B{r}"].value = "Uplift de eficiência"
    ws[f"B{r}"].font = _font(); ws[f"B{r}"].fill = _fill(LGRAY)
    ws[f"B{r}"].alignment = _al(); ws[f"B{r}"].border = _border()
    for col, ref in [("C", f"=C{r_uplift_base}"),
                     ("D", f"=C{r_uplift_30}"),
                     ("E", f"=C{r_uplift_50}")]:
        ws[f"{col}{r}"].value = ref
        ws[f"{col}{r}"].number_format = "0.00%"
        ws[f"{col}{r}"].font = _font(); ws[f"{col}{r}"].fill = _fill(LGRAY)
        ws[f"{col}{r}"].alignment = _al("right"); ws[f"{col}{r}"].border = _border()
    r_uplift_row = r; r += 1

    # Adjusted efficiency
    ws[f"B{r}"].value = "Eficiência ajustada (%/mês)"
    ws[f"B{r}"].font = _font(); ws[f"B{r}"].fill = _fill(WHITE)
    ws[f"B{r}"].alignment = _al(); ws[f"B{r}"].border = _border()
    for col in ["C", "D", "E"]:
        ws[f"{col}{r}"].value = f"={efic_cell}*(1+{col}{r_uplift_row})"
        ws[f"{col}{r}"].number_format = "0.00%"
        ws[f"{col}{r}"].font = _font(); ws[f"{col}{r}"].fill = _fill(WHITE)
        ws[f"{col}{r}"].alignment = _al("right"); ws[f"{col}{r}"].border = _border()
    r_efic = r; r += 1

    # Pilot wallet
    ws[f"B{r}"].value = f"Carteira piloto {cart_label} (R$)"
    ws[f"B{r}"].font = _font(); ws[f"B{r}"].fill = _fill(LGRAY)
    ws[f"B{r}"].alignment = _al(); ws[f"B{r}"].border = _border()
    for col in ["C", "D", "E"]:
        ws[f"{col}{r}"].value = f"={carteira_ref}"
        ws[f"{col}{r}"].number_format = "R$\\ #,##0"
        ws[f"{col}{r}"].font = _font(); ws[f"{col}{r}"].fill = _fill(LGRAY)
        ws[f"{col}{r}"].alignment = _al("right"); ws[f"{col}{r}"].border = _border()
    r_cart = r; r += 1

    # Monthly recovery
    ws[f"B{r}"].value = "Recuperação mensal (R$)"
    ws[f"B{r}"].font = _font(); ws[f"B{r}"].fill = _fill(WHITE)
    ws[f"B{r}"].alignment = _al(); ws[f"B{r}"].border = _border()
    for col in ["C", "D", "E"]:
        ws[f"{col}{r}"].value = f"={col}{r_efic}*{col}{r_cart}"
        ws[f"{col}{r}"].number_format = "R$\\ #,##0"
        ws[f"{col}{r}"].font = _font(); ws[f"{col}{r}"].fill = _fill(WHITE)
        ws[f"{col}{r}"].alignment = _al("right"); ws[f"{col}{r}"].border = _border()
    r_recup = r; r += 1

    # Success fee
    ws[f"B{r}"].value = "Success Fee (%)"
    ws[f"B{r}"].font = _font(); ws[f"B{r}"].fill = _fill(LGRAY)
    ws[f"B{r}"].alignment = _al(); ws[f"B{r}"].border = _border()
    for col in ["C", "D", "E"]:
        ws[f"{col}{r}"].value = f"={fee_cell}"
        ws[f"{col}{r}"].number_format = "0.00%"
        ws[f"{col}{r}"].font = _font(); ws[f"{col}{r}"].fill = _fill(LGRAY)
        ws[f"{col}{r}"].alignment = _al("right"); ws[f"{col}{r}"].border = _border()
    r_fee = r; r += 1

    # Remuneração CoralAi
    ws[f"B{r}"].value = f"★ Remuneração CoralAi — {faixa_label} (R$)"
    ws[f"B{r}"].font = _font(bold=True, color=RED)
    ws[f"B{r}"].fill = _fill(PINK)
    ws[f"B{r}"].alignment = _al(); ws[f"B{r}"].border = _border()
    for col in ["C", "D", "E"]:
        ws[f"{col}{r}"].value = f"={col}{r_recup}*{col}{r_fee}"
        ws[f"{col}{r}"].number_format = "R$\\ #,##0"
        ws[f"{col}{r}"].font = _font(bold=True, color=RED)
        ws[f"{col}{r}"].fill = _fill(PINK)
        ws[f"{col}{r}"].alignment = _al("right"); ws[f"{col}{r}"].border = _border()
    r_rem = r

    return r_recup, r_rem, r_start + 7


# ── Main builder ──────────────────────────────────────────────────────────────
def build_model(
    bands: list[dict],
    pilot_pct: float = 0.10,
    output_path: str = "Projecao_Piloto.xlsx",
    title: str = "Projeção de Remuneração — Piloto",
    subtitle: str = "Modelo de projeção para operação de cobrança — CONFIDENCIAL",
    include_costs: bool = False,
    include_taxes: bool = False,
    dados_base_title: str = "Dados Base da Carteira",
    band_noun: str = "DIAS",
    costs_overrides: Optional[dict] = None,
    fixed_monthly_fee: float = 0.0,
) -> dict:
    """
    Build a collection pilot projection workbook.

    Parameters
    ----------
    bands : list of dicts, each with keys:
        label (str)  - e.g. "91–120"
        valor (float) - total wallet value in R$ (full portfolio, pre-pilot split)
        cpfs  (int)   - total CPF count (full portfolio, pre-pilot split)
        efic  (float) - current efficiency rate per month (e.g. 0.0107 = 1.07%)
        fee   (float) - success fee as decimal (e.g. 0.1392 = 13.92%)
    pilot_pct : float  - pilot allocation fraction (default 0.10 = 10%)
    output_path : str  - absolute path for the output .xlsx file
    title : str        - main title shown in row 1
    subtitle : str     - subtitle shown in row 2
    include_costs : bool  - add the operational costs block (8 sections, ~44 rows)
    include_taxes : bool  - add the Lucro Presumido tax block + margin demonstration
                            (requires include_costs=True for break-even formula)
    dados_base_title : str - title text for the "Dados Base" sheet

    Returns
    -------
    dict with keys:
        REM_ROW        : int   - row of ★★ REMUNERAÇÃO TOTAL
        H_TOTAL_CPFS   : str   - cell address of total pilot CPFs (e.g. "H13")
        row_total_cost : int   - row of CUSTO OPERACIONAL TOTAL (0 if not included)
        row_total_taxes: int   - row of TOTAL DE TRIBUTOS (0 if not included)
    """
    if include_taxes and not include_costs:
        raise ValueError("include_taxes=True requires include_costs=True")

    B = len(bands)
    if B == 0:
        raise ValueError("bands list cannot be empty")

    wb = Workbook()

    # ── Sheet 1: Dados Base ───────────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "Dados Base"
    ws1.column_dimensions["A"].width = 3
    ws1.column_dimensions["B"].width = 38
    for col in ["C", "D", "E", "F", "G"]:
        ws1.column_dimensions[col].width = 18

    ws1.merge_cells("B1:G1")
    ws1["B1"].value = dados_base_title
    ws1["B1"].font = _font(bold=True, color=WHITE, size=13)
    ws1["B1"].fill = _fill(RED); ws1["B1"].alignment = _al("center"); ws1["B1"].border = _border()
    ws1.row_dimensions[1].height = 30

    ws1.merge_cells("B2:G2")
    ws1["B2"].value = subtitle
    ws1["B2"].font = _font(italic=True, color=DGRAY, size=9)
    ws1["B2"].fill = _fill(CREAM); ws1["B2"].alignment = _al("center"); ws1["B2"].border = _border()

    # Column headers
    for col, txt in zip(["B", "C", "D", "E", "F", "G"],
                        ["Faixa", "Carteira Total (R$)", "CPFs Totais",
                         "Efic. Atual (%/mês)", "Success Fee (%)", "Observação"]):
        ws1[f"{col}4"].value = txt
        ws1[f"{col}4"].font = _font(bold=True, color=WHITE)
        ws1[f"{col}4"].fill = _fill(RED)
        ws1[f"{col}4"].alignment = _al("center"); ws1[f"{col}4"].border = _border()

    for i, band in enumerate(bands):
        r = 5 + i
        bg = PINK if i < B else LGRAY  # all bands in pilot highlighted
        _sfx = f" {band_noun.lower()}" if band_noun else ""
        ws1[f"B{r}"].value = f"{band['label']}{_sfx}  ★ FAIXA DO PILOTO"
        ws1[f"B{r}"].font = _font(bold=True, color=RED)
        ws1[f"B{r}"].fill = _fill(bg); ws1[f"B{r}"].alignment = _al(); ws1[f"B{r}"].border = _border()
        ws1[f"C{r}"].value = band["valor"]
        ws1[f"C{r}"].number_format = "R$\\ #,##0"
        ws1[f"C{r}"].font = _font(); ws1[f"C{r}"].fill = _fill(bg)
        ws1[f"C{r}"].alignment = _al("right"); ws1[f"C{r}"].border = _border()
        ws1[f"D{r}"].value = band["cpfs"]
        ws1[f"D{r}"].number_format = "#,##0"
        ws1[f"D{r}"].font = _font(); ws1[f"D{r}"].fill = _fill(bg)
        ws1[f"D{r}"].alignment = _al("right"); ws1[f"D{r}"].border = _border()
        ws1[f"E{r}"].value = band["efic"]
        ws1[f"E{r}"].number_format = "0.00%"
        ws1[f"E{r}"].font = _font(); ws1[f"E{r}"].fill = _fill(bg)
        ws1[f"E{r}"].alignment = _al("right"); ws1[f"E{r}"].border = _border()
        ws1[f"F{r}"].value = band["fee"]
        ws1[f"F{r}"].number_format = "0.00%"
        ws1[f"F{r}"].font = _font(); ws1[f"F{r}"].fill = _fill(bg)
        ws1[f"F{r}"].alignment = _al("right"); ws1[f"F{r}"].border = _border()
        ws1[f"G{r}"].value = f"Piloto {pilot_pct:.0%}"
        ws1[f"G{r}"].font = _font(color=DGRAY, italic=True, size=9)
        ws1[f"G{r}"].fill = _fill(bg); ws1[f"G{r}"].alignment = _al(); ws1[f"G{r}"].border = _border()

    # ── Sheet 2: Projeção Piloto ──────────────────────────────────────────────
    ws = wb.create_sheet("Projeção Piloto")

    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 40
    ws.column_dimensions["C"].width = 21
    ws.column_dimensions["D"].width = 21
    ws.column_dimensions["E"].width = 21
    ws.column_dimensions["F"].width = 3
    ws.column_dimensions["G"].width = 40
    ws.column_dimensions["H"].width = 21
    ws.column_dimensions["I"].width = 16
    ws.column_dimensions["J"].width = 3

    # Row 1: Title
    ws.merge_cells("B1:J1")
    ws["B1"].value = title
    ws["B1"].font = _font(bold=True, color=WHITE, size=14)
    ws["B1"].fill = _fill(RED); ws["B1"].alignment = _al("center"); ws["B1"].border = _border()
    ws.row_dimensions[1].height = 35

    # Row 2: Subtitle
    ws.merge_cells("B2:J2")
    ws["B2"].value = subtitle
    ws["B2"].font = _font(italic=True, color=DGRAY, size=9)
    ws["B2"].fill = _fill(CREAM); ws["B2"].alignment = _al("center"); ws["B2"].border = _border()

    # Row 4: Section headers
    ws.merge_cells("B4:E4")
    ws["B4"].value = "  PREMISSAS DO PILOTO (células em azul = inputs ajustáveis)"
    ws["B4"].font = _font(bold=True, color=WHITE)
    ws["B4"].fill = _fill(DGRAY); ws["B4"].alignment = _al(); ws["B4"].border = _border()
    ws.merge_cells("G4:J4")
    ws["G4"].value = f"  RESUMO — CARTEIRA DO PILOTO ({pilot_pct:.0%} de cada faixa)"
    ws["G4"].font = _font(bold=True, color=WHITE)
    ws["G4"].fill = _fill(DGRAY); ws["G4"].alignment = _al(); ws["G4"].border = _border()

    # Row 5: Column headers
    for col, txt in zip(["B", "C", "D", "E"],
                        ["Premissa", "Valor", "Unidade", "Observação"]):
        ws[f"{col}5"].value = txt
        ws[f"{col}5"].font = _font(bold=True, color=WHITE)
        ws[f"{col}5"].fill = _fill(RED)
        ws[f"{col}5"].alignment = _al("center" if col != "B" else "left")
        ws[f"{col}5"].border = _border()
    for col, txt in zip(["G", "H", "I"], ["Métrica", "Valor", "Unidade"]):
        ws[f"{col}5"].value = txt
        ws[f"{col}5"].font = _font(bold=True, color=WHITE)
        ws[f"{col}5"].fill = _fill(RED)
        ws[f"{col}5"].alignment = _al("center" if col != "G" else "left")
        ws[f"{col}5"].border = _border()
    ws.row_dimensions[5].height = 25

    # ── Premissas block (col C, rows 6+) ─────────────────────────────────────
    # Layout for B bands:
    #   C6         = % piloto
    #   C7..C(6+B) = valor por faixa
    #   C(7+B)..C(6+2B) = CPFs por faixa
    #   C(7+2B)..C(6+3B) = efic por faixa
    #   C(7+3B)..C(6+4B) = fee por faixa
    #   C(7+4B) = uplift baseline (0.00)
    #   C(8+4B) = uplift +30%
    #   C(9+4B) = uplift +50%

    def _prem_row(r, label, val, unit, obs, bg=WHITE, is_blue=True):
        ws[f"B{r}"].value = label
        ws[f"B{r}"].font = _font(); ws[f"B{r}"].fill = _fill(bg)
        ws[f"B{r}"].alignment = _al(); ws[f"B{r}"].border = _border()
        ws[f"C{r}"].value = val
        ws[f"C{r}"].font = _font(color=BLUE if is_blue else BLACK, bold=is_blue)
        ws[f"C{r}"].fill = _fill(bg)
        ws[f"C{r}"].alignment = _al("right"); ws[f"C{r}"].border = _border()
        if unit == "%":   ws[f"C{r}"].number_format = "0.00%"
        elif unit == "R$": ws[f"C{r}"].number_format = "R$\\ #,##0"
        else:              ws[f"C{r}"].number_format = "#,##0"
        ws[f"D{r}"].value = unit
        ws[f"D{r}"].font = _font(color=DGRAY); ws[f"D{r}"].fill = _fill(bg)
        ws[f"D{r}"].alignment = _al("center"); ws[f"D{r}"].border = _border()
        ws[f"E{r}"].value = obs
        ws[f"E{r}"].font = _font(color=DGRAY, italic=True, size=9)
        ws[f"E{r}"].fill = _fill(bg); ws[f"E{r}"].alignment = _al(); ws[f"E{r}"].border = _border()
        ws.row_dimensions[r].height = 18

    alt = [LGRAY, WHITE]
    r = 6
    _prem_row(r, "% da carteira no piloto", pilot_pct, "%",
              f"Piloto de {pilot_pct:.0%} de cada faixa selecionada", LGRAY); r += 1

    for i, band in enumerate(bands):
        _prem_row(r, f"Faixa {band['label']}: valor total carteira (R$)",
                  band["valor"], "R$", f"Fonte: dados fornecidos", alt[i % 2]); r += 1
    for i, band in enumerate(bands):
        _prem_row(r, f"Faixa {band['label']}: CPFs totais",
                  band["cpfs"], "n", "Fonte: dados fornecidos", alt[i % 2]); r += 1
    for i, band in enumerate(bands):
        _prem_row(r, f"Efic. s/ carteira {band['label']} (atual)",
                  band["efic"], "%", "Eficiência de recuperação mensal atual", alt[i % 2]); r += 1
    for i, band in enumerate(bands):
        _prem_row(r, f"Success Fee {band['label']} (%)",
                  band["fee"], "%", "Taxa de sucesso acordada", alt[i % 2]); r += 1

    # Row offsets for uplift references
    r_uplift_base = r
    _prem_row(r, "Uplift eficiência cenário base",  0.00, "%",
              "CoralAi = mesma eficiência atual (baseline)", LGRAY); r += 1
    r_uplift_30 = r
    _prem_row(r, "Uplift eficiência cenário +30%", 0.30, "%",
              "CoralAi: +30% vs. eficiência atual", WHITE); r += 1
    r_uplift_50 = r
    _prem_row(r, "Uplift eficiência cenário +50%", 0.50, "%",
              "CoralAi: +50% vs. eficiência atual", LGRAY); r += 1

    r_fixo_prem = 0
    if fixed_monthly_fee > 0:
        r_fixo_prem = r
        _prem_row(r, "Receita fixa mensal — piso (R$)", fixed_monthly_fee, "R$",
                  "Modelo híbrido: piso fixo mensal, independe da recuperação", WHITE); r += 1

    last_premissa_row = r - 1  # = 9 + 4*B  (ou +1 se houver piso fixo)

    # ── Summary block (col H, rows 6..) ──────────────────────────────────────
    # H6..H(5+B)      = valor piloto per faixa
    # H(6+B)          = total valor piloto
    # H(7+B)..H(6+2B) = CPFs piloto per faixa
    # H(7+2B)         = total CPFs piloto  → H_TOTAL_CPFS

    def _resumo_row(r, label, formula, unit, is_total=False, bg=None):
        bg = bg or (DPINK if is_total else (LGRAY if (r % 2 == 0) else WHITE))
        ws[f"G{r}"].value = label
        ws[f"G{r}"].font = _font(bold=is_total)
        ws[f"G{r}"].fill = _fill(bg); ws[f"G{r}"].alignment = _al(); ws[f"G{r}"].border = _border()
        ws[f"H{r}"].value = formula
        ws[f"H{r}"].font = _font(bold=is_total)
        ws[f"H{r}"].fill = _fill(bg); ws[f"H{r}"].alignment = _al("right"); ws[f"H{r}"].border = _border()
        ws[f"H{r}"].number_format = "R$\\ #,##0" if unit == "R$" else "#,##0"
        ws[f"I{r}"].value = unit
        ws[f"I{r}"].font = _font(color=DGRAY)
        ws[f"I{r}"].fill = _fill(bg); ws[f"I{r}"].alignment = _al("center"); ws[f"I{r}"].border = _border()

    # Valor por faixa: rows 6 to 5+B
    h_val_rows = []
    for i, band in enumerate(bands):
        rh = 6 + i
        _resumo_row(rh, f"Valor Carteira {band['label']} (piloto R$)",
                    f"=C{7+i}*C6", "R$")
        h_val_rows.append(f"H{rh}")

    # Total valor
    rh_total_val = 6 + B
    _resumo_row(rh_total_val, "Valor Total Carteira Piloto (R$)",
                f"=SUM(H6:H{5+B})", "R$", is_total=True)

    # CPFs por faixa: rows 7+B to 6+2B
    h_cpf_rows = []
    for i, band in enumerate(bands):
        rh = 7 + B + i
        _resumo_row(rh, f"CPFs {band['label']} (piloto)",
                    f"=C{7+B+i}*C6", "n")
        h_cpf_rows.append(f"H{rh}")

    # Total CPFs
    rh_total_cpf = 7 + 2 * B
    _resumo_row(rh_total_cpf, "Total CPFs Piloto",
                f"=SUM(H{7+B}:H{6+2*B})", "n", is_total=True)

    H_TOTAL_CPFS = f"H{rh_total_cpf}"

    # ── Revenue projection section ────────────────────────────────────────────
    # Starts 2 rows after the last premissa row
    r_proj = last_premissa_row + 3   # gap of 2 blank rows + header
    ws.merge_cells(f"B{r_proj}:J{r_proj}")
    band_labels_str = " · ".join(f"{b['label']}{(' ' + band_noun.lower()) if band_noun else ''}" for b in bands)
    ws[f"B{r_proj}"].value = (
        f"  PROJEÇÃO MENSAL — REMUNERAÇÃO (R$) | 3 CENÁRIOS: Baseline / +30% / +50%  "
        f"[{B} faixas: {band_labels_str}]"
    )
    ws[f"B{r_proj}"].font = _font(bold=True, color=WHITE, size=11)
    ws[f"B{r_proj}"].fill = _fill(DGRAY); ws[f"B{r_proj}"].alignment = _al(); ws[f"B{r_proj}"].border = _border()
    ws.row_dimensions[r_proj].height = 24

    r_ph = r_proj + 1
    for col, txt in zip(["B", "C", "D", "E"],
                        ["Métrica", "Cenário Baseline\n(Efic. Atual)",
                         "Cenário Base\n(+30% Efic.)", "Cenário Otimista\n(+50% Efic.)"]):
        ws[f"{col}{r_ph}"].value = txt
        ws[f"{col}{r_ph}"].font = _font(bold=True, color=WHITE)
        ws[f"{col}{r_ph}"].fill = _fill(RED)
        ws[f"{col}{r_ph}"].alignment = _al("center" if col != "B" else "left")
        ws[f"{col}{r_ph}"].border = _border()
    ws.row_dimensions[r_ph].height = 36

    # One block per band
    r_cur = r_ph + 1
    r_recup_rows = []
    r_rem_rows   = []

    for i, band in enumerate(bands):
        # Premissas row offsets:
        #   valor[i]  = row (7+i)  → C(7+i)
        #   cpfs[i]   = row (7+B+i) — not needed in revenue block
        #   efic[i]   = row (7+2B+i)
        #   fee[i]    = row (7+3B+i)
        #   carteira  = H(6+i)
        efic_cell    = f"C{7 + 2*B + i}"
        fee_cell     = f"C{7 + 3*B + i}"
        carteira_ref = f"H{6 + i}"

        r_recup, r_rem, r_cur = _faixa_block(
            ws, r_cur,
            faixa_label  = f"FAIXA {band['label']}{(' ' + band_noun) if band_noun else ''}",
            cart_label   = band["label"],
            efic_cell    = efic_cell,
            fee_cell     = fee_cell,
            carteira_ref = carteira_ref,
            r_uplift_base = r_uplift_base,
            r_uplift_30   = r_uplift_30,
            r_uplift_50   = r_uplift_50,
        )
        r_recup_rows.append(r_recup)
        r_rem_rows.append(r_rem)

    # Consolidado block (3 rows after bands)
    ws.merge_cells(f"B{r_cur}:E{r_cur}")
    faixa_range = f"{bands[0]['label']} A {bands[-1]['label']}{(' ' + band_noun) if band_noun else ''}"
    ws[f"B{r_cur}"].value = f"CONSOLIDADO PILOTO — {faixa_range}"
    ws[f"B{r_cur}"].font = _font(bold=True, color=WHITE, size=11)
    ws[f"B{r_cur}"].fill = _fill(RED)
    ws[f"B{r_cur}"].alignment = _al(); ws[f"B{r_cur}"].border = _border()
    ws.row_dimensions[r_cur].height = 22
    r_cur += 1

    # Recovery total
    r_recup_total = r_cur
    sum_recup_c = "+".join(f"C{r}" for r in r_recup_rows)
    sum_recup_d = "+".join(f"D{r}" for r in r_recup_rows)
    sum_recup_e = "+".join(f"E{r}" for r in r_recup_rows)
    for col, lbl in [("B", "Recuperação Total Mensal (R$)")]:
        ws[f"B{r_cur}"].value = lbl
        ws[f"B{r_cur}"].font = _font(bold=True, color=RED)
        ws[f"B{r_cur}"].fill = _fill(PINK)
        ws[f"B{r_cur}"].alignment = _al(); ws[f"B{r_cur}"].border = _border()
    for col, formula in zip(["C", "D", "E"],
                             [f"={sum_recup_c}", f"={sum_recup_d}", f"={sum_recup_e}"]):
        ws[f"{col}{r_cur}"].value = formula
        ws[f"{col}{r_cur}"].number_format = "R$\\ #,##0"
        ws[f"{col}{r_cur}"].font = _font(bold=True, color=RED)
        ws[f"{col}{r_cur}"].fill = _fill(PINK)
        ws[f"{col}{r_cur}"].alignment = _al("right"); ws[f"{col}{r_cur}"].border = _border()
    r_cur += 1

    sum_rem_c = "+".join(f"C{r}" for r in r_rem_rows)
    sum_rem_d = "+".join(f"D{r}" for r in r_rem_rows)
    sum_rem_e = "+".join(f"E{r}" for r in r_rem_rows)

    # Modelo híbrido: separa receita variável (success fee) e fixa (piso), soma no total
    if fixed_monthly_fee > 0:
        r_var = r_cur
        ws[f"B{r_var}"].value = "Receita variável — success fee (R$)"
        ws[f"B{r_var}"].font = _font(); ws[f"B{r_var}"].fill = _fill(LGRAY)
        ws[f"B{r_var}"].alignment = _al(); ws[f"B{r_var}"].border = _border()
        for col, formula in zip(["C", "D", "E"],
                                 [f"={sum_rem_c}", f"={sum_rem_d}", f"={sum_rem_e}"]):
            ws[f"{col}{r_var}"].value = formula
            ws[f"{col}{r_var}"].number_format = "R$\\ #,##0"
            ws[f"{col}{r_var}"].font = _font(); ws[f"{col}{r_var}"].fill = _fill(LGRAY)
            ws[f"{col}{r_var}"].alignment = _al("right"); ws[f"{col}{r_var}"].border = _border()
        r_cur += 1

        r_fix = r_cur
        ws[f"B{r_fix}"].value = "Receita fixa mensal — piso (R$)"
        ws[f"B{r_fix}"].font = _font(); ws[f"B{r_fix}"].fill = _fill(WHITE)
        ws[f"B{r_fix}"].alignment = _al(); ws[f"B{r_fix}"].border = _border()
        for col in ["C", "D", "E"]:
            ws[f"{col}{r_fix}"].value = f"=C{r_fixo_prem}"
            ws[f"{col}{r_fix}"].number_format = "R$\\ #,##0"
            ws[f"{col}{r_fix}"].font = _font(); ws[f"{col}{r_fix}"].fill = _fill(WHITE)
            ws[f"{col}{r_fix}"].alignment = _al("right"); ws[f"{col}{r_fix}"].border = _border()
        r_cur += 1

        rem_c, rem_d, rem_e = f"=C{r_var}+C{r_fix}", f"=D{r_var}+D{r_fix}", f"=E{r_var}+E{r_fix}"
    else:
        rem_c, rem_d, rem_e = f"={sum_rem_c}", f"={sum_rem_d}", f"={sum_rem_e}"

    # ★★ REMUNERAÇÃO TOTAL
    REM_ROW = r_cur
    ws[f"B{REM_ROW}"].value = "★★ REMUNERAÇÃO TOTAL CoralAi (R$)"
    ws[f"B{REM_ROW}"].font = _font(bold=True, color=RED, size=11)
    ws[f"B{REM_ROW}"].fill = _fill(DPINK)
    ws[f"B{REM_ROW}"].alignment = _al(); ws[f"B{REM_ROW}"].border = _border()
    ws.row_dimensions[REM_ROW].height = 22
    for col, formula in zip(["C", "D", "E"], [rem_c, rem_d, rem_e]):
        ws[f"{col}{REM_ROW}"].value = formula
        ws[f"{col}{REM_ROW}"].number_format = "R$\\ #,##0"
        ws[f"{col}{REM_ROW}"].font = _font(bold=True, color=RED, size=11)
        ws[f"{col}{REM_ROW}"].fill = _fill(DPINK)
        ws[f"{col}{REM_ROW}"].alignment = _al("right"); ws[f"{col}{REM_ROW}"].border = _border()
    r_cur += 1

    # Annualised + per-CPF rows
    ws[f"B{r_cur}"].value = "Remuneração Anualizada (R$)"
    ws[f"B{r_cur}"].font = _font(); ws[f"B{r_cur}"].fill = _fill(LGRAY)
    ws[f"B{r_cur}"].alignment = _al(); ws[f"B{r_cur}"].border = _border()
    for col in ["C", "D", "E"]:
        ws[f"{col}{r_cur}"].value = f"={col}{REM_ROW}*12"
        ws[f"{col}{r_cur}"].number_format = "R$\\ #,##0"
        ws[f"{col}{r_cur}"].font = _font(); ws[f"{col}{r_cur}"].fill = _fill(LGRAY)
        ws[f"{col}{r_cur}"].alignment = _al("right"); ws[f"{col}{r_cur}"].border = _border()
    r_cur += 1

    ws[f"B{r_cur}"].value = "Remuneração/CPF piloto (R$)"
    ws[f"B{r_cur}"].font = _font(); ws[f"B{r_cur}"].fill = _fill(WHITE)
    ws[f"B{r_cur}"].alignment = _al(); ws[f"B{r_cur}"].border = _border()
    for col in ["C", "D", "E"]:
        ws[f"{col}{r_cur}"].value = f"={col}{REM_ROW}/{H_TOTAL_CPFS}"
        ws[f"{col}{r_cur}"].number_format = "R$\\ #,##0"
        ws[f"{col}{r_cur}"].font = _font(); ws[f"{col}{r_cur}"].fill = _fill(WHITE)
        ws[f"{col}{r_cur}"].alignment = _al("right"); ws[f"{col}{r_cur}"].border = _border()
    r_cur += 1

    row_total_cost  = 0
    row_total_taxes = 0

    # ── Costs block ───────────────────────────────────────────────────────────
    if include_costs:
        co = costs_overrides or {}
        # Always starts at max(row after revenue + gap, 54)
        R = max(54, r_cur + 3)

        # Header
        ws.merge_cells(f"B{R}:F{R}")
        ws[f"B{R}"].value = (
            "  BLOCO DE CUSTOS OPERACIONAIS DO PILOTO — células azuis = inputs ajustáveis"
        )
        ws[f"B{R}"].font = _font(bold=True, color=WHITE)
        ws[f"B{R}"].fill = _fill(RED); ws[f"B{R}"].alignment = _al(); ws[f"B{R}"].border = _border()
        ws.row_dimensions[R].height = 22; R += 1

        for col, txt, aln in [
            ("B", "Item de Custo", "left"), ("C", "Qtd / Volume", "center"),
            ("D", "Custo Unitário (R$)", "center"),
            ("E", "Custo Mensal (R$)", "center"), ("F", "Fonte / Observação", "left")
        ]:
            ws[f"{col}{R}"].value = txt
            ws[f"{col}{R}"].font = _font(bold=True, color=WHITE)
            ws[f"{col}{R}"].fill = _fill(RED)
            ws[f"{col}{R}"].alignment = _al(aln); ws[f"{col}{R}"].border = _border()
        ws.row_dimensions[R].height = 26; R += 1

        # Section 1: Human operators
        _head(ws, R, "  1. OPERADORES HUMANOS", "B", "F"); R += 1
        r_op_qty = R
        _inp(ws, R, "Qtd. de operadores (PA)", co.get("operators_qty", 10),
             co.get("operators_cost", 3500.00),
             "Remuneração + encargos (CLT ~1,7×)"); R += 1
        r_op_sub = R
        _subtotal(ws, R, "Subtotal Operadores Humanos", f"=C{r_op_qty}*D{r_op_qty}"); R += 1

        # Section 2: Operational staff (conditional on operators > 0)
        _head(ws, R, "  2. STAFF OPERACIONAL  ⚠ Zerado automaticamente se Qtd. operadores = 0",
              "B", "F"); R += 1
        r_st1 = R; _inp(ws, R, "Coordenador(es)",      1, 7000.00, "Qtd. × custo/mês (CLT ~1,7×)"); R += 1
        r_st2 = R; _inp(ws, R, "Supervisor(es)",       1, 5500.00, "Qtd. × custo/mês", LGRAY); R += 1
        r_st3 = R; _inp(ws, R, "Treinamento (amort.)", 1, 800.00,  "Custo de treinamento amortizado/mês"); R += 1
        r_st_sub = R
        _subtotal(ws, R, "Subtotal Staff Operacional (condicional)",
                  f"=IF(C{r_op_qty}>0,SUM(E{r_st1}:E{r_st3}),0)")
        ws[f"F{R}"].value = "⚠ Zerado se modelo 100% digital"
        ws[f"F{R}"].font = _font(italic=True, color=AMBER, size=9)
        ws[f"F{R}"].fill = _fill(CREAM); ws[f"F{R}"].alignment = _al(); ws[f"F{R}"].border = _border()
        R += 1

        # Section 3: Voice bot
        _head(ws, R, "  3. BOT DE VOZ  (regra: 1 bot por 3.000 CPFs — Ebook Alavancas)",
              "B", "F"); R += 1
        r_cpf_per_bot = R
        _inp(ws, R, "CPFs por bot (parâmetro operacional)", co.get("cpf_per_bot", 3000), 0,
             "1 bot para cada 3.000 CPFs da carteira piloto", LGRAY)
        ws[f"D{R}"].value = ""; ws[f"E{R}"].value = ""; R += 1

        _calc_row(ws, R, "Total CPFs piloto (referência)",
                  f"={H_TOTAL_CPFS}",
                  # ⚠ Pitfall #1: obs must NOT start with '=' — use a literal string
                  f"Vinculado à carteira piloto ({H_TOTAL_CPFS})", "n"); R += 1

        r_bv_qty = R
        _calc_row(ws, R, "Qtd. de bots necessários (calculado)",
                  f"=CEILING({H_TOTAL_CPFS}/C{r_cpf_per_bot},1)",
                  f"CEILING(CPFs_piloto / 3.000)", "n", LGRAY)
        ws[f"C{R}"].number_format = "#,##0"; R += 1

        r_bv_cost = R
        _bot_cost = co.get("bot_cost", 2000.00)
        _inp(ws, R, "Custo operacional/bot/mês", 1, _bot_cost,
             "Fonte: Ebook Alavancas — Custo Op. Mês agente digital (R$2.000)")
        ws[f"C{R}"].value = 1; ws[f"D{R}"].value = _bot_cost
        ws[f"E{R}"].value = f"=C{r_bv_qty}*D{r_bv_cost}"
        ws[f"E{R}"].number_format = "R$\\ #,##0"; R += 1

        r_bv_sub = R
        _subtotal(ws, R, "Subtotal Bot de Voz", f"=E{r_bv_cost}"); R += 1

        # Section 4: Telecom
        _head(ws, R, "  4. TELECOM  (Fonte: Ebook Alavancas — Matriz Capacidade, pág. 7)",
              "B", "F"); R += 1
        _ref_row(ws, R, "Ref. ebook: Chamadas/PA-mês (humano)", 9084, 0.004,
                 "1 PA humano = 9.084 chamadas/mês"); R += 1
        r_tc_h_cost = R
        _ref_row(ws, R, "Ref. ebook: Custo telefonia/PA-mês (humano)", 1, 872.00,
                 "1 PA humano = R$872/mês de telefonia (Ebook, pág. 7)"); R += 1

        r_tc_h_total = R
        ws[f"B{R}"].value = "Total telecom humano"
        ws[f"B{R}"].font = _font(); ws[f"B{R}"].fill = _fill(WHITE)
        ws[f"B{R}"].alignment = _al(); ws[f"B{R}"].border = _border()
        ws[f"C{R}"].value = f"=C{r_op_qty}"; ws[f"C{R}"].number_format = "#,##0"
        ws[f"C{R}"].font = _font(); ws[f"C{R}"].fill = _fill(WHITE)
        ws[f"C{R}"].alignment = _al("right"); ws[f"C{R}"].border = _border()
        ws[f"D{R}"].value = 872; ws[f"D{R}"].number_format = "R$\\ #,##0.00"
        ws[f"D{R}"].font = _font(color=BLUE); ws[f"D{R}"].fill = _fill(WHITE)
        ws[f"D{R}"].alignment = _al("right"); ws[f"D{R}"].border = _border()
        ws[f"E{R}"].value = f"=IF(C{r_op_qty}>0,C{r_op_qty}*D{r_tc_h_total},0)"
        ws[f"E{R}"].number_format = "R$\\ #,##0"
        ws[f"E{R}"].font = _font(); ws[f"E{R}"].fill = _fill(WHITE)
        ws[f"E{R}"].alignment = _al("right"); ws[f"E{R}"].border = _border()
        ws[f"F{R}"].value = "Vinculado à qtd. de operadores — zerado se modelo digital"
        ws[f"F{R}"].font = _font(italic=True, color=DGRAY, size=9)
        ws[f"F{R}"].fill = _fill(WHITE); ws[f"F{R}"].alignment = _al(); ws[f"F{R}"].border = _border()
        ws.row_dimensions[R].height = 18; R += 1

        _ref_row(ws, R, "Ref. ebook: Chamadas/bot-mês (agente digital)", 12350, 0.004,
                 "1 agente digital = 12.350 chamadas/mês"); R += 1
        _ref_row(ws, R, "Ref. ebook: Custo telefonia/bot-mês (digital)", 1, 1186.00,
                 "1 agente digital = R$1.186/mês de telefonia (Ebook, pág. 7)"); R += 1

        r_tc_d_total = R
        ws[f"B{R}"].value = "Total telecom digital (bots)"
        ws[f"B{R}"].font = _font(); ws[f"B{R}"].fill = _fill(LGRAY)
        ws[f"B{R}"].alignment = _al(); ws[f"B{R}"].border = _border()
        ws[f"C{R}"].value = f"=C{r_bv_qty}"; ws[f"C{R}"].number_format = "#,##0"
        ws[f"C{R}"].font = _font(); ws[f"C{R}"].fill = _fill(LGRAY)
        ws[f"C{R}"].alignment = _al("right"); ws[f"C{R}"].border = _border()
        ws[f"D{R}"].value = 1186; ws[f"D{R}"].number_format = "R$\\ #,##0.00"
        ws[f"D{R}"].font = _font(color=BLUE); ws[f"D{R}"].fill = _fill(LGRAY)
        ws[f"D{R}"].alignment = _al("right"); ws[f"D{R}"].border = _border()
        ws[f"E{R}"].value = f"=C{r_bv_qty}*D{r_tc_d_total}"
        ws[f"E{R}"].number_format = "R$\\ #,##0"
        ws[f"E{R}"].font = _font(); ws[f"E{R}"].fill = _fill(LGRAY)
        ws[f"E{R}"].alignment = _al("right"); ws[f"E{R}"].border = _border()
        # ⚠ Pitfall #1: obs starts with H_TOTAL_CPFS — write as literal, NOT f"={H_TOTAL_CPFS}..."
        ws[f"F{R}"].value = f"Vinculado à qtd. de bots (CEILING({H_TOTAL_CPFS}/3.000))"
        ws[f"F{R}"].font = _font(italic=True, color=DGRAY, size=9)
        ws[f"F{R}"].fill = _fill(LGRAY); ws[f"F{R}"].alignment = _al(); ws[f"F{R}"].border = _border()
        ws.row_dimensions[R].height = 18; R += 1

        r_tc_sub = R
        _subtotal(ws, R, "Subtotal Telecom", f"=E{r_tc_h_total}+E{r_tc_d_total}"); R += 1

        # Section 5: CRM
        _head(ws, R, "  5. CRM / PLATAFORMA DE COBRANÇA", "B", "F"); R += 1
        r_crm1 = R
        _inp(ws, R, "Licença CRM (fixo/mês)", 1, co.get("crm_license", 2500.00),
             "Custo fixo da plataforma CRM"); R += 1
        r_crm2 = R
        # ⚠ Pitfall #1: obs MUST be a literal string — must NOT start with '='
        _inp(ws, R, "Custo por CPF ativo/mês", 1, co.get("crm_per_cpf", 0.15),
             f"Qtd. vinculada ao total de CPFs piloto ({H_TOTAL_CPFS}) × R$0,15/CPF", LGRAY)
        ws[f"C{R}"].value = f"={H_TOTAL_CPFS}"
        ws[f"C{R}"].number_format = "#,##0"
        ws[f"E{R}"].value = f"=C{R}*D{R}"
        ws[f"E{R}"].number_format = "R$\\ #,##0"; R += 1
        r_crm_sub = R
        _subtotal(ws, R, "Subtotal CRM", f"=SUM(E{r_crm1}:E{r_crm2})"); R += 1

        # Section 6: Mass comms
        _head(ws, R, "  6. COMUNICAÇÕES MASSIVAS — SMS / RCS / WhatsApp", "B", "F"); R += 1
        r_sms = R; _inp(ws, R, "SMS",                   co.get("sms_vol", 40000), 0.085, "Vol. disparos/mês × custo unitário"); R += 1
        r_rcs = R; _inp(ws, R, "RCS",                   co.get("rcs_vol", 20000), 0.18,  "Vol. disparos/mês × custo unitário", LGRAY); R += 1
        r_wpp = R; _inp(ws, R, "WhatsApp (HSM/sessão)", co.get("wpp_vol", 25000), 0.25,  "Vol. mensagens/mês × custo unitário"); R += 1
        r_mass_sub = R
        _subtotal(ws, R, "Subtotal Massivas (SMS + RCS + WhatsApp)",
                  f"=SUM(E{r_sms}:E{r_wpp})"); R += 1

        # Section 7: Platform
        _head(ws, R, "  7. PLATAFORMA / INFRAESTRUTURA", "B", "F"); R += 1
        r_p1 = R; _inp(ws, R, "Plataforma de orquestração", 1, co.get("platform_orch", 3500.00), "Licença/uso da plataforma"); R += 1
        r_p2 = R; _inp(ws, R, "Infraestrutura cloud (proporcional)", 1, co.get("platform_cloud", 1200.00), "Custo proporcional ao piloto", LGRAY); R += 1
        r_plat_sub = R
        _subtotal(ws, R, "Subtotal Plataforma", f"=SUM(E{r_p1}:E{r_p2})"); R += 1

        # Section 8: Support staff
        _head(ws, R, "  8. STAFF DE SUPORTE (Planejamento / Control Desk / MIS)", "B", "F"); R += 1
        r_s1 = R; _inp(ws, R, "Planejamento operacional", 1, co.get("support_planning", 6000.00), "Analista de planejamento"); R += 1
        r_s2 = R; _inp(ws, R, "Control Desk / Qualidade", 1, co.get("support_controldesk", 5000.00), "Monitor/analista de qualidade", LGRAY); R += 1
        r_s3 = R; _inp(ws, R, "MIS / BI / Dados",         1, co.get("support_mis", 6500.00), "Analista MIS/BI dedicado ao piloto"); R += 1
        r_sup_sub = R
        _subtotal(ws, R, "Subtotal Staff Suporte", f"=SUM(E{r_s1}:E{r_s3})"); R += 2

        # Total costs
        row_total_cost = R
        ws.merge_cells(f"B{R}:D{R}")
        ws[f"B{R}"].value = "★★ CUSTO OPERACIONAL TOTAL MENSAL (R$)"
        ws[f"B{R}"].font = _font(bold=True, color=WHITE, size=11)
        ws[f"B{R}"].fill = _fill(DGRAY); ws[f"B{R}"].alignment = _al(); ws[f"B{R}"].border = _border()
        ws.row_dimensions[R].height = 24
        formula_total = (
            f"=E{r_op_sub}+E{r_st_sub}+E{r_bv_sub}+"
            f"E{r_tc_sub}+E{r_crm_sub}+E{r_mass_sub}+"
            f"E{r_plat_sub}+E{r_sup_sub}"
        )
        ws[f"E{R}"].value = formula_total
        ws[f"E{R}"].number_format = "R$\\ #,##0"
        ws[f"E{R}"].font = _font(bold=True, color=WHITE, size=11)
        ws[f"E{R}"].fill = _fill(DGRAY)
        ws[f"E{R}"].alignment = _al("right"); ws[f"E{R}"].border = _border()
        ws[f"F{R}"].fill = _fill(DGRAY); ws[f"F{R}"].border = _border()
        R += 2

        # Footnote row
        ws.merge_cells(f"B{R}:J{R}")
        ws[f"B{R}"].value = (
            f"📖 Fonte telecom: Ebook Alavancas — Matriz de Capacidade Instalada (pág. 7) | "
            f"1 PA humano = R$872/mês | 1 Agente Digital = R$1.186/mês | "
            f"Bot de voz: 1 bot por 3.000 CPFs | Total CPFs piloto: {H_TOTAL_CPFS}."
        )
        ws[f"B{R}"].font = _font(italic=True, size=9, color="1565C0")
        ws[f"B{R}"].fill = _fill(TEAL)
        ws[f"B{R}"].alignment = Alignment(wrap_text=True, horizontal="left", vertical="center")
        ws[f"B{R}"].border = _border()
        ws.row_dimensions[R].height = 36
        R += 2

        # ── Tax block (Lucro Presumido) ───────────────────────────────────────
        if include_taxes:
            T = R

            # Title
            ws.merge_cells(f"B{T}:J{T}")
            ws[f"B{T}"].value = (
                "  BLOCO FISCAL — REGIME LUCRO PRESUMIDO (serviços de cobrança — Brasil)"
            )
            ws[f"B{T}"].font = _font(bold=True, color=WHITE, size=11)
            ws[f"B{T}"].fill = _fill(PURPLE); ws[f"B{T}"].alignment = _al(); ws[f"B{T}"].border = _border()
            ws.row_dimensions[T].height = 24; T += 1

            _head(ws, T,
                  "  A. PREMISSAS FISCAIS — células azuis = inputs ajustáveis  |  Regime: Lucro Presumido",
                  "B", "J", bg=PURPLE); T += 1

            # Column headers
            for col, txt in zip(["B", "C", "D", "E", "F"],
                                 ["Tributo / Parâmetro", "Alíquota / Valor",
                                  "Cenário", "Cenário", "Fonte / Observação"]):
                ws[f"{col}{T}"].value = txt
                ws[f"{col}{T}"].font = _font(bold=True, color=WHITE, size=9)
                ws[f"{col}{T}"].fill = _fill("7B1FA2")
                ws[f"{col}{T}"].alignment = _al("center" if col != "B" else "left")
                ws[f"{col}{T}"].border = _border()
            ws[f"D{T}"].value = "Aplica-se a todos os cenários (mesma alíquota)"
            ws[f"D{T}"].font = _font(italic=True, color="999999", size=8)
            ws.merge_cells(f"D{T}:F{T}")
            ws[f"D{T}"].alignment = _al(); ws.row_dimensions[T].height = 20; T += 1

            _head(ws, T,
                  "  A1. TRIBUTOS SOBRE RECEITA BRUTA (antes do resultado)",
                  "B", "J", bg="7B1FA2"); T += 1

            r_iss = T; _inp_rate(ws, T, "ISS — Imposto Sobre Serviços (Municipal)", 0.05,
                                  "2%–5% conforme município; serviços de cobrança geralmente 5%",
                                  LPURP); T += 1
            r_pis = T; _inp_rate(ws, T, "PIS — Prog. Integração Social (cumulativo)", 0.0065,
                                  "0,65% no Lucro Presumido (regime cumulativo)"); T += 1
            r_cof = T; _inp_rate(ws, T, "COFINS (cumulativo)", 0.03,
                                  "3,00% no Lucro Presumido (regime cumulativo)", LPURP); T += 1

            # Subtotal rate
            ws[f"B{T}"].value = "  ↳ Total % tributos sobre receita (ISS+PIS+COFINS)"
            ws[f"B{T}"].font = _font(bold=True, color=PURPLE); ws[f"B{T}"].fill = _fill(MPURP)
            ws[f"B{T}"].alignment = _al(); ws[f"B{T}"].border = _border()
            ws[f"C{T}"].value = f"=C{r_iss}+C{r_pis}+C{r_cof}"
            ws[f"C{T}"].font = _font(bold=True, color=PURPLE); ws[f"C{T}"].fill = _fill(MPURP)
            ws[f"C{T}"].number_format = "0.00%"; ws[f"C{T}"].alignment = _al("right"); ws[f"C{T}"].border = _border()
            ws[f"D{T}"].value = "Alíquota única — varia apenas o valor R$ por cenário"
            ws[f"D{T}"].font = _font(italic=True, color="666666", size=9)
            ws.merge_cells(f"D{T}:F{T}")
            ws[f"D{T}"].fill = _fill(MPURP); ws[f"D{T}"].alignment = _al(); ws[f"D{T}"].border = _border()
            r_subtotal_rate = T; ws.row_dimensions[T].height = 17; T += 1

            _head(ws, T,
                  "  A2. IRPJ + CSLL — BASE DE PRESUNÇÃO SOBRE RECEITA BRUTA",
                  "B", "J", bg="7B1FA2"); T += 1

            r_pres = T; _inp_rate(ws, T, "Base de presunção s/ receita bruta (serviços)", 0.32,
                                   "32% é a base presumida padrão p/ serviços (RIR/1999)", LPURP); T += 1
            r_irpj = T; _inp_rate(ws, T, "Alíquota IRPJ", 0.15,
                                   "15% sobre base presumida"); T += 1
            r_adic = T; _inp_rate(ws, T, "Adicional IRPJ (excedente do limite mensal)", 0.10,
                                   "10% sobre base que exceder o limite mensal", LPURP); T += 1
            r_lim  = T; _inp_val( ws, T, "Limite mensal base IRPJ p/ adicional (R$)", 20000,
                                   "R$20.000/mês = R$240.000/ano — limite legal"); T += 1
            r_csll = T; _inp_rate(ws, T, "Alíquota CSLL", 0.09,
                                   "9% sobre base presumida de 32% da receita bruta", LPURP); T += 1

            # Section B: Calculations
            _head(ws, T, "  B. CÁLCULO DOS IMPOSTOS POR CENÁRIO (valores em R$)", "B", "J",
                  bg=PURPLE); T += 1

            for col, txt in zip(["B", "C", "D", "E"],
                                 ["Descrição", "Cenário Baseline\n(Efic. Atual)",
                                  "Cenário Base\n(+30% Efic.)", "Cenário Otimista\n(+50% Efic.)"]):
                ws[f"{col}{T}"].value = txt
                ws[f"{col}{T}"].font = _font(bold=True, color=WHITE)
                ws[f"{col}{T}"].fill = _fill(PURPLE)
                ws[f"{col}{T}"].alignment = _al("center" if col != "B" else "left")
                ws[f"{col}{T}"].border = _border()
            ws[f"F{T}"].fill = _fill(PURPLE); ws[f"F{T}"].border = _border()
            ws.row_dimensions[T].height = 32; T += 1

            r_rev_ref = T
            _calc3(ws, T, "Receita bruta (remuneração) — R$",
                   f"=C{REM_ROW}", f"=D{REM_ROW}", f"=E{REM_ROW}",
                   LPURP, bold=True, color=PURPLE); T += 1

            r_iss_val = T
            _calc3(ws, T, "ISS (5% sobre receita bruta)",
                   f"=C{r_rev_ref}*C{r_iss}", f"=D{r_rev_ref}*C{r_iss}", f"=E{r_rev_ref}*C{r_iss}"); T += 1

            r_pis_val = T
            _calc3(ws, T, "PIS (0,65% sobre receita bruta)",
                   f"=C{r_rev_ref}*C{r_pis}", f"=D{r_rev_ref}*C{r_pis}", f"=E{r_rev_ref}*C{r_pis}",
                   LPURP); T += 1

            r_cof_val = T
            _calc3(ws, T, "COFINS (3% sobre receita bruta)",
                   f"=C{r_rev_ref}*C{r_cof}", f"=D{r_rev_ref}*C{r_cof}", f"=E{r_rev_ref}*C{r_cof}"); T += 1

            r_sub_ipc = T
            _subtotal3(ws, T, "Subtotal ISS + PIS + COFINS",
                       f"=SUM(C{r_iss_val}:C{r_cof_val})",
                       f"=SUM(D{r_iss_val}:D{r_cof_val})",
                       f"=SUM(E{r_iss_val}:E{r_cof_val})"); T += 1

            r_base_pres = T
            _calc3(ws, T, "Base de presunção IRPJ/CSLL (32% × receita bruta)",
                   f"=C{r_rev_ref}*C{r_pres}", f"=D{r_rev_ref}*C{r_pres}", f"=E{r_rev_ref}*C{r_pres}",
                   LPURP, color="666666"); T += 1

            r_irpj_val = T
            _calc3(ws, T, "IRPJ (15% × base de presunção)",
                   f"=C{r_base_pres}*C{r_irpj}",
                   f"=D{r_base_pres}*C{r_irpj}",
                   f"=E{r_base_pres}*C{r_irpj}"); T += 1

            r_adic_val = T
            _calc3(ws, T, "Adicional IRPJ (10% sobre base acima de R$20.000/mês)",
                   f"=MAX(0,(C{r_base_pres}-C{r_lim})*C{r_adic})",
                   f"=MAX(0,(D{r_base_pres}-C{r_lim})*C{r_adic})",
                   f"=MAX(0,(E{r_base_pres}-C{r_lim})*C{r_adic})",
                   LPURP); T += 1

            r_csll_val = T
            _calc3(ws, T, "CSLL (9% × base de presunção)",
                   f"=C{r_base_pres}*C{r_csll}",
                   f"=D{r_base_pres}*C{r_csll}",
                   f"=E{r_base_pres}*C{r_csll}"); T += 1

            r_sub_irpj_csll = T
            _subtotal3(ws, T, "Subtotal IRPJ + Adicional + CSLL",
                       f"=SUM(C{r_irpj_val}:C{r_csll_val})",
                       f"=SUM(D{r_irpj_val}:D{r_csll_val})",
                       f"=SUM(E{r_irpj_val}:E{r_csll_val})"); T += 1

            row_total_taxes = T
            ws[f"B{T}"].value = "  ↳ TOTAL DE TRIBUTOS (ISS+PIS+COFINS+IRPJ+CSLL)"
            ws[f"B{T}"].font = _font(bold=True, color=PURPLE, size=11)
            ws[f"B{T}"].fill = _fill(PURPLE); ws[f"B{T}"].alignment = _al(); ws[f"B{T}"].border = _border()
            for col, formula in zip(["C", "D", "E"],
                                     [f"=C{r_sub_ipc}+C{r_sub_irpj_csll}",
                                      f"=D{r_sub_ipc}+D{r_sub_irpj_csll}",
                                      f"=E{r_sub_ipc}+E{r_sub_irpj_csll}"]):
                ws[f"{col}{T}"].value = formula
                ws[f"{col}{T}"].number_format = "R$\\ #,##0"
                ws[f"{col}{T}"].font = _font(bold=True, color=WHITE, size=11)
                ws[f"{col}{T}"].fill = _fill(PURPLE)
                ws[f"{col}{T}"].alignment = _al("right"); ws[f"{col}{T}"].border = _border()
            ws[f"F{T}"].fill = _fill(PURPLE); ws[f"F{T}"].border = _border()
            ws.row_dimensions[T].height = 24; T += 2

            # ── Margin demonstration ──────────────────────────────────────────
            ws.merge_cells(f"B{T}:J{T}")
            ws[f"B{T}"].value = "  DEMONSTRATIVO DE MARGEM LÍQUIDA"
            ws[f"B{T}"].font = _font(bold=True, color=WHITE, size=11)
            ws[f"B{T}"].fill = _fill(GREEN); ws[f"B{T}"].alignment = _al(); ws[f"B{T}"].border = _border()
            ws.row_dimensions[T].height = 24; T += 1

            for col, txt in zip(["B", "C", "D", "E"],
                                 ["Métrica", "Cenário Baseline", "Cenário +30%", "Cenário Otimista"]):
                ws[f"{col}{T}"].value = txt
                ws[f"{col}{T}"].font = _font(bold=True, color=WHITE)
                ws[f"{col}{T}"].fill = _fill(GREEN)
                ws[f"{col}{T}"].alignment = _al("center" if col != "B" else "left")
                ws[f"{col}{T}"].border = _border()
            ws.row_dimensions[T].height = 20; T += 1

            def _marg_row(r, label, cf, df, ef, bg=LGREEN, bold=False, color=BLACK):
                ws[f"B{r}"].value = label
                ws[f"B{r}"].font = _font(bold=bold, color=color)
                ws[f"B{r}"].fill = _fill(bg); ws[f"B{r}"].alignment = _al(); ws[f"B{r}"].border = _border()
                for col, formula in zip(["C", "D", "E"], [cf, df, ef]):
                    ws[f"{col}{r}"].value = formula
                    ws[f"{col}{r}"].font = _font(bold=bold, color=color)
                    ws[f"{col}{r}"].fill = _fill(bg)
                    ws[f"{col}{r}"].alignment = _al("right"); ws[f"{col}{r}"].border = _border()
                    ws[f"{col}{r}"].number_format = "R$\\ #,##0"
                ws.row_dimensions[r].height = 18

            r_m_rec = T
            _marg_row(T, "( + ) Receita bruta",
                      f"=C{REM_ROW}", f"=D{REM_ROW}", f"=E{REM_ROW}"); T += 1
            r_m_cus = T
            _marg_row(T, "( - ) Custos operacionais totais",
                      f"=-E{row_total_cost}", f"=-E{row_total_cost}", f"=-E{row_total_cost}",
                      LGRAY); T += 1
            r_m_tri = T
            _marg_row(T, "( - ) Total de tributos",
                      f"=-C{row_total_taxes}", f"=-D{row_total_taxes}", f"=-E{row_total_taxes}"); T += 1

            r_m_net = T
            _marg_row(T, "( = ) MARGEM LÍQUIDA (R$)",
                      f"=C{r_m_rec}+C{r_m_cus}+C{r_m_tri}",
                      f"=D{r_m_rec}+D{r_m_cus}+D{r_m_tri}",
                      f"=E{r_m_rec}+E{r_m_cus}+E{r_m_tri}",
                      bg=LGREEN, bold=True, color=GREEN); T += 1

            r_m_pct = T
            ws[f"B{T}"].value = "( = ) Margem líquida (%)"
            ws[f"B{T}"].font = _font(bold=True, color=GREEN)
            ws[f"B{T}"].fill = _fill(LGREEN); ws[f"B{T}"].alignment = _al(); ws[f"B{T}"].border = _border()
            for col, net_row in zip(["C", "D", "E"], [r_m_net, r_m_net, r_m_net]):
                rev_col = col
                ws[f"{col}{T}"].value = f"={col}{r_m_net}/{rev_col}{r_m_rec}"
                ws[f"{col}{T}"].number_format = "0.00%"
                ws[f"{col}{T}"].font = _font(bold=True, color=GREEN)
                ws[f"{col}{T}"].fill = _fill(LGREEN)
                ws[f"{col}{T}"].alignment = _al("right"); ws[f"{col}{T}"].border = _border()
            ws.row_dimensions[T].height = 18; T += 1

            # Break-even row (uses only ISS+PIS+COFINS — no IRPJ/CSLL at break-even)
            T += 1
            ws.merge_cells(f"B{T}:J{T}")
            # Weighted fee formula across all bands
            fee_terms = "+".join(
                f"C{7+3*B+i}*H{6+i}" for i in range(B)
            )
            total_cart = f"H{6+B}"
            fee_w = f"({fee_terms})/{total_cart}"
            tax_r = f"(C{r_iss}+C{r_pis}+C{r_cof})"
            if fixed_monthly_fee > 0:
                be_txt = (
                    f"Break-even da parte variável (piso cobre custos primeiro): "
                    f"=MAX(0; E{row_total_cost}-C{r_fixo_prem}*(1-{tax_r}))/({fee_w}*(1-{tax_r})) "
                    f"— se o piso já cobre os custos, o break-even variável é zero."
                )
            else:
                be_txt = (
                    f"Break-even (custos cobertos sem lucro): "
                    f"=E{row_total_cost}/({fee_w}*(1-{tax_r}))"
                )
            ws[f"B{T}"].value = be_txt
            ws[f"B{T}"].font = _font(italic=True, size=9, color="333333")
            ws[f"B{T}"].fill = _fill(CREAM); ws[f"B{T}"].alignment = _al(); ws[f"B{T}"].border = _border()
            ws.row_dimensions[T].height = 28

    # Save
    wb.save(output_path)

    print(f"✓ Saved: {output_path}")
    print(f"  REM_ROW={REM_ROW}, H_TOTAL_CPFS={H_TOTAL_CPFS}")
    print(f"  row_total_cost={row_total_cost}, row_total_taxes={row_total_taxes}")

    return {
        "REM_ROW": REM_ROW,
        "H_TOTAL_CPFS": H_TOTAL_CPFS,
        "row_total_cost": row_total_cost,
        "row_total_taxes": row_total_taxes,
    }


# ── CLI quick-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a collection pilot model (.xlsx)")
    parser.add_argument("--out", default="/tmp/test_model.xlsx", help="Output path")
    parser.add_argument("--costs", action="store_true", help="Include costs block")
    parser.add_argument("--taxes", action="store_true", help="Include tax block")
    args = parser.parse_args()

    bands = [
        {"label": "91–120",  "valor": 207_611_875, "cpfs": 79_722, "efic": 0.0107, "fee": 0.1392},
        {"label": "121–150", "valor": 205_193_318, "cpfs": 79_326, "efic": 0.0072, "fee": 0.1463},
        {"label": "151–180", "valor": 200_045_695, "cpfs": 76_852, "efic": 0.0055, "fee": 0.1352},
    ]
    result = build_model(
        bands=bands,
        pilot_pct=0.10,
        output_path=args.out,
        title="Piloto de Cobrança — Projeção de Remuneração (Teste)",
        subtitle="Modelo genérico — 3 faixas de inadimplência — CONFIDENCIAL",
        include_costs=args.costs,
        include_taxes=args.taxes,
    )
    print(f"\nAnchors: {result}")
