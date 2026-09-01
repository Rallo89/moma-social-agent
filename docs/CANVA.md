# Collegare Canva

Serve una volta sola. Alla fine gli sfondi si riesportano con un comando.

> **Prerequisito: il progetto deve stare sul tuo computer.**
> L'autorizzazione (passo 4) apre il browser e Canva rimanda il codice su
> `http://127.0.0.1:8721`, cioe' sulla macchina dove hai lanciato il comando.
> Non funziona da un container remoto o da una sessione web: il redirect
> arriverebbe a un localhost che il tuo browser non raggiunge.
>
> **macOS / Linux**
> ```bash
> git clone https://github.com/Rallo89/moma-social-agent
> cd moma-social-agent
> python3 -m venv .venv && ./.venv/bin/pip install -e "."
> cp .env.example .env        # e valorizza CANVA_CLIENT_ID / CANVA_CLIENT_SECRET
> ```
>
> **Windows (PowerShell)** — un comando per riga: `&&` non esiste in
> PowerShell 5.1, e il venv mette gli eseguibili in `Scripts\`, non in `bin/`.
> ```powershell
> git clone https://github.com/Rallo89/moma-social-agent
> cd moma-social-agent
> python -m venv .venv
> .\.venv\Scripts\pip install -e "."
> Copy-Item .env.example .env
> ```
> Se `python` non risponde, usa `py -3 -m venv .venv`. Conviene chiamare gli
> eseguibili direttamente (`.\.venv\Scripts\momasocial ...`) invece di attivare
> il venv: si evita il blocco dell'execution policy su `Activate.ps1`.
>
> Le credenziali Canva restano sul tuo computer, in `.env`, che e' git-ignored:
> non vanno committate, ne' incollate in chat.

---

## 1. Creare l'integrazione su Canva

1. Vai su **[canva.com/developers](https://www.canva.com/developers/)** e accedi
   con l'account che possiede i design (o che vi ha accesso).
2. **Developer Portal → Your integrations → Create an integration**.
3. Tipo: **Public**. Non farti ingannare dai nomi:
   - **Private** non vuol dire "non pubblicata": vuol dire *riservata al tuo
     team su un piano Canva **Enterprise***. Senza Enterprise non e' selezionabile.
   - **Public** in stato *draft* e' gia' utilizzabile per uso individuale e
     test. La revisione di Canva serve **solo** per renderla disponibile a
     tutti gli utenti Canva: non e' il nostro caso.
4. Dai un nome, es. `moma-social-agent`.

> **Non premere "Submit for review".** L'integrazione resta in draft, tu la
> autorizzi con il tuo account e funziona. La revisione servirebbe soltanto per
> distribuirla ad altri utenti Canva.

## 2. Configurare l'integrazione

Nella scheda **Configuration** dell'integrazione:

**Scopes** — abilita esattamente questi due, non servono altri:

| Scope | Perche' |
|---|---|
| `design:content:read` | esportare il design in PNG |
| `design:meta:read` | leggere il titolo del design (compare nei log) |

**Redirect URL** — aggiungi:

```
http://127.0.0.1:8721
```

Attenzione: deve essere l'indirizzo numerico. **Canva rifiuta `localhost`.**
Se la porta 8721 e' occupata sulla tua macchina, cambiala qui *e* in
`config/config.toml` (`canva.redirect_port`): devono coincidere.

**Client ID e Client Secret** — copiali, servono al passo 3. Il secret e'
visibile una volta sola: se lo perdi lo rigeneri da qui.

## 3. Metterli nel progetto

In locale, nel file `.env` (git-ignored, copia da `.env.example`):

```
CANVA_CLIENT_ID=...
CANVA_CLIENT_SECRET=...
```

Questi due non vanno nei GitHub Secrets: il sync gira dalla tua macchina, non
in CI. Il motivo e' spiegato in fondo.

## 4. Autorizzare

```bash
momasocial canva-auth                    # macOS / Linux
.\.venv\Scripts\momasocial canva-auth     # Windows
```

Si apre il browser sulla pagina di Canva, dai il consenso, e la scheda si
chiude da sola. I token finiscono in `config/canva-tokens.json`, che e'
git-ignored: **non committarlo mai.**

Se sei su una macchina senza browser, usa `momasocial canva-auth --no-browser`,
apri l'indirizzo stampato altrove e completa da li'.

## 5. Dire quale design corrisponde a quale sfondo

Il **design ID** e' il segmento **subito dopo `/design/`**. Attenzione: l'URL ne
contiene due, e serve solo il primo.

```
https://www.canva.com/design/DAF5kNaAdDU/sNtVNbJOh1j7RmAGeIgfUA/edit
                             ^^^^^^^^^^^ ^^^^^^^^^^^^^^^^^^^^^^
                             design ID   token del link, NON serve
