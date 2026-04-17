let currentUserId = null;
let allContracts = [];
let usersDebounceTimer = null;
let editingContractId = null;

async function loadMeForNavbar() {
  const r = await fetch('/api/me');
  const data = await r.json();
  if (!data.ok) {
    window.location.href = '/login';
    return false;
  }

  const navProfileName = document.getElementById('navProfileName');
  if (navProfileName) {
    navProfileName.textContent = data.user?.name || 'Профіль';
  }
  return true;
}

async function loadUsers() {
  showLoader();
  const search = document.getElementById('searchInput').value;
  const sort = document.getElementById('roleFilter').value;
  const serviceId = document.getElementById('serviceFilter')?.value || '';
  const connectionStatus = document.getElementById('connectionFilter')?.value || 'all';
  const params = new URLSearchParams();
  if (search) params.append('search', search);
  if (sort) params.append('sort', sort);
  if (serviceId) params.append('service_id', serviceId);
  if (connectionStatus) params.append('connection_status', connectionStatus);
  const r = await fetch('/api/users?' + params.toString());
  const data = await r.json();
  hideLoader();
  const list = document.getElementById('usersList');
  list.innerHTML = '';
  if (!data.ok) return;

  if (!data.users.length) {
    list.innerHTML = '<div class="users-empty">Користувачів не знайдено</div>';
    return;
  }

  data.users.forEach(u => {
    const card = document.createElement('article');
    card.className = 'admin-user-card';
    const services = Array.isArray(u.connected_services) ? u.connected_services : [];
    const visibleServices = services.slice(0, 4);
    const hiddenServicesCount = Math.max(0, services.length - visibleServices.length);
    const servicesHtml = services.length
      ? `<div class="admin-card-services">
           ${visibleServices.map(name => `<span class="service-chip">${escapeHtml(name)}</span>`).join('')}
           ${hiddenServicesCount ? `<span class="service-chip service-chip-more">+${hiddenServicesCount}</span>` : ''}
         </div>`
      : '<div class="admin-card-no-services">Немає підключених сервісів</div>';

    const selectedServiceInfo = serviceId
      ? `<span class="user-role ${u.has_selected_service ? 'role-connected' : 'role-not-connected'}">
           <span class="material-icons-round" style="font-size:13px;vertical-align:middle">${u.has_selected_service ? 'check_circle' : 'cancel'}</span>
           ${u.has_selected_service ? 'Підключено до обраного сервісу' : 'Не підключено до обраного сервісу'}
         </span>`
      : '';

    card.innerHTML = `
      <div class="admin-user-card-main">
        <div class="user-info admin-card-header">
          <span class="user-name">${escapeHtml(u.name || '—')}</span>
          <span class="user-phone">${escapeHtml(u.phone_number || '')}</span>
          <div class="user-badges-wrap">
            <span class="user-role role-${u.role}">
              <span class="material-icons-round" style="font-size:13px;vertical-align:middle">${u.role === 'admin' ? 'shield' : 'person'}</span>
              ${u.role === 'admin' ? 'Адмін' : 'Користувач'}
            </span>
            <span class="user-role role-user">
              <span class="material-icons-round" style="font-size:13px;vertical-align:middle">key</span>
              Сервісів: ${u.services_count || 0}
            </span>
            ${selectedServiceInfo}
          </div>
        </div>
        ${servicesHtml}
      </div>
      <div class="admin-user-card-actions">
        <button class="manage-btn" type="button" data-action="open-services" data-user-id="${u.id}" data-user-name="${escapeHtmlAttr(u.name || '')}">
          <span class="material-icons-round" style="font-size:16px">key</span>
          Сервіси
        </button>
      </div>
    `;
    list.appendChild(card);
  });
}

function escapeHtmlAttr(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

async function loadContracts() {
  const r = await fetch('/api/contracts');
  const data = await r.json();
  if (!data.ok) return;
  allContracts = data.contracts;
  const assignableContracts = data.contracts.filter(c => {
    const type = String(c.service_type || '').toLowerCase();
    // Do not allow Google Sheets/table-like services in assignment modal.
    return !(type.includes('sheet') || type.includes('table'));
  });
  const sel = document.getElementById('selectContract');
  sel.innerHTML = '';
  assignableContracts.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.name;
    sel.appendChild(opt);
  });

  const serviceFilter = document.getElementById('serviceFilter');
  if (serviceFilter) {
    const prev = serviceFilter.value;
    serviceFilter.innerHTML = '<option value="">Всі сервіси</option>';
    assignableContracts.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      serviceFilter.appendChild(opt);
    });
    if (prev && assignableContracts.some(c => String(c.id) === String(prev))) {
      serviceFilter.value = prev;
    }
  }
}

async function openServicesModal(userId, userName) {
  currentUserId = userId;
  document.getElementById('modalUserName').textContent = userName;
  document.getElementById('servicesModal').classList.remove('hidden');
  showLoader();
  await loadUserServices(userId);
  hideLoader();
}

