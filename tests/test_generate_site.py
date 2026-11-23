"""サイト生成のテスト(ネットワーク不使用)。商品の dict から HTML を作る関数を直接確かめる。"""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401
import generate_site as G
import crawl


def setUpModule():
    """テストはネタフルの記事キャッシュ(data/netaful_reviews.json)に左右されないよう、空にしておく。"""
    global _patch
    _patch = mock.patch.object(G, "ARTICLES_BY_ID", {})
    _patch.start()
    G.REVIEWS.update({"articles": {}, "matches": {}})


def tearDownModule():
    _patch.stop()


def item(chain="dennys", pid="dessert-sweet-potato-sundae", name="蜜いものザ・サンデー～紅天使使用", **kw):
    p = crawl.base_product(chain, pid, name, "2026-11-23T07:00:00+09:00", "2026-11-23")
    crawl.set_initial_price(p, 1969, None, "2026-11-23")
    p.update({"fair": "蜜いもデザート", "price_excl_tax": 1790, "limited_kind": "フェア",
              "official_url": "https://www.dennys.jp/menu/dessert/sweet-potato-sundae/",
              "stores_note": "一部の店舗(新宿西口店・赤坂駅前店・浅草雷門店など)では、価格や取り扱いが異なります"})
    p.update(kw)
    return p


class TestPriceAndPeriod(unittest.TestCase):
    def test_price_is_tax_included(self):
        self.assertEqual(G.fmt_price(item()), "1,969円（税込）")
        self.assertEqual(G.fmt_price(item(price=None)), "")

    def test_period_uses_recording_start_when_launch_unknown(self):
        self.assertEqual(G.period_text(item()), "2026-11-23（記録開始日）〜 販売中")
        self.assertEqual(G.period_text(item(launch_date="2026-10-28")), "2026-10-28〜 販売中")

    def test_ended_period_says_observed(self):
        it = item(status="ended", ended_observed_at="2026-12-20")
        self.assertEqual(G.period_text(it), "2026-11-23（記録開始日）〜2026-12-20")
        self.assertIn("消えたことを確認した日", G.period_text(it, detailed=True))


class TestItemPage(unittest.TestCase):
    def test_facts_only_and_source_link(self):
        h = G.render_item_page(item(launch_date="2026-10-28"))
        self.assertIn("蜜いものザ・サンデー～紅天使使用", h)
        self.assertIn("1,969円（税込）", h)
        self.assertIn("税抜価格", h)
        self.assertIn("1,790円", h)
        self.assertIn("蜜いもデザート", h)
        self.assertIn("2026-10-28〜 販売中", h)
        self.assertIn("出典：デニーズ公式サイト（2026年11月23日時点）", h)
        self.assertIn('href="https://www.dennys.jp/menu/dessert/sweet-potato-sundae/"', h)
        self.assertIn("一部の店舗", h)

    def test_no_description_nutrition_allergen_or_images(self):
        h = re.sub(r"<style>.*?</style>", "", G.render_item_page(item()), flags=re.S)
        for word in ("栄養成分", "アレルゲン", "アレルギー", "kcal", "カロリー", "blockquote"):
            self.assertNotIn(word, h)
        self.assertNotRegex(h, r"<img[^>]+src=\"(?!/assets/)")  # サイトのアイコン以外の画像は無い

    def test_launch_unknown_note(self):
        self.assertIn("発売日は不明のため、記録を始めた日から表示しています", G.render_item_page(item()))
        self.assertNotIn("発売日は不明", G.render_item_page(item(launch_date="2026-10-28")))

    def test_launch_source_note_only_for_indirect_matches(self):
        direct = G.render_item_page(item(launch_date="2026-10-28", launch_date_source="official_news"))
        fair = G.render_item_page(item(launch_date="2026-10-28", launch_date_source="official_news_fair"))
        self.assertNotIn("ずれることがあります", direct)
        self.assertIn("ずれることがあります", fair)

    def test_ended_note_and_relaunch(self):
        h = G.render_item_page(item(status="ended", ended_observed_at="2026-12-20"))
        self.assertIn("店頭ではまだ販売していることもあります", h)
        self.assertIn("販売終了", h)

    def test_price_history_only_when_changed(self):
        it = item()
        self.assertNotIn("価格の履歴", G.render_item_page(it))
        crawl.record_price(it, 2000, None, "2026-12-01")
        self.assertIn("価格の履歴", G.render_item_page(it))

    def test_single_h1_and_title(self):
        h = G.render_item_page(item())
        self.assertEqual(len(re.findall(r"<h1[ >]", h)), 1)
        self.assertIn("<title>デニーズ「蜜いものザ・サンデー～紅天使使用」の価格・販売期間｜ファミレスポチ</title>", h)

    def test_jonathan_item(self):
        it = item(chain="jonathan", pid="fair-abc", name="炙り鮭はらすといくらの出汁茶漬け膳", fair="秋のよくばりマルシェ",
                  official_url="https://www.skylark.co.jp/jonathan/menu/fair/index.html")
        h = G.render_item_page(it)
        self.assertIn("出典：ジョナサン公式サイト", h)
        self.assertIn("秋のよくばりマルシェ", h)

    def test_joyfull_item(self):
        it = item(chain="joyfull", pid="527", name="「幻のコショウのチキン竜田」", fair="世界の山ちゃんフェア",
                  official_url="https://www.joyfull.co.jp/menu/527",
                  stores_note="関東エリア店舗(東京都・埼玉県・千葉県・群馬県・栃木県・茨城県・福島県)では、メニューや価格が異なる場合があります")
        h = G.render_item_page(it)
        self.assertIn("出典：ジョイフル公式サイト", h)
        self.assertIn("世界の山ちゃんフェア", h)
        self.assertIn("関東エリア店舗", h)
        self.assertIn('href="https://www.joyfull.co.jp/menu/527"', h)

    def test_cocos_item(self):
        it = item(chain="cocos", pid="limited_sweets-roasted_sweet_potato_crepe2611", name="勤労感謝の芋栗かぼちゃクレープ",
                  fair="ココスの期間限定スイーツ",
                  official_url="https://www.cocos-jpn.co.jp/menu/fair/limited_sweets/roasted_sweet_potato_crepe2611.html",
                  launch_date="2026-11-19", launch_date_source="official_news")
        h = G.render_item_page(it)
        self.assertIn("出典：ココス公式サイト", h)
        self.assertIn("ココスの期間限定スイーツ", h)
        self.assertIn("2026-11-19〜 販売中", h)
        self.assertIn("<title>ココス「勤労感謝の芋栗かぼちゃクレープ」の価格・販売期間｜ファミレスポチ</title>", h)

    def test_steakdon_item_with_size_variants(self):
        it = item(chain="steakdon", pid="1636", name="黒毛和牛ステーキ", fair="フェアメニュー",
                  price=3278, price_max=4818, price_excl_tax=2980,
                  price_variants=[{"label": "100g", "price": 3278}, {"label": "150g", "price": 3938},
                                  {"label": "200g", "price": 4818}],
                  official_url="https://www.steak-don.jp/fmenu_detail.html?fmenu_item_id=1636",
                  stores_note="※店舗限定")
        h = G.render_item_page(it)
        self.assertIn("出典：ステーキのどん公式サイト", h)
        self.assertIn("フェアメニュー", h)
        self.assertIn("100g", h)
        self.assertIn("4,818円（税込）", h)
        self.assertIn("※店舗限定", h)


