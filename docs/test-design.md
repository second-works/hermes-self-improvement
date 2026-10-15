# テスト設計と安全な削除

**Decision: 現行AGENTSの詳細契約を、必要な作業時に参照する文書へ分離する。**

親 [#168](https://github.com/second-works/ai-development/issues/168)、準備 [#173](https://github.com/second-works/ai-development/issues/173)、契約案 [PR #172](https://github.com/second-works/ai-development/pull/172)。原文は `7a52b2b3f46487b91190a6c923926c9325913046` の [固定原文AGENTS](https://github.com/second-works/ai-development/blob/7a52b2b3f46487b91190a6c923926c9325913046/AGENTS.md) の Test Design / Safe Test Deletion。

PR #174で移行準備し、先行PRの人間Merge後、Issue #177でAGENTSから参照する詳細正本として有効化した。通常レビューの直接対応は2026-10-03の人間指示を反映し、その他の安全責務・例外を保持する。

## Test Design / Safe Test Deletion

テストは「数を増やすこと」ではなく、「必要な検証責務を適切な層で保証すること」を目的とする。

原則として、次のように責務に応じてテスト種別を選ぶ。

- ビジネスロジック、計算、値変換、境界条件: Unit Test
- HTTP入力、Controller、API契約、認証・認可、入力バリデーション: Controller / API Test
- SQL、永続化、DB制約、Repository境界: Repository Test
- 複数コンポーネントの接続、主要ユースケース: Integration Test
- ユーザー視点の重要なHappy Path、システム全体の接続確認: E2E Test

すべてをIntegration / E2Eで検証する設計は避ける。遅いテストや重複テストが増えた場合は、責務をより小さいテスト層へ移せないか検討する。

既存テストを削除・統合する場合は、削除前に以下を確認する。

1. そのテストが何を保証しているか説明できる。
2. 同じ検証責務が別のテストで保証されている、または不要になった合理的理由がある。
3. 責務を別テストへ移す場合は、新しいテストが先に追加され成功している。
4. 認証・認可、入力検証、Repository境界、重要な回帰テストなどの安全性確認が失われない。
5. 重要なHappy Path / Integration / E2Eの安全網が必要に応じて残っている。
6. 削除理由と検証責務の移行先をPR本文またはIssueで説明できる。

「CIを速くしたい」「テストが遅い」「コード量を減らしたい」だけを理由に、検証責務の所在を確認せずテストを削除してはいけない。

テスト移行では、可能な限り **新しいテストを追加して成功を確認してから古いテストを削除する**。大規模なテスト整理では、ドメインや責務ごとにIssue / PRを分け、比較可能な状態を保ちながら段階的に進める。
