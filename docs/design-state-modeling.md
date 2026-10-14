# 設計・状態モデリング

**Decision: 現行AGENTSの詳細契約を、必要な作業時に参照する文書へ分離する。**

親 [#168](https://github.com/second-works/ai-development/issues/168)、準備 [#173](https://github.com/second-works/ai-development/issues/173)、契約案 [PR #172](https://github.com/second-works/ai-development/pull/172)。原文は `7a52b2b3f46487b91190a6c923926c9325913046` の [固定原文AGENTS](https://github.com/second-works/ai-development/blob/7a52b2b3f46487b91190a6c923926c9325913046/AGENTS.md) の Design / State Modeling。

PR #174で移行準備し、先行PRの人間Merge後、Issue #177でAGENTSから参照する詳細正本として有効化した。通常レビューの直接対応は2026-10-03の人間指示を反映し、その他の安全責務・例外を保持する。

## Design / State Modeling

型・スキーマ・状態設計で保証できる制約は、プロンプトやレビューだけに依存せず、コード構造そのもので保証する。

- 不正な状態を型上表現できない設計を優先する。
- 複数のbooleanの組合せで状態を表現するより、状態を判別できるモデルを優先する。
- 外部入力はシステム境界で検証・変換し、内部では検証済みの型として扱う。
- 状態分岐は可能な範囲で網羅性チェックが働く構造にする。
- 型で保証できる内容を、防御的な`if`や重複したvalidationとして各所に散在させない。
- AIが局所的に理解しやすい、単純で明示的な型や構造を優先する。必要性のない複雑な型テクニックを標準化しない。

これは防御的なチェックをすべて禁止するものではない。信頼境界での入力検証や、外部システム由来の異常を扱う処理は省略せず、型で保証できる責務との境界を明確にする。特定言語の機能に限定せず、Generic、Python、Node.jsなどへ適用できる一般原則として扱う。
