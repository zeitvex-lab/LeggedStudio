@echo off
REM Legged Studio - Windows Desktop Launcher

echo ============================================================
echo Legged Studio - Starting...
echo ============================================================
echo.

echo Starting Electron desktop launcher...
call npm start

echo.
echo ============================================================
echo Legged Studio closed.
echo ============================================================
echo.
echo The desktop launcher owns the backend lifecycle.
echo ============================================================
pause
