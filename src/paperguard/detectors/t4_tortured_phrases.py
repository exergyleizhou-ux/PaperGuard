"""T4 — Tortured Phrases 检测（论文工厂签名）。

学术依据：
Cabanac, Labbé & Magazinov (2021) "Tortured phrases: A dubious writing
style emerging in science." arXiv:2107.06751.
Cabanac et al. (2024) Problematic Paper Screener (PPS).

"Tortured phrases" 是论文工厂常用伎俩：把已确立的术语 ("deep neural
network") 经多轮机器翻译/同义词替换 ("profound neural organization")
以规避剽窃检测。这些短语在自然学术写作中几乎不可能出现。

实现：保守的字典匹配。命中即 SUSPICIOUS（这种短语在合法文本中假阳性
率极低）。本字典是 PPS 公开列表的高精度子集 + ar5iv 全文摘录，约 160 项；
社区贡献可扩展至 7500+。字典刻意只收"在自然学术写作中几乎不可能出现"
的条目——已剔除会误伤正常论文的词（如 "skin disease"、"drug treatment"、
"surface region"）以保持高 LR+。
"""
from __future__ import annotations

import re
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity

# (tortured, canonical) 对。
# 来源：
# - Cabanac, Labbé & Magazinov (2021) arXiv:2107.06751 Table 1 + Appendix
# - Problematic Paper Screener (PPS) https://www.irit.fr/~Guillaume.Cabanac/
#   problematic-paper-screener/tortured/
# - PubMed retracted-papers analyses (Nature 2021; Sci Eng Ethics 2022)
# - Sleuth-confirmed phrases reported in Retraction Watch
TORTURED_PHRASES: dict[str, str] = {
    # === Computer science / ML ===
    "profound neural organization": "deep neural network",
    "fake neural organization": "artificial neural network",
    "counterfeit neural organization": "artificial neural network",
    "phony neural organization": "artificial neural network",
    "false neural organization": "artificial neural network",
    "versatile organization": "mobile network",
    "organization ambush": "network attack",
    "organization assault": "network attack",
    "organization association": "network connection",
    "organization activity": "network traffic",
    "remote sensor organization": "wireless sensor network",
    "remote network sensor": "wireless sensor network",
    "enormous information": "big data",
    "huge information": "big data",
    "immense information": "big data",
    "colossal information": "big data",
    "monstrous information": "big data",
    "gigantic information": "big data",
    "tremendous information": "big data",
    "information stockroom": "data warehouse",
    "information distribution center": "data warehouse",
    "information mining": "data mining",
    "counterfeit consciousness": "artificial intelligence",
    "human-made consciousness": "artificial intelligence",
    "made man-made consciousness": "artificial intelligence",
    "elite figuring": "high-performance computing",
    "elite execution figuring": "high-performance computing",
    "haze figuring": "fog computing",
    "cloud figuring": "cloud computing",
    "mist figuring": "fog computing",
    "edge figuring": "edge computing",
    "designs preparing unit": "graphics processing unit (GPU)",
    "focal preparing unit": "central processing unit (CPU)",
    "work process motor": "workflow engine",
    "facial acknowledgement": "face recognition",
    "facial recognizable proof": "face recognition",
    "facial verification": "face authentication",
    "discourse acknowledgement": "voice recognition",
    "voice acknowledgement": "voice recognition",
    "discourse handling": "speech processing",
    "ordinary language handling": "natural language processing",
    "regular language handling": "natural language processing",
    # === Statistics & math ===
    "mean square mistake": "mean square error",
    "mean square blunder": "mean square error",
    "mean outright mistake": "mean absolute error",
    "mean supreme blunder": "mean absolute error",
    "motion to clamor": "signal-to-noise ratio",
    "flag to clamor": "signal-to-noise ratio",
    "sign to commotion": "signal-to-noise ratio",
    "signal to clamor": "signal-to-noise ratio",
    "indicator to noise": "signal-to-noise ratio",
    "worldwide parameters": "global parameters",
    "worldwide ideal arrangement": "global optimal solution",
    "neighborhood optima": "local optima",
    "neighborhood ideal arrangement": "local optimal solution",
    "arbitrary get right of passage to": "random access",
    "irregular get right of passage to": "random access",
    "arbitrary backwoods": "random forest",
    "irregular timberland": "random forest",
    "arbitrary lush territory": "random forest",
    "arbitrary esteem": "random value",
    "irregular esteem": "random value",
    "arbitrary number": "random number",
    "irregular variable": "random variable",
    "credulous Bayes": "naïve Bayes",
    "innocent Bayes": "naïve Bayes",
    "stand pivotal": "support vector",
    "bolster vector machine": "support vector machine",
    "choice tree": "decision tree",
    "highlight extraction": "feature extraction",
    "include extraction": "feature extraction",
    # === Optimization / energy ===
    "subterranean insect state": "ant colony",
    "underground creepy crawly settlement": "ant colony",
    "subterranean insect settlement enhancement": "ant colony optimization",
    "molecule swarm enhancement": "particle swarm optimization",
    "hereditary calculation": "genetic algorithm",
    "leftover vitality": "remaining energy",
    "leftover power": "remaining power",
    "remaining vitality": "remaining energy",
    "remaining force": "remaining power",
    "territorial normal vitality": "local average energy",
    "motor vitality": "kinetic energy",
    "potential vitality": "potential energy",
    "vitality misfortune": "energy loss",
    "vitality utilization": "energy consumption",
    "vitality proficiency": "energy efficiency",
    # === Biomedical ===
    "individual computerized collaborator": "personal digital assistant (PDA)",
    "bosom danger": "breast cancer",
    "bosom growth": "breast cancer",
    "renal disappointment": "kidney failure",
    "renal harm": "kidney damage",
    "kidney disappointment": "kidney failure",
    "liver disappointment": "liver failure",
    "lactose narrow mindedness": "lactose intolerance",
    # NOTE: removed "X disease" -> "X cancer" entries (rectal/colorectal/
    # prostate/lung/ovarian/cervical/skin) — "lung disease", "skin disease"
    # etc. are legitimate, common medical terms, not documented tortured
    # phrases; they generated false positives on normal papers. The genuine
    # cancer tortures are "bosom danger"/"bosom growth" (kept above).
    # Also removed no-op self-maps ("diabetic patient","glucose level"),
    # the over-generic "circulatory strain", and normal-English
    # "drug treatment"/"compound treatment"/"radiation treatment".
    "blood circulatory strain": "blood pressure",
    "coronary illness": "heart disease",
    "cardiovascular illness": "cardiovascular disease",
    "insulin opposition": "insulin resistance",
    "white platelet": "white blood cell",
    "red platelet": "red blood cell",
    "platelet check": "platelet count",
    "regenerative wellbeing": "reproductive health",
    "imperative signs": "vital signs",
    # === Other common ===
    # NOTE: removed "surface region" (legit math/physics term), "increasing
    # speed" (normal English), "deceleration" (no-op self-map), and the no-op
    # self-maps "diabetic patient"/"glucose level" / generic "circulatory
    # strain" / normal-English "drug treatment"/"radiation treatment"/
    # "compound treatment" — all false-positive sources that lowered LR+.
    "Joined States": "United States",
    "Joined Realm": "United Kingdom",
    "atomic vitality": "nuclear energy",
    "atomic family": "nuclear family",
    "sun powered vitality": "solar energy",
    "sun based force": "solar power",
    "sun oriented force": "solar power",
    "wind vitality": "wind energy",
    "geothermal vitality": "geothermal energy",
    "petroleum derivative": "fossil fuel",
    "ozone harming substance": "greenhouse gas",
    "non-renewable energy source": "fossil fuel",
    "stockpile and request": "supply and demand",
    "thickness work": "density function",
    "warm vitality": "thermal energy",
    "warm conductivity": "thermal conductivity",
    # === Mid-2024 GPT-disguise additions ===
    "demolish learning": "deep learning",
    "convolutional neural organization": "convolutional neural network",
    "intermittent neural organization": "recurrent neural network",
    "long short-term memory organization": "long short-term memory network",
    "creating ill-disposed organization": "generative adversarial network",
    "ill-disposed organization": "adversarial network",
    # === 2026 curated high-precision additions (Cabanac PPS + literature) ===
    # Each chosen to be near-impossible in natural academic writing.
    # --- CS / ML ---
    "leftover organization": "residual network",
    "consideration mechanism": "attention mechanism",
    "consideration component": "attention mechanism",
    "move learning": "transfer learning",
    "shrouded layer": "hidden layer",
    "shrouded Markov model": "hidden Markov model",
    "computerized reasoning": "artificial intelligence",
    "man-made brainpower": "artificial intelligence",
    "profound conviction organization": "deep belief network",
    "outfit learning": "ensemble learning",
    "bunching calculation": "clustering algorithm",
    "fluffy rationale": "fuzzy logic",
    "fluffy set": "fuzzy set",
    "harsh set": "rough set",
    "slope plummet": "gradient descent",
    "angle plunge": "gradient descent",
    "back proliferation": "backpropagation",
    "actuation work": "activation function",
    "misfortune work": "loss function",
    # --- Statistics / math ---
    "relapse investigation": "regression analysis",
    "straight relapse": "linear regression",
    "calculated relapse": "logistic regression",
    "head part investigation": "principal component analysis",
    "relationship coefficient": "correlation coefficient",
    "covariance grid": "covariance matrix",
    "disarray grid": "confusion matrix",
    "lattice duplication": "matrix multiplication",
    "likelihood circulation": "probability distribution",
    "Gaussian circulation": "Gaussian distribution",
    "certainty span": "confidence interval",
    "speculation testing": "hypothesis testing",
    "invalid speculation": "null hypothesis",
    "elective speculation": "alternative hypothesis",
    "centrality level": "significance level",
    "reproduced strengthening": "simulated annealing",
    # --- Biomedical ---
    "coronary corridor": "coronary artery",
}


