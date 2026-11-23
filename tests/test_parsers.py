"""パーサのテスト(ネットワーク不使用)。公式の構造を再現した最小のフィクスチャで確認する。"""
import unittest

import helpers  # noqa: F401
import parsers as P
import synth as S


class TestPrice(unittest.TestCase):
    def test_pair(self):
        self.assertEqual(P.parse_price_pair("1,790円<span>（税込1,969円）</span>"), (1790, 1969))
        self.assertEqual(P.parse_price_pair("980円（税込1,078円）"), (980, 1078))
        self.assertIsNone(P.parse_price_pair("おまかせ"))

    def test_extra_charge_is_not_a_price(self):
        self.assertIsNone(P.parse_price_pair("＋180円（税込198円）"))


class TestDennysFairLinks(unittest.TestCase):
    def test_links_from_fair_area_only(self):
        links = P.parse_dennys_fair_links(S.dennys_menu())
        self.assertEqual([l["path"] for l in links], ["/menu/collaboration17/", "/menu/oimo/"])
        self.assertEqual(links[1]["title"], "蜜いもデザート")  # 定番(/menu/okonomi/)は入らない

    def test_page_names_are_not_fixed(self):
        links = P.parse_dennys_fair_links(S.dennys_menu([("/menu/winter2027/", "冬のフェア")]))
        self.assertEqual(links[0]["path"], "/menu/winter2027/")

    def test_empty_fair_area_is_empty_list_but_missing_area_is_error(self):
        self.assertEqual(P.parse_dennys_fair_links(S.dennys_menu([])), [])
        with self.assertRaises(ValueError):
            P.parse_dennys_fair_links("<html><body>構造が変わった</body></html>")

    def test_commented_out_fair_is_ignored(self):
        html = S.dennys_menu().replace('<ul class="fairArea center">', '<ul class="fairArea center"><!-- <li><a href="/menu/old/" title="旧">旧</a></li> -->')
        self.assertEqual(len(P.parse_dennys_fair_links(html)), 2)


class TestDennysFairPage(unittest.TestCase):
    def test_items_prices_and_product_path_ids(self):
        html = S.dennys_fair("蜜いもデザート", [
            ('<span class="nowrap">蜜いものザ・サンデー</span><span class="nowrap">～紅天使使用</span>', 1790, 1969,
             "/menu/dessert/sweet-potato-sundae/"),
            ("おいもプリン", 300, 330, "/menu/dessert/sweet-potato-pudding/"),
        ])
        page = P.parse_dennys_fair_page(html, "/menu/oimo/")
        self.assertEqual(page["title"], "蜜いもデザート")
        self.assertEqual([i["pid"] for i in page["items"]], ["dessert-sweet-potato-sundae", "dessert-sweet-potato-pudding"])
        first = page["items"][0]
        self.assertEqual((first["name"], first["price"], first["price_excl_tax"]), ("蜜いものザ・サンデー～紅天使使用", 1969, 1790))
        # フェア自身のリンク(/menu/half-parfait/oimo/ はメニューの前にある別ページ)は商品の識別キーにしない
        self.assertNotIn("half-parfait", "".join(i["pid"] for i in page["items"]))

    def test_item_without_link_uses_fair_path_and_normalized_name(self):
        html = S.dennys_fair("飯田商店", [('麻婆牡蠣＆豆腐', 690, 759, None)])
        a = P.parse_dennys_fair_page(html, "/menu/collaboration17/")["items"][0]
        self.assertEqual(a["pid"], P.stable_id("collaboration17", "麻婆牡蠣＆豆腐"))
        self.assertIsNone(a["link"])

    def test_br_and_ruby_do_not_split_names(self):
        name = '味噌らぁ麺・改<br><span class="nowrap">～<ruby>五重<rt>いつつがさね</rt></ruby>の味噌</span>'
        html = S.dennys_fair("飯田商店", [(name, 1360, 1496, None)],
                             sets=[("味噌らぁ麺・改～五重の味噌＋焼き餃子（2個）セット", 1720, 1892)])
        names = [i["name"] for i in P.parse_dennys_fair_page(html, "/menu/c/")["items"]]
        self.assertEqual(names, ["味噌らぁ麺・改～五重の味噌", "味噌らぁ麺・改～五重の味噌＋焼き餃子（2個）セット"])

    def test_commented_out_price_is_ignored(self):
        html = S.dennys_fair("X", [("商品A", 100, 110, None)],
                             commented='<p class="menuTitle">幻</p><p class="price">1円<span>（税込1円）</span></p>')
        self.assertEqual(len(P.parse_dennys_fair_page(html, "/menu/x/")["items"]), 1)

    def test_no_price_means_empty_items_and_no_title_is_error(self):
        self.assertEqual(P.parse_dennys_fair_page('<h1 class="label">画像だけ</h1><img alt="1,000円">', "/menu/x/")["items"], [])
        with self.assertRaises(ValueError):
            P.parse_dennys_fair_page("<html>構造が変わった</html>", "/menu/x/")

    def test_description_is_never_read(self):
        html = S.dennys_fair("X", [("商品A", 100, 110, None)]).replace(
            "</body>", '<p class="subTxt">北海道産小麦100%の説明文</p></body>')
        self.assertNotIn("説明文", str(P.parse_dennys_fair_page(html, "/menu/x/")))


