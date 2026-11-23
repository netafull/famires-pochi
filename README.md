# ファミレスポチ

デニーズ・ジョナサン・ココスの**期間限定フェアのメニュー**を1日1回巡回して記録し、フェアが終わって公式サイトから消えても残るアーカイブにするサイト
（公開予定 https://famires.netaful.jp/ ）。価格（税込・税抜）・開始日・終了を確認した日を、あとから引ける形で残す。

姉妹サイト（電書ポチ・家電ポチ・林檎ポチ・漫画ポチ・コンビニポチ・ファストフードポチ・カフェポチ ほか）と同じく、
pip依存なしのPython標準ライブラリだけ（HTML解析は正規表現、PDFは扱わない）。
**構造は `cafe-pochi`（ファストフードポチ由来）の汎用エンジン**（保存スキーマ・終了判定・歯止め・価格履歴・再登場・run_summary/_health・pending.json・
ntfy通知・サイト生成・category icon・sitemap）をそのまま使い、チェーン固有の取得（`parse_dennys_*` / `parse_jonathan_*` / `parse_cocos_*` と
`crawl_dennys` / `crawl_jonathan` / `crawl_cocos`）だけを作っている。サイトの色は赤系 `#C62828`（ダークモード `#EF9A9A`）。

## 使い方

```bash
python3 scripts/crawl.py                    # 全チェーンを巡回して data/products/ に蓄積
python3 scripts/crawl.py jonathan           # チェーンを指定すると、そのチェーンだけ巡回する
python3 scripts/fetch_netaful_reviews.py    # ネタフルの記事を取得・商品とひも付け（ネタフル自身のAPI。公式サイトには触らない）
python3 scripts/generate_site.py            # docs/ 一式を生成
python3 -m unittest discover -s tests       # 公式ページの最小限の写し（fixture）でテスト。ネットワーク不要
```

定期実行は `.github/workflows/update.yml`（`workflow_dispatch` のみ。scheduleもpushトリガーも無い）を **Cloud Scheduler から起動**する
（ジョブ名 `famires-pochi-update`、毎朝1回。他の食ポチと同じPAT・同じ書き方）。通知の `NTFY_TOPIC` は GitHub Secrets（コードに書かない・未設定なら通知なし）。
**開発中は公式サイトを必要最小限しか叩かない。**

## 何を記録するか（事実だけ）

- 記録・表示する: **フェア名・商品名・価格（税込を主表示、税抜も保存）・開始日・終了（観測）日・出典URL（その商品が載っていた公式ページ）**。
- **保存も表示もしない: 説明文・画像・画像URL・栄養成分・アレルゲン。** パーサは説明文・画像のキーを読み取りもしない（テストで確認している）。
  ニュースの見出し・リード文は**開始日の照合のためにメモリ上で読むだけで、保存しない**（保存するのは日付と、照合に使った見出しの文字列・URLだけ。見出しは `news_title`）。
- 初回から、その時点でフェアに載っている商品を**全部記録**する（`data/baseline_ids.json` は2回目以降の歯止めの判定にだけ使う）。
- 商品1件1ファイル `data/products/{dennys|jonathan|cocos}/{id}.json`。既存ファイルは丸ごと上書きしない（初回取得が正）。更新するのは last_seen_at / status / price_history 等の追跡項目と、まだ空の開始日だけ。
- 各商品ページに「出典：○○公式サイト（取得日）」と公式ページへのリンクを付ける。aboutに「記録しているのは事実情報だけで、説明文・画像は載せていない」と書いてある。
- 規約: デニーズは「ご利用に際して」（dennys.co.jp/dennys-japan/copyright.html）を確認済み（複製は私的使用の範囲まで・著作権法を超える転載は控える旨。自動取得・クローラー・営利目的の記載はなし）。
  ココスは「当サイトについて」（cocos-jpn.co.jp/aboutsite/）を2026-11-23に確認済み（一般的な著作権の注意のみ。自動取得・クローラーを名指しで禁じる条文はなし）。
  **すかいらーく（ジョナサン）の規約（corp.skylark.co.jp/sitepolicy/）は未確認**。そのため全チェーンとも事実のみを記録する。

