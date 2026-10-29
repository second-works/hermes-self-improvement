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
現head・送信元ごとの最新attemptと同名commit status両方の成功、正式Codex reviewを確認し、skip・古いhead・未解決thread・変更要求は保留する。
botの👍/要約コメントだけのレビュー完了は自動認定しないため、人の確認が残る。
この判定はrepoの正式Merge Gateを代替しない。

## 手順と根拠

自由要約を入力する機能はない。ハーネスが次の7種から決め、原文の抜粋と現在状態を付ける（#28で案件ごとの確認手順、#50で親の検収待ちを追加）。

| 種別 | 条件 / 次に人が確認すること |
| --- | --- |
| 今回対応不要 | CLOSED/MERGED。再実装を開始しない |
| 親の検収待ち | 子一覧の番号付き項目がすべてチェック済みで参照先がすべてCLOSED、別repo・PR・自分自身・未取得を指す行がなく、未チェックは参照を1つも含まない項目（人の検収・照合）だけ。各子の完了根拠と `docs/parent-issue-completion.md` の5項目を照合し、親のCloseを人が判断する |
| レビュー対応準備 | OPEN PR。現在head、check、レビュー、threadを確認 |
| 依存確認 | 依存が番号だけで書かれている。依存先と開始条件を確認 |
| 完了範囲確認 | OPEN Issueに、MERGED PRからのclosing関係、またはPR本文のRefs等による参照がある。Doneと実装範囲を照合 |
| 対象範囲確認 | 上記以外で保留がある。保留ごとの問いと解除条件を確認 |
| 計画整理 | その他の保留なしOPEN Issue。GoalとScopeを照合 |

### 読み取る形式

見出し（`#`〜`######`、コードブロック内は除く）を次の名前で認識する。前方一致は直後が空白・`/`・括弧・コロンの場合だけ。

| 欄 | 認識する見出し |
| --- | --- |
| goal | Goal / 目的 / 目標 |
| scope | Scope（Scope / Boundaries を含む） / 作業 / 範囲 / 対象範囲 |
| done | Done / 完了条件 / Acceptance criteria / 受入条件 |
| verification | Verification / 検証 |
| dependencies | Dependencies / 依存 |
| non_goals | Non-goals / 対象外 |
| boundaries | Boundaries / 境界 |

本文中の `依存: …` / `Dependencies: …` / `Depends on: …` の行も依存の記載として読む。
依存が `none` / `なし` / `依存なし`、または番号だけ（`- depends-on: #8`、`依存: #3, #5` など）のときだけ確定する。確定した番号はIssueとして解決するため、`PR #25` のようにPRと書かれた依存は確定せず、自然文の保留にする。
名前や文章を含む依存は確定せず、項目ごとに引用する。題名と語が一部一致するIssueを「候補（未確定）」として最大3件示すが、依存の順序には使わない。
条件付きの番号は、確定依存とは別の `dependency_hints` に確認先として保持する。
対象は現行の依存欄にある、文頭または句点・セミコロン・空白付きピリオドの直後の `Depends on:` / `依存:` と、その直後の番号列だけ。
`Parent: #31。Depends on: #35（#32→#33→#34→#35の人間Mergeと独立評価の証拠）。` では、確認先は#35だけとなり、条件は原文で引用する。
番号付きの条件混在は「番号なし」とせず、機械確定できない形式と説明する。
Parent、括弧内の参考番号、任意・再利用経路、コード例、コメント、履歴、対象外URLから確認先を推測しない。
直後に `PR #N` とあれば種別を保持し、取得されていない番号はUNFETCHEDのまま示す。

確認先の状態、Doneのチェック数、取得済みPRの明示RefsまたはGitHubのclosing関係、full headと出典を手順に示す。
RefsはPR本文の行頭（箇条書き可）の宣言とその番号列に限定し、コード例・コメント・単なる言及から結び付けない。
CLOSED/MERGEDや本文チェックを成功・採用の認定に使わず、実装範囲と評価根拠を人が照合する。
この案内は依存グラフ、優先順、保留の解除、取得範囲には影響しない。未対応文法や矛盾は保留を維持する。

