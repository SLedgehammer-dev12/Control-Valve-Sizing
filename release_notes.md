# Control Valve Sizing v3.3.3

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması.

> Geçmiş sürümlerin what's new ve release notları: [CHANGELOG.md](CHANGELOG.md)

## İndirmeler

| Platform | Dosya | Not |
|---|---|---|
| Windows (x86_64) | `ControlValveSizing_windows_x86_64.zip` | Kurulum gerektirmez, klasörü açıp `ControlValveSizing.exe` çalıştırın |
| macOS (Apple Silicon / arm64) | `ControlValveSizing_macos_arm64_3.3.3.dmg` | DMG'i açıp `.app` dosyasını `/Applications`'a taşıyın |

## Bu sürümde düzeltilenler

- **Windows exe açılış hatası giderildi**: CoolProp 8.x'in `coolprop.libs` altındaki MSVC runtime DLL'leri artık pakete dahil ediliyor; `ImportError: DLL load failed while importing CoolProp` hatası oluşmuyor.
- **Eksik `fpdf2` bağımlılığı eklendi**: PDF rapor modülü donmuş uygulamada da yüklenebiliyor.
- **macOS sürüm numarası**: `CFBundleShortVersionString` / `CFBundleVersion` 3.3.1 → **3.3.3** düzeltildi.
- **Masaüstü tooltip'leri**: `ToolTip` sınıfındaki hatalı `self.on_enter` / `self.on_leave` bağları düzeltildi.

## Bu sürümde yeni

### UI / UX İyileştirmeleri
- **Tooltip sistemi**: Hem web hem masaüstü arayüzde tüm giriş alanlarına bilgilendirici tooltip'ler (ⓘ)
- **Collapsible bölümler**: Sıvı/Gaz/Buhar girişleri gruplanabilir panellere alındı
- **Sonuç geçmişi / karşılaştırma**: Son 3 benzersiz hesaplama yan yana karşılaştırılabilir
- **3D görselleştirme**: Vana karakteristik eğrisi 3D yüzey (Açıklık × Tasarım Marjı × Cv)
- **Masaüstü klavye kısayolları**: Enter = Hesapla, Esc = Varsayılana Sıfırla

### Raporlama
- **PDF rapor exportu**: Karakteristik eğri grafiği + renk kodlu "Key Highlights" özet şeridi (gürültü, aktöör marjı, açıklık, boğulma)
- **Gaz Z duyarlılık paneli**: Z faktörü belirsizliğinin (±0.05) gerekli Cv'ye etkisi

## Windows — Kurulum ve SmartScreen

- ZIP'i açın, `ControlValveSizing.exe`'yi çalıştırın.
- Dağıtım imzasız olduğundan **SmartScreen "More info → Run anyway"** isteyebilir. Bu normaldir; uygulama
  antivirüs/antimalware alarmını azaltmak için tek dosyalık değil klasör tabanlı (one-dir) ve UPX'siz derlenmiştir.
- Kurulum gerektirmez; taşınabilirdir.

## macOS — Kurulum ve Gatekeeper

1. DMG'i açın, `ControlValveSizing.app`'i `/Applications`'a taşıyın.
2. Uygulama noter onaylı (notarized) olmadığından ilk açılışta Gatekeeper uyarısı çıkar. Şu adımlardan birini kullanın:
   - **Sağ tık → Aç** → "Aç" deyin, veya
   - Terminalden karantina bayrağını kaldırın:
     ```bash
     xattr -dr com.apple.quarantine "/Applications/ControlValveSizing.app"
     ```

## Sistem Gereksinimleri

- Windows 10 / 11 (64-bit)
- macOS 12+ (Apple Silicon / M1-M4)
