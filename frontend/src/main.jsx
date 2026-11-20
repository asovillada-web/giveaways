import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Archive, ArrowDownWideNarrow, ArrowUpRight, Check, ChevronDown, Clock3, Cpu, Gamepad2,
  Gift, Globe2, Headphones, Radar, RotateCcw, Search, Sparkles, Star, X,
} from 'lucide-react'
import '@fontsource-variable/inter'
import '@fontsource-variable/space-grotesk'
import './styles.css'
import { countries } from './countries.js'
import {
  activeRows, addedAt, configured, FREEBIE_KINDS, freebieKind, GAME_FREEBIES, isFeatured, loadGiveaways,
  matchesCountry, matchesFreebieType, matchesPlatform, matchesSearch, orderRows, PAGE_SIZE, PLATFORMS, regionLabel, safeLink, timeLeft,
} from './catalog.js'

const categories = [
  ['100% Freebie', 'free', Gift],
  ['Hardware & Devices', 'hardware', Cpu],
  ['Peripherals & Gear', 'gear', Headphones],
  ['Games & Gift Cards', 'games', Gamepad2],
]
const sorts = [
  ['recommended', 'Recommended', Sparkles], ['free', '100% Freebies First', Gift],
  ['newest', 'Newest', ArrowDownWideNarrow], ['ending', 'Ending Soonest', Clock3],
]
const ENTERED_KEY = 'drop-radar:entered:v1'
const COUNTRY_KEY = 'drop-radar:country:v1'

function savedEntered(raw) {
  try {
    const values = JSON.parse(raw)
    return new Set(Array.isArray(values) ? values.filter(value => typeof value === 'string') : [])
  } catch {
    return new Set()
  }
}

function useStored(key, initial, read, write) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw === null ? initial : read(raw)
    } catch {
      return initial
    }
  })
  useEffect(() => {
    function changed(event) {
      if (event.key === key) setValue(event.newValue === null ? initial : read(event.newValue))
    }
    window.addEventListener('storage', changed)
    return () => window.removeEventListener('storage', changed)
  }, [key, initial, read])
  return [value, next => {
    setValue(next)
    try {
      localStorage.setItem(key, write(next))
      return true
    } catch {
      return false
    }
  }]
}

const emptyEntered = new Set()
const encodeEntered = values => JSON.stringify([...values])
const identity = value => value
const isEntered = (item, entered) => entered.has(item.canonical_url)
  || item.previous_canonical_urls?.some(url => entered.has(url)) || false

function SelectField({ label, value, onChange, children, className = '' }) {
  return <label className={`select-field ${className}`}>
    <span className="sr-only">{label}</span>
    <select value={value} onChange={event => onChange(event.target.value)}>{children}</select>
    <ChevronDown size={15} aria-hidden="true" />
  </label>
}

function Card({ item, now, entered, mark }) {
  const [, tone, Icon] = categories.find(([label]) => label === item.category) || categories[3]
  const remaining = timeLeft(item, now)
  const destination = safeLink(item.original_url)
  const origin = safeLink(item.source_url)
  const kind = freebieKind(item)
  return <article className={`drop-card tone-${tone}`}>
    <div className="flex flex-wrap items-center gap-2 card-badges">
      <span className="category-badge"><Icon size={14} aria-hidden="true" />{item.category}</span>
      <span className={`region-badge ${item.region_scope === 'Worldwide' ? 'worldwide' : ''}`}>
        <Globe2 size={13} aria-hidden="true" />{regionLabel(item)}
      </span>
      {isFeatured(item) && <span className="featured-badge"><Star size={13} aria-hidden="true" />Featured</span>}
    </div>
    <h3>{item.title}</h3>
    <p className="summary">{item.prize_summary}</p>
    <div className="byline">
      <strong>{item.platform}</strong><span className="byline-divider" aria-hidden="true" />
      {origin ? <a href={origin} target="_blank" rel="noreferrer">{item.creator_or_host}</a> : <span>{item.creator_or_host}</span>}
      {kind && kind !== 'Other freebie' && <span className="kind-label">{kind}</span>}
    </div>
    <div className="card-time">
      <time dateTime={item.created_at}>{addedAt(item.created_at, now)}</time>
      <span className={remaining.urgent ? 'urgent' : ''}>
        <Clock3 size={14} aria-hidden="true" />{remaining.label}
      </span>
    </div>
    <div className="card-actions">
      {destination ? <a className="open-drop" href={destination} target="_blank" rel="noreferrer">
        Open Giveaway <ArrowUpRight size={16} aria-hidden="true" />
      </a> : <span className="open-drop unavailable">Link unavailable</span>}
      <button className="mark-drop" type="button" onClick={() => mark(item, entered)}
        aria-label={entered ? `Restore ${item.title}` : `Mark as Entered: ${item.title}`}
        title={entered ? 'Restore to active feed' : 'Mark as Entered and hide from active feed'}>
        {entered ? <RotateCcw size={17} aria-hidden="true" /> : <Check size={18} aria-hidden="true" />}
        <span>{entered ? 'Restore' : 'Mark as Entered'}</span>
      </button>
    </div>
  </article>
}