一致の基準は、項目の語（英単語と、それ以外の文字の2文字組）のうち題名にも含まれる割合が0.3以上であること。候補は手がかりであり、正しさは測っていない。

### 保留の出し方

保留は理由の種類を分ける。`format`は欄がない・空・番号付き条件混在の未対応形式など形式の問題、`semantic`は複数の目的・自然文の依存・コメントでの方針変更・closingでない関係など意味の確定が必要なもの、`state`は依存先の状態、`gate`はPRの必須checkとレビュー。
各保留は、原文の該当箇所（evidence）、確認対象、確認する問い、解除条件を持つ。解除条件は「人が確認」で終わらせず、何を決めれば保留が外れるかを書く。

### 関連の扱い

同じrepoの `#N`、`owner/repo#N`、Issue/PRのURLを読み、両方向（本文が言及／相手が言及）で「関連候補」として出す。
`Refs` / `Related` / `Part of` / `Closes` / `関連` の直後にある参照は、参照の関係として区別する。GitHubのclosing関係（`closingIssuesReferences`）は別に表示する。
関連候補は依存の確定でも完了の証拠でもない。Refsだけの関係は `relation_not_closing` の保留になり、Issueのどの完了条件を満たしたかを人が確定する。
対象外repoのURLは「取得しない」と表示するだけで、内容を取得しない。
関連PRのMergeがIssueの最終更新より後なら、本文の状態の記述はMerge前の時点として読むよう注意を出す。

### 計画の検証

各候補は対象、原文の抜粋（1件300文字まで。切った場合は「抜粋」）、source hash、リンク、確認手順、保留、開始条件、成功判定、停止条件を持つ。
抜粋は原文の完全な部分文字列で、識別子は行番号（`issue:7:L34-L39`、コメントは `issue:4:c1:L3:53`）。
保存planはsnapshotからの再生成と全体一致が必要。種別変更、未知ID、捏造引用、余分な完了主張、順序改変を拒否する。
planの形式はversion 5。version 4に、親の検収待ち（`acceptance`）の種別を追加した（#50）。version 4はversion 3の履歴区別・子一覧に、未確定の依存確認先 `dependency_hints` を追加したもの。旧versionのplanを持つrunは再確認で拒否されるため、新しくcollectし直す。snapshotの形式（version 1）は変わらない。
hashはローカル破損/改変の検知でありGitHub署名や発行元の証明ではない。snapshotを信頼できない人から受け取って実行根拠にしない。
MERGEDからIssue Close、本番適用、検収済みを推定しない。本文中の完了主張も引用された未検証データであり、ハーネスの結論ではない。
確認手順は固定の文型と、番号・head・日時・件数・根拠IDだけで作る。原文の文章は引用（JSON文字列として無害化）でだけ表示する。Issue番号ごとの判断文はコードにない。

## 差分と再確認

`FIRST` / `ADDED` / `UNCHANGED` / `CHANGED` / `UNAVAILABLE` を区別する。
取得できなくなった項目は削除・解決と呼ばない。変更フィールドにstate、body、headを含むdetail、comments、checks、statuses、reviews、threads等を表示する。

差分と再確認は、原本hashとは別の作業fingerprintで比べる。fingerprintは原本から、PRの `head.repo` / `base.repo` のrepo全体のメタデータ（`open_issues_count`、`pushed_at`、`updated_at` など）を `full_name` だけに縮めたもののhash。
これらだけが変わったitemは `UNCHANGED`（`metadata_only: true`）で、reportに件数を出す。state、title、本文、head SHA/ref、コメント、check、status、レビュー、thread、closing関係の変化は引き続き `CHANGED` / `STALE` になる。
原本と原本hashはそのまま保存し、読出し時に検証する。

