# Security Policy

## Scope

This repository is a self-contained analytics project built entirely on **synthetic data**.
It contains no production credentials, no personal data, and no required network services. The
practical security surface is therefore limited to the integrity of the code and its
inputs.

## Supported version

Only the latest `main` is maintained. Released artefacts are reproducible from source.

## Reporting a vulnerability

If you discover a security issue — for example a path-traversal or code-injection vector
in the data-loading, table-naming, or report-generation paths — please **do not open a
public issue**. Instead email the maintainer:

- **Miguel Fidalgo Martins** — mfidalgomartins@gmail.com

Include a description, reproduction steps, and the affected file or command.

## Hardening already in place

- `src/utils/paths.resolve_project_path` rejects paths that escape the project root.
- `src/utils/io._validate_table_name` restricts table names to a safe character set,
  blocking directory traversal via crafted bundle keys.
- I/O helpers validate input types before touching the filesystem.
- Dashboard JSON escapes HTML-significant characters before entering an inline script,
  preventing source labels from terminating the script element.
- All dependencies are fully pinned in [`requirements.lock`](requirements.lock); CI runs
  `pip check` for incompatible resolutions and `pip-audit` for published vulnerabilities.
- Dependabot monitors dependencies (see [.github/dependabot.yml](.github/dependabot.yml)).
