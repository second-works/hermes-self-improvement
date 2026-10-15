# RAG標準設計指針

## 目的

この文書は、Nine標準AI開発テンプレートを利用するRAG（Retrieval-Augmented Generation）プロジェクトの共通設計方針を定める。

RAGは最初から高機能化せず、必要性を確認しながら段階的に高度化する。特定のベクトルDB、LLM、Embeddingモデル、フレームワークには固定しない。

## 基本原則

- 最小構成から開始し、検索品質・回答品質・運用要件を計測してから上位Phaseへ進む。
- 検索精度と回答時の文脈量を分離して考える。
- Vector Searchだけに依存せず、キーワード検索やMetadataを組み合わせる。
- 検索結果には可能な限り出典・文書ID・位置情報などの追跡可能性を持たせる。
- Reranking、Multi-Representation、RAPTOR、GraphRAGは必要性が確認できた場合に追加する。
- 高度化による精度改善だけでなく、レイテンシ、計算資源、インデックス更新コスト、保守性も評価する。
- 本番利用では引用、根拠確認、ハルシネーション検証を品質要件として扱う。

## 段階導入モデル

### Phase 1: Hybrid Search + Metadata

初期標準構成。

- Vector Search
- BM25等のキーワード検索
- Metadata Filter

Vector検索とキーワード検索を組み合わせ、文書種別、日時、権限、カテゴリ、出典などのMetadataで候補を絞り込めるようにする。

### Phase 2: Parent–Child Retrieval

検索用チャンクと回答用文脈を分離する。

- Child: 検索精度を優先した小さなチャンク
- Parent: LLMが回答時に参照する、より広い文脈

小さいチャンクで検索し、ヒットしたChildに対応するParentをLLMへ渡す。これにより検索精度を維持しつつ、前後関係や条件文を保持する。

### Phase 3: Reranker

初期検索で得た候補を、質問との関連度で再順位付けする。

- Hybrid Searchの候補集合を対象にする
- Cross-EncoderやLLM Reranker等は要件に応じて選択する
- Recallを初期検索で確保し、PrecisionをRerankerで高める

Reranker導入時は回答精度だけでなく、追加レイテンシと計算コストを測定する。

### Phase 4: Multi-Representation Retrieval

1つの情報源から複数の検索用表現を生成する。

例:

- 原文チャンク
- 要約
- 想定質問
- キーワード / エンティティ
- 表の説明文
- コードの説明 / Docstring
- 画像の説明文

検索用表現と回答時に提示する原文を分離し、PDF、表、コード、画像など異種データの検索性を高める。

### Phase 5: RAPTOR

大量文書や長文書を対象に、情報を階層化して検索する必要がある場合に検討する。

- 下位層: 原文に近いチャンク
- 中間層: 複数チャンクの要約
- 上位層: より広いテーマ・文書群の要約

局所的な質問だけでなく、文書全体や複数文書を横断する抽象的な質問への対応を目的とする。

RAPTORはインデックス生成・更新コストが上がるため、通常のParent–ChildやMulti-Representationで不足することを確認してから導入する。

### Phase 6: GraphRAG

人物、組織、製品、技術、制度などの関係性を複数文書にまたがって探索する必要がある場合に検討する。

- Entity抽出
- Relation抽出
- Knowledge Graph構築
- Graph探索とVector / Keyword検索の統合

単純な文書検索で十分なシステムにGraphRAGを導入しない。構築・更新・品質管理の運用コストに見合うユースケースがあることを確認する。

## 推奨検索パイプライン

本番RAGでは、必要に応じて次の構成を検討する。

1. Query Guardrail / 入力検証
2. Intent判定・Routing
3. Metadata Filter
4. Hybrid Retrieval（Vector + Keyword）
5. Parent–Child / Multi-Representation / RAPTOR / Graph等から必要なRetrieverを実行
6. Reranking
7. Context整理・重複除去
8. LLM生成
9. 引用・根拠整合性確認
10. ハルシネーション検証

