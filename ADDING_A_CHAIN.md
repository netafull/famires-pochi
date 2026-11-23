# ファミレスポチにチェーンを追加する手順

読者は、下調べから実装、PRまでを進める担当のエージェント。レビューだけをモル（Claude Code）に頼む前提で書いている。
先に `AGENTS.md` と `README.md` を読むこと。この手順書は両方の補足で、食い違ったら AGENTS.md が優先する。
確認できていないことは「未確認」と書いた。推測で埋めずに、レビューで聞いてほしい。

## 1. 先に下調べをして、取れないチェーンは対象外にする

追加の可否は、実装の前に次の6点で決める。1つでも満たさなければ、そのチェーンは追加しない。

1. **robots.txt**: 対象のパスが `Disallow` でないこと。`crawl.py` の `Robots` クラスが実行時にも見る（404は全許可、HTMLが返るサイトも全許可）。
2. **規約**: サイトポリシーやご利用条件の、複製・転載・自動取得（クローラー）の条文を読み、結果を記録する。
   読めなかったときは「未確認」と書く。デニーズは確認済み、すかいらーく（ジョナサン）は未確認のまま、オーナーの了解を得て始めた。
3. **ボット対策**: 403・429・チャレンジページ（Cloudflare や Akamai の確認画面）が返るチェーンは対象外。UA偽装などの回避はしない（`scripts/fetch.py` も回避しない作りで、`BlockedError` を出して止まる）。
   UAは `config.json` の `user_agent`（`FamiresPochi/1.0 (+https://famires.netaful.jp/)`）のまま。
4. **価格と商品名がHTMLのテキストで取れること**。`<img>` の `alt` に入っている形（ジョナサン）はよい。
   **価格が画像の中にしかないチェーンはOCRせず対象外**にする（オーナー方針。誤読がそのまま記録になるため）。ガスト・バーミヤン・夢庵がこれに当たる。
5. **開始日の一次情報**（ニュースやお知らせの見出しなど）があるか。あれば商品ごとの開始日を拾える。
   なければ開始日は「記録開始日」になる。記録開始日の商品は、新発売ポチには載らない（新発売ポチは `launch_date` のある商品だけを載せる。`shinhatsubai-pochi/README.md` の集約ルール）。
6. **事実だけを記録できること**。保存・表示するのはフェア名・商品名・価格（税込、税抜）・開始日・終了観測日・出典URLだけ。公式の説明文・画像・栄養・アレルゲンは、保存も表示も、パーサで読むこともしない。

下調べのルール:

- リクエストは少なく、同じ宛先へ3秒以上あける。ページは1回だけ取り、手元（scratchpad など）に保存して、以降はそのコピーでパーサを書く。
- 本番の定期実行の上限（後述）とは別に、開発中の取得も最小限にする。
- 下調べの結果は、対象外と判断した場合も含めて、PRの説明かレポートに残す（第7章）。

## 2. 触るファイルと、チェーンごとに書く部分

### 共通エンジンが受け持つもの（触らない）

`scripts/crawl.py` の次の部分。チェーンごとに書き直さない。

| 役目 | 場所 |
|---|---|
| 保存（1商品1ファイル `data/products/{slug}/{pid}.json`、既存は丸ごと上書きしない） | `save_product` `load_product` `Run.finish` |
| 取得の上限と間隔 | `Getter` `Throttle` |
| robots.txt | `Robots` |
| 追跡（最終確認日・価格履歴・再登場） | `touch_seen` `record_price` `start_new_season` |
| 終了判定（別の日に連続2回の消失で `ended`） | `apply_missing` `MISSES_TO_END` |
| 歯止め（新規の急増で保留） | `burst_filter` `burst_threshold` |
| 記録対象の急減の検知 | `ratio_ok` |
| 一覧の不完全（`list_failed`）・連続日数（`_health`）・通知用の要約 | `collect_problems` `update_health` `save_run_summary` |
| 商品レコードの骨格 | `base_product` `set_initial_price` |
| 開始日の照合 | `find_launch` `apply_launch` `PressSources` `needs_launch` `launch_ref` |

### チェーンごとに書くもの

境界は「一覧の取得と、1商品の抽出」までがチェーンごと。それ以降は `Run.finish` に渡せば、共通エンジンが処理する。

