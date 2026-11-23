"""巡回(デニーズ・ジョナサン・ステーキのどん)と共通の仕組み(販売状況の追跡・歯止め・急減の検知・実行要約・連続日数・設定)のテスト。ネットワーク不使用。"""
import json
import unittest
from unittest import mock

import helpers
from helpers import DENNYS, SKY, JOYFULL, FakeSite, TempData, run_chain, BlockedError, NotFoundError
import crawl
import synth as S

D_MENU = DENNYS + "/menu/"
D_NEWS = DENNYS + "/news/"
D_OIMO = DENNYS + "/menu/oimo/"
D_COLLAB = DENNYS + "/menu/collaboration17/"
J_TOP = SKY + "/jonathan/menu/"
J_FAIR = SKY + "/jonathan/menu/fair/index.html"
J_DESSERT = SKY + "/jonathan/menu/dessert/index.html"
SD = "https://www.steak-don.jp"
SD_LIST = SD + "/fmenu_list.html?fmenu_categ_id=94"
SD_NEWS = SD + "/news.html"
SD_NEWS_ENTRIES = [("2026年09月09日", 1041, "9月17日（木）より「マロンスイーツフェア」開始")]
COCOS = "https://www.cocos-jpn.co.jp"
C_FAIR = COCOS + "/menu/fair/"
C_NEWS = COCOS + "/news/2026/menu/"

COCOS_NEWS = [
    ("/news/2026/menu/1119-122027.html", "2026-11-19",
     "本日より販売開始！ココスの期間限定スイーツ！「勤労感謝の芋栗かぼちゃクレープ」、ココウェブで200円引きクーポン配信中！"),
    ("/news/2026/menu/1105-122026.html", "2026-11-05",
     "【11月19日(木)開始】ココスの期間限定スイーツ！「勤労感謝の芋栗かぼちゃクレープ」、ココウェブで200円引きクーポンを配信します！"),
    ("/news/2026/menu/1006-115296.html", "2026-10-06",
     "【10月13日(火)開始】濃厚なチョコや甘酸っぱいカシスが上品な甘さのマロンを引き立てる！ココスが「マロンフェア」を開催！"),
]


def cocos_site(fairs=None, news=COCOS_NEWS):
    s = FakeSite()
    # 実サーバーは robots.txt が無く、存在しないパスに 403 でエラーページを返す
    s.set(COCOS + "/robots.txt", BlockedError("HTTP 403"))
    s.set(C_FAIR, S.cocos_fair_page(fairs) if fairs is not None else S.cocos_fair_page())
    s.set(C_NEWS, S.cocos_news(news))
    return s

OIMO_ITEMS = [
    ("蜜いものザ・サンデー～紅天使使用", 1790, 1969, "/menu/dessert/sweet-potato-sundae/"),
    ("蜜いものブリュレパンケーキ（パンケーキ4枚）", 980, 1078, "/menu/dessert/sweet-potato-brulee-pancakes/"),
    ("おいもプリン", 300, 330, "/menu/dessert/sweet-potato-pudding/"),
]
COLLAB_ITEMS = [("麻婆牡蠣＆豆腐", 690, 759, None), ("辛味噌らぁ麺", 1450, 1595, None)]
NEWS = [("2026/10/14", "「蜜いものザ・サンデー」&初登場「蜜いものブリュレパンケーキ」全8品10月28日（水）販売開始", "リード"),
        ("2026/10/1", "デニーズ×飯田商店 監修の新境地！ 10月14日（水）スタート", "リード")]


def dennys_site(oimo=OIMO_ITEMS, collab=COLLAB_ITEMS, news=NEWS, fairs=None):
    s = FakeSite()
    s.set(DENNYS + "/robots.txt", NotFoundError("404"))
    s.set(D_MENU, S.dennys_menu(fairs) if fairs else S.dennys_menu())
    s.set(D_OIMO, S.dennys_fair("蜜いもデザート", oimo))
    s.set(D_COLLAB, S.dennys_fair("飯田商店監修「味噌らぁ麺」", collab))
    s.set(D_NEWS, S.dennys_news(news))
    return s


def jonathan_site(fair_alt=S.JONATHAN_FAIR_ALT, dessert_alt=None, slugs=("collab", "fair", "dessert", "drink_bar")):
    s = FakeSite()
    s.set(SKY + "/robots.txt", "User-agent: *\nAllow: /\nDisallow: /company/\n")
    s.set(J_TOP, S.jonathan_top(slugs))
    s.set(J_FAIR, S.jonathan_page("秋のよくばりマルシェ", [fair_alt]))
    dessert_alt = dessert_alt or S.alt(("季節のジョナパフェ（早生みかん）", 999, 1099))
    s.set(J_DESSERT, S.jonathan_page("しあわせ早生みかん", [dessert_alt]))
    return s


def steakdon_site(items=S.STEAKDON_ITEMS, news=SD_NEWS_ENTRIES):
    s = FakeSite()
    s.set(SD + "/robots.txt", NotFoundError("404"))
    s.set(SD_LIST, S.steakdon_fair_list(items))
    s.set(SD_NEWS, S.steakdon_news(news))
    return s


def ids(chain):
    return sorted(p["product_id"] for p in crawl.load_chain_products(chain))


BIGBOY = "https://www.bigboyjapan.co.jp"
B_MENU = BIGBOY + "/menu/grand/"
B_FAIR = BIGBOY + "/fair/"
B_NEWS6555 = BIGBOY + "/news/fair/6555.html"

OIMO_ITEMS = [
    ("蜜いものザ・サンデー～紅天使使用", 1790, 1969, "/menu/dessert/sweet-potato-sundae/"),
    ("蜜いものブリュレパンケーキ（パンケーキ4枚）", 980, 1078, "/menu/dessert/sweet-potato-brulee-pancakes/"),
    ("おいもプリン", 300, 330, "/menu/dessert/sweet-potato-pudding/"),
]
COLLAB_ITEMS = [("麻婆牡蠣＆豆腐", 690, 759, None), ("辛味噌らぁ麺", 1450, 1595, None)]
NEWS = [("2026/10/14", "「蜜いものザ・サンデー」&初登場「蜜いものブリュレパンケーキ」全8品10月28日（水）販売開始", "リード"),
        ("2026/10/1", "デニーズ×飯田商店 監修の新境地！ 10月14日（水）スタート", "リード")]


def dennys_site(oimo=OIMO_ITEMS, collab=COLLAB_ITEMS, news=NEWS, fairs=None):
    s = FakeSite()
    s.set(DENNYS + "/robots.txt", NotFoundError("404"))
    s.set(D_MENU, S.dennys_menu(fairs) if fairs else S.dennys_menu())
    s.set(D_OIMO, S.dennys_fair("蜜いもデザート", oimo))
    s.set(D_COLLAB, S.dennys_fair("飯田商店監修「味噌らぁ麺」", collab))
    s.set(D_NEWS, S.dennys_news(news))
    return s


def jonathan_site(fair_alt=S.JONATHAN_FAIR_ALT, dessert_alt=None, slugs=("collab", "fair", "dessert", "drink_bar")):
    s = FakeSite()
    s.set(SKY + "/robots.txt", "User-agent: *\nAllow: /\nDisallow: /company/\n")
    s.set(J_TOP, S.jonathan_top(slugs))
    s.set(J_FAIR, S.jonathan_page("秋のよくばりマルシェ", [fair_alt]))
    dessert_alt = dessert_alt or S.alt(("季節のジョナパフェ（早生みかん）", 999, 1099))
    s.set(J_DESSERT, S.jonathan_page("しあわせ早生みかん", [dessert_alt]))
    return s


def bigboy_site(items=S.BIGBOY_ITEMS, article=S.bigboy_news_article):
    s = FakeSite()
    s.set(BIGBOY + "/robots.txt", NotFoundError("404"))
    s.set(B_MENU, S.bigboy_grand_menu(items))
    s.set(B_FAIR, S.bigboy_fair_list())
    s.set(B_NEWS6555, article() if callable(article) else article)
    return s


def ids(chain):
    return sorted(p["product_id"] for p in crawl.load_chain_products(chain))


