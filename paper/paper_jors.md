---
title: 'PaperGuard: A 39-detector open-source pipeline for triage-stage statistical-anomaly screening in research-data integrity, with a non-verdict architectural design and 13 empirical-calibration studies'
authors:
  - name: Lei Zhou
    orcid: 0009-0000-9073-1349
    affiliation: 1
affiliations:
  - name: Independent
    index: 1
keywords:
  - research integrity
  - statistical forensics
  - LLM-text detection
  - image forensics
  - industrial-process data
  - GRIM
  - statcheck
  - SPRITE
  - Carlisle
  - DetectGPT
  - empirical calibration
date: 24 May 2026
bibliography: paper.bib
---

# Abstract

Research-data integrity tooling has historically been a patchwork of
single-signal procedures — statcheck for p-value recomputation, GRIM
and SPRITE for summary-statistic reverse-reconstruction, the Carlisle
procedure for randomised-trial baseline balance, Bik-style perceptual-
hash workflows for image-duplication forensics — each living in a
separate codebase with its own conventions and threshold choices.
`PaperGuard` is a Python library, command-line tool, and multi-tenant
Web UI that integrates Python re-implementations of these published
procedures with thirty additional detectors across eight methodological
families, including a four-detector industrial-process layer for which
no direct prior art exists in the academic-integrity literature.
The pipeline is architecturally **non-verdict**: every `Finding`
emitted by every detector ships with at least three plausible innocent
explanations, and verdict vocabulary (`fraud`, `fabrication`,
`misconduct`) is forbidden at the codebase level by a static check.
The software ships with thirteen public empirical calibration studies
covering text-layer recall (N=200), image-layer recall (N=212 in the
latest run), industrial-process recall (N=200 synthetic), B4-vs-R-
`statcheck` cross-validation (κ=0.79 on N=41), and per-endpoint
controlled benchmarks of the LLM-text family on five real chat-
completion endpoints. Honest negative findings — including image-layer
LR+ ≈ 1 on randomly-sampled retracted papers and continuation-
perplexity direction inversion on RLHF-tuned OpenAI reference language
models — are published at face value as a design choice.

# (1) Overview

## Motivation

The 2010s and 2020s have seen a sharp expansion in published research
that, on independent re-examination, contains data that is internally
inconsistent, mechanically irreproducible, or visually duplicated
across experimental conditions. Aggregate retraction rates have grown
roughly fivefold between 2002 and 2022 (Retraction Watch tracking),
and a significant fraction of those retractions cite at least one of
the failure modes that existing statistical and image-forensic
procedures are designed to detect: number-pattern impossibilities
flagged by GRIM [@brown2017grim] and SPRITE [@heathers2018sprite],
p-value recomputation errors flagged by `statcheck`
[@nuijten2016statcheck], baseline-balance implausibilities in
randomised trials flagged by the Carlisle method [@carlisle2017non],
image duplications flagged by perceptual-hash workflows
[@bik2016prevalence], and most recently, LLM-authored prose surfacing
through lexical fingerprints documented in
[@cabanac2024chatgpt; @kobak2025delving].

Each of these procedures was developed in isolation. The published
artifacts live in heterogeneous codebases — `statcheck` is an R
package; GRIM and SPRITE ship as standalone scripts; the
Carlisle test as published is a method, not a tool; pHash forensics
is a workflow embedded in human expert practice rather than a
standalone library. Each comes with its own input format, threshold
choices, and reporting style. A reviewer or editor wanting to run
the full battery of available checks must currently set up five-plus
toolchains, normalise their inputs by hand, and reconcile five-plus
reporting styles. The integration gap, more than the detection-method
gap, is what limits the impact of available science on day-to-day
peer review.

A second, more recent gap is that the prior-art literature on
research-integrity tooling addresses only academic publications. The
same data-fabrication and data-fitting failure modes occur in
**industrial process data** — SCADA logs from wastewater treatment
plants and pharmaceutical manufacturing batches contain mass-balance
inconsistencies, copy-pasted historical batches, and over-smoothed
trend windows that are direct analogues of the academic failure modes
the prior-art literature was built for, but no published tooling
generalises to that domain.

## Approach

`PaperGuard` integrates Python re-implementations of the published
procedures and 30+ additional detectors into a single package with a
uniform interface, a cross-detector evidence combiner, a plugin
entry-point system, and three deployment surfaces (Python library,
command-line tool, multi-tenant Web UI). The 39 detectors are
organised into eight methodological families (Table 1, §2). Each is
a subclass of the abstract `BaseDetector` class with declared
`data_requirements`, an explicit random seed, and a return value
structured as `DetectorResult(findings: list[Finding])`.

