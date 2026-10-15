# hermes-self-improvement

Hermes Agentの改善案をIssueとPRで検討する開発リポジトリです。現在は開発基盤のセットアップのみで、自己改善を自動適用する機能はありません。Hermes Agent本体 `~/.hermes` は操作しません。

1 Issue = 1 PRで進め、ローカル検証 → self-review → PR → CI / Security / CodeQL → Codexレビュー → 必要修正と同じheadの再検証 → 人間のMerge判断を維持します。

```sh
./scripts/verify.sh
# SecurityはBash 5以上。macOSの例:
/opt/homebrew/bin/bash scripts/security-preflight.sh .
```

Python 3とGit、Bashが必要です。テストは標準ライブラリだけを使います。typecheck / buildはアプリと型検査設定がないため理由付きで対象外です。

採用・除外ファイル、レビュー起動・認証・費用・失敗時対応、保護設定の状態は[導入記録](docs/repository-setup.md)を参照してください。[AGENTS.md](AGENTS.md)と[Security Policy](SECURITY.md)を適用します。

標準検証の前提はGit、Bash 5以上、Python 3、Node.js/npmです。npm監査の回帰は実CLIでも検証し、依存0の無害fixtureだけを使います。Hermes本番には接続しません。