class TestBigboyPage(unittest.TestCase):
    def test_item_page_source_and_price_range(self):
        p = item(chain="bigboy", pid="grand-1", name="牡蠣フライ＆大俵ハンバーグ", price=1639, price_max=2035,
                 price_excl_tax=1490, fair="期間限定メニュー",
                 price_variants=[{"label": "大俵150g", "price": 1639}, {"label": "大俵250g", "price": 2035}],
                 source_list=["www.bigboyjapan.co.jp/menu/grand/"],
                 official_url="https://www.bigboyjapan.co.jp/menu/grand/")
        h = G.render_item_page(p, [p])
        self.assertIn("出典：ビッグボーイ公式サイト", h)
        self.assertIn("1,639〜2,035円（税込）", h)
        self.assertIn("<th>大俵150g</th><td>1,639円（税込）</td>", h)


class TestSameName(unittest.TestCase):
    def test_same_name_gets_a_qualifier(self):
        a = item(pid="a", name="おいもプリン", launch_date="2026-10-28")
        b = item(pid="b", name="おいもプリン", launch_date="2027-10-27")
        q = G.name_qualifiers([a, b])
        self.assertEqual(q[("dennys", "a")], "2026年10月発売")
        self.assertNotEqual(q[("dennys", "a")], q[("dennys", "b")])
        self.assertIn("同じ名前の商品", G.render_item_page(a, [a, b]))