The architectural design is **non-verdict**. Every `Finding` emitted
by every detector carries at least three documented innocent
explanations alongside the anomaly. Verdict vocabulary — the words
`fraud`, `fabrication`, `misconduct`, and their Chinese-language
equivalents — is forbidden in all detector code paths by a static
check that runs in continuous integration. The tool surfaces
manuscripts worth a human reviewer's attention; it does not render
judgment, by construction.

## Use cases

`PaperGuard` targets three concrete use cases identified from
discussions with editorial-office staff and research-integrity
officers during 2024-2025:

1. **Pre-submission self-audit.** Authors who want to catch
   data-formatting inconsistencies before peer review run
   `paperguard scan file.csv` against their own draft data.
2. **Editorial-office triage.** Editors managing high-volume
   submission streams use the multi-tenant Web UI to surface
   manuscripts where multiple detectors fire concordantly, focusing
   limited human-review capacity on the highest-probability cases.
3. **Forensic re-examination.** Post-publication concerns flagged on
   PubPeer or similar channels can be re-examined by running the
   full detector battery against the published data, providing
   independent corroboration that does not rely on the reviewer's own
   confirmation bias.

A fourth, newer use case is **industrial-process data audit** —
pharmaceutical batch-release engineers and wastewater regulatory
auditors run `paperguard scan-industrial --domain X file.csv` to
flag potentially-falsified process data ahead of FDA or EPA
inspections. The industrial-domain templates (12 preconfigured
domains: wastewater, waste-gas, pharmaceutical, semiconductor, food,
environmental, agricultural, biopharma, biocomputation, distillation,
chemical, and medical) ship default tolerances drawn from regulatory
references; an empirical study (§3, Industrial-layer recall) documents
their out-of-the-box performance and the calibration step required to
adapt them to a specific facility.

# (2) Implementation and architecture

## Detector taxonomy

Table 1 summarises the 39 built-in detectors organised into eight
methodological families.

| Family | Detectors | Example methods |
|---|---|---|
| Digit-distribution | A1, A2, A7 | Terminal-digit χ², Benford's first-digit χ², last-digit 0/5 bias |
| Arithmetic / bounds | A3, A5, A6 | Inter-column arithmetic, decimal consistency, plausible-range filters |
| Summary-statistic consistency | B1, B4, B5, B6, B7, B8 | GRIM, statcheck, TIVA, GRIMMER, p-curve, SPRITE |
| Clinical-trial plausibility | C1 | Carlisle baseline-imbalance |
| Variance / independence | D1, D2, E1 | Residual smoothness, missing-data pattern, intra-class correlation |
| Image / metadata forensics | F1–F6, G1, G3, G4, G5 | pHash duplication, splice forensics, per-channel patch-splice, EXIF temporal, docx rsid, file metadata, reagent-year consistency |
| Text / authorship / paper-mill | M1, T1–T8 | Co-authorship graph signatures, n-gram plagiarism, NCT-trial outcome drift, data-availability audit, stylometry, three LLM-text detectors |
| Industrial process data | I1, I2, I5, I6 | Mass-balance closure, SCADA timestamp integrity, batch-repetition detection, process-trend over-smoothness |

## Core abstractions

The `BaseDetector` abstract base class (in `src/paperguard/core/
base_detector.py`) defines the contract every detector implements:

```python
class BaseDetector(ABC):
    id: ClassVar[str]                # e.g. "B4"
    name: ClassVar[str]              # human-readable
    description: ClassVar[str]       # one-line summary
    academic_basis: ClassVar[str]    # citation(s)
    data_requirements: ClassVar[list[str]]
    assumption_cluster: ClassVar[str]   # for combiner

    @abstractmethod
    def check_applicability(self, data) -> tuple[bool, str]: ...
    @abstractmethod
    def _detect(self, data, seed) -> list[Finding]: ...

    def detect(self, data, seed: int = 42) -> DetectorResult:
        """Public entrypoint; checks applicability then runs _detect."""
```

Each `Finding` carries seven required fields: severity (one of
`NOTE`, `CONCERN`, `SUSPICIOUS`, `CRITICAL`), one-line summary,
detailed body, structured evidence dictionary, list of `innocent_
explanations` (≥ 3 by codebase-level convention), an `academic_
reference` string, and applicability notes. A static check in CI
parses every Finding-emitting code path to ensure none of the
forbidden verdict words ever reach a user-facing field.

