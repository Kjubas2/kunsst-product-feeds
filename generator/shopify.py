"""
Pobieranie danych ze sklepu Shopify – TYLKO ODCZYT, niczego w sklepie nie zmienia.

Program loguje się danymi aplikacji z Shopify Dev Dashboard
(SHOPIFY_CLIENT_ID i SHOPIFY_CLIENT_SECRET zapisane w sekretach GitHuba),
dostaje klucz ważny 24 h i czyta przez Admin API:
  1. aktywne produkty: tytuł, opis, zdjęcia, metapola, opcje + tłumaczenia,
  2. wszystkie warianty, z ceną dla każdego kraju z 01.settings/02.markets.csv,
  3. tłumaczenia nazw opcji i ich wartości (np. Golden Hour → Miodowy).
"""
import json
import os
import time
import urllib.parse
import urllib.request

PRODUCTS = """
query Products($after: String) {
  products(first: 10, after: $after, query: "status:active") {
    pageInfo { hasNextPage endCursor }
    nodes {
      id handle title descriptionHtml onlineStoreUrl
      __TRANSLATIONS__
      options { id name optionValues { id name } }
      media(first: 40) { nodes { id ... on MediaImage { image { url } } } }
      highlights: metafield(namespace: "custom", key: "product_highlights") { value __TRANSLATIONS_MF__ }
      dimensions: metafield(namespace: "custom", key: "dimensions") { value __TRANSLATIONS_MF__ }
      lead_time: metafield(namespace: "custom", key: "lead_time") { value }
    }
  }
}
"""

VARIANTS = """
query Variants($id: ID!, $after: String) {
  product(id: $id) {
    variants(first: __PAGE__, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id title sku availableForSale
        selectedOptions { name value }
        media(first: 1) { nodes { id ... on MediaImage { image { url } } } }
        inventoryItem { measurement { weight { value unit } } }
        __PRICES__
      }
    }
  }
}
"""

OPTION_TRANSLATIONS = """
query Options($ids: [ID!]!) {
  translatableResourcesByIds(first: 100, resourceIds: $ids) {
    nodes { resourceId __TRANSLATIONS__ }
  }
}
"""


MARKETS = """
query Markets($after: String) {
  markets(first: 50, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      name status
      conditions { regionsCondition { regions(first: 250) { nodes { ... on MarketRegionCountry { code } } } } }
    }
  }
}
"""


def fetch_markets(s):
    """Rynki ze Shopify z listą krajów – do sprawdzenia, czy każdy kraj ma feed.
    Przy błędzie zwraca None: feedy i tak powstają, raport tylko o tym wspomni."""
    try:
        out, cursor = [], None
        while True:
            part = s.query(MARKETS, {"after": cursor})["markets"]
            for m in part["nodes"]:
                regions = ((((m.get("conditions") or {}).get("regionsCondition") or {})
                            .get("regions") or {}).get("nodes") or [])
                out.append({"name": m["name"], "status": m.get("status"),
                            "countries": [r["code"] for r in regions if r.get("code")]})
            if not part["pageInfo"]["hasNextPage"]:
                return out
            cursor = part["pageInfo"]["endCursor"]
    except (SystemExit, KeyError, TypeError):
        return None


def _translations(languages, with_key=True):
    fields = "key value" if with_key else "value"
    return " ".join(f't_{l}: translations(locale: "{l}") {{ {fields} }}' for l in languages if l != "en")


def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_token(store):
    """Wymienia dane aplikacji (client id + secret) na klucz dostępu ważny 24 h."""
    client_id = os.environ.get("SHOPIFY_CLIENT_ID")
    secret = os.environ.get("SHOPIFY_CLIENT_SECRET")
    if not client_id or not secret:
        raise SystemExit("Brak SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET w sekretach GitHuba "
                         "(Settings → Secrets and variables → Actions).")
    data = urllib.parse.urlencode({"grant_type": "client_credentials",
                                   "client_id": client_id, "client_secret": secret}).encode()
    resp = _post(f"https://{store}/admin/oauth/access_token", data,
                 {"Content-Type": "application/x-www-form-urlencoded"})
    return resp["access_token"]


