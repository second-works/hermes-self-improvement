# Deployment as Code 設計・Release / Production運用標準

最小Issueに非Deploy案件の空のRelease欄は設けない。Release / Productionが適用される場合はScope / BoundariesとVerificationから設計記録へ接続し、承認状態、Release Candidate SHA / artifact identity、RC静的監査・Staging確認、Full-System Security Auditの結果・理由を記録する。対象外判定の適格性と理由、identity不一致・FAIL時停止は省略しない。


## 1. 文書の目的

この文書は、GitHub上の実装完了と、本番投入可能な状態を分けて記録するための設計標準である。

実装PRは、コード・テスト・ドキュメントをGitHub上で完了させる。
本番投入可能とは、対象環境、データ、Secrets、Release判定、Deploy、確認、監視、Rollbackまでの運用経路を決定し、必要な検証を終えた状態を指す。
本番投入を今回行わない場合も、理由と次に判断するタイミングを記録する。

この文書は設計項目と安全条件の正本であり、標準フローは工程順、親Issueテンプレートはプロジェクトごとの決定記録を担当する。Deploy後の実利用検証と検収は [docs/acceptance-verification.md](acceptance-verification.md) を正本とし、Health Check / Smoke Testとは別に扱う。

## 2. 計画時に記録する設計項目

各項目は、採用案だけでなく「不要」と判断した場合の理由も記録する。

| 項目 | 記録する内容 |
| --- | --- |
| Production runtime | 本番の実行環境、OS / platform、公開範囲、想定規模 |
| Container | Docker / Docker Compose等が必要か。不要なら、再現性・運用・対象環境を踏まえた理由 |
| Persistent data | DB、ファイル、vector store、外部ストレージ、backup、logの保存先と、アプリ／コンテナ再作成後も残る仕組み |
| Deployment method | GitHub Actions、self-hosted runner、Cloudflare連携、VPS等の方式、実行主体、権限、承認方法 |
| Release Candidate / artifact identity | commit SHA、artifact ID、image digest等で候補を識別し、Stagingで検証した同一成果物をProductionへ昇格させる方法 |
| Full-System Security Audit | Release Candidate全体の監査対象、使用するSecurity結果、Stagingで確認する境界、結果、対象SHA / artifact identity、証拠参照 |
| Secrets / external services | Secrets、環境変数、外部API／サービス、GitHub Environmentの利用。値そのものは記録しない |
| Backup / migration | 永続データ変更前のbackup、DB / schema / vector migration、失敗時の停止・復旧手順 |
| Post-deploy check | Health Check、Smoke Test、必要なE2E、確認対象、合格条件、失敗時の扱い |
| Rollback | アプリ、設定、schema、vector index、データの互換性を含むRollback単位と実行条件 |

## 3. 標準Release / Production工程

標準順序は次のとおりとする。小規模・ローカルアプリなどでStagingを省略する場合は、Design Decisionに理由と代替確認方法を記録する。

```text
Merge
  ↓ Release Candidate
  ↓ RC静的監査
  ↓ Staging Deploy（必要な場合）
  ↓ Staging上のSecurity確認 / E2E / Smoke Test
  ↓ Full-System Security Audit判定
  ↓ Release判定
  ↓ Production Deploy
  ↓ Post-deploy Health Check
  ↓ Monitoring開始 / Rollback判断
  ↓ 実利用シナリオ検証
  ↓ 計画時の目的・成功条件との照合
  ↓ 検収判定
  ↓ Monitoring / Rollback
```

Mergeは実装の統合であり、Production Deployの自動実行を意味しない。
Production Deployは、CI成功、必要なPR単位Security Check、Full-System Security Auditの`PASS`または理由と適格性を確認した`NOT_APPLICABLE`、Release判定、必要なbackupとmigration確認を満たした後に実行する。
自動承認が適切でない場合は、GitHub Environmentsの`production`などで人間の承認を要求する。

## 4. Full-System Security Audit