## Cross-detector evidence combination

Single detectors emit independent signals; their joint information
content is the focus of the `paperguard.evidence.combiner` module.
The combiner aggregates per-detector p-values via Benjamini-Hochberg
false-discovery-rate correction [@benjamini1995controlling] and
produces a Stouffer-style `integrity_score` that maps to severity
tiers rather than to a verdict. Detectors that share an
`assumption_cluster` (e.g. `paper_mill_signature` for T1, T4, M1)
are treated as non-independent and down-weighted accordingly.

## Plugin entry-point system

Third-party detectors register via the standard Python `entry_points`
mechanism under the `paperguard.detectors` group. A custom detector
deployed against a private lab's domain-specific data shape ships
as its own pip-installable wheel; `PaperGuard` discovers and
registers it automatically at next CLI invocation. No fork of the
core package is required, and the plugin's tests run in isolation
against the host's test suite.

## Three deployment surfaces

`PaperGuard` exposes its detector pipeline through three deployment
surfaces sharing a single core:

1. **Python library** — `from paperguard import scan; report =
   scan(path_or_dataframe)` for embedding in larger workflows.
2. **Command-line tool** — `paperguard scan file.{csv,xlsx,docx,pdf}`
   with HTML and JSON output, optional LLM-assisted explanation,
   and `--llm-review` / `--perplexity-check` / `--detectgpt-check`
   opt-in flags for the LLM-text family. A second `paperguard
   scan-industrial --domain D file.csv` subcommand routes through
   the 12 preconfigured industrial-domain templates.
3. **Multi-tenant Web UI** — FastAPI-based, with project-scoped
   scan history, per-user rate-limiting (10 attempts / 5 min on
   `/login`; 60 scans / 60 s / IP on `/scan`), SQLite or PostgreSQL
   persistence, optional Redis cache, an audit-event log
   (`AuditEvent` SQLAlchemy model + JSON-lines export via
   `PAPERGUARD_AUDIT_FILE` env var), and an admin-only audit
   endpoint at `GET /app/admin/audit`.

A `paperguard doctor` diagnostic command runs a 19-item environment
pre-flight (Python version, required and optional dependencies,
detector registry consistency, plugin entry points, cache directory
writability, dynamic dictionary state, image-corpus presence, and
LLM endpoint configuration) and reports machine-readable JSON
suitable for CI use.

# (3) Quality control

## Test suite

`PaperGuard` 2.6.1 ships **539 unit and integration tests** (with 3
additional network-dependent tests deselected by default). Tests are
authored in pytest, organised by detector family, and run under
`pytest -m "not network"` in continuous integration. A
`tests/test_golden.py` golden-fixture regression suite ensures no
new detector causes a regression on a curated set of synthetic
genuine inputs.

The project enforces `ruff` style checks and `mypy --strict` type
checks in CI on Linux, macOS, and Windows for Python 3.11 and 3.12.
The mypy `--strict` configuration covers 103 source files with zero
issues at the current release.

## Empirical calibration

Beyond unit tests, `PaperGuard` ships **13 public empirical
calibration studies**, with raw data and reproducible analyser
scripts under `scripts/` and per-study writeups under `docs/`. These
studies establish the operating-point performance of the detector
families against curated retraction corpora and synthetic ground
truth.

**Text-layer recall (`docs/recall_test_v10.md`, N=200).** The T6
lexical detector at its default 0.003 LLM-marker-density threshold
yields LR+ ≈ 0 against Nature-tier post-publication retractions,
where copy-editing systematically removes lexical LLM markers before
publication. At a stricter 0.001 threshold T6 achieves
**LR+ = ∞ (1 TP / 0 FP)** — one retracted manuscript exceeds the
density bar while every control stays below. T6's operating point is
therefore the pre-submission / preprint stage, not post-publication
forensics; both numbers are public and the conservative default is
the one shipped in the CLI.

