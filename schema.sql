begin;

create table if not exists public.giveaways (
    id uuid primary key default gen_random_uuid(),
    canonical_url text not null unique check (canonical_url ~ '^https?://'),
    original_url text not null check (original_url ~ '^https?://'),
    title text not null,
    prize_summary text not null,
    category text not null check (category in ('100% Freebie', 'Hardware & Devices', 'Peripherals & Gear', 'Games & Gift Cards')),
    platform text not null,
    source_type text not null check (source_type in ('Creator', 'Community', 'Official')),
    creator_or_host text not null,
    language text not null default 'und',
    country_hint text,
    source_url text,
    region_scope text not null,
    is_worldwide boolean not null default true,
    region_codes text[] not null default '{}',
    region_exclusions text[] not null default '{}',
    priority_score integer not null default 0 check (priority_score between 0 and 100),
    expires_at timestamptz,
    created_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    is_expired boolean not null default false,
    ending_soon boolean not null default false,
    source_rank smallint not null default 0,
    category_confidence smallint not null default 0,
    region_confidence smallint not null default 0,
    expires_confidence smallint not null default 0,
    alert_sent_at timestamptz,
    alert_lease_until timestamptz,
    alert_token uuid
);

alter table public.giveaways
    add column if not exists freebie_kind text check (freebie_kind in (
        'Full game claim', 'Game key', 'DLC & loot', 'Software & assets', 'Other freebie'
    )),
    add column if not exists verified_until timestamptz,
    add column if not exists previous_canonical_urls text[] not null default '{}';

create index if not exists giveaways_active_priority_idx
    on public.giveaways (is_expired, priority_score desc, created_at desc);
create index if not exists giveaways_category_idx on public.giveaways (category);
create index if not exists giveaways_last_seen_idx on public.giveaways (last_seen_at);
create index if not exists giveaways_previous_urls_idx on public.giveaways using gin (previous_canonical_urls);

alter table public.giveaways enable row level security;
revoke all on table public.giveaways from public, anon, authenticated, service_role;
grant select, insert, update, delete on table public.giveaways to service_role;
grant select (
    id, canonical_url, original_url, title, prize_summary, category, platform, source_type, creator_or_host,
    language, country_hint, source_url, region_scope, is_worldwide, region_codes, region_exclusions,
    priority_score, expires_at, created_at, last_seen_at, is_expired, ending_soon, freebie_kind, verified_until,
    previous_canonical_urls
) on public.giveaways to anon, authenticated;
drop policy if exists "Public read" on public.giveaways;
create policy "Public read" on public.giveaways for select to anon, authenticated using (true);

-- Calculate these fields from the merged evidence, covering elapsed time during missed runs.
create or replace function public.giveaway_score(category text, worldwide boolean, urgent boolean)
returns integer language sql immutable parallel safe set search_path = '' as $$
    select 40 * (category = '100% Freebie')::integer
         + 30 * worldwide::integer
         + 20 * (category = 'Hardware & Devices')::integer
         + 10 * urgent::integer;
$$;

create or replace view public.active_giveaways
with (security_invoker = true) as
select id, canonical_url, original_url, title, prize_summary, category, platform, source_type, creator_or_host,
       language, country_hint, source_url, region_scope, is_worldwide, region_codes, region_exclusions,
       public.giveaway_score(category, is_worldwide,
           coalesce(expires_at <= now() + interval '48 hours', false)) as priority_score,
       expires_at, created_at, coalesce(expires_at <= now() + interval '48 hours', false) as ending_soon,
       least(last_seen_at + interval '28 days',
             coalesce(expires_at, last_seen_at + interval '7 days'), verified_until) as visible_until,
       freebie_kind, previous_canonical_urls
from public.giveaways g
where not is_expired
  and last_seen_at > now() - interval '28 days'
  and least(coalesce(expires_at, last_seen_at + interval '7 days'), verified_until) > now()
  and not exists (
      select 1 from public.giveaways direct
      where direct.previous_canonical_urls @> array[g.canonical_url]
  );
revoke all on table public.active_giveaways from public, anon, authenticated, service_role;
grant select on public.active_giveaways to anon, authenticated, service_role;

