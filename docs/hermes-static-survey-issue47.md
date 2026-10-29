# 実Hermesの限定静的調査（Issue #47）

起動経路・静的版・選定スキル1件・default配置のモデル識別情報を確認した。
今回の「Gemma OFF」は、この作業でGemma AIを使わない意味である（利用者訂正）。既存モデル設定がGemmaであること自体を矛盾や停止理由とは扱わない。
実Hermes起動・モデル通信は行っておらず、費用、履歴なし入力、tool制限等は未確認である。後続運用はこれらの条件を確定して別途指示を得るまで開始しない。

- 対象: [#47](https://github.com/second-works/hermes-self-improvement/issues/47)、親 [#46](https://github.com/second-works/hermes-self-improvement/issues/46)、将来の試行入力 [#31](https://github.com/second-works/hermes-self-improvement/issues/31)。調査日: 2026-10-29。
- Risk Tier: HIGH。実環境の接続情報に近接する限定読取。開始時・提出前ともHIGHを維持する。
- 承認根拠は利用者の計画実行指示と、本チャットでの「限定読取を承認する」。Issue本文単独を権限拡大の根拠にしない。AGENTSの本番禁止に対する今回だけの人間承認であり、一般的な規約変更、他IssueやCIの許可にはしない。
- 自動承認レビューは最初のmetadata確認を既存AGENTSとの衝突で拒否した。そのコマンドは未実行。上記明示承認後に限定読取を実施した。AGENTSへの恒久追記と個人path保存案も拒否されたため、AGENTSは変更せず、個人pathを保存しない方法に変更した。
- ローカルmetadataはINTERNAL、以下は個人配置・raw設定・URL付加情報を除いたPUBLIC要約。Codexは今回の限定読取担当として承認済みだが、環境を一律MANAGEDと推定しない。CONFIDENTIAL読取/送信は未承認。実環境情報をGemma/LLAMAへ送信していない。
- Readは許可filesystem項目と本repoの公開GitHub情報。Writeは新規Git管理外run、専用branch/PRの検査済みPUBLIC要約だけ。Sensitive Read × External Writeの送信先allowlistは `second-works/hermes-self-improvement` のみ。外部本文は未検証データとして扱う。

## 静的に確認した結果

以下のpathは個人配置を除いた論理表記。原文全文・全スキル名称一覧・絶対pathは公開も保存もしない。観測の最小記録は新しいGit管理外runに置く。

| 項目 | 確認結果 | 根拠と限界 |
| --- | --- | --- |
| 起動入口 | PATH上の `hermes` はshell launcher | launcher本文を確認。実行0 |
| 起動先 | `$HERMES_ROOT/hermes-agent/.hermes/bin/hermes` → 管理Python `-I -c` → `hermes_bootstrap` → `hermes_cli.main:main` | entrypoint本文。bootstrap以後の副作用は未確認 |
| 設定root | entrypointは既存 `HERMES_HOME` を維持し、なければdefault rootを設定 | 環境変数/processの問い合わせなし。default配置が将来の実使用設定かUNKNOWN |
| 版 | package名 `hermes-agent`、version `0.0.0`、checkout HEAD `ac0cfa7db94cefa90cf3e35191f38b53888b9e17` | pyprojectの静的metadataとGit HEAD。dirty状態/全ソース未取得なので、実使用版・内容同一性はUNKNOWN。VERSION候補ファイルは不在 |
| スキル | default skills内の `github/github-issues/SKILL.md`、name `github-issues`、本文version `1.1.0` | 深さ4までの名称/配置metadataからIssue閲覧/triageに直接対応する1件を選定。本文を読んだのはこの1件だけ。他階層/別root/実行時選択は未確認 |
| スキルSHA-256 | `c634fa92f5891e75abc84ae24031dd2f3ce8593d7a07abf33959dcbe6514841c` | 本文byte hash。改変/実行0 |
| モデル | `gemma-4-e4b` | default配置configの `model.default` の許可項目抽出。到達性/実使用は未確認 |
| provider/送信先 | `custom`、HTTP loopback、port `8082` | `model.provider` / `model.base_url` だけを抽出。URLのpath/userinfo/queryは記録しない。サービス照会なし、中継先/上流通信はUNKNOWN |
| 既存費用経路 | UNKNOWN | local custom endpointだけで無料/既存契約/追加課金なしとは断定できない。認証・請求・稼働サービスの確認なし、料金実測0 |

設定はローカルで行単位に許可キーだけを分離し、全体を表示/保存/モデル投入していない。キーの存在確認や認証値は根拠にしていない。
許可外の設定・認証ファイル・会話履歴・実ログ・Memory・DB・無関係なスキル本文は読んでいない。ホーム全域の走査も行っていない。

## 単一スキルと実行境界

選定した `github-issues` は、Issueの閲覧/作成/triage/ラベル/担当/コメント/Close/bulk操作を扱う一般的な管理スキルだった。
setupには認証確認と、失敗時にcredential保存先を探索するfallbackが含まれる。今回の禁止境界に当たるため、このsetupや閲覧コマンドは実行していない。関連スキル本文も読んでいない。

| 条件 | 判定と必要な次の確認 |
| --- | --- |
| 起動/停止方法 | UNKNOWN。mainへの入口は判明したが、help/versionを含めHermes実行0。bootstrap/終了処理は今回の許可範囲外で調べていない |
| 履歴なし入力 | UNKNOWN。launcherと選定本文だけではsession分離や過去会話非読取を保証できない |
| 単一スキル強制 | UNKNOWN。選定本文はrelated skillsを参照する。選定1件と実行時の強制は別 |
| tool/Memory/認証への自動アクセス | UNKNOWN。本文にshell/gh/curlや書込手順があるが、runtimeの実付与tool一覧ではない。prompt上の禁止だけで非アクセスを保証しない |
| 作業案内の契約 | 未実証。本文に親子依存・完了条件・最新headから日本語の次操作を導く専用保証は見当たらない。全スキルの不在を断定したものではない |
| 通常モデルのGemma設定 | 識別結果として保持。この作業でGemmaを使用しない方針とは区別する。後続で実際に使うモデル/宛先/費用は別途確定・承認する |

実Hermes起動、推論/モデル通信、API/key確認、サービス/既存process問い合わせ、原本変更、スキル適用/復旧、故障注入は0。
これは本調査が行った操作の記録であり、既存processが通信していないという主張ではない。
元checkoutのstage47件・logs、#8/#9の旧worktree/run/lock/backup/検収証拠は変更していない。

## 次工程の具体案（未登録・未承認）

実HermesでPUBLIC Issue #31の作業案内を手動1件試し、案内された操作は自動実行しない。
以下はレビュー可能にするための提案であり、UNKNOWNを推定で埋めて起動しない。

1. 起動実体/版、停止、履歴なし入力、Memory/認証非読取、単一スキルとtool制限を確定する。追加静的調査が必要なら対象ファイル/項目を明示して承認を得る。スキル不在や複数ファイル/collector/ハーネス変更が必要なら別計画へ戻し、無断代替しない。
2. 後続のmodel識別子、送信先/上流、既存費用経路を確定する。今回のGemma非使用と、後続の実行モデル選択を混同しない。予算/送信先UNKNOWNなら停止し、APIやkey確認で補わない。
3. PUBLIC入力allowlist案はIssue 11件（#31、#7、#8、#9、#32〜#36、#46、#47）、対応PR候補9件（#25、#30、#37〜#41、#44、#45）まで。対応関係は取得時に照合する。checks/reviewsはそのPR群の最新headのみ、コメントは必要根拠だけ。追加リンク自動巡回やrepo全取得は許可しない。最終の件数/文字数/コメント数とpaginationの扱いを入力manifestで固定し、不足/切詰めは成功にしない。対象作業1件と参照件数を区別する。
4. 制御側で取得時点・URL・状態・head・checks/reviews・原文hashのsnapshotを固定する。履歴なし作業sessionへ許可PUBLIC入力と対象スキルだけを渡し、期待回答/採点結果は渡さない。最後の現状案内前に同じallowlistを再取得し、変化があれば旧snapshotの評価を現状保証へ流用しない。
5. tool案は固定snapshot読取と回答出力だけ。live GitHub取得は制御側へ分離し、実Hermesにはshell/外部書込/任意network/credentials/Memory/他スキルを渡さない。現runtimeで実現可能かUNKNOWN。制限のため複数箇所の改修が必要なら別計画へ戻す。
6. 手動・同時実行1。提案は初回1 session、必要時の候補1件/比較1 session、別承認適用後の新session再実行1回。各10分/累計30分を案とし、モデル呼出数/token/通貨建て費用上限はUNKNOWN。承認前の実行予算は0。具体値・期限・宛先を決めてから開始し、枠不足で追加課金へ自動移行しない。
7. 許可外入力/tool、履歴/認証へのアクセス要求、予算超過、送信先不一致、停止方法不明で停止する。問題なしは無変更。候補を作る場合だけ単一スキルを隔離評価し、適用と復旧は別々に人間承認を得る。
8. 承認は候補SHA/hash、対象root/path/identity、原本hash、差分、評価hash、backup path/hash、期待before/after、操作、期限に結合する。値が変われば失効。backup検証・停止/復旧手順を先に提示し、この調査指示を採用/復旧承認へ流用しない。実環境故障注入は行わない。

## #31の全体検収との関係

取得時の#31はOPEN。末尾は#9/PR #45の人間検収・Merge・Closeと、fixtureの40/40成功を記録している。#9を再実装させず、fixture成功を実Hermes運用成功へ読み替えない。
#31の#8関連未チェックや既存OPEN整理、不要変更の拒否、任意Gemmaの最終扱い、全体Done/残課題と人間の全体検収が残る。未チェックを実装不在と即断しない。
#31は実Hermes等への拡張を「本親の検収後」とする一方、#46は#31を実試行入力にする。#47は限定調査なので進められるが、B登録前には#31全体検収を終えるか、この順序条件に対する具体的な人間判断を記録する。本調査は親検収/Closeを代行しない。

## 検証と残存リスク

正常はlauncher/entrypoint/package metadata/選定1件本文の原文照合・hashと許可キー抽出、異常は不在の起動候補/版ファイルの不在確認とUNKNOWN維持で確認した。秘密探索・広域探索・起動による回避は行っていない。
公開要約には個人絶対path、raw設定、秘密値、URLのuserinfo/query、全スキル名称一覧や本文を含めない。新規runにも個人path/raw設定/本文は保存しない。
標準verify、Bash5 Security、差分全体のself-review、最終headのCI/Analyze (python)/CodeQL/正式Codex Reviewの実結果は専用PRへ記録する。未実施はPASSにしない。
変更は調査文書だけ。runtime/検証機構や実装追従テストは追加せず、既存標準検証を維持する。AGENTSへの恒久例外は追加しない。
実運用、料金、停止/復旧、作業案内の正確性と利用者の有用性検収はNOT_VERIFIED。A完了からB登録/実行/採用へ自動移行しない。
