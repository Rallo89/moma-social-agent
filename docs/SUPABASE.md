# Collegare il database Supabase

Supabase espone ogni tabella via **PostgREST**: un endpoint REST che
restituisce JSON. Per l'agente e' una normale API HTTP, quindi non serve
nessuna libreria Supabase e nessuna modifica al codice — solo configurazione.

---

## Perche' REST e non la connessione Postgres

Supabase offre anche una connessione Postgres diretta, e l'adapter la
supporterebbe. **Non usarla per questo progetto:**

`db.<ref>.supabase.co` risolve **solo in IPv6**, e i runner di GitHub Actions
sono IPv4. I post schedulati fallirebbero tutti, pur funzionando dalla tua
macchina. Le alternative sarebbero il pooler Supavisor (IPv4) o l'add-on IPv4
a pagamento: complicazioni che l'API REST rende inutili.

L'API REST funziona ovunque, non ha dipendenze aggiuntive e passa dalle
policy RLS.

---

## 1. La chiave

Da **Project Settings → API** servono due cose:

- l'**URL del progetto**: `https://<ref>.supabase.co`
- la chiave **anon** (pubblicabile)

> **Usa la chiave `anon`, non `service_role`.** La `service_role` scavalca le
> policy RLS e puo' scrivere e cancellare qualunque cosa: darla a un agente
> che deve solo leggere tre tabelle e' sproporzionato. La `anon` fa solo
> quello che le policy permettono.

La chiave va in `.env` (locale) e nei GitHub Secrets (produzione), mai in
`config/config.toml`, che e' versionato:

```
SUPABASE_KEY=eyJhbGciOi...
```

## 2. Le policy di lettura

Con RLS attivo, la chiave `anon` non legge nulla finche' non glielo permetti.
Per ogni tabella usata dai post serve una policy di sola lettura. Nel SQL
Editor di Supabase:

```sql
create policy "lettura pubblica eventi"
  on public.eventi for select
  to anon
  using (true);
```

Ripeti per le tabelle dei risultati e delle classifiche. Nessuna policy di
`insert`, `update` o `delete`: l'agente non deve poter scrivere.

Se preferisci non esporre le tabelle cosi' come sono, crea delle **viste**
con le sole colonne che servono ai post e dai la policy a quelle.

## 3. Scoprire i nomi delle colonne

Invece di trascriverli dalla dashboard:

```bash
momasocial schema --url https://<ref>.supabase.co/rest/v1/
```

Legge la descrizione OpenAPI che PostgREST pubblica sulla propria radice e
stampa tabelle e colonne, gia' pronte per la sezione `map`. La chiave viene
da `SUPABASE_KEY`, oppure si passa con `--key`.

## 4. La configurazione

I filtri PostgREST stanno **nell'URL**. La sintassi e' `colonna=operatore.valore`:

```toml
[sources.events]
url = "https://<ref>.supabase.co/rest/v1/eventi?select=*&data=gte.{date_from}&data=lte.{date_to}&order=data.asc"

[sources.events.headers]
apikey        = "${SUPABASE_KEY}"
Authorization = "Bearer ${SUPABASE_KEY}"

[sources.events.map]
date       = "data"           # campo interno = colonna vostra
title      = "titolo"
format     = "formato"
start_time = "ora_inizio"
venue      = "sede"
```

Operatori utili: `eq` (uguale), `gte` / `lte` (maggiore/minore o uguale),
`in` (`?formato=in.(Pauper,Modern)`), piu' `order=colonna.asc` e `limit=`.

Placeholder disponibili: `{date}` `{date_from}` `{date_to}` `{format}`
`{season}`.

**Il filtro server-side e' un'ottimizzazione, non un requisito.** L'agente
riapplica sempre il filtro sui dati ricevuti: anche un `?select=*` senza
condizioni produce post corretti. Se una tabella cresce molto conviene
comunque filtrare e aggiungere `limit=`, per non scaricare tutto ogni volta.

## 5. Verificare

```bash
momasocial doctor            # prova le tre sorgenti e dice cosa e' arrivato
momasocial agenda --json     # gli eventi come li vede il codice
```

Poi genera un post senza pubblicarlo:

```bash
momasocial results --date 2026-03-13 --no-publish
```

## 6. In produzione

Aggiungi `SUPABASE_KEY` ai GitHub Secrets del repository e referenziala nei
workflow, come gli altri segreti.

---

## Se qualcosa non va

| Messaggio | Causa |
|---|---|
| `ha risposto 401 ... Invalid API key` | chiave sbagliata, o `SUPABASE_KEY` non valorizzata |
| `ha risposto 404` | nome tabella errato, o manca `/rest/v1/` nell'URL |
| Risposta `[]` con dati presenti | manca la policy RLS di lettura per `anon` |
| `Nessun evento fra ...` | i dati ci sono ma le date non combaciano: guarda `momasocial agenda --json` |
| Post vuoto ma la sorgente risponde | mappatura dei campi da correggere in `[sources.*.map]` |

Il messaggio d'errore riporta sempre il corpo della risposta di Supabase, che
di solito dice esattamente cosa non va.