JF_LIST = JOYFULL + "/menu?category=19"
JF_NEWS = JOYFULL + "/news?category=menu"

OIMO_ITEMS = [
    ("蜜いものザ・サンデー～紅天使使用", 1790, 1969, "/menu/dessert/sweet-potato-sundae/"),
    ("蜜いものブリュレパンケーキ（パンケーキ4枚）", 980, 1078, "/menu/dessert/sweet-potato-brulee-pancakes/"),
    ("おいもプリン", 300, 330, "/menu/dessert/sweet-potato-pudding/"),
]
COLLAB_ITEMS = [("麻婆牡蠣＆豆腐", 690, 759, None), ("辛味噌らぁ麺", 1450, 1595, None)]
NEWS = [("2026/10/14", "「蜜いものザ・サンデー」&初登場「蜜いものブリュレパンケーキ」全8品10月28日（水）販売開始", "リード"),
        ("2026/10/1", "デニーズ×飯田商店 監修の新境地！ 10月14日（水）スタート", "リード")]


def dennys_site(oimo=OIMO_ITEMS, collab=COLLAB_ITEMS, news=NEWS, fairs=None):
    s = FakeSite()
    s.set(DENNYS + "/robots.txt", NotFoundError("404"))
    s.set(D_MENU, S.dennys_menu(fairs) if fairs else S.dennys_menu())
    s.set(D_OIMO, S.dennys_fair("蜜いもデザート", oimo))
    s.set(D_COLLAB, S.dennys_fair("飯田商店監修「味噌らぁ麺」", collab))
    s.set(D_NEWS, S.dennys_news(news))
    return s


JOYFULL_ITEMS = [
    (602, "【2026年12月1日（火）15時より販売】テストハンバーグコンボ", 1299, 1428),
    (527, "「幻のコショウのチキン竜田」", 939, 1032),
    (502, "「黒ごまアイスのパフェ」", 769, 845),
]
JOYFULL_FAIRS = {602: "「ジョイフル×テスト」コラボメニュー", 527: "世界の山ちゃんフェア", 502: "世界の山ちゃんフェア"}
JOYFULL_NEWS = [(99, "2026.10.02", "【ジョイフル】「世界の山ちゃんフェア」2026年10月13日（火）15時より販売開始!!")]


def joyfull_site(items=JOYFULL_ITEMS, fairs=None, news=JOYFULL_NEWS):
    fairs = JOYFULL_FAIRS if fairs is None else fairs
    s = FakeSite()
    s.set(JOYFULL + "/robots.txt", "User-agent: *\nDisallow:\n")
    s.set(JF_LIST, S.joyfull_list(items))
    for pid, name, ex, inc in items:
        if pid in fairs:
            s.set(JOYFULL + f"/menu/{pid}", S.joyfull_detail(fairs[pid], name))
    s.set(JF_NEWS, S.joyfull_news(news))
    return s


def jonathan_site(fair_alt=S.JONATHAN_FAIR_ALT, dessert_alt=None, slugs=("collab", "fair", "dessert", "drink_bar")):
    s = FakeSite()
    s.set(SKY + "/robots.txt", "User-agent: *\nAllow: /\nDisallow: /company/\n")
    s.set(J_TOP, S.jonathan_top(slugs))
    s.set(J_FAIR, S.jonathan_page("秋のよくばりマルシェ", [fair_alt]))
    dessert_alt = dessert_alt or S.alt(("季節のジョナパフェ（早生みかん）", 999, 1099))
    s.set(J_DESSERT, S.jonathan_page("しあわせ早生みかん", [dessert_alt]))
    return s


def ids(chain):
    return sorted(p["product_id"] for p in crawl.load_chain_products(chain))


class TestConfig(unittest.TestCase):
    def test_user_agent_is_plain_and_honest(self):
        self.assertEqual(crawl.UA, "FamiresPochi/1.0 (+https://famires.netaful.jp/)")
        self.assertNotIn("Mozilla", crawl.UA)

    def test_limits_and_thresholds_from_the_brief(self):
        cfg = crawl.CONFIG
        self.assertEqual(sorted(c["slug"] for c in cfg["chains"]), ["bigboy", "cocos", "dennys", "jonathan", "joyfull", "steakdon"])
        self.assertEqual(cfg["max_requests_per_run"], {"dennys": 25, "jonathan": 5, "cocos": 10, "bigboy": 20, "joyfull": 25, "steakdon": 10})
        self.assertEqual(cfg["new_burst_min_by_chain"], {"dennys": 20, "jonathan": 15, "cocos": 20, "bigboy": 15, "joyfull": 20, "steakdon": 15})
        self.assertEqual(cfg["new_burst_ratio"], 0.6)
        for c in ("dennys", "jonathan", "cocos", "bigboy", "joyfull", "steakdon"):
            self.assertGreaterEqual(cfg["request_interval_seconds"][c], 3)

    def test_site_identity_and_ads(self):
        cfg = crawl.CONFIG
        self.assertEqual(cfg["site_title"], "ファミレスポチ")
        self.assertEqual(cfg["site_url"], "https://famires.netaful.jp/")
        self.assertEqual(cfg["adsense_client_id"], "ca-pub-2195959398357532")
        self.assertEqual(cfg["adsense_ad_slot"], "1215675017")
        self.assertEqual(cfg["ga_measurement_id"], "G-D8F2T2XB5W")
        self.assertNotIn("famires", [s["url"] for s in cfg["related_sites"]])
        self.assertIn("https://cafe.netaful.jp/", [s["url"] for s in cfg["related_sites"]])

    def test_throttle_never_below_one_second(self):
        with mock.patch.dict(crawl.INTERVALS, {"dennys": 0}):
            t = crawl.Throttle()
            with mock.patch.object(crawl.time, "sleep") as sl, mock.patch.object(crawl.time, "monotonic", side_effect=[0.0, 0.0, 0.2, 0.2]):
                t.wait("dennys")
                t.wait("dennys")
            self.assertGreaterEqual(sl.call_args.args[0], 0.8 - 1e-9)

    def test_getter_enforces_request_cap(self):
        g = crawl.Getter()
        g.throttle.wait = lambda chain: None
        with mock.patch.dict(crawl.MAX_REQUESTS, {"jonathan": 2}), mock.patch.object(crawl, "fetch", return_value="x"):
            g("jonathan", "https://a/1")
            g("jonathan", "https://a/2")
            with self.assertRaises(RuntimeError):
                g("jonathan", "https://a/3")


