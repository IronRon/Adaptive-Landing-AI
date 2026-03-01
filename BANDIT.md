# Contextual Multi-Armed Bandit

A simple bucketised contextual bandit that picks **one page-layout variant
(arm) per visit** for returning users, then learns which arm works best in
each context bucket from CTA-click rewards.

Everything lives in the **`landing`** app.

---

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  POST /accept-cookies/                                          │
│                                                                 │
│  1. Resolve / create Visitor + Session                          │
│  2. Compute visit_number for this visitor                       │
│  3. If visit_number == 1 → return control (no page_config)      │
│  4. If visit_number >= 2:                                       │
│       a. build_context(visitor, request)                        │
│       b. bucketize(context)  →  e.g. "desktop_price"            │
│       c. choose_arm(bucket)  →  epsilon-greedy pick             │
│       d. Save BanditDecision row                                │
│       e. Return { arm_id, page_config } in JSON response        │
│  5. Frontend calls applyPageConfig(page_config)                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  POST /end-session/                                             │
│                                                                 │
│  1. Compute intent scores + cta_clicked as usual                │
│  2. If visit_number >= 2:                                       │
│       a. Find BanditDecision for this session                   │
│       b. reward = 1.0 if cta_clicked else 0.0                   │
│       c. Store reward on BanditDecision                         │
│       d. update_stats(bucket, arm, reward)                      │
│  3. If visit_number == 1 → nothing bandit-related               │
└─────────────────────────────────────────────────────────────────┘
```

### Why only returning users?

The first visit is **observation-only** — we collect intent scores and
behavioural data without changing the page. From the second visit onward we
have a `last_primary_intent` to bucket on, and a baseline to compare
against.

---

## Models

All three models are defined in `landing/models.py`.

### `BanditArm`

| Field | Type | Description |
|---|---|---|
| `arm_id` | `CharField(unique)` | Machine-readable key, e.g. `"pricing_highlight_plan_2"` |
| `name` | `CharField` | Optional human label |
| `page_config` | `JSONField` | Config dict for `applyPageConfig()` (see shape below) |
| `is_active` | `BooleanField` | Inactive arms are excluded from selection |
| `created_at` | `DateTimeField` | Auto-set on creation |

### `BanditDecision`

One row per session where the bandit ran (visit ≥ 2).

| Field | Type | Description |
|---|---|---|
| `session` | `OneToOneField → Session` | The session this decision belongs to |
| `visitor` | `ForeignKey → Visitor` | The visitor |
| `context_bucket` | `CharField(indexed)` | e.g. `"desktop_price"` |
| `context_json` | `JSONField` | Full context snapshot at decision time |
| `arm` | `ForeignKey → BanditArm` | The chosen arm |
| `explore` | `BooleanField` | `True` if random/warmup pick |
| `epsilon` | `FloatField` | Epsilon at decision time |
| `reward` | `FloatField(nullable)` | Filled when session ends (1.0 or 0.0) |
| `created_at` | `DateTimeField` | Auto-set |

### `BanditArmStat`

Running stats per (bucket, arm) pair. Unique constraint on `(context_bucket, arm)`.

| Field | Type | Description |
|---|---|---|
| `context_bucket` | `CharField(indexed)` | e.g. `"mobile_trust"` |
| `arm` | `ForeignKey → BanditArm` | The arm |
| `n` | `IntegerField` | Pull count in this bucket |
| `sum_reward` | `FloatField` | Cumulative reward |
| `mean_reward` | `FloatField` | `sum_reward / n` (cached) |
| `updated_at` | `DateTimeField` | Auto-updated on save |

### `Session.visit_number`

`IntegerField(default=1)` added to the existing Session model. Computed on
session creation as `(prior sessions for this visitor) + 1`.

---

## Utility Functions

All in `landing/bandit_utils.py`.

### `build_context(visitor, request) → dict`

Extracts context features used for bucketing:

- **`device_type`** — `"mobile"` or `"desktop"` (User-Agent heuristic)
- **`last_primary_intent`** — `primary_intent` from the visitor's most
  recent ended session (`"price"`, `"trust"`, `"service"`, `"location"`,
  `"contact"`, or `"unknown"`)
- **`last_scores`** — dict of the five intent score floats from that session

### `bucketize(context) → str`

Produces a discrete bucket string: `"{device_type}_{last_primary_intent}"`.

Examples: `desktop_price`, `mobile_trust`, `mobile_unknown`.

### `choose_arm(bucket, epsilon=0.10) → (arm, explore_flag)`

Epsilon-greedy selection within the given bucket.

1. **Warmup** — if any active arm has fewer than `MIN_TRIES_PER_ARM` (5)
   pulls in this bucket, pick one of those at random (forced exploration).
2. **Explore** — with probability `EPSILON` (0.10), pick a random arm.
3. **Exploit** — otherwise pick the arm with the highest `mean_reward` in
   this bucket.

### `update_stats(bucket, arm, reward)`

Incremental update: `get_or_create` the `BanditArmStat` row, then:

```
n          += 1
sum_reward += reward
mean_reward = sum_reward / n
```

### Configuration Constants

| Constant | Default | Description |
|---|---|---|
| `EPSILON` | `0.10` | Exploration probability |
| `MIN_TRIES_PER_ARM` | `5` | Warmup pulls before epsilon-greedy kicks in |

---

## Starter Arms

Seeded via `python manage.py seed_bandit_arms`. Each arm's `page_config`
follows the shape consumed by the frontend's `applyPageConfig()`:

```json
{
  "compact":  ["section_id", ...],
  "hide":     ["section_id", ...],
  "promote":  "section_id" | null,
  "variants": { "section_id": "css-class", ... }
}
```

| arm_id | Description | page_config |
|---|---|---|
| `no_change` | Control — no layout changes | `{}` |
| `hero_compact` | Hero section compacted | `compact: ["hero"]` |
| `pricing_compact` | Pricing section compacted | `compact: ["pricing"]` |
| `pricing_highlight_plan_2` | Highlight the middle pricing plan | `variants: {"pricing": "highlight-plan-2"}` |
| `testimonials_single` | Show one testimonial at a time | `variants: {"testimonials": "testimonials-single"}` |
| `services_compact` | Services section compacted | `compact: ["services"]` |

---

## Management Commands

### `seed_bandit_arms`

```bash
python manage.py seed_bandit_arms          # insert new arms (skip existing)
python manage.py seed_bandit_arms --reset  # delete all arms first, then insert
```

---

## Reward Signal

Currently binary:

| Condition | Reward |
|---|---|
| `session.cta_clicked == True` | `1.0` |
| `session.cta_clicked == False` | `0.0` |

Rewards are only recorded for sessions where the bandit ran (`visit_number >= 2`).

---

## Context Buckets

Buckets are the Cartesian product of:

- **Device**: `mobile`, `desktop`
- **Last intent**: `price`, `service`, `trust`, `location`, `contact`, `unknown`

Giving up to **12 buckets** (e.g. `mobile_price`, `desktop_unknown`).
Each bucket maintains independent arm statistics, so the bandit can learn
that e.g. `pricing_highlight_plan_2` works well for `desktop_price` visitors
but not for `mobile_trust`.

---

## Frontend Integration

The `/accept-cookies/` response includes:

```json
{
  "session_id": "...",
  "visitor_id": "...",
  "is_new": false,
  "visit_number": 3,
  "arm_id": "pricing_highlight_plan_2",
  "page_config": {
    "compact": [],
    "hide": [],
    "promote": null,
    "variants": { "pricing": "highlight-plan-2" }
  }
}
```

`ui.js` calls `window.applyPageConfig(data.page_config)` after receiving
the response, which applies compact/hide/promote/variant CSS classes to the
page sections.

---

## File Map

| File | Contents |
|---|---|
| `landing/models.py` | `BanditArm`, `BanditDecision`, `BanditArmStat` + `Session.visit_number` |
| `landing/bandit_utils.py` | `build_context`, `bucketize`, `choose_arm`, `update_stats` |
| `landing/views.py` | Bandit logic in `accept_cookies` and `end_session` views |
| `landing/admin.py` | Admin classes for all three bandit models |
| `landing/management/commands/seed_bandit_arms.py` | Seed command for starter arms |
| `static/landing/ui.js` | `applyPageConfig()` + call site in `startTracking()` |
