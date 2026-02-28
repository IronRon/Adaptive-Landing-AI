# styles.css — Landing Page Styles

> `static/landing/styles.css` — 1 055 lines

Single-file stylesheet for the SparkleWash landing page. CSS-variable driven, mobile-first with a 768 px breakpoint. No preprocessor — plain CSS only.

---

## File Structure

| Lines | Section | Description |
|---|---|---|
| 1–55 | **0. Design Tokens** | `:root` custom properties — palette, typography scale, spacing scale, layout, shadows, transitions |
| 56–78 | **1. Reset & Base** | Box-sizing reset, smooth scroll, body typography, link/button/list resets, focus ring |
| 79–114 | **2. Utility** | `.container` (max 1200 px), `.hide-mobile`, `.section` (vertical padding), `.section-heading`, `.section-subheading`, buttons (`.btn--primary/outline/text/small/lg/block/accent`), `.badge` |
| 163–260 | **3. Header** | Sticky header with glassmorphism, logo, hamburger animation, full-screen mobile nav, desktop inline nav |
| 265–330 | **4. Hero** | Gradient background, clamp-sized title, CTA row, trust badges, **variant styles** |
| 332–360 | **5. Trust Bar** | Flexbox badge list |
| 362–420 | **6. Services** | Auto-fill card grid, hover lift, **variant styles** (compact, featured-service) |
| 422–545 | **7. Pricing** | Toggle switch, plan cards, popular tag badge, feature list with check/dash icons, **variant styles** (compact, highlight-plan) |
| 547–655 | **8. Testimonials** | Carousel grid (3-up default), card show/hide via `.carousel-visible`, prev/next/dots, **variant styles** (single, compact), mobile stack |
| 657–718 | **9. FAQ** | Accordion via `<details>`, chevron rotation, **variant styles** (compact, compact-top3 with "View All") |
| 720–780 | **10. About** | 2-column grid (text + stats), read-more expand, **variant styles** (compact) |
| 782–820 | **11. Locations** | Auto-fit card grid, **variant styles** (compact) |
| 822–880 | **12. Contact** | 2-column grid (info + form), form field focus ring, **variant styles** (compact) |
| 882–930 | **13. Footer** | Dark background, 4-column grid, link columns, copyright bar |
| 932–957 | **14. Compact Density** | Global `.section.is-compact` padding, `.compact-read-more` visibility rules, `.section-cta` |
| 959–978 | **15. Responsive** | `@media (max-width: 767px)` overrides: smaller hero, stacked pricing, centred stats |
| 980–998 | **16. Pricing Guarantee** | Guarantee line below pricing grid |
| 1000–1005 | **17. Hide Section** | `.section.is-hidden { display: none !important }` |
| 1007–1030 | **18. Section Reorder** | `.page-sections` flexbox column with `order` values; `.section-promoted` gets `order: 3` |
| 1032–1055 | **19. Cookie Consent Modal** | Full-screen overlay with blur, centred box, focus trap, body scroll lock |

---

## Design Tokens (`:root`)

### Palette

| Variable | Value | Usage |
|---|---|---|
| `--clr-primary` | `#0e7490` (teal-600) | Links, nav hover, form focus, accent outlines |
| `--clr-primary-dark` | `#0c5e74` | Link hover |
| `--clr-primary-light` | `#67e8f9` | *(reserved)* |
| `--clr-accent` | `#f59e0b` (amber-500) | CTAs, badges, popular tag, focus ring, featured highlights |
| `--clr-accent-hover` | `#d97706` | CTA hover state |
| `--clr-success` | `#22c55e` | Checkmark icons, guarantee badge |
| `--clr-bg` | `#f8fafc` | Page background, alternating section background |
| `--clr-surface` | `#ffffff` | Cards, form, header |
| `--clr-text` | `#1e293b` | Body copy |
| `--clr-text-muted` | `#64748b` | Secondary copy, labels |
| `--clr-border` | `#e2e8f0` | Card borders, dividers |
| `--clr-hero-bg` | `linear-gradient(135deg, #0e7490, #065f73)` | Hero section gradient |

### Typography

