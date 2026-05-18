# Conversation Distillation Workflow

This project may use long-running conversations as raw material for better local answers, but raw conversations are not project knowledge by themselves. They must be distilled, reviewed, and separated from private data before anything becomes a committed asset.

## Why Raw Conversations Are Not Direct Inputs

Raw conversations can contain debugging logs, failed attempts, obsolete facts, real local paths, real holding snapshots, private account context, and bad model answers. They also mix stable user policy with temporary decisions made during a single run.

Do not paste raw conversations directly into prompts. Do not use raw conversations directly as fine-tuning data. Do not treat an old market statement, a tool output, or a temporary model mistake as a durable fact.

The useful unit is the reviewed extraction: a stable rule, a style preference, a reusable evaluation case, or a clearly labeled bad-answer pattern.

## Distilled Output Types

- `stable_fact`: A long-lived project fact that is unlikely to change often.
- `user_policy`: A user investment rule, portfolio policy, or operating boundary.
- `style_preference`: A durable answer style preference.
- `eval_case`: A reusable test question with required concepts and forbidden claims.
- `knowledge_note`: A general knowledge note that can guide future local analysis.
- `bad_answer_pattern`: A pattern that should trigger repair or fallback.
- `sft_candidate`: A future supervised fine-tuning candidate, pending manual review.
- `preference_pair`: A future preference-training candidate, pending manual review.
- `obsolete`: A statement that is no longer current or should not be reused.
- `private_sensitive`: Any content that should remain outside Git and outside prompts unless explicitly sanitized.

## Recommended Private Directory Structure

Keep these files under `data/private/`, which is ignored by Git:

```text
data/private/conversations/raw/
data/private/conversations/curated/
data/private/style_examples/
data/private/sft_candidates/
data/private/preference_pairs/
```

These directories may contain raw conversation exports, intermediate notes, draft samples, private preference pairs, and future training candidates. They are local-only working material and must not be committed.

## Commit Boundary

Safe to commit after review and sanitization:

- desensitized docs
- `configs/eval_questions.yaml`
- `configs/answer_style.yaml`
- `docs/answer_style_guide.md`
- `docs/user_investment_policy.md`

Do not commit:

- raw chat logs
- `data/holdings/current_holdings.csv`
- generated `outputs`
- `.env`
- API keys
- text that includes real local paths, private account snapshots, or original holding exports
- raw conversation excerpts that include private or obsolete content

## Distillation Process

1. Read the raw conversation locally from `data/private/`.
2. Mark each useful paragraph as one of the distilled output types.
3. Remove debugging noise, failed commands, temporary tool output, and model mistakes.
4. Separate stable user rules from temporary project state.
5. Separate ideal answer examples from bad model answers.
6. Extract `required_concepts` and `forbidden_claims`.
7. Convert durable material into an eval case, style sample, policy note, or knowledge note.
8. Manually confirm the distilled asset before moving it into `docs/` or `configs/`.
9. Keep private source material under `data/private/` and out of Git.

## Distilled Eval Case Schema Example

```yaml
case_id: dotcom_ai_bubble_analyst_memo
category: analyst_memo
source_type: conversation_distilled
question: >
  如何评价有人把当前 AI 行情与 2000 年互联网泡沫做类比？我觉得市场过热、
  情绪乐观，但这次技术也确实有基础支撑。
required_concepts:
  - 类比有合理性但要加限定
  - 不是 2000 年简单复刻
  - 技术革命真实存在
  - 资产价格可能过度透支
  - 核心 AI 公司可能有基本面支撑
  - 风险不是 AI 无用，而是高估值和高预期兑现压力
  - 未来 1-2 年杀估值或科技股回撤概率上升
  - 系统性经济危机证据不足
  - 不清仓
  - 不追涨
  - 不提高纳指权重
  - 纪律化定投和再平衡框架
forbidden:
  - 危机必然一两年内到来
  - 一定崩盘
  - 立即清仓
  - 编造价格、PE 或媒体来源
privacy:
  contains_private_data: false
  can_commit: true
```

The schema is a design aid, not a license to invent facts. If a required concept depends on current market data, the eval case must either provide that data in local context or require the answer to say that local context does not provide it.
