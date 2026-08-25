---
description: Genera (e opzionalmente pubblica) il carosello risultati di tappa + classifica
argument-hint: "[data] [formato] [--pubblica]"
allowed-tools: Bash(./.venv/bin/mtgsocial:*), Bash(mtgsocial:*), Read, Glob
---

Genera il carosello a due slide con i risultati della tappa e la classifica
generale aggiornata.

Argomenti ricevuti: `$ARGUMENTS`. Senza data si usa **ieri**, che e' il
comportamento previsto dallo scatto notturno.

1. Esegui `mtgsocial results --no-publish` (aggiungi `--date` / `--format` se
   indicati).
2. Se esce `[skip]`, la tappa non e' ancora stata caricata nel DB: dillo e non
   proseguire. E' il caso piu' frequente e non e' un guasto.
3. Apri **entrambi** i PNG con Read: slide 1 risultati, slide 2 classifica.
   Verifica che l'ordine sia questo e che il vincitore in caption coincida con
   il primo della slide 1.
4. Controlla che le posizioni della classifica siano coerenti con le frecce
   di tendenza.
5. Pubblica solo se e' presente `--pubblica`.
