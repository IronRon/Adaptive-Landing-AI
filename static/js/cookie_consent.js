// Display logic handled server-side via template flag
// This script sets a "cookie_consent" flag so popup does not show again.

document.addEventListener("DOMContentLoaded", () => {
    const modal = document.getElementById("cookie-popup");
    if (!modal) return;

    // block page scroll & interactions
    document.body.classList.add('modal-open');
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // focus management (trap)
    const focusable = modal.querySelectorAll('button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])');
    const firstFocusable = focusable[0];
    const lastFocusable = focusable[focusable.length - 1];

    // ensure clickable area outside card does not close or interact
    modal.addEventListener('click', (e) => {
        // clicks on overlay should not close modal or interact with page
        if (e.target === modal) {
            e.preventDefault();
            e.stopPropagation();
        }
    });

    // key handling: trap Tab inside modal; ignore Escape to force explicit choice
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

    // Move focus to the primary action
    firstFocusable?.focus();

    const acceptBtn = document.getElementById("accept-cookies");
    const declineBtn = document.getElementById("decline-cookies");

    const closeModal = () => {
        document.body.style.overflow = prevOverflow || '';
        document.body.classList.remove('modal-open');
        modal?.remove();
    };

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

    declineBtn?.addEventListener("click", () => {
        closeModal();
    });
});