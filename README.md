# Control Valve Sizing

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması. Liquid, gas ve steam servisleri için Cv/Kv hesabı, vana seçimi, vendor katalog entegrasyonu, proje kaydetme/yükleme ve Markdown rapor üretimi içerir.

## Modüller

| Modül | Açıklama |
|---|---|
| `valve_sizing.py` | Çekirdek sizing motoru (liquid/gas/steam), dataclass'lar (`LiquidSizingInput`, `GasSizingInput`, `SteamSizingInput`) |
| `fluid_properties.py` | CoolProp HEOS ile akışkan özellikleri (Z, MW, k, viskozite, yoğunluk), gaz kompozisyon normalizasyonu |
| `vendor_catalog.py` | Emerson Fisher katalog (4 vana tipi, ValveSize/Cv serileri) |
| `config.py` | Ortak sabitler: `GAS_PRESETS`, `GAS_PRESET_NAMES`, `DEFAULT_GAS_ROWS` |
| `project_io.py` | JSON proje kaydetme/yükleme (Liquid/Gas/Steam) |
| `reporting.py` | Markdown rapor üretimi |
| `app_desktop.py` | Tkinter masaüstü arayüzü (3 servis, vendor, proje, rapor) |
| `app_web.py` | Streamlit web arayüzü |

## Hızlı Başlangıç

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

- **Web UI:** `streamlit run app_web.py`
- **Desktop UI:** `python app_desktop.py`

## Test

```powershell
pytest -v              # 44 test
.\run_smoke_test.ps1   # hızlı smoke test
```

## Sürüm Geçmişi

- **Phase 5 (current):** 44 test, edge case testleri, desktop entegrasyon testi, CI/CD yapılandırması
- **Phase 4:** Logging, magic number sabitleri, CoolProp LRU cache, steam/gas bug fix
- **Phase 3:** `config.py` merkezileştirme, GasSizingInput FL/Fd, kod tekrarı temizliği
- **Phase 2:** Vendor katalog, steam sizing, sıvı preset seçici, pipe reducer, proje I/O, Markdown rapor
- **Phase 1:** Kritik bug fix: `_diameter_mm_to_m` None kontrolü, `LiquidSizingInput`/`GasSizingInput` alan eklemeleri
