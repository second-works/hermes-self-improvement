# Instruction Architecture Inventory

本書の旧AGENTS節名・byte数・routing表は当時の固定監査記録。Issue #177以降の現行正本・参照入口は [最小契約の移行表](minimal-development-contract.md#旧agentsとの移行対応) とroot AGENTSに従う。通常レビューはSkillを自動起動せず、[review正本](code-review-contract.md)を使ってCodexが直接対応する。


## Decision First

Issue #121では、既存の機能・Safety Gate・検証責務を移動または削除せず、Instructionの配置判断を先に記録する。

常時必要な停止条件と判断入口は `AGENTS.md` に残し、詳細仕様は `docs/`、反復手順は `.agents/skills/`、決定的な判定は `scripts/`・`tests/`・CI、入力欄はIssue / PR templateへ分ける。

実際の移動・統合・削除は、この台帳の判断をレビューした後に、影響範囲ごとの子Issueへ分割する。

## Scope and classification

| 分類 | 意味 | 主な配置 |
| --- | --- | --- |
| `RESIDENT` | すべての作業で最初に必要な禁止事項、停止条件、基本境界 | `AGENTS.md` |
| `ENTRYPOINT` | 条件発生時に正本文書を取得する短い入口 | `AGENTS.md` → `docs/` |
| `CANONICAL_DETAIL` | 設計仕様、状態、判断基準、背景の正本 | `docs/` |
| `REPEATABLE_EXECUTION` | 特定作業を再現する手順とスクリプト | `.agents/skills/`, `templates/` |
| `MECHANICAL_CHECK` | 機械的に判定できる契約、テスト、CI | `scripts/`, `tests/`, `.github/workflows/` |
| `INPUT_CONTRACT` | Issue / PR作成時に埋める今回値 | `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` |
| `TOOL_OR_PROJECT_CONFIG` | Codexや個別プロジェクトの実行設定 | `.codex/`, `.cursor/`, 各プロジェクト |
| `ISSUE_ONLY` | 今回だけの要求、Acceptance、Design Decision | GitHub Issue / PR |

配置は排他的ではない。同じテーマが複数層に現れる場合は、`AGENTS.md`に短い適用条件、正本文書に詳細、templateに今回値、test/CIに機械判定を置く。

## Baseline and change boundary

- 基準: `main` の `1f48747`（2026-09-20取得）。
- 変更前の `AGENTS.md`: **47,136 bytes**。
- Issue #121の実装では、まずこの台帳とread-only smoke testを追加する。
- 既存ルールの意味を変える移動・削除・統合、Safety / Security / Review / Acceptance / Human Merge条件の弱体化は行わない。
- `AGENTS.md`変更後のサイズは、同じcheckoutで `wc -c AGENTS.md` を再実行して記録する。

## AGENTS.md section inventory

