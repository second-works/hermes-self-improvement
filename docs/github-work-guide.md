# GitHub作業指針の手動ハーネス

Issue #26のPUBLIC読取専用CLI。取得 → 版付き保存 → 前回差分 → 根拠付き手順 → 選択候補の再取得を行う。
Risk Tier: MEDIUM。公開情報の読取とローカル新規成果物だけを追加し、認証・権限・既存Gate・本番を変更しない。

## 使い方

既存の認証済み `gh` とPython 3を使う。tokenを読出し・表示・保存せず、認証の新設や権限追加もしない。
送信先は `github.com` の `second-works/hermes-self-improvement` だけ。公開repoであることを取得時に確認する。
外部送信する内容は固定の読取query、対象番号、ページ番号/cursorのみで、Issue本文の命令やURLを実行しない。
Cloud AIにはPUBLICコード・合成fixture・検証要約だけを扱わせる。追加ローカルLLM通信0。

隔離checkout内から、新しい `runs/<名前>` を毎回指定する。

```sh
python3 -I -B scripts/report_github_work_guide.py collect --out runs/first
python3 -I -B scripts/report_github_work_guide.py collect --previous runs/first --out runs/second
# ネットワークを使わない別プロセス読出し
python3 -I -B scripts/report_github_work_guide.py report --run runs/second --previous runs/first --out runs/report
# 選んだ候補だけを判定する。再取得は関係の追加/欠落を検知するため同じrepo全範囲を取得する
python3 -I -B scripts/report_github_work_guide.py recheck --run runs/second --target issue:2 --out runs/preflight
```

`issue:2` は指定方法の例で、特別な実装分岐はない。
人間の優先順を渡す場合は `collect` / `report` に `--priority issue:9 issue:8` のように指定する。
依存順が優先する。本文/コメント中の優先指示から引数を自動生成しない。
`--repo` はallowlistと一致しなければ通信前に拒否する。

JSONは `snapshot.json`、`diff.json`、`plan.json`、必要時の `recheck.json`。
日本語の `report.md` にcoverage、上限、差分、保留、原文引用とリンク、開始条件、次操作、成功判定、停止条件を出す。
`manifest.json` は最後に作り、保存済みファイルのhashを持つ。途中出力・改変済み・symlinkは読出しを拒否する。
既存出力先を再利用しない。中断したdirectoryは残し、再実行には別名を指定する。
macOSの `/tmp` / `/var` などsymlinkを含む絶対pathは実体path（`/private/tmp` など）を使う。
原本や以前のrunを上書きしない。runのraw API応答・実行ログはGitへ追加しない。

## 取得範囲と限界

1回につき全状態のIssue/PR一覧、各本文と現在状態、Issue/PR会話コメント、PR head、headのcheck runsとcommit statuses、正式レビュー、inline review comments、review threadの解決状態、GitHubのclosing issue関係を取得する。
GraphQLは固定の `query` 2種のconnectionだけで、mutationも任意query入力もない。
RESTは固定repo・固定routeのGETだけ。shellは使わず、`gh api` の固定引数を呼ぶ。
書込API・操作実行・通知・予定変更・モデル・本番・Dockerの入口はない。

- 1系列あたり最大10ページ、1ページ100件。
- 全系列合計5000 list node、500 API呼出、全体180秒（1呼出最大30秒）。
- API応答は1呼出10MB、保存JSONの読出しは1ファイル32MBまで。
- 再試行0。空の短い最終ページ/GraphQL pageInfoまで追い、check total_countも照合する。
- 認証不足、rate limit、欠落、不正schema、上限、時間切れ、途中失敗は `INCOMPLETE`。手順を生成しない。
- 一覧を最後に再取得し、件数・updated_at・stateの不一致を停止する。GitHub APIは複数要求の原子的snapshotを提供しない。収集直後/確認直後の変化を防止するロックではない。
- PR file diff、添付、外部URLの内容、本番採用、実検収、任意の関連Issueまでの横断探索は取得しない。

