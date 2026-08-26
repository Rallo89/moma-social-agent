---
name: sorgenti-dati
description: Come collegare e mappare il DB di eventi, risultati di tappa e classifiche (HTTP JSON, CSV, Google Sheets, SQL) usato dai post Instagram. Usala quando arriva l'URL di una nuova sorgente, quando cambiano i nomi delle colonne, quando `momasocial doctor` segnala un SourceError, o quando i dati arrivano ma i post escono vuoti o incompleti.
---

# Collegare il DB

## Il contratto

Il codice non sa nulla dello schema della vostra sorgente. Conosce solo questi
campi, e la sezione `[sources.*.map]` della config fa da traduttore:

**Eventi** — `date` (obbligatorio), `title`, `format`, `start_time`, `venue`,
`city`, `entry_fee`, `prize`, `signup_url`, `notes`

**Risultati di tappa** — `date`, `format`, `leg`, `rank`, `player`, `deck`,
`record`, `points`, `players_count`, `venue`

**Classifica** — `format`, `season`, `rank`, `player`, `points`,
`events_played`, `delta` (variazione di posizione: numero, anche negativo)

Le colonne non mappate non vanno perse: finiscono in `_extra` e restano
usabili dai template come `e.extra.nome_colonna`.

## Collegare una sorgente nuova

```toml
[sources.results]
url  = "https://api.esempio.it/tappe?data={date}&formato={format}"
kind = "auto"          # auto | json | csv | sql | yaml
root = "data"          # JSON: chiave che contiene la lista di record

[sources.results.headers]
Authorization = "Bearer ${RESULTS_API_TOKEN}"

[sources.results.map]
date   = "data_torneo"
player = "nome_giocatore"
rank   = "posizione"
```

Formati riconosciuti automaticamente:

| Sorgente | Cosa mettere in `url` |
|---|---|
| API REST JSON | l'endpoint, con i placeholder che servono |
| CSV pubblicato | il link diretto al `.csv` |
| Google Sheets | il link normale del foglio: viene convertito in export CSV |
| Postgres / MySQL / SQLite | la connection string + `query = "SELECT ..."` |
| File locale | un path relativo alla radice del repo |

Placeholder disponibili in `url`, `params`, `headers` e `query`:
`{date}` `{date_from}` `{date_to}` `{format}` `{season}`.
Nelle query SQL diventano bind parameter (`:date_from`), mai concatenazione:
non serve — e non va fatto — costruire SQL a mano con i valori dentro.

**Il filtro viene sempre riapplicato in memoria.** Se l'endpoint ignora i
parametri e restituisce tutto, i post restano comunque corretti. Non serve
quindi che la sorgente supporti i filtri: e' un'ottimizzazione, non un requisito.

## Segreti

I token non si scrivono in `config/config.toml` (che e' versionato): si usa
`${NOME_VAR}` e la variabile si mette in `.env` (locale) o nei GitHub Secrets
(CI). Vedi `.env.example`.

## Diagnosi

```bash
momasocial doctor           # prova tutte e tre le sorgenti e stampa cosa e' arrivato
momasocial agenda --json    # dump degli eventi come li vede il codice
```

Sintomi ricorrenti:

- **`SourceError: Chiave 'X' non trovata`** -> `root` sbagliato: guarda la
  risposta grezza con `curl` e correggi.
- **Post vuoto ma la sorgente risponde** -> la mappatura dei campi non
  corrisponde, oppure le date arrivano in un formato che non viene
  riconosciuto. `momasocial agenda --json` mostra subito quale dei due.
- **Date sbagliate di qualche mese** -> formato ambiguo tipo `03/11/2026`:
  viene letto come giorno/mese (uso italiano). Se la sorgente e' americana,
  chiedi di esporre ISO `AAAA-MM-GG`, che non e' ambiguo.
- **Formati che non fanno match** (es. "Pioneer" vs "pioneer ") -> il confronto
  e' gia' tollerante a maiuscole, spazi, trattini e underscore. Se il problema
  persiste, i due valori sono davvero diversi: guardali con `agenda --json`.
