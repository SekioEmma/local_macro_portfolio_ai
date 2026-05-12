# Local Macro Portfolio AI - Project Status

## 项目定位

本项目是本地个人投资研究与资产配置辅助系统。它不是自动交易系统，不预测短期涨跌，不保证收益，不提供专业投资顾问服务。

目标：
- 读取用户本地持仓数据
- 读取用户目标配置与定投规则
- 查询公开/官方金融与宏观数据
- 计算账户状态、配置偏离、预算压力
- 用规则模型描述市场温度
- 后续接入 RAG 和本地 LLM，用于解释和生成报告

## 用户投资规则摘要

- 用户为学生，投资资金主要用于长期学习与实践
- 月投入约 1200-1300 元
- 目标配置：
  - S&P 500：50%
  - Nasdaq 100：20%
  - short bond：20%
  - gold：10%
- 当前建仓规则：
  - 017641：50 元/交易日
  - 019172：20 元/交易日
  - 270042：暂停新增
  - short_bond：暂停新增
  - gold：暂停新增
- 再平衡偏好：
  - 优先用新增资金纠偏
  - 避免频繁卖出
  - 偏离超过约 5% 才提示
  - 年底统一复盘

## 已完成阶段

### 阶段 0：项目骨架

已完成：
- README.md
- configs/user_profile.yaml
- data/holdings/holdings_template.csv
- data/holdings/sample_holdings.csv
- 基础目录结构
- Git 初始化
- .gitignore
- .gitattributes

### 阶段 1：组合计算引擎

已完成：
- src/portfolio/portfolio_engine.py
- scripts/run_portfolio_check.py

能力：
- 读取持仓 CSV
- 读取 user_profile.yaml
- 计算总资产、投资资产、现金、浮盈浮亏
- 按资产类别聚合
- 计算目标配置偏离
- 判断 underweight / overweight / within_range
- 检查定投预算是否超出月预算

当前示例判断：
- S&P 500 低配
- Nasdaq 100 低配
- short bond 高配
- gold 高配
- 当前 70 元/交易日计划约 1470 元/月，超过 1200-1300 元预算区间

### 阶段 2：FRED-first 公开数据源

已完成：
- configs/data_sources.yaml
- src/data_providers/fred_provider.py
- src/data_providers/fed_provider.py
- src/data_providers/yfinance_provider.py
- src/data_providers/market_data_service.py
- src/data_providers/cache.py
- scripts/run_market_data_check.py

数据源策略：
- FRED 是主数据源
- yfinance 仅作为可选补充
- Stooq 已放弃作为默认数据源
- .env 保存 FRED_API_KEY，禁止提交

已能获取：
- SP500
- NASDAQCOM
- DGS10
- FEDFUNDS
- CPIAUCSL
- PCEPI
- PAYEMS
- DEXCHUS

已知限制：
- Nasdaq 100 暂无稳定主数据源
- Gold 暂无稳定主数据源
- yfinance 可能被 rate limited

### 阶段 3：规则化市场温度评分

已完成：
- src/market/market_temperature.py
- scripts/run_market_temperature_check.py

能力：
- 计算 SP500 / NASDAQCOM 近 1 月和 3 月变化
- 计算 DGS10 最新水平和近 1 月变化
- 计算 CPI / PCE MoM 和 YoY
- 计算 PAYEMS MoM
- 计算 DEXCHUS 近 1 月变化
- 输出 equity_temperature、rate_pressure、inflation_pressure、labor_market、fx_pressure、overall_regime、risk_level

当前示例输出：
- equity_temperature: warm
- rate_pressure: medium
- inflation_pressure: medium
- labor_market: resilient
- fx_pressure: neutral
- overall_regime: warm_but_macro_sensitive
- risk_level: medium

### 阶段 4.10：LLM Context Pack

已完成：
- src/reports/llm_context_pack.py
- scripts/run_llm_context_pack.py

能力：
- 读取 portfolio_snapshot.json
- 读取 market_snapshot.json
- 读取 market_temperature.json
- 读取 daily_report.md
- 读取 market_history_features.json
- 读取 macro_regime_history.json
- 生成 outputs/reports/llm_context_pack.json
- 生成 outputs/reports/llm_context_pack.md

上下文包明确区分：
- confirmed facts
- rule-based assessments
- historical outcomes
- portfolio context
- data quality
- data limitations
- allowed model tasks
- forbidden model behaviors

