# 新規合成スキルの生成と独立利用

Issue #35は、完全な合成一覧に集計機能がないことを根拠として、新しいSKILL.mdとaggregate.pyを生成し、履歴なし3セッションで利用する実証である。
Risk Tier: HIGH。生成Python、独立受渡し、Docker隔離、固定評価を扱う。
本番登録、~/.hermes、認証、モデルサービス、依存追加、workflow変更は対象外。

## 契約と生成前固定

正本は `fixtures/generated_skills/event-counts-task/contract.json`。
入力はeventsだけを持つJSON objectで、各eventはcategory/statusだけ。categoryは英小文字・数字1〜16文字、statusはok/failed。
categoryごとに両statusの件数を持つcounts objectを返し、重複eventも数える。空配列は空counts。
不正入力はexit 2、厳密なINVALID_INPUT JSON、空stderr。UTF-8のstdin全体は16KiB以下。
生成側に渡すのは完全な合成一覧、契約、公開4例と許可ツールだけ。
候補は `event-status-counts/SKILL.md` と `event-status-counts/scripts/aggregate.py` の2ファイル、合計64KiB以下、Python 3.12標準ライブラリだけ。
完成コード、評価器、対照コード、hidden入力/正解、作成会話は渡さない。

専用の独立checkoutで、標準検証・関連回帰・Security・self-review後に評価器をcommitし、次を実行する。

```sh
python3 -B scripts/skill_create.py prepare
python3 -B scripts/skill_create.py freeze --run skill-<24hex>
```

#34のprepare/freeze結合・hash連鎖・audit・固定Sandboxを再利用する。
prepareは実Docker 7種gateを確認する。新imageのpullはしない。
freezeは評価器、環境、予算、基準commit、公開例、3試行分の入力/期待値を候補生成前に固定する。
run/lockは既存のものを再利用せず、失敗時も削除しない。

PUBLIC packetをGit履歴ごと独立コピーし、fork_turns=noneの生成担当へ渡す。
初回生成と公開修正1回まで、候補内容1件。生成後は2ファイルだけの子孫commitとbundleを返す。
候補をホストで実行/importしない。intakeのast.parseは静的なデータ検査であり、生成Pythonの実行ではない。
通常blob、cleanなpacket、原本保持、範囲、容量、標準ライブラリimportを検査する。

## 公開テストと受理

hooksを無効にしたローカルbundle fetch/checkoutで候補を受け取り、publicで実stdoutを公開例と照合する。
最大2回の公開検査とし、hidden利用後に候補を変更しない。

```sh
python3 -B scripts/skill_create.py public --run <run> --candidate-sha <full-sha>
python3 -B scripts/skill_create.py accept --run <run> --candidate-sha <full-sha>
```

acceptは完全SHAと2ファイルのhashを固定し、実行用の別コピーをread-onlyにする。
コピーとpacket原本のhashを各利用後・監査時にも照合する。
実行は既存固定image、networkなし、非root、read-only、CPU1、256MiB等の既存Sandbox内だけ。
機械実行は累計20分、逐次。監督はprepareからの壁時計でも20分以内に止める。API/Gemma呼出・キー参照・追加クレジットは0。

## 独立3セッション

実Codex subagentをfork_turns=noneで1つずつ起動し、作成会話・評価器・期待値・他セッション結果を渡さない。
許可されるホストToolは、専用CLIのread/use/respondだけ。全exec_commandは絶対workdirとrequire_escalatedを必須にする。
これはtrusted controllerのDocker接続用であり、container内の制限緩和ではない。

readはSKILL.mdとtask群だけを返す。taskのraw stdinはcontrollerが固定hashで束縛し、モデルは結果を作り直さない。
16KiB境界の空白をcontextに展開せず、入力JSONと実bytes数/hash・空白の説明を渡す。実スクリプトには原bytesを渡す。

```sh
python3 -B scripts/skill_create.py read --run <run> --trial 0
python3 -B scripts/skill_create.py use --run <run> --trial 0 --case mixed --request '{"operation":"run_aggregate"}'
```

各trialは、混在category・空・重複・16KiB境界・誤型・不正status・不正category・余分なキー・過大入力を実行する。
正常exit 0と契約どおりのexit 2を区別し、失敗を正常な空countsとして扱わない。
実行taskの最終返却先はrespond。実stdoutを末尾改行まで変更せず返し、チャット終了文は管理用受領報告だけとする。
respondは受領だけを返し、3試行終了前に正誤フィードバックしない。

routing taskは、元の要求に対して提示catalogだけから作成要否を選ぶ合成対照であり、ファイルを作成する操作ではない。
完全一覧に機能なし・同等機能あり・一覧不完全・作成権限不足を固定し、select_create/select_reuse/hold_evidence/hold_permissionを記録する。
常に新規作成を選ぶ動作を合格にしない。既存同等機能の本番実装を取り込む試験ではない。

## 一括判定と監査

```sh
python3 -B scripts/skill_create.py evaluate --run <run>
python3 -B scripts/skill_create.py audit --run <run>
```

3試行の実taskを終え、監督側が実際のセッション識別子をsessions.jsonへ新規保存してから1回だけ一括評価する。
実stdoutのschema/exit/期待値と、最終返却bytes/hashの一致を必須にする。欠損・timeout・不正出力を成功にしない。
assessment.lock後の追加提出や再採点を拒否する。監査は原本、両SHA、2ファイル、manifest、read/trace/response、report/checkpointを結合する。
個別入力・正解・trace・返却bytesはINTERNALとしてローカル保持し、PUBLIC候補と検査済み集計だけを本repo専用PRへ送る。
同一OS利用者の任意読取隔離は保証せず、trusted supervisorと最小受渡しを前提にする。

Harness判定はSTRENGTHEN。HSI-05と#34の隔離・hash監査を再利用し、2ファイル生成と集計出力を接続する。
失敗モードは不要な新規作成、不正入力の空結果化、候補差替え、自己申告だけの成功。発火は新規skill候補受取と利用時。
入力は固定catalog/契約/候補/実stdout/最終返却、出力は固定3試行の集計と監査。比較は決定論的。
コストは公開最大8回と本評価27回の逐次Docker、既存CI/Security/Reviewは代替しない。
同じ生成境界と返却保証を別実装で示せるときに再評価し、既存保証を削除・緩和しない。

LLMは承認済みCodexアプリ、ReadはPUBLIC packet/対象repo/Issue、Writeは本repo専用branch/PR。
人間の2026-10-28再計画と「マージしました。進めて下さい」に基づき実施する。
標準verify、関連回帰、Bash 5 Securityと、最終headのCI/CodeQL/正式レビューを確認する。
Merge・Issue Close・採用と失敗後の新runは人間判断。#36や#8の実装へ進まない。
