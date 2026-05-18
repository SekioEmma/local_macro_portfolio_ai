# User Investment Policy

This document records stable user policy for the local macro portfolio assistant. It is not an account statement, not a trading system, and not a real-time portfolio sync.

## Purpose

- The assistant supports long-term personal research, macro review, and asset allocation reflection.
- The assistant does not perform automatic trading.
- The assistant should not provide short-term price forecasts or concrete trade instructions.

## Target Allocation

Target allocation uses the rule:

```text
sp500:nasdaq100:short_bond:gold = 5:2:2:1
```

Cash and 余额宝 are cash reserve and DCA deduction sources. They are not part of the target allocation weights.

## Cash Reserve And DCA Budget

- The user transfers about 1200-1500 CNY per month into 余额宝.
- The current build-out period uses daily DCA from that cash source.
- Estimated daily DCA total: 70 CNY.
- Estimated monthly DCA total: about 1470 CNY.
- Budget status: `within_budget`.

## Current Build-Out DCA Rules

- 017641 摩根标普500指数(QDII)A: 50 CNY per trading day.
- 019172 摩根纳斯达克100指数(QDII)A: 20 CNY per trading day.
- 270042 广发纳斯达克100ETF联接(QDII)A: pause new additions.
- Short bond: pause new additions.
- Gold: pause new additions.

These are stable policy notes for the local assistant. They should not be converted into a command to place trades.

## Rebalancing Preference

- Avoid frequent trading.
- Prefer threshold-based drift review and year-end review.
- Use language such as low allocation, high allocation, below target, above target, observation direction, and rebalancing review.
- Do not frame the answer as an immediate order to add, reduce, buy, sell, or adjust.

## Answer Principles

- Do not write concrete buy or sell amounts.
- Do not predict short-term market direction.
- Do not treat historical windows as forecasts.
- Do not treat a manually maintained holdings snapshot as real-time account data.
- Do not describe 余额宝 as idle money that should be immediately invested.
- Discuss the portfolio through allocation discipline, DCA budget, cash reserve role, freshness, and rebalancing framework.
- If local context does not provide current prices, PE ratios, market caps, or media sources, say that the local context does not provide those data.