| `AGENTS.md` section | 現在の分類 | 再配置候補 | 旧→新の参照経路（候補） | 正本または参照先 | 今回の扱い / 判断理由 |
| --- | --- | --- | --- | --- | --- |
| `Purpose` | `RESIDENT` | `KEEP` | `AGENTS.md#Purpose` → `AGENTS.md#Purpose` | `docs/instruction-architecture-inventory.md` | 台帳入口として短いまま残す。 |
| `Core Rules` | `RESIDENT` | `SHORTEN+REFERENCE` | `AGENTS.md#Core Rules` → 短い常駐規則 → Issue / 各正本文書 | Issue / PR rule、各正本文書 | 基本禁止事項だけを常駐し、工程詳細は正本へ移す候補。 |
| `Core Rules > Template Change Evaluation Routing` | `ENTRYPOINT` | `KEEP` | `AGENTS.md#Template Change Evaluation Routing` → `.agents/skills/template-change-evaluator/SKILL.md` | `.agents/skills/template-change-evaluator/SKILL.md` | テンプレート改善の採否・重複・配置判断だけを起動し、詳細な反復手順はSkillへ委譲する。単純要約や一般質問には適用しない。 |
| `AI生成ドキュメント原則` | `RESIDENT` | `KEEP` | `AGENTS.md#AI生成ドキュメント原則` → 同節 | Issue / PR template | 文書生成時の常時判断。 |
| `Adaptive Development Flow / Risk Tier` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Adaptive Development Flow / Risk Tier` → `docs/adaptive-development-flow.md` | `docs/adaptive-development-flow.md` | HIGH停止条件は残し、判定詳細を委譲する。 |
| `Design / State Modeling` | `RESIDENT` | `MOVE` | `AGENTS.md#Design / State Modeling` → 将来 `docs/design-state-modeling.md`（子Issue） | 各案件の型・schema・信頼境界 | 専用正本がないため今回は維持し、作成後に短い入口へする。 |
| `Structured Current State` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Structured Current State` → `docs/ai-execution-state.md` | `docs/ai-execution-state.md` | schema、enum、遷移は正本へ。 |
| `GitHub上の言語` | `RESIDENT` | `KEEP` | `AGENTS.md#GitHub上の言語` → 同節 | README、Issue / PR template | 外部文章の常時方針。 |
| `Plan Review Gate` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Plan Review Gate` → `docs/plan-review-gate.md` | `docs/plan-review-gate.md` | 判定と出力形式は正本へ。 |
| `Plan Review Gate > Plan to Issues Routing` | `ENTRYPOINT` | `KEEP` | `AGENTS.md#Plan to Issues Routing` → `.agents/skills/plan-to-issues/SKILL.md` | `.agents/skills/plan-to-issues/SKILL.md` | 合意済み計画をIssue化する反復手順だけをSkillへ委譲し、Framework / Plan Review / Risk / Child Issue Qualityの詳細は各正本を参照する。 |
| `Framework Decision` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Framework Decision` → `docs/architecture/framework-decision.md` | `docs/architecture/framework-decision.md` | 発火条件だけを残す。 |
| `AI / Codex Reference Contract` | `RESIDENT` | `SHORTEN+REFERENCE` | `AGENTS.md#AI / Codex Reference Contract` → `docs/product-ui-standard.md` / 案件 `docs/design.md` | `docs/product-ui-standard.md`、案件 `docs/design.md` | PRODUCT UIの参照順序を短く保つ。 |
| `Child Issue Quality Gate` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Child Issue Quality Gate` → `docs/issue-quality-check.md` | `docs/issue-quality-check.md` | MUST / SHOULD / Scoreは正本へ。 |
| `Issue Selection` | `RESIDENT` | `KEEP` | `AGENTS.md#Issue Selection` → 同節 | GitHub Issue | 依存不明時の停止条件。 |
| `Issue / PR Rule` | `RESIDENT` | `KEEP` | `AGENTS.md#Issue / PR Rule` → 同節 | Issue / PR template | 作業単位と実装前確認の共通入口。 |
| `RAG Architecture Standard` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#RAG Architecture Standard` → `docs/architecture/rag-guidelines.md` → 案件 `rag-design.md` | `docs/architecture/rag-guidelines.md` | template本体に案件固有空ファイルは置かない。 |
| `Test Design / Safe Test Deletion` | `ENTRYPOINT` | `MOVE` | `AGENTS.md#Test Design / Safe Test Deletion` → 将来専用test-design doc（子Issue） | `docs/nine-standard-ai-development-flow.md`、各プロジェクトのtests | 専用正本化までは現行参照を維持する。 |
| `Implementation Workflow` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Implementation Workflow` → `docs/nine-standard-ai-development-flow.md` | `docs/nine-standard-ai-development-flow.md` | 手順全文を常駐させない。 |
| `Standard Verification Gate` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Standard Verification Gate` → `templates/verification/verify.sh` / `docs/template-guide.md` | `templates/verification/verify.sh`、`docs/template-guide.md` | template本体と生成先の境界を明示する。 |
| `Parent Issue Completion` | `ENTRYPOINT` | `KEEP` | `AGENTS.md#Parent Issue Completion` → `AGENTS.md#Parent Issue Completion` | `AGENTS.md#Parent Issue Completion` | 子Issue checkbox、全体完了条件、残課題切り出し、人間確認を含む実在の移動先はまだない。正本を収容する子Issueが完了するまで現行の発火入口と詳細契約を維持する。 |
| `GitHub Actions CI` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#GitHub Actions CI` → `.github/workflows/ci.yml` / `templates/github-actions/` | `.github/workflows/ci.yml`、`templates/github-actions/` | 実行コマンドはworkflow / templateを正本とする。 |
| `Code Review Rules` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Code Review Rules` → `docs/nine-standard-ai-development-flow.md` | `docs/nine-standard-ai-development-flow.md` | 起動と探索範囲だけを常駐させる。 |
| `Review Evidence Contract` | `CANONICAL_DETAIL` | `KEEP` | `AGENTS.md#Review Evidence Contract` → 同節 → 詳細複製（標準フロー / Skill）・意図的要約（README / template guide / harness inventory / execution state）・PR template | `AGENTS.md#Review Evidence Contract` | 現行の詳細正本。全出現層と、詳細複製を短縮する順序、意図的要約が正本を上書きしない境界はIA-02で追跡する。PR templateは今回値の入力欄に限る。 |
| `Rule Promotion` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Rule Promotion` → `docs/nine-standard-ai-development-flow.md` | `docs/nine-standard-ai-development-flow.md` | 自動昇格しない入口。 |
| `Harness Minimalism` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Harness Minimalism` → `docs/ai-development-harness-inventory.md` | `docs/ai-development-harness-inventory.md` | 台帳と再評価条件を正本へ。 |
| `GitHub Guardrails` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#GitHub Guardrails` → `docs/github-repository-security-baseline.md` | `docs/github-repository-security-baseline.md` | Ruleset等の詳細をSecurity正本へ。 |
| `Dependabot` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Dependabot` → `templates/dependabot/` / `docs/template-guide.md` | `templates/dependabot/`、`docs/template-guide.md` | template選択と運用詳細を分離する。 |
| `Secrets` | `RESIDENT` | `KEEP` | `AGENTS.md#Secrets` → 同節 → `docs/ai-agent-security-boundary.md` | `docs/ai-agent-security-boundary.md` | 漏えい禁止と停止条件は常駐。 |
| `AI Agent Security Boundary` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#AI Agent Security Boundary` → `docs/ai-agent-security-boundary.md` | `docs/ai-agent-security-boundary.md` | 境界判定詳細を委譲する。 |
| `CodeQL / Code Scanning` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#CodeQL / Code Scanning` → Security baseline / CodeQL template | `docs/github-repository-security-baseline.md`、`templates/github-actions/codeql.yml` | 利用可否とworkflowを参照する。 |
| `Security Preflight` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Security Preflight` → `templates/security/security-preflight.sh` → 生成先 `scripts/security-preflight.sh` | `templates/security/security-preflight.sh` | template本体と生成先を区別する。 |
| `Full-System Security Audit` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Full-System Security Audit` → `docs/deployment-release-design.md` | `docs/deployment-release-design.md` | Release Candidate時だけ取得する。 |
| `Before PR` | `ENTRYPOINT` | `SHORTEN+REFERENCE` | `AGENTS.md#Before PR` → `docs/template-guide.md` / PR template | `docs/template-guide.md`、PR template | 標準検証の入口を示す。 |
| `PR Description` | `INPUT_CONTRACT` | `MOVE` | `AGENTS.md#PR Description` → `.github/pull_request_template.md` | `.github/pull_request_template.md` | 詳細な今回値はtemplateへ集約する候補。 |
| `Prohibited Actions` | `RESIDENT` | `KEEP` | `AGENTS.md#Prohibited Actions` → 同節 | `docs/ai-agent-security-boundary.md` | 常時適用の禁止事項と停止条件。 |
| `Human Decision Points` | `RESIDENT` | `KEEP` | `AGENTS.md#Human Decision Points` → 同節 | Issue / PR | AIが推測で決めない境界。 |
| `Standard Codex Instruction` | `ENTRYPOINT` | `MOVE` | `AGENTS.md#Standard Codex Instruction` → README / `docs/template-guide.md` | README、`docs/template-guide.md` | 実行依頼例を正本へ移す候補。 |

