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


class TestBigboyPrice(unittest.TestCase):
    def test_yen_pair_with_split_tags(self):
        html = ('<span class="size">大俵150g</span><span class="yen">¥</span>\n1,490'
                '<span class="tax_sum">（<span class="tax">税込</span><span class="yen">¥</span>\n1,639）</span>')
        self.assertEqual(P.parse_bigboy_price_pair(html), (1490, 1639))
        self.assertEqual(P.parse_bigboy_price_pair("¥590（税込¥649）"), (590, 649))
        self.assertIsNone(P.parse_bigboy_price_pair("おまかせ"))
        # 円表記の共通パーサでは ¥ 表記は取れない(書式が違う)
        self.assertIsNone(P.parse_price_pair("¥590（税込¥649）"))


class TestBigboyGrandMenu(unittest.TestCase):
    def test_items_names_prices_and_variants(self):
        page = P.parse_bigboy_grand_menu(S.bigboy_grand_menu())
        self.assertEqual(page["title"], "期間限定メニュー")
        self.assertEqual([i["name"] for i in page["items"]],
                         ["牡蠣フライ＆大俵ハンバーグ", "牡蠣フライ＆手ごねハンバーグ", "甘栗のモンブランファッジサンデー"])
        sized = page["items"][0]
        self.assertEqual((sized["price_excl_tax"], sized["price"], sized["price_max"]), (1490, 1639, 2035))
        self.assertEqual(sized["price_variants"],
                         [{"label": "大俵150g", "price": 1639}, {"label": "大俵200g", "price": 1815},
                          {"label": "大俵250g", "price": 2035}])
        single = page["items"][1]
        self.assertEqual((single["price_excl_tax"], single["price"], single["price_max"]), (1290, 1419, None))
        self.assertEqual(single["price_variants"], [])

    def test_other_sections_and_sub_and_comments_are_not_read(self):
        page = P.parse_bigboy_grand_menu(S.bigboy_grand_menu(
            commented='<li class="box"><h4 class="name"><span class="main">コメント内の商品</span></h4>'
                      '<p class="price"><span class="yen">¥</span>100<span class="tax_sum">（税込¥110）</span></p></li>'))
        names = [i["name"] for i in page["items"]]
        self.assertNotIn("定番ハンバーグ", names)  # 定番の欄は対象外
        self.assertNotIn("コメント内の商品", names)
        self.assertTrue(all("タルタル" not in n for n in names))  # span.sub(付け合わせの注記)は名前に含めない

    def test_no_section_is_error_and_no_price_is_empty(self):
        with self.assertRaises(ValueError):
            P.parse_bigboy_grand_menu("<html>変わった</html>")
        page = P.parse_bigboy_grand_menu(S.bigboy_grand_menu(items=[("価格なし商品", [])], regular=None))
        self.assertEqual(page["items"], [])

    def test_ids_are_stable_across_runs(self):
        a = P.parse_bigboy_grand_menu(S.bigboy_grand_menu())["items"]
        b = P.parse_bigboy_grand_menu(S.bigboy_grand_menu())["items"]
        self.assertEqual([i["pid"] for i in a], [i["pid"] for i in b])
        self.assertTrue(all(i["pid"].startswith("grand-") for i in a))


class TestBigboyNews(unittest.TestCase):
    def test_fair_links(self):
        links = P.parse_bigboy_fair_links(S.bigboy_fair_list())
        self.assertEqual(links, [{"path": "/news/fair/6555.html",
                                  "title": "【フェア情報】「甘栗のモンブランファッジサンデー」、10月20日（火）より販売！"}])
        self.assertEqual(P.parse_bigboy_fair_links("<html>変わった</html>"), [])

    def test_article_date_title_text(self):
        art = P.parse_bigboy_news_article(S.bigboy_news_article(), "https://www.bigboyjapan.co.jp/news/fair/6555.html")
        self.assertEqual(art["date"], "2026-10-14")
        self.assertIn("甘栗のモンブランファッジサンデー", art["title"])
        self.assertIn("10月20日（火）より", art["text"])
        self.assertEqual(art["url"], "https://www.bigboyjapan.co.jp/news/fair/6555.html")

    def test_launch_date_uses_article_year(self):
        art = P.parse_bigboy_news_article(S.bigboy_news_article(), "https://www.bigboyjapan.co.jp/news/fair/6555.html")
        import datetime
        self.assertEqual(P.launch_date_from_text(art["title"], datetime.date(2026, 10, 14)), "2026-10-20")

    def test_garbage_article_is_none(self):
        self.assertIsNone(P.parse_bigboy_news_article("<html>変わった</html>", "https://www.bigboyjapan.co.jp/news/fair/1.html"))



