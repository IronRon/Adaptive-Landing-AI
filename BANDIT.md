# Contextual Multi-Armed Bandit

A **linear contextual bandit** that picks **one page-layout variant (arm) per
visit** for returning users. Each arm learns which kinds of visitors it works
well for, using ridge regression on a continuous feature vector — no discrete
buckets.

Everything lives in the **`landing`** app.

---

## The Problem

We have a landing page and lots of possible layout variations (compact sections,
highlighted plans, promoted sections, etc.). We want to automatically find which
variation works best for each type of visitor, without hard-coding rules.

Traditional A/B testing shows everyone the same variant and takes ages to reach
significance. A contextual bandit **learns while it serves** — it shows the
layout it thinks will work best for *this* visitor, while still occasionally
trying random alternatives to discover something better.

---

## How It Works (Plain English)

1. A visitor arrives. We describe them as **8 numbers** (their feature vector) —
   things like "are they on mobile?", "how interested in pricing were they last
   time?", etc.

2. Each arm has learned a set of **weights** — one per feature. To predict
   whether an arm will work for this visitor, we multiply each feature by its
   weight and add them up:

   ```
   predicted_reward = feature₁ × weight₁ + feature₂ × weight₂ + ... + feature₈ × weight₈
   ```

3. **90% of the time** we pick the arm with the highest predicted reward
   (exploit). **10% of the time** we pick a random arm (explore) so we keep
   learning about all options.

4. When the visitor leaves, we check if they clicked a CTA (reward = 1) or not
   (reward = 0). We use that result to update the chosen arm's weights so
   predictions get better over time.

