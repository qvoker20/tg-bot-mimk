document.addEventListener("DOMContentLoaded", () => {
    const rowMenu = document.querySelector("[data-main-row-context-menu]");
    const infoModal = document.querySelector("[data-main-info-modal]");
    const infoModalClose = document.querySelectorAll("[data-main-info-modal-close]");
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
    const subcontractsModal = document.querySelector("[data-main-subcontracts-modal]");
    const subcontractsCloseButtons = document.querySelectorAll("[data-main-subcontracts-close]");
    const subcontractsOrderNumber = document.querySelector("[data-main-subcontracts-order-number]");
    const subcontractsCustomer = document.querySelector("[data-main-subcontracts-customer]");
    const subcontractsStatus = document.querySelector("[data-main-subcontracts-status]");
    const subcontractsBody = document.querySelector("[data-main-subcontracts-body]");
    const page = document.querySelector("[data-assemblers-page='main']");
    const canManageOrders = page?.dataset.canManageOrders === "true";
    const tableWrap = page?.querySelector("[data-assemblers-table-wrap]");
    const table = page?.querySelector("table");
    const tbody = page?.querySelector("[data-main-body]");
    const meta = page?.querySelector("[data-main-meta]");
    const orderSearch = page?.querySelector("[data-main-search-order]");
    const customerSearch = page?.querySelector("[data-main-search-customer]");
    const openFiltersButton = page?.querySelector("[data-main-open-filters]");
    const activeFiltersEl = page?.querySelector("[data-main-active-filters]");
    const filtersModal = document.querySelector("[data-main-filters-modal]");
    const filtersStatus = document.querySelector("[data-main-filter-status]");
    const filtersOrderType = document.querySelector("[data-main-filter-order-type]");
    const filtersDeadline = document.querySelector("[data-main-filter-deadline]");
    const filtersApplyButton = document.querySelector("[data-main-filters-apply]");
    const filtersResetButton = document.querySelector("[data-main-filters-reset]");
    const filtersCloseButtons = document.querySelectorAll("[data-main-filters-close]");
    const modal = document.querySelector("[data-main-modal]");
    const modalForm = document.querySelector("[data-main-modal-form]");
    const modalDetailsBody = document.querySelector("[data-main-modal-details-body]");
    const modalTitle = document.querySelector("[data-main-modal-title]");
    const modalOrderNumber = document.querySelector("[data-main-modal-order-number]");
    const modalCustomer = document.querySelector("[data-main-modal-customer]");
    const modalStatus = document.querySelector("[data-main-modal-status]");
    const modalDeadline = document.querySelector("[data-main-modal-deadline]");
    const modalOrderType = document.querySelector("[data-main-modal-order-type]");
    const modalAddress = document.querySelector("[data-main-modal-address]");
    const modalAddressNote = document.querySelector("[data-main-modal-address-note]");
    const modalNote = document.querySelector("[data-main-modal-note]");
    const noteField = document.querySelector("[data-main-note-field]");
    const noteFillRecent = document.querySelector("[data-main-note-fill-recent]");
    const noteFillPicker = document.querySelector("[data-main-note-fill-picker]");
    const noteFillClear = document.querySelector("[data-main-note-fill-clear]");
    const noteTextPicker = document.querySelector("[data-main-note-text-picker]");
    const noteTextClear = document.querySelector("[data-main-note-text-clear]");
    const modalVat = document.querySelector("[data-main-modal-vat]");
    const modalSubmit = document.querySelector("[data-main-modal-submit]");
    const detailStageModal = document.querySelector("[data-main-detail-stage-modal]");
    const detailStageModalMeta = document.querySelector("[data-main-stage-modal-meta]");
    const detailStageAssemblyStatus = document.querySelector("[data-main-stage-assembly-status]");
    const detailStageInstallStatus = document.querySelector("[data-main-stage-install-status]");
    const detailStageAssemblyCompleteButton = document.querySelector("[data-main-stage-assembly-complete]");
    const detailStageAssemblyResetButton = document.querySelector("[data-main-stage-assembly-reset]");
    const detailStageInstallCompleteButton = document.querySelector("[data-main-stage-install-complete]");
    const detailStageInstallResetButton = document.querySelector("[data-main-stage-install-reset]");
    const detailStageModalCloseButtons = document.querySelectorAll("[data-main-stage-modal-close]");
    const closeButtons = document.querySelectorAll("[data-main-modal-close]");
    const noteToolButtons = Array.from(document.querySelectorAll("[data-main-note-tool]"));
    const notePopovers = Array.from(document.querySelectorAll("[data-main-note-popover]"));
    const noteFillButtons = Array.from(document.querySelectorAll("[data-main-note-fill-color]"));
    const noteTextButtons = Array.from(document.querySelectorAll("[data-main-note-text-color]"));
    const noteEmojiButtons = Array.from(document.querySelectorAll("[data-main-note-emoji]"));

    if (!page || !tableWrap || !table || !tbody || !meta || !orderSearch || !customerSearch || !modal || !modalForm || !modalDetailsBody || !modalTitle || !modalOrderNumber || !modalCustomer || !modalStatus || !modalDeadline || !modalOrderType || !modalAddress || !modalAddressNote || !modalNote || !noteField || !noteFillRecent || !noteFillPicker || !noteFillClear || !noteTextPicker || !noteTextClear || !modalVat || !modalSubmit) {
        return;
    }

    const withGlobalLoader = (operation, message) => window.ERPLoading?.withLoader
        ? window.ERPLoading.withLoader(operation, { message })
        : operation();

    const stageConfirmDialog = document.querySelector("[data-stage-confirm-dialog]");
    const stageConfirmMessage = document.querySelector("[data-stage-confirm-message]");

    const showStyledConfirm = (message) => new Promise((resolve) => {
        if (!stageConfirmDialog || !stageConfirmMessage) {
            resolve(window.confirm(message));
            return;
        }
        stageConfirmMessage.textContent = message;
        stageConfirmDialog.classList.remove("hidden");

        const cleanup = (result) => {
            stageConfirmDialog.classList.add("hidden");
            okBtn.removeEventListener("click", onOk);
            cancelBtn.removeEventListener("click", onCancel);
            stageConfirmDialog.removeEventListener("click", onOverlay);
            resolve(result);
        };
        const okBtn = stageConfirmDialog.querySelector(".stage-confirm-ok");
        const cancelBtn = stageConfirmDialog.querySelector(".stage-confirm-cancel");
        const onOk = () => cleanup(true);
        const onCancel = () => cleanup(false);
        const onOverlay = (e) => { if (e.target === stageConfirmDialog) cleanup(false); };
        okBtn.addEventListener("click", onOk);
        cancelBtn.addEventListener("click", onCancel);
        stageConfirmDialog.addEventListener("click", onOverlay);
    });

    let tableManager = null;
    window.AssemblersTableTools?.initTable({ table, storageKey: table.dataset.tableKey || "assemblers-main" })
        .then(manager => { tableManager = manager; })
        .catch(e => console.warn("Failed to initialize table manager", e));

    const state = {
        offset: 0,
        limit: 30,
        loading: false,
        hasMore: true,
        total: 0,
        rowsByOrder: new Map(),
        rowElements: new Map(),
        activeOrderNumber: "",
        modalLoading: false,
        modalSaving: false,
        contextOrderNumber: "",
        filters: {
            orderNumber: "",
            customer: "",
            status: "",
            orderType: "",
            deadlineBucket: "",
        },
        filterOptions: {
            statuses: [],
            orderTypes: [],
        },
        noteColor: "",
        noteTextColor: "#0f172a",
        notePopover: "",
        activeDetailId: null,
        detailActionState: new Map(),
    };
    let searchTimer = null;
    const NOTE_FILL_RECENT_COLORS_KEY = "assemblers-main-note-fill-recent-colors";
    const NOTE_FILL_PICKER_FALLBACK = "#fff3bf";
    const NOTE_TEXT_PICKER_FALLBACK = "#0f172a";

    const getDetailDateInputs = () => Array.from(modalDetailsBody.querySelectorAll("input[type='date']"));

    const DETAIL_ACTION_DEFAULTS = Object.freeze({
        complete_assembly_now: false,
        reset_assembly_completed: false,
        complete_install_now: false,
        reset_install_completed: false,
    });

    const cloneDetailActionDefaults = () => ({ ...DETAIL_ACTION_DEFAULTS });

    const getDetailIdNumber = (value) => {
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    };

    const getDetailActionState = (detailId) => {
        const normalizedDetailId = getDetailIdNumber(detailId);
        if (normalizedDetailId == null) {
            return cloneDetailActionDefaults();
        }

        if (!state.detailActionState.has(normalizedDetailId)) {
            state.detailActionState.set(normalizedDetailId, cloneDetailActionDefaults());
        }
        return state.detailActionState.get(normalizedDetailId);
    };

    const normalizeStageStatus = (value) => {
        const normalized = String(value || "").trim();
        return normalized || "У черзі";
    };

    const isStageCompleted = (statusValue, completedAtValue) => {
        const normalizedStatus = String(statusValue || "").trim().toLowerCase();
        const normalizedCompletedAt = String(completedAtValue || "").trim();
        return normalizedStatus === "завершено" || Boolean(normalizedCompletedAt && normalizedCompletedAt !== "—");
    };

    const resolveStageStatus = (detail, stage, actionState) => {
        const requiresAssembly = detail.requires_assembly !== false;
        const requiresInstall = detail.requires_install !== false;
        if (stage === "assembly") {
            if (!requiresAssembly) {
                return "Без збірки";
            }
            if (actionState.complete_assembly_now) {
                return "Завершено";
            }
            if (actionState.reset_assembly_completed) {
                return "У черзі";
            }
            return normalizeStageStatus(detail.assembly_status);
        }

        if (!requiresInstall) {
            return "Без монтажу";
        }
        if (actionState.complete_install_now) {
            return "Завершено";
        }
        if (actionState.reset_install_completed) {
            return "У черзі";
        }
        return normalizeStageStatus(detail.install_status);
    };

    const syncDetailActionInputs = (row, detailId) => {
        const actionState = getDetailActionState(detailId);
        row.querySelectorAll("input[data-detail-action-field]").forEach((input) => {
            const fieldName = input.dataset.detailActionField;
            if (!fieldName) {
                return;
            }
            input.value = actionState[fieldName] ? "1" : "0";
        });
    };

    const closeDetailStageModal = () => {
        state.activeDetailId = null;
        detailStageModal?.classList.add("hidden");
    };

    const renderDetailStageModalState = (detail, row) => {
        if (!detailStageModalMeta || !detailStageAssemblyStatus || !detailStageInstallStatus) {
            return;
        }

        const detailId = getDetailIdNumber(detail.detail_id);
        const actionState = getDetailActionState(detailId);
        const assemblyStatus = resolveStageStatus(detail, "assembly", actionState);
        const installStatus = resolveStageStatus(detail, "install", actionState);
        const requiresAssembly = detail.requires_assembly !== false;
        const requiresInstall = detail.requires_install !== false;

        detailStageModalMeta.textContent = `Частина ${displayValue(detail.part_number)} · ${displayValue(detail.product_name)}`;
        setStatusBadgeToNode(detailStageAssemblyStatus, assemblyStatus);
        setStatusBadgeToNode(detailStageInstallStatus, installStatus);

        const assemblyCompleted = assemblyStatus.toLowerCase() === "завершено";
        const installCompleted = installStatus.toLowerCase() === "завершено";

        if (detailStageAssemblyCompleteButton) {
            detailStageAssemblyCompleteButton.hidden = !requiresAssembly || assemblyCompleted;
            detailStageAssemblyCompleteButton.disabled = !canManageOrders;
        }
        if (detailStageAssemblyResetButton) {
            detailStageAssemblyResetButton.hidden = !requiresAssembly || !assemblyCompleted;
            detailStageAssemblyResetButton.disabled = !canManageOrders;
        }
        if (detailStageInstallCompleteButton) {
            detailStageInstallCompleteButton.hidden = !requiresInstall || installCompleted;
            detailStageInstallCompleteButton.disabled = !canManageOrders;
        }
        if (detailStageInstallResetButton) {
            detailStageInstallResetButton.hidden = !requiresInstall || !installCompleted;
            detailStageInstallResetButton.disabled = !canManageOrders;
        }

        syncDetailActionInputs(row, detailId);
    };

    const openDetailStageModal = (detail) => {
        if (!detailStageModal) {
            return;
        }

        const detailId = getDetailIdNumber(detail.detail_id);
        const row = detailId == null ? null : modalDetailsBody.querySelector(`tr[data-detail-id="${detailId}"]`);
        if (!row) {
            return;
        }

        state.activeDetailId = detailId;
        renderDetailStageModalState(detail, row);
        detailStageModal.classList.remove("hidden");
    };

    const applyDetailStageAction = async (stage, actionKind) => {
        if (!canManageOrders || state.activeDetailId == null) {
            return;
        }

        const row = modalDetailsBody.querySelector(`tr[data-detail-id="${state.activeDetailId}"]`);
        if (!row) {
            return;
        }

        const detail = {
            detail_id: state.activeDetailId,
            part_number: row.children[0]?.textContent || "",
            product_name: row.children[1]?.textContent || "",
            assembly_status: row.dataset.assemblyStatus || "",
            install_status: row.dataset.installStatus || "",
            assembly_completed_at: row.dataset.assemblyCompletedAt || "",
            install_completed_at: row.dataset.installCompletedAt || "",
            requires_assembly: row.dataset.requiresAssembly !== "false",
            requires_install: row.dataset.requiresInstall !== "false",
        };

        const actionState = getDetailActionState(state.activeDetailId);

        if (stage === "assembly" && actionKind === "complete") {
            if (!detail.requires_assembly) {
                return;
            }
            const isConfirmed = await showStyledConfirm("Завершити Збірку достроково?");
            if (!isConfirmed) {
                return;
            }
            actionState.complete_assembly_now = true;
            actionState.reset_assembly_completed = false;
        }
        if (stage === "assembly" && actionKind === "reset") {
            if (!detail.requires_assembly) {
                return;
            }
            const isConfirmed = await showStyledConfirm("Скасувати завершення Збірки?");
            if (!isConfirmed) {
                return;
            }
            actionState.complete_assembly_now = false;
            actionState.reset_assembly_completed = true;
        }
        if (stage === "install" && actionKind === "complete") {
            if (!detail.requires_install) {
                return;
            }
            const isConfirmed = await showStyledConfirm("Завершити Монтаж достроково?");
            if (!isConfirmed) {
                return;
            }
            actionState.complete_install_now = true;
            actionState.reset_install_completed = false;
        }
        if (stage === "install" && actionKind === "reset") {
            if (!detail.requires_install) {
                return;
            }
            const isConfirmed = await showStyledConfirm("Скасувати завершення Монтажу?");
            if (!isConfirmed) {
                return;
            }
            actionState.complete_install_now = false;
            actionState.reset_install_completed = true;
        }

        renderDetailStageModalState(detail, row);
    };

    const collectDetailsPayload = () => {
        return Array.from(modalDetailsBody.querySelectorAll("input[data-detail-id][data-detail-field]"))
            .reduce((accumulator, input) => {
                const detailId = Number(input.dataset.detailId);
                if (!Number.isFinite(detailId)) {
                    return accumulator;
                }

                let detail = accumulator.find((item) => item.detail_id === detailId);
                if (!detail) {
                    detail = {
                        detail_id: detailId,
                        planned_assembly_due_at: "",
                        planned_install_due_at: "",
                        item_percent: 0,
                        requires_assembly: true,
                        requires_install: true,
                        complete_assembly_now: false,
                        reset_assembly_completed: false,
                        complete_install_now: false,
                        reset_install_completed: false,
                    };
                    accumulator.push(detail);
                }

                if (input.dataset.detailField === "planned_assembly_due_at") {
                    detail.planned_assembly_due_at = input.value || "";
                }
                if (input.dataset.detailField === "planned_install_due_at") {
                    detail.planned_install_due_at = input.value || "";
                }
                if (input.dataset.detailField === "item_percent") {
                    detail.item_percent = parseFloat(input.value) || 0;
                }
                if (input.dataset.detailField === "requires_assembly") {
                    detail.requires_assembly = input.checked;
                }
                if (input.dataset.detailField === "requires_install") {
                    detail.requires_install = input.checked;
                }
                if (input.dataset.detailField === "reset_assembly_completed") {
                    detail.reset_assembly_completed = input.value === "1";
                }
                if (input.dataset.detailField === "complete_assembly_now") {
                    detail.complete_assembly_now = input.value === "1";
                }
                if (input.dataset.detailField === "reset_install_completed") {
                    detail.reset_install_completed = input.value === "1";
                }
                if (input.dataset.detailField === "complete_install_now") {
                    detail.complete_install_now = input.value === "1";
                }

                return accumulator;
            }, []);
    };

    const persistMainOrderChanges = async ({ loadingMessage = "Збереження змін...", closeAfterSave = true } = {}) => {
        const payload = await withGlobalLoader(async () => {
            const response = await fetch(`/assemblers/api/main/${encodeURIComponent(state.activeOrderNumber)}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    address: modalAddress.value,
                    address_note: modalAddressNote.value,
                    note: modalNote.value,
                    note_color: state.noteColor,
                    note_text_color: state.noteTextColor,
                    vat: modalVat.checked,
                    details: collectDetailsPayload(),
                }),
            });
            const result = await response.json();
            if (!response.ok || !result.ok) {
                throw new Error(result.error || "Не вдалося зберегти зміни.");
            }
            return result;
        }, loadingMessage);

        if (state.noteColor) {
            pushRecentFillColor(state.noteColor);
        }
        renderRecentFillColors();
        applyOrderCard(payload.order);
        await refreshLoadedRows();

        if (closeAfterSave) {
            closeModal();
        }

        return payload;
    };

    const updateDateInputState = (input) => {
        if (!input) return;
        const hasValue = String(input.value || "").trim().length > 0;
        input.classList.toggle("has-value", hasValue);
        input.classList.toggle("is-empty", !hasValue);
        };

    const cellIndexes = {
        order_number: 0,
        customer: 1,
        order_type: 2,
        status: 3,
        note: 4,
        deadline: 7,
        address: 48,
        address_note: 49,
    };

    const displayValue = (value) => {
        if (value == null) {
            return "—";
        }
        const normalized = String(value).trim();
        return normalized || "—";
    };

    const normalizeHexColor = (value) => {
        const raw = String(value || "").trim();
        if (!/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(raw)) {
            return "";
        }
        if (raw.length === 4) {
            return `#${raw.slice(1).split("").map((char) => char + char).join("")}`.toLowerCase();
        }
        return raw.toLowerCase();
    };

    const hexToRgba = (hexColor, alpha) => {
        const normalized = normalizeHexColor(hexColor);
        if (!normalized) {
            return "";
        }
        const value = normalized.slice(1);
        const red = Number.parseInt(value.slice(0, 2), 16);
        const green = Number.parseInt(value.slice(2, 4), 16);
        const blue = Number.parseInt(value.slice(4, 6), 16);
        return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
    };

    const getRecentFillColors = () => {
        try {
            const raw = window.localStorage.getItem(NOTE_FILL_RECENT_COLORS_KEY);
            const parsed = raw ? JSON.parse(raw) : [];
            if (!Array.isArray(parsed)) {
                return [];
            }
            return parsed
                .map((color) => normalizeHexColor(color))
                .filter((color, index, array) => color && array.indexOf(color) === index)
                .slice(0, 6);
        } catch (error) {
            console.warn("Failed to read recent note colors", error);
            return [];
        }
    };

    const saveRecentFillColors = (colors) => {
        try {
            window.localStorage.setItem(NOTE_FILL_RECENT_COLORS_KEY, JSON.stringify(colors));
        } catch (error) {
            console.warn("Failed to save recent note colors", error);
        }
    };

    const updateNoteToolButtonsState = () => {
        noteToolButtons.forEach((button) => {
            button.classList.toggle("is-active", button.dataset.mainNoteTool === state.notePopover);
        });
    };

    const updateNoteColorButtonsState = () => {
        const activeFillColor = normalizeHexColor(state.noteColor);
        const activeTextColor = normalizeHexColor(state.noteTextColor) || NOTE_TEXT_PICKER_FALLBACK;
        document.querySelectorAll("[data-main-note-fill-color], [data-main-note-fill-recent-color]").forEach((button) => {
            const buttonColor = normalizeHexColor(button.dataset.mainNoteFillColor || button.dataset.mainNoteFillRecentColor || "");
            button.classList.toggle("is-active", Boolean(activeFillColor) && buttonColor === activeFillColor);
        });
        noteTextButtons.forEach((button) => {
            const buttonColor = normalizeHexColor(button.dataset.mainNoteTextColor || "");
            button.classList.toggle("is-active", buttonColor === activeTextColor);
        });
    };

    const openNotePopover = (popoverName) => {
        state.notePopover = state.notePopover === popoverName ? "" : popoverName;
        notePopovers.forEach((popover) => {
            popover.classList.toggle("hidden", popover.dataset.mainNotePopover !== state.notePopover);
        });
        updateNoteToolButtonsState();
    };

    const closeNotePopovers = () => {
        state.notePopover = "";
        notePopovers.forEach((popover) => popover.classList.add("hidden"));
        updateNoteToolButtonsState();
    };

    const renderRecentFillColors = () => {
        noteFillRecent.innerHTML = "";
        const recentColors = getRecentFillColors();

        if (!recentColors.length) {
            const placeholder = document.createElement("span");
            placeholder.className = "main-order-note-recent-empty";
            placeholder.textContent = "Ще немає історії";
            noteFillRecent.appendChild(placeholder);
            updateNoteColorButtonsState();
            return;
        }

        recentColors.forEach((color) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "main-order-note-swatch is-recent";
            button.dataset.mainNoteFillRecentColor = color;
            button.title = color;
            button.setAttribute("aria-label", `Останній колір ${color}`);
            button.style.setProperty("--swatch-color", color);
            noteFillRecent.appendChild(button);
        });

        updateNoteColorButtonsState();
    };

    const pushRecentFillColor = (color) => {
        const normalized = normalizeHexColor(color);
        if (!normalized) {
            return;
        }
        const nextColors = [normalized, ...getRecentFillColors().filter((item) => item !== normalized)].slice(0, 6);
        saveRecentFillColors(nextColors);
    };

    const applyNoteAppearanceToField = (fillColor, textColor) => {
        const normalizedFill = normalizeHexColor(fillColor);
        const normalizedText = normalizeHexColor(textColor) || NOTE_TEXT_PICKER_FALLBACK;
        state.noteColor = normalizedFill;
        state.noteTextColor = normalizedText;
        noteField.classList.toggle("has-note-fill", Boolean(normalizedFill));
        noteField.style.setProperty("--main-note-fill", normalizedFill ? hexToRgba(normalizedFill, 0.22) : "#ffffff");
        noteField.style.setProperty("--main-note-border", normalizedFill ? hexToRgba(normalizedFill, 0.52) : "#d5deea");
        noteField.style.setProperty("--main-note-text", normalizedText);
        noteField.style.setProperty("--main-note-accent", normalizedFill || normalizedText || "#dd6d20");
        noteFillPicker.value = normalizedFill || NOTE_FILL_PICKER_FALLBACK;
        noteTextPicker.value = normalizedText || NOTE_TEXT_PICKER_FALLBACK;
        updateNoteColorButtonsState();
    };

    const applyNoteAppearanceToCell = (cell, fillColor, textColor) => {
        if (!cell) {
            return;
        }
        const normalizedFill = normalizeHexColor(fillColor);
        const normalizedText = normalizeHexColor(textColor) || "";
        cell.style.backgroundColor = normalizedFill ? hexToRgba(normalizedFill, 0.22) : "";
        cell.style.boxShadow = normalizedFill ? `inset 0 0 0 1px ${hexToRgba(normalizedFill, 0.38)}` : "";
        if (normalizedText) {
            cell.style.color = normalizedText;
            cell.style.setProperty("color", normalizedText, "important");
        } else {
            cell.style.color = "";
        }
    };

    const insertEmojiIntoNote = (emoji) => {
        if (!emoji || modalNote.disabled) {
            return;
        }
        const start = Number.isInteger(modalNote.selectionStart) ? modalNote.selectionStart : modalNote.value.length;
        const end = Number.isInteger(modalNote.selectionEnd) ? modalNote.selectionEnd : modalNote.value.length;
        modalNote.setRangeText(`${emoji} `, start, end, "end");
        modalNote.focus();
        modalNote.dispatchEvent(new Event("input", { bubbles: true }));
    };

    const formatHoursMinutes = (value) => {
        const text = String(value ?? "").trim();
        if (!text || text === "—" || text === "-") {
            return "—";
        }

        const numeric = Number(text.replace(",", "."));
        if (!Number.isFinite(numeric)) {
            return displayValue(value);
        }

        const sign = numeric < 0 ? "-" : "";
        const totalMinutes = Math.round(Math.abs(numeric) * 60);
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes % 60;

        if (hours === 0) {
            return `${sign}${minutes} хв`;
        }
        if (minutes === 0) {
            return `${sign}${hours} год`;
        }
        return `${sign}${hours} год ${minutes} хв`;
    };

    const parseNumeric = (value) => {
        const text = String(value ?? "").trim();
        if (!text || text === "—" || text === "-") {
            return null;
        }
        const numeric = Number(text.replace(",", "."));
        return Number.isFinite(numeric) ? numeric : null;
    };

    const setCellValue = (rowElement, index, value) => {
        const cell = rowElement?.children?.[index];
        if (cell) {
            cell.textContent = displayValue(value);
        }
    };

    const setModalBusy = (busy) => {
        state.modalLoading = busy;
        modalSubmit.disabled = !canManageOrders || busy || state.modalSaving;
        modalAddress.disabled = !canManageOrders || busy || state.modalSaving;
        modalAddressNote.disabled = !canManageOrders || busy || state.modalSaving;
        modalNote.disabled = !canManageOrders || busy || state.modalSaving;
        noteFillPicker.disabled = !canManageOrders || busy || state.modalSaving;
        noteFillClear.disabled = !canManageOrders || busy || state.modalSaving;
        noteTextPicker.disabled = !canManageOrders || busy || state.modalSaving;
        noteTextClear.disabled = !canManageOrders || busy || state.modalSaving;
        noteToolButtons.forEach((button) => {
            button.disabled = !canManageOrders || busy || state.modalSaving;
        });
        noteFillButtons.forEach((button) => {
            button.disabled = !canManageOrders || busy || state.modalSaving;
        });
        noteTextButtons.forEach((button) => {
            button.disabled = !canManageOrders || busy || state.modalSaving;
        });
        noteEmojiButtons.forEach((button) => {
            button.disabled = !canManageOrders || busy || state.modalSaving;
        });
        noteFillRecent.querySelectorAll("button").forEach((button) => {
            button.disabled = !canManageOrders || busy || state.modalSaving;
        });
        getDetailDateInputs().forEach((input) => {
            input.disabled = !canManageOrders || busy || state.modalSaving;
        });
    };

    const setModalSaving = (saving) => {
        state.modalSaving = saving;
        modalSubmit.disabled = !canManageOrders || saving || state.modalLoading;
        modalAddress.disabled = !canManageOrders || saving || state.modalLoading;
        modalAddressNote.disabled = !canManageOrders || saving || state.modalLoading;
        modalNote.disabled = !canManageOrders || saving || state.modalLoading;
        noteFillPicker.disabled = !canManageOrders || saving || state.modalLoading;
        noteFillClear.disabled = !canManageOrders || saving || state.modalLoading;
        noteTextPicker.disabled = !canManageOrders || saving || state.modalLoading;
        noteTextClear.disabled = !canManageOrders || saving || state.modalLoading;
        noteToolButtons.forEach((button) => {
            button.disabled = !canManageOrders || saving || state.modalLoading;
        });
        noteFillButtons.forEach((button) => {
            button.disabled = !canManageOrders || saving || state.modalLoading;
        });
        noteTextButtons.forEach((button) => {
            button.disabled = !canManageOrders || saving || state.modalLoading;
        });
        noteEmojiButtons.forEach((button) => {
            button.disabled = !canManageOrders || saving || state.modalLoading;
        });
        noteFillRecent.querySelectorAll("button").forEach((button) => {
            button.disabled = !canManageOrders || saving || state.modalLoading;
        });
        getDetailDateInputs().forEach((input) => {
            input.disabled = !canManageOrders || saving || state.modalLoading;
        });
        modalSubmit.textContent = saving ? "Збереження..." : "Зберегти";
    };

    const parseYmd = (value) => {
    const raw = String(value || "").trim();
    if (!raw) return null;
    const d = new Date(raw + "T00:00:00");
    return Number.isNaN(d.getTime()) ? null : d;
};

const formatUaDate = (dateObj) => {
    if (!dateObj) return "—";
    const dd = String(dateObj.getDate()).padStart(2, "0");
    const mm = String(dateObj.getMonth() + 1).padStart(2, "0");
    const yyyy = dateObj.getFullYear();
    return dd + "." + mm + "." + yyyy;
};

const formatUaDateTime = (value) => {
    if (!value) return "—";
    const dateObj = value instanceof Date ? value : new Date(String(value));
    if (Number.isNaN(dateObj.getTime())) return displayValue(value);
    const dd = String(dateObj.getDate()).padStart(2, "0");
    const mm = String(dateObj.getMonth() + 1).padStart(2, "0");
    const yyyy = dateObj.getFullYear();
    const hh = String(dateObj.getHours()).padStart(2, "0");
    const min = String(dateObj.getMinutes()).padStart(2, "0");
    return `${dd}.${mm}.${yyyy} ${hh}:${min}`;
};

const parseFlexibleDate = (value) => {
    const raw = String(value || "").trim();
    if (!raw || raw === "—") return null;

    const direct = new Date(raw);
    if (!Number.isNaN(direct.getTime())) return direct;

    const match = raw.match(/^(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2}))?$/);
    if (!match) return null;

    const day = Number(match[1]);
    const month = Number(match[2]) - 1;
    const year = Number(match[3]);
    const hour = Number(match[4] || 0);
    const minute = Number(match[5] || 0);
    const parsed = new Date(year, month, day, hour, minute);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const calcPlanSummary = (details, fieldName, requiredField = null) => {
    const relevant = requiredField
        ? details.filter((x) => x?.[requiredField] !== false)
        : details;

    const total = relevant.length;
    const filled = relevant.filter((x) => String(x[fieldName] || "").trim() !== "");
    const allPlanned = total > 0 && filled.length === total;

    if (!allPlanned) {
        return { text: "План не повний", complete: false };
    }

    let maxDate = null;
    filled.forEach((x) => {
        const d = parseYmd(x[fieldName]);
        if (d && (!maxDate || d > maxDate)) maxDate = d;
    });

    return { text: formatUaDate(maxDate), complete: true };
};

const calcFactSummary = (details, completedField, requiredField = null) => {
    const relevant = requiredField
        ? details.filter((x) => x?.[requiredField] !== false)
        : details;

    const total = relevant.length;
    if (!total) {
        return { text: "—", complete: false };
    }

    const completed = relevant.filter((x) => String(x?.[completedField] || "").trim() !== "");
    if (completed.length !== total) {
        return { text: `Не завершено (${completed.length}/${total})`, complete: false };
    }

    let maxDate = null;
    completed.forEach((x) => {
        const parsed = parseFlexibleDate(x?.[completedField]);
        if (parsed && (!maxDate || parsed > maxDate)) {
            maxDate = parsed;
        }
    });

    if (maxDate) {
        return { text: formatUaDate(maxDate), complete: true };
    }

    return { text: displayValue(completed[completed.length - 1]?.[completedField]), complete: true };
};

const applySummaryField = (node, summary) => {
    if (!node) return;
    node.textContent = summary.text;
    node.classList.toggle("is-plan-incomplete", !summary.complete);
    node.classList.toggle("is-plan-complete", summary.complete);
};

const formatOrderStageSummary = (order, stageKey) => {
    const status = displayValue(order?.[`${stageKey}_status`]);
    const startedAt = displayValue(order?.[`${stageKey}_started_at`]);
    const completedAt = displayValue(order?.[`${stageKey}_completed_at`]);
    const hours = formatHoursMinutes(order?.[`${stageKey}_hours`]);
    const workers = displayValue(order?.[`${stageKey}_workers_count`]);

    return [status, `${startedAt} → ${completedAt}`, `годин: ${hours}`, `робочих: ${workers}`].join(" · ");
};

const renderInfoDetails = (details) => {
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
        const row = document.createElement("tr");
        const detailActionState = cloneDetailActionDefaults();
        const effectiveAssemblyStatus = resolveStageStatus(d, "assembly", detailActionState);
        const effectiveInstallStatus = resolveStageStatus(d, "install", detailActionState);
        const cells = [
            d.part_number || "—",
            d.product_name || "—",
            d.item_value || "—",
            d.item_percent != null ? String(d.item_percent) + "%" : "—",
            d.planned_assembly_due_at || "—",
            d.planned_install_due_at || "—",
            effectiveAssemblyStatus,
            effectiveInstallStatus,
        ];

        cells.forEach((value) => {
            const td = document.createElement("td");
            td.textContent = displayValue(value);
            row.appendChild(td);
        });
        infoDetailsBody.appendChild(row);
    });
};

