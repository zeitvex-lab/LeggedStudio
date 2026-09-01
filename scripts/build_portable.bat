@echo off
setlocal
cd /d "%~dp0.."
echo Legged Studio portable release builder
call npm ci
if errorlevel 1 exit /b %errorlevel%
call npm run build:portable
exit /b %errorlevel%