function App() {
  const [items, setItems] = useState([])
  const [status, setStatus] = useState(configured ? 'loading' : 'setup')
  const [request, setRequest] = useState(0)
  const [now, setNow] = useState(Date.now)
  const [sort, setSort] = useState('recommended')
  const [category, setCategory] = useState('')
  const [kind, setKind] = useState('')
  const [platform, setPlatform] = useState('')
  const [query, setQuery] = useState('')
  const [eligible, setEligible] = useState(false)
  const [worldwide, setWorldwide] = useState(false)
  const [featured, setFeatured] = useState(false)
  const [view, setView] = useState('feed')
  const [limit, setLimit] = useState(PAGE_SIZE)
  const [notice, setNotice] = useState('')
  const [entered, setEntered] = useStored(ENTERED_KEY, emptyEntered, savedEntered, encodeEntered)
  const [country, setCountry] = useStored(COUNTRY_KEY, '', identity, identity)

  useEffect(() => {
    if (!configured) return
    let controller
    function refresh() {
      controller?.abort()
      controller = new AbortController()
      const signal = controller.signal
      loadGiveaways(signal).then(rows => {
        if (!signal.aborted) {
          setItems(rows)
          setStatus('ready')
        }
      }).catch(() => {
        if (!signal.aborted) setStatus('error')
      })
    }
    refresh()
    const timer = setInterval(refresh, 5 * 60_000)
    return () => {
      controller?.abort()
      clearInterval(timer)
    }
  }, [request])

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(timer)
  }, [])

  const active = useMemo(() => activeRows(items, now), [items, now])
  const enteredCount = active.filter(item => isEntered(item, entered)).length
  const results = useMemo(() => orderRows(active.filter(item =>
    isEntered(item, entered) === (view === 'entered')
    && (!category || item.category === category)
    && matchesFreebieType(item, kind)
    && matchesPlatform(item.platform, platform)
    && (!eligible || matchesCountry(item, country))
    && (!worldwide || item.region_scope === 'Worldwide')
    && (!featured || isFeatured(item))
    && matchesSearch(item, query)
  ), sort, now), [active, category, country, eligible, entered, featured, kind, now, platform, query, sort, view, worldwide])

  function change(setter, value) {
    setter(value)
    setLimit(PAGE_SIZE)
  }

  function mark(item, isEntered) {
    const selected = new Set(entered)
    if (isEntered) {
      selected.delete(item.canonical_url)
      for (const url of item.previous_canonical_urls || []) selected.delete(url)
    } else selected.add(item.canonical_url)
    const saved = setEntered(selected)
    document.getElementById("results-title")?.focus({ preventScroll: true })
    setNotice((isEntered ? 'Restored to the active feed.' : 'Marked as entered.') +
      (saved ? '' : ' This browser could not save the change.'))
  }

  function clearFilters() {
    setCategory('')
    setKind('')
    setPlatform('')
    setQuery('')
    setEligible(false)
    setWorldwide(false)
    setFeatured(false)
    setLimit(PAGE_SIZE)
  }

  function selectCategory(value) {
    change(setCategory, value)
    if (value !== '100% Freebie') setKind('')
    else setFeatured(false)
  }

  function selectKind(value) {
    change(setKind, value)
    if (value) {
      setCategory('100% Freebie')
      setFeatured(false)
    }
  }

  const steamGames = category === '100% Freebie' && platform === 'steam' && kind === GAME_FREEBIES
  function toggleSteamGames() {
    setFeatured(false)
    setPlatform(steamGames ? '' : 'steam')
    setCategory(steamGames ? '' : '100% Freebie')
    change(setKind, steamGames ? '' : GAME_FREEBIES)
  }
  function toggleFeatured() {
    if (category === '100% Freebie') selectCategory('')
    if (platform === 'steam' || platform === 'mobile' || platform.startsWith('epic')) setPlatform('')
    change(setFeatured, !featured)
  }
  const hasFilters = Boolean(category || kind || platform || query || eligible || worldwide || featured)

  function reload() {
    setStatus('loading')
    setRequest(number => number + 1)
  }

  return <>
    <a className="skip-link" href="#results">Skip to giveaways</a>
    <header className="site-header">
      <div className="shell header-inner">
        <button className="brand" onClick={() => change(setView, 'feed')} type="button">
          <span className="brand-icon"><Radar size={23} strokeWidth={1.9} aria-hidden="true" /></span>
          Drop Radar
        </button>
        <nav className="view-switch" aria-label="Giveaway views">
          <button type="button" className={view === 'feed' ? 'selected' : ''}
            aria-pressed={view === 'feed'} onClick={() => change(setView, 'feed')}>
            <Radar size={17} aria-hidden="true" /> Live feed
          </button>
          <button type="button" className={view === 'entered' ? 'selected' : ''}
            aria-pressed={view === 'entered'} onClick={() => change(setView, 'entered')}>
            <Archive size={16} aria-hidden="true" /> Entered {enteredCount > 0 && <span className="nav-count">{enteredCount}</span>}
          </button>
        </nav>
      </div>
    </header>

    <main className="shell">
      <section className="hero" aria-labelledby="page-title">
        <div className="radar-art" aria-hidden="true"><span /><span /><span /><i /><i /><i /></div>
        <div className="hero-copy">
          <h1 id="page-title">Find your next drop.</h1>
          <p>Track tech giveaways, hardware draws, and free-to-keep games from around the world.</p>
        </div>
        {status !== 'setup' && <dl className="stats">
          <div><dt>Active drops</dt><dd>{status !== 'ready' && !items.length ? '–' : active.length}</dd></div>
          <div><dt>Freebies</dt><dd>{status !== 'ready' && !items.length ? '–' : active.filter(item => item.category === '100% Freebie').length}</dd></div>
          <div><dt>Ending in 48h</dt><dd>{status !== 'ready' && !items.length ? '–' : active.filter(item => timeLeft(item, now).urgent).length}</dd></div>
        </dl>}
      </section>

      <section className="filters" aria-label="Filter giveaways">
        <div className="filter-row">
          <div className="search-field">
            <Search size={19} aria-hidden="true" />
            <label className="sr-only" htmlFor="giveaway-search">Search giveaways</label>
            <input id="giveaway-search" type="search" value={query} placeholder="Search giveaways" onChange={event => change(setQuery, event.target.value)} />
            {query && <button type="button" onClick={() => change(setQuery, '')} aria-label="Clear search"><X size={16} aria-hidden="true" /></button>}
          </div>
          <SelectField label="Filter by platform" value={platform} onChange={value => {
            if (value === 'mobile' || value.startsWith('epic')) setFeatured(false)
            change(setPlatform, value)
          }}>
            <option value="">All platforms</option>
            <option value="mobile">Mobile games</option>
            {Object.entries(PLATFORMS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            <option value="storefront">Steam / Epic</option>
            <option value="other">Other</option>
          </SelectField>
          <label className="world-toggle">
            <Globe2 size={17} aria-hidden="true" />
            <input type="checkbox" checked={eligible} onChange={event => change(setEligible, event.target.checked)} />
            <span className="switch-track" aria-hidden="true" />
            <span>Worldwide / Eligible for Me Only</span>
          </label>
        </div>
        {eligible && <div className="eligibility-options">
          <SelectField label="My country" value={country} onChange={value => change(setCountry, value)}>
            <option value="">Choose your country</option>
            {countries.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
          </SelectField>
          <span>Includes listings with no stated region. Check the host’s eligibility rules before entering.</span>
        </div>}
        <div className="category-filters">
          <div className="categories" role="group" aria-label="Categories">
            <button type="button" aria-pressed={!category} onClick={() => selectCategory('')}>All categories</button>
            {categories.map(([label, tone, Icon]) =>
              <button type="button" key={label} className={`tone-${tone}`} aria-pressed={category === label}
                onClick={() => selectCategory(category === label ? '' : label)}>
                <Icon size={15} aria-hidden="true" />{label}
              </button>)}
            <button type="button" aria-pressed={steamGames} onClick={toggleSteamGames}>
              <Gamepad2 size={15} aria-hidden="true" />Steam games
            </button>
            <button type="button" aria-pressed={worldwide} onClick={() => change(setWorldwide, !worldwide)}>
              <Globe2 size={15} aria-hidden="true" />Worldwide only
            </button>
            <button type="button" className="featured-filter" aria-pressed={featured} onClick={toggleFeatured}>
              <Star size={15} aria-hidden="true" />Featured giveaways
            </button>
          </div>
          <SelectField label="Filter by freebie type" className="kind-filter" value={kind} onChange={selectKind}>
            <option value="">All freebie types</option>
            <option value={GAME_FREEBIES}>{GAME_FREEBIES}</option>
            {FREEBIE_KINDS.map(label => <option key={label} value={label}>{label}</option>)}
          </SelectField>
        </div>
      </section>

      <section className="results" id="results" aria-labelledby="results-title" aria-busy={status === 'loading'}>
        <div className="results-heading">
          <h2 id="results-title" tabIndex={-1}>{view === 'entered' ? 'Entered giveaways' : 'Active giveaways'}</h2>
          {status === 'ready' && <span className="result-count" aria-live="polite">{results.length} {results.length === 1 ? 'result' : 'results'}</span>}
        </div>
        <div className="sort-controls" role="group" aria-label="Sort giveaways">
          {sorts.map(([value, title, Icon]) => <button type="button" key={value} aria-pressed={sort === value}
            onClick={() => change(setSort, value)}>
            <Icon size={15} aria-hidden="true" />{title}
          </button>)}
        </div>
        {status === 'setup' && <div className="empty"><Radar size={26} aria-hidden="true" /><h3>Connect Supabase to load the feed</h3><p>Set the public frontend environment variables and run the ingestion workflow.</p></div>}
        {status === 'loading' && !items.length && <div className="empty" role="status"><Radar size={26} aria-hidden="true" /><h3>Loading giveaways</h3></div>}
        {status === 'error' && <div className="empty" role="status">
          <Radar size={26} aria-hidden="true" /><h3>The feed could not refresh</h3>
          <p>{items.length ? 'Showing the most recent successful load.' : 'Check the connection and try again.'}</p>
          <button type="button" className="secondary" onClick={reload}>Try again</button>
        </div>}
        {status === 'ready' && !results.length && <div className="empty">
          <Search size={25} aria-hidden="true" />
          <h3>{hasFilters ? 'No giveaways match these filters' : view === 'entered' ? 'No active entered giveaways' : 'No active giveaways yet'}</h3>
          {hasFilters
            ? <button type="button" className="secondary" onClick={clearFilters}>Clear filters</button>
            : <p>{view === 'entered' ? 'Use Mark as Entered on a card to move it here.' : 'New listings appear after the next successful refresh.'}</p>}
          {view === 'feed' && platform === 'steam' && <a className="source-link" href="https://steamdb.info/upcoming/free/" target="_blank" rel="noreferrer">Browse SteamDB free promotions</a>}
        </div>}
        {results.length > 0 && <div className="card-grid">
          {results.slice(0, limit).map(item => <Card key={item.id} item={item} now={now} entered={view === 'entered'} mark={mark} />)}
        </div>}
        {results.length > limit && <div className="more"><button type="button" className="secondary" onClick={() => setLimit(value => value + PAGE_SIZE)}>Show more giveaways</button></div>}
        <p className="sr-only" role="status">{notice}</p>
      </section>
    </main>

    <footer className="shell footer">
      <span>Sources checked every 3 hours</span>
      <div>Sources include <a href="https://store.steampowered.com/" target="_blank" rel="noreferrer">Steam</a>, <a href="https://www.gamerpower.com/" target="_blank" rel="noreferrer">GamerPower</a>, and <a href="https://github.com/eikowagenknecht/lootscraper#rss-feeds" target="_blank" rel="noreferrer">LootScraper</a></div>
    </footer>
  </>
}

createRoot(document.getElementById('root')).render(<App />)
