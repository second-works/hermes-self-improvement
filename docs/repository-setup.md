# Issue #1 導入判断・運用

2026-10-14。Risk Tier: HIGH（CI・Security・レビュー運用の初期導入）。ユーザーがIssue #1の実装とPR提出を承認。Hermes本番、課金変更、自己改善の自動適用、Auto-Mergeは範囲外。復旧は本PRのrevertで行う。

原本は second-works/ai-development の `b2715a76c5ab3715ccce88167c23ce12c81e85b1`。取得時点の原文とプロジェクト固有境界を照合した。参照資産の3文書（plan-authoring、app/docs/design、web-todo-app-plan.sample）は末尾空白のみ正規化した。既存ファイルはなく、既存の未追跡 `.bm25/` は保持・除外した。空リポジトリのPR比較先として、ファイルなしの初期コミットだけmainに配置した。

| 原本 | 採用・調整 | 理由 |
| --- | --- | --- |
| AGENTS.md | 採用。原本自身のtests実行行を削除し、Hermes非操作・通常レーン・verify入口を追記 | 1 Issue = 1 PR、同一headの検証、人間Mergeを保持 |
| docs/、.agents/skills/、templates/ | 参照資産として同一revisionを配置 | 原本guideの参照先保持。helperの実行許可・自動起動は意味しない |
| .github/ISSUE_TEMPLATE/、pull_request_template.md | 採用 | Scope、Done、Risk、Evidence、Reviewを記録 |
| templates/verification/verify.sh | scripts/verify.shに採用 | lint → typecheck → test → build。全skipと失敗は停止 |
| templates/security/security-preflight.sh、security.yml | scripts/へ配置しworkflow参照先を調整 | 正確なPR headのindex snapshotの既知秘密パターン検査。Bash 5必須（レビューP1修正を原本copyにも同期） |
| templates/github-actions/generic-ci.yml | CIとして採用 | アプリのない構成にも標準入口を適用 |
| templates/github-actions/codeql.yml | Python、build-mode noneへ調整 | 今回のPythonテストと参照helperを解析。JSアプリはない |
| templates/dependabot/ | github-actions専用設定へ調整 | runtime依存未導入。npm/pip更新は対象外 |
| SECURITY.md | プロジェクト向けに書換え | 架空のサポートversionを除去。非公開報告とHermes境界 |
| 原本ci.yml、tests/、scripts/ | 実行資産としては除外 | テンプレート自体の回帰検査・状態収集はこのprojectのCIではない |
| jev-triage、decision-shadow、local-judge-smoke、slack-failure-alert | 除外 | 追加Secrets、外部送信、ローカルモデル／API依存が今回不要 |
| node-ci、python-ci、app/setup、app/doctor | 有効化しない | アプリのセットアップや本番接続は範囲外 |

## CIと費用・権限

GitHub-hosted runnerのみ使用し、Hermes本番へ接続しない。CIとSecurityのGITHUB_TOKENはcontents: read、checkoutは認証情報を残さない。Securityはmain側のpull_request_targetから候補headのGitオブジェクトだけを取得し、固定revision `02cab2e1798d5a6c42cea4fb2591a37f1494bfb0` のscannerへ渡す。候補コード・設定・依存installをSecurity jobで実行しない。CI / CodeQL定義、検証入口と既存テストのblob・modeも固定revisionへ照合する。

人間が承認した専用GitHub App `hermes-security-reporter` のtokenを、候補SHAのSecurity Preflight報告stepだけへ渡す。App権限はCommit statuses書込とMetadata読取、このrepoだけへinstall。秘密鍵はmain branchだけを許可するEnvironment `security-reporter` に保持し、main保護の必須送信元をApp ID5322549へ固定する。管理者のEnvironment bypassは無効。設定・認証の失敗を成功にせず、GITHUB_TOKENへfallbackしない。詳しくは docs/security-reporter.md。

CodeQLだけsecurity-events: writeをjob単位で付与。CI/CodeQLはPRとmain push、CodeQLは週次も検査する。OPENAI_API_KEY、API課金のActions、自己改善の自動適用は導入しない。

公開repo・admin権限・Actions有効をGitHub APIで確認。利用プランの変更は行わない。DependabotはmainへのMerge後に有効になる。ActionsとCodeQLの実発火・利用可否はPRのrunで確認する。

## Codexレビュー

