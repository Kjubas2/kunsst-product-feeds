"""
Wymogi platform – czego dana platforma wymaga od pliku feedu.

Kolumny pliku i ich źródła ustawia się w panelu: ustawienia/profile/<profil>.csv.
Tutaj są tylko twarde zasady platformy, których panel nie powinien móc złamać:
  - które kolumny muszą być wypełnione (oferta bez nich jest pomijana),
  - maksymalne długości (dłuższe teksty są przycinane z ostrzeżeniem),
  - format pliku.

Nowa platforma = nowy wpis w WYMOGI + nowy plik profilu w ustawieniach.
"""
import gzip

WYMOGI = {
    "google": {
        "opis": "Google Merchant Center (także Microsoft Merchant Center – ten sam format)",
        "format": "tsv",
        "wymagane": ["id", "title", "description", "link", "image_link", "availability", "price", "brand"],
        "maks_dlugosc": {"title": 150, "description": 5000, "color": 100, "size": 100, "material": 200,
                         "product_type": 750, "product_highlight": 150, "product_detail": 1000,
                         "custom_label_0": 100, "custom_label_1": 100, "custom_label_2": 100,
                         "custom_label_3": 100, "custom_label_4": 100},
    },
    # Przykład na przyszłość – jeszcze nieaktywne (patrz instrukcje/4-jak-dziala-generator.md):
    # "openai": {"format": "csv.gz", "wymagane": [...], "maks_dlugosc": {...}},
    # "meta":   {"format": "csv",    "wymagane": [...], "maks_dlugosc": {...}},
}


def sprawdz(wiersze, kolumny, profil, feed_id, ostrzezenia):
    """Przycina za długie teksty i odrzuca oferty bez wymaganych pól. Zwraca (dobre_wiersze, odrzucone)."""
    w = WYMOGI[profil]
    indeksy_wym = [i for i, k in enumerate(kolumny) if k in w["wymagane"]]
    dobre, odrzucone = [], 0
    for wiersz in wiersze:
        braki = [kolumny[i] for i in indeksy_wym if not wiersz[i]]
        if braki:
            odrzucone += 1
            ostrzezenia.append(f"{feed_id}: oferta {wiersz[0]} pominięta – puste wymagane pola: {', '.join(braki)}.")
            continue
        for i, k in enumerate(kolumny):
            limit = w["maks_dlugosc"].get(k)
            if limit and len(wiersz[i]) > limit:
                if k == "title":
                    ostrzezenia.append(f"{feed_id}: tytuł dłuższy niż {limit} znaków przycięty ({wiersz[0]}).")
                wiersz[i] = wiersz[i][:limit].rstrip(" ,–-")
        dobre.append(wiersz)
    return dobre, odrzucone


def zapisz(sciezka, kolumny, wiersze, profil):
    """Zapisuje plik w formacie platformy. Zwraca nazwę zapisanego pliku."""
    fmt = WYMOGI[profil]["format"]
    if fmt == "tsv":
        # Google: jedna oferta = jedna linia, tabulatory, bez cudzysłowów.
        with open(sciezka + ".tsv", "w", encoding="utf-8", newline="") as f:
            f.write("\t".join(kolumny) + "\n")
            for w in wiersze:
                f.write("\t".join(k.replace("\t", " ") for k in w) + "\n")
        return sciezka + ".tsv"
    if fmt in ("csv", "csv.gz"):
        import csv
        import io
        bufor = io.StringIO()
        pisarz = csv.writer(bufor)
        pisarz.writerow(kolumny)
        pisarz.writerows(wiersze)
        if fmt == "csv":
            with open(sciezka + ".csv", "w", encoding="utf-8", newline="") as f:
                f.write(bufor.getvalue())
            return sciezka + ".csv"
        with gzip.open(sciezka + ".csv.gz", "wt", encoding="utf-8", newline="") as f:
            f.write(bufor.getvalue())
        return sciezka + ".csv.gz"
    raise ValueError(f"Nieznany format {fmt}")
