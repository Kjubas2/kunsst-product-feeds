"""
GENERATOR FEEDÓW KUNSST – plik główny. Uruchamia go GitHub (.github/workflows/generate-feeds.yml).

Kolejność pracy:
  1. Czyta ustawienia z 01.settings.
  2. Pobiera produkty i wszystkie warianty ze Shopify (tylko odczyt).
  3. Buduje Shopify Master Feed → 02.shopify_master_feed/02.shopify_master_feed.csv
  4. Dla każdej platformy z 03.platforms buduje feedy → 03.platforms/<platforma>/output/
     oraz stronę podglądu 03.platforms/<platforma>/04.overview.md
  5. Zapisuje raport → 04.reports/report.md

Bezpieczniki: gdy feed ma za mało ofert albo liczba ofert mocno spadła, stary plik zostaje,
a GitHub wysyła e-mail o nieudanym uruchomieniu.

Testy bez Shopify:  python generator/run.py --data-file dane.json
Zapis pobranych danych:  python generator/run.py --save-data dane.json
"""
import collections
import csv
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import master_feed  # noqa: E402
import platforms  # noqa: E402
import settings  # noqa: E402
import shopify  # noqa: E402
from settings import norm, yes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "02.shopify_master_feed", "02.shopify_master_feed.csv")
REPORT = os.path.join(ROOT, "04.reports", "report.md")
RAW = "https://raw.githubusercontent.com/Kjubas2/kunsst-product-feeds/main/"


def now_pl():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def percent(text, default):
    try:
        return float(str(text).replace("%", "").strip()) / 100
    except ValueError:
        return default


def md(s):
    return str(s if s is not None else "–").replace("|", "\\|").replace("\n", " ")


COUNTRY_NAMES = {
    "PL": "Polska", "DE": "Niemcy", "AT": "Austria", "LU": "Luksemburg", "CH": "Szwajcaria", "LI": "Liechtenstein",
    "BE": "Belgia", "NL": "Holandia", "FR": "Francja", "MC": "Monako", "IT": "Włochy", "ES": "Hiszpania",
    "PT": "Portugalia", "IE": "Irlandia", "GR": "Grecja", "FI": "Finlandia", "SE": "Szwecja", "DK": "Dania",
    "NO": "Norwegia", "IS": "Islandia", "CZ": "Czechy", "SK": "Słowacja", "SI": "Słowenia", "HU": "Węgry",
    "HR": "Chorwacja", "RO": "Rumunia", "BG": "Bułgaria", "EE": "Estonia", "LV": "Łotwa", "LT": "Litwa",
    "CY": "Cypr", "MT": "Malta", "GB": "Wielka Brytania", "US": "Stany Zjednoczone", "CA": "Kanada",
    "AU": "Australia", "JP": "Japonia",
}


def country_check(shop_markets, platform_list, S, warnings):
    """Porównuje kraje z rynków Shopify z krajami włączonych feedów (kolumna target_countries)."""
    lines = ["", "## Kraje: Shopify a feedy", "",
             "Kraje w GMC ustawiasz w źródle danych – kolumna `target_countries` w `01.feeds_list.csv` "
             "ma się z nimi zgadzać. Kraje celowo bez feedu wpisz w `countries_without_feed` "
             "(`01.settings/01.general_settings.csv`).", ""]
    if shop_markets is None:
        lines.append("Nie udało się odczytać rynków ze Shopify – sprawdzenie pominięte.")
        warnings.append("Nie udało się odczytać rynków ze Shopify (uprawnienie read_markets) – "
                        "sprawdzenie krajów pominięte.")
        return lines
    skip = {c.strip().upper() for c in S["general"].get("countries_without_feed", "").split(",") if c.strip()}
    shop = {}
    for m in shop_markets:
        if (m.get("status") or "ACTIVE").upper() == "ACTIVE":
            for c in m["countries"]:
                shop[c.upper()] = m["name"]
    feeds = collections.defaultdict(list)
    for platform in platform_list:
        for f in platform["feeds"]:
            fid = (f.get("feed_id") or "").strip()
            if fid and yes(f.get("enabled")):
                label = fid if len(platform_list) == 1 else f"{platform['name']}: {fid}"
                for c in (f.get("target_countries") or "").split(","):
                    if c.strip():
                        feeds[c.strip().upper()].append(label)

    def name(c):
        return f"{c} – {COUNTRY_NAMES[c]}" if c in COUNTRY_NAMES else c

    lines += ["| Kraj | Rynek Shopify | Feedy | Stan |", "|---|---|---|---|"]
    for c in sorted(set(shop) | set(feeds), key=lambda c: (shop.get(c, "~"), c)):
        if c in shop and c in feeds:
            status = "✅"
        elif c in shop and c in skip:
            status = "celowo bez feedu"
        elif c in shop:
            status = "⚠️ brak feedu"
            warnings.append(f"Shopify sprzedaje do kraju {name(c)} (rynek {shop[c]}), ale żaden włączony feed go "
                            "nie ma. Dopisz kraj do target_countries właściwego feedu i w źródle w GMC "
                            "albo do countries_without_feed.")
        else:
            status = "⚠️ brak w rynkach Shopify"
            warnings.append(f"Feed {', '.join(feeds[c])} ma kraj {name(c)}, którego nie ma w żadnym aktywnym "
                            "rynku Shopify – klient z tego kraju nie kupi w sklepie.")
        lines.append(f"| {md(name(c))} | {md(shop.get(c, '–'))} | {md(', '.join(feeds.get(c, [])) or '–')} | {status} |")
    return lines


