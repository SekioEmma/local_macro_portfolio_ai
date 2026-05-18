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

## Conversation-Distilled Analyst Memo Style Sample

The `analyst_memo` style should feel like a research note for a personal long-term investor. It should not read like a mechanical checklist, a compliance template, or a table generated for its own sake.

An analyst memo should:

- state the core conclusion directly
- acknowledge the reasonable part of the user's view
- correct overstrong claims without dismissing the concern
- separate similarities from differences
- distinguish a real technology cycle from asset-price overextension
- distinguish a large drawdown, valuation compression, and systemic crisis
- connect the analysis back to the user's portfolio framework
- avoid unnecessary tables when paragraphs are clearer
- avoid invented current prices, PE ratios, market caps, or media sources
- say that local context does not provide current data when those data are absent
- use fallback only for severe hallucination, not normal stylistic imperfection

### Example Skeleton: Current AI Market Versus The 2000 Dot-Com Bubble

核心结论可以先给出：这个类比有合理性，但不能简单说成 2000 年的复刻。合理的部分在于，市场可能同时存在真实技术进步和资产价格提前透支；需要修正的部分在于，技术真实存在并不自动推出危机会在某个具体时间到来。

相似点可以写在情绪和估值压力上：当一个技术主题被广泛相信、资金集中、叙事变得顺畅时，未来收益容易受高预期约束。即使技术方向长期成立，短中期也可能经历杀估值或科技股回撤。

差异点要保持克制：如果本地 context 没有提供当前价格、PE、市值、盈利、现金流或媒体引用，就不要编造这些数据。可以说本地 context 未提供这些最新数据，因此这里只能做一般性框架判断。

对用户判断的修正应当是：担心过热是合理的，但“危机一两年内必然到来”证据不足。更稳妥的表达是，科技股回撤和估值压缩的概率可能上升，但系统性经济危机需要更多证据。

对组合的含义应回到纪律：不清仓、不追涨、不提高纳指权重，把纳指权重控制在既定 `5:2:2:1` 框架内，用 DCA、现金 reserve、freshness 和再平衡评估来处理不确定性。这里不是交易指令，也不提供具体买卖金额。
