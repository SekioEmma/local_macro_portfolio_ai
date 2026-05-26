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

### 阶段 5.1：Ollama 本地模型真实回答

已完成：
- configs/llm.yaml 默认切换到 local_http / ollama
- 默认模型使用 gemma4:e2b
- src/llm/local_llm_client.py 支持 Ollama /api/generate
- scripts/ask_local_ai.py 支持保存 cleaned answer
- outputs/answers/.gitkeep

模型选择：
- gemma4:e2b 已通过基本中文运行测试
- gemma4:e4b 与 gemma4:e4b-lowctx 在当前 Windows + RTX 4060 Laptop 8GB VRAM + 16GB RAM 环境下出现 memory layout cannot be allocated
- 阶段 5.1 暂不使用 gemma4:e4b 或 e4b-lowctx 作为默认模型，后续再排查

能力：
- 调用本机 Ollama endpoint: http://localhost:11434/api/generate
- 调用前检查 Ollama /api/tags 或 /api/version
- 如果 gemma4:e2b 不存在，提示 ollama pull gemma4:e2b
- 保存 outputs/reports/latest_llm_prompt.md
- 保存 outputs/reports/latest_llm_answer.md
- 可选保存 outputs/answers/YYYY-MM-DD/HHMMSS_prompt.md
- 可选保存 outputs/answers/YYYY-MM-DD/HHMMSS_answer.md
- 可选保存 outputs/answers/YYYY-MM-DD/HHMMSS_manifest.json
- 支持清理 Thinking Process / Thinking... / done thinking
- manifest 记录 context_health、status、error、removed_thinking、cleaning_notes、answer_validation
- 支持 context_health 阻断 degraded context，默认 allow_degraded_context=false
- answer_validation 检查保证收益、短期确定性涨跌和具体买卖命令等违禁模式

已明确限制：
- 不接 OpenAI API
- 不接任何云端 API
- 不训练模型
- 不微调模型
- 不写具体买卖建议
- 不预测短期涨跌
- 不修改 .env
- 不提交 API key
- 不创建真实 current_holdings.csv
- 不创建真实 market_data_manual.csv
- 不提交 latest_llm_prompt.md / latest_llm_answer.md
- 不提交 outputs/answers 真实问答记录
- 不把 historical outcome 写成 forecast
- 不允许模型绕过 context pack 编造数据
- 不在 answer 文件中保存 Thinking Process / chain-of-thought

### 阶段 5.2：本地模型回答质量评估集

已完成：
- configs/eval_questions.yaml
- src/eval/answer_evaluator.py
- scripts/run_llm_eval.py
- outputs/eval/.gitkeep

能力：
- 固定评估问题集
- 批量调用本地 ask_local_ai.py / Ollama 回答流程
- 每个 case 生成 answer 与 eval json
- 生成 outputs/eval/YYYY-MM-DD/eval_summary.json
- 生成 outputs/eval/YYYY-MM-DD/eval_report.md
- 规则化检查 required_terms_any
- 规则化检查 forbidden_terms
- 检查 Thinking Process / Thinking... / done thinking
- 检查明显交易命令模式
- 汇总 pass / fail / warning / pass_rate

评估覆盖：
- sample_fallback 必须说明不是真实账户
- historical outcome is not forecast
- 禁止具体交易指令
- 必须引用组合事实
- 必须尊重数据限制和缓存/数据源失败边界
- 黄金和短债高配说明不能变成交易命令

已明确限制：
- 不接 OpenAI API
- 不接云端 API
- 不训练模型
- 不微调模型
- 不写投资建议
- 不预测短期涨跌
- 不修改 .env
- 不提交 API key
- 不创建真实 current_holdings.csv
- 不创建真实 market_data_manual.csv
- 不提交 outputs/eval 真实评估结果
- 不提交 outputs/answers 真实问答记录
- 不把 historical outcome 写成 forecast

### 阶段 5.3：本地模型对比与 repair 依赖评估