class TestDennysCrawl(unittest.TestCase):
    def test_first_run_records_all_fair_items_with_facts_only(self):
        with TempData():
            site = dennys_site()
            _, st = run_chain(crawl.crawl_dennys, site, "2026-11-23")
            self.assertTrue(st["dennys"]["list_ok"])
            self.assertEqual(len(ids("dennys")), 5)
            p = helpers.prod("dennys", "dessert-sweet-potato-sundae")
            self.assertEqual((p["name"], p["price"], p["price_excl_tax"]), ("蜜いものザ・サンデー～紅天使使用", 1969, 1790))
            self.assertEqual(p["fair"], "蜜いもデザート")
            self.assertEqual(p["official_url"], DENNYS + "/menu/dessert/sweet-potato-sundae/")
            self.assertEqual(p["price_history"], [{"date": "2026-11-23", "price": 1969}])
            c = [x for x in crawl.load_chain_products("dennys") if x["name"] == "辛味噌らぁ麺"][0]
            self.assertEqual(c["official_url"], D_COLLAB)  # リンクの無い商品はフェアページが出典
            self.assertIn("一部の店舗", c["stores_note"])

    def test_no_description_or_image_keys_are_saved(self):
        with TempData():
            run_chain(crawl.crawl_dennys, dennys_site(), "2026-11-23")
            for p in crawl.load_chain_products("dennys"):
                blob = json.dumps(p, ensure_ascii=False)
                for k in ("image", "photo", "description", "lead", "nutrition", "allergen"):
                    self.assertNotIn(k, blob)

    def test_request_count_is_small_and_follows_menu_links_each_time(self):
        with TempData():
            site = dennys_site()
            run_chain(crawl.crawl_dennys, site, "2026-11-23")
            self.assertEqual(site.count("dennys.jp"), len(site.calls))
            self.assertLessEqual(len(site.calls), 8)  # robots + menu + fair 2 + news 1
            # ページ名が変わっても /menu/ から辿り直す
            s2 = dennys_site(fairs=[("/menu/winter2027/", "冬のフェア")])
            s2.set(DENNYS + "/menu/winter2027/", S.dennys_fair("冬のフェア", [("冬の新作", 500, 550, None)]))
            run_chain(crawl.crawl_dennys, s2, "2026-11-24")
            self.assertIn(DENNYS + "/menu/winter2027/", s2.calls)
            self.assertNotIn(D_OIMO, s2.calls)

    def test_launch_date_from_news_by_product_name_and_fair_name(self):
        with TempData():
            run_chain(crawl.crawl_dennys, dennys_site(), "2026-11-23")
            sundae = helpers.prod("dennys", "dessert-sweet-potato-sundae")
            self.assertEqual(sundae["launch_date"], "2026-10-28")
            self.assertEqual(sundae["launch_date_source"], "official_news")
            self.assertEqual(sundae["news_url"], DENNYS + "/news/")
            # 名前では照合できず、フェア名(蜜いもデザート)でも見出しに無い→開始日は記録開始日(launch_date なし)
            pudding = helpers.prod("dennys", "dessert-sweet-potato-pudding")
            self.assertIsNone(pudding["launch_date"])

    def test_launch_date_by_fair_name(self):
        with TempData():
            news = [("2026/10/14", "蜜いもデザート全8品 10月28日（水）販売開始", "")]
            run_chain(crawl.crawl_dennys, dennys_site(news=news), "2026-11-23")
            p = helpers.prod("dennys", "dessert-sweet-potato-pudding")
            self.assertEqual((p["launch_date"], p["launch_date_source"]), ("2026-10-28", "official_news_fair"))

    def test_unmatched_news_leaves_recording_start(self):
        with TempData():
            news = [("2026/10/14", "全く別の発表 10月28日（水）販売開始", "")]
            run_chain(crawl.crawl_dennys, dennys_site(news=news), "2026-11-23")
            self.assertTrue(all(p["launch_date"] is None for p in crawl.load_chain_products("dennys")))

    def test_news_failure_does_not_stop_recording(self):
        with TempData():
            site = dennys_site()
            site.set(D_NEWS, RuntimeError("timeout"))
            _, st = run_chain(crawl.crawl_dennys, site, "2026-11-23")
            self.assertEqual(len(ids("dennys")), 5)
            self.assertTrue(st["dennys"]["list_ok"])

    def test_ended_after_two_misses_on_different_days(self):
        with TempData():
            run_chain(crawl.crawl_dennys, dennys_site(), "2026-11-23")
            fewer = dennys_site(oimo=OIMO_ITEMS[:2])
            run_chain(crawl.crawl_dennys, fewer, "2026-11-24")
            run_chain(crawl.crawl_dennys, fewer, "2026-11-24")  # 同じ日は1回
            p = helpers.prod("dennys", "dessert-sweet-potato-pudding")
            self.assertEqual((p["status"], p["missed_runs"]), ("on_sale", 1))
            run_chain(crawl.crawl_dennys, fewer, "2026-11-25")
            p = helpers.prod("dennys", "dessert-sweet-potato-pudding")
            self.assertEqual((p["status"], p["ended_observed_at"]), ("ended", "2026-11-25"))
            self.assertEqual(helpers.prod("dennys", "dessert-sweet-potato-sundae")["status"], "on_sale")

    def test_relaunch_and_price_change(self):
        with TempData():
            run_chain(crawl.crawl_dennys, dennys_site(), "2026-11-23")
            run_chain(crawl.crawl_dennys, dennys_site(oimo=OIMO_ITEMS[:2]), "2026-11-24")
            run_chain(crawl.crawl_dennys, dennys_site(oimo=OIMO_ITEMS[:2]), "2026-11-25")
            changed = [("おいもプリン", 320, 352, "/menu/dessert/sweet-potato-pudding/")]
            run_chain(crawl.crawl_dennys, dennys_site(oimo=OIMO_ITEMS[:2] + changed), "2026-12-01")
            p = helpers.prod("dennys", "dessert-sweet-potato-pudding")
            self.assertEqual(p["status"], "on_sale")
            self.assertEqual(p["relaunches"][0]["reappeared_at"], "2026-12-01")
            self.assertEqual(p["price"], 352)
            self.assertTrue(p["price_history"][-1]["relaunch"])

    def test_fair_page_without_price_is_incomplete_and_nothing_ends(self):
        with TempData():
            run_chain(crawl.crawl_dennys, dennys_site(), "2026-11-23")
            broken = dennys_site()
            broken.set(D_OIMO, '<h1 class="label">蜜いもデザート</h1><img alt="画像だけになった 1,969円">')
            for d in ("2026-11-24", "2026-11-25", "2026-11-26"):
                _, st = run_chain(crawl.crawl_dennys, broken, d)
                self.assertFalse(st["dennys"]["list_ok"])
            self.assertTrue(all(p["status"] == "on_sale" for p in crawl.load_chain_products("dennys")))
            # 取れた分(別のフェア)の記録は続く
            self.assertEqual(helpers.prod("dennys", "dessert-sweet-potato-sundae")["last_seen_at"], "2026-11-23")

    def test_one_fair_page_failing_is_incomplete(self):
        with TempData():
            run_chain(crawl.crawl_dennys, dennys_site(), "2026-11-23")
            site = dennys_site()
            site.set(D_COLLAB, NotFoundError("404"))
            _, st = run_chain(crawl.crawl_dennys, site, "2026-11-24")
            self.assertFalse(st["dennys"]["list_ok"])

    def test_menu_structure_change_or_zero_fairs_is_list_failed(self):
        with TempData():
            for menu in ("<html>変わった</html>", S.dennys_menu([])):
                site = dennys_site()
                site.set(D_MENU, menu)
                p, st = run_chain(crawl.crawl_dennys, site, "2026-11-23")
                self.assertFalse(st["dennys"]["list_ok"])
                self.assertEqual(ids("dennys"), [])

    def test_blocked_stops_without_workaround(self):
        with TempData():
            site = dennys_site()
            site.set(D_OIMO, BlockedError("HTTP 403"))
            _, st = run_chain(crawl.crawl_dennys, site, "2026-11-23")
            self.assertTrue(st["dennys"]["blocked"])
            self.assertFalse(st["dennys"]["list_ok"])

    def test_robots_disallow_skips(self):
        with TempData():
            site = dennys_site()
            site.set(DENNYS + "/robots.txt", "User-agent: *\nDisallow: /menu/\n")
            run_chain(crawl.crawl_dennys, site, "2026-11-23")
            self.assertEqual(ids("dennys"), [])
            self.assertNotIn(D_MENU, site.calls)

    def test_burst_guard_holds_a_restructure_but_allows_a_real_fair(self):
        with TempData():
            run_chain(crawl.crawl_dennys, dennys_site(), "2026-11-23")  # baseline: 5件
            # 本物の新フェア: 新規10件(閾値20以下)は記録される
            ten = [(f"新作{i}", 500 + i, 550 + i, f"/menu/new/item{i}/") for i in range(10)]
            _, st = run_chain(crawl.crawl_dennys, dennys_site(oimo=OIMO_ITEMS + ten), "2026-11-24")
            self.assertEqual(st["dennys"]["new_products"], 10)
            # 全件のIDが変わる構造変更(新規25件 > 閾値)は保留
            many = [(f"別{i}", 500, 550, f"/menu/chg/x{i}/") for i in range(25)]
            pend, st = run_chain(crawl.crawl_dennys, dennys_site(oimo=many, collab=[]), "2026-11-25")
            self.assertEqual(st["dennys"]["new_products"], 0)
            self.assertFalse(st["dennys"]["list_ok"])
            self.assertEqual(pend["dennys"]["_suspected_restructure"]["threshold"], 20)
            self.assertEqual(len(ids("dennys")), 15)
            self.assertTrue(all(p["status"] == "on_sale" and p["missed_runs"] == 0 for p in crawl.load_chain_products("dennys")))

    def test_burst_threshold_values(self):
        self.assertEqual(crawl.burst_threshold("dennys", 10), 20)
        self.assertEqual(crawl.burst_threshold("jonathan", 10), 15)
        self.assertEqual(crawl.burst_threshold("jonathan", 50), 30)  # 一覧×0.6 のほうが大きいとき
        self.assertEqual(crawl.burst_threshold("cocos", 10), 20)


