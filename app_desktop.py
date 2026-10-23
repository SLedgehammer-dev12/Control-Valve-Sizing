import contextlib
import logging
import re
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from config import GAS_PRESET_NAMES, GAS_PRESETS
from fluid_properties import LIQUID_PRESETS, evaluate_gas_mixture, evaluate_liquid_preset, get_pure_fluid_state, list_coolprop_fluids
from project_io import dump_project_json, load_project_json
from reporting import build_pdf_report, build_report
from units import (
    GAS_FLOW_UNITS,
    LIQUID_FLOW_UNITS,
    PRESSURE_UNITS,
    STEAM_FLOW_UNITS,
    TEMPERATURE_UNITS,
    UNIT_KIND_LABELS,
    UNIT_MAPS,
    convert_unit,
    gas_flow_to_nm3h,
    liquid_flow_to_m3h,
    pressure_from_bar_a,
    pressure_to_bar_a,
    steam_flow_to_kgh,
    temperature_from_c,
    temperature_to_c,
)
from valve_curve import evaluate_operating_point, generate_characteristic_curve, generate_installed_characteristic
from valve_sizing import GasSizingInput, LiquidSizingInput, SteamSizingInput, size_gas_valve, size_liquid_valve, size_steam_valve
from vendor_catalog import find_catalog_matches, get_vendor_definition, get_vendor_options

logger = logging.getLogger(__name__)

SERVICE_KEYS = ("liquid", "gas", "steam")
SERVICE_NAMES = ("Sivi", "Gaz", "Buhar")


