"""
Zamiana Shopify Master Feed na pliki dla platform (Google, później Meta, TikTok…).

Dla każdej platformy (folder 03.platforms/<nazwa>) program czyta:
  01.feeds_list.csv    – jakie feedy zrobić (rynek, kraje, feed label, włączony),
  02.field_mapping.csv – jakie kolumny ma plik i skąd biorą wartości ({kolumna Master Feed}),
  03.platform_rules.csv – zasady platformy (pola obowiązkowe, limity długości, zapis wartości).
Nowa platforma = nowy folder z tymi trzema plikami; programu nie trzeba zmieniać.
"""
import csv
import gzip
import io
import os
import re

from settings import norm, yes


def fill(template, values):
    """Podstawia {pole}. Gdy PIERWSZE pole w szablonie jest puste, cała kolumna jest pusta
    (np. „{sale_price} {currency}” bez promocji nie da samego „PLN”)."""
    names = re.findall(r"\{([^{}]+)\}", template or "")
    if names and not str(values.get(names[0].strip(), "") or "").strip():
        return ""
    out = re.sub(r"\{([^{}]+)\}", lambda m: str(values.get(m.group(1).strip(), "") or ""), template or "")
    return " ".join(out.split())


def quote(s):
    return '"' + s.replace('"', '""') + '"'


def columns_of(rule):
    return [c.strip() for c in (rule.get("column") or "").split(",") if c.strip()]


def parse_rules(rules, warnings, platform):
    r = {"format": "tsv", "required": [], "value_map": {}, "max_length": {}, "trim_warn": set(),
         "min_values": {}, "quote_if_comma": set(), "quote_sub_values": set(), "currency_check": False}
    for rule in rules:
        kind = norm(rule.get("rule"))
        if not kind:
            continue
        cols, value = columns_of(rule), (rule.get("value") or "").strip()
        if kind == "file_format":
            r["format"] = value.lower()
        elif kind == "required":
            r["required"] += cols
        elif kind == "value_map":
            pairs = {}
            for part in value.split(";"):
                a, _, b = part.replace("->", "→").partition("→")
                if a.strip() and b.strip():
                    pairs[a.strip()] = b.strip()
            for c in cols:
                r["value_map"][c] = pairs
        elif kind == "max_length":
            for c in cols:
                r["max_length"][c] = int(value)
                if "warn" in norm(rule.get("what_happens")):
                    r["trim_warn"].add(c)
        elif kind == "min_values":
            for c in cols:
                r["min_values"][c] = int(value)
        elif kind == "quote_if_comma":
            r["quote_if_comma"].update(cols)
        elif kind == "quote_sub_values":
            r["quote_sub_values"].update(cols)
        elif kind == "currency_must_match_market":
            r["currency_check"] = True
        elif kind in ("skip_empty_columns",):
            pass
        else:
            warnings.append(f"{platform}: nieznana zasada „{rule.get('rule')}” w 03.platform_rules.csv – pominięta.")
    return r


def count_offers(path):
    if not os.path.exists(path):
        return None
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return max(sum(1 for _ in f) - 1, 0)


def write_file(path, header, rows, fmt):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if fmt == "tsv":
        # Google: jedna oferta = jedna linia, kolumny rozdzielone tabulatorem
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\t".join(header) + "\n")
            for row in rows:
                f.write("\t".join(v.replace("\t", " ") for v in row) + "\n")
        return
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    if fmt == "csv.gz":
        with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())
    else:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())


