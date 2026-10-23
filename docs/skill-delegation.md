# Hermes本体の標準Skills・Delegationによる候補作成

2026-10-23に、登録済み操作をAIが選び、ハーネスが検証付きで実行する構成を採用した。
現在の実装と完了条件は[登録済み操作の構成](registered-operations.md)を参照。
以下の生成と再利用を目指した設計は過去の経緯として保持し、新しい完了条件と区別する。

2026-10-23の確認結果と未決事項は[Issue #7の調査メモ](issue-7-status-review-2026-10-23.md)を参照。
以下の試験経緯は各試験時点の記録であり、過去の呼出枠や承認待ちの記述を現在の実行許可として扱わない。
限定試験の成功とIssue全体の完了は区別する。

現状（2026-10-17）: **Gemmaの操作選択→ハーネスの修正・検証・実行・JSON出力が一連で成功**。6/15→15/15へ改善し、次の判断では「修正不要」を選択。別の2入力も実スクリプトの実行結果から正しいJSONを保存した。登録済み2操作・固定PUBLIC課題の限定試験。以前の自由回答によるスキル再利用試験の不合格は保持。累計102/102呼出で終了し元32Kへ復元。本番適用・独立評価・日次自動実行は未実施。[最新の改善試験結果](gemma-e4b-improvement-cycle.md)を参照。

Decision: [Issue #7](https://github.com/second-works/hermes-self-improvement/issues/7) は、固定公開revisionのHermes本体を隔離実行し、標準Skillsと標準Delegationで候補1件を作る方向へ変更する。2026-10-16のユーザー指示を反映した設計案。模擬worker中心の旧案と `codex login status` の提案は撤回し、実行していない。

Risk Tier: **HIGH**。実モデル通信、認証と生成候補の分離を扱う。

以下は累計35/40呼出時点の過去の経過要約。
後続試験の最新集計は冒頭とリンク先を参照する。

方針変更と既存Gemmaを使う実装開始は承認済み。省メモリ設定で64K起動・実Hermes初期化・実skills_listを検証済み。最大3試験を累計14呼出・781秒で終了し、最終試験は作成工程のモデル応答が90秒を超えて停止した。その後の時間延長試験では実子エージェントと標準skill_manageの作成要求まで到達したが、script生成中にswap停止。再開試験もswapが149.75MiB増えて停止した。この時点では累計35/40呼出、入力120385、出力予約26949トークン。生成・再利用のDoneは未達。元の32K・画像対応へ復元し、8081/8082のhealthとcontext32768、元plist hashを再確認した。[再開時の証拠](evidence/skill-delegation-resume.json)を参照。キャッシュとbatch縮小・累計60呼出案は、この時点では準備と無害な検証のみで、実行承認待ちだった。

branchは `issue-7-isolated-skill-delegation`、基準mainは `10419e1a49b62b28c6862102c7f08d8c9d03f4b2`。Issue #7はOPEN。依存PR #14/#13、直前PR #15のMergeを確認したが、過去の実験許可は流用しない。

## 公式資料と固定ソース

調査revisionは公開mainの `74e7a25c949625479487c009a2fd64d14d5b5c06`。本番revisionの推定ではない。公開ファイルは `/private/tmp/hermes-issue7-source-<SHA>/` へ調査用に保存し、実行・installしていない。Context7の公式IDは `/nousresearch/hermes-agent`。検索例より固定ソースを優先する。

| 機能 | 原文確認と今回使う責務 |
| --- | --- |
| `skills_list` / `skill_view` | [標準Skills](https://github.com/NousResearch/hermes-agent/blob/74e7a25c949625479487c009a2fd64d14d5b5c06/tools/skills_tool.py)。一覧、SKILL.md/supporting file読込。新sessionで同じskillを再読込して別のPUBLIC課題へ適用 |
| `skill_manage` | [標準管理tool](https://github.com/NousResearch/hermes-agent/blob/74e7a25c949625479487c009a2fd64d14d5b5c06/tools/skill_manager_tool.py#L768)。`create` / `patch` / `write_file`等。作成先は隔離HERMES_HOME配下 |
| `delegate_task` | [標準委任](https://github.com/NousResearch/hermes-agent/blob/74e7a25c949625479487c009a2fd64d14d5b5c06/tools/delegate_tool.py#L225)。実際の子AIAgentを生成。goal/contextを単一leafへ渡す。このrevisionのモデル向けschemaにはtoolsets/model/provider指定がなく、Context7の一部の例と異なる |
| 権限継承 | [子toolsets](https://github.com/NousResearch/hermes-agent/blob/74e7a25c949625479487c009a2fd64d14d5b5c06/tools/delegate_tool_toolsets.py)。親のtoolsets/disableを継承し、子のmemory/send_message/cron等を除く。tool制限だけをOS隔離と扱わない |
| 子の上限 | [設定](https://github.com/NousResearch/hermes-agent/blob/74e7a25c949625479487c009a2fd64d14d5b5c06/tools/delegate_tool_config.py#L85)。oneshot_max_children=1 / max_concurrent_children=1 / max_spawn_depth=1 / max_iterations=8を隔離configで固定。child_timeout_secondsは無活動時間の制限で、wall timeoutの代用にならない |
| HOME | [get_hermes_home](https://github.com/NousResearch/hermes-agent/blob/74e7a25c949625479487c009a2fd64d14d5b5c06/hermes_constants.py#L161)。HOME/HERMES_HOME/CODEX_HOMEをすべて新規隔離pathへ固定し、hostのroot/profileへfallbackさせない |
| OAuth | [Codex認証](https://github.com/NousResearch/hermes-agent/blob/74e7a25c949625479487c009a2fd64d14d5b5c06/hermes_cli/auth_codex.py)。Hermes自身のstoreに保存するが、既存CLI認証のimport経路もある。既存認証をmount/importしない |

確認時SHA-256: delegate_tool.py=`bf42067cacc5d8b42cf03ace7c424b5beec690f8b4e095402ad08640d215c3c9`、skills_tool.py=`a8f58c20bbe8fb42c7e765ba41dbf096183023a129c19bd2e0f0f623ce0ee8e1`、skill_manager_tool.py=`131d3720957659c37addd27430693d5d0b7dec0b5176a83b2bedad783b7edcd7`。実行前に全取得物・依存lockを別途固定する。

公式 [hermes-agent-skill-authoring](https://github.com/NousResearch/hermes-agent/blob/74e7a25c949625479487c009a2fd64d14d5b5c06/skills/software-development/hermes-agent-skill-authoring/SKILL.md) は、このrevisionではrepoに組み込むスキルの作法が対象で、個人用ローカルスキルはskill_manageを使うと明記する。監査proposalの参照文字列だけを根拠に必須起動しない。

## 最小実証

1. 制御側で専用PUBLIC課題・公開例・path・予算・基準SHA/hashを固定。隔離profileで対象skillが未登録であることを実skills_listと監査へ渡す検査済みsnapshotで確認する。抽象sampleのcapability=missingを実課題の証拠に流用しない。
2. 隔離Hermesの親が改善仕様を読み、実delegate_taskで子1件へ作成を委任。子がskill_manageでSKILL.mdとscripts/review.pyを作る。API/Delegationを模擬で置換しない。
3. 制御側が通常ファイル・path・byte数・展開/依存指定等を検査し、認証なし・networkなしの別コンテナで固定公開単体試験を実行。認証を持つprocessで候補scriptを実行しない。
4. 履歴を継がない新しいHermes sessionで、同じ検査済みskillをskills_list→skill_viewで読込み、別のPUBLIC課題へ適用。tool trace・保存file hash・結果を照合し、file存在だけを再利用成功としない。
5. 候補diff・単体/再利用結果・hash付き受渡しmanifestを記録。scriptは既存評価器のstdin JSON / stdout findings,cpu_seconds契約に合わせる。既存artifact path `fixtures/skills/github-code-review/review.py` に対応するdiffを出力し、元tracked fixtureはその時点で変更しない。

対象skill名はdelegated-patch-reviewの案。匿名patchから動的実行findingを返す小さな手順とscriptを作る。隔離profileで手順skillが未登録であることと、比較用基準scriptの存在を区別する。src/audit、src/evaluation、記録/hashの既存責務を再利用し、必要な接続だけを追加。Memory/session_searchの重複実装、DB/RAG、公式Self-Evolutionは追加しない。

候補・基準の完全commit SHAが揃う前はcandidate_commit_sha=null、handoff_status=PENDING_COMMIT。既存評価への登録に必要なcommitは検査済み差分の承認後。評価器のpath/schema/閾値を変更しない。hidden原本・正解・個別traceを生成者へ渡さず、hidden結果による再調整を行わない。独立評価PASSなしにAWAITING_APPROVALにしない。

## ローカルGemma接続の確認（2026-10-16）

ユーザーは対象機能を了承し、実装済みGemma E4Bを使用、接続方法は調査するよう指示した。外部モデルAPI/OAuthを初回に使わず、追加従量課金0 USD。既存モデルの停止/切替/設定変更は行わない。

接続調査でlocalhostの待受と以下のGETだけを実行した。最初のGET試行は自動承認レビューのtimeoutで未実行、一度の再試行が成功。prompt送信、推論POST、認証file読取、サービス操作は行っていない。

| 接続 | live確認 | 今回の位置付け |
| --- | --- | --- |
| http://127.0.0.1:8081/health | status=ok | llama-serverの状態確認 |
| http://127.0.0.1:8081/v1/models | id=gemma-4-e4b、meta.n_ctx=32768 | 初回Hermesの上流は8081/v1を案とする |
| http://127.0.0.1:8082/health | status=ok | 既存プロキシの状態確認 |
| http://127.0.0.1:8082/v1/models | id=gemma-4-e4b、meta.n_ctx=32768 | 初回は使わず、互換性に問題があれば補正内容を調べてから別判断 |

GETはAuthorizationなしで成功した。推論POSTの認証要否・応答・tool calling・速度・競合は未検証。モデルaliasとcontextはlive値だが、稼働中GGUFの完全hashやbuild revisionは未固定。repo内LaunchAgent設定例のファイル名をlive artifact identityとして流用しない。

Hermesの[標準custom endpoint](https://github.com/NousResearch/hermes-agent/blob/74e7a25c949625479487c009a2fd64d14d5b5c06/website/docs/integrations/providers.md)を使う設定案は次の通り。これは隔離環境用で、本番configへ書き込まない。API keyはローカル向けに空を指定できる公式契約だが、実client初期化を予備確認する。

```yaml
model:
  provider: custom
  default: gemma-4-e4b
  base_url: http://127.0.0.1:8081/v1
  api_key: ""
  context_length: 32768
  streaming: false
```

streaming=falseは固定ソースagent/agent_init.py:1239-1242の正式設定。まず非streamingで応答とtool引数を観測する。利用APIはPOST /v1/chat/completions。Docker内の127.0.0.1はホストとは異なるため、このURLをそのまま候補コンテナへ渡さない。Secretなしの限定中継でホスト側だけが8081へ送る案とし、候補の任意network、host filesystem、Docker socketへのアクセスを許可しない。到達性・宛先固定・予算停止のgateを実験前に確認する。別途OAuth認証brokerを作る必要はなく、既存中継案は呼出/token/timeを制御する最小の接続に限定する。

skill_viewは[preprocess](https://github.com/NousResearch/hermes-agent/blob/74e7a25c949625479487c009a2fd64d14d5b5c06/tools/skills_tool.py#L570)でinline shellや依存準備経路を持つため、skillsだけのallowlistでもOS隔離は省略しない。生成候補・親子runtimeにはSecretを渡さず、検査済みskillだけを再利用へ進める。実験は既存LLMの推論資源を使うため競合/timeout時停止とする。後述の明示承認済み一時64K試験だけをサービス再起動の例外とした。

## ローカルモデルの能力確認と失敗分類

小型モデルの成功を前提にしない。簡単な合成課題と最小tool集合で、実Hermesの標準tool呼出と結果解釈を先に確認する。予備確認もrun全体のcall/token/time上限に含め、通ったことを本実証の完了とは扱わない。同じ候補を無制限に作り直したり、tool結果を人間/制御側が代筆して成功に変えたりしない。

1. 接続/schema/context確認: 正常な応答、tool名/引数、応答長、usageを確認。通信失敗やtool未対応は基盤/互換性の停止として残す。
2. 最小の実tool確認: skills_list/skill_viewの結果を解釈できるかを確認。tool未呼出/不正引数/幻の成功報告はtool利用の失敗。
3. 本実証: 親の実delegate_task→子のskill_manage→公開単体試験→別session再利用。コード不備、手順不備、予算切れを別々に記録。

失敗はモデル一般の能力限界とは断定せず、このrevision・モデルhash・量子化・context・tool定義・有限課題・予算での結果とする。単純化した課題でも基準/期待値を後から緩めず、未達は未達として保持する。初回run終了後、モデル/設定の変更や次runは証拠を見て判断する。

## 提案上限と未決事項

| 項目 | 提案値・停止条件 |
| --- | --- |
| 回数 | run 1、子1、候補1、生成retry 0、深さ1。親8・子8・再利用4 iteration以下。2件目spawnを制御側でも拒否 |
| モデル呼出 | 親・子・再利用・補助・内部retry合計20 request。中継で送信前に予約して上限停止 |
| token | 1呼出入力16,384/出力4,096、run入力100,000/出力20,000以下の案。実token計測と最大費用予約が確定不能なら呼ばない |
| 費用 | 追加従量課金0 USDがローカル方針。外部モデルAPI/OAuthは初回不使用。外部モデルへ変更する場合はprovider/モデル/単価・上限の別承認 |
| 時間 | wall全体20分、子開始通知から5分、model呼出90秒、単体処理30秒。外部監視で子の超過時は親子コンテナ全体を停止。開始通知なしも成功にしない。準備/認証は別工程の上限を固定 |
| retry | agent.api_max_retries=1（単発）、agent.auto_recovery_cycles=0、fallbackなしの案。SDK/stream/補助呼出も中継で集計。不明なら停止。output_schemaによる子の自動修正retryを使わない |
| tool | 親skills/delegation、子は継承されたskillsを想定。実定義を照合。terminal/file/web/MCP/GitHub/cron/Memoryを渡さない |
| OS境界 | 非root、root/source read-only、cap-drop ALL、no-new-privileges、seccomp。親子は中継以外network拒否、候補試験はnetwork全面拒否 |
| 資源 | CPU 1、memory 1GiB、swap 0、pids 64、tmpfs 128MiB。既存Dockerと他コンテナを確認し、競合時停止。他サービスを自動停止しない |
| 入出力 | 課題JSON 64KiB以下、SKILL.md/scripts/review.pyだけ計128KiB以下、stdout/stderr計1MiBで停止、監査run 20MiB以下 |
| 分類 | 課題/候補/公開集計は検査済みPUBLIC。ローカル初回はSecret不要。hiddenは既存評価者のINTERNAL |
| 保存 | 新規runs/delegation-unique-idに合成成果物と検査済み証拠。認証fileを作成/保存しない。旧run/logを保持し自動削除しない |

取得先は固定GitHub source・承認済み公式registry/PyPIだけの案。準備実行前にimage digest、依存hash lock、byte上限、取得先allowlistを具体化する。モデル送信先はhost側127.0.0.1:8081のchat-completions経路だけに限定する案。実験前に中継の到達性と拒否gateを確定する。

## 検証と終了条件

実モデル実験前に、無害な拒否probeで合成canary/hidden/socket未mount、network/中継宛先制限、非root、read-only、資源、出力、子開始通知付きtimeoutと停止回収を確認。中継の認証非露出と上限も無害fixtureで先行確認。未確認なら本体を起動しない。

実Hermes親子のtool trace、候補作成、公開単体試験、別session再利用、diff/hash受渡しを全て必須とする。認証失敗・schema違反・上限・子未起動/iteration切れ・tool未呼出・回収不明はSTOPPEDと理由を保存し、自動再開しない。模擬試験/help/stdout成功文だけでは完了にしない。

追加試験、標準verify、Bash5 Security、全差分self-review成功後だけcommit/提出承認へ進む。既存固定検証入口/CI/setup試験を変更しない。同一head CI/Security/CodeQL/Codex Review、人間Mergeを維持する。

本番 ~/.hermes、設定・venv・認証・会話・サービスは読取/変更/起動しない。現在は公開資料の読取と設計更新だけ。認証アクセス、本体起動、依存install、Docker実験、モデル通信、commit/push、Issue更新は未実施。

調査文書のローカルLLM圧縮は結果未取得で打ち切り、判断に使用していない。原文の該当箇所を直接確認した。設計案更新時の標準verifyは30 testsとlint成功、typecheck/buildは既存入口未設定の理由付きskip。実Hermes・隔離・モデル通信の成功証拠ではない。

## Issue #7本文の変更案（未送信）

- タイトル: feat: Hermes標準Skills・Delegationによる隔離候補作成と再利用
- Goal: 監査で確認したテスト用不足スキル1件に対し、固定公開revisionのHermes本体を隔離実行し、標準Skillsと単一子Delegationで候補作成と再利用を実証する。
- Scope / Boundaries: 親の仕様→実delegate_task→skill_manage作成→認証なし隔離単体試験→新sessionのskills_list/skill_viewと再利用→diff/成果物→既存独立評価へ受渡し。Risk HIGH。検査済みPUBLIC合成入力のみ。モデル・認証・送信先・予算を実行前に承認。
- Non-goals: 本番アクセス/適用、公式Self-Evolution採用、追加DB/RAG、Memory/session_search再実装、定期化、模擬workerだけの完了、評価閾値/固定Gate変更、Auto-Merge。
- Done: 実Hermesの標準toolと単一子の実作業、公開単体試験、別session再利用が成功。仕様・候補・環境・diff・公開結果をhash固定し既存評価へ渡せる。認証不能/予算/timeout/権限逸脱は証拠を残して明示停止し、承認前に本番を変えない。
- Verification: 隔離/中継拒否試験、認証不能停止、子上限、path/出力/timeout、実親子trace/成果物、別session再利用、既存監査/評価回帰、標準verify、Security、同一head CI/CodeQL/Codex Review。未確認は成功扱いしない。
- Dependencies: 監査PR #14、評価PR #13。具体的実験・モデル・認証・予算の人間承認。本文反映もこの具体案への承認後。

## 実装開始後の記録と現在の停止点

2026-10-16、ユーザーが「実装開始して下さい」と指示した。設計案の範囲でsrc/delegation、専用CLI、PUBLIC worker/fixture、追加契約試験を実装。標準Skills/Delegationを本物のAIAgentへ接続し、制御側は予算・policy・成果物・隔離を担当する。生成Markdownのinline shell/依存指定は、モデル応答が実toolへ渡る前にも検査し、危険な候補をskill_viewで展開しない。

入口は `python3 -I -B scripts/delegate_skill.py prepare|check|run --preparation runs/delegation-prepare-74e7a25c9496-3`。prepareは既存記録を上書きせず、再利用wheelは `--wheels` の明示指定と固定lock hash一致を要求する。checkは拒否gateと本体の初期化、runだけがその後のcapability→委任→単体試験→新session再利用へ進む。現状のrun実行はcontext不一致で停止する。

固定公開sourceは2,384 file / 49,893,579 bytes。初回archive取得は429で失敗し、同じSHAを認証helperなしのGit sparse取得へ切替えた。wheelは54件 / 20,067,723 bytesを公開PyPIから取得してhash lockを作成し、networkなしで導入した。準備だけの永続保存上限は既存spikeの2GiB、source上限64MiB、wheel総量検査512MiB、単一wheel100MiB、ライブラリhash検査8MiBとする。監査runの20MiBとは分け、モデル側へこの準備directory全体やGit DBを渡さない。

初回の準備はDocker接続不可でSTOPPED、次は導入後のライブラリが2MiB hash上限に掛かってSTOPPED。どちらの原本も保持し、PUBLICネイティブライブラリ用hash上限を8MiBへ分けたうえで、新しい準備先へ固定hash wheelをオフライン導入した。準備成功はHermes実証の成功と区別する。

32Kでの実証原本は `runs/delegation-20261016T092509Z-0c0fa7364d0f/`、検査済み抜粋は [stage1 evidence](evidence/skill-delegation-stage1.json)。同じ制御source hashで実Dockerの7分類拒否gateと停止回収が成功。モデル一覧の実値32,768に対し、固定Hermesのagent/model_metadata.pyがMINIMUM_CONTEXT_LENGTH=64_000を要求するため、`RUNTIME_CONTEXT_UNSUPPORTED` でSTOPPED。最初の2回は本物のAIAgent初期化でも同じValueErrorを確認した。最終版はこの不一致をconstructor前に明示停止する。推論呼出0、子0、候補0。本体初期化・実委任・生成・再利用・独立評価受渡しは未達。

監査側が固定する公開revision f97608f178d1ffeca59860195ab7da295f7c8e5fのagent/model_metadata.pyでも64,000の下限を確認した。この2 revisionだけから旧版全体の32K可否を断定しない。公開v0.21.5 tagの照会は取得できず、本番のrevisionを推定しない。

専用監査fixtureは既存auditの固定revision/分類契約を保持した合成診断例で、実行revisionの棚卸しやモデル認証の観測ではない。診断側のapi_calls=0を候補実行の許可へ変換せず、人間指示と別の実行仕様へproposal hashを結び付ける。実際のskills_listによる不足確認は本体初期化後の工程として残る。

次の判断は、(A) 本番から独立した64K以上のGemma検証instanceを用意するか、(B) 既存Gemmaを64K以上へ変更するか。Aは追加RAM/ポート/実行資源と停止回収の具体化・承認が必要。Bは既存サービスの再起動と他用途への影響があり、本番設定変更の明示承認が必要。contextを64Kと偽装、Hermesの下限削除、別providerを装う迂回、無承認のモデル切替は行わない。現在の32Kサービスは変更していない。

ローカル検証: 追加18 / 監査15 / 評価34 / 既存spike14 / 標準30、計111 tests成功。標準lint成功、typecheck/buildは既存入口未設定の理由付きskip。stageした新規コード・lock・PUBLIC証拠のSecurityはSECURITY_PASSED。依存脆弱性監査は対応manifestなしでSECURITY_NOT_APPLICABLEであり、54 wheelに脆弱性がないという証明ではない。self-reviewで空directory symlinkがtree commitmentから漏れる点を修正し、拒否の回帰試験と新しいsource hashでの7分類gate/明示停止を再確認した。未達の実生成を模擬workerで置換していない。

### 一時64K試験の承認範囲と結果

既存モデルの現行process引数から、Gemma用binary、GGUF、alias、context=32768を確認した。MacのRAMは16GiB、swap使用量は6,756.94MiB。追加Gemmaを並行起動する案は採らず、次の一時変更を人間判断へ提示する。これはGemma提供サービスの変更であり、Hermes本番へのアクセス承認ではない。

- 対象: localhost:8081を提供する既存Gemma E4Bのcontextだけを `32768 → 65536` へ一時変更。同じbinary・model・draft・aliasを保持。設定元の特定、当該LaunchAgent設定の読取・hash付きバックアップ、変更diffの照合を実行前の必須工程とする。認証値や本番Hermesは読まない。
- 影響: Gemmaの開始時と復元時に各1回再起動するため、8082や他の既存利用者への推論提供が一時中断する。64K化によるRAM増加量は未検証。新しいモデルや外部APIは使わない。
- 実証: 隔離Hermesのみ、PUBLIC合成課題、親/子/再利用等の全体で最大20推論呼出・20分・入力100,000/出力20,000tokens、追加API費用0。候補の本番適用は含めない。
- 起動/復元: 各60秒以内でhealth・model ID・実contextを確認。起動不能、swapが開始前より32MiB増加、memory pressure異常、予算超過、隔離異常なら実証を止める。メモリ監視の実装/無害試験も開始前に必要。
- 終了: 成功/失敗を問わず、元の設定hashとcontext=32768へ1回復元しhealth/model IDを確認。復元失敗は追加の自動再起動をせず、停止理由・対象を保持して人間へ戻す。他サービスの設定変更・再起動や既存run/log削除は含めない。

この範囲は「了承します」と、その後の「承認済みのGemma 64K試験を先に継続する」で承認された。2026-10-16の実行 `runs/context64-20261016T141058Z/` は起動中にswapが6,610.25→6,945.38MiB（+335.13MiB）へ増えたため、32MiB上限でSTOPPED / SWAP_GROWTH。memory freeは31→20%。起動完了確認前に停止し、Hermes起動・推論・委任へ進んでいない。元のplistは変更せず、元設定をloadして32K復元を検証した。8081/8082ともhealth=ok、model=gemma-4-e4b、n_ctx=32768、元plist SHA-256一致。再試行は行っていない。PUBLIC抜粋は [64K試験証拠](evidence/skill-delegation-context64.json)。24件の委任・復元境界テスト成功。commit/push/Issue更新/PR作成は未実施。

この結果は現在の資源状態における起動停止の証拠であり、Gemmaのskill能力の不合格ではない。Codex OAuthは構成選択の回答だけを受領しており、隔離ログイン・認証読取・通信は未承認かつ未実行。次の方式へ自動で切り替えない。

### 2026-10-17 再承認後の再試験

Xcode作業終了後、起動中のSimulator/デバッガがなく、swap=3,454.81MiB、5秒観測のswap増加なしを確認した。前回と同じ停止条件・32K復元での再試験を提示し「お願いします」で再承認を受け、一度実行した。14:47 JSTの `runs/context64-20261017T054712Z/` は64K起動中にswapが3,454.81→3,647.44MiB（+192.63MiB）、memory free指標が64→17%になり、SWAP_GROWTHで停止した。64Kの準備完了確認前で、controller開始・モデル推論・子委任・候補生成はいずれも0。元の32K、設定hash一致、8081/8082ともhealth=ok/model=gemma-4-e4b/n_ctx=32768への復元を確認した。追加の再試行は行わない。検査済みPUBLIC抜粋は [再試験証拠](evidence/skill-delegation-context64-retry.json)。この停止は現行設定と承認されたswap上限での結果であり、16GBで64Kが絶対に動かないことや、Gemmaのskill能力の不合格を証明するものではない。

### 2026-10-17 省メモリ設定での試験

KVをq8_0へ変更、Flash Attention=on、batch=512/ubatch=128、画像projectorを一時無効にする具体案を提示し、「では再度テストお願いします」で承認を得た。同じbinary・主/補助モデル・MTP・並列数1を保持し、提示済み一時plist hash=41f8f669acedbf0a90d861765ed0e178d7a6cf0a79653ccb15ea9171eeb6342eとの一致を起動前に必須検査した。起動/停止/復元条件は前回と同じ。

14:54 JSTの `runs/context64-20261017T055425Z/` では64K起動に成功し、実Hermes初期化とDockerの7分類拒否gateにも成功した。実行中の監視では資源上限停止は発生せず、開始swap=5,316.38MiB、最終監視swap=5,055.69MiB。開始時/最終監視値だけからピーク削減量や64Kでの推論安定性を断定しない。実原本 `runs/delegation-20261017T055431Z-6da6847635cb/` は最初のcapability要求でREQUEST_SCHEMA停止、推論0・候補0。終了後の32K/画像対応設定復元、元plist hash一致、8081/8082正常応答を確認した。証拠は [省メモリ試験](evidence/skill-delegation-context64-memory.json)。

停止理由はHermesが実際に付与したreasoning_effort=mediumを中継allowlistが扱っていなかったこと。Gemma通信なし・合成64Kメタデータを使った別のDocker通信検査で実要求を捕捉し、mediumだけ明示許可する境界変換へ修正した。未知値・不正型・送信先変更は拒否を維持。実Hermes要求のオフライン正規化検査と関連26テストで検証し、推論成功とは区別する。この一度の本番サービス試験終了後は追加の再起動を行っていない。スキル作成・再利用・独立評価は未達。

### 2026-10-17 要求形式修正後の実通信と計数診断

「了解しました。続けてください」で再承認を受け、省メモリ64K試験を一度実行した。14:58 JSTの `runs/context64-20261017T055838Z/` は64K起動、実Hermes初期化、7分類拒否gateに成功した。capabilityで推論要求を1回送信したがUSAGE_UNVERIFIEDで停止した。失敗時reportのinput=2,835/output=4,096は事前予約値であり、実使用量として報告しない。旧版は不一致時の実usageを保存しておらず、この応答の不一致数値は未確認。終了時の元32K・画像対応設定hash・8081/8082正常応答を検証した。

承認済み20呼出/20分の通信予算内で、復元済み32KへPUBLIC診断入力「Reply OK.」を出力1token・追加1回だけ送り、再起動なしで計数比較した。特殊tokenなし=11、あり=12、実usage.prompt_tokens=12、completion_tokens=1。診断のfinish_reason=lengthは1token上限によるもので、能力評価の成功として扱わない。swapは診断前後5,674MiBで変化なし。合計推論要求2回。

この観測に合わせ事前tokenizeのadd_specialをtrueへ修正し、回帰試験を追加した。不一致の許容や予算の増加は行わず、今後は失敗時にも数値だけのusage観測を保存する。実Hermes隔離試験の元応答が残っていないため、この1token差だけを元停止の確定原因とは断定しない。関連27テストが成功。修正後の実Hermes推論・スキル生成・再利用は未検証。証拠は [計数診断](evidence/skill-delegation-context64-accounting.json)。

### 2026-10-17 承認された最大3試験の集計

ユーザーの「テスト進めてください」で、同じ省メモリ設定・最大3試験・合計20呼出/20分・各回32K復元を承認として実行した。1回目は4呼出で通信停止、2回目は短い委任指示へ修正し累計8呼出で通信停止、3回目は委任内容を80語以内と明示し累計14呼出でMODEL_TIMEOUT停止した。最終試験の診断はcompletion stage / 90.008秒。モデル応答の計数一致は検証できたが、長い生成は完了せず、スキル作成・新session再利用・独立評価のDoneは未達。

後続試験には失敗要求の最大出力予約も含め、前回のcalls/input/outputを引き継いだ。全体期限は06:25:15 UTC（15:25:15 JST）で固定し、復元60秒分を先に確保した。全3試験の開始から最終復元まで781秒、累計入力予約52,111/100,000、出力予約12,501/20,000、呼出14/20で終了した。出力予約を実際の生成token数として扱わない。3回とも64K起動、Hermes初期化、実skills_list、7分類隔離gateが成功し、メモリによる停止はなかった。終了後は元plist hash・32K・8081/8082正常応答、実行中Dockerコンテナ0を確認した。

失敗したcreate phaseでは従来のpipe実装が例外前のtool/child eventを保存していなかったため、子の成功や候補未作成を推測しない。exportされた候補は0、生成・委任成功はNOT_VERIFIED。今後の失敗時にもbounded eventを残す修正を加え、例外前のchild event保持を回帰試験で確認した。この修正後の追加モデル通信・再起動は行っていない。最終関連30テスト、標準30テストを確認し、同条件の4回目は実施しない。PUBLIC証拠は [3試験集計](evidence/skill-delegation-three-trials.json)。

### 応答時間を延長する継続試験の承認

ユーザーの「時間を伸ばしながら、作成されるまでテスト」「試行過程を結果報告しながら」で、同じ省メモリGemmaを使う応答時間の段階延長を承認として扱う。request timeoutを180→300→600秒、子wall/idle timeoutを各requestの3倍（最大1,800秒）へ設定可能にした。全体は新しい実行枠で60分、呼出20回・入力100,000/出力20,000予約・各request入力16,384/出力4,096を維持し、失敗予約も後続へ引き継ぐ。開始時に40呼出と案内した点は20呼出維持へ訂正した。startup/restore各60秒、swap増32MiB、memory free指標10%未満停止、隔離・tool allowlist・候補検査・元32K復元は維持する。

requestのブロッキング中にも子wall期限を優先し、全体の復元60秒を先に確保する。progress.jsonlはrequest開始/完了/失敗、tool/子イベントの公開メタデータだけを逐次保存し、モデルの内部推論やraw promptを進捗ログへ出さない。待ち時間延長を能力評価の成功や本番適用の承認に変換しない。

### 時間延長後の3試行と呼出枠の確認

180秒設定で3試行を行い、いずれも実delegate_taskと子起動が確認できた。停止理由は順にSKILL_METADATA、SKILL_WRITE_BOUNDARY、SKILL_WRITE_BOUNDARYで、今回の停止は時間切れではない。2試行目の隔離された拒否内容にはcategory追加と仮実装、3試行目にはcreate操作へのfile_path混在があり、保存前に制御側で拒否した。ヘッダーと機能仕様は3試行目で正しく含まれた。未実行の生成内容を成功として採用しない。

累計18/20呼出、入力予約68,518/100,000、出力予約13,200/20,000。失敗分も予約を保持し、各試行後は元32Kへ復元済み。親が子へ渡す指示を、正しいcreate/write_fileの具体的引数例と実装要件へ整理した。実Hermes標準skill_manageへ同じ操作例を送るモデルなしDocker合成検査では、create/write_fileとファイル内容照合が成功した。これはモデル生成の成功ではない。証拠は [時間延長後の試行](evidence/skill-delegation-extended-time.json)。

残りの全体期限内で累計40呼出・入力200,000/出力40,000へ拡張する具体案をユーザーへ確認中。既定20回の境界は維持し、extended profileはテスト用に準備しただけで未使用。メモリ・権限・保存前検査は拡張しない。モデルを使う追加試験は回答まで行わない。

### 累計40呼出への拡張承認とツール定義の整合

ユーザーの「承認します」で、同じ全体期限内・累計40呼出・入力200,000/出力40,000への拡張を承認として有効化した。使用済み18回と予約を引き継いだ第4試行は累計24回でCHILD_LIMIT停止。1回の試行で2回目の委任要求が出たため拒否し、子の成功とは扱わない。

モデルに提示するskill_manage/delegate_taskの引数定義を、制御側が既に許可しているcreate/write_fileと単一goal/contextへ絞った。実Hermesのtool handlerは変更せず、候補検査・child数検査も維持する。隔離Dockerのjsonschema検査で正しい3ケースが元schemaと制限定義の両方に適合し、過去に混在したcreate/file_path、create/category、複数tasksの3ケースを制限定義が拒否することを確認した。modelのtool引数だけを別のサイズ制限付きtraceへ保存し、内部推論を保存せずに委任失敗を検証可能にした。標準機能の成功をこの合成schema検査だけで主張しない。

## Xcode終了後の再試験（2026-10-17）

残存xcodebuildをユーザー指示で通常終了し、承認済み省メモリ64K設定・300秒・累計40呼出上限で再試験。swap2825.62→3054.06MiB（+228.44）で停止し、累計39呼出・入力129441・出力予約31069となった。Xcode終了だけでは解消せず、原因は未特定。元32K・画像対応、元plist hash、両ポートhealth、実行中コンテナ0件を確認した。ユーザーのリセット提案を受け停止中。Mac再起動と新たな試験予算は実行していない。詳細は[試験証拠](evidence/skill-delegation-post-xcode.json)。

## Mac再起動後の試験（2026-10-17）

再起動直後のswap0MiBとXcode不在を確認し、明示許可でDocker Desktopを起動した。起動後の試験開始時swapは303.69MiBであり、推論開始まで0を維持したわけではない。累計60呼出・入力30万／出力6万・20:35:13 JST期限を新規承認し、従来の64K省メモリ設定だけで3試行。全試行でswap停止・モデル時間切れはなく、WORKER_PIPE_CLOSED、SKILL_FRONTMATTER、CHILD_LIMITで停止した。親完了後も実子の完了イベントを期限内で待つ修正と、既定Markdownのschema明示を追加。最終累計59/60呼出、候補完成・再利用・独立評価は未達。原因をメモリ問題だけに帰属しない。詳細は[再起動後の証拠](evidence/skill-delegation-post-reboot.json)。

## 実候補2件の生成と品質不合格（2026-10-17）

累計80呼出の拡張承認後、入れ子JSONを除いた指示で実親→実子→標準skill_manageが完了し、SKILL.mdとscripts/review.pyを2試行とも保存できた。1件目は公開6件中4件合格、コメント誤検出と文脈行番号で失敗。公開の失敗内容を反映した2件目は6件中3件合格で、追加行prefix・rule名・AST処理等の契約違反が残った。両試行ともモデル300秒timeoutやswap停止はなく、待ち時間だけの問題ではない。候補・hash・traceを保存し、再利用と独立評価、本番適用は行っていない。累計74/80呼出、入力220722、出力予約44813、残り6呼出は未使用。元32Kへの復元を確認し、同じ再生成を重ねず停止した。[生成結果の証拠](evidence/skill-delegation-created-candidates.json)を参照。

## 既存候補への限定修正試験（2026-10-17）

ユーザー承認の最大2回を実行。4/6候補をhash照合して隔離HOMEへ投入し、Gemmaが標準skill_viewで読み、skill_manageで変更した。コメント誤検出の修正は5/6へ改善し、既存4件の合格を維持。次の行番号修正では無関係な正規表現も変更し、実行時エラーを握り潰して5ケースでJSONを返さず、全6件の追加確認では1/6に退行した。新規モデル通信なしで全6件を確認し、候補・出力hashを保存。最良5/6候補を保持し、再利用・独立評価・本番適用は実施せず停止。累計80/80呼出、入力240863、出力予約46413。最大2回の結果は[限定修正の証拠](evidence/skill-delegation-bounded-repair.json)を参照。

## 差分限定2案の試験（2026-10-17）

候補全文の書き換えを禁止し、行番号カウンターの2種類の挿入のみを制御側で許可した。モデルにはread-only toolsだけを提示し、実行境界でも書き込み・委任を拒否する。関連45テスト・標準30テスト・Security検査を実施。制御用候補は既存6件＋追加3件の9/9に合格したが、これはGemma生成ではない。モデル第1案はコメントの挿入でPATCH_REJECTED、第2案はskill_viewを実行せずPATCH_READ_ONLY_UNVERIFIEDとなり差分内容は未評価。プロンプトにもソースを与えていたため、後者を生成コードの不正と断定しない。実候補へ適用した差分は0。2案上限により停止し、5/6の候補を保持。累計84/88呼出、入力254678、出力予約46576。元32Kへ復元し、再利用・独立評価・本番適用は未実施。

## 直接ソース入力の差分2案（2026-10-17）

ユーザー承認でskill_view必須条件を除去。制御側がhash照合した全文と行番号をモデルへ直接渡し、モデルAPIからtool定義を除去し、予期しないtool呼出も実行前に拒否した。第1案はJSON閉じ括弧不足とコメント/continue挿入、第2案はMarkdownコード枠と範囲外のafter_line52挿入のため拒否。第2案のコード枠を除いたオフライン検査でもPATCH_OUTSIDE_SCOPEとなったが、実適用のための正規化は行っていない。両案とも入力hashの確認に成功し、以前の読み込み証拠条件では止まっていない。差分適用0件、元候補保持、再利用・独立評価・本番適用は未実施。累計86/88呼出、入力260376、出力予約46682。関連46テスト・標準30テスト・Security検査は通過。