const openInfoModal = async (orderNumber) => {
    const response = await fetch("/assemblers/api/main/" + encodeURIComponent(orderNumber));
    const result = await response.json();
    if (!response.ok || !result.ok) {
        showToast(result.error || "Не вдалося завантажити дані.", "error");
        return;
    }

    const order = result.order || {};
    const details = Array.isArray(order.details) ? order.details : [];

    infoOrderNumber.textContent = order.order_number || "—";
    infoCustomer.textContent = order.customer || "—";
    setStatusBadgeToNode(infoStatus, order.status);
    infoSignedAt.textContent = order.signed_at || "—";
    infoInstallAt.textContent = order.planned_install_at || "—";

    const assemblyPlan = calcPlanSummary(details, "planned_assembly_due_at_input", "requires_assembly");
    const installPlan = calcPlanSummary(details, "planned_install_due_at_input", "requires_install");
    const assemblyFact = calcFactSummary(details, "assembly_completed_at", "requires_assembly");
    const installFact = calcFactSummary(details, "install_completed_at", "requires_install");

    applySummaryField(infoPlanAssembly, assemblyPlan);
    applySummaryField(infoPlanInstall, installPlan);
    applySummaryField(infoFactAssembly, assemblyFact);
    applySummaryField(infoFactInstall, installFact);

    renderInfoDetails(details);
    infoModal.classList.remove("hidden");
};

