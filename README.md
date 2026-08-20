# Control Valve Sizing

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması. Liquid, gas ve steam servisleri için Cv/Kv hesabı, vana seçimi, vendor katalog entegrasyonu, proje kaydetme/yükleme ve Markdown rapor üretimi içerir. Dual UI: Tkinter masaüstü + Streamlit web.

## Modüller

| Modül | Açıklama |
|---|---|
| `valve_sizing.py` | Çekirdek sizing motoru (liquid/gas/steam), dataclass'lar, `_size_iteration()` candidate-valve döngüsü |
| `fluid_properties.py` | CoolProp HEOS akışkan özellikleri (Z, MW, k, viskozite, yoğunluk), gaz karışımı, LRU cache |
| `vendor_catalog.py` | Emerson Fisher / Metso / SAMSON / ARCA katalogları (12 representative trim) |
| `config.py` | Ortak sabitler: `GAS_PRESETS` (enerji gazları dahil), `GAS_PRESET_NAMES`, `DEFAULT_GAS_ROWS` |
| `project_io.py` | JSON proje kaydetme/yükleme, schema versioning + doğrulama |
| `reporting.py` | Markdown rapor üretimi |
| `two_phase.py` | Flashing/iki-fazlı Cv tahmini (HEM) |
| `valve_selection.py` | ANSI basınç sınıfı, sızdırmazlık sınıfı, fail-safe ve vana spec önerileri |
| `trim_guidance.py` | Rule-based trim önerileri (anti-flash, anti-kavitasyon, düşük gürültü, vb.) |
| `thermal_expansion.py` | Boru hattı termal genleşme, termal gerilme ve loop uzunluğu |
| `valve_noise.py` | IEC 60534-8-4 aerodinamik gürültü tahmini |
| `actuator_sizing.py` | Aktüatör boyutlandırma yardımcıları |
| `units.py` | Pint tabanlı birim dönüşümleri |
| `app_desktop.py` | Tkinter masaüstü arayüzü |
| `app_web.py` | Streamlit web arayüzü |

## Hızlı Başlangıç

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

- **Web UI:** `streamlit run app_web.py`
- **Desktop UI:** `python app_desktop.py`
- **Paketlenmiş giriş noktaları:** `valve-sizing-web`, `valve-sizing-desktop`

## Yayınlar (Desktop)

`v*` etiketine push edildiğinde GitHub Actions **Windows (x86_64)** ve **macOS (Apple Silicon/arm64)** için PyInstaller paketlerini derler ve Release'e ekler. AV alarmını azaltmak için paketler tek dosyalık değil klasör tabanlı (one-dir) ve UPX'siz derlenir; macOS paketi ad-hoc imzalıdır. Detaylar ve SmartScreen/Gatekeeper talimatları için `release_notes.md`'ye bakın.

```powershell
git tag v3.2.0 && git push origin v3.2.0
```

## Test

```powershell
python -m pytest -q        # 328 test
python -m pytest --cov=. --cov-report=term -q
ruff check .
mypy . --ignore-missing-imports
python verify_scenarios.py  # 12-senaryolu motor doğrulama raporu (12/12 PASS)
```

## Özellikler

- **Sizing:** IEC 60534-2-1 (liquid), IEC 60534-2-1 gas (choked) ve steam (CoolProp yoğunluk + gas yolu)
- **Açıklık & tasarım marjı:** `design_margin_pct`, doğrusal/equal-percentage karakteristik, rangeability kontrolü, `opening_percent`
- **Flashing / iki-fazlı:** HEM yaklaşımı ile `flashing_cv_estimate` (quality_x, iki-fazlı yoğunluk, Cv çarpanı)
- **Vana spec:** ANSI basınç sınıfı, sızdırmazlık sınıfı (I-VI), fail-safe yönü, trim önerileri
- **Hız & erozyon:** Boru içi hız, Mach sayısı, API 14E erozyon hızı uyarıları
- **Enerji gazları:** H2-NG blend'leri (%5/%10/%20/%50), syngas, H2-CO2 preset'leri (ideal-gaz fallback)
- **Gürültü:** IEC 60534-8-4 aerodinamik gürültü (SPL)
- **Boru hattı:** Termal genleşme, termal gerilme, expansion loop uzunluğu (web UI bölümü)

## Sürüm Geçmişi

- **3.2.0 (current):** Hesaplama doğrulama paketi — 12 bağımsız senaryo (sıvı kritik altı/choked/flashing/hız, IEC yayınlı CO₂, analitik choked hava, H₂-NG %20, kızgın/doygunluğa yakın buhar, SI↔US birim, %15 marj, Fisher katalog) bağımsız referanslarla < %0.05 sapma, 12/12 PASS — 328 test, ruff + mypy temiz
- **3.1.0:** Sektör birim seçicileri (°C/°F/K; bar/psi/kPa/MPa/atm mutlak+gauge; m³/h-gpm-bbl-d gibi akış birimleri; Nm³/h-sm³/h-scfh-MMSCFD; t/h-lb/h), web + desktop'ta canlı hesaplama (butonsuz), birimlerin projede saklanması, Windows + macOS Apple Silicon için PyInstaller release pipeline (one-dir, UPX'siz, ad-hoc imza) — 315 test, ruff + mypy temiz
- **3.0.0:** IEC doğrulama benchmark'ları, gürültü/aktüatör çıktıları, FLP/xTP tutarlılığı, açıklık & tasarım marjı, flashing Cv, vana spec & trim önerileri, hız/erozyon, enerji gaz preset'leri, termal genleşme web bölümü, Streamlit preset düzeltmesi, proje schema versioning, paketleme metadata'sı — 249 test, ruff + mypy temiz
- **2.0.0:** `SizingResult` dataclass, steam sizing IEC hizalaması, `_size_iteration()` yardımcısı, LRU cache, `.opencode/` skills/agents, Dockerfile, coverage eşiği
- **1.x:** Vendor katalog, steam sizing, sıvı preset seçici, pipe reducer, proje I/O, Markdown rapor, config merkezileştirme, edge case testleri