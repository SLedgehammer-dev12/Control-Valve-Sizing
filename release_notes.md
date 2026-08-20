# Control Valve Sizing v3.2.0

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması.

## İndirmeler

| Platform | Dosya | Not |
|---|---|---|
| Windows (x86_64) | `ControlValveSizing_windows_x86_64.zip` | Kurulum gerektirmez, klasörü açıp `ControlValveSizing.exe` çalıştırın |
| macOS (Apple Silicon / arm64) | `ControlValveSizing_macos_arm64.zip` | `.app` dosyasını `/Applications`'a taşıyın |

## Bu sürümde yeni

- **Hesaplama doğrulama paketi** — motorun doğruluğunu 12 bağımsız senaryo ile teyit eder:
  - Sıvı: kritik altı, choking, flashing (HEM kendi-tutarlılığı), yüksek hız / erozyon
  - Gaz: IEC yayınlı CO₂ örneği (63.34), analitik choked hava, H₂-NG %20 CoolProp karışımı
  - Buhar: kızgın buhar 12→8 bar(a), doygunluğa yakın 6→3 bar(a)
  - Çapraz kontroller: SI↔US birim eşdeğerliği, %15 tasarım marjı, Fisher vendor katalogu
  - Tüm senaryolar bağımsız referanslarla < %0.05 sapma — **12/12 PASS**
- Hesaplamalar, motoru test etmek isteyenler için `python verify_scenarios.py` ile yeniden çalıştırılabilir.

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