const closeInfoModal = () => infoModal.classList.add("hidden");

const statusClassFromText = (value) => {
    const text = String(value ?? "").trim().toLowerCase();
    if (!text || text === "—") return "is-default";

    const percentMatch = text.match(/^(\d+(?:[.,]\d+)?)%$/);
    if (percentMatch) {
        const percent = Number(percentMatch[1].replace(",", "."));
        if (Number.isFinite(percent)) {
            if (percent <= 0) return "is-plan-none";
            if (percent < 50) return "is-plan-low";
            if (percent < 100) return "is-plan-mid";
            return "is-completed";
        }
    }

    if (text.includes("закрит")) {
        return "is-closed";
    }
    if (text.includes("розпод")) {
        return "is-distributed";
    }
    if (text.includes("прост")) {
        return "is-idle";
    }
    if (text.includes("не передано")) {
        return "is-not-sent";
    }
    if (text === "немає" || text === "нема") {
        return "is-missing";
    }

    if (text.includes("заверш") || text.includes("викон") || text.includes("готов") || text.includes("закрит") || text.includes("completed") || text.includes("done")) {
        return "is-completed";
    }
    if (text.includes("заплан") || text.includes("монтаж") || text.includes("збірк")) {
        return "is-in-progress";
    }
    if (text.includes("черг") || text.includes("очіку") || text.includes("pending") || text.includes("new")) {
        return "is-queued";
    }
    if (text.includes("пауз") || text.includes("hold") || text.includes("стоп")) {
        return "is-paused";
    }
    if (text.includes("робот") || text.includes("процес") || text.includes("progress") || text.includes("active")) {
        return "is-in-progress";
    }

    return "is-default";
};

