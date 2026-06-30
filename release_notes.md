# Control Valve Sizing v1.1.0

IEC 60534 / ISA tabanlı kontrol vanası boyutlandırma uygulaması — 22 bug fix.

## Düzeltmeler

### Kritik
- **Proje kaydet/yükle**: Servis adı büyük/küçük harf duyarsız yapıldı. Masaüstü (`"liquid"`) ve web (`"Liquid"`) projeleri artık karşılıklı yüklenebilir.
- **Eksik LRU cache**: `get_pure_fluid_state`'a `@lru_cache(256)` eklendi. CoolProp çağrıları tekrarlanmıyor.
- **Kavitasyon indeksi**: IEC 60534-8-4 standardına geçildi (`sigma = (P1-Pv)/(P1-P2)`). Daha önce 2 farklı formül vardı.
- **Steam uyarısı**: Overflow durumunda CoolProp düşüş uyarısı ezilmiyor, birleştiriliyor.
- **Gaz karışımı fallback**: `k_avg` hep `1.4` döndüren sahte döngü kaldırıldı.

### Entegrasyon
- **Vana gürültüsü (IEC 60534-8)**: Liquid/Gas/Steam sonuçlarına `noise_db` alanı eklendi. `valve_noise.py` motor'a bağlandı.
- **Aktüatör boyutlandırma**: Vana seçimi sonrası otomatik `actuator_thrust_n` hesaplanıyor. `actuator_sizing.py` motor'a bağlandı.
- **Web UI**: Referans basınç kaldırıldı, giriş basıncı tek kaynak. Akışkan özellikleri doğru basınçta hesaplanıyor.

### Akışkan özellikleri
- **İdeal gaz viskozitesi**: Sabit `1.5e-5` → sıcaklık düzeltmeli `mu_ref * sqrt(T/300)`. Yüksek sıcaklıkta daha doğru.
- **Flaş buhar fraksiyonu**: Kaba `DeltaT_sat = DeltaP * 2.0` → Clausius-Clapeyron (`dT/dP = RT^2/Ph_fg`).
- **Chemicals hata loglama**: Sessiz hata yutma → `logger.debug()` eklendi.
- **Chemicals cache sınırı**: Sınırsız büyüme → max 512 giriş.

### Diğer
- `get_vendor_definition`: Çıplak `KeyError` → `ValueError("Bilinmeyen vendor...")`
- `cavitation_severity`: İngilizce → Türkçe etiketler
- `select_valve_size`: `DeprecationWarning` eklendi
- `.dockerignore` eklendi
- `pyproject.toml`: Geçersiz `test_app_integration.py` referansı silindi
- CI fallback komutu genişletildi
- CoolProp versiyon kısıtı gevşetildi (`<8.0` → `<9.0`)

## Sistem Gereksinimleri
- Windows 10 / 11 (64-bit)
- Standalone .exe — kurulum gerektirmez
