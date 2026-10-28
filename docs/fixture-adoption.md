# PUBLIC fixtureの承認付き模擬採用と復旧

Issue #8の制御側CLIは、独立評価済みの#33候補1件を登録済みfixtureへ採用し、故障時に元版へ復旧する。
Risk Tier: HIGH。対象への書込と人間承認、部分適用、再起動時の復旧を扱う。最終Merge、模擬採用、復旧の承認はそれぞれ独立している。

対象は `runs/<controller>/fixtures/<target>/scripts/review.py` のPUBLIC合成fixtureだけ。
候補は `e3153fec973051b28178df0656db05d2a3ffae84`、基準は `65c53babda8f31405d54941e900c2d3987efa4b1`、独立評価hashは `e15519cd9488daa211d51fedb1d7f2a804eb38952a9e915211fc3d3934874183`。
#35のMergeとPUBLIC評価証拠を依存の完了根拠とし、元版が存在する#33を採用・復旧の対象に選ぶ。
生成、hidden再評価、#9、Gemma、本番採用を追加しない。

## 提示と承認

`python3 -B scripts/adopt_fixture.py --area <絶対controller path> prepare` は、PUBLIC bundleの基準・候補SHA、通常blob、差分allowlist、内容hash、既知の独立評価hashとPASSを照合する。
`packet.json`、`diff.patch`、元版・候補のコピーを保存し、`submission` が検査済みpacketを表示する。
PR提出用の同一packetと差分は `artifacts/fixture-adoption/issue-8/` に固定する。
GitHubへの書込機能は持たず、人間が内容を確認し、本repo専用PRへの提出を明示する。提出者は通常のlocal→CI→Security→CodeQL→正式Codex Reviewを通す。
実装依頼による専用PR提出の許可をfixture採用の許可へ流用しない。

制御側がfixtureを基準bytesで用意し、`register --environment <id> --target <id> --root <absolute root>` を実行する。
登録はenvironment/target/canonical root/device/inode/versionの不変対応で、正規直列化したSHA-256がroot_binding_hashとなる。
同一rootの別ID登録は拒否する。登録root差替え時は新targetと新承認が必要。

`request --target <id> --operation ADOPT --actor <human-id> --expires-at <timezone付き日時>` は**未承認の下書き**だけを表示する。
承認期限は発行から最大24時間。候補SHA・評価hash・environment/target/root/root_binding_hash/path・基準SHA・期待前後hash・観測現在hashを固定する。
登録時に保存した実在backupの参照・hashも採用票へ固定する。人間が全内容を確認した後、制御側に下書きのrequest objectを保存し、`approve --request <controller内のファイル> --confirm-request-hash <request hash>` を実行する。
承認の保存だけでは書き込まない。`execute --approval-hash <hash>` が保存票を再照合してから書き込む。
JSON票は署名された本人証明ではなく、trusted supervisorによる明示操作の記録である。生成workerへregistry/approval/controller directoryを渡さない。
同一OS利用者の任意改変やroot権限からの保護は保証しない。

## 永続化と停止

一度に1操作をOSの排他lockで実行する。別にtargetごとの永続intent-lockを保持し、完了や期限切れで自動削除しない。
採用前に元版backupをfsyncし、対象と承認を含むintent-lockとADOPTINGイベントを永続化してから書き込む。
書込はno-followで開いた親directoryに新しい通常ファイルをfsyncし、renameして親directoryもfsyncする。
symlink・特殊ファイル・hardlink・過大ファイル・path逸脱・古い票・別対象・改変された評価/候補を拒否する。
対象root/pathを直前にも照合し、書込後はhashと固定Docker回帰を確認してADOPTEDにする。

書込開始後の失敗・不明な結果はRECOVERY_REQUIREDとなる。
再起動後の未完ADOPTING/ROLLING_BACKもRECOVERY_REQUIREDと判定し、`status --target <id>` が再起動検出を追記する。
journalが欠如しても永続intent-lockがあれば新規採用を許可しない。intentの復元証拠がない場合は自動復旧も行わない。
イベントはsequence/前イベントhash/UTC/state/承認hashを持ち、破損・途中の切断を拒否する。監査hashは外部の検査済み記録へも残し、完全な改ざん防止とは呼ばない。

`observe --target <id>` は採用後のhashと回帰を再確認し、劣化をRECOVERY_REQUIREDにする。
復旧の下書きは `request --operation ROLLBACK` で、同一対象と候補・評価に加え、観測した現在hash（通常ファイル欠如ならnull）、元版hash、backup hash、元intent hashを固定する。
symlink等で現在状態が不明なら承認も復旧も進めない。
復旧票は最新観測イベントhashにも結び付け、実行票は1回の試行で消費する。別の人間承認後にROLLING_BACKを永続化し、現在状態とbackupを再照合して元bytesを戻す。
元hashと回帰が両方成功した場合だけROLLED_BACKにする。復旧失敗はRECOVERY_REQUIREDを維持し、新しい観測・明示承認なしに再試行しない。

## 検証と保証範囲

