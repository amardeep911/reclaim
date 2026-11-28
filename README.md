# 🌿 Reclaim

**One hour at a time. One day at a time.**

Reclaim is a personal recovery companion for quitting or cutting down on **smoking** and **alcohol**.
You log each hour as you go, record consumption honestly and without judgement, and see your real
progress: streaks, money saved, cigarettes avoided and alcohol-free days.

Built with **Python + Streamlit** and **Supabase** (Postgres + Auth). There is no separate backend server.

> Reclaim is a self-help tracking tool. It does not diagnose, treat or replace medical care.
> Alcohol withdrawal can be dangerous. See *Health & Safety* in the app.

---

## Status: Phase 3 complete

| Phase 1 – MVP ✅ | Phase 2 – Recovery features ✅ | Phase 3 – Analytics ✅ |
|---|---|---|
| Sign up / log in / password reset | **Craving Manager**: "I'm having a craving" button, coping toolkit, trigger stats, history | **Analytics & Insights** page with 7 / 30 / 90 days / all time / custom filters |
| Onboarding with alcohol-dependence safety screening | **Money Saved**: calculator, projections, savings goals | Daily, weekly and monthly trends vs. baseline; cigarettes avoided over time |
| **Hourly Recovery Tracker** + morning sleep card | **Journal**: daily reflections, calendar, history, edit/delete | Weekday × hour heatmap; by-hour and by-weekday patterns |
| Smoking + alcohol consumption tracker | **Achievements**: 24 badges, unlock celebrations, kept forever | Tracked-hours breakdown; craving timing, triggers, what helps |
| Dashboard, daily check-in, Settings | **Streaks**: current, best-ever and tracking streaks, separate from lifetime totals | Weekly & monthly reports; behavioural insights from your own records |

**Next – Phase 4:** AI recovery companion (optional, OpenAI), richer health resources, notification enhancements.

---

## Architecture

```
Browser ──► Streamlit app (app.py + pages/)        ← UI and app logic, one Python process
               │
               ├── services/   talks to Supabase with the *signed-in user's* token
               ├── utils/      pure functions: calculations, dates, validation (unit tested)
               └── components/ reusable UI: cards, hourly timeline, forms, charts
               │
               ▼
          Supabase:  Auth (accounts, sessions)  +  Postgres (data, protected by RLS)
```

* **Each browser session gets its own Supabase client** (kept in `st.session_state`). The app only has the
  public *anon* key. Every query runs as the logged-in user, and **Row Level Security** in Postgres makes sure
  people can only read and write their own rows. The service-role key is never used.
* **"Not tracked" is never stored.** An hour is only saved when the user logs it, and nothing is filled in
  automatically. Progress counts only finished hours that were logged.
* **Consumption events are stored separately** (`consumption_logs`) from hourly statuses (`hourly_logs`).
  Logging a cigarette or drink marks that hour as *consumed*. Deleting the last entry in an hour returns the
  hour to *not tracked*.
* **Timezones:** everything is stored in UTC. Days and hour slots are built in the user's timezone with
  `zoneinfo`, including half-hour offsets (such as IST) and daylight-saving days with 23 or 25 hours.

### Project structure

```
addiction-free/                  ← project root (the "reclaim" repo)
├── app.py                       entry point + routing (login → onboarding → app)
├── config.py                    reads Streamlit secrets / .env
├── requirements.txt             runtime dependencies (pinned)
├── requirements-dev.txt         + pytest
├── .env.example                 local settings template
├── .streamlit/
│   ├── config.toml              light + dark theme, fonts
│   └── secrets.toml.example     template for Streamlit Cloud secrets
├── pages/
│   ├── auth.py                  log in / create account / reset password
│   ├── onboarding.py            setup wizard (incl. safety screening)
│   ├── 1_Dashboard.py
│   ├── 2_Hourly_Tracker.py
│   ├── 3_Consumption_Tracker.py
│   ├── 4_Craving_Manager.py     craving log + coping toolkit
│   ├── 5_Analytics.py           trends, heatmap, reports, insights
│   ├── 6_Achievements.py        streaks, lifetime progress, badges
│   ├── 8_Journal.py             private journal with calendar
│   ├── 11_Savings.py            savings calculator + goals
│   ├── 9_Resources.py           health & safety, support lines
│   └── 10_Settings.py
├── components/                  cards.py, hourly_timeline.py, forms.py, charts.py, navigation.py, coping.py
├── services/                    auth, database, tracking, analytics, craving, journal, savings, achievement
├── utils/                       calculations, datetime_utils, validators, constants
├── database/
│   ├── schema.sql               14 tables, indexes, constraints, triggers, achievement catalogue
│   └── rls_policies.sql         Row Level Security for every table
├── assets/                      styles.css, logo.svg, icon.svg
└── tests/                       unit tests + end-to-end page tests (in-memory Supabase fake)
```

