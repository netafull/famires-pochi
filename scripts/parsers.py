#!/usr/bin/env python3
"""デニーズ・ジョナサン・ココス・ビッグボーイ・ジョイフル・ステーキのどん・ジョリーパスタの公式ページのパーサ。

ネットワークには触らない純粋関数だけを置く(合成フィクスチャでテストする)。
公式のHTML/JSONの構造が変わったら、まずここが壊れる。壊れ方は2通りに分ける:
  ・構造が想定と違う(キーが無い・型が違う) -> ValueError。呼び出し側は「構造変更の疑い」として
    list_failed 扱いにし、終了判定をしない。
  ・構造は正しいが該当の商品が0件 -> 空のリストを返す。

規約: 説明文・画像の複製を避けるため、ここで取り出すのは事実(フェア名・商品名・価格・日付)だけ。
説明文・画像のURLは、読み取りもしない。
"""

from __future__ import annotations

import datetime
import hashlib
import html as html_lib
import json
import re
import unicodedata

# ---------------------------------------------------------------------------
# 共通
# ---------------------------------------------------------------------------


def clean_text(s: str | None) -> str:
    """HTMLタグ(<br>は空白扱い)を除き、実体参照を戻し、空白を整える。"""
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_lib.unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t\r\n　]+", " ", s)
    return s.strip()


def strip_html(s: str | None) -> str:
    """発売日の照合用に、記事全体を平文にする(スクリプト・スタイルも除く)。保存はしない。"""
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    return clean_text(s)


_NORM_DROP = re.compile(r"[\s「」『』\"“”'’・＜＞<>()（）【】\[\]～〜~!！?？\-ー―—:：/／,、。.&＆®™©*＊★☆]+")


def normalize_name(s: str | None) -> str:
    """商品名の照合用: NFKC・実体参照・空白と記号を除き、小文字にする。"""
    s = html_lib.unescape(s or "")
    s = unicodedata.normalize("NFKC", s)
    return _NORM_DROP.sub("", s).lower()


