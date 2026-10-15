# Review Comment Auto-Triage PoC

Issue #116のPhase 1向け、Cloudflare Workers AI `typesafe/jev`を使ったDecision Layerの最小実装です。

このPoCはレビューコメントを判定・分類・記録するだけで、Jevにコードを書かせません。既定値は`shadow`であり、既存の人間レビュー判断を変更せず、`routed_to=record_only`を返します。

## 責務

- `src/decision-layer.mjs`: GitHubレビューコメントadapter、Jev入力、構造化結果、fallback、既存判断との差分比較。
- `src/index.mjs`: `/triage`へのbounded JSON入力とWorkers AI bindingのHTTP入口。
- `decision-result.schema.json`: 判定結果のJSON Schema。
- `wrangler.jsonc`: `AI` bindingとShadow Modeの最小設定例。
- `tests/review-comment-auto-triage/test.mjs`: API成功、Shadow Mode、既存判断との差分、低confidence、高リスク、API障害の契約テスト。

## AI Gateway

`typesafe/jev` はCloudflareのThird-party modelです。Workers AI bindingから呼び出す際はAI Gatewayを指定します。

このPoCは `AI_GATEWAY_ID` を参照し、未設定時は `default` Gatewayを使用します。

```json
"vars": {
  "TRIAGE_MODE": "shadow",
  "AI_GATEWAY_ID": "default"
}
```

Cloudflare Dashboardの **AI > AI Gateway** でGatewayを作成し、Third-party model利用に必要なUnified Billingとクレジット残高を設定してください。Gateway IDを変更する場合は `AI_GATEWAY_ID` を同じ値にします。

## HTTP認証

`/triage`は公開URLからWorkers AIを呼び出せないよう、Bearer tokenによる共有Secret認証を必須とします。Secret未設定時はfail-closedで503を返し、認証失敗時はAI推論を実行せず401を返します。

Secretはソースや`wrangler.jsonc`へ書かず、Wrangler Secretとして登録します。

```sh
wrangler secret put TRIAGE_SHARED_SECRET
```

呼び出し側は`Authorization: Bearer <登録したSecret>`を付けます。実運用でサービス間接続を使える場合は、公開HTTP入口を置かずService Binding等の内部経路に限定する構成を優先します。

## 入出力

入力の最低要件は`comment_id`と`body`です。`path`、`line`、`diff_hunk`、PRのrepository/number/head SHAは任意の相関情報として受け取ります。`existing_decision`を渡すと、Jev結果との差分を記録します。既存判断は許可されたフィールドと列挙値だけを受け付け、不正なbaselineは`invalid_existing_decision`としてfallbackします。

結果にはIssueの記録項目を含めます。

```json
{
  "comment_id": "review-1",
  "model": "typesafe/jev",
  "mode": "shadow",
  "decision": "action_required",
  "category": "bug",
  "priority": "p2",
  "auto_fixable": true,
  "high_risk": false,
  "confidence": 0.9,
  "suggested_route": "record_only",
  "routed_to": "record_only",
  "final_result": "shadow_observation",
  "fallback_reason": null,
  "latency_ms": 123,
  "usage": { "input_tokens": 426, "output_tokens": 73 },
  "neuron_usage": {
    "status": "unavailable",
    "reason": "AI.run response exposes token usage, not Neurons"
  },
  "comparison": {
    "baseline_present": true,
    "disagreement_count": 1,
    "disagreements": ["category"]
  }
}
```

Cloudflareの`AI.run`レスポンスで確認できる利用量は`input_tokens`/`output_tokens`です。Neuron値や単価はレスポンスから推測せず、`neuron_usage`を未提供として記録し、Cloudflare側の請求・使用量観測と別に検証します。

## Billing / Spend Limit fallback

JEV / AI Gatewayが利用できない場合も、PRレビュー工程全体は停止させません。Decision Layerは安全な理由コードだけを返し、`pr-review-fix` はCodex baselineへfallbackします。

- `credits_exhausted`: Unified Billingのプリペイドクレジット不足
- `spend_limit`: AI GatewayのSpend Limit到達
- `rate_limited`: 一般的な429 / rate limit
- `billing_unavailable`: Unified Billing / payment設定の異常
- `api_failure`: 上記に分類できないAI推論障害

上流の生エラーメッセージは監査ログへ保存せず、分類コードだけを残します。Spend LimitはCloudflare仕様上429で拒否されますが、429だけでSpend Limitと断定せず、エラーメッセージにSpend/Budget情報がある場合だけ `spend_limit` と分類し、それ以外は `rate_limited` とします。

## 安全境界

- Shadow ModeではCodex、GitHub、CI、Reviewerへ外部送信・書き込みを行いません。
- `security`、`p0`、`p1`、低confidence、判定不能、API障害はhuman fallbackです。
- `limited_automation`はPoC評価後の別Design Decisionで明示的に許可するまで使いません。閾値をこのPoCで正式決定しません。
- コメント本文とdiffは内部情報として扱い、ログには本文を出しません。`comment_id`と判定メタデータだけを相関用に保存します。
- レビューコメントとdiffはuntrusted dataとして扱い、本文中の指示を実行・追従しません。
- リクエスト本文は64 KiBまでに制限します。Secret/API tokenを入力やソースに含めません。
- Jevを外しても既存レビュー工程は継続します。fallbackはレビュー工程を停止させません。

## 実行例

Cloudflare Workerプロジェクトへコピーした上で、`AI` bindingと`TRIAGE_SHARED_SECRET`を設定して`wrangler dev`で実行します。実際のアカウント・Workers AI利用量・レイテンシは、認証済みの検証環境でサンプルレビューコメントを用いて測定します。このリポジトリの契約テストは外部APIを呼ばず、秘密情報を要求しません。

参照:

- [Cloudflare Jev model](https://developers.cloudflare.com/ai/models/typesafe/jev/)
- [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
- [TypeSafe AI JavaScript SDK documentation](https://docs.typesafe.ai/sdk/javascript)
