# -*- coding: utf-8 -*-
"""
TelefonSes - Telefonu bilgisayara kablosuz hoparlor + mikrofon yapar.

  PC sesi  --(WASAPI loopback)--> WebSocket --> telefon hoparloru
  Telefon mikrofonu --> WebSocket --> sanal ses kablosu --> Windows "mikrofon"

Kullanim:  python sunucu.py
           python sunucu.py --liste
           python sunucu.py --kaynak "Stereo" --mik-cikis "CABLE"
"""

import os
import subprocess
import sys

# --------------------------------------------------------------------------
# 0) Bagimliliklar
# --------------------------------------------------------------------------
_GEREKLI = {
    "numpy": "numpy",
    "aiohttp": "aiohttp",
    "soundcard": "soundcard",
    "sounddevice": "sounddevice",
    "cryptography": "cryptography",
    "qrcode": "qrcode",
}


def _bagimliliklari_sagla():  # pragma: no cover
    eksik = []
    for mod, pkg in _GEREKLI.items():
        try:
            __import__(mod)
        except ImportError:
            eksik.append(pkg)
    if eksik:
        print("Eksik paketler kuruluyor: " + ", ".join(eksik))
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *eksik]
        )
        print("Kurulum tamam.\n")


_bagimliliklari_sagla()

import argparse
import asyncio
import datetime
import ipaddress
import json
import socket
import ssl
import threading
import time
import warnings
from collections import deque

import numpy as np
import sounddevice as sd
import soundcard as sc
from aiohttp import WSMsgType, web

try:
    import sescikis
except Exception:  # pragma: no cover
    sescikis = None

warnings.filterwarnings("ignore", message="data discontinuity in recording")

# --------------------------------------------------------------------------
# Sabitler
# --------------------------------------------------------------------------
SR = 48000          # dahili ornekleme hizi
BLOK = 480          # 10 ms
KOK = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(KOK, "web")
SERTIFIKA_DIZIN = os.path.join(KOK, "sertifika")

# Sanal ses kablosu adaylari (giris = Windows'un icine ses basacagimiz oynatma aygiti)
SANAL_KABLO_DESENLERI = [
    "cable input",
    "vb-audio",
    "voicemeeter input",
    "voicemeeter aux input",
    "virtual audio cable",
    "line 1 (virtual",
]


def db(x: float) -> float:
    return -90.0 if x <= 1e-9 else max(-90.0, 20.0 * np.log10(x))


