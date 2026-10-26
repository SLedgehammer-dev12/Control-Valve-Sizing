# Control Valve Sizing v3.5.1

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması.

> Geçmiş sürümlerin what's new ve release notları: [CHANGELOG.md](CHANGELOG.md) veya [docs/releases/](docs/releases/index.md)

## Bu sürümde yeni

### Gaz ve Buhar Boyutlandırma Motoru IEC 60534-2-1 Düzeltmesi
- **Doğrudan Standart Normal Debi ($Q_N$) İletimi**:
  - `valve_sizing.py` içerisindeki gaz ve buhar boyutlandırma hesaplamalarında, IEC 60534-2-1 Denklem 8a motoruna aktüel debi yerine standart normal debi ($Q_N$, $273.15\text{ K}$, $1\text{ atm}$) aktarıldı.
  - Giriş basıncının ($P_1$) iki kez bölünmesi hatası giderildi; böylece yüksek ve orta basınçlı gaz/buhar hatlarında $Cv$ değerinin ~12.7 kata kadar küçük hesaplanması sorunu tamamen çözüldü.
  - BOTAŞ Marmaraereğlisi LNG Terminali gerçek vana veri sayfaları (ör. `5510-PV-101`, `5070-PV-004`, `5070-PV-007`) ile yapılan çapraz doğrulamalarda hesaplama sapması **%0.1 - %1.6** aralığına oturtuldu.
- **Buhar İçin IEC Denklem 6a Doğrudan Kütlesel Formülasyon Uyumu**:
  - Buhar servisi, normal yoğunluk üzerinden gaz motoruna entegre edilerek IEC 60534-2-1 Clause 8.3 Eq. 6a doğrudan kütlesel buhar formülasyonu ile **%0.27** seviyesinde tam örtüşmeye kavuşturuldu.
- **Küçük $\Delta P$ ve Ekstrem Redüksiyon Fallback Koruması**:
  - Çok düşük fark basınçlarda ($0.001\text{ bar}$) veya vana çapının boru çapından büyük olduğu durumlarda fluids piping iterasyonunun kilitlenmesini (`math domain error`) engelleyen koruma sağlandı.

### Windows Web Arayüzü Başlatıcı (Launcher) Kararlılığı
- Windows ortamında pencere (windowed/noconsole) modunda çalıştırıldığında Uvicorn loglayıcısının standart çıktı akışı bulamaması (`AttributeError: 'NoneType' object has no attribute 'isatty'`) sorunu giderildi; `sys.stdout` ve `sys.stderr` akışları güvenli sahte akışlara (null/log stream) yönlendirildi.

### Test ve Doğrulama
- **Pytest**: 725/725 test %100 başarılı.
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

### macOS Notları
- DMG imajını açıp uygulamayı `/Applications` klasörüne sürükleyin.
- Noter onayı (notarization) bulunmadığından ilk açılışta **Sağ tık → Aç** yapın veya terminalde karantinayı kaldırın:
  ```bash
  xattr -dr com.apple.quarantine "/Applications/ControlValveSizing_Web.app"
  ```