再確認は保存planを検証後、実際に再取得する。対象・依存・関係の追加/欠落も検知するため、計画範囲の全itemのfingerprintを照合する。
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
`fixtures/github_work_guide/real_20261023.json` は、2026-10-23に公開REST GETで取得した本repoのIssue 15件・PR 12件の原文（PUBLIC）。案内に使わないCLOSED/MERGEDのコメント・check・レビュー・threadは省き、closing関係はPR本文の `Closes #N` 行から再現した。
`tests/test_github_work_guide_real.py` は、このfixtureで #7 / #8 / #9 / #18 の期待する案内、OPEN Issueの手順がすべて異なること、reportが本文合計より短いこと、メタデータだけの変化の扱い、番号を100ずらした複製で同じ構造になることを確かめる。意味の正確さの測定ではない。
既存のverify/CI/既存testを変更しない。固定CIの標準test入口は `tests/test_setup.py` のため、`test_github_work_guide*.py` はCIでは自動実行されない（#28の追加試験も同じ）。提出時に明示実行した結果を記録する。

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

追加試験は35件成功。標準verifyはlintと既存30試験に成功し、typecheck/buildは既存設定なしの理由付き対象外。
Security Preflightはstage済み成果を検査してSECURITY_PASSED。依存manifestなしで依存監査はSECURITY_NOT_APPLICABLE。
PRのCI/Security/正式レビューは提出後の同一headで別途照合する。意味精度・人の確認時間・有用性検収は未確認であり、監視/制御全体の完成とはしない。

## #28: 実Issueでの案内の改善（2026-10-23）

#26の追加検収で、OPEN Issueがすべて同じ一般文の保留になると分かったため、`fixtures/github_work_guide/real_20261023.json` で期待結果を先に固定し、修正前のコードで不足を再現してから直した。

| 観点 | 修正前 | 修正後 |
| --- | --- | --- |
| OPEN Issue 10件の次操作 | 1種類（「対象範囲と保留理由を人が確認する。」） | 確認手順が10件すべて異なる。完了範囲確認5件、対象範囲確認5件 |
| #7 | 対象範囲確認、関連根拠なし | 完了範囲確認。PR #25（MERGED、head `3dd1227…`、Refs、closingではない）と、Done 6/6チェックの照合を案内。目的2箇所・依存2箇所を引用。Merge後にIssue本文が更新されていないことを注意として出す |
| #8 | 「依存欄がない」「Goalを一意に確認できない」 | 目的・作業・完了条件を認識。検証欄がないこと、依存3項目が番号未確定であることを、未確定の候補とともに示す |
| #9 | 同上 | 依存6項目を引用。「GitHub承認フロー」の候補に#8が出るが、未確定のままで依存順序には使わない |
| #18 | 同上 | 目的欄・依存欄がないこと（format）、Acceptance criteria 0/5、#4との境界の引用、対象外repo 3件は取得しないことを示す |
| report | 84,276文字（本文合計55,050文字より長い） | 35,150文字。本文全文ではなく抜粋とリンク。各案件に完了条件のチェック数（例: #18は0/5）を表示 |
| repoメタデータだけの変化 | 過去PR 12件がCHANGED / 再確認はSTALE | UNCHANGED（metadata_only）。state・head・本文の変化はCHANGED / STALE |