def shipping_section(ship, rows, S, platform_list, warnings):
    """Tabela: co feedy mówią Google o wysyłce w każdym rynku – do porównania z Ustawieniami Shopify."""
    lines = ["", "## Wysyłka w feedach", "",
             "Koszt: Shopify → Ustawienia → Wysyłka i dostawa (najtańsza stawka dla jednej sztuki, progi cenowe "
             "liczone od ceny wariantu). Czas realizacji: pola produktu/wariantu „Production time” albo "
             "„Shipping settings” dla gotowych do wysyłki. Transport: Metaobiekty → „Shipping country”. "
             "Wszystko w dniach roboczych.", ""]
    if not ship or ship.get("error"):
        return lines + ["Nie udało się odczytać wysyłki – sekcja pominięta."]
    lines += ["| Rynek | Kraj | Koszt dostawy w ofertach | Darmowa | Czas realizacji | Transport | Bez kosztu |",
              "|---|---|---|---|---|---|---|"]
    by_market = collections.defaultdict(list)
    for r in rows:
        if r["in_feeds"] == "YES":
            by_market[r["market"]].append(r)
    free_everywhere, free_partly = [], []
    for mid, m in S["markets"].items():
        if not yes(m.get("enabled")):
            continue
        rs = by_market.get(mid, [])
        cur = m["currency"].strip().upper()
        country = m["prices_from_country"].strip().upper()
        prices = sorted({float(r["shipping_price"]) for r in rs if r["shipping_price"]})
        missing = sum(1 for r in rs if not r["shipping_price"])
        n_free = sum(1 for r in rs if r["shipping_price"] and float(r["shipping_price"]) == 0)
        free = "wszystkie" if rs and n_free == len(rs) else (f"{n_free} z {len(rs)}" if n_free else "–")
        if rs and n_free == len(rs):
            free_everywhere.append(country)
        elif n_free:
            free_partly.append(country)
        handling = sorted({(r["handling_days_min"], r["handling_days_max"]) for r in rs if r["handling_days_min"] != ""})
        h_txt = ", ".join(f"{a}–{b}" for a, b in handling) or "–"
        transit = (ship.get("transit") or {}).get(country)
        t_txt = f"{transit[0]}–{transit[1]}" if transit else "–"
        p_txt = ", ".join(f"{p:g} {cur}" for p in prices) or "–"
        lines.append(f"| {mid} | {country} | {md(p_txt)} | {free} | {h_txt} | {t_txt} | {missing or '–'} |")
    lines += ["", f"Darmowa dostawa dla wszystkich ofert: **{', '.join(sorted(set(free_everywhere))) or '–'}**. "
              f"Darmowa tylko dla tańszych produktów (progi): **{', '.join(sorted(set(free_partly))) or '–'}**.", "",
              "Lista krajów „Free delivery” na stronie produktu (Dostosuj motyw → Ustawienia motywu → "
              "KUB – Free delivery) powinna zawierać dokładnie kraje z pierwszej listy.", ""]
    for platform in platform_list:
        for f in platform["feeds"]:
            if not yes(f.get("enabled")):
                continue
            market = S["markets"].get((f.get("market") or "").strip()) or {}
            mc = (market.get("prices_from_country") or "").strip().upper()
            targets = {c.strip().upper() for c in (f.get("target_countries") or "").split(",") if c.strip()}
            if mc and targets and targets != {mc}:
                warnings.append(f"Feed {f.get('feed_id')}: kraje {', '.join(sorted(targets))}, a koszt i czas "
                                f"wysyłki są liczone dla {mc}. Jeden feed = jeden kraj.")
    return lines