def build(platform, master_rows, S, warnings, safety):
    """Buduje wszystkie włączone feedy jednej platformy. Zwraca listę wyników (do raportu)."""
    name = platform["name"]
    rules = parse_rules(platform["rules"], warnings, name)
    first_key = list(platform["mapping"][0].keys())[0]
    header = [m[first_key].strip() for m in platform["mapping"]]
    sources = [m.get("source", "") for m in platform["mapping"]]
    ext = {"tsv": ".tsv", "csv": ".csv", "csv.gz": ".csv.gz"}.get(rules["format"], ".tsv")
    results = []

    for feed in platform["feeds"]:
        feed_id = (feed.get("feed_id") or "").strip()
        if not feed_id:
            continue
        res = {"feed_id": feed_id, "feed": feed, "offers": None, "previous": None, "status": "", "example": None,
               "file": f"03.platforms/{name}/output/{feed_id}{ext}"}
        results.append(res)
        if not yes(feed.get("enabled")):
            res["status"] = "wyłączony (enabled = NO) – plik nie jest tworzony"
            continue
        market_id = (feed.get("market") or "").strip()
        market = S["markets"].get(market_id)
        if not market or not yes(market.get("enabled")):
            res["status"] = f"⛔ rynek {market_id} nie istnieje albo jest wyłączony w 01.settings/02.markets.csv"
            warnings.append(f"{name}/{feed_id}: {res['status']}")
            continue

        extra = {"feed_id": feed_id, "feed_label": (feed.get("feed_label") or "").strip(),
                 "target_countries": (feed.get("target_countries") or "").strip(),
                 "excluded_destinations": (feed.get("excluded_destinations") or "").strip()}
        out, dropped = [], 0
        for row in master_rows:
            if row["market"] != market_id or row["in_feeds"] != "YES":
                continue
            if rules["currency_check"] and row["currency"] != market["currency"].strip().upper():
                dropped += 1
                continue
            values = dict(row, **extra)
            cells = [fill(src, values) for src in sources]
            for i, col in enumerate(header):
                if col in rules["value_map"]:
                    cells[i] = rules["value_map"][col].get(cells[i], cells[i])
                limit = rules["max_length"].get(col)
                if limit and len(cells[i]) > limit:
                    if col in rules["trim_warn"]:
                        warnings.append(f"{feed_id}: {col} dłuższy niż {limit} znaków – przycięty ({row['offer_id']}).")
                    cells[i] = cells[i][:limit].rstrip(" ,–-")
            for col, minimum in rules["min_values"].items():
                idx = [i for i, c in enumerate(header) if c == col]
                if 0 < sum(1 for i in idx if cells[i]) < minimum:
                    for i in idx:
                        cells[i] = ""
            missing = [c for c in rules["required"] if not any(cells[i] for i, h in enumerate(header) if h == c)]
            if missing:
                dropped += 1
                warnings.append(f"{feed_id}: oferta {row['offer_id']} pominięta – puste pola obowiązkowe: "
                                f"{', '.join(missing)}.")
                continue
            for i, col in enumerate(header):
                if not cells[i]:
                    continue
                if col in rules["quote_if_comma"] and ("," in cells[i] or cells[i].startswith('"')):
                    cells[i] = quote(cells[i])
                elif col in rules["quote_sub_values"]:
                    parts = cells[i].split(":", 2)
                    cells[i] = ":".join(quote(p) if re.search(r'[,:"]', p) else p for p in parts)
                elif cells[i].startswith('"'):
                    cells[i] = quote(cells[i])
            out.append(cells)
            if res["example"] is None:
                res["example"] = cells

        path = os.path.join(platform["folder"], "output", feed_id + ext)
        res["previous"] = count_offers(path)
        res["offers"] = len(out)
        res["dropped"] = dropped
        problem = None
        if len(out) < safety["min_offers"]:
            problem = f"za mało ofert ({len(out)} < {safety['min_offers']})"
        elif res["previous"] and len(out) < res["previous"] * (1 - safety["max_drop"]):
            problem = f"spadek z {res['previous']} do {len(out)} ofert"
        if problem:
            res["status"] = f"⛔ NIE zapisano – {problem}. Stary plik zostaje"
            res["held"] = True
            continue
        write_file(path, header, out, rules["format"])
        res["status"] = "✅ zapisano"
    return results, header, sources, rules
