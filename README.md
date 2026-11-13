# KUNSST – generator feedów produktowych

To repozytorium samo tworzy feedy produktowe (listy produktów dla Google Merchant Center,
a później także dla ChatGPT i innych kanałów) z danych sklepu **kunsst.com** w Shopify.

**Nic tu nie trzeba klikać na co dzień.** Feedy odświeżają się same co 6 godzin.

---

## Mapa folderów – co gdzie jest

| Folder / plik | Co zawiera | Czy edytujesz? |
|---|---|---|
| 📁 `ustawienia/` | Ustawienia feedów – te same zakładki co w arkuszu „KUNSST_feedy_panel” | ✅ **Tak – tylko tutaj** |
| ├ `feedy.csv` | Lista feedów: język, waluta, kraje, szablon linku i tytułu. Kolumna `aktywny` = TAK/NIE | ✅ |
| ├ `produkty.csv` | Ustawienia per produkt: własny tytuł, typ produktu, materiał, kolor, czas realizacji, etykiety | ✅ |
| ├ `slownik.csv` | Tłumaczenie wariantów z Shopify na kolor/rozmiar/materiał i fragmenty tytułu | ✅ |
| └ `ustawienia.csv` | Ustawienia wspólne: domena, marka, bezpieczniki | rzadko |
| 📁 `feedy/` | **Gotowe pliki dla Google** (`PL_PLN.tsv`, `DE_EUR.tsv`…). Tworzone automatycznie | ❌ Nie |
| 📁 `raporty/` | `ostatnie-uruchomienie.md` – ile ofert, czy były problemy | ❌ Tylko czytasz |
| 📁 `instrukcje/` | Instrukcje krok po kroku (klucz Shopify, sekrety, podpięcie do Merchant Center) | czytasz |
| 📁 `generator/` | Program, który robi całą pracę | ❌ Nie |
| 📁 `.github/workflows/` | Harmonogram (co 6 h) | ❌ Nie |

> Docelowo ustawienia będą czytane prosto z arkusza Google. Do tego czasu edytujesz pliki
> w folderze `ustawienia/` (kliknij plik → ikona ołówka → „Commit changes”).

---

## Jak to działa (w 5 krokach)

1. GitHub co 6 godzin uruchamia generator (albo od razu po zmianie w `ustawienia/`).
2. Generator czyta produkty ze Shopify – **tylko odczyt**, niczego w sklepie nie zmienia.
3. Dla każdego feedu z `aktywny = TAK` buduje plik w `feedy/`.
4. **Bezpieczniki:** jeśli ofert jest podejrzanie mało, stary plik zostaje, a Ty dostajesz e-mail.
5. Merchant Center codziennie pobiera pliki z `feedy/` pod stałym adresem.

---

## Najczęstsze sytuacje

| Sytuacja | Co zrobić |
|---|---|
| Zmieniłem cenę / opis / zdjęcie w Shopify | Nic. Feed zaktualizuje się sam w ciągu 6 h |
| Dodałem nowy produkt | Nic – trafi do feedu automatycznie. Dla porządku dopisz go w `produkty.csv` |
| Dodałem nowy wariant (np. nowy kolor) | Dopisz wiersz w `slownik.csv` (raport pokaże, czego brakuje) |
| Chcę wyłączyć produkt z feedu | `produkty.csv` → kolumna `w_feedzie` = NIE |
| Chcę nowy feed (np. francuski) | `feedy.csv` → zmień `aktywny` na TAK |
| Chcę wygenerować feedy teraz | Zakładka **Actions** → „Generuj feedy” → **Run workflow** |
| Przyszedł e-mail „Run failed” | Otwórz `raporty/ostatnie-uruchomienie.md` – tam jest powód |

---

## Ważne zasady

- **Treść produktu zmieniasz w Shopify**, nie tutaj. Tutaj tylko to, co dotyczy feedów.
- **Nie zmieniaj „Prefiks ID oferty”** w `ustawienia.csv` – Google straciłby historię produktów.
- Dane dostępowe do Shopify są w **sekretach GitHuba** (Settings → Secrets), nigdy w plikach.
