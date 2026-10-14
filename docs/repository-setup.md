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

GitHub-hosted runnerのみ使用し、self-hosted runnerやHermes本番には接続しない。CIとSecurityはcontents: read、checkoutは認証情報を残さない。CodeQLだけsecurity-events: writeをjob単位で付与。workflowはPR → mainを検査し、CI/CodeQLはmain pushも検査する。CodeQLは週次実行も行う。pull_request_targetは使用しない。追加Secrets、OPENAI_API_KEY、API課金のActionsは導入しない。

公開repo・admin権限・Actions有効をGitHub APIで確認。利用プランの変更は行わない。DependabotはmainへのMerge後に有効になる。ActionsとCodeQLの実発火・利用可否はPRのrunで確認する。

## Codexレビュー

[公式GitHub連携ドキュメント](https://learn.chatgpt.com/docs/third-party/github)に従い、Codexに接続したrepoでReview codeのAutomatic reviewとpersonal preferencesのReview triggerを設定する。設定はOpenAI側であり、workflowの追加だけでは有効にならない。GitHub連携の認証を使い、APIキーは不要。アカウントのレビュー利用枠・制限に従うため、無制限・無料と断定しない。

このPRを実動テストに使う。自動発火が確認できなければ `@codex review` をPRコメントで依頼する。👀反応は受付であって完了ではない。botのreviewまたは明示的な完了コメントと対象headを照合する。認証不足、repo未接続、利用制限、無応答、途中失敗はNOT_VERIFIED / BLOCKEDとし、Merge可能と報告しない。GitHubのCI成功やレビュー要求コメント自体をCodex成功の証拠にしない。

指摘は同じPR branchで修正し、head変更後にlocal → CI → Security → CodeQL → Codex Reviewをやり直す。P0/P1/BLOCKING P2は未解決で進めない。最終Mergeは人間が判断する。CIの必須チェックはCodex完了を代替しない。

## 検証責務

標準ライブラリのunittestで、Security成功、stage後に作業ツリーだけを消去しても提出内容を検査する回帰、秘密検出の非zeroと値非表示、依存監査未対応のUNAVAILABLE、symlink非追跡、verify全skip拒否と失敗後停止、AGENTS参照先を検査する。fixtureは一時ディレクトリ内の無害な値だけを使う。`~/.hermes`は読み込まない。

typecheck / buildはアプリと型検査設定がないため対象外。Security Preflightはindex登録済みのファイルを検査するため、提出内容をstageしてから実行する。作業ツリーではなく一時領域へ展開したindexの内容を検査する。依存監査も同じsnapshotを使い、symlinkの依存manifestは外部参照せずUNAVAILABLEとして停止する。共通参照helperの全回帰テスト・本番実データの検収は今回対象外。

## 保護と実動証拠

初期状態: main rulesetなし。2026-10-14に自動承認レビューが具体設定への承認不足として一度拒否した後、ユーザーが承認票数0の設定を明示承認し、main保護を適用・APIで確認した。必要なチェックはCI `ci`、Security `Security Preflight`、CodeQL `Analyze (python)`。PR経由、人間の承認、未解決threadの解消、最新headのチェック、force pushと削除の禁止を推奨する。設定の適用結果と本PRのCI / Security / Codex実動証拠はPRコメントへ記録する。未設定・未確認を適用済みと扱わない。


適用候補は `docs/main-protection.proposed.json`。最新headの必須チェック、PR経由、stale review失効、未解決thread解消、管理者も対象、force pushと削除禁止。承認票数0は単独管理者がPR作者として自分に承認票を付けられないための候補値であり、人間の最終Merge判断を免除しない。1票必須にする場合は別の人間reviewerが必要。承認票数0で適用済み。最終Mergeの実行承認は別途必要。

実動確認: PR #10でCI、Security Preflight、CodeQL Analyze (python)とCodeQL結果checkが成功。Codex連携は手動の `@codex review` へ👀反応とRunning summaryを返した。初回の自動発火は未確認だったが、Chromeのログイン済み公式設定画面でリポジトリの自動レビューON、レビュー対象とトリガーは個人設定を継承、個人設定の自動レビューON・PR作成時、レート制限後のクレジット使用OFFを確認した。設定変更や追加課金は行っていない。最終Codex結果と最新headの証拠はPRコメントへ記録する。
