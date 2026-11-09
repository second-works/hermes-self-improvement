# Skill改善の週次集計（#108）

**Decision: 記録率は「セッション」ではなく「作業日」（repoとmanifestのtimezoneの日付の組）で数える。分母は許可branchのcommit日と作業日登録の和集合、分子はそのうち終了記録がある日。自動化の条件は検討開始の目安として示すだけで、承認や自動実行にはつながらない。**

親は [#105](https://github.com/second-works/hermes-self-improvement/issues/105)、本書は子 [#108](https://github.com/second-works/hermes-self-improvement/issues/108) の成果物。Risk Tier: HIGH（複数repoのローカル履歴を読み、自動化判断の材料を出すため）。
台帳は [#107のCLI](skill-improvement-ledger.md) で書く。実運用は #109、自動化の設計は #110 で扱う。

## 1. 契約の拡張（利用者が選択肢Aとして承認）

#106の契約だけでは、commitのない作業日・作業時間・読むcheckoutとbranchを表せなかった。#108のIssueで3案を示し、利用者が「#108のPRで契約を拡張する」（A）を選んだ。

| 追加 | 場所 | 内容 |
| --- | --- | --- |
| `work_day` | 台帳の行 | commitのない作業日。作業単位ごとに1件。分母にだけ入る |
| `effort` | 台帳の行 | 人が使った分。作業の種類と記録済みの対象IDに結び付ける |
| `local_checkout` / `allowed_branches` | manifestのrepo | commitを読むcheckoutの絶対pathと、読むローカルbranch。組で書く |

既存の台帳とmanifestはそのまま有効。`local_checkout` のないrepoは、作業日登録だけで分母を作る。

## 2. 使い方

```bash
python3 -I -B scripts/report_skill_improvement.py --manifest M --ledger D [--start YYYY-MM-DD] [--end YYYY-MM-DD]
```

期間を省くとmanifestの期間全体。期間はmanifestの期間の中だけ指定できる（外なら `OUTSIDE_PERIOD`、形式・前後が不正なら `PERIOD_INVALID`）。結果は標準出力へJSONで1行出す。拒否は標準エラーへ `{"error", "detail"}` を出し、終了コード2で終わる。台帳の行は書かず、台帳ディレクトリへ集計のcache（`report-cache.json`）だけを書く。`PUBLIC_FIXTURE` の台帳はrepo内に置けるため、commitを読むrepoがPUBLICでなければ `CLASSIFICATION_NOT_PUBLIC` で拒否する。

## 3. 作業日の数え方

| 判断 | 採用 | 理由 |
| --- | --- | --- |
| commitの日付 | committer日時をmanifestのtimezoneで日付にする | rebase・cherry-pickを適用した日を作業日とみなす。UTCでは前日のcommitも現地の日付で数える |
| merge commit | 数えない（`--no-merges`） | 統合操作は作業そのものではない |
| bot | 作者名かメールに `[bot]` を含むcommitは数えない | 人の作業日だけを分母にする |
| 複数branch | 許可branchから辿れるcommitを1回だけ数える | 同じcommitが複数branchにあっても1日を二重に数えない |
| 同日の複数作業 | 1日として数える | 単位は作業日。終了記録が同日に複数あっても分子は1 |
| 遅れた記録 | 記録時刻ではなく `work_date` で数える | 後から追記した終了記録も、その作業日の分子になる |
| 作業日外の終了記録 | 記録率に入れず、`end_records_outside_work_days` に別に出す | 分母にない日を分子へ入れると率が1を超えうる |
| 分母0 | 率は `null`（N/A）。0%と区別する | 作業がない期間を「記録漏れ」と誤読しない |

週は月曜始まり。期間の端の週は期間内の日だけで数える。

## 4. 出力

| 項目 | 内容 |
| --- | --- |
| `coverage` | 作業日数・記録済み作業日数・率、未記録の作業日の一覧、終了記録数、作業日外の終了記録の件数、判定未完了の割合、分母の内訳（commit日・登録日・登録だけの日） |
| `weeks` | 週ごとの作業日数・記録済み日数・率・作業時間 |
| `candidates` | 期間内に作られた候補の状態別件数と、`DUPLICATE` を除く独立候補数 |
| `effort_minutes` | 作業別の合計分、合計、週平均（合計×7÷期間日数） |
| `size_reviews` / `effects` | 分量レビューの件数・純増行数・参照分離・例外、再発・悪化・効果未確認の配備 |
| `automation` | 自動化の検討条件（下表）と総合判定 |
| `recording_aid` | 記録補助フックを提案するか |
| `commits` | repoごとの読んだcommit数・除いたbot commit数・ローカルにないbranch |
| `limits` | この数字で分からないこと（commitのない未登録作業、ローカルだけを読むこと、条件達成は承認ではないこと、checkoutのないrepo、ないbranch） |

自動化の検討条件は、すべて満たすと `CONDITIONS_MET`、どれかが満たさないと `NOT_MET`、満たさないものがなくデータが足りないものがあると `UNDETERMINED`。

| 条件 | 閾値 | データ不足 |
| --- | --- | --- |
| 期間 | 14日以上 | — |
| 記録率 | 0.8以上 | 分母0 |
| 独立候補数 | 4件以上 | — |
| 作業時間の週平均 | 30分を超える | `effort` が1件もない |

`CONDITIONS_MET` でも、削減できる時間・自動化後に残る時間・開発保守の負担を人が比べるまで何も始めない。
記録補助フックは自動化の条件とは別に判断する。記録率が0.8未満、または終了記録1件あたりの記録時間（`RECORD` の時間を記録した終了記録だけで平均する）が5分を超えると `SUGGESTED`、どちらも分からないと `UNDETERMINED`。提案は配備の承認ではない。

## 5. 読む範囲と再計算

- `local_checkout` は絶対pathで、symlink・`.`・`..`・`/System/Volumes/Data` の別名を含まず、git checkoutであること。`~/.hermes` の下は大文字小文字を区別しないpathの比較だけで拒否し、中身もメタデータも読まない。満たさなければ `REPOSITORY_UNAVAILABLE`。
- `.git` はディレクトリか `gitdir:` ファイル（worktree）に限り、symlinkは拒否する。gitdirと `commondir` の指す先も同じ条件で検査し、値の `..` は先頭だけ許す（`x/../y` はsymlinkをまたぐと検査と食い違うため拒否）。gitdirとcommondirの中（`hooks` を除く）にsymlinkがあれば拒否する。object alternatesとgit設定のinclude（行の途中の `[include]` を含む）は、検査していない場所を読ませるため拒否する。
- 実行するのは、ローカルの `git rev-parse`（branchの先端）と `git log`（commit日付・作者）だけ。利用者とシステムのgit設定を読まず、fetch・pull・remote・APIの取得をしない。checkoutには書かない。checkout自身の設定は読まれるため、外部プログラムの起動や別ファイルの読込につながる設定（署名検証・mailmap・pager・fsmonitor）を毎回無効にし、replace objectと遅延fetchも使わない。
- branchがないこと（`rev-parse --verify --quiet` の終了コード1）以外のgitの失敗は `REPOSITORY_UNAVAILABLE` で止まり、commit 0件として集計しない。cacheも書かない。
- branchの先端・shallowの境界・台帳の内容・manifest・期間・集計の版とコードから指紋を作る。前回と同じなら台帳ディレクトリの `report-cache.json` を返し（`status: UNCHANGED`）、`git log` を実行しない。どれかが変われば再計算する（`status: COMPUTED`）。cacheが壊れていれば信用せず再計算する。cacheを書けなくても集計結果は返し、`cache: NOT_SAVED` と出す。

## 6. 検証

```bash
python3 -I -B tests/test_skill_improvement_metrics.py -v
```

一時ディレクトリのgit repoへ日時と作者を指定したcommitを作り、複数branch・bot・merge・cherry-pick・timezoneの日付境界・週境界・commitのない作業日・分母0・遅れた記録・未記録日・同日の複数作業・許可外branch・ないbranch・symlinkや `~/.hermes` のcheckout・gitdir・commondirの拒否・alternatesとincludeの拒否・署名検証プログラムを起動しないこと（陽性対照つき）・読めないrepoで止まること・cache再利用と再計算・14日の合成データでの3判定を確認する。