const makeStatusBadge = (value) => {
    const span = document.createElement("span");
    const text = displayValue(value);
    span.textContent = text;
    span.className = `assemblers-status-badge ${statusClassFromText(text)}`;
    return span;
};

const setStatusBadgeToNode = (node, value) => {
    if (!node) return;
    node.textContent = "";
    node.appendChild(makeStatusBadge(value));
};

const SUBCONTRACT_FIELDS = [
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

const renderSubcontractsTable = (order) => {
    if (!subcontractsBody) return;

    subcontractsBody.innerHTML = "";

    if (!order) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 3;
        cell.textContent = "Дані по підрядах відсутні.";
        row.appendChild(cell);
        subcontractsBody.appendChild(row);
        return;
    }

    SUBCONTRACT_FIELDS.forEach((item) => {
        const row = document.createElement("tr");

        const nameCell = document.createElement("td");
        nameCell.textContent = item.label;
        row.appendChild(nameCell);

        const presenceCell = document.createElement("td");
        presenceCell.appendChild(makePresenceBadge(order[item.presenceKey]));
        row.appendChild(presenceCell);

        const statusCell = document.createElement("td");
        if (item.statusKey) {
            statusCell.classList.add("assemblers-status-cell");
            statusCell.appendChild(makeStatusBadge(order[item.statusKey]));
        } else {
            statusCell.textContent = "—";
        }
        row.appendChild(statusCell);

        subcontractsBody.appendChild(row);
    });
};

