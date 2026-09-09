---
description: Genera (e opzionalmente pubblica) il post con il calendario settimanale
argument-hint: "[data] [--pubblica]"
allowed-tools: Bash(./.venv/bin/momasocial:*), Bash(momasocial:*), Read, Glob
---

Genera il post del calendario settimanale.

Argomenti ricevuti: `$ARGUMENTS` (facoltativi: una data dentro la settimana da
pubblicare, e `--pubblica` per pubblicare davvero).

Procedi cosi':

1. Esegui `momasocial weekly --no-publish` aggiungendo `--date <data>` se e'
   stata indicata una data.
2. Se esce `[skip]` (nessun evento in settimana), fermati e dillo: non si
   inventano eventi.
3. Apri i PNG generati in `out/<data di oggi>/` con Read e controlla che sia leggibile e che
   ci siano tutti i giorni con eventi.
4. Mostra la caption e segnala eventuali problemi.
5. Pubblica **solo** se in `$ARGUMENTS` compare `--pubblica`, rilanciando lo
   stesso comando senza `--no-publish`. Altrimenti chiudi dicendo che il post
   e' pronto in `out/` e come pubblicarlo.
