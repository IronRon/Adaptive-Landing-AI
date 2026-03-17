# Contextual Multi-Armed Bandit (Combinational Slate Model)

A **linear contextual bandit** that picks a **slate of up to K=3 compatible
page-layout arms per returning visit**. Each arm still learns independently via
ridge regression on a continuous feature vector (same mathematics), while a new
slate-selection layer handles compatibility and merged page configuration.

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

3. We rank arms by predicted reward and greedily build a slate of up to 3
   **non-conflicting** arms.

4. **90% of the time** we keep the greedy slate (exploit). **10% of the time**
   we explore by replacing one slate slot with a random valid non-conflicting
   arm.

5. When the visitor leaves, reward is still binary (CTA clicked or not). The
   reward is session-level (full-bandit), but each chosen arm is updated only
   if the visitor actually observed at least one section that arm affects.

That's it. Over many visits the weights converge — each arm learns which
visitor features predict success, and the bandit naturally starts composing
better slates for each visitor type.

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
│       b. choose_slate(feature_vector, K=3)                      │
│          → greedy non-conflicting slate + ε exploration         │
│       c. merge_page_configs(chosen_arms)                        │
│       d. Save BanditDecision row (chosen_arm_ids, merged config)│
│       e. Return { chosen_arms, page_config, explore }           │
│  5. Frontend calls applyPageConfig(page_config)                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  POST /end-session/                                             │
│                                                                 │
│  1. Compute intent scores + cta_clicked as usual                │
│  2. If visit_number >= 2:                                       │
│       a. Find BanditDecision for this session                   │
│       b. If decision.reward already set → return (idempotent)   │
│       c. reward = 1.0 if cta_clicked else 0.0                   │
│       d. observed_sections = DISTINCT Event.section             │
│          where event_type in {section_view, section_dwell}      │
│       e. For each arm_id in decision.chosen_arm_ids:            │
│            - load arm.affected_sections                         │
│            - update_stats only if intersects observed_sections  │
│       f. Save decision.reward and decision.updated_arm_ids       │
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

## Arm Selection Policy: ε-Greedy Slate Selection

```python
EPSILON         = 0.10    # explore 10% of the time
MIN_PULLS_PER_ARM = 2     # show each arm at least 2 times before trusting predictions
```

### Step-by-step

1. **Warmup-aware scoring** — if an arm has fewer than 2 pulls, it receives a
   very high score so it is likely to enter the greedy slate early.

2. **Exploit slate build** — sort arms by predicted score and greedily add arms
   until K=3, skipping any arm that conflicts with already-chosen arms.

3. **Explore (10%)** — with probability ε = 0.10, replace one random slot in
   the current slate with a random valid non-conflicting arm.

4. **Fallback** — if not enough valid arms exist after conflict filtering,
   return fewer than K arms (first visit still uses control/no-change).

### Why epsilon-greedy?

It keeps exploration simple and stable while supporting a combinational slate:
you mostly serve the best-known compatible set, but still inject randomness in
one slot to keep learning.

---

## Slate Conflict Rules

The combinational layer prevents incompatible arm combinations.

Two arms conflict if any of these are true:

1. Same arm (duplicate).
2. Both set the same key in page_config.variants.
3. Both define non-null promote (only one promote action per slate).
4. One hides a section that the other compacts, variants, or promotes.

These checks are implemented by _has_conflict and _conflicts_with_slate.

---

## Merging Multiple Arms Into One page_config

After selecting a slate, arm configs are merged deterministically:

1. compact: union of all compact lists.
2. hide: union of all hide lists.
3. promote: first non-null promote value (conflicts already prevent multiples).
4. variants: merged dictionary (conflicts already prevent same-key collisions).

For deterministic output, compact and hide are converted to sorted lists before
returning JSON to the frontend.

---

## Reward Signal

Currently binary (full-bandit reward at session level):

| Condition | Reward |
|---|---|
| `session.cta_clicked == True` | `1.0` |
| `session.cta_clicked == False` | `0.0` |

Rewards are only recorded for sessions where the bandit ran (visit_number >= 2).

### Observation-gated per-arm updates

