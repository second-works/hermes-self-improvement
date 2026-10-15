# HTML Status Report

`scripts/render-status-report.py` は、`scripts/collect-github-state.py` が出力した観測JSONを、ローカルで読める単一HTMLファイルへ変換する。

MarkdownとJSONの正本を置き換えない。生成HTMLは観測内容の表示用であり、CI、Security、レビュー、受入、マージ可否を判断しない。

## 実行

出力先は利用者が指定する。入力と同じパスは指定できず、既存ファイルも上書きしない。

```bash
python3 scripts/render-status-report.py \
  /path/to/github-observation.json \
  --output /path/to/status-report.html
```

生成物は外部CSS、JavaScript、画像、ネットワーク通信を使わない。通常はGit管理に追加せず、必要な共有時だけ生成元JSONとともに扱う。

## 表示する内容

- 正本リポジトリ、入力JSONのパス、観測時刻、収集状態
- IssueとPRの状態、対象head SHA、head整合性
- Securityを含むWorkflowの観測結果
- 同一headのレビューとレビューコメントの件数
- 未観測、収集エラー、再収集などの残作業
- 観測artifactの解釈上の境界

入力の文字列はすべてHTMLエスケープして表示する。URLを含む入力もリンクとして実行・遷移させない。

## 検証

```bash
bash tests/html-status-report/run-samples.sh
```

この検証は固定fixtureを使い、正常表示、長いSHA、空の観測、危険文字列、入力JSONの非変更、無効JSON、出力先エラーを確認する。
