@echo off
chcp 65001 >nul
title Telefon Ses - sunucu
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python bulunamadi. https://python.org adresinden kur.
  pause
  exit /b 1
)

python sunucu.py %*
echo.
pause
