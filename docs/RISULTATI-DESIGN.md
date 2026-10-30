# Risultati dei tornei — layout Vaporwave approvato

Layout approvato dall'utente: logo Uno Critico in basso a sinistra e
partecipanti a destra del nome del torneo nella fascia sopra la classifica.

Reference: carosello multipagina «Infografica Neon Torneo Pauper Modena Magic».
La classifica di lega nella parte destra di quella reference è esclusa.

- PNG 1080 × 1350 reali, scala 1; testi, punti e grafici renderizzati da HTML/SVG.
- Prime 8 posizioni nella prima slide con nome del torneo e sede; successive 16 per slide.
- Partecipanti a destra del nome del torneo nella fascia della prima slide;
  logo Uno Critico in basso a sinistra su tutte le slide, inclusa quella del meta.
- Posizioni e record restano quelli restituiti dall'adattatore esistente, senza ricalcolo.
- Meta nell'ultima slide, con donut, legenda, percentuali e conteggi. Denominatore:
  tutti i partecipanti rappresentati nei risultati; mazzi mancanti separati come
  «Non dichiarato». Mostrare sempre la copertura «Mazzi registrati: N su totale».
- Se non è registrato alcun mazzo, conservare la slide finale con il messaggio
  «Dati dei mazzi non disponibili», senza grafico inventato.
- Numerazione dell'intero carosello, inclusa la slide meta. Nessun ringraziamento.
- Riutilizzo degli asset e della palette approvati per le Stories, compreso il
  Colosso bianco per gli altri formati, senza modificare il template delle leghe.
- Oltre il limite configurato/API: bloccare la generazione anziché omettere giocatori.
  L'opzione CLI esplicita `--no-meta` rimane disponibile.

Configurazione: `posts.leg_results` in `config/config.toml`. Template:
`risultati_vaporwave.html.j2` e `risultati_meta.html.j2`, con base comune
`_risultati_vaporwave.html.j2`. I vecchi template `classifica.html.j2` e
`meta.html.j2` rimangono disponibili e non vengono ridisegnati.

Prima revisione con dati reali: Pauper del 28 ottobre 2026, 29 partecipanti,
29 mazzi noti. Il carosello contiene 3 pagine di classifica (8 + 16 + 5) e
una pagina meta. Artefatti di revisione in `out/risultati-review/`.
Nessuna pubblicazione durante la prova.
