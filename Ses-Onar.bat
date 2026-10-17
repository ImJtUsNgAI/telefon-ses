@echo off
chcp 65001 >nul
title Windows sesini onar
echo.
echo  Windows ses motorunu yeniden baslatir.
echo  Hicbir aygittan ses gelmiyorsa / ses aygitlari kaybolduysa kullan.
echo  Yonetici izni ister (UAC penceresi cikacak).
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile','-Command','Restart-Service AudioEndpointBuilder -Force; Start-Sleep 3'"
echo.
echo  Servisler yeniden baslatildi. Ses aygitlari:
powershell -NoProfile -Command "Start-Sleep 3; Get-CimInstance Win32_SoundDevice | Select-Object -ExpandProperty Name"
echo.
pause