1. **パーサ**（`scripts/parsers.py`）。ネットワークに触れない純粋関数にする。命名は `parse_<slug>_...`。
   - 構造が想定と違うとき（見出しが無い、一覧の欄が無い）は `ValueError`。呼び出し側が「構造変更の疑い」として扱う。
   - 構造は正しいが商品が0件のときは、空のリストを返す。
   - コメントアウトされた部分は読まない（`_strip_comments`）。説明文・画像のキーは読み取らない。
   - 価格の書式「1,790円（税込1,969円）」には共通の `_PRICE_PAIR_RE` と `parse_price_pair` がある。別の書式（`¥1,099（税込¥1,209）` など）は専用の正規表現を足す。ジョナサンの `parse_jonathan_alt` はこの書式を取れずに0件になる例。
   - 識別キー（pid）をここで作る（下の「識別キーの決め方」）。
2. **クローラ関数**（`scripts/crawl.py`）`crawl_<slug>(getter, pending, stats, today=None)`。次の流れで書く。
   1. `run = Run(chain, pending, stats, today)` を作り、`Robots` で許可を確かめる。
   2. 一覧→各ページを `getter(chain, url)` で取る。取るたびに `st["list_requests"] += 1`（ニュースなど補助の取得は `st["detail_requests"]`）。
   3. 完全に取れたかを `complete` フラグで持つ。取れないページ・価格が1件も取れないページ・上限超過のときは `False` にして続ける。
   4. `entries = {pid: {pid, name, price, price_max, price_excl_tax, fair, official_url, ...}}` を作る。`price` と `price_max` のキーは必須（`touch_seen` が読む）。
   5. `build(e)`（新規レコードを作る。`base_product` + `fair` `limited_kind` `price_excl_tax` `price_note` `official_url` `stores_note` `source_list`）、`refresh(p, e)`（既存の更新）、開始日を拾うなら `enrich(p, e, is_new)` を用意して `run.finish(entries, complete, build, refresh, enrich)` を呼ぶ。
   - `BlockedError` を受けたら `run.block(...)` して `return`。
   - `run.finish` の前に `return` すると `list_ok` が `False` のまま残り、`list_failed` として通知に出る（終了判定はしない）。構造変更の疑いはこの経路にする。
3. **登録**: `crawl.py` 末尾の `CRAWLERS = {"dennys": ..., "jonathan": ...}` に1行足す。`main()` の引数（`python3 scripts/crawl.py <slug>`）もここから決まる。
4. **設定**（`config.json`）。足すキーは次のとおり。

| キー | 内容 |
|---|---|
| `chains` | `slug` `name` `base_url` `color` `color_dark`。並びがトップのグループ順になる |
| `chain_official` | `source`（「○○公式サイト」）`url` `menu_url`。商品ページの出典と公式リンク |
| `request_interval_seconds` | 3以上（コードの下限は1秒だが、方針は3秒以上） |
| `max_requests_per_run` | **必ず足す**。未設定のチェーンは `Getter` が上限なしで通す |
| `new_burst_min_by_chain` | 歯止めの下限（第3章） |
| `netaful_tags` `netaful_search_terms` `netaful_title_filters` | ネタフルのレビュー連携。`netaful_tags` のキーが取得対象になる（タグが無ければ `null` と検索語） |
| `netaful_title_always` / `netaful_title_excludes` | タイトル判定。一般名と紛れる名前のチェーンは除外語を足す |
| チェーン固有 | ジョナサンの `jonathan_max_pages` `jonathan_skip_slugs` `jonathan_exclude_names` のように、`<slug>_...` で名前をそろえる |

5. **文言（手で直す）**: `config.json` の `top_title` `site_tagline` `site_description` と、`about` の3段落目（開始日の説明がチェーンごとに書いてある）。
   `notify.py` の `CHAIN_LABEL`（足さないと通知にslugがそのまま出る）。`parsers.py` `crawl.py` `fetch_netaful_reviews.py` の冒頭の docstring にあるチェーン名の並び。
6. **自動で追従するもの**: `generate_site.py` の `CHAIN_LIST_TEXT`（`config.json` の `chains` から作る）、チェーンページ `/chains/{slug}/`、絞り込み、sitemap、色の変数（`--{slug}`）。コードは触らない。

