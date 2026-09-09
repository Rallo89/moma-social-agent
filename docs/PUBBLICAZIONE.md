# Mettere in linea la pubblicazione

Due cose mancano perché l'agente pubblichi da solo: **un posto pubblico da cui
Instagram scarichi le immagini** e **le credenziali dell'account**. Finché
mancano, tutto il resto funziona: i post si generano in `out/` e si guardano.

Si fanno in quest'ordine, perché la seconda si collauda solo se la prima
funziona.

---

## 1. Hosting delle immagini

La Content Publishing API **non accetta un file**: vuole un URL, e va a
scaricarlo lei, senza credenziali. Quindi i PNG devono stare su HTTP pubblico
prima della pubblicazione.

Due strade. Consiglio di partire dalla prima e passare alla seconda quando
volete tenervi i file.

### imgbb — cinque minuti, nessuna infrastruttura

1. Registratevi su <https://imgbb.com> e aprite <https://api.imgbb.com>.
2. Copiate la **API key**.
3. Nel `.env` (che non finisce su git):

   ```
   IMGBB_API_KEY=la-chiave
   ```
4. In `config/config.toml`:

   ```toml
   [media]
   backend = "imgbb"
   ```

### Cloudflare R2 — i file restano vostri

Piano gratuito da 10 GB, compatibile S3. Serve un account Cloudflare.

1. **R2 → Create bucket**, per esempio `moma-social`.
2. Nelle impostazioni del bucket abilitate l'accesso pubblico: o il dominio
   `r2.dev`, o un dominio vostro. Serve l'URL da cui Meta scaricherà.
3. **Manage R2 API Tokens → Create token**, permesso *Object Read & Write*.
   Vi dà Access Key ID, Secret Access Key e l'endpoint
   `https://<account-id>.r2.cloudflarestorage.com`.
4. Nel `.env`:

   ```
   MEDIA_BUCKET=moma-social
   MEDIA_PUBLIC_BASE=https://pub-xxxxxxxx.r2.dev
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   AWS_REGION=auto
   ```
5. In `config/config.toml`:

   ```toml
   [media]
   backend = "s3"

   [media.s3]
   endpoint_url = "https://<account-id>.r2.cloudflarestorage.com"
   acl          = ""        # ← obbligatorio su R2
   ```

   `acl = "public-read"` è il default e su **R2 fa fallire ogni upload**: R2
   non ha le ACL per oggetto, la visibilità si decide sul bucket. Su AWS S3
   invece va lasciato com'è. È l'errore che costa più tempo dei due.

   Serve anche `pip install '.[s3]'`, che porta boto3.

### Collaudo

```powershell
.\.venv\Scripts\momasocial weekly --no-publish   # genera qualcosa
.\.venv\Scripts\momasocial media-test
```

`media-test` carica l'ultimo PNG e poi **lo riscarica senza credenziali**,
come farebbe Meta. Vuole `200` e un `Content-Type: image/*`. Un `200` con
`text/html` è quasi sempre una pagina di login travestita: l'oggetto non è
pubblico.

Finché questo comando non è verde, non ha senso passare a Instagram: l'errore
che vedreste là (`container in stato ERROR`) non direbbe niente di utile.

---

## 2. Credenziali Instagram

Servono due valori: **`IG_USER_ID`** e **`IG_ACCESS_TOKEN`**. Tutto il resto
di questa sezione serve solo a ottenerli.

> La console di Meta cambia spesso nomi e posizioni delle voci. Quello che
> segue è il percorso, non i click esatti: se una voce si chiama diversamente,
> l'obiettivo resta ricavare quei due valori. La documentazione ufficiale è
> *Instagram Platform → Content Publishing* su developers.facebook.com.

### Prerequisiti sull'account

- L'account Instagram deve essere **professionale** (Business o Creator).
  Si cambia dall'app: Impostazioni → Tipo di account.
- Deve essere **collegato a una Pagina Facebook**. L'agente parla con
  `graph.facebook.com`, ed è questo il percorso che richiede la Pagina.
- Chi fa la configurazione deve essere amministratore di entrambi.

### Creare l'app Meta

1. <https://developers.facebook.com> → **My Apps → Create App**, tipo
   *Business*.
2. Aggiungete il prodotto **Instagram** (o *Instagram Graph API*) e collegate
   la Pagina Facebook.
