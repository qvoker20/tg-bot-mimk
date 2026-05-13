(() => {
    const bindToast = (toast) => {
        if (!toast || toast.dataset.toastBound === "1") {
            return toast;
        }

        toast.dataset.toastBound = "1";
        const closeButton = toast.querySelector("[data-action-toast-close]");
        const hideToast = () => {
            toast.remove();
        };

        const timeoutId = window.setTimeout(hideToast, 4200);
        closeButton?.addEventListener("click", () => {
            window.clearTimeout(timeoutId);
            hideToast();
        });

        return toast;
    };

    const normalizeKind = (kind) => (kind === "error" ? "danger" : kind || "success");

    window.ActionToast = {
        show(message, kind = "success") {
            const toast = document.createElement("div");
            toast.className = `alert action-toast alert-${normalizeKind(kind)} alert-dismissible`;
            toast.setAttribute("data-action-toast", "");
            toast.setAttribute("role", "status");
            toast.setAttribute("aria-live", "polite");
            toast.innerHTML = `
                <div class="action-toast-text"></div>
                <button type="button" class="btn-close action-toast-close" data-action-toast-close aria-label="Закрити повідомлення">×</button>
            `;
            toast.querySelector(".action-toast-text").textContent = message;
            document.body.appendChild(toast);
            return bindToast(toast);
        },
        bind: bindToast,
    };

    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll("[data-action-toast]").forEach(bindToast);
    });
})();