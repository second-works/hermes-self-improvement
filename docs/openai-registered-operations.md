# OpenAI APIによる登録済み操作の選択

Issue #7の2026-10-27方針に基づき、現在の入口をOpenAI provider対応にした。
モデルは固定PUBLIC候補の登録済み修正を選び、既存ハーネスが適用・検証・実stdoutからのJSON出力を担当する。
今回の実装・検証では実API通信、キーの存在確認、課金確認、Docker実行、ローカルサービス操作を行わない。
Gemmaの実験入口と証拠は履歴として保持する。

Risk Tier: HIGH。有料API、認証ヘッダー、PUBLIC入力の外部送信を扱う実装のため。
承認済み範囲はコード・設定・モック検証と本repoの専用PRへの提出。
実モデル・料金の採用とlive実行は、対象・予算を指定した別途の人間承認が必要。
復旧は本PRの変更を戻し、既存の選択ファイル方式を使用する。失敗runを再利用・自動再送しない。

## 通信と情報の境界

`scripts/run_registered_operations.py --openai-config ...` が新しい入口。
`--allow-api`がなければキーを読む前に停止する。`--selection`との同時指定も拒否する。
従来の`--catalog`、選択ファイル方式、既定の候補準備だけの動作は維持する。
この経路はGemma、localhost relay、Hermes本体を呼ばず、サービスを起動・変更しない。

送信先は`https://api.openai.com/v1/chat/completions`へのTLS検証付きPOSTだけ。
proxy環境変数、任意URL、HTTP method、redirect、retry、tool呼出は使わない。
キーは明示オプトイン・設定・予算検査後に`OPENAI_API_KEY`からのみ読む。
引数や設定ファイルにキーを渡す欄はない。

送信するのは固定カタログ、固定prompt、PUBLIC候補から得た「現在適用可能な操作ID」のみ。
候補ソース自体も送信せず、事前に固定hashの4状態と照合する。
実ログ、会話、hidden評価、任意ソースを入力とする経路はない。
公開仕様の読取と本repoへのコード提出を除き、本作業でモデルへ送信するデータはない。
CONFIDENTIALをMANAGED/UNMANAGED環境へ送る許可も追加しない。

## 明示設定と費用の予約

[設定雛形](../fixtures/delegation/registered-operations/openai-config.example.json)のmodel・料金・contextは未設定で、通信前に必ず失敗する。
価格の既定値やモデルの自動選択はない。
将来のlive実行前に、公式仕様と契約料金を確認し、次を人間が明示する。

- `model`: 応答のmodelと一致する固定モデルID。aliasが別IDで応答する場合も停止する。
- `input_usd_per_million`、`output_usd_per_million`: 正の10進文字列、USD/100万token。通常入力単価で計算し、キャッシュ割引を見込まない。
- `model_context_tokens`: 採用モデルの公式context上限。未知なら実行しない。
- `max_input_tokens`: context上限以上の入力予約枠。contextの全量を予約して、tokenizerの推測による費用の過小評価を避ける。
- `max_output_tokens`: APIに渡す`max_completion_tokens`。推論tokenを含むcompletion全体の上限。
- `max_total_input_tokens`、`max_total_output_tokens`、`max_calls`、`max_cost_usd`: 1 provider runの累計上限。
- `deadline_seconds`、`timeout_seconds`、`max_response_bytes`: run期限、1通信のtimeout、応答byte上限。

入力のbyte数＋8192のframing余裕＋出力予約がcontextに入らなければ、送信前に停止する。
これは入力tokenの正確な計数ではない。費用予約はbyte見積りではなく、設定した入力枠全量を使う。
予約費用は`(入力枠×入力単価 + 出力枠×出力単価) / 1000000`。
既消費額との合計がrun費用上限以上なら送信しない。上限ちょうども拒否する。
料金・contextの正確さは操作者が公式資料と照合する設定契約であり、自動で料金やアカウントを取得しない。

usageの入力・出力・合計を整数として検査し、予約枠と照合してから費用を確定する。
通信失敗やusage不明時は予約を未精算のまま保持し、runを停止する。
失敗後に呼出枠を戻したり、費用を0として再試行したりしない。
CLIは1回の選択だけを行う。別CLIのrunとの累計予算共有はなく、各live runの承認が必要。

## 選択・実行・保存

APIにはstrict JSON schemaを渡し、応答もローカルで厳密JSON、固定ID、重複なし、適用可能性を検査する。
provider schemaではOpenAIの対応subsetに合わせて`uniqueItems`を外し、重複拒否をローカルで保持する。
拒否、途中打切り、tool呼出、非JSON、未知操作、usage不整合は失敗として停止する。
未知IDを捨てる、Markdownを補正する、別モデルへフォールバックする動作はない。

新規runには検査済みIDだけの`selection.json`、`provider-report.json`、`candidate/`を保存する。
選択ファイルはAPI本文の保存ではなく、固定allowlistへ正規化したハーネス入力である。
provider reportは呼出数・usage・計算費用・未精算予約・status・応答hash等のメタデータだけ。
prompt、API応答本文、キー、HTTPエラー本文は保存・表示しない。
既存出力、symlink、不正な出力境界は通信前に拒否する。原本と過去証拠は上書きしない。

既定は`PREPARED_NOT_EXECUTED`であり、選択の成功を候補品質や実行の成功にしない。
`--execute`を別途承認して指定した場合だけ、既存の固定Docker隔離へ渡す。
15公開課題の回帰・完全性検査と別2入力の実stdout由来のJSON保存は既存ハーネスが担う。
candidate reportの`model_calls: 0`は、そのファイル適用工程自身がモデルを呼ばない意味。
APIの呼出数は外側のprovider reportで別に記録する。
不完全修正・回帰・実行失敗は成功にならず、独立評価、本番採用、Merge、Issue Closeは人間に残す。

## オフライン検証

```sh
python3 -I -B -m unittest discover -s tests -p 'test_openai_provider.py' -v
python3 -I -B -m unittest discover -s tests -p 'test_registered_operations.py' -v
python3 -I -B -m unittest discover -s tests -p 'test_delegation*.py' -v
./scripts/verify.sh
/opt/homebrew/bin/bash scripts/security-preflight.sh .
```

provider試験は合成キーとmock transportだけを使い、実環境のキーを取得しない。
実API疎通、実費用、モデル精度、実Dockerの新しい検証結果は未確認。
標準CIは既存30試験の固定入口であり、追加試験はローカルで明示実行する。CIの保証範囲を広く解釈しない。
既存のテスト・Gate・workflowは変更しない。

参照: [Chat Completions公式API仕様](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)、[既存の実行境界](registered-operations.md)。
