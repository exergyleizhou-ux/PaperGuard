"""Domain-specific templates for I1 / I2 / I5 industrial detectors.

A ``DomainTemplate`` is a frozen dataclass holding domain-aware
defaults: the column names expected for a mass/energy balance, the
nominal SCADA sample period, narrative field names, and the
regulatory frame.

Twelve sectors are pre-defined; users can also build their own
``DomainTemplate`` from scratch or modify any of the constants in
this module.

Each template provides three factory methods:

- ``mass_balance(df, **overrides)`` → ``MassBalanceInput``
- ``timestamp_integrity(df, **overrides)`` → ``TimestampIntegrityInput``
- ``batch_repetition(df, **overrides)`` → ``BatchRepetitionInput``

Column names can be overridden per call so the same template works
whether the user's CSV uses "feed_kg" or "Feed (kg)" or "进料量_kg".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from paperguard.detectors.i1_mass_balance import MassBalanceInput
from paperguard.detectors.i2_timestamp_integrity import (
    TimestampIntegrityInput,
)
from paperguard.detectors.i5_batch_repetition import BatchRepetitionInput


@dataclass(frozen=True)
class DomainTemplate:
    """Industrial sector template for the I1 / I2 / I5 detectors."""

    name: str
    description: str
    regulatory_frame: str

    # I1 mass-balance defaults
    sources: tuple[str, ...] = ()
    sinks: tuple[str, ...] = ()
    tolerance_pct: float = 1.0

    # I2 timestamp defaults
    timestamp_column: str = "timestamp"
    expected_dt_seconds: float = 60.0

    # I5 batch-repetition defaults
    narrative_column: str = "narrative"
    id_column: str = "batch_id"
    narrative_min_words: int = 30

    # Sector-specific extras for documentation
    typical_units: dict[str, str] = field(default_factory=dict)
    falsification_modes: tuple[str, ...] = ()

    # ---------------------------------------------------------------
    # Factory methods — return the generic detector inputs
    # ---------------------------------------------------------------

    def mass_balance(self, df: pd.DataFrame, **overrides: Any) -> MassBalanceInput:
        return MassBalanceInput(
            df=df,
            sources=list(overrides.get("sources", self.sources)),
            sinks=list(overrides.get("sinks", self.sinks)),
            tolerance_pct=float(
                overrides.get("tolerance_pct", self.tolerance_pct)
            ),
        )

    def timestamp_integrity(
        self, df: pd.DataFrame, **overrides: Any
    ) -> TimestampIntegrityInput:
        return TimestampIntegrityInput(
            df=df,
            timestamp_column=str(
                overrides.get("timestamp_column", self.timestamp_column)
            ),
            expected_dt_seconds=float(
                overrides.get("expected_dt_seconds", self.expected_dt_seconds)
            ),
        )

    def batch_repetition(
        self, df: pd.DataFrame, **overrides: Any
    ) -> BatchRepetitionInput:
        return BatchRepetitionInput(
            df=df,
            text_column=str(
                overrides.get("narrative_column", self.narrative_column)
            ),
            id_column=str(overrides.get("id_column", self.id_column)),
            n_gram=int(overrides.get("n_gram", 4)),
            min_text_words=int(
                overrides.get("narrative_min_words", self.narrative_min_words)
            ),
        )


# ---------------------------------------------------------------------------
# 12 PRE-DEFINED DOMAINS
# ---------------------------------------------------------------------------

WASTEWATER = DomainTemplate(
    name="wastewater",
    description=(
        "Wastewater treatment plant (municipal or industrial). "
        "Mass-balance is on COD, BOD, TSS, and nutrients (N, P) "
        "between influent and effluent streams."
    ),
    regulatory_frame=(
        "USA: EPA NPDES (40 CFR 122); EU: Urban Wastewater Treatment "
        "Directive 91/271/EEC; China: GB 18918-2002."
    ),
    sources=("influent_COD_kg_day", "influent_BOD_kg_day"),
    sinks=(
        "effluent_COD_kg_day",
        "effluent_BOD_kg_day",
        "sludge_COD_kg_day",
        "co2_emitted_kg_day_C",
    ),
    tolerance_pct=5.0,
    timestamp_column="sample_time",
    expected_dt_seconds=3600.0,
    narrative_column="operator_log",
    id_column="report_date",
    typical_units={
        "COD": "kg/day", "BOD": "kg/day", "TSS": "kg/day",
        "TN": "kg/day", "TP": "kg/day", "flow": "m^3/day",
    },
    falsification_modes=(
        "Removal-efficiency padding (over-reported COD removal to meet permit)",
        "Sample-time backfill (operator writes 8 sample-times after the fact)",
        "Identical operator log copy-pasted across 30 days",
    ),
)

WASTE_GAS = DomainTemplate(
    name="waste_gas",
    description=(
        "Waste-gas / flue-gas treatment plant (incineration, FGD, "
        "VOC abatement). Mass balance is on pollutant species "
        "(VOC, NOx, SOx, PM, Hg) between inlet and stack."
    ),
    regulatory_frame=(
        "USA: EPA CEMS (40 CFR 60/63); EU: IED 2010/75/EU; "
        "China: GB 13223 (thermal power), GB 18484 (incineration)."
    ),
    sources=(
        "inlet_VOC_mg_Nm3",
        "inlet_NOx_mg_Nm3",
        "inlet_SO2_mg_Nm3",
    ),
    sinks=(
        "stack_VOC_mg_Nm3",
        "stack_NOx_mg_Nm3",
        "stack_SO2_mg_Nm3",
        "captured_in_scrubber_mg_Nm3",
    ),
    tolerance_pct=3.0,
    timestamp_column="cem_timestamp",
    expected_dt_seconds=1.0,
    narrative_column="shift_log",
    id_column="cem_run_id",
    typical_units={
        "VOC": "mg/Nm³", "NOx": "mg/Nm³", "SO2": "mg/Nm³",
        "particulate": "mg/Nm³", "flow": "Nm³/h",
    },
    falsification_modes=(
        "CEMS data substitution during exceedance windows",
        "Calibration-gas check log fabricated",
        "Stack-test report repetition across consecutive monitoring quarters",
    ),
)

DISTILLERS_GRAIN = DomainTemplate(
    name="distillers_grain",
    description=(
        "Distillers' grain / spent grain valorization plant — fresh "
        "wet grains in, dried product / feed / extracted oil / "
        "biogas out. Mass balance on dry-matter basis."
    ),
    regulatory_frame=(
        "USA: FDA CGMP for animal feed (21 CFR 507); EU: Regulation "
        "(EC) 183/2005 on feed hygiene; China: NY/T 2861 feed "
        "regulations."
    ),
    sources=(
        "wet_grain_in_kg",
        "added_water_kg",
        "enzyme_in_kg",
    ),
    sinks=(
        "dried_DDGS_kg",
        "extracted_oil_kg",
        "evaporated_water_kg",
        "wastewater_kg",
    ),
    tolerance_pct=2.0,
    timestamp_column="batch_start",
    expected_dt_seconds=86400.0,
    narrative_column="batch_narrative",
    id_column="batch_id",
    typical_units={
        "mass": "kg", "moisture": "%w/w", "protein": "%w/w (db)",
    },
    falsification_modes=(
        "Moisture-adjusted yield padding (dry weight inflated)",
        "Heavy-metal screening report substitution across batches",
        "Batch narrative copy-pasted from regulatory template",
    ),
)

CHEMICAL = DomainTemplate(
    name="chemical",
    description=(
        "Generic batch chemical reactor — reactants in, product + "
        "byproducts + waste out. Atom-balance equality for "
        "stoichiometric reactions."
    ),
    regulatory_frame=(
        "USA: EPA TSCA + RCRA; EU: REACH; China: GB 30000.x "
        "Chemical safety classification series."
    ),
    sources=("reactant_A_kg", "reactant_B_kg", "solvent_in_kg"),
    sinks=(
        "product_kg",
        "byproduct_kg",
        "waste_solvent_kg",
        "vent_gas_kg",
    ),
    tolerance_pct=1.0,
    timestamp_column="dcs_timestamp",
    expected_dt_seconds=30.0,
    narrative_column="batch_record",
    id_column="batch_id",
    typical_units={"mass": "kg", "temperature": "°C", "pressure": "bar"},
    falsification_modes=(
        "Yield padding (un-recovered material recorded as product)",
        "Reactor temperature trend back-filled after upset",
        "Batch record narrative shared across multiple lot numbers",
    ),
)

PHARMA = DomainTemplate(
    name="pharma",
    description=(
        "Pharmaceutical batch — API + excipients in, finished dosage "
        "+ rejects out. Strictest tolerance: GMP requires full "
        "yield reconciliation to ±0.5% per dosage strength."
    ),
    regulatory_frame=(
        "USA: FDA 21 CFR Part 211 (cGMP) + Part 11 (audit trail); "
        "EU: EMA EU GMP Annex 11; ICH Q7. China: 药品 GMP 附录."
    ),
    sources=("API_kg", "excipient_kg", "lubricant_kg"),
    sinks=("finished_tablets_kg", "reject_kg", "in_process_loss_kg"),
    tolerance_pct=0.5,
    timestamp_column="batch_record_ts",
    expected_dt_seconds=300.0,
    narrative_column="deviation_log",
    id_column="lot_number",
    narrative_min_words=20,
    typical_units={"mass": "kg", "potency": "% LC", "moisture": "%w/w"},
    falsification_modes=(
        "Deviation backdating (write after release)",
        "Lot record narrative cloned across consecutive lots (FDA WL 2018-04)",
        "Audit-trail timestamp rounding to mask exact reconciliation time",
    ),
)

FOOD = DomainTemplate(
    name="food",
    description=(
        "Food processing batch — raw ingredients in, finished food + "
        "waste + cleaning losses out. HACCP CCP monitoring + "
        "allergen / contaminant balance."
    ),
    regulatory_frame=(
        "USA: FDA FSMA + HACCP (21 CFR 117); EU: Regulation (EC) "
        "852/2004; China: GB 14881 + GB 22000."
    ),
    sources=("raw_ingredient_kg", "water_kg", "additive_kg"),
    sinks=(
        "finished_product_kg",
        "trim_waste_kg",
        "cleaning_loss_kg",
        "evaporated_water_kg",
    ),
    tolerance_pct=2.0,
    timestamp_column="ccp_timestamp",
    expected_dt_seconds=900.0,
    narrative_column="haccp_observation",
    id_column="production_lot",
    typical_units={"mass": "kg", "temperature": "°C", "pH": "pH unit"},
    falsification_modes=(
        "CCP temperature back-filled within tolerance after deviation",
        "Allergen swab-test log copy-pasted across product lines",
        "Net-weight padding by including packaging mass",
    ),
)

SEMICONDUCTOR = DomainTemplate(
    name="semiconductor",
    description=(
        "Semiconductor fab line — wafers in, processed wafers + "
        "yield rejects out. Mass-flow controllers (MFC) deliver "
        "process gases stoichiometrically; balance on gas consumption "
        "is the integrity check."
    ),
    regulatory_frame=(
        "ISO 14001 (env mgmt), SEMI E10 (equipment efficiency), "
        "ITRS process specs. No regulatory frame for yield reporting; "
        "investor due-diligence drives the integrity question."
    ),
    sources=("wafers_in_count", "process_gas_kg_per_lot"),
    sinks=("wafers_out_count", "yield_reject_count", "gas_vented_kg_per_lot"),
    tolerance_pct=0.1,
    timestamp_column="foup_timestamp",
    expected_dt_seconds=1.0,
    narrative_column="recipe_deviation",
    id_column="lot_id",
    typical_units={
        "wafers": "count", "gas": "sccm",
        "temperature": "°C", "vacuum": "Torr",
    },
    falsification_modes=(
        "Yield padding (rejected wafers reclassified as good)",
        "Recipe-deviation log shared across shifts",
        "MFC totalizer reset to mask over-consumption",
    ),
)

ENVIRONMENT = DomainTemplate(
    name="environment",
    description=(
        "Environmental monitoring — emission inventories, monitoring-"
        "well records, remediation mass balance. Time series across "
        "long horizons with regulatory submission requirements."
    ),
    regulatory_frame=(
        "USA: EPA CERCLA + CWA reporting; EU: E-PRTR Regulation "
        "166/2006; China: 排污许可 monitoring rules."
    ),
    sources=("source_kg_yr", "import_kg_yr"),
    sinks=(
        "stack_emission_kg_yr",
        "wastewater_kg_yr",
        "land_disposal_kg_yr",
        "off_site_transfer_kg_yr",
    ),
    tolerance_pct=10.0,
    timestamp_column="sample_date",
    expected_dt_seconds=86400.0 * 30.0,
    narrative_column="annual_report_section",
    id_column="reporting_year",
    narrative_min_words=50,
    typical_units={"mass": "kg/yr", "concentration": "mg/L or µg/m³"},
    falsification_modes=(
        "Annual emission inventory narrative cloned across years",
        "Monitoring-well sample-date clustering on report deadlines",
        "Negative or zero emissions where physical process forbids it",
    ),
)

MEDICAL = DomainTemplate(
    name="medical",
    description=(
        "Hospital / clinical operations data — drug dispensing "
        "records, procedure logs, billing-vs-record consistency. "
        "Narrative repetition signals copy-paste of patient notes."
    ),
    regulatory_frame=(
        "USA: HIPAA + CMS audit; EU: GDPR + MDR; China: 医疗机构管理条例. "
        "Subject to strict PHI handling — run on de-identified data only."
    ),
    sources=("drug_dispensed_count", "procedure_billed_count"),
    sinks=("drug_administered_count", "procedure_recorded_count"),
    tolerance_pct=0.0,
    timestamp_column="emr_timestamp",
    expected_dt_seconds=60.0,
    narrative_column="progress_note",
    id_column="encounter_id",
    narrative_min_words=40,
    typical_units={"count": "count", "dose": "mg"},
    falsification_modes=(
        "Phantom-billing (procedure billed, no progress-note text)",
        "Progress-note text duplicated across patients (Cerner copy-forward)",
        "EMR timestamp clustering on shift-end times",
    ),
)

AGRICULTURE = DomainTemplate(
    name="agriculture",
    description=(
        "Farm / agribusiness — seed + fertiliser + feed in, "
        "yield + biomass + livestock out. Field-log narrative "
        "and dispatch-record balance."
    ),
    regulatory_frame=(
        "USA: USDA NOP (organic), FDA Produce Safety Rule; "
        "EU: CAP IACS; China: 农产品质量安全法."
    ),
    sources=("seed_kg", "fertiliser_kg", "irrigation_m3"),
    sinks=("yield_kg", "biomass_residue_kg", "spoilage_kg"),
    tolerance_pct=15.0,
    timestamp_column="field_log_date",
    expected_dt_seconds=86400.0,
    narrative_column="field_observation",
    id_column="plot_id",
    typical_units={"mass": "kg", "area": "ha", "water": "m^3"},
    falsification_modes=(
        "Yield over-reporting for subsidy or certification claims",
        "Fertiliser application log narrative cloned across plots",
        "Organic-certification scout-record timestamp rounding",
    ),
)

BIOPHARMA = DomainTemplate(
    name="biopharma",
    description=(
        "Biopharmaceutical fermenter + downstream purification — "
        "feed media in, harvest broth → DSP unit operations → bulk "
        "drug substance + waste streams. Tighter tolerance than "
        "chemical because biological titres are precise."
    ),
    regulatory_frame=(
        "USA: FDA cGMP (21 CFR 210/211/600); ICH Q5 series; "
        "EU: EMA EU GMP Annex 1 (sterile) + Annex 2 (biological). "
        "USP / EP / JP pharmacopoeias for analytical methods."
    ),
    sources=(
        "feed_media_kg",
        "inoculum_kg",
        "antifoam_kg",
        "buffer_kg",
    ),
    sinks=(
        "harvest_broth_kg",
        "spent_media_kg",
        "purified_product_kg",
        "process_waste_kg",
    ),
    tolerance_pct=0.5,
    timestamp_column="bioreactor_ts",
    expected_dt_seconds=60.0,
    narrative_column="ebmr_narrative",
    id_column="campaign_lot",
    narrative_min_words=30,
    typical_units={
        "mass": "kg", "volume": "L", "OD600": "AU",
        "titre": "g/L", "pH": "pH unit",
    },
    falsification_modes=(
        "Titre back-calculation from claimed yield rather than "
        "measured (FDA recurring observation)",
        "EBMR narrative copy-forward across campaign lots",
        "Bioreactor pH trend back-filled during excursion",
    ),
)

BIOCOMPUTATION = DomainTemplate(
    name="biocomputation",
    description=(
        "Computational biology / bioinformatics — sequencing run "
        "metadata, sample volumes, pipeline run logs. Balance is "
        "on sample volume and read counts; narrative is the "
        "computational-protocol log."
    ),
    regulatory_frame=(
        "USA: CLIA + CAP molecular diagnostics; EU: IVDR 2017/746. "
        "Reproducibility frame: FAIR principles, MIQE for qPCR, "
        "MINSEQE for sequencing."
    ),
    sources=("input_sample_volume_uL", "input_read_count_M"),
    sinks=(
        "output_library_volume_uL",
        "output_demuxed_reads_M",
        "qc_failed_reads_M",
        "unmapped_reads_M",
    ),
    tolerance_pct=2.0,
    timestamp_column="run_start_ts",
    expected_dt_seconds=60.0,
    narrative_column="pipeline_log",
    id_column="run_id",
    narrative_min_words=40,
    typical_units={
        "volume": "µL", "reads": "M reads",
        "quality": "Q-score", "coverage": "×",
    },
    falsification_modes=(
        "Read-count padding (failed reads silently re-included)",
        "Pipeline-log narrative cloned across runs (same software "
        "versions but different sample QC outcomes)",
        "Run-start timestamp rounded to hide overlapping flowcell use",
    ),
)


# ---------------------------------------------------------------------------
# Registry of all templates
# ---------------------------------------------------------------------------

_ALL_TEMPLATES: dict[str, DomainTemplate] = {
    t.name: t
    for t in [
        WASTEWATER,
        WASTE_GAS,
        DISTILLERS_GRAIN,
        CHEMICAL,
        PHARMA,
        FOOD,
        SEMICONDUCTOR,
        ENVIRONMENT,
        MEDICAL,
        AGRICULTURE,
        BIOPHARMA,
        BIOCOMPUTATION,
    ]
}


def get_template(name: str) -> DomainTemplate:
    """Look up a template by its ``name`` field. Raises ``KeyError``."""
    if name not in _ALL_TEMPLATES:
        raise KeyError(
            f"Unknown industrial domain {name!r}. "
            f"Available: {sorted(_ALL_TEMPLATES.keys())}"
        )
    return _ALL_TEMPLATES[name]


def list_domains() -> list[str]:
    """Return the names of all built-in domain templates."""
    return sorted(_ALL_TEMPLATES.keys())
