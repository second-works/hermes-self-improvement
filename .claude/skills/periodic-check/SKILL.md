---
name: periodic-check
description: 本repoの週1回の定期点検の手順と、その自動実行（launchd ＋ モデルを使わない scripts/periodic_check.py）の条件。作業指針ハーネスで前回からの変化と放置されたIssueを確認し、上限への近さ、mainのCI、正式レビューの設定、runs/の容量を人に報告する。定期点検、棚卸し、放置Issueの確認、点検の報告を読むときに使う。読み取りと報告だけで、GitHubへは書き込まない。
---

# 定期点検

点検の結果は報告だけで、Issueの更新・Close・削除は人の判断を待つ。手で実行してもよい。

## 自動実行（#59）

2026-10-30、利用者の判断で、この点検を利用者のMacで週1回、launchd から **モデルを使わない点検スクリプト** `scripts/periodic_check.py` で自動実行する。#31 の「Cron/定期運転」を対象外とした決定は改善サイクルの範囲のもので、これはその例外として記録する。ほかのスキルや操作は自動にしない。

- 場所: 点検専用の checkout `/Users/work/Developer/hsi-periodic-check`（このrepoの git worktree、detached HEAD）だけ。目印として、その checkout に空のファイル `runs/.periodic-check-checkout`（Git管理外）を置く。共有の元checkout（`/Users/work/Developer/hermes-self-improvement`）や、ほかのworktreeは使わない・変更しない。
- 更新: `--update` で `git fetch origin main` と `git checkout --detach origin/main` を行う。目印がない、ブランチ上にある、追跡ファイルの変更か未追跡のファイル（`runs/` を除く）がある、main に載っていないコミットがある、のどれかなら何も変えずに止まる。この checkout では編集・commit・push をしない。更新の後の取得は新しい main のハーネスで行うが、`periodic_check.py` 自身はその回は更新前の版で動く（翌週からそろう）。
- 中身: 下の1〜4をスクリプトが行う（取得、差分、親の検収待ち・完了範囲確認・14日以上動いていないOPEN、上限の8割の警告、mainのCI、`origin/main` の `.github/pr-gate-review`、`runs/` の容量）。
- 保存: 取得のrunは `runs/periodic-<YYYYMMDD-HHMM>`、報告は `runs/periodic-summaries/<YYYYMMDD-HHMM>.md`（どちらもGit管理外。既存の報告があれば止まる）。`--notify` でmacOSの通知を出す。
- してはいけないこと: GitHubへの書き込み（Issue・PR・コメント・ラベル）、runs/ の削除・移動、モデル（Claude・Codex・Gemma）の使用、`~/.hermes` や本番への接続。GitHubへの通信は、作業指針ハーネスの読取と `gh run list` だけ。
- 停止: 取得が INCOMPLETE、checkout が更新できない、時間切れ（collect 600秒、git fetch 300秒、gh 60秒）、コマンドが見つからない、のどれかなら、報告に「停止」として書いて終了コード1で終える。再試行はしない。上限の8割を超えたら警告として報告する。前回のrunは、ハーネスの `load_run` の検証を通る、いちばん新しい `periodic-<YYYYMMDD-HHMM>` を使う（通らないrunは飛ばす）。
- 報告を読んで判断が要るときは、人がこのスキルの「5. 報告する」の観点で確認するか、Claude Code に報告ファイルを読ませて相談する。

launchd の設定例（`~/Library/LaunchAgents/com.second-works.hsi-periodic-check.plist`、毎週月曜9:00。ログは `runs/` の外。設定は利用者のMacの判断で置く。gh の認証はログイン中のユーザーで使える前提で、ログアウト中は停止として報告される）:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.second-works.hsi-periodic-check</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/homebrew/bin/python3</string><string>-I</string><string>-B</string>
    <string>/Users/work/Developer/hsi-periodic-check/scripts/periodic_check.py</string>
    <string>--update</string><string>--notify</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/work/Developer/hsi-periodic-check</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/Users/work/Library/Logs/hsi-periodic-check.log</string>
  <key>StandardErrorPath</key><string>/Users/work/Library/Logs/hsi-periodic-check.log</string>
</dict>
</plist>
```

手で1回動かすときは、点検専用の checkout で `python3 -I -B scripts/periodic_check.py --update` を実行する。

## 1. 状態の変化を見る

自動実行では、スクリプトが `runs/` の中で保存を終えた、いちばん新しい `periodic-<YYYYMMDD-HHMM>` のrunを前回として使う。なければ `--previous` なしで取得する。

work-resume スキルの手順1で、前回の点検のrun（collect・report・recheck のrun。同じ checkout の `runs/` にあるもの）を `--previous` に渡して取得する。所要時間は `time python3 -I -B scripts/report_github_work_guide.py collect …` のように `time` を付けて測る。

報告すること:

- 前回から ADDED / CHANGED になったIssue / PR
- OPENのまま、最終更新から2週間以上動いていないIssue（report.md の「最終更新」を見る）
- 種別「親の検収待ち」のIssue（人の最終検収を待っている親）
- 種別「完了範囲確認」のIssue（関連PRがMerge済みでOPENのまま）。Closeするかは人が決める

## 2. ハーネスの健全性を見る

- collect の所要時間（`time` で測った値）とAPI呼出数（report.md 冒頭の「API呼出」）。上限（180秒、500呼出）の8割（144秒、400呼出）を超えたら報告する。2026-10-30の時点で57件、約76秒・144呼出。
- coverage が COMPLETE でなかった場合は、その原因。
- report.md 冒頭の「取得対象外」が、閉じたPRのcheck等を取得しない旨になっていること（#49）。

## 3. mainとレビューの設定を見る

- mainの最新commitで CI と CodeQL の結果を確認する（`gh run list --repo second-works/hermes-self-improvement --branch main --limit 5`）。失敗や、移行予告などの notice があれば報告する。workflow は変更しない。
- 照合が読むのは GitHub 上の main の `.github/pr-gate-review`。`git fetch origin` の後に `git show origin/main:.github/pr-gate-review` で確認し、利用者の現在の指示（2026-10-30時点は `claude-code`）と合っているかを報告する。

## 4. 保存物を見る

- `du -sh runs` で容量を確認する。runは自動で削除しない。合成原データは最低30日、監査記録は最低90日保持する方針（`docs/memory-verification.md`）。期限を過ぎた削除は、対象を限って人の承認を取る。
- 未追跡のファイルが増えていないかを `git status --short` で確認する。他者の未コミットの変更には触らない。

## 5. 報告する

次の形で報告する。

- 取得: run名、coverage、所要時間、API呼出数
- 変化: 追加・変更されたIssue / PR
- 要対応の候補: 放置されたIssue、親の検収待ち、Close待ちのIssue、上限に近い項目、CIの警告、設定の食い違い
- 人の判断が要るもの

## してはいけないこと

- 点検の結果を理由に、Issueを自動で更新・Closeする。
- runs/ のファイルを削除・移動する。
- launchd の設定を追加・変更する（追加と変更は利用者の判断。#59 の条件の外で自動実行しない）。
