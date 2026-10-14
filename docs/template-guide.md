# Nine標準AI開発テンプレート 利用ガイド

## 1. このリポジトリの役割

`ai-development` は、各AI開発プロジェクトで共通利用する開発ルール・Issue/PRテンプレート・CI/セキュリティ設定の原本を管理するリポジトリです。

新しいプロジェクトでは、このリポジトリの内容をそのまま全部コピーするのではなく、プロジェクトの技術構成に合わせて必要なテンプレートを選び、調整して利用します。

基本思想は次の分担です。

- ChatGPT: 要件整理、設計、親Issue/子Issueの作成、Issue品質チェック
- GitHub: Issue、PR、履歴、CI、セキュリティ、マージ制御
- Codex: Issue単位の実装、ローカルテスト、PR作成、既存PRのhead branchでの修正
- GitHub Actions: Codexとは独立した機械的な再検証
- 人間: 仕様確定、例外判断、最終レビュー、Merge

## 2. 新規プロジェクト開始時の使い方

新しいプロジェクトでは、まずGitHubに対象プロジェクト用リポジトリを作成します。

その後、原則として以下を準備します。

1. `AGENTS.md` と、その参照先を支える `docs/` 一式（下記配置手順）
2. `docs/ai-agent-security-boundary.md`
3. `docs/ai-development-harness-inventory.md`
4. `.github/ISSUE_TEMPLATE/parent-issue.md`
5. `.github/ISSUE_TEMPLATE/child-issue.md`
6. `.github/pull_request_template.md`
7. `.github/workflows/ci.yml`
8. Dependabot設定
9. Secrets管理方針
10. Security Preflight
11. 利用可能ならCodeQL
12. Ruleset / Branch protection
13. `Automatically delete head branches` の有効化
14. Framework Decision正本文書（`docs/architecture/framework-decision.md`）を配置
15. Plan Review正本文書（`docs/plan-review-gate.md`）を配置
16. `.agents/skills/` と参照用 `templates/` 一式を配置し、Skill / State契約 / 標準検証原本への入口を保つ

設定後、計画書を親Issue・子Issueへ変換します。新規Web/UI案件ではFramework DecisionをUI Level DecisionとPlan Reviewより前に確認し、その結果を引き継ぎます。子Issue単位でCodexに実装させます。ただし、Issue化の前に [docs/plan-review-gate.md](plan-review-gate.md) のPlan Review Gate（Grilling）を実施します。重大な未決定事項がある場合はNEEDS_DECISIONとしてIssue化を止め、Design Decision確定後に再Reviewします。




### 最小AGENTSと参照先の配置

最小AGENTSは単体で配布しない。`AGENTS.md` と `docs/` 一式を同じ原本revisionから配置する。必須入口には `docs/nine-standard-ai-development-flow.md`、`docs/code-review-contract.md`、`docs/test-design.md`、`docs/design-state-modeling.md`、`docs/parent-issue-completion.md`、`docs/minimal-development-contract.md` があり、条件表から参照するSecurity / Framework / UI / RAG / State / Acceptance等も含める。directory構造を維持し、参照先を選別して欠落させない。

Skillの入口・State契約・文書からの原本参照も維持するため、`.agents/skills/` と `templates/` を参照資産として併せて配置する。配置はSkill/helperの実行許可や自動起動を意味しない。通常reviewはCodexが直接対応する。Actions・Dependabot・verifyの実行設定は引き続き技術構成に合うものを選び、以下の原本copyだけで実行設定済みと扱わない。

次の例は新規projectの未配置directoryに限定する。`template_source_root` は原本checkout、`project_output_root` は対象projectのabsolute pathへ設定する。既存projectへ一括上書きせず、既存のAGENTS / docsとの責務・差分を個別に確認する。

