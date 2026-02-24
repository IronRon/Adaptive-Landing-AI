/* ================================================================
   SparkleWash – Event Tracking  v2
   Tracks all meaningful interactions and sends them to the Django
   backend so the bandit / personalisation system can use the data
   on a revisit.

   Data attributes used:
     data-track          – marks a section for visibility / dwell tracking
     data-track-click    – marks an element for click / hover tracking
     data-section        – section identifier (on the <section> wrapper)

   Event types emitted
   ───────────────────
   page_view       – fired once on load         { referrer }
   click           – any [data-track-click]      { element, section, tag, text, is_cta }
   hover           – mouse dwell on interactive  { element, section, duration_ms, is_cta }
   section_view    – first time section enters   { section }
   section_dwell   – when section leaves / unload{ section, duration_ms, read }
   scroll_depth    – 25 / 50 / 75 / 100 %        { depth }
   time_on_page    – on page hide / unload       { seconds }
   form_focus      – user focuses a field        { section, field }
   form_submit     – form submitted              { section, form_id }

   All events carry: type, ts (ISO), session, url
   Events are batched and flushed every 5 s, on visibilitychange, and
   on beforeunload (via sendBeacon).
   ================================================================ */

(function () {
  'use strict';

  /* ── Configuration ─────────────────────────────────────────── */
  const CONFIG = {
    endpoint:       '/track-interactions/',
    batchInterval:  5000,         // ms between periodic flushes
    maxQueueSize:   50,           // flush immediately when queue hits this
    sessionKey:     'sw_session_id',
    dwellReadMs:    3000,         // section dwell ≥ this → classified as "read"
    hoverMinMs:     200,          // ignore micro-hovers below this threshold
    debug:          true,         // set false to silence console output
  };

  /* ── Debug colours per event type ─────────────────────────── */
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

  function debugLog(event) {
    if (!CONFIG.debug) return;
    const style = DEBUG_STYLES[event.type] || 'background:#334155;color:#fff;padding:1px 6px;border-radius:3px';
    const { type, ts, session, url, ...rest } = event;
    console.groupCollapsed(
      '%c ' + type + ' ',
      style,
      '·',
      Object.entries(rest).map(([k, v]) => k + ': ' + JSON.stringify(v)).join('  ')
    );
    console.log('timestamp :', ts);
    console.log('session   :', session);
    console.log('url       :', url);
    if (Object.keys(rest).length) console.table(rest);
    console.groupEnd();
  }

  /* ── State ─────────────────────────────────────────────────── */
  let queue     = [];
  const sessionId = getOrCreateSession();

  /* ── Session ID ────────────────────────────────────────────── */
  function getOrCreateSession() {
    let id = sessionStorage.getItem(CONFIG.sessionKey);
    if (!id) {
      id = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : Date.now().toString(36) + Math.random().toString(36).slice(2);
      sessionStorage.setItem(CONFIG.sessionKey, id);
    }
    return id;
  }

  /* ── Core: enqueue an event ────────────────────────────────── */
  function track(eventType, data) {
    const event = {
      type:    eventType,
      ts:      new Date().toISOString(),
      session: sessionId,
      url:     location.pathname,
      ...data,
    };

    queue.push(event);
    debugLog(event);
    if (queue.length >= CONFIG.maxQueueSize) flush();
  }

  /* ── Flush / Send ──────────────────────────────────────────── */
  function flush() {
    if (queue.length === 0) return;
    const payload   = queue.splice(0);

    if (CONFIG.debug) {
      console.groupCollapsed(
        '%c FLUSH ',
        'background:#1e293b;color:#fff;padding:1px 6px;border-radius:3px',
        '— sending', payload.length, 'event(s)'
      );
      console.table(payload.map(e => ({
        type:        e.type,
        section:     e.section  || e.element || '—',
        detail:      e.duration_ms != null ? e.duration_ms + ' ms'
                   : e.depth     != null   ? e.depth + '%'
                   : e.seconds   != null   ? e.seconds + ' s'
                   : e.text      || e.field || '—',
        is_cta:      e.is_cta   != null ? e.is_cta : '—',
        ts:          e.ts,
      })));
      console.log('Full payload:', JSON.parse(JSON.stringify(payload)));
      console.groupEnd();
    }

    const csrfToken = getCookie('csrftoken');
    const headers   = { 'Content-Type': 'application/json' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;

    if (navigator.sendBeacon && document.visibilityState === 'hidden') {
      const blob = new Blob(
        [JSON.stringify({ events: payload })],
        { type: 'application/json' }
      );
      navigator.sendBeacon(CONFIG.endpoint, blob);
    } else {
      fetch(CONFIG.endpoint, {
        method:    'POST',
        headers,
        body:      JSON.stringify({ events: payload }),
        keepalive: true,
      }).catch(() => {
        // put back on failure so data isn't lost
        queue.unshift(...payload);
      });
    }
  }

  function getCookie(name) {
    const match = document.cookie.match(
      new RegExp('(^| )' + name + '=([^;]+)')
    );
    return match ? match[2] : '';
  }

  /* ── Helpers ───────────────────────────────────────────────── */
  function isCTA(el) {
    return el.classList.contains('btn') ||
           el.closest('.btn') !== null   ||
           el.closest('.section-cta') !== null;
  }

  function sectionOf(el) {
    const s = el.closest('[data-section]');
    return s ? s.getAttribute('data-section') : null;
  }

  /* ================================================================
     1. CLICK TRACKING
     Fires on every [data-track-click] element.
     is_cta = true if the element is (or is inside) a .btn / .section-cta
     ================================================================ */
  function initClickTracking() {
    document.addEventListener('click', e => {
      const el = e.target.closest('[data-track-click]');
      if (!el) return;

      track('click', {
        element:  el.getAttribute('data-track-click'),
        section:  sectionOf(el),
        tag:      el.tagName.toLowerCase(),
        text:     (el.textContent || '').trim().slice(0, 80),
        is_cta:   isCTA(el),
      });
    });
  }

  /* ================================================================
     2. HOVER TRACKING
     Records how long the cursor rests on any [data-track-click] element.
     Very short hovers (<200 ms) are discarded to remove noise.
     is_cta flag helps the backend weigh intent signals.
     ================================================================ */
  function initHoverTracking() {
    // Map from element → timestamp when mouseenter fired
    const enterTimes = new WeakMap();

    document.addEventListener('mouseenter', e => {
      const el = e.target.closest('[data-track-click]');
      if (el) enterTimes.set(el, Date.now());
    }, true);

    document.addEventListener('mouseleave', e => {
      const el = e.target.closest('[data-track-click]');
      if (!el) return;
      const entered = enterTimes.get(el);
      if (!entered) return;

      const duration_ms = Date.now() - entered;
      enterTimes.delete(el);

      if (duration_ms < CONFIG.hoverMinMs) return; // discard micro-hovers

      track('hover', {
        element:     el.getAttribute('data-track-click'),
        section:     sectionOf(el),
        duration_ms,
        is_cta:      isCTA(el),
      });
    }, true);
  }

  /* ================================================================
     3. SECTION VISIBILITY + DWELL TIME
     section_view  – fired once the first time a section enters the viewport
     section_dwell – fired when the section leaves (or on page unload)
                     duration_ms = total time the section was on-screen
                     read = duration_ms >= CONFIG.dwellReadMs (3 s default)
     ================================================================ */
  function initSectionTracking() {
    const sections = document.querySelectorAll('[data-track]');
    if (!sections.length) return;

    const firstSeen   = new Set();          // sections seen at least once
    const entryTimes  = new Map();          // section id → timestamp entered viewport
    const accumulated = new Map();          // section id → total ms visible (for multi-entry)

    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        const id = entry.target.getAttribute('data-track') ||
                   entry.target.getAttribute('data-section') ||
                   entry.target.id;
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
          const entered = entryTimes.get(id);
          if (entered == null) return;

          const elapsed = Date.now() - entered;
          entryTimes.delete(id);

          const total = (accumulated.get(id) || 0) + elapsed;
          accumulated.set(id, total);

          track('section_dwell', {
            section:     id,
            duration_ms: total,
            read:        total >= CONFIG.dwellReadMs,
          });
        }
      });
    }, { threshold: 0.3 });   // 30 % visible counts as "in view"

    sections.forEach(s => observer.observe(s));

    // On page unload, flush dwell for any currently-visible sections
    function flushActiveDwells() {
      entryTimes.forEach((entered, id) => {
        const elapsed = Date.now() - entered;
        const total   = (accumulated.get(id) || 0) + elapsed;
        track('section_dwell', {
          section:     id,
          duration_ms: total,
          read:        total >= CONFIG.dwellReadMs,
        });
      });
      entryTimes.clear();
    }

    window.addEventListener('beforeunload', flushActiveDwells);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flushActiveDwells();
    });
  }

  /* ================================================================
     4. SCROLL DEPTH
     Fires once at 25 / 50 / 75 / 100 % of page height.
     ================================================================ */
  function initScrollDepth() {
    const milestones = [25, 50, 75, 100];
    const reached    = new Set();

    window.addEventListener('scroll', () => {
      const total = document.documentElement.scrollHeight - window.innerHeight;
      if (total <= 0) return;
      const pct = Math.round((window.scrollY / total) * 100);

      milestones.forEach(m => {
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
    const startedAt = Date.now();

    function emitTimeOnPage() {
      track('time_on_page', {
        seconds: Math.round((Date.now() - startedAt) / 1000),
      });
    }

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') emitTimeOnPage();
    });
    window.addEventListener('beforeunload', emitTimeOnPage);
  }

  /* ================================================================
     6. FORM TRACKING
     Tracks field focus (engagement signal) and submission.
     ================================================================ */
  function initFormTracking() {
    document.addEventListener('submit', e => {
      const form = e.target.closest('[data-track]');
      if (!form) return;
      track('form_submit', {
        section: form.getAttribute('data-track'),
        form_id: form.id || null,
      });
    });

    document.addEventListener('focusin', e => {
      if (!e.target.matches('input, textarea, select')) return;
      const form = e.target.closest('[data-track]');
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
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flush();
    });
  }

  /* ── Public API ─────────────────────────────────────────────── */
  window.SparkleTracker = {
    track,
    flush,
    getSessionId: () => sessionId,
  };

  /* ── Init ───────────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', () => {
    track('page_view', { referrer: document.referrer || null });
    initClickTracking();
    initHoverTracking();
    initSectionTracking();
    initScrollDepth();
    initTimeOnPage();
    initFormTracking();
    startBatchTimer();
  });

})();
