param(
    [ValidateSet('oyun','sohbet','durum')]
    [string]$Mode = 'durum'
)

# ttec AirBeat Twist - ses modu degistirici
# oyun   : Stereo (A2DP) cikis  -> tam kalite ses, mikrofon YOK
# sohbet : Hands-Free (HFP)     -> mikrofon VAR, ses telefon kalitesinde
# durum  : su an hangi mod aktif

$RENDER  = '{0.0.0.00000000}.'
$CAPTURE = '{0.0.1.00000000}.'

# Endpoint GUID'leri kulaklik yeniden eslestirilince DEGISIR.
# Bu yuzden sabit yazmiyoruz; her calistirmada isimden bulup cozuyoruz.
function Find-Endpoint([string]$flow, [string]$nameLike) {
    $base   = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\$flow"
    $prefix = if ($flow -eq 'Render') { $RENDER } else { $CAPTURE }
    foreach ($k in (Get-ChildItem $base -ErrorAction SilentlyContinue)) {
        $st = (Get-ItemProperty $k.PSPath -ErrorAction SilentlyContinue).DeviceState
        if ($st -ne 1) { continue }   # 1 = ACTIVE; kapali/yok olanlari atla
        $p = Join-Path $k.PSPath 'Properties'
        if (-not (Test-Path $p)) { continue }
        $n = (Get-ItemProperty $p -ErrorAction SilentlyContinue).'{b3f8fa53-0004-438e-9003-51a46e139bfc},6'
        if ($n -like $nameLike) { return $prefix + $k.PSChildName }
    }
    return $null
}

$DEV = @{
    StereoOut = Find-Endpoint 'Render'  '*AirBeat Twist Stereo*'
    HfpOut    = Find-Endpoint 'Render'  '*AirBeat Twist Hands-Free*'
    HfpMic    = Find-Endpoint 'Capture' '*AirBeat Twist Hands-Free*'
}

if (-not $DEV.StereoOut -and -not $DEV.HfpOut) {
    Write-Host ""
    Write-Host "  ! ttec AirBeat Twist bulunamadi - kulaklik bagli mi?" -ForegroundColor Red
    Write-Host "    Kulaklgi acip Bluetooth'a baglandiktan sonra tekrar dene." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

$src = @'
using System;
using System.Runtime.InteropServices;

[Guid("f8679f50-850a-41cf-9c72-430f290290c8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPolicyConfig
{
    [PreserveSig] int GetMixFormat([MarshalAs(UnmanagedType.LPWStr)] string id, IntPtr p);
    [PreserveSig] int GetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string id, bool b, IntPtr p);
    [PreserveSig] int ResetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string id);
    [PreserveSig] int SetDeviceFormat([MarshalAs(UnmanagedType.LPWStr)] string id, IntPtr a, IntPtr b);
    [PreserveSig] int GetProcessingPeriod([MarshalAs(UnmanagedType.LPWStr)] string id, bool b, IntPtr a, IntPtr c);
    [PreserveSig] int SetProcessingPeriod([MarshalAs(UnmanagedType.LPWStr)] string id, IntPtr p);
    [PreserveSig] int GetShareMode([MarshalAs(UnmanagedType.LPWStr)] string id, IntPtr p);
    [PreserveSig] int SetShareMode([MarshalAs(UnmanagedType.LPWStr)] string id, IntPtr p);
    [PreserveSig] int GetPropertyValue([MarshalAs(UnmanagedType.LPWStr)] string id, bool b, IntPtr k, IntPtr v);
    [PreserveSig] int SetPropertyValue([MarshalAs(UnmanagedType.LPWStr)] string id, bool b, IntPtr k, IntPtr v);
    [PreserveSig] int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string id, int role);
    [PreserveSig] int SetEndpointVisibility([MarshalAs(UnmanagedType.LPWStr)] string id, bool vis);
}

[ComImport, Guid("870af99c-171d-4f9e-af0d-e63df40c2bc9")]
public class CPolicyConfigClient { }

