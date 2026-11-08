# GitHub点検の取得時間改善（#99）

closing参照を最大10 PRずつまとめ、取得範囲と安全上限を保ったままHTTP要求を減らした。
foreground実測は123.471秒から113.993秒へ短縮した。無人実行の180秒警告が解消したかは、別途LaunchAgentでの検証が必要。

## 計測結果

2026-11-08、main `fecf94a4cfb10591db1e31f71c8b1bffd9021839` と本変更を同じMacで順番に実行。対象はPUBLICの99項目（Issue 52、PR 47）、OPEN PRなし。モデル・Hermes本番・認証ファイル・サービスを操作していない。

| 対象 | 改善前 | 改善後 |
| --- | ---: | ---: |
| 完全性 | COMPLETE | COMPLETE |
| HTTP要求 | 248 | 206 |
| 論理読み取り | 248 | 248 |
| 全体 | 123.471秒 | 113.993秒 |
| closing参照 | 47要求 / 26.5811秒 | 5要求 / 2.8850秒 |
| コメント | 99要求 / 44.4305秒 | 99要求 / 41.2912秒 |
| Issue詳細 | 52要求 / 24.8998秒 | 52要求 / 23.2306秒 |
| PR詳細 | 47要求 / 24.5739秒 | 47要求 / 43.9619秒 |

直列HTTPと要求ごとのgh起動が積み重なる構造を確認した。closing部分は約23.7秒減ったが、PR詳細が約19.4秒増え、全体は約9.5秒（7.7%）の短縮だった。各1試行であり、ネットワーク、GitHub応答、gh起動、OS優先度の寄与は分離できない。以前のBackground実行の約181秒での失敗を、今回の計測だけで単一原因へ断定しない。

## 原文と判断の保存

改善前の全応答を固定し、旧方式と一括方式でreplayした。99項目すべてのitems/raw/hashと、snapshot_hashを除くplan全体が一致した。248の論理読み取りを維持し、物理HTTPは248→206となった。

実際の連続取得では47 PRの`detail.head.repo.size` / `detail.base.repo.size`が変化した。これらも原文として保存するため、生のハッシュとplanの証拠参照は異なる。`work_view`は全99項目で一致した。実取得を固定入力と偽って比較しない。

PUBLICの集計・原文ファイルのハッシュ・replay結果は[証跡JSON](evidence/github-collection-performance-issue99.json)に記録した。実際の応答や全ログはGitHubへ投稿しない。

## 制御と再計測

- 接続ごと10ページ、全5000ノード、500論理読み取り、180秒を維持する。`coverage.calls`は論理読み取り、追加した`coverage.http_requests`は物理要求数。一括要求のalias数を送信前に予約する。
- 固定repo、PR番号、alias対応、cursor、部分エラーを検証する。失敗はINCOMPLETEとなり、再送や旧方式への切替を行わない。最初と最後のinventory照合、コメント件数、OPEN PRの全gate取得も維持する。
- 既存の注入transportに一括機能がない場合だけ、送信前に従来の単独connection経路を選ぶ。実際のGhReadOnlyは常に一括機能を持つ。
- `python3 -I -B scripts/profile_github_collection.py --out runs/<未使用名>`でforeground再計測できる。既存の固定transportとCollectorを利用し、snapshotと時間集計を既存manifestへ保存する。上限・任意query・自動再試行の指定はない。計測中のIssue/PR変更はinventory不一致になり得る。

本変更は起動時間短縮の実装であり、#88の検収完了や運転有効化ではない。LaunchAgentの追加登録・実機試験は今回行っていない。以前の161秒はBackground実行、今回の114秒はforegroundであり、同じ条件として比較できない。モデル推論、追加課金、認証変更、無人運転有効化は別承認の境界を維持する。
