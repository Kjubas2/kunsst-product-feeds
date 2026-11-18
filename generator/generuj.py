"""
GENERATOR FEEDÓW KUNSST – plik główny.

Co robi po kolei:
  1. Czyta panel z folderu ustawienia/ (Ustawienia, Feedy, Produkty, Opcje, Słownik, profile/).
  2. Pobiera produkty i WSZYSTKIE ich warianty ze Shopify (tylko odczyt).
  3. Dla każdego aktywnego feedu buduje oferty (1 wariant = 1 oferta) w języku, walucie i cenach rynku.
  4. Układa oferty w kolumny według profilu platformy (np. profile/google.csv) i sprawdza wymogi platformy.
  5. Sprawdza bezpieczniki – jeśli coś wygląda podejrzanie, NIE nadpisuje starego pliku.
  6. Zapisuje pliki w feedy/ i raport w raporty/ostatnie-uruchomienie.md.

Uruchamia go automatycznie GitHub (plik .github/workflows/generuj-feedy.yml).
Test bez Shopify (na zapisanych danych):  python generator/generuj.py --dane-z-pliku plik.json
Zapis pobranych danych do pliku (do testów):  python generator/generuj.py --zapisz-dane plik.json
"""
import collections
import datetime
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from budowanie import oferta_na_wiersz, wczytaj_profil, wczytaj_ustawienia, zbuduj_oferty  # noqa: E402
import platformy  # noqa: E402
import shopify  # noqa: E402

KATALOG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USTAWIENIA = os.path.join(KATALOG, "ustawienia")
FEEDY = os.path.join(KATALOG, "feedy")
RAPORT = os.path.join(KATALOG, "raporty", "ostatnie-uruchomienie.md")


def ile_ofert_w_pliku(sciezka_bez_rozszerzenia):
    for sciezka in glob.glob(sciezka_bez_rozszerzenia + ".*"):
        if sciezka.endswith(".gz"):
            return None
        with open(sciezka, encoding="utf-8") as f:
            return max(sum(1 for _ in f) - 1, 0)
    return None


def procent(tekst, domyslnie):
    try:
        return float(str(tekst).replace("%", "").strip()) / 100
    except ValueError:
        return domyslnie


def main():
    U = wczytaj_ustawienia(USTAWIENIA)
    ust, feedy = U["ogolne"], U["feedy"]
    jezyki = sorted({f["język"].strip().lower() for f in feedy})
    kraje = sorted({f["kraj_cennika"].strip().upper() for f in feedy})

    if "--dane-z-pliku" in sys.argv:
        with open(sys.argv[sys.argv.index("--dane-z-pliku") + 1], encoding="utf-8") as f:
            dane = json.load(f)
        produkty, tl_opcji = dane["produkty"], dane["tlumaczenia_opcji"]
    else:
        produkty, tl_opcji = shopify.pobierz_produkty(
            ust["Adres sklepu (myshopify)"], ust.get("Wersja API Shopify", "2026-10"), jezyki, kraje)
    if "--zapisz-dane" in sys.argv:
        with open(sys.argv[sys.argv.index("--zapisz-dane") + 1], "w", encoding="utf-8") as f:
            json.dump({"produkty": produkty, "tlumaczenia_opcji": tl_opcji}, f, ensure_ascii=False)

    min_ofert = int(ust.get("Bezpiecznik: min. liczba ofert w feedzie", "50") or 50)
    max_spadek = procent(ust.get("Bezpiecznik: maks. spadek liczby ofert", "30%"), 0.3)
    wszystkich = sum(len(p["variants"]["nodes"]) for p in produkty)

    teraz = datetime.datetime.now(datetime.timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=1))).strftime("%Y-%m-%d %H:%M")
    linie = [f"# Ostatnie uruchomienie generatora: {teraz} (czas polski zimowy)", "",
             f"Pobrano ze Shopify: **{len(produkty)} produktów, {wszystkich} wariantów**.", "",
             "| Feed | Profil | Ofert w pliku | Poprzednio | Pominięte warianty | Wynik |",
             "|---|---|---|---|---|---|"]
    ostrzezenia, zatrzymane, szczegoly_pominiec = [], [], []
    brakujace_zdjecia = set()

    for feed in feedy:
        profil = (feed.get("profil") or "").strip().lower()
        if profil not in platformy.WYMOGI:
            linie.append(f"| {feed['feed_id']} | {profil or '–'} | – | – | – | pominięty: profil jeszcze nieobsługiwany |")
            continue
        kolumny_profilu = wczytaj_profil(USTAWIENIA, profil)
        kolumny = [k for k, _ in kolumny_profilu]

        statystyka = collections.Counter()
        oferty = zbuduj_oferty(feed, produkty, tl_opcji, U, ostrzezenia, statystyka)
        brakujace_zdjecia |= statystyka.pop("_brakujace_zdjecia", set())
        wiersze = [oferta_na_wiersz(o, kolumny_profilu) for o in oferty]
        wiersze, odrzucone = platformy.sprawdz(wiersze, kolumny, profil, feed["feed_id"], ostrzezenia)
        if odrzucone:
            statystyka["brak wymaganych pól"] += odrzucone

        sciezka = os.path.join(FEEDY, feed["feed_id"])
        poprzednio = ile_ofert_w_pliku(sciezka)
        pominiete = sum(v for k, v in statystyka.items() if k != "wariant bez SKU (mpn puste)")
        szczegoly_pominiec.append(f"- **{feed['feed_id']}**: " + (
            ", ".join(f"{k}: {v}" for k, v in statystyka.items()) or "brak"))

        problem = None
        if len(wiersze) < min_ofert:
            problem = f"za mało ofert ({len(wiersze)} < {min_ofert})"
        elif poprzednio and len(wiersze) < poprzednio * (1 - max_spadek):
            problem = f"spadek z {poprzednio} do {len(wiersze)} ofert"
        if problem:
            zatrzymane.append(feed["feed_id"])
            linie.append(f"| {feed['feed_id']} | {profil} | {len(wiersze)} | {poprzednio} | {pominiete} | "
                         f"⛔ NIE zapisano – {problem}. Stary plik zostaje |")
            continue

        os.makedirs(FEEDY, exist_ok=True)
        plik = platformy.zapisz(sciezka, kolumny, wiersze, profil)
        linie.append(f"| {feed['feed_id']} | {profil} | {len(wiersze)} | "
                     f"{poprzednio if poprzednio is not None else '–'} | {pominiete} | "
                     f"✅ zapisano feedy/{os.path.basename(plik)} |")

    linie += ["", "## Dlaczego część wariantów nie trafiła do feedu", ""] + szczegoly_pominiec
    if brakujace_zdjecia:
        linie += ["", "## Kombinacje bez zdjęcia (przypisz zdjęcie do wariantu w Shopify, a oferty pojawią się same)", ""]
        linie += [f"- {b}" for b in sorted(brakujace_zdjecia)]
    linie += ["", "## Ostrzeżenia", ""]
    linie += [f"- {o}" for o in dict.fromkeys(ostrzezenia)] or ["Brak – wszystko w porządku."]
    os.makedirs(os.path.dirname(RAPORT), exist_ok=True)
    with open(RAPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(linie) + "\n")
    print("\n".join(linie))

    if zatrzymane:
        # Kod błędu = GitHub wyśle e-mail o nieudanym uruchomieniu.
        sys.exit(f"Zatrzymano feedy: {', '.join(zatrzymane)} – szczegóły w raporty/ostatnie-uruchomienie.md")


if __name__ == "__main__":
    main()
