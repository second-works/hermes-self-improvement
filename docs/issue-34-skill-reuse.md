# Issue #34: 既存スキル手順の修正と別セッション利用

Risk Tier: HIGH。PUBLIC合成スキルの手順生成、履歴なし利用担当、隔離実行と独立評価を扱う。
Issue #33 / PR #38の人間Merge後、2026-10-28の「マージしました。進めて下さい」で着手した。

**受入状態はHOLD / NOT_ACCEPTED。PR #39の正式レビュー指摘を修正中で、Merge可能ではない。**
旧評価器は操作とスクリプトstdoutだけを照合し、利用担当の最終返却を検査していなかった。
以下の旧reportのPASS/audit VERIFIEDは、その限定した検査結果として原bytesのまま保持する。
SKILL.md手順4の「実stdoutを変更せず返す」の実証には不足していた。
[レビュー指摘と分類](https://github.com/second-works/hermes-self-improvement/pull/39#discussion_r4396515148)はP2 BLOCKING。

旧runでは各条件の操作と実スクリプト出力は3/3一致した。adapter計測11.93秒、先行停止runを含む監督上限約574秒。
これらを最終返却契約の合格やIssue完了とは扱わない。
修正は候補SKILL.mdの変更ではなく、受渡しadapterによる最終返却の取得と実stdoutとのbytes/hash照合である。
新runの入力・評価器を事前freezeして、同じ候補内容で新しい3セッションを実測する必要がある。

## 原因と変更

既存スキルの原文はツール禁止とJSONリスト出力を指示し、正しい同梱スクリプトの実行と実stdout取得を案内していなかった。
履歴なしの生成担当は、独立PUBLIC packetの原文・公開再現例・既存一覧・同梱スクリプトとGit情報だけから原因を診断した。
完成した修正説明、評価器、tests、hidden正解、過去の生成会話は渡していない。

候補は既存のgithub-code-reviewを再利用し、SKILL.mdだけに許可されたrun_review操作、入力・権限確認、実stdoutの厳密JSON検査、失敗時停止を案内する。
正常出力はfindings/cpu_seconds objectで、モデルがfindingsやcpu_secondsを作り直さず実stdoutを保持する。
新規スキルやスクリプトの生成で回避していない。
同梱review.pyは#7の固定2操作適用版とbytesが一致し、hashは `7d342aa1fc92afaeea8b7aee834650965b885f167975fd2d4f18e5c31ee80b6e` のまま。

生成は初回1回、公開修正0回、候補内容1件。候補内容hashは全runで `d391dc90267e2126af399a83664da2120904bfcd8df83d51e008cfa4e5c2b1da` と一致する。
スキルのfrontmatter/nameを保持し、skill-creatorのquick_validateにも合格した。

## 事前固定と受渡し

評価器は `5b3ec010e855ac7a30fb1c959252e4cc24bbd717` のcommit済み版をfreezeした。
実Dockerの7種gateを確認し、固定image、networkなし、非root、read-only、CPU1、memory256MiBなどの既存制限を維持した。
候補スクリプトをホストで実行/importせず、新imageのpullやサービス変更も行っていない。

最終runは `skill-20f39038ce3782f579d101ba`。

| 識別子 | 値 |
| --- | --- |
| packet基準SHA | `dd923f2ef1026447f1a89d8f57b3d87a0c3ea93a` |
| 候補SHA | `4959610ae8efa8d954f0194d7393b6b5e54ae249` |
| manifest hash | `836fb6683ebdd1b52592a83ec4b39d26444a0aab928bb36de304f4856421a67a` |

freeze後に同一候補bytesを新packetの基準の子孫commitとして受理した。
SHA、cleanなpacket、SKILL.mdだけの差分、上限、元スクリプトhashを確認した。評価中に候補を変更していない。

利用担当は `fork_turns=none` の実Codex subagentを3つ逐次起動した。別のユーザー向けchatタブではなく、履歴なしの独立した推論セッションである。
旧試行で各担当に渡したのは専用read/use入口、trial番号と、その入口が返すスキル・タスク・許可Toolだけ。
作成会話、評価器、正解、他担当の結果は渡していない。
全Tool呼出しでホスト側の必要権限を明示し、Docker内の制限は維持した。

各試行のprimaryとsufficientでは、候補を読み、スクリプトを変更せず再利用して別入力の実stdoutを得る。
deniedでは実行権限不足、missingではpatch不足で停止し、修正前baselineでは実行手順がないため停止する。
3試行を終えるまで途中採点せず、機械のexit/stdout、厳密schema、原本・候補・入力hashを一括照合する。
採点にモデルの成功宣言は使用しない。ただし旧試行では管理用の概要だけを親へ返すよう指示してしまい、実stdoutを保持した最終返却の検査が欠けた。この点は未検証として訂正する。

## 先行2 runの停止と承認

[停止記録と修正済み受渡し](skill-reuse-resume.md)を保持した。
最初はadapterのイベント名が既存監査の結合契約に合わず、候補受理前に停止した。
別checkoutで実監査器を使う失敗再現と回帰を追加し、adapter側を既存イベントと結合ファイルへ合わせた。元監査器は変更していない。
次のrunでは利用担当への権限指定が不十分で、最初の実行呼出しが停止した。
その後に残存コンテナ0を確認し、両runとlockを保持した。
人間の「了承します」を受け、第三の独立checkoutで新runを実施した。候補内容は初回から変更していない。
各freezeで基準commitが異なるため候補SHAも異なるが、内容hashは同一である。

## 再現と保証範囲

受渡しadapterの操作は [skill-reuse.md](skill-reuse.md) を参照する。
候補bundleと集計証拠は `artifacts/skill-reuse/issue-34/` に保存する。
`candidate.bundle` から元版と候補の両SHA、SKILL.mdだけの差分、スクリプトbytesを再検査できる。

```sh
python3 -B -m unittest discover -s tests -p test_skill_reuse_artifact.py
python3 -B -m unittest discover -s tests -p test_skill_reuse.py
```

adapter回帰のコンテナ観測はmockであり、実利用の証拠とは区別する。
実利用traceには実stdout等を保持するが、正解を含めない。個別入力・正解・traceはローカルrunのINTERNAL資料とし、GitHubへ送らない。
PUBLIC報告は候補、公開再現結果、検査済み集計とhashだけ。
同じcontrollerと元runを保持すればauditを再実行できる。既存runのevaluate再実行やlock解除は行わない。
新規実評価は、人間判断の後に新runとfreezeを用意する。既存SHAを新しい基準へそのまま流用しない。

本実証は固定課題・固定回数の結果であり、一般的なスキル品質や本番Hermesでの再利用を保証しない。
同一OS利用者の任意読取を隔離する保証はなく、trusted supervisorと最小受渡しを前提とする。
候補は本番・グローバル環境へインストールしていない。
LLMは承認済みCodexアプリ、ReadはPUBLIC packet/対象repo/Issue、Writeは本repo専用branch/PR。
送信先allowlistは `second-works/hermes-self-improvement`。有料API・Gemma・認証・権限/課金/workflow変更は0。
Merge、Issue Close、採用は人間判断とし、#35へ進まない。復旧はPUBLIC追加のrevertを人間が判断する。

## ローカル検証

標準verifyのlint・setup 30件、旧版の専用adapter回帰8件、PUBLIC証拠同一性1件に成功。
既存generated-repair 19件、登録操作8件、evaluation 34件にも成功した（合計100件）。
Bash 5 Security PreflightはSECURITY_PASSED。依存manifestなしのため依存監査は理由付きSECURITY_NOT_APPLICABLE。
typecheck/buildは設定がないため理由付き対象外。warning/deprecationは観測していない。
最終PR headのCI・Security・CodeQL・正式Codex Reviewと残存リスクはPRへ記録する。

## レビュー修正の再実証条件

修正版は成功した各taskの最終結果をrespondへ届け、実stdoutのbytes/hashと一致した場合だけ成功に数える。
JSONリスト・再構成した値・返却なしをそれぞれ回帰で拒否する。respondは受領だけを返し、3試行終了前の採点はしない。
一括評価の開始時にassessment.lockを作り、欠損で停止した後の追加返却・再採点を拒否する。
旧runとlock、候補内容は維持する。修正版での実3試行はまだ実施していない。
親 #31の「新runの再試行は人間判断」に従い、修正・標準検証が完了した具体案について人間の承認を得てから新runへ進む。
