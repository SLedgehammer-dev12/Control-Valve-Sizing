# Control Valve Sizing v3.3.4

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması.

> Geçmiş sürümlerin what's new ve release notları: [CHANGELOG.md](CHANGELOG.md)

## Bu sürümde yeni

### Kurulum paketleri

- **Windows kurulum sihirbazı**: `ControlValveSizing_Setup_<version>.exe` (Inno Setup). Kullanıcı dizinine kurulur, yönetici izni gerektirmez; Başlat menüsü ve masaüstü kısayolu oluşturur.
- **Taşınabilir Windows zip**: `ControlValveSizing_windows_x86_64_<version>.zip`.
- **macOS DMG**: `ControlValveSizing_macos_arm64_<version>.dmg`; içinde `.app` ve `/Applications` kısayolu bulunur.
- **Web Docker imajı**: `ghcr.io/sledgehammer-dev12/control-valve-sizing:<version>` ve `latest`; non-root kullanıcı ve `/_stcore/health` healthcheck.
- Tüm çıktı dosyalarının adı sürüm numarasını içerir. Release iş akışı `vX.Y.Z` etiketini `valve_sizing.__version__` ile karşılaştırır.

### Arayüz

- **Hizmet sekmeleri**: Masaüstünde Notebook, web'de segmented butonlar; sekme ve açıklık slider'ı birbiriyle senkron.
- **Birim dönüştürücü**: Masaüstünde dialog, web'de sidebar; `units.py` içindeki merkezi birim haritalarını kullanır.
- **Testler**: Sürüm/meta veri tutarlılığı ve sürüm numaralı release çıktıları için testler eklendi.

## Windows — Kurulum ve SmartScreen

- `ControlValveSizing_Setup_<version>.exe` dosyasını çalıştırın ve kurulum sihirbazını izleyin.
- Alternatif olarak `ControlValveSizing_windows_x86_64_<version>.zip` dosyasını indirip açabilir, `ControlValveSizing.exe`'yi doğrudan çalıştırabilirsiniz.
- Dağıtım imzasız olduğundan **SmartScreen "More info → Run anyway"** isteyebilir. Bu normaldir; uygulama
  antivirüs/antimalware alarmını azaltmak için tek dosyalık değil klasör tabanlı (one-dir) ve UPX'siz derlenmiştir.
- Kurulum sihirbazı varsayılan olarak kullanıcı dizinine kurar; yönetici izni gerekmez.

## macOS — Kurulum ve Gatekeeper

1. DMG'i açın, `ControlValveSizing.app`'i `/Applications`'a taşıyın.
2. Uygulama noter onaylı (notarized) olmadığından ilk açılışta Gatekeeper uyarısı çıkar. Şu adımlardan birini kullanın:
   - **Sağ tık → Aç** → "Aç" deyin, veya
   - Terminalden karantina bayrağını kaldırın:
     ```bash
     xattr -dr com.apple.quarantine "/Applications/ControlValveSizing.app"
     ```

## Web — Docker

```bash
docker run --rm -p 8501:8501 ghcr.io/sledgehammer-dev12/control-valve-sizing:<version>
```

Tarayıcıda `http://localhost:8501` adresini açın. İmaj hem sürüm hem `latest` etiketiyle yayınlanır.

## Sistem Gereksinimleri

- Windows 10 / 11 (64-bit)
- macOS 12+ (Apple Silicon / M1-M4)
- Web: Docker 24+ (veya `docker compose up --build`)