class TestDennysNews(unittest.TestCase):
    def test_entries(self):
        news = P.parse_dennys_news(S.dennys_news([
            ("2026/10/14", "「蜜いものザ・サンデー」全8品10月28日（水）販売開始", "リード文です"),
            ("2026/10/2", "別の発表", "")]))
        self.assertEqual(news[0]["date"], "2026-10-14")
        self.assertEqual(news[1]["date"], "2026-10-02")
        self.assertIn("10月28日", news[0]["title"])

    def test_launch_date_from_headline(self):
        self.assertEqual(P.launch_date_from_text("全8品10月28日（水）販売開始", __import__("datetime").date(2026, 11, 23)), "2026-10-28")
        self.assertEqual(P.launch_date_from_text("人気の味噌らぁ麺は進化！ 10月14日（水）スタート", __import__("datetime").date(2026, 11, 23)), "2026-10-14")

    def test_garbage_is_empty(self):
        self.assertEqual(P.parse_dennys_news("<html>変わった</html>"), [])


class TestJonathanAlt(unittest.TestCase):
    def test_real_alt_names(self):
        got = {i["name"]: (i["price"], i["price_excl_tax"]) for i in P.parse_jonathan_alt(S.JONATHAN_FAIR_ALT)}
        self.assertEqual(got["炙り鮭はらすといくらの出汁茶漬け＋おつまみカキフライ膳"], (1869, 1699))
        self.assertEqual(got["炙り鮭はらすといくらの出汁茶漬け膳"], (1539, 1399))
        self.assertEqual(got["とろサーモン＆いくら丼（みそ汁・惣菜つき）"], (1869, 1699))
        self.assertEqual(got["アンガスビーフ100% 贅沢きのこのオニオンスープハンバーグ"], (1484, 1349))
        self.assertEqual(got["かぼちゃとキャロットラペのサラダ"], (384, 349))
        self.assertEqual(got["八天堂とろけるカスタードくりーむのミニパルフェ（早生みかん）"], (549, 499))

    def test_catchphrases_and_descriptions_are_not_names(self):
        names = [i["name"] for i in P.parse_jonathan_alt(S.JONATHAN_FAIR_ALT)]
        for frag in ("お出汁をかけて", "2度おいしい", "脂ののった", "温泉卵と一緒に", "Side Menu", "Sweets", "八天堂。",
                     "オーストラリア産", "スープには"):
            self.assertFalse(any(frag in n for n in names), frag)
        self.assertEqual(len(names), 7)

    def test_extra_charges_and_colon_labels(self):
        alt = ("もちっと生パスタ。トマトスープ：トマトスープパスタ マルゲリータ 1,049円（税込1,154円）、"
               "選べるアペタイザーセット（ドリンクバーつき） 1,498円（税込1,648円）。"
               "トッピング：ローストビーフ ＋180円（税込198円）、コーン・粉チーズ 各＋50円（税込55円）。")
        got = [i["name"] for i in P.parse_jonathan_alt(alt)]
        self.assertEqual(got, ["トマトスープパスタ マルゲリータ", "選べるアペタイザーセット（ドリンクバーつき）"])

    def test_commas_inside_parentheses_do_not_split_a_name(self):
        alt = "季節のパフェ（早生みかん、みかんゼリー、アイス） 999円（税込1,099円）。"
        self.assertEqual([i["name"] for i in P.parse_jonathan_alt(alt)], ["季節のパフェ（早生みかん、みかんゼリー、アイス）"])

    def test_too_long_or_too_short_is_dropped(self):
        long = "あ" * 90 + " 100円（税込110円）。"
        self.assertEqual(P.parse_jonathan_alt(long), [])
        self.assertEqual(P.parse_jonathan_alt("A 100円（税込110円）"), [])

    def test_no_price_is_empty(self):
        self.assertEqual(P.parse_jonathan_alt("秋のよくばりマルシェ。かぼちゃサラダ"), [])
        self.assertEqual(P.parse_jonathan_alt(None), [])


