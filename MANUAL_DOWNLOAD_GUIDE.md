# Manual Download Guide for Aditya-L1 Data from PRADAN

## Overview
The PRADAN portal (https://pradan.issdc.gov.in/al1/) has session expiration issues that prevent full automation. This guide provides step-by-step instructions for manual download of additional Aditya-L1 SoLEXS/HEL1OS paired events.

## Current Status
**Already Downloaded & Analyzed (5 pairs):**
| Date | Flare | SoLEXS | HEL1OS | Status |
|------|-------|--------|--------|--------|
| 2024-05-10 | X3.9 | ✅ | ⚠️ (starts after peak) | Analyzed |
| 2024-05-11 | X5.8 | ✅ | ✅ | Analyzed |
| 2024-05-14 | X8.7 | ✅ | ✅ | Analyzed |
| 2024-10-01 | X7.1 | ✅ | ✅ | Analyzed |
| 2024-10-03 | X9.0 | ✅ | ✅ | Analyzed |

**Target:** Download 25-50 more paired events for HXR ablation study.

## Manual Download Procedure

### 1. Login to PRADAN
1. Go to: https://pradan.issdc.gov.in/al1/
2. Click "Browse and Download" → Select "HEL1OS" or "SoLEXS"
3. Log in with your ISRO credentials

### 2. Filter for Specific Date Range
For each instrument:

**HEL1OS:**
1. Go to: https://pradan.issdc.gov.in/al1/protected/browse.xhtml?id=hel1os
2. Set filter:
   - ObservationTime → "In"
   - From: `2024-05-01 00:00:00`
   - To: `2024-05-31 23:59:59` (for May 2024)
   - Or: `2024-10-01 00:00:00` to `2024-10-31 23:59:59` (for Oct 2024)
3. Click "Filter"

**SoLEXS:**
1. Go to: https://pradan.issdc.gov.in/al1/protected/browse.xhtml?id=solexs
2. Set same filter as above
3. Click "Filter"

### 3. Bulk Download (Recommended)
**For each instrument after filtering:**
1. Click **"Select, Zip and DOWNLOAD (max 1024.0MB data)"** button
2. Wait for zip file to generate
3. Save as: `hel1os_may2024.zip` or `solexs_may2024.zip`
2. Extract to `data/raw/`

### 4. Alternative: Select and Download in Bulk with Script
1. Click **"Select and Download in Bulk with Script"**
2. This generates a shell script with wget/curl commands
3. Run the script to download all files

## Target Dates for Additional Downloads

### Priority 1: May 2024 (X-class flares)
| Date | Flare Class | Notes |
|------|-------------|-------|
| 2024-05-01 to 2024-05-31 | Multiple | Already have 5/10, need 5 more |

### Priority 2: October 2024 (X-class flares)
| Date | Flare Class | Notes |
|------|-------------|-------|
| 2024-10-01 to 2024-10-31 | X7.1, X9.0 | Already have 2/2 |

### Priority 3: Other months with X/M-class flares
Check NOAA flare catalog for:
- 2024-01 to 2024-12: All X-class and M-class flares
- Focus on dates where both SoLEXS and HEL1OS have data

## Expected File Counts (Estimated)
| Instrument | May 2024 | Oct 2024 | Other months |
|------------|----------|----------|--------------|
| SoLEXS | ~31 files | ~31 files | ~31/month |
| HEL1OS | ~30+ files | ~30+ files | ~30/month |

## File Naming Patterns
**SoLEXS:** `AL1_SLX_L1_YYYYMMDD_v1.0.zip`
**HEL1OS:** `HLS_YYYYMMDD_HHMMSS_XXXXsec_lev1_V111.zip`

## Post-Download Processing
After downloading and extracting to `data/raw/`:
```bash
# Run Neupert analysis on new data
python scripts/neupert_analysis.py --raw data/raw --band CZT2 --sweep-bands

# Run ML evaluation
python scripts/evaluate_aditya_real.py
```

## Troubleshooting
- **Session expires:** Re-login and re-apply filters
- **Filter not working:** Clear filter and re-apply
- **Download fails:** Try "Select, Zip and DOWNLOAD" instead of individual downloads
- **Missing HEL1OS for a date:** Check if HEL1OS segment covers the flare time (some segments start after flare peak)

## Data Already Available
The following 5 pairs are already downloaded and analyzed in `data/raw/`:
- 2024-05-10 (X3.9) - HEL1OS starts after peak
- 2024-05-11 (X5.8) - Complete pair
- 2024-05-14 (X8.7) - Complete pair
- 2024-10-01 (X7.1) - Complete pair
- 2024-10-03 (X9.0) - Complete pair

## Next Steps for HXR Ablation Study
1. Download ~25-50 more paired events
2. Run band sensitivity sweep on new data
3. Retrain ML models with expanded dataset
4. Update paper with new results

## Contact
For issues with PRADAN portal: Check FAQ at https://pradan.issdc.gov.in/al1/faq.xhtml