# GH Actions Monitoring — Phase 1

Small CLI tool to poll GitHub / GitHub Enterprise Actions workflow runs for a repo and generate JSON / CSV / HTML reports.

## Files
- `scripts/fetch_runs.py` — main script (async) to fetch workflow runs and jobs, generate reports.
- `scripts/utils.py` — helper functions and env loader.
- `repos.txt` — list of `owner/repo` entries (one per line).
- `config.yaml` — basic config values.
- `.env.example` — template for environment variables (copy to `.env`).
- `reports/` — output directory for generated reports.

## Quick start

1. Copy `.env.example` to `.env` and set:
   ```ini
   GITHUB_TOKEN=YOUR_TOKEN_WITH_ACTIONS_READ
   API_BASE=https://gitenterprise.xilinx.com/api/v3
