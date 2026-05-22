# MVP v1 Observation Plan

## 1. Observation status

Local Macro Portfolio AI is now in MVP v1 observation.

The goal of this phase is day-to-day usage observation, not feature expansion, new distillation work, or more refactoring. The current priorities are:

- Stability of the local daily workflow.
- Clear factual boundaries in LLM answers.
- Strong privacy boundaries around account data and generated outputs.
- Long-term investment discipline instead of trade-like instructions.

## 2. Daily usage commands

Recommended daily commands:

```powershell
python scripts/run_daily_report.py
python scripts/run_llm_context_pack.py
```

Optional local Q&A:

```powershell
python scripts/ask_local_ai.py --style analyst_memo "<your question>"
```

`run_llm_eval.py` does not need to run every day. It must run after any code, prompt, config, or eval change. It can also run during weekly or phase-level health checks.

## 3. Weekly health check

Recommended weekly commands:

```powershell
python scripts/run_llm_eval.py
git status --short --untracked-files=all
git ls-files .env
git ls-files data/holdings/current_holdings.csv
git ls-files data/private
git ls-files outputs/reports
git ls-files outputs/answers
git ls-files outputs/eval
git ls-files outputs/model_eval
```

The expected Git tracking result is no private files, with only `.gitkeep` placeholders under ignored output roots where applicable.

## 4. What to record

Record abstract observations only. Do not store full generated answers, raw outputs, screenshots, account snapshots, or original chat transcripts.

Suggested observation fields:

- date
- question summary
- answer_style
- answer_mode
- fallback_reason
- guardrail_triggers summary
- whether final answer was acceptable
- whether there was hallucinated market data
- whether there was trade-like language
- whether cash reserve was misused
- whether current_holdings was described as real-time
- whether the issue is repeated

## 5. Failure categories

Use these categories when summarizing issues:

- first-pass hallucinated market data
- invented external source
- trade-like instruction
- portfolio direction inconsistency
- cash reserve misuse
- current_holdings real-time misstatement
- over-fallback / overly templated answer
- standard concept answer polluted by portfolio context
- missing required macro concept
- eval pass but human fail

## 6. When not to fix immediately

Do not open a development fix for every single anomaly.

- A single fallback is not necessarily a bug.
- A single model fluctuation is not necessarily a bug.
- Do not expand guardrails because of one isolated answer.
- Do not add an eval case because of one isolated answer.
- Do not treat fallback as the desired default writing style.
- Do not write time-sensitive market data into long-term knowledge.

Observation first, then development only when patterns repeat or safety boundaries fail.

## 7. When to open a new development stage

Open a new development stage when one or more of these conditions appears:

- The same failure category appears more than 3 times.
- Eval keeps failing across reruns.
- Daily report generation fails.
- LLM context pack generation fails.
- Private files appear in `git status` or `git ls-files`.
- `ask_local_ai.py` raises runtime errors.
- The model outputs trade-like advice and guardrails do not block it.
- cash reserve or current_holdings boundaries are repeatedly misused.

## 8. Known limitations

- `qwen3:4b` first-pass answers can still be unstable.
- `context_only_fallback` share is currently high.
- The system is an investment research assistant, not an automated trading system.
- The system does not predict short-term market moves.
- The system does not output concrete buy or sell amounts.
- `current_holdings.csv` is a local manual snapshot, not real-time account sync.
- cash reserve / Yu'e Bao is a cash reserve and DCA deduction source, and does not participate in target allocation weights.

## 9. Privacy boundary

Never write these into Git:

- `.env`
- `data/holdings/current_holdings.csv`
- `data/private/*`
- `outputs/reports/*`
- `outputs/answers/*`
- `outputs/eval/*`
- `outputs/model_eval/*`
- raw chat transcripts
- real account screenshots
- complete real account snapshots
- SFT candidate raw text
- preference pair raw text

## 10. Next possible stages

Candidates only; do not execute during MVP v1 observation:

- Semantic eval enhancement
- Answer pipeline extraction
- Line ending normalization with `.gitattributes`
- Additional distilled material landing
- RAG prototype, later only if needed
- Fine-tuning, not in MVP v1