Although reward is one scalar per session, each chosen arm is updated only if
the user observed at least one section affected by that arm.

Observed section definition:

- There exists Event with event_type in {section_view, section_dwell}
- and Event.section equals a section in arm.affected_sections.

This avoids rewarding arms for sections never seen by the user.

---

## Models

### `BanditArm`

| Field | Type | Description |
|---|---|---|
| `arm_id` | `CharField(unique)` | Machine-readable key, e.g. `"highlight_plan_2"` |
| `name` | `CharField` | Optional human label |
| `page_config` | `JSONField` | Config dict for `applyPageConfig()` (see shape below) |
| `is_active` | `BooleanField` | Inactive arms are excluded from selection |
| `affected_sections` | `JSONField` | Sections the arm modifies, used for observation-gated updates |
| `created_at` | `DateTimeField` | Auto-set on creation |

### `BanditDecision`

One row per session where the bandit ran (visit ≥ 2).

| Field | Type | Description |
|---|---|---|
| `session` | `OneToOneField → Session` | The session this decision belongs to |
| `visitor` | `ForeignKey → Visitor` | The visitor |
| `context_json` | `JSONField` | Human-readable context snapshot |
| `context_vector` | `JSONField` | The 8-number feature vector used for prediction |
| `arm` | `ForeignKey → BanditArm (nullable)` | Legacy single-arm field |
| `chosen_arm_ids` | `JSONField` | List of arm_id strings in the chosen slate |
| `merged_page_config` | `JSONField` | Final merged config sent to frontend |
| `explore` | `BooleanField` | `True` if random/warmup pick |
| `epsilon` | `FloatField` | Epsilon at decision time |
| `reward` | `FloatField(nullable)` | Filled when session ends (1.0 or 0.0) |
| `updated_arm_ids` | `JSONField` | Arms actually updated after observation gating |
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

With `MIN_PULLS_PER_ARM = 2`, warmup pressure is spread across early visits.
Because each returning visit can update multiple arms from the chosen slate,
coverage is typically reached much faster than a strict one-arm-per-visit
system.

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

### `choose_slate(feature_vector, k=3, epsilon=0.10) → (chosen_arms, explore_flag, predicted_scores)`

Epsilon-greedy combinational selection:

1. Score all active arms (excluding no_change) using the linear model
2. Greedily build up to K non-conflicting arms
3. With probability ε, replace one random slot with a random valid arm
4. Return chosen arms, explore flag, and per-arm predicted scores

Auto-creates LinUCBParam rows for any arm missing one.

### `merge_page_configs(arms) → merged_config`

Merges compact/hide/promote/variants across chosen arms into one deterministic
frontend payload.

### `_has_conflict(arm_a, arm_b)` and `_conflicts_with_slate(arm, slate)`

Conflict guards used during greedy slate construction.

### `update_stats(arm, feature_vector, reward)`

Called when a session ends. Updates one arm's LinUCBParam (used for each
eligible arm in the chosen slate):

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

The /accept-cookies/ response includes:

```json
{
  "session_id": "...",
  "visitor_id": "...",
  "is_new": false,
  "visit_number": 3,
   "chosen_arms": ["highlight_plan_2", "testimonials_single", "faq_compact"],
   "explore": false,
  "page_config": {
      "compact": ["faq"],
    "hide": [],
    "promote": null,
      "variants": {
         "pricing": "highlight-plan-2",
         "testimonials": "testimonials-single"
      }
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

The command also derives and backfills BanditArm.affected_sections from each
arm's page_config (compact/hide/promote/variants).

---

## File Map

| File | Contents |
|---|---|
| `landing/models.py` | `BanditArm`, `BanditDecision`, `LinUCBParam` + `Session.visit_number` |
| `landing/bandit_utils.py` | `build_context`, `choose_slate`, conflict checks, `merge_page_configs`, `update_stats`, `_predict` |
| `landing/views.py` | Bandit logic in `accept_cookies` and `end_session` views |
| `landing/admin.py` | Admin classes for all bandit models |
| `landing/management/commands/seed_bandit_arms.py` | Seed command for starter arms |
| `static/landing/ui.js` | `applyPageConfig()` + call site in `startTracking()` |