coverageは取得完了の判定であり、必須checkやレビュー成功の判定とは別。
`COMPLETE` でも0件のcheck/レビューは必要条件の未確認となる。
必須名はこのrepoの `ci` / `Security Preflight` / `Analyze (python)` に固定。
現head・最新attemptの成功と正式Codex reviewを確認し、skip・古いhead・未解決thread・変更要求は保留する。
botの👍/要約コメントだけのレビュー完了は自動認定しないため、人の確認が残る。
この判定はrepoの正式Merge Gateを代替しない。

## 手順と根拠

自由要約を入力する機能はない。ハーネスが次の6種から決め、原文と現在状態を付ける。

| 種別 | 条件 / 次に人が確認すること |
| --- | --- |
| 今回対応不要 | CLOSED/MERGED。再実装を開始しない |
| レビュー対応準備 | OPEN PR。現在head、check、レビュー、threadを確認 |
| 依存確認 | 明示の依存番号がある。依存先と開始条件を確認 |
| 対象範囲確認 | 依存不明、Goal不明、コメントにGoal/方針変更あり。保留理由を確認 |
| 完了範囲確認 | 保留なしOPEN Issueに、MERGED PRからGitHubのclosing関係がある。Doneと実装範囲を照合 |
| 計画整理 | その他の保留なしOPEN Issue。GoalとScopeを照合 |

依存欄は `# Dependencies` 内の `none` / `なし` / `依存なし`、または `- depends-on: #番号` の行だけを確定的に扱う。
自然文の依存、欄の欠落/重複、未取得依存、循環は保留する。複数のGoal、コメントのGoal/目標/方針変更も保留する。
この限定した文法は曖昧な意味判断を避けるための制限であり、既存Issueの本文を書き換える指示ではない。
依存がCLOSEDでも成功・採用を推定せず、開始条件の人間確認を保留理由に残す。
既存の自然文を安全に解釈する精度、人の確認時間、有用性は未検収。

各候補は対象、根拠ID・原文・source hash・リンク、開始条件、次操作、成功判定、停止条件を持つ。
保存planはsnapshotからの再生成と全体一致が必要。種別変更、未知ID、捏造引用、余分な完了主張、順序改変を拒否する。
hashはローカル破損/改変の検知でありGitHub署名や発行元の証明ではない。snapshotを信頼できない人から受け取って実行根拠にしない。
MERGEDからIssue Close、本番適用、検収済みを推定しない。本文中の完了主張も引用された未検証データであり、ハーネスの結論ではない。

## 差分と再確認

`FIRST` / `ADDED` / `UNCHANGED` / `CHANGED` / `UNAVAILABLE` を区別する。
取得できなくなった項目は削除・解決と呼ばない。変更フィールドにstate、body、headを含むdetail、comments、checks、statuses、reviews、threads等を表示する。

再確認は保存planを検証後、実際に再取得する。対象・依存・関係の追加/欠落も検知するため、計画範囲の全item hashを照合する。
関係のないコメント更新も `STALE` になる保守的な実装である。

| 結果 | 意味 |
| --- | --- |
| CONFIRMED | 読取dry-runで状態不変・保留なし。操作実行、承認取得、完了、Merge可否を意味しない |
| STALE | 計画時から状態/head/本文/依存/check/レビュー/取得対象等が変化。新snapshotから再計画 |
| BLOCKED | 取得不完全、対象欠落、または依存/Goal/必要check等が保留。原因を人が確認 |

CLIのexit 0は完全取得/保存、再確認時はさらにCONFIRMEDを表す。exit 2は不完全/拒否/STALE/BLOCKED。
成果物があってもcoverageとrecheckを別々に確認する。

## 検証責務

```sh
python3 -I -B -m unittest discover -s tests -p 'test_github_work_guide*.py' -v
./scripts/verify.sh
/opt/homebrew/bin/bash scripts/security-preflight.sh .
```

