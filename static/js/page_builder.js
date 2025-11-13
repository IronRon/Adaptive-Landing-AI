const config = JSON.parse(document.getElementById("page-config").textContent);
const root = document.getElementById("page-root");

const sections = {
  header: (data) => `
    <header data-section="header" class="hero ${data.style || ''}">
      <div class="container hero-content">
        <div>
          <h1>${data.text}</h1>
          <p>Premium car wash and detailing that brings back the showroom shine — quick, eco-friendly, and affordable.</p>
          <div class="hero-actions">
            <a class="btn primary" href="#booking">Book Now</a>
            <a class="btn secondary" href="#pricing">View Pricing</a>
            <a class="btn" href="#contact">Call Us</a>
          </div>
        </div>
        <div class="hero-image">
          <img src="/static/images/carwash.jpeg" alt="Car Wash" />
        </div>
      </div>
    </header>`,

  services: (data) => `
    <section id="services" data-section="services" class="cards ${data.highlight ? 'highlight' : ''}">
      <div class="container">
        <h2>Our Services</h2>
        <div class="cards-grid">
          <article class="card"><h3>Express Wash</h3><p>Quick exterior wash and dry.</p></article>
          <article class="card"><h3>Deluxe Detail</h3><p>Full inside-out deep clean.</p></article>
          <article class="card"><h3>Eco-Friendly</h3><p>Water-efficient biodegradable wash.</p></article>
        </div>
      </div>
    </section>`,

  pricing: (data) => `
    <section id="pricing" data-section="pricing" class="pricing ${data.highlight ? 'highlight' : ''}">
      <div class="container">
        <h2>Pricing</h2>
        <div class="price-grid">
          <div class="price">
            <h4>Express</h4>
            <p class="amount">$10</p>
            <ul class="price-features">
              <li>Exterior wash & dry</li>
              <li>Quick hand-dry</li>
            </ul>
            <div class="price-actions">
              <a class="btn primary" href="#booking">Buy Now</a>
              <a class="btn secondary" href="#pricing">Details</a>
            </div>
          </div>

          <div class="price">
            <h4>Standard</h4>
            <p class="amount">$25</p>
            <ul class="price-features">
              <li>Exterior + interior vacuum</li>
              <li>Window clean & tire shine</li>
            </ul>
            <div class="price-actions">
              <a class="btn primary" href="#booking">Buy Now</a>
              <a class="btn secondary" href="#pricing">Details</a>
            </div>
          </div>

          <div class="price">
            <h4>Detail</h4>
            <p class="amount">$75</p>
            <ul class="price-features">
              <li>Full detail: shampoo, polish, protect</li>
              <li>Leather treatment (if applicable)</li>
            </ul>
            <div class="price-actions">
              <a class="btn primary" href="#booking">Buy Now</a>
              <a class="btn secondary" href="#pricing">Details</a>
            </div>
          </div>
        </div>
      </div>
    </section>`,

  cta: (data) => `
    <section id="booking" data-section="cta" class="cta ${data.highlight ? 'highlight' : ''}">
      <div class="container">
        <h2>Ready for a clean ride?</h2>
        <p>Schedule online or call us for 10% off your first service.</p>
        <div class="cta-actions">
          <a class="btn primary" href="#contact">Buy Now</a>
          <a class="btn secondary" href="#contact">Schedule</a>
        </div>
      </div>
    </section>`,

  features: (data) => `
    <section id="features" data-section="features" class="features">
      <div class="container">
        <h2>Why Choose ShinePro</h2>
        <div class="features-grid">
          <div class="feature"><h3>Fast & Reliable</h3><p>Get in and out in under 20 minutes.</p></div>
          <div class="feature"><h3>Eco Friendly</h3><p>Water-saving systems and biodegradable soaps.</p></div>
          <div class="feature"><h3>Skilled Technicians</h3><p>Experienced staff who treat your car like their own.</p></div>
          <div class="feature"><h3>Mobile Service</h3><p>We come to you for on-site detailing.</p></div>
        </div>
      </div>
    </section>`,

  testimonials: (data) => `
    <section id="testimonials" data-section="testimonials" class="testimonials">
      <div class="container">
        <h2>What our customers say</h2>
        <div class="testimonials-list">
          <blockquote class="testimonial">"Quick, friendly, and my car looks new again!" — <strong>Alex</strong></blockquote>
          <blockquote class="testimonial">"Best value for money. Highly recommend." — <strong>Maria</strong></blockquote>
        </div>
      </div>
    </section>`,

  contact: (data) => `
    <section id="contact" data-section="contact" class="contact container">
      <h2>Contact Us</h2>
      <div class="contact-grid">
        <form class="contact-form">
          <label>Name<input type="text" name="name" required></label>
          <label>Email<input type="email" name="email" required></label>
          <label>Message<textarea name="message"></textarea></label>
          <button class="btn primary" type="submit">Send Message</button>
        </form>
        <div class="contact-info">
          <p><strong>Phone:</strong> <a href="tel:1234567890">123-456-7890</a></p>
          <p><strong>Address:</strong> 123 Shine St, Clean City</p>
          <p><strong>Hours:</strong> Mon-Sun 8am–6pm</p>
        </div>
      </div>
    </section>`,
};

// Render in order
// Ensure defaults if layout missing
const layout = Array.isArray(config.layout) ? config.layout : ['header','features','services','pricing','testimonials','cta','contact'];
layout.forEach((key) => {
  const html = sections[key]
    ? sections[key](config.customizations && config.customizations[key] ? config.customizations[key] : {})
    : `<section><p>Unknown section: ${key}</p></section>`;
  root.insertAdjacentHTML('beforeend', html);
});

// Debug panel: show whether default layout was used and click counts
(function renderDebug() {
  try {
    const dbg = config.debug || null;
    if (!dbg) return;
    const panel = document.createElement('aside');
    panel.className = 'debug-panel';
    const used = dbg.used_default ? 'YES (default used)' : 'NO (reordered)';
    const lines = [];
    lines.push(`<strong>Layout debug</strong>`);
    lines.push(`<div>Used default: <em>${used}</em></div>`);
    lines.push(`<div>Sessions considered: <em>${dbg.session_count_considered}</em></div>`);
    lines.push(`<div>Session IDs: <pre>${JSON.stringify(dbg.sessions_considered || [], null, 2)}</pre></div>`);
    lines.push(`<div>Section clicks: <pre>${JSON.stringify(dbg.section_clicks || {}, null, 2)}</pre></div>`);
    panel.innerHTML = lines.join('');
    document.body.appendChild(panel);
  } catch (e) {
    console.warn('debug panel error', e);
  }
})();
