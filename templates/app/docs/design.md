# Product Design

<!-- PRODUCT案件では、Framework Decision完了後にこのファイルを案件リポジトリの docs/design.md として具体化する。 -->
<!-- 案件に不要な定型章は削除できる。ただし、PRODUCT UI標準と既存Gateが要求する判断・検証情報は残す。 -->

## Decision Summary

- Adopted:
- Primary reason:
- Impact:

## Alternatives

| Alternative | Rejection reason |
| --- | --- |
|  |  |

<!-- 比較判断に必要な場合だけ詳細を追加する。 -->

## Non-goals

- Out of scope:

## Framework Decision Boundary

- Framework Decision reference:
- Framework Decision result: `DECIDED / NOT_APPLICABLE / NEEDS_DECISION`
- Rendering / Application Architecture assumptions handed into UI design:

<!--
Framework DecisionはRequirements、Rendering Strategy、Application Architecture、Framework選定を扱う。
このファイルはFrameworkを再選定せず、UI Level、画面構造、navigation、visual direction、component、accessibilityを扱う。
ResultがNEEDS_DECISIONの場合はFramework依存のUI設計を開始せず、既存のDesign Decisionへ接続する。
-->

## Product

- Product name:
- Product summary:

## UI Level

- UI Level: PRODUCT

## Target User / Primary Goal

- Target User:
- Primary Goal:
- Usage Environment:
- Expected Skill Level:

## Device Priority

- Mobile First / Desktop First / Equal:
- Reason:

## Design Direction

- Selected direction:
- Reason:
- Human Design Decision reference:

## Visual References

### Reference A

- Source URL or screenshot:
- Use:
  - 
- Do NOT copy:
  - 

<!-- Referenceごとに、採用する構造と採用しないブランド・著作物を記録する。 -->

## Design System

- Existing brand or product system:
- Default candidates considered:
- Selected system:
- Why it fits:
- Not forced by this template:

## Typography

- Font family:
- Scale:
- Readability constraints:

## Layout

- Information hierarchy:
- Screen width behavior:
- Primary action placement:

## Spacing

- Base unit:
- Component spacing:
- Dense / relaxed areas:

## Color Semantics

- Primary action:
- Current state:
- Success:
- Warning:
- Error:
- Disabled / unavailable:
- Non-color cues:

## Components

- Navigation:
- Forms:
- Data display:
- Feedback:
- Destructive action:

## Component Decision Rules

PRODUCT UIのcomponent / pattern判断は、標準 `docs/product-ui-standard.md` の `Component Decision Rules` を参照して記録する。案件側ではvisual、brand、tokens、採用component、例外を具体化するが、標準のUX原則とAccessibility最低条件を暗黙に弱めない。

### Rule Record

- Rule ID:
- Condition:
- Decision:
- Candidate pattern/component:
- Verification:
- Fallback: 重要な判断を確定できない場合は `NEEDS_DECISION` として停止する。

### Project-specific Decision

- Selected rule / Rule ID:
- Project context:
- Adopted pattern/component:
- Reason and evidence:
- Exception or conflict:
- Design Decision / Issue reference:

案件特性で変わる判断は案件側へ記録する。根拠のない数値閾値、特定Framework、component library、brandをこのテンプレートから標準化しない。
## UI States

- LOADING:
- READY/NORMAL:
- EMPTY:
- SUCCESS:
- ERROR:
- DISABLED:
- UNAVAILABLE/PERMISSION_DENIED:
- NEEDS_REVIEW:
- UNKNOWN:

<!-- UNKNOWN != ERROR、EMPTY != ERROR、UNAVAILABLE != FAILED。状態を色だけで表現しない。 -->

### State Ownership / Transition

<!-- 複数component、業務状態、非同期処理、navigation、modal、destructive actionなどで記録が必要な場合に使う。業務状態は競合の有無にかかわらず所有者と遷移を記録する。単純なlocal stateは過剰に書かない。 -->

- State / domain:
- Owner / source of truth:
- Allowed events/actions:
- Allowed transitions:
- Invalid transition handling:
- Concurrent / async handling:
- Verification:

## Responsive Rules

- Breakpoints or behavior changes:
- Mobile information priority:
- Preserved Primary Action:
- Preserved Current State:
- Preserved Critical Information:
- Preserved Error / Recovery Action:

## Accessibility

- Semantic HTML:
- Keyboard operation:
- Explicit labels:
- Visible focus:
- Readable typography:
- Contrast:
- Status beyond color:

## Do

- Rule IDとConditionを参照して、DecisionとVerificationを記録する。
- 案件固有のvisual、brand、tokens、採用component、例外を根拠とともに記録する。
- 判断不能、矛盾、候補不足では `NEEDS_DECISION` としてDesign Decisionへ接続する。

## Don't

- 見た目だけでPrimary/Secondaryやcomponentを決めない。
- 標準の最低品質、semantic、keyboard、label、focus、contrast、status表現を案件都合で暗黙に弱めない。
- 根拠のない数値閾値、特定Framework、component library、brandを標準ルールとして追加しない.

## Open Design Decisions

- Decision:
- Options:
- Recommended option:
- Owner:
- Decision date:
- Escalation / Issue reference:
