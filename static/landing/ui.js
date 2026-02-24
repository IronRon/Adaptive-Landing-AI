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
      'is-compact',
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
  });

})();
