# ビッグボーイ追加レポート（2026-11-23）

ブランチ `maru/add-bigboy`（main から分岐。maru/add-cocos とは独立で、ココスの変更は取り込んでいない）。
手順書 `ADDING_A_CHAIN.md` 第2〜6章に沿って実装した。マージ・PR作成はしていない（レビューはモル）。

## 1. 下調べの結果（第1章の6点、2026-11-23確認）

対象：ビッグボーイ、公式サイト https://www.bigboyjapan.co.jp/
（ヴィクトリアステーション・ビッグボーイダイニングとの共用サイトでフェアは共通開催。記録はビッグボーイとして行う）

1. **robots.txt**：存在しない（404）。Disallow の宣言なし
2. **規約**：サイトポリシー・ご利用条件にあたるページ自体が存在しない。サイトマップ・フッター・会社情報ページを確認しても見当たらない。
   /privacy/（個人情報保護方針）にも複製・転載・自動取得を禁じる条文なし
3. **ボット対策**：なし（指定UA `FamiresPochi/1.0` で全ページ200、チャレンジなし）
4. **価格・商品名**：グランドメニュー https://www.bigboyjapan.co.jp/menu/grand/ の「期間限定メニュー」欄に、
   商品名が `<h4 class="name">` の `<span class="main">`、価格が `<p class="price">` のHTMLテキスト（税抜＋税込併記）。
   価格は「¥」記号で、¥ と数字は別タグに分かれている（`<span class="yen">¥</span>1,490` 形式）。
   実例：「牡蠣フライ＆大俵ハンバーグ」¥1,490（税込¥1,639）。サイズ別に価格が複数ある商品がある
5. **開始日**：ニュースのフェア記事（例：/news/fair/6555.html）に見出し・本文で開始日が明記される
   （月日＋曜日だけの表記で、年は記事の掲載日 `<p class="date">` から補う）。フェア一覧 https://www.bigboyjapan.co.jp/fair/ の見出しでも確認できる
6. **事実だけの記録**：可。終了日は記事に明記されないため、終了判定はメニューページの期間限定欄からの消失で判定する（ジョナサンと同じ方式）

## 2. 変更ファイルと要点

- `scripts/parsers.py`：ビッグボーイ節を追加
  - `parse_bigboy_price_pair`：¥ 表記専用の価格パーサ（共通の `parse_price_pair` は円表記用で使えないため自前で追加。¥ と数字が別タグに分かれているのでタグを除いてから読む）
  - `parse_bigboy_grand_menu`：グランドメニューの「期間限定メニュー」欄（tab_title）だけを読む。他の欄（定番）は読まない。
    商品名は span.main のみ（付け合わせの注記 span.sub は含めない）。サイズ別の価格は price（先頭サイズの税込）・price_max（最大）・price_variants（内訳）に分ける。
    欄が無ければ ValueError、価格が取れた商品が0件なら items は空（呼び出し側が「不完全」とする）。pid は商品ページが無いので stable_id("grand", 名前)
  - `parse_bigboy_fair_links` / `parse_bigboy_news_article`：フェア一覧の記事リンクと、記事の掲載日・見出し・本文（照合用、保存しない）
- `scripts/crawl.py`：`crawl_bigboy` を追加し CRAWLERS に登録。開始日はデニーズ方式（find_launch/apply_launch）で、
  フェア一覧→ニュース記事（最大 `bigboy_news_max_articles`=8本）を遅延読み込みして商品名で照合する。
  フェア名は公式メニューに区別が無いため欄の名前「期間限定メニュー」で統一。出典はグランドメニューのページ自体
- `config.json`：chains に bigboy を追加（色は後述）、chain_official、request_interval_seconds=3、
  max_requests_per_run=20、new_burst_min_by_chain=15、bigboy_news_max_articles=8、
  netaful_tags=null＋netaful_search_terms「ビッグボーイ」＋netaful_title_filters＋netaful_title_always に追加。
  文言（top_title・site_tagline・site_description・about）にビッグボーイを追加
- `scripts/notify.py`：CHAIN_LABEL に bigboy を追加
- 文言の追随：`scripts/fetch_netaful_reviews.py`・`scripts/generate_site.py`（コメント）・`scripts/parsers.py`・`scripts/crawl.py` の docstring、
  `AGENTS.md`（対象サイト説明と max_requests の数字）、`.github/workflows/update.yml`（上限合計のコメント 30→50）
- `README.md`：冒頭、規約の確認状況、収集の前提にビッグボーイの節、しきい値の表に列追加と実測行、サイトの構成、既知の限界
- テスト：`tests/synth.py` にビッグボーイの fixture（grand menu／fair list／news article）、
  `tests/test_parsers.py` に TestBigboyPrice・TestBigboyGrandMenu・TestBigboyNews、
  `tests/test_crawl.py` に TestBigboyCrawl と TestConfig・CRAWLERS の期待値更新、
  `tests/test_generate_site.py` にタイトル期待値の更新と TestBigboyPage を追加

docs/ の再生成は含めていない（マージ後の update.yml が再生成する。ココス追加時の取り決めと同じ）。