已完成：
- configs/model_eval.yaml
- src/eval/model_comparison.py
- scripts/run_model_comparison.py
- outputs/model_eval/.gitkeep

模型范围：
- gemma4:e2b
- qwen3:4b
- 暂不加入 qwen3:1.7b

能力：
- 读取固定评估集 configs/eval_questions.yaml
- 按模型覆盖 configs/llm.yaml 中的本地 Ollama 配置
- 检查 Ollama health 与模型是否存在
- 对每个模型逐 case 记录 first-pass 回答
- 对 first-pass 失败 case 触发本地 repair
- 记录 final-pass 回答
- 统计 first_pass_pass_rate
- 统计 final_pass_rate
- 统计 repair_used_count
- 统计 repair_success_count
- 记录 average_first_score 与 average_final_score
- 结构化记录 model_not_found、model_health_error、model_memory_layout_error
- 生成 outputs/model_eval/YYYY-MM-DD/model_comparison_summary.json
- 生成 outputs/model_eval/YYYY-MM-DD/model_comparison_report.md

已明确限制：
- 不接 OpenAI API
- 不接云端 API
- 不训练模型
- 不微调模型
- 不写具体买卖建议
- 不预测短期涨跌
- 不修改 .env
- 不提交 outputs/eval 真实评估结果
- 不提交 outputs/answers 真实问答记录
- 不提交 outputs/model_eval 真实结果
- 不把 historical outcome 写成 forecast

### 阶段 5.4：完整本地模型比较与默认模型选择

已完成：
- 完整 6-case local model comparison
- 比较 gemma4:e2b 与 qwen3:4b
- 记录 first-pass 与 final-pass 表现
- 记录 repair 依赖
- 记录 Thinking 清理结果
- 记录模型运行错误

gemma4:e2b 结果：
- preflight_status: ok
- total_cases: 6
- first_pass_pass_rate: 0.6667
- final_pass_rate: 0.6667
- repair_used_count: 2
- repair_success_count: 0
- average_first_score: 89.17
- average_final_score: 90.5
- failed_case_ids: market_overheat_portfolio, historical_outcome_not_forecast
- no thinking residue
- no model_errors

qwen3:4b 结果：
- preflight_status: ok
- total_cases: 6
- first_pass_pass_rate: 0.5
- final_pass_rate: 0.5
- repair_used_count: 3
- repair_success_count: 0
- average_first_score: 88.0
- average_final_score: 89.17
- failed_case_ids: market_overheat_portfolio, historical_outcome_not_forecast, degraded_context_behavior
- no thinking residue
- no model_errors

默认模型选择结论：
- 不切换默认模型
- 继续使用 gemma4:e2b
- qwen3:4b 暂不切换，保留为候选模型
- 当前主要瓶颈不是模型加载，也不是 Thinking 清理
- 当前主要瓶颈是 compact prompt / repair 对失败 case 的纠错能力不足

下一步重点：
- 进入 repair effectiveness improvement
- 优先修复 repair_success_count=0
- 重点 case: market_overheat_portfolio
- 重点 case: historical_outcome_not_forecast

已明确限制：
- 不接 OpenAI API
- 不接云端 API
- 不训练模型
- 不微调模型
- 不写具体买卖建议
- 不预测短期涨跌
- 不修改 .env
- 不提交 outputs/eval 真实评估结果
- 不提交 outputs/answers 真实问答记录
- 不提交 outputs/model_eval 真实结果
- 不提交 latest_llm_prompt.md / latest_llm_answer.md
- 不把 historical outcome 写成 forecast

### 阶段 5.7：默认本地模型切换到 qwen3:4b

已完成：
- configs/llm.yaml 默认模型从 gemma4:e2b 切换为 qwen3:4b
- 默认 Ollama provider 与本机 endpoint 保持不变
- 默认 num_ctx 调整为 2048
- 默认 max_context_chars 调整为 5000
- 默认 compact_prompt=true
- strip_thinking_output 继续保持 true
- gemma4:e2b 保留为备用模型

