# 対応Issue

Closes #

# 差分・判断・レビュー上の注意点

- 差分:
- 判断と理由:
- Issue受入条件:
- 変更しない範囲 / 主な影響:
- レビュー上の注意点・残課題:

<!-- GitHubから確認できる変更ファイル一覧は再掲しない。 -->

# Risk Tier

# Agent Security Boundary

- Tier（LOW / MEDIUM / HIGH）と理由:
- 判定理由・影響範囲:
- 再判定（実装開始 / PR提出 / 影響変更時）:
- 情報分類（PUBLIC / INTERNAL / CONFIDENTIAL） / LLM Trust Boundary:
- Read / Write範囲、Human Approval、例外:
- Sensitive Read Capability × External Write Capability:
- Prompt Injection対策:
- Security / Productionへの影響:

詳細は [Adaptive Development Flow](../blob/main/docs/adaptive-development-flow.md) と [AI Agent Security Boundary](../blob/main/docs/ai-agent-security-boundary.md) を参照する。権限、Secrets、Security Policy、Production操作は人間承認まで停止する。

# Current State

- Current phase:
- Issue acceptance status:
- Product Acceptance result:
- Product Acceptance conditions / deadline / follow-up Issue:
- Product Acceptance target artifact:
- Current Deploy target artifact:
- Current head SHA:
- Expected SHA:
- Verification status（local / CI / Security / Review）:
- Review round / blocking finding status:
- Stop reason:
- Next action:

# 検証とGitHub観測

- 標準検証 / 手動確認:
- 対象SHA:
- CI:
- Security Preflight判定:
- GitHub Security / Code Scanning判定:
- Codex Review:
- 未実行・例外の理由:

CI、Security、Reviewは別々に確認し、対象SHAがPR headと一致することを確認する。Current Stateの正本は [AI Execution State](../blob/main/docs/ai-execution-state.md)。

# Verification Evidence / Residual Risk Summary

詳細な証跡は [Verification Evidence Contract](../blob/main/docs/acceptance-verification.md#5-verification-evidence-contract--residual-risk-summary) に一度だけ保存し、ここでは参照先と最小サマリーを記録する。テスト実行の成功だけをRequirementの`VERIFIED`としない。

- Verification Evidence record / source（`Requirement → Risk → Test → Result → Evidence`）:
- Verified:
- Failed:
- Not Verified:
- Blocked / Skipped:
- Known Remaining Risk:
- Human Decision Required:

# Harness（追加・変更時のみ）

- 台帳ID / 判定:
- 失敗モード・代替制御:
- 再評価条件:

詳細は [Harness Minimalism台帳](../blob/main/docs/ai-development-harness-inventory.md) を参照する。

# Harness Minimalism / ETCSLV

- 対象ハーネス / 台帳ID:
- 削除・再評価条件:

# 実利用検証 / Product Acceptance

- Implementation Done / Deployed / Product Accepted:
- Product Acceptance target artifact:
- Current Deploy target artifact:
- 検証環境・実利用シナリオ:
- 未実施または対象外の理由・引き継ぎ先:

検収の正本は [Acceptance Verification](../blob/main/docs/acceptance-verification.md)。

# レビュー収束

- P0 / P1 / BLOCKING P2:
- 非BLOCKING P2の分類・Follow-up:
- 修正時のPR番号・head branch・修正後SHA:

[Review Evidence Contract](../blob/main/AGENTS.md#review-evidence-contract) と [FOLLOW-UP](../blob/main/docs/review-followups.md)、[Safe Auto-Fix / Auto-Merge](../blob/main/docs/safe-auto-fix-auto-merge.md) を参照する。修正は既存PR branchで行い、最終Mergeは人間が判断する。
