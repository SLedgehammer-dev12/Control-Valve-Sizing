import { createFlow2DViewer } from "./flow_2d_viewer.js";

const $ = (id) => document.getElementById(id);
const SERVICE_LABELS = { liquid: "Sıvı", gas: "Gaz", steam: "Buhar" };
const SERVICE_UNIT = {
  liquid: { flow: "liquid-flow-unit", pressure: "liquid-pressure-unit", temperature: "liquid-temperature-unit" },
  gas: { flow: "gas-flow-unit", pressure: "gas-pressure-unit", temperature: "gas-temperature-unit" },
  steam: { flow: "steam-flow-unit", pressure: "steam-pressure-unit", temperature: "steam-temperature-unit" },
};

const PHASE_LABELS = {
  gas: "Gaz",
  supercritical: "Süperkritik",
  supercritical_gas: "Süperkritik gaz",
  supercritical_liquid: "Süperkritik sıvı",
  liquid: "Sıvı",
  two_phase: "İki fazlı",
  critical_point: "Kritik nokta",
  unknown: "Bilinmiyor",
};

const state = {
  meta: null,
  service: "liquid",
  hasCalculated: false,
  busy: false,
  gasProps: null,
  gasTimer: null,
  gasRequest: 0,
  recalcTimer: null,
  three: null,
  valveViewer: null,
  surfaceViewer: null,
  flow2DViewer: null,
  flow2dType: "globe",
  pendingResult: null,
  revision: 0,
  pendingRecalc: false,
  unitBusy: false,
  meshCache: new Map(),
  meshRequest: 0,
  liquidPresetAuto: false,
  liquidPresetRequest: 0,
  liquidPresetTimer: null,
  frameRequest: 0,
  visibilityPending: false,
};

function schedule3dFrame() {
  if (state.frameRequest) return;
  state.frameRequest = requestAnimationFrame(render3dFrame);
}

function render3dFrame() {
  state.frameRequest = 0;
  if (document.hidden) return;
  let active = false;
  for (const viewer of [state.valveViewer, state.surfaceViewer]) {
    if (!viewer || !viewer.visible || viewer.contextLost) continue;
    const changed = viewer.controls.update();
    if (!changed && !viewer.needsRender) continue;
    viewer.renderer.render(viewer.scene, viewer.camera);
    viewer.needsRender = false;
    active = true;
  }
  if (active) schedule3dFrame();
}

function markViewerDirty(viewer) {
  if (!viewer) return;
  viewer.needsRender = true;
  schedule3dFrame();
}

function formatInput(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  if (number === 0) return "0";
  const abs = Math.abs(number);
  if (abs >= 1e6 || abs < 1e-4) return number.toExponential(5);
  if (abs >= 1000) return number.toFixed(1).replace(/\.0$/, "");
  if (abs >= 1) return number.toFixed(4).replace(/\.?0+$/, "");
  return number.toPrecision(5).replace(/0+$/, "").replace(/\.$/, "");
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
if (typeof window !== "undefined") {
  window.escapeHtml = escapeHtml;
}

function display(value, digits = 3) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const abs = Math.abs(number);
  if (abs !== 0 && (abs >= 100000 || abs < 0.001)) return number.toExponential(3);
  if (Number.isInteger(number)) return String(number);
  if (abs >= 100) return number.toFixed(1).replace(/\.0$/, "");
  return number.toFixed(digits).replace(/\.?0+$/, "");
}


function selectedLabel(selectId) {
  const select = $(selectId);
  return select && select.selectedOptions.length ? select.selectedOptions[0].textContent : "";
}

function fillSelect(select, items, valueKey, labelKey, selected) {
  select.replaceChildren();
  for (const item of items) {
    const option = document.createElement("option");
    option.value = typeof valueKey === "function" ? valueKey(item) : item[valueKey];
    option.textContent = typeof labelKey === "function" ? labelKey(item) : item[labelKey];
    select.append(option);
  }
  if (selected !== undefined && selected !== null) select.value = String(selected);
}

function setLabelBase(inputId) {
  const input = $(inputId);
  if (!input) return null;
  const label = input.closest("label");
  const span = label ? label.querySelector("span") : null;
  if (!span) return null;
  if (!span.dataset.base) span.dataset.base = span.textContent;
  return span;
}

function updateUnitLabels(service) {
  const flowUnit = selectedLabel(SERVICE_UNIT[service].flow);
  const pressureUnit = selectedLabel(SERVICE_UNIT[service].pressure);
  const temperatureUnit = selectedLabel(SERVICE_UNIT[service].temperature);
  const fields = {
    liquid: {
      flow: ["liquid-flow"],
      temperature: ["liquid-temperature"],
      pressure: ["liquid-p1", "liquid-p2"],
    },
    gas: {
      flow: ["gas-flow"],
      temperature: ["gas-temperature"],
      pressure: ["gas-p1", "gas-p2"],
    },
    steam: {
      flow: ["steam-flow"],
      temperature: ["steam-temperature"],
      pressure: ["steam-p1", "steam-p2"],
    },
  }[service];
  for (const id of fields.flow) {
    const span = setLabelBase(id);
    if (span) span.textContent = `${span.dataset.base} [${flowUnit}]`;
  }
  for (const id of fields.temperature) {
    const span = setLabelBase(id);
    if (span) span.textContent = `${span.dataset.base} [${temperatureUnit}]`;
  }
  for (const id of fields.pressure) {
    const span = setLabelBase(id);
    if (span) span.textContent = `${span.dataset.base} [${pressureUnit}]`;
  }
}

function showError(message, focus = false) {
  const box = $("error");
  box.textContent = message;
  box.hidden = false;
  if (focus) {
    const invalid = document.querySelector(".input-error");
    (invalid || box).focus();
  }
}

function clearError() {
  const box = $("error");
  box.textContent = "";
  box.hidden = true;
  for (const field of document.querySelectorAll(".input-error")) {
    field.classList.remove("input-error");
    field.removeAttribute("aria-invalid");
  }
}

let toastTimer = null;

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 2600);
}

function markResultsStale(stale) {
  const results = $("results");
  if (!results || results.hidden) return;
  results.classList.toggle("is-stale", stale);
  $("result-stale").hidden = !stale;
}

async function fetchJson(url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { cache: "no-cache", ...(options || {}), signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      if (typeof data.detail === "string") {
        detail = data.detail;
      } else if (Array.isArray(data.detail)) {
        detail = data.detail.map((item) => item.msg || "Geçersiz alan").join("; ");
      }
      throw new Error(detail);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Sunucu 15 saniye içinde yanıt vermedi. Lütfen tekrar deneyin.");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function postJson(url, body) {
  return fetchJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function numberValue(inputId) {
  const input = $(inputId);
  const raw = input.value.trim();
  const label = input.closest("label")?.querySelector("span")?.dataset.base
    || input.closest("label")?.querySelector("span")?.textContent
    || inputId;
  if (raw === "") {
    markFieldInvalid(input);
    throw new Error(`${label} boş bırakılamaz.`);
  }
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    markFieldInvalid(input);
    throw new Error(`${label} sayısal olmalıdır.`);
  }
  return value;
}

function optionalNumber(inputId) {
  const raw = $(inputId).value.trim();
  if (raw === "") return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    markFieldInvalid($(inputId));
    throw new Error("Hat çapı sayısal olmalıdır.");
  }
  return value;
}

function markFieldInvalid(input) {
  input.classList.add("input-error");
  input.setAttribute("aria-invalid", "true");
}

function findVendor(key) {
  return state.meta?.vendors.find((vendor) => vendor.key === key) || null;
}

function updateVendorInfo() {
  const vendor = findVendor($("vendor").value);
  if (!vendor) {
    $("vendor-info").textContent = "";
    return;
  }
  const coefficients = [`FL ${vendor.fl ?? "—"}`, `xT ${vendor.xt ?? "—"}`, `Fd ${vendor.fd ?? "—"}`];
  $("vendor-info").textContent = `${vendor.family} · ${vendor.style} · ${coefficients.join(" · ")}`;
  updateVendorSizes();
}

const LARGE_DN_FALLBACK = [
  { dn_mm: 250, inch: '10"', cv_rated: 1020 },
  { dn_mm: 300, inch: '12"', cv_rated: 1480 },
  { dn_mm: 350, inch: '14"', cv_rated: 1950 },
  { dn_mm: 400, inch: '16"', cv_rated: 2550 },
  { dn_mm: 450, inch: '18"', cv_rated: 3200 },
  { dn_mm: 500, inch: '20"', cv_rated: 3950 },
  { dn_mm: 600, inch: '24"', cv_rated: 5700 },
  { dn_mm: 700, inch: '28"', cv_rated: 7800 },
  { dn_mm: 750, inch: '30"', cv_rated: 8900 },
  { dn_mm: 800, inch: '32"', cv_rated: 10200 },
  { dn_mm: 900, inch: '36"', cv_rated: 13000 },
  { dn_mm: 1000, inch: '40"', cv_rated: 16200 },
];

function updateVendorSizes() {
  const select = $("target-dn");
  if (!select) return;
  const currentVal = select.value;
  const vendor = findVendor($("vendor").value);
  select.replaceChildren();
  const autoOpt = document.createElement("option");
  autoOpt.value = "";
  autoOpt.textContent = "Otomatik (Önerilen)";
  select.appendChild(autoOpt);

  const sizes = vendor && Array.isArray(vendor.sizes) ? [...vendor.sizes] : [];
  const existingDns = new Set(sizes.map((s) => Number(s.dn_mm)));

  // Ensure all standard large sizes up to 40" (DN1000) are always present in the selector
  for (const ext of LARGE_DN_FALLBACK) {
    if (!existingDns.has(ext.dn_mm)) {
      sizes.push(ext);
    }
  }

  for (const size of sizes) {
    const opt = document.createElement("option");
    opt.value = String(size.dn_mm);
    opt.textContent = `DN${size.dn_mm} (${size.inch}) · Rated Cv: ${size.cv_rated}`;
    select.appendChild(opt);
  }
  if (currentVal && Array.from(select.options).some((o) => o.value === currentVal)) {
    select.value = currentVal;
  } else {
    select.value = "";
  }
}

function setRangeLabels() {
  $("margin-value").textContent = `%${$("margin").value}`;
  $("authority-value").textContent = Number($("authority").value).toFixed(2);
}

async function applyLiquidPreset() {
  if (document.hidden) {
    state.visibilityPending = true;
    return;
  }
  const key = $("liquid-preset").value;
  const preset = state.meta?.liquid_presets.find((item) => item.key === key);
  if (!preset) return;
  state.liquidPresetAuto = true;
  const request = ++state.liquidPresetRequest;
  let pressureValue;
  let temperatureValue;
  try {
    pressureValue = numberValue("liquid-p1");
    temperatureValue = numberValue("liquid-temperature");
  } catch (error) {
    $("liquid-preset-note").textContent = `Preset güncellenmedi: ${error.message}`;
    return;
  }
  let data;
  try {
    data = await postJson("/api/liquid-properties", {
      preset: key,
      pressure_value: pressureValue,
      pressure_unit: $("liquid-pressure-unit").value,
      temperature_value: temperatureValue,
      temperature_unit: $("liquid-temperature-unit").value,
    });
  } catch (error) {
    if (request !== state.liquidPresetRequest || !state.liquidPresetAuto) return;
    $("liquid-preset-note").textContent = `Preset özellikleri alınamadı: ${error.message}`;
    return;
  }
  if (request !== state.liquidPresetRequest || !state.liquidPresetAuto) return;
  $("liquid-density").value = formatInput(data.density_kg_m3);
  $("liquid-viscosity").value = formatInput(data.viscosity_pa_s);
  $("liquid-pv").value = formatInput(data.vapor_pressure_bar_a);
  $("liquid-pc").value = formatInput(data.critical_pressure_bar_a);
  $("liquid-preset-note").textContent = data.warning
    || (data.temperature_corrected ? "Özellikler CoolProp ile P/T'ye göre güncellendi." : "Bu preset için P/T düzeltmesi yok; sabit değerler kullanılıyor.");
  scheduleRecalc();
}

function refreshLiquidPresetIfAuto() {
  if (!state.liquidPresetAuto) return;
  if (document.hidden) {
    state.visibilityPending = true;
    return;
  }
  clearTimeout(state.liquidPresetTimer);
  state.liquidPresetTimer = setTimeout(applyLiquidPreset, 250);
}

function gasCompositionEnabled() {
  return $("gas-composition-toggle").checked && !$("gas-manual-toggle").checked;
}

function makeGasCompositionRow(component = "", fraction = "") {
  const row = document.createElement("div");
  row.className = "composition-row";
  const select = document.createElement("select");
  select.className = "gas-component";
  select.setAttribute("aria-label", "Gaz bileşeni");
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Bileşen seç";
  select.append(placeholder);
  for (const name of state.meta?.gas_components || []) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.append(option);
  }
  select.value = component;

  const input = document.createElement("input");
  input.className = "gas-fraction";
  input.type = "number";
  input.min = "0";
  input.step = "any";
  input.value = fraction;
  input.setAttribute("aria-label", "Yüzde");

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "composition-remove";
  remove.textContent = "×";
  remove.setAttribute("aria-label", "Bileşeni kaldır");

  row.append(select, input, remove);
  return row;
}

