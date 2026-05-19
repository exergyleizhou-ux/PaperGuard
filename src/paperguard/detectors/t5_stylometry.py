"""T5 — Stylometry: 编造论文的语言学指纹（Stapel-style）。

学术依据：
Markowitz & Hancock (2014) "Linguistic Traces of a Scientific Fraud:
The Case of Diederik Stapel." PLOS ONE 9(8): e105937.

关键发现：Stapel 编造的论文 vs 真实论文：
- 方法学 / 调查相关词汇密度更高（"measured", "study", "experiment"）
- 确定性词汇更多（"clearly", "obvious", "certain", "definitely"）
- 形容词更少（编造者倾向于减少修饰）
- 第一人称单数更少

策略：计算三个比值，与"自然学术写作"参考区间比较。任一显著偏离 → NOTE
或 CONCERN。多个同时偏离 → SUSPICIOUS。

注意：这是探索性检测器，假阳性率比 A1/A3 高，仅作为补充信号。
"""
from __future__ import annotations

import re
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity

_WORD = re.compile(r"[A-Za-z]+")
_METHODOLOGY_WORDS = {
    "measure", "measured", "measurement", "measurements",
    "method", "methods", "methodology", "methodological",
    "study", "studies", "studied",
    "experiment", "experiments", "experimental",
    "investigation", "investigations", "investigated",
    "observation", "observations", "observed",
    "analysis", "analyses", "analyzed", "analysed",
    "procedure", "procedures",
    "design", "designed",
}
_CERTAINTY_WORDS = {
    "clearly", "obviously", "obvious",
    "certain", "certainly", "certainty",
    "definite", "definitely", "definitively",
    "undoubtedly", "doubtless",
    "indisputable", "indisputably",
    "evidently", "evident",
    "unambiguous", "unambiguously",
}
# 极简形容词词缀启发（不需要 NLP 库）：以 -al, -ic, -ous, -ful, -ive 结尾
_ADJECTIVE_SUFFIXES = ("al", "ic", "ous", "ful", "ive", "ent", "ant")


def _count(words: list[str], target_set: set[str]) -> int:
    return sum(1 for w in words if w in target_set)


def _adjective_count(words: list[str]) -> int:
    return sum(
        1 for w in words if len(w) > 4 and any(w.endswith(s) for s in _ADJECTIVE_SUFFIXES)
    )


class T5StylometryDetector(BaseDetector):
    """Stylometric ratios — methodology, certainty, adjectives."""

    id: ClassVar[str] = "T5"
    name: ClassVar[str] = "Stylometry (Stapel Linguistic Fingerprint)"
    description: ClassVar[str] = (
        "Methodology / certainty / adjective 密度异常 → 类 Stapel 风格。"
    )
    academic_basis: ClassVar[str] = (
        "Markowitz & Hancock (2014). Linguistic Traces of a Scientific "
        "Fraud: The Case of Diederik Stapel. PLOS ONE 9(8): e105937."
    )
    data_requirements: ClassVar[list[str]] = ["manuscript_text"]
    assumption_cluster: ClassVar[str] = "linguistic_pattern"

    # 经验参考区间（来自 Markowitz-Hancock supplementary 大致估算）
    # 注意：这是英文学术写作的粗略参考，中文/其它语言需要不同基线
    REF_METHODOLOGY_RATE: ClassVar[float] = 0.025  # 2.5%
    REF_CERTAINTY_RATE: ClassVar[float] = 0.005    # 0.5%
    REF_ADJECTIVE_RATE: ClassVar[float] = 0.10     # 10%

    MIN_WORDS: ClassVar[int] = 500

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, str):
            return False, "Expected text string"
        if len(_WORD.findall(data)) < self.MIN_WORDS:
            return False, f"Text < {self.MIN_WORDS} words"
        return True, ""

    def _detect(self, data: str, seed: int) -> list[Finding]:
        words = [w.lower() for w in _WORD.findall(data)]
        n = len(words)

        meth_rate = _count(words, _METHODOLOGY_WORDS) / n
        cert_rate = _count(words, _CERTAINTY_WORDS) / n
        adj_rate = _adjective_count(words) / n

        # 偏离方向与 Stapel 论文一致
        meth_z = (meth_rate - self.REF_METHODOLOGY_RATE) / max(self.REF_METHODOLOGY_RATE, 1e-6)
        cert_z = (cert_rate - self.REF_CERTAINTY_RATE) / max(self.REF_CERTAINTY_RATE, 1e-6)
        adj_z = (self.REF_ADJECTIVE_RATE - adj_rate) / max(self.REF_ADJECTIVE_RATE, 1e-6)

        # 各维度偏离 > 50% 视为一个"信号"
        flags: list[str] = []
        if meth_z > 0.5:
            flags.append(f"methodology density {meth_rate:.4f} (ref ≈ {self.REF_METHODOLOGY_RATE})")
        if cert_z > 0.5:
            flags.append(f"certainty density {cert_rate:.4f} (ref ≈ {self.REF_CERTAINTY_RATE})")
        if adj_z > 0.3:
            flags.append(f"adjective density {adj_rate:.4f} (ref ≈ {self.REF_ADJECTIVE_RATE})")

        if not flags:
            return []
        if len(flags) >= 3:
            severity = Severity.CONCERN
        else:
            severity = Severity.NOTE

        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"Stylometric outlier on {len(flags)} dimensions: "
                    + "; ".join(flags)
                ),
                detail=(
                    f"Manuscript word count: {n}. "
                    f"Methodology-word rate: {meth_rate:.4f} "
                    f"(Stapel-fraud signature: elevated). "
                    f"Certainty-word rate: {cert_rate:.4f} "
                    f"(Stapel-fraud signature: elevated). "
                    f"Adjective rate: {adj_rate:.4f} "
                    f"(Stapel-fraud signature: depressed). "
                    "These are exploratory ratios derived from "
                    "Markowitz & Hancock (2014); cross-language and "
                    "cross-discipline calibration is limited."
                ),
                test_statistic=float(len(flags)),
                test_name="dimensions deviating",
                evidence={
                    "n_words": n,
                    "methodology_rate": meth_rate,
                    "certainty_rate": cert_rate,
                    "adjective_rate": adj_rate,
                    "flags": flags,
                },
                innocent_explanations=[
                    "本论文的研究领域确实需要密集方法学描述（如系统综述）",
                    "作者写作风格本就偏强力修饰（非英语母语等）",
                    "参考区间基于英文心理学语料，与本论文学科不匹配",
                    "Adjective 启发只看后缀，会漏掉无典型后缀的形容词",
                ],
                academic_reference=self.academic_basis,
            )
        ]
