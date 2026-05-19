"""M1 paper-mill graph detector tests with synthetic citation subgraphs."""
from __future__ import annotations

import networkx as nx

from paperguard.core.types import Severity
from paperguard.detectors.m1_paper_mill_graph import M1PaperMillGraphDetector


def _make_clean_graph(n: int = 15) -> nx.DiGraph:
    """Pure tree-like citation graph: no reciprocal, no cycles, no overlap."""
    g = nx.DiGraph()
    for i in range(n):
        g.add_node(
            f"W{i}",
            title=f"Paper {i}",
            year=2020 + (i % 4),
            authors=[f"A{i}"],  # 每节点独立作者
            journal="J",
            is_root=(i == 0),
        )
    # 单向 tree edges
    for i in range(1, n):
        g.add_edge(f"W{i}", f"W{(i - 1) // 2}")
    return g


def _make_reciprocal_ring(n: int = 8) -> nx.DiGraph:
    """All-pairs reciprocal — extreme paper-mill signature."""
    g = nx.DiGraph()
    for i in range(n):
        g.add_node(
            f"W{i}",
            title=f"Mill paper {i}",
            year=2024,
            authors=[f"A{i}"],
            journal="J",
            is_root=(i == 0),
        )
    for i in range(n):
        for j in range(n):
            if i != j:
                g.add_edge(f"W{i}", f"W{j}")
    return g


def _make_dense_clique_with_shared_refs() -> nx.DiGraph:
    """4 papers互相引用 + 共享 ≥50% 外部参考。"""
    g = nx.DiGraph()
    # 4 clique members
    for i in range(4):
        g.add_node(
            f"M{i}",
            title=f"Clique {i}",
            year=2023,
            authors=[f"A{i}"],
            journal="J",
            is_root=(i == 0),
        )
    # 6 共享外部参考 (W10-W15)
    for i in range(10, 16):
        g.add_node(f"W{i}", title=f"Ref {i}", year=2018, authors=[], journal="J", is_root=False)
    # Clique edges
    for i in range(4):
        for j in range(4):
            if i != j:
                g.add_edge(f"M{i}", f"M{j}")
    # 每个 clique 成员都引用全部 6 个共享外部
    for i in range(4):
        for j in range(10, 16):
            g.add_edge(f"M{i}", f"W{j}")
    return g


def _make_self_citation_cluster() -> nx.DiGraph:
    """同一作者出现在 5 个节点上，节点间引用率高。"""
    g = nx.DiGraph()
    same_author = "A_PROLIFIC"
    for i in range(5):
        g.add_node(
            f"S{i}",
            title=f"Self {i}",
            year=2020 + i,
            authors=[same_author, f"A_co_{i}"],
            journal="J",
            is_root=(i == 0),
        )
    for i in range(5):
        g.add_node(
            f"E{i}",
            title=f"Ext {i}",
            year=2015,
            authors=[f"Other_{i}"],
            journal="J",
            is_root=False,
        )
    # 高密度内部互引（每对都有边）
    for i in range(5):
        for j in range(5):
            if i != j:
                g.add_edge(f"S{i}", f"S{j}")
    # 一些外部引用以稀释总边数
    for i in range(5):
        g.add_edge(f"S{i}", f"E{i}")
    return g


# === Tests ===

def test_m1_inapplicable_too_small() -> None:
    g = nx.DiGraph()
    g.add_node("W1")
    result = M1PaperMillGraphDetector().detect(g, seed=42)
    assert not result.applicable


def test_m1_clean_graph_passes() -> None:
    g = _make_clean_graph(n=20)
    result = M1PaperMillGraphDetector().detect(g, seed=42)
    assert result.applicable
    # 干净 tree 无信号
    assert len(result.findings) == 0


def test_m1_flags_reciprocal_ring() -> None:
    g = _make_reciprocal_ring(n=8)
    result = M1PaperMillGraphDetector().detect(g, seed=42)
    assert result.applicable
    recip_findings = [
        f for f in result.findings
        if "reciprocal" in f.summary.lower()
    ]
    assert len(recip_findings) >= 1
    assert recip_findings[0].severity >= Severity.SUSPICIOUS


def test_m1_flags_shared_reference_clique() -> None:
    g = _make_dense_clique_with_shared_refs()
    result = M1PaperMillGraphDetector().detect(g, seed=42)
    assert result.applicable
    clique_findings = [
        f for f in result.findings
        if "clique" in f.summary.lower() or "share" in f.summary.lower()
    ]
    assert len(clique_findings) >= 1


def test_m1_flags_self_citation_cluster() -> None:
    g = _make_self_citation_cluster()
    result = M1PaperMillGraphDetector().detect(g, seed=42)
    assert result.applicable
    self_findings = [
        f for f in result.findings
        if "A_PROLIFIC" in f.summary or "internal citation" in f.summary.lower()
    ]
    assert len(self_findings) >= 1
    assert self_findings[0].severity >= Severity.CONCERN