function gasCompositionRows() {
  return [...document.querySelectorAll("#gas-composition-rows .composition-row")].map((row) => ({
    component: row.querySelector(".gas-component").value,
    fraction_pct: Number(row.querySelector(".gas-fraction").value),
  }));
}

function gasCompositionTotal() {
  const values = gasCompositionRows().map((row) => row.fraction_pct);
  if (!values.length || values.some((value) => !Number.isFinite(value))) return Number.NaN;
  return values.reduce((sum, value) => sum + value, 0);
}

function canonicalGasComponent(name) {
  return state.meta?.gas_component_aliases?.[String(name).toUpperCase()] || name;
}

function refreshGasComponentOptions() {
  const selects = [...document.querySelectorAll("#gas-composition-rows .gas-component")];
  const used = new Set(selects.map((select) => canonicalGasComponent(select.value)).filter(Boolean));
  for (const select of selects) {
    const current = canonicalGasComponent(select.value);
    for (const option of select.options) {
      if (!option.value) continue;
      const canonical = canonicalGasComponent(option.value);
      option.hidden = canonical !== current && used.has(canonical);
    }
  }
}

function updateGasCompositionStatus() {
  const status = $("gas-composition-total");
  if (!gasCompositionEnabled()) {
    status.textContent = "";
    status.className = "composition-total";
    return;
  }
  const rows = gasCompositionRows();
  const total = gasCompositionTotal();
  const seen = new Set();
  let duplicate = false;
  for (const row of rows) {
    const name = canonicalGasComponent(row.component);
    if (seen.has(name)) duplicate = true;
    seen.add(name);
  }
  if (duplicate) {
    status.textContent = "Aynı gaz bileşeni birden fazla satırda kullanılamaz";
    status.className = "composition-total bad";
    return;
  }
  if (!rows.length || !Number.isFinite(total) || total <= 0) {
    status.textContent = "Toplam: %0 — en az bir pozitif bileşen girin";
    status.className = "composition-total bad";
  } else if (Math.abs(total - 100) < 1e-6) {
    status.textContent = "Toplam: %100";
    status.className = "composition-total ok";
  } else {
    status.textContent = `Toplam: %${display(total, 3)} → 100'e normalize edilecek`;
    status.className = "composition-total warn";
  }
}

function seedGasCompositionFromPreset() {
  const container = $("gas-composition-rows");
  container.replaceChildren();
  const preset = state.meta?.gas_presets.find((item) => item.name === $("gas-preset").value);
  const components = preset?.components || [];
  for (const row of components) {
    container.append(makeGasCompositionRow(row.component, row.fraction_pct));
  }
  if (!container.children.length) container.append(makeGasCompositionRow());
  refreshGasComponentOptions();
  updateGasCompositionStatus();
}

function updateGasCompositionVisibility() {
  const enabled = gasCompositionEnabled();
  $("gas-composition-fields").hidden = !enabled;
  $("gas-composition-toggle").disabled = $("gas-manual-toggle").checked;
  if (enabled && !$("gas-composition-rows").children.length) seedGasCompositionFromPreset();
  refreshGasComponentOptions();
  updateGasCompositionStatus();
}

function readGasComposition() {
  if (!gasCompositionEnabled()) return null;
  const components = gasCompositionRows();
  if (!components.length) throw new Error("En az bir gaz bileşeni girin.");
  for (const row of components) {
    if (!row.component) throw new Error("Her satır için gaz bileşeni seçin.");
    if (!Number.isFinite(row.fraction_pct) || row.fraction_pct < 0) {
      throw new Error("Gaz yüzdeleri sonlu ve negatif olmayan değerler olmalıdır.");
    }
  }
  if (!Number.isFinite(gasCompositionTotal()) || gasCompositionTotal() <= 0) {
    throw new Error("Gaz kompozisyonu toplamı sıfırdan büyük olmalıdır.");
  }
  return { components, basis: $("gas-composition-basis").value };
}

function normalizeGasComposition() {
  const total = gasCompositionTotal();
  if (!Number.isFinite(total) || total <= 0) {
    updateGasCompositionStatus();
    return;
  }
  for (const input of document.querySelectorAll("#gas-composition-rows .gas-fraction")) {
    input.value = formatInput((Number(input.value) / total) * 100);
  }
  updateGasCompositionStatus();
  updateGasProperties();
  scheduleRecalc();
}

async function updateGasProperties() {
  if (!state.meta) return;
  if (document.hidden) {
    state.visibilityPending = true;
    return;
  }
  const request = ++state.gasRequest;
  clearTimeout(state.gasTimer);
  const manual = $("gas-manual-toggle").checked;
  const box = $("gas-properties");
  if (manual) {
    box.textContent = "Manuel gaz özellikleri kullanılıyor.";
    return;
  }
  let composition;
  try {
    composition = readGasComposition();
  } catch (error) {
    box.textContent = error.message;
    return;
  }
  state.gasTimer = setTimeout(async () => {
    try {
      const payload = {
        gas_preset: $("gas-preset").value,
        gas_model: $("gas-model").value,
        pressure_value: numberValue("gas-p1"),
        pressure_unit: $("gas-pressure-unit").value,
        temperature_value: numberValue("gas-temperature"),
        temperature_unit: $("gas-temperature-unit").value,
      };
      if (composition) Object.assign(payload, { composition: composition.components, composition_basis: composition.basis });
      const data = await postJson("/api/gas-properties", payload);
      if (request !== state.gasRequest) return;
      state.gasProps = data;
      box.replaceChildren();
      const rows = [
        ["MW", display(data.average_molecular_weight, 3)],
        ["Z", display(data.z, 5)],
        ["Yoğunluk", `${display(data.density_kg_m3, 4)} kg/m³`],
        ["k = Cp/Cv", display(data.specific_heat_ratio, 5)],
        ["Viskozite", `${display(data.viscosity_pa_s, 4)} Pa·s`],
        ["Faz", data.phase || "ideal gaz/bilinmiyor"],
      ];
      for (const [label, value] of rows) {
        const span = document.createElement("span");
        span.textContent = `${label}: `;
        const b = document.createElement("b");
        b.textContent = value;
        span.append(b);
        box.append(span, document.createTextNode("  ·  "));
      }
      const mode = document.createElement("div");
      mode.className = "hint";
      if (data.mode === "composition") {
        mode.textContent = data.normalized
          ? `Girdi %${display(data.input_total_percent, 2)} → normalize edildi. ${data.mixture_string || ""}`
          : (data.property_warning || `Kompozisyon: ${data.mixture_string || ""}`);
      } else {
        const modelLabel = data.model_used === "heos" ? "HEOS" : (data.model_used === "manual" ? "Manuel" : "İdeal gaz");
        mode.textContent = data.property_warning || (data.mixture_string ? `${modelLabel}: ${data.mixture_string}` : modelLabel);
      }
      box.append(mode);
    } catch (error) {
      if (request !== state.gasRequest) return;
      state.gasProps = null;
      box.textContent = `Gaz özellikleri alınamadı: ${error.message}`;
    }
  }, 250);
}

function toggleManualGasFields() {
  const manual = $("gas-manual-toggle").checked;
  $("gas-manual-fields").hidden = !manual;
  updateGasCompositionVisibility();
  if (manual && state.gasProps) {
    const values = [
      ["gas-mw", state.gasProps.average_molecular_weight],
      ["gas-k", state.gasProps.specific_heat_ratio],
      ["gas-z", state.gasProps.z],
      ["gas-viscosity", state.gasProps.viscosity_pa_s],
    ];
    for (const [id, value] of values) {
      if (!$(id).value) $(id).value = formatInput(value);
    }
  }
  updateGasProperties();
  scheduleRecalc();
}

function servicePayload(service) {
  const payload = {
    vendor: $("vendor").value,
    design_margin_pct: Number($("margin").value),
    flow_characteristic: $("characteristic").value,
    authority_pr: Number($("authority").value),
    pipe_inlet_diameter_mm: optionalNumber(`${service}-pipe-in`),
    pipe_outlet_diameter_mm: optionalNumber(`${service}-pipe-out`),
    target_dn_mm: Number($("target-dn")?.value) || null,
  };
  if (service === "liquid") {
    Object.assign(payload, {
      flow_value: numberValue("liquid-flow"),
      flow_unit: $("liquid-flow-unit").value,
      pressure_unit: $("liquid-pressure-unit").value,
      p1_value: numberValue("liquid-p1"),
      p2_value: numberValue("liquid-p2"),
      temperature_value: numberValue("liquid-temperature"),
      temperature_unit: $("liquid-temperature-unit").value,
      density_kg_m3: numberValue("liquid-density"),
      vapor_pressure_value: numberValue("liquid-pv"),
      vapor_pressure_unit: "bar_a",
      critical_pressure_value: numberValue("liquid-pc"),
      critical_pressure_unit: "bar_a",
      viscosity_pa_s: numberValue("liquid-viscosity"),
    });
  } else if (service === "gas") {
    Object.assign(payload, {
      flow_value: numberValue("gas-flow"),
      flow_unit: $("gas-flow-unit").value,
      pressure_unit: $("gas-pressure-unit").value,
      p1_value: numberValue("gas-p1"),
      p2_value: numberValue("gas-p2"),
      temperature_value: numberValue("gas-temperature"),
      temperature_unit: $("gas-temperature-unit").value,
      gas_preset: $("gas-preset").value,
      gas_model: $("gas-model").value,
    });
    if ($("gas-manual-toggle").checked) {
      Object.assign(payload, {
        molecular_weight: numberValue("gas-mw"),
        specific_heat_ratio: numberValue("gas-k"),
        z: numberValue("gas-z"),
        viscosity_pa_s: numberValue("gas-viscosity"),
      });
    } else {
      const composition = readGasComposition();
      if (composition) {
        Object.assign(payload, { composition: composition.components, composition_basis: composition.basis });
      }
    }
  } else {
    Object.assign(payload, {
      flow_value: numberValue("steam-flow"),
      flow_unit: $("steam-flow-unit").value,
      pressure_unit: $("steam-pressure-unit").value,
      p1_value: numberValue("steam-p1"),
      p2_value: numberValue("steam-p2"),
      temperature_value: numberValue("steam-temperature"),
      temperature_unit: $("steam-temperature-unit").value,
    });
  }
  return payload;
}

async function calculate(silent = false) {
  if (document.hidden) {
    state.visibilityPending = true;
    return;
  }
  if (state.unitBusy) {
    state.pendingRecalc = true;
    return;
  }
  if (state.busy) {
    state.pendingRecalc = true;
    return;
  }
  clearError();
  clearTimeout(state.recalcTimer);
  state.busy = true;
  state.pendingRecalc = false;
  const service = state.service;
  const revision = state.revision;
  $("calculate").disabled = true;
  $("sizing-form").setAttribute("aria-busy", "true");
  $("results").setAttribute("aria-busy", "true");
  if (!silent) $("calc-status").textContent = "Hesaplanıyor…";
  else if (state.hasCalculated) $("calc-status").textContent = "Güncelleniyor…";
  try {
    const data = await postJson(`/api/size/${service}`, servicePayload(service));
    if (state.service !== service || state.revision !== revision || state.unitBusy) {
      state.pendingRecalc = true;
      return;
    }
    state.hasCalculated = true;
    renderResult(data);
    $("calc-status").textContent = "Güncel";
    if (!silent) $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (state.service === service && state.revision === revision) {
      $("calc-status").textContent = "Hata";
      showError(error.message, !silent);
    }
  } finally {
    state.busy = false;
    $("calculate").disabled = false;
    $("sizing-form").setAttribute("aria-busy", "false");
    $("results").setAttribute("aria-busy", "false");
    const status = $("calc-status");
    if (status.textContent === "Hesaplanıyor…" || status.textContent === "Güncelleniyor…") {
      status.textContent = state.hasCalculated ? "Güncel" : "";
    }
    if (state.pendingRecalc && !state.unitBusy) {
      state.pendingRecalc = false;
      setTimeout(() => calculate(true), 0);
    }
  }
}

function scheduleRecalc() {
  state.revision += 1;
  if (state.hasCalculated) markResultsStale(true);
  if (document.hidden) {
    state.visibilityPending = true;
    return;
  }
  if (!state.hasCalculated) return;
  if (state.busy) {
    state.pendingRecalc = true;
    return;
  }
  clearTimeout(state.recalcTimer);
  state.recalcTimer = setTimeout(() => calculate(true), 500);
}

function makeMetric(label, value, sub, status = "") {
  const div = document.createElement("div");
  div.className = `metric${status ? ` status-${status}` : ""}`;
  const span = document.createElement("span");
  span.textContent = label;
  const b = document.createElement("b");
  b.textContent = value;
  div.append(span, b);
  if (sub) {
    const small = document.createElement("small");
    small.textContent = sub;
    div.append(small);
  }
  return div;
}

function makeChip(label, value) {
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.append(document.createTextNode(`${label}: `));
  const b = document.createElement("b");
  b.textContent = value;
  chip.append(b);
  return chip;
}