### デニーズとジョナサンの違い（実例）

| | デニーズ | ジョナサン |
|---|---|---|
| 一覧 | `/menu/` の `ul.fairArea` から各フェアページを毎回たどる（`parse_dennys_fair_links`） | `/jonathan/menu/fair/index.html` と、メニュートップのおすすめスライドの先（`parse_jonathan_menu_links`） |
| 商品の抽出 | HTMLの `menuTitle`+`price` の組と `dt`/`dd`（`parse_dennys_fair_page`） | `img` の `alt` を価格で区切って分解（`parse_jonathan_alt`） |
| 識別キー | 商品ページのパス。無ければフェアのパス+名前のハッシュ | フェアのパス+名前のハッシュ |
| 開始日 | `/news/` の見出し・リード文を `find_launch` で照合（`enrich`） | なし（記録開始日） |
| 不完全の判定 | フェア欄が無い／0件、どれかのフェアページが取れない、価格が1件も取れない | メニュートップが取れない、ページ数が上限超過、フェアページ（や商品が載っていたページ）が空 |

### 識別キー（pid）の決め方

- 商品ごとの安定したURLやIDが公式にあれば、それを使う（デニーズの商品ページのパス）。
- 無ければ `stable_id(接頭辞, 名前)`（名前を `normalize_name` で正規化したSHA-1の先頭10桁）。接頭辞はフェアやページの名前にする。
- **名前が変わると別商品になる**。旧商品は2日の消失で `ended`、新しいほうは新規として記録され、歯止めの数にも入る。公式が名前を直しても追えない、という既知の限界として README に書く。
- pid は `data/products/{slug}/{pid}.json` と `/items/{slug}-{pid}.html` のURL、ネタフルのレビュー照合のキーに使われる。**公開後に pid の作り方を変えない**（全商品が入れ替わったとみなされ、歯止めで保留される）。
- 同じ名前が複数ページに載るときは、先に巡回したページの1件だけを残す（ジョナサンの `names_seen`）。

## 3. 歯止めの件数と、リクエスト上限の決め方

### 歯止め（`new_burst_min_by_chain`）

`burst_threshold` の式は `max(new_burst_min_by_chain[slug], int(一覧の項目数 × new_burst_ratio))`。`new_burst_ratio` は全チェーン共通の0.6。
新規候補（baselineにも既存レコードにも無い項目）がこの値を超えると、その回はそのチェーンの新規を記録せず、終了判定もしない（`data/pending.json` の `_suspected_restructure`）。3日続くと通知が「要判断」に変わる。初回（baselineなし）は対象外。

下限は「本物のフェアの一斉投入では止まらない値」にする。これは公式のID体系が変わった事故（松屋の一斉更新）を止めるための仕組みで、止めすぎると新作を取り逃す。

- 実績: デニーズ20、ジョナサン15。初回の一覧はデニーズ20件、ジョナサン14件（`data/baseline_ids.json`）。README には「フェアは1回に5〜15品ほど出る」と書いてある。
- 教訓: カフェポチのタリーズは下限が6だったため、ホリデーの一斉投入10品が保留された。2026-11-22に16へ引き上げた（`cafe-pochi/README.md`）。
- 決め方（推奨。リポジトリの規則ではない）: 下調べで見た1回の投入の最大品数より、十分に大きくする。分からなければ、デニーズ・ジョナサンと同じ15〜20から始める。保留されたときの解き方は README の「運用手順」にある。
- 変えたら、README の「しきい値・上限」の表と `config.json` を一緒に直す（AGENTS.md の指示）。

### リクエスト上限（`max_requests_per_run`）

数える対象は robots.txt・一覧・各ページ・ニュースのすべて（`Getter` が数える）。超えると例外になり、そのチェーンは `errors` になる。

- 見積もり: 通常日の実測の数倍。デニーズは通常日で約6〜8リクエスト、上限25。ジョナサンは約5リクエスト（初回は4）、上限5で、ほぼ余裕がない。
- フェアのページ数が増減するチェーンは多めにし、増減しないチェーンは実測に近づける。上限が実測に近いほど、ページが増えたときに「不完全」で止まる。
- 間隔3秒×上限の合計が、`update.yml` の `timeout-minutes: 30` に収まること。あわせて `update.yml` の「リクエスト上限の合計」のコメントを直す。

