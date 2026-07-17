# Contributing

Thanks for taking the time to contribute. This project values reproducibility and
clear quality gates, so the contribution loop is deliberately simple and fully scripted.

## Development setup

```bash
make install                      # create .venv and install the pinned toolchain
.venv/bin/pre-commit install      # install local git hooks (optional but recommended)
```

Runtime and CI tooling (ruff, mypy, pytest) are pinned in
[`requirements.lock`](requirements.lock) and declared in [`pyproject.toml`](pyproject.toml).
CI runs the same checks directly rather than invoking the local hook wrapper.

## The quality gate

Before opening a pull request, run the network-independent local quality gate:

```bash
make check
```

`make check` runs, in order:

| Step | Command | What it enforces |
|---|---|---|
| Lint | `make lint` | ruff style and correctness rules |
| Format | `make format-check` | ruff formatting (line length 100) |
| Types | `make typecheck` | mypy on `src` |
| Compile | `make compile` | every module byte-compiles |
| Tests | `make test` | pytest with a 90% coverage gate |
| Preflight | `make preflight` | required files and artifacts present |

Run `make audit` before a release candidate to query the Python Packaging Advisory Database for known vulnerabilities in the pinned dependency set. CI enforces this network-dependent check separately, then adds a smoke pipeline run and release gate so `make check` remains usable offline.

To auto-fix style and formatting issues:

```bash
make format
make lint        # ruff also reports auto-fixable issues
```

## Coding standards

- Target Python 3.12; keep full type annotations (`from __future__ import annotations`).
- The formatter owns line length (100). Do not hand-wrap to satisfy a linter.
- New behaviour needs a test. Coverage must stay at or above 90%.
- Keep governed decision thresholds and policy in [`config/`](config/). Give exploratory
  analytical heuristics explicit names and document their interpretation.
- Scripts may bootstrap `sys.path`; that is the only sanctioned `E402` exception.

## Pull requests

1. Branch from `main`.
2. Make the change plus its tests and docs.
3. Run `make check` — it must exit 0.
4. Keep the PR focused; describe the change and how you verified it.

## Reporting issues

Open a GitHub issue describing the expected vs. actual behaviour and the exact command
used. For anything security-sensitive, follow [SECURITY.md](SECURITY.md) instead.