class Store:
    def __init__(self, store, api_version):
        self.url = f"https://{store}/admin/api/{api_version}/graphql.json"
        self.token = get_token(store)

    def query(self, query, variables):
        body = json.dumps({"query": query, "variables": variables}).encode()
        for attempt in range(8):
            resp = _post(self.url, body, {"Content-Type": "application/json",
                                          "X-Shopify-Access-Token": self.token})
            errors = resp.get("errors")
            if errors and any((e.get("extensions") or {}).get("code") == "THROTTLED" for e in errors):
                time.sleep(5 + 5 * attempt)  # Shopify prosi o chwilę przerwy
                continue
            if errors:
                raise SystemExit("Shopify zwrócił błąd: " + json.dumps(errors, ensure_ascii=False)[:2000])
            # Pilnujemy limitu zapytań: gdy zostaje mało punktów, czekamy aż się odnowią.
            status = ((resp.get("extensions") or {}).get("cost") or {}).get("throttleStatus") or {}
            available, rate = status.get("currentlyAvailable"), status.get("restoreRate") or 50
            if available is not None and available < 1000:
                time.sleep(min(20, (1000 - available) / rate))
            return resp["data"]
        raise SystemExit("Shopify kilka razy odmówił (limit zapytań). Uruchom ponownie za kilka minut.")


def fetch(store, api_version, languages, countries):
    """Zwraca (produkty, tłumaczenia_opcji, rynki).

    produkty – aktywne produkty, każdy z pełną listą wariantów w p["variants"]["nodes"];
               cena wariantu dla kraju XX jest w polu price_XX.
    tłumaczenia_opcji – {id opcji lub wartości opcji: {"pl": "...", "de": "..."}}.
    rynki – rynki Shopify z krajami (albo None, gdy nie udało się ich odczytać).
    """
    s = Store(store, api_version)
    q_products = (PRODUCTS.replace("__TRANSLATIONS__", _translations(languages))
                  .replace("__TRANSLATIONS_MF__", _translations(languages, with_key=False)))
    prices = " ".join(
        f"price_{c}: contextualPricing(context: {{ country: {c} }}) "
        f"{{ price {{ amount currencyCode }} compareAtPrice {{ amount }} }}"
        for c in countries)
    # mniej wariantów na stronę, gdy rynków jest dużo (limit kosztu jednego zapytania w Shopify)
    page = max(5, min(50, 900 // (3 * len(countries) + 12)))
    q_variants = VARIANTS.replace("__PRICES__", prices).replace("__PAGE__", str(page))

    products, cursor = [], None
    while True:
        part = s.query(q_products, {"after": cursor})["products"]
        products += part["nodes"]
        if not part["pageInfo"]["hasNextPage"]:
            break
        cursor = part["pageInfo"]["endCursor"]

    for p in products:
        variants, cursor = [], None
        while True:
            part = s.query(q_variants, {"id": p["id"], "after": cursor})["product"]["variants"]
            variants += part["nodes"]
            if not part["pageInfo"]["hasNextPage"]:
                break
            cursor = part["pageInfo"]["endCursor"]
        p["variants"] = {"nodes": variants}

    option_translations = {}
    other = [l for l in languages if l != "en"]
    if other:
        ids = [o["id"] for p in products for o in p["options"]]
        ids += [v["id"] for p in products for o in p["options"] for v in o["optionValues"]]
        q_opts = OPTION_TRANSLATIONS.replace("__TRANSLATIONS__", _translations(other))
        for i in range(0, len(ids), 100):
            for n in s.query(q_opts, {"ids": ids[i:i + 100]})["translatableResourcesByIds"]["nodes"]:
                option_translations[n["resourceId"]] = {
                    l: next((t["value"] for t in n.get(f"t_{l}") or [] if t["key"] == "name" and t["value"]), None)
                    for l in other}
    return products, option_translations, fetch_markets(s)
