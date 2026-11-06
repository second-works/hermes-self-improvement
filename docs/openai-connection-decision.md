# HermesのOpenAI接続判定（#62）

第一候補はChatGPT Plusの `openai-codex` OAuth。公開資料による候補選定まで完了し、接続の判定は **UNKNOWN（実通信停止）** とする。
対象版、アカウントでの利用枠、無人運転の条件、送信・保持・停止の制御を実行前に確認する。今回の追加費用・実推論・実推論の再試行は0。Risk TierはHIGH（認証・外部送信・費用の境界）。

## 候補版と接続経路

- 静的確認の対象は [Hermes v0.22.7](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.7)、commit `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`。導入済み版とは別。#47 の [静的調査](hermes-static-survey-issue47.md) では、実使用版と既存費用経路はUNKNOWNだった。
- [固定版のprovider文書](https://github.com/NousResearch/hermes-agent/blob/b200f5bc60e31588ba2cb60e288029c4a54ba5fa/website/docs/integrations/providers.md) と [OAuth実装](https://github.com/NousResearch/hermes-agent/blob/b200f5bc60e31588ba2cb60e288029c4a54ba5fa/hermes_cli/auth_codex.py) で、device-code OAuthとトークン更新を確認。認証発行元は `auth.openai.com`。推論はChatGPT側のCodexバックエンドを候補とし、上書き設定を含む実効URLと補助経路は承認前に固定する。Hermesの [OAuthガイド](https://hermes-agent.nousresearch.com/docs/guides/oauth-over-ssh) はPlus/Proを挙げるが、固定版のprovider文書には利用枠の計上方法が記載されていない。
- OpenAIの [Sign in with ChatGPT](https://developers.openai.com/siwc/token-sharing-open-source) は適格な契約の利用経路を説明している。Hermesの特定版・アカウント・運転形態の利用条件は個別に確認する。手動は承認後に隔離した新規セッションで公開入力1件を試す候補。無人運転は、手動試行に加えて自動更新・失効・再起動・緊急停止の境界を確認するまで保留。
- APIは別の認証・利用枠・課金を持つ。[既存provider](../src/delegation/openai_provider.py) は固定の `https://api.openai.com/v1/chat/completions` に `OPENAI_API_KEY` で接続し、登録済み操作の選択をJSON schemaで受ける。送信前に呼出数・token・USD予算を照合し、期限を制限する。Skills修正案を返すHermes接続と契約が異なるため、再利用するのは宛先制限・予算・応答検査の実装を候補とする。APIを採用する場合は [単価](https://developers.openai.com/api/docs/pricing) と1件・期間ごとの通貨上限を承認し、最大費用を送信前に確保する。

## 送信と停止の判定

| 条件 | 判定 |
| --- | --- |
| 未対応版・アカウントやモデルの対象資格が不明 | 送信前に停止。対象版・根拠・環境を人間が確認 |
| 期限切れ・認証拒否・更新不能 | 停止して再認証の要否を人間へ。自動で別のログインを借用・コピーしない |
| 利用枠不足・費用や上限不明 | 停止。追加クレジット購入やAPIへの自動切替を許可しない |
| 補助呼出・再試行・別providerの宛先や総回数を制御できない | 停止。タイトル、圧縮、レビュー、tool起因の補助呼出も確認する |
| PUBLIC以外が混入、保持条件が不明、入力経路や出力先が承認と異なる | 送信前に停止。秘密・会話・実Memory・hidden評価データを渡さない |
| 承認済みの版・環境・送信先・入力・上限がすべて一致 | 別Issueで承認した操作だけを許可。今回のIssueでは実通信0 |

[Hermesのcredential pool文書](https://hermes-agent.nousresearch.com/docs/user-guide/features/credential-pools) は、一時的な制限での再試行・資格情報の切替、設定時のfallback、失効した資格情報の隔離を説明している。補助呼出は主モデルを継承する場合もある。既定の挙動を安全制御の証拠にせず、対象版で各経路を無効化または上限内に制限できることを確認する。

個人契約の推論環境は管理条件を確認するまでUNMANAGEDとして扱う。OAuthの保存・利用条件をAPIの条件から推定しない。APIの `store: false` は保持全体を無効化する保証ではない。[APIのデータ管理](https://developers.openai.com/api/docs/guides/your-data) に基づき、乱用監視ログと機能別保存を確認する。許可を求める際は固定版、実行環境、データ分類と保持、宛先、権限、時間・呼出数・token・追加費用、緊急停止と証跡を提示する。詳細は [安全境界](ai-agent-security-boundary.md)。

## オフライン実装への受渡し

#63から#64へ渡すのは、完了した観測から切り出したPUBLIC packet。観測識別子、安定したイベントID、失敗分類と根拠ID、対象Skill・変更可能範囲を含め、入力のサイズ上限と分類を制御側で検査する。
#64は提案1件（原因・根拠・許可範囲の候補差分）、再利用、無変更、保留のいずれかを返し、不正形式・根拠不足・境界違反は制御側で停止する。
#65は既存の候補形式・独立評価・最小監査記録へ接続する。認証情報、利用枠、送信先の設定はこの入出力に含めず、モデルにはshell・任意通信・GitHub書込を付与しない。候補実行は既存の隔離評価に限り、合格後も人間確認待ちで止める。

## 模擬改善の緊急停止と再開

ローカルの監督者が `python3 -I -B scripts/run_mock_improvement.py --stop` を実行すると、停止要求が `runs/mock-improvement/intake-stop.json` に残る。別の観測とプロセス再起動からの受付も拒否する。稼働中の隔離ワーカーがあれば、試行記録と隔離設定を照合して停止し、既存コントローラによる後始末を待つ。終了を確認できない場合は受付を閉じたままにする。

`INTAKE_STOPPED` が返れば実行ロックと保留中の隔離記録を確認済み。確認不能の場合は保留記録と対象コンテナを監督者が調査し、記録を保全する。保留記録を削除して再開を強制しない。停止が確認できたら、監督者は `python3 -I -B scripts/run_mock_improvement.py --resume` で受付を再開できる。処理済み観測の試行記録は再開後も有効。