```bash
set -e
: "${template_source_root:?原本checkoutのabsolute pathを設定する}"
: "${project_output_root:?対象projectのabsolute pathを設定する}"
for path in AGENTS.md docs .agents/skills templates; do
  test -e "$template_source_root/$path"
  if test -e "$project_output_root/$path"; then
    printf '既存の配置先を上書きしません: %s\n' "$path" >&2
    exit 1
  fi
done
mkdir -p "$project_output_root/.agents"
# ai-development自身の検証行は生成projectへ持ち込まない。
awk '!/^このrepoの検証は全 /' "$template_source_root/AGENTS.md" > "$project_output_root/AGENTS.md"
cp -R "$template_source_root/docs" "$project_output_root/docs"
cp -R "$template_source_root/.agents/skills" "$project_output_root/.agents/skills"
cp -R "$template_source_root/templates" "$project_output_root/templates"
```

配置後、root AGENTS内の `docs/` / Skill path、および `docs/minimal-development-contract.md` の条件表の参照先が対象projectで開けることを確認する。案件固有の `docs/design.md` はPRODUCT案件で別途作成する。必要な正本が欠落・取得不能ならIssue生成・実装開始へ進まず、配置を修復する。`scripts/verify.sh` とCIは下記の標準検証・技術スタック別手順で設定する。


## 2.1 Risk Tierの記入

新規プロジェクトでは `docs/adaptive-development-flow.md` も配置する。Child IssueとPRのRisk Tier欄に `LOW / MEDIUM / HIGH` の今回値と理由を記入し、詳細は [正本文書](adaptive-development-flow.md) を参照する。

既定MEDIUM、混在は最大Tier、安全影響不明・Gate変更はHIGH。LOWは実行動作・API・依存・workflow・安全ルールに影響しない文言や表示だけの変更に限定する。LOWの目的・範囲・根拠・テスト証拠は一段落で記録でき、対象外欄は理由をまとめて参照できる。必須情報を空欄にしてよいという意味ではない。

MEDIUMでは影響と通常テスト、HIGHでは安全境界・復旧・必要な承認と追加検証を記す。標準検証・CI・Security・Codex Review・Human Merge判断・適用対象Acceptanceは省略しない。Issue化前、実装開始時、PR提出前、影響変更時に再判定する。

## 2.2 テンプレートに記入する値

テンプレートは今回の判断・範囲・証拠を記入し、停止条件、安全境界、検収、レビュー収束の詳細は正本文書を参照する。リンクだけで必要な今回値を省略してはならない。

記述はDecision Firstとし、冒頭で採用案、主要理由、影響を把握できるようにする。Non-goalsへ今回扱わない範囲を記録し、Alternativesは原則として案と主要な却下理由の表にする。背景、用語、将来拡張などの定型章は判断に必要な場合だけ追加する。

生成後は、重複説明、意思決定に不要な章、同じ理由の言い換え、将来の可能性だけを述べる文章を削除する。コード、diff、Issueから自明な内容も再掲しない。ただし、既存Gateが要求する今回値と証拠は削除しない。

Design Decisionの最小構成は次のとおりとする。案件固有の判断や既存Gateに必要な情報がある場合だけ節を追加する。

```md
# Decision
採用:
理由:
影響:

# Alternatives
| 案 | 却下理由 |
| --- | --- |

# Non-goals
- 今回扱わないもの

# Implementation Notes
意思決定の理解に必要な場合のみ記載
```

| Tier | テンプレートに記入する値 | 正本参照で不足しない情報 |
| --- | --- | --- |
| LOW | 目的、範囲、理由、テスト証拠を一段落で記入する。 | 必須Gate、Security、Review、人間Merge判断。 |
| MEDIUM | 目的、範囲、影響、6観点のテスト、対象SHAと検証結果を記入する。 | 停止条件、安全境界、検収、レビュー収束の詳細。 |
| HIGH | MEDIUMに加え、安全境界、復旧、必要な人間承認と追加検証を記入する。 | 正本文書の制約を満たした具体的な承認・例外の根拠。 |

