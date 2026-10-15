# 段階的実装計画案

最初に独立評価を完成させ、候補作成と承認を接続した手動1サイクルを実証する。
Memory、公式Self-Evolution、Cronは実証と承認を経て接続する。本番採用と定期運転は最後に判断する。
[Issue #2](https://github.com/second-works/hermes-self-improvement/issues/2) の成果物は [architecture](architecture.md) と [security-model](security-model.md) を含む文書3点。Risk Tier: HIGH（安全境界の設計）。後続Issueの本文は今回変更せず、重要未決を解消するまで実装しない。

## 既存Issueとの依存

Issue番号は実行順を意味しない。依存を満たしてから、1子Issue=1 PRで進める。

| 順序 | Issue | 依存・今回確認した役割 | 完了証拠 |
| --- | --- | --- | --- |
| 完了 | [#1 共通開発基盤](https://github.com/second-works/hermes-self-improvement/issues/1) | #2の前提。2026-10-15 Close、PR #10はmainへMerge済み | 最新mainとIssue状態 |
| 現在 | [#2 基本設計](https://github.com/second-works/hermes-self-improvement/issues/2) | 図、入出力、権限、上限、独立評価、段階計画 | 文書、標準検証、self-review、PRの同一head CI/Security/Codex Review、人間判断 |
| 1 | [#3 Memory検証](https://github.com/second-works/hermes-self-improvement/issues/3) | #2。隔離homeの合成識別子で保存/別セッション/再起動検索 | 正常・競合・欠如・mask・復旧。実Memoryとの統合は別承認 |
| 1 | [#5 独立評価](https://github.com/second-works/hermes-self-improvement/issues/5) | #2。匿名github-code-review fixture、hidden隔離、劣化版判別 | 両SHAと環境固定のJSON/レポート、PASS/FAIL/HOLD、安全拒否 |
| 2 | [#4 監査・診断](https://github.com/second-works/hermes-self-improvement/issues/4) | #2/#3。fixtureによる失敗6分類と根拠付き提案 | 同一入力の再現、誤判定・過剰生成の検査 |
| 2 | [#6 公式隔離spike](https://github.com/second-works/hermes-self-improvement/issues/6) | #2/#5。固定upstream/依存、CLIと候補変化を実証 | logs、lock、実コマンド、副作用、費用、採否理由 |
| 3 | [#7 候補委任](https://github.com/second-works/hermes-self-improvement/issues/7) | #4/#5。単一workerと候補1件、予算・timeout・限定パス | diff、単体検証、認証不能時の停止。hidden/本番/Secret権限なし |
| 4 | [#8 PR承認・復旧](https://github.com/second-works/hermes-self-improvement/issues/8) | #1/#5/#7。通常レーンのPR、対象/SHA別承認 | 必須の別試験2種: 模擬採用はADOPTED、故障注入・復旧はROLLED_BACK。全Gate、人間承認、両試験のhash一致 |
| 5 | [#9 手動ループ・Cron](https://github.com/second-works/hermes-self-improvement/issues/9) | #3/#4/#5/#6/#7/#8 | fixtureのOBSERVED→ADOPTEDを1回接続。復旧は別試験でROLLED_BACK、上限停止/排他/通知、継続と定期化の承認 |

#3と#5、#4と#6は依存上別系統だが、重要ファイル競合と優先順位を確認せず並列着手しない。この表は委任や複数agentを起動する許可ではない。
#6が不採用でも調査と人間の採否判断を完了証拠にし、未検証のまま#9へ進めない。#9の実装は採用された方式を使う。

## 実装前に確定する判断

| 判断 | 提案・未確認 | 解消先・停止点 |
| --- | --- | --- |
| 実行環境 | 合成fixture、空HOME、networkなし。Docker/arm64/資源は未実証 | #5開始前に隔離方式を承認。拒否試験成功まで候補実行停止 |
| 予算 | 最初はAPI 0 USD、1候補、全体20分。API試験は1 USD/20呼出が案 | #6/#7の実験前にprovider・モデル・料金と上限を承認 |
| 評価基準 | fixture閾値はarchitecture参照。一般品質の統計的基準は未確定 | #5でデータ・指標・閾値・HOLD基準を候補生成前に固定 |
| 公式互換性 | v0.21.5の基準公開commitを静的確認。本番revision・依存適合・成功経路は未検証 | #6で隔離実証。直接導入の前提にしない |
| Memory | Issueの「有効な読出し未検証」は継承。新DB/RAGは導入しない | #3で隔離検証。本番の確認が必要なら具体的な読取範囲を別承認 |
| Skills件数 | 123/124はIssueの過去観測。builtin/local/hub/profile差は未解明 | #4で集計定義を固定。fixture検証と本番事実を区別 |
| GitHub提出 | 既存repoの対応branch、検査済みPUBLIC要約 | push/PR提出前に承認確認。Gateと人間Mergeを保持 |
| 監査保存 | run別hash付き追記。期間・保存先未確定 | #3/#8開始前に保存・削除境界を確定 |
| 採用/復旧 | 最初はfixture模擬だけ。本番targetは未承認 | #8で模擬実証。本番適用は具体的差分・対象・backup・復旧票を提示後に承認 |
| 定期化 | defaultのCron 0件は過去観測。将来は診断/提案通知だけ | #9で通知宛先、重複、再起動、結果回収、不達を検証。有効化は別承認 |

これらは設計案としてレビューできるが、未承認の重要実装判断を推測で決めない。既存Issueが本番の読取を要する場合も、現在のAGENTSによる禁止を解除したとは解釈しない。

## 最小サイクルの検収手順案

終了境界は、#5/#7の候補作成・評価段階が `AWAITING_APPROVAL`。#8は単一の終了状態を持つサイクルではなく、人間承認・模擬採用の `ADOPTED` と、別の故障注入・復旧試験の `ROLLED_BACK` を両方必須とする。#9では観測からfixtureの `ADOPTED` までを1サイクルとして検収し、#8の復旧試験も別に再検証する。すべてfixture配備先に限定し、本番採用を含めない。

1. #5で隔離と評価を先に実証する。基準、意図的劣化版、安全違反版を固定し、分類の期待値を確認する。
2. #3/#4で合成の失敗観測から根拠付きproposalを作る。基準SHA、公開データ、予算、allowlistを固定する。
3. #7で1候補だけ作成し、単体検証とdiffを保存する。#6の方式が未採用なら公式CLIに依存しない。
4. 独立評価者が未知データで基準と候補を比較する。FAIL/HOLDは停止、PASSだけ承認待ちへ進む。
5. #8で検査済みの評価・差分・未確認を対応PRにまとめ、local→CI→Security→CodeQL→Codex Reviewを同一headで確認する。Mergeは人間が判断する。
6. #8でfixtureだけの人間承認票→模擬採用（ADOPTED）と、別の故障注入・復旧試験（ROLLED_BACK）を検査する。後者は採用後劣化と採用途中の部分適用/再起動の両方からRECOVERY_REQUIRED→人間承認→ROLLING_BACK→ROLLED_BACKを確認する。#9で観測から模擬採用までの手動1サイクルと上限停止を再現し、復旧試験も別に再検証する。

初期の品質差はfixtureでの結果として報告し、本番性能や汎用的な改善と呼ばない。API実験・本番採用・Cron運転はこの検収から分離する。

## Issue #2の検証境界

図の各遷移と入出力を読み合わせ、成功・棄却・証拠不足・予算境界・異常終了・再起動・二重実行・承認SHA変更・復旧失敗を追跡する。
リンク、固定ソース、3文書間の状態・上限・依存・権限の整合、Hermes本番を使わないことをself-reviewし、`./scripts/verify.sh` とBash 5以上のSecurity Preflightを実行する。
文書検証の成功と実行機能の完成を区別する。今回、最小サイクルのコード、公式CLI実行、Memory検証、Docker、モデルAPI、Cron、本番採用は未実施。実装済みと報告しない。
