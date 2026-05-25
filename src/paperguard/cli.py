"""CLI 入口。"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")

import click
from rich.console import Console
from rich.table import Table

from paperguard import __version__
from paperguard.config import get_settings
from paperguard.core.audit import AuditLog
from paperguard.core.registry import DetectorRegistry
from paperguard.core.types import AuditReport, DetectorResult, Finding, Severity
from paperguard.detectors.g4_metadata_forensics import MetadataForensicsInput
from paperguard.evidence.combiner import combine_evidence
from paperguard.extractor.docx_tables import parse_docx_tables
from paperguard.extractor.excel import parse_data_file
from paperguard.extractor.inline_numbers import extract_text_from_docx
from paperguard.extractor.pdf_text import extract_pdf_tables, extract_pdf_text
from paperguard.fetcher.crossref import CrossRefClient
from paperguard.fetcher.oa_pdf import fetch_oa_pdf
from paperguard.fetcher.openalex import OpenAlexClient
from paperguard.fetcher.orcid import OrcidCandidate, disambiguate_author
from paperguard.fetcher.pubpeer import PubPeerClient
from paperguard.fetcher.semantic_scholar import SemanticScholarClient
from paperguard.fetcher.unpaywall import UnpaywallClient
from paperguard.reporter.html_export import export_html
from paperguard.reporter.json_export import export_json
from paperguard.reporter.terminal import print_report
from paperguard.utils.hash import sha256_file


def _safe_pdf_tables(file_path: Path) -> tuple[dict[str, Any], str | None]:
    """Wrap ``extract_pdf_tables`` to never crash on malformed PDFs.

    Returns ``(sheets, error_message_or_None)``. Empty dict + message
    when the parser raises. Saves callers from having to know which
    publisher PDFs trip up pdfplumber/pdfminer.

    Since 2.14.0 (W2): when pdfplumber returns no tables, falls back
    to OCR-based extraction (requires ``pip install paperguard[ocr]``).
    """
    err: str | None = None
    try:
        sheets = dict(extract_pdf_tables(file_path))
    except Exception as e:  # noqa: BLE001
        sheets = {}
        err = f"{type(e).__name__}: {e}"

    # W2 OCR fallback: when pdfplumber finds no embedded tables,
    # try Tesseract-based extraction (requires paperguard[ocr]).
    if not sheets:
        try:
            from paperguard.extractor.ocr_tables import ocr_pdf_tables

            ocr_sheets = dict(ocr_pdf_tables(file_path))
            if ocr_sheets:
                return ocr_sheets, None
        except Exception:  # noqa: BLE001
            pass

    return sheets, err


def _safe_pdf_text(file_path: Path) -> tuple[str, str | None]:
    """Wrap ``extract_pdf_text`` to never crash on malformed PDFs."""
    try:
        return extract_pdf_text(file_path), None
    except Exception as e:  # noqa: BLE001
        return "", f"{type(e).__name__}: {e}"


def _run_detectors_on_file(
    file_path: Path,
    registry: DetectorRegistry,
    report: AuditReport,
    seed: int,
    audit: AuditLog | None = None,
    console: Console | None = None,
    *,
    skip_images: bool = False,
) -> None:
    """Run the common detector flow on a single file.

    Used by both the interactive ``scan`` command (with audit + console)
    and the headless ``_scan_single_file`` helper (without either).
    Single source of truth for which detectors run on which file types
    — historically these two paths had drifted apart and bugs had to
    be fixed twice. Keep them in sync by routing both through here.

    The audit log and console are optional; pass ``None`` for headless
    use (e.g. multi-tenant Web UI scan submissions).
    """
    suffix = file_path.suffix.lower()

    # --- 1) Table-data detectors (A1/A2/A3/A5/A6/A7/D1/D2) ----------------
    sheets: dict[str, Any] = {}
    if suffix in {".xlsx", ".xlsm", ".csv", ".tsv"}:
        sheets = dict(parse_data_file(file_path))
    elif suffix == ".docx":
        sheets = dict(parse_docx_tables(file_path))
    elif suffix == ".pdf":
        sheets, pdf_table_err = _safe_pdf_tables(file_path)
        if pdf_table_err is not None:
            if console is not None:
                console.print(
                    f"[yellow]  PDF table extraction failed for "
                    f"{file_path.name}: {pdf_table_err}[/]"
                )
            if audit is not None:
                audit.log_event(
                    "pdf_table_extract_failed",
                    {"file": str(file_path), "error": pdf_table_err},
                )

    if sheets and console is not None:
        console.print(
            f"[dim]  Extracted {len(sheets)} table(s) from {file_path.name}[/]"
        )

    for sheet_name, df in sheets.items():
        if audit is not None:
            audit.log_event(
                "sheet_processed",
                {
                    "file": str(file_path),
                    "sheet": sheet_name,
                    "rows": len(df),
                    "cols": [str(c) for c in df.columns],
                },
            )
        for d_id in ("A1", "A2", "A3", "A5", "A6", "A7", "D1", "D2"):
            detector = registry.get(d_id)
            if detector is None:
                continue
            result = detector.detect(df, seed=seed)
            report.detector_results.append(result)
            report.all_findings.extend(result.findings)

    # --- 2) Full-text detectors (B4 / T3 / T4 / T5 / T6) ------------------
    text = ""
    if suffix == ".docx":
        text = extract_text_from_docx(file_path)
    elif suffix in {".doc", ".docb"}:
        # Legacy Word binary format — best-effort via olefile (2.1.17).
        from paperguard.extractor.legacy_doc import extract_legacy_doc_text

        try:
            text = extract_legacy_doc_text(file_path)
        except Exception as e:  # noqa: BLE001
            if console is not None:
                console.print(
                    f"[yellow]  Legacy .doc text extraction failed for "
                    f"{file_path.name}: {type(e).__name__}: {e}[/]"
                )
            if audit is not None:
                audit.log_event(
                    "legacy_doc_text_failed",
                    {"file": str(file_path), "error": str(e)},
                )
    elif suffix == ".pdf":
        text, pdf_text_err = _safe_pdf_text(file_path)
        if pdf_text_err is not None:
            if console is not None:
                console.print(
                    f"[yellow]  PDF text extraction failed for "
                    f"{file_path.name}: {pdf_text_err}[/]"
                )
            if audit is not None:
                audit.log_event(
                    "pdf_text_extract_failed",
                    {"file": str(file_path), "error": pdf_text_err},
                )

    if text:
        if audit is not None:
            audit.log_event(
                "text_extracted",
                {"file": str(file_path), "chars": len(text)},
            )
        # T3 wants paper_year for year-stratified severity (since 2.0.7).
        # Build a DataAvailabilityInput so the year is plumbed through;
        # other text detectors take raw text.
        import os as _os_local

        from paperguard.detectors.t3_data_availability import (
            DataAvailabilityInput,
        )

        text_detector_ids: list[str] = ["B4", "T3", "T4", "T5", "T6"]
        # T7 / T8 are opt-in via --perplexity-check / --detectgpt-check.
        # Skip otherwise so we don't waste API calls per scan.
        if _os_local.environ.get(
            "PAPERGUARD_PERPLEXITY_CHECK", ""
        ).lower() in {
            "1", "true", "yes",
        }:
            text_detector_ids.append("T7")
        if _os_local.environ.get(
            "PAPERGUARD_DETECTGPT_CHECK", ""
        ).lower() in {
            "1", "true", "yes",
        }:
            text_detector_ids.append("T8")
        for d_id in text_detector_ids:
            detector = registry.get(d_id)
            if detector is None:
                continue
            if d_id == "T3":
                t3_input = DataAvailabilityInput(
                    text=text,
                    paper_year=report.paper_year,
                )
                result = detector.detect(t3_input, seed=seed)
            else:
                result = detector.detect(text, seed=seed)
            report.detector_results.append(result)
            report.all_findings.extend(result.findings)

    # --- 3) Metadata / forensics (G3 docx, G4 file metadata) --------------
    g3 = registry.get("G3")
    if g3 is not None and suffix == ".docx":
        result = g3.detect(file_path, seed=seed)
        report.detector_results.append(result)
        report.all_findings.extend(result.findings)

    g4 = registry.get("G4")
    if g4 is not None:
        g4_input = MetadataForensicsInput(
            file_path=file_path,
            claimed_authors=report.paper_authors,
        )
        result = g4.detect(g4_input, seed=seed)
        report.detector_results.append(result)
        report.all_findings.extend(result.findings)

    # --- 4) Image forensics (F1-F7) -----------------------------------------
    if not skip_images and suffix in {".docx", ".pdf", ".doc", ".docb"}:
        from tempfile import TemporaryDirectory

        from paperguard.detectors.f1_image_duplication import (
            ImageDuplicationInput,
        )
        from paperguard.detectors.f2_internal_duplication import (
            InternalDuplicationInput,
        )
        from paperguard.detectors.f3_splice_forensics import (
            SpliceForensicsInput,
        )
        from paperguard.detectors.f4_cross_paper_image import (
            CrossPaperImageInput,
        )
        from paperguard.detectors.f5_exif_clustering import (
            ExifClusteringInput,
        )
        from paperguard.detectors.f6_patch_splice import (
            PatchSpliceInput,
        )
        from paperguard.detectors.f7_gan_spectral import (
            GanSpectralInput,
        )
        from paperguard.extractor.images import (
            extract_docx_images,
            extract_pdf_images,
        )

        with TemporaryDirectory() as tdir:
            tdir_path = Path(tdir)
            if suffix == ".docx":
                imgs = extract_docx_images(file_path, tdir_path)
            elif suffix == ".pdf":
                imgs = extract_pdf_images(file_path, tdir_path)
            else:  # .doc / .docb — legacy binary
                from paperguard.extractor.legacy_doc import (
                    extract_legacy_doc_images,
                )

                imgs = extract_legacy_doc_images(file_path, tdir_path)
            if audit is not None and imgs:
                audit.log_event(
                    "images_extracted",
                    {"file": str(file_path), "n_images": len(imgs)},
                )
            if console is not None and imgs:
                console.print(
                    f"[dim]  Extracted {len(imgs)} image(s) from "
                    f"{file_path.name} for F1-F7[/]"
                )

            # F1: intra-paper pHash duplication (needs ≥ 2 images)
            f1 = registry.get("F1")
            if f1 is not None and len(imgs) >= 2:
                result = f1.detect(
                    ImageDuplicationInput(image_paths=imgs), seed=seed
                )
                report.detector_results.append(result)
                report.all_findings.extend(result.findings)

            # F2: internal ORB-based duplication (needs ≥ 2 images)
            f2 = registry.get("F2")
            if f2 is not None and len(imgs) >= 2:
                try:
                    result = f2.detect(
                        InternalDuplicationInput(image_paths=imgs),
                        seed=seed,
                    )
                except Exception as e:  # noqa: BLE001
                    if audit is not None:
                        audit.log_event(
                            "f2_failed",
                            {"file": str(file_path), "error": str(e)},
                        )
                else:
                    report.detector_results.append(result)
                    report.all_findings.extend(result.findings)

            # F3: splice / copy-move forensics (per-image)
            f3 = registry.get("F3")
            if f3 is not None and imgs:
                try:
                    result = f3.detect(
                        SpliceForensicsInput(image_paths=imgs), seed=seed
                    )
                except Exception as e:  # noqa: BLE001
                    if audit is not None:
                        audit.log_event(
                            "f3_failed",
                            {"file": str(file_path), "error": str(e)},
                        )
                else:
                    report.detector_results.append(result)
                    report.all_findings.extend(result.findings)

            # F4: cross-paper duplication via persistent corpus.
            f4 = registry.get("F4")
            if f4 is not None and imgs:
                from paperguard.config import get_settings as _gs

                corpus_path = _gs().cache_dir / "image_corpus.db"
                paper_id = report.paper_identifier
                authors = list(report.paper_authors)
                f4_input = CrossPaperImageInput(
                    image_paths=imgs,
                    store_path=corpus_path,
                    current_paper_id=paper_id,
                    current_authors=authors or None,
                )
                try:
                    result = f4.detect(f4_input, seed=seed)
                except Exception as e:  # noqa: BLE001
                    if audit is not None:
                        audit.log_event(
                            "f4_failed",
                            {"file": str(file_path), "error": str(e)},
                        )
                else:
                    report.detector_results.append(result)
                    report.all_findings.extend(result.findings)
                    if audit is not None:
                        audit.log_event(
                            "f4_ran",
                            {
                                "corpus_path": str(corpus_path),
                                "n_images_indexed": len(imgs),
                                "n_findings": len(result.findings),
                            },
                        )

            # F5: EXIF cross-image clustering (needs ≥ 3 images)
            f5 = registry.get("F5")
            if f5 is not None and len(imgs) >= 3:
                try:
                    result = f5.detect(
                        ExifClusteringInput(
                            image_paths=imgs, label=file_path.name,
                        ),
                        seed=seed,
                    )
                except Exception as e:  # noqa: BLE001
                    if audit is not None:
                        audit.log_event(
                            "f5_failed",
                            {"file": str(file_path), "error": str(e)},
                        )
                else:
                    report.detector_results.append(result)
                    report.all_findings.extend(result.findings)

            # F6: per-channel histogram patch splice (per-image)
            f6 = registry.get("F6")
            if f6 is not None and imgs:
                try:
                    result = f6.detect(
                        PatchSpliceInput(image_paths=imgs), seed=seed
                    )
                except Exception as e:  # noqa: BLE001
                    if audit is not None:
                        audit.log_event(
                            "f6_failed",
                            {"file": str(file_path), "error": str(e)},
                        )
                else:
                    report.detector_results.append(result)
                    report.all_findings.extend(result.findings)

            # F7: GAN / diffusion spectral signature (per-image)
            f7 = registry.get("F7")
            if f7 is not None and imgs:
                try:
                    result = f7.detect(
                        GanSpectralInput(image_paths=imgs), seed=seed
                    )
                except Exception as e:  # noqa: BLE001
                    if audit is not None:
                        audit.log_event(
                            "f7_failed",
                            {"file": str(file_path), "error": str(e)},
                        )
                else:
                    report.detector_results.append(result)
                    report.all_findings.extend(result.findings)

    # --- 5) PDF-specific: C1 Carlisle on auto-extracted baseline tables ---
    if suffix == ".pdf":
        from paperguard.detectors.c1_carlisle import CarlisleInput
        from paperguard.extractor.baseline_tables import extract_baseline_tables

        c1 = registry.get("C1")
        if c1 is not None:
            try:
                baselines = extract_baseline_tables(file_path)
            except Exception as e:  # noqa: BLE001
                if audit is not None:
                    audit.log_event(
                        "baseline_extract_failed",
                        {"file": str(file_path), "error": str(e)},
                    )
                baselines = []
            for bt in baselines:
                if len(bt.variables) < 5:
                    continue
                inp = CarlisleInput(
                    trial_id=f"{file_path.name}#p{bt.page_number}",
                    variables=bt.variables,
                )
                result = c1.detect(inp, seed=seed)
                report.detector_results.append(result)
                report.all_findings.extend(result.findings)
                if audit is not None:
                    audit.log_event(
                        "c1_auto_run",
                        {
                            "page": bt.page_number,
                            "n_variables": len(bt.variables),
                            "caption": bt.caption[:80],
                        },
                    )


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """PaperGuard — 学术论文数据诚信审查工具。"""


@main.command()
@click.argument(
    "paths",
    nargs=-1,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--file",
    "-f",
    "files",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="本地数据文件路径（可多次使用）。也可直接传位置参数。",
)
@click.option("--doi", help="论文 DOI（可选，用于获取元数据 + 撤稿状态）。")
@click.option(
    "--output-json",
    type=click.Path(path_type=Path),
    help="将报告导出为 JSON。",
)
@click.option(
    "--output-html",
    type=click.Path(path_type=Path),
    help="将报告导出为自包含 HTML。",
)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option(
    "--lang",
    type=click.Choice(["en", "zh-CN", "es", "ja", "de"]),
    default=None,
    help="报告语言（默认读 $PAPERGUARD_LANG，否则 en）。",
)
@click.option(
    "--check-paper-mill",
    is_flag=True,
    default=False,
    help=(
        "Run M1 paper-mill citation-graph detector. Requires --doi. "
        "Fetches a 2-hop citation subgraph (≤ 200 nodes) via OpenAlex. "
        "Will trigger many cached API calls on first run."
    ),
)
@click.option(
    "--paper-year",
    type=int,
    default=None,
    help=(
        "Publication year, used for year-stratified severity in T3 "
        "(ICMJE data-availability mandate 2018; NCT trial-reg 2005). "
        "Auto-filled from DOI metadata when --doi is given."
    ),
)
@click.option(
    "--llm-review",
    is_flag=True,
    default=False,
    help=(
        "Opt-in: also run LLM-assisted content review over the "
        "extracted manuscript text. Requires PAPERGUARD_LLM_PROVIDER "
        "(openai / anthropic / ollama) + corresponding API key. The "
        "LLM is restricted to 5 objective issue categories and "
        "forbidden from making verdicts about authors."
    ),
)
@click.option(
    "--perplexity-check",
    is_flag=True,
    default=False,
    help=(
        "Opt-in: run T7 LLM-perplexity detector on the manuscript text. "
        "Requires OPENAI_API_KEY (and optionally PAPERGUARD_LLM_BASE_URL "
        "+ PAPERGUARD_LLM_MODEL). Low continuation-perplexity is a "
        "paraphrase-resistant LLM-authorship signal. Not a verdict."
    ),
)
@click.option(
    "--detectgpt-check",
    is_flag=True,
    default=False,
    help=(
        "Opt-in: run T8 DetectGPT detector on the manuscript text. "
        "Works on any chat-completion endpoint (no logprobs needed). "
        "Requires OPENAI_API_KEY. Costs ~14 LLM calls per paper. "
        "Not a verdict."
    ),
)
@click.option(
    "--t6-abstract-only",
    is_flag=True,
    default=False,
    help=(
        "Restrict T6 lexical scan to the abstract + introduction "
        "(the author-written zone least touched by copy-editing). "
        "Empirically motivated by recall_test_v8: full-text T6 on "
        "Nature-tier published papers has LR+ ≈ 0 because "
        "copy-editing removes LLM phrase markers from Methods / "
        "Results / Discussion. Use this for post-publication "
        "screening; full-text T6 is the default for pre-submission."
    ),
)
@click.option(
    "--no-image-extract",
    is_flag=True,
    default=False,
    help=(
        "Skip automatic image extraction from PDF/DOCX files. "
        "When set, F1-F7 image-forensics detectors will not run. "
        "Useful for faster scans when only statistical / text "
        "detectors are needed."
    ),
)
def scan(
    paths: tuple[Path, ...],
    files: tuple[Path, ...],
    doi: str | None,
    output_json: Path | None,
    output_html: Path | None,
    seed: int,
    lang: str | None,
    check_paper_mill: bool,
    paper_year: int | None,
    llm_review: bool,
    perplexity_check: bool,
    detectgpt_check: bool,
    t6_abstract_only: bool,
    no_image_extract: bool,
) -> None:
    """扫描本地数据文件 + 可选 DOI 元数据。

    支持位置参数和 --file/-f 选项两种方式传入文件：

      paperguard scan a.pdf b.pdf

      paperguard scan -f a.pdf -f b.pdf
    """
    import os as _os

    all_files: tuple[Path, ...] = tuple(dict.fromkeys((*paths, *files)))
    files = all_files

    console = Console(legacy_windows=False)
    settings = get_settings()
    run_id = uuid.uuid4().hex[:12]
    audit_dir = settings.cache_dir / "audits" / run_id
    audit = AuditLog(run_id=run_id, output_dir=audit_dir)

    # T7/T8 opt-in: flip env vars the detectors check during applicability.
    if perplexity_check:
        _os.environ["PAPERGUARD_PERPLEXITY_CHECK"] = "1"
    if detectgpt_check:
        _os.environ["PAPERGUARD_DETECTGPT_CHECK"] = "1"
    if t6_abstract_only:
        _os.environ["PAPERGUARD_T6_ABSTRACT_ONLY"] = "1"

    report = AuditReport(
        paper_identifier=doi or (str(files[0]) if files else "local"),
        seed=seed,
    )
    if paper_year is not None:
        report.paper_year = paper_year

    if doi:
        _fetch_metadata(report, audit, doi, settings.email, console)
        # If --paper-year was not explicitly passed, fall back to what
        # the DOI lookup populated (OpenAlex provides publication_year).
        if paper_year is None and report.paper_year:
            console.print(
                f"[dim]  paper_year auto-filled from DOI: {report.paper_year}[/]"
            )

    # 如果给了 --doi 但没给 -f，尝试通过 Unpaywall 自动拉 OA PDF
    if doi and not files:
        with console.status(f"[cyan]Looking up OA PDF for {doi}..."):
            up = UnpaywallClient(email=settings.email)
            try:
                tmp_pdf = settings.cache_dir / "auto_pdf" / f"{doi.replace('/', '_')}.pdf"
                downloaded = up.download_oa_pdf(doi, tmp_pdf)
            finally:
                up.close()
        if downloaded:
            console.print(f"[green]Downloaded OA PDF → {downloaded}[/]")
            files = (downloaded,)
            audit.log_event("oa_pdf_downloaded", {"doi": doi, "path": str(downloaded)})
        else:
            console.print(
                "[yellow]No OA PDF available via Unpaywall; "
                "scan will report DOI-only metadata.[/]"
            )

    registry = DetectorRegistry().register_default()

    for file_path in files:
        console.print(f"[cyan]Processing {file_path.name}...[/]")
        file_hash = sha256_file(file_path)
        report.file_hashes[str(file_path)] = file_hash
        audit.log_event(
            "file_loaded",
            {"path": str(file_path), "sha256": file_hash},
        )
        _run_detectors_on_file(
            file_path, registry, report, seed, audit=audit, console=console,
            skip_images=no_image_extract,
        )

    # Auto-NCT → T2 trial outcome consistency
    # If a NCT/ISRCTN ID was found in any extracted text, auto-run T2 (best effort)
    # NOTE: T2 needs `reported_primary_outcomes` which we can't reliably extract
    # automatically yet, so we just log the trial ID for now.
    from paperguard.extractor.trial_ids import extract_trial_ids

    combined_text_for_ids = " ".join(
        str((r.findings[0].evidence or {}).get("raw_text", ""))
        for r in report.detector_results
        if r.findings
    )
    # 更简单：从已抽 text 重新扫
    nct_ids_found: list[str] = []
    for file_path in files:
        suffix2 = file_path.suffix.lower()
        try:
            if suffix2 == ".pdf":
                text_for_id = extract_pdf_text(file_path)
            elif suffix2 == ".docx":
                text_for_id = extract_text_from_docx(file_path)
            else:
                text_for_id = ""
        except Exception:  # noqa: BLE001
            text_for_id = ""
        for tid in extract_trial_ids(text_for_id):
            if tid not in nct_ids_found:
                nct_ids_found.append(tid)
    if nct_ids_found:
        console.print(
            f"[cyan]Found {len(nct_ids_found)} trial registration ID(s): "
            f"{', '.join(nct_ids_found[:3])}"
            + (f" (+{len(nct_ids_found) - 3} more)" if len(nct_ids_found) > 3 else "")
            + "[/]"
        )
        audit.log_event("trial_ids_extracted", {"ids": nct_ids_found})

        # Live verify NCT IDs against ClinicalTrials.gov v2 API.
        # If a paper claims NCT123… and the registry returns 404, that's
        # a SUSPICIOUS finding (fabricated trial id is a real fraud pattern).
        from paperguard.fetcher.clinicaltrials import ClinicalTrialsClient

        nct_only = [n for n in nct_ids_found if n.upper().startswith("NCT")]
        if nct_only:
            with console.status(
                f"[cyan]Verifying {len(nct_only)} NCT ID(s) against ClinicalTrials.gov..."
            ):
                ct_client = ClinicalTrialsClient(email=settings.email)
                missing: list[str] = []
                verified: list[str] = []
                try:
                    for nct in nct_only:
                        try:
                            study = ct_client.get_study(nct)
                        except Exception as e:  # noqa: BLE001
                            audit.log_event(
                                "ct_gov_lookup_failed",
                                {"nct": nct, "error": str(e)},
                            )
                            continue
                        if study is None:
                            missing.append(nct)
                        else:
                            verified.append(nct)
                finally:
                    ct_client.close()
            if verified:
                console.print(
                    f"[green]  ✓ {len(verified)} NCT verified in registry[/]"
                )
                audit.log_event("ct_gov_verified", {"nct_ids": verified})
            if missing:
                console.print(
                    f"[red]  ✗ {len(missing)} NCT NOT FOUND in registry: "
                    f"{', '.join(missing[:3])}"
                    + (
                        f" (+{len(missing) - 3} more)"
                        if len(missing) > 3
                        else ""
                    )
                    + "[/]"
                )
                audit.log_event("ct_gov_missing", {"nct_ids": missing})
                missing_findings: list[Finding] = []
                for nct in missing:
                    missing_findings.append(
                        Finding(
                            detector_id="T2",
                            detector_name="Clinical Trial Outcome Consistency",
                            severity=Severity.SUSPICIOUS,
                            summary=(
                                f"Claimed trial registration {nct} does not "
                                "exist in ClinicalTrials.gov"
                            ),
                            detail=(
                                f"The manuscript references {nct} as a "
                                "trial-registration identifier, but the "
                                "ClinicalTrials.gov v2 API returns 404. A "
                                "registered, ICMJE-compliant trial must "
                                "have a resolvable record. An unresolvable "
                                "NCT in a published article is a strong "
                                "signal worth investigating."
                            ),
                            evidence={"nct_id": nct, "ct_gov_status": "404"},
                            innocent_explanations=[
                                "OCR misread the NCT number (off by 1-2 digits)",
                                "The trial actually registered with a non-US "
                                "registry (ISRCTN/ChiCTR/ACTRN/EudraCT) and "
                                "the NCT-like format is coincidental",
                                "Very recent registration not yet indexed "
                                "in the v2 API (rare; takes 24-48 h)",
                                "Registry record was withdrawn by the "
                                "submitter (rare; usually leaves a stub)",
                            ],
                            academic_reference=(
                                "ICMJE 2005: required pre-registration of "
                                "all interventional trials. Live API check "
                                "against https://clinicaltrials.gov/api/v2"
                            ),
                        )
                    )
                if missing_findings:
                    report.detector_results.append(
                        DetectorResult(
                            detector_id="T2",
                            applicable=True,
                            findings=missing_findings,
                        )
                    )
                    report.all_findings.extend(missing_findings)
    _ = combined_text_for_ids  # silence linter

    # M1 — paper-mill citation-graph (opt-in via --check-paper-mill)
    if check_paper_mill and doi:
        m1 = registry.get("M1")
        if m1 is not None:
            from paperguard.fetcher.citation_graph import build_citation_subgraph

            with console.status(
                f"[cyan]Fetching 2-hop citation subgraph for {doi}..."
            ):
                try:
                    graph = build_citation_subgraph(
                        doi, max_hops=2, max_nodes=200, email=settings.email
                    )
                except Exception as e:  # noqa: BLE001
                    console.print(f"[yellow]Citation graph build failed: {e}[/]")
                    graph = None
            if graph is not None and graph.number_of_nodes() >= 8:
                result = m1.detect(graph, seed=seed)
                report.detector_results.append(result)
                report.all_findings.extend(result.findings)
                audit.log_event(
                    "m1_citation_graph",
                    {
                        "n_nodes": graph.number_of_nodes(),
                        "n_edges": graph.number_of_edges(),
                        "n_findings": len(result.findings),
                    },
                )
                console.print(
                    f"[dim]M1 ran on subgraph: "
                    f"{graph.number_of_nodes()} nodes, "
                    f"{graph.number_of_edges()} edges → "
                    f"{len(result.findings)} finding(s)[/]"
                )

    # LLM content review (opt-in, after detector findings collected)
    if llm_review:
        from paperguard.llm.content_review import (
            LLMContentReviewer,
            issues_to_findings,
        )

        reviewer = LLMContentReviewer()
        if not reviewer.enabled:
            console.print(
                "[yellow]--llm-review requested but PAPERGUARD_LLM_PROVIDER "
                "is not set; skipping LLM review.[/]"
            )
        else:
            # Re-extract text from each input file (cheap; results
            # already in disk cache for pdf cases) and feed to LLM.
            combined_text = ""
            for fp in files:
                suffix = fp.suffix.lower()
                if suffix == ".docx":
                    combined_text += extract_text_from_docx(fp) + "\n\n"
                elif suffix == ".pdf":
                    t, _ = _safe_pdf_text(fp)
                    combined_text += t + "\n\n"
            if combined_text.strip():
                with console.status(
                    f"[cyan]LLM review ({reviewer.provider}) "
                    f"over {len(combined_text):,} chars..."
                ):
                    issues = reviewer.review(combined_text)
                if issues:
                    llm_findings = issues_to_findings(issues)
                    llm_result = DetectorResult(
                        detector_id="LLM_REVIEW",
                        applicable=True,
                        findings=llm_findings,
                    )
                    report.detector_results.append(llm_result)
                    report.all_findings.extend(llm_findings)
                    console.print(
                        f"[yellow]  LLM flagged {len(llm_findings)} "
                        f"issue(s) in the manuscript text[/]"
                    )
                    audit.log_event(
                        "llm_review_completed",
                        {
                            "n_issues": len(llm_findings),
                            "provider": reviewer.provider,
                            "model": reviewer.model or "default",
                        },
                    )

    combine_evidence(report)
    audit.log_event(
        "evidence_combined",
        {
            "overall_severity": report.overall_severity.label,
            "total_findings": len(report.all_findings),
        },
    )

    print_report(report, console, lang=lang)

    if output_json:
        export_json(report, output_json)
        console.print(f"[green]JSON report saved to {output_json}[/]")
    if output_html:
        export_html(report, output_html, lang=lang)
        console.print(f"[green]HTML report saved to {output_html}[/]")

    audit_file = audit.save()
    console.print(f"[dim]Audit log: {audit_file}[/]")


def _fetch_metadata(
    report: AuditReport,
    audit: AuditLog,
    doi: str,
    email: str,
    console: Console,
) -> None:
    """通过 OpenAlex + CrossRef 填充论文元数据 + 撤稿状态。"""
    with console.status(f"[cyan]Fetching metadata for {doi}..."):
        try:
            oa = OpenAlexClient(email=email)
            work: dict[str, Any] | None = oa.get_work_by_doi(doi)
            if work:
                title = work.get("title") or work.get("display_name") or ""
                report.paper_title = title
                year = work.get("publication_year")
                if isinstance(year, int):
                    report.paper_year = year
                primary = work.get("primary_location") or {}
                source = primary.get("source") or {}
                report.paper_journal = source.get("display_name") or ""
                auths = work.get("authorships") or []
                report.paper_authors = [
                    (a.get("author") or {}).get("display_name") or ""
                    for a in auths[:10]
                ]
                # Capture OpenAlex author IDs for the retraction-history
                # cross-check below. These are stable OpenAlex URIs like
                # 'https://openalex.org/A1234567890' that the retraction-
                # rate endpoint accepts directly.
                author_ids: list[tuple[str, str]] = [
                    (
                        (a.get("author") or {}).get("display_name") or "",
                        (a.get("author") or {}).get("id") or "",
                    )
                    for a in auths[:10]
                    if (a.get("author") or {}).get("id")
                ]

                # Author retraction-history scan. For each named author,
                # query their last ≤200 works for is_retracted=true. Tier
                # mapping is conservative: a single retraction can be
                # honest (e.g. uncorrectable error), three+ across a
                # career is highly atypical (Bik 2016; ORI investigation
                # data) and worth elevating.
                if author_ids:
                    with console.status(
                        f"[cyan]Checking retraction history of "
                        f"{len(author_ids)} author(s)..."
                    ):
                        for name, aid in author_ids:
                            try:
                                stats = oa.get_author_retraction_rate(aid)
                            except Exception as e:  # noqa: BLE001
                                audit.log_event(
                                    "author_retraction_lookup_failed",
                                    {"author": name, "error": str(e)},
                                )
                                continue
                            n_ret = int(stats.get("n_retracted", 0))
                            n_total = int(stats.get("n_works_sampled", 0))
                            if n_ret == 0:
                                continue
                            if n_ret >= 3:
                                ar_sev = Severity.CRITICAL
                            elif n_ret >= 1:
                                ar_sev = Severity.SUSPICIOUS
                            else:
                                ar_sev = Severity.CONCERN
                            ar_finding = Finding(
                                detector_id="AUTHOR_HISTORY",
                                detector_name="Author Retraction History",
                                severity=ar_sev,
                                summary=(
                                    f"Co-author {name} has {n_ret} "
                                    f"retracted work(s) on record "
                                    f"({n_total} sampled)"
                                ),
                                detail=(
                                    f"OpenAlex (synced with Retraction "
                                    f"Watch) shows author {name} "
                                    f"(OpenAlex ID {aid}) has "
                                    f"{n_ret} of {n_total} sampled "
                                    f"works marked is_retracted. "
                                    f"Retraction rate "
                                    f"{stats.get('retraction_rate', 0):.2%}. "
                                    "Multiple retractions across an "
                                    "author's career is highly atypical "
                                    "(< 1% of researchers have any "
                                    "retraction; ≥ 3 is rarer still and "
                                    "warrants closer reading of the "
                                    "current paper, especially in the "
                                    "methodology + data sections."
                                ),
                                evidence={
                                    "author_name": name,
                                    "openalex_author_id": aid,
                                    "n_retracted": n_ret,
                                    "n_works_sampled": n_total,
                                    "retraction_rate": stats.get(
                                        "retraction_rate"
                                    ),
                                    "retracted_work_ids": (
                                        stats.get("retracted_work_ids") or []
                                    )[:10],
                                },
                                innocent_explanations=[
                                    "Honest retractions for uncorrectable "
                                    "errors are not misconduct (e.g. data "
                                    "loss, reagent contamination found "
                                    "post-publication)",
                                    "Author may have been a low-level "
                                    "contributor on retracted multi-author "
                                    "papers led by someone else",
                                    "Highly prolific authors have higher "
                                    "absolute retraction counts at the "
                                    "same misconduct rate as the field",
                                    "Some 'retractions' in OpenAlex are "
                                    "actually corrections or republications "
                                    "with metadata still mis-flagged",
                                ],
                                academic_reference=(
                                    "OpenAlex is_retracted flag, synced "
                                    "with Retraction Watch. ORI 2010-2020 "
                                    "investigation statistics on repeat-"
                                    "offender base rates."
                                ),
                            )
                            ar_result = DetectorResult(
                                detector_id="AUTHOR_HISTORY",
                                applicable=True,
                                findings=[ar_finding],
                            )
                            report.detector_results.append(ar_result)
                            report.all_findings.append(ar_finding)
                            console.print(
                                f"[red]  ⚠ {name}: {n_ret} retracted "
                                f"work(s) in OpenAlex[/]"
                            )
                            audit.log_event(
                                "author_retraction_history_flagged",
                                {
                                    "author": name,
                                    "n_retracted": n_ret,
                                    "n_sampled": n_total,
                                },
                            )
            oa.close()
            audit.log_event("openalex_fetched", {"doi": doi, "found": bool(work)})

            cr = CrossRefClient(email=email)
            retraction = cr.check_retraction(doi)
            if retraction:
                report.retraction_status = "Retracted"
                audit.log_event("retraction_detected", retraction)
            cr.close()

            pp = PubPeerClient(email=email)
            pp_result = pp.get_comments(doi)
            if pp_result:
                count = int(pp_result.get("comment_count", 0) or 0)
                report.pubpeer_concerns_count = count
                audit.log_event("pubpeer_checked", pp_result)
                if count > 0:
                    console.print(
                        f"[yellow]PubPeer has {count} comment(s) on this DOI: "
                        f"{pp_result.get('search_url')}[/]"
                    )
                    # Emit a finding so PubPeer commentary affects
                    # overall_severity. The tier mapping is informed by
                    # empirical observation: most papers have 0; a
                    # handful of comments is normal scholarly discourse;
                    # double-digit threads (e.g. Bik-flagged image
                    # duplication papers) reliably precede or follow
                    # retraction.
                    if count >= 10:
                        pp_sev = Severity.CRITICAL
                    elif count >= 3:
                        pp_sev = Severity.SUSPICIOUS
                    else:
                        pp_sev = Severity.CONCERN
                    pp_finding = Finding(
                        detector_id="PUBPEER",
                        detector_name="PubPeer Commentary Signal",
                        severity=pp_sev,
                        summary=(
                            f"PubPeer has {count} public comment(s) on "
                            f"this DOI"
                        ),
                        detail=(
                            f"PubPeer (https://pubpeer.com) hosts public "
                            f"anonymous and signed commentary on published "
                            f"papers. This DOI has {count} comment(s) "
                            "indexed. PubPeer threads frequently precede "
                            "retractions (Bik et al. 2016 used PubPeer to "
                            "catalogue image-duplication retractions). The "
                            "specific comments may concern statistics, "
                            "image integrity, methodology, or be routine "
                            "post-publication review. Read the thread "
                            "before forming a judgement.\n"
                            f"Tier mapping: 1-2 → CONCERN, 3-9 → "
                            "SUSPICIOUS, 10+ → CRITICAL."
                        ),
                        evidence={
                            "pubpeer_comment_count": count,
                            "pubpeer_url": pp_result.get("search_url"),
                            "doi": doi,
                        },
                        innocent_explanations=[
                            "Routine post-publication discussion (e.g. "
                            "methods clarification, citation requests)",
                            "Anonymous commentary may be from competitors "
                            "or actors with non-integrity motives",
                            "Authors may have already addressed the "
                            "comments in a correction or response",
                            "High comment count can reflect topical "
                            "importance rather than concerns",
                        ],
                        academic_reference=(
                            "Bik EM et al. (2016) The Prevalence of "
                            "Inappropriate Image Duplication in "
                            "Biomedical Research Publications. mBio. "
                            "PubPeer's commentary is one of the primary "
                            "sources for that catalogue."
                        ),
                    )
                    pp_result_obj = DetectorResult(
                        detector_id="PUBPEER",
                        applicable=True,
                        findings=[pp_finding],
                    )
                    report.detector_results.append(pp_result_obj)
                    report.all_findings.append(pp_finding)
            pp.close()
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]Metadata fetch failed: {e}[/]")


@main.command("webui")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8765, show_default=True)
@click.option("--reload", is_flag=True, help="Auto-reload on code change (dev).")
def webui_cmd(host: str, port: int, reload: bool) -> None:
    """Run the FastAPI Web UI on http://<host>:<port>/ (dev mode)."""
    try:
        import uvicorn
    except ImportError as e:
        raise click.ClickException(
            "Web UI requires 'fastapi' + 'uvicorn'. Install with:\n"
            "    pip install paperguard[webui]"
        ) from e

    uvicorn.run(
        "paperguard.webui.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@main.command("server")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", type=int, default=8765, show_default=True)