class TestJoyfullPrice(unittest.TestCase):
    def test_fullwidth_yen_pair(self):
        self.assertEqual(P.parse_joyfull_price_pair("￥1,299 （税込￥1,428）"), (1299, 1428))
        self.assertEqual(P.parse_joyfull_price_pair("￥839\n（税込￥922）"), (839, 922))

    def test_common_format_is_not_read(self):
        # 「N円（税込M円）」はデニーズ・ジョナサンの書式で、ジョイフルのパーサでは取らない
        self.assertIsNone(P.parse_joyfull_price_pair("1,790円（税込1,969円）"))
        self.assertIsNone(P.parse_joyfull_price_pair("おまかせ"))


class TestJoyfullListedLaunch(unittest.TestCase):
    def test_prefix_with_year_and_hour(self):
        self.assertEqual(P.parse_joyfull_listed_launch("【2026年12月1日（火）15時より販売】日向翔陽のハンバーグ"), "2026-12-01")

    def test_no_prefix(self):
        self.assertIsNone(P.parse_joyfull_listed_launch("「幻のコショウのチキン竜田」"))
        self.assertIsNone(P.parse_joyfull_listed_launch("【数量限定】テスト"))
        self.assertIsNone(P.parse_joyfull_listed_launch(None))


class TestJoyfullCategory(unittest.TestCase):
    ITEMS = [(602, "【2026年12月1日（火）15時より販売】テストハンバーグ", 1299, 1428),
             (527, "「幻のコショウのチキン竜田」", 939, 1032)]

    def test_items_prices_and_numeric_ids(self):
        page = P.parse_joyfull_category(S.joyfull_list(self.ITEMS))
        self.assertEqual(page["declared_count"], 2)
        self.assertEqual([i["pid"] for i in page["items"]], ["602", "527"])
        first = page["items"][0]
        self.assertEqual((first["price"], first["price_excl_tax"]), (1428, 1299))
        self.assertEqual(first["listed_launch"], "2026-12-01")
        self.assertEqual(first["link"], "/menu/602")
        self.assertIsNone(page["items"][1]["listed_launch"])

    def test_listed_launch_prefix_is_stripped_from_name(self):
        page = P.parse_joyfull_category(S.joyfull_list(self.ITEMS))
        first = page["items"][0]
        self.assertEqual(first["name"], "テストハンバーグ")
        self.assertEqual(first["listed_launch"], "2026-12-01")

    def test_surrounding_brackets_are_stripped_from_name(self):
        page = P.parse_joyfull_category(S.joyfull_list(self.ITEMS))
        self.assertEqual(page["items"][1]["name"], "幻のコショウのチキン竜田")
        inner = P.parse_joyfull_category(S.joyfull_list([(601, "テスト「限定」バーガー", 500, 550)]))
        self.assertEqual(inner["items"][0]["name"], "テスト「限定」バーガー")

    def test_ids_are_stable_across_runs(self):
        a = P.parse_joyfull_category(S.joyfull_list(self.ITEMS))["items"]
        b = P.parse_joyfull_category(S.joyfull_list(self.ITEMS))["items"]
        self.assertEqual([i["pid"] for i in a], [i["pid"] for i in b])

    def test_commented_out_card_is_ignored(self):
        html = S.joyfull_list(self.ITEMS, commented='<li class="mg-item"><a href="https://www.joyfull.co.jp/menu/999" class="menu-card"><h3 class="mg-title">幻</h3><p class="menu-meta">￥100 （税込￥110）</p></a></li>')
        self.assertEqual(len(P.parse_joyfull_category(html)["items"]), 2)

    def test_missing_structure_is_error(self):
        with self.assertRaises(ValueError):
            P.parse_joyfull_category("<html><body>構造が変わった</body></html>")

    def test_card_without_price_is_skipped(self):
        html = S.joyfull_list(self.ITEMS).replace("￥939", "価格は店頭で")
        page = P.parse_joyfull_category(html)
        self.assertEqual([i["pid"] for i in page["items"]], ["602"])
        self.assertEqual(page["declared_count"], 2)  # 呼び出し側が差を見て「不完全」にする


