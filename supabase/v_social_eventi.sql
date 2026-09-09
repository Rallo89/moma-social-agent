-- ═══════════════════════════════════════════════════════════════════════════
--  v_social_eventi — eventi in calendario per l'agente social
--
--  Rispetto alla versione attuale aggiunge due colonne:
--
--    lega   nome della lega a cui la tappa appartiene (NULL per gli spot)
--    tappa  numero progressivo della tappa dentro quella lega
--
--  Servono al titolo della grafica, che deve essere uguale ogni settimana
--  ("Lega Pauper Fall 2026" / "Tappa 3") invece del nome che il torneo ha a
--  database, diverso ogni volta. Senza lega non c'e' nessuna tappa da
--  numerare e la card tiene il nome dell'evento: e' il caso degli eventi spot.
--
--  Il numero di tappa NON e' una colonna della tabella: si ricava contando i
--  tornei della stessa lega in ordine di data. Cosi' resta giusto anche se un
--  torneo viene spostato, e non c'e' un campo in piu' da tenere aggiornato a
--  mano. Il rovescio: aggiungere una tappa in mezzo rinumera quelle dopo.
--
--  ATTENZIONE — questa e' una BOZZA da fondere con la vista esistente.
--  La versione attuale espone gia' sede, quota e note, e non so da quali
--  colonne le prenda. Prima di eseguire:
--
--    1. leggere la definizione attuale
--         select pg_get_viewdef('public.v_social_eventi'::regclass, true);
--    2. tenerne tutte le colonne e aggiungere solo il join su leagues,
--       la colonna `lega` e la colonna `tappa` qui sotto.
--
--  Sostituire <UUID-MODENA-MAGIC> con lo stesso valore delle altre viste.
-- ═══════════════════════════════════════════════════════════════════════════

create or replace view public.v_social_eventi as
select t.start_date                    as data,
       t.name                          as titolo,
       t.format::text                  as formato,
       -- ... qui vanno le colonne che la vista attuale espone gia':
       --     sede, quota, note
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
-- Le tappe di una lega devono numerarsi 1, 2, 3... in ordine di data:
--
--   select lega, tappa, data, titolo
--   from public.v_social_eventi
--   where lega is not null
--   order by lega, tappa;
--
-- E gli eventi spot devono avere lega e tappa nulle:
--
--   select data, titolo, formato
--   from public.v_social_eventi
--   where lega is null
--   order by data;
