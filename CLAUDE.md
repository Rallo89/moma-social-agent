# tech-feeder — agente social MTG

Genera e pubblica i post Instagram dei tornei di Magic: The Gathering
dell'associazione: calendario settimanale, formato del giorno, risultati di
tappa con classifica. Cinque post a settimana, tutti automatici.

## Orientarsi

| Dove | Cosa c'e' |
|---|---|
| `src/moma_social/` | il codice: sorgenti dati, rendering, caption, pubblicazione |
| `templates/images/` | le slide, HTML+Jinja2 renderizzate in PNG 1080x1350 |
| `templates/captions/` | i testi dei post, Jinja2 |
| `config/config.toml` | tutto cio' che cambia senza toccare il codice |
| `.github/workflows/` | i cinque scatti settimanali |
| `state/published.jsonl` | registro delle pubblicazioni (idempotenza) |
| `config/canva-tokens.json` | token Canva, git-ignored, mai committare |
| `out/` | anteprime generate, git-ignored |

Le **skill** in `.claude/skills/` sono la documentazione operativa:
`social-mtg` (piano editoriale), `template-grafici`, `sorgenti-dati`,
`instagram-publishing`. Leggile prima di intervenire sull'area corrispondente.

## Comandi

```bash
./.venv/bin/momasocial doctor                 # diagnosi completa
./.venv/bin/momasocial agenda                 # eventi della settimana
./.venv/bin/momasocial weekly  --no-publish   # anteprima calendario
./.venv/bin/momasocial format  --no-publish   # anteprima formato del giorno
./.venv/bin/momasocial results --no-publish   # anteprima carosello risultati
./.venv/bin/momasocial canva-sync --check    # sfondi da riesportare da Canva
./.venv/bin/python -m pytest -q              # 112 test (i marcati slow renderizzano davvero)
./.venv/bin/ruff check src tests
```

Il `SessionStart` hook prepara `.venv` da solo alla prima sessione.

## Regole di lavoro

- **Guarda i PNG.** Una slide sbagliata non si vede nei test: apri l'immagine
  in `out/` con Read prima di dire che un post e' pronto.
- **Non pubblicare per provare.** `--no-publish` genera tutto senza toccare
  Instagram. Un hook chiede conferma se un comando pubblicherebbe davvero.
- **Nessun dato non e' un errore.** `NoDataError` -> uscita 78 -> il post si
  salta. Non riempire un post con dati inventati o parziali.
- **Lo schema del DB cambia in config, non nel codice.** Se per far entrare
  una sorgente serve toccare `sources.py`, e' un caso mancante nell'adapter:
  dillo invece di aggirarlo con un caso speciale.
- **I segreti stanno nelle variabili d'ambiente.** `config/config.toml` e'
  versionato: dentro ci vanno solo `${NOME_VAR}`.
- **Italiano** in codice, commenti, caption e messaggi d'errore.

## Fuso orario

Tutto ragiona in `Europe/Rome`. I cron di GitHub sono in UTC e non seguono
l'ora legale: ogni workflow schedula due orari e il comando `momasocial gate`
lascia proseguire solo quello che a Roma corrisponde all'ora giusta. Se
sposti un orario, sposta **entrambi** i cron.
