# Framework Decision v1

最小Issueでは適用確認を行い、Framework選定に影響しないCLI / library / 文書変更へ空のFramework欄やNOT_APPLICABLE欄を強制しない。適用時は結果・理由・正本参照をContextから引き継ぎ、未決定事項 / 停止範囲を明示する。既存の適用条件を例外で免除する場合の理由記録は維持する。


## 1. 目的

Framework Decisionは、AIや実装者が慣性で特定Frameworkを選ぶことを防ぎ、案件の要件、実行環境、配備条件、運用制約から採用技術を説明可能にするための設計記録である。

特定Frameworkを標準として固定しない。候補を比較し、採用理由と不採用理由を記録する。

## 2. 適用範囲

新規Web案件、またはRendering Strategy、Application Architecture、Runtime、Deployment / hostingの変更によってFramework選定を見直す案件へ適用する。

CLI、ライブラリ、文書のみの変更、既存Framework内で完結する局所変更など、Framework選定が実装結果へ影響しない案件は `NOT_APPLICABLE` とできる。その場合も対象外理由を記録する。

## 3. 選定順序

判断は次の順序で行う。Framework名から要件を逆算してはならない。

```text
Requirements
  ↓
Rendering Strategy
  ↓
Application Architecture
  ↓
Framework
```

1. **Requirements**: 利用者、公開範囲、SEO、対話性、データ、認証、性能、運用、配備の要件を明確にする。
2. **Rendering Strategy**: SSG、SSR、SPA、または必要な組合せを要件から決める。
3. **Application Architecture**: Static / Content、SPA、SPA + API、Full Stack / SSRなど、UIとAPIの責務境界を決める。
4. **Framework**: 確定した前提に合う候補を比較し、採用または停止を判定する。

## 4. 判定

判定結果は次のいずれかとする。

| 判定 | 意味 | 次のアクション |
| --- | --- | --- |
| `NOT_APPLICABLE` | Framework選定が案件の実装結果へ影響しない | 対象外理由を記録して後続工程へ進む |
| `DECIDED` | 必要な前提と比較結果が揃い、採用Frameworkを説明できる | 決定内容を後続のUI設計、Plan Review、Issueへ引き継ぐ |
| `NEEDS_DECISION` | 重要な前提が未決定、または複数候補のtrade-offを人間が判断する必要がある | Framework依存の計画・設計・実装を停止し、既存のDesign Decisionへ送る |

`NEEDS_DECISION` をAIが暗黙に `DECIDED` へ変更してはならない。Design Decisionでは未決定事項、候補、trade-off、推奨案、決定者、決定日、参照Issueを記録し、確定後にFramework Decisionを更新する。

## 5. 最低評価項目

案件ごとに、少なくとも次を評価する。要件上の対象外項目は、空欄にせず理由付きで対象外とする。

| 観点 | 確認内容 |
| --- | --- |
| SEO / 公開ページ | 検索流入、metadata、crawler向け出力、公開ページの初期表示が必要か |
| Rendering Strategy | SSR、SSG、SPAのどれが必要か。混在する場合は境界がどこか |
| 公開 / 認証後中心 | 公開コンテンツ中心か、ログイン後の対話型アプリ中心か |
| コンテンツ / アプリケーション | 静的コンテンツ中心か、状態を持つアプリケーション中心か |
| Server機能 | server-side rendering、server-side data access、Server Components等が本当に必要か |
| API分離 | UIとAPIを同居させるか、独立serviceとして分離するか |
| Runtime | Node.js、Edge、browser、その他runtimeの制約と利用できないAPIは何か |
| Deployment / hosting | Cloudflare、container、managed hosting等の対象環境と制約は何か |
| self-host portability | self-hostの必要性、移行可能性、vendor固有機能への依存を許容できるか |
| 運用複雑性 | build、deploy、監視、障害対応、更新、必要skill、運用人数に見合うか |

## 6. 候補比較と決定記録

候補ごとに、少なくとも次を記録する。

- 候補名と想定versionまたは制約
- Requirementsへの適合
- Rendering Strategyへの適合
- Application Architectureへの適合
- RuntimeとDeployment / hostingへの適合
- self-host portabilityとvendor lock-in
- 運用複雑性
- 主な利点、欠点、リスク
- 採用または不採用の理由

候補数を機械的に固定しない。比較可能な候補が一つしかない場合も、他候補を検討しない理由を記録する。知名度、AIの得意分野、初期生成速度だけを採用理由にしない。