class TestLists(unittest.TestCase):
    def setUp(self):
        self.items = [item(), item(pid="p2", name="おいもプリン", price=None),
                      item(chain="jonathan", pid="fair-1", name="とろサーモン＆いくら丼", fair="秋のよくばりマルシェ"),
                      item(chain="joyfull", pid="527", name="「幻のコショウのチキン竜田」", fair="世界の山ちゃんフェア",
                           official_url="https://www.joyfull.co.jp/menu/527")]

    def test_top_groups_by_chain_and_has_no_kcal_sort(self):
        h = G.render_top(self.items)
        self.assertIn("デニーズ (", h)
        self.assertIn("ジョナサン (", h)
        self.assertIn("ジョイフル (", h)
        self.assertNotIn("カロリー順", h)
        self.assertEqual(len(re.findall(r"<h1[ >]", h)), 1)
        self.assertIn('"name": "ファミレスポチ"', h)
        self.assertIn("<title>ファミレスポチ｜デニーズ・ジョナサン・ココス・ビッグボーイ・ジョイフル・ステーキのどんの期間限定メニュー記録</title>", h)

    def test_card_has_no_image_besides_category_icon(self):
        for m in re.finditer(r"<img[^>]+>", G.render_card(self.items[0])):
            self.assertIn("/assets/icons/cat/", m.group(0))

    def test_chain_seo_mentions_price_not_nutrition(self):
        title, desc = G.chain_seo(G.CHAINS[0], self.items[:2])
        self.assertIn("デニーズの期間限定メニュー一覧", title)
        self.assertIn("価格を掲載", desc)
        self.assertNotIn("カロリー", desc)

    def test_archive_empty_and_with_months(self):
        self.assertIn("まだ販売が終わったメニューはありません", G.render_archive_index(self.items))
        ended = item(status="ended", ended_observed_at="2026-12-20", launch_date="2026-10-28")
        h = G.render_archive_index([ended])
        self.assertIn("/archive/2026-10/", h)

    def test_search_index(self):
        idx = G.build_search_index(self.items)
        self.assertEqual({i["c"] for i in idx}, {"dennys", "jonathan", "joyfull"})


class TestSiteFiles(unittest.TestCase):
    def test_sitemap_lastmod_and_robots(self):
        it = item()
        x = G.generate_sitemap([it], [])
        self.assertIn("https://famires.netaful.jp/items/dennys-dessert-sweet-potato-sundae.html", x)
        self.assertIn("<lastmod>2026-11-23</lastmod>", x)
        self.assertIn("https://famires.netaful.jp/chains/jonathan/", x)
        self.assertIn("https://famires.netaful.jp/chains/joyfull/", x)
        self.assertIn("Sitemap: https://famires.netaful.jp/sitemap.xml", G.generate_robots())

    def test_main_writes_everything_to_a_temp_docs(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            (base / "data" / "products" / "dennys").mkdir(parents=True)
            (base / "docs").mkdir()
            (base / "data" / "products" / "dennys" / "x.json").write_text(json.dumps(item(), ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(G, "PRODUCTS", base / "data" / "products"), mock.patch.object(G, "DOCS", base / "docs"):
                self.assertEqual(G.main(), 0)
            self.assertTrue((base / "docs" / "index.html").is_file())
            self.assertTrue((base / "docs" / "chains" / "jonathan" / "index.html").is_file())
            self.assertTrue((base / "docs" / "chains" / "cocos" / "index.html").is_file())
            self.assertEqual((base / "docs" / "CNAME").read_text(), "famires.netaful.jp\n")
            self.assertTrue((base / "docs" / "items" / "dennys-dessert-sweet-potato-sundae.html").is_file())


class TestAdsAndAnalytics(unittest.TestCase):
    def test_ads_ga_and_disclosure_from_config(self):
        h = G.render_item_page(item())
        self.assertIn("ca-pub-2195959398357532", h)
        self.assertIn('data-ad-slot="1215675017"', h)
        self.assertIn("G-D8F2T2XB5W", h)
        self.assertIn("当サイトはGoogle AdSenseを掲載し、Googleアナリティクスを使っています。いずれもCookieを使うことがあります。", h)

    def test_disclosure_follows_actual_settings(self):
        with mock.patch.dict(G.CONFIG, {"ga_measurement_id": ""}):
            h = G.render_item_page(item())
            self.assertNotIn("アクセス解析", h)
            self.assertNotIn("googletagmanager", h)
        with mock.patch.dict(G.CONFIG, {"adsense_client_id": "", "adsense_ad_slot": "", "ga_measurement_id": ""}):
            h = G.render_item_page(item())
            self.assertNotIn("adsbygoogle", h)
            self.assertNotIn("Google AdSenseを掲載し", h)

    def test_footer_links(self):
        h = G.render_top([item()])
        self.assertIn("https://cafe.netaful.jp/", h)
        self.assertNotIn('href="https://famires.netaful.jp/">ファミレスポチ<span', h)
        self.assertIn("https://pochi.netaful.jp/", h)


class TestChainColors(unittest.TestCase):
    def test_css_has_light_and_dark_chain_colors(self):
        css = G.build_css()
        self.assertIn("--dennys: #B71C1C", css)
        self.assertIn("--jonathan: #1B5E20", css)
        self.assertIn("--cocos: #E65100", css)
        self.assertIn("--cocos: #FFB74D", css)
        self.assertIn("--joyfull: #6A1B9A", css)
        self.assertIn("--steakdon: #6D4C41", css)
        self.assertIn("prefers-color-scheme: dark", css)


if __name__ == "__main__":
    unittest.main()
