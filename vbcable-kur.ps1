# VB-CABLE sanal ses kablosunu indirir ve kurar.
# Bu, telefon mikrofonunun Windows'ta gercek bir mikrofon gibi gorunmesi icin gerekir.
# Yonetici hakki ister ve kurulum sonunda BILGISAYARI YENIDEN BASLATMAN gerekir.

$ErrorActionPreference = "Stop"

# --- yonetici degilsek kendini yukselt ---
$kimlik = [Security.Principal.WindowsIdentity]::GetCurrent()
$yetki  = New-Object Security.Principal.WindowsPrincipal($kimlik)
if (-not $yetki.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Yonetici olarak yeniden baslatiliyor..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList @(
        "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$PSCommandPath`""
    )
    return
}

Write-Host ""
Write-Host "=== VB-CABLE kurulumu ===" -ForegroundColor Cyan
Write-Host ""

# --- zaten kurulu mu? ---
$var = Get-CimInstance Win32_SoundDevice -ErrorAction SilentlyContinue |
       Where-Object { $_.Name -like "*CABLE*" -or $_.Name -like "*VB-Audio*" }
if ($var) {
    Write-Host "VB-CABLE zaten kurulu:" -ForegroundColor Green
    $var | ForEach-Object { Write-Host "  - $($_.Name)" }
    Write-Host ""
    Read-Host "Cikmak icin Enter"
    return
}

$gecici = Join-Path $env:TEMP "vbcable_kurulum"
New-Item -ItemType Directory -Force -Path $gecici | Out-Null
$zip = Join-Path $gecici "vbcable.zip"

$adresler = @(
    "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip",
    "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack43.zip"
)

$indi = $false
foreach ($u in $adresler) {
    try {
        Write-Host "Indiriliyor: $u"
        Invoke-WebRequest -Uri $u -OutFile $zip -UseBasicParsing -TimeoutSec 120
        if ((Get-Item $zip).Length -gt 200KB) { $indi = $true; break }
    } catch {
        Write-Host "  olmadi, sonraki adres deneniyor..." -ForegroundColor DarkYellow
    }
}

if (-not $indi) {
    Write-Host "Indirilemedi. Elle kur: https://vb-audio.com/Cable/" -ForegroundColor Red
    Start-Process "https://vb-audio.com/Cable/"
    Read-Host "Cikmak icin Enter"
    return
}

$klasor = Join-Path $gecici "paket"
Remove-Item $klasor -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip -DestinationPath $klasor -Force

$kurulum = Join-Path $klasor "VBCABLE_Setup_x64.exe"
if (-not (Test-Path $kurulum)) { $kurulum = Join-Path $klasor "VBCABLE_Setup.exe" }

Write-Host ""
Write-Host "Kurulum penceresi acilacak." -ForegroundColor Cyan
Write-Host "  -> Acilan pencerede 'Install Driver' dugmesine bas." -ForegroundColor Cyan
Write-Host "  -> Windows surucu uyarisi cikarsa 'Yukle' / 'Install' de." -ForegroundColor Cyan
Write-Host ""

Start-Process -FilePath $kurulum -Verb RunAs -Wait

Write-Host ""
Write-Host "Kurulum bitti. BILGISAYARI YENIDEN BASLAT." -ForegroundColor Green
Write-Host "Sonrasinda sunucu.py 'CABLE Input' aygitini otomatik bulacak." -ForegroundColor Green
Write-Host ""
Read-Host "Cikmak icin Enter"
