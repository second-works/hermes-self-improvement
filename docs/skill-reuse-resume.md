# Issue #34の停止記録と再開条件（履歴）

以下は第三run実施前の停止時点の記録である。その後、人間の「了承します」で再試行を承認し、[最終実証記録](issue-34-skill-reuse.md)へ進んだ。停止時点では実証未完了・PR未提出であり、品質合格を宣言していない。
Risk Tier: HIGH。元checkoutは操作せず、以下の独立checkoutとrunを保持する。

## 実施済みと停止原因

1. `hsi-issue34-controller-20261028` のrun `skill-9d1f21ebd7be74c083184838` は、実Dockerの7種gateと公開実行に成功したが、候補受理前に `AUDIT_BINDING` で停止した。専用adapterが既存監査にないイベント名を使っていた。
2. 人間の「再開して下さい」に基づき、別checkout `hsi-issue34-repair-20261028` でadapterを既存イベント名と結合先へ合わせた。元監査器・旧runは変更していない。実監査器を使う回帰で修正前失敗→修正後成功を確認した。コンテナ観測だけはmockなので、利用実証とは区別する。
3. 修正版 `5b3ec010e855ac7a30fb1c959252e4cc24bbd717` でrun `skill-5dc04f84780e323fb11ef7da` をfreezeした。実Docker 7種gate、公開実行、候補受理は成功した。候補の内容は初回生成から変更していない。
4. 履歴なし利用セッション `/root/skill_trial_0` はprimaryで `run_review` を選択したが、Docker接続に必要なsandbox権限を指定せず呼び出したため `ISOLATION_CLEANUP_FAILED` で停止した。実利用3試行・一括評価・auditは未実施。親の受渡し指示が必要権限を必須にしていなかったことが原因。
5. 停止後に権限付きの `docker ps -a` で残存コンテナ0を確認した。エラーが示したpending名とactive.lockは記録として保持し、再実行やlock解除はしていない。

PUBLIC候補・bundle・公開stdout・停止集計は `artifacts/skill-reuse/issue-34/` に保存した。
hiddenの入力・正解・traceは保存対象に加えていない。

- 最終候補SHA: `6a31dfe7c38fe3ed08760b0a82b933984372b813`
- 内容hash: `d391dc90267e2126af399a83664da2120904bfcd8df83d51e008cfa4e5c2b1da`
- スクリプトhash: `7d342aa1fc92afaeea8b7aee834650965b885f167975fd2d4f18e5c31ee80b6e`
- 生成1回、公開修正0回。初回候補 `0539237b7d41b6545bdbf16534d624e94aefabbf` と内容同一。新freezeの基準が異なるためcommit SHAだけが異なる。

標準verify 30件、adapter回帰8件、Bash 5 Securityは成功した。依存manifestなしのため依存監査は理由付き対象外。実アプリ利用評価の代替にはしない。

## 次の再開で行うこと

親Issue #31の「新runの再試行は人間判断」に従い、人間が新runを承認するまで追加の実評価を始めない。
承認後は第三の独立checkoutを用い、旧2 run/lockには触れない。
修正版の評価器と入力を新たにfreezeし、同じ内容hashの候補を受理する。候補を再生成・再調整しない。
新packetの基準の子孫commitにするためSHAの再固定は必要である。

履歴なしの3つの実Codex subagentを `fork_turns=none` で1つずつ起動する。
各利用担当の許可Tool設定を、以下の通り必須とする。

```text
Every tools.exec_command call, including read and use, MUST explicitly set
sandbox_permissions="require_escalated" and the exact absolute controller workdir.
Default sandbox execution is not an allowed transport. Do not try it first.
Use only the provided trusted adapter read/use commands. Never run review.py
on the host, change Docker restrictions, fetch images, or retry a failed use.
```

これはDockerの制限緩和ではなく、既存Dockerへ接続するtrusted controllerのホスト側権限指定である。
既存Sandboxのnetworkなし・非root・read-only・CPU/memory等は維持する。
各利用担当に渡すのはrun/trial、read/use入口、各条件のスキル・タスク・許可Toolだけである。
作成履歴・評価器・正解・他セッションの結果は渡さない。
3試行が完了するまで途中採点せず、一括evaluateとauditを実施する。
失敗・欠損・回収不能では再び停止し、同じrunで再実行しない。

成功した場合にだけ、同じPR headの標準verify・関連回帰・Bash 5 Security・CI・CodeQL・正式レビューを揃えて人間のMerge判断へ進む。
#35、本番登録、採用へ進まない。
