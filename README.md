# Google Sheets to CSV sync through your own Chrome

A small command-line tool that pulls every tab of a private Google Sheet into CSV files so a
dashboard can read them, without a service account, an API key, a GCP project or any admin
approval. It drives the Chrome you are already signed into, so any sheet you can open in the
browser, it can export. It runs on a Windows workstation and is meant to be scheduled.

I wrote it for an internal reporting team whose Google Workspace DLP policy blocks the usual
API routes (service-account shares, personal GCP projects, the gcloud SDK). I built the
exporter, the Chrome launcher and the guide that ships with them.

## What it does

**For the person refreshing a dashboard**
- Launch Chrome with one double-click, open the sheet, run one command: every readable tab
  becomes a CSV named `<TabName>__gid<gid>.csv` in the folder you choose
- Export only the tabs you need with `--only "MASTER,Summary"`
- A `sync_manifest.json` records when the sync ran, how long it took, and the byte count of
  every tab, plus a list of anything that was skipped and why
- Can be wrapped in a `.bat` and pointed at Windows Task Scheduler for unattended refreshes

**For the dashboard that consumes the files**
- Plain CSVs in a fixed folder; the dashboard's data layer needs no change beyond the path
- A tab that fails never overwrites a previously good CSV, so a hiccup cannot corrupt a report

## How it works

- **Attaches to your real browser:** Chrome starts with `--remote-debugging-port=9222` and a
  dedicated profile; Playwright connects with `connect_over_cdp`, so your Google session is
  reused and nothing has to be shared with a robot account
- **Finds the tabs by clicking them:** it locates the browser tab where the sheet is open,
  reads the tab strip, clicks each sheet tab and captures its `gid` from the URL
- **Downloads through the authenticated context:** each tab is fetched from Google's
  `export?format=csv&gid=` endpoint using the page's own request context, so private-sheet
  auth carries over
- **Safe writes:** temp file, `fsync`, then `os.replace`, so a CSV is either the old complete
  file or the new complete file, never half-written
- **Rate-limit aware:** 2.5 s between tabs, detects Google's "too many requests" HTML page,
  waits 12 s and retries once, then keeps the previous file if it still fails

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3 (developed on 3.14) |
| Browser automation | Playwright (Python), attached over the Chrome DevTools Protocol |
| Browser | The user's installed Google Chrome with a dedicated debug profile |
| Launcher | Windows batch file (`start_chrome_debug.bat`) |
| Output | CSV per tab plus a JSON manifest |

## Running it locally

```
pip install playwright                                   # no "playwright install" needed
share\share\share\start_chrome_debug.bat                 # close all Chrome windows first
                                                         # sign in to Google, open the sheet
cd share\share\share
py -3.14 gsheet_to_csv.py --sheet-id <SHEET_ID> --out .\data
py -3.14 gsheet_to_csv.py --sheet-id <SHEET_ID> --only "MASTER,Summary" --out .\data
```

The sheet ID is the long string in the URL: `docs.google.com/spreadsheets/d/<SHEET_ID>/edit`.
There is no `.env`; the tool uses your browser session and stores no credentials.
`README_sheet_sync.md` next to the script has the troubleshooting table.

## Repository notes

- The canonical files are in `share/share/share/` (`gsheet_to_csv.py`,
  `start_chrome_debug.bat`, `README_sheet_sync.md`). `share.zip` is the same three files as
  they were originally handed over.
- No screenshots: the tool is a console script with no UI of its own.
