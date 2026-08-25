---
name: instagram-publishing
description: Pubblicazione su Instagram via Graph API - carosello, container, token, hosting delle immagini, limiti di rate e diagnosi degli errori. Usala quando un post non viene pubblicato, quando compare un PublishError o un codice di errore Graph API, quando scade il token, quando si configura l'hosting delle immagini (S3/R2/imgbb), o quando si deve capire perche' un carosello e' uscito male.
---

# Pubblicazione Instagram

## Il flusso reale

La Content Publishing API **non accetta upload binari**: scarica l'immagine da
un URL pubblico. Da qui i due passaggi:

```
PNG in out/  ->  upload su hosting pubblico  ->  URL  ->  Graph API
```

Immagine singola:
1. `POST /{ig-user-id}/media` con `image_url` e `caption` -> container id
2. attesa che il container sia `FINISHED`
3. `POST /{ig-user-id}/media_publish` con `creation_id`

Carosello (i due post dei risultati):
1. un container per slide con `is_carousel_item=true` (senza caption)
2. un container `media_type=CAROUSEL` con `children` e la caption
3. publish del container carosello

L'attesa del container non e' opzionale: la Graph API restituisce subito un id
ma elabora l'immagine in modo asincrono, e un publish su container non pronto
fallisce.

## Prerequisiti dell'account

- Account Instagram **Business** o **Creator** collegato a una Pagina Facebook.
- Un'app Meta con i permessi `instagram_basic`, `instagram_content_publish`,
  `pages_read_engagement`.
- Un **token long-lived** (60 giorni) — va rinnovato: vedi sotto.

## Hosting delle immagini

`media.backend` in config:

- **`s3`** — S3, Cloudflare R2 o MinIO (per R2/MinIO valorizza `endpoint_url`).
  Serve che gli oggetti siano leggibili pubblicamente e che `public_base` punti
  al dominio da cui Instagram li scarichera'.
- **`imgbb`** — piu' rapido da attivare, adatto a partire; per una realta' che
  pubblica ogni settimana conviene passare a S3/R2.
- **`none`** — nessun hosting: le immagini restano in `out/` e la pubblicazione
  fallisce con un messaggio esplicito. Va bene solo per `--dry-run`.

## Errori frequenti

| Sintomo | Causa | Cosa fare |
|---|---|---|
| `PublishError ... code 190` | token scaduto o revocato | rigenera il long-lived token e aggiorna il secret `IG_ACCESS_TOKEN` |
| `code 100` su `image_url` | l'URL non e' raggiungibile da Meta | verifica che l'oggetto sia pubblico e che `public_base` sia giusto |
| container in stato `ERROR` | immagine fuori specifica | rapporto fra 4:5 e 1.91:1, JPEG/PNG, sotto gli 8 MB |
| `code 4` / `code 32` | rate limit (25 post/24h) | non ritentare a raffica: aspetta e ricontrolla il ledger |
| Carosello con slide in ordine sbagliato | `children` in ordine errato | l'ordine e' quello di `draft.images`: prima i risultati, poi la classifica |

Diagnosi rapida: `mtgsocial doctor` chiama `GET /{ig-user-id}` e mostra subito
se il token e' ancora valido.

## Rinnovo del token

Il token long-lived dura 60 giorni e va rinnovato **prima** della scadenza
(`GET /oauth/access_token?grant_type=fb_exchange_token`). Il workflow
`.github/workflows/token-check.yml` lo controlla ogni settimana e apre una
issue quando mancano meno di 14 giorni: se quella issue esiste, il rinnovo e'
la cosa piu' urgente da fare, perche' alla scadenza si fermano tutti e cinque
i post settimanali.

## Idempotenza

`out/published.jsonl` registra ogni tentativo. Prima di pubblicare si controlla
la `dedupe_key` (`tipo:data:formato`): se quel post e' gia' uscito, il run
viene saltato e registrato come `skipped`. Un workflow rilanciato a mano non
produce doppioni. `--force` scavalca il controllo: usalo solo se il post
precedente e' stato davvero cancellato da Instagram.