-- One observation per call. ON CONFLICT locks the existing row, including for concurrent writers.
create or replace function public.record_giveaways(items jsonb)
returns integer language plpgsql set search_path = '' as $$
declare
    incoming public.giveaways;
    item jsonb;
    touched integer := 0;
    first_seen timestamptz;
    prior_alert_sent timestamptz;
begin
    for item in select value from jsonb_array_elements(items)
    loop
        incoming := jsonb_populate_record(null::public.giveaways, item);
        select min(created_at), min(alert_sent_at) into first_seen, prior_alert_sent
        from public.giveaways
        where canonical_url = any(incoming.previous_canonical_urls);
        insert into public.giveaways as g (
            canonical_url, original_url, title, prize_summary, category, platform, source_type,
            creator_or_host, language, country_hint, source_url, region_scope, is_worldwide,
            region_codes, region_exclusions, expires_at, source_rank, category_confidence,
            region_confidence, expires_confidence, priority_score, is_expired, ending_soon, freebie_kind, verified_until,
            previous_canonical_urls, created_at, alert_sent_at
        ) values (
            incoming.canonical_url, incoming.original_url, incoming.title, incoming.prize_summary,
            incoming.category, incoming.platform, incoming.source_type, incoming.creator_or_host,
            incoming.language, incoming.country_hint, incoming.source_url, incoming.region_scope,
            incoming.is_worldwide, incoming.region_codes, incoming.region_exclusions,
            incoming.expires_at, incoming.source_rank, incoming.category_confidence,
            incoming.region_confidence, incoming.expires_confidence, incoming.priority_score,
            incoming.is_expired, incoming.ending_soon, incoming.freebie_kind, incoming.verified_until,
            coalesce(incoming.previous_canonical_urls, '{}'), coalesce(first_seen, now()), prior_alert_sent
        )
        on conflict (canonical_url) do update set
            last_seen_at = now(),
            created_at = least(g.created_at, excluded.created_at),
            alert_sent_at = coalesce(g.alert_sent_at, excluded.alert_sent_at),
            previous_canonical_urls = array(
                select distinct unnest(g.previous_canonical_urls || excluded.previous_canonical_urls)
            ),
            original_url = case when excluded.source_rank >= g.source_rank then excluded.original_url else g.original_url end,
            title = case when excluded.source_rank >= g.source_rank then excluded.title else g.title end,
            prize_summary = case when excluded.source_rank >= g.source_rank then excluded.prize_summary else g.prize_summary end,
            platform = case when excluded.platform <> 'Other'
                and (excluded.source_rank >= g.source_rank or g.platform = 'Other') then excluded.platform else g.platform end,
            source_type = case when excluded.source_rank >= g.source_rank then excluded.source_type else g.source_type end,
            creator_or_host = case when excluded.source_rank >= g.source_rank then excluded.creator_or_host else g.creator_or_host end,
            language = case when excluded.language <> 'und'
                and (excluded.source_rank >= g.source_rank or g.language = 'und') then excluded.language else g.language end,
            country_hint = case when excluded.source_rank >= g.source_rank then excluded.country_hint else g.country_hint end,
            source_url = case when excluded.source_rank >= g.source_rank then excluded.source_url else g.source_url end,
            source_rank = greatest(excluded.source_rank, g.source_rank),
            category = case when excluded.category_confidence > g.category_confidence
                or (excluded.category_confidence = g.category_confidence and excluded.source_rank >= g.source_rank)
                then excluded.category else g.category end,
            freebie_kind = case
                when excluded.category_confidence > g.category_confidence
                  or (excluded.category_confidence = g.category_confidence and excluded.source_rank >= g.source_rank)
                then case when excluded.category = '100% Freebie'
                    then coalesce(nullif(excluded.freebie_kind, 'Other freebie'), g.freebie_kind, excluded.freebie_kind)
                    else null end
                when g.category = '100% Freebie' and excluded.category = g.category
                then coalesce(nullif(g.freebie_kind, 'Other freebie'), excluded.freebie_kind, g.freebie_kind)
                else g.freebie_kind end,
            category_confidence = greatest(excluded.category_confidence, g.category_confidence),
            region_scope = case when excluded.region_confidence > g.region_confidence
                or (excluded.region_confidence = g.region_confidence and excluded.source_rank >= g.source_rank)
                then excluded.region_scope else g.region_scope end,
            is_worldwide = case when excluded.region_confidence > g.region_confidence
                or (excluded.region_confidence = g.region_confidence and excluded.source_rank >= g.source_rank)
                then excluded.is_worldwide else g.is_worldwide end,
            region_codes = case when excluded.region_confidence > g.region_confidence
                or (excluded.region_confidence = g.region_confidence and excluded.source_rank >= g.source_rank)
                then excluded.region_codes else g.region_codes end,
            region_exclusions = case when excluded.region_confidence > g.region_confidence
                or (excluded.region_confidence = g.region_confidence and excluded.source_rank >= g.source_rank)
                then excluded.region_exclusions else g.region_exclusions end,
            region_confidence = greatest(excluded.region_confidence, g.region_confidence),
            expires_at = case when excluded.expires_at is not null and excluded.expires_confidence >= g.expires_confidence
                then excluded.expires_at
                when excluded.verified_until is not null and excluded.source_rank >= g.source_rank and g.expires_at <= now()
                    then null else g.expires_at end,
            verified_until = case
                when excluded.expires_at is not null and excluded.expires_confidence >= g.expires_confidence
                    then null
                when excluded.verified_until is not null and excluded.source_rank >= g.source_rank and g.expires_at <= now()
                    then excluded.verified_until
                when g.expires_at is not null then g.verified_until
                else greatest(excluded.verified_until, g.verified_until) end,
            expires_confidence = case
                when excluded.verified_until is not null and excluded.source_rank >= g.source_rank and g.expires_at <= now()
                    then excluded.expires_confidence
                else greatest(excluded.expires_confidence, g.expires_confidence) end;
        touched := touched + 1;
    end loop;
    return touched;
