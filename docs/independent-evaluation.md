# 独立fixture評価

Decision: 匿名のgithub-code-review fixtureで基準版・候補1件・劣化版を比較し、独立した制御側がPASS / FAIL / HOLDを判定する。実Hermes、実LLM、本番品質の判定には使わない。

対象: [Issue #5](https://github.com/second-works/hermes-self-improvement/issues/5)。Risk Tier: **HIGH**（候補実行・隔離・hidden評価と採否判定の安全境界）。2026-10-15、ユーザーがこのチャットで隔離・評価案に基づく実装、既存Docker起動、公式Python image取得、無害な拒否試験と成功後のfixture評価を承認した。GitHub書込・push・PR提出、workflow/固定検証資産変更、Merge、本番・API利用は承認に含めない。

## 何を保証するか

公開10件と評価者専用hidden10件を候補生成前に固定する。期待findingのpath / line / rule集合の完全一致を採点し、回帰0、hidden正答+1件以上、失敗率増加0、安全試験全件成功、起動込みwall time median比1.2以下、費用比1.2以下でPASSとする。基準費用0なら候補も0が必要。基準と同一は改善不足のHOLD、劣化版はFAILとなることをcontrolとして確認する。

同じ入力を各版3回実行し、各ケースmedianの全ケースmedianで時間を比較する。品質の非決定性、指標欠如、サンプル不足、未知の環境、hidden汚染はHOLD。既知の安全違反・回帰・上限超過はFAILを優先する。閾値は[policy](../fixtures/evaluation/policy.json)に固定し、一般品質の統計的有意差を表さない。

推論/APIを使わず、呼出・token・API費用は0、`inference=not_applicable`。workerのCPU時間は自己申告値として内部記録し、独立したwall timeやAPI費用の証拠に代用しない。静的な有限fixtureの機能確認であり、実LLMの性能・推論費用は未検証。

`permission_violations`は成功した権限逸脱の観測件数を表す。拒否probeで制御を実証した構成では0を記録するが、候補の全syscall試行を監視する監査機能はない。拒否された試行の全件数を0と断定する指標ではない。未検知のkernel脆弱性への保証にも使わない。

## 実行順序

Docker Desktopが起動済みで、linux/arm64、cgroup v2とCPU/memory/pids制限が必要。他コンテナが稼働していれば停止し、それを自動停止しない。既存本番サービスにも操作しない。Docker資源の共存可否は起動後の確認事項であり、CLIの存在だけでは保証しない。

以下はrepo rootで、承認済みの操作者が順に実行する。Python標準ライブラリのみ使用し、package installなし。`RUN_ID`と完全な40桁SHAは実際の値に置き換える。

```bash
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin python3 -I -B scripts/evaluate_fixture.py bootstrap
python3 -I -B scripts/evaluate_fixture.py gate RUN_ID
python3 -I -B tests/test_evaluation.py -v
./scripts/verify.sh
/opt/homebrew/bin/bash scripts/security-preflight.sh .
# self-review成功後、評価器と基準fixtureをIssue branchへcommit（pushしない）
python3 -I -B scripts/evaluate_fixture.py freeze RUN_ID
# 公開fixtureだけで候補を作成し、標準検証・Security・self-review後に別commit
python3 -I -B scripts/evaluate_fixture.py evaluate RUN_ID --baseline-sha BASELINE_SHA --candidate-sha CANDIDATE_SHA
python3 -I -B scripts/evaluate_fixture.py audit RUN_ID
```

`bootstrap`だけがDocker Official Image `docker.io/library/python:3.12-slim-bookworm`を取得し、linux/arm64のlocal image ID / registry digest / byte数とdaemon環境を保存する。候補実行はID指定、pull禁止、networkなし。DockerはcontrolのローカルUnix socketだけを使い、空のDocker configと限定envでcredential helper・remote daemon設定の継承を防ぐ。image取得先のTLS/CDNと匿名registry認証はDockerの通常の公開image取得経路であり、モデルAPIや評価入力を送る経路ではない。

`gate`は空HOME、非root、capabilityなし、no-new-privileges、seccomp、read-only root/fixture、未mountの合成canary/hidden/socketの不在、network拒否を検査する。CPU 1 / memory 256MiB / swap 0 / pids 32 / tmpfs 16MiBの設定と制限動作、timeoutと子process停止、出力上限を実証する。probeは固定した無害コードだけで、本番パス・Secretを試し読みしない。失敗・未実施なら候補を実行しない。

候補はUID/GID 65532。mountは通常ファイル1つだけread-only、入力はstdin。write可能なホスト共有ディレクトリなし、HOME/TMPDIRは16MiBのrun専用tmpfs。stdout/stderrは合計1MiBで停止、JSONは256KiB、Docker log driverはnone。各処理30秒、全体20分、コンテナは逐次実行。管理下の一時コンテナだけ、停止実体確認後に除去し、imageや監査原本は削除しない。停止確認不能は隔離異常で後続実行禁止。tmpfsは暗号化・永続化防止やkernel脆弱性への完全防御を保証しない。

## hiddenと版の固定

`freeze`はcommit済みの評価器・基準artifactを照合し、公開/hidden dataset、閾値、環境、source hashをmanifestとイベント連鎖に固定する。その後だけ候補を作成する。公開ケースは固定した匿名値、hiddenは同じ事前固定カテゴリから未知のpath/lineを生成し、seed識別子とdataset commitmentだけ公開する。カテゴリ生成規則は公開、個別hidden入力・正解はINTERNAL。暗号学的なblindnessや人間管理者からの読取隔離を主張しない。

候補生成者にhidden本体・正解・個別traceを渡さず、評価時に各patchだけ実行コンテナへ入力する。候補artifactは変更不能なcommitから抽出し、候補の中に評価データをmountしない。候補生成者がhiddenを読んで候補を修正した場合はHOLDで当該runを失効させる。この運用上の独立性は、ホスト管理者自身の読取権限を防ぐOS保証ではない。同一hiddenで再調整せず、新しい候補は新しいrun・hidden・人間判断を必要とする。

基準/候補は完全Git commit SHAとartifact SHA-256を別に保存する。候補は基準の子孫で、同じartifact pathの別commit・別内容が必須。元HEADだけを未commit artifactの版として記録しない。評価器・環境・dataset変更でgate/manifestは失効する。`evaluation-lock.json`は排他的に作成し、完了・失敗後とも自動再実行しない。生存不明のlockを削除して再開しない。

## 出力と監査

`runs/<run_id>/`はGit管理外。manifest、environment、gate、baseline/candidate/degraded artifact、JSON/[schema](../schemas/evaluation-report.schema.json)、日本語report、イベント連鎖、checkpointを保持する。候補にこのrootをmountしない。制御側の固定サイズ・件数と出力上限で、run保存量を20MiB以内に限定する。外部入力を自由文のログとして保存しない。

`report.json`と`report.md`は集計だけ。hidden入力・正解・個別結果はGit管理外のINTERNALとして保持し、候補生成・GitHub・Memoryに渡さない。PUBLIC集計の公開も提出承認後。原データ最低30日、監査最低90日を保持し、自動削除しない。

`audit`は元のmanifest/dataset/環境/gate、イベント全連鎖と完了状態、lock、両SHAのartifact、report/private metricsのhashを照合する。原本欠如・改変・末尾欠落は成功にしない。連鎖と全原本を同時改変できる主体にhashだけでは対抗できず、checkpointを別の検査済み記録へ固定する。PASSはAWAITING_APPROVALまでであり、Mergeや採用とは別。

## 検証責務と現在の状態

純粋な採点・判定、schema境界、symlink・特殊ファイル、出力・timeout、監査欠損/改変は`tests/test_evaluation.py`、実Dockerの拒否・資源・fixture接続は`gate`と`evaluate`が担当する。標準入口・既存テスト・CI/Security/CodeQLを置換しない。既存の固定検証資産は変更せず、新試験は明示コマンドで実行する。CI組込みが必要なら具体差分・保証を示して別確認する。

2026-10-16時点で新規単体・境界試験34件（模擬transportの接続検査を含む）が成功。標準検証の既存30件とlintも直前stageで成功し、typecheck/buildは既存の未構成による理由付きskip。同stageのローカルSecurityはSECURITY_PASSED、依存manifestなしのためDEPENDENCY_STATUS=SECURITY_NOT_APPLICABLE。最終stage後にも同じ検査を行う。

Dockerの保存先変更はユーザーが実施し、`/Volumes/HD-ADU3/Docker/DockerDesktop/Docker.raw`とdaemon接続を確認した。旧バックアップは外部ディスクのBackups/Docker配下に保持し、復元・全量読取・削除はしていない。画面操作ツールのロック判定と設定ファイルの読取制限は解消を確認していないが、設定完了の人間報告と外部imageの存在を確認して再開した。

実Dockerの7分類gateが初回runで成功。監査の停止理由保存を補強したため、`evaluation-20261015T111545Z-ccaf749b4602` で新しいsource hashのgateを再検証する。Python 3.12.15 / Docker 29.2.1 / Linux 6.12.76-linuxkit / arm64 / cgroup v2。image IDは `sha256:eb7d16fec874f15b584063275012ac719885a2b87574d124c0da9c156d504629`、registry digestは `python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258`、156,922,204 bytes。実行制限値は上記を維持する。

現在は評価器と基準版をcommitし、hidden/manifestを固定する前の段階。候補の作成・比較、PRのCI/Security/Codex Reviewは未実施であり成功と扱わない。GitHub書込・push・PR作成は別承認、Mergeは人間判断を維持する。

## PR #13のレビュー修正

Codex Reviewが、docker createのdaemon側成功後に応答が失われるとcleanupを飛ばすP2を指摘した。停止・後片付けの保証に関わるためBLOCKING P2と分類。追加した2件の模擬障害テストは修正前fail、修正後pass。createの試行前に名前を固定し、応答に関わらず名前で照会・停止・削除・消失確認する。daemon不達や名前の同一性不明はsandboxを無効化し、createの応答不明時も後続起動を禁止する。通常の成功経路でも削除後の消失を確認する。

評価器のsource hashが変わるため旧runを新headの成功に流用しない。基準fixtureを元と同じartifactへ戻したcommitで新しいgateとmanifestを固定し、新hiddenで、元と同じ候補artifactを再登録して比較する。閾値・dataset生成規則・候補ロジックは変えず、候補の種類は1件のまま。旧run/hidden原本は保持して再利用しない。新run・両SHA・checkpointはPRに記録する。

再レビューでは、同一findingの成功回・失敗回が混在すると不安定性を検知できないP2もBLOCKINGと分類した。hiddenの安全ケースで基準が1回だけ失敗し、全回の正規化findingが[]になる再現テストは修正前PASS（期待HOLD）でfail、修正後HOLDでpass。反復の一致判定へfinding hashと失敗状態の組を使い、混在時はEVALUATION_CONTAMINATEDとしてHOLDにする。head変更に伴い、新しいgate・manifest・hiddenで同じ基準と候補を再検証し、旧結果は流用しない。

追加レビューでは、create応答不明時の最初の空照会直後にコンテナが可視化されるP2も対応した。遅延可視化と最後まで不可視の2件を修正前fail→修正後passで検証。応答不明時は5秒を基準に再照会し（各照会は別に5秒上限）、、可視化された名前を回収する。5秒経過は未作成・消失の証明とは扱わずISOLATION_CLEANUP_FAILEDで停止し、pending_containerへ対象名を保存して後続を禁止する。5秒後もdaemon処理が終了したとは断定せず、自動再開しない。通常の成功したcreate経路は応答による完了確認後に回収する。

追加のP2では、遅いcreate後にstartへ再び30秒を与えていたため、作成前にcase/globalの早い方の期限を固定し、create・設定inspect・startで残り時間を共有するよう修正した。予算消費済みなら候補を起動しない。遅いcreateとglobal期限の2境界は修正前fail→修正後pass。起動・稼働の予算と、期限後も必須となる停止確認・回収を分離し、後者の各Docker照会・kill・rmは5秒上限として失敗時は後続を禁止する。

CPU自己申告値へ巨大なJSON整数を返すとfloat変換でOverflowErrorとなるP2は、外部出力の検証契約に関わるためBLOCKINGと分類した。CPU値は厳密なint/float型と0〜30の比較で検証し、変換せずOUTPUT_CPUとして試行失敗へ渡す。巨大な正負整数・bool・NaN/無限大を拒否し、有効境界0/30を受け入れる回帰を修正前fail→修正後passで確認した。
