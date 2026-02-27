console.log("🔧 Page Builder Loaded");

// Read JSON data embedded into the page by Django
const config = JSON.parse(document.getElementById("page-config").textContent);
const builderSections = JSON.parse(document.getElementById("page-sections").textContent);
const combinedCss = document.getElementById("page-css").textContent;

const root = document.getElementById("page-root");

(function injectBaseCSS() {
  // If there is combined CSS from the server, insert it into the document head
  if (!combinedCss.trim()) return;

  const styleEl = document.createElement("style");
  styleEl.id = "builder-base-css";
  styleEl.textContent = combinedCss;
  document.head.appendChild(styleEl);
})();

// Return customization object for a section (or empty object)
function getCustomization(key) {
  return (config.customizations && config.customizations[key]) ? config.customizations[key] : {};
}

// Determine final layout order, fallback to DB order if not provided
const layout = Array.isArray(config.layout) ? config.layout : Object.keys(builderSections); // fallback: DB order

// Hold CSS blocks collected from section customizations
const collectedCss = [];

// Render template string using data (safely attempts interpolation)
function renderTemplate(template, data) {
  try {
    // Use a dynamic function to evaluate a template literal with 'data' in scope
    const fn = new Function("data", "with(data){ return `" + template + "` }");
    return fn(data);
  } catch (e) {
    console.warn("Template render error:", e);
    // If render fails, return original template HTML
    return template;
  }
}

layout.forEach((key) => {
  const sec = builderSections[key];
  if (!sec) {
    // Show placeholder for unknown/missing sections
    root.insertAdjacentHTML("beforeend", `<section><p>Unknown section: ${key}</p></section>`);
    return;
  }

  const customization = getCustomization(key);
  // Collect any CSS provided as part of customization
  if (customization.css) {
    collectedCss.push(`/* ${key} css */\n${customization.css}`);
  }

  // Render section HTML using overrides from customization
  const rendered = renderTemplate(sec.html, customization);
  // Insert the rendered HTML into the page
  root.insertAdjacentHTML("beforeend", rendered);

  // After inserting, apply inline style attribute if provided
  try {
    const el = root.querySelector(`[data-section="${key}"]`);
    if (el && customization.style) {
      el.setAttribute('style', customization.style);
    }
  } catch (e) {
    console.warn('apply customization failed for', key, e);
  }
});

// If any customization CSS was collected, append it to the head
if (collectedCss.length) {
  const styleEl = document.createElement('style');
  styleEl.id = 'ai-custom-css';
  styleEl.textContent = collectedCss.join('\n\n');
  document.head.appendChild(styleEl);
}

// Render a simple debug panel when debug info is present
(function renderDebug() {
  try {
    const dbg = config.debug || null;
    if (!dbg) return;

    const panel = document.createElement('aside');
    panel.className = 'debug-panel';

    // Gather key debug fields to show
    const toRender = {
      debug: dbg,
      layout: config.layout || null,
      scores: config.scores || null,
      global_scores: config.global_scores || null,
      user_scores: config.user_scores || null,
      customizations: config.customizations || null,
    };

    const lines = [];
    lines.push(`<strong>Recommendations Debug</strong>`);
    lines.push(`<div><em>Note:</em> all fields from server-side recommendations are shown below.</div>`);
    lines.push(`<div><h4>Debug object</h4><pre>${JSON.stringify(toRender.debug, null, 2)}</pre></div>`);
    lines.push(`<div><h4>Layout (final)</h4><pre>${JSON.stringify(toRender.layout, null, 2)}</pre></div>`);
    lines.push(`<div><h4>Scores (combined)</h4><pre>${JSON.stringify(toRender.scores, null, 2)}</pre></div>`);
    lines.push(`<div><h4>Global scores (bandit)</h4><pre>${JSON.stringify(toRender.global_scores, null, 2)}</pre></div>`);
    lines.push(`<div><h4>User scores (per-visitor)</h4><pre>${JSON.stringify(toRender.user_scores, null, 2)}</pre></div>`);
    lines.push(`<div><h4>Customizations</h4><pre>${JSON.stringify(toRender.customizations, null, 2)}</pre></div>`);

    panel.innerHTML = lines.join('');
    document.body.appendChild(panel);
  } catch (e) {
    console.warn('debug panel error', e);
  }
})();
