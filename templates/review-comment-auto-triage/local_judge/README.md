# Local Judge Shadow Provider（Issue #153）

既存JEVを維持し、Gemma 4による判定を非権威的な比較Providerとして追加する。
判断・修正・resolve・Mergeの正本はCodex baselineのままとする。
2026-09-25時点の実装対象モデルは `gemma-4-e4b`。モデル追加や自動化の解禁は対象外。

## 今回の設計

Risk Tierは **HIGH**（Actions、Secrets、ローカルLLMへの外部経路）。依存Issue #116 / #123 / #131 は実装開始時にcompletedを確認。
UI LevelはNONE。Framework DecisionはDECIDED：限定JSON APIだけが必要で描画は不要、UIから独立したloopbackサービスとし、既存Python実行環境の標準ライブラリを使う。追加Web frameworkは単一endpointに不要、汎用LLM proxyは要求する安全境界に反するため不採用。Plan ReviewはNOT_APPLICABLE（新しい計画のIssue化ではなく、既存Issue #153の実装）。

変更範囲は `local_judge/`、Skillの比較入口と説明、専用Workflow、契約テストとCI、ハーネス台帳。既存JEV Worker / API / 単独Workflow、MergeやレビューGate、既存サービス設定は変更しない。

`JevProvider / LocalJudgeProvider / BaselineProvider.observe(review)` は同じobservationを返す。`decision` は `needs_action / category / priority / auto_fixable / high_risk` の5項目、失敗時はnull。`model` とconfidenceはProvider固有。JEVは既存の検証済み監査結果をadapterで取り込み、wire契約を変更しない。

全observationで `mode=shadow`、`authoritative=false`、`effective_disposition_source=baseline`。baseline行も監査上の観測であり、Skillの最終Dispositionを更新する命令ではない。JEV confidenceは `confidence`、Local Judgeの全候補確率は `probabilities` に分離する。P0/P1/security/high-risk、低確率、障害時のfallbackは観測用メタデータで、どの結果にも実行権限を与えない。

## 1-tokenと確率

`server.py` は毎回モデルaliasを確認し、A〜Fがそれぞれ単一tokenになることを `/tokenize` で検証する。共有するレビューprefixと問いを既存Gemma chat templateへ通し、各項目を `/completion` の `n_predict=1` で実行する。5回の生成を直列化し、`cache_prompt=true`、各項目の時間と `tokens_cached` を記録する。

実機のllama.cppではgrammarだけでは `top_probs` が候補外tokenを含んだため、候補に同じ `logit_bias=100` を加え、温度1・候補を切り捨てるsamplerなしで分布を得る。候補間のlogit差は維持される。生成tokenが候補内・1個で、全候補が揃い、確率が有限の0〜1で和が約1のときだけ、分布のargmaxを分類値にする。候補外確率や欠落は推測で補完せずfallbackする。

これは **固定候補内の確率** であり、正答確率でもJEV confidenceでもない。`LOCAL_JUDGE_MIN_CONFIDENCE`（既定0.8）は選ばれた候補確率の観測閾値だけに使用する。`/completion` の本文・prompt echo・上流エラー・推論文は保存しない。返却フィールドも制限する。仕様の参照元は [llama.cpp server API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)。

## 接続と承認境界

```text
GitHub Actions（保護Environment・default branchの信頼済みコード）
  → HTTPS / Cloudflare Access Service Auth
  → 専用Tunnel（/triageだけ、その他404）
  → 127.0.0.1:8093（Bearer認証）
  → 127.0.0.1:8081（既存llama-server）
```

`cloudflared.example.yml` は未適用の雛形。raw llama-serverの `/completion`、`/tokenize` 等をTunnelへ登録しない。外部入力は `comment_id / body / diff_hunk` だけで、モデル、endpoint、prompt template、生成パラメータ、toolを指定できない。本文中のspecial tokenはJSONのUnicode escapeに変換する。

