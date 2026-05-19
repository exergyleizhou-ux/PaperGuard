"""LLM 解释器测试（不联网，仅验证 opt-in 行为与 prompt 构造）。"""
from __future__ import annotations

from paperguard.core.types import Finding, Severity
from paperguard.llm.explainer import LLMExplainer


def _sample_finding() -> Finding:
    return Finding(
        detector_id="A1",
        detector_name="Terminal Digit",
        severity=Severity.CONCERN,
        summary="末位偏差",
        detail="详细",
        p_value=0.001,
        evidence={"n": 50},
        innocent_explanations=["仪器量化"],
    )


def test_disabled_by_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("PAPERGUARD_LLM_PROVIDER", raising=False)
    e = LLMExplainer()
    assert e.enabled is False
    assert e.explain(_sample_finding()) is None


def test_explicit_provider_enables(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    e = LLMExplainer(provider="openai")
    assert e.enabled is True


def test_unknown_provider_raises_inside_call() -> None:
    """未知 provider 不该让主流程崩溃，应被 except 吞掉返回 None。"""
    e = LLMExplainer(provider="nonexistent")
    assert e.enabled is True
    assert e.explain(_sample_finding()) is None


def test_prompt_contains_finding_fields() -> None:
    e = LLMExplainer(provider="openai")
    prompt = e._build_user_prompt(_sample_finding())
    assert "A1" in prompt
    assert "末位偏差" in prompt
    assert "0.001" in prompt
    assert "仪器量化" in prompt
