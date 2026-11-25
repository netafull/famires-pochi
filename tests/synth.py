"""テスト用の最小フィクスチャ。公式ページの構造(クラス名・価格の書式・alt の並び)を再現した、必要最小限の写し。
ネットワークには触らない。"""

from __future__ import annotations

import json


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
BIGBOY_ITEMS = [
    ("牡蠣フライ＆大俵ハンバーグ", [("大俵150g", 1490, 1639), ("大俵200g", 1650, 1815), ("大俵250g", 1850, 2035)]),
    ("牡蠣フライ＆手ごねハンバーグ", [("", 1290, 1419)]),
    ("甘栗のモンブランファッジサンデー", [("", 590, 649)]),
]


def bigboy_grand_menu(items=BIGBOY_ITEMS, regular=("定番ハンバーグ", [("", 990, 1089)]), commented: str = "") -> str:
    """items: [(名前, [(サイズ, 税抜, 税込)])]。価格は ¥ 表記で、¥ と数字は別タグ(span.yen)に分かれる。
    期間限定メニュー欄のほかに定番の欄(大俵ハンバーグ)も置く(欄の外は読まないことの確認用)。"""
    def box(name, prices):
        ps = "".join(
            f'<p class="price"><span class="size">{sz}</span><span class="yen">¥</span>\n{ex:,}'
            f'<span class="tax_sum">（<span class="tax">税込</span><span class="yen">¥</span>\n{inc:,}）</span></p>'
            for sz, ex, inc in prices)
        return (f'<li class="box"><p class="pic"><img src="/x.jpg"></p>'
                f'<h4 class="name"><span class="main">{name}</span>'
                f'<span class="sub">タルタルソース＆濃厚ソース付</span></h4>{ps}</li>\n')
    limited = "".join(box(n, ps) for n, ps in items)
    reg = box(*regular) if regular else ""
    return f"""<html><body><div class="tab_contents">
<section id="219"><div class="tab_title_block"><h3 class="tab_title">期間限定メニュー</h3></div>
<ul class="menu_block">
{limited}<!-- {commented} --></ul></section>
<section id="120"><div class="tab_title_block"><h3 class="tab_title">大俵ハンバーグ</h3></div>
<ul class="menu_block">
{reg}</ul></section>
</div></body></html>"""


def bigboy_fair_list(links=(("/news/fair/6555.html",
                              "【フェア情報】「甘栗のモンブランファッジサンデー」、10月20日（火）より販売！"),)) -> str:
    """links: [(記事のパス, 見出し)]"""
    lis = "".join(
        f'<li class="post"><p class="item_detail_pic"><img src="/x.jpg"></p>'
        f'<div class="post_inner"><p class="item">{t}</p>'
        f'<p class="item_detail"><p>リード文</p></p>'
        f'<div class="to_link"><a href="{p}" class="btn"><span class="label">詳細はこちら</span></a></div>'
        f'</div></li>\n' for p, t in links)
    return f'<html><body><ul class="news_block">\n{lis}</ul></body></html>'


def bigboy_news_article(date: str = "2026/10/14",
                        title: str = "【フェア情報】「甘栗のモンブランファッジサンデー」、10月20日（火）より販売！",
                        body: str = "「ビッグボーイ」では、10月20日（火）より「甘栗のモンブランファッジサンデー」を販売します。") -> str:
    return (f'<html><body><section id="section-news"><ul class="news_block"><li class="post">'
            f'<div class="post_inner"><p class="date">{date}</p>'
            f'<p class="post_icon icon_fair">フェア情報</p><p class="item">{title}</p></div>'
            f'<p class="item_detail"><p>{body}</p></p>'
            f'</li></ul></section></body></html>')