切换依据：
- 阶段 5.6 使用真实 scripts/ask_local_ai.py 主链路验证
- gemma4:e2b: total_questions=5, passed=4, failed=1, pass_rate=0.8
- gemma4:e2b failed case: market_overheat_portfolio
- qwen3:4b: total_questions=5, passed=5, failed=0, pass_rate=1.0
- qwen3:4b thinking_residue_count=0
- latest_llm_answer.md 未残留 Thinking Process / Thinking... / done thinking

重要限制：
- qwen3:4b 在阶段 5.6 中没有触发 repair
- 因此只能说明 qwen3:4b 在真实 ask_local_ai first-pass 主链路中更稳
- 不能声称 qwen3:4b repair 已在真实 ask_local_ai 主链路中被证明有效
- 仍需保留 clean_model_answer / strip_thinking_output
- 仍需保留 context pack only、禁止预测、禁止具体交易指令、禁止编造数据等边界

已明确限制：
- 不接 OpenAI API
- 不接云端 API
- 不训练模型
- 不微调模型
- 不写具体买卖建议
- 不预测短期涨跌
- 不修改 .env
- 不提交 outputs/eval 真实评估结果
- 不提交 outputs/answers 真实问答记录
- 不提交 outputs/model_eval 真实结果
- 不提交 latest_llm_prompt.md / latest_llm_answer.md
- 不把 historical outcome 写成 forecast

## 当前技术原则

- 事实数据来自 provider
- 持仓和收益由 portfolio_engine 计算
- 市场温度由规则模型计算
- 本地 LLM 问答接口只能读取 llm_context_pack
- 默认 local_http 调用本机 Ollama
- 默认模型为 qwen3:4b
- gemma4:e2b 保留为备用模型
- local_http 只允许本机 endpoint，不接云端 API
- degraded context 默认阻断模型调用
- LLM 不能编造数据
- LLM 不能直接计算仓位
- LLM 不能写投资建议或短期涨跌预测

### 阶段 6.0：真实持仓接入与余额宝扣款逻辑

已完成：
- data/holdings/current_holdings.csv 已作为本地真实持仓快照接入
- current_holdings.csv 已被 Git 忽略，不进入仓库
- holdings_source.mode 切换为 current_holdings
- 余额宝识别为 cash reserve / 扣款准备金
- 余额宝不参与 5:2:2:1 目标仓位计算
- nasdaq100 合并 019172 与 270042
- DCA daily_total = 70
- estimated_monthly_dca ≈ 1470
- monthly transfer range = 1200-1500
- DCA status = within_budget

当前真实持仓口径：
- 真实账户金额、现金余额、收益和具体持仓比例属于本地私有快照信息，不写入可提交文档。
- 可提交文档只保留资产类别方向、目标配置规则、cash reserve 口径和 DCA 规则。
- 需要查看当前真实数值时，只读取本地 `data/holdings/current_holdings.csv` 和生成的 `outputs/reports/portfolio_snapshot.json`；这些文件不进入 Git。

已明确限制：
- 不提交 current_holdings.csv
- 不把余额宝解释为应立即投入市场的闲置资金
- 不输出具体买卖金额
- 不输出“需增加持仓 / 需减持 / 应买入 / 应卖出 / 立即调整”

### 阶段 6.1：真实持仓主链路一致性回归

已完成：
- portfolio_snapshot.json 使用 current_holdings 口径
- daily_report.md 使用 current_holdings 口径
- llm_context_pack.md 使用 current_holdings 口径
- ask_local_ai.py 回答使用 current_holdings 口径
- 四个入口不再显示 sample_fallback
- 现金 / 余额宝统一作为 cash reserve
- Allocation vs Target 统一按 excluding cash 计算
- latest_llm_answer.md 不再输出 sample_fallback 警告
- latest_llm_answer.md 明确本地持仓快照不是实时账户同步