class TestJonathanCrawl(unittest.TestCase):
    def test_first_run_from_alt(self):
        with TempData():
            site = jonathan_site()
            _, st = run_chain(crawl.crawl_jonathan, site, "2026-11-23")
            self.assertTrue(st["jonathan"]["list_ok"])
            names = sorted(p["name"] for p in crawl.load_chain_products("jonathan"))
            self.assertIn("炙り鮭はらすといくらの出汁茶漬け膳", names)
            self.assertIn("季節のジョナパフェ（早生みかん）", names)
            self.assertNotIn("ドリンクバーセット", names)  # config の jonathan_exclude_names
            # 同じ名前が fair と dessert の両方に載っても1件
            self.assertEqual(len(names), len(set(names)))
            p = [x for x in crawl.load_chain_products("jonathan") if x["name"] == "炙り鮭はらすといくらの出汁茶漬け膳"][0]
            self.assertEqual((p["price"], p["price_excl_tax"], p["fair"]), (1539, 1399, "秋のよくばりマルシェ"))
            self.assertEqual(p["official_url"], J_FAIR)
            self.assertIsNone(p["launch_date"])

    def test_requests_within_limit_and_skipped_pages_not_fetched(self):
        with TempData():
            site = jonathan_site()
            run_chain(crawl.crawl_jonathan, site, "2026-11-23")
            self.assertLessEqual(len(site.calls), crawl.CONFIG["max_requests_per_run"]["jonathan"])
            self.assertNotIn(SKY + "/jonathan/menu/collab/index.html", site.calls)
            self.assertNotIn(SKY + "/jonathan/menu/drink_bar/index.html", site.calls)
            self.assertFalse(any("corp.skylark" in u or "takeout.skylark" in u for u in site.calls))

    def test_menu_top_failure_is_incomplete_but_fair_page_is_recorded(self):
        with TempData():
            site = jonathan_site()
            site.set(J_TOP, NotFoundError("404"))
            _, st = run_chain(crawl.crawl_jonathan, site, "2026-11-23")
            self.assertFalse(st["jonathan"]["list_ok"])
            self.assertGreater(len(ids("jonathan")), 0)

    def test_too_many_pages_is_incomplete(self):
        with TempData():
            site = jonathan_site(slugs=("fair", "dessert", "a1", "a2"))
            _, st = run_chain(crawl.crawl_jonathan, site, "2026-11-23")
            self.assertFalse(st["jonathan"]["list_ok"])

    def test_fair_page_without_price_is_incomplete_and_nothing_ends(self):
        with TempData():
            run_chain(crawl.crawl_jonathan, jonathan_site(), "2026-11-23")
            broken = jonathan_site(fair_alt="価格が画像だけになった。かぼちゃサラダ")
            for d in ("2026-11-24", "2026-11-25", "2026-11-26"):
                _, st = run_chain(crawl.crawl_jonathan, broken, d)
                self.assertFalse(st["jonathan"]["list_ok"])
            self.assertTrue(all(p["status"] == "on_sale" for p in crawl.load_chain_products("jonathan")))

    def test_dessert_page_that_had_items_and_becomes_empty_is_incomplete(self):
        with TempData():
            run_chain(crawl.crawl_jonathan, jonathan_site(), "2026-11-23")
            _, st = run_chain(crawl.crawl_jonathan, jonathan_site(dessert_alt="価格なし"), "2026-11-24")
            self.assertFalse(st["jonathan"]["list_ok"])

    def test_ends_after_two_misses_and_price_history(self):
        with TempData():
            run_chain(crawl.crawl_jonathan, jonathan_site(), "2026-11-23")
            gone = jonathan_site(dessert_alt=S.alt(("季節のジョナパフェDX（早生みかん）", 1599, 1759)))
            run_chain(crawl.crawl_jonathan, gone, "2026-11-24")
            _, st = run_chain(crawl.crawl_jonathan, gone, "2026-11-25")
            self.assertEqual(st["jonathan"]["ended"], 1)
            ended = [p for p in crawl.load_chain_products("jonathan") if p["status"] == "ended"]
            self.assertEqual([p["name"] for p in ended], ["季節のジョナパフェ（早生みかん）"])
            self.assertEqual(ended[0]["ended_observed_at"], "2026-11-25")

    def test_blocked(self):
        with TempData():
            site = jonathan_site()
            site.set(J_FAIR, BlockedError("HTTP 429"))
            _, st = run_chain(crawl.crawl_jonathan, site, "2026-11-23")
            self.assertTrue(st["jonathan"]["blocked"])

    def test_burst_guard(self):
        with TempData():
            run_chain(crawl.crawl_jonathan, jonathan_site(), "2026-11-23")
            many = S.alt(*[(f"全く別の新作メニュー{i}", 500, 550) for i in range(20)])
            pend, st = run_chain(crawl.crawl_jonathan, jonathan_site(fair_alt=many), "2026-11-24")
            self.assertEqual(st["jonathan"]["new_products"], 0)
            self.assertIn("_suspected_restructure", pend["jonathan"])