@click.option(
    "--workers", type=int, default=2, show_default=True,
    help="Uvicorn worker processes.",
)
@click.option(
    "--api-token", default=None,
    help="If set, requires X-API-Token header on POST endpoints. "
         "Can also be set via PAPERGUARD_API_TOKEN env var.",
)
def server_cmd(host: str, port: int, workers: int, api_token: str | None) -> None:
    """Run the Web UI in production mode (multi-worker, no reload, with auth)."""
    try:
        import uvicorn
    except ImportError as e:
        raise click.ClickException(
            "Server requires 'fastapi' + 'uvicorn'. Install with:\n"
            "    pip install paperguard[webui]"
        ) from e

    import os

    if api_token:
        os.environ["PAPERGUARD_API_TOKEN"] = api_token
        click.echo("[security] API token enabled; clients must send X-API-Token header.")
    else:
        click.echo(
            "[warning] No API token set. Server accepts unauthenticated requests. "
            "Set --api-token or PAPERGUARD_API_TOKEN for production.",
            err=True,
        )

    uvicorn.run(
        "paperguard.webui.app:create_app",
        host=host,
        port=port,
        workers=workers,
        factory=True,
        log_level="info",
    )


@main.command("batch")
@click.option(
    "--glob",
    "patterns",
    multiple=True,
    required=True,
    help="文件 glob 模式，可多次使用。例如：--glob 'data/*.csv'。",
)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=Path("batch_reports"),
    show_default=True,
    help="批量报告输出目录。每个文件输出一个 .json 和一个 .html。",
)
@click.option(
    "--perplexity-check",
    is_flag=True,
    default=False,
    help="Run T7 LLM-perplexity detector on each file (requires OPENAI_API_KEY).",
)
@click.option(
    "--detectgpt-check",
    is_flag=True,
    default=False,
    help="Run T8 DetectGPT detector on each file (requires OPENAI_API_KEY).",
)
@click.option("--seed", type=int, default=42, show_default=True)
def batch(
    patterns: tuple[str, ...],
    out_dir: Path,
    perplexity_check: bool,
    detectgpt_check: bool,
    seed: int,
) -> None:
    """批量扫描：按 glob 展开所有匹配的文件，逐个 scan。"""
    import glob as glob_mod
    import os as _os_local

    console = Console(legacy_windows=False)
    out_dir.mkdir(parents=True, exist_ok=True)
    if perplexity_check:
        _os_local.environ["PAPERGUARD_PERPLEXITY_CHECK"] = "1"
    if detectgpt_check:
        _os_local.environ["PAPERGUARD_DETECTGPT_CHECK"] = "1"

    all_files: list[Path] = []
    for pattern in patterns:
        all_files.extend(Path(p) for p in glob_mod.glob(pattern, recursive=True))
    all_files = [p for p in all_files if p.is_file()]

    if not all_files:
        console.print("[yellow]No files matched.[/]")
        return

    console.print(f"[cyan]Batch scanning {len(all_files)} file(s)...[/]")

    summary: list[dict[str, Any]] = []
    for fp in all_files:
        report = _scan_single_file(fp, seed=seed)
        base = out_dir / fp.stem
        export_json(report, base.with_suffix(".json"))
        export_html(report, base.with_suffix(".html"))
        summary.append(
            {
                "file": str(fp),
                "overall": report.overall_severity.label,
                "n_findings": len(report.all_findings),
                "json": str(base.with_suffix(".json")),
                "html": str(base.with_suffix(".html")),
            }
        )
        console.print(
            f"  [{report.overall_severity.color}]{report.overall_severity.label}[/] "
            f"{fp.name}  ({len(report.all_findings)} findings)"
        )

    summary_path = out_dir / "summary.json"
    import json as _json

    summary_path.write_text(_json.dumps(summary, indent=2, ensure_ascii=False))
    console.print(f"[green]Summary -> {summary_path}[/]")


