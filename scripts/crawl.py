#!/usr/bin/env python3
"""デニーズ・ジョナサン・ココス・ビッグボーイ・ジョイフル・ステーキのどんの期間限定フェアメニューを巡回し、
data/products/{dennys|jonathan|cocos|bigboy|joyfull|steakdon}/{id}.json に1商品1ファイルで蓄積する。

このサイトの核は「販売状況の追跡」。公式サイトはフェアが終わると商品を消すので、
一覧に居た商品が消えたら終了とみなして記録を残す(カフェポチ・ファストフードポチと同じ設計)。

・既存ファイルは丸ごと上書きしない(初回取得が正)。更新するのは last_seen_at / status /
  price_history 等の追跡用の項目と、まだ空の発売日だけ。
・**初回から、その時点でフェアとして載っている商品を全部記録する**。baseline_ids.json は
  「初回に見えた記録対象のID」を持ち、2回目以降の歯止め(新規が急に大量に出たら構造変更とみなして保留)の
  判定にだけ使う。
・終了判定は「そのチェーンの一覧取得が全部成功した回」だけ行い、さらに「連続2回(別の日)
  見つからなかった」ときに初めて status=ended にする。
・取得失敗はチェーン単位で隔離し(data/pending.json)、他のチェーンへ波及させない。
・ブロック(403・チャレンジ)されたらUA偽装などに切り替えず、止まって報告する。
・保存するのは事実(フェア名・商品名・価格・日付)だけ。説明文・画像は読み取りもしない。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
import time
import unicodedata
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import parsers  # noqa: E402
from fetch import BlockedError, NotFoundError, fetch  # noqa: E402

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA = ROOT / "data"
PRODUCTS = DATA / "products"
PENDING_PATH = DATA / "pending.json"
BASELINE_PATH = DATA / "baseline_ids.json"
RUN_SUMMARY = DATA / "run_summary.json"
LIST_STATE_PATH = DATA / "list_state.json"  # チェーンごとの前回の記録対象の件数(急減の検知用)
JST = datetime.timezone(datetime.timedelta(hours=9))

UA = CONFIG.get("user_agent", "FamiresPochi/1.0 (+https://famires.netaful.jp/)")
INTERVALS = CONFIG.get("request_interval_seconds", {})
MAX_REQUESTS = CONFIG.get("max_requests_per_run", {})
MIN_INTERVAL = 1.0  # どのチェーンも1秒未満にはしない
# 連続何回(別の日)見つからなければ終了扱いにするか
MISSES_TO_END = 2
# 記録対象の件数が前回の半分未満になったら、3日続くまで「一覧が壊れた」とみなして終了判定をしない
RATIO_MIN = 0.5
RATIO_MIN_PREV = 8
RATIO_ACCEPT_DAYS = 3


def now_iso() -> str:
    return datetime.datetime.now(JST).isoformat(timespec="seconds")


def today_jst() -> str:
    return datetime.datetime.now(JST).date().isoformat()


# ---------------------------------------------------------------------------
# 保存まわり
# ---------------------------------------------------------------------------

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, obj, **kw) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, **kw), encoding="utf-8")


def product_path(chain: str, product_id: str) -> Path:
    return PRODUCTS / chain / f"{product_id}.json"


def save_product(chain: str, product: dict) -> None:
    save_json(product_path(chain, product["product_id"]), product)


def load_product(chain: str, product_id: str) -> dict | None:
    return load_json(product_path(chain, product_id), None)


def load_chain_products(chain: str) -> list[dict]:
    out = []
    d = PRODUCTS / chain
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            p = load_json(f, None)
            if p:
                out.append(p)
    return out


class Throttle:
    """チェーンごとに最後のリクエスト時刻を覚え、間隔を守って待つ。"""

    def __init__(self):
        self.last: dict[str, float] = {}

    def wait(self, chain: str) -> None:
        interval = max(INTERVALS.get(chain, 2), MIN_INTERVAL)
        last = self.last.get(chain)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < interval:
                time.sleep(interval - elapsed)
        self.last[chain] = time.monotonic()


class Getter:
    """リクエスト数の上限つきの取得器。テストでは差し替える。素のUA(config の user_agent)で取る。"""

    def __init__(self):
        self.throttle = Throttle()
        self.counts: dict[str, int] = {}

    def __call__(self, chain: str, url: str) -> str:
        limit = MAX_REQUESTS.get(chain)
        if limit is not None and self.counts.get(chain, 0) >= limit:
            raise RuntimeError(f"{chain}: 1回の実行あたりのリクエスト上限({limit})に達しました")
        self.throttle.wait(chain)
        self.counts[chain] = self.counts.get(chain, 0) + 1
        return fetch(url, UA)


# ---------------------------------------------------------------------------
# 販売状況の追跡(チェーン共通)
# ---------------------------------------------------------------------------

def record_price(product: dict, price: int | None, price_max: int | None, today: str, relaunch: bool = False) -> bool:
    """価格(と上限)が前回の記録と違えば price_history に追記する。変わったら True。"""
    if price is None:
        return False
    pmax = price_max if (price_max is not None and price_max != price) else None
    hist = product.setdefault("price_history", [])
    last = hist[-1] if hist else None
    if last is not None and last.get("price") == price and last.get("price_max") == pmax:
        return False
    entry = {"date": today, "price": price}
    if pmax is not None:
        entry["price_max"] = pmax
    if relaunch:
        entry["relaunch"] = True
    if last is not None and last.get("date") == today:
        hist[-1] = entry  # 同じ日の再実行は上書き
    else:
        hist.append(entry)
    product["price"] = price
    product["price_max"] = pmax
    return True


def start_new_season(product: dict, old_ended: str | None) -> None:
    """終了後に同じIDが一覧へ戻ってきた(季節商品の再登場)。昨季の期間を seasons に残し、
    今季の発売日は未確定に戻す(昨季の日付を今季として出さない)。"""
    product.setdefault("seasons", []).append({
        "launch_date": product.get("launch_date"),
        "observed_start": season_ref_for_end(product),
        "ended_observed_at": old_ended,
        "news_url": product.get("news_url"),
        "news_title": product.get("news_title"),
    })
    product["launch_date"] = None
    product["launch_date_source"] = None
    for k in ("news_url", "news_title", "news_date"):
        product[k] = None
    product["launch_search_runs"] = 0


def season_ref_for_end(product: dict) -> str:
    """終わった季の観測の起点日(再登場前の relaunches 末尾、無ければ初回に見つけた日)。"""
    rel = product.get("relaunches") or []
    if rel and rel[-1].get("reappeared_at"):
        return rel[-1]["reappeared_at"]
    return (product.get("first_seen_at") or "")[:10]


def touch_seen(product: dict, entry_price: int | None, entry_price_max: int | None, today: str) -> bool:
    """一覧に居た既存商品の追跡項目を更新する。変更があれば True。

    ・last_seen_at を更新、status=on_sale、見失った回数をリセット
    ・終了後に再登場したら on_sale に戻し、relaunches / seasons に記録
    ・一覧の価格が前回と違えば price_history に追記
    """
    relaunched = False
    if product.get("status") == "ended":
        old_ended = product.get("ended_observed_at")
        start_new_season(product, old_ended)
        product.setdefault("relaunches", []).append({
            "ended_observed_at": old_ended,
            "reappeared_at": today,
        })
        product["status"] = "on_sale"
        product["ended_observed_at"] = None
        relaunched = True
    elif product.get("status") != "on_sale":
        product["status"] = "on_sale"
    if product.get("missed_runs"):
        product["missed_runs"] = 0
        product["last_miss_date"] = None
    product["last_seen_at"] = today  # 日付だけ(同じ日に複数回実行してもgitの差分が増えないように)
    record_price(product, entry_price, entry_price_max, today, relaunch=relaunched)
    return relaunched


def apply_missing(chain: str, seen_ids: set[str], today: str, stats: dict) -> None:
    """一覧取得が全部成功した回にだけ呼ぶ。一覧に居なかった販売中の商品を数え、
    連続 MISSES_TO_END 回(別の日)見つからなければ status=ended にする。"""
    for p in load_chain_products(chain):
        if p["product_id"] in seen_ids:
            continue
        if p.get("status") != "on_sale":
            continue
        if p.get("last_miss_date") == today:
            continue  # 同じ日に何度実行しても1回と数える
        p["missed_runs"] = int(p.get("missed_runs") or 0) + 1
        p["last_miss_date"] = today
        if p["missed_runs"] >= MISSES_TO_END:
            p["status"] = "ended"
            p["ended_observed_at"] = today
            stats["ended"] = stats.get("ended", 0) + 1
        save_product(chain, p)


def new_stats() -> dict:
    return {"list_requests": 0, "detail_requests": 0, "new_products": 0, "ended": 0,
            "failed": 0, "blocked": False, "list_ok": False, "limited_seen": 0}


def baseline_for(chain: str) -> set[str] | None:
    data = load_json(BASELINE_PATH, {})
    ids = data.get(chain)
    return set(ids) if ids is not None else None


def save_baseline(chain: str, ids: set[str]) -> None:
    data = load_json(BASELINE_PATH, {})
    data[chain] = sorted(ids)
    save_json(BASELINE_PATH, data)


def ratio_ok(chain: str, n: int, today: str) -> bool:
    """記録対象の件数が前回の半分未満に急減したら、3日続くまで終了判定をしない(取得の不具合の疑い)。
    季節の入れ替わりで本当に減ったなら、3日目に受け入れて基準を更新する。"""
    state = load_json(LIST_STATE_PATH, {})
    cur = state.get(chain) or {}
    prev = int(cur.get("count") or 0)
    if prev >= RATIO_MIN_PREV and n < prev * RATIO_MIN:
        low = dict(cur.get("low") or {})
        if low.get("date") != today:
            low = {"date": today, "days": int(low.get("days") or 0) + 1, "count": n}
        state[chain] = {**cur, "low": low}
        if low["days"] < RATIO_ACCEPT_DAYS:
            save_json(LIST_STATE_PATH, state, sort_keys=True)
            print(f"[WARNING] {chain}: 記録対象が{n}件(前回{prev}件)に急減。{low['days']}日目なので終了判定はしない",
                  file=sys.stderr)
            return False
    state[chain] = {"count": n, "checked_at": today}
    save_json(LIST_STATE_PATH, state, sort_keys=True)
    return True


# ---------------------------------------------------------------------------
# 歯止め: 1回で「新規候補」が極端に多いときは、公式のページ構造・ID体系の変更とみなして記録しない
# ---------------------------------------------------------------------------
# 2026-10-13 に松屋(ファストフードポチ)が商品URLの日付を一斉に更新し、定番メニューまで37件が
# 「新規」になった事故から入れた仕組み。新規候補(baselineにも既存レコードにも無い項目)が
# max(new_burst_min[チェーン別], 一覧の項目数×new_burst_ratio)を超えたら、その回はそのチェーンの
# 新規を記録せず、終了判定もしない。
# **初回(baselineがまだ無い)は対象外**(ファミレスポチは初回にフェア商品を全部記録する)。
# 保留は翌日以降に候補が閾値以下に戻れば自然に再開する。3日連続で保留なら通知が「要判断」に変わる。
# フェアの入れ替えで一度に新作が10品以上出ることがある(デニーズは1フェアで8品前後)ため、
# 閾値はファストフードポチより高め(config の new_burst_min / new_burst_ratio / new_burst_min_by_chain)。

BURST_KEY = "_suspected_restructure"
BURST_ESCALATE_DAYS = 3


def burst_threshold(chain: str, list_size: int) -> int:
    lo = int((CONFIG.get("new_burst_min_by_chain") or {}).get(chain, CONFIG.get("new_burst_min", 15)))
    ratio = float(CONFIG.get("new_burst_ratio", 0.6))
    return max(lo, int(list_size * ratio))


def burst_filter(chain: str, items: dict, baseline: set[str] | None, pending: dict, stats: dict,
                 today: str) -> dict:
    """items({商品ID: 一覧の項目})を受け取り、歯止めが働かなければそのまま返す。
    働いたら、既存レコードのある項目だけを返し(最終確認日の更新だけは続ける)、
    stats[chain]["list_ok"]=False(baseline作成・終了判定を止める)と、保留の記録を残す。"""
    st = stats[chain]
    chain_pending = pending.setdefault(chain, {})
    if baseline is None:  # 初回は対象外
        chain_pending.pop(BURST_KEY, None)
        return items
    candidates = [pid for pid in items if pid not in baseline and load_product(chain, pid) is None]
    limit = burst_threshold(chain, len(items))
    if len(candidates) <= limit:
        chain_pending.pop(BURST_KEY, None)
        return items
    prev = chain_pending.get(BURST_KEY) or {}
    if prev.get("date") == today:
        days = int(prev.get("consecutive_days") or 1)
    else:
        days = int(prev.get("consecutive_days") or 0) + 1
    chain_pending[BURST_KEY] = {
        "reason": "suspected_restructure", "count": len(candidates), "threshold": limit,
        "list_size": len(items), "date": today, "consecutive_days": days,
        "first_date": prev.get("first_date") or today,
        "sample": sorted(candidates)[:5],
    }
    st["suspected_restructure"] = {"count": len(candidates), "threshold": limit, "consecutive_days": days}
    st["list_ok"] = False
    msg = (f"[WARNING] {chain}: 新規候補が一度に{len(candidates)}件(閾値{limit}件・一覧{len(items)}件)。"
           "公式のサイト構造変更の疑い。この回は新規を記録せず、終了判定も行わない")
    if days >= BURST_ESCALATE_DAYS:
        msg += f" [{days}日連続で保留中。運営者の判断が必要]"
    print(msg, file=sys.stderr)
    return {pid: e for pid, e in items.items() if load_product(chain, pid) is not None}


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

class Robots:
    """ホストごとに robots.txt を1回だけ取る。404・HTML(robots.txtが無いサイトが返すページ)は全許可。
    取得に失敗したときも全許可として続行する(警告のみ)。403等のブロックは BlockedError。"""

    def __init__(self, getter, chain: str, stats_st: dict):
        self.getter = getter
        self.chain = chain
        self.st = stats_st
        self.parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

    def allowed(self, base: str, path: str) -> bool:
        rp = self.parsers.get(base)
        if rp is None:
            text = None
            try:
                text = self.getter(self.chain, base + "/robots.txt")
                self.st["list_requests"] += 1
            except NotFoundError:
                self.st["list_requests"] += 1
            except BlockedError:
                raise
            except Exception as e:  # noqa: BLE001
                print(f"[warn] {self.chain} {base}/robots.txt 取得失敗(全許可として続行): {e}", file=sys.stderr)
            if text and re.search(r"<\s*html", text[:500], re.I):
                text = None  # robots.txtの代わりにHTMLを返すサイト
            rp = urllib.robotparser.RobotFileParser()
            rp.parse((text or "User-agent: *\nAllow: /").splitlines())
            self.parsers[base] = rp
        return rp.can_fetch(UA, base + path)


# ---------------------------------------------------------------------------
# 共通の巡回の流れ
# ---------------------------------------------------------------------------

class Run:
    """1チェーンの1回の巡回の状態と、共通の後処理(記録・追跡・終了判定)。"""

    def __init__(self, chain: str, pending: dict, stats: dict, today: str | None):
        self.chain = chain
        # 日付を指定した実行(テスト)では、初回観測の時刻もその日にそろえる
        self.now = now_iso() if today is None else f"{today}T07:00:00+09:00"
        self.today = today or today_jst()
        self.pending = pending
        self.pending.setdefault(chain, {})
        stats.setdefault(chain, new_stats())
        self.stats = stats
        self.st = stats[chain]

    def block(self, where: str, e: Exception) -> None:
        self.st["blocked"] = True
        print(f"[blocked] {self.chain} {where}: {e}", file=sys.stderr)

    def fail_detail(self, pid: str, url: str, reason: str) -> None:
        self.st["failed"] += 1
        self.pending[self.chain][pid] = {"url": url, "reason": reason, "checked_at": self.now}

    def finish(self, entries: dict[str, dict], list_ok: bool, build, refresh=None, enrich=None,
               present_extra: set[str] | None = None) -> None:
        """entries({商品ID: 一覧の項目})を記録する。

        build(entry) -> 新規レコード(ネットワークに触らない。一覧の情報だけで作る)
        refresh(existing, entry) -> 既存レコードに一覧の最新の項目を反映(純粋な更新。変更があれば True)
        enrich(product, entry, is_new) -> 詳細の取得で栄養などを埋める(ネットワークに触れてよい。変更があれば True)
        present_extra: 記録対象ではないが「公式サイトにまだ載っている」ことを示すID(終了判定に足す)
        """
        chain, st, today = self.chain, self.st, self.today
        st["list_ok"] = bool(list_ok and entries)
        st["limited_seen"] = len(entries)
        if st["list_ok"] and not ratio_ok(chain, len(entries), today):
            st["list_ok"] = False
        baseline = baseline_for(chain)
        entries = burst_filter(chain, entries, baseline, self.pending, self.stats, today)
        for pid, e in entries.items():
            existing = load_product(chain, pid)
            is_new = existing is None
            if is_new:
                product = build(e)
                st["new_products"] += 1
                changed = True
            else:
                product = existing
                relaunched = touch_seen(product, e.get("price"), e.get("price_max"), today)
                if relaunched:
                    st["relaunched"] = st.get("relaunched", 0) + 1
                if refresh:
                    refresh(product, e)
                changed = True
            if enrich is not None and not st["blocked"]:
                try:
                    enrich(product, e, is_new)
                except BlockedError as ex:
                    self.block(f"detail {pid}", ex)
                except NotFoundError as ex:
                    self.fail_detail(pid, e.get("official_url") or "", f"404: {ex}")
                except Exception as ex:  # noqa: BLE001
                    self.fail_detail(pid, e.get("official_url") or "", f"fetch_error: {ex}")
                else:
                    self.pending[chain].pop(pid, None)
            if changed:
                save_product(chain, product)
            if st["blocked"]:
                break
        if st["list_ok"] and not st["blocked"]:
            if baseline is None:
                save_baseline(chain, set(entries))
            apply_missing(chain, set(entries) | (present_extra or set()), today, st)


# ---------------------------------------------------------------------------
# 商品レコードの共通部分
# ---------------------------------------------------------------------------

def base_product(chain: str, pid: str, name: str, now: str, today: str) -> dict:
    """全チェーン共通のレコードの骨格。**説明文・画像は持たない**(規約対策)。"""
    return {
        "chain": chain,
        "product_id": pid,
        "name": name,
        "category": None,
        "fair": None,
        "price": None,
        "price_excl_tax": None,
        "price_max": None,
        "price_note": None,
        "price_variants": None,
        "launch_date": None,
        "launch_date_source": None,
        "news_title": None,
        "news_url": None,
        "news_date": None,
        "listed_at": None,
        "planned_end_text": None,
        "limited_kind": None,
        "stores_note": None,
        "official_url": None,
        "first_seen_at": now,
        "last_seen_at": today,
        "status": "on_sale",
        "ended_observed_at": None,
        "missed_runs": 0,
        "price_history": [],
        "launch_search_runs": 0,
    }



def set_initial_price(product: dict, price: int | None, price_max: int | None, today: str) -> None:
    product["price_history"] = []
    product["price"] = None
    product["price_max"] = None
    record_price(product, price, price_max, today)


# ---- 発売日の照合(見出し・お知らせ・プレスリリース) -----------------------------

LAUNCH_WINDOW_BEFORE_DAYS = 120
LAUNCH_WINDOW_AFTER_DAYS = 14
LAUNCH_SEARCH_RUNS_MAX = 3  # 本文の取得まで使う探索は、新しい商品について最大この回数


def launch_name_keys(name: str) -> list[str]:
    """発売日の照合に使う、商品名の正規化キー(全体と、末尾の（単品）（ホット）・先頭の【店舗限定】を除いたもの)。
    短すぎるキー(4文字以下)は誤爆するので使わない。"""
    keys = []
    variants = [name,
                re.sub(r"[（(][^）)]*[）)]\s*$", "", name),
                re.sub(r"^【[^】]*】", "", name),
                re.sub(r"ミニサイズ", "", re.sub(r"[（(][^）)]*[）)]\s*$", "", name))]
    for v in variants:
        k = parsers.normalize_name(v)
        if len(k) >= 5 and k not in keys:
            keys.append(k)
    return keys


def raw_name_variants(name: str) -> list[str]:
    """本文の中で商品名を探すための、NFKC化した商品名の候補(全体・末尾の括弧なし・先頭の【】なし)。"""
    n = unicodedata.normalize("NFKC", name)
    out = []
    for v in (n, re.sub(r"[(][^)]*[)]\s*$", "", n), re.sub(r"^\[[^\]]*\]", "", re.sub(r"^【[^】]*】", "", n))):
        v = v.strip()
        if len(v) >= 4 and v not in out:
            out.append(v)
    return out


def competitor_keys(name: str, all_names: list[str]) -> list[str]:
    """同じチェーンの他の商品のうち、この商品の名前(正規化)を丸ごと含む、より長い名前のキー。
    「ジョイフルメドレー ティー」が「ジョイフルメドレー ティー ラテ」の記事に誤って結びつくのを防ぐために使う。"""
    mine = launch_name_keys(name)
    out: list[str] = []
    for other in all_names:
        if other == name:
            continue
        for ok in launch_name_keys(other):
            if any(m in ok and m != ok for m in mine) and ok not in out:
                out.append(ok)
    return out


def count_standalone(hay: str, key: str, competitors: list[str]) -> int:
    """hay の中の key の出現数から、より長い別商品の名前の中での出現を引いた数。"""
    n = hay.count(key)
    for c in competitors:
        if key in c:
            n -= hay.count(c) * c.count(key)
    return n


def find_launch(name: str, sources: list[dict], ref: str, all_names: list[str] | None = None) -> dict | None:
    """sources=[{title, text, date, url}] から、商品名が出てくる記事を探し、その発売日を返す。

    date が ref の前 LAUNCH_WINDOW_BEFORE_DAYS 日〜後 LAUNCH_WINDOW_AFTER_DAYS 日の記事だけを対象にする。
    発売日は記事の見出しから、無ければ本文の(商品名の近く→先頭の)「M月D日より」から取る。見つからなければ None。"""
    keys = launch_name_keys(name)
    if not keys or not ref:
        return None
    try:
        ref_d = datetime.date.fromisoformat(ref)
    except ValueError:
        return None
    comp = competitor_keys(name, all_names or [])
    lo = ref_d - datetime.timedelta(days=LAUNCH_WINDOW_BEFORE_DAYS)
    hi = ref_d + datetime.timedelta(days=LAUNCH_WINDOW_AFTER_DAYS)
    for s in sources:
        try:
            d = datetime.date.fromisoformat(s.get("date") or "")
        except ValueError:
            continue
        if not (lo <= d <= hi):
            continue
        title_n = parsers.normalize_name(s.get("title"))
        text = s.get("text") or ""
        text_n = parsers.normalize_name(text)
        in_title = any(count_standalone(title_n, k, comp) > 0 for k in keys)
        in_text = any(count_standalone(text_n, k, comp) > 0 for k in keys)
        if not (in_title or in_text):
            continue
        launch = parsers.launch_date_from_text(s.get("title"), d) if in_title else None
        via = "title"
        if launch is None and text:
            via = "body"
            # 商品名の近くの日付を優先し、無ければ本文の最初の発売日
            text_k = unicodedata.normalize("NFKC", text)
            dates = parsers.launch_dates_in_text(text_k, d)
            for v in raw_name_variants(name):
                pos = text_k.find(v)
                if pos >= 0 and dates:
                    near = min(dates, key=lambda x: abs(x[0] - pos))
                    if abs(near[0] - pos) <= 60:
                        launch = near[1]
                    break
            if launch is None and dates:
                launch = dates[0][1]
        if launch:
            return {"launch_date": launch, "title": s.get("title"), "url": s.get("url"), "date": s.get("date"), "via": via}
    return None


def apply_launch(product: dict, hit: dict, source: str) -> None:
    """発売日を入れる。商品名が見出しに無く本文でだけ見つかった記事は「_body」を付けて区別する
    (1本の記事が複数の商品を扱う・成分名として商品名が出る、などで商品ごとの発売日とずれることがあるため)。"""
    product["launch_date"] = hit["launch_date"]
    product["launch_date_source"] = source + ("_body" if hit.get("via") == "body" else "")
    product["news_title"] = hit["title"]
    product["news_url"] = hit["url"]
    product["news_date"] = hit["date"]


def launch_ref(product: dict) -> str:
    return product.get("listed_at") or (product.get("first_seen_at") or "")[:10]


def needs_launch(product: dict) -> bool:
    return product.get("launch_date") is None and product.get("status") != "ended"


class PressSources:
    """発売日の照合に使う記事の一覧。必要になるまで取らない(遅延取得)。取得に失敗したら空のまま続行。"""

    def __init__(self, loader):
        self.loader = loader
        self.items: list[dict] | None = None

    def get(self) -> list[dict]:
        if self.items is None:
            try:
                self.items = self.loader()
            except BlockedError:
                raise
            except Exception as e:  # noqa: BLE001
                print(f"[warn] 発売日の照合元の取得に失敗(発売日なしで続行): {e}", file=sys.stderr)
                self.items = []
        return self.items


# ---------------------------------------------------------------------------
# デニーズ
# ---------------------------------------------------------------------------

DENNYS_BASE = parsers.DENNYS_BASE
DENNYS_STORES_NOTE = "一部の店舗(新宿西口店・赤坂駅前店・浅草雷門店など)では、価格や取り扱いが異なります"


def crawl_dennys(getter, pending: dict, stats: dict, today: str | None = None) -> None:
    """デニーズ: /menu/ のフェア欄 → 各フェアページ(毎回リンクをたどる。ページ名は固定でない)。
    フェアページから価格が1件も取れない回、フェア欄が無い・0件の回、どれかのフェアページが取れない回は
    「一覧が不完全(構造変更の疑い)」として終了判定をしない。
    開始日は /news/(HTML)の見出し・リード文の「10月28日（水）販売開始」を、商品名またはフェア名で照合できたときだけ使う
    (PDFは読まない)。取れなければ記録開始日。"""
    chain = "dennys"
    run = Run(chain, pending, stats, today)
    st, today, now = run.st, run.today, run.now
    robots = Robots(getter, chain, st)
    complete = True
    entries: dict[str, dict] = {}
    try:
        if not robots.allowed(DENNYS_BASE, parsers.DENNYS_MENU_PATH):
            print("[skip] dennys: robots.txtでDisallow", file=sys.stderr)
            return
        menu = getter(chain, DENNYS_BASE + parsers.DENNYS_MENU_PATH)
        st["list_requests"] += 1
        try:
            fairs = parsers.parse_dennys_fair_links(menu)
        except ValueError as e:
            print(f"[warn] dennys {e}", file=sys.stderr)
            return
        if not fairs:
            print("[warn] dennys: フェアが0件(構造変更の疑い。この回は終了判定をしない)", file=sys.stderr)
            return
        for fair in fairs:
            path = fair["path"]
            if not robots.allowed(DENNYS_BASE, path):
                complete = False
                continue
            try:
                html = getter(chain, DENNYS_BASE + path)
                st["list_requests"] += 1
                page = parsers.parse_dennys_fair_page(html, path)
            except BlockedError:
                raise
            except Exception as e:  # noqa: BLE001  取得失敗・構造変更
                print(f"[warn] dennys フェア {path}: {e}", file=sys.stderr)
                complete = False
                continue
            if not page["items"]:
                print(f"[warn] dennys フェア {path}: 価格が1件も取れない(構造変更の疑い)", file=sys.stderr)
                complete = False
                continue
            for it in page["items"]:
                if it["pid"] in entries:
                    continue
                entries[it["pid"]] = {
                    "pid": it["pid"], "name": it["name"], "price": it["price"], "price_max": None,
                    "price_excl_tax": it["price_excl_tax"], "fair": page["title"] or fair["title"],
                    "fair_path": path,
                    "official_url": DENNYS_BASE + (it["link"] or path),
                }
    except BlockedError as e:
        run.block("list", e)
        return
    except Exception as e:  # noqa: BLE001
        print(f"[warn] dennys 一覧取得失敗: {e}", file=sys.stderr)
        return

    all_names = [e["name"] for e in entries.values()]

    def news_loader():
        if not robots.allowed(DENNYS_BASE, parsers.DENNYS_NEWS_PATH):
            return []
        got = parsers.parse_dennys_news(getter(chain, DENNYS_BASE + parsers.DENNYS_NEWS_PATH))
        st["detail_requests"] += 1
        return [{"title": n["title"], "text": n["text"], "date": n["date"], "url": n["url"]} for n in got]

    news = PressSources(news_loader)

    def build(e):
        p = base_product(chain, e["pid"], e["name"], now, today)
        p["fair"] = e["fair"]
        p["limited_kind"] = "フェア"
        p["price_excl_tax"] = e["price_excl_tax"]
        p["price_note"] = "税込。税抜は公式サイトの表示"
        set_initial_price(p, e["price"], None, today)
        p["official_url"] = e["official_url"]
        p["stores_note"] = DENNYS_STORES_NOTE
        p["source_list"] = [f"www.dennys.jp{e['fair_path']}"]
        return p

    def refresh(p, e):
        p["fair"] = e["fair"]
        p["price_excl_tax"] = e["price_excl_tax"]
        if e["official_url"] != p.get("official_url"):
            p["official_url"] = e["official_url"]

    def enrich(p, e, is_new):
        if not (needs_launch(p) and (is_new or int(p.get("launch_search_runs") or 0) < LAUNCH_SEARCH_RUNS_MAX)):
            return
        hit = find_launch(p["name"], news.get(), launch_ref(p), all_names)
        base = re.split(r"[～〜~]", p["name"])[0]  # 「蜜いものザ・サンデー～紅天使使用」→ 見出しは副題なしで書かれる
        if hit is None and base != p["name"]:
            hit = find_launch(base, news.get(), launch_ref(p), all_names)
        if hit is None and p.get("fair"):
            hit = find_launch(p["fair"], news.get(), launch_ref(p), [])
            if hit:
                hit["via"] = "fair"  # 商品名でなくフェア名での照合(本文由来と同じく「ずれることがある」扱い)
        if hit:
            apply_launch(p, hit, "official_news")
            if hit.get("via") == "fair":
                p["launch_date_source"] = "official_news_fair"
        else:
            p["launch_search_runs"] = int(p.get("launch_search_runs") or 0) + 1

    run.finish(entries, complete, build, refresh, enrich)


# ---------------------------------------------------------------------------
# ジョナサン
# ---------------------------------------------------------------------------

JONATHAN_BASE = parsers.JONATHAN_BASE
JONATHAN_STORES_NOTE = "店舗により価格や取り扱いが異なる場合があります"


def crawl_jonathan(getter, pending: dict, stats: dict, today: str | None = None) -> None:
    """ジョナサン: フェアページ(/jonathan/menu/fair/index.html)と、メニュートップ(/jonathan/menu/)のおすすめスライドから
    辿れる他のページ(config の jonathan_skip_slugs は除く)の img の alt から、商品名と価格を取る。
    巡回するページ数は jonathan_max_pages まで。収まらないとき・メニュートップが取れないとき・
    フェアページ(または既に商品が載っていたページ)から価格が取れないときは「一覧が不完全」として終了判定をしない。
    開始日は記録開始日(プレスリリースは取らない)。"""
    chain = "jonathan"
    run = Run(chain, pending, stats, today)
    st, today, now = run.st, run.today, run.now
    robots = Robots(getter, chain, st)
    skip = set(CONFIG.get("jonathan_skip_slugs") or [])
    exclude = {parsers.normalize_name(n) for n in (CONFIG.get("jonathan_exclude_names") or [])}
    max_pages = int(CONFIG.get("jonathan_max_pages", 3))
    complete = True
    entries: dict[str, dict] = {}
    names_seen: set[str] = set()
    anchor = parsers.JONATHAN_FAIR_PATH
    known_urls = {p.get("official_url") for p in load_chain_products(chain) if p.get("status") == "on_sale"}
    try:
        if not robots.allowed(JONATHAN_BASE, parsers.JONATHAN_MENU_PATH):
            print("[skip] jonathan: robots.txtでDisallow", file=sys.stderr)
            return
        pages = [anchor]
        try:
            top = getter(chain, JONATHAN_BASE + parsers.JONATHAN_MENU_PATH)
            st["list_requests"] += 1
            for link in parsers.parse_jonathan_menu_links(top):
                if link["slug"] in skip or link["path"] in pages:
                    continue
                pages.append(link["path"])
        except BlockedError:
            raise
        except Exception as e:  # noqa: BLE001  メニュートップが読めないと、他のフェアページを見落とす
            print(f"[warn] jonathan メニュートップ: {e}", file=sys.stderr)
            complete = False
        if len(pages) > max_pages:
            print(f"[warn] jonathan: 巡回対象のページが{len(pages)}件で上限{max_pages}を超える。超えた分は見ない", file=sys.stderr)
            pages = pages[:max_pages]
            complete = False
        for path in pages:
            slug = path.strip("/").split("/")[-2]
            if not robots.allowed(JONATHAN_BASE, path):
                complete = False
                continue
            url = JONATHAN_BASE + path
            try:
                html = getter(chain, url)
                st["list_requests"] += 1
                page = parsers.parse_jonathan_fair_page(html, slug)
            except BlockedError:
                raise
            except Exception as e:  # noqa: BLE001
                print(f"[warn] jonathan {path}: {e}", file=sys.stderr)
                complete = False
                continue
            if not page["items"]:
                print(f"[warn] jonathan {path}: 価格が1件も取れない", file=sys.stderr)
                if path == anchor or url in known_urls:
                    complete = False  # フェアページ、または商品が載っていたページが空になったら構造変更の疑い
                continue
            for it in page["items"]:
                key = parsers.normalize_name(it["name"])
                if key in exclude or key in names_seen:
                    continue  # 常設の付け合わせ(ドリンクバーセット等)と、複数ページに載る同名商品
                names_seen.add(key)
                entries[it["pid"]] = {
                    "pid": it["pid"], "name": it["name"], "price": it["price"], "price_max": None,
                    "price_excl_tax": it["price_excl_tax"], "fair": page["title"], "official_url": url,
                }
    except BlockedError as e:
        run.block("list", e)
        return
    except Exception as e:  # noqa: BLE001
        print(f"[warn] jonathan 一覧取得失敗: {e}", file=sys.stderr)
        return

    def build(e):
        p = base_product(chain, e["pid"], e["name"], now, today)
        p["fair"] = e["fair"]
        p["limited_kind"] = "フェア"
        p["price_excl_tax"] = e["price_excl_tax"]
        p["price_note"] = "税込。税抜は公式サイトの表示"
        set_initial_price(p, e["price"], None, today)
        p["official_url"] = e["official_url"]
        p["stores_note"] = JONATHAN_STORES_NOTE
        p["source_list"] = [e["official_url"].replace("https://", "")]
        return p

    def refresh(p, e):
        p["fair"] = e["fair"]
        p["price_excl_tax"] = e["price_excl_tax"]

    run.finish(entries, complete, build, refresh)


# ---------------------------------------------------------------------------
# ビッグボーイ
# ---------------------------------------------------------------------------

BIGBOY_BASE = parsers.BIGBOY_BASE
BIGBOY_STORES_NOTE = "一部店舗では販売内容や価格が異なります"


def crawl_bigboy(getter, pending: dict, stats: dict, today: str | None = None) -> None:
    """ビッグボーイ: グランドメニュー(/menu/grand/)の「期間限定メニュー」欄から商品名・価格(¥表記)を取る。
    商品ごとのページは無いので、出典はグランドメニューのページ自体。フェアごとの区別は公式メニューに
    無いため、フェア名は欄の名前(期間限定メニュー)で統一する。欄が無い・価格が1件も取れない回は
    「一覧が不完全(構造変更の疑い)」として終了判定をしない。
    開始日はフェア情報(/fair/)から辿れるニュース記事(掲載日つき)の見出し・本文を、商品名で
    照合できたときだけ使う(年は記事の掲載日から補う。find_launch が持つ)。フェア記事は商品名を
    列挙しないことが多いので、取れない商品は記録開始日になる。"""
    chain = "bigboy"
    run = Run(chain, pending, stats, today)
    st, today, now = run.st, run.today, run.now
    robots = Robots(getter, chain, st)
    complete = True
    entries: dict[str, dict] = {}
    try:
        if not robots.allowed(BIGBOY_BASE, parsers.BIGBOY_MENU_PATH):
            print("[skip] bigboy: robots.txtでDisallow", file=sys.stderr)
            return
        html = getter(chain, BIGBOY_BASE + parsers.BIGBOY_MENU_PATH)
        st["list_requests"] += 1
        try:
            page = parsers.parse_bigboy_grand_menu(html)
        except ValueError as e:
            print(f"[warn] bigboy {e}", file=sys.stderr)
            return
        if not page["items"]:
            print("[warn] bigboy: 期間限定メニューから価格が1件も取れない(構造変更の疑い。この回は終了判定をしない)",
                  file=sys.stderr)
            return
        for it in page["items"]:
            if it["pid"] in entries:
                continue
            entries[it["pid"]] = {
                "pid": it["pid"], "name": it["name"], "price": it["price"], "price_max": it["price_max"],
                "price_excl_tax": it["price_excl_tax"], "price_variants": it["price_variants"],
                "fair": page["title"], "official_url": BIGBOY_BASE + parsers.BIGBOY_MENU_PATH,
            }
    except BlockedError as e:
        run.block("list", e)
        return
    except Exception as e:  # noqa: BLE001
        print(f"[warn] bigboy 一覧取得失敗: {e}", file=sys.stderr)
        return

    all_names = [e["name"] for e in entries.values()]
    max_articles = int(CONFIG.get("bigboy_news_max_articles", 8))

    def news_loader():
        if not robots.allowed(BIGBOY_BASE, parsers.BIGBOY_FAIR_PATH):
            return []
        links = parsers.parse_bigboy_fair_links(getter(chain, BIGBOY_BASE + parsers.BIGBOY_FAIR_PATH))
        st["detail_requests"] += 1
        out = []
        for link in links[:max_articles]:
            url = BIGBOY_BASE + link["path"]
            try:
                art_html = getter(chain, url)
                st["detail_requests"] += 1
            except BlockedError:
                raise
            except Exception as e:  # noqa: BLE001  記事1本の失敗は開始日なしで続行
                print(f"[warn] bigboy ニュース {link['path']}: {e}", file=sys.stderr)
                continue
            art = parsers.parse_bigboy_news_article(art_html, url)
            if art:
                out.append(art)
        return out

    news = PressSources(news_loader)

    def build(e):
        p = base_product(chain, e["pid"], e["name"], now, today)
        p["fair"] = e["fair"]
        p["limited_kind"] = "フェア"
        p["price_excl_tax"] = e["price_excl_tax"]
        p["price_note"] = "税込。税抜は公式サイトの表示"
        p["price_variants"] = e["price_variants"] or None
        set_initial_price(p, e["price"], e["price_max"], today)
        p["official_url"] = e["official_url"]
        p["stores_note"] = BIGBOY_STORES_NOTE
        p["source_list"] = ["www.bigboyjapan.co.jp" + parsers.BIGBOY_MENU_PATH]
        return p

    def refresh(p, e):
        p["fair"] = e["fair"]
        p["price_excl_tax"] = e["price_excl_tax"]
        p["price_variants"] = e["price_variants"] or None

    def enrich(p, e, is_new):
        if not (needs_launch(p) and (is_new or int(p.get("launch_search_runs") or 0) < LAUNCH_SEARCH_RUNS_MAX)):
            return
        hit = find_launch(p["name"], news.get(), launch_ref(p), all_names)
        base = re.split(r"[～〜~]", p["name"])[0]  # デニーズと同じく、副題(～以降)を落とした名前でも照合する
        if hit is None and base != p["name"]:
            hit = find_launch(base, news.get(), launch_ref(p), all_names)
        # フェア名での照合はしない。ビッグボーイのフェア名は全商品共通の欄名(期間限定メニュー)なので、
        # その語を含む記事があると全商品に同じ開始日が付いてしまう(モルのレビュー指摘、2026-11-23)
        if hit:
            apply_launch(p, hit, "official_news")
        else:
            p["launch_search_runs"] = int(p.get("launch_search_runs") or 0) + 1

    run.finish(entries, complete, build, refresh, enrich)


# ---------------------------------------------------------------------------
# ココス
# ---------------------------------------------------------------------------

COCOS_BASE = parsers.COCOS_BASE
COCOS_STORES_NOTE = "一部の店舗で取扱商品、販売時間帯、価格が異なる場合があります"


class CocosRobots(Robots):
    """ココスは存在しないパス(robots.txt を含む)に 403 でエラーページを返すサーバー仕様で、
    robots.txt の取得が BlockedError になる(2026-11-23 確認)。RFC 9309 では 4xx(429を除く)は
    「robots.txt が無い」扱いでよいので、その場合だけ制限なしとして扱う。429・チャレンジ・
    それ以外の BlockedError はそのまま止める。実際のページ取得でブロックされた場合は
    そちらの BlockedError で止まる(共通の Robots は触らない)。"""

    def allowed(self, base: str, path: str) -> bool:
        try:
            return super().allowed(base, path)
        except BlockedError as e:
            m = re.match(r"HTTP (\d{3})", str(e))
            code = int(m.group(1)) if m else None
            if code is None or not 400 <= code < 500 or code == 429:
                raise
            self.st["list_requests"] += 1  # 403 でもリクエストは発生している
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(["User-agent: *", "Allow: /"])
            self.parsers[base] = rp
            return True


def crawl_cocos(getter, pending: dict, stats: dict, today: str | None = None) -> None:
    """ココス: フェアページ(/menu/fair/)の「h2(フェア名)+メニュー一覧」から商品名・価格(¥表記)を取る。
    フェアの組が無い・どれかのフェアが0件・価格が1件も取れない回は「一覧が不完全(構造変更の疑い)」として
    終了判定をしない。開始日は /news/<年>/menu/ の見出しの「【11月19日(木)開始】」を、商品名またはフェア名で
    照合できたときだけ使う。取れなければ記録開始日。ニュースは当年分だけなので、年をまたぐと前年の
    フェアの開始日は拾えない(デニーズと同じ限界)。"""
    chain = "cocos"
    run = Run(chain, pending, stats, today)
    st, today, now = run.st, run.today, run.now
    robots = CocosRobots(getter, chain, st)
    exclude_words = [w for w in (CONFIG.get("cocos_exclude_words") or []) if w]
    complete = True
    entries: dict[str, dict] = {}
    try:
        if not robots.allowed(COCOS_BASE, parsers.COCOS_FAIR_PATH):
            print("[skip] cocos: robots.txtでDisallow", file=sys.stderr)
            return
        html = getter(chain, COCOS_BASE + parsers.COCOS_FAIR_PATH)
        st["list_requests"] += 1
        try:
            sections = parsers.parse_cocos_fair_page(html)
        except ValueError as e:
            print(f"[warn] cocos {e}", file=sys.stderr)
            return
        for sec in sections:
            if not sec["items"]:
                print(f"[warn] cocos フェア「{sec['title']}」: 価格が1件も取れない(構造変更の疑い)", file=sys.stderr)
                complete = False
                continue
            for it in sec["items"]:
                if any(w in it["name"] for w in exclude_words):
                    continue  # 「追加〜」等のトッピングは単品の商品ではないので記録しない
                if it["pid"] in entries:
                    continue
                entries[it["pid"]] = {
                    "pid": it["pid"], "name": it["name"], "price": it["price"], "price_max": None,
                    "price_excl_tax": it["price_excl_tax"], "fair": sec["title"],
                    "official_url": COCOS_BASE + (it["link"] or parsers.COCOS_FAIR_PATH),
                }
        if not entries:
            print("[warn] cocos: 商品が0件(構造変更の疑い。この回は終了判定をしない)", file=sys.stderr)
            return
    except BlockedError as e:
        run.block("list", e)
        return
    except Exception as e:  # noqa: BLE001
        print(f"[warn] cocos 一覧取得失敗: {e}", file=sys.stderr)
        return

    all_names = [e["name"] for e in entries.values()]
    news_path = f"/news/{today[:4]}/menu/"

    def news_loader():
        if not robots.allowed(COCOS_BASE, news_path):
            return []
        got = parsers.parse_cocos_news(getter(chain, COCOS_BASE + news_path))
        st["detail_requests"] += 1
        return [{"title": n["title"], "text": n["text"], "date": n["date"], "url": n["url"]} for n in got]

    news = PressSources(news_loader)

    def build(e):
        p = base_product(chain, e["pid"], e["name"], now, today)
        p["fair"] = e["fair"]
        p["limited_kind"] = "フェア"
        p["price_excl_tax"] = e["price_excl_tax"]
        p["price_note"] = "税込。税抜は公式サイトの表示"
        set_initial_price(p, e["price"], None, today)
        p["official_url"] = e["official_url"]
        p["stores_note"] = COCOS_STORES_NOTE
        p["source_list"] = ["www.cocos-jpn.co.jp" + parsers.COCOS_FAIR_PATH]
        return p

    def refresh(p, e):
        p["fair"] = e["fair"]
        p["price_excl_tax"] = e["price_excl_tax"]
        if e["official_url"] != p.get("official_url"):
            p["official_url"] = e["official_url"]

    def enrich(p, e, is_new):
        if not (needs_launch(p) and (is_new or int(p.get("launch_search_runs") or 0) < LAUNCH_SEARCH_RUNS_MAX)):
            return
        hit = find_launch(p["name"], news.get(), launch_ref(p), all_names)
        base = re.split(r"[～〜~]", p["name"])[0]  # デニーズと同じく、副題(～以降)を落とした名前でも照合する
        if hit is None and base != p["name"]:
            hit = find_launch(base, news.get(), launch_ref(p), all_names)
        if hit is None and p.get("fair"):
            hit = find_launch(p["fair"], news.get(), launch_ref(p), [])
            if hit:
                hit["via"] = "fair"  # 商品名でなくフェア名での照合(本文由来と同じく「ずれることがある」扱い)
        if hit:
            apply_launch(p, hit, "official_news")
            if hit.get("via") == "fair":
                p["launch_date_source"] = "official_news_fair"
        else:
            p["launch_search_runs"] = int(p.get("launch_search_runs") or 0) + 1

    run.finish(entries, complete, build, refresh, enrich)


# ---------------------------------------------------------------------------
# ジョイフル
# ---------------------------------------------------------------------------

JOYFULL_BASE = parsers.JOYFULL_BASE
JOYFULL_STORES_NOTE = "関東エリア店舗(東京都・埼玉県・千葉県・群馬県・栃木県・茨城県・福島県)では、メニューや価格が異なる場合があります"


def crawl_joyfull(getter, pending: dict, stats: dict, today: str | None = None) -> None:
    """ジョイフル: 「季節・期間限定」の一覧(/menu?category=19)から商品名・価格(全角￥の税抜＋税込併記)を、
    商品ページ(/menu/<数値ID>)のパンくずからフェア名を取る。識別キーは商品ページの数値ID。
    商品ページは、まだ記録していない商品と、フェア名が保存されていない既存商品だけ取る
    (記録済みでフェア名のある商品は保存済みのフェア名を使う。フェア名はほぼ変わらないので、
    毎日の取得を減らし、件数が増えたときに上限へ当たって不完全扱いになる詰まりも防ぐ)。
    一覧の枠が無い・0件の回、表示件数(該当件数)より取れた商品が少ない回、取るべき商品ページが
    取れない・パンくずが読めない回は「一覧が不完全(構造変更の疑い)」として終了判定をしない。
    開始日は、まず商品名の先頭の告知「【YYYY年M月D日(曜)H時より販売】」(年まで含む一次情報)、
    次にお知らせ(メニュー分類)の見出しを商品名・フェア名で照合できたときだけ使う。取れなければ記録開始日。"""
    chain = "joyfull"
    run = Run(chain, pending, stats, today)
    st, today, now = run.st, run.today, run.now
    robots = Robots(getter, chain, st)
    complete = True
    entries: dict[str, dict] = {}
    try:
        if not robots.allowed(JOYFULL_BASE, parsers.JOYFULL_LIST_PATH):
            print("[skip] joyfull: robots.txtでDisallow", file=sys.stderr)
            return
        html = getter(chain, JOYFULL_BASE + parsers.JOYFULL_LIST_PATH)
        st["list_requests"] += 1
        try:
            page = parsers.parse_joyfull_category(html)
        except ValueError as e:
            print(f"[warn] joyfull {e}", file=sys.stderr)
            return
        if not page["items"]:
            print("[warn] joyfull: 商品が0件(構造変更の疑い。この回は終了判定をしない)", file=sys.stderr)
            return
        if page["declared_count"] is not None and len(page["items"]) < page["declared_count"]:
            print(f"[warn] joyfull: 表示{page['declared_count']}件のうち{len(page['items'])}件しか価格が取れない"
                  "(構造変更の疑い)", file=sys.stderr)
            complete = False
        for it in page["items"]:
            url = JOYFULL_BASE + it["link"]
            saved = load_product(chain, it["pid"])
            if saved is not None and saved.get("fair"):
                # 記録済みでフェア名も保存されている商品は、商品ページを取り直さない
                # (モルのレビュー指摘、2026-11-23)
                fair = saved["fair"]
            else:
                if not robots.allowed(JOYFULL_BASE, it["link"]):
                    complete = False
                    continue
                try:
                    detail = getter(chain, url)
                    st["detail_requests"] += 1
                    fair = parsers.parse_joyfull_detail(detail)["fair"]
                except BlockedError:
                    raise
                except Exception as e:  # noqa: BLE001  取得失敗・構造変更
                    print(f"[warn] joyfull 商品 {it['link']}: {e}", file=sys.stderr)
                    complete = False
                    continue
            entries[it["pid"]] = {
                "pid": it["pid"], "name": it["name"], "price": it["price"], "price_max": None,
                "price_excl_tax": it["price_excl_tax"], "fair": fair,
                "listed_launch": it["listed_launch"], "official_url": url,
            }
    except BlockedError as e:
        run.block("list", e)
        return
    except Exception as e:  # noqa: BLE001
        print(f"[warn] joyfull 一覧取得失敗: {e}", file=sys.stderr)
        return

    all_names = [e["name"] for e in entries.values()]

    def news_loader():
        if not robots.allowed(JOYFULL_BASE, parsers.JOYFULL_NEWS_PATH):
            return []
        got = parsers.parse_joyfull_news(getter(chain, JOYFULL_BASE + parsers.JOYFULL_NEWS_PATH))
        st["detail_requests"] += 1
        return [{"title": n["title"], "text": "", "date": n["date"], "url": n["url"]} for n in got]

    news = PressSources(news_loader)

    def build(e):
        p = base_product(chain, e["pid"], e["name"], now, today)
        p["fair"] = e["fair"]
        p["limited_kind"] = "フェア"
        p["price_excl_tax"] = e["price_excl_tax"]
        p["price_note"] = "税込。税抜は公式サイトの表示"
        set_initial_price(p, e["price"], None, today)
        p["official_url"] = e["official_url"]
        p["stores_note"] = JOYFULL_STORES_NOTE
        p["source_list"] = ["www.joyfull.co.jp/menu?category=19"]
        return p

    def refresh(p, e):
        if e["fair"]:
            p["fair"] = e["fair"]
        if e["name"] and p["name"] != e["name"]:
            # 識別キーは数値IDで安定しているので、名前は一覧の表示に追随させる
            # (「」の除去など、記録済みの名前の表記も次の巡回でそろう)
            p["name"] = e["name"]
        p["price_excl_tax"] = e["price_excl_tax"]

    def enrich(p, e, is_new):
        if not (needs_launch(p) and (is_new or int(p.get("launch_search_runs") or 0) < LAUNCH_SEARCH_RUNS_MAX)):
            return
        if e.get("listed_launch"):
            # 商品名の先頭の告知(公式の一覧の表示そのもの)が最も確かな一次情報
            p["launch_date"] = e["listed_launch"]
            p["launch_date_source"] = "official_menu"
            return
        hit = find_launch(p["name"], news.get(), launch_ref(p), all_names)
        if hit is None and p.get("fair"):
            hit = find_launch(p["fair"], news.get(), launch_ref(p), [])
            if hit:
                hit["via"] = "fair"  # フェア名での照合(商品ごとの開始日とずれることがある扱い)
        if hit:
            apply_launch(p, hit, "official_news")
            if hit.get("via") == "fair":
                p["launch_date_source"] = "official_news_fair"
        else:
            p["launch_search_runs"] = int(p.get("launch_search_runs") or 0) + 1

    run.finish(entries, complete, build, refresh, enrich)


# ステーキのどん
# ---------------------------------------------------------------------------

STEAKDON_BASE = parsers.STEAKDON_BASE


def crawl_steakdon(getter, pending: dict, stats: dict, today: str | None = None) -> None:
    """ステーキのどん: メニューの「フェアメニュー」カテゴリページ
    (fmenu_list.html?fmenu_categ_id=94)の商品名・価格を取る。バナー側のフェアページ
    (campaign_fair.html)は価格が画像の中だけなので巡回しない。商品詳細ページは一覧と同じ
    名前・価格しか載っていないため取らない(識別キーは一覧のリンクの fmenu_item_id)。
    見出し・一覧の枠が無い回、価格が1件も取れない回は「一覧が不完全(構造変更の疑い)」として終了判定をしない。
    開始日は /news.html の見出しを商品名で照合できたときだけ使う(フェア名は商品ごとに
    一覧へ載らないため、フェア名での照合はしない)。取れなければ記録開始日。
    終了はカテゴリページからの消失で判定する(共通エンジン)。"""
    chain = "steakdon"
    run = Run(chain, pending, stats, today)
    st, today, now = run.st, run.today, run.now
    robots = Robots(getter, chain, st)
    entries: dict[str, dict] = {}
    try:
        if not robots.allowed(STEAKDON_BASE, parsers.STEAKDON_FAIR_LIST_PATH):
            print("[skip] steakdon: robots.txtでDisallow", file=sys.stderr)
            return
        html = getter(chain, STEAKDON_BASE + parsers.STEAKDON_FAIR_LIST_PATH)
        st["list_requests"] += 1
        try:
            page = parsers.parse_steakdon_fair_list(html)
        except ValueError as e:
            print(f"[warn] steakdon {e}", file=sys.stderr)
            return
        if not page["items"]:
            print("[warn] steakdon: 価格が1件も取れない(構造変更の疑い。この回は終了判定をしない)", file=sys.stderr)
            return
        for it in page["items"]:
            if it["pid"] in entries:
                continue
            entries[it["pid"]] = {
                "pid": it["pid"], "name": it["name"], "price": it["price"], "price_max": it["price_max"],
                "price_excl_tax": it["price_excl_tax"], "price_variants": it["price_variants"],
                "fair": page["title"], "official_url": STEAKDON_BASE + it["link"], "note": it["note"],
            }
    except BlockedError as e:
        run.block("list", e)
        return
    except Exception as e:  # noqa: BLE001
        print(f"[warn] steakdon 一覧取得失敗: {e}", file=sys.stderr)
        return

    all_names = [e["name"] for e in entries.values()]

    def news_loader():
        if not robots.allowed(STEAKDON_BASE, parsers.STEAKDON_NEWS_PATH):
            return []
        got = parsers.parse_steakdon_news(getter(chain, STEAKDON_BASE + parsers.STEAKDON_NEWS_PATH))
        st["detail_requests"] += 1
        return [{"title": n["title"], "text": n["text"], "date": n["date"], "url": n["url"]} for n in got]

    news = PressSources(news_loader)

    def build(e):
        p = base_product(chain, e["pid"], e["name"], now, today)
        p["fair"] = e["fair"]
        p["limited_kind"] = "フェア"
        p["price_excl_tax"] = e["price_excl_tax"]
        p["price_note"] = "税込。税抜は公式サイトの表示"
        p["price_variants"] = e["price_variants"]
        set_initial_price(p, e["price"], e["price_max"], today)
        p["official_url"] = e["official_url"]
        p["stores_note"] = e["note"]
        p["source_list"] = ["www.steak-don.jp" + parsers.STEAKDON_FAIR_LIST_PATH]
        return p

    def refresh(p, e):
        p["fair"] = e["fair"]
        p["price_excl_tax"] = e["price_excl_tax"]
        p["price_variants"] = e["price_variants"]
        p["stores_note"] = e["note"]
        if e["official_url"] != p.get("official_url"):
            p["official_url"] = e["official_url"]

    def enrich(p, e, is_new):
        if not (needs_launch(p) and (is_new or int(p.get("launch_search_runs") or 0) < LAUNCH_SEARCH_RUNS_MAX)):
            return
        hit = find_launch(p["name"], news.get(), launch_ref(p), all_names)
        if hit:
            apply_launch(p, hit, "official_news")
        else:
            p["launch_search_runs"] = int(p.get("launch_search_runs") or 0) + 1

    run.finish(entries, True, build, refresh, enrich)


# ---------------------------------------------------------------------------
# 実行
# ---------------------------------------------------------------------------

def collect_problems(stats: dict[str, dict]) -> dict[str, list[str]]:
    """この実行で問題があったチェーンを種別ごとに集める(通知用)。

    list_failed は「一覧の取得・解析が完全には成功しなかった」チェーン。取得失敗・商品0件(構造変更の疑い)・
    急減・robots.txtで弾いた一覧など、list_ok が False で終わった経路すべてを含む。
    ただし、ブロック(blocked)・例外(errors)・歯止め(suspected_restructure。既存の「保留」通知がある)は
    重複させないため除く。詳細ページ単発の失敗(stats["failed"])は一時的なことが多く翌日に自動で再試行されるので、
    問題には数えない。"""
    return {
        "blocked": [c for c, s in stats.items() if s.get("blocked")],
        "list_failed": [c for c, s in stats.items()
                        if not s.get("list_ok") and not s.get("blocked") and not s.get("error")
                        and not s.get("suspected_restructure")],
        "errors": [c for c, s in stats.items() if s.get("error")],
    }


def update_health(pending: dict, stats: dict[str, dict], today: str) -> dict[str, int]:
    """チェーンごとの「連続で問題が出ている日数」を pending["_health"] に持ち、今回問題があった
    チェーンの日数を返す。日付で数えるので同じ日の再実行では増えず、1日でも空けば数え直す。
    今回巡回しなかったチェーン(チェーン指定の実行)は触らない。歯止めの保留は別に consecutive_days を持つ。"""
    health = pending.setdefault("_health", {})
    bad = {c for names in collect_problems(stats).values() for c in names}
    yesterday = (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat()
    streaks: dict[str, int] = {}
    for chain in stats:
        if chain not in bad:
            health.pop(chain, None)
            continue
        prev = health.get(chain) or {}
        n = int(prev.get("days", 0))
        if prev.get("last_date") != today:
            n = n + 1 if prev.get("last_date") == yesterday else 1
        health[chain] = {"days": n, "last_date": today}
        streaks[chain] = n
    if not health:
        pending.pop("_health", None)
    return streaks


def save_run_summary(stats: dict[str, dict], streaks: dict[str, int] | None = None) -> None:
    """この実行で新規に記録した商品数・終了を観測した商品数・問題があったチェーンを書き出す。
    notify.py が読む。

    日付(UTC/JSTのずれ)で数えると朝の実行で通知が出ない・手動実行で二重に通知が出る
    不具合が姉妹サイト(コンビニポチ)で起きたため、実行ごとに上書きする一時ファイル
    (gitには入れない)にする。

    形式: {"new": {...}, "ended": {...}, "suspected": {...},
           "blocked": [チェーン], "list_failed": [チェーン], "errors": [チェーン],
           "streaks": {チェーン: 連続日数}, "detail_failed": {チェーン: 詳細取得失敗件数}}
    """
    out = {
        "new": {chain: s.get("new_products", 0) for chain, s in stats.items()},
        "ended": {chain: s.get("ended", 0) for chain, s in stats.items()},
        "suspected": {chain: s["suspected_restructure"] for chain, s in stats.items()
                      if s.get("suspected_restructure")},
    }
    problems = collect_problems(stats)
    out.update(problems)
    out["streaks"] = streaks or {}
    listed = set(problems["list_failed"]) | set(problems["blocked"]) | set(problems["errors"])
    out["detail_failed"] = {c: s["failed"] for c, s in stats.items() if s.get("failed") and c not in listed}
    RUN_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    RUN_SUMMARY.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


CRAWLERS = {"dennys": crawl_dennys, "jonathan": crawl_jonathan, "cocos": crawl_cocos, "bigboy": crawl_bigboy, "joyfull": crawl_joyfull, "steakdon": crawl_steakdon}


def main(argv: list[str] | None = None) -> int:
    # 引数でチェーンを指定すると、そのチェーンだけ巡回する(例: crawl.py jonathan)。
    # 引数なしは全チェーン(Actionsの定期実行)
    argv = sys.argv[1:] if argv is None else argv
    unknown = [a for a in argv if a not in CRAWLERS]
    if unknown:
        print(f"不明なチェーン: {unknown} (指定できるのは {list(CRAWLERS)})", file=sys.stderr)
        return 2
    targets = [CRAWLERS[a] for a in argv] if argv else list(CRAWLERS.values())
    pending = load_json(PENDING_PATH, {})
    stats: dict[str, dict] = {}
    getter = Getter()
    started = time.monotonic()
    names = {v: k for k, v in CRAWLERS.items()}

    for fn in targets:
        try:
            fn(getter, pending, stats)
        except Exception as e:  # noqa: BLE001
            print(f"[error] {fn.__name__} で例外: {e}", file=sys.stderr)
            err_chain = names.get(fn)
            if err_chain:
                stats.setdefault(err_chain, new_stats())["error"] = f"{type(e).__name__}: {e}"

    streaks = update_health(pending, stats, today_jst())
    save_json(PENDING_PATH, pending, sort_keys=True)
    save_run_summary(stats, streaks)

    print("=== クロール結果 ===")
    for chain, s in stats.items():
        print(
            f"{chain}: 一覧等{s.get('list_requests', 0)}件 / 詳細{s.get('detail_requests', 0)}件 "
            f"(リクエスト計{getter.counts.get(chain, 0)}) / 記録対象として一覧に居た{s.get('limited_seen', 0)}件 "
            f"/ 新規{s.get('new_products', 0)}件 / 終了観測{s.get('ended', 0)}件 / 失敗{s.get('failed', 0)}件 "
            f"/ 一覧取得={'全部成功' if s.get('list_ok') else '一部失敗'} "
            f"/ ブロック={'あり' if s.get('blocked') else 'なし'}"
            + (f" / 例外={s['error']}" if s.get("error") else "")
        )
    print(f"所要時間: {time.monotonic() - started:.0f}秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())

