
// Event tracker for landing page
// Reads session id from <body data-session-id="..."> and sends events to /track-interactions/

function getCookie(name) {
	const value = `; ${document.cookie}`;
	const parts = value.split(`; ${name}=`);
	if (parts.length === 2) return parts.pop().split(';').shift();
	return null;
}

const sessionId = document.body && document.body.dataset && document.body.dataset.sessionId ? document.body.dataset.sessionId : null;
let events = [];

function logEvent(type, element, extraData = {}) {
	const evt = {
		event_type: type,
		element: element,
		additional_data: extraData,
		timestamp: new Date().toISOString(),
		x: extraData.x ?? null,
		y: extraData.y ?? null,
	};
	events.push(evt);
	// keep a small cap in memory to avoid unbounded growth
	if (events.length > 1000) events.shift();
}

document.addEventListener('click', (e) => {
	try {
		// determine the section id (data-section or id) for the clicked element
		let section = 'unknown';
		if (e.target && e.target.closest) {
			const secEl = e.target.closest('[data-section]');
			if (secEl) section = secEl.dataset.section || secEl.id || section;
		} else {
			// fallback: walk up the DOM
			let el = e.target;
			while (el && el !== document.body) {
				if (el.dataset && el.dataset.section) { section = el.dataset.section; break; }
				el = el.parentElement;
			}
		}
		logEvent('click', section, { x: e.clientX, y: e.clientY, tag: e.target.tagName });
	} catch (err) { console.warn('click log error', err); }
});

// Throttle scroll events to avoid huge volumes
let lastScrollTime = 0;
document.addEventListener('scroll', () => {
	const now = Date.now();
	if (now - lastScrollTime < 200) return; // 200ms throttle
	lastScrollTime = now;
	try {
		logEvent('scroll', 'window', { scrollY: window.scrollY });
	} catch (err) { console.warn('scroll log error', err); }
});

function sendEvents(payload) {
	const csrftoken = getCookie('csrftoken');
	// Prefer fetch with keepalive so we can include CSRF header
	if (window.fetch) {
		try {
			fetch('/track-interactions/', {
				method: 'POST',
				credentials: 'same-origin',
				headers: {
					'Content-Type': 'application/json',
					...(csrftoken ? { 'X-CSRFToken': csrftoken } : {}),
				},
				body: payload,
				keepalive: true,
			}).catch((e) => {
				// fallback to sendBeacon
				if (navigator.sendBeacon) navigator.sendBeacon('/track-interactions/', payload);
			});
			return;
		} catch (e) {
			// fall through to sendBeacon
		}
	}

	if (navigator.sendBeacon) {
		navigator.sendBeacon('/track-interactions/', payload);
	}
}

window.addEventListener('beforeunload', () => {
	if (!events.length || !sessionId) return;
	const payload = JSON.stringify({ session_id: sessionId, events: events });
	sendEvents(payload);
});

