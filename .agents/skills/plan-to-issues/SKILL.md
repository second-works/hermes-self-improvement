---
name: plan-to-issues
description: 合意済みの計画・方針・設計を、Nine標準AI開発フローの既存Gateを通してGitHub Issueへ変換・登録する。ユーザーがSkill名を明示しなくても、「この方向でIssue化して」「親Issueと子Issueに分けて」「実装できるIssueにして」「この計画をGitHub Issueベースにして」「Codexで進められる形に分割して」など、現在の合意内容を実装可能なIssueへ変換する自然文または近い表現で使う。既存Issueの実装・レビュー・コメント確認、Issue一覧や状態確認、単なるIssue本文の文言修正には使わない。
---

# Plan to Issues

合意済みの計画・方針を、未決定事項を実装者へ持ち込まず、レビュー可能なGitHub Issueへ変換するSkill。

このSkillは既存Gateの正本ではない。Framework Decision、Plan Review、Risk Tier、Child Issue Quality Gateの詳細を再定義せず、それぞれの正本文書を参照して順番に実行する。

## Canonical References

Issue登録前に必要な範囲で次を読む。

- [Plan Review Gate](../../../docs/plan-review-gate.md)
- [Child Issue Quality Gate](../../../docs/issue-quality-check.md)
- [Adaptive Development Flow / Risk Tier](../../../docs/adaptive-development-flow.md)
- 新規Web/UIまたはFramework判断が必要な場合は [Framework Decision](../../../docs/architecture/framework-decision.md)
- PRODUCT UIが適用される場合は、Plan Reviewから参照されるUI正本と案件Design Decision
- Security / Deployment / Acceptanceなど条件発生時の詳細は、上記正本から接続される既存文書

