# Codexレビューとコメント対応の契約

**Decision: 現行AGENTSの詳細契約を、必要な作業時に参照する文書へ分離する。**

親 [#168](https://github.com/second-works/ai-development/issues/168)、準備 [#173](https://github.com/second-works/ai-development/issues/173)、契約案 [PR #172](https://github.com/second-works/ai-development/pull/172)。原文は `7a52b2b3f46487b91190a6c923926c9325913046` の [固定原文AGENTS](https://github.com/second-works/ai-development/blob/7a52b2b3f46487b91190a6c923926c9325913046/AGENTS.md) の Code Review Rules / Review Evidence Contract / Rule Promotion。

PR #174で移行準備し、先行PRの人間Merge後、Issue #177でAGENTSから参照する詳細正本として有効化した。通常レビューの直接対応は2026-10-03の人間指示を反映し、その他の安全責務・例外を保持する。

初回レビュー・通常コメント対応・同一head検証で参照する。通常経路の変更は人間の明示指示による。既採用Safe Auto-Fix / Auto-Mergeの1ラウンド制限・全Safety Gateは変更しない。

## Code Review Rules

Codex Code Reviewを、GitHub Actions CI後・人間の最終確認前の標準品質ゲートとして使用する。

### 既存PRコメントの直接対応

既存PRのコメントは、CodexがGitHubの指摘・Issue・現head・差分を直接確認して対応する。通常経路ではpr-review-fixやそのhelperを起動しない。同Skillは手動資産として保持し、ユーザーが明示して使う場合の任意参照とする。対象PRが一意に定まらなければ、推測で別PRを書き換えない。

指摘の根拠、今回差分との因果、受入条件を確認し、関連する契約・呼出元・対称実装までまとめて点検する。妥当なIssue内修正は同じhead branchで行い、更新headの検証と再レビューを確認する。改善候補・既存の未変更問題・誤検知を、重大度だけで今回の必須修正へ広げない。

### 起動方法

- CodexのAutomatic reviewsが利用可能なリポジトリでは、原則として自動レビューを有効化する。
- Automatic reviewsが無効または利用できない場合は、PR上で `@codex review` を実行してレビューを依頼する。
- 実装担当Codexの自己レビューだけで完了扱いにせず、PR単位のCodex Code Review結果を確認する。

### レビュー観点

最低限、以下を確認する。

- IssueのAcceptance Criteria / 完了条件を満たしているか
- Issue範囲外の変更が混ざっていないか
- 明確なバグ、回帰、境界値・異常系の見落としがないか
- 必要なテストが不足していないか
- 認証・認可、秘密情報、入力検証などのセキュリティ上の問題がないか
- 不要な依存関係や破壊的変更がないか
- テスト削除・skip・例外握りつぶし等で品質ゲートを回避していないか
- 本来存在しない状態を処理するためだけのdead branchが増えていないか。
- 型・スキーマで防げる不正状態を、実行時チェックだけで処理していないか。
- 同一の信頼境界を通過した後の内部処理で、同じ入力検証が複数箇所に重複していないか。信頼境界ごとに必要な入力検証は重複とみなさない。
- 状態追加時に未対応箇所を型チェックなどの網羅性チェックで検出できる設計になっているか。

### 初回レビューの標準探索観点

初回レビューでは、PR目的に関係する範囲で、差分だけでなく次の関連実装も確認する。

- 変更箇所の呼び出し元・利用箇所への影響
- 類似実装・対称実装との一貫性
- API、データモデル、状態遷移等の既存契約との整合性
- 固定値・特殊処理・例外処理等の設計意図が変更後も保存されているか
- エラー握りつぶし等によるsilent failureがないか
- 外部API / SDK / DB / filesystem等のシステム境界仕様との整合性
- 共通部品変更による波及先

既存コード全体の改善探索へ無制限に広げず、変更内容とIssue目的に関連する範囲に限定する。

## Review Evidence Contract

レビュー指摘はSeverityラベルだけでなく、検証可能な証拠と今回PRとの因果関係を伴う形で記録する。
P0 / P1、および `BLOCKING` 候補のP2には、最低限次の項目を記載する。

```text
Finding ID:
Severity:
Classification:

Location:
- file:
- line / symbol:

Claim:
- 何が壊れるか

Trigger:
- 問題が成立する入力・状態・実行経路

Expected:
- Issue / Design Decision上の期待動作

Actual:
- 現行差分で実際に起こる動作

PR Causality:
- 今回PRのどの差分が原因か

Acceptance Criteria:
- どの受入条件・契約・安全条件に違反するか

Reproduction:
- 再現手順 / failing test / 検証方法

Confidence:
- high / medium / low

Disposition:
- BLOCKING / IN-SCOPE FIX / FOLLOW-UP / DISMISS
```

`BLOCKING` とするには、成立条件、今回PR差分との因果、Issue / 契約 / 安全条件上の根拠、および `Reproduction` または実行再現が困難な場合の決定的な静的根拠を説明できることを要求する。
再現可能な問題は、可能な限り修正前に失敗し修正後に成功するテストまたは再現手順を残す。Security、競合状態、契約違反、型・schema不整合など、実行再現が困難でも静的に成立を説明できる問題では、決定的な静的根拠を使用できる。
Evidence不足の指摘をSeverityだけで `BLOCKING` と扱わない。P2は必ず `BLOCKING / IN-SCOPE FIX / FOLLOW-UP / DISMISS` に分類し、非BLOCKING P2は分類と記録後に追加修正ループへ戻さない。

Review Evidence Contractはレビュー指摘の成立条件とPR因果を記録する契約であり、受入条件・主要リスクの検証結果を記録する契約ではない。後者は [Verification Evidence Contract / Residual Risk Summary](acceptance-verification.md#5-verification-evidence-contract--residual-risk-summary) を正本とし、両者を同じ証跡として二重管理しない。

## Rule Promotion

同種の妥当なレビュー指摘が複数PRで反復する場合は、反復性、誤検知リスク、適用範囲を確認して機械判定可能性を評価する。

- 機械判定可能: lint / type check / test / CodeQL / CI / security ruleへの昇格を検討する
- 機械判定が困難: AGENTS / coding rule / design guidelineへの明文化を検討する

Rule Promotionは自動的にルール化する仕組みではなく、レビュー判断を置き換えない。FOLLOW-UP台帳の責務とも重複させない。

### SeverityとMerge条件

- **P0 / P1**: Merge禁止。必ず修正する。
- **P2**: severityだけでMerge可否を決定せず、必ず `BLOCKING / IN-SCOPE FIX / FOLLOW-UP / DISMISS` に分類する。
  - `BLOCKING`: Merge阻害条件。今回のPR差分が原因で、Issue受入条件違反、明確な機能不具合、回帰、データ破損、セキュリティ問題、または本番運用上の明確な破綻が発生する場合は修正必須とする。
  - `IN-SCOPE FIX`: Issue範囲内で合理的なら修正するが、原則としてMerge blockerではない。
  - `FOLLOW-UP`: 当該PRでは修正せず、既存の記録ルールに従う。
  - `DISMISS`: 修正しない。
- **P3**: 改善候補。原則としてMerge阻害条件にはしない。必要なら後続Issueへ切り出す。
- 最終Merge判断は人間が行う。

標準Merge条件は次のとおりとする。

- GitHub Actions CI成功
- `CI_STATUS=CI_PASSED` かつ、`SECURITY_STATUS=SECURITY_PASSED`。依存チェック対象外の場合は `DEPENDENCY_STATUS=SECURITY_NOT_APPLICABLE` と理由を記録する
- `SECURITY_FAILED` はMerge禁止。`SECURITY_UNAVAILABLE` は人間の明示判断なしに通過させない
- Codex Code ReviewのP0 / P1が0件
- 四分類後の`BLOCKING` P2が0件
- `IN-SCOPE FIX`、`FOLLOW-UP`、`DISMISS` に分類された非BLOCKING P2は、分類と記録のルールに従って残置できる
- 人間の最終確認完了

### 修正ループ

CodexレビューでP0 / P1 / BLOCKINGと分類したP2が見つかった場合は、次の順で対応する。

1. 指摘内容がIssue範囲内か確認する。
2. `@codex review` はレビュー専用とし、レビュー担当に修正を実行させない。P0 / P1 / BLOCKINGと分類したP2の修正は標準手順から `@codex address that feedback` を外し、Codex Desktop / Work等で実施する。
3. 修正前に対象PR番号、head branch、head SHAをGitHub上で確認・記録し、既存PRのhead branchをチェックアウトする。PR番号とIssue番号、head branchと作業用の別branchを混同しない。
4. 指摘がIssue範囲内なら既存PRのhead branch上で修正し、同じhead branchへcommit / pushする。新しいPRを作らず、既存PRを再利用する。
5. pushした修正コミットのSHAを確認し、GitHub上の同じPRのhead branchとhead SHAが、そのpushしたコミットSHAと一致することを確認する。単に修正前後でSHAが異なるだけでは完了扱いにしない。
6. head branchまたはSHAを確認できない、pushした修正コミットSHAとGitHub上のPR head SHAが一致しない、またはSHAが更新されていない場合は、ローカルテスト、CI、セキュリティチェック、再レビューへ進まず停止して人間に確認を求める。
7. head SHAの更新確認後、修正コミットSHAを検証対象SHAとして記録し、そのSHAを対象に次の順で再検証する: 標準検証入口 `./scripts/verify.sh`（lint → type check → test → build） → GitHub Actions CI → 利用可能なセキュリティチェック → `@codex review`。
8. ローカルテスト、CI、セキュリティチェック、再レビューの各結果が、記録した同じ検証対象SHAに対するものか確認する。
9. 再検証完了時に、GitHub上のPR head SHAが、pushした修正コミットSHAおよび記録した検証対象SHAと一致することを確認する。不一致の場合は完了扱いにせず停止して人間に確認を求める。
台帳登録後の検証対象SHAの扱い:

- 更新後のheadに対する再レビューで新しいP2を `FOLLOW-UP` かつ `ISSUE` と判定した場合、同じhead branch上で中央台帳へ登録するcommitを作成する。
- 台帳登録commitを作成したら、SHA照合前に `git push origin "HEAD:refs/heads/$HEAD_BRANCH"` を実行する。pushが成功しない場合はSHA照合・再検証へ進まない。
- 台帳登録commitでhead SHAが変わるため、登録前の `EXPECTED_SHA` とローカル検証・CI・セキュリティチェック・再レビュー結果は新しいheadの検証には使わない。
- 台帳登録commitのSHAを新しい `EXPECTED_SHA` / 検証対象SHAとして記録し、GitHub上の同じPRのhead SHAと一致することを確認する。
- 台帳登録後の新しいSHAに対して、標準検証入口 → GitHub Actions CI → 利用可能なセキュリティチェック → `@codex review` を同じ順で再実行する。各結果と最終head確認が新しいSHAに対するものになるまで完了扱いにしない。
- 台帳登録を行わない `NOTE` / `DISMISS` の分類では、この台帳登録後の再検証遷移を開始しない。

10. 更新後のheadに対する再レビューで前回のBLOCKINGが解消され、新しいP0 / P1 / BLOCKING P2がないことを確認する。非BLOCKING P2は四分類・記録後に追加修正ループへ戻さない。
11. 更新headの指摘を根拠・今回差分との因果・受入条件で判定する。通常レビューは回数だけで停止せず、関連責務をまとめて点検して修正を収束させる。P0 / P1 / BLOCKING P2が残る場合はMerge禁止。非BLOCKING P2は分類・記録後に追加修正ループへ戻さない。
12. 仕様判断・破壊的変更・Issue範囲拡大が必要、対象branchへpushできない、安全に解消できない依存/競合など、具体的な判断・安全境界に達した場合は停止して人間に判断を求める。反復自体は原因分析のきっかけとし、回数だけを停止理由にしない。

通常レーンのMergeは人間が最終判断する。Safe Auto-Fix / Auto-Mergeレーンは、[`docs/safe-auto-fix-auto-merge.md`](safe-auto-fix-auto-merge.md) のSafety Gateをすべて満たし、人間が採用を明示した場合に限り、記録された主体がAuto-Mergeできる例外として扱う。

### Safe Auto-Fix / Auto-Merge

- `IN-SCOPE FIX`であることだけではAUTO-FIX eligibleとはみなさず、Safety Gateの全項目を確認する。
- P0 / P1 / `BLOCKING` P2、仕様・設計判断、公開契約、DB、auth、security、infra、Deploy、network、Workflow権限、dependency major update、テスト弱体化、Issue範囲外変更は通常レーンへ戻す。
- AUTO-FIXは原則1ラウンドだけとし、修正で変わったhead SHAに対して標準検証 → CI → 利用可能なSecurity（または事前定義済みの安全な適用除外） → Codex再Review → 最終SHA確認を実施する。
- 自動修正後の再レビューで新しいP2が1件でも発生した場合は、分類・記録後もAuto-Mergeせず通常レーンへ戻す。非BLOCKING P2でも追加AUTO-FIXへ戻さない。
- Auto-MergeはP0 / P1 / `BLOCKING` P2がなく、元P2が解消し、全検証対象SHAとPR head SHAが一致し、監査記録が残る場合だけ許可する。条件を満たさない場合は人間の通常レーンへ戻す。
- Auto-Mergeでは `SECURITY_STATUS=SECURITY_PASSED` を必須とし、`SECURITY_FAILED` または `SECURITY_UNAVAILABLE` は許可しない。`SECURITY_NOT_APPLICABLE` は対象外理由と人間の監査記録がある場合だけ通常のMerge判断で扱う。
