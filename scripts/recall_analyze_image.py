"""Compute F1/F4 LR+ at multiple thresholds and print a Markdown report.

Usage:
    python scripts/recall_analyze_image.py scripts/recall_image_v1_results.json
        > docs/recall_image_v1.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_SEVERITIES = ("CRITICAL", "SUSPICIOUS", "CONCERN", "none")


def _severity_rank(sev: str) -> int:
    order = {"CRITICAL": 4, "SUSPICIOUS": 3, "CONCERN": 2, "none": 1}
    return order.get(sev, 0)


def _at_least(sev: str, threshold: str) -> bool:
    return _severity_rank(sev) >= _severity_rank(threshold)


def _lr_plus_table(
    records: list[dict[str, Any]], field: str, label: str
) -> str:
    lines = [f"### {label} LR+ table\n"]
    lines.append(
        "| Threshold | TPR (retracted) | FPR (control) | LR+ | n_ret | n_ctrl |"
    )
    lines.append("|---|---|---|---|---|---|")
    for thr in ("CRITICAL", "SUSPICIOUS", "CONCERN"):
        ret = [
            r for r in records
            if r["arm"] == "retracted" and r["pdf_ok"] and r["n_images"] >= 2
        ]
        ctrl = [
            r for r in records
            if r["arm"] == "control" and r["pdf_ok"] and r["n_images"] >= 2
        ]
        if not ret or not ctrl:
            lines.append(f"| ≥ {thr} | (insufficient data) | — | — | {len(ret)} | {len(ctrl)} |")
            continue
        tp = sum(1 for r in ret if _at_least(r[field], thr))
        fp = sum(1 for r in ctrl if _at_least(r[field], thr))
        tpr = tp / len(ret) if ret else 0.0
        fpr = fp / len(ctrl) if ctrl else 0.0
        if fpr == 0:
            lr_str = "∞" if tpr > 0 else "—"
        else:
            lr_str = f"{tpr / fpr:.2f}"
        lines.append(
            f"| ≥ {thr} | {tpr * 100:.1f}% ({tp}/{len(ret)}) | "
            f"{fpr * 100:.1f}% ({fp}/{len(ctrl)}) | {lr_str} | "
            f"{len(ret)} | {len(ctrl)} |"
        )
    return "\n".join(lines)


def _hamming_distribution(records: list[dict[str, Any]], field: str) -> str:
    lines = [f"### {field} — min-hamming-distance distribution (lower = more similar)"]
    lines.append("")
    lines.append("| Arm | n | min | P25 | median | P75 | max |")
    lines.append("|---|---|---|---|---|---|---|")
    for arm in ("retracted", "control"):
        vals = sorted(
            r[field] for r in records
            if r["arm"] == arm and isinstance(r.get(field), int)
        )
        if not vals:
            lines.append(f"| {arm} | 0 | — | — | — | — | — |")
            continue
        n = len(vals)

        def _pct(p: float, _vals: list[int] = vals, _n: int = n) -> int:
            idx = max(0, min(_n - 1, int(p * _n)))
            return _vals[idx]

        lines.append(
            f"| {arm} | {n} | {vals[0]} | {_pct(0.25)} | "
            f"{vals[n // 2]} | {_pct(0.75)} | {vals[-1]} |"
        )
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: recall_analyze_image.py <results.json>", file=sys.stderr)
        return 2
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    records = data.get("results", [])
    n_per_arm = data.get("n_per_arm", "?")

    # Sample-quality summary
    arms: dict[str, int] = {}
    pdf_ok: dict[str, int] = {}
    img_count_ok: dict[str, int] = {}
    n_images_total: dict[str, int] = {"retracted": 0, "control": 0}
    for r in records:
        arms[r["arm"]] = arms.get(r["arm"], 0) + 1
        if r["pdf_ok"]:
            pdf_ok[r["arm"]] = pdf_ok.get(r["arm"], 0) + 1
            if r["n_images"] >= 2:
                img_count_ok[r["arm"]] = (
                    img_count_ok.get(r["arm"], 0) + 1
                )
            n_images_total[r["arm"]] = (
                n_images_total.get(r["arm"], 0) + r["n_images"]
            )

    print(
        "# PaperGuard image-layer recall study — v1\n\n"
        "**Dataset:** OpenAlex `is_retracted:true` (OA, English, image-rich fields), "
        f"N = {n_per_arm} per arm, matched controls by subfield + year ± 1. "
        "PDF fetch via PMC → Unpaywall → OpenAlex chain; image extraction "
        "via `paperguard.extractor.images.extract_pdf_images` with raster "
        "fallback for vector-figure PDFs.\n"
    )

    print("## 1. Sample quality\n")
    print("| Arm | Recruited | PDF fetched | ≥ 2 images | Total images |")
    print("|---|---|---|---|---|")
    for arm in ("retracted", "control"):
        a = arms.get(arm, 0)
        p = pdf_ok.get(arm, 0)
        i = img_count_ok.get(arm, 0)
        t = n_images_total.get(arm, 0)
        print(f"| {arm} | {a} | {p} | {i} | {t} |")
    print()

    print("## 2. F1 — intra-paper image-duplication detector\n")
    print(_hamming_distribution(records, "f1_min_hamming"))
    print()
    print(_lr_plus_table(records, "f1_severity", "F1 (intra-paper pHash)"))
    print()

    print("## 3. F4 — cross-paper image-duplication detector\n")
    print(_hamming_distribution(records, "f4_min_hamming_cross"))
    print()
    print(_lr_plus_table(records, "f4_severity", "F4 (cross-paper pHash)"))
    print()

    print("## 4. Joint F1 ∨ F4\n")
    print(
        "Severity = max(F1, F4). A paper trips this rule if **either** "
        "intra- or cross-paper image-duplication crosses the threshold."
    )
    print()
    for r in records:
        r["_joint_severity"] = (
            r["f1_severity"]
            if _severity_rank(r["f1_severity"])
            > _severity_rank(r["f4_severity"])
            else r["f4_severity"]
        )
    print(_lr_plus_table(records, "_joint_severity", "F1 ∨ F4"))
    print()

    print("## 5. Notes\n")
    print(
        "- F1 measures intra-paper image duplication (Bik 2016 pattern). "
        "Threshold is hamming distance on perceptual hash: ≤ 2 CRITICAL, "
        "≤ 5 SUSPICIOUS, ≤ 8 CONCERN.\n"
        "- F4 inserts each paper's images into a persistent SQLite store "
        "keyed by DOI, then queries for cross-paper near-duplicates. "
        "Order of insertion: retracted first, then control — so a "
        "control matching a retracted's image is a cross-arm match. "
        "Same hamming thresholds as F1.\n"
        "- Vector-graphic PDFs (Springer / Nature / Lancet / Cell Press) "
        "are captured by the raster fallback in `extract_pdf_images` so "
        "F1/F4 see the same content readers do.\n"
        "- Failed PDF fetches (no OA source returns a `%PDF-` body) and "
        "PDFs with < 2 extracted images are excluded from LR+ rows but "
        "counted in §1.\n"
        "- This is the **first published image-layer recall measurement** "
        "for PaperGuard's F1/F4 detectors.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
