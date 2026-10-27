# Issue #33: 未登録の入力契約修正の実証

CodexアプリがPUBLIC packetだけから作成した候補は、凍結済みの独立評価でPASSとなった。
公開・hidden各10ケースはそれぞれ基準5件から候補10件へ改善し、回帰0、候補の実行失敗0、劣化対照FAIL、audit VERIFIEDを確認した。
これは固定課題1件の結果であり、一般的な生成品質、実Hermesへの統合、採用を証明しない。
Risk Tier: HIGH。生成コードの隔離と評価の独立性を扱う。着手・提出前ともHIGHを維持する。

## 入力と生成

2026-10-28、人間がPR #37をMergeした後の#33着手を承認した。
controllerは `ac91393276781758f9f8273fa58ead8ccc1ac394`、runは `generated-a9879c182fccecc0ce488323`。
生成前にfreeze済みの独立packetから `scripts/review.py`、`contract.json`、`public.json` とGit識別情報だけを読んだ。
前チャットの完成解、登録操作、評価器実装、tests、hidden、対照コードは初回候補の材料にしていない。

原因仮説は、基準のmainが入力型・キー集合・path・bytes上限を検証せず、空入力や例外を正常終了として握りつぶすため、拒否契約を満たさないことだった。
候補はstdinを最大16KiB+1だけ読み、UTF-8/JSON、キー集合、文字列型、path全体一致、非空patchを境界で検証する。
重複キーと非JSON定数も拒否し、不正入力をexit 2、指定error JSON、空stderrへ統一した。
正常系の `analyze_diff` とfinding判定関数は変更していない。

初回生成1回、公開テスト修正0回、最終候補1件、hidden評価後の修正0回。
候補固定後に既存catalogを照合した。登録2操作はcontext行と追加comment行のカウンター挿入だけであり、今回のmainと入力検証の変更を生成できない。
これらのカウンター処理はpacket基準に既に含まれていた。

## 固定と証拠

PUBLIC成果物は [artifact directory](../artifacts/generated-repair/issue-33/) に保存した。

| 識別子 | 値 |
| --- | --- |
| packet基準SHA | `65c53babda8f31405d54941e900c2d3987efa4b1` |
| 候補SHA | `e3153fec973051b28178df0656db05d2a3ffae84` |
| 候補SHA-256 | `ffd1fbd0087c86edea77ca0f1eac2c4c2a4cc516fba8a011331e0fe5a36d876d` |
| manifest SHA-256 | `339f7d4e9c63ff8041df9f8d7bbe66deb13ede7bd36048e442e64654d614278d` |

`candidate.bundle` は基準と候補の履歴・公開契約を保存し、`review.py` は同一候補の参照用コピーである。
基準の子孫、変更1ファイル、64KiB以下、cleanなpacket、完全SHAと内容hashを固定してからhooks無効のbundle fetch/checkoutで受け取った。
`report.json` は検査した集計の原bytesを保持し、`audit.json` のreport hashと一致する。
公開ケースの実stdout・exit・stderrは `public-results.json` に保存した。
hidden原本・正解・個別trace・private metrics・manifest原本はローカルrunに保持し、Gitへ追加していない。

| 集計 | 基準 | 候補 | 劣化対照 |
| --- | ---: | ---: | ---: |
| 公開正答 | 5/10 | 10/10 | 1/10 |
| hidden正答 | 5/10 | 10/10 | 1/10 |
| 実行失敗の観測数 | 18 | 0 | 0 |
| median秒 | 0.379468125 | 0.381998541 | 0.420302875 |

各入力3回、3版で180回の逐次Docker実行。回答・実行状態の揺れなし。
候補のlatency倍率は約1.007で、既存上限1.2以下。hidden改善+5、回帰0、費用0で既存policyを満たした。
prepare 11.11秒、公開全件照合5.59秒、事前呼出し2秒以内と独立評価を含む保守的累計上限132秒を確認した（予算1200秒）。
有料API呼出し・キー確認・追加クレジットは0。モデルサービスは使用していない。