[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDevice
{
    [PreserveSig] int Activate(ref Guid iid, uint ctx, IntPtr p, out IntPtr o);
    [PreserveSig] int OpenPropertyStore(uint access, out IntPtr store);
    [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
    [PreserveSig] int GetState(out uint state);
}

[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDeviceEnumerator
{
    [PreserveSig] int EnumAudioEndpoints(int flow, uint mask, out IntPtr col);
    [PreserveSig] int GetDefaultAudioEndpoint(int flow, int role, out IMMDevice dev);
    [PreserveSig] int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string id, out IMMDevice dev);
}

[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
public class MMDeviceEnumerator { }

public static class Audio
{
    // role: 0=Console 1=Multimedia 2=Communications
    public static int SetDefault(string endpointId)
    {
        IPolicyConfig cfg = (IPolicyConfig)new CPolicyConfigClient();
        int last = 0;
        for (int role = 0; role < 3; role++)
        {
            int hr = cfg.SetDefaultEndpoint(endpointId, role);
            if (hr != 0) last = hr;
        }
        Marshal.ReleaseComObject(cfg);
        return last;
    }

    // flow: 0=Render 1=Capture
    public static string GetDefault(int flow, int role)
    {
        IMMDeviceEnumerator en = (IMMDeviceEnumerator)new MMDeviceEnumerator();
        IMMDevice dev;
        int hr = en.GetDefaultAudioEndpoint(flow, role, out dev);
        if (hr != 0 || dev == null) return null;
        string id;
        dev.GetId(out id);
        Marshal.ReleaseComObject(dev);
        Marshal.ReleaseComObject(en);
        return id;
    }
}
'@

if (-not ('Audio' -as [type])) { Add-Type -TypeDefinition $src -ErrorAction Stop }

function Set-Endpoint([string]$name, [string]$id) {
    $hr = [Audio]::SetDefault($id)
    if ($hr -ne 0) { Write-Host ("  ! {0} ayarlanamadi (HRESULT 0x{1:X8})" -f $name, $hr) -ForegroundColor Red; return $false }
    Write-Host ("  + {0}" -f $name) -ForegroundColor Green
    return $true
}

function Show-Durum {
    $out = [Audio]::GetDefault(0, 0)
    $mic = [Audio]::GetDefault(1, 0)
    $outCom = [Audio]::GetDefault(0, 2)

    $mod = switch ($out) {
        $DEV.StereoOut { 'OYUN MODU  (Stereo - tam kalite ses, mikrofon YOK)' }
        $DEV.HfpOut    { 'SOHBET MODU (Hands-Free - mikrofon VAR, ses dusuk kalite)' }
        default        { 'BILINMEYEN cikis: ' + $out }
    }
    Write-Host ""
    Write-Host "  Aktif mod : $mod" -ForegroundColor Cyan
    if ($outCom -ne $out) {
        Write-Host "  ! Iletisim cikisi farkli -> Discord sesi baska yere gidiyor olabilir" -ForegroundColor Yellow
    }
    if ($mic -eq $DEV.HfpMic) { Write-Host "  Mikrofon  : kulaklik mikrofonu (varsayilan)" }
    else { Write-Host "  Mikrofon  : $mic" }
    Write-Host ""
}

Write-Host ""
switch ($Mode) {
    'oyun' {
        Write-Host "OYUN MODU'na geciliyor..." -ForegroundColor Cyan
        Set-Endpoint 'Cikis -> ttec AirBeat Twist Stereo' $DEV.StereoOut | Out-Null
        Write-Host ""
        Write-Host "  Tam kaliteli stereo ses acik. Mikrofon bu modda CALISMAZ." -ForegroundColor Yellow
        Write-Host "  Discord/oyun sesli sohbet acarsan ses kesilir -> Sohbet Modu'na gec." -ForegroundColor Yellow
        Show-Durum
    }
    'sohbet' {
        Write-Host "SOHBET MODU'na geciliyor..." -ForegroundColor Cyan
        Set-Endpoint 'Cikis   -> ttec AirBeat Twist Hands-Free' $DEV.HfpOut | Out-Null
        Set-Endpoint 'Mikrofon -> ttec AirBeat Twist Hands-Free' $DEV.HfpMic | Out-Null
        Write-Host ""
        Write-Host "  Mikrofon ve ses birlikte calisir. Ses kalitesi telefon kalitesindedir." -ForegroundColor Yellow
        Write-Host "  Muzik/oyun icin Oyun Modu'na geri don." -ForegroundColor Yellow
        Show-Durum
    }
    'durum' { Show-Durum }
}
