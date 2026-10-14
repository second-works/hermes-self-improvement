# 計画書の作り方（会話 → テンプレ → 門番）

## Decision

- **採用:** 方針は会話で固め、計画書本文はテンプレへ転記する。README には手順の全文を置かない。
- **主要理由:** README は地図、Plan Review は実装してよいかの判定、この文書は人間が計画書を書く手順。同じ説明を3箇所に増やさない。
- **影響:** 計画書の厚さは案件の危険度で変える。記入例の行数を毎回の必須量としない。

## Non-goals

- Plan Review Gate、Framework Decision、子Issue品質チェックの置き換え
- 計画書の固定章立ての新設（必須なのは判断の中身であり、見出し名の完全一致ではない）
- 一問一答の強制、計画書の全面書き換え
- 見本の Framework を Nine 標準として固定すること

## 文書の分け方

| 文書 | 役割 |
| --- | --- |
| [README](../README.md) | リポジトリの地図。ここへ手順の全文は書かない |
| この文書 | 会話から計画書にする手順と依頼文 |
| [Plan Review Gate](plan-review-gate.md) | Issue化前の門番（PASS / NEEDS_DECISION / NOT_APPLICABLE） |
| [記入例（Web Todo）](../templates/planning/web-todo-app-plan.sample.md) | 埋まった状態の学習用。丸写しの正本ではない |

---

## 手順

```text
会話で方針（目的・範囲・やらないこと）
  ↓
テンプレに沿って計画書化（未決は推測で埋めない）
  ↓
Framework Decision
  ├─ NEEDS_DECISION → 確認して計画を更新 → 再判定。Framework依存のIssue化は停止
  ├─ DECIDED / NOT_APPLICABLE → 次工程
  ↓
UI Level Decision / PRODUCT前提整理
  ├─ NEEDS_DECISION → 確認して計画を更新 → 再判定。UI依存のIssue化は停止
  ├─ NONE / UTILITY / PRODUCT → 次工程（PRODUCTは7項目が COMPLETE）
  ↓
Plan Review Gate
  ├─ NEEDS_DECISION → 確認して計画を更新 → 再Review
  ├─ PASS → 親Issue / 子Issue
  └─ NOT_APPLICABLE → 省略理由を記録 → 必要ならIssue
```

会話ログを正本にしない。決まったことだけ計画書へ移す。

### 1. 会話で方針を揃える

最初は箇条書きでよい。最低限、次が口頭またはメモで揃うまで計画書化を急がない。

- 何を作るか、なぜ、誰が使うか
- 今回やること / やらないこと（Non-goals）
- 成功したら何が起きているか
- ログイン・サーバー保存・公開の要否（未決なら未決のまま）

AI が Framework 名から話し始めたら止める。順番は **要件 → 画面の出し方 → アプリの形 → 最後に Framework**。

### 2. テンプレで計画書にする

方針が見えたら、次のように依頼する。計画書化のあとにすぐ Issue 化せず、手順 3〜6 を経る。

> 今までの方針で、Nine の計画書の作り方（`docs/plan-authoring.md`）と関連テンプレに沿って計画書を作成してください。  
> 会話で決まっていない欄は推測で埋めないでください。  
> テンプレ上必要だが未決の項目は、候補案・主なトレードオフ・推奨案を出して確認してください。  
> 重要判断が残る場合は `NEEDS_DECISION` とし、Issue 化しないでください。  
> 対象外の項目は空欄にせず、対象外である理由を書いてください。

「確認してください」だけだと AI が埋めてしまうことがある。**推測で埋めない** を明示する。

### 3. Framework Decision を先に確定する

新規 Web / UI、または描画方針・構成・Runtime・配備が変わる案件では、[Framework Decision](architecture/framework-decision.md) を Plan Review より前に完了する。順番は **要件 → 画面の出し方 → アプリの形 → Framework**。`NEEDS_DECISION` の間は Framework 依存の計画・Issue化・実装を止める。CLI や文書のみなら理由付き `NOT_APPLICABLE`。

### 4. UI Level と PRODUCT 前提を確定する

[PRODUCT UI Standard](product-ui-standard.md) に従い `NONE` / `UTILITY` / `PRODUCT` を決める。分類できない、または PRODUCT の7項目が未完なら `NEEDS_DECISION` とし、Issue化を止める。

### 5. 確認への答え方

| 答え | 使うとき |
| --- | --- |
| 今決める | 骨格が決まる話（保存場所、ログインの有無、画面の有無） |
| 今回はやらない | Non-goals に理由付きで書く |
| 後で人間が決める | `NEEDS_DECISION` のまま止め、Issue 化しない |

「よく分からないからお任せ」は、技術選定や認証など実装の骨格が変わる話には使わない。

### 6. 門番を通してから Issue 化する

Framework Decision と UI Level が `NEEDS_DECISION` でないことを確認してから Plan Review する。依頼文の正本は [Plan Review Gate の標準利用方法](plan-review-gate.md#7-標準利用方法)。

子Issueのテスト6観点まで計画書に全部書かなくてよい。計画では分割と依存、詳細は子Issueテンプレート。

---

## 計画書に必要な中身（最低）

章の名前より、門番が止まらないことが目的。詳細な停止条件は [Plan Review Gate](plan-review-gate.md)。

**どの案件でも書く**

- Decision（採用、理由、影響）、Alternatives（案と却下理由）、Non-goals
- 要件、成功条件、失敗条件、失敗時の挙動
- 依存と境界（外部API、保存、入力）
- セキュリティ上の制約、Risk Tier（`LOW` / `MEDIUM` / `HIGH` と理由）

**計画書とセットで決める入力**

- Framework Decision: `DECIDED` / `NOT_APPLICABLE`（理由必須） / `NEEDS_DECISION`（ここで停止）
- UI Level: `NONE` / `UTILITY` / `PRODUCT` / `NEEDS_DECISION`
- PRODUCT なら画面骨格、遷移、主操作、主フロー、破壊操作、端末優先、デザイン方針
- NONE / UTILITY なら PRODUCT 用チェックは `NOT_APPLICABLE`

**公開・データを残す／検収**

- Deployment 項目は不要でも理由を書く。Merge は本番公開ではない
- 検収計画（実利用シナリオ、成功／失敗、検証環境）。`Implementation Done` と `Product Accepted` は別

対象外は消さず理由を書く。誤字や局所修正は Plan Review を `NOT_APPLICABLE` にできる。

---

## 厚さの目安

| 案件 | 計画の厚さ |
| --- | --- |
| 文言だけの修正 | 省略理由つき `NOT_APPLICABLE` で足りることが多い |
| 既存仕様の小さな修正 | 目的・範囲・成功条件・Non-goals が中心 |
| 新規 Web / 画面あり | Framework、UI Level、保存、検収まで会話で揃える |
| 認証・本番・破壊的変更 | 安全境界と公開方法を厚くする。Risk は `HIGH` |

Web Todo の記入例は PRODUCT 新規の「埋まった例」であり、毎回の分量ノルマではない。

---

## 関連正本

- フロー全体: [Nine標準AI開発フロー](nine-standard-ai-development-flow.md)
- 技術選定: [Framework Decision](architecture/framework-decision.md)
- 検収: [Acceptance Verification](acceptance-verification.md)
- 公開: [Deployment / Release Design](deployment-release-design.md)
- 子Issue MUST: [Issue Quality Check](issue-quality-check.md)
