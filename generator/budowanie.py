"""
Budowanie ofert z danych Shopify i ustawień z folderu ustawienia/.

Zasada: treść produktu pochodzi z Shopify (także tłumaczenia nazw kolorów,
gatunków i konfiguracji), a ustawienia mówią tylko, jak ją ułożyć dla danego
feedu. Słownik służy wyłącznie do nadpisań – tam, gdzie wartość ze Shopify
nie pasuje do feedu (np. „130 cm - Standard” → „130 cm”).

Wynik tego pliku to lista ofert w jednym, wspólnym kształcie (słownik pól,
np. oferta["tytul"], oferta["kolor"]). Dopiero profil platformy
(ustawienia/profile/<profil>.csv) decyduje, w jakich kolumnach te pola trafią
do pliku – dzięki temu kolejne platformy nie wymagają przepisywania tego kodu.
"""
import csv
import html
import io
import json
import re
import urllib.request

KOLUMNY_JEZYKA = {"en": "EN", "de": "DE", "pl": "PL", "fr": "FR"}
SEKCJA_WYMIARY = {"en": "Dimensions", "de": "Abmessungen", "pl": "Wymiary", "fr": "Dimensions"}
ILE_WYROZNIKOW, ILE_SZCZEGOLOW, ILE_ZDJEC_DODATKOWYCH = 6, 6, 10


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


def norm(s):
    return (s or "").strip().lower()


def tak(s, domyslnie=False):
    s = norm(s)
    if not s:
        return domyslnie
    return s in ("tak", "yes", "1", "true")


def wczytaj_ustawienia(folder):
    """Zwraca wszystkie zakładki panelu jako jeden słownik."""
    return {
        "ogolne": {r["Ustawienie"]: r["Wartość"] for r in wczytaj_csv(f"{folder}/ustawienia.csv")},
        "feedy": [r for r in wczytaj_csv(f"{folder}/feedy.csv") if tak(r["aktywny"])],
        "produkty": {r["handle"].strip(): r for r in wczytaj_csv(f"{folder}/produkty.csv")},
        "opcje": {norm(r["opcja_w_shopify"]): r for r in wczytaj_csv(f"{folder}/opcje.csv")},
        "slownik": {(norm(r["opcja_w_shopify"]), norm(r["wartość_w_shopify"])): r
                    for r in wczytaj_csv(f"{folder}/slownik.csv")},
    }


def wczytaj_profil(folder, nazwa):
    """Profil platformy = lista kolumn pliku i źródło każdej z nich."""
    return [(r["kolumna"].strip(), r["źródło"]) for r in wczytaj_csv(f"{folder}/profile/{nazwa}.csv")
            if r["kolumna"].strip()]


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


def wypelnij(szablon, wartosci):
    """Podstawia {pole} w szablonie. Nieznane pola zostają puste."""
    return re.sub(r"\{([^{}]+)\}", lambda m: str(wartosci.get(m.group(1).strip(), "") or ""), szablon or "")


def z_malej(tekst, jezyk):
    """'Jesion' -> 'jesion' w środku tytułu (PL, EN). Nazw własnych typu 'Golden Hour' nie rusza."""
    if jezyk not in ("pl", "en") or not tekst:
        return tekst
    reszta = tekst[1:]
    if any(ch.isupper() for ch in reszta):
        return tekst
    return tekst[0].lower() + reszta


def obraz(media):
    nodes = (media or {}).get("nodes") or []
    for m in nodes:
        if m and m.get("image"):
            return m["id"], m["image"]["url"]
    return None, None


# ---------------------------------------------------------------- opcje wariantu

