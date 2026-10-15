# Nine PRODUCT UI Standard v1

## 1. 目的と適用範囲

この標準は、案件ごとのUI設計品質を揃えるための最低契約である。特定の案件の色・フォント・レイアウトや、特定のフロントエンドframeworkを固定するものではない。

案件計画時にUI適用を確認し、UIがある場合にUI Levelと理由・参照を記録する。非UIのIssue本文にNONE欄を強制しない。既存のUI受入条件を対象外へ変更する場合は理由を残す。

| UI Level | 対象 | 適用する契約 |
| --- | --- | --- |
| `NONE` | CLI / API / Batchなど、利用者向けUIを持たない案件 | UI仕様と専門欄は原則不要。既存UI受入項目の対象外への変更は理由を記録する |
| `UTILITY` | 管理画面、個人ツール、内部ツール | 機能性、現在状態、入力結果、エラーと回復を確認する |
| `PRODUCT` | 一般利用者向けWeb / App | 本文書、UI Specification、Design Profile、`docs/design.md`、Visual/UI Acceptanceを適用する |

UIを持つ可能性があるのに分類できない場合は、AI/Codexが推測せず `NEEDS_DECISION` とする。

## 2. Nine PRODUCT UIの5原則

1. **User Goal First** — 画面ではなく、誰が何を達成すれば完了かを先に定義する。
2. **Current State is Visible** — ユーザーが現在の状態を判断できる。
3. **Next Action is Clear** — 主要画面で次の行動が明確である。
4. **Invalid States are Prevented Structurally** — booleanの組み合わせに頼らず、enum / union / schemaなどで不正状態を作りにくくする。
5. **Implementation Done != UI Accepted** — コード完成とUI/UX検収を分離する。

## 3. PRODUCT UI Specification

### 3.1 User / Context

- Target User
- Primary Goal
- Usage Environment
- Device Priority: `Mobile First | Desktop First | Equal`
- Expected Skill Level

### 3.2 Information Architecture

- Screen List
- Navigation
- Screen Hierarchy
- Entry Point
- Primary Flow
- Exit / Completion Point

主要操作は `Entry -> Action -> Result` を追跡できるようにする。

### 3.3 Screen Specification

主要画面ごとに次を定義する。

- Screen
- Purpose
- Primary User Goal
- Primary Action
- Secondary Actions
- Displayed Information
- Possible States
- Error Recovery
- Next Screen

### 3.4 Required UI States

案件に必要な状態を明示的に区別する。

- `LOADING`
- `READY/NORMAL`
- `EMPTY`
- `SUCCESS`
- `ERROR`
- `DISABLED`
- `UNAVAILABLE/PERMISSION_DENIED`
- `NEEDS_REVIEW`
- `UNKNOWN`

`UNKNOWN != ERROR`、`EMPTY != ERROR`、`UNAVAILABLE != FAILED` とする。状態を色だけで表現せず、文字、アイコン、構造、または説明を併用する。

## 4. Design Profile

PRODUCT案件では、要件とは別に実際の見た目を決めるDesign Profileを作成する。デザインそのものを全案件で固定せず、決定手順と最低品質を固定する。

### 4.1 デザイン決定の優先順位

1. 案件固有のVisual Reference（ユーザー指定URL、スクリーンショット、既存製品、ブランドガイド）
2. Design Research（案件に適した2〜3のDesign Direction）
3. Default Design System（案件固有指定がない場合の候補）
4. AI実装裁量（余白、一般的なレスポンシブ調整、明白なアクセシビリティ改善などの細部）

案件固有のVisual Referenceがある場合は、何を採用し何を採用しないかを記録する。重要なDesign DirectionはHuman Design Decisionで確定する。

### 4.2 Visual Referenceの記録

各Referenceについて、次を記録する。

```md
Reference A: <URL or screenshot>
Use:
- information architecture
- information density
- component hierarchy

Do NOT copy:
- brand colors
- logo
- illustrations
- copyrighted visual assets
```

複数製品の要素を組み合わせる場合も、ブランドや著作物を無批判にコピーしない。

### 4.3 Default Design System

固有のDesign SystemがないWeb PRODUCTでは、技術要件に適合する場合に限り次を候補としてよい。

- React / Next.js
- Tailwind CSS
- shadcn/ui
- Lucide Icons
- Project-specific Design Tokens

