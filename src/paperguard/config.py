"""配置系统。"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAPERGUARD_", env_file=".env", extra="ignore")

    email: str = Field("anonymous@example.com", description="用于 API 礼貌池")
    cache_dir: Path = Path.home() / ".paperguard" / "cache"
    seed: int = 42

    # 检测器阈值
    a1_min_n: int = 20
    a1_p_threshold_concern: float = 0.01
    a1_p_threshold_suspicious: float = 1e-6

    a3_eps_relative: float = 0.001
    a3_eps_absolute: float = 1e-9
    a3_min_rows: int = 10

    a5_max_unique_ratio: float = 0.3

    b1_rounding_tolerance: float = 0.005

    openalex_base: str = "https://api.openalex.org"
    crossref_base: str = "https://api.crossref.org"
    unpaywall_base: str = "https://api.unpaywall.org/v2"


def get_settings() -> Settings:
    return Settings()