已明确限制：
- outputs/reports 真实报告不提交
- outputs/answers 真实问答归档不提交
- 不把本地手动截图快照说成实时同步账户

### 阶段 6.2：持仓快照 freshness 与更新流程

已完成：
- portfolio_snapshot.json 增加 holdings_updated_at
- portfolio_snapshot.json 增加 holdings_age_days
- portfolio_snapshot.json 增加 holdings_freshness_status
- portfolio_snapshot.json 增加 holdings_updated_at_status
- daily_report.md 显示持仓快照日期与 freshness
- llm_context_pack.md 显示持仓快照日期与 freshness
- ask_local_ai.py 提示基于本地持仓快照，不是实时同步
- docs/holdings_update_workflow.md 记录持仓更新流程
- 修复 current_holdings.csv 中文基金名读取乱码
- 增加 hallucination guardrail：严重跑题或编造时使用 context-only fallback 完整替换最终答案

freshness 规则：
- 0-7 天：fresh
- 8-14 天：aging
- 15-30 天：stale
- >30 天：very_stale
- 无法解析日期：unknown

当前持仓快照：
- holdings_updated_at = 2026-05-14
- holdings_freshness_status 按运行日期动态计算
- current_holdings.csv 是用户本地手动录入快照，不是实时账户同步

已明确限制：
- 不把旧持仓快照当实时账户
- 不提交 current_holdings.csv
- 不提交 outputs 真实结果
- 不编造外部行情、阈值、日期或目标比例

### 阶段 6.3：Analyst Memo 风格层与 fallback 分层

当前状态：
- 已实现 analyst_memo 回答模式
- ask_local_ai.py 支持 --style standard
- ask_local_ai.py 支持 --style analyst_memo
- 新增 configs/answer_style.yaml
- 新增 docs/answer_style_guide.md
- analyst_memo 适用于宏观、市场类比、估值、历史周期、组合影响类问题
- 保留默认 qwen3:4b
- 保留 clean_model_answer / strip_thinking_output
- 保留 hallucination guardrail 与 context-only fallback

fallback 分层：
- answer_mode = natural：模型自然回答通过校验
- answer_mode = repaired：轻微缺项后 repair 通过
- answer_mode = context_only_fallback：严重幻觉、跑题、编造外部数据、错误目标比例、Thinking 残留或交易化措辞时整段替换

已完成验证：
- analyst_memo 测试问题可生成安全答案
- latest_llm_answer.md 无 Thinking / Thinking Process / done thinking
- 不再出现 sample_fallback
- 不编造最新价格、PE、市值、媒体来源
- 不把“危机一两年内到来”写成确定性预测
- 可接回 current_holdings、余额宝 cash reserve、5:2:2:1 目标配置与持仓 freshness
- run_llm_eval.py 更新为 7 个 case
- run_llm_eval.py 当前验收结果：total=7, passed=7, failed=0, pass_rate=1.0

后续注意：
- analyst_memo 当前以安全性优先
- 如果模型自然回答触发严重 guardrail，会使用 context_only_fallback
- 后续可继续优化 first-pass 自然回答质量，减少 fallback 依赖
- 不切换默认模型
- 不接云端 API
- 不训练或微调模型

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

### 阶段 6.4：Analyst Memo 自然回答质量优化

已完成：
- analyst_memo guardrail classification
- answer_mode / fallback_reason / repair metadata
- natural / repaired / context_only_fallback 分层
- run_llm_eval.py 扩展为 9 个 case
- 宏观 + 组合复盘题型覆盖

当前状态：
- run_llm_eval.py 通过
- qwen3:4b 在复杂 analyst_memo 首答中仍可能编造 context 外数据
- 严重幻觉时 context_only_fallback 仍是必要保护

### 阶段 6.5：Conversation Distillation / 风格样本蒸馏基础

已完成：
- docs/conversation_distillation_workflow.md
- docs/user_investment_policy.md
- docs/answer_style_guide.md 增加 conversation-distilled analyst_memo 风格样本
- .gitignore 增加 data/private/

