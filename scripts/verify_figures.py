"""Verify every figure in paper/figures/ renders real content.

A figure "looks fine" in a file listing but can still be blank, or be drawn
from hardcoded numbers. This checks both:

  1. ink: fraction of non-background pixels per panel (a blank panel has ~0)
  2. provenance: does the generating function read the FITS archives, or
     contain hardcoded metric arrays?
"""
from __future__ import annotations

import ast
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "paper" / "figures"
GEN = ROOT / "paper" / "generate_figures.py"

# Keys are file STEMS (no extension). They previously carried ".png" while the
# lookup used png.stem, so every multi-panel figure silently fell back to the
# whole-image check and "0 blank panels" meant nothing for 2x2 layouts.
PANELS = {
    "figure1_lightcurves": (4, 1),
    "figure2_neupert_scatter": (2, 2),
    "figure3_band_sweep": (2, 2),
    "figure6_data_gap": (3, 1),
    "figure10_energy_bands": (1, 1),
}

# Figures withdrawn because no evidence supports them. If any of these files
# reappears, the verification fails loudly rather than letting it be cited.
WITHHELD = {
    "figure4_ablation": "no ablation code exists in src/forecast/",
    "figure5_feature_importance": "no saved importance artifact",
    "figure7_ml_comparison": "hardcoded bars, no saved predictions",
    "figure8_roc_reliability": "np.random simulation, no saved predictions",
    "figure9_lt_far": "underlying lt_far_table is degenerate (POD=0, FAR=1)",
}

INK_FLOOR = 1.0  # percent; below this a panel is effectively blank


def panel_ink(path: Path, rows: int, cols: int) -> list[list[float]]:
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    H, W, _ = a.shape
    out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            y0, y1 = int(r * H / rows) + 20, int((r + 1) * H / rows) - 20
            x0, x1 = int(c * W / cols) + 20, int((c + 1) * W / cols) - 20
            q = a[y0:y1, x0:x1].reshape(-1, 3)
            row.append(100.0 * float((np.abs(q - 255).sum(axis=1) > 12).mean()))
        out.append(row)
    return out


def provenance() -> dict[str, str]:
    """Classify each generator as reading real archives or using literals."""
    tree = ast.parse(GEN.read_text(encoding="utf-8"))
    res = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("generate_figure"):
            continue
        # get_source_segment needs the exact source; read once per call is fine
        # for a 1k-line file and keeps the AST as the single source of truth.
        src = ast.get_source_segment(GEN.read_text(encoding="utf-8"), node) or ""
        name = node.name[len("generate_"):]
        reads_fits = any(t in src for t in ("read_slx_zip", "read_hel1os_zip", "_open("))
        has_random = "np.random" in src
        has_lit_list = any(
            isinstance(n, ast.Assign) and isinstance(n.value, ast.List)
            and len(n.value.elts) >= 3 and all(isinstance(e, ast.Constant) for e in n.value.elts)
            for n in ast.walk(node)
        )
        if reads_fits:
            kind = "REAL DATA"
        elif has_random:
            kind = "SIMULATED (np.random)"
        elif has_lit_list:
            kind = "HARDCODED numbers"
        else:
            kind = "schematic/illustrative"
        res[name] = kind
    return res


def _schematic_checks_against_manifest() -> list[str]:
    """A schematic is allowed to hardcode numbers, but only if they match the
    instrument facts recorded in data/verified_metrics.json, which were read
    from the FITS EXTNAME strings."""
    out: list[str] = []
    manifest_path = ROOT / "data" / "verified_metrics.json"
    if not manifest_path.exists():
        return ["FAIL figure10: data/verified_metrics.json missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        facts = manifest["instrument_facts_verified_from_fits"]
    except Exception as exc:  # noqa: BLE001
        return [f"FAIL figure10: cannot read manifest ({exc})"]

    src = GEN.read_text(encoding="utf-8")
    for det, key in (("CDTE", "CDTE2_channels_keV"), ("CZT", "CZT1_channels_keV")):
        expected = [tuple(ch) for ch in facts[key]]
        for lo, hi in expected:
            token = f"({lo:g}, {hi:g})"
            if token not in src:
                out.append(
                    f"FAIL figure10: {det} channel {lo:g}-{hi:g} keV (from FITS) "
                    f"is not drawn in the figure"
                )
    if not out:
        out.append(
            "figure10_energy_bands: schematic energies match "
            "data/verified_metrics.json (read from FITS EXTNAMEs)"
        )
    return out


def main() -> int:
    print("=" * 78)
    print("FIGURE VERIFICATION")
    print("=" * 78)

    prov = provenance()

    print("\n[1] RENDERING - per-panel ink coverage (blank panels read ~0%)")
    print("-" * 78)
    blanks = []
    for png in sorted(FIG.glob("*.png")):
        stem = png.stem
        if stem not in PANELS:
            im = Image.open(png).convert("RGB")
            a = np.asarray(im).reshape(-1, 3).astype(int)
            ink = 100.0 * float((np.abs(a - 255).sum(axis=1) > 12).mean())
            flag = "  <== BLANK" if ink < INK_FLOOR else ""
            print(f"  {stem:<34} ink={ink:7.3f}%{flag}")
            if ink < INK_FLOOR:
                blanks.append(stem)
        else:
            rows, cols = PANELS[stem]
            inks = panel_ink(png, rows, cols)
            cells = []
            for r, row in enumerate(inks):
                for c, v in enumerate(row):
                    cells.append(f"[{r},{c}]={v:6.2f}%")
                    if v < INK_FLOOR:
                        blanks.append(f"{stem}[{r},{c}]")
            print(f"  {stem:<34} " + " ".join(cells))

    print("\n[2] PROVENANCE - is the figure drawn from the FITS archives?")
    print("-" * 78)
    for k in sorted(prov):
        v = prov[k]
        if k in WITHHELD:
            print(f"  {k:<36} {v}  (withheld - generator still present)")
            continue
        mark = "" if v == "REAL DATA" else "  <== CHECK BELOW"
        print(f"  {k:<36} {v}{mark}")

    print("\n[2b] SCHEMATIC CROSS-CHECK against verified_metrics.json")
    print("-" * 78)
    schematic_failures = []
    for line in _schematic_checks_against_manifest():
        print(f"  {line}")
        if line.startswith("FAIL"):
            schematic_failures.append(line)

    print("\n[3] WITHHELD FIGURES - these must NOT exist on disk")
    print("-" * 78)
    leaked = []
    for stem, why in sorted(WITHHELD.items()):
        present = [p.name for p in FIG.glob(f"{stem}.*")]
        if present:
            leaked.append(stem)
            print(f"  {stem:<34} PRESENT {present}  <== MUST BE REMOVED ({why})")
        else:
            print(f"  {stem:<34} absent (correct) - {why}")

    print("\n" + "=" * 78)
    print(f"blank panels: {len(blanks)}" + (f" -> {blanks}" if blanks else " (none)"))
    print(f"withheld figures present: {len(leaked)}" + (f" -> {leaked}" if leaked else " (none)"))
    print(f"schematic cross-check failures: {len(schematic_failures)}"
          + (f" -> {schematic_failures}" if schematic_failures else " (none)"))
    print("=" * 78)
    return 1 if (blanks or leaked or schematic_failures) else 0


if __name__ == "__main__":
    sys.exit(main())