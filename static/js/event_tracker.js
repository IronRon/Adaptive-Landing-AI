// Track user interactions and send them to /track-interactions/

// Get a cookie value by name
function getCookie(name) {
	const value = `; ${document.cookie}`;
	const parts = value.split(`; ${name}=`);
	if (parts.length === 2) return parts.pop().split(';').shift();
	return null;
}

// Read session id from body[data-session-id]
let sessionId = document.body && document.body.dataset && document.body.dataset.sessionId ? document.body.dataset.sessionId : null;
if (sessionId === "None" || sessionId === "null") sessionId = null;
let events = [];

// Add an event object to the in-memory buffer
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
	// Limit buffer size to avoid unbounded growth
	if (events.length > 1000) events.shift();
}

// Log clicks with nearest data-section or id
document.addEventListener('click', (e) => {
	try {
		let section = 'unknown';
		if (e.target && e.target.closest) {
			const secEl = e.target.closest('[data-section]');
			if (secEl) section = secEl.dataset.section || secEl.id || section;
		} else {
			// Fallback DOM walk for older browsers
			let el = e.target;
			while (el && el !== document.body) {
				if (el.dataset && el.dataset.section) { section = el.dataset.section; break; }
				el = el.parentElement;
			}
		}
		logEvent('click', section, { x: e.clientX, y: e.clientY, tag: e.target.tagName });
	} catch (err) { console.warn('click log error', err); }
});

// Throttled scroll logging to reduce volume
let lastScrollTime = 0;
document.addEventListener('scroll', () => {
	const now = Date.now();
	if (now - lastScrollTime < 200) return; // 200ms throttle
	lastScrollTime = now;
	try {
		logEvent('scroll', 'window', { scrollY: window.scrollY });
	} catch (err) { console.warn('scroll log error', err); }
});

// Send events payload to server, prefer fetch with keepalive, fallback to sendBeacon
function sendEvents(payload) {
	const csrftoken = getCookie('csrftoken');
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
				// If fetch fails, try sendBeacon
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

// Allow setting session id from other scripts
window.setSessionId = function(sid) {
    if (!sid) return;
    sessionId = sid;
    console.log('Session ID set for event tracker:', sessionId);
};

// On page unload, send any buffered events if we have a session id
window.addEventListener('beforeunload', () => {
	sessionId = document.body && document.body.dataset && document.body.dataset.sessionId ? document.body.dataset.sessionId : null;
	if (sessionId === "None" || sessionId === "null") sessionId = null;

	if (!events.length || !sessionId) return;
	const payload = JSON.stringify({ session_id: sessionId, events: events });
	sendEvents(payload);
});

