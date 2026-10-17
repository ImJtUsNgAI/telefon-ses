# Telefonun bilgisayara baglanabilmesi icin 8443 portunu (sadece ev agi icin) acar.
# Windows zaten ilk calistirmada bir izin penceresi cikarir; oraya "Izin ver" dersen
# bu betige gerek kalmaz. Cikmadiysa / yanlislikla reddettiysen bunu calistir.

$ErrorActionPreference = "Stop"

$kimlik = [Security.Principal.WindowsIdentity]::GetCurrent()
$yetki  = New-Object Security.Principal.WindowsPrincipal($kimlik)
if (-not $yetki.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList @(
        "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$PSCommandPath`""
    )
    return
}

$ad = "TelefonSes (8443)"
Get-NetFirewallRule -DisplayName $ad -ErrorAction SilentlyContinue | Remove-NetFirewallRule

New-NetFirewallRule -DisplayName $ad -Direction Inbound -Protocol TCP `
    -LocalPort 8443 -Action Allow -Profile Private,Domain | Out-Null

Write-Host "Kural eklendi: $ad (sadece ozel/ev agi)" -ForegroundColor Green
Read-Host "Cikmak icin Enter"
