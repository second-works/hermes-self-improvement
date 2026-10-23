# Gemma隔離改善試験

2026-10-23に、実証済みの操作選択方式を[実装構成](registered-operations.md)として採用した。
以下はその判断に使った過去の試験記録であり、新しいCLI全体の実モデル検証結果ではない。

Issue全体の未達条件と完了範囲の未決事項は[2026-10-23の調査メモ](issue-7-status-review-2026-10-23.md)を参照。
各節の呼出枠と承認状態は各試験時点の記録であり、現在の追加実験の許可を示さない。

現状: **Gemmaの操作選択→改善→修正不要の判断→ハーネスの実行・JSON出力まで、新構成の一連試験が成功**。候補は15/15合格、別の2入力も正解かつ厳密JSONとして保存。累計102呼出で終了、元32Kへ復元済み。登録済み2操作と固定PUBLIC課題での結果であり、自由なコード生成・自律的なスキル解釈・一般的な安定性を保証しない。

Decision: 最大2段階で修正操作を選び、全テスト合格かつ回帰なしの場合にだけ隔離候補を保持する。修正は登録済みの2操作に限定する。毎日の自動実行・本番適用・モデル本体の学習は行わない。

Risk Tier: HIGH。実モデル通信と一時サービス変更を伴うため。固定PUBLICソース・認証不要のローカルGemma・既存Docker隔離だけを使う。Issue #7内の候補改善と検証が対象。

## 予行結果

モデル通信0回の制御確認は成功した。

| 段階 | 結果 |
| --- | --- |
| 改善前 | 従来5/9、別問題1/6、合計6/15 |
| 登録済みの2修正を適用 | 従来9/9、別問題6/6、合計15/15 |
| 古い不具合コードを候補として再提示 | 6/15に悪化。REJECTED_REGRESSIONとして不採用 |
| 元の候補の保護 | 元hashを保持 |
| 隔離の拒否試験 | 7種を確認 |

別問題はパス・開始行・コメント数・文脈行・削除行・複数検出・shell実行を変えた6入力で、操作選択のプロンプトには渡さない。封印された独立評価セットではない。

初回の予行では新規fixtureのファイル名が既存出力契約に違反していた。契約を緩めずfixtureを修正して再検証し、初回runも保存した。Gemmaの新規判断結果として数えない。

## 実モデル試験の準備

前回の累計94呼出枠は消費済み。新しい通信は承認待ち。提案枠は追加最大6呼出・累計100呼出・入力40万/出力8万token据え置き・承認後20分。Gemmaが最大2段階で操作を選択し、全15問合格時だけ、新規Hermesセッションでskills_list/skill_viewを実際に呼び、別の課題に再利用する。

設定は承認済みの思考ON・省メモリ64K、操作選択だけJSON schemaあり。再利用中は実際のtool呼出を許可するためJSON grammarなし。swap増加32MiBまたはfree指標10%未満で停止、終了後は元32K・画像対応に復元する。誤回答・予算不足・未実施を成功扱いしない。

関連57テスト、標準30テスト、Security検査は通過。typecheck/buildは既存script非実行で理由付きskip、依存検査は対応manifestなしでNOT_APPLICABLE。commit・push・PR・本番変更は行っていない。

[予行の証拠](evidence/skill-delegation-improvement-cycle-offline.json)。原本runは `runs/cycle-offline-20261017T131908Z-aa840142/`。実行計画は `runs/gemma-cycle-plan/plan.json`。

## 実モデル試験の結果

承認された追加6呼出・20分枠で4呼出を実行し、累計98呼出・入力291476・出力予約56236tokenで停止した。改善選択では2操作を選んで6/15→15/15、次の判断では空リストを選び15/15を保持した。修正コードは検証側の登録済み処理であり、自由なコード生成の成功ではない。

新規Hermesセッションでskills_listとskill_viewを実際に呼んだが、最終回答にMarkdown fenceが付き、ruleが指定enumではなく説明文になった。行23とpathは正しかった。JSON_INVALIDで停止し、再利用は不合格。実スクリプトの読み込みと保存スキル説明の読み込みは区別する。回答を補正して成功扱いにはしていない。

予算の残りは2呼出だが、承認期限22:42:43 JSTを経過したため新規通信は停止。元32K復元はVERIFIED、swapは1149.5→1141.5MiB。改善済み候補はcycle-retainedに保持、本番適用なし。

元runのprogressでreuse=NOT_RUNのままなのは、JSON解析例外で結果代入前に停止したため。実際の試行・失敗はtool記録と回答原本で確認できる。今後の制御はRUNNING/FAILEDを保存するよう修正した。

再試験は、新規セッションでskills_list・説明・スクリプトを実際に読ませ、出力契約を明記する方式。同じ課題で比較し、JSON解析やrule検証を緩めない。最大2呼出・10分の枠はその後承認され、次節の再試験を実施した。

[実モデル試験の証拠](evidence/skill-delegation-improvement-cycle-live.json)。原本runは `runs/delegation-20261017T132309Z-69b9d703cc9f/`。

## 実スクリプト読込・契約明記の再試験

2呼出で、実skills_list、SKILL.mdのskill_view、scripts/review.pyのskill_viewを確認した。返却スクリプトの内容が保存済み候補と一致することもworkerで検証した。別セッションで候補を読み、課題を解釈した試験であり、Gemmaがその場でPythonスクリプトを実行した証拠ではない。実スクリプトの実行は別の隔離runnerで全15問を再確認した。

