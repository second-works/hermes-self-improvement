# GitHub Ruleset / Branch Protection 設定ガイド

## 目的

`AGENTS.md` に記載した「mainへ直接pushしない」「CI成功後にMergeする」などのルールを、GitHub側でも強制する。

Nine標準AI開発フローでは、Codex側の自己チェックとGitHub側の強制チェックを二重化する。

## 推奨対象

`main` branch

## 推奨Ruleset名

`protect-main`

## 設定手順

先に[利用条件と未保護時の扱い](../../docs/github-repository-security-baseline.md#利用条件と未保護時の扱い)を確認し、プラン・権限・現在の設定と人間の設定承認を記録する。利用不能・取得不能・承認待ちならここで停止する。

1. 対象GitHubリポジトリを開く。
2. `Settings` を開く。
3. 左メニューの `Rules` → `Rulesets` を開く。
4. `New ruleset` → `New branch ruleset` を選ぶ。
5. Ruleset name に `protect-main` を入力する。
6. Enforcement status を `Active` にする。
7. Target branches で `main` を対象にする。
8. 以下のルールを設定する。

## 標準で有効にするルール

### Require a pull request before merging

有効にする。

目的:

- mainへの直接変更を避ける
- 1 Issue = 1 PR運用をGitHub側でも担保する
- PR差分、CI結果、レビュー履歴を残す

個人開発の初期段階では、承認レビュー人数を必須にすると自分自身でMergeできないケースがあるため、`Required approvals` はまず0またはGitHubプラン/運用に合わせて設定する。

### Require status checks to pass before merging

有効にする。

GitHub Actionsを一度実行してから、CI workflowのstatus checkを必須対象として選択する。

workflow名ではなく、対象PRのcheck-runsで実在するjobのcheck名と発行元Appを確認して選ぶ。このrepoでは `Template CI` の `verification` と `Security` の `Security Preflight`（ともに `github-actions`）を確認済み。他repoへこの名前をそのままコピーせず、配置したworkflowの実結果から選択する。可能なら期待する発行元Appも指定し、最新baseとの整合性を要求する。

初回リポジトリでは、CI workflowを配置しただけではstatus check候補が表示されない場合がある。その場合は一度PRまたはpushでActionsを実行してからRulesetへ戻る。

### Block force pushes

有効にする。

### Restrict deletions

`main` branchを誤って削除しないよう有効化を推奨する。これは保護対象branchの削除を制限する設定であり、Issue用の短命head branchを自動削除する設定とは別である。

リポジトリのPull Requests設定で `Automatically delete head branches` をONにし、Merge済みPRのIssue用head branchは原則自動削除する。

### Require conversation resolution before merging

レビューコメントを利用するプロジェクトでは有効化を推奨する。

## 最初は任意でよいルール

以下はプロジェクト規模や運用成熟度に応じて追加する。

- Require signed commits
- Require linear history
- Require merge queue
- Require code scanning results
- Required approving reviews

初回の小規模個人開発では、ルールを厳しくしすぎて開発不能になることを避け、まずPR必須・CI必須・force push禁止を中心にする。

## Bypass

原則として通常開発ではRulesetを迂回しない。

管理者等へbypass権限を付ける場合も、緊急時やRuleset設定ミス修正用として扱う。

Codexや通常の自動化処理へ安易にbypass権限を与えない。

Rulesetsは対象branchへ適用される全ルールとbypass対象・モードを確認する。classic方式では `Settings` → `Branches` で対象branchの同等ルールを設定し、管理者にも適用する `Do not allow bypassing the above settings` を確認する。既存の別ルールを無効化して置き換えない。

## Nine標準推奨値

```text
Ruleset name: protect-main
Status: Active
Target: main

Require pull request: ON
Required approvals: 0（初期個人開発）
Require status checks: ON
Block force pushes: ON
Restrict deletions: ON
Automatically delete head branches: ON
Conversation resolution: 推奨
```

## CI必須化のタイミング

新規リポジトリ初期化時は次の順番で設定する。

```text
CI workflow配置
    ↓
最初のPR / Actions実行
    ↓
CI status check名がGitHubに登録される
    ↓
RulesetでRequire status checksをON
    ↓
CI成功しないPRはMerge不可
```

## Bootstrap CIについて

新規リポジトリでは、最初の基盤Issueより前にテストファイルが存在しないことがある。

Nine標準Python CIテンプレートでは、テストファイルがまだ存在しない場合のみBootstrapとしてpytestをskipする。テストファイルが作成された後は、pytestが存在しない・失敗する場合はCIを失敗させる。

この例外は「テストが存在するのにskipする」目的では使わない。

## 確認項目

Ruleset作成後に以下を確認する。

承認された設定だけを適用し、APIまたはSettingsで対象branch・有効状態・required checks・bypassを再取得する。拒否動作は別途許可された隔離repo / branchに同等設定を用意し、通常actor（bypassなし）で検証する。実mainへの直接push・force push・削除で試さない。隔離検証は実mainの拒否実証とは区別し、未実施項目は未確認と記録する。

- mainへの直接pushが防止されるか
- PRからMergeできるか
- CI失敗時にMergeがブロックされるか
- CI成功後にMerge可能になるか
- force pushが禁止されているか
- 保護対象branchの削除が禁止されているか
- 管理者・Appを含むbypassが承認した範囲だけか

実際のプロジェクトで問題があれば、`ai-development` の標準設定自体を見直す。
