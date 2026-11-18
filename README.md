# KUNSST – generator feedów produktowych

To repozytorium samo tworzy feedy produktowe (listy produktów dla Google Merchant Center,
a później także dla innych platform) z danych sklepu **kunsst.com** w Shopify.

**Nic tu nie trzeba klikać na co dzień.** Feedy odświeżają się same co 6 godzin.
Dokładne zasady działania krok po kroku: [`instrukcje/4-jak-dziala-generator.md`](instrukcje/4-jak-dziala-generator.md).

---

## Mapa folderów – co gdzie jest

| Folder / plik | Co zawiera | Czy edytujesz? |
|---|---|---|
| 📁 `ustawienia/` | **Panel sterowania** – te same zakładki, które trafią do arkusza Google | ✅ **Tak – tylko tutaj** |
| ├ `feedy.csv` | Lista feedów: platforma (profil), język, waluta, kraje, szablon linku i tytułu. `aktywny` = TAK/NIE | ✅ |
| ├ `produkty.csv` | Ustawienia per produkt: własny tytuł, kategoria Google, typ, etykiety, wykluczenie | ✅ |
| ├ `opcje.csv` | Rola każdej opcji wariantu (Color → kolor, Material → materiał, Length → rozmiar…) | rzadko |
| ├ `slownik.csv` | Wyjątki: gdy nazwa ze Shopify nie pasuje do feedu (np. „130 cm - Standard” → „130 cm”) | ✅ |
| ├ `ustawienia.csv` | Ustawienia wspólne: domena, marka, bezpieczniki, co robić z wariantami bez zdjęcia | rzadko |
| └ 📁 `profile/` | Układ kolumn pliku dla każdej platformy (`google.csv`; kolejne platformy później) | rzadko |
| 📁 `feedy/` | **Gotowe pliki** (`PL_PLN.tsv`, `DE_EUR.tsv`, `DE_CHF.tsv`…). Tworzone automatycznie | ❌ Nie |
| 📁 `raporty/` | `ostatnie-uruchomienie.md` – ile ofert, co pominięto i dlaczego, czego brakuje | ❌ Tylko czytasz |
| 📁 `instrukcje/` | Instrukcje krok po kroku | czytasz |
| 📁 `generator/` | Program, który robi całą pracę | ❌ Nie |
| 📁 `.github/workflows/` | Harmonogram (co 6 h) | ❌ Nie |

> Docelowo zakładki z `ustawienia/` będą czytane prosto z arkusza Google. Do tego czasu
> edytujesz pliki w przeglądarce (kliknij plik → ikona ołówka → „Commit changes”).

---

## Najczęstsze sytuacje

| Sytuacja | Co zrobić |
|---|---|
| Zmieniłem cenę / opis / zdjęcie / tłumaczenie w Shopify | Nic. Feed zaktualizuje się sam w ciągu 6 h |
| Przypisałem zdjęcie do wariantu (np. jesion + czarny) | Nic. Te warianty same pojawią się w feedzie |
| Dodałem nowy kolor do palety | Nic, jeśli kolor ma tłumaczenie PL/DE w Shopify. Dla feedu angielskiego dopisz zwykłą nazwę w `slownik.csv` |
| Dodałem nowy produkt | Trafi do feedu sam. Dopisz go w `produkty.csv` (kategoria Google, etykiety) |
| Dodałem nową opcję wariantu (np. „Uchwyt”) | Dopisz ją w `opcje.csv` (raport przypomni) |
| Chcę wyłączyć produkt z feedu | `produkty.csv` → `w_feedzie` = NIE |
| Chcę nowy feed (np. francuski) | `feedy.csv` → `aktywny` = TAK |
| Chcę wygenerować feedy teraz | Zakładka **Actions** → „Generuj feedy” → **Run workflow** |
| Przyszedł e-mail „Run failed” | Otwórz `raporty/ostatnie-uruchomienie.md` – tam jest powód |

---

## Ważne zasady

- **Treść produktu zmieniasz w Shopify**, nie tutaj. Tutaj tylko to, co dotyczy feedów.
- **Nie zmieniaj „Prefiks ID oferty”** w `ustawienia.csv` – Google straciłby historię produktów.
- Dane dostępowe do Shopify są w **sekretach GitHuba** (Settings → Secrets), nigdy w plikach.
