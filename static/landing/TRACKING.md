# tracking.js — Event Tracking (v3)

> `static/landing/tracking.js`

Client-side behavioural tracker for the SparkleWash adaptive landing page. Captures every meaningful user interaction and batches them to the Django backend for the contextual bandit / personalisation pipeline.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Server-provided `session_id` only** | The tracker never generates its own UUID. `_init(sessionId)` must be called with a value from `POST /accept-cookies/`. This guarantees every event references a real `Session` row in the database. |
| **Batched sends** | Events queue in memory and flush every 5 s, on `visibilitychange` (tab hidden), or on `beforeunload`. Reduces network chatter and survives page closes via `sendBeacon`. |
| **`session_id` at payload top level** | The UUID is sent once per batch, not repeated inside every event object. Saves bandwidth and simplifies the backend parser. |
| **No auto-init** | The IIFE exposes `window.SparkleTracker` but does **not** auto-start. `ui.js → initCookieConsent()` calls `_init()` after cookie consent + server handshake. |

---

## Public API

```js
window.SparkleTracker = {
  _init(serverSessionId),  // Start tracking (called by ui.js)
  track(eventType, data),  // Manually enqueue a custom event
  flush(),                 // Force-send the current queue
  endSession(),            // Flush events then POST /end-session/ (called automatically on unload)
  getSessionId(),          // Returns the active session UUID or null
};
```

### `_init(serverSessionId)`

Called once by `ui.js` after `POST /accept-cookies/` returns a `session_id`. If called without a valid string the tracker logs a warning and does **not** start — all subsequent `track()` calls are silently discarded.

On init the tracker:
1. Stores the session ID in `sessionStorage` (survives soft navigations).
2. Fires a `page_view` event with `{ referrer }`.
3. Wires up all event listeners (clicks, hovers, scroll, visibility, forms).
4. Starts the periodic flush timer.

---

## Event Types

| Event | Trigger | Payload Fields |
|---|---|---|
| `page_view` | Once on init | `referrer` |
| `click` | Click on any `[data-track-click]` element | `element`, `section`, `tag`, `text` (≤ 80 chars), `is_cta` |
| `hover` | Mouse dwell ≥ 200 ms on `[data-track-click]` | `element`, `section`, `duration_ms`, `is_cta` |
| `section_view` | First time a `[data-track]` section enters the viewport (≥ 30 %) | `section` |
| `section_dwell` | Section leaves viewport or page unloads | `section`, `duration_ms`, `read` (bool, ≥ 3 s) |
| `scroll_depth` | User scrolls past 25 / 50 / 75 / 100 % | `depth` (integer) |
| `time_on_page` | Page hidden or unloaded | `seconds` |
| `form_focus` | User focuses an `<input>` / `<textarea>` / `<select>` inside `[data-track]` | `section`, `field` |
| `form_submit` | Form inside `[data-track]` submitted | `section`, `form_id` |

Every event also carries: `type`, `ts` (ISO 8601), `url` (pathname).

---

## Flush / Send Mechanics

```
Queue fills up via track() calls
        │
        ▼
┌───────────────────────────────────┐
│  Flush triggered by:              │
│   • setInterval (5 000 ms)        │
│   • queue.length >= 50            │
│   • visibilitychange → "hidden"   │
│   • beforeunload                  │
└───────────────┬───────────────────┘
                │
                ▼
     Page visible?
     ┌──yes──┐  ┌──no──┐
     │ fetch │  │ sendBeacon │
     │ + keepalive │     │ (fire-and-forget) │
     └───────┘  └────────────┘
```

**Payload shape:**

```json
{
  "session_id": "a1b2c3d4-...",
  "events": [
    { "type": "click", "ts": "2025-...", "url": "/", "element": "hero-cta-primary", ... },
    { "type": "section_dwell", "ts": "2025-...", "url": "/", "section": "pricing", ... }
  ]
}
```

On `fetch` failure the events are pushed **back** onto the queue so they can be retried on the next flush.

---

## End-Session Flow

When the user leaves the page (`visibilitychange → hidden` or `beforeunload`), the tracker performs two actions **in order**:

1. **`flush()`** — sends any remaining queued events to `/track-interactions/`.
2. **`endSession()`** — sends `{ session_id }` to `/end-session/` via `sendBeacon` (or `fetch` with `keepalive`).

The backend then marks the session as ended and computes intent-feature scores from the recorded events (see [README § Session Intent Scoring](../../README.md#session-intent-scoring-post-end-session)).

`endSession()` is **idempotent** — a guard flag (`_sessionEnded`) prevents it from firing more than once per page lifecycle, even though both `visibilitychange` and `beforeunload` can trigger in quick succession.

```
visibilitychange / beforeunload
        │
        ├── flush()        → POST /track-interactions/  (remaining events)
        └── endSession()   → POST /end-session/         (compute scores)
                                ↓
                           Backend sets ended_at, is_active=False
                           Computes price/service/trust/quick_scan scores
                           Saves to Session row
```

---

## Configuration

Constants at the top of the IIFE:

| Key | Default | Description |
|---|---|---|
| `endpoint` | `/track-interactions/` | Backend URL that receives the batch POST |
| `endSessionEndpoint` | `/end-session/` | Backend URL called on page unload to finalise the session |
| `batchInterval` | `5000` | Milliseconds between periodic flushes |
| `maxQueueSize` | `50` | Queue size that triggers an immediate flush |
| `sessionKey` | `sw_session_id` | `sessionStorage` key for the UUID |
| `dwellReadMs` | `3000` | Section dwell ≥ this = `read: true` |
| `hoverMinMs` | `200` | Hovers shorter than this are discarded |
| `debug` | `true` | Enables colour-coded console logs per event |

---

## Debug Console Output

When `CONFIG.debug` is `true`, every event is logged in a colour-coded collapsed group:

- Purple — `page_view`
- Amber — `click`
- Teal — `hover`
- Green — `section_view`
- Cyan — `section_dwell`
- Violet — `scroll_depth`
- Slate — `time_on_page`
- Orange — `form_focus`
- Red — `form_submit`

Flush operations log a summary table of all events being sent.

---

## Helper Functions

| Function | Purpose |
|---|---|
| `isCTA(el)` | Returns `true` if the element is or is inside a `.btn` / `.section-cta` |
| `sectionOf(el)` | Returns the `data-section` value of the nearest ancestor section |
| `getCookie(name)` | Reads a cookie value (used to grab `csrftoken`) |

---

## Data Attributes Used

| Attribute | Placed On | Tracker Behaviour |
|---|---|---|
| `data-track` | `<section>` root | IntersectionObserver watches for visibility → `section_view` / `section_dwell` |
| `data-track-click` | Interactive elements | Delegated click + mouseenter/mouseleave listeners → `click` / `hover` |
| `data-section` | `<section>` root | Read by `sectionOf()` to tag click/hover events with their parent section |
