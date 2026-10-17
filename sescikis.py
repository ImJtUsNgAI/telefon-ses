# -*- coding: utf-8 -*-
"""
Windows varsayilan oynatma aygitini okuyup degistirir.

Kayit defterinden uc noktalari listeler, degistirmek icin belgelenmemis ama
Windows 10/11'de kararli olan IPolicyConfig COM arayuzunu kullanir (yonetici
hakki gerekmez). Basarisiz olursa sessizce False doner.
"""

import winreg

MMDEV = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
AD_ANAHTARI = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"

DURUM_AKTIF = 1

# eConsole, eMultimedia, eCommunications
ROLLER = (0, 1, 2)


def uc_noktalar(sadece_aktif=True):
    """[(aygit_id, ad, aktif_mi)] dondurur."""
    sonuc = []
    try:
        kok = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, MMDEV)
    except OSError:
        return sonuc
    with kok:
        i = 0
        while True:
            try:
                alt = winreg.EnumKey(kok, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(kok, alt) as k:
                    durum = winreg.QueryValueEx(k, "DeviceState")[0]
                with winreg.OpenKey(kok, alt + r"\Properties") as k:
                    ad = winreg.QueryValueEx(k, AD_ANAHTARI)[0]
            except OSError:
                continue
            aktif = bool(durum & DURUM_AKTIF)
            if sadece_aktif and not aktif:
                continue
            sonuc.append(("{0.0.0.00000000}.%s" % alt, ad, aktif))
    return sonuc


def _politika():
    from ctypes import HRESULT, c_int
    from ctypes.wintypes import LPCWSTR

    from comtypes import CLSCTX_ALL, COMMETHOD, GUID, CoCreateInstance, IUnknown

    class IPolicyConfig(IUnknown):
        _iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetMixFormat"),
            COMMETHOD([], HRESULT, "GetDeviceFormat"),
            COMMETHOD([], HRESULT, "ResetDeviceFormat"),
            COMMETHOD([], HRESULT, "SetDeviceFormat"),
            COMMETHOD([], HRESULT, "GetProcessingPeriod"),
            COMMETHOD([], HRESULT, "SetProcessingPeriod"),
            COMMETHOD([], HRESULT, "GetShareMode"),
            COMMETHOD([], HRESULT, "SetShareMode"),
            COMMETHOD([], HRESULT, "GetPropertyValue"),
            COMMETHOD([], HRESULT, "SetPropertyValue"),
            COMMETHOD(
                [],
                HRESULT,
                "SetDefaultEndpoint",
                (["in"], LPCWSTR, "deviceId"),
                (["in"], c_int, "role"),
            ),
            COMMETHOD([], HRESULT, "SetEndpointVisibility"),
        ]

    return CoCreateInstance(
        GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}"), IPolicyConfig, CLSCTX_ALL
    )


def tam_ada_gore_bul(tam_ad):
    """soundcard'in verdigi uzun adi ('Kulakliklar (ttec ... Stereo)') kayit
    defterindeki kisa adla ('Kulakliklar') eslestirir.

    EN UZUN onek kazanir: aksi halde 'Kulaklik' kaydi 'Kulakliklar (...)' adiyla
    yanlis eslesir ve yanlis aygiti varsayilan yapariz.
    """
    if not tam_ad:
        return None, None
    t = tam_ad.lower()
    en_iyi = (None, None, -1)
    for aid, ad, _a in uc_noktalar():
        a = ad.lower()
        if t == a or t.startswith(a):
            if len(a) > en_iyi[2]:
                en_iyi = (aid, ad, len(a))
    return en_iyi[0], en_iyi[1]


def varsayilan_oku():
    """(aygit_id, ad) - suanki varsayilan oynatma aygiti."""
    try:
        import soundcard as sc

        hedef = str(sc.default_speaker().name)
    except Exception:
        return None, None
    aid, ad = tam_ada_gore_bul(hedef)
    return (aid, ad) if aid else (None, hedef)


def varsayilan_yap(aygit_id):
    """Verilen uc noktayi tum roller icin varsayilan yapar."""
    try:
        pc = _politika()
        for rol in ROLLER:
            pc.SetDefaultEndpoint(aygit_id, rol)
        return True
    except Exception:
        return False


def ada_gore_bul(parca):
    p = parca.lower()
    for aid, ad, _a in uc_noktalar():
        if p in ad.lower():
            return aid, ad
    return None, None


if __name__ == "__main__":
    simdi_id, simdi_ad = varsayilan_oku()
    print("Aktif oynatma aygitlari:")
    for aid, ad, _a in uc_noktalar():
        isaret = "->" if aid == simdi_id else "  "
        print("  %s %-45s %s" % (isaret, ad, aid))
    print("\nVarsayilan:", simdi_ad)
