# 計画書サンプル（学習用）: Web Todo アプリ V1

> このファイルは、Nine標準フローで計画書を書くときの**記入例**です。案件の正本ではありません。  
> Vue を Nine の標準 Framework として固定するものでもありません。下記は「要件 → 描画方針 → 構成 → Framework」の順で導いた **V1 の採用案**です。  
> 実際の案件では、利用者・公開範囲・運用制約が違えば別の技術になります。

---

# Decision

- **採用案:** ログインなしの個人向け Web Todo。ブラウザ内に保存し、静的ファイルとして配信する SPA。
- **主要理由:** V1 の目的は「今日やることを追加・完了・削除できる」ことであり、検索流入・会員機能・サーバー保存は不要。サーバーを持たないと運用と秘密情報の負担が最小になる。
- **影響:** 複数端末の同期はできない。ブラウザのデータを消すとタスクも消える。SEO 用のサーバー描画（SSR）は採用しない。
- **Risk Tier:** `MEDIUM`  
  - 理由: 新しい Web / UI であり実行動作を作る。認証・Secrets・Production 権限変更は含まないため `HIGH` ではない。文言だけでもないため `LOW` ではない。
- **Plan Review 想定:** `PASS`（このサンプルが埋めている判断を、実案件でも人間が承認した場合）

# Alternatives

| 案 | 却下理由 |
| --- | --- |
| 会員制 + サーバーDB | V1 の利用者は自分だけ。アカウント・API・バックアップ設計が一気に増える |
| ドキュメント中心の静的サイト（SSG） | タスクは頻繁に変わる状態付きアプリであり、記事サイトではない |
| Next.js 等の Full Stack / SSR | 公開SEOもサーバーデータも不要なのに、運用と構成が過剰 |
| デスクトップ専用GUI | 「Webで使う」要件を満たさない |

# Non-goals（今回やらないこと）

- ログイン、ユーザー登録、権限、チーム共有
- クラウド同期、複数端末での同一データ
- 期限・繰り返し・タグ・サブタスク・添付ファイル
- ネイティブアプリ、PWA のオフライン高度対応、プッシュ通知
- 本番での自動 Deploy、コンテナ、データベース
- Framework の再選定を実装中に行うこと

---

# 要件

## 何を作るか / なぜ

個人がブラウザで「やることを書いて、終わったら完了し、不要なら消す」ための小さな Web アプリ。紙のメモより探しやすく、スマホでも使えることを目指す。

## 利用者

- 対象: 自分のタスクを管理したい一般利用者（非エンジニアでも使える）
- 人数: V1 は1人利用を想定（同じブラウザプロファイル内）
- 技能: Web の基本操作（入力、タップ、スクロール）ができればよい

## 必要機能（V1）

1. タスクを追加する（空文字・空白のみは追加できない）
2. 未完了一覧を見る
3. 完了 / 未完了を切り替える
4. 完了済みも含めて見る、未完了だけ見る、完了だけ見る（フィルタ）
5. タスクを削除する（取り消し確認あり）
6. 再読み込み後も、同じブラウザに残っている

## 現在の環境

- 開発: 手元のブラウザとローカル開発サーバー
- 公開（任意）: 静的ホスティング（HTML/CSS/JS を置くだけ）
- サーバーサイド実行、DB、GitHub Environments の production 承認は V1 対象外

## セキュリティ上の制約

- ログインなし。データは利用者のブラウザ内（`localStorage`）のみ
- 情報分類: タスク文言は利用者端末上の `INTERNAL` 相当。リポジトリや Issue に実タスクを貼らない
- 入力した文字を画面へ出すときは、HTML として実行されないようにする（XSS 防止）
- 秘密情報・API キーは使わない。`.env` に本番秘密を置かない
- AI エージェントは Production 変更・権限拡大をしない

---

# Framework Decision

正本: 生成プロジェクトでは `docs/architecture/framework-decision.md` を配置し、案件記録は `docs/framework-decision.md`（雛形: `templates/app/docs/framework-decision.md`）。

- **Result:** `DECIDED`
- **適用:** 新規 Web 案件のため対象。CLI 専用ではない。

## 1. Requirements（Framework 名より先）

