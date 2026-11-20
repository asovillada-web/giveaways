const HOUR = 3_600_000
export const PAGE_SIZE = 12

const GROUPS = {
  NA: 'BM CA GL MX PM US',
  EU: 'AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE',
  EUROPE: 'AL AD AT BY BE BA BG HR CY CZ DK EE FI FR DE GR HU IS IE IT LV LI LT LU MT MD MC ME NL MK NO PL PT RO RU SM RS SK SI ES SE CH TR UA GB VA',
  LATAM: 'AR BO BR CL CO CR CU DO EC SV GF GT HT HN MX NI PA PY PE PR UY VE',
  APAC: 'AU BD BN BT KH CN FJ HK IN ID JP KI KR LA MO MY MV MH FM MN MM NR NP NZ PK PW PG PH WS SG SB LK TW TH TL TO TV VU VN',
}
const REGION_LABELS = { NA: 'North America', EU: 'EU', EUROPE: 'Europe', LATAM: 'Latin America', APAC: 'Asia-Pacific', GB: 'UK' }

export function matchesCountry(item, country) {
  if (item.is_worldwide) return true
  if (!country) return false
  const matches = code => code === country || GROUPS[code]?.split(' ').includes(country)
  if (item.region_exclusions.some(matches)) return false
  return item.region_codes.some(matches) || (item.region_codes.length === 0 && item.region_exclusions.length > 0)
}

export function regionLabel(item) {
  if (!item.region_codes.length && !item.region_exclusions.length) {
    return item.region_scope === 'Unspecified' ? 'Region unspecified' : item.region_scope
  }
  const label = code => REGION_LABELS[code] || code
  const included = item.region_codes.map(label).join(' / ') || 'Worldwide'
  const excluded = item.region_exclusions.map(label).join(' / ')
  return excluded ? included + ' except ' + excluded : included
}

export function timeLeft(item, now) {
  const remaining = Date.parse(item.expires_at) - now
  if (Number.isNaN(remaining)) return { label: 'No deadline listed', urgent: false }
  if (remaining <= 0) return { label: 'Ended', urgent: false }
  const hours = Math.ceil(remaining / HOUR)
  const label = remaining < HOUR ? 'Under 1h left' : hours < 48 ? hours + 'h left' : Math.ceil(hours / 24) + 'd left'
  return { label, urgent: remaining <= 48 * HOUR }
}

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

export function addedAt(value, now) {
  const minutes = Math.max(0, Math.floor((now - Date.parse(value)) / 60_000))
  if (minutes < 1) return 'Just added'
  if (minutes < 60) return 'Added ' + relative.format(-minutes, 'minute')
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return 'Added ' + relative.format(-hours, 'hour')
  return 'Added ' + relative.format(-Math.floor(hours / 24), 'day')
}

export function safeLink(value) {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined
  } catch {
    return undefined
  }
}

const normalize = value => value.toLocaleLowerCase('en').normalize('NFKD').replace(/\p{Diacritic}/gu, '')

export function matchesSearch(item, query) {
  if (!query.trim()) return true
  const searchable = normalize([item.title, item.prize_summary, item.platform, item.creator_or_host, regionLabel(item)].join(' '))
  return normalize(query.trim()).split(/\s+/).every(word => searchable.includes(word))
}

export function matchesPlatform(platform, filter) {
  if (!filter) return true
  if (filter === 'gleam') return platform === 'Gleam'
  if (filter === 'storefront') return ['Steam', 'Epic Games'].includes(platform)
  return !['Gleam', 'Steam', 'Epic Games'].includes(platform)
}

export function activeRows(items, now) {
  return items.filter(item => Date.parse(item.visible_until) > now)
}

export function orderRows(items, sort, now) {
  const newest = (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || a.id.localeCompare(b.id)
  const score = item => item.priority_score + (timeLeft(item, now).urgent && !item.ending_soon ? 10 : 0)
  const ranked = items.map(item => ({
    item, points: score(item), deadline: item.expires_at ? Date.parse(item.expires_at) : Infinity,
  }))
  ranked.sort((a, b) => {
    if (sort === 'ending') {
      return (a.deadline - b.deadline) || newest(a.item, b.item)
    }
    if (sort === 'newest') return newest(a.item, b.item)
    if (sort === 'free') {
      const free = Number(b.item.category === '100% Freebie') - Number(a.item.category === '100% Freebie')
      if (free) return free
    }
    return b.points - a.points || newest(a.item, b.item)
  })
  return ranked.map(({ item }) => item)
}

const root = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_ANON_KEY
export const configured = Boolean(root && key)

export async function loadGiveaways(signal) {
  const rows = new Map()
  const headers = { apikey: key }
  if (!key.startsWith('sb_publishable_')) headers.Authorization = `Bearer ${key}`
  const pageSize = 200
  // Immutable sort columns keep pages deterministic while scores and expiry change.
  for (let offset = 0; ; ) {
    const url = new URL('/rest/v1/active_giveaways', root)
    url.search = new URLSearchParams({ order: 'created_at.desc,id.asc', offset, limit: pageSize })
    const response = await fetch(url, { signal, headers })
    if (!response.ok) throw new Error(`Feed request failed (${response.status})`)
    const page = await response.json()
    for (const item of page) rows.set(item.id, item)
    if (page.length < pageSize) return [...rows.values()]
    offset += page.length
  }
}