本表は `AGENTS.md` の現行35トップレベルセクション（`##`）をすべて列挙し、追加のroutingサブセクション（`###`）は親セクション直下のENTRYPOINT行として追跡する。`MOVE` と `SHORTEN+REFERENCE` は候補であり、今回のPRでは実行しない。実行する子Issueでは、表の旧→新経路、適用漏れ、サイズ差分、失敗時の停止を更新してから移動する。

## Overlap, contradiction, and source-of-truth ledger

| ID | 検出した重複・競合 | 関係する層 | 正本 / 判断 | 結果と後続 |
| --- | --- | --- | --- | --- |
| IA-01 | 開発フローが `AGENTS.md`、README、template guide、標準フローに現れる。 | AGENTS / README / docs / template | `docs/nine-standard-ai-development-flow.md` を詳細正本、AGENTSは発火入口、README / templateは利用導線。 | 意味上の矛盾なし。`Implementation Workflow` を `SHORTEN+REFERENCE` 候補にする。 |
| IA-02 | Review Evidence Contractが、詳細正本、詳細複製、実行・状態・templateの要約または入力欄、機械判定に分散する。完全な出現層と責務は直後のIA-02 layer mapに列挙する。 | AGENTS / README / docs / Skill / tests / PR template | 現行の詳細正本は `AGENTS.md#Review Evidence Contract` とする。詳細複製は正本競合、意図的要約は適用文脈だけを担い、テストは意味を定義しない機械判定、PR templateは今回値の入力契約である。 | 正本競合は未解消として記録する。詳細複製は正本参照入口へ短縮する子Issueの対象とし、要約層は正本を再定義せず、テスト層は正本変更と同一PRで期待値を更新する。 |
| IA-03 | 検証入口がAGENTS、`templates/verification/verify.sh`、template CIに現れる。 | AGENTS / templates / CI | 生成先の実行正本は `scripts/verify.sh`、template本体は `templates/verification/verify.sh`、このrepositoryの実行記録は `.github/workflows/ci.yml`。 | 対象リポジトリと生成先を混同しない。CIがtemplate内の未実行workflowを成功扱いしない。 |
| IA-04 | Securityの説明がAGENTS、security boundary doc、Preflight script、Security workflowに分散する。 | AGENTS / docs / scripts / CI | 判断基準は `docs/ai-agent-security-boundary.md`、機械判定はPreflight scriptとSecurity workflow。 | 意味上の矛盾なし。Secrets停止条件はRESIDENTのまま維持する。 |
| IA-05 | Current Stateの概要がAGENTSと詳細schemaに現れる。 | AGENTS / docs | `docs/ai-execution-state.md` がschema / enum /遷移の正本。 | `Structured Current State` は `SHORTEN+REFERENCE` 候補。 |
| IA-06 | RAGの共通規則と案件固有設計が混同され得る。 | AGENTS / docs / Issue | 共通正本は `docs/architecture/rag-guidelines.md`、`rag-design.md` はRAG採用案件だけの成果物。 | template repositoryに空の `rag-design.md` を作らない。 |
| IA-07 | Codex configとCursor configを共通ルールとして固定する誘惑がある。 | config / Issue / docs | host・version・secret・network境界を伴う設定は案件Design Decisionが正本。 | `.codex/config.toml` とoverride機構は採用判断を子Issueへ延期する。 |

