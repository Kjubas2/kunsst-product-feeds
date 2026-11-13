"""
GENERATOR FEEDÓW KUNSST – plik główny.

Co robi po kolei:
  1. Czyta ustawienia z folderu ustawienia/ (te same zakładki co w arkuszu).
  2. Pobiera produkty ze Shopify (tylko odczyt).
  3. Dla każdego aktywnego feedu (feedy.csv, aktywny = TAK) buduje plik w folderze feedy/.
  4. Sprawdza bezpieczniki – jeśli coś wygląda podejrzanie, NIE nadpisuje starego pliku.
  5. Zapisuje raport w raporty/ostatnie-uruchomienie.md.

Uruchamia go automatycznie GitHub (plik .github/workflows/generuj-feedy.yml).
Ręcznie (dla zaawansowanych):  python generator/generuj.py
Test bez Shopify (na zapisanych danych):  python generator/generuj.py --dane-z-pliku plik.json
"""
import csv
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from budowanie import KOLUMNY_GOOGLE, wczytaj_ustawienia, zbuduj_feed  # noqa: E402
import shopify  # noqa: E402

KATALOG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USTAWIENIA = os.path.join(KATALOG, "ustawienia")
FEEDY = os.path.join(KATALOG, "feedy")
RAPORT = os.path.join(KATALOG, "raporty", "ostatnie-uruchomienie.md")


def ile_ofert_w_pliku(sciezka):
    if not os.path.exists(sciezka):
        return None
    with open(sciezka, encoding="utf-8") as f:
        return max(sum(1 for _ in f) - 1, 0)


def procent(tekst, domyslnie):
    try:
        return float(str(tekst).replace("%", "").strip()) / 100
    except ValueError:
        return domyslnie


def main():
    ust, feedy, ustawienia_produktow, slownik = wczytaj_ustawienia(USTAWIENIA)
    jezyki = sorted({f["język"].strip().lower() for f in feedy})
    kraje = sorted({f["kraj_cennika"].strip().upper() for f in feedy})

    if "--dane-z-pliku" in sys.argv:
        with open(sys.argv[sys.argv.index("--dane-z-pliku") + 1], encoding="utf-8") as f:
            produkty = json.load(f)
    else:
        produkty = shopify.pobierz_produkty(ust["Adres sklepu (myshopify)"], ust.get("Wersja API Shopify", "2026-10"),
                                            jezyki, kraje)

    min_ofert = int(ust.get("Bezpiecznik: min. liczba ofert w feedzie", "50") or 50)
    max_spadek = procent(ust.get("Bezpiecznik: maks. spadek liczby ofert", "30%"), 0.3)

    teraz = datetime.datetime.now(datetime.timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=1))).strftime("%Y-%m-%d %H:%M")
    linie = [f"# Ostatnie uruchomienie generatora: {teraz} (czas polski zimowy)", "",
             f"Produktów pobranych ze Shopify: **{len(produkty)}**", "",
             "| Feed | Ofert teraz | Ofert poprzednio | Wynik |", "|---|---|---|---|"]
    ostrzezenia, zatrzymane = [], []

    for feed in feedy:
        if feed["kanał"].strip() != "Google Merchant Center":
            linie.append(f"| {feed['feed_id']} | – | – | pominięty (kanał {feed['kanał']} jeszcze nieobsługiwany) |")
            continue
        wiersze = zbuduj_feed(feed, produkty, ust, ustawienia_produktow, slownik, ostrzezenia)
        sciezka = os.path.join(FEEDY, f"{feed['feed_id']}.tsv")
        poprzednio = ile_ofert_w_pliku(sciezka)

        problem = None
        if len(wiersze) < min_ofert:
            problem = f"za mało ofert ({len(wiersze)} < {min_ofert})"
        elif poprzednio and len(wiersze) < poprzednio * (1 - max_spadek):
            problem = f"spadek z {poprzednio} do {len(wiersze)} ofert"

        if problem:
            zatrzymane.append(feed["feed_id"])
            linie.append(f"| {feed['feed_id']} | {len(wiersze)} | {poprzednio} | ⛔ NIE zapisano – {problem}. Stary plik zostaje |")
            continue

        os.makedirs(FEEDY, exist_ok=True)
        with open(sciezka, "w", encoding="utf-8", newline="") as f:
            zapis = csv.writer(f, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
            zapis.writerow(KOLUMNY_GOOGLE)
            zapis.writerows([[k.replace("\t", " ").replace("\r", "") for k in w] for w in wiersze])
        linie.append(f"| {feed['feed_id']} | {len(wiersze)} | {poprzednio if poprzednio is not None else '–'} | ✅ zapisano feedy/{feed['feed_id']}.tsv |")

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