3. I permessi che servono sono `instagram_basic`,
   `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`.

**La App Review di norma non serve**: finché pubblicate solo sull'account
della vostra associazione e le persone coinvolte hanno un ruolo sull'app
(amministratore, sviluppatore o tester), l'app può restare in sviluppo. La
Review serve per pubblicare su account di terzi.

### Ricavare i due valori

Con il **Graph API Explorer** (Tools → Graph API Explorer):

1. Selezionate l'app, chiedete i permessi qui sopra e generate un token.
2. `GET /me/accounts` → l'`id` della vostra Pagina.
3. `GET /<page-id>?fields=instagram_business_account` → **questo `id` è
   `IG_USER_ID`**.
4. Il token dell'Explorer dura un'ora. Scambiatelo con uno **long-lived**
   (60 giorni):

   ```
   GET /oauth/access_token
       ?grant_type=fb_exchange_token
       &client_id=<app-id>
       &client_secret=<app-secret>
       &fb_exchange_token=<token-breve>
   ```

   Il risultato è **`IG_ACCESS_TOKEN`**.

Il token **scade dopo 60 giorni**. Il workflow `token-check.yml` gira ogni
lunedì e apre una issue quando mancano meno di 14 giorni: quando la vedete, è
la cosa più urgente da fare, perché alla scadenza si fermano tutti i post
insieme e in silenzio.

---

## 3. Dove mettere i valori

**Sulla vostra macchina**, in `.env` (git-ignored):

```
IG_USER_ID=1784...
IG_ACCESS_TOKEN=EAAG...
IMGBB_API_KEY=...
```

**Su GitHub**, in *Settings → Secrets and variables → Actions*:

| Nome | Dove | Serve a |
|---|---|---|
| `IG_USER_ID` | Secret | account su cui pubblicare |
| `IG_ACCESS_TOKEN` | Secret | token long-lived |
| `IMGBB_API_KEY` | Secret | solo con backend imgbb |
| `MEDIA_BUCKET` | Secret | solo con backend s3 |
| `AWS_ACCESS_KEY_ID` | Secret | solo con backend s3 |
| `AWS_SECRET_ACCESS_KEY` | Secret | solo con backend s3 |
| `MEDIA_PUBLIC_BASE` | Variable | dominio pubblico del bucket |
| `AWS_REGION` | Variable | `auto` su R2 |

`config/config.toml` è versionato e contiene solo riferimenti `${VAR}`: le
chiavi non ci vanno mai.

---

## 4. La prima pubblicazione

Salite un gradino per volta, e fermatevi al primo rosso.

```powershell
.\.venv\Scripts\momasocial weekly --no-publish   # 1. la grafica esce?
.\.venv\Scripts\momasocial media-test            # 2. l'hosting regge?
.\.venv\Scripts\momasocial doctor                # 3. le credenziali sono valide?
.\.venv\Scripts\momasocial weekly --dry-run      # 4. il giro completo, senza rete
.\.venv\Scripts\momasocial weekly                # 5. pubblica davvero
```

`--dry-run` si ferma **prima di toccare la rete**: registra nel ledger cosa
sarebbe uscito senza caricare né pubblicare. Serve a controllare caption e
numero di slide, non l'hosting — quello è il passo 2.

Il passo 5 pubblica sul profilo vero. Il ledger `state/published.jsonl`
registra ogni tentativo, e la chiave di deduplica impedisce che un rilancio
produca un doppione: `--force` scavalca il controllo, e va usato solo se il
post precedente è stato davvero cancellato da Instagram.

### Interruttore generale

```toml
[instagram]
publish_enabled = false
```

Ogni pipeline si ferma prima di pubblicare e lascia i file in `out/`. È il
modo corretto di sospendere i social senza disattivare i workflow — utile
mentre configurate, e in caso di emergenza.

---

## Cosa non è un problema

- **Peso delle immagini**: le slide generate stanno sotto il mezzo megabyte,
  contro gli 8 MB che Instagram accetta.
- **Proporzioni**: 1080×1080 è dentro l'intervallo ammesso (fra 4:5 e 1.91:1).
- **Numero di slide**: i caroselli sono già limitati a 10, che è il massimo
  della API — l'app ne permette 20, ma noi passiamo di lì.