**Image-layer recall (`docs/recall_image_v6.md`, N=212 analysable
after pdf_ok and image-extraction filtering of a raw 200 + 83
arm).** At the documented `z=6 / cluster=8` defaults, all three
image detectors converge to **LR+ ≈ 1**: F1 (intra-paper pHash)
1.09 with 95 % Wilson CI [0.44, 2.86]; F4 (cross-paper pHash)
0.96 [0.28, 3.46]; F6 (per-channel patch-splice) 0.89 [0.74, 1.12].
An earlier small-sample run (v4, N=159) reported F6 LR+ = 1.63;
the larger v5 (N=180) and v6 (N=212) samples revise this downward
to ≈ 1, confirming that the v4 figure was an upward sampling
fluctuation rather than calibrated signal. v5's apparent F4 LR+ of
4.36 was specifically a one-false-positive artifact in a control
arm of n=48; v6 with five false positives in n=49 collapses it to
0.96. The image layer at published defaults is structurally tuned
to the Bik-style patch-splice / Western-blot-duplication failure
mode [@bik2016prevalence], which is rare in randomly-sampled
retracted papers on the biomedical Europe-PMC OA corpus dominated
by statistical-fabrication, paper-mill, and image-reuse failures
that F1/F4/F6 do not cleanly detect. The image layer retains value
as a contributor to the cross-detector combiner; future work needs
F6 calibration against a Bik-curated patch-splice corpus that is
not publicly redistributable today.

**Industrial-layer recall (`docs/recall_industrial_v1.md`, 2 domains
× 50 clean + 50 tampered = 200 synthetic datasets).** On the
wastewater domain at template-default thresholds, I5 (batch-
repetition detection) achieves **LR+ = ∞** (60 % TPR / 0 % FPR);
I1 (mass-balance) and I2 (timestamp integrity) fire on
100 % TPR / 100 % FPR at the same defaults, indicating their
out-of-the-box tolerances need calibration to the local plant's
noise floor before they discriminate. On the pharma domain all
three detectors fire at 100 % / 100 %. The industrial layer is the
most recent addition and has no direct prior art in the academic-
integrity literature; this study sets a **lower bound** on
detector capability against synthetic ground truth, not an upper
bound against real EPA / FDA enforcement actions.

**B4 statcheck cross-validation (`docs/crossval_statcheck.md` +
`docs/crossval_statcheck_kappa.md`, N=41).** Against an
independent `scipy`-based p-value reference on a 41-paper
ground-truth corpus, B4 achieves recall = 100 % and decision-flip
recall = 94.12 %. A separate cross-validation directly against the
R `statcheck` package on the same corpus yields Cohen's κ = 0.79
[@landis1977measurement] on the decision-flip class, corresponding
to Landis–Koch "substantial agreement."

**T7 controlled endpoint benchmark
(`docs/llm_detection_real_endpoints.md`, 10 + 10 controlled corpus
× 5 endpoints).** T7 implements a continuation-perplexity probe in
the GLTR / DetectGPT line of work
[@gehrmann2019gltr; @mitchell2023detectgpt]. Across the five
real-logprobs endpoints tested, the four OpenAI models
(`gpt-3.5-turbo`, `gpt-4`, `gpt-4o-mini`, `gpt-4o`) all show
*reversed* continuation-perplexity direction (AI ppl > human ppl),
opposite to the classical assumption that LLM-authored prose
exhibits *lower* reference-LM perplexity than human academic
writing; the one non-OpenAI endpoint (Groq `qwen/qwen3-32b`) shows
the textbook direction. At an
inverted threshold equal to the maximum human perplexity in the
corpus, three of four OpenAI runs yield LR+ = ∞ at TPR 70–90 %
with *p* values from 0.0011 (`gpt-4o`) to 2.1 × 10⁻⁶ (`gpt-4`).
The pattern is **not monotonic in model size** — both
`gpt-3.5-turbo` (small, early) and `gpt-4` (older base)
outperform `gpt-4o` (newer, larger) at this task — implicating the
specific RLHF training schedule rather than parameter count.
`PaperGuard` exposes the inversion as a per-endpoint configuration
choice (`PAPERGUARD_T7_INVERT_THRESHOLD` env var, auto-detected
for OpenAI endpoints since 2.6.0). OpenAI reasoning models
(`o1`, `o3-mini`, `o4-mini`) cannot be used as T7 reference LMs:
the OpenAI API returns HTTP 400 *"You are not allowed to request
logprobs from this model"* — an infrastructure-level confirmation
of the structural-incompatibility claim previously argued only on
empirical grounds.

