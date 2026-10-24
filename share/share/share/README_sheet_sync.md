# Google Sheet → CSV sync (for dashboards)

Pull any private Google Sheet's tabs into CSV files **using your own logged-in
Chrome** — no service account, no API key, no GCP project, no Workspace-admin
approval. It attaches to your browser over the DevTools port and downloads each
tab through Google's CSV export endpoint with your session.

> **Why not the "proper" API / service account?** Our Workspace DLP policy blocks
> app-style access (service-account shares, personal GCP projects, the gcloud
> SDK). A sheet you can open in your browser, you can export this way — because
> it *is* your browser doing it.

---

## Files in this folder

| File | What it is |
|---|---|
| `gsheet_to_csv.py` | The exporter. Point it at any sheet with `--sheet-id`. |
| `start_chrome_debug.bat` | Launches Chrome with the debug port + a dedicated profile. |
| `README_sheet_sync.md` | This guide. |

---

## One-time setup

1. Install Python 3 (we use 3.14) and Playwright:
   ```
   pip install playwright
   ```
   *(You do **not** need `playwright install` — we attach to your real Chrome, not a bundled browser.)*

2. Find your **Sheet ID** — it's the long string in the URL:
   ```
   https://docs.google.com/spreadsheets/d/<THIS_IS_THE_SHEET_ID>/edit#gid=0
   ```

---

## Every time you want to refresh

1. **Close all Chrome windows.**
2. Double-click **`start_chrome_debug.bat`** (first run: sign into Google in that window).
3. In that Chrome window, **open your Google Sheet.**
4. Run the exporter:
   ```
   py -3.14 gsheet_to_csv.py --sheet-id YOUR_SHEET_ID --out ./data
   ```

That's it. You'll get one CSV per tab in `./data` plus a `sync_manifest.json`
with timestamps and byte counts.

### Useful options
```
--out ./data                 where to write the CSVs (default ./sheet_csv)
--only "MASTER,Summary"      export only these tab names (default: all readable)
--cdp http://127.0.0.1:9222  Chrome DevTools endpoint (rarely changed)
```

### Schedule it (optional)
Wrap the command in a `.bat` and point Windows **Task Scheduler** at it, or run it
on a loop. (Chrome must be running with the debug port for it to work.)

---

## How it works (for the curious)

1. Chrome runs with `--remote-debugging-port=9222`; Playwright attaches via
   `connect_over_cdp` — it controls the Chrome you're already signed into.
2. It finds the tab where your sheet is open, reads the tab strip, and clicks
   each tab to capture its `gid`.
3. It downloads `…/export?format=csv&gid=<gid>` through the browser's
   authenticated request context, so private-sheet auth just works.
4. Writes are **atomic** (temp file + replace) and paced (2.5s between tabs, with
   one retry on Google's rate-limit page), so a hiccup never corrupts a good CSV.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `connecting to Chrome … ` then hangs / connection refused | Chrome isn't running with the debug port. Close **all** Chrome, run `start_chrome_debug.bat`. |
| `Sheet (id …) is not open` | Open the sheet in the **debug-port** Chrome window (the one the .bat launched), not a different Chrome. |
| Debug port won't bind on newer Chrome | The `.bat` already uses `--user-data-dir` for a dedicated profile, which fixes this. Make sure no Chrome using that profile is already open. |
| A tab logs `rate_limited` | It auto-retries after 12s; if it still fails it keeps the previous CSV. Re-run later. |
| Hidden / overflow tabs `SKIPPED` | Expected — tabs that aren't clickable are skipped and listed in the manifest. |

---

## Adapting to your dashboard

The script writes plain CSVs named `<TabName>__gid<gid>.csv`. Your dashboard's
data layer should read those files. The only things you change are:
- `--sheet-id` → your sheet
- `--out` → wherever your dashboard reads its CSVs from
- `--only` → if you only need specific tabs

No code edits required.