def _scan_single_file(
    file_path: Path,
    seed: int = 42,
    paper_year: int | None = None,
) -> AuditReport:
    """Headless single-file scan, used by the multi-tenant Web UI.

    Thin wrapper over ``_run_detectors_on_file`` with no audit log
    and no console output. Identical detector coverage to the
    ``paperguard scan`` command since 2.0.6.

    ``paper_year`` (optional) is plumbed through to T3 for year-
    stratified severity (since 2.0.8).
    """
    registry = DetectorRegistry().register_default()
    report = AuditReport(paper_identifier=str(file_path), seed=seed)
    if paper_year is not None:
        report.paper_year = paper_year
    report.file_hashes[str(file_path)] = sha256_file(file_path)
    _run_detectors_on_file(file_path, registry, report, seed)
    combine_evidence(report)
    return report


@main.command("scan-pmc")
@click.argument("doi")
@click.option(
    "--output-json",
    type=click.Path(path_type=Path),
    default=None,
)
@click.option(
    "--llm-review",
    is_flag=True,
    default=False,
    help=(
        "Also run LLM-assisted content review over the PMC full text. "
        "Requires PAPERGUARD_LLM_PROVIDER + API key."
    ),
)
@click.option(
    "--perplexity-check",
    is_flag=True,
    default=False,
    help=(
        "Run T7 LLM-perplexity detector on the PMC text. "
        "Requires OPENAI_API_KEY."
    ),
)
@click.option(
    "--detectgpt-check",
    is_flag=True,
    default=False,
    help=(
        "Run T8 DetectGPT detector on the PMC text. "
        "Requires OPENAI_API_KEY."
    ),
)
@click.option(
    "--t6-abstract-only",
    is_flag=True,
    default=False,
    help=(
        "Restrict T6 lexical scan to abstract + intro (recommended "
        "for published / post-publication scans; see "
        "docs/recall_test_v8.md)."
    ),
)
@click.option("--seed", type=int, default=42, show_default=True)
def scan_pmc(
    doi: str,
    output_json: Path | None,
    llm_review: bool,
    perplexity_check: bool,
    detectgpt_check: bool,
    t6_abstract_only: bool,
    seed: int,
) -> None:
    """Scan an OA paper by DOI via Europe PMC full text (no PDF needed).

    Faster + cleaner than ``scan -f <pdf>`` when the paper is in PMC,
    because there's no PDF parsing layer. Useful for batch scanning
    biomedical OA literature.
    """
    from paperguard.fetcher.europepmc import fetch_article

    console = Console(legacy_windows=False)
    settings = get_settings()
    run_id = uuid.uuid4().hex[:12]
    audit_dir = settings.cache_dir / "audits" / run_id
    audit = AuditLog(run_id=run_id, output_dir=audit_dir)

    console.print(f"[cyan]Looking up {doi} in Europe PMC...[/]")
    article = fetch_article(doi)
    if not article:
        console.print(
            f"[yellow]{doi} not found in Europe PMC, or has no OA full text. "
            "Use `paperguard scan -f <pdf>` instead.[/]"
        )
        return

    console.print(
        f"[green]  ✓ PMC ID {article.pmcid}, "
        f"{len(article.full_text):,} chars, "
        f"{len(article.sections)} sections[/]"
    )
    audit.log_event(
        "pmc_fetched",
        {
            "doi": doi,
            "pmcid": article.pmcid,
            "n_chars": len(article.full_text),
            "n_sections": len(article.sections),
        },
    )

    registry = DetectorRegistry().register_default()
    report = AuditReport(
        paper_identifier=doi,
        paper_title=article.title,
        seed=seed,
    )

    text = article.full_text
    # T7 / T8 / T6-abstract opt-in: flip the env vars the detectors check.
    if perplexity_check or detectgpt_check or t6_abstract_only:
        import os as _os

        if perplexity_check:
            _os.environ["PAPERGUARD_PERPLEXITY_CHECK"] = "1"
        if detectgpt_check:
            _os.environ["PAPERGUARD_DETECTGPT_CHECK"] = "1"
        if t6_abstract_only:
            _os.environ["PAPERGUARD_T6_ABSTRACT_ONLY"] = "1"

    # Run the same text-detector flow on the PMC body
    text_detector_ids = ["B4", "T4", "T5", "T6"]
    if perplexity_check:
        text_detector_ids.append("T7")
    if detectgpt_check:
        text_detector_ids.append("T8")
    for d_id in text_detector_ids:
        detector = registry.get(d_id)
        if detector is None:
            continue
        result = detector.detect(text, seed=seed)
        report.detector_results.append(result)
        report.all_findings.extend(result.findings)

    # T3 still wants DataAvailabilityInput (year unknown here unless we
    # also fetch OpenAlex)
    from paperguard.detectors.t3_data_availability import (
        DataAvailabilityInput,
    )

    t3 = registry.get("T3")
    if t3 is not None:
        t3_result = t3.detect(
            DataAvailabilityInput(text=text), seed=seed
        )
        report.detector_results.append(t3_result)
        report.all_findings.extend(t3_result.findings)

    if llm_review:
        from paperguard.llm.content_review import (
            LLMContentReviewer,
            issues_to_findings,
        )

        reviewer = LLMContentReviewer()
        if not reviewer.enabled:
            console.print(
                "[yellow]--llm-review requested but "
                "PAPERGUARD_LLM_PROVIDER is not set; skipping.[/]"
            )
        else:
            with console.status(
                f"[cyan]LLM review ({reviewer.provider}) over "
                f"{len(text):,} chars..."
            ):
                issues = reviewer.review(text)
            if issues:
                llm_findings = issues_to_findings(issues)
                llm_result = DetectorResult(
                    detector_id="LLM_REVIEW",
                    applicable=True,
                    findings=llm_findings,
                )
                report.detector_results.append(llm_result)
                report.all_findings.extend(llm_findings)
                console.print(
                    f"[yellow]  LLM flagged {len(llm_findings)} "
                    f"issue(s) in the manuscript text[/]"
                )

    combine_evidence(report)
    audit.log_event(
        "evidence_combined",
        {
            "overall_severity": report.overall_severity.label,
            "total_findings": len(report.all_findings),
        },
    )
    audit.save()
    print_report(report, console, lang="en")

    if output_json:
        export_json(report, output_json)
        console.print(f"[green]JSON report saved to {output_json}[/]")


