# Project Handoff

This document is the preferred starting point for a new ChatGPT/Codex window working on Local Macro Portfolio AI.

## Project Identity

Local Macro Portfolio AI is a local-first personal research and asset-allocation assistant. It reads local portfolio snapshots, user allocation policy, DCA rules, public macro/market data, and generated reports, then builds a local LLM context pack for context-only answers.

The project is not an automatic trading system. It does not guarantee returns, does not predict short-term market direction, and must not output concrete buy/sell instructions.

## Repository And Branches

- Local path: `G:\local_macro_portfolio_ai\local_macro_portfolio_ai`
- GitHub repository: `SekioEmma/local_macro_portfolio_ai`
- Current local branch at handoff time: `master`
- Remote: `origin`
- GitHub may also have a `main` branch from repository initialization. Prefer consolidating future work onto one primary branch after reviewing the remote default branch.

## Current MVP Capabilities

- Reads local `data/holdings/current_holdings.csv` when present.
- Falls back to sample holdings only when the real local snapshot is missing.
- Treats `asset_class=cash` / 余额宝 as cash reserve and DCA deduction source.
- Excludes cash reserve from target allocation weights.
- Computes target allocation drift for `sp500:nasdaq100:short_bond:gold = 5:2:2:1`.
- Tracks holdings snapshot freshness using `updated_at`.
- Generates portfolio snapshot, daily report, market temperature, history features, macro regime history, and LLM context pack.
- Uses local Ollama with default model `qwen3:4b`.
- Supports `standard` and `analyst_memo` answer styles.
- Records answer modes: `natural`, `repaired`, and `context_only_fallback`.
- Uses context-only fallback for severe hallucination, Thinking residue, fabricated data, wrong allocation facts, or trade-command wording.
- Maintains a local eval suite in `configs/eval_questions.yaml`.

## Core User Policy

- Long-term personal research and asset-allocation reflection.
- No automatic trading.
- No short-term forecasts.
- No concrete buy/sell amounts.
- Target allocation: `sp500:nasdaq100:short_bond:gold = 5:2:2:1`.
- Cash reserve / 余额宝 is not idle cash to deploy immediately.
- Rebalancing preference: threshold review and year-end review over frequent trading.
- Preferred language: underweight/overweight, relative to target, exposure, observation direction, DCA discipline, and rebalancing review.
- Forbidden language: “需增加持仓”, “需减持”, “应买入”, “应卖出”, “立即调整”, or any exact trade amount.

## Privacy Rules

Do not commit or expose:

- `.env`
- API keys or tokens
- `data/holdings/current_holdings.csv`
- `data/private/`
- raw conversation exports
- generated `outputs/` reports or answers
- private account snapshots
- exact real account values copied from local outputs

Tracked documentation should describe policies and architecture, not current private account values.

## Key Files

- `README.md`: public entry point and quick start.
- `docs/project_status.md`: chronological project status.
- `docs/project_handoff.md`: this new-window handoff.
- `docs/daily_workflow.md`: normal daily operation.
- `docs/troubleshooting.md`: common local failures.
- `docs/mvp_release_checklist.md`: MVP v1 readiness checklist.
- `docs/holdings_update_workflow.md`: local holdings update process.
- `docs/answer_style_guide.md`: answer style and analyst memo expectations.
- `docs/conversation_distillation_workflow.md`: private conversation distillation rules.
- `docs/user_investment_policy.md`: stable investment policy.
- `configs/user_profile.yaml`: target allocation and DCA policy.
- `configs/llm.yaml`: local model configuration.
- `configs/eval_questions.yaml`: local eval cases.
- `scripts/run_portfolio_check.py`: portfolio snapshot entrypoint.
- `scripts/run_daily_report.py`: daily report entrypoint.
- `scripts/run_llm_context_pack.py`: LLM context pack entrypoint.
- `scripts/ask_local_ai.py`: local model Q&A entrypoint.
- `scripts/run_llm_eval.py`: local answer eval entrypoint.

## Daily Commands

```powershell
python scripts/run_portfolio_check.py
python scripts/run_daily_report.py
python scripts/run_llm_context_pack.py
python scripts/ask_local_ai.py "当前市场是否过热？对我的组合意味着什么？"
```

Full deterministic workflow:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/update_daily_report.ps1
```

Eval:

```powershell
python scripts/run_llm_eval.py
```

## GitHub Sync Notes

- The HTTPS remote uses `https://github.com/SekioEmma/local_macro_portfolio_ai.git`.
- If HTTPS fails with connection reset, keep the Git proxy settings aligned with the user's local proxy.
- If HTTPS credentials fail in non-interactive Codex, ask the user to run the final `git push` from their PowerShell session.
- Before each push, check:

```powershell
git status --short --untracked-files=all
git ls-files .env data/holdings/current_holdings.csv data/private outputs/reports outputs/answers outputs/eval outputs/model_eval
```

Only `.gitkeep` files under ignored output directories should be tracked.

## Current Next Step

The MVP is ready for daily-use observation. Future work should prefer small, reviewable phases:

1. Keep GitHub branch/default-branch organization tidy.
2. Preserve privacy boundaries before every push.
3. Improve analyst memo quality only through distilled rules, eval cases, and prompt/style guidance unless the user explicitly asks for another direction.
4. Do not switch the default model, expand guardrails, train/fine-tune, or add cloud APIs without an explicit phase request.
