# Gemma 4 E4Bのエージェント適性調査（2026-10-17）

追記：以下の設定確認は4条件比較の前の調査時点。後続の実測では思考切替とJSON制約を確認したが適用可能な差分は得られなかった。[4条件の実測結果](gemma-e4b-thinking-json-comparison-2026-10-17.md)を参照。

**結論：現時点で「モデルの能力限界」と断定しない。** E4Bをエージェントの実行モデルに使う研究・公開実装は存在する。一方、今回のHermes親子による自律コード生成・修正を、同じMac・同じ量子化・同じ制御で安定完了できることまでは公開資料から確認できなかった。モデル切替を先に推奨した判断は、以下の設定差を調べてから行うべきだった。

**今回のローカル確認。** 対象はGemma 3nではなく `gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf`。既存LaunchAgentと直近2つの保存済み試験plistで `--reasoning off` を確認した。推論なしの `/props` GETでもreasoning_format=none、template内にenable_thinking参照があることを確認。temperature=1.0 / top_p約0.95 / top_k=64は公式推奨と一致する。リクエストのreasoning_effort=mediumだけでは思考有効化の確認にならず、今回のサーバー設定はoffだった。中継の許可フィールドにresponse_format / chat_template_kwargsはなく、JSON出力は自然文指示に依存していた。これはruntimeや設定の評価であり、モデル能力の上限測定ではない。詳細数値は `runs/gemma-e4b-research-20261017/local-observations.json`。

| 一次資料 | 確認内容 | 証拠の限界 |
|---|---|---|
| [Google公式モデルカード](https://huggingface.co/google/gemma-4-E4B-it) | native function callingとcodingを機能として記載。E4BのTau2平均指標42.2%、LiveCodeBench v6は52.0%。思考制御と推奨samplingを説明 | 4bit QAT、Mac mini、今回の差分課題の成功率ではない |
| [Google公式function callingガイド](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4) | E4Bを対象モデルに含む。Thinkingを用いたfunction calling例と精度改善の説明がある | 例は天気API等。自律コード修正の保証ではない |
| [EDGEGEN論文・2026-09-21](https://arxiv.org/html/2609.24115v1) | Gemma-4-e4bを実行側エージェントとしたτ²-bench airline実験。Table2の平均進捗はbase0.4301、人手ケースで最適化0.5083、EdgeGen最適化0.5608。後者はbase比約30%相対改善 | 正答率や自律修正成功率ではない。航空業務のtool-agent実験。E4B自身が自分のハーネスを改変した証拠ではない。GPU環境でMac4bitと同条件ではない。論文の著者報告であり本調査の再現実験ではない |
| [boldblackai/harness](https://github.com/boldblackai/harness) | Pi / OpenCode / Hermesを包む実装。READMEでLM Studioのgemma-4-e4bを既定モデルとして明記 | 統合構成の存在の証拠。E4Bで全agent・全課題が合格した第三者再現データとしては扱わない |
| [g667300/hermes-agent-local](https://github.com/g667300/hermes-agent-local) | compose.e4b-qat.ymlに今回と同じUD-Q4_K_XLのモデルbasename、context64000、MTPを含む。READMEに試験環境・速度測定を記載 | Ubuntu、RAM30GB、Quadro P2200 5GB等の条件。機能の信頼性と今回のコード修正品質は別。手順を実行・導入していない |
| [llama.cpp E4B不具合 #22786](https://github.com/ggml-org/llama.cpp/issues/22786) | E4BのQ8/BF16でtool callがcontentとして返るという当事者報告。closedの過去Issue | 現在のbuildや今回の失敗原因と同一とは未確認 |
| [llama.cpp 複数行引数 #25986](https://github.com/ggml-org/llama.cpp/issues/25986) | 長い複数行文字列のtool-call解析についての報告 | maintainerが再現curlを要求し、その後staleで閉じた報告。確定した現行バグや原因と扱わない |
| [Hermes E4B/vLLM parser相談 #6626](https://github.com/NousResearch/hermes-agent/issues/6626) | 同じE4BとHermesでparserの組み合わせが問題になる導入報告 | llama.cppとはruntimeが異なり、今回の直接JSON出力の誤りを説明しない |

**JSON制約出力。** [llama.cpp server一次仕様](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)にはresponse_formatによるJSON / schema制約出力がある。モデルに「JSONだけ」と頼むことと、生成時にschemaで制約することは違う。今回の閉じ括弧不足やMarkdown fenceには対策余地がある。ただし、JSONが正しくなっても挿入位置やコードの意味が正しいとは限らず、差分の境界検査と9テストを保持する必要がある。現行ローカルbuild・Gemma thinkingとの併用互換性は未検証。

**今回の失敗との関係。** 実親子の起動・skill_manageによるファイル生成は実際に成功している。コメント修正では4/6から5/6へ改善しているため、E4Bがagentとして一切稼働しないという結果ではない。一方、後半はtoolをAPIから除いた直接ソース入力でも誤った挿入位置を返した。これらをすべてtool parserだけの問題と説明することもできない。厳密な制約への追従、生成コードの意味、思考設定、出力制御、試験側の条件を別々に評価する必要がある。

**次の推奨検証。** 同じE4B・同じ固定課題・同じ候補・同じ差分境界で、思考OFF/ON × JSON schema制約なし/ありの4条件を比較する。形式合格、範囲合格、全9テスト合格を別々に記録する。時間・token・memoryを測り、成功時だけ新session再利用へ進める。schemaは出力構造だけに使い、正しい差分そのものを固定してモデル成功と数えない。これでも位置や意味の誤りが残るなら、同一条件で別モデル比較を行う根拠になる。現在の稼働サービスへ変更を加えず、具体的な差分・予算・停止条件を準備して別途実行範囲を確認する。

調査中のモデル推論0回、サービス変更0件。公開資料の閲覧・保存と限定したローカル設定/GETメタデータの読み取りだけを行った。GitHubの公開READMEやIssueは各著者の記述として扱い、安全設定を変更したり手順を実行したりしていない。公式資料はContext7のllama.cpp索引でも照合した。
