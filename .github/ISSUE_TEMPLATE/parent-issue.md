---
name: Parent Issue
about: 開発テーマ全体を管理する親Issue
title: "[Project] "
labels: []
assignees: []
---

> 非該当の専門欄を作らず、[条件付き参照](../blob/main/docs/minimal-development-contract.md#条件付き参照)から該当する正本だけを読む。適用可否が不明、重要判断がNEEDS_DECISION、MUST不足なら登録・実装開始を停止する。

# Goal

プロジェクト全体で達成する利用者の目的。親Issueはロードマップとし、実装は1子Issue = 1 PRへ分ける。

# Context

必要な理由、採用済み判断と関連仕様への参照。合意済み計画から生成する場合はPlan Reviewの判定（PASS / NOT_APPLICABLE）、理由、[正本参照](../blob/main/docs/plan-review-gate.md)を短く保存する。単一Issueでも省略しない。

# Scope / Boundaries

- 変更可能なpath・責務:
- Risk Tier: LOW / MEDIUM / HIGH。判定理由・影響範囲（[判定基準](../blob/main/docs/adaptive-development-flow.md)）:
- 安全境界と停止条件: 情報読取・外部書込の適用を確認し、今回の情報分類・送信先・権限範囲とHuman Approvalの要否を短く示す。[AI Agent Security Boundary](../blob/main/docs/ai-agent-security-boundary.md)に該当する制御・例外は理由、残るリスク、代替制御、承認者まで記録する。未承認の本番・Deploy・破壊的操作・Secrets・認証/権限/Security Policy/公開/課金/repo保護設定変更は停止する。

# Non-goals

今回変更しない範囲。

# Done

- [ ] 全体の目的を、子PRのMergeだけでなく実利用シナリオと人間の最終確認で判定できる条件。

# Verification

検証コマンド・手動確認と期待結果。正常・範囲・整合性・境界・異常・回帰の6観点から必要なケースを選び、全観点の空欄は作らない。未実施は理由と残るリスクを記録する。標準検証・self-review、現headのCI / Security / Codex Review、人間Mergeを維持する。

実利用検収がある場合は[Acceptance Verification](../blob/main/docs/acceptance-verification.md)に従い、環境・成功/失敗条件・人間確認・対象artifactを特定する。Release時は[Deployment / Release Design](../blob/main/docs/deployment-release-design.md)の監査結果とRC identityを照合する。親Closeは[親完了契約](../blob/main/docs/parent-issue-completion.md)の5確認を満たす。

# Children / Dependencies

子Issue一覧、依存順序、親がある場合はParent。依存がなければ「なし」。未確定の依存をなしと推測しない。

> 子Issue登録前は[Issue Quality Check](../blob/main/docs/issue-quality-check.md)の6 MUSTを確認する。Framework / UI / State / Harnessの詳細は条件付き参照に従う。非該当のNONE / NOT_APPLICABLE欄は不要。