## 4. テスト

テストはネットワーク不要。**ファイルのfixtureは置かず、`tests/synth.py` が公式ページの構造（クラス名・価格の書式・altの並び）を再現した最小限のHTMLを文字列で作る**。取得は `tests/helpers.py` の `FakeSite`（URLごとに応答か例外を返す偽の取得器）、保存先は `TempData`（一時ディレクトリへ差し替え）を使う。

1. 公式ページを手元に保存し（第1章のルールで1回だけ）、構造に必要な部分だけを `tests/synth.py` に関数として写す。説明文や画像のURLは写さない（alt の説明文の断片を入れるのは、パーサが読まないことの確認だけにする）。
2. 書くテスト。既存の `tests/test_parsers.py` と `tests/test_crawl.py` の同名のテストを手本にする。
   - パーサ: 一覧のリンク抽出、商品の名前・価格・pid、コメント内の商品を読まない、説明文を読まない、価格なしは空・構造崩れは `ValueError`、pid が実行をまたいで安定する。
   - 巡回: 初回に全件記録される、保存キーに説明文・画像が無い、リクエスト数が上限内、別の日2回の消失で終了、再登場と価格変更、一覧の不完全（0件・取得失敗）で終了しない、`BlockedError` で止まる、robots の Disallow、歯止め（本物のフェアは通り、構造変更は保留）、`burst_threshold` の値。
   - 生成: 商品ページに出典・公式リンクが出る、チェーンページができる（`tests/test_generate_site.py`）。
3. **既存テストの直し**: `tests/test_crawl.py` の `TestConfig`（チェーンのslug一覧・上限・歯止めの値をそのまま比べている）と、`tests/test_generate_site.py` のトップの `<title>` の比較（`top_title` を変えるため）。
4. 実行。このMacの `python3`（3.9.6、`/usr/bin/python3`）で確認済み（2026-11-23時点で92件が通る）。CIは3.12。書き方は3.9でも動くものにする（パターンマッチなどは使わない）。

```bash
cd /Users/kogure/Desktop/Claude/famires-pochi
python3 -m unittest discover -s tests                         # 全部
python3 -m unittest discover -s tests -p "test_parsers.py"    # ファイル単位
python3 -m unittest discover -s tests -k burst                # 名前で絞る
```

実サイトでの確認は、リポジトリを一時ディレクトリにコピーして `python3 scripts/crawl.py <slug>` を1回実行する（`crawl.py` は自分のあるリポジトリの `data/` に書くので、コピー先なら作業ツリーが汚れない）。
結果の件数・リクエスト数・`list_failed` の有無・商品の例を、第7章に載せる。**この実行が公式への実リクエストなので、1回だけにする**。

## 5. 公開までの流れ

1. `git checkout main && git pull` で最新を取り込み、未マージのPRや作業中のブランチが無いことを確かめる（同時作業の禁止）。
2. ブランチを切って実装する。コミットしたらPRを出す。mainへ直接pushしない。AGENTS.md の範囲外（URL・canonical・広告・外部APIの契約）は変えない。
3. PRの説明に、変更内容・検証・見送ったことと未確認のこと、第7章の材料を書く。
4. **マージはオーナーの確認後**。勝手にマージしない。レビューはモルに頼む。
5. マージ後の更新は、Cloud Scheduler の `famires-pochi-update`（毎朝9:30 JST）が `update.yml` を起動して行う。
   待たずに確かめたいときは `update.yml` を手動実行（`workflow_dispatch`）してよいが、公式へのリクエストが1回分増える。するかどうかはオーナーに聞く。
6. 本番での確認（https://famires.netaful.jp/）:
   - トップ: 新チェーンのグループが出る、件数が手元の実行と合う。
   - `/chains/{slug}/`: 商品が並ぶ。
   - 商品ページを2件: 価格（税込・税抜）、開始日（または「記録開始日」の注記）、出典と公式ページへのリンクがある。**説明文と画像が無い**。
   - `data/pending.json` の `_health` に新チェーンが無い（連続で問題が出ていない）。`list_failed`・`blocked` の通知が来ていない。
