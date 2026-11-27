"""
Budowanie Shopify Master Feed: jeden wiersz = jeden wariant w jednym rynku.

Treść pochodzi ze Shopify (także tłumaczenia nazw kolorów, gatunków i konfiguracji).
Pliki z 01.settings mówią tylko, jak ją ułożyć: które rynki, jak budować tytuł,
które warianty pominąć i jakie wyjątki w nazwach zastosować (05.dictionary).

Każda platforma (03.platforms/...) bierze gotowe wiersze stąd – nic nie liczy od nowa.
"""
import collections
import html
import json
import re

from settings import norm, yes

HIGHLIGHTS, DETAILS, EXTRA_IMAGES = 6, 6, 10
SPECIES = ["oak", "ash", "beech", "walnut", "maple", "cherry", "birch", "pine", "elm", "alder"]
DIMENSIONS_SECTION = {"en": "Dimensions", "de": "Abmessungen", "pl": "Wymiary", "fr": "Dimensions"}
WEIGHT_UNITS = {"KILOGRAMS": "kg", "GRAMS": "g", "POUNDS": "lb", "OUNCES": "oz"}

COLUMNS = (["market", "offer_id", "product_id", "variant_id", "sku", "product_name", "variant_features", "title",
            "description", "product_url", "image_link", "additional_image_links", "availability", "price",
            "sale_price", "currency", "brand", "color", "material", "size", "wood_species", "finish",
            "product_line", "category", "priority", "google_product_category", "product_type"]
           + [f"highlight_{i}" for i in range(1, HIGHLIGHTS + 1)]
           + [f"detail_{i}" for i in range(1, DETAILS + 1)]
           + ["weight", "ready_to_ship", "handling_days_min", "handling_days_max",
              "shipping_country", "shipping_service", "shipping_price", "transit_days_min", "transit_days_max",
              "in_feeds", "skip_reason"])


# ---------------------------------------------------------------- pomocnicze

def one_line(s):
    return " ".join((s or "").split())


def rich_text(value):
    """Pole Shopify typu 'rich text' (JSON) → lista akapitów / punktów."""
    if not value:
        return []
    try:
        tree = json.loads(value)
    except ValueError:
        return [value]
    out = []

    def text(n):
        if n.get("type") == "text":
            return n.get("value", "")
        return "".join(text(c) for c in n.get("children", []))

    def walk(n):
        if n.get("type") in ("paragraph", "list-item", "heading"):
            t = text(n).strip()
            if t:
                out.append(t)
        else:
            for c in n.get("children", []):
                walk(c)

    walk(tree)
    return out


def plain_text(h):
    if not h:
        return ""
    h = re.sub(r"<\s*br\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"</\s*(p|li|h\d|div)\s*>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", "", h)
    return one_line(html.unescape(h).replace("\xa0", " "))[:5000]


def clean(s):
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s*\([^)]*(in|Zoll|In|cala|cali|cale)\)", "", s)  # bez wymiarów w calach
    return one_line(s)


def translated(product, lang, key):
    if lang == "en":
        return None
    for t in product.get(f"t_{lang}") or []:
        if t["key"] == key and t["value"]:
            return t["value"]
    return None


def metafield_lines(product, name, lang):
    m = product.get(name)
    if not m:
        return []
    if lang != "en" and m.get(f"t_{lang}"):
        return rich_text(m[f"t_{lang}"][0]["value"])
    return rich_text(m["value"])


def days(value):
    """Wartość metapola liczbowego → int albo None."""
    try:
        return int(float((value or {}).get("value")))
    except (TypeError, ValueError):
        return None


def is_true(field):
    return str((field or {}).get("value", "")).strip().lower() == "true"


def ready_to_ship(p, v):
    """Gotowe do wysyłki = pole wariantu (gdy ustawione) albo pole produktu, i są sztuki na stanie
    (albo stan nie jest śledzony). Ta sama zasada co na stronie produktu (snippets/kub-shipping-line)."""
    flag = v.get("ready_to_ship") if v.get("ready_to_ship") else p.get("ready_to_ship")
    if not is_true(flag):
        return False
    tracked = (v.get("inventoryItem") or {}).get("tracked")
    return tracked is False or (v.get("inventoryQuantity") or 0) > 0


