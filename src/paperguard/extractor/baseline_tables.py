"""自动从 RCT 论文 PDF 提取 baseline characteristics 表。

策略：
1. 用 pdfplumber 抽所有页表
2. 启发式识别 baseline 表：caption 含 "baseline" / "characteristics" /
   "demographics" / "table 1" / "study population" 等关键词；
   或表头含至少 2 组（treatment/control/placebo/arm）列
3. 解析每行的 mean ± sd 模式（多组并行）
4. 解析 categorical 行（n (%) 格式）作为信号但暂不喂 C1
5. 自动从表头抽取 per-arm N（如 "Treatment (n=42)"）
6. 输出 list[BaselineVariable]（C1 兼容，含 multi-arm）
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from paperguard.detectors.c1_carlisle import BaselineVariable

_BASELINE_KEYWORDS = re.compile(
    r"(baseline|characteristics|demographics|patient\s*characteristics|"
    r"study\s+population|participant\s+characteristics|"
    r"table\s+1|table\s+s?1|table\s+i\b)",
    re.IGNORECASE,
)
_GROUP_KEYWORDS = re.compile(
    r"(treatment|control|placebo|intervention|active|arm|group|"
    r"comparator|sham|usual\s+care)",
    re.IGNORECASE,
)

# Mean ± SD patterns: "45.2 ± 12.3" / "45.2 (12.3)" / "45.2 [12.3]"
_MEAN_SD_RE = re.compile(
    r"(-?\d+\.?\d*)\s*(?:±|\+/?\-|\(|\[)\s*(\d+\.?\d*)\s*[\)\]]?"
)
# Header-embedded N: "Treatment (n=42)" or "Treatment, n = 42"
_HEADER_N_RE = re.compile(r"[Nn]\s*=\s*(\d+)")
# Plain "n=50" anywhere
_PLAIN_N_RE = re.compile(r"\b[Nn]\s*=\s*(\d+)\b")
# Categorical "23 (45.5%)"
_CAT_RE = re.compile(r"(\d+)\s*\(\s*(\d+\.?\d*)\s*%\s*\)")


@dataclass
class ExtractedBaselineTable:
    page_number: int
    caption: str
    n_per_arm: list[int]
    arms_header: list[str]
    variables: list[BaselineVariable]
    categorical_rows: list[dict[str, object]]


def _extract_arm_ns(header_cells: list[str]) -> list[int]:
    """从表头每个单元格抽 N。返回长度 = len(header_cells) 的 list（缺失补 0）。"""
    result: list[int] = []
    for cell in header_cells:
        m = _HEADER_N_RE.search(cell or "")
        result.append(int(m.group(1)) if m else 0)
    return result


def _is_arm_header(cell: str) -> bool:
    return bool(_GROUP_KEYWORDS.search(cell or ""))


def _identify_arm_columns(header_row: list[str]) -> list[int]:
    """Return column indices that look like arm columns (skip 'Variable' col)."""
    arm_cols: list[int] = []
    for i, cell in enumerate(header_row):
        if i == 0:
            continue  # 通常是变量名列
        if _is_arm_header(cell) or _HEADER_N_RE.search(cell or ""):
            arm_cols.append(i)
    # If at least one arm keyword matched but not all non-first cols,
    # expand to include adjacent columns (often "Drug A", "Drug B", "Placebo"
    # where only Placebo matches the keyword list).
    if arm_cols and len(arm_cols) < len(header_row) - 1:
        arm_cols = list(range(1, len(header_row)))
    # 完全没识别 + 列数 ≥ 3 → 退化为全部非首列
    elif not arm_cols and len(header_row) >= 3:
        arm_cols = list(range(1, len(header_row)))
    return arm_cols


def _parse_continuous_row(
    row: list[str], arm_cols: list[int]
) -> tuple[float, float] | None:
    """单行中按 arm_cols 顺序抽取所有 (mean, sd)。返回平铺 [(m1,s1),(m2,s2)...]."""
    pairs: list[tuple[float, float]] = []
    for col_idx in arm_cols:
        if col_idx >= len(row):
            return None
        cell = row[col_idx]
        m = _MEAN_SD_RE.search(cell or "")
        if not m:
            return None
        try:
            pairs.append((float(m.group(1)), float(m.group(2))))
        except ValueError:
            return None
    if len(pairs) < 2:
        return None
    # 平铺
    flat: tuple[float, ...] = tuple(x for pair in pairs for x in pair)
    return flat  # type: ignore[return-value]


def _parse_categorical_row(
    row: list[str], arm_cols: list[int]
) -> list[tuple[int, float]] | None:
    """Try to parse "n (%)" pattern in each arm column."""
    pairs: list[tuple[int, float]] = []
    for col_idx in arm_cols:
        if col_idx >= len(row):
            return None
        m = _CAT_RE.search(row[col_idx] or "")
        if not m:
            return None
        try:
            pairs.append((int(m.group(1)), float(m.group(2))))
        except ValueError:
            return None
    return pairs if len(pairs) >= 2 else None


def _build_baseline_variable(
    name: str,
    arms: list[tuple[float, float]],
    arm_ns: list[int],
) -> BaselineVariable | None:
    """Build a BaselineVariable with 2+ arms."""
    if len(arms) < 2 or len(arm_ns) < 2:
        return None
    # 把 arms (mean, sd) + arm_ns 合并成 (n, mean, sd) 列表
    triples: list[tuple[int, float, float]] = []
    for i, (mean, sd) in enumerate(arms):
        n = arm_ns[i] if i < len(arm_ns) else 0
        if n < 2:
            return None
        triples.append((n, mean, sd))

    if len(triples) == 2:
        # 保持 backward-compat 字段
        return BaselineVariable(
            name=name,
            n1=triples[0][0], mean1=triples[0][1], sd1=triples[0][2],
            n2=triples[1][0], mean2=triples[1][1], sd2=triples[1][2],
            arms=triples,
        )
    return BaselineVariable(name=name, arms=triples)


def _is_baseline_table(rows: list[list[str]], caption_text: str = "") -> bool:
    if _BASELINE_KEYWORDS.search(caption_text):
        return True
    if not rows:
        return False
    header = " ".join(c or "" for c in rows[0]).lower()
    if not _GROUP_KEYWORDS.search(header):
        return False
    body_text = "\n".join(" ".join(r) for r in rows[1:])
    return len(_MEAN_SD_RE.findall(body_text)) >= 3


def extract_baseline_tables(
    pdf_path: Path,
    default_n_per_group: tuple[int, ...] | None = None,
) -> list[ExtractedBaselineTable]:
    """主入口：返回 PDF 中所有 baseline 表。

    支持 2-arm + multi-arm (3+) RCT。
    Per-arm N 优先取自表头单元格 "Treatment (n=42)"；其次取 page 文本中
    任何 "n=K" 模式（顺序匹配）；最后用 default_n_per_group 兜底。
    """
    results: list[ExtractedBaselineTable] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            page_ns = [int(m.group(1)) for m in _PLAIN_N_RE.finditer(page_text)]

            tables = page.extract_tables() or []
            for tbl in tables:
                if not tbl:
                    continue
                rows = [[(c or "").strip() for c in row] for row in tbl]
                caption = " ".join(rows[0]) if rows else ""

                if not _is_baseline_table(rows, caption + " " + page_text):
                    continue

                header_row = rows[0]
                arm_cols = _identify_arm_columns(header_row)
                if len(arm_cols) < 2:
                    continue

                arms_header = [header_row[i] for i in arm_cols]
                # 先尝试从表头每列拿 N
                arm_ns = [
                    _HEADER_N_RE.search(arms_header[i]).group(1)  # type: ignore[union-attr]
                    if _HEADER_N_RE.search(arms_header[i])
                    else None
                    for i in range(len(arms_header))
                ]
                arm_ns_int: list[int] = []
                for i, val in enumerate(arm_ns):
                    if val:
                        arm_ns_int.append(int(val))
                    elif i < len(page_ns):
                        arm_ns_int.append(page_ns[i])
                    elif default_n_per_group and i < len(default_n_per_group):
                        arm_ns_int.append(default_n_per_group[i])
                    else:
                        arm_ns_int.append(0)

                if all(n < 2 for n in arm_ns_int):
                    continue

                variables: list[BaselineVariable] = []
                categorical_rows: list[dict[str, object]] = []
                for row in rows[1:]:
                    if not row or not row[0]:
                        continue
                    name = row[0].strip()
                    # 先试连续变量
                    flat = _parse_continuous_row(row, arm_cols)
                    if flat:
                        arms = [
                            (flat[2 * i], flat[2 * i + 1])
                            for i in range(len(flat) // 2)
                        ]
                        bv = _build_baseline_variable(name, arms, arm_ns_int)
                        if bv is not None:
                            variables.append(bv)
                            continue
                    # 试 categorical
                    cat = _parse_categorical_row(row, arm_cols)
                    if cat:
                        categorical_rows.append(
                            {"name": name, "arms": cat}
                        )

                if variables:
                    results.append(
                        ExtractedBaselineTable(
                            page_number=page_no,
                            caption=caption,
                            n_per_arm=arm_ns_int,
                            arms_header=arms_header,
                            variables=variables,
                            categorical_rows=categorical_rows,
                        )
                    )

    return results
