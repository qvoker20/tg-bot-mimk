document.addEventListener("DOMContentLoaded", () => {
    const panel = document.querySelector("[data-bulk-ops-panel]");
    if (!panel) return;

    // Елементи для закриття
    const closeOrderListTextarea = panel.querySelector("[data-close-order-list]");
    const closeAnalyzeBtn = panel.querySelector("[data-close-analyze-btn]");
    const closeEnteredCountSpan = panel.querySelector("[data-close-entered-count]");
    const closeUniqueCountSpan = panel.querySelector("[data-close-unique-count]");
    const closeAlreadyCountSpan = panel.querySelector("[data-close-already-count]");
    const bulkCloseCountSpan = panel.querySelector("[data-bulk-close-count]");
    const bulkCloseCountBtnSpan = panel.querySelector("[data-bulk-close-count-btn]");
    const bulkPreviewBtn = panel.querySelector("[data-bulk-preview-btn]");
    const bulkCloseBtn = panel.querySelector("[data-bulk-close-btn]");

    // Елементи для повернення
    const reopenTextarea = panel.querySelector("[data-reopen-list]");
    const reopenCountSpan = panel.querySelector("[data-reopen-count]");
    const reopenCountBtnSpan = panel.querySelector("[data-reopen-count-btn]");
    const reopenBtn = panel.querySelector("[data-reopen-btn]");

    // Модальне вікно
    const previewModal = document.querySelector("[data-preview-modal]");
    const previewList = previewModal?.querySelector("[data-preview-list]");
    const confirmCloseBtn = previewModal?.querySelector("[data-confirm-close-btn]");

    let analyzing = false;

    const parseApiResponse = async (response) => {
        const raw = await response.text();
        try {
            return JSON.parse(raw || "{}");
        } catch {
            return { ok: false, error: raw || "Некоректна відповідь сервера." };
        }
    };

    const showToast = (message, kind = "success") => {
        if (window.ActionToast?.show) {
            window.ActionToast.show(message, kind);
            return;
        }

        const toast = document.createElement("div");
        toast.className = `alert action-toast alert-${kind === "error" ? "danger" : kind} alert-dismissible`;
        toast.setAttribute("role", "status");
        toast.setAttribute("aria-live", "polite");
        toast.innerHTML = `
            <div class="action-toast-text">${message}</div>
            <button type="button" class="btn-close action-toast-close" aria-label="Закрити">×</button>
        `;
        toast.querySelector(".action-toast-close")?.addEventListener("click", () => toast.remove());
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 4200);
    };

    const parseTypedOrders = (text) => {
        const raw = String(text || "").trim();
        if (!raw) {
            return { entered: 0, unique: [], uniqueSet: new Set() };
        }

        const normalized = raw
            .split(/[\s,;]+/)
            .map((token) => token.replace(/[^0-9A-Za-z_-]/g, "").trim())
            .filter(Boolean)
            .map((token) => token.toUpperCase());

        const unique = [];
        const uniqueSet = new Set();
        normalized.forEach((value) => {
            if (!uniqueSet.has(value)) {
                uniqueSet.add(value);
                unique.push(value);
            }
        });

        return {
            entered: normalized.length,
            unique,
            uniqueSet,
        };
    };

    const parseReopenList = (text) => {
        const normalized = String(text || "")
            .split(/[\s,;]+/)
            .map((s) => s.replace(/[^0-9A-Za-z_-]/g, "").trim())
            .filter((s) => s.length > 0)
            .map((s) => s.toUpperCase());

        return Array.from(new Set(normalized));
    };

    const resetCloseSummary = () => {
        closeAlreadyCountSpan.textContent = "0";
        bulkCloseCountSpan.textContent = "0";
        bulkCloseCountBtnSpan.textContent = "0";
        bulkCloseBtn.disabled = true;
        bulkPreviewBtn.disabled = true;
        bulkCloseBtn.dataset.toClose = "[]";
    };

    const updateTypedCloseCounts = () => {
        const parsed = parseTypedOrders(closeOrderListTextarea?.value || "");
        closeEnteredCountSpan.textContent = String(parsed.entered);
        closeUniqueCountSpan.textContent = String(parsed.unique.length);
        resetCloseSummary();
    };

    const analyzeCloseOrders = async () => {
        if (analyzing) return;

        const parsed = parseTypedOrders(closeOrderListTextarea?.value || "");
        closeEnteredCountSpan.textContent = String(parsed.entered);
        closeUniqueCountSpan.textContent = String(parsed.unique.length);

        if (!parsed.unique.length) {
            showToast("Вкажіть номери замовлень для аналізу.", "warning");
            resetCloseSummary();
            return;
        }

        analyzing = true;
        closeAnalyzeBtn.disabled = true;

        try {
            const response = await fetch("/assemblers/api/buffer/close", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    order_numbers: parsed.unique,
                    analyze_only: true,
                }),
            });
            const data = await parseApiResponse(response);
            if (!response.ok || !data.ok) throw new Error(data.error || "Помилка аналізу");

            const toClose = Array.isArray(data.orders_to_close)
                ? data.orders_to_close.map((x) => String(x || "").trim().toUpperCase()).filter(Boolean)
                : [];

            closeAlreadyCountSpan.textContent = String(data.already_closed_orders || 0);
            bulkCloseCountSpan.textContent = String(toClose.length);
            bulkCloseCountBtnSpan.textContent = String(toClose.length);
            bulkCloseBtn.disabled = toClose.length === 0;
            bulkPreviewBtn.disabled = toClose.length === 0;
            bulkCloseBtn.dataset.toClose = JSON.stringify(toClose);

            showToast(
                `Аналіз готовий: буде закрито ${toClose.length}, вже закрито ${data.already_closed_orders || 0}.`,
                "info"
            );
        } catch (error) {
            showToast(`Помилка аналізу: ${error.message}`, "error");
            resetCloseSummary();
        } finally {
            analyzing = false;
            closeAnalyzeBtn.disabled = false;
        }
    };

    const showPreview = () => {
        const toClose = JSON.parse(bulkCloseBtn.dataset.toClose || "[]");
        if (previewList) {
            previewList.innerHTML = `<div class="preview-list">${toClose
                .map((n) => `<div class="preview-item">${n}</div>`)
                .join("")}</div>`;
        }
        previewModal?.classList.add("show");
    };

    const closePreview = () => {
        previewModal?.classList.remove("show");
    };

    const performBulkClose = async (toClose) => {
        if (!toClose || toClose.length === 0) {
            showToast("Немає замовлень для закриття", "warning");
            return;
        }

        try {
            const response = await fetch("/assemblers/api/buffer/close", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    order_numbers: toClose,
                }),
            });
            const data = await parseApiResponse(response);
            if (!response.ok || !data.ok) throw new Error(data.error || "Помилка при закритті");

            showToast(
                `✓ Закрито ${data.closed_orders || 0}. Вже закритих пропущено: ${data.already_closed_orders || 0}.`,
                "success"
            );

            closePreview();
            resetCloseSummary();
            bulkCloseBtn.dataset.toClose = "[]";
        } catch (error) {
            showToast(`Помилка: ${error.message}`, "error");
        }
    };

    const updateReopenCount = () => {
        const list = parseReopenList(reopenTextarea?.value || "");
        reopenCountSpan.textContent = String(list.length);
        reopenCountBtnSpan.textContent = String(list.length);
        reopenBtn.disabled = list.length === 0;
        reopenBtn.dataset.toReopen = JSON.stringify(list);
    };

    const performReopen = async (toReopen) => {
        if (!toReopen || toReopen.length === 0) {
            showToast("Немає замовлень для повернення", "warning");
            return;
        }

        try {
            const response = await fetch("/assemblers/api/closed-orders/reopen", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ order_numbers: toReopen }),
            });
            const data = await parseApiResponse(response);
            if (!response.ok || !data.ok) throw new Error(data.error || "Помилка при повертанні");

            showToast(
                `✓ Повернено ${data.reopened_orders || 0} замовлень`,
                "success"
            );
            reopenTextarea.value = "";
            updateReopenCount();
        } catch (error) {
            showToast(`Помилка: ${error.message}`, "error");
        }
    };

    closeOrderListTextarea?.addEventListener("input", updateTypedCloseCounts);
    closeAnalyzeBtn?.addEventListener("click", () => {
        void analyzeCloseOrders();
    });

    bulkPreviewBtn?.addEventListener("click", showPreview);
    previewModal?.addEventListener("click", (e) => {
        if (e.target === previewModal) closePreview();
    });
    previewModal?.querySelector(".btn-close")?.addEventListener("click", closePreview);

    bulkCloseBtn?.addEventListener("click", () => {
        const toClose = JSON.parse(bulkCloseBtn.dataset.toClose || "[]");
        if (confirm(`Ви впевнені? Будуть закриті ${toClose.length} замовлень.`)) {
            void performBulkClose(toClose);
        }
    });

    confirmCloseBtn?.addEventListener("click", () => {
        const toClose = JSON.parse(bulkCloseBtn.dataset.toClose || "[]");
        void performBulkClose(toClose);
    });

    reopenTextarea?.addEventListener("input", updateReopenCount);
    reopenBtn?.addEventListener("click", () => {
        const toReopen = JSON.parse(reopenBtn.dataset.toReopen || "[]");
        if (confirm(`Ви впевнені? Будуть повернені ${toReopen.length} замовлень.`)) {
            void performReopen(toReopen);
        }
    });

    updateTypedCloseCounts();
    updateReopenCount();
});
