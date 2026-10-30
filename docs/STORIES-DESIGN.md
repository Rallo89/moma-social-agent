# Stories Vaporwave — proposta da approvare

## Revisione della disposizione informazioni

La reference `social-design/references/stories-info-layout.png` aggiorna
disposizione e dimensioni dei dati per tutte le varianti, compresa quella bianca.
Su canvas 1080 × 1920: data a tutta larghezza da y=925 (testo 92 px,
etichetta 44 px e icona 108 px), iscrizione a sinistra e orario a destra
da y=1155 (valori 66 px), separatore a y=1367 e sede in basso a destra.
I loghi e il footer approvati restano nelle loro posizioni.
Il titolo mantiene integralmente il nome del torneo, adattando il corpo
alla larghezza disponibile con le metriche del font locale, senza occupare
la zona dati. I titoli stagionali non sono più separati su tre righe.

Riferimento: prima riga **Tornei (annunci)** di `social-design/references/griglia.png`.
Le altre righe e le altre reference non guidano il layout Stories.

Canvas 1080 × 1920; contenuti principali fra 205 e 1660 px, fuori dalle
fasce dell'interfaccia Instagram. Titoli, date, ora, sede e quota sono HTML,
le illustrazioni non contengono testi. Restano selezione eventi e pubblicazione esistenti.

## Palette e creature

Colori dal tema scuro del repository locale `D:/Repos/Modena.Magic`,
`src/app/globals.css`, token `--format-*` (verificati il 30 ottobre 2026).
La mappatura operativa è in `config/config.toml`, `posts.story_event.illustrations`.
È una fotografia dei token: aggiornare questa mappatura se cambia la palette del sito.

| Formato | Colore | Soggetto |
| --- | --- | --- |
| Pauper | #2dd4bf | Myr Enforcer |
| Modern | #818cf8 | Eldrazi |
| Premodern | #ffb77d | Phyrexian Dreadnought |
| Legacy | #c084fc | Griselbrand |
| Pioneer | #ffb77d | Arclight Phoenix, scelta esplicita dell'utente |
| Limited | #81cfff | Drago |

Premodern e Pioneer condividono il colore del sito. La loro distinzione
avviene tramite etichetta e creatura. I formati non mappati usano il Colosso di Darksteel già creato,
ricolorato bianco/argento su fondo scuro (accento #ffffff), come richiesto
dall’utente. Il nome del formato rimane quello effettivo dell’evento.

## Asset e anteprime

Le sette illustrazioni sono interpretazioni generate con lo strumento integrato
ImageGen, non illustrazioni ufficiali delle carte. Verificare la riconoscibilità
dei soggetti durante l'approvazione grafica. Asset e prompt completi:
`templates/images/assets/stories/vaporwave/`.
La revisione Pauper segue la reference anatomica fornita dall'utente,
`social-design/references/myr-enforcer.png`: torso bombato, pugno alzato,
avambraccio allungato e gambe corte. Il Myr viene reinterpretato con piani
sfaccettati e luce verde acqua, coerentemente con le altre Stories.
I vecchi ritagli ufficiali sono conservati ma non più usati dalle nuove Stories.
La nota fan resta nel template; non vengono attribuite le nuove immagini agli artisti delle carte.

Da radice del progetto:

```powershell
.\.venv\Scripts\python.exe scripts/preview_stories.py
```

Genera PNG, JPEG e HTML per sei formati più un esempio Commander con il
Colosso neutro, e `out/stories-review/confronto.jpg`, senza interrogare
le sorgenti né pubblicare. I valori delle sei anteprime sono **dati fittizi di layout**:
data, quota e tappa non rappresentano un calendario reale.
La pipeline ordinaria continua a usare i dati degli eventi.

La revisione riguarda tutte le Stories. Risultati, leghe e calendario
rimangono una fase successiva, dopo approvazione dell'utente.