class TestCocosCrawl(unittest.TestCase):
    def test_first_run_records_all_fair_items_with_facts_only(self):
        with TempData():
            site = cocos_site()
            _, st = run_chain(crawl.crawl_cocos, site, "2026-11-23")
            self.assertTrue(st["cocos"]["list_ok"])
            self.assertEqual(len(ids("cocos")), 3)
            p = helpers.prod("cocos", "limited_sweets-roasted_sweet_potato_crepe2611")
            self.assertEqual((p["name"], p["price"], p["price_excl_tax"]), ("勤労感謝の芋栗かぼちゃクレープ", 649, 590))
            self.assertEqual(p["fair"], "ココスの期間限定スイーツ")
            self.assertEqual(p["official_url"], COCOS + "/menu/fair/limited_sweets/roasted_sweet_potato_crepe2611.html")
            self.assertEqual(p["price_history"], [{"date": "2026-11-23", "price": 649}])
            self.assertIn("一部の店舗", p["stores_note"])
            for prod_ in crawl.load_chain_products("cocos"):
                blob = json.dumps(prod_, ensure_ascii=False)
                for k in ("image", "photo", "description", "lead", "nutrition", "allergen"):
                    self.assertNotIn(k, blob)

    def test_robots_txt_403_is_treated_as_no_robots_and_requests_stay_small(self):
        with TempData():
            site = cocos_site()
            run_chain(crawl.crawl_cocos, site, "2026-11-23")
            # robots.txt(403)・フェアページ・ニュースの3リクエストだけ
            self.assertEqual(len(site.calls), 3)
            self.assertLessEqual(len(site.calls), crawl.CONFIG["max_requests_per_run"]["cocos"])

    def test_robots_txt_429_stays_blocked(self):
        with TempData():
            site = cocos_site()
            site.set(COCOS + "/robots.txt", BlockedError("HTTP 429: https://www.cocos-jpn.co.jp/robots.txt"))
            _, st = run_chain(crawl.crawl_cocos, site, "2026-11-23")
            self.assertTrue(st["cocos"]["blocked"])
            self.assertEqual(ids("cocos"), [])

    def test_robots_txt_challenge_stays_blocked(self):
        with TempData():
            site = cocos_site()
            site.set(COCOS + "/robots.txt", BlockedError("challenge page detected: https://www.cocos-jpn.co.jp/robots.txt"))
            _, st = run_chain(crawl.crawl_cocos, site, "2026-11-23")
            self.assertTrue(st["cocos"]["blocked"])
            self.assertEqual(ids("cocos"), [])

    def test_exclude_words_skip_toppings(self):
        with TempData():
            fairs = (("マロンフェア",
                      [("マロンとチョコのパフェ", 1290, 1419,
                        "/menu/fair/marron2610/shinemuscat_parfait2609.html"),
                       ("追加カシスシロップ", 80, 88, None)]),)
            _, st = run_chain(crawl.crawl_cocos, cocos_site(fairs=fairs), "2026-11-23")
            self.assertTrue(st["cocos"]["list_ok"])
            names = [p["name"] for p in crawl.load_chain_products("cocos")]
            self.assertEqual(names, ["マロンとチョコのパフェ"])

    def test_launch_date_from_news_by_product_name_and_fair_name(self):
        with TempData():
            run_chain(crawl.crawl_cocos, cocos_site(), "2026-11-23")
            crepe = helpers.prod("cocos", "limited_sweets-roasted_sweet_potato_crepe2611")
            self.assertEqual((crepe["launch_date"], crepe["launch_date_source"]), ("2026-11-19", "official_news"))
            self.assertEqual(crepe["news_url"], COCOS + "/news/2026/menu/1105-122026.html")
            parfait = helpers.prod("cocos", "marron2610-shinemuscat_parfait2609")
            self.assertEqual((parfait["launch_date"], parfait["launch_date_source"]), ("2026-10-13", "official_news_fair"))

    def test_unmatched_news_leaves_recording_start(self):
        with TempData():
            news = [("/news/2026/menu/1.html", "2026-11-05", "全く別の発表【11月19日(木)開始】")]
            run_chain(crawl.crawl_cocos, cocos_site(news=news), "2026-11-23")
            self.assertTrue(all(p["launch_date"] is None for p in crawl.load_chain_products("cocos")))

    def test_news_failure_does_not_stop_recording(self):
        with TempData():
            site = cocos_site()
            site.set(C_NEWS, RuntimeError("timeout"))
            _, st = run_chain(crawl.crawl_cocos, site, "2026-11-23")
            self.assertEqual(len(ids("cocos")), 3)
            self.assertTrue(st["cocos"]["list_ok"])

    def test_ended_after_two_misses_on_different_days(self):
        with TempData():
            run_chain(crawl.crawl_cocos, cocos_site(), "2026-11-23")
            fewer = cocos_site(fairs=(("ココスの期間限定スイーツ",
                                       [("勤労感謝の芋栗かぼちゃクレープ", 590, 649,
                                         "/menu/fair/limited_sweets/roasted_sweet_potato_crepe2611.html")]),
                                      ("マロンフェア",
                                       [("マロンとチョコのパフェ", 1290, 1419,
                                         "/menu/fair/marron2610/shinemuscat_parfait2609.html")])))
            run_chain(crawl.crawl_cocos, fewer, "2026-11-24")
            run_chain(crawl.crawl_cocos, fewer, "2026-11-25")
            p = helpers.prod("cocos", "marron2610-shinemuscat_crepe2609")
            self.assertEqual((p["status"], p["ended_observed_at"]), ("ended", "2026-11-25"))
            self.assertEqual(helpers.prod("cocos", "marron2610-shinemuscat_parfait2609")["status"], "on_sale")

    def test_fair_section_without_items_is_incomplete_and_nothing_ends(self):
        with TempData():
            run_chain(crawl.crawl_cocos, cocos_site(), "2026-11-23")
            broken = cocos_site(fairs=(("ココスの期間限定スイーツ",
                                        [("勤労感謝の芋栗かぼちゃクレープ", 590, 649,
                                          "/menu/fair/limited_sweets/roasted_sweet_potato_crepe2611.html")]),
                                       ("マロンフェア", [])))
            for d in ("2026-11-24", "2026-11-25", "2026-11-26"):
                _, st = run_chain(crawl.crawl_cocos, broken, d)
                self.assertFalse(st["cocos"]["list_ok"])
            self.assertTrue(all(p["status"] == "on_sale" for p in crawl.load_chain_products("cocos")))

    def test_structure_change_is_list_failed(self):
        with TempData():
            site = cocos_site()
            site.set(C_FAIR, "<html>変わった</html>")
            _, st = run_chain(crawl.crawl_cocos, site, "2026-11-23")
            self.assertFalse(st["cocos"]["list_ok"])
            self.assertEqual(ids("cocos"), [])

    def test_blocked_fair_page_stops(self):
        with TempData():
            site = cocos_site()
            site.set(C_FAIR, BlockedError("HTTP 403"))
            _, st = run_chain(crawl.crawl_cocos, site, "2026-11-23")
            self.assertTrue(st["cocos"]["blocked"])
            self.assertFalse(st["cocos"]["list_ok"])

    def test_burst_guard_holds_a_restructure(self):
        with TempData():
            run_chain(crawl.crawl_cocos, cocos_site(), "2026-11-23")  # baseline: 3件
            many = [(f"別{i}", 500, 550, f"/menu/fair/chg/x{i}.html") for i in range(25)]
            pend, st = run_chain(crawl.crawl_cocos, cocos_site(fairs=(("別フェア", many),)), "2026-11-24")
            self.assertEqual(st["cocos"]["new_products"], 0)
            self.assertFalse(st["cocos"]["list_ok"])
            self.assertEqual(pend["cocos"]["_suspected_restructure"]["threshold"], 20)


