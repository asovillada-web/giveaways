# Drop Radar

Drop Radar collects tech and gaming giveaways and free-to-keep offers. A Python worker runs every three hours, PostgreSQL merges duplicate listings, and a Vite + React dashboard reads active offers directly from Supabase. Visitors can filter by country and save entered giveaways in their browser.

## Deploy in about 10 minutes

Allow extra time for account signup, provider approval, and the first hosted build.

1. **Create a Supabase Free project.** Open **SQL Editor**, paste the complete contents of [schema.sql](schema.sql), and run it. Copy the project URL, a publishable key or legacy `anon` key, and a secret key or legacy `service_role` key. [Supabase API key guide](https://supabase.com/docs/guides/getting-started/api-keys)
2. **Push this folder to a GitHub repository.** Commit the source and examples, then push to the default branch. In **Settings → Secrets and variables → Actions**, add the repository secrets below. In **Actions → Refresh giveaway listings**, select **Run workflow** to seed the database and watch the logs. The cron runs at minute 17 every three hours in UTC. Inactive public repositories can have scheduled workflows disabled after 60 days. [GitHub schedule reference](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
3. **Import the repository into Vercel or Netlify.** Set the public variables from the table below, then deploy. These variables are read at build time.
   - **Vercel** — Choose the Vite framework preset and set **Root Directory** to `frontend`. Use Node.js 22, `npm run build`, and the `dist` output. [Vercel Vite guide](https://vercel.com/docs/frameworks/frontend/vite)
   - **Netlify** — Import the repository and use the checked-in [netlify.toml](netlify.toml). It sets the `frontend` base, Node.js 22, and `dist` publish directory. [Netlify Vite guide](https://docs.netlify.com/build/frameworks/framework-setup-guides/vite/)
4. **Verify the hosted dashboard.** After the first workflow succeeds, open a giveaway and mark it as entered. Reload the page and check the **Entered** view. The workflow summary shows how many sources responded and how many relevant observations were saved.

| Where | Variable | Value |
| --- | --- | --- |
| GitHub secret | `SUPABASE_URL` | The HTTPS project URL |
| GitHub secret | `SUPABASE_SERVICE_KEY` | Supabase secret key or legacy `service_role` key |
| GitHub secret | `YOUTUBE_API_KEY` | A Google Cloud API key restricted to YouTube Data API v3 |
| GitHub secret, optional | `DISCORD_WEBHOOK_URL` | Discord channel webhook URL |
| GitHub secrets, optional | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Approved Reddit app-only OAuth credentials |
| GitHub variable, optional | `REDDIT_USER_AGENT` | Descriptive User-Agent with your Reddit contact |
| Vercel or Netlify | `VITE_SUPABASE_URL` | The same HTTPS project URL |
| Vercel or Netlify | `VITE_SUPABASE_ANON_KEY` | Supabase publishable key or legacy `anon` key |

The write key belongs in GitHub Actions or the local worker environment. The frontend build rejects a privileged key in its public key setting. RLS and PostgreSQL grants make the dashboard read-only.

Enable YouTube Data API v3 in a Google Cloud project before creating its key. The worker covers English, Spanish, Portuguese, German, and French. Each run searches the preceding 48 hours using two widget domains per language. Domain pairs rotate every three hours, for 80 scheduled search requests per day. The worker extracts offer links from full video descriptions and credits the creator. Review YouTube’s API policies for your intended deployment. [YouTube API setup and quotas](https://developers.google.com/youtube/data/getting-started), [YouTube API developer policies](https://developers.google.com/youtube/terms/developer-policies)

Reddit starts with the requested public JSON feeds. Hosted IP ranges can receive HTTP 401 or 403. Approved OAuth credentials activate the official Reddit endpoint. Reddit source failures leave the other feeds running. [Reddit developer access and hosted IP restrictions](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data)

Discord sends up to 12 alerts per run for new guaranteed freebies and hardware giveaways that explicitly state worldwide eligibility. Alerts go out on discovery by the scheduled or manual worker. A database lease prevents two workers from claiming the same alert at once. A rare ambiguous timeout after Discord accepts a message can result in a repeat on retry.

## Run locally

Use Python 3.11+ and Node.js 22.12+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m unittest discover -s tests -v
python main.py --dry-run
```

Fill in the worker values in `.env` and run `python main.py` to write to Supabase. `--dry-run` collects and classifies offers without database writes or alerts. Add `--skip-metadata` to test feed access without visiting giveaway landing pages.

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Fill in `frontend/.env.local` with the two public Supabase values and restart the dev server if it is already running. `npm run build` creates the production site in `frontend/dist`.

## How listings are handled

- **Sources.** The Reddit adapter reads r/giveaways, r/FreeGameFindings, r/freegames, r/SteamGiveaway, and r/pcmasterrace. GamerPower JSON and RSS ship configured. Add RSS/Atom or selector-based HTML sources in [config.py](config.py). Use `source_type="Official"` for a feed from a publisher and `guaranteed=True` for a feed that exclusively contains no-cost, no-draw claims. [GamerPower API reference](https://www.gamerpower.com/api-read), [GamerPower RSS feeds](https://www.gamerpower.com/feeds)
- **Deduplication.** The canonical key drops trackers and normalizes known campaign and storefront URLs. The stored outbound URL preserves the working path and parameters. Reposts update one database row and retain stronger eligibility evidence and known deadlines.
- **Classification and eligibility.** Prize vocabulary is configurable. The Freebie category requires claim evidence and excludes draws, trials, and paid subscriptions. An unstated region gets the requested worldwide score and appears as **Region unspecified**. Explicit worldwide offers get a green badge. The optional country filter also includes supported regional matches, with stated exclusions applied.
- **Expiry.** Explicit landing-page metadata takes precedence over structured feed dates and text. Date-only deadlines use end of day UTC when no time zone is available. Unknown-deadline offers disappear seven days after their last observation. Records unseen for 28 days are pruned. The active view excludes ended offers between scheduled runs.
- **Priority.** The recommended sort adds 40 for a guaranteed freebie, 30 for worldwide or unspecified eligibility, 20 for hardware, and 10 for a known deadline in the next 48 hours.

## Folder structure

```text
.
├── .env.example
├── .github/workflows/scrape.yml
├── .gitignore
├── README.md
├── config.py
├── dates.py
├── db.py
├── eligibility.py
├── fetchers/
│   ├── __init__.py
│   ├── directories.py
│   ├── landing.py
│   ├── reddit.py
│   └── youtube.py
├── frontend/
│   ├── .env.example
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── src/
│   │   ├── catalog.js
│   │   ├── countries.js
│   │   ├── main.jsx
│   │   └── styles.css
│   └── vite.config.js
├── links.py
├── main.py
├── netlify.toml
├── processor.py
├── requirements.txt
├── schema.sql
└── tests/test_ingestion.py
```
