-- ═══════════════════════════════════════════════════════════════════════════
--  v_social_eventi — eventi in calendario per l'agente social
--
--  Sostituisce la versione attuale ed espone tutto quello che serve alla card
--  evento, cosi' non si torna piu' a toccarla:
--
--    sede / indirizzo   dove si gioca
--    quota              tournaments.costo — il prezzo vero, non uno in config
--    lega               nome della lega, prima riga del titolo della grafica
--    tipo / stato       non usati oggi, ma li abbiamo sotto mano se servono
--
--  Il NUMERO DI TAPPA non c'e', e non e' una dimenticanza. Contare i tornei
--  della lega in ordine di data sembrava ovvio ma sui dati veri sbaglia:
--  le finali sono datate fuori sequenza (la finale di Modern Autumn 2025 e'
--  del 12 maggio, prima della tappa 1), una serata di Limited gira su due o
--  tre tavoli che a database sono tornei distinti, e le tappe saltate
--  lasciano buchi. Il numero vero e' scritto nel nome del torneo, e da li'
--  lo legge l'agente.
--
--  I tornei `eliminato` sono esclusi: sono cancellati, e annunciarli in
--  calendario sarebbe peggio che non annunciare niente. Restano `aperto` e
--  `chiuso`. Fuori anche i tornei senza data, che sono prove.
--
--  Nessun dato personale: solo il torneo, mai chi ci gioca.
--
--  Sostituire <UUID-MODENA-MAGIC> con lo stesso valore delle altre viste.
--
--  PERCHE' UN DROP E NON UN CREATE OR REPLACE
--  `create or replace view` in Postgres sa solo aggiungere colonne in fondo:
--  non puo' rinominarle ne' riordinarle, e qui l'ordine cambia. Da cui
--
--      ERROR: cannot change name of view column "quota" to "indirizzo"
--
--  Il drop e' senza CASCADE apposta: se qualcosa dipendesse da questa vista,
--  meglio un errore che scoprire dopo di averlo cancellato. In quel caso
--  fermarsi e guardare cosa dipende, invece di aggiungere CASCADE.
--  Fra il drop e il create la vista non esiste: eseguire tutto insieme.
-- ═══════════════════════════════════════════════════════════════════════════

drop view if exists public.v_social_eventi;

create view public.v_social_eventi as
select t.start_date                    as data,
       t.name                          as titolo,
       t.format::text                  as formato,
       -- location_alias e' il nome del locale, location l'indirizzo esteso.
       -- Se nei vostri dati sono invertiti, scambiare queste due righe.
       t.location_alias                as sede,
       t.location                      as indirizzo,
       t.costo                         as quota,
       t.description                   as note,
       t.kind::text                    as tipo,
       t.status::text                  as stato,
       l.name                          as lega
from public.tournaments t
left join public.leagues l on l.id = t.league_id
where t.community_id = '<UUID-MODENA-MAGIC>'
  and t.status::text <> 'eliminato'
  and t.start_date is not null;

grant select on public.v_social_eventi to anon;

-- ── Verifica ────────────────────────────────────────────────────────────────
-- a) sede, indirizzo e quota devono esserci:
--
--      select data, titolo, sede, quota
--      from public.v_social_eventi
--      order by data desc
--      limit 10;
--
-- b) nessun torneo eliminato e nessuna data nulla:
--
--      select count(*) filter (where stato = 'eliminato') as eliminati,
--             count(*) filter (where data is null)        as senza_data
--      from public.v_social_eventi;
