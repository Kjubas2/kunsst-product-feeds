# Raport z ostatniego uruchomienia (PRZYKŁAD)

> Ten plik tworzy się sam przy każdym uruchomieniu programu. Poniżej przykład. Liczby są szacunkowe.

Uruchomienie: 2026-11-20 18:17 · Shopify: 10 produktów, 520 wariantów · Wynik: ✅ wszystkie feedy zapisane

## Feedy

| Platforma | Feed | Ofert | Poprzednio | Pominięte | Wynik |
|---|---|---|---|---|---|
| google | PL_PLN | 150 | 150 | 370 | ✅ zapisano |
| google | DE_EUR | 150 | 150 | 370 | ✅ zapisano |
| google | DE_CHF | 150 | 150 | 370 | ✅ zapisano |
| google | EN_EUR | 150 | 150 | 370 | ✅ zapisano |

## Dlaczego warianty nie trafiły do feedów
- Brak zdjęcia w gatunku i kolorze: ok. 345
- Wariant „Custom Order”: ok. 25

## Plan zdjęć – co przygotować najpierw
Jedno zdjęcie przypisane w Shopify do dowolnego wariantu z danej kombinacji odblokowuje w feedach wszystkie jej rozmiary i konfiguracje.
Kolejność: najpierw produkty z priorytetem (`priority` w 03.products_settings.csv), potem kombinacje, które odblokują najwięcej ofert.

| # | Produkt | Gatunek / kolor | Odblokuje ofert w każdym feedzie |
|---|---|---|---|
| 1 | Wooden audio rack (flagship) | Oak wood / Solid Black | 10 |
| 2 | Wooden audio rack (flagship) | Oak wood / Dark Roast | 10 |
| 3 | Wooden audio rack (flagship) | Walnut wood / Natural | 10 |
| 4 | Solid wood desk with drawer | Oak wood / Solid Black | 6 |
| 5 | Solid wood desk with drawer | Ash wood / Natural | 6 |
| … | … (pełna lista w prawdziwym raporcie, ok. 50 kombinacji) | … | … |

## Ostrzeżenia
- Brak – wszystko w porządku.
