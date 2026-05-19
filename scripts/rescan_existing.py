"""Re-scan PDFs that were already downloaded by recall_test_v2.

Useful for measuring the impact of a detector-severity change without
re-running the full ~1-hour download pipeline. Reads a v2 results JSON,
finds the PDF files (still in the original work_dir tempdir), re-runs
``paperguard scan`` on each, and writes a new results JSON with the
fresh severity values.

Usage:

    python scripts/rescan_existing.py \\
        --in scripts/recall_test_v2_results.json \\
        --pdf-dir /tmp/pg_recall_v2_<id> \\
        --out scripts/recall_test_v3_results.json
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


def scan_one(pdf: Path) -> dict[str, Any]:
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
        res = subprocess.run(cmd, env=env, capture_output=True, timeout=300, text=True)
        if res.returncode != 0:
            return {"error": f"exit={res.returncode}", "stderr": res.stderr[-1500:]}
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
    for i, r in enumerate(data["results"], 1):
        # Find the PDF for this record. Filename pattern from
        # recall_test_v2.py: f"{arm}_{i:03d}_{slug}.pdf"
        arm = r["arm"]
        doi = r["doi"]
        if not r.get("download_ok"):
            results.append(r)
            continue
        # search by content_type or filename
        slug = doi.replace("/", "_").replace(":", "_")[:80]
        # try patterns from v1 and v2
        candidates = list(pdf_dir.glob(f"{arm}_*_{slug}.pdf"))
        if not candidates:
            new = dict(r)
            new["rescan_error"] = "PDF not found"
            results.append(new)
            continue
        pdf = candidates[0]
        print(f"[{i:3d}] rescanning {arm} {doi}", file=sys.stderr, flush=True)
        rep = scan_one(pdf)
        new = dict(r)
        new["scan"] = summarise(rep)
        results.append(new)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"n_per_arm": data.get("n_per_arm"), "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(results)} records to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