追加試験は標準ライブラリだけ。合成APIを使い、read allowlist、ページング、失敗/上限/時間、部分check、厳密JSON、状態/依存/根拠整合、旧head、保存中断・原本保持、別プロセス読出しを検証する。
先行試験の「本番自動適用完了」挿入と#9を#8より先にする依存飛ばしを拒否する回帰を含む。
`fixtures/github_work_guide/synthetic.json` はPUBLIC合成snapshot。実ログ/認証値は含まない。
既存のverify/CI/既存testを変更しない。固定CIの標準test入口は `tests/test_setup.py` のため、今回の追加試験はCIでは自動実行されない。提出時に明示実行した結果を記録する。

既存の `scripts/collect-github-state.py` は最小メタデータの観測、作業ログ候補CLIはofflineログ抽出、delegationは登録済み操作の隔離実行が責務。
今回はこれらを変更せず、差分と固定手順・直前dry-runの失敗モードだけを担当する。自動適用や常駐機能を追加しない。
判定: KEEP（Issue #26）。自然文解釈を拡張する場合は、意味精度と人の確認負荷を別途測定してから再評価する。

実読取の要約証拠はこの文書末尾に記録する。実データの変化を起こす書込は行わず、変化の試験と実際の観測を区別する。

## 2026-10-23の実読取証拠

隔離checkout `/private/tmp/hermes-issue-26` のGit管理外 `runs/issue26-live-*` へ保存した。
開発成果を提出する前の読取試験で、製品collectorによるGitHub書込は0。新規モデル通信も0。

| run | JST取得時刻 | coverage / 範囲 | snapshot hash |
| --- | --- | --- | --- |
| first | 13:25:05 | COMPLETE、Issue 15 + PR 11、121 calls、94系列、406 list nodes | `9c683d650da79ae884370514143ac5fc5b9ebb050cb28772fbcce584c40c5b83` |
| second | 13:26:28 | COMPLETE、同26件、121 calls、94系列 | `1e158d7907c33782dc37075fe84ba00e8eccdc6ab33cc54c6b5aa8041cceeccb` |
| recheck | 13:28:09 | COMPLETE、同26件、121 calls、94系列 | `ec6d64b02de22c129d891fde8a608b20acc972eede6b5e276772673dae771a64` |

別プロセスの `report --run runs/issue26-live-first --out runs/issue26-reloaded` もexit 0。
secondとの差分は26件すべてUNCHANGED。実変化を作るGitHub操作はしていない。
CLOSEDの `issue:2` の「今回対応不要」を実再取得で照合しCONFIRMED（exit 0）。
OPEN案件は自然文の依存などを保留し、開始や完了を承認していない。
状態変化/head更新/check/レビュー変化は合成試験で検証した結果であり、今回の実データで変化を観測したとの主張ではない。

| Requirement → Risk | Test → Result / Evidence |
| --- | --- |
| 読取境界 → 書込/対象外repo | transport引数・固定query・禁止route/公開判定の故障注入に成功。実collectorは上記3 runのみ |
| 完全取得 → 欠落をゼロ/成功へ変換 | 空一覧、複数ページ、途中失敗、部分check、rate/auth相当失敗、件数/呼出/ページ/時間上限でCOMPLETEとINCOMPLETEを区別 |
| 根拠付き手順 → 虚偽完了/依存飛ばし | 先行反例、誤種別/未知根拠/捏造引用、循環/不明/1100段依存、MERGEDからの飛躍を拒否/保留 |
| 直前確認 → 旧headの流用 | 状態/head/依存/check/レビュー/コメントの変化はSTALE、欠落/失敗はBLOCKED。上記実再確認では不変のみCONFIRMED |
| 保存 → 上書き/改変/中断 | 新規directoryのみ、manifest/hash、保存中断・同名再実行拒否、別プロセス読出しに成功 |

追加試験は33件成功。標準verifyはlintと既存30試験に成功し、typecheck/buildは既存設定なしの理由付き対象外。
Security Preflightはstage済み成果を検査してSECURITY_PASSED。依存manifestなしで依存監査はSECURITY_NOT_APPLICABLE。
PRのCI/Security/正式レビューは提出後の同一headで別途照合する。意味精度・人の確認時間・有用性検収は未確認であり、監視/制御全体の完成とはしない。