詳細をテンプレートへ再掲せず、[Adaptive Development Flow](adaptive-development-flow.md)、[AI Agent Security Boundary](ai-agent-security-boundary.md)、[Acceptance Verification](acceptance-verification.md)、[Review Follow-ups](review-followups.md)、[Safe Auto-Fix / Auto-Merge](safe-auto-fix-auto-merge.md)を正本として参照する。

## 3. AGENTS.md

### 目的

CodexなどのAIエージェントに、プロジェクトで守るべき共通ルールを伝えるためのファイルです。

主なルール:

- GitHub Issueを仕様の基準とする
- 1子Issue = 1 PR
- Issue範囲外を実装しない
- 依存Issueを確認する
- mainへ直接pushしない
- 必要なテストを実行する
- GitHub Actions CIの結果も確認する
- Codexレビュー後の修正は既存PRのhead branchへ反映し、head SHA更新を確認する
- レビュー指摘はReview Evidence Contractで成立条件・期待結果・実結果・PR因果・受入条件・再現または静的根拠を記録する
- 秘密情報をcommitしない
- 仕様が不明確なら推測で拡張しない

### 新規プロジェクトでの扱い

上記「最小AGENTSと参照先の配置」に従い、`ai-development/AGENTS.md` と `docs/` / Skill / 参照原本を併せて配置します。AGENTS末尾のai-development自身に固有な検証・配置履歴行は持ち込まず、対象projectの `./scripts/verify.sh`、技術構成、禁止事項を設定します。AGENTSだけのコピーで移行完了にしません。

## 4. 親Issueテンプレート

ファイル: `.github/ISSUE_TEMPLATE/parent-issue.md`