7. **要らないもの**: Cloud Scheduler・PAT・DNS・GA4・AdSense は、サイト単位の設定なのでチェーン追加では触らない。
8. **docs/ と data/ について**: どちらも Actions が生成・更新する。PRに含めるかは、過去のPR（アイコン・OGPのPR）は `docs/` の再生成を含んでいた。`data/` は、手元の実行結果をPRに入れない運用を推奨する（初回の記録は本番の実行に任せる）。明文化された規則はないので、迷ったらレビューで聞く。

## 6. あわせて更新する場所

チェーン追加だけなら、ポチフル・各サイトのフッター・ローテーター・新発売ポチの一覧は、サイト単位の掲載なので**原則不要**。ただし文言にチェーン名を並べている次の箇所は直す。
2026-11-23時点で、`grep` で「デニーズ・ジョナサン」を探して出た場所は次のとおり。

| 場所 | 直す内容 | 備考 |
|---|---|---|
| `famires-pochi/config.json` | `top_title` `site_tagline` `site_description` `about` | 第2章 |
| `famires-pochi/AGENTS.md` | 対象サイトの説明、`max_requests_per_run` の数字 | 数字は第3章の設定と合わせる |
| `famires-pochi/README.md` | 冒頭、収集の前提（チェーンの節）、しきい値の表、既知の限界、規約の確認状況 | |
| `pochi-branding/sites.py` | `famires` のキャッチ（OGP・アイコンの元） | 直したら `python3 make_branding.py famires` で `docs/assets/` に再生成して配置（ヘッドレスChrome使用。**未実行**。動作未確認） |
| `pochi-full/data/sites.json` | `famires` の `description`（「デニーズ・ジョナサンの…を記録」） | `build.py` で `docs/` を再生成。pochi-fullは別リポジトリなのでPRを分ける |
| `netafull-pochi-rotator/pochi.js` | `NFPR_POCHIS` の `famires` の `title` | WordPress側への反映（zipの再作成とアップロード）はオーナー作業。ネタフルの配信は1時間キャッシュ |

`related_sites`（各ポチの `config.json`）の説明は「ファミレスの期間限定フェア」で、チェーン名を含まないので直さない。
ファミレスポチは `feed.json` を持たないので、ポチフルの新着ダッシュボードにも関係しない（現状）。

**新発売ポチ（`shinhatsubai-pochi`）**: チェーンは自動で拾う。`scripts/aggregate.py` が `famires-pochi` の `config.json` の `chains[].name` で表示名を作り、`data/products/<slug>/` の商品を読む。コードの手直しは要らない。
ただし次の2点は確かめる。

- 開始日が取れない商品は載らない（ジョナサンが全件なしのため載らない）。新チェーンも開始日の一次情報が無ければ載らない。
- アイコンはカテゴリーが全件なしのため、商品名から推定する（`icon_guess.py`、`app.py` の `GUESS_SITES` に `famires` がある）。新チェーンの商品で外れが多いかは**未確認**。反映後に新発売ポチで見て、外れがあれば `icon_guess.py`（正本は新発売ポチ側）の規則を直す、という別作業にする。

## 7. モルにレビューを頼むときに渡すもの

PRの説明か、同じ内容のファイルに、次をそろえる。

1. **下調べの結果**（第1章の6点それぞれの結論）: robots.txt の該当行、規約の条文の要旨と確認日・確認したURL（読めなければ「未確認」）、ボット対策の有無、価格がテキストで取れる根拠（取れたHTMLの該当箇所）、開始日の一次情報の有無。
2. **PRのURL**。
3. **初回記録の件数と例**（一時コピーでの実行結果）: 記録対象の件数、商品の例を3〜5件（名前・価格・開始日とその由来・pid）、開始日が取れた件数と取れなかった件数。
4. **リクエスト数**: 一覧とニュースの別、合計、設定した `max_requests_per_run` との比較。`list_failed` と `blocked` が無かったこと。
5. **設定値の根拠**: `new_burst_min_by_chain` の値（第3章）、`max_requests_per_run` の値。
6. **確認できなかったこと**: 「未確認」と書いた項目を、そのまま一覧にする。
7. **やらなかったこと**: OCR をしない、説明文・画像を保存しない、など。

追加して公開するかどうか、規約が未確認のまま始めるかどうかは、オーナーが決める。
