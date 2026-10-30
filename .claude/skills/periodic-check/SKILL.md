---
name: periodic-check
description: 本repoの週1回の定期点検の手順。作業指針ハーネスで前回からの変化と放置されたIssueを確認し、ハーネスの上限への近さ、mainのCI、正式レビューの設定、runs/の容量を点検して人に報告する。定期点検、棚卸し、放置Issueの確認を頼まれたとき、利用者のMacの予定実行から呼ばれたときに使う。読み取りと報告だけで、GitHubへは書き込まない。
---

# 定期点検

点検の結果は報告だけで、Issueの更新・Close・削除は人の判断を待つ。手で実行してもよい。

## 自動実行してよい条件（#59）

2026-10-30、利用者の判断で、この点検だけを利用者のMacで週1回、Claude Code の予定実行として自動で行う。#31 の「Cron/定期運転」を対象外とした決定は改善サイクルの範囲のもので、これはその例外として記録する。ほかのスキルや操作は自動にしない。

- 場所: 点検専用の checkout `/Users/work/Developer/hsi-periodic-check`（このrepoの git worktree）だけ。共有の元checkout（`/Users/work/Developer/hermes-self-improvement`）や、ほかのworktreeは使わない・変更しない。
- 更新: 点検の始めに `git fetch origin` と `git checkout --detach origin/main` で main に合わせる。この checkout では編集・commit・push をしない。追跡ファイルに変更があれば点検を中止して報告する。
- してはいけないこと: GitHubへの書き込み（Issue・PR・コメント・ラベル）、runs/ の削除・移動、モデルへの判断の受け渡し（judgment-handoff）、Gemma の使用、`~/.hermes` や本番への接続、予定の追加・変更。
- 保存: 取得のrunは `runs/periodic-<YYYYMMDD-HHMM>`、報告は `runs/periodic-summaries/<YYYYMMDD-HHMM>.md`（どちらもGit管理外。既存の出力先は使わない）。報告の本文は予定実行の結果としても返す。
- 停止: 取得が INCOMPLETE、checkout が汚れている、main に合わせられない、上限の8割を超えた、のどれかなら、その事実を報告して終える（回避のために再試行を重ねない。再試行は1回まで）。

## 1. 状態の変化を見る

予定実行のときは、`runs/` の中で名前が `periodic-` で始まる、いちばん新しい collect のrun（`runs/periodic-summaries` を除く）を前回とする。なければ `--previous` なしで取得する。

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
- 予定実行を登録・変更する（登録と変更は利用者の判断。#59 の条件の外で自動実行しない）。
