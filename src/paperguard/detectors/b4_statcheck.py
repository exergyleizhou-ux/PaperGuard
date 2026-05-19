"""B4 — Statcheck: 重算论文中报告的 p 值。

学术依据：
Nuijten et al. (2016). The prevalence of statistical reporting errors in
psychology (1985–2013). Behavior Research Methods, 48(4), 1205–1226.
algorithm: statcheck.io

支持的统计量：
- t(df) = X, p = Y
- F(df1, df2) = X, p = Y
- chi2(df) = X, p = Y  /  χ²(df) = X, p = Y
- r(df) = X, p = Y     (df = N-2)
- z = X, p = Y

不支持（未来扩展）：
- p 值给出区间（"p < 0.05"）无精确 reported_p，本检测器跳过这类
- 单尾 / 双尾未声明时假设双尾
- df 含小数（混合模型）跳过

输入：原始文本字符串（PDF 或 docx 已提取的全文）
输出：list[Finding]，每条对应一次报告-实际不一致
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from scipy import stats

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class StatcheckMatch:
    test_type: str  # t / F / chi2 / r / z
    df1: float
    df2: float | None
    reported_stat: float
    reported_p: float
    computed_p: float
    inequality: str  # "=", "<", "≤" 等
    raw: str  # 匹配到的原文片段
    is_one_tailed: bool = False


_RE_T = re.compile(
    r"t\s*\(\s*(?P<df>\d+(?:\.\d+)?)\s*\)\s*[<>≤≥]?=?\s*"
    r"(?P<stat>-?\d+\.\d+)\s*,?\s*"
    r"[Pp]\s*(?P<ineq>[<=≤])\s*(?P<p>\d*\.\d+|\.\d+)"
    r"(?P<tail>[\s,;.]*(?:one[-\s]?tailed|two[-\s]?tailed|one[-\s]?sided|two[-\s]?sided|单尾|双尾))?",
    flags=re.IGNORECASE,
)

_RE_F = re.compile(
    r"F\s*\(\s*(?P<df1>\d+(?:\.\d+)?)\s*,\s*(?P<df2>\d+(?:\.\d+)?)\s*\)\s*[<>≤≥]?=?\s*"
    r"(?P<stat>\d+\.\d+)\s*,?\s*"
    r"[Pp]\s*(?P<ineq>[<=≤])\s*(?P<p>\d*\.\d+|\.\d+)"
)

_RE_CHI2 = re.compile(
    r"(?:chi2|χ²|χ2|χ\^2)\s*\(\s*(?P<df>\d+)\s*\)\s*[<>≤≥]?=?\s*"
    r"(?P<stat>\d+\.\d+)\s*,?\s*"
    r"[Pp]\s*(?P<ineq>[<=≤])\s*(?P<p>\d*\.\d+|\.\d+)",
    flags=re.IGNORECASE,
)

_RE_R = re.compile(
    r"\br\s*\(\s*(?P<df>\d+)\s*\)\s*[<>≤≥]?=?\s*"
    r"(?P<stat>-?\.\d+|-?0?\.\d+|-?\d+\.\d+)\s*,?\s*"
    r"[Pp]\s*(?P<ineq>[<=≤])\s*(?P<p>\d*\.\d+|\.\d+)"
)

_RE_Z = re.compile(
    r"\bz\s*[<>≤≥]?=?\s*(?P<stat>-?\d+\.\d+)\s*,?\s*"
    r"[Pp]\s*(?P<ineq>[<=≤])\s*(?P<p>\d*\.\d+|\.\d+)",
    flags=re.IGNORECASE,
)

# Q 检验（meta-analysis 异质性，常见 random-effects model）
_RE_Q = re.compile(
    r"\bQ\s*\(\s*(?P<df>\d+)\s*\)\s*[<>≤≥]?=?\s*"
    r"(?P<stat>\d+\.\d+)\s*,?\s*"
    r"[Pp]\s*(?P<ineq>[<=≤])\s*(?P<p>\d*\.\d+|\.\d+)"
)


def _compute_p(
    test_type: str,
    stat: float,
    df1: float,
    df2: float | None,
    one_tailed: bool = False,
) -> float:
    """根据统计量类型重算 p。

    one_tailed=False（默认）→ 双尾
    one_tailed=True          → 单尾（仅对 t / r / z 有意义；F / chi² 本就单尾）
    """
    if test_type == "t":
        p_one = float(1 - stats.t.cdf(abs(stat), df=df1))
        return p_one if one_tailed else 2 * p_one
    if test_type == "F":
        assert df2 is not None
        return float(1 - stats.f.cdf(stat, df1, df2))
    if test_type == "chi2":
        return float(1 - stats.chi2.cdf(stat, df=df1))
    if test_type == "r":
        n = df1 + 2
        t_stat = stat * ((n - 2) / max(1 - stat**2, 1e-12)) ** 0.5
        p_one = float(1 - stats.t.cdf(abs(t_stat), df=n - 2))
        return p_one if one_tailed else 2 * p_one
    if test_type == "z":
        p_one = float(1 - stats.norm.cdf(abs(stat)))
        return p_one if one_tailed else 2 * p_one
    if test_type == "Q":
        # Q 是 χ² 的特例（meta-analysis 异质性）
        return float(1 - stats.chi2.cdf(stat, df=df1))
    raise ValueError(f"Unknown test type: {test_type}")


def _compute_p_two_tailed(
    test_type: str, stat: float, df1: float, df2: float | None
) -> float:
    """向后兼容封装。"""
    return _compute_p(test_type, stat, df1, df2, one_tailed=False)


_ONE_TAIL_KEYWORDS = ("one-tailed", "one tailed", "one-sided", "one sided", "单尾")


def _is_one_tailed(annotation: str | None) -> bool:
    if not annotation:
        return False
    a = annotation.lower()
    return any(k in a for k in _ONE_TAIL_KEYWORDS)


def _extract_matches(text: str) -> list[StatcheckMatch]:
    """扫文本，返回所有解析出的统计报告。"""
    matches: list[StatcheckMatch] = []

    for m in _RE_T.finditer(text):
        df = float(m.group("df"))
        stat = float(m.group("stat"))
        reported_p = float(m.group("p"))
        ineq = m.group("ineq")
        one_tail = _is_one_tailed(m.groupdict().get("tail"))
        try:
            computed_p = _compute_p("t", stat, df, None, one_tailed=one_tail)
        except ValueError:
            continue
        matches.append(
            StatcheckMatch(
                "t", df, None, stat, reported_p, computed_p, ineq, m.group(0),
                is_one_tailed=one_tail,
            )
        )

    for m in _RE_F.finditer(text):
        df1 = float(m.group("df1"))
        df2 = float(m.group("df2"))
        stat = float(m.group("stat"))
        reported_p = float(m.group("p"))
        ineq = m.group("ineq")
        try:
            computed_p = _compute_p_two_tailed("F", stat, df1, df2)
        except ValueError:
            continue
        matches.append(
            StatcheckMatch("F", df1, df2, stat, reported_p, computed_p, ineq, m.group(0))
        )

    for m in _RE_CHI2.finditer(text):
        df = float(m.group("df"))
        stat = float(m.group("stat"))
        reported_p = float(m.group("p"))
        ineq = m.group("ineq")
        try:
            computed_p = _compute_p_two_tailed("chi2", stat, df, None)
        except ValueError:
            continue
        matches.append(
            StatcheckMatch("chi2", df, None, stat, reported_p, computed_p, ineq, m.group(0))
        )

    for m in _RE_R.finditer(text):
        df = float(m.group("df"))
        stat = float(m.group("stat"))
        reported_p = float(m.group("p"))
        ineq = m.group("ineq")
        if abs(stat) >= 1:
            continue
        try:
            computed_p = _compute_p_two_tailed("r", stat, df, None)
        except ValueError:
            continue
        matches.append(
            StatcheckMatch("r", df, None, stat, reported_p, computed_p, ineq, m.group(0))
        )

    # 全文一次性扫描 "one-tailed" / "one-sided" / "单尾"——若全文出现，
    # 则后续 t/r/z 匹配在两尾不一致时会再以单尾重算并接受（statcheck 同款启发）
    text_has_one_tailed_keyword = any(
        k in text.lower() for k in _ONE_TAIL_KEYWORDS
    )

    for m in _RE_Z.finditer(text):
        stat = float(m.group("stat"))
        reported_p = float(m.group("p"))
        ineq = m.group("ineq")
        try:
            computed_p = _compute_p("z", stat, 1, None, one_tailed=False)
        except ValueError:
            continue
        matches.append(
            StatcheckMatch(
                "z", 1, None, stat, reported_p, computed_p, ineq, m.group(0),
            )
        )

    for m in _RE_Q.finditer(text):
        df = float(m.group("df"))
        stat = float(m.group("stat"))
        reported_p = float(m.group("p"))
        ineq = m.group("ineq")
        try:
            computed_p = _compute_p("Q", stat, df, None)
        except ValueError:
            continue
        matches.append(
            StatcheckMatch(
                "Q", df, None, stat, reported_p, computed_p, ineq, m.group(0),
            )
        )

    # 全文级单尾修正：对 t / r / z 匹配做"如果换算单尾就一致"的回查
    if text_has_one_tailed_keyword:
        for mt in matches:
            if mt.test_type not in {"t", "r", "z"}:
                continue
            # 已经一致的不动
            num, dec = _is_inconsistent(mt)
            if not num and not dec:
                continue
            try:
                p_one = _compute_p(
                    mt.test_type, mt.reported_stat, mt.df1, mt.df2,
                    one_tailed=True,
                )
            except ValueError:
                continue
            # 创建一个临时 match 在单尾下再判一次
            shadow = StatcheckMatch(
                mt.test_type, mt.df1, mt.df2, mt.reported_stat,
                mt.reported_p, p_one, mt.inequality, mt.raw,
                is_one_tailed=True,
            )
            n2, d2 = _is_inconsistent(shadow)
            if not n2 and not d2:
                # 单尾下一致 → 改写为单尾
                mt.computed_p = p_one
                mt.is_one_tailed = True

    return matches


def _is_inconsistent(match: StatcheckMatch) -> tuple[bool, bool]:
    """判断该匹配是否报告/计算不一致。

    Returns:
        (any_inconsistency, decision_inconsistency)
        - any_inconsistency: 报告值与计算值在四舍五入精度上不一致
        - decision_inconsistency: 报告 p<0.05 但计算 p>=0.05，或反之
    """
    rp = match.reported_p
    cp = match.computed_p
    alpha = 0.05

    # 1) decision-level inconsistency
    # 报告"显著"意味着：等号 → rp < α；不等号(<, ≤) → rp ≤ α（"p < 0.05" 即声明显著）
    if match.inequality == "=":
        claimed_sig = rp < alpha
    else:
        claimed_sig = rp <= alpha
    actual_sig = cp < alpha
    decision = claimed_sig != actual_sig

    # 2) numeric inconsistency
    if match.inequality == "=":
        precision = _decimal_precision(rp)
        rounded_cp = round(cp, precision)
        numeric = abs(rounded_cp - rp) > (10 ** (-precision)) / 2 + 1e-12
    else:
        # "p < X" 不一致当 computed >= X
        numeric = cp >= rp

    return numeric, decision


def _decimal_precision(p: float) -> int:
    """估算 p 值的报告精度（小数位数）。"""
    s = f"{p:.10f}".rstrip("0").rstrip(".")
    if "." in s:
        return len(s.split(".", 1)[1])
    return 0


class B4StatcheckDetector(BaseDetector):
    """Statcheck — 重算论文文本中报告的 p 值。"""

    id: ClassVar[str] = "B4"
    name: ClassVar[str] = "Statcheck p-value Recomputation"
    description: ClassVar[str] = "扫描论文文本中 t/F/χ²/r/z 检验的报告 p 值，重算并比对。"
    academic_basis: ClassVar[str] = (
        "Nuijten et al. (2016). The prevalence of statistical reporting errors in "
        "psychology. Behavior Research Methods, 48(4), 1205-1226."
    )
    data_requirements: ClassVar[list[str]] = ["manuscript_text"]
    assumption_cluster: ClassVar[str] = "summary_statistic_consistency"

    def check_applicability(self, data: str) -> tuple[bool, str]:
        if not isinstance(data, str):
            return False, "Expected text string"
        if len(data) < 30:
            return False, "Text too short"
        return True, ""

    def _detect(self, data: str, seed: int) -> list[Finding]:
        matches = _extract_matches(data)
        findings: list[Finding] = []

        for m in matches:
            numeric, decision = _is_inconsistent(m)
            if not numeric and not decision:
                continue

            severity = Severity.SUSPICIOUS if decision else Severity.CONCERN

            label = (
                f"{m.test_type}({int(m.df1)}"
                + (f",{int(m.df2)})" if m.df2 is not None else ")")
                + f"={m.reported_stat}, p{m.inequality}{m.reported_p}"
            )

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"报告统计量 {label} 与重算 p={m.computed_p:.4f} 不一致"
                        + ("（跨 α=0.05 决策反转）" if decision else "")
                    ),
                    detail=(
                        f"原文片段：'{m.raw}'\n"
                        f"报告统计量：{m.test_type} = {m.reported_stat}, "
                        f"df = {m.df1}"
                        + (f", {m.df2}" if m.df2 is not None else "")
                        + f"\n报告 p = {m.reported_p}（{m.inequality}）；"
                        f"双尾重算 p = {m.computed_p:.6f}。"
                    ),
                    p_value=m.computed_p,
                    test_statistic=m.reported_stat,
                    test_name=f"{m.test_type} (recomputed)",
                    evidence={
                        "raw_match": m.raw,
                        "test_type": m.test_type,
                        "df1": m.df1,
                        "df2": m.df2,
                        "reported_stat": m.reported_stat,
                        "reported_p": m.reported_p,
                        "computed_p": m.computed_p,
                        "inequality": m.inequality,
                        "decision_reversal": decision,
                    },
                    innocent_explanations=[
                        "原文为单尾检验，但本工具默认双尾（请人工核对）",
                        "df 报告错误或文本提取错误（如来自图注/脚注的次要数字）",
                        "p 值经过 BH-FDR 等多重比较校正后报告",
                        "统计量本身是从置信区间反推（精度损失）",
                        "排版错误：报告值的小数位错位",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        return findings
