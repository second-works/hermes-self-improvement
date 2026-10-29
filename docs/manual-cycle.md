# PUBLIC fixtureの手動1サイクル

Issue #9は、PUBLIC失敗観測から今回生成した候補の独立評価、専用PR、明示承認、fixtureへの模擬採用、再観測までを結合する。
Risk Tier: HIGH。候補と評価の同一性、承認、模擬書込、中断からの復旧を扱う。
既存#32の生成受取・固定評価と#8の登録root・承認票・backup・intent・回帰を再利用する。
#8の旧候補、評価hash、承認、rootは流用しない。

## 境界と責務

制御側CLIは `python3 -B scripts/manual_cycle.py --run cycle-<id> <step>`。
自動モデル呼出、GitHub書込、Merge、次サイクル開始の機能はない。
CodexはPUBLIC観測の原文を確認して診断する。
原因と対応の選択はAIの判断であり、その自己申告は品質評価、本人証明、採用結果の代用にならない。
生成担当には `runs/generated-<id>/packet/` の基準・contract・PUBLIC例だけを渡す。
制御側journal、評価器、hidden入力/正解/個別trace、既存の完成候補、登録済み修正、registryと承認票を渡さない。
生成コンテキストを独立させても、同一OS利用者に対するfilesystemの強制隔離を保証するものではない。
候補bytesの実行は既存固定Dockerだけ。ホストでimport/exec/実行しない。

PUBLICは合成観測・候補・検査済み集計、INTERNALは評価者専用hiddenと個別metrics。
機密情報、実ログ、会話、認証、`~/.hermes`、本番は読まない。
Codexアプリを主経路とし、有料API/キー確認/追加クレジットは0、GemmaはOFF。
外部Writeはユーザーが指示した `second-works/hermes-self-improvement` の専用branch/Issue/PRだけ。
新しい送信先、workflow、権限、サービス、課金の変更はない。
依存のMergeと検収はtrusted supervisorがGitHubで別々に照合し、PUBLIC参照を `fixtures/manual_cycle/dependency.json` に固定する。
このreceiptは外部署名された証明ではなく、人間検収の検査済み記録である。

## 手順と状態

1. `initialize --expires-at <timezone付き日時>` は有効期限24時間以内のconfigと永続global lockを新規作成する。
   既存run、別run、期限切れlockを再初期化・削除しない。
2. `start` は固定image/隔離probeを検証し、評価集合・policy・評価器sourceを候補前にfreezeする。
   基準版をPUBLIC失敗例でDocker実行し、観測の入力hash・基準SHA・結果hashを保存してOBSERVEDへ進む。
3. `diagnose --proposal <controller内のJSON>` は下記schemaを検査する。
   REPAIRだけがPROPOSEDへ進む。NO_CHANGEはNO_CHANGE、REUSEはREUSED、INSUFFICIENT_EVIDENCE/INSUFFICIENT_AUTHORITYはHOLD、FORBIDDENはFAILで停止する。
   理由にPUBLIC以外を含めない。既存機能の再利用が十分な場合も新しい候補を作らない。
4. `handoff` で生成開始を記録し、PUBLIC packetの場所を表示する。
   初回と公開修正1回まで。生成担当は指定artifactだけを変更してpacket内にcommitし、完全SHAを返す。
   PUBLIC例の実行もホストでは行わず、制御側の `public-check --candidate-sha <SHA>` に渡す。
5. PUBLIC合格の候補1件だけを `evaluate` で独立評価する。
   基準・候補・劣化対照を各PUBLIC/hiddenで3回比較し、監査する。
   FAIL/HOLDは終端。hidden判定後に同じ集合で生成・再調整・再評価しない。
6. PASSだけが新しい採用controller/登録root/backupとPUBLIC packetを作りAWAITING_PRになる。
   `submission` のpacket、diff、candidate bundle、PUBLIC集計を検査して本repo専用PRへ提出する。
   `submit --url <PR URL> --head-sha <repo PR head> --packet-hash <canonical packet hash>` はtrusted supervisorがGitHubで照合した提出記録。
   packet内のcandidate SHAはfixtureのcommitで、repo PR head SHAと別の識別子。提出記録はCI/Review/Merge成功の証拠ではない。
