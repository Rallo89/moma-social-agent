# La card evento

Grafica di due dei tre post: il **calendario del lunedì** (un carosello, una
card per evento) e il **formato del giorno** (una card sola).

Nasce dall'artboard `templates/calendar/Template Evento Dark.dc.html`, fatto in
Claude Design. Il file dell'artboard resta nel repo come originale di
riferimento: quello che l'agente renderizza è la sua traduzione in
`templates/images/evento.html.j2`, dove i testi sono variabili.

## Cosa si cambia senza toccare il codice

Tutto in `config/config.toml`, sezione `[content.evento]`:

| Chiave | Riempie | Nell'esempio del grafico |
|---|---|---|
| `kicker_1` / `kicker_2` | occhiello in alto a destra | "Evento settimanale" / "Modena" |
| `kicker_calendario` | riga 1 delle slide del lunedì | "Calendario settimanale" |
| `badge` | fascia lime | "Modern · Torneo settimanale" |
| `titolo` | tipografia grande | "Giovedì Modern" |
| `quando` `dove` `quota` | blocco dati | usati solo se il database non li espone |
| `invito` `link` `qr` | piede | "Iscriviti" / "modenamagic.it/iscrizioni" |

Segnaposto disponibili nei modelli: `{format}` `{cadenza}` `{weekday}`
`{giorno}` `{data}` `{title}` `{venue}` `{city}` `{fee}` `{time}` `{org}`.

I dati dell'evento hanno la precedenza: `quando`, `dove` e `quota` in config
servono quando la sorgente non li espone. Oggi il Supabase non ha ora di
inizio né link iscrizioni, quindi quelli arrivano da qui.

`[content.evento.cadenza]` dichiara la cadenza per formato: una lega è
settimanale, una Prerelease no, e stampare "Torneo settimanale" su una
Prerelease sarebbe una frase falsa.

## I limiti del disegno

Il grafico indica: titolo 22 caratteri, quando 30, dove 28, iscrizione 26,
link 34. Oltre, il testo va a capo e rompe il ritmo.

Il template si difende da solo: prima di scattare lo screenshot rimpicciolisce
i testi che non ci stanno — in larghezza per le righe che devono restare su
una riga sola, in altezza per il titolo, che altrimenti spingerebbe il logo e
il piede fuori dalla slide. Un titolo di lunghezza normale resta a 190px,
identico all'artboard: la riduzione è un paracadute, non la regola.

## I font

`Bebas Neue`, `Barlow Condensed` e `JetBrains Mono` sono in
`templates/images/fonts/`, inlinati nella pagina come data URI. Non si caricano
da Google Fonts: il runner di GitHub Actions non ha font installati, e con un
webfont remoto Chromium può scattare lo screenshot prima che arrivi, mandando
in stampa un ripiego di sistema. Tutti in licenza SIL OFL 1.1 (`fonts/OFL-*.txt`).

## Gli asset

`logo-modena-magic.png`, `triangoli.png` e `unocritico.png` stanno in
`templates/images/assets/`, copiati da quelli dell'artboard. Se il grafico li
cambia, si sostituiscono lì.
