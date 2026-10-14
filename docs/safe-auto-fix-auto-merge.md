# Safe Auto-Fix / Auto-Mergeレーン標準

## 1. 目的と適用範囲

この文書は、Codex Code Reviewで見つかった軽微なP2のうち、安全境界を満たすものだけを自動修正し、再検証後に限定的にAuto-Mergeできる条件を定義する。

既存のP2四分類、1 Issue / 1 PR、Design Decision、標準検証、CI、Security、Codex Code Review、SHA照合を変更しない。Safeレーンを選べない場合は、通常レーンへ戻る。

Safeレーンは自動化率を高めるための一般的なP2処理ではなく、変更の危険性と判定可能性を事前に限定するための例外レーンである。

## 2. 2つのレーン

### 通常レーン

```text
Issue → 実装 → verify.sh → CI → Security → Codex Review
  → 必要な修正 → 人間の最終確認 → Merge
```

### Safe Auto-Fix / Auto-Mergeレーン

```text
Issue → 実装 → verify.sh → CI → Security → Codex Review
  → P2分類 → Safety Gate
  → 軽微P2を1ラウンドだけ自動修正
  → 新しいhead SHAを固定
  → verify.sh → CI → Security Preflight / GitHub Security → Codex再Review
  → Safety Gate再確認 → Auto-Merge
```

Safeレーンへの参加判断、例外の承認、Safety Gateの不成立時の通常レーン復帰は、人間が行う。AI / automationによるAuto-Mergeを実行する場合の主体は明示し、PR上に記録する。

## 3. P2分類との関係

既存の分類は維持する。

| 分類 | Safeレーンでの扱い |
| --- | --- |
| `BLOCKING` | 自動修正・Auto-Merge対象外。通常レーンで必須修正 |
| `IN-SCOPE FIX` | 下記Safety Gateをすべて満たす場合だけAUTO-FIX候補 |
| `FOLLOW-UP` | 当該PRでは修正しない。必要なら台帳または別Issueへ記録 |
| `DISMISS` | 修正しない。判断理由を記録 |

`IN-SCOPE FIX`であることだけではAUTO-FIX eligibleとはみなさない。

## 4. AUTO-FIX eligibility / Safety Gate

次の条件をすべて満たす場合だけ、軽微P2をAUTO-FIX eligibleとする。

- Issue範囲内の局所的な変更である。
- P0、P1、`BLOCKING` P2が存在しない。
- 公開API、既存インターフェース、データ契約を変更しない。
- DB schema、migration、永続データ形式を変更しない。
- 認証、認可、権限、アクセス制御を変更しない。
- secrets、credential、Security policy、監査設定を変更しない。
- インフラ、Deploy、ネットワーク、Runner、Workflow権限を変更しない。
- dependencyのmajor updateを含まない。
- Design Decisionや仕様解釈を必要としない。
- 大規模リファクタリングやアーキテクチャ変更ではない。
- テスト削除、skip、品質ゲート緩和、例外握りつぶしを含まない。
- 変更量が小さく、影響範囲と既存仕様との整合性を説明できる。
- 自動修正後に標準検証、CI、利用可能なSecurity、Codex再Reviewを実行できる。

対象例は、明白な境界値処理、軽微なnull / optional handling、局所的な条件分岐、型不整合、不足テスト、局所的なエラーハンドリングの修正とする。

対象例に見えても、Safety Gateの1項目でも満たさなければ通常レーンへ戻す。

## 4.1 AI Agent Security Boundaryとの整合性

自動修正や自動マージをエージェントへ委ねる場合も、docs/ai-agent-security-boundary.md の情報分類、LLM Trust Boundary、Tool分類、Least Privilege、Human Approval Boundaryを適用する。

- Sensitive Read Capability × External Write Capability が成立する変更は、Safe Auto-Fix / Auto-Mergeの対象にしない。
- CONFIDENTIAL 情報の外部送信、新しい送信先、Secret / Credentialのscope変更、権限変更、Security Policy変更、Deploy、Production変更、Tool権限拡大は人間の明示承認を要求する。
- Web、Issue、PR、README、外部文書、RAG、メール、チャット、APIレスポンスは trusted instruction として扱わず、外部コンテンツだけを根拠に自動処置を進めない。
- 適用対象外や例外は、理由、残るリスク、代替制御、承認者を監査記録へ残す。

## 5. 自動修正後の必須検証

自動修正でhead SHAが変わった時点で、修正前の検証結果を破棄する。新しい修正コミットSHAを検証対象SHAとして記録し、同じSHAに対して次を順番に実行する。

