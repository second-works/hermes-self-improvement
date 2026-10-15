# fixtureによる自己監査・失敗診断

Decision: [Issue #4](https://github.com/second-works/hermes-self-improvement/issues/4) は、明示指定した合成snapshotだけを読む決定的なCLIで実装する。監査結果と根拠付き改善提案をJSONで返し、実行・インストールへ接続しない。Risk Tier: **MEDIUM**（機能追加。権限、安全規則、本番、既存Gateの変更なし）。

基準mainは `fe81a5c17e2ad2832e8f5d7a7190b86019e17262`。基本設計PR #11、Memory検証PR #12、独立評価PR #13のMergeを確認した。#3/#5のIssue Closeや本番のProduct Acceptanceは今回行わない。

## 入力と出力

```sh
python3 -I -B scripts/audit_fixture.py --input fixtures/audit/sample.json
python3 -I -B tests/test_audit.py -v
```

[入力schema](../schemas/audit-input.schema.json)、[合成入力](../fixtures/audit/sample.json)、[出力schema](../schemas/audit-report.schema.json)、[出力例](../fixtures/audit/report.example.json)。Python標準ライブラリのみを使う。同じ入力は同じbyte列を返す。時刻、乱数、環境変数、本番の探索、network、provider、Docker、SessionDBを使用しない。

入力はrepo内 `fixtures/audit/` の明示相対path、通常ファイル、256KiB以下に限定する。絶対path、`..`、symlink、特殊ファイルを拒否する。CLIはstdoutに結果を返し、保存・追記・削除しない。既存 `runs/` と `logs/` は入力にも出力にも使わない。このpath制限はローカルの信頼済みfixture操作用であり、敵対processとの同時差替えを防ぐOS sandboxではない。

`source_kind=synthetic-fixture` と `classification=PUBLIC`、固定upstream SHA、完全な基準SHAを必須とする。Skills、Tools、Models、認証の状態、Delegationの状態を列挙する。認証は `ready / blocked / unknown` の状態だけで、認証値や環境変数名を格納しない。各観測は対象capabilityと参照resourceを固定する。未定義field、重複ID、未登録参照、未知enum、JSONの重複key、非有限数を拒否する。公開ラベルやschemaだけでは実データの機密性は保証できないため、入力は人間が検査した合成データだけに限定する。

原ログの代わりに、合成ログの行番号と固定event codeだけを受理する。自由文、prompt、会話、Secretは受理しない。根拠は正規化JSONのSHA-256と入力内JSON Pointer、行番号、codeで参照する。入力hashは意味内容へのcommitmentであり、外部ログの真実性や改ざん防止を保証するものではない。

fixture ID、Issue URL、UTCの観測日時を入力で固定し、run IDは入力hash先頭12桁から導出する。サンプル日時は合成値で、実環境をその時刻に観測した意味ではない。resourceの状態は選択したprofileについて入力されたsnapshotとして扱い、他profileの認証やモデル状態へ一般化しない。

## Skills集計の定義

固定公開upstreamは `NousResearch/hermes-agent@f97608f178d1ffeca59860195ab7da295f7c8e5f`。確認原文は [profile別path](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/tools/skills_tool.py#L67)、[探索順](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/tools/skills_tool.py#L173)、[一覧のfilterと同名排除](https://github.com/NousResearch/hermes-agent/blob/f97608f178d1ffeca59860195ab7da295f7c8e5f/tools/skills_tool.py#L184)。同ファイルの確認時SHA-256は `0d47bda41ed9d1ec84856df3d336a42bb94161e89bd9a8b857e76ec76be9f7b7`。

upstreamではproject/local/externalの探索順とprofile、disabled、platform/environment/apps条件、同名排除が件数に影響する。builtin/local/hubはその探索順位と同じ概念ではない。今回のfixtureでは次の単純化した契約を固定する。

| 項目 | 定義 |
| --- | --- |
| `origin` | `builtin`=同梱由来、`local`=手動作成由来、`hub`=hub取得由来というfixtureの排他的な由来ラベル。upstreamに同じ3分類のAPIがあるという主張ではない |
| `profile` | 明示した1つのprofile。暗黙のprofile継承やglobal検索なし |
| `registered_records` | 全profile・全originの入力レコード数。実ファイル数ではない |
| `profile_filtered_records` | 対象profileかつenabled/compatibleの両方がtrueの件数。compatibleはfixture内の既知条件であり、実環境の検査ではない |
| `available_unique_names` | filter後、同名を明示priority昇順→id辞書順で1件にした件数。由来から優先順位を推測しない |
| `excluded` | 別profile、対象profileのdisabled、有効だが非互換、filter後の同名重複という重ならない除外数 |

124登録・1件disabledなら123利用可能になる合成試験を持つ。同名重複、profile差、非互換も個別に試験する。過去の123件/124件が実際にどの条件で生じたかは**未確認**であり、固定公開upstreamだけから本番の原因を推定しない。pluginやlegacy形式を含む実runtime全体のcollectorは実装していない。

## 診断と提案

| 失敗原因 | 支持する観測と追加条件 | 提案 |
| --- | --- | --- |
| スキル不足 `skill_gap` | `SEARCH_COMPLETE`、完全な棚卸し、全参照resourceがready、全profileに同capabilityの既存スキルなし | 隔離fixtureのスキル案 |
| 既存スキル未選択 `skill_not_selected` | 完全な検索、`SELECTION_SKIPPED`、利用可能な既存スキルあり、未選択、resourceがready | 選択手順の改善 |
| 手順不良 `procedure` | 利用可能なスキルを選択済み、`STEP_SKIPPED` | 既存手順の修正案 |
| モデル制約 `model_limit` | `CONTEXT_LENGTH_EXCEEDED` | 固定上限内の入力調整案 |
| 権限/APIエラー `permission_api` | `HTTP_401 / HTTP_403 / HTTP_429` | inert fixtureでの診断、人間確認 |
| 外部依存 `external_dependency` | `DEPENDENCY_UNAVAILABLE` | 依存失敗の明示とfixtureによる復旧試験案 |

複数原因、未知の観測、成功と失敗の矛盾、証拠欠如、説明できないblocked/unknown resourceはHOLD。成功ログだけの成功観測はNO_FAILUREとする。disabled、別profile、非互換、同名shadow下に既存capabilityがある場合、利用不能だけを理由に新規作成しない。これは決定的なルールの診断であり、因果の証明ではない。確度MEDIUMはルールが支持した推定、LOWは保留で、較正済み確率ではない。

改善提案には原因、観測ID、入力hash、確度、期待効果、テスト可能な受入条件、基準SHA、fixture用allowlist、ゼロAPI予算、依存記録、未申請の承認状態を付け、内容をproposal hashで固定する。同じ原因・capability・profileは1提案に集約する。`public_evaluation_id=audit-v1-<capability>` はこの合成入力のcapability別診断試験を指す。#5のhidden評価IDや実LLMの品質証明ではない。

`hermes-agent-skill-authoring` はスキル不足提案の文字列参照だけで、呼び出さない。既存スキル未選択、手順不良、モデル、権限/API、外部依存から新規スキル案を生成しない。提案は複数あっても候補workerは0で、各予算の候補上限1は実行許可ではない。#7で実行へ接続する前に、対象artifact、具体的変更path、評価入力、予算全体、承認を固定する必要がある。実装/採用/認証変更を自動承認しない。

## 検証と境界

独立した[期待値](../fixtures/audit/expected.json)は、10観測の6分類、HOLD2件、NO_FAILURE1件、スキル不足の重複観測を含む。出力は6提案、新規authoring提案1件。誤判定は期待原因との不一致、過剰生成は非スキル不足からのauthoring提案または同原因の重複提案として検査する。有限fixtureでの一致を一般的な診断精度とは呼ばない。

正常系は6分類と再現性、境界は空入力・124/123・profile/filter/同名・byte上限、異常系はschema/参照/矛盾/未知resource、回帰は既存verifyとMemory/評価の純粋契約試験を使う。実runtime統合・並列worker・HTTPサーバー・性能/負荷試験は、この純粋な合成診断CLIには対象外。全体の標準検証入口、CI、固定setup試験は変更しない。追加試験は上記コマンドで明示実行し、既存CIへ自動追加済みとは報告しない。

Harness判断はKEEP。発火は明示CLIによる合成の失敗観測、入力は固定snapshot、出力はstdoutの診断・提案だけ。API費用0、候補実行0、既存Memory/独立評価と責務重複なし。新しいcollectorや本番adapterを提案する時点で、この単純化と試験の保証範囲を再評価する。

情報分類は検査済みPUBLIC fixtureと公開upstreamのみ。Readは当repoと固定公開ソース、LLM環境は追加のモデルAPIを使わず、ローカル文書圧縮もPUBLIC文書に限定する。GitHubへのWriteは当repoのIssue/PR/branchに限定し、今回の検査済み差分と提出文の人間承認後に行う。復旧は今回の機能差分を戻す人間判断であり、保存原本を削除しない。`~/.hermes`、本番、Secrets、hidden評価原本、RAG/DB、定期化、外部サービスへの新規接続は対象外。

実装時のローカル確認では、追加14テスト、標準verifyの30テスト、既存独立評価の純粋契約34テスト、Memoryハーネス8テストが成功した。10観測の期待原因は全件一致し、HOLD2件、NO_FAILURE1件、6提案・authoring提案1件を確認した。Security PreflightはSECURITY_PASSED、依存manifestがないためDEPENDENCY_STATUS=SECURITY_NOT_APPLICABLE。typecheck/buildは入口未設定の理由付きskip。self-reviewでは呼出元CLI、両schema、出力例、既存監査・評価契約との境界を確認した。PR未提出のためremote CI / Security / CodeQL / Codex Reviewは未確認。

文書8点のローカルLLM圧縮は結果未取得で打ち切り、完全coverageのdigestを得られていない。圧縮結果は判断に使わず、変更・安全境界に関わる原文を直接確認した。