def opisz_opcje(p, v, jezyk, J, U, tl_opcji, ostrzezenia):
    """Dla jednego wariantu zwraca listę opcji z wartościami w języku feedu."""
    id_wartosci = {(o["name"], w["name"]): w["id"] for o in p["options"] for w in o["optionValues"]}
    wynik = []
    for so in v["selectedOptions"]:
        nazwa, wartosc = so["name"], so["value"]
        if norm(nazwa) == "title":
            continue  # produkt bez wariantów
        definicja = U["opcje"].get(norm(nazwa))
        if definicja is None:
            ostrzezenia.append(f"Opcja „{nazwa.strip()}” nie ma wiersza w zakładce Opcje ({p['handle']}) – "
                               "trafi tylko do tytułu. Dopisz ją, żeby ustalić jej rolę.")
            definicja = {}
        wpis = U["slownik"].get((norm(nazwa), norm(wartosc))) or {}

        # Nazwa w języku feedu: tłumaczenie ze Shopify, a gdy go brak – nazwa ze Shopify
        ze_shopify = wartosc
        if jezyk != "en":
            ze_shopify = (tl_opcji.get(id_wartosci.get((nazwa, wartosc)), {}) or {}).get(jezyk) or ""
            if not ze_shopify and not wpis.get(f"wartość_{J}") and not wpis.get(f"fragment_tytułu_{J}"):
                ostrzezenia.append(f"Brak tłumaczenia {jezyk.upper()} w Shopify: {nazwa.strip()} = „{wartosc}” "
                                   f"({p['handle']}). Użyto nazwy angielskiej.")
            ze_shopify = ze_shopify or wartosc

        # Atrybut Google (color/material/size): 1) Słownik  2) Shopify
        tekst = (wpis.get(f"wartość_{J}") or "").strip() or ze_shopify

        # Fragment tytułu: 1) Słownik („-” = pomiń)  2) przedrostek z zakładki Opcje + nazwa ze Shopify
        fragment = (wpis.get(f"fragment_tytułu_{J}") or "").strip()
        if fragment == "-":
            fragment = ""
        elif not fragment:
            fragment = (definicja.get(f"przedrostek_{J}") or "") + z_malej(ze_shopify, jezyk)

        wynik.append({
            "nazwa": nazwa.strip(),
            "wartosc_shopify": wartosc,
            "tekst": tekst,
            "fragment": fragment if tak(definicja.get("w_tytule"), True) else "",
            "kolejnosc": float(definicja.get("kolejność_w_tytule") or 9),
            "atrybut": norm(definicja.get("atrybut_google")),
            "do_zdjec": tak(definicja.get("rozróżnia_zdjęcia")),
            "etykieta": norm(definicja.get("etykieta")),
            "etykieta_wartosc": (wpis.get("etykieta") or "").strip(),
            "na_zamowienie": norm(wpis.get("typ_wariantu")) == "na_zamowienie",
        })
    return wynik


def klucz_zdjecia(v, opcje_zdjec):
    return tuple(norm(so["value"]) for so in v["selectedOptions"] if norm(so["name"]) in opcje_zdjec)


# ---------------------------------------------------------------- oferty

