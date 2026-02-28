# ui.js — UI Interactions & Cookie Consent

> `static/landing/ui.js`

Pure vanilla JS (no dependencies) that powers all interactive UI behaviour on the SparkleWash landing page — navigation, carousel, accordion, pricing toggle, compact-mode expansion, cookie consent, and section variant helpers for the bandit/AI system.

---

## Initialisation

Everything runs inside a single IIFE. On `DOMContentLoaded` the following init functions fire in order:

| # | Function | What it does |
|---|---|---|
| 1 | `initStickyHeader()` | Toggles `.scrolled` class on `#site-header` when `scrollY > 10` (adds box-shadow) |
| 2 | `initNavToggle()` | Mobile hamburger menu — toggles `aria-expanded` and `.open` on `#main-nav` |
| 3 | `initTestimonialCarousel()` | Paginated carousel (3 cards/page default, 1 in `testimonials-single` mode). Prev/next buttons + dot navigation. A `MutationObserver` re-renders when the section's class list changes (variant swap). |
| 4 | `initPricingToggle()` | Monthly ↔ Annual toggle via `aria-checked` on `.toggle-switch`. Swaps `hidden` on `.monthly-price` / `.annual-price` elements. |
| 5 | `initReadMore()` | About section "Read more" button. Toggles `compact--expanded` on the parent `.section` and shows/hides `#about-more`. |
| 6 | `initCompactReadMore()` | Generic handler for all `.compact-read-more` buttons. Adds `compact--expanded` to the parent section. |
| 7 | `initFAQ()` | Handles the "View All FAQs" button in `faq-compact-top3` mode — adds `.faq--expanded`. |
| 8 | `initPlanHighlight()` | Exposes `window.setHighlightPlan(n)` to add `highlight-plan-N` to the pricing section. |
| 9 | `initSmoothScroll()` | All `href="#…"` links get smooth scroll behaviour (fallback for older browsers). |
| 10 | `initCookieConsent()` | Cookie consent modal — see below. |

---

## Cookie Consent Flow

```
Page loads
    │
    ├── sw_cookie_consent cookie exists?
    │       │
    │      YES → remove modal, call startTracking()
    │       │
    │      NO  → show modal, lock body scroll, focus trap
    │              │
    │              ├── [Accept] → set sw_cookie_consent cookie (1 yr)
    │              │               remove modal, call startTracking()
    │              │
    │              └── [Decline] → remove modal (no cookie set)
    │                               tracking does NOT start
    │                               modal reappears next page load
```

### `startTracking()` (async)

1. Reads `csrftoken` from cookies.
2. `POST /accept-cookies/` with CSRF header.
3. Server creates (or finds) a `Visitor`, creates a new `Session`, returns `{ session_id }`.
4. Calls `window.SparkleTracker._init(data.session_id)` to start the event tracker.

If the fetch fails, an error is logged and tracking silently does not start.

---

## Section Variant Helpers

These global functions let the backend / AI system change section appearance at runtime without a page reload.

### `window.setVariant(sectionId, variantClass)`

Removes all known variant classes from the element, then adds the given one.

```js
setVariant('hero', 'hero-cta-emphasis');
setVariant('services', 'featured-service-2');
setVariant('pricing', '');  // reset to default
```

**Known variant classes removed automatically:**
`hero-compact`, `hero-cta-emphasis`, `is-compact`, `is-hidden`, `section-promoted`, `featured-service-1/2/3`, `highlight-plan-1/2/3`, `testimonials-single`, `faq-compact-top3`

### `window.toggleCompact(sectionId, on)`

Adds or removes `is-compact` on a section.

```js
toggleCompact('about', true);   // compact mode on
toggleCompact('about', false);  // compact mode off
```

### `window.hideSection(sectionId)` / `window.showSection(sectionId)`

Adds/removes `is-hidden` (`display: none !important`).

```js
hideSection('locations');
showSection('locations');
```

### `window.promoteSection(sectionId)` / `window.demoteSection(sectionId)`

Adds/removes `section-promoted` (CSS `order: 3`) to visually move a section right below the trust bar.

```js
promoteSection('pricing');  // pricing moves up
demoteSection('pricing');   // pricing returns to default order
```

### `window.applyPageConfig(cfg)`

Batch-apply a full configuration object from the backend:

```js
applyPageConfig({
  compact:  ['about', 'faq'],           // toggleCompact(..., true)
  hide:     ['locations'],               // hideSection(...)
  promote:  'pricing',                   // promoteSection(...)
  variants: {                            // setVariant(...)
    hero:    'hero-cta-emphasis',
    pricing: 'highlight-plan-2'
  }
});
```

All fields are optional. This is the primary interface the AI recommendation system will use to personalise the page for each visitor.

---

## Utility Helpers

```js
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
```

Used internally — not exposed globally.
