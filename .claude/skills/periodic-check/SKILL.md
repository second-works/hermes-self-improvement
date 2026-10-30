---
name: periodic-check
description: 週1回程度、手で実行する定期点検の手順。作業指針ハーネスで前回からの変化と放置されたIssueを確認し、ハーネスの上限への近さ、mainのCI、正式レビューの設定、runs/の容量を点検して人に報告する。定期点検、棚卸し、放置Issueの確認を頼まれたときに使う。自動実行（cronなど）にはしない。
---

# 定期点検（手で実行）

cronや常駐での自動実行はしない（#31 の対象外）。点検の結果は報告だけで、Issueの更新・Close・削除は人の判断を待つ。

## 1. 状態の変化を見る

work-resume スキルの手順1で、前回の点検のrunを `--previous` に渡して取得する。

報告すること:

- 前回から ADDED / CHANGED になったIssue / PR
- OPENのまま、最終更新から2週間以上動いていないIssue（report.md の「最終更新」を見る）
- 種別「親の検収待ち」のIssue（人の最終検収を待っている親）
- 種別「完了範囲確認」のIssue（関連PRがMerge済みでOPENのまま）。Closeするかは人が決める

## 2. ハーネスの健全性を見る

- collect の所要時間とAPI呼出数。上限（180秒、500呼出）の8割（144秒、400呼出）を超えたら報告する。2026-10-30の時点で57件、約76秒・144呼出。
- coverage が COMPLETE でなかった場合は、その原因。
- report.md 冒頭の「取得対象外」が、閉じたPRのcheck等を取得しない旨になっていること（#49）。

## 3. mainとレビューの設定を見る

- mainの最新commitで CI と CodeQL の結果を確認する（`gh run list --repo second-works/hermes-self-improvement --branch main --limit 5`）。失敗や、移行予告などの notice があれば報告する。workflow は変更しない。
- `.github/pr-gate-review` の内容を確認し、利用者の現在の指示（2026-10-30時点は `claude-code`）と合っているかを報告する。

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
- 点検をcronやスケジュールに登録する。
