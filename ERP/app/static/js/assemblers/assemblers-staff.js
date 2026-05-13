document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector("[data-assemblers-page='staff']");
    const table = page?.querySelector("table");
    const tableBody = page?.querySelector("[data-staff-body]");
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

    window.AssemblersTableTools?.initTable({
        table,
        storageKey: table.dataset.tableKey || "assemblers-staff",
    }).catch(e => console.warn("Failed to initialize table manager", e));

    if (!tableBody || !modal || !modalForm || !modalUser || !modalSourceUserId || !modalSubdivision || !modalBrigade || !brigadeMembersText || !modalSubmit) {
        return;
    }

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
        modalSubdivision.disabled = value;
        modalBrigade.disabled = value;
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
        modalSourceUserId.value = row.dataset.sourceUserId || "";
        modalSubdivision.value = row.dataset.subdivision || "";
        modalBrigade.value = row.dataset.brigadeNumber || "";
        modalUser.textContent = `${row.dataset.name || '—'} | ${row.dataset.username || '—'} | Telegram ID: ${row.dataset.telegramId || '—'}`;
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
});