最初の制限付きホストからのSandbox呼出しは `ISOLATION_CLEANUP_FAILED` となった。
Docker残存コンテナ0を確認し、同じ候補をDockerへ接続可能な実行権限で検査した。
候補をホストで実行・importせず、imageのpull、制限緩和、サービス変更は行っていない。
固定arm64 image、networkなし、UID/GID65532、read-only、CPU1、memory256MiBなどの既存Sandboxを使用した。

## 再現手順

PUBLIC候補の完全SHAと元版は、空の一時Git repositoryへbundleをfetchし、コードを実行せず検査できる。
以下はrepo rootで実行する。

```sh
git -c core.hooksPath=/dev/null bundle verify artifacts/generated-repair/issue-33/candidate.bundle
python3 -B -m unittest discover -s tests -p test_issue33_artifact.py
```

公開ケースを再実行する場合は、既存の固定imageが利用できる独立controller checkoutで、次のtrusted controllerだけをホストで実行する。
新しいworkを作って実行証拠を保持し、候補は `write_new` で別コピーにしてread-onlyとする。候補をホストから起動しない。

```python
from pathlib import Path
import json
import tempfile
from evaluation.core import write_new
from evaluation.sandbox import Sandbox

root = Path.cwd().resolve()
artifact = root / 'artifacts/generated-repair/issue-33'
image = 'sha256:eb7d16fec874f15b584063275012ac719885a2b87574d124c0da9c156d504629'
work = Path(tempfile.mkdtemp(prefix='issue33-public-', dir=root / 'runs'))
program = work / 'candidate.py'
write_new(program, (artifact / 'review.py').read_bytes())
program.chmod(0o444)
box = Sandbox(root, work, image)
for case in json.loads((artifact / 'public.json').read_text()):
    result = box.run(program, case['stdin'].encode(), timeout=15)
    assert result['exit'] == case['exit']
    assert not result['stderr'] and not result['error'] and not result['oom']
    answer = json.loads(result['stdout'])
    if case['exit'] == 2:
        assert answer == {'error': 'INVALID_INPUT'}
    else:
        assert set(answer) == {'findings', 'cpu_seconds'} and answer['cpu_seconds'] == 0
        assert [[f['path'], f['line'], f['rule']] for f in answer['findings']] == case['expected']
```

`PYTHONPATH=src python3 -B <trusted script>` で実行する。Docker故障時は停止し、残存containerと回収を確認する。
新規image pullや制限緩和は行わない。
元runの独立評価は一度だけ実施済みであり、再evaluateやlock解除は行わない。
原本を保持した同じcontrollerで `python3 -B scripts/generated_repair.py audit --run generated-a9879c182fccecc0ce488323` により再監査できる。
新規独立評価には新しい承認済みrunとfreezeが必要で、元候補commitはその新packetの子孫ではない。旧SHAの評価を使い回さない。

## 保証範囲と人間判断

artifact回帰テストはbundleから両SHAとhash、1ファイル差分、元版、公開ケース、report/auditの結合を検査し、候補を実行しない。
既存generated-repair、固定操作、評価の回帰はmockによるcontroller検証であり、上記の実Docker評価と区別する。
既存fixture・評価器・policy・dataset・workflow・検証入口は変更していない。復旧はPRのPUBLIC追加をrevertする人間判断とする。

情報分類はPUBLIC候補と検査済み集計、hiddenはINTERNALでローカル保持。
LLMは今回承認済みCodexアプリ、Readはpacket/対象repo/Issue、Writeは対象repoの専用branch/PRのみ。
送信先allowlistは `second-works/hermes-self-improvement`。2026-10-28の人間指示でPUBLIC push/PR/正式レビューまで承認済み。
秘密情報・本番・認証・サービス・権限・課金変更は対象外。
Merge、Issue Close、採用は人間が判断する。#34へ進まない。

## ローカル検証

標準 `./scripts/verify.sh` はlintとsetup 30件に成功。typecheck/buildは設定がないため理由付き対象外。
追加でartifact同一性1件、generated-repair 19件、固定操作8件、evaluation 34件に成功した。
Bash 5 Security PreflightはSECURITY_PASSED。依存manifestがないため依存監査は理由付きSECURITY_NOT_APPLICABLE。
warning/deprecationは観測していない。CI・Security・CodeQL・正式レビューは提出後の同じPR headで照合し、証拠をPRへ記録する。
