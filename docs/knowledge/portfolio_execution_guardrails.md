# Portfolio Execution Guardrails

This document stores abstract, non-private execution guardrails for local portfolio answers. It must not contain account snapshots, private holdings, current prices, or trade tickets.

## Pullback-Risk Conclusions And Portfolio Execution

When pullback risk rises, do not automatically turn the conclusion into selling, pausing DCA, waiting for a lower entry point, or clearing positions. A market-risk judgment is not a trade ticket.

For a long-term DCA portfolio, translate pullback-risk analysis into review questions:

- Is each asset class underweight or overweight relative to target?
- Has portfolio concentration become too high?
- Does future DCA need review rather than acceleration?
- Has a rebalancing threshold been reached?
- Has the user's liquidity need changed?
- Has any product-channel risk appeared, such as subscription, redemption, FX, NAV conversion, or platform constraints?

Acceptable wording:

- "估值压力不支持加速扩大风险暴露。"
- "后续定投可以进入复核框架，而不是变成单次暂停或加速指令。"
- "组合含义应落在相对目标、风险暴露、阈值复核和年末再平衡评估。"

Forbidden execution drift:

- do not provide new buy or sell amounts from a single market judgment
- do not say the user should sell, reduce, clear, or pause DCA
- do not treat cash reserve as idle cash waiting to be deployed
- do not describe current_holdings.csv as real-time account sync
- do not convert valuation pressure into an immediate position-adjustment plan
