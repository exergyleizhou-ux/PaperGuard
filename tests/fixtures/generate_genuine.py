"""生成符合真实实验特征的对照数据。

特征：
- 高斯噪声而非离散值
- 处理-对照差值有真实变异（非恒定）
- 末位数字分布均匀
- 细胞计数有真实变异
"""
from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any


def generate_genuine(n: int = 70, seed: int = 42) -> list[dict[str, Any]]:
    random.seed(seed)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        control_true = random.gauss(2.5, 0.3)
        control_obs = round(control_true + random.gauss(0, 0.005), 3)
        treatment_obs = round(
            control_true + 0.3 + random.gauss(0, 0.05) + random.gauss(0, 0.005),
            3,
        )
        viability = round(random.uniform(0.05, 1.5), 2)
        cell_count = int(random.gauss(4500, 800))

        rows.append(
            {
                "Replicate": i + 1,
                "Control_OD": control_obs,
                "Treatment_OD": treatment_obs,
                "Viability_Percent": f"{viability}%",
                "Cell_Count": cell_count,
            }
        )
    return rows


def main() -> None:
    rows = generate_genuine()
    out_path = Path(__file__).parent / "genuine_random.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
