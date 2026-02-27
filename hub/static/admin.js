let currentUserId = null;
let allContracts = [];

async function loadUsers() {
  showLoader();
  const search = document.getElementById('searchInput').value;
  const sort = document.getElementById('roleFilter').value;
  const params = new URLSearchParams();
  if (search) params.append('search', search);
  if (sort) params.append('sort', sort);
  const r = await fetch('/api/users?' + params.toString());
  const data = await r.json();
  hideLoader();
  const list = document.getElementById('usersList');
  list.innerHTML = '';
  if (!data.ok) return;
  data.users.forEach(u => {
    const row = document.createElement('div');
    row.className = 'user-row';
    row.innerHTML = `
      <div class="user-info">
        <span class="user-name">${u.name || '—'}</span>
        <span class="user-phone">${u.phone_number || ''}</span>
        <span class="user-role role-${u.role}">
          <span class="material-icons-round" style="font-size:13px;vertical-align:middle">${u.role === 'admin' ? 'shield' : 'person'}</span>
          ${u.role === 'admin' ? 'Адмін' : 'Користувач'}
        </span>
      </div>
      <button class="manage-btn" onclick="openServicesModal(${u.id}, '${(u.name || '').replace(/'/g, '')}')">
        <span class="material-icons-round" style="font-size:16px">key</span>
        Сервіси
      </button>
    `;
    list.appendChild(row);
  });
}

async function loadContracts() {
  const r = await fetch('/api/contracts');
  const data = await r.json();
  if (!data.ok) return;
  allContracts = data.contracts;
  const sel = document.getElementById('selectContract');
  sel.innerHTML = '';
  data.contracts.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.name + (c.service_type === 'sheet' ? ' 📊' : ' 🌐');
    sel.appendChild(opt);
  });
}

window.openServicesModal = async function(userId, userName) {
  currentUserId = userId;
  document.getElementById('modalUserName').textContent = userName;
  document.getElementById('servicesModal').classList.remove('hidden');
  showLoader();
  await loadUserServices(userId);
  hideLoader();
};

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
    row.innerHTML = `
      <div class="service-info">
        <b>${s.contract_title}</b>
        <span>Логін: <code>${s.login || '—'}</code></span>
        <span>Пароль: <code>${s.password || '—'}</code></span>
      </div>
      <button class="delete-btn" onclick="deleteUserService(${s.id})">🗑️</button>
    `;
    list.appendChild(row);
  });
}

document.getElementById('addServiceBtn').addEventListener('click', async () => {
  const contract_id = document.getElementById('selectContract').value;
  const login = document.getElementById('serviceLogin').value.trim();
  const password = document.getElementById('servicePassword').value.trim();
  if (!contract_id) return showToast('Оберіть сервіс', 'error');
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

window.deleteUserService = async function(id) {
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
};

document.getElementById('closeServicesModal').addEventListener('click', () => {
  document.getElementById('servicesModal').classList.add('hidden');
  currentUserId = null;
});

document.getElementById('searchInput').addEventListener('input', loadUsers);
document.getElementById('roleFilter').addEventListener('change', loadUsers);

loadUsers();
loadContracts();