すべてを必須実装とはしない。プロジェクト要件に必要な段階だけ採用する。

## 品質評価

RAGの改善は感覚ではなく、評価データを用いて判断する。

最低限、以下を検討する。

- Retrieval Recall: 必要な根拠が候補に含まれるか
- Retrieval Precision: 不要な候補が多すぎないか
- Answer Correctness: 回答が正しいか
- Faithfulness / Groundedness: 回答が取得した根拠に基づいているか
- Citation Accuracy: 引用先が回答内容を実際に支持しているか
- Latency: 実用上許容できる応答時間か
- Cost / Resource Usage: API費用、GPU/CPU、メモリ、ストレージが妥当か

上位Phaseへ進む前に、現在のボトルネックを評価し、そのPhaseで改善可能かを確認する。

## セキュリティ・権限制御

業務データを扱うRAGでは、検索後ではなく検索前または検索時に権限制御を行う。

- ユーザー / 組織 / ロールに基づくMetadata Filter
- 機密文書のアクセス制御
- 出典追跡
- ログへの機密情報出力防止
- Embedding / Indexに保存する情報の取り扱い確認

権限のない文書を取得した後にPromptで隠す設計は避ける。

## 各プロジェクトでの採用記録

RAGを採用するプロジェクトでは、原則として次のファイルを作成する。

`docs/architecture/rag-design.md`

最低限、以下を記録する。

```markdown
# RAG設計

標準:
- docs/architecture/rag-guidelines.md

採用Phase:
- Phase 1
- Phase 2
- Phase 3

採用構成:
- Hybrid Search
- Metadata Filter
- Parent–Child Retrieval
- Reranker

未採用:
- Multi-Representation
- RAPTOR
- GraphRAG

未採用理由:
- 現時点では検索品質に十分な改善余地があり、高度化コストに見合わないため

評価指標:
- Retrieval Recall
- Answer Correctness
- Citation Accuracy
- Latency
```

標準と異なる構成を採用する場合は、その理由を `rag-design.md` に記録する。

## Phase昇格ルール

上位Phaseへ進む場合は、次を確認する。

1. 現在の品質問題を具体的に説明できる。
2. 評価データまたは再現可能な失敗例がある。
3. 次Phaseがその問題を改善できる合理的根拠がある。
4. レイテンシ・計算資源・保守コストの増加を許容できる。
5. 追加後に効果を比較評価できる。

「高機能だから」「新しい技術だから」という理由だけでPhaseを上げない。

## 参考設計思想

本指針は、Flat RAGからParent–Child、Multi-Representation、RAPTOR、GraphRAGへ段階的に発展させる設計思想、およびHybrid Retrieval、Reranking、引用・検証を組み合わせる実運用RAGの考え方を参考にしている。

実装時は外部記事の構成をそのままコピーせず、対象データ、質問特性、運用コスト、セキュリティ要件に合わせて採用範囲を決定する。

## AGENTSから移した詳細責務

Issue #177で常駐本文を短縮し、main `2afd63dcfc68e7e0596d70e1fcc350fcbcc71d6c` の詳細責務を本正本へ移した。以下の適用条件・例外は既存の具体手順と併せて適用する。矛盾や重要判断不足があれば推測せず停止する。

### RAG Architecture Standard

RAGを新規構築・変更する場合は [`docs/architecture/rag-guidelines.md`](rag-guidelines.md) を標準設計指針として参照する。

原則として最小構成から開始し、検索品質・回答品質・運用コストを評価してから上位Phaseへ進む。高機能であることだけを理由にRAPTORやGraphRAG等を先行導入しない。

RAGを採用する各プロジェクトでは、原則として `docs/architecture/rag-design.md` を作成し、少なくとも次を記録する。

- 採用Phase
- 採用するRetriever / Reranker / Metadata構成
- 未採用Phaseと理由
- 品質評価指標
- 標準から逸脱する場合の理由

本番RAGでは、引用・出典追跡・根拠整合性・ハルシネーション検証・権限制御を要件に応じて評価対象とする。
