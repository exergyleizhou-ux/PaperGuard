"""Gradio app for the PaperGuard HuggingFace Space.

Deploy (as of 2.16.0):
    1. Create a new Space at https://huggingface.co/new-space
       SDK = Gradio. Hardware = CPU basic is sufficient.
    2. Copy this file to the Space repo as `app.py`.
    3. Copy `examples/hf_space_requirements.txt` as `requirements.txt`
       (gradio>=5.0,<6.0 + paperguard>=2.16.0).
    4. Copy `examples/hf_space_readme.md` as `README.md` — the
       frontmatter pins sdk_version: 5.34.0 and python_version: "3.11"
       which are both required (HF default container moved to Py 3.13
       which broke gradio 4.44 via removed `audioop` stdlib, and
       gradio 4.44 also imports `HfFolder` which `huggingface_hub` 1.x
       removed).
    5. `git push` to deploy.

Features
--------
- Upload a PDF or DOCX, or paste a DOI, or paste raw manuscript text.
- Toggle three opt-in detectors:
    * --llm-review         (PAPERGUARD_LLM_PROVIDER required)
    * --perplexity-check   (T7; needs logprobs-capable endpoint)
    * --detectgpt-check    (T8; works on any chat-completion endpoint)
- Returns the PaperGuard HTML report + JSON download.
- Built-in 3-paper example carousel (public retracted DOIs) for
  instant demos without uploading.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import gradio as gr

from paperguard import __version__
from paperguard.core.audit import AuditLog
from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import AuditReport, Severity
from paperguard.evidence.combiner import combine_evidence
from paperguard.reporter.html_export import export_html
from paperguard.reporter.json_export import export_json

# --- Empirical LR+ data from docs/recall_test_v8.md, surfaced in the UI ---
EMPIRICAL_FINDINGS_MD = f"""
**PaperGuard v{__version__}** — 40 detectors active (academic 36 + industrial 4).

**Validated performance**

- **T6 lexical** (LLM-text): LR+ = ∞ at 0.001 threshold, N = 200 OpenAlex
  retracted + matched controls (`docs/recall_test_v10.md`). Best signal
  for pre-submission / preprint screening.
- **B4 statcheck**: Cohen's κ = 0.79 vs the original R `statcheck` package
  on N = 41 ground-truth corpus (`docs/crossval_statcheck.md`).
- **F6 image cluster** (forensics): LR+ = 1.63 at N = 159
  (`docs/recall_image_v4.md`).
- **I5 batch repetition** (industrial): LR+ = ∞ on wastewater corpus,
  N = 200 (`docs/recall_industrial_v1.md`).
- **T6 at Nature-tier post-publication**: signal is largely copy-edited
  out before publication — T6 is a preprint / submission-stage screen,
  not a post-publication forensics signal.

**T7 / T8 scope.** T7 needs a non-reasoning LM with real per-token
logprobs (OpenAI `gpt-4o-mini` recommended; Groq Qwen3-32B gave a weak
LR+ 1.69 at N = 17). T8 needs a non-reasoning paraphraser that drifts
off-manifold — **reasoning models (o-series, DeepSeek-v4, Qwen3-thinking)
are structurally incompatible** (LR+ collapsed to 0.25 on DeepSeek-v4).
See `docs/llm_detection_real_endpoints.md` for the full matrix.

