/* ================================================================
   SparkleWash - Event Tracking  v3
   Tracks all meaningful interactions and sends them to the Django
   backend so the bandit / personalisation system can use the data
   on a revisit.

   IMPORTANT - session lifecycle
   -----------------------------
   The session_id is created SERVER-SIDE by POST /accept-cookies/
   and passed into _init(sessionId).  The tracker never generates
   its own UUID.  If _init is called without a sessionId the
   tracker will not start.

   Data attributes used:
     data-track          - marks a section for visibility / dwell tracking
     data-track-click    - marks an element for click / hover tracking
     data-section        - section identifier (on the <section> wrapper)

   Event types emitted
   -------------------
   page_view       - fired once on load         { referrer }
   click           - any [data-track-click]      { element, section, tag, text, is_cta }
   hover           - mouse dwell on interactive  { element, section, duration_ms, is_cta }
   section_view    - first time section enters   { section }
   section_dwell   - when section leaves / unload{ section, duration_ms, read }
   scroll_depth    - 25 / 50 / 75 / 100 %        { depth }
   time_on_page    - on page hide / unload       { seconds }
   form_focus      - user focuses a field        { section, field }
   form_submit     - form submitted              { section, form_id }

   All events carry: type, ts, url
   The session_id is sent ONCE at the top level of each batch
   payload, not repeated inside every event.

   Events are batched and flushed every 5 s, on visibilitychange,
   and on beforeunload (via sendBeacon).
   ================================================================ */

