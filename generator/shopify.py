"""
Pobieranie danych produktów ze sklepu Shopify (tylko odczyt).

Generator loguje się do Shopify danymi aplikacji z Dev Dashboard
(SHOPIFY_CLIENT_ID i SHOPIFY_CLIENT_SECRET zapisane w sekretach GitHuba),
dostaje klucz ważny 24 h i czyta produkty przez Admin API.
Niczego w sklepie nie zmienia.

Co pobiera:
  1. produkty (tytuł, opis, zdjęcia, metapola, opcje wariantów) + ich tłumaczenia,
  2. WSZYSTKIE warianty każdego produktu (po 50 na stronę – bez limitu liczby),
     z ceną dla każdego kraju z zakładki Feedy (kolumna kraj_cennika),
  3. tłumaczenia nazw opcji i ich wartości (np. Color → Kolor, Golden Hour → Miodowy).
"""
import json
import os
import time
import urllib.parse
import urllib.request

PRODUKTY = """
query Produkty($po: String) {
  products(first: 10, after: $po, query: "status:active") {
    pageInfo { hasNextPage endCursor }
    nodes {
      id handle title descriptionHtml onlineStoreUrl
      __TLUMACZENIA__
      options { id name optionValues { id name } }
      media(first: 30) { nodes { id ... on MediaImage { image { url } } } }
      materialy: metafield(namespace: "custom", key: "materials") { value __TLUMACZENIA_MF__ }
      wyrozniki: metafield(namespace: "custom", key: "product_highlights") { value __TLUMACZENIA_MF__ }
      wymiary: metafield(namespace: "custom", key: "dimensions") { value __TLUMACZENIA_MF__ }
      czas_realizacji: metafield(namespace: "custom", key: "lead_time") { value }
    }
  }
}
"""

WARIANTY = """
query Warianty($id: ID!, $po: String) {
  product(id: $id) {
    variants(first: 50, after: $po) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id title sku availableForSale
        selectedOptions { name value }
        media(first: 1) { nodes { id ... on MediaImage { image { url } } } }
        inventoryItem { measurement { weight { value unit } } }
        __CENY__
      }
    }
  }
}
"""

TLUMACZENIA_OPCJI = """
query Opcje($ids: [ID!]!) {
  translatableResourcesByIds(first: 100, resourceIds: $ids) {
    nodes { resourceId __TLUMACZENIA__ }
  }
}
"""


def _tl(jezyki, z_kluczem=True):
    pola = "key value" if z_kluczem else "value"
    return " ".join(f't_{j}: translations(locale: "{j}") {{ {pola} }}' for j in jezyki if j != "en")


def _post(url, dane, naglowki):
    zad = urllib.request.Request(url, data=dane, headers=naglowki, method="POST")
    with urllib.request.urlopen(zad, timeout=90) as odp:
        return json.loads(odp.read().decode("utf-8"))


def pobierz_klucz(sklep):
    """Wymienia dane aplikacji (client id + secret) na klucz dostępu ważny 24 h."""
    client_id = os.environ.get("SHOPIFY_CLIENT_ID")
    secret = os.environ.get("SHOPIFY_CLIENT_SECRET")
    if not client_id or not secret:
        raise SystemExit(
            "Brak SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET. "
            "Uzupełnij sekrety w GitHubie – instrukcja: instrukcje/2-sekrety-github.md"
        )
    dane = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": secret,
    }).encode()
    odp = _post(f"https://{sklep}/admin/oauth/access_token", dane,
                {"Content-Type": "application/x-www-form-urlencoded"})
    return odp["access_token"]


class Sklep:
    def __init__(self, sklep, wersja_api):
        self.url = f"https://{sklep}/admin/api/{wersja_api}/graphql.json"
        self.klucz = pobierz_klucz(sklep)

    def zapytaj(self, zapytanie, zmienne):
        tresc = json.dumps({"query": zapytanie, "variables": zmienne}).encode()
        for proba in range(4):
            odp = _post(self.url, tresc, {"Content-Type": "application/json",
                                          "X-Shopify-Access-Token": self.klucz})
            bledy = odp.get("errors")
            if bledy and any((b.get("extensions") or {}).get("code") == "THROTTLED" for b in bledy):
                time.sleep(3 * (proba + 1))  # Shopify prosi o chwilę przerwy
                continue
            if bledy:
                raise SystemExit("Shopify zwrócił błąd: " + json.dumps(bledy, ensure_ascii=False)[:2000])
            return odp["data"]
        raise SystemExit("Shopify kilka razy odmówił (limit zapytań). Spróbuj uruchomić ponownie.")


def pobierz_produkty(sklep, wersja_api, jezyki, kraje):
    """Zwraca (produkty, tlumaczenia_opcji).

    produkty – lista aktywnych produktów, każdy z pełną listą wariantów (p["variants"]["nodes"]).
    tlumaczenia_opcji – {id opcji lub wartości: {"pl": "...", "de": "..."}}.
    """
    s = Sklep(sklep, wersja_api)
    zap_produkty = (PRODUKTY.replace("__TLUMACZENIA__", _tl(jezyki))
                    .replace("__TLUMACZENIA_MF__", _tl(jezyki, z_kluczem=False)))
    ceny = " ".join(
        f"cena_{k}: contextualPricing(context: {{ country: {k} }}) "
        f"{{ price {{ amount currencyCode }} compareAtPrice {{ amount }} }}"
        for k in kraje
    )
    zap_warianty = WARIANTY.replace("__CENY__", ceny)

    produkty, kursor = [], None
    while True:
        strona = s.zapytaj(zap_produkty, {"po": kursor})["products"]
        produkty += strona["nodes"]
        if not strona["pageInfo"]["hasNextPage"]:
            break
        kursor = strona["pageInfo"]["endCursor"]

    for p in produkty:
        warianty, kursor = [], None
        while True:
            strona = s.zapytaj(zap_warianty, {"id": p["id"], "po": kursor})["product"]["variants"]
            warianty += strona["nodes"]
            if not strona["pageInfo"]["hasNextPage"]:
                break
            kursor = strona["pageInfo"]["endCursor"]
            time.sleep(0.3)
        p["variants"] = {"nodes": warianty}

    tlumaczenia_opcji = {}
    inne_jezyki = [j for j in jezyki if j != "en"]
    if inne_jezyki:
        ids = [o["id"] for p in produkty for o in p["options"]]
        ids += [w["id"] for p in produkty for o in p["options"] for w in o["optionValues"]]
        zap_opcje = TLUMACZENIA_OPCJI.replace("__TLUMACZENIA__", _tl(inne_jezyki))
        for i in range(0, len(ids), 100):
            for n in s.zapytaj(zap_opcje, {"ids": ids[i:i + 100]})["translatableResourcesByIds"]["nodes"]:
                tlumaczenia_opcji[n["resourceId"]] = {
                    j: next((t["value"] for t in n.get(f"t_{j}") or [] if t["key"] == "name" and t["value"]), None)
                    for j in inne_jezyki
                }
    return produkty, tlumaczenia_opcji
