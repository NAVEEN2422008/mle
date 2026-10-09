#!/usr/bin/env python3
"""
fix_prose_encoding.py - Sanitizes scripts/expand_treatise_prose.py,
replacing any garbled unicode or replacement characters with proper HTML entities.
"""
from pathlib import Path

def main():
    path = Path("scripts/expand_treatise_prose.py")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    # Replacements for known corrupted tokens
    replacements = [
        ("CSHKP modelcommonly", "CSHKP model&mdash;commonly"),
        ("1859comparable", "1859&mdash;comparable"),
        ("2.022.0", "2.0&ndash;22.0"),
        ("10150", "10&ndash;150"),
        ("2.022.0 keV", "2.0&ndash;22.0 keV"),
        ("10150 keV", "10&ndash;150 keV"),
        ("F5.1F5.7", "F5.1&ndash;F5.7"),
        ("16:4017:20", "16:40&ndash;17:20"),
        ("22:0522:40", "22:05&ndash;22:40"),
        ("12:0512:50", "12:05&ndash;12:50"),
        ("01:1001:45", "01:10&ndash;01:45"),
        ("400800", "400&ndash;800"),
        ("1012", "10&ndash;12"),
        ("815", "8&ndash;15"),
        ("TSS ~ 0.700.85", "TSS ~ 0.70&ndash;0.85"),
        ("r ~ 0.800.85", "r ~ 0.80&ndash;0.85"),
        ("Zeitschrift fr Physik", "Zeitschrift f&uuml;r Physik"),
        ("Spitzer, L., & Hrm, R.", "Spitzer, L., & H&auml;rm, R."),
        ("Veronig, A. M., Vrnak, B.", "Veronig, A. M., Vr&scaron;nak, B."),
        ("along closed field linesa fundamental", "along closed field lines&mdash;a fundamental"),
        ("loop footpointsa fundamental", "loop footpoints&mdash;a fundamental"),
        ("evaporationa fundamental", "evaporation&mdash;a fundamental"),
        ("superflaresActive Regions", "superflares&mdash;Active Regions"),
    ]

    for old, new in replacements:
        text = text.replace(old, new)

    # Any remaining replacement character \ufffd can be replaced by &mdash; or &ndash;
    # Let's check if there are remaining \ufffd
    text = text.replace("\ufffd\ufffd", "&mdash;")
    text = text.replace("\ufffd", "&ndash;")

    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    print("[OK] expand_treatise_prose.py successfully sanitized and saved with UTF-8 encoding.")

if __name__ == "__main__":
    main()
