---
name: Child Issue
about: 1 PR単位でCodexに実装させる子Issue
title: "[Task] "
labels: []
assignees: []
---

> 非該当の専門欄を作らず、[条件付き参照](../blob/main/docs/minimal-development-contract.md#条件付き参照)から該当する正本だけを読む。適用可否が不明、重要判断がNEEDS_DECISION、MUST不足なら登録・実装開始を停止する。

# Goal

この1子Issue = 1 PRで達成すること。

# Context

必要な理由、採用済み判断と関連仕様への参照。合意済み計画から生成する場合はPlan Reviewの判定（PASS / NOT_APPLICABLE）、理由、[正本参照](../blob/main/docs/plan-review-gate.md)を短く保存する。単一Issueでも省略しない。

# Scope / Boundaries

- 変更可能なpath・責務:
- Risk Tier: LOW / MEDIUM / HIGH。判定理由・影響範囲（[判定基準](../blob/main/docs/adaptive-development-flow.md)）:
- 安全境界と停止条件: 情報読取・外部書込の適用を確認し、今回の情報分類・送信先・権限範囲とHuman Approvalの要否を短く示す。[AI Agent Security Boundary](../blob/main/docs/ai-agent-security-boundary.md)に該当する制御・例外は理由、残るリスク、代替制御、承認者まで記録する。未承認の本番・Deploy・破壊的操作・Secrets・認証/権限/Security Policy/公開/課金/repo保護設定変更は停止する。

# Non-goals

今回変更しない範囲。

# Done

- [ ] 実装手順とは独立した利用者の結果・確認方法で判定できる条件。

# Verification

検証コマンド・手動確認と期待結果。正常・範囲・整合性・境界・異常・回帰の6観点から必要なケースを選び、全観点の空欄は作らない。未実施は理由と残るリスクを記録する。標準検証・self-review、現headのCI / Security / Codex Review、人間Mergeを維持する。

テスト・Gateの保証を変更する場合は[安全なテスト変更](../blob/main/docs/test-design.md)と[Harness Minimalism台帳](../blob/main/docs/ai-development-harness-inventory.md)を確認し、失敗モード・代替保証・再評価条件を記録する。代替成功前に旧保証を消さない。

# Dependencies

Parent / Depends on、実装順。依存がなければ「なし」。未確定の依存をなしと推測しない。

> 登録・実装前は[Issue Quality Check](../blob/main/docs/issue-quality-check.md)の6 MUSTを確認する。Framework / UI / State / Harnessの詳細は条件付き参照に従う。非該当のNONE / NOT_APPLICABLE欄は不要。
