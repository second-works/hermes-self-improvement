# 初回障害を確認する監視試運転（#103）

公開GitHubを1時間ごとに点検し、最初の障害を記録したら推論前で停止する。
利用者が2026-11-08に選んだ試運転範囲。これは実推論の包括承認でも、改善品質の検収完了でもない。
Risk Tier: HIGH（定期起動・初回停止・証跡保全）。#83 / #88、前提 #101 / PR #102。

## 何が動くか

- 対象はPUBLICの `second-works/hermes-self-improvement`。Pythonが既存の固定collectorで情報を取得する。
- 初回は登録後すぐ、その後は1時間間隔、同時1件。最大168回の新規点検、保存量512MiB到達時に停止し、自動削除しない。ログイン中のGUI agentを使う。スリープ・ログアウト中の実行は保証しない。
- 収集上限180秒・500論理読取・5000ノード・接続ごと10ページを維持する。collectorの完全取得と保存manifest/hashを検証する。
- OPEN PRの現在headにある必須check（ci / Security Preflight / Analyze (python)）の最新check-run、または同じheadの最新commit-statusの失敗を検出する。完了した失敗・期限超過・cancelled等を確認対象とする。旧headや成功に置き換わった失敗は使わない。
- 複数あればPR番号・必須check順で最初の観測を固定する。現在の状態や再現性を確定した結果ではない。実行前の再照合・再現根拠・profile照合・個別送信承認は後続で必要。
- 最初の障害、不完全取得、設定/保存不正、実行中断、上限のいずれかで停止する。後のtimer起動は保存状態を確認するだけで、新しいAPI取得はしない。
- モデル通信・Hermes認証読取・候補採用は0。改善dispatcherは呼ばない。GitHubへの書込、既存gatewayや別repoの点検変更も行わない。

## 初回の内容を確認する

専用checkoutの `runs/first-failure-pilot/first-report.md` が固定の確認票。
PR・head・check/status ID・結論、取得時刻、snapshot hashと原本の参照先、未確認事項、推論前に必要な確認を示す。
`terminal.json` とレポートのhash、保存点検のmanifest/hashを照合する。記録が変わった場合も再取得へ進まず停止する。
ローカル通知は固定レポートへの案内だけ。通知の受付は配達や検収の証明ではなく、通知が失敗してもレポートを保全する。状態はJSONでも確認できる。

```sh
python3 -I -B scripts/first_failure_pilot.py status
```

| 状態 | 意味 |
| --- | --- |
| MONITORING / CLEAR | 監視待ち / 完了した点検で対象なし |
| RUNNING / BUSY | 既存の点検が実行中。追加の点検は始めない |
| AWAITING_REVIEW | 初回障害の確認待ち。推論前で停止 |
| STOP_REQUESTED | 停止要求を保存。実行中なら終了確認が必要 |
| STOPPED | 不確実性や上限等で停止。cycles/と部分点検を保全 |
| NOT_CONFIGURED / DISABLED | 未設定 / 無効。取得しない |

一度停止したpilotを自動再開したり、configureで既存記録を上書きしたりしない。
次に進める時は初回記録・再現根拠・現在の障害を確認し、別の試運転/送信計画を判断する。

## マージ後の有効化

利用者はこの読取のみの有効化を依頼済み。実装・正式レビュー・人間Mergeの前には登録しない。
専用のクリーンなcheckoutを、確認したmainのSHAへ固定する。作業中の元repoは使わず、実行中のfetch/updateもしない。
これは利用者所有filesystemを前提とする運用上の整合性検査であり、同じOS利用者に対する権限分離ではない。

1. 専用checkoutのHEAD・追跡変更なし・runtimeファイルとGit blobの一致を確認する。
2. 同checkoutで `python3 -I -B scripts/first_failure_pilot.py configure --runtime-sha <確定した40桁SHA>` を実行。設定は本人所有600、状態dirは700となる。既存pilotは上書きしない。
3. `scripts/launchd/com.secondworks.hermes.first-failure-pilot.plist` の `@PYTHON@` / `@CHECKOUT@` を実パスへ置換し、plist構文・引数・間隔・出力先を検証する。既存の同ラベルがあれば上書き登録しない。
4. 利用者のLaunchAgentsへ保存し、`launchctl bootstrap gui/<uid> <具体的plist>` で専用ジョブだけを登録。初回点検の終了、CLEARまたは固定された停止理由、保存manifestを確認して#88へ記録する。
5. 状態がMONITORING/CLEARなら次回を待つ。実障害の有用性や推論の検収完了とは報告しない。

[AppleのLaunchAgentと間隔起動の説明](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)を参照。
このrepo専用のラベルは `com.secondworks.hermes.first-failure-pilot`。既存のai-development点検とHermes gatewayは別物。

## 停止する

```sh
python3 -I -B scripts/first_failure_pilot.py stop
```

停止要求は設定JSONの正常性に依存せず耐久保存し、実行中の固定collectorを確認済みの子process groupだけにTERM/KILLして待つ。
SIGTERM/INTも同じ停止条件にする。強制終了等で結果不明なら、未完了cycleを見つけた次回起動がRECOVERY_REQUIREDで停止し、再取得しない。
状態を安全に保存できない場合も取得しない。読取専用/満杯のfilesystemでは停止印の永続化ができないため、定期ジョブを解除してから復旧する。
取得workerは既存の180秒制限、親の監督は210秒を上限とする。後始末には別途TERM後0.25秒の猶予と、最終group KILL後5秒の待機がある。固定supervisorがgroup leaderを保持し、reporter終了後も残る子を停止する。TERMの猶予中もleaderを生存させ、groupへの最終signal後に回収するため、PID再利用後のgroupを操作しない。終了観測には回収しないwaitid/WNOWAITを使う（macOSではPython 3.13以上が必要。準備済み環境は3.14.5）。
定期ジョブ自体も止める場合は、同じ利用者の `launchctl bootout gui/<uid>/com.secondworks.hermes.first-failure-pilot` で専用ラベルだけを解除し、消失を確認する。
設定・ログ・点検・初回レポートを削除しない。

## 検証

`python3 -B -m unittest discover -s tests -p 'test_first_failure_pilot.py' -v`。
固定PUBLIC snapshotで最新性・初回記録・改変・再起動・並行・停止・中断・上限を確認し、固定collectのargvと子groupの停止を模擬検証する。
実機の有効化・初回取得結果はマージ後に#88へ記録し、合成試験の成功と区別する。コードのマージだけを有効化済みとしない。
