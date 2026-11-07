# 週次点検から改善処理への接続（#87）

既存の `scripts/periodic_check.py` が点検の結果を保存した後、改善dispatcherを呼ぶ。
改善は初期無効とし、既存の送信承認を省略しない。点検・定型報告はPythonが担当し、OpenAIへの送信は承認された生成・意味的評価だけに限定する。
Risk Tier: HIGH（無人起動、送信承認、停止の境界）。親 #83、前提 #59 / #77 / #85 / #86 / #92。

## 起動と承認の境界

既存launchdジョブが使う `periodic_check.py --update --notify` の入口を維持する。
新しい常駐サービスや監視タイマーは追加しない。今回、実機の登録・設定変更・有効化は行わない。
専用checkoutの `runs/periodic-improvement/config.json` が存在しない場合、改善は `DISABLED` となり、選定・認証読取・モデル起動を行わない。
設定は本人所有の通常ファイル、mode 600、schemaは次の2項目だけとする。

```json
{"schema_version":1,"enabled":false}
```

`enabled: true` はdispatcherの受付条件であり、送信の承認ではない。
実機での設定作成・有効化と実通信は #88 の別承認後に行う。
実通信前にPlusの利用枠、追加クレジットOFF、追加費用0円を本人が確認する。API課金や別providerへのfallbackは行わない。

## 処理と記録

点検が完了・保存検証済みの場合だけ、既存の #84 選定で公開障害を最大1件受け付ける。
再現証跡は固定の `runs/periodic-improvement/reproductions/<event_id>.json` に監督者が用意する。
未処理のjobがある場合はその1件だけを扱い、同じ点検から別の障害を追加で選ばない。
未対応の障害や未登録profileを推測で対象へ広げない。

| 記録 | 内容・停止条件 |
| --- | --- |
| `checks/<snapshot_hash>.json` | 点検と受け付けた元eventを固定。再起動しても別eventを追加しない |
| `events/<event_id>/entry.json` | 元の保存点検とPUBLIC entry。処理前に公開PR・最新head・失敗check・再現根拠を再照合 |
| `mapping.json` | 本人所有mode 600の #86 mapping。なければ `AWAITING_MAPPING` |
| `prepare.json` | 登録profileの凍結済みcontext。生成へ渡すのは既存のPUBLIC packetだけ |
| `generation-plan.json` | #85の送信計画。本人所有mode 600の `generation-approval.json` がなければ `AWAITING_GENERATION_APPROVAL` |
| `generate.json` | 既存controllerが署名付きreceiptへ結合した生成結果。生成は元eventにつき最大1回 |
| `evaluate.json` | #86の隔離評価・監査。差分・候補・Memory参照を既存runへ保全 |
| `semantic-prepare.json` | Skill文変更の意味的評価が必要な場合だけ #92 の送信計画を固定 |
| `semantic-approval.json` | 別の本人承認。なければ `AWAITING_SEMANTIC_APPROVAL`。自動生成しない |
| `semantic.json` | baseline/candidate/劣化対照を各3回、生成分込み最大10回で評価した結果 |
| `finished.json` | 最終状態とcontext run・report hash。候補を採用せず、人間承認待ち/HOLD/拒否/停止で終える |

承認ファイルは #85 / #92 と同じ全項目と1時間以内の `expires_at` を照合する。
ファイルの作成だけを利用者の同意の証明とみなさない。利用者の具体的な送信承認に基づいて監督者が配置する。
各actionの直前に排他的な `*-started.json` をfsyncし、完了結果を保存する。
中断で開始記録だけ残った場合は `PERIODIC_RECOVERY_REQUIRED`。下位の予算が残っていても再送しない。
モデルの結果不明・認証拒否・枠切れ・承認不一致は停止し、失敗したactionを自動再実行しない。
同じ元eventは別点検でも再選定しない。dispatcher同士と既存の生成・評価はそれぞれ既存のlockで直列化する。

保存済み点検の承認待ちjobを進める入口は次のとおり。承認条件は週次入口と共通。

```sh
python3 -I -B scripts/periodic_improvement.py --run runs/periodic-YYYYMMDD-HHMM
```

## 停止・再開

```sh
python3 -I -B scripts/periodic_improvement.py --stop
python3 -I -B scripts/periodic_improvement.py --resume
```

停止は #77 / #85 / #92 と同じ通常入口の受付停止マーカーを耐久保存する。
実行中の生成・意味的評価はintent、固定image・コンテナ設定、検査済みIDを照合して停止する。
機械評価も既存の各case境界で停止を確認する。停止確認待ちは上限10秒であり、実行中caseの終了などが間に合わなければ `STOP_UNCONFIRMED` を返す。
後始末不明を成功にしない。pending、試行予算、評価・点検記録を保全し、人が後始末を確認するまで再開を拒否する。
`--resume` は受付を明示的に開く操作で、処理済みeventや開始済みactionを再送する操作ではない。

点検の収集・定型報告は改善の停止中も継続する。
改善を呼ぶ前に点検summaryをfsyncし、改善側が失敗しても点検の完了結果を維持する。
summaryの末尾に改善側の状態を追記し、点検の成功と改善処理の成功を区別する。

## 検証と残る検収

新規制御テストは `python3 -I -B -m unittest discover -s tests -p 'test_periodic_improvement.py' -v`。
無効・不完全点検・改変・本人承認不足・中断・並行起動・停止・明示再開・後始末不明・記録保全をPUBLIC合成入力と模擬輸送で検証する。
`tests/run_periodic_improvement_docker.py` は、保存点検・合成GitHub応答から既存評価までをつなぎ、9つの新規Hermes profileをnetwork-noneで動かす明示的な隔離テストである。
実認証・実推論・launchd実登録は使用しない。固定CI資産は変更せず、標準verifyと追加テストを別々に記録する。

これは初期無効の接続実装であり、未知の障害に対する包括的な送信承認を新設しない。
公開実障害1件の実通信、実launchdの通し検収、定期有効化は #88 に残る。
候補採用・復旧もそれぞれ別承認であり、この入口は実行しない。
問題時は受付停止・証跡保全のうえ、差分のrevertを人が判断する。
