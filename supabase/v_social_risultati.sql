-- ═══════════════════════════════════════════════════════════════════════════
--  v_social_risultati — risultati di tappa per l'agente social
--
--  Espone vinte/perse/pari separate (il record lo compone l'agente, cosi' i
--  pareggi non si perdono) e lega_id, che serve a scegliere QUALE classifica
--  aggiornare quando piu' leghe condividono lo stesso formato — di norma una
--  per stagione.
--
--  Sostituire <UUID-MODENA-MAGIC>.
-- ═══════════════════════════════════════════════════════════════════════════

create or replace view public.v_social_risultati as
select t.start_date                                    as data,
       t.format::text                                  as formato,
       t.name                                          as torneo,
       t.league_id                                     as lega_id,
       tp.rank                                         as posizione,
       tp.player_name                                  as giocatore,
       tp.points                                       as punti,
       tp.win                                          as vinte,
       tp.lost                                         as perse,
       tp.draw                                         as pari,
       tp.manual_archetype                             as mazzo,
       count(*) over (partition by tp.tournament_id)   as iscritti
from public.tournament_players tp
join public.tournaments t on t.id = tp.tournament_id
where t.community_id = '<UUID-MODENA-MAGIC>'
  and tp.rank is not null;

grant select on public.v_social_risultati to anon;
