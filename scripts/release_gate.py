from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.paths import CONFIGS_DIR, OUTPUTS_DIR
from src.validation.release_gate import evaluate_release_gate


def main() -> int:
    summary_path = OUTPUTS_DIR / "final_validation_summary.json"
    metric_contract_path = OUTPUTS_DIR / "metric_contract_validation.csv"
    policy_path = CONFIGS_DIR / "release_policy.json"

    report, passed = evaluate_release_gate(
        summary_path=summary_path,
        metric_contract_report_path=metric_contract_path,
        policy_path=policy_path,
        outputs_dir=OUTPUTS_DIR,
    )

    print(f"Release gate passed: {passed}")
    print(f"Release readiness state: {report['release_readiness_state']}")
    print("Report written to outputs/release/release_gate_report.json")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