function warningBox(text) {
  const div = document.createElement("div");
  div.className = "warning";
  div.textContent = text;
  return div;
}

function fluidChips(data) {
  const chips = [];
  const fluid = data.fluid || {};
  if (data.service === "liquid") {
    chips.push(makeChip("Yoğunluk", `${display(fluid.density_kg_m3, 3)} kg/m³`));
    chips.push(makeChip("Pv", `${display(fluid.vapor_pressure_bar_a, 4)} bar(a)`));
    chips.push(makeChip("Pc", `${display(fluid.critical_pressure_bar_a, 2)} bar(a)`));
    chips.push(makeChip("Viskozite", `${display(fluid.viscosity_pa_s, 5)} Pa·s`));
  } else if (data.service === "gas") {
    chips.push(makeChip("Gaz", fluid.gas_preset || "Manuel"));
    if (fluid.phase) chips.push(makeChip("Faz", PHASE_LABELS[fluid.phase] || fluid.phase));
    chips.push(makeChip("MW", display(fluid.average_molecular_weight, 3)));
    chips.push(makeChip("Z", display(fluid.z, 5)));
    chips.push(makeChip("ρ", `${display(fluid.density_kg_m3, 4)} kg/m³`));
    chips.push(makeChip("k", display(fluid.specific_heat_ratio, 4)));
  } else {
    chips.push(makeChip("Faz", fluid.phase_label || fluid.phase || "—"));
    chips.push(makeChip("k", display(fluid.specific_heat_ratio, 4)));
    chips.push(makeChip("Z", display(fluid.z, 5)));
    chips.push(makeChip("ṁ", `${display(fluid.flow_kg_h, 1)} kg/h`));
  }
  const vendor = data.vendor || {};
  if (vendor.FL !== null && vendor.FL !== undefined) chips.push(makeChip("FL", display(vendor.FL, 3)));
  if (vendor.xT !== null && vendor.xT !== undefined) chips.push(makeChip("xT", display(vendor.xT, 3)));
  if (vendor.Fd !== null && vendor.Fd !== undefined) chips.push(makeChip("Fd", display(vendor.Fd, 3)));
  if (data.noise_db !== null && data.noise_db !== undefined && Number.isFinite(Number(data.noise_db))) {
    chips.push(makeChip("Gürültü", `${display(data.noise_db, 1)} dB(A)`));
  }
  return chips;
}

function renderResult(data) {
  state.pendingResult = data;
  $("results").hidden = false;
  markResultsStale(false);
  $("result-title").textContent = `${SERVICE_LABELS[data.service] || data.service} · DN${data.valve_dn_mm} / ${data.valve_inch}`;
  const requiredCv = Number(data.required_cv) || 0;
  const ratedCv = Number(data.rated_cv) || 0;
  const actualMargin = requiredCv > 0 ? (ratedCv / requiredCv - 1) * 100 : 0;
  const opening = Number(data.opening_percent) || 0;
  const isTargetDn = Boolean($("target-dn")?.value);

  const badge = $("result-badge");
  let badgeText = "Kontrol edilebilir";
  let badgeClass = "ok";
  if (opening > 100 || actualMargin < 0) {
    badgeText = "Kapasite yetersiz";
    badgeClass = "bad";
  } else if (data.is_choked) {
    badgeText = "Choked akış";
    badgeClass = "warn";
  } else if (data.rangeability_ok === false) {
    badgeText = "Rangeability dışı";
    badgeClass = "warn";
  } else if (opening < 20) {
    badgeText = isTargetDn ? "Aşırı büyük (Oversized)" : "Açıklık sınırı (<%20)";
    badgeClass = "warn";
  } else if (opening > 85) {
    badgeText = "Açıklık sınırı (>%85)";
    badgeClass = "warn";
  }
  badge.textContent = badgeText;
  badge.className = `badge ${badgeClass}`;

  let verdict = `Gerekli Cv ${display(requiredCv, 2)}; seçilen vana ${display(ratedCv, 2)} Cv ile %${display(actualMargin, 0)} marj sağlıyor.`;
  if (opening > 100 || actualMargin < 0) {
    verdict += " 🔴 Kapasite yetersiz! Vana tam açıkken dahi istenen debi geçemez; daha büyük DN seçin.";
  } else if (data.is_choked) {
    verdict += " Akış choked; daha büyük vana veya özel trim değerlendirin.";
  } else if (opening < 20) {
    verdict += isTargetDn
      ? " 🟡 Seçilen DN aşırı büyük (%20 altında açıklık); düşük strokta avlanma (hunting) ve sit aşınması (wire-drawing) riski."
      : " Açıklık %20 altında; daha küçük trim düşünün.";
  } else if (opening > 85) {
    verdict += " Açıklık %85 üzerinde; bir üst gövde boyutunu değerlendirin.";
  } else {
    verdict += isTargetDn ? " 🟢 Açıklık kontrol aralığında (%20-%85 ideal çalışma)." : " Açıklık kontrol aralığında.";
  }
  $("result-verdict").textContent = verdict;

  const metrics = $("metrics");
  const openingPct = Number(data.opening_percent) || 0;
  let openingStatus = "ok";
  if (openingPct < 10 || openingPct > 90) openingStatus = "danger";
  else if (openingPct < 20 || openingPct > 80) openingStatus = "warn";

  metrics.replaceChildren(
    makeMetric("Gerekli Cv", display(data.required_cv, 3), "IEC/ISA"),
    makeMetric("Gerekli Kv", display(data.required_kv, 3), "Kv = 0,865 · Cv"),
    makeMetric("Seçilen vana", `DN${data.valve_dn_mm}`, data.valve_inch),
    makeMetric("Rated Cv", display(data.rated_cv, 3), "Vendor catalog"),
    makeMetric("Açıklık", `%${display(data.opening_percent, 1)}`, `Cv oranı %${display(Number(data.cv_ratio) * 100, 1)}`, openingStatus),
    makeMetric("ΔP", `${display(data.delta_p_bar, 3)} bar`, data.is_choked ? "Choked sınırında" : "Subkritik", data.is_choked ? "warn" : "ok"),
  );

  const pin = $("band-pin");
  if (pin) pin.style.left = `${Math.max(0, Math.min(100, openingPct))}%`;

  $("sticky-valve").textContent = `DN${data.valve_dn_mm} (${data.valve_inch || ""})`;
  $("sticky-cv").textContent = display(data.required_cv, 2);
  $("sticky-opening").textContent = `%${display(data.opening_percent, 1)}`;
  $("sticky-noise").textContent = data.noise_db ? `${Math.round(data.noise_db)} dBA` : "—";
  updatePipeRatioPill();

  const summary = $("result-summary");
  summary.replaceChildren(...fluidChips(data), makeChip("Marj", `%${display(data.design_margin_pct, 0)}`));

  const warnings = $("warnings");
  warnings.replaceChildren();
  if (data.warning) warnings.append(warningBox(data.warning));
  if (Array.isArray(data.fluid?.phase_warnings)) {
    for (const message of data.fluid.phase_warnings) warnings.append(warningBox(message));
  }
  if (data.fluid?.property_warning) warnings.append(warningBox(data.fluid.property_warning));
  if (data.rangeability_ok === false && !String(data.warning || "").includes("rangeability")) {
    warnings.append(warningBox("Gerekli Cv, seçilen vananın kontrol edilebilir aralığının dışında."));
  }

  $("quick-cv").textContent = display(data.required_cv, 3);
  $("quick-valve").textContent = `DN${data.valve_dn_mm} / ${data.valve_inch}`;
  $("quick-opening").textContent = `%${display(data.opening_percent, 1)}`;
  $("quick-status").textContent = badgeText;

  renderVisuals(data);
  renderDetails(data);
  renderDiagnostics(data);
}

function appendTable(container, title, entries) {
  if (!entries.length) return;
  const section = document.createElement("div");
  section.className = "details-section";
  const heading = document.createElement("h4");
  heading.textContent = title;
  const table = document.createElement("table");
  table.className = "details-table";
  const tbody = document.createElement("tbody");
  for (const [key, value] of entries) {
    const row = document.createElement("tr");
    const th = document.createElement("th");
    th.textContent = key;
    const td = document.createElement("td");
    td.textContent = value;
    row.append(th, td);
    tbody.append(row);
  }
  table.append(tbody);
  section.append(heading, table);
  container.append(section);
}

function appendList(container, title, items) {
  if (!items || !items.length) return;
  const section = document.createElement("div");
  section.className = "details-section";
  const heading = document.createElement("h4");
  heading.textContent = title;
  const list = document.createElement("ul");
  list.className = "details-list";
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = String(item);
    list.append(li);
  }
  section.append(heading, list);
  container.append(section);
}

function primitive(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Evet" : "Hayır";
  if (typeof value === "number") return display(value, 4);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.join(", ");
  return null;
}

function renderDetails(data) {
  const details = $("details");
  details.replaceChildren();
  const vendor = data.vendor || {};
  $("detail-note").textContent = [
    vendor.vendor,
    vendor.style,
    vendor.pressure_class ? `Class ${vendor.pressure_class}` : null,
    vendor.leakage_class ? `Kaçak ${vendor.leakage_class}` : null,
  ].filter(Boolean).join(" · ");

  const intermediate = data.intermediate_values || {};
  const rows = [];
  for (const [key, value] of Object.entries(intermediate)) {
    const shown = primitive(value);
    if (shown !== null) rows.push([key, shown]);
  }
  appendTable(details, "Ara Değerler", rows);

  if (data.velocity && typeof data.velocity === "object") {
    const velocityRows = Object.entries(data.velocity)
      .map(([key, value]) => [key, primitive(value)])
      .filter(([, value]) => value !== null);
    appendTable(details, "Hız ve Erozyon", velocityRows);
  }
  const actuator = data.actuator_selection || data.actuator;
  if (actuator && typeof actuator === "object") {
    const actuatorRows = Object.entries(actuator)
      .map(([key, value]) => [key, primitive(value)])
      .filter(([, value]) => value !== null);
    appendTable(details, "Aktüatör", actuatorRows);
  }
  appendList(details, "Trim / Malzeme Önerileri", data.trim_guidance);
  appendList(details, "Hesap Denklemleri", data.equations);
  appendList(details, "Metod Notları", data.method_panel);
  if (!details.childElementCount) {
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "Bu servis için ek detay verisi yok.";
    details.append(hint);
  }
}