**T8 controlled endpoint benchmark.** Two real-endpoint runs.
On a non-reasoning paraphraser (OpenAI `gpt-4o`, N=10 + 10) T8
yields **LR+ = ∞** (2 / 10 TP, 0 / 10 FP) — the cleanest result
`PaperGuard` has on the DetectGPT family. On a reasoning-model
paraphraser (DeepSeek-v4-flash, N=10 + 10) the rewrites stay on
the LLM-likelihood manifold, the Mitchell-style probability-
curvature signal inverts, and measured LR+ collapses to 0.25 —
worse than coin flip — directly validating the structural
prediction in [@mitchell2023detectgpt]. The detector ships an
authoritative compatibility matrix documenting which endpoint
classes the method is mathematically valid on (non-reasoning
`gpt-4o`, self-hosted Llama-3.3-70B) and which it is structurally
incompatible with (OpenAI o-series, DeepSeek-v4,
Qwen3-thinking, GPT-5).

## Honest reporting of negative findings

Publishing the image-layer LR+ ≈ 1 result and the T7 direction
inversion at face value is an explicit design choice. The
alternative — quoting v4's small-sample LR+ of 1.63 or the
classical-direction T7 numbers as if they were calibrated operating
points — would be the kind of mis-calibration `PaperGuard` exists
to flag in other work. The project publishes its own false-negative
rates and per-endpoint failure modes alongside the detection
methodology so users can calibrate trust.

## Continuous integration

CI runs on Linux, macOS, and Windows × Python 3.11 and 3.12. Each
push runs `pytest`, `ruff check`, `mypy --strict`, a privacy grep
guarding against committing local-path or identifying-token leaks,
and a builds-the-JOSS-style-PDF workflow on changes to `paper/*`.
Tag pushes additionally trigger a multi-architecture
(`linux/amd64` + `linux/arm64`) Docker image build that publishes
to the GitHub Container Registry.

# (4) Availability

## Operating system

`PaperGuard` is platform-independent. Continuous integration tests
all three major desktop platforms (Linux, macOS, Windows) on every
push.

## Programming language

Python ≥ 3.11. The package targets 3.11 and 3.12 in CI; 3.13 is
expected to be added after `pydub` (a transitive dependency of the
Gradio HuggingFace-Space demo) catches up to the Python-3.13
`audioop` standard-library removal.

## Additional system requirements

A minimal install requires no external services. The Web UI surface
optionally uses Redis for cross-worker cache/rate-limit
coordination (via the `PAPERGUARD_REDIS_URL` env var); SQLite is the
default. The LLM-text detector family (T7 / T8) optionally requires
an OpenAI-compatible chat-completion endpoint; the per-endpoint
compatibility matrix in §3 documents which endpoints expose real
per-token logprobs and which are structurally incompatible with the
DetectGPT-style probability-curvature method.

## Dependencies

The core dependency surface is intentionally small: `pydantic` for
data structures, `numpy` and `pandas` for tabular work, `scipy` for
the statistical-recomputation detectors, `pymupdf` and `pdfplumber`
for PDF ingestion, `opencv-python` and `Pillow` for image
processing, `networkx` for the paper-mill graph signature, `httpx`
for OA-PDF and external-API fetches, `openpyxl` for `.xlsx`/
`.docx` ingestion, `bcrypt` and `itsdangerous` for the Web UI auth
layer, `sqlalchemy` and `aiosqlite` for the persistence layer,
`fastapi` and `uvicorn` for the Web UI HTTP layer, and `click` for
the CLI. Optional extras include `redis` (cache backend) and
`fakeredis` (test-only).

## List of contributors

Lei Zhou (https://orcid.org/0009-0000-9073-1349, principal
implementer, all code paths, all 13 empirical studies). Third-
party contributions are welcomed via the GitHub repository's pull-
request flow.

## Software location

| Resource | URL |
|---|---|
| Source code repository | https://github.com/exergyleizhou-ux/PaperGuard |
| Current release | https://github.com/exergyleizhou-ux/PaperGuard/releases/tag/v2.6.1 |
| PyPI distribution | https://pypi.org/project/paperguard/ |
| Multi-architecture Docker image | `ghcr.io/exergyleizhou-ux/paperguard:latest` (`linux/amd64` + `linux/arm64`) |
| Live browser demo | https://huggingface.co/spaces/exergyleizhou/paperguard-demo |
| Issue tracker | https://github.com/exergyleizhou-ux/PaperGuard/issues |

Archived versioned snapshots will be deposited on Zenodo with DOI
assignment on publication acceptance.

## Language

The user-facing CLI and Web UI surface support English and Simplified
Chinese; the codebase, paper, and inline-help strings are all
English-primary.

# (5) Reuse potential

`PaperGuard` is designed for reuse along five axes.

## Reuse axis 1: as a library

The `paperguard` Python package exposes the full detector pipeline
through a stable public API:

```python
from paperguard import scan
from paperguard.core.types import Severity

report = scan("manuscript_data.csv")
for finding in report.all_findings:
    if finding.severity >= Severity.SUSPICIOUS:
        print(f"[{finding.detector_id}] {finding.summary}")
```

Embedding `PaperGuard` in a larger editorial-workflow pipeline
(e.g. a journal's submission system that runs an automatic pre-check
on every uploaded manuscript) is a one-import operation. The
`DetectorRegistry` class exposes per-detector instantiation for
callers that want to disable specific detectors or override their
thresholds, and the cross-detector combiner can be invoked
independently of the full pipeline.

## Reuse axis 2: as a custom-detector platform

Third parties writing domain-specific detectors register them via
the standard Python `entry_points` mechanism under the
`paperguard.detectors` group. A custom detector deployed against a
private lab's proprietary instrument-data format ships as its own
pip-installable wheel; `PaperGuard` discovers and registers it at
CLI invocation time without any modification to the host package.
A reference template at `examples/03_custom_detector.py` walks
through the contract.

## Reuse axis 3: industrial-domain templates

The four industrial detectors (I1 mass-balance, I2 SCADA timestamp
integrity, I5 batch-repetition, I6 process-trend over-smoothness)
ship with 12 preconfigured domain templates (wastewater, waste-gas,
pharmaceutical, semiconductor, food, environmental, agricultural,
biopharma, biocomputation, distillation, chemical, medical). Each
template supplies default tolerances drawn from regulatory
references for that industry. Adapting `PaperGuard` to a 13th
domain is a configuration change (a new YAML file under
`src/paperguard/industrial/templates/`) rather than a code change.

## Reuse axis 4: as an empirical-corpus contribution

The 13 published empirical studies under `scripts/` and `docs/`
constitute a reusable corpus for future research-integrity tooling
work. The raw JSON results (e.g. `scripts/
recall_image_v6_results.json`, 283 records; `scripts/
t7_controlled_benchmark_results_*.json`, five-endpoint coverage)
are amenable to re-analysis under different threshold rules,
different aggregation methods, or different reference cohorts.
Downstream tools can publish their own performance numbers against
the same corpora for direct method-method comparison.

## Reuse axis 5: as a deployment-ready Web service

The multi-tenant Web UI surface is production-deployable as-is. A
single-Docker-container deployment (`docker run -p 8000:8000
ghcr.io/exergyleizhou-ux/paperguard:latest server`) suffices for an
in-organisation pilot. A production deployment behind an HTTPS-
terminating reverse proxy (`PAPERGUARD_BEHIND_PROXY=1`) with Redis
shared-state (`PAPERGUARD_REDIS_URL`) and PostgreSQL persistence
(`PAPERGUARD_DB_URL`) supports multi-worker, multi-host operation.
Authentication is single-tenant invite-only by default; OAuth/SAML
SSO integration is the most-requested feature on the public roadmap.

## Limitations and known boundaries

The honest negative findings reported in §3 — image-layer LR+ ≈ 1
on randomly-sampled retracted papers, T7 direction inversion on
RLHF-tuned OpenAI reference LMs — represent the most important
known boundaries of the tool. The image-detection family is
structurally tuned to the Bik-style patch-splice failure mode and
under-performs on the average retraction case, which is dominated
by statistical-fabrication and paper-mill failure modes that
image-pHash workflows do not cleanly catch. The T7/T8 family
requires a non-reasoning reference LM with real per-token logprobs;
OpenAI reasoning models are API-blocked from this access.

The industrial-layer detectors achieve their headline numbers
against synthetic ground truth; their real-world performance
against actual EPA/FDA enforcement-action data remains future
work, gated on access to such datasets.

# Acknowledgements

`PaperGuard` owes its statistical foundation to the published work
of James Heathers, Nicholas Brown, Elisabeth Bik, John Carlisle,
Michèle Nuijten, Guillaume Cabanac, Dmitry Kobak, Eric Mitchell,
and the broader research-integrity community. The project is
independent and unaffiliated with any of the authors cited; any
errors in the implementation or interpretation are entirely the
implementer's.

The author thanks the editors and reviewers in advance for their
time, and acknowledges the JOSS review process for the structured
feedback that informed several of the 2.4–2.6 release-cycle
improvements documented in §3.

# Funding statement

No external funding supported the development of `PaperGuard`. The
project is independently developed and maintained.

# Competing interests

The author declares no competing interests, financial or otherwise.

# References
