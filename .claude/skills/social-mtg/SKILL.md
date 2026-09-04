---
name: social-mtg
description: Piano editoriale social dell'associazione MTG - come si generano, si rivedono e si pubblicano i post Instagram (calendario settimanale del lunedi, formato del giorno di mercoledi e giovedi, carosello risultati di tappa di giovedi e venerdi). Usala quando si parla di post Instagram, calendario eventi, spotlight di formato, risultati di tappa, classifiche, caption, o quando qualcosa nella pubblicazione automatica non ha funzionato.
---

# Piano editoriale social MTG

## Il calendario editoriale

| Quando (Europe/Rome) | Post | Contenuto | Comando |
|---|---|---|---|
| Lunedi 10:00 | Immagine singola | Calendario di tutti gli eventi della settimana | `momasocial weekly` |
| Mercoledi 10:00 | Immagine singola | Formato in programma quel giorno | `momasocial format` |
| Giovedi 10:00 | Immagine singola | Formato in programma quel giorno | `momasocial format` |
| Giovedi 03:00 | Carosello 2 slide | Risultati tappa di mercoledi + classifica generale | `momasocial results` |
| Venerdi 03:00 | Carosello 2 slide | Risultati tappa di giovedi + classifica generale | `momasocial results` |

I due post dei risultati girano alle 03:00 e leggono la tappa **del giorno
prima** (`--date yesterday`, che e' il default): a quell'ora il DB dei
risultati e' stato compilato a fine serata.

Il formato di mercoledi/giovedi **non e' cablato**: viene dedotto dagli eventi
in calendario per quel giorno. Se in sorgente non c'e' nulla, si usa il
fallback `content.formats_by_weekday` in `config/config.toml`.

## Come lavorare

Prima di toccare qualsiasi cosa, guarda i dati:

```bash
momasocial agenda                      # eventi della settimana corrente
momasocial doctor                      # config, sorgenti, rendering, credenziali
```

Per generare un'anteprima senza pubblicare nulla:

```bash
momasocial weekly  --no-publish
momasocial format  --date 2026-03-11 --no-publish
momasocial results --date 2026-03-11 --no-publish
```

Ogni run lascia in `out/`: il PNG, l'HTML sorgente (per capire un layout
sbagliato senza rilanciare), la caption in `.caption.txt` e i metadati `.json`.
**Guarda sempre il PNG** prima di dire che un post e' pronto: la caption puo'
essere perfetta e la slide illeggibile.

## Caroselli e numero di partecipanti

La grafica della classifica mostra 16 giocatori per slide (due colonne da 8).
Con piu' partecipanti il post diventa un carosello con piu' slide di risultati,
numerate nel sottotitolo ("Tappa 10 · 1/2"), seguite dalla classifica.

**Il limite vero e' 10 slide, non 20.** L'app Instagram ne accetta 20 ma la
Content Publishing API, con cui pubblichiamo, si ferma a 10. Oltre quel numero
le slide vengono tagliate partendo dalla classifica, che cede spazio ai
risultati; `meta.slide_tagliate` nel ledger dice quante se ne sono perse.
Se capita spesso, la strada e' alzare `rows_per_slide`, non il limite.

## La classifica e' facoltativa

Se la classifica generale non e' disponibile — formato senza lega, sorgente non
ancora collegata, o `--no-standings` — il post esce con le sole slide dei
risultati invece di non uscire affatto. La caption si adatta da sola.

Vale anche per la riga "prossima tappa": e' una rifinitura, e se la sorgente
eventi non risponde degrada in una frase generica senza far fallire un post
che ha gia' tutti i dati che gli servono.

## Regole di pubblicazione

- La pubblicazione e' automatica: i workflow GitHub Actions pubblicano da soli
  all'orario previsto. Non serve approvazione umana per il flusso normale.
- Il ledger `out/published.jsonl` rende l'operazione **idempotente**: rilanciare
  un workflow non produce un doppione. Per forzare davvero un secondo post
  serve `--force`, e va usato solo se il primo e' stato cancellato a mano.
- Kill switch: `instagram.publish_enabled = false` in config ferma ogni
  pubblicazione lasciando comunque i file generati in `out/`. E' il modo
  corretto di mettere in pausa i social (es. lutto, evento annullato), non
  disabilitare i workflow.
- `NoDataError` **non e' un errore**: se non ci sono eventi o risultati, la
  pipeline esce con codice 78 e il workflow salta il post. Non inventare
  contenuti per riempire un post vuoto, e non pubblicare una slide con dati
  parziali: meglio nessun post che un post sbagliato.

## Quando qualcosa non torna

1. `momasocial doctor` dice quale anello si e' rotto (sorgente, rendering, token).
2. Errori `SourceError` -> la sorgente dati e' cambiata: vedi la skill
   **sorgenti-dati**.
3. Errori di layout (testo tagliato, righe fuori slide) -> skill **template-grafici**.
4. Errori `PublishError` con codice Graph API -> skill **instagram-publishing**.

## Tono di voce

Italiano, diretto, entusiasta senza esagerare. Seconda persona plurale ("ci
vediamo ai tavoli"). Mai spoiler di risultati nel post del calendario. I nomi
dei giocatori si scrivono come li ha scritti il DB: non correggere maiuscole o
accenti a intuito, e non aggiungere soprannomi.
