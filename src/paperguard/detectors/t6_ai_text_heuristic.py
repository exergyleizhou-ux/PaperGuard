"""T6 — AI 生成文本启发式检测。

学术依据：
- Cabanac et al. (2024) "ChatGPT-generated text found in increasing
  number of scientific papers." Nature.
- Kobak et al. (2025) "Delving into ChatGPT word patterns" arXiv.
- "Tortured phrases" 工作 (Cabanac 2021) 的延伸：AI 也有自己的
  word patterns（"delve into", "tapestry", "meticulously", etc.）

策略：保守的字典匹配 + 风格统计。本检测器不"检测 AI"——它检测
**AI 高频但学术写作罕见**的词汇签名。命中即 NOTE / CONCERN，
不下定论。

关键短语（来源：多篇 Nature/Science 报道 + Kobak 2025 抓取数据）：
- "delve into" / "delves into"
- "tapestry of" / "rich tapestry"
- "meticulous" / "meticulously"
- "intricate interplay"
- "in the realm of"
- "navigating the"
- "underscoring the importance"
- "shed light on"（过度使用）
- "pivotal role"
- "groundbreaking"
- "leveraging" (在非技术文档中)
- "boasts a"
- 句首 "Moreover," "Furthermore," "Additionally," 高频
- "in conclusion" 同段重复

另一个强信号：未清理的 ChatGPT prompt 残留，如：
- "as an AI language model"
- "I'm sorry, but"
- "as of my last training" / "as of my knowledge cutoff"
- "regenerate response"
- "let me know if you need"
"""
from __future__ import annotations

import re
from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity

# 极强信号：未清理 LLM 残留（直接 CRITICAL）
_LLM_LEAK_PATTERNS = (
    r"as an AI language model",
    r"I(?:'m| am) sorry,? but",
    r"as of my (?:last training|knowledge cutoff|knowledge update)",
    r"regenerate response",
    r"I cannot (?:provide|access|browse)",
    r"I don't have access to (?:real[\-\s]?time|the internet)",
    r"certainly[!,]? here(?:'s| is) (?:the|a)",
)

# 中等信号：AI 风格短语（多条命中才 SUSPICIOUS，单条 NOTE）
# 2.0.14 升级:按 provider 分类,可以输出"这段更像 GPT / Claude / Gemini"
# 提示。源:
#   - GPT: Kobak 2025 + Liang 2024 抓 ChatGPT 输出统计
#   - Claude: Anthropic 自家 system-prompt 析出 + 真实输出对比
#   - Gemini: Google 自家 + 公开 RLHF 训练资料
_AI_STYLE_PHRASES_GPT = (
    "delve into", "delves into", "delving into",
    "tapestry of", "rich tapestry", "intricate tapestry",
    "meticulous", "meticulously",
    "intricate interplay", "complex interplay",
    "in the realm of",
    "navigating the complex", "navigating the intricacies",
    "underscoring the importance", "underscores the importance",
    "shed light on", "sheds light on", "shedding light on",
    "pivotal role", "plays a pivotal",
    "groundbreaking",
    "boasts a", "boasts an",
    "noteworthy", "it's worth noting",
    "comprehensively", "comprehensive understanding",
    "leveraging the power", "leverage the power",
    "embark on", "embark upon",
    "paradigm shift",
    "the multifaceted",
    "a robust framework", "robust framework",
    # 2.0.14 newer GPT-4/5 favorites:
    "testament to", "stands as a testament",
    "in summary", "to summarize",
    "vibrant",
    "captivate", "captivating",
    "seamlessly",
    "synergy", "synergistic",
    "ever-evolving", "ever-changing landscape",
    "cutting-edge",
    "harness the power",
    "treasure trove",
    "kaleidoscope",
)
_AI_STYLE_PHRASES_CLAUDE = (
    # Claude-isms — these are characteristic openers / qualifiers
    "I'd be happy to",
    "I'll help",
    "Let me",
    "Certainly!",
    "Here's a",
    "Of course!",
    # Hedging clusters Claude uses more than GPT:
    "it's important to note",
    "it's worth mentioning",
    "I should mention",
    "to be clear",
    "to be more precise",
    # Claude's preferred structure marker:
    "Let me break this down",
    "I'll address each",
    "There are several",
    # Subtle Claude markers from 2024-2025 outputs:
    "thoughtful",
    "nuanced",
    "trade-offs",
    "consideration",
    "balanced perspective",
    "with that said",
)
_AI_STYLE_PHRASES_GEMINI = (
    # Gemini header-heavy style:
    "Here's a breakdown",
    "Here are the key",
    "Key Takeaways",
    "Key Points",
    "Important Considerations",
    "Quick Summary",
    "TL;DR",
    "In short,",
    "In essence,",
    # Gemini's preferred bullet headers:
    "Pros and Cons",
    "Advantages:",
    "Disadvantages:",
    "Limitations:",
    # Gemini's tone markers from 2024 outputs:
    "Absolutely!",
    "Great question!",
    "Excellent question!",
    "That's a fantastic",
)
# Combined for back-compat
_AI_STYLE_PHRASES = (
    _AI_STYLE_PHRASES_GPT + _AI_STYLE_PHRASES_CLAUDE + _AI_STYLE_PHRASES_GEMINI
)

