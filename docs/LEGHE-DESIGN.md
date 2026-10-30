# Classifiche delle leghe — layout approvato

Proposta approvata dall'utente prima di passare al calendario settimanale.

Revisione della scritta stagionale: font Cyber Brush fornito dall'utente
nell'archivio `cyber_brush_2.zip`, incorporato localmente come
`templates/images/fonts/CyberBrush.ttf`. Mantiene l'inclinazione naturale,
senza deformazioni artificiali, con bagliore neon nel colore del formato.
Sostituisce la precedente approssimazione Road Rage su tutte le varianti.

Reference esclusiva: seconda riga «Classifiche generali» della griglia
`social-design/references/griglia.png`. Il fondo scuro con accenti per formato
sostituisce la precedente indicazione verde del documento iniziale.

- Una slide 1080 × 1350 per lega aperta, top 8 nell'ordine della fonte ufficiale.
- Logo Modena Magic, etichetta formato, stagione e intestazione «Classifica generale».
- Colonne posizione, giocatore, punti cumulativi e tappe individuali dalla sorgente.
  Nessun ricalcolo dei punteggi o sostituzione delle tappe con il massimo della lega.
- Asset e colori condivisi con le Stories approvate, compreso il Colosso bianco
  per i formati non mappati. Il nome della stagione perde soltanto il prefisso
  formato quando questo è già rappresentato nell'etichetta.
- Logo Uno Critico in basso a sinistra, data dell'aggiornamento e numerazione
  a destra. Nessun numero di tappa inventato: manca un riferimento univoco nella vista.
- Configurazione in `posts.standings_update`; template dedicato
  `lega_vaporwave.html.j2`, senza cambiare Stories e risultati dei tornei approvati.

Anteprime reali del 30 ottobre 2026: Modern, Limited, Premodern, Legacy.
Pauper e Pioneer non risultano fra le leghe aperte restituite dalla sorgente:
nessuna classifica fittizia viene creata. Per tutte le slide viene usato
un unico snapshot della sorgente. PNG, caption, confronto e ZIP sono in
`out/leghe-review/`. Nessuna pubblicazione durante la revisione.
