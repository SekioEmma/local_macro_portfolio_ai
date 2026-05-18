# MVP Release Checklist

Use this checklist before calling MVP v1 ready for daily personal use.

## Data And Holdings

- `data/holdings/current_holdings.csv` can be read locally.
- `data/holdings/current_holdings.csv` is ignored by Git.
- Cash reserve / 余额宝 is excluded from target allocation weights.
- `holdings_updated_at` is visible in generated outputs.
- `holdings_freshness_status` is visible and correct.
- DCA budget status is shown and consistent with the local policy.

## Reports

- `python scripts/run_portfolio_check.py` completes successfully.
- `python scripts/run_daily_report.py` completes successfully.
- `python scripts/run_llm_context_pack.py` completes successfully.
- `outputs/reports/daily_report.md` does not show `sample_fallback` during real holdings use.
- `outputs/reports/llm_context_pack.md` states data limitations and model boundaries.

## Local Model

- Ollama is running locally.
- `qwen3:4b` is available in `ollama list`.
- `scripts/ask_local_ai.py` uses the configured default model successfully.
- `outputs/reports/latest_llm_answer.md` contains no Thinking residue.
- Answers do not provide trade commands.
- Answers do not invent context-external market data.
- Severe hallucination or forbidden output triggers context-only fallback.

## Evaluation

- `python scripts/run_llm_eval.py` completes successfully.
- `pass_rate = 1.0`.
- `failed = 0`.
- Analyst memo cases are covered.
- Evaluation reports include answer mode and fallback metadata.

## Privacy

- `.env` is ignored by Git.
- `data/holdings/current_holdings.csv` is ignored by Git.
- `outputs/` generated artifacts are ignored by Git.
- `data/private/` is ignored by Git.
- Raw conversations are not committed.
- API keys are not committed.
- Private account snapshots are not committed.

## Git And Documentation

- `git status` is clean before tagging or sharing.
- Important phases have commits.
- `README.md` describes the current MVP, not the early skeleton.
- `docs/project_status.md` is updated.
- `docs/daily_workflow.md` explains normal use.
- `docs/troubleshooting.md` covers common failures.
- `docs/conversation_distillation_workflow.md` explains private conversation handling.
