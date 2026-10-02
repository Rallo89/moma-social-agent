# tech-feeder — agente social per tornei Magic: The Gathering

Agente che genera e pubblica su Instagram i contenuti settimanali di
un'associazione no-profit che organizza tornei di Magic: The Gathering.

Contenuti programmati, tutti automatici:

| Quando (Europe/Rome) | Post | Contenuto |
|---|---|---|
| **Sabato 10:00** | carosello | riepilogo della settimana CHE COMINCIA + una card per serata |
| **Lunedi 10:00** | carosello | classifiche di lega, una slide per lega aperta con la top 8 |
| **Ogni giorno 10:00** | storie 9:16 | un torneo per storia: eventi di oggi e domani, con invito al link in bio |
| **Giovedi 03:00** | carosello | risultati della tappa di mercoledi + meta della serata |
| **Venerdi 03:00** | carosello | risultati della tappa di giovedi + meta della serata |
| **Il 30, 10:00** | carosello | calendario del mese successivo |

Le storie leggono i singoli tornei in calendario e invitano al link in bio.
Per generare o pubblicare una singola storia usa `momasocial stories --tournament-id UUID`;
il workflow manuale accetta lo stesso ID e l’opzione `force` per ripubblicare.
I due post notturni leggono la tappa **della sera prima**, quando i
risultati sono stati caricati a fine serata. Il post mensile gira l'ultimo
giorno utile: a febbraio il 30 non esiste, quindi esce il 28.

Gli orari sono un "non prima di", non una promessa: i cron di GitHub sono a
sforzo migliore e arrivano anche con ore di ritardo. Ogni workflow ritenta a
ogni ora dentro una finestra, pubblica al primo scatto utile e si ferma da
solo sui successivi, che trovano la pubblicazione gia' a registro.

## Come funziona

```
DB eventi/risultati ──► adapter sorgenti ──► modelli ──► template Jinja2
                                                            │
                                            ┌───────────────┴────────────────┐
                                            ▼                                ▼
                                     HTML → Chromium → PNG            caption testuale
                                            │                                │
                                            └────────► hosting pubblico ─────┘
                                                              │
                                                    Instagram Graph API
```

- **Sorgenti dati**: un solo adapter legge Supabase (PostgREST), HTTP JSON,
  CSV, Google Sheets, SQL o file locali. Lo schema del vostro DB si dichiara in `config/config.toml`,
  senza toccare il codice.
- **Immagini**: le slide sono HTML+CSS renderizzate da Chromium headless a
  1080x1350 (4:5, il verticale del feed) con `scale = 2`. Il template grafico
  fornito dal grafico si inserisce come sfondo, il testo resta sovrapposto.
- **Pubblicazione**: Instagram Content Publishing API, con il flusso a
  container richiesto dai caroselli e dalle storie. L'API non supporta lo
  sticker link: la storia invita a usare il link in bio.
- **Idempotenza**: `state/published.jsonl` registra ogni post; rilanciare un
  workflow non produce un doppione.
- **Scheduling**: GitHub Actions. I cron girano in UTC, quindi ogni workflow
  ne schedula due (ora legale e ora solare) e un cancello orario lascia
  passare solo quello giusto: il post esce alle 10:00 italiane tutto l'anno.

## Avvio rapido

```bash
# macOS / Linux
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev,sql,s3]"
./.venv/bin/momasocial agenda                    # dati di esempio inclusi
./.venv/bin/momasocial weekly --no-publish       # genera il primo post in out/
```

```powershell
# Windows (PowerShell): un comando per riga, eseguibili in Scripts\
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev,sql,s3]"
.\.venv\Scripts\momasocial agenda
.\.venv\Scripts\momasocial weekly --no-publish
```

Il repo funziona da subito sui dati di esempio in `data/samples/`. Per
collegarlo ai vostri dati e al vostro account: **[docs/AVVIO.md](docs/AVVIO.md)**.

## Uso quotidiano

```bash
momasocial doctor                      # config, sorgenti, rendering, token
momasocial agenda                      # cosa si gioca questa settimana
momasocial weekly  --no-publish        # anteprima calendario
momasocial format  --date 2026-03-11 --no-publish
momasocial stories --date 2026-03-11 --no-publish
momasocial results --date 2026-03-11 --no-publish
```

Ogni run lascia in `out/`: il PNG, l'HTML sorgente, la caption e i metadati.

### Da Claude Code

Il repo e' attrezzato come progetto Claude Code:

- **Skill** — `social-mtg` (piano editoriale), `template-grafici`,
  `sorgenti-dati`, `instagram-publishing`
- **Guida alla messa in linea** — `docs/PUBBLICAZIONE.md`: hosting delle
  immagini e credenziali Instagram, passo per passo
- **Slash command** — `/post-calendario`, `/post-mensile`, `/post-formato`,
  `/post-risultati`, `/social-check`, `/rivedi-post`
- **Subagent** — `revisore-social` (QA su slide e caption),
  `analista-dati` (diagnosi sorgenti)
- **Server MCP** — `moma-social`: interroga calendario, risultati e classifiche
  e genera anteprime direttamente in conversazione
- **Hook** — preparazione automatica dell'ambiente; conferma richiesta prima
  di una pubblicazione reale lanciata a mano

## Sfondi grafici da Canva

Se i template vivono su Canva, si recuperano senza scaricarli a mano:

```bash
momasocial canva-auth                  # una volta sola, apre il browser
momasocial canva-sync --check          # cosa cambierebbe
momasocial canva-sync                  # riesporta in templates/images/assets/
```

Il sync **non** gira nei workflow schedulati: l'OAuth di Canva ha refresh token
monouso a rotazione e una catena rotta richiede di riautorizzare dal browser,
cosa che non deve poter fermare il post del lunedi'. I workflow leggono i PNG
committati nel repo. Setup completo in [docs/CANVA.md](docs/CANVA.md).

## Mettere in pausa

```toml
[instagram]
publish_enabled = false
```

Le pipeline continuano a generare i file in `out/` ma non pubblicano nulla.
E' il modo corretto di sospendere i social senza disattivare i workflow.

## Test

```bash
./.venv/bin/python -m pytest -q              # tutto, incluso il rendering reale
./.venv/bin/python -m pytest -q -m "not slow"  # solo i test veloci
```
