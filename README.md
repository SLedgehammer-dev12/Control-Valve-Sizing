# Control Valve Sizing

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması. Liquid, gas ve steam servisleri için Cv/Kv hesabı, vana seçimi, vendor katalog entegrasyonu, proje kaydetme/yükleme ve Markdown rapor üretimi içerir. Arayüzler: Tkinter masaüstü + FastAPI/Three.js tarayıcı arayüzü (Streamlit alternatif olarak korunur).

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
| `valve_curve.py` | Inherent/kurulu karakteristik eğrileri ve installed gain |
| `valve_3d.py` | Parametrik 3D vana mesh üretimi (Plotly Mesh3d) |
| `valve_noise.py` | IEC 60534-8-4 aerodinamik gürültü tahmini |
| `actuator_sizing.py` | Aktüatör boyutlandırma yardımcıları |
| `units.py` | Pint tabanlı birim dönüşümleri |
| `app_desktop.py` | Tkinter masaüstü arayüzü |
| `api.py` | FastAPI backend: sizing, birim dönüşümü, vendor, 3D mesh |
| `webapp/` | Tarayıcı arayüzü (HTML/CSS/JS + Three.js) |
| `app_web.py` | Streamlit web arayüzü (alternatif) |

## Hızlı Başlangıç

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

- **Web UI (tarayıcı):** `uvicorn api:app --reload --port 8501` → http://127.0.0.1:8501
- **Streamlit (alternatif):** `streamlit run app_web.py`
- **Desktop UI:** `python app_desktop.py`
- **Paketlenmiş giriş noktaları:** `valve-sizing-web`, `valve-sizing-desktop`

## Yayınlar

`vX.Y.Z` etiketine push edildiğinde GitHub Actions üç hedefi derler. Sürüm numarası etiketten okunur, `valve_sizing.__version__` ile karşılaştırılır ve tüm kurulum dosyalarının adına eklenir:

| Platform | Çıktı | Açıklama |
|---|---|---|
| Windows (x86_64) | `ControlValveSizing_Setup_<version>.exe` | Inno Setup kurulum sihirbazı |
| Windows (taşınabilir) | `ControlValveSizing_windows_x86_64_<version>.zip` | Kurulum gerektirmez |
| macOS (Apple Silicon / arm64) | `ControlValveSizing_macos_arm64_<version>.dmg` | `.app` + `/Applications` kısayolu |
| Web (Docker) | `ghcr.io/sledgehammer-dev12/control-valve-sizing:<version>` | FastAPI + Three.js imajı; ayrıca `latest` |

AV alarmını azaltmak için masaüstü paketleri tek dosyalık değil klasör tabanlı (one-dir) ve UPX'siz derlenir; macOS paketi ad-hoc imzalıdır. Detaylar ve SmartScreen/Gatekeeper talimatları için `release_notes.md`'ye bakın.

GHCR imajının herkes tarafından çekilebilmesi için ilk yayından sonra GitHub → Packages → Package settings → Change visibility → **Public** ayarlanmalıdır.

Tüm sürümlerin what's new ve release notları: [`docs/releases/index.md`](docs/releases/index.md)

```bash
git tag v3.3.4 && git push origin v3.3.4
```

Yerel derleme:

```powershell
pyinstaller app_desktop.spec
iscc /DMyAppVersion=3.3.4 installer.iss
docker compose up --build
```

## Web Arayüzü

```powershell
uvicorn api:app --reload --port 8501
```

- Tarayıcı: http://127.0.0.1:8501
- Three.js ve OrbitControls `webapp/vendor/` altından yerel olarak servis edilir; CDN gerekmez.
- CSP importmap hash’i `test_api.py` ile doğrulanır; `/docs` varsayılan kapalıdır (`CVS_ENABLE_DOCS=1` ile açılır).
- Geliştirme sırasında headless Chromium ile manuel smoke testi çalıştırıldı; otomatik tarayıcı harness’ı yoktur. Ekran okuyucu ve gerçek mobil cihaz testi ayrıca yapılmalıdır.

## Gaz Akışkan Notları

