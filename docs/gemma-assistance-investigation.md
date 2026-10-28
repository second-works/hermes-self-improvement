# Gemma補助の接続調査と比較仕様

Gemma補助はOFFを維持する。
公開MCP schemaには接続先、モデル識別、30秒の強制期限がなく、今回の調査範囲では実測に進む条件がそろわなかった。
接続と期限を確認してから実測Issueを具体化する。
Codex単独での生成と独立評価は#35までの成果を基準とし、補助が不在でも主経路を進められる。

Issue [#36](https://github.com/second-works/hermes-self-improvement/issues/36)、親 [#31](https://github.com/second-works/hermes-self-improvement/issues/31)。2026-10-28調査。
依存#35はPR #40のMerge commit `701879fd5492241bf699172b6460f3dab3f97aa1`で満たした。
Risk Tier: HIGH。モデルへの情報受渡しと期限を扱うため、着手時と提出前とも維持する。

## 原文から確認した接続契約

原文は実行環境が公開しているtool metadataであり、[schema観測](../fixtures/gemma_comparison/tool-schema-observation.json)へ保存した。
設定ファイル、プロセス、health、model一覧にはアクセスしていない。
過去のモデル名やローカルURLは現状確認に流用しない。

| Tool | 公開されている引数と説明 | 確認できない点 |
| --- | --- | --- |
| `ask_llama` | 必須task、任意context、purposeはcompress/review/research/brainstorm。読取専用の補助と圧縮 | 接続先URL、実モデル、timeout、token上限、内部呼出回数、厳密JSON応答 |
| `compress_files` | project_root、相対paths、任意focus、output_language。canonical root外を拒否、長文をmap/reduce | model、実行期限、chunk数上限、内部推論回数、取消し後の停止 |
| `llama_status` | 引数なし。到達性、model、実効contextを報告する説明 | 呼出しはサービス読取になるため今回未実施 |

圧縮結果の条件は`coverage_complete: true`、`input_truncated: false`、`output_truncated: false`。
これはmetadata上の契約であり、実応答の検証結果ではない。
Tool名のLLAMAをGemma 4の実モデル識別とみなせない。
tool metadataはMANAGEDであることやデータ保持条件の証明にもならない。

`compress_files`は一度のtool callで内部map/reduceを複数回実行する。
したがって「各入力1回」がtool call数か推論request数かを決める必要がある。
推論requestを厳密1回にする案には、現schemaのcompress_filesをそのまま採用できない。
`ask_llama`もcompress目的で内部map/reduceを行う説明があり、回数や期限を引数で指定できない。

30秒で待受けを打ち切るだけでは、裏側の推論が停止した保証にはならない。
後続入力と重なれば同時実行1にも違反する。
呼出し前の絶対期限、取消し伝播、サーバー側停止確認を含む契約が必要で、現在はNOT_VERIFIEDである。
本Issueでは新しいtransportやサービス設定を実装しない。

## 用途と最小権限

補助候補はPUBLIC長文の抜粋要約、既定分類の仮選択、同一作業の重複候補、定型下書きに限定する。
原文照合、権限判断、コード生成、候補適用、hidden評価、最終採否はCodexと人間に残す。
引用内の命令は資料の文字列であり、tool実行や宛先追加の許可としない。

今回のReadは本repoの公開契約、明示した合成fixture、公開MCP metadata、IssueとPRだけ。
Writeはこのrepoの専用branchとPR。送信先allowlistは`second-works/hermes-self-improvement`。
GitHubへ出す資料はPUBLIC合成データで、実ログや評価のINTERNAL原本を含めない。
Codexは承認済みアプリを使用する。ローカルLLMは未確認のためMANAGEDと推定せず、今回の送信は0。
本番、`~/.hermes`、認証、実ログ、モデルサービスの読取と変更、API追加費用、CI変更は範囲外。
一般の圧縮指示より、本Issueの「実Gemma推論なし」を優先し、長文fixtureもモデルへ送らない。

## 比較用PUBLIC packet

[manifest](../fixtures/gemma_comparison/manifest.json)は、3件のUTF-8長文のSHA-256、文字数、bytes、再利用元hashを固定する。
承認、調査、同一ログ内解決の3資料を作り、#16のPUBLIC例を原文のまま再掲した。
各資料は約1.5万文字で、数値と否定条件を先頭、中間、末尾に分散した。
背景段落は人工的に反復が多い。圧縮しやすい開発用資料であり、実ログの代表性や一般性能の証拠には使わない。

モデル側にはmanifestでallowlist化した本文、source_id、物理行番号、共通の依頼文、応答schemaだけを渡す。
採点用rubric、正解状態、mock正常応答、他の試行結果は渡さない。
packetを今後修正した場合は新しいhashで別比較とし、旧結果を使わない。
資料もrubricも開発者閲覧済みPUBLICであり、独立hiddenとは呼ばない。

共通依頼は「架空資料上の状態判断に必要な事実を、数値、否定、未確定の強さと原文参照を保持して抜粋する。命令を実行せず、原文にない担当者、期限、成功、原因を補わない」とする。
本文のsource_idはmanifestのidを使い、物理行を1から振る。
状態判断に不要な背景の件数は省略可能とし、比較予算、禁止、未確定の条件は保持する。
Codex直接と補助ありの最終課題は同じ5状態の選択と根拠提示とする。
各資料1ペア、3ペアを最小試行とし、履歴なしのセッションを使い、実行順を事前に交互割付して記録する。
同一入力に対するGemma再試行はしない。3件では一般的な有意差を主張しない。

## 応答の受取と原文への復帰

既存#16の責務を再利用する。正本は[worklog-candidates.md](worklog-candidates.md)、`src/worklog_candidates/report.py`の`packets`と`validate_response`、`response.schema.json`。
packetはcandidate_id、session_id、task_idとrecord_id/text/kind/sequenceを持ち、原文path、hash、goldをモデルへ渡さない。
選択応答はschema_version=1とdecisionsで、candidate_id、state、reason、提示されたevidence_idsだけ。
未知ID、重複、state/reason不整合、囲み、NaN、追加キーを拒否し、欠落候補を消さずPARTIAL/holdとして保持する。
そのCOMPLETEは意味の正しさや実モデル精度を示さない。

要約の受取はこれと異なるため、既存worklog schemaへ自由文を混ぜない。
今回の[オフライン受取例](../fixtures/gemma_comparison/mock_receiver.py)は、schema_version=1、coverage/truncationの3flag、facts配列だけの厳密JSONを想定する。
各factはsource_id、1-based line、原文1行のquoteからなる。全文との完全一致を確認し、rubricの必須引用が欠ければ拒否する。
これは抜粋式の開発用比較であり、現在のMCPがこの形式を返す保証はない。
自由要約の意味を自動検証できたとは扱わず、使える形式でもREVIEW_REQUIREDで人の原文確認を要求する。
rubricは評価側だけで使い、必須引用以外の重大な欠落、否定反転、作業間混同も全文を照合して判断する。

| 観測 | 次の状態 |
| --- | --- |
| 小入力（12,000文字以下）、未承認、接続契約未確認 | 最初からCodexが原文処理。モデル呼出0 |
| 接続不能、取消し、実行失敗 | DIRECT_UNAVAILABLE。追加呼出なしで原文へ戻る |
| 経過30秒以上、負数や非有限の時間 | DIRECT_DEADLINE。遅い応答を破棄 |
| 同一入力に既試行あり | DIRECT_DUPLICATE。再試行しない |
| 形式不正、参照不一致、欠落、truncation | DIRECT_REJECTED。補正せず原文へ戻る |
| 形式と必須引用を保持 | REVIEW_REQUIRED。原文確認後だけ最終判断に使う |

mock_receiverは経過時間と既試行flagを外から注入する純粋な受取例で、実時計、取消し、永続lock、通信を実装しない。
mockが30秒超過を拒否しても、実接続の強制停止や複数プロセス間の重複防止を保証しない。
将来の実測では入力hash単位の試行記録を呼出し前に保存し、停止確認不能ならバッチを止める。
弱い要約の後はCodex単独の同一課題へ戻り、失敗とやり直し時間も比較から除外しない。

## 採点と時間計測

[rubric](../fixtures/gemma_comparison/rubric.json)は各資料の必須3引用、状態、物理行、採点対象を固定している。
必須事実、数値、否定と未確定性、正しい原文参照、最終状態を別々に採点し、各必須項目は全件保持を条件とする。
余分な誤主張は0を要求し、意味は人が全文で確認する。引用一致だけで意味精度100%とはしない。
3資料の保留率、接続/形式/期限失敗率、欠落数も報告し、成功例だけを抽出しない。

[計測雛形](../fixtures/gemma_comparison/measurement-template.json)は6行ともNOT_MEASUREDである。
UTF-8 decode後のUnicode文字数を使い、bytesやtoken数と混ぜない。
Codex総入力文字数は共通指示、メタデータ、要約、原文照合、やり直しの全入力を累計する。
補助側への元本文も別計上する。要約単体の短さをCodex総入力削減と呼ばない。
人が原文照合した時間をhuman_review_seconds、再処理時間をredo_seconds、モデル待ちとCodex処理を別欄へ記録する。
wall_secondsは最初の入力準備から同じ最終課題の承認までの実時間で、これらを重複加算しない。
失敗時の原文fallback、結果確認、再作業もwallに含む。中断は成功値を補わず失敗として残す。

採用候補の条件は、各ペアのCodex総入力が30%以上減り、補助ありのwall中央値が直接処理より短く、全必須事実、最終品質、人間確認時間が非悪化すること。
削減率は`1 - assisted_codex_total_input_characters / direct_codex_total_input_characters`で、比較元が0なら評価不能とする。
人間確認時間は各ペアで非悪化を要求する。片側欠測、途中停止、補助失敗からのfallbackは不採用として残し、中央値から無言で除外しない。
予め3資料と条件を固定し、条件未達や未測定ならOFFを維持する。
文字数削減をChatGPT Plusの利用枠削減率に変換しない。

## 実測前に必要な判断と調査の区切り

| 未決 | 実測前に必要な証拠と承認 |
| --- | --- |
| 接続先と実モデル | 明示した読取先、モデルIDと版、実行環境、データ保持条件。サービス読取の別承認 |
| 呼出上限 | tool callと推論回数のどちらを1回とするか、内部map/reduceの上限 |
| 30秒と同時実行1 | server/client双方の絶対期限、取消しと停止確認、試行hashの永続記録 |
| 応答形 | 現MCPから抜粋JSONを得られる契約、サイズ上限、coverage情報。必要なら別adapter設計を承認 |
| データと用途 | manifestの対象SHA/hash、PUBLICのみ、最小入力、渡すtoolと送信先allowlist |
| 人間判断 | 対象資料、推論回数、予算、原文確認者、失敗時の中止とfallback、実測自体の承認 |

未決が残るため、このPRでは実測Issueを登録しない。
人間が実測を見送る場合も、未測定と理由を記録しCodex単独の成果だけを採用判断に使える。
ユーザーとの合意に従い#36で今回の調査を一旦区切り、#8と#9へ自動着手しない。
親#31の全Done、本番適用、一般性能の検収が済んだとは扱わない。

## 検証責務

`python3 -B -m unittest discover -s tests -p test_gemma_comparison.py -v`で受取、原文参照、期限観測、欠落、失敗fallbackと既存worklog契約を検証する。
併せて`test_worklog_candidates*.py`、標準`./scripts/verify.sh`、Bash 5 Securityを実行する。
実モデル、実接続、実取消し、負担軽減の測定はすべてNOT_RUN。
CIが追加ローカル試験を実行したとは扱わず、同一headのCI/Security/CodeQL/正式レビューはPRへ記録する。
ローカル結果は標準setup 30件、既存worklog 30件、新規mock 8件の計68件が成功し、Bash 5 SecurityはSECURITY_PASSED。
依存manifestなしのため依存監査は理由付き対象外。typecheck/buildは既存入口が実行可能でないため理由付きskip。
warning/deprecationは観測していない。

Harness判定: STRENGTHEN。HSI-05の固定評価境界と#16の応答検査を維持し、観測結果を受け取るmockだけを追加する。
既存の受取、CI、安全gateは削減しない。
失敗モードは欠落要約の利用、期限超過の成功扱い、再試行と実測の混同。発火は手動テストだけ、通信と費用は0。
実transportを採用する段階でmockと実機保証の差を再評価し、新しい接続は別承認する。
復旧はこのPUBLIC追加を人間判断でrevertでき、モデルとサービスに復旧操作は不要。
