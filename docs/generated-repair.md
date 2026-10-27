# 生成修正候補の独立評価

Issue #32では、課題 `review-input-contract-v1` の受取と評価接続を準備する。
Risk TierはHIGHであり、生成コードの隔離と評価の独立性を扱う。
実生成の品質実証は、本PRを人間がMergeした後の #33で行う。

## 固定する課題

編集可能なartifactは `scripts/review.py` の1ファイル、上限は64KiBである。
基準の内容hashは `7d342aa1fc92afaeea8b7aee834650965b885f167975fd2d4f18e5c31ee80b6e` とする。
生成用Git repositoryの基準と候補は、この同じ論理pathと完全commit SHAで識別する。
契約の正本は `fixtures/generated_repair/contract.json`、公開10ケースはfreeze時の `packet/public.json` にある。

入力は16KiB以下のJSON objectで、キーはpathとpatchだけを許可する。
pathは `case_[a-z0-9]{8,32}\.py`、patchは非空文字列とする。
不正JSON、空入力、キーの過不足、誤型、不正path、上限超過はexit 2、stdoutはJSON object `{"error":"INVALID_INPUT"}`、stderrは空とする。
正常入力では既存のfinding schemaと挙動を維持する。
既存の固定2操作入口と、既存runnerのexit 0契約は変更しない。

## 評価者の準備

評価者だけがcontroller repositoryとrun rootを扱う。
PUBLIC合成資料を使い、hidden原本、正解、個別traceはINTERNALとしてローカルrunに保存する。
生成担当に渡すのは後述の独立したPUBLIC packetだけである。
生成担当へcontroller repositoryの探索権限を与える運用は対象外とする。
同一OS利用者による任意ファイル読取までをこのCLIが隔離する保証はなく、別チャットの作業領域と入力をpacketに限定する。

controllerの差分を標準検証、self-review後にcommitしてから、評価者が次を実行する。

```sh
python3 -B scripts/generated_repair.py prepare
python3 -B scripts/generated_repair.py freeze --run generated-<24桁hex>
```

`prepare` は既存の固定arm64 imageを検査し、既存7種の隔離gateを実行する。
imageがなければ停止し、pullは行わない。
networkなし、非root、read-only、CPU1、memory256MiB、PID上限、出力上限、timeout、回収を既存Sandboxで確認する。
候補以外のHOME、Secrets、socket、hidden rootをcontainerへmountしない。

`freeze` はcommit済み評価器のhash、環境、gate、policy、予算、公開10ケース、評価者専用hidden10ケースを固定する。
新規packetのGit履歴には基準commitだけが存在するため、受理する子孫候補はfreeze後に追加する。
閾値は既存policy（hidden改善1件以上、回帰なし、失敗増なし、latency倍率1.2以下、API費用0）を使う。
各入力3回を評価し、1候補、逐次実行、機械処理の累計20分以内とする。

## 生成担当へのPUBLIC handoff

freezeの成功とmanifest hashを評価者が記録した後、`runs/<run>/packet` だけを独立した場所へコピーする。
Git履歴もコピーし、hardlinkやshared object storeを作らない。
packetには基準、入力契約、公開ケースとGitの識別情報だけがあり、登録修正ID、完成patch、評価原本への参照、hidden原本やtraceは含めない。
controllerのdocs、tests、runの親directoryは生成担当へ渡さない。

生成担当へ渡す依頼は次に限定する。

> 同梱contractと公開ケースを満たすようにscripts/review.pyだけを修正する。
> 他のartifactは変更しない。
> 初回生成と公開テスト修正1回までとし、最終候補1件を基準の子孫commitにする。
> 公開テストを含む候補実行は、評価者の固定Docker経由だけで行い、ホストでは実行しない。
> モデルAPI、ネットワーク、controllerやhiddenの探索を行わない。
> 完全candidate SHAと、基準以降のGit bundleを評価者へ返す。

生成側に評価結果を返すのは、最終候補の集計だけとする。
hiddenの結果を見た後の再調整は行わない。

## 受取と比較

評価者はPUBLIC bundleのSHAと送信元を確認し、packet repositoryへローカルのbundleを取り込む。
この操作は候補コードを実行しない。
Git hooksは無効化し、remote URLやshared objectsは追加しない。

```sh
git -c core.hooksPath=/dev/null -C runs/<run>/packet fetch --no-tags /absolute/public-candidate.bundle <candidate-full-sha>
git -c core.hooksPath=/dev/null -C runs/<run>/packet checkout --detach <candidate-full-sha>
python3 -B scripts/generated_repair.py evaluate --run generated-<24桁hex> --candidate-sha <candidate-full-sha>
python3 -B scripts/generated_repair.py audit --run generated-<24桁hex>
```

受取時は基準の子孫、1ファイル差分、通常blob、内容hash、cleanな作業領域、現HEADと指定SHAの一致を検査する。
symlink、範囲外差分、変更済み評価器、dataset、policy、旧SHA、既存出力、使い済みlockは拒否する。
候補はread-onlyの別コピーで実行し、原本とコピーを評価後にも照合する。
SHAを変えれば既存評価は再利用できない。

adapterは期待されたexit 2を正答として扱い、stderr、timeout、OOM、実行故障、schema不正を分ける。
基準、候補、空findingの劣化対照を比較し、劣化対照を検出できない場合はHOLDとする。
reportはSHA、artifact hash、manifest hash、公開とhiddenの正答件数、PASS/FAIL/HOLDだけを返す。
個別観測は `metrics.private.json` に残し、GitHubや生成担当へ送らない。
`audit` はhash連鎖、checkpoint、両SHA、artifact、manifest、private metricsを照合する。
PASSも採用やMergeの承認ではない。

## 停止と検証

runとglobal lockは成功時も失敗時も自動削除しない。
故障や回収不能では停止し、pending containerを記録する。
次のrunは、人間が既存runの監査とcontainer残存を確認し、lockの解除や新しい評価rootを判断してから準備する。
既存runやlockを上書きして再試行しない。

`tests/test_generated_repair.py` の通し試験は、実行観測を供給するmockであり、候補品質や実隔離の証明には使わない。
正常、劣化、証拠不足、freeze前の拒否、改変、旧SHA、path、symlink、上限、lock、監査を検証する。
実Dockerの7種gateは別に実行し、controllerのhashとrunを記録する。
固定CIの標準検証は従来のsetup試験であり、新規試験と関連回帰は追加ローカル検証として明記する。

このadapterは既存の独立評価と固定操作の入口を保持したまま、今回の期待拒否だけを追加する（Harness判定: STRENGTHEN）。
解決する失敗は、未登録候補のすり替え、評価条件の事後変更、期待拒否と実行故障の混同である。
入力はPUBLIC packetとimmutable commit、出力は比較reportと監査記録、実行コストは最大180回の逐次container実行となる。
同じ拒否保証と独立性を別実装で実証できた場合に再評価する。
有料API、Gemma、本番接続、workflow、権限、課金の変更は含めない。
