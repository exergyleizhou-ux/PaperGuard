"""Re-scan v5 PDFs but pass paper_year to the scanner.

This produces a v6 results JSON: same input PDFs as v5, but the new
2.0.8 year-stratified T3 severity gets to see the year. Used to
measure how much T3 year-stratification (the v3.x Step 1 fix) moves
the recall / FP / LR+ numbers.

Usage:

    python scripts/rescan_existing_v2.py \\
        --in scripts/recall_test_v5_results.json \\
        --pdf-dir /path/to/pg_recall_v5_<id> \\
        --out scripts/recall_test_v6_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def scan_one(pdf: Path, paper_year: int | None) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    paperguard = (
        Path(__file__).resolve().parent.parent
        / ".venv"
        / "Scripts"
        / "paperguard.exe"
    )
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_json = Path(tf.name)
    try:
        cmd = [
            str(paperguard) if paperguard.exists() else "paperguard",
            "scan",
            "-f",
            str(pdf),
            "--output-json",
            str(out_json),
            "--lang",
            "en",
        ]
        if paper_year is not None:
            cmd.extend(["--paper-year", str(paper_year)])
        # text=False + manual decode: stderr from paperguard CLI is mixed
        # English/Chinese; default GBK on Windows crashes the reader thread.
        res = subprocess.run(
            cmd, env=env, capture_output=True, timeout=600, text=False
        )
        if res.returncode != 0:
            stderr_str = (
                res.stderr.decode("utf-8", errors="replace")[-1500:]
                if res.stderr
                else ""
            )
            return {"error": f"exit={res.returncode}", "stderr": stderr_str}
        with out_json.open(encoding="utf-8") as f:
            return json.load(f)
    finally:
        try:
            out_json.unlink()
        except OSError:
            pass


def summarise(rep: dict[str, Any]) -> dict[str, Any]:
    if "error" in rep:
        return rep
    findings = rep.get("all_findings") or []
    sev_counts: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}
    hits: dict[str, int] = {}
    for f in findings:
        s = f.get("severity", 0)
        sev_counts[s] = sev_counts.get(s, 0) + 1
        hits[f.get("detector_id", "?")] = hits.get(f.get("detector_id", "?"), 0) + 1
    return {
        "overall_severity": rep.get("overall_severity"),
        "n_findings": len(findings),
        "severity_counts": sev_counts,
        "detectors_fired": sorted(hits),
        "detector_hits": hits,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir)
    with open(args.inp, encoding="utf-8") as f:
        data = json.load(f)

    results = []
    rescanned = 0
    for i, r in enumerate(data["results"], 1):
        if not r.get("download_ok"):
            results.append(r)
            continue
        arm = r["arm"]
        doi = r["doi"]
        slug = doi.replace("/", "_").replace(":", "_")[:80]
        candidates = list(pdf_dir.glob(f"{arm}_*_{slug}.pdf"))
        if not candidates:
            new = dict(r)
            new["rescan_error"] = "PDF not found"
            results.append(new)
            continue
        pdf = candidates[0]
        year = r.get("year")
        print(
            f"[{i:3d}] rescanning {arm:9s} {doi} (year={year})",
            file=sys.stderr,
            flush=True,
        )
        rep = scan_one(pdf, paper_year=year)
        new = dict(r)
        new["scan"] = summarise(rep)
        new["scan_paper_year"] = year
        results.append(new)
        rescanned += 1

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(
            {"n_per_arm": data.get("n_per_arm"), "results": results},
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(
        f"\nRescanned {rescanned} PDFs with paper_year. Wrote {len(results)} "
        f"records to {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
