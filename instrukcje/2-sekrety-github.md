# Krok 2 – sekrety w GitHubie

Sekrety to sejf: GitHub przechowuje w nim dane dostępowe do Shopify, nikt ich nie zobaczy
(nawet Ty po zapisaniu – można je tylko podmienić).

## Co zrobić

1. Otwórz repozytorium `kunsst-product-feeds` na github.com.
2. **Settings** (zakładka u góry) → po lewej **Secrets and variables** → **Actions**.
3. Kliknij **New repository secret** i dodaj dwa sekrety:

| Name (wpisz dokładnie) | Secret (wklej) |
|---|---|
| `SHOPIFY_CLIENT_ID` | Client ID z kroku 1 |
| `SHOPIFY_CLIENT_SECRET` | Client secret z kroku 1 |

4. Sprawdź działanie: zakładka **Actions** → **Generuj feedy** → **Run workflow**.
   Po ok. minucie powinien pojawić się zielony znaczek ✅, a w folderze `feedy/` świeże pliki.
   Szczegóły w `raporty/ostatnie-uruchomienie.md`.
