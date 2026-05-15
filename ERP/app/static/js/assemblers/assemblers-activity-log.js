(function () {
    const page = document.querySelector("[data-activity-log-page]");
    if (!page) {
        return;
    }

    const form = page.querySelector("[data-activity-log-filters]");
    const searchInput = page.querySelector("[data-activity-log-search]");
    const actorInput = page.querySelector("[data-activity-log-actor]");
    const orderNumberInput = page.querySelector("[data-activity-log-order-number]");
    const subdivisionInput = page.querySelector("[data-activity-log-subdivision]");
    const sourceSelect = page.querySelector("[data-activity-log-source]");
    const dateFromInput = page.querySelector("[data-activity-log-date-from]");
    const dateToInput = page.querySelector("[data-activity-log-date-to]");
    const body = page.querySelector("[data-activity-log-body]");
    const meta = page.querySelector("[data-activity-log-meta]");

    const state = {
        offset: 0,
        limit: 30,
        loading: false,
        hasMore: false,
        total: 0,
        scrollLoading: false,
    };

    const formatDateTime = (value) => {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("uk-UA", {
            dateStyle: "short",
            timeStyle: "short",
        }).format(date);
    };

    const escapeHtml = (value) => String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");

    const parseDetails = (rawDetails) => {
        if (!rawDetails) {
            return null;
        }

        if (typeof rawDetails === "object") {
            return rawDetails;
        }

        try {
            return JSON.parse(rawDetails);
        } catch {
            return null;
        }
    };

    const buildDescriptionHtml = (row) => {
        const details = parseDetails(row.details) || {};
        const mainText = String(row.description || row.action_label || row.action_key || "—").trim() || "—";
        const metaParts = [];

        if (details.task_type) metaParts.push(`тип: ${details.task_type}`);
        if (details.created_count != null) metaParts.push(`створено: ${details.created_count}`);
        if (details.affected_count != null) metaParts.push(`змінено: ${details.affected_count}`);
        if (details.selected_parts_count != null) metaParts.push(`частин: ${details.selected_parts_count}`);
        if (details.cells_count != null) metaParts.push(`клітинок: ${details.cells_count}`);
        if (details.pause_reason) metaParts.push(`причина паузи: ${details.pause_reason}`);
        if (details.status_code) metaParts.push(`код: ${details.status_code}`);
        if (details.error_type) metaParts.push(`помилка: ${details.error_type}`);

        const metaText = metaParts.join(" · ");
        return `
            <div class="activity-log-description">
                <div class="activity-log-description-main">${escapeHtml(mainText)}</div>
                ${metaText ? `<div class="activity-log-description-meta">${escapeHtml(metaText)}</div>` : ""}
            </div>
        `;
    };

    const collectFilters = () => ({
        search: searchInput?.value?.trim() || "",
        actor: actorInput?.value?.trim() || "",
        order_number: orderNumberInput?.value?.trim() || "",
        subdivision: subdivisionInput?.value?.trim() || "",
        source: sourceSelect?.value || "",
        date_from: dateFromInput?.value || "",
        date_to: dateToInput?.value || "",
    });

    const renderRows = (rows, append = false) => {
        if (!append) {
            body.innerHTML = "";
        }

        if (!rows.length && !append) {
            body.innerHTML = `
                <tr>
                    <td colspan="10" style="text-align:center; padding: 22px;">Нічого не знайдено.</td>
                </tr>
            `;
            return;
        }

        const loader = `
            <tr class="activity-log-loader-row">
                <td colspan="10" style="text-align:center; padding: 12px;">
                    <span style="display: inline-flex; align-items: center; gap: 8px; font-size: 0.9em; color: #64748b;">
                        <svg style="width: 16px; height: 16px; animation: spin 1s linear infinite;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <path d="M12 6v6l4 2" stroke-linecap="round"></path>
                        </svg>
                        Завантаження...
                    </span>
                </td>
            </tr>
        `;

        body.insertAdjacentHTML("beforeend", rows.map((row) => `
            <tr class="${Number(row.status_code || 0) >= 400 ? "is-subcontract" : row.actor_kind === "system" ? "is-subcontract" : ""}">
                <td>${escapeHtml(formatDateTime(row.event_at))}</td>
                <td><strong>${escapeHtml(row.action_label || row.action_key || "—")}</strong></td>
                <td>${escapeHtml(row.actor_name || "Система")}</td>
                <td>${escapeHtml(row.actor_role || row.actor_kind || "—")}</td>
                <td>${escapeHtml([row.entity_type, row.entity_id].filter(Boolean).join(" #") || "—")}</td>
                <td>${escapeHtml(row.order_number || "—")}</td>
                <td>${escapeHtml(row.subdivision || "—")}</td>
                <td>${escapeHtml([row.source_table, row.source_op].filter(Boolean).join(" / ") || "—")}</td>
                <td><span class="activity-log-status-pill ${Number(row.status_code || 0) >= 500 ? "is-error" : Number(row.status_code || 0) >= 400 ? "is-warn" : Number(row.status_code || 0) > 0 ? "is-ok" : ""}">${escapeHtml(row.status_code ? String(row.status_code) : "—")}</span></td>
                <td>${buildDescriptionHtml(row)}</td>
            </tr>
        `).join(""));

        if (state.scrollLoading) {
            body.insertAdjacentHTML("beforeend", loader);
        }
    };

    const loadRows = async ({ reset = false } = {}) => {
        if (state.loading) {
            return;
        }

        state.loading = true;
        if (!reset) {
            state.scrollLoading = true;
        }
        if (reset) {
            meta.textContent = "Пошук журналу...";
        }

        const filters = collectFilters();
        const params = new URLSearchParams({
            offset: String(reset ? 0 : state.offset),
            limit: String(state.limit),
            ...filters,
        });

        try {
            const response = await fetch(`/assemblers/api/activity-log?${params.toString()}`, {
                credentials: "same-origin",
            });
            const payload = await response.json();

            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || "Не вдалося завантажити журнал дій.");
            }

            const rows = Array.isArray(payload.rows) ? payload.rows : [];
            if (reset) {
                state.offset = 0;
                renderRows(rows, false);
            } else {
                renderRows(rows, true);
            }

            state.offset += rows.length;
            state.total = Number(payload.total || 0);
            state.hasMore = Boolean(payload.has_more);
            meta.textContent = state.total
                ? `Знайдено ${state.total} записів.`
                : "Журнал порожній.";
        } catch (error) {
            meta.textContent = error.message || "Не вдалося завантажити журнал дій.";
        } finally {
            state.loading = false;
            state.scrollLoading = false;
        }
    };

    form?.addEventListener("submit", (event) => {
        event.preventDefault();
        loadRows({ reset: true });
    });

    const tableWrap = page.closest(".module-content") || page.parentElement;
    const handleTableScroll = () => {
        if (!tableWrap || state.loading || !state.hasMore) {
            return;
        }

        const { scrollTop, scrollHeight, clientHeight } = tableWrap;
        const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);

        if (distanceFromBottom < 300) {
            loadRows({ reset: false });
        }
    };

    tableWrap?.addEventListener("scroll", handleTableScroll);

    page.querySelector("[data-activity-log-reset]")?.addEventListener("click", () => {
        if (searchInput) searchInput.value = "";
        if (actorInput) actorInput.value = "";
        if (orderNumberInput) orderNumberInput.value = "";
        if (subdivisionInput) subdivisionInput.value = "";
        if (sourceSelect) sourceSelect.value = "";
        if (dateFromInput) dateFromInput.value = "";
        if (dateToInput) dateToInput.value = "";
        loadRows({ reset: true });
    });

    loadRows({ reset: true });
})();