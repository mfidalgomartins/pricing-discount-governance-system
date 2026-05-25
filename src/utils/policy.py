from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def load_policy_thresholds() -> dict[str, Any]:
    policy_path = Path(__file__).resolve().parents[2] / "config" / "policy_thresholds.json"
    if not policy_path.exists():
        raise FileNotFoundError(f"Policy threshold config not found: {policy_path}")
    return json.loads(policy_path.read_text(encoding="utf-8"))
