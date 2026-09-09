---
description: Genera (e opzionalmente pubblica) il post con il calendario del mese successivo
argument-hint: "[data] [--pubblica]"
allowed-tools: Bash(./.venv/bin/momasocial:*), Bash(momasocial:*), Read, Glob
---

Genera il post del calendario mensile: gira a fine mese e annuncia il mese
**successivo**.

Argomenti ricevuti: `$ARGUMENTS` (facoltativi: una data nel mese *precedente*
a quello da pubblicare, e `--pubblica` per pubblicare davvero).

Procedi cosi':

1. Esegui `momasocial monthly --no-publish` aggiungendo `--date <data>` se e'
   stata indicata una data. Attenzione: `--date 2026-09-30` produce il
   calendario di **ottobre**.
2. Se esce `[skip]` (nessun evento il mese prossimo), fermati e dillo: puo'
   voler dire che le tappe non sono ancora state create a database, ma non si
   inventano eventi.
3. Apri i PNG generati in `out/<data di oggi>/` con Read e controlla che le
   righe siano leggibili e che nessuna serata manchi.
4. Mostra la caption e segnala eventuali problemi.
5. Pubblica **solo** se in `$ARGUMENTS` compare `--pubblica`, rilanciando lo
   stesso comando senza `--no-publish`. Altrimenti chiudi dicendo che il post
   e' pronto e come pubblicarlo.
