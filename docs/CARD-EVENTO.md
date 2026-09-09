# Le card

Grafica di due dei tre post: il **calendario del lunedì** e il **formato del
giorno**.

Il lunedì esce un carosello: la prima slide è la **card di riepilogo**
(`settimana.html.j2`) con tutte le serate in elenco, poi una **card evento**
(`evento.html.j2`) per ogni serata. Le due condividono la cornice
(`_carta.html.j2`): fondo, trama, occhiello, filo lime, piede. Cambia solo il
centro, così non possono divergere. `riepilogo = false` in
`[posts.weekly_calendar]` lascia il solo carosello di card.

Nel riepilogo ogni riga porta il formato in testa — `Modern · Tappa 2` — perché
in un calendario è quello che si cerca; se il nome dell'evento lo dice già
(`Serata Commander`) non si ripete. L'elenco si rimpicciolisce da solo quando
le serate sono tante, in blocco, così le proporzioni fra le righe restano
quelle.

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
   `Tappa N` (o `Finale`), in tipografia grande. È la forma normale, e resta
   identica ogni settimana.
2. **Evento spot** — una riga sola con il nome del torneo a database. Un
   evento che non appartiene a nessuna lega non ha una tappa da numerare, e il
   suo nome è l'unica cosa che lo identifica.
3. **Nessun evento** — il modello `titolo` in configurazione (`{weekday}
   {format}`). Capita solo quando il post del formato del giorno viene
   generato dal fallback `content.formats_by_weekday`.

Una lega senza numero di tappa ricade nel caso 2: meglio il nome del torneo
che un "Tappa" senza numero.

**Il numero di tappa non è un campo del database**: l'unico posto dove esiste
è il nome del torneo, e `stage_from_title` lo legge da lì. I nomi sono scritti
a mano e assumono molte forme — `Tappa 3`, `1° tappa`, `quinta tappa`,
`Tappa 1 -Recupero` — tutte riconosciute; il numero è limitato a due cifre,
altrimenti `Lega Pauper Fall 1° tappa 2026` diventerebbe la tappa 2026. Quello
che non si riconosce resta senza numero e ricade sul caso 2: meglio il nome
del torneo che un numero sbagliato.

Contarle in ordine di data sembrava più pulito, ma sui dati veri sbaglia: le
finali sono datate fuori sequenza, una serata di Limited gira su due o tre
tavoli che a database sono tornei distinti, e le tappe saltate lasciano buchi.

Quei tavoli multipli sono anche il motivo di `_una_card_per_tappa`: nel
carosello del lunedì tre tornei con la stessa lega, tappa e data diventano una
card sola.

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
