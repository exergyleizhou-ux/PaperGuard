# Contributing to PaperGuard

Thanks for considering a contribution. Most useful contributions are new
detectors. The codebase makes adding one straightforward.

## Setup

```bash
git clone <repo>
cd PaperGuard
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows:     .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]" types-openpyxl
pre-commit install   # optional
```

Run the validation suite before any PR:

```bash
pytest -m "not network" -v
ruff check src/ tests/
mypy src/
```

## Adding a new detector

Use `src/paperguard/detectors/a1_terminal_digit.py` as the canonical template.
Every detector must:

1. Subclass `BaseDetector`.
2. Define class-level `id`, `name`, `description`, `academic_basis`,
   `data_requirements`, `assumption_cluster` (all as `ClassVar`).
3. Implement `check_applicability(data) -> tuple[bool, str]` — return
   `(False, reason)` rather than raising when data doesn't fit.
4. Implement `_detect(data, seed) -> list[Finding]`.
5. Register the detector in
   `src/paperguard/core/registry.py:DetectorRegistry.register_default()`.

Each `Finding` must include at least three `innocent_explanations`. This is
non-negotiable — the epistemic posture of the tool depends on it.

## Tests

For each detector, add a test file under `tests/test_detectors/`. At minimum:

- One test that confirms the detector flags `fabricated_data` at
  `CONCERN` or higher.
- One test that confirms it does not flag `genuine_data` at `SUSPICIOUS+`.
- One test for inapplicability (e.g., wrong data type or too-small N).

Tests requiring network calls must be marked with `@pytest.mark.network` so
CI can skip them.

## Code style

- Python ≥ 3.11. Use `X | Y` not `Union[X, Y]`; `list[X]` not `List[X]`.
- Type hint every public function. We run `mypy --strict`.
- Use pydantic v2 for data validation; `click` for CLI; `rich` for terminal.
- Avoid hard-coding secrets. New API clients should read credentials via
  `pydantic-settings` in `config.py`.

## Epistemic rules (not negotiable)

The tool never outputs the words "fraud", "造假", "misconduct",
"cheating" in any report. Use "anomaly", "statistical inconsistency",
"unexplained pattern". Every report ends with the standard disclaimer.

A finding without `innocent_explanations` is a bug.
