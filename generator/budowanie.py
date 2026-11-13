"""
Budowanie wierszy feedu z danych Shopify i ustawień z folderu ustawienia/.

Zasada: treść produktu pochodzi z Shopify, a ustawienia (zakładki arkusza)
mówią tylko, jak ją ułożyć dla danego kanału, języka i waluty.
"""
import csv
import html
import io
import json
import re
import urllib.request

# ---------------------------------------------------------------- ustawienia

def wczytaj_csv(sciezka_lub_url):
    """Czyta plik CSV z dysku albo z adresu (np. opublikowanej zakładki Google Sheets)."""
    if sciezka_lub_url.startswith("http"):
        with urllib.request.urlopen(sciezka_lub_url, timeout=60) as odp:
            tekst = odp.read().decode("utf-8")
    else:
        with open(sciezka_lub_url, encoding="utf-8") as f:
            tekst = f.read()
    return list(csv.DictReader(io.StringIO(tekst)))


def wczytaj_ustawienia(folder):
    ust = {r["Ustawienie"]: r["Wartość"] for r in wczytaj_csv(f"{folder}/ustawienia.csv")}
    feedy = [r for r in wczytaj_csv(f"{folder}/feedy.csv") if r["aktywny"].strip().upper() == "TAK"]
    produkty = {r["handle"].strip(): r for r in wczytaj_csv(f"{folder}/produkty.csv")}
    slownik = {}
    for r in wczytaj_csv(f"{folder}/slownik.csv"):
        slownik[klucz(r["opcja_w_shopify"], r["wartość_w_shopify"])] = r
    return ust, feedy, produkty, slownik


def klucz(opcja, wartosc):
    return (opcja.strip().lower(), wartosc.strip().lower())


# ---------------------------------------------------------------- pomocnicze

def tekst_z_rich_text(wartosc):
    """Zamienia pole Shopify typu 'rich text' (JSON) na listę akapitów / punktów."""
    if not wartosc:
        return []
    try:
        drzewo = json.loads(wartosc)
    except ValueError:
        return [wartosc]
    wynik = []

    def tekst(w):
        if w.get("type") == "text":
            return w.get("value", "")
        return "".join(tekst(d) for d in w.get("children", []))

    def przejdz(w):
        if w.get("type") in ("paragraph", "list-item", "heading"):
            t = tekst(w).strip()
            if t:
                wynik.append(t)
        else:
            for d in w.get("children", []):
                przejdz(d)

    przejdz(drzewo)
    return wynik


def bez_html(h):
    if not h:
        return ""
    h = re.sub(r"<\s*br\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"</\s*(p|li|h\d|div)\s*>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", "", h)
    h = html.unescape(h).replace("\xa0", " ")
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r"\n\s*\n+", "\n\n", h)
    return h.strip()[:5000]


def oczysc(s):
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s*\([^)]*(in|Zoll|In|cala|cali|cale)\)", "", s)  # bez wymiarów w calach
    return re.sub(r"\s+", " ", s).strip()


def tlumaczenie(produkt, jezyk, klucz_pola):
    if jezyk == "en":
        return None
    for t in produkt.get(f"t_{jezyk}") or []:
        if t["key"] == klucz_pola and t["value"]:
            return t["value"]
    return None


def metapole(produkt, nazwa, jezyk):
    m = produkt.get(nazwa)
    if not m:
        return []
    if jezyk != "en" and m.get(f"t_{jezyk}"):
        return tekst_z_rich_text(m[f"t_{jezyk}"][0]["value"])
    return tekst_z_rich_text(m["value"])


def dni_realizacji(tekst):
    """'Lead time: 2 -4 weeks' -> (10, 20) dni roboczych."""
    if not tekst:
        return "", ""
    liczby = [int(x) for x in re.findall(r"\d+", tekst)]
    if len(liczby) < 2:
        return "", ""
    if "week" in tekst.lower():
        return liczby[0] * 5, liczby[1] * 5
    return liczby[0], liczby[1]


def wypelnij(szablon, **wartosci):
    for k, v in wartosci.items():
        szablon = szablon.replace("{" + k + "}", str(v))
    return szablon


