# Drop Radar

Drop Radar collects tech and gaming giveaways and free-to-keep offers. A Python worker runs every three hours, PostgreSQL merges duplicate listings, and a Vite + React dashboard reads active offers directly from Supabase. Visitors can filter by country and save entered giveaways in their browser.

## Deploy in about 10 minutes

Allow extra time for account signup, provider approval, and the first hosted build.

### 1. Set up Supabase

Create a Supabase Free project. Open **SQL Editor**, paste the full [schema.sql](schema.sql), and run it. **Success. No rows returned** is expected. Use the project’s **Connect** button to copy its HTTPS URL and **Settings → API Keys** to find the publishable and secret keys. The `sb_secret_…` key works as `SUPABASE_SERVICE_KEY`. Keep `.env.example` as a template and save local credentials in the ignored `.env` file. [Supabase API key guide](https://supabase.com/docs/guides/getting-started/api-keys)

### 2. Set up the GitHub worker

1. Push the source to GitHub and open the repository in your browser.
2. Go to **Settings → Secrets and variables → Actions**. Under **Secrets**, click **New repository secret**. Add `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `YOUTUBE_API_KEY` one at a time using the values below. `YOUTUBE_API_KEY` enables creator discovery. The directory feeds run even when that key is absent. [GitHub repository secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets#creating-secrets-for-a-repository)
3. Open **Actions → Refresh giveaway listings → Run workflow**. Select the default branch and click **Run workflow** again. Open the run and check **Collect and publish giveaways** for the number of recorded observations. The schedule runs at minute 17 every three hours in UTC. Inactive public repositories can have scheduled workflows disabled after 60 days. [Running a workflow manually](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow), [schedule reference](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

### 3. Publish the dashboard

Use one hosting provider. On **Vercel**, sign in with GitHub, choose **Add New → Project**, and click **Import** next to the giveaway repository. If the repository is missing, grant the Vercel GitHub app access to that repository. Open **Root Directory → Edit**, select `frontend`, and confirm **Vite** in **Framework Preset**. Keep the detected build and output settings, normally `npm run build` and `dist`.

Before clicking **Deploy**, expand **Environment Variables** and add `VITE_SUPABASE_URL` with your project URL and `VITE_SUPABASE_ANON_KEY` with the `sb_publishable_…` key. Click **Deploy** and open the generated `.vercel.app` URL. If you add or change a variable later under **Settings → Environment Variables**, redeploy from **Deployments** so the build picks it up. [Importing a GitHub repo into Vercel](https://vercel.com/docs/git#deploying-a-git-repository), [Vercel environment variables](https://vercel.com/docs/environment-variables)

On **Netlify**, choose **Add new project → Import an existing project**, connect GitHub, and pick the repository. The checked-in [netlify.toml](netlify.toml) sets the `frontend` base, Node.js 22, and `dist` publish directory. Add the same two `VITE_` variables before deploying. [Netlify Vite guide](https://docs.netlify.com/build/frameworks/framework-setup-guides/vite/)

### 4. Verify the first deployment

After the first workflow succeeds, open the dashboard, select a giveaway, and mark it as entered. Reload the page and check the **Entered** view.

For an existing deployment, run the updated [schema.sql](schema.sql) in **Supabase → SQL Editor** before pushing the new worker and dashboard to GitHub. The migration preserves existing listings and adds the new feed fields. Then run **Actions → Refresh giveaway listings → Run workflow** to populate the new sources.

| Where | Variable | Value |
| --- | --- | --- |
| GitHub secret | `SUPABASE_URL` | The HTTPS project URL |
| GitHub secret | `SUPABASE_SERVICE_KEY` | Supabase secret key or legacy `service_role` key |
| GitHub secret | `YOUTUBE_API_KEY` | A Google Cloud API key restricted to YouTube Data API v3 |
| GitHub secret, optional | `DISCORD_WEBHOOK_URL` | Discord channel webhook URL |
| GitHub secrets, optional | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | App-only OAuth credentials from an existing approved Reddit Data API app |
| GitHub variable, optional | `REDDIT_USER_AGENT` | Descriptive User-Agent with your Reddit contact |
| Vercel or Netlify | `VITE_SUPABASE_URL` | The same HTTPS project URL |
| Vercel or Netlify | `VITE_SUPABASE_ANON_KEY` | Supabase publishable key or legacy `anon` key |

The write key belongs in GitHub Actions or the local worker environment. The frontend build rejects a privileged key in its public key setting. RLS and PostgreSQL grants make the dashboard read-only.

If the workflow reports `InvalidHeader`, open **Settings → Secrets and variables → Actions**, edit `SUPABASE_SERVICE_KEY`, and paste the value copied from Supabase on a single line without quotes or the variable name. Save the secret and start a new run from the workflow page.

### YouTube creator discovery

In Google Cloud Console, select your project and enable **YouTube Data API v3** under **APIs & Services → Library**. In **APIs & Services → Credentials**, create or select an **API key**. If the wizard asks for the type of data, select public data. For a standard GitHub-hosted runner, leave **Application restrictions** at **None** and set **API restrictions → Restrict key → YouTube Data API v3**. Save and copy the key into the GitHub repository secret `YOUTUBE_API_KEY`. [Google’s public-data credentials guide](https://developers.google.com/youtube/data/guides/authentication)

The worker covers English, Spanish, Portuguese, German, and French. Each run searches the preceding 48 hours with two queries per language, one for tech giveaways and one for a widget domain. The widget domain rotates every three hours across Gleam, SweepWidget, KingSumo, and Rafflecopter, for 80 scheduled search requests per day. Results require a supported entry link in the full video description and credit the creator. [YouTube API setup and quotas](https://developers.google.com/youtube/data/getting-started), [YouTube API developer policies](https://developers.google.com/youtube/terms/developer-policies)

### Optional Discord alerts

In your Discord server, go to **Server Settings → Integrations → Webhooks → New Webhook**. Select the destination text channel, give the webhook a name such as **Drop Radar**, and click **Copy Webhook URL**. Under **Settings → Secrets and variables → Actions** in GitHub, save the whole URL as the repository secret `DISCORD_WEBHOOK_URL`. The URL includes the ID and token. Start a fresh workflow run to verify delivery. Leave the setting empty to skip alerts. [Discord webhook guide](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks)

Discord sends up to 12 alerts per run for new guaranteed freebies and hardware giveaways that explicitly state worldwide eligibility. Alerts go out on discovery by the scheduled or manual worker. A database lease prevents two workers from claiming the same alert at once. A rare ambiguous timeout after Discord accepts a message can result in a repeat on retry.

### Optional Reddit OAuth

Reddit stopped accepting new Public Data API requests on October 31, 2026 and plans to end remaining public access in March 2027. A new Reddit integration would use Devvit and need Reddit to approve the data flow to the external dashboard. Hosted runners can be blocked when they request the public JSON feeds. The other sources continue running when Reddit is unavailable. [Reddit’s migration timeline](https://www.reddit.com/r/redditdev/comments/1wubcvf/moving_data_api_apps_to_the_developer_platform/), [Devvit migration guide](https://developers.reddit.com/docs/guides/migrate/public-api)

If you already have an approved Data API app with app-only access, add its client ID and secret as `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in GitHub Actions. Under the **Variables** tab, add `REDDIT_USER_AGENT` with a value like `linux:drop-radar:v1.0 (by /u/your_username)`. Check Reddit’s registration instructions for existing apps. [Register an existing Reddit app](https://developers.reddit.com/app-registration), [Reddit OAuth and User-Agent guidance](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)

## Run locally

Use Python 3.11+ and Node.js 22.12+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
python -m unittest discover -s tests -v
python main.py --dry-run
```

Fill in the worker values in `.env` and run `python main.py` to write to Supabase. `--dry-run` collects and classifies offers without database writes or alerts. Add `--skip-metadata` to test feed access without visiting giveaway landing pages.

```bash
cd frontend
cp -n .env.example .env.local
npm ci
npm run dev
```

Fill in `frontend/.env.local` with the two public Supabase values and restart the dev server if it is already running. `npm run build` creates the production site in `frontend/dist`.

## How listings are handled

- **Game claims.** The worker checks Steam's storefront specials, Epic's active store promotions, GamerPower, and LootScraper feeds for Steam, GOG, and Humble. Steam claims require a normally paid full game with a 100% discount. The dashboard links to SteamDB for manual browsing when no Steam games match. [Steam Free to Keep](https://partner.steamgames.com/doc/marketing/discounts/freetokeep?language=english), [Epic free games](https://store.epicgames.com/en-US/free-games), [GamerPower API reference](https://www.gamerpower.com/api-read), [LootScraper feeds](https://github.com/eikowagenknecht/lootscraper#rss-feeds)
- **Software and assets.** The worker uses Giveaway of the Day, SharewareOnSale releases marked 100% off, and LootScraper's Fab feed. [Giveaway of the Day](https://blog.giveawayoftheday.com/), [SharewareOnSale](https://sharewareonsale.com/about-us), [Fab limited-time free offers](https://www.fab.com/limited-time-free)
- **Prize draws.** The worker checks GiveawayBase's worldwide feed for direct entry links, stated eligibility, and deadlines. The YouTube and Reddit adapters also surface creator and community draws. Add other RSS/Atom or selector-based HTML feeds in [config.py](config.py). Use `guaranteed=True` for feeds that exclusively list no-cost claims. [GiveawayBase worldwide listings](https://giveawaybase.com/category/worldwide-2/)
- **Deduplication.** The canonical key drops trackers and normalizes known campaign and storefront URLs. The stored outbound URL preserves the working path and parameters. Reposts update one database row and retain stronger eligibility evidence and known deadlines.
- **Filters and eligibility.** **Steam games** selects full Steam game claims and Steam keys. Full game claims, keys, DLC and loot, and software and assets also have individual filters. **Worldwide only** requires explicit worldwide eligibility and works with the **Gleam** platform filter. Unstated eligibility appears as **Region unspecified**, while the country filter includes supported matches and applies stated exclusions.
- **Expiry.** Verified claim schedules take precedence for structured promotions. Other listings use landing-page metadata before feed dates and text. Date-only deadlines use end of day UTC when no time zone is available. Offers with a confirmed active price and no deadline must refresh within six hours. Other unknown-deadline offers disappear seven days after their last observation. Records unseen for 28 days are pruned.
- **Priority.** Recommended and Freebies First put Steam full game claims first, followed by Steam game keys, then games from other stores. The underlying score adds 40 for a guaranteed freebie, 30 for worldwide or unspecified eligibility, 20 for hardware, and 10 for a known deadline in the next 48 hours.

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
│   ├── promotions.py
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
└── tests/
    ├── test_ingestion.py
    └── test_promotions.py
```
