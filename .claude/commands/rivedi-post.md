---
description: Fa revisionare l'ultimo post generato dal subagent revisore-social
argument-hint: "[nome file in out/]"
allowed-tools: Bash(ls:*), Glob, Read, Agent
---

Individua il post da revisionare: se `$ARGUMENTS` indica un file, usa quello;
altrimenti prendi il `.json` piu' recente in `out/`.

Poi delega al subagent **revisore-social**, passandogli il path del `.json`
e chiedendo il verdetto completo.

Riporta il verdetto cosi' com'e'. Se e' `DA CORREGGERE`, proponi le correzioni
concrete (quale template, quale riga) ma non applicarle senza conferma.
