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

## 当前技术原则

- 事实数据来自 provider
- 持仓和收益由 portfolio_engine 计算
- 市场温度由规则模型计算
- LLM 不能编造数据
- LLM 不能直接计算仓位
- LLM 后续只负责解释、总结和报告生成

## 当前不做

- 不接自动交易
- 不预测短期涨跌
- 不保证收益
- 不接支付宝自动抓取
- 不接 LLM
- 不训练模型
- 不做 iPad 部署
- 不做复杂 UI

## 下一阶段计划

阶段 4：账户 + 市场综合报告。

目标：
读取：
- outputs/reports/portfolio_snapshot.json
- outputs/reports/market_snapshot.json
- outputs/reports/market_temperature.json

生成：
- outputs/reports/daily_report.md
- outputs/reports/daily_report.json

报告包含：
- 账户状态
- 资产配置偏离
- 定投预算压力
- 市场温度
- 宏观压力
- 数据来源
- 数据限制
- 非投资建议声明

注意：
阶段 4 仍然不接 LLM，只生成规则化报告底稿。
