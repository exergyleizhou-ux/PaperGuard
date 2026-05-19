"""自动从源码生成每个检测器的 deep-dive markdown。

用法：从仓库根目录跑
    python scripts/generate_detector_docs.py

它会：
1. 实例化所有内置检测器
2. 抽取 id/name/description/academic_basis/data_requirements/assumption_cluster
3. 用 Finding 模板字段（如 innocent_explanations）从源代码里手动维护的列表
4. 输出 docs/detectors/{ID}.md（每个 ~50 行）
"""
from __future__ import annotations

from pathlib import Path

from paperguard.core.registry import DetectorRegistry

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "detectors"

TEMPLATE = """# {id} — {name}

> {description}

## What it detects

{description}

Cluster: `{cluster}` — findings from detectors in the same cluster
are treated as non-independent during the BH-FDR + severity escalation
in [`combiner.py`](../../src/paperguard/evidence/combiner.py).

## Inputs

This detector requires data shaped as: `{data_requirements}`.

See [`detect()` signature](../../src/paperguard/detectors/{filename}) for
exact type expectations.

## Method

See implementation: [`src/paperguard/detectors/{filename}`](../../src/paperguard/detectors/{filename})

The algorithm and thresholds are documented in the file header docstring;
they intentionally live with the code so that changing one without the
other is impossible.

## Severity ladder

PaperGuard maps internal scores to the standard five-level Severity:

| Level | Meaning |
|---|---|
| PASS | Not applicable / no signal |
| NOTE | Minor curiosity, archived |
| CONCERN | Single-detector p < 0.01 OR moderate signal |
| SUSPICIOUS | Strong signal OR multi-cluster CONCERN+ |
| CRITICAL | Mathematically impossible result OR cross-cluster ≥ 3 CONCERN+ |

This detector's specific cut-points are in the source file.

## Innocent explanations

Every finding from `{id}` carries a non-exhaustive list of plausible
non-fraud explanations. Read them. A flagged finding is **never proof of
misconduct** — it is a request for the author / reviewer / editor to
investigate further with full context.

The current innocent_explanations list lives in
[`{filename}`](../../src/paperguard/detectors/{filename}).

## Known false positives / negatives

| Pattern | Likely outcome |
|---|---|
| Very small sample (N < detector minimum) | Detector marks `applicable=False` (no finding) |
| Data with legitimate structural reasons for the pattern | False positive (use innocent_explanations) |
| Data fabricated by an algorithm that mimics this detector's null distribution | False negative (no detector is silver bullet) |

## Academic basis

{academic_basis}

## Source

- Implementation: [`src/paperguard/detectors/{filename}`](../../src/paperguard/detectors/{filename})
- Tests: see `tests/test_detectors/`
- See also: [`docs/fraud_case_studies.md`](../fraud_case_studies.md) for
  which real misconduct cases motivate this detector.

## See also

- [Detector index](README.md)
- [Epistemic position](../epistemic_position.md)
- [Combiner: BH-FDR + severity escalation](../../src/paperguard/evidence/combiner.py)
"""


def _filename_for(det_id: str) -> str:
    import importlib

    # 各 detector 文件名是从源码 module 导出来的
    # 用 inspect 找
    import inspect

    reg = DetectorRegistry().register_default(load_plugins=False)
    det = reg.get(det_id)
    if det is None:
        return ""
    module = inspect.getmodule(det.__class__)
    if module is None or module.__file__ is None:
        return ""
    return Path(module.__file__).name


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    reg = DetectorRegistry().register_default(load_plugins=False)
    for det in reg.all():
        filename = _filename_for(det.id)
        body = TEMPLATE.format(
            id=det.id,
            name=det.name,
            description=det.description,
            cluster=det.assumption_cluster,
            data_requirements=", ".join(det.data_requirements),
            academic_basis=det.academic_basis,
            filename=filename,
        )
        out = DOCS_DIR / f"{det.id}.md"
        out.write_text(body, encoding="utf-8")
        print(f"  wrote {out}")


if __name__ == "__main__":
    main()
