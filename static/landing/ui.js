/* ================================================================
   SparkleWash – UI Interactions
   Accordion, slider, read-more, pricing toggle, nav, scroll header
   Pure vanilla JS — no dependencies.
   ================================================================ */

(function () {
  'use strict';

  /* ── Helpers ──────────────────────────────────────────────── */
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

  /* ================================================================
     1. STICKY HEADER — add .scrolled class on scroll
     ================================================================ */
  function initStickyHeader() {
    const header = $('#site-header');
    if (!header) return;

    const onScroll = () => {
      header.classList.toggle('scrolled', window.scrollY > 10);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ================================================================
     2. MOBILE NAV TOGGLE
     ================================================================ */
  function initNavToggle() {
    const toggle = $('.nav-toggle');
    const nav = $('#main-nav');
    if (!toggle || !nav) return;

    toggle.addEventListener('click', () => {
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!expanded));
      nav.classList.toggle('open', !expanded);
      document.body.style.overflow = !expanded ? 'hidden' : '';
    });

    // Close nav when clicking a link
    $$('a', nav).forEach(link => {
      link.addEventListener('click', () => {
        toggle.setAttribute('aria-expanded', 'false');
        nav.classList.remove('open');
        document.body.style.overflow = '';
      });
    });
  }

  /* ================================================================
     3. TESTIMONIAL CAROUSEL
        Default: 3 cards per page.  .testimonials-single: 1 card per page.
     ================================================================ */
  function initTestimonialCarousel() {
    const section = document.querySelector('.testimonials');
    if (!section) return;

    const cards  = [...section.querySelectorAll('.testimonial-card')];
    const prevBtn = section.querySelector('.carousel-prev');
    const nextBtn = section.querySelector('.carousel-next');
    const dotsBox = section.querySelector('.carousel-dots');
    if (!cards.length || !prevBtn || !nextBtn || !dotsBox) return;

    function getPerPage() {
      return section.classList.contains('testimonials-single') ? 1 : 3;
    }

    let currentPage = 0;

    function render() {
      const perPage    = getPerPage();
      const totalPages = Math.ceil(cards.length / perPage);
      if (currentPage >= totalPages) currentPage = 0;

      /* Show / hide cards */
      cards.forEach((card, i) => {
        const page = Math.floor(i / perPage);
        card.classList.toggle('carousel-visible', page === currentPage);
      });

      /* Rebuild dots */
      dotsBox.innerHTML = '';
      for (let i = 0; i < totalPages; i++) {
        const dot = document.createElement('button');
        dot.className = 'carousel-dot' + (i === currentPage ? ' active' : '');
        dot.setAttribute('aria-label', 'Page ' + (i + 1));
        dot.addEventListener('click', () => { currentPage = i; render(); });
        dotsBox.appendChild(dot);
      }
    }

    prevBtn.addEventListener('click', () => {
      const totalPages = Math.ceil(cards.length / getPerPage());
      currentPage = (currentPage - 1 + totalPages) % totalPages;
      render();
    });
    nextBtn.addEventListener('click', () => {
      const totalPages = Math.ceil(cards.length / getPerPage());
      currentPage = (currentPage + 1) % totalPages;
      render();
    });

    /* Re-render when variant class changes (observed externally) */
    const observer = new MutationObserver(() => render());
    observer.observe(section, { attributes: true, attributeFilter: ['class'] });

    render();
  }

  /* ================================================================
     4. PRICING TOGGLE (monthly / annual)
     ================================================================ */
  function initPricingToggle() {
    const toggle = $('.toggle-switch');
    if (!toggle) return;

    const labels = $$('.toggle-label');
    const monthlyPrices = $$('.monthly-price');
    const annualPrices = $$('.annual-price');

    toggle.addEventListener('click', () => {
      const isAnnual = toggle.getAttribute('aria-checked') === 'true';
      toggle.setAttribute('aria-checked', String(!isAnnual));

      labels.forEach(l => l.classList.toggle('toggle-label--active'));

      monthlyPrices.forEach(p => p.hidden = !isAnnual);
      annualPrices.forEach(p => p.hidden = isAnnual);
    });
  }

  /* ================================================================
     5. READ MORE (About section — only active in compact mode)
     ================================================================ */
  function initReadMore() {
    $$('.read-more-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const section = btn.closest('.section');
        if (!section) return;

        const targetId = btn.getAttribute('aria-controls');
        const target = targetId ? document.getElementById(targetId) : null;

        // For compact mode: toggle compact--expanded on the section
        const expanded = btn.getAttribute('aria-expanded') === 'true';
        btn.setAttribute('aria-expanded', String(!expanded));

        if (section.classList.contains('is-compact')) {
          section.classList.toggle('compact--expanded', !expanded);
        }

        if (target) {
          target.hidden = expanded;
        }

        btn.textContent = expanded ? 'Read more \u25BE' : 'Read less \u25B4';
      });
    });
  }

  /* ================================================================
     5b. COMPACT READ MORE (Services and other sections)
     ================================================================ */
  function initCompactReadMore() {
    $$('.compact-read-more').forEach(btn => {
      btn.addEventListener('click', () => {
        const section = btn.closest('.section');
        if (!section) return;

        section.classList.add('compact--expanded');
        btn.setAttribute('aria-expanded', 'true');
      });
    });
  }

  /* ================================================================
     6. FAQ ACCORDION — <details> is native, but we handle
        the "View All FAQs" button for compact-top3 mode.
     ================================================================ */
  function initFAQ() {
    const faqSection = $('.faq');
    if (!faqSection) return;

    const viewAllBtn = $('.faq-view-all', faqSection);
    if (viewAllBtn) {
      viewAllBtn.addEventListener('click', () => {
        faqSection.classList.add('faq--expanded');
      });
    }
  }

  /* ================================================================
     7. PLAN HIGHLIGHT — add/remove highlight classes
        (Utility: can be called externally via window.setHighlightPlan)
     ================================================================ */
  function initPlanHighlight() {
    const pricing = $('.pricing');
    if (!pricing) return;

    window.setHighlightPlan = function (planNum) {
      pricing.classList.remove('highlight-plan-1', 'highlight-plan-2', 'highlight-plan-3');
      if (planNum >= 1 && planNum <= 3) {
        pricing.classList.add('highlight-plan-' + planNum);
      }
    };
  }

  /* ================================================================
     8. SECTION VARIANT HELPERS
        window.setVariant(sectionId, variantClass)
        window.toggleCompact(sectionId, on)
     ================================================================ */
  window.setVariant = function (sectionId, variantClass) {
    const el = document.getElementById(sectionId);
    if (!el) return;
    // Remove known variant classes
    const knownVariants = [
      'hero-compact', 'hero-cta-emphasis',
      'is-compact', 'is-hidden', 'section-promoted',
      'featured-service-1', 'featured-service-2', 'featured-service-3',
      'highlight-plan-1', 'highlight-plan-2', 'highlight-plan-3',
      'testimonials-single',
      'faq-compact-top3',
    ];
    knownVariants.forEach(v => el.classList.remove(v));
    if (variantClass) el.classList.add(variantClass);
  };

  window.toggleCompact = function (sectionId, on) {
    const el = document.getElementById(sectionId);
    if (!el) return;
    el.classList.toggle('is-compact', on);
  };

  /* ================================================================
     8b. HIDE / SHOW SECTION
         window.hideSection('faq')   → adds .is-hidden (display:none)
         window.showSection('faq')   → removes .is-hidden
     ================================================================ */
  window.hideSection = function (sectionId) {
    const el = document.getElementById(sectionId);
    if (el) el.classList.add('is-hidden');
  };

  window.showSection = function (sectionId) {
    const el = document.getElementById(sectionId);
    if (el) el.classList.remove('is-hidden');
  };

  /* ================================================================
     8c. PROMOTE / DEMOTE SECTION  (reorder to top)
         window.promoteSection('pricing')  → moves pricing right
         below trust bar via CSS order.
         window.demoteSection('pricing')   → resets to default order.
     ================================================================ */
  window.promoteSection = function (sectionId) {
    const el = document.getElementById(sectionId);
    if (el) el.classList.add('section-promoted');
  };

  window.demoteSection = function (sectionId) {
    const el = document.getElementById(sectionId);
    if (el) el.classList.remove('section-promoted');
  };

  /* ================================================================
     8d. APPLY BACKEND INSTRUCTIONS
         Designed for future backend use. Accepts an object like:
         {
           compact:  ['about', 'faq'],
           hide:     ['locations'],
           promote:  'pricing',
           variants: { hero: 'hero-cta-emphasis', pricing: 'highlight-plan-2' }
         }
     ================================================================ */
  window.applyPageConfig = function (cfg) {
    if (!cfg) return;

    // Compact sections
    if (Array.isArray(cfg.compact)) {
      cfg.compact.forEach(id => window.toggleCompact(id, true));
    }

    // Hidden sections
    if (Array.isArray(cfg.hide)) {
      cfg.hide.forEach(id => window.hideSection(id));
    }

    // Promote a section to the top
    if (cfg.promote) {
      window.promoteSection(cfg.promote);
    }

    // Per-section variant classes
    if (cfg.variants && typeof cfg.variants === 'object') {
      Object.entries(cfg.variants).forEach(([id, cls]) => {
        window.setVariant(id, cls);
      });
    }
  };

  /* ================================================================
     9. SMOOTH SCROLL for anchor links (fallback for older browsers)
     ================================================================ */
  function initSmoothScroll() {
    $$('a[href^="#"]').forEach(a => {
      a.addEventListener('click', e => {
        const target = document.querySelector(a.getAttribute('href'));
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });
  }

  /* ================================================================
     10. COOKIE CONSENT
     Shows the cookie modal on every visit unless the user has accepted.
     Accepting sets a persistent cookie sw_cookie_consent=accepted.
     Declining does nothing - modal reappears next page load.
     Tracking is only started after consent is given AND the server
     returns a valid session_id (via POST /accept-cookies/).
     ================================================================ */
  function initCookieConsent() {
    const accepted = document.cookie.includes('sw_cookie_consent=accepted');
    const modal    = $('#cookie-popup');

    if (accepted) {
      // Already consented - remove modal and start tracking
      if (modal) modal.remove();
      startTracking();
      return;
    }

    // Show modal
    if (!modal) return;
    modal.hidden = false;
    document.body.classList.add('cookie-modal-open');

    // Focus trap
    const focusable = [...modal.querySelectorAll('button, a[href]')];
    if (focusable.length) focusable[0].focus();

    modal.addEventListener('keydown', e => {
      if (e.key !== 'Tab' || !focusable.length) return;
      if (e.shiftKey && document.activeElement === focusable[0]) {
        e.preventDefault();
        focusable[focusable.length - 1].focus();
      } else if (!e.shiftKey && document.activeElement === focusable[focusable.length - 1]) {
        e.preventDefault();
        focusable[0].focus();
      }
    });

    // Block clicks on overlay backdrop
    modal.addEventListener('click', e => {
      if (e.target === modal) { e.preventDefault(); e.stopPropagation(); }
    });

    const closeModal = () => {
      document.body.classList.remove('cookie-modal-open');
      modal.remove();
    };

    // ACCEPT
    const acceptBtn = $('#accept-cookies');
    if (acceptBtn) {
      acceptBtn.addEventListener('click', () => {
        // Set consent cookie - 1 year expiry
        document.cookie = 'sw_cookie_consent=accepted;path=/;max-age=' + (60*60*24*365) + ';SameSite=Lax';
        closeModal();
        // Call backend to create Visitor + Session, then start tracking
        startTracking();
      });
    }

    // DECLINE - just close modal (no cookie set, it will reappear next visit)
    const declineBtn = $('#decline-cookies');
    if (declineBtn) {
      declineBtn.addEventListener('click', () => {
        closeModal();
        // Tracking does NOT start
      });
    }
  }

  /**
   * Start tracking by calling POST /accept-cookies/ to obtain a
   * server-created session_id, then initialise SparkleTracker with it.
   *
   * This is called:
   *   - Immediately on page load if consent was previously given.
   *   - Right after the user clicks "Accept Cookies".
   *
   * For new visitors the backend creates a Visitor + Session.
   * For returning visitors (visitor_id cookie exists) the backend
   * finds the existing Visitor and creates a fresh Session.
   */
  async function startTracking() {
    console.log('Attempting to start tracking session');
    try {
      console.log('Checking cookie consent with backend...');
      const csrfToken = (document.cookie.match(/(^| )csrftoken=([^;]+)/) || [])[2] || '';
      const res = await fetch('/accept-cookies/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: csrfToken ? { 'X-CSRFToken': csrfToken } : {},
      });
      console.log('Received response from /accept-cookies/:', res);

      if (!res.ok) throw new Error('POST /accept-cookies/ returned ' + res.status);

      const data = await res.json();
      console.log('bandit page_config check:', data);

      if (data.session_id && window.SparkleTracker) {
        window.SparkleTracker._init(data.session_id);
      }

      

      // Apply bandit-chosen page config for returning visitors
      if (data.page_config && Object.keys(data.page_config).length > 0) {
        console.log('[SparkleWash] Applying bandit page_config:', data.page_config);
        window.applyPageConfig(data.page_config);
      }
    } catch (err) {
      console.error('[SparkleWash] Failed to start tracking session:', err);
    }
  }

  /* ================================================================
     INIT
     ================================================================ */
  document.addEventListener('DOMContentLoaded', () => {
    initStickyHeader();
    initNavToggle();
    initTestimonialCarousel();
    initPricingToggle();
    initReadMore();
    initCompactReadMore();
    initFAQ();
    initPlanHighlight();
    initSmoothScroll();
    initCookieConsent();
  });

})();