- **Nm³/h** referansı 0 °C / 1.01325 bar(a), **Sm³/h** 15 °C, **scfh/MMSCFD** 60 °F bazındadır.
- **m³/h (actual)** ve **kg/h** dönüşümleri proses basıncı ve sıcaklığı gerektirir; `kg/h` ayrıca yoğunluk ister.
- Manuel gaz özellikleri kullanılacaksa **MW, k, Z ve viskozite birlikte** girilmelidir; eksik/negatif değerler reddedilir.
- Bazı özel karışımlar için CoolProp HEOS yerine ideal-gaz fallback kullanılabilir; sonuçlar mühendislik ön değerlendirmesi olarak doğrulanmalıdır.

## Test

```powershell
python -m pytest -q        # 666 test
python -m pytest --cov=. --cov-report=term -q  # coverage floor 94%
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

- **3.3.4 (current):** Proje kaydet/yükleme round-trip, mutlak Pv/Pc ve preset tazeliği, 3D Y-up/klavye/context toparlama, CSP + yerel Three.js, API gövde/statik yüzey sertleştirmesi, 666 test, %95.32 coverage, ruff + mypy temiz
- **3.3.3:** Windows/macOS paketleme ve sürüm düzeltmeleri, PDF/tooltip iyileştirmeleri
- **3.3.0:** İleri mühendislik ve güvenlik paketi — 52 endüstriyel senaryo doğrulama paketi (%100 PASS), çoklu çalışma noktası (Min/Norm/Max) zarf boyutlandırması, Joule-Thomson genleşmesi & Towler-Mokhatab hidrat dengesi, ISO 15848-1 / API 641 kaçak emisyon salmastra seçimi (PTFE chevron, kalıplanmış saf grafit, metal körüklü), API RP 14E erozyonel boru hızı sınırı & API 520 fail-open aşırı basınç tahliye kapasitesi, ISA Form 20 (ISA-S20.50) teknik veri sayfası üreticisi, IEC 60534-8 Whisper Trim / akustik ceket / difüzör iyileştirmesi ve AIV (>110 dBA) uyarısı, kriyojenik (-196 °C) / kanatlı / yüksek sıcaklık boyunları, NACE MR0175 / API 941 Nelson / Duplex 2205 / Monel gövde metalurjisi — 428 test, %91 coverage, ruff + mypy temiz
- **3.2.0:** Hesaplama doğrulama paketi — 12 bağımsız senaryo (sıvı kritik altı/choked/flashing/hız, IEC yayınlı CO₂, analitik choked hava, H₂-NG %20, kızgın/doygunluğa yakın buhar, SI↔US birim, %15 marj, Fisher katalog) bağımsız referanslarla < %0.05 sapma, 12/12 PASS — 328 test, ruff + mypy temiz
- **3.1.0:** Sektör birim seçicileri (°C/°F/K; bar/psi/kPa/MPa/atm mutlak+gauge; m³/h-gpm-bbl-d gibi akış birimleri; Nm³/h-sm³/h-scfh-MMSCFD; t/h-lb/h), web + desktop'ta canlı hesaplama (butonsuz), birimlerin projede saklanması, Windows + macOS Apple Silicon için PyInstaller release pipeline (one-dir, UPX'siz, ad-hoc imza) — 315 test, ruff + mypy temiz
- **3.0.0:** IEC doğrulama benchmark'ları, gürültü/aktüatör çıktıları, FLP/xTP tutarlılığı, açıklık & tasarım marjı, flashing Cv, vana spec & trim önerileri, hız/erozyon, enerji gaz preset'leri, termal genleşme web bölümü, Streamlit preset düzeltmesi, proje schema versioning, paketleme metadata'sı — 249 test, ruff + mypy temiz
- **2.0.0:** `SizingResult` dataclass, steam sizing IEC hizalaması, `_size_iteration()` yardımcısı, LRU cache, `.opencode/` skills/agents, Dockerfile, coverage eşiği
- **1.x:** Vendor katalog, steam sizing, sıvı preset seçici, pipe reducer, proje I/O, Markdown rapor, config merkezileştirme, edge case testleri