def handling(p, v, ship, warnings):
    """Czas od zamówienia do nadania (dni robocze) → (od, do, gotowe_do_wysyłki)."""
    if ready_to_ship(p, v):
        rd = ship.get("ready_dispatch") if ship else None
        if rd:
            return rd[0], rd[1], True
        warnings.append("Brak czasu wysyłki gotowych sztuk (Metaobiekty → Shipping settings → default) – "
                        "gotowe warianty dostały czas produkcji.")
    lo = days(v.get("production_from"))
    hi = days(v.get("production_to"))
    if lo is None:
        lo, hi = days(p.get("production_from")), days(p.get("production_to"))
    if lo is None:
        warnings.append(f"Brak czasu realizacji (pole „Production time from/to”) w produkcie {p['title']} – "
                        "feedy nie podają czasu realizacji, Google przyjmie własne założenia.")
        return "", "", False
    return lo, hi if hi is not None else lo, False


def zone_for(profile, country):
    exact = next((z for z in profile["zones"] if country in z["countries"]), None)
    return exact or next((z for z in profile["zones"] if "*" in z["countries"]), None)


def condition_ok(c, amount, currency, warnings, where):
    if c["field"] != "TOTAL_PRICE":
        warnings.append(f"Wysyłka {where}: warunek „{c['field']}” (np. waga) – generator liczy tylko progi cenowe, "
                        "ta stawka jest pomijana w feedach.")
        return False
    if c["currency"] and c["currency"] != currency:
        warnings.append(f"Wysyłka {where}: próg w {c['currency']}, a ceny w feedzie w {currency} – "
                        "ta stawka jest pomijana w feedach. Ustaw próg w walucie kraju.")
        return False
    if c["operator"] == "GREATER_THAN_OR_EQUAL_TO":
        return amount >= c["amount"] - 1e-9
    if c["operator"] == "LESS_THAN_OR_EQUAL_TO":
        return amount <= c["amount"] + 1e-9
    warnings.append(f"Wysyłka {where}: nieznany warunek {c['operator']} – stawka pominięta.")
    return False


def shipping_rate(ship, variant_gid, country, amount, currency, warnings):
    """Najtańsza stawka ze Shopify, jaką zapłaci klient z danego kraju za JEDNĄ sztukę tego wariantu
    (progi cenowe liczone od ceny wariantu). → (nazwa, cena) albo None."""
    if not ship or ship.get("error") or not ship.get("profiles"):
        return None
    profile = next((pr for pr in ship["profiles"] if not pr["default"] and variant_gid in pr["variants"]), None) \
        or next((pr for pr in ship["profiles"] if pr["default"]), None)
    if not profile:
        return None
    zone = zone_for(profile, country)
    if not zone:
        warnings.append(f"Kraj {country} nie ma strefy w profilu wysyłki „{profile['name']}” (Ustawienia → Wysyłka "
                        "i dostawa) – oferty bez kosztu wysyłki. Dodaj strefę albo wyłącz feed tego kraju.")
        return None
    where = f"{zone['name']} ({profile['name']})"
    best, before = None, len(warnings)
    for m in zone["methods"]:
        if not m["active"]:
            continue
        if m["calculated"] or m["price"] is None:
            warnings.append(f"Wysyłka {where}: stawka „{m['name']}” jest liczona przez przewoźnika/aplikację – "
                            "generator jej nie zna i ją pomija.")
            continue
        if not all(condition_ok(c, amount, currency, warnings, where) for c in m["conditions"]):
            continue
        if m["price"] > 0 and m["currency"] != currency:
            warnings.append(f"Wysyłka {where}: stawka {m['price']:g} {m['currency']}, a ceny w feedzie w {currency} – "
                            "stawka pominięta. Ustaw ją w walucie kraju.")
            continue
        if best is None or m["price"] < best[1]:
            best = (m["name"], m["price"])
    if best is None and len(warnings) == before:
        warnings.append(f"Wysyłka {where}: dla części cen żadna stawka nie pasuje (luka między progami?) – "
                        "te oferty są bez kosztu wysyłki.")
    return best


