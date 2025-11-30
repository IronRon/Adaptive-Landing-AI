// Show cookie consent modal and persist user's choice

document.addEventListener("DOMContentLoaded", () => {
    const modal = document.getElementById("cookie-popup");
    if (!modal) return;

    // Prevent page scrolling while modal is open
    document.body.classList.add('modal-open');
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // Focusable elements inside modal for focus trapping
    const focusable = modal.querySelectorAll('button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])');
    const firstFocusable = focusable[0];
    const lastFocusable = focusable[focusable.length - 1];

    // Block clicks on overlay so page beneath doesn't react
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            e.preventDefault();
            e.stopPropagation();
        }
    });

    // Keep keyboard focus inside the modal (trap Tab). Ignore Escape.
    modal.addEventListener('keydown', (e) => {
        if (e.key === 'Tab') {
            if (focusable.length === 0) { e.preventDefault(); return; }
            if (e.shiftKey && document.activeElement === firstFocusable) {
                e.preventDefault();
                lastFocusable.focus();
            } else if (!e.shiftKey && document.activeElement === lastFocusable) {
                e.preventDefault();
                firstFocusable.focus();
            }
        }
    });

    // Focus the first actionable control
    firstFocusable?.focus();

    const acceptBtn = document.getElementById("accept-cookies");
    const declineBtn = document.getElementById("decline-cookies");

    // Close modal and restore page scrolling
    const closeModal = () => {
        document.body.style.overflow = prevOverflow || '';
        document.body.classList.remove('modal-open');
        modal?.remove();
    };

    // Accept: POST to server, update session id if returned
    acceptBtn?.addEventListener("click", async () => {
        try {
            const res = await fetch("/accept-cookies/", {
                method: "POST",
                credentials: "same-origin",
            });
            if (!res.ok) throw new Error("accept failed");
            const data = await res.json();
            if (data && data.session_id) {
                document.body.dataset.sessionId = data.session_id;
                if (typeof window.setSessionId === "function") {
                    window.setSessionId(data.session_id);
                }
            }
        } catch (err) {
            console.error("Accept cookies failed", err);
        } finally {
            closeModal();
        }
    });

    // Decline: just close the modal
    declineBtn?.addEventListener("click", () => {
        closeModal();
    });
});