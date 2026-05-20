document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector("[data-assemblers-page='details']");
    const tableWrap = page?.querySelector("[data-assemblers-table-wrap]");
    const table = page?.querySelector("table");
    const tbody = page?.querySelector("[data-details-body]");
    const meta = page?.querySelector("[data-details-meta]");
    const loader = page?.querySelector("[data-details-loader]");
    const orderSearch = page?.querySelector("[data-details-search-order]");
    const customerSearch = page?.querySelector("[data-details-search-customer]");
    const productSearch = document.querySelector("[data-details-search-product]");
    const searchApplyButton = page?.querySelector("[data-details-search-apply]");
    const openFiltersButton = page?.querySelector("[data-details-open-filters]");
    const activeFiltersEl = page?.querySelector("[data-details-active-filters]");
    const filtersModal = document.querySelector("[data-details-filters-modal]");
    const filtersCloseButtons = document.querySelectorAll("[data-details-filters-close]");
    const filtersApplyButton = document.querySelector("[data-details-filters-apply]");
    const filtersResetButton = document.querySelector("[data-details-filters-reset]");
    const filtersRequiresAssembly = document.querySelector("[data-details-filter-requires-assembly]");
    const filtersRequiresInstall = document.querySelector("[data-details-filter-requires-install]");

    if (!page || !tableWrap || !table || !tbody || !meta || !loader || !orderSearch || !customerSearch) {
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
        filters: {
            orderNumber: "",
            customer: "",
            product: "",
            requiresAssembly: "",
            requiresInstall: "",
        },
    };
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

    const isMissingPlannedDate = (value) => {
        const text = String(value ?? "").trim();
        return !text || text === "—" || text === "-";
    };

    const renderRow = (row) => {
        const tr = document.createElement("tr");
        const values = [
            row.order_number, row.part_number, row.customer, row.product_name, row.planned_assembly_due_at,
            row.assembly_worker, row.assembly_started_at, row.assembly_completed_at, row.assembly_days, row.assembly_hours,
            row.assembly_status, row.planned_install_due_at, row.install_worker, row.install_started_at,
            row.install_completed_at, row.install_days, row.install_hours, row.install_status, row.item_type, row.constructor_status,
            row.production_launches, row.production_completed, row.metal, row.glass_eta, row.glass_delivered,
            row.planned_hours, row.item_value,
            row.assembly_percent != null ? `${row.assembly_percent}%` : "—",
            row.install_percent != null ? `${row.install_percent}%` : "—",
            row.total_hours,
        ];

        values.forEach((value, index) => {
            const td = document.createElement("td");
            td.dataset.colIndex = String(index);
            if (index === 4 || index === 11) {
                if (isMissingPlannedDate(value)) {
                    td.textContent = "Потребує планування!";
                    td.classList.add("is-deadline-critical");
                } else {
                    td.textContent = value ?? "—";
                }
            } else if (index === 10) {
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
        if (state.filters.requiresAssembly) {
            params.set("requires_assembly", state.filters.requiresAssembly);
        }
        if (state.filters.requiresInstall) {
            params.set("requires_install", state.filters.requiresInstall);
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

    const applySearch = () => {
        state.filters.orderNumber = orderSearch.value.trim();
        state.filters.customer = customerSearch.value.trim();
        reloadDetails();
    };

    const updateActiveFilters = () => {
        if (!activeFiltersEl) return;
        const chips = [];
        if (state.filters.requiresAssembly === "yes") chips.push("Зі збіркою");
        else if (state.filters.requiresAssembly === "no") chips.push("Без збірки");
        if (state.filters.requiresInstall === "yes") chips.push("З монтажем");
        else if (state.filters.requiresInstall === "no") chips.push("Без монтажу");
        if (state.filters.product) chips.push(`Виріб: "${state.filters.product}"`);
        activeFiltersEl.innerHTML = chips
            .map(c => `<span class="active-filter-chip">${c}</span>`)
            .join("");
    };

    const applyFilters = () => {
        state.filters.requiresAssembly = filtersRequiresAssembly?.value ?? "";
        state.filters.requiresInstall = filtersRequiresInstall?.value ?? "";
        state.filters.product = productSearch?.value.trim() ?? "";
        filtersModal?.classList.add("hidden");
        updateActiveFilters();
        reloadDetails();
    };

    const resetFilters = () => {
        if (filtersRequiresAssembly) filtersRequiresAssembly.value = "";
        if (filtersRequiresInstall) filtersRequiresInstall.value = "";
        if (productSearch) productSearch.value = "";
        state.filters.requiresAssembly = "";
        state.filters.requiresInstall = "";
        state.filters.product = "";
        filtersModal?.classList.add("hidden");
        updateActiveFilters();
        reloadDetails();
    };

    const openFiltersModal = () => filtersModal?.classList.remove("hidden");
    const closeFiltersModal = () => filtersModal?.classList.add("hidden");

    openFiltersButton?.addEventListener("click", openFiltersModal);
    filtersCloseButtons.forEach(btn => btn.addEventListener("click", closeFiltersModal));
    filtersModal?.addEventListener("click", (e) => {
        if (e.target === filtersModal) closeFiltersModal();
    });
    filtersApplyButton?.addEventListener("click", applyFilters);
    filtersResetButton?.addEventListener("click", resetFilters);
    searchApplyButton?.addEventListener("click", applySearch);
    orderSearch.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            applySearch();
        }
    });
    customerSearch.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            applySearch();
        }
    });
    productSearch?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            applySearch();
        }
    });

    tableWrap.addEventListener("scroll", () => {
        const threshold = 160;
        if (tableWrap.scrollTop + tableWrap.clientHeight >= tableWrap.scrollHeight - threshold) {
            void loadNextPage();
        }
    }, { passive: true });

    void loadNextPage();
});