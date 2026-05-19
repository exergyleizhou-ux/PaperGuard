"""生成耿同学风格的造假数据用于测试。

异常特征：
- Treatment_OD - Control_OD 恒定差值 0.30（违反真实仪器噪声）
- Control_OD 末位强烈偏向 0 和 5
- Cell_Count 末位强制 0 或 5
- Viability_Percent 取自离散有限集合
"""
from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any


def generate_fabricated(n: int = 70, seed: int = 42) -> list[dict[str, Any]]:
    random.seed(seed)
    rows: list[dict[str, Any]] = []

    biased_last_digits = [0, 0, 0, 5, 5, 5, 5, 1, 2, 7]
    integer_parts = [1, 2, 3]
    second_digits = [0, 4, 5, 9]
    viability_set = [0.1, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2]

    for i in range(n):
        ip = random.choice(integer_parts)
        d2 = random.choice(second_digits)
        d3 = random.choice(biased_last_digits)
        control = round(ip + d2 / 10 + d3 / 100, 2)

        treatment = round(control + 0.30, 2)

        base = random.randint(300, 700) * 10
        last = random.choice([0, 5])
        cell_count = base * 10 + last

        viability = random.choice(viability_set)

        rows.append(
            {
                "Replicate": i + 1,
                "Control_OD": control,
                "Treatment_OD": treatment,
                "Viability_Percent": f"{viability}%",
                "Cell_Count": cell_count,
            }
        )

    return rows


def main() -> None:
    rows = generate_fabricated()
    out_path = Path(__file__).parent / "fabricated_geng_style.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
