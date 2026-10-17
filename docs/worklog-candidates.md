# 合成作業ログの対応候補CLI

Issue [#16](https://github.com/second-works/hermes-self-improvement/issues/16)。2026-10-18開始。
Risk Tier: MEDIUM。PUBLICの架空fixtureだけを読むオフライン機能で、権限・本番・既存Gateの変更はない。

人が原文へ戻れる5分類の候補一覧を、JSONとMarkdownで出す初期実装。
今回の合意は「通信なしで入力・根拠・状態・出力契約を確認する」まで。
Gemma分類精度、実ログの利用、有用性の人間検収は未実施。
提出後のcommit・CI・Security・Codex Reviewの対象SHAと結果はPRを正本とする。

## 実行

専用worktreeのrepo直下で実行する。Python標準ライブラリのみ。

```sh
python3 -I -B scripts/report_worklog_candidates.py --evaluate
python3 -I -B scripts/report_worklog_candidates.py --format markdown
python3 -I -B scripts/report_worklog_candidates.py --responses responses/complete.json
python3 -I -B scripts/report_worklog_candidates.py --responses responses/partial.json
python3 -I -B scripts/report_worklog_candidates.py --packets
```

既定manifestは `fixtures/worklog_candidates/manifest.json`。
`--manifest` と `--responses` のpath基準はこのfixtureディレクトリ。実ログrootを指定する機能はない。
入力は人がPUBLICの架空資料として用意したものに限定し、分類ラベルだけで実データを安全と判定しない。

`--output <新規ディレクトリ>` を付けると `report.json` と `report.md` を作る。
親ディレクトリは既存であること。既存出力への上書き・追記は拒否する。
stdoutも同じ結果を返す。入力・JSON形式・filesystemの失敗はexit 2、固定codeだけをstderrへ出す。
出力途中のfilesystem障害では新規出力先に部分ファイルが残り得る。CLIの失敗を無視して採用しない。原本を削除して復旧しない。

`COMPLETE` / exit 0は入力と応答coverageの処理完了だけを表す。
意味的な正解、未解決0件、承認取得、実用性の受入を表さない。
形式違反、欠落応答、未対応構文は全候補を保持して `PARTIAL` / exit 2とする。
文脈不足による意味的な判断保留は `COMPLETE` の一覧にも含まれ、保留率を報告する。

## 入力と状態の契約

manifestはschema_version=1、classification=PUBLIC、source_kind=synthetic-fixture。
各fileはpath・sha256・session_id・task_id・scenario_id・sequenceを持つ。
初期fixtureは **1ファイル=明示した1作業**。同一作業の続きだけが同じsession_id/task_idを共有する。
一つのログに別作業が混ざる実ログの自動分離は今回の保証対象ではない。
manifestの識別・順序情報は人が用意した評価用メタデータで、モデルに推測させない。
異なるsession/taskを同文だけでまとめず、同じtaskでも異なるsnapshotに同一sequenceが付いた場合は時系列不明として保留する。

上限は20シナリオ、40ファイル、1ファイル256KiB、合計2MiB、64候補。
1段落/コードblockは8192bytes、1作業は128記録・32768bytesまで。
超過は明示エラーで、無言の切捨てや自動的な追加通信はない。
相対path逸脱・symlink・特殊ファイル・hash不一致・非UTF-8を拒否。
ディレクトリdescriptorとNOFOLLOWで読み、名前の差替えによるsymlink追従を避ける。

段落を物理行範囲付きの記録へ分け、見出しを区切りとする。
コード囲み内の見出しは区切らず、引用とコードの文字列をルール基準の状態根拠に使わない。
未閉鎖コード囲みや見出ししかない入力は診断を残す。
source_idは相対pathと原本hash、record_idはsource_idと行範囲、candidate_idは明示session/taskから生成。
原文が変われば記録IDは変わる。同一入力では候補ID/候補集合/JSONが再現する。
同じ作業のコピーや再出力は候補として二重計上せず、全参照元を残す。
原本hashが同じファイルの再保存は古い状態の再発として扱わない。内容の異なる再発記録は別の時系列イベントとして扱う。
原文へのpath基準はrepoの `fixtures/worklog_candidates/`。行は1-based。

| enum | 意味 |
| --- | --- |
| needs_check | ログ上の要確認 |
| awaiting_approval | 当該操作の承認待ち |
| investigating | 継続調査 |
| resolved_in_log | 同じ作業の問題と修正後成功をログ上で結べる |
| hold | 文脈不足・矛盾・不完全入力などの判断保留 |

ルール基準は少数の明示表現だけを扱う比較対象。
現在のGitHubや実行環境を照会せず、現在の未解決・完了を断定しない。
担当者・期限・次操作を補わない。Markdownは固定文言と検査済み原文だけから生成し、リンク/HTML/制御文字を安全に表示する。

## 選択応答の責務

`src/worklog_candidates/response.schema.json` は応答の形を定義する。
コードは追加key・重複JSON key・NaN・不正型・enum・ID・state/reasonの組合せ・重複IDを厳密検証する。
候補ごとに独立したpacketを作り、その候補以外の記録IDを根拠にすることはできない。
選べる値は候補ID、固定状態・理由code、提示された記録IDだけ。自由文fieldとtoolはない。

Markdown囲み除去、未知enum補正、期待値の埋込みで成功扱いしない。
不正応答はinvalid_response、未出力の候補はmissing_responseとして保留し、消さない。
原文hash・行・IDの一致は構造上の検証であり、意味的な根拠の正しさは別途人が評価する。
同じ作業の失敗を別作業の成功で解決扱いしないことはfixtureで検証するが、任意の文章に対する完全な意味判定は保証しない。

`responses/complete.json` は全件を保留とする通信stub。
`partial.json` は1件だけ選択し、残りを欠落させる試験。`invalid.json` は囲み違反。
これらは実Gemmaの予測ではなく、精度測定には使わない。

## 評価と現在の結果

20シナリオ・25ファイル・21候補。開発10シナリオ/10候補と評価10シナリオ/11候補。
未解決3、承認待ち2、継続調査2、同一ログ内解決3、後日解決/再開2、重複3、別作業成功1、文脈不足/矛盾2、攻撃文2。
シナリオ16は異なる状態の2作業を含む。

`gold.json` は人が確認できるラベル、原文、相対path、行範囲、根拠IDを持つ。
分類が終わった後に `--evaluate` で採点する。packet/分類器へ正解は渡さない。
このPUBLIC fixtureは開発者が閲覧済みであり、封印した独立hidden評価ではない。

| 比較 | 状態一致 | 対応候補の見落とし | 対応済みの誤検出 |
| --- | --- | --- | --- |
| ルール・全体 | 18/21 | 2/12 | 1/5 |
| 開発 | 8/10 | 1/7 | 1/3 |
| 評価 | 10/11 | 1/5 | 0/2 |

対応候補は要確認/承認待ち/継続調査をまとめた指標。
全体precision=10/11、recall=10/12、保留6/21、候補重複0、余分な候補0。
3件の状態不一致は、未確認の言い換え、解決表現の言い換え、別作業との関係を慎重に保留した例。
根拠範囲coverageの欠落0だが、それだけで意味的根拠の正解を保証しない。
少数の合成例の結果で一般精度や有用性を主張しない。

過去のGemma実験は固定PUBLIC課題と登録済み2操作の選択で15/15＋別2入力が成功した範囲。
自由回答の囲み違反は不合格のままで、この機能の成功に置き換えない。
約66秒/呼出、入力/出力tokens、人の確認時間は後続の実Gemma評価で測る。今はモデル呼出0。
元32K復元などの過去記録や通信枠を新機能の承認に流用しない。

## 検証責務と停止点

```sh
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin python3 -I -B -m unittest discover -s tests -p 'test_worklog_candidates*.py' -v
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin ./scripts/verify.sh
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin /opt/homebrew/bin/bash scripts/security-preflight.sh .
```

新規unit/integrationは境界・証拠ID/物理行・時系列・重複・欠落・再実行・原本保持・CLI接続を担当。
既存の固定workflow、verify/lint/test入口、既存testは変更しない。
新規試験は標準verifyが自動発見するとは扱わず、明示実行を記録する。
Securityとstaged lintはindexを読むため、専用worktreeの追加pathをindexへ入れて検査する。
既存Issue #7のindexとは分離している。検証のためのstageはcommit/pushを意味しない。

ハーネスの追加理由は観測済みの形式違反と、根拠捏造・誤った状態結合の既知リスク。
手動manifest実行時だけ起動し、PUBLICの原文と模擬応答を読み、候補一覧だけを出す。
schema/ID/hash/path/line検査は決定的コードへ移し、意味判断とモデル精度を分ける。
既存監査はSkills/Toolsの6原因分類、既存評価器は候補実行の隔離を担当し、本機能とは重複しない。
運用負荷は手動実行と人の根拠確認。不要な意味推定や定期化を増やさず、モデルの価値が基準を上回らなければ接続を見送る。
安全境界を削除せず、既存保証も削除しない。

初期実装の検証とProduct Acceptanceは区別する。
実Gemma通信・サービス操作・実ログ利用・自動Issue化/修正・Cron・本番・Secrets・認証・Dockerは対象外。
実Gemmaと実データは、それぞれ宛先・分類・対象allowlist・上限・停止条件を具体化して別承認する。
CI/Security/Codex ReviewはPR提出後の同一headで確認し、人間がMergeを判断する。

ローカル検証（2026-10-18）: 新規24 testsと標準30 testsが成功。Securityの最終結果は同じindexの実行記録で照合する。typecheck/buildは既存入口非実行による理由付きskip、依存manifestなしで依存監査は対象外。GitHub CI/Security/Codex Review、実Gemma、人間の有用性検収は未実施。

PR #17の初回レビューでは、字下げ/空ATX見出しの認識とgoldの原文・行末・記録ID照合をBLOCKING P2として補強した。捏造text/IDと不一致line_endはGOLD_SOURCE_MISMATCHで停止し、物理coverageの成功へ混入させない。