def write_master(rows):
    os.makedirs(os.path.dirname(MASTER), exist_ok=True)
    with open(MASTER, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=master_feed.COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_overview(platform, results, header, sources, stamp):
    lines = [f"# {platform['name'].capitalize()} – podgląd wszystkich feedów", "",
             f"> Ta strona tworzy się sama przy każdym uruchomieniu (ostatnio: {stamp}). "
             "Zmiany robisz w plikach 01–03 w tym folderze.", "",
             "## Feedy", "",
             "| Feed | Włączony | Rynek | Kraje | Feed label | Ofert | Adres pliku (wklejany w GMC) |",
             "|---|---|---|---|---|---|---|"]
    for r in results:
        f = r["feed"]
        url = RAW + r["file"] if yes(f.get("enabled")) else "–"
        lines.append(f"| {md(r['feed_id'])} | {md(f.get('enabled'))} | {md(f.get('market'))} | "
                     f"{md(f.get('target_countries'))} | {md(f.get('feed_label'))} | {md(r['offers'])} | {url} |")
    example = next((r for r in results if r["example"]), None)
    lines += ["", "## Kolumny pliku", "",
              f"Przykład z feedu **{example['feed_id']}** (pierwsza oferta)." if example else "", "",
              "| Kolumna | Skąd (02.field_mapping.csv) | Przykład |", "|---|---|---|"]
    for i, col in enumerate(header):
        value = example["example"][i] if example else ""
        if len(value) > 120:
            value = value[:117] + "…"
        lines.append(f"| {md(col)} | `{md(sources[i])}` | {md(value)} |")
    lines += ["", "## Zasady platformy (03.platform_rules.csv)", "", "| Zasada | Kolumna | Wartość | Opis |",
              "|---|---|---|---|"]
    for rule in platform["rules"]:
        if (rule.get("rule") or "").strip():
            lines.append(f"| {md(rule.get('rule'))} | {md(rule.get('column'))} | {md(rule.get('value'))} | "
                         f"{md(rule.get('opis'))} |")
    with open(os.path.join(platform["folder"], "04.overview.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    S = settings.load(ROOT)
    g = S["general"]
    markets = [m for m in S["markets"].values() if yes(m.get("enabled"))]
    languages = sorted({norm(m["language"]) for m in markets})
    countries = sorted({m["prices_from_country"].strip().upper() for m in markets})

    if "--data-file" in sys.argv:
        with open(sys.argv[sys.argv.index("--data-file") + 1], encoding="utf-8") as f:
            data = json.load(f)
        products, option_tr, shop_markets = data["products"], data["option_translations"], data.get("markets")
        ship = data.get("shipping")
    else:
        products, option_tr, shop_markets, ship = shopify.fetch(
            g["shopify_store"].strip(), g.get("shopify_api_version", "2026-10").strip(), languages, countries)
    if "--save-data" in sys.argv:
        with open(sys.argv[sys.argv.index("--save-data") + 1], "w", encoding="utf-8") as f:
            json.dump({"products": products, "option_translations": option_tr, "markets": shop_markets,
                       "shipping": ship}, f, ensure_ascii=False)

    warnings = []
    if not ship or ship.get("error"):
        warnings.append("Nie udało się odczytać wysyłki ze Shopify (" + str((ship or {}).get("error")) + ") – "
                        "feedy bez kosztu i czasu dostawy; GMC użyje usług wysyłki z konta, jeśli są.")
    rows, photo_plan = master_feed.build(products, option_tr, S, warnings, ship)
    write_master(rows)

    safety = {"min_offers": int(g.get("safety_min_offers", "50") or 50),
              "max_drop": percent(g.get("safety_max_drop", "30%"), 0.3)}
    stamp = now_pl()
    all_results = []
    platform_list = settings.platforms(ROOT)
    for platform in platform_list:
        results, header, sources, _ = platforms.build(platform, rows, S, warnings, safety)
        write_overview(platform, results, header, sources, stamp)
        all_results += [(platform["name"], r) for r in results]

    # ---------------------------------------------------------------- raport
    variants = sum(len(p["variants"]["nodes"]) for p in products)
    held = [r["feed_id"] for _, r in all_results if r.get("held")]
    lines = [f"# Raport z ostatniego uruchomienia: {stamp}", ""]
    if held:
        lines += [f"> ⛔ **Zatrzymane feedy: {', '.join(held)}** – stare pliki działają dalej. Przyczyna w tabeli poniżej.", ""]
    lines += [f"Pobrano ze Shopify: **{len(products)} produktów, {variants} wariantów**. "
              f"Shopify Master Feed: **{len(rows)} wierszy** ({len(markets)} rynków), "
              f"z czego w feedach: **{sum(1 for r in rows if r['in_feeds'] == 'YES')}**.", "",
              "## Feedy", "",
              "| Platforma | Feed | Rynek | Ofert | Poprzednio | Wynik |", "|---|---|---|---|---|---|"]
    for name, r in all_results:
        lines.append(f"| {name} | {r['feed_id']} | {md(r['feed'].get('market'))} | {md(r['offers'])} | "
                     f"{md(r['previous'])} | {r['status']} |")

    lines += ["", "## Dlaczego część wariantów nie trafiła do feedów", "",
              "Liczby dla jednego rynku (w każdym rynku są takie same, chyba że niżej napisano inaczej).", "",
              "| Powód | Wariantów |", "|---|---|"]
    first_market = next(iter(m for m, x in S["markets"].items() if yes(x.get("enabled"))), None)
    reasons = collections.Counter(
        ("brak zdjęcia (szczegóły w planie zdjęć)" if r["skip_reason"].startswith("brak zdjęcia") else r["skip_reason"])
        for r in rows if r["market"] == first_market and r["skip_reason"])
    lines += [f"| {md(k)} | {v} |" for k, v in reasons.most_common()] or ["| – | 0 |"]
    market_specific = collections.Counter((r["market"], r["skip_reason"]) for r in rows
                                          if r["skip_reason"].startswith(("brak ceny", "Shopify podał")))
    if market_specific:
        lines += ["", "Różnice między rynkami:", ""]
        lines += [f"- {m}: {reason} – {n} wariantów" for (m, reason), n in market_specific.most_common()]

    if photo_plan:
        lines += ["", "## Plan zdjęć – od najważniejszych", "",
                  "Przypisz zdjęcie do jednego wariantu z tej kombinacji w Shopify (Produkt → wariant → zdjęcie). "
                  "Przy następnym uruchomieniu wszystkie warianty tej kombinacji wejdą do feedów.", "",
                  "| # | Produkt | Kombinacja bez zdjęcia | Nowych ofert w każdym feedzie |", "|---|---|---|---|"]
        order = sorted(photo_plan.items(), key=lambda kv: (0 if norm(kv[0][2]) == "flagship" else 1, -kv[1], kv[0][1]))
        for i, ((_, title, _, combo), n) in enumerate(order, 1):
            lines.append(f"| {i} | {md(title)} | {md(combo)} | {n} |")

    lines += country_check(shop_markets, platform_list, S, warnings)
    lines += shipping_section(ship, rows, S, platform_list, warnings)

    lines += ["", "## Ostrzeżenia", ""]
    lines += [f"- {w}" for w in dict.fromkeys(warnings)] or ["Brak – wszystko w porządku."]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:40]))

    if held:
        # kod błędu = GitHub wyśle e-mail o nieudanym uruchomieniu
        sys.exit(f"Zatrzymane feedy: {', '.join(held)} – szczegóły w 04.reports/report.md")


if __name__ == "__main__":
    main()
