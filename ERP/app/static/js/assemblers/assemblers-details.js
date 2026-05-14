document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector("[data-assemblers-page='details']");
    const tableWrap = page?.querySelector("[data-assemblers-table-wrap]");
    const table = page?.querySelector("table");
    const tbody = page?.querySelector("[data-details-body]");
    const meta = page?.querySelector("[data-details-meta]");
    const loader = page?.querySelector("[data-details-loader]");
    const orderSearch = page?.querySelector("[data-details-search-order]");
    const customerSearch = page?.querySelector("[data-details-search-customer]");
    const productSearch = page?.querySelector("[data-details-search-product]");
    const filterToggle = page?.querySelector("[data-details-toggle-filters]");
    const filterPanel = page?.querySelector("[data-details-filters-panel]");

    if (!page || !tableWrap || !table || !tbody || !meta || !loader || !orderSearch || !customerSearch || !productSearch || !filterToggle || !filterPanel) {
        return;
    }

    const withGlobalLoader = (operation, message) => window.ERPLoading?.withLoader
        ? window.ERPLoading.withLoader(operation, { message })
        : operation();

    let tableManager = null;
    window.AssemblersTableTools?.initTable({ table, storageKey: table.dataset.tableKey || "assemblers-details" })
        .then(manager => { tableManager = manager; })
        .catch(e => console.warn("Failed to initialize table manager", e));

    const state = {
        offset: 0,
        limit: 30,
        loading: false,
        hasMore: true,
        total: 0,
        filtersOpen: false,
        filters: {
            orderNumber: "",
            customer: "",
            product: "",
        },
    };
    let searchTimer = null;
    let activeController = null;
    let requestVersion = 0;

    const setLoaderVisible = (visible) => {
        loader.classList.toggle("hidden", !visible);
    };

    const statusClassByValue = (status) => {
        const normalized = String(status || "").trim().toLowerCase();
        if (!normalized || normalized === "—") return "is-default";

        const percentMatch = normalized.match(/^(\d+(?:[.,]\d+)?)%$/);
        if (percentMatch) {
            const percent = Number(percentMatch[1].replace(",", "."));
            if (Number.isFinite(percent)) {
                if (percent <= 0) return "is-plan-none";
                if (percent < 50) return "is-plan-low";
                if (percent < 100) return "is-plan-mid";
                return "is-completed";
            }
        }

        if (normalized.includes("закрит")) return "is-closed";
        if (normalized.includes("розпод")) return "is-distributed";
        if (normalized.includes("прост")) return "is-idle";
        if (normalized.includes("не передано")) return "is-not-sent";
        if (normalized === "немає" || normalized === "нема") return "is-missing";
        if (normalized.includes("заверш") || normalized.includes("викон") || normalized.includes("done")) return "is-completed";
        if (normalized.includes("заплан") || normalized.includes("монтаж") || normalized.includes("збірк")) return "is-in-progress";
        if (normalized.includes("у черз") || normalized.includes("черг") || normalized.includes("очіку")) return "is-queued";
        if (normalized.includes("пауз") || normalized.includes("стоп")) return "is-paused";
        if (normalized.includes("в робот") || normalized.includes("процес") || normalized.includes("active")) return "is-in-progress";
        return "is-default";
    };

    const makeStatusBadge = (status, paused = false, pauseReason = "") => {
        const span = document.createElement("span");
        span.className = `assemblers-status-badge ${statusClassByValue(status)}`;
        
        if (paused && pauseReason) {
            span.textContent = `${status || "—"} (Пауза: ${pauseReason})`;
        } else if (paused) {
            span.textContent = `${status || "—"} (Пауза)`;
        } else {
            span.textContent = status || "—";
        }
        return span;
    };

    const renderRow = (row) => {
        const tr = document.createElement("tr");
        const values = [
            row.order_number, row.part_number, row.customer, row.product_name, row.planned_assembly_due_at,
            row.assembly_worker, row.assembly_started_at, row.assembly_completed_at, row.assembly_days, row.assembly_hours,
            row.assembly_status, row.planned_install_due_at, row.install_worker, row.install_started_at,
            row.install_completed_at, row.install_days, row.install_hours, row.install_status, row.item_type, row.constructor_status,
            row.production_launches, row.production_completed, row.metal, row.glass_eta, row.glass_delivered,
            row.planned_hours, row.item_value, row.item_percent, row.total_hours,
        ];

        values.forEach((value, index) => {
            const td = document.createElement("td");
            td.dataset.colIndex = String(index);
            if (index === 10) {
                // assembly_status with pause indicator
                td.classList.add("assemblers-status-cell");
                td.appendChild(makeStatusBadge(value, row.assembly_paused, row.assembly_pause_reason));
            } else if (index === 17) {
                // install_status with pause indicator
                td.classList.add("assemblers-status-cell");
                td.appendChild(makeStatusBadge(value, row.install_paused, row.install_pause_reason));
            } else if (index === 19) {
                td.classList.add("assemblers-status-cell");
                td.appendChild(makeStatusBadge(value));
            } else {
                td.textContent = value ?? "—";
            }
            tr.appendChild(td);
        });
        tableManager?.applyRow(tr);
        return tr;
    };

    const updateMeta = () => {
        setLoaderVisible(state.loading);
        meta.textContent = state.loading && !tbody.children.length
            ? "Завантаження..."
            : state.total
            ? ""
            : "Поки що деталей немає.";
    };

    const buildDetailsQueryString = (offset, limit) => {
        const params = new URLSearchParams();
        params.set("offset", String(offset));
        params.set("limit", String(limit));
        if (state.filters.orderNumber) {
            params.set("order_number", state.filters.orderNumber);
        }
        if (state.filters.customer) {
            params.set("customer", state.filters.customer);
        }
        if (state.filters.product) {
            params.set("product", state.filters.product);
        }
        return params.toString();
    };

    const loadNextPage = async () => {
        if (state.loading || !state.hasMore) {
            return;
        }

        const currentVersion = requestVersion;
        state.loading = true;
        updateMeta();

        try {
            activeController = new AbortController();
            const payload = await withGlobalLoader(async () => {
                const response = await fetch(`/assemblers/api/details?${buildDetailsQueryString(state.offset, state.limit)}`, {
                    cache: "no-store",
                    signal: activeController.signal,
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Не вдалося завантажити деталі");
                }
                return result;
            }, "Завантаження деталей...");

            if (currentVersion !== requestVersion) {
                return;
            }

            payload.rows.forEach((row) => tbody.appendChild(renderRow(row)));
            tableManager?.applyPinnedColumns?.();
            state.offset += payload.rows.length;
            state.total = payload.total || 0;
            state.hasMore = Boolean(payload.has_more);
            updateMeta();
        } catch (error) {
            if (error.name === "AbortError") {
                return;
            }
            meta.textContent = error.message || "Помилка завантаження деталей.";
            state.hasMore = false;
        } finally {
            if (currentVersion === requestVersion) {
                activeController = null;
            }
            state.loading = false;
            updateMeta();
        }
    };

    const reloadDetails = () => {
        requestVersion += 1;
        activeController?.abort();
        activeController = null;
        state.loading = false;
        state.offset = 0;
        state.total = 0;
        state.hasMore = true;
        tbody.innerHTML = "";
        tableWrap.scrollTop = 0;
        updateMeta();
        void loadNextPage();
    };

    const scheduleSearch = () => {
        if (searchTimer) {
            window.clearTimeout(searchTimer);
        }
        searchTimer = window.setTimeout(() => {
            state.filters.orderNumber = orderSearch.value.trim();
            state.filters.customer = customerSearch.value.trim();
            state.filters.product = productSearch.value.trim();
            reloadDetails();
        }, 260);
    };

    const toggleFilters = () => {
        state.filtersOpen = !state.filtersOpen;
        filterPanel.classList.toggle("hidden", !state.filtersOpen);
        filterToggle.textContent = state.filtersOpen ? "Сховати фільтри" : "Фільтри";
    };

    filterToggle.addEventListener("click", toggleFilters);
    orderSearch.addEventListener("input", scheduleSearch);
    customerSearch.addEventListener("input", scheduleSearch);
    productSearch.addEventListener("input", scheduleSearch);

    tableWrap.addEventListener("scroll", () => {
        const threshold = 160;
        if (tableWrap.scrollTop + tableWrap.clientHeight >= tableWrap.scrollHeight - threshold) {
            void loadNextPage();
        }
    }, { passive: true });

    void loadNextPage();
});