SEKCJA_WYMIARY = {"en": "Dimensions", "de": "Abmessungen", "pl": "Wymiary", "fr": "Dimensions"}
KOLUMNY_JEZYKA = {"en": "EN", "de": "DE", "pl": "PL", "fr": "FR"}
ILE_WYROZNIKOW, ILE_SZCZEGOLOW = 6, 6

KOLUMNY_GOOGLE = (
    ["id", "item_group_id", "title", "description", "link", "ads_redirect", "image_link",
     "additional_image_link", "availability", "price", "sale_price", "brand", "mpn", "condition",
     "google_product_category", "product_type", "color", "size", "material"]
    + ["product_highlight"] * ILE_WYROZNIKOW
    + ["product_detail"] * ILE_SZCZEGOLOW
    + ["shipping_weight", "min_handling_time", "max_handling_time",
       "custom_label_0", "custom_label_1", "custom_label_2", "custom_label_3", "custom_label_4"]
)


# ---------------------------------------------------------------- feed Google

def zbuduj_feed(feed, produkty_shopify, ust, ustawienia_produktow, slownik, ostrzezenia):
    """Zwraca listę wierszy (każdy = jedna oferta = jeden wariant) dla jednego feedu."""
    jezyk = feed["język"].strip().lower()
    J = KOLUMNY_JEZYKA.get(jezyk, "EN")
    waluta = feed["waluta"].strip().upper()
    kraj = feed["kraj_cennika"].strip().upper()
    separator = f' {ust.get("Separator w tytule", "–").strip()} '
    wiersze = []

    for p in produkty_shopify:
        if not p.get("onlineStoreUrl"):
            continue  # produkt nieopublikowany w sklepie internetowym
        handle_en = p["handle"]
        up = ustawienia_produktow.get(handle_en)
        if up is None:
            ostrzezenia.append(f"Nowy produkt bez wiersza w zakładce Produkty: {handle_en} – użyto ustawień domyślnych.")
            up = {}
        if up.get("w_feedzie", "TAK").strip().upper() == "NIE":
            continue

        pid = p["id"].split("/")[-1]
        handle = tlumaczenie(p, jezyk, "handle") or handle_en
        tytul_produktu = (up.get(f"tytuł_{J} (nadpisanie)") or "").strip() \
            or tlumaczenie(p, jezyk, "title") or p["title"]
        opis = bez_html(tlumaczenie(p, jezyk, "body_html") or p["descriptionHtml"])
        zdjecia = [m["image"]["url"] for m in p["media"]["nodes"] if m and m.get("image")]

        wyrozniki = []
        if up.get("wyróżniki_z_shopify", "TAK").strip().upper() != "NIE":
            for w in metapole(p, "wyrozniki", jezyk):
                w = oczysc(w)
                if w and not w.endswith("?"):  # pytania to nie są cechy produktu
                    wyrozniki.append(w[:150])
        szczegoly = []
        for linia in metapole(p, "wymiary", jezyk):
            if ":" not in linia or re.search(r"contact|kontakt|skontaktuj", linia, re.I):
                continue
            a, b = (oczysc(x) for x in linia.split(":", 1))
            if a and b:
                szczegoly.append(f"{SEKCJA_WYMIARY.get(jezyk, 'Dimensions')}:{a}:{b}")

        dmin, dmax = up.get("min_dni_realizacji", ""), up.get("max_dni_realizacji", "")
        if not str(dmin).strip() or not str(dmax).strip():
            dmin, dmax = dni_realizacji((p.get("czas_realizacji") or {}).get("value", ""))

        for v in p["variants"]["nodes"]:
            vid = v["id"].split("/")[-1]
            kolor = up.get(f"kolor_domyślny_{J}", "")
            material = up.get(f"materiał_{J}", "")
            rozmiar, typ, fragmenty = "", "standard", []
            for opcja in v["selectedOptions"]:
                if opcja["name"].strip().lower() == "title":
                    continue  # produkt bez wariantów
                wpis = slownik.get(klucz(opcja["name"], opcja["value"]))
                if wpis is None:
                    ostrzezenia.append(
                        f"Brak w Słowniku: opcja „{opcja['name']}” = „{opcja['value']}” ({handle_en}). "
                        "W tytule użyto nazwy z Shopify – dopisz wiersz do Słownika.")
                    fragmenty.append(opcja["value"])
                    continue
                frag = (wpis.get(f"fragment_tytułu_{J}") or "").strip()
                if frag:
                    fragmenty.append(frag)
                atrybut = (wpis.get("atrybut_google") or "").strip()
                wartosc = (wpis.get(f"wartość_{J}") or "").strip()
                if atrybut == "color":
                    kolor = wartosc
                elif atrybut == "size":
                    rozmiar = wartosc
                elif atrybut == "material":
                    material = wartosc
                if (wpis.get("typ_wariantu") or "").strip() == "na_zamowienie":
                    typ = "na_zamowienie"

            if fragmenty:
                tytul = wypelnij(feed["szablon_tytułu"], tytul_produktu=tytul_produktu,
                                 cechy_wariantu=", ".join(fragmenty))
            else:
                tytul = tytul_produktu
            tytul = tytul.replace(" – ", separator)[:150]

            wspolne = dict(domena=ust["Domena sklepu"].rstrip("/"), prefiks_jezyka=feed["prefiks_języka"].strip(),
                           handle=handle, id_wariantu=vid, waluta=waluta, feed_label=feed["feed_label"].strip())
            link = wypelnij(feed["szablon_url"], **wspolne)
            link_reklamy = wypelnij(feed["szablon_url_reklamy"], **wspolne) if feed.get("szablon_url_reklamy") else ""

            zdj_wariantu = [m["image"]["url"] for m in v["media"]["nodes"] if m and m.get("image")]
            glowne = zdj_wariantu[0] if zdj_wariantu else (zdjecia[0] if zdjecia else "")
            dodatkowe = [u for u in zdjecia if u != glowne][:10]

            c = v.get(f"cena_{kraj}")
            if not c:
                ostrzezenia.append(f"Brak ceny dla kraju {kraj}: {handle_en} / {v['title']} – pominięto.")
                continue
            if c["price"]["currencyCode"] != waluta:
                ostrzezenia.append(
                    f"Feed {feed['feed_id']}: Shopify podał cenę w {c['price']['currencyCode']} zamiast {waluta} "
                    f"dla kraju {kraj} – sprawdź walutę rynku. Pominięto {handle_en} / {v['title']}.")
                continue
            cena, promocja = float(c["price"]["amount"]), ""
            stara = c.get("compareAtPrice")
            if stara and float(stara["amount"]) > cena:
                promocja = f"{cena:.2f} {waluta}"
                cena = float(stara["amount"])

            waga = (v.get("inventoryItem") or {}).get("measurement", {}).get("weight") or {}
            waga_txt = f"{waga['value']:g} kg" if waga.get("value") else ""

            wiersz = [
                ust["Prefiks ID oferty"] + pid + "_" + vid, pid, tytul, opis, link, link_reklamy,
                glowne, ",".join(dodatkowe), "in_stock" if v["availableForSale"] else "out_of_stock",
                f"{cena:.2f} {waluta}", promocja, ust["Marka (brand)"],
                ((v.get("mpn") or {}).get("value") or v.get("sku") or ""), ust.get("Stan (condition)", "new"),
                up.get("google_product_category", ""), up.get("product_type", ""), kolor, rozmiar, material,
            ]
            wiersz += (wyrozniki + [""] * ILE_WYROZNIKOW)[:ILE_WYROZNIKOW]
            wiersz += (szczegoly + [""] * ILE_SZCZEGOLOW)[:ILE_SZCZEGOLOW]
            wiersz += [waga_txt, dmin, dmax, up.get("custom_label_0", ""), up.get("custom_label_1", ""),
                       up.get("custom_label_2", ""), up.get("custom_label_3", ""), typ]
            wiersze.append(["" if x is None else str(x) for x in wiersz])
    return wiersze