### Database (Supabase Postgres)

| Table | Purpose |
|---|---|
| `profiles` | name, timezone, tracking hours, currency, units, motivation (1 row per user) |
| `addiction_profiles` | baseline and settings per habit (`smoking` / `alcohol`), dependence-risk flag |
| `recovery_goals` | active and past goals (quit / reduce, target per day) |
| `hourly_logs` | **one row per tracked hour**, `unique(user_id, addiction_type, slot_start)` |
| `consumption_logs` | each cigarette or drinking event, with trigger, mood, standard drinks and cost |
| `craving_logs` | cravings: intensity, trigger, mood, resisted, coping strategy |
| `daily_logs` | daily check-in: mood, sleep, exercise, water |
| `journal_entries` | private journal, one entry per day |
| `achievements`, `user_achievements` | catalogue + unlocked achievements (kept forever) |
| `savings_goals` | savings targets, filled in order |
| `notification_preferences` | reminder settings |
| `ai_conversations`, `ai_messages` | AI companion history (Phase 4) |

A sign-up trigger creates the profile and reminder rows automatically. `delete_my_account()` is a
`SECURITY DEFINER` function that can only delete the **calling** user. All their data is then removed
through `ON DELETE CASCADE`.

### Authentication flow

1. **Sign up:** `auth.sign_up`. If email confirmation is on, the user confirms by email and then logs in.
2. **Log in:** `auth.sign_in_with_password`. The session (access + refresh token) is kept in that browser
   tab's `st.session_state`.
3. **Every page load** calls `auth.get_session()`, which refreshes the access token if it is about to expire.
   No session means the user goes back to the login page. Pages are only registered for signed-in users.
4. **Password reset:** the user requests a code, Supabase emails a one-time code, and the user enters it with
   a new password (`verify_otp(type="recovery")` + `update_user`). This works inside Streamlit, which can't
   read the `#access_token` fragment that a default reset link uses.
5. **Log out:** `auth.sign_out()` and clear the session.

> Note: reloading the browser tab starts a new Streamlit session, so you'll need to log in again.
> This is a deliberate trade-off: tokens are never written to cookies or local storage.

---

### Phase 3: analytics rules

* **Insights come only from your records.** Each rule in `utils/insights.py` needs a minimum amount of data
  (for example 5+ cravings for a timing pattern, 3+ days for a baseline comparison) and is skipped on ties.
  Every sentence includes the counts it is based on.
* **Ranges start at your tracking start date.** Today counts as a partial day, weighted by how much of your
  waking time has passed, so averages and savings stay fair.
* **Chart colours were checked** with a palette validator for both light and dark mode (lightness, chroma,
  colour-blind separation, contrast). Every chart has hover tooltips and a "View data" table.

### Phase 2 business rules

* **A resisted craving** is stored in `craving_logs` and marks that hour as *craving resisted*, unless consumption
  is already logged in that hour. A consumed hour is never overwritten.
* **A craving the user acted on** can log the cigarettes or drinks at the same time. They go into
  `consumption_logs` like any other entry.
* **For alcohol cravings**, the toolkit always starts with withdrawal guidance. If the user reports physical
  symptoms, it tells them to get medical help before offering any self-help.
* **Achievements** are evaluated from real records when the Dashboard or Achievements page loads. They stay
  unlocked forever. Milestones need at least one tracked hour for that habit, so an untouched account earns
  nothing. "Reduced week" and "Best week" need activity logged on at least 5 of the 7 days.
* **Savings goals** fill in the order they were created. Marking a goal as bought deducts its cost from the
  savings available for the remaining goals.

## 1. Supabase setup (about 10 minutes)

1. Create a free project at <https://supabase.com> (choose a region close to your users).
2. **SQL Editor → New query**: paste the whole of `database/schema.sql` and click **Run**.
   Then do the same with `database/rls_policies.sql`. Both scripts are safe to re-run.
3. **Authentication → Sign In / Providers → Email**: keep Email enabled.
   * For quick local testing you can turn **Confirm email** off. Turn it back on for production.
4. **Authentication → URL Configuration → Site URL**: `http://localhost:8501` for now (change it to your
   Streamlit Cloud URL after deploying).
5. **Authentication → Emails → Reset Password** template: make sure the email shows the code by adding:
   ```html
   <p>Your Reclaim reset code is: <strong>{{ .Token }}</strong></p>
   ```
6. **Project Settings → API**: copy the **Project URL** and the **anon public** key.
   ⚠️ Do **not** use the `service_role` key anywhere in this app.

> Supabase's built-in email service is heavily rate-limited (a few emails per hour). Before you invite real
> users, set up custom SMTP under *Authentication → Emails → SMTP Settings*.

### Upgrading an existing database

