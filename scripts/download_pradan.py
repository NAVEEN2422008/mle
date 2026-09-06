"""Interactive OR headless PRADAN downloader.

Interactive (you, in your own terminal):
    python scripts/download_pradan.py

Headless (assistant-driven, reads a local two-line cred file):
    python scripts/download_pradan.py --creds PRADAN.cred \
        --start 20260810 --end 20260822 --forget

--forget deletes the credential file after downloading (recommended).
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingest.pradan_download import PradanSession


def default_range(days: int = 14):
    end = datetime.utcnow().date() - timedelta(days=2)  # portal latency margin
    start = end - timedelta(days=days)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--creds", help="path to two-line credential file "
                                    "(enables headless mode)")
    ap.add_argument("--start", help="YYYYMMDD")
    ap.add_argument("--end", help="YYYYMMDD")
    ap.add_argument("--instruments", default="both",
                    choices=["both", "solexs", "hel1os"])
    ap.add_argument("--dest", default="data/raw")
    ap.add_argument("--forget", action="store_true",
                    help="delete the cred file after download")
    args = ap.parse_args()

    print("=" * 62)
    print("PRADAN DOWNLOADER - Aditya-L1 SoLEXS / HEL1OS Level-1")
    print("=" * 62)

    if args.creds:
        sess = PradanSession.from_cred_file(args.creds)
        s, e = args.start, args.end
        if not (s and e):
            s, e = default_range()
    else:
        sess = PradanSession.from_env_or_prompt(prompt_user=True)
        s, e = ask_range_interactive(args)

    print(f"[*] Range {s} .. {e}   instruments={args.instruments}")
    print("[*] Logging in via Keycloak ...")

    if not sess.login():
        print("\n[!] LOGIN FAILED.")
        print("    - re-check username/password in the file / prompt")
        print("    - portal may have drifted: use browser Bulk Download")
        return 1
    probe = sess.whoami_check()
    print(f"[+] LOGIN OK  (auth probe: {probe['looks_authenticated']})")

    reports = {}
    if args.instruments in ("both", "solexs"):
        print("[*] SoLEXS:")
        reports["solexs"] = sess.download_solexs(s, e, dest=args.dest)
        r = reports["solexs"]
        print(f"    downloaded={r.downloaded} skipped={r.skipped_existing} "
              f"failed={len(r.failed)}")
    if args.instruments in ("both", "hel1os"):
        print("[*] HEL1OS:")
        reports["hel1os"] = sess.download_hel1os(s, e, dest=args.dest)
        r = reports["hel1os"]
        print(f"    downloaded={r.downloaded} skipped={r.skipped_existing} "
              f"failed={len(r.failed)}")

    all_failed = sorted({f for rep in reports.values() for f in rep.failed})
    if all_failed:
        print("\n[!] Failed/absent files (portal gaps or drift):")
        for f in all_failed[:12]:
            print("    ", f)
        if len(all_failed) > 12:
            print(f"     ... and {len(all_failed)-12} more")

    if args.forget and args.creds:
        try:
            Path(args.creds).unlink()
            print(f"\n[+] credential file deleted: {args.creds}")
        except Exception as ex:
            print(f"\n[!] could not delete {args.creds}: {ex} - delete manually")

    total_dl = sum(rep.downloaded for rep in reports.values())
    print(f"\n[done] new files: {total_dl} -> {args.dest}/")
    print("Next:  python scripts/run_pradan.py --raw data/raw")
    return 0


def ask_range_interactive(args) -> tuple[str, str]:
    raw = input(f"Date range YYYYMMDD:YYYYMMDD (Enter = last 14 days): ").strip()
    if raw:
        a, b = raw.split(":")
        return a.replace("-", ""), b.replace("-", "")
    return default_range()


if __name__ == "__main__":
    raise SystemExit(main())
