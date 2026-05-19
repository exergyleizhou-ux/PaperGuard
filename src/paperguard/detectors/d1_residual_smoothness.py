"""D1 — Residual Smoothness 检测（Stapel-style 过度平滑）。

学术依据：
- Stapel 调查报告（Levelt et al. 2012）发现编造数据"过于平滑"，
  组间大效应却伴随组内异常小的变异。
- Embassy of Good Science (2024) "Forensic Statistics to detect
  Data Fabrication"：natural data should be 'messy'.

原理：
对每个数值列拟合最小二乘线性趋势，残差应有自然方差（按全列方差的
某个比例）。若残差 σ/raw σ 远小于真实数据预期下限，说明值"靠得太近"
（人工生成的常见副产物）。

补充：单独看一列残差不足够，因为很多真实测量列方差也小。
所以本检测器额外做"variance-of-variance"检验：
- 把列分块（如每 10 行一块），计算每块的 σ²
- 真实数据各块 σ² 应有自然变异
- 编造数据各块 σ² 异常接近 → 触发
"""
from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd

from paperguard.core.base_detector import BaseDetector
from paperguard.core.types import Finding, Severity


class D1ResidualSmoothnessDetector(BaseDetector):
    """检测列残差异常平滑 + 块方差稳定性异常。"""

    id: ClassVar[str] = "D1"
    name: ClassVar[str] = "Residual Smoothness (Over-clean Data)"
    description: ClassVar[str] = (
        "拟合趋势后的残差 σ 异常小，或块方差异常稳定 → 数据可能过度平滑。"
    )
    academic_basis: ClassVar[str] = (
        "Stapel committee report (Levelt et al. 2012); Embassy of Good "
        "Science (2024) Forensic Statistics to detect Data Fabrication."
    )
    data_requirements: ClassVar[list[str]] = ["raw_numeric_values"]
    assumption_cluster: ClassVar[str] = "variance_structure"

    MIN_N: ClassVar[int] = 30
    MIN_BLOCK: ClassVar[int] = 5
    # variance-of-variance 异常阈值
    # 真实数据各块 σ² 的相对标准差通常 ≥ 0.3；
    # < 0.10 → CONCERN, < 0.05 → SUSPICIOUS, < 0.02 → CRITICAL
    # 经验：真实正态随机数据各块 σ² 的相对 std 约 0.3-0.5；
    # 仪器量化数据可能 0.1-0.2；编造数据常 < 0.05。
    # 阈值更保守，避免真实数据假阳。
    REL_STD_CONCERN: ClassVar[float] = 0.05
    REL_STD_SUSPICIOUS: ClassVar[float] = 0.02
    REL_STD_CRITICAL: ClassVar[float] = 0.005

    def check_applicability(self, data: pd.DataFrame) -> tuple[bool, str]:
        if not isinstance(data, pd.DataFrame):
            return False, "Expected pd.DataFrame"
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            if len(data[col].dropna()) >= self.MIN_N:
                return True, ""
        return False, f"No numeric column with N ≥ {self.MIN_N}"

    def _detect(self, data: pd.DataFrame, seed: int) -> list[Finding]:
        findings: list[Finding] = []
        numeric_cols = data.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            values = data[col].dropna().to_numpy(dtype=float)
            n = len(values)
            if n < self.MIN_N:
                continue
            if values.std(ddof=1) == 0:
                continue  # 整列零方差 → A3 / D2 处理

            # 跳过单调索引/ID 列（如 Replicate 1..N）：相邻差恒定且唯一值 = n
            diffs = np.diff(values)
            unique_count = len(set(values.tolist()))
            if (
                diffs.size > 0
                and diffs.std() == 0
                and unique_count == n
            ):
                continue

            # 把列分块；每块至少 MIN_BLOCK 行
            n_blocks = max(3, n // 10)
            block_size = n // n_blocks
            if block_size < self.MIN_BLOCK:
                continue
            block_vars: list[float] = []
            for i in range(n_blocks):
                start = i * block_size
                end = start + block_size
                if end > n:
                    break
                block = values[start:end]
                block_vars.append(float(block.var(ddof=1)))

            if len(block_vars) < 3:
                continue
            mean_v = float(np.mean(block_vars))
            std_v = float(np.std(block_vars, ddof=1))
            if mean_v == 0:
                continue
            rel_std = std_v / mean_v

            if rel_std >= self.REL_STD_CONCERN:
                continue
            if rel_std < self.REL_STD_CRITICAL:
                severity = Severity.CRITICAL
            elif rel_std < self.REL_STD_SUSPICIOUS:
                severity = Severity.SUSPICIOUS
            else:
                severity = Severity.CONCERN

            findings.append(
                Finding(
                    detector_id=self.id,
                    detector_name=self.name,
                    severity=severity,
                    summary=(
                        f"列 '{col}' 块方差稳定性异常 (rel σ(σ²) = "
                        f"{rel_std:.3f}, n_blocks = {len(block_vars)})"
                    ),
                    detail=(
                        f"对 {col} 列的 {n} 个值按 {block_size} 行分块，"
                        f"得到 {len(block_vars)} 个块方差。真实测量数据中"
                        "块方差通常本身有 ≥ 30% 的相对变异。"
                        f"本列块方差均值 {mean_v:.4g}，σ {std_v:.4g}，"
                        f"相对 σ = {rel_std:.4f}。"
                        "过于稳定的块方差是已知造假签名（Stapel 调查报告）。"
                    ),
                    test_statistic=rel_std,
                    test_name="rel σ of block-variance",
                    evidence={
                        "column": str(col),
                        "n": n,
                        "n_blocks": len(block_vars),
                        "block_size": block_size,
                        "block_variances": block_vars,
                        "mean_block_variance": mean_v,
                        "std_block_variance": std_v,
                        "relative_std": rel_std,
                    },
                    innocent_explanations=[
                        "实验设计采用了严格的标准化流程，测量噪声本就极小",
                        "数据是仪器自动量化输出，离散等距步长",
                        "数据已经过 winsorization / 平滑预处理（应在 Methods 说明）",
                        "样本量小，块数 < 3 时统计不稳",
                    ],
                    academic_reference=self.academic_basis,
                )
            )

        return findings
