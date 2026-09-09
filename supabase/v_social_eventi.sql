-- ═══════════════════════════════════════════════════════════════════════════
--  v_social_eventi — eventi in calendario per l'agente social
--
--  Sostituisce la versione attuale ed espone tutto quello che serve alla card
--  evento, cosi' non si torna piu' a toccarla:
--
--    sede / indirizzo   dove si gioca, su due righe nella grafica
--    quota              tournaments.costo — il prezzo vero, non uno in config
--    lega / tappa       titolo standard: "Lega Pauper Fall" / "Tappa 3"
--    tipo / stato       non usati oggi, ma li abbiamo sotto mano se servono
--
--  Il numero di tappa NON e' una colonna: si ricava contando i tornei della
--  stessa lega in ordine di data. Nessun campo da aggiornare a mano, e resta
--  giusto se un torneo viene spostato. Il rovescio: inserire una tappa in
--  mezzo alla stagione rinumera quelle successive.
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
       l.name                          as lega,
       case
         when t.league_id is null then null
         else row_number() over (partition by t.league_id
                                 order by t.start_date, t.id)
       end                             as tappa
from public.tournaments t
left join public.leagues l on l.id = t.league_id
where t.community_id = '<UUID-MODENA-MAGIC>';

grant select on public.v_social_eventi to anon;

-- ── Verifica ────────────────────────────────────────────────────────────────
-- a) sede e indirizzo non devono essere invertiti, e la quota deve esserci:
--
--      select data, titolo, sede, indirizzo, quota
--      from public.v_social_eventi
--      order by data desc
--      limit 10;
--
-- b) le tappe di una lega devono numerarsi 1, 2, 3... in ordine di data:
--
--      select lega, tappa, data, titolo
--      from public.v_social_eventi
--      where lega is not null
--      order by lega, tappa;
--
-- c) quali stati esistono davvero, per capire se ce n'e' uno da escludere
--    dal calendario (un torneo annullato non va annunciato):
--
--      select stato, count(*)
--      from public.v_social_eventi
--      group by stato
--      order by 2 desc;
