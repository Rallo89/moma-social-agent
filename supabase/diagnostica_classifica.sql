-- ═══════════════════════════════════════════════════════════════════════════
--  Scompone la classifica nei cinque addendi che formano il totale.
--
--  Serve a confrontare i numeri con quelli mostrati dall'app: quando una
--  posizione non coincide, dice QUALE componente diverge invece di lasciare
--  indovinare fra punti base, bonus piazzamento, presenza ed eventi bonus.
--
--  Sostituire <LEGA> con l'id della lega da verificare.
-- ═══════════════════════════════════════════════════════════════════════════

with lega as (
  select id                                             as lega_id,
         greatest(coalesce(presence_bonus_points, 0), 0) as pbp,
         greatest(coalesce(presence_bonus_every, 2), 1)  as pbe,
         greatest(coalesce(bonus_event_points, 0), 0)    as bep,
         greatest(coalesce(best_of, 0), 0)               as bo,
         placement_bonus_top8                            as pb8
  from public.leagues
  where id = '<LEGA>'
),
tornei as (
  select t.id as torneo_id, coalesce(t.is_league_bonus, false) as e_bonus, t.start_date
  from public.tournaments t, lega
  where t.league_id = lega.lega_id
    and (t.status is null or t.status::text in ('aperto', 'in_corso', 'chiuso'))
    and coalesce(t.kind::text, '') <> 'league_final'
    and coalesce(t.description, '') not like '%[LEAGUE_FINAL_BRACKET]%'
),
righe as (
  select tor.torneo_id, tor.e_bonus, tor.start_date,
         case when tp.registered_user_id is not null
              then 'user:' || tp.registered_user_id::text
              else 'name:' || lower(btrim(tp.player_name)) end as chiave,
         nullif(btrim(tp.player_name), '')       as nome,
         case when tp.rank > 0 then tp.rank end  as posizione,
         greatest(coalesce(tp.points, 0), 0)     as punti
  from public.tournament_players tp
  join tornei tor on tor.torneo_id = tp.tournament_id
  where coalesce(tp.status::text, '') <> 'canceled'
    and (tp.registered_user_id is not null or btrim(coalesce(tp.player_name, '')) <> '')
),
per_torneo as (
  select chiave, torneo_id, min(posizione) as posizione, max(punti) as punti
  from righe where not e_bonus group by chiave, torneo_id
),
ordinati as (
  select p.*, row_number() over (partition by chiave order by punti desc, torneo_id) as n
  from per_torneo p
),
-- Aggregati per giocatore, senza join che moltiplichino le righe.
standard as (
  select o.chiave,
         count(*)                                                       as tornei,
         sum(o.punti) filter (where lega.bo = 0 or o.n <= lega.bo)      as punti_base,
         sum(case when o.posizione between 1 and 8
                  then coalesce((lega.pb8 ->> o.posizione::text)::int, 0)
                  else 0 end)                                           as bonus_piazz
  from ordinati o cross join lega
  group by o.chiave
),
eventi_bonus as (
  select chiave, count(distinct torneo_id) as tornei_bonus
  from righe where e_bonus group by chiave
),
nomi as (
  select distinct on (chiave) chiave, nome from righe
  where nome is not null
  order by chiave, start_date desc nulls last, torneo_id
)
select
  coalesce(n.nome, 'Sconosciuto')                        as giocatore,
  coalesce(s.tornei, 0)                                  as tornei,
  coalesce(s.punti_base, 0)                              as "1_punti_base",
  coalesce(s.bonus_piazz, 0)                             as "2_bonus_piazzamento",
  coalesce(s.tornei, 0)                                  as "3_punto_presenza",
  floor(coalesce(s.tornei, 0) / lega.pbe) * lega.pbp     as "4_bonus_periodico",
  coalesce(b.tornei_bonus, 0) * lega.bep                 as "5_eventi_bonus",
  coalesce(s.punti_base, 0) + coalesce(s.bonus_piazz, 0) + coalesce(s.tornei, 0)
    + floor(coalesce(s.tornei, 0) / lega.pbe) * lega.pbp
    + coalesce(b.tornei_bonus, 0) * lega.bep             as totale
from (select distinct chiave from righe) g
cross join lega
left join standard     s on s.chiave = g.chiave
left join eventi_bonus b on b.chiave = g.chiave
left join nomi         n on n.chiave = g.chiave
order by totale desc, giocatore;
