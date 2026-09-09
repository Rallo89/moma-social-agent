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
| `badge` | fascia lime | "Modern" |
| `titolo` | tipografia grande | solo se l'evento non ha un nome a database |
| `quando` `dove` `indirizzo` | blocco dati | usati solo se il database non li espone |
| `invito` `link` `qr` | piede | "Iscriviti" / l'indirizzo del sito |

Segnaposto disponibili nei modelli: `{format}` `{weekday}` `{giorno}`
`{data}` `{title}` `{venue}` `{city}` `{fee}` `{time}` `{org}`.

Il **titolo** ha tre forme, in ordine di preferenza:

1. **Tappa di lega** — due righe: sopra il nome della lega, più piccolo; sotto
   `Tappa N`, in tipografia grande. Serve che la vista esponga sia `lega` sia
   `tappa`. È la forma normale, e resta identica ogni settimana.
2. **Evento spot** — una riga sola con il nome del torneo a database. Un
   evento che non appartiene a nessuna lega non ha una tappa da numerare, e il
   suo nome è l'unica cosa che lo identifica.
3. **Nessun evento** — il modello `titolo` in configurazione (`{weekday}
   {format}`). Capita solo quando il post del formato del giorno viene
   generato dal fallback `content.formats_by_weekday`.

Una lega senza numero di tappa ricade nel caso 2: meglio il nome del torneo
che un "Tappa" senza numero.

Il numero di tappa non è un campo del database: la vista lo calcola contando
i tornei della stessa lega in ordine di data — vedi
`supabase/v_social_eventi.sql`.

L'**indirizzo** è la riga piccola sotto la sede. Compare solo quando la sede
dell'evento coincide con `dove`: accostare l'indirizzo di Uno Critico a un
torneo giocato altrove indicherebbe il posto sbagliato.

I dati dell'evento hanno la precedenza: `quando`, `dove` e la quota in config
servono quando la sorgente non li espone. Oggi il Supabase non ha ora di
inizio né link iscrizioni, quindi quelli arrivano da qui.

`[content.evento.quota]` dichiara la quota per formato — il Pauper non costa
come il Limited — con `default` per tutti gli altri.

Il `link` si scrive per intero in configurazione: la card lo stampa senza
`https://`, come chiede il grafico, ma il valore completo resta disponibile
altrove.

`qr` è vuoto: senza un PNG vero il riquadro non viene disegnato affatto. Per
riattivarlo basta metterci il percorso di un file.

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
