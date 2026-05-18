# Answer Style Guide

This project supports two local answer styles. Both styles are context-only and must obey the same safety boundaries: no cloud API, no invented market data, no investment advice, no short-term forecast, and no trade commands.

## standard

`standard` is the default. It is best for short questions, checks, tool-like queries, and direct explanations.

Expected shape:

- concise conclusion
- confirmed facts
- rule-based assessment
- portfolio implication
- data limitations
- observable indicators

## analyst_memo

`analyst_memo` is for longer macro, market-cycle, valuation, historical analogy, and portfolio-impact questions. It should read like a local research memo rather than a mechanical fact table.

Suggested structure:

1. 核心判断
2. 类比成立的部分
3. 类比不成立的部分
4. 真正风险在哪里
5. 对用户判断的修正
6. 需要观察的信号
7. 对当前组合的含义
8. 最终判断

## Required Boundaries

- Do not invent current prices, PE ratios, market caps, media reports, or institutional sources.
- Do not cite Reuters, FactSet, Goldman, Bloomberg, or other external sources unless they are in the local context pack.
- Historical outcomes are historical references, not forecasts.
- Scenario analysis is allowed, but deterministic claims are not.
- Portfolio language must stay in observation, DCA discipline, and rebalancing-framework terms.
- `current_holdings.csv` is a local manually maintained snapshot, not real-time account sync.
- `holdings_updated_at` and `holdings_freshness_status` must remain visible when discussing the user's portfolio.
- 余额宝 / `asset_class=cash` is cash reserve and DCA deduction source; it is excluded from target allocation weights.
- Do not use wording such as “需增加持仓”, “需减持”, “应买入”, “应卖出”, or “立即调整”.

## Fallback Policy

Fallback is not a writing style. It is a safety layer.

Use a context-only fallback only when the model answer shows severe hallucination, context leakage, wrong target ratios, invented dates, invented thresholds, English chatter, Thinking residue, or trade-command wording that cannot be safely repaired. Normal stylistic awkwardness should be handled with repair or accepted if the answer is otherwise safe.
