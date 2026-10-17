@echo off
chcp 65001 >nul
title Telefon Ses - SADECE TELEFON modu
cd /d "%~dp0"

echo.
echo  SADECE TELEFON modu
echo  --------------------------------------------------
echo  Windows'un varsayilan ses cikisi sanal kabloya alinir,
echo  ses yalnizca telefondan calar. Kulaklik acik olmasa da
echo  calisir. Pencereyi kapatinca eski aygita geri donulur.
echo.
echo  (Sanal kablo yoksa once vbcable-kur.ps1 calistir.)
echo.

python sunucu.py --sanal %*
echo.
pause