_LEAK_RE = [re.compile(p, re.IGNORECASE) for p in _LLM_LEAK_PATTERNS]
_PHRASE_RE = [
    (re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE), p)
    for p in _AI_STYLE_PHRASES
]
_PHRASE_RE_GPT = [
    (re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE), p)
    for p in _AI_STYLE_PHRASES_GPT
]
_PHRASE_RE_CLAUDE = [
    (re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE), p)
    for p in _AI_STYLE_PHRASES_CLAUDE
]
_PHRASE_RE_GEMINI = [
    (re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE), p)
    for p in _AI_STYLE_PHRASES_GEMINI
]


def _provider_attribution(text: str) -> tuple[str, dict[str, int]]:
    """Return (most-likely-provider, {provider: hit_count}).

    Compares per-provider hit rates and reports whichever crossed the
    significance threshold most strongly. If all under threshold,
    returns 'none'.
    """
    counts = {
        "gpt": sum(
            len(p.findall(text)) for p, _ in _PHRASE_RE_GPT
        ),
        "claude": sum(
            len(p.findall(text)) for p, _ in _PHRASE_RE_CLAUDE
        ),
        "gemini": sum(
            len(p.findall(text)) for p, _ in _PHRASE_RE_GEMINI
        ),
    }
    if max(counts.values()) < 3:
        return "none", counts
    return max(counts.items(), key=lambda kv: kv[1])[0], counts


