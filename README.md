# Local Macro Portfolio AI

Local Macro Portfolio AI 是一个本地个人投研与资产配置辅助系统。它读取本地持仓快照、目标配置、定投规则和公开宏观/市场数据，生成每日报告、LLM context pack，并通过本机 Ollama 模型提供 context-only 问答。

它不是自动交易系统，不保证收益，不预测短期涨跌，也不提供具体交易指令。

## 当前能力

- 读取 `data/holdings/current_holdings.csv` 本地持仓快照
- 将 余额宝 / cash reserve 作为扣款来源，并排除在目标仓位权重之外
- 计算 `sp500:nasdaq100:short_bond:gold = 5:2:2:1` 目标配置偏离
- 显示 holdings freshness、DCA budget、现金准备金和组合结构
- 生成 `portfolio_snapshot`、`daily_report`、`llm_context_pack`
- 使用本地 Ollama 默认模型 `qwen3:4b`
- 支持 `standard` 与 `analyst_memo` 两种回答风格
- 通过 `run_llm_eval.py` 做本地回答质量回归评估

## Quick Start

Run from the project root:

```powershell
python scripts/run_portfolio_check.py
python scripts/run_daily_report.py
python scripts/run_llm_context_pack.py
python scripts/ask_local_ai.py "当前市场是否过热？对我的组合意味着什么？"
```

Full deterministic daily update:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/update_daily_report.ps1
```

Run local LLM eval:

```powershell
python scripts/run_llm_eval.py
```

## Main Docs

- [Daily workflow](docs/daily_workflow.md)
- [Troubleshooting](docs/troubleshooting.md)
- [MVP release checklist](docs/mvp_release_checklist.md)
- [Holdings update workflow](docs/holdings_update_workflow.md)
- [Answer style guide](docs/answer_style_guide.md)
- [Conversation distillation workflow](docs/conversation_distillation_workflow.md)
- [Project status](docs/project_status.md)

## Privacy

The project is designed for local use. Do not commit:

- `.env`
- API keys
- `data/holdings/current_holdings.csv`
- `data/private/`
- generated `outputs/`
- raw conversation exports
- private account snapshots

## Non-Goals

- no automatic trading
- no cloud LLM API
- no training or fine-tuning in the MVP workflow
- no guaranteed returns
- no short-term market forecast
- no concrete buy/sell instructions
- no use of old holding snapshots as real-time account sync