def joyfull_list(items=(), declared=None, commented: str = "") -> str:
    """items: [(数値ID, 名前, 税抜, 税込)]。公式の一覧(季節・期間限定)の最小の写し。"""
    if declared is None:
        declared = len(items)
    cards = ""
    for pid, name, ex, inc in items:
        cards += f"""<li class="mg-item">
          <a href="https://www.joyfull.co.jp/menu/{pid}" class="menu-card span-4 hover-scale-trigger">
            <div class="hover-scale-wrap">
              <img src="https://www.joyfull.co.jp/menu/{pid}/image" class="menu-thumb hover-scale-img" width="344" height="212" loading="lazy" alt="{name}">
            </div>
            <div class="menu-body">
              <h3 class="mg-title">{name}</h3>
              <p class="menu-meta">
                ￥{ex:,}
                <span class="inline-block">（<span class="small">税込</span>￥{inc:,}）</span>
              </p>
            </div>
          </a>
        </li>
"""
    return f"""<html><body><main>
<h2 class="sec-title">季節・期間限定</h2>
<span class="result-count">該当件数 <span class="count">{declared}</span>件</span>
<ul class="menu-grid grid-row-middle">
{cards}</ul>
<!-- {commented} -->
</main></body></html>"""


def joyfull_detail(fair: str | None, name: str) -> str:
    """商品ページのパンくずだけの最小の写し。fair が None ならフェアの要素が無い並び。"""
    names = ["ホーム", "メニュー", "季節・期間限定"] + ([fair] if fair else []) + [name]
    lis = "".join(
        f'<li class="bl-item" itemprop="itemListElement" itemscope itemtype="https://schema.org/ListItem">'
        f'<a href="https://www.joyfull.co.jp" itemprop="item"><span itemprop="name">{n}</span></a>'
        f'<meta itemprop="position" content="{i + 1}"></li>' for i, n in enumerate(names))
    return (f'<html><body><nav class="breadcrumb" aria-label="パンくず"><div class="container">'
            f'<ol class="breadcrumb-list" itemscope itemtype="https://schema.org/BreadcrumbList">{lis}</ol>'
            f'</div></nav><h1>{name}</h1></body></html>')


def joyfull_news(entries=()) -> str:
    """entries: [(数値ID, 日付 YYYY.MM.DD, 見出し)]。お知らせ(メニュー分類)の一覧の最小の写し。"""
    cards = ""
    for nid, d, title in entries:
        cards += f"""<a href="https://www.joyfull.co.jp/news/{nid}" class="menu-card span-4 hover-float" data-cat="menu">
          <div class="news-card-image"><img src="https://www.joyfull.co.jp/news/{nid}/image_thumb" class="menu-thumb" width="344" height="212" loading="lazy" alt="{title}"></div>
          <div class="news-body">
            <div class="news-meta">
              <span class="chip">メニュー</span>
              <span class="date">{d}</span>
            </div>
            <h3 class="news-title">{title}</h3>
          </div>
        </a>
"""
    return f'<html><body><main><div class="menu-grid">{cards}</div></main></body></html>'


# ステーキのどんのフェアメニュー一覧(2026-11-23)の一部。サイズ別の価格は <br> 区切りで1つの <p> に入る
STEAKDON_ITEMS = [
    ("1636", "黒毛和牛ステーキ",
     "100g　2,980円（税込3,278円）<br>\n150g　3,580円（税込3,938円）<br>\n200g　4,380円（税込4,818円）<br>※店舗限定"),
    ("1635", "ワイルドポークマウンテン２００ｇ", "1,380円（税込1,518円）"),
    ("1638", "モンブランパフェ", "390円（税込429円）"),
]


def steakdon_fair_list(items=STEAKDON_ITEMS, title: str = "フェアメニュー", extra: str = "") -> str:
    """items: [(商品ID, 名前, 価格ブロックHTML)]。extra は一覧の <ul> の中に入れる追加HTML(コメントの確認用)。"""
    lis = ""
    for iid, name, price_html in items:
        lis += (f'<li>\n<a href="fmenu_detail.html?fmenu_item_id={iid}">\n'
                f'<img src="/img/fmenu/{iid}_img1.jpg">\n'
                f'<div class="menu_list_border">\n<p class="menu_name">{name}</p>\n'
                f'<p class="menu_price">{price_html}</p>\n</div>\n</a>\n'
                f'<div class="menu_list_kcal">\n<p></p>\n</div>\n</li>\n')
    return f"""<html><body>
<div class="menu_list_subtitle">
<p>{title}</p>
</div>
<div class="menulist_list_inner">
<ul>
{lis}{extra}
</ul>
</div><!--/menulist_list_inner-->
</body></html>"""


