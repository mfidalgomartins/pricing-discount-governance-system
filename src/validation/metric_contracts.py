from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _result_row(
    contract_table: str,
    check_name: str,
    passed: bool,
    detail: str,
    severity: str = "High",
) -> dict:
    return {
        "contract_table": contract_table,
        "check_name": check_name,
        "status": "PASS" if passed else "FAIL",
        "severity": severity,
        "detail": detail,
    }


def _load_contracts(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Metric contract config not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def _resolve_table(
    table_name: str,
    spec: dict,
    processed_tables: dict[str, pd.DataFrame],
    outputs_dir: Path,
) -> pd.DataFrame | None:
    source = spec.get("source", "processed")
    if source == "processed":
        return processed_tables.get(table_name)

    if source == "output":
        csv_name = spec.get("csv")
        if not csv_name:
            return None
        csv_path = outputs_dir / csv_name
        if not csv_path.exists():
            return None
        return pd.read_csv(csv_path)

    return None


def validate_metric_contracts(
    processed_tables: dict[str, pd.DataFrame],
    outputs_dir: Path,
    config_path: Path,
) -> tuple[pd.DataFrame, bool]:
    contracts = _load_contracts(config_path)
    table_specs = contracts.get("tables", {})

    checks: list[dict] = []

    for table_name, spec in table_specs.items():
        table = _resolve_table(table_name, spec, processed_tables, outputs_dir)
        if table is None:
            checks.append(
                _result_row(
                    table_name,
                    "table_exists",
                    False,
                    "table source unavailable for contract",
                )
            )
            continue

        checks.append(
            _result_row(
                table_name,
                "table_exists",
                True,
                f"rows={len(table)} cols={len(table.columns)}",
                severity="Low",
            )
        )

        required_columns = spec.get("required_columns", [])
        missing_columns = [col for col in required_columns if col not in table.columns]
        checks.append(
            _result_row(
                table_name,
                "required_columns_present",
                len(missing_columns) == 0,
                "missing=" + ", ".join(missing_columns) if missing_columns else "all present",
            )
        )

        if missing_columns:
            continue

        primary_key = spec.get("primary_key", [])
        if isinstance(primary_key, str):
            primary_key = [primary_key]
        if primary_key:
            missing_pk_cols = [col for col in primary_key if col not in table.columns]
            if missing_pk_cols:
                checks.append(_result_row(table_name, "primary_key_columns_present", False, f"missing={missing_pk_cols}"))
            else:
                duplicate_keys = int(table.duplicated(subset=primary_key).sum())
                checks.append(
                    _result_row(
                        table_name,
                        "primary_key_uniqueness",
                        duplicate_keys == 0,
                        f"primary_key={primary_key}, duplicate_rows={duplicate_keys}",
                    )
                )

        not_null_keys = spec.get("not_null_keys")
        if not_null_keys is None:
            not_null_keys = [col for col in required_columns if col.endswith("_id") or col in {"order_date", "order_month"}]
        missing_not_null_cols = [col for col in not_null_keys if col not in table.columns]
        if missing_not_null_cols:
            checks.append(_result_row(table_name, "not_null_key_columns_present", False, f"missing={missing_not_null_cols}"))

        null_rate_cols = [col for col in not_null_keys if col in table.columns]
        if null_rate_cols:
            null_rate_series = table[null_rate_cols].isna().mean().sort_values(ascending=False)
            max_null_rate = float(null_rate_series.iloc[0]) if not null_rate_series.empty else 0.0
            checks.append(
                _result_row(
                    table_name,
                    "key_null_rate",
                    max_null_rate == 0.0,
                    f"max_null_rate={max_null_rate:.4f}",
                )
            )

        for bound_spec in spec.get("bounds", []):
            col = bound_spec["column"]
            if col not in table.columns:
                checks.append(_result_row(table_name, f"bound_{col}", False, "column missing for bounds check"))
                continue

            series = pd.to_numeric(table[col], errors="coerce")
            valid_mask = series.notna()
            violations = table[col].notna() & series.isna()

            min_value = bound_spec.get("min")
            max_value = bound_spec.get("max")
            if min_value is not None:
                violations = violations | (valid_mask & (series < min_value))
            if max_value is not None:
                violations = violations | (valid_mask & (series > max_value))

            violation_count = int(violations.sum())
            checks.append(
                _result_row(
                    table_name,
                    f"bound_{col}",
                    violation_count == 0,
                    f"violations={violation_count}, min={min_value}, max={max_value}; non-numeric values count as violations",
                )
            )

        for col, allowed in spec.get("allowed_values", {}).items():
            if col not in table.columns:
                checks.append(_result_row(table_name, f"allowed_values_{col}", False, "column missing"))
                continue

            invalid = (~table[col].isin(allowed)) & table[col].notna()
            invalid_count = int(invalid.sum())
            checks.append(
                _result_row(
                    table_name,
                    f"allowed_values_{col}",
                    invalid_count == 0,
                    f"invalid_rows={invalid_count}",
                )
            )

    report = pd.DataFrame(checks)
    if report.empty:
        report = pd.DataFrame(columns=["contract_table", "check_name", "status", "severity", "detail"])

    is_valid = bool((report["status"] == "PASS").all()) if not report.empty else False
    return report, is_valid