@main.command("notify")
@click.argument("patterns", nargs=-1, required=True)
@click.option(
    "--webhook",
    required=True,
    help=(
        "Slack incoming-webhook or Discord webhook URL. Auto-detected "
        "from URL host (hooks.slack.com vs discord.com/api/webhooks)."
    ),
)
@click.option(
    "--min-severity",
    type=click.Choice(["NOTE", "CONCERN", "SUSPICIOUS", "CRITICAL"]),
    default="SUSPICIOUS",
    show_default=True,
    help="Only post papers at or above this severity to the webhook.",
)
@click.option(
    "--perplexity-check",
    is_flag=True,
    default=False,
    help="Run T7 LLM-perplexity detector on each file.",
)
@click.option(
    "--detectgpt-check",
    is_flag=True,
    default=False,
    help="Run T8 DetectGPT detector on each file.",
)
@click.option("--seed", type=int, default=42, show_default=True)
def notify(
    patterns: tuple[str, ...],
    webhook: str,
    min_severity: str,
    perplexity_check: bool,
    detectgpt_check: bool,
    seed: int,
) -> None:
    """Batch-scan a glob, POST a summary of high-severity findings to a webhook.

    Designed for daily team automation. Example:

      paperguard notify "papers/*.pdf" \\
          --webhook "https://hooks.slack.com/services/T0/B0/XYZ" \\
          --min-severity SUSPICIOUS

    Pings the webhook once per `paperguard notify` run with a digest
    of all flagged papers. No HTTP call is made if no paper meets
    `--min-severity`.
    """
    import glob as glob_mod
    import os as _os_local

    if perplexity_check:
        _os_local.environ["PAPERGUARD_PERPLEXITY_CHECK"] = "1"
    if detectgpt_check:
        _os_local.environ["PAPERGUARD_DETECTGPT_CHECK"] = "1"

    import httpx

    console = Console(legacy_windows=False)
    sev_threshold = {
        "NOTE": 1,
        "CONCERN": 2,
        "SUSPICIOUS": 3,
        "CRITICAL": 4,
    }[min_severity]

    paths: list[Path] = []
    for pat in patterns:
        paths.extend(Path(p) for p in glob_mod.glob(pat))
    if not paths:
        console.print(f"[yellow]No files matched: {' '.join(patterns)}[/]")
        return

    console.print(
        f"[cyan]Scanning {len(paths)} file(s); threshold = {min_severity}[/]"
    )

    flagged: list[dict[str, object]] = []
    for p in paths:
        try:
            report = _scan_single_file(p, seed=seed)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]  ✗ {p.name}: {e}[/]")
            continue
        sev = int(report.overall_severity)
        sev_label = report.overall_severity.label
        console.print(
            f"  [{report.overall_severity.color}]{sev_label}[/] "
            f"{p.name}  ({len(report.all_findings)} findings)"
        )
        if sev >= sev_threshold:
            flagged.append(
                {
                    "file": p.name,
                    "severity": sev_label,
                    "n_findings": len(report.all_findings),
                    "top_detectors": sorted(
                        {f.detector_id for f in report.all_findings}
                    )[:6],
                }
            )

    if not flagged:
        console.print(
            f"[green]No paper at or above {min_severity}. "
            "Skipping webhook.[/]"
        )
        return

    # Build a message; auto-detect Slack vs Discord by hostname.
    host = httpx.URL(webhook).host or ""
    summary_lines = [
        f"*PaperGuard daily digest*  ·  {len(flagged)} paper(s) "
        f"≥ {min_severity}",
        "",
    ]
    for f in flagged[:30]:
        summary_lines.append(
            f"• `{f['file']}` — {f['severity']} · "
            f"{f['n_findings']} findings · "
            f"{', '.join(f['top_detectors'])}"  # type: ignore[arg-type]
        )
    if len(flagged) > 30:
        summary_lines.append(f"… and {len(flagged) - 30} more")
    summary_lines.append("")
    summary_lines.append(
        "_Disclaimer: PaperGuard flags anomalies, not fraud. "
        "Every finding includes innocent explanations. Investigate "
        "before acting._"
    )
    msg = "\n".join(summary_lines)

    if "slack.com" in host:
        payload = {"text": msg}
    elif "discord.com" in host or "discordapp.com" in host:
        payload = {"content": msg[:1900]}
    else:
        # Generic webhook: send both keys for portability
        payload = {"text": msg, "content": msg[:1900]}

    try:
        r = httpx.post(webhook, json=payload, timeout=30)
        r.raise_for_status()
        console.print(
            f"[green]✓ Webhook delivered "
            f"({len(flagged)} paper(s) reported)[/]"
        )
    except httpx.HTTPError as e:
        console.print(f"[red]Webhook POST failed: {e}[/]")