end;
$$;

create or replace function public.refresh_giveaways()
returns void language sql set search_path = '' as $$
    delete from public.giveaways where last_seen_at <= now() - interval '28 days';
    with statuses as (
        select id,
               least(coalesce(expires_at, last_seen_at + interval '7 days'), verified_until) <= now() as expired,
               coalesce(expires_at > now() and expires_at <= now() + interval '48 hours', false) as urgent,
               category, is_worldwide
        from public.giveaways
    ), scores as (
        select id, expired, urgent, public.giveaway_score(category, is_worldwide, urgent) as points
        from statuses
    )
    update public.giveaways as g
    set is_expired = s.expired, ending_soon = s.urgent, priority_score = s.points
    from scores as s
    where g.id = s.id and (g.is_expired, g.ending_soon, g.priority_score)
        is distinct from (s.expired, s.urgent, s.points);
$$;

create or replace function public.claim_giveaway_alerts()
returns table (id uuid, title text, original_url text, category text, region_scope text, alert_token uuid)
language sql set search_path = '' as $$
    with candidates as (
        select g.id
        from public.giveaways g
        where not g.is_expired and coalesce(g.expires_at, 'infinity') > now()
          and g.alert_sent_at is null and (g.alert_lease_until is null or g.alert_lease_until <= now())
          and g.created_at > now() - interval '24 hours'
          and (g.category = '100% Freebie' or (g.category = 'Hardware & Devices' and g.region_scope = 'Worldwide'))
          and not exists (
              select 1 from public.giveaways direct
              where direct.previous_canonical_urls @> array[g.canonical_url]
          )
        order by g.priority_score desc, g.created_at desc
        limit 12 for update skip locked
    )
    update public.giveaways as g
    set alert_lease_until = now() + interval '20 minutes', alert_token = gen_random_uuid()
    from candidates c where c.id = g.id
    returning g.id, g.title, g.original_url, g.category, g.region_scope, g.alert_token;
$$;

create or replace function public.finish_giveaway_alert(giveaway_id uuid, lease_token uuid)
returns void language sql set search_path = '' as $$
    update public.giveaways
    set alert_sent_at = now(), alert_lease_until = null, alert_token = null
    where id = giveaway_id and alert_token = lease_token;
$$;

revoke execute on function public.record_giveaways(jsonb), public.refresh_giveaways(),
    public.claim_giveaway_alerts(), public.finish_giveaway_alert(uuid, uuid)
    from public, anon, authenticated;
grant execute on function public.record_giveaways(jsonb), public.refresh_giveaways(),
    public.claim_giveaway_alerts(), public.finish_giveaway_alert(uuid, uuid) to service_role;

notify pgrst, 'reload schema';
commit;