7. 同じ最新repo headのlocal/CI/Security/CodeQL/正式Codex Reviewを照合する。
   `request --action ADOPT --expires-at <日時> --actor <human-id>` は未承認の下書きだけを返す。
   人間へ候補/評価/対象root/binding/前後hash/backup/期限を提示した後だけ、承認済みrequest objectをcontroller内に保存する。
   `execute --request <file> --confirm-request-hash <canonical request hash>` は#8と同じ再照合・intent・backup・Docker回帰で書き込む。
8. `reobserve` が実体とDocker回帰を再検査し、REOBSERVEDで1サイクルを終了する。
   同じ候補/評価/rootを追跡し、次サイクルを開始しない。

proposal schema（未知field/変更範囲/古い観測を拒否）:

```json
{"decision":"REPAIR","reason":"PUBLIC観測を原文照合した原因と選択理由","observation_hash":"canonical observation SHA256","baseline_sha":"full fixture baseline SHA","allowlist":["scripts/review.py"],"classification":"PUBLIC"}
```

修正以外のdecisionではallowlistを空配列にする。
理由の妥当性はCodexと人間が観測原文から確認し、ハーネスはhashとschemaと遷移を保証する。

## 停止・排他・予算

run_idと基準/候補SHA、observation/proposal/manifest/evaluation/packet/approval/adoption/rollbackのhashを結合する。
評価または候補の変更は採用packetと承認を失効させる。
1課題・候補1件・1サイクル・同時1、累計machine timeは1200秒。
各commandのmonotonic時間をjournalに加算し、Docker子processも残りdeadlineで制限する。
人間待ちはchargeしないが、runと承認票のwall-clock期限は再開前に照合する。
予算超過/期限超過、依存欠如、出力不正、旧票、二重実行は停止する。
OS排他lockはcommand間競合を防ぎ、永続lockは別runの自動開始を禁止する。lock/intentを自動消去しない。

commandの前にBUSYと時間予約をfsyncする。
途中にADOPTED等の状態があっても、operation_completedまたは明示的な失敗・中断記録まで未完了として扱う。
再起動では書込前はSTOPPED、採用/復旧intentが未完または書込有無不明ならRECOVERY_REQUIRED。
書込後は対象側journalにもRECOVERY_REQUIREDを記録し、その最新eventへ結合した別の復旧票を要求する。
同一bootの中断時間は経過時間を保守的にchargeし、OS再起動や時計同一性不明では残り全額を予約済みとして扱う。
予算/期限不足では復旧も実行せず、人間に新しい範囲の判断を求める。制限を自動延長しない。
再開とは人間待ちから次の明示commandへ進むこと。FAIL/HOLD/STOPPEDから自動再開しない。
`status` は未完処理の検出を保存する。`submission` は読取表示で、停止状態の実行を再開しない。

## 別の故障注入と復旧

正常サイクルのREOBSERVED後、`prepare-trial --kind degradation` と、復旧後の `prepare-trial --kind crash` を別々に行う。
同じ評価済み候補でも、各trialは新しいcontroller/登録root/backup/承認を持つ。
正常対象の内容、root binding、journalは保持し、故障対象に流用しない。
各trialのADOPT下書きを取得し、`fault-plan --request <file>` の計画とhashも提示する。
人間が採用と故障計画を承認した後だけ、`execute` に `--confirm-fault-hash <plan hash>` も渡す。
degradationは採用回帰成功後に固定PUBLIC劣化bytesを書き、再観測でRECOVERY_REQUIREDへ移る。
crashは#8のintent/backup保存後、候補先頭128bytesを書いてprocess exit71とする。
新processの `status` でRECOVERY_REQUIREDを確認する。注入を合格候補の品質と混同しない。

