# 公式Self-Evolutionの隔離spike

対象: [Issue #6](https://github.com/second-works/hermes-self-improvement/issues/6)。調査日: 2026-10-16。
Risk Tier: **HIGH**。外部コード・依存の実行と隔離境界の検証を含む。2026-10-16にユーザーが下記の費用0・第1段階を承認し、実施した。push / PR、モデルAPI、本番適用の承認は含まない。

## 現時点の判断

**現行固定版の直接導入は見送りを推奨する。** 実依存DSPy 3.4.1では公式のGEPA引数がTypeErrorとなり、実validatorには全文/本文の不整合がある。実CLIの故障注入試験でも制約失敗時のexit 0とテスト未接続を確認した。
API費用を使う前に解消すべき問題がある。最終採否は人間判断とし、実モデルの改善成功率とHermes本体互換性は未検証のまま残す。

この文書は調査成果と実験承認の対象を記録する。Issue #6の完了報告ではない。
本番Hermes、設定、認証、会話、サービスは読み取りも起動も行っていない。

## 仕様・依存と固定対象

- Goal: 公式実装を固定revision・分離環境で検証し、導入 / ラップ / 独自実装を比較する。
- Scope: 公開README・設定・依存・ライセンス・未解決Issue、実CLI/API、安全な複製スキルの小規模実験、費用・副作用・失敗モード。
- Done: 実行ログ、依存lock、再現手順、採否判断を同じPRへまとめる。
- Verification: 隔離拒否試験、CLI/APIの成功・失敗とartifact hash、候補の実変化、独立評価。repoの標準検証 / SecurityとPR後の同一head CI / Security / CodeQL / Codex Reviewは別に確認する。
- Dependencies: 基本設計 #2（PR #11）、独立評価 #5（PR #13）。監査・診断PR #14も取り込まれたmain `1d9439f4836db44d37f76f5f193497800ada4c8b` を開始点とする。IssueのCloseは今回の作業に含めない。
- 禁止範囲: 本番への適用、sessiondb、追加DB/RAG、Cron、新しいモデルAPI、認証の読取、既存workflow・固定検証入口・`tests/test_setup.py`の変更。旧runsやログの削除・上書きもしない。

Self-Evolutionの公開mainをGitHub APIで再確認したところ、従来の調査基準と同じ
`0a929e3aa20e15cf04dc7c28492a7d41a5139125`（2026-06-17）だった。
一時領域へcloneし、このcommitをdetached checkoutしてソースを読んだ。取得コードは実行していない。

Hermesの比較基準は公開commit `f97608f178d1ffeca59860195ab7da295f7c8e5f`。
v0.21.5タグ、本番との同一性、公式CLIとの実行互換性は未確認。本番revisionを推定して補わない。

## 固定ソースで確認した実装

以下のリンクはすべて同じSelf-Evolution commitを参照する。静的確認と動的な再現を区別する。

| 観点 | 原文で確認した事実 | 動的検証・判断への影響 |
| --- | --- | --- |
| 実装範囲 | [README](https://github.com/NousResearch/hermes-agent-self-evolution/blob/0a929e3aa20e15cf04dc7c28492a7d41a5139125/README.md#L54-L60)はPhase 1のスキル改善だけをImplemented、Phase 2〜5をPlannedとする | Tool / prompt / code / 常時ループを実装済みとしない |
| Python・依存 | [pyproject](https://github.com/NousResearch/hermes-agent-self-evolution/blob/0a929e3aa20e15cf04dc7c28492a7d41a5139125/pyproject.toml#L10-L31)はPython >=3.10、DSPy >=3.0.0、OpenAI >=1.0.0、PyYAML >=6.0、Click >=8.0、Rich >=13.0。devとdarwinianはoptional | 依存lockはなく、現在解決される版での互換性は未保証。darwinianは導入しない |
| License | READMEとpyprojectはMITを表記するが、固定treeにLICENSEファイルがない。GitHub repo APIのlicenseもnull | 宣言はあるがライセンス文面を確認できない。再配布・本番採用の承認根拠にしない |
| CLI | [evolve_skill.py](https://github.com/NousResearch/hermes-agent-self-evolution/blob/0a929e3aa20e15cf04dc7c28492a7d41a5139125/evolution/skills/evolve_skill.py#L297-L323)は `python -m evolution.skills.evolve_skill`。`--skill`, `--iterations`, `--eval-source`, `--dataset-path`, `--optimizer-model`, `--eval-model`, `--hermes-repo`, `--run-tests`, `--dry-run` | `evolve_skill` という裸のコマンドや、docstringの `--dataset` を採用しない。実helpは未実行 |
| repo探索 | [config.py](https://github.com/NousResearch/hermes-agent-self-evolution/blob/0a929e3aa20e15cf04dc7c28492a7d41a5139125/evolution/core/config.py#L67-L108)は環境変数・home・隣接repoを探索する。明示引数は探索より優先 | 空HOMEと明示 `--hermes-repo /fixture/hermes-agent` を併用する。本番pathを試し読みしない |
| dry-run | [CLI 72〜77行](https://github.com/NousResearch/hermes-agent-self-evolution/blob/0a929e3aa20e15cf04dc7c28492a7d41a5139125/evolution/skills/evolve_skill.py#L72-L77)はスキル読込後にreturnする | dry-run成功からAPI・最適化・制約・PR生成の成功を推定しない |
| 構造検査 | [CLI 121行・188行](https://github.com/NousResearch/hermes-agent-self-evolution/blob/0a929e3aa20e15cf04dc7c28492a7d41a5139125/evolution/skills/evolve_skill.py#L118-L204)は本文を渡す。[validator](https://github.com/NousResearch/hermes-agent-self-evolution/blob/0a929e3aa20e15cf04dc7c28492a7d41a5139125/evolution/core/constraints.py#L150-L175)はfrontmatterを要求する | 正常なfrontmatter付きfixtureの全文と本文を同じAPIへ渡し、差を実証する必要がある |
| 候補抽出 | [SkillModule](https://github.com/NousResearch/hermes-agent-self-evolution/blob/0a929e3aa20e15cf04dc7c28492a7d41a5139125/evolution/skills/skill_module.py#L94-L119)は本文を通常属性 `skill_text` として保存しpredictorの入力に渡す。CLIは最適化後もその属性を抽出する | predictorの変更と保存本文の変更を別々にhash検査する。no-opの動的再現は未実施 |
| fallback | [CLI 155〜177行](https://github.com/NousResearch/hermes-agent-self-evolution/blob/0a929e3aa20e15cf04dc7c28492a7d41a5139125/evolution/skills/evolve_skill.py#L155-L177)はGEPAの広い例外を捕捉してMIPROv2へ切り替える | 互換性・実行エラーとoptimizer不在を混同しない。fallbackと実際のAPI回数を記録する |
| 失敗終了 | 構造検査NGでも `evolved_FAILED.md` を保存してreturnする | exit 0だけで成功判定しない。出力内容・検査結果・候補hashが必要 |
| テスト | `--run-tests` はconfigの `run_pytest` へ渡るが、CLIは `run_test_suite` を呼ばない。`validate_all` もその呼出しを持たない | フラグを付けたこととテスト実行を区別する。fixtureのsentinelで呼出し有無を確認する |
| PRと品質 | CLIは候補・基準・metricsをファイル保存する。holdout差が正なら改善メッセージを出すが、有意性検定やPR作成処理はこの経路にない | PR生成の成功や汎用的改善を主張しない。既存の独立評価を公式の自己採点で置換しない |
| 費用 | READMEは1 run約2〜10 USDと説明する | 見積説明であり、現在のprovider料金・実測・予算保証ではない。今回のAPI実費は0 USD |

公開未解決Issueには [#164 LICENSE欠如](https://github.com/NousResearch/hermes-agent-self-evolution/issues/164)、
[#171 本文の構造検査](https://github.com/NousResearch/hermes-agent-self-evolution/issues/171)、
[#172 候補本文の抽出](https://github.com/NousResearch/hermes-agent-self-evolution/issues/172)、
[#175 DSPy 3.3互換性と抽出](https://github.com/NousResearch/hermes-agent-self-evolution/issues/175) がある。
一覧のタイトルは補助情報であり、本文の正しさや修正済みを保証しない。上表は取得ソースを根拠とする。
Context7でも公式ライブラリIDを解決してCLI/golden/dry-run文書を確認したが、実装との整合は固定ソースを優先する。

## 承認対象: 費用0の第1段階

状態: **APPROVED / 第1段階実施済み**。以下は2026-10-16のこのチャットでユーザーが承認した範囲。過去IssueのDocker承認は流用していない。

1. 取得済み固定Self-Evolutionと、固定公開Hermesソースまたは明示した最小模擬repo、合成 `github-code-review` スキルだけを使用する。最小模擬repoの結果はHermes本体互換性の証拠にしない。
2. Dockerを起動・確認し、公式Python 3.12 linux/arm64 imageをdigest固定する。ソース・依存準備と試験を分離し、準備時だけDocker公式registryとPyPIの公開配布経路を利用する。モデルproviderへは接続しない。
3. ホストvenvへ依存を導入せず、専用の準備コンテナで実依存を解決する。依存版・wheel hash・image ID/digestを記録し、lockからオフライン再導入を確認する。wheelのない依存や新しい配布先が必要なら停止する。上流コード・依存をホストで実行しない。
4. 実行は1コンテナずつ、非root・capabilityなし・no-new-privileges・read-only root・networkなし・空HOME。fixtureと固定ソースはread-only、ホストHOME・Secrets・socket・hidden・旧traceをmountしない。CPU 1、memory 1 GiB、swap追加0、pids 64、書込tmpfs 128 MiB、stdout/stderr合計1 MiB、各試験60秒、準備を含む全体20分を上限とする。新規保存量は2 GiBを上限とし、超過時は停止して原本を保持する。
5. 今回のimage・資源条件で隔離拒否・資源上限・timeout・子process停止を先に検証する。過去gateの成功を流用しない。他コンテナとの競合や停止確認不能は中止し、既存サービスを停止しない。
6. 実CLIのhelp/dry-run、実validatorの全文/本文比較、実DSPyのAPI signatureと候補抽出を確認する。ネットワーク不要のin-process fixtureで到達できる範囲だけを試す。模擬optimizerや応答を使った結果は明示して、実モデル改善や公式optimizerの成功と混同しない。候補は最大1件、再試行は自動で増やさない。
7. CLIと独立評価を区別し、exit code・失敗理由・候補前後hash・fixture前後hash・許可された保存先の差分を記録する。実行不能はBLOCKED、証拠不足はNOT_VERIFIEDとして保持する。
8. 新規 `runs/<run_id>/` をGit管理外で使い、既存保存方針と同じく合成原本は最低30日、検査済み監査記録は最低90日、自動削除なしとする。この保存範囲も今回の承認対象とする。GitHubへ出すのは別途検査・承認したPUBLIC要約だけ。

変更先はこの文書、専用の `scripts/` / `src/` / `tests/` / `fixtures/` の追加資産に限定する。既存評価controllerの制約を黙って拡張しない。
新しい隔離方式や上限変更が必要なら実行前に対象と差分を示す。

第1段階の停止点は「失敗モード・実依存互換性・費用0で確認可能な範囲の実証」とする。
実モデルによる改善、モデルprovider・モデルrevision・保持条件・送信先・現在料金・呼出数/token/金額上限の決定、認証アクセスは次の具体的承認へ戻す。
第1段階だけではIssue #6の小規模改善実験を完了扱いにしない。直接導入不可という結果が出ても、Issueの採否判断と完了範囲は人間へ確認する。
push / PR提出 / Mergeもこの実験承認には含めない。

## 実行結果・再現手順

実行原本: `runs/self-evolution-20261015T221545Z-788921933356/`（Git管理外）。
検査済みPUBLIC抜粋: [構造化証拠](evidence/self-evolution-stage1.json)、[実help](evidence/self-evolution-help.txt)、[実dry-run](evidence/self-evolution-dry-run.txt)。原本は上書き・削除していない。

Python 3.12.15 / linux arm64 / cgroup v2、Docker 29.8.2、Linux 7.0.14-linuxkit。
公式image ID `sha256:eb7d16fec874f15b584063275012ac719885a2b87574d124c0da9c156d504629`、registry digest `python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258`。
実測50.460秒、保存量295,124,039 bytes（report書込前）。モデルAPI 0呼出、0 USD。全試験後に今回のコンテナが残っていないことも確認した。

直接依存はDSPy 3.4.1、OpenAI 2.54.0、PyYAML 6.0.3、Click 8.5.0、Rich 15.0.0。
GEPA 0.1.4、LiteLLM 1.105.1を含む全70パッケージを[hash付きlock](../fixtures/self-evolution/requirements.lock)に固定し、同lockのwheelだけをnetworkなしで導入した。
lockはlinux/arm64・CPython 3.12向け。別platformへの流用は未検証。

| 検証 | 結果と限界 |
| --- | --- |
| 隔離gate | 7分類成功。境界22項目、disk / memory / pids / CPU制限、timeoutと子process停止、出力上限。実行時networkなし・全入力read-only、ホスト書込共有なし |
| 実CLI help / dry-run | 成功。ただし最小模擬repoのスキル読込までで、Hermes本体の統合成功ではない |
| 実validator | 同一335文字のスキルは全文で `skill_structure=true`、本文だけではfalse。他のsize/non_emptyは両方true |
| 実GEPA API | 公式CLIと同じ `max_steps=1` は `TypeError: GEPA.__init__() got an unexpected keyword argument 'max_steps'`。providerに接続せずconstructorで再現 |
| 候補抽出の検査fixture | 実SkillModuleのpredictor instructionsを手動変更しても、保存に使う `skill_text` は不変。optimizerによる改善実験ではなく、属性抽出の分離を示す限定試験 |
| 実CLIの故障注入 | datasetとoptimizerを明示的に模擬化し、実validatorを使用。制約失敗メッセージ、失敗artifact保存、exit 0を確認。`--run-tests`指定時のtest-suite sentinelは0回、模擬compileは1回 |
| 副作用 | source / dependency / fixture hashは試験前後で一致。失敗候補は使い捨てtmpfsに生成され、検査済み合成内容とhashは新runのログへ保存。ホスト本番の無変更を本番読取で検証したわけではなく、未mount・空env・明示パスでアクセスを防いだ |

再現には起動済みのローカルDocker、ネットワーク準備時の公式registry/PyPI、公開upstreamの固定checkoutが必要。依存をホストへinstallしない。
この入口は承認済みの実験を再現するためのもので、CIへ自動接続していない。

```sh
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin git clone --no-checkout https://github.com/NousResearch/hermes-agent-self-evolution.git /private/tmp/hermes-self-evolution-public
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin git -C /private/tmp/hermes-self-evolution-public checkout --detach 0a929e3aa20e15cf04dc7c28492a7d41a5139125
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin python3 -I -B scripts/self_evolution_spike.py --source /private/tmp/hermes-self-evolution-public
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin python3 -I -B tests/test_self_evolution_spike.py -v
```

初回 `self-evolution-20261015T221254Z-5a7fa18b4099` はpip展開用tmpfsのENOSPCで停止した。候補実行なし、原本保持。準備だけの一時領域を、上限2 GiB監視下の専用prepareへ移し、候補tmpfsの128 MiBは維持した。
次の `self-evolution-20261015T221401Z-622fc30e3efb` は隔離gateとhelp/dry-run成功後、検査fixtureの `ChainOfThought.signature` 参照ミスで停止した。これは検査側の不備で、公式の不具合へ計上しない。実依存ソースに合わせて `.predict.signature` へ修正し、最終runで全工程を再確認した。
最終入口は固定lockを必須とし、初回の無固定依存解決を繰り返さない。入口に自動retryはなく、1 runの上限は20分。今回の3 run全体も最初の開始から最終終了まで約222秒で承認上限内に収め、候補生成APIは全runで0呼出だった。再現のために上限を超えて再実行する承認ではない。

## 採否比較と未確認

| 選択肢 | 判断 |
| --- | --- |
| 公式をそのまま導入 | 見送り推奨。今回の依存版ではGEPA引数不整合、構造検査不整合、exit 0とテスト未接続があり、READMEの契約を満たせない |
| 公式をラップ | 条件付き候補。引数変換だけでは候補抽出・検査・テスト・独立評価・費用境界を保証できず、内部へのpatchと追加検証が必要。実装は今回行わない |
| 既存評価基盤へ小さな候補生成器を接続 | 後続 #7 向けの推奨方向。既存のhidden隔離と採否判定を維持できる。新しい生成器・モデル・APIの採用は今回未承認で、設計と費用の具体的承認が必要 |

実モデル改善が成功しないと断定した結果ではない。公式の現行経路を安全な改善サイクルとして採用する根拠が不足し、費用を使う前に阻害要因を実証できた結果である。
人間がこの調査を不採用spikeの完了証拠として採用するか、互換patch / 実モデル試験を追加するかは未決。Issue #6は閉じない。

- VERIFIED（静的）: live Issueと公開main、固定checkout、上表のソース上の契約と制御フロー。
- VERIFIED: 固定lockのオフライン導入、実CLI起動、今回の隔離gate、構造検査の不整合、GEPA constructor不整合、模擬optimizer使用時の失敗終了・テスト未接続。
- NOT_VERIFIED: 実optimizerによる本文変更、実モデル改善成功率、Hermes本体/v0.21.5互換性、依存の脆弱性監査、ライセンス文面。
- モデルAPI・認証アクセス・本番読取・本番変更は全runで0。一般品質や本番採用成功には換算しない。
- 人間判断待ち: 最終採否、Issue完了範囲、Merge。
- 2026-10-16、ユーザーが検査済みPUBLIC差分12ファイルとPR本文案を確認してcommit / push / 調査PR提出を承認した。宛先は `second-works/hermes-self-improvement` の `issue-6-self-evolution-spike` → main、参照は `Refs #6`。原本runs/logsの送信、Issue Close、Merge、モデルAPI、本番適用は含まない。

最終実装の標準検証は30 tests成功、追加の隔離契約試験10 testsと既存評価基盤の回帰34 testsも成功（計74）。typecheck/buildは既存の実行可能入口がないため理由付きskip。
新規資産を含むSecurity PreflightはSECURITY_PASSED。依存の脆弱性監査は対応manifestがなく対象外であり、wheelの安全性を保証するものではない。
self-reviewではIssue・既存評価controller・公式の呼出元/validator/対称する候補保存経路と照合し、既存の固定入口・workflow・本番境界に変更がないこと、成功/失敗/未検証の区別、原本保存を確認した。PR後のCI / Security / CodeQL / Codex Reviewは未実施。
設計文書のローカルLLM圧縮は完了結果を得られず中断し、判断に使用しなかった。安全境界・固定ソースの上記事実は原文を直接確認した。