## 収集の前提（どのページから何を取るか）

### デニーズ（https://www.dennys.jp）

- robots.txt は404（制限なし）。ボット対策なし。UAは自前（`FamiresPochi/1.0 (+https://famires.netaful.jp/)`）。
- `/menu/` の **FAIR欄（`<ul class="fairArea">`）** から各フェアページ（例 `/menu/oimo/` `/menu/collaboration17/`）のリンクを**毎回たどる**（ページ名は固定でない）。
  欄の外（グランドメニュー等の定番）は対象外。HTMLコメントで無効化されている部分は読まない（「新登場」「期間限定」バッジはコメントなので使わない）。
- 各フェアページから **`<p class="menuTitle">` + `<p class="price">「1,790円（税込1,969円）」`** の組と、セット欄の `<dt>名前</dt><dd>価格</dd>` を商品として取る。
  ルビ・`<br>` は名前に混ぜない。ページ名は `h1.label`（フェア名）。
- **識別キー**: 商品ページへのリンク（`/menu/dessert/sweet-potato-sundae/`）があればそのパス（`dessert-sweet-potato-sundae`）、無ければ「フェアのパス＋正規化した商品名」のハッシュ（`collaboration17-4b2a681e04`）。
  リンクが無い商品は名前が変わると別商品になる（既知）。
- **開始日**: `/news/`（HTML。1リクエスト）の各項目の見出し・リード文から「10月14日（水）スタート」「10月28日（水）販売開始」を拾い、
  ①商品名 ②「～」より前の商品名 ③フェア名 の順に照合できたときだけ使う（`launch_date_source` は `official_news` / `official_news_body`（リード文由来）/ `official_news_fair`（フェア名由来））。
  ②③と本文由来の日付は商品ごとの開始日とずれることがあるので、商品ページに注記が出る。取れなければ**記録開始日**を開始日として表示する。
  ニュースPDFは読まない。`/news/` は当年分だけなので、年をまたぐと前年のフェアの開始日は拾えない。
- 一部店舗（新宿西口・赤坂駅前・浅草雷門など）は価格が違う旨を、商品ページの「取り扱い」に一文で出している。

### ジョナサン（https://www.skylark.co.jp/jonathan/）

- robots.txt は `User-agent: *` で `/jonathan/` を禁止していない。ボット対策なし。`corp.skylark.co.jp`・`takeout.skylark.co.jp` には**触らない**。
- `/jonathan/menu/fair/index.html`（フェアページ）と、メニュートップ `/jonathan/menu/` のおすすめスライドから辿れる他のページ（`jonathan_skip_slugs` を除く。現在はデザートの `dessert`）を巡回する。
  常設・価格がalt以外の形式のページ（`collab` `recommend` `recommend2` `souppasta` `drink_bar`）は config で除外している。
- 価格はHTML本文になく、**img の alt に「商品名 1,699円（税込1,869円）。…」の形で複数商品が1つの長い文字列に入っている**。`parse_jonathan_alt` が分解する:
  価格の直前の区切り（`。` `、` `：`・直前の価格の終わり。括弧の中の区切りは無視）から価格までを商品名とする。
  「＋180円」のような追加料金は商品にしない。名前が3文字未満・80文字超（説明の断片）は捨てる。`jonathan_exclude_names`（ドリンクバーセット）は記録しない。
  別形式の価格表記（`¥1,099（税込¥1,209）`）のページは取れない（0件）。
- **識別キー**: フェアのパスの名前（`fair` `dessert`）＋正規化した商品名のハッシュ（`fair-9abfb153dd`）。**開始日は記録開始日**（プレスリリースは取らない）。
  同じ名前が複数ページに載るときは先に巡回したページ（fair → 他）の1件だけ。