親IssueはGoal / Context / Scope・Boundaries / Non-goals / Done / Verification / Children・Dependenciesでロードマップを記録する。Plan Reviewの判定・理由・正本参照はContextへ短く保存する。Risk Tierと安全境界は常時必要。専門事項は[最小契約の条件付き参照](minimal-development-contract.md#条件付き参照)に従い該当時だけ追加し、非該当の空欄は作らない。親の全体Doneは子Mergeだけでなく目的と人間確認で判定する。

## 4.1 デプロイ設計とRelease / Production計画

Issue計画時に、実装完了と本番投入可能を分けて記録します。
Deployment as Codeの正本は [docs/deployment-release-design.md](deployment-release-design.md) です。
Release / Productionが適用される場合に、Production runtime、Container、Persistent data、Deployment method、Secretsの扱い、backup / migration、Full-System Security Audit、Smoke Test、Health Check、Monitoring、Rollbackの今回値または設計記録への参照を追加します。非Deploy案件には空欄を設けません。

プロジェクトごとにCloudflare、Home PC / VPS、self-hosted runner、Docker / Compose、Staging、自動Deploy、人間承認の要否を判断し、不要なものは理由を記録します。
MergeはProduction Deployを意味しません。CI、PR単位Security Check、Full-System Security Auditの`PASS`または理由と適格性を確認した`NOT_APPLICABLE`、Release判定、必要なbackupとmigration確認を経てProductionへ進み、Deploy後のHealth CheckとRollbackまで確認可能にします。
詳細な手順・データ互換性・Secretsの安全条件は正本文書へ集約し、親Issueや標準フローへ重複記載しません。

## 4.2 実利用検証と検収

実装・Deployの完了と、作る目的を満たしたことの検収を分けて記録します。検収の正本は [docs/acceptance-verification.md](acceptance-verification.md) です。

親Issueの計画段階で、解決したい課題、対象ユーザー、実利用シナリオ、成功条件、失敗条件、検証環境、実データ / fixture、人間確認項目、検収タイミングを定義します。

Deploy後は、Health Check / Smoke Testとは別に主要ユースケースを最初から最後まで実行し、計画時の成功条件と照合します。`Implementation Done`、`Deployed`、`Product Accepted` は別状態です。検収結果は `Accepted` / `Not Accepted` / `Conditional` で記録し、発見事項は `ACCEPTANCE BLOCKER` / `DEFECT` / `IMPROVEMENT` / `FUTURE` に分類します。重要なRequirement・主要リスクの検証証跡と残存リスク要約は、[Verification Evidence Contract](acceptance-verification.md#5-verification-evidence-contract--residual-risk-summary)に従って記録します。

新要求や改善案を、元PRのレビュー修正ループへ無制限に戻しません。必要に応じて別Issue候補として次サイクルへ送り、設計前提の誤りは `Design Decision Escalation` へ戻します。

## 4.3 Plan Review Gate（計画書Grilling）

計画書の存在と、実装開始できるほど重要判断が確定していることは別です。Plan Review Gateの正本は [docs/plan-review-gate.md](plan-review-gate.md) とし、計画書からIssue化する前に参照します。

- PASS: 親Issue / 子Issue化へ進む
- NEEDS_DECISION: Issue化・実装開始を止め、既存のDesign Decisionへ戻す
- NOT_APPLICABLE: 軽微な変更等。省略理由を記録する

Plan Reviewは子Issue品質チェックを置き換えません。Issue化後は従来どおり docs/issue-quality-check.md を使い、1 Issue / 1 PR、CI、Codex Code Review、人間Mergeの流れを維持します。Deployment設計、実利用検証、Issue #30の状態設計原則は各正本文書を参照し、同じ詳細を重複記載しません。

## 4.4 計画書の作り方（会話）

方針は会話で固め、テンプレへ転記する。未決欄は推測で埋めず確認する。手順・依頼文・READMEに全文を置かない理由は [計画書の作り方](plan-authoring.md) を正本とする。記入例は [Web Todo 計画書サンプル](../templates/planning/web-todo-app-plan.sample.md)。Plan Review の判定は [Plan Review Gate](plan-review-gate.md) のままとする。

## 5. 子Issueテンプレート

ファイル: `.github/ISSUE_TEMPLATE/child-issue.md`

子IssueはGoal / Context / Scope・Boundaries / Non-goals / Done / Verification / Dependenciesを記入する。Risk Tierと理由、安全境界はScope / Boundaries、独立した完了判定はDoneとVerificationへ置く。6観点から影響に応じた検証を選び、6つの空欄は要求しない。対象SHAはPR / 再開 / 検収など識別が必要な段階で記録する。1子Issue = 1 PRを維持し、MUST不足時は[Issue Quality Check](issue-quality-check.md)に従って停止する。

詳細なDesign Decision Escalation、Security Boundary、Harness、Current Stateのenum、検収とレビュー収束は正本文書を参照する。テンプレートには今回の例外、承認、停止理由、引き継ぎ先だけを記録する。

## 6. 子Issue品質チェック

ファイル: `docs/issue-quality-check.md`

子IssueをGitHubへ正式登録する前に、MUSTを確認する。目的、変更範囲、独立した完了判定とテスト、1 PRでのレビュー可能性、依存関係、安全境界の1つでも欠落した場合は、Scoreにかかわらず登録・実装開始を停止する。

読みやすさ、背景、補足例はSHOULDであり、それだけの不足は改善候補として継続できる。Scoreは補助表示で、各観点0〜2点、合計0〜12点だけを有効値とする。高ScoreでもMUST不足を打ち消さない。

## 7. Pull Requestテンプレート

ファイル: `.github/pull_request_template.md`

PRには対応Issue、差分、判断、レビュー上の注意点、Risk Tierと安全境界、対象SHA、標準検証・CI・Security・Codex Reviewの結果、残課題だけを記録する。GitHubから確認できる変更ファイル一覧は再掲しない。修正時は既存PR branchと修正後SHAを記録し、詳細なP2分類・Evidence・Safe Auto-Fix条件は正本文書を参照する。検証証跡は正本への参照と、Verified / Not Verified / Blocked・Skipped / Known Remaining Risk / Human Decision Requiredの短い要約をPRへ記録する。

CI、Security、Reviewは別ゲートであり、最終Mergeは人間が判断する。

## 8. 標準検証入口とGitHub Actions CIテンプレート

保存場所:

- `templates/verification/verify.sh`
- `templates/github-actions/`

### 標準検証入口

新規プロジェクトでは、まず `templates/verification/verify.sh` を `scripts/verify.sh` として配置し、実行権限を付与します。

ローカル・Agent・GitHub Actionsの検証コマンドは、原則として次の1つに統一します。

```bash
./scripts/verify.sh
```

標準入口は次の順序で工程を実行します。

1. lint
2. type check
3. test
4. build

対象外工程は `skipped` と理由をログへ出します。対象工程のツール未導入や失敗は工程名を示して非0終了し、後続工程へ進みません。4工程すべてが対象外、または工程スクリプトが1つもない場合も、検証ゼロの成功を防ぐため非0終了します。

### Node.js

`node-ci.yml` はNode.js / TypeScript系プロジェクト向けです。

- `.nvmrc` にNode.jsの正確なバージョンを固定する
- `package-lock.json` をcommitし、CIは `npm ci` を使う
- `package.json` の `scripts.lint`、`scripts.typecheck`、`scripts.test`、`scripts.build` を標準入口から実行する
- 存在しないscriptは対象外として明示する

### Python

`python-ci.yml` はPython系プロジェクト向けです。

- `.python-version` にPythonの正確なバージョンを固定する
- `requirements-dev.txt`、`uv.lock`、`poetry.lock` 等でRuff / mypy / pytest / buildなどの開発ツールを固定する
- Ruff、mypy、pytest、PEP 517 buildの設定がある工程を標準入口から実行する
- 設定がない工程は対象外として明示する。テストファイルが存在する場合のpytest未導入は失敗とする

### Generic

`generic-ci.yml` はNode.js / Python以外、または技術スタック未確定のプロジェクト向けです。

- `scripts/lint.sh`
- `scripts/typecheck.sh`
- `scripts/test.sh`
- `scripts/build.sh`

を必要な工程だけ実装し、標準入口から順番に呼び出します。工程スクリプトがない工程は対象外として明示します。工程スクリプトが1つもない場合は、既存の `scripts/ci.sh` や任意の単一コマンドへ暗黙にfallbackせず、標準検証を失敗させて工程別スクリプトへの移行を促します。

### 生成直後のサンプル検証

テンプレート正本には `tests/verification/run-samples.sh` を含めます。このスクリプトは生成相当の一時プロジェクトを作成し、次を検証します。

- 正常系で4工程が順序どおり成功する
- lint失敗時に非0終了し、失敗工程をログから特定できる
- lint失敗後にtype check / test / buildが実行されない

### 開発ツールの更新

バージョン固定を変更する場合は、固定ファイル、依存lock、CIテンプレートを必要に応じて同じPRで更新します。更新後は `tests/verification/run-samples.sh` と対象プロジェクトの `./scripts/verify.sh` を再実行し、更新理由と結果をPR本文へ記録します。

## 9. Ruleset / Branch protection

関連資料:

`templates/github-security/ruleset-guide.md`

### 目的

AGENTS.mdに書いたルールを、GitHub側でも強制します。

推奨設定:

- mainへの直接pushを禁止
- Pull Requestを必須化
- GitHub Actions CI成功を必須化
- force push禁止
- `main` など保護対象branchの削除を禁止

Rulesetの削除禁止は `main` などの保護対象branchに適用します。Issue用の短命head branchは、リポジトリ設定の `Automatically delete head branches` をONにして、PR Merge後に原則自動削除します。

### 標準設定手順

1. リポジトリの `Settings` を開く
2. `Rules` → `Rulesets`
3. `New ruleset` → `New branch ruleset`
4. Ruleset名を `protect-main` にする
5. Enforcement statusを `Active`
6. Target branchesで `main` を対象にする
7. `Require a pull request before merging` をON
8. `Require status checks to pass before merging` をON
9. `Block force pushes` をON
10. `Restrict deletions` をON推奨

CIのrequired status checkは、workflowを一度実行しないと候補に出ない場合があります。その場合は最初のPRでActionsを動かした後、Ruleset設定へ戻ってCI checkを必須化します。

個人開発の初期段階ではRequired approvalsを必須にすると自分でMergeできなくなる場合があるため、まず0件で運用し、必要に応じて後から増やします。

詳細は `templates/github-security/ruleset-guide.md` を参照してください。

## 10. Dependabot

テンプレートはプロジェクトのpackage ecosystemに合わせて `.github/dependabot.yml` として配置します。

### 目的

依存パッケージの更新を継続的に確認します。

不要なecosystemは削除し、更新頻度や対象ディレクトリをプロジェクトに合わせます。

## 11. Secrets管理

### 基本原則

- APIキーをソースコードへ書かない
- `.env` をcommitしない
- Actionsで必要な秘密情報はGitHub Secretsを利用する
- ログへ秘密情報を出力しない
- 利用可能ならSecret scanning / push protectionを有効化する

Codexへの指示にも秘密情報をコードへ埋め込まないことを含めます。

## 12. Security Preflight / CodeQL

利用可能なリポジトリでは `.github/workflows/codeql.yml` として配置します。

### 目的

GitHub側でソースコードのセキュリティ問題を静的解析します。

CodeQLは通常のCIとは役割が異なります。

- CI: ビルド、lint、型、テストなどの動作検証
- CodeQL: セキュリティ上問題になり得るコードパターンの検出

利用可能な言語・GitHubプラン・リポジトリ設定を確認してから有効化します。

GitHub Security checkの有無にかかわらず、CIとSecurityの判定は分離します。利用可能なGitHub Security checkがないプロジェクトでは、`templates/security/security-preflight.sh` を `scripts/security-preflight.sh` としてコピーし、`chmod +x scripts/security-preflight.sh` を実行します。Security Preflightは既知のsecret patternと、対応するlockfileがある場合のnpm auditを検査し、全体の `SECURITY_STATUS` と依存チェックの `DEPENDENCY_STATUS` を機械可読に出力します。

Security Preflightと通常のレビュー用helperはBash 5以上が必要です。macOS標準`/bin/bash` 3.2で実行すると外部操作前に停止し、Preflightは`SECURITY_UNAVAILABLE`を出します。使用するBashの絶対パスを `BASH5` に設定して `"$BASH5" --version` で確認し、Preflightは `"$BASH5" scripts/security-preflight.sh .` として起動します。以下の待機例も `bash` の代わりに `"$BASH5"` を使います。待機helperはfallback Preflightを同じBashで起動します。手動JEV評価用helperは今回のBash 5前提に含めません。インストールやPATH変更は自動化しません。

- `SECURITY_PASSED`
- `SECURITY_FAILED`
- `SECURITY_NOT_APPLICABLE`（依存チェックの対象マニフェストがない場合。`DEPENDENCY_STATUS` と理由を監査記録へ残す）
- `SECURITY_UNAVAILABLE`（未対応マニフェスト、scanner、実行環境、結果が利用できない場合。人間判断が必要）

標準の待機スクリプトへfallbackのパスを渡す例:

```bash
"$BASH5" "$RUNTIME_DIR/scripts/wait-checks.sh" "$REPO" "$EXPECTED_SHA" 300 60 30 "./scripts/security-preflight.sh"
```

`SECURITY_FAILED` はMerge禁止、`SECURITY_UNAVAILABLE` は人間の明示判断なしに通過させません。CIの成功だけでSecurity成功とは判断せず、修正後は同じ新しいPR head SHAに対してCI・Security・レビューを再実行します。

## 12.1 AI Agent Security Boundary

新規プロジェクトでAIエージェントにToolを渡す場合は、docs/ai-agent-security-boundary.md を読み、Parent Issue、Child Issue、PRの該当欄へ適用結果を記録する。

- 情報をPUBLIC / INTERNAL / CONFIDENTIALに分類する。
- LLM環境をMANAGED / UNMANAGEDと判定し、CONFIDENTIAL情報の送信先を確認する。
- Intake / ReadとExposure / Writeを分け、Sensitive Read Capability × External Write Capabilityを高リスクとして判定する。
- Least PrivilegeのscopeとHuman Approval Boundaryを記録する。
- 外部コンテンツをtrusted instructionとして扱わず、適用対象外や例外の理由、残るリスク、代替制御、承認者を記録する。

テンプレート利用プロジェクトでは、適用可否を「対象外」とだけ書かず、対象Tool、データ分類、代替制御、承認者まで記録する。

## 12.2 Harness MinimalismとETCSLV台帳

AI開発テンプレートへ新しいハーネスを追加する前に、docs/ai-development-harness-inventory.md へ失敗モード、発火条件、Context、State、決定論的判定、コスト、重複、安全上の必須性、判定、削除・再評価条件を記録する。

既存ハーネスを削除または簡素化する場合は、対象の受入条件、代替制御、影響範囲、実測結果、対象SHAを記録する。
新規プロジェクトでは、台帳を常時Contextへ投入せず、追加または変更するハーネスに関係する項目を参照する。

モデル、Codex、Tool、CIの能力向上だけを理由にSecurity Boundary、Human Approval Boundary、Production保護を弱めない。
対象外やREMOVE_CANDIDATEの判定は、失敗モードと代替制御を確認した別IssueまたはPRで決定する。

## 13. 二重チェックの考え方

Nine標準AI開発フローでは、AIだけにもGitHubだけにも品質保証を依存しません。

### Codex側

- Issueを理解する
- Issue範囲を守る
- コードを実装する
- テストを書く
- ローカルで検証する
- 自己レビューする

### GitHub側

- Rulesetで危険な操作を禁止する
- Actions CIで独立して再テストする
- Dependabotで依存関係を監視する
- Secrets対策で秘密情報流出を防ぐ
- CodeQLでセキュリティ問題を検査する
- PRとして変更履歴を残す

### 人間側

- 仕様が正しいか判断する
- Issueの分割が適切か確認する
- AIが意図を取り違えていないか確認する
- 例外を認めるか判断する
- 最終Mergeを決定する

この三層構造を基本とします。

## 14. 標準的な開発の流れ

```text
相談・アイデア
    ↓
ChatGPTで計画書
    ↓
Framework Decision
    ├─ NEEDS_DECISION → Design Decision → 計画書更新 → 再Review
    ├─ DECIDED / NOT_APPLICABLE → 次工程
    ↓
UI Level Decision / PRODUCT前提整理
    ↓
Plan Review Gate（Grilling）
    ├─ NEEDS_DECISION → Design Decision → 計画書更新 → 再Review
    ├─ PASS → 親Issue
    └─ NOT_APPLICABLE → 省略理由を記録 → 親Issue
    ↓
子Issue案
    ↓
子Issue品質チェック
    ↓
GitHubへ子Issue登録
    ↓
Codex実装
    ↓
Codexローカルテスト
    ↓
Pull Request
    ↓
GitHub Actions CI
    ↓
CodeQL等のセキュリティチェック
    ↓
    Codex Code Review（レビュー専用）
    ↓
通常レーン / Safe Auto-Fix・Auto-Merge判定
    ↓
必要なら既存PRのhead branchで修正
    ↓
SHA更新確認 → ローカルテスト → CI → セキュリティチェック → 更新後headを再レビュー
    ↓
人間レビュー
    ↓
Merge
    ↓
Merge済みIssue用branchを自動削除
    ├─→ 最新mainから次のIssue用branchを作成 → 次の子Issue
    └─→ Production Deploy後の実利用シナリオ検証
         ↓
       計画時の成功条件との照合 → Accepted / Not Accepted / Conditional
         ↓
       発見事項の分類 → 修正Issue / 改善Issue / 次サイクル
```

Merge後の次Issue着手と、Deploy後の実利用検証・検収は独立した工程として扱う。依存関係のない次Issueは、検収完了を待たずに優先順位と依存関係に従って開始できる。検収で見つかった事項は、元PRの修正ループへ戻さず、必要な修正Issue / 改善Issueとして追跡する。

## 15. 新規リポジトリ初期化チェックリスト

新しい開発リポジトリを作成したら以下を確認します。

- [ ] 最小 `AGENTS.md` と同revisionの `docs/` 一式を配置（単体copyしない）
- [ ] `.agents/skills/` と参照原本 `templates/` を配置
- [ ] `docs/nine-standard-ai-development-flow.md` / `docs/code-review-contract.md` / `docs/test-design.md` / `docs/minimal-development-contract.md` と条件表の参照先を対象projectで開ける
- [ ] ai-development自身の検証行を除き、対象projectの `scripts/verify.sh` とCIを設定
- [ ] `docs/ai-agent-security-boundary.md` を配置
- [ ] `docs/ai-development-harness-inventory.md` を配置
- [ ] `docs/architecture/framework-decision.md` を配置
- [ ] `docs/plan-review-gate.md` を配置
- [ ] 親Issueテンプレートを配置
- [ ] 子Issueテンプレートを配置
- [ ] PRテンプレートを配置
- [ ] 技術スタックに合うActions CIを配置
- [ ] 初期Bootstrap時にテスト0件でも意図せずCI失敗しないことを確認
- [ ] 最初のテスト作成後はテスト失敗がCIを確実に失敗させることを確認
- [ ] Ruleset / Branch protectionを設定
- [ ] `Automatically delete head branches` をONにする
- [ ] `main` など保護対象branchの削除禁止とIssue用短命branchの自動削除を確認
- [ ] PR経由を必須化
- [ ] Actions実行後にCI status checkをrequiredに設定
- [ ] force push禁止を確認
- [ ] Dependabotを設定
- [ ] Secrets管理を確認
- [ ] 利用可能ならSecret scanning / push protectionを有効化
- [ ] `templates/security/security-preflight.sh` を `scripts/security-preflight.sh` として配置し、実行権限を付与
- [ ] 利用可能ならCodeQLを有効化
- [ ] 最初の親Issueを作成
- [ ] 子Issue品質チェックを実施

## 16. 普段の短縮指示

ChatGPTには例えば次のように依頼します。

方針が見えたあと、計画書化（詳細は [計画書の作り方](plan-authoring.md)）:

> 今までの方針で、Nineの計画書の作り方に沿って計画書を作成してください。会話で決まっていない欄は推測で埋めないでください。テンプレ上必要だが未決の項目は候補と推奨を出して確認してください。重要判断が残る場合はNEEDS_DECISIONとし、Issue化しないでください。

計画書のあと、Issue化:

> この計画をNine標準AI開発フローでIssue化して。Issue化前にPlan Review（Grilling）を実施し、PASSまたは理由付きNOT_APPLICABLEの場合だけ親Issue / 子Issueへ変換して。NEEDS_DECISIONの場合はIssue化を止め、Design Decisionの候補案と推奨案を提示して。

または

> このリポジトリをNine標準AI開発フローで初期化して。

Codexには基本的に次のように指示します。

> このリポジトリのGitHub Issueを確認し、AGENTS.mdに従って対象Issueを実装してください。

詳細な共通ルールはAGENTS.mdとIssue側に持たせることで、毎回長いプロンプトを書く必要を減らします。

## 17. このリポジトリを変更するとき

`ai-development` は今後の全プロジェクトの原本になるため、テンプレート変更時は次を確認します。

- 既存プロジェクトにも反映すべき変更か
- 新規プロジェクトだけに適用すべき変更か
- Codexの作業ルールに影響するか
- GitHub ActionsやSecurity設定に影響するか

大きな変更は、このリポジトリ自体でもIssue → PR → CI → Reviewの流れを使うことを推奨します。