def zbuduj_oferty(feed, produkty_shopify, tl_opcji, U, ostrzezenia, statystyka):
    """Zwraca listę ofert (każda = jeden wariant) dla jednego feedu, w kształcie niezależnym od platformy."""
    ust = U["ogolne"]
    jezyk = norm(feed["język"])
    J = KOLUMNY_JEZYKA.get(jezyk, "EN")
    waluta = feed["waluta"].strip().upper()
    kraj = feed["kraj_cennika"].strip().upper()
    separator = f' {ust.get("Separator w tytule", "–").strip()} '
    pomijaj_zamowienia = norm(ust.get("Warianty na zamówienie (inny kolor)", "POMIŃ")) != "pokaż"
    pomijaj_bez_zdjec = norm(ust.get("Warianty bez pasującego zdjęcia", "POMIŃ")) != "pokaż"
    opcje_zdjec = {k for k, d in U["opcje"].items() if tak(d.get("rozróżnia_zdjęcia"))}
    oferty = []

    for p in produkty_shopify:
        if not p.get("onlineStoreUrl"):
            statystyka["produkt nieopublikowany"] += len(p["variants"]["nodes"])
            continue
        handle_en = p["handle"]
        up = U["produkty"].get(handle_en)
        if up is None:
            ostrzezenia.append(f"Nowy produkt bez wiersza w zakładce Produkty: {handle_en} – użyto ustawień domyślnych.")
            up = {}
        if norm(up.get("w_feedzie")) == "nie":
            statystyka["produkt wyłączony w panelu"] += len(p["variants"]["nodes"])
            continue

        pid = p["id"].split("/")[-1]
        handle = tlumaczenie(p, jezyk, "handle") or handle_en
        tytul_produktu = (up.get(f"tytuł_{J} (nadpisanie)") or "").strip() \
            or tlumaczenie(p, jezyk, "title") or p["title"]
        opis = bez_html(tlumaczenie(p, jezyk, "body_html") or p["descriptionHtml"])

        # --- zdjęcia: które pasują do jakiej kombinacji gatunek/kolor/drzwi
        warianty = p["variants"]["nodes"]
        zdjecia_produktu = [(m["id"], m["image"]["url"]) for m in p["media"]["nodes"] if m and m.get("image")]
        zdjecie_kombinacji, zdjecia_cudze = {}, {}
        for v in warianty:
            mid, url = obraz(v.get("media"))
            if url:
                k = klucz_zdjecia(v, opcje_zdjec)
                zdjecie_kombinacji.setdefault(k, (mid, url))
                zdjecia_cudze.setdefault(mid, set()).add(k)
        glowna = (up.get("zdjęcie_główne_pokazuje") or "").strip()
        klucz_glowny = tuple(norm(x) for x in glowna.split("/")) if glowna else \
            (klucz_zdjecia(warianty[0], opcje_zdjec) if warianty else ())
        if zdjecia_produktu and zdjecia_produktu[0][0] not in zdjecia_cudze:
            # zdjęcie główne pokazuje kombinację z zdjęcie_główne_pokazuje (domyślnie: pierwszy wariant),
            # więc nie dokładamy go jako dodatkowego do innych kolorów
            zdjecia_cudze[zdjecia_produktu[0][0]] = {klucz_glowny}

        # --- treści wspólne dla wszystkich wariantów produktu
        wyrozniki = []
        if tak(up.get("wyróżniki_z_shopify"), True):
            for w in metapole(p, "wyrozniki", jezyk):
                w = oczysc(w)
                if w and not w.endswith("?"):  # pytania to nie są cechy produktu
                    wyrozniki.append(w[:150])
        szczegoly = []
        # Wymiary z metapola opisują wersję standardową. Gdy produkt ma warianty różniące się rozmiarem
        # (Length, Configuration), nie dokładamy ich do ofert, bo byłyby błędne dla innych rozmiarów.
        rozmiar_w_wariantach = any(norm((U["opcje"].get(norm(o["name"])) or {}).get("atrybut_google")) == "size"
                                   and len(o["optionValues"]) > 1 for o in p["options"])
        for linia in ([] if rozmiar_w_wariantach else metapole(p, "wymiary", jezyk)):
            if ":" not in linia or re.search(r"contact|kontakt|skontaktuj", linia, re.I):
                continue
            a, b = (oczysc(x) for x in linia.split(":", 1))
            if a and b:
                szczegoly.append(f"{SEKCJA_WYMIARY.get(jezyk, 'Dimensions')}:{a}:{b}")
        dmin, dmax = up.get("min_dni_realizacji", ""), up.get("max_dni_realizacji", "")
        if not str(dmin).strip() or not str(dmax).strip():
            dmin, dmax = dni_realizacji((p.get("czas_realizacji") or {}).get("value", ""))

        for v in warianty:
            vid = v["id"].split("/")[-1]
            opcje = opisz_opcje(p, v, jezyk, J, U, tl_opcji, ostrzezenia)

            if pomijaj_zamowienia and any(o["na_zamowienie"] for o in opcje):
                statystyka["wariant „inny kolor – na zamówienie”"] += 1
                continue

            atrybuty = {"color": "", "material": "", "size": ""}
            etykiety = {"gatunek": "", "wykończenie": ""}
            for o in opcje:
                if o["atrybut"] in atrybuty and not atrybuty[o["atrybut"]]:
                    atrybuty[o["atrybut"]] = o["tekst"]
                if o["etykieta"] in etykiety and not etykiety[o["etykieta"]]:
                    domyslna = o["wartosc_shopify"].split()[0].lower() if o["etykieta"] == "gatunek" else \
                        ("natural" if norm(o["wartosc_shopify"]).startswith("natural") else "stained")
                    etykiety[o["etykieta"]] = o["etykieta_wartosc"] or domyslna
            atrybuty["material"] = atrybuty["material"] or (up.get(f"materiał_{J}") or "").strip()
            etykiety["gatunek"] = etykiety["gatunek"] or (up.get("gatunek_domyślny") or "").strip()

            # --- zdjęcie: wariantu → innego wariantu w tym samym gatunku/kolorze → główne (tylko dla kombinacji z głównego zdjęcia)
            k = klucz_zdjecia(v, opcje_zdjec)
            mid, url = obraz(v.get("media"))
            if not url and k in zdjecie_kombinacji:
                mid, url = zdjecie_kombinacji[k]
            if not url and k == klucz_glowny and zdjecia_produktu:
                mid, url = zdjecia_produktu[0]
            if not url:
                opis_kombinacji = " / ".join(so["value"] for so in v["selectedOptions"]
                                             if norm(so["name"]) in opcje_zdjec) or "—"
                statystyka["brak zdjęcia dla kombinacji"] += 1
                statystyka.setdefault("_brakujace_zdjecia", set()).add(f"{p['title']}: {opis_kombinacji}")
                if pomijaj_bez_zdjec:
                    continue
                if zdjecia_produktu:
                    mid, url = zdjecia_produktu[0]
            dodatkowe = [u for (i, u) in zdjecia_produktu
                         if u != url and (i not in zdjecia_cudze or k in zdjecia_cudze[i])][:ILE_ZDJEC_DODATKOWYCH]

            # --- cena dla rynku
            c = v.get(f"cena_{kraj}")
            if not c:
                statystyka["brak ceny"] += 1
                ostrzezenia.append(f"Brak ceny dla kraju {kraj}: {handle_en} / {v['title']} – pominięto.")
                continue
            if c["price"]["currencyCode"] != waluta:
                statystyka["inna waluta niż w feedzie"] += 1
                ostrzezenia.append(
                    f"Feed {feed['feed_id']}: Shopify podał cenę w {c['price']['currencyCode']} zamiast {waluta} "
                    f"dla kraju {kraj} – sprawdź walutę rynku. Pominięto {handle_en} / {v['title']}.")
                continue
            cena, promocja = float(c["price"]["amount"]), ""
            stara = c.get("compareAtPrice")
            if stara and float(stara["amount"]) > cena:  # cena porównawcza 0 lub niższa = brak promocji
                promocja = f"{cena:.2f} {waluta}"
                cena = float(stara["amount"])

            # --- tytuł
            fragmenty = [o["fragment"] for o in sorted(opcje, key=lambda o: o["kolejnosc"]) if o["fragment"]]
            tytul = wypelnij(feed["szablon_tytułu"], {"tytul_produktu": tytul_produktu,
                                                     "cechy_wariantu": ", ".join(fragmenty)}) \
                if fragmenty else tytul_produktu
            tytul = tytul.replace(" – ", separator).strip(" –")

            wspolne = {"domena": ust["Domena sklepu"].rstrip("/"), "prefiks_jezyka": feed["prefiks_języka"].strip(),
                       "handle": handle, "id_wariantu": vid, "waluta": waluta,
                       "feed_label": feed["feed_label"].strip()}
            waga = (v.get("inventoryItem") or {}).get("measurement", {}).get("weight") or {}
            sku = (v.get("sku") or "").strip()
            if not sku:
                statystyka["wariant bez SKU (mpn puste)"] += 1

            oferta = {
                "id": ust["Prefiks ID oferty"] + pid + "_" + vid,
                "id_grupy": pid,
                "tytul": tytul,
                "opis": opis,
                "link": wypelnij(feed["szablon_url"], wspolne),
                "link_reklamy": wypelnij(feed.get("szablon_url_reklamy", ""), wspolne),
                "zdjecie": url or "",
                "zdjecia_dodatkowe": ",".join(dodatkowe),
                "dostepnosc": "in_stock" if v["availableForSale"] else "out_of_stock",
                "cena": f"{cena:.2f} {waluta}",
                "cena_kwota": f"{cena:.2f}",
                "cena_promocyjna": promocja,
                "waluta": waluta,
                "marka": ust["Marka (brand)"],
                "sku": sku,
                "mpn": sku,
                "identyfikator_istnieje": "no",
                "stan": ust.get("Stan (condition)", "new"),
                "kategoria_google": up.get("google_product_category", ""),
                "typ_produktu": up.get("product_type", ""),
                "kolor": atrybuty["color"],
                "rozmiar": atrybuty["size"],
                "material": atrybuty["material"],
                "waga": f"{waga['value']:g} kg" if waga.get("value") else "",
                "dni_min": dmin, "dni_max": dmax,
                "linia": up.get("linia", ""),
                "kategoria": up.get("kategoria", ""),
                "gatunek": etykiety["gatunek"],
                "wykonczenie": etykiety["wykończenie"],
                "priorytet": up.get("priorytet", ""),
                "jezyk": jezyk,
                "kraje": feed.get("kraje_docelowe", ""),
                "feed_label": feed["feed_label"].strip(),
            }
            for i in range(ILE_WYROZNIKOW):
                oferta[f"wyroznik_{i + 1}"] = wyrozniki[i] if i < len(wyrozniki) else ""
            for i in range(ILE_SZCZEGOLOW):
                oferta[f"szczegol_{i + 1}"] = szczegoly[i] if i < len(szczegoly) else ""
            oferty.append(oferta)
    return oferty


def oferta_na_wiersz(oferta, profil):
    return [" ".join(wypelnij(zrodlo, oferta).split()) for _, zrodlo in profil]
