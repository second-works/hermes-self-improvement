# Application setup / doctor template

このディレクトリを自作アプリのリポジトリへコピーし、アプリ固有の設定・依存関係・health endpointに合わせて調整します。

## 標準構成

    bin/
      setup
      doctor
    .env.example
    README.md

コピー後は実行権限を付与します。

    mkdir -p bin
    cp templates/app/bin/setup bin/setup
    cp templates/app/bin/doctor bin/doctor
    cp templates/app/.env.example .env.example
    chmod +x bin/setup bin/doctor

## 使い方

    ./bin/setup
    ./bin/doctor

setupは既存の.envを上書きせず、アプリのデータディレクトリを作成します。Node.jsアプリではpackage-lock.jsonに基づくnpm ci、Pythonアプリでは.venvとリポジトリ内の依存定義を使います。依存関係がないアプリでもデータディレクトリと設定ファイルを準備できます。何度実行しても既存の設定・データを破壊しないことが契約です。

doctorは設定ファイル、基盤コマンド、依存定義、永続データディレクトリ、port設定を検査します。APP_HEALTHCHECK_REQUIRED=1にするとAPP_HEALTHCHECK_URLへ接続し、APP_EXPECT_RUNNING=1と組み合わせることで設定portとhealth endpointのport一致を確認します。両フラグは0または1だけを受け付け、health URLの資格情報やqueryは出力しません。起動前の開発環境ではhealth検査をスキップし、明示的な理由を表示します。

## 境界

Docker、Node.js、Python自体の導入は環境側の責務です。アプリ固有の依存関係は各リポジトリ側へ置きます。永続データはAPP_DATA_DIRでコード外へ分離し、秘密情報は.envやローカルのSecret Managerで注入します。setupとdoctorは秘密情報の値を出力しません。

CIでは、CI用の実行環境・依存関係を準備した後、同じ./bin/doctorを設定した検査モードで呼び出します。runtime health endpointがCIで起動できない場合は、APP_HEALTHCHECK_REQUIRED=0の契約検査とし、実環境のhealth検査は別の受入テストで実施します。
