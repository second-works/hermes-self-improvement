# 実地検証フィードバック

`system-monitor-dashboard` V1でNine標準AI開発フローを一周した結果、以下を標準運用として扱う。

## 1. 親Issueの最終確認

子Issueが `Closes #<Issue番号>` により自動Closeされても、親Issue本文のチェックボックスは自動更新されない場合がある。

親IssueをCloseする前に、全子IssueのMerge / Close、全体完了条件、CI、セキュリティチェック、手動確認を照合し、親Issue本文を最終状態へ更新する。

## 2. Dependabot PRの位置づけ

Dependabot PRは開発本線の子Issueとは別の保守作業である。PR番号が本線の間に入っても異常ではない。

開発作業を中断して即時処理する必要はなく、適切な保守タイミングでrelease notes、breaking changes、CI結果を確認してMergeする。

古いmainをベースに作成されたDependabot PRでCIが失敗している場合は、最新mainへrebase / updateしてから再評価する。

## 3. Python CIのBootstrap例外

新規リポジトリでテストファイルがまだ0件の初期段階だけ、pytestの0件終了をBootstrap例外として扱える。

最初のテストファイルが追加された後は例外を終了し、pytestが実際に実行・成功することを必須にする。

## 4. Warning / Deprecation

テスト成功とwarningなしは同義ではない。

warning / deprecationが残っていてもV1完了を妨げない場合は、その理由をPRに記録し、将来の破壊的変更や互換性問題につながる可能性があれば後続メンテナンスIssueとして管理する。

## 5. 実地検証で正常動作を確認した項目

- 親Issueから子Issueへの分割
- 依存関係順の実装
- 1子Issue = 1 PR
- CodexによるIssue範囲内実装
- `Closes #<Issue番号>` による子Issue自動Close
- GitHub Actions CI
- CodeQL
- RulesetによるPR必須化とrequired status check
- 人間による最終Merge

この結果、標準フロー自体に設計変更が必要な欠陥は確認されず、上記の運用補強を標準へ反映する。