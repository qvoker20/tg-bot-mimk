document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector("[data-assemblers-page='closed-orders']");
    const tableWrap = page?.querySelector("[data-assemblers-table-wrap]");
    const table = page?.querySelector("table");
    const tbody = page?.querySelector("[data-closed-orders-body]");
    const meta = page?.querySelector("[data-closed-orders-meta]");

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
    const state = { offset: 0, limit: 30, loading: false, hasMore: true, total: 0 };

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
        tableManager?.applyRow(tr);
        return tr;
    };

    const updateMeta = () => {
        meta.textContent = state.total
            ? `Завантажено ${tbody.children.length} з ${state.total} закритих замовлень.`
            : "Закриті замовлення будуть підгружатись по 30 рядків.";
    };

    const loadNextPage = async () => {
        if (state.loading || !state.hasMore) {
            return;
        }

        state.loading = true;
        updateMeta();

        try {
            const payload = await withGlobalLoader(async () => {
                const response = await fetch(`/assemblers/api/closed-orders?offset=${state.offset}&limit=${state.limit}`, {
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

    void loadNextPage();
});