Already ran the Phase 1 SQL? Run **`database/schema.sql` again** in the SQL Editor. It is idempotent. Its
*Upgrades* section adds any new columns (Phase 2 adds `trusted_contact_name` and `trusted_contact_phone` to
`profiles`). Existing data is untouched. `rls_policies.sql` doesn't need re-running for Phase 2.

## 2. Run locally

```bash
cd ~/Documents/addiction-free
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env          # then edit .env: SUPABASE_URL and SUPABASE_ANON_KEY
streamlit run app.py          # opens http://localhost:8501
```

## 3. Run the tests

```bash
pytest -q
```

* `tests/test_calculations.py`: standard drinks, savings, streaks, free days, milestones.
* `tests/test_tracking.py`: hour slots (IST offsets, DST days), timestamp parsing, validators.
* `tests/test_analytics.py`: every insight rule (thresholds, ties, wording), range maths, and the
  daily / weekly / cumulative frames.
* `tests/test_phase3_flow.py`: seeds three weeks of history and renders every range and tab for smoking,
  alcohol and both. It also checks that the expected insights appear and that a new account sees a friendly
  empty state.
* `tests/test_phase2_flow.py`: craving logging (resisted / used / never overwriting a consumed hour),
  alcohol withdrawal guidance, journal save, update and delete, savings goals, achievement unlocking (exactly
  once, and nothing for an untouched account), and trusted-contact validation.
* `tests/test_app_flow.py`: drives the **real pages** through Streamlit's `AppTest` against an in-memory
  Supabase fake. It covers onboarding, every page rendering, one-tap hourly logging, no duplicate hours, bulk
  marking (which skips consumed hours), logging and deleting consumption, profile editing and account deletion.

The SQL was also checked on PostgreSQL with a mocked `auth` schema: duplicate hours are rejected, users can't
see or write each other's rows, `anon` sees nothing, and account deletion cascades.

### Manual test checklist (against your real Supabase)

1. Create an account. With email confirmation on, confirm it from your inbox, then log in.
2. Complete onboarding with **Both** selected. In the alcohol step, answer "yes" to one safety question and
   check that the warning appears.
3. **Hourly Tracker:** tap ✅ on the quick-log card, then tap an earlier hour, mark it 💪, add a note and save.
   Mark an hour as consumed with 2 cigarettes. Go back a day with ◀ and edit an hour there.
4. **Consumption:** log a drink with a beverage, check the standard-drink estimate, then edit and delete it
   in *History*.
5. **Dashboard:** check the numbers match what you logged, and save a daily check-in.
6. **Settings:** change the tracking hours, then export your data (JSON).
7. **Craving Manager:** tap *I'm having a craving*, log it as resisted, try the breathing exercise, then
   close. Check that the hour turned yellow in the Hourly Tracker.
8. **Journal:** write today's entry, open a past day from the date picker, then edit and delete an entry.
9. **Money Saved:** add two goals and check that the first fills before the second.
10. **Achievements:** after logging an hour, the *First smoke-free hour* badge unlocks with a celebration.
11. **Settings → Profile:** add a trusted contact. The Craving Manager's *Get support* tab now has
    call and message buttons.
12. In Supabase **Table Editor**, confirm the rows exist. Then create a second account and confirm it sees
   none of the first account's data.

## 4. Put it on GitHub

```bash
cd ~/Documents/addiction-free
git init
git add .
git status                      # make sure .env and .streamlit/secrets.toml are NOT listed
git commit -m "Reclaim – Phase 1 MVP"
git branch -M main
git remote add origin https://github.com/<your-username>/reclaim.git
git push -u origin main
```

## 5. Deploy on Streamlit Community Cloud

1. Go to <https://share.streamlit.io>, choose **Create app**, pick your repo and branch `main`, and set the main file to `app.py`.
2. Under **Advanced settings → Secrets**, paste:
   ```toml
   SUPABASE_URL = "https://your-project-ref.supabase.co"
   SUPABASE_ANON_KEY = "your-anon-public-key"
   APP_ENV = "production"
   ```
3. Deploy. Then in Supabase, set **Authentication → URL Configuration → Site URL** to your
   `https://<app>.streamlit.app` address.

---

## Privacy & security

* Passwords are handled only by Supabase Auth. The app never stores them.
* Row Level Security on every table means each user can only access their own rows, even if the app had a bug.
* Only the public anon key is used. Secrets live in `.env` / Streamlit secrets, which git ignores.
* Errors shown to users are generic, and logs never contain journal text, notes or credentials.
* **Third-party hosting:** data is stored by Supabase and the app runs on Streamlit Community Cloud. Both
  process data on their own infrastructure. The Settings page explains this to users, and they can
  **export** or **delete** all of their data there.
* **Reset my data** (Settings → Privacy & data) clears every record but keeps the login and basic
  settings, then restarts the setup wizard. It is safe to retry if interrupted.
* The AI companion (Phase 4) is optional, and the app works fully without an OpenAI key.
