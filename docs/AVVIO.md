# Messa in servizio

Quattro cose da collegare, in quest'ordine. Dopo ognuna c'e' un comando che
dice se ha funzionato: non passare alla successiva finche' non passa.

---

> **Windows:** il progetto dichiara `tzdata` fra le dipendenze perche' Windows
> non ha un database dei fusi orari di sistema. Se hai installato il progetto
> prima di questa correzione, aggiorna con `pip install -e .` oppure
> `pip install tzdata`, altrimenti ogni comando fallisce su `Europe/Rome`.

## 1. Le sorgenti dati

Serve un URL per ognuna delle tre sorgenti (possono essere lo stesso endpoint
con parametri diversi, o lo stesso foglio con tre schede):

- **eventi** — cosa si gioca e quando
- **risultati di tappa** — piazzamenti di una singola serata
- **classifica generale** — punteggi cumulati per formato

Vanno bene: un endpoint REST JSON, un CSV pubblicato, un Google Sheets
(basta il link normale del foglio) o un database SQL raggiungibile.

I campi che il codice si aspetta:

| Sorgente | Campi |
|---|---|
| eventi | `date`* , `title`, `format`, `start_time`, `venue`, `city`, `entry_fee`, `prize`, `signup_url`, `notes` |
| risultati | `date`*, `format`*, `leg`, `rank`, `player`*, `deck`, `record`, `points`, `players_count`, `venue` |
| classifica | `format`*, `season`, `rank`, `player`*, `points`*, `events_played`, `delta` |

`*` = necessari. Gli altri, se mancano, spariscono dalla slide senza rompere nulla.

**Non serve rinominare le colonne del vostro DB**: si dichiara la
corrispondenza in `config/config.toml`.

```toml
[sources.events]
url  = "https://api.esempio.it/eventi?from={date_from}&to={date_to}"
root = "data"                       # chiave JSON che contiene la lista

[sources.events.map]
date       = "data_evento"          # campo interno = colonna vostra
title      = "nome"
format     = "formato"
start_time = "ora_inizio"
```

Se l'endpoint richiede un token:

```toml
[sources.events.headers]
Authorization = "Bearer ${EVENTS_API_TOKEN}"
```

Verifica:

```bash
momasocial doctor
momasocial agenda --json      # gli eventi come li vede il codice
```

Dettagli e casi particolari: `.claude/skills/sorgenti-dati/SKILL.md`.

---

## 2. I template grafici e testuali

**Immagini.** Esportate a 1080x1350 (o 2160x2700) e salvate in
`templates/images/assets/`. Poi in `config/config.toml`:

```toml
[posts.weekly_calendar]
background = "templates/images/assets/sfondo_calendario.png"

[posts.format_spotlight]
background = "templates/images/assets/sfondo_formato.png"

[posts.leg_results]
background = "templates/images/assets/sfondo_risultati.png"

[posts.leg_results_standings]
background = "templates/images/assets/sfondo_classifica.png"   # facoltativo
```

Servono quattro sfondi (o meno, se le slide condividono la grafica). Quasi
sempre bisognera' spostare le safe zone del testo, perche' lo sfondo ha gia'
le sue decorazioni: si fa nel blocco `styles` della slide corrispondente in
`templates/images/`.

Se i design vivono su Canva, si possono riesportare con un comando invece che
a mano: vedi [CANVA.md](CANVA.md).

**Testi.** I template delle caption sono in `templates/captions/`. Sostituite
il corpo mantenendo le variabili: l'elenco di quelle disponibili e' nel
commento in testa a ogni file.

**Colori, font e logo** stanno nella sezione `[brand]` della config. Per usare
il font del brand, mettete il `.woff2` in `templates/images/fonts/`.

Verifica: rigenerate e **guardate i PNG**.

```bash
momasocial weekly  --no-publish
momasocial format  --no-publish
momasocial results --no-publish
```

Dettagli: `.claude/skills/template-grafici/SKILL.md`.

---

## 3. L'account Instagram

Requisiti dell'account:

1. Profilo Instagram **Business** o **Creator** (non personale).
2. Collegato a una **Pagina Facebook**.
3. Un'app Meta con i permessi `instagram_basic`, `instagram_content_publish`,
   `pages_read_engagement`.
4. Un **token long-lived** e l'**ID numerico** dell'account Instagram
   (non l'handle `@nome`).

In locale finiscono in `.env` (copiate `.env.example`); in produzione nei
GitHub Secrets del repository.

Il token dura **60 giorni**. Il workflow `token-check.yml` lo controlla ogni
lunedi e apre una issue quando mancano meno di due settimane: quella issue e'
la cosa piu' urgente da chiudere, perche' alla scadenza si fermano tutti e
cinque i post.

Verifica: `momasocial doctor` deve mostrare ✅ su "Credenziali Instagram".

---

## 4. L'hosting delle immagini

**Questo passaggio non e' opzionale.** La Graph API non accetta upload di
file: scarica l'immagine da un URL pubblico. Senza hosting, la generazione
funziona ma la pubblicazione no.

Due opzioni:

- **S3 / Cloudflare R2 / MinIO** (consigliata) — `media.backend = "s3"`, con
  `endpoint_url` valorizzato per R2 e MinIO. Gli oggetti devono essere
  leggibili pubblicamente.
- **imgbb** — `media.backend = "imgbb"`, basta una API key. Piu' rapida da
  attivare, adatta per partire.

Verifica: `momasocial weekly` (senza `--no-publish`) su una settimana di prova.

---

## 5. Accendere gli scatti automatici

I workflow sono gia' schedulati e partono da soli una volta che i Secrets
sono a posto. Secrets e variabili da impostare in
*Settings → Secrets and variables → Actions*:

| Nome | Tipo | Serve a |
|---|---|---|
| `IG_USER_ID` | secret | account Instagram |
| `IG_ACCESS_TOKEN` | secret | account Instagram |
| `MEDIA_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | secret | hosting S3 |
| `MEDIA_PUBLIC_BASE`, `AWS_REGION` | variable | hosting S3 |
| `IMGBB_API_KEY` | secret | hosting imgbb (in alternativa a S3) |
| `EVENTS_API_TOKEN`, `RESULTS_API_TOKEN` | secret | sorgenti protette da token |

Serve anche il permesso di scrittura per i workflow
(*Settings → Actions → General → Workflow permissions → Read and write*):
serve a ricommittare `state/published.jsonl`, il registro che impedisce i post
doppi.

**Prima prova a mano**, senza aspettare il cron: *Actions → Post calendario
settimanale → Run workflow*, con "Genera senza pubblicare" attivo. Se
l'artifact contiene il PNG giusto, togliete la spunta e rilanciate.

---

## Domande ricorrenti

**Cosa succede se una settimana non ci sono eventi?**
Il post viene saltato e il workflow risulta comunque verde, con una nota nel
log. Nessun post vuoto.

**E se i risultati della tappa non sono ancora nel DB alle 03:00?**
Stesso comportamento: post saltato. Si puo' rilanciare il workflow a mano
appena i dati ci sono; il registro impedisce comunque il doppione se nel
frattempo era gia' uscito.

**Come si mette in pausa tutto?**
`instagram.publish_enabled = false` in `config/config.toml`. Meglio che
disattivare i workflow: continuate a vedere cosa *sarebbe* uscito.

**Come si pubblica un post fuori orario?**
*Actions → il workflow → Run workflow*, indicando la data. Oppure da Claude
Code con `/post-calendario 2026-03-09 --pubblica`.
