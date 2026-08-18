# Control Valve Sizing v3.1.0

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması.

## İndirmeler

| Platform | Dosya | Not |
|---|---|---|
| Windows (x86_64) | `ControlValveSizing_windows_x86_64.zip` | Kurulum gerektirmez, klasörü açıp `ControlValveSizing.exe` çalıştırın |
| macOS (Apple Silicon / arm64) | `ControlValveSizing_macos_arm64.zip` | `.app` dosyasını `/Applications`'a taşıyın |

## Bu sürümde yeni

- **Sektör birim seçicileri** (petrol / doğalgaz / enerji):
  - Sıcaklık: °C, °F, K
  - Basınç: bar(a)/bar(g), psi(a)/psi(g), kPa(a), MPa(a), atm(a)
  - Sıvı debi: m³/h, US gpm, L/min, m³/d, US bbl/d, kg/h
  - Gaz debi: Nm³/h, Sm³/h, scfh, MMSCFD, m³/h (actual), kg/h
  - Buhar debi: kg/h, t/h, lb/h, kg/s
- **Canlı hesaplama**: Girdi veya birim değiştirdiğinizde sonuç anında güncellenir (butona gerek yok).
- Gauge basınçlar 1.01325 bar atmosfer basıncıyla mutlak değere çevrilir.
- Seçilen birimler proje kaydet/yükle ile saklanır.

## Windows — Kurulum ve SmartScreen

- ZIP'i açın, `ControlValveSizing.exe`'yi çalıştırın.
- Dağıtım imzasız olduğundan **SmartScreen "More info → Run anyway"** isteyebilir. Bu normaldir; uygulama
  antivirüs/antimalware alarmını azaltmak için tek dosyalık değil klasör tabanlı (one-dir) ve UPX'siz derlenmiştir.
- Kurulum gerektirmez; taşınabilirdir.

## macOS (Apple Silicon) — Kurulum ve Gatekeeper

1. ZIP'i açın, `ControlValveSizing.app`'i `/Applications`'a taşıyın.
2. Uygulama noter onaylı (notarized) olmadığından ilk açılışta Gatekeeper uyarısı çıkar. Şu adımlardan birini kullanın:
   - **Sağ tık → Aç** → "Aç" deyin, veya
   - Terminalden karantina bayrağını kaldırın:
     ```
     xattr -dr com.apple.quarantine "/Applications/ControlValveSizing.app"
     ```
3. uygulama Apple Silicon için ad-hoc imzalanmıştır (arm64 zorunluluğu), doğrulama:
   ```
   codesign --verify --deep --strict "/Applications/ControlValveSizing.app"
   ```

> Not: Windows Authenticode ve macOS noter onayı için bir geliştirici sertifikası gereklidir.
> Sertifika eklendiğinde uyarılar tamamen kalkar; bu sürümde ad-hoc imza + karantina talimatı kullanılmaktadır.

## Sistem Gereksinimleri

- Windows 10 / 11 (64-bit)
- macOS 12+ (Apple Silicon / M1-M4)