class ToolTip:
    """Create a tooltip for a given widget (desktop Tkinter)."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.widget.bind("<Enter>", self._on_enter)
        self.widget.bind("<Leave>", self._on_leave)
        self.widget.bind("<Button-1>", self._on_leave)

    def _show_tooltip(self, _event):
        x, y, _, _ = self.widget.bbox("insert")
        if self.widget.winfo_width() > 0:
            x = self.widget.winfo_rootx() + 25
            y = self.widget.winfo_rooty() + 25
        else:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("Tahoma", 8, "normal"),
        )
        label.pack(ipadx=1)

    def _hide_tooltip(self, _event=None):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

    def _on_enter(self, event=None):
        self._show_tooltip(event)

    def _on_leave(self, _event=None):
        self._hide_tooltip()


def tooltip_label(widget, text):
    """Add a tooltip to a widget."""
    ToolTip(widget, text)


def _unit_key_for_label(unit_map: dict[str, str], value: str) -> str:
    """Map a displayed unit label back to its engine key."""
    for key, label in unit_map.items():
        if label == value:
            return key
    return value


def _service_key(value: object) -> str:
    key = str(value or "liquid").lower()
    if key not in SERVICE_KEYS:
        raise ValueError(f"Gecersiz servis: {value}")
    return key


def _absolute_pressure_unit(unit: str) -> str:
    return {"bar_g": "bar_a", "psi_g": "psi_a"}.get(unit, unit)


class _UnitVar(tk.StringVar):
    """Store a unit key while displaying its human-readable label."""

    def __init__(self, unit_map: dict[str, str], value: str) -> None:
        self._unit_map = unit_map
        super().__init__(value=unit_map.get(value, value))

    def get(self) -> str:
        return _unit_key_for_label(self._unit_map, super().get())

    def set(self, value: str) -> None:
        super().set(self._unit_map.get(value, value))


class ValveSizingApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Control Valve Sizing")
        self.root.geometry("1100x820")
        self.root.minsize(980, 720)

        self.service_type = tk.StringVar(value="liquid")
        self.service_slider = tk.DoubleVar(value=0.0)
        self.service_slider_label = tk.StringVar(value=SERVICE_NAMES[0])
        self.vendor_key = tk.StringVar(value="fisher_globe_eqpct")
        self.liquid_source = tk.StringVar(value="Preset")
        self.liquid_preset_label = tk.StringVar(value="Su")
        self.inputs = {
            # Liquid
            "liquid_flow_m3h": tk.DoubleVar(value=25.0),
            "liquid_p1": tk.DoubleVar(value=8.0),
            "liquid_p2": tk.DoubleVar(value=5.0),
            "liquid_temp_c": tk.DoubleVar(value=25.0),
            "liquid_density": tk.DoubleVar(value=998.0),
            "liquid_pv": tk.DoubleVar(value=0.023),
            "liquid_pc": tk.DoubleVar(value=220.64),
            "liquid_mu": tk.DoubleVar(value=0.00089),
            "liquid_fl": tk.DoubleVar(value=0.85),
            "liquid_fd": tk.DoubleVar(value=0.31),
            "liquid_pipe_in_mm": tk.DoubleVar(value=50.0),
            "liquid_pipe_out_mm": tk.DoubleVar(value=50.0),
            # Gas
            "gas_flow_nm3h": tk.DoubleVar(value=800.0),
            "gas_p1": tk.DoubleVar(value=8.0),
            "gas_p2": tk.DoubleVar(value=6.0),
            "gas_temp_c": tk.DoubleVar(value=20.0),
            "gas_mw": tk.DoubleVar(value=18.0),
            "gas_xt": tk.DoubleVar(value=0.69),
            "gas_composition": tk.StringVar(value="Doğal Gaz"),
            "gas_pipe_in_mm": tk.DoubleVar(value=80.0),
            "gas_pipe_out_mm": tk.DoubleVar(value=80.0),
            # Steam
            "steam_flow_kgh": tk.DoubleVar(value=2500.0),
            "steam_p1": tk.DoubleVar(value=12.0),
            "steam_p2": tk.DoubleVar(value=8.0),
            "steam_temp_c": tk.DoubleVar(value=220.0),
        }
        self.design_margin = tk.DoubleVar(value=15.0)
        self.flow_characteristic = tk.StringVar(value="equal_percentage")

        # Sector unit selectors (temperature / pressure / flow)
        self.liquid_temp_unit = _UnitVar(TEMPERATURE_UNITS, "C")
        self.liquid_pres_unit = _UnitVar(PRESSURE_UNITS, "bar_a")
        self.liquid_flow_unit = _UnitVar(LIQUID_FLOW_UNITS, "m3h")
        self.gas_model = tk.StringVar(value="real")
        self.gas_temp_unit = _UnitVar(TEMPERATURE_UNITS, "C")
        self.gas_pres_unit = _UnitVar(PRESSURE_UNITS, "bar_a")
        self.gas_flow_unit = _UnitVar(GAS_FLOW_UNITS, "nm3h")
        self.steam_temp_unit = _UnitVar(TEMPERATURE_UNITS, "C")
        self.steam_pres_unit = _UnitVar(PRESSURE_UNITS, "bar_a")
        self.steam_flow_unit = _UnitVar(STEAM_FLOW_UNITS, "kgh")

        # Live-calculation bookkeeping
        self._live_enabled = False
        self._syncing_service = False
        self._debounce_timer: str | None = None
        self._unit_previous: dict[str, str] = {}
        self._field_labels: dict[str, ttk.Label] = {}
        self._field_family: dict[str, str] = {}
        self._result_history: list[dict[str, Any]] = []

        # Display variables
        self.z_calculated_display = tk.StringVar(value="--")
        self._gas_z_value: float | None = None
        self.k_calculated_display = tk.StringVar(value="--")
        self.viscosity_calculated_display = tk.StringVar(value="--")
        self.gas_status_text = tk.StringVar(value="")
        self.gas_composition_text: tk.Text | None = None
        self.steam_k_display = tk.StringVar(value="1.30")
        self.steam_z_display = tk.StringVar(value="1.00")
        self.steam_status_text = tk.StringVar(value="")

        self._build_menu()
        self._build_ui()
        self._toggle_service()
        self._update_gas_properties()
        self._refresh_unit_labels()
        self._live_enabled = True

        # Snapshot of all input variable default values (for reset)
        self._var_defaults: dict[str, Any] = {}
        for attr in (
            "service_type", "vendor_key", "liquid_source", "liquid_preset_label",
            "design_margin", "flow_characteristic",
            "liquid_temp_unit", "liquid_pres_unit", "liquid_flow_unit",
            "gas_model", "gas_temp_unit", "gas_pres_unit", "gas_flow_unit",
            "steam_temp_unit", "steam_pres_unit", "steam_flow_unit",
        ):
            self._var_defaults[attr] = getattr(self, attr).get()
        for key, var in self.inputs.items():
            self._var_defaults[f"input:{key}"] = var.get()

        # Klavye kısayolları: Enter = Hesapla, Esc = Varsayılana Sıfırla
        self.root.bind("<Return>", lambda _event: self._calculate())
        self.root.bind("<Escape>", lambda _event: self._reset_to_defaults())

    def _reset_to_defaults(self) -> None:
        """Reset all input variables to their initial default values."""
        for attr, value in self._var_defaults.items():
            if attr.startswith("input:"):
                key = attr[len("input:"):]
                self.inputs[key].set(value)
            else:
                getattr(self, attr).set(value)
        self._result_history = []
        for key in self._unit_previous:
            self._unit_previous[key] = getattr(self, key).get()
        self._toggle_service()
        self._on_live_change()

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Projeyi Kaydet (JSON)", command=self._save_project)
        file_menu.add_command(label="Projeyi Yukle (JSON)", command=self._load_project)
        file_menu.add_separator()
        file_menu.add_command(label="Hesaplama Raporu Kaydet (Markdown)", command=self._save_report)
        file_menu.add_command(label="Hesaplama Raporu Kaydet (PDF)", command=self._save_pdf_report)
        file_menu.add_command(label="ISA-20 Datasheet Kaydet (MD / HTML)", command=self._export_isa20)
        file_menu.add_separator()
        file_menu.add_command(label="Cikis", command=self.root.quit)
        menubar.add_cascade(label="Dosya", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(
            label="Vana Karakteristik Eğrisi & Kontrol Analizi (IEC 60534-2-4)",
            command=self._open_characteristic_curve_dialog,
        )
        tools_menu.add_command(label="Termal Genlesme (Boru Hatti)", command=self._open_thermal_expansion_dialog)
        tools_menu.add_command(label="Joule-Thomson ve Gaz Hidrat Analizi", command=self._open_joule_thomson_dialog)
        tools_menu.add_command(label="Coklu Calisma Durumu (Multi-Case Sizing)", command=self._open_multicase_dialog)
        tools_menu.add_command(
            label="Global Vana Üreticileri & Model Eşleştirme (Vendor Match)",
            command=self._open_vendor_match_dialog,
        )
        tools_menu.add_separator()
        tools_menu.add_command(label="Kavitasyon Kademe Analizi (ISA-RP75.23)", command=self._open_cavitation_dialog)
        tools_menu.add_command(label="Salmastra ve Kacak Emisyon (ISO 15848-1)", command=self._open_packing_dialog)
        tools_menu.add_command(label="ISA-20 Sartname Veri Sayfasi (Datasheet)", command=self._open_isa20_dialog)
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Boru Guvenligi ve PSV Tahliye Debisi (API 14E / API 520)",
            command=self._open_safety_piping_dialog,
        )
        tools_menu.add_command(
            label="Gelismis Malzeme ve Bonnet Secimi (NACE / API 941)",
            command=self._open_material_selection_dialog,
        )
        tools_menu.add_command(
            label="Aktorator Tepki Suresi ve Hava Tuketimi (ISA-75.25)",
            command=self._open_actuator_dynamics_dialog,
        )
        menubar.add_cascade(label="Araclar", menu=tools_menu)

        self.root.config(menu=menubar)

    def _build_ui(self) -> None:
        self.root.configure(bg="#eef3f8")

        header = tk.Frame(self.root, bg="#12344d", padx=18, pady=16)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Control Valve Sizing",
            font=("Segoe UI Semibold", 20),
            fg="white",
            bg="#12344d",
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Sivi, gaz ve buhar sizing destekliyor; CoolProp ile Z, k, viskozite otomatik hesaplanir.",
            font=("Segoe UI", 10),
            fg="#d8e9f7",
            bg="#12344d",
        ).pack(anchor="w", pady=(4, 0))

        body = tk.Frame(self.root, bg="#eef3f8", padx=18, pady=18)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)
        body.grid_rowconfigure(3, weight=1)

        # Row 0: Service slider + Vendor
        top_card = ttk.LabelFrame(body, text="Servis Tipi / Vendor")
        top_card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(top_card, text="Servis:").grid(row=0, column=0, padx=(12, 4), pady=8, sticky="w")
        ttk.Scale(
            top_card,
            from_=0.0,
            to=2.0,
            orient="horizontal",
            variable=self.service_slider,
            command=self._on_service_slider,
            length=170,
        ).grid(row=0, column=1, padx=(0, 4), pady=8, sticky="ew")
        ttk.Label(top_card, textvariable=self.service_slider_label, width=6).grid(
            row=0, column=2, padx=(0, 12), pady=8, sticky="w"
        )
        ttk.Label(top_card, text="Vendor Trim:").grid(row=0, column=3, padx=12, pady=8, sticky="e")
        vendor_combo = ttk.Combobox(
            top_card,
            textvariable=self.vendor_key,
            values=get_vendor_options(),
            state="readonly",
            width=26,
        )
        vendor_combo.grid(row=0, column=4, padx=12, pady=8, sticky="w")
        ttk.Label(top_card, text="Tasarim Marj (%):").grid(row=1, column=3, padx=(12, 4), pady=8, sticky="e")
        ttk.Entry(top_card, textvariable=self.design_margin, width=7).grid(row=1, column=4, padx=(0, 4), pady=8, sticky="w")
        ttk.Label(top_card, text="Karakteristik:").grid(row=1, column=5, padx=(8, 4), pady=8, sticky="e")
        ttk.Combobox(
            top_card,
            textvariable=self.flow_characteristic,
            values=("equal_percentage", "linear", "quick_opening"),
            state="readonly",
            width=16,
        ).grid(row=1, column=6, padx=(0, 12), pady=8, sticky="w")

        # Row 1: Service tabs
        self.notebook = ttk.Notebook(body)
        self.notebook.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        self.liquid_frame = ttk.Frame(self.notebook, padding=8)
        self.gas_frame = ttk.Frame(self.notebook, padding=8)
        self.steam_frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.liquid_frame, text="Sivi Verileri")
        self.notebook.add(self.gas_frame, text="Gaz Verileri")
        self.notebook.add(self.steam_frame, text="Buhar Verileri")

        # Build liquid form with source selector and pipe reducer
        self._build_form_liquid(self.liquid_frame)
        self._build_form_gas(self.gas_frame)
        self._build_form_steam(self.steam_frame)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Live calculation: re-run on any flow / pressure / temperature edit with debounce
        live_keys = (
            "liquid_flow_m3h", "liquid_p1", "liquid_p2", "liquid_temp_c",
            "gas_flow_nm3h", "gas_p1", "gas_p2", "gas_temp_c",
            "steam_flow_kgh", "steam_p1", "steam_p2", "steam_temp_c",
        )
        for key in live_keys:
            self.inputs[key].trace_add("write", self._queue_live_change)
        for key in ("liquid_p1", "liquid_temp_c"):
            self.inputs[key].trace_add("write", self._queue_liquid_conditions_change)

        # Row 3: Action bar
        action_bar = tk.Frame(body, bg="#eef3f8")
        action_bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        tk.Button(
            action_bar,
            text="Hesapla",
            command=self._calculate,
            bg="#1f6f5f",
            fg="white",
            activebackground="#19584b",
            relief="flat",
            font=("Segoe UI Semibold", 11),
            padx=18,
            pady=10,
        ).pack(side="left", padx=(0, 10))
        tk.Button(
            action_bar,
            text="Raporu Kaydet",
            command=self._save_report,
            bg="#2a6d8a",
            fg="white",
            activebackground="#1f5670",
            relief="flat",
            font=("Segoe UI Semibold", 11),
            padx=18,
            pady=10,
        ).pack(side="left")
        tk.Button(
            action_bar,
            text="Varsayılana Sıfırla",
            command=self._reset_to_defaults,
            bg="#6c757d",
            fg="white",
            activebackground="#5a6268",
            relief="flat",
            font=("Segoe UI Semibold", 11),
            padx=18,
            pady=10,
        ).pack(side="left")
        tk.Button(
            action_bar,
            text="Gecmis / Karsilastirma",
            command=self._show_history_dialog,
            bg="#8a6d3b",
            fg="white",
            activebackground="#725a30",
            relief="flat",
            font=("Segoe UI Semibold", 11),
            padx=18,
            pady=10,
        ).pack(side="left")
        tk.Button(
            action_bar,
            text="Birim Dönüştürücü",
            command=self._show_unit_converter,
            bg="#4a5568",
            fg="white",
            activebackground="#3b4453",
            relief="flat",
            font=("Segoe UI Semibold", 11),
            padx=18,
            pady=10,
        ).pack(side="left", padx=(10, 0))

        self.result_box = tk.Text(
            body,
            wrap="word",
            font=("Consolas", 11),
            bg="#0f1b24",
            fg="#ecf4fb",
            insertbackground="white",
            relief="flat",
            padx=14,
            pady=14,
        )
        self.result_box.grid(row=3, column=0, columnspan=2, sticky="nsew")

    def _build_form_liquid(self, parent: ttk.Frame) -> None:
        """Build liquid form with source selector, pipe reducer fields."""
        row = 0
        # Source selector
        ttk.Label(parent, text="Akiskan kaynagi").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        source_combo = ttk.Combobox(
            parent,
            textvariable=self.liquid_source,
            values=["Preset", "CoolProp pure fluid", "Custom"],
            state="readonly",
            width=16,
        )
        source_combo.grid(row=row, column=1, sticky="ew", padx=10, pady=8)

        def _on_source_change(*_args):
            src = self.liquid_source.get()
            if src == "Preset":
                self.liquid_preset_combo.configure(values=[v["label"] for v in LIQUID_PRESETS.values()])
                self.liquid_preset_label.set("Su")
            elif src == "CoolProp pure fluid":
                self.liquid_preset_combo.configure(values=list_coolprop_fluids())
                self.liquid_preset_label.set("Water")
            self._update_liquid_properties()
            self._on_live_change()

        source_combo.bind("<<ComboboxSelected>>", _on_source_change)
        row += 1

        # Preset / Fluid selector
        ttk.Label(parent, text="Preset / Fluid").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.liquid_preset_combo = ttk.Combobox(
            parent,
            textvariable=self.liquid_preset_label,
            values=[str(v["label"]) for v in LIQUID_PRESETS.values()],
            state="readonly",
            width=16,
        )
        self.liquid_preset_combo.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        self.liquid_preset_combo.bind("<<ComboboxSelected>>", self._on_preset_change)
        row += 1

        # Temperature and basic fields
        self._add_unit_selector_row(parent, row, "liquid", LIQUID_FLOW_UNITS)
        row += 1
        fields = [
            ("Sicaklik", "temp", "liquid_temp_c"),
            ("Debi", "flow", "liquid_flow_m3h"),
            ("Giris basinci", "pres", "liquid_p1"),
            ("Cikis basinci", "pres", "liquid_p2"),
            ("Yogunluk", None, "liquid_density"),
            ("Buhar basinci", "pres_abs", "liquid_pv"),
            ("Kritik basinc", "pres_abs", "liquid_pc"),
            ("Viskozite", None, "liquid_mu"),
            ("FL", None, "liquid_fl"),
            ("Fd", None, "liquid_fd"),
            ("Hat giris capi", None, "liquid_pipe_in_mm"),
            ("Hat cikis capi", None, "liquid_pipe_out_mm"),
        ]
        for base_label, family, key in fields:
            text = self._field_label_text(base_label, family, "liquid")
            lbl = ttk.Label(parent, text=text)
            lbl.grid(row=row, column=0, sticky="w", padx=10, pady=6)
            self._field_labels[key] = lbl
            if family:
                self._field_family[key] = family
            ttk.Entry(parent, textvariable=self.inputs[key], width=18).grid(
                row=row, column=1, sticky="ew", padx=10, pady=6
            )
            row += 1

        parent.grid_columnconfigure(1, weight=1)

    def _add_unit_selector_row(self, parent: ttk.Frame, row: int, prefix: str, flow_units: dict[str, str]) -> None:
        """Add a compact temperature / pressure / flow unit selector row."""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=4)
        ttk.Label(frame, text="Birimler:").pack(side="left")
        spec = [
            ("Sicaklik", f"{prefix}_temp_unit", TEMPERATURE_UNITS, "temp"),
            ("Basinc", f"{prefix}_pres_unit", PRESSURE_UNITS, "pres"),
            ("Debi", f"{prefix}_flow_unit", flow_units, "flow"),
        ]
        for label_text, var_name, unit_map, kind in spec:
            ttk.Label(frame, text=label_text).pack(side="left", padx=(10, 2))
            unit_var = getattr(self, var_name)
            self._unit_previous[var_name] = unit_var.get()
            combo = ttk.Combobox(frame, textvariable=unit_var, values=list(unit_map.values()), state="readonly", width=10)
            combo.pack(side="left", padx=(0, 4))
            def _on_unit_selected(_event: object, p: str = prefix, k: str = kind, v: str = var_name) -> None:
                self._on_unit_change(p, k, v)

            combo.bind("<<ComboboxSelected>>", _on_unit_selected)

    def _flow_map_for(self, prefix: str) -> dict[str, str]:
        if prefix == "liquid":
            return LIQUID_FLOW_UNITS
        if prefix == "gas":
            return GAS_FLOW_UNITS
        return STEAM_FLOW_UNITS

    def _field_label_text(self, base_label: str, family: str | None, prefix: str) -> str:
        """Build a field label including the selected unit when applicable."""
        if family == "temp":
            unit = getattr(self, f"{prefix}_temp_unit").get()
            return f"{base_label} [{TEMPERATURE_UNITS[unit]}]"
        if family == "pres":
            unit = getattr(self, f"{prefix}_pres_unit").get()
            return f"{base_label} [{PRESSURE_UNITS[unit]}]"
        if family == "pres_abs":
            unit = _absolute_pressure_unit(getattr(self, f"{prefix}_pres_unit").get())
            return f"{base_label} [{PRESSURE_UNITS[unit]}]"
        if family == "flow":
            unit = getattr(self, f"{prefix}_flow_unit").get()
            return f"{base_label} [{self._flow_map_for(prefix)[unit]}]"
        return base_label

    def _refresh_unit_labels(self) -> None:
        """Update field labels to reflect the currently selected units."""
        for key, family in self._field_family.items():
            prefix = key.split("_", 1)[0]
            base_label = self._field_labels[key].cget("text")
            base = base_label.split(" [")[0]
            self._field_labels[key].config(text=self._field_label_text(base, family, prefix))

    def _unit_fields(self, prefix: str, kind: str) -> tuple[str, ...]:
        if kind == "temp":
            return (f"{prefix}_temp_c",)
        if kind == "pres":
            if prefix == "liquid":
                return ("liquid_p1", "liquid_p2", "liquid_pv", "liquid_pc")
            return (f"{prefix}_p1", f"{prefix}_p2")
        return {
            "liquid": ("liquid_flow_m3h",),
            "gas": ("gas_flow_nm3h",),
            "steam": ("steam_flow_kgh",),
        }[prefix]

    def _gas_model_key(self) -> str:
        var = getattr(self, "gas_model", None)
        return var.get() if var is not None else "auto"

    def _gas_z_for_conversion(self) -> float:
        z_value = getattr(self, "_gas_z_value", None)
        if isinstance(z_value, (int, float)) and z_value > 0:
            return float(z_value)
        with contextlib.suppress(ValueError):
            return float(self.z_calculated_display.get())
        return 1.0

    def _convert_unit_value(self, kind: str, value: float, previous: str, new: str, prefix: str, field: str) -> float:
        if kind == "temp":
            return convert_unit("temperature", value, previous, new)
        if kind == "pres":
            if prefix == "liquid" and field in {"liquid_pv", "liquid_pc"}:
                return convert_unit("pressure", value, _absolute_pressure_unit(previous), _absolute_pressure_unit(new))
            return convert_unit("pressure", value, previous, new)
        unit_kind = {"liquid": "liquid_flow", "gas": "gas_flow", "steam": "steam_flow"}[prefix]
        context: dict[str, Any] = {}
        if prefix == "liquid":
            context["density_kg_m3"] = self.inputs["liquid_density"].get()
        elif prefix == "gas" and ({"m3h", "kgh"} & {previous, new}):
            pressure = pressure_to_bar_a(self.inputs["gas_p1"].get(), self.gas_pres_unit.get())
            temperature = temperature_to_c(self.inputs["gas_temp_c"].get(), self.gas_temp_unit.get())
            z_factor = self._gas_z_for_conversion()
            molecular_weight = self.inputs["gas_mw"].get() / 1000.0
            # shortcut: ideal-gas density with Z for kgh/m3h unit changes; upgrade to CoolProp density if composition accuracy matters.
            density = pressure * 1e5 * molecular_weight / (max(z_factor, 1e-6) * 8.314462618 * (temperature + 273.15))
            context.update(
                pressure_bar_a=pressure,
                temperature_c=temperature,
                z=z_factor,
                density_kg_m3=density,
            )
        return convert_unit(unit_kind, value, previous, new, **context)

    def _on_unit_change(self, prefix: str, kind: str, var_name: str) -> None:
        """Convert existing values to the newly selected unit, then recalculate."""
        previous = self._unit_previous.get(var_name)
        new = getattr(self, var_name).get()
        if not previous or previous == new:
            self._unit_previous[var_name] = new
            return
        keys = self._unit_fields(prefix, kind)
        was_live = getattr(self, "_live_enabled", False)
        self._live_enabled = False
        try:
            converted = [self._convert_unit_value(kind, self.inputs[key].get(), previous, new, prefix, key) for key in keys]
        except Exception as exc:
            getattr(self, var_name).set(previous)
            self._unit_previous[var_name] = previous
            self._live_enabled = was_live
            messagebox.showerror("Birim donusumu", f"Birim donusumu yapilamadi: {exc}")
            return
        self._unit_previous[var_name] = new
        for key, value in zip(keys, converted, strict=True):
            self.inputs[key].set(float(f"{value:.6g}"))
        self._live_enabled = was_live
        self._refresh_unit_labels()
        if was_live:
            self._calculate(show_errors=False)

    def _on_preset_change(self, *_args) -> str:
        """Refresh liquid properties from the selected preset and re-calculate."""
        self._update_liquid_properties()
        return self._on_live_change()

    def _queue_live_change(self, *_args) -> None:
        if self._debounce_timer is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._debounce_timer)
        self._debounce_timer = self.root.after(300, self._on_live_change)

    def _queue_liquid_conditions_change(self, *_args) -> None:
        if not getattr(self, "_live_enabled", False) or self.liquid_source.get() == "Custom":
            return
        if self._debounce_timer is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._debounce_timer)
        self._debounce_timer = self.root.after(300, self._on_liquid_conditions_change)

    def _on_live_change(self, *_args) -> str:
        """Re-calculate silently on unit changes or input edits."""
        self._debounce_timer = None
        if not getattr(self, "_live_enabled", False):
            return ""
        with contextlib.suppress(tk.TclError):
            self._refresh_unit_labels()
            self._calculate(show_errors=False)
        return ""

    def _on_liquid_conditions_change(self, *_args) -> None:
        if not getattr(self, "_live_enabled", False) or self.liquid_source.get() == "Custom":
            return
        self._update_liquid_properties()
        self._on_live_change()

    def _build_form_steam(self, parent: ttk.Frame) -> None:
        """Build steam form with auto-calculated k and Z from CoolProp."""
        self._add_unit_selector_row(parent, 0, "steam", STEAM_FLOW_UNITS)
        fields = [
            ("Debi", "flow", "steam_flow_kgh"),
            ("Giris basinci", "pres", "steam_p1"),
            ("Cikis basinci", "pres", "steam_p2"),
            ("Sicaklik", "temp", "steam_temp_c"),
        ]
        row = 1
        for base_label, family, key in fields:
            text = self._field_label_text(base_label, family, "steam")
            lbl = ttk.Label(parent, text=text)
            lbl.grid(row=row, column=0, sticky="w", padx=10, pady=8)
            self._field_labels[key] = lbl
            if family:
                self._field_family[key] = family
            ttk.Entry(parent, textvariable=self.inputs[key], width=18).grid(
                row=row, column=1, sticky="ew", padx=10, pady=8
            )
            row += 1

        ttk.Label(parent, text="k = Cp/Cv (Hesaplanan)").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        ttk.Label(parent, textvariable=self.steam_k_display, relief="sunken", width=18).grid(
            row=row, column=1, sticky="ew", padx=10, pady=8
        )
        row += 1
        ttk.Label(parent, text="Z (Hesaplanan)").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        ttk.Label(parent, textvariable=self.steam_z_display, relief="sunken", width=18).grid(
            row=row, column=1, sticky="ew", padx=10, pady=8
        )
        row += 1
        ttk.Label(parent, textvariable=self.steam_status_text, foreground="#a94442").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8)
        )

    def _build_form_gas(self, parent: ttk.Frame) -> None:
        """Build gas form with composition selector and calculated Z display."""
        self._add_unit_selector_row(parent, 0, "gas", GAS_FLOW_UNITS)
        fields_simple = [
            ("Debi", "flow", "gas_flow_nm3h"),
            ("Giris basinci", "pres", "gas_p1"),
            ("Cikis basinci", "pres", "gas_p2"),
            ("Sicaklik", "temp", "gas_temp_c"),
        ]

        # Build simple fields
        row = 1
        for base_label, family, key in fields_simple:
            text = self._field_label_text(base_label, family, "gas")
            lbl = ttk.Label(parent, text=text)
            lbl.grid(row=row, column=0, sticky="w", padx=10, pady=8)
            self._field_labels[key] = lbl
            if family:
                self._field_family[key] = family
            ttk.Entry(parent, textvariable=self.inputs[key], width=18).grid(
                row=row, column=1, sticky="ew", padx=10, pady=8
            )
            row += 1

        # Add gas type selector
        ttk.Label(parent, text="Gaz Tipi").grid(row=row, column=0, sticky="w", padx=10, pady=8)

        # We use a list of values including Custom
        gas_values = GAS_PRESET_NAMES + ["Özel (Custom)"]
        gas_type_combo = ttk.Combobox(
            parent,
            textvariable=self.inputs["gas_composition"],
            values=gas_values,
            state="readonly",
            width=16
        )
        gas_type_combo.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1

        ttk.Label(parent, text="Gaz modeli").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        gas_model_combo = ttk.Combobox(
            parent,
            textvariable=self.gas_model,
            values=("real", "auto", "ideal"),
            state="readonly",
            width=16,
        )
        gas_model_combo.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        gas_model_combo.bind("<<ComboboxSelected>>", self._on_live_change)
        row += 1

        # Add custom gas composition text area
        ttk.Label(parent, text="Özel Gaz Bileşimi\n(Örn: Methane 90)").grid(
            row=row, column=0, sticky="nw", padx=10, pady=8
        )
        self.gas_composition_text = tk.Text(parent, height=4, width=18)
        self.gas_composition_text.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        self.gas_composition_text.bind("<KeyRelease>", lambda _e: self._update_gas_properties())
        self.gas_composition_text.grid_remove() # Initially hidden
        row += 1

        # Watch gas composition and conditions to refresh Z and MW automatically
        def _on_gas_composition_change(*_args):
            if self.gas_composition_text is not None:
                if self.inputs["gas_composition"].get() == "Özel (Custom)":
                    self.gas_composition_text.grid()
                else:
                    self.gas_composition_text.grid_remove()
            self._update_gas_properties()

        self.inputs["gas_composition"].trace_add("write", _on_gas_composition_change)
        self.inputs["gas_p1"].trace_add("write", lambda *_args: self._update_gas_properties())
        self.inputs["gas_temp_c"].trace_add("write", lambda *_args: self._update_gas_properties())

        # Add calculated Z display
        ttk.Label(parent, text="Z (Hesaplanan)").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        z_display = ttk.Label(
            parent,
            textvariable=self.z_calculated_display,
            relief="sunken",
            width=18
        )
        z_display.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1

        # Add gas status message below Z
        status_label = ttk.Label(parent, textvariable=self.gas_status_text, foreground="#a94442")
        status_label.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8))
        row += 1

        # Add molecular weight display as readonly field
        ttk.Label(parent, text="Molekuler agirlik").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self.inputs["gas_mw"], width=18, state="readonly").grid(
            row=row, column=1, sticky="ew", padx=10, pady=8
        )
        row += 1

        # Add calculated k (Cp/Cv) display
        ttk.Label(parent, text="k = Cp/Cv (Hesaplanan)").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        k_display = ttk.Label(
            parent,
            textvariable=self.k_calculated_display,
            relief="sunken",
            width=18
        )
        k_display.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1

        # Add calculated viscosity display
        ttk.Label(parent, text="Viskozite [Pa.s] (Hesaplanan)").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        mu_display = ttk.Label(
            parent,
            textvariable=self.viscosity_calculated_display,
            relief="sunken",
            width=18
        )
        mu_display.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        row += 1

        # Pipe reducer fields
        ttk.Label(parent, text="Hat giris capi [mm]").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self.inputs["gas_pipe_in_mm"], width=18).grid(
            row=row, column=1, sticky="ew", padx=10, pady=8
        )
        row += 1
        ttk.Label(parent, text="Hat cikis capi [mm]").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self.inputs["gas_pipe_out_mm"], width=18).grid(
            row=row, column=1, sticky="ew", padx=10, pady=8
        )
        row += 1

        parent.grid_columnconfigure(1, weight=1)


    def _parse_custom_composition(self) -> list[dict[str, float | str]]:
        """Parse text area content into composition list."""
        if self.gas_composition_text is None:
            return []
        text = self.gas_composition_text.get("1.0", "end-1c").strip()
        if not text:
            return []

        composition = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = re.split(r'[:\s]+', line)
            if len(parts) >= 2:
                try:
                    comp = parts[0]
                    val = float(parts[1])
                    composition.append({"component": comp, "fraction_pct": val})
                except ValueError:
                    continue
        return composition

    def _calculate_gas_properties(self, raise_on_error: bool = False) -> tuple[float, float, float]:
        """
        Calculate Z, specific_heat_ratio (k) and viscosity from gas composition
        and conditions using CoolProp. Falls back to defaults if calculation fails.
        Returns (z, k, viscosity_pa_s).
        """
        def _fail(message: str):
            self._gas_z_value = None
            self.z_calculated_display.set("--")
            self.k_calculated_display.set("--")
            self.viscosity_calculated_display.set("--")
            self.gas_status_text.set(message)
            if raise_on_error:
                raise ValueError(message)
            return 1.0, 1.30, 1e-5

        gas_type = self.inputs["gas_composition"].get()
        if gas_type not in GAS_PRESETS and gas_type != "Özel (Custom)":
            return _fail("Bilinmeyen gaz tipi secildi.")
        composition = self._gas_composition_rows()
        if not composition:
            return _fail("Gaz kompozisyonu bos; varsayilan degerler kullanildi.")

        pressure_bar_a = pressure_to_bar_a(self.inputs["gas_p1"].get(), self.gas_pres_unit.get())
        temperature_c = temperature_to_c(self.inputs["gas_temp_c"].get(), self.gas_temp_unit.get())

        try:
            total_pct = sum(float(row["fraction_pct"]) for row in composition)
            if abs(total_pct - 100.0) > 1e-6:
                return _fail(f"Toplam {total_pct:.4f}% - 100% olmali; varsayilan degerler kullanildi.")

            summary = evaluate_gas_mixture(
                composition,
                "molar",
                pressure_bar_a,
                temperature_c,
                self._gas_model_key(),
            )
            z_value = summary.z if summary.z is not None else 1.0
            self._gas_z_value = z_value
            k_value = summary.specific_heat_ratio if summary.specific_heat_ratio is not None else 1.30
            mu_value = summary.viscosity_pa_s if summary.viscosity_pa_s is not None else 1e-5

            if summary.average_molecular_weight is not None:
                self.inputs["gas_mw"].set(summary.average_molecular_weight)

            if z_value < 0.25 or z_value > 1.5:
                self.gas_status_text.set(f"Uyari: Z={z_value:.3f} tipik araligin disinda.")
            else:
                self.gas_status_text.set("")

            self.z_calculated_display.set(f"{z_value:.5f}")
            self.k_calculated_display.set(f"{k_value:.5f}")
            self.viscosity_calculated_display.set(f"{mu_value:.5g}")
            if summary.fallback_used:
                self.gas_status_text.set("CoolProp HEOS kullanılamadı; ideal gaz varsayımları kullanıldı.")
            return z_value, k_value, mu_value
        except Exception as exc:
            return _fail(f"Gaz ozellikleri hesaplanamadi: {exc}.")

    def _gas_composition_rows(self) -> list[dict[str, float | str]]:
        """Return the active gas composition rows (preset or custom)."""
        gas_type = self.inputs["gas_composition"].get()
        if gas_type == "Özel (Custom)":
            return self._parse_custom_composition()
        if gas_type in GAS_PRESETS:
            return GAS_PRESETS[gas_type]["components"]
        return []

    def _update_gas_properties(self) -> None:
        """Refresh calculated gas properties from selected preset and current conditions."""
        z_factor, k_value, mu_value = self._calculate_gas_properties()
        if z_factor == 1.0 and self.z_calculated_display.get() == "ERROR":
            return

    def _on_service_slider(self, value: str) -> None:
        if self._syncing_service or not hasattr(self, "notebook"):
            return
        index = min(2, max(0, int(round(float(value)))))
        if self.notebook.select() != str(self.notebook.tabs()[index]):
            self.notebook.select(index)

    def _on_tab_changed(self, _event: object = None) -> None:
        index = self.notebook.index(self.notebook.select())
        self.service_type.set(SERVICE_KEYS[index])
        self._toggle_service()
        if self._live_enabled:
            self._calculate(show_errors=False)

    def _toggle_service(self) -> None:
        if self._syncing_service:
            return
        self._syncing_service = True
        try:
            svc = self.service_type.get()
            index = SERVICE_KEYS.index(svc)
            if self.notebook.index(self.notebook.select()) != index:
                self.notebook.select(index)
            self.service_slider.set(float(index))
            self.service_slider_label.set(SERVICE_NAMES[index])
            is_liquid = svc == "liquid"
            is_gas = svc == "gas"
            is_steam = svc == "steam"
            for child in self.liquid_frame.winfo_children():
                with contextlib.suppress(tk.TclError):
                    child.configure(state="normal" if is_liquid else "disabled")  # type: ignore[call-overload,call-arg]
            for child in self.gas_frame.winfo_children():
                with contextlib.suppress(tk.TclError):
                    child.configure(state="normal" if is_gas else "disabled")  # type: ignore[call-overload,call-arg]
            for child in self.steam_frame.winfo_children():
                with contextlib.suppress(tk.TclError):
                    child.configure(state="normal" if is_steam else "disabled")  # type: ignore[call-overload,call-arg]
        finally:
            self._syncing_service = False

    def _liquid_pressures_bar_a(self) -> dict[str, float]:
        unit = self.liquid_pres_unit.get()
        absolute_unit = _absolute_pressure_unit(unit)
        return {
            "liquid_p1": pressure_to_bar_a(self.inputs["liquid_p1"].get(), unit),
            "liquid_p2": pressure_to_bar_a(self.inputs["liquid_p2"].get(), unit),
            "liquid_pv": pressure_to_bar_a(self.inputs["liquid_pv"].get(), absolute_unit),
            "liquid_pc": pressure_to_bar_a(self.inputs["liquid_pc"].get(), absolute_unit),
        }

    def _multicase_operating_case(
        self,
        service: str,
        name: str,
        flow: float,
        p1: float,
        p2: float,
        flow_unit: str,
        pressure_unit: str,
        temp_c: float,
    ):
        from multi_case import OperatingCase

        p1_bar_a = pressure_to_bar_a(p1, pressure_unit)
        p2_bar_a = pressure_to_bar_a(p2, pressure_unit)
        if service == "liquid":
            flow_engine = liquid_flow_to_m3h(flow, flow_unit, density_kg_m3=self.inputs["liquid_density"].get())
        elif service == "gas":
            summary = evaluate_gas_mixture(self._gas_composition_rows(), "molar", p1_bar_a, temp_c, self._gas_model_key())
            flow_engine = gas_flow_to_nm3h(
                flow,
                flow_unit,
                pressure_bar_a=p1_bar_a,
                temperature_c=temp_c,
                z=summary.z or 1.0,
                density_kg_m3=summary.density_kg_m3,
            )
        else:
            flow_engine = steam_flow_to_kgh(flow, flow_unit)
        extra_props: dict[str, Any] = {}
        if service == "gas":
            extra_props = {
                "molecular_weight": summary.average_molecular_weight,
                "specific_heat_ratio": summary.specific_heat_ratio or 1.30,
                "viscosity_pa_s": summary.viscosity_pa_s or 1.8e-5,
                "z": summary.z or 1.0,
            }
        return OperatingCase(name, flow_engine, p1_bar_a, p2_bar_a, temp_c, extra_props=extra_props)

    def _update_liquid_properties(self) -> None:
        """Auto-fill liquid properties from preset or CoolProp."""
        source = self.liquid_source.get()
        label = self.liquid_preset_label.get()
        unit = _absolute_pressure_unit(self.liquid_pres_unit.get())
        if source == "Preset":
            preset_map = {v["label"]: k for k, v in LIQUID_PRESETS.items()}
            key = preset_map.get(label)
            if key:
                pressures = self._liquid_pressures_bar_a()
                preset = evaluate_liquid_preset(
                    key,
                    pressures["liquid_p1"],
                    temperature_to_c(self.inputs["liquid_temp_c"].get(), self.liquid_temp_unit.get()),
                )
                self.inputs["liquid_density"].set(preset["density_kg_m3"])
                self.inputs["liquid_pv"].set(pressure_from_bar_a(preset["vapor_pressure_bar_a"], unit))
                self.inputs["liquid_pc"].set(pressure_from_bar_a(preset["critical_pressure_bar_a"], unit))
                self.inputs["liquid_mu"].set(preset["viscosity_pa_s"])
        elif source == "CoolProp pure fluid":
            try:
                props = get_pure_fluid_state(
                    label,
                    self._liquid_pressures_bar_a()["liquid_p1"],
                    temperature_to_c(self.inputs["liquid_temp_c"].get(), self.liquid_temp_unit.get()),
                )
                self.inputs["liquid_density"].set(props["density_kg_m3"])
                self.inputs["liquid_pv"].set(pressure_from_bar_a(props["vapor_pressure_bar_a"], unit))
                self.inputs["liquid_pc"].set(pressure_from_bar_a(props["critical_pressure_bar_a"], unit))
                self.inputs["liquid_mu"].set(props["viscosity_pa_s"])
            except Exception:
                pass  # Keep current values on error

    def _vendor_meta_for_service(self, vendor, service: str) -> dict:
        base = {"vendor": vendor.vendor, "family": vendor.family, "style": vendor.style}
        if service == "steam":
            base["xT"] = vendor.xt
        else:
            base["FL"] = vendor.fl
            base["Fd"] = vendor.fd
            if service == "gas":
                base["xT"] = vendor.xt
        base["pressure_class"] = vendor.pressure_class
        base["leakage_class"] = vendor.leakage_class
        return base

    def _calc_liquid(self, vendor):
        pressures = self._liquid_pressures_bar_a()
        p1 = pressures["liquid_p1"]
        p2 = pressures["liquid_p2"]
        pv = pressures["liquid_pv"]
        pc = pressures["liquid_pc"]
        temp_c = temperature_to_c(self.inputs["liquid_temp_c"].get(), self.liquid_temp_unit.get())
        result = size_liquid_valve(
            LiquidSizingInput(
                flow_m3h=liquid_flow_to_m3h(
                    self.inputs["liquid_flow_m3h"].get(),
                    self.liquid_flow_unit.get(),
                    density_kg_m3=self.inputs["liquid_density"].get(),
                ),
                inlet_pressure_bar_a=p1,
                outlet_pressure_bar_a=p2,
                density_kg_m3=self.inputs["liquid_density"].get(),
                vapor_pressure_bar_a=pv,
                critical_pressure_bar_a=pc,
                viscosity_pa_s=self.inputs["liquid_mu"].get(),
                fl=vendor.fl or self.inputs["liquid_fl"].get(),
                fd=vendor.fd or self.inputs["liquid_fd"].get(),
                pipe_inlet_diameter_mm=self.inputs["liquid_pipe_in_mm"].get(),
                pipe_outlet_diameter_mm=self.inputs["liquid_pipe_out_mm"].get(),
            ),
            valve_series=list(vendor.sizes),
            valve_meta=self._vendor_meta_for_service(vendor, "liquid"),
            design_margin_pct=self.design_margin.get(),
            flow_characteristic=self.flow_characteristic.get(),
        )
        absolute_unit = _absolute_pressure_unit(self.liquid_pres_unit.get())
        fluid_summary = {
            "Fluid": self.liquid_preset_label.get(),
            f"Temperature [{TEMPERATURE_UNITS[self.liquid_temp_unit.get()]}]": f"{temperature_from_c(temp_c, self.liquid_temp_unit.get()):.3f}",
            "Density [kg/m3]": f"{self.inputs['liquid_density'].get():.4f}",
            f"Pv [{PRESSURE_UNITS[absolute_unit]}]": f"{pressure_from_bar_a(pv, absolute_unit):.5f}",
            f"Pc [{PRESSURE_UNITS[absolute_unit]}]": f"{pressure_from_bar_a(pc, absolute_unit):.5f}",
            "Viscosity [Pa.s]": f"{self.inputs['liquid_mu'].get():.7g}",
        }
        return result, fluid_summary

    def _calc_gas(self, vendor):
        z_factor, k_value, mu_value = self._calculate_gas_properties(raise_on_error=True)
        p1 = pressure_to_bar_a(self.inputs["gas_p1"].get(), self.gas_pres_unit.get())
        p2 = pressure_to_bar_a(self.inputs["gas_p2"].get(), self.gas_pres_unit.get())
        temp_c = temperature_to_c(self.inputs["gas_temp_c"].get(), self.gas_temp_unit.get())
        summary = evaluate_gas_mixture(self._gas_composition_rows(), "molar", p1, temp_c, self._gas_model_key())
        flow_nm3h = gas_flow_to_nm3h(
            self.inputs["gas_flow_nm3h"].get(),
            self.gas_flow_unit.get(),
            pressure_bar_a=p1,
            temperature_c=temp_c,
            z=z_factor,
            density_kg_m3=summary.density_kg_m3,
        )
        result = size_gas_valve(
            GasSizingInput(
                flow_nm3h=flow_nm3h,
                inlet_pressure_bar_a=p1,
                outlet_pressure_bar_a=p2,
                temperature_c=temp_c,
                molecular_weight=self.inputs["gas_mw"].get(),
                specific_heat_ratio=k_value,
                viscosity_pa_s=mu_value,
                z=z_factor,
                fl=vendor.fl or 0.9,
                fd=vendor.fd or 1.0,
                xt=vendor.xt or self.inputs["gas_xt"].get(),
                pipe_inlet_diameter_mm=self.inputs["gas_pipe_in_mm"].get(),
                pipe_outlet_diameter_mm=self.inputs["gas_pipe_out_mm"].get(),
            ),
            valve_series=list(vendor.sizes),
            valve_meta=self._vendor_meta_for_service(vendor, "gas"),
            design_margin_pct=self.design_margin.get(),
            flow_characteristic=self.flow_characteristic.get(),
        )
        fluid_summary = {
            "Mixture": self.inputs["gas_composition"].get(),
            "Average MW": self._get_display_value(self.inputs["gas_mw"]),
            "Z": self.z_calculated_display.get(),
            "k = Cp/Cv": self.k_calculated_display.get(),
            "Viscosity [Pa.s]": self.viscosity_calculated_display.get(),
        }
        return result, fluid_summary

    def _calc_steam(self, vendor):
        p1 = pressure_to_bar_a(self.inputs["steam_p1"].get(), self.steam_pres_unit.get())
        p2 = pressure_to_bar_a(self.inputs["steam_p2"].get(), self.steam_pres_unit.get())
        temp_c = temperature_to_c(self.inputs["steam_temp_c"].get(), self.steam_temp_unit.get())
        try:
            from fluid_properties import evaluate_steam_state

            steam_eval = evaluate_steam_state(p1, temp_c)
            props = get_pure_fluid_state("Water", p1, temp_c)
            gamma = props["specific_heat_ratio"]
            z_value = props["z"]
            self.steam_k_display.set(f"{gamma:.5f}")
            self.steam_z_display.set(f"{z_value:.5f}")
            self.steam_status_text.set(f"{steam_eval['phase_label']} (Tsat={steam_eval['t_sat_c']:.1f} \u00b0C)")
        except Exception as exc:
            gamma = 1.30
            z_value = 1.0
            self.steam_k_display.set("1.30")
            self.steam_z_display.set("1.00")
            self.steam_status_text.set(f"Steam ozellikleri okunamadi: {exc}")

        result = size_steam_valve(
            SteamSizingInput(
                flow_kg_h=steam_flow_to_kgh(self.inputs["steam_flow_kgh"].get(), self.steam_flow_unit.get()),
                inlet_pressure_bar_a=p1,
                outlet_pressure_bar_a=p2,
                temperature_c=temp_c,
                specific_heat_ratio=gamma,
                z=z_value,
                xt=vendor.xt or 0.72,
                fl=vendor.fl or 0.9,
                fd=vendor.fd or 1.0,
            ),
            valve_series=list(vendor.sizes),
            valve_meta=self._vendor_meta_for_service(vendor, "steam"),
            design_margin_pct=self.design_margin.get(),
            flow_characteristic=self.flow_characteristic.get(),
        )
        fluid_summary = {
            "Reference fluid": "Water/Steam",
            "k = Cp/Cv": f"{gamma:.6f}",
            "Z": f"{z_value:.6f}",
        }
        return result, fluid_summary

    def _calculate(self, show_errors: bool = True) -> None:
        self.last_result = None
        self.last_fluid_summary = None
        vendor = get_vendor_definition(self.vendor_key.get())

        dispatch = {"liquid": self._calc_liquid, "gas": self._calc_gas, "steam": self._calc_steam}
        try:
            svc = self.service_type.get()
            calc_fn = dispatch[svc]
            result, fluid_summary = calc_fn(vendor)
        except KeyError:
            if show_errors:
                messagebox.showerror("Hata", f"Bilinmeyen servis tipi: {svc}")
            return
        except Exception as exc:
            if show_errors:
                messagebox.showerror("Hata", str(exc))
            return

        self.last_result = result
        self.last_fluid_summary = fluid_summary
        if show_errors:
            # Explicit "Hesapla" click only (live updates pass show_errors=False)
            entry = {
                "service": result["service"],
                "p1": round(float(result.get("p1", 0.0)), 3),
                "p2": round(float(result.get("p2", 0.0)), 3),
                "flow": round(float(result.get("flow", 0.0)), 3),
                "required_cv": float(result["required_cv"]),
                "rated_cv": float(result["rated_cv"]),
                "valve_dn_mm": int(result["valve_dn_mm"]),
                "valve_inch": str(result["valve_inch"]),
                "opening_percent": round(float(result["opening_percent"]), 1),
                "is_choked": bool(result["is_choked"]),
            }
            if entry not in self._result_history:
                self._result_history = [entry, *self._result_history][:3]
        char_name = self.flow_characteristic.get()
        op_analysis = evaluate_operating_point(
            required_cv=result["required_cv"],
            rated_cv=result["rated_cv"],
            characteristic=char_name,
        )
        lines = [
            f"Servis                  : {result['service']}",
            f"Gerekli Cv              : {result['required_cv']:.3f}",
            f"Gerekli Kv              : {result['required_kv']:.3f}",
            f"Secilen vana            : DN{result['valve_dn_mm']} ({result['valve_inch']})",
            f"Rated Cv                : {result['rated_cv']:.3f}",
            f"Rated Kv                : {result['rated_kv']:.3f}",
            f"Basinc dusumu [bar]     : {result['delta_p_bar']:.3f}",
            f"Bogulma durumu          : {'Evet' if result['is_choked'] else 'Hayir'}",
            f"Tasarim acikligi [%]    : {result['opening_percent']:.1f} (karakteristik: {char_name})",
            f"Kontrol Bolgesi         : {op_analysis.controllability_zone} (Kazanc: {op_analysis.point_gain:.2f})",
            f"Tasarim marji [%]       : {result['design_margin_pct']:.1f}",
            f"Cv orani (marjli/rated) : {result['cv_ratio']:.3f}",
        ]

        if result["service"] == "liquid":
            lines.extend([
                f"Efektif dP [bar]        : {result['effective_delta_p_bar']:.3f}",
                f"Bogulma dP siniri [bar] : {result['dp_choked_bar']:.3f}",
                f"Ozgul agirlik           : {result['specific_gravity']:.4f}",
                f"Pv cikis marji [bar]    : {result['outlet_margin_to_vapor_bar']:.3f}",
                f"Akis rejimi            : {result['flow_regime']}",
                f"Cavitasyon indeksi      : {result['cavitation_index']:.4f}",
            ])
        elif result["service"] == "gas":
            gas_type = self.inputs["gas_composition"].get()
            lines.extend([
                f"Gaz Tipi                : {gas_type}",
                f"Z (Hesaplanan)          : {self.z_calculated_display.get()}",
                f"k = Cp/Cv (Hesaplanan)  : {self.k_calculated_display.get()}",
                f"Viskozite [Pa.s]        : {self.viscosity_calculated_display.get()}",
                f"x = dP/P1               : {result['pressure_drop_ratio_x']:.4f}",
                f"Efektif x               : {result['effective_x']:.4f}",
                f"Expansion factor Y      : {result['expansion_factor_y']:.4f}",
                f"Gas specific gravity    : {result['gas_specific_gravity']:.4f}",
            ])
        else:  # steam
            lines.extend([
                f"k = Cp/Cv               : {self.steam_k_display.get()}",
                f"Z                       : {self.steam_z_display.get()}",
                f"x = dP/P1               : {result['pressure_drop_ratio_x']:.4f}",
                f"Efektif x               : {result['effective_x']:.4f}",
                f"Expansion factor Y      : {result['expansion_factor_y']:.4f}",
            ])

        lines.append("")
        lines.append(f"Vendor / Trim           : {vendor.vendor} / {vendor.style}")

        if result.get("noise_db") is not None:
            lines.append(f"Tahmini gurultu [dB(A)] : {result['noise_db']:.1f} (IEC 60534-8, tahmini)")

        velocity = result.get("velocity")
        if velocity:
            lines.append(f"Cikis hizi [m/s]        : {velocity['pipe_out_m_s']:.2f}")
            if "mach_outlet" in velocity:
                lines.append(f"Cikis Mach              : {velocity['mach_outlet']:.3f}")
            if "two_phase_out_m_s" in velocity:
                lines.append(f"Iki fazli hiz [m/s]     : {velocity['two_phase_out_m_s']:.2f} (API14E limit {velocity['api_14e_limit_m_s']:.2f})")

        trim_guidance = result.get("trim_guidance")
        if trim_guidance:
            lines.append("")
            lines.append("Trim onerileri:")
            for item in trim_guidance:
                lines.append(f"  - {item}")

        thrust = result.get("actuator_thrust_n")
        act_sel = result.get("actuator_selection")
        if act_sel and isinstance(act_sel, dict) and act_sel.get("model"):
            thrust_val = thrust.get("total_n", 0.0) if isinstance(thrust, dict) else (thrust or 0.0)
            lines.append(f"Tahmini akt. kuvveti [N]: {thrust_val:.1f}")
            margin = act_sel.get("thrust_margin_pct", 0.0)
            stroke_status = "Yeterli" if act_sel.get("stroke_ok") else "Yetersiz"
            lines.append(f"Onerilen aktorator     : {act_sel['model']} (+%{margin:.0f} marj, strok: {stroke_status})")
        spec = result.get("valve_spec")
        if spec:
            lines.append("")
            lines.append("Vana Spesifikasyonu:")
            lines.append(f"  Onerilen ANSI sinifi  : {spec.get('pressure_class_recommended', '-')}")
            if "derated_mawp_bar" in spec:
                t_sp = spec.get("temperature_c", 20.0)
                mat_grp = spec.get("material_group", "WCB")
                lines.append(f"  ASME B16.34 MAWP      : {spec['derated_mawp_bar']:.1f} bar @ {t_sp:.1f} \u00b0C ({mat_grp})")
            lines.append(f"  Onerilen sizdirmazlik : {spec.get('leakage_class_recommended', '-')}")
            if "allowable_leakage" in spec and isinstance(spec["allowable_leakage"], dict):
                al = spec["allowable_leakage"]
                lines.append(f"  Izin verilen sizinti  : {al.get('max_rate', 0.0):.4f} {al.get('rate_unit', '')}")
            lines.append(f"  Onerilen fail-safe    : {spec.get('fail_safe_recommended', '-')}")

        if op_analysis.warnings:
            lines.append("")
            lines.append("Kontrol Edilebilirlik:")
            for w in op_analysis.warnings:
                lines.append(f"  [!] {w}")

        if result.get("warning"):
            lines.extend(["", f"Uyari: {result['warning']}"])

        self.result_box.delete("1.0", tk.END)
        self.result_box.insert("1.0", "\n".join(lines))

    def _show_unit_converter(self) -> None:
        """Open a unit converter dialog backed by units.convert_unit."""
        win = tk.Toplevel(self.root)
        win.title("Birim Dönüştürücü")
        win.transient(self.root)
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)

        kind_label = tk.StringVar(value=UNIT_KIND_LABELS["temperature"])
        from_unit = tk.StringVar()
        to_unit = tk.StringVar()
        value_var = tk.StringVar(value="1")
        density_var = tk.StringVar(value="998")
        pressure_var = tk.StringVar(value="1.01325")
        temperature_var = tk.StringVar(value="15")
        z_var = tk.StringVar(value="1")
        result_var = tk.StringVar(value="--")
        status_var = tk.StringVar(value="")

        ttk.Label(frame, text="Tür:").grid(row=0, column=0, sticky="w", pady=4)
        kind_combo = ttk.Combobox(
            frame, textvariable=kind_label, values=list(UNIT_KIND_LABELS.values()), state="readonly", width=16
        )
        kind_combo.grid(row=0, column=1, columnspan=3, sticky="ew", pady=4)

        ttk.Label(frame, text="Değer:").grid(row=1, column=0, sticky="w", pady=4)
        value_entry = ttk.Entry(frame, textvariable=value_var, width=16)
        value_entry.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Sonuç:").grid(row=1, column=2, sticky="e", padx=(12, 4), pady=4)
        ttk.Label(frame, textvariable=result_var, font=("Segoe UI Semibold", 11)).grid(row=1, column=3, sticky="w", pady=4)

        ttk.Label(frame, text="Kaynak:").grid(row=2, column=0, sticky="w", pady=4)
        from_combo = ttk.Combobox(frame, textvariable=from_unit, state="readonly", width=16)
        from_combo.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Hedef:").grid(row=2, column=2, sticky="e", padx=(12, 4), pady=4)
        to_combo = ttk.Combobox(frame, textvariable=to_unit, state="readonly", width=16)
        to_combo.grid(row=2, column=3, sticky="ew", pady=4)

        optional = ttk.Frame(frame)
        optional.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        density_label = ttk.Label(optional, text="Yoğunluk [kg/m³]")
        density_entry = ttk.Entry(optional, textvariable=density_var, width=10)
        pressure_label = ttk.Label(optional, text="P [bar(a)]")
        pressure_entry = ttk.Entry(optional, textvariable=pressure_var, width=10)
        temperature_label = ttk.Label(optional, text="T [°C]")
        temperature_entry = ttk.Entry(optional, textvariable=temperature_var, width=10)
        z_label = ttk.Label(optional, text="Z")
        z_entry = ttk.Entry(optional, textvariable=z_var, width=6)
        ttk.Label(frame, textvariable=status_var, foreground="#b91c1c").grid(
            row=4, column=0, columnspan=4, sticky="w"
        )

        def current_kind() -> str:
            return next(k for k, v in UNIT_KIND_LABELS.items() if v == kind_label.get())

        def refresh_units(*_args) -> None:
            kind = current_kind()
            units = UNIT_MAPS[kind]
            labels = list(units.values())
            from_combo.configure(values=labels)
            to_combo.configure(values=labels)
            from_unit.set(labels[0])
            to_unit.set(labels[1] if len(labels) > 1 else labels[0])
            show_density = kind in {"liquid_flow", "gas_flow"}
            show_gas = kind == "gas_flow"
            for widget, visible, col in (
                (density_label, show_density, 0),
                (density_entry, show_density, 1),
                (pressure_label, show_gas, 2),
                (pressure_entry, show_gas, 3),
                (temperature_label, show_gas, 4),
                (temperature_entry, show_gas, 5),
                (z_label, show_gas, 6),
                (z_entry, show_gas, 7),
            ):
                if visible:
                    widget.grid(row=0, column=col, sticky="w" if col % 2 == 0 else "ew", padx=(0, 6), pady=2)
                else:
                    widget.grid_remove()
            convert()

        def convert(*_args) -> None:
            try:
                kind = current_kind()
                units = UNIT_MAPS[kind]
                from_key = next(k for k, v in units.items() if v == from_unit.get())
                to_key = next(k for k, v in units.items() if v == to_unit.get())
                kwargs: dict[str, float] = {}
                if kind in {"liquid_flow", "gas_flow"}:
                    kwargs["density_kg_m3"] = float(density_var.get())
                if kind == "gas_flow":
                    kwargs["pressure_bar_a"] = float(pressure_var.get())
                    kwargs["temperature_c"] = float(temperature_var.get())
                    kwargs["z"] = float(z_var.get())
                converted = convert_unit(kind, float(value_var.get()), from_key, to_key, **kwargs)
            except (ValueError, StopIteration) as exc:
                result_var.set("--")
                status_var.set(str(exc))
            else:
                result_var.set(f"{converted:.6g} {units[to_key]}")
                status_var.set("")

        kind_combo.bind("<<ComboboxSelected>>", refresh_units)
        from_combo.bind("<<ComboboxSelected>>", convert)
        to_combo.bind("<<ComboboxSelected>>", convert)
        for entry in (value_entry, density_entry, pressure_entry, temperature_entry, z_entry):
            entry.bind("<KeyRelease>", convert)
        ttk.Button(frame, text="Kapat", command=win.destroy).grid(row=5, column=3, sticky="e", pady=(8, 0))
        refresh_units()

    def _show_history_dialog(self) -> None:
        """Show a comparison table of the last few explicit calculations."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Onceki Hesaplamalar (Karsilastirma)")
        dlg.geometry("980x260")
        dlg.transient(self.root)
        if not self._result_history:
            ttk.Label(dlg, text="Henuz hesaplama gecmisi yok. 'Hesapla' butonuna basin.", padding=20).pack()
            return
        columns = ("no", "service", "p1", "p2", "flow", "required_cv", "rated_cv", "valve", "opening", "status")
        tree = ttk.Treeview(dlg, columns=columns, show="headings", height=min(len(self._result_history), 6))
        headings = {
            "no": "#", "service": "Servis", "p1": "P1 [bar]", "p2": "P2 [bar]", "flow": "Debi",
            "required_cv": "Gerekli Cv", "rated_cv": "Rated Cv",
            "valve": "Vana", "opening": "Aciklik %", "status": "Durum",
        }
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=95, anchor="center")
        for i, h in enumerate(self._result_history):
            tree.insert("", tk.END, values=(
                i + 1, h["service"], h.get("p1", "-"), h.get("p2", "-"), h.get("flow", "-"),
                f"{h['required_cv']:.3f}", f"{h['rated_cv']:.3f}",
                f"DN{h['valve_dn_mm']} / {h['valve_inch']}", f"{h['opening_percent']:.1f}",
                "BOGULMUS" if h["is_choked"] else "Normal",
            ))
        tree.pack(fill="both", expand=True, padx=12, pady=12)

    def _open_thermal_expansion_dialog(self) -> None:
        from thermal_expansion import (
            get_material_label,
            get_material_options,
            pipe_linear_expansion,
            pipe_thermal_stress,
        )

        dlg = tk.Toplevel(self.root)
        dlg.title("Termal Genlesme (Boru Hatti)")
        dlg.geometry("480x380")
        dlg.resizable(False, False)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Boru Malzemesi:").grid(row=0, column=0, sticky="w", pady=4)
        mat_options = get_material_options()
        mat_labels = [get_material_label(k) for k in mat_options]
        mat_var = tk.StringVar(value=mat_labels[0])
        mat_combo = ttk.Combobox(frame, values=mat_labels, textvariable=mat_var, state="readonly", width=28)
        mat_combo.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Boru Uzunlugu [m]:").grid(row=1, column=0, sticky="w", pady=4)
        len_var = tk.DoubleVar(value=10.0)
        ttk.Entry(frame, textvariable=len_var).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Montaj Sicakligi [°C]:").grid(row=2, column=0, sticky="w", pady=4)
        t1_var = tk.DoubleVar(value=10.0)
        ttk.Entry(frame, textvariable=t1_var).grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Isletme Sicakligi [°C]:").grid(row=3, column=0, sticky="w", pady=4)
        t2_var = tk.DoubleVar(value=90.0)
        ttk.Entry(frame, textvariable=t2_var).grid(row=3, column=1, sticky="ew", pady=4)

        res_frame = ttk.LabelFrame(frame, text="Sonuclar", padding=10)
        res_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 8))

        res_text = tk.StringVar(value="Hesaplamak icin asagidaki butona basin.")
        ttk.Label(res_frame, textvariable=res_text, font=("Consolas", 10), justify="left").pack(anchor="w")

        def _calc() -> None:
            try:
                selected_label = mat_var.get()
                mat_key = mat_options[mat_labels.index(selected_label)]
                length_m = len_var.get()
                t1 = t1_var.get()
                t2 = t2_var.get()
                delta_t = t2 - t1
                exp_mm = pipe_linear_expansion(length_m, delta_t, mat_key)
                stress_mpa = pipe_thermal_stress(delta_t, mat_key)
                res_text.set(
                    f"Sicaklik Farki (dT) : {delta_t:.1f} °C\n"
                    f"Boru Uzamasi       : {exp_mm:.2f} mm\n"
                    f"Termal Gerilme     : {stress_mpa:.1f} MPa"
                )
            except Exception as exc:
                res_text.set(f"Hata: {exc}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=6)
        ttk.Button(btn_frame, text="Hesapla", command=_calc).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=4)

    def _open_joule_thomson_dialog(self) -> None:
        from joule_thomson import calc_joule_thomson_drop

        dlg = tk.Toplevel(self.root)
        dlg.title("Joule-Thomson ve Gaz Hidrat Analizi")
        dlg.geometry("520x460")
        dlg.resizable(False, False)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Gaz Tipi:").grid(row=0, column=0, sticky="w", pady=4)
        gas_var = tk.StringVar(value="Methane")
        ttk.Combobox(
            frame,
            values=["Methane", "NaturalGas", "Nitrogen", "CarbonDioxide", "Hydrogen"],
            textvariable=gas_var,
            state="readonly",
            width=22,
        ).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Giris Basinci P1 [bar]:").grid(row=1, column=0, sticky="w", pady=4)
        p1_val = float(self.inputs["gas_p1"].get() if self.service_type.get() == "gas" else 50.0)
        p1_var = tk.DoubleVar(value=p1_val)
        ttk.Entry(frame, textvariable=p1_var).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Cikis Basinci P2 [bar]:").grid(row=2, column=0, sticky="w", pady=4)
        p2_val = float(self.inputs["gas_p2"].get() if self.service_type.get() == "gas" else 10.0)
        p2_var = tk.DoubleVar(value=p2_val)
        ttk.Entry(frame, textvariable=p2_var).grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Giris Sicakligi T1 [\u00b0C]:").grid(row=3, column=0, sticky="w", pady=4)
        t1_val = float(self.inputs["gas_temp_c"].get() if self.service_type.get() == "gas" else 20.0)
        t1_var = tk.DoubleVar(value=t1_val)
        ttk.Entry(frame, textvariable=t1_var).grid(row=3, column=1, sticky="ew", pady=4)

        res_frame = ttk.LabelFrame(frame, text="Sonuclar", padding=10)
        res_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 8))

        res_text = tk.StringVar(value="Hesaplamak icin asagidaki butona basin.")
        ttk.Label(res_frame, textvariable=res_text, font=("Consolas", 10), justify="left").pack(anchor="w")

        def _calc_jt() -> None:
            try:
                p1 = p1_var.get()
                p2 = p2_var.get()
                t1 = t1_var.get()
                res = calc_joule_thomson_drop(gas_var.get(), p1, p2, t1)
                lines = [
                    f"Cikis Sicakligi (T2) : {res.t2_c:.1f} \u00b0C",
                    f"Sicaklik Dususu (dT): {res.delta_t_c:.1f} \u00b0C",
                    f"J-T Katsayisi (mu)  : {res.mu_jt_c_per_bar:.3f} \u00b0C/bar",
                    f"Hidrat Sicakligi    : {res.t_hydrate_c:.1f} \u00b0C",
                    f"Hidrat Tehlikesi    : {'VAR (TEHLIKE!)' if res.hydrate_risk else 'YOK (Guvenli)'}",
                    f"Donma Tehlikesi     : {'VAR (Buzlanma)' if res.freezing_risk else 'YOK'}",
                    f"Min On Isitma (T)   : {res.t_preheat_min_c:.1f} \u00b0C",
                ]
                res_text.set("\n".join(lines))
            except Exception as exc:
                res_text.set(f"Hata: {exc}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=6)
        ttk.Button(btn_frame, text="Hesapla", command=_calc_jt).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=4)

    def _open_multicase_dialog(self) -> None:
        from multi_case import size_multicase

        dlg = tk.Toplevel(self.root)
        dlg.title("Coklu Calisma Durumu (Multi-Case Sizing: Min / Normal / Max)")
        dlg.geometry("700x580")
        dlg.resizable(True, True)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill="both", expand=True)

        cur_service = self.service_type.get()
        ttk.Label(
            frame,
            text=f"Aktif Servis: {cur_service.upper()}",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        flow_key = "liquid_flow_m3h" if cur_service == "liquid" else ("gas_flow_nm3h" if cur_service == "gas" else "steam_flow_kgh")
        p1_key = f"{cur_service}_p1"
        p2_key = f"{cur_service}_p2"
        flow_units = self._flow_map_for(cur_service)
        flow_unit = getattr(self, f"{cur_service}_flow_unit").get()
        pres_unit = getattr(self, f"{cur_service}_pres_unit").get()
        temp_unit = getattr(self, f"{cur_service}_temp_unit").get()
        flow_label = flow_units[flow_unit]
        pres_label = PRESSURE_UNITS[pres_unit]

        base_flow = float(self.inputs[flow_key].get())
        base_p1 = float(self.inputs[p1_key].get())
        base_p2 = float(self.inputs[p2_key].get())

        ttk.Label(frame, text="Vaka", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=2, padx=4)
        ttk.Label(frame, text=f"Debi [{flow_label}]", font=("Segoe UI", 9, "bold")).grid(row=1, column=1, sticky="w", pady=2, padx=4)
        ttk.Label(frame, text=f"P1 [{pres_label}]", font=("Segoe UI", 9, "bold")).grid(row=1, column=2, sticky="w", pady=2, padx=4)
        ttk.Label(frame, text=f"P2 [{pres_label}]", font=("Segoe UI", 9, "bold")).grid(row=1, column=3, sticky="w", pady=2, padx=4)

        ttk.Label(frame, text="Min:").grid(row=2, column=0, sticky="w", pady=2, padx=4)
        min_q_var = tk.DoubleVar(value=max(base_flow * 0.4, 0.1))
        ttk.Entry(frame, textvariable=min_q_var, width=12).grid(row=2, column=1, sticky="w", pady=2, padx=4)
        min_p1_var = tk.DoubleVar(value=base_p1)
        ttk.Entry(frame, textvariable=min_p1_var, width=10).grid(row=2, column=2, sticky="w", pady=2, padx=4)
        min_p2_var = tk.DoubleVar(value=base_p2)
        ttk.Entry(frame, textvariable=min_p2_var, width=10).grid(row=2, column=3, sticky="w", pady=2, padx=4)

        ttk.Label(frame, text="Normal:").grid(row=3, column=0, sticky="w", pady=2, padx=4)
        norm_q_var = tk.DoubleVar(value=max(base_flow, 0.1))
        ttk.Entry(frame, textvariable=norm_q_var, width=12).grid(row=3, column=1, sticky="w", pady=2, padx=4)
        norm_p1_var = tk.DoubleVar(value=base_p1)
        ttk.Entry(frame, textvariable=norm_p1_var, width=10).grid(row=3, column=2, sticky="w", pady=2, padx=4)
        norm_p2_var = tk.DoubleVar(value=base_p2)
        ttk.Entry(frame, textvariable=norm_p2_var, width=10).grid(row=3, column=3, sticky="w", pady=2, padx=4)

        ttk.Label(frame, text="Max:").grid(row=4, column=0, sticky="w", pady=2, padx=4)
        max_q_var = tk.DoubleVar(value=max(base_flow * 1.3, 0.1))
        ttk.Entry(frame, textvariable=max_q_var, width=12).grid(row=4, column=1, sticky="w", pady=2, padx=4)
        max_p1_var = tk.DoubleVar(value=max(base_p1 * 0.95, 0.1))
        ttk.Entry(frame, textvariable=max_p1_var, width=10).grid(row=4, column=2, sticky="w", pady=2, padx=4)
        max_p2_var = tk.DoubleVar(value=base_p2)
        ttk.Entry(frame, textvariable=max_p2_var, width=10).grid(row=4, column=3, sticky="w", pady=2, padx=4)

        res_box = tk.Text(frame, height=16, font=("Consolas", 9), wrap="none")
        res_box.grid(row=5, column=0, columnspan=4, sticky="nsew", pady=10)
        frame.rowconfigure(5, weight=1)
        frame.columnconfigure(1, weight=1)

        def _calc_mc() -> None:
            try:
                temp_c = temperature_to_c(float(self.inputs[f"{cur_service}_temp_c"].get()), temp_unit)
                cases = [
                    self._multicase_operating_case(
                        cur_service, "Min", min_q_var.get(), min_p1_var.get(), min_p2_var.get(), flow_unit, pres_unit, temp_c
                    ),
                    self._multicase_operating_case(
                        cur_service, "Normal", norm_q_var.get(), norm_p1_var.get(), norm_p2_var.get(), flow_unit, pres_unit, temp_c
                    ),
                    self._multicase_operating_case(
                        cur_service, "Max", max_q_var.get(), max_p1_var.get(), max_p2_var.get(), flow_unit, pres_unit, temp_c
                    ),
                ]
                fluid_data: dict[str, Any] = {}
                if cur_service == "liquid":
                    pressures = self._liquid_pressures_bar_a()
                    fluid_data = {
                        "density_kg_m3": self.inputs["liquid_density"].get(),
                        "vapor_pressure_bar_a": pressures["liquid_pv"],
                        "critical_pressure_bar_a": pressures["liquid_pc"],
                        "viscosity_pa_s": self.inputs["liquid_mu"].get(),
                    }
                elif cur_service == "gas":
                    try:
                        k_val = float(self.k_calculated_display.get())
                    except (ValueError, TypeError):
                        k_val = 1.30
                    try:
                        mu_val = float(self.viscosity_calculated_display.get())
                    except (ValueError, TypeError):
                        mu_val = 1e-5
                    try:
                        z_val = float(self.z_calculated_display.get())
                    except (ValueError, TypeError):
                        z_val = 1.0
                    try:
                        mw_val = float(self.inputs["gas_mw"].get())
                    except (ValueError, TypeError):
                        mw_val = 28.96
                    fluid_data = {
                        "molecular_weight": mw_val,
                        "specific_heat_ratio": k_val,
                        "viscosity_pa_s": mu_val,
                        "z": z_val,
                    }
                else:
                    try:
                        k_val = float(self.steam_k_display.get())
                    except (ValueError, TypeError):
                        k_val = 1.30
                    try:
                        z_val = float(self.steam_z_display.get())
                    except (ValueError, TypeError):
                        z_val = 1.0
                    fluid_data = {"specific_heat_ratio": k_val, "z": z_val}

                vendor = get_vendor_definition(self.vendor_key.get())
                fluid_data["fl"] = vendor.fl or 0.9
                fluid_data["xt"] = vendor.xt or 0.7
                fluid_data["fd"] = vendor.fd or 1.0

                mc_res = size_multicase(
                    cur_service,
                    cases,
                    fluid_data,
                    valve_series=list(vendor.sizes),
                    flow_characteristic=self.flow_characteristic.get(),
                )
                self.last_multicase_result = mc_res
                lines = [
                    f"Ozet: {mc_res.overall_summary}",
                    f"Turndown Orani (Qmax/Qmin): {mc_res.turndown_ratio:.1f}:1",
                    "-" * 70,
                    f"{'Vana':<12} {'Rated Cv':<10} {'Min %':<10} {'Norm %':<10} {'Max %':<10} {'Durum'}",
                    "-" * 70,
                ]
                for c in mc_res.candidates:
                    flag = " [*]" if c.is_recommended else ""
                    lines.append(
                        f"DN{c.valve.dn_mm:<8} {c.valve.cv_rated:<10.1f} {c.opening_min_pct:<10.1f} "
                        f"{c.opening_norm_pct:<10.1f} {c.opening_max_pct:<10.1f} {c.status_label}{flag}"
                    )
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", "\n".join(lines))
            except Exception as exc:
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", f"Hata: {exc}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=4, pady=6)
        ttk.Button(btn_frame, text="Hesapla", command=_calc_mc).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=4)

    def _open_cavitation_dialog(self) -> None:
        from trim_guidance import design_multistage_cavitation_trim, evaluate_cavitation_severity

        dlg = tk.Toplevel(self.root)
        dlg.title("Kavitasyon ve Cok Kademeli Trim Tasarimi (ISA-RP75.23 / IEC 60534)")
        dlg.geometry("780x620")
        dlg.resizable(True, True)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill="both", expand=True)

        pressures = self._liquid_pressures_bar_a()
        p1_init = pressures["liquid_p1"]
        p2_init = pressures["liquid_p2"]
        pv_init = pressures["liquid_pv"]
        cv_init = 25.0
        if hasattr(self, "last_result") and self.last_result:
            cv_init = float(self.last_result.get("required_cv", 25.0))

        ttk.Label(frame, text="Giris Basinci P1 [bar(a)]:").grid(row=0, column=0, sticky="w", pady=3)
        p1_var = tk.DoubleVar(value=round(p1_init, 3))
        ttk.Entry(frame, textvariable=p1_var, width=16).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Cikis Basinci P2 [bar(a)]:").grid(row=1, column=0, sticky="w", pady=3)
        p2_var = tk.DoubleVar(value=round(p2_init, 3))
        ttk.Entry(frame, textvariable=p2_var, width=16).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Buharlasma Basinci Pv [bar(a)]:").grid(row=2, column=0, sticky="w", pady=3)
        pv_var = tk.DoubleVar(value=round(pv_init, 4))
        ttk.Entry(frame, textvariable=pv_var, width=16).grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Tasarim Cv:").grid(row=3, column=0, sticky="w", pady=3)
        cv_var = tk.DoubleVar(value=round(cv_init, 2))
        ttk.Entry(frame, textvariable=cv_var, width=16).grid(row=3, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Kademe Secimi:").grid(row=4, column=0, sticky="w", pady=3)
        stage_mode_var = tk.StringVar(value="Otomatik (Minimum Guvenli)")
        ttk.Combobox(
            frame,
            textvariable=stage_mode_var,
            values=("Otomatik (Minimum Guvenli)", "1 Kademe", "2 Kademe", "3 Kademe", "4 Kademe", "6 Kademe"),
            state="readonly",
            width=26,
        ).grid(row=4, column=1, sticky="w", pady=3)

        res_box = tk.Text(frame, height=18, width=88, font=("Consolas", 10))
        res_box.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(10, 8))
        frame.rowconfigure(5, weight=1)
        frame.columnconfigure(1, weight=1)

        def _calc_cav() -> None:
            try:
                p1 = p1_var.get()
                p2 = p2_var.get()
                pv = pv_var.get()
                cv = cv_var.get()
                dp = max(p1 - p2, 0.001)
                sigma = (p1 - pv) / dp if dp > 0 else 999.0
                sev_res = evaluate_cavitation_severity(sigma, dp, p1, pv)

                stg_mode = stage_mode_var.get()
                req_stg = None
                if stg_mode != "Otomatik (Minimum Guvenli)":
                    req_stg = int(stg_mode.split()[0])

                m_res = design_multistage_cavitation_trim(
                    p1_bar_a=p1,
                    p2_bar_a=p2,
                    pv_bar_a=pv,
                    required_cv=cv,
                    requested_stages=req_stg,
                )

                cav_status = "ONLENDI (GUVENLI)" if m_res.is_cavitation_eliminated else "KAVITASYON RISKI MEVCUT"

                lines = [
                    "=" * 78,
                    "KAVITASYON & COK KADEMELI TRIM TASARIMI (ISA-RP75.23 / IEC 60534)",
                    "=" * 78,
                    f"Kavitasyon Indeksi (\u03c3)        : {sev_res.sigma:.3f}",
                    f"Siddet Rejimi                 : {sev_res.severity_level}",
                    f"Onerilen Trim Yapisi          : {m_res.trim_description}",
                    f"Kademe Sayisi                 : {m_res.stages_count} Kademe (Min Onerilen: {m_res.min_recommended_stages})",
                    f"Kavitasyon Durumu             : {cav_status}",
                    f"Gurultu Azaltma Tahmini       : -{m_res.noise_reduction_dba:.1f} dB(A)",
                    f"Kademe Basi Izin Verilen \u0394P   : {sev_res.max_allowable_dp_per_stage_bar:.1f} bar",
                    "-" * 78,
                    "KADEME BASINC VE AKIS PROFILI TABLOSU:",
                    f"{'Kademe':<8} {'P_in [bar]':<11} {'P_out [bar]':<12} {'ΔP [bar]':<9} "
                    f"{'P_vc [bar]':<11} {'Buhar Marji':<12} {'Kavitasyon':<11} {'Kademe Cv':<10}",
                    "-" * 78,
                ]
                for s in m_res.stages:
                    cav_flag = "EVET" if s.is_cavitating else "HAYIR"
                    lines.append(
                        f"Kademe {s.stage_number:<2} {s.inlet_pressure_bar_a:<11.2f} {s.outlet_pressure_bar_a:<12.2f} "
                        f"{s.delta_p_bar:<9.2f} {s.vena_contracta_pressure_bar_a:<11.2f} "
                        f"{s.margin_to_vapor_bar:<12.2f} {cav_flag:<11} {s.stage_cv:<10.2f}"
                    )
                lines.append("-" * 78)

                all_warnings = list(sev_res.warnings) + list(m_res.warnings)
                if all_warnings:
                    lines.append("UYARILAR:")
                    for w in all_warnings:
                        lines.append(f"  [!] {w}")
                    lines.append("-" * 78)

                all_notes = list(sev_res.engineering_notes) + list(m_res.engineering_notes)
                if all_notes:
                    lines.append("MUHENDISLIK NOTLARI:")
                    for n in all_notes:
                        lines.append(f"  * {n}")

                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", "\n".join(lines))
            except Exception as exc:
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", f"Hata: {exc}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=6)
        ttk.Button(btn_frame, text="Analiz Et", command=_calc_cav).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=4)
        _calc_cav()

    def _open_packing_dialog(self) -> None:
        from packing_emissions import recommend_packing_system

        dlg = tk.Toplevel(self.root)
        dlg.title("Salmastra ve Kacak Emisyon Analizi (ISO 15848-1 / API 641)")
        dlg.geometry("640x520")
        dlg.resizable(True, True)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill="both", expand=True)

        cur_service = self.service_type.get()
        p1_key = f"{cur_service}_p1"
        t_key = f"{cur_service}_temp_c"
        p_init = float(self.inputs.get(p1_key, tk.StringVar(value="10.0")).get())
        t_init = float(self.inputs.get(t_key, tk.StringVar(value="25.0")).get())

        ttk.Label(frame, text="Akiskan Tipi:").grid(row=0, column=0, sticky="w", pady=3)
        fluid_var = tk.StringVar(value="Su" if cur_service == "liquid" else ("Dogal Gaz" if cur_service == "gas" else "Buhar"))
        ttk.Entry(frame, textvariable=fluid_var, width=22).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Calisma Sicakligi [\u00b0C]:").grid(row=1, column=0, sticky="w", pady=3)
        temp_var = tk.DoubleVar(value=t_init)
        ttk.Entry(frame, textvariable=temp_var, width=16).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Giris Basinci [bar(a)]:").grid(row=2, column=0, sticky="w", pady=3)
        pres_var = tk.DoubleVar(value=p_init)
        ttk.Entry(frame, textvariable=pres_var, width=16).grid(row=2, column=1, sticky="w", pady=3)

        toxic_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Zehirli / Tehlikeli Akiskan (Lethal Service)", variable=toxic_var).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=3
        )

        sour_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Eksi Gaz / H2S Ortami (NACE MR0175)", variable=sour_var).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=3
        )

        res_box = tk.Text(frame, height=13, width=65, font=("Consolas", 10))
        res_box.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(8, 8))
        frame.rowconfigure(5, weight=1)
        frame.columnconfigure(1, weight=1)

        def _calc_pack() -> None:
            try:
                res = recommend_packing_system(
                    service=cur_service,
                    fluid_name=fluid_var.get(),
                    temperature_c=temp_var.get(),
                    pressure_bar_a=pres_var.get(),
                    is_toxic_or_lethal=toxic_var.get(),
                    is_sour_gas=sour_var.get(),
                )
                lines = [
                    "=" * 60,
                    "SALMASTRA VE KACAK EMISYON DEGERLENDIRMESI",
                    "=" * 60,
                    f"Onerilen Salmastra : {res.packing_type}",
                    f"Emisyon Sinifi     : {res.emission_class}",
                    f"Sizdirmazlik Siniri: < {res.leakage_tightness_ppmv:.0f} ppmv",
                    f"Yangin Emniyeti    : {'API 607 Yangina Dayanikli' if res.fire_safe else 'Standard'}",
                    f"NACE MR0175 Uyumu  : {'Uyumlu (HRC <= 22)' if res.nace_mr0175_compliant else 'Standart Malzeme'}",
                    f"Sicaklik Araligi   : {res.temperature_range_c[0]:.0f} \u00b0C ... {res.temperature_range_c[1]:.0f} \u00b0C",
                    "-" * 60,
                    f"Tasarim Notu: {res.description}",
                    "-" * 60,
                ]
                for r in res.recommendations:
                    lines.append(f"  * {r}")
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", "\n".join(lines))
            except Exception as exc:
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", f"Hata: {exc}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=6)
        ttk.Button(btn_frame, text="Degerlendir", command=_calc_pack).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=4)
        _calc_pack()

    def _open_isa20_dialog(self) -> None:
        if not hasattr(self, "last_result") or self.last_result is None:
            messagebox.showinfo("Bilgi", "Once ana ekranda vana boyutlandirma hesaplamasi yapin.")
            return

        from reporting import build_isa20_html_report, build_isa20_report

        dlg = tk.Toplevel(self.root)
        dlg.title("ISA Form 20 Kontrol Vanasi Sartnamesi (Datasheet)")
        dlg.geometry("760x620")
        dlg.resizable(True, True)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=14)
        frame.pack(fill="both", expand=True)

        service_map = {"liquid": "Liquid", "gas": "Gas", "steam": "Steam"}
        srv = service_map.get(self.service_type.get(), "Liquid")
        if self.service_type.get() == "liquid":
            fluid_str = self.liquid_preset_label.get() or "Water"
        elif self.service_type.get() == "gas":
            gas_comp = self.inputs.get("gas_composition")
            fluid_str = gas_comp.get() if gas_comp else "NaturalGas"
        else:
            fluid_str = "Steam"

        last_mc = getattr(self, "last_multicase_result", None)
        mc_cases = last_mc.to_isa20_process_cases() if last_mc else None
        md_text = build_isa20_report(
            self.last_result,
            tag="CV-101",
            service_desc=f"{srv} Control Valve",
            fluid_name=fluid_str,
            multicase_cases=mc_cases,
        )

        text_box = tk.Text(frame, wrap="word", font=("Consolas", 10))
        text_box.grid(row=0, column=0, columnspan=3, sticky="nsew", pady=(0, 10))
        text_box.insert("1.0", md_text)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        def _save_md() -> None:
            fp = filedialog.asksaveasfilename(
                defaultextension=".md",
                filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
                title="ISA-20 Datasheet Markdown Olarak Kaydet",
            )
            if fp:
                try:
                    with open(fp, "w", encoding="utf-8") as f:
                        f.write(md_text)
                    messagebox.showinfo("Basarili", f"Datasheet kaydedildi: {fp}")
                except Exception as e:
                    messagebox.showerror("Hata", f"Kaydedilemedi: {e}")

        def _save_html() -> None:
            fp = filedialog.asksaveasfilename(
                defaultextension=".html",
                filetypes=[("HTML / Excel", "*.html"), ("All files", "*.*")],
                title="ISA-20 Datasheet HTML Olarak Kaydet",
            )
            if fp:
                try:
                    html_content = build_isa20_html_report(
                        self.last_result,
                        tag="CV-101",
                        service_desc=f"{srv} Control Valve",
                        fluid_name=fluid_str,
                        multicase_cases=mc_cases,
                    )
                    with open(fp, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    messagebox.showinfo("Basarili", f"Datasheet kaydedildi: {fp}")
                except Exception as e:
                    messagebox.showerror("Hata", f"Kaydedilemedi: {e}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, columnspan=3, pady=4)
        ttk.Button(btn_frame, text="Markdown Kaydet (.md)", command=_save_md).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="HTML / Excel Kaydet (.html)", command=_save_html).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=6)

    def _export_isa20(self) -> None:
        self._open_isa20_dialog()

    def _open_safety_piping_dialog(self) -> None:
        from safety_piping import calc_wide_open_relief_capacity, check_erosional_velocity

        dlg = tk.Toplevel(self.root)
        dlg.title("Boru Guvenligi ve PSV Tahliye Debisi (API 14E / API 520)")
        dlg.geometry("680x560")
        dlg.resizable(True, True)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill="both", expand=True)

        cur_service = self.service_type.get()
        p1_val = float(self.inputs.get(f"{cur_service}_p1", tk.StringVar(value="10.0")).get())
        p2_val = float(self.inputs.get(f"{cur_service}_p2", tk.StringVar(value="5.0")).get())
        cv_val = float(self.last_result["rated_cv"]) if hasattr(self, "last_result") and self.last_result else 50.0

        ttk.Label(frame, text="Vana Rated Cv:").grid(row=0, column=0, sticky="w", pady=3)
        cv_var = tk.DoubleVar(value=cv_val)
        ttk.Entry(frame, textvariable=cv_var, width=14).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Giris Basinci P1 [bar(a)]:").grid(row=1, column=0, sticky="w", pady=3)
        p1_var = tk.DoubleVar(value=p1_val)
        ttk.Entry(frame, textvariable=p1_var, width=14).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="PSV Tahliye Basinci [bar(a)]:").grid(row=2, column=0, sticky="w", pady=3)
        prel_var = tk.DoubleVar(value=max(p2_val * 1.1, 1.0))
        ttk.Entry(frame, textvariable=prel_var, width=14).grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Boru Akis Hizi [m/s]:").grid(row=3, column=0, sticky="w", pady=3)
        vel_var = tk.DoubleVar(value=4.5)
        ttk.Entry(frame, textvariable=vel_var, width=14).grid(row=3, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Akiskan Yogunlugu [kg/m3]:").grid(row=4, column=0, sticky="w", pady=3)
        rho_var = tk.DoubleVar(value=1000.0 if cur_service == "liquid" else (15.0 if cur_service == "gas" else 5.0))
        ttk.Entry(frame, textvariable=rho_var, width=14).grid(row=4, column=1, sticky="w", pady=3)

        res_box = tk.Text(frame, height=14, width=70, font=("Consolas", 10))
        res_box.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(8, 8))
        frame.rowconfigure(5, weight=1)
        frame.columnconfigure(1, weight=1)

        def _calc_safety() -> None:
            try:
                cv = cv_var.get()
                p1 = p1_var.get()
                prel = prel_var.get()
                v = vel_var.get()
                rho = rho_var.get()

                eros = check_erosional_velocity(v, rho)
                fl_data = {"specific_gravity": 1.0, "molecular_weight": 28.96, "density_kg_m3": rho, "xt": 0.70}
                rel = calc_wide_open_relief_capacity(cur_service, cv, p1, prel, fl_data)

                lines = [
                    "=" * 65,
                    "BORU GUVENLIGI VE PSV TAHLIYE KAPASITESI (API 14E / API 520)",
                    "=" * 65,
                    f"Mevcut Boru Hizi             : {eros.actual_velocity_m_s:.2f} m/s",
                    f"API 14E Erozyonel Hiz Limiti : {eros.erosional_limit_m_s:.2f} m/s",
                    f"Erozyon Limiti Asildi mi?    : {'EVET (TEHLIKE!)' if eros.is_velocity_exceeded else 'HAYIR (Guvenli)'}",
                    f"Hiz Orani (v / ve)           : %{eros.velocity_ratio * 100.0:.1f}",
                ]
                if eros.min_recommended_pipe_dn_mm > 0:
                    lines.append(f"Onerilen Min Boru Capi       : DN{eros.min_recommended_pipe_dn_mm}")
                lines.extend([
                    "-" * 65,
                    f"PSV Ariza Tahliye Debisi     : {rel.wide_open_flow_rate:.1f} {rel.flow_unit}",
                    f"Akis Bogulmasi (Choking)     : {'EVET' if rel.is_choked else 'HAYIR'}",
                    "-" * 65,
                ])
                for w in eros.warnings:
                    lines.append(f"  [!] {w}")
                for sn in rel.safety_notes:
                    lines.append(f"  * {sn}")
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", "\n".join(lines))
            except Exception as exc:
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", f"Hata: {exc}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=4)
        ttk.Button(btn_frame, text="Hesapla", command=_calc_safety).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=4)
        _calc_safety()

    def _open_material_selection_dialog(self) -> None:
        from valve_selection import recommend_alloy_material, recommend_bonnet_type

        dlg = tk.Toplevel(self.root)
        dlg.title("Gelismis Malzeme ve Bonnet Secimi (ASME B31.3 / NACE / API 941)")
        dlg.geometry("680x520")
        dlg.resizable(True, True)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill="both", expand=True)

        cur_service = self.service_type.get()
        t_val = float(self.inputs.get(f"{cur_service}_temp_c", tk.StringVar(value="25.0")).get())

        ttk.Label(frame, text="Akiskan Adi:").grid(row=0, column=0, sticky="w", pady=3)
        fluid_var = tk.StringVar(value="Dogal Gaz" if cur_service == "gas" else ("Su" if cur_service == "liquid" else "Buhar"))
        ttk.Entry(frame, textvariable=fluid_var, width=22).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Calisma Sicakligi [\u00b0C]:").grid(row=1, column=0, sticky="w", pady=3)
        temp_var = tk.DoubleVar(value=t_val)
        ttk.Entry(frame, textvariable=temp_var, width=14).grid(row=1, column=1, sticky="w", pady=3)

        sour_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Eksi Gaz / H2S Ortami (NACE MR0175)", variable=sour_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=3
        )

        h2_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Hidrojen / Sentez Gazi (API 941 Nelson)", variable=h2_var).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=3
        )

        res_box = tk.Text(frame, height=14, width=70, font=("Consolas", 10))
        res_box.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(8, 8))
        frame.rowconfigure(4, weight=1)
        frame.columnconfigure(1, weight=1)

        def _calc_mat() -> None:
            try:
                t = temp_var.get()
                f_name = fluid_var.get()
                bonnet = recommend_bonnet_type(t, cur_service, f_name)
                alloy = recommend_alloy_material(cur_service, f_name, t, is_sour=sour_var.get(), is_h2=h2_var.get())

                lines = [
                    "=" * 65,
                    "MALZEME VE BONNET SPESIFIKASYONU",
                    "=" * 65,
                    f"Onerilen Bonnet Tipi : {bonnet}",
                    f"Govde Malzemesi      : {alloy.body_material}",
                    f"Trim Malzemesi       : {alloy.trim_material}",
                    f"Mil Malzemesi        : {alloy.stem_material}",
                    f"Tasarim Standardi    : {alloy.design_standard}",
                    f"NACE MR0175 Uyumu    : {'EVET' if alloy.nace_compliant else 'Standart'}",
                    f"Sicaklik Sinirlari   : {alloy.temperature_limits_c[0]:.0f} \u00b0C ... {alloy.temperature_limits_c[1]:.0f} \u00b0C",
                    "-" * 65,
                ]
                for r in alloy.recommendations:
                    lines.append(f"  * {r}")
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", "\n".join(lines))
            except Exception as exc:
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", f"Hata: {exc}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=4)
        ttk.Button(btn_frame, text="Degerlendir", command=_calc_mat).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=4)
        _calc_mat()

    def _open_characteristic_curve_dialog(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Vana Karakteristik Eğrisi ve Kontrol Analizi (IEC 60534-2-4)")
        dlg.geometry("760x600")
        dlg.resizable(True, True)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=14)
        frame.pack(fill="both", expand=True)

        init_rated = 50.0
        init_req = 25.0
        init_char = self.flow_characteristic.get()
        if hasattr(self, "last_result") and self.last_result:
            init_rated = float(self.last_result.get("rated_cv", 50.0))
            init_req = float(self.last_result.get("required_cv", 25.0))

        ttk.Label(frame, text="Rated Cv (Anma Kapasitesi):").grid(row=0, column=0, sticky="w", pady=4)
        rated_var = tk.DoubleVar(value=round(init_rated, 2))
        ttk.Entry(frame, textvariable=rated_var, width=16).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Gereken Tasarım Cv:").grid(row=1, column=0, sticky="w", pady=4)
        req_var = tk.DoubleVar(value=round(init_req, 2))
        ttk.Entry(frame, textvariable=req_var, width=16).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Karakteristik Tipi:").grid(row=2, column=0, sticky="w", pady=4)
        char_var = tk.StringVar(value=init_char)
        ttk.Combobox(
            frame,
            textvariable=char_var,
            values=("equal_percentage", "linear", "quick_opening"),
            state="readonly",
            width=18,
        ).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Rangeability (Kısılabilirlik R):").grid(row=3, column=0, sticky="w", pady=4)
        r_var = tk.DoubleVar(value=50.0)
        ttk.Entry(frame, textvariable=r_var, width=16).grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Vana Otoritesi PR (ΔPv/ΔPtot):").grid(row=4, column=0, sticky="w", pady=4)
        pr_var = tk.DoubleVar(value=0.50)
        ttk.Entry(frame, textvariable=pr_var, width=16).grid(row=4, column=1, sticky="w", pady=4)

        res_box = tk.Text(frame, height=20, width=82, font=("Consolas", 10))
        res_box.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(10, 8))
        frame.rowconfigure(5, weight=1)
        frame.columnconfigure(1, weight=1)

        def _calc() -> None:
            try:
                cv_r = rated_var.get()
                cv_req = req_var.get()
                c_type = char_var.get()
                r_val = r_var.get()
                pr_val = pr_var.get()
                curve = generate_characteristic_curve(
                    rated_cv=cv_r,
                    required_cv=cv_req,
                    characteristic=c_type,
                    rangeability=r_val,
                )
                inst = generate_installed_characteristic(
                    rated_cv=cv_r,
                    required_cv=cv_req,
                    characteristic=c_type,
                    valve_authority_pr=pr_val,
                    rangeability=r_val,
                )
                op = curve.operating_point
                lines = [
                    "=" * 78,
                    "VANA AKIS KARAKTERISTIK VE TESISAT KURULU KONTROL ANALIZI (IEC 60534-2-4)",
                    "=" * 78,
                    f"Karakteristik Tipi   : {op.characteristic.upper()}",
                    f"Rated Cv / Req Cv    : {op.rated_cv:.2f} / {op.required_cv:.2f} (Kapasite: %{op.relative_cv_pct:.1f})",
                    f"Rangeability (R)     : {curve.rangeability:.1f}:1",
                    f"Calisma Noktasi      : Aciklik %{op.opening_pct:.1f} | Inherent Kazanc: {op.point_gain:.2f}",
                    f"Kontrol Bolgesi      : {op.controllability_zone}",
                    "-" * 78,
                    "TESISAT KURULU (INSTALLED) KONTROL VE VANA OTORITESI:",
                    f"Vana Otoritesi (PR)  : {inst.valve_authority_pr:.2f} -> {inst.authority_assessment}",
                    f"Karakteristik Egilimi: {inst.distortion_trend}",
                    f"Dinamik Kazanc Orani : {inst.gain_ratio:.1f}:1 ({'Kararli <= 4:1' if inst.is_gain_linear else 'Dogrusal Degil > 4:1'})",
                    f"Calisma Noktasi Debi : %{inst.operating_installed_flow_pct:.1f} | Dinamik Kazanc dQ/dh: {inst.operating_installed_gain:.2f}",
                    "-" * 78,
                ]
                all_warnings = list(op.warnings) + list(inst.warnings)
                if all_warnings:
                    lines.append("UYARILAR VE TAVSIYELER:")
                    for w in all_warnings:
                        lines.append(f"  [!] {w}")
                    lines.append("-" * 78)
                else:
                    lines.append("  [OK] Calisma noktasi ve vana otoritesi ideal proses kontrol araligindadir.")
                    lines.append("-" * 78)

                lines.append(f"{'Aciklik':<10}{'Inh Cv':<12}{'Kurulu Q%':<14}{'Dinamik Kazanc':<18}{'Vana dP%':<12}")
                lines.append("-" * 66)
                for pt, ipt in zip(curve.points[::2], inst.points[::2], strict=False):
                    marker = " <== (Calisma)" if abs(pt.opening_pct - op.opening_pct) < 2.0 else ""
                    lines.append(
                        f"{pt.opening_pct:>6.1f}%    {pt.cv:>8.2f}    {ipt.installed_flow_pct:>8.1f}%     "
                        f"{ipt.installed_gain:>10.2f}        %{ipt.valve_dp_ratio * 100:>6.1f}{marker}"
                    )

                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", "\n".join(lines))
            except Exception as exc:
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", f"Hata olustu: {exc}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=4)
        ttk.Button(btn_frame, text="Hesapla ve Listele", command=_calc).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=4)
        _calc()

    def _open_actuator_dynamics_dialog(self) -> None:
        from actuator_sizing import analyze_actuator_dynamics, get_actuator_options

        dlg = tk.Toplevel(self.root)
        dlg.title("Aktuator Tepki Suresi ve Hava Tuketimi (ISA-75.25 / IEC 60534-6)")
        dlg.geometry("740x600")
        dlg.resizable(True, True)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill="both", expand=True)

        act_opts = get_actuator_options()
        def_act = "DA-150"
        if hasattr(self, "last_result") and self.last_result:
            act_sel = self.last_result.get("actuator_selection")
            if isinstance(act_sel, dict) and act_sel.get("model") in act_opts:
                def_act = act_sel["model"]

        ttk.Label(frame, text="Aktuator Modeli:").grid(row=0, column=0, sticky="w", pady=3)
        act_var = tk.StringVar(value=def_act)
        ttk.Combobox(frame, textvariable=act_var, values=act_opts, state="readonly", width=18).grid(
            row=0, column=1, sticky="w", pady=3
        )

        ttk.Label(frame, text="Besleme Basinci [bar(g)]:").grid(row=1, column=0, sticky="w", pady=3)
        psup_var = tk.DoubleVar(value=4.0)
        ttk.Entry(frame, textvariable=psup_var, width=16).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Konumlandirici Kapasitesi [Nm³/h]:").grid(row=2, column=0, sticky="w", pady=3)
        qpos_var = tk.DoubleVar(value=14.0)
        ttk.Entry(frame, textvariable=qpos_var, width=16).grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Hedef Strok Suresi [s]:").grid(row=3, column=0, sticky="w", pady=3)
        ttarg_var = tk.DoubleVar(value=2.0)
        ttk.Entry(frame, textvariable=ttarg_var, width=16).grid(row=3, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Modulasyon Cevrimi [cevrim/saat]:").grid(row=4, column=0, sticky="w", pady=3)
        cyc_var = tk.DoubleVar(value=60.0)
        ttk.Entry(frame, textvariable=cyc_var, width=16).grid(row=4, column=1, sticky="w", pady=3)

        res_box = tk.Text(frame, height=17, width=84, font=("Consolas", 10))
        res_box.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(10, 8))
        frame.rowconfigure(5, weight=1)
        frame.columnconfigure(1, weight=1)

        def _calc() -> None:
            try:
                model = act_var.get()
                p_sup = psup_var.get()
                q_pos = qpos_var.get()
                t_targ = ttarg_var.get()
                cycles = cyc_var.get()

                dyn = analyze_actuator_dynamics(
                    actuator_key=model,
                    supply_pressure_bar_g=p_sup,
                    positioner_flow_capacity_nm3h=q_pos,
                    target_stroke_time_sec=t_targ,
                    cycles_per_hour=cycles,
                )

                booster_status = "GEREKLI (Hedef asildi)" if dyn.booster_recommended else "Gerekli Degil (Yeterli)"

                lines = [
                    "=" * 74,
                    "AKTUATOR TEPKI SURESI VE HAVA TUKETIMI ANALIZI (ISA-75.25 / IEC 60534-6)",
                    "=" * 74,
                    f"Aktorator Modeli             : {dyn.model} (Piston: {dyn.piston_diameter_mm:.0f} mm, Strok: {dyn.stroke_mm:.0f} mm)",
                    f"Toplam Hava Hacmi            : {dyn.chamber_volume_liters:.2f} Litre",
                    f"Besleme Basinci              : {dyn.supply_pressure_bar_g:.2f} bar(g)",
                    f"Konumlandirici Debisi        : {dyn.positioner_flow_capacity_nm3h:.1f} Nm\u00b3/h",
                    "-" * 74,
                    f"Acilma Suresi (t_open)       : {dyn.stroke_time_open_sec:.2f} saniye",
                    f"Kapanma Suresi (t_close)     : {dyn.stroke_time_close_sec:.2f} saniye",
                    f"Hedef Strok Suresi           : {dyn.target_stroke_time_sec:.2f} saniye",
                    f"Hacim Yukseltici (Booster)   : {booster_status}",
                    "-" * 74,
                    f"Statik Kacak Tuketimi        : {dyn.quiescent_air_consumption_nm3h:.2f} Nm\u00b3/h",
                    f"Dinamik Modulasyon Tuketimi  : {dyn.dynamic_air_consumption_nm3h:.3f} Nm\u00b3/h ({cycles:.0f} cevrim/saat)",
                    f"Toplam Hava Tuketimi         : {dyn.total_air_consumption_nm3h:.3f} Nm\u00b3/h",
                    f"Onerilen Besleme Hatti       : {dyn.supply_line_recommendation}",
                    "=" * 74,
                ]
                if dyn.warnings:
                    lines.append("UYARILAR:")
                    for w in dyn.warnings:
                        lines.append(f"  [!] {w}")
                    lines.append("-" * 74)
                if dyn.engineering_notes:
                    lines.append("MUHENDISLIK NOTLARI:")
                    for n in dyn.engineering_notes:
                        lines.append(f"  * {n}")

                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", "\n".join(lines))
            except Exception as exc:
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", f"Hata olustu: {exc}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=6)
        ttk.Button(btn_frame, text="Hesapla", command=_calc).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=4)
        _calc()

    def _open_vendor_match_dialog(self) -> None:
        """Open Global Vendor Match dialog comparing suitable models from all manufacturers."""
        if not hasattr(self, "last_result") or self.last_result is None:
            messagebox.showinfo("Bilgi", "Once ana ekranda bir hesaplama yapin.")
            return

        req_cv = float(self.last_result.get("required_cv", 0.0))
        if req_cv <= 0:
            messagebox.showinfo("Bilgi", "Gecerli bir gerekli Cv hesaplanamadi.")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Global Vana Üreticileri & Model Eşleştirme (Vendor Match)")
        dlg.geometry("920x540")
        dlg.minsize(750, 420)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill="both", expand=True)

        header_lbl = ttk.Label(
            frame,
            text=f"Gerekli Cv: {req_cv:.2f} — Tüm üretici kataloglarından uygun vana adayları taranıyor",
            font=("Segoe UI", 11, "bold"),
        )
        header_lbl.pack(anchor="w", pady=(0, 8))

        filter_bar = ttk.Frame(frame)
        filter_bar.pack(fill="x", pady=(0, 8))

        ttk.Label(filter_bar, text="Bölge Filtresi:").pack(side="left", padx=(0, 4))
        reg_var = tk.StringVar(value="Tümü")
        reg_cb = ttk.Combobox(filter_bar, textvariable=reg_var, values=["Tümü", "USA", "Europe", "Asia"], state="readonly", width=12)
        reg_cb.pack(side="left", padx=(0, 16))

        only_ideal_var = tk.BooleanVar(value=True)
        ideal_chk = ttk.Checkbutton(filter_bar, text="Yalnızca İdeal Açıklık (%20 - %80)", variable=only_ideal_var)
        ideal_chk.pack(side="left")

        cols = ("vendor", "region", "model", "dn", "rated_cv", "opening", "status", "class")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=15)
        tree.heading("vendor", text="Üretici")
        tree.heading("region", text="Bölge")
        tree.heading("model", text="Model / Seri")
        tree.heading("dn", text="Çap")
        tree.heading("rated_cv", text="Nominal Cv")
        tree.heading("opening", text="Açıklık")
        tree.heading("status", text="Durum")
        tree.heading("class", text="Sınıf")

        tree.column("vendor", width=140)
        tree.column("region", width=80)
        tree.column("model", width=220)
        tree.column("dn", width=70, anchor="center")
        tree.column("rated_cv", width=80, anchor="e")
        tree.column("opening", width=80, anchor="e")
        tree.column("status", width=110, anchor="center")
        tree.column("class", width=70, anchor="center")

        tree.pack(fill="both", expand=True, side="left")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="left", fill="y")

        def _populate():
            for item in tree.get_children():
                tree.delete(item)
            reg = None if reg_var.get() == "Tümü" else reg_var.get()
            char_t = getattr(self, "flow_characteristic", None)
            char_val = char_t.get() if char_t else "equal_percentage"
            matches = find_catalog_matches(
                required_cv=req_cv,
                design_margin_pct=float(self.design_margin.get() if hasattr(self, "design_margin") else 10.0),
                flow_characteristic=char_val,
                region_filter=reg,
            )
            if only_ideal_var.get():
                matches = [m for m in matches if m.status == "ideal"]
            for m in matches:
                tree.insert("", "end", values=(
                    m.vendor_name,
                    m.region,
                    f"{m.family} ({m.style})",
                    f"DN{m.dn_mm}",
                    f"{m.rated_cv:.1f}",
                    f"%{m.opening_pct:.1f}",
                    m.status_label,
                    m.pressure_class,
                ))

        reg_cb.bind("<<ComboboxSelected>>", lambda _e: _populate())
        ideal_chk.configure(command=_populate)
        _populate()



    def _get_display_value(self, var: tk.Variable, fmt: str = ".4f") -> str:
        try:
            return f"{var.get():{fmt}}"
        except (tk.TclError, ValueError):
            return str(var.get())

    def _save_report(self) -> None:
        if not hasattr(self, 'last_result') or self.last_result is None:
            messagebox.showinfo("Bilgi", "Once hesaplama yapin.")
            return
        filepath = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
            title="Raporu kaydet",
        )
        if not filepath:
            return
        service_map = {"liquid": "Liquid", "gas": "Gas", "steam": "Steam"}
        report = build_report(
            service_map.get(self.service_type.get(), "Liquid"),
            self.last_fluid_summary,
            self.last_result,
        )
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report)
            messagebox.showinfo("Basarili", f"Rapor kaydedildi: {filepath}")
        except Exception as exc:
            messagebox.showerror("Hata", f"Rapor kaydedilemedi: {exc}")

    def _save_pdf_report(self) -> None:
        if not hasattr(self, 'last_result') or self.last_result is None:
            messagebox.showinfo("Bilgi", "Once hesaplama yapin.")
            return
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf"), ("All files", "*.*")],
            title="PDF raporu kaydet",
        )
        if not filepath:
            return
        service_map = {"liquid": "Liquid", "gas": "Gas", "steam": "Steam"}
        try:
            pdf_bytes = build_pdf_report(
                service_map.get(self.service_type.get(), "Liquid"),
                self.last_fluid_summary,
                self.last_result,
            )
            with open(filepath, "wb") as f:
                f.write(pdf_bytes)
            messagebox.showinfo("Basarili", f"PDF raporu kaydedildi: {filepath}")
        except Exception as exc:
            messagebox.showerror("Hata", f"PDF raporu kaydedilemedi: {exc}")

    def _collect_payload(self) -> dict:
        payload = {"service": self.service_type.get(), "vendor_key": self.vendor_key.get()}
        for key, var in self.inputs.items():
            payload[key] = var.get()
        payload["liquid_source"] = self.liquid_source.get()
        payload["gas_model"] = self._gas_model_key()
        payload["liquid_preset_label"] = self.liquid_preset_label.get()
        for prefix in ("liquid", "gas", "steam"):
            payload[f"{prefix}_temp_unit"] = getattr(self, f"{prefix}_temp_unit").get()
            payload[f"{prefix}_pres_unit"] = getattr(self, f"{prefix}_pres_unit").get()
            payload[f"{prefix}_flow_unit"] = getattr(self, f"{prefix}_flow_unit").get()
        return payload

    def _save_project(self) -> None:
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            title="Projeyi kaydet",
        )
        if not filepath:
            return
        payload = self._collect_payload()
        data = dump_project_json(self.service_type.get(), payload)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(data)
            messagebox.showinfo("Basarili", f"Proje kaydedildi: {filepath}")
        except Exception as exc:
            messagebox.showerror("Hata", f"Proje kaydedilemedi: {exc}")

    def _load_project(self) -> None:
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            title="Proje yukle",
        )
        if not filepath:
            return
        try:
            with open(filepath, encoding="utf-8") as f:
                text = f.read()
            payload = load_project_json(text)
            data = payload.get("data", {})
            service = _service_key(payload.get("service") or data.get("service") or "liquid")
            for key, value in data.items():
                if key in self.inputs:
                    with contextlib.suppress(tk.TclError, ValueError):
                        self.inputs[key].set(value)
            self.service_type.set(service)
            if "vendor_key" in data:
                self.vendor_key.set(data["vendor_key"])
            if "liquid_source" in data:
                self.liquid_source.set(data["liquid_source"])
            if "gas_model" in data:
                self.gas_model.set(data["gas_model"])
            if "liquid_preset_label" in data:
                self.liquid_preset_label.set(data["liquid_preset_label"])
            for prefix in ("liquid", "gas", "steam"):
                for suffix in ("temp_unit", "pres_unit", "flow_unit"):
                    key = f"{prefix}_{suffix}"
                    if key in data:
                        getattr(self, key).set(data[key])
            for key in self._unit_previous:
                self._unit_previous[key] = getattr(self, key).get()
            self._refresh_unit_labels()
            self._toggle_service()
            self._calculate(show_errors=False)
            messagebox.showinfo("Basarili", "Proje yuklendi.")
        except Exception as exc:
            messagebox.showerror("Hata", f"Proje yuklenemedi: {exc}")


def _self_test() -> int:
    """Headless smoke test for the frozen bundle (CoolProp import + sizing)."""
    fluid_state = get_pure_fluid_state("Water", 5.0, 25.0)
    result = size_liquid_valve(
        LiquidSizingInput(
            flow_m3h=10.0,
            inlet_pressure_bar_a=5.0,
            outlet_pressure_bar_a=3.0,
            density_kg_m3=fluid_state["density_kg_m3"],
            vapor_pressure_bar_a=fluid_state["vapor_pressure_bar_a"],
            critical_pressure_bar_a=fluid_state["critical_pressure_bar_a"],
            viscosity_pa_s=fluid_state["viscosity_pa_s"],
            fl=0.9,
        )
    )
    print(f"SELF-TEST OK cv={result.required_cv:.3f}")
    return 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    root = tk.Tk()
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    ValveSizingApp(root)
    root.mainloop()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    main()
