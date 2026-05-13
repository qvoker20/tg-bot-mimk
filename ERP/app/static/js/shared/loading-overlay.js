(() => {
    const root = document.querySelector("[data-global-loader]");
    const messageNode = root?.querySelector("[data-global-loader-text]");
    if (!root || !messageNode) {
        return;
    }

    const defaultMessage = (messageNode.textContent || "").trim() || "Завантаження...";
    const activeLoaders = new Map();
    let nextLoaderId = 0;

    const syncState = () => {
        if (!activeLoaders.size) {
            root.classList.remove("is-active");
            document.body.classList.remove("has-global-loader");
            messageNode.textContent = defaultMessage;
            return;
        }

        const messages = Array.from(activeLoaders.values());
        messageNode.textContent = messages[messages.length - 1] || defaultMessage;
        root.classList.add("is-active");
        document.body.classList.add("has-global-loader");
    };

    const show = () => {
        const loaderId = ++nextLoaderId;
        activeLoaders.set(loaderId, defaultMessage);
        syncState();
        return loaderId;
    };

    const hide = (loaderId) => {
        if (typeof loaderId === "number") {
            activeLoaders.delete(loaderId);
        }
        syncState();
    };

    const withLoader = async (operation, options = {}) => {
        const loaderId = show(options.message);
        try {
            return await operation();
        } finally {
            hide(loaderId);
        }
    };

    window.ERPLoading = {
        show,
        hide,
        withLoader,
        isActive: () => activeLoaders.size > 0,
    };
})();