**Full-System Security Audit**は、完成したRelease Candidate全体を対象に、統合後のコード、構成、依存関係、実行環境の境界をRelease判定前に確認するGateである。
各Issue / PRのSecurity Checkは個別差分を対象とし、このGateはそれらを置き換えない。

Release Candidateを作る案件では、原則として次の証拠を一つのGateへ集約する。

- RC静的監査：完成したコードと構成、認証、認可、権限境界、Secretsやcredentialの混入、Dependencyとsupply chainの既知リスク、CodeQL等の静的解析、API、DB、外部サービス間のtrust boundaryを確認する。
- Staging上の確認：実行環境で確認する必要がある認証、認可、公開範囲、権限、Secrets注入、外部接続、Production / Deployment設定を確認する。
- Identity照合：Security結果、監査証拠、Stagingへ配置した成果物が、Release Candidateのcommit SHA、artifact ID、image digest等と一致することを確認する。
- HIGH Risk確認：認証、認可、Secrets、Production、破壊的変更、Security Gate変更に対して計画した追加検証の完了を確認する。

Stagingを使わない案件では、Design Decisionに記録した代替環境または静的な代替確認を使用する。
RC静的監査だけで実行環境の確認が必要な項目をPASSにしてはならない。

確認深度は既存のRisk Tierを再利用する。

- `LOW`：既存Security結果とRelease Candidateのidentity照合を中心とする。ただし、LOWだけを理由に監査を省略しない。
- `MEDIUM`：適用可能な静的監査とStaging上の確認を実施する。
- `HIGH`：認証、認可、Secrets、Production、破壊的変更、Security Gate変更に対する追加検証と人間承認の状態を確認する。

Gate結果は次の3値で記録する。

- `PASS`：適用対象の証拠が揃い、すべて同じRelease Candidateを指している。Release判定へ進める。
- `FAIL`：未解決のSecurity問題がある。Releaseを停止し、修正Issue / PRへ戻す。
- `NOT_APPLICABLE`：Release工程を持たない成果物、またはセキュリティ影響が実質なく監査対象がない案件に限る。理由と適格性を確認した場合はRelease判定へ進める。

未実施、`FAIL`、証拠不足、Release Candidateとのidentity不一致では、Release判定とProduction Deployへ進めない。
監査後にコード、依存関係、Secrets設定、Deploy設定、Release Candidateのidentityが変わった場合は、古い`PASS`を再利用せず、変更後のRelease Candidateを再監査する。
`NOT_APPLICABLE`は、既存のPR単位Security Checkを省略する根拠にはならない。

## 5. 環境別の設計判断

### Cloudflare等のマネージド環境

Cloudflare Workers / Pages等でDockerが不要な場合は、Dockerを導入せず、GitHub Actionsまたは公式連携によるDeploy、Secrets、binding、migration、Health Checkを記録する。
Cloudflareを全プロジェクトの必須基盤にはしない。

### Home PC / VPSのWeb・API

self-hosted runnerからDocker / Docker Composeを使う案は候補の一つである。
採用する場合はrunnerの最小権限、実行場所、公開ポート、Secrets、volumeや外部DBの保存先、Deploy失敗時の停止・復旧を記録する。
self-hosted runner、Docker、Compose、Staging、MergeからProductionへの自動Deployを一律に強制しない。

### macOS固有アプリ

macOSアプリやmacOS専用のローカル運用では、Dockerを使わない選択を標準的な候補として扱う。
LaunchAgent、アプリバンドル、ローカルデータ、ログ、更新・Rollback方法など、対象環境に合った運用経路を記録する。

## 6. 永続データとRollback

アプリやコンテナの再作成と、永続データのライフサイクルを分離する。
永続データを持つ場合は、少なくとも保存先、backup頻度・保持期間、復元確認、migrationの前後互換性を記録する。

schema、DB、vector store、indexなどに後方互換性のない変更がある場合は、アプリだけをRollbackしてはならない。
次のいずれかを明示する。

- expand / migrate / contractの段階的移行
- データを含むRollback手順
- 非互換変更をProduction Deploy前に停止する判定

migration失敗時は、後続のDeployやHealth Checkを成功扱いにせず、backupからの復旧または安全な再実行手順へ進む。