class TestJonathanPages(unittest.TestCase):
    def test_menu_links(self):
        links = P.parse_jonathan_menu_links(S.jonathan_top())
        self.assertEqual([l["slug"] for l in links], ["collab", "fair", "dessert", "drink_bar"])
        with self.assertRaises(ValueError):
            P.parse_jonathan_menu_links("<html>変わった</html>")

    def test_fair_page_items_dedup_and_comment(self):
        page = P.parse_jonathan_fair_page(S.jonathan_page("秋のよくばりマルシェ", [S.JONATHAN_FAIR_ALT, S.JONATHAN_FAIR_ALT]), "fair")
        self.assertEqual(page["title"], "秋のよくばりマルシェ")
        self.assertEqual(len(page["items"]), 7)  # 同じ alt が2回(PC/SP)出ても重複しない・コメント内の価格は読まない
        self.assertTrue(all(i["pid"].startswith("fair-") for i in page["items"]))

    def test_ids_are_stable_across_runs_and_differ_by_page(self):
        a = P.parse_jonathan_fair_page(S.jonathan_page("A"), "fair")["items"][0]["pid"]
        b = P.parse_jonathan_fair_page(S.jonathan_page("A"), "fair")["items"][0]["pid"]
        c = P.parse_jonathan_fair_page(S.jonathan_page("A"), "dessert")["items"][0]["pid"]
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_no_h1_is_error(self):
        with self.assertRaises(ValueError):
            P.parse_jonathan_fair_page("<html>変わった</html>", "fair")


class TestCocosPriceYenPair(unittest.TestCase):
    def test_yen_pair_with_space_after_yen_sign(self):
        html = '<span class="tax_ex"><span>¥</span>590</span><span class="tax_in">(<span>税込</span>¥ 649)</span>'
        self.assertEqual(P.parse_price_yen_pair(html), (590, 649))
        self.assertEqual(P.parse_price_yen_pair("¥1,280(税込¥ 1,408)"), (1280, 1408))
        self.assertEqual(P.parse_price_yen_pair("¥80(税込¥ 88)"), (80, 88))

    def test_yen_format_is_not_read_by_the_yen_word_parser(self):
        # 共通の parse_price_pair(円表記用)では取れない。だから専用の正規表現が要る
        self.assertIsNone(P.parse_price_pair("¥590(税込¥ 649)"))
        self.assertIsNone(P.parse_price_yen_pair("1,790円（税込1,969円）"))
        self.assertIsNone(P.parse_price_yen_pair("おまかせ"))


