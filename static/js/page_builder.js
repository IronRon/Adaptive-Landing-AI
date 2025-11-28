console.log("🔧 Page Builder Loaded");

// 1. Read data embedded by Django
const config = JSON.parse(document.getElementById("page-config").textContent);
const builderSections = JSON.parse(document.getElementById("page-sections").textContent);
const combinedCss = document.getElementById("page-css").textContent;

const root = document.getElementById("page-root");

(function injectBaseCSS() {
  if (!combinedCss.trim()) return;

  const styleEl = document.createElement("style");
  styleEl.id = "builder-base-css";
  styleEl.textContent = combinedCss;
  document.head.appendChild(styleEl);
})();

// helper to normalize incoming customization per section
function getCustomization(key) {
  return (config.customizations && config.customizations[key]) ? config.customizations[key] : {};
}

// Render in order
// Ensure defaults if layout missing
const layout = Array.isArray(config.layout) ? config.layout : Object.keys(builderSections); // fallback: DB order

// collect CSS blocks from customizations (optional data.css per section)
const collectedCss = [];

function renderTemplate(template, data) {
  try {
    // Wrap template as a JS template literal and execute
    const fn = new Function("data", "with(data){ return `" + template + "` }");
    return fn(data);
  } catch (e) {
    console.warn("Template render error:", e);
    return template; // fallback to raw HTML if error
  }
}


layout.forEach((key) => {
  const sec = builderSections[key];
  if (!sec) {
    root.insertAdjacentHTML("beforeend", `<section><p>Unknown section: ${key}</p></section>`);
    return;
  }

  const customization = getCustomization(key);
  // if provided, gather css block
  if (customization.css) {
    // scope comment helps debugging; user-provided css is inserted as-is
    collectedCss.push(`/* ${key} css */\n${customization.css}`);
  }

  // Render the section as a template with AI overrides
  const rendered = renderTemplate(sec.html, customization);
  // Insert rendered HTML
  root.insertAdjacentHTML("beforeend", rendered);

  // --- new: ensure inline style / text overrides are applied after insert ---
  try {
    const el = root.querySelector(`[data-section="${key}"]`);
    if (el && customization.style) {
      el.setAttribute('style', customization.style);
    }
  } catch (e) {
    console.warn('apply customization failed for', key, e);
  }
});

// append collected CSS to document head (if any)
if (collectedCss.length) {
  const styleEl = document.createElement('style');
  styleEl.id = 'ai-custom-css';
  styleEl.textContent = collectedCss.join('\n\n');
  document.head.appendChild(styleEl);
}

// Debug panel: show whether default layout was used and click counts
(function renderDebug() {
  try {
    const dbg = config.debug || null;
    if (!dbg) return;

    const panel = document.createElement('aside');
    panel.className = 'debug-panel';

    // Collect everything we want to show from the recommendations payload
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
    lines.push(`<div><em>Note:</em> all fields from server-side ` +
      `recommendations are shown below.</div>`);
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