@main.command("selfcheck")
@click.option(
    "--detector",
    multiple=True,
    help="只检查指定 ID（如 --detector A1 --detector B4）；默认检查全部。",
)
def selfcheck_cmd(detector: tuple[str, ...]) -> None:
    """在内置 fixtures 上跑一次 sanity check 确认安装正确。"""
    import importlib.resources as resources

    console = Console(legacy_windows=False)
    registry = DetectorRegistry().register_default(load_plugins=False)
    all_ids = [d.id for d in registry.all()]
    selected = list(detector) if detector else all_ids

    fixtures = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
    fabricated = fixtures / "fabricated_geng_style.csv"
    genuine = fixtures / "genuine_random.csv"
    if not (fabricated.exists() and genuine.exists()):
        # 兜底：用包资源（如果安装到 site-packages 没带 tests/）
        console.print(
            "[yellow]Fixture CSVs not found; selfcheck needs the source tree.[/]"
        )
        console.print(f"[dim]Looking at: {fixtures}[/]")
        _ = resources  # silence unused
        raise click.Abort()

    console.print(
        f"[cyan]Selfcheck: {len(selected)} detector(s) on 2 fixture(s)[/]"
    )

    import pandas as pd

    fab_df = pd.read_csv(fabricated)
    gen_df = pd.read_csv(genuine)

    ok = True
    for d_id in selected:
        det = registry.get(d_id)
        if det is None:
            console.print(f"  [red]✗[/] {d_id}: not registered")
            ok = False
            continue
        # 对每个 detector 选合适输入；不适用就 SKIP
        if d_id in {"A1", "A2", "A3", "A5", "A6", "A7", "D1", "D2"}:
            r_fab = det.detect(fab_df, seed=42)
            r_gen = det.detect(gen_df, seed=42)
            fab_findings = len(r_fab.findings)
            gen_findings = len(r_gen.findings)
            status = "✓" if r_fab.applicable else "SKIP"
            color = "green" if status == "✓" else "yellow"
            console.print(
                f"  [{color}]{status}[/] {d_id}: "
                f"fabricated={fab_findings}, genuine={gen_findings}"
            )
        else:
            console.print(
                f"  [dim]·[/] {d_id}: requires specialized input (skipped in selfcheck)"
            )

    console.print(
        f"\n[{'green' if ok else 'red'}]"
        f"{'OK — installation looks healthy' if ok else 'Issues detected'}"
        "[/]"
    )


@main.command("explain")
@click.option(
    "--json",
    "report_json",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="先前 paperguard scan --output-json 产生的报告。",
)
@click.option(
    "--finding-index",
    type=int,
    default=None,
    help="只解释第 N 个 finding；不给则解释所有。",
)
def explain_cmd(report_json: Path, finding_index: int | None) -> None:
    """用 LLM 把 finding 翻译成给非专家看的语言（需 PAPERGUARD_LLM_PROVIDER）。"""
    import json as _json

    from paperguard.core.types import Finding
    from paperguard.llm.explainer import LLMExplainer

    console = Console(legacy_windows=False)
    explainer = LLMExplainer()
    if not explainer.enabled:
        console.print(
            "[yellow]LLM 解释未启用。设置 PAPERGUARD_LLM_PROVIDER="
            "openai|anthropic|ollama 并提供 API key。[/]"
        )
        raise click.Abort()

    data = _json.loads(report_json.read_text(encoding="utf-8"))
    raw_findings = data.get("all_findings", [])
    if finding_index is not None:
        if not (0 <= finding_index < len(raw_findings)):
            console.print(f"[red]finding-index 越界 (有 {len(raw_findings)} 个)[/]")
            raise click.Abort()
        targets = [raw_findings[finding_index]]
    else:
        targets = raw_findings

    for idx, fd in enumerate(targets):
        # 重建 Finding 对象（pydantic 会校验）
        try:
            finding = Finding(**fd)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Could not parse finding #{idx}: {e}[/]")
            continue
        console.print(f"\n[bold]Finding #{idx}: {finding.summary}[/bold]")
        explanation = explainer.explain(finding)
        if explanation is None:
            console.print("  [dim]LLM call failed; skipping[/]")
            continue
        console.print(f"  [cyan]Plain summary:[/] {explanation.plain_summary}")
        console.print(f"  [cyan]Lay translation:[/] {explanation.lay_translation}")


@main.command("diff")
@click.argument("before", type=click.Path(exists=True, path_type=Path))
@click.argument("after", type=click.Path(exists=True, path_type=Path))
def diff_cmd(before: Path, after: Path) -> None:
    """对比两次 paperguard scan --output-json 报告，列出新增/消失的 finding。"""
    import json as _json

    console = Console(legacy_windows=False)
    a = _json.loads(before.read_text(encoding="utf-8"))
    b = _json.loads(after.read_text(encoding="utf-8"))

    def fingerprint(f: dict[str, Any]) -> str:
        return f"{f.get('detector_id')}::{f.get('summary')}"

    a_fps = {fingerprint(f): f for f in a.get("all_findings", [])}
    b_fps = {fingerprint(f): f for f in b.get("all_findings", [])}

    added = [b_fps[k] for k in b_fps if k not in a_fps]
    removed = [a_fps[k] for k in a_fps if k not in b_fps]

    console.print(f"[bold]Diff:[/] {before.name} → {after.name}\n")
    console.print(f"  Before overall: {a.get('overall_severity')}")
    console.print(f"  After overall:  {b.get('overall_severity')}\n")

    if not added and not removed:
        console.print("[green]No changes in findings.[/]")
        return

    if added:
        console.print(f"[red]+ {len(added)} new findings:[/]")
        for f in added:
            console.print(f"    + [{f.get('detector_id')}] {f.get('summary')}")
    if removed:
        console.print(f"\n[green]- {len(removed)} resolved findings:[/]")
        for f in removed:
            console.print(f"    - [{f.get('detector_id')}] {f.get('summary')}")