class TestJoyfullDetail(unittest.TestCase):
    def test_fair_from_breadcrumb(self):
        self.assertEqual(P.parse_joyfull_detail(S.joyfull_detail("世界の山ちゃんフェア", "商品A")), {"fair": "世界の山ちゃんフェア"})

    def test_no_fair_is_none(self):
        self.assertEqual(P.parse_joyfull_detail(S.joyfull_detail(None, "商品A")), {"fair": None})

    def test_broken_breadcrumb_is_error(self):
        with self.assertRaises(ValueError):
            P.parse_joyfull_detail("<html>構造が変わった</html>")
        bad = S.joyfull_detail("フェア", "商品A").replace("季節・期間限定", "グランドメニュー")
        with self.assertRaises(ValueError):
            P.parse_joyfull_detail(bad)


class TestJoyfullNews(unittest.TestCase):
    def test_entries(self):
        news = P.parse_joyfull_news(S.joyfull_news([
            (99, "2026.10.02", "【ジョイフル】「世界の山ちゃんフェア」2026年10月13日（火）15時より販売開始!!"),
            (91, "2026.09.30", "2026年10月6日（火）15時販売開始！「2026秋冬 新グランドメニュー」")]))
        self.assertEqual(news[0]["date"], "2026-10-02")
        self.assertEqual(news[0]["url"], "https://www.joyfull.co.jp/news/99")
        self.assertIn("世界の山ちゃんフェア", news[0]["title"])

    def test_garbage_is_empty(self):
        self.assertEqual(P.parse_joyfull_news("<html>変わった</html>"), [])



if __name__ == "__main__":
    unittest.main()