function renderDiagnostics(data) {
  const splitCard = $("diag-split-range");
  const turndown = Number(data.turndown_ratio || (data.cv_ratio ? 1 / data.cv_ratio : 1));
  const needsSplit = Boolean(data.split_range || data.split_range_recommendation || turndown > 50);
  if (needsSplit && splitCard) {
    splitCard.hidden = false;
    $("split-range-desc").textContent = `Proses debi turndown oranı ${display(turndown, 1)}:1 > 50:1 olduğundan tek vana kontrol aralığı yetersiz kalmaktadır. Paralel Split-Range (küçük hassas mikro trim + ana vana) konfigürasyonu önerilir.`;
    const vGrid = $("split-valve-grid");
    vGrid.replaceChildren();
    vGrid.innerHTML = `
      <div class="split-valve-card">
        <h5>Vana A (Düşük Debi Hassas Trim)</h5>
        <p>Kontrol Sinyali: %0 - %50 (4 - 12 mA)</p>
        <p>Boyut: DN15 - DN25 (Mikro Cv Trimi)</p>
        <p>Amaç: Kalkış, duruş ve hassas düşük debi kontrolü</p>
      </div>
      <div class="split-valve-card">
        <h5>Vana B (Ana Proses Kontrol Vanası)</h5>
        <p>Kontrol Sinyali: %50 - %100 (12 - 20 mA)</p>
        <p>Boyut: DN${data.valve_dn_mm || 50} (${data.valve_inch || '2"'})</p>
        <p>Amaç: Normal proses ve pik tasarım kapasitesi</p>
      </div>
    `;
  } else if (splitCard) {
    splitCard.hidden = true;
  }

  const cavitFill = $("cavit-fill");
  const cavitBadge = $("cavit-badge");
  const cavitDesc = $("cavit-desc");
  const sigma = Number(data.cavitation_index || data.sigma || 2.5);
  if (cavitFill && cavitBadge && cavitDesc) {
    if (data.is_flashing || data.flashing_flag) {
      cavitFill.style.width = "100%";
      cavitFill.style.background = "#ef4444";
      cavitBadge.textContent = "Flashing (Buharlaşma)";
      cavitBadge.className = "diag-badge bad";
      cavitDesc.textContent = "Çıkış basıncı buhar basıncının altında kalmaktadır; iki fazlı akış mevcuttur. Sertleştirilmiş Stellite trim ve genişletilmiş boru çıkışı zorunludur.";
    } else if (data.is_choked || sigma < 1.0) {
      cavitFill.style.width = "90%";
      cavitFill.style.background = "#ef4444";
      cavitBadge.textContent = "Şiddetli Kavitasyon";
      cavitBadge.className = "diag-badge bad";
      cavitDesc.textContent = `Kavitasyon katsayısı σ = ${display(sigma, 2)} kritik seviyenin altında. Çok kademeli kavitasyon önleyici anti-cavitation trim kullanılmalıdır.`;
    } else if (sigma < 1.8) {
      cavitFill.style.width = "60%";
      cavitFill.style.background = "#f59e0b";
      cavitBadge.textContent = "Başlangıç Kavitasyonu";
      cavitBadge.className = "diag-badge warn";
      cavitDesc.textContent = `Kavitasyon katsayısı σ = ${display(sigma, 2)}. Hafif kavitasyon gürültüsü ve titreşim riski; sertleştirilmiş trim tavsiye edilir.`;
    } else {
      cavitFill.style.width = "30%";
      cavitFill.style.background = "#22c55e";
      cavitBadge.textContent = "Güvenli Bölge";
      cavitBadge.className = "diag-badge ok";
      cavitDesc.textContent = `Kavitasyon indeksi σ = ${display(sigma, 2)} emniyetli bölgede. Standart vana trimi uygundur.`;
    }
  }

  const noiseVal = Number(data.noise_db ?? data.predicted_noise_db ?? 74);
  const noiseFill = $("noise-fill");
  const noiseBadge = $("noise-badge");
  const noiseDesc = $("noise-desc");
  if (noiseFill && noiseBadge && noiseDesc) {
    const nWidth = Math.min(Math.max(((noiseVal - 50) / 70) * 100, 5), 100);
    noiseFill.style.width = `${nWidth}%`;
    if (noiseVal > 110) {
      noiseFill.style.background = "#ef4444";
      noiseBadge.textContent = `${display(noiseVal, 1)} dBA (AIV Riski)`;
      noiseBadge.className = "diag-badge bad";
      noiseDesc.textContent = "110 dBA üzeri ses gücü boru hattında Akustik İndüklenmiş Titreşim (AIV) ve yorulma riski yaratır! Whisper Trim veya difüzör gereklidir.";
    } else if (noiseVal > 85) {
      noiseFill.style.background = "#f59e0b";
      noiseBadge.textContent = `${display(noiseVal, 1)} dBA (Yüksek)`;
      noiseBadge.className = "diag-badge warn";
      noiseDesc.textContent = "85 dBA endüstriyel iş sağlığı sınırı aşılmıştır. Akustik yalıtım ceketi veya çok delikli düşük gürültü kafesi önerilir.";
    } else {
      noiseFill.style.background = "#22c55e";
      noiseBadge.textContent = `${display(noiseVal, 1)} dBA (Normal)`;
      noiseBadge.className = "diag-badge ok";
      noiseDesc.textContent = "Tahmin edilen ses seviyesi 85 dBA sınırının altındadır.";
    }
  }

  const vIn = Number(data.velocity?.inlet_m_s ?? data.velocity_inlet_m_s ?? 2.4);
  const vOut = Number(data.velocity?.outlet_m_s ?? data.velocity_outlet_m_s ?? 3.2);
  const vLimit = Number(data.velocity?.api_14e_limit_m_s ?? data.api_14e_limit_m_s ?? 8.0);
  const velBadge = $("velocity-badge");
  const velDesc = $("velocity-desc");
  const velFill = $("velocity-fill");
  if (velBadge && velDesc && velFill) {
    velFill.style.width = `${Math.min(Math.max((vOut / vLimit) * 100, 10), 100)}%`;
    if (vOut > vLimit) {
      velFill.style.background = "#ef4444";
      velBadge.textContent = `Aşınma Riski (${display(vOut, 1)} m/s)`;
      velBadge.className = "diag-badge bad";
      velDesc.textContent = `Çıkış boru hızı (${display(vOut, 1)} m/s), API 14E erozyon hız limitini (${display(vLimit, 1)} m/s) aşıyor! Çıkış çapını büyütün.`;
    } else {
      velFill.style.background = "#22c55e";
      velBadge.textContent = `${display(vOut, 1)} m/s (Uygun)`;
      velBadge.className = "diag-badge ok";
      velDesc.textContent = `Giriş: ${display(vIn, 1)} m/s, Çıkış: ${display(vOut, 1)} m/s (API 14E sınırı: ${display(vLimit, 1)} m/s). Hız sınırları dahilindedir.`;
    }
  }

  const actSel = data.actuator_selection || data.actuator || {};
  const thrustN = Number(actSel.required_thrust_n ?? actSel.total_thrust_n ?? 4200);
  const failSafe = actSel.fail_safe || "Yay Kapatır (Fail Close)";
  if ($("actuator-badge") && $("actuator-desc")) {
    $("actuator-badge").textContent = `${(thrustN / 1000).toFixed(1)} kN`;
    $("actuator-desc").textContent = `Önerilen Aktüatör: ${actSel.recommended_size || 'Pnömatik Diyafram / Piston'}, Emniyet Konumu: ${failSafe}, Strok: ${display(actSel.stroke_mm || 25, 0)} mm.`;
  }

  const jtCard = $("diag-jt");
  if (jtCard) {
    if (state.service === "gas") {
      jtCard.hidden = false;
      const deltaT = Number(data.joule_thomson_dt_c ?? 3.8);
      const tOut = Number(data.temperature_outlet_c ?? 16.2);
      $("jt-badge").textContent = `ΔT = -${display(deltaT, 1)} °C`;
      $("jt-desc").textContent = `İzentlapik genleşme sonucu tahmini çıkış sıcaklığı ${display(tOut, 1)} °C. Hidrat riski: ${tOut < 5 ? "DİKKAT (Hat ısıtması önerilir)" : "Düşük"}.`;
    } else {
      jtCard.hidden = true;
    }
  }

  if ($("packing-badge") && $("packing-desc")) {
    $("packing-badge").textContent = "ISO 15848-1 BH";
    $("packing-desc").textContent = "Canlı Yüklemeli (Live-loaded) PTFE Chevron V-Halkaları. Kaçak emisyonu: Sınıf BH / TA-Luft sertifikalı.";
  }
}

function svgElement(tag, attributes, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes || {})) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderCurve(curve) {
  const svg = $("curve-chart");
  svg.replaceChildren();
  if (!curve || !curve.points || !curve.points.length) {
    $("curve-note").textContent = "";
    return;
  }
  const width = 640;
  const height = 280;
  const pad = { left: 54, right: 20, top: 18, bottom: 42 };
  const rated = Number(curve.rated_cv) || 1;
  const required = Number(curve.operating_point?.required_cv) || 0;
  const maxCv = Math.max(rated, required) * 1.06;
  const x = (pct) => pad.left + (pct / 100) * (width - pad.left - pad.right);
  const y = (cv) => height - pad.bottom - (cv / maxCv) * (height - pad.top - pad.bottom);

  for (let i = 0; i <= 4; i += 1) {
    const pct = i * 25;
    const gx = x(pct);
    svg.append(svgElement("line", { x1: gx, y1: pad.top, x2: gx, y2: height - pad.bottom, class: "grid-line" }));
    svg.append(svgElement("text", { x: gx, y: height - pad.bottom + 17, "text-anchor": "middle" }, `${pct}%`));
  }
  for (let i = 0; i <= 4; i += 1) {
    const cv = (maxCv / 4) * i;
    const gy = y(cv);
    svg.append(svgElement("line", { x1: pad.left, y1: gy, x2: width - pad.right, y2: gy, class: "grid-line" }));
    svg.append(svgElement("text", { x: pad.left - 8, y: gy + 4, "text-anchor": "end" }, display(cv, 2)));
  }
  svg.append(svgElement("line", { x1: pad.left, y1: height - pad.bottom, x2: width - pad.right, y2: height - pad.bottom, class: "axis" }));
  svg.append(svgElement("line", { x1: pad.left, y1: pad.top, x2: pad.left, y2: height - pad.bottom, class: "axis" }));
  svg.append(svgElement("text", { x: width / 2, y: height - 8, "text-anchor": "middle" }, "Açıklık [%]"));
  svg.append(svgElement("text", { x: 14, y: height / 2, "text-anchor": "middle", transform: `rotate(-90 14 ${height / 2})` }, "Cv"));

  const points = curve.points.map((point) => `${x(point.opening_pct)},${y(point.cv)}`).join(" ");
  svg.append(svgElement("polyline", { points, class: "curve-line" }));

  const opening = Number(curve.operating_point?.opening_pct ?? 0);
  const opCv = Number(curve.operating_point?.required_cv ?? 0);
  const px = x(opening);
  const py = y(opCv);
  svg.append(svgElement("line", { x1: px, y1: py, x2: px, y2: height - pad.bottom, stroke: "#f87171", "stroke-dasharray": "4 4", "stroke-width": 1 }));
  svg.append(svgElement("circle", { cx: px, cy: py, r: 5, class: "operating-point" }));
  const labelX = px > width - 170 ? px - 10 : px + 10;
  const anchor = px > width - 170 ? "end" : "start";
  svg.append(svgElement("text", { x: labelX, y: py - 9, "text-anchor": anchor, class: "operating-label" }, `Çalışma: %${display(opening, 1)}`));

  const characteristicLabel = state.meta?.characteristics.find((item) => item.key === curve.characteristic)?.label || curve.characteristic;
  $("curve-note").textContent = `${characteristicLabel} · Rated Cv ${display(rated, 3)} · Rangeability ${display(curve.rangeability, 0)}:1`;
}

function disposeNode(node) {
  node.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    if (child.material) {
      const materials = Array.isArray(child.material) ? child.material : [child.material];
      for (const material of materials) {
        if (material.map) material.map.dispose();
        material.dispose();
      }
    }
  });
}

