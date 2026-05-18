# Troubleshooting

This guide covers the common MVP v1 failure modes for the local deterministic pipeline and the local Ollama Q&A layer.

## Ollama Connection Failed

Typical symptoms:

- `WinError 10061`
- `connection refused`
- `memory layout cannot be allocated`
- model health check fails before answer generation

Checks:

```powershell
ollama list
```

Open or query the local tag endpoint:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

Fixes:

- Start the Ollama desktop app.
- Confirm the configured model exists in `ollama list`.
- Confirm `configs/llm.yaml` still points to the local endpoint.
- Check `OLLAMA_MODELS` if models are stored outside the default location.
- If `memory layout cannot be allocated` appears, close memory-heavy applications and check Windows virtual memory/pagefile settings.
- If `qwen3:4b` is unavailable or unhealthy, the script should report model health failure or use its context-only safety behavior where configured. Do not switch the default model as part of troubleshooting unless that is an explicit project decision.

## Thinking Output Appears

Some local models may emit Thinking-style text. The project does not rely on `/no_think` being honored.

Keep these protections enabled:

- `strip_thinking_output`
- `clean_model_answer`
- answer validation in `ask_local_ai.py`
- eval checks for `Thinking`, `Thinking Process`, and `done thinking`

If Thinking residue appears in `latest_llm_answer.md`, treat it as a regression and rerun the eval set after fixing cleanup.

## Chinese Text Looks Garbled

Examples of encoding trouble:

- `鎽╂牴`
- `绾虫柉`
- `骞垮彂`

Checks and fixes:

- Save `data/holdings/current_holdings.csv` as UTF-8 or UTF-8-sig.
- Keep Chinese fund names in the CSV, but avoid copying through tools that silently change encoding.
- The reader has encoding fallback, but a badly saved file can still corrupt text before the pipeline sees it.
- If garbled fund names reach reports, resave the CSV with UTF-8/UTF-8-sig and rerun the daily workflow.

## sample_fallback Reappears

`sample_fallback` means the system is not using the intended local real holdings snapshot.

Check:

```powershell
Test-Path data/holdings/current_holdings.csv
git ls-files data/holdings/current_holdings.csv
```

Expected:

- `Test-Path` should be `True` for real local use.
- `git ls-files` should print nothing for `current_holdings.csv`.

Also check:

- the file name is exactly `current_holdings.csv`
- required CSV fields match the template
- fund rows have valid `asset_class`
- 余额宝 uses `asset_class=cash`
- `updated_at` is present and parseable

After fixing the file, rerun:

```powershell
python scripts/run_portfolio_check.py
python scripts/run_daily_report.py
python scripts/run_llm_context_pack.py
```

## Holdings Freshness Is Old

Freshness is computed from `updated_at` in `current_holdings.csv`:

| Age | Status |
| --- | --- |
| 0-7 days | `fresh` |
| 8-14 days | `aging` |
| 15-30 days | `stale` |
| More than 30 days | `very_stale` |
| Missing or invalid | `unknown` |

If the status is `stale`, `very_stale`, or `unknown`, update the local holdings snapshot manually and set `updated_at` on each refreshed row. The assistant must continue to describe it as a local snapshot, not a real-time account sync.

## Output Uses Context-Only Fallback

Context-only fallback is expected when the first model answer has severe issues, such as:

- invented prices, PE ratios, market caps, dates, or sources
- external citations not present in local context
- wrong target allocation
- Thinking residue
- deterministic short-term prediction
- trade-command wording
- treating an old holdings snapshot as real-time account sync

If fallback becomes frequent on normal questions, inspect:

- prompt shape in `src/llm/prompt_builder.py`
- answer style settings in `configs/answer_style.yaml`
- guardrail classification in `scripts/ask_local_ai.py`
- eval coverage in `configs/eval_questions.yaml`

Do not loosen factual constraints just to make answers sound more natural. Prefer better prompts, style examples, or repair behavior while keeping context-only boundaries intact.
