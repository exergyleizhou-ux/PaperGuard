"""T1 — 文本剽窃 / 自我抄袭 检测（n-gram shingling + Jaccard）。

学术依据：标准 plagiarism-detection 文献（Brin, Davis, Garcia-Molina 1995
COPS；Schleimer et al. 2003 Winnowing）。

策略：
1. 用户提供 query 文本（manuscript 全文） + corpus（候选源文本集合）
2. 对每个文本做 5-gram word shingling，计算 hash 集
3. 用 Jaccard 相似度 + 共享 shingle 数评估重叠
4. 超阈值 → 输出可疑段（含命中的 corpus ID）

本检测器不联网。Corpus 由用户自己准备（例如：之前的 manuscript 草稿、
已发表论文的全文 .txt 列表）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


@dataclass
class TextSimilarityInput:
    query_text: str
    corpus: dict[str, str]  # {label: full_text}
    n: int = 5
    jaccard_concern: float = 0.10
    jaccard_suspicious: float = 0.25
    jaccard_critical: float = 0.50


_WORD_RE = re.compile(r"[A-Za-z一-鿿]+")


def _normalize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _shingles(words: list[str], n: int) -> set[str]:
    if len(words) < n:
        return set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


class T1TextSimilarityDetector(BaseDetector):
    """通过 n-gram shingling 检测 query 与 corpus 间文本重叠。"""

    id: ClassVar[str] = "T1"
    name: ClassVar[str] = "Text Similarity (n-gram Shingling)"
    description: ClassVar[str] = (
        "查 query 文本与用户提供的 corpus 之间的 n-gram 重叠 Jaccard。"
    )
    academic_basis: ClassVar[str] = (
        "Brin, Davis, Garcia-Molina (1995) COPS; Schleimer et al. (2003) Winnowing."
    )
    data_requirements: ClassVar[list[str]] = ["manuscript_text", "text_corpus"]
    assumption_cluster: ClassVar[str] = "text_similarity"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, TextSimilarityInput):
            return False, "Expected TextSimilarityInput"
        if len(_WORD_RE.findall(data.query_text)) < data.n + 5:
            return False, "Query text too short"
        if not data.corpus:
            return False, "Empty corpus"
        return True, ""

    def _detect(self, data: TextSimilarityInput, seed: int) -> list[Finding]:
        q_words = _normalize(data.query_text)
        q_shingles = _shingles(q_words, data.n)
        if not q_shingles:
            return []

        findings: list[Finding] = []
        for label, src in data.corpus.items():
            s_shingles = _shingles(_normalize(src), data.n)
            if not s_shingles:
                continue
            jacc = _jaccard(q_shingles, s_shingles)
            shared = len(q_shingles & s_shingles)
            if jacc < data.jaccard_concern:
                continue
            if jacc >= data.jaccard_critical:
                severity = Severity.CRITICAL
            elif jacc >= data.jaccard_suspicious:
                severity = Severity.SUSPICIOUS
            else:
                severity = Severity.CONCERN

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"与 corpus '{label}' 的 {data.n}-gram Jaccard = "
                        f"{jacc:.3f}（共享 {shared} 个 shingle）"
                    ),
                    detail=(
                        f"对 query 文本与 corpus 条目 '{label}' 做 {data.n}-gram "
                        f"shingling，Jaccard 相似度为 {jacc:.4f}。"
                        f"Query 总 shingle {len(q_shingles)} 个，"
                        f"source 总 shingle {len(s_shingles)} 个，"
                        f"重叠 {shared} 个。"
                    ),
                    test_statistic=jacc,
                    test_name=f"{data.n}-gram Jaccard",
                    evidence={
                        "corpus_label": label,
                        "n": data.n,
                        "query_shingle_count": len(q_shingles),
                        "source_shingle_count": len(s_shingles),
                        "shared_shingles": shared,
                        "jaccard": jacc,
                    },
                    innocent_explanations=[
                        "Corpus 是同一作者的早期 preprint 或学位论文"
                        "（合法的自我重用，但应在 Methods 中声明）",
                        "重叠在 boilerplate 部分（如标准 PRISMA 流程描述）",
                        "Corpus 是论文 SI 或开放数据描述，本就允许重复",
                        "短文本下 Jaccard 高估了真实相似度（噪声）",
                    ],
                    academic_reference=self.academic_basis,
                )
            )
        return findings
