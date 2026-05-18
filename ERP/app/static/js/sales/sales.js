document.addEventListener("DOMContentLoaded", () => {
	const statusesNode = document.getElementById("sales-dashboard-statuses");
	const ordersNode = document.getElementById("sales-dashboard-orders");
	const subcontractNode = document.getElementById("sales-subcontract-options");
	if (!statusesNode || !ordersNode || !subcontractNode) return;

	const statuses = JSON.parse(statusesNode.textContent || "[]");
	const orders = JSON.parse(ordersNode.textContent || "[]");
	const subcontractOptions = JSON.parse(subcontractNode.textContent || "[]");

	const laneMap = new Map();
	document.querySelectorAll("[data-sales-lane]").forEach((laneEl) => {
		laneMap.set(laneEl.dataset.salesLane || "", {
			root: laneEl,
			body: laneEl.querySelector("[data-sales-lane-body]"),
			count: laneEl.querySelector("[data-sales-lane-count]"),
		});
	});

	const createModal = document.querySelector("[data-sales-create-modal]");
	const subcontractsModal = document.querySelector("[data-sales-subcontracts-modal]");
	const productsBody = document.querySelector("[data-sales-products-body]");
	const subcontractsList = document.querySelector("[data-sales-subcontracts-list]");
	const stepPanels = Array.from(document.querySelectorAll("[data-sales-step-panel]"));
	const stepChips = Array.from(document.querySelectorAll("[data-sales-step]"));

	const state = {
		orders,
		currentStep: 1,
		draft: {
			order_number: "",
			customer: "",
			order_type: "",
			sign_date: "",
			install_date: "",
		},
		products: [],
		activeProductIndex: null,
	};

	function formatNow() {
		const date = new Date();
		const dd = String(date.getDate()).padStart(2, "0");
		const mm = String(date.getMonth() + 1).padStart(2, "0");
		const hh = String(date.getHours()).padStart(2, "0");
		const min = String(date.getMinutes()).padStart(2, "0");
		return `${dd}.${mm} ${hh}:${min}`;
	}

	function escapeHtml(value) {
		return String(value || "")
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;");
	}

	function statusClass(status) {
		if (status === "Перевірено" || status === "Передано в КБ") return "is-true";
		if (status === "Переробка") return "is-false";
		return "";
	}

	function renderCard(order) {
		return `
			<article class="sales-card">
				<div class="sales-card-head">
					<div>
						<p class="sales-card-title">Замовлення №${escapeHtml(order.order_number)}</p>
						<p class="sales-card-subtitle">Клієнт: ${escapeHtml(order.customer)}</p>
					</div>
					<span class="sales-card-status">${escapeHtml(order.status)}</span>
				</div>

				<dl class="sales-card-meta">
					<div><dt>Тип</dt><dd>${escapeHtml(order.order_type)}</dd></div>
					<div><dt>Менеджер</dt><dd>${escapeHtml(order.manager || "-")}</dd></div>
					<div><dt>Створено</dt><dd>${escapeHtml(order.created_at || "-")}</dd></div>
					<div><dt>Редаговано</dt><dd>${escapeHtml(order.updated_at || "-")}</dd></div>
					<div><dt>Дата підписання</dt><dd>${escapeHtml(order.sign_date || "-")}</dd></div>
					<div><dt>Дата монтажу</dt><dd>${escapeHtml(order.install_date || "-")}</dd></div>
				</dl>

				<div class="sales-card-flags">
					<span class="sales-flag">Виробів: ${escapeHtml(order.products || 0)}</span>
					<span class="sales-flag ${statusClass(order.status)}">Статус: ${escapeHtml(order.status)}</span>
				</div>
			</article>
		`;
	}

	function renderBoard() {
		statuses.forEach((status) => {
			const lane = laneMap.get(status);
			if (!lane || !lane.body || !lane.count) return;

			const rows = state.orders.filter((item) => item.status === status);
			lane.count.textContent = String(rows.length);
			if (!rows.length) {
				lane.body.innerHTML = '<div class="sales-empty">Поки що записів немає</div>';
				return;
			}

			lane.body.innerHTML = rows.map(renderCard).join("");
		});
	}

	function setStep(step) {
		state.currentStep = step;
		stepPanels.forEach((panel) => {
			panel.classList.toggle("hidden", Number(panel.dataset.salesStepPanel) !== step);
		});
		stepChips.forEach((chip) => {
			chip.classList.toggle("is-active", Number(chip.dataset.salesStepIndex) === step);
		});
	}

	function resetDraft() {
		state.draft = {
			order_number: "",
			customer: "",
			order_type: "",
			sign_date: "",
			install_date: "",
		};
		state.products = [];
		state.activeProductIndex = null;

		document.querySelectorAll("[data-order-field]").forEach((input) => {
			input.value = "";
		});
		renderProducts();
		setStep(1);
	}

	function showModal(modal) {
		if (!modal) return;
		modal.classList.remove("hidden");
		modal.setAttribute("aria-hidden", "false");
	}

	function hideModal(modal) {
		if (!modal) return;
		modal.classList.add("hidden");
		modal.setAttribute("aria-hidden", "true");
	}

	function productSubcontractsLabel(product) {
		const active = Object.entries(product.subcontracts || {})
			.filter(([, value]) => value)
			.map(([name]) => name);
		return active.length ? `Обрано: ${active.length}` : "Обрати";
	}

	function renderProducts() {
		if (!productsBody) return;
		if (!state.products.length) {
			productsBody.innerHTML = `
				<tr>
					<td colspan="6" class="sales-empty">Натисни +1, щоб додати виріб</td>
				</tr>
			`;
			return;
		}

		productsBody.innerHTML = state.products
			.map(
				(product, index) => `
				<tr data-product-index="${index}">
					<td><input type="text" data-product-field="part" value="${escapeHtml(product.part)}" placeholder="Напр. A1"></td>
					<td><input type="text" data-product-field="name" value="${escapeHtml(product.name)}" placeholder="Назва виробу"></td>
					<td><input type="number" min="0" step="0.01" data-product-field="price" value="${escapeHtml(product.price)}" placeholder="0"></td>
					<td><input type="checkbox" data-product-field="measure" ${product.measure ? "checked" : ""}></td>
					<td><button type="button" class="ghost-button" data-product-subcontracts>${productSubcontractsLabel(product)}</button></td>
					<td><button type="button" class="ghost-button" data-product-remove>Видалити</button></td>
				</tr>
			`,
			)
			.join("");
	}

	function validateStepOne() {
		if (!state.draft.order_number.trim()) {
			alert("Вкажіть номер замовлення");
			return false;
		}
		if (!state.draft.customer.trim()) {
			alert("Вкажіть замовника");
			return false;
		}
		if (!state.draft.order_type.trim()) {
			alert("Оберіть тип замовлення");
			return false;
		}
		return true;
	}

	function validateProducts() {
		if (!state.products.length) {
			alert("Додайте хоча б один виріб");
			return false;
		}

		for (const row of state.products) {
			if (!String(row.part || "").trim() || !String(row.name || "").trim()) {
				alert("У кожному виробі потрібно вказати частину і назву");
				return false;
			}
		}
		return true;
	}

	function openSubcontracts(index) {
		state.activeProductIndex = index;
		if (!subcontractsList) return;

		const current = state.products[index];
		subcontractsList.innerHTML = subcontractOptions
			.map((option) => {
				const checked = current.subcontracts?.[option] ? "checked" : "";
				return `
					<label class="sales-checkbox">
						<input type="checkbox" data-subcontract-item="${escapeHtml(option)}" ${checked}>
						<span>${escapeHtml(option)}</span>
					</label>
				`;
			})
			.join("");
		showModal(subcontractsModal);
	}

	function applySubcontracts() {
		const index = state.activeProductIndex;
		if (index === null || index === undefined) return;

		const map = {};
		subcontractsList.querySelectorAll("[data-subcontract-item]").forEach((checkbox) => {
			map[checkbox.dataset.subcontractItem || ""] = checkbox.checked;
		});
		state.products[index].subcontracts = map;
		renderProducts();
		hideModal(subcontractsModal);
	}

	document.querySelector("[data-sales-open-create-modal]")?.addEventListener("click", () => {
		resetDraft();
		showModal(createModal);
	});

	document.querySelectorAll("[data-sales-close-create-modal]").forEach((button) => {
		button.addEventListener("click", () => hideModal(createModal));
	});

	document.querySelectorAll("[data-sales-close-subcontracts]").forEach((button) => {
		button.addEventListener("click", () => hideModal(subcontractsModal));
	});

	document.querySelector("[data-sales-next-step]")?.addEventListener("click", () => {
		if (!validateStepOne()) return;
		setStep(2);
	});

	document.querySelector("[data-sales-prev-step]")?.addEventListener("click", () => setStep(1));

	document.querySelectorAll("[data-order-field]").forEach((input) => {
		input.addEventListener("input", () => {
			state.draft[input.dataset.orderField || ""] = input.value;
		});
		input.addEventListener("change", () => {
			state.draft[input.dataset.orderField || ""] = input.value;
		});
	});

	document.querySelector("[data-sales-add-product]")?.addEventListener("click", () => {
		state.products.push({
			part: "",
			name: "",
			price: "",
			measure: false,
			subcontracts: {},
		});
		renderProducts();
	});

	productsBody?.addEventListener("input", (event) => {
		const target = event.target;
		const row = target.closest("tr[data-product-index]");
		if (!row) return;
		const index = Number(row.dataset.productIndex);
		const field = target.dataset.productField;
		if (!Number.isFinite(index) || !field) return;

		if (field === "measure") {
			state.products[index][field] = target.checked;
			return;
		}
		state.products[index][field] = target.value;
	});

	productsBody?.addEventListener("click", (event) => {
		const target = event.target;
		const row = target.closest("tr[data-product-index]");
		if (!row) return;
		const index = Number(row.dataset.productIndex);
		if (!Number.isFinite(index)) return;

		if (target.hasAttribute("data-product-remove")) {
			state.products.splice(index, 1);
			renderProducts();
			return;
		}
		if (target.hasAttribute("data-product-subcontracts")) {
			openSubcontracts(index);
		}
	});

	document.querySelector("[data-sales-apply-subcontracts]")?.addEventListener("click", applySubcontracts);

	document.querySelector("[data-sales-save-order]")?.addEventListener("click", () => {
		if (!validateStepOne()) {
			setStep(1);
			return;
		}
		if (!validateProducts()) return;

		const now = formatNow();
		const manager = (window.__ERP_INITIAL_USER__ && window.__ERP_INITIAL_USER__.name) || "Поточний менеджер";

		state.orders.unshift({
			order_number: state.draft.order_number.trim(),
			status: "Нові",
			customer: state.draft.customer.trim(),
			order_type: state.draft.order_type,
			manager,
			created_at: now,
			updated_at: now,
			sign_date: state.draft.sign_date || "-",
			install_date: state.draft.install_date || "-",
			products: state.products.length,
			product_rows: state.products,
		});

		renderBoard();
		hideModal(createModal);
		resetDraft();
	});

	renderProducts();
	renderBoard();
});