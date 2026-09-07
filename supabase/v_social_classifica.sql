-- ═══════════════════════════════════════════════════════════════════════════
--  v_social_classifica — classifica di lega per l'agente social
-- ═══════════════════════════════════════════════════════════════════════════
--
--  Traduzione in SQL di computeLeagueStandings (src/lib/league-standings.ts
--  della webapp Modena.Magic). E' una SECONDA implementazione della stessa
--  regola: se il calcolo cambia nella webapp e non qui, l'agente pubblica
--  numeri che smentiscono l'app, senza che nulla segnali l'errore.
--
--  Prima di ogni pubblicazione automatica va confrontata con la classifica
--  mostrata dall'app. L'obiettivo resta spostare il calcolo qui e far leggere
--  anche alla webapp questa vista, eliminando la duplicazione.
--
--  Sostituire <UUID-MODENA-MAGIC> con l'id della community.
-- ═══════════════════════════════════════════════════════════════════════════

create or replace view public.v_social_classifica as
with lega as (
  select l.id                                         as lega_id,
         l.name                                       as lega,
         l.format::text                               as formato,
         l.status::text                               as stato_lega,
         greatest(coalesce(l.presence_bonus_points, 0), 0) as presence_bonus_points,
         greatest(coalesce(l.presence_bonus_every, 2), 1)  as presence_bonus_every,
         greatest(coalesce(l.bonus_event_points, 0), 0)    as bonus_event_points,
         greatest(coalesce(l.best_of, 0), 0)               as best_of,
         l.placement_bonus_top8
  from public.leagues l
  where l.community_id = '<UUID-MODENA-MAGIC>'
    and coalesce(l.hide_standings, false) = false   -- lega che nasconde la classifica: non si pubblica
),

-- Tornei della lega: si escludono gli eliminati e il torneo finale, che non
-- contribuisce mai al totale.
tornei as (
  select t.id                                    as torneo_id,
         t.league_id                             as lega_id,
         coalesce(t.is_league_bonus, false)      as e_bonus,
         t.start_date
  from public.tournaments t
  join lega on lega.lega_id = t.league_id
  where (t.status is null or t.status::text in ('aperto', 'in_corso', 'chiuso'))
    and coalesce(t.kind::text, '') <> 'league_final'
    and coalesce(t.description, '') not like '%[LEAGUE_FINAL_BRACKET]%'
),

-- Una riga per iscrizione valida. La chiave replica toLeagueStandingKey:
-- l'utente registrato vince sul nome, il non registrato si unifica per nome
-- normalizzato. Chi non ha ne' l'uno ne' l'altro viene scartato.
righe as (
  select tor.lega_id,
         tor.torneo_id,
         tor.e_bonus,
         tor.start_date,
         case when tp.registered_user_id is not null
              then 'user:' || tp.registered_user_id::text
              else 'name:' || lower(btrim(tp.player_name))
         end                                              as chiave,
         nullif(btrim(tp.player_name), '')                as nome,
         case when tp.rank > 0 then tp.rank end           as posizione,
         greatest(coalesce(tp.points, 0), 0)              as punti
  from public.tournament_players tp
  join tornei tor on tor.torneo_id = tp.tournament_id
  where coalesce(tp.status::text, '') <> 'canceled'
    and (tp.registered_user_id is not null
         or btrim(coalesce(tp.player_name, '')) <> '')
),

-- Un giocatore puo' comparire piu' volte nello stesso torneo: si tiene il
-- piazzamento migliore e il punteggio piu' alto, come fa la webapp.
per_torneo as (
  select lega_id, chiave, torneo_id,
         min(posizione) as posizione,
         max(punti)     as punti
  from righe
  where not e_bonus
  group by lega_id, chiave, torneo_id
),

-- best_of tiene solo gli N risultati migliori per punteggio, non per data.
ordinati as (
  select pt.*,
         row_number() over (partition by pt.lega_id, pt.chiave
                            order by pt.punti desc, pt.torneo_id) as posto_valore
  from per_torneo pt
),

standard as (
  select o.lega_id,
         o.chiave,
         count(*)                                   as tornei_standard,
         sum(o.punti)                               as punti_tutti,
         sum(o.punti) filter (where lega.best_of = 0
                                 or o.posto_valore <= lega.best_of) as punti_contati,
         min(o.posizione)                           as miglior_piazzamento,
         -- Il bonus piazzamento vale su TUTTI i tornei standard, anche su
         -- quelli esclusi dal best_of.
         sum(case when o.posizione between 1 and 8
                  then coalesce((lega.placement_bonus_top8 ->> o.posizione::text)::int, 0)
                  else 0 end)                       as bonus_piazzamento
  from ordinati o
  join lega on lega.lega_id = o.lega_id
  group by o.lega_id, o.chiave
),

bonus as (
  select lega_id, chiave, count(distinct torneo_id) as tornei_bonus
  from righe
  where e_bonus
  group by lega_id, chiave
),

-- Chi ha giocato solo tornei bonus compare comunque in classifica.
giocatori as (
  select distinct lega_id, chiave from righe
),

-- La webapp prende il nome dalla prima riga che incontra, in ordine non
-- deterministico. Qui si sceglie il piu' recente: stesso risultato nei casi
-- normali, e stabile quando un utente ha cambiato nome fra un torneo e l'altro.
nomi as (
  select distinct on (lega_id, chiave) lega_id, chiave, nome
  from righe
  where nome is not null
  order by lega_id, chiave, start_date desc nulls last, torneo_id
)

select
  lega.formato                                          as formato,
  lega.lega                                             as lega,
  lega.lega_id                                          as lega_id,
  lega.stato_lega                                       as stato_lega,
  coalesce(n.nome, 'Sconosciuto')                       as giocatore,
  coalesce(s.punti_contati, 0)
    + coalesce(s.bonus_piazzamento, 0)
    + coalesce(s.tornei_standard, 0)                                        -- +1 per torneo giocato
    + floor(coalesce(s.tornei_standard, 0) / lega.presence_bonus_every)
      * lega.presence_bonus_points                                          -- bonus presenza periodica
    + coalesce(b.tornei_bonus, 0) * lega.bonus_event_points                 -- eventi bonus
                                                        as punti,
  coalesce(s.tornei_standard, 0)                        as tappe,
  row_number() over (
    partition by lega.lega_id
    order by
      coalesce(s.punti_contati, 0)
        + coalesce(s.bonus_piazzamento, 0)
        + coalesce(s.tornei_standard, 0)
        + floor(coalesce(s.tornei_standard, 0) / lega.presence_bonus_every)
          * lega.presence_bonus_points
        + coalesce(b.tornei_bonus, 0) * lega.bonus_event_points   desc,
      coalesce(s.punti_tutti, 0)                                  desc,
      coalesce(s.miglior_piazzamento, 2147483647)                 asc,
      coalesce(s.tornei_standard, 0)                              desc,
      coalesce(n.nome, 'Sconosciuto')                             asc
  )                                                     as posizione
from giocatori g
join lega        on lega.lega_id = g.lega_id
left join standard s on s.lega_id = g.lega_id and s.chiave = g.chiave
left join bonus    b on b.lega_id = g.lega_id and b.chiave = g.chiave
left join nomi     n on n.lega_id = g.lega_id and n.chiave = g.chiave;

grant select on public.v_social_classifica to anon;
