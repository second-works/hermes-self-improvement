# AI開発ハーネス台帳

## 目的

この台帳は、AI開発テンプレートに存在するハーネスの役割、発火条件、実行コスト、重複、安全性、削除または再評価条件を一つの正本で追跡する。
台帳は新しい工程を増やすための一覧ではなく、既存工程を残す、強化する、簡素化する、削除候補にする判断の根拠を記録するために使う。

## Harness Minimalism

ハーネスは、観測された失敗モードまたは既知の重大リスクに対応する場合だけ追加する。
新しいハーネスを追加するときは、少なくとも次を記録する。

- 解決する失敗モード
- 発火条件
- 入力と参照するContext
- 出力と変更するState
- 決定論的な判定へ移せるか
- 実行コストと運用負荷
- 既存ハーネスとの重複
- 安全上の必須性
- 判定（KEEP / STRENGTHEN / SIMPLIFY / REMOVE_CANDIDATE）
- 削除または再評価条件
- 関連Issueと正本文書

モデルやToolの能力が向上した場合も、ハーネスを自動的に残す理由にはしない。
一方で、Security Boundary、Human Approval Boundary、Production保護のように、失敗の発生を待つと被害を防げない制約は、実測コストだけを理由に弱めない。

## 判定の定義

- **KEEP**：現在の失敗モードまたは重大リスクに対して役割が明確であり、現状の境界を維持する。
- **STRENGTHEN**：役割は必要だが、観測可能性、決定論的検証、Context / Stateの引継ぎなどを強化する。
- **SIMPLIFY**：役割を維持しながら、重複する説明、不要な入力、過剰な実行回数、運用負荷を減らす。
- **REMOVE_CANDIDATE**：現在の失敗モードまたは安全上の必要性を確認できず、削除または代替を評価する候補。
  この判定は削除の実行ではなく、依存関係、代替制御、影響範囲を確認するための保留状態である。

## 評価手順

各ハーネスを次の順序で確認する。

1. 失敗モードまたは既知の重大リスクを、Issue、レビュー指摘、失敗テスト、運用記録へ結び付ける。
2. 発火条件、入力、出力、State変更、決定論的判定の可否を記録する。
3. 同じ失敗を別のハーネスも検出していないか確認する。
4. 実行コストと運用負荷を、品質、安全性、追跡可能性の効果と比較する。
5. 判定を決め、削除または再評価の条件を記録する。
6. 判定を変更した場合は、理由と対象SHAまたは実測結果を更新する。

「失敗が観測されていない」ことと「安全上不要である」ことは同じではない。
Security、権限、Productionなどの既知重大リスクは、実際の事故が起きていなくてもKEEPの根拠になる。

## 根拠レコード

- **#56**：今回のETCSLV棚卸しの要求、判定基準、受入条件、テスト観点を定義する監査元Issue。
- **E-01からV-03、およびL-02aからL-02c**：各台帳項目の根拠レコードID。個別の運用事故やレビュー指摘を新たに主張するものではなく、Issue #56の監査条件と各項目の現行正本を追跡するための識別子。
## 主要ハーネスの判定

| ID | ハーネス | ETCSLV | 判定 | 正本または参照 |
| --- | --- | --- | --- | --- |
| E-01 | IssueからPRまでの実行単位 | E | KEEP | AGENTS.md、Issue / PRテンプレート |
| E-02 | Plan Review Gate | E | KEEP | docs/plan-review-gate.md |
| E-03 | Design DecisionとEscalation | E | KEEP | Issueテンプレート、AGENTS.md |
| E-04 | Safe Auto-Fix / Auto-Merge | E | KEEP | docs/safe-auto-fix-auto-merge.md |
| E-05 | Child Issue Quality Gate | E | KEEP | AGENTS.md、docs/issue-quality-check.md |
| E-06 | Deployment Design / Release Gate | E | STRENGTHEN | docs/deployment-release-design.md、.github/workflows |
| E-07 | RAG Architecture Standard | E | KEEP | AGENTS.md、docs/architecture/rag-guidelines.md、docs/architecture/rag-design.md |
| E-08 | Test Design / Safe Test Deletion | E | KEEP | AGENTS.md、テスト実装、Issue / PR |
| E-09 | Parent Issue Completion | E | KEEP | AGENTS.md、親Issue、子Issue、PR |
| E-10 | Cloud Agent開発環境確認 | E | KEEP | .cursor/environment.json、.gitignore |
| C-03 | Adaptive Development Flow | C | SIMPLIFY | docs/adaptive-development-flow.md |
| C-04 | Human-facing HTML Status Report | C | SIMPLIFY | scripts/render-status-report.py、docs/html-status-report.md |
| T-01 | CodexとSkills | T | SIMPLIFY | AGENTS.md、.agents/skills |
| T-03 | Decision Provider Shadow比較 | T | KEEP | templates/review-comment-auto-triage/local_judge/README.md |
| T-02 | GitHub Actionsと外部Tool | T | KEEP | .github/workflows、AI Agent Security Boundary |
| C-01 | 正本文書とIssue / PR Context | C | STRENGTHEN | docs/template-guide.md、docs、Issue / PRテンプレート |
| C-02 | Review Context | C | SIMPLIFY | PRテンプレート、Review Evidence Contract |
| S-01 | Issue、PR、head SHA | S | KEEP | PR、Git履歴、CI結果 |
| S-02 | FOLLOW-UPとDesign Decision履歴 | S | KEEP | docs/review-followups.md、Issue |
| S-03 | Implementation、Deploy、Product Acceptance状態 | S | KEEP | Issue、PR、docs/acceptance-verification.md |
| S-04 | Structured Current State契約 | S | STRENGTHEN | docs/ai-execution-state.md、AGENTS.md、pr-review-fix Skill、Issue / PRテンプレート |
| L-01 | verify.shとCI | L | KEEP | templates/verification、.github/workflows/ci.yml |
| L-03 | PRODUCT UI Standard contract test | L | KEEP | docs/product-ui-standard.md、templates/app/docs/design.md、tests/product-ui-standard/run-samples.sh、.github/workflows/ci.yml |
| L-02a | Security Preflight | L | KEEP | templates/security、docs/ai-agent-security-boundary.md |
| L-02b | CodeQL | L | KEEP | GitHub Code Scanning、docs/github-repository-security-baseline.md |
| L-02c | Dependabot | L | KEEP | GitHub Dependabot、docs/github-repository-security-baseline.md |
| V-01 | Codex Code Review | V | SIMPLIFY | PRコメント、レビュー履歴 |
| V-02 | Review Evidence ContractとP2収束 | V | KEEP | AGENTS.md、.agents/skills/pr-review-fix |
| V-03 | Acceptance Verification | V | KEEP | docs/acceptance-verification.md |

## 台帳

### HSI-05 独立fixture評価

