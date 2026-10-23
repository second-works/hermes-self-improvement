# hermes-self-improvement

Hermes Agentの改善案をIssueとPRで検討する開発リポジトリです。合成課題で監査、評価、登録済み操作による候補修正を検証します。Hermes Agent本体 `~/.hermes` は操作しません。

1 Issue = 1 PRで進め、ローカル検証 → self-review → PR → CI / Security / CodeQL → Codexレビュー → 必要修正と同じheadの再検証 → 人間のMerge判断を維持します。

```sh
./scripts/verify.sh
# SecurityはBash 5以上。macOSの例:
/opt/homebrew/bin/bash scripts/security-preflight.sh .
```

Python 3とGit、Bashが必要です。テストは標準ライブラリだけを使います。typecheck / buildはアプリと型検査設定がないため理由付きで対象外です。

採用・除外ファイル、レビュー起動・認証・費用・失敗時対応、保護設定の状態は[導入記録](docs/repository-setup.md)を参照してください。[AGENTS.md](AGENTS.md)と[Security Policy](SECURITY.md)を適用します。

標準検証の前提はGit、Bash 5以上、Python 3、Node.js/npmです。npm監査の回帰は実CLIでも検証し、依存0の無害fixtureだけを使います。Hermes本番には接続しません。

合成fixtureの[自己監査・失敗診断](docs/audit-diagnosis.md)は、6分類と根拠付き改善提案を決定的なJSONで出力します。実環境の棚卸しやスキルの自動生成・適用は行いません。

[登録済み操作を選ぶ実行構成](docs/registered-operations.md)では、AIの選択とハーネスの修正、検証、結果出力を分けます。`python3 -I -B scripts/run_registered_operations.py --catalog`で固定メニューを確認できます。既定の候補準備はモデルやDockerへ接続しません。実際の隔離実行は明示指定時だけ行い、本番へ自動適用しません。
