# Security reporterの送信元分離

Decision: 専用GitHub Appとmain限定Environmentを使用する案を2026-10-15にユーザーが明示承認した。目的は候補workflowによるSecurity Preflight status上書きの防止。Risk Tier: HIGH（認証・権限・保護設定）。PUBLICのrepositoryだけを対象とし、秘密鍵はCONFIDENTIALとしてGitHub Environment Secretだけに保持する。

Environment `security-reporter` はAPIで作成済み。custom branch policyはbranch `main` のみ、tag許可なし、管理者bypass=false。App `hermes-security-reporter`（ID 5322549 / Client ID Iv23lixI99PZUoYTzGlk）はユーザーが作成し、本人認証後にCommit statuses書込＋Metadata読取だけを保存、hermes-self-improvementだけへinstallした。Webhookは無効。App IDとClient IDをEnvironmentへ登録済み。2026-10-15にユーザーが秘密鍵を登録し、APIでSecret名のみを確認した。必須Security Preflight送信元はApp ID5322549へ固定済み。main workflow反映と実動検証は未完了。

Appの権限はCommit statuses: read/writeと必須Metadata: read、このrepoだけへinstallする。Environment Secretは `SECURITY_APP_PRIVATE_KEY`、variablesは `SECURITY_APP_ID` と `SECURITY_APP_CLIENT_ID`。秘密鍵をrepo/organization Secretやチャット・logへ出さない。新しい鍵の入力・保存はユーザーがGitHub上で行う。追加課金・外部ホスティング・Hermes本体へのアクセス・Mergeは対象外。

workflow修正は公式App token actionの固定revision `64ab729a6294000f5aa4a4bc0b73d1f32bc45510`（v3）を使い、repoとstatuses書込だけを指定する。GITHUB_TOKENはcontents readへ縮小。App tokenはstatus報告stepだけへ渡し、候補コードは実行しない。tokenはjob終了時に公式actionで失効する。設定欠如・token発行失敗は成功へfallbackせず停止する。

関連P1の修正候補: workflowだけでなくscripts/verify.sh、scripts/lint.sh、scripts/test.sh、tests/test_setup.pyも固定revisionのmode/blobへ照合し、no-opへの差し替えを拒否する。これらの変更とscanner更新には検証済みpin更新が必要。検証済み固定revisionは `8c2508eb7e7970d40adbcdba9731b83038300feb`。main側への反映と実動確認は別途PRコメントへ記録する。

npm監査は新しい一時directoryにmanifestとlockfileだけをコピーする。candidate .npmrcを持ち込まず、user/global configを無効化し、継承環境を分離して https://registry.npmjs.org を明示する。候補のregistryや認証設定は読まない。候補側のproxy、omit、registry設定で検査を変えない。

必要な実動証拠はPRへ記録する: 新しい同一headのlocal / CI / Security / CodeQL / Codex結果、専用App由来statusの成功・検査失敗・不能、main以外のEnvironment拒否、別App由来の同名successでfailureを解除できないこと、管理者保護復元、BLOCKING残件ゼロ。未観測は成功扱いしない。途中失敗時はPRをMerge不可として保持し、保護の解除やGITHUB_TOKENへのfallbackはしない。