- **ETCSLV分類 / 判定**: Lifecycle Hooks / KEEP。
- **失敗モード / 発火条件**: Issue #5の改善候補を主観や公開例だけで採用すること、候補が評価器・hidden・監査を書換えること。fixture候補比較のとき発火。
- **入力 / Context**: commit固定の基準・候補、公開10件/hidden10件、事前固定policy、image digest、既存承認境界。
- **出力 / State**: PASS/FAIL/HOLDのJSON・日本語集計、hash連鎖。PASSもAWAITING_APPROVALまで。採用権限なし。
- **決定論 / コスト / 重複**: finding完全一致と判定は決定論。各入力3回、逐次Docker、全体20分、API費用0。既存CI/Security/Codex Reviewは代替しない。
- **安全上の必要性 / 再評価条件**: 候補と評価・本番の隔離が必須。同じ拒否保証・独立評価を持つ実装へ置換する際に再評価し、検証成功前に旧保証を消さない。
- **正本**: [独立評価](independent-evaluation.md)、[Issue #5](https://github.com/second-works/hermes-self-improvement/issues/5)。実Docker未確認を成功扱いしない。

### E-01 IssueからPRまでの実行単位

- **ETCSLV分類**：Execution
- **解決する失敗モード**：変更がIssueの受入条件から外れること、複数Issueの変更が一つのPRへ混在すること。
- **発火条件**：Issueを実装し、PRを作成するとき。
- **入力 / Context**：Issue本文、Design Decision、依存関係、AGENTS.md。
- **出力 / State変更**：Issue専用branch、PR、CI対象SHA。
- **決定論的判定可能か**：Issue番号、branch、PRの対応は機械確認できる。
- **実行コスト / 運用負荷**：PR作成とCIは必要だが、Issueごとに分けることでレビュー範囲を限定する。
- **重複する仕組み**：該当なし。Issue単位のbranch / PR対応を担う専用の追跡単位であり、他の実行ハーネスと同じ責務を持たない。
- **安全上必須か**：追跡可能性と変更範囲の制御に必要。
- **判定**：KEEP。
- **削除・再評価条件**：IssueとPRの対応を別の機械的な方法で同等以上に追跡できる場合に再評価する。
- **関連Issue / 正本文書**：#56、E-01。Issue #56の監査条件とこの項目の判定を追跡する。 正本：AGENTS.md、Issue / PRテンプレート。

### E-02 Plan Review Gate

- **ETCSLV分類**：Execution
- **解決する失敗モード**：未決定の要件や設計境界を残したままIssue化、実装を開始すること、または採用案を自己肯定して反証できないまま計画を進めること。
- **発火条件**：計画を親Issueまたは子Issueへ変換する前。
- **入力 / Context**：計画書、代替案、判断基準、懸念点、未決定事項、反証観点（失敗原因、成立条件、単純な代替案、不利な証拠、期待の先取り）、関連する過去のAcceptance VerificationのPlan vs Reality記録と次回計画へ反映する教訓。
- **出力 / State変更**：PASS、NOT_APPLICABLE、NEEDS_DECISIONの判定と反証レビュー記録。
- **決定論的判定可能か**：未決定事項の存在は機械補助できるが、設計判断は人間またはレビューで確認する。
- **実行コスト / 運用負荷**：Issue化前の一回のレビュー。反証観点を計画規模に応じて簡潔に記録し、Design Decision Escalationとは発火時点が異なる。
- **重複する仕組み**：E-03 Design DecisionとEscalationとは実装前後の発火時点が異なるため重複しない。
- **安全上必須か**：未決定のまま実装を始めないために必要。
- **判定**：KEEP。
- **削除・再評価条件**：計画の未決定事項と反証観点を同等の証拠でIssue化前に確認できる仕組みが整った場合に再評価する。
- **関連Issue / 正本文書**：#56、#58、E-02。Issue #56の監査条件とIssue #58の反証観点を追跡する。 正本：docs/plan-review-gate.md。

### E-03 Design DecisionとEscalation

- **ETCSLV分類**：Execution
- **解決する失敗モード**：実装中の重要な判断を、Issueの仕様や事前承認なしに独自決定すること。
- **発火条件**：既存のDesign Decisionにない設計境界へ到達したとき。
- **入力 / Context**：Issue、Design Decision、選択肢、影響範囲。
- **出力 / State変更**：停止理由、推奨案、親Issue更新または追加Issueの判断。
- **決定論的判定可能か**：変更範囲の検出は補助できるが、設計判断は決定論的に代替しない。
- **実行コスト / 運用負荷**：通常は発火しない。Plan Reviewは実装前、Escalationは実装中で役割が異なる。
- **重複する仕組み**：E-02 Plan Review Gateとは実装中の設計境界で発火する点が異なるため重複しない。
- **安全上必須か**：仕様のない権限、データ、Production変更を止めるために必要。
- **判定**：KEEP。
- **削除・再評価条件**：設計判断の承認と停止を同等に追跡できる運用へ置き換える場合に再評価する。
- **関連Issue / 正本文書**：#56、E-03。Issue #56の監査条件とこの項目の判定を追跡する。 正本：Issueテンプレート、AGENTS.md。

### E-04 Safe Auto-Fix / Auto-Merge

- **ETCSLV分類**：Execution
- **解決する失敗モード**：軽微な修正を自動化する過程で、認証、Secret、Deploy、Security Policy、権限を変更すること。
- **発火条件**：レビュー指摘を自動修正または自動マージの対象に分類するとき。
- **入力 / Context**：Issue範囲、レビュー指摘、変更差分、CI、Security、レビュー履歴。
- **出力 / State変更**：通常レーンまたはSafeレーンの判定、検証結果。
- **決定論的判定可能か**：変更ファイル、差分、CI結果は機械確認できる。安全性の例外判断は人間の承認を残す。
- **実行コスト / 運用負荷**：適格性確認と再検証が必要。通常のレビュー修正を二重に自動化しない。
- **重複する仕組み**：V-02 Review Evidence Contractと一部のレビュー判定を共有するが、Safeレーン適格性と権限変更の安全判定が固有。
- **安全上必須か**：自動化の権限範囲を制御するために必要。
- **判定**：KEEP。
- **削除・再評価条件**：安全条件、停止条件、監査記録を同等に保証できる自動化へ置換する場合に再評価する。
- **関連Issue / 正本文書**：#56、E-04。Issue #56の監査条件とこの項目の判定を追跡する。 正本：docs/safe-auto-fix-auto-merge.md。

### E-05 Child Issue Quality Gate

- **ETCSLV分類**：Execution
- **解決する失敗モード**：目的、範囲、独立検証、1 PR、依存関係、安全境界のMUST不足を補助Scoreで見落とし、不完全な子Issueを登録・実装開始すること。
- **発火条件**：子IssueをGitHubへ登録する前、およびCodexが子Issueの実装を開始する前。
- **入力 / Context**：子Issue案、親Issue、MUST、SHOULD、完了条件、テスト条件、依存Issue、安全境界、AGENTS.md、docs/issue-quality-check.md。
- **出力 / State変更**：MUST充足時の登録・実装開始、MUST不足時の停止、SHOULD不足時の改善候補、補助Score（各0〜2点、合計0〜12点）。
- **決定論的判定可能か**：MUSTの明記、Scoreの許容範囲、停止・継続は機械確認できる。目的の妥当性や分割・統合の判断はレビューで確認する。
- **実行コスト / 運用負荷**：Issue登録・実装開始前の軽量な一回の確認。MUSTと依存関係を確認し、SHOULDだけで停止しないことで手戻りと過剰停止を減らす。
- **重複する仕組み**：E-02 Plan Review Gateは計画全体の未決定事項をIssue化前に確認し、E-05は子Issue固有のMUST、SHOULD、補助Scoreを確認する。Issue / PR Ruleは確認項目を定義するが、E-05の採点と停止判定を代替しない。
- **安全上必須か**：実装範囲の逸脱、完了条件の曖昧さ、依存関係の見落としを防ぐために必要。Security Boundary、Human Approval Boundary、Production保護の代替ではない。
- **判定**：KEEP。
- **削除・再評価条件**：目的、範囲、独立検証、1 PR、依存関係、安全境界のMUSTと、SHOULD・補助Score・停止条件を同等以上に確認し、再現可能に記録できる仕組みへ置換する場合に再評価する。
- **関連Issue / 正本文書**：#56、E-05。Issue #56の監査条件とこの項目の判定を追跡する。 正本：AGENTS.md、docs/issue-quality-check.md、Issueテンプレート。

### E-06 Deployment Design / Release Gate

- **ETCSLV分類**：Execution
- **解決する失敗モード**：実装PRの完了を本番投入可能と誤認し、Production runtime、永続データ、Secrets、完成したRelease Candidate全体のSecurity監査、Release判定、Deploy後確認、Monitoring、Rollback、人間承認の設計や前提条件を確認しないまま本番投入すること。
- **発火条件**：本番投入経路を設計するとき、Release Candidateを作成するとき、またはProduction Deployの可否を判定するとき。
- **入力 / Context**：対象環境、runtime、Container、Persistent data、Deployment method、Release Candidateのcommit SHAやartifact identity、RC静的監査、Staging上のSecurity確認、Secrets / 外部サービス、Dependency、CodeQL等の静的解析、trust boundary、Production / Deployment設定、backup、migration、Health Check、Smoke Test、Monitoring、Rollback、PR単位Security Check、Risk Tier、GitHub Environment、人間承認。
- **出力 / State変更**：実装完了と本番投入可能状態の分離、Full-System Security Auditの`PASS / FAIL / NOT_APPLICABLE`、監査対象identityと証拠、Release判定、Deploy可否、Post-deploy Health Check、Monitoring開始、Rollback判断、人間承認の記録。
- **決定論的判定可能か**：対象SHA / artifact identity、CI、PR単位Security結果、監査証拠のidentity一致、Full-System Security Audit結果、backup成功、Health Check結果、必要な項目の記録有無は機械確認できる。監査範囲、`NOT_APPLICABLE`の適格性、Release判定、設計選択、人間承認はレビューで確認する。
- **実行コスト / 運用負荷**：本番投入経路の設計とRelease前後の確認に加え、RC静的監査と必要なStaging上のSecurity確認が必要。既存のPR単位Security結果を再利用しつつ、完成成果物のidentity照合と統合後の境界を確認する負荷が増えるが、個別PRでは検出できない境界不整合をRelease前に停止する。
- **重複する仕組み**：L-02aからL-02cはPR単位のSecurity検査を担う。S-03はImplementation、Deploy、Product Acceptanceの状態を分離し、V-03はDeploy後の実利用検証と検収を担う。E-06はそれらを置き換えず、Release Candidate全体のSecurity監査、本番投入前の設計、Release判定、backup・migration・Rollback、人間承認を担う。
- **安全上必須か**：Production保護、永続データの安全性、Secretsの扱い、Rollback可能性、人間承認を維持するために必要。
- **判定**：STRENGTHEN。
- **削除・再評価条件**：Release Candidate全体のSecurity監査、対象identity、停止と再監査、対象環境、データ、Release判定、backup・migration、Health Check、Monitoring、Rollback、人間承認を同等以上に記録・検証できる独立したRelease機構へ置換する場合に再評価する。
- **関連Issue / 正本文書**：#56、#110、E-06。Issue #110でFull-System Security Audit、identity照合、停止と再監査条件を追加した。正本：docs/deployment-release-design.md、.github/workflows、templates/verification。

### E-07 RAG Architecture Standard

- **ETCSLV分類**：Execution
- **解決する失敗モード**：RAGを必要以上に複雑化し、採用Phase、Retriever / Reranker / Metadata、未採用Phase、品質指標、標準からの逸脱理由を記録しないまま構築・変更すること。また、本番RAGで引用・出典追跡、根拠整合性、ハルシネーション検証、権限制御を評価しないこと。
- **発火条件**：RAGを新規構築または変更するとき、および本番RAGの品質・権限制御を設計するとき。
- **入力 / Context**：RAG要件、採用Phase、Retriever、Reranker、Metadata、品質評価指標、未採用Phaseと理由、標準逸脱理由、引用・出典追跡、根拠整合性、ハルシネーション検証、権限制御。
- **出力 / State変更**：採用構成、未採用理由、品質評価方法、標準逸脱理由、本番RAGの検証条件と設計判断の記録。
- **決定論的判定可能か**：必須設計項目と記録の有無は機械確認できる。Phase選択、品質指標、標準逸脱の妥当性はレビューで確認する。
- **実行コスト / 運用負荷**：RAGの新規構築・変更時に設計記録と品質評価を作成する負荷がある。高機能化による実装・運用コストを事前に比較できるため、不要な構成の導入を抑えられる。
- **重複する仕組み**：C-01は正本文書とIssue / PR Contextを管理し、V-03はDeploy後の実利用検証を担う。E-07はRAG固有の構成選択、品質、出典、根拠、権限制御を対象とし、Context管理や実利用検収を代替しない。
- **安全上必須か**：RAGの品質、出典追跡、権限制御、不要な複雑化を管理するために必要。Security Boundary、Human Approval Boundary、Production保護の代替ではない。
- **判定**：KEEP。
- **削除・再評価条件**：RAGの構成、品質、出典、根拠、ハルシネーション、権限制御、標準逸脱理由を同等以上に記録・検証できる設計ゲートへ置換する場合に再評価する。
- **関連Issue / 正本文書**：#56、E-07。Issue #56の監査条件とこの項目の判定を追跡する。 正本：AGENTS.md、docs/architecture/rag-guidelines.md、docs/architecture/rag-design.md。

### E-08 Test Design / Safe Test Deletion

- **ETCSLV分類**：Execution
- **解決する失敗モード**：テストの責務、適切なテスト層、検証責務の移行先を確認せず、速度・コード量・重複だけを理由にテストを削除または統合し、安全性確認や重要な回帰を失うこと。
- **発火条件**：テストを追加、更新、削除、統合するとき。特に既存テストを削除・統合し、検証責務を別テストへ移すとき。
- **入力 / Context**：対象テスト、保証する検証責務、テスト層、移行先テスト、認証・認可、入力検証、Repository境界、重要な回帰、Happy Path / Integration / E2E、削除理由、Issue / PR。
- **出力 / State変更**：テスト層の選択、検証責務の移行先、削除・統合理由、新しいテストの成功確認、安全網の維持、PRまたはIssueへの記録。
- **決定論的判定可能か**：テスト実行結果、対象ファイル、削除差分、移行先の存在は機械確認できる。責務の同等性、不要化の合理性、安全網の十分性はレビューで確認する。
- **実行コスト / 運用負荷**：テスト追加・更新・削除時の責務確認と検証実行が必要。新しいテストを先に成功させる負荷はあるが、品質ゲートの弱体化と回帰の見逃しを防ぐ。
- **重複する仕組み**：L-01はCIでテスト結果を検証し、E-08はテスト責務の設計と削除・統合時の安全条件を確認する。L-01の実行結果やV-03の実利用検証を代替しない。
- **安全上必須か**：テスト削除・統合による検証責務の消失を防ぐために必要。
- **判定**：KEEP。
- **削除・再評価条件**：テスト責務、移行先、削除理由、安全性確認、新しいテストの成功を同等以上に記録・検証できる仕組みへ置換する場合に再評価する。
- **関連Issue / 正本文書**：#56、E-08。Issue #56の監査条件とこの項目の判定を追跡する。 正本：AGENTS.md、テスト実装、Issue / PR。

### E-09 Parent Issue Completion

- **ETCSLV分類**：Execution
- **解決する失敗モード**：子IssueのPRが自動Closeされたことだけを根拠に、親Issueのチェックボックス、全体完了条件、CI、Security、AIレビュー、手動確認、残課題、人間の最終確認を照合せず親IssueをCloseすること。
- **発火条件**：親IssueをCloseするとき、および子IssueのMerge / Close後に親Issue全体の完了を確認するとき。
- **入力 / Context**：親Issue、子Issue、PR、Merge / Close状態、チェックボックス、全体完了条件、CI、Security、AIレビュー、手動確認、warning / deprecation、後続メンテナンスIssue。
- **出力 / State変更**：子Issueの完了一覧、親Issueチェックボックスの最終状態、全体完了条件との照合結果、残課題の記録、親IssueのClose可否、人間の最終確認。
- **決定論的判定可能か**：子IssueとPRの状態、チェックボックス、CI・Security・レビュー結果は機械確認できる。全体完了条件、残課題、人間の最終確認はレビューで確認する。
- **実行コスト / 運用負荷**：親IssueをCloseする前の一回の状態照合。子Issue、PR、CI、Security、レビュー、手動確認を確認する負荷はあるが、未完了の親Issueを誤ってCloseすることを防ぐ。
- **重複する仕組み**：S-03はImplementation、Deploy、Product Acceptanceの状態を分離し、V-03は実利用検証と検収を担う。E-09は親Issueの子Issue完了、チェックボックス、全体完了条件、残課題、人間確認を担い、個別PRのCIや検収を代替しない。
- **安全上必須か**：親Issueの完了状態と監査記録を正確に保つために必要。
- **判定**：KEEP。
- **削除・再評価条件**：子Issue、PR、完了条件、残課題、CI・Security・レビュー、手動確認を同等以上に照合し、親IssueのClose可否を記録できる仕組みへ置換する場合に再評価する。
- **関連Issue / 正本文書**：#56、E-09。Issue #56の監査条件とこの項目の判定を追跡する。 正本：AGENTS.md、親Issue、子Issue、PR。

### E-10 Cloud Agent開発環境確認

- **ETCSLV分類**：Execution
- **解決する失敗モード**：Cloud Agentがテストに必要なPython、Node.js、Bashを欠いたまま起動すること、または補助scriptの構文不正を実行時まで見逃すこと。
- **発火条件**：Cloud AgentがRepositoryから開発環境をプロビジョニングするときのinstall段階。
- **入力 / Context**：`.cursor/environment.json`、PATH上の`python3` / `node` / `bash`、`scripts/collect-github-state.py`、`scripts/render-status-report.py`。
- **出力 / State変更**：ツールチェーンのversion表示、Python bytecode検証、`__pycache__` / `*.pyc`の生成。必要Toolの不在や構文不正では非0終了する。
- **決定論的判定可能か**：Toolの存在、versionコマンドの終了状態、`py_compile`の成否は機械判定できる。
- **実行コスト / 運用負荷**：プロビジョニング時にversion確認3件とPython標準ライブラリの構文確認2ファイルを1回実行する軽量な負荷。
- **重複する仕組み**：L-01のCIもテスト環境を検証するが、E-10はCloud Agentのプロビジョニング時に必要Toolの不在を早期停止する点が異なる。依存packageのinstallやCIの全テストは重複実行しない。
- **安全上必須か**：Security、Production、Secretsを保護するハーネスではないが、Cloud Agent上の再現可能な検証入口を確保するために必要。
- **判定**：KEEP。
- **削除・再評価条件**：Cloud Agentが同じToolと補助scriptの構文をプロビジョニング前に同等以上に検証し、失敗を停止できる標準機構へ置換した場合に再評価する。
- **関連Issue / 正本文書**：PR #114、E-10。PR #114のCloud Agent開発環境追加とこの判定を追跡する。正本：`.cursor/environment.json`、`.gitignore`。Issue #181で実行回帰を `tests/cloud-agent-environment/run-samples.sh` へ移し、Template CIから直接実行する。隔離project/cacheで正常compile、Bash不在、version終了code伝播、Python構文不正時停止を確認する。実install設定は変更しない。

### T-01 CodexとSkills

- **ETCSLV分類**：Tools
- **解決する失敗モード**：モデルの判断だけでは再現できない手順を毎回手作業で再構成すること、同じ処理を複数Skillへ重複実装すること、外部の新しい手法を現行repoの既存責務確認なしに追加してテンプレートを肥大化させること、合意済み計画をIssue化するときにPlan ReviewやChild Issue Quality Gateを飛ばして未決定事項を実装Issueへ持ち込むこと。
- **発火条件**：標準手順を再利用可能なSkillへ切り出すとき。
- **入力 / Context**：Issue、AGENTS.md、対象PR、評価対象の外部提案、合意済み計画・方針、現行repoの既存責務、各Gate正本、Skillの契約。
- **出力 / State変更**：テンプレート変更の採否・配置判断、親Issue / 1 PR単位の子Issueまたは単一Issueの登録、実装、レビュー依頼、検証の実行。
- **決定論的判定可能か**：ファイル、branch、SHA、コマンド結果は機械確認できる。Skillを追加する価値は失敗モードと再利用頻度で評価する。
- **実行コスト / 運用負荷**：Skill数が増えるほど参照と更新の負荷が増える。既存Skillで足りる処理を新設しない。
- **重複する仕組み**：V-01 Codex Code ReviewとTool / Skill利用が重なるが、Skillの再利用契約とレビュー判定は別責務。
- **安全上必須か**：個々のSkillは一律に必須ではない。PR修正のSHA管理など、追跡可能性を担う契約は維持する。
- **判定**：SIMPLIFY。
- **削除・再評価条件**：対象Skillに固有の失敗モード、再利用、検証上の効果がなくなった場合にREMOVE_CANDIDATEとして再評価する。
- **関連Issue / 正本文書**：#56、#147、#148、T-01。Issue #56の監査条件、Issue #147のテンプレート変更評価Skill、Issue #148の計画→Issue変換Skillを追跡する。 正本：AGENTS.md、.agents/skills/pr-review-fix/SKILL.md、.agents/skills/template-change-evaluator/SKILL.md、.agents/skills/plan-to-issues/SKILL.md。

### T-03 Decision Provider Shadow比較

- **ETCSLV分類**：Tools
- **解決する失敗モード**：JEV固有scoreとローカルモデルの確率を同一視し、False Negativeや障害を検出せず判定を委譲すること。
- **発火条件**：人間がShadow比較を有効にしたときだけ実行する。
- **入力 / Context**：現PR headのCodexコメント、独立して判断したbaselineの判定ラベル。
- **出力 / State変更**：本文を含まない同一comment単位の比較observation。`authoritative=false`を固定し、修正・resolve・routing・MergeのStateを変更しない。
- **決定論的判定可能か**：schema、enum/range、redirect禁止、Secret非保存、baseline不変は契約テストで保証し、意味分類の正答率は実測する。
- **実行コスト / 運用負荷**：1コメント5回・各1-token、合計25秒上限、直列処理。Gemma 4の共有メモリ/KVとの競合は配備時に評価する。
- **重複する仕組み**：JEV比較adapterは既存JEV契約を再実装せず、共通observationへ変換する。T-01のレビュー修正やV-01のレビュー判定を代行しない。
- **安全上必須か**：追加Provider自体は任意だが、利用する際の認証・サイズ・timeout・非権威契約は必須。
- **判定**：KEEP。
- **削除・再評価条件**：50〜100件の実レビューで精度、False Negative、レイテンシ、通常利用との競合を見て、別Design Decisionで継続または削除を判断する。
- **関連Issue / 正本文書**：#153、#116、#123、#131。`templates/review-comment-auto-triage/local_judge/README.md`、`tests/local-judge/`。

### T-02 GitHub Actionsと外部Tool

- **ETCSLV分類**：Tools
- **解決する失敗モード**：AIエージェントや外部Toolが、許可されていないRepository、network、Secret、Deploy先へアクセスすること。
- **発火条件**：CI、Security、Issue / PR操作、DeployなどのToolを実行するとき。
- **入力 / Context**：Repository、branch、workflow、Tool権限、環境、外部送信先。
- **出力 / State変更**：CI / Security結果、Issue / PR更新、Deployまたは外部状態変更。
- **決定論的判定可能か**：権限scope、対象SHA、workflow結果は機械確認できる。
- **実行コスト / 運用負荷**：CIとSecurityは異なる境界であり、同じ判定として統合しない。
- **重複する仕組み**：L-02a Security PreflightとTool権限境界が重なるが、T-02は外部Tool全般の許可scope、L-02aはPR Security検査の実行状態が対象。
- **安全上必須か**：Least Privilege、Security Boundary、Production保護に必要。
- **判定**：KEEP。
- **削除・再評価条件**：許可範囲、監査、失敗時の停止を同等に保証できるToolへ置換する場合に再評価する。
- **関連Issue / 正本文書**：#56、T-02。Issue #56の監査条件とこの項目の判定を追跡する。 正本：docs/ai-agent-security-boundary.md、GitHub workflow。

### C-01 正本文書とIssue / PR Context

- **ETCSLV分類**：Context
- **解決する失敗モード**：仕様、判断理由、安全条件が複数箇所で不一致になり、エージェントが必要な情報へ到達できないこと。
- **発火条件**：実装、レビュー、テンプレート利用、新規プロジェクト初期化のとき。
- **入力 / Context**：正本文書、AGENTS.md、Parent / Child Issue、PRテンプレート。
- **出力 / State変更**：参照関係、記録された設計判断、適用可否。
- **決定論的判定可能か**：参照先の存在とリンクは機械確認できる。正本の選択は設計判断として記録する。
- **実行コスト / 運用負荷**：全文複製を続けると更新コストが増える。正本と短い参照へ整理する。
- **重複する仕組み**：Issue / PRテンプレートの記入欄と重なるが、C-01は正本と参照の整合、テンプレートは入力入口である。
- **安全上必須か**：仕様と安全条件の一貫性に必要。
- **判定**：STRENGTHEN。
- **削除・再評価条件**：必要なContextをJIT取得でき、正本と参照の整合を契約テストで確認できる状態になった場合に再評価する。
- **関連Issue / 正本文書**：#56、C-01。Issue #56の監査条件とこの項目の判定を追跡する。 正本：AGENTS.md、docs、Issue / PRテンプレート。

### C-02 Review Context

- **ETCSLV分類**：Context
- **解決する失敗モード**：レビュー対象SHA、Issue範囲、受入条件、既存の指摘が不明なままレビューまたは修正を行うこと。
- **発火条件**：PRレビュー、レビュー修正、再レビューのとき。
- **入力 / Context**：PRテンプレートのReview Context、Issue、head SHA、レビュー履歴。
- **出力 / State変更**：レビュー対象、判定根拠、修正範囲の記録。
- **決定論的判定可能か**：SHA、変更ファイル、未解決スレッドは機械確認できる。
- **実行コスト / 運用負荷**：同じIssueとSHAを複数欄へ全文転記すると負荷が増える。必要な識別子と参照へ簡素化する。
- **重複する仕組み**：V-01 Codex Code Reviewと対象SHAを共有するが、C-02はレビュー入力の追跡、V-01はレビュー内容の検証を担う。
- **安全上必須か**：レビューの再現性には必要だが、記録の全文複製は不要。
- **判定**：SIMPLIFY。
- **削除・再評価条件**：対象SHA、Issue範囲、指摘の因果を別の追跡可能な記録で保持できる場合に再評価する。
- **関連Issue / 正本文書**：#56、C-02。Issue #56の監査条件とこの項目の判定を追跡する。 正本：PRテンプレート、Review Evidence Contract。

### C-03 Adaptive Development Flow

- **ETCSLV分類**：Context
- **解決する失敗モード**：#62の低リスク変更への過剰な記入と、誤ったTierによるGate bypass。基準SHA `9b72ff7743039ee11ac90aa47803989c38978d8c` のテンプレートに対して説明量だけを調整する。
- **発火条件**：Issue化前、実装開始時、PR提出前、影響が変わる修正時。
- **入力 / Context**：Issue、実差分、影響境界、承認済みDesign Decision。
- **出力 / State変更**：Issue / PRへLOW / MEDIUM / HIGHと理由、追加検証・承認状態を記録する。schema v3のphaseやGate結果は変更しない。
- **決定論的判定可能か**：語彙・参照・判定例の契約をテスト可能。意味上の安全影響は人間とAgentが確認し、今回は自動分類しない。
- **実行コスト / 運用負荷**：判定と短い根拠の記入が必要。LOWの対象外説明をまとめ、規則全文の再転記を減らす。実利用時間の削減率は未測定。
- **重複する仕組み**：Plan Review、Design Decision、Security、Reviewと同じリスクを参照するが、承認や検証の合否を代行しない。
- **安全上必須か**：Tier自体は安全Gateの代替ではない。標準検証・CI・Security・Review・Human Approval・Acceptanceを残すことが代替制御である。
- **判定**：SIMPLIFY
- **削除・再評価条件**：記入量が増える、誤分類が反復する場合は#62の実利用記録で再評価。削除時も既存安全境界を維持する。
- **関連Issue / 正本文書**：#62、#63、docs/adaptive-development-flow.md。影響範囲は文書とChild/PRの今回値欄。再検証は文書契約、CI、Security、現head Reviewと記入例照合。

### S-01 Issue、PR、head SHA

- **ETCSLV分類**：State
- **解決する失敗モード**：古いCI、Security、レビュー結果を新しい差分へ誤って適用すること。
- **発火条件**：commit、push、レビュー依頼、CI / Security待機、マージ確認の各時点。
- **入力 / Context**：Issue番号、PR番号、branch、head SHA、base SHA。
- **出力 / State変更**：対象SHAごとの検証記録、merge状態。
- **決定論的判定可能か**：SHA、CI、Security、PR状態は機械確認できる。
- **実行コスト / 運用負荷**：SHAの照合は各trust boundaryで必要。別工程の結果を一つにまとめない。
- **重複する仕組み**：L-01 CI、L-02a Security、V-01 ReviewとSHAを共有するが、S-01は各結果を同一SHAへ結び付けるState管理である。
- **安全上必須か**：古い検証結果の誤使用を防ぐために必要。
- **判定**：KEEP。
- **削除・再評価条件**：検証結果と差分の同一性を同等に証明できる仕組みへ置換する場合に再評価する。
- **関連Issue / 正本文書**：#56、S-01。Issue #56の監査条件とこの項目の判定を追跡する。 正本：PR、Git履歴、CI結果。

### S-02 FOLLOW-UPとDesign Decision履歴

- **ETCSLV分類**：State
- **解決する失敗モード**：未対応事項や設計判断の理由がセッションを跨いで失われ、同じ調査や判断を繰り返すこと。
- **発火条件**：今回PRの範囲外に残す指摘、設計判断、次Issueを登録するとき。
- **入力 / Context**：レビュー指摘、Issue、設計判断、対象PR。
- **出力 / State変更**：FOLLOW-UP台帳、親Issueまたは追加Issueへの参照。
- **決定論的判定可能か**：台帳項目、Issue番号、PR番号は機械確認できる。
- **実行コスト / 運用負荷**：登録と参照が必要。Issue本文、PR本文、台帳へ同じ説明を全文複製しない。
- **重複する仕組み**：レビューコメントとIssueの記録が重なるが、S-02は範囲外事項と設計判断の継続履歴を保持する。
- **安全上必須か**：未対応を消失させず、修正範囲を広げないために必要。
- **判定**：KEEP。
- **削除・再評価条件**：IssueとPRの状態から未対応事項を漏れなく復元できる場合に再評価する。
- **関連Issue / 正本文書**：#56、S-02。Issue #56の監査条件とこの項目の判定を追跡する。 正本：docs/review-followups.md、Issue。

### S-03 Implementation、Deploy、Product Acceptance状態

- **ETCSLV分類**：State
- **解決する失敗モード**：実装済み、マージ済み、Deploy済み、利用者が受入済みを同じ完了状態として扱うこと。
- **発火条件**：PRマージ、Deploy、実利用検証、検収のとき。
- **入力 / Context**：Issue受入条件、PR、Release Candidate、環境、実利用シナリオ。
- **出力 / State変更**：Implementation Done、Deployed、Product Acceptedなどの独立した記録。
- **決定論的判定可能か**：PRマージ、Deploy結果、検証実行は機械確認できる。利用者の受入は人間確認を記録する。
- **実行コスト / 運用負荷**：状態を分けるための記録負荷があるが、工程の取り違えを防ぐ。
- **重複する仕組み**：V-03 Acceptance Verificationと状態確認が重なるが、S-03はImplementation / Deploy / Acceptedの状態分離、V-03は利用者受入の検証を担う。
- **安全上必須か**：Production変更と利用者受入を混同しないために必要。
- **判定**：KEEP。
- **削除・再評価条件**：状態遷移を同等以上に表現できる構造化Stateへ移行する場合に再評価する。
- **関連Issue / 正本文書**：#56、S-03。Issue #56の監査条件とこの項目の判定を追跡する。 正本：Issue、PR、docs/acceptance-verification.md。

### S-04 Structured Current State契約

- **ETCSLV分類**：State
- **解決する失敗モード**：長時間タスクの再開時に現在のIssue / PR / SHA / 検証 / レビュー状態を誤認し、古い観測や検証結果を現headへ誤適用すること。
- **発火条件**：複数工程、複数レビューラウンド、中断再開、commit / push、CI / Security待機、Review、Merge判断、Product Acceptance完了のとき。
- **入力 / Context**：固定ルール、Current State、Issue、PR、branch、最新head SHA、local / CI / Security / Review結果、必要な証拠参照。
- **出力 / State変更**：schema v3に従ったphase、next action、Product Acceptance結果と終端アクション、Acceptance対象artifact、現行Deploy target、Conditionalの条件・期限・追跡Issue・未解決BLOCKER、stop reason、対象SHA、検証状態、レビューラウンド、P2分類の差分更新。
- **決定論的判定可能か**：schema必須field、enum、SHA一致、検証結果、停止条件の一部は機械判定できる。Issue受入条件とレビュー因果は確認が必要。
- **実行コスト / 運用負荷**：全文履歴の再読と重複転記を減らし、必要な識別子・enum・証拠参照だけを更新する。Stateと最新GitHub観測の照合は各trust boundaryで必要。
- **重複する仕組み**：S-01はIssue / PR / SHAと検証結果の紐付け、S-02はFOLLOW-UPとDesign Decisionの継続履歴、S-03はImplementation / Deploy / Acceptanceの分離を担う。S-04はそれらを置き換えず、再開時の型付きStateと更新契約を担う。
- **安全上必須か**：古いSHAの検証誤適用、停止条件の見落とし、chain-of-thoughtの永続化を防ぐために重要。
- **判定**：STRENGTHEN。
- **削除・再評価条件**：GitHub metadataと既存正本文書だけで、同じ再開性、SHA照合、停止、最小化を追跡可能に証明できる場合に再評価する。
- **関連Issue / 正本文書**：#59、#64、S-04。Issue #59のCurrent State契約と#64の読み取り専用GitHub観測を追跡する。正本：docs/ai-execution-state.md、AGENTS.md、scripts/collect-github-state.py、.agents/skills/pr-review-fix/SKILL.md、Issue / PRテンプレート。
  #64の収集scriptは観測artifactを出力するだけで、schema v3のverification、P2分類、approval、Acceptance、next actionを設定しない。初回 / 最終headが不一致、または取得不能ならartifactをState更新に利用しない。

### L-01 verify.shとCI

- **ETCSLV分類**：Lifecycle Hooks
- **解決する失敗モード**：ローカルで成功した変更が、独立環境でlint、型、test、buildに失敗すること。
- **発火条件**：PR作成前とPR更新後、GitHub Actions実行時。
- **入力 / Context**：Repository、変更差分、標準検証入口、依存関係。
- **出力 / State変更**：CI結果、検証ログ、merge可否に使う状態。
- **決定論的判定可能か**：lint、type check、test、buildの成功・失敗を判定する。
- **実行コスト / 運用負荷**：ローカルとCIは異なるtrust boundaryであり、同一結果として省略しない。
- **重複する仕組み**：CIは独立環境のPR検証、verify.shはローカル入口。L-02a Securityは別の安全検証。
- **安全上必須か**：変更の機械的な再検証は必要。Security Boundary、Human Approval Boundary、Production保護の代替ではない。
- **判定**：KEEP。
- **削除・再評価条件**：同等の独立検証と失敗時停止へ置換する場合に再評価する。
- **関連Issue / 正本文書**：#56、#183、L-01。正本：templates/verification、.github/workflows/ci.yml。#181で実行回帰を独立させた後、#183で台帳schema・集約表の一致だけを強制するHarness suiteを削減した。台帳の書式整合は現在のCI責務ではない。

### L-03 PRODUCT UI Standard contract test

- **ETCSLV分類**：Lifecycle Hooks
- **解決する失敗モード**：PRODUCT UI標準、`design.md`雛形、README導線、またはCI配線が変更されたときに、必須のUI Level、状態、Design Profile、AI境界、既存正本参照が欠落したまま後続案件へ流れること。
- **発火条件**：Template CIでPRODUCT UI標準の契約テストを実行するとき。標準文書、`templates/app/docs/design.md`、README、または対応CI配線を変更するPRでは、同テストを実行対象とする。
- **入力 / Context**：リポジトリ差分、`docs/product-ui-standard.md`、`templates/app/docs/design.md`、`README.md`、`tests/product-ui-standard/run-samples.sh`、`.github/workflows/ci.yml`、Issue #92、AGENTS.md、Harness台帳。
- **出力 / State変更**：必須マーカーの存在確認とCI結果を出力し、欠落時はPRの検証を失敗させる。Product AcceptanceやCurrent State schemaは変更しない。
- **決定論的判定可能か**：Shellの`grep`による必須契約、`bash -n`による構文、CIステップの存在を決定論的に判定できる。
- **実行コスト / 運用負荷**：外部サービスや追加依存を使わない軽量なShell 1ステップ。既存Template CIの実行時間とログを少量増加させる。
- **重複する仕組み**：L-01は標準検証とCI実行を担う。L-03はPRODUCT UI標準固有の必須契約を担い、通常のlint/type/test/buildを代替しない。
- **安全上必須か**：後続案件のUI計画品質とAIの設計境界を、文書・雛形・CIの契約欠落から保護するために必要。Security Boundary、Human Approval Boundary、Production保護の代替ではない。
- **判定**：KEEP。
- **削除・再評価条件**：PRODUCT UI標準の必須契約を、同等以上に決定論的かつ独立して検証し、CIで実行される既存ハーネスへ移行できる場合に再評価する。
- **関連Issue / 正本文書**：#92、L-03。正本：docs/product-ui-standard.md、templates/app/docs/design.md、tests/product-ui-standard/run-samples.sh、.github/workflows/ci.yml、AGENTS.md。

### L-02a Security Preflight

- **ETCSLV分類**：Lifecycle Hooks
- **解決する失敗モード**：通常CIの成功だけで、Repository、Secret、Tool権限、外部送信先に関するSecurity Boundaryの逸脱や、利用可能なセキュリティ検査の失敗を見逃すこと。
- **発火条件**：PR更新時にSecurity workflowまたはPR単位のSecurity Preflightを実行するとき。
- **入力 / Context**：対象SHA、Git管理対象、workflow、Tool権限、Secretの扱い、外部送信先。
- **出力 / State変更**：Security Preflightの成功、警告、失敗、未実行の状態。利用不能を成功扱いにしない。
- **決定論的判定可能か**：workflowの実行状態、対象SHA、許可されたscopeは機械判定できる。利用可否や例外は記録して判断する。
- **実行コスト / 運用負荷**：PR更新ごとの独立した検査。CIやCodeQL、Dependabotの結果を代用しない。
- **重複する仕組み**：L-02b CodeQLとL-02c Dependabotとは検出対象が異なる。L-02aはSecurity Boundary、権限scope、PR検査の実行状態を対象とする。
- **安全上必須か**：Security Boundary、Least Privilege、Human Approval、Production保護を維持するために必要。
- **判定**：KEEP。
- **削除・再評価条件**：対象SHA、許可範囲、失敗時停止、監査記録を同等以上に保証するSecurity機構へ移行する場合に再評価する。
- **関連Issue / 正本文書**：#56、L-02a。Issue #56の監査条件とこの項目の判定を追跡する。 正本：templates/security、docs/ai-agent-security-boundary.md。

### L-02b CodeQL

- **ETCSLV分類**：Lifecycle Hooks
- **解決する失敗モード**：コードのデータフロー、Injection、権限処理などの脆弱性を、通常CIやSecurity Preflightの成功だけで見逃すこと。
- **発火条件**：CodeQLが対象言語とRepositoryで有効化され、PR、push、またはスケジュールの解析を実行するとき。
- **入力 / Context**：対象SHA、対象言語のソースコード、ビルド設定、CodeQL query suite、解析環境。
- **出力 / State変更**：Code Scanningの解析結果、アラート、PRへのチェック状態。
- **決定論的判定可能か**：対象SHA、解析結果、チェック状態は機械判定できる。CodeQLが利用不能または未設定の場合は成功扱いにしない。
- **実行コスト / 運用負荷**：言語解析と必要なビルドの実行負荷がある。対象言語、解析時間、失敗率を測定して再評価する。
- **重複する仕組み**：L-02a Security PreflightとL-02c Dependabotとは検出対象が異なる。L-02bはソースコードとデータフローの解析を対象とする。
- **安全上必須か**：コード上の既知の脆弱性を検出するために必要。利用不能時の扱いも安全条件として維持する。
- **判定**：KEEP。
- **削除・再評価条件**：対象言語、exact SHA、失敗時の停止、解析結果の監査を同等以上に保証するコード解析へ移行する場合に再評価する。
- **関連Issue / 正本文書**：#56、L-02b。Issue #56の監査条件とこの項目の判定を追跡する。 正本：GitHub Code Scanning、docs/github-repository-security-baseline.md。

### L-02c Dependabot

- **ETCSLV分類**：Lifecycle Hooks
- **解決する失敗モード**：依存パッケージの既知脆弱性や更新漏れを、アプリケーションCIやCodeQLの成功だけで見逃すこと。
- **発火条件**：Dependency Graphがmanifestまたはlockfileを解析し、Dependabot alertまたは更新PRを生成するとき。
- **入力 / Context**：対象Repository、manifest、lockfile、Dependency Graph、脆弱性データ、更新ポリシー。
- **出力 / State変更**：Dependabot alert、更新PR、依存更新のレビュー対象。
- **決定論的判定可能か**：対象manifest、alert、更新PR、更新元の脆弱性情報は機械確認できる。Dependency Graphや脆弱性データが利用不能な状態は成功扱いにしない。
- **実行コスト / 運用負荷**：依存解析と更新PRのレビュー負荷がある。alert件数、更新PR数、対応時間を測定して再評価する。
- **重複する仕組み**：L-02a Security PreflightとL-02b CodeQLとは検出対象が異なる。L-02cはmanifest / lockfileと依存脆弱性を対象とする。
- **安全上必須か**：依存由来の既知脆弱性を管理するために必要。自動更新PRの採用は人間レビューとCIを経る。
- **判定**：KEEP。
- **削除・再評価条件**：Dependency Graph、脆弱性情報、更新PR、レビュー記録を同等以上に保証する依存管理機構へ移行する場合に再評価する。
- **関連Issue / 正本文書**：#56、L-02c。Issue #56の監査条件とこの項目の判定を追跡する。 正本：GitHub Dependabot、docs/github-repository-security-baseline.md。

### V-01 Codex Code Review

- **ETCSLV分類**：Verification
- **解決する失敗モード**：CIでは表現できないIssue受入条件、仕様、レビュー観点の漏れを見落とすこと。
- **発火条件**：CI成功後、PRの対象SHAでレビューを依頼するとき。
- **入力 / Context**：Issue、PR差分、AGENTS.md、対象SHA、既存レビュー。
- **出力 / State変更**：レビュー結果、コメント、レビュー対象SHA。
- **決定論的判定可能か**：レビューの実行履歴と対象SHAは機械確認できる。内容の妥当性は人間が確認する。
- **実行コスト / 運用負荷**：CIの代替ではない。レビュー後に新規改善探索を無制限に繰り返すとコストだけが増える。
- **重複する仕組み**：L-01 CIとは仕様・受入条件の意味検証が異なる。C-02 Review Contextとはレビュー入力と判定の責務が異なる。
- **安全上必須か**：Issue仕様と差分の対応を独立に確認するために必要。
- **判定**：SIMPLIFY。
- **削除・再評価条件**：Issue受入条件、仕様、Security、変更因果を同等に検証できる別のレビュー契約が成立した場合に再評価する。
- **関連Issue / 正本文書**：#56、V-01。Issue #56の監査条件とこの項目の判定を追跡する。 正本：PR、AGENTS.md、レビュー履歴。

### V-02 Review Evidence ContractとP2収束

- **ETCSLV分類**：Verification
- **解決する失敗モード**：Severityだけで指摘をBlocking扱いすること、P2修正で無制限の修正ループへ入ること。
- **発火条件**：P0、P1、P2、P3のレビュー指摘を分類し、修正または記録するとき。
- **入力 / Context**：Finding、成立条件、PR因果、受入条件、再現手順、対象SHA。
- **出力 / State変更**：BLOCKING、IN-SCOPE FIX、FOLLOW-UP、DISMISS、レビュー収束状態。
- **決定論的判定可能か**：必須項目、対象SHA、未解決スレッドは機械確認できる。因果と受入条件はレビューで確認する。
- **実行コスト / 運用負荷**：記録負荷はあるが、P2の追加修正ループを制限する。
- **重複する仕組み**：V-01 Codex Code Reviewから指摘を受けるが、V-02はSeverity、因果、収束分類と記録を担い、レビュー実行を代替しない。
- **安全上必須か**：誤った修正範囲拡大と見逃しを分けるために必要。
- **判定**：KEEP。
- **削除・再評価条件**：同じ証拠、分類、停止、再レビューを同等に保証する契約へ移行する場合に再評価する。
- **関連Issue / 正本文書**：#56、V-02。Issue #56の監査条件とこの項目の判定を追跡する。 正本：AGENTS.md、.agents/skills/pr-review-fix。

### V-03 Acceptance Verification

- **ETCSLV分類**：Verification
- **解決する失敗モード**：実装やDeployが成功しただけで、利用者の目的を達成したと判断すること、テスト実行をRequirement検証と混同すること、または計画時の予測・失敗仮説と実績の差分を次回計画へ戻せないこと。
- **発火条件**：ReleaseまたはProduction Deploy後、検収を実施するとき。
- **入力 / Context**：利用目的、対象ユーザー、実利用シナリオ、成功条件、実データ、環境、計画時の主要予測、設計判断の失敗仮説、設計価値と代替案優位性の確認条件。
- **出力 / State変更**：Verification Evidence（Requirement、Risk、Test、Result、Evidence）、Residual Risk Summary、Accepted、Not Accepted、Conditional、発見事項の分類、Plan vs Reality（実績、失敗した前提、不要 / 過剰設計、予期せぬ問題、次回の教訓）。
- **決定論的判定可能か**：開始条件、成功条件、環境は検証できる。利用者の有用性は人間が確認する。
- **実行コスト / 運用負荷**：Deploy確認とは別工程。既存のAcceptance Verificationへ最小契約を追加し、PRには正本参照とResidual Risk Summaryだけを記録する。計画時の予測・失敗仮説と実績の差分を既存のProduct Accepted記録へ追加し、受入条件を同じ文面で複数文書へ複製しない。
- **重複する仕組み**：S-03 Implementation / Deploy状態と関係するが、V-03は利用者目的の実利用検証であり、状態記録を代替しない。
- **安全上必須か**：Product Acceptanceを実装完了と混同しないために必要。
- **判定**：KEEP。
- **削除・再評価条件**：利用者の目的、成功条件、計画と実績の差分を同等に確認できる運用へ移行する場合に再評価する。
- **関連Issue / 正本文書**：#56、#58、#119、V-03。Issue #56の監査条件とIssue #58のPlan vs Reality記録を追跡する。 正本：docs/acceptance-verification.md。

### C-04 Human-facing HTML Status Report

- **ETCSLV分類**：Context
- **解決する失敗モード**：観測JSONやMarkdownの正本を人間が読む際に、対象SHA、収集時刻、未観測項目、残作業を見落とすこと。
- **発火条件**：利用者が既存の観測JSONをローカルで人向けに確認するとき。
- **入力 / Context**：利用者が指定した既存JSON、入力パス、観測時刻、Issue、PR、Workflow、Reviewの観測項目。
- **出力 / State変更**：ローカルの静的HTML。正本JSON、GitHub、CI、Security、Review、Acceptance、マージ状態を変更しない。
- **決定論的判定可能か**：固定JSONからの表示、HTMLエスケープ、入力非変更、出力上書き拒否はfixtureで判定できる。観測内容の意味づけは行わない。
- **実行コスト / 運用負荷**：Python標準ライブラリだけで単一HTMLを生成する。外部asset、ネットワーク、公開、追跡用の新しいStateは増やさない。
- **重複する仕組み**：S-04 Structured Current Stateと#64の観測JSONは正本と再開状態を担い、C-04はそれらを変更せず人間向け表示だけを担う。
- **安全上必須か**：Security Boundary、Human Approval Boundary、Production保護の代替ではない。入力文字列をHTMLとして実行しない表示境界として必要である。
- **判定**：SIMPLIFY。
- **削除・再評価条件**：同じ正本参照、オフライン可読性、HTMLエスケープ、入力非変更をより小さい既存表示で満たせる場合に再評価する。
- **関連Issue / 正本文書**：#67、C-04。正本：scripts/render-status-report.py、docs/html-status-report.md、tests/html-status-report/run-samples.sh。

## 削除候補と簡素化候補

今回の棚卸しでは既存ハーネスを削除しない。
次の候補は、失敗モード、代替制御、実測コストを確認してから別PRまたは別Issueで判断する。

| 候補 | 判定 | 条件 |
| --- | --- | --- |
| 同じ運用ルールをAGENTS.md、標準フロー、Skillへ全文複製する説明 | SIMPLIFY | 正本文書を決め、参照と各工程固有の停止条件へ整理できること。 |
| 観測された失敗を追加せずに増やす補助Skillや追加レビュー | REMOVE_CANDIDATE | 対象失敗モード、再利用、Security上の必要性を示せないこと。 |
| 同じtrust boundaryで繰り返す重複検証 | REMOVE_CANDIDATE | 同一SHA、同一入力、同一環境であることを確認し、別の境界を失わず統合できること。 |
| レビュー後に新規改善探索へ戻る追加修正ループ | REMOVE_CANDIDATE | BLOCKINGでなく、今回Issueの受入条件やPR差分に因果がないこと。 |

## 新規ハーネスの記録様式

新しいハーネスを追加するPRでは、次の項目をPR本文とこの台帳へ記録する。

```text
Harness ID:
名称:
ETCSLV分類:
解決する失敗モード:
発火条件:
入力 / Context:
出力 / State変更:
決定論的判定可能か:
実行コスト / 運用負荷:
重複する仕組み:
安全上必須か:
判定: KEEP / STRENGTHEN / SIMPLIFY / REMOVE_CANDIDATE
削除・再評価条件:
関連Issue / 正本文書:
```

既存ハーネスを変更する場合も、変更理由、対象SHA、検証結果、削除または再評価条件を記録する。
記録できない新しいハーネスは、実装へ追加する前に停止して設計判断を確認する。

## モデル更新時の再評価

モデル、Codex、GitHub Actions、Toolの能力が変わったときは、次を確認する。

- 既存ハーネスが解決している失敗モードが現在も成立するか。
- モデルだけでは得られないContext、State、権限境界を補っているか。
- 決定論的なtest、type、lint、CI、Security ruleへ移せるか。
- 実行時間、API利用量、レビュー回数、運用負荷が変化したか。
- 安全上必要な制約を弱めずに簡素化できるか。
- 判定変更の根拠、実測結果、対象環境、対象SHAを記録したか。

再評価は、能力向上だけを理由に削除を決めない。
失敗モード、代替制御、実測結果、Securityと人間承認の境界を確認してから判定を更新する。

## 既存標準との関係

この台帳は、Issue、Design Decision、CI、Security、Codex Review、Review Evidence Contract、Safe Auto-Fix / Auto-Merge、Deployment、Product Acceptanceを置き換えない。
各工程の正本は既存文書に置き、台帳には役割、判定、重複、コスト、再評価条件を記録する。

- AGENTS.md：作業時の共通ルール
- docs/nine-standard-ai-development-flow.md：工程の流れ
- docs/ai-agent-security-boundary.md：AIエージェントの情報とToolの境界
- docs/safe-auto-fix-auto-merge.md：自動修正の安全条件
- docs/github-repository-security-baseline.md：GitHub側の防御
- docs/acceptance-verification.md：実利用検証と検収
- Verification Evidence ContractとResidual Risk Summaryは同文書内でAcceptance Verificationへ接続し、Current State、CI、Security、Reviewを置き換えない

## AGENTSから移した運用・安全責務

固定原文はmain `d4ee8ee56ad15ca4bcbca604bc3622a1400b667b` のAGENTS。Issue #177でAGENTS本文を短縮し、以下を詳細責務の正本として適用する。既存節は概説・具体手順、以下は旧AGENTSから保持する責務・例外。短縮後も両方を適用し、矛盾があれば推測せず停止する。Security・承認条件は変更しない。参照テストも正本へ切り替える。docs内の重複整理は後続Issueで行う。

### 移行契約: Harness Minimalism

既存ハーネスの台帳は docs/ai-development-harness-inventory.md とする。
ハーネスを追加または変更する場合は、解決する失敗モード、発火条件、入力とContext、出力とState変更、決定論的判定の可否、実行コスト、重複、安全上の必須性、判定、削除・再評価条件、関連Issueを記録する。

- 失敗モードを示せない新規ハーネスは、実装前に停止して設計判断を確認する。
- AIレビューで繰り返し検出できる問題は、test、type、lint、CI、Security ruleなどの決定論的チェックへ移せるか評価する。
- Model、Codex、Tool、CIの能力向上だけを理由に、Security Boundary、Human Approval Boundary、Production保護を削除または弱体化しない。
- 既存ハーネスを簡素化する場合は、対象SHAまたは実測結果、代替制御、影響範囲を記録する。
- 削除候補は、別のIssueまたはPRで依存関係と代替制御を確認してから判断する。
