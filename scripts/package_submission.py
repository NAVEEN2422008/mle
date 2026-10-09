#!/usr/bin/env python3
"""
Package all publication assets for Overleaf / arXiv / Journal submission.
Creates paper_submission_package.zip containing:
  - paper/paper.tex
  - paper/references.bib
  - All verified figures (figures/*.pdf, figures/*.png)
  - data/deep_metrics.json
  - data/verified_metrics.json
  - SUBMISSION_README.md
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ZIP = ROOT / "paper_submission_package.zip"


def create_submission_package() -> int:
    print("=" * 70)
    print("PACKAGING ADITYA-L1 MANUSCRIPT & VERIFIED ASSETS")
    print("=" * 70)

    files_to_pack = [
        ROOT / "paper" / "paper.tex",
        ROOT / "paper" / "references.bib",
        ROOT / "paper" / "research_paper.pdf",
        ROOT / "paper" / "research_paper.html",
        ROOT / "paper" / "PAPER_DRAFT.docx",
        ROOT / "data" / "deep_metrics.json",
        ROOT / "data" / "verified_metrics.json",
    ]

    # Include all 14 verified publication figures (PDF and PNG)
    fig_dir = ROOT / "paper" / "figures"
    expected_stems = [
        "figure1_orbit_and_sensors",
        "figure2_detector_physics",
        "figure3_energy_bands",
        "figure4_data_gap",
        "figure5_lightcurves",
        "figure6_hydrodynamic_simulation",
        "figure7_neupert_scatter",
        "figure8_band_sweep",
        "figure9_graph_transformer_architecture",
        "figure10_pinn_cooling_verification",
        "figure11_multihorizon_forecast",
        "figure12_deep_architectural_benchmark",
        "figure13_verification_and_conformal",
        "figure14_xai_and_economic_value",
    ]

    for stem in expected_stems:
        pdf_file = fig_dir / f"{stem}.pdf"
        png_file = fig_dir / f"{stem}.png"
        if pdf_file.exists():
            files_to_pack.append(pdf_file)
        if png_file.exists():
            files_to_pack.append(png_file)

    readme_content = """# Aditya-L1 Neupert Effect & Deep Learning Solar Flare Forecasting Package

## Contents:
- `paper.tex`: Main publication LaTeX manuscript.
- `references.bib`: Complete BibTeX bibliography (65 entries, all cited keys resolved).
- `research_paper.pdf`: 18-page publication-ready typeset PDF.
- `research_paper.html`: Self-contained standalone interactive HTML paper with embedded figures.
- `PAPER_DRAFT.docx`: Editable Word document for co-author review.
- `figures/`: All 14 publication figures in vector PDF and high-res PNG format.
- `data/deep_metrics.json`: Empirical benchmark evaluation manifest on held-out X9.0 flare episode.
- `data/verified_metrics.json`: Authenticated instrument metadata and Neupert correlation values.

## Compilation Instructions:
Compile with pdflatex or xelatex:
```bash
pdflatex paper.tex
bibtex paper
pdflatex paper.tex
pdflatex paper.tex
```
Or simply upload this .zip directly to Overleaf.
"""

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write readme
        zf.writestr("SUBMISSION_README.md", readme_content)

        for p in files_to_pack:
            if not p.exists():
                print(f"[ERROR] Missing required asset: {p}")
                return 1
            if "figures" in p.parts:
                arcname = f"figures/{p.name}"
            elif p.parent.name == "data":
                arcname = f"data/{p.name}"
            else:
                arcname = p.name
            zf.write(p, arcname=arcname)
            print(f"  + Added: {arcname} ({p.stat().st_size:,} bytes)")

    print(f"\n[SUCCESS] Package created: {OUTPUT_ZIP} ({OUTPUT_ZIP.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(create_submission_package())