That's it. Over many visits the weights converge — each arm learns which
visitor features predict success, and the bandit naturally starts picking the
right arm for each visitor type.

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
│       a. build_context(visitor, request) → feature_vector       │
│       b. choose_arm(feature_vector) → ε-greedy pick             │
│       c. Save BanditDecision row (with feature_vector)          │
│       d. Return { arm_id, page_config } in JSON response        │
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
│       d. update_stats(arm, feature_vector, reward)              │
│          → updates LinUCBParam (A_matrix, b_vector)             │
│  3. If visit_number == 1 → nothing bandit-related               │
└─────────────────────────────────────────────────────────────────┘
```

### Why only returning visitors?

The first visit is **observation-only** — we collect intent scores and
behavioural data without changing the page. From the second visit onward we
have engagement data from their previous session(s) to build a meaningful
feature vector.

---

## Feature Vector

Each visitor is represented by 8 continuous numbers (all between 0 and 1):

| # | Feature | Source | Range |
|---|---------|--------|-------|
| 0 | `is_mobile` | User-Agent header | 0 or 1 |
| 1 | `price_score` | `price_intent_score` from last ended session | 0–1 |
| 2 | `service_score` | `service_intent_score` from last ended session | 0–1 |
| 3 | `trust_score` | `trust_intent_score` from last ended session | 0–1 |
| 4 | `location_score` | `location_intent_score` from last ended session | 0–1 |
| 5 | `contact_score` | `contact_intent_score` from last ended session | 0–1 |
| 6 | `visit_number_norm` | `min(visit_count, 10) / 10` | 0–1 |
| 7 | `bias` | Always `1.0` | 1 |

The **bias term** is a constant 1.0 that lets the model learn a baseline
prediction even when all other features are zero (like an intercept in a
regression equation).

### Why continuous instead of buckets?

The old approach threw away information — it reduced 5 intent scores to a single
"primary intent" label, and combined that with device type into ~12 buckets
like `desktop_price`. The linear model keeps all the original scores as
continuous values, so it can learn nuanced patterns like "visitors with
*high* pricing interest respond differently from those with *moderate*
pricing interest."

---

## The Linear Model (Ridge Regression)

Each arm stores two things in its `LinUCBParam`:

### A_matrix — "What visitors this arm has seen"

An 8×8 grid (matrix). Every time a visitor is shown this arm, their feature
vector gets multiplied by itself to produce an 8×8 grid of feature-pair
combinations, which is added to A_matrix:

```
A_matrix = A_matrix + outer_product(features, features)
```

This tracks:
- **Diagonal cells**: how much of each feature has been seen (e.g. how many
  mobile visitors, how much pricing interest overall).
- **Off-diagonal cells**: which features appeared together (correlations), so
  the model doesn't double-count overlapping signals.

**Starting value**: identity matrix (1s on diagonal, 0s elsewhere) — scaled by
`LAMBDA_REG` (1.0). This acts as a safety net that keeps early predictions
conservative and prevents division-by-zero. As real data accumulates, it gets
overwhelmed by actual observations.

### b_vector — "What worked"

A list of 8 numbers. Every time a visitor clicks a CTA after seeing this arm
(reward = 1), their feature vector gets added to b_vector:

```
b_vector = b_vector + reward × features
```

If the visitor didn't click (reward = 0), nothing changes — only successes
contribute. Over time b_vector accumulates a picture of "the kind of visitor
this arm works well for."

**Starting value**: all zeros — "no rewards seen yet."

### Computing weights (prediction)

To predict a reward for a visitor:

```
weights  = solve(A_matrix, b_vector)     # i.e. A⁻¹ × b
predicted_reward = dot(features, weights) # multiply each feature by its weight and sum
```

In plain English: **weights = "what worked" ÷ "what I've seen"**. Then
multiply each feature by its weight and add up to get a predicted reward.

This is computed using `numpy.linalg.solve()` — a numerically stable way to
solve the equation `A × weights = b` for weights.

---

## Arm Selection Policy: ε-Greedy

```python
EPSILON         = 0.10    # explore 10% of the time
MIN_PULLS_PER_ARM = 2     # show each arm at least 2 times before trusting predictions
```

### Step-by-step

1. **Warmup** — if any active arm has been shown fewer than 2 times total, pick
   one of those under-explored arms at random. This ensures every arm gets at
   least a couple of data points before we start comparing predictions.

2. **Explore (10%)** — with probability ε = 0.10, pick a completely random arm.
   This ensures we keep discovering if an arm has improved or if a previously
   bad arm works well for a new visitor type.

3. **Exploit (90%)** — compute the predicted reward for every active arm using
   the visitor's feature vector, and pick the one with the highest prediction.

### Why epsilon-greedy?

It's the simplest effective exploration strategy. More sophisticated approaches
(UCB confidence bounds, Thompson sampling) exist but epsilon-greedy is easy to
understand, implement, and explain in a report — and it works well in practice.

---

## Reward Signal

Currently binary:

| Condition | Reward |
|---|---|
| `session.cta_clicked == True` | `1.0` |
| `session.cta_clicked == False` | `0.0` |

Rewards are only recorded for sessions where the bandit ran (`visit_number >= 2`).

---

## Models

### `BanditArm`

| Field | Type | Description |
|---|---|---|
| `arm_id` | `CharField(unique)` | Machine-readable key, e.g. `"highlight_plan_2"` |
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
| `context_json` | `JSONField` | Human-readable context snapshot |
| `context_vector` | `JSONField` | The 8-number feature vector used for prediction |
| `arm` | `ForeignKey → BanditArm` | The chosen arm |
| `explore` | `BooleanField` | `True` if random/warmup pick |
| `epsilon` | `FloatField` | Epsilon at decision time |
| `reward` | `FloatField(nullable)` | Filled when session ends (1.0 or 0.0) |
| `created_at` | `DateTimeField` | Auto-set |

### `LinUCBParam`

One row per arm — stores the learned model parameters.

| Field | Type | Description |
|---|---|---|
| `arm` | `OneToOneField → BanditArm` | The arm these parameters belong to |
| `A_matrix` | `JSONField` | 8×8 list of lists — "what visitors this arm has seen" |
| `b_vector` | `JSONField` | 8-element list — "what worked" |
| `n` | `IntegerField` | Total number of times this arm has been shown |
| `updated_at` | `DateTimeField` | Auto-updated on save |

### `BanditArmStat` (deprecated)

Kept for backward compatibility. The old bucket-based bandit stored per-bucket
per-arm mean reward here. No longer written to by the linear bandit.

---

## Starter Arms (23)

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

| Category | arm_id | What it does |
|---|---|---|
| **Control** | `no_change` | Baseline — no layout changes |
| **Hero** | `hero_compact` | Smaller hero, hides subtitle & trust badges |
| | `hero_cta_emphasis` | Pulsing CTA button (amber glow animation) |
| **Services** | `services_compact` | Compact — hides descriptions, shows top 3 |
| | `featured_service_1` | Highlight service card 1 |
| | `featured_service_2` | Highlight service card 2 |
| | `featured_service_3` | Highlight service card 3 |
| **Pricing** | `pricing_compact` | Compact — fewer features shown |
| | `highlight_plan_1` | Highlight plan 1 (cheapest) |
| | `highlight_plan_2` | Highlight plan 2 (middle) |
| | `highlight_plan_3` | Highlight plan 3 (premium) |
| **Testimonials** | `testimonials_single` | Single card spotlight (1 per page) |
| | `testimonials_compact` | Compact — smaller quotes, no subheading |
| **FAQ** | `faq_compact` | Compact — smaller text |
| | `faq_top3` | Show only top 3, "View All" button |
| **About** | `about_compact` | Compact — hides stats & extra text |
| **Locations** | `locations_compact` | Compact — hides addresses & hours |
| | `hide_locations` | Hidden entirely |
| **Contact** | `contact_compact` | Compact — hides details, form only |
| **Promote** | `promote_pricing` | Move pricing right below trust bar |
| | `promote_services` | Move services right below trust bar |
| | `promote_testimonials` | Move testimonials right below trust bar |
| | `promote_contact` | Move contact right below trust bar |

With `MIN_PULLS_PER_ARM = 2`, warmup requires 46 visits (2 × 23 arms), after
which the model starts exploiting what it has learned.

---

## Utility Functions

All in `landing/bandit_utils.py`. Uses numpy for all linear algebra.

### `build_context(visitor, request) → (context_dict, feature_vector)`

Extracts the 8-number feature vector from the visitor and request:

- `is_mobile` — parsed from User-Agent header
- Five intent scores — from the visitor's most recent ended session
- `visit_number_norm` — normalised visit count
- `bias` — always 1.0

Also returns a human-readable `context_dict` for logging.

### `choose_arm(feature_vector, epsilon=0.10) → (arm, explore_flag)`

Epsilon-greedy selection:

1. Warmup → forced exploration of under-pulled arms
2. ε probability → random arm
3. Otherwise → arm with highest `predicted_reward = dot(features, weights)`

Auto-creates `LinUCBParam` rows for any arm missing one.

### `update_stats(arm, feature_vector, reward)`

Called when a session ends. Updates the chosen arm's `LinUCBParam`:

```python
x = np.array(feature_vector)
A = np.array(param.A_matrix)
b = np.array(param.b_vector)