同じ詳細をSkill本文へ複製して独自基準を作らない。[最小契約の条件付き参照](../../../docs/minimal-development-contract.md#条件付き参照)に従い、非該当のFramework / UI / State / Harnessの空欄は出力しない。該当する安全制御・承認・例外とAcceptance対象は省略しない。

## 1. 入力となる合意を固定する

現在の会話、計画書、Design Decision、ユーザーの明示指示から、Issue化する範囲を短く整理する。

- 目的
- 採用済みの方針・Design Decision
- Scope / Non-goals
- 成功条件
- 既知の依存関係
- 変更対象の概略
- 未決定に見える事項

ユーザーが「この方向で」と指示した場合、会話上すでに確定している内容を再質問しない。重要事項が未決定かどうかは既存Gateで判定する。

## 2. Issue化前Gateを順番に実行する

原則として次の順序を守る。

```text
Requirements / agreed plan
  ↓
Framework Decision（適用時）
  ↓
UI Level Decision（UI適用を確認し、UIがある場合だけ記録）
  ↓
PRODUCT前提（PRODUCT時のみ）
  ↓
Plan Review Gate
  ↓
Design Decision（NEEDS_DECISIONの場合）
  ↓
Risk Tier
  ↓
Issue構造案
  ↓
Child Issue Quality Gate
  ↓
GitHub Issue登録
```

- UIの適用確認は全案件で行う。UIがある場合は `UTILITY / PRODUCT` と分類理由・参照をContextに記録する。非UIに `NONE` 欄を強制しない。UIを持つ可能性があるのに分類できない場合は `NEEDS_DECISION` として停止する。
- Framework Decision、UI LevelまたはPlan Reviewが `NEEDS_DECISION` の場合はIssue登録へ進まない。
- Plan Reviewが `PASS` または理由付き `NOT_APPLICABLE` の場合だけIssue構造案へ進み、その判定・理由・正本参照をGitHub上のIssue本文へ保存する。
- 重要な判断を推測で埋めない。
- Risk Tierは [Adaptive Development Flow](../../../docs/adaptive-development-flow.md) の正本で判定し、IssueへTierと理由を記録する。
- Child Issue Quality GateのMUST不足はScoreで相殺せず、補完・分割・統合・依存整理が終わるまで登録しない。

## 3. Issue構造を決める

### 複数PRに分かれる場合

親Issueをロードマップとして作り、実装は子Issueへ分割する。

- 親Issueはプロジェクト全体の目的、主要Decision、Scope / Non-goals、子Issue一覧、依存順序、全体完了条件、検収計画を持つ。
- 親Issue自体をCodexの実装単位にしない。
- 子Issueは原則 **1子Issue = 1 PR** とする。
- 子Issue間の依存を明示し、同じ重要ファイルを競合して触る可能性が高いものを根拠なく並列化しない。

### 1 PRで完結する場合

空の親Issueを作ること自体を目的にしない。既存Child Issue Quality Gateを満たす単一Issueとして登録してよい。

単一Issueを複数の見出しに分けただけで、実装責務が複数混在する状態を許可しない。

## 4. Issue本文を既存templateへ合わせる

親Issueは `.github/ISSUE_TEMPLATE/parent-issue.md`、子Issueまたは単一Issueは `.github/ISSUE_TEMPLATE/child-issue.md` を入力契約として使う。

子IssueはGoal / Context / Scope・Boundaries / Non-goals / Done / Verification / Dependenciesの最小入力契約を使い、正本が要求する今回値を埋める。合意済み計画のPlan Review結果はContextへ一行で保存する。

- 目的
- Plan Review結果（`PASS / NOT_APPLICABLE`）、理由、正本参照
- UIがある場合のUI Level、分類理由、必要なDesign Decision参照
- 変更範囲
- Non-goals / 変更禁止範囲
- 完了条件
- テスト条件
- 依存関係
- Risk Tierと理由
- Security / Human Approval等の安全境界
- 必要なDesign Decision参照

具体的な必須項目と判定はtemplateおよび [Child Issue Quality Gate](../../../docs/issue-quality-check.md) を正本とし、この一覧だけで代替しない。

## 5. 登録前に全Issueを検査する

GitHubへ書き込む前に、すべての子Issueまたは単一IssueへChild Issue Quality Gateを適用する。単一Issueでも、Plan Reviewの判定・理由・正本参照をContextへ、UIがある場合の分類と参照もIssue本文へ保存する。

- MUST不足があれば、まずdraftを補完・分割・統合・依存整理する。
- 不足を解消するために未承認の設計判断が必要なら、Issue登録を停止してDesign Decisionへ戻す。
- SHOULD不足だけなら、実装可能性を損なわない範囲で簡潔さを優先できる。
- 親Issueと子Issueへ同じ詳細を全文複製せず、親はロードマップ、子は実装契約に分ける。

## 6. GitHubへ登録する

ユーザーが実際のIssue化・登録を依頼している場合だけGitHubへ書き込む。「Issue案を見せて」「どう分ける？」など提案だけの依頼では登録しない。

複数Issueの場合は次の順にする。

1. 親Issueを登録する。
2. 実際の親Issue番号 / URLを使って子Issueを登録する。
3. 子Issueの実番号を使って親Issueの子Issue一覧・依存関係を更新する。
4. 登録後に親子関係、依存順序、1 PR単位が意図どおりか確認する。

GitHubが返したIssue番号やURLを使用し、番号を推測しない。

## 7. 登録後の境界

Issue登録が完了したら、このSkillの作業は終了する。

- branchを作らない。
- Issueの実装を開始しない。
- PRを作らない。
- Mergeしない。
- 次のIssueへ自動着手しない。

生成だけの依頼から実装を始めない。実装も既に明示指示されている場合は再承認を要求せず、Skillの登録作業を終えて既存Implementation Workflowへ進む。

## 停止条件

次のいずれかではIssue登録を行わず、停止理由と必要なDecisionを示す。

- Framework Decision / UI Level / Plan Reviewが `NEEDS_DECISION`
- Child Issue Quality GateのMUST不足を、既存の合意だけでは解消できない
- Scopeまたは成功条件が未確定でIssue構造が変わる
- 依存関係が不明で、安全な直列化・並列化を決められない
- Security / Production / data migration等の重要境界を推測する必要がある
- 対象repositoryを一意に特定できない

## 標準出力

登録した場合は簡潔に次を示す。

- Plan Review結果: `PASS / NOT_APPLICABLE`
- Risk Tier
- 親Issue（作成した場合）
- 子Issue / 単一Issue
- 実装順序・依存関係
- 登録しなかった項目またはNon-goals
- 次のアクション: 実装指示が未取得なら人間判断を待つ。既に実装も指示済みなら、このSkillを終了して標準実装フローへ進む

停止した場合は、作成していないことを明示し、`NEEDS_DECISION` または不足MUSTと、解消に必要な判断だけを示す。
