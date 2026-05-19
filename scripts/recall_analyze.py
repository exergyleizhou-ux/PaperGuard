"""Analyze recall_test_v* results JSON into a human + Markdown report.

Reusable for partial and final outputs. Prints a Markdown-ready summary
to stdout that can be pasted into docs/recall_test_v2.md.

Usage:

    .venv/Scripts/python.exe scripts/recall_analyze.py \
        scripts/recall_test_v2_results.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def bucket_error(err: str) -> str:
    if not err:
        return "—"
    if "403" in err:
        return "403 Forbidden"
    if "404" in err:
        return "404 Not Found"
    if "429" in err:
        return "429 Rate Limit"
    if "5" in err[:25] and ("500" in err or "503" in err or "502" in err):
        return "5xx server"
    if "not a PDF" in err:
        return "HTML (not PDF)"
    if "timeout" in err.lower() or "TimeoutException" in err:
        return "Timeout"
    if "ConnectError" in err or "ReadError" in err:
        return "Network error"
    if "no pdf url" in err:
        return "No PDF URL"
    if "PdfminerException" in err or "PDFSyntaxError" in err:
        return "PDF parse error"
    return "Other"


def scan_ok(r: dict) -> bool:
    s = r.get("scan")
    return (
        isinstance(s, dict)
        and "error" not in s
        and s.get("overall_severity") is not None
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: recall_analyze.py <results.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    results = data["results"]

    ret = [r for r in results if r["arm"] == "retracted"]
    ctrl = [r for r in results if r["arm"] == "control"]

    print(f"# Recall test analysis — {path.name}\n")
    print(f"**Total records**: {len(results)} "
          f"(retracted = {len(ret)}, control = {len(ctrl)})\n")

    # Pipeline stages
    ret_dl = [r for r in ret if r.get("download_ok")]
    ctrl_dl = [r for r in ctrl if r.get("download_ok")]
    ret_scan = [r for r in ret_dl if scan_ok(r)]
    ctrl_scan = [r for r in ctrl_dl if scan_ok(r)]

    print("## Pipeline stages\n")
    print("| Arm | Queried | Downloaded as PDF | Scan returned severity |")
    print("|---|---|---|---|")
    print(f"| Retracted | {len(ret)} | {len(ret_dl)} ({100*len(ret_dl)/max(len(ret),1):.0f}%) | "
          f"{len(ret_scan)} ({100*len(ret_scan)/max(len(ret),1):.0f}%) |")
    print(f"| Control   | {len(ctrl)} | {len(ctrl_dl)} ({100*len(ctrl_dl)/max(len(ctrl),1):.0f}%) | "
          f"{len(ctrl_scan)} ({100*len(ctrl_scan)/max(len(ctrl),1):.0f}%) |\n")

    # Download failure breakdown
    print("## Download outcomes\n")
    print("| Outcome | Retracted | Control |")
    print("|---|---|---|")
    all_buckets = set()
    ret_b = Counter(bucket_error(r.get("download_error", "")) if not r.get("download_ok") else "OK" for r in ret)
    ctrl_b = Counter(bucket_error(r.get("download_error", "")) if not r.get("download_ok") else "OK" for r in ctrl)
    all_buckets.update(ret_b)
    all_buckets.update(ctrl_b)
    for b in sorted(all_buckets, key=lambda x: -(ret_b.get(x, 0) + ctrl_b.get(x, 0))):
        print(f"| {b} | {ret_b.get(b, 0)} | {ctrl_b.get(b, 0)} |")
    print()

    if not ret_scan and not ctrl_scan:
        print("\n_No successful scans — cannot compute recall/FP yet._")
        return 0

    # Severity distribution
    print("## Severity distribution (of successfully scanned)\n")
    print("| Arm | sev=0 PASS | sev=1 CONCERN | sev=2 SUSPICIOUS | sev=3 CRITICAL |")
    print("|---|---|---|---|---|")
    for arm_name, arm in (("Retracted", ret_scan), ("Control", ctrl_scan)):
        sevs = Counter(r["scan"]["overall_severity"] for r in arm)
        total = max(len(arm), 1)
        print(
            f"| {arm_name} | "
            f"{sevs.get(0,0)} ({100*sevs.get(0,0)/total:.0f}%) | "
            f"{sevs.get(1,0)} ({100*sevs.get(1,0)/total:.0f}%) | "
            f"{sevs.get(2,0)} ({100*sevs.get(2,0)/total:.0f}%) | "
            f"{sevs.get(3,0)} ({100*sevs.get(3,0)/total:.0f}%) |"
        )
    print()

    # Per-detector firing rate
    print("## Per-detector firing rate (of successfully scanned)\n")
    print("| Detector | Retracted % | Control % | Ratio (retr / ctrl) |")
    print("|---|---|---|---|")
    all_dets: set[str] = set()
    for r in ret_scan + ctrl_scan:
        all_dets.update((r["scan"].get("detector_hits") or {}).keys())
    rows = []
    for d in sorted(all_dets):
        rh = sum(1 for r in ret_scan if d in (r["scan"].get("detector_hits") or {}))
        ch = sum(1 for r in ctrl_scan if d in (r["scan"].get("detector_hits") or {}))
        rp = 100 * rh / max(len(ret_scan), 1)
        cp = 100 * ch / max(len(ctrl_scan), 1)
        ratio = rp / cp if cp > 0 else (float("inf") if rp > 0 else 0.0)
        rows.append((d, rp, cp, ratio))
    rows.sort(key=lambda x: -(x[3] if x[3] != float("inf") else 1e9))
    for d, rp, cp, ratio in rows:
        ratio_str = "—" if ratio == 0 else "∞" if ratio == float("inf") else f"{ratio:.2f}x"
        print(f"| {d} | {rp:.0f}% | {cp:.0f}% | {ratio_str} |")
    print()

    # Recall / FP at multiple thresholds
    print("## Recall vs false-positive at severity thresholds\n")
    print("| Threshold | Recall (retracted hit) | False-positive (control hit) | LR+ |")
    print("|---|---|---|---|")
    for thresh, name in [(1, "CONCERN"), (2, "SUSPICIOUS"), (3, "CRITICAL")]:
        rh = sum(1 for r in ret_scan if r["scan"]["overall_severity"] >= thresh)
        ch = sum(1 for r in ctrl_scan if r["scan"]["overall_severity"] >= thresh)
        recall = rh / max(len(ret_scan), 1)
        fp = ch / max(len(ctrl_scan), 1)
        # Positive likelihood ratio = recall / (1 - specificity) = recall / fp
        if fp > 0:
            lr_plus = f"{recall / fp:.2f}"
        elif recall > 0:
            lr_plus = "∞ (no FPs)"
        else:
            lr_plus = "—"
        print(
            f"| sev ≥ {thresh} ({name}) | "
            f"{rh}/{len(ret_scan)} = {100*recall:.0f}% | "
            f"{ch}/{len(ctrl_scan)} = {100*fp:.0f}% | "
            f"{lr_plus} |"
        )
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