**This is a screening tool, not a verdict tool.** Every finding ships
with ≥ 3 innocent explanations. Do not treat any signal as evidence
of misconduct.
"""

# Public retracted DOIs for example carousel (Europe PMC-resolvable).
EXAMPLE_DOIS = [
    "10.1038/s41598-023-29485-0",
    "10.1371/journal.pone.0295951",
    "10.1057/s41599-023-01787-8",
]


def _make_audit_report(identifier: str) -> tuple[AuditReport, AuditLog]:
    import uuid

    run_id = uuid.uuid4().hex[:12]
    workdir = Path(tempfile.gettempdir()) / "paperguard_hf" / run_id
    workdir.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(run_id=run_id, output_dir=workdir)
    report = AuditReport(paper_identifier=identifier)
    return report, audit


def _scan_text(
    text: str,
    enable_t7: bool,
    enable_t8: bool,
    enable_llm_review: bool,
) -> tuple[AuditReport, Path, Path]:
    """Run text detectors on `text`. Returns (report, html_path, json_path)."""
    if enable_t7:
        os.environ["PAPERGUARD_PERPLEXITY_CHECK"] = "1"
    if enable_t8:
        os.environ["PAPERGUARD_DETECTGPT_CHECK"] = "1"

    report, _audit = _make_audit_report("hf-space-input")
    registry = DetectorRegistry().register_default()

    text_detector_ids = ["B4", "T4", "T5", "T6"]
    if enable_t7:
        text_detector_ids.append("T7")
    if enable_t8:
        text_detector_ids.append("T8")
    for did in text_detector_ids:
        det = registry.get(did)
        if det is None:
            continue
        result = det.detect(text)
        report.detector_results.append(result)
        report.all_findings.extend(result.findings)

    if enable_llm_review:
        from paperguard.llm.content_review import (
            LLMContentReviewer,
            issues_to_findings,
        )

        reviewer = LLMContentReviewer()
        if reviewer.enabled:
            issues = reviewer.review(text)
            if issues:
                report.all_findings.extend(issues_to_findings(issues))

    combine_evidence(report)

    tmp = Path(tempfile.mkdtemp(prefix="pg_hf_"))
    html_path = tmp / "report.html"
    json_path = tmp / "report.json"
    export_html(report, html_path, lang="en")
    export_json(report, json_path)
    return report, html_path, json_path


def _fetch_doi(doi: str) -> str | None:
    from paperguard.fetcher.europepmc import fetch_article

    article = fetch_article(doi)
    if article and article.full_text:
        return article.full_text
    return None


def _severity_badge(sev: Severity) -> str:
    colors = {
        "PASS": "#22c55e",
        "NOTE": "#3b82f6",
        "CONCERN": "#eab308",
        "SUSPICIOUS": "#a855f7",
        "CRITICAL": "#ef4444",
    }
    color = colors.get(sev.name, "#9ca3af")
    return (
        f"<span style='background:{color};color:white;padding:4px 12px;"
        f"border-radius:6px;font-weight:600;'>{sev.name}</span>"
    )


def _summary_for_ui(report: AuditReport) -> str:
    n_findings = len(report.all_findings)
    detectors_fired = sorted({f.detector_id for f in report.all_findings})
    return (
        f"### Result {_severity_badge(report.overall_severity)}\n\n"
        f"- **Total findings:** {n_findings}\n"
        f"- **Detectors that fired:** "
        f"{', '.join(detectors_fired) if detectors_fired else 'none'}\n"
        f"- **Identifier:** `{report.paper_identifier}`\n"
    )


def run_scan(
    doi: str,
    pasted_text: str,
    enable_t7: bool,
    enable_t8: bool,
    enable_llm_review: bool,
) -> tuple[str, str | None, str | None]:
    text: str | None = None
    if pasted_text and pasted_text.strip():
        text = pasted_text
        identifier = "pasted-text"
    elif doi and doi.strip():
        identifier = doi.strip()
        text = _fetch_doi(identifier)
        if text is None:
            return (
                f"### Could not resolve `{identifier}` via Europe PMC.\n\n"
                "Try a different DOI or paste text directly.",
                None,
                None,
            )
    else:
        return (
            "### Provide a DOI or paste manuscript text to scan.\n",
            None,
            None,
        )

    if len(text) < 300:
        return (
            "### Text is too short for the text detectors (need ≥ 300 words).\n",
            None,
            None,
        )

    report, html_path, json_path = _scan_text(
        text, enable_t7, enable_t8, enable_llm_review
    )

    summary = _summary_for_ui(report)
    findings_md = "\n\n### Findings\n\n"
    if not report.all_findings:
        findings_md += "_No findings — the manuscript passed all text detectors._\n"
    else:
        for f in report.all_findings[:20]:
            findings_md += (
                f"- {_severity_badge(f.severity)} **{f.detector_id}** "
                f"({f.detector_name}) — {f.summary}\n"
            )
    return summary + findings_md, str(html_path), str(json_path)


with gr.Blocks(
    title="PaperGuard demo",
    theme=gr.themes.Soft(),
) as demo:
    gr.Markdown(
        f"# PaperGuard {__version__} — research integrity screening"
    )
    gr.Markdown(EMPIRICAL_FINDINGS_MD)

    with gr.Tab("Scan a DOI (PMC)"):
        with gr.Row():
            with gr.Column():
                doi_input = gr.Textbox(
                    label="DOI",
                    placeholder="10.1038/s41598-023-29485-0",
                    info="Europe PMC must have the OA full text.",
                )
                gr.Examples(
                    examples=[[d] for d in EXAMPLE_DOIS],
                    inputs=[doi_input],
                    label="Public retracted DOIs (instant demo)",
                )

    with gr.Tab("Paste manuscript text"):
        text_input = gr.Textbox(
            label="Manuscript text",
            placeholder="Paste at least 500 words of the manuscript here…",
            lines=15,
        )

    with gr.Accordion("Opt-in detectors (LLM-based, may cost API calls)", open=False):
        t7_box = gr.Checkbox(
            label="T7 LLM perplexity (needs OPENAI_API_KEY + logprobs)",
            value=False,
        )
        t8_box = gr.Checkbox(
            label="T8 DetectGPT-style (needs OPENAI_API_KEY, no logprobs needed)",
            value=False,
        )
        llm_box = gr.Checkbox(
            label="LLM content review (needs PAPERGUARD_LLM_PROVIDER)",
            value=False,
        )

    scan_btn = gr.Button("Run scan", variant="primary")
    result_md = gr.Markdown()
    html_file = gr.File(label="Full HTML report")
    json_file = gr.File(label="Raw JSON")

    scan_btn.click(
        fn=run_scan,
        inputs=[doi_input, text_input, t7_box, t8_box, llm_box],
        outputs=[result_md, html_file, json_file],
    )

    gr.Markdown(
        "---\n*PaperGuard is a triage tool. Every finding ships with ≥3 "
        "innocent explanations. Do not treat any signal as evidence of "
        "misconduct.*"
    )


if __name__ == "__main__":
    demo.launch()