class TestCocosFairPage(unittest.TestCase):
    def test_sections_items_prices_and_path_ids(self):
        sections = P.parse_cocos_fair_page(S.cocos_fair_page())
        self.assertEqual([s["title"] for s in sections], ["ココスの期間限定スイーツ", "マロンフェア"])
        first = sections[0]["items"][0]
        self.assertEqual(first["pid"], "limited_sweets-roasted_sweet_potato_crepe2611")
        self.assertEqual((first["name"], first["price"], first["price_excl_tax"]),
                         ("勤労感謝の芋栗かぼちゃクレープ", 649, 590))
        self.assertEqual(first["link"], "/menu/fair/limited_sweets/roasted_sweet_potato_crepe2611.html")
        marron = sections[1]["items"]
        self.assertEqual([i["pid"] for i in marron],
                         ["marron2610-shinemuscat_parfait2609", "marron2610-shinemuscat_crepe2609"])
        self.assertEqual((marron[0]["price"], marron[0]["price_excl_tax"]), (1419, 1290))

    def test_item_without_link_uses_name_hash(self):
        html = S.cocos_fair_page((("フェア", [("リンクなし商品", 100, 110, None)]),))
        it = P.parse_cocos_fair_page(html)[0]["items"][0]
        self.assertEqual(it["pid"], P.stable_id("cocos", "リンクなし商品"))
        self.assertIsNone(it["link"])

    def test_non_fair_h2_sections_are_ignored(self):
        # 「ココス公式アプリ」等の h2 は type_menu_list を伴わないのでフェアにしない
        sections = P.parse_cocos_fair_page(S.cocos_fair_page())
        self.assertNotIn("ココス公式アプリCoco's App", [s["title"] for s in sections])

    def test_commented_out_item_is_ignored(self):
        commented = ('<h2>旧フェア</h2><ul class="img_link type_menu_list"><li><a href="/menu/fair/old/x.html">'
                     '<div class="name">幻</div><div class="price">¥100(税込¥ 110)</div></a></li></ul>')
        sections = P.parse_cocos_fair_page(S.cocos_fair_page(commented=commented))
        self.assertEqual([s["title"] for s in sections], ["ココスの期間限定スイーツ", "マロンフェア"])

    def test_no_price_means_empty_items_and_no_section_is_error(self):
        html = ('<html><body><h2>画像だけ</h2><ul class="img_link type_menu_list">'
                '<li><a href="/menu/fair/x/a.html"><div class="menu_info">'
                '<div class="name">価格は画像の中の商品</div><div class="price">価格は画像の中</div>'
                '</div></a></li></ul></body></html>')
        self.assertEqual(P.parse_cocos_fair_page(html)[0]["items"], [])
        with self.assertRaises(ValueError):
            P.parse_cocos_fair_page("<html>構造が変わった</html>")

    def test_description_is_never_read(self):
        html = S.cocos_fair_page().replace("</body>", '<p class="subTxt">北海道産小麦100%の説明文</p></body>')
        self.assertNotIn("説明文", str(P.parse_cocos_fair_page(html)))

    def test_ids_are_stable_across_runs(self):
        a = P.parse_cocos_fair_page(S.cocos_fair_page())[0]["items"][0]["pid"]
        b = P.parse_cocos_fair_page(S.cocos_fair_page())[0]["items"][0]["pid"]
        self.assertEqual(a, b)


class TestCocosNews(unittest.TestCase):
    def test_entries(self):
        news = P.parse_cocos_news(S.cocos_news([
            ("/news/2026/menu/1105-122026.html", "2026-11-05",
             "【11月19日(木)開始】ココスの期間限定スイーツ！「勤労感謝の芋栗かぼちゃクレープ」"),
            ("/news/2026/menu/1006-115296.html", "2026-10-06", "【10月13日(火)開始】ココスが「マロンフェア」を開催！")]))
        self.assertEqual(news[0]["date"], "2026-11-05")
        self.assertEqual(news[0]["url"], "https://www.cocos-jpn.co.jp/news/2026/menu/1105-122026.html")
        self.assertIn("11月19日", news[0]["title"])
        self.assertEqual(news[0]["text"], "")  # 一覧にリード文は無い
        self.assertEqual(P.launch_date_from_text(news[0]["title"], __import__("datetime").date(2026, 11, 5)), "2026-11-19")

    def test_garbage_is_empty(self):
        self.assertEqual(P.parse_cocos_news("<html>変わった</html>"), [])


if __name__ == "__main__":
    unittest.main()
