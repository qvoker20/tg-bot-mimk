(() => {
    const MOBILE_MEDIA = window.matchMedia("(max-width: 900px)");

    const syncBodyState = () => {
        const hasOpenSidebar = Boolean(document.querySelector(".module-shell.has-collapsible-sidebar.is-sidebar-open"));
        document.body.classList.toggle("has-module-sidebar-open", hasOpenSidebar && MOBILE_MEDIA.matches);
    };

    const enhanceModuleShell = (shell) => {
        if (!shell || shell.dataset.sidebarEnhanced === "true") {
            return;
        }

        const sidebar = shell.querySelector(".module-sidebar");
        const toolbarHead = shell.querySelector(".module-toolbar-head") || shell.querySelector(".module-content");
        const sidebarHead = sidebar?.querySelector(".module-sidebar-head");
        if (!sidebar || !toolbarHead || !sidebarHead) {
            return;
        }

        shell.dataset.sidebarEnhanced = "true";
        shell.classList.add("has-collapsible-sidebar");

        const toggleButton = document.createElement("button");
        toggleButton.type = "button";
        toggleButton.className = "ghost-button module-sidebar-toggle";
        toggleButton.setAttribute("aria-expanded", "false");
        toggleButton.setAttribute("aria-label", "Показати навігацію");
        toggleButton.textContent = "Меню";
        toolbarHead.prepend(toggleButton);

        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "module-sidebar-close";
        closeButton.setAttribute("aria-label", "Сховати навігацію");
        closeButton.textContent = "Закрити";
        sidebarHead.append(closeButton);

        const backdrop = document.createElement("div");
        backdrop.className = "module-sidebar-backdrop";
        backdrop.hidden = false;
        shell.append(backdrop);

        const closeSidebar = () => {
            shell.classList.remove("is-sidebar-open");
            toggleButton.setAttribute("aria-expanded", "false");
            syncBodyState();
        };

        const openSidebar = () => {
            if (!MOBILE_MEDIA.matches) {
                return;
            }
            shell.classList.add("is-sidebar-open");
            toggleButton.setAttribute("aria-expanded", "true");
            syncBodyState();
        };

        toggleButton.addEventListener("click", () => {
            if (shell.classList.contains("is-sidebar-open")) {
                closeSidebar();
                return;
            }
            openSidebar();
        });

        closeButton.addEventListener("click", closeSidebar);
        backdrop.addEventListener("click", closeSidebar);
        sidebar.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeSidebar));

        MOBILE_MEDIA.addEventListener("change", () => {
            if (!MOBILE_MEDIA.matches) {
                closeSidebar();
            } else {
                syncBodyState();
            }
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && shell.classList.contains("is-sidebar-open")) {
                closeSidebar();
            }
        });
    };

    const init = () => {
        document.querySelectorAll(".module-shell").forEach(enhanceModuleShell);
        syncBodyState();
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
    } else {
        init();
    }
})();
