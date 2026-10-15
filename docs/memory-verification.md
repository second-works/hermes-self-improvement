# Memory保存・検索の隔離検証

Decision: Built-in memoryは短い継続情報、state.dbは会話履歴、session_searchはその検索に使う。自己改善の評価・承認・復旧の正本はhash付き監査記録に置き、Memoryは検索用の補助にする。外部RAG・追加DBは導入しない。

対象は [Issue #3](https://github.com/second-works/hermes-self-improvement/issues/3)。Risk Tier: **HIGH**（保存・失敗時停止・隔離・監査出力の安全境界を検証するため）。本番、モデルAPI、候補実行、権限、既存workflow・検証入口は変更しない。復旧は隔離fixture内だけで試験し、実装差分を戻す場合も人間が判断する。

## 役割と固定ソース

公開upstream `NousResearch/hermes-agent` の `f97608f178d1ffeca59860195ab7da295f7c8e5f` を使う。[lock](../fixtures/memory/upstream-lock.json) に必要な49ファイルのGit blob SHA・SHA-256・byte数を固定した。本番のrevisionやv0.21.5との同一性は未確認。Context7の最新資料を固定版の動作証拠に流用しない。

| 対象 | 固定版で確認した責務 | 誤認しやすい点 |
| --- | --- | --- |
| Built-in memory / MemoryStore | 制限付きの編集・保存と、セッション読込時のプロンプト用snapshot | 書込み後も同じインスタンスのsnapshotは更新されない |
| `memories/MEMORY.md` | agentの短い継続情報。既定上限2,200文字 | 検索用DBでも完全な監査台帳でもない |
| `memories/USER.md` | ユーザー情報。既定上限1,375文字 | MEMORY.mdと別target。両方を検証する |
| `state.db` / SessionDB | セッションmetadata、messages、FTS index | Markdown memoryを自動的に検索するものではない |
| `session_search` | SessionDBに対する検索・セッション指定読出し | 現在のセッション、roleなどで結果が除外される。空結果と検索エラーを区別する |

原文: [保存・snapshot](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/tools/memory_tool_store.py#L88)、[ロックと再読込](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/tools/memory_tool_store.py#L245)、[SessionDB](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/hermes_state.py#L547)、[検索API](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/tools/session_search_tool.py#L619)。これらは上流の公開実装であり、ローカル本番の観測ではない。

## 再現手順と安全境界

このrepoのrootから実行する。POSIX・SQLite FTS5を使う。検証済みPython versionは証拠節を参照し、他versionの互換性は未検証。新しいPython packageのinstallは不要。取得と試験を分け、`run` はnetworkを使わない。取得先は固定公開GitHub raw URLだけで、redirect・proxy・認証情報の継承を使わない。

```bash
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin python3 -I -B scripts/memory_probe.py fetch
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin python3 -I -B tests/test_memory_probe_harness.py -v
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin python3 -I -B scripts/memory_probe.py run
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin ./scripts/verify.sh
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin /opt/homebrew/bin/bash scripts/security-preflight.sh .
```

`fetch` は `runs/memory-source-<固定SHA>/` にソースを保存する。既存ファイルの不一致は上書きせず停止する。`run` は新しい `runs/memory-<UTC>-<乱数>/` を作り、空のHOME / HERMES_HOME、環境変数のallowlist、CPU 40秒/プロセス、出力ファイル32MiB、timeout 60秒/プロセスを使う。seedプロセス終了後、別プロセスで競合書込みと再読込を実行する。ここでいう再起動はPythonプロセスの終了・再起動であり、OS再起動やHermesサービス再起動ではない。

workerのPython audit hookはnetwork、子process、許可外ファイルのopen・主要な変更操作、run外のSQLite接続を拒否する。拒否試験はダミーパスだけを使う。本番 `~/.hermes`、設定、認証、履歴、サービスは試験のためにも参照しない。この制御はレビューした公開ソースを動かす追加防御であり、悪意ある候補やnative codeに対するOS sandboxの保証ではない。候補実行を許可する根拠にしない。

保存本体、SessionDBのmixin群、session_searchは取得したmoduleを変更せず読み込む。`utils`・`tools.todo_tool`・agent配下の計9 module（workerの `slice_module` 呼出し参照）は、必要な関数・定数・classmethodのAST宣言と依存宣言だけを元の本体のままcompileする。圧縮モデル、認証、設定loader、providerの起動を避けるための試験用境界であり、通常importとの統合試験ではない。除外した圧縮連携が呼ばれれば失敗し、成功として代替しない。したがって圧縮済み会話・画像・外部Memory provider・実CLI全体の互換性は未検証。

標準検証と固定CI資産を保持している。新しい試験は上記の明示コマンドで実行し、現行CIには自動追加していない。既存の検証入口はSecurityの固定SHA照合対象のため、その更新とCIへの組込みは別途承認・検証が必要。

## 検証対象と原因の切り分け

| 試験 | 期待する観測・回復 |
| --- | --- |
| 固有識別子の保存・プロセス再起動 | MEMORY / USER / DBから再取得できる。別セッションIDで検索し、session指定でも読める |
| 同一セッションのsnapshot | 書込前の表示を維持する。新しいMemoryStoreで読込み直すと更新が見える |
| stale writer・2プロセスの競合 | 両appendを保持し、重複を増やさない。古いentryを根拠にしたreplaceは拒否する |
| 容量超過・存在しないreplace対象 | `success=false`、元ファイル不変。対象・容量を確認してから新しい操作を行う |
| 不正UTF-8 | loadは空として見えるが、mutationは拒否しbytesを保持する。試験内backupを戻すと再取得できる |
| 空の別profile・Memory欠如 | 空として読める。初回の有効な書込みで作成できる。別profileの情報とは混同しない |
| miss / 現在セッション除外 / role filter | 空のresultsになる。queryは出力にも含まれるため、文字列全体の有無だけでhitと判定しない |
| 不明session / 不正日付 / SQL故障注入 | エラーを返し、空検索の成功として処理しない |
| 欠如・破損DBのread-only open | 例外になり、空DBの新規作成や破損内容の上書きを成功扱いしない |
| 保持期間 | `prune_sessions(older_than_days=90)` を合成DBに明示実行。古い終了済みだけを除去し、古いactive・最近のendedを保持 |
| 偽Secretの保存・読出し | 保存・検索層では自動maskされないことを確認。監査には値を渡さず、既定文言・件数・hashだけを出す |
| Prompt Injection文字列 | strict threat patternに一致する書込みを拒否し、ファイルを保持 |
| harness拒否 | ソース欠如/改変/追加、symlink、パス逸脱、空/skip試験、監査改変/末尾欠落を成功扱いしない |

MemoryStore自体の永続ファイルには、この試験でTTLによる自動削除を確認していない。90日は上記の明示prune引数であり、実Hermesの設定・schedulerを確認した値ではない。DBの最終活動はheartbeatと最新message日時から求める。[prune原文](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/hermes_state_maintenance.py#L272)、[最終活動](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/hermes_state_common.py#L227)。

「Memoryから有効な情報を取得できなかった」の本番原因は **NOT_VERIFIED**。snapshotの更新時点、profile/target、未保存、容量、decode失敗、検索filterを切り分け候補として示せるが、この試験から本番原因を断定しない。自動マスキングも保証できないため、実Secret・実会話を取り込む用途は承認済みの保護・検査を別に設計するまで進めない。

## 監査保存と最小schema

2026-10-15にユーザーがこのチャットで承認した方針:

- 保存先はrepo内 `runs/<run_id>/`、Git管理外。合成の原データ（home/DBなど）は最低30日、検査済み監査記録は最低90日保持する。
- 期限後も自動削除しない。人間が対象run・分類・保存期間・保持すべき証拠を確認し、個別に承認してから削除する。削除機能は今回実装しない。
- 原データに実Secret・本番会話を使わない。Git管理と将来のGitHub提出は検査済みPUBLIC要約・再現手順だけとし、提出承認は別に得る。

`manifest.json` は固定source / lock / runner / workerのhash、Python・SQLite version、保持方針と未検証項目を記録する。`report.json` は件数・case名・状態・固定理由codeだけを許可し、workerのstdout/stderr・検索内容・例外messageは保存しない。予期しないstderrがあれば内容を出さず失敗にする。`events.jsonl` はrun_id、UTC、actor、状態、入出力hash、費用0、承認参照、終了理由code、前イベントhashを追記する。試験失敗・未完了runを再利用せず、新runでやり直す。既存原本を削除してからの再実行は不要。

```bash
python3 -I -B scripts/memory_probe.py verify-events memory-YYYYMMDDTHHMMSSZ-xxxxxxxx
```

上記は実際に出力されたrun IDに置き換える。連鎖、終端、report hashを検査する。全記録と連鎖を同時に書き換えられる主体にはhashだけで対抗できない。検査済みのreport hash・最終event hashを別のレビュー済み記録へ固定して照合する。今回の保存方針は、将来の候補workerに監査原本の編集・削除権限を与える承認ではない。

[最小schema](../schemas/improvement-log.schema.json) と [未検証の設計例](../fixtures/memory/improvement-log.example.json) は `iteration / baseline / candidate / metrics / approval / rollback` を明示する。候補未作成は `candidate=null`、未計測は `metrics.status=NOT_VERIFIED`、未申請は `NOT_REQUESTED` として成功を推定しない。自由文のprompt・会話・tokenを格納するfieldを設けない。Git commit SHAとartifact SHA-256を別に保存する。

`approval / rollback` は別の正本レコードのhash参照にとどめ、これだけで採用・復旧を許可しない。対象/root、期限、候補・評価hashを含む承認票の実装・照合はIssue #8で行う。schemaは設計成果物であり、本番の入力検証器として接続していない。構造だけでは値に紛れた秘密や機密を分類できないため、PUBLIC分類と出力allowlistの確認も必要。

## 今回の証拠

2026-10-15、Python **3.14.5** / SQLite **3.53.1** / macOS arm64で、保存・検索13項目とharness 7項目が成功した。FTS5経路と正常なread-only検索も確認した。標準検証は既存30テストとlintが成功。typecheck / buildは既存の未構成による理由付きskipで、全工程skipではない。Bash 5以上のローカルSecurity Preflightは `SECURITY_PASSED`、追加package manifestなしのため依存監査は `SECURITY_NOT_APPLICABLE`。

保存・検索の記録済みrunは `memory-20261015T055332Z-e5b5a211`。原本はGit管理外の同名runに保持する。

- report SHA-256: `17d72eebf848fea5248cd4452e824d2714a95c398ef1a61dcd5d3986a83d006e`
- 最終event SHA-256: `0805acf9f4e0ee935817e61c628e274d2acaef68ec6248fc8f4cb8c556c1faa6`
- 3イベントの連鎖・終端・report hashを `verify-events` で検査する。これは今回の検査済みcheckpointであり、原本のアクセス制御の代替ではない。

schemaと例のJSON構文・内部参照を確認した。JSON Schema validatorによる動的検証と実行系への接続は未実施。self-reviewでSQLite URIの隔離判定を修正し、read-only成功とDatabaseError / OperationalErrorを区別する試験を追加した。残る制約はAST sliceを使う限定統合、通常CLI・本番原因・OS再起動・自動prune・悪意あるnative codeの隔離・新試験のCI組込みである。

Risk Tierと作業境界のIssue追記は、初回はGitHub掲載本文の明示承認不足として自動承認レビューに拒否された。掲載予定文を提示した後、2026-10-15にユーザーがIssue追記・commit・push・PR作成を明示承認し、Issue #3へ記録した。Mergeと本番操作は承認範囲に含めない。CI / remote Security / Codex Reviewは、同じPR headの証拠をPRへ別途記録する。未確認を成功扱いせず、本番のProduct Acceptanceとも分けて扱う。