class TestBigboyCrawl(unittest.TestCase):
    def test_first_run_records_all_limited_items_with_facts_only(self):
        with TempData():
            site = bigboy_site()
            _, st = run_chain(crawl.crawl_bigboy, site, "2026-11-23")
            self.assertTrue(st["bigboy"]["list_ok"])
            self.assertEqual(len(ids("bigboy")), 3)
            p = [x for x in crawl.load_chain_products("bigboy") if x["name"] == "牡蠣フライ＆大俵ハンバーグ"][0]
            self.assertEqual((p["price"], p["price_max"], p["price_excl_tax"]), (1639, 2035, 1490))
            self.assertEqual(p["price_variants"],
                             [{"label": "大俵150g", "price": 1639}, {"label": "大俵200g", "price": 1815},
                              {"label": "大俵250g", "price": 2035}])
            self.assertEqual(p["price_history"], [{"date": "2026-11-23", "price": 1639, "price_max": 2035}])
            self.assertEqual(p["fair"], "期間限定メニュー")
            self.assertEqual(p["official_url"], B_MENU)
            self.assertIn("一部店舗", p["stores_note"])
            for prod_ in crawl.load_chain_products("bigboy"):
                blob = json.dumps(prod_, ensure_ascii=False)
                for k in ("image", "photo", "description", "lead", "nutrition", "allergen"):
                    self.assertNotIn(k, blob)

    def test_request_count_stays_within_cap(self):
        with TempData():
            site = bigboy_site()
            run_chain(crawl.crawl_bigboy, site, "2026-11-23")
            # robots・グランドメニュー・フェア一覧・ニュース記事1本
            self.assertEqual(len(site.calls), 4)
            self.assertLessEqual(len(site.calls), crawl.CONFIG["max_requests_per_run"]["bigboy"])

    def test_launch_date_from_news_by_product_name(self):
        with TempData():
            run_chain(crawl.crawl_bigboy, bigboy_site(), "2026-11-23")
            sundae = [x for x in crawl.load_chain_products("bigboy")
                      if x["name"] == "甘栗のモンブランファッジサンデー"][0]
            self.assertEqual((sundae["launch_date"], sundae["launch_date_source"]), ("2026-10-20", "official_news"))
            self.assertEqual(sundae["news_url"], B_NEWS6555)
            # 記事に名前が出ない商品は開始日なし(記録開始日)
            kaki = [x for x in crawl.load_chain_products("bigboy") if x["name"] == "牡蠣フライ＆手ごねハンバーグ"][0]
            self.assertIsNone(kaki["launch_date"])

    def test_fair_name_is_never_used_for_launch_matching(self):
        # フェア名は全商品共通の欄名「期間限定メニュー」。その語と開始日を含む記事があっても、
        # 商品名で照合できない商品に開始日が付いてはいけない(フェア名で照合すると全商品に同じ日が付く)
        article = S.bigboy_news_article(
            date="2026/10/01", title="【フェア情報】期間限定メニューのお知らせ",
            body="「ビッグボーイ」では、期間限定メニューとして牡蠣フライを販売します。10月6日（月）から。")
        with TempData():
            run_chain(crawl.crawl_bigboy, bigboy_site(article=article), "2026-11-23")
            prods = crawl.load_chain_products("bigboy")
            self.assertEqual(len(prods), 3)
            self.assertTrue(all(p["launch_date"] is None for p in prods))

    def test_news_failure_does_not_stop_recording(self):
        with TempData():
            site = bigboy_site()
            site.set(B_FAIR, RuntimeError("timeout"))
            _, st = run_chain(crawl.crawl_bigboy, site, "2026-11-23")
            self.assertEqual(len(ids("bigboy")), 3)
            self.assertTrue(st["bigboy"]["list_ok"])
            self.assertTrue(all(p["launch_date"] is None for p in crawl.load_chain_products("bigboy")))

    def test_ended_after_two_misses_on_different_days(self):
        with TempData():
            run_chain(crawl.crawl_bigboy, bigboy_site(), "2026-11-23")
            fewer = bigboy_site(items=S.BIGBOY_ITEMS[:2])
            run_chain(crawl.crawl_bigboy, fewer, "2026-11-24")
            run_chain(crawl.crawl_bigboy, fewer, "2026-11-25")
            sundae = [x for x in crawl.load_chain_products("bigboy")
                      if x["name"] == "甘栗のモンブランファッジサンデー"][0]
            self.assertEqual((sundae["status"], sundae["ended_observed_at"]), ("ended", "2026-11-25"))

    def test_missing_section_or_no_price_is_incomplete_and_nothing_ends(self):
        with TempData():
            run_chain(crawl.crawl_bigboy, bigboy_site(), "2026-11-23")
            for broken_html in ("<html>変わった</html>", S.bigboy_grand_menu(items=[("価格なし商品", [])])):
                site = bigboy_site()
                site.set(B_MENU, broken_html)
                for d in ("2026-11-24", "2026-11-25"):
                    _, st = run_chain(crawl.crawl_bigboy, site, d)
                    self.assertFalse(st["bigboy"]["list_ok"])
            self.assertTrue(all(p["status"] == "on_sale" for p in crawl.load_chain_products("bigboy")))

    def test_blocked_stops_without_workaround(self):
        with TempData():
            site = bigboy_site()
            site.set(B_MENU, BlockedError("HTTP 403"))
            _, st = run_chain(crawl.crawl_bigboy, site, "2026-11-23")
            self.assertTrue(st["bigboy"]["blocked"])
            self.assertFalse(st["bigboy"]["list_ok"])

    def test_robots_disallow_skips(self):
        with TempData():
            site = bigboy_site()
            site.set(BIGBOY + "/robots.txt", "User-agent: *\nDisallow: /menu/\n")
            run_chain(crawl.crawl_bigboy, site, "2026-11-23")
            self.assertEqual(ids("bigboy"), [])
            self.assertNotIn(B_MENU, site.calls)

    def test_burst_threshold_value(self):
        self.assertEqual(crawl.burst_threshold("bigboy", 9), 15)
        self.assertEqual(crawl.burst_threshold("bigboy", 100), 60)


class TestJoyfullCrawl(unittest.TestCase):
    def test_first_run_records_all_with_facts_only(self):
        with TempData():
            site = joyfull_site()
            _, st = run_chain(crawl.crawl_joyfull, site, "2026-11-23")
            self.assertTrue(st["joyfull"]["list_ok"])
            self.assertEqual(ids("joyfull"), ["502", "527", "602"])
            p = helpers.prod("joyfull", "527")
            self.assertEqual((p["name"], p["price"], p["price_excl_tax"]), ("幻のコショウのチキン竜田", 1032, 939))
            self.assertEqual(p["fair"], "世界の山ちゃんフェア")
            self.assertEqual(p["official_url"], JOYFULL + "/menu/527")
            self.assertEqual(p["price_history"], [{"date": "2026-11-23", "price": 1032}])
            self.assertIn("関東エリア店舗", p["stores_note"])
            for prod_ in crawl.load_chain_products("joyfull"):
                blob = json.dumps(prod_, ensure_ascii=False)
                for k in ("image", "photo", "description", "lead", "nutrition", "allergen"):
                    self.assertNotIn(k, blob)

    def test_launch_from_name_prefix_and_from_fair_name_news(self):
        with TempData():
            run_chain(crawl.crawl_joyfull, joyfull_site(), "2026-11-23")
            collab = helpers.prod("joyfull", "602")
            self.assertEqual((collab["launch_date"], collab["launch_date_source"]), ("2026-12-01", "official_menu"))
            self.assertEqual(collab["fair"], "「ジョイフル×テスト」コラボメニュー")
            # 商品名は見出しに無く、フェア名で照合できたもの
            p = helpers.prod("joyfull", "527")
            self.assertEqual((p["launch_date"], p["launch_date_source"]), ("2026-10-13", "official_news_fair"))
            self.assertEqual(p["news_url"], JOYFULL + "/news/99")

    def test_unmatched_news_leaves_recording_start(self):
        with TempData():
            run_chain(crawl.crawl_joyfull, joyfull_site(news=[(1, "2026.11.01", "全く別の発表 11月5日（木）販売開始")]), "2026-11-23")
            self.assertIsNone(helpers.prod("joyfull", "527")["launch_date"])
            # 接頭辞の告知がある商品は、ニュースと関係なく開始日が取れる
            self.assertEqual(helpers.prod("joyfull", "602")["launch_date"], "2026-12-01")

    def test_news_failure_does_not_stop_recording(self):
        with TempData():
            site = joyfull_site()
            site.set(JF_NEWS, RuntimeError("timeout"))
            _, st = run_chain(crawl.crawl_joyfull, site, "2026-11-23")
            self.assertTrue(st["joyfull"]["list_ok"])
            self.assertEqual(len(ids("joyfull")), 3)
            self.assertIsNone(helpers.prod("joyfull", "527")["launch_date"])

    def test_request_count_within_cap(self):
        with TempData():
            site = joyfull_site()
            run_chain(crawl.crawl_joyfull, site, "2026-11-23")
            # robots・一覧・詳細3・news1
            self.assertEqual(len(site.calls), 6)
            self.assertLessEqual(len(site.calls), crawl.CONFIG["max_requests_per_run"]["joyfull"])

    def test_ended_after_two_misses_and_price_change(self):
        with TempData():
            run_chain(crawl.crawl_joyfull, joyfull_site(), "2026-11-23")
            fewer = joyfull_site(items=JOYFULL_ITEMS[:2])
            run_chain(crawl.crawl_joyfull, fewer, "2026-11-24")
            run_chain(crawl.crawl_joyfull, fewer, "2026-11-25")
            p = helpers.prod("joyfull", "502")
            self.assertEqual((p["status"], p["ended_observed_at"]), ("ended", "2026-11-25"))
            changed = joyfull_site(items=[JOYFULL_ITEMS[0], (527, "「幻のコショウのチキン竜田」", 999, 1099)])
            run_chain(crawl.crawl_joyfull, changed, "2026-11-26")
            p = helpers.prod("joyfull", "527")
            self.assertEqual(p["price"], 1099)
            self.assertEqual(p["price_history"][-1], {"date": "2026-11-26", "price": 1099})

    def test_detail_failure_is_incomplete_and_nothing_ends(self):
        with TempData():
            run_chain(crawl.crawl_joyfull, joyfull_site(), "2026-11-23")
            # 記録済みでフェア名のある商品の詳細は取り直さないので、失敗させるのは新規の商品の詳細
            items = JOYFULL_ITEMS + [(700, "新作テスト", 500, 550)]
            fairs = {**JOYFULL_FAIRS, 700: "新フェア"}
            broken = joyfull_site(items=items, fairs=fairs)
            broken.set(JOYFULL + "/menu/700", NotFoundError("404"))
            for d in ("2026-11-24", "2026-11-25", "2026-11-26"):
                _, st = run_chain(crawl.crawl_joyfull, broken, d)
                self.assertFalse(st["joyfull"]["list_ok"])
            self.assertTrue(all(p["status"] == "on_sale" for p in crawl.load_chain_products("joyfull")))

    def test_recorded_name_follows_list_display(self):
        with TempData():
            run_chain(crawl.crawl_joyfull, joyfull_site(), "2026-11-23")
            p = helpers.prod("joyfull", "527")
            p["name"] = "「幻のコショウのチキン竜田」"  # かぎかっこ付きで記録されていた既存データの想定
            crawl.save_product("joyfull", p)
            run_chain(crawl.crawl_joyfull, joyfull_site(), "2026-11-24")
            self.assertEqual(helpers.prod("joyfull", "527")["name"], "幻のコショウのチキン竜田")

    def test_second_run_skips_detail_pages_of_known_products(self):
        with TempData():
            site = joyfull_site()
            run_chain(crawl.crawl_joyfull, site, "2026-11-23")
            site.calls.clear()
            _, st = run_chain(crawl.crawl_joyfull, site, "2026-11-24")
            self.assertTrue(st["joyfull"]["list_ok"])
            for pid in ("502", "527", "602"):
                self.assertNotIn(JOYFULL + f"/menu/{pid}", site.calls)
            # 2回目は robots・一覧(newsは開始日が全件そろっているので呼ばれない)だけ
            self.assertLessEqual(len(site.calls), 3)

    def test_declared_count_mismatch_is_incomplete(self):
        with TempData():
            site = joyfull_site()
            site.set(JF_LIST, S.joyfull_list(JOYFULL_ITEMS).replace("￥939", "価格は店頭で"))
            _, st = run_chain(crawl.crawl_joyfull, site, "2026-11-23")
            self.assertFalse(st["joyfull"]["list_ok"])
            self.assertEqual(ids("joyfull"), ["502", "602"])  # 取れた分は記録される

    def test_list_structure_change_is_list_failed(self):
        with TempData():
            site = joyfull_site()
            site.set(JF_LIST, "<html>変わった</html>")
            _, st = run_chain(crawl.crawl_joyfull, site, "2026-11-23")
            self.assertFalse(st["joyfull"]["list_ok"])
            self.assertEqual(ids("joyfull"), [])

    def test_blocked_stops_without_workaround(self):
        with TempData():
            site = joyfull_site()
            site.set(JOYFULL + "/menu/527", BlockedError("HTTP 403"))
            _, st = run_chain(crawl.crawl_joyfull, site, "2026-11-23")
            self.assertTrue(st["joyfull"]["blocked"])
            self.assertFalse(st["joyfull"]["list_ok"])

    def test_robots_disallow_skips(self):
        with TempData():
            site = joyfull_site()
            site.set(JOYFULL + "/robots.txt", "User-agent: *\nDisallow: /menu\n")
            run_chain(crawl.crawl_joyfull, site, "2026-11-23")
            self.assertEqual(ids("joyfull"), [])
            self.assertNotIn(JF_LIST, site.calls)

    def test_burst_guard_holds_a_restructure_but_allows_a_real_fair(self):
        with TempData():
            run_chain(crawl.crawl_joyfull, joyfull_site(), "2026-11-23")  # baseline: 3件
            # 本物の新フェア: 新規10件(閾値20以下)は記録される
            ten = [(700 + i, f"新作テスト{i}", 500, 550) for i in range(10)]
            fairs = {**JOYFULL_FAIRS, **{700 + i: "新フェア" for i in range(10)}}
            _, st = run_chain(crawl.crawl_joyfull, joyfull_site(items=JOYFULL_ITEMS + ten, fairs=fairs), "2026-11-24")
            self.assertEqual(st["joyfull"]["new_products"], 10)
            # 全件のIDが変わる構造変更(新規25件 > 閾値20)は保留
            many = [(800 + i, f"別テスト{i}", 500, 550) for i in range(25)]
            many_fairs = {800 + i: "別フェア" for i in range(25)}
            pend, st = run_chain(crawl.crawl_joyfull, joyfull_site(items=many, fairs=many_fairs), "2026-11-25")
            self.assertEqual(st["joyfull"]["new_products"], 0)
            self.assertFalse(st["joyfull"]["list_ok"])
            self.assertEqual(pend["joyfull"]["_suspected_restructure"]["threshold"], 20)


