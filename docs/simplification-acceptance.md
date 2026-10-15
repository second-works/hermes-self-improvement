# 最小フローの実利用受入

親 [#168](https://github.com/second-works/ai-development/issues/168)、実装 [#185](https://github.com/second-works/ai-development/issues/185)。目的は、Nine標準のIssue生成とCodex実装に必要な入口を簡潔にし、安全な検証・レビューを保つこと。全projectや全モデルでの効果測定は範囲外。

## 実際のIssueから実装まで

以下は未登録の文書サンプルではなく、このrepoで最小テンプレートから登録して実装した子Issueである。各本文の7見出しからScope / Done / Verificationを読み、追加の人間による仕様説明を求めず実装した。通常のrepoルール・該当正本は併せて参照している。

| 最小Issue | 本文から読み取った実装契約 | 実際の結果 / 証拠 |
| --- | --- | --- |
| [#181](https://github.com/second-works/ai-development/issues/181) | Cloud Agent回帰・CI配線・記録だけ。実install設定とsuite削除は対象外。代替入口を先に成功させて旧重複を移す | [PR #182](https://github.com/second-works/ai-development/pull/182)。追加head `6da4ffd001d925cb9672cdc7496812a598763f21` のCI #1052 / Security #346成功後に移行。更新head `51ec4003d1333e88db6af23b5da74c9ff0521b3a` の29suite、CI #1056 / Security #348成功、レビュー指摘解消後merge |
| [#183](https://github.com/second-works/ai-development/issues/183) | 独立保証済みHarnessの文書suiteとCI参照だけ削減。他28suite・安全正本は保持。Gate削除は個別人間確認 | [PR #184](https://github.com/second-works/ai-development/pull/184)。提示差分を人間が個別承認。head `013b34ad75ba0e76c3698abf2a1394a15322baa0` の28suite、CI #1059 / Security #349成功、28直接stepもsuccess。レビュー指摘なし、merge `658d28ecf05e5b0f2badcae03a3907dd21a0bfc2` |
| [#185](https://github.com/second-works/ai-development/issues/185) | README・既存review-evidence回帰・受入記録だけ。PR前順序、実copyと生成verify、安全境界・既存Issueの扱いを確認する | 本変更。PR/最終head/CI/Security/Review/mergeの結果はGitHubの親 #168に記録する。事前に成功を仮定しない |

これらの非UI案件はFramework / UI / State等の空欄を持たない。Risk、安全境界、依存、独立したDoneとVerificationは各Issueに保存した。入力契約の例3件・負例13件は既存 [plan-to-issues suite](../tests/plan-to-issues/run-samples.sh) が確認し、実登録から実装までの証拠は上のGitHub履歴で追跡する。

## Reviewから直接修正まで

#181の [P2](https://github.com/second-works/ai-development/pull/182#discussion_r4176920600) は、Python shimを隔離PATHへ置くとgrep/sed/tr依存で失敗する問題だった。IN-SCOPE FIXとしてSkill/helperを起動せず再現し、実interpreterを解決してから隔離する修正と、対称Node・shim回帰を同じPR branchへ追加した。

修正前のshim fixtureはexit 1、修正後はexit 0。Bash不在・version失敗伝播・Python compile失敗時停止は保持した。更新head `51ec4003d1333e88db6af23b5da74c9ff0521b3a` のlocal / CI / Security成功、[Codex Review](https://github.com/second-works/ai-development/pull/182#issuecomment-5978562522)、返信とthread解決を確認してmergeした。plan-to-issues → 実Issue → Codex → PR → Review → Codexの直接修正を実施した範囲の証拠であり、他案件での判断精度まで保証しない。

## 配置・検証・安全境界

2026-10-05、Bash 5と一時projectで以下を実行した。対象は本PRの作業treeで、最終headに対応するlocal / CI / Security / Review結果はPR本文と親 #168に記録する。

- guideの[実copyコマンド](template-guide.md#最小agentsと参照先の配置)を実行し、AGENTSの参照先と原本資産の配置を確認。再実行は非成功となり既存AGENTSは非変更。project固有designは案件時に作成する。
- 生成projectへ原本の `scripts/verify.sh` と4工程fixtureを配置。正常時はlint → typecheck → test → buildの順で成功。lintをexit 17にした異常時は17を伝播し、後続3工程は実行されなかった。一時projectはcleanup済み。
- 配置後に安全正本test-design.mdを欠落させる負例では参照欠落を検出。コピーだけでproject固有CI・Secrets・repo設定が完成したとは扱わない。
- READMEのPR前順序は [既存review-evidence suite](../tests/review-evidence/run-samples.sh) で正常と3負例（self-review欠落、PR先行、検証不能停止欠落）を検査する。これは文章上の順序回帰であり実装者の判断を代替しない。
- Security Preflight、Review判定、read-only収集、State/Deploy identity、最小入力、安全境界等の残存28suiteを実行する。Security workflow、contents: read、timeout 10分は維持した。安全正本の停止条件と参照は原文照合する。
- Production / Deploy / Secrets / 権限 / 課金 / 公開 / repo保護操作は実施しない。今回の検収対象は開発テンプレートであり、実アプリの本番DeployやVisual/UI Acceptanceは対象外。

## Plan vs Reality

予測は、最小7項目で範囲・完了条件・検証を理解でき、安全な同一PR修正まで進められることだった。このrepoの3子Issueでは追加の仕様質問なしで進め、#181の指摘を同じbranchで修正した。READMEは9,127から5,190 bytes、AGENTSは52,476から5,325 bytesへ縮小した。自己管理専用Harness検査345行・CI stepは独立保証後に個別承認を得て削減した。

失敗した前提は「代替回帰成功だけでGate削除を適用できる」こと。自動承認レビューは親Issueの個別確認境界を要求し、提示差分の承認後に進めた。またSecurity Preflightはindexに残る削除前ファイルを走査して停止したため、対象差分をstageしてから再検証した。Security処理は変更していない。

短縮後も配置先docsの欠落や現在のheadに対応しない検証結果は危険であり、常駐本文を短くすることと保証の削除を分離する。一般的な可読性や処理速度の優位性、全projectへの適合は測定していない。ここではこのrepoのIssue単位の実装可能性、サイズ削減、回帰保持を成功条件とした。

## 既存Issueの再判定と残課題

2026-10-05にGitHub本文・状態を再取得して判断した。以下のIssue/PRは本親の子Issueではなく、自動close/mergeしない。

| 対象 | 判断 / 追跡 |
| --- | --- |
| [#157](https://github.com/second-works/ai-development/issues/157) | 継続。#158〜#160の実効的修正を維持し、独立するmain保護課題をこの簡素化完了で解決扱いにしない |
| [#161 / PR #167](https://github.com/second-works/ai-development/issues/161) | 6直接stepの目的は#181へ統合。元の6suiteはHarness経由で実行済みだった。追加の全入口登録メタ検査は不採用、旧Issue/PRは統合によるclose候補として人間判断まで保持 |
| [#162](https://github.com/second-works/ai-development/issues/162) | PR前self-review・修正後再verify・停止責務を#185へ統合。現headの検証成功後に統合によるclose候補として扱い、人間による整理まで保持 |
| [#163](https://github.com/second-works/ai-development/issues/163) | 独立継続。main保護の調査・設定承認・残存リスク判断は本Issueの承認外。過去のprotected=falseや403を現在の観測として再利用しない |

残る文書contractには安全責務が含まれ、分類だけで削除しない。別の自己管理検査の整理は新たな責務確認と承認の対象。今回の実行ログに新たなwarning / deprecationは観測していない。

親Closeは [5項目の完了確認](parent-issue-completion.md) に従う。人間は指摘解消・現head検証成功後のmergeと親 #168完了までの継続を委任した。人間が実際にREADMEを目視評価したと代わりに記録せず、実装・実利用証拠・残課題・委任された判断条件を親Issueへ照合して最終判定する。
