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

## Analyst Memo Pattern: Geopolitics, Rates, Inflation Shock, And Portfolio Implications

Use this pattern when the user connects geopolitical tension, diplomatic talks, energy supply risk, Treasury yields, Fed policy repricing, long-duration equities, gold, bonds, and portfolio implications.

### Applicable Scenarios

- Geopolitical conflict, shipping disruption, oil supply risk, or energy-cost shock.
- Diplomatic de-escalation that lowers tail risk but does not resolve structural trade, technology, supply-chain, security, or financial constraints.
- Treasury yield rise, bond price pressure, equity valuation compression, or stock/bond/gold simultaneous weakness.
- User asks whether these signals mean a systemic crisis is starting.

### Terms To Correct

- If the user says bonds are rising while the context is yield rise, correct the wording: yields are rising, bond prices are falling.
- Distinguish ordinary risk-off from inflation shock.
- Distinguish valuation compression from systemic crisis.
- Distinguish diplomatic cooling from structural risk resolution.
- Distinguish real technology progress from asset-price overextension.

### Recommended Structure

1. Core judgment: this is a macro-pricing pressure chain, not enough by itself to declare systemic crisis.
2. Clarify the bond wording: yield up means bond price down.
3. Ordinary risk-off versus inflation shock.
4. Transmission chain: geopolitics/energy/shipping/insurance costs -> inflation expectations and Fed policy repricing -> long-end yield or real-rate pressure -> bond prices and high-valuation equities under pressure -> gold may also be pressured by real rates or dollar strength.
5. Diplomatic de-escalation versus structural risk resolution.
6. Valuation compression versus systemic crisis.
7. Monitoring signals.
8. Portfolio implications using only target-relative and review language.

### Required Concepts

- Ordinary risk-off: stocks can fall while long bonds and gold may be supported.
- Inflation shock: oil, shipping, insurance, energy costs, inflation expectations, real rates, or term premium can rise together, so stocks, long bonds, and gold can all be pressured.
- Treasury yields and bond prices move in opposite directions.
- Long-duration growth equities are sensitive to higher discount rates.
- Diplomatic de-escalation can reduce tail risk without removing structural constraints.
- Systemic crisis needs broader evidence: credit spreads, bank or funding stress, earnings expectations, labor data, volatility, dollar funding stress, liquidity anomalies, and QDII subscription/redemption, FX, or NAV conversion abnormality.
- For the user's portfolio, use exposure, relative-to-target, observation direction, DCA discipline, threshold review, and year-end review.

### Forbidden Expressions

- Do not say crisis is certain or already proven by stock/bond/gold weakness alone.
- Do not predict short-term market direction.
- Do not provide exact buy or sell amounts.
- Do not say bonds are rising when the evidence is yield rise unless immediately clarifying the price/yield relationship.
- Do not invent latest Treasury yields, ETF prices, PE ratios, market caps, FedWatch probabilities, Reuters links, broker forecasts, or institutional quotes.
- Do not tell the user to immediately buy, sell, pause, resume, add, reduce, clear, or lever.
- Do not treat cash reserve / 余额宝 as idle money waiting to be deployed.

### Reusable Phrases

- “更准确地说，这是收益率上行、债券价格承压，而不是债券价格上涨。”
- “这更像通胀型冲击链条，而不是普通避险链条。”
- “外交降温降低尾部风险，但不等于贸易、技术、供应链和金融约束已经结构性解除。”
- “估值压缩和系统性危机不是同一件事；系统性危机需要看到信用、融资、盈利、就业和流动性压力共振。”
- “对组合的含义只能落在风险暴露、相对目标偏高/偏低、观察方向和再平衡评估上，不是交易命令。”

### Bad Answer Patterns

- Treating every geopolitical event as ordinary risk-off and assuming long bonds or gold must rise.
- Writing “bond market rises” when the text actually describes yield rise.
- Turning diplomatic talks into a claim that structural risk has disappeared.
- Turning higher yields and equity pressure into “systemic crisis is certain.”
- Citing latest prices, exact yield levels, FedWatch odds, Reuters, Goldman, FactSet, or CME without local context.
- Converting portfolio implications into buy/sell/add/reduce instructions.

## Analyst Memo Pattern: Market Top, Pullback Risk, And Long-Term Allocation

Use this pattern when the user asks whether US equities have topped, whether a pullback is becoming more likely, whether AI or technology equities are overheated, or whether high valuation plus rate and inflation pressure should change long-term DCA discipline.

### Required Framing

The memo must separate three layers:

1. Stage-level overheating or pullback risk.
2. Medium-term trend reversal.
3. Systemic crisis.

It is acceptable to say pullback risk has risen when the reasoning is framed as probabilistic. It is not acceptable to say the market has confirmed a top, that a crash is imminent, or that a crisis has already started unless the local context contains broad, timestamped confirmation across stress indicators.

### Reasonable Concerns To Acknowledge

- elevated valuation
- crowded technology or AI leadership
- rising long-end yields or real yields
- repeated inflation pressure
- oil or energy-cost disruption
- worsening market breadth
- high market concentration
- earnings expectations that may be hard to satisfy
- liquidity conditions becoming less forgiving

### Corrections To Overstrong Claims

- "Pullback risk rising" is not the same as "confirmed top."
- Stage-level top signals are not the same as a medium-term trend reversal.
- Valuation compression is not the same as systemic crisis.
- AI industry progress can be real while asset prices still discount too much growth too early.
- Higher rates, inflation pressure, oil shocks, and narrow leadership reduce the margin of safety, but they do not by themselves prove an imminent crash.

### Technology Fundamentals Versus Valuation Risk

Do not frame the issue as "AI is fake" versus "AI guarantees returns." The better frame is whether fundamentals, valuation, liquidity, and rates are aligned:

- Are revenue and earnings actually being realized?
- Has valuation already priced in aggressive growth?
- Are capital expenditures pressuring free cash flow?
- Has market concentration increased portfolio-level risk?
- Are higher discount rates making long-duration equities less forgiving?

### Portfolio Translation

For the user's portfolio, translate the conclusion only into:

- target allocation
- relative risk exposure
- underweight / overweight language
- future DCA review
- threshold review
- year-end rebalancing review
- liquidity and product-channel risk checks

Do not convert the memo into immediate buy, sell, pause DCA, clear position, wait for a dip, or specific amount instructions.

### Reusable Expressions

- "说'回调风险上升'有依据，但说'已确认见顶'还过度。"
- "AI产业趋势可以真实存在，但估值仍可能透支。"
- "高估值市场的核心风险不是故事消失，而是利率、通胀和盈利兑现降低容错率。"
- "阶段性顶部信号成立，不等于中期趋势反转已经确认。"
- "系统性危机需要信用、流动性、就业和盈利等多维证据。"
- "对组合的含义应落实到相对风险暴露和后续再平衡评估，而不是即时交易命令。"

### Forbidden Expressions

- "美股已经确定见顶。"
- "接下来一定大跌。"
- "危机已经启动。"
- "必须清仓等回调。"
- "应暂停定投。"
- "应卖出一部分。"
- "按今天行情应调整为某金额。"
- "截至最新行情。"

Only use time-sensitive wording when the local context provides explicit timestamped data and the answer cites that boundary. Otherwise say the local context does not provide the latest market data.