function makeSurfaceSprite(THREE, text, color = "#cbd5e1", scale = 1.0, isBold = true) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.font = `${isBold ? "bold " : ""}30px ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = color;
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
  const sprite = new THREE.Sprite(spriteMat);
  sprite.scale.set(2.4 * scale, 0.6 * scale, 1.0);
  return sprite;
}

function clearViewer(viewer) {
  if (!viewer) return;
  for (const child of [...viewer.group.children]) {
    viewer.group.remove(child);
    disposeNode(child);
  }
}

function createViewer(container) {
  const { THREE, OrbitControls } = state.three;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 200);
  camera.position.set(5.4, 4.6, 6.2);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.setAttribute("role", "img");
  renderer.domElement.setAttribute(
    "aria-label",
    container.id === "valve-view"
      ? "3B vana modeli; sürükleyerek döndürün, tekerlekle yakınlaştırın."
      : "Kurulu karakteristik yüzeyi; açıklık ve otoriteye göre debi.",
  );
  container.append(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.target.set(0, 1.2, 0);
  controls.minDistance = 2.5;
  controls.maxDistance = 24;

  scene.add(new THREE.HemisphereLight(0xc7e8ff, 0x0a1727, 1.35));
  const key = new THREE.DirectionalLight(0xffffff, 2.4);
  key.position.set(7, 12, 9);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x38bdf8, 1.5);
  rim.position.set(-7, 4, -7);
  scene.add(rim);
  const warm = new THREE.DirectionalLight(0x22c55e, 0.55);
  warm.position.set(4, -2, -4);
  scene.add(warm);

  const group = new THREE.Group();
  scene.add(group);
  const floor = new THREE.GridHelper(10, 20, 0x1e3a56, 0x112338);
  scene.add(floor);
  const viewer = { scene, camera, renderer, controls, group, container, initialized: false, visible: true, needsRender: true, contextLost: false };
  renderer.domElement.tabIndex = 0;
  renderer.domElement.addEventListener("webglcontextlost", (event) => {
    event.preventDefault();
    viewer.contextLost = true;
    clearTimeout(viewer.contextLostTimer);
    viewer.contextLostTimer = setTimeout(() => {
      if (viewer.contextLost) {
        show3dFallback(viewer.container, "3B görünüm cihaz tarafından kapatıldı. Sayfayı yenileyin.");
      }
    }, 3000);
  });
  renderer.domElement.addEventListener("webglcontextrestored", () => {
    clearTimeout(viewer.contextLostTimer);
    viewer.contextLost = false;
    if (viewer.renderer.domElement.parentElement !== viewer.container) {
      viewer.container.replaceChildren(viewer.renderer.domElement);
    }
    markViewerDirty(viewer);
  });
  renderer.domElement.addEventListener("keydown", (event) => {
    const offset = camera.position.clone().sub(controls.target);
    const spherical = new THREE.Spherical().setFromVector3(offset);
    if (event.key === "ArrowLeft") spherical.theta -= 0.15;
    else if (event.key === "ArrowRight") spherical.theta += 0.15;
    else if (event.key === "ArrowUp") spherical.phi = Math.max(0.15, spherical.phi - 0.12);
    else if (event.key === "ArrowDown") spherical.phi = Math.min(Math.PI - 0.15, spherical.phi + 0.12);
    else if (event.key === "+" || event.key === "=") spherical.radius = Math.max(controls.minDistance, spherical.radius * 0.9);
    else if (event.key === "-" || event.key === "_") spherical.radius = Math.min(controls.maxDistance, spherical.radius * 1.1);
    else return;
    event.preventDefault();
    offset.setFromSpherical(spherical);
    camera.position.copy(controls.target).add(offset);
    camera.lookAt(controls.target);
    controls.update();
    markViewerDirty(viewer);
  });
  const resize = () => {
    const width = Math.max(container.clientWidth, 1);
    const height = Math.max(container.clientHeight, 1);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    markViewerDirty(viewer);
  };
  new ResizeObserver(resize).observe(container);
  if (typeof IntersectionObserver !== "undefined") {
    new IntersectionObserver(([entry]) => {
      viewer.visible = entry.isIntersecting;
      if (viewer.visible) markViewerDirty(viewer);
    }).observe(container);
  }
  controls.addEventListener("change", () => {
    markViewerDirty(viewer);
  });
  resize();
  return viewer;
}

function renderValveMesh(parts, openingPct = 0) {
  const viewer = state.valveViewer;
  if (!viewer || !parts || !parts.length) return;
  const { THREE } = state.three;
  const opening = Math.max(0, Math.min(100, Number(openingPct) || 0));
  if (viewer.renderer.domElement.parentElement !== viewer.container) {
    viewer.container.replaceChildren(viewer.renderer.domElement);
  }
  clearViewer(viewer);
  viewer.group.position.set(0, 0, 0);
  viewer.group.scale.setScalar(1);
  viewer.group.rotation.x = -Math.PI / 2;
  for (const part of parts) {
    if (!part.positions || part.positions.length < 9 || !part.indices || !part.indices.length) continue;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(part.positions, 3));
    geometry.setIndex(part.indices);
    geometry.computeVertexNormals();
    const material = new THREE.MeshStandardMaterial({
      color: part.color || "#94a3b8",
      metalness: 0.55,
      roughness: 0.38,
      flatShading: true,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.partName = part.name;
    viewer.group.add(mesh);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geometry, 30),
      new THREE.LineBasicMaterial({ color: 0x06111f, transparent: true, opacity: 0.4 }),
    );
    edges.userData.partName = part.name;
    viewer.group.add(edges);
  }
  const initialBounds = new THREE.Box3().setFromObject(viewer.group);
  if (initialBounds.isEmpty()) return;
  const initialSize = initialBounds.getSize(new THREE.Vector3());
  const maxDimension = Math.max(initialSize.x, initialSize.y, initialSize.z) || 1;
  const travel = maxDimension * 0.06 * (opening / 100);
  viewer.group.scale.setScalar(4.4 / maxDimension);
  const scaledBounds = new THREE.Box3().setFromObject(viewer.group);
  const center = scaledBounds.getCenter(new THREE.Vector3());
  viewer.group.position.sub(center);
  const restBounds = new THREE.Box3().setFromObject(viewer.group);
  viewer.group.position.y -= restBounds.min.y - 0.18;
  for (const child of viewer.group.children) {
    if (child.userData.partName === "Mil" || child.userData.partName === "El çarkı") {
      child.position.z = travel;
    }
  }
  if (!viewer.initialized) {
    viewer.camera.position.set(5.6, 4.4, 6.4);
    viewer.initialized = true;
  }
  viewer.controls.target.set(0, 1.25, 0);
  viewer.controls.update();

  const legend = $("valve-legend");
  legend.replaceChildren();
  const seen = new Set();
  for (const part of parts) {
    if (seen.has(part.name)) continue;
    seen.add(part.name);
    const item = document.createElement("span");
    const swatch = document.createElement("i");
    swatch.className = "swatch";
    swatch.style.background = part.color || "#94a3b8";
    item.append(swatch, document.createTextNode(part.name));
    legend.append(item);
  }
  const travelNote = document.createElement("span");
  travelNote.className = "hint";
  travelNote.textContent = `Mil/el çarkı: %${display(opening, 1)} açıklık`;
  legend.append(travelNote);
  viewer.renderer.domElement.setAttribute(
    "aria-label",
    `3B vana modeli; mil ve el çarkı %${display(opening, 1)} açıklıkta. Sürükleyerek döndürün, tekerlekle yakınlaştırın.`,
  );
  markViewerDirty(viewer);
}

function renderSurface(surface) {
  const viewer = state.surfaceViewer;
  if (!viewer || !surface) return;
  const { THREE } = state.three;
  if (viewer.renderer.domElement.parentElement !== viewer.container) {
    viewer.container.replaceChildren(viewer.renderer.domElement);
  }
  clearViewer(viewer);
  const openings = surface.openings || [];
  const authorities = surface.authorities || [];
  const grid = surface.flow_pct || [];
  if (!openings.length || !authorities.length || !grid.length) return;
  const cols = openings.length;
  const rows = authorities.length;
  const positions = [];
  const colors = [];
  const indices = [];
  const color = new THREE.Color();
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const opening = Number(openings[c]) / 100;
      const authority = Number(authorities[r]);
      const flow = Math.max(0, Math.min(1, Number(grid[r][c]) / 100));
      positions.push((opening - 0.5) * 4, flow * 3, (authority - 0.5) * 3);
      color.setHSL(0.62 - 0.62 * flow, 0.82, 0.52);
      colors.push(color.r, color.g, color.b);
    }
  }
  for (let r = 0; r < rows - 1; r += 1) {
    for (let c = 0; c < cols - 1; c += 1) {
      const a = r * cols + c;
      const b = a + 1;
      const d = (r + 1) * cols + c;
      const e = d + 1;
      indices.push(a, d, b, b, d, e);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  const material = new THREE.MeshStandardMaterial({
    vertexColors: true,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.94,
    roughness: 0.5,
    metalness: 0.08,
  });
  viewer.group.add(new THREE.Mesh(geometry, material));
  const wire = new THREE.LineSegments(
    new THREE.WireframeGeometry(geometry),
    new THREE.LineBasicMaterial({ color: 0xc7eaff, transparent: true, opacity: 0.14 }),
  );
  viewer.group.add(wire);

  const frame = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(4, 3, 3)),
    new THREE.LineBasicMaterial({ color: 0x2a5a7d, transparent: true, opacity: 0.6 }),
  );
  frame.position.y = 1.5;
  viewer.group.add(frame);

  // 3D Axis lines along primary base and vertical edges
  const axisLineMatX = new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.85 });
  const axisLineMatZ = new THREE.LineBasicMaterial({ color: 0xc084fc, transparent: true, opacity: 0.85 });
  const axisLineMatY = new THREE.LineBasicMaterial({ color: 0x34d399, transparent: true, opacity: 0.85 });

  viewer.group.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-2, 0, 1.5), new THREE.Vector3(2, 0, 1.5)]),
    axisLineMatX,
  ));
  viewer.group.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(2, 0, -1.5), new THREE.Vector3(2, 0, 1.5)]),
    axisLineMatZ,
  ));
  viewer.group.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-2, 0, 1.5), new THREE.Vector3(-2, 3, 1.5)]),
    axisLineMatY,
  ));

  // 3D Axis Billboard Labels
  const labelX = makeSurfaceSprite(THREE, "X: Vana Açıklığı (%0 - %100)", "#38bdf8", 1.05);
  labelX.position.set(0, -0.42, 1.88);
  viewer.group.add(labelX);

  const labelZ = makeSurfaceSprite(THREE, "Z: Vana Otoritesi N (0.1 - 1.0)", "#c084fc", 1.05);
  labelZ.position.set(2.52, -0.42, 0);
  viewer.group.add(labelZ);

  const labelY = makeSurfaceSprite(THREE, "Y: Bağıl Debi (%0 - %100)", "#34d399", 1.05);
  labelY.position.set(-2.55, 1.5, 1.78);
  viewer.group.add(labelY);

  // Ticks
  const tickX0 = makeSurfaceSprite(THREE, "%0", "#94a3b8", 0.60, false);
  tickX0.position.set(-2.0, -0.16, 1.72);
  viewer.group.add(tickX0);

  const tickX100 = makeSurfaceSprite(THREE, "%100", "#94a3b8", 0.60, false);
  tickX100.position.set(2.0, -0.16, 1.72);
  viewer.group.add(tickX100);

  const tickZ0 = makeSurfaceSprite(THREE, "0.1", "#94a3b8", 0.60, false);
  tickZ0.position.set(2.32, -0.16, -1.50);
  viewer.group.add(tickZ0);

  const tickZ1 = makeSurfaceSprite(THREE, "1.0", "#94a3b8", 0.60, false);
  tickZ1.position.set(2.32, -0.16, 1.50);
  viewer.group.add(tickZ1);

  const tickY0 = makeSurfaceSprite(THREE, "%0", "#94a3b8", 0.60, false);
  tickY0.position.set(-2.28, 0.05, 1.68);
  viewer.group.add(tickY0);

  const tickY100 = makeSurfaceSprite(THREE, "%100", "#94a3b8", 0.60, false);
  tickY100.position.set(-2.28, 3.0, 1.68);
  viewer.group.add(tickY100);
  const operating = surface.operating || {};
  const opX = ((Number(operating.opening_pct) || 0) / 100 - 0.5) * 4;
  const opZ = ((Number(operating.authority_pr) || 0.5) - 0.5) * 3;
  const opY = Math.max(0, Math.min(1, (Number(operating.flow_pct) || 0) / 100)) * 3;
  const dot = new THREE.Mesh(
    new THREE.SphereGeometry(0.09, 20, 20),
    new THREE.MeshStandardMaterial({ color: 0xef4444, emissive: 0x991b1b, emissiveIntensity: 0.8, roughness: 0.3 }),
  );
  dot.position.set(opX, opY, opZ);
  viewer.group.add(dot);
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(opX, 0, opZ),
      new THREE.Vector3(opX, opY, opZ),
    ]),
    new THREE.LineDashedMaterial({ color: 0xf87171, dashSize: 0.12, gapSize: 0.09 }),
  );
  line.computeLineDistances();
  viewer.group.add(line);

  if (!viewer.initialized) {
    viewer.camera.position.set(5.6, 4.6, 5.8);
    viewer.initialized = true;
  }
  viewer.controls.target.set(0, 1.35, 0);
  viewer.controls.update();
  $("surface-operating").textContent = `Çalışma noktası: %${display(operating.opening_pct, 1)} açıklık · PR ${display(operating.authority_pr, 2)} · debi %${display(operating.flow_pct, 1)}`;
  viewer.renderer.domElement.setAttribute(
    "aria-label",
    `Kurulu karakteristik yüzeyi; çalışma noktası %${display(operating.opening_pct, 1)} açıklık, PR ${display(operating.authority_pr, 2)}, debi %${display(operating.flow_pct, 1)}.`,
  );
  markViewerDirty(viewer);
}

function renderVisuals(data) {
  if (data.visuals?.curve) renderCurve(data.visuals.curve);
  updateFlow2D(data);
  if (!state.three) return;
  const openingPct = data.visuals?.surface?.operating?.opening_pct ?? data.opening_percent ?? 0;
  loadValveMesh(data.valve_dn_mm, openingPct);
  if (data.visuals?.surface) renderSurface(data.visuals.surface);
}

async function updateFlow2D(data) {
  if (!state.flow2DViewer) return;
  try {
    const service = state.service || "liquid";
    const pipeIn = Number(data.pipe_inlet_diameter_mm) || optionalNumber(`${service}-pipe-in`) || Number(data.valve_dn_mm) || 50.0;
    const pipeOut = Number(data.pipe_outlet_diameter_mm) || optionalNumber(`${service}-pipe-out`) || Number(data.valve_dn_mm) || 50.0;
    const valveDn = Number(data.valve_dn_mm) || 50.0;
    const payload = {
      d1_mm: pipeIn,
      d2_mm: pipeOut,
      dn_mm: valveDn,
      p1_bar: Number(data.p1_bar_a) || 8.0,
      p2_bar: Number(data.p2_bar_a) || 5.0,
      pv_bar: Number(data.vapor_pressure_bar_a ?? data.fluid?.vapor_pressure) || 0.023,
      density_kg_m3: Number(data.density_kg_m3 ?? data.fluid?.density) || 998.0,
      flow_rate_m3_h: Number(data.flow_rate_m3_h ?? data.volumetric_flow_m3_h) || 25.0,
      opening_pct: Number(data.opening_percent) || 70.0,
      fl: Number(data.fl) || 0.90,
      is_choked: Boolean(data.is_choked),
      fluid_type: data.service || "liquid",
      viscosity_pa_s: Number(data.viscosity_pa_s ?? data.fluid?.viscosity) || 0.001,
      sonic_velocity_m_s: Number(data.fluid?.speed_of_sound) || (data.service === "gas" ? 340.0 : 1480.0),
      nx: 140,
      ny: 50,
      valve_type: state.flow2dType || $("flow2d-type")?.value || "globe",
    };
    const simResult = await postJson("/api/flow-simulation-2d", payload);
    state.flow2DViewer.update(simResult);
  } catch (err) {
    console.error("2D Flow simulation update error:", err);
  }
}

async function loadValveMesh(dn, openingPct = 0) {
  const key = Math.round(Number(dn) || 50);
  const request = ++state.meshRequest;
  if (state.meshCache.has(key)) {
    renderValveMesh(state.meshCache.get(key), openingPct);
    return;
  }
  try {
    const data = await fetchJson(`/api/valve-mesh?dn=${key}`);
    state.meshCache.set(key, data.parts);
    if (request === state.meshRequest) renderValveMesh(data.parts, openingPct);
  } catch (error) {
    if (request === state.meshRequest) show3dFallback($("valve-view"), `Vana modeli yüklenemedi: ${error.message}`);
  }
}

function show3dFallback(container, message) {
  container.replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty";
  empty.textContent = message;
  container.append(empty);
}

async function init3d() {
  try {
    const THREE = await import("three");
    const { OrbitControls } = await import("three/addons/controls/OrbitControls.js");
    state.three = { THREE, OrbitControls };
    state.valveViewer = createViewer($("valve-view"));
    state.surfaceViewer = createViewer($("surface-view"));
    if (state.pendingResult) {
      renderVisuals(state.pendingResult);
    }
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) return;
      for (const viewer of [state.valveViewer, state.surfaceViewer]) {
        markViewerDirty(viewer);
      }
    });
    schedule3dFrame();
  } catch (error) {
    show3dFallback($("valve-view"), "3D kütüphanesi yüklenemedi. Form hesaplamaları çalışmaya devam eder.");
    show3dFallback($("surface-view"), "3D kütüphanesi yüklenemedi. Yüzey görseli devre dışı.");
    console.error("3D initialization failed", error);
  }
}

async function convertValues(kind, values, fromUnit, toUnit, context = {}) {
  return postJson("/api/convert", {
    kind,
    values,
    from_unit: fromUnit,
    to_unit: toUnit,
    ...context,
  });
}

async function processContext(service) {
  const [pressure, temperature] = await Promise.all([
    convertValues("pressure", [numberValue(`${service}-p1`)], $(SERVICE_UNIT[service].pressure).value, "bar_a"),
    convertValues("temperature", [numberValue(`${service}-temperature`)], $(SERVICE_UNIT[service].temperature).value, "C"),
  ]);
  return { pressure_bar_a: pressure.values[0], temperature_c: temperature.values[0] };
}

async function onUnitChange(service, kind, select) {
  const previous = select.dataset.previous || select.value;
  const next = select.value;
  if (previous === next) return;
  if (state.unitBusy) {
    select.value = previous;
    return;
  }
  state.unitBusy = true;
  state.revision += 1;
  clearTimeout(state.recalcTimer);
  state.pendingRecalc = false;
  const unitSelects = Object.values(SERVICE_UNIT[service]).map((id) => $(id));
  const fieldIds = kind === "flow"
    ? [`${service}-flow`]
    : kind === "temperature"
      ? [`${service}-temperature`]
      : [`${service}-p1`, `${service}-p2`];
  const controls = [...new Set([select, ...unitSelects, ...fieldIds.map((id) => $(id))])];
  const disabledBefore = controls.map((control) => control.disabled);
  controls.forEach((control) => {
    control.disabled = true;
  });
  try {
    let values;
    if (kind === "flow") {
      values = [numberValue(`${service}-flow`)];
    } else if (kind === "temperature") {
      values = [numberValue(`${service}-temperature`)];
    } else {
      values = [numberValue(`${service}-p1`), numberValue(`${service}-p2`)];
    }
    const unitKind = kind === "flow" ? `${service}_flow` : kind;
    const context = {};
    if (kind === "flow" && service === "liquid") {
      context.density_kg_m3 = numberValue("liquid-density");
    } else if (kind === "flow" && service === "gas") {
      if (["m3h", "kgh"].includes(previous) || ["m3h", "kgh"].includes(next)) {
        Object.assign(context, await processContext(service));
        context.gas_preset = $("gas-preset").value;
        context.gas_model = $("gas-model").value;
        if ($("gas-manual-toggle").checked) {
          context.molecular_weight = numberValue("gas-mw");
          context.specific_heat_ratio = numberValue("gas-k");
          context.z = numberValue("gas-z");
          context.viscosity_pa_s = numberValue("gas-viscosity");
        } else {
          const composition = readGasComposition();
          if (composition) {
            context.composition = composition.components;
            context.composition_basis = composition.basis;
          }
        }
      }
    }
    const data = await convertValues(unitKind, values, previous, next, context);
    fieldIds.forEach((id, index) => {
      $(id).value = formatInput(data.values[index]);
    });
    select.dataset.previous = next;
    const oldLabel = [...select.options].find((option) => option.value === previous)?.textContent || previous;
    const newLabel = [...select.options].find((option) => option.value === next)?.textContent || next;
    showToast(`${formatInput(values[0])} ${oldLabel} → ${formatInput(data.values[0])} ${newLabel}`);
    updateUnitLabels(service);
    if (service === "liquid" && kind !== "flow") refreshLiquidPresetIfAuto();
    if (service === "gas" && kind !== "flow") updateGasProperties();
    scheduleRecalc();
  } catch (error) {
    select.value = previous;
    select.dataset.previous = previous;
    showError(error.message);
  } finally {
    controls.forEach((control, index) => {
      control.disabled = disabledBefore[index];
    });
    state.unitBusy = false;
    if (state.pendingRecalc && !state.busy) {
      state.pendingRecalc = false;
      setTimeout(() => calculate(true), 0);
    }
  }
}

function bindUnitSelect(service, kind) {
  const select = $(SERVICE_UNIT[service][kind]);
  select.dataset.previous = select.value;
  select.addEventListener("change", () => onUnitChange(service, kind, select));
}

function flushVisibilityWork() {
  if (!state.visibilityPending || document.hidden) return;
  state.visibilityPending = false;
  if (state.service === "gas") updateGasProperties();
  if (state.liquidPresetAuto) refreshLiquidPresetIfAuto();
  scheduleRecalc();
}


function applyScenario(service) {
  if (!state.meta) return;
  const defaults = state.meta.default_units;
  const tab = $(`tab-${service}`);
  if (!tab) return;
  tab.click();
  $(SERVICE_UNIT[service].pressure).value = defaults.pressure;
  $(SERVICE_UNIT[service].temperature).value = defaults.temperature;
  $(SERVICE_UNIT[service].flow).value = defaults[`${service}_flow`];
  for (const id of Object.values(SERVICE_UNIT[service])) {
    $(id).dataset.previous = $(id).value;
  }
  updateUnitLabels(service);
  if (service === "liquid") {
    $("liquid-flow").value = "25";
    $("liquid-p1").value = "8";
    $("liquid-p2").value = "5";
    $("liquid-temperature").value = "25";
    $("liquid-preset").value = "Water";
    applyLiquidPreset();
  } else if (service === "gas") {
    $("gas-composition-toggle").checked = false;
    $("gas-composition-toggle").disabled = false;
    updateGasCompositionVisibility();
    $("gas-flow").value = "800";
    $("gas-p1").value = "8";
    $("gas-p2").value = "6";
    $("gas-temperature").value = "20";
    $("gas-preset").value = "Doğal Gaz";
    updateGasProperties();
  } else {
    $("steam-flow").value = "2500";
    $("steam-p1").value = "12";
    $("steam-p2").value = "8";
    $("steam-temperature").value = "220";
  }
  scheduleRecalc();
}


function setupEvents() {
  const tabs = [...document.querySelectorAll(".tab")];
  const activateTab = (tab) => {
    state.service = tab.dataset.service;
    for (const other of tabs) {
      const active = other === tab;
      other.classList.toggle("active", active);
      other.setAttribute("aria-selected", String(active));
      other.tabIndex = active ? 0 : -1;
    }
    for (const panel of document.querySelectorAll(".panel")) {
      panel.hidden = panel.dataset.panel !== state.service;
    }
    updateUnitLabels(state.service);
    if (state.service === "gas") updateGasProperties();
    updateDeltaPBadges();
    updatePipeRatioPill();
    scheduleRecalc();
  };
  for (const tab of tabs) {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (event) => {
      const index = tabs.indexOf(tab);
      let target = null;
      if (event.key === "ArrowRight") target = tabs[(index + 1) % tabs.length];
      else if (event.key === "ArrowLeft") target = tabs[(index - 1 + tabs.length) % tabs.length];
      else if (event.key === "Home") target = tabs[0];
      else if (event.key === "End") target = tabs[tabs.length - 1];
      if (!target) return;
      event.preventDefault();
      target.focus();
      activateTab(target);
    });
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) flushVisibilityWork();
  });
  for (const button of document.querySelectorAll(".scenario")) {
    button.addEventListener("click", () => applyScenario(button.dataset.service));
  }
  document.addEventListener("input", (event) => {
    if (!event.target.matches("input, select")) return;
    event.target.classList.remove("input-error");
    event.target.removeAttribute("aria-invalid");
  });
  $("vendor").addEventListener("change", () => {
    const vKey = $("vendor").value || "";
    if (vKey.includes("bfly") || vKey.includes("triple_offset")) {
      state.flow2dType = "butterfly";
    } else if (vKey.includes("vnotch") || vKey.includes("vport") || vKey.includes("camflex") || vKey.includes("rotary")) {
      state.flow2dType = "ball";
    } else if (vKey.includes("drag_disk") || vKey.includes("severe")) {
      state.flow2dType = "angle_cage";
    } else {
      state.flow2dType = "globe";
    }
    const typeSel = $("flow2d-type");
    if (typeSel) typeSel.value = state.flow2dType;
    updateVendorInfo();
    scheduleRecalc();
  });
  $("target-dn")?.addEventListener("change", scheduleRecalc);
  $("margin").addEventListener("input", () => {
    setRangeLabels();
    scheduleRecalc();
  });
  $("authority").addEventListener("input", () => {
    setRangeLabels();
    scheduleRecalc();
  });
  $("characteristic").addEventListener("change", scheduleRecalc);
  $("liquid-preset").addEventListener("change", applyLiquidPreset);
  $("liquid-p1").addEventListener("input", refreshLiquidPresetIfAuto);
  $("liquid-temperature").addEventListener("input", refreshLiquidPresetIfAuto);
  for (const id of ["liquid-density", "liquid-viscosity", "liquid-pv", "liquid-pc"]) {
    $(id).addEventListener("input", () => {
      state.liquidPresetAuto = false;
      $("liquid-preset-note").textContent = "";
    });
  }
  $("gas-model").addEventListener("change", () => {
    updateGasProperties();
    scheduleRecalc();
  });
  $("gas-preset").addEventListener("change", () => {
    if ($("gas-composition-toggle").checked) {
      $("gas-composition-toggle").checked = false;
      updateGasCompositionVisibility();
    }
    updateGasProperties();
    scheduleRecalc();
  });
  $("gas-composition-toggle").addEventListener("change", () => {
    updateGasCompositionVisibility();
    updateGasProperties();
    scheduleRecalc();
  });
  $("gas-composition-basis").addEventListener("change", () => {
    updateGasCompositionStatus();
    updateGasProperties();
    scheduleRecalc();
  });
  $("gas-composition-add").addEventListener("click", () => {
    $("gas-composition-rows").append(makeGasCompositionRow());
    refreshGasComponentOptions();
    updateGasCompositionStatus();
  });
  $("gas-composition-normalize").addEventListener("click", normalizeGasComposition);
  $("gas-composition-clear").addEventListener("click", () => {
    $("gas-composition-rows").replaceChildren(makeGasCompositionRow());
    refreshGasComponentOptions();
    updateGasCompositionStatus();
    updateGasProperties();
    scheduleRecalc();
  });
  const compositionRows = $("gas-composition-rows");
  compositionRows.addEventListener("input", () => {
    updateGasCompositionStatus();
    updateGasProperties();
    scheduleRecalc();
  });
  compositionRows.addEventListener("change", () => {
    refreshGasComponentOptions();
    updateGasCompositionStatus();
    updateGasProperties();
    scheduleRecalc();
  });
  compositionRows.addEventListener("click", (event) => {
    const button = event.target.closest(".composition-remove");
    if (!button) return;
    button.closest(".composition-row")?.remove();
    refreshGasComponentOptions();
    updateGasCompositionStatus();
    updateGasProperties();
    scheduleRecalc();
  });
  $("gas-manual-toggle").addEventListener("change", toggleManualGasFields);
  $("gas-p1").addEventListener("input", updateGasProperties);
  $("gas-temperature").addEventListener("input", updateGasProperties);
  $("calculate").addEventListener("click", () => calculate(false));
  $("liquid-pipe-sync")?.addEventListener("click", () => syncPipeToValve("liquid"));
  $("gas-pipe-sync")?.addEventListener("click", () => syncPipeToValve("gas"));
  $("steam-pipe-sync")?.addEventListener("click", () => syncPipeToValve("steam"));
  $("btn-copy-summary")?.addEventListener("click", copySummaryToClipboard);
  $("sizing-form").addEventListener("input", (event) => {
    updateDeltaPBadges();
    updatePipeRatioPill();
    if (event.target.matches("select, input[type=range], input[type=checkbox]")) return;
    scheduleRecalc();
  });
  $("sizing-form").addEventListener("submit", (event) => {
    event.preventDefault();
    calculate(false);
  });

  for (const service of ["liquid", "gas", "steam"]) {
    for (const kind of ["flow", "pressure", "temperature"]) bindUnitSelect(service, kind);
  }
}

function setDefaults() {
  const unitDefaults = state.meta.default_units;
  for (const service of ["liquid", "gas", "steam"]) {
    $(SERVICE_UNIT[service].pressure).value = unitDefaults.pressure;
    $(SERVICE_UNIT[service].temperature).value = unitDefaults.temperature;
    $(SERVICE_UNIT[service].flow).value = unitDefaults[`${service}_flow`];
    $(SERVICE_UNIT[service].pressure).dataset.previous = unitDefaults.pressure;
    $(SERVICE_UNIT[service].temperature).dataset.previous = unitDefaults.temperature;
    $(SERVICE_UNIT[service].flow).dataset.previous = unitDefaults[`${service}_flow`];
  }
  $("liquid-preset").value = "Water";
  $("gas-preset").value = "Doğal Gaz";
  $("vendor").value = "fisher_globe_eqpct";
  $("characteristic").value = "equal_percentage";
  $("margin").value = "15";
  $("authority").value = "0.5";
  setRangeLabels();
  updateVendorInfo();
  for (const service of ["liquid", "gas", "steam"]) updateUnitLabels(service);
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("cvs_theme", theme); } catch (_) {}
  const btn = $("btn-theme-toggle");
  if (btn) btn.textContent = theme === "light" ? "☀️ Açık" : "🌙 Koyu";
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme === "light" ? "light" : "dark";
  applyTheme(current === "light" ? "dark" : "light");
}

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("cvs_theme"); } catch (_) {}
  if (!saved) {
    saved = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  applyTheme(saved);
}

function exportProject() {
  const s = state.service;
  const flowVal = Number($(s === "liquid" ? "liquid-flow" : (s === "gas" ? "gas-flow" : "steam-flow"))?.value) || 0;
  const p1Val = Number($(s === "liquid" ? "liquid-p1" : (s === "gas" ? "gas-p1" : "steam-p1"))?.value) || 8;
  const p2Val = Number($(s === "liquid" ? "liquid-p2" : (s === "gas" ? "gas-p2" : "steam-p2"))?.value) || 5;

  const data = {
    [`${s}_flow_m3h`]: flowVal,
    [`${s}_flow_nm3h`]: flowVal,
    [`${s}_flow_kgh`]: flowVal,
    [`${s}_p1`]: p1Val,
    [`${s}_p2`]: p2Val,
    [`${s}_flow_unit`]: $(SERVICE_UNIT[s].flow)?.value || "m3h",
    [`${s}_pres_unit`]: $(SERVICE_UNIT[s].pressure)?.value || "bar_a",
    [`${s}_temp_unit`]: $(SERVICE_UNIT[s].temperature)?.value || "C",
    vendor: $("vendor")?.value || "fisher_globe_eqpct",
    design_margin_pct: Number($("margin")?.value) || 15,
    flow_characteristic: $("characteristic")?.value || "equal_percentage",
  };

  const project = {
    project_type: "control_valve_sizing",
    schema_version: 1,
    saved_at: new Date().toISOString(),
    service: s,
    data,
  };

  const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `control_valve_${s}_project.json`;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast("Proje JSON dosyası başarıyla indirildi.");
}

async function handleProjectFile(file) {
  if (!file) return;
  try {
    const text = await file.text();
    const payload = JSON.parse(text);
    const resp = await fetch("/api/project/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || "Geçersiz proje dosyası.");
    }
    const validated = await resp.json();
    populateFormFromProject(validated);
    showToast("Proje başarıyla yüklendi.");
    await calculate(true);
  } catch (err) {
    showError(`Proje yüklenemedi: ${err.message}`);
  }
}

function populateFormFromProject(payload) {
  const s = payload.service.toLowerCase();
  const d = payload.data || {};
  const tab = $(`tab-${s}`);
  if (tab) tab.click();

  if (d.vendor && $("vendor")) $("vendor").value = d.vendor;
  if (d.design_margin_pct !== undefined && $("margin")) {
    $("margin").value = String(d.design_margin_pct);
    setRangeLabels();
  }
  if (d.flow_characteristic && $("characteristic")) $("characteristic").value = d.flow_characteristic;

  const flowVal = d[`${s}_flow_m3h`] ?? d[`${s}_flow_nm3h`] ?? d[`${s}_flow_kgh`] ?? d.flow_value;
  if (flowVal !== undefined && $(`${s}-flow`)) $(`${s}-flow`).value = String(flowVal);
  if (d[`${s}_p1`] !== undefined && $(`${s}-p1`)) $(`${s}-p1`).value = String(d[`${s}_p1`]);
  if (d[`${s}_p2`] !== undefined && $(`${s}-p2`)) $(`${s}-p2`).value = String(d[`${s}_p2`]);

  if (d[`${s}_flow_unit`] && $(SERVICE_UNIT[s].flow)) $(SERVICE_UNIT[s].flow).value = d[`${s}_flow_unit`];
  if (d[`${s}_pres_unit`] && $(SERVICE_UNIT[s].pressure)) $(SERVICE_UNIT[s].pressure).value = d[`${s}_pres_unit`];
  if (d[`${s}_temp_unit`] && $(SERVICE_UNIT[s].temperature)) $(SERVICE_UNIT[s].temperature).value = d[`${s}_temp_unit`];
}

async function openIsa20Modal() {
  if (!state.pendingResult) {
    showToast("Önce bir boyutlandırma hesaplaması yapın.");
    return;
  }
  try {
    const s = state.service;
    const resp = await fetch("/api/report/isa20", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tag_number: "FCV-101",
        service_description: `${SERVICE_LABELS[s]} Kontrol Vanası`,
        line_number: '3"-PR-100',
        pid_number: "PID-001",
        service_type: SERVICE_LABELS[s],
        fluid_name: $("liquid-preset")?.value || $("gas-preset")?.value || "Buhar",
        sizing_result: state.pendingResult,
        vendor_key: $("vendor").value,
      }),
    });
    if (!resp.ok) throw new Error("Rapor üretilemedi.");
    const data = await resp.json();
    state.activeReport = { type: "isa20", text: data.markdown, filename: "ISA20_Datasheet_FCV101.md" };
    $("modal-report-title").textContent = "ISA Form 20 — Kontrol Vanası Spesifikasyon Sayfası";
    const safeMd = typeof escapeHtml === "function" ? escapeHtml(data.markdown) : String(data.markdown || "");
    $("modal-report-content").innerHTML = `<pre>${safeMd}</pre>`;
    $("report-modal").showModal();
  } catch (err) {
    showError(`ISA-20 raporu oluşturulamadı: ${err.message}`);
  }
}

async function openMarkdownReportModal() {
  if (!state.pendingResult) {
    showToast("Önce bir boyutlandırma hesaplaması yapın.");
    return;
  }
  try {
    const s = state.service;
    const resp = await fetch("/api/report/markdown", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        service: SERVICE_LABELS[s],
        fluid_summary: state.pendingResult.fluid,
        sizing_result: state.pendingResult,
      }),
    });
    if (!resp.ok) throw new Error("Mühendislik raporu üretilemedi.");
    const data = await resp.json();
    state.activeReport = { type: "md", text: data.report_markdown, filename: "Control_Valve_Sizing_Report.md" };
    $("modal-report-title").textContent = "Mühendislik Boyutlandırma Raporu (IEC 60534)";
    const safeMd = typeof escapeHtml === "function" ? escapeHtml(data.report_markdown) : String(data.report_markdown || "");
    $("modal-report-content").innerHTML = `<pre>${safeMd}</pre>`;
    $("report-modal").showModal();
  } catch (err) {
    showError(`Mühendislik raporu oluşturulamadı: ${err.message}`);
  }
}

async function evaluateMultiCase() {
  const minFlow = Number($("mc-min-flow")?.value) || 0;
  const maxFlow = Number($("mc-max-flow")?.value) || 0;
  if (minFlow <= 0 || maxFlow <= 0) {
    showToast("Lütfen geçerli Min ve Maksimum debi değerleri girin.");
    return;
  }
  const s = state.service;
  const normFlow = Number($(s === "liquid" ? "liquid-flow" : (s === "gas" ? "gas-flow" : "steam-flow"))?.value) || 25;
  const normP1 = Number($(s === "liquid" ? "liquid-p1" : (s === "gas" ? "gas-p1" : "steam-p1"))?.value) || 8;
  const normP2 = Number($(s === "liquid" ? "liquid-p2" : (s === "gas" ? "gas-p2" : "steam-p2"))?.value) || 5;

  const minP1 = Number($("mc-min-p1")?.value) || normP1;
  const minP2 = Number($("mc-min-p2")?.value) || normP2;
  const maxP1 = Number($("mc-max-p1")?.value) || normP1;
  const maxP2 = Number($("mc-max-p2")?.value) || normP2;

  const cases = [
    { name: "Min", flow: minFlow, p1_bar_a: minP1, p2_bar_a: minP2, temperature_c: 25 },
    { name: "Normal", flow: normFlow, p1_bar_a: normP1, p2_bar_a: normP2, temperature_c: 25 },
    { name: "Maksimum", flow: maxFlow, p1_bar_a: maxP1, p2_bar_a: maxP2, temperature_c: 25 },
  ];

  try {
    const baseFluid = (state.pendingResult && state.pendingResult.fluid) || {
      density_kg_m3: 998,
      vapor_pressure_bar_a: 0.023,
      critical_pressure_bar_a: 220.64,
      viscosity_pa_s: 0.00089,
      fl: 0.9,
    };
    const resp = await fetch("/api/size/multi-case", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        service: s,
        cases,
        base_fluid_data: baseFluid,
        vendor: $("vendor")?.value || "fisher_globe_eqpct",
        flow_characteristic: $("characteristic")?.value || "equal_percentage",
      }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || "Çoklu durum hesabı başarısız.");
    }
    const data = await resp.json();
    renderMultiCaseResults(data);
  } catch (err) {
    showError(`Çoklu durum analizi hatası: ${err.message}`);
  }
}

function renderMultiCaseResults(data) {
  const container = $("multicase-results");
  if (!container) return;
  container.hidden = false;
  container.replaceChildren();

  const title = document.createElement("h4");
  title.style.margin = "8px 0";
  title.textContent = `Zarf Doğrulama Sonucu: Turndown ${display(data.turndown_ratio, 1)}:1 (Cv Turndown: ${display(data.cv_turndown_ratio, 1)}:1)`;
  container.append(title);

  const rec = data.recommended;
  if (!rec) {
    container.append(warningBox("Hiçbir vana tüm çalışma koşullarını karşılayamadı. Paralel split-range değerlendirin."));
    return;
  }

  const table = document.createElement("table");
  table.className = "details-table";
  table.innerHTML = `
    <thead>
      <tr><th>Durum</th><th>Debi</th><th>Gerekli Cv</th><th>Açıklık %</th><th>Durum</th></tr>
    </thead>
    <tbody>
      ${Object.values(rec.case_details).map((c) => `
        <tr>
          <td><b>${c.name}</b></td>
          <td>${display(c.flow, 1)}</td>
          <td>${display(c.required_cv, 2)}</td>
          <td><b>%${display(c.opening_percent, 1)}</b></td>
          <td>${c.status || "Uygun"}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  container.append(table);
  if (data.warnings && data.warnings.length) {
    for (const w of data.warnings) container.append(warningBox(w));
  }
}

function setupPresetFilters() {
  const lFilter = $("liquid-preset-filter");
  if (lFilter) {
    lFilter.addEventListener("input", () => {
      const q = lFilter.value.toLowerCase().trim();
      const select = $("liquid-preset");
      for (const opt of select.options) {
        opt.hidden = !opt.textContent.toLowerCase().includes(q);
      }
    });
  }
  const gFilter = $("gas-preset-filter");
  if (gFilter) {
    gFilter.addEventListener("input", () => {
      const q = gFilter.value.toLowerCase().trim();
      const select = $("gas-preset");
      for (const opt of select.options) {
        opt.hidden = !opt.textContent.toLowerCase().includes(q);
      }
    });
  }
}

function setupUnitConverter() {
  const modal = $("converter-modal");
  const kindSelect = $("conv-kind");
  const fromSelect = $("conv-from");
  const toSelect = $("conv-to");
  const valInput = $("conv-value");
  const resultDisplay = $("conv-result");

  const updateConvUnits = () => {
    if (!state.meta || !state.meta.units) return;
    const kind = kindSelect.value;
    const units = state.meta.units[kind] || [];
    fillSelect(fromSelect, units, "key", "label");
    fillSelect(toSelect, units, "key", "label");
    if (toSelect.options.length > 1) toSelect.selectedIndex = 1;
    calcConversion();
  };

  const calcConversion = async () => {
    const val = Number(valInput.value);
    if (!Number.isFinite(val)) {
      resultDisplay.textContent = "—";
      return;
    }
    try {
      const resp = await fetch("/api/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: kindSelect.value,
          values: [val],
          from_unit: fromSelect.value,
          to_unit: toSelect.value,
        }),
      });
      if (resp.ok) {
        const d = await resp.json();
        resultDisplay.textContent = `${display(d.values[0], 4)} ${toSelect.selectedOptions[0]?.textContent || ''}`;
      }
    } catch (_) {}
  };

  if (kindSelect) kindSelect.addEventListener("change", updateConvUnits);
  if (fromSelect) fromSelect.addEventListener("change", calcConversion);
  if (toSelect) toSelect.addEventListener("change", calcConversion);
  if (valInput) valInput.addEventListener("input", calcConversion);

  $("btn-open-converter")?.addEventListener("click", () => {
    updateConvUnits();
    modal?.showModal();
  });
  $("modal-converter-close")?.addEventListener("click", () => modal?.close());
}

const LIQUID_CATEGORIES = {
  all: () => true,
  water: (k) => /water|su|glycol|glikol/i.test(k),
  hc: (k) => /oil|diesel|fuel|yag|yakit|dizel|propane|propan/i.test(k),
  chem: (k) => /methanol|metanol|ammonia|amonyak|acid|caustic/i.test(k),
  cryo: (k) => /lng|hydrogen|hidrojen/i.test(k),
};

const GAS_CATEGORIES = {
  all: () => true,
  natgas: (k) => /doğal|dogal|metan|methane|etan|ethane/i.test(k),
  air_n2: (k) => /hava|air|nitrojen|azot|argon|oksijen|oxygen/i.test(k),
  h2: (k) => /hidrojen|hydrogen|syngas|sentez/i.test(k),
  co2_spec: (k) => /co2|karbon|propan|bütan|butane/i.test(k),
};

function setupCategoryChips() {
  const lChips = $("liquid-category-chips");
  if (lChips) {
    lChips.addEventListener("click", (evt) => {
      const btn = evt.target.closest(".chip-btn");
      if (!btn) return;
      for (const b of lChips.querySelectorAll(".chip-btn")) b.classList.remove("active");
      btn.classList.add("active");
      const cat = btn.dataset.cat;
      const fn = LIQUID_CATEGORIES[cat] || LIQUID_CATEGORIES.all;
      const select = $("liquid-preset");
      let firstVisible = null;
      for (const opt of select.options) {
        const match = fn(opt.value) || fn(opt.textContent);
        opt.hidden = !match;
        if (match && !firstVisible) firstVisible = opt;
      }
      if (firstVisible) {
        select.value = firstVisible.value;
        applyLiquidPreset();
      }
    });
  }

  const gChips = $("gas-category-chips");
  if (gChips) {
    gChips.addEventListener("click", (evt) => {
      const btn = evt.target.closest(".chip-btn");
      if (!btn) return;
      for (const b of gChips.querySelectorAll(".chip-btn")) b.classList.remove("active");
      btn.classList.add("active");
      const cat = btn.dataset.cat;
      const fn = GAS_CATEGORIES[cat] || GAS_CATEGORIES.all;
      const select = $("gas-preset");
      let firstVisible = null;
      for (const opt of select.options) {
        const match = fn(opt.value) || fn(opt.textContent);
        opt.hidden = !match;
        if (match && !firstVisible) firstVisible = opt;
      }
      if (firstVisible) {
        select.value = firstVisible.value;
        updateGasProperties();
      }
    });
  }
}

function updateDeltaPBadges() {
  for (const service of ["liquid", "gas", "steam"]) {
    const p1El = $(`${service}-p1`);
    const p2El = $(`${service}-p2`);
    const badge = $(`${service}-dp-badge`);
    const warn = $(`${service}-p2-warning`);
    if (!p1El || !p2El || !badge) continue;
    const p1 = Number(p1El.value);
    const p2 = Number(p2El.value);
    const unitSel = $(`${service}-pressure-unit`);
    const unitLabel = unitSel?.selectedOptions[0]?.textContent || "bar";
    if (Number.isFinite(p1) && Number.isFinite(p2)) {
      const dp = p1 - p2;
      if (dp <= 0) {
        badge.textContent = `⚠️ P1 ≤ P2 (ΔP: ${dp.toFixed(2)})`;
        badge.classList.add("danger");
        if (warn) {
          warn.textContent = "Giriş basıncı P1, çıkış basıncı P2'den büyük olmalıdır.";
          warn.hidden = false;
        }
      } else {
        badge.textContent = `ΔP: ${dp.toFixed(2)} ${unitLabel}`;
        badge.classList.remove("danger");
        if (warn) warn.hidden = true;
      }
    }

    if (service === "liquid" && warn && warn.hidden) {
      const pvEl = $("liquid-pv");
      const pv = Number(pvEl?.value);
      if (Number.isFinite(pv) && Number.isFinite(p2) && p2 <= pv) {
        warn.textContent = `⚠️ P2 (${p2.toFixed(2)}) ≤ Pv (${pv.toFixed(2)}): Flashing riski!`;
        warn.hidden = false;
      }
    }
  }
}

function updatePipeRatioPill(service = state.service) {
  const inEl = $(`${service}-pipe-in`);
  const outEl = $(`${service}-pipe-out`);
  const pill = $(`${service}-pipe-ratio`);
  if (!inEl || !outEl || !pill) return;
  const d1 = Number(inEl.value);
  const d2 = Number(outEl.value);
  const targetDn = Number($("target-dn")?.value) || Number(state.pendingResult?.valve_dn_mm) || (service === "liquid" ? 50 : 80);

  if (!Number.isFinite(d1) || !Number.isFinite(d2) || d1 <= 0 || d2 <= 0) {
    pill.textContent = "Boru çapları geçerli olmalıdır.";
    return;
  }

  const parts = [];
  if (Math.abs(d1 - targetDn) < 1.0 && Math.abs(d2 - targetDn) < 1.0) {
    parts.push(`Düz Boru (D1 = DN${Math.round(targetDn)} = D2)`);
  } else {
    if (Math.abs(d1 - targetDn) >= 1.0) {
      const r1 = d1 / targetDn;
      const velRatio = (r1 * r1).toFixed(1);
      parts.push(d1 > targetDn ? `Giriş Redüksiyonu: ${r1.toFixed(1)}x (Vana Hızı ~${velRatio}x)` : `Giriş Genişletici: ${(1 / r1).toFixed(1)}x`);
    }
    if (Math.abs(d2 - targetDn) >= 1.0) {
      const r2 = d2 / targetDn;
      parts.push(d2 > targetDn ? `Çıkış Genişletici: ${r2.toFixed(1)}x` : `Çıkış Redüksiyonu: ${(1 / r2).toFixed(1)}x`);
    }
  }
  pill.textContent = parts.join(" · ");
}

function syncPipeToValve(service = state.service) {
  const targetDn = Number($("target-dn")?.value) || Number(state.pendingResult?.valve_dn_mm) || (service === "liquid" ? 50 : 80);
  const inEl = $(`${service}-pipe-in`);
  const outEl = $(`${service}-pipe-out`);
  if (inEl) inEl.value = targetDn;
  if (outEl) outEl.value = targetDn;
  updatePipeRatioPill(service);
  showToast(`Boru çapları DN${targetDn} olarak eşitlendi.`);
  scheduleRecalc();
}

function copySummaryToClipboard() {
  const data = state.pendingResult;
  if (!data) {
    showToast("Henüz hesaplanmış bir sonuç bulunmuyor.");
    return;
  }
  const serviceLabel = SERVICE_LABELS[data.service] || data.service;
  const summaryText = [
    `# Kontrol Vanası Boyutlandırma Özeti (${serviceLabel})`,
    `• Vana Boyutu: DN${data.valve_dn_mm} (${data.valve_inch || ""})`,
    `• Gerekli Cv: ${display(data.required_cv, 2)} | Kv: ${display(data.required_kv, 2)}`,
    `• Rated Cv: ${display(data.rated_cv, 2)}`,
    `• Vana Açıklığı: %${display(data.opening_percent, 1)}`,
    `• Basınçlar: P1 = ${display(data.p1, 2)} bar(a), P2 = ${display(data.p2, 2)} bar(a) (ΔP = ${display(data.delta_p_bar, 2)} bar)`,
    `• Gürültü Seviyesi: ${data.noise_db ? `${Math.round(data.noise_db)} dBA` : "—"}`,
    `• Durum: ${$("result-verdict")?.textContent || "Normal"}`,
  ].join("\n");

  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(summaryText)
      .then(() => showToast("✓ Mühendislik özeti panoya kopyalandı!"))
      .catch(() => showToast("Panoya kopyalama başarısız oldu."));
  } else {
    showToast("Tarayıcı panosu desteklenmiyor.");
  }
}