これは強制スタックではない。既存技術、案件要件、ブランドDesign Systemを優先する。

## 5. Information Hierarchy

必要に応じて `Summary -> Detail -> Evidence / History / Source` の順で情報を整理する。初期画面には判断とPrimary Actionに必要な情報を優先して表示する。

## 6. Interaction / Feedback

主要操作は次を追跡できるようにする。

`Action -> Processing -> Success/Failure -> Next Action`

長時間処理ではProcessing状態を表示する。削除、取消、上書きなどの危険操作は通常操作と明確に区別し、Confirmationは必要な場合にだけ要求する。

## 7. Responsive Design

PRODUCTは原則レスポンシブ対応とする。単純縮小ではなく、画面幅に応じて情報の優先順位を変える。

小画面でも原則として次を失わない。

- Primary Action
- Current State
- Critical Information
- Error / Recovery Action

## 8. Accessibility Minimum

最低限、次を確認する。

- semantic HTML
- keyboard operation
- explicit labels
- visible focus
- readable typography
- sufficient contrast
- status not represented by color alone

## 9. AI / Codex Design Boundary

Codex/AIは仕様にない重要UX判断を勝手に確定しない。次が未決定の場合は原則 `NEEDS_DECISION` とし、既存のDesign Decisionへ接続する。

- Primary screen structure
- Navigation model
- Primary Action
- Critical user flow
- Destructive action behavior
- Mobile/Desktop priority
- Major Design Direction

一方、承認済みDesign Systemに従う微細なspacing、一般的レスポンシブ調整、明白なアクセシビリティ改善は実装裁量としてよい。

## Component Decision Rules

PRODUCT UIでは、重要なcomponent / patternの選択を、見た目の好みではなく次のrule recordで追跡する。これは標準側の判断原則と最低品質を定義し、案件固有のvisual、brand、tokens、採用component、例外は案件 `docs/design.md` で決定する。

### Rule Record Contract

各ruleは次の順序で記録する。

- Rule ID:
- Condition: どの利用者、目的、選択肢、状態、画面幅、危険度が判断条件になるか。
- Decision: 条件から導くUI判断。
- Candidate pattern/component: 候補と、候補を選ぶ理由。特定libraryの採用を標準から強制しない。
- Verification: 実装後に確認する意味、状態、操作、Accessibility、またはVisual/UI Acceptance。
- Fallback: 条件や候補が不足し、重要UX判断を確定できない場合は `NEEDS_DECISION` として停止する。

数値閾値は根拠がある場合だけ記録する。案件特性で変わる判断は、閾値をglobal ruleへ固定せず、案件側の判断材料と例外を `docs/design.md` に記録する。

### Primary Action

- Rule ID: `PRIMARY_ACTION`
- Condition: 画面のPrimary user goalと、同時に提示する操作の優先順位を確認する。
- Decision: 最重要操作を一意にPrimaryとし、競合する同格Primary CTAを乱立させない。
- Candidate pattern/component: Primary button、link、または既存Design Systemの同等semantic component。
- Verification: `Entry -> Action -> Result` とPrimary Actionの意図が追跡でき、Responsiveでも失われないことを確認する。
- Fallback: Primary goalまたは優先順位が定まらない場合は `NEEDS_DECISION`。

### Selection Pattern

- Rule ID: `SELECTION_PATTERN`
- Condition: 選択肢の相互排他性、可視性、探索性、検索要否、入力頻度を確認する。
- Decision: まず単一選択か複数選択かを確定する。非排他的な少数候補はCheckbox group候補、多数または検索可能な複数選択はmulti-select候補とする。排他的な少数で同時比較する候補はRadio候補、既知の単一候補を省スペースで選ぶ場合はSelect候補、多数または検索可能な単一選択はCombobox候補とする。
- Candidate pattern/component: Checkbox group、multi-select、Radio、Select、Combobox、または案件Design Systemの同等semantic component。
- Verification: キーボード操作、label、単一/複数選択の意味、現在値、未選択、候補なし、選択数制約、エラー状態を確認する。
- Fallback: 単一/複数選択、排他性、候補の探索性を区別できない場合は `NEEDS_DECISION`。根拠のない選択肢数を閾値として固定しない。

### Destructive Action