const openSubcontractsModal = (orderNumber) => {
    if (!subcontractsModal) return;

    const order = state.rowsByOrder.get(orderNumber);
    if (!order) {
        showToast("Не вдалося знайти дані замовлення для підрядів.", "error");
        return;
    }

    if (subcontractsOrderNumber) subcontractsOrderNumber.textContent = displayValue(order.order_number);
    if (subcontractsCustomer) subcontractsCustomer.textContent = displayValue(order.customer);
    if (subcontractsStatus) setStatusBadgeToNode(subcontractsStatus, order.status);

    renderSubcontractsTable(order);
    subcontractsModal.classList.remove("hidden");
};

const closeSubcontractsModal = () => {
    if (!subcontractsModal) return;
    subcontractsModal.classList.add("hidden");
    if (subcontractsOrderNumber) subcontractsOrderNumber.textContent = "—";
    if (subcontractsCustomer) subcontractsCustomer.textContent = "—";
    if (subcontractsStatus) setStatusBadgeToNode(subcontractsStatus, null);
    renderSubcontractsTable(null);
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
            <div class="action-toast-text"></div>
            <button type="button" class="btn-close action-toast-close" aria-label="Закрити повідомлення">×</button>
        `;

        toast.querySelector(".action-toast-text").textContent = message;
        toast.querySelector(".action-toast-close")?.addEventListener("click", () => toast.remove());
        document.body.appendChild(toast);
        window.setTimeout(() => toast.remove(), 4200);
    };

    const resetRenderedRows = () => {
        tbody.innerHTML = "";
        state.rowsByOrder.clear();
        state.rowElements.clear();
    };

    const STATUS_LABELS = {
        "розподіл": "Розподіл",
        "простой": "Простой",
        "збірка": "Збірка",
        "монтаж": "Монтаж",
        "запланована збірка": "Запланована збірка",
        "заплановано монтаж": "Заплановано монтаж",
        "пауза": "Пауза",
        "завершено": "Завершено",
    };

    const DEADLINE_LABELS = {
        overdue: "Прострочені",
        critical: "Критичні (0-9)",
        upcoming: "Найближчі (10-30)",
        far: "Далекі (>30)",
        no_deadline: "Без дедлайну",
    };

    const fillSelectWithOptions = (select, options, placeholder) => {
        if (!select) return;
        const currentValue = select.value;
        select.innerHTML = "";

        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = placeholder;
        select.appendChild(defaultOption);

        options.forEach((value) => {
            const normalized = String(value || "").trim();
            if (!normalized) return;
            const option = document.createElement("option");
            option.value = normalized;
            option.textContent = normalized;
            select.appendChild(option);
        });

        if (currentValue) {
            select.value = currentValue;
        }
    };

    const loadFilterOptions = async () => {
        const params = new URLSearchParams();
        if (state.filters.orderNumber) params.set("order_number", state.filters.orderNumber);
        if (state.filters.customer) params.set("customer", state.filters.customer);

        const query = params.toString();
        const url = query
            ? `/assemblers/api/main/filter-options?${query}`
            : "/assemblers/api/main/filter-options";

        const response = await fetch(url);
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
            throw new Error(payload.error || "Не вдалося завантажити фільтри.");
        }

        state.filterOptions.statuses = Array.isArray(payload.statuses) ? payload.statuses : [];
        state.filterOptions.orderTypes = Array.isArray(payload.order_types) ? payload.order_types : [];

        fillSelectWithOptions(filtersStatus, state.filterOptions.statuses, "Усі статуси");
        fillSelectWithOptions(filtersOrderType, state.filterOptions.orderTypes, "Усі типи");
    };

    const syncActiveFilters = () => {
        if (!activeFiltersEl) return;

        activeFiltersEl.innerHTML = "";
        const chips = [];

        if (state.filters.status) {
            const statusKey = state.filters.status.toLowerCase();
            chips.push({
                label: `Статус: ${STATUS_LABELS[statusKey] || state.filters.status}`,
                clear: () => {
                    state.filters.status = "";
                    if (filtersStatus) filtersStatus.value = "";
                    void resetAndReload();
                },
            });
        }

        if (state.filters.orderType) {
            chips.push({
                label: `Тип: ${state.filters.orderType}`,
                clear: () => {
                    state.filters.orderType = "";
                    if (filtersOrderType) filtersOrderType.value = "";
                    void resetAndReload();
                },
            });
        }

        if (state.filters.deadlineBucket) {
            chips.push({
                label: `Дедлайн: ${DEADLINE_LABELS[state.filters.deadlineBucket] || state.filters.deadlineBucket}`,
                clear: () => {
                    state.filters.deadlineBucket = "";
                    if (filtersDeadline) filtersDeadline.value = "";
                    void resetAndReload();
                },
            });
        }

        chips.forEach(({ label, clear }) => {
            const chip = document.createElement("span");
            chip.className = "buffer-filter-chip";
            chip.textContent = label;

            const removeBtn = document.createElement("button");
            removeBtn.type = "button";
            removeBtn.setAttribute("aria-label", `Скинути фільтр ${label}`);
            removeBtn.textContent = "×";
            removeBtn.addEventListener("click", clear);
            chip.appendChild(removeBtn);

            activeFiltersEl.appendChild(chip);
        });

        openFiltersButton?.classList.toggle("is-active-filter", chips.length > 0);
    };

    const buildMainQueryString = (offset, limit) => {
        const params = new URLSearchParams({
            offset: String(offset),
            limit: String(limit),
        });

        if (state.filters.orderNumber) {
            params.set("order_number", state.filters.orderNumber);
        }
        if (state.filters.customer) {
            params.set("customer", state.filters.customer);
        }
        if (state.filters.status) {
            params.set("status", state.filters.status);
        }
        if (state.filters.orderType) {
            params.set("order_type", state.filters.orderType);
        }
        if (state.filters.deadlineBucket) {
            params.set("deadline_bucket", state.filters.deadlineBucket);
        }

        return params.toString();
    };

    const resetAndReload = async () => {
        state.offset = 0;
        state.total = 0;
        state.hasMore = true;
        resetRenderedRows();
        await loadNextPage();
        tableManager?.applyPinnedColumns?.();
        syncActiveFilters();
    };

    const closeFiltersModal = () => {
        filtersModal?.classList.add("hidden");
    };

    const openFiltersModal = async () => {
        try {
            await loadFilterOptions();
        } catch (error) {
            showToast(error.message || "Не вдалося завантажити опції фільтра.", "error");
        }

        if (filtersStatus) filtersStatus.value = state.filters.status;
        if (filtersOrderType) filtersOrderType.value = state.filters.orderType;
        if (filtersDeadline) filtersDeadline.value = state.filters.deadlineBucket;
        filtersModal?.classList.remove("hidden");
    };

    const applyFilters = async () => {
        state.filters.status = filtersStatus?.value || "";
        state.filters.orderType = filtersOrderType?.value || "";
        state.filters.deadlineBucket = filtersDeadline?.value || "";
        closeFiltersModal();
        await resetAndReload();
    };

    const resetFilters = async () => {
        state.filters.status = "";
        state.filters.orderType = "";
        state.filters.deadlineBucket = "";
        if (filtersStatus) filtersStatus.value = "";
        if (filtersOrderType) filtersOrderType.value = "";
        if (filtersDeadline) filtersDeadline.value = "";
        closeFiltersModal();
        await resetAndReload();
    };

    const refreshLoadedRows = async () => {
        const loadedCount = Math.max(tbody.children.length || 0, state.offset || 0, state.limit);
        const previousScrollTop = tableWrap.scrollTop;
        const payload = await withGlobalLoader(async () => {
            const response = await fetch(`/assemblers/api/main?${buildMainQueryString(0, loadedCount)}`);
            const result = await response.json();
            if (!response.ok || !result.ok) {
                throw new Error(result.error || "Не вдалося оновити таблицю.");
            }
            return result;
        }, "Оновлення головної таблиці...");

        resetRenderedRows();
        payload.rows.forEach((row) => tbody.appendChild(renderRow(row)));
        state.offset = payload.rows.length;
        state.total = payload.total || 0;
        state.hasMore = Boolean(payload.has_more);
        updateMeta();
        tableWrap.scrollTop = previousScrollTop;
        tableManager?.applyPinnedColumns?.();
    };

    const renderDetails = (details) => {
        modalDetailsBody.innerHTML = "";
        state.detailActionState.clear();
        state.activeDetailId = null;

        if (!details?.length) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.colSpan = 9;
            cell.textContent = "По замовленню ще немає деталізації.";
            row.appendChild(cell);
            modalDetailsBody.appendChild(row);
            return;
        }

        details.forEach((detail) => {
            const row = document.createElement("tr");
            const detailId = getDetailIdNumber(detail.detail_id);
            row.dataset.detailId = String(detailId ?? "");
            row.dataset.assemblyStatus = resolveStageStatus(detail, "assembly", DETAIL_ACTION_DEFAULTS);
            row.dataset.installStatus = resolveStageStatus(detail, "install", DETAIL_ACTION_DEFAULTS);
            row.dataset.assemblyCompletedAt = String(detail.assembly_completed_at || "");
            row.dataset.installCompletedAt = String(detail.install_completed_at || "");
            row.dataset.requiresAssembly = String(detail.requires_assembly !== false);
            row.dataset.requiresInstall = String(detail.requires_install !== false);

            if (detailId != null) {
                state.detailActionState.set(detailId, cloneDetailActionDefaults());
            }

            const buildStageControl = ({ detailField, inputValue, label }) => {
                const cell = document.createElement("td");
                const wrap = document.createElement("div");
                wrap.className = "main-order-detail-stage-control";

                const input = document.createElement("input");
                input.type = "date";
                input.value = inputValue;
                input.dataset.detailField = detailField;
                input.dataset.detailId = String(detail.detail_id || "");
                input.setAttribute("aria-label", `${label} ${detail.part_number || ""}`.trim());

                updateDateInputState(input);
                input.addEventListener("input", () => updateDateInputState(input));
                input.addEventListener("change", () => updateDateInputState(input));
                wrap.appendChild(input);

                cell.appendChild(wrap);
                return cell;
            };

            [detail.part_number, detail.product_name, detail.item_value].forEach((value, index) => {
                const cell = document.createElement("td");
                cell.textContent = displayValue(value);
                row.appendChild(cell);
            });

            // Відсоток — числове поле
            const percentCell = document.createElement("td");
            const percentInput = document.createElement("input");
            percentInput.type = "number";
            percentInput.min = "0";
            percentInput.max = "100";
            percentInput.step = "0.01";
            percentInput.value = String(detail.item_percent ?? 0);
            percentInput.dataset.detailField = "item_percent";
            percentInput.dataset.detailId = String(detail.detail_id || "");
            percentInput.setAttribute("aria-label", `Відсоток ${detail.part_number || ""}`.trim());
            percentInput.style.width = "70px";
            percentCell.appendChild(percentInput);
            row.appendChild(percentCell);

            const requiresAssemblyCell = document.createElement("td");
            requiresAssemblyCell.className = "main-order-detail-require-cell";
            const requiresAssemblyInput = document.createElement("input");
            requiresAssemblyInput.type = "checkbox";
            requiresAssemblyInput.className = "main-order-detail-require-toggle";
            requiresAssemblyInput.checked = detail.requires_assembly !== false;
            requiresAssemblyInput.dataset.detailField = "requires_assembly";
            requiresAssemblyInput.dataset.detailId = String(detail.detail_id || "");
            requiresAssemblyCell.appendChild(requiresAssemblyInput);
            row.appendChild(requiresAssemblyCell);

            const requiresInstallCell = document.createElement("td");
            requiresInstallCell.className = "main-order-detail-require-cell";
            const requiresInstallInput = document.createElement("input");
            requiresInstallInput.type = "checkbox";
            requiresInstallInput.className = "main-order-detail-require-toggle";
            requiresInstallInput.checked = detail.requires_install !== false;
            requiresInstallInput.dataset.detailField = "requires_install";
            requiresInstallInput.dataset.detailId = String(detail.detail_id || "");
            requiresInstallCell.appendChild(requiresInstallInput);
            row.appendChild(requiresInstallCell);

            row.appendChild(buildStageControl({
                detailField: "planned_assembly_due_at",
                inputValue: detail.planned_assembly_due_at_input || "",
                label: "Дата планування збірка",
            }));

            row.appendChild(buildStageControl({
                detailField: "planned_install_due_at",
                inputValue: detail.planned_install_due_at_input || "",
                label: "Дата планування монтаж",
            }));

            const applyRequirementState = () => {
                const assemblyRequired = requiresAssemblyInput.checked;
                const installRequired = requiresInstallInput.checked;

                row.dataset.requiresAssembly = String(assemblyRequired);
                row.dataset.requiresInstall = String(installRequired);

                const actionState = getDetailActionState(detailId);
                if (!assemblyRequired) {
                    actionState.complete_assembly_now = false;
                    actionState.reset_assembly_completed = false;
                }
                if (!installRequired) {
                    actionState.complete_install_now = false;
                    actionState.reset_install_completed = false;
                }

                const assemblyDateInput = row.querySelector("input[data-detail-field='planned_assembly_due_at']");
                const installDateInput = row.querySelector("input[data-detail-field='planned_install_due_at']");
                if (assemblyDateInput) {
                    assemblyDateInput.disabled = !assemblyRequired || !canManageOrders;
                    const assemblyWrap = assemblyDateInput.closest(".main-order-detail-stage-control");
                    if (!assemblyRequired) {
                        assemblyDateInput.value = "";
                        updateDateInputState(assemblyDateInput);
                        if (assemblyWrap) assemblyWrap.style.visibility = "hidden";
                    } else {
                        if (assemblyWrap) assemblyWrap.style.visibility = "";
                    }
                }
                if (installDateInput) {
                    installDateInput.disabled = !installRequired || !canManageOrders;
                    const installWrap = installDateInput.closest(".main-order-detail-stage-control");
                    if (!installRequired) {
                        installDateInput.value = "";
                        updateDateInputState(installDateInput);
                        if (installWrap) installWrap.style.visibility = "hidden";
                    } else {
                        if (installWrap) installWrap.style.visibility = "";
                    }
                }
            };

            requiresAssemblyInput.addEventListener("change", applyRequirementState);
            requiresInstallInput.addEventListener("change", applyRequirementState);
            applyRequirementState();

            const actionsCell = document.createElement("td");
            actionsCell.className = "main-order-detail-actions-cell";

            const actionButton = document.createElement("button");
            actionButton.type = "button";
            actionButton.className = "main-order-detail-edit-button";
            actionButton.textContent = "Редагувати";
            actionButton.disabled = !canManageOrders;
            actionButton.addEventListener("click", () => openDetailStageModal(detail));
            actionsCell.appendChild(actionButton);

            [
                "complete_assembly_now",
                "reset_assembly_completed",
                "complete_install_now",
                "reset_install_completed",
            ].forEach((fieldName) => {
                const hiddenInput = document.createElement("input");
                hiddenInput.type = "hidden";
                hiddenInput.value = "0";
                hiddenInput.dataset.detailActionField = fieldName;
                hiddenInput.dataset.detailField = fieldName;
                hiddenInput.dataset.detailId = String(detailId ?? "");
                actionsCell.appendChild(hiddenInput);
            });

            row.appendChild(actionsCell);
            syncDetailActionInputs(row, detailId);

            modalDetailsBody.appendChild(row);
        });
    };

    const applyOrderCard = (order) => {
        if (!order) {
            return;
        }

        state.activeOrderNumber = order.order_number || "";
        modalTitle.textContent = order.order_number ? `Замовлення ${order.order_number}` : "Замовлення";
        modalOrderNumber.textContent = displayValue(order.order_number);
        modalCustomer.textContent = displayValue(order.customer);
        setStatusBadgeToNode(modalStatus, order.status);
        modalDeadline.textContent = displayValue(order.deadline);
        modalOrderType.textContent = displayValue(order.order_type);
        modalAddress.value = order.address || "";
        modalAddressNote.value = order.address_note || "";
        modalNote.value = order.note || "";
        applyNoteAppearanceToField(order.note_color || "", order.note_text_color || NOTE_TEXT_PICKER_FALLBACK);
        modalVat.checked = Boolean(order.vat);
        renderDetails(order.details || []);
        modalSubmit.hidden = !canManageOrders;
    };

    const closeModal = () => {
        state.activeOrderNumber = "";
        closeDetailStageModal();
        state.detailActionState.clear();
        modal.classList.add("hidden");
        modalForm.reset();
        modalVat.checked = false;
        modalTitle.textContent = "Замовлення";
        modalOrderNumber.textContent = "—";
        modalCustomer.textContent = "—";
        setStatusBadgeToNode(modalStatus, null);
        modalDeadline.textContent = "—";
        modalOrderType.textContent = "—";
        closeNotePopovers();
        applyNoteAppearanceToField("", NOTE_TEXT_PICKER_FALLBACK);
        renderDetails([]);
        setModalBusy(false);
        setModalSaving(false);
    };

    const openModal = async (orderNumber) => {
        if (!orderNumber || state.modalLoading || state.modalSaving) {
            return;
        }

        setModalBusy(true);

        try {
            const payload = await withGlobalLoader(async () => {
                const response = await fetch(`/assemblers/api/main/${encodeURIComponent(orderNumber)}`);
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Не вдалося завантажити замовлення.");
                }
                return result;
            }, "Завантаження замовлення...");

            applyOrderCard(payload.order);
            modal.classList.remove("hidden");
        } catch (error) {
            showToast(error.message || "Не вдалося завантажити замовлення.", "error");
            closeModal();
        } finally {
            setModalBusy(false);
        }
    };

    const makePlanPercentBadge = (value) => {
        const text = String(value ?? "0%").trim();
        const num = parseInt(text) || 0;
        const span = document.createElement("span");
        span.textContent = text;
        span.className = "assemblers-status-badge " + (
            num === 0 ? "is-plan-none" :
            num < 50  ? "is-plan-low" :
            num < 100 ? "is-plan-mid" :
            "is-completed"
        );
        return span;
    };

    const parseStatusDistribution = (value) => {
        const text = String(value ?? "").toLowerCase();
        const parts = text.split("|").map((p) => p.trim());

        let queued = 0;
        let inProgress = 0;
        let completed = 0;

        parts.forEach((part) => {
            const m = part.match(/(\d+)\s*%/);
            if (!m) return;
            const percent = Number(m[1]) || 0;

            if (part.includes("у черзі")) queued = percent;
            else if (part.includes("в роботі")) inProgress = percent;
            else if (part.includes("завершено")) completed = percent;
        });

        return { queued, inProgress, completed };
    };

    const statusClassFromDistribution = (value) => {
        const p = parseStatusDistribution(value);

        if (p.completed > 80) return "is-completed";   // зелений
        if (p.queued > 40) return "is-plan-none";      // червоний
        if (p.inProgress >= 50) return "is-plan-low";  // жовтий
        return "is-default";
    };

    const makeDistributionBadge = (value) => {
        const span = document.createElement("span");
        span.textContent = String(value ?? "—").trim() || "—";
        span.className = `assemblers-status-badge ${statusClassFromDistribution(value)}`;
        return span;
    };

    const SUBCONTRACT_PRESENCE_INDEXES = new Set([
        24, // paint_shop
        26, // metal
        28, // veneer
        29, // plastic_hpl
        30, // joinery_shop
        31, // soft_shop
        32, // artificial_stone
        33, // compact_plate
        34, // dsp_countertop
        35, // sliding_systems
        36, // glass_mirror
        38, // frame_facades
        39, // ceramic_granite
    ]);

    const STATUS_TEXT_INDEXES = new Set([
        3,  // status
        25, // paint_status
        27, // metal_status
        37, // glass_status
        40, // constructor_status
        41, // production_status
    ]);

    const HOURS_COLUMNS_INDEXES = new Set([
        8,  // planned_hours
        9,  // actual_hours
        10, // remaining_hours
        16, // assembly_hours
        21, // install_hours
    ]);

    const isSubcontractColumn = (index) => SUBCONTRACT_PRESENCE_INDEXES.has(index);

    const hasDbValue = (value) => {
        if (value == null) return false;
        const text = String(value).trim();
        return text !== "" && text !== "-" && text !== "—";
    };

    const makePresenceBadge = (value) => {
        const span = document.createElement("span");
        const present = hasDbValue(value);
        span.className = `assemblers-status-badge ${present ? "is-completed" : "is-default"}`;
        span.textContent = present ? "✓" : "немає";
        return span;
    };


    const renderRow = (row) => {
        const tr = document.createElement("tr");
        tr.dataset.orderNumber = row.order_number || "";
        tr.classList.add("main-order-row", "is-clickable");
        const values = [
            row.order_number, row.customer, row.order_type, row.status, row.note, row.products,
            row.contract_due_at, row.deadline, row.planned_hours, row.actual_hours, row.remaining_hours,
            row.planned_assembly_parts, row.planned_install_parts, row.assembly_status, row.assembly_started_at,
            row.assembly_completed_at, row.assembly_hours, row.assembly_workers_count, row.install_status, row.install_started_at, 
            row.install_completed_at, row.install_hours, row.assembly_workers, row.install_workers, 
            row.paint_shop, row.paint_status, row.metal,
            row.metal_status, row.veneer, row.plastic_hpl, row.joinery_shop, row.soft_shop, row.artificial_stone,
            row.compact_plate, row.dsp_countertop, row.sliding_systems, row.glass_mirror, row.glass_status,
            row.frame_facades, row.ceramic_granite, row.constructor_status, row.production_status, row.order_value,
            row.vat, row.parts_count, row.launches_count,
            row.recorded_at, row.address, row.address_note, row.assembler_stop_note,
            row.materials, row.constructor_name, row.assembler_pause_at, row.manager_name,
        ];

        values.forEach((value, index) => {
            const td = document.createElement("td");
            td.dataset.colIndex = String(index);

            if (isSubcontractColumn(index)) {
                td.classList.add("is-subcontract");
            }

            if (index === 11 || index === 12) {
                td.appendChild(makePlanPercentBadge(value));
            } else if (index === 13 || index === 18) {
                td.appendChild(makeDistributionBadge(value));
            } else if (index === 43) {
                // ПДВ column — show Так/— badge
                const span = document.createElement("span");
                const hasVat = Boolean(value);
                span.className = `assemblers-status-badge ${hasVat ? "is-completed" : "is-default"}`;
                span.textContent = hasVat ? "Так" : "—";
                td.appendChild(span);
            } else if (STATUS_TEXT_INDEXES.has(index)) {
                td.classList.add("assemblers-status-cell");
                td.appendChild(makeStatusBadge(value));
            } else if (SUBCONTRACT_PRESENCE_INDEXES.has(index)) {
                td.appendChild(makePresenceBadge(value));
            } else if (HOURS_COLUMNS_INDEXES.has(index)) {
                td.textContent = formatHoursMinutes(value);
            } else if (index === 7) {
                td.textContent = displayValue(value);
                const deadlineDays = parseNumeric(value);
                if (deadlineDays != null && deadlineDays < 10) {
                    td.classList.add("is-deadline-critical");
                }
            } else {
                td.textContent = value ?? "—";
            }

            if (index === cellIndexes.note) {
                td.classList.add("main-order-note-cell");
                applyNoteAppearanceToCell(td, row.note_color, row.note_text_color);
            }

            tr.appendChild(td);
        });

        if (row.order_number) {
            state.rowsByOrder.set(row.order_number, { ...row });
            state.rowElements.set(row.order_number, tr);
        }

        tableManager?.applyRow(tr);
        return tr;
    };

    const updateMeta = () => {
        meta.textContent = "";
    };

    const loadNextPage = async () => {
        if (state.loading || !state.hasMore) {
            return;
        }

        state.loading = true;
        updateMeta();

        try {
            const payload = await withGlobalLoader(async () => {
                const response = await fetch(`/assemblers/api/main?${buildMainQueryString(state.offset, state.limit)}`);
                const result = await response.json();
                if (!response.ok || !result.ok) {
                    throw new Error(result.error || "Не вдалося завантажити головну таблицю");
                }
                return result;
            }, "Завантаження головної таблиці...");

            payload.rows.forEach((row) => tbody.appendChild(renderRow(row)));
            tableManager?.applyPinnedColumns?.();
            state.offset += payload.rows.length;
            state.total = payload.total || 0;
            state.hasMore = Boolean(payload.has_more);
            updateMeta();
        } catch (error) {
            meta.textContent = "";
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

    const scheduleSearch = () => {
        if (searchTimer) {
            window.clearTimeout(searchTimer);
        }
        searchTimer = window.setTimeout(async () => {
            state.filters.orderNumber = orderSearch.value.trim();
            state.filters.customer = customerSearch.value.trim();
            try {
                await loadFilterOptions();
            } catch (error) {
                console.warn("Не вдалося оновити опції фільтрів", error);
            }
            await resetAndReload();
        }, 280);
    };

    tbody.addEventListener("click", (event) => {
        const row = event.target.closest("tr[data-order-number]");
        if (!row || !tbody.contains(row)) {
            return;
        }

        void openModal(row.dataset.orderNumber || "");
    });

    tbody.addEventListener("contextmenu", (event) => {
        const row = event.target.closest("tr[data-order-number]");
        if (!row || !tbody.contains(row) || !rowMenu) return;

        event.preventDefault();
        state.contextOrderNumber = row.dataset.orderNumber || "";
        rowMenu.style.left = event.pageX + "px";
        rowMenu.style.top = event.pageY + "px";
        rowMenu.classList.remove("hidden");
    });

    closeButtons.forEach((button) => {
        button.addEventListener("click", closeModal);
    });

    orderSearch.addEventListener("input", scheduleSearch);
    customerSearch.addEventListener("input", scheduleSearch);
    openFiltersButton?.addEventListener("click", () => {
        void openFiltersModal();
    });
    filtersApplyButton?.addEventListener("click", () => {
        void applyFilters();
    });
    filtersResetButton?.addEventListener("click", () => {
        void resetFilters();
    });
    filtersCloseButtons.forEach((btn) => btn.addEventListener("click", closeFiltersModal));
    filtersModal?.addEventListener("click", (event) => {
        if (event.target === filtersModal) {
            closeFiltersModal();
        }
    });

    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            closeModal();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
            return;
        }

        if (state.notePopover) {
            closeNotePopovers();
            return;
        }

        if (subcontractsModal && !subcontractsModal.classList.contains("hidden")) {
            closeSubcontractsModal();
            return;
        }

        if (!infoModal.classList.contains("hidden")) {
            closeInfoModal();
            return;
        }

        if (filtersModal && !filtersModal.classList.contains("hidden")) {
            closeFiltersModal();
            return;
        }

        if (!modal.classList.contains("hidden")) {
            closeModal();
        }
    });

    rowMenu?.addEventListener("click", async (event) => {
        const btn = event.target.closest("button[data-main-row-action]");
        if (!btn) return;

        const action = btn.dataset.mainRowAction;
        const orderNumber = state.contextOrderNumber;
        rowMenu.classList.add("hidden");

        if (!orderNumber) return;

        if (action === "details") {
            await openInfoModal(orderNumber);
            return;
        }

        if (action === "subcontracts") {
            openSubcontractsModal(orderNumber);
        }
    });

    document.addEventListener("click", () => rowMenu?.classList.add("hidden"));
    document.addEventListener("scroll", () => rowMenu?.classList.add("hidden"), true);
    noteToolButtons.forEach((button) => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            openNotePopover(button.dataset.mainNoteTool || "");
        });
    });
    notePopovers.forEach((popover) => {
        popover.addEventListener("click", (event) => event.stopPropagation());
    });
    noteField.addEventListener("click", (event) => {
        if (!event.target.closest("[data-main-note-tool]") && !event.target.closest("[data-main-note-popover]")) {
            closeNotePopovers();
        }
    });
    document.addEventListener("click", (event) => {
        if (!event.target.closest("[data-main-note-field]")) {
            closeNotePopovers();
        }
    });
    noteFillButtons.forEach((button) => {
        const color = button.dataset.mainNoteFillColor || "";
        button.style.setProperty("--swatch-color", normalizeHexColor(color) || NOTE_FILL_PICKER_FALLBACK);
        button.addEventListener("click", () => applyNoteAppearanceToField(color, state.noteTextColor));
    });
    noteTextButtons.forEach((button) => {
        const color = button.dataset.mainNoteTextColor || "";
        button.style.setProperty("--swatch-color", normalizeHexColor(color) || NOTE_TEXT_PICKER_FALLBACK);
        button.addEventListener("click", () => applyNoteAppearanceToField(state.noteColor, color));
    });
    noteFillPicker.addEventListener("input", () => applyNoteAppearanceToField(noteFillPicker.value, state.noteTextColor));
    noteFillClear.addEventListener("click", () => applyNoteAppearanceToField("", state.noteTextColor));
    noteTextPicker.addEventListener("input", () => applyNoteAppearanceToField(state.noteColor, noteTextPicker.value));
    noteTextClear.addEventListener("click", () => applyNoteAppearanceToField(state.noteColor, NOTE_TEXT_PICKER_FALLBACK));
    noteFillRecent.addEventListener("click", (event) => {
        const button = event.target.closest("[data-main-note-fill-recent-color]");
        if (!button) {
            return;
        }
        applyNoteAppearanceToField(button.dataset.mainNoteFillRecentColor || "", state.noteTextColor);
    });
    noteEmojiButtons.forEach((button) => {
        button.addEventListener("click", () => insertEmojiIntoNote(button.dataset.mainNoteEmoji || ""));
    });
    detailStageAssemblyCompleteButton?.addEventListener("click", async () => {
        const activeDetailId = state.activeDetailId;
        await applyDetailStageAction("assembly", "complete");
        if (state.activeDetailId == null) {
            return;
        }
        try {
            const payload = await persistMainOrderChanges({ loadingMessage: "Оновлення статусу збірки...", closeAfterSave: false });
            if (activeDetailId != null) {
                const updatedDetail = (payload.order?.details || [])
                    .find((item) => Number(item?.detail_id) === Number(activeDetailId));
                if (updatedDetail) {
                    openDetailStageModal(updatedDetail);
                }
            }
            showToast("Статус збірки оновлено.");
        } catch (error) {
            showToast(error.message || "Не вдалося оновити статус збірки.", "error");
        }
    });
    detailStageAssemblyResetButton?.addEventListener("click", async () => {
        const activeDetailId = state.activeDetailId;
        await applyDetailStageAction("assembly", "reset");
        if (state.activeDetailId == null) {
            return;
        }
        try {
            const payload = await persistMainOrderChanges({ loadingMessage: "Скасування завершення збірки...", closeAfterSave: false });
            if (activeDetailId != null) {
                const updatedDetail = (payload.order?.details || [])
                    .find((item) => Number(item?.detail_id) === Number(activeDetailId));
                if (updatedDetail) {
                    openDetailStageModal(updatedDetail);
                }
            }
            showToast("Завершення збірки скасовано.");
        } catch (error) {
            showToast(error.message || "Не вдалося скасувати завершення збірки.", "error");
        }
    });
    detailStageInstallCompleteButton?.addEventListener("click", async () => {
        const activeDetailId = state.activeDetailId;
        await applyDetailStageAction("install", "complete");
        if (state.activeDetailId == null) {
            return;
        }
        try {
            const payload = await persistMainOrderChanges({ loadingMessage: "Оновлення статусу монтажу...", closeAfterSave: false });
            if (activeDetailId != null) {
                const updatedDetail = (payload.order?.details || [])
                    .find((item) => Number(item?.detail_id) === Number(activeDetailId));
                if (updatedDetail) {
                    openDetailStageModal(updatedDetail);
                }
            }
            showToast("Статус монтажу оновлено.");
        } catch (error) {
            showToast(error.message || "Не вдалося оновити статус монтажу.", "error");
        }
    });
    detailStageInstallResetButton?.addEventListener("click", async () => {
        const activeDetailId = state.activeDetailId;
        await applyDetailStageAction("install", "reset");
        if (state.activeDetailId == null) {
            return;
        }
        try {
            const payload = await persistMainOrderChanges({ loadingMessage: "Скасування завершення монтажу...", closeAfterSave: false });
            if (activeDetailId != null) {
                const updatedDetail = (payload.order?.details || [])
                    .find((item) => Number(item?.detail_id) === Number(activeDetailId));
                if (updatedDetail) {
                    openDetailStageModal(updatedDetail);
                }
            }
            showToast("Завершення монтажу скасовано.");
        } catch (error) {
            showToast(error.message || "Не вдалося скасувати завершення монтажу.", "error");
        }
    });
    detailStageModalCloseButtons.forEach((button) => button.addEventListener("click", closeDetailStageModal));
    detailStageModal?.addEventListener("click", (event) => {
        if (event.target === detailStageModal) {
            closeDetailStageModal();
        }
    });
    infoModalClose.forEach((btn) => btn.addEventListener("click", closeInfoModal));
    infoModal?.addEventListener("click", (event) => { if (event.target === infoModal) closeInfoModal(); });
    subcontractsCloseButtons.forEach((btn) => btn.addEventListener("click", closeSubcontractsModal));
    subcontractsModal?.addEventListener("click", (event) => {
        if (event.target === subcontractsModal) {
            closeSubcontractsModal();
        }
    });
        
    modalForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!canManageOrders || !state.activeOrderNumber || state.modalLoading || state.modalSaving) {
            showToast("Недостатньо прав для керування замовленням.", "error");
            return;
        }

        setModalSaving(true);

        try {
            const payload = await persistMainOrderChanges({
                loadingMessage: "Збереження змін по замовленню...",
                closeAfterSave: true,
            });
            showToast(payload.message || "Керування замовленням збережено.");
        } catch (error) {
            showToast(error.message || "Не вдалося зберегти зміни.", "error");
        } finally {
            setModalSaving(false);
        }
    });

    void loadFilterOptions().catch((error) => {
        console.warn("Не вдалося завантажити фільтри головної таблиці", error);
    });
    renderRecentFillColors();
    applyNoteAppearanceToField("", NOTE_TEXT_PICKER_FALLBACK);
    syncActiveFilters();
    void loadNextPage();
});