# Skill改善MVPの手動運用・評価・復旧契約（#106）

**Decision: Skill改善MVPを「記録・集計」と「個別承認した手動改善」に分け、記録・評価・配備・効果確認・rollbackの判定を、PUBLIC例で照合できる契約に固定する。**

親は [#105](https://github.com/second-works/hermes-self-improvement/issues/105)、本書は子 [#106](https://github.com/second-works/hermes-self-improvement/issues/106) の成果物。
Risk Tier: HIGH。実Skillへの反映・復旧の承認条件と、評価の合否契約を定める。
本書は契約だけを定める。台帳CLIは #107、集計は #108、2週間の実運用は #109、自動化の設計は #110 で扱う。
本書のMergeは、pilotの開始、実Skillの変更、モデル呼出、他repoへの書込の承認ではない。

## 1. 正本と例

| 種類 | ファイル | 役割 |
| --- | --- | --- |
| 台帳1行のschema | [ledger-record.schema.json](../schemas/skill-improvement/ledger-record.schema.json) | 終了記録・経験・候補・評価・分量レビュー・配備計画・配備状態・効果観測 |
| 対象repo manifest | [repository-manifest.schema.json](../schemas/skill-improvement/repository-manifest.schema.json) | 実運用開始前の必須入力 |
| 許可遷移 | [state-transitions.json](../schemas/skill-improvement/state-transitions.json) | 候補と配備の状態遷移。表にない遷移は拒否する |
| PUBLIC台帳例 | [ledger.example.jsonl](../fixtures/skill_improvement/ledger.example.jsonl) | 合成2 repoでの、記録から効果確認までの一連 |
| PUBLIC判定例 | [scenarios](../fixtures/skill_improvement/scenarios) | 保留・停止・復旧待ちになる例と陽性対照 |
| 例の生成 | [build_examples.py](../fixtures/skill_improvement/build_examples.py) | 合成例を作り直す。承認hashなどの計算値を手で直さない |
| 照合テスト | [test_skill_improvement_contract.py](../tests/test_skill_improvement_contract.py) | schema・参照・遷移・判定表と例の整合を確認する |

PUBLIC例のhash・ID・repo・担当者はすべて合成値で、承認の記録ではない。
台帳は1行1イベントのappend-only JSONLとする。状態の変更も新しい行の追記で表し、既存行を書き換えない。
共通の項目は `schema_version / event_id / recorded_at(UTC) / work_date / timezone / repository_id / work_unit_id / classification` とする。

## 2. 2つの段階と開始条件

| 段階 | 開始に必要なもの | できること | できないこと |
| --- | --- | --- | --- |
| `RECORD_ONLY` | 承認済みmanifest | 終了記録、経験、候補の登録と集計 | 実Skillの変更 |
| `RECORD_AND_MANUAL_IMPROVEMENT` | 承認済みmanifestと、反映ごとの個別承認 | 第6節の条件を満たした1件ずつの手動反映 | 承認範囲外の反映、自動反映 |

manifestには、対象repo（2つ以上）の識別子・許可root・読取項目・情報分類・担当と、全体の期間・timezone・保存先・承認を書く。
manifestにないrepoを推測で追加しない。manifestが未承認なら記録も始めない。
許可rootはrepo内の相対pathに限り、`.` や `..` の区間を含めない。`repository_id` はmanifest内で一意とする。schemaでは表せないため、台帳の実装と照合テストで検査する。期間はmanifestのtimezoneの日付で判定する。
`RECORD_ONLY` のmanifestでは、承認票が揃っていても反映を保留にする（例: `deploy-record-only-stage`）。

## 3. 記録の種類と状態

終了記録（`session_end`）は作業単位ごとに1件で、次の3つから選ぶ。

- `CANDIDATE_FOUND`: 経験のIDを1件以上持つ。経験には種類・一行要約（120字以内）・根拠参照・原因分類が必要。
- `NO_CANDIDATE`: 経験の種類や根拠を求めない。記録負担を増やさないため、空の経験は作らない。
- `UNDETERMINED`: 判定できなかった理由を必ず書く。候補なしとして数えない。

経験の種類は、訂正（`CORRECTION`）・手戻り（`REWORK`）・反復指摘（`REPEATED_FEEDBACK`）・より良い方法（`BETTER_METHOD`）の4つ。
根拠は参照文字列だけを保存し、URLを自動取得しない。

候補の状態は `OPEN / HOLD / DECLINED / DUPLICATE / DEPLOYED / ROLLED_BACK`。`OPEN` 以外は理由を必須にする。
`DUPLICATE` は元候補のIDを持ち、同じ経験を根拠に含む。`DEPLOYED` と `ROLLED_BACK` は配備IDを持つ。

配備の状態は計画（`PLANNED`）→承認（`APPROVED`）→（他repoならMerge記録 `MERGED`）→反映済み・効果未確認（`DEPLOYED_EFFECT_UNCONFIRMED`）と進む。
その後は効果確認済み（`EFFECT_CONFIRMED`）・改善未確認（`IMPROVEMENT_UNCONFIRMED`）・停止（`HALTED`）に分かれる。
rollbackは `HALTED → ROLLING_BACK → ROLLED_BACK / RECOVERY_REQUIRED` だけを許可する。取り下げは `WITHDRAWN`。
反映前に計画を追記し直すと `PLANNED` へ戻り、以前の承認は使えない。
承認を経ない反映など、[許可遷移](../schemas/skill-improvement/state-transitions.json) にない遷移は拒否する（例: `transition-deploy-without-approval`）。

## 4. 原因の6分類と対処

| 分類 | 意味 | 対処 |
| --- | --- | --- |
| `MISSING_PROCEDURE` 手順欠落 | Skillに必要な手順がない | 最小の手順追加を候補にできる |
| `NOT_LOADED` 読込不足 | 手順はあるが読まれていない | 本文へ追記せず、入口・起動条件・参照先を見直す |
| `NOT_FOLLOWED` 遵守不足 | 読まれたが守られていない | 本文へ追記せず、確認手順・構造・停止条件を見直す |
| `TEMPORARY` 一時事情 | その場限りの事情 | Skillを変更しない（`DECLINED`） |
| `CONFLICT_OR_UNVERIFIED` 競合・未確認 | 既存規則との矛盾、根拠不足 | 確認できるまで `HOLD` |
| `DUPLICATE` 重複 | 既存の候補・規則で扱える | 元候補へ結び付ける |

分類前の経験は `UNCLASSIFIED` で記録できるが、候補にするには6分類のどれかが必要。
共通Skill化（`SHARED`）は人が判断し、根拠を次のどちらかに限る: 2つ以上のrepoでの反復（repoの一覧を記録）、または明確な共通契約の欠落（契約の参照を記録）。

## 5. 分量レビュー

対象Skillの本文は、初期のレビュー目安を120行または80行とし、どちらを使うかを対象ごとに `guide_lines` へ記録する。
120行と80行の割当先は計画0.2で特定されていないため、本書では決めない。対象ごとに担当者が選び、理由を残す。
目安は停止条件ではなく、責務の削除を強制しない。各分量レビューに次を記録する。

- 変更前後の行数、純増行数（変更後−変更前と一致させる）、参照分離の移動先。
- 変更前の責務の一覧と、各責務の行き先（`KEPT / MOVED / MERGED`、または理由と承認者付きの `RETIRED`）。
- 目安を超える場合の例外理由。

判定は、行き先のない責務があれば `HOLD`、目安超過で理由がなければ `HOLD`、理由があれば `EXCEPTION_RECORDED`、目安内なら `WITHIN_GUIDE`。
行数を減らしても責務が消えれば保留にする（例: `size-responsibility-dropped`）。

## 6. 手動反映の前に固定するもの

配備計画（`deployment_plan`）に次を固定し、その後に個別承認を追記する。

- 対象Skillとそれを所有するrepo（`target.repository_id`）、正本の参照、配備先の参照。
- baseline・candidate・評価のhash、反映前後の期待hash、backupの参照とhash。
- 担当者、期限、適用条件、Skillのversion（効果窓の判定に使う）。
- rollbackの事前承認（承認者・実行者・発動条件・期限）。なければ `null` とし、即時rollbackはできない。
- 経路: 手元での手動反映（`LOCAL_MANUAL`）か、所有repoの専用Issue/PR（`OWNER_REPOSITORY_PR`）か。他repoのSkillは所有repoのIssue/PRでしか変更しない。手元の手動反映は、所有repoと記録したrepoが同じ場合に限る。

承認は計画イベントのID（`plan_event_id`）と、計画の `record` 部分を正規化JSON（キー順・区切り固定・UTF-8）にしたSHA-256（`plan_sha256`）に結び付ける。
反映してよいのは次をすべて満たすときだけで、満たさなければ理由付きで保留する。

| 確認 | 保留理由 |
| --- | --- |
| manifestのrepoが一意で、記録repo・所有repo・PR先repoがすべて登録済み、段階が手動改善で、期間内 | `MANIFEST_DUPLICATE_REPOSITORY / REPOSITORY_NOT_IN_MANIFEST / STAGE_RECORD_ONLY / OUTSIDE_PERIOD` |
| 経路が所有repoと合う | `OWNER_REPOSITORY_PR_REQUIRED / OWNER_REPOSITORY_MISMATCH` |
| 候補の最新状態が `OPEN` | `CANDIDATE_NOT_OPEN` |
| 評価が `IMPROVED` で、hashが計画と一致 | `EVALUATION_NOT_IMPROVED / EVALUATION_MISMATCH` |
| 分量レビューが `HOLD` でなく、同じ候補と正本を対象にしている | `SIZE_REVIEW_HOLD / SIZE_REVIEW_MISMATCH` |
| 最新計画に対する承認があり、`plan_event_id` と `plan_sha256` が一致 | `APPROVAL_MISSING / APPROVAL_MISMATCH` |
| 承認の期限内、計画の期限内 | `APPROVAL_EXPIRED / DEADLINE_PASSED` |
| 他repo経路ではMergeの記録がある | `MERGE_MISSING` |

MergeとSkillの反映は別の記録にする。Mergeしただけでは配備済みとしない。
反映の記録には、根拠にした最新の承認イベントと、反映前に観測したhash・反映後のhashを残し、計画の期待hashと照合する。反映時刻（`deployed_at`）は追記時刻（`recorded_at`）以前とし、どちらの時刻でも上の確認を満たす必要がある。この確認を通らない反映の記録（反映後hashの不一致を含む）は、台帳に追記できない不正な行として扱い、人の確認を待つ。

## 7. 評価

次の3条件を別々に判定し、すべて満たしたときだけ `IMPROVED` とする。

1. 必須契約への絶対合格: 必須ケースをすべて合格する。1件でも落とせば `CONTRACT_FAILED`。
2. 退行なし: baselineで合格していたケースを候補が落とさない。落とせば `REGRESSED`。
3. 改善の確認: 改善対象のケースで候補がbaselineを上回り、試行が安定し、劣化対照が有効である。

安定の確認には3試行以上を必要とする。同点・不安定・試行不足・対照不成立は `IMPROVEMENT_UNCONFIRMED`（例: `evaluation-tie`、`evaluation-unstable`）。
件数が矛盾する評価（合格数がケース数を超える、改善対象が0件など）は判定に使わない。
決定的な検査で評価できない品質だけ、人間がbaselineと比べる（`HUMAN_COMPARISON`）。人間比較で差がない・比較できない場合も改善未確認とする。
確認する内容は質問の有無だけでなく、必要事項・操作順序・本来のタスクの完了を含める。3試行は初期のスモークで、一般的な有効性の証明ではない。
評価は候補の生成前に凍結し、hiddenの正解や個別結果を生成側へ渡さない。[#86](candidate-evaluation-issue86.md) と [#92](semantic-evaluation-issue92.md) の独立評価の考え方を再利用するが、#92の生成1＋評価9の予算と承認は流用しない。

## 8. 効果窓

反映後に観測した作業を、配備ごとに1からの連続番号（`sequence`）で記録する。適用条件に合うかは `applicable` で示し、合わない作業も番号を飛ばさずに記録する。失敗・未完了の作業も落とさない。反映前に記録された観測は数えない。
効果窓は、Skillの読込・適用を確認できた最初の該当作業を含む連続3件とする。適用条件とversionは反映前に計画へ固定する。

判定は次の順で行う。

1. 安全違反・誤適用・明確な悪化・利用者の撤回が1件でもあれば `HALTED`（停止し、rollbackを判断する）。
2. 連番に欠けがあれば効果未確認（`SEQUENCE_GAP`）。
3. 窓の中で同じ問題が再発したら `IMPROVEMENT_UNCONFIRMED` とし、悪化とは分けて扱う。再評価は同じ経験を根拠にした新しい候補IDで記録し、元の候補は `DEPLOYED`、配備は `IMPROVEMENT_UNCONFIRMED` のまま残す。
4. 窓の中に、Skillが適用されなかった作業や結果不明の未完了作業があれば `IMPROVEMENT_UNCONFIRMED`。次の作業で埋め合わせない。
5. 窓が3件に満たなければ効果未確認（`WINDOW_INCOMPLETE`、配備は `DEPLOYED_EFFECT_UNCONFIRMED` のまま）。
6. それ以外は `EFFECT_CONFIRMED`。失敗した作業も、同じ問題が再発していなければ窓に数える。

## 9. rollbackと復旧待ち

即時rollbackは、計画に固定した事前承認の範囲（対象・発動条件・実行者・期限）でだけ行う。範囲外は別の承認（`SEPARATE_APPROVAL`）を記録してから行う。
intentの発動条件は、直前に停止（`HALTED`）させた条件と一致させる。別の条件を書いて事前承認を流用しようとした場合は保留する（`TRIGGER_MISMATCH`）。
手順は次の順に固定する。

0. 発動条件・承認・想定hashを確認する。満たさなければintentを記録せずに保留する。満たさないintentの行は不正な遷移として拒否する。
1. 排他lockを取る。
2. intent（lock・実行者・発動条件・承認根拠・想定する現在hash・backupのhash）を `ROLLING_BACK` として先に永続化する。
3. 現在hashを読み、想定した候補のhashと照合する。
4. backupから復元する。
5. 復元後のhashを反映前の期待hashと照合する。
6. `ROLLED_BACK` を記録する。

終了の記録（`ROLLED_BACK` / `RECOVERY_REQUIRED`）は、観測したhashから導かれる結果と一致しなければ不正な行として拒否する。

次の場合は上書きせず `RECOVERY_REQUIRED` にし、人の確認なしに再試行しない。

- 現在hashが想定と異なる（`CURRENT_HASH_MISMATCH`、例: `rollback-hash-conflict`）。
- intentの後に終了記録がない、または書込が途中で止まった（`PARTIAL_WRITE`、例: `rollback-partial-write`）。
- 結果が分からない（`UNKNOWN_RESULT`）、復元後のhashが合わない（`RESTORED_HASH_MISMATCH`）。

記録した理由は観測と整合させる。現在hashが観測できないのに `CURRENT_HASH_MISMATCH` とは書かない。`RESTORED_HASH_MISMATCH` は、観測した復元後のhash（`restored_sha256`）が期待と違う場合だけに使う。
事前承認の期限切れや実行者違いは、rollbackを始めずに保留する（例: `rollback-preapproval-expired`）。
採用・復旧の永続化と承認の結び付けは、[#8のfixture採用](fixture-adoption.md) の仕組みを再利用元とする。ただし本書は実Skillへの書込手段を追加しない。

## 10. モデル0と会計

MVPの「モデル0」は、ハーネスが追加で自動推論を送信する回数を0にすることを指す。
人が行う通常の作業と必須のPRレビューは別の会計とし、MVPの負担や費用に混ぜない。新しい宛先・認証・課金は許可しない。

## 11. 情報分類と保存先

実データの台帳は、manifestで承認したローカル保存先（`APPROVED_LOCAL_DIRECTORY`）にだけ置く。
GitHub、commit、PRへ出すのは、PUBLICな契約、合成例、公開可能な集計だけ。分類が不明なものはローカルで保留する。
`~/.hermes`、本番設定、認証値、会話履歴、サービス、登録外のrepoは、読取・変更・起動しない。

## 12. 計画0.2と改善案の対応

| 計画0.2の論点 | 採用した改善（#105） | 本書の箇所 |
| --- | --- | --- |
| MVPの範囲 | 記録・集計と個別承認の手動改善を分離し、反映前に対象・hash・backup・期限・担当・承認を確定 | 第2節、第6節 |
| 網羅率の指標 | 作業日網羅率（同日複数記録は1件）。集計の実装は #108 | 第3節の終了記録（分子の元データ） |
| 台帳 | append-only JSONLで、終了記録・経験・候補・配備を分離。候補なしに種類や根拠を強制しない | 第1節、第3節 |
| 評価 | 絶対合格・退行なし・改善確認を別判定。同点・揺らぎ・比較不能は改善未確認 | 第7節 |
| 評価の独立性 | 評価を生成前に凍結し、hiddenを生成側へ渡さない | 第7節 |
| 効果確認 | 読込確認を含む連続3件。再発と悪化を分ける | 第8節 |
| 反映と復旧 | 別操作の承認。即時rollbackは事前承認内のみ。不一致・結果不明は `RECOVERY_REQUIRED` | 第6節、第9節 |
| 分量 | 120/80行は目安。責務を保存し、参照分離・統合・理由付き例外を記録 | 第5節 |
| 自動化の条件 | 記録補助と生成自動化の判断条件を分ける。判断は #109 / #110 | 本書の対象外 |
| モデル0 | 追加の自動推論0。通常作業と必須レビューは別会計 | 第10節 |

ジョブ停止は利用者が実施済みと報告したため、本書の作業・前提・承認・チェックリストに含めない。停止状態の再確認や再開も行わない。

## 13. 照合方法と限界

`python3 -I -B tests/test_skill_improvement_contract.py -v` で、schema・参照・遷移と、第5〜9節の判定表をPUBLIC例へ当てて確認する。
テストは記録された判定ラベルをそのまま信じず、件数・hash・期限・連番から判定し直す。事実を変えた例で結果が変わることも確認する。コミット済みの例が [build_examples.py](../fixtures/skill_improvement/build_examples.py) の出力と一致することも確認する。
このテストは固定CI（`scripts/test.sh`）には含まれない。ローカルで別途実行した結果をPRに記録する。
実Skillへの書込、障害注入、モデル呼出、他repoへの書込は行っていない。合成例の合格は、実運用での有用性や効果の証明ではない（#109で確認する）。
