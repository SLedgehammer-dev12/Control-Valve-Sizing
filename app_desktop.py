import contextlib
import logging
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from config import GAS_PRESET_NAMES, GAS_PRESETS
from fluid_properties import LIQUID_PRESETS, evaluate_gas_mixture, get_liquid_preset, get_pure_fluid_state, list_coolprop_fluids
from project_io import dump_project_json, load_project_json
from reporting import build_report
from units import (
    GAS_FLOW_UNITS,
    LIQUID_FLOW_UNITS,
    PRESSURE_UNITS,
    STEAM_FLOW_UNITS,
    TEMPERATURE_UNITS,
    gas_flow_to_nm3h,
    liquid_flow_to_m3h,
    pressure_from_bar_a,
    pressure_to_bar_a,
    steam_flow_to_kgh,
    temperature_from_c,
    temperature_to_c,
)
from valve_sizing import GasSizingInput, LiquidSizingInput, SteamSizingInput, size_gas_valve, size_liquid_valve, size_steam_valve
from vendor_catalog import get_vendor_definition, get_vendor_options

logger = logging.getLogger(__name__)


class ValveSizingApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Control Valve Sizing")
        self.root.geometry("1100x820")
        self.root.minsize(980, 720)

        self.service_type = tk.StringVar(value="liquid")
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
        self.liquid_temp_unit = tk.StringVar(value="C")
        self.liquid_pres_unit = tk.StringVar(value="bar_a")
        self.liquid_flow_unit = tk.StringVar(value="m3h")
        self.gas_temp_unit = tk.StringVar(value="C")
        self.gas_pres_unit = tk.StringVar(value="bar_a")
        self.gas_flow_unit = tk.StringVar(value="nm3h")
        self.steam_temp_unit = tk.StringVar(value="C")
        self.steam_pres_unit = tk.StringVar(value="bar_a")
        self.steam_flow_unit = tk.StringVar(value="kgh")

        # Live-calculation bookkeeping
        self._live_enabled = False
        self._field_labels: dict[str, ttk.Label] = {}
        self._field_family: dict[str, str] = {}

        # Display variables
        self.z_calculated_display = tk.StringVar(value="--")
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

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Projeyi Kaydet (JSON)", command=self._save_project)
        file_menu.add_command(label="Projeyi Yukle (JSON)", command=self._load_project)
        file_menu.add_separator()
        file_menu.add_command(label="Hesaplama Raporu Kaydet (Markdown)", command=self._save_report)
        file_menu.add_command(label="ISA-20 Datasheet Kaydet (MD / HTML)", command=self._export_isa20)
        file_menu.add_separator()
        file_menu.add_command(label="Cikis", command=self.root.quit)
        menubar.add_cascade(label="Dosya", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Termal Genlesme (Boru Hatti)", command=self._open_thermal_expansion_dialog)
        tools_menu.add_command(label="Joule-Thomson ve Gaz Hidrat Analizi", command=self._open_joule_thomson_dialog)
        tools_menu.add_command(label="Coklu Calisma Durumu (Multi-Case Sizing)", command=self._open_multicase_dialog)
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
        body.grid_rowconfigure(3, weight=1)

        # Row 0: Service type + Vendor
        top_card = ttk.LabelFrame(body, text="Servis Tipi / Vendor")
        top_card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Radiobutton(
            top_card, text="Sivi", variable=self.service_type, value="liquid", command=self._toggle_service
        ).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        ttk.Radiobutton(
            top_card, text="Gaz", variable=self.service_type, value="gas", command=self._toggle_service
        ).grid(row=0, column=1, padx=12, pady=8, sticky="w")
        ttk.Radiobutton(
            top_card, text="Buhar", variable=self.service_type, value="steam", command=self._toggle_service
        ).grid(row=0, column=2, padx=12, pady=8, sticky="w")
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
            values=("equal_percentage", "linear"),
            state="readonly",
            width=16,
        ).grid(row=1, column=6, padx=(0, 12), pady=8, sticky="w")

        # Row 1: Liquid frame (left) + Gas frame (right)
        self.liquid_frame = ttk.LabelFrame(body, text="Sivi Verileri")
        self.liquid_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.gas_frame = ttk.LabelFrame(body, text="Gaz Verileri")
        self.gas_frame.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))

        # Row 2: Steam frame (span both columns)
        self.steam_frame = ttk.LabelFrame(body, text="Buhar Verileri")
        self.steam_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=(0, 0), pady=(0, 8))

        # Build liquid form with source selector and pipe reducer
        self._build_form_liquid(self.liquid_frame)
        self._build_form_gas(self.gas_frame)
        self._build_form_steam(self.steam_frame)

        # Live calculation: re-run on any flow / pressure / temperature edit
        live_keys = (
            "liquid_flow_m3h", "liquid_p1", "liquid_p2", "liquid_temp_c",
            "gas_flow_nm3h", "gas_p1", "gas_p2", "gas_temp_c",
            "steam_flow_kgh", "steam_p1", "steam_p2", "steam_temp_c",
        )
        for key in live_keys:
            self.inputs[key].trace_add("write", self._on_live_change)

        # Row 3: Action bar
        action_bar = tk.Frame(body, bg="#eef3f8")
        action_bar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 12))
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
        self.result_box.grid(row=4, column=0, columnspan=2, sticky="nsew")

    def _build_form_liquid(self, parent: ttk.LabelFrame) -> None:
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
            ("Buhar basinci", "pres", "liquid_pv"),
            ("Kritik basinc", "pres", "liquid_pc"),
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

    def _add_unit_selector_row(self, parent: ttk.LabelFrame, row: int, prefix: str, flow_units: dict[str, str]) -> None:
        """Add a compact temperature / pressure / flow unit selector row."""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=4)
        ttk.Label(frame, text="Birimler:").pack(side="left")
        spec = [
            ("Sicaklik", f"{prefix}_temp_unit", list(TEMPERATURE_UNITS.values())),
            ("Basinc", f"{prefix}_pres_unit", list(PRESSURE_UNITS.values())),
            ("Debi", f"{prefix}_flow_unit", list(flow_units.values())),
        ]
        for label_text, var_name, values in spec:
            ttk.Label(frame, text=label_text).pack(side="left", padx=(10, 2))
            combo = ttk.Combobox(frame, textvariable=getattr(self, var_name), values=values, state="readonly", width=10)
            combo.pack(side="left", padx=(0, 4))
            combo.bind("<<ComboboxSelected>>", self._on_live_change)

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

    def _on_preset_change(self, *_args) -> str:
        """Refresh liquid properties from the selected preset and re-calculate."""
        self._update_liquid_properties()
        return self._on_live_change()

    def _on_live_change(self, *_args) -> str:
        """Re-calculate silently on unit changes or input edits."""
        if not getattr(self, "_live_enabled", False):
            return ""
        with contextlib.suppress(tk.TclError):
            self._refresh_unit_labels()
            self._calculate(show_errors=False)
        return ""

    def _build_form_steam(self, parent: ttk.LabelFrame) -> None:
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

    def _build_form_gas(self, parent: ttk.LabelFrame) -> None:
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

        # Add xT field
        ttk.Label(parent, text="xT").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self.inputs["gas_xt"], width=18).grid(
            row=row, column=1, sticky="ew", padx=10, pady=8
        )
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
            )
            z_value = summary.z if summary.z is not None else 1.0
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

    def _toggle_service(self) -> None:
        svc = self.service_type.get()
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

    def _update_liquid_properties(self) -> None:
        """Auto-fill liquid properties from preset or CoolProp."""
        source = self.liquid_source.get()
        label = self.liquid_preset_label.get()
        if source == "Preset":
            preset_map = {v["label"]: k for k, v in LIQUID_PRESETS.items()}
            key = preset_map.get(label)
            if key:
                preset = get_liquid_preset(key)
                self.inputs["liquid_density"].set(preset["density_kg_m3"])
                self.inputs["liquid_pv"].set(preset["vapor_pressure_bar_a"])
                self.inputs["liquid_pc"].set(preset["critical_pressure_bar_a"])
                self.inputs["liquid_mu"].set(preset["viscosity_pa_s"])
        elif source == "CoolProp pure fluid":
            try:
                props = get_pure_fluid_state(
                    label,
                    pressure_to_bar_a(self.inputs["liquid_p1"].get(), self.liquid_pres_unit.get()),
                    temperature_to_c(self.inputs["liquid_temp_c"].get(), self.liquid_temp_unit.get()),
                )
                self.inputs["liquid_density"].set(props["density_kg_m3"])
                self.inputs["liquid_pv"].set(props["vapor_pressure_bar_a"])
                self.inputs["liquid_pc"].set(props["critical_pressure_bar_a"])
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
        p1 = pressure_to_bar_a(self.inputs["liquid_p1"].get(), self.liquid_pres_unit.get())
        p2 = pressure_to_bar_a(self.inputs["liquid_p2"].get(), self.liquid_pres_unit.get())
        pv = pressure_to_bar_a(self.inputs["liquid_pv"].get(), self.liquid_pres_unit.get())
        pc = pressure_to_bar_a(self.inputs["liquid_pc"].get(), self.liquid_pres_unit.get())
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
        fluid_summary = {
            "Fluid": self.liquid_preset_label.get(),
            f"Temperature [{TEMPERATURE_UNITS[self.liquid_temp_unit.get()]}]": f"{temperature_from_c(temp_c, self.liquid_temp_unit.get()):.3f}",
            "Density [kg/m3]": f"{self.inputs['liquid_density'].get():.4f}",
            f"Pv [{PRESSURE_UNITS[self.liquid_pres_unit.get()]}]": f"{pressure_from_bar_a(pv, self.liquid_pres_unit.get()):.5f}",
            f"Pc [{PRESSURE_UNITS[self.liquid_pres_unit.get()]}]": f"{pressure_from_bar_a(pc, self.liquid_pres_unit.get()):.5f}",
            "Viscosity [Pa.s]": f"{self.inputs['liquid_mu'].get():.7g}",
        }
        return result, fluid_summary

    def _calc_gas(self, vendor):
        z_factor, k_value, mu_value = self._calculate_gas_properties(raise_on_error=True)
        p1 = pressure_to_bar_a(self.inputs["gas_p1"].get(), self.gas_pres_unit.get())
        p2 = pressure_to_bar_a(self.inputs["gas_p2"].get(), self.gas_pres_unit.get())
        temp_c = temperature_to_c(self.inputs["gas_temp_c"].get(), self.gas_temp_unit.get())
        summary = evaluate_gas_mixture(self._gas_composition_rows(), "molar", p1, temp_c)
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
        lines = [
            f"Servis                  : {result['service']}",
            f"Gerekli Cv              : {result['required_cv']:.3f}",
            f"Gerekli Kv              : {result['required_kv']:.3f}",
            f"Secilen vana            : DN{result['valve_dn_mm']} ({result['valve_inch']})",
            f"Rated Cv                : {result['rated_cv']:.3f}",
            f"Rated Kv                : {result['rated_kv']:.3f}",
            f"Basinc dusumu [bar]     : {result['delta_p_bar']:.3f}",
            f"Bogulma durumu          : {'Evet' if result['is_choked'] else 'Hayir'}",
            f"Tasarim acikligi [%]    : {result['opening_percent']:.1f} (karakteristik: {self.flow_characteristic.get()})",
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

        if result.get("warning"):
            lines.extend(["", f"Uyari: {result['warning']}"])

        self.result_box.delete("1.0", tk.END)
        self.result_box.insert("1.0", "\n".join(lines))

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
        from multi_case import OperatingCase, size_multicase

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

        base_flow = float(self.inputs[flow_key].get())
        base_p1 = float(self.inputs[p1_key].get())
        base_p2 = float(self.inputs[p2_key].get())

        ttk.Label(frame, text="Min Debi:").grid(row=1, column=0, sticky="w", pady=3)
        min_q_var = tk.DoubleVar(value=max(base_flow * 0.4, 0.1))
        ttk.Entry(frame, textvariable=min_q_var, width=14).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Normal Debi:").grid(row=2, column=0, sticky="w", pady=3)
        norm_q_var = tk.DoubleVar(value=max(base_flow, 0.1))
        ttk.Entry(frame, textvariable=norm_q_var, width=14).grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(frame, text="Max Debi:").grid(row=3, column=0, sticky="w", pady=3)
        max_q_var = tk.DoubleVar(value=max(base_flow * 1.3, 0.1))
        ttk.Entry(frame, textvariable=max_q_var, width=14).grid(row=3, column=1, sticky="w", pady=3)

        res_box = tk.Text(frame, height=16, font=("Consolas", 9), wrap="none")
        res_box.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=10)
        frame.rowconfigure(4, weight=1)
        frame.columnconfigure(1, weight=1)

        def _calc_mc() -> None:
            try:
                temp_c = float(self.inputs[f"{cur_service}_temp_c"].get())
                cases = [
                    OperatingCase("Min", min_q_var.get(), base_p1, base_p2, temp_c),
                    OperatingCase("Normal", norm_q_var.get(), base_p1, base_p2, temp_c),
                    OperatingCase("Max", max_q_var.get(), max(base_p1 * 0.95, 0.1), base_p2, temp_c),
                ]
                fluid_data: dict[str, Any] = {}
                if cur_service == "liquid":
                    fluid_data = {
                        "density_kg_m3": self.inputs["liquid_density"].get(),
                        "vapor_pressure_bar_a": self.inputs["liquid_pv"].get(),
                        "critical_pressure_bar_a": self.inputs["liquid_pc"].get(),
                        "viscosity_pa_s": self.inputs["liquid_mu"].get(),
                    }
                elif cur_service == "gas":
                    fluid_data = {
                        "molecular_weight": 28.96,
                        "specific_heat_ratio": 1.40,
                        "viscosity_pa_s": 1.8e-5,
                        "z": 1.0,
                    }
                else:
                    fluid_data = {"specific_heat_ratio": 1.30, "z": 1.0}

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
        btn_frame.grid(row=5, column=0, columnspan=3, pady=6)
        ttk.Button(btn_frame, text="Hesapla", command=_calc_mc).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Kapat", command=dlg.destroy).pack(side="left", padx=4)

    def _open_cavitation_dialog(self) -> None:
        from trim_guidance import evaluate_cavitation_severity

        dlg = tk.Toplevel(self.root)
        dlg.title("Kavitasyon ve Agir Hizmet Trim Analizi (ISA-RP75.23)")
        dlg.geometry("640x520")
        dlg.resizable(True, True)
        dlg.transient(self.root)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill="both", expand=True)

        p1_init = float(self.inputs.get("liquid_p1", tk.StringVar(value="10.0")).get())
        p2_init = float(self.inputs.get("liquid_p2", tk.StringVar(value="5.0")).get())
        pv_init = float(self.inputs.get("liquid_pv", tk.StringVar(value="0.0234")).get())

        ttk.Label(frame, text="Giris Basinci P1 [bar(a)]:").grid(row=0, column=0, sticky="w", pady=4)
        p1_var = tk.DoubleVar(value=p1_init)
        ttk.Entry(frame, textvariable=p1_var, width=16).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Cikis Basinci P2 [bar(a)]:").grid(row=1, column=0, sticky="w", pady=4)
        p2_var = tk.DoubleVar(value=p2_init)
        ttk.Entry(frame, textvariable=p2_var, width=16).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Buharlasma Basinci Pv [bar(a)]:").grid(row=2, column=0, sticky="w", pady=4)
        pv_var = tk.DoubleVar(value=pv_init)
        ttk.Entry(frame, textvariable=pv_var, width=16).grid(row=2, column=1, sticky="w", pady=4)

        res_box = tk.Text(frame, height=14, width=65, font=("Consolas", 10))
        res_box.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(10, 8))
        frame.rowconfigure(3, weight=1)
        frame.columnconfigure(1, weight=1)

        def _calc_cav() -> None:
            try:
                p1 = p1_var.get()
                p2 = p2_var.get()
                pv = pv_var.get()
                dp = max(p1 - p2, 0.001)
                sigma = (p1 - pv) / dp if dp > 0 else 999.0
                res = evaluate_cavitation_severity(sigma, dp, p1, pv)
                lines = [
                    "=" * 60,
                    "KAVITASYON & AGIR HIZMET TRIM DEGERLENDIRMESI (ISA-RP75.23)",
                    "=" * 60,
                    f"Kavitasyon Indeksi (\u03c3)     : {res.sigma:.3f}",
                    f"Siddet Rejimi                 : {res.severity_level}",
                    f"Onerilen Kademe Sayisi        : {res.stages_recommended} Kademe",
                    f"Onerilen Trim Tipi            : {res.trim_recommendation}",
                    f"Kademe Basi Max Izin Delta P  : {res.max_allowable_dp_per_stage_bar:.1f} bar",
                    "-" * 60,
                ]
                if res.warnings:
                    lines.append("UYARILAR:")
                    for w in res.warnings:
                        lines.append(f"  [!] {w}")
                    lines.append("-" * 60)
                if res.engineering_notes:
                    lines.append("MUHENDISLIK NOTLARI:")
                    for n in res.engineering_notes:
                        lines.append(f"  * {n}")
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", "\n".join(lines))
            except Exception as exc:
                res_box.delete("1.0", tk.END)
                res_box.insert("1.0", f"Hata: {exc}")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=6)
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
        fluid_str = (
            self.inputs.get("liquid_fluid", tk.StringVar(value="Water")).get()
            if self.service_type.get() == "liquid"
            else ("NaturalGas" if self.service_type.get() == "gas" else "Steam")
        )

        md_text = build_isa20_report(self.last_result, tag="CV-101", service_desc=f"{srv} Control Valve", fluid_name=fluid_str)

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
                        self.last_result, tag="CV-101", service_desc=f"{srv} Control Valve", fluid_name=fluid_str
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

    def _collect_payload(self) -> dict:
        payload = {"service": self.service_type.get(), "vendor_key": self.vendor_key.get()}
        for key, var in self.inputs.items():
            payload[key] = var.get()
        payload["liquid_source"] = self.liquid_source.get()
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
            for key, value in data.items():
                if key in self.inputs:
                    with contextlib.suppress(tk.TclError, ValueError):
                        self.inputs[key].set(value)
            if "service" in data:
                self.service_type.set(data["service"])
            if "vendor_key" in data:
                self.vendor_key.set(data["vendor_key"])
            if "liquid_source" in data:
                self.liquid_source.set(data["liquid_source"])
            if "liquid_preset_label" in data:
                self.liquid_preset_label.set(data["liquid_preset_label"])
            for prefix in ("liquid", "gas", "steam"):
                for suffix in ("temp_unit", "pres_unit", "flow_unit"):
                    key = f"{prefix}_{suffix}"
                    if key in data:
                        getattr(self, key).set(data[key])
            self._refresh_unit_labels()
            self._toggle_service()
            self._calculate(show_errors=False)
            messagebox.showinfo("Basarili", "Proje yuklendi.")
        except Exception as exc:
            messagebox.showerror("Hata", f"Proje yuklenemedi: {exc}")


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
    main()
