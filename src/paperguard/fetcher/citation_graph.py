"""引用图基础设施 — 用 OpenAlex referenced_works 构建 2-hop 子图。

设计原则：
- 每个 OpenAlex /works 调用走 fetcher.cache（默认 7 天 TTL），重复扫
  同一 DOI 不重复打 API
- 默认 2-hop，节点上限 max_nodes（默认 200），防止图爆炸
- 节点带作者列表 + 年份 + 期刊；边方向：A → B 表示"A 引用 B"
- 返回 networkx.DiGraph

学术依据：
Cabanac et al. (2025) "A paper mill detection model based on citation
manipulation paradigm." Journal of Data and Information Science.
PDCN 模型使用 5M-节点完整图；本工具用同样的图签名但局部子图，覆盖
单论文级别的快速筛查。
"""
from __future__ import annotations

from collections import deque
from typing import Any

from paperguard.fetcher.cache import cached_call
from paperguard.fetcher.openalex import OpenAlexClient


@cached_call("openalex.work_full", ttl=7 * 24 * 3600)
def _fetch_work_full(_client: OpenAlexClient, doi_or_id: str) -> dict[str, Any] | None:
    """带缓存的全 work 拉取（含 referenced_works）。"""
    if doi_or_id.startswith("W") and doi_or_id[1:].isdigit():
        try:
            return _client._get(f"/works/{doi_or_id}")
        except Exception:  # noqa: BLE001
            return None
    return _client.get_work_by_doi(doi_or_id)


def _normalize_id(work_id: str) -> str:
    """OpenAlex 返回的 id 可能是 URL 形式；统一截短为 W12345..."""
    if not work_id:
        return ""
    return work_id.rsplit("/", 1)[-1]


def _extract_author_ids(work: dict[str, Any]) -> list[str]:
    auths = work.get("authorships", []) or []
    out: list[str] = []
    for a in auths:
        author_obj = a.get("author") or {}
        aid = _normalize_id(author_obj.get("id", "") or "")
        if aid:
            out.append(aid)
    return out


def build_citation_subgraph(
    root_doi: str,
    max_hops: int = 2,
    max_nodes: int = 200,
    email: str | None = None,
) -> Any:
    """从 root DOI 出发构建 ≤ max_hops 层引用 + 被引子图。

    返回 networkx.DiGraph，节点属性：
        title, year, journal, authors (list of OpenAlex author IDs),
        is_root (only true for the root node)
    边：u → v 表示 u 引用了 v。

    注意：OpenAlex 给的是"我引用了哪些"，反向需要单独查 cited_by_api_url，
    本实现只走 referenced_works（正向引用图）。这已足够检测大多数论文工厂
    签名（互引环、过度自引、密集小团 clique）。
    """
    import networkx as nx  # type: ignore[import-untyped]

    client = OpenAlexClient(email=email)
    graph = nx.DiGraph()

    try:
        root_work = _fetch_work_full(client, root_doi)
        if not root_work:
            return graph

        root_id = _normalize_id(root_work.get("id", ""))
        if not root_id:
            return graph

        def add_node_from(work: dict[str, Any], is_root: bool = False) -> str:
            wid = _normalize_id(work.get("id", ""))
            if not wid or wid in graph:
                return wid
            graph.add_node(
                wid,
                title=(work.get("title") or work.get("display_name") or "")[:200],
                year=work.get("publication_year"),
                journal=(
                    (work.get("primary_location") or {}).get("source") or {}
                ).get("display_name", ""),
                authors=_extract_author_ids(work),
                is_root=is_root,
            )
            return wid

        add_node_from(root_work, is_root=True)

        # BFS, level by level
        frontier: deque[tuple[str, int]] = deque([(root_id, 0)])
        visited: set[str] = {root_id}

        while frontier and len(graph) < max_nodes:
            current_id, depth = frontier.popleft()
            if depth >= max_hops:
                continue

            # Need the full work record to know referenced_works
            current_work: dict[str, Any] | None
            if depth == 0:
                current_work = root_work
            else:
                current_work = _fetch_work_full(client, current_id)
                if not current_work:
                    continue
            assert current_work is not None

            refs = current_work.get("referenced_works", []) or []
            for ref_url in refs[:30]:  # cap per-node fanout
                if len(graph) >= max_nodes:
                    break
                ref_id = _normalize_id(ref_url)
                if not ref_id:
                    continue
                if ref_id not in graph:
                    ref_work = _fetch_work_full(client, ref_id)
                    if ref_work:
                        add_node_from(ref_work)
                    else:
                        # 仍然作为占位节点存在（孤立）
                        graph.add_node(
                            ref_id,
                            title="",
                            year=None,
                            journal="",
                            authors=[],
                            is_root=False,
                        )
                graph.add_edge(current_id, ref_id)
                if ref_id not in visited:
                    visited.add(ref_id)
                    frontier.append((ref_id, depth + 1))
    finally:
        client.close()

    return graph