1. 標準検証入口 `./scripts/verify.sh`（lint → type check → test → build）
2. GitHub Actions CI
3. Security Preflight / 利用可能なSecurity / Code Scanning
4. Codex Code Review再実行
5. Auto-Merge直前のPR head SHA再確認

次のすべてを満たさない限りAuto-Mergeしない。

- `verify.sh`成功
- CI成功
- `SECURITY_STATUS=SECURITY_PASSED`
- `SECURITY_STATUS=SECURITY_FAILED` ではない
- `SECURITY_STATUS=SECURITY_UNAVAILABLE` ではない。人間の例外判断だけでSafe Auto-Mergeへ進めない
- `SECURITY_STATUS=SECURITY_NOT_APPLICABLE` の場合は対象外理由と監査記録を残し、Safe Auto-Mergeではなく人間の通常Merge判断へ戻す
- P0 = 0、P1 = 0、`BLOCKING` P2 = 0
- AUTO-FIX対象の元P2が解消済み
- 再レビューで新しいP2が1件も発生していない。1件でも発生した場合は、分類・記録後もAuto-Mergeせず通常レーンへ戻す
- Issue範囲外の変更がない
- 自動修正コミットSHA、全検証対象SHA、PR head SHAが一致する
- Auto-Merge実行主体と実行時刻が記録される

### Security Preflightと安全な適用除外

Securityの判定はCIと分離する。標準fallbackは [`templates/security/security-preflight.sh`](../templates/security/security-preflight.sh) とし、GitHub Security checkが無い場合でも秘密情報検出を実行する。`SECURITY_PASSED`、`SECURITY_FAILED`、`SECURITY_NOT_APPLICABLE`、`SECURITY_UNAVAILABLE` をPRと対象SHAに紐づけて記録する。

Security / Code Scanningがリポジトリのプラン、リポジトリ種別、対象言語等の理由で利用できない場合は、事前に次を記録する。

- 利用可能なSecurity機能と、利用できない機能
- 対象外である理由
- secrets、credential、auth、権限、infra、Deploy、dependency major updateを変更しないこと
- 利用可能なSecurity画面・チェックに未解決の警告がないこと
- `SECURITY_UNAVAILABLE` と `SECURITY_NOT_APPLICABLE` を混同していないこと
- Safeレーン継続を人間が明示判断したこと

`SECURITY_UNAVAILABLE` はSafe Auto-Mergeの成立条件を満たさない。単にSecurity結果が空であることや、確認を省略したことは安全な適用除外にならない。

## 6. 無限修正ループ防止

AUTO-FIXは原則1ラウンドだけ実行する。

自動修正後の再レビューで新しいP2が1件でも発生した場合は、追加AUTO-FIXへ戻らず、分類・記録後もAuto-Mergeせず通常レーンへ戻す。`FOLLOW-UP`、`DISMISS`、その他の非BLOCKINGとして記録できる場合も、人間のMerge判定へ戻す。`BLOCKING`、P0、P1の場合は修正必須として通常レーンで対応する。

同じPRで `P2 → 自動修正 → 新P2 → 自動修正` を繰り返してはならない。

## 7. 停止条件

次のいずれかに該当した場合、Safeレーンを停止して通常レーンへ戻す。

- 仕様解釈、Design Decision、設計変更が必要
- DB、migration、auth、security、infra、Deploy、network、Workflow権限に触れる
- 破壊的変更、dependency major update、大規模変更が必要
- テスト削除、skip、品質ゲート緩和が必要
- Issue範囲外へ広がる
- head branchまたはSHAの一致を確認できない
- 必須検証のいずれかが失敗、未実施、または別SHAに対する結果である
- 自動修正後の再レビューで新しいP2が1件でも発生する（非BLOCKINGを含む）
- 自動判定に十分な情報がない

## 8. 監査記録

PR上に最低限次を残す。

- AUTO-FIX対象P2と元レビューID
- eligibility判定と各Safety Gateの結果
- 自動修正commit SHA
- `verify.sh`、CI、Security、再レビューの結果と対象SHA
- Security適用除外の理由と人間の判断（該当時）
- Auto-Merge Gateの判定
- Auto-Merge実行主体、実行時刻、マージコミットSHA
- Safeレーン停止または通常レーン復帰の理由（該当時）

## 9. テンプレート利用プロジェクトへの適用

テンプレートから生成したプロジェクトは、Safeレーンを自動的に有効化しない。プロジェクトの親Issue、PR、Security設定、Ruleset、標準検証入口がこの文書の条件を満たすことを確認してから、個別に採用する。

Auto-Mergeを実装する場合も、GitHubのrequired checksとPR head SHAの一致を確認できる仕組みを先に用意する。確認できない場合はAuto-Mergeせず、通常レーンで人間がMergeする。