(function () {
  'use strict';

  /* -- Configuration ---------------------------------------------------- */
  const CONFIG = {
    endpoint:       '/track-interactions/',
    endSessionEndpoint: '/end-session/',
    batchInterval:  5000,         // ms between periodic flushes
    maxQueueSize:   50,           // flush immediately when queue hits this
    sessionKey:     'sw_session_id',
    dwellReadMs:    3000,         // section dwell >= this = classified as "read"
    hoverMinMs:     200,          // ignore micro-hovers below this threshold
    debug:          true,         // set false to silence console output
  };

  /* -- Debug colours per event type ------------------------------------- */
  const DEBUG_STYLES = {
    page_view:     'background:#6366f1;color:#fff;padding:1px 6px;border-radius:3px',
    click:         'background:#f59e0b;color:#fff;padding:1px 6px;border-radius:3px',
    hover:         'background:#14b8a6;color:#fff;padding:1px 6px;border-radius:3px',
    section_view:  'background:#22c55e;color:#fff;padding:1px 6px;border-radius:3px',
    section_dwell: 'background:#0e7490;color:#fff;padding:1px 6px;border-radius:3px',
    scroll_depth:  'background:#8b5cf6;color:#fff;padding:1px 6px;border-radius:3px',
    time_on_page:  'background:#64748b;color:#fff;padding:1px 6px;border-radius:3px',
    form_focus:    'background:#f97316;color:#fff;padding:1px 6px;border-radius:3px',
    form_submit:   'background:#ef4444;color:#fff;padding:1px 6px;border-radius:3px',
  };

  /** Pretty-print a single event to the console (dev only). */
  function debugLog(event) {
    if (!CONFIG.debug) return;
    const style = DEBUG_STYLES[event.type]
      || 'background:#334155;color:#fff;padding:1px 6px;border-radius:3px';
    const { type, ts, url, ...rest } = event;
    console.groupCollapsed(
      '%c ' + type + ' ',
      style,
      '\u00b7',
      Object.entries(rest)
        .map(([k, v]) => k + ': ' + JSON.stringify(v))
        .join('  ')
    );
    console.log('timestamp :', ts);
    console.log('session   :', sessionId);
    console.log('url       :', url);
    if (Object.keys(rest).length) console.table(rest);
    console.groupEnd();
  }

  /* -- State ------------------------------------------------------------- */
  let queue     = [];
  let sessionId = null;   // set by _init() with the server-provided UUID

  /* -- Core: enqueue an event ------------------------------------------- */
  /**
   * Push a new event onto the queue.
   * Events are NOT sent individually -- they are batched and flushed
   * periodically or when the queue reaches CONFIG.maxQueueSize.
   *
   * @param {string} eventType  One of the documented event types.
   * @param {Object} data       Type-specific fields (section, element, ...).
   */
  function track(eventType, data) {
    if (!sessionId) return;  // no session yet -- discard silently

    const event = {
      type: eventType,
      ts:   new Date().toISOString(),
      url:  location.pathname,
      ...data,
    };

    queue.push(event);
    debugLog(event);
    if (queue.length >= CONFIG.maxQueueSize) flush();
  }

  /* -- Flush / Send ----------------------------------------------------- */
  /**
   * Send all queued events to the backend in a single POST.
   *
   * Payload format:
   *   { session_id: "<uuid>", events: [ ...event objects ] }
   *
   * Uses sendBeacon when the page is being hidden (more reliable)
   * and fetch with keepalive otherwise.
   */
  function flush() {
    if (queue.length === 0 || !sessionId) return;
    const payload = queue.splice(0);

    if (CONFIG.debug) {
      console.groupCollapsed(
        '%c FLUSH ',
        'background:#1e293b;color:#fff;padding:1px 6px;border-radius:3px',
        '-- sending', payload.length, 'event(s)'
      );
      console.table(payload.map(function (e) {
        return {
          type:    e.type,
          section: e.section || e.element || '-',
          detail:  e.duration_ms != null ? e.duration_ms + ' ms'
                 : e.depth       != null ? e.depth + '%'
                 : e.seconds     != null ? e.seconds + ' s'
                 : e.text        || e.field || '-',
          is_cta:  e.is_cta != null ? e.is_cta : '-',
          ts:      e.ts,
        };
      }));
      console.log('Full payload:', JSON.parse(JSON.stringify(payload)));
      console.groupEnd();
    }

    // Build the body -- session_id at the top level, events as array
    var body = JSON.stringify({ session_id: sessionId, events: payload });

    var csrfToken = getCookie('csrftoken');
    var headers   = { 'Content-Type': 'application/json' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;

    if (navigator.sendBeacon && document.visibilityState === 'hidden') {
      // sendBeacon is fire-and-forget, ideal for page unload
      var blob = new Blob([body], { type: 'application/json' });
      navigator.sendBeacon(CONFIG.endpoint, blob);
    } else {
      fetch(CONFIG.endpoint, {
        method:    'POST',
        headers:   headers,
        body:      body,
        keepalive: true,
      }).catch(function () {
        // Put events back on failure so data is not lost
        queue.unshift.apply(queue, payload);
      });
    }
  }

  /** Read a cookie value by name. */
  function getCookie(name) {
    var match = document.cookie.match(
      new RegExp('(^| )' + name + '=([^;]+)')
    );
    return match ? match[2] : '';
  }

  /* -- Helpers ---------------------------------------------------------- */

  /** Return true if the element is (or is inside) a .btn / .section-cta. */
  function isCTA(el) {
    return el.classList.contains('btn')
      || el.closest('.btn') !== null
      || el.closest('.section-cta') !== null;
  }

  /** Return the data-section value of the nearest ancestor section. */
  function sectionOf(el) {
    var s = el.closest('[data-section]');
    return s ? s.getAttribute('data-section') : null;
  }

  /* ================================================================
     1. CLICK TRACKING
     Fires on every [data-track-click] element.
     is_cta = true if the element is (or is inside) a .btn / .section-cta
     ================================================================ */
  function initClickTracking() {
    document.addEventListener('click', function (e) {
      var el = e.target.closest('[data-track-click]');
      if (!el) return;

      track('click', {
        element: el.getAttribute('data-track-click'),
        section: sectionOf(el),
        tag:     el.tagName.toLowerCase(),
        text:    (el.textContent || '').trim().slice(0, 80),
        is_cta:  isCTA(el),
      });
    });
  }

  /* ================================================================
     2. HOVER TRACKING
     Records how long the cursor rests on any [data-track-click] element.
     Very short hovers (< CONFIG.hoverMinMs) are discarded as noise.
     is_cta flag helps the backend weigh intent signals.
     ================================================================ */
  function initHoverTracking() {
    var enterTimes = new WeakMap();

    document.addEventListener('mouseenter', function (e) {
      var el = e.target.closest('[data-track-click]');
      if (el) enterTimes.set(el, Date.now());
    }, true);

    document.addEventListener('mouseleave', function (e) {
      var el = e.target.closest('[data-track-click]');
      if (!el) return;
      var entered = enterTimes.get(el);
      if (!entered) return;

      var duration_ms = Date.now() - entered;
      enterTimes.delete(el);

      if (duration_ms < CONFIG.hoverMinMs) return; // discard micro-hovers

      track('hover', {
        element:     el.getAttribute('data-track-click'),
        section:     sectionOf(el),
        duration_ms: duration_ms,
        is_cta:      isCTA(el),
      });
    }, true);
  }

  /* ================================================================
     3. SECTION VISIBILITY + DWELL TIME
     section_view  - fired once the first time a section enters viewport
     section_dwell - fired when the section leaves (or on page unload)
                     duration_ms = total time the section was on-screen
                     read = duration_ms >= CONFIG.dwellReadMs (3 s default)
     ================================================================ */
  function initSectionTracking() {
    var sections = document.querySelectorAll('[data-track]');
    if (!sections.length) return;

    var firstSeen   = new Set();          // sections seen at least once
    var entryTimes  = new Map();          // section id -> timestamp entered viewport
    var accumulated = new Map();          // section id -> total ms visible

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var id = entry.target.getAttribute('data-track')
              || entry.target.getAttribute('data-section')
              || entry.target.id;
        if (!id) return;

        if (entry.isIntersecting) {
          // Section scrolled into view
          if (!firstSeen.has(id)) {
            firstSeen.add(id);
            track('section_view', { section: id });
          }
          entryTimes.set(id, Date.now());

        } else {
          // Section scrolled out of view
          var entered = entryTimes.get(id);
          if (entered == null) return;

          var elapsed = Date.now() - entered;
          entryTimes.delete(id);

          var total = (accumulated.get(id) || 0) + elapsed;
          accumulated.set(id, total);

          track('section_dwell', {
            section:     id,
            duration_ms: total,
            read:        total >= CONFIG.dwellReadMs,
          });
        }
      });
    }, { threshold: 0.3 });   // 30 % visible counts as "in view"

    sections.forEach(function (s) { observer.observe(s); });

    // On page unload, flush dwell for any currently-visible sections
    function flushActiveDwells() {
      entryTimes.forEach(function (entered, id) {
        var elapsed = Date.now() - entered;
        var total   = (accumulated.get(id) || 0) + elapsed;
        track('section_dwell', {
          section:     id,
          duration_ms: total,
          read:        total >= CONFIG.dwellReadMs,
        });
      });
      entryTimes.clear();
    }

    window.addEventListener('beforeunload', flushActiveDwells);
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') flushActiveDwells();
    });
  }

  /* ================================================================
     4. SCROLL DEPTH
     Fires once at 25 / 50 / 75 / 100 % of page height.
     ================================================================ */
  function initScrollDepth() {
    var milestones = [25, 50, 75, 100];
    var reached    = new Set();

    window.addEventListener('scroll', function () {
      var total = document.documentElement.scrollHeight - window.innerHeight;
      if (total <= 0) return;
      var pct = Math.round((window.scrollY / total) * 100);

      milestones.forEach(function (m) {
        if (pct >= m && !reached.has(m)) {
          reached.add(m);
          track('scroll_depth', { depth: m });
        }
      });
    }, { passive: true });
  }

  /* ================================================================
     5. TIME ON PAGE
     Total active time, emitted on page hide / unload.
     ================================================================ */
  function initTimeOnPage() {
    var startedAt = Date.now();

    function emitTimeOnPage() {
      track('time_on_page', {
        seconds: Math.round((Date.now() - startedAt) / 1000),
      });
    }

    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') emitTimeOnPage();
    });
    window.addEventListener('beforeunload', emitTimeOnPage);
  }

  /* ================================================================
     6. FORM TRACKING
     Tracks field focus (engagement signal) and submission.
     ================================================================ */
  function initFormTracking() {
    document.addEventListener('submit', function (e) {
      var form = e.target.closest('[data-track]');
      if (!form) return;
      track('form_submit', {
        section: form.getAttribute('data-track'),
        form_id: form.id || null,
      });
    });

    document.addEventListener('focusin', function (e) {
      if (!e.target.matches('input, textarea, select')) return;
      var form = e.target.closest('[data-track]');
      if (!form) return;
      track('form_focus', {
        section: form.getAttribute('data-track'),
        field:   e.target.name || e.target.id || null,
      });
    });
  }

  /* ================================================================
     7. BATCH TIMER + UNLOAD HOOKS
     ================================================================ */
  function startBatchTimer() {
    setInterval(flush, CONFIG.batchInterval);
    window.addEventListener('beforeunload', flush);
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') flush();
    });
  }

  /* ================================================================
     8. END SESSION
     Flushes all remaining events, then signals the backend to close
     the session and compute intent scores.
     Uses navigator.sendBeacon (fire-and-forget) so it survives
     page unload; falls back to fetch with keepalive.
     ================================================================ */
  var _sessionEnded = false;

  function endSession() {
    if (!sessionId || _sessionEnded) return;
    _sessionEnded = true;

    // 1. Flush any remaining queued events first
    flush();

    // 2. Send end-session signal
    var body = JSON.stringify({ session_id: sessionId });

    if (CONFIG.debug) {
      console.log(
        '%c END-SESSION ',
        'background:#dc2626;color:#fff;padding:2px 8px;border-radius:3px',
        'Closing session', sessionId
      );
    }

    if (navigator.sendBeacon) {
      var blob = new Blob([body], { type: 'application/json' });
      navigator.sendBeacon(CONFIG.endSessionEndpoint, blob);
    } else {
      fetch(CONFIG.endSessionEndpoint, {
        method:    'POST',
        headers:   { 'Content-Type': 'application/json' },
        body:      body,
        keepalive: true,
      }).catch(function () { /* best effort */ });
    }
  }

  /* Hook end-session into page lifecycle events */
  function initEndSessionHooks() {
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') endSession();
    });
    window.addEventListener('beforeunload', endSession);
  }

  /* -- Public API ------------------------------------------------------- */
  var _initialised = false;

  /**
   * Initialise the tracker with a server-provided session ID.
   *
   * Called by ui.js after POST /accept-cookies/ returns the session UUID.
   * If no sessionId is provided the tracker will NOT start (events would
   * have nowhere to go).
   *
   * @param {string} serverSessionId  UUID returned by /accept-cookies/.
   */
  function _init(serverSessionId) {
    if (_initialised) return;

    // Require a valid session ID from the server
    if (!serverSessionId) {
      if (CONFIG.debug) {
        console.warn(
          '%c TRACKER ',
          'background:#ef4444;color:#fff;padding:2px 8px;border-radius:3px',
          'No session_id provided -- tracking will not start.'
        );
      }
      return;
    }

    _initialised = true;
    sessionId = serverSessionId;

    // Persist in sessionStorage so the value survives soft navigations
    // (not used for cross-page-load persistence -- a new session is
    // created on every page load via /accept-cookies/).
    sessionStorage.setItem(CONFIG.sessionKey, sessionId);

    if (CONFIG.debug) {
      console.log(
        '%c TRACKER ',
        'background:#22c55e;color:#fff;padding:2px 8px;border-radius:3px',
        'Tracking started.  session_id =', sessionId
      );
    }

    // Fire the initial page_view event
    track('page_view', { referrer: document.referrer || null });

    // Wire up all event listeners
    initClickTracking();
    initHoverTracking();
    initSectionTracking();
    initScrollDepth();
    initTimeOnPage();
    initFormTracking();
    startBatchTimer();
    initEndSessionHooks();
  }

  /* Expose a minimal public API on the window object */
  window.SparkleTracker = {
    track:        track,
    flush:        flush,
    endSession:   endSession,
    getSessionId: function () { return sessionId; },
    _init:        _init,
  };

  /*
   * NOTE: auto-init is intentionally removed.
   * The tracker MUST be started by ui.js (initCookieConsent) which
   * calls /accept-cookies/ first to obtain a server session_id and
   * then calls SparkleTracker._init(sessionId).
   */

})();
