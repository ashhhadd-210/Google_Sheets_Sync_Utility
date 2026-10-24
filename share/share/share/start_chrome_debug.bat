@echo off
REM ============================================================================
REM  Launch Chrome with the DevTools debug port so the sheet exporter can attach.
REM  Uses a DEDICATED profile so it works even if your normal Chrome is open and
REM  so newer Chrome builds don't ignore the flag. First run: sign into Google in
REM  this window (it remembers you afterwards).
REM ============================================================================

set CHROME_EXE="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME_EXE% set CHROME_EXE="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

start "" %CHROME_EXE% --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome-debug-profile"

echo.
echo Chrome launched with CDP debug port 9222 (profile: %USERPROFILE%\chrome-debug-profile).
echo   1) Sign into Google in this window (first time only).
echo   2) Open your Google Sheet.
echo   3) Run:  py -3.14 gsheet_to_csv.py --sheet-id YOUR_SHEET_ID --out ./data
echo.
