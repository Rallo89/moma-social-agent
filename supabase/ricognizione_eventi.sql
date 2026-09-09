-- ═══════════════════════════════════════════════════════════════════════════
--  Ricognizione prima di toccare v_social_eventi
--
--  Tre query da lanciare nel SQL Editor di Supabase. Insieme dicono tutto
--  quello che serve per riscrivere la vista UNA VOLTA SOLA: cosa espone oggi,
--  cosa contiene davvero, e quali colonne esistono da cui pescare.
-- ═══════════════════════════════════════════════════════════════════════════

-- 1. Come e' fatta la vista adesso.
select pg_get_viewdef('public.v_social_eventi'::regclass, true) as definizione;

-- 2. Cosa restituisce davvero: interessa soprattutto se `quota` e' valorizzata
--    o se e' sempre nulla.
select *
from public.v_social_eventi
order by data desc
limit 5;

-- 3. Da quali colonne si puo' pescare. Cerchiamo dove vive il costo di
--    iscrizione, e confermiamo i nomi di quelle della lega.
select table_name, column_name, data_type
from information_schema.columns
where table_schema = 'public'
  and table_name in ('tournaments', 'leagues')
order by table_name, ordinal_position;
