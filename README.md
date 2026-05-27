# Local Macro Portfolio AI

Local Macro Portfolio AI is a local personal macro and portfolio research helper. It reads local holdings snapshots, target allocation rules, DCA rules, and public macro/market data, then generates deterministic daily reports, an LLM context pack, and analyst memo inputs.

The project is not an automated trading system. It does not place orders, issue buy/sell instructions, guarantee returns, or predict short-term market moves.

## Current Status

- Default `analyst_memo` provider: DeepSeek V4 Pro.
- Local qwen/Ollama remains available only as a legacy/offline path.
- Deterministic scripts still build the data package before the analyst memo step.
- Generated real outputs under `outputs/` are local artifacts and should not be committed.

## Recommended Workflow

Run from the project root:

```powershell
python scripts/run_market_data_check.py
python scripts/run_daily_report.py
python scripts/run_llm_context_pack.py
python scripts/run_analyst_memo.py
```

For a dry run without calling DeepSeek:

```powershell
python scripts/run_analyst_memo.py --dry-run
```

## Environment Variables

Use environment variables only. Do not write API keys into source files, docs, configs, or committed outputs.

- `DEEPSEEK_API_KEY`
- `FRED_API_KEY`
- `ALPHA_VANTAGE_API_KEY`

## Main Docs

- [Daily workflow](docs/daily_workflow.md)
- [Troubleshooting](docs/troubleshooting.md)
- [MVP release checklist](docs/mvp_release_checklist.md)
- [Project handoff](docs/project_handoff.md)
- [Holdings update workflow](docs/holdings_update_workflow.md)
- [Answer style guide](docs/answer_style_guide.md)
- [Conversation distillation workflow](docs/conversation_distillation_workflow.md)
- [Project status](docs/project_status.md)

## Privacy

Do not commit:

- `.env`
- API keys
- `data/holdings/current_holdings.csv`
- `data/private/`
- generated real `outputs/`
- raw conversation exports
- private account snapshots

## Non-Goals

- No automatic trading.
- No buy/sell commands.
- No guaranteed returns.
- No short-term market forecasts.
- No new financial data sources unless a future stage explicitly adds them.
