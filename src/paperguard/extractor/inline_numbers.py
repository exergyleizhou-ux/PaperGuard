"""从段落文本中按上下文分类抽取数字。

许多论文的数据嵌在段落里（"mean=2.31 ± 0.12, p<0.05"），而非原生
Word/PDF 表格。把这些数字按语义分类后分别送检测器，比把所有数字
一锅端喂 A1 更有意义（不同语义类的分布本就不同）。

分类策略（保守正则，宁可漏不可错）：
- p_values:    "p < 0.05" / "p = 0.04" / "P=0.001"
- percentages: "23.5%" / "0.5 %"
- ci_bounds:   "95% CI: [1.2, 3.4]"
- means_with_sd: "mean=2.31 ± 0.12" / "2.31±0.12" / "2.31 (SD 0.12)"
- general:     其它独立小数 / 整数（兜底，最不可靠）
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def extract_text_from_docx(path: Path) -> str:
    """从 docx 提取所有正文文本（按段落用换行连接）。"""
    with zipfile.ZipFile(path) as z:
        if "word/document.xml" not in z.namelist():
            return ""
        root = ET.parse(z.open("word/document.xml")).getroot()
    paragraphs: list[str] = []
    for p in root.iter(f"{{{W_NS}}}p"):
        text = "".join(t.text or "" for t in p.iter(f"{{{W_NS}}}t")).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


_P_VALUE_RE = re.compile(
    r"\b[Pp]\s*[<=≤>≥]\s*(?P<val>\d+\.?\d*[eE][+-]?\d+|\d*\.\d+|\.\d+)"
)
_PERCENT_RE = re.compile(r"(?P<val>-?\d+\.?\d*)\s*%")
_MEAN_SD_RE = re.compile(
    r"(?P<mean>-?\d+\.\d+)\s*(?:±|\+\-|\+/\-)\s*(?P<sd>\d+\.\d+)"
)
# 兜底：独立的小数（至少 1 位小数）
_DECIMAL_RE = re.compile(r"(?<![\d\.])-?\d+\.\d+(?![\d\.])")


def classify_numbers(text: str) -> dict[str, list[float]]:
    """把文本里的数字按语义分类。

    返回：{类别名: list[float]}。空类别不会被略去（始终包含全部 keys）。
    """
    out: dict[str, list[float]] = {
        "p_values": [],
        "percentages": [],
        "mean_centers": [],
        "mean_sds": [],
        "general_decimals": [],
    }

    used_spans: list[tuple[int, int]] = []

    for m in _P_VALUE_RE.finditer(text):
        try:
            out["p_values"].append(float(m.group("val")))
            used_spans.append(m.span())
        except ValueError:
            pass

    for m in _PERCENT_RE.finditer(text):
        try:
            out["percentages"].append(float(m.group("val")))
            used_spans.append(m.span())
        except ValueError:
            pass

    for m in _MEAN_SD_RE.finditer(text):
        try:
            out["mean_centers"].append(float(m.group("mean")))
            out["mean_sds"].append(float(m.group("sd")))
            used_spans.append(m.span())
        except ValueError:
            pass

    # general_decimals: 排除已分类区间
    used_spans.sort()

    def in_used(start: int, end: int) -> bool:
        return any(s <= start < e or s < end <= e for s, e in used_spans)

    for m in _DECIMAL_RE.finditer(text):
        if in_used(*m.span()):
            continue
        try:
            out["general_decimals"].append(float(m.group(0)))
        except ValueError:
            pass

    return out


def classify_numbers_from_docx(path: Path) -> dict[str, list[float]]:
    """便捷封装：直接从 .docx 路径分类。"""
    return classify_numbers(extract_text_from_docx(path))
