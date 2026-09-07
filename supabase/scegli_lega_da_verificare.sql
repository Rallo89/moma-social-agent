-- Quale lega conviene verificare per prima: quella che attiva piu' meccanismi.
-- Una lega con tutti i bonus a zero verifica quasi niente.
--
-- Sostituire <UUID-MODENA-MAGIC>.

select l.id,
       l.name                                        as lega,
       l.format::text                                as formato,
       l.status::text                                as stato,
       l.best_of,
       l.presence_bonus_points || ' ogni ' || l.presence_bonus_every as bonus_presenza,
       l.bonus_event_points                          as punti_evento_bonus,
       l.placement_bonus_top8,
       l.hide_standings,
       (select count(*) from public.tournaments t
         where t.league_id = l.id)                   as tornei,
       (select count(*) from public.tournaments t
         where t.league_id = l.id and t.is_league_bonus) as tornei_bonus,
       -- Quanti meccanismi diversi mette alla prova questa lega
       (l.best_of > 0)::int
         + (l.placement_bonus_top8 is not null)::int
         + (l.bonus_event_points > 0)::int
         + (l.presence_bonus_points > 0)::int        as meccanismi_attivi
from public.leagues l
where l.community_id = '<UUID-MODENA-MAGIC>'
order by meccanismi_attivi desc, tornei desc;
