# Adaptive Landing Page AI

A Django-based system that **personalises a landing page in real time** using a
contextual multi-armed bandit algorithm. The system tracks every visitor
interaction, builds per-user engagement profiles, and will (once the bandit is
fully wired) automatically adjust section ordering, visibility, and variant
styling to maximise conversions.

> **Status:** The tracking + database layer and frontend event pipeline are
> implemented and functional. The contextual bandit algorithm is the next
> milestone.

---

## Table of Contents

1. [Project Goal](#project-goal)
2. [Architecture Overview](#architecture-overview)
3. [Tech Stack](#tech-stack)
4. [What Has Been Implemented](#what-has-been-implemented)
5. [What Is Next](#what-is-next)
6. [Project Structure](#project-structure)
7. [Database Schema](#database-schema)
8. [Data Flow](#data-flow)
9. [Setup & Running](#setup--running)
10. [Legacy / Prototype Code](#legacy--prototype-code)

---

## Project Goal

Traditional A/B testing shows every visitor the same variant and requires large
sample sizes before reaching significance. This project replaces A/B testing
with a **contextual multi-armed bandit** that:

- **Explores** different page configurations (section order, variants, CTA
  emphasis, hidden/promoted sections) across visitors.
- **Exploits** configurations that perform well for visitors with similar
  context (return vs. new, referrer, device, engagement history).
- **Converges** on high-conversion layouts faster than a fixed A/B split.

The landing page used as the test case is a fictional car-wash membership site
(**SparkleWash**) with 11 sections (header, hero, trust bar, services, pricing,
testimonials, about, locations, FAQ, contact, footer).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      Browser                            │
│                                                         │
│  landing_page.html                                      │
│    ├── ui.js        (cookie consent, UI interactions)   │
│    └── tracking.js  (event tracking, batching, flush)   │
│                                                         │
│  ① Accept cookies  ──POST /accept-cookies/──►           │
│  ② Batch events    ──POST /track-interactions/──►       │
└──────────────────────────────┬──────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────┐
│                   Django Backend                        │
│                                                         │
│  views.py                                               │
│    ├── accept_cookies()   → Visitor + Session creation   │
│    ├── track_interactions() → Event bulk_create          │
│    └── demo_landing_page()  → serves landing_page.html  │
│                                                         │
│  models.py                                              │
│    ├── Visitor   (cookie-based identity)                │
│    ├── Session   (one per page-load)                    │
│    ├── Event     (every tracked interaction)            │
│    └── BanditArm (global section scoring — future)      │
│                                                         │
│  bandit.py       (UCB1 scoring — placeholder)           │
│  utils.py        (per-user section engagement scores)   │
└──────────────────────────────┬──────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────┐
│              PostgreSQL  (adaptive_landing)              │
│                                                         │
│  landing_visitor  ──1:N──  landing_session               │
│  landing_session  ──1:N──  landing_event                 │
│  landing_banditarm                                       │
└─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer       | Technology                              |
| ----------- | --------------------------------------- |
| Backend     | Python 3, Django 4.2                    |
| Database    | PostgreSQL (via psycopg2-binary)         |
| Frontend    | Vanilla JS, Django templates, CSS       |
| Tracking    | Custom event pipeline (tracking.js)     |
| AI (future) | Contextual multi-armed bandit (Python)  |

---

## What Has Been Implemented

### Visitor & Cookie Tracking

- **Long-lived visitor identity** via a `visitor_id` cookie (UUID, 1-year
  expiry) set by the backend on cookie acceptance.
- **Cookie consent modal** in the landing page — tracking only begins after the
  user explicitly clicks "Accept Cookies".
- `POST /accept-cookies/` handles both **first-time** and **returning**
  visitors:
  - New visitor → creates `Visitor` + `Session`, sets `visitor_id` cookie.
  - Returning visitor → finds existing `Visitor` (from cookie), closes stale
    sessions, creates a fresh `Session`.
  - Returns `{ session_id, visitor_id, is_new }` to the frontend.

### Session Management

- One `Session` per page-load (created server-side, UUID passed to JS).
- `user_agent` and `referrer` captured automatically from request headers.
- Previous active sessions are closed (`is_active=False`, `ended_at` stamped)
  when a new session starts.

### Frontend Event Tracking (`tracking.js` v3)

The tracker captures 9 event types using data attributes:

| Event Type      | Trigger                                      | Key Fields                        |
| --------------- | -------------------------------------------- | --------------------------------- |
| `page_view`     | Once on page load                            | `referrer`                        |
| `click`         | Any `[data-track-click]` element             | `element`, `section`, `tag`, `text`, `is_cta` |
| `hover`         | Mouse dwell on `[data-track-click]` (>200ms) | `element`, `section`, `duration_ms`, `is_cta` |
| `section_view`  | Section first enters viewport (30%)          | `section`                         |
| `section_dwell` | Section leaves viewport or page unload       | `section`, `duration_ms`, `read`  |
| `scroll_depth`  | 25 / 50 / 75 / 100% milestones              | `depth`                           |
| `time_on_page`  | Page hide / unload                           | `seconds`                         |
| `form_focus`    | User focuses a form field                    | `section`, `field`                |
| `form_submit`   | Form submitted                               | `section`, `form_id`              |

Events are queued in memory and flushed:
- Every 5 seconds (batch timer).
- When the queue reaches 50 events.
- On `visibilitychange` (tab hidden) and `beforeunload` (via `sendBeacon`).

The tracker **never generates its own session ID** — it requires a server-provided UUID from `/accept-cookies/` before it will start.

### Backend Event Storage (`POST /track-interactions/`)

- Receives `{ session_id, events: [...] }` from the frontend.
- Maps commonly-queried fields (`event_type`, `section`, `element`, `is_cta`,
  `duration_ms`) to dedicated database columns for fast filtering.
- Stores all remaining event fields in a `metadata` JSONField (so the frontend
  can evolve without requiring migrations).
- Uses `bulk_create` for efficiency.

### Landing Page (Hardcoded)

- `templates/landing/landing_page.html` — the single landing page served at `/demo/`.
- 11 section templates in `templates/sections/` (header, hero, trust_bar,
  services, pricing, testimonials, about, locations, faq, contact, footer).
- Each section uses `data-track` and `data-track-click` attributes for the
  event tracker.
- `ui.js` handles all interactive UI (carousel, pricing toggle, FAQ accordion,
  smooth scroll, section variant helpers, cookie consent flow).

### Django Admin

All tracking models (`Visitor`, `Session`, `Event`, `BanditArm`) are registered
in the admin with appropriate `list_display`, `list_filter`, and
`search_fields` for easy debugging and data inspection.

---

## What Is Next

### Contextual Multi-Armed Bandit Algorithm

The core personalisation engine. Planned approach:

1. **Arms** — each "arm" is a page configuration (section order, variant
   classes, promoted/hidden sections). The existing `BanditArm` model and
   `ui.js` variant helpers (`setVariant`, `toggleCompact`, `hideSection`,
   `promoteSection`, `applyPageConfig`) are already in place.

2. **Context** — per-visitor features derived from tracked data:
   - New vs. returning visitor, session count
   - Referrer / traffic source
   - Device type (from user-agent)
   - Historical section engagement scores (from `utils.get_user_section_scores`)

3. **Reward signal** — derived from events:
   - CTA clicks (`is_cta=True`)
   - Form submissions
   - Section dwell time (read = True)
   - Scroll depth reaching 75%+

4. **Policy** — contextual bandit (e.g. LinUCB or Thompson Sampling with
   contextual features) selects the page configuration on each visit, observes
   the reward, and updates its model.

5. **Decision table** — a new model to log which configuration was shown to
   which visitor and the resulting reward, closing the feedback loop.

---

## Project Structure

```
adaptive-landing-ai/
├── manage.py
├── core/                       # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── landing/                    # Main application
│   ├── models.py               # Visitor, Session, Event, BanditArm, ...
│   ├── views.py                # Endpoints + page views
│   ├── urls.py                 # URL routing
│   ├── admin.py                # Admin registrations
│   ├── bandit.py               # UCB1 scoring (placeholder)
│   ├── utils.py                # Scoring utilities
│   ├── ai_llm.py               # Legacy: LLM recommendation call
│   └── migrations/
├── static/
│   ├── landing/
│   │   ├── styles.css          # Landing page styles
│   │   ├── tracking.js         # Event tracking (v3)
│   │   └── ui.js               # UI interactions + cookie consent
│   └── js/
│       └── cookie_consent.js   # Legacy: old cookie handler
├── templates/
│   ├── base.html               # Base HTML template
│   ├── landing/
│   │   ├── landing_page.html   # Hardcoded landing page (current)
│   │   ├── index_dynamic.html  # Legacy: dynamic builder-based page
│   │   └── index.html          # Legacy
│   ├── sections/               # 11 section partials
│   │   ├── header.html
│   │   ├── hero.html
│   │   ├── trust_bar.html
│   │   ├── services.html
│   │   ├── pricing.html
│   │   ├── testimonials.html
│   │   ├── about.html
│   │   ├── locations.html
│   │   ├── faq.html
│   │   ├── contact.html
│   │   └── footer.html
│   └── builder/                # Legacy: page builder templates
└── fyp_env/                    # Python virtual environment
```

---

## Database Schema

### Tracking Models (active)

```
Visitor
  ├── cookie_id      UUID (unique, auto-generated)
  ├── created_at     datetime
  └── last_seen      datetime (auto-updated)

Session
  ├── visitor         FK → Visitor
  ├── session_id      UUID (unique, auto-generated)
  ├── started_at      datetime
  ├── ended_at        datetime (nullable)
  ├── user_agent      text
  ├── referrer        URL
  └── is_active       boolean

Event
  ├── session         FK → Session
  ├── event_type      char     (indexed)
  ├── timestamp       datetime (client-side)
  ├── created_at      datetime (server-side)
  ├── url             char
  ├── section         char     (indexed)
  ├── element         char
  ├── is_cta          boolean  (nullable)
  ├── duration_ms     integer  (nullable)
  └── metadata        JSON     (catch-all)
```

### Other Models (legacy / future)

- `BanditArm` — global per-section pull count and reward (future bandit use).
- `LandingPage` / `LandingSection` — legacy page builder (not actively used).
- `AIRecommendation` — legacy LLM response log.

---

## Data Flow

```
Page load → ui.js initCookieConsent()
  │
  ├── No consent cookie → show modal → user clicks Accept
  │     → set sw_cookie_consent cookie (JS)
  │
  └── Has consent (or just accepted) → startTracking()
        │
        ├── POST /accept-cookies/
        │     → backend creates/finds Visitor + new Session
        │     → Set-Cookie: visitor_id=<uuid> (1 year)
        │     → returns { session_id }
        │
        └── SparkleTracker._init(session_id)
              ├── Emits page_view event
              ├── Wires click, hover, section, scroll, time, form listeners
              └── Batch timer every 5s → POST /track-interactions/
                    → { session_id, events: [...] }
                    → bulk_create → Event table
```

---

## Setup & Running

### Prerequisites

- Python 3.10+
- PostgreSQL running locally

### Installation

```bash
# Clone and enter the project
cd adaptive-landing-ai

# Create and activate virtual environment
python -m venv fyp_env
fyp_env\Scripts\activate        # Windows
# source fyp_env/bin/activate   # macOS/Linux

# Install dependencies
pip install django psycopg2-binary

# Create the PostgreSQL database
# (Expects: database=adaptive_landing, user=fyp, password=fyp123)

# Run migrations
python manage.py migrate

# Create a superuser (for /admin/ access)
python manage.py createsuperuser

# Start the dev server
python manage.py runserver
```

### Key URLs

| URL                     | Description                        |
| ----------------------- | ---------------------------------- |
| `/demo/`                | Hardcoded landing page             |
| `/admin/`               | Django admin (inspect tracked data)|
| `POST /accept-cookies/` | Cookie acceptance + session start  |
| `POST /track-interactions/` | Batched event ingestion        |

---

## Legacy / Prototype Code

The initial prototype used a different approach — a **landing page builder** that
let developers create pages via a Django admin-like UI, and used **ChatGPT
(OpenAI API)** as the AI engine to generate layout recommendations based on
section HTML and engagement data.

The following files remain from that prototype but are **not actively used** in
the current implementation:

| File / Directory             | Purpose (legacy)                                |
| ---------------------------- | ----------------------------------------------- |
| `landing/ai_llm.py`         | OpenAI API call to generate LLM recommendations |
| `landing/bandit.py`         | Simple UCB1 bandit (global, non-contextual)      |
| `templates/builder/`        | Page builder UI templates                        |
| `templates/landing/index_dynamic.html` | Dynamic page rendered from DB sections |
| `static/js/cookie_consent.js` | Old cookie consent handler (replaced by `ui.js`) |
| `static/js/page_builder.js` | Builder frontend logic                           |
| Builder views in `views.py` | `builder_*` endpoints for CRUD on pages/sections |
| `LandingPage` / `LandingSection` models | DB-driven page/section storage      |
| `AIRecommendation` model    | Logged LLM responses                             |

These will be cleaned up or repurposed as the contextual bandit is implemented.
