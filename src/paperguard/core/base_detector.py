"""检测器基类。所有检测器继承此类。"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from paperguard.core.types import DetectorResult, Finding


class BaseDetector(ABC):
    """检测器抽象基类。

    每个具体检测器必须定义：
    - id, name: 唯一标识
    - description: 一句话说明
    - academic_basis: 学术引用
    - data_requirements: 需要哪些类型的数据
    - assumption_cluster: 用于证据组合（同 cluster 的检测器不独立）
    """

    id: ClassVar[str] = ""
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    academic_basis: ClassVar[str] = ""
    data_requirements: ClassVar[list[str]] = []
    assumption_cluster: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ != "BaseDetector" and not cls.id:
            raise TypeError(f"{cls.__name__} must define 'id' class attribute")

    @abstractmethod
    def check_applicability(self, data: Any) -> tuple[bool, str]:
        """检查检测器是否适用于当前数据。

        Returns:
            (是否适用, 不适用时的原因)
        """
        ...

    @abstractmethod
    def _detect(self, data: Any, seed: int) -> list[Finding]:
        """执行检测逻辑。子类实现。"""
        ...

    def detect(self, data: Any, seed: int = 42) -> DetectorResult:
        """对外接口：检查适用性后执行检测。"""
        applicable, reason = self.check_applicability(data)

        result = DetectorResult(
            detector_id=self.id,
            applicable=applicable,
            skip_reason=reason if not applicable else None,
            seed=seed,
        )

        if applicable:
            start = time.perf_counter()
            try:
                findings = self._detect(data, seed)
                result.findings = findings
            except Exception as e:
                result.applicable = False
                result.skip_reason = f"Detector raised exception: {type(e).__name__}: {e}"
            result.runtime_seconds = time.perf_counter() - start

        return result
