# Copertina Facebook del calendario mensile

`momasocial monthly` genera il carosello Instagram e una copertina orizzontale
con il calendario del mese successivo. La copertina resta un artefatto separato:
non entra nel carosello. Il percorso compare in CLI, nelle anteprime MCP e
nel campo `artifacts.facebook_cover` del JSON. PNG e HTML sono nella cartella
di output del giorno. `--no-publish` non scrive sul registro; `--dry-run`
registra un'anteprima senza chiamare i servizi di pubblicazione.

## Contratto Meta e permessi

Verifica documentale effettuata il 19 ottobre 2026 sulle fonti ufficiali:

- [Page](https://developers.facebook.com/docs/graph-api/reference/page/):
  `POST /{page-id}`, parametro `cover` con ID numerico della foto;
  la documentazione richiede Page Admin o Page Editor con `EDIT_PROFILE`
  e permesso `business_management` per questo campo.
- [Page Photos](https://developers.facebook.com/docs/graph-api/reference/page/photos/):
  `POST /{page-id}/photos`, upload `source`, `published=false`; token della
  pagina con task `CREATE_CONTENT` e permessi `pages_read_engagement`,
  `pages_manage_posts`, `pages_show_list`.
- [CoverPhoto](https://developers.facebook.com/docs/graph-api/reference/cover-photo/):
  verificare il campo `id` della copertina restituita dopo l'aggiornamento.

Il client usa `v26.0`, configurabile in `facebook.api_version`. La documentazione
non garantisce che il token e la pagina specifici possano eseguire l'operazione:
`fb-setup` prova la lettura, mentre il primo `fb-cover` prova la scrittura reale.
In caso di rifiuto Meta l'aggiornamento automatico resta bloccato e il PNG
rimane disponibile. Non si tenta un metodo alternativo non documentato.

## Collegamento e prima impostazione

1. Ottenere un **Page Access Token**, distinto da quello Instagram, con i
   ruoli e permessi sopra indicati. Configurare nel `.env` locale:

   ```dotenv
   FB_PAGE_ID=ID_NUMERICO_DELLA_PAGINA
   FB_PAGE_ACCESS_TOKEN=TOKEN_DELLA_PAGINA
   ```

2. Eseguire `momasocial fb-setup`. Mostra nome, ID e copertina della pagina
   senza modificarla. Con un token utente autorizzato, ricava in memoria il
   token della sola pagina indicata da `FB_PAGE_ID`. Un token di un'altra
   pagina o senza accesso alla pagina richiesta viene rifiutato prima di scrivere.
   Sono tollerati spazi esterni, virgolette e la riga `NOME=valore` incollata
   per intero nei Secrets; il valore consigliato resta il solo token della pagina.

3. Generare il mensile con `momasocial monthly --no-publish`, quindi aprire il
   PNG indicato come `facebook_cover`. `--date` indica sempre una data nel
   mese precedente a quello rappresentato.

4. Impostare davvero la prima copertina, ad esempio per novembre:

   ```bash
   momasocial fb-cover --file out/PERCORSO-facebook-cover.png --month 2026-11-01
   ```

   Il comando modifica Facebook anche se `facebook.publish_enabled` e' falso:
   e' il comando esplicito di prima impostazione. `--dry-run` produce soltanto
   la registrazione di anteprima. Non usare una copertina di un mese diverso.

5. La configurazione versionata abilita `facebook.publish_enabled`, ma i run
   automatici richiedono comunque un precedente successo per la stessa pagina
   e versione API. Conservare e committare la riga riuscita di
   `state/published.jsonl` se la prima impostazione e' stata eseguita in locale.

6. Aggiungere `FB_PAGE_ID` e `FB_PAGE_ACCESS_TOKEN` ai GitHub Secrets del
   repository. I segreti non vanno nei file versionati. Il workflow mensile
   li passa gia' al comando.

In alternativa alla prima impostazione locale, usare **Run workflow** con
`channel=facebook`, `dry_run=false` e una data del mese precedente a quello
desiderato (per ottobre: `2026-09-30`). Questa scelta esplicita esegue anche
la prima impostazione verificata e il workflow conserva il registro su GitHub.
`force` puo' restare falso: i precedenti tentativi saltati non bloccano il rilancio.

Da quel momento la copertina cambia insieme alla pubblicazione mensile,
normalmente il 30 alle 10:00 Europe/Rome (ultimo giorno nei mesi piu' corti).
Non sono richieste conferme ricorrenti. Cambiare pagina o versione API richiede
una nuova prima impostazione riuscita.

## Recupero degli errori

In **Actions → Post calendario mensile → Run workflow**, il parametro `channel`
sceglie `instagram` (solo carosello), `facebook` (solo copertina) oppure `both`
(entrambi, valore predefinito anche per i run programmati).
`dry_run` prova soltanto i canali selezionati senza chiamare le API;
`force` ripete la pubblicazione soltanto sui canali selezionati. Il canale
escluso non viene contattato e non riceve nuove righe nel registro.

La stessa scelta e' disponibile da CLI:

```bash
momasocial monthly --channel instagram
momasocial monthly --channel facebook --dry-run
momasocial monthly --channel facebook --force
```

La selezione rispetta `facebook.publish_enabled`: se falso, nessuna chiamata
di pubblicazione del mensile modifica Facebook. Con l'abilitazione attiva,
`channel=facebook` consente anche la prima impostazione; `both` e i run
programmati richiedono invece una verifica reale precedente, riuscita con
`fb-cover` oppure `monthly --channel facebook`.
Tutte le anteprime vengono comunque generate e archiviate.

Instagram e Facebook hanno chiavi ed esiti separati nel registro. Se un canale
fallisce, si tenta comunque l'altro e il comando termina con errore, riportando
entrambi gli esiti. Rilanciare il mensile ritenta solo il canale incompleto.
`--force` ignora i due controlli di duplicazione e carica una nuova foto.

L'ID della foto Facebook viene registrato prima di impostarla come copertina.
Se la scrittura o la verifica falliscono, il tentativo successivo riusa quell'ID
e controlla prima se la foto e' gia' stata applicata. Un timeout durante
l'upload, prima di ricevere l'ID, puo' lasciare una foto non pubblicata sul
server: senza quell'ID non e' possibile recuperarne con certezza il risultato.

Il workflow conserva output e registro anche quando la pubblicazione fallisce.
Token scaduti o permessi revocati producono un errore esplicito: correggere
le credenziali e rilanciare. L'aggiornamento della copertina richiede una lettura
di conferma; un semplice HTTP 200 non viene registrato come successo.

## Grafica

La sezione `[posts.monthly_calendar.facebook_cover]` configura `enabled`,
`image_template`, `width` e `height`. Il PNG ha dimensioni effettive
1640 × 720 pixel di default, indipendenti da `render.scale` del carosello.
Il template mostra settimane da lunedi a domenica, al massimo tre eventi
per giorno e `+N eventi` per gli ulteriori. I nomi troppo lunghi terminano
con ellissi. Tutti gli eventi alimentano la griglia, anche quelli che non
entrano nelle slide Instagram. Verificare il ritaglio desktop/mobile su Facebook
durante la prima impostazione.
