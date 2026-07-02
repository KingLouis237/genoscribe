# GenoScribe CLI Packaging Log (2026-02-16)

## Goal
Make GenoScribe runnable as a CLI command: `genoscribe`

## Why
- Reduce environment drift and missing dependency errors.
- Reduce variables: one command → one entrypoint → one behavior.
- Improve reproducibility via conda environment + pyproject manifest.

## Steps
1) Created `genoscribe/` package folder.
2) Added `genoscribe/cli.py` that imports `genoscribe_app` and runs `genoscribe_app.main()`.
3) Added `pyproject.toml`:
   - Declares dependencies.
   - Defines CLI entrypoint: `genoscribe = genoscribe.cli:main`.
4) Added `environment.yml` for conda-based reproducible install.

## Validation
- `conda env create -f environment.yml`
- `conda activate genoscribe`
- `genoscribe` launches the app.

## Notes / Debugging
- If `genoscribe` not found: env not activated or install failed.
- If import error: confirm `genoscribe_app.py` exists at repo root and has `main()`.
