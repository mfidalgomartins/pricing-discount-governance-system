# SQL Modeling Layer

This directory provides a warehouse-oriented modeling flow with three layers:
- `staging`: source-conformed views
- `intermediate`: conformed transaction models
- `marts`: stakeholder-facing analytics tables

Execution is handled by `scripts/run_sql_models.py` or automatically through `scripts/run_pipeline.py`.

Design goals:
- preserve analytical grain integrity
- centralize reusable join logic
- keep metric definitions explicit and reconcilable
- support auditable validation checks
