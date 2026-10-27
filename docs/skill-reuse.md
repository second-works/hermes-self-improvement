# 既存PUBLICスキルの手順修正と再利用

Issue #34では、正しい同梱スクリプトがある既存合成スキルの手順だけを修正する。
Risk Tier: HIGH。履歴なしのCodex利用担当への受渡し、隔離実行、固定評価を扱う。
本番インストール、新規スキル、スクリプト改修、モデルAPI、Gemma、権限・workflow変更は対象外。

## 課題と境界

`fixtures/generated_skills/github-code-review` は既存PUBLIC合成スキルの原文と、#7の行番号2操作を適用済みのPUBLICスクリプトを再利用する。
原文はツール禁止とJSONリストを指示し、同梱実行経路とfindings/cpu_seconds契約を案内していない。
生成担当には原文・公開再現例・既存一覧・不変スクリプトだけを独立packetで渡す。
候補に許す編集は `github-code-review/SKILL.md` の1ファイル、16KiB以下。
元スクリプトSHA-256は `7d342aa1fc92afaeea8b7aee834650965b885f167975fd2d4f18e5c31ee80b6e`。
既存fixtureや本番スキルは上書きしない。

adapterは既存Sandboxを使い、固定arm64 image、networkなし、非root、read-only、CPU1、256MiB等を維持する。
ホストで実行するのはtrusted controllerだけで、review.pyはwrite_newによる別コピーをread-onlyにしてDocker内で実行する。
新しいimageのpull、サービス変更、制限緩和を行わない。

## 事前固定

標準verify・関連回帰・Security・self-review後に準備用commitを作る。
独立checkoutで次を実行する。

```sh
python3 -B scripts/skill_reuse.py prepare
python3 -B scripts/skill_reuse.py freeze --run skill-<24hex>
```

prepareは既存7種Docker gateを実測する。freezeはcommit済み評価器、原本、script、環境、予算、3試行分の入力/正解をhashで固定する。
固定前や改変後には候補を受理しない。入力・正解の個別値はローカルのtrials.private.jsonに保持する。
freeze済みpacketの独立コピーだけを履歴なしの生成担当へ渡し、完成手順や正解は渡さない。
最終候補1件、初回生成と公開修正1回まで。機械実行20分、逐次、API呼出し/費用0。
adapterは処理時間の累計に加え、prepareからの壁時計20分でも厳しく停止する。

## 候補固定と別セッション

生成担当はpacketの基準の子孫commitとbundleを返す。hooks無効のローカルfetch/checkoutで受け取る。

```sh
git -c core.hooksPath=/dev/null -C runs/<run>/packet fetch --no-tags /absolute/candidate.bundle <full-sha>
git -c core.hooksPath=/dev/null -C runs/<run>/packet checkout --detach <full-sha>
python3 -B scripts/skill_reuse.py accept --run <run> --candidate-sha <full-sha>
```

受理は完全SHA、cleanなpacket、通常blob、差分1ファイル、上限、元script hashを照合し、candidate.mdをread-onlyに保持する。
受理は1回のみ。評価結果による候補調整は行わない。

利用担当は履歴を継がない3つのCodexセッションとし、各セッションにはtrial番号、read/use入口、候補スキル・タスク・許可ツールだけを渡す。
各trialにprimary、手順が十分なsufficient、実行権限なしdenied、patch不足missing、修正前baselineの5条件を固定する。
readはその条件のスキル・タスク・ツールを返し、読取hashを残す。生成会話と正解は渡さない。
useはoperationだけを持つJSON objectを受ける。run_review以外は固定の停止報告だけを許す。
任意コマンド、外部取得、追加キーを拒否する。権限・入力が不足する実行も拒否する。
モデルは実stdoutを受け取り、結果を作り直さない。1条件につきread/use各1回、逐次実行する。

```sh
python3 -B scripts/skill_reuse.py read --run <run> --trial 0 --scenario primary
python3 -B scripts/skill_reuse.py use --run <run> --trial 0 --scenario primary --request '{"operation":"run_review"}'
```

利用traceには読取hash、入力hash、候補hash、script hash、実exit/stdout/stderrとそのhashを記録し、正解は含めない。
これらの個別値はローカル保持し、PUBLIC報告は集計とhashだけとする。
監督側は実際の3セッションIDをsessions.jsonへwrite_newで保存する。自己申告の成功文は採点に使わない。
mock試験はadapter回帰に限定し、実Codexセッションを代替しない。

## 一括評価と監査

```sh
python3 -B scripts/skill_reuse.py evaluate --run <run>
python3 -B scripts/skill_reuse.py audit --run <run>
```

全3試行・全条件を終えてから一括評価する。途中結果で候補を変更しない。
実stdoutの厳密JSON、exit、状態、正解、両SHA、原本・候補・入力hashを照合する。
primary/sufficientの実行成功と、denied/missing/baselineでの適切な停止が各3件すべて成立した場合だけPASSとする。
欠損、timeout、故障、改変、回収不能、予算超過を成功にしない。
失敗ではactive.lockとrunを保持して停止する。既存run/lockの削除や再試行は人間判断とする。
auditはfreeze checkpoint、原本、両SHA、candidate、script、trace、セッション記録、report/checkpointを照合する。
同一OS利用者の任意ファイル読取を隔離する保証ではなく、trusted supervisorと最小受渡しを前提とする。

PUBLIC成果だけを対象repoの専用PRへ提出する。hiddenはINTERNALでローカル保持。
ReadはPUBLIC packet/対象repo/Issue、Writeは本repo専用branch/PR、LLMは承認済みCodexアプリ。
2026-10-28の再計画と人間の「マージしました。進めて下さい」に基づいて#34を実施する。
標準verify、関連回帰、Bash 5 Security、同一headのCI/CodeQL/正式Codex Reviewを確認する。
Merge、Issue Close、採用は人間判断。失敗時のPUBLIC差分revertも人間判断とする。
