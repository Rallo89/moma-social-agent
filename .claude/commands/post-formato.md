---
description: Genera (e opzionalmente pubblica) il post sul formato in programma oggi
argument-hint: "[data] [formato] [--pubblica]"
allowed-tools: Bash(./.venv/bin/mtgsocial:*), Bash(mtgsocial:*), Read, Glob
---

Genera il post dedicato al formato di giornata.

Argomenti ricevuti: `$ARGUMENTS` (facoltativi: data, nome del formato,
`--pubblica`).

1. Se non e' stato indicato un formato, lascialo dedurre dal calendario: non
   passare `--format`. Il formato si ricava dagli eventi di quel giorno.
2. Esegui `mtgsocial format --no-publish` con `--date` e `--format` solo se
   sono stati indicati.
3. Se esce `[skip]`, riporta che per quel giorno non risulta nessun evento e
   verifica con `mtgsocial agenda` se e' corretto.
4. Apri il PNG con Read e controlla orario, luogo, quota e premi.
5. Pubblica solo se e' presente `--pubblica`.