| 観点 | 今回値 |
| --- | --- |
| 公開ページ / SEO | 検索流入は不要。OGP やクローラ向け SSR は対象外（理由: 個人ツール） |
| 公開 / 認証後 | ログインなし。認証後エリアはない |
| コンテンツ / アプリ | 状態を持つアプリケーション中心 |
| Server 機能 | SSR、Server Components、サーバーでのデータアクセスは不要 |
| API 分離 | V1 は API サーバーなし。保存はブラウザ内 |
| Runtime | モダンブラウザ（Chrome / Safari / Firefox の現行）。Node.js は開発時の build のみ |
| Deployment | 静的ファイル配信。Cloudflare Pages / GitHub Pages / ローカルどれでも可 |
| self-host | 静的ファイルをコピーすれば自己ホスト可能。特定ベンダー機能に依存しない |
| 運用複雑性 | 開発者1人。build と静的配置が上限 |

## 2. Rendering Strategy

- **選定:** `SPA`
- **要件からの理由:** 初回以降は同じ画面で一覧が頻繁に更新される。SEO 用のサーバー HTML は不要。
- **初期データ:** 起動時に `localStorage` を読み、空なら EMPTY 状態。
- **却下:** `SSG`（内容がユーザーごとに変わり、ビルド時に確定しない）／ `SSR`（サーバー実行が要件にない）

## 3. Application Architecture

- **選定:** `SPA`（API 同居も分離もしない。クライアント完結）
- **UI / API 境界:** 画面は「検証済みの Todo 一覧」だけを扱う。保存の読み書きは `TodoRepository` 相当の1箇所に閉じる
- **サーバー機能:** なし（理由: 保存も認証もサーバー不要）
- **データ境界:** 外部入力はタイトル文字列のみ。境界で trim、空拒否、最大長、危険な制御文字の除去を行い、内部では検証済み型として扱う

## 4. Framework 候補

| 候補 | 採否 | 主な理由 |
| --- | --- | --- |
| Vite + TypeScript + Vue 3 | **採用** | SPA と静的ホストに合う。画面状態の表現が素直。build が軽い |
| Vite + TypeScript + 素の DOM | 不採用 | 状態（空・エラー・フィルタ）が増えると画面更新が散らばりやすい |
| Next.js（SSR / App Router） | 不採用 | Rendering が SPA で足りるのにサーバー実行が前提になりやすい |
| 多ページの素の HTML だけ | 不採用 | フィルタと完了切替の状態をページ遷移で持つと複雑になる |

- **採用 version 制約（例）:** Node.js は `.nvmrc` で固定。Vue 3 と Vite は lockfile で固定
- **採用しない理由の共通原則:** 知名度や AI の生成しやすさだけでは選ばない
- **この決定が無効になる条件:** 複数人同期、ログイン、SEO 必須の公開 LP が要件に入ったとき。その場合は Framework Decision を `NEEDS_DECISION` に戻して再選定する

## 5. 後続への引き渡し

- UI Level / `docs/design.md`: SPA、1画面中心、Framework は再選定しない
- Plan Review: Result `DECIDED`、静的 SPA、API なし
- Deployment: 静的ホスト。DB / コンテナなし
- Security: サーバーSecretsなし。入力のエスケープが主リスク

---

# UI Level / PRODUCT 前提

- **UI Level:** `PRODUCT`
- **分類理由:** 一般利用者がブラウザで使う visibile な製品画面であり、内部管理者ツール（`UTILITY`）や CLI（`NONE`）ではない
- **PRODUCT UI completeness:** `COMPLETE`

| 必須項目 | 今回の決定 |
| --- | --- |
| Primary screen structure | 1カラム。上: タイトルと追加フォーム。中: フィルタ。下: 一覧 |
| Navigation | 画面遷移なし。フィルタは同一画面の切替 |
| Primary Action | 「追加」（モバイルでは入力欄のすぐ下またはキーボード送信） |
| Critical user flow | 開く → 追加 → 一覧に出る → 完了にする → （任意）削除 |
| Destructive action behavior | 削除は確認ダイアログ。キャンセルで何も消さない。一括削除は V1 にない |
| Device Priority | `Mobile First`（片手・通勤中を想定。タッチ対象は十分大きくする） |
| Major Design Direction | 落ち着いたライトテーマ、余白多め、装飾より「今いくつ残っているか」を優先 |

