# Krok 1 – klucz do Shopify (tylko odczyt)

Generator potrzebuje „przepustki” do odczytu produktów. Tworzysz ją raz.
Shopify od 2026 r. tworzy takie przepustki w **Dev Dashboard** (stare „Develop apps” w panelu sklepu
już nie pozwala zakładać nowych).

## Co zrobić

1. W panelu Shopify wejdź w **Ustawienia → Aplikacje** i przejdź do **Dev Dashboard**
   (link „Develop apps” / „Build apps in Dev Dashboard”).
2. **Utwórz aplikację** – nazwa np. `KUNSST generator feedów`.
3. W wersji aplikacji (**Versions / Access**) zaznacz **tylko uprawnienia do odczytu**:
   - `read_products` – produkty, warianty, ceny
   - `read_translations` – tłumaczenia PL / DE
   - `read_inventory` – waga wariantów
   - `read_markets` – ceny dla poszczególnych rynków

   Żadnych uprawnień zaczynających się od `write_` – generator ma tylko czytać.
4. Wydaj wersję (**Release**) i **zainstaluj aplikację w sklepie** kunsst.com.
5. W **Settings** aplikacji skopiuj dwie wartości:
   - **Client ID**
   - **Client secret**

   Nie wklejaj ich do żadnego pliku ani na czat – trafiają tylko do sekretów GitHuba (krok 2).

Jeśli któryś przycisk nazywa się inaczej, napisz do Claude, co widzisz na ekranie – przeprowadzi Cię dalej.
