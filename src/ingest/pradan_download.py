"""PRADAN bulk downloader - real Keycloak auth flow (discovered 2026-08).

Auth chain (verified from live portal HTML):
  1. GET  https://pradan1.issdc.gov.in/al1/protected/payload.xhtml
        -> 302 to Keycloak: https://idp.issdc.gov.in/auth/realms/issdc/...
        -> login page whose <form action="...login-actions/authenticate?session_code=...">
           carries dynamic session_code/execution/client_id params
  2. POST that action with username/password/credentialId=''/login='Sign In'
        -> 302 back into PRADAN with an authenticated session cookie

Credentials are NEVER hardcoded: read from env (AL1_PRADAN_USER/PASS) or
prompted via getpass by scripts/download_pradan.py.

If any step drifts, the browser Bulk Download route still works - everything
downstream only needs zips inside data/raw/.
"""
from __future__ import annotations

import getpass
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

BASE = "https://pradan1.issdc.gov.in/al1"
LOGIN_PAGE = f"{BASE}/protected/payload.xhtml"
UA = {"User-Agent": "Mozilla/5.0 (AdityaFlareCast research downloader)"}

SOLEXS_TAG = "SLX"
HEL1OS_TAG = "HLD"


@dataclass
class DownloadReport:
    requested_days: int = 0
    downloaded: int = 0
    skipped_existing: int = 0
    failed: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class PradanSession:
    def __init__(self, user: str, password: str, timeout_s: int = 60) -> None:
        if requests is None:
            raise RuntimeError("`pip install requests` required.")
        self.user, self.password = user, password
        self.timeout_s = timeout_s
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.logged_in = False

    # ------------- construction -------------

    @classmethod
    def from_cred_file(cls, path: str | Path = "PRADAN.cred") -> "PradanSession":
        """Read credentials from a two-line local file (line1=user, line2=pass).

        The file is expected to be created by the user themselves; helpers
        must delete it after use (--forget in scripts/download_pradan.py).
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(
                f"{p} not found. Create it with exactly two lines: "
                "username, then password."
            )
        lines = [ln.rstrip("\r\n") for ln in
                 p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(lines) < 2:
            raise ValueError(f"{p} must contain TWO non-empty lines "
                             "(username, password).")
        user, pw = lines[0].strip(), lines[1].strip()
        bad = (user.lower().startswith("your_")
               or pw.lower().startswith("your_"))
        if bad:
            raise ValueError(f"{p} still contains the template placeholders - "
                             "replace them with real credentials first.")
        return cls(user, pw)

    @classmethod
    def from_env_or_prompt(cls, prompt_user: bool = False) -> "PradanSession":
        user = os.environ.get("AL1_PRADAN_USER", "")
        pw = os.environ.get("AL1_PRADAN_PASS", "")
        if prompt_user or not user:
            user = input("PRADAN username/email: ").strip()
        if prompt_user or not pw:
            pw = getpass.getpass("PRADAN password (hidden): ")
        return cls(user, pw)

    # ------------- auth -------------

    def login(self) -> bool:
        # Step 1: hit protected page -> follow to Keycloak login form
        r = self.s.get(LOGIN_PAGE, timeout=self.timeout_s)
        m = re.search(r'<form[^>]*action="([^"]+)"', r.text, re.I | re.S)
        if not m:
            print("[pradan] no login form found (maybe already logged in?)")
            self.logged_in = "logout" in r.text.lower() or "sign out" in r.text.lower()
            return self.logged_in
        action = m.group(1).replace("&amp;", "&")

        # Step 2: POST credentials to the dynamic action
        r2 = self.s.post(
            action,
            data={"username": self.user, "password": self.password,
                  "credentialId": "", "login": "Sign In"},
            timeout=self.timeout_s, allow_redirects=True,
        )
        body = r2.text.lower()
        bad = ("invalid_username_or_password" in body
               or "invalid username or password" in body
               or r2.url.endswith("/authenticate"))
        self.logged_in = (r2.ok and not bad
                          and ("logout" in body or "sign out" in body
                               or "payload" in r2.url))
        if not self.logged_in:
            hint = ("wrong credentials" if bad else
                    "unexpected post-login page - check browser route fallback")
            print(f"[pradan] LOGIN FAILED ({hint}). "
                  "Use portal Bulk Download instead; zips -> data/raw/.")
        return self.logged_in

    def whoami_check(self) -> dict:
        """Cheap probe used by --check-login."""
        r = self.s.get(LOGIN_PAGE, timeout=self.timeout_s)
        return {
            "status": r.status_code,
            "url": r.url,
            "looks_authenticated": ("logout" in r.text.lower()
                                    or "sign out" in r.text.lower()),
        }

    def __enter__(self) -> "PradanSession":
        if not self.user and not self.password:
            raise ValueError("empty credentials")
        self.login()
        return self

    def __exit__(self, *exc) -> None:
        self.s.close()

    # ------------- downloads -------------

    def _zip_name(self, tag: str, ymd: str) -> str:
        return f"AL1_{tag}_L1_{ymd}_v1.0.zip"

    def _find_zip_url(self, tag: str, ymd: str) -> Optional[str]:
        """Locate the zip on the portal for a given day.

        Strategy: probe the documented static WEBDATA layout first (fast),
        then fall back to scanning the section page HTML for the filename.
        """
        year = ymd[:4]
        candidates = [
            f"{BASE}/WEBDATA/{tag}/{year}/{self._zip_name(tag, ymd)}",
            f"{BASE}/WEBDATA/{tag}/{self._zip_name(tag, ymd)}",
        ]
        for url in candidates:
            try:
                h = self.s.head(url, timeout=self.timeout_s, allow_redirects=True)
                if h.ok and int(h.headers.get("content-length", 0)) > 1000:
                    return url
            except Exception:
                continue
        # HTML scan fallback on section page for this month
        try:
            page = self.s.get(f"{BASE}/protected/{tag.lower()}.xhtml",
                              timeout=self.timeout_s).text
            m = re.search(r'["\']([^"\']*' + self._zip_name(tag, ymd) + r')["\']', page)
            if m:
                u = m.group(1)
                return u if u.startswith("http") else f"{BASE}{u}"
        except Exception:
            pass
        return None

    def download_range(self, tag: str, start_yyyymmdd: str, end_yyyymmdd: str,
                       dest: str = "data/raw", max_retries: int = 2,
                       quiet: bool = False) -> DownloadReport:
        d0 = datetime.strptime(start_yyyymmdd, "%Y%m%d")
        d1 = datetime.strptime(end_yyyymmdd, "%Y%m%d")
        if d1 < d0:
            raise ValueError("end before start")
        Path(dest).mkdir(parents=True, exist_ok=True)
        rep = DownloadReport(requested_days=(d1 - d0).days + 1)

        day = d0
        while day <= d1:
            ymd = day.strftime("%Y%m%d")
            fname = self._zip_name(tag, ymd)
            out = Path(dest) / fname
            if out.exists() and out.stat().st_size > 1000:
                rep.skipped_existing += 1
                if not quiet:
                    print(f"  skip (exists): {fname}")
            else:
                url = self._find_zip_url(tag, ymd)
                ok = False
                if url:
                    for att in range(max_retries + 1):
                        try:
                            rr = self.s.get(url, timeout=300, stream=True)
                            ct = rr.headers.get("content-type", "")
                            if rr.ok and len(rr.content) > 1000 \
                                    and "text/html" not in ct.lower():
                                tmp = out.with_suffix(".part")
                                tmp.write_bytes(rr.content)
                                tmp.rename(out)
                                rep.downloaded += 1
                                ok = True
                                if not quiet:
                                    print(f"  OK: {fname} "
                                          f"({len(rr.content)//1024} KB)")
                                break
                        except Exception:
                            time.sleep(2 ** att)
                    if not ok:
                        rep.failed.append(fname)
                        if not quiet:
                            print(f"  FAIL: {fname}")
                else:
                    rep.failed.append(fname)
                    if not quiet:
                        print(f"  not found: {fname}")
            day += timedelta(days=1)
        return rep

    def download_solexs(self, s: str, e: str, dest: str = "data/raw") -> DownloadReport:
        return self.download_range(SOLEXS_TAG, s, e, dest)

    def download_hel1os(self, s: str, e: str, dest: str = "data/raw") -> DownloadReport:
        return self.download_range(HEL1OS_TAG, s, e, dest)