class TestSteakdonFairList(unittest.TestCase):
    def test_items_names_prices_and_official_ids(self):
        page = P.parse_steakdon_fair_list(S.steakdon_fair_list())
        self.assertEqual(page["title"], "フェアメニュー")
        self.assertEqual([i["pid"] for i in page["items"]], ["1636", "1635", "1638"])
        pork = page["items"][1]
        self.assertEqual((pork["name"], pork["price"], pork["price_excl_tax"]),
                         ("ワイルドポークマウンテン２００ｇ", 1518, 1380))
        self.assertIsNone(pork["price_max"])
        self.assertIsNone(pork["price_variants"])
        self.assertEqual(pork["link"], "/fmenu_detail.html?fmenu_item_id=1635")

    def test_size_variants_and_note(self):
        beef = P.parse_steakdon_fair_list(S.steakdon_fair_list())["items"][0]
        self.assertEqual((beef["price"], beef["price_max"], beef["price_excl_tax"]), (3278, 4818, 2980))
        self.assertEqual(beef["price_variants"], [
            {"label": "100g", "price": 3278}, {"label": "150g", "price": 3938}, {"label": "200g", "price": 4818}])
        self.assertEqual(beef["note"], "※店舗限定")

    def test_unreadable_item_is_counted_as_skipped(self):
        items = [("9999", "時価ステーキ", "時価")] + list(S.STEAKDON_ITEMS)
        page = P.parse_steakdon_fair_list(S.steakdon_fair_list(items=items))
        self.assertEqual(page["skipped"], 1)
        self.assertEqual([i["pid"] for i in page["items"]], ["1636", "1635", "1638"])
        self.assertEqual(P.parse_steakdon_fair_list(S.steakdon_fair_list())["skipped"], 0)

    def test_commented_out_item_is_ignored(self):
        extra = ('<!-- <li><a href="fmenu_detail.html?fmenu_item_id=9999">'
                 '<p class="menu_name">幻のメニュー</p><p class="menu_price">100円（税込110円）</p></a></li> -->')
        page = P.parse_steakdon_fair_list(S.steakdon_fair_list(extra=extra))
        self.assertEqual([i["pid"] for i in page["items"]], ["1636", "1635", "1638"])

    def test_description_is_never_read(self):
        extra = ('<li><a href="fmenu_detail.html?fmenu_item_id=2000">'
                 '<p class="menu_name">説明つき商品</p><p class="menu_price">500円（税込550円）</p>'
                 '<p class="menu_txt">北海道産の素材を使った説明文</p></a></li>')
        page = P.parse_steakdon_fair_list(S.steakdon_fair_list(extra=extra))
        self.assertNotIn("説明文", str(page))
        self.assertEqual(page["items"][-1]["name"], "説明つき商品")

    def test_no_price_means_empty_items_and_missing_structure_is_error(self):
        no_price = S.steakdon_fair_list([("3000", "価格が画像だけ", "画像のみ")])
        self.assertEqual(P.parse_steakdon_fair_list(no_price)["items"], [])
        with self.assertRaises(ValueError):
            P.parse_steakdon_fair_list("<html>構造が変わった</html>")
        with self.assertRaises(ValueError):
            P.parse_steakdon_fair_list('<div class="menu_list_subtitle"><p>フェアメニュー</p></div><p>枠が無い</p>')

    def test_ids_are_stable_across_runs(self):
        a = [i["pid"] for i in P.parse_steakdon_fair_list(S.steakdon_fair_list())["items"]]
        b = [i["pid"] for i in P.parse_steakdon_fair_list(S.steakdon_fair_list())["items"]]
        self.assertEqual(a, b)


class TestSteakdonNews(unittest.TestCase):
    def test_entries(self):
        news = P.parse_steakdon_news(S.steakdon_news([
            ("2026年09月09日", 1041, "9月17日（木）より「マロンスイーツフェア」開始"),
            ("2026年11月3日", 1073, "11月6日ステーキのどん公田店<br>営業時間変更について")]))
        self.assertEqual(news[0]["date"], "2026-09-09")
        self.assertEqual(news[0]["url"], "https://www.steak-don.jp/news_detail.html?num=1041")
        self.assertIn("マロンスイーツフェア", news[0]["title"])
        self.assertEqual(news[1]["date"], "2026-11-03")
        self.assertNotIn("<br>", news[1]["title"])

    def test_garbage_is_empty(self):
        self.assertEqual(P.parse_steakdon_news("<html>変わった</html>"), [])