能力：
- 明确 raw conversation 不能直接进入 prompt 或微调
- 明确 stable_fact / user_policy / style_preference / eval_case / bad_answer_pattern 等蒸馏类型
- 明确 data/private/ 只做本地私有样本和中间稿，不进入 Git

### 阶段 6.6：MVP Daily Workflow And Release Checklist

已完成：
- docs/daily_workflow.md
- docs/troubleshooting.md
- docs/mvp_release_checklist.md
- README.md 刷新为当前 MVP 入口
- docs/project_status.md 更新本阶段状态

能力：
- 明确每日/每次开机推荐流程
- 明确 PowerShell 日常运行命令
- 明确 outputs、current_holdings.csv、data/private、.env 的隐私边界
- 覆盖 Ollama、虚拟内存、Thinking 输出、中文乱码、sample_fallback、holdings freshness、context-only fallback 的故障处理
- 明确 MVP v1 完成标准与发布前检查项

### GitHub Handoff 整理

已完成：
- 新增 docs/project_handoff.md 作为新 ChatGPT/Codex 窗口接手入口
- README.md 增加 handoff 文档链接
- docs/project_status.md 中的真实持仓数值摘要已脱敏，避免可提交文档暴露本地账户快照

注意：
- GitHub 同步前必须确认 `.env`、`current_holdings.csv`、`data/private/` 和真实 `outputs/` 未被跟踪
- 如果仓库保持 public，后续文档仍应避免写入真实账户金额、持仓快照原文或原始对话内容

### 阶段 6.7：Distilled Analyst Memo Answer Optimization

已完成：
- docs/answer_style_guide.md 增加地缘、利率、通胀型冲击和组合含义的 analyst_memo 模式
- docs/knowledge/macro_market_regime.md 增加普通避险与通胀型冲击的宏观 regime 知识框架
- configs/eval_questions.yaml 增加 macro_geopolitics_rates_001 analyst_memo eval case
- configs/answer_style.yaml 小幅补充 analyst_memo 风格约束

能力：
- 区分普通避险与通胀型冲击，不把所有地缘事件都写成普通 risk-off
- 明确收益率上行与债券价格下跌的关系
- 建立地缘 / 能源 / 通胀 / Fed 路径重定价 / 长端利率 / 高估值权益资产的分析链条
- 区分外交降温与结构性风险解除
- 区分估值压缩与系统性危机
- 组合含义继续限制在相对目标、风险暴露、观察方向、DCA 纪律和再平衡评估内

边界：
- 未读取或提交 data/private 原文
- 未写入真实账户金额、真实持仓快照、outputs 原文或时效行情
- 未训练模型、未调用云 API、未修改默认模型

## 下一阶段计划

MVP v1 进入冻结与日常使用观察期。下一阶段应优先处理真实日常运行中暴露的文档缺口、流程缺口或高频故障，不主动扩大 guardrail、不切换默认模型、不接云端 API、不训练或微调模型。

### Stage 6.12: MVP v1 observation readiness

Status: 6.11b stabilization passed, and MVP v1 observation is ready.

The project should now prioritize daily use observation, factual boundaries, privacy boundaries, and long-term discipline. Known limitation: fallback share remains high, but final answers are guarded for safety. Do not expand features, add distillation material, or continue refactoring unless repeated observation failures justify a new development stage.

### Stage 7.2: Financial data package enrichment for DeepSeek Pro reports

Status: implemented locally; pending user review and commit.

Scope: enrich the local, auditable financial conditions package for DeepSeek Pro analyst memos. This stage adds timestamped FRED/public data fields for credit spread, VIX, real yield, inflation expectations, and the 10Y-2Y yield curve, while keeping valuation proxy and FedWatch probability explicit as unavailable unless stable configured sources are added.

Boundaries: do not make DeepSeek the default provider, do not modify portfolio policy or target allocation logic, do not store API keys, and do not commit real generated outputs.
