document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector("[data-application-page]");
    const dayLabel = document.querySelector("[data-app-day-label]");
    const dayDate = document.querySelector("[data-app-day-date]");
    const meta = document.querySelector("[data-app-meta]");
    const taskList = document.querySelector("[data-app-task-list]");
    const shiftButtons = document.querySelectorAll("[data-app-day-shift]");
    const swipeZone = document.querySelector("[data-app-swipe-zone]");
    const pauseModal = document.querySelector("[data-app-pause-modal]");
    const pauseInput = document.querySelector("[data-app-pause-input]");
    const pauseError = document.querySelector("[data-app-pause-error]");
    const pauseConfirm = document.querySelector("[data-app-pause-confirm]");
    const pauseCancelButtons = document.querySelectorAll("[data-app-pause-cancel]");
    const finishModal = document.querySelector("[data-app-finish-modal]");
    const finishList = document.querySelector("[data-app-finish-list]");
    const finishError = document.querySelector("[data-app-finish-error]");
    const finishConfirm = document.querySelector("[data-app-finish-confirm]");
    const finishCancelButtons = document.querySelectorAll("[data-app-finish-cancel]");
    const finishSelectAll = document.querySelector("[data-app-finish-select-all]");
    const finishClearAll = document.querySelector("[data-app-finish-clear-all]");
    const checkLocationButtons = document.querySelectorAll("[data-app-check-location]");
    const locationStatus = document.querySelector("[data-app-location-status]");
    const locationGate = document.querySelector("[data-app-location-gate]");

    if (!root || !dayLabel || !dayDate || !meta || !taskList || !pauseModal || !pauseInput || !pauseError || !pauseConfirm || !finishModal || !finishList || !finishError || !finishConfirm) {
        return;
    }

    const withGlobalLoader = (operation, message) => window.ERPLoading?.withLoader
        ? window.ERPLoading.withLoader(operation, { message })
        : operation();

    const setLocationGateState = (blocked) => {
        root.classList.toggle("is-location-blocked", blocked);
        if (!locationGate) {
            return;
        }
        locationGate.classList.toggle("hidden", !blocked);
        locationGate.setAttribute("aria-hidden", blocked ? "false" : "true");
        if (blocked) {
            locationGate.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    };

    const STATUS_CLASS_MAP = {
        "У черзі": "status-queued",
        "В роботі": "status-in-progress",
        "Пауза": "status-paused",
        "Завершено": "status-completed",
    };

    const TASK_TYPE_LABELS = {
        assembly: "Збирання",
        install: "Монтаж",
        related: "Супутня задача",
    };

    const TASK_TYPE_ALIASES = {
        assembly: "assembly",
        "збірка": "assembly",
        "збирання": "assembly",
        install: "install",
        "монтаж": "install",
        related: "related",
        "супутня": "related",
        "супутня задача": "related",
    };

    const formatDayKey = (dateValue) => {
        if (!(dateValue instanceof Date) || Number.isNaN(dateValue.getTime())) {
            return "";
        }

        const year = dateValue.getFullYear();
        const month = String(dateValue.getMonth() + 1).padStart(2, "0");
        const day = String(dateValue.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    };

    const state = {
        currentDay: root.dataset.initialDay || formatDayKey(new Date()),
        tasks: [],
        pendingPauseTaskId: null,
        pendingFinishTaskId: null,
        pendingFinishProducts: [],
        pendingFinishSelections: new Set(),
    };

    let touchStartX = null;
    let touchStartY = null;

    const toAppDate = (value) => {
        const [year, month, day] = String(value || "").split("-").map(Number);
        if (!year || !month || !day) {
            return null;
        }
        return new Date(year, month - 1, day);
    };

    const formatLongDate = (value) => {
        const parsed = toAppDate(value);
        if (!parsed) {
            return value || "";
        }
        return new Intl.DateTimeFormat("uk-UA", {
            weekday: "long",
            day: "numeric",
            month: "long",
        }).format(parsed);
    };

    const getRelativeDayLabel = (value) => {
        const selected = toAppDate(value);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (!selected) {
            return "День";
        }

        const diff = Math.round((selected.getTime() - today.getTime()) / 86400000);
        if (diff === 0) {
            return "Сьогодні";
        }
        if (diff === 1) {
            return "Завтра";
        }
        if (diff === -1) {
            return "Вчора";
        }
        return diff > 0 ? `Через ${diff} дн.` : `${Math.abs(diff)} дн. тому`;
    };

    const shiftDay = (delta) => {
        const parsed = toAppDate(state.currentDay) || new Date();
        parsed.setDate(parsed.getDate() + delta);
        state.currentDay = formatDayKey(parsed);
        renderDayHeader();
        void loadTasks();
    };

    const escapeHtml = (value) => String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#39;");

    const splitStructuredText = (value) => String(value || "")
        .split(/[,\n;]/)
        .map((item) => item.trim())
        .filter(Boolean);

    const getProductDisplayIndex = (partNumber, fallbackIndex) => {
        const normalizedPart = String(partNumber || "").trim();
        return normalizedPart || String(fallbackIndex + 1);
    };

    const normalizeTaskType = (value) => TASK_TYPE_ALIASES[String(value || "").trim().toLowerCase()] || String(value || "").trim();

    const buildProductsMarkup = (task) => {
        const productNames = splitStructuredText(task.product_name);
        const partNumbers = splitStructuredText(task.part_number);
        const productCount = Math.max(productNames.length, partNumbers.length);

        if (!productCount) {
            const fallbackText = escapeHtml(task.description || "Немає деталей по виробах");
            return `<span class="application-mobile-task-value">${fallbackText}</span>`;
        }

        const items = [];
        for (let index = 0; index < productCount; index += 1) {
            const partNumber = partNumbers[index] || "";
            const displayIndex = getProductDisplayIndex(partNumber, index);
            const productName = productNames[index] || partNumber || `Виріб ${displayIndex}`;
            items.push(`
                <li class="application-mobile-products-item">
                    <span class="application-mobile-products-index">${escapeHtml(displayIndex)}</span>
                    <div class="application-mobile-products-copy">
                        <strong>${escapeHtml(productName)}</strong>
                    </div>
                </li>
            `);
        }

        return `<ol class="application-mobile-products-list">${items.join("")}</ol>`;
    };

    const buildTaskProductsForSelection = (task) => {
        const productNames = splitStructuredText(task.product_name);
        const partNumbers = splitStructuredText(task.part_number);
        const productCount = Math.max(productNames.length, partNumbers.length);
        const items = [];

        for (let index = 0; index < productCount; index += 1) {
            const partNumber = partNumbers[index] || "";
            const displayIndex = getProductDisplayIndex(partNumber, index);
            const productName = productNames[index] || partNumber || `Виріб ${displayIndex}`;
            const selectedPartNumber = partNumber && partNumber !== productName ? partNumber : "";
            items.push({
                checkboxValue: `${index + 1}`,
                product_name: productName,
                part_number: selectedPartNumber,
                display_index: displayIndex,
            });
        }

        if (!items.length && task.description) {
            items.push({
                checkboxValue: "1",
                product_name: task.description,
                part_number: "",
                display_index: "1",
            });
        }

        return items;
    };

    const getTaskById = (taskId) => state.tasks.find((task) => Number(task.id) === Number(taskId)) || null;

    const requiresFinishSelection = (task) => Boolean(task && ["assembly", "install"].includes(normalizeTaskType(task.task_type)));

    const taskTypeBadgeClass = (taskType) => {
        const normalizedType = normalizeTaskType(taskType);
        if (normalizedType === "assembly") {
            return "is-assembly";
        }
        if (normalizedType === "install") {
            return "is-install";
        }
        return "is-related";
    };

    const renderTaskTypeBadge = (taskType) => {
        const normalizedType = normalizeTaskType(taskType);
        const label = TASK_TYPE_LABELS[normalizedType] || taskType || "Не вказано";
        return `<span class="application-mobile-task-type-badge ${taskTypeBadgeClass(normalizedType)}">${escapeHtml(label)}</span>`;
    };

    const buildTaskDetails = (task) => {
        const details = [];

        details.push(`
            <div class="application-mobile-task-row">
                <span class="application-mobile-task-label">Тип</span>
                <div class="application-mobile-task-type-row">${renderTaskTypeBadge(task.task_type)}</div>
            </div>
        `);

        details.push(`
            <div class="application-mobile-task-row">
                <span class="application-mobile-task-label">Вироби</span>
                ${buildProductsMarkup(task)}
            </div>
        `);

        if (task.description) {
            details.push(`
                <div class="application-mobile-task-row">
                    <span class="application-mobile-task-label">Опис</span>
                    <span class="application-mobile-task-value">${escapeHtml(task.description)}</span>
                </div>
            `);
        }

        if (task.constructor_status) {
            details.push(`
                <div class="application-mobile-task-row">
                    <span class="application-mobile-task-label">Статус конструктора</span>
                    <span class="application-mobile-task-value">${escapeHtml(task.constructor_status)}</span>
                </div>
            `);
        }

        return details.join("");
    };

    const buildTaskActions = (task) => {
        if (task.status === "У черзі") {
            if (state.currentDay !== formatDayKey(new Date())) {
                return '<button type="button" class="application-mobile-action ghost" disabled>Доступно у день задачі</button>';
            }
            return '<button type="button" class="application-mobile-action primary" data-task-action="start">Розпочати</button>';
        }
        if (task.status === "В роботі") {
            return [
                '<button type="button" class="application-mobile-action secondary" data-task-action="pause">Пауза</button>',
                '<button type="button" class="application-mobile-action success" data-task-action="finish">Завершити</button>',
            ].join("");
        }
        if (task.status === "Пауза") {
            return [
                '<button type="button" class="application-mobile-action primary" data-task-action="resume">Продовжити</button>',
                '<button type="button" class="application-mobile-action success" data-task-action="finish">Завершити</button>',
            ].join("");
        }
        return "";
    };

    const renderDayHeader = () => {
        dayLabel.textContent = getRelativeDayLabel(state.currentDay);
        dayDate.textContent = formatLongDate(state.currentDay);
    };

    const renderTasks = () => {
        if (!state.tasks.length) {
            taskList.innerHTML = `
                <article class="application-mobile-empty-state">
                    <strong>На цей день задач немає</strong>
                    <span>Спробуйте свайпнути на інший день або дочекайтесь нового призначення.</span>
                </article>
            `;
            return;
        }

        taskList.innerHTML = state.tasks.map((task) => {
            const statusClass = STATUS_CLASS_MAP[task.status] || "status-queued";
            const pauseNote = task.status === "Пауза" && task.pause_reason
                ? `<div class="application-mobile-task-note"><strong>Причина паузи:</strong> ${escapeHtml(task.pause_reason)}</div>`
                : "";
            const actions = buildTaskActions(task);

            return `
                <article class="application-mobile-task-card ${statusClass}" data-task-card data-task-id="${task.id}">
                    <header class="application-mobile-task-head">
                        <div>
                            <p class="application-mobile-task-order">№ ${escapeHtml(task.order_number || "без номера")}</p>
                            <p class="application-mobile-task-customer">${escapeHtml(task.customer || "Замовник не вказаний")}</p>
                        </div>
                        <span class="application-mobile-status-pill ${statusClass}">${escapeHtml(task.status || "У черзі")}</span>
                    </header>
                    <div class="application-mobile-task-grid">
                        ${buildTaskDetails(task)}
                    </div>
                    ${pauseNote}
                    ${actions ? `<div class="application-mobile-task-actions">${actions}</div>` : ""}
                </article>
            `;
        }).join("");
    };

    const setMeta = (text) => {
        meta.textContent = text;
    };

    const loadTasks = async () => {
        setMeta("Завантажуємо ваші задачі...");
        try {
            const payload = await withGlobalLoader(async () => {
                const params = new URLSearchParams({ day: state.currentDay });
                const response = await fetch(`/assemblers/api/app/tasks?${params.toString()}`, { cache: "no-store" });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Не вдалося завантажити задачі");
                }
                return result;
            }, "Завантаження задач...");

            state.currentDay = payload.day || state.currentDay;
            state.tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
            renderDayHeader();
            renderTasks();
            setMeta(state.tasks.length
                ? `Знайдено задач: ${state.tasks.length}. Свайп вліво або вправо перемикає день.`
                : "На обраний день задач немає.");
        } catch (error) {
            state.tasks = [];
            renderTasks();
            setMeta(error.message || "Не вдалося завантажити задачі.");
        }
    };

    const getLocationPayload = () => {
        if (!navigator.geolocation) {
            return Promise.reject(new Error("Браузер не підтримує геолокацію."));
        }

        return new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude, longitude, accuracy } = position.coords;
                    resolve({
                        latitude,
                        longitude,
                        accuracy,
                        label: `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`,
                    });
                },
                () => reject(new Error("Не вдалося отримати локацію. Перевірте дозвіл у браузері.")),
                {
                    enableHighAccuracy: true,
                    timeout: 12000,
                    maximumAge: 0,
                }
            );
        });
    };

    const setLocationStatus = (text, kind = "info") => {
        if (!locationStatus) {
            return;
        }
        locationStatus.textContent = text;
        locationStatus.dataset.statusKind = kind;
    };

    const checkLocationAccess = async () => {
        if (!navigator.geolocation) {
            setLocationGateState(true);
            setLocationStatus("Геолокація не підтримується браузером.", "error");
            return;
        }

        if (navigator.permissions?.query) {
            try {
                const permission = await navigator.permissions.query({ name: "geolocation" });
                if (permission.state === "granted") {
                    setLocationGateState(false);
                    setLocationStatus("Доступ до геолокації дозволено.", "success");
                } else if (permission.state === "denied") {
                    setLocationGateState(true);
                    setLocationStatus("Доступ до геолокації заборонено. Увімкніть дозвіл у браузері.", "error");
                } else {
                    setLocationGateState(false);
                    setLocationStatus("Дозвіл на геолокацію ще не підтверджено.", "info");
                }
                return;
            } catch (error) {
                console.warn("Permission query failed", error);
            }
        }

        try {
            await getLocationPayload();
            setLocationGateState(false);
            setLocationStatus("Доступ до геолокації працює.", "success");
        } catch (error) {
            setLocationGateState(true);
            setLocationStatus(error.message || "Не вдалося перевірити геолокацію.", "error");
        }
    };

    const openPauseModal = (taskId) => {
        state.pendingPauseTaskId = taskId;
        pauseInput.value = "";
        pauseError.textContent = "";
        pauseError.classList.add("hidden");
        pauseModal.classList.remove("hidden");
        pauseModal.setAttribute("aria-hidden", "false");
        window.setTimeout(() => pauseInput.focus(), 0);
    };

    const closePauseModal = () => {
        state.pendingPauseTaskId = null;
        pauseModal.classList.add("hidden");
        pauseModal.setAttribute("aria-hidden", "true");
    };

    const syncFinishToggleButton = (button, selected) => {
        if (!button) {
            return;
        }

        button.classList.toggle("is-selected", selected);
        button.setAttribute("aria-pressed", selected ? "true" : "false");

        const marker = button.querySelector(".application-mobile-finish-marker");
        if (marker) {
            marker.textContent = selected ? "✓" : "";
        }
    };

    const bindFinishSelectionItems = () => {
        finishList.querySelectorAll("[data-app-finish-toggle]").forEach((button) => {
            const toggleSelection = (event) => {
                event.preventDefault();
                event.stopPropagation();

                const productIndex = Number(button.dataset.finishIndex);
                if (!Number.isInteger(productIndex) || !state.pendingFinishProducts[productIndex]) {
                    return;
                }

                const selected = !state.pendingFinishSelections.has(productIndex);
                if (selected) {
                    state.pendingFinishSelections.add(productIndex);
                } else {
                    state.pendingFinishSelections.delete(productIndex);
                }

                if (state.pendingFinishSelections.size) {
                    finishError.textContent = "";
                    finishError.classList.add("hidden");
                }

                syncFinishToggleButton(button, selected);
            };

            button.onclick = null;
            button.onpointerup = null;

            if (window.PointerEvent) {
                button.onpointerup = toggleSelection;
            } else {
                button.onclick = toggleSelection;
            }
        });
    };

    const renderFinishSelectionItems = (task = null) => {
        if (task) {
            state.pendingFinishProducts = buildTaskProductsForSelection(task);
        }
        finishList.innerHTML = state.pendingFinishProducts.map((product, index) => `
            <button
                type="button"
                class="application-mobile-finish-item${state.pendingFinishSelections.has(index) ? " is-selected" : ""}"
                data-app-finish-toggle
                data-finish-index="${index}"
                aria-pressed="${state.pendingFinishSelections.has(index) ? "true" : "false"}"
            >
                <span class="application-mobile-finish-marker" aria-hidden="true">${state.pendingFinishSelections.has(index) ? "✓" : ""}</span>
                <span class="application-mobile-finish-copy">
                    <strong>${escapeHtml(product.display_index || String(index + 1))}. ${escapeHtml(product.product_name)}</strong>
                </span>
            </button>
        `).join("");

        bindFinishSelectionItems();
    };

    const openFinishModal = (task) => {
        state.pendingFinishTaskId = Number(task.id);
        state.pendingFinishSelections = new Set();
        finishError.textContent = "";
        finishError.classList.add("hidden");
        renderFinishSelectionItems(task);
        finishModal.classList.remove("hidden");
        finishModal.setAttribute("aria-hidden", "false");
    };

    const closeFinishModal = () => {
        state.pendingFinishTaskId = null;
        state.pendingFinishProducts = [];
        state.pendingFinishSelections = new Set();
        finishList.innerHTML = "";
        finishError.textContent = "";
        finishError.classList.add("hidden");
        finishModal.classList.add("hidden");
        finishModal.setAttribute("aria-hidden", "true");
    };

    const toggleFinishSelections = (checked) => {
        state.pendingFinishSelections = checked
            ? new Set(state.pendingFinishProducts.map((_, index) => index))
            : new Set();
        renderFinishSelectionItems();
    };

    const collectSelectedFinishProducts = () => Array.from(state.pendingFinishSelections)
            .sort((left, right) => left - right)
            .map((index) => state.pendingFinishProducts[index])
            .filter(Boolean)
            .map((product) => ({
                product_name: product.product_name || "",
                part_number: product.part_number || "",
            }));

    const submitTaskAction = async (taskId, action, extraPayload = {}) => {
        const payload = { action, ...extraPayload };
        if (action === "start" || action === "finish") {
            payload.location = await getLocationPayload();
        }

        const result = await withGlobalLoader(async () => {
            const response = await fetch(`/assemblers/api/app/tasks/${taskId}/action`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.error || "Не вдалося змінити статус задачі");
            }
            return data;
        }, "Оновлення задачі...");

        setMeta(result.message || "Статус задачі оновлено.");
        await loadTasks();
    };

    shiftButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const delta = Number(button.dataset.appDayShift || 0);
            if (!delta) {
                return;
            }
            shiftDay(delta);
        });
    });

    checkLocationButtons.forEach((button) => {
        button.addEventListener("click", () => {
            void checkLocationAccess();
        });
    });

    swipeZone?.addEventListener("touchstart", (event) => {
        const firstTouch = event.changedTouches?.[0];
        touchStartX = firstTouch?.clientX ?? null;
        touchStartY = firstTouch?.clientY ?? null;
    }, { passive: true });

    swipeZone?.addEventListener("touchend", (event) => {
        const firstTouch = event.changedTouches?.[0];
        if (touchStartX === null || touchStartY === null || !firstTouch) {
            return;
        }

        const deltaX = firstTouch.clientX - touchStartX;
        const deltaY = firstTouch.clientY - touchStartY;
        touchStartX = null;
        touchStartY = null;

        if (Math.abs(deltaX) < 60 || Math.abs(deltaX) <= Math.abs(deltaY) * 1.2) {
            return;
        }

        shiftDay(deltaX < 0 ? 1 : -1);
    }, { passive: true });

    taskList.addEventListener("click", async (event) => {
        const actionButton = event.target.closest("[data-task-action]");
        if (!actionButton) {
            return;
        }

        const taskCard = actionButton.closest("[data-task-card]");
        const taskId = Number(taskCard?.dataset.taskId || 0);
        const action = actionButton.dataset.taskAction || "";
        if (!taskId || !action) {
            return;
        }

        if (action === "pause") {
            openPauseModal(taskId);
            return;
        }

        const task = getTaskById(taskId);
        if (action === "finish" && requiresFinishSelection(task)) {
            openFinishModal(task);
            return;
        }

        try {
            await submitTaskAction(taskId, action);
        } catch (error) {
            setMeta(error.message || "Не вдалося оновити задачу.");
        }
    });

    pauseCancelButtons.forEach((button) => {
        button.addEventListener("click", closePauseModal);
    });

    finishCancelButtons.forEach((button) => {
        button.addEventListener("click", closeFinishModal);
    });

    finishSelectAll?.addEventListener("click", () => toggleFinishSelections(true));
    finishClearAll?.addEventListener("click", () => toggleFinishSelections(false));

    pauseConfirm.addEventListener("click", async () => {
        const reason = pauseInput.value.trim();
        if (!state.pendingPauseTaskId) {
            closePauseModal();
            return;
        }
        if (!reason) {
            pauseError.textContent = "Причина паузи обов'язкова.";
            pauseError.classList.remove("hidden");
            pauseInput.focus();
            return;
        }

        pauseError.textContent = "";
        pauseError.classList.add("hidden");

        try {
            await submitTaskAction(state.pendingPauseTaskId, "pause", { pause_reason: reason });
            closePauseModal();
        } catch (error) {
            pauseError.textContent = error.message || "Не вдалося поставити задачу на паузу.";
            pauseError.classList.remove("hidden");
        }
    });

    finishConfirm.addEventListener("click", async () => {
        const task = getTaskById(state.pendingFinishTaskId);
        if (!task) {
            closeFinishModal();
            return;
        }

        const selectedProducts = collectSelectedFinishProducts();
        finishError.textContent = "";
        finishError.classList.add("hidden");

        try {
            await submitTaskAction(task.id, "finish", { selected_products: selectedProducts });
            closeFinishModal();
        } catch (error) {
            finishError.textContent = error.message || "Не вдалося завершити задачу.";
            finishError.classList.remove("hidden");
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !pauseModal.classList.contains("hidden")) {
            closePauseModal();
            return;
        }
        if (event.key === "Escape" && !finishModal.classList.contains("hidden")) {
            closeFinishModal();
        }
    });

    renderDayHeader();
    void checkLocationAccess();
    void loadTasks();
});