def lower_first(text, lang):
    """'Lity jesion' → 'lity jesion' w środku tytułu (PL, EN). Nazw typu 'Golden Hour' nie zmienia."""
    if lang not in ("pl", "en") or not text or any(ch.isupper() for ch in text[1:]):
        return text
    return text[0].lower() + text[1:]


def species_in(text):
    words = re.findall(r"[a-z]+", norm(text))
    return next((w for w in words if w in SPECIES), "")


def first_image(media):
    for m in (media or {}).get("nodes") or []:
        if m and m.get("image"):
            return m["id"], m["image"]["url"]
    return None, None


# ---------------------------------------------------------------- opcje wariantu

def describe_options(p, v, lang, S, option_tr, warnings):
    """Opcje jednego wariantu z wartościami w języku rynku."""
    value_ids = {(norm(o["name"]), v_["name"]): v_["id"] for o in p["options"] for v_ in o["optionValues"]}
    out = []
    for so in v["selectedOptions"]:
        name, value = so["name"].strip(), so["value"]
        if norm(name) == "title":
            continue  # produkt bez wariantów
        rule = S["options"].get(norm(name))
        if rule is None:
            warnings.append(f"Opcja „{name}” ({p['handle']}) nie ma wiersza w 01.settings/04.variant_options.csv – "
                            "trafia tylko do tytułu. Dopisz ją, żeby ustalić jej rolę.")
            rule = {}
        entry = S["dictionary"].get((norm(name), norm(value))) or {}
        from_dict = (entry.get(lang) or "").strip()

        from_shopify = value
        if lang != "en":
            from_shopify = (option_tr.get(value_ids.get((norm(name), value)), {}) or {}).get(lang) or ""
            language_neutral = not re.search(r"[^\W\d_]{3,}", re.sub(r"(?i)\b(cm|mm)\b", "", value))
            if not from_shopify and not from_dict and not language_neutral:  # „110 cm” jest takie samo w każdym języku
                warnings.append(f"Brak tłumaczenia {lang.upper()} w Shopify: {name} = „{value}” ({p['handle']}) – "
                                "użyto nazwy angielskiej. Dodaj tłumaczenie w Shopify albo wpis w 05.dictionary.csv.")
            from_shopify = from_shopify or value

        text = from_dict or from_shopify
        in_title = yes(entry.get("show_in_title"), True)
        out.append({
            "name": name,
            "shopify_value": value,
            "text": text,
            "fragment": (rule.get(f"title_prefix_{lang}") or "") + lower_first(text, lang) if in_title else "",
            "order": float(rule.get("title_order") or 9),
            "role": norm(rule.get("role")),
            "label": norm(rule.get("label")),
        })
    return out


def image_key(v, image_options):
    return tuple(norm(so["value"]) for so in v["selectedOptions"] if norm(so["name"]) in image_options)


# ---------------------------------------------------------------- budowanie

