document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector("[data-assemblers-page='closed-orders']");
    const tableWrap = page?.querySelector("[data-assemblers-table-wrap]");
    const table = page?.querySelector("table");
    const tbody = page?.querySelector("[data-closed-orders-body]");
    const meta = page?.querySelector("[data-closed-orders-meta]");
    const orderSearch = page?.querySelector("[data-closed-search-order]");
    const customerSearch = page?.querySelector("[data-closed-search-customer]");
    const orderTypeFilter = page?.querySelector("[data-closed-filter-order-type]");
    const infoModal = document.querySelector("[data-main-info-modal]");
    const infoModalCloseButtons = document.querySelectorAll("[data-main-info-modal-close]");
    const infoOrderNumber = document.querySelector("[data-main-info-order-number]");
    const infoCustomer = document.querySelector("[data-main-info-customer]");
    const infoStatus = document.querySelector("[data-main-info-status]");
    const infoSignedAt = document.querySelector("[data-main-info-signed-at]");
    const infoInstallAt = document.querySelector("[data-main-info-install-at]");
    const infoPlanAssembly = document.querySelector("[data-main-info-plan-assembly]");
    const infoPlanInstall = document.querySelector("[data-main-info-plan-install]");
    const infoFactAssembly = document.querySelector("[data-main-info-fact-assembly]");
    const infoFactInstall = document.querySelector("[data-main-info-fact-install]");
    const infoDetailsBody = document.querySelector("[data-main-info-details-body]");
    const infoAssemblyBody = document.querySelector("[data-main-info-assembly-body]");
    const infoInstallBody = document.querySelector("[data-main-info-install-body]");
    const infoScheduleBody = document.querySelector("[data-main-info-schedule-body]");

    if (!page || !tableWrap || !table || !tbody || !meta) {
        return;
    }

    const withGlobalLoader = (operation, message) => window.ERPLoading?.withLoader
        ? window.ERPLoading.withLoader(operation, { message })
        : operation();

    let tableManager = null;
    window.AssemblersTableTools?.initTable({ table, storageKey: table.dataset.tableKey || "assemblers-closed-orders" })
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
            orderType: "",
        },
    };

    let searchDebounceTimer = null;

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

    const makeStatusBadge = (status) => {
        const span = document.createElement("span");
        span.className = `assemblers-status-badge ${statusClassByValue(status)}`;
        span.textContent = status || "—";
        return span;
    };

    const displayValue = (value) => {
        const text = String(value ?? "").trim();
        return text || "—";
    };

    const setStatusBadgeToNode = (node, value) => {
        if (!node) {
            return;
        }
        node.innerHTML = "";
        node.appendChild(makeStatusBadge(value));
    };

    const parseFlexibleDate = (value) => {
        const text = String(value || "").trim();
        if (!text || text === "—" || text === "-") {
            return null;
        }
        const d = new Date(text);
        return Number.isNaN(d.getTime()) ? null : d;
    };

    const formatUaDate = (date) => {
        if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
            return "—";
        }
        return date.toLocaleDateString("uk-UA");
    };

    const calcPlanSummary = (details, field, requirementField) => {
        const relevant = details.filter((x) => x?.[requirementField] !== false);
        if (!relevant.length) {
            return "—";
        }
        let maxDate = null;
        relevant.forEach((x) => {
            const parsed = parseFlexibleDate(x?.[field]);
            if (parsed && (!maxDate || parsed > maxDate)) {
                maxDate = parsed;
            }
        });
        return maxDate ? formatUaDate(maxDate) : "—";
    };

    const calcFactSummary = (details, field, requirementField) => {
        const relevant = details.filter((x) => x?.[requirementField] !== false);
        if (!relevant.length) {
            return "—";
        }
        const completed = relevant.filter((x) => String(x?.[field] || "").trim() !== "");
        if (completed.length !== relevant.length) {
            return `Не завершено (${completed.length}/${relevant.length})`;
        }
        let maxDate = null;
        completed.forEach((x) => {
            const parsed = parseFlexibleDate(x?.[field]);
            if (parsed && (!maxDate || parsed > maxDate)) {
                maxDate = parsed;
            }
        });
        return maxDate ? formatUaDate(maxDate) : "—";
    };

    const calcDaysBetween = (startStr, endStr) => {
        const s = parseFlexibleDate(startStr);
        const e = parseFlexibleDate(endStr);
        if (!s || !e) {
            return "—";
        }
        const diff = Math.round((e - s) / (1000 * 60 * 60 * 24));
        return diff >= 0 ? String(diff + 1) : "—";
    };

    const TASK_TYPE_LABELS = {
        assembly: "Збірка",
        install: "Монтаж",
        related: "Супутня",
    };

    const renderInfoDetails = (details) => {
        if (!infoDetailsBody) {
            return;
        }
        infoDetailsBody.innerHTML = "";
        if (!details.length) {
            const tr = document.createElement("tr");
            const td = document.createElement("td");
            td.colSpan = 8;
            td.textContent = "Деталізація відсутня.";
            tr.appendChild(td);
            infoDetailsBody.appendChild(tr);
            return;
        }

        details.forEach((d) => {
            const tr = document.createElement("tr");
            [
                d.part_number || "—",
                d.product_name || "—",
                d.item_value || "—",
                d.item_percent != null ? `${d.item_percent}%` : "—",
                d.planned_assembly_due_at || "—",
                d.planned_install_due_at || "—",
                d.assembly_status || "—",
                d.install_status || "—",
            ].forEach((value, i) => {
                const td = document.createElement("td");
                if (i >= 6) {
                    td.appendChild(makeStatusBadge(value));
                } else {
                    td.textContent = displayValue(value);
                }
                tr.appendChild(td);
            });
            infoDetailsBody.appendChild(tr);
        });
    };

    const renderInfoTimeline = (details, stage, targetBody) => {
        if (!targetBody) {
            return;
        }
        targetBody.innerHTML = "";
        const relevant = details.filter((d) => d[`requires_${stage}`] !== false);
        if (!relevant.length) {
            const tr = document.createElement("tr");
            const td = document.createElement("td");
            td.colSpan = 7;
            td.textContent = "Даних немає.";
            tr.appendChild(td);
            targetBody.appendChild(tr);
            return;
        }

        relevant.forEach((d) => {
            const workerKey = stage === "assembly" ? "assembly_worker" : "install_worker";
            const startKey = stage === "assembly" ? "assembly_started_at" : "install_started_at";
            const endKey = stage === "assembly" ? "assembly_completed_at" : "install_completed_at";
            const statusKey = stage === "assembly" ? "assembly_status" : "install_status";
            const tr = document.createElement("tr");
            [
                d.part_number || "—",
                d.product_name || "—",
                d[workerKey] || "—",
                d[startKey] || "—",
                d[endKey] || "—",
                calcDaysBetween(d[startKey], d[endKey]),
                d[statusKey] || "—",
            ].forEach((value, i) => {
                const td = document.createElement("td");
                if (i === 6) {
                    td.appendChild(makeStatusBadge(value));
                } else {
                    td.textContent = displayValue(value);
                }
                tr.appendChild(td);
            });
            targetBody.appendChild(tr);
        });
    };

    const renderInfoSchedule = (scheduleTasks, targetBody) => {
        if (!targetBody) {
            return;
        }
        targetBody.innerHTML = "";
        if (!scheduleTasks.length) {
            const tr = document.createElement("tr");
            const td = document.createElement("td");
            td.colSpan = 4;
            td.textContent = "Запланованих днів немає.";
            tr.appendChild(td);
            targetBody.appendChild(tr);
            return;
        }

        scheduleTasks.forEach((task) => {
            const tr = document.createElement("tr");
            const dateText = task.scheduled_for
                ? formatUaDate(new Date(`${task.scheduled_for}T00:00:00`))
                : "—";
            [
                dateText,
                task.assembler_name || "—",
                TASK_TYPE_LABELS[task.task_type] || displayValue(task.task_type),
                task.status || "—",
            ].forEach((value, i) => {
                const td = document.createElement("td");
                if (i === 3) {
                    td.appendChild(makeStatusBadge(value));
                } else {
                    td.textContent = displayValue(value);
                }
                tr.appendChild(td);
            });
            targetBody.appendChild(tr);
        });
    };

    const closeInfoModal = () => infoModal?.classList.add("hidden");

    const openInfoModal = async (orderNumber) => {
        if (!orderNumber || !infoModal) {
            return;
        }
        try {
            const response = await fetch(`/assemblers/api/main/${encodeURIComponent(orderNumber)}`);
            const result = await response.json();
            if (!response.ok || !result.ok) {
                throw new Error(result.error || "Не вдалося завантажити деталі замовлення.");
            }

            const order = result.order || {};
            const details = Array.isArray(order.details) ? order.details : [];
            const scheduleTasks = Array.isArray(order.schedule_tasks) ? order.schedule_tasks : [];

            if (infoOrderNumber) infoOrderNumber.textContent = displayValue(order.order_number);
            if (infoCustomer) infoCustomer.textContent = displayValue(order.customer);
            setStatusBadgeToNode(infoStatus, order.status);
            if (infoSignedAt) infoSignedAt.textContent = displayValue(order.signed_at);
            if (infoInstallAt) infoInstallAt.textContent = displayValue(order.planned_install_at);

            if (infoPlanAssembly) infoPlanAssembly.textContent = calcPlanSummary(details, "planned_assembly_due_at_input", "requires_assembly");
            if (infoPlanInstall) infoPlanInstall.textContent = calcPlanSummary(details, "planned_install_due_at_input", "requires_install");
            if (infoFactAssembly) infoFactAssembly.textContent = calcFactSummary(details, "assembly_completed_at", "requires_assembly");
            if (infoFactInstall) infoFactInstall.textContent = calcFactSummary(details, "install_completed_at", "requires_install");

            renderInfoDetails(details);
            renderInfoTimeline(details, "assembly", infoAssemblyBody);
            renderInfoTimeline(details, "install", infoInstallBody);
            renderInfoSchedule(scheduleTasks, infoScheduleBody);

            infoModal.classList.remove("hidden");
        } catch (error) {
            meta.textContent = error.message || "Не вдалося завантажити деталі замовлення.";
        }
    };

    const STATUS_COLUMN_INDEXES = new Set([
        3,  // status
        13, // assembly_status
        16, // install_status
        22, // paint_status
        24, // metal_status
        34, // glass_status
        37, // constructor_status
        38, // production_status
        49, // completion_percent
        50, // warehouse_status
    ]);

    const renderRow = (row) => {
        const tr = document.createElement("tr");
        const values = [
            row.order_number, row.customer, row.order_type, row.status, row.note, row.products,
            row.contract_due_at, row.deadline, row.planned_hours, row.actual_hours, row.remaining_hours,
            row.planned_assembly_parts, row.planned_install_parts, row.assembly_status, row.assembly_started_at,
            row.assembly_completed_at, row.install_status, row.install_started_at, row.install_completed_at,
            row.assembly_workers, row.install_workers, row.paint_shop, row.paint_status, row.metal,
            row.metal_status, row.veneer, row.plastic_hpl, row.joinery_shop, row.soft_shop, row.artificial_stone,
            row.compact_plate, row.dsp_countertop, row.sliding_systems, row.glass_mirror, row.glass_status,
            row.frame_facades, row.ceramic_granite, row.constructor_status, row.production_status, row.order_value,
            row.vat, row.install_percent, row.assembly_percent, row.parts_count, row.launches_count,
            row.recorded_at, row.address, row.address_note, row.assembler_stop_note, row.completion_percent,
            row.warehouse_status, row.warehouse_note, row.materials, row.constructor_name, row.assembler_pause_at,
            row.manager_name, row.closed_at, row.closed_by_name, row.closed_by_role,
        ];

        values.forEach((value, index) => {
            const td = document.createElement("td");
            td.dataset.colIndex = String(index);
            if (STATUS_COLUMN_INDEXES.has(index)) {
                td.classList.add("assemblers-status-cell");
                td.appendChild(makeStatusBadge(value));
            } else {
                td.textContent = value ?? "—";
            }
            tr.appendChild(td);
        });
        tr.dataset.orderNumber = String(row.order_number || "").trim();
        tr.classList.add("detail-row", "is-expandable");
        tableManager?.applyRow(tr);
        return tr;
    };

    const updateMeta = () => {
        meta.textContent = state.total
            ? `Завантажено ${tbody.children.length} з ${state.total} закритих замовлень.`
            : "Закриті замовлення будуть підгружатись по 30 рядків.";
    };

    const buildQueryString = (offset, limit) => {
        const params = new URLSearchParams();
        params.set("offset", String(offset));
        params.set("limit", String(limit));
        if (state.filters.orderNumber) {
            params.set("order_number", state.filters.orderNumber);
        }
        if (state.filters.customer) {
            params.set("customer", state.filters.customer);
        }
        if (state.filters.orderType) {
            params.set("order_type", state.filters.orderType);
        }
        return params.toString();
    };

    const renderOrderTypeOptions = (orderTypes) => {
        if (!orderTypeFilter) {
            return;
        }

        const previousValue = orderTypeFilter.value;
        orderTypeFilter.innerHTML = "";

        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = "Усі типи";
        orderTypeFilter.appendChild(defaultOption);

        (Array.isArray(orderTypes) ? orderTypes : []).forEach((type) => {
            const option = document.createElement("option");
            option.value = type;
            option.textContent = type;
            orderTypeFilter.appendChild(option);
        });

        const canRestore = Array.from(orderTypeFilter.options).some((option) => option.value === previousValue);
        orderTypeFilter.value = canRestore ? previousValue : "";
        state.filters.orderType = orderTypeFilter.value;
    };

    const loadFilterOptions = async () => {
        try {
            const params = new URLSearchParams();
            if (state.filters.orderNumber) {
                params.set("order_number", state.filters.orderNumber);
            }
            if (state.filters.customer) {
                params.set("customer", state.filters.customer);
            }
            const query = params.toString();
            const url = query
                ? `/assemblers/api/closed-orders/filter-options?${query}`
                : "/assemblers/api/closed-orders/filter-options";
            const response = await fetch(url, { cache: "no-store" });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || "Не вдалося завантажити типи замовлень");
            }
            renderOrderTypeOptions(payload.order_types || []);
        } catch (error) {
            console.warn("Failed to load closed-order filter options", error);
        }
    };

    const resetAndReload = async () => {
        state.offset = 0;
        state.total = 0;
        state.hasMore = true;
        tbody.innerHTML = "";
        updateMeta();
        await loadNextPage();
    };

    const loadNextPage = async () => {
        if (state.loading || !state.hasMore) {
            return;
        }

        state.loading = true;
        updateMeta();

        try {
            const payload = await withGlobalLoader(async () => {
                const response = await fetch(`/assemblers/api/closed-orders?${buildQueryString(state.offset, state.limit)}`, {
                    cache: "no-store",
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Не вдалося завантажити закриті замовлення");
                }
                return result;
            }, "Завантаження закритих замовлень...");

            payload.rows.forEach((row) => tbody.appendChild(renderRow(row)));
            state.offset += payload.rows.length;
            state.total = payload.total || 0;
            state.hasMore = Boolean(payload.has_more);
            updateMeta();
        } catch (error) {
            meta.textContent = error.message || "Помилка завантаження даних.";
            state.hasMore = false;
        } finally {
            state.loading = false;
            updateMeta();
        }
    };

    tableWrap.addEventListener("scroll", () => {
        const threshold = 160;
        if (tableWrap.scrollTop + tableWrap.clientHeight >= tableWrap.scrollHeight - threshold) {
            void loadNextPage();
        }
    }, { passive: true });

    tbody.addEventListener("click", (event) => {
        const row = event.target.closest("tr[data-order-number]");
        if (!row) {
            return;
        }
        const orderNumber = String(row.dataset.orderNumber || "").trim();
        if (!orderNumber) {
            return;
        }
        void openInfoModal(orderNumber);
    });

    infoModalCloseButtons.forEach((button) => button.addEventListener("click", closeInfoModal));
    if (infoModal) {
        infoModal.addEventListener("click", (event) => {
            if (event.target === infoModal) {
                closeInfoModal();
            }
        });
    }

    const handleSearchChange = () => {
        state.filters.orderNumber = String(orderSearch?.value || "").trim();
        state.filters.customer = String(customerSearch?.value || "").trim();
        if (searchDebounceTimer) {
            clearTimeout(searchDebounceTimer);
        }
        searchDebounceTimer = setTimeout(() => {
            void (async () => {
                await loadFilterOptions();
                await resetAndReload();
            })();
        }, 260);
    };

    const handleOrderTypeChange = () => {
        state.filters.orderType = String(orderTypeFilter?.value || "").trim();
        void resetAndReload();
    };

    orderSearch?.addEventListener("input", handleSearchChange);
    customerSearch?.addEventListener("input", handleSearchChange);
    orderTypeFilter?.addEventListener("change", handleOrderTypeChange);

    void (async () => {
        await loadFilterOptions();
        await loadNextPage();
    })();
});