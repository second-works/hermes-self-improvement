# Issue #35: 不足する集計スキルの生成実証

既存機能の不足を確認してCodexが新規生成した2ファイルは、履歴なしの実Codex 3セッションで利用できた。
一括評価はPASS、auditはVERIFIED。13条件すべて各3/3で、実行27件の最終返却が実stdoutと末尾改行まで一致した。
Risk Tier: HIGH。AI生成Python、独立受渡し、隔離実行と固定評価を扱い、着手・提出前とも維持した。
固定課題の結果であり、一般的な生成精度や本番Hermesでの動作を保証しない。

## 新規作成の根拠と生成材料

2026-10-28、人間がPR #39をMergeして「進めて下さい」と指示した後に着手した。
完全な合成一覧はcomplete:trueで、既存はgithub-code-review / python-diff-reviewの1件だけだった。
path/patchを検査する既存機能は、eventsをcategory別のok/failed件数へ集計する入出力契約を満たさない。
生成担当はこれを根拠に新規作成が必要と判断した。

生成担当はfork_turns=noneで起動し、独立PUBLIC packetのcatalog.json、contract.json、public.jsonとGit識別情報だけを読んだ。
完成コード、既存対照実装、評価器、tests、hidden、以前の会話は渡していない。
生成は `event-status-counts/SKILL.md` と `event-status-counts/scripts/aggregate.py` だけ。
Python 3.12標準ライブラリのみで、hostでの実行/importはしていない。静的ast検査とskill-creator quick_validateに合格した。

初回生成1回、公開修正1回、最終候補内容1件。
初回の集計コードは公開4例すべてに合格したが、手順に未提供の資料取得とroutingへのrespond呼出しがあった。
公開transportとの照合を根拠にSKILL.mdだけを修正し、再度4/4に合格した。
aggregate.pyのbytesは初回から不変。hidden利用後の修正は0回。

## 固定対象

評価器・入力・期待値は生成前にfreezeした。

| 識別子 | 値 |
| --- | --- |
| controller SHA | `0ee8a76549376926a53b5296e30452e885a94e02` |
| run | `skill-2ee186c219dab2e1b3a8af15` |
| packet基準SHA | `6294fb8a69d2a31eed2af045bf51a83b99a69601` |
| 初回候補SHA | `f84cbf78eb117219d53e5a34a80fca0c077bebe8` |
| 最終候補SHA | `a5ed84835670818aa63b0345ad60e111fd10fb75` |
| SKILL.md SHA-256 | `3c72df2e34093a0c9e101805b265001356c3c8cfc795b3bbf5d17cbe655e827a` |
| aggregate.py SHA-256 | `71d21965955799bdbe865fc529dd61da0051d854b2c3027a84c94e7b1e57af14` |
| manifest hash | `1e6eb829f9a7e3c19aa9890d8ff9e669017983142b09b0d76c460fcbd29e77e4` |

候補受理は、基準の子孫、2ファイルだけの追加、通常blob、合計64KiB以下、cleanなpacketと標準ライブラリimportを検査した。
同じSHA・2ファイルhashで公開合格した結果も受理時に結合する。
受領bundleは基準commitを前提とする差分だったため、評価済みpacketから原本を含む独立bundleへ再exportした。
候補SHAと2ファイルbytesは変えていない。空Git repositoryへfetchし、元版と全差分を検査する回帰に成功した。

## 実利用と一括評価

fork_turns=noneの実Codex subagentを3つ逐次起動した。通常のchatタブを3つ作ったものではなく、履歴なしの独立推論セッションである。
渡したのはread/use/respond入口、スキル、task群、許可operationとtransportだけ。作成会話・評価器・正解・他担当結果は渡していない。
catalogのcapability IDは同じI/O契約を指す識別子と説明した。routingは提示snapshotで元要求の作成要否を選ぶ対照であり、追加のファイル生成ではない。

| 固定条件 | 3試行の結果 |
| --- | --- |
| 新規必要、同等機能あり、一覧不完全、権限不足 | 各3/3で作成選択・再利用・保留を適切に選択 |
| 複数category、空、重複、16KiB境界 | 各3/3で正常stdout一致 |
| 誤型、不正status、不正category、余分なキー、過大入力 | 各3/3でexit 2とINVALID_INPUT JSON一致 |
| 最終返却 | 27/27で実stdoutのbytes/hashと一致 |

各担当はreadを読み判断した後、trusted CLIのuse→stdout文字列の転送→respondを逐次実行した。
JSONの再計算・再シリアライズをせず、taskの最終返却先へ原stdoutを渡した。終了チャットは管理用受領報告だけ。
16KiB空白はモデルcontextへ展開せず、入力JSON・実bytes数/hashと空白の説明を渡した。プログラムには原bytesを入力した。
正誤フィードバックは3試行終了まで返さず、一括評価は1回だけ。自己申告や説明の体裁は採点に使っていない。

実Docker 7種gate、公開8回、本評価27回を逐次実行した。
固定image、networkなし、非root、read-only、CPU1、256MiB等の既存制限を維持し、新imageのpull・制限緩和・サービス変更は0。
prepare/public/useの計測は29.93秒。prepareから監査までの壁時計を含む保守的上限は約597秒で、1200秒以内。
API/Gemma呼出・キー確認・追加クレジットは0。元版・候補・run/lockを保持する。

## PUBLIC証拠と再現

`artifacts/skill-creation/issue-35/` に候補2ファイル、独立bundle、公開実stdout、検査済み集計、audit、生成回数と根拠を保存した。
reportは実行観測と最終返却のhashだけを公開し、個別入力・正解・trace・返却原bytesはINTERNALとしてローカルrunに保持する。

```sh
python3 -B -m unittest discover -s tests -p test_skill_creation_artifact.py
python3 -B -m unittest discover -s tests -p test_skill_creation.py
```

専用adapterの操作は [skill-creation.md](skill-creation.md) を参照する。
元controllerとrunを保持すればauditを再実行できる。同じrunでevaluateを再実行しない。
新しい実評価には人間判断後の新runとfreezeが必要で、旧候補SHAを新しい基準へそのまま流用しない。

adapter回帰12件は実freeze/audit結合を使うが、コンテナ観測はmockである。これを実モデル/Dockerの成功証拠とは扱わない。
PUBLIC同一性1件と、標準・関連回帰を実行し、最終PR headのlocal/CI/Security/正式レビューはPRへ記録する。
依存manifestなしのため依存監査は理由付き対象外、typecheck/buildは設定なしの理由付き対象外。warning/deprecationは観測していない。

情報分類はPUBLIC合成候補/集計と、ローカル保持のINTERNAL評価原本。LLMは承認済みCodexアプリ。
ReadはPUBLIC packet/本repo/Issue、Writeは本repo専用branch/PR、送信先allowlistはsecond-works/hermes-self-improvement。
同一OS利用者の任意読取隔離は保証せず、trusted supervisorと最小受渡しを前提とする。
本番/~/.hermes/実ログ/認証/モデルサービス、インストール、依存・権限・課金・CI変更は対象外。
Merge、Issue Close、採用は人間判断。#36や#8へ進まない。復旧はPUBLIC追加のrevertを人間が判断する。

ローカル結果は標準setup 30件、新規adapter 12件、新規PUBLIC証拠1件、既存skill-reuse 11件と証拠1件、generated-repair 19件、登録操作8件、evaluation 34件の計116件が成功。
Bash 5 Security PreflightはSECURITY_PASSED。固定CIが追加ローカル試験も実行したとは扱わない。
