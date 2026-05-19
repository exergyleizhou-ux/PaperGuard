"""PubPeer 客户端测试。"""
from __future__ import annotations

import pytest

from paperguard.fetcher.pubpeer import PubPeerClient


@pytest.mark.network
def test_pubpeer_search_smoke() -> None:
    """对一个稳定的 DOI 跑查询，验证客户端能拿到响应。

    用 Watson-Crick 1953（极不太可能有 PubPeer 评论，作为"未质疑"对照）。
    """
    client = PubPeerClient(email="test@example.com")
    try:
        result = client.get_comments("10.1038/171737a0")
        assert result is not None
        assert "search_url" in result
        assert isinstance(result["comment_count"], int)
    finally:
        client.close()
