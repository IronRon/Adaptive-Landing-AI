// Display logic handled server-side via template flag
// This script sets a "cookie_consent" flag so popup does not show again.

document.addEventListener("DOMContentLoaded", () => {
    const acceptBtn = document.getElementById("accept-cookies");
    const declineBtn = document.getElementById("decline-cookies");

    acceptBtn?.addEventListener("click", async () => {
        try {
            const res = await fetch("/accept-cookies/", {
                method: "POST",
                credentials: "same-origin", // ensure browser stores Set-Cookie
            });
            if (!res.ok) throw new Error("accept failed");
            const data = await res.json();
            if (data && data.session_id) {
                // make session id available to tracker immediately
                document.body.dataset.sessionId = data.session_id;
                if (typeof window.setSessionId === "function") {
                    window.setSessionId(data.session_id);
                }
            }
            document.getElementById("cookie-popup")?.remove();
        } catch (err) {
            console.error("Accept cookies failed", err);
            document.getElementById("cookie-popup")?.remove();
        }
    });

    declineBtn?.addEventListener("click", () => {
        localStorage.setItem("cookie_declined", "1");
        document.getElementById("cookie-popup")?.remove();
    });
});