故障後の `request --action ROLLBACK` は現在hash、元版hash、同じroot、intent、backup、最新event、期限へ結合した**新しい下書き**。
人間がこれを別承認した後にだけ `execute` し、元hashと固定Docker回帰が合格した場合にROLLED_BACKとなる。
復旧不能・期限/予算不足・未実施は成功にしない。
具体的targetの故障注入と復旧は、実装依頼やPR提出の許可から推定しない。

## 検証と検収

`python3 -I -B tests/test_manual_cycle.py -v` は合成承認とfake評価/Docker観測を明示して、実filesystem・実process終了で境界を検査する。
候補自体の実行・独立評価成功・人間検収の証拠にはしない。
既存の `tests/test_generated_repair.py`、`tests/test_evaluation.py`、`tests/test_adoption.py` を関連回帰として維持する。
標準verify、Bash5 Security、same-head CI/Security/Analyze(python)/CodeQL/正式レビューは別gate。
追加ローカル/Docker試験は固定CIが実行したと記載しない。

人間検収は、PUBLIC失敗が今回の生成候補と同じSHA/hashを通して改善し、正常対象で再観測でき、別trialで故障と承認付き復旧を確認できること。
人間は原因分析、対応選択、承認対象、再観測結果の有用性と検収を判断する。
記録先は `runs/cycle-<id>/` と専用PRの検査済みPUBLIC集計。未実施はNOT_RUNを維持する。
設計失敗仮説は、既存完成解の再利用、候補/評価取り違え、人間承認省略、停止後自動再開、正常対象の巻込み。
これらの検出、20分超過、停止/復旧不足ではNot Acceptedとする。
有限fixtureの成功から一般的な自己改善能力や本番採用を主張しない。
UI/Production Release/Full-System Security Auditは対象外（CLIによるPUBLIC fixture検収のみ）。

Harness判定はSTRENGTHEN。既存評価と採用は各工程を守るが、工程をまたぐ同一性・総予算・生成上限・二重cycleを保証しないため、既存処理へ薄い制御journalを追加する。
入力はPUBLIC観測/診断/候補SHAと人間票、出力はhash連鎖状態と限定fixture。
判定は状態/hash/予算で決定可能。コストは既存独立評価の逐次Docker180件、PUBLIC確認10件、採用/再観測各10件、復旧5件と人間確認。
同等の工程間同一性と停止/復旧保証を持つ代替が実証された場合に統合を再評価する。既存gateや試験を削除しない。

## Issue #9の検証記録（2026-10-29）

以下の生成・独立評価・Docker40件は修正前head `a6d2fa6f6c8206e819d8b2ce80a4ee49ab47970c` の履歴である。
PR #45のレビュー修正で制御側source hashが変わったため、現headのサイクル実証には流用しない。
同じ候補bytesと閾値による新runは人間の別承認後に再検証した（末尾参照）。旧run・評価・lock・backup・未承認票は保全し、旧票を実行しない。

[PUBLIC証拠](../artifacts/manual-cycle/issue-9/summary.json)を、候補・評価・packet・bundleのhashで固定した。
新runは `cycle-issue9-approved-20261029`、候補SHAは `8a32cf60008e28fd0175074018b13eceaa35e7ec`。
候補内容hashは `3e5354f0a2043112e5e38c46ee8793471bad1bc74621a5af29c8dfa4c6782a57`、評価hashは `dc5a67348ade4e646c6d8e44410026346b0aa165208dfdd05394d93006f989d1`。
基準はPUBLIC5/10・hidden5/10、候補は両方10/10で独立評価PASS、劣化対照はFAIL、監査VERIFIED。
今回の独立生成コンテキストはPUBLIC packetだけを読み、ホストで候補を実行しなかった。
初回生成SHA `498865c0b81e418a48254ef5487b651f0050049a` から、新runへ同一bytesを再登録した。hidden結果で修正していない。

初期runは評価器の自己点検で期限切れ回収の不具合を見つけたためSTOPPEDとして保全した。
新規実行のdeadlineが安全回収も拒否する修正前失敗を再現し、基底Sandboxの個別5秒回収を維持するよう修正した。
修正後20件と、固定probeの実Docker deadline2秒→TIMEOUT→停止/回収成功を確認した。
ユーザーが別runを明示承認した後だけ、新しい評価集合をfreezeした。旧評価のPASSは新headへ流用していない。