### IA-02 Review Evidence layer map

`rg -n "Review Evidence Contract|成立条件.*期待結果|V-02 Review Evidence|PR Causality|Evidence不足|BLOCKING / IN-SCOPE FIX / FOLLOW-UP / DISMISS|非BLOCKING P2" README.md docs .agents .github tests` で見つかる出現層を、正本競合か、正本を代替しない文脈要約か、機械判定か、今回値の入力欄かで区別する。単なる正本への参照も含め、以下の層をIA-02の判断対象から除外しない。

| 層 | 現在のpath / 役割 | 現在の扱い | 判断と後続 |
| --- | --- | --- | --- |
| 詳細正本 | `AGENTS.md#Review Evidence Contract`。field、証拠不足時の扱い、PR因果、受入条件、再現または静的根拠、Dispositionを定義する。 | `CANONICAL_DETAIL` | `KEEP`。他層と矛盾した場合はこの節を優先する。 |
| 詳細複製 | `docs/nine-standard-ai-development-flow.md`。Review Evidence、BLOCKING、P2分類、Verification Evidence境界を工程手順として再記述する。 | 正本競合 | 子Issueで正本参照入口へ `SHORTEN+REFERENCE` する。工程の発火順だけを残し、field schemaを再定義しない。 |
| 詳細複製 | `.agents/skills/pr-review-fix/SKILL.md`。修正ラウンドで使う必須field、分類、停止条件を再記述する。 | 正本競合 | 子Issueで正本参照入口へ `SHORTEN+REFERENCE` する。反復手順と停止時の人間引継ぎだけを残す。 |
| 利用者向け要約 | `README.md`。レビュー修正ラウンド、BLOCKING条件、Review Evidenceに必要な根拠を短く案内する。 | `ENTRYPOINT_SUMMARY` | 意図的な概要として `KEEP`。詳細fieldの列挙や独自の成立条件は追加せず、正本変更時は正本への参照と矛盾しないかを確認する。 |
| project template要約 | `docs/template-guide.md`。生成先projectのreview記録にReview Evidenceを使うことを短いchecklistで案内する。 | `ENTRYPOINT_SUMMARY` | 意図的な概要として `KEEP`。生成先の詳細契約ではなく、詳細fieldは `AGENTS.md#Review Evidence Contract` を参照する。 |
| Harness台帳要約 | `docs/ai-development-harness-inventory.md#V-02`。V-02の入力、四分類、停止・再評価条件を、Harnessが担う失敗モードと運用コストの文脈で記録する。 | `INTENTIONAL_INVENTORY_SUMMARY` | `KEEP`。Review Evidenceのfield schemaやSeverity判定の正本にはせず、Harnessの採否・再評価の説明だけを担う。V-02を変更する子Issueでは正本との整合を確認する。 |
| State連携要約 | `docs/ai-execution-state.md`。Current StateにP2分類とevidence参照を保存する際の連携条件を示す。 | `STATE_INTEGRATION_SUMMARY` | `KEEP`。State schemaの更新手順だけを担い、Review Evidenceの成立条件・field schemaを再定義しない。 |
| 機械判定 | `tests/review-evidence/run-samples.sh`。AGENTS、Skill、標準フロー、PR templateの必須field、BLOCKING条件、P2収束条件を検査する。 | `MECHANICAL_CHECK` | `KEEP`。正本ではなく期待値を検査する層であり、正本または詳細複製を短縮する同一PRで期待値を更新する。 |
| 機械判定の参照 | `tests/instruction-architecture/run-samples.sh`、`tests/template-simplification/run-samples.sh`、`tests/verification-evidence/run-samples.sh`、`tests/pr-review-followups/run-samples.sh`。台帳の出現層、PR template、Verification Evidence、FOLLOW-UPの四分類と非BLOCKING P2の接続を検査する。 | `MECHANICAL_CHECK` | `KEEP`。Review Evidenceの語句を参照してもfield schemaを定義しない。正本変更時は `tests/review-evidence/run-samples.sh` と併せて同一PRで更新・実行する。 |
| 今回値の入力欄 | `.github/pull_request_template.md`。レビューround、Finding、Disposition、根拠URLなどをPRごとに記録する。 | `INPUT_CONTRACT` | `KEEP`。正本のfield意味を変更せず、今回の値を受け取る欄だけを担う。 |

