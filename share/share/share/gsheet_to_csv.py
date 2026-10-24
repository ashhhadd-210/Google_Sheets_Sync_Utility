r"""Pull all (or selected) tabs of a Google Sheet to CSV via your logged-in Chrome.

WHY THIS APPROACH
  No service account, no API key, no GCP project, no Workspace-admin approval.
  It attaches to YOUR already-running Chrome over the DevTools port and downloads
  each tab through Google's public CSV export endpoint using your own browser
  session. Any private sheet you can open in the browser, this can export — which
  is exactly what the "app-style" access paths (service-account share, personal
  GCP, gcloud SDK) are blocked from doing.

SETUP (once)
  pip install playwright

RUN
  1) Close ALL Chrome windows.
  2) Launch Chrome with the debug port + a dedicated profile (stays logged in):
        chrome.exe --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome-debug-profile"
     (first time, sign into Google in that window)
  3) Open your Google Sheet in that Chrome window.
  4) Run:
        py -3.14 gsheet_to_csv.py --sheet-id <SHEET_ID> --out ./data

ARGUMENTS
  --sheet-id   the long ID from the URL:  docs.google.com/spreadsheets/d/<SHEET_ID>/edit
  --out        folder to write CSVs into (default ./sheet_csv)
  --only       comma-separated tab names to export (default: every readable tab)
  --cdp        Chrome DevTools endpoint (default http://127.0.0.1:9222)

OUTPUT
  One CSV per tab:  <TabName>__gid<gid>.csv
  A manifest:       sync_manifest.json  (timestamps + per-tab byte counts)
  Writes are atomic (temp file + os.replace) and a tab that errors NEVER
  overwrites a previously-good CSV.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


def gid_from_url(url: str) -> str | None:
    m = re.search(r"gid=(\d+)", url)
    return m.group(1) if m else None


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:60]


def atomic_write(target: Path, body: bytes) -> None:
    """Temp file + fsync + os.replace, so a partial/failed write never corrupts."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".g2c-",
                                     suffix=".tmp", delete=False) as tmp:
        tmp.write(body)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name
    os.replace(tmp_name, target)


def sync_once(sheet_id: str, out_dir: Path, cdp_url: str, only: set[str] | None) -> dict:
    started = datetime.now(timezone.utc)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{started.isoformat(timespec='seconds')}] connecting to Chrome at {cdp_url}")

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(cdp_url)

        # Find the tab where the target Sheet is open.
        page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if sheet_id in p.url:
                    page = p
                    break
            if page:
                break
        if not page:
            raise SystemExit(
                f"Sheet (id {sheet_id}) is not open in the CDP-attached Chrome.\n"
                f"Open it in the debug-port Chrome window first, then re-run."
            )

        page.bring_to_front()
        n_tabs = len(page.locator(".docs-sheet-tab").all())
        print(f"  found {n_tabs} tab elements on the Sheet")

        # Click each tab to read its name + capture its gid from the URL.
        pairs: list[tuple[str, str]] = []
        skipped: list[dict] = []
        for i in range(n_tabs):
            tabs = page.locator(".docs-sheet-tab").all()
            if i >= len(tabs):
                break
            tab = tabs[i]
            try:
                name = tab.locator(".docs-sheet-tab-name").first.inner_text(timeout=2000).strip()
            except Exception as e:
                skipped.append({"index": i, "reason": f"name_unreadable: {e!r}"})
                continue
            if only and name not in only:
                continue
            try:
                tab.click(force=True, timeout=4000)
                page.wait_for_timeout(700)
                gid = gid_from_url(page.url)
                if gid:
                    pairs.append((name, gid))
                    print(f"  tab {i}: {name!r}  gid={gid}")
                else:
                    skipped.append({"index": i, "name": name, "reason": "no_gid_in_url"})
            except Exception as e:
                skipped.append({"index": i, "name": name, "reason": f"click_failed: {str(e)[:120]}"})
                print(f"  tab {i}: {name!r}  SKIPPED ({str(e)[:80]})")

        # Export each tab via the public CSV endpoint, using the browser's
        # authenticated request context (so private-sheet auth carries over).
        request_ctx = page.context.request
        manifest_tabs = []

        def fetch_csv(url: str) -> tuple[bytes, str | None]:
            resp = request_ctx.get(url, max_redirects=5, timeout=30000)
            body = resp.body()
            head = body[:200].lstrip().lower()
            if head.startswith(b"<!doctype") or head.startswith(b"<html"):
                reason = "rate_limited" if b"too many requests" in body[:1024].lower() else "html_error_page"
                return body, reason
            return body, None

        for i, (name, gid) in enumerate(pairs):
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
            try:
                if i > 0:
                    time.sleep(2.5)  # pace requests to stay under Google's rate limit
                body, err = fetch_csv(url)
                if err:
                    print(f"[retry] {name!r}: {err} — waiting 12s then retrying once")
                    time.sleep(12)
                    body, err = fetch_csv(url)
                if err:
                    print(f"[fail] {name!r}: {err} after retry; keeping previous CSV if any")
                    skipped.append({"name": name, "reason": f"export_{err}"})
                    continue
                dest = out_dir / f"{safe_name(name)}__gid{gid}.csv"
                atomic_write(dest, body)
                print(f"[ok] {dest.name}  ({len(body):,} bytes)")
                manifest_tabs.append({"name": name, "gid": gid, "file": dest.name, "bytes": len(body)})
            except Exception as e:
                print(f"[fail] {name!r}: {e}")
                skipped.append({"name": name, "reason": f"export_failed: {str(e)[:120]}"})

    finished = datetime.now(timezone.utc)
    manifest = {
        "syncedAt": finished.isoformat(timespec="seconds"),
        "elapsedSec": round((finished - started).total_seconds(), 2),
        "sheetId": sheet_id,
        "tabsExported": len(manifest_tabs),
        "tabsSkipped": len(skipped),
        "tabs": manifest_tabs,
        "skipped": skipped,
    }
    atomic_write(out_dir / "sync_manifest.json",
                 json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"))
    print(f"[done] {len(manifest_tabs)} ok / {len(skipped)} skipped "
          f"in {manifest['elapsedSec']}s — manifest at {out_dir / 'sync_manifest.json'}")
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Export Google Sheet tabs to CSV via your logged-in Chrome (CDP attach).")
    ap.add_argument("--sheet-id", required=True, help="Sheet ID from the URL: .../d/<SHEET_ID>/edit")
    ap.add_argument("--out", default="./sheet_csv", help="output folder (default ./sheet_csv)")
    ap.add_argument("--only", default="", help="comma-separated tab names to export (default: all)")
    ap.add_argument("--cdp", default="http://127.0.0.1:9222", help="Chrome DevTools endpoint")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sync_once(args.sheet_id, Path(args.out), args.cdp, only)
