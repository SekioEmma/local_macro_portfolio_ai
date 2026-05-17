# Holdings Update Workflow

`data/holdings/current_holdings.csv` is the local user holdings snapshot used by the portfolio and local LLM pipeline. It is manually maintained from user-confirmed Alipay fund screenshots and is not a real-time account sync.

## Storage Rules

- `current_holdings.csv` contains personal holdings data and must stay local.
- Do not commit `data/holdings/current_holdings.csv` to Git.
- Do not commit generated files under `outputs/`.
- Keep `.env` and API keys out of Git.

## Update Frequency

- Update the snapshot weekly or monthly during normal use.
- Update immediately after any large fund purchase, sale, conversion, or other material account change.
- Update `updated_at` on every row whenever the snapshot is refreshed.
- If rows have different `updated_at` values, the system uses the newest date and reports mixed row freshness.

## Freshness Status

The pipeline classifies holdings freshness from `updated_at`:

| Age | Status |
| --- | --- |
| 0-7 days | fresh |
| 8-14 days | aging |
| 15-30 days | stale |
| More than 30 days | very_stale |
| Missing or unparseable date | unknown |

Stale, very stale, or unknown snapshots must not be treated as real-time account data.

## Cash Reserve

- 余额宝 should use `asset_class=cash`.
- Cash is a reserve and DCA deduction source.
- Cash is included in total account value.
- Cash is excluded from target allocation weights.
- Do not interpret the current cash reserve as money that should be immediately invested.

## Manual Update Steps

1. Open the latest Alipay fund holdings screenshots.
2. Update each fund row in `data/holdings/current_holdings.csv`:
   - `asset_name`
   - `fund_code`
   - `asset_class`
   - `current_value`
   - `cost_basis`
   - `profit_loss`
   - `currency`
   - `updated_at`
   - `notes`
3. Keep `asset_class=cash` for 余额宝.
4. Keep active DCA and paused status notes in `notes` if the CSV schema has no dedicated fields.
5. Save the file locally.

## Refresh Commands

After updating the CSV, run:

```powershell
python scripts/run_portfolio_check.py
python scripts/run_daily_report.py
python scripts/run_llm_context_pack.py
python scripts/ask_local_ai.py "当前市场是否过热？对我的组合意味着什么？"
```

The outputs are written under `outputs/reports/` and remain ignored by Git.
