document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector("[data-assemblers-page='staff']");
    const table = page?.querySelector("table");
    const loader = page?.querySelector("[data-staff-loader]");
    const tableWrap = page?.querySelector("[data-assemblers-table-wrap]");
    const metaRow = page?.querySelector("[data-staff-meta-row]");
    const metaText = metaRow?.querySelector(".table-meta");
    const tableBody = page?.querySelector("[data-staff-body]");
    const searchNameInput = page?.querySelector("[data-staff-search-name]");
    const searchBrigadeInput = page?.querySelector("[data-staff-search-brigade]");
    const modal = document.querySelector("[data-staff-modal]");
    const modalForm = document.querySelector("[data-staff-modal-form]");
    const modalUser = document.querySelector("[data-staff-modal-user]");
    const modalSourceUserId = document.querySelector("[data-staff-source-user-id]");
    const modalSubdivision = document.querySelector("[data-staff-subdivision]");
    const modalBrigade = document.querySelector("[data-staff-brigade]");
    const brigadeMembersText = document.querySelector("[data-staff-brigade-members]");
    const modalSubmit = document.querySelector("[data-staff-submit]");
    const closeButtons = document.querySelectorAll("[data-staff-modal-close]");

    if (!page || !table) {
        return;
    }

    const loaderStartedAt = Date.now();
    const minLoaderMs = 550;
    const globalLoaderId = window.ERPLoading?.show?.();

    const revealTable = () => {
        const elapsed = Date.now() - loaderStartedAt;
        const delay = Math.max(0, minLoaderMs - elapsed);

        window.setTimeout(() => {
            loader?.classList.add("hidden");
            tableWrap?.classList.remove("hidden");
            metaRow?.classList.remove("hidden");
            if (typeof globalLoaderId === "number") {
                window.ERPLoading?.hide?.(globalLoaderId);
            }
        }, delay);
    };

    // Fallback: even if table tools fail, still reveal the table.
    window.setTimeout(revealTable, 1800);

    window.AssemblersTableTools?.initTable({
        table,
        storageKey: table.dataset.tableKey || "assemblers-staff",
    })
        .then(() => {
            revealTable();
        })
        .catch(e => {
            console.warn("Failed to initialize table manager", e);
            revealTable();
        });

    if (!tableBody || !modal || !modalForm || !modalUser || !modalSourceUserId || !modalSubdivision || !modalBrigade || !brigadeMembersText || !modalSubmit) {
        return;
    }

    const rows = Array.from(tableBody.querySelectorAll("[data-staff-row]"));

    const updateMetaCount = (visibleCount) => {
        if (!metaText) {
            return;
        }
        metaText.textContent = `Знайдено ${visibleCount} користувачів.`;
    };

    const applyFilters = () => {
        const nameQuery = String(searchNameInput?.value || "").trim().toLowerCase();
        const brigadeQuery = String(searchBrigadeInput?.value || "").trim().toLowerCase();
        let visibleCount = 0;

        rows.forEach((row) => {
            const name = String(row.dataset.name || "").trim().toLowerCase();
            const username = String(row.dataset.username || "").trim().toLowerCase();
            const brigade = String(row.dataset.brigadeNumber || "").trim().toLowerCase();

            const matchesName = !nameQuery || name.includes(nameQuery) || username.includes(nameQuery);
            const matchesBrigade = !brigadeQuery || brigade.includes(brigadeQuery);
            const isVisible = matchesName && matchesBrigade;

            row.classList.toggle("hidden", !isVisible);
            if (isVisible) {
                visibleCount += 1;
            }
        });

        updateMetaCount(visibleCount);
    };

    const searchParams = new URLSearchParams(window.location.search);
    if (searchParams.get("saved") === "1") {
        window.ActionToast?.show?.("Налаштування збиральника збережено.", "success");
    }
    if (searchParams.get("error")) {
        window.ActionToast?.show?.(decodeURIComponent(searchParams.get("error") || "Помилка збереження."), "error");
    }

    let isSubmitting = false;
    const setSubmittingState = (value) => {
        isSubmitting = value;
        modalSubmit.disabled = value;
        modalSubmit.textContent = value ? "Збереження..." : "Зберегти";
    };

    const collectBrigadeMembers = (subdivisionValue, brigadeValue, excludeSourceUserId) => {
        const normalizedSubdivision = String(subdivisionValue || "").trim().toLowerCase();
        const normalizedBrigade = String(brigadeValue || "").trim();

        if (!normalizedSubdivision || !normalizedBrigade) {
            return [];
        }

        return Array.from(tableBody.querySelectorAll("[data-staff-row]")).filter((row) => {
            const rowSubdivision = String(row.dataset.subdivision || "").trim().toLowerCase();
            const rowBrigade = String(row.dataset.brigadeNumber || "").trim();
            const rowSourceUserId = String(row.dataset.sourceUserId || "").trim();
            if (!rowSubdivision || !rowBrigade) {
                return false;
            }
            if (rowSourceUserId && excludeSourceUserId && rowSourceUserId === excludeSourceUserId) {
                return false;
            }
            return rowSubdivision === normalizedSubdivision && rowBrigade === normalizedBrigade;
        });
    };

    const renderBrigadeMembers = () => {
        const sourceUserId = String(modalSourceUserId.value || "").trim();
        const members = collectBrigadeMembers(modalSubdivision.value, modalBrigade.value, sourceUserId);

        if (!String(modalSubdivision.value || "").trim() || !String(modalBrigade.value || "").trim()) {
            brigadeMembersText.textContent = "Оберіть підрозділ і номер бригади.";
            return;
        }

        if (!members.length) {
            brigadeMembersText.textContent = "Поки що нікого немає.";
            return;
        }

        const names = members.map((row) => {
            const name = row.dataset.name || "—";
            const username = row.dataset.username || "—";
            return `${name} (${username})`;
        });
        brigadeMembersText.textContent = names.join(", ");
    };

    const openModal = (row) => {
        const sourceUserId = row.dataset.sourceUserId || "";
        const subdivision = row.dataset.subdivision || "";
        const brigadeNumber = row.dataset.brigadeNumber || "";
        
        modalSourceUserId.value = sourceUserId;
        modalSubdivision.value = subdivision;
        modalBrigade.value = brigadeNumber;
        
        // Validate and set defaults if empty
        if (!modalSourceUserId.value) {
            console.warn("Warning: source_user_id is empty");
        }
        if (!modalSubdivision.value) {
            modalSubdivision.value = "Приват";
        }
        if (!modalBrigade.value) {
            modalBrigade.value = "1";
        }
        
        modalUser.textContent = `${row.dataset.name || '—'} | ${row.dataset.username || '—'}`;
        setSubmittingState(false);
        renderBrigadeMembers();
        modal.classList.remove("hidden");
    };

    const closeModal = () => {
        if (isSubmitting) {
            return;
        }
        modal.classList.add("hidden");
        modalForm.reset();
        modalSourceUserId.value = "";
        brigadeMembersText.textContent = "Оберіть підрозділ і номер бригади.";
    };

    tableBody.addEventListener("click", (event) => {
        const row = event.target.closest("[data-staff-row]");
        if (!row) {
            return;
        }
        openModal(row);
    });

    closeButtons.forEach((button) => {
        button.addEventListener("click", closeModal);
    });

    modalSubdivision.addEventListener("change", renderBrigadeMembers);
    modalBrigade.addEventListener("input", renderBrigadeMembers);

    modalForm.addEventListener("submit", () => {
        setSubmittingState(true);
        window.ActionToast?.show?.("Зберігаємо зміни...", "success");
        window.ERPLoading?.show?.();
    });

    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            closeModal();
        }
    });

    searchNameInput?.addEventListener("input", applyFilters);
    searchBrigadeInput?.addEventListener("input", applyFilters);
    applyFilters();
});