# Security Policy

このリポジトリのmainと公開PRを保守対象とします。Hermes Agent本体は対象外です。

脆弱性はGitHubのSecurity → Report a vulnerabilityが利用可能なら非公開で報告してください。利用できない場合は機密情報・攻撃手順・APIキーを公開Issueに貼らず、リポジトリ管理者へ非公開の連絡先を確認してください。受付期限や修正期限は保証しません。

秘密情報はGitHub Secretsまたはローカルの管理対象外ファイルに保持します。Security reporterの秘密鍵はmain限定EnvironmentのSecretだけへ保存します。OpenAI APIキーは要求しません。CIから本番・`~/.hermes`へ接続しません。

[AI Agent Security Boundary](docs/ai-agent-security-boundary.md)と[プロジェクト固有ルール](AGENTS.md)を適用します。Security Preflightは既知パターン検査であり、完全な秘密検出を保証しません。未対応の依存監査はSECURITY_UNAVAILABLEとして停止します。
