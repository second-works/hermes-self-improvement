# 標準検証入口

`verify.sh` は、テンプレートから生成したプロジェクトのローカル・Agent・GitHub Actionsで共有する検証入口です。

## 配置

このファイルを新規プロジェクトの `scripts/verify.sh` としてコピーし、実行権限を付与します。

```bash
mkdir -p scripts
cp templates/verification/verify.sh scripts/verify.sh
chmod +x scripts/verify.sh
```

実行コマンドは次の1つに統一します。

```bash
./scripts/verify.sh
```

## 実行契約

工程は必ず次の順に実行します。

1. lint
2. type check
3. test
4. build

対象外工程は `[verify] stage=... skipped reason=...` として理由を出力します。対象工程のコマンドが失敗した場合は `[verify] stage=... failed exit=...` を出力して同じ終了コードで終了し、後続工程を実行しません。4工程すべてが対象外、または工程スクリプトが1つもない場合も、検証ゼロの成功を防ぐため非0終了します。

## 技術スタック別の設定

- Node.js: `.nvmrc` と `package-lock.json` をcommitし、`package.json` に必要な `lint`、`typecheck`、`test`、`build` scriptを定義します。存在しないscriptは対象外です。Node.js自体が利用できない場合や `package.json` を読めない場合は停止します。
- Python: `.python-version` と依存lock/pin（例: `requirements-dev.txt`、`uv.lock`、`poetry.lock`）をcommitします。Ruff / mypyの設定がある工程は対応コマンドを必須とし、設定がなければ対象外です。テストファイルがある場合はpytestを必須とします。PEP 517の `[build-system]` がある場合は `python -m build` を必須とします。
- Generic: 必要な工程を `scripts/lint.sh`、`scripts/typecheck.sh`、`scripts/test.sh`、`scripts/build.sh` として実装します。存在しない工程は対象外です。工程スクリプトが1つもない場合は検証失敗とし、`scripts/ci.sh` へ暗黙にfallbackしません。

## 実行前ゲート

標準検証が成功する前にcommit、PR作成、Codex Code Review依頼へ進みません。検証を実行できない場合は、実行不能の理由を記録して停止し、人間の判断を得ます。CIを無効化したり、Lint・型検査・テストを削除・skip・無条件緩和したりして成功扱いにしてはいけません。

## バージョン更新

Node.jsの実行環境は `.nvmrc`、依存関係は `package-lock.json` で固定します。Pythonの実行環境は `.python-version`、開発ツールは依存lock/pinで固定します。固定を更新するときは、固定ファイル・依存lock・CI設定を同じ変更単位で更新し、標準検証と生成サンプル検証を再実行してPR本文に記録します。