| Variable | Value |
|---|---|
| `--ff-sans` | `'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif` |
| `--fs-base` | `1rem` (16 px) |
| `--fs-sm` | `0.875rem` |
| `--fs-lg` | `1.125rem` |
| `--fs-xl` | `1.5rem` |
| `--fs-2xl` | `2rem` |
| `--fs-3xl` | `2.75rem` |
| `--fs-4xl` | `3.5rem` |

### Spacing Scale

`--space-xs` (0.25rem) → `--space-sm` (0.5) → `--space-md` (1) → `--space-lg` (1.5) → `--space-xl` (2.5) → `--space-2xl` (4) → `--space-3xl` (6)

### Other

| Variable | Value | Purpose |
|---|---|---|
| `--max-w` | `1200px` | Container max-width |
| `--radius` | `12px` | Default border-radius |
| `--radius-sm` | `8px` | Buttons, inputs |
| `--radius-lg` | `20px` | Modals, plan cards |
| `--shadow-sm/md/lg` | Increasing box-shadow depth | Cards, header scroll, hover effects |
| `--ease` | `cubic-bezier(.4,0,.2,1)` | Default easing curve |
| `--dur` | `250ms` | Default transition duration |

---

## Variant CSS — How the Bandit Changes the Page

The core mechanic: the backend injects a CSS class string into a Django template variable (e.g. `{{ hero_variant }}`). The browser applies matching variant CSS rules. No JavaScript DOM manipulation is needed for the initial render.

### Compact Mode System

```css
/* Global compact padding */
.section.is-compact { padding-block: var(--space-2xl); }

/* "Read more" button — hidden normally, shown in compact */
.compact-read-more                      { display: none; }
.section.is-compact .compact-read-more  { display: inline-flex; }

/* After user clicks "Read more" */
.section.is-compact.compact--expanded .compact-read-more { display: none; }
```

Each section then adds its own compact overrides (hiding descriptions, truncating lists, etc.). The `compact--expanded` class is added by `ui.js` when the user clicks "Read more" — it re-reveals hidden content.

### Section Reorder System

```css
.page-sections              { display: flex; flex-direction: column; }
.page-sections > .section   { order: 10; }   /* default */
.site-header                { order: 0; }
.hero                       { order: 1; }
.trust-bar                  { order: 2; }
.site-footer                { order: 99; }
.section.section-promoted   { order: 3; }     /* right after trust bar */
```

The bandit can promote any section (e.g. pricing) to appear immediately below the trust bar by adding `section-promoted`.

### Hide Section

```css
.section.is-hidden { display: none !important; }
```

---

## Key Animations

| Name | Used By | Effect |
|---|---|---|
| `pulse-glow` | `.hero.hero-cta-emphasis .btn--primary` | 2 s infinite ease-in-out box-shadow pulse (amber glow 0.4 → 0.65 opacity) |

---

## Responsive Breakpoints

| Breakpoint | Behaviour |
|---|---|
| `< 768 px` (default) | Mobile-first: stacked layouts, full-screen nav, single-column pricing/testimonials/carousel, reduced hero height, smaller `--space-3xl` |
| `≥ 768 px` | Desktop: inline nav, multi-column grids for about/contact/footer/pricing/testimonials. `.hide-mobile` becomes visible. |

---

## Button System

| Class | Style |
|---|---|
| `.btn` | Base: inline-flex, rounded, 600 weight, transition |
| `.btn--primary` | Amber background, white text |
| `.btn--outline` | Teal border, transparent bg (inverts on hover) |
| `.btn--text` | Text-only link style with underline on hover |
| `.btn--accent` | Amber bg (alias of primary for semantic use) |
| `.btn--small` | Reduced padding + font-size |
| `.btn--lg` | Larger padding + font-size |
| `.btn--block` | `width: 100%` |

In the hero, `.btn--outline` is overridden to use white border/text against the dark gradient.

---

## Cookie Consent Modal

```css
.cookie-overlay   → fixed fullscreen, z-index 9999, dark backdrop + blur
.cookie-box       → centred white card (max 480 px), shadow-lg
.cookie-actions   → flex row of Accept/Decline buttons
body.cookie-modal-open → overflow: hidden (prevents background scroll)
```