`python3 -I -B tests/test_adoption.py -v` は合成承認票・実filesystem・実プロセス終了で承認境界と復旧を検査する。回帰callbackはテスト用で、候補実行や人間検収の証拠ではない。
`python3 -I -B tests/run_adoption_docker.py <新規controller絶対path>` は合成承認票で、正常採用、別targetの劣化、部分書込とプロセス終了、復旧を実Dockerで検査する。
失敗run/lock/backupは保持し、同じareaの再初期化や自動unlockをしない。
生成候補は固定image・networkなし・非root・read-only・資源制限の既存Sandboxだけで実行する。image pull、サービス変更、ホスト実行はしない。
採用回帰は#33の公開10件、元版回帰は既知の正常入力5件。元版の拒否契約の既知欠陥を直したと主張しない。
候補実行のsnapshotとPUBLIC結果はcontroller配下のcheck directoryに保持する。
固定CIは既存setup試験だけで、追加ローカル/Docker試験をCI実行済みとは記載しない。

人間の実操作検収には、自動試験とは別controller/targetを準備し、候補・評価・root binding・期待hash・backup参照・期限・操作を具体化して提示する。
採用と故障注入/復旧は別targetで行う。復旧の承認は故障後に観測した現在状態へ改めて結び付ける。
人間検収未実施ではIssue #8を完了、READY_FOR_HUMAN_MERGE、Product Acceptedにしない。

情報分類はPUBLIC候補/集計/fixtureのみ。LLMは承認済みCodexアプリ。Readは本repoとIssue、外部Writeは検査済みPUBLICを本repoの専用branch/PRだけ。
今回の実装・自動試験・専用PRはユーザー指示の範囲。機密入力、hidden原本・個別trace、認証情報、本番、~/.hermes、モデルサービス、有料APIを扱わない。
Production Release/Full-System Security Auditは対象外（Release工程なし、PUBLIC fixtureの手動実証のみ）。本番投入には別計画と人間判断が必要。

Harness判定はSTRENGTHEN。既存評価は候補の品質と隔離を保証するが、承認対象違い・部分書込・再起動での二重採用を防がないため、本制御を追加する。
入力は固定packet・制御側registry・人間票、出力はfixture実体と永続監査。判定はhashと状態で決定可能、実行コストはPUBLIC Docker回帰10件/5件と確認操作。
同等の承認binding・永続intent・停止/復旧保証が実証された代替へ移行する際に再評価し、既存評価やSecurity Gateを削除しない。

## Issue #8 検証記録（2026-10-29）

[PUBLIC集計](../artifacts/fixture-adoption/issue-8/synthetic-results.json)は合成承認票による実Docker検証の結果である。
normalはADOPTED、degradationとcrashはRECOVERY_REQUIREDから合成の復旧承認を経てROLLED_BACK。候補/元版hashが一致した。
採用2回の公開各10件と復旧2回の元版各5件、計30件を固定imageで実行し全件成功。新規image取得、サービス変更、ホスト候補実行、API/Gemma/キー確認は0。
ユーザーがDockerを起動した後に接続を確認した。最初の未接続runはRECOVERY_REQUIREDのまま保持し、その失敗を復旧成功に含めない。
最初の接続済み統合試験で、保存intent-lockを登録情報と誤認する失敗を検出した。登録レコードとlockを区別し、採用後の別target登録の回帰を追加して修正した。
この実証は有限のPUBLIC fixtureのみ。人間承認による実操作、故障注入と復旧の検収は未実施で、Issue #8 Doneには残る。

| Requirement | Risk | Test | Result / Evidence |
| --- | --- | --- | --- |
| 同じ候補・評価・差分を提示 | 別候補/改変評価の誤提示 | pinned bundle/評価hash/公開packetの照合 | VERIFIED: test_public_submission_matches_pinned_packet_and_diff |
| 承認・root・pathの拘束 | 古い票/別root/別target/symlink/二重採用 | tests/test_adoption.pyの拒否・実filesystem試験 | VERIFIED（合成票） |
| 正常採用 | 実体不一致、回帰失敗の誤成功 | 独立normal target、実Docker公開10件 | VERIFIED（合成票）: synthetic-results.json |
| 故障と復旧 | 部分書込/再起動/劣化からの誤再開 | 別degradation/crash target、元版各5件 | VERIFIED（合成票）: synthetic-results.json |
| 人間の採用/復旧検収 | 実装承認/合成票を採用承認へ流用 | 別の具体的な対象と操作への人間承認 | NOT_VERIFIED: 人間承認前、未実施 |
| 最終headの外部Gate | 古いCI/レビューの流用 | 専用PRのCI/Security/CodeQL/正式レビュー | NOT_VERIFIED: PR提出後に記録 |

自己レビューはIssue #8とarchitecture/security-modelの承認binding・状態・復旧契約、CLI呼出元、既存Sandboxとの接続、PUBLIC提出境界を照合する。
元版の既知の入力拒否欠陥、同一OS利用者の任意改変、初期失敗runの未復旧は残存制約として保持する。
本Issueの人間操作と最終Mergeは人間判断であり、#9と親#31完了へ進まない。