- APIはloopback固定、直列処理、待ち行列2。認証失敗401、不正入力400、サイズ超過413、上流障害503。HTTPアクセスログは無効。上流llama-serverもprompt/bodyをログ保存する設定にしない。
- body/diffは各6,000 UTF-8 bytes、HTTP requestは16 KiB、responseは32 KiB、入力読み取り5秒、上流呼出し全体25秒、Actions client30秒。外部endpointは `https://LOCAL_JUDGE_HOST/triage` だけ。redirectと環境proxyを無効化する。
- 新しい保護Environment `local-judge-shadow` はdefault branch限定とし、required reviewerを設定する。workflow_dispatch入力をshellへ直接展開せず、PR head SHAを送信前・送信後に照合する。checkoutはPRコードではなくdefault branch、credentials永続化なし、権限はcontents/readとpull-requests/readだけ。
- Secrets: `LOCAL_JUDGE_TOKEN`、`LOCAL_JUDGE_ACCESS_CLIENT_ID`、`LOCAL_JUDGE_ACCESS_CLIENT_SECRET`。JEV並走時は既存の `JEV_TRIAGE_TOKEN` も同Environmentへ設定する。Variable: `LOCAL_JUDGE_URL`、`LOCAL_JUDGE_HOST`、任意の `LOCAL_JUDGE_MIN_CONFIDENCE`、`JEV_TRIAGE_URL`。
- Macのservice managerだけが `LOCAL_JUDGE_API_TOKEN` を設定し、Actionsの `LOCAL_JUDGE_TOKEN` と一致させる。値はCodex prompt、ファイル、PR、artifact、コマンド履歴へ記載しない。API単体はAccess JWTを検証しないため、AccessのService Auth policyとBearerの両方を配備時に実通信で検証する。

**まだ適用しない操作**：専用hostnameの決定、Access/Tunnel/Environmentの登録、Secretの登録、常駐化、実レビューの新経路への送信。これらは人間が接続先と権限を確認してから行う。コード準備・合成データによるloopback検証とは区別する。配備後に未認証・誤token・認可済み呼出し、非/triage拒否、PR SHA不一致、本文非保存を確認するまで外部経路のAcceptanceはNOT_VERIFIED。

起動コマンド（Secretはservice managerの環境から取得）:

```bash
cd templates/review-comment-auto-triage
python3 -m local_judge.server
```

`LOCAL_JUDGE_BACKEND` は任意のloopback port指定だけに使える（既定 `http://127.0.0.1:8081`）。別モデルや外部ホストは受け付けない。

## 比較と評価

Actionsの `decision-shadow.yml` は100件までの現headのCodexコメントだけを観測する。未設定Providerはfallbackし、レビュー工程は継続する。JEV実行は全体120秒で打ち切り、Local Judgeがその後に動作する。生の入力は一時ディレクトリだけで扱い、最後に削除する。artifactは同一repository / PR / head SHA / comment_idに紐づく3行のobservationだけ（保持7日）。

Codexによる確定ラベルは、実際に判断した後、本文を含めず次の形式で用意する。値をJEV/Local Judgeから転記してbaselineと呼ばない。

```json
{
  "repository": "github.com/owner/repo",
  "pr_number": 1,
  "head_sha": "0000000000000000000000000000000000000000",
  "decisions": {
    "153": {"needs_action": true, "category": "bug", "priority": "p2", "auto_fixable": true, "high_risk": false}
  }
}
```

既存のartifactとラベルを結合して集計する（再推論なし）:

```bash
PYTHONPATH=templates/review-comment-auto-triage python3 -m local_judge.evaluate \
  /tmp/shadow-audit.jsonl /tmp/codex-baseline.json /tmp/comparison-summary.json
```

未ラベルは比較分母に入れない。5項目の一致率、JEVとの一致率、False Positive / False Negative件数、BLOCKING/security見逃し件数、fallback率、平均/P95レイテンシ、項目別時間、キャッシュtoken、確率帯別実正答率を出す。JEVとLocal Judgeのscoreは別表として集計する。

合成fixtureの実機確認:

```bash
PYTHONPATH=templates/review-comment-auto-triage python3 -m local_judge.benchmark \
  tests/local-judge/fixtures.json /tmp/local-judge-benchmark.json --limit 12 --llama-pid <PID>
```

キャッシュ無効→有効の順に各1回測定する。12件の合成ラベルであり、本番50〜100件のCodex baseline比較を代替しない。CPU/RSSは指定PIDの前後snapshotでピーク負荷ではなく、OpenClaw/RAGとの競合はNOT_MEASUREDのまま。モデル選定には実レビューを50〜100件蓄積し、False Negativeの内容、確率校正、通常利用中の待ち時間とリソース競合を別途評価する。

## 検証

`bash tests/local-judge/run-samples.sh` はモデル・Secretなしで、型/enum/範囲/余剰項目、1-token契約、認証、size、timeout、redirect、本文非保存、baseline不変、比較計算を検証する。既存JEVとBrokerの回帰テストも維持する。外部接続・本番評価・最終Mergeはこれらのテスト成功と分離する。
