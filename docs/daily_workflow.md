# Daily Workflow

This is the MVP v1 daily operating flow for the local macro portfolio assistant. It keeps deterministic reports, portfolio context, and optional local LLM answers refreshed without using cloud LLM APIs.

## Recommended Startup Flow

1. Confirm Ollama is running if you plan to ask the local model.
2. Refresh the portfolio snapshot.
3. Refresh the daily report.
4. Refresh the LLM context pack.
5. Optionally ask the local AI a context-only question.
6. Review generated files under `outputs/`, which are local and ignored by Git.

## Recommended Commands

Run from the project root:

```powershell
python scripts/run_portfolio_check.py
python scripts/run_daily_report.py
python scripts/run_llm_context_pack.py
python scripts/ask_local_ai.py "当前市场是否过热？对我的组合意味着什么？"
```

The first three commands refresh deterministic data and reports. The final command is optional and calls the local Ollama model configured in `configs/llm.yaml`.

## Full Daily Automation Script

If the PowerShell helper is available, use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/update_daily_report.ps1
```

That script runs the broader deterministic pipeline:

- portfolio check
- market data check
- market temperature check
- daily report
- market history check
- macro regime history check
- LLM context pack
- archive reports

It writes a daily log under `outputs/logs/` and archives the latest reports under `outputs/archive/YYYY-MM-DD/`.

## Main Output Files

- `outputs/reports/portfolio_snapshot.json`
- `outputs/reports/daily_report.md`
- `outputs/reports/llm_context_pack.md`
- `outputs/reports/latest_llm_answer.md`
- `outputs/answers/YYYY-MM-DD/`
- `outputs/archive/YYYY-MM-DD/`

`outputs/reports/` stores the latest working files. `outputs/archive/YYYY-MM-DD/` stores dated snapshots created by the archive step. `outputs/answers/YYYY-MM-DD/` stores optional local Q&A artifacts.

## Privacy Rules

- Do not commit generated `outputs/`.
- Do not commit `data/holdings/current_holdings.csv`.
- Do not commit anything under `data/private/`.
- Do not commit `.env`.
- Do not commit API keys, raw conversation exports, or private account snapshots.

## Daily Review Checklist

- `daily_report.md` should not mention `sample_fallback` during real use.
- `portfolio_snapshot.json` should show `holdings_updated_at` and `holdings_freshness_status`.
- `llm_context_pack.md` should describe data limitations and forbidden model behavior.
- `latest_llm_answer.md`, when generated, should contain no Thinking residue and no context-invented market data.
