---
description: Diagnosi completa dell'agente social (config, sorgenti, rendering, token)
allowed-tools: Bash(./.venv/bin/momasocial:*), Bash(momasocial:*), Read, Glob
---

Esegui `momasocial doctor` e commenta il risultato.

Per ogni controllo fallito indica: cosa significa, quale file o secret va
sistemato, e il comando per riverificare. Se fallisce il controllo sulle
credenziali Instagram, ricorda che il token long-lived scade dopo 60 giorni.

Chiudi con lo stato dei prossimi scatti: leggi `.github/workflows/` e di'
quale post uscira' per primo e quando.