class TestTouchSeen(unittest.TestCase):
    def new_prod(self, **kw):
        p = crawl.base_product("dennys", "1", "テスト", "2026-11-03T07:00:00+09:00", "2026-11-03")
        crawl.set_initial_price(p, 500, None, "2026-11-03")
        p.update(kw)
        return p

    def test_price_history_only_on_change(self):
        p = self.new_prod()
        crawl.touch_seen(p, 500, None, "2026-11-04")
        self.assertEqual(len(p["price_history"]), 1)
        crawl.touch_seen(p, 550, None, "2026-11-05")
        self.assertEqual(p["price_history"][-1], {"date": "2026-11-05", "price": 550})
        crawl.touch_seen(p, None, None, "2026-11-06")
        self.assertEqual(p["price"], 550)

    def test_missing_counts_reset_when_back(self):
        p = self.new_prod(missed_runs=1, last_miss_date="2026-11-04")
        crawl.touch_seen(p, 500, None, "2026-11-05")
        self.assertEqual((p["missed_runs"], p["last_miss_date"]), (0, None))


class TestRatioGuard(unittest.TestCase):
    def test_sudden_drop_is_ignored_for_two_days_then_accepted(self):
        with TempData():
            self.assertTrue(crawl.ratio_ok("dennys", 20, "2026-11-01"))
            self.assertFalse(crawl.ratio_ok("dennys", 5, "2026-11-02"))
            self.assertFalse(crawl.ratio_ok("dennys", 5, "2026-11-02"))
            self.assertFalse(crawl.ratio_ok("dennys", 5, "2026-11-03"))
            self.assertTrue(crawl.ratio_ok("dennys", 5, "2026-11-04"))

    def test_small_lists_are_exempt(self):
        with TempData():
            self.assertTrue(crawl.ratio_ok("jonathan", 6, "2026-11-01"))
            self.assertTrue(crawl.ratio_ok("jonathan", 2, "2026-11-02"))


