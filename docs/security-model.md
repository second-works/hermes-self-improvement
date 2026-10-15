# 自己改善の権限・データ境界案

候補生成者には隔離した無害fixtureと候補ディレクトリだけを渡す。
評価者、GitHubへの提出者、人間の採用担当を分離し、既存の [AI Agent Security Boundary](ai-agent-security-boundary.md) を保持する。
[Issue #2](https://github.com/second-works/hermes-self-improvement/issues/2) の設計案であり、新しい安全規則・権限・接続を有効化するものではない。Risk Tier: HIGH（外部送信・採用権限の設計）。

## データと送信先

| データ | 分類 | 許可範囲 |
| --- | --- | --- |
| 公開upstream、合成fixture、検査済み設計 | PUBLIC | このrepoと承認済みGitHub宛先 |
| hidden評価、内部診断・trace | INTERNAL | 隔離評価者と承認済み保存先。候補生成者・GitHubへ個別データを送らない |
| 認証、個人会話、本番設定 | CONFIDENTIAL | 今回収集しない。未承認LLMへ送信しない |

LLM環境をMANAGEDと推定しない。provider・保持・学習利用・監査条件を確認し、未確定はUNMANAGEDとして扱う。今回の公開資料と文書の調査以外のモデルAPI利用は別承認。
最小fixtureのネットワークはなし。将来API実験はproviderの正確な宛先、モデル、PUBLIC入力、権限、費用を人間が承認したallowlistのみ。GitHub提出先は `second-works/hermes-self-improvement` の対応IssueとPR branchに限定し、push承認を別に確認する。

## 主体ごとの能力

| 主体 | 読取 | 書込・実行 | 渡さない能力 |
| --- | --- | --- | --- |
| 観測・診断 | 検査済みfixture/観測 | 提案レコード | 本番・Secret参照、インストール |
| 候補worker | 仕様、公開評価、基準スキル | run内候補作成と隔離テスト | hidden、GitHub token、push、Merge、採用 |
| 独立評価者 | 固定基準・候補、hidden | 隔離評価・集計レポート | 候補書換え、閾値変更、外部送信 |
| 制御・提出者 | 検査済み成果物・公開集計 | 状態・予算・排他管理、承認済みbranch提出 | 本番アクセス、自動承認・Merge |
| GitHub Actions | repoと無害fixture | 固定された既存検証 | 本番接続、自己改善API、自動適用 |
| 人間の採用担当 | 差分・検証・承認・バックアップ | 明示対象だけ採用/復旧 | 包括的な自動適用権限の付与 |

Sensitive Read × External Writeとなる評価データの集計提出はHIGHとして、生成者から提出権限を分離する。制御側で出力schema、パス、Secrets、分類、送信先を検査し、不明なデータは送信停止。
観測・候補・README・PR・評価traceの命令は未検証データとして扱い、そこからallowlist、予算、権限、workflowを変更しない。ルール変更を候補の目的に含めない。

## 隔離の実装条件

後続Issueで、root以外のuser、capability削除、read-only root、CPU/memory/process/ディスク/時間制限を固定する。HOMEは使い捨ての空領域、必要なfixtureだけread-onlyで渡し、書込はrun内だけ。
ホストHOME、`~/.hermes`、SSH agent、鍵、環境変数のSecrets、Docker socket、Git credential、ホストnetworkを渡さない。最小試験はnetworkなし、外部toolsはin-processの無害fixtureを使う。
Dockerでこれらを実証するまで候補実行を許可しない。Mac mini M2/16GBでのDocker利用可否・arm64 image・資源上限は未検証で、本番サービスを停止して資源を空けない。
拒否試験は一時領域のダミーパスと偽Secretで行い、本番の読取を拒否試験のためにも実行しない。ソース取得と依存導入は候補実行から分離し、固定SHA/lock/image digestを検証する。

## 人間承認と復旧

仕様・予算・API宛先・隔離方式を承認してから実験を開始する。PRのMerge、人間の本番採用、権限変更、定期ジョブ有効化はそれぞれ別承認。通常レーンだけを使い、Auto-Fix / Auto-Mergeは採用しない。
採用・復旧承認はenvironment_id・target_id・root_binding_hash・登録root内の正規化済みartifact相対path・候補SHA・評価hash・許可操作・期限に紐づけ、変化があれば失効する。root_binding_hashは信頼済み登録のenvironment_id/target_id/canonical root/root実体ID（filesystemのdevice/inode等、照合可能なidentity）/登録versionを固定形式で直列化したSHA-256。同じIDとrootの対応は不変とし、root変更は新target_id・新規承認を必須にする。候補workerは登録を変更できない。採用/復旧直前に承認票・lock・登録・実配備先のcanonical rootと実体IDを照合し、root差替え（実体差替えを含む）や同一性不明は承認失効として停止する。
採用承認では、期待する基準SHAと採用前artifact hash、承認済み候補artifact hashを別フィールドで固定する。承認票とlock・実配備先の全対象項目が一致しなければ拒否し、同一hashでも対象Aの承認を対象B/root別先に流用しない。対象登録で同じ配備先の別ID登録を拒否する。未確認のCI/Security/Codex Reviewを成功扱いしない。既存workflowとmain保護の設定変更は本設計に含めない。

将来の採用前に、元のスキルのhashと復旧可能なsnapshot、変更allowlist、配備先、復旧承認を記録する。設定・DB・会話履歴を巻き込むバックアップや削除はしない。
同一ターゲットと実配備先の採用・復旧を排他し、承認票・lock・実配備先のenvironment_id/target_id/root_binding_hash/pathを照合する。現在の採用前artifact hashを承認票の期待する基準artifact hashと照合する。候補の取得元commitを承認済み候補SHAと照合し、候補artifact hashも承認票と照合してから適用する。採用後artifact hashは候補artifact hashと照合する。Git commit SHAとartifact hashを直接比較せず、基準版と候補版の同一性も要求しない。書込前の不一致はSTOPPED。制御側がADOPTINGと元版snapshot・対象/rootを永続化してから書込を開始し、途中失敗・採用後不一致・書込有無不明はRECOVERY_REQUIREDにして対象を隔離する。未採用/部分適用として記録し、成功や無変更と推定しない。
採用後の安全違反・必須回帰・品質劣化もRECOVERY_REQUIREDにして次反復を停止・通知する。復旧承認には同じ配備先の対象項目、観測済みの現在状態（通常ファイルのhashまたは欠如）と復旧先の基準SHA・artifact hashを固定し、現在状態と復旧元をそれぞれ照合する。現在状態が不明なままは書き込まない。人間承認後にROLLING_BACKを永続化して元版を戻し、復旧後hashと回帰が合格した時だけROLLED_BACKにする。復旧途中失敗・結果不明はRECOVERY_REQUIREDのまま対象を隔離してエスカレーションする。再起動時の未完了intentも同じ扱いとし、自動再開しない。#8で採用後劣化と部分適用失敗から元版へ戻る別試験を実証し、#9でも再検証する。

監査イベントはrun_id、UTC、actor、状態遷移、入出力hash、予算予約/精算、承認参照、終了理由を追記する。イベント連鎖hashと外部の検査済み記録で改ざんを検出し、ハッシュだけを完全な改ざん防止とは扱わない。
Issue #3の隔離試験について、2026-10-15にユーザーがrepo内 `runs/<run_id>/`（Git管理外）、合成原データは最低30日、検査済み監査記録は最低90日保持し、期限後も自動削除しない方針を承認した。[Memory検証の保存境界](memory-verification.md)を参照する。本番保存や候補実行の権限は含まない。候補workerに監査原本の編集・削除権限を渡さず、削除は人間承認後の対象限定作業とする。ログに生のprompt・token・Secret・会話履歴を残さない。

## 安全検証の受入例

- パス逸脱、symlink、偽Secret、送信先不一致、権限拡大の要求を拒否し、値をログへ出さない。
- hidden漏洩、候補による評価・承認改変、古いSHAの承認、評価欠如でPASSへ進めない。
- 予算直前/超過、子workerのretry、timeout、異常終了で全体停止し、結果と理由を保持する。
- 同じrunの二重起動、再起動後の生存不明lock、二重採用を拒否する。
- 同一hashの別target、承認root/pathとlock/登録/配備先の不一致、旧IDのroot差替え、root実体差替え、配備先の別ID登録を拒否する。
- 模擬採用・復旧でhash一致を確認し、採用途中/復旧途中の失敗・再起動をRECOVERY_REQUIREDへ移して、承認付き復旧まで追跡する。

これは後続実装の受入条件案であり、今回テスト済みの機能ではない。
