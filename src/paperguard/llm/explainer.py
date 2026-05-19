"""LLM 辅助 Finding 解释（**opt-in**）。

默认关闭。启用方式：
- 环境变量 `PAPERGUARD_LLM_PROVIDER=openai`（或 anthropic / ollama）
- 对应密钥：`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
- 自托管：`OLLAMA_BASE=http://localhost:11434`

设计原则：
1. LLM 输出**只是辅助**，绝不替代 detector 的客观证据
2. Prompt 强制限定为"解释统计含义 + 给非专家可读说明"，不允许 LLM 做有/无造假判断
3. 始终把 finding.evidence 原文一起喂给模型避免幻觉
4. 失败 / 没配置时静默返回 None，主流程不中断
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from paperguard.core.types import Finding

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a careful scientific-integrity assistant.

You will receive a single statistical or forensic Finding from PaperGuard.
Your job:
- Explain in 2-3 plain-language sentences what the finding means.
- Translate any p-values or test statistics into intuitive terms.
- Restate (do NOT add to) the innocent explanations the detector already listed.

You MUST NOT:
- Claim the paper is fraudulent.
- Use the words "fraud", "fabrication", "misconduct", "造假".
- Invent evidence the Finding does not contain.
- Add new innocent explanations the detector did not list.

Return JSON with exactly two keys: {"plain_summary": str, "lay_translation": str}.
"""


@dataclass
class LLMExplanation:
    plain_summary: str
    lay_translation: str


class LLMExplainer:
    """LLM 解释器。未配置时所有方法返回 None。"""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.provider = provider or os.environ.get("PAPERGUARD_LLM_PROVIDER")
        self.model = model or os.environ.get("PAPERGUARD_LLM_MODEL")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.provider)

    def explain(self, finding: Finding) -> LLMExplanation | None:
        if not self.enabled:
            return None
        try:
            return self._call_provider(finding)
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM call failed: %s", e)
            return None

    def _build_user_prompt(self, finding: Finding) -> str:
        return (
            f"Detector: {finding.detector_id} — {finding.detector_name}\n"
            f"Severity: {finding.severity.label}\n"
            f"Summary: {finding.summary}\n"
            f"Detail: {finding.detail}\n"
            f"p-value: {finding.p_value}\n"
            f"Test statistic ({finding.test_name}): {finding.test_statistic}\n"
            f"Evidence: {json.dumps(finding.evidence, ensure_ascii=False, default=str)}\n"
            f"Innocent explanations from detector:\n"
            + "\n".join(f"- {e}" for e in finding.innocent_explanations)
        )

    def _call_provider(self, finding: Finding) -> LLMExplanation:
        if self.provider == "openai":
            return self._call_openai(finding)
        if self.provider == "anthropic":
            return self._call_anthropic(finding)
        if self.provider == "ollama":
            return self._call_ollama(finding)
        raise ValueError(f"Unknown LLM provider: {self.provider}")

    def _call_openai(self, finding: Finding) -> LLMExplanation:
        import httpx

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        model = self.model or "gpt-4o-mini"
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_user_prompt(finding)},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        return LLMExplanation(
            plain_summary=str(data.get("plain_summary", "")),
            lay_translation=str(data.get("lay_translation", "")),
        )

    def _call_anthropic(self, finding: Finding) -> LLMExplanation:
        import httpx

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        model = self.model or "claude-sonnet-4-6"
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 400,
                "system": _SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": self._build_user_prompt(finding)},
                ],
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        content = r.json()["content"][0]["text"]
        data = json.loads(content)
        return LLMExplanation(
            plain_summary=str(data.get("plain_summary", "")),
            lay_translation=str(data.get("lay_translation", "")),
        )

    def _call_ollama(self, finding: Finding) -> LLMExplanation:
        import httpx

        base = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
        model = self.model or "llama3"
        r = httpx.post(
            f"{base}/api/chat",
            json={
                "model": model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_user_prompt(finding)},
                ],
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        content = r.json()["message"]["content"]
        data = json.loads(content)
        return LLMExplanation(
            plain_summary=str(data.get("plain_summary", "")),
            lay_translation=str(data.get("lay_translation", "")),
        )
