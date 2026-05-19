"""轻量 fetcher 缓存层。

外部 API（OpenAlex / CrossRef / Unpaywall / PubPeer）有速率限制和"礼貌池"
要求。重复扫描同一 DOI 时不应重复打 API。

策略：
- 用 diskcache 把 JSON 响应缓存到 settings.cache_dir / "http"
- 默认 7 天 TTL
- 提供 cache_get / cache_set / cache_decorator 三个 API
"""
from __future__ import annotations

import functools
import hashlib
import json
from collections.abc import Callable
from typing import Any, TypeVar

from paperguard.config import get_settings

T = TypeVar("T")

_DEFAULT_TTL = 7 * 24 * 3600  # 7 days


def _get_cache() -> Any:
    """惰性打开 diskcache。"""
    from diskcache import Cache  # type: ignore[import-untyped]

    cache_dir = get_settings().cache_dir / "http"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return Cache(str(cache_dir))


def _key_for(namespace: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    blob = json.dumps([args, sorted(kwargs.items())], default=str, sort_keys=True)
    digest = hashlib.sha256(blob.encode()).hexdigest()[:24]
    return f"{namespace}:{digest}"


def cache_get(namespace: str, key: str) -> Any:
    """直接取，命中返回 value, miss 返回 None。"""
    cache = _get_cache()
    full_key = f"{namespace}:{key}"
    return cache.get(full_key)


def cache_set(
    namespace: str, key: str, value: Any, ttl: int = _DEFAULT_TTL
) -> None:
    cache = _get_cache()
    full_key = f"{namespace}:{key}"
    cache.set(full_key, value, expire=ttl)


def cached_call(
    namespace: str, ttl: int = _DEFAULT_TTL
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """装饰器：缓存被装饰函数的返回值。

    用例：

        @cached_call("openalex.work", ttl=86400)
        def get_work_by_doi(self, doi: str): ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # 跳过 self：first arg 是非内置类型且 func 看起来是 method
            # 简单判据：args[0] 含 __dict__（class instance），且其 type 名包含
            # "Client" 或 "Detector"（PaperGuard 的约定）
            key_args: tuple[Any, ...] = args
            if (
                args
                and hasattr(args[0], "__dict__")
                and type(args[0]).__name__.endswith(("Client", "Detector"))
            ):
                key_args = args[1:]
            full_key = _key_for(namespace, key_args, kwargs)
            cache = _get_cache()
            hit = cache.get(full_key)
            if hit is not None:
                return hit  # type: ignore[no-any-return]
            result = func(*args, **kwargs)
            try:
                cache.set(full_key, result, expire=ttl)
            except Exception:  # noqa: BLE001
                pass  # cache failure should never break the call
            return result

        return wrapper

    return decorator
