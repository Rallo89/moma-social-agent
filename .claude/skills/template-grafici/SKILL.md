---
name: template-grafici
description: Come sono fatti i template delle immagini Instagram (HTML+Jinja2 renderizzati in PNG 1080x1350 con Chromium) e come inserire il template grafico fornito dal grafico. Usala quando si deve cambiare un layout, aggiungere una slide, sistemare testo tagliato o fuori formato, cambiare colori e font, o quando arriva un nuovo file grafico da usare come sfondo.
---

# Template grafici

## Come funziona il rendering

`templates/images/*.html.j2` -> Jinja2 -> HTML -> Chromium headless -> PNG.
Misura di uscita: `render.width` x `render.height` (default 1080x1350, il 4:5
verticale del feed) moltiplicata per `render.scale` (default 2).

Tutte le slide estendono `_base.html.j2`, che definisce tre fasce fisse:

```
header   (auto)  eyebrow + titolo + filetto
body     (1fr)   contenuto della slide, con overflow nascosto
footer   (auto)  handle, sito, logo
```

E' una **griglia**, non un flex: cosi' il footer resta sempre dentro la slide
anche quando il contenuto e' troppo. Se il contenuto sborda viene tagliato nel
mezzo, non spinge fuori il footer.

## Inserire il template grafico fornito dall'associazione

1. Esporta lo sfondo a 1080x1350 (o 2160x2700) e salvalo in
   `templates/images/assets/`, es. `sfondo_calendario.png`.
2. In `config/config.toml`, nella sezione del post:
   ```toml
   [posts.weekly_calendar]
   background = "templates/images/assets/sfondo_calendario.png"
   ```
   Chiavi disponibili: `posts.weekly_calendar.background`,
   `posts.format_spotlight.background`, `posts.leg_results.background` e
   `posts.leg_results_standings.background` (se le due slide del carosello
   hanno sfondi diversi).
3. Rigenera e **guarda il PNG**: quasi sempre servira' spostare le safe zone
   nel blocco `{% block styles %}` della slide, perche' lo sfondo ha gia' il
   suo titolo o le sue decorazioni.

Lo sfondo viene inlinato come data URI: il PNG finale non dipende da file
esterni e non puo' "rompersi" in produzione per un path sbagliato.

## Recuperare gli sfondi da Canva

Se i template vivono su Canva, `momasocial canva-sync` li riesporta e li
scrive direttamente in `templates/images/assets/`.

```bash
momasocial canva-sync --check          # cosa cambierebbe, senza scrivere
momasocial canva-sync                  # riesporta tutto
momasocial canva-sync --only sfondo_calendario.png
```

La configurazione sta in `[canva]` e nei blocchi `[[canva.assets]]` di
`config/config.toml`: ogni blocco lega un `design_id` (la parte dopo `/design/`
nell'URL di Canva) a un file di destinazione. `page` serve quando un solo
design contiene piu' sfondi su pagine diverse.

**Il sync non gira nei workflow schedulati, e non va messo li'.** L'OAuth di
Canva e' per utente, con refresh token monouso a rotazione: una catena rotta
richiede una riautorizzazione dal browser, e non deve poter fermare il post del
lunedi' mattina. I workflow leggono i PNG committati nel repo; Canva li
aggiorna solo quando qualcuno lancia il sync a mano.

Setup dell'integrazione: `docs/CANVA.md`. Nota che su Canva "Private" significa
*riservata a un team Enterprise*: per un uso come il nostro si crea
un'integrazione **Public** e la si lascia in draft, senza inviarla in revisione.

**Il design puntato da `[[canva.assets]]` dev'essere quello pulito**, senza i
livelli di testo segnaposto: altrimenti il sync sovrascrive lo sfondo buono
con l'export che ha `{{NOME}}` e `{p}` impressi nella grafica.

Errori tipici:

| Messaggio | Cosa significa |
|---|---|
| `Nessun token Canva in ...` | non e' mai stata fatta l'autorizzazione: `momasocial canva-auth` |
| `invalid_grant` / `Refresh token used twice` | catena dei refresh token rotta: riesegui `canva-auth` |
| `Risorsa non trovata su Canva` | `design_id` sbagliato, o il design non appartiene all'account autorizzato |
| `richiesta pagina N ma il design ne ha M` | `page` fuori range in `[[canva.assets]]` |

Dopo ogni sync che riporta "aggiornato", **guarda i PNG**: uno sfondo nuovo
sposta quasi sempre le safe zone del testo.

## Font

Il rendering usa i font di sistema. Per usare il font del brand:
1. Metti il `.woff2`/`.ttf` in `templates/images/fonts/`.
2. Aggiungi in `_base.html.j2` una `@font-face` con `src: url('{{ "templates/images/fonts/Brand.woff2"|asset }}')`.
3. Imposta `brand.font_family` in config.

Il filtro `|asset` inlina qualunque file come data URI: vale per font, logo e
immagini.

## Testo che non ci sta

In ordine di preferenza:

1. Le classi `dense-8` / `dense-10` / `dense-12` (assegnate automaticamente da
   `pipelines._density`) riducono il corpo quando le righe sono molte.
2. Riduci `posts.leg_results.top_n` / `standings_top_n`: meglio una top 8
   leggibile che una top 16 illeggibile su un telefono.
3. Solo come ultima cosa, tocca i `font-size` nel blocco `styles` della slide.

## Verificare una modifica

```bash
momasocial weekly --date 2026-03-11 --no-publish
```

Poi apri il PNG in `out/`. L'HTML corrispondente e' salvato accanto: aprilo nel
browser per ispezionare il layout con i devtools invece di indovinare.
