#!/usr/bin/env python3
"""デニーズ・ジョナサン・ココスの公式ページのパーサ。

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