def steakdon_news(entries=()) -> str:
    """entries: [(日付 2026年09月09日, num, 見出しHTML)]"""
    rows = ""
    for d, num, title in entries:
        rows += (f'<tr>\n<td class="news_date">{d}</td>\n'
                 f'<td><a href="news_detail.html?num={num}">{title}</a></td>\n</tr>\n')
    return f'<html><body><table class="news_table">{rows}</table></body></html>'


# ジョリーパスタのメニューJSON(jp_menu.json)の一部。パーサが読まないキー(説明・カロリー・NEW等)も
# 実物どおり入れてある(読まないことの確認用)。金額が無い商品・複数カテゴリに載る商品も含む
JOLLYPASTA_MENU = {
    "季節のおすすめ": [
        {"名称": "～スープパスタ～ 牡蠣と彩り野菜のクリームスープパスタ", "金額": "1,490円(税込1,639円)",
         "詳細URL": "/menu/season/r_soup_oystercream.html", "カテゴリ": "季節のおすすめ",
         "説明": "説明文は読まない", "カロリー": "999kcal", "NEW": "1"},
        {"名称": "牡蠣のアヒージョ", "金額": "790円(税込869円)",
         "詳細URL": "/menu/season/r_oyster_ajillo.html", "カテゴリ": "季節のおすすめ"},
        {"名称": "牡蠣とほうれん草のバターソテー", "金額": "690円(税込759円)",
         "詳細URL": "/menu/season/r_oyster_butter.html", "カテゴリ": "季節のおすすめ"},
        {"名称": "価格未定の季節商品", "金額": None,
         "詳細URL": "/menu/season/r_mitei.html", "カテゴリ": "季節のおすすめ"},
    ],
    "前菜": [
        {"名称": "牡蠣のアヒージョ", "金額": "790円(税込869円)",
         "詳細URL": "/menu/season/r_oyster_ajillo.html", "カテゴリ": "前菜"},
        {"名称": "定番の前菜", "金額": "490円(税込539円)",
         "詳細URL": "/menu/appetizer/a_teiban.html", "カテゴリ": "前菜"},
    ],
    "ドルチェ": [
        {"名称": "焼きリンゴとバニラアイスのパイ", "金額": "590円(税込649円)",
         "詳細URL": "/menu/dolce/d_applepie.html", "カテゴリ": "ドルチェ"},
    ],
}


def jollypasta_menu_json(menu=JOLLYPASTA_MENU) -> str:
    return json.dumps(menu, ensure_ascii=False)


def jollypasta_news_index(entries=()) -> str:
    """entries: [(日付 2026.11.24, href, 分類, 見出し)]。実物どおり属性は複数行に分かれる"""
    lis = ""
    for d, href, cat, title in entries:
        lis += (f'<li class="news_list_item" data-href="{href}"\n'
                f'        data-date="{d}" data-category="{cat}"\n'
                f'        data-title="{title}">\n'
                f'    <a href="{href}"><span class="news_date">{d}</span></a>\n</li>\n')
    return f'<html><body><div class="news_list"><ul>\n{lis}</ul></div></body></html>'


def jollypasta_news_article(date: str = "2026.11.24",
                            title: str = "12月1日(火)「窯焼きチーズパスタフェア」が始まります！",
                            body: str = "") -> str:
    """記事ページ。body は news_detail_txt の中身(★行の商品リスト等)"""
    return f"""<html><body>
<div class="top_news_date">{date}</div>
<div class="top_news_title">{title}</div>
<div class="news_detail_txt" style="text-align: left;">
<p>{body}</p>
<div class="submenu_button">
<div class="btn_m"><a href="/info/"><span>ニュース一覧に戻る</span></a></div>
</div>
</div>
</body></html>"""
