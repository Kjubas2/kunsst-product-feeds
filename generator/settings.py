"""
Czytanie ustawień z plików CSV (folder 01.settings i foldery platform w 03.platforms).
"""
import csv
import os


def read_csv(path):
    """Czyta plik CSV. Nagłówki bez spacji na brzegach; wartości bez zmian (ważne np. dla „kolor ”)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{(k or "").strip(): (v if v is not None else "") for k, v in row.items()}
                for row in csv.DictReader(f)]


def norm(s):
    return " ".join((s or "").split()).lower()


def yes(s, default=False):
    s = norm(s)
    if not s:
        return default
    return s in ("yes", "tak", "true", "1")


def load(root):
    folder = os.path.join(root, "01.settings")
    general = {r["setting"].strip(): r["value"] for r in read_csv(os.path.join(folder, "01.general_settings.csv"))
               if r.get("setting", "").strip()}
    markets = {r["market_id"].strip(): r for r in read_csv(os.path.join(folder, "02.markets.csv"))
               if r.get("market_id", "").strip()}
    products = {r["product_id"].strip(): r for r in read_csv(os.path.join(folder, "03.products_settings.csv"))
                if r.get("product_id", "").strip()}
    options = {norm(r["option_name"]): r for r in read_csv(os.path.join(folder, "04.variant_options.csv"))
               if r.get("option_name", "").strip()}
    dictionary = {(norm(r["option_name"]), norm(r["shopify_value"])): r
                  for r in read_csv(os.path.join(folder, "05.dictionary.csv"))
                  if r.get("option_name", "").strip()}
    return {"general": general, "markets": markets, "products": products,
            "options": options, "dictionary": dictionary}


def platforms(root):
    """Zwraca listę platform: każdy podfolder 03.platforms/<nazwa> z plikami 01–03."""
    base = os.path.join(root, "03.platforms")
    result = []
    for name in sorted(os.listdir(base)):
        folder = os.path.join(base, name)
        if not os.path.isfile(os.path.join(folder, "01.feeds_list.csv")):
            continue
        result.append({
            "name": name,
            "folder": folder,
            "feeds": read_csv(os.path.join(folder, "01.feeds_list.csv")),
            "mapping": [r for r in read_csv(os.path.join(folder, "02.field_mapping.csv"))
                        if list(r.values())[0].strip()],
            "rules": read_csv(os.path.join(folder, "03.platform_rules.csv")),
        })
    return result
