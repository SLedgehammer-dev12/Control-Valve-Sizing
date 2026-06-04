import logging
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

logger = logging.getLogger(__name__)

from config import GAS_PRESET_NAMES, GAS_PRESETS
from fluid_properties import LIQUID_PRESETS, evaluate_gas_mixture, get_liquid_preset, get_pure_fluid_state, list_coolprop_fluids
from project_io import dump_project_json, load_project_json
from reporting import build_report
from valve_sizing import GasSizingInput, LiquidSizingInput, SteamSizingInput, size_gas_valve, size_liquid_valve, size_steam_valve
from vendor_catalog import get_vendor_definition, get_vendor_options


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

        # Display variables
        self.z_calculated_display = tk.StringVar(value="--")
        self.k_calculated_display = tk.StringVar(value="--")
        self.viscosity_calculated_display = tk.StringVar(value="--")
        self.gas_status_text = tk.StringVar(value="")
        self.gas_composition_text = None # Will be initialized in _build_form_gas
        self.steam_k_display = tk.StringVar(value="1.30")
        self.steam_z_display = tk.StringVar(value="1.00")
        self.steam_status_text = tk.StringVar(value="")

        self._build_menu()
        self._build_ui()
        self._toggle_service()
        self._update_gas_properties()

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Projeyi Kaydet (JSON)", command=self._save_project)
        file_menu.add_command(label="Projeyi Yukle (JSON)", command=self._load_project)
        file_menu.add_separator()
        file_menu.add_command(label="Cikis", command=self.root.quit)
        menubar.add_cascade(label="Dosya", menu=file_menu)
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
        self.liquid_preset_combo.bind("<<ComboboxSelected>>", lambda e: self._update_liquid_properties())
        row += 1

        # Temperature and basic fields
        fields = [
            ("Sicaklik [C]", "liquid_temp_c"),
            ("Debi [m3/h]", "liquid_flow_m3h"),
            ("Giris basinci [bar(a)]", "liquid_p1"),
            ("Cikis basinci [bar(a)]", "liquid_p2"),
            ("Yogunluk [kg/m3]", "liquid_density"),
            ("Buhar basinci [bar(a)]", "liquid_pv"),
            ("Kritik basinc [bar(a)]", "liquid_pc"),
            ("Viskozite [Pa.s]", "liquid_mu"),
            ("FL", "liquid_fl"),
            ("Fd", "liquid_fd"),
            ("Hat giris capi [mm]", "liquid_pipe_in_mm"),
            ("Hat cikis capi [mm]", "liquid_pipe_out_mm"),
        ]
        for label, key in fields:
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=6)
            ttk.Entry(parent, textvariable=self.inputs[key], width=18).grid(
                row=row, column=1, sticky="ew", padx=10, pady=6
            )
            row += 1

        parent.grid_columnconfigure(1, weight=1)

    def _build_form_steam(self, parent: ttk.LabelFrame) -> None:
        """Build steam form with auto-calculated k and Z from CoolProp."""
        fields = [
            ("Debi [kg/h]", "steam_flow_kgh"),
            ("Giris basinci [bar(a)]", "steam_p1"),
            ("Cikis basinci [bar(a)]", "steam_p2"),
            ("Sicaklik [C]", "steam_temp_c"),
        ]
        for row, (label, key) in enumerate(fields):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=8)
            ttk.Entry(parent, textvariable=self.inputs[key], width=18).grid(
                row=row, column=1, sticky="ew", padx=10, pady=8
            )

        row = len(fields)
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
        fields_simple = [
            ("Debi [Nm3/h]", "gas_flow_nm3h"),
            ("Giris basinci [bar(a)]", "gas_p1"),
            ("Cikis basinci [bar(a)]", "gas_p2"),
            ("Sicaklik [C]", "gas_temp_c"),
        ]

        # Build simple fields
        row = 0
        for label, key in fields_simple:
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=8)
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
        self.gas_composition_text.bind("<KeyRelease>", lambda e: self._update_gas_properties())
        self.gas_composition_text.grid_remove() # Initially hidden
        row += 1

        # Watch gas composition and conditions to refresh Z and MW automatically
        def _on_gas_composition_change(*args):
            if self.inputs["gas_composition"].get() == "Özel (Custom)":
                self.gas_composition_text.grid()
            else:
                self.gas_composition_text.grid_remove()
            self._update_gas_properties()

        self.inputs["gas_composition"].trace_add("write", _on_gas_composition_change)
        self.inputs["gas_p1"].trace_add("write", lambda *args: self._update_gas_properties())
        self.inputs["gas_temp_c"].trace_add("write", lambda *args: self._update_gas_properties())

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

    def _calculate_gas_properties(self) -> tuple[float, float, float]:
        """
        Calculate Z, specific_heat_ratio (k) and viscosity from gas composition
        and conditions using CoolProp. Falls back to defaults if calculation fails.
        Returns (z, k, viscosity_pa_s).
        """
        gas_type = self.inputs["gas_composition"].get()
        if gas_type == "Özel (Custom)":
            composition = self._parse_custom_composition()
        elif gas_type in GAS_PRESETS:
            composition = GAS_PRESETS[gas_type]["components"]
        else:
            self.z_calculated_display.set("--")
            self.k_calculated_display.set("--")
            self.viscosity_calculated_display.set("--")
            return 1.0, 1.30, 1e-5

        if not composition:
            self.z_calculated_display.set("--")
            self.k_calculated_display.set("--")
            self.viscosity_calculated_display.set("--")
            return 1.0, 1.30, 1e-5

        pressure_bar_a = self.inputs["gas_p1"].get()
        temperature_c = self.inputs["gas_temp_c"].get()

        try:
            total_pct = sum(row["fraction_pct"] for row in composition)
            if abs(total_pct - 100.0) > 1e-6:
                self.gas_status_text.set(f"Toplam {total_pct:.4f}% - 100% olmali. Varsayilan degerler kullanildi.")
                self.z_calculated_display.set("--")
                self.k_calculated_display.set("--")
                self.viscosity_calculated_display.set("--")
                return 1.0, 1.30, 1e-5

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
            self.z_calculated_display.set("ERROR")
            self.k_calculated_display.set("ERROR")
            self.viscosity_calculated_display.set("ERROR")
            self.gas_status_text.set(f"Gaz ozellikleri hesaplanamadi: {exc}. Varsayilan degerler kullanildi.")
            return 1.0, 1.30, 1e-5

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
            try:
                child.configure(state="normal" if is_liquid else "disabled")
            except tk.TclError:
                pass
        for child in self.gas_frame.winfo_children():
            try:
                child.configure(state="normal" if is_gas else "disabled")
            except tk.TclError:
                pass
        for child in self.steam_frame.winfo_children():
            try:
                child.configure(state="normal" if is_steam else "disabled")
            except tk.TclError:
                pass

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
                    self.inputs["liquid_p1"].get(),
                    self.inputs["liquid_temp_c"].get(),
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
        return base

    def _calc_liquid(self, vendor):
        result = size_liquid_valve(
            LiquidSizingInput(
                flow_m3h=self.inputs["liquid_flow_m3h"].get(),
                inlet_pressure_bar_a=self.inputs["liquid_p1"].get(),
                outlet_pressure_bar_a=self.inputs["liquid_p2"].get(),
                density_kg_m3=self.inputs["liquid_density"].get(),
                vapor_pressure_bar_a=self.inputs["liquid_pv"].get(),
                critical_pressure_bar_a=self.inputs["liquid_pc"].get(),
                viscosity_pa_s=self.inputs["liquid_mu"].get(),
                fl=vendor.fl or self.inputs["liquid_fl"].get(),
                fd=vendor.fd or self.inputs["liquid_fd"].get(),
                pipe_inlet_diameter_mm=self.inputs["liquid_pipe_in_mm"].get(),
                pipe_outlet_diameter_mm=self.inputs["liquid_pipe_out_mm"].get(),
            ),
            valve_series=list(vendor.sizes),
            valve_meta=self._vendor_meta_for_service(vendor, "liquid"),
        )
        fluid_summary = {
            "Fluid": self.liquid_preset_label.get(),
            "Temperature [C]": f"{self.inputs['liquid_temp_c'].get():.3f}",
            "Density [kg/m3]": f"{self.inputs['liquid_density'].get():.4f}",
            "Pv [bar(a)]": f"{self.inputs['liquid_pv'].get():.5f}",
            "Pc [bar(a)]": f"{self.inputs['liquid_pc'].get():.5f}",
            "Viscosity [Pa.s]": f"{self.inputs['liquid_mu'].get():.7g}",
        }
        return result, fluid_summary

    def _calc_gas(self, vendor):
        z_factor, k_value, mu_value = self._calculate_gas_properties()
        status = self.gas_status_text.get()
        if "100% olmali" in status or "hesaplanamadi" in status:
            raise ValueError(f"Gaz kompozisyonu gecersiz: {status}")
        result = size_gas_valve(
            GasSizingInput(
                flow_nm3h=self.inputs["gas_flow_nm3h"].get(),
                inlet_pressure_bar_a=self.inputs["gas_p1"].get(),
                outlet_pressure_bar_a=self.inputs["gas_p2"].get(),
                temperature_c=self.inputs["gas_temp_c"].get(),
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
        try:
            props = get_pure_fluid_state("Water", self.inputs["steam_p1"].get(), self.inputs["steam_temp_c"].get())
            gamma = props["specific_heat_ratio"]
            z_value = props["z"]
            self.steam_k_display.set(f"{gamma:.5f}")
            self.steam_z_display.set(f"{z_value:.5f}")
            self.steam_status_text.set("")
        except Exception as exc:
            gamma = 1.30
            z_value = 1.0
            self.steam_k_display.set("1.30")
            self.steam_z_display.set("1.00")
            self.steam_status_text.set(f"Steam ozellikleri okunamadi: {exc}")

        result = size_steam_valve(
            SteamSizingInput(
                flow_kg_h=self.inputs["steam_flow_kgh"].get(),
                inlet_pressure_bar_a=self.inputs["steam_p1"].get(),
                outlet_pressure_bar_a=self.inputs["steam_p2"].get(),
                temperature_c=self.inputs["steam_temp_c"].get(),
                specific_heat_ratio=gamma,
                z=z_value,
                xt=vendor.xt or 0.72,
                fl=vendor.fl or 0.9,
                fd=vendor.fd or 1.0,
            ),
            valve_series=list(vendor.sizes),
            valve_meta=self._vendor_meta_for_service(vendor, "steam"),
        )
        fluid_summary = {
            "Reference fluid": "Water/Steam",
            "k = Cp/Cv": f"{gamma:.6f}",
            "Z": f"{z_value:.6f}",
        }
        return result, fluid_summary

    def _calculate(self) -> None:
        self.last_result = None
        self.last_fluid_summary = None
        vendor = get_vendor_definition(self.vendor_key.get())

        dispatch = {"liquid": self._calc_liquid, "gas": self._calc_gas, "steam": self._calc_steam}
        try:
            svc = self.service_type.get()
            calc_fn = dispatch[svc]
            result, fluid_summary = calc_fn(vendor)
        except KeyError:
            messagebox.showerror("Hata", f"Bilinmeyen servis tipi: {svc}")
            return
        except Exception as exc:
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

        if result.get("warning"):
            lines.extend(["", f"Uyari: {result['warning']}"])

        self.result_box.delete("1.0", tk.END)
        self.result_box.insert("1.0", "\n".join(lines))

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
                    try:
                        self.inputs[key].set(value)
                    except (tk.TclError, ValueError):
                        pass
            if "service" in data:
                self.service_type.set(data["service"])
            if "vendor_key" in data:
                self.vendor_key.set(data["vendor_key"])
            if "liquid_source" in data:
                self.liquid_source.set(data["liquid_source"])
            if "liquid_preset_label" in data:
                self.liquid_preset_label.set(data["liquid_preset_label"])
            self._toggle_service()
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
