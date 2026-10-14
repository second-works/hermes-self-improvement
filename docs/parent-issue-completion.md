# 親Issueの完了確認

**Decision: 現行AGENTSの詳細契約を、必要な作業時に参照する文書へ分離する。**

親 [#168](https://github.com/second-works/ai-development/issues/168)、準備 [#173](https://github.com/second-works/ai-development/issues/173)、契約案 [PR #172](https://github.com/second-works/ai-development/pull/172)。原文は `7a52b2b3f46487b91190a6c923926c9325913046` の [固定原文AGENTS](https://github.com/second-works/ai-development/blob/7a52b2b3f46487b91190a6c923926c9325913046/AGENTS.md) の Parent Issue Completion。

PR #174で移行準備し、先行PRの人間Merge後、Issue #177でAGENTSから参照する詳細正本として有効化した。通常レビューの直接対応は2026-10-03の人間指示を反映し、その他の安全責務・例外を保持する。

## Parent Issue Completion

子IssueのPRが `Closes #<Issue番号>` で自動Closeされても、親Issue本文の子Issueチェックボックスは自動更新されない場合がある。

親IssueをCloseする前に以下を必ず確認する。

1. すべての必要な子IssueがMerge / Close済みか。
2. 親Issue本文の子Issueチェックボックスを最終状態へ更新したか。
3. 全体完了条件を実際のPR、CI、セキュリティチェック、AIレビュー、手動確認結果と照合したか。
4. warning / deprecation等の残課題を確認し、必要なら後続メンテナンスIssueへ切り出したか。
5. 人間が最終確認したか。