```

Il secondo segmento e' il token di accesso del link condiviso: non va in
configurazione (ed e' bene non diffonderlo).

In `config/config.toml`, un blocco per sfondo:

```toml
[[canva.assets]]
design_id = "DAFxxxxxxxx"
target    = "templates/images/assets/sfondo_calendario.png"

[[canva.assets]]
design_id = "DAFyyyyyyyy"
target    = "templates/images/assets/sfondo_formato.png"

[[canva.assets]]
design_id = "DAFzzzzzzzz"
target    = "templates/images/assets/sfondo_risultati.png"

[[canva.assets]]
design_id = "DAFzzzzzzzz"
page      = 2
target    = "templates/images/assets/sfondo_classifica.png"
```

Come nell'ultimo blocco, se un solo design contiene piu' sfondi su pagine
diverse basta indicare `page`.

Poi vanno collegati alle slide, nelle sezioni `[posts.*]`:

```toml
[posts.weekly_calendar]
background = "templates/images/assets/sfondo_calendario.png"
```

> **Punta il sync al design PULITO, non a quello con i placeholder.**
> Un template di lavorazione contiene i segnaposto come testo (`{{NOME}}`,
> `{p}`, `{{pt}}`): esportato diventa uno sfondo con quelle scritte impresse.
> Lo sfondo va ricavato da un **duplicato del design senza i livelli di testo**,
> ed e' l'ID di quel duplicato che va in `[[canva.assets]]`.
>
> Se in `target` lasci il design di lavorazione, il primo `canva-sync` che
> qualcuno lancia sovrascrive lo sfondo pulito con quello pieno di segnaposto.
> Il comando sta facendo il suo mestiere: e' puntato al design sbagliato.

## 6. Usarlo

```bash
momasocial canva-sync --check     # cosa cambierebbe, senza scrivere niente
momasocial canva-sync             # riesporta
momasocial canva-sync --only sfondo_calendario.png
```

Il comando confronta il contenuto e riscrive solo cio' che e' davvero
cambiato. Dopo un sync che riporta *aggiornato*:

```bash
momasocial weekly --no-publish
```

e **guarda il PNG**. Uno sfondo nuovo sposta quasi sempre le safe zone del
testo, e il difetto si vede solo a occhio. Se serve, si sistema il blocco
`{% block styles %}` della slide in `templates/images/`.

Infine committa i PNG in `templates/images/assets/`: sono loro che i workflow
leggono in produzione.

Da Claude Code c'e' `/canva-sync`, che fa tutto questo e controlla anche i PNG.

---

## Perche' il sync non gira nei workflow schedulati

L'OAuth di Canva e' **per utente**, non per macchina: access token di 4 ore e
refresh token **monouso a rotazione** — ogni rinnovo restituisce un token nuovo
e invalida il precedente.

In un cron questo e' fragile: il token ruotato andrebbe riscritto in un Secret
a ogni giro, e se due esecuzioni si accavallano o una muore a meta' rinnovo,
Canva revoca tutto e serve riautorizzare a mano dal browser.

Se succedesse di martedi', il calendario del lunedi' successivo non uscirebbe.
Per questo i workflow leggono i PNG committati nel repo e non sanno nemmeno che
Canva esiste: **un problema con Canva non puo' fermare la pubblicazione.**

Gli sfondi cambiano una volta a stagione. Lanciare un comando quando succede e'
un costo trascurabile rispetto a quel rischio.

## Se qualcosa non va

| Messaggio | Cosa fare |
|---|---|
| `Nessun token Canva in ...` | non hai mai fatto il passo 4: `momasocial canva-auth` |
| `invalid_grant` / `Refresh token used twice` | catena dei token rotta: rilancia `momasocial canva-auth` |
| `Impossibile ascoltare su http://127.0.0.1:8721` | porta occupata: cambiala in config e nel Redirect URL su Canva |
| `Risorsa non trovata su Canva` | `design_id` sbagliato, o il design non e' accessibile all'account autorizzato |
| `richiesta pagina N ma il design ne ha M` | `page` fuori range in `[[canva.assets]]` |
| `Credenziali Canva mancanti` | `.env` non valorizzato, o non caricato dalla cartella del progetto |