## 7. `NEEDS_DECISION` の停止条件

次のいずれかがFramework選定へ重大な差を生む場合は `NEEDS_DECISION` とする。

- SEO、公開範囲、認証境界、Rendering Strategyが未決定
- APIの同居 / 分離、Runtime、Deployment / hostingの制約が未決定
- self-host portabilityまたはvendor lock-inの許容範囲が未決定
- 複数候補が残り、コスト、移行性、運用複雑性などのtrade-offに人間判断が必要
- 候補の成立条件を検証できず、推測しなければ選べない

停止中も、確定済みの要件と比較結果は保存する。Framework依存でない調査まで禁止するものではないが、未決定のFrameworkを前提にUI設計、Issue化、実装を進めない。

## 8. 既存Gateとの責務境界

- **Plan Review Gate**: Framework Decisionの内容を入力として、計画全体の実装可能性を判定する。Framework候補の比較記録をPlan Reviewへ重複保存しない。
- **Design Decision / Escalation**: `NEEDS_DECISION` の重要判断を人間へ戻し、確定する。Framework Decisionは独自の承認台帳を作らない。
- **UI Level / Product Design**: Framework Decisionはrenderingとarchitectureを決める。UI Level、画面構造、navigation、visual direction、component、accessibilityはUI標準と案件の `docs/design.md` が扱う。
- **Deployment / Release**: 対象runtimeとhostingの制約を選定入力として記録するが、deployment手順、promotion、rollback、production承認を再設計しない。
- **Security / Acceptance**: 認証境界やserver-side data accessを比較条件に含めるが、Security Gate、実利用検証、Product Acceptanceを置き換えない。

関連する正本は [Plan Review Gate](../plan-review-gate.md)、[Deployment / Release Design](../deployment-release-design.md)、[Nine PRODUCT UI Standard v1](../product-ui-standard.md) を参照する。案件用の記録には [`templates/app/docs/framework-decision.md`](../../templates/app/docs/framework-decision.md) を使用する。

## 9. 完了チェック

### 全判定共通

- [ ] 適用判定と理由がある
- [ ] 結果が `NOT_APPLICABLE / DECIDED / NEEDS_DECISION` のいずれかである
- [ ] UI設計、Deployment、Security、Acceptanceの既存責務を置き換えていない

### `NOT_APPLICABLE` の場合

- [ ] Framework選定が実装結果へ影響しない理由がある

### `DECIDED` の場合

- [ ] RequirementsがFramework名より先に記録されている
- [ ] Rendering Strategyが決まっている
- [ ] Application ArchitectureとAPI境界が決まっている
- [ ] 最低評価項目が評価済み、または理由付き対象外である
- [ ] 候補の採用理由と不採用理由がある

### `NEEDS_DECISION` の場合

- [ ] 未決定事項と候補のtrade-offが記録されている
- [ ] Framework依存作業の停止範囲が記録されている
- [ ] 既存Design Decisionへの参照先が記録されている

## AGENTSから移した詳細責務

Issue #177で常駐本文を短縮し、main `2afd63dcfc68e7e0596d70e1fcc350fcbcc71d6c` の詳細責務を本正本へ移した。以下の適用条件・例外は既存の具体手順と併せて適用する。矛盾や重要判断不足があれば推測せず停止する。

### Framework Decision

新規Web/UI案件、またはRendering Strategy、Application Architecture、Runtime、Deployment / hostingの変更を伴う案件では、[Framework Decision v1](framework-decision.md) をUI Level DecisionとPlan Review Gateより前に確認する。

- 判断順序は `Requirements → Rendering Strategy → Application Architecture → Framework` とし、特定FrameworkをAIが暗黙に採用しない。
- 結果は `DECIDED / NOT_APPLICABLE / NEEDS_DECISION` で記録する。`NOT_APPLICABLE` は対象外理由を必須とする。
- `NEEDS_DECISION` の間はFramework依存のUI設計、Issue化、実装開始を停止し、既存のDesign Decisionへ接続する。
- Framework DecisionはUI Level、Plan Review、Deployment / Release、Security、Acceptanceの責務を置き換えない。Plan Reviewへは結果と正本文書の参照を引き継ぎ、候補比較を重複保存しない。
- CLI、library、文書のみの変更など、Framework選定が実装結果へ影響しない案件は、理由付きで `NOT_APPLICABLE` とできる。
