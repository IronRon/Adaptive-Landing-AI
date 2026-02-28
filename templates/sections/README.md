# Section Templates

This directory contains the **11 Django template partials** that make up the SparkleWash landing page. Each section is a self-contained HTML fragment included by `landing_page.html`.

---

## Common Patterns

Every section follows the same conventions:

| Convention | Example | Purpose |
|---|---|---|
| `data-section="<id>"` | `data-section="hero"` | Identifies the section for the backend / AI |
| `data-track="<id>"` | `data-track="hero"` | Marks the section for **visibility / dwell** tracking (IntersectionObserver) |
| `data-track-click="<name>"` | `data-track-click="hero-cta-primary"` | Marks interactive elements for **click / hover** tracking |
| Django variant variable | `{{ hero_variant\|default:'' }}` | Injects a CSS class string from the server so the bandit can change a section's appearance |
| `.section` base class | `class="section hero ..."` | Provides consistent vertical padding |
| `id="<id>"` | `id="hero"` | Anchor-link target and JS lookup key |

### Data-Attribute Summary

```
data-track          → triggers section_view + section_dwell events (tracking.js)
data-track-click    → triggers click + hover events (tracking.js)
data-section        → read by tracking.js via sectionOf() to tag events
```

---

## Sections at a Glance

| # | File | Section ID | Django Variant Var | Description |
|---|---|---|---|---|
| 1 | `header.html` | `site-header` | — | Sticky nav bar with anchor links and mobile toggle |
| 2 | `hero.html` | `hero` | `hero_variant` | Headline, CTAs, trust badges |
| 3 | `trust_bar.html` | `trust-bar` | `trust_variant` | Social proof badges (ratings, stats) |
| 4 | `services.html` | `services` | `services_variant` | 6-card service grid |
| 5 | `pricing.html` | `pricing` | `pricing_variant` | 3 membership plans with monthly/annual toggle |
| 6 | `testimonials.html` | `testimonials` | `testimonials_variant` | 6-card carousel with prev/next/dots |
| 7 | `about.html` | `about` | `about_variant` | Company story with stats sidebar |
| 8 | `locations.html` | `locations` | `locations_variant` | 3 location cards with address + hours |
| 9 | `faq.html` | `faq` | `faq_variant` | 8 accordion items (`<details>` based) |
| 10 | `contact.html` | `contact` | `contact_variant` | Contact form + info panel |
| 11 | `footer.html` | — | — | Brand tagline, nav columns, copyright |

---

## Variant Classes

The bandit / AI system can inject variant classes via the Django template variable. These classes change the visual presentation of a section **without altering the HTML**.

### Global Variants (any section)

| Class | Effect |
|---|---|
| `is-compact` | Reduced padding, hides secondary content (descriptions, stats, details). Shows a "Read more" button to expand. |
| `is-hidden` | `display: none !important` — section disappears entirely. |
| `section-promoted` | CSS `order: 3` — moves the section visually right below the trust bar. |

### Hero (`hero.html`)

| Class | Effect |
|---|---|
| `hero-compact` | Shorter height (360 px), hides subtitle and trust badges. |
| `hero-cta-emphasis` | Primary CTA grows larger with a pulsing amber glow animation. |

### Services (`services.html`)

| Class | Effect |
|---|---|
| `is-compact` | Hides descriptions; only shows first 3 cards (rest revealed via "Show all services"). |
| `featured-service-1` | Highlights service card `data-service="1"` with accent border + scale. |
| `featured-service-2` | Highlights service card `data-service="2"`. |
| `featured-service-3` | Highlights service card `data-service="3"`. |

### Pricing (`pricing.html`)

| Class | Effect |
|---|---|
| `is-compact` | Truncates feature lists to first 3 items, reduces card padding. |
| `highlight-plan-1` | Highlights plan `data-plan="1"` with accent border + glow + scale. |
| `highlight-plan-2` | Highlights plan `data-plan="2"`. |
| `highlight-plan-3` | Highlights plan `data-plan="3"`. |

### Testimonials (`testimonials.html`)

| Class | Effect |
|---|---|
| `is-compact` | Smaller text, hides subheading, reduced card padding. |
| `testimonials-single` | Carousel shows **1 large card** at a time instead of 3. |

### About (`about.html`)

| Class | Effect |
|---|---|
| `is-compact` | Hides stats sidebar and "about-more" text. "Read more" button expands them back. |

### Locations (`locations.html`)

| Class | Effect |
|---|---|
| `is-compact` | Hides address and hours on each card. "Show full details" button expands them. |

### FAQ (`faq.html`)

| Class | Effect |
|---|---|
| `is-compact` | Smaller text and tighter padding. |
| `faq-compact-top3` | Shows only the first 3 FAQs. Items 4–8 have `.faq-item--extra` and are hidden until "View All FAQs" is clicked. |

### Contact (`contact.html`)

| Class | Effect |
|---|---|
| `is-compact` | Hides contact details (phone, email, address). "Show contact details" button reveals them. |

---

## Compact Mode Mechanics

Several sections share the same expand pattern:

1. CSS hides content when `.is-compact` is present.
2. A `<button class="compact-read-more">` is rendered in the template but only visible in compact mode (CSS controlled).
3. Clicking the button adds `.compact--expanded` to the section, which CSS uses to reveal hidden content and hide the button.
4. JS handler lives in `ui.js → initCompactReadMore()`.

---

## Tracked Elements per Section

| Section | `data-track-click` values |
|---|---|
| Header | `logo`, `nav-toggle`, `nav-services`, `nav-pricing`, `nav-reviews`, `nav-faq`, `nav-contact`, `nav-cta` |
| Hero | `hero-cta-primary`, `hero-cta-secondary` |
| Trust Bar | `trust-cta` |
| Services | `service-1` … `service-6`, `services-read-more`, `services-cta` |
| Pricing | `pricing-toggle`, `pricing-toggle-switch`, `plan-1`, `plan-2`, `plan-3`, `plan-1-cta`, `plan-2-cta`, `plan-3-cta` |
| Testimonials | `testimonial-1` … `testimonial-6`, `testimonials-cta` |
| About | `about-read-more`, `about-cta` |
| Locations | `location-1` … `location-3`, `locations-read-more`, `locations-cta` |
| FAQ | `faq-1` … `faq-8`, `faq-view-all`, `faq-cta` |
| Contact | `contact-read-more`, `contact-submit` |
| Footer | *(none — no tracked elements)* |

---

## Adding a New Section

1. Create `templates/sections/newsection.html` following the same pattern.
2. Add `data-section`, `data-track`, and `id` attributes on the root `<section>`.
3. Add `data-track-click` on every interactive element you want tracked.
4. Accept a `{{ newsection_variant|default:'' }}` template variable.
5. Add corresponding CSS in `static/landing/styles.css`.
6. Include the partial in `templates/landing/landing_page.html`.