已明确限制：
- historical outcome is not forecast
- ETF proxy return is not actual fund NAV
- sample_fallback is not real account data
- LLM must not invent market data or portfolio holdings
- LLM must not recommend frequent trading
- LLM must not guarantee returns

### 阶段 4.11：每日自动更新与历史快照归档

已完成：
- scripts/update_daily_report.ps1
- scripts/archive_reports.py
- docs/windows_task_scheduler.md
- outputs/logs/.gitkeep
- outputs/archive/.gitkeep

能力：
- 手动运行或由 Windows Task Scheduler 运行每日更新流程
- 依次刷新组合快照、市场数据、市场温度、日报、历史市场特征、宏观 regime 历史分析、LLM Context Pack
- 将 stdout/stderr 追加写入 outputs/logs/update_daily_report_YYYY-MM-DD.log
- 将 outputs/reports/ 中的最新报告复制到 outputs/archive/YYYY-MM-DD/
- 同一天重复运行时覆盖当天归档目录中的同名文件
- 生成 outputs/archive/YYYY-MM-DD/archive_manifest.json

存储策略：
- outputs/reports/ 始终保存最新报告，每次运行覆盖
- outputs/archive/YYYY-MM-DD/ 保存每日快照
- outputs/logs/update_daily_report_YYYY-MM-DD.log 同一天追加写入
- data/history/fred/*.raw.json 不做每日复制，作为本地缓存复用
- data/history/market/*_YYYY-MM-DD.raw.json 作为 Alpha Vantage 当日缓存，普通运行优先复用
- outputs/archive/、outputs/logs/、data/history/**/*.raw.json 不提交到 Git

保留策略预留：
- logs_retention_days = 30
- archive_retention_days = 365
- market_raw_cache_retention_days = 30
- 第一版只记录保留策略，不自动删除历史文件

已明确限制：
- 不接 LLM
- 不调用 OpenAI API
- 不训练模型
- 不写投资建议
- 不预测未来
- 不修改 .env
- 不提交 API key
- 不创建真实 current_holdings.csv
- 不创建真实 market_data_manual.csv
- 不提交 raw history JSON
- 不提交 outputs/archive 里的真实快照
- historical outcome is not forecast

### 阶段 5.0：本地 LLM 最小问答接口

已完成：
- configs/llm.yaml
- src/llm/context_loader.py
- src/llm/prompt_builder.py
- src/llm/local_llm_client.py
- scripts/ask_local_ai.py

能力：
- 默认 mode=prompt_only，只生成 prompt，不调用模型
- 读取 outputs/reports/llm_context_pack.md
- 读取 outputs/reports/llm_context_pack.json
- 基于用户问题生成带安全边界的中文回答 prompt
- prompt 明确要求只基于 context pack 回答
- prompt 明确区分 confirmed facts、rule-based assessments、historical outcomes、reasonable inferences、assumptions、uncertainties
- prompt_only 模式保存 outputs/reports/latest_llm_prompt.md
- local_http 模式预留 localhost 本地 HTTP 调用
- local_http 仅允许 localhost / 127.0.0.1 / ::1 endpoint

已明确限制：
- 不训练模型
- 不微调模型
- 不接 OpenAI API
- 不接云端 API
- 不写投资建议
- 不预测短期涨跌
- 不修改 .env
- 不提交 API key
- 不创建真实 current_holdings.csv
- 不创建真实 market_data_manual.csv
- 不提交 outputs/reports 生成文件
- 不提交 outputs/archive 真实快照
- 不把 historical outcome 写成 forecast
- 不允许模型编造 context pack 之外的数据

## 当前技术原则

- 事实数据来自 provider
- 持仓和收益由 portfolio_engine 计算
- 市场温度由规则模型计算
- 本地 LLM 问答接口只能读取 llm_context_pack
- 默认 prompt_only，不调用模型
- local_http 只允许本机 endpoint，不接云端 API
- LLM 不能编造数据
- LLM 不能直接计算仓位
- LLM 不能写投资建议或短期涨跌预测

## 当前不做

- 不接自动交易
- 不预测短期涨跌
- 不保证收益
- 不接支付宝自动抓取
- 不接云端 LLM
- 不调用 OpenAI API
- 不训练模型
- 不微调模型
- 不做 iPad 部署
- 不做复杂 UI

## 下一阶段计划

阶段 5.1：待规划。

阶段 5.0 已完成最小本地 LLM 问答接口。下一阶段仍需遵守不接云端 API、不训练模型、不预测未来、不写投资建议的边界。