class TestJollypastaMenu(unittest.TestCase):
    def test_items_prices_and_dedup(self):
        items = P.parse_jollypasta_menu(S.jollypasta_menu_json())
        self.assertEqual([i["pid"] for i in items],
                         ["season-r_soup_oystercream", "season-r_oyster_ajillo", "season-r_oyster_butter",
                          "season-r_mitei", "appetizer-a_teiban", "dolce-d_applepie"])
        top = items[0]
        self.assertEqual((top["name"], top["price_excl_tax"], top["price"]),
                         ("～スープパスタ～ 牡蠣と彩り野菜のクリームスープパスタ", 1490, 1639))
        self.assertEqual(top["category"], "季節のおすすめ")
        self.assertEqual(top["official_url"], "https://www.jolly-pasta.co.jp/menu/season/r_soup_oystercream.html")
        # 前菜にも載る牡蠣のアヒージョは1件だけ残り、所在は「季節のおすすめ」が優先される
        ajillo = [i for i in items if i["pid"] == "season-r_oyster_ajillo"]
        self.assertEqual(len(ajillo), 1)
        self.assertEqual(ajillo[0]["category"], "季節のおすすめ")
        # 金額が無い商品は価格Noneで返る(対象にするかは巡回側が決める)
        self.assertIsNone(items[3]["price"])
        self.assertIsNone(items[3]["price_excl_tax"])

    def test_unread_keys_are_not_in_the_result(self):
        for i in P.parse_jollypasta_menu(S.jollypasta_menu_json()):
            self.assertEqual(set(i), {"pid", "name", "price", "price_excl_tax", "category", "official_url"})

    def test_broken_json_raises(self):
        with self.assertRaises(ValueError):
            P.parse_jollypasta_menu("{broken")

    def test_missing_season_category_raises(self):
        with self.assertRaises(ValueError):
            P.parse_jollypasta_menu('{"前菜": []}')

    def test_row_without_name_or_url_raises(self):
        with self.assertRaises(ValueError):
            P.parse_jollypasta_menu('{"季節のおすすめ": [{"名称": "x"}]}')


class TestJollypastaNews(unittest.TestCase):
    def test_index(self):
        idx = P.parse_jollypasta_news_index(S.jollypasta_news_index([
            ("2026.11.24", "/info/menu/20261124.html", "メニュー", "12月1日(火)「窯焼きチーズパスタフェア」が始まります！"),
            ("2026.11.20", "/info/info/20261120.html", "お知らせ", "年末年始の営業時間について"),
        ]))
        self.assertEqual(idx[0], {"date": "2026-11-24",
                                  "title": "12月1日(火)「窯焼きチーズパスタフェア」が始まります！",
                                  "url": "https://www.jolly-pasta.co.jp/info/menu/20261124.html",
                                  "category": "メニュー"})
        self.assertEqual(idx[1]["category"], "お知らせ")
        self.assertEqual(P.parse_jollypasta_news_index("<html>変わった</html>"), [])

    def test_article_and_headline_launch(self):
        art = P.parse_jollypasta_news_article(
            S.jollypasta_news_article(body="★「～窯焼きチーズパスタ～ 牡蠣と燻製ベーコンのクリームソース」"),
            "https://www.jolly-pasta.co.jp/info/menu/20261124.html")
        self.assertEqual(art["date"], "2026-11-24")
        self.assertEqual(art["title"], "12月1日(火)「窯焼きチーズパスタフェア」が始まります！")
        self.assertEqual(art["launch_date"], "2026-12-01")  # 見出し冒頭の日付。年は掲載日から補う
        self.assertIn("牡蠣と燻製ベーコンのクリームソース", art["text"])
        self.assertNotIn("ニュース一覧に戻る", art["text"])  # 本文の後ろのボタンは含めない

    def test_article_year_rollover(self):
        art = P.parse_jollypasta_news_article(
            S.jollypasta_news_article(date="2026.12.25", title="1月6日(火)「新春フェア」が始まります！"),
            "https://www.jolly-pasta.co.jp/info/menu/20261225.html")
        self.assertEqual(art["launch_date"], "2027-01-06")

    def test_article_without_headline_date(self):
        art = P.parse_jollypasta_news_article(
            S.jollypasta_news_article(title="「窯焼きチーズパスタフェア」が始まります！"),
            "https://www.jolly-pasta.co.jp/info/menu/20261124.html")
        self.assertIsNone(art["launch_date"])

    def test_article_garbage_is_none(self):
        self.assertIsNone(P.parse_jollypasta_news_article("<html>変わった</html>", "https://x/"))

    def test_fair_name(self):
        self.assertEqual(P.jollypasta_fair_name("12月1日(火)「窯焼きチーズパスタフェア」が始まります！"),
                         "窯焼きチーズパスタフェア")
        self.assertIsNone(P.jollypasta_fair_name("年末年始の営業時間について"))


if __name__ == "__main__":
    unittest.main()