class TestHealthAndSummary(unittest.TestCase):
    def test_streak_counts_days_and_resets(self):
        pending = {}
        bad = {"dennys": {**crawl.new_stats(), "list_ok": False}}
        self.assertEqual(crawl.update_health(pending, bad, "2026-11-01"), {"dennys": 1})
        self.assertEqual(crawl.update_health(pending, bad, "2026-11-01"), {"dennys": 1})
        self.assertEqual(crawl.update_health(pending, bad, "2026-11-02"), {"dennys": 2})
        ok = {"dennys": {**crawl.new_stats(), "list_ok": True}}
        crawl.update_health(pending, ok, "2026-11-03")
        self.assertNotIn("_health", pending)

    def test_run_summary_written(self):
        with TempData() as base:
            run_chain(crawl.crawl_dennys, dennys_site(), "2026-11-23")
            stats = {}
            crawl.crawl_dennys(dennys_site(), {}, stats, "2026-11-23")
            crawl.save_run_summary(stats, {})
            data = json.loads((base / "run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(data["new"]["dennys"], 0)
            self.assertEqual(data["list_failed"], [])

    def test_main_rejects_unknown_chain(self):
        self.assertEqual(crawl.main(["starbucks"]), 2)
        self.assertEqual(sorted(crawl.CRAWLERS), ["bigboy", "cocos", "dennys", "jonathan", "joyfull", "steakdon"])

    def test_one_chain_exception_does_not_stop_the_other(self):
        def boom(getter, pending, stats, today=None):
            raise RuntimeError("boom")

        with TempData():
            site = dennys_site()
            site.counts = {}
            with mock.patch.object(crawl, "Getter", return_value=site), \
                 mock.patch.dict(crawl.CRAWLERS, {"jonathan": boom}):
                import io, contextlib
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    crawl.main([])
            summary = json.loads(crawl.RUN_SUMMARY.read_text(encoding="utf-8"))
            self.assertEqual(summary["errors"], ["jonathan"])
            self.assertEqual(len(ids("dennys")), 5)


if __name__ == "__main__":
    unittest.main()


class TestSteakdonCrawl(unittest.TestCase):
    def test_first_run_records_all_items_with_facts_only(self):
        with TempData():
            site = steakdon_site()
            _, st = run_chain(crawl.crawl_steakdon, site, "2026-11-23")
            self.assertTrue(st["steakdon"]["list_ok"])
            self.assertEqual(ids("steakdon"), ["1635", "1636", "1638"])
            p = helpers.prod("steakdon", "1636")
            self.assertEqual((p["name"], p["price"], p["price_max"], p["price_excl_tax"]),
                             ("黒毛和牛ステーキ", 3278, 4818, 2980))
            self.assertEqual(p["price_variants"], [
                {"label": "100g", "price": 3278}, {"label": "150g", "price": 3938}, {"label": "200g", "price": 4818}])
            self.assertEqual(p["fair"], "フェアメニュー")
            self.assertEqual(p["official_url"], SD + "/fmenu_detail.html?fmenu_item_id=1636")
            self.assertEqual(p["stores_note"], "※店舗限定")
            self.assertEqual(p["price_history"], [{"date": "2026-11-23", "price": 3278, "price_max": 4818}])
            single = helpers.prod("steakdon", "1638")
            self.assertEqual((single["price"], single["price_max"], single["price_variants"]), (429, None, None))
            self.assertIsNone(single["stores_note"])

    def test_unreadable_price_run_does_not_end_the_product(self):
        with TempData():
            run_chain(crawl.crawl_steakdon, steakdon_site(), "2026-11-23")
            bad = [("1636", "黒毛和牛ステーキ", "時価")] + list(S.STEAKDON_ITEMS[1:])
            run_chain(crawl.crawl_steakdon, steakdon_site(items=bad), "2026-11-24")
            run_chain(crawl.crawl_steakdon, steakdon_site(items=bad), "2026-11-25")
            p = helpers.prod("steakdon", "1636")
            self.assertEqual(p["status"], "on_sale")
            self.assertIsNone(p.get("ended_observed_at"))

    def test_no_description_or_image_keys_are_saved(self):
        with TempData():
            run_chain(crawl.crawl_steakdon, steakdon_site(), "2026-11-23")
            for p in crawl.load_chain_products("steakdon"):
                blob = json.dumps(p, ensure_ascii=False)
                for k in ("image", "photo", "description", "lead", "nutrition", "allergen"):
                    self.assertNotIn(k, blob)

    def test_requests_within_limit_and_detail_pages_are_not_fetched(self):
        with TempData():
            site = steakdon_site()
            run_chain(crawl.crawl_steakdon, site, "2026-11-23")
            self.assertLessEqual(len(site.calls), crawl.CONFIG["max_requests_per_run"]["steakdon"])
            self.assertEqual(len(site.calls), 3)  # robots + カテゴリページ + ニュース一覧
            self.assertFalse(any("fmenu_detail" in u for u in site.calls))
            self.assertFalse(any("campaign_fair" in u for u in site.calls))

    def test_launch_date_from_news_by_product_name(self):
        with TempData():
            news = [("2026年09月09日", 2001, "「モンブランパフェ」9月17日（木）より販売開始")]
            run_chain(crawl.crawl_steakdon, steakdon_site(news=news), "2026-11-23")
            p = helpers.prod("steakdon", "1638")
            self.assertEqual((p["launch_date"], p["launch_date_source"]), ("2026-09-17", "official_news"))
            self.assertEqual(p["news_url"], SD + "/news_detail.html?num=2001")
            # 見出しに商品名の出ないフェア記事(マロンスイーツフェア)では結びつかない
            self.assertIsNone(helpers.prod("steakdon", "1635")["launch_date"])

    def test_fair_name_only_news_leaves_recording_start(self):
        with TempData():
            run_chain(crawl.crawl_steakdon, steakdon_site(), "2026-11-23")
            self.assertTrue(all(p["launch_date"] is None for p in crawl.load_chain_products("steakdon")))

    def test_news_failure_does_not_stop_recording(self):
        with TempData():
            site = steakdon_site()
            site.set(SD_NEWS, RuntimeError("timeout"))
            _, st = run_chain(crawl.crawl_steakdon, site, "2026-11-23")
            self.assertEqual(len(ids("steakdon")), 3)
            self.assertTrue(st["steakdon"]["list_ok"])

    def test_ended_after_two_misses_on_different_days(self):
        with TempData():
            run_chain(crawl.crawl_steakdon, steakdon_site(), "2026-11-23")
            fewer = steakdon_site(items=S.STEAKDON_ITEMS[:2])
            run_chain(crawl.crawl_steakdon, fewer, "2026-11-24")
            p = helpers.prod("steakdon", "1638")
            self.assertEqual((p["status"], p["missed_runs"]), ("on_sale", 1))
            run_chain(crawl.crawl_steakdon, fewer, "2026-11-25")
            p = helpers.prod("steakdon", "1638")
            self.assertEqual((p["status"], p["ended_observed_at"]), ("ended", "2026-11-25"))

    def test_price_change_is_recorded(self):
        with TempData():
            run_chain(crawl.crawl_steakdon, steakdon_site(), "2026-11-23")
            changed = [("1638", "モンブランパフェ", "450円（税込495円）") if i[0] == "1638" else i
                       for i in S.STEAKDON_ITEMS]
            run_chain(crawl.crawl_steakdon, steakdon_site(items=changed), "2026-11-24")
            p = helpers.prod("steakdon", "1638")
            self.assertEqual(p["price"], 495)
            self.assertEqual(p["price_history"][-1], {"date": "2026-11-24", "price": 495})

    def test_list_without_price_is_incomplete_and_nothing_ends(self):
        with TempData():
            run_chain(crawl.crawl_steakdon, steakdon_site(), "2026-11-23")
            broken = steakdon_site(items=[("3000", "価格が画像だけ", "画像のみ")])
            for d in ("2026-11-24", "2026-11-25", "2026-11-26"):
                _, st = run_chain(crawl.crawl_steakdon, broken, d)
                self.assertFalse(st["steakdon"]["list_ok"])
            self.assertTrue(all(p["status"] == "on_sale" for p in crawl.load_chain_products("steakdon")))

    def test_structure_change_is_list_failed(self):
        with TempData():
            site = steakdon_site()
            site.set(SD_LIST, "<html>構造が変わった</html>")
            _, st = run_chain(crawl.crawl_steakdon, site, "2026-11-23")
            self.assertFalse(st["steakdon"]["list_ok"])
            self.assertEqual(ids("steakdon"), [])

    def test_blocked_stops_without_workaround(self):
        with TempData():
            site = steakdon_site()
            site.set(SD_LIST, BlockedError("HTTP 403"))
            _, st = run_chain(crawl.crawl_steakdon, site, "2026-11-23")
            self.assertTrue(st["steakdon"]["blocked"])
            self.assertFalse(st["steakdon"]["list_ok"])

    def test_robots_disallow_skips(self):
        with TempData():
            site = steakdon_site()
            site.set(SD + "/robots.txt", "User-agent: *\nDisallow: /fmenu_list.html\n")
            run_chain(crawl.crawl_steakdon, site, "2026-11-23")
            self.assertEqual(ids("steakdon"), [])
            self.assertNotIn(SD_LIST, site.calls)

    def test_burst_guard_holds_a_restructure(self):
        with TempData():
            run_chain(crawl.crawl_steakdon, steakdon_site(), "2026-11-23")  # baseline: 3件
            many = [(str(5000 + i), f"全く別の新作{i}", "500円（税込550円）") for i in range(20)]
            pend, st = run_chain(crawl.crawl_steakdon, steakdon_site(items=many), "2026-11-24")
            self.assertEqual(st["steakdon"]["new_products"], 0)
            self.assertFalse(st["steakdon"]["list_ok"])
            self.assertEqual(pend["steakdon"]["_suspected_restructure"]["threshold"], 15)