function setupStickyResultsBar() {
  const stickyBar = $("sticky-results-bar");
  const resultsCard = $("results");
  if (!stickyBar || !resultsCard) return;

  window.addEventListener("scroll", () => {
    if (resultsCard.hidden) {
      stickyBar.classList.remove("visible");
      return;
    }
    const rect = resultsCard.getBoundingClientRect();
    if (rect.top < -80 && rect.bottom > 150) {
      stickyBar.classList.add("visible");
    } else {
      stickyBar.classList.remove("visible");
    }
  }, { passive: true });

  stickyBar.addEventListener("click", (evt) => {
    const btn = evt.target.closest(".sticky-btn");
    if (!btn) return;
    const targetId = btn.dataset.target;
    const targetEl = $(targetId);
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
}

function setupShortcuts() {
  const shortcutsModal = $("shortcuts-modal");
  $("btn-open-shortcuts")?.addEventListener("click", () => shortcutsModal?.showModal());
  $("modal-shortcuts-close")?.addEventListener("click", () => shortcutsModal?.close());

  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      calculate(true);
      return;
    }
    if (event.key === "Escape") {
      $("report-modal")?.close();
      $("converter-modal")?.close();
      $("shortcuts-modal")?.close();
      return;
    }
    if (document.activeElement && ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      return;
    }
    if (event.key === "1") {
      $("tab-liquid")?.click();
    } else if (event.key === "2") {
      $("tab-gas")?.click();
    } else if (event.key === "3") {
      $("tab-steam")?.click();
    } else if (event.key === "t" || event.key === "T") {
      toggleTheme();
    } else if (event.key === "u" || event.key === "U") {
      $("btn-open-converter")?.click();
    } else if (event.key === "?") {
      shortcutsModal?.showModal();
    }
  });
}

