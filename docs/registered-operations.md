# 登録済み操作を選ぶ実行構成

2026-10-23、ユーザーは「AIが決まった操作を選んで実行できる」をIssue #7のゴールとして採用し、実装への移行を承認した。
AIが登録済み操作を選び、ハーネスが入力検査、候補への適用、検証、隔離実行と結果保存を担当する。
自由なコード生成と自律的なスキル再利用は今回の完了条件から外す。
以前の生成と再利用の不合格は、成功した操作選択方式と分けて保持する。

Risk Tier: HIGH。候補修正と隔離実行の境界を実装として確定するため。
対象は固定PUBLIC課題と候補で、本番、実ログ、認証、サービス変更、Cronは扱わない。
今回の実装では新しいモデル通信やDocker実行を行わず、2026-10-17の実測証拠と今回のオフライン試験を分けて示す。

## 責任の分担

| 部品 | 正本 | 責任 |
| --- | --- | --- |
| 操作カタログ | src/delegation/catalog.py | 固定ID、バージョン、目的、前提条件、選択schemaを提示 |
| 修正処理 | src/delegation/patch.py | 許可されたカウンター挿入だけを適用。未知ID、重複、適用済み、アンカー不一致を拒否 |
| 実行ハーネス | src/delegation/registered.py | 選択ファイルを受け取り、新規runで候補を準備。明示指定時だけ隔離実行 |
| 実行境界 | src/evaluation/sandbox.py | networkなし、非root、read-only mount、資源制限、起動設定照合、終了処理 |
| 出力検査 | src/delegation/execution.py | 実stdoutを厳密JSONとして検査し、結果をシリアライズ |

カタログは事前登録式で、実行時にAIが新しい処理を登録する経路はない。
操作の追加はコード変更としてレビューする。
今回の操作は匿名化したPython差分の検査スクリプトの行番号修正に限定される。

| 操作ID | 内容 |
| --- | --- |
| count_context_lines | 文脈行を読んだときに新ファイルの行番号を進める |
| count_added_comments | 追加コメントを読み飛ばす前に新ファイルの行番号を進める |
| 空のoperations配列 | 変更せず検証へ進む。検証合格を伴わなければ修正不要の成功にはしない |

AIが返す選択形式は `{"operations":["count_context_lines","count_added_comments"]}`。
ハーネスは0件から2件の異なる既知IDだけを受け付ける。
対応できる操作がない場合は、上位の呼び出し側が停止する。
今回の選択契約には「対応不能」と「修正不要」を別enumで返す機能を追加していない。
空配列を対応可能性や正しさの保証にしない。

## 使い方

Python 3の標準ライブラリだけで、カタログ表示と候補準備ができる。
リポジトリのルートから実行する。

```sh
python3 -I -B scripts/run_registered_operations.py --catalog
mkdir -p runs
python3 -I -B scripts/run_registered_operations.py \
  --source fixtures/delegation/registered-operations/review.py \
  --selection fixtures/delegation/registered-operations/selection.json \
  --output runs/registered-example
```

選択ファイルはAIの回答を受け取るアダプターである。
このCLI自体はAIに接続しない。
同梱selection.jsonは再現用の固定選択であり、この実行を新しいAI判断として数えない。
モデルによる選択の実測証拠は後述のJSONを参照する。

既定ではbaseline.py、candidate.py、report.jsonだけを新規runへ保存し、`PREPARED_NOT_EXECUTED`を返す。
原本と選択ファイルを上書きせず、既存の出力先やsymlinkを拒否する。
失敗後のrunは調査用に残すため、再試行には別の新規出力先を使う。
入力ソースは、固定hashに一致する同梱PUBLIC候補と、その2操作から作れる4状態だけを許可する。
この照合は空配列にも適用し、任意のrepo内ファイルや追記したコードは受け付けない。
選択ファイルはリポジトリ内の通常ファイル、出力はruns配下の新規ディレクトリに限定する。

隔離実行する場合は、上のコマンドに`--execute`を付け、別の新規出力先を指定する。
この指定はDockerコンテナを実際に作成するため、実行の承認境界を確認してから使う。
CLIはDockerサービスを起動せず、イメージのpullやモデル通信も行わない。
既存のarm64 Linux Docker環境と、core.pyの固定IMAGEに一致するローカルPythonイメージが必要である。
環境、イメージ、隔離設定の検査に失敗した場合は停止する。

実行時は修正前後を既知の15問で比較し、回帰なしで全問合格する改善、または全問合格した変更なしだけを認める。
その後、別の固定2入力を実行し、実stdout由来の結果をexecution-results.jsonへ保存する。
不合格と実行失敗は`FAILED`として記録し、CLIはexit 2を返す。
検査済みJSONへ期待値を合成したり、モデルのMarkdown回答を補正したりしない。
`VERIFIED`はこの有限の公開課題の実行結果であり、独立評価や本番採用を表さない。

## 証拠と検証

2026-10-17の[実モデル証拠](evidence/skill-delegation-controlled-execution-live.json)は、AIが2操作を選択して6/15から15/15へ改善し、次の判断で修正不要を選び、ハーネスが別2入力を実行した記録である。
今回のファイルアダプターはこの責任分担を再利用する。
新しいCLIを実モデルや実Dockerで通した結果とは区別する。

再現用review.pyは、同証拠のsource_hashesにある候補から末尾空白と最終改行を正規化したもの。
元hashは`1804f0badf98b154e4793d8e3a86ed10733fa2073a609f7a19d7d8247ac20d3c`、再現用hashは`091055ee7066c5ea2b8d5d919a7845585793f90b7109ba9a52273ffcfc4239ea`。
元候補は変更しない。
このfixtureの検出ロジックは固定課題向けで、一般のPythonコードレビュー品質を保証しない。

今回の対象試験は、モデル、Docker、本番サービスへ接続せずに実行する。

```sh
python3 -I -B -m unittest discover -s tests -p 'test_delegation*.py' -v
python3 -I -B -m unittest discover -s tests -p 'test_registered_operations.py' -v
./scripts/verify.sh
```

登録済み操作の試験では、隔離runnerのテストダブルを使って出力の受け渡しと拒否を検証する。
これを候補コードの実行合格やモデルの精度として扱わない。
既存CIの固定検証入口は変更せず、新規試験はローカルで明示実行する。
提出前のSecurityは変更をstageした後、Bash 5以上で`bash scripts/security-preflight.sh .`を実行する。

過去の実験用入口はscripts/delegate_skill.pyとscripts/check_improvement_cycle.pyに保持する。
そこに残るrun固有のパス、呼出枠、サービス操作は、履歴の再現条件であって現在の実行許可ではない。
初期調査の指摘と今回の合意は[調査メモ](issue-7-status-review-2026-10-23.md)を参照する。