## 3. 初回記録の結果（2026-11-23、一時コピーで1回だけ実行）

- 記録件数：**9件**（全件が期間限定メニュー欄の商品。作業ツリー側の data/ には入れていない）
- 開始日が取れた件数：**1件 / 9件**
  - 甘栗のモンブランファッジサンデー → 2026-10-20（official_news。記事 /news/fair/6555.html の見出しに商品名と日付）
  - 残り8件は開始日なし（記録開始日）。牡蠣フライフェアの記事（/news/fair/6506.html）は商品名を列挙せず
    「牡蠣フライフェア」「牡蠣フライ」としか書かないため、商品名での照合では結びつかない（フェア単位では10月6日開始と記事にある）
- 商品例：
  - `grand-8530e479a7` 牡蠣フライ＆大俵ハンバーグ：税抜1,490円／税込1,639円、サイズ別 150g 1,639円・200g 1,815円・250g 2,035円（price_max=2,035）
  - `grand-66475d0623` 牡蠣フライ＆手ごねハンバーグ：税抜1,290円／税込1,419円
  - `grand-fa3fc55282` 甘栗のモンブランファッジサンデー：税抜590円／税込649円、開始日2026-10-20
  - `grand-2954e7f6e0` 単品 牡蠣フライ：税抜550円／税込605円
  - `grand-005d4e7d25` 渋皮栗＆バニラアイス：税抜220円／税込242円

## 4. リクエスト数

- 実測（初回）：**合計7件**（一覧系2＝robots.txt・グランドメニュー、詳細系5＝フェア一覧・ニュース記事4本）。所要19秒
- run_summary：list_failed なし、blocked なし、errors なし
- 最悪の内訳：robots 1＋グランドメニュー 1＋フェア一覧 1＋記事 8（上限）＝11件
- 設定した上限 `max_requests_per_run.bigboy` = **20**（最悪ケース11件の約1.8倍、実測7件の約2.9倍）

## 5. 設定値の根拠

- **歯止め `new_burst_min_by_chain.bigboy` = 15**：初回一覧は9件。期間限定欄の全入れ替えでも10件規模なので、
  手順書の目安（15〜20）の下限15にした。全入れ替え（〜10件）では誤発動せず、構造変更で項目が膨らんだ場合は止まる
- **色**：color `#1565C0` / color_dark `#64B5F6`（青）。デニーズの赤（#B71C1C）・ジョナサンの緑（#1B5E20）と被らず、
  公式サイトの基調色（濃紺系）にも寄せた

## 6. テスト結果

- 全111件通過（main 時点の既存92件＋追加19件）。`python3 -m unittest discover -s tests` で OK

## 7. 未確認のこと・やらなかったこと

- **ココス（maru/add-cocos）との文言競合の見通し**：本ブランチは main 起点のため、トップ文言・about・README・AGENTS.md・
  テストの期待値などは「デニーズ・ジョナサン」にビッグボーイを足した形になっている。ココス側も同じ箇所を
  「デニーズ・ジョナサン・ココス」に変えているため、**両ブランチのマージ時に同じ行で競合する**。後からマージする側で
  「デニーズ・ジョナサン・ココス・ビッグボーイ」に揃えれば解消する想定（設定値の衝突は無い。chains・上限・歯止めは追記式）
- フェア記事が商品名を列挙しない問題（開始日1/9件）は、デニーズ方式の照合の範囲では解消できない。
  フェア単位の日付を、そのフェア名を含む商品へ広げるような照合拡張はしていない（レビューで要否を判断してほしい）
- すかいらーく（ジョナサン）の規約確認は本作業の対象外（従来どおり未確認のまま）
- やらなかったこと（別作業・申し送り）：
  - マージ・PR作成（本レポートがPRの材料）
  - マージ後の確認：ポチフルの説明文へのビッグボーイ追加、ローテーターのタイトル、新発売ポチへの供給表示の確認
  - pochi-branding でのアイコン類生成（オーナー作業）
  - data/ への初回記録の投入（本番の初回実行で行う。手元の試し実行結果は一時コピー側だけに残した）

## レビュー対応（2026-11-23、モルのレビュー指摘）

- 指摘：`crawl_bigboy` の enrich にあるフェア名での照合（`p["fair"]` で `find_launch` する分岐）を外すこと。ビッグボーイのフェア名は全商品共通の欄名「期間限定メニュー」なので、その語を含む記事が1本あると全商品に同じ開始日が付く（モルが手元で再現済み）
- 対応：フェア名の分岐と `via == "fair"` の処理をビッグボーイから削除し、商品名と副題を落とした名前での照合だけにした。理由をコード内コメントに残した。ココス・デニーズはフェア名が個別の名前なので分岐はそのまま
- 回帰テストを1本追加（`test_fair_name_is_never_used_for_launch_matching`：本文に「期間限定メニュー」と開始日を含む記事があっても、名前の合わない商品に開始日が付かない）。修正前は失敗し、修正後に通過することを確認した
- テストは全137件通過（136＋回帰1）。README のビッグボーイの開始日の説明も実態に合わせて直した