| Requirement | Risk | Verification | Result |
| --- | --- | --- | --- |
| PUBLIC観測→独立生成→独立評価 | 完成解/hidden混入、自己申告PASS | 独立PUBLICコンテキスト、事前freeze、基準/候補/劣化対照のDocker180件、audit | VERIFIED（有限fixture） |
| 不要生成/旧票/上限/排他/停止 | 権限不足、根拠不足、予算、二重run、出力不正 | tests/test_manual_cycle.py 20件、既存生成19/評価34/採用28件 | VERIFIED（合成観測/票を含む） |
| 採用/再観測/故障/復旧の接続 | 実体取り違え、部分書込、正常対象巻込み | tests/run_manual_cycle_docker.py、別controller/root、実process exit71、Docker40件 | VERIFIED（合成票、人間検収ではない） |
| 人間の模擬採用/復旧と全体検収 | 実装/提出許可の採用承認への流用 | 未採用の別人間target、具体的票・故障計画、故障後の別復旧票 | NOT_RUN |
| 最新repo headの外部gate | 旧headのCI/Review流用 | 標準verify/Bash5 Security、PR後にCI/Security/CodeQL/正式レビュー | PRで最新結果を記録 |

新runの観測・評価・合成Docker試験のmachine timeは約156秒。人間待ちは除外し、今後の実操作も同じ予算へchargeする。
有料API/キー確認は0、cycle内GemmaはOFF。資料読解時のローカルLLM圧縮はcycle外であり、この実証のモデル効果に含めない。
固定CIは既存setup30件とlintで、上記追加試験を実行したと扱わない。
人間targetはAWAITING_APPROVAL、試験container残存0。人間の採用・故障注入・復旧・検収、最終Mergeは未実施。
Product Accepted/Issue #9完了/親#31完了を宣言しない。

レビュー指摘 PR45-R1（P2/BLOCKING）: 劣化bytes注入後、再観測前にprocessを終了すると、中間ADOPTEDを完了扱いして復旧票を要求できなかった。
実process exit72の再現と、書込前PROPOSED後のexit73の対称例は修正前2件失敗、修正後成功。
完了記録のない操作を検出し、対象側とcycle側を停止状態へ揃える。復旧は新票で元hashへ戻り、正常対象不変、再statusで再記録・二重chargeなしを確認した。
追加suiteは22件成功。評価と回帰callbackは合成であり、今回の22件を独立評価・実Docker・人間検収の代わりにしない。

## レビュー修正後の再検証

ユーザーがPR45-R1修正後の別runを明示承認し、`b94691e7f99aa408c76a5f43f0d7c42807392018` の制御sourceをfreezeして再検証した。
最新の[PUBLIC証拠](../artifacts/manual-cycle/issue-9/r1/summary.json)は `cycle-issue9-r1-approved-20261029` に対応する。
候補SHAは `4f643dc0a3b44a6f217922cb6356c7c45fe49d6a`、評価hashは `e4f5aecabec40cbfa5c900cc15edffa0c6c2c2112afdb365abe4058172737fe5`。
候補bytesは初回独立生成から不変（内容hash `3e5354f0a2043112e5e38c46ee8793471bad1bc74621a5af29c8dfa4c6782a57`）。新集合で基準PUBLIC/hidden各5/10、候補各10/10、PASS、劣化対照FAIL、audit VERIFIED。
合成承認票・別rootによるDocker40件も再実行し、正常ADOPTED/再観測、劣化と部分書込・exit71からのROLLED_BACK、候補/元hash一致を確認した。
機械時間は約144秒、人間用targetは未採用AWAITING_APPROVALで不変、container残存0。有料API/キー確認0、cycle Gemma OFF。
上記の再検証は人間の実操作検収ではない。人間承認による採用/故障注入/復旧、手動サイクル検収、最終Mergeは未実施。
追加22件と標準verify/Security、同じ最終repo headのCI/CodeQL/正式再レビューはPRに別々に記録する。