この棚卸しでは、上表以外に既存Gateを弱める意味上の矛盾は検出しなかった。未決定項目を「矛盾なし」と扱わず、後続欄に明示した。

## Layer boundary

### `AGENTS.md`

AIが毎回最初に読む共通境界。Issueを仕様の基準にすること、範囲外変更・秘密情報・直接main変更の禁止、HIGHリスクや人間判断で停止すること、条件発生時の正本文書への参照だけを置く。

### `docs/`

設計原則、状態schema、Gate、Security、Acceptance、レビュー証跡など、条件発生時に取得する詳細仕様を置く。`AGENTS.md`と同じ詳細を全文複製しない。

### `.agents/skills/` and `templates/`

反復する特定作業の実行手順と、生成先へコピーする雛形を置く。Skillは適用範囲と停止条件を明記し、templateは生成先での配置先を明記する。現行repo-local Skillとして `.agents/skills/pr-review-fix/SKILL.md`、`.agents/skills/template-change-evaluator/SKILL.md`、`.agents/skills/plan-to-issues/SKILL.md` を追跡し、順に既存PRレビュー修正、テンプレート改善の採否・重複・配置判断、合意済み計画からGitHub Issueへの変換に限定する。

### `scripts/`, `tests/`, and `.github/workflows/`

