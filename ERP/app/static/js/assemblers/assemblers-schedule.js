document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector("[data-schedule-page]");
    const tableHead = page?.querySelector("[data-schedule-head]");
    const tableBody = page?.querySelector("[data-schedule-body]");
    const meta = page?.querySelector("[data-schedule-meta]");
    const weekLabel = page?.querySelector("[data-schedule-week-label]");
    const datePicker = page?.querySelector("[data-schedule-date-picker]");
    const prevWeekButton = page?.querySelector("[data-schedule-prev-week]");
    const nextWeekButton = page?.querySelector("[data-schedule-next-week]");
    const todayButton = page?.querySelector("[data-schedule-today]");
    const openModalButton = page?.querySelector("[data-schedule-open-modal]");
    const openEditModalButton = page?.querySelector("[data-schedule-open-edit-modal]");
    const openForceEditModalButton = page?.querySelector("[data-schedule-open-force-edit-modal]");
    const modal = document.querySelector("[data-schedule-modal]");
    const editModal = document.querySelector("[data-schedule-edit-modal]");
    const selectedWorkers = document.querySelector("[data-schedule-selected-workers]");
    const selectedDates = document.querySelector("[data-schedule-selected-dates]");
    const editSelectedWorkers = document.querySelector("[data-schedule-edit-selected-workers]");
    const editSelectedDates = document.querySelector("[data-schedule-edit-selected-dates]");
    const taskTypeInputs = Array.from(document.querySelectorAll("[data-schedule-task-type]"));
    const orderSection = document.querySelector("[data-schedule-order-section]");
    const relatedSection = document.querySelector("[data-schedule-related-section]");
    const relatedDescription = document.querySelector("[data-schedule-related-description]");
    const orderInput = document.querySelector("[data-schedule-order-input]");
    const orderSearchButton = document.querySelector("[data-schedule-order-search]");
    const searchLoader = document.querySelector("[data-schedule-search-loader]");
    const searchMeta = document.querySelector("[data-schedule-search-meta]");
    const searchResultsWrap = document.querySelector("[data-schedule-search-results-wrap]");
    const searchResults = document.querySelector("[data-schedule-search-results]");
    const confirmButton = document.querySelector("[data-schedule-assign-confirm]");
    const editConfirmButton = document.querySelector("[data-schedule-edit-confirm]");
    const assignCloseButtons = document.querySelectorAll("[data-schedule-modal-close]");
    const editCloseButtons = document.querySelectorAll("[data-schedule-edit-modal-close]");
    const editList = document.querySelector("[data-schedule-edit-list]");
    const editMeta = document.querySelector("[data-schedule-edit-meta]");
    const rowsScript = page?.querySelector("[data-schedule-rows]");

    if (!page || !tableHead || !tableBody || !meta || !weekLabel || !datePicker || !prevWeekButton || !nextWeekButton || !todayButton || !openModalButton || !openEditModalButton || !modal || !editModal || !selectedWorkers || !selectedDates || !editSelectedWorkers || !editSelectedDates || !orderSection || !relatedSection || !relatedDescription || !orderInput || !orderSearchButton || !searchLoader || !searchMeta || !searchResultsWrap || !searchResults || !confirmButton || !editConfirmButton || !editList || !editMeta || !rowsScript) {
        return;
    }

    const withGlobalLoader = (operation, message) => window.ERPLoading?.withLoader
        ? window.ERPLoading.withLoader(operation, { message })
        : operation();

    const safeParseRows = () => {
        try {
            const parsed = JSON.parse(rowsScript.textContent || "[]");
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    };

    const rows = safeParseRows();
    const today = page.dataset.scheduleInitialDate ? new Date(`${page.dataset.scheduleInitialDate}T00:00:00`) : new Date();
    const canManageSchedule = page.dataset.scheduleCanManage === "true";
    const isAdmin = page.dataset.scheduleIsAdmin === "true";
    const collapseStorageKey = `erp.schedule.collapsedWorkers:${window.location.pathname}:${page.dataset.scheduleSubdivision || "all"}`;
    const assignments = new Map();
    const selectedCells = new Set();
    const collapsedWorkers = new Set(loadCollapsedWorkers());
    let currentWeekStart = startOfWeek(today);
    let currentEditTaskGroups = [];
    let currentEditAction = "delete";

    const showToast = (message, kind = "success") => {
        if (window.ActionToast?.show) {
            window.ActionToast.show(message, kind);
        }
    };

    function startOfWeek(date) {
        const next = new Date(date);
        const day = next.getDay();
        const diff = day === 0 ? -6 : 1 - day;
        next.setDate(next.getDate() + diff);
        next.setHours(0, 0, 0, 0);
        return next;
    }

    function addDays(date, days) {
        const next = new Date(date);
        next.setDate(next.getDate() + days);
        return next;
    }

    function formatIso(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    function formatDisplayDate(date) {
        return date.toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit", year: "numeric" });
    }

    function formatWeekday(date) {
        return date.toLocaleDateString("uk-UA", { weekday: "short" }).replace(".", "").toUpperCase();
    }

    function getWeekDays() {
        return Array.from({ length: 7 }, (_, index) => addDays(currentWeekStart, index));
    }

    function cellKey(workerId, dateIso) {
        return `${workerId}:${dateIso}`;
    }

    function loadCollapsedWorkers() {
        try {
            const rawValue = window.localStorage.getItem(collapseStorageKey);
            if (!rawValue) {
                return [];
            }

            const parsed = JSON.parse(rawValue);
            return Array.isArray(parsed) ? parsed.map((value) => String(value || "")).filter(Boolean) : [];
        } catch {
            return [];
        }
    }

    function persistCollapsedWorkers() {
        try {
            window.localStorage.setItem(collapseStorageKey, JSON.stringify(Array.from(collapsedWorkers)));
        } catch {
            // Ignore storage failures and keep the UI working in-memory.
        }
    }

    function currentTaskType() {
        return taskTypeInputs.find((input) => input.checked)?.value || "assembly";
    }

    function taskTypeLabel(taskType) {
        if (taskType === "assembly") {
            return "Збірка";
        }
        if (taskType === "install") {
            return "Монтаж";
        }
        return "Супутня задача";
    }

    function taskStatusClass(status) {
        const normalizedStatus = String(status || "").trim().toLowerCase();
        if (normalizedStatus === "у черзі") {
            return "is-queued";
        }
        if (normalizedStatus === "в роботі") {
            return "is-in-progress";
        }
        if (normalizedStatus === "пауза") {
            return "is-paused";
        }
        if (normalizedStatus === "завершено") {
            return "is-completed";
        }
        return "is-default";
    }

    function renderStatusBadge(status) {
        const label = status || "—";
        return `<span class="schedule-task-status-badge ${taskStatusClass(label)}">${label}</span>`;
    }

    function getSelectedCellsData() {
        return Array.from(selectedCells).map((key) => {
            const [workerId, dateIso] = key.split(":");
            const worker = rows.find((row) => String(row.source_user_id) === workerId);
            return {
                workerId,
                workerName: worker?.name || "—",
                dateIso,
            };
        });
    }

    function fillSelectionSummary(targetWorkers, targetDates) {
        const selectedData = getSelectedCellsData();
        const uniqueWorkers = [...new Set(selectedData.map((item) => item.workerName))];
        const uniqueDates = [...new Set(selectedData.map((item) => item.dateIso))].sort();
        targetWorkers.textContent = uniqueWorkers.join(", ") || "—";
        targetDates.textContent = uniqueDates.map((dateIso) => formatDisplayDate(new Date(`${dateIso}T00:00:00`))).join(", ") || "—";
    }

    function getSelectedExistingTaskGroups() {
        const groups = [];
        Array.from(selectedCells).sort().forEach((key) => {
            const [workerId, dateIso] = key.split(":");
            const worker = rows.find((row) => String(row.source_user_id) === workerId);
            const assignment = assignments.get(key) || [];
            groupTasksForCell(assignment).forEach((group) => {
                groups.push({
                    ...group,
                    workerName: worker?.name || "—",
                    displayDate: formatDisplayDate(new Date(`${dateIso}T00:00:00`)),
                });
            });
        });
        return groups;
    }

    function updateMeta() {
        if (!canManageSchedule) {
            meta.textContent = "Перегляд графіка. Керування доступне лише admin та керівникам цього напряму.";
            return;
        }

        if (!selectedCells.size) {
            meta.textContent = "Оберіть одну або кілька комірок, щоб назначити задачу.";
            return;
        }

        const existingTaskCount = getSelectedExistingTaskGroups().length;
        meta.textContent = existingTaskCount
            ? `Обрано ${selectedCells.size} комірок. Знайдено ${existingTaskCount} існуючих задач для можливого видалення.`
            : `Обрано ${selectedCells.size} комірок для призначення задач.`;
    }

    function updateActionButtons() {
        openModalButton.disabled = !canManageSchedule || selectedCells.size === 0;
        openEditModalButton.disabled = !canManageSchedule || getSelectedExistingTaskGroups().length === 0;
        if (openForceEditModalButton) {
            openForceEditModalButton.disabled = !canManageSchedule || !isAdmin || getSelectedExistingTaskGroups().length === 0;
        }
        updateMeta();
    }

    function groupAssignments(tasks) {
        assignments.clear();
        (tasks || []).forEach((task) => {
            const key = cellKey(task.source_user_id, task.scheduled_for);
            const bucket = assignments.get(key) || [];
            bucket.push(task);
            assignments.set(key, bucket);
        });
    }

    async function fetchOrderDetails(orderNumber) {
        const normalizedOrder = String(orderNumber || "").trim();
        if (!normalizedOrder) {
            return [];
        }

        const payload = await withGlobalLoader(async () => {
            const response = await fetch(`/assemblers/api/details/search?order_number=${encodeURIComponent(normalizedOrder)}`, { cache: "no-store" });
            const result = await response.json();
            if (!response.ok || !result.ok) {
                throw new Error(result.error || "Не вдалося знайти деталі замовлення.");
            }
            return result;
        }, "Пошук деталей замовлення...");
        return payload.rows || [];
    }

    async function loadWeekTasks() {
        try {
            const payload = await withGlobalLoader(async () => {
                const response = await fetch(`/assemblers/api/schedule/tasks?subdivision=${encodeURIComponent(page.dataset.scheduleSubdivision || "")}&start_date=${encodeURIComponent(formatIso(currentWeekStart))}`, {
                    cache: "no-store",
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Не вдалося завантажити задачі графіка.");
                }
                return result;
            }, "Завантаження графіка...");

            groupAssignments(payload.tasks || []);
            renderGrid();
            updateActionButtons();
        } catch (error) {
            meta.textContent = error.message || "Не вдалося завантажити задачі графіка.";
        }
    }

    function isCompletedStatus(value) {
        return String(value || "").trim().toLowerCase() === "завершено";
    }

    function isConstructorReady(value) {
        return isCompletedStatus(value);
    }

    function isPartBlockedForAssign(row) {
        const type = currentTaskType();
        const requiresAssembly = row.requires_assembly !== false;
        const requiresInstall = row.requires_install !== false;
        const assemblyDone = Boolean(row.assembly_completed_at) || isCompletedStatus(row.assembly_status);
        const installDone = Boolean(row.install_completed_at) || isCompletedStatus(row.install_status);

        if (type === "assembly") {
            return !requiresAssembly || assemblyDone;
        }
        if (type === "install") {
            return !requiresInstall || installDone;
        }
        return false;

    }

    function renderPartResults(rowsToRender, tableBodyTarget, wrapTarget, metaTarget) {
        tableBodyTarget.innerHTML = "";
        if (!rowsToRender.length) {
            wrapTarget.classList.add("hidden");
            metaTarget.textContent = "За цим номером замовлення деталі не знайдено.";
            return;
        }

        rowsToRender.forEach((row) => {
            const tr = document.createElement("tr");
            const selectCell = document.createElement("td");
            const checkbox = document.createElement("input");
            const constructorReady = isConstructorReady(row.constructor_status);
            const productCompleted = isCompletedStatus(row.product_status);
            const requiresAssembly = row.requires_assembly !== false;
            const requiresInstall = row.requires_install !== false;
            const stageBlocked = isPartBlockedForAssign(row);
            const blocked = !constructorReady || productCompleted || stageBlocked;

            checkbox.disabled = blocked;
            if (blocked) {
                tr.classList.add("schedule-search-row-blocked");
                let blockReason;
                if (!constructorReady) {
                    blockReason = "Ви не можете призначити даний виріб: конструктор ще не завершив роботу";
                } else if (currentTaskType() === "assembly" && !requiresAssembly) {
                    blockReason = "Ви не можете призначити даний виріб: виріб не потребує збірки";
                } else if (currentTaskType() === "install" && !requiresInstall) {
                    blockReason = "Ви не можете призначити даний виріб: виріб не потребує монтажу";
                } else if (productCompleted) {
                    blockReason = "Ви не можете призначити даний виріб: виріб вже повністю завершено";
                } else {
                    blockReason = currentTaskType() === "assembly"
                        ? "Ви не можете призначити даний виріб: збірку вже завершено"
                        : "Ви не можете призначити даний виріб: монтаж вже завершено";
                }
                tr.dataset.blockReason = blockReason;
                tr.title = blockReason;
                checkbox.title = blockReason;
                tr.classList.add("schedule-search-row-has-tooltip");
            }
            checkbox.type = "checkbox";
            checkbox.className = "schedule-part-checkbox";
            checkbox.dataset.partNumber = row.part_number || "";
            checkbox.dataset.customer = row.customer || "";
            checkbox.dataset.productName = row.product_name || "";
            checkbox.dataset.constructorStatus = row.constructor_status || "";
            checkbox.dataset.productStatus = row.product_status || "";
            selectCell.appendChild(checkbox);
            tr.appendChild(selectCell);

            [row.part_number, row.product_name, row.constructor_status, row.product_status].forEach((value) => {
                const td = document.createElement("td");
                td.textContent = value || "—";
                tr.appendChild(td);
            });
            tableBodyTarget.appendChild(tr);
        });
        wrapTarget.classList.remove("hidden");
        metaTarget.textContent = `Знайдено ${rowsToRender.length} частин. Оберіть потрібні.`;
    }

    function getSelectedParts(container) {
        return Array.from(container.querySelectorAll(".schedule-part-checkbox:checked")).map((checkbox) => ({
            part_number: checkbox.dataset.partNumber || "",
            customer: checkbox.dataset.customer || "",
            product_name: checkbox.dataset.productName || "",
            constructor_status: checkbox.dataset.constructorStatus || "",
            product_status: checkbox.dataset.productStatus || "",
        }));
    }

    function splitCsvText(value) {
        return String(value || "")
            .split(",")
            .map((chunk) => chunk.trim())
            .filter(Boolean);
    }

    function joinUniqueTexts(values) {
        const seen = new Set();
        const items = [];

        (values || []).forEach((value) => {
            splitCsvText(value).forEach((chunk) => {
                if (seen.has(chunk)) {
                    return;
                }
                seen.add(chunk);
                items.push(chunk);
            });
        });

        return items.join(", ");
    }

    function groupTasksForCell(tasks) {
        const groups = new Map();

        tasks.forEach((task) => {
            const key = task.task_type === "related"
                ? `${task.task_type}:${task.description}:${task.status}`
                : `${task.task_type}:${task.order_number}:${task.status}`;
            const existing = groups.get(key) || {
                ids: [],
                task_type: task.task_type,
                order_number: task.order_number,
                customer: "",
                status: task.status,
                description: task.description,
                customers: [],
            };

            if (task.id) {
                existing.ids.push(task.id);
            }
            existing.customers.push(task.customer || "");

            groups.set(key, existing);
        });

        return Array.from(groups.values()).map((group) => ({
            ...group,
            ids: Array.from(new Set(group.ids)),
            customer: joinUniqueTexts(group.customers),
        }));
    }

    function renderGrid() {
        const weekDays = getWeekDays();
        datePicker.value = formatIso(currentWeekStart);
        weekLabel.textContent = `${formatDisplayDate(weekDays[0])} - ${formatDisplayDate(weekDays[6])}`;

        tableHead.innerHTML = "";
        const headRow = document.createElement("tr");
        const brigadeHead = document.createElement("th");
        brigadeHead.className = "schedule-sticky-col schedule-col-brigade";
        brigadeHead.textContent = "Бригада";
        headRow.appendChild(brigadeHead);

        const workerHead = document.createElement("th");
        workerHead.className = "schedule-sticky-col-2 schedule-col-worker";
        workerHead.textContent = "Збиральник";
        headRow.appendChild(workerHead);

        weekDays.forEach((day) => {
            const th = document.createElement("th");
            th.className = "schedule-day-head";
            if (formatIso(day) === formatIso(today)) {
                th.classList.add("is-today");
            }
            if (day.getDay() === 0 || day.getDay() === 6) {
                th.classList.add("is-weekend");
            }
            th.innerHTML = `<span>${formatWeekday(day)}</span><strong>${formatDisplayDate(day)}</strong>`;
            headRow.appendChild(th);
        });
        tableHead.appendChild(headRow);

        tableBody.innerHTML = "";
        if (!rows.length) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.colSpan = 9;
            cell.className = "schedule-empty-cell";
            cell.textContent = `Поки що немає збиральників, прив'язаних до підрозділу ${page.dataset.scheduleSubdivision || ""}.`;
            row.appendChild(cell);
            tableBody.appendChild(row);
            return;
        }

        rows.forEach((worker) => {
            const workerId = String(worker.source_user_id || "");
            const isCollapsed = collapsedWorkers.has(workerId);
            const tr = document.createElement("tr");
            if (isCollapsed) {
                tr.classList.add("schedule-row-collapsed");
            }
            const brigadeCell = document.createElement("td");
            brigadeCell.className = "schedule-sticky-col schedule-brigade-cell";
            brigadeCell.textContent = worker.brigade || "—";
            tr.appendChild(brigadeCell);

            const workerCell = document.createElement("td");
            workerCell.className = "schedule-sticky-col-2 schedule-worker-cell";
            workerCell.innerHTML = `
                <div class="schedule-worker-cell-inner">
                    <strong>${worker.name || "—"}</strong>
                    <button type="button" class="schedule-worker-toggle" data-worker-toggle data-worker-id="${workerId}" aria-label="${isCollapsed ? "Розгорнути" : "Згорнути"} рядок" title="${isCollapsed ? "Розгорнути" : "Згорнути"} рядок">
                        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                            <path d="${isCollapsed ? "M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6z" : "M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z"}"></path>
                        </svg>
                    </button>
                </div>
            `;
            tr.appendChild(workerCell);

            weekDays.forEach((day) => {
                const dateIso = formatIso(day);
                const key = cellKey(worker.source_user_id, dateIso);
                const assignment = assignments.get(key) || [];
                const cell = document.createElement("td");
                cell.className = "schedule-slot";
                cell.dataset.cellKey = key;
                cell.dataset.workerId = String(worker.source_user_id || "");
                cell.dataset.workerName = worker.name || "—";
                cell.dataset.dateIso = dateIso;
                cell.dataset.displayDate = formatDisplayDate(day);
                cell.tabIndex = 0;

                if (selectedCells.has(key)) {
                    cell.classList.add("is-selected");
                }
                if (formatIso(day) === formatIso(today)) {
                    cell.classList.add("is-today");
                }
                if (day.getDay() === 0 || day.getDay() === 6) {
                    cell.classList.add("is-weekend");
                }

                const card = document.createElement("div");
                card.className = "schedule-slot-card";
                if (isCollapsed && assignment.length) {
                    card.classList.add("is-collapsed");
                    card.classList.add("has-task");
                    const firstTask = assignment[0];
                    const title = taskTypeLabel(firstTask.task_type);
                    const orderLine = firstTask.task_type === "related"
                        ? `<span>${firstTask.description || "—"}</span>`
                        : `<span>Замовлення: ${firstTask.order_number || "—"}</span>`;
                    const statusLine = `<div class="schedule-task-status-row"><span class="schedule-task-status-label">Статус</span>${renderStatusBadge(firstTask.status)}</div>`;
                    const hiddenCount = assignment.length > 1
                        ? `<span class="schedule-collapsed-more">+${assignment.length - 1}</span>`
                        : "";
                    card.innerHTML = `<div class="schedule-task-item schedule-task-item-${firstTask.task_type}"><strong>${title}</strong>${orderLine}${statusLine}</div>${hiddenCount}`;
                } else if (assignment.length) {
                    card.classList.add("has-task");
                    const uniqueTypes = Array.from(new Set(assignment.map((task) => task.task_type)));
                    if (uniqueTypes.length === 1) {
                        card.classList.add(`task-${uniqueTypes[0]}`);
                    } else if (uniqueTypes.length > 1) {
                        card.classList.add("task-mixed");
                    }
                    const preview = assignment.map((task) => {
                        const title = taskTypeLabel(task.task_type);
                        const orderLine = task.task_type === "related"
                            ? `<span>${task.description || "—"}</span>`
                            : `<span>Замовлення: ${task.order_number || "—"}</span>`;
                        const customerLine = task.task_type === "related"
                            ? ""
                            : `<span>Замовник: ${task.customer || "—"}</span>`;
                        const statusLine = `<div class="schedule-task-status-row"><span class="schedule-task-status-label">Статус</span>${renderStatusBadge(task.status)}</div>`;
                        return `<div class="schedule-task-item schedule-task-item-${task.task_type}"><strong>${title}</strong>${orderLine}${customerLine}${statusLine}</div>`;
                    }).join("");
                    card.innerHTML = preview;
                } else if (isCollapsed) {
                    card.classList.add("is-collapsed");
                    card.innerHTML = "<span>Вільно</span>";
                } else {
                    card.innerHTML = "<span>Вільно</span>";
                }

                cell.appendChild(card);
                tr.appendChild(cell);
            });

            tableBody.appendChild(tr);
        });
    }

    function resetAssignModalState() {
        orderInput.value = "";
        relatedDescription.value = "";
        searchLoader.classList.add("hidden");
        searchResultsWrap.classList.add("hidden");
        searchResults.innerHTML = "";
        searchMeta.textContent = "Введіть номер замовлення, щоб переглянути частини.";
        taskTypeInputs.forEach((input, index) => {
            input.checked = index === 0;
        });
        toggleTaskTypeSections();
    }

    function openModal() {
        if (!canManageSchedule || !selectedCells.size) {
            return;
        }
        fillSelectionSummary(selectedWorkers, selectedDates);
        resetAssignModalState();
        modal.classList.remove("hidden");
    }

    function closeModal() {
        modal.classList.add("hidden");
    }

    function toggleTaskTypeSections() {
        const type = currentTaskType();
        const related = type === "related";
        orderSection.classList.toggle("hidden", related);
        relatedSection.classList.toggle("hidden", !related);
    }

    async function searchOrderDetails() {
        const orderNumber = orderInput.value.trim();
        if (!orderNumber) {
            searchResultsWrap.classList.add("hidden");
            searchResults.innerHTML = "";
            searchMeta.textContent = "Введіть номер замовлення, щоб переглянути частини.";
            return;
        }

        searchResultsWrap.classList.add("hidden");
        searchResults.innerHTML = "";

        try {
            const rowsToRender = await fetchOrderDetails(orderNumber);
            renderPartResults(rowsToRender, searchResults, searchResultsWrap, searchMeta);
        } catch (error) {
            searchMeta.textContent = error.message || "Не вдалося знайти деталі замовлення.";
        }
    }

    async function assignTask() {
        if (!canManageSchedule) {
            meta.textContent = "Недостатньо прав для керування цим графіком.";
            return;
        }

        const type = currentTaskType();
        const orderNumber = orderInput.value.trim();
        const description = relatedDescription.value.trim();
        const selectedParts = getSelectedParts(searchResults);

        if (type === "related" && !description) {
            meta.textContent = "Для супутньої задачі треба вказати опис.";
            return;
        }

        if (type !== "related" && !orderNumber) {
            meta.textContent = "Для збірки або монтажу треба вказати номер замовлення.";
            return;
        }

        if (type !== "related" && !selectedParts.length) {
            meta.textContent = "Оберіть хоча б одну частину замовлення.";
            return;
        }

        confirmButton.disabled = true;

        try {
            const payload = await withGlobalLoader(async () => {
                const response = await fetch("/assemblers/api/schedule/tasks", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        subdivision: page.dataset.scheduleSubdivision || "",
                        task_type: type,
                        order_number: type === "related" ? "" : orderNumber,
                        description: type === "related" ? description : "",
                        selected_parts: type === "related" ? [] : selectedParts,
                        cells: Array.from(selectedCells).map((key) => {
                            const [sourceUserId, scheduledFor] = key.split(":");
                            return {
                                source_user_id: Number(sourceUserId),
                                scheduled_for: scheduledFor,
                            };
                        }),
                    }),
                });
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Не вдалося записати задачі в базу.");
                }
                return result;
            }, "Збереження задач графіка...");

            selectedCells.clear();
            closeModal();
            await loadWeekTasks();
            updateActionButtons();
            meta.textContent = payload.message || "Задачі записано в базу.";
            showToast(payload.message || "Задачі записано в базу.");
        } catch (error) {
            meta.textContent = error.message || "Не вдалося записати задачі в базу.";
            showToast(error.message || "Не вдалося записати задачі в базу.", "error");
        } finally {
            confirmButton.disabled = false;
        }
    }

    function resetEditModalState() {
        currentEditTaskGroups = [];
        currentEditAction = "delete";
        editList.innerHTML = "";
        editMeta.textContent = "Оберіть конкретні задачі зі статусом У черзі для видалення.";
        editConfirmButton.textContent = "Видалити";
    }

    function getCheckedEditTaskGroups() {
        return Array.from(editList.querySelectorAll(".schedule-edit-task-checkbox:checked"))
            .map((checkbox) => currentEditTaskGroups[Number(checkbox.dataset.groupIndex)])
            .filter(Boolean);
    }

    function updateEditMeta() {
        const checkedGroups = getCheckedEditTaskGroups();
        const isForceDelete = currentEditAction === "admin_delete";
        if (!currentEditTaskGroups.length) {
            editMeta.textContent = "У вибраних комірках немає задач для видалення.";
            return;
        }
        if (!checkedGroups.length) {
            editMeta.textContent = isForceDelete
                ? "Оберіть хоча б одну задачу для примусового видалення незалежно від статусу."
                : "Оберіть хоча б одну задачу зі статусом У черзі для видалення.";
            return;
        }
        editMeta.textContent = isForceDelete
            ? `Admin-режим: буде примусово видалено ${checkedGroups.length} задач.`
            : `Буде видалено ${checkedGroups.length} задач.`;
    }

    function renderEditTaskList(taskGroups) {
        currentEditTaskGroups = taskGroups;
        editList.innerHTML = "";

        taskGroups.forEach((group, index) => {
            const tr = document.createElement("tr");
            tr.className = "schedule-edit-row";
            const canEdit = currentEditAction === "admin_delete" || group.status === "У черзі";
            if (!canEdit) {
                tr.classList.add("is-locked");
            }

            const checkboxCell = document.createElement("td");
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "schedule-edit-task-checkbox";
            checkbox.dataset.groupIndex = String(index);
            checkbox.checked = false;
            checkbox.disabled = !canEdit;
            checkboxCell.appendChild(checkbox);
            tr.appendChild(checkboxCell);

            [
                group.workerName || "—",
                group.displayDate || "—",
                taskTypeLabel(group.task_type),
                group.task_type === "related" ? (group.description || "—") : (group.order_number || "—"),
                renderStatusBadge(group.status),
            ].forEach((value) => {
                const td = document.createElement("td");
                if (String(value).includes("schedule-task-status-badge")) {
                    td.innerHTML = value;
                } else {
                    td.textContent = value;
                }
                tr.appendChild(td);
            });

            editList.appendChild(tr);
        });

        updateEditMeta();
    }

    function openEditModal(action = "delete") {
        if (!canManageSchedule) {
            return;
        }

        if (action === "admin_delete" && !isAdmin) {
            meta.textContent = "Ця дія доступна лише адміністратору.";
            return;
        }

        const taskGroups = getSelectedExistingTaskGroups();
        if (!taskGroups.length) {
            meta.textContent = "У вибраних комірках немає задач для видалення.";
            return;
        }

        fillSelectionSummary(editSelectedWorkers, editSelectedDates);
        resetEditModalState();
        currentEditAction = action;
        editConfirmButton.textContent = action === "admin_delete" ? "Примусово видалити" : "Видалити";
        editMeta.textContent = action === "admin_delete"
            ? "Admin-режим: можна видаляти задачі з будь-яким статусом."
            : "Оберіть конкретні задачі зі статусом У черзі для видалення.";
        renderEditTaskList(taskGroups);
        editModal.classList.remove("hidden");
    }

    function closeEditModal() {
        editModal.classList.add("hidden");
    }

    async function applyEdit() {
        if (!canManageSchedule) {
            editMeta.textContent = "Недостатньо прав для керування цим графіком.";
            return;
        }

        const checkedGroups = getCheckedEditTaskGroups();
        if (!checkedGroups.length) {
            editMeta.textContent = currentEditAction === "admin_delete"
                ? "Оберіть хоча б одну задачу для примусового видалення незалежно від статусу."
                : "Оберіть хоча б одну задачу зі статусом У черзі для видалення.";
            return;
        }

        const taskIds = Array.from(new Set(checkedGroups.flatMap((group) => group.ids || [])));
        const payload = {
            subdivision: page.dataset.scheduleSubdivision || "",
            action: currentEditAction,
            task_ids: taskIds,
        };

        editConfirmButton.disabled = true;
        try {
            const result = await withGlobalLoader(async () => {
                const response = await fetch("/assemblers/api/schedule/tasks/edit", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify(payload),
                });
                const data = await response.json();
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Не вдалося оновити задачі графіка.");
                }
                return data;
            }, "Оновлення задач графіка...");

            selectedCells.clear();
            closeEditModal();
            await loadWeekTasks();
            updateActionButtons();
            meta.textContent = result.message || "Задачі видалено.";
            showToast(result.message || "Задачі видалено.");
        } catch (error) {
            editMeta.textContent = error.message || "Не вдалося видалити задачі графіка.";
            showToast(error.message || "Не вдалося видалити задачі графіка.", "error");
        } finally {
            editConfirmButton.disabled = false;
        }
    }

    tableBody.addEventListener("click", (event) => {
        const workerToggle = event.target.closest("[data-worker-toggle]");
        if (workerToggle) {
            event.preventDefault();
            event.stopPropagation();
            const workerId = String(workerToggle.dataset.workerId || "");
            if (!workerId) {
                return;
            }
            if (collapsedWorkers.has(workerId)) {
                collapsedWorkers.delete(workerId);
            } else {
                collapsedWorkers.add(workerId);
            }
            persistCollapsedWorkers();
            renderGrid();
            updateActionButtons();
            return;
        }

        if (!canManageSchedule) {
            return;
        }

        const cell = event.target.closest("[data-cell-key]");
        if (!cell) {
            return;
        }

        const key = cell.dataset.cellKey;
        if (!key) {
            return;
        }

        if (selectedCells.has(key)) {
            selectedCells.delete(key);
        } else {
            selectedCells.add(key);
        }

        renderGrid();
        updateActionButtons();
    });

    prevWeekButton.addEventListener("click", () => {
        currentWeekStart = addDays(currentWeekStart, -7);
        selectedCells.clear();
        void loadWeekTasks();
    });

    nextWeekButton.addEventListener("click", () => {
        currentWeekStart = addDays(currentWeekStart, 7);
        selectedCells.clear();
        void loadWeekTasks();
    });

    todayButton.addEventListener("click", () => {
        currentWeekStart = startOfWeek(today);
        selectedCells.clear();
        void loadWeekTasks();
    });

    datePicker.addEventListener("change", () => {
        if (!datePicker.value) {
            return;
        }
        currentWeekStart = startOfWeek(new Date(`${datePicker.value}T00:00:00`));
        selectedCells.clear();
        void loadWeekTasks();
    });

    openModalButton.addEventListener("click", openModal);
    openEditModalButton.addEventListener("click", () => openEditModal("delete"));
    openForceEditModalButton?.addEventListener("click", () => openEditModal("admin_delete"));
    assignCloseButtons.forEach((button) => {
        button.addEventListener("click", closeModal);
    });
    editCloseButtons.forEach((button) => {
        button.addEventListener("click", closeEditModal);
    });
    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            closeModal();
        }
    });
    editModal.addEventListener("click", (event) => {
        if (event.target === editModal) {
            closeEditModal();
        }
    });
    taskTypeInputs.forEach((input) => {
        input.addEventListener("change", toggleTaskTypeSections);
        input.addEventListener("change", () => {
            if (!orderSection.classList.contains("hidden") && orderInput.value.trim()) {
                void searchOrderDetails();
            }
        });
    });
    editList.addEventListener("change", () => {
        updateEditMeta();
    });
    orderSearchButton.addEventListener("click", () => {
        void searchOrderDetails();
    });
    orderInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            void searchOrderDetails();
        }
    });
    confirmButton.addEventListener("click", assignTask);
    editConfirmButton.addEventListener("click", applyEdit);

    renderGrid();
    updateActionButtons();
    toggleTaskTypeSections();
    void loadWeekTasks();
});