[公式GitHub連携ドキュメント](https://learn.chatgpt.com/docs/third-party/github)に従い、Codexに接続したrepoでReview codeのAutomatic reviewとpersonal preferencesのReview triggerを設定する。設定はOpenAI側であり、workflowの追加だけでは有効にならない。GitHub連携の認証を使い、APIキーは不要。アカウントのレビュー利用枠・制限に従うため、無制限・無料と断定しない。

このPRを実動テストに使う。自動発火が確認できなければ `@codex review` をPRコメントで依頼する。👀反応は受付であって完了ではない。botのreviewまたは明示的な完了コメントと対象headを照合する。認証不足、repo未接続、利用制限、無応答、途中失敗はNOT_VERIFIED / BLOCKEDとし、Merge可能と報告しない。GitHubのCI成功やレビュー要求コメント自体をCodex成功の証拠にしない。

指摘は同じPR branchで修正し、head変更後にlocal → CI → Security → CodeQL → Codex Reviewをやり直す。P0/P1/BLOCKING P2は未解決で進めない。最終Mergeは人間が判断する。CIの必須チェックはCodex完了を代替しない。

## 検証責務

標準ライブラリのunittestで、Security成功、stage後の作業ツリー消去・checkout filterでも提出内容を検査する回帰、秘密検出の非zeroと値非表示、依存監査未対応のUNAVAILABLE、symlink非追跡、verify全skip拒否と失敗後停止、AGENTS参照先を検査する。fixtureは一時ディレクトリ内の無害な値だけを使う。`~/.hermes`は読み込まない。

typecheck / buildはアプリと型検査設定がないため対象外。Security Preflightはindex登録済みのファイルを検査するため、提出内容をstageしてから実行する。作業ツリーではなくgit cat-fileで一時領域へ展開した未変換のindex blobを検査する。依存監査も同じsnapshotを使い、symlinkの依存manifestは外部参照せずUNAVAILABLEとして停止する。共通参照helperの全回帰テスト・本番実データの検収は今回対象外。

## 保護と実動証拠

初期状態: main rulesetなし。2026-10-14に自動承認レビューが具体設定への承認不足として一度拒否した後、ユーザーが承認票数0の設定を明示承認し、main保護を適用・APIで確認した。必要なチェックはCI `ci`、Security `Security Preflight`、CodeQL `Analyze (python)`。PR経由、人間の承認、未解決threadの解消、最新headのチェック、force pushと削除の禁止を推奨する。設定の適用結果と本PRのCI / Security / Codex実動証拠はPRコメントへ記録する。未設定・未確認を適用済みと扱わない。


適用候補は `docs/main-protection.proposed.json`。最新headの必須チェック、PR経由、stale review失効、未解決thread解消、管理者も対象、force pushと削除禁止。承認票数0は単独管理者がPR作者として自分に承認票を付けられないための候補値であり、人間の最終Merge判断を免除しない。1票必須にする場合は別の人間reviewerが必要。承認票数0で適用済み。最終Mergeの実行承認は別途必要。

実動確認: PR #10でCI、Security Preflight、CodeQL Analyze (python)とCodeQL結果checkが成功。Codex連携は手動の `@codex review` へ👀反応とRunning summaryを返した。初回の自動発火は未確認だったが、Chromeのログイン済み公式設定画面でリポジトリの自動レビューON、レビュー対象とトリガーは個人設定を継承、個人設定の自動レビューON・PR作成時、レート制限後のクレジット使用OFFを確認した。設定変更や追加課金は行っていない。最終Codex結果と最新headの証拠はPRコメントへ記録する。


## 空mainへの信頼境界の初期配置

PR-controlled workflowでrequired job名を維持しつつ検査stepだけをexit 0へ変えられるP1を受け、Security workflowをmain側へ移した。PR headのGitオブジェクトをfetch/read-treeして固定scannerに渡し、候補SHAへpending → success / failure / errorを報告する。GitHubのpull_request_target仕様と最小権限は[公式安全指針](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)を確認した。初期構成はPUBLICデータだけを検査し、追加Secrets・PRコード実行・本番接続を使わなかった。現在の承認済みreporter構成は下記およびdocs/security-reporter.mdを参照する。

初期mainは空のコミットだったため、PRに追加しただけでは初回発火しなかった。信頼するsecurity.ymlだけのmain初期配置が必要。既存のmain保護を黙って緩めず、具体的な初期配置commitと差分を提示し、人間が一度限りの初期配置と管理者bypassの一時切替を承認するまで停止する。CI/CodeQL/local Securityの成功でこの未検証を代替しない。配置後は管理者保護を即座に戻し、PRをmainと同期して、trusted workflowの同じheadの実動結果とCodex再レビューを確認する。


2026-10-14、人間が「初期配置のみ」を明示承認した。mainが空の既知SHAであることを再確認し、管理者保護の適用だけを一時解除してsecurity.yml 1ファイルの `735dfe26a45fde134d88f484ddbb6faf384a2297` を通常pushし、finallyで管理者保護を即復元した。PR全体のMergeはしていない。PRをmainへ同期後、pull_request_targetのrun `38576794780` が成功し、候補head `32c769241427be6eafe5d0725af30e9113e48085` へSecurity Preflight=successを報告した。管理者保護と必須チェックの復元もAPIで確認した。以降のheadの証拠はPRコメントへ記録する。

GitHub公式は公開repo向けpull_request_target既定policyの2026-11-02強制適用を案内している。現時点の実動runは成功したが、policyのopt-outや課金・プラン変更は今回行っていない。将来イベントがpolicyで拒否された場合はSecurity未検証として停止し、管理者が適用対象と許可設定を確認する。関連するpolicy変更は別の人間承認が必要。


レビュー追加対応: Secretを含むindexのファイル名も値を表示せず拒否するscanner、Security PreflightをCodeQL成功で代替しない手動helper、未変換index blobのlint、文書化済みPython依存marker認識へ修正した。P1とP2（IN-SCOPE FIX）はそれぞれ修正前fail→修正後passを確認し、20件のテストが成功。固定scannerの更新候補は `ffc843ab1f880917922a9c4fa2ece7d730afbcc2`。mainのpin1行更新は人間が具体差分を承認した後、b590b3e903b13ff3399fffd9fafdf963c51affcaだけを通常pushして実施し、finallyで管理者保護を即復元した。PR全体のMergeはしていない。以降のscanner変更も具体差分の承認・検証が必要。

手動wait-checks helperはci、Security Preflight、Analyze (python)の3 contextを明示的に要求する。他の成功checkやローカルfallbackで不足を代替しない。欠如ケースの回帰を含む22件が成功。

参照用generic / Node / Python / CodeQLのcheckoutもpersist-credentials: falseへ統一した。PRテンプレートのReview Evidence Contractリンクを実在する正本へ修正。Python CIテンプレートのuv / Poetry開発依存導入は非実行資産に関するP2 FOLLOW-UPとしてdocs/review-followups.mdのFU-10-1へ記録し、現行CIでは有効化しない。

CI / CodeQLの実行定義は固定scannerと同じ承認済みrevisionに固定し、main側Security gateがcandidate treeのworkflow blob・modeを照合する。ci.ymlまたはcodeql.ymlの改変・欠如・mode変更はSecurityを失敗させ、required job名だけを維持したno-opを受理しない。CI / CodeQL定義を正当に更新する場合は、承認済みrevisionの更新とgateの実動検証を先に行う。1正常・6異常の無害なGit fixtureでこの検査を確認した。main側guardの反映は具体差分への人間承認後にのみ行う。

workflow path集合も固定し、別workflowでrequired job名を複製する回避を拒否する。candidateのSecurity定義も実際のmain側workflow revision（github.workflow_sha）とblob・modeを照合し、同じファイルへのno-op追加も拒否する。

2026-10-15、ユーザーがworkflow定義固定の具体差分を承認した。security.ymlだけの2a5aceba7cee7d43a17ab1be73b6acc5b826c0c2をmainへ通常pushし、finallyで管理者保護を即復元した。PR全体のMergeはしていない。CI / CodeQL定義とworkflow集合は固定revision、Security定義は実行中のmain側workflow revisionに照合する。以降の実動証拠はPRコメントへ記録する。

2026-10-15、専用GitHub Appとmain限定Environmentによるstatus上書き対策をユーザーが承認した。App権限・repo限定install、Environment、送信元固定を適用。ユーザーがAppに対応する新しいPEMでSecretを更新し、head40ea0860のSecurity run38649338289 attempt2でApp認証・固定scanner検査・候補SHAへのsuccess報告を確認した。診断用コードは削除し、最終headの実動証拠はPRコメントへ記録する。各Security-onlyのmain配置後に管理者保護をfinallyで即復元し、PR全体のMergeは行っていない。
