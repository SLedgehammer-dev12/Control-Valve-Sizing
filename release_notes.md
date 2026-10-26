# Control Valve Sizing v3.5.2

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması.

> Geçmiş sürümlerin what's new ve release notları: [CHANGELOG.md](CHANGELOG.md) veya [docs/releases/](docs/releases/index.md)

## Bu sürümde yeni

### Çok Bileşenli Hidrokarbon Karışımlarında Peng-Robinson VLE Flaş Yoğuşma Modeli
- **Wilson Başlangıç Tahmini & Rachford-Rice Çözücüsü**:
  - Doğal gaz ve çok bileşenli hidrokarbon karışımlarının genleşme veya kriyojenik soğuma altında yoğuşma fraksiyonunu gerçeğe en yakın şekilde belirlemek üzere Peng-Robinson Kübik Durum Denklemi (PR-EOS) tabanlı $P$-$T$ flaş algoritması eklendi.
  - Kritik sıcaklık ($T_c$), kritik basınç ($P_c$) ve asentrik faktör ($\omega$) parametreleri kullanılarak Wilson K-faktörü başlangıç tahmini oluşturulur ve Rachford-Rice denklemi çözülerek buhar fazı mol kesri ($\beta$) ile sıvılaşma fraksiyonu tam olarak belirlenir.
  - Çözülen denge kökleri üzerinden yoğuşan sıvının gerçek yoğunluğu (ör. -150 °C / 6 bar(a) koşullarında doğal gaz yoğuşmasıyla ~423 kg/m³ LNG yoğunluğu) hesaplanır.

### Dinamik Değerlendirme & Gelişmiş İki Fazlı Akış (HEM) Kararlılığı
- **Dinamik Hesaplama Takılmalarının Giderilmesi**:
  - Web UI'da kullanıcı veri girerken arayüzün takılmasını veya sunucunun HTTP 400/500 hatası döndürmesini önleyen koruyucu sınırlar getirildi.
  - Gaz akışında yoğuşma meydana geldiğinde (`advanced_two_phase: true`) boyutlandırma doğrudan yoğuşan sıvı faz üzerinden Homojen Denge Modeli (HEM) analizleriyle kesintisiz yürütülür.
  - Kaynayan/flaş eden sıvılarda giriş basıncının efektif buhar basıncından düşük kaldığı ekstrem durumlarda vana iterasyon kilitlenmesi engellendi.

### İnteraktif Mühendislik Parametre Bilgi Modalı (Info Dialog)
- **Teknik Detaylar ve Ara Değerler İçin Zengin Açıklamalar**:
  - Kullanıcı arayüzünde Ara Değerler tablosundaki info butonlarına veya tablo başlıklarına tıklandığında açılan interaktif modal diyaloğu eklendi (`<dialog id="info-modal">`).
  - Her bir mühendislik parametresi için Türkçe tanım, standart sembol, IEC/ISA mühendislik formülü, birim ve pratik mühendislik yorumu sunuldu.
  - Klavye erişilebilirliği (ESC ile kapatma, Enter/Boşluk ile açma) ve modern cam (glassmorphic) kart tasarımı sağlandı.

### Kullanıcı Arayüzü & Boru Çapı Netliği
- **Net İç Çap Vurgusu**:
  - Boru giriş ve çıkış çapı alan etiketleri kullanıcıların nominal çap (NPS/DN) yerine gerçek iç çapı girmelerini netleştirmek adına **"Hat giriş iç çapı D1 [mm]"** ve **"Hat çıkış iç çapı D2 [mm]"** olarak güncellendi.
- **İşletme & Proses Koşulları Tek Satır Düzeni**:
  - İşletme & Proses Koşulları bölümündeki giriş alanları (Debi, Sıcaklık, Giriş Basıncı P1, ΔP Rozeti, Çıkış Basıncı P2) masaüstü ekranlarda tek bir yatay satırda yan yana dizildi; mobil ve dar ekranlar için esnek grid korundu.

### Test ve Doğrulama
- **Pytest**: 765/765 test %100 başarılı (E2E Web UI test paketi ve Peng-Robinson VLE testleri dahil).
- **Bağımsız IEC Doğrulama (`verify_scenarios.py`)**: 12/12 senaryo %100 başarılı.
- **Endüstriyel Tesis Doğrulama (`verify_50_scenarios.py`)**: 52/52 senaryo %100 başarılı.

---

## İndirilen Paketler ve Kurulum

| Sürüm / Paket | Platform | Dosya |
|---|---|---|
| **Web UI Disk İmajı** | macOS (Apple Silicon M1+) | `ControlValveSizing_Web_macos_arm64_<version>.dmg` |
| **Web UI Kurulum Sihirbazı** | Windows (x86_64) | `ControlValveSizing_Web_Setup_<version>.exe` |
| **Web UI Taşınabilir** | Windows (x86_64) | `ControlValveSizing_Web_windows_x86_64_<version>.zip` |
| **Web Konteyner (Docker)** | Linux / Container | `ghcr.io/sledgehammer-dev12/control-valve-sizing:<version>` |

### Windows Notları
- `.exe` kurulum dosyasını çalıştırın ve kurulum sihirbazını izleyin.
- İmzasız açık kaynak paket olduğu için **SmartScreen "More info → Run anyway"** uyarısı verebilir.