## 画面と状態（不正状態を型で防ぐ）

タスク1件の状態は `ACTIVE` / `COMPLETED` の2値だけにする。`isDone` と `isArchived` などの boolean の組合せにしない。

フィルタは `ALL` / `ACTIVE` / `COMPLETED`。

画面の状態は、独立して同時に成り立つ軸と、入れ子でしか成り立たない軸を分ける。権限画面（`UNAVAILABLE`）はログインがないため対象外。

```text
load:
  LOADING
  | LOAD_FAILED
  | { tag: LOADED, list: EMPTY | NONEMPTY, form: IDLE | INVALID | SUBMITTING }

notice: NONE | SAVED | SAVE_FAILED   # load と直交
```

`LOADING` や `LOAD_FAILED` のときに `list` と `form` を持たない。`LOADED + EMPTY` はエラーではない。`LOADED` 中は `form=INVALID` でも `list` は消えない。`SAVED` は `LOADED` の上に短い通知を重ねてよい（最後の1件を消した直後は `list=EMPTY` でも可）。

## 主要画面仕様（一覧 = 唯一の主画面）

- **目的:** 残っていることを把握し、追加・完了・削除する
- **Primary Action:** 追加
- **Secondary:** フィルタ、完了切替、削除
- **表示:** タイトル、完了状態、残数、フィルタ中の件数
- **Error Recovery:** 保存失敗時は文言を残し、再試行ボタン。削除確認でキャンセルしたら元のまま
- **次画面:** なし（同一画面）

Accessibility（最低）: 追加ボタンと削除確認はキーボードで操作できる。完了はチェックボックスまたは `aria-pressed` 付きボタン。色だけに依存しない（完了は取り消し線 + 「完了」テキスト）。

案件の見た目詳細は実装リポジトリの `docs/design.md` に移す。この計画書では方向だけ固定する。

---

# データ / 状態 / 境界

## データ

```text
Todo = {
  id: 空でない文字列（内部で発行。同一一覧で一意。ユーザー入力ではない）
  title: 1〜100文字（前後空白なし）
  status: ACTIVE | COMPLETED
  createdAt: 日時
}
```

保存形式は JSON 配列。読み込み境界の採用挙動は次で固定する（拒否と無視を併用しない）。

- 全体が配列でない、または JSON として壊れている: `load=LOAD_FAILED`。空配列で上書きしない
- 配列の各要素: 必須フィールド（`id`, `title`, `status`, `createdAt`）が型どおりなら **要素単位で採用**。未知フィールドは捨てて既知フィールドだけ残す（将来キー追加の前方互換）
- `id` の不変条件: 空でない文字列。配列内で一意。空文字・空白のみは **その要素だけ捨てる**。同じ `id` が複数ある場合は **先に現れた正当な要素だけ残し、後続の重複は捨てる**
- `title` の不変条件: 1〜100文字で、`title === title.trim()` を満たす。trim後が空、前後に空白がある、または100文字を超える場合は **その要素だけ捨てる**。読込時に値を暗黙にtrimして別のTodoへ変換しない
- 必須フィールド欠落・型不正・`status` が `ACTIVE` でも `COMPLETED` でもない要素: **その要素だけ捨てる**。他の正当な要素は残す
- 正当な要素が0件: `{ tag: LOADED, list: EMPTY }`。不正要素を捨てた事実は V1 では利用者向け `notice` に出さない（開発者向けログのみ）
- 内部では検証済み `Todo` だけを持ち、未知フィールドをアプリ状態へ広げない。完了切替・削除は検証済み `id` だけをキーにする

## 外部入力

- 入力: タイトル文字列のみ
- 検証: 必須、最大100文字、改行は空白に正規化
- 出力: テキストとして描画し、HTML 注入しない

## 失敗時

- 保存失敗: `notice=SAVE_FAILED`。`list` は直前の正当な一覧を残す
- 読み込み不能: `load=LOAD_FAILED`。空配列で上書きしない。「データを読み込めません」+ 再試行
- 削除確認を閉じる: 削除しない。`notice` は `NONE` のまま

---

# Deployment（V1）

正本: `docs/deployment-release-design.md`。Merge は本番公開を意味しない。