@main.command("list-detectors")
@click.option("--cluster", default=None, help="Only list detectors in this cluster.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "ids"]),
    default="table",
    show_default=True,
)
def list_detectors_cmd(cluster: str | None, fmt: str) -> None:
    """List all registered detectors (built-in + plugins)."""
    console = Console(legacy_windows=False)
    registry = DetectorRegistry().register_default()
    detectors = registry.all()
    if cluster:
        detectors = [d for d in detectors if d.assumption_cluster == cluster]

    if fmt == "ids":
        for d in detectors:
            click.echo(d.id)
        return
    if fmt == "json":
        import json as _json

        click.echo(
            _json.dumps(
                [
                    {
                        "id": d.id,
                        "name": d.name,
                        "description": d.description,
                        "cluster": d.assumption_cluster,
                        "data_requirements": d.data_requirements,
                        "academic_basis": d.academic_basis,
                    }
                    for d in detectors
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    tbl = Table(show_header=True, header_style="bold")
    tbl.add_column("ID", width=5)
    tbl.add_column("Name", max_width=40)
    tbl.add_column("Cluster", max_width=25)
    tbl.add_column("Data requirements", max_width=35)
    for d in detectors:
        tbl.add_row(
            d.id, d.name, d.assumption_cluster, ", ".join(d.data_requirements)
        )
    console.print(tbl)
    console.print(f"\n[dim]{len(detectors)} detector(s).[/]")


@main.command("fetch-rw")
@click.option(
    "--url",
    default="https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv",
    show_default=True,
    help="Retraction Watch CSV URL.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path. Default: <cache_dir>/retraction_watch.csv.",
)
def fetch_rw_cmd(url: str, out: Path | None) -> None:
    """Download a fresh Retraction Watch CSV snapshot to local cache."""
    import httpx

    console = Console(legacy_windows=False)
    settings = get_settings()
    dst = out or settings.cache_dir / "retraction_watch.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]Downloading {url}...[/]")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as r:
            r.raise_for_status()
            with dst.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    except httpx.HTTPError as e:
        console.print(f"[red]Download failed: {e}[/]")
        raise click.Abort() from e
    console.print(
        f"[green]Saved {dst} ({dst.stat().st_size / 1024:.1f} KB).[/]\n"
        f"[dim]Use it with: paperguard.fetcher.retraction_watch."
        f"lookup_retraction(doi, Path('{dst}'))[/]"
    )


@main.command("fetch-ori")
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path. Default: <cache_dir>/ori_sanctions.csv.",
)
def fetch_ori_cmd(out: Path | None) -> None:
    """Create a template ORI sanctions CSV (you must fill it in manually).

    PaperGuard does not scrape ORI's HTML pages (HTML changes break scrapers).
    Curate the CSV from https://ori.hhs.gov/case-summaries.
    """
    console = Console(legacy_windows=False)
    settings = get_settings()
    dst = out or settings.cache_dir / "ori_sanctions.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        console.print(f"[yellow]{dst} already exists; not overwriting.[/]")
        return
    template = (
        "Name,Institution,ActionDate,ActionEnd,Findings,URL\n"
        "# Example row (delete this line + fill from "
        "https://ori.hhs.gov/case-summaries):\n"
        "# Doe Jane,Example U,2024-01-15,2027-01-15,Falsification,"
        "https://ori.hhs.gov/case/jane-doe\n"
    )
    dst.write_text(template, encoding="utf-8")
    console.print(
        f"[green]Wrote template {dst}.[/]\n"
        "[dim]Now fill in real entries from "
        "https://ori.hhs.gov/case-summaries[/]"
    )


DEFAULT_AI_DICT_URL = (
    "https://raw.githubusercontent.com/exergyleizhou-ux/PaperGuard/"
    "main/docs/dictionaries/llm_phrases_v1.json"
)


@main.command("refresh-ai-dict")
@click.option(
    "--source",
    "source_url",
    default=None,
    help=(
        "URL serving a JSON document shaped "
        "{\"phrases\": {\"gpt\": [...], \"claude\": [...], "
        "\"gemini\": [...], \"other\": [...]}}. "
        "If omitted (and no --corpus), defaults to the PaperGuard "
        f"official dictionary at {DEFAULT_AI_DICT_URL}."
    ),
)
@click.option(
    "--official",
    "use_official",
    is_flag=True,
    default=False,
    help=(
        "Shortcut: pull from the official PaperGuard dictionary URL "
        "(same as --source <default>)."
    ),
)
@click.option(
    "--corpus",
    "corpus_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help=(
        "Path to a text file of suspected LLM output. "
        "Candidate 2-4-gram phrases are extracted and merged "
        "into the user dictionary."
    ),
)
@click.option(
    "--provider",
    type=click.Choice(("gpt", "claude", "gemini", "other")),
    default="other",
    show_default=True,
    help="Provider bucket to assign --corpus candidates to.",
)
@click.option(
    "--min-count",
    type=int,
    default=3,
    show_default=True,
    help="Minimum corpus occurrences for an n-gram to be a candidate.",
)
@click.option(
    "--min-per-million",
    type=float,
    default=200.0,
    show_default=True,
    help="Minimum per-million-token frequency for an n-gram to be a candidate.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show the diff but do not write to disk.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom output path. Defaults to ~/.paperguard/ai_dictionary.json.",
)
@click.option(
    "--auto",
    is_flag=True,
    default=False,
    help=(
        "Auto-refresh mode: only pulls from the official URL when "
        "the local dictionary is missing OR older than --max-age-days. "
        "Otherwise prints 'still fresh' and exits 0. Useful in cron / "
        "CI pre-flight checks."
    ),
)
@click.option(
    "--max-age-days",
    type=float,
    default=7.0,
    show_default=True,
    help="Used with --auto. Refresh only if local dict is older than this.",
)
def refresh_ai_dict_cmd(
    source_url: str | None,
    use_official: bool,
    corpus_path: Path | None,
    provider: str,
    min_count: int,
    min_per_million: float,
    dry_run: bool,
    out: Path | None,
    auto: bool,
    max_age_days: float,
) -> None:
    """Refresh the T6 user dictionary from a remote JSON URL or local corpus.

    The dictionary is additive — built-in phrases stay in effect; the user
    dictionary only **adds** more. Run this command periodically (or when a
    new LLM tic shows up) to keep T6 current.
    """
    import datetime as _dt

    from paperguard.llm.dynamic_dictionary import (
        DictionarySnapshot,
        diff_snapshots,
        load_user_dictionary,
        merge_snapshots,
        refresh_from_corpus,
        refresh_from_url,
        save_user_dictionary,
    )

    console = Console(legacy_windows=False)

    if use_official and not source_url:
        source_url = DEFAULT_AI_DICT_URL

    if not source_url and not corpus_path:
        # Default to the official URL when nothing else specified.
        source_url = DEFAULT_AI_DICT_URL
        console.print(
            "[dim]No --source / --corpus given; using official "
            f"PaperGuard dictionary at {source_url}[/]"
        )

    # --auto mode: skip the refresh if the local dict is recent.
    if auto:
        from paperguard.llm.dynamic_dictionary import (
            _default_dictionary_path,
        )

        dict_path = out or _default_dictionary_path()
        if dict_path.exists():
            current_snap = load_user_dictionary(dict_path)
            generated = current_snap.generated_at
            try:
                gen_dt = _dt.datetime.fromisoformat(generated)
                age_days = (
                    _dt.datetime.now(_dt.UTC) - gen_dt
                ).total_seconds() / 86400.0
                if age_days < max_age_days:
                    console.print(
                        f"[green]Dictionary at {dict_path} is "
                        f"{age_days:.2f} days old (< {max_age_days} "
                        f"threshold); skipping refresh.[/]"
                    )
                    return
                console.print(
                    f"[yellow]Dictionary is {age_days:.1f} days old "
                    f"(≥ {max_age_days}); refreshing...[/]"
                )
            except (ValueError, TypeError):
                console.print(
                    "[yellow]Could not parse generated_at; refreshing.[/]"
                )
        else:
            console.print(
                f"[yellow]No dictionary at {dict_path}; refreshing.[/]"
            )

    current = load_user_dictionary(out)
    incoming: list[DictionarySnapshot] = []

    if source_url:
        console.print(f"[cyan]Fetching dictionary from {source_url}...[/]")
        try:
            incoming.append(refresh_from_url(source_url))
        except RuntimeError as e:
            console.print(f"[red]Source fetch failed: {e}[/]")
            raise click.Abort() from e

    if corpus_path:
        console.print(
            f"[cyan]Extracting candidates from {corpus_path} → "
            f"provider={provider}...[/]"
        )
        text = corpus_path.read_text(encoding="utf-8", errors="ignore")
        incoming.append(
            refresh_from_corpus(
                text,
                provider=provider,
                min_count=min_count,
                min_per_million=min_per_million,
            )
        )

    merged = merge_snapshots(current, *incoming)
    diff = diff_snapshots(current, merged)

    console.print("[bold]Dictionary diff:[/]")
    for line in diff.summary_lines():
        console.print(line)

    if dry_run:
        console.print("[yellow]--dry-run: not writing.[/]")
        return
    if diff.is_empty:
        console.print("[dim]No changes — leaving disk file untouched.[/]")
        return

    merged.source = source_url or "corpus"
    path = save_user_dictionary(merged, out)
    console.print(f"[green]Wrote {path}.[/]")
    console.print(
        "[dim]The next paperguard scan will pick up the new phrases "
        "automatically (T6 detector lazy-loads on import).[/]"
    )


