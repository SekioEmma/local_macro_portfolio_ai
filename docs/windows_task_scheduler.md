# Windows Task Scheduler

This project can refresh deterministic reports manually or through Windows Task Scheduler.

## Manual Run

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/update_daily_report.ps1
```

## Task Scheduler Settings

Create a basic task or a custom task with these action settings:

Program:

```text
powershell.exe
```

Arguments:

```text
-ExecutionPolicy Bypass -File "G:\local_macro_portfolio_ai\local_macro_portfolio_ai\scripts\update_daily_report.ps1"
```

Start in:

```text
G:\local_macro_portfolio_ai\local_macro_portfolio_ai
```

Suggested triggers:
- At log on
- Daily at a fixed time

## Requirements

- `.env` must already exist locally and contain `FRED_API_KEY` and `ALPHA_VANTAGE_API_KEY`.
- The Conda hook path in `scripts/update_daily_report.ps1` must exist:
  `E:\software\miniConda\shell\condabin\conda-hook.ps1`
- The Conda environment `portfolio_ai` must already be available.
- If `data/holdings/current_holdings.csv` does not exist, the portfolio step may use `sample_fallback`.
- Alpha Vantage free quota is limited, so avoid frequent repeated runs.

## Outputs

- Latest reports are overwritten in `outputs/reports/`.
- Daily report snapshots are archived in `outputs/archive/YYYY-MM-DD/`.
- Logs are appended to `outputs/logs/update_daily_report_YYYY-MM-DD.log`.
- Same-day archive runs overwrite files with the same names in the same date directory.
- Raw history JSON caches under `data/history/` are local cache files and are not copied into daily archives.

## Safety Boundaries

- This task does not connect to an LLM.
- This task does not call the OpenAI API.
- This task does not train models.
- This task does not generate investment advice or forecasts.
- Do not commit `.env`, real holdings files, manual market data files, raw history JSON, logs, or archive snapshots.
