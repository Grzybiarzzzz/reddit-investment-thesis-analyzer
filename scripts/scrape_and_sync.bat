@echo off
REM Run locally via Task Scheduler or double-click.
REM Scrapes Reddit, then pushes the updated DB to GitHub
REM Analysis and tracking can then be started manually in GitHub Actions.

cd /d "%~dp0.."

call venv\Scripts\activate.bat

echo === Pulling latest from GitHub ===
git pull
if errorlevel 1 (
    echo Pull failed! Resolve conflicts before scraping.
    pause
    exit /b 1
)

echo === Scraping Reddit ===
python main.py scrape
if errorlevel 1 (
    echo Scraping failed!
    pause
    exit /b 1
)

echo === Syncing database to GitHub ===
git add reddit_stocks.db
git commit -m "data: daily scrape %date:~0,10%"
git push

echo === Done. Start Analyze ^& Track manually in GitHub Actions when needed. ===
pause
