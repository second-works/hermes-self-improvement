# Framework Decision

## Decision Summary

- Adopted:
- Primary reason:
- Impact:

<!-- 判断完了後に記入する。RequirementsからFrameworkまでの判断順序は変更しない。 -->

<!--
新規Web案件またはFramework再選定時に、このファイルを案件リポジトリの
docs/framework-decision.md として具体化する。
先に要件を記録し、特定Frameworkを前提に欄を埋めない。
判断に不要な補助項目は対象外理由をまとめて記録できるが、Completion Checklistの必須情報は残す。
-->

## Record

- Decision owner:
- Decision date:
- Related plan / Issue:
- Standard reference: `docs/architecture/framework-decision.md`

## Applicability

- Framework Decision is applicable: Yes / No
- Reason:

<!-- CLI、library、文書のみの変更等でNoの場合は、ResultをNOT_APPLICABLEとして理由を残す。 -->

## 1. Requirements

### Product / User

- Target users:
- Primary use cases:
- Public pages:
- Authenticated experience:
- Content-centric / application-centric:

### Quality / Operations

- SEO / metadata / crawler requirements:
- Performance and initial rendering requirements:
- Accessibility or device constraints relevant to architecture:
- Expected traffic / scaling constraints:
- Team skill / maintenance constraints:

### Runtime / Deployment

- Required runtime:
- Runtime restrictions:
- Deployment / hosting target:
- Managed hosting constraints:
- self-host portability requirement:
- Acceptable vendor lock-in:

## 2. Rendering Strategy

- Selected strategy: `SSG / SSR / SPA / HYBRID / NEEDS_DECISION`
- Why it follows from Requirements:
- Route or page boundaries when hybrid:
- Initial data and hydration requirements:
- Rejected strategies and reasons:

## 3. Application Architecture

- Selected architecture: `STATIC_CONTENT / SPA / SPA_WITH_API / FULL_STACK_SSR / OTHER / NEEDS_DECISION`
- UI / API boundary:
- API co-located or separated:
- Server-side functions actually required:
- Data and authentication boundary:
- Why it follows from Rendering Strategy:

## 4. Framework Alternatives

| Candidate / version constraint | Requirements fit | Rendering fit | Architecture fit | Runtime / hosting fit | Portability / lock-in | Operational complexity | Decision and reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |

<!-- 候補の採否と主要理由はこの表だけに記録する。候補が一つだけの場合は、他候補を比較しない理由をDecision and reasonへ記録する。 -->

## 5. Decision

- Result: `NOT_APPLICABLE / DECIDED / NEEDS_DECISION`
- Selected Framework:
- Selected version or constraint:
- Adoption reasons:
  -
- Known risks and mitigations:
  -
- Conditions that would invalidate this decision:
  -
- Re-evaluation trigger:

## Non-goals

- Out of scope:

## 6. Open Decisions / Escalation

- Unresolved item:
- Options and trade-offs:
- Recommended option:
- Framework-dependent work to stop:
- Allowed framework-independent investigation:
- Design Decision owner:
- Design Decision date:
- Escalation / Issue reference:

<!--
重要な前提が未決定、または複数候補のtrade-offに人間判断が必要な場合は
ResultをNEEDS_DECISIONとする。AIが暗黙に候補を採用せず、Framework依存の
計画・UI設計・Issue化・実装を停止して既存のDesign Decisionへ送る。
-->

## 7. Handoff

- Inputs handed to UI Level / Product Design:
- Inputs handed to Plan Review:
- Inputs handed to Deployment / Release Design:
- Inputs handed to Security review:
- Framework-specific assumptions that must not be duplicated as new policy:

<!--
Framework Decisionはrendering、application architecture、Framework選定を扱う。
画面構造、navigation、visual direction、component、accessibilityは案件の
docs/design.mdで扱う。Deployment、Security、Acceptanceの既存Gateを置き換えない。
-->

## Completion Checklist

### All results

- [ ] Applicability and reason are recorded
- [ ] Result is one of `NOT_APPLICABLE / DECIDED / NEEDS_DECISION`
- [ ] Existing UI, Deployment, Security, and Acceptance responsibilities remain separate

### When `NOT_APPLICABLE`

- [ ] The reason Framework selection cannot affect the implementation result is recorded

### When `DECIDED`

- [ ] Requirements precede Framework selection
- [ ] Rendering Strategy is decided
- [ ] Application Architecture and API boundary are decided
- [ ] SEO, public/auth focus, runtime, hosting, portability, and operations are evaluated or excluded with reasons
- [ ] Adoption and rejection reasons are recorded

### When `NEEDS_DECISION`

- [ ] Unresolved items and candidate trade-offs are recorded
- [ ] Framework-dependent work to stop is recorded
- [ ] A Design Decision / escalation reference is recorded
