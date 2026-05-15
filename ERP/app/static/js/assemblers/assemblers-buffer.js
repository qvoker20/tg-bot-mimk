document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector("[data-buffer-page='root']");
    const tableWrap = document.querySelector("[data-buffer-table-wrap]");
    const table = document.querySelector("[data-buffer-table]");
    const header = root?.querySelector(".subpage-header");
    const tbody = document.querySelector("[data-buffer-body]");
    const transferButton = document.querySelector("[data-transfer-selected]");
    const meta = document.querySelector("[data-buffer-meta]");
    const orderSearch = document.querySelector("[data-buffer-search-order]");
    const customerSearch = document.querySelector("[data-buffer-search-customer]");
    const searchApplyButton = document.querySelector("[data-buffer-search-apply]");
    const infoModal = document.querySelector("[data-buffer-info-modal]");
    const infoModalCloseButtons = document.querySelectorAll("[data-buffer-info-modal-close]");
    const infoOrderNumber = document.querySelector("[data-buffer-info-order-number]");
    const infoCustomer = document.querySelector("[data-buffer-info-customer]");
    const infoStatus = document.querySelector("[data-buffer-info-status]");
    const infoDaysToInstall = document.querySelector("[data-buffer-info-days-to-install]");
    const infoDetailsBody = document.querySelector("[data-buffer-info-details-body]");
    const modal = document.querySelector("[data-transfer-modal]");
    const modalTitle = document.querySelector("[data-transfer-title]");
    const modalText = document.querySelector("[data-transfer-text]");
    const modalSelection = document.querySelector("[data-transfer-selection]");
    const modalSelectionList = document.querySelector("[data-transfer-selection-list]");
    const confirmButton = document.querySelector("[data-transfer-confirm]");
    const cancelButtons = document.querySelectorAll("[data-transfer-cancel]");
    const canTransferOrders = root?.dataset.canTransfer === "true";

    // Контекстне меню
    const rowContextMenu = document.querySelector("[data-buffer-row-context-menu]");
    // Модальне вікно деталів — нові поля
    const infoInstallAt = document.querySelector("[data-buffer-info-install-at]");
    const activeFiltersEl = document.querySelector("[data-buffer-active-filters]");
    const infoProductsBody = document.querySelector("[data-buffer-info-products-body]");
    const infoOrderType = document.querySelector("[data-buffer-info-order-type]");
    const infoOrderValue = document.querySelector("[data-buffer-info-order-value]");
    const infoManagerEl = document.querySelector("[data-buffer-info-manager]");
    const infoConstructorEl = document.querySelector("[data-buffer-info-constructor]");
    const infoSubcontractsBody = document.querySelector("[data-buffer-info-subcontracts-body]");
    // Фільтр модаль
    const openFiltersButton = document.querySelector("[data-buffer-open-filters]");
    const filtersModal = document.querySelector("[data-buffer-filters-modal]");
    const filtersSortBy = document.querySelector("[data-buffer-filter-sort-by]");
    const filtersPercentOp = document.querySelector("[data-buffer-filter-percent-op]");
    const filtersPercentValue = document.querySelector("[data-buffer-filter-percent-value]");

    if (!root || !tableWrap || !table || !header || !tbody || !meta || !orderSearch || !customerSearch || !infoModal || !infoOrderNumber || !infoCustomer || !infoStatus || !infoDaysToInstall || !infoDetailsBody || !modal || !modalTitle || !modalText || !modalSelection || !modalSelectionList || !confirmButton) {
        return;
    }

    const withGlobalLoader = (operation, message) => window.ERPLoading?.withLoader
        ? window.ERPLoading.withLoader(operation, { message })
        : operation();

    const showToast = (message, kind = "success") => {
        if (window.ActionToast?.show) {
            window.ActionToast.show(message, kind);
            return;
        }
        meta.textContent = message;
    };

    let tableManager = null;
    const tableToolsInit = window.AssemblersTableTools?.initTable?.({
        table,
        storageKey: table.dataset.tableKey || "assemblers-buffer",
    });
    if (tableToolsInit?.then) {
        tableToolsInit
            .then((manager) => {
                tableManager = manager;
            })
            .catch((e) => console.warn("Failed to initialize table manager", e));
    }

    const state = {
        offset: 0,
        limit: 30,
        loading: false,
        hasMore: true,
        total: 0,
        pendingTransfer: [],
        pendingTransferDetails: [],
        pendingAction: "transfer",
        rowsByOrder: new Map(),
        filters: {
            orderNumber: "",
            customer: "",
            sortBy: "",
            sortDir: "asc",
            statusPercentOp: "",
            statusPercentValue: "",
        },
    };
    let activeController = null;
    let requestVersion = 0;
    let activeContextMenuOrder = null;

    const closeContextMenu = () => {
        rowContextMenu?.classList.add("hidden");
        activeContextMenuOrder = null;
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
        if (normalized.includes("не передано") || normalized.includes("не запущ")) return "is-not-sent";
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

    const setStatusBadgeToNode = (node, status) => {
        if (!node) return;
        node.textContent = "";
        node.appendChild(makeStatusBadge(status));
    };

    const parseNumeric = (value) => {
        const text = String(value ?? "").trim();
        if (!text || text === "—" || text === "-") return null;
        const numeric = Number(text.replace(",", "."));
        return Number.isFinite(numeric) ? numeric : null;
    };

    const displayValue = (value) => {
        if (value == null) return "—";
        const normalized = String(value).trim();
        return normalized || "—";
    };

    const STATUS_COLUMN_INDEXES = new Set([
        2,  // status
        7,  // constructor_percent
        13, // production_status
        18, // materials_status
    ]);

    const syncSelectionState = () => {
        const selected = tbody.querySelectorAll("input[type='checkbox']:checked").length;
        if (transferButton) {
            transferButton.disabled = !canTransferOrders || selected === 0;
        }
        meta.textContent = state.total
            ? `Завантажено ${tbody.children.length} з ${state.total} замовлень. Вибрано: ${selected}.`
            : "Замовлення будуть підгружатись по 30 рядків.";

        if (!canTransferOrders && !state.loading) {
            meta.textContent = state.total
                ? `Завантажено ${tbody.children.length} з ${state.total} замовлень. Доступ лише на перегляд.`
                : "Перегляд буфера доступний, але передача замовлень дозволена лише admin і керівникам збиральників.";
        }
    };

    const renderRow = (row) => {
        const tr = document.createElement("tr");
        tr.dataset.orderNumber = row.order_number;
        tr.dataset.customer = row.client || "—";
        tr.dataset.status = row.status || "—";

        const checkboxCell = document.createElement("td");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.setAttribute("aria-label", `Вибрати замовлення ${row.order_number}`);
        checkbox.addEventListener("change", syncSelectionState);
        checkboxCell.appendChild(checkbox);
        tr.appendChild(checkboxCell);

        const values = [
            row.order_number, row.client, row.status, row.products_hidden, row.signed_at, row.install_at,
            row.days_to_install, row.constructor_percent, row.constructor_total, row.constructor_done,
            row.constructor_completed_at, row.adapter_done, row.adapter_completed_at, row.production_status,
            row.production_total, row.production_done, row.production_completed_at, row.materials_present,
            row.materials_status, row.materials_total, row.materials_constructor_done, row.materials_metal_done,
            row.materials_paint_done, row.manager, row.constructor, row.order_value, row.order_type,
        ];

        values.forEach((value, index) => {
            const td = document.createElement("td");
            td.dataset.colIndex = String(index + 1);
            if (STATUS_COLUMN_INDEXES.has(index)) {
                td.classList.add("assemblers-status-cell");
                td.appendChild(makeStatusBadge(value));
            } else if (index === 6) {
                td.textContent = displayValue(value);
                const deadlineDays = parseNumeric(value);
                if (deadlineDays != null && deadlineDays < 10) {
                    td.classList.add("is-deadline-critical");
                }
            } else {
                td.textContent = value ?? "—";
            }
            tr.appendChild(td);
        });

        if (row.order_number) {
            state.rowsByOrder.set(row.order_number, { ...row });
        }

        tableManager?.applyRow(tr);

        return tr;
    };

    const BUFFER_SUBCONTRACT_FIELDS = [
        { label: "Малярний цех", presenceKey: "paint_shop", statusKey: "paint_status" },
        { label: "Метал", presenceKey: "metal", statusKey: "metal_status" },
        { label: "Шпон", presenceKey: "veneer" },
        { label: "Пластик HPL", presenceKey: "plastic_hpl" },
        { label: "Столярний цех", presenceKey: "joinery_shop" },
        { label: "М'який цех", presenceKey: "soft_shop" },
        { label: "Штучний камінь", presenceKey: "artificial_stone" },
        { label: "Компакт-плита", presenceKey: "compact_plate" },
        { label: "Стільниця ДСП", presenceKey: "dsp_countertop" },
        { label: "Розсувні системи", presenceKey: "sliding_systems" },
        { label: "Скло/дзеркало", presenceKey: "glass_mirror", statusKey: "glass_status" },
        { label: "Рамкові фасади", presenceKey: "frame_facades" },
        { label: "Керамограніт", presenceKey: "ceramic_granite" },
    ];

    const hasBufferShopValue = (value) => {
        if (value == null) return false;
        const text = String(value).trim();
        return text !== "" && text !== "-" && text !== "—";
    };

    const makeBufferPresenceBadge = (value) => {
        const span = document.createElement("span");
        const present = hasBufferShopValue(value);
        span.className = `assemblers-status-badge ${present ? "is-completed" : "is-default"}`;
        span.textContent = present ? "✓" : "немає";
        return span;
    };

    const makeBufferStatusBadge = (value) => {
        const span = document.createElement("span");
        const text = value == null ? "" : String(value).trim();
        if (!text || text === "-" || text === "—") {
            span.className = "buffer-info-status-badge is-default";
            span.textContent = "—";
            return span;
        }
        span.className = `buffer-info-status-badge ${statusClassByValue(text)}`;
        span.textContent = text;
        return span;
    };

    const renderInfoSubcontracts = (row) => {
        if (!infoSubcontractsBody) return;

        const subcontracts = row.subcontracts || {};
        infoSubcontractsBody.innerHTML = "";

        BUFFER_SUBCONTRACT_FIELDS.forEach(({ label, presenceKey, statusKey }) => {
            const tr = document.createElement("tr");

            const nameCell = document.createElement("td");
            nameCell.textContent = label;
            tr.appendChild(nameCell);

            const presenceCell = document.createElement("td");
            presenceCell.appendChild(makeBufferPresenceBadge(subcontracts[presenceKey]));
            tr.appendChild(presenceCell);

            const statusCell = document.createElement("td");
            if (statusKey) {
                statusCell.appendChild(makeBufferStatusBadge(subcontracts[statusKey]));
            } else {
                statusCell.textContent = "—";
            }
            tr.appendChild(statusCell);

            infoSubcontractsBody.appendChild(tr);
        });
    };

    const renderInfoDetails = (row) => {
        const details = [
            ["Вироби", row.products_hidden],
            ["Дата підписання", row.signed_at],
            ["Дата монтажу", row.install_at],
            ["Статус конструктора", row.constructor_percent],
            ["Кількість позицій", row.constructor_total],
            ["Завершено конструктор", row.constructor_done],
            ["Дата завершення конструктором", row.constructor_completed_at],
            ["Завершено технолог", row.adapter_done],
            ["Дата завершення технологом", row.adapter_completed_at],
            ["Статус виробництва", row.production_status],
            ["Кількість запусків", row.production_total],
            ["Запусків завершено", row.production_done],
            ["Дата завершення виробництвом", row.production_completed_at],
        ];

        infoDetailsBody.innerHTML = "";
        details.forEach(([label, value]) => {
            const tr = document.createElement("tr");
            const tdLabel = document.createElement("td");
            const tdValue = document.createElement("td");
            tdLabel.textContent = label;
            if (label.startsWith("Статус")) {
                tdValue.classList.add("buffer-info-status-cell");
                tdValue.appendChild(makeBufferStatusBadge(value));
            } else {
                tdValue.textContent = displayValue(value);
            }
            tr.appendChild(tdLabel);
            tr.appendChild(tdValue);
            infoDetailsBody.appendChild(tr);
        });
    };

    const renderProductList = (row) => {
        if (!infoProductsBody) return;

        const products = Array.isArray(row.products_list) ? row.products_list : [];
        infoProductsBody.innerHTML = "";

        if (!products.length) {
            const tr = document.createElement("tr");
            const td = document.createElement("td");
            td.colSpan = 3;
            td.textContent = "Немає даних про вироби.";
            tr.appendChild(td);
            infoProductsBody.appendChild(tr);
            return;
        }

        products.forEach((product) => {
            const tr = document.createElement("tr");

            const partCell = document.createElement("td");
            const partNumber = String(product.part_number ?? "").trim();
            partCell.textContent = partNumber && partNumber !== "—" ? partNumber : "—";
            tr.appendChild(partCell);

            const nameCell = document.createElement("td");
            nameCell.textContent = displayValue(product.name);
            tr.appendChild(nameCell);

            const statusCell = document.createElement("td");
            statusCell.className = "buffer-info-status-cell";
            statusCell.appendChild(makeBufferStatusBadge(product.status));
            tr.appendChild(statusCell);

            infoProductsBody.appendChild(tr);
        });
    };

    const syncActiveFilters = () => {
        if (!activeFiltersEl) return;

        activeFiltersEl.innerHTML = "";
        const chips = [];

        if (state.filters.sortBy) {
            const sortLabel = state.filters.sortBy === "install_at"
                ? "Дата монтажу"
                : state.filters.sortBy === "days_to_install"
                    ? "Дні до монтажу"
                    : state.filters.sortBy === "status"
                        ? "Загальний статус"
                        : state.filters.sortBy;
            chips.push({
                label: `Сортування: ${sortLabel} (${state.filters.sortDir === "desc" ? "спадання" : "зростання"})`,
                onRemove: () => {
                    state.filters.sortBy = "";
                    state.filters.sortDir = "asc";
                    resetAndReload();
                },
            });
        }

        if (state.filters.statusPercentOp && state.filters.statusPercentValue !== "") {
            const opLabel = state.filters.statusPercentOp === "gt" ? ">" : "<";
            chips.push({
                label: `Статус ${opLabel} ${state.filters.statusPercentValue}%`,
                onRemove: () => {
                    state.filters.statusPercentOp = "";
                    state.filters.statusPercentValue = "";
                    resetAndReload();
                },
            });
        }

        chips.forEach(({ label, onRemove }) => {
            const chip = document.createElement("span");
            chip.className = "buffer-filter-chip";
            chip.textContent = label;

            const button = document.createElement("button");
            button.type = "button";
            button.setAttribute("aria-label", `Скасувати фільтр ${label}`);
            button.textContent = "×";
            button.addEventListener("click", onRemove);
            chip.appendChild(button);

            activeFiltersEl.appendChild(chip);
        });

        openFiltersButton?.classList.toggle("is-active-filter", chips.length > 0);
    };

    const openInfoModalByOrder = (orderNumber) => {
        const row = state.rowsByOrder.get(orderNumber);
        if (!row) return;

        infoOrderNumber.textContent = displayValue(row.order_number);
        infoCustomer.textContent = displayValue(row.client);
        setStatusBadgeToNode(infoStatus, row.status);
        infoDaysToInstall.textContent = displayValue(row.days_to_install);
        if (infoInstallAt) infoInstallAt.textContent = displayValue(row.install_at);
        if (infoOrderType) infoOrderType.textContent = displayValue(row.order_type);
        if (infoOrderValue) infoOrderValue.textContent = displayValue(row.order_value);
        if (infoManagerEl) infoManagerEl.textContent = displayValue(row.manager);
        if (infoConstructorEl) infoConstructorEl.textContent = displayValue(row.constructor);
        renderInfoSubcontracts(row);
        renderInfoDetails(row);
        renderProductList(row);
        infoModal.classList.remove("hidden");
    };

    const closeInfoModal = () => {
        infoModal.classList.add("hidden");
    };

    const getSelectedOrders = () => Array.from(tbody.querySelectorAll("tr[data-order-number] input[type='checkbox']:checked"))
        .map((input) => {
            const row = input.closest("tr[data-order-number]");
            if (!row?.dataset.orderNumber) {
                return null;
            }
            return {
                orderNumber: row.dataset.orderNumber,
                customer: row.dataset.customer || "—",
                status: row.dataset.status || "—",
            };
        })
        .filter(Boolean);

    const renderPendingOrders = () => {
        if (!state.pendingTransferDetails.length) {
            modalSelection.classList.add("hidden");
            modalSelectionList.innerHTML = "";
            return;
        }

        modalSelection.classList.remove("hidden");
        modalSelectionList.innerHTML = state.pendingTransferDetails.map((item) => `
            <article class="buffer-transfer-selection-item">
                <strong>${item.orderNumber}</strong>
                <span>Замовник: ${item.customer}</span>
                <span>Статус: ${item.status}</span>
            </article>
        `).join("");
    };

    const loadNextPage = async () => {
        if (state.loading || !state.hasMore) {
            return;
        }

        const currentVersion = requestVersion;
        state.loading = true;
        syncSelectionState();
        try {
            const params = new URLSearchParams({
                offset: String(state.offset),
                limit: String(state.limit),
                order_number: state.filters.orderNumber,
                customer: state.filters.customer,
                sort_by: state.filters.sortBy,
                sort_dir: state.filters.sortDir,
                status_percent_op: state.filters.statusPercentOp,
                status_percent_value: state.filters.statusPercentValue || "-1",
            });
            activeController = new AbortController();
            const payload = await withGlobalLoader(async () => {
                const response = await fetch(`/assemblers/api/buffer?${params.toString()}`, {
                    cache: "no-store",
                    signal: activeController.signal,
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Не вдалося завантажити буфер");
                }
                return result;
            }, "Завантаження буфера...");

            if (currentVersion !== requestVersion) {
                return;
            }

            payload.rows.forEach((row) => tbody.appendChild(renderRow(row)));
            state.offset += payload.rows.length;
            state.total = payload.total || 0;
            state.hasMore = Boolean(payload.has_more);
            syncSelectionState();
        } catch (error) {
            if (error.name === "AbortError") {
                return;
            }
            meta.textContent = error.message || "Помилка завантаження буфера.";
            state.hasMore = false;
        } finally {
            if (currentVersion === requestVersion) {
                activeController = null;
            }
            state.loading = false;
            syncSelectionState();
        }
    };

    const resetAndReload = () => {
        requestVersion += 1;
        activeController?.abort();
        activeController = null;
        state.loading = false;
        state.offset = 0;
        state.total = 0;
        state.hasMore = true;
        state.pendingTransfer = [];
        state.rowsByOrder.clear();
        tbody.innerHTML = "";
        tableWrap.scrollTop = 0;
        syncSelectionState();
        syncActiveFilters();
        void loadNextPage();
    };

    const applySearch = () => {
        state.filters.orderNumber = orderSearch.value.trim();
        state.filters.customer = customerSearch.value.trim();
        resetAndReload();
    };

    const openModal = (orderNumbers) => {
        if (state.pendingAction === "transfer" && !canTransferOrders) {
            meta.textContent = "Недостатньо прав для передачі замовлень з буфера.";
            return;
        }

        state.pendingTransfer = orderNumbers;
        state.pendingTransferDetails = orderNumbers.map((orderNumber) => {
            const row = tbody.querySelector(`tr[data-order-number='${CSS.escape(orderNumber)}']`);
            return {
                orderNumber,
                customer: row?.dataset.customer || "—",
                status: row?.dataset.status || "—",
            };
        });
        if (state.pendingAction === "close") {
            modalTitle.textContent = "Підтвердити закриття";
            modalText.textContent = `Закрити ${orderNumbers.length} замовлень? Вони підуть у вкладку закритих замовлень.`;
            confirmButton.textContent = "Закрити замовлення";
            confirmButton.classList.add("danger-button");
        } else {
            modalTitle.textContent = "Підтвердити передачу";
            modalText.textContent = `Передати на головну ${orderNumbers.length} замовлень? Після цього вони зникнуть з буфера.`;
            confirmButton.textContent = "Підтвердити";
            confirmButton.classList.remove("danger-button");
        }
        renderPendingOrders();
        modal.classList.remove("hidden");
    };

    const closeModal = () => {
        modal.classList.add("hidden");
        state.pendingTransfer = [];
        state.pendingTransferDetails = [];
        state.pendingAction = "transfer";
        modalSelection.classList.add("hidden");
        modalSelectionList.innerHTML = "";
        confirmButton.classList.remove("danger-button");
        confirmButton.textContent = "Підтвердити";
    };

    const processSelected = async () => {
        if (!state.pendingTransfer.length) {
            closeModal();
            return;
        }

        if (state.pendingAction === "transfer" && !canTransferOrders) {
            closeModal();
            meta.textContent = "Недостатньо прав для передачі замовлень з буфера.";
            return;
        }

        confirmButton.disabled = true;
        try {
            const isCloseAction = state.pendingAction === "close";
            const payload = await withGlobalLoader(async () => {
                const response = await fetch(isCloseAction ? "/assemblers/api/buffer/close" : "/assemblers/api/buffer/transfer", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ order_numbers: state.pendingTransfer }),
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || (isCloseAction ? "Не вдалося закрити замовлення" : "Не вдалося передати замовлення"));
                }
                return result;
            }, isCloseAction ? "Закриття замовлень..." : "Передача замовлень на головну...");

            state.pendingTransfer.forEach((orderNumber) => {
                tbody.querySelector(`tr[data-order-number='${CSS.escape(orderNumber)}']`)?.remove();
            });
            state.total = Math.max(0, state.total - state.pendingTransfer.length);
            syncSelectionState();
            closeModal();
            const resultMessage = payload?.message
                || (isCloseAction ? "Замовлення успішно закрито." : "Замовлення успішно передано на головну.");
            meta.textContent = resultMessage;
            showToast(resultMessage, "success");
            if (tbody.children.length < state.limit && state.hasMore) {
                void loadNextPage();
            }
        } catch (error) {
            meta.textContent = error.message || (state.pendingAction === "close" ? "Помилка закриття замовлень." : "Помилка передачі замовлень.");
            showToast(meta.textContent, "error");
        } finally {
            confirmButton.disabled = false;
        }
    };

    const syncViewportHeight = () => {
        const rootStyles = window.getComputedStyle(root);
        const rootPaddingBottom = Number.parseFloat(rootStyles.paddingBottom || "0");
        const rootRect = root.getBoundingClientRect();
        const tableWrapRect = tableWrap.getBoundingClientRect();
        const availableHeight = Math.floor(rootRect.bottom - tableWrapRect.top - rootPaddingBottom);

        tableWrap.style.height = `${Math.max(320, availableHeight)}px`;
    };

    tableWrap.addEventListener("scroll", () => {
        const threshold = 160;
        if (tableWrap.scrollTop + tableWrap.clientHeight >= tableWrap.scrollHeight - threshold) {
            void loadNextPage();
        }
    }, { passive: true });

    transferButton?.addEventListener("click", () => {
        if (!canTransferOrders) {
            meta.textContent = "Недостатньо прав для передачі замовлень з буфера.";
            return;
        }

        const selected = getSelectedOrders();
        if (!selected.length) {
            return;
        }
        state.pendingAction = "transfer";
        openModal(selected.map((item) => item.orderNumber));
    });

    confirmButton.addEventListener("click", () => {
        void processSelected();
    });

    cancelButtons.forEach((button) => {
        button.addEventListener("click", closeModal);
    });

    infoModalCloseButtons.forEach((button) => {
        button.addEventListener("click", closeInfoModal);
    });

    infoModal.addEventListener("click", (event) => {
        if (event.target === infoModal) {
            closeInfoModal();
        }
    });

    tbody.addEventListener("contextmenu", (event) => {
        const row = event.target.closest("tr[data-order-number]");
        if (!row?.dataset.orderNumber || !rowContextMenu) {
            return;
        }
        event.preventDefault();
        activeContextMenuOrder = row.dataset.orderNumber;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const left = Math.min(event.clientX, vw - 230);
        const top = Math.min(event.clientY, vh - 70);
        rowContextMenu.style.left = `${left + window.scrollX}px`;
        rowContextMenu.style.top = `${top + window.scrollY}px`;
        rowContextMenu.classList.remove("hidden");
    });

    rowContextMenu?.querySelector("[data-buffer-row-action='details']")?.addEventListener("click", () => {
        const orderNumber = activeContextMenuOrder;
        closeContextMenu();
        if (orderNumber) {
            openInfoModalByOrder(orderNumber);
        }
    });

    document.addEventListener("click", (event) => {
        if (rowContextMenu && !rowContextMenu.contains(event.target)) {
            closeContextMenu();
        }
    });

    // Фільтр модаль
    openFiltersButton?.addEventListener("click", () => {
        if (filtersSortBy) filtersSortBy.value = state.filters.sortBy;
        const dirRadio = document.querySelector(`[data-buffer-filter-sort-dir][value='${state.filters.sortDir || "asc"}']`);
        if (dirRadio) dirRadio.checked = true;
        if (filtersPercentOp) filtersPercentOp.value = state.filters.statusPercentOp;
        if (filtersPercentValue) filtersPercentValue.value = state.filters.statusPercentValue;
        filtersModal?.classList.remove("hidden");
    });

    const closeFiltersModal = () => filtersModal?.classList.add("hidden");

    const applyFilters = () => {
        state.filters.sortBy = filtersSortBy?.value || "";
        const dirRadio = document.querySelector("[data-buffer-filter-sort-dir]:checked");
        state.filters.sortDir = dirRadio?.value || "asc";
        state.filters.statusPercentOp = filtersPercentOp?.value || "";
        const pv = Number(filtersPercentValue?.value ?? "");
        state.filters.statusPercentValue = Number.isFinite(pv) && filtersPercentValue?.value !== "" ? String(pv) : "";
        closeFiltersModal();
        resetAndReload();
        syncActiveFilters();
    };

    const resetFilters = () => {
        if (filtersSortBy) filtersSortBy.value = "";
        const asc = document.querySelector("[data-buffer-filter-sort-dir][value='asc']");
        if (asc) asc.checked = true;
        if (filtersPercentOp) filtersPercentOp.value = "";
        if (filtersPercentValue) filtersPercentValue.value = "";
        state.filters.sortBy = "";
        state.filters.sortDir = "asc";
        state.filters.statusPercentOp = "";
        state.filters.statusPercentValue = "";
        closeFiltersModal();
        resetAndReload();
        syncActiveFilters();
    };

    document.querySelectorAll("[data-buffer-filters-close]").forEach((btn) =>
        btn.addEventListener("click", closeFiltersModal));
    document.querySelector("[data-buffer-filters-apply]")?.addEventListener("click", applyFilters);
    document.querySelector("[data-buffer-filters-reset]")?.addEventListener("click", resetFilters);
    filtersModal?.addEventListener("click", (event) => {
        if (event.target === filtersModal) closeFiltersModal();
    });

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

    syncViewportHeight();
    window.addEventListener("resize", syncViewportHeight, { passive: true });
    syncSelectionState();
    void loadNextPage();
});