| 項目 | 今回値 |
| --- | --- |
| Production runtime | 静的ファイルを HTTPS で配信。サーバープロセスなし |
| Container | 不要。理由: OS 上の常駐処理も DB もない |
| Persistent data | ブラウザ `localStorage` のみ。サーバー永続データなし。バックアップはブラウザ／利用者責任と明記する |
| Deployment method | V1 の必須はローカル実行。任意公開は静的ホストへ手動または既存 CI の pages 相当。GitHub `production` 環境の自動 Deploy は対象外 |
| Release Candidate | 公開する場合は Git の commit SHA と一致する build 成果物 |
| Full-System Security Audit | サーバーも Secrets もない静的 V1 は、依存監査 + XSS 観点の静的確認。Staging 省略理由: 実行環境がブラウザのみ。代替: 本番相当 URL かローカル build を実機ブラウザで確認 |
| Secrets | アプリ実行に Secrets なし。値を計画書に書かない |
| Backup / migration | サーバー migration なし。保存キー名を変えるときは旧キーからの一度きりの変換か、互換を Issue 化する |
| Post-deploy check | ページが開ける、追加できる、再読み込み後に残る |
| Rollback | 静的ホスト上の前 SHA の成果物に戻す。利用者の `localStorage` はサーバーから巻き戻せない（制約として検収に書く） |

---

# 検収計画

正本: `docs/acceptance-verification.md`。`Implementation Done` / `Deployed` / `Product Accepted` は別状態。

- **解決したい課題:** 頭の中や紙に散らばった「今日やること」を、一つの画面で処理したい
- **対象ユーザー:** 非エンジニアの個人
- **実利用シナリオ:** 朝にアプリを開く → 「牛乳を買う」を追加 → 買い物後に完了にする → 不要な下書きを削除確認して消す → ブラウザを閉じる → 再度開き、完了済みが残っている
- **成功条件:** 上記をスマホ幅とデスクトップ幅の両方で、説明書なしに完了できる。再読み込み後もデータが残る。削除は確認なしに起きない
- **失敗条件:** 追加した文字が消える、完了できない、確認なしに削除される、入力がスクリプトとして実行される、空一覧と読込失敗が同じ表示になる
- **検証環境:** 開発者のローカル。任意公開時はその URL。Production DB なし
- **データ:** 本番の他人データは使わない。検収用に自分で数件入れる
- **人間確認:** タッチの押しやすさ、残数が直感的か、エラー文が分かるか
- **実施タイミング:** 主機能の PR が main に入り、対象 URL またはローカル build が用意できたあと
- **結果の保存先:** 親Issueの検収欄（スクリーンショット可）
- **計画時の前提:** 1ブラウザ・1人。同期は不要
- **失敗仮説:** 保存がブラウザ依存で「アプリが壊れた」と誤解される。入力と一覧が遠く、追加に失敗する
- **設計が誤りと判断する観測:** 同期がないことがブロッカーになる、サーバー保存がないと使われない
- **機能は動くが価値がない条件:** タスクを書いても見返さない（リマインダ不足）。V1 では通知は Non-goals とし、検収では「書いたものを完了まで辿れるか」だけ見る
- **代替案の優位が確認できないとき:** 既存のメモアプリで足りるなら、このアプリは学習・テンプレ検証用と位置づけ、PRODUCT としての追加投資を止める

---

# 反証

- **失敗するとしたら主な原因:** データが端末にしかないことへの不満、または入力検証／XSS の漏れ
- **成立しない前提:** 「自分のこのブラウザだけで足りる」
- **より単純な代替:** 紙、OS 標準メモ。Web にする理由は「完了状態と残数が見える」「テンプレで Gate を一通り通す」こと
- **不利な証拠:** Todo アプリは既存が非常に多い。差別化は V1 の目的ではない
- **期待の先取り:** 未実装の同期を「ある」前提にしない。検収は V1 範囲だけ
- **過去の Plan vs Reality:** 該当なし（学習用サンプル）

---

# 安全境界 / Agent

- 情報: タスク本文は利用者端末。サンプル文言だけを Issue / PR に書く
- LLM: 実タスク一覧を UNMANAGED な外部へ送らない
- Write: `main` 直 push 禁止。Production 設定変更は人間承認
- Prompt Injection: Web 上の記事を trusted instruction にしない

