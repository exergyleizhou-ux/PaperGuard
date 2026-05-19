"""pytest 共享 fixtures。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def fabricated_data(fixtures_dir: Path) -> pd.DataFrame:
    """加载造假测试数据。如果文件缺失，提供内置 fallback。"""
    csv_path = fixtures_dir / "fabricated_geng_style.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path)
    rng = np.random.default_rng(42)
    n = 70
    control = rng.choice([2.50, 2.51, 2.52, 1.50, 1.51, 3.50, 3.51], size=n)
    treatment = control + 0.3
    return pd.DataFrame(
        {
            "Replicate": range(1, n + 1),
            "Control_OD": control,
            "Treatment_OD": treatment,
            "Cell_Count": rng.choice([3500, 4000, 4500, 5000, 5500], size=n),
        }
    )


@pytest.fixture
def genuine_data(fixtures_dir: Path) -> pd.DataFrame:
    """加载真实对照数据。如果文件缺失，模拟独立同分布数据。"""
    csv_path = fixtures_dir / "genuine_random.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path)
    rng = np.random.default_rng(42)
    n = 70
    control = rng.normal(2.5, 0.3, size=n).round(3)
    treatment = (control + rng.normal(0.3, 0.05, size=n)).round(3)
    return pd.DataFrame(
        {
            "Replicate": range(1, n + 1),
            "Control_OD": control,
            "Treatment_OD": treatment,
            "Cell_Count": rng.integers(3000, 6000, size=n),
        }
    )
