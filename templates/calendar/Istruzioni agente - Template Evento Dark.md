# Template Evento Dark — istruzioni per l'agente

File da compilare: `Template Evento Dark.dc.html`
Output: post Instagram quadrato, 1080 × 1080 px.

## Come popolarlo

Sostituire **solo** i segnaposto `{{...}}` nel markup. Non modificare stili, dimensioni, colori, posizioni o gli asset. Ogni campo ha anche un attributo `data-slot` per individuarlo in modo affidabile.

| Segnaposto | data-slot | Contenuto | Limite consigliato |
|---|---|---|---|
| `{{KICKER_RIGA_1}}` | KICKER | prima riga dell'occhiello in alto a destra | max 20 caratteri |
| `{{KICKER_RIGA_2}}` | KICKER | seconda riga | max 20 caratteri |
| `{{FORMATO}}` | FORMATO | formato di gioco / tipo di evento, nel badge lime | max 34 caratteri |
| `{{TITOLO}}` | TITOLO | titolo dell'evento, tipografia grande | max 22 caratteri (o 2 parole) |
| `{{QUANDO}}` | QUANDO | data e ora | max 30 caratteri |
| `{{DOVE}}` | DOVE | luogo | max 28 caratteri |
| `{{QUOTA}}` | QUOTA | quota di iscrizione | max 26 caratteri |
| `{{LINK}}` | LINK | URL iscrizioni, senza `https://` | max 34 caratteri |

Se un campo supera il limite il testo va a capo e rompe il ritmo del layout: preferire un'abbreviazione (es. "gio 24 set · 20:30") piuttosto che allungare.

Il quadrato QR è un segnaposto: per un QR reale sostituire il contenuto di `data-slot="QR"` con `<img src="..." style="width:128px;height:128px;">` mantenendo il fondo chiaro.

## Regole di scrittura

- Tutto in italiano, tono diretto e informativo, nessuna enfasi promozionale ("imperdibile", "non mancare").
- Nessuna emoji.
- I testi vengono resi in maiuscolo dal CSS: scriverli in caso normale, non in CAPS.
- Titolo: nome dell'evento, non una frase (es. "Giovedì Modern", "Prerelease", "Legacy Night").
- Formato: nome del formato Magic più la cadenza, separati da `·` (es. "Modern · Torneo settimanale").
- Data: giorno della settimana, giorno e mese, ora — separati da virgola.

## Sistema grafico (per riferimento, non modificare)

Colori
- Fondo: `#14171a`
- Lime accento: `#a9d227`
- Testo principale: `#f2f4f0`
- Testo secondario: `#8b9490` / `#d5dad6`

Font (Google Fonts, già caricati nel file)
- `Bebas Neue` — titolo evento, 190 px
- `Barlow Condensed` 600/700 — dati evento (46 px), badge formato (30 px), "Iscriviti" (32 px)
- `JetBrains Mono` — occhiello, etichette Quando/Dove/Iscrizione (14 px, letter-spacing ampio), link (17 px)

Asset, sempre presenti e non sostituibili
- `assets/logo-modena-magic.png` — logo Modena Magic, in alto a sinistra, 168 px
- `assets/triangoli.png` — pattern triangoli, in alto a sinistra, ruotato, opacità 0.3
- `assets/unocritico.png` — logo Uno Critico, in basso a destra, 84 px

Struttura fissa: occhiello in alto, badge formato + titolo + blocco dati al centro con filo lime verticale, QR e link + logo Uno Critico in basso.

## Esempio compilato

```
KICKER_RIGA_1: Evento settimanale
KICKER_RIGA_2: Modena
FORMATO: Modern · Torneo settimanale
TITOLO: Giovedì Modern
QUANDO: Giovedì 24 settembre, 20:30
DOVE: Uno Critico — Modena
QUOTA: 10 € · include buste
LINK: modenamagic.it/iscrizioni
```