機械的に判定できる検証を置く。文書の存在だけでなく、参照先、状態値、失敗時の停止、読み取り専用境界を契約テストで確認する。

### Issue / PR / project config

今回のAcceptance、Risk Tier、Design Decision、対象SHAはIssue / PRへ記録する。`.codex/config.toml` は現テンプレート本体に存在しないため、Codexのバージョンやhost依存の設定をこのIssueで新規固定しない。`.cursor/environment.json` はtool固有設定として扱う。

## Read-only smoke test

文書の存在確認だけでは、指示が適用されることの証拠にならない。Issue #121では、実装や外部書き込みを行わない次のread-only確認を定義し、`tests/instruction-architecture/run-samples.sh` で実施する。

1. **Source map**: 現在の `AGENTS.md`、`docs/`、`.agents/skills/`、`.github/`、`tests/` の役割を説明でき、主要な正本文書が存在する。
2. **Gate enumeration**: 任意のIssueに対して、実装前のRisk / Design Decision / Security Boundary、標準検証、CI / Security / Review、Human Mergeの入口を列挙できる。
3. **Scope**: repo-local Skillは対象ディレクトリと作業目的が一致した場合だけ適用され、全作業の常駐ルールへ昇格していない。`pr-review-fix` は既存PRレビュー修正、`template-change-evaluator` はテンプレート改善の採否・重複・配置判断、`plan-to-issues` は合意済み計画からGitHub Issueへの変換に限定され、それぞれの `AGENTS.md` routingからSkillへ参照経路をたどれる。
4. **Triggered retrieval**: Framework、Plan Review、Acceptance、Security、RAGなどの詳細は、発火条件と正本文書の対応をたどれる。
5. **Read-only boundary**: read-only確認ではbranch、commit、push、PR、Issueコメントを作成しない。確認前後のHEAD、branch、refs（dangling symbolic refを含むref storageと参照先）、status、index entryと`assume-unchanged` / `skip-worktree` flag、worktree内容が一致する。
6. **Runtime evidence**: 利用可能なCodexの実機または公式仕様で確認できない `/status`、`/debug-config` 等のコマンドを、標準手順として固定しない。

このshell smoke testはCodex自身の全runtimeを再現するものではない。source map、参照経路、禁止された書き込みの不在、Git状態不変という決定可能な境界をCIで固定し、実機でしか確認できない適用結果は次のAgent実行記録で補完する。

### Agent-executed protocol

1. 新しいread-only Agent sessionで、対象Issue、対象commit、root `AGENTS.md` を提示する。branch、commit、push、PR、Issueコメントの作成を禁止する。
2. Agentに、現在適用中のinstruction source、Issue実装前に必要なGate、repo-local Skillの適用scope、Framework / Plan Review / Securityなどの発火条件と参照先を列挙させる。
3. Agentは根拠にしたsource pathまたはGitHub URLを示し、実在確認できないruntime commandを標準手順として提案しない。
4. 実行者は、前後の `HEAD`、branch、refsとdangling symbolic refを含むcommon ref storage・worktree-local ref storage・参照先、working tree、index entryと`assume-unchanged` / `skip-worktree` flagが変化していないことを記録する。結果はIssueまたはPRに残し、CIのdeterministic contractと混同しない。

### Execution record (historical session)

以下は初回のread-only Agent sessionに対する記録であり、対象SHAはそのセッション時点のものです。PRのheadを証跡文書自身のコミットへ自己参照させないため、後続の検証結果はPR本文または別の外部証跡へ記録します。

- 実行日: 2026-09-20。
- 対象: Issue #121、commit `5b962f7d23f6665d6e5807cf2916d163866d5358`。
- 実読したsource: root `AGENTS.md` のCode Review / Review Evidence Contract、Issue #121、`docs/nine-standard-ai-development-flow.md`、本台帳。
- 結果: root AGENTSの常駐停止条件、Issue基準、HIGHリスク停止、CI → Security → Codex Review → Human Mergeの順序を列挙し、詳細参照先とrepo-local Skillのscopeを区別できた。
- read-only境界: この記録のAgent確認ではGitHub閲覧、`git diff`、`git status`、shell contract testだけを実行し、branch / commit / push / PR / Issueコメントを作成しなかった。
- 限界: この記録は特定sessionの実行証拠であり、将来のhostやCodex versionへ無条件に一般化しない。runtime設定の標準化には別のDesign Decisionが必要である。

