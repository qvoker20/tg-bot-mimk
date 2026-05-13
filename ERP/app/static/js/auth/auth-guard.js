(() => {
    const initialUser = window.__ERP_INITIAL_USER__;
    if (!initialUser || typeof fetch !== "function") {
        return;
    }

    const userName = document.getElementById("topbar-user-name");
    const userLogin = document.getElementById("topbar-user-login");
    const userRole = document.getElementById("topbar-user-role");

    const buildState = (user) => JSON.stringify([
        user?.id ?? null,
        user?.name ?? "",
        user?.username ?? "",
        user?.role ?? "",
    ]);

    const syncHeader = (user) => {
        if (userName) {
            userName.textContent = user?.name || "Користувач";
        }
        if (userLogin) {
            userLogin.textContent = `Логін: ${user?.username || "—"}`;
        }
        if (userRole) {
            userRole.textContent = `Роль: ${user?.role || "користувач"}`;
        }
    };

    let currentState = buildState(initialUser);

    const checkSession = async () => {
        try {
            const response = await fetch("/auth/session", {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
                headers: {
                    Accept: "application/json",
                },
            });

            if (response.status === 401) {
                window.location.replace("/");
                return;
            }

            if (!response.ok) {
                return;
            }

            const payload = await response.json();
            if (!payload?.authenticated || !payload.user) {
                window.location.replace("/");
                return;
            }

            const nextState = buildState(payload.user);
            if (nextState !== currentState) {
                syncHeader(payload.user);
                window.location.reload();
                return;
            }

            syncHeader(payload.user);
            currentState = nextState;
        } catch {
            // Ignore transient network failures and re-check on the next interval.
        }
    };

    checkSession();

    const intervalId = window.setInterval(checkSession, 20000);
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            checkSession();
        }
    });
    window.addEventListener("beforeunload", () => {
        window.clearInterval(intervalId);
    });
})();