def _compile_patterns() -> list[tuple[re.Pattern[str], str, str]]:
    patterns: list[tuple[re.Pattern[str], str, str]] = []
    for tortured, canonical in TORTURED_PHRASES.items():
        # 单词边界 + 大小写不敏感 + 多空格容差
        escaped = re.escape(tortured).replace(r"\ ", r"\s+")
        patterns.append(
            (re.compile(rf"\b{escaped}\b", re.IGNORECASE), tortured, canonical)
        )
    return patterns


_COMPILED = _compile_patterns()


class T4TorturedPhrasesDetector(BaseDetector):
    """检测论文工厂/机器翻译/反剽窃工具产生的"扭曲短语"。"""

    id: ClassVar[str] = "T4"
    name: ClassVar[str] = "Tortured Phrases (Paper-Mill Fingerprints)"
    description: ClassVar[str] = (
        "匹配 Problematic Paper Screener 已知扭曲短语字典。"
    )
    academic_basis: ClassVar[str] = (
        "Cabanac, Labbé & Magazinov (2021). Tortured phrases: A dubious "
        "writing style emerging in science. arXiv:2107.06751. "
        "Problematic Paper Screener, IRIT."
    )
    data_requirements: ClassVar[list[str]] = ["manuscript_text"]
    assumption_cluster: ClassVar[str] = "paper_mill_signature"

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, str):
            return False, "Expected text string"
        if len(data) < 200:
            return False, "Text too short"
        return True, ""

    def _detect(self, data: str, seed: int) -> list[Finding]:
        hits: list[tuple[str, str, int]] = []  # (tortured, canonical, count)
        all_examples: list[tuple[str, str, str]] = []  # (tortured, canonical, context)

        for pat, tortured, canonical in _COMPILED:
            matches = list(pat.finditer(data))
            if not matches:
                continue
            hits.append((tortured, canonical, len(matches)))
            for m in matches[:3]:
                ctx_start = max(0, m.start() - 40)
                ctx_end = min(len(data), m.end() + 40)
                ctx = data[ctx_start:ctx_end].replace("\n", " ").strip()
                all_examples.append((tortured, canonical, ctx))

        if not hits:
            return []

        # 严重性：单条命中即 SUSPICIOUS（这类短语在真实学术写作中
        # 几乎不可能自然出现），多条命中 → CRITICAL
        total = sum(c for _, _, c in hits)
        unique_phrases = len(hits)
        if unique_phrases >= 3 or total >= 5:
            severity = Severity.CRITICAL
        else:
            severity = Severity.SUSPICIOUS

        sample = "; ".join(
            f"'{t}' → expected '{c}'" for t, c, _ in hits[:5]
        )

        return [
            Finding(
                detector_id=self.id,
                detector_name=self.name,
                severity=severity,
                summary=(
                    f"发现 {unique_phrases} 类已知扭曲短语，共 {total} 次出现 "
                    f"({sample})"
                ),
                detail=(
                    "在 manuscript 全文中匹配到 Problematic Paper Screener "
                    f"字典中的扭曲短语：{unique_phrases} 个不同短语，共 "
                    f"{total} 次。扭曲短语通常源自机器翻译或反剽窃软件改写，"
                    "在自然学术写作中几乎不可能自然出现，是论文工厂/AI 代写/"
                    "粗糙剽窃的典型签名。"
                ),
                test_statistic=float(total),
                test_name="tortured-phrase match count",
                evidence={
                    "unique_phrases_matched": unique_phrases,
                    "total_matches": total,
                    "hits": [
                        {"tortured": t, "canonical": c, "count": cnt}
                        for t, c, cnt in hits
                    ],
                    "examples_with_context": [
                        {"tortured": t, "canonical": c, "context": ctx}
                        for t, c, ctx in all_examples[:15]
                    ],
                },
                innocent_explanations=[
                    "短语在引用框 / 数据集名 / 历史性引用语境出现"
                    "（应人工核对上下文）",
                    "本论文是关于扭曲短语本身的语言学研究（罕见但合法）",
                    "字典存在假阳性条目（如 'individual computerized "
                    "collaborator' 在某些罕见上下文可指 PDA）",
                    "短语在用户在 figure caption / 表注 / 自动生成索引中"
                    "（非作者实际选词）",
                ],
                academic_reference=self.academic_basis,
            )
        ]
