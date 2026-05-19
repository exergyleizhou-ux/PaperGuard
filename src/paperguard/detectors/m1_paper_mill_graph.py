"""M1 — Paper-mill 引用图签名检测。

学术依据：
Cabanac, Magazinov, Labbé (2025) "A paper mill detection model based on
citation manipulation paradigm." Journal of Data and Information Science.
Sci Rep (2024) "Identifying fabricated networks within authorship-for-sale
enterprises." (Cell Press shared series).

四类经典签名（每类独立 Finding）：

1. **互引环（reciprocal citation cycles）**：A→B 且 B→A，密度异常
2. **小团 clique**：N 个节点构成完全图，且共享 ≥50% 参考文献
3. **过度自引集团**：一组节点共享同一作者，且这些节点之间互引率
   远高于本领域基线
4. **citation rings of length 3–4**：A→B→C→A 这种闭环数量异常

输入：networkx.DiGraph（来自 fetcher.citation_graph.build_citation_subgraph）
"""
from __future__ import annotations

from typing import Any, ClassVar

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


class M1PaperMillGraphDetector(BaseDetector):
    """局部引用子图上的论文工厂签名检测。"""

    id: ClassVar[str] = "M1"
    name: ClassVar[str] = "Paper-Mill Citation Graph Signatures"
    description: ClassVar[str] = (
        "检测引用子图中的互引环 / 小团 clique / 过度自引集团 / 短引用闭环。"
    )
    academic_basis: ClassVar[str] = (
        "Cabanac, Magazinov, Labbé (2025) JDIS. "
        "Network-based paper-mill detection methodologies."
    )
    data_requirements: ClassVar[list[str]] = ["citation_subgraph"]
    assumption_cluster: ClassVar[str] = "citation_network"

    # 阈值（基于 Cabanac 2025 + 合成测试经验）
    MIN_NODES: ClassVar[int] = 8
    RECIPROCAL_RATIO_CONCERN: ClassVar[float] = 0.10  # 10% 边互引
    RECIPROCAL_RATIO_SUSPICIOUS: ClassVar[float] = 0.20
    CLIQUE_MIN_SIZE: ClassVar[int] = 4
    CLIQUE_SHARED_REF_THRESHOLD: ClassVar[float] = 0.50
    SELF_CITE_RATIO_CONCERN: ClassVar[float] = 0.40
    SELF_CITE_RATIO_SUSPICIOUS: ClassVar[float] = 0.60
    CYCLE_COUNT_CONCERN: ClassVar[int] = 3
    CYCLE_COUNT_SUSPICIOUS: ClassVar[int] = 8

    def check_applicability(self, data: Any) -> tuple[bool, str]:
        try:
            import networkx as nx  # type: ignore[import-untyped]  # noqa: F401
        except ImportError:
            return False, "networkx not installed"
        # data 应是 DiGraph
        if not hasattr(data, "nodes") or not hasattr(data, "edges"):
            return False, "Expected networkx.DiGraph"
        if data.number_of_nodes() < self.MIN_NODES:
            return False, (
                f"Subgraph needs ≥ {self.MIN_NODES} nodes (got "
                f"{data.number_of_nodes()})"
            )
        return True, ""

    def _detect(self, data: Any, seed: int) -> list[Finding]:
        import networkx as nx

        graph = data
        findings: list[Finding] = []

        # === 1. Reciprocal citations
        reciprocal_pairs = []
        for u, v in graph.edges():
            if graph.has_edge(v, u) and u < v:  # 去重
                reciprocal_pairs.append((u, v))
        n_edges = graph.number_of_edges()
        reciprocal_ratio = (
            2 * len(reciprocal_pairs) / n_edges if n_edges else 0.0
        )

        if reciprocal_ratio >= self.RECIPROCAL_RATIO_CONCERN:
            sev = (
                Severity.SUSPICIOUS
                if reciprocal_ratio >= self.RECIPROCAL_RATIO_SUSPICIOUS
                else Severity.CONCERN
            )
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=sev,
                    summary=(
                        f"Reciprocal-citation ratio {reciprocal_ratio:.1%} "
                        f"({len(reciprocal_pairs)} pairs / {n_edges} edges)"
                    ),
                    detail=(
                        "在 academic citation 中，A→B 同时 B→A 的双向引用罕见"
                        "（通常因为时间先后只可能单向）。论文工厂常通过协调"
                        "出版时间制造大量互引以放大引用数。"
                        f"本子图 {len(reciprocal_pairs)} 对互引 / {n_edges} 总边"
                        f"= {reciprocal_ratio:.1%}（健康文献 < 5%）。"
                    ),
                    test_statistic=reciprocal_ratio,
                    test_name="reciprocal/total edge ratio",
                    evidence={
                        "n_nodes": graph.number_of_nodes(),
                        "n_edges": n_edges,
                        "reciprocal_pair_count": len(reciprocal_pairs),
                        "reciprocal_ratio": reciprocal_ratio,
                        "example_pairs": reciprocal_pairs[:10],
                    },
                    innocent_explanations=[
                        "同一研究领域的两篇论文在 revision 阶段互相增加引用",
                        "Editorial / commentary 与其响应论文互引（合法）",
                        "同一作者团队的连续工作互相引用（合法但若占比极高需声明）",
                        "时间窗口内的紧密合作者团体（小领域常见）",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        # === 2. Citation rings (length 3-4)
        try:
            # 把方向忽略后看 cycle，再 verify 是 directed cycle
            cycles_3 = [
                c for c in nx.simple_cycles(graph, length_bound=4)
                if 3 <= len(c) <= 4
            ]
        except Exception:  # noqa: BLE001
            cycles_3 = []

        n_cycles = len(cycles_3)
        if n_cycles >= self.CYCLE_COUNT_CONCERN:
            sev = (
                Severity.SUSPICIOUS
                if n_cycles >= self.CYCLE_COUNT_SUSPICIOUS
                else Severity.CONCERN
            )
            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=sev,
                    summary=(
                        f"{n_cycles} short citation cycles (length 3–4) "
                        f"detected"
                    ),
                    detail=(
                        f"在子图中发现 {n_cycles} 个长度 3–4 的有向引用闭环 "
                        "（A→B→C→A）。短闭环在合规引文中数学上很难出现"
                        "（时间因果约束 + 论文工厂典型签名）。"
                    ),
                    test_statistic=float(n_cycles),
                    test_name="short cycles count",
                    evidence={
                        "n_cycles": n_cycles,
                        "example_cycles": [
                            [str(n) for n in c] for c in cycles_3[:5]
                        ],
                    },
                    innocent_explanations=[
                        "OpenAlex referenced_works 数据可能含日期错位"
                        "（罕见但已记录）",
                        "preprint 系统允许后版本互引（应在 Methods 声明）",
                        "Errata / corrections 形成的合法闭环",
                        "本工具只看 OpenAlex 子图，可能含数据库噪声",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        # === 3. Dense small cliques sharing references
        # 用 undirected projection 找 clique
        undirected = graph.to_undirected()
        cliques = [
            c for c in nx.find_cliques(undirected)
            if len(c) >= self.CLIQUE_MIN_SIZE
        ]
        for clique in cliques[:5]:
            # 检查 shared references
            ref_sets: list[set[str]] = []
            for node in clique:
                if node in graph:
                    out_refs = set(graph.successors(node))
                    if out_refs:
                        ref_sets.append(out_refs)
            if len(ref_sets) < 2:
                continue
            # 交集 / 平均集大小
            common = set.intersection(*ref_sets)
            avg_size = sum(len(s) for s in ref_sets) / len(ref_sets)
            if avg_size == 0:
                continue
            shared_ratio = len(common) / avg_size

            if shared_ratio >= self.CLIQUE_SHARED_REF_THRESHOLD:
                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=Severity.SUSPICIOUS,
                        summary=(
                            f"Clique of {len(clique)} papers share "
                            f"{shared_ratio:.0%} of their references"
                        ),
                        detail=(
                            f"{len(clique)} 个相互引用的论文共享 {len(common)} "
                            "个相同参考文献，远高于自然合作者团体的预期。"
                            "已知论文工厂签名：批量生产时引用模板被复用。"
                        ),
                        test_statistic=shared_ratio,
                        test_name="shared-reference ratio",
                        evidence={
                            "clique_size": len(clique),
                            "clique_members": [str(n) for n in clique],
                            "shared_reference_count": len(common),
                            "avg_reference_count": avg_size,
                            "shared_ratio": shared_ratio,
                        },
                        innocent_explanations=[
                            "Clique 都来自同一专题或 special issue，共享方法学引用"
                            "（合法但应在论文中可识别）",
                            "Systematic review 集群本就引用相同基础文献",
                            "小领域共享核心 canonical references",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )

        # === 4. Self-citation cluster
        # 找一组节点：共享同一 author 集合 + 互引率高
        author_to_nodes: dict[str, set[str]] = {}
        for n, attrs in graph.nodes(data=True):
            for aid in attrs.get("authors", []):
                author_to_nodes.setdefault(aid, set()).add(n)

        for aid, nodes in author_to_nodes.items():
            if len(nodes) < 3:
                continue
            internal_edges = sum(
                1 for u, v in graph.edges()
                if u in nodes and v in nodes
            )
            potential = len(nodes) * (len(nodes) - 1)
            if potential == 0:
                continue
            cluster_density = internal_edges / potential

            if cluster_density >= self.SELF_CITE_RATIO_CONCERN:
                sev = (
                    Severity.SUSPICIOUS
                    if cluster_density >= self.SELF_CITE_RATIO_SUSPICIOUS
                    else Severity.CONCERN
                )
                findings.append(
                    Finding(
                        detector_id=self.id,
                        detector_name=self.name,
                        severity=sev,
                        summary=(
                            f"Author {aid} appears on {len(nodes)} nodes with "
                            f"internal citation density {cluster_density:.1%}"
                        ),
                        detail=(
                            f"作者 OpenAlex ID {aid} 出现在子图 {len(nodes)} "
                            f"个节点上，且这些节点间内部互引比例 "
                            f"{cluster_density:.1%}（{internal_edges} 内部边 / "
                            f"{potential} 可能边）。"
                            "过度自我引用是论文工厂的次级签名。"
                        ),
                        test_statistic=cluster_density,
                        test_name="author-cluster internal citation density",
                        evidence={
                            "author_id": aid,
                            "n_nodes_in_cluster": len(nodes),
                            "internal_edges": internal_edges,
                            "potential_edges": potential,
                            "density": cluster_density,
                        },
                        innocent_explanations=[
                            "高产作者的纵向研究自然互引（合法）",
                            "Series of papers on one topic by same group",
                            "Cumulative publications in PhD thesis context",
                            "OpenAlex author disambiguation 可能错把不同人合并",
                        ],
                        academic_reference=self.academic_basis,
                    )
                )
                # 每个作者只触发一次最严重的
                break

        return findings