## Deferred decisions and follow-up boundary

- `AGENTS.md` の詳細を実際に `docs/` へ移す場合は、移動前後の参照経路、適用漏れ、サイズ差分、失敗時の停止を別PRで検証する。
- `Review Evidence Contract` の専用文書化は、IA-02 layer mapに列挙した `AGENTS.md`、README、`docs/nine-standard-ai-development-flow.md`、`docs/template-guide.md`、`docs/ai-development-harness-inventory.md#V-02`、`docs/ai-execution-state.md`、`.agents/skills/pr-review-fix/SKILL.md`、`tests/review-evidence/run-samples.sh`、`tests/pr-review-followups/run-samples.sh`を含む参照契約テスト群、PR templateの責務を確認してから判断する。まず詳細複製であるdocs側とSkill側を正本参照入口へ短縮し、意図的要約が正本を再定義せず、同一PRでテスト期待値を更新・実行することを検証する。
- `Parent Issue Completion` は、子Issue checkbox、全体完了条件、残課題切り出し、人間確認を収容する実在の正本文書ができるまで `AGENTS.md` に維持する。
- `Design / State Modeling` と `Test Design / Safe Test Deletion` の専用正本化は、既存の標準フローとの重複を確認して子Issue化する。
- `docs/architecture/rag-design.md` はRAG採用プロジェクトの案件固有記録であり、template repositoryへ空ファイルを追加しない。
- Codex設定層のtemplate化は、対象host、version drift、適用スコープ、secret / network境界を確認できるDesign Decisionができるまで行わない。

### Historical verification record (pre-self-reference)

- 実行日: 2026-09-20。
- 対象: Issue #121、後続コミットでこの台帳を更新する前の親commit `418e7c9fa22ece4cf358564aae3983e2bba67e65`。
- 実行: `bash tests/instruction-architecture/run-samples.sh`、`bash tests/pr-review-fix-jev/run-samples.sh`、`bash tests/app-template/run-samples.sh`、shell syntax、`git diff --check`。
- 結果: 競合解消後のInstruction Architecture、JEV、app-template契約テスト、shell syntax、差分検査はPASS。Deployment / Security Preflightのローカル実行はmacOSのGit実行環境制限で未完了とし、GitHub CI / Securityで再検証する。
- GitHub証跡: この節は親commitに対する履歴記録であり、後続headのCI / Security workflowやCodex ReviewのPASSを主張しない。後続headの結果はPR本文へ記録する。

## Verification record

- 変更前 `AGENTS.md`: 47,136 bytes（`main` `1f48747`）。
- 変更後 `AGENTS.md`: 47,438 bytes（`+302 bytes`）。
- 変更理由: Purposeに本台帳への参照と、常駐ルール・詳細仕様・反復手順・機械判定の境界を1段落追加した。
- 成功条件: 台帳の全セクション列挙、read-only smoke test、既存契約テスト、CI / Security / Review / Human Merge境界の維持。

## Issue #177以降の現行常駐節

| 常駐節 | 配置 | 判定 | 参照先 |
| --- | --- | --- | --- |
| `作業境界` | `RESIDENT` | `KEEP` | Issue仕様、risk、状態設計、情報境界、停止条件 |
| `検証とレビュー` | `ENTRYPOINT` | `KEEP` | 標準フロー、test設計、review契約、例外Safety Gate |
| `必要時の参照` | `ENTRYPOINT` | `KEEP` | 条件付きSkill、UI、親完了、最小契約の条件表 |

Issue #179で親子Issueとplan-to-issuesの入力を最小契約へ切り替える。7見出しと6 MUST、Risk / 安全境界を維持し、専門本文は条件付き参照へ集約する。旧見出し検査は入力契約・正本への到達へ同期し、PR template、helper、CIの実行回帰は維持する。責務対応と記入例は[Issue #179の入力責務移行](minimal-development-contract.md#issue-179-入力責務の移行)を参照。