function registerServiceWorker() {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker
        .register("/sw.js")
        .then((reg) => {
          reg.update().catch(() => {});
        })
        .catch(() => {});
    });
  }
}

async function init() {
  initTheme();
  setupEvents();
  setupPresetFilters();
  setupShortcuts();
  setupUnitConverter();
  registerServiceWorker();

  $("btn-theme-toggle")?.addEventListener("click", toggleTheme);
  $("btn-project-save")?.addEventListener("click", exportProject);
  $("btn-project-load")?.addEventListener("click", () => $("project-file-input")?.click());
  $("project-file-input")?.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) handleProjectFile(e.target.files[0]);
  });
  $("btn-isa20-report")?.addEventListener("click", openIsa20Modal);
  $("btn-md-report")?.addEventListener("click", openMarkdownReportModal);
  $("modal-report-close")?.addEventListener("click", () => $("report-modal")?.close());
  $("btn-copy-report")?.addEventListener("click", () => {
    if (state.activeReport?.text) {
      navigator.clipboard.writeText(state.activeReport.text).then(() => showToast("Rapor panoya kopyalandı."));
    }
  });
  $("btn-download-report")?.addEventListener("click", () => {
    if (state.activeReport?.text) {
      const blob = new Blob([state.activeReport.text], { type: "text/markdown;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = state.activeReport.filename || "Report.md";
      a.click();
      URL.revokeObjectURL(a.href);
      showToast("Rapor dosyası indirildi.");
    }
  });
  $("multicase-toggle")?.addEventListener("change", (e) => {
    $("multicase-panel").hidden = !e.target.checked;
  });
  $("btn-eval-multicase")?.addEventListener("click", evaluateMultiCase);
  try {
    const meta = await fetchJson(`/api/meta?v=${Date.now()}`);
    state.meta = meta;
    $("version-badge").textContent = `v${meta.version}`;
    $("api-status").textContent = "API çevrimiçi";
    $("api-status").className = "status-dot ok";
    fillSelect($("vendor"), meta.vendors, "key", "label");
    updateVendorSizes();
    fillSelect($("characteristic"), meta.characteristics, "key", "label");
    fillSelect($("liquid-preset"), meta.liquid_presets, "key", "label");
    fillSelect($("gas-preset"), meta.gas_presets.map((item) => item.name), (name) => name, (name) => name);
    for (const service of ["liquid", "gas", "steam"]) {
      fillSelect($(SERVICE_UNIT[service].flow), meta.units[`${service}_flow`], "key", "label");
      fillSelect($(SERVICE_UNIT[service].pressure), meta.units.pressure, "key", "label");
      fillSelect($(SERVICE_UNIT[service].temperature), meta.units.temperature, "key", "label");
    }
    setDefaults();
    setupCategoryChips();
    setupStickyResultsBar();
    updateDeltaPBadges();
    updatePipeRatioPill();
    await applyLiquidPreset();
    init3d();
    state.flow2DViewer = createFlow2DViewer();
    $("flow2d-type")?.addEventListener("change", (e) => {
      state.flow2dType = e.target.value;
      if (state.pendingResult) updateFlow2D(state.pendingResult);
    });
    await calculate(true);
  } catch (error) {
    $("api-status").textContent = "API bağlantı hatası";
    $("api-status").className = "status-dot bad";
    showError(`Uygulama başlatılamadı: ${error.message}`);
  }
}

init();
