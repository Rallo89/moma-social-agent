---
description: Riesporta da Canva gli sfondi grafici e verifica il risultato
argument-hint: "[nome sfondo] [--check]"
allowed-tools: Bash(./.venv/bin/momasocial:*), Bash(momasocial:*), Bash(git status:*), Bash(git diff:*), Read, Glob
---

Riesporta gli sfondi da Canva.

Argomenti ricevuti: `$ARGUMENTS` (facoltativi: il nome di un singolo sfondo,
e `--check` per vedere cosa cambierebbe senza scrivere).

1. Esegui `momasocial canva-sync`, aggiungendo `--only <nome>` e `--check` se
   indicati.
2. Se compare un errore `invalid_grant` o "Refresh token used twice", la catena
   dei token e' rotta: serve rilanciare `momasocial canva-auth` dalla macchina
   di chi gestisce l'integrazione. Non e' una cosa che puoi risolvere tu.
3. Per ogni sfondo che risulta **aggiornato**, rigenera il post che lo usa con
   `--no-publish` e **apri il PNG con Read**: uno sfondo nuovo sposta quasi
   sempre le safe zone del testo, e il difetto si vede solo guardando.
4. Se il testo finisce sopra le decorazioni dello sfondo, correggi il blocco
   `{% block styles %}` della slide interessata in `templates/images/` e
   rigenera finche' non regge.
5. Chiudi mostrando `git status` dei file in `templates/images/assets/`: i PNG
   vanno committati, sono loro che i workflow leggono in produzione.

Non pubblicare nulla su Instagram durante questa operazione.
