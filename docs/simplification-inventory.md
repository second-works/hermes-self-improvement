# 簡素化のInventory / Safety Baseline

親Issue [#168](https://github.com/second-works/ai-development/issues/168)、実装単位 [#169](https://github.com/second-works/ai-development/issues/169)。2026-10-03取得のmain `7a52b2b3f46487b91190a6c923926c9325913046` を基準とする。

これはPhase 1の棚卸しと後続変更案であり、現行ルールの置換・削除承認ではない。分類の人間確認後、責務単位で別子Issue / PRへ進む。既存案件への一括移行を要求しない。

## 判断と測定範囲

役割の提案: **ai-developmentは、Nine標準のIssue生成とCodex実装に必要なテンプレートを提供する。** 最小契約そのものの確定はPhase 2で行う。

`template-change-evaluator`の主判定は **ADAPT**。既存の安全資産を使い、常駐ルールと今回値を減らす。新しいGate・Skill・状態管理システムは追加しない。

| 測定対象 | mainでの観測 |
| --- | --- |
| `AGENTS.md` | 52,476 bytes |
| `README.md` | 9,127 bytes |
| `.github/ISSUE_TEMPLATE/parent-issue.md` | 6,039 bytes |
| `.github/ISSUE_TEMPLATE/child-issue.md` | 7,255 bytes |
| `.agents/skills/*/SKILL.md` | 3 Skills |
| `tests/*/run-samples.sh` | 28入口 |
| `.github/workflows/ci.yml` | 22入口の直接実行。6入口は直接stepなし |
| `.github/workflows/*.yml` | 6 workflows |

bytesはUTF-8ファイルサイズでありtoken数ではない。CIの直接実行数は行単位の `run: [bash ]tests/*/run-samples.sh` を数えた。syntax check・間接呼出・GitHub上の成功件数とは区別する。全体の実行時間短縮や生成Issueの読解改善は未検証で、Phase 5で確認する。

[Instruction Architecture Inventory](instruction-architecture-inventory.md)は2026-09-20の47,136 bytesを基準とする既存配置案、[Harness台帳](ai-development-harness-inventory.md)は責務・停止条件の既存資料。本書は#168の差分判断であり、過去のサイズ・判定を現在の確定値として再利用しない。

## 分類の意味

- **KEEP**: 最小ルール・実効的安全制御・必要な実装資産として維持。
- **MOVE_TO_SKILL**: 判断を含む反復作業を既存Skillへ集約。AGENTSには短い入口。
- **MOVE_TO_DOCS**: 条件発生時に読む詳細仕様へ集約。今回値はIssue / PRに保持。
- **REMOVE_CANDIDATE**: 重複・固定文言検査・常時記入の削減候補。削除は保証先確認と人間確認後。

ファイル単位で一律に判定せず、同じファイル内の安全責務と記入・説明責務を分ける。以下の移動先は提案であり、未作成の正本を現行参照先として扱わない。

## 常駐ルール・入力・Skillの責務

| 現行資産 / 節 | 分類 | 責務・理由 / 移動先・削減条件 |
| --- | --- | --- |
| [AGENTS](../AGENTS.md) Purpose、Core Rules、Issue Selection、Issue / PR Rule、Prohibited Actions、Human Decision Points | KEEP | Issue仕様、範囲、依存、1子Issue=1 PR、Secrets禁止、main直接push/force push禁止、重要判断と人間Mergeを短く維持 |
| AGENTS Implementation Workflow、Before PR、Standard Verification Gate、GitHub Actions CI | MOVE_TO_DOCS | [標準フロー](nine-standard-ai-development-flow.md)と[検証雛形](../templates/verification/verify.sh)へ工程詳細を集約。検証不能・重大問題時の停止は常駐 |
| AGENTS Code Review Rules、Review Evidence Contract、Rule Promotion | KEEP / MOVE_TO_DOCS | 初回レビューの探索観点・証拠要件・Rule Promotionは一般レビューから到達できるAGENTS入口と正本に保持。専用docsへ移す場合は先に作成し、初回reviewから明示参照。既存指摘対応だけのpr-review-fixを唯一の保証先にしない |
| AGENTS 修正ループ | MOVE_TO_SKILL | [pr-review-fix](../.agents/skills/pr-review-fix/SKILL.md)に分類・同じbranch・SHA照合・再検証を集約。現head ReviewとBLOCKING停止は常駐 |
| AGENTS Plan Review、Plan to Issues Routing、Child Issue Quality Gate | MOVE_TO_SKILL | [plan-to-issues](../.agents/skills/plan-to-issues/SKILL.md)でGoal / Context / Boundaries / Done / Verification / Dependenciesを確認。重要未決は推測しない |
| AGENTS Framework Decision、AI / Codex Reference Contract、RAG Architecture、Design / State Modeling | MOVE_TO_DOCS | Framework / PRODUCT UI / RAG適用時だけ関連docsへ。Design / State Modelingは専用正本未整備のため、移動先確定前には消さない |
| AGENTS Adaptive Development Flow、Structured Current State、Parent Completion、Deployment / Acceptance詳細 | MOVE_TO_DOCS | Tier・schema・RC・artifact・検収詳細は既存正本へ。高リスク承認と未実施を成功にしない原則はKEEP |
| AGENTS Secrets、AI Agent Security Boundary、GitHub Guardrails、CodeQL、Dependabot、Security Preflight、Full-System Security Audit | KEEP / MOVE_TO_DOCS | 短い禁止・承認・失敗時停止はKEEP。情報分類や監査手順は条件付きdocsへ。Security script/workflowは維持 |
| AGENTS Harness Minimalism、Standard Codex Instruction、同じ工程の複数説明 | REMOVE_CANDIDATE | 毎Issueの台帳記入・長い指示例・重複説明を削減。境界・検証責務まで削らない |
| AGENTS AI生成ドキュメント原則、GitHub上の言語 | MOVE_TO_DOCS | 簡潔な日本語と必要情報の保持を最小ルールに残し、文章規範の詳細を参照へ |
| [README](../README.md) | KEEP / REMOVE_CANDIDATE | 用途と実利用フロー・入口はKEEP。AGENTS / guide / workflow説明の複製は縮小。PR前self-review欠落は#162と統合再判定 |
| [parent template](../.github/ISSUE_TEMPLATE/parent-issue.md) | KEEP / REMOVE_CANDIDATE | Goal、Context、Decision、Boundaries、子Issue/依存、全体DoneはKEEP。非該当Framework/UI/Harnessの常時欄は候補 |
| [child template](../.github/ISSUE_TEMPLATE/child-issue.md) | KEEP / REMOVE_CANDIDATE | Goal、Context、Scope/Boundaries、Non-goals、Done、Verification、DependenciesはKEEP。非該当欄とCurrent State毎回転記は候補 |
| AGENTS Test Design / Safe Test Deletion、PR Description | MOVE_TO_DOCS | テスト種別・削除前保証条件とPR記入手順を詳細正本へ。テスト弱体化禁止・検証証拠はKEEP |
| [PR template](../.github/pull_request_template.md) | KEEP / MOVE_TO_SKILL | 対応Issue、差分、検証、残存リスク・未解決事項はKEEP。細かなレビュー反復手順はSkillへ |
| plan-to-issues Skill | KEEP | Issue生成入口。現行の全案件UI分類、Framework引継ぎ、Plan Review出力を適用案件に限定する候補。生成だけの依頼では実装を始めない境界を維持 |
| pr-review-fix Skill | KEEP | 同じPRの修正と現headの収束。通常はCodexのみ。長いJEV / Local Judgeの手動運用説明は専用READMEへMOVE_TO_DOCS |
| [template-change-evaluator Skill](../.agents/skills/template-change-evaluator/SKILL.md) | REMOVE_CANDIDATE | 棚卸しには有用だが、テンプレ自己管理専用の常時routingは必須ではない。Issue上の採否判断で足りるか確認して任意参照化を判断 |

## docs / script / template / CIの責務

| 資産 | 分類 | 維持する責務 / 後続で整理する内容 |
| --- | --- | --- |
| [標準フロー](nine-standard-ai-development-flow.md)、[template-guide](template-guide.md) | MOVE_TO_DOCS | 短いREADMEから利用時参照。AGENTS / Skillとの手順複製を削減し正本を一本化 |
| [plan-authoring](plan-authoring.md)、[Plan Review](plan-review-gate.md)、[Issue quality](issue-quality-check.md) | MOVE_TO_SKILL / MOVE_TO_DOCS | Skillは判断手順、docsは詳細基準。Score・全案件の定型出力はREMOVE_CANDIDATE。重要未決・Scope/Done不足は停止 |
| [adaptive flow](adaptive-development-flow.md)、[execution state](ai-execution-state.md) | MOVE_TO_DOCS | リスク判断とartifact不一致停止を保持。全Issueへのschema/state記入強制は候補 |
| [agent security](ai-agent-security-boundary.md)、[repository security](github-repository-security-baseline.md)、[SECURITY](../SECURITY.md) | KEEP / MOVE_TO_DOCS | 最小権限・未承認送信・Secrets・repo保護の正本。SECURITYの例示support tableは実製品保証ではなく、採用案件で整備が必要 |
| [safe-auto-fix](safe-auto-fix-auto-merge.md) | MOVE_TO_DOCS | 現行の明示採用時のみの例外を保存。#168の標準フローには自動Mergeを導入しない |
| [deployment design](deployment-release-design.md)、[acceptance](acceptance-verification.md) | MOVE_TO_DOCS | Deploy / RC / 実利用検収がある案件で参照。merge成功とProduct Acceptanceを区別 |
| [review followups](review-followups.md)、[field lessons](field-validation-lessons.md) | MOVE_TO_SKILL / MOVE_TO_DOCS | 判断・残存事項を既存Issue/PRへ記録。中央台帳を更新するためだけのcommit・再Review連鎖は削減候補。追跡責務は保持 |
| [framework](architecture/framework-decision.md)、[RAG](architecture/rag-guidelines.md)、[PRODUCT UI](product-ui-standard.md) | MOVE_TO_DOCS | 採用・変更時のみ参照。非該当案件へNONE / NOT_APPLICABLEを大量要求しない |
| [HTML report](html-status-report.md) | MOVE_TO_DOCS | 必要な人向け出力でのみ使用。Markdown/JSON正本・エスケープ・入力非破壊を維持 |
| [instruction inventory](instruction-architecture-inventory.md)、[harness inventory](ai-development-harness-inventory.md) | REMOVE_CANDIDATE | 過去の根拠資料として参照を残す候補。毎Issueの更新義務と同じ正本の重複を削減。安全項目の所在を先に移す |
| [collect-github-state.py](../scripts/collect-github-state.py)、[render-status-report.py](../scripts/render-status-report.py) | KEEP | 読取観測・表示の任意ツール。収集失敗、古いSHA、HTML注入、上書き防止の回帰は残す |
| [Review scripts](../.agents/skills/pr-review-fix/scripts/) prepare-pr / verify-pr-head / wait-checks / wait-codex-review | KEEP | PR identity、現head、CI/Security分離、review本文・状態・thread停止条件。Bash 5前提を維持 |
| triage-with-jev.sh / triage-with-providers.py、[auto-triage](../templates/review-comment-auto-triage/) | MOVE_TO_DOCS | 手動比較専用として保持。通常レビューからの自動呼出は復活させない |
| [verify.sh](../templates/verification/verify.sh)、[verification README](../templates/verification/README.md) | KEEP | 生成projectの標準入口。lint→type→test→build、失敗・全skip時の停止 |
| [security-preflight.sh](../templates/security/security-preflight.sh) | KEEP | tracked file / symlink、依存ごとの監査、High/Critical停止、未監査を成功にしない |
| [app template](../templates/app/) | KEEP / MOVE_TO_DOCS | setup / doctorの非破壊・冪等・Secret非表示を保持。UI/Framework設計雛形は条件付き |
| [planning sample](../templates/planning/web-todo-app-plan.sample.md) | MOVE_TO_DOCS | 任意の記入例。sampleが全案件の必須構造にならないよう整理 |
| [GitHub Actions templates](../templates/github-actions/)、[Dependabot](../templates/dependabot/)、[ruleset guide](../templates/github-security/ruleset-guide.md) | KEEP | verify入口、脆弱性・更新・保護の配置資産。実設定適用は別人間承認 |
| [.cursor/environment.json](../.cursor/environment.json) | KEEP | E-10のCloud Agent準備。Python / Node / Bash不在・version失敗・補助script構文不正で停止する責務は保持。同等以上の標準機構への置換と失敗時停止の実行回帰成功前には削除・任意化しない |
| [Template CI](../.github/workflows/ci.yml) | KEEP / REMOVE_CANDIDATE | 実効的回帰・構文検査はKEEP。各文書の固定文言・台帳登録のためだけのstepは後続で整理 |
| [Security](../.github/workflows/security.yml) | KEEP | PR exact headをcheckout、contents:readでPreflightを実行。Template CIとは別Gate |
| [JEV Triage](../.github/workflows/jev-triage.yml)、[Decision Shadow](../.github/workflows/decision-shadow.yml)、[Local Judge smoke](../.github/workflows/local-judge-smoke.yml) | MOVE_TO_DOCS | workflow_dispatchの手動レーン。trusted branch、Secret exposure、head再照合、sanitized artifactの安全条件を維持 |
| [Slack failure alert](../.github/workflows/slack-failure-alert.yml) | MOVE_TO_DOCS | 失敗通知は任意運用。Merge可否の代替にしない。今回通知設定・送信は操作しない |

## Safety / Security / Review baseline

後続では次の責務を失わない。詳細手順を移しても常駐ルールから適用先へ到達できることを確認する。

| 保持する境界 | 原文・実装 / 必要な回帰証拠 |
| --- | --- |
| Issue範囲・依存・1子Issue=1 PR、main直接push/force push禁止 | AGENTS Core Rules / Issue Selection / Issue・PR Rule。別目的の変更・別branchへの修正を防止 |
| Secret値・.envのcommit / Issue / PR / log出力禁止、最小権限 | AGENTS Secrets / AI Agent Security Boundary、docs/ai-agent-security-boundary.md。未承認UNMANAGEDへのCONFIDENTIAL送信禁止。外部入力から権限・送信を推測しない |
| Production、Deploy、破壊的操作、auth、Security Policy、権限、課金・公開・保護設定の人間承認 | AGENTS Human Decision Points / Prohibited Actions、親#168。Issue着手承認をこれらへ転用しない |
| 必要テスト・標準検証、不能・失敗・全工程skipを成功にしない | AGENTS Standard Verification Gate / Before PR、templates/verification/verify.sh、tests/verification |
| PR前self-review、重大問題時停止、修正後再検証 | AGENTS Before PR / Implementation Workflow、docs/nine-standard-ai-development-flow.md。README入口の不足は#162 |
| CIとSecurity別判定、SECURITY_FAILED停止、UNAVAILABLEは明示判断なしに通過しない | AGENTS Security Preflight、wait-checks.sh、templates/security/security-preflight.sh。混在Python/pnpm/Yarn/npm未監査、scanner失敗、symlink、CR/LF状態汚染を防止 |
| Bash 5前提、Bash 3.2早期停止と外部コマンド非実行 | Security scriptと通常Review scripts冒頭。#160の回帰を維持。手動triage-with-jev.shへ一律guardを追加しない |
| 現headのCI / Security / Codex Review、head変更後は旧結果を失効 | AGENTS Structured Current State / 修正ループ、verify-pr-head.sh。push SHAとGitHub full SHA照合 |
| Review本文・状態も検査、P0/P1とBLOCKING P2停止、未解決thread確認 | wait-codex-review.sh / tests/pr-review-fix-jev/test-wait-codex-review.py。CHANGES_REQUESTED / DISMISSEDを成功にしない。Finding ID集計を維持 |
| P2四分類、同じPR branch修正、3ラウンド異常時の人間判断 | pr-review-fix Skill。非BLOCKING P2を機械的な追加修正ループへ戻さない。分類記録を削除しない |
| 通常レーンのMergeは人間、Auto-Mergeは本簡素化の標準にしない | AGENTS SeverityとMerge条件 / Safe Auto-Fix、親#168。現行例外を無承認で拡張しない |
| Deploy・実装・Product Acceptanceを区別、RC/artifact identity不一致を通過させない | docs/deployment-release-design.md / acceptance-verification.md / ai-execution-state.md。適用案件だけ詳細を参照しても責務は保持 |
| テスト削除前に責務と保証先を確認 | AGENTS Test Design / Safe Test Deletion。移行先テスト成功→旧テスト整理、認証/入力/永続化/重要E2Eを維持 |

baselineは現行repoの契約・実装を固定したもの。branch protectionの実設定、Secrets登録状態、外部サービスの稼働・課金状態は本棚卸しでは確認していない。workflowの存在だけを保護有効化・運用成功の証拠にしない。

## 28テスト入口の責務と削減判断

「実害回帰」はコード実行・失敗時停止・非破壊等を検証。「文書契約」は文言・欄・配置の検査。「混在」は両方を含む。文書契約にも安全規則が含まれるため、カテゴリだけで一括削除しない。各リンクの `run-samples.sh` と呼出先を原文で確認した。

| `tests/` 系統 | 現行責務 / 種別 | 分類と保証先 |
| --- | --- | --- |
| [verification](../tests/verification/run-samples.sh) | 標準入口の成功・失敗・未導入・skip / 実害回帰 | KEEP。verify.sh責務を保持 |
| [app-template](../tests/app-template/run-samples.sh) | setup / doctorの冪等・.env・health/port・Secret / 実害回帰 | KEEP。生成appの非破壊・安全診断 |
| [security-preflight](../tests/security-preflight/run-samples.sh) | 混在依存、Secret、symlink、状態汚染、Bash guard / 混在 | KEEP。marker削減でも実行回帰は保持 |
| [pr-review-fix-jev](../tests/pr-review-fix-jev/run-samples.sh) | Shadow clientのfallback/非権威、Skill marker、Codex review判定 / 混在 | KEEP。Codex待機判定を手動JEV責務と分離して保証する候補。入口の丸ごと削除禁止 |
| [review-comment-auto-triage](../tests/review-comment-auto-triage/run-samples.sh) | Node decision/schema/認証・入力等 / 実害回帰 | KEEP。手動資産を残す間の安全検証 |
| [local-judge](../tests/local-judge/run-samples.sh) | provider/transport/server/evaluation/手動workflow / 混在 | KEEP。手動資産のSecret・baseline非権威・入力回帰 |
| [github-state](../tests/github-state/run-samples.sh) | read-only収集、異常API、ページ、head identity / 実害回帰 | KEEP。collectorを残す間の観測保証 |
| [html-status-report](../tests/html-status-report/run-samples.sh) | escaping、入力非破壊、上書き/不正schema拒否 / 実害回帰 | KEEP。rendererを残す間の安全保証 |
| [instruction-architecture](../tests/instruction-architecture/run-samples.sh) | 配置marker + HEAD/refs/index/worktreeの非変更 / 混在 | KEEP / REMOVE_CANDIDATE。read-only実行保証は保持、台帳の固定構造は候補 |
| [harness-minimalism（固定baseline）](https://github.com/second-works/ai-development/blob/7a52b2b3f46487b91190a6c923926c9325913046/tests/harness-minimalism/run-samples.sh) | 台帳marker、workflow登録、Cloud Agent install失敗時停止、他suite間接呼出 / 混在 | KEEP / REMOVE_CANDIDATE。181–199行のCloud Agent実行回帰（Bash不在・Bash version失敗伝播）はKEEPとして分離。子suiteの直接CI化だけでは代替できない。具体的な独立回帰入口へ移してCI成功を先に確認するまで現行入口を保持。自主管理markerだけ整理候補 |
| [jev-triage-workflow](../tests/jev-triage-workflow/run-samples.sh) | trusted checkout/Secret/head/artifact配置 + YAML parse / 混在 | KEEP。手動経路の安全検証。単なる表示markerだけ整理候補 |
| [agent-security-boundary](../tests/agent-security-boundary/run-samples.sh) | 安全規則のmarker / 文書契約 | KEEP。最小境界と参照に合わせて縮小。実行Security検査の代替ではない |
| [review-evidence](../tests/review-evidence/run-samples.sh) | P2 / evidence / Pre-PR規則のmarker / 文書契約 | KEEP / REMOVE_CANDIDATE。Skillの停止・分類責務を保持し重複markerを削減 |
| [safe-auto-fix](../tests/safe-auto-fix/run-samples.sh) | opt-in / 通常復帰のmarker / 文書契約 | MOVE_TO_DOCS。例外資産を残すなら最低限の禁止・停止契約を維持 |
| [acceptance-verification](../tests/acceptance-verification/run-samples.sh) | 検収・artifact・状態分離のmarker / 文書契約 | MOVE_TO_DOCS。適用案件の責務を保持し常時記入契約は候補 |
| [verification-evidence](../tests/verification-evidence/run-samples.sh) | 検証結果・証拠契約marker / 文書契約 | MOVE_TO_DOCS。実施/未実施・対象識別と根拠は維持 |
| [deployment-design](../tests/deployment-design/run-samples.sh) | Deploy / RC監査marker / 文書契約 | MOVE_TO_DOCS。適用時の人間承認・identity停止は保持 |
| [current-state](../tests/current-state/run-samples.sh) | schema/遷移/重複記入marker / 文書契約 | REMOVE_CANDIDATE。毎Issueの定型Stateは削減。artifact不一致停止を関連正本/検証へ保持 |
| [adaptive-development-flow](../tests/adaptive-development-flow/run-samples.sh) | Tier / 必須Gate marker / 文書契約 | REMOVE_CANDIDATE。Tier定型出力削減。HIGH境界と失敗時停止を残す |
| [issue-quality](../tests/issue-quality/run-samples.sh) | MUST / SHOULD / Score marker / 文書契約 | REMOVE_CANDIDATE。Scope/Done/Verification/依存/安全境界はSkillで確認、Score維持を必須にしない |
| [template-simplification](../tests/template-simplification/run-samples.sh) | template/台帳/guide marker / 文書契約 | REMOVE_CANDIDATE。新最小templateの意味確認へ置換後に旧欄検査を整理 |
| [plan-review-gate](../tests/plan-review-gate/run-samples.sh) | 全案件Framework/UI/Plan章・順序marker / 文書契約 | REMOVE_CANDIDATE。重要未決時停止と適用時参照をSkillへ保証 |
| [plan-to-issues](../tests/plan-to-issues/run-samples.sh) | Skill routing/登録後境界marker / 文書契約 | KEEP / REMOVE_CANDIDATE。Issue-only依頼の境界と必要仕様を残し重複手順markerを整理 |
| [product-ui-standard](../tests/product-ui-standard/run-samples.sh) | UI詳細/判断/参照marker / 文書契約 | MOVE_TO_DOCS。PRODUCT適用時の参照と検証責務を保持 |
| [issue-template-ui](../tests/issue-template-ui/run-samples.sh) | UI/Framework欄・参照marker / 文書契約 | REMOVE_CANDIDATE。非UIの常時欄をなくす際に更新。重要UI判断の保証先はdocs/案件Issue |
| [pr-review-followups](../tests/pr-review-followups/run-samples.sh) | 台帳記入・再SHA・分類marker / 文書契約 | REMOVE_CANDIDATE。追跡はIssue/PRへ集約、現head再検証をSkillへ保持 |
| [document-concision](../tests/document-concision/run-samples.sh) | 文章原則marker / 文書契約 | REMOVE_CANDIDATE。固定文言より生成Issueの読解dry-runで検証 |
| [template-change-evaluator](../tests/template-change-evaluator/run-samples.sh) | 自己管理Skill/routing marker / 文書契約 | REMOVE_CANDIDATE。Skill任意化の決定後に関連固定文言検査を整理 |

棚卸し基準mainで直接stepがない6入口は `github-state / current-state / html-status-report / adaptive-development-flow / issue-quality / template-simplification`。棚卸し基準mainのHarness suiteはこの6入口すべてを間接呼出している。HTMLは205行、他5入口は末尾で実行される。**直接stepなし=未実行ではない**。棚卸し基準CIには28入口の直接または間接実行経路があり、#161の提案は間接依存をなくして各入口の直接登録を保証する変更として区別する。

PR #167は28入口の直接実行と `tests/harness-minimalism/test-ci-entrypoints.py` の独立実行を提案中。これはmainに存在しない追加メタテストで、#168の削減候補に含めるが削除済みとは扱わない。安全回帰のCI保証と、全旧文書contractの無条件登録を別責務として再判定する。

## #157 / #161〜#163の再判定案

2026-10-03のGitHub読取では全4 Issueがopen、PR #167もopen。以下は人間判断用の案で、close/mergeの実行ではない。

| 対象 | 案 | 重複・競合 / 完了を判断する条件 |
| --- | --- | --- |
| #157 | 継続範囲を分離 | #158〜#160のmain取り込み済み安全修正はKEEP。#161/#162は簡素化計画へ接続し、#163の保護は独立。元の全体完了条件を自動で満たした扱いにしない |
| #161 / PR #167 | 保留してPhase 4で再判定 | 未マージPR head `023282356db2ea2f02af147770c4f35cdbabbb26`。全旧contract必須登録は#168と競合。安全回帰入口を保証する目的はKEEP。今すぐmerge/closeせず、人間判断で継続・仕様更新・統合候補を決める |
| #162 | 新READMEフローへ統合候補 | self-reviewの実効的停止条件は維持。旧READMEへの局所追加よりPhase 2/5の新フロー確定後に再判定。旧Issueは自動closeしない |
| #163 | 独立継続候補 | main保護は有用なSecurity責務。設定適用は本承認外。過去のprotected=false/403を現在の実設定として断定せず、このIssue実施時に再取得 |

#157の「次は#161」と#168の「#161保留」は競合する。今回のユーザー指定対象は#168であり、その棚卸し優先・保留方針に従う。#161のCI実装を本PRへ混ぜない。

## 人間確認後の次の実装単位

1. Phase 2: AGENTS最小契約とparent/childの必須・条件付き項目を確定。今回の移動案・削減条件を確認してから子Issue化。
2. Phase 3: Review反復手順をpr-review-fix、Issue生成判断をplan-to-issues、専門仕様を既存docsへ集約。旧参照先を壊さない。
3. Phase 4: 回帰責務の保証先を先に成功させ、旧marker/台帳メタ検査を段階整理。#161とCIの扱いを同時に確定。
4. Phase 5: 最小templateでサンプルIssue生成とScope/Done/Verification読解、標準フローdry-run、安全境界、README、既存project互換を確認。#162を再判定。

後続の大量削除・Gate意味変更・Security停止条件緩和は親#168の人間確認境界に従う。この文書のmergeだけを、その実施承認・親Issue全体のAcceptanceと解釈しない。

## Phase 1の検証記録

- 変更は本書のみ。既存AGENTS / Skill / template / script / test / workflowは変更しない。
- 28サンプル入口すべて成功。Bash 5.3.15、互換Git、合成fixture用localhost socketを利用できる環境で実施。通常PRでJEV / Local Judgeの外部比較評価を起動していない。
- 初回sandbox内のsocket拒否、Python cache書込制限、子processがBash 3.2を選んだ失敗は環境を訂正して再検証。失敗を成功扱いにせず、再実行結果を採用した。
- 相対リンクの存在、28系統の列挙、ファイルサイズ、CI直接step、間接呼出、原文の安全条件と禁止範囲を照合。Pre-PR self-reviewで重大な問題なし。
- この管理repositoryには `scripts/verify.sh` がなく、生成project用原本は `templates/verification/verify.sh`。管理repoの既存28入口を標準の検証対象として実行した。
- 現headのGitHub CI / Security / Codex Reviewの証拠はPRに記録する。人間の棚卸し確認・Merge・後続変更承認は未完了。

## PR #170のレビュー修正

P2 3件をBLOCKINGと判断し、#169の原文根拠・安全保証先・CI観測の完了条件違反として修正した。初回レビューの入口と探索/証拠/Rule PromotionをKEEPし、反復修正だけSkillへ移す。Cloud Agent install回帰をKEEPとして分離し、代替入口のCI成功前は削除しない。HTMLを含む全6入口のHarness経由実行を原文で再照合した。既存ルール・test・CIの変更はない。

## 移行進捗（2026-10-04）

本書の件数・byte数・分類は上記固定baselineの記録。PR #170 / #172 / #174は人間指示でマージ済み。Issue #175で残る運用・安全責務を既存docsへ保存する。AGENTS短縮、参照テスト変更、Gate削減、生成サンプル検収は後続であり、この棚卸しから完了と推定しない。

Issue #177: 詳細責務を正本へ移し、root AGENTSを合意済み最小本文へ切り替える。28系統の実行回帰とCIを保持し、文書markerの検査先だけを正本へ変更する。Phase 4のtest削減・Phase 5の生成サンプル検収は未完了。

Issue #179: 親子Issueとplan-to-issuesの最小入力を有効化する。非該当のUI / Framework / Harness / State欄を省略し、Riskと安全境界、MUST不足・未決定時停止を保持。文書見出し検査の同期と記入例3件・負例13件を追加するが、既存28入口の削除やCI縮小は行わない。Phase 4 / 5の実行受入は後続である。

### Issue #181: Phase 4の独立保証先

棚卸し表の分類を一括削除へ転用しない。Cloud Agent実行回帰と間接6suiteの独立入口を先に成功させ、Harnessへの依存を外す。

| 移行責務 | 保持する保証先 / 判断 |
| --- | --- |
| Cloud Agent installのBash不在・version失敗伝播 | [独立実行回帰](../tests/cloud-agent-environment/run-samples.sh)、CIのCloud Agent step。KEEP。実設定を隔離fixtureへ適用し正常compile/構文不正も確認 |
| 間接6suiteの実行 | 各既存run-samples.shとCI独立step。29入口を直接実行し、台帳文書検査の削減と実行網羅を分離 |
| Harnessの文書/台帳契約 | 元入口を保持。旧2異常系と6呼出だけ代替成功後に移行し、marker削減は別の責務判断へ |

代替追加head `6da4ffd001d925cb9672cdc7496812a598763f21` の29 suite、CI #1052、Security #346と各独立step成功を移行前に確認した。原文の2異常系を維持し、既存6suiteの本体は変更しない。#161/PR #167のメタ検査は追加・merge・closeしていない。最終headの検証結果はPR本文を正本とする。

### Issue #183: Harness台帳検査の削減

#181/PR #182で実行回帰と間接6suiteを独立させた後、残る345行の台帳schema・ID・集約表一致・固定文言・CI登録だけの検査を削減する。台帳書式の機械的強制は最小フローに不要と判断する。安全正本、Security/Review停止条件、他28suiteは保持する。実行回帰を代替成功前に消さない。2026-10-04に人間が提示差分の適用を個別承認した。

| 対象 | 保証先 / 理由 |
| --- | --- |
| 台帳12欄・ID・enum・集約表一致 | 台帳は参照資料として保持。書式一致をCI条件にする責務は不要 |
| Cloud Agent install / 旧間接6suite | tests/cloud-agent-environmentと各既存suiteの独立CI。PR #182の現head CI成功済み |
| Security / Human Approval / State・Deploy identity | AGENTSと各安全正本・既存suiteを変更せず保持 |
| 条件付き参照・最小Issue・安全な検証削除 | instruction-architecture / plan-to-issues / template-simplification、AGENTS / minimal-development-contract / test-design正本を維持 |
| PRODUCT UI / Issue UIのCI | 既存独立stepを維持し、Harnessから同じ配線を再検査する追加メタ検査は削減 |

CI権限contents: read、timeout 10分、Security workflowは変更しない。他の28入口は全て直接CI実行する。残る文書suiteには安全責務があるため一括削除しない。過去baselineの削除入口リンクは固定commit参照へ直し、Harness台帳L-01/L-03から削除入口への現行参照と台帳schemaのCI必須扱いを外す。適用後に28suiteと同じ最終headのCI/Security/Codex Reviewを確認する。Phase 5受入は後続。

## Issue #185: 最小フローの実利用受入

READMEをIssue生成・Codex実装の入口へ同期する。最小Issue #181/#183/#185、直接コメント修正、guideの実copyと非上書き、生成verify正常/失敗時停止、安全境界、旧Issue #157/#161〜#163の再判定は [実利用受入記録](simplification-acceptance.md) を参照する。最終headのCI/Security/Reviewと親の完了照合はPRとGitHub親 #168へ記録する。検証前の結果を完了としない。