@main.command()
@click.option("--author", required=True, help="作者姓名。")
@click.option("--affiliation", default="", help="机构名过滤（模糊匹配）。")
@click.option("--year-from", type=int, default=None)
@click.option("--year-to", type=int, default=None)
@click.option("--limit", type=int, default=20, show_default=True)
def search(
    author: str,
    affiliation: str,
    year_from: int | None,
    year_to: int | None,
    limit: int,
) -> None:
    """通过作者名搜索论文。"""
    console = Console(legacy_windows=False)
    settings = get_settings()
    oa = OpenAlexClient(email=settings.email)
    try:
        works = oa.search_works(
            author=author,
            institution=affiliation,
            year_from=year_from,
            year_to=year_to,
            per_page=limit,
        )
        if not works:
            console.print("[yellow]No works found.[/]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("Year", width=6)
        table.add_column("Title")
        table.add_column("Venue", max_width=30)
        table.add_column("DOI", max_width=40)
        for w in works:
            title = (w.get("title") or w.get("display_name") or "")[:80]
            year = str(w.get("publication_year") or "")
            primary = w.get("primary_location") or {}
            source = primary.get("source") or {}
            venue = (source.get("display_name") or "")[:30]
            doi = (w.get("doi") or "").replace("https://doi.org/", "")
            table.add_row(year, title, venue, doi)
        console.print(table)
    finally:
        oa.close()


@main.command("search-cn")
@click.argument("query")
@click.option(
    "--year",
    default=None,
    help="Year filter, e.g. '2020' or '2018-2023'.",
)
@click.option(
    "--limit",
    "max_results",
    default=20,
    show_default=True,
    help="Max results to show.",
)
@click.option(
    "--output-json",
    type=click.Path(path_type=Path),
    default=None,
    help="Write results as JSON to this path.",
)
def search_cn(
    query: str,
    year: str | None,
    max_results: int,
    output_json: Path | None,
) -> None:
    """Search Chinese & multilingual papers via Semantic Scholar.

    Accepts Chinese or English queries. Results include DOI, title,
    authors, venue, year, citation count, and open-access status.
    Papers with DOIs can be scanned with ``paperguard scan <file>``.
    """
    import json as _json

    console = Console(legacy_windows=False)
    client = SemanticScholarClient()
    try:
        with console.status("[bold]Searching Semantic Scholar…[/]"):
            papers = client.search(query, limit=max_results, year=year)
    finally:
        client.close()

    if not papers:
        console.print("[yellow]No papers found for this query.[/]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Year", width=6)
    table.add_column("Title", max_width=50)
    table.add_column("Authors", max_width=30)
    table.add_column("DOI", width=25)
    table.add_column("Cite", justify="right", width=5)
    table.add_column("OA", width=3)

    for p in papers:
        authors_str = ", ".join(p.authors[:3])
        if len(p.authors) > 3:
            authors_str += " et al."
        table.add_row(
            str(p.year or ""),
            p.title[:50],
            authors_str[:30],
            p.doi[:25] if p.doi else "-",
            str(p.citation_count),
            "Y" if p.is_open_access else "",
        )
    console.print(table)
    console.print(f"[dim]{len(papers)} results[/]")

    if output_json:
        payload = [
            {
                "paper_id": p.paper_id,
                "title": p.title,
                "doi": p.doi,
                "authors": p.authors,
                "year": p.year,
                "venue": p.venue,
                "citation_count": p.citation_count,
                "is_open_access": p.is_open_access,
            }
            for p in papers
        ]
        output_json.write_text(
            _json.dumps(payload, indent=2, ensure_ascii=False),
        )
        console.print(f"JSON written to {output_json}")


@main.command()
@click.argument("name")
@click.option("--affiliation", default=None, help="机构名过滤。")
def who(name: str, affiliation: str | None) -> None:
    """ORCID 作者消歧 — 按姓名搜索 ORCID 候选人。"""
    import asyncio as _asyncio

    console = Console(legacy_windows=False)
    with console.status("[bold]Searching ORCID…[/]"):
        candidates: list[OrcidCandidate] = _asyncio.run(
            disambiguate_author(name, affiliation)
        )
    if not candidates:
        console.print("[yellow]No candidates found.[/]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ORCID", width=20)
    table.add_column("Name")
    table.add_column("Affiliation(s)")
    table.add_column("Works", justify="right", width=6)
    for c in candidates:
        table.add_row(
            c.orcid_id,
            c.name,
            ", ".join(c.affiliations) if c.affiliations else "-",
            str(c.works_count),
        )
    console.print(table)


@main.command("scan-name")
@click.argument("name")
@click.option("--affiliation", default=None, help="Filter ORCID candidates by affiliation.")
@click.option("--pick", default=1, show_default=True, help="Pick the Nth candidate (1-based).")
@click.option("--max-papers", default=20, show_default=True, help="Max papers to scan.")
@click.option(
    "--output-json",
    type=click.Path(path_type=Path),
    default=None,
    help="Write aggregated JSON report to this path.",
)
def scan_name(
    name: str,
    affiliation: str | None,
    pick: int,
    max_papers: int,
    output_json: Path | None,
) -> None:
    """Auto-fetch: disambiguate author by name, then batch-scan papers.

    Combines ORCID disambiguation (W10) with batch author audit (W7)
    into a single command.  Resolves the author name to an ORCID ID,
    then fetches works via OpenAlex, downloads OA PDFs, and runs the
    full PaperGuard pipeline on each.
    """
    import asyncio as _asyncio

    console = Console(legacy_windows=False)
    console.print(f"[bold]Resolving author: {name}[/]")

    with console.status("[bold]Searching ORCID…[/]"):
        candidates: list[OrcidCandidate] = _asyncio.run(
            disambiguate_author(name, affiliation),
        )

    if not candidates:
        console.print("[yellow]No ORCID candidates found for this name.[/]")
        return

    if pick < 1 or pick > len(candidates):
        console.print(f"[red]--pick {pick} out of range (1–{len(candidates)}).[/]")
        raise SystemExit(1)

    chosen = candidates[pick - 1]
    console.print(
        f"[green]Selected:[/] {chosen.name}  ORCID {chosen.orcid_id}"
        f"  ({chosen.works_count} works)",
    )

    # Delegate to scan_author logic via its Click context
    ctx = click.get_current_context()
    ctx.invoke(
        scan_author,
        orcid_id=chosen.orcid_id,
        max_papers=max_papers,
        output_json=output_json,
    )


@main.command("scan-author")
@click.argument("orcid_id")
@click.option("--max-papers", default=20, show_default=True, help="Max papers to scan.")
@click.option(
    "--output-json",
    type=click.Path(path_type=Path),
    default=None,
    help="Write aggregated JSON report to this path.",
)
def scan_author(orcid_id: str, max_papers: int, output_json: Path | None) -> None:
    """Batch-scan an author's papers by ORCID ID.

    Fetches the author's works via OpenAlex, downloads OA PDFs,
    runs the full PaperGuard pipeline on each, and prints an
    aggregated summary.
    """
    import json as _json
    import tempfile

    console = Console(legacy_windows=False)
    console.print(f"[bold]Scanning author ORCID {orcid_id}…[/]")

    try:
        oal = OpenAlexClient()
        works = oal.get_author_works(
            f"https://orcid.org/{orcid_id}", per_page=max_papers,
        )
        oal.close()
    except Exception as exc:
        console.print(f"[red]OpenAlex query failed: {exc}[/]")
        raise SystemExit(1) from exc

    if not works:
        console.print("[yellow]No works found for this ORCID.[/]")
        return

    console.print(f"Found {len(works)} works. Downloading OA PDFs…")

    all_findings: list[dict[str, object]] = []
    scanned = 0
    skipped = 0

    with tempfile.TemporaryDirectory(prefix="pg_author_") as tmpdir:
        for i, work in enumerate(works[:max_papers]):
            doi: str = (work.get("doi") or "").replace("https://doi.org/", "")
            title: str = work.get("title") or f"work-{i}"
            if not doi:
                skipped += 1
                continue

            oa_url: str | None = None
            oa_loc = work.get("best_oa_location") or {}
            if isinstance(oa_loc, dict):
                oa_url = oa_loc.get("pdf_url") or oa_loc.get("url_for_pdf")

            dest = Path(tmpdir) / f"{doi.replace('/', '_')}.pdf"
            try:
                result = fetch_oa_pdf(doi, dest, openalex_oa_url=oa_url)
            except Exception:
                skipped += 1
                continue

            if not result.success:
                skipped += 1
                continue

            console.print(f"  [{i+1}/{len(works)}] {title[:60]}… ", end="")
            try:
                report = _scan_single_file(dest, seed=42)
                n = len(report.all_findings)
                sev = report.overall_severity
                console.print(f"[green]{n} findings, severity {sev}[/]")
                for f in report.all_findings:
                    entry: dict[str, object] = {
                        "doi": doi,
                        "title": title,
                        "detector_id": f.detector_id,
                        "severity": f.severity.value,
                        "summary": f.summary,
                    }
                    all_findings.append(entry)
                scanned += 1
            except Exception as exc:
                console.print(f"[red]error: {exc}[/]")
                skipped += 1

    # Summary
    console.print()
    console.print(
        f"[bold]Author scan complete:[/] {scanned} scanned, {skipped} skipped",
    )
    if all_findings:
        table = Table(show_header=True, header_style="bold")
        table.add_column("DOI", width=30)
        table.add_column("Detector")
        table.add_column("Sev", width=4)
        table.add_column("Summary")
        for row in all_findings:
            table.add_row(
                str(row["doi"])[:30],
                str(row["detector_id"]),
                str(row["severity"]),
                str(row["summary"])[:60],
            )
        console.print(table)
    else:
        console.print("[green]No anomalies detected across scanned papers.[/]")

    if output_json:
        payload = {
            "orcid_id": orcid_id,
            "papers_scanned": scanned,
            "papers_skipped": skipped,
            "total_findings": len(all_findings),
            "findings": all_findings,
        }
        output_json.write_text(
            _json.dumps(payload, indent=2, ensure_ascii=False),
        )
        console.print(f"JSON report written to {output_json}")


@main.command("scan-industrial")
@click.argument(
    "file_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--domain",
    type=click.Choice(
        [
            "wastewater", "waste_gas", "distillers_grain", "chemical",
            "pharma", "food", "semiconductor", "environment",
            "medical", "agriculture", "biopharma", "biocomputation",
        ],
        case_sensitive=False,
    ),
    required=True,
    help="Industrial-sector template name. Determines column-name "
    "expectations, balance tolerance, SCADA period, and narrative field.",
)
@click.option(
    "--output-json",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional JSON output path for the audit report.",
)
@click.option(
    "--narrative-column",
    default=None,
    help="Override the template's narrative column for I5.",
)
@click.option(
    "--id-column",
    default=None,
    help="Override the template's batch-id column for I5.",
)
@click.option(
    "--timestamp-column",
    default=None,
    help="Override the template's timestamp column for I2.",
)
@click.option(
    "--tolerance-pct",
    type=float,
    default=None,
    help="Override the template's I1 mass-balance tolerance (% units).",
)
def scan_industrial_cmd(
    file_path: Path,
    domain: str,
    output_json: Path | None,
    narrative_column: str | None,
    id_column: str | None,
    timestamp_column: str | None,
    tolerance_pct: float | None,
) -> None:
    """Scan an industrial CSV / Excel / HDF5 with I1 + I2 + I5 using a
    pre-configured domain template.

    Examples:

      paperguard scan-industrial --domain wastewater plant_2026Q1.csv
      paperguard scan-industrial --domain pharma batch_records.xlsx --tolerance-pct 0.3
      paperguard scan-industrial --domain semiconductor fab_log.h5 \\
          --narrative-column recipe_log --id-column lot_id
    """
    import pandas as pd

    from paperguard.detectors.i1_mass_balance import I1MassBalanceDetector
    from paperguard.detectors.i2_timestamp_integrity import (
        I2TimestampIntegrityDetector,
    )
    from paperguard.detectors.i5_batch_repetition import (
        I5BatchRepetitionDetector,
    )
    from paperguard.industrial import get_template

    console = Console(legacy_windows=False)
    template = get_template(domain.lower())

    # Load DataFrame
    suffix = file_path.suffix.lower()
    if suffix in (".csv", ".tsv"):
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(file_path, sep=sep)
    elif suffix in (".xlsx", ".xlsm"):
        df = pd.read_excel(file_path)
    elif suffix in (".h5", ".hdf5"):
        from paperguard.extractor.hdf5_io import extract_hdf5_tables

        tables = extract_hdf5_tables(file_path)
        if not tables:
            console.print(
                f"[red]No tabular leaves found in {file_path}[/]"
            )
            raise click.Abort()
        # Use the largest table by row count as the primary one
        primary_key = max(tables, key=lambda k: len(tables[k]))
        df = tables[primary_key]
        console.print(
            f"[dim]HDF5 has {len(tables)} datasets; using {primary_key!r} "
            f"({len(df)} rows).[/]"
        )
    else:
        console.print(
            f"[red]Unsupported file type {suffix}; expected csv/tsv/xlsx/h5[/]"
        )
        raise click.Abort()

    console.print(
        f"[cyan]Loaded {len(df)} rows × {len(df.columns)} cols from "
        f"{file_path.name}[/]"
    )
    console.print(
        f"[dim]Domain = {template.name}  "
        f"(tolerance = {template.tolerance_pct}%, "
        f"expected Δt = {template.expected_dt_seconds}s)[/]"
    )

    overrides_i1: dict[str, object] = {}
    if tolerance_pct is not None:
        overrides_i1["tolerance_pct"] = tolerance_pct

    overrides_i2: dict[str, object] = {}
    if timestamp_column is not None:
        overrides_i2["timestamp_column"] = timestamp_column

    overrides_i5: dict[str, object] = {}
    if narrative_column is not None:
        overrides_i5["narrative_column"] = narrative_column
    if id_column is not None:
        overrides_i5["id_column"] = id_column

    all_findings: list[Finding] = []

    # --- I1 ---
    console.print("\n[bold]I1 — Mass / Energy Balance[/]")
    try:
        i1_input = template.mass_balance(df, **overrides_i1)
        ok, reason = I1MassBalanceDetector().check_applicability(i1_input)
        if not ok:
            console.print(f"  [yellow]Skipped: {reason}[/]")
        else:
            r1 = I1MassBalanceDetector().detect(i1_input)
            for f in r1.findings:
                _print_finding(console, f)
            all_findings.extend(r1.findings)
            if not r1.findings:
                console.print("  [green]No balance violations.[/]")
    except Exception as e:  # noqa: BLE001
        console.print(f"  [red]I1 failed: {type(e).__name__}: {e}[/]")

    # --- I2 ---
    console.print("\n[bold]I2 — SCADA Timestamp Integrity[/]")
    try:
        i2_input = template.timestamp_integrity(df, **overrides_i2)
        ok, reason = I2TimestampIntegrityDetector().check_applicability(i2_input)
        if not ok:
            console.print(f"  [yellow]Skipped: {reason}[/]")
        else:
            r2 = I2TimestampIntegrityDetector().detect(i2_input)
            for f in r2.findings:
                _print_finding(console, f)
            all_findings.extend(r2.findings)
            if not r2.findings:
                console.print("  [green]No timestamp anomalies.[/]")
    except Exception as e:  # noqa: BLE001
        console.print(f"  [red]I2 failed: {type(e).__name__}: {e}[/]")

    # --- I5 ---
    console.print("\n[bold]I5 — Batch-Log Narrative Repetition[/]")
    try:
        i5_input = template.batch_repetition(df, **overrides_i5)
        ok, reason = I5BatchRepetitionDetector().check_applicability(i5_input)
        if not ok:
            console.print(f"  [yellow]Skipped: {reason}[/]")
        else:
            r5 = I5BatchRepetitionDetector().detect(i5_input)
            for f in r5.findings:
                _print_finding(console, f)
            all_findings.extend(r5.findings)
            if not r5.findings:
                console.print("  [green]No repetition flagged.[/]")
    except Exception as e:  # noqa: BLE001
        console.print(f"  [red]I5 failed: {type(e).__name__}: {e}[/]")

    console.print(
        f"\n[bold]Summary:[/] {len(all_findings)} finding(s) across "
        f"I1 + I2 + I5. PaperGuard does not use verdict language. "
        f"Each finding ships with innocent explanations."
    )

    if output_json:
        import json as _json

        payload = {
            "file": str(file_path),
            "domain": template.name,
            "n_rows": len(df),
            "n_columns": len(df.columns),
            "findings": [
                {
                    "detector_id": f.detector_id,
                    "severity": f.severity.name,
                    "summary": f.summary,
                    "detail": f.detail,
                    "test_statistic": f.test_statistic,
                    "evidence": f.evidence,
                    "innocent_explanations": f.innocent_explanations,
                }
                for f in all_findings
            ],
        }
        output_json.write_text(
            _json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        console.print(f"[green]JSON report saved to {output_json}[/]")


def _print_finding(console: Console, f: Finding) -> None:
    sev = f.severity
    console.print(
        f"  [{sev.color}]{sev.label}[/]  {f.summary}"
    )


@main.command("doctor")
@click.option(
    "--ping-llm",
    is_flag=True,
    default=False,
    help=(
        "Also probe the configured LLM endpoint with a 1-token call to verify "
        "connectivity. Off by default to avoid spending API quota."
    ),
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output machine-readable JSON instead of human-readable lines.",
)
def doctor_cmd(ping_llm: bool, as_json: bool) -> None:
    """Diagnose your PaperGuard install: deps, config, connectivity, paths.

    Exits with code 0 when everything checked passes, 1 if any check is RED,
    and 2 if any check is YELLOW (non-fatal warning). Useful in CI as a
    pre-flight before batch scanning.
    """
    import json as _json
    import os as _os
    import platform
    import sys as _sys

    from paperguard import __version__ as pg_version

    console = Console(legacy_windows=False)
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    # 1) Python version
    py = _sys.version_info
    py_ok = (py.major, py.minor) >= (3, 11)
    add(
        "python_version",
        "GREEN" if py_ok else "RED",
        f"{py.major}.{py.minor}.{py.micro} (need ≥ 3.11)",
    )

    # 2) PaperGuard version
    add("paperguard_version", "GREEN", pg_version)

    # 3) Platform
    add("platform", "GREEN", f"{platform.system()} {platform.machine()}")

    # 4) Optional dependencies
    deps_required = ["click", "rich", "pydantic", "pandas", "scipy", "httpx"]
    deps_optional = [
        "pymupdf", "pdfplumber", "openpyxl", "cv2", "imagehash",
        "networkx", "Bio",
    ]
    for mod in deps_required:
        try:
            __import__(mod)
            add(f"dep:{mod}", "GREEN", "installed")
        except ImportError:
            add(f"dep:{mod}", "RED", "MISSING — pip install paperguard[dev]")
    for mod in deps_optional:
        try:
            __import__(mod)
            add(f"opt:{mod}", "GREEN", "installed")
        except ImportError:
            add(
                f"opt:{mod}",
                "YELLOW",
                "optional — some detectors will skip",
            )

    # 5) Detector registry
    try:
        registry = DetectorRegistry().register_default(load_plugins=False)
        n = len(registry.all())
        add(
            "registry",
            "GREEN" if n >= 33 else "YELLOW",
            f"{n} built-in detector(s) registered (expected ≥ 33)",
        )
    except Exception as e:  # noqa: BLE001
        add("registry", "RED", f"registry init failed: {type(e).__name__}: {e}")

    # 6) Plugin entry points
    try:
        plugin_ids = DetectorRegistry().load_plugins()
        add(
            "plugins",
            "GREEN",
            f"{len(plugin_ids)} third-party detector(s) loaded via entry points",
        )
    except Exception as e:  # noqa: BLE001
        add("plugins", "YELLOW", f"plugin discovery failed: {type(e).__name__}")

    # 7) Cache dir writability
    try:
        settings = get_settings()
        cache = settings.cache_dir
        cache.mkdir(parents=True, exist_ok=True)
        probe = cache / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        add("cache_dir", "GREEN", f"writable: {cache}")
    except Exception as e:  # noqa: BLE001
        add("cache_dir", "RED", f"NOT writable: {type(e).__name__}: {e}")

    # 8) Dynamic T6 dictionary
    try:
        from paperguard.llm.dynamic_dictionary import (
            _default_dictionary_path,
            load_user_dictionary,
        )

        dict_path = _default_dictionary_path()
        if dict_path.exists():
            snap = load_user_dictionary()
            n_phrases = sum(len(v) for v in snap.phrases.values())
            add(
                "t6_dictionary",
                "GREEN",
                f"{dict_path} ({n_phrases} user phrases, "
                f"generated {snap.generated_at or 'unknown'})",
            )
        else:
            add(
                "t6_dictionary",
                "YELLOW",
                f"no user dictionary at {dict_path}; "
                "T6 uses built-in phrases only. Run "
                "`paperguard refresh-ai-dict --official` to fetch one.",
            )
    except Exception as e:  # noqa: BLE001
        add("t6_dictionary", "YELLOW", f"check failed: {type(e).__name__}")

    # 9) F4 image corpus DB (optional)
    try:
        corpus_path = (
            Path(_os.environ.get("PAPERGUARD_HOME", str(Path.home() / ".paperguard")))
            / "image_corpus.db"
        )
        if corpus_path.exists():
            size_kb = corpus_path.stat().st_size / 1024
            add(
                "f4_image_corpus",
                "GREEN",
                f"{corpus_path} ({size_kb:,.0f} KB)",
            )
        else:
            add(
                "f4_image_corpus",
                "YELLOW",
                f"no corpus at {corpus_path}; F4 will auto-build on first scan",
            )
    except Exception:  # noqa: BLE001
        add("f4_image_corpus", "YELLOW", "could not stat corpus path")

    # 10) Redis backend for multi-tenant Web UI rate-limiting
    redis_url = _os.environ.get("PAPERGUARD_REDIS_URL", "")
    if not redis_url:
        add(
            "webui_redis",
            "YELLOW",
            "PAPERGUARD_REDIS_URL unset; webui uses InMemoryBackend "
            "for rate-limiting (NOT safe for multi-worker deployments)",
        )
    else:
        try:
            from paperguard.webui.ratelimit import RedisBackend

            backend = RedisBackend.from_url(redis_url)
            decision = backend.hit(
                "doctor-probe", max_requests=100, window_seconds=60
            )
            assert decision.allowed
            add(
                "webui_redis",
                "GREEN",
                f"Redis backend reachable at {redis_url}",
            )
        except Exception as e:  # noqa: BLE001
            add(
                "webui_redis",
                "RED",
                f"PAPERGUARD_REDIS_URL set but unreachable: "
                f"{type(e).__name__}: {e}",
            )

    # 11) LLM endpoint config (no API call by default)
    provider = _os.environ.get("PAPERGUARD_LLM_PROVIDER", "")
    base_url = _os.environ.get("PAPERGUARD_LLM_BASE_URL", "(default)")
    model = _os.environ.get("PAPERGUARD_LLM_MODEL", "(default)")
    api_key_present = bool(_os.environ.get("OPENAI_API_KEY"))
    if provider:
        add(
            "llm_config",
            "GREEN" if api_key_present else "YELLOW",
            f"provider={provider} base_url={base_url} model={model} "
            f"OPENAI_API_KEY={'set' if api_key_present else 'unset'}",
        )
    else:
        add(
            "llm_config",
            "YELLOW",
            "no PAPERGUARD_LLM_PROVIDER set; T7 / T8 / --llm-review "
            "will skip silently. Set provider + OPENAI_API_KEY to enable.",
        )

    # 11) Optional: LLM connectivity ping
    if ping_llm:
        if not api_key_present:
            add(
                "llm_ping",
                "YELLOW",
                "skipped — no OPENAI_API_KEY",
            )
        else:
            try:
                import httpx as _httpx

                base = base_url if base_url != "(default)" else "https://api.openai.com/v1"
                r = _httpx.post(
                    f"{base.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {_os.environ['OPENAI_API_KEY']}"},
                    json={
                        "model": model if model != "(default)" else "gpt-4o-mini",
                        "messages": [{"role": "user", "content": "Reply OK."}],
                        "max_tokens": 5,
                        "temperature": 0,
                    },
                    timeout=20.0,
                )
                r.raise_for_status()
                data = r.json()
                content = (data.get("choices") or [{}])[0].get(
                    "message", {}
                ).get("content", "")
                logprobs_field = (
                    (data.get("choices") or [{}])[0].get("logprobs") is not None
                )
                add(
                    "llm_ping",
                    "GREEN",
                    f"endpoint reachable, content={content!r}, "
                    f"logprobs_supported={logprobs_field}",
                )
            except Exception as e:  # noqa: BLE001
                add("llm_ping", "RED", f"{type(e).__name__}: {e}")

    # 12) Summary
    red = sum(1 for c in checks if c["status"] == "RED")
    yellow = sum(1 for c in checks if c["status"] == "YELLOW")
    green = sum(1 for c in checks if c["status"] == "GREEN")

    if as_json:
        click.echo(_json.dumps(
            {
                "summary": {"green": green, "yellow": yellow, "red": red},
                "checks": checks,
            },
            indent=2,
        ))
    else:
        color_map = {"GREEN": "green", "YELLOW": "yellow", "RED": "red bold"}
        mark_map = {"GREEN": "✓", "YELLOW": "~", "RED": "✗"}
        console.print("[bold]PaperGuard doctor[/]")
        for c in checks:
            mark = mark_map[c["status"]]
            color = color_map[c["status"]]
            console.print(f"  [{color}]{mark}[/] {c['name']:24} {c['detail']}")
        console.print(
            f"\n[bold]Summary:[/] "
            f"[green]{green} green[/] / "
            f"[yellow]{yellow} yellow[/] / "
            f"[red]{red} red[/]"
        )

    if red > 0:
        raise click.exceptions.Exit(1)
    if yellow > 0:
        raise click.exceptions.Exit(2)


if __name__ == "__main__":
    main()