## 7. Secretsと安全性の最低条件

- Secrets、APIキー、個人情報、実データをGit、Issue、PR、ログへ書かない
- SecretsはGitHub Secrets、GitHub Environment、対象基盤のSecret管理などから実行時に注入する
- self-hosted runnerは専用アカウント・最小権限・不要な公開ポートなしを基本とする
- Production Deploy前にCIと必要なPR単位Security Checkを成功させ、Full-System Security Auditを`PASS`または理由と適格性を確認した`NOT_APPLICABLE`にする
- backupが必要な変更では、backup成功をDeployの前提条件にする
- Health Check / Smoke Testの失敗時はRelease失敗として扱い、MonitoringとRollbackへ接続する

Health Check / Smoke Testの成功だけでは、利用者が当初の目的を達成したことを意味しない。Post-deploy後に実利用シナリオを実行し、検収判定と発見事項の分類を行う。具体的な状態、記録項目、`Accepted` / `Not Accepted` / `Conditional` の扱いは [docs/acceptance-verification.md](acceptance-verification.md) に従う。

MonitoringはPost-deploy Health Check後に開始し、障害時のRollback判断・実行を検収完了まで遅らせない。実利用検証はMonitoring / Rollbackを妨げない形で行う。

## 8. Design Decisionとエスカレーション

少なくとも次の判断を、プロジェクトの親Issueまたは設計記録に残す。

- Cloudflare、Home PC、VPS等の実行環境
- Docker / Composeの採否と理由
- self-hosted runnerの採否と権限
- Stagingの要否と省略理由
- 永続データの保存先とbackup
- 自動Deploy・人間承認の境界
- Rollbackの単位とデータ互換性

Issue本文や親IssueのDesign Decisionにない重要な設計判断が実装中に必要になった場合は、Codexは推測で実装せず停止する。
選択肢、推奨案、影響範囲、親Issue更新または追加Issueの要否を提示し、人間の決定後に記録を更新する。
Docker化、Kubernetes導入、全プロジェクトのCloudflare統一、大規模な既存アプリ移行は、このIssueの自動的な完了条件ではない。

## 9. 完了チェック

- [ ] GitHub上の実装完了と本番投入可能を別状態として記録した
- [ ] Production runtime、Container、Persistent dataを記録した
- [ ] Deployment method、Secrets / external servicesを記録した
- [ ] backup、migration、失敗時の復旧を記録した
- [ ] Staging要否、Smoke Test、Release判定を記録した
- [ ] Production Deploy後のHealth Check、Monitoring、Rollbackを記録した
- [ ] データの後方互換性または非互換時の停止・移行方法を確認した
- [ ] CI、Security Check、秘密情報の扱いを確認した
- [ ] Full-System Security Auditの結果、対象SHA / artifact identity、証拠参照を記録した
- [ ] 不要とした工程には理由がある

## AGENTSから移した詳細責務

Issue #177で常駐本文を短縮し、main `2afd63dcfc68e7e0596d70e1fcc350fcbcc71d6c` の詳細責務を本正本へ移した。以下の適用条件・例外は既存の具体手順と併せて適用する。矛盾や重要判断不足があれば推測せず停止する。

### Full-System Security Audit

Release Candidateを作る案件では、Release判定前に [Deployment / Release Design](deployment-release-design.md) のFull-System Security Auditを実施する。

- PR単位Security Checkは個別差分のGateとして維持し、Full-System Security Auditで置き換えない。
- RC静的監査と必要なStaging上の確認を、同じRelease CandidateのSHA / artifact identityへ結び付ける。
- 結果は `PASS / FAIL / NOT_APPLICABLE` で記録し、未実施、`FAIL`、証拠不足、identity不一致ではRelease判定とProduction Deployへ進まない。
- LOW Riskだけを理由に監査を省略しない。`NOT_APPLICABLE` は対象外理由を必要とする。
- 監査後にコード、依存関係、Secrets設定、Deploy設定、Release Candidateが変わった場合は、変更後の対象を再監査する。
