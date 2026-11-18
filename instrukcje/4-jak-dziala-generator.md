# Jak działa generator – krok po kroku

## Trzy źródła, jeden wynik

| Źródło | Co z niego pochodzi | Gdzie zmieniasz |
|---|---|---|
| **Shopify** | produkty, warianty, ceny dla każdego rynku, opisy, zdjęcia, tłumaczenia (także nazw kolorów, gatunków, konfiguracji), czas realizacji, wyróżniki | w Shopify |
| **Panel** (`ustawienia/`) | jakie feedy, dla jakich krajów, jak budować tytuł i link, kategoria Google, etykiety, wyjątki | w panelu |
| **Profil platformy** (`ustawienia/profile/` + wymogi w programie) | nazwy kolumn, format pliku, pola wymagane, limity długości | rzadko; nowa platforma = nowy profil |

## Co się dzieje przy każdym uruchomieniu (co 6 h albo po kliknięciu „Run workflow”)

**Krok 1 – czytanie panelu.** Generator sprawdza, które feedy mają `aktywny = TAK`.
Z nich wie, jakich języków i jakich krajów (cen) potrzebuje.

**Krok 2 – pobranie danych ze Shopify (tylko odczyt).** Wszystkie aktywne produkty i **wszystkie
ich warianty** – bez limitu (pobiera po 50 wariantów, aż do końca). Dla każdego wariantu cenę
w każdym potrzebnym kraju (np. PL → PLN, DE → EUR, CH → CHF) – dokładnie taką, jaką widzi klient z tego kraju.

**Krok 3 – budowa oferty dla każdego wariantu, osobno w każdym feedzie.**
1 wariant = 1 oferta. Dla każdej oferty:

- **Tytuł** = nazwa produktu w języku feedu + cechy wariantu w kolejności z `opcje.csv`
  (gatunek, kolor, rozmiar, drzwi…). Np. *Biurko z litego drewna z szufladą – jesion, kolor czarny, 140 cm*.
  Nazwę produktu można nadpisać w `produkty.csv` (kolumny `tytuł_XX (nadpisanie)`).
- **Kolor, materiał, rozmiar** (atrybuty Google) – z wartości wariantu.
  Kolejność szukania nazwy: **Słownik** (jeśli jest wyjątek) → **tłumaczenie w Shopify** → nazwa ze Shopify.
  Dlatego Twoje tłumaczenia palety (Miodowy, Honigfarben…) trafiają do feedu same.
- **Zdjęcie** – musi pasować do gatunku i koloru (i drzwi w szafkach – opcje z `rozróżnia_zdjęcia = TAK`):
  1. zdjęcie przypisane do wariantu,
  2. albo zdjęcie innego wariantu w tej samej kombinacji (długość może być inna),
  3. albo zdjęcie główne – tylko dla kombinacji, którą ono pokazuje (domyślnie: pierwszy wariant, np. dąb naturalny),
  4. inaczej wariant **jest pomijany** i trafia do listy „Kombinacje bez zdjęcia” w raporcie.
  Zdjęcia innych kolorów nie trafiają do zdjęć dodatkowych.
- **Cena** – z cennika rynku w Shopify; cena promocyjna tylko, gdy jest cena porównawcza wyższa od ceny.
- **Link** – do konkretnego wariantu, w języku feedu (`/pl/`, `/de/`), z walutą i parametrami UTM.
  Osobny link dla reklam (bez UTM), żeby działało auto-tagowanie Google Ads.
- **MPN** = SKU wariantu, **identifier_exists = no** (brak kodów EAN).
- **Czas realizacji** – z metapola „lead time” (tygodnie × 5 = dni robocze).
- **Etykiety** – patrz niżej.

Pomijane są też: produkty z `w_feedzie = NIE`, warianty „inny kolor – na zamówienie”
(ustawienie w `ustawienia.csv`), warianty bez ceny w walucie feedu.

**Krok 4 – ułożenie w kolumny platformy.** Profil (`profile/google.csv`) mówi, która kolumna pliku
bierze które pole oferty. Wymogi platformy (w programie) pilnują pól obowiązkowych i limitów długości –
za długi tytuł jest przycinany, oferta bez wymaganego pola odrzucana (z wpisem w raporcie).

**Krok 5 – bezpieczniki.** Jeśli ofert jest mniej niż minimum albo liczba spadła o ponad 30% względem
poprzedniego pliku – plik **nie jest nadpisywany**, stary zostaje, GitHub wysyła e-mail.

**Krok 6 – zapis i raport.** Pliki w `feedy/`, raport w `raporty/ostatnie-uruchomienie.md`:
ile ofert, ile wariantów pominięto i dlaczego, których kombinacji brakuje zdjęć, ostrzeżenia.

**Krok 7 – Merchant Center** pobiera plik codziennie pod stałym adresem
(`https://raw.githubusercontent.com/Kjubas2/kunsst-product-feeds/main/feedy/PL_PLN.tsv` itd.).

## Etykiety (custom_label) – czy trzeba je ustawiać w produktach?

Nie. Etykiety **nie są potrzebne**, żeby produkt był zatwierdzony ani widoczny w bezpłatnych wynikach.
Służą tylko do **dzielenia produktów w kampaniach Google Ads** (np. osobny budżet dla stolików audio,
wyższe stawki dla orzecha). Generator wylicza je sam – nic nie dodajesz w Shopify:

| Etykieta | Znaczenie | Skąd |
|---|---|---|
| custom_label_0 | linia: audio / home | panel, `produkty.csv` → `linia` |
| custom_label_1 | kategoria: desks / audio-racks / vinyl-cabinets / coffee-tables | panel → `kategoria` |
| custom_label_2 | gatunek: oak / ash / beech / walnut | automatycznie z wariantu |
| custom_label_3 | wykończenie: natural / stained | automatycznie z koloru |
| custom_label_4 | priorytet (np. flagship, bestseller) | panel → `priorytet`, na razie puste |

## Inne platformy

Każda platforma = **profil** (układ kolumn w `ustawienia/profile/<nazwa>.csv`) + wpis wymogów w
`generator/platformy.py` + wiersz w `feedy.csv` z kolumną `profil`. Dane i reguły z panelu są wspólne.

| Platforma | Stan |
|---|---|
| Google Merchant Center | ✅ działa (profil `google`) |
| Microsoft Merchant Center (Bing) | ten sam format co Google – wystarczy podać ten sam adres pliku |
| ChatGPT / OpenAI | planowane później (profil `openai`, format csv.gz) |
| Meta (Facebook/Instagram), Pinterest | kandydaci, gdy ruszą płatne kampanie |