A = A + np.outer(x, x)       # "what I've seen" += this visitor's feature combos
b = b + reward * x            # "what worked"   += features × reward

param.A_matrix = A.tolist()   # convert back to JSON-safe lists
param.b_vector = b.tolist()
param.n += 1
param.save()
```

### `make_initial_A()` / `make_initial_b()`

Return the starting values for a new arm's parameters:
- `A`: 8×8 identity matrix × LAMBDA_REG
- `b`: 8 zeros

### `_predict(A_list, b_list, x_list) → float`

Computes `weights = np.linalg.solve(A, b)` then `return weights @ x`.

### Configuration Constants

| Constant | Value | Description |
|---|---|---|
| `EPSILON` | `0.10` | Exploration probability |
| `MIN_PULLS_PER_ARM` | `2` | Warmup pulls per arm before ε-greedy kicks in |
| `LAMBDA_REG` | `1.0` | Regularisation — scales the identity starting value of A |
| `FEATURE_DIM` | `8` | Length of the feature vector |

---

## Frontend Integration

The `/accept-cookies/` response includes:

```json
{
  "session_id": "...",
  "visitor_id": "...",
  "is_new": false,
  "visit_number": 3,
  "arm_id": "highlight_plan_2",
  "page_config": {
    "compact": [],
    "hide": [],
    "promote": null,
    "variants": { "pricing": "highlight-plan-2" }
  }
}
```

`ui.js` calls `window.applyPageConfig(data.page_config)` which applies
CSS classes to page sections:

- `compact: [...]` → adds `is-compact` class to those sections
- `hide: [...]` → adds `is-hidden` class (display: none)
- `promote: "id"` → adds `section-promoted` class (CSS order: 3, moves below trust bar)
- `variants: {id: class}` → sets the variant CSS class on the section

---

## Management Commands

### `seed_bandit_arms`

```bash
python manage.py seed_bandit_arms          # insert new arms (skip existing)
python manage.py seed_bandit_arms --reset  # delete all arms first, then insert
```

---

## File Map

| File | Contents |
|---|---|
| `landing/models.py` | `BanditArm`, `BanditDecision`, `LinUCBParam` + `Session.visit_number` |
| `landing/bandit_utils.py` | `build_context`, `choose_arm`, `update_stats`, `_predict`, numpy helpers |
| `landing/views.py` | Bandit logic in `accept_cookies` and `end_session` views |
| `landing/admin.py` | Admin classes for all bandit models |
| `landing/management/commands/seed_bandit_arms.py` | Seed command for starter arms |
| `static/landing/ui.js` | `applyPageConfig()` + call site in `startTracking()` |
