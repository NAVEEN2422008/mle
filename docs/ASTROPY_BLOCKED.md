# Reproducibility Note — Windows Smart App Control blocks astropy

## Status

**As of 2026-10-03 22:34:34 local time, `from astropy.io import fits` fails on this
machine.** Everything downstream that reads the FITS archives is affected.

```
ImportError: DLL load failed while importing _compression:
An Application Control policy has blocked this file.
```

## Cause

Not a code or dependency problem. Windows **Smart App Control** (code-integrity
policy `0283ac0f-fff1-49ae-ada1-8a933130cad6`, registry
`HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy\VerifiedAndReputablePolicyState = 1`)
blocked the unsigned native extension:

```
...\Python314\site-packages\astropy\io\fits\hdu\compressed\_compression.pyd
```

Event ID 3077, `Microsoft-Windows-CodeIntegrity/Operational`:

> Code Integrity determined that a process
> (`\Device\HarddiskVolume3\Python314\python.exe`) attempted to load
> `...astropy\io\fits\hdu\compressed\_compression.pyd` that did not meet the
> Enterprise signing level requirements or violated code integrity policy.

Reproduced on 4+ consecutive attempts with a 20 s gap, so it is persistent, not
transient. The `.pyd` itself is untouched (mtime 2026-06-08).

## Why this was not "worked around"

The obvious workaround — switching the machine to "Evaluation"/"Off" under
Windows Security → Smart App Control — **disables a security control
system-wide**. That is the user's decision to make, not an agent's, and it would
weaken protection on the whole machine to fix a Python import. It was therefore
not done, and no policy was modified.

A Python-level stub for the blocked module was also rejected: `_compression`
implements real FITS tile decompression, so stubbing it would risk silently
returning wrong pixel values rather than failing loudly. Silent wrong numbers in
a scientific pipeline are worse than a hard import error.

## Impact on prior verification

The full verification run that reported `53 passed` and
`ALL CHECKS PASSED` completed **before** 22:34:34 and is unaffected. Only the
post-22:34 attempts to re-run the FITS-dependent steps are blocked.

| Step | Depends on astropy | Status |
|---|---|---|
| `pytest tests/` (53 passed) | yes | verified pre-block, cannot re-run now |
| `verify_all.py` -> ALL CHECKS PASSED | yes | verified pre-block, cannot re-run now |
| `scripts/verify_figures.py` | no (reads PDFs + manifest) | **still passes** |
| `scripts/verify_paper_tex.py` | no | **still passes** |
| `scripts/check_figure2_lag.py` | no | **still passes** |
| `paper/paper.tex` text fixes | no | applied and re-verified |

## Options for the user

1. **Sign or allow-list astropy's `.pyd`** — narrowest fix, keeps Smart App
   Control enabled for everything else.
2. **Turn off Smart App Control** (Windows Security → Smart App Control →
   Off/Evaluation). Broadest and least safe; requires a reboot.
3. **Reinstall astropy** from a currently-signed wheel, if a newer build is
   signed. Worth trying first — it is non-destructive.
4. **Run the analysis on an unsilenced machine/CI runner** and commit the
   resulting artifacts, so the paper is reproducible even though this laptop
   cannot currently re-derive it.

## Reviewer-facing implication

Until astropy can load again, this checkout **cannot regenerate the figures from
raw data on this machine**. The committed figures were produced by the code in
this repo from the committed raw archives before the block; their provenance was
verified by `scripts/verify_figures.py`, which still passes. A reviewer
re-running the pipeline on a clean machine should be unaffected.

Any paper revision that changes FITS-derived numbers must wait for this to be
resolved, or be re-derived on another machine.