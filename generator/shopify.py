"""
Pobieranie danych produktów ze sklepu Shopify (tylko odczyt).

Generator loguje się do Shopify danymi aplikacji z Dev Dashboard
(SHOPIFY_CLIENT_ID i SHOPIFY_CLIENT_SECRET zapisane w sekretach GitHuba),
dostaje klucz ważny 24 h i czyta produkty przez Admin API.
Niczego w sklepie nie zmienia.
"""
import json
import os
import time
import urllib.parse
import urllib.request

# Pola produktu, które generator pobiera. Ceny pobierane są osobno dla każdego
# kraju z arkusza (kolumna kraj_cennika), tłumaczenia dla każdego języka feedu.
ZAPYTANIE = """
query Produkty($po: String) {
  products(first: 10, after: $po, query: "status:active") {
    pageInfo { hasNextPage endCursor }
    nodes {
      id handle title descriptionHtml vendor onlineStoreUrl
      category { fullName }
      __TLUMACZENIA__
      media(first: 15) { nodes { ... on MediaImage { image { url } } } }
      materialy: metafield(namespace: "custom", key: "materials") { value __TLUMACZENIA_MF__ }
      wyrozniki: metafield(namespace: "custom", key: "product_highlights") { value __TLUMACZENIA_MF__ }
      wymiary: metafield(namespace: "custom", key: "dimensions") { value __TLUMACZENIA_MF__ }
      czas_realizacji: metafield(namespace: "custom", key: "lead_time") { value }
      variants(first: 100) {
        nodes {
          id title sku availableForSale
          selectedOptions { name value }
          media(first: 1) { nodes { ... on MediaImage { image { url } } } }
          inventoryItem { measurement { weight { value unit } } }
          mpn: metafield(namespace: "mm-google-shopping", key: "mpn") { value }
          __CENY__
        }
      }
    }
  }
}
"""


def zbuduj_zapytanie(jezyki, kraje):
    """Dokleja do zapytania tłumaczenia (np. pl, de) i ceny (np. PL, DE, NL)."""
    tl = " ".join(f't_{j}: translations(locale: "{j}") {{ key value }}' for j in jezyki if j != "en")
    tl_mf = " ".join(f't_{j}: translations(locale: "{j}") {{ value }}' for j in jezyki if j != "en")
    ceny = " ".join(
        f"cena_{k}: contextualPricing(context: {{ country: {k} }}) "
        f"{{ price {{ amount currencyCode }} compareAtPrice {{ amount }} }}"
        for k in kraje
    )
    return (ZAPYTANIE.replace("__TLUMACZENIA__", tl)
            .replace("__TLUMACZENIA_MF__", tl_mf)
            .replace("__CENY__", ceny))


def _post(url, dane, naglowki):
    zad = urllib.request.Request(url, data=dane, headers=naglowki, method="POST")
    with urllib.request.urlopen(zad, timeout=60) as odp:
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


def pobierz_produkty(sklep, wersja_api, jezyki, kraje):
    """Zwraca listę wszystkich aktywnych produktów z wariantami, cenami i tłumaczeniami."""
    klucz = pobierz_klucz(sklep)
    url = f"https://{sklep}/admin/api/{wersja_api}/graphql.json"
    zapytanie = zbuduj_zapytanie(jezyki, kraje)
    produkty, kursor = [], None
    while True:
        tresc = json.dumps({"query": zapytanie, "variables": {"po": kursor}}).encode()
        odp = _post(url, tresc, {"Content-Type": "application/json", "X-Shopify-Access-Token": klucz})
        if odp.get("errors"):
            raise SystemExit("Shopify zwrócił błąd: " + json.dumps(odp["errors"], ensure_ascii=False)[:2000])
        strona = odp["data"]["products"]
        produkty += strona["nodes"]
        if not strona["pageInfo"]["hasNextPage"]:
            break
        kursor = strona["pageInfo"]["endCursor"]
        time.sleep(0.5)
    return produkty
