# Release Notları — Dizin

Control Valve Sizing sürümlerinin what's new ve release notları. Her sürüm kendi dosyasında saklanır;
`release_notes.md` (repo kökü) güncel sürümün GitHub Release body'sidir.

| Sürüm | Tarih | Öne Çıkanlar |
|---|---|---|
| [v3.2.0](v3.2.0.md) | 2026-08-20 | Hesaplama doğrulama paketi (12 senaryo, 12/12 PASS) |
| [v3.1.0](v3.1.0.md) | 2026-08-18 | Sektör birim seçicileri, canlı hesaplama, Windows + macOS release pipeline |
| [v3.0.0](v3.0.0.md) | 2026-08-18 | IEC benchmark'ları, gürültü/aktüatör, açıklık & marj, flashing Cv, vana spec & trim |
| [v2.0.0](v2.0.0.md) | 2026-05-18 | `SizingResult` dataclass, steam IEC hizalaması, `_size_iteration()`, LRU cache |
| [v1.1.0](v1.1.0.md) | 2026-07-01 | 22 bug fix, gürültü/aktüatör entegrasyonu, IEC kavitasyon |
| [v1.0.0](v1.0.0.md) | 2026-06-05 | İlk sürüm: liquid/gas/steam sizing, CoolProp, Fisher katalog, dual UI |

## Yayın Tarihçesi

- **v3.1.0+** sürümleri GitHub Actions ile **Windows (x86_64)** ve **macOS (Apple Silicon/arm64)** için
  PyInstaller paketleri olarak derlenip yayınlanır (`ControlValveSizing_windows_x86_64.zip`,
  `ControlValveSizing_macos_arm64.zip`).
- **v1.0.0 / v1.1.0** yalnızca Windows için tek `.exe` ile yayınlanmıştır.
- **v2.0.0 / v3.0.0** kaynak sürümlerdir; paketlenmiş ikili dosya yayınlanmamıştır.

## Paket Kurulum Notları

- Windows: ZIP'i açın, `ControlValveSizing.exe`'yi çalıştırın. İmzasız olduğu için SmartScreen
  **"More info → Run anyway"** isteyebilir.
- macOS: `.app`'i `/Applications`'a taşıyın; noter onayı olmadığı için ilk açılışta karantina bayrağını
  kaldırın: `xattr -dr com.apple.quarantine "/Applications/ControlValveSizing.app"`