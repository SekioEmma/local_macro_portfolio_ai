# Daily Workflow

This is the daily operating flow for the local macro portfolio assistant. Deterministic local scripts still generate market data checks, daily reports, and the LLM context pack. The formal analyst memo now defaults to DeepSeek V4 Pro reading the generated context package, with local qwen retained only as legacy/offline fallback.

## Recommended Startup Flow

1. Refresh market data.
2. Refresh the portfolio snapshot and daily report.
3. Refresh the LLM context pack.
4. Generate the analyst memo with the default DeepSeek provider.
5. Review generated files under `outputs/`, which are local and ignored by Git.

## Recommended Commands

Run from the project root:

```powershell
python scripts/run_portfolio_check.py
python scripts/run_market_data_check.py
python scripts/run_daily_report.py
python scripts/run_llm_context_pack.py
python scripts/run_analyst_memo.py
```

The first commands refresh deterministic data and reports. The final command calls the default analyst memo provider configured in `configs/analyst_memo.yaml`, currently `deepseek-pro` / `deepseek-v4-pro`. `DEEPSEEK_API_KEY` must be provided through the environment, never written into config files.

To ask a focused analyst memo question:

```powershell
python scripts/run_analyst_memo.py --question "请基于当前数据包判断：当前更像正常回调、横盘估值消化，还是通胀型利率冲击？并说明对标普、纳指、短债、黄金的组合观察含义。"
```

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

Run `scripts/run_analyst_memo.py` separately when you want a DeepSeek analyst memo.

## Main Output Files

- `outputs/reports/portfolio_snapshot.json`
- `outputs/reports/daily_report.md`
- `outputs/reports/llm_context_pack.md`
- `outputs/analyst_memos/analyst_memo_YYYYMMDD_HHMMSS.md`
- `outputs/analyst_memos/analyst_memo_YYYYMMDD_HHMMSS.json`
- `outputs/reports/latest_llm_answer.md`
- `outputs/answers/YYYY-MM-DD/`
- `outputs/archive/YYYY-MM-DD/`

`outputs/reports/` stores the latest working files. `outputs/archive/YYYY-MM-DD/` stores dated snapshots created by the archive step. `outputs/answers/YYYY-MM-DD/` stores optional legacy local Q&A artifacts.

`outputs/analyst_memos/` stores DeepSeek analyst memo artifacts. These files require human review and must not be committed.

## Privacy Rules

- Do not commit generated `outputs/`.
- Do not commit `data/holdings/current_holdings.csv`.
- Do not commit anything under `data/private/`.
- Do not commit `.env`.
- Do not commit API keys, raw conversation exports, or private account snapshots.
- Do not write `DEEPSEEK_API_KEY`, `FRED_API_KEY`, or `ALPHA_VANTAGE_API_KEY` into tracked files.

## Daily Review Checklist

- `daily_report.md` should not mention `sample_fallback` during real use.
- `portfolio_snapshot.json` should show `holdings_updated_at` and `holdings_freshness_status`.
- `llm_context_pack.md` should describe data limitations and forbidden model behavior.
- `analyst_memos/*.md`, when generated, should show provider/model, human review status, validator flags, and an evidence table.
- DeepSeek analyst memos should not invent FedWatch, PE, forward PE, FactSet, Bloomberg, Reuters, intraday Treasury highs, or trading instructions.
- Local qwen remains available through legacy scripts, but it is not the default analyst memo provider.
