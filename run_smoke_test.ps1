# Smoke test — runs fast sanity checks and the full pytest suite
Write-Host "=== Smoke Test ===" -ForegroundColor Cyan

Write-Host "1. Import check" -ForegroundColor Yellow
python -c "import valve_sizing; import fluid_properties; import vendor_catalog; import config; import reporting; import project_io; print('OK')" 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED" -ForegroundColor Red; exit 1 }

Write-Host "2. Core sizing sanity" -ForegroundColor Yellow
python -c "
from valve_sizing import LiquidSizingInput, size_liquid_valve, GasSizingInput, size_gas_valve
r = size_liquid_valve(LiquidSizingInput(25, 8, 5, 998, 0.023, 220.64, 0.00089, fl=0.9, fd=1.0))
assert 10 < r['cv'] < 50, f'cv={r[\"cv\"]} out of range'
print(f'Liquid cv={r[\"cv\"]:.2f} OK')
r2 = size_gas_valve(GasSizingInput(800, 8, 6, 20, 18, 1.28, 1.1e-5, z=0.98, xt=0.7))
assert 50 < r2['cv'] < 500, f'cv={r2[\"cv\"]} out of range'
print(f'Gas cv={r2[\"cv\"]:.2f} OK')
print('OK')
" 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED" -ForegroundColor Red; exit 1 }

Write-Host "3. Full pytest suite" -ForegroundColor Yellow
python -m pytest --tb=short -q 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED" -ForegroundColor Red; exit 1 }

Write-Host "=== ALL PASSED ===" -ForegroundColor Green