- Rule ID: `DESTRUCTIVE_ACTION`
- Condition: 削除、取消、上書きなどの不可逆性、影響範囲、復旧可能性を確認する。
- Decision: 危険操作を通常操作と区別し、Confirmationは必要な場合だけ要求する。
- Candidate pattern/component: Destructive button、確認dialog、Undo、または復旧手順を持つ同等component。
- Verification: 誤操作防止、確認内容、キャンセル、成功、失敗、復旧または次の操作を確認する。
- Fallback: 危険度または復旧方法が定まらない場合は `NEEDS_DECISION`。

### Async Feedback

- Rule ID: `ASYNC_FEEDBACK`
- Condition: 処理時間、進行中に許可する操作、成功・失敗時の次の操作を確認する。
- Decision: `Action -> Processing -> Success/Failure -> Next Action` を状態として表現する。
- Candidate pattern/component: Progress、status、toast、inline message、retry、または同等のfeedback component。
- Verification: Processing中の二重実行、成功、失敗、retry、cancel、recoveryを確認する。
- Fallback: 処理中・成功・失敗・復旧の区別が定まらない場合は `NEEDS_DECISION`。

### Form Validation

- Rule ID: `FORM_VALIDATION`
- Condition: 入力境界、required/optional、形式、依存入力、送信時と入力時の検証を確認する。
- Decision: 境界で検証し、inline error、required/optional、修正方法を明示する。
- Candidate pattern/component: label、input、fieldset、inline error、summary、または同等form component。
- Verification: 正常値、境界値、空値、異常値、キーボード操作、error recoveryを確認する。
- Fallback: 入力制約またはエラー回復が定まらない場合は `NEEDS_DECISION`。

### State Mapping

- Rule ID: `STATE_MAPPING`
- Condition: データ取得、権限、空結果、エラー、未確認状態、利用不能状態を区別する。複数componentに影響する共有状態や業務状態では、状態の所有者と変更境界も定義する。
- Decision: `LOADING`、`READY/NORMAL`、`EMPTY`、`SUCCESS`、`ERROR`、`DISABLED`、`UNAVAILABLE/PERMISSION_DENIED`、`NEEDS_REVIEW`、`UNKNOWN`を意味どおりにcomponentへ割り当てる。共有状態はstate owner / source of truthを一意にし、状態変更は明示されたevent/actionと裁定境界を経由させる。
- Candidate pattern/component: skeleton、empty state、error message、status、disabled control、recovery actionなどの同等component。
- Verification: `UNKNOWN != ERROR`、`EMPTY != ERROR`、`UNAVAILABLE != FAILED`、および色以外のstatus cueを確認する。複雑なinteractionでは `Event -> Current State -> Transition -> Resulting State` を追跡できるようにし、不正、二重実行、cancel/complete競合、navigation中のasync完了、stale response、rapid repeated inputを必要に応じて検証する。
- Fallback: 状態の意味または遷移が区別できない場合は `NEEDS_DECISION`。

共有状態の変更はcomponent間で互いの内部状態を直接変更せず、案件で採用したowner / coordinator / reducer / store / state machine等の明示された境界を経由させる。ただし、これら特定のpattern、ライブラリ、frameworkを標準として強制しない。単純なlocal stateには不要な状態管理契約を過剰に適用しない。

### Responsive Priority

- Rule ID: `RESPONSIVE_PRIORITY`
- Condition: 画面幅、情報量、操作順、Primary Action、Current State、Critical Information、Recoveryを確認する。
- Decision: 小画面でもPrimary Action、Current State、Critical Information、Error / Recovery Actionを失わないように優先順位を定める。
- Candidate pattern/component: responsive layout、priority content、折りたたみ、scroll、または同等layout component。
- Verification: Device Priorityに沿って主要flowと重要情報が追跡できることを確認する。
- Fallback: 小画面で何を残すか決められない場合は `NEEDS_DECISION`。

### Accessibility

- Rule ID: `ACCESSIBILITY`
- Condition: semantic、keyboard、label、focus、typography、contrast、status表現を確認する。
- Decision: semantic HTML、keyboard operation、explicit labels、visible focus、readable typography、sufficient contrast、color以外のstatus cueを最低条件とする。
- Candidate pattern/component: native semantic element、accessible form/control、status、focus management、または同等component。
- Verification: キーボード、screen reader相当のlabel/status、focus、contrast、非色表現を確認する。主観的Visual品質はHuman Visual/UI Acceptanceで確認する。
- Fallback: Accessibility要件またはstatusの伝達方法が定まらない場合は `NEEDS_DECISION`。

