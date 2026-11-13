# Krok 3 – podpięcie feedu do Google Merchant Center

Merchant Center musi móc **pobrać plik feedu z internetu**, bez logowania.

## Decyzja przed podpięciem: skąd Google pobierze plik

| Opcja | Jak działa | Plusy | Minusy |
|---|---|---|---|
| **A. Repozytorium publiczne** | Plik dostępny pod adresem `https://raw.githubusercontent.com/Kjubas2/kunsst-feeds/main/feedy/EN_EUR.tsv` | Najprościej, zero dodatkowych kont | Każdy, kto zna adres, zobaczy pliki repozytorium (ceny i opisy i tak są publiczne na stronie; dane dostępowe zostają w sejfie) |
| **B. Repozytorium prywatne + osobne publiczne tylko na feedy** | Generator kopiuje same pliki feedów do drugiego, publicznego repozytorium | Ustawienia i program zostają prywatne | Jedno repozytorium więcej |

Decyzję podejmujesz Ty – Claude nie upublicznia niczego bez Twojej zgody.

## Dodanie feedu w Merchant Center (robi Claude po Twoim potwierdzeniu albo Ty)

1. Merchant Center → **Ustawienia → Źródła danych → Dodaj źródło produktów**.
2. **Plik → Użyj hostowanego URL** – wklej adres pliku, np. `.../feedy/EN_EUR.tsv`.
3. Ustaw:
   - język feedu (kolumna `język` w `ustawienia/feedy.csv`),
   - kraje (kolumna `kraje_docelowe`),
   - etykieta feedu (kolumna `feed_label`),
   - pobieranie: **codziennie**.
4. Miejsca docelowe: bezpłatne wyniki + reklamy produktowe. **Bez** lokalnego asortymentu.
5. Po 1–3 dniach: **Produkty → Diagnostyka** – sprawdzenie, czy oferty są zatwierdzone.