- 巡回するページ数は `jonathan_max_pages`（3）まで。スライドのページがこれを超えると超えた分が見えず、「一覧が不完全」として終了判定をしない（通知に出る）。

### ココス（https://www.cocos-jpn.co.jp）

- robots.txt は存在しない。しかも**存在しないパスには403でエラーページが返るサーバー仕様**のため、robots.txt の取得が
  `BlockedError` になる。`crawl_cocos` だけ `Robots` のサブクラス（`CocosRobots`）で「robots.txt が無い=制限なし」として扱い、
  実際のページ取得でブロックされた場合はそちらで止める（共通エンジンは触っていない）。ボット対策は無い（2026-11-23確認）。
- フェアページ `/menu/fair/` の **「`<h2>フェア名</h2>` + `<ul class="img_link type_menu_list">」** の組から取る。商品は各 `<li>` の
  **`<div class="name">`（商品名）と `<div class="price">`（価格）**。価格は円表記ではなく **「¥590(税込¥ 649)」の ¥ 表記**
  （税込側は ¥ の後ろに空白が入る）なので、専用の `parse_price_yen_pair` で取る（共通の `parse_price_pair` は円表記用）。
- **識別キー**: 商品詳細ページ（`/menu/fair/<フェアのディレクトリ>/<商品>.html`）のパス（`limited_sweets-roasted_sweet_potato_crepe2611`）。
  リンクが無い商品は「cocos＋正規化した商品名」のハッシュ。詳細ページのファイル名が変わると別商品になる（デニーズのリンク方式と同じ限界）。
- **開始日**: `/news/<年>/menu/`（お知らせのメニュー分類、1ページ目だけ）の見出しの「【11月19日(木)開始】」を、
  デニーズと同じ `find_launch` で ①商品名 ②「～」より前の商品名 ③フェア名 の順に照合できたときだけ使う
  （`launch_date_source` は `official_news` / `official_news_fair`）。一覧にリード文は無いので本文由来の照合は無い。
  ニュースは当年分だけなので、年をまたぐと前年のフェアの開始日は拾えない。取れなければ**記録開始日**。
- フェアページ冒頭の注記どおり、一部の店舗で取扱商品・販売時間帯・価格が異なる旨を、商品ページの「取り扱い」に出している。
- 「追加カシスシロップ」のような追加オプションは、単品の商品ではないため記録しない（`config.json` の `cocos_exclude_words` に「追加」を入れ、名前にこの語を含むものを落とす。新発売ポチへ「新商品」として流れてしまうのを防ぐため）。

## 販売状況の追跡（サイトの核・共通エンジン）

- 巡回で一覧に居たら `last_seen_at` を更新し `status=on_sale`。価格が前回と違えば `price_history` に追記。
- **そのチェーンの一覧取得が全部成功した回だけ**、一覧から消えた商品を数える。**別の日に連続2回**見つからなかったら `status=ended`、`ended_observed_at` にその日付（同じ日に何度実行しても1回）。
  **終了日は「公式のフェアページから消えたのを確認した日」**で、公式の最終販売日ではない（サイトにもそう書く）。
- 終了後に再登場したら `on_sale` に戻し、`relaunches` に記録、昨季の期間を `seasons` に残し、今季の開始日は未確定に戻す。
- **一覧が不完全（構造変更の疑い）= `list_failed`**。次のどれでも、その回は新規記録以外の終了判定をしない:
  フェア欄が無い／0件・どれかのフェアページが取れない（404・タイムアウト・h1なし）・**フェアページから価格が1件も取れない**・robots.txtでDisallow・歯止めの保留・
  ジョナサンのメニュートップが取れない／ページ数が上限超過／フェアページ（または商品が載っていたページ）から価格が取れない。
  ブロック（403・429・チャレンジ）は `blocked`、例外は `errors`（どれも終了判定をしない）。詳細ページ単発の失敗は通知しない（翌日に再試行）。
- **記録対象の急減の検知**（`data/list_state.json`）: 記録対象が前回の半分未満（前回8件以上のとき）になったら、**3日続くまで**終了判定をしない。

## しきい値・上限

| 項目 | デニーズ | ジョナサン | ココス | 場所 |
|---|---|---|---|---|
| 1回の実行のリクエスト上限 `max_requests_per_run` | 25 | 5 | 10 | `config.json` |
| リクエスト間隔 `request_interval_seconds`（コードの下限は1秒） | 3秒 | 3秒 | 3秒 | `config.json` |
| 歯止めの下限 `new_burst_min_by_chain` | 20 | 15 | 20 | `config.json` |
| 歯止めの比率 `new_burst_ratio` | 0.6 | 0.6 | 0.6 | `config.json` |
| 終了判定 | 別の日に連続2回消失 | 同左 | 同左 | `crawl.py` の `MISSES_TO_END` |
| 急減の検知 | 前回8件以上で半分未満→3日続くまで保留 | 同左 | 同左 | `crawl.py` の `RATIO_*` |
| ジョナサンの巡回ページ数 `jonathan_max_pages` | － | 3 | － | `config.json` |

- **歯止め（burst guard）**: 新規候補（baselineにも既存レコードにも無い項目）が `max(new_burst_min_by_chain, 一覧の項目数×new_burst_ratio)` を超えたら、
  公式のID体系・ページ構造の変更とみなして、その回はそのチェーンの新規を記録せず終了判定もしない（`pending.json` の `_suspected_restructure`、`run_summary.json` の `suspected`）。
  3日連続の保留で通知が「要判断」に変わる。**初回（baselineが無い）は対象外。** フェアは1回に5〜15品ほど出るので、最初から高めにしてある。
- 実測（2026-11-23 初回）: デニーズ5リクエスト（robots・/menu/・フェア2・news）、ジョナサン4リクエスト（robots・メニュートップ・fair・dessert）。通常日の合計は10前後。上限に十分な余裕がある。
  ココスは2026-11-23の初回確認で3リクエスト（robots・フェアページ・news）、10件を記録し、開始日は10件すべて取得できた（商品名由来1件・フェア名由来9件）。

## 運用手順

- **保留（歯止め）の解き方**: 保留は自動では再開しない場合がある。まず公式サイトを見て、本当にフェアが一斉に入れ替わっただけなら `config.json` の
  `new_burst_min_by_chain` のそのチェーンの値を一時的に新規件数より大きくして `python3 scripts/crawl.py <チェーン>` を1回実行し、記録されたら値を戻す。
  構造変更なら `scripts/parsers.py` を直す。翌日以降に新規候補が閾値以下に戻れば自然に再開する。
- **上限の変え方**: `config.json` の `max_requests_per_run`（ジョナサンのページを増やすときは `jonathan_max_pages` と一緒に）。上げるときは公式サイトへの負荷を考え、間隔3秒以上を保つ。
- **通知の一時停止**: リポジトリ変数 `NTFY_PAUSED=true`（`gh variable set NTFY_PAUSED --body true -R netafull/famires-pochi`、再開は `gh variable delete NTFY_PAUSED -R netafull/famires-pochi`）。
  要約・失敗の通知ステップをまとめて飛ばす（失敗通知も止まるので、停止中は更新が止まっても鳴らない）。
- **定期実行**: Cloud Scheduler のジョブ `famires-pochi-update` が毎朝1回 `workflow_dispatch` を叩く。GitHubのscheduleは使わない。
- **ブロックされたら**: 回避（UA偽装等）はしない。`blocked` が通知に出たら止めて、運営者が判断する。
- ジョナサンの除外ページを変える・追加するとき（`jonathan_skip_slugs`）は、実際のalt（`img alt`）に「N円（税込M円）」の形があるかを先に確認する。

## サイトの構成（docs/）

- トップ（チェーンごとにグルーピング・開始日順・販売状況の絞り込み・メニュー名検索・ネタフルの最新レビュー）、`/archive/` と `/archive/YYYY-MM/`、
  `/chains/{dennys|jonathan|cocos}/`、`/items/{chain}-{id}.html`（価格・税抜価格・フェア名・価格履歴・販売期間・出典と公式リンク。**説明文・画像は無い**）。
- sitemap.xml、robots.txt（AI学習専用クローラーを拒否）、OGP、CNAME（`famires.netaful.jp`）、.nojekyll。
- 広告（AdSense）とGA4は `config.json`（`adsense_client_id` / `adsense_ad_slot` はカフェポチと同じ値、`ga_measurement_id` は発行済みの値）。
  フッターの開示の一文は実際の設定（AdSense・GAの有無）に合わせて出る。
- ネタフルのレビュー連携（`fetch_netaful_reviews.py`）は、タグが無いので記事の全文検索（デニーズ・ジョナサン・ココス）＋タイトル判定。レビュー記事のサムネイルはネタフル自身の画像。
- アイコン類（favicon・logo・OGP）は**まだ作っていない**（`docs/assets/` には category icon だけ）。`~/Desktop/Claude/pochi-branding/` での生成はオーナー確認後。

## 既知の限界

- **終了＝フェアページからの消失**。公式の最終販売日ではなく、フェアのページが閉じられただけで店頭にはまだあることもある。
- ガスト・バーミヤン・夢庵は価格が画像だけ（OCRは誤読がそのまま記録になるのでしない）ため対象外。ガストのテイクアウトサイトのJSONは店内価格と違うので使わない。
- デニーズは `/menu/` のFAIR欄に載るフェアだけ。ハロウィン等のニュースだけで告知されるフェア（FAIR欄に無いもの）、冬ギフト・おせちなど価格の書式が違うページは拾わない。
- デニーズの開始日はニュース見出し・リード文の照合で、拾えない商品が多い（初回: 20件中11件）。拾えなかったものは記録開始日。コラボの商品など、見出しに名前の出ないものは開始日が取れない。
- デニーズの商品でリンクの無いもの（コラボのセット等）は、名前が変わると別商品になる。
- ジョナサンは alt の文章構造に依存する。名前の区切りに使える `。` `、` `：` が無い文章や、別の価格表記（`¥1,099`）のページは取れない（取れなければ価格0件として「不完全」になるだけで、誤った記録はしない）。
  「揚げなす＆モッツァレラ入り」のような、直前の商品の派生（親の名前が前の文にある）は名前だけの記録になる。
- ジョナサンは開始日が常に記録開始日（プレスリリース未使用）。
- ココスの開始日はお知らせ（当年分・メニュー分類の1ページ目）の見出し照合で、見出しに商品名・フェア名と開始日がそろわない商品は取れない。
  ココスの識別キーは詳細ページのファイル名由来なので、公式がファイル名を変えると別商品になる（旧商品は終了、新しいほうは新規として記録される）。
- 価格は店舗で異なる場合がある（デニーズは新宿西口店など一部店舗が別価格）。表示は公式ページの標準価格。
- 公式のHTML構造の変更に弱い。壊れたら list_failed／保留として通知され、終了判定はしない。

## 公開前に運営者がやること（未実施）

1. GitHubリポジトリ（案 `netafull/famires-pochi`）を作って push（Pages: `main /docs`）。
2. DNS: `famires.netaful.jp` の CNAME（`docs/CNAME` は用意済み）。
3. Cloud Scheduler: `workflow_dispatch` を毎朝1回叩くジョブ `famires-pochi-update`。
4. 通知を使うなら GitHub Secrets に `NTFY_TOPIC`。
5. アイコン類（pochi-branding）の生成・配置、ポチフル・新発売ポチ・他サイトの `related_sites` への追加。
6. すかいらーく（`corp.skylark.co.jp/sitepolicy/`）の規約の目視確認。
7. 公開後、初日の実行結果（件数・list_failed の有無）を確認する。
