(function () {
   async function loadState(storageKey, totalColumns) {
    try {
        // Спробуємо загрузити з сервера
        try {
            const response = await fetch(`/assemblers/api/column-preferences/${storageKey}`);
            if (response.ok) {
                const data = await response.json();
                if (data.ok && data.column_order) {
                    const order = data.column_order;
                    const pinned = Array.isArray(data.pinned) ? data.pinned : [];
                    const widths = data.widths && typeof data.widths === "object" ? data.widths : {};
                    if (Array.isArray(order) && order.length === totalColumns) {
                        return {
                            order,
                            widths,
                            pinned,
                        };
                    }
                }
            }
        } catch (e) {
            console.warn("Failed to load column preferences from server, falling back to localStorage", e);
        }

        // Fallback на localStorage
        const parsed = JSON.parse(localStorage.getItem(storageKey) || "null") || {};
        const defaultOrder = Array.from({ length: totalColumns }, (_, index) => index);
        const order = Array.isArray(parsed.order) && parsed.order.length === totalColumns
            ? parsed.order.filter((value) => Number.isInteger(value) && value >= 0 && value < totalColumns)
            : defaultOrder;

        const pinned = Array.isArray(parsed.pinned)
            ? parsed.pinned
                .map((value) => Number(value))
                .filter((value) => Number.isInteger(value) && value >= 0 && value < totalColumns)
            : [];

        return {
            order: order.length === totalColumns ? order : defaultOrder,
            widths: parsed.widths && typeof parsed.widths === "object" ? parsed.widths : {},
            pinned,
        };
    } catch {
        return {
            order: Array.from({ length: totalColumns }, (_, index) => index),
            widths: {},
            pinned: [],
        };
    }
}

    function saveState(storageKey, state) {
        localStorage.setItem(storageKey, JSON.stringify(state));
        
        // Зберігаємо також на сервер (без очікування результату)
        fetch(`/assemblers/api/column-preferences/${storageKey}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                column_order: state.order,
                pinned: state.pinned || [],
                widths: state.widths || {},
            }),
        }).catch(e => console.warn("Failed to save column preferences to server", e));
    }

    function reorderChildren(parent, order) {
        const items = Array.from(parent.children);
        const byIndex = new Map(items.map((item) => [Number(item.dataset.colIndex), item]));
        order.forEach((index) => {
            const item = byIndex.get(index);
            if (item) {
                parent.appendChild(item);
            }
        });
    }

    window.AssemblersTableTools = {
        async initTable({ table, storageKey }) {
            if (!table || !table.tHead || !table.tHead.rows.length) {
                return null;
            }

            const headerRow = table.tHead.rows[0];
            const headerCells = Array.from(headerRow.cells);
            const totalColumns = headerCells.length;
            const state = await loadState(storageKey, totalColumns);

            const pinnedColumns = new Set(state.pinned || []);

const persistPinnedColumns = () => {
    state.pinned = Array.from(pinnedColumns);
    saveState(storageKey, state);
};

const clearPinnedStyles = () => {
    table.querySelectorAll(".is-sticky-col, .is-pinned-header").forEach((cell) => {
        cell.classList.remove("is-sticky-col", "is-pinned-header");
        cell.style.removeProperty("--sticky-left");
    });
};

const applyPinnedColumns = () => {
    if (!table.tHead || !table.tHead.rows.length) {
        return;
    }

    clearPinnedStyles();

    const headerCells = Array.from(table.tHead.rows[0].cells);
    let left = 0;

    headerCells.forEach((headerCell) => {
        const colIndex = Number(headerCell.dataset.colIndex);
        if (!pinnedColumns.has(colIndex)) {
            return;
        }

        const width = Math.ceil(headerCell.getBoundingClientRect().width || 0);
        const colCells = table.querySelectorAll(`[data-col-index="${colIndex}"]`);

        colCells.forEach((cell) => {
            cell.classList.add("is-sticky-col");
            cell.style.setProperty("--sticky-left", `${left}px`);
        });

        headerCell.classList.add("is-pinned-header");
        left += width;
    });
};

const togglePinnedColumn = (headerCell) => {
    const colIndex = Number(headerCell.dataset.colIndex);
    if (!Number.isInteger(colIndex)) {
        return;
    }

    if (pinnedColumns.has(colIndex)) {
        pinnedColumns.delete(colIndex);
    } else {
        pinnedColumns.add(colIndex);
    }

    persistPinnedColumns();
    applyPinnedColumns();
};

            let colgroup = table.querySelector("colgroup");
            if (!colgroup) {
                colgroup = document.createElement("colgroup");
                table.insertBefore(colgroup, table.firstChild);
            }

            if (colgroup.children.length !== totalColumns) {
                colgroup.innerHTML = "";
                for (let index = 0; index < totalColumns; index += 1) {
                    const col = document.createElement("col");
                    col.dataset.colIndex = String(index);
                    colgroup.appendChild(col);
                }
            }

            const cols = Array.from(colgroup.children);
            cols.forEach((col, index) => {
                col.dataset.colIndex = String(index);
            });

            let isResizing = false;
            let autoFitQueued = false;
            let needsAutoFit = Object.keys(state.widths).length < totalColumns;

            const measureCellWidth = (cell) => {
                if (!cell) {
                    return 72;
                }

                if (cell.querySelector("input[type='checkbox']")) {
                    return 52;
                }

                const styles = window.getComputedStyle(cell);
                const probe = document.createElement("span");
                probe.textContent = (cell.textContent || "").trim() || "—";
                probe.style.position = "fixed";
                probe.style.left = "-9999px";
                probe.style.top = "-9999px";
                probe.style.visibility = "hidden";
                probe.style.whiteSpace = "nowrap";
                probe.style.font = styles.font;
                probe.style.fontSize = styles.fontSize;
                probe.style.fontWeight = styles.fontWeight;
                probe.style.letterSpacing = styles.letterSpacing;
                probe.style.textTransform = styles.textTransform;
                document.body.appendChild(probe);

                const paddingX = parseFloat(styles.paddingLeft || "0") + parseFloat(styles.paddingRight || "0");
                const extra = cell.classList.contains("table-col-header") ? 18 : 0;
                const width = Math.ceil(probe.getBoundingClientRect().width + paddingX + extra);

                probe.remove();
                return Math.max(52, Math.min(width, 480));
            };

            const autoFitColumns = () => {
                if (!needsAutoFit) {
                    return;
                }

                const rows = Array.from(table.tBodies).flatMap((tbody) => Array.from(tbody.rows));
                Array.from(headerRow.cells).forEach((headerCell, position) => {
                    const columnIndex = Number(headerCell.dataset.colIndex);
                    if (state.widths[columnIndex]) {
                        return;
                    }

                    let nextWidth = measureCellWidth(headerCell);
                    rows.forEach((row) => {
                        const cell = row.cells[position];
                        if (cell) {
                            nextWidth = Math.max(nextWidth, measureCellWidth(cell));
                        }
                    });
                    state.widths[columnIndex] = nextWidth;
                });

                needsAutoFit = Object.keys(state.widths).length < totalColumns;
                applyWidths();
                saveState(storageKey, state);
            };

            const queueAutoFit = () => {
                if (!needsAutoFit || autoFitQueued) {
                    return;
                }

                autoFitQueued = true;
                requestAnimationFrame(() => {
                    autoFitQueued = false;
                    autoFitColumns();
                });
            };

            const applyWidths = () => {
                Array.from(colgroup.children).forEach((col) => {
                    const index = Number(col.dataset.colIndex);
                    const width = state.widths[index];
                    col.style.width = width ? `${width}px` : "";
                });

                Array.from(headerRow.cells).forEach((cell) => {
                    const index = Number(cell.dataset.colIndex);
                    const width = state.widths[index];
                    cell.style.width = width ? `${width}px` : "";
                    cell.style.minWidth = width ? `${width}px` : "";
                });
            };

            const updateSubcontractClasses = () => {
                const subcontractIndexes = new Set([24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39]);
                table.querySelectorAll("[data-col-index]").forEach((cell) => {
                    const colIndex = Number(cell.dataset.colIndex);
                    if (subcontractIndexes.has(colIndex)) {
                        cell.classList.add("is-subcontract");
                    } else {
                        cell.classList.remove("is-subcontract");
                    }
                });
            };

           const applyOrder = () => {
                reorderChildren(colgroup, state.order);
                reorderChildren(headerRow, state.order);
                Array.from(table.tBodies).forEach((tbody) => {
                    Array.from(tbody.rows).forEach((row) => {
                        reorderChildren(row, state.order);
                    });
                });
                applyWidths();
                updateSubcontractClasses();
                applyPinnedColumns();
                saveState(storageKey, state);
            };

            headerCells.forEach((cell, index) => {
                cell.dataset.colIndex = String(index);
                cell.classList.add("table-col-header");
                cell.draggable = true;

                if (!cell.querySelector(".table-col-resizer")) {
                    const handle = document.createElement("span");
                    handle.className = "table-col-resizer";
                    handle.addEventListener("mousedown", (event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        isResizing = true;
                        const startX = event.clientX;
                        const startWidth = cell.getBoundingClientRect().width;

                        const onMouseMove = (moveEvent) => {
                            const nextWidth = Math.max(24, Math.round(startWidth + moveEvent.clientX - startX));
                            state.widths[index] = nextWidth;
                            applyWidths();
                        };

                        const onMouseUp = () => {
                            document.removeEventListener("mousemove", onMouseMove);
                            document.removeEventListener("mouseup", onMouseUp);
                            isResizing = false;
                            saveState(storageKey, state);
                        };

                        document.addEventListener("mousemove", onMouseMove);
                        document.addEventListener("mouseup", onMouseUp);
                    });
                    cell.appendChild(handle);
                }

                cell.addEventListener("dragstart", (event) => {
                    if (isResizing) {
                        event.preventDefault();
                        return;
                    }
                    event.dataTransfer.setData("text/plain", String(index));
                    event.dataTransfer.effectAllowed = "move";
                    cell.classList.add("is-dragging");
                });

                cell.addEventListener("dragend", () => {
                    cell.classList.remove("is-dragging");
                });

                cell.addEventListener("dragover", (event) => {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = "move";
                });

                cell.addEventListener("drop", (event) => {
                    event.preventDefault();
                    const draggedIndex = Number(event.dataTransfer.getData("text/plain"));
                    const targetIndex = Number(cell.dataset.colIndex);
                    if (!Number.isInteger(draggedIndex) || draggedIndex === targetIndex) {
                        return;
                    }

                    const nextOrder = state.order.filter((value) => value !== draggedIndex);
                    const targetPosition = nextOrder.indexOf(targetIndex);
                    nextOrder.splice(targetPosition, 0, draggedIndex);
                    state.order = nextOrder;
                    applyOrder();
                    applyPinnedColumns();
                });

                cell.addEventListener("dblclick", (event) => {
                    if (isResizing) {
                        event.preventDefault();
                        return;
                    }
                    togglePinnedColumn(cell);
                });
            });

            const applyRow = (row) => {
                Array.from(row.cells).forEach((cell, index) => {
                    if (!cell.dataset.colIndex) {
                        cell.dataset.colIndex = String(index);
                    }
                });
                reorderChildren(row, state.order);
                applyWidths();
                applyPinnedColumns();
                queueAutoFit();
            };

            Array.from(table.tBodies).forEach((tbody) => {
                Array.from(tbody.rows).forEach(applyRow);
            });

            applyOrder();
            queueAutoFit();

            return {
                applyRow,
                applyPinnedColumns,
            };
        },
    };
})();
