"""检测器注册系统 + 插件发现。

内置检测器在 `register_default()` 中显式注册。
第三方插件通过 Python entry point group `paperguard.detectors` 自动发现：

    # 在第三方包 pyproject.toml 中：
    [project.entry-points."paperguard.detectors"]
    my_detector = "my_package.detectors:MyDetector"

每个 entry point 必须解析为 BaseDetector 的子类（非实例）。
"""
from __future__ import annotations

import logging
from importlib.metadata import entry_points

from paperguard.core.base_detector import BaseDetector

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "paperguard.detectors"


class DetectorRegistry:
    """注册并执行所有可用的检测器（含第三方插件）。"""

    def __init__(self) -> None:
        self._detectors: dict[str, BaseDetector] = {}

    def register(self, detector: BaseDetector) -> None:
        self._detectors[detector.id] = detector

    def register_default(self, load_plugins: bool = True) -> DetectorRegistry:
        """注册内置检测器。load_plugins=True 时同时发现第三方插件。"""
        from paperguard.detectors.a1_terminal_digit import A1TerminalDigitDetector
        from paperguard.detectors.a2_benford import A2BenfordDetector
        from paperguard.detectors.a3_arithmetic import A3ArithmeticRelationDetector
        from paperguard.detectors.a5_decimal_consistency import (
            A5DecimalConsistencyDetector,
        )
        from paperguard.detectors.a6_implausible_values import (
            A6ImplausibleValueDetector,
        )
        from paperguard.detectors.a7_last_digit_five_zero import (
            A7LastDigitFiveZeroDetector,
        )
        from paperguard.detectors.b1_grim import B1GRIMDetector
        from paperguard.detectors.b4_statcheck import B4StatcheckDetector
        from paperguard.detectors.b5_tiva import B5TIVADetector
        from paperguard.detectors.b6_grimmer import B6GRIMMERDetector
        from paperguard.detectors.b7_pcurve import B7PCurveDetector
        from paperguard.detectors.b8_sprite import B8SPRITEDetector
        from paperguard.detectors.c1_carlisle import C1CarlisleDetector
        from paperguard.detectors.d1_residual_smoothness import (
            D1ResidualSmoothnessDetector,
        )
        from paperguard.detectors.d2_missing_pattern import D2MissingPatternDetector
        from paperguard.detectors.e1_icc_independence import (
            E1ICCIndependenceDetector,
        )
        from paperguard.detectors.f1_image_duplication import F1ImageDuplicationDetector
        from paperguard.detectors.f2_internal_duplication import (
            F2InternalDuplicationDetector,
        )
        from paperguard.detectors.f3_splice_forensics import F3SpliceForensicsDetector
        from paperguard.detectors.f4_cross_paper_image import (
            F4CrossPaperImageDetector,
        )
        from paperguard.detectors.f5_exif_clustering import F5ExifClusteringDetector
        from paperguard.detectors.g1_exif_temporal import G1ExifTemporalDetector
        from paperguard.detectors.g3_rsid_forensics import G3RsidForensicsDetector
        from paperguard.detectors.g4_metadata_forensics import (
            G4MetadataForensicsDetector,
        )
        from paperguard.detectors.m1_paper_mill_graph import (
            M1PaperMillGraphDetector,
        )
        from paperguard.detectors.t1_text_similarity import T1TextSimilarityDetector
        from paperguard.detectors.t2_trial_consistency import T2TrialConsistencyDetector
        from paperguard.detectors.t3_data_availability import (
            T3DataAvailabilityDetector,
        )
        from paperguard.detectors.t4_tortured_phrases import T4TorturedPhrasesDetector
        from paperguard.detectors.t5_stylometry import T5StylometryDetector
        from paperguard.detectors.t6_ai_text_heuristic import (
            T6AITextHeuristicDetector,
        )
        from paperguard.detectors.t7_perplexity import T7PerplexityDetector
        from paperguard.detectors.t8_detectgpt import T8DetectGPTDetector

        for detector_cls in (
            A1TerminalDigitDetector,
            A2BenfordDetector,
            A3ArithmeticRelationDetector,
            A5DecimalConsistencyDetector,
            A6ImplausibleValueDetector,
            A7LastDigitFiveZeroDetector,
            B1GRIMDetector,
            B4StatcheckDetector,
            B5TIVADetector,
            B6GRIMMERDetector,
            B7PCurveDetector,
            B8SPRITEDetector,
            C1CarlisleDetector,
            D1ResidualSmoothnessDetector,
            D2MissingPatternDetector,
            E1ICCIndependenceDetector,
            F1ImageDuplicationDetector,
            F2InternalDuplicationDetector,
            F3SpliceForensicsDetector,
            F4CrossPaperImageDetector,
            F5ExifClusteringDetector,
            G1ExifTemporalDetector,
            G3RsidForensicsDetector,
            G4MetadataForensicsDetector,
            M1PaperMillGraphDetector,
            T1TextSimilarityDetector,
            T2TrialConsistencyDetector,
            T3DataAvailabilityDetector,
            T4TorturedPhrasesDetector,
            T5StylometryDetector,
            T6AITextHeuristicDetector,
            T7PerplexityDetector,
            T8DetectGPTDetector,
        ):
            self.register(detector_cls())

        if load_plugins:
            self.load_plugins()

        return self

    def load_plugins(self) -> list[str]:
        """从 entry points 加载第三方检测器。返回成功加载的 ID 列表。"""
        loaded: list[str] = []
        # Python 3.10+ 总是支持 group= kwarg；项目最低要求 3.11，所以直接调用
        eps = entry_points(group=ENTRY_POINT_GROUP)

        for ep in eps:
            try:
                cls = ep.load()
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Failed to load detector plugin %s: %s", ep.name, e
                )
                continue
            if not isinstance(cls, type) or not issubclass(cls, BaseDetector):
                logger.warning(
                    "Plugin %s did not resolve to a BaseDetector subclass; got %r",
                    ep.name,
                    cls,
                )
                continue
            try:
                instance = cls()
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Plugin %s could not be instantiated: %s", ep.name, e
                )
                continue
            self.register(instance)
            loaded.append(instance.id)
        return loaded

    def get(self, detector_id: str) -> BaseDetector | None:
        return self._detectors.get(detector_id)

    def all(self) -> list[BaseDetector]:
        return list(self._detectors.values())

    def get_by_requirements(self, data_type: str) -> list[BaseDetector]:
        return [d for d in self.all() if data_type in d.data_requirements]
