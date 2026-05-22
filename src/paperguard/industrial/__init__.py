"""PaperGuard industrial-domain extensions.

The ``industrial`` sub-package bundles **domain-specific templates**
that pre-configure the generic I1 / I2 / I5 detectors for concrete
industries. Each template is a thin factory producing the appropriate
``MassBalanceInput`` / ``TimestampIntegrityInput`` /
``BatchRepetitionInput`` for that sector.

Why templates instead of new detectors
--------------------------------------
The mathematical machinery is the same across industries — mass and
energy must be conserved everywhere, timestamps must be monotone
everywhere, narrative repetition is suspicious everywhere. What
changes between a wastewater plant and a semiconductor fab is
**which columns to plug into the balance equation, what the
tolerance should be, and which fields carry the narrative**.

Templates encode that domain knowledge once so the same I1/I2/I5
detectors work across 12 sectors documented in
``docs/industrial_domain_templates.md``.
"""
from paperguard.industrial.templates import (
    AGRICULTURE,
    BIOCOMPUTATION,
    BIOPHARMA,
    CHEMICAL,
    DISTILLERS_GRAIN,
    ENVIRONMENT,
    FOOD,
    MEDICAL,
    PHARMA,
    SEMICONDUCTOR,
    WASTE_GAS,
    WASTEWATER,
    DomainTemplate,
    get_template,
    list_domains,
)

__all__ = [
    "DomainTemplate",
    "AGRICULTURE",
    "BIOCOMPUTATION",
    "BIOPHARMA",
    "CHEMICAL",
    "DISTILLERS_GRAIN",
    "ENVIRONMENT",
    "FOOD",
    "MEDICAL",
    "PHARMA",
    "SEMICONDUCTOR",
    "WASTE_GAS",
    "WASTEWATER",
    "get_template",
    "list_domains",
]