| 確認対象 | 結果 |
| --- | --- |
| 候補の実行テスト | 15/15合格 |
| スキル一覧・説明・実スクリプトの読込 | 実tool呼出と内容一致を確認 |
| 回答のpath・line・rule・cpu_seconds | 期待内容と一致 |
| JSONのみの回答形式 | Markdown囲みが残り不合格 |
| 総合判定 | FAILED_JSON_INVALID。再利用完了扱いにしない |

前回の誤ったrule説明文は正しいdynamic-evalへ改善し、pathと行23も一致した。ただし、内容確認のために囲み内を解析した結果は診断用であり、囲み除去を本番の受理処理へ導入したものではない。厳密なJSON入力条件は変更していない。

今回入力6049・出力1194token、モデル応答は約39.9秒と51.2秒。累計100/100呼出、入力297525・出力予約57430token、追加モデル料金0USD。swapは1125.5MiBのまま。元32K復元、8081/8082 health正常・実起動context32768、元plist hash、実行中コンテナ0を確認した。呼出上限に達したため追加通信なし。

制御プログラムは関連57テスト・標準30テスト・Securityを通過した版を使用した。typecheck/buildは既存script非実行で理由付きskip、依存検査は対応manifestなしでNOT_APPLICABLE。本番変更・commit・push・PRは未実施。

[再試験の証拠](evidence/skill-delegation-cycle-reuse-contract.json)。原本runは `runs/delegation-20261017T142052Z-89215c2533ff/`、サービス記録は `runs/context64-20261017T142045Z/service-report.json`。

次に試す場合は、toolを使う段階と、最終結果だけをJSON schemaで返す段階を分ける方法が候補となる。あるいは実スクリプトの実行結果をハーネスが直接返し、Gemmaは操作選択だけを担当する構成を検討できる。いずれも今回の再利用試験で実証済みの構成とは区別する。

## 操作選択とハーネス実行の分離

Decision: 最終結果のJSONをモデルに再記述させず、隔離実行したスクリプトの実stdoutを厳密検証して、ハーネスがJSONへシリアライズする構成を追加した。Gemmaは登録済み修正の選択だけを担当する。

Risk Tier: HIGH。実モデル試験では一時サービス変更と生成コードの隔離実行を伴う。情報分類PUBLIC、承認済みローカルUNMANAGED LLMへの固定コードのみ、宛先は既存localhost8081。秘密情報・本番Hermesには接続しない。

予行はモデル通信0回で成功した。従来9問＋別6問は6/15→15/15へ改善。追加の2入力を実スクリプトへ渡し、dynamic-evalは行23、shell-executionは行62の正しい結果を、囲みのないJSONで保存した。古い不具合コードを再提示した回帰拒否も確認した。

出力は実行stdout由来であり、テストの期待値から合成しない。JSON以外、契約外のrule、異なるpath、非ゼロcpu_seconds、実行失敗を拒否する。モデルのMarkdown回答を補正する処理は追加していない。関連62テスト、標準30テスト、Securityを確認。typecheck/buildは既存非実行scriptで理由付きskip、依存検査は対応manifestなしでNOT_APPLICABLE。

予行後に実Gemmaを接続する試験が承認された。試験枠は最大2呼出・累計102呼出・入力40万/出力8万token据え置き・承認後10分。修正選択→15問検証→修正不要の再判断→ハーネスによる2入力の実行とJSON出力を確認する。同じ思考ON・JSON schema・一時省メモリ64K、swap増加32MiB停止、終了後32K復元を維持する。

[通信なし予行の証拠](evidence/skill-delegation-controlled-execution-offline.json)。原本は `runs/cycle-offline-20261017T142826Z-caad8604/`、実行計画は `runs/gemma-controlled-execution-plan/plan.json`。

## 新構成の実モデル試験：成功

最大2呼出・10分枠で、以下を一連の処理として実測した。

| 段階 | 結果 |
| --- | --- |
| 改善前 | 6/15合格 |
| Gemmaが修正を選択 | count_context_lines と count_added_comments |
| ハーネスが登録済み修正を適用・検証 | 15/15合格 |
| 改善済みコードをGemmaが再判断 | 空リスト＝修正不要。15/15を維持 |
| ハーネスが別の2入力を実行 | evalは行23、shell=Trueは行62で正解 |
| 最終JSON | 実スクリプトstdoutを検証してシリアライズ。Markdown囲みなし |
| 終了判定 | CONTROLLED_EXECUTION_VERIFIED |

Gemmaは自由な修正コードや最終結果を生成せず、選択IDだけを返した。実行結果はハーネスが作成し、期待値を結果へ混入させない。以前のスキル読込後の自由回答試験は不合格のまま保存し、この成功で上書きしない。

今回入力4985・出力1933token、モデル応答は約66.1秒と66.8秒。累計102/102呼出、入力302510・出力予約59363token、追加モデル料金0USD。swapは開始1244.31→終了1236.31MiB、メモリ停止なし。元32K・画像対応への復元、8081/8082 health正常・実起動context32768、元plist hash、実行中コンテナ0を確認した。元候補・固定依存・制御ファイルのhash照合も通過。

関連62テスト・標準30テスト・Security通過の版を使用。typecheck/buildは既存script非実行で理由付きskip、依存検査は対応manifestなしでNOT_APPLICABLE。独立評価・本番適用・毎日の自動実行は行っていない。commit・push・PRも未実施。

[新構成の実測証拠](evidence/skill-delegation-controlled-execution-live.json)。原本runは `runs/delegation-20261017T143114Z-cdb80f512c0f/`、実結果は同runの `execution-results.json`、サービス記録は `runs/context64-20261017T143111Z/service-report.json`。
