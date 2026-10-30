---
name: change-intake
description: Codexなどが作ったコード修正やスキルを、作った側の自己申告ではなく、ハーネスの受取・独立評価・承認付き模擬採用で確かめてから取り込む手順。AIが提案した修正やスキルを採用したいとき、改善の前後を比べたいときに使う。Dockerと段階ごとの人間承認が必要。
---

# AIが作った変更を取り込む

AIの「直った」「合格した」という申告では採用しない。ハーネスで受け取り、評価し、承認に結び付けてから使う。
対象は本repoのPUBLIC合成課題（fixture）だけ。実Hermes、`~/.hermes`、本番には使わない。

## 0. 使うかどうかを決める

毎回は使わない。次のどれかに当たるときだけ使う。

- AIが作ったコードやスキルを、評価済みとして残したい
- 修正の前後で、本当に良くなったかを比べたい
- 採用と、失敗したときの復旧まで確認したい

診断の結果が「直す必要なし」「既存で足りる」「根拠不足」「権限不足」なら、候補を作らずに止める（docs/manual-cycle.md の NO_CHANGE / REUSE / HOLD）。

## 1. 候補を受け取って検査する

変更の種類で、使うスクリプトと手順書を選ぶ。引数は各手順書に従い、推測で付けない。

| 種類 | スクリプト | 手順書 |
| --- | --- | --- |
| コード修正 | `scripts/generated_repair.py`（prepare / freeze / evaluate / audit） | docs/generated-repair.md |
| 既存スキルの再利用・修正 | `scripts/skill_reuse.py`（prepare / freeze / accept / read / use / respond / evaluate / audit） | docs/skill-reuse.md |
| 新規スキル | `scripts/skill_create.py`（上記に public を追加） | docs/skill-creation.md |

- 評価の課題・基準・評価器は、候補を作る前に固定する（freeze）。
- 生成側に hidden の課題、正解、評価結果を渡さない。
- 生成されたコードを、ホストで実行・importしない。実行は固定imageのDocker（networkなし、非root、read-only）だけ。

## 2. 独立して評価する

`scripts/evaluate_fixture.py`（bootstrap → freeze → gate → evaluate → audit）。手順は docs/independent-evaluation.md。

- 基準版・候補版・劣化版を同じ課題で比べ、PASS / HOLD / FAIL を出す。
- PASS は「承認待ち」まで。採用の許可ではない。
- 同じ hidden の結果を見て候補を作り直さない。やり直しは新しいrunで、人が判断する。

## 3. 承認して模擬採用する

`scripts/adopt_fixture.py`（prepare / submission / register / request / approve / execute / status / observe）。全体を通すときは `scripts/manual_cycle.py`。手順は docs/fixture-adoption.md と docs/manual-cycle.md。

- 承認は、候補のSHA・評価hash・対象・期限・操作に結び付けて人から取る。PRのMergeや、ほかの対象への承認を流用しない。
- 書き込む前に backup と intent を保存する。途中で失敗したり結果が不明になったりしたら、RECOVERY_REQUIRED で止める。lockを自動で外さない。
- 復旧も別の承認で行う。元のhashと回帰テストが通ったときだけ ROLLED_BACK にする。

## 4. 記録してPRにする

差分・評価hash・未確認の事項を同じSHAで記録し、steward スキルの順でPRにする。PUBLICな要約だけをGitHubに出す。正式レビューは `.github/pr-gate-review` が指定する種類（2026-10-30時点は `claude-code`）で行い、`scripts/check-pr-head.sh <PR番号>` が READY になってからマージを依頼する。候補を作ったAIと、レビューする担当は分ける（同じ会話でレビューしない）。

## してはいけないこと

- 合成課題での合格を、実Hermesや本番でも大丈夫という意味で扱う。
- 承認なしに採用・復旧を実行する。期限切れや別SHAの承認を使う。
- Docker の制限を緩める、ホストで生成コードを動かす。
