# Verificare la classifica di lega

`v_social_classifica` non legge un dato: **riproduce un calcolo** che vive nella
webapp. L'unico riscontro possibile e' il confronto con quello che l'app mostra
ai giocatori. Nessun test automatico puo' sostituirlo, perche' testerebbe la
mia lettura del codice contro se stessa.

Questa procedura rende il confronto meccanico invece che a occhio.

---

## 1. Scegliere la lega giusta

Non una qualsiasi: quella che mette alla prova piu' regole. Una lega con tutti
i bonus a zero e `best_of = 0` verifica solo una somma, e passerebbe anche se
avessi sbagliato tutto il resto.

Esegui `supabase/scegli_lega_da_verificare.sql`: ordina le leghe per numero di
meccanismi attivi (best_of, bonus piazzamento, eventi bonus, bonus presenza).
**Parti dalla prima.**

## 2. Prendere i numeri della vista

```sql
select posizione, giocatore, punti, tappe
from public.v_social_classifica
where lega_id = '<LEGA>'
order by posizione;
```

## 3. Confrontare con l'app

Apri la stessa lega nella webapp, tab **Classifica**. Tre cose devono
coincidere, in quest'ordine di importanza:

| Cosa | Perche' conta |
|---|---|
| **Numero di giocatori** | se differisce, sbaglio a includere o escludere qualcuno: chiave giocatore, `status`, tornei filtrati |
| **Somma totale dei punti** | se differisce a parita' di giocatori, sbaglio un addendo per tutti |
| **Le prime 8 posizioni**, ordine e punti | se differisce solo qui, e' un problema di spareggi o di un singolo giocatore |

Se tutti e tre coincidono, la traduzione e' corretta per quella lega. Ripeti
sulla seconda lega piu' complessa: due leghe concordi sono un riscontro solido.

## 4. Se un numero non coincide

Esegui `supabase/diagnostica_classifica.sql` sulla stessa lega. Scompone il
totale nei cinque addendi:

```
giocatore  tornei  1_punti_base  2_bonus_piazzamento  3_punto_presenza  4_bonus_periodico  5_eventi_bonus  totale
```

Cerca il giocatore che diverge e guarda **quale colonna** e' sbagliata:

| Colonna sbagliata | Dove guardare |
|---|---|
| `1_punti_base` | il troncamento `best_of`, o la deduplicazione per torneo (piazzamento migliore, punteggio piu' alto) |
| `2_bonus_piazzamento` | la forma di `placement_bonus_top8`, o il fatto che il bonus vale su **tutti** i tornei standard, anche quelli esclusi dal best_of |
| `3_punto_presenza` | quali tornei vengono contati: filtro su `status`, esclusione del torneo finale, separazione standard/bonus |
| `4_bonus_periodico` | `presence_bonus_every` e la divisione intera |
| `5_eventi_bonus` | il flag `is_league_bonus` sui tornei |

Mandami la riga divergente con la scomposizione: con quella si capisce subito
dove ho sbagliato a tradurre.

## 5. Un controllo che non richiede l'app

Su una lega con **tutti i bonus a zero e `best_of = 0`**, il totale deve essere
esattamente:

```
somma dei punti dei tornei giocati + numero di tornei giocati
```

Verificabile a mano su un giocatore in due minuti. Non prova le regole
complesse, ma se fallisce questa non serve nemmeno guardare il resto.

## 6. Dopo la verifica

Genera il carosello vero e guarda le immagini:

```bash
momasocial results --date <data-ultima-tappa> --no-publish
```

Le prime cinque posizioni compaiono anche nella caption: e' un'ultima
occasione per accorgersi di un numero fuori posto prima che finisca su
Instagram.

---

## Quando rifare questa verifica

Ogni volta che nella webapp cambia una regola di punteggio. La vista **non se
ne accorge**: continua a calcolare con le regole vecchie, senza errori e senza
test rossi.

E' il motivo per cui l'obiettivo resta far leggere anche alla webapp questa
vista: finche' ci sono due implementazioni, questa procedura va rieseguita a
ogni cambio.