# --------------------------------------------------------------------------
# 1) TLS sertifikasi (getUserMedia HTTPS ister)
# --------------------------------------------------------------------------
def sertifika_hazirla(ipler):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    os.makedirs(SERTIFIKA_DIZIN, exist_ok=True)
    crt = os.path.join(SERTIFIKA_DIZIN, "sunucu.crt")
    key = os.path.join(SERTIFIKA_DIZIN, "sunucu.key")
    meta = os.path.join(SERTIFIKA_DIZIN, "ipler.json")

    istenen = sorted(set(ipler) | {"127.0.0.1"})
    if os.path.exists(crt) and os.path.exists(key) and os.path.exists(meta):
        try:
            with open(meta, encoding="utf-8") as f:
                if json.load(f) == istenen:
                    return crt, key
        except Exception:
            pass

    anahtar = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    isim = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TelefonSes")])
    sans = [x509.DNSName("localhost")]
    for ip in istenen:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            pass
    simdi = datetime.datetime.now(datetime.timezone.utc)
    sert = (
        x509.CertificateBuilder()
        .subject_name(isim)
        .issuer_name(isim)
        .public_key(anahtar.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(simdi - datetime.timedelta(days=1))
        .not_valid_after(simdi + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .sign(anahtar, hashes.SHA256())
    )
    with open(crt, "wb") as f:
        f.write(sert.public_bytes(serialization.Encoding.PEM))
    with open(key, "wb") as f:
        f.write(
            anahtar.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
    with open(meta, "w", encoding="utf-8") as f:
        json.dump(istenen, f)
    return crt, key


def yerel_ipler():
    ipler = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ipler.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for bilgi in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ipler.add(bilgi[4][0])
    except Exception:
        pass
    return sorted(i for i in ipler if not i.startswith("127."))


# --------------------------------------------------------------------------
# 2) PC sesini yakalama (WASAPI loopback)
# --------------------------------------------------------------------------
class Yakalayici(threading.Thread):
    """Varsayilan (ya da secilen) oynatma aygitinin sesini dinler."""

    def __init__(self, tercih, tuket):
        super().__init__(daemon=True)
        self.tercih = tercih
        self.tuket = tuket
        self.dur = threading.Event()
        self.aygit_adi = "-"
        self.hata = None
        self.rms = 0.0

    def _mikrofon_sec(self):
        mikler = sc.all_microphones(include_loopback=True)
        if self.tercih:
            t = self.tercih.lower()
            for m in mikler:
                if m.isloopback and t in str(m.name).lower():
                    return m
            raise RuntimeError("Loopback aygiti bulunamadi: %s" % self.tercih)
        hoparlor = str(sc.default_speaker().name)
        for m in mikler:
            if m.isloopback and str(m.name) == hoparlor:
                return m
        return sc.get_microphone(hoparlor, include_loopback=True)

    def run(self):
        while not self.dur.is_set():
            try:
                mik = self._mikrofon_sec()
                self.aygit_adi = str(mik.name)
                self.hata = None
                kanal = 2 if (mik.channels or 2) >= 2 else 1
                with mik.recorder(
                    samplerate=SR, channels=kanal, blocksize=BLOK
                ) as kayit:
                    hedef = self.aygit_adi
                    sayac = 0
                    while not self.dur.is_set():
                        d = kayit.record(numframes=BLOK)
                        if d.ndim == 1:
                            d = d[:, None]
                        if d.shape[1] == 1:
                            d = np.repeat(d, 2, axis=1)
                        elif d.shape[1] > 2:
                            d = d[:, :2]
                        d = np.ascontiguousarray(d, dtype=np.float32)
                        self.rms = float(np.sqrt(np.mean(d * d)) if d.size else 0.0)
                        self.tuket(d)
                        sayac += 1
                        # varsayilan cikis aygiti degistiyse yeniden bagla
                        if sayac % 200 == 0 and not self.tercih:
                            try:
                                if str(sc.default_speaker().name) != hedef:
                                    break
                            except Exception:
                                pass
            except Exception as e:
                # Aygit yoksa saniyede bir yeniden denemek Windows ses motorunu
                # (ozellikle Bluetooth'ta) yorar. Kademeli olarak yavasla.
                self.hata = str(e)
                self.rms = 0.0
                self.bekleme = min(15.0, getattr(self, "bekleme", 0.5) * 2)
                self.dur.wait(self.bekleme)
            else:
                self.bekleme = 0.5


# --------------------------------------------------------------------------
# 3) Telefon mikrofonunu Windows'a basma
# --------------------------------------------------------------------------
class MikKuyrugu:
    """Tek bir telefonun mikrofon akisi icin jitter tamponu."""

    def __init__(self, hedef_ms=100, maks_ms=400):
        self.bloklar = deque()
        self.kilit = threading.Lock()
        self.cerceve = 0
        self.hazir = False
        self.hedef = int(SR * hedef_ms / 1000)
        self.maks = int(SR * maks_ms / 1000)
        self.altakis = 0
        self.rms = 0.0

    def ekle(self, dizi: np.ndarray):
        with self.kilit:
            self.bloklar.append(dizi)
            self.cerceve += len(dizi)
            while self.cerceve > self.maks and self.bloklar:
                self.cerceve -= len(self.bloklar.popleft())
            if not self.hazir and self.cerceve >= self.hedef:
                self.hazir = True

    def al(self, n):
        cikti = np.zeros(n, dtype=np.float32)
        with self.kilit:
            if not self.hazir:
                return cikti
            i = 0
            while i < n and self.bloklar:
                b = self.bloklar[0]
                al = min(len(b), n - i)
                cikti[i : i + al] = b[:al]
                if al == len(b):
                    self.bloklar.popleft()
                else:
                    self.bloklar[0] = b[al:]
                self.cerceve -= al
                i += al
            if i < n:
                self.hazir = False
                self.altakis += 1
        return cikti


class MikCikis:
    """Telefon mikrofonunu bir oynatma aygitina (sanal kablo) yazar."""

    def __init__(self, aygit_index, kanal_sayisi):
        self.aygit = aygit_index
        self.kanal = max(1, min(2, kanal_sayisi))
        self.kuyruklar = {}
        self.kilit = threading.Lock()
        self.akis = None
        self.rms = 0.0
        self.hata = None

    def kuyruk_ac(self, kimlik):
        q = MikKuyrugu()
        with self.kilit:
            self.kuyruklar[kimlik] = q
        return q

    def kuyruk_kapat(self, kimlik):
        with self.kilit:
            self.kuyruklar.pop(kimlik, None)

    def _geri_cagri(self, veri, cerceve, zaman, durum):
        with self.kilit:
            kuyruklar = list(self.kuyruklar.values())
        if kuyruklar:
            karisim = kuyruklar[0].al(cerceve)
            for q in kuyruklar[1:]:
                karisim = karisim + q.al(cerceve)
            np.clip(karisim, -1.0, 1.0, out=karisim)
        else:
            karisim = np.zeros(cerceve, dtype=np.float32)
        self.rms = float(np.sqrt(np.mean(karisim * karisim)))
        for c in range(self.kanal):
            veri[:, c] = karisim

    def baslat(self):
        if self.aygit is None:
            return False
        try:
            ekstra = None
            try:
                if "WASAPI" in sd.query_hostapis(
                    sd.query_devices(self.aygit)["hostapi"]
                )["name"]:
                    ekstra = sd.WasapiSettings(auto_convert=True)
            except Exception:
                pass
            self.akis = sd.OutputStream(
                device=self.aygit,
                samplerate=SR,
                channels=self.kanal,
                dtype="float32",
                blocksize=BLOK,
                callback=self._geri_cagri,
                extra_settings=ekstra,
            )
            self.akis.start()
            return True
        except Exception as e:
            self.hata = str(e)
            self.akis = None
            return False

    def kapat(self):
        if self.akis:
            try:
                self.akis.stop()
                self.akis.close()
            except Exception:
                pass
            self.akis = None


def cikis_aygitlari():
    hostapiler = sd.query_hostapis()
    sonuc = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0:
            sonuc.append((i, d, hostapiler[d["hostapi"]]["name"]))
    return sonuc


def sanal_kablo_bul(tercih=None):
    """(index, ad, kanal) dondurur; bulunamazsa (None, None, 0)."""
    adaylar = [
        (i, d, h) for i, d, h in cikis_aygitlari() if "WASAPI" in h
    ] or cikis_aygitlari()
    if tercih:
        t = tercih.lower()
        if t.isdigit():
            i = int(t)
            d = sd.query_devices(i)
            return i, d["name"], d["max_output_channels"]
        for i, d, _h in adaylar:
            if t in d["name"].lower():
                return i, d["name"], d["max_output_channels"]
        return None, None, 0
    for desen in SANAL_KABLO_DESENLERI:
        for i, d, _h in adaylar:
            if desen in d["name"].lower():
                return i, d["name"], d["max_output_channels"]
    return None, None, 0


# --------------------------------------------------------------------------
# 4) Ses paketleme
# --------------------------------------------------------------------------
def paketle(blok: np.ndarray, hz: int, kanal: int) -> bytes:
    x = blok
    if kanal == 1:
        x = x.mean(axis=1, keepdims=True)
    if hz == 24000:
        n = (len(x) // 2) * 2
        x = (x[0:n:2] + x[1:n:2]) * 0.5
    pcm = np.clip(x * 32767.0, -32768, 32767).astype("<i2")
    # baslik 4 bayt: [tip, kanal, hz kodu, 0] -> int16 dizisi 4'e hizali kalsin
    return bytes([0x02, kanal, 0 if hz == 48000 else 1, 0]) + pcm.tobytes()


def yeniden_ornekle(x: np.ndarray, kaynak_hz: int, hedef_hz: int) -> np.ndarray:
    if kaynak_hz == hedef_hz or len(x) == 0:
        return x
    n = max(1, int(round(len(x) * hedef_hz / kaynak_hz)))
    return np.interp(
        np.linspace(0, len(x) - 1, n, dtype=np.float64),
        np.arange(len(x), dtype=np.float64),
        x,
    ).astype(np.float32)


# --------------------------------------------------------------------------
# 5) Sunucu
# --------------------------------------------------------------------------
class Istemci:
    _sayac = 0

    def __init__(self, ws):
        Istemci._sayac += 1
        self.kimlik = Istemci._sayac
        self.ws = ws
        self.hz = 48000
        self.kanal = 2
        self.hoparlor_acik = True
        self.mik_hz = 48000
        self.mik_kazanc = 1.0
        self.kuyruk = asyncio.Queue(maxsize=60)
        self.dusen = 0
        self.ad = "telefon"
        self.gecikme = 0.0


class Uygulama:
    def __init__(self, args):
        self.args = args
        self.istemciler = {}
        self.loop = None
        self.yakalayici = None
        self.mik_cikis = None
        self.mik_cikis_adi = "-"
        self.baslangic = time.time()
        self.onceki_varsayilan = None  # (aygit_id, ad) - --sanal modunda geri alinir

    # -------- ses dagitimi --------
    def _blok_geldi(self, blok):
        if self.loop and self.istemciler:
            try:
                self.loop.call_soon_threadsafe(self._dagit, blok)
            except RuntimeError:
                pass

    def _dagit(self, blok):
        onbellek = {}
        for c in list(self.istemciler.values()):
            if not c.hoparlor_acik:
                continue
            anahtar = (c.hz, c.kanal)
            paket = onbellek.get(anahtar)
            if paket is None:
                paket = paketle(blok, c.hz, c.kanal)
                onbellek[anahtar] = paket
            try:
                c.kuyruk.put_nowait(paket)
            except asyncio.QueueFull:
                # Telefon yetisemiyor. Sadece EN ESKI paketi at: 10 ms'lik bir
                # atlama, kuyrugu yariya indirmenin yaptigi 300 ms'lik sicramadan
                # cok daha az duyulur.
                c.dusen += 1
                try:
                    c.kuyruk.get_nowait()
                    c.kuyruk.put_nowait(paket)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    # -------- http --------
    async def sayfa(self, request):
        return web.FileResponse(os.path.join(WEB, "index.html"))

    async def durum_json(self, request):
        return web.json_response(
            {
                "kaynak": self.yakalayici.aygit_adi if self.yakalayici else "-",
                "mikCikis": self.mik_cikis_adi,
                "istemci": len(self.istemciler),
            }
        )

    async def ws_islem(self, request):
        ws = web.WebSocketResponse(max_msg_size=4 << 20, heartbeat=25, compress=False)
        await ws.prepare(request)
        c = Istemci(ws)
        self.istemciler[c.kimlik] = c
        kuyruk = self.mik_cikis.kuyruk_ac(c.kimlik) if self.mik_cikis else None
        yazici = asyncio.create_task(self._yazici(c))
        print(f"\n[+] Telefon baglandi (#{c.kimlik}) - {request.remote}")

        await ws.send_str(
            json.dumps(
                {
                    "t": "hos",
                    "kaynak": self.yakalayici.aygit_adi if self.yakalayici else "-",
                    "mikCikis": self.mik_cikis_adi,
                    "mikVar": self.mik_cikis is not None
                    and self.mik_cikis.akis is not None,
                }
            )
        )
        try:
            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    d = msg.data
                    if len(d) > 2 and d[0] == 0x01 and kuyruk is not None:
                        pcm = np.frombuffer(d, dtype="<i2", offset=2)
                        x = (pcm.astype(np.float32) / 32768.0) * c.mik_kazanc
                        if c.mik_hz != SR:
                            x = yeniden_ornekle(x, c.mik_hz, SR)
                        kuyruk.rms = float(np.sqrt(np.mean(x * x)) if x.size else 0.0)
                        kuyruk.ekle(np.clip(x, -1.0, 1.0))
                elif msg.type == WSMsgType.TEXT:
                    try:
                        veri = json.loads(msg.data)
                    except Exception:
                        continue
                    t = veri.get("t")
                    if t == "cfg":
                        c.hz = 24000 if int(veri.get("hz", 48000)) == 24000 else 48000
                        c.kanal = 1 if int(veri.get("kanal", 2)) == 1 else 2
                        c.hoparlor_acik = bool(veri.get("hoparlor", True))
                        c.mik_hz = int(veri.get("mikHz", 48000))
                        c.mik_kazanc = float(veri.get("kazanc", 1.0))
                        c.ad = str(veri.get("ad", c.ad))[:40]
                    elif t == "ping":
                        await ws.send_str(
                            json.dumps(
                                {"t": "pong", "ts": veri.get("ts"), "dusen": c.dusen}
                            )
                        )
                    elif t == "gecikme":
                        c.gecikme = float(veri.get("ms", 0))
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            yazici.cancel()
            self.istemciler.pop(c.kimlik, None)
            if self.mik_cikis:
                self.mik_cikis.kuyruk_kapat(c.kimlik)
            print(f"\n[-] Telefon ayrildi (#{c.kimlik})")
        return ws

    async def _yazici(self, c: Istemci):
        try:
            while True:
                paket = await c.kuyruk.get()
                await c.ws.send_bytes(paket)
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        except Exception:
            pass

    # -------- konsol --------
    async def konsol(self):
        cizgi = "#" * 20
        while True:
            await asyncio.sleep(0.2)
            if not sys.stdout.isatty():
                continue
            gelen = self.yakalayici.rms if self.yakalayici else 0.0
            giden = self.mik_cikis.rms if self.mik_cikis else 0.0

            def bar(r):
                seviye = int(max(0.0, min(1.0, (db(r) + 60) / 60)) * 20)
                return (cizgi[:seviye]).ljust(20, ".")

            hata = ""
            if self.yakalayici and self.yakalayici.hata:
                hata = "  HATA: " + self.yakalayici.hata[:40]
            sys.stdout.write(
                "\r  PC->Tel [%s]   Tel->PC [%s]   telefon:%d%s   "
                % (bar(gelen), bar(giden), len(self.istemciler), hata)
            )
            sys.stdout.flush()


# --------------------------------------------------------------------------
# 6) Baslatma
# --------------------------------------------------------------------------
def aygitlari_listele():
    print("\n== Yakalanabilir PC cikislari (loopback) ==")
    for m in sc.all_microphones(include_loopback=True):
        if m.isloopback:
            print("   *", m.name)
    print("\n== Oynatma aygitlari (telefon mikrofonunu buraya basariz) ==")
    for i, d, h in cikis_aygitlari():
        if "WASAPI" in h or "MME" in h:
            print("  %3d  [%s] %s (%dch)" % (i, h[:8], d["name"], d["max_output_channels"]))
    print()


def _sanal_moda_gec(uyg, args):
    """Sanal kabloyu Windows varsayilan cikisi yapar; kaynak olarak onu secer."""
    if sescikis is None:
        print("  [SANAL] sescikis.py yuklenemedi, --sanal atlandi.")
        return
    uc_id = uc_ad = None
    for desen in SANAL_KABLO_DESENLERI:
        uc_id, uc_ad = sescikis.ada_gore_bul(desen)
        if uc_id:
            break
    if not uc_id:
        print("\n  [SANAL] Sanal ses kablosu bulunamadi - bu mod calismaz.")
        print("          Once vbcable-kur.ps1 ile VB-CABLE kur ve yeniden baslat.\n")
        return
    uyg.onceki_varsayilan = sescikis.varsayilan_oku()
    if sescikis.varsayilan_yap(uc_id):
        args.kaynak = uc_ad
        eski = uyg.onceki_varsayilan[1] or "yok"
        print("  [SANAL] Windows varsayilan cikisi -> %s   (eski: %s)" % (uc_ad, eski))
        print("          Cikista eski aygita geri donulecek.")
    else:
        uyg.onceki_varsayilan = None
        print("  [SANAL] Varsayilan cikis degistirilemedi (COM reddetti).")
        print("          Windows ses ayarlarindan elle '%s' sec." % uc_ad)


def _ayni_aygit(a, b):
    if not a or not b:
        return False
    a, b = a.strip().lower(), b.strip().lower()
    return a == b or a.startswith(b) or b.startswith(a)


def main():
    p = argparse.ArgumentParser(description="Telefonu PC hoparloru + mikrofonu yapar")
    p.add_argument("--port", type=int, default=8443)
    p.add_argument("--kaynak", default=None, help="Yakalanacak PC cikisi (ad parcasi)")
    p.add_argument("--mik-cikis", default=None, help="Telefon mikrofonunun basilacagi aygit (ad parcasi veya index)")
    p.add_argument("--monitor", action="store_true", help="Sanal kablo yoksa telefon mikrofonunu PC hoparlorunden dinlet (yanki riski!)")
    p.add_argument("--sanal", action="store_true", help="Sadece telefon modu: sanal kabloyu Windows varsayilan cikisi yapar ve onu yakalar (kulaklik gerekmez)")
    p.add_argument("--liste", action="store_true", help="Ses aygitlarini listele ve cik")
    args = p.parse_args()

    if args.liste:
        aygitlari_listele()
        return

    print("=" * 68)
    print("  TELEFON SES  -  telefonun = kablosuz hoparlor + mikrofon")
    print("=" * 68)

    uyg = Uygulama(args)

    # --- sadece telefon modu: sanal kabloyu varsayilan cikis yap ---
    if args.sanal:
        _sanal_moda_gec(uyg, args)

    # --- cikis aygiti var mi? ---
    try:
        hoparlorler = sc.all_speakers()
    except Exception:
        hoparlorler = []
    if not hoparlorler:
        print("\n  !!! UYARI: Windows'ta AKTIF HICBIR SES CIKISI YOK.")
        print("      Kulaklik/hoparlor bagli degilken uygulamalar ses uretmez,")
        print("      dolayisiyla yakalanacak ses de olusmaz. Kalici cozum:")
        print("      1) vbcable-kur.ps1 ile VB-CABLE kur, yeniden baslat")
        print("      2) 'Telefon-Hoparlor.bat' ile calistir (--sanal)")
        print("      Detay: OKUBENI.md > 'Kulaklik kapaliyken ses gelmiyor'\n")

    # --- PC sesi yakalama ---
    uyg.yakalayici = Yakalayici(args.kaynak, uyg._blok_geldi)
    uyg.yakalayici.start()
    time.sleep(0.6)
    print("  [HOPARLOR] Yakalanan PC cikisi : %s" % uyg.yakalayici.aygit_adi)
    if uyg.yakalayici.hata:
        print("             ! %s" % uyg.yakalayici.hata)

    # --- telefon mikrofonu -> Windows ---
    idx, ad, kanal = sanal_kablo_bul(args.mik_cikis)
    if idx is None and args.monitor:
        try:
            idx = sd.default.device[1]
            d = sd.query_devices(idx)
            ad, kanal = d["name"], d["max_output_channels"]
            print("  [MIKROFON] Monitor modu: telefon mikrofonu PC hoparlorunden calacak")
        except Exception:
            idx = None
    if idx is not None and _ayni_aygit(ad, uyg.yakalayici.aygit_adi):
        print("  [MIKROFON] KAPALI - yakalanan cikisla ayni aygit (%s)." % ad)
        print("             Ayni kabloya hem yazip hem okumak yanki dongusu yapar.")
        print("             Iki yon icin ikinci bir sanal kablo gerekir")
        print("             (VoiceMeeter kur ya da --sanal olmadan calistir).")
        idx = None
    if idx is not None:
        uyg.mik_cikis = MikCikis(idx, kanal)
        if uyg.mik_cikis.baslat():
            uyg.mik_cikis_adi = ad
            print("  [MIKROFON] Ses su aygita basiliyor : %s" % ad)
            if not args.monitor:
                print("             -> Windows/Zoom/Discord'da mikrofon olarak")
                print('                "CABLE Output (VB-Audio Virtual Cable)" sec.')
        else:
            print("  [MIKROFON] Aygit acilamadi: %s" % uyg.mik_cikis.hata)
            uyg.mik_cikis = None
    if uyg.mik_cikis is None:
        print("  [MIKROFON] KAPALI - sanal ses kablosu bulunamadi.")
        print("             Mikrofon icin VB-CABLE kur (bir kez, ucretsiz):")
        print("             sag tik -> 'vbcable-kur.ps1' -> PowerShell ile calistir")
        print("             (ya da hemen denemek icin:  --monitor)")

    # --- web sunucusu ---
    ipler = yerel_ipler()
    crt, key = sertifika_hazirla(ipler)
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(crt, key)

    app = web.Application()
    app.router.add_get("/", uyg.sayfa)
    app.router.add_get("/durum", uyg.durum_json)
    app.router.add_get("/ws", uyg.ws_islem)
    app.router.add_static("/statik", WEB)

    async def calistir():
        uyg.loop = asyncio.get_running_loop()
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", args.port, ssl_context=ssl_ctx)
        await site.start()

        adres = "https://%s:%d" % (ipler[0] if ipler else "127.0.0.1", args.port)
        print("\n" + "-" * 68)
        print("  TELEFONDAN AC:   %s" % adres)
        for ip in ipler[1:]:
            print("    (alternatif)   https://%s:%d" % (ip, args.port))
        print("  Not: 'Baglanti guvenli degil' uyarisinda")
        print("       Gelismis > Yine de devam et  de. (kendi sertifikamiz)")
        print("-" * 68)
        try:
            import qrcode

            q = qrcode.QRCode(border=1)
            q.add_data(adres)
            q.make(fit=True)
            q.print_ascii(invert=True)
        except Exception:
            pass
        print("  Kapatmak icin Ctrl+C\n")

        asyncio.create_task(uyg.konsol())
        await asyncio.Event().wait()

    try:
        asyncio.run(calistir())
    except KeyboardInterrupt:
        print("\nKapatiliyor...")
    finally:
        if uyg.yakalayici:
            uyg.yakalayici.dur.set()
        if uyg.mik_cikis:
            uyg.mik_cikis.kapat()
        if uyg.onceki_varsayilan and uyg.onceki_varsayilan[0] and sescikis:
            if sescikis.varsayilan_yap(uyg.onceki_varsayilan[0]):
                print("Varsayilan ses cikisi geri alindi: %s" % uyg.onceki_varsayilan[1])


if __name__ == "__main__":
    main()