def to_float(v) -> float | None:
    """「401」「21.0」「-」→数値/None。数値はそのまま。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = unicodedata.normalize("NFKC", str(v)).strip().replace(",", "")
    if t in ("", "-", "ー", "−"):
        return None
    m = re.match(r"^-?\d+(?:\.\d+)?", t)
    return float(m.group(0)) if m else None


def parse_yen(text: str | None) -> int | None:
    """「￥1,380」「¥ 560」「680円」→ 整数。見つからなければ None。"""
    t = unicodedata.normalize("NFKC", text or "")
    m = re.search(r"(?:¥|￥)\s*([\d,]+)|([\d,]+)\s*円", t)
    if not m:
        return None
    return int((m.group(1) or m.group(2)).replace(",", ""))


def _round(v: float | None, nd: int) -> float | int | None:
    if v is None:
        return None
    r = round(v, nd)
    return int(r) if nd == 0 else r


def stable_id(prefix: str, name: str) -> str:
    """URLやIDを持たない商品の、名前から作る安定したID(例 sx-1a2b3c4d5e)。"""
    return f"{prefix}-{hashlib.sha1(normalize_name(name).encode('utf-8')).hexdigest()[:10]}"


# ---- 発売日(見出し・本文の「11月2日（月）より」) ------------------------------

_DATE_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")
_LAUNCH_WORD_RE = re.compile(r"より|から|発売|販売|登場|スタート|開始|解禁")


def launch_dates_in_text(text: str | None, ref: datetime.date) -> list[tuple[int, str]]:
    """見出し・本文の中の「M月D日（曜）より/から/発売/販売/登場/スタート」を [(位置, YYYY-MM-DD)] で返す。
    位置は NFKC 化した文字列の中の位置。年は ref の日付から補い、ref から半年以上ずれる年になる場合は前後の年に寄せる。
    「M月D日」の後ろ(20文字以内)に発売の語が続くものだけ採用する(「12月25日まで」「予約は11月1日まで」のような
    終わりの日付を取り違えない)。"""
    t = unicodedata.normalize("NFKC", text or "")
    out = []
    for m in _DATE_RE.finditer(t):
        tail = t[m.end(): m.end() + 20]
        end_pos = re.search(r"まで", tail)
        word = _LAUNCH_WORD_RE.search(tail)
        if not word or (end_pos and end_pos.start() < word.start()):
            continue
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            cand = datetime.date(ref.year, mo, d)
        except ValueError:
            continue
        delta = (cand - ref).days
        if delta > 180:
            cand = datetime.date(ref.year - 1, mo, d)
        elif delta < -180:
            cand = datetime.date(ref.year + 1, mo, d)
        out.append((m.start(), cand.isoformat()))
    return out


def launch_date_from_text(text: str | None, ref: datetime.date) -> str | None:
    """見出し・本文の中の最初の発売日(launch_dates_in_text 参照)。無ければ None。"""
    found = launch_dates_in_text(text, ref)
    return found[0][1] if found else None



# ---------------------------------------------------------------------------
# 共通: 価格の表記「1,790円（税込1,969円）」
# ---------------------------------------------------------------------------

_PRICE_PAIR_RE = re.compile(r"(＋|\+)?\s*([\d,]+)\s*円\s*[（(]\s*税込\s*([\d,]+)\s*円\s*[）)]")


def _strip_comments(html: str) -> str:
    """HTMLコメント(公式は旧バッジなどをコメントで無効化している)を除く。コメント内の商品・価格は読まない。"""
    return re.sub(r"<!--.*?-->", "", html or "", flags=re.S)


def parse_price_pair(text: str | None) -> tuple[int, int] | None:
    """「1,790円（税込1,969円）」→ (税抜, 税込)。「＋」付きの追加料金は None。見つからなければ None。"""
    t = unicodedata.normalize("NFKC", clean_text(text))
    m = _PRICE_PAIR_RE.search(t)
    if not m or m.group(1):
        return None
    return int(m.group(2).replace(",", "")), int(m.group(3).replace(",", ""))


# ---------------------------------------------------------------------------
# デニーズ (www.dennys.jp)
# ---------------------------------------------------------------------------

DENNYS_BASE = "https://www.dennys.jp"
DENNYS_MENU_PATH = "/menu/"
DENNYS_NEWS_PATH = "/news/"


def parse_dennys_fair_links(html: str) -> list[dict]:
    """/menu/ の「FAIR」欄(ul.fairArea)から、フェアページへのリンク [{path, title}] を返す。
    ページ名(/menu/oimo/ など)は固定でないので毎回ここから辿る。欄そのものが無ければ ValueError(構造変更の疑い)。"""
    h = _strip_comments(html)
    m = re.search(r'<ul[^>]*class="[^"]*fairArea[^"]*"[^>]*>(.*?)</ul>', h, re.S)
    if not m:
        raise ValueError("デニーズ: /menu/ に FAIR 欄(fairArea)が見つからない")
    out, seen = [], set()
    for a in re.finditer(r'<a\s[^>]*href="(/menu/[^"#?]+/)"[^>]*>(.*?)</a>', m.group(1), re.S):
        path = a.group(1)
        if path in seen:
            continue
        seen.add(path)
        t = re.search(r'title="([^"]*)"', a.group(0))
        txt = re.search(r'<p class="txt">(.*?)</p>', a.group(2), re.S)
        out.append({"path": path, "title": clean_text(t.group(1) if t else (txt.group(1) if txt else ""))})
    return out


def _dennys_name(inner: str) -> str:
    inner = re.sub(r"<rt>.*?</rt>", "", inner, flags=re.S)  # ルビの読みがな
    inner = re.sub(r"<br\s*/?>", "", inner, flags=re.I)  # 折り返し用の<br>は空白にしない(名前がセット欄とそろう)
    return clean_text(inner)


def parse_dennys_fair_page(html: str, fair_path: str) -> dict:
    """フェアページから {title, items:[{pid, name, price, price_excl_tax, link}]}。
    商品は ①<p class="menuTitle"> + <p class="price"> の組、②セット欄の <dt>名前</dt><dd>価格</dd>。
    識別キーは、商品ページへのリンク(/menu/dessert/xxx/)があればそのパス、無ければフェアのパス＋正規化した商品名。
    ページ名(h1.label)が無ければ ValueError(構造変更の疑い)。価格が取れた商品が0件なら items は空(呼び出し側が「不完全」とする)。"""
    h = _strip_comments(html)
    t = re.search(r'<h1[^>]*class="[^"]*label[^"]*"[^>]*>(.*?)</h1>', h, re.S)
    if not t:
        raise ValueError("デニーズ: フェアページの題名(h1.label)が見つからない")
    fair_slug = fair_path.strip("/").split("/")[-1]
    pair_re = re.compile(r'<p class="menuTitle">(.*?)</p>\s*<p class="price">(.*?)</p>', re.S)
    dl_re = re.compile(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", re.S)
    marks = [(m.start(), m.end(), m.group(1), m.group(2), "t") for m in pair_re.finditer(h)]
    marks += [(m.start(), m.end(), m.group(1), m.group(2), "d") for m in dl_re.finditer(h)]
    marks.sort()
    items, seen = [], set()
    for i, (s, e, name_html, price_html, kind) in enumerate(marks):
        pp = parse_price_pair(price_html)
        name = _dennys_name(name_html)
        if not pp or not name:
            continue
        link = None
        if kind == "t":
            nxt = marks[i + 1][0] if i + 1 < len(marks) else len(h)
            for a in re.finditer(r'href="(/menu/[^"#?]+/[^"#?]+/?)"', h[e:nxt]):
                if not a.group(1).startswith(fair_path):
                    link = a.group(1) if a.group(1).endswith("/") else a.group(1) + "/"
                    break
        pid = (re.sub(r"[^A-Za-z0-9_\-]+", "-", link.strip("/")[len("menu/"):]).strip("-") if link
               else stable_id(fair_slug, name))
        if pid in seen:
            continue
        seen.add(pid)
        items.append({"pid": pid, "name": name, "price_excl_tax": pp[0], "price": pp[1], "link": link})
    return {"title": clean_text(t.group(1)), "items": items}


def parse_dennys_news(html: str) -> list[dict]:
    """/news/(HTML)の一覧から [{date: YYYY-MM-DD, title, text, url}]。title は見出し、text はリード文。
    PDF の本文は読まない。構造が違えば空のリスト(発売日なしで続行)。"""
    h = _strip_comments(html)
    out = []
    pat = r'<dt class="newsyear">(.*?)</dt>\s*<dd class="newstit">(.*?)</dd>(?:\s*<dd class="newstxt">(.*?)</dd>)?'
    for m in re.finditer(pat, h, re.S):
        d = re.fullmatch(r"\s*(\d{4})/(\d{1,2})/(\d{1,2})\s*", clean_text(m.group(1)))
        if not d:
            continue
        out.append({"date": f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}",
                    "title": clean_text(m.group(2)), "text": clean_text(m.group(3) or ""),
                    "url": DENNYS_BASE + DENNYS_NEWS_PATH})
    return out


# ---------------------------------------------------------------------------
# ジョナサン (www.skylark.co.jp/jonathan/)
# ---------------------------------------------------------------------------

JONATHAN_BASE = "https://www.skylark.co.jp"
JONATHAN_MENU_PATH = "/jonathan/menu/"
JONATHAN_FAIR_PATH = "/jonathan/menu/fair/index.html"
JONATHAN_NAME_MAX = 80
JONATHAN_NAME_MIN = 3


def parse_jonathan_menu_links(html: str) -> list[dict]:
    """メニュートップ(/jonathan/menu/)のおすすめスライドから [{slug, path, title}]。
    リンクが1つも無ければ ValueError(構造変更の疑い)。"""
    h = _strip_comments(html)
    out, seen = [], set()
    pat = r'<a\s[^>]*href="(/jonathan/menu/([A-Za-z0-9_\-]+)/index\.html)"[^>]*>(.*?)</a>'
    for m in re.finditer(pat, h, re.S):
        path, slug = m.group(1), m.group(2)
        if path in seen:
            continue
        seen.add(path)
        t = re.search(r"<h3[^>]*>(.*?)</h3>", m.group(3), re.S)
        out.append({"slug": slug, "path": path, "title": clean_text(t.group(1)) if t else ""})
    if not out:
        raise ValueError("ジョナサン: メニュートップにおすすめページのリンクが見つからない")
    return out


def parse_jonathan_alt(alt: str | None) -> list[dict]:
    """img の alt 1つ分から [{name, price, price_excl_tax}]。

    alt は「商品名 1,699円（税込1,869円）。…説明…。商品名 1,399円（税込1,539円）。」のように、複数の商品と
    説明の断片が1つの文字列に入っている。価格(「N円（税込M円）」)ごとに、その直前の区切り
    (「。」「、」「：」・直前の価格の終わり。括弧の中の区切りは無視)から価格までを商品名とする。
    ・「＋180円」「各＋50円」のような追加料金(トッピング)は商品にしない
    ・名前が短すぎる(3文字未満)・長すぎる(80文字超。説明の断片)ものは捨てる"""
    s = unicodedata.normalize("NFC", alt or "")
    depth, d = [], 0  # 各位置の直前までの括弧の深さ
    for ch in s:
        depth.append(d)
        if ch in "（(":
            d += 1
        elif ch in "）)" and d > 0:
            d -= 1
    delims = [i for i, ch in enumerate(s) if ch in "。、：\n" and depth[i] == 0]
    out, prev_end = [], 0
    for m in _PRICE_PAIR_RE.finditer(s):
        start = m.start()
        seg_start = max([prev_end] + [i + 1 for i in delims if i < start])
        prev_end = m.end()
        if m.group(1):  # ＋付きの追加料金
            continue
        name = re.sub(r"\s+", " ", s[seg_start:start]).strip(" 　、。")
        name = re.sub(r"^各\s*", "", name)
        if not (JONATHAN_NAME_MIN <= len(name) <= JONATHAN_NAME_MAX):
            continue
        out.append({"name": name, "price_excl_tax": int(m.group(2).replace(",", "")),
                    "price": int(m.group(3).replace(",", ""))})
    return out


def parse_jonathan_fair_page(html: str, page_slug: str) -> dict:
    """フェアページから {title, items:[{pid, name, price, price_excl_tax}]}。商品は img の alt から取る。
    識別キーは、フェアのパス(fair/dessert 等)＋正規化した商品名。h1 が無ければ ValueError。"""
    h = _strip_comments(html)
    t = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
    if not t:
        raise ValueError("ジョナサン: フェアページの題名(h1)が見つからない")
    items, seen = [], set()
    for m in re.finditer(r'<img\b[^>]*?\balt="([^"]*)"', h, re.S):
        alt = html_lib.unescape(m.group(1))
        if "円" not in alt:
            continue
        for it in parse_jonathan_alt(alt):
            pid = stable_id(page_slug, it["name"])
            if pid in seen:
                continue
            seen.add(pid)
            items.append({"pid": pid, **it})
    return {"title": clean_text(t.group(1)), "items": items}


# ---------------------------------------------------------------------------
# ココス (www.cocos-jpn.co.jp)
# ---------------------------------------------------------------------------

COCOS_BASE = "https://www.cocos-jpn.co.jp"
COCOS_FAIR_PATH = "/menu/fair/"

_PRICE_YEN_PAIR_RE = re.compile(r"¥\s*([\d,]+)\s*[（(]\s*税込\s*¥\s*([\d,]+)\s*[）)]")


def parse_price_yen_pair(text: str | None) -> tuple[int, int] | None:
    """「¥590(税込¥ 649)」→ (税抜, 税込)。ココスの ¥ 表記専用(共通の parse_price_pair は円表記用)。
    税込側は「¥ 649」のように ¥ の後ろに空白が入ることがある。見つからなければ None。"""
    t = unicodedata.normalize("NFKC", clean_text(text))
    m = _PRICE_YEN_PAIR_RE.search(t)
    if not m:
        return None
    return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))


def _cocos_pid(link: str | None, name: str) -> str:
    """識別キー: 商品詳細ページ(/menu/fair/<フェアのディレクトリ>/<商品>.html)があればそのパス
    (例 marron2610-shinemuscat_parfait2609)。無ければ名前のハッシュ(接頭辞 cocos)。"""
    if link:
        p = link[len("/menu/fair/"):] if link.startswith("/menu/fair/") else link.strip("/")
        p = re.sub(r"\.html$", "", p)
        pid = re.sub(r"[^A-Za-z0-9_\-]+", "-", p).strip("-")
        if pid:
            return pid
    return stable_id("cocos", name)


def parse_cocos_fair_page(html: str) -> list[dict]:
    """フェアページ(/menu/fair/)から [{title, items:[{pid, name, price, price_excl_tax, link}]}]。
    フェアは「<h2>フェア名</h2> + <ul class="img_link type_menu_list">」の組で並び、商品はその中の
    <li><a href="詳細ページ"><div class="name">名前</div><div class="price">価格</div></a></li>。
    価格は「¥590(税込¥ 649)」の ¥ 表記。組が1つも無ければ ValueError(構造変更の疑い)。
    価格が取れない商品は items に入れない(そのフェアが0件になるかどうかは呼び出し側が判定する)。"""
    h = _strip_comments(html)
    sections = []
    pat = re.compile(r'<h2[^>]*>(.*?)</h2>\s*<ul[^>]*class="[^"]*type_menu_list[^"]*"[^>]*>(.*?)</ul>', re.S)
    for m in pat.finditer(h):
        items, seen = [], set()
        for li in re.finditer(r'<li><a\s[^>]*href="([^"]*)"[^>]*>(.*?)</a></li>', m.group(2), re.S):
            nm = re.search(r'<div class="name">(.*?)</div>', li.group(2), re.S)
            pr = re.search(r'<div class="price">(.*?)</div>', li.group(2), re.S)
            if not nm or not pr:
                continue
            pp = parse_price_yen_pair(pr.group(1))
            name = clean_text(nm.group(1))
            if not pp or not name:
                continue
            link = li.group(1) if li.group(1).startswith("/menu/fair/") else None
            pid = _cocos_pid(link, name)
            if pid in seen:
                continue
            seen.add(pid)
            items.append({"pid": pid, "name": name, "price_excl_tax": pp[0], "price": pp[1], "link": link})
        sections.append({"title": clean_text(m.group(1)), "items": items})
    if not sections:
        raise ValueError("ココス: フェアページにフェアの見出し(h2)+メニュー一覧(type_menu_list)が見つからない")
    return sections


def parse_cocos_news(html: str) -> list[dict]:
    """/news/<年>/menu/ の一覧から [{date: YYYY-MM-DD, title, text, url}]。text は常に空(一覧にリード文が無い)。
    構造が違えば空のリスト(発売日なしで続行)。"""
    h = _strip_comments(html)
    out = []
    pat = (r'<li><a\s[^>]*href="(/news/[^"]+)"[^>]*>\s*<span class="label[^"]*">.*?</span>\s*'
           r'<span class="date" data-postdate="(\d{4}-\d{2}-\d{2})">.*?</span>\s*<p>(.*?)</p>')
    for m in re.finditer(pat, h, re.S):
        out.append({"date": m.group(2), "title": clean_text(m.group(3)), "text": "",
                    "url": COCOS_BASE + m.group(1)})
    return out

# ---------------------------------------------------------------------------
# ビッグボーイ (www.bigboyjapan.co.jp)
# ---------------------------------------------------------------------------

BIGBOY_BASE = "https://www.bigboyjapan.co.jp"
BIGBOY_MENU_PATH = "/menu/grand/"
BIGBOY_FAIR_PATH = "/fair/"
BIGBOY_SECTION_TITLE = "期間限定メニュー"

_PRICE_YEN_PAIR_BB_RE = re.compile(r"(?:¥|￥)\s*([\d,]+)\s*[（(]\s*税込\s*(?:¥|￥)\s*([\d,]+)\s*[）)]")


def parse_bigboy_price_pair(text: str | None) -> tuple[int, int] | None:
    """「¥1,490（税込¥1,639）」→ (税抜, 税込)。ビッグボーイの ¥ 表記専用(共通の parse_price_pair は円表記用)。
    公式HTMLでは ¥ と数字が別タグ(<span class="yen">¥</span>1,490)に分かれているので、タグを除いてから読む。
    見つからなければ None。"""
    t = unicodedata.normalize("NFKC", clean_text(text))
    m = _PRICE_YEN_PAIR_BB_RE.search(t)
    if not m:
        return None
    return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))


def parse_bigboy_grand_menu(html: str) -> dict:
    """グランドメニュー(/menu/grand/)の「期間限定メニュー」欄から {title, items:[{pid, name, price,
    price_max, price_excl_tax, price_variants}]}。他の欄(大俵ハンバーグ等の定番)は読まない。
    商品は欄の中の <li class="box"> で、名前は <h4 class="name"> の <span class="main">
    (付け合わせの注記 <span class="sub"> は名前に含めない)。価格は <p class="price"> で、
    サイズ別に複数ある商品は price=先頭サイズの税込・price_max=最大の税込・price_variants に
    [{label, price}] の内訳を入れる(サイズが1つなら price_max は None、price_variants は空)。
    識別キーは、商品ごとのページが無いので「grand」＋正規化した商品名のハッシュ。
    欄そのものが無ければ ValueError(構造変更の疑い)。価格が取れた商品が0件なら items は空
    (呼び出し側が「不完全」とする)。"""
    h = _strip_comments(html)
    body = None
    for m in re.finditer(r"<section\b[^>]*>(.*?)</section>", h, re.S):
        t = re.search(r'<h3[^>]*class="[^"]*tab_title[^"]*"[^>]*>(.*?)</h3>', m.group(1), re.S)
        if t and clean_text(t.group(1)) == BIGBOY_SECTION_TITLE:
            body = m.group(1)
            break
    if body is None:
        raise ValueError("ビッグボーイ: グランドメニューに「期間限定メニュー」欄(tab_title)が見つからない")
    items, seen = [], set()
    for chunk in re.split(r'<li[^>]*class="[^"]*box[^"]*"[^>]*>', body)[1:]:
        nm = re.search(r'<h4[^>]*class="[^"]*name[^"]*"[^>]*>(.*?)</h4>', chunk, re.S)
        if not nm:
            continue
        main = re.search(r'<span[^>]*class="[^"]*main[^"]*"[^>]*>(.*?)</span>', nm.group(1), re.S)
        name = clean_text(main.group(1)) if main else ""
        if not name:
            continue
        variants = []
        for pr in re.finditer(r'<p[^>]*class="[^"]*price[^"]*"[^>]*>(.*?)</p>', chunk, re.S):
            pp = parse_bigboy_price_pair(pr.group(1))
            if not pp:
                continue
            sz = re.search(r'<span[^>]*class="[^"]*size[^"]*"[^>]*>(.*?)</span>', pr.group(1), re.S)
            variants.append({"label": clean_text(sz.group(1)) if sz else "",
                             "price_excl_tax": pp[0], "price": pp[1]})
        if not variants:
            continue
        pid = stable_id("grand", name)
        if pid in seen:
            continue
        seen.add(pid)
        items.append({"pid": pid, "name": name,
                      "price_excl_tax": variants[0]["price_excl_tax"],
                      "price": variants[0]["price"],
                      "price_max": max(v["price"] for v in variants) if len(variants) > 1 else None,
                      "price_variants": ([{"label": v["label"], "price": v["price"]} for v in variants]
                                         if len(variants) > 1 else [])})
    return {"title": BIGBOY_SECTION_TITLE, "items": items}


def parse_bigboy_fair_links(html: str) -> list[dict]:
    """フェア情報(/fair/)の一覧から [{path, title}]。各記事は <li class="post"> で、見出しは
    <p class="item">、詳細へのリンクは /news/fair/<id>.html。構造が違えば空のリスト
    (開始日なしで続行する。デニーズのニュースと同じ扱い)。"""
    h = _strip_comments(html)
    out, seen = [], set()
    for m in re.finditer(r'<li[^>]*class="[^"]*post[^"]*"[^>]*>(.*?)</li>', h, re.S):
        a = re.search(r'href="(/news/[^"#?]+\.html)"', m.group(1))
        if not a or a.group(1) in seen:
            continue
        seen.add(a.group(1))
        t = re.search(r'<p[^>]*class="[^"]*\bitem\b[^"]*"[^>]*>(.*?)</p>', m.group(1), re.S)
        out.append({"path": a.group(1), "title": clean_text(t.group(1)) if t else ""})
    return out


def parse_bigboy_news_article(html: str, url: str) -> dict | None:
    """ニュース記事(/news/fair/<id>.html 等)から {date, title, text, url}。
    date は <p class="date">2026/10/14</p>(掲載日)、title は <p class="item">(見出し)、
    text は本文(<p class="item_detail">以下)を平文にしたもの(保存はしない。開始日の照合だけに使う)。
    掲載日か見出しが取れなければ None(その記事は照合に使わない)。"""
    h = _strip_comments(html)
    d = re.search(r'<p[^>]*class="[^"]*date[^"]*"[^>]*>\s*(\d{4})/(\d{1,2})/(\d{1,2})\s*</p>', h)
    t = re.search(r'<p[^>]*class="[^"]*\bitem\b[^"]*"[^>]*>(.*?)</p>', h, re.S)
    if not d or not t:
        return None
    body = ""
    b = re.search(r'<p[^>]*class="[^"]*item_detail[^"]*"[^>]*>(.*?)</li>', h, re.S)
    if b:
        body = strip_html(b.group(1))
    return {"date": f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}",
            "title": clean_text(t.group(1)), "text": body, "url": url}
# ---------------------------------------------------------------------------
# ジョイフル (www.joyfull.co.jp)
# ---------------------------------------------------------------------------

JOYFULL_BASE = "https://www.joyfull.co.jp"
JOYFULL_LIST_PATH = "/menu?category=19"
JOYFULL_NEWS_PATH = "/news?category=menu"
JOYFULL_CATEGORY_NAME = "季節・期間限定"

_JOYFULL_PRICE_RE = re.compile(r"¥\s*([\d,]+)\s*[（(]\s*税込\s*¥\s*([\d,]+)\s*[）)]")
_JOYFULL_LISTED_LAUNCH_RE = re.compile(
    r"^【(\d{4})年(\d{1,2})月(\d{1,2})日（[^）]*）(?:\d{1,2}時)?より販売】")


def parse_joyfull_price_pair(text: str | None) -> tuple[int, int] | None:
    """「￥1,299 （税込￥1,428）」→ (税抜, 税込)。全角￥と全角括弧の書式(NFKCで半角化してから読む)。
    共通の parse_price_pair(「N円（税込M円）」)では取れない。見つからなければ None。"""
    t = unicodedata.normalize("NFKC", clean_text(text))
    m = _JOYFULL_PRICE_RE.search(t)
    if not m:
        return None
    return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))


def parse_joyfull_listed_launch(name: str | None) -> str | None:
    """商品名の先頭の「【2026年12月1日（火）15時より販売】」→ "2026-12-01"。
    販売開始前の商品にだけ付く告知で、年まで含む一次情報。付いていなければ None。"""
    m = _JOYFULL_LISTED_LAUNCH_RE.match(name or "")
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def parse_joyfull_category(html: str) -> dict:
    """「季節・期間限定」の一覧(/menu?category=19)から
    {title, declared_count, items:[{pid, name, price, price_excl_tax, listed_launch, link}]}。
    商品は ul.menu-grid の li.mg-item のカード(a.menu-card)で、識別キーは商品ページのパス(/menu/<数値ID>)。
    価格(全角￥の税抜＋税込併記)はカードの中(p.menu-meta)にある。名前に販売開始の告知
    「【…より販売】」の接頭辞が付いていたら、開始日は listed_launch に別途入れ、名前からは接頭辞を落とす
    (表示と名前での照合は接頭辞なしで行う。モルのレビュー指摘、2026-11-23)。
    名前全体を囲む「」も、前後のかぎかっこだけを外して記録する(同、2026-11-23)。
    一覧の枠(見出し・ul.menu-grid)が無ければ ValueError(構造変更の疑い)。
    価格の取れないカードは items に入れない(呼び出し側が declared_count との差で「不完全」とする)。"""
    h = _strip_comments(html)
    t = re.search(r"<h2[^>]*>\s*" + JOYFULL_CATEGORY_NAME + r"\s*</h2>", h)
    g = re.search(r'<ul[^>]*class="[^"]*menu-grid[^"]*"[^>]*>(.*?)</ul>', h, re.S)
    if not t or not g:
        raise ValueError("ジョイフル: 一覧の見出し(季節・期間限定)またはメニュー一覧(menu-grid)が見つからない")
    cnt = re.search(r'該当件数\s*<span class="count">(\d+)</span>', h)
    items, seen = [], set()
    for li in re.finditer(r'<li[^>]*class="[^"]*mg-item[^"]*"[^>]*>(.*?)</li>', g.group(1), re.S):
        a = re.search(r'href="https://www\.joyfull\.co\.jp/menu/(\d+)"', li.group(1))
        name_m = re.search(r'<h3[^>]*class="[^"]*mg-title[^"]*"[^>]*>(.*?)</h3>', li.group(1), re.S)
        price_m = re.search(r'<p[^>]*class="[^"]*menu-meta[^"]*"[^>]*>(.*?)</p>', li.group(1), re.S)
        if not a or not name_m:
            continue
        pp = parse_joyfull_price_pair(price_m.group(1)) if price_m else None
        name = clean_text(name_m.group(1))
        if not pp or not name:
            continue
        pid = a.group(1)
        if pid in seen:
            continue
        seen.add(pid)
        listed_launch = parse_joyfull_listed_launch(name)
        if listed_launch:
            name = _JOYFULL_LISTED_LAUNCH_RE.sub("", name).strip()
        if len(name) >= 2 and name.startswith("「") and name.endswith("」"):
            # 公式の表示では商品名全体が「」で囲まれている。前後のかぎかっこは名前の一部ではないので外す
            # (モルのレビュー指摘、2026-11-23)
            name = name[1:-1].strip()
        items.append({"pid": pid, "name": name, "price_excl_tax": pp[0], "price": pp[1],
                      "listed_launch": listed_launch,
                      "link": f"/menu/{pid}"})
    return {"title": JOYFULL_CATEGORY_NAME,
            "declared_count": int(cnt.group(1)) if cnt else None,
            "items": items}


def parse_joyfull_detail(html: str) -> dict:
    """商品ページから {fair}。フェア名はパンくず(BreadcrumbList)の
    「ホーム / メニュー / 季節・期間限定 / <フェア名> / <商品名>」の4番目。フェアに属さない商品は None。
    パンくずが無い・並びが想定と違えば ValueError(構造変更の疑い)。"""
    h = _strip_comments(html)
    m = re.search(r'<ol[^>]*class="[^"]*breadcrumb-list[^"]*"[^>]*>(.*?)</ol>', h, re.S)
    if not m:
        raise ValueError("ジョイフル: 商品ページのパンくず(breadcrumb-list)が見つからない")
    names = [clean_text(x) for x in re.findall(r'itemprop="name"[^>]*>([^<]+)</span>', m.group(1))]
    if len(names) not in (4, 5) or names[:3] != ["ホーム", "メニュー", JOYFULL_CATEGORY_NAME]:
        raise ValueError(f"ジョイフル: パンくずの並びが想定と違う: {names}")
    return {"fair": names[3] if len(names) == 5 else None}


def parse_joyfull_news(html: str) -> list[dict]:
    """お知らせ(メニュー分類)の一覧から [{date: YYYY-MM-DD, title, url}]。
    カード(a.menu-card)の中の span.date(YYYY.MM.DD)と h3.news-title を読む。リード文は一覧に無いので text は空。
    構造が違えば空のリスト(発売日なしで続行)。"""
    h = _strip_comments(html)
    out = []
    for a in re.finditer(r'<a\s[^>]*href="(https://www\.joyfull\.co\.jp/news/\d+)"[^>]*>(.*?)</a>', h, re.S):
        d = re.search(r'<span class="date">(\d{4})\.(\d{1,2})\.(\d{1,2})</span>', a.group(2))
        t = re.search(r'<h3[^>]*class="[^"]*news-title[^"]*"[^>]*>(.*?)</h3>', a.group(2), re.S)
        if not d or not t:
            continue
        out.append({"date": f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}",
                    "title": clean_text(t.group(1)), "url": a.group(1)})
    return out


# ---------------------------------------------------------------------------
# ステーキのどん (www.steak-don.jp)
# ---------------------------------------------------------------------------

STEAKDON_BASE = "https://www.steak-don.jp"
STEAKDON_FAIR_LIST_PATH = "/fmenu_list.html?fmenu_categ_id=94"
STEAKDON_NEWS_PATH = "/news.html"


def _steakdon_price_block(block_html: str) -> dict | None:
    """<p class="menu_price"> の中身(「100g　2,980円（税込3,278円）<br>150g　…<br>※店舗限定」)を分解する。
    <br> で区切られた行ごとに parse_price_pair で読み、価格の手前の語(「100g」)をサイズのラベルにする。
    価格でない行(「※店舗限定」など)は note に集める。価格が1つも取れなければ None。"""
    variants, notes = [], []
    for seg in re.split(r"<br\s*/?>", block_html or ""):
        text = clean_text(seg)
        if not text:
            continue
        pp = parse_price_pair(text)
        if pp is None:
            notes.append(text)
            continue
        label = _PRICE_PAIR_RE.sub("", unicodedata.normalize("NFKC", text)).strip()
        variants.append({"label": label, "price_excl_tax": pp[0], "price": pp[1]})
    if not variants:
        return None
    prices = [v["price"] for v in variants]
    return {
        "price": prices[0],
        "price_max": max(prices) if len(set(prices)) > 1 else None,
        "price_excl_tax": variants[0]["price_excl_tax"],
        "price_variants": ([{"label": v["label"], "price": v["price"]} for v in variants]
                           if len(variants) > 1 else None),
        "note": "".join(notes) or None,
    }


def parse_steakdon_fair_list(html: str) -> dict:
    """フェアメニューのカテゴリページ(fmenu_list.html?fmenu_categ_id=94)から
    {title, items:[{pid, name, price, price_max, price_excl_tax, price_variants, note, link}], skipped}。
    商品は <div class="menulist_list_inner"> の中の、商品詳細へのリンク
    (fmenu_detail.html?fmenu_item_id=N)に付いた <p class="menu_name"> と <p class="menu_price">。
    識別キーは公式の商品ID(fmenu_item_id)。バナー側のフェアページ(campaign_fair.html)は価格が画像だけなので使わない。
    見出し(menu_list_subtitle)か一覧の枠(menulist_list_inner)が無ければ ValueError(構造変更の疑い)。
    リンクはあったが名前か価格が読めなかった商品は items に入れず、件数を skipped に数える
    (呼び出し側は skipped が1件以上なら、その回を「不完全」として終了判定をしない)。
    価格が取れた商品が0件なら items は空(呼び出し側が「不完全」とする)。"""
    h = _strip_comments(html)
    t = re.search(r'<div class="menu_list_subtitle">\s*<p>(.*?)</p>', h, re.S)
    if not t:
        raise ValueError("ステーキのどん: カテゴリページの見出し(menu_list_subtitle)が見つからない")
    inner = re.search(r'<div class="menulist_list_inner">', h)
    if not inner:
        raise ValueError("ステーキのどん: 商品一覧の枠(menulist_list_inner)が見つからない")
    end = h.find("</ul>", inner.end())
    if end < 0:
        raise ValueError("ステーキのどん: 商品一覧の枠(menulist_list_inner)に </ul> が見つからない")
    block_all = h[inner.end():end]
    items, seen, skipped = [], set(), 0
    pat = r'<a\s[^>]*href="fmenu_detail\.html\?fmenu_item_id=(\d+)"[^>]*>(.*?)</a>'
    for m in re.finditer(pat, block_all, re.S):
        item_id, block = m.group(1), m.group(2)
        if item_id in seen:
            continue
        nm = re.search(r'<p class="menu_name">(.*?)</p>', block, re.S)
        pm = re.search(r'<p class="menu_price">(.*?)</p>', block, re.S)
        name = clean_text(nm.group(1)) if nm else ""
        price = _steakdon_price_block(pm.group(1)) if pm else None
        if not name or price is None:
            skipped += 1
            continue
        seen.add(item_id)
        items.append({"pid": item_id, "name": name, "link": f"/fmenu_detail.html?fmenu_item_id={item_id}",
                      **price})
    return {"title": clean_text(t.group(1)), "items": items, "skipped": skipped}


def parse_steakdon_news(html: str) -> list[dict]:
    """/news.html の一覧から [{date: YYYY-MM-DD, title, text, url}]。text は一覧にリード文が無いので空。
    行は <td class="news_date">2026年09月09日</td><td><a href="news_detail.html?num=1041">見出し</a></td>。
    構造が違えば空のリスト(発売日なしで続行)。"""
    h = _strip_comments(html)
    out = []
    pat = (r'<td class="news_date">\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*</td>\s*'
           r'<td><a\s[^>]*href="(news_detail\.html\?num=\d+)"[^>]*>(.*?)</a></td>')
    for m in re.finditer(pat, h, re.S):
        out.append({"date": f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
                    "title": clean_text(m.group(5)), "text": "",
                    "url": STEAKDON_BASE + "/" + m.group(4)})
    return out


# ---------------------------------------------------------------------------
# ジョリーパスタ (www.jolly-pasta.co.jp)
# ---------------------------------------------------------------------------

JOLLYPASTA_BASE = "https://www.jolly-pasta.co.jp"
JOLLYPASTA_MENU_JSON_PATH = "/json/jp_menu.json"
JOLLYPASTA_NEWS_PATH = "/info/"
JOLLYPASTA_MENU_PATH = "/menu/"
JOLLYPASTA_SEASON_CATEGORY = "季節のおすすめ"


def _jollypasta_pid(url_path: str | None) -> str:
    """詳細URLのパスから識別キーを作る(/menu/season/r_soup_oystercream.html → season-r_soup_oystercream)。
    ココスと同じく、パスの区切りを「-」にし、末尾の .html を落とす。"""
    p = re.sub(r"^https?://[^/]+", "", (url_path or "").strip())
    p = p.split("?")[0].split("#")[0]
    if p.startswith("/menu/"):
        p = p[len("/menu/"):]
    else:
        p = p.strip("/")
    p = re.sub(r"\.html$", "", p)
    return re.sub(r"[^A-Za-z0-9_\-]+", "-", p).strip("-")


def parse_jollypasta_menu(json_text: str) -> list[dict]:
    """メニューJSON(jp_menu.json)から [{pid, name, price, price_excl_tax, category, official_url}]。
    JSON は「カテゴリ名 → 商品の配列」で、商品は 名称・金額・詳細URL を持つ。ここで読むキーは
    この3つとカテゴリだけ(説明・画像URL・カロリー・アレルゲン非掲載・NEW・RENEW・スタート は読まない)。
    価格は「1,490円(税込1,639円)」の書式で、共通の parse_price_pair で分解する。金額が無い・
    読めない商品は price/price_excl_tax を None にして返す(対象にするかは呼び出し側が決める)。
    識別キーは詳細URLのパス。同じ商品が複数カテゴリに載るときは1件だけ残し、カテゴリは
    「季節のおすすめ」を優先する(所在の判別は呼び出し側の内部処理だけに使う)。
    JSON として壊れている・「季節のおすすめ」キーが無い・行の構造が違う場合は ValueError
    (構造変更の疑い)。"""
    try:
        data = json.loads(json_text)
    except (ValueError, TypeError) as e:
        raise ValueError(f"ジョリーパスタ: メニューJSONが読めない: {e}") from e
    if not isinstance(data, dict) or JOLLYPASTA_SEASON_CATEGORY not in data:
        raise ValueError("ジョリーパスタ: メニューJSONに「季節のおすすめ」カテゴリが無い")
    items: list[dict] = []
    by_pid: dict[str, dict] = {}
    for category, rows in data.items():
        if not isinstance(rows, list):
            raise ValueError(f"ジョリーパスタ: カテゴリ「{category}」が配列でない")
        for row in rows:
            if not isinstance(row, dict) or "名称" not in row or "詳細URL" not in row:
                raise ValueError("ジョリーパスタ: 商品の行に名称・詳細URLが無い")
            name = clean_text(row.get("名称"))
            url_path = (row.get("詳細URL") or "").strip()
            if not name or not url_path:
                continue
            pid = _jollypasta_pid(url_path) or stable_id("jollypasta", name)
            pp = parse_price_pair(row.get("金額"))
            if pid in by_pid:
                # 複数カテゴリに載る商品は1件だけ。「季節のおすすめ」に載っていればそちらを所在にする
                if category == JOLLYPASTA_SEASON_CATEGORY:
                    by_pid[pid]["category"] = category
                continue
            item = {"pid": pid, "name": name,
                    "price_excl_tax": pp[0] if pp else None,
                    "price": pp[1] if pp else None,
                    "category": category,
                    "official_url": JOLLYPASTA_BASE + (url_path if url_path.startswith("/") else "/" + url_path)}
            by_pid[pid] = item
            items.append(item)
    return items


def parse_jollypasta_news_index(html: str) -> list[dict]:
    """ニュース一覧(/info/)から [{date: YYYY-MM-DD, title, url, category}]。
    行は <li data-href="/info/menu/20261124.html" data-date="2026.11.24" data-category="メニュー"
    data-title="12月1日(火)「窯焼きチーズパスタフェア」が始まります！"> の属性で並ぶ。
    構造が違えば空のリスト(開始日なしで続行)。"""
    h = _strip_comments(html)
    out = []
    for m in re.finditer(r'<li\b[^>]*\bdata-href="[^"]+"[^>]*>', h):
        tag = m.group(0)

        def attr(name: str) -> str:
            a = re.search(name + r'="([^"]*)"', tag)
            return html_lib.unescape(a.group(1)) if a else ""

        d = re.fullmatch(r"\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\s*", attr("data-date"))
        href = attr("data-href")
        if not d or not href:
            continue
        url = href if href.startswith("http") else JOLLYPASTA_BASE + (href if href.startswith("/") else "/" + href)
        out.append({"date": f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}",
                    "title": clean_text(attr("data-title")), "url": url,
                    "category": clean_text(attr("data-category"))})
    return out


def _jollypasta_headline_launch(title: str | None, date_iso: str) -> str | None:
    """フェア記事の見出し冒頭の「12月1日(火)」→ "2026-12-01"。
    見出しは開始日で始まる(「12月1日(火)「窯焼きチーズパスタフェア」が始まります！」)。
    「始まります」は launch_dates_in_text の対象語(より・から・発売…)に含まれないため、
    共通の抽出では拾えない。年は掲載日から補い、半年以上ずれる場合は前後の年に寄せる
    (launch_dates_in_text と同じ寄せ方)。冒頭に日付が無ければ None。"""
    m = re.match(r"\s*(\d{1,2})月(\d{1,2})日", title or "")
    if not m:
        return None
    try:
        ref = datetime.date.fromisoformat(date_iso)
        cand = datetime.date(ref.year, int(m.group(1)), int(m.group(2)))
        delta = (cand - ref).days
        if delta > 180:
            cand = datetime.date(ref.year - 1, cand.month, cand.day)
        elif delta < -180:
            cand = datetime.date(ref.year + 1, cand.month, cand.day)
    except ValueError:
        return None
    return cand.isoformat()


def jollypasta_fair_name(title: str | None) -> str | None:
    """見出しの「…フェア」をフェア名として取り出す
    (「12月1日(火)「窯焼きチーズパスタフェア」が始まります！」→「窯焼きチーズパスタフェア」)。
    取れなければ None。"""
    for pat in (r"「([^」]*フェア[^」]*)」", r"『([^』]*フェア[^』]*)』"):
        m = re.search(pat, title or "")
        if m:
            return clean_text(m.group(1))
    return None


def parse_jollypasta_news_article(html: str, url: str) -> dict | None:
    """ニュース記事から {date, title, text, url, launch_date}。
    date は .top_news_date(「2026.11.24」)、title は .top_news_title、text は .news_detail_txt の
    本文を平文にしたもの(保存はしない。開始日の照合と、フェア対象の拾い上げだけに使う)。
    launch_date は見出し冒頭の日付(_jollypasta_headline_launch)。掲載日か見出しが取れなければ
    None(その記事は照合に使わない)。"""
    h = _strip_comments(html)
    d = re.search(r'<div[^>]*class="[^"]*top_news_date[^"]*"[^>]*>\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\s*</div>', h)
    t = re.search(r'<div[^>]*class="[^"]*top_news_title[^"]*"[^>]*>(.*?)</div>', h, re.S)
    if not d or not t:
        return None
    date = f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}"
    title = clean_text(t.group(1))
    body = ""
    b = re.search(r'<div[^>]*class="[^"]*news_detail_txt[^"]*"[^>]*>', h)
    if b:
        chunk = h[b.end(): b.end() + 20000]
        cut = chunk.find("submenu_button")  # 本文の後ろの「ニュース一覧に戻る」ボタンは本文ではない
        if cut >= 0:
            start = chunk.rfind("<div", 0, cut)
            chunk = chunk[:start if start >= 0 else cut]
        body = strip_html(chunk)
    return {"date": date, "title": title, "text": body, "url": url,
            "launch_date": _jollypasta_headline_launch(title, date)}
