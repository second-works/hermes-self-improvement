# Issue #7の調査結果と未決事項

## 調査後の合意

2026-10-23、ユーザーは「AIが決まった操作を選んで実行できる」を採用し、実装へ進むことを承認した。
最新のGoalとScopeは[Issue #7](https://github.com/second-works/hermes-self-improvement/issues/7)、構成と操作方法は[登録済み操作の実装資料](registered-operations.md)に記録する。
完了範囲の変更は合意済みであり、自由生成と自律的な再利用の成功を追加で求めない。
独立評価、本番採用、日次実行を完了扱いにする合意ではない。

元checkoutのindexとlogsを保持し、最新mainの`75d09d8c52215a1060ec342562cef1492aaf62e1`から別worktreeの`issue-7-controlled-operations`で実装を進めた。
必要な48ファイルを作業ファイルからコピーし、元のrunsとlogsは移していない。
この方法で後述の4 PRを実装基準へ反映した。

## 初期調査時点の記録

2026-10-23時点の確認結果。
登録済み修正の選択とハーネス実行は成功したが、既存設計が求める候補の品質合格と新セッションでの再利用成功は揃っていない。
Issue #7全体は未完了として扱い、完了条件の変更は未決定のまま保持する。

Risk Tier: LOW。今回は調査結果と過去の試験記録の区別を文書化するだけで、実装、完了条件、安全境界は変更しない。
Issue #7の実験自体のHIGH判定は維持する。
情報分類はPUBLICの検査済み証拠とINTERNALの作業状態で、保存先は本リポジトリ内だけ。
外部書き込み、モデル通信、本番参照、サービス操作は行わない。

## 指摘と確認結果

| Claudeの指摘 | 確認結果 | 対応状態 |
| --- | --- | --- |
| 完了の解釈が未決定 | 既存条件は存在する。未決定なのは、登録済み修正を選ぶ構成へ完了範囲を変更するかどうか | 判断待ち。条件は変更しない |
| 起点がmainよりPR 4件ぶん古い | 現HEADから確認済みorigin/mainまで、#17、#22、#23、#24の4件、16コミットの差がある | 取り込み未実施 |
| 資料に古い現状記述がある | 冒頭の102/102呼出と、本文の「現在は35/40呼出」「実行承認待ち」が併存していた | 過去の記録と明記し、このメモへ案内 |

## 到達点と未達条件

[Issue #7](https://github.com/second-works/hermes-self-improvement/issues/7)は確認時点でOPEN、コメントは0件。
Issue本文は、親から子への委任、候補作成、単体テスト、成果物の記録、評価基盤への受け渡しを求めている。
[既存設計の「最小実証」](skill-delegation.md#最小実証)は、さらに履歴を継がない新セッションでの再利用を定めている。
再利用はIssue本文の明示条件と、設計で追加された条件を区別して扱う。

| 対象 | 保存済み証拠の結果 | 判定上の意味 |
| --- | --- | --- |
| 実親から実子への委任とモデルによる候補生成 | SKILL.mdとreview.pyを2試行で保存。公開6問で4/6、3/6 | 生成は成立、品質は不合格 |
| モデルによる限定修正 | 最良5/6まで改善。その後の修正は退行 | 品質合格には未到達 |
| 登録済み修正の選択とハーネス適用 | 6/15から15/15へ改善、次の判断で修正不要を選択 | 限定された操作選択方式の成功 |
| ハーネスによる別の2入力の実行 | 実stdoutから厳密なJSONを保存 | 固定課題の直接実行が成功 |
| 新セッションでのスキル再利用 | 自由回答方式はJSON形式不合格。最新方式のreuseはNOT_APPLICABLE_DIRECT_EXECUTION | 再利用成功の代替証拠にはしない |
| 独立評価 | 未実施。15問の追加ケースは封印された独立評価ではない | 評価合格や採用待ちには進めない |
| 本番適用と日次自動実行 | 未実施 | 今回の成果に含めない |

根拠：

- [実候補の生成結果](evidence/skill-delegation-created-candidates.json)
- [限定修正の結果](evidence/skill-delegation-bounded-repair.json)
- [新セッション再利用試験の結果](evidence/skill-delegation-cycle-reuse-contract.json)
- [操作選択と直接実行の結果](evidence/skill-delegation-controlled-execution-live.json)
- [改善試験の経緯と最新結果](gemma-e4b-improvement-cycle.md)

最新の保存済み集計は累計102/102呼出、入力302510token、出力予約59363token。
これは過去の実験の記録であり、追加通信の許可や現在のサービス状態を示さない。
今回は試験を再実行せず、文書とJSON証拠を照合した。

## 完了範囲について必要な判断

既存条件を維持する場合は、品質合格したモデル生成候補と設計上の再利用成功を揃え、既存の独立評価と受け渡し条件を満たす必要がある。
追加実験の方法、予算、実行境界は改めて具体化する。
過去の呼出枠やサービス変更の承認は流用しない。

登録済み修正を選ぶ構成を今回の到達点とする場合は、その限界と未達事項を明記した完了範囲の変更案を作り、人間の合意後にIssueと設計へ反映する。
その合意だけで、未実施の独立評価や本番採用まで完了扱いにはしない。
従来の生成と再利用を継続するか、後続へ分けるかも、その時点で決める。

本メモは両案の採用を決めるものではない。
完了範囲が決まるまでは、Issue Closeや追加モデル実験へ進めない。

## mainとの差とローカル成果の保全

| 確認対象 | 値 |
| --- | --- |
| 作業ブランチ | issue-7-isolated-skill-delegation |
| HEADとローカルmain | 10419e1a49b62b28c6862102c7f08d8c9d03f4b2 |
| 確認済みorigin/main | 75d09d8c52215a1060ec342562cef1492aaf62e1 |
| 今回の文書整理前のindex | 47ファイル、7757行の追加がステージ済み |
| その他 | logs/が未追跡 |

今回の文書整理前の差分を、次のコマンドで確認した。

```sh
git rev-parse HEAD origin/main
git log --first-parent --oneline HEAD..origin/main
git diff --cached --stat
git status --short --branch
```

| 未反映PR | mainへ入った変更 |
| --- | --- |
| [#17](https://github.com/second-works/hermes-self-improvement/pull/17) | 作業ログ候補のオフラインCLI |
| [#22](https://github.com/second-works/hermes-self-improvement/pull/22) | 開発ルールの軽量構成への切り替え |
| [#23](https://github.com/second-works/hermes-self-improvement/pull/23) | CLI出力失敗時の不完全な成果物の防止 |
| [#24](https://github.com/second-works/hermes-self-improvement/pull/24) | JEVとLocal Judgeの実行資産の撤去 |

取り込みは未実施。
先にindexと作業ファイル、未追跡logsの保全方法を決め、その後で最新mainを再確認して統合する。
特に#22と#24は開発手順と参照資産を変えるため、統合後の規則と差分全体を再確認し、標準検証と必要なSecurity検証をやり直す。
取り込み前の試験結果を統合後の成功として流用しない。

## 資料整理の範囲と次の作業

今回、skill-delegation.mdの冒頭にこのメモを追加し、35/40呼出時点の説明を過去の記録として明記した。
gemma-e4b-improvement-cycle.mdにも、各試験時点の承認待ちや上限を現在の状態と区別する案内を付けた。
試験履歴と不合格の証拠は保持する。

次の作業は、未コミット成果の保全とmain取り込み、統合後の再検証、完了範囲の具体案の確認である。
コミット、push、PR作成、Issue更新、Merge、追加実験は今回行っていない。

## 今回の文書整理の検証

- `./scripts/verify.sh`：成功。lintと既存30テストが通過。
- typecheckとbuild：各入口scriptが非実行のため、既存動作どおり理由付きskip。
- 編集した3資料のローカルリンク：参照先の存在を確認。
- 文書差分の自己確認：試験結果、履歴、未決事項を分け、完了条件と承認範囲を変更していないことを確認。

標準lintのソース構文検査はindexが対象で、今回のMarkdown整理は作業ファイル側に保持している。
この検証を、Issue #7の実験の再実行、独立評価、Securityの全体合格、CI、正式レビュー、Product Acceptanceの証拠にはしない。
元のindexは変更していない。
