# Telefon Ses

Telefonunu bilgisayarının **kablosuz hoparlörü** ve **mikrofonu** yapar.
Uygulama kurmana gerek yok — telefonda sadece tarayıcı açılır.

```
  PC sesi ──(WASAPI loopback)──► WebSocket ──► telefon hoparlörü
  telefon mikrofonu ──► WebSocket ──► sanal ses kablosu ──► Windows "mikrofon"
```

---

## Hızlı başlangıç

1. **`Baslat.bat`** dosyasına çift tıkla.
   İlk çalıştırmada Windows güvenlik duvarı izin sorabilir → **İzin ver** (Özel ağlar).
2. Terminalde çıkan adresi telefonda aç:
   `https://192.168.x.x:8443`
   (Terminaldeki **QR kodu** telefon kamerasıyla okutman en kolayı.)
3. Telefonda "Bağlantı güvenli değil" uyarısı çıkar →
   **Gelişmiş → Yine de devam et**.
   (Sertifika bizim ürettiğimiz kendi sertifikamız; ses trafiği yine de şifreli.)
4. Büyük yeşil **BAŞLAT** düğmesine bas.

Bilgisayarın sesi artık telefondan çıkıyor. ✔

> Telefon ve bilgisayar **aynı Wi-Fi ağında** olmalı.

---

## ⚠ "Kulaklığı açık tutmam gerekiyor, yoksa ses gelmiyor"

Bu bilgisayarda **Bluetooth kulaklık dışında aktif ses çıkışı yok** (Realtek
hoparlör/kulaklık uçları "takılı değil" durumunda). Kulaklık kapalıyken Windows'un
çalacağı hiçbir aygıt kalmıyor; uygulamalar ses üretmeyi bırakıyor. Ortada ses
oluşmadığı için loopback de yakalayacak bir şey bulamıyor.

Kalıcı çözüm, donanıma bağlı olmayan **her zaman aktif sanal bir çıkış** eklemek:

1. `vbcable-kur.ps1` → VB-CABLE'ı kur, bilgisayarı yeniden başlat
2. **`Telefon-Hoparlor.bat`** ile çalıştır (= `python sunucu.py --sanal`)

Bu mod, Windows'un varsayılan ses çıkışını sanal kabloya alır ve o kabloyu yakalar.
Sonuç: **kulaklık tamamen kapalıyken bile ses telefondan çalar** — üstelik sadece
telefondan çalar, PC'ye paralel ses gitmez. Pencereyi kapatınca varsayılan aygıt
otomatik olarak eski haline döner.

> **Tek kablonun sınırı:** VB-CABLE tek bir kablo (Input↔Output) verir. `--sanal`
> modunda o kablo hoparlör yönüne ayrılır, aynı anda mikrofon yönü kullanılamaz —
> aynı kabloya hem yazıp hem okumak yankı döngüsü yapar. Sunucu bunu kendisi fark
> edip mikrofonu kapatır ve uyarır. **İki yönü aynı anda** istiyorsan ikinci bir
> sanal kablo gerekir: ücretsiz **VoiceMeeter**'ı kur (VB-Audio'nun kendi programı),
> ikinci çift olarak otomatik bulunur.

---

## Mikrofon yönü (telefon → PC)

Windows'ta "telefonum mikrofon olsun" demek için sisteme **sanal bir ses aygıtı**
eklemek şart — bu bir sürücü işi, tarayıcı tek başına yapamaz. Bir kere kurulur:

1. `vbcable-kur.ps1` dosyasına **sağ tık → PowerShell ile çalıştır**
   (yönetici izni ister, VB-CABLE'ı indirip kurar — ücretsiz).
2. Kurulum bitince **bilgisayarı yeniden başlat**.
3. `Baslat.bat`'ı tekrar çalıştır — `CABLE Input` aygıtı otomatik bulunur, terminalde
   `[MIKROFON] Ses su aygita basiliyor: CABLE Input...` yazar.
4. Telefondaki sayfada **Mikrofon** anahtarını aç, tarayıcı izin isteyince **İzin ver**.
5. Zoom / Discord / Teams / Windows ses ayarlarında mikrofon olarak
   **`CABLE Output (VB-Audio Virtual Cable)`** seç.

**Hemen denemek için** (VB-CABLE kurmadan): `python sunucu.py --monitor`
Telefon mikrofonun PC hoparlöründen çalar. Sadece testlik — telefon da PC sesini
çalıyorsa **uğultu/yankı döngüsü** olur, kulaklıkla dene.

---

## Ayarlar (telefon ekranında)

| Ayar | Ne işe yarar |
|---|---|
| **Hoparlör** | PC sesinin telefona akışını açar/kapatır |
| **Mikrofon** | Telefon mikrofonunun PC'ye akışını açar/kapatır |
| **Ses kalitesi** | Yüksek 48 kHz stereo (~1.5 Mbps) / Orta mono / Düşük 24 kHz mono. Wi-Fi zayıfsa düşür. |
| **Tampon** | Varsayılan 120 ms, 20–500 ms arası. Ses kesik kesikse **artır**, gecikme rahatsız ediyorsa **azalt**. Değişiklik anında uygulanır: büyütünce kısa bir sessizlikle yeniden dolar, küçültünce fazlası atılıp gecikme hemen düşer. |
| **Mikrofon seviyesi** | PC'ye giden sesin kazancı |
| **Yankı engelleme** | Telefon aynı anda hem çalıp hem dinliyorsa **açık** tut |

Alttaki **Durum** tablosu gecikmenin nereden geldiğini ayrı ayrı gösterir:

| Satır | Ne demek |
|---|---|
| **Ağ gecikmesi** | Wi-Fi gidiş-dönüş. Aynı ağda genelde 5–20 ms — küçüktür, sorun burası değildir. |
| **Ses tamponu** | Kaydırıcıyla belirlediğin cushion. Doğrudan senin kontrolünde. |
| **Telefon çıkış gecikmesi** | Tarayıcı → Android ses yolu. **Genelde en büyük kalem** (50–200 ms) ve dışarıdan değiştirilemez; telefonun/Bluetooth kulaklığın donanım gerçeği. Bluetooth hoparlör/kulaklık kullanıyorsan buna 100–200 ms daha biner. |
| **Toplam gecikme** | Hepsinin toplamı ≈ gerçekte duyduğun gecikme. |

Ağ gecikmesi 5–10 ms olmasına rağmen toplam yüksek çıkıyorsa, tamponu daha da
kısmanın faydası yoktur — kalan gecikme telefonun kendi ses çıkışındadır.
Telefonu **kabloyla** ya da doğrudan telefon hoparlöründen dinlemek, Bluetooth'a
göre belirgin fark yaratır.

---

## Komut satırı seçenekleri

```powershell
python sunucu.py                          # normal
python sunucu.py --sanal                  # SADECE TELEFON: sanal kabloyu varsayılan
                                          #   çıkış yapar, kulaklık gerekmez
python sunucu.py --liste                  # ses aygıtlarını listele
python sunucu.py --kaynak "Stereo"        # hangi PC çıkışı yakalansın
python sunucu.py --mik-cikis "CABLE"      # telefon mikrofonu nereye basılsın (ad veya index)
python sunucu.py --monitor                # mikrofonu PC hoparlöründen dinlet
python sunucu.py --port 9443              # başka port
```

`--kaynak` verilmezse **o anki varsayılan oynatma aygıtı** yakalanır ve varsayılan
aygıtı değiştirdiğinde sunucu kendini otomatik yeni aygıta bağlar.

---

## Sık karşılaşılanlar

**Hiçbir aygıttan ses gelmiyor (telefon bağlı olmasa da)**
Windows ses motoru takılmış olabilir — belirtisi: ses aygıtları listeden kaybolur,
uygulamalar "ses aygıtı yok" der, ana ses seviyesi okunur ama hiçbir şey çalmaz.
**`Ses-Onar.bat`** çift tıkla (UAC ister); ses servislerini yeniden başlatır,
birkaç saniyede düzelir. Bu sorunun TelefonSes çalışmıyorken de olabileceğini unutma —
Bluetooth kulaklıklarda Windows'un bilinen bir aksaklığıdır.

**Telefonda sayfa açılmıyor**
Güvenlik duvarı engelliyor olabilir → `guvenlik-duvari-izni.ps1` (sağ tık → PowerShell ile çalıştır).
Ayrıca Wi-Fi ağının "Genel ağ" değil **"Özel ağ"** olarak işaretli olduğundan emin ol.
Bazı modemlerde açık olan **AP/Client Isolation** cihazların birbirini görmesini engeller.

**Ses geliyor ama kesik kesik**
Telefondaki **Tampon**'u 200–300 ms'e çek, kaliteyi "Orta"ya düşür.
5 GHz Wi-Fi belirgin şekilde daha iyi sonuç verir.

**Hiç ses gelmiyor (çubuklar boş)**
Terminaldeki `[HOPARLOR] Yakalanan PC cikisi` satırının, sesin gerçekten çaldığı
aygıt olduğundan emin ol. Bluetooth kulaklık takılıyken varsayılan çıkış o olur;
`--kaynak` ile istediğini seçebilirsin.

**PC hoparlöründen de çalıyor, sadece telefondan istiyorum**
Ses hâlâ PC'nin kendi çıkışına gidiyor, biz onu dinliyoruz. Sadece telefondan
çıkmasını istiyorsan VB-CABLE kurulduktan sonra Windows'un **varsayılan oynatma
aygıtını `CABLE Input` yap** ve sunucuyu `--kaynak "CABLE Input"` ile çalıştır.

**Gecikme ne kadar?**
Aynı Wi-Fi'da tipik olarak 130–250 ms. Müzik/film için sorunsuz, oyun ve
dudak senkronu isteyen işler için değil (Wi-Fi'ın fiziksel sınırı).

**Telefon ekranı kapanınca susuyor**
Sayfa ekranı açık tutmaya çalışır (Wake Lock) ama tarayıcı yine de arka planda
sesi kısabilir. Sekmeyi ön planda bırak.

---

## Nasıl çalışıyor (kısaca)

* `sunucu.py` — Python. WASAPI **loopback** ile PC'nin çıkış sesini dinler
  (`soundcard`), 10 ms'lik 16-bit PCM bloklarını WebSocket üzerinden yollar.
  Telefondan gelen mikrofon paketlerini jitter tamponundan geçirip `sounddevice`
  ile sanal kablo aygıtına yazar. Birden fazla telefon bağlanabilir; mikrofonları
  toplanarak karışır.
* `web/index.html` — telefon arayüzü. Ses için **AudioWorklet** kullanır:
  gelen paketler halka tamponunda birikir, tampon dolunca çalmaya başlar
  (kesilmeleri bu tampon yutar). Mikrofonu 480 örneklik bloklar halinde yollar.
* HTTPS zorunlu, çünkü tarayıcılar mikrofona sadece güvenli sayfada izin verir.
  Sertifika ilk çalıştırmada `sertifika/` klasörüne üretilir.

## Dosyalar

```
Baslat.bat                  çift tıkla, sunucu açılır
Telefon-Hoparlor.bat        SADECE TELEFON modu (kulaklık gerekmez, VB-CABLE ister)
Aygitlari-Listele.bat       ses aygıtlarını gösterir
sunucu.py                   sunucu
sescikis.py                 Windows varsayılan çıkış aygıtını okur/değiştirir
web/index.html              telefon arayüzü
vbcable-kur.ps1             sanal ses kablosu kurulumu (bir kez)
guvenlik-duvari-izni.ps1    8443 portunu ev ağına açar
sertifika/                  otomatik üretilen HTTPS sertifikası
```

`python sescikis.py` tek başına çalıştırılırsa aktif oynatma aygıtlarını ve
hangisinin varsayılan olduğunu listeler.

Gereken Python paketleri ilk çalıştırmada otomatik kurulur:
`numpy aiohttp soundcard sounddevice cryptography qrcode`

---

## Gereksinimler

Windows (WASAPI ve sanal ses kablosu kullanıyor). Python paketleri: `aiohttp comtypes cryptography numpy qrcode soundcard sounddevice`
