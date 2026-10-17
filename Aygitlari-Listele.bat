@echo off
chcp 65001 >nul
title Telefon Ses - ses aygitlari
cd /d "%~dp0"
python sunucu.py --liste
pause