class T6AITextHeuristicDetector(BaseDetector):
    """检测 AI 生成文本的两类签名：未清理残留 + 风格短语密度。"""

    id: ClassVar[str] = "T6"
    name: ClassVar[str] = "AI-Generated Text Heuristic"
    description: ClassVar[str] = (
        "扫 LLM 残留短语 + AI 高频风格词，给出 AI-likelihood 信号。"
    )
    academic_basis: ClassVar[str] = (
        "Cabanac et al. (2024) ChatGPT-in-papers Nature; "
        "Kobak et al. (2025) ChatGPT word patterns arXiv."
    )
    data_requirements: ClassVar[list[str]] = ["manuscript_text"]
    assumption_cluster: ClassVar[str] = "paper_mill_signature"

    MIN_WORDS: ClassVar[int] = 300
    PHRASE_DENSITY_CONCERN: ClassVar[float] = 0.003   # 0.3% (vs typical < 0.05%)
    PHRASE_DENSITY_SUSPICIOUS: ClassVar[float] = 0.006

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        if not isinstance(data, str):
            return False, "Expected text string"
        words = re.findall(r"\b[a-zA-Z]+\b", data)
        if len(words) < self.MIN_WORDS:
            return False, "Text too short"
        return True, ""

    def _detect(self, data: str, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        # 1) Hard signal: LLM leakage
        leaks: list[tuple[str, str]] = []
        for pat in _LEAK_RE:
            for m in pat.finditer(data):
                start = max(0, m.start() - 30)
                end = min(len(data), m.end() + 30)
                ctx = data[start:end].replace("\n", " ").strip()
                leaks.append((m.group(0), ctx))

        if leaks:
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=Severity.CRITICAL,
                    summary=(
                        f"Manuscript contains {len(leaks)} uncleaned LLM "
                        f"response artifact(s)"
                    ),
                    detail=(
                        "Found phrases that are characteristic of unedited "
                        "LLM (ChatGPT/Claude/Gemini) responses left inside "
                        "the manuscript text. Examples: "
                        + "; ".join(f"'{m}'" for m, _ in leaks[:3])
                    ),
                    evidence={
                        "leak_count": len(leaks),
                        "examples": [
                            {"match": m, "context": c} for m, c in leaks[:5]
                        ],
                    },
                    innocent_explanations=[
                        "Authors quote an LLM response as an explicit example "
                        "(should be marked with quotes and attribution)",
                        "Authors discuss LLMs as a research topic",
                        "Text extracted from a reviewer-revision comment "
                        "embedded in the document",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        # 2) Soft signal: AI-style phrase density
        n_words = len(re.findall(r"\b[a-zA-Z]+\b", data))
        phrase_hits: list[tuple[str, int]] = []
        total_phrase = 0
        for pat, label in _PHRASE_RE:
            count = sum(1 for _ in pat.finditer(data))
            if count > 0:
                phrase_hits.append((label, count))
                total_phrase += count

        density = total_phrase / n_words if n_words else 0
        # 2.0.14: per-provider attribution
        provider, provider_counts = _provider_attribution(data)
        provider_hint = (
            f" Provider profile: GPT={provider_counts['gpt']}, "
            f"Claude={provider_counts['claude']}, "
            f"Gemini={provider_counts['gemini']}. "
            f"Strongest match: {provider}."
        )

        if density >= self.PHRASE_DENSITY_CONCERN:
            severity = (
                Severity.SUSPICIOUS
                if density >= self.PHRASE_DENSITY_SUSPICIOUS
                else Severity.CONCERN
            )
            phrase_hits.sort(key=lambda x: -x[1])
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"AI-style phrase density {density:.4f} "
                        f"({total_phrase} hits / {n_words} words; threshold "
                        f"{self.PHRASE_DENSITY_CONCERN}; "
                        f"most-likely provider: {provider})"
                    ),
                    detail=(
                        f"Text contains {total_phrase} occurrences of "
                        f"{len(phrase_hits)} distinct AI-overused phrases. "
                        "These phrases appear at elevated frequency in "
                        "LLM-generated text relative to typical academic "
                        "writing (Kobak et al. 2025)."
                        + provider_hint
                    ),
                    test_statistic=density,
                    test_name="AI-phrase density",
                    evidence={
                        "n_words": n_words,
                        "total_phrase_hits": total_phrase,
                        "density": density,
                        "top_hits": phrase_hits[:15],
                        "provider_attribution": provider,
                        "provider_counts": provider_counts,
                    },
                    innocent_explanations=[
                        "Author has a stylistic preference for some of these "
                        "phrases (common in non-native English writers)",
                        "Authors used LLM assistance only for polishing, "
                        "with manual edits (declare in Methods)",
                        "Domain genuinely uses some phrases (e.g., 'pivotal "
                        "role' in cell-signaling)",
                        "Phrase dictionary may over-flag certain disciplines",
                    ],
                    academic_reference=self.academic_basis,
                )
            )
        elif provider != "none":
            # Sub-threshold density but a specific provider dominates →
            # NOTE-level signal worth surfacing.
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name + " — provider attribution",
                    severity=Severity.NOTE,
                    summary=(
                        f"Mild {provider.upper()}-style phrase pattern "
                        f"detected ({provider_counts[provider]} hits)"
                    ),
                    detail=(
                        "Density below CONCERN threshold but the relative "
                        "balance of phrases leans toward a specific LLM "
                        "provider's writing style. NOTE-level signal."
                        + provider_hint
                    ),
                    evidence={
                        "provider_attribution": provider,
                        "provider_counts": provider_counts,
                        "density": density,
                    },
                    innocent_explanations=[
                        "Phrase dictionary overlaps with normal academic "
                        "English; provider attribution is heuristic only",
                        "Author may have consulted a specific LLM "
                        "casually for one paragraph",
                        "Coincidental overlap with the provider's "
                        "fingerprint at low N",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        return findings
