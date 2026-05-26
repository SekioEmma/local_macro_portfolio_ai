from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProviderResponse:
    provider: str
    model: str
    answer_text: str
    latency_seconds: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    estimated_cost_cny: float | None = None
    raw_error: str | None = None
    success: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def empty_usage() -> dict[str, Any]:
    return {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cache_hit_tokens": None,
        "cache_miss_tokens": None,
    }
