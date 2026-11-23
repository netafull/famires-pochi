"""テスト用の最小フィクスチャ。公式ページの構造(クラス名・価格の書式・alt の並び)を再現した、必要最小限の写し。
ネットワークには触らない。"""

from __future__ import annotations


def dennys_menu(fairs=(("/menu/collaboration17/", "飯田商店監修「味噌らぁ麺」"), ("/menu/oimo/", "蜜いもデザート"))) -> str:
    lis = "".join(
        f'<li><a href="{p}" title="{t}"><div class="fairImg"><img src="/x.jpg" alt="{t}"></div>'
        f'<p class="txt">{t}</p></a></li>' for p, t in fairs)
    return f"""<html><body><article id="menuTop">
<section class="menuTopCategory" id="fair"><ul class="fairArea center">{lis}</ul></section>
<section id="grand"><ul class="bnrArea"><li><a href="/menu/okonomi/" title="おこのみチョイス">定番</a></li></ul></section>
</article></body></html>"""


def dennys_fair(title: str, items=(), sets=(), commented: str = "") -> str:
    """items: [(名前HTML, 税抜, 税込, 商品ページのパス or None)]、sets: [(名前, 税抜, 税込)]。"""
    boxes = ""
    for name, ex, inc, link in items:
        more = f'<p class="more"><a href="{link}">MORE</a></p>' if link else ""
        boxes += (f'<div class="txtBox"><p class="menuTitle">{name}</p>'
                  f'<p class="price">{ex:,}円<span>（税込{inc:,}円）</span></p>{more}</div>\n')
    dls = "".join(f"<dl><dt>{n}</dt><dd>{ex:,}円<span>（税込{inc:,}円）</span></dd></dl>" for n, ex, inc in sets)
    return f"""<html><body><h1 class="label">{title}</h1>
<a href="/menu/half-parfait/oimo/"><img alt="まっぷたつ？パフェ"></a>
{boxes}{dls}
<!-- {commented} -->
</body></html>"""


def dennys_news(entries=()) -> str:
    """entries: [(日付 2026/10/14, 見出し, リード文)]"""
    out = ""
    for d, title, lead in entries:
        out += (f'<dl class="newsbox"><dt class="newsyear">{d}</dt>'
                f'<dd class="newstit"><a target="_blank" href="/pdf/x.pdf"><strong>{title}</strong></a></dd>'
                f'<dd class="newstxt">{lead}</dd></dl><hr>\n')
    return f'<html><body><div id="news">{out}</div></body></html>'


def jonathan_top(slugs=("collab", "fair", "dessert", "drink_bar")) -> str:
    lis = "".join(
        f'<li class="swiper-slide"><a href="/jonathan/menu/{s}/index.html" class="slide-link">'
        f'<h3 class="slide-title">{s}のタイトル</h3><p class="slide-text"><img alt="{s}"></p></a></li>'
        for s in slugs)
    return f'<html><body><main><ul class="swiper-wrapper">{lis}</ul></main></body></html>'


# 公式の alt(2026-11-23)の一部。説明文の断片と商品が1つの文字列に入っている
JONATHAN_FAIR_ALT = (
    "Jonathan's Autumn Fair 秋のよくばりマルシェ。お出汁をかけて出汁茶漬けに！2度おいしい！かぼちゃサラダ アーモンド。"
    "炙り鮭はらすといくらの出汁茶漬け＋おつまみカキフライ膳 1,699円（税込1,869円）。"
    "炙り鮭はらすといくらの出汁茶漬け膳 1,399円（税込1,539円）。"
    "脂ののったとろサーモンに、いくらを散らした三色丼です。温泉卵と一緒にどうぞ。"
    "とろサーモン＆いくら丼（みそ汁・惣菜つき） 1,699円（税込1,869円）。"
    "オーストラリア産アンガス牛100%ステーキハンバーグ。スープには淡路島産玉ねぎ使用。"
    "アンガスビーフ100% 贅沢きのこのオニオンスープハンバーグ 1,349円（税込1,484円）。"
    "Side Menu サイドメニュー。かぼちゃとキャロットラペのサラダ 349円（税込384円）。"
    "Sweets スイーツ 八天堂。八天堂とろけるカスタードくりーむのミニパルフェ（早生みかん） 499円（税込549円）。"
    "ドリンクバーセット 269円（税込296円）。"
)


def jonathan_page(title: str, alts=(JONATHAN_FAIR_ALT,)) -> str:
    imgs = "".join(f'<img src="/a.png" alt="{a}">' for a in alts)
    return f'<html><body><main><h1>{title}</h1>{imgs}<img alt="">\n<!-- <img alt="コメント内 999円（税込1,099円）。"> --></main></body></html>'


def alt(*pairs) -> str:
    """alt を作る: [(名前, 税抜, 税込)] → 「名前 1,000円（税込1,100円）。」の連結"""
    return "".join(f"{n} {ex:,}円（税込{inc:,}円）。" for n, ex, inc in pairs)


def cocos_fair_page(fairs=(("ココスの期間限定スイーツ",
                            [("勤労感謝の芋栗かぼちゃクレープ", 590, 649,
                              "/menu/fair/limited_sweets/roasted_sweet_potato_crepe2611.html")]),
                           ("マロンフェア",
                            [("マロンとチョコのパフェ", 1290, 1419,
                              "/menu/fair/marron2610/shinemuscat_parfait2609.html"),
                             ("マロンのもちもちクレープ", 590, 649,
                              "/menu/fair/marron2610/shinemuscat_crepe2609.html")])), commented: str = "") -> str:
    """fairs: [(フェア名, [(名前, 税抜, 税込, 詳細ページのパス or None)])]。価格は ¥ 表記(税込側は「¥ 649」)。"""
    sections = ""
    for title, items in fairs:
        lis = ""
        for name, ex, inc, link in items:
            lis += (f'<li><a href="{link or ""}">'
                    f'<figure><img data-src="/x.jpg" alt=""></figure>'
                    f'<div class="menu_info">'
                    f'<div class="label"><span class="new">NEW</span><span class="limited">期間限定</span></div>'
                    f'<div class="name">{name}</div>'
                    f'<div class="price"><span class="tax_ex"><span>¥</span>{ex:,}</span>'
                    f'<span class="tax_in">(<span>税込</span>¥ {inc:,})</span></div>'
                    f'</div></a></li>\n')
        sections += f'<h2>{title}</h2>\n<ul class="img_link type_menu_list">\n{lis}</ul>\n'
    return f"""<html><body><section class="menu_wrap"><div class="base_entry">
<p>販売時間は10:00～ラストオーダーです。<br>※一部店舗で取扱商品、販売時間帯、価格が異なる場合がございます。</p>
{sections}<h2>ココス公式アプリCoco's App</h2>
<!-- {commented} -->
</div></section></body></html>"""


def cocos_news(entries=()) -> str:
    """entries: [(記事のパス, 掲載日 YYYY-MM-DD, 見出し)]"""
    lis = ""
    for path, d, title in entries:
        y, m, dd = d.split("-")
        lis += (f'<li><a href="{path}" >\n'
                f'      <span class="label menu">メニュー</span>\n'
                f'      <span class="date" data-postdate="{d}">{y}/{m}/{dd}</span>\n'
                f'      <p>{title}</p>\n    </a></li>\n')
    return f'<html><body><div class="tab_cont"><ul>\n{lis}</ul></div></body></html>'