def build(products, option_tr, S, warnings, ship=None):
    """Zwraca (wiersze Master Feed, plan zdjęć).

    plan zdjęć – {(product_id, nazwa produktu, priorytet, kombinacja): liczba wariantów bez zdjęcia}.
    """
    g = S["general"]
    markets = [(mid, m) for mid, m in S["markets"].items() if yes(m.get("enabled"))]
    image_options = {k for k, r in S["options"].items() if yes(r.get("image_must_match"))}
    skip_text = norm(g.get("skip_variants_containing", ""))
    skip_no_image = norm(g.get("variants_without_matching_image", "SKIP")) != "show_main_image"
    separator = g.get("title_separator", " – ") or " – "
    domain = g["shop_domain"].rstrip("/")
    photo_plan = collections.Counter()
    rows = []

    prepared = []
    for p in products:
        pid = p["id"].split("/")[-1]
        ps = S["products"].get(pid)
        if ps is None:
            warnings.append(f"Nowy produkt bez wiersza w 01.settings/03.products_settings.csv: {p['title']} "
                            f"(product_id {pid}) – trafia do feedów bez kategorii i etykiet. Dopisz go.")
            ps = {}
        variants = p["variants"]["nodes"]

        # --- zdjęcia: które pasują do jakiej kombinacji gatunek / kolor / drzwi
        product_images = [(m["id"], m["image"]["url"]) for m in p["media"]["nodes"] if m and m.get("image")]
        combo_image, image_owner = {}, {}
        for v in variants:
            mid, url = first_image(v.get("media"))
            if url:
                k = image_key(v, image_options)
                combo_image.setdefault(k, (mid, url))
                image_owner.setdefault(mid, set()).add(k)
        main = (ps.get("main_image_shows") or "").strip()
        main_key = tuple(norm(x) for x in main.split("/")) if main else \
            (image_key(variants[0], image_options) if variants else ())
        if product_images and product_images[0][0] not in image_owner:
            image_owner[product_images[0][0]] = {main_key}

        images = {}
        for v in variants:
            k = image_key(v, image_options)
            mid, url = first_image(v.get("media"))
            if not url and k in combo_image:
                mid, url = combo_image[k]
            if not url and k == main_key and product_images:
                mid, url = product_images[0]
            missing = not url
            if missing:
                combo = " / ".join(so["value"] for so in v["selectedOptions"]
                                   if norm(so["name"]) in image_options) or "—"
                if not (skip_text and any(skip_text in norm(so["value"]) for so in v["selectedOptions"])):
                    photo_plan[(pid, p["title"], ps.get("priority", ""), combo)] += 1
                if not skip_no_image and product_images:
                    mid, url = product_images[0]
            extra = [u for (i, u) in product_images
                     if u != url and (i not in image_owner or k in image_owner[i])][:EXTRA_IMAGES]
            images[v["id"]] = (url or "", extra, missing)

        size_varies = any(norm((S["options"].get(norm(o["name"])) or {}).get("role")) == "size"
                          and len(o["optionValues"]) > 1 for o in p["options"])
        times = {v["id"]: handling(p, v, ship, warnings) for v in variants}
        prepared.append((p, pid, ps, images, size_varies, times))

    for market_id, m in markets:
        lang = norm(m["language"])
        currency = m["currency"].strip().upper()
        country = m["prices_from_country"].strip().upper()
        path = (m.get("language_path") or "").strip()

        for p, pid, ps, images, size_varies, times in prepared:
            handle = translated(p, lang, "handle") or p["handle"]
            name = (ps.get(f"feed_title_{lang}") or "").strip() or translated(p, lang, "title") or p["title"]
            description = plain_text(translated(p, lang, "body_html") or p["descriptionHtml"])
            highlights = [clean(h)[:150] for h in metafield_lines(p, "highlights", lang)
                          if clean(h) and not clean(h).endswith("?")]
            details = []
            # Wymiary z metapola opisują wersję standardową – pomijamy je, gdy warianty różnią się rozmiarem.
            for line in ([] if size_varies else metafield_lines(p, "dimensions", lang)):
                if ":" not in line or re.search(r"contact|kontakt|skontaktuj", line, re.I):
                    continue
                a, b = (clean(x) for x in line.split(":", 1))
                if a and b:
                    details.append(f"{DIMENSIONS_SECTION.get(lang, 'Dimensions')}:{a}:{b}")
            species_default = species_in(p["title"])

            for v in p["variants"]["nodes"]:
                vid = v["id"].split("/")[-1]
                opts = describe_options(p, v, lang, S, option_tr, warnings)
                attrs = {"color": "", "material": "", "size": ""}
                species, finish = "", ""
                for o in opts:
                    if o["role"] in attrs and not attrs[o["role"]]:
                        attrs[o["role"]] = o["text"]
                    if o["label"] == "wood_species" and not species:
                        species = species_in(o["shopify_value"]) or norm(o["shopify_value"]).split(" ")[0]
                    if o["label"] == "finish" and not finish:
                        finish = "natural" if norm(o["shopify_value"]).startswith("natural") else "stained"
                species = species or species_default
                fragments = [o["fragment"] for o in sorted(opts, key=lambda o: o["order"]) if o["fragment"]]
                features = ", ".join(fragments)
                title = f"{name}{separator}{features}" if features else name

                image, extra, missing_image = images[v["id"]]
                dmin, dmax, ready = times[v["id"]]
                weight = (v.get("inventoryItem") or {}).get("measurement", {}).get("weight") or {}
                row = {
                    "market": market_id,
                    "offer_id": g["offer_id_prefix"].strip() + pid + "_" + vid,
                    "product_id": pid,
                    "variant_id": vid,
                    "sku": (v.get("sku") or "").strip(),
                    "product_name": name,
                    "variant_features": features,
                    "title": title,
                    "description": description,
                    "product_url": f"{domain}{path}/products/{handle}?variant={vid}&currency={currency}&country={country}",
                    "image_link": image,
                    "additional_image_links": ",".join(extra),
                    "availability": "available" if v["availableForSale"] else "not_available",
                    "price": "", "sale_price": "", "currency": currency,
                    "brand": g["brand"].strip(),
                    "color": attrs["color"], "material": attrs["material"], "size": attrs["size"],
                    "wood_species": species, "finish": finish,
                    "product_line": ps.get("product_line", ""), "category": ps.get("category", ""),
                    "priority": ps.get("priority", ""),
                    "google_product_category": ps.get("google_product_category", ""),
                    "product_type": ps.get("product_type", ""),
                    "weight": f"{weight['value']:g} {WEIGHT_UNITS.get(weight.get('unit'), 'kg')}"
                              if weight.get("value") else "",
                    "ready_to_ship": "YES" if ready else "NO",
                    "handling_days_min": dmin, "handling_days_max": dmax,
                    "shipping_country": "", "shipping_service": "", "shipping_price": "",
                    "transit_days_min": "", "transit_days_max": "",
                }
                for i in range(HIGHLIGHTS):
                    row[f"highlight_{i + 1}"] = highlights[i] if i < len(highlights) else ""
                for i in range(DETAILS):
                    row[f"detail_{i + 1}"] = details[i] if i < len(details) else ""

                # --- cena dla rynku
                reason = ""
                c = v.get(f"price_{country}")
                if not c:
                    reason = f"brak ceny dla kraju {country}"
                elif c["price"]["currencyCode"] != currency:
                    reason = f"Shopify podał cenę w {c['price']['currencyCode']} zamiast {currency}"
                else:
                    price, compare = float(c["price"]["amount"]), c.get("compareAtPrice")
                    if compare and float(compare["amount"]) > price:  # promocja
                        row["price"], row["sale_price"] = f"{float(compare['amount']):.2f}", f"{price:.2f}"
                    else:
                        row["price"] = f"{price:.2f}"
                    # --- koszt i czas dostawy dla kraju rynku (cena zapłacona = cena po promocji)
                    rate = shipping_rate(ship, v["id"], country, price, currency, warnings)
                    if rate:
                        row["shipping_country"] = country
                        row["shipping_service"] = rate[0].replace(":", " ").replace(",", " ")
                        row["shipping_price"] = f"{rate[1]:.2f}"
                        transit = (ship.get("transit") or {}).get(country)
                        if transit:
                            row["transit_days_min"], row["transit_days_max"] = transit
                        else:
                            warnings.append(f"Brak czasu transportu dla kraju {country} (Metaobiekty → Shipping "
                                            "country) – feedy bez czasu transportu do tego kraju.")

                # --- czy wariant trafia do feedów (pierwszy powód wygrywa)
                if not yes(ps.get("in_feeds"), True):
                    reason = "produkt wyłączony w 03.products_settings"
                elif not p.get("onlineStoreUrl"):
                    reason = "produkt niewidoczny w sklepie internetowym"
                elif skip_text and any(skip_text in norm(so["value"]) for so in v["selectedOptions"]):
                    reason = f"wariant „{g.get('skip_variants_containing', '').strip()}”"
                elif missing_image and skip_no_image:
                    combo = " / ".join(so["value"] for so in v["selectedOptions"]
                                       if norm(so["name"]) in image_options)
                    reason = f"brak zdjęcia: {combo}"
                row["in_feeds"] = "NO" if reason else "YES"
                row["skip_reason"] = reason
                if reason:
                    # w wierszach pominiętych bez długich tekstów – plik byłby zbyt duży
                    row["description"], row["additional_image_links"] = "", ""
                rows.append(row)
    return rows, photo_plan