### Conflict and Scope Boundary

- 標準Design RulesはUX原則、component semantics、Accessibility最低条件を定義する。
- 案件 `docs/design.md` は案件固有のvisual、brand、tokens、採用component、例外を定義する。
- 案件側の決定が標準の最低条件を満たす範囲では案件側の選択を尊重する。
- 標準ruleと案件設計が重要UXについて矛盾する、候補componentがない、または判断材料が不足する場合は暗黙PASSせず `NEEDS_DECISION` とする。
- この契約は `NONE` / `UTILITY` にPRODUCT UIの必須条件を過剰適用せず、特定Framework、component library、brandを強制しない。

## 10. Visual Review / UI Acceptance

PRODUCTではコードレビューとVisual/UI Reviewを分離する。

```text
Implementation Done
  -> Screenshot / Render
  -> Visual Review
  -> Fix
  -> UI Acceptance
  -> Product Acceptance
```

UI Acceptanceでは最低限、次を確認する。

- Primary user flow
- Primary Action clarity
- Navigation
- Loading
- Empty
- Error + Recovery
- Success/feedback
- Responsive behavior
- Accessibility minimum
- Design consistency
- `docs/design.md` conformity

「画面が表示された」だけではPASSにしない。Visual/UIの主観的品質は決定論的なCI booleanで代替せず、人間確認の証跡を残す。

## 11. 既存標準との整合

- Plan Reviewは [Plan Review Gate](plan-review-gate.md) を正本とし、UI Level / PRODUCT未決定事項の具体的統合は後続子Issue #95で行う。本Issueでは独立したUI Gateを作らず、責務境界と参照先を定義する。
- 検収は [Acceptance Verification](acceptance-verification.md) を正本とし、Visual/UI Acceptanceの具体的統合は後続子Issue #94で行う。本IssueではImplementation、Deploy、Product Acceptanceを混同しない責務境界を定義する。
- Harnessの追加・変更は [Harness Minimalism / ETCSLV](ai-development-harness-inventory.md) に従う。
- `NONE` に不要なUIチェックを課さず、`UTILITY` にPRODUCT相当の重いVisual Reviewを強制しない。
- 自動検証はsemantic HTML、lint、既知のaccessibility ruleなど決定論的な範囲を優先し、主観的なデザイン品質を自動合否にしない。
- 重要なUX判断、既存状態モデルとの衝突、Design Systemの強制につながる変更はDesign Decisionへエスカレーションする。

## AGENTSからの参照契約の移行準備

[#173](https://github.com/second-works/ai-development/issues/173)で保存した参照順序・適用範囲・停止条件を、Issue #177のAGENTS短縮後の正本として適用する。

## AI / Codex Reference Contract

PRODUCT UIの実装を開始するAI/Codexは、重要なUI判断を行う前に、次の順序でrepositoryとIssueの正本を参照する。

1. Framework Decision結果と正本文書（Frameworkを再選定しない）
2. UI Level Decisionと適用対象
3. Nine PRODUCT UI Standard / `Component Decision Rules`
4. 案件 `docs/design.md`（案件固有のvisual、brand、tokens、採用component、例外）
5. component / library固有docs（存在する場合）

- 参照順序、適用対象、案件固有の例外と根拠をIssueまたはPRで追跡できる状態にする。
- Framework Decision、UI Level、標準Design Rules、案件 `docs/design.md` のいずれかが欠落・矛盾・判断不能で、重要UX判断を確定できない場合は推測で補完せず `NEEDS_DECISION` として既存のDesign Decisionへ接続し、実装を停止する。component / library固有docsは採用する場合に参照し、採用を決めたdocsが取得できない場合だけ同じ停止条件を適用する。
- 案件 `docs/design.md` の決定は、標準Design RulesのUX原則とAccessibility最低条件を満たす範囲で尊重する。標準側と案件側の責務を暗黙に入れ替えない。
- `NONE` / `UTILITY` の案件にはPRODUCT UI用の必須欄やVisual/UI Acceptanceを過剰適用しない。Framework、component library、brandの採用をこの契約から強制しない。