async function loadUserServices(userId) {
  const r = await fetch('/api/user-services?user_id=' + userId);
  const data = await r.json();
  const list = document.getElementById('userServicesList');
  list.innerHTML = '';
  if (!data.ok || !data.services.length) {
    list.innerHTML = '<p style="color:#999;">Немає прив\'язаних сервісів</p>';
    return;
  }
  data.services.forEach(s => {
    const row = document.createElement('div');
    row.className = 'service-row';
    row.dataset.contractId = String(s.contract_id);
    row.dataset.contractTitle = s.contract_title || '';
    row.dataset.login = s.login || '';
    row.innerHTML = `
      <div class="service-info">
        <b>${escapeHtml(s.contract_title)}</b>
        <span>Логін: <code>${escapeHtml(s.login || '—')}</code></span>
        <span>Пароль: <code>Приховано</code></span>
      </div>
      <div class="service-actions">
        <button class="service-action-btn service-edit-btn" type="button" data-action="edit-service" data-contract-id="${s.contract_id}">
          <span class="material-icons-round" style="font-size:14px">edit</span>
          <span>Редагувати</span>
        </button>
        <button class="service-action-btn service-delete-btn" type="button" data-action="delete-service" data-service-id="${s.id}">
          <span class="material-icons-round" style="font-size:14px">delete</span>
          <span>Видалити</span>
        </button>
      </div>
    `;
    list.appendChild(row);
  });
}

function openEditServiceModal(contractId, contractTitle, login) {
  editingContractId = contractId;
  document.getElementById('editServiceContractName').value = contractTitle || '';
  document.getElementById('editServiceLogin').value = login || '';
  document.getElementById('editServicePassword').value = '';
  document.getElementById('editServiceModal').classList.remove('hidden');
  document.getElementById('editServicePassword').focus();
}

function closeEditServiceModal() {
  document.getElementById('editServiceModal').classList.add('hidden');
  editingContractId = null;
}

document.getElementById('addServiceBtn').addEventListener('click', async () => {
  const contract_id = document.getElementById('selectContract').value;
  const login = document.getElementById('serviceLogin').value.trim();
  const password = document.getElementById('servicePassword').value.trim();
  if (!contract_id) return showToast('Оберіть сервіс', 'error');
  if (!login) return showToast('Вкажіть логін', 'error');
  if (!password) return showToast('Вкажіть пароль', 'error');
  showLoader();
  const r = await fetch('/api/user-services', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ user_id: currentUserId, contract_id, login, password })
  });
  const data = await r.json();
  hideLoader();
  if (data.ok) {
    document.getElementById('serviceLogin').value = '';
    document.getElementById('servicePassword').value = '';
    showToast('Сервіс додано!', 'success');
    await loadUserServices(currentUserId);
  } else {
    showToast(data.error || 'Помилка', 'error');
  }
});

async function deleteUserService(id) {
  if (!confirm('Видалити?')) return;
  showLoader();
  const r = await fetch('/api/user-services/' + id, { method: 'DELETE' });
  const data = await r.json();
  hideLoader();
  if (data.ok) {
    showToast('Сервіс видалено', 'success');
    await loadUserServices(currentUserId);
  } else {
    showToast(data.error || 'Помилка', 'error');
  }
}

document.getElementById('usersList').addEventListener('click', async (event) => {
  const btn = event.target.closest('button[data-action="open-services"]');
  if (!btn) return;
  const userId = Number(btn.dataset.userId || 0);
  const userName = btn.dataset.userName || '';
  if (!userId) return;
  await openServicesModal(userId, userName);
});

document.getElementById('userServicesList').addEventListener('click', async (event) => {
  const editBtn = event.target.closest('button[data-action="edit-service"]');
  if (editBtn) {
    const row = editBtn.closest('.service-row');
    if (!row) return;
    const contractId = Number(editBtn.dataset.contractId || row.dataset.contractId || 0);
    const contractTitle = row.dataset.contractTitle || '';
    const login = row.dataset.login || '';
    if (!contractId) return;
    openEditServiceModal(contractId, contractTitle, login);
    return;
  }

  const deleteBtn = event.target.closest('button[data-action="delete-service"]');
  if (deleteBtn) {
    const serviceId = Number(deleteBtn.dataset.serviceId || 0);
    if (!serviceId) return;
    await deleteUserService(serviceId);
  }
});

document.getElementById('saveServiceEditBtn').addEventListener('click', async () => {
  if (!editingContractId || !currentUserId) {
    return showToast('Не вибрано сервіс для редагування', 'error');
  }

  const login = document.getElementById('editServiceLogin').value.trim();
  const password = document.getElementById('editServicePassword').value.trim();
  if (!login) return showToast('Вкажіть логін', 'error');
  if (!password) return showToast('Вкажіть новий пароль', 'error');

  showLoader();
  const r = await fetch('/api/user-services', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      user_id: currentUserId,
      contract_id: editingContractId,
      login,
      password,
    })
  });
  const data = await r.json();
  hideLoader();

  if (!data.ok) {
    return showToast(data.error || 'Помилка оновлення', 'error');
  }

  showToast('Дані доступу оновлено', 'success');
  closeEditServiceModal();
  await loadUserServices(currentUserId);
  await loadUsers();
});

document.getElementById('closeEditServiceModal').addEventListener('click', closeEditServiceModal);

document.getElementById('closeServicesModal').addEventListener('click', () => {
  document.getElementById('servicesModal').classList.add('hidden');
  currentUserId = null;
  closeEditServiceModal();
});

document.getElementById('roleFilter').addEventListener('change', loadUsers);
document.getElementById('serviceFilter').addEventListener('change', loadUsers);
document.getElementById('connectionFilter').addEventListener('change', loadUsers);

document.getElementById('searchInput').addEventListener('input', () => {
  clearTimeout(usersDebounceTimer);
  usersDebounceTimer = setTimeout(loadUsers, 220);
});

(async function initAdminPage() {
  const ok = await loadMeForNavbar();
  if (!ok) return;
  await loadContracts();
  await loadUsers();
})();