検証: `test_github_work_guide_real.py` の当初10件は修正前のコードで8件が失敗し、修正後は既存35件と合わせて45件が成功した。PR #29の自己レビューで、reportに完了条件のチェック数を出す試験1件を追加した。Codexレビューの指摘2件（`PR #N` の依存を存在しないIssueとして扱う、コードブロック内のチェック例を完了条件に数える）を直し、修正前に失敗する試験2件を追加した。続く再レビューの指摘（Done配下の小見出しのチェック項目が数えられない）と、同じ種類の目的欄の問題（直下が小見出しだけだと空と判定する）を直し、試験2件を追加した。3回目の指摘（4個のバッククォートの中の3個のバッククォートでコードブロックが終わったと誤認する）を直し、同じ種類のコメント中の「Goal/方針」検出もコードブロックを除外するようにして、試験2件を追加し、計52件が成功した。コードブロックは、開始と同じ文字で、開始以上の長さの行（後ろは空白だけ）で閉じる。完了条件のチェック数と目的欄の空判定は、配下の小見出しまでを範囲とし（認識する欄の見出しが来たらそこで終える）、コードブロック内の行を数えない。
番号を100ずらした複製でも、同じ種別・保留・関係・手順数になる（番号ごとの規則がない）。
意味の正確さ（名称一致の候補が正しいか、保留の判断が妥当か）と人の確認時間は測っていない。実際の作業再開に役立つかは、利用者の確認が必要。


## 現行契約と履歴、親子欄の読取（2026-10-28）

最新のPUBLIC Issueを使った再検証で、履歴を目的の重複として数える問題と、補足付きの「依存なし」を保留する問題を修正した。
親の子一覧は、自身の開始依存へ変換せず、行ごとの参照先、取得時の状態、本文チェック、原文を示す。
子一覧にある主経路と任意Gemma経路の採否や開始順は推測せず、各子の依存と人の優先指示を確認する。
番号付きの子がすべてチェック済み・CLOSEDで、取得範囲外（別repo・PR・自分自身・未取得）を指す行がなく、未チェックが参照を含まない項目だけの親は「親の検収待ち」とし（#50）、それ以外は「次に進める子を人が選ぶ」保留（`parent_plan`）を維持する。どちらもチェックやCLOSEDを成功・検収の証明にしない。

履歴の除外は、現行Goalの後にある区切り線 `---` に続く `履歴` または `YYYY-MM-DDの履歴` 見出しから末尾までに限定する。
後ろにその見出しより上位の見出しがあれば曖昧なので除外しない。
コードブロック内の記法も履歴境界には使わない。
除外した見出しの引用を注意として出し、履歴を含む原本とfingerprintは保持する。
明示境界のない複数Goalは従来どおり保留する。

`なし（#26 / PR #27はマージ済み）` のような補足は、括弧内が番号の列と固定の完了状態語だけの場合に受理する。
許可する状態語は `マージ済み`、`Merge済み`、`MERGED`、`CLOSED`。
この補足は依存なしという宣言の注記であり、参照先の完了や採用を確認した意味にはしない。
「ただし#8が必要」、未知の文章、括弧外の追加条件は引き続き保留する。

`Children / Dependencies`、`Children`、`子Issue`、`子一覧` は子一覧として認識する。
チェック行の同repo参照を示すが、列挙順を開始順とせず、チェック済みを成功とみなさない。
子欄があっても、独立したDependencies欄の解釈と確認は省略しない。
親計画を直接実装する案内は出さず、子の未完了項目と各子の依存を確認する案内を出す。

GitHubのclosing関係があるOPEN PRは、現headのcheck、レビュー、検収を確認する先として示す。
同じIssueの新規実装を重複して始める案内を避ける。
Refsだけの関連候補からこの関係を推測しない。
既存PRのcheckや正式レビューが未確認の場合は保留する既存Gateを変更しない。

`current_contracts_20261028.json` は、製品collectorがCOMPLETE取得したsnapshotから#8、#9、#28、#31の公開本文だけを固定したfixtureである。
raw API応答や生ログはGitへ追加しない。
追加12試験は、現行と履歴、親子、矛盾する補足、コードブロック、元snapshotの変更検知、コメントとの行番号衝突、OPEN closing PR、番号を100ずらした同一構造を確認する。
修正前には履歴、補足付き「なし」、子欄の4ケースの失敗を確認し、修正後は既存52件を含む64件が成功した。
標準CI入口は変更せず、追加試験はローカルで明示実行する。

