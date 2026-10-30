# Calendario settimanale — proposta da approvare

Reference esclusiva: calendario a destra dell'immagine con due post,
`social-design/references/calendario-reference.png`. La classifica a sinistra
non viene utilizzata. Layout 1080 × 1350 con titolo «La settimana», intervallo
di date, schede orizzontali e footer con iscrizioni e logo Uno Critico.

Revisione di fedeltà alla reference: dettagli in Barlow Condensed Regular
(font locale con famiglia separata, senza cambiare le Stories), maiuscole
e indirizzo spaziato; titolo della tappa più grande, colonne e separatori
spostati secondo la reference. Cornici SVG con quattro angoli smussati,
contorno luminoso e doppio bagliore esterno. Tre schede con altezza minima di 224 px, distanti
20 px, a partire da y=448 sul canvas 1080 × 1350.

## Dati e comportamento

- Tre eventi per slide, con continuazione numerata per le settimane più ricche.
  Il superamento del limite del carosello blocca l'esportazione, senza tagli silenziosi.
- Ogni scheda mostra giorno, numero, mese, formato, tappa/finale o nome
  originale per eventi spot, ora, sede, indirizzo e quota.
- Colori condivisi con Stories e leghe, dai token scuri del sito. Variante
  bianca per i formati non mappati; lo sfondo generale usa il magenta della reference.
- Nessuna creatura nello sfondo del calendario: castelli, sole a fasce e griglia.
- Sede e quota dalla sorgente; ripieghi configurati già in uso. L'indirizzo
  abituale si applica soltanto quando coincide la sede, tramite l'adattatore esistente.
- Orario dalla sorgente, oppure `content.evento.ora_default`; se entrambi
  mancano, mostrare «Da definire». Analoga dicitura per la quota mancante.
- Titolo e data si ripetono sulle continuazioni. Il cambio d'anno mostra entrambi gli anni.
- Resta il raggruppamento dei tavoli della stessa tappa Limited già esistente.

## Integrazione e verifica

`posts.weekly_calendar.layout = "schede"` seleziona il nuovo template
`settimana_vaporwave.html.j2`; `layout = "legacy"` conserva il precedente
riepilogo più card evento. Solo la modalità legacy usa `riepilogo`.
Lo scheduling resta sulla settimana prossima; per l'anteprima del 30 ottobre
si usa un override in memoria su `settimana = "corrente"`.

Sfondo generato con ImageGen integrato, asset locale
`templates/images/assets/vaporwave-settimana.png`; prompt in `SETTIMANA-PROMPT.txt`.
Testi, icone e dati restano HTML/SVG. Non sono incorporati nell'immagine.

Prima anteprima reale: 26 ottobre–1 novembre 2026, tre tornei. La sorgente
non espone l'ora, quindi tutte le schede usano il ripiego configurato 21:00.
PNG, caption, manifest dei dati e ZIP in `out/settimana-review/`.
Nessuna pubblicazione durante la revisione.
