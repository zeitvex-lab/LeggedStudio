@echo off
cd /d "C:\Users\31560\Documents\00_open\legged_studio"
set LOG=logs\daily_check.log
echo [%date% %time%] === daily check === >> "%LOG%"
git status --porcelain | findstr /r "." >nul 2>&1
if errorlevel 1 (echo [git] clean >> "%LOG%") else (echo [git] DIRTY - uncommitted changes >> "%LOG%")
for /f "delims=" %%i in ('git describe --tags --abbrev^=0 2^>nul') do echo [git] latest tag: %%i >> "%LOG%"
uv run --no-sync python -m unittest discover -s backend -p "test_*.py" > logs\test_last.log 2>&1
if errorlevel 1 (echo [test] FAIL - see logs/test_last.log >> "%LOG%") else (echo [test] PASS >> "%LOG%")
echo [plan] next: follow docs/EXECUTION_PLAN.md >> "%LOG%"
