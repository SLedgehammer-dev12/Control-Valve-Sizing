# Control Valve Sizing v3.4.0

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması.

> Geçmiş sürümlerin what's new ve release notları: [CHANGELOG.md](CHANGELOG.md) veya [docs/releases/](docs/releases/index.md)

## Bu sürümde yeni

### Web Sürümü Bağımsız Paketleme (macOS Apple Silicon & Windows)

- **macOS (Apple Silicon M1+) Web UI Disk İmajı**: `ControlValveSizing_Web_macos_arm64_<version>.dmg`
  - `.app` ve `/Applications` kısayolu içerir.
  - Açıldığında FastAPI/Uvicorn motorunu arka planda başlatır ve varsayılan tarayıcıda Web UI'ı otomatik açar.
- **Windows Web UI Kurulum Sihirbazı**: `ControlValveSizing_Web_Setup_<version>.exe` (Inno Setup, yönetici izni gerektirmez).
- **Windows Web UI Taşınabilir Paket**: `ControlValveSizing_Web_windows_x86_64_<version>.zip`.
- **Otomatik Port Tespiti**: 8501 portu meşgulse çakışmayı önlemek için müsait ilk port dinamik olarak seçilir.
- **Minimalist Durum Penceresi**: Arka plan sunucusunu izleme, tarayıcıyı yeniden açma ve tek tıkla kapatma imkanı.

### Küresel Vana Üretici Veritabanı Genişletmesi

- **Masoneilan (ABD)**: 21000 single-port globe, 41005 balanced cage globe, Camflex II rotary plug.
- **Flowserve (ABD)**: Valtek Mark One globe, MaxFlo 4 eccentric plug rotary.
- **IMI CCI / Bopp & Reuther (Avrupa)**: Ağır hizmet proses kontrol vanaları serisi.
- **WZI (Wuzhong Instrument - Çin)**: Enerji ve kimya sektörü yüksek performanslı kontrol vanaları serisi.
- **Azbil (Japonya)**: ACTIVAL ve yüksek hassasiyetli cage/globe serisi kontrol vanaları.

### Paralel Split-Range Vana Boyutlandırma Motoru ($R_{Cv} > 50:1$)

- $Q_{max} / Q_{min} > 50$ aşırı turndown koşullarında tek vana kısıtını çözen otomatik paralel çift vana boyutlandırması.
- Hassas düşük debi mikro trim vanası ve ana kontrol vanası optimizasyonu; geçiş debisi ve histerezis bandı önerileri.

### IEC 60534-2-1 ve Termodinamik Düzeltmeleri

- IEC 60534-2-1 Denklem 6a ($N_6 = 27.3$) ile doğrudan buhar kütlesel debi hesabı.
- Boru reducer/expander montajında $\Delta P_{max}$ ve $F_L$ kavitasyon katsayılarının standart revizyonu.

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