Risk Tier: MEDIUM。PUBLIC本文からローカルで作る案内の形式認識だけを改善し、GitHub書込、モデル、権限、check判定、取得上限は追加、変更しない。
Harness判定はSTRENGTHEN。元文書を変更せず、誤保留と重複実装の案内を減らし、依存の推測確定と未確認の成功扱いを引き続き拒否する。


レビュー追加修正: 履歴見出しの直前の区切り線も履歴境界に含め、最後の現行欄の値へ残さない。
`none`、`なし`、補足付き「なし」の3ケースで修正前の失敗を確認した。
修正後は依存の値とsubtreeの両方から区切り線が除外され、同一snapshotの再確認がCONFIRMEDとなる。
P2はBLOCKINGに分類した。今回の履歴判定が正しい「依存なし」を誤保留し、作業再開の受入条件を満たせないためである。
Risk TierはMEDIUMを維持し、取得、権限、承認、必須checkの規則は変更しない。

## Issue #42: 条件付き依存の確認案内

Risk Tier: MEDIUM。PUBLIC原文から作るローカル案内を追加し、開始許可やGateは変えない。
PUBLIC fixtureの#8/#9と#35/PR #40を使い、修正前の4件の失敗を再現した。
修正後は、#35のDone 5/5とPR #40のRefs/full headを照合先に示し、#9では#8を確認先に示す。
合成の番号変更・未取得・PR種別・コード例・履歴・矛盾・closing出典・旧plan拒否・STALE/BLOCKEDを含め、関連83件がローカルで成功した。
fixtureは決定的な試験用にPUBLIC本文/状態/headを抜粋したものであり、実取得や実評価の代わりにはしない。
実データのcollect/report/recheckによる再検収と、同じPR headのCI/Security/正式レビューは別の証拠として記録する。

PR #43の正式レビューで、Refs番号列の後続番号が案内から漏れる点と、未取得の明示PR種別が失われる点をBLOCKING P2に分類した。
修正前に失敗する再現を追加し、番号列を区切りごとに読み、未取得でも明示されたissue/prの種別を保持する。
確定依存とBLOCKED判定は維持する。

再レビューで、括弧内の句点後にある依存ラベルを追加確認先へ誤変換するP2をBLOCKINGとした。全角・半角括弧の入れ子と複数行を追跡し、条件内の番号は引用に留める。未閉鎖条件は残りを確認先抽出から除外し、保留は解除しない。コード内の括弧は条件範囲へ影響させない。

複数行にまたがるインラインコード例の誤抽出もBLOCKING P2として再現・修正した。原文ごとに同じ長さのバッククォートの開閉を追跡し、依存確認先とPR Refsで同じコード範囲を使う。異なる長さのバッククォートでは閉じず、コード範囲の終了後は通常の宣言を読む。

HTMLコメント内の隠された宣言と、エスケープされたバッククォートによる後続宣言の欠落もBLOCKING P2として再現・修正した。コードとHTMLコメントを原文単位で一緒に追跡し、互いの内容で状態を変えない。エスケープはコード外の開始記号だけに適用し、コード内のバックスラッシュは文字として扱う。4空白/タブで始まるコード例も確認先とRefsから除外する。

コメント/複数行コード内の囲みコード記号が後続宣言を隠す指摘もBLOCKING P2として再現した。囲みコードの開始/終了も同じ原文走査へ統合し、コード・コメントの中では囲みコードを開始しない。従来の同一文字・開始以上の長さ・末尾空白だけという終了条件は維持する。

コメント/複数行コード内の見出しが依存欄を途中で切るP2もBLOCKINGとして再現・修正した。見出し認識に同じ除外範囲を適用し、隠されたScope/Goal/Doneを欄の境界や目的の重複として扱わない。