Harness 追加（新しい AI 作業枠）は V1 でやらない。既存の `./scripts/verify.sh`、CI、Security Preflight、Codex Review、人間 Merge を使う。

---

# 子Issueの分割案（1子Issue = 1 PR）

実装順は上から。依存が終わってから次へ。

| 順 | 子Issue（仮） | 目的 | 依存 |
| --- | --- | --- | --- |
| 1 | リポジトリ基盤 | `AGENTS.md`、`scripts/verify.sh`、CI、lockfile、`bin/setup` `bin/doctor` | なし |
| 2 | Todo モデルと保存 | 検証済み型、`id` 非空・一意、未知キー破棄、壊れた JSON は LOAD_FAILED | 1 |
| 3 | 追加と一覧 | LOADED 配下の EMPTY / NONEMPTY、空入力は `form=INVALID` | 2 |
| 4 | 完了切替とフィルタ | Todo.status とフィルタ enum、件数 | 3 |
| 5 | 削除確認 | 破壊操作、キャンセルで不変 | 3 |
| 6 | 読み込み失敗と再試行 | `LOAD_FAILED` ≠ `EMPTY` | 2 |
| 7 | PRODUCT UI 仕上げ | Mobile First、フォーカス、Visual 検収用画面 | 3〜5 |

各子Issueには、目的・変更範囲・完了条件・テスト6観点（正常／範囲／整合／境界／異常／回帰）・安全境界を既存の child-issue テンプレートで書く。この計画書では分割と依存だけ固定する。

テストの置き場所:

- モデル・文字数・状態遷移: Unit
- 保存の壊れ方: Repository 相当（モジュール境界）
- 追加〜削除の主経路: コンポーネントまたは軽い結合テスト
- 見た目と操作感: Acceptance（人間 + スクリーンショット）

---

# 全体完了条件（親Issueへ移す内容）

- [ ] 子Issueがすべて Merge / Close
- [ ] `./scripts/verify.sh` と GitHub Actions CI が対象 SHA で成功
- [ ] Security Preflight 等の結果を記録（依存があれば監査、Secrets 混入なし）
- [ ] Codex Review の P0 / P1 / BLOCKING P2 が未解決でない
- [ ] Product Acceptance 対象 artifact と現行 Deploy target が設定済みかつ一致している
- [ ] 検収が `Accepted`、または `Conditional` なら条件・期限・追跡 Issue があり、未解決の ACCEPTANCE BLOCKER がない
- [ ] `COMPLETED` 直前に Deploy 正本から現行 target を再取得し、未設定・不一致なら検収をやり直している
- [ ] 人間が Merge と検収を最終確認

---

# Plan Review 記録（サンプル記入）

判定: `PASS`

### Framework Decision

- Result: `DECIDED`
- 正本参照: `docs/architecture/framework-decision.md`（案件では `docs/framework-decision.md` に具体化）
- 要約: SPA、API なし、Vite + Vue 3 + TypeScript、静的配信
- Framework 依存の未決定: なし

### UI Level / PRODUCT UI completeness

- UI Level: `PRODUCT`
- UI 適用対象: PRODUCT
- PRODUCT UI completeness: `COMPLETE`
- PRODUCT 未決定事項: なし（上表で決定済み）
- Design Decision へ送る UI 項目: なし

### 未決定事項

- なし（任意の静的ホスト先は公開時に親Issueへ追記。未定のままでもローカル検収は可能）

### 暗黙の前提

- 利用者は自分のブラウザを信頼できる
- モダンブラウザのみ（Internet Explorer は対象外）

### 反証検証

- 失敗原因: 端末保存の限界、入力の安全処理漏れ
- 成立しない条件: 複数端末必須
- 単純な代替: OS メモ
- 不利な証拠: 類似アプリは既に多い
- 先取り: 同期を成功条件に入れていない
- 過去の Plan vs Reality: なし
- 反映した教訓: EMPTY と ERROR を分け、削除は確認必須

### 主要リスク / エッジケース

- 100文字超、空白のみ、絵文字、非常に長いペースト
- `localStorage` 無効 / 容量不足
- 別タブ同時編集（V1 は「最後の書き込み勝ち」と明記。高度な同期は Non-goals）

### Design Decision へ送る項目

- なし

### Issue化可否

- 可（人間がこの採用案を承認したあと）
