# Skill改善の台帳CLI（#107）

**Decision: 終了記録・経験・候補を、承認済みmanifestが指すローカルのappend-only JSONLへ、人の明示入力だけで追記する。壊れた台帳では全コマンドを止め、原本に触れない。**

親は [#105](https://github.com/second-works/hermes-self-improvement/issues/105)、本書は子 [#107](https://github.com/second-works/hermes-self-improvement/issues/107) の成果物。Risk Tier: HIGH（複数repo由来の情報、入力境界、耐久記録を扱うため）。
台帳の形式・状態・遷移は [#106の契約](skill-improvement-mvp.md) をそのまま使い、schemaは変更しない。集計は #108、実運用は #109 で扱う。

## 1. 保存先

| 条件 | 拒否コード |
| --- | --- |
| 台帳ディレクトリは絶対pathで、symlinkや `..` を含まず、macOSの別名（`/System/Volumes/Data/...`）でもない | `LEDGER_PATH_INVALID` |
| ディレクトリ名はmanifestの `ledger_location.label` と一致する | `LEDGER_LABEL_MISMATCH` |
| 実データ（`APPROVED_LOCAL_DIRECTORY`）は本repoを含むどのgit checkout（祖先に `.git` がある場所）の外にも置く | `LEDGER_INSIDE_REPOSITORY` |
| `~/.hermes` の下には置かない（大文字小文字を区別しないpathの比較だけで、中身もメタデータも読まない） | `LEDGER_IN_HERMES_HOME` |
| `PUBLIC_FIXTURE` の台帳にはPUBLICの記録だけを置く | `CLASSIFICATION_NOT_PUBLIC` |

ディレクトリは利用者が先に作る。CLIは中に `ledger.jsonl`（台帳、権限600）と `ledger.lock`（排他lock）だけを作る。

## 2. 使い方

共通の引数は `--manifest <承認済みmanifest> --ledger <台帳ディレクトリ>`。結果は標準出力へJSONで1行出す。拒否は標準エラーへ `{"error": コード, "detail": ...}` を出し、終了コード2で終わる。

```bash
python3 -I -B scripts/record_skill_experience.py --manifest M --ledger D end --repository demo-app --work-unit wu-1 --result NO_CANDIDATE
```

| コマンド | 入力 | 動作 |
| --- | --- | --- |
| `end` | repo、作業単位、結果（`CANDIDATE_FOUND / NO_CANDIDATE / UNDETERMINED`）、作業日（省略時はmanifestのtimezoneで今日） | 終了記録を1件追記する。候補ありは `--experience` で経験を1〜16件（種類・一行要約120字以内・根拠参照1〜8件、原因は省略時 `UNCLASSIFIED`）。判定未完了は `--reason` が必須 |
| `propose` | repo、作業単位、経験ID、対象Skill、原因（6分類） | 候補を1件追記する。共通化は `--shared-repositories` か `--shared-contract` と `--decided-by` |
| `set-state` | 候補ID、状態（`OPEN / HOLD / DECLINED / DUPLICATE`）、理由 | 遷移表で許される状態変更だけを追記する。`DEPLOYED / ROLLED_BACK` は扱わない |
| `verify` | なし | 台帳全体を読み直し、件数を出す。終了記録は経験が何件あっても1件と数える |

`schema_version / event_id / recorded_at / work_date / timezone / classification` はCLIが付ける。`classification` はmanifestのrepoの分類を既定とし、より厳しい分類にだけ変えられる。分類が分からないとき（`UNKNOWN`）は記録せず保留する。

## 3. 重複と再送

- IDは入力から決まる。終了記録はrepoと作業単位から、経験はさらに順番から、候補は対象Skillと経験IDの組から作る。
- 同じ入力の再送は何も追記せず `ALREADY_RECORDED` を返す。同じ作業単位へ違う内容を送ると `WORK_UNIT_ALREADY_ENDED` で拒否する。再送では作業日も同じ値を渡す。
- 同じ対象Skillについて、経験IDまたは根拠参照が既存の候補（`DUPLICATE` の候補を含む）と重なる候補は、新しい `OPEN` にせず、元候補への `DUPLICATE` として記録する。根拠参照はrepoごとに別物として比べる（`pr-review:7` は repo が違えば別の根拠）。経験IDには元候補と重なった経験を含め、候補の分類は最終的に含めた経験のうち最も厳しい分類にする。重なった相手が `DUPLICATE` の候補なら、その候補を元候補として連鎖させる（大元の候補とは経験が重ならない場合があるため）。
- 原因の初期状態は第4節の表に従う。`TEMPORARY` は `DECLINED`、`CONFLICT_OR_UNVERIFIED` は `HOLD`、それ以外は `OPEN`。

## 4. 根拠参照

根拠は `種類:値` の文字列だけを保存し、取得しない。

| 種類 | 必要なmanifestの読取項目 | 例 |
| --- | --- | --- |
| `input:` | `EXPLICIT_INPUT` | `input:利用者の訂正` |
| `end:` | `END_RECORD` | `end:wu-1` |
| `pr-review:` | `PR_REVIEW_COMMENT` | `pr-review:12` |
| `commit:` | `COMMIT_MESSAGE` | `commit:1a2b3c4` |
| `path:` | 許可rootの下の相対path（`.` `..` は不可） | `path:docs/guide.md` |
| `synthetic:` | `PUBLIC_FIXTURE` の台帳だけ | `synthetic:demo-app/pr-1` |

URLなどそれ以外の種類は `REF_KIND_NOT_ALLOWED` で拒否する。要約・理由・根拠に、よく知られたtoken形式（GitHub・GitLab・OpenAI/Anthropic系の `sk-`・AWS・Google・Slack・秘密鍵）や `password=` のような代入があれば `SECRET_LIKE_INPUT` で拒否する。検出は補助であり、秘密値を入れない運用が前提。`token: 期限切れ` のような説明文も拒否されるため、「tokenの期限切れ」のように `:` `=` を続けない書き方にする。

## 5. 書込と破損

- 台帳ディレクトリは `/` から1段ずつsymlinkを辿らずに開く。追記は排他lockの中で、読直し→検査→1回の書込→同期（macOSでは `F_FULLFSYNC`）の順に行う。lockを10秒待っても取れなければ `LOCK_TIMEOUT`。追記後に読込上限（32MB）を超える場合は `LEDGER_FULL` で拒否し、新しい承認済み台帳へ移る。
- 書込が失敗・途中で終わった場合は、元の長さへ戻して `WRITE_FAILED` を返す。戻せなかった場合は `WRITE_FAILED_RECOVERY_REQUIRED` を返し、人が確認する。成功とは返さない。
- 読込時に、通常ファイル以外（FIFOなど）、途中で切れた最終行、厳密でないJSON（重複キー・深すぎる入れ子など）、schema違反、manifestと異なるtimezone、`PUBLIC_FIXTURE` 台帳の非PUBLIC行、event_idの重複、経験と終了記録の不整合、遷移表にない候補の変化があれば `LEDGER_CORRUPT` で止まる。行を落としたり修復したりせず、その後の追記もしない。
- manifestでrepoの分類を後から厳しくすると、それより弱い分類の既存行があるため台帳全体が `LEDGER_CORRUPT` で止まる。分類を変えるときは新しい承認済み台帳（別のlabel）へ移る。
- `recorded_at` は後から追記する行ほど新しくする。時計が戻っていれば `CLOCK_REGRESSION` で拒否する（#106の合成例は時刻順ではないため、読込時には検査しない）。

## 6. 対象外

commit集計、終了フック、常時監視、自動候補生成、モデルへの送信、HTTP通信、他repoへの書込、配備・rollbackの記録（#106の契約の配備部分）、ジョブの停止・再開・削除。

## 7. 検証

```bash
python3 -I -B tests/test_skill_improvement_ledger.py -v
```

一時ディレクトリとPUBLICの合成manifestで、正常登録・候補なし・未完了・複数経験・重複・分類不明の保留・未知状態・登録外repo・path/symlinkの逸脱・同時追記・途中書込・破損を確認する。#106の合成台帳を読めることも確認する。
