let workersLoaded = [];
let workersDebounceTimer = null;

async function ensureAuthenticated() {
  const meResp = await fetch('/api/me');
  const meData = await meResp.json();
  if (!meData.ok) {
    window.location.href = '/login';
    return false;
  }

  const navProfileName = document.getElementById('navProfileName');
  if (navProfileName) {
    navProfileName.textContent = meData.user?.name || 'Профіль';
  }
  return true;
}

function debounceLoadWorkers() {
  clearTimeout(workersDebounceTimer);
  workersDebounceTimer = setTimeout(loadWorkers, 220);
}

function getFilters() {
  return {
    search: (document.getElementById('workersSearch')?.value || '').trim(),
    position: (document.getElementById('workersPositionFilter')?.value || '').trim(),
  };
}

async function loadWorkers() {
  showLoader();
  const filters = getFilters();

  const params = new URLSearchParams();
  if (filters.search) params.append('search', filters.search);
  if (filters.position) params.append('position', filters.position);

  const r = await fetch('/api/workers?' + params.toString());
  const data = await r.json();
  hideLoader();

  if (!data.ok) {
    renderWorkers([]);
    return;
  }

  workersLoaded = data.workers || [];
  fillPositionFilter(workersLoaded);
  renderWorkers(workersLoaded);
}

function fillPositionFilter(workers) {
  const select = document.getElementById('workersPositionFilter');
  if (!select) return;

  const prev = select.value;
  const positions = [...new Set((workers || [])
    .map(w => (w.username || '').trim())
    .filter(Boolean))].sort((a, b) => a.localeCompare(b, 'uk'));

  select.innerHTML = '<option value="">Всі посади</option>';
  positions.forEach(p => {
    const option = document.createElement('option');
    option.value = p;
    option.textContent = '@' + p;
    select.appendChild(option);
  });

  if (prev && positions.includes(prev)) {
    select.value = prev;
  }
}

function renderWorkers(workers) {
  const cardsRoot = document.getElementById('workersCardsList');
  const emptyBlock = document.getElementById('workersEmpty');
  cardsRoot.innerHTML = '';

  if (!workers.length) {
    emptyBlock.classList.remove('hidden');
    return;
  }

  emptyBlock.classList.add('hidden');

  workers.forEach(worker => {
    const card = document.createElement('article');
    card.className = 'worker-card';

    const displayName = worker.name || '—';
    const phone = worker.phone_number || '—';
    const positionLabel = worker.position || 'Не вказано';
    const avatarHtml = worker.avatar_path
      ? `<img src="/uploads/${worker.avatar_path}" alt="${displayName}" class="worker-avatar-img" />`
      : `<span class="worker-avatar-letter">${(worker.name || worker.username || '?')[0].toUpperCase()}</span>`;

    card.innerHTML = `
      <div class="worker-card-top">
        <div class="worker-avatar">${avatarHtml}</div>
        <div class="worker-card-main">
          <h4 class="worker-name">${displayName}</h4>
          <div class="worker-phone">${phone}</div>
          <span class="worker-role-badge ${worker.is_admin ? 'worker-role-admin' : 'worker-role-user'}">${positionLabel}</span>
        </div>
      </div>
    `;

    cardsRoot.appendChild(card);
  });
}

document.getElementById('workersSearch').addEventListener('input', debounceLoadWorkers);
document.getElementById('workersPositionFilter').addEventListener('change', loadWorkers);

(async function initWorkersPage() {
  const ok = await ensureAuthenticated();
  if (!ok) return;
  await loadWorkers();
})();
