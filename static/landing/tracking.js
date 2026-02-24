/* ================================================================
   SparkleWash – Event Tracking
   Lightweight, configurable tracker that captures user interactions
   and sends them to the Django backend.

   Data attributes used:
     data-track          – marks a section for visibility tracking
     data-track-click    – marks an element for click tracking
     data-section        – section identifier

   Events are batched and sent periodically or on page unload.
   ================================================================ */

(function () {
  'use strict';

  /* ── Configuration ───────────────────────────────────────── */
  const CONFIG = {
    endpoint: '/track-interactions/',    // Django endpoint
    batchInterval: 5000,                 // ms between batch sends
    maxQueueSize: 50,                    // flush when queue hits this
    sessionKey: 'sw_session_id',
    debug: false,                        // set true to log events to console
  };

  /* ── State ───────────────────────────────────────────────── */
  let queue = [];
  let sessionId = getOrCreateSession();
  let batchTimer = null;

  /* ── Session ─────────────────────────────────────────────── */
  function getOrCreateSession() {
    let id = sessionStorage.getItem(CONFIG.sessionKey);
    if (!id) {
      id = crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2);
      sessionStorage.setItem(CONFIG.sessionKey, id);
    }
    return id;
  }

  /* ── Enqueue ─────────────────────────────────────────────── */
  function track(eventType, data) {
    const event = {
      type: eventType,
      ts: new Date().toISOString(),
      session: sessionId,
      url: location.pathname,
      ...data,
    };

    queue.push(event);

    if (CONFIG.debug) console.log('[tracker]', event);

    if (queue.length >= CONFIG.maxQueueSize) flush();
  }

  /* ── Flush / Send ────────────────────────────────────────── */
  function flush() {
    if (queue.length === 0) return;

    const payload = queue.splice(0);

    // Get CSRF token from cookie
    const csrfToken = getCookie('csrftoken');

    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;

    // Use sendBeacon for unload, fetch otherwise
    if (navigator.sendBeacon && document.visibilityState === 'hidden') {
      const blob = new Blob([JSON.stringify({ events: payload })], { type: 'application/json' });
      navigator.sendBeacon(CONFIG.endpoint, blob);
    } else {
      fetch(CONFIG.endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify({ events: payload }),
        keepalive: true,
      }).catch(() => {
        // Re-queue on failure
        queue.unshift(...payload);
      });
    }
  }

  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? match[2] : '';
  }

  /* ── Click Tracking ──────────────────────────────────────── */
  function initClickTracking() {
    document.addEventListener('click', e => {
      const el = e.target.closest('[data-track-click]');
      if (!el) return;

      const label = el.getAttribute('data-track-click');
      const section = el.closest('[data-section]');

      track('click', {
        element: label,
        section: section ? section.getAttribute('data-section') : null,
        tag: el.tagName.toLowerCase(),
        text: (el.textContent || '').trim().slice(0, 80),
      });
    });
  }

  /* ── Section Visibility Tracking (Intersection Observer) ── */
  function initVisibilityTracking() {
    const sections = document.querySelectorAll('[data-track]');
    if (sections.length === 0) return;

    const seen = new Set();

    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        const id = entry.target.getAttribute('data-track') || entry.target.id;
        if (entry.isIntersecting && !seen.has(id)) {
          seen.add(id);
          track('section_view', {
            section: id,
          });
        }
      });
    }, { threshold: 0.3 });

    sections.forEach(s => observer.observe(s));
  }

  /* ── Scroll Depth Tracking ───────────────────────────────── */
  function initScrollDepth() {
    const milestones = [25, 50, 75, 100];
    const reached = new Set();

    window.addEventListener('scroll', () => {
      const scrollPct = Math.round(
        (window.scrollY / (document.documentElement.scrollHeight - window.innerHeight)) * 100
      );
      milestones.forEach(m => {
        if (scrollPct >= m && !reached.has(m)) {
          reached.add(m);
          track('scroll_depth', { depth: m });
        }
      });
    }, { passive: true });
  }

  /* ── Time on Page ────────────────────────────────────────── */
  function initTimeOnPage() {
    const start = Date.now();
    window.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        track('time_on_page', { seconds: Math.round((Date.now() - start) / 1000) });
        flush();
      }
    });
  }

  /* ── Form Tracking ───────────────────────────────────────── */
  function initFormTracking() {
    document.addEventListener('submit', e => {
      const form = e.target.closest('[data-track]');
      if (!form) return;
      track('form_submit', {
        section: form.getAttribute('data-track'),
        form_id: form.id || null,
      });
    });

    // Track form field focus
    document.addEventListener('focusin', e => {
      if (e.target.matches('input, textarea, select')) {
        const form = e.target.closest('[data-track]');
        if (!form) return;
        track('form_focus', {
          section: form.getAttribute('data-track'),
          field: e.target.name || e.target.id || null,
        });
      }
    });
  }

  /* ── Batch Timer ─────────────────────────────────────────── */
  function startBatchTimer() {
    batchTimer = setInterval(flush, CONFIG.batchInterval);
    window.addEventListener('beforeunload', flush);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flush();
    });
  }

  /* ── Public API ──────────────────────────────────────────── */
  window.SparkleTracker = {
    track,
    flush,
    getSessionId: () => sessionId,
  };

  /* ── Init ────────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', () => {
    track('page_view', { referrer: document.referrer || null });
    initClickTracking();
    initVisibilityTracking();
    initScrollDepth();
    initTimeOnPage();
    initFormTracking();
    startBatchTimer();
  });

})();
