# Adaptive Development Flow

## 目的と正本

Risk Tierは、変更の影響に応じて説明量と追加検証を調整するために使用する。
フロー全体の正本は [Nine標準AI開発フロー](nine-standard-ai-development-flow.md)、Tier判定の正本はこの文書とする。
関連Issue: #62 / #63。導入日: 2026-09-07。

## 判定順

Issue化前に変更内容を確認し、実装開始時とPR提出前に実際の差分で再判定する。
修正で範囲・依存・権限・実行動作が変わった場合も再判定し、IssueとPRの今回値を更新する。

1. 認証・認可・Secrets・権限・Production・破壊的変更・Gate自体の変更、または安全影響不明を含む場合は `HIGH`。
2. 実行動作・API・依存関係・workflow・安全ルールを変えない文言または表示だけの変更であることを確認できた場合だけ `LOW`。
3. それ以外の通常の機能追加・不具合修正は `MEDIUM`。

既定値は `MEDIUM`。未入力はMEDIUMとして記録したうえで上の判定順を適用し、安全影響不明をMEDIUMのまま進めない。
有効値は `LOW / MEDIUM / HIGH` の3値のみ。未知値は判定済みとして使わず、3値へ訂正してから進む。
複数の変更が混在するときは最大Tierを採用する（`HIGH > MEDIUM > LOW`）。
ファイル拡張子、変更行数、自己申告したLOWだけでは確定しない。安全規則の変更はMarkdownだけでもHIGHとなる。

## Tierごとの記録と追加検証

| Tier | 今回記録する内容 | 影響に応じた追加検証 |
| --- | --- | --- |
| LOW | 目的・範囲・LOWの根拠・テスト証拠を短く記録。該当しない欄は理由を一文でまとめ、正本を参照する | 文言の意味、表示崩れ、リンクなど変更対象を確認。Plan Reviewは既存基準で理由付きNOT_APPLICABLEが成立する場合だけ使用 |
| MEDIUM | 通常の影響範囲・受入条件・6観点のテスト条件を記録 | 変更に関係する正常系、境界値、異常系、回帰を選び、対象外は理由を記録 |
| HIGH | MEDIUMの内容に加え、影響する安全境界・失敗時の復旧方針・必要な人間承認とその状態を記録 | 権限拒否、データ保護、失敗時停止、復旧など今回の境界を検証。対象外は理由を記録し、未承認の重要判断は停止 |

記入欄の説明を毎回コピーする必要はない。同じ今回値は記録先へリンクして参照できるが、必須情報自体は欠落させない。
HIGHであることだけでは未承認を意味しない。既に承認された設計範囲の作業は進め、新しい重要判断だけをDesign Decision Escalationへ戻す。

## 全Tierで維持するGate

次の既存契約はTierに関係なく維持する。Tierは免除や承認の根拠にはならない。

- 標準検証: `./scripts/verify.sh` の実行契約を維持する。実行不能・失敗を成功扱いしない。
- CI: 現headのGitHub Actions結果を確認する。
- Security: CIと区別して確認する。`SECURITY_UNAVAILABLE` は人間の明示判断なしに通過させない。
- Codex Review: 現headに対するレビューを確認し、P0 / P1 / BLOCKING P2を未解決のまま進めない。
- Human Merge: 通常レーンの最終Mergeは人間が判断する。
- Acceptance: 適用対象のProduct Acceptanceを維持する。未実施理由と実施時期を引き継ぎ、対象artifactの不一致を無視しない。

LOWはCI・Security・Review・Acceptanceのskip、Production Deploy、権限拡大、自動Mergeを許可しない。
既存の [Safe Auto-Fix / Auto-Merge](safe-auto-fix-auto-merge.md) は独立したSafety Gateで判定し、LOWから適用資格を推定しない。
Plan Reviewの適用除外、Securityの例外、Acceptanceの対象外は、それぞれの正本の条件と理由・承認を必要とし、Tierから自動設定しない。

安全影響が不明ならHIGHへ上げて影響を確認する。未承認の重要設計、安全境界の変更、Issue範囲外の変更が必要なら既存のDesign Decision Escalationで停止する。
影響が確認できた後のTier訂正は、実差分と理由をIssue/PRへ記録する。Gate未実施や失敗を解消するための降格は禁止する。

## 記入例とPlan vs Reality

以下はテンプレートへ今回値を当てはめた文書上の試行であり、本番利用の成果やGitHub Gate成功の証拠ではない。

| 試行 | 計画した変更 | 判定結果と記入例 | 確認結果・残る検証 |
| --- | --- | --- | --- |
| 文言のみ | READMEの誤字1箇所。命令・安全条件の意味を変えない | LOW。理由: 実行動作/API/依存/workflow/安全ルールに影響なし。目的・範囲・訂正箇所・リンク確認の証拠を一段落で記録 | LOWの定義に適合。不要な説明の再転記を省ける。CI/Security/Reviewの証拠は別途必要 |
| 通常機能 | 既存の非機密データ一覧に内部ソートを追加 | MEDIUM。理由: 表示動作が変わる。順序・空一覧・同値・既存表示の回帰をテスト | 表示変更でも動作変更のためLOWにしない。実装の機能テストは別途必要 |
| 高リスク | 認可条件の変更 | HIGH。理由: 権限境界に影響。許可/拒否、既存権限の回帰、復旧方針、設計承認を記録 | 文言修正より追加検証が必要。未承認なら停止。実システムの検証は別途必要 |
| 混在 | 誤字修正と認可条件の変更 | HIGH。最大Tierを採用 | LOW項目の併記でHIGHを隠せない |
| 不明 | 影響先を確認できない設定変更 | HIGH。影響確認と必要な設計判断を記録 | MEDIUM既定値を安全影響不明の代用にしない |
| 今回 #63 | Risk TierとGate適用規則の文書追加 | HIGH。理由: Gate自体の変更。親 #62 で設計承認済み。誤分類と必須Gate維持を契約検証。復旧はこのPR差分のrevertを人間判断で行う | 文書のみでもHIGH。安全workflowの変更なし。実行結果はPRへ記録 |

全体テンプレートの重複削減は #66、実データ収集は #64、HTMLでの状態表示は #67 で検証する。
今回の文書試行だけで親Issueの実利用検収や全体完了を宣言しない。

## AGENTSから移した詳細責務

Issue #177で常駐本文を短縮し、main `2afd63dcfc68e7e0596d70e1fcc350fcbcc71d6c` の詳細責務を本正本へ移した。以下の適用条件・例外は既存の具体手順と併せて適用する。矛盾や重要判断不足があれば推測せず停止する。

### Adaptive Development Flow / Risk Tier

Issue化前、実装開始時、PR提出前および差分の影響変更時は [docs/adaptive-development-flow.md](adaptive-development-flow.md) に従ってRisk Tierを判定し、Issue / PRへTierと理由を記録する。

- 有効値は `LOW / MEDIUM / HIGH`、既定値はMEDIUM。混在時は最大Tierを使用する。
- 安全影響不明、認証・認可・Secrets・権限・Production・破壊的変更・Gate自体の変更はHIGHとする。
- LOWは実行動作・API・依存関係・workflow・安全ルールを変えない文言や表示だけの変更に限定する。
- Tierで説明量と追加検証を調整し、必須情報は維持する。標準検証・CI・Security・Codex Review・Human Merge判断・適用対象AcceptanceをTierによって省略しない。
- LOWはAuto-Mergeの許可ではない。既存Safety GateとHuman Approval Boundaryを維持する。
- 承認済み設計内の作業は継続し、未承認の重要判断だけを既存Design Decision Escalationで停止する。
