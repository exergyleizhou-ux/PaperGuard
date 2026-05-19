"""PubPeer 客户端 — 查询某 DOI 是否有公开质疑。

PubPeer 提供两种访问：
1. 公开 HTML 页面 https://pubpeer.com/publications?q=<DOI>
2. 开发者 API（需 dev_key）

为避免分发 key、保持依赖最小，本实现走 HTML 公开页面，
仅做"是否存在评论 + 评论数"的轻量检测。详细评论内容应由
用户手动到 PubPeer 上查看。

学术依据：
PubPeer 是公开的同行匿名 / 实名质疑平台。一篇被广泛质疑的论文
通常在 PubPeer 上会有数条评论，是审视该工作时不容忽视的信号。
"""
from __future__ import annotations

import re

import httpx

from paperguard.config import get_settings


class PubPeerClient:
    """轻量 PubPeer 查询客户端。"""

    PAGE_URL = "https://pubpeer.com/publications"

    def __init__(self, email: str | None = None, timeout: float = 30.0) -> None:
        self.email = email or get_settings().email
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": (
                    f"PaperGuard/0.1.0 (mailto:{self.email}; "
                    "purpose: integrity screening)"
                )
            },
            follow_redirects=True,
        )

    def get_comments(self, doi: str) -> dict[str, int | str | bool] | None:
        """查询 DOI 是否有 PubPeer 评论。

        Returns:
            None 当请求失败或解析失败时。
            dict:
                - has_comments: bool
                - comment_count: int (best-effort, 0 = 未知)
                - search_url: 用户可点开查看的页面 URL
        """
        doi_clean = doi.strip().lower().replace("https://doi.org/", "")
        search_url = f"{self.PAGE_URL}?q={httpx.QueryParams({'q': doi_clean})['q']}"
        try:
            r = self.client.get(self.PAGE_URL, params={"q": doi_clean})
            r.raise_for_status()
        except httpx.HTTPError:
            return None

        html = r.text
        # 检测页面是否含"X comments" 文本（典型 PubPeer 结果页样式）
        match = re.search(r"(\d+)\s+comments?", html, re.IGNORECASE)
        if match:
            count = int(match.group(1))
            return {
                "has_comments": count > 0,
                "comment_count": count,
                "search_url": search_url,
            }

        # 没匹配到数字：判断是否含"No publications found"
        if re.search(r"No publications found", html, re.IGNORECASE):
            return {
                "has_comments": False,
                "comment_count": 0,
                "search_url": search_url,
            }

        # 解析不确定，返回 unknown 状态而非假装无评论
        return {
            "has_comments": False,
            "comment_count": 0,
            "search_url": search_url,
            "parser_uncertain": True,
        }

    def close(self) -> None:
        self.client.close()
