let workersLoaded = [];
let workersDebounceTimer = null;

function getWorkersRenderMode() {
  const cardsRoot = document.getElementById('workersCardsList');
  if (cardsRoot) return { mode: 'cards', root: cardsRoot };

  const tableBody = document.getElementById('workersTbody');
  if (tableBody) return { mode: 'table', root: tableBody };

  return { mode: 'none', root: null };
}

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

  let data = { ok: false, workers: [] };
  try {
    const r = await fetch('/api/workers?' + params.toString());
    data = await r.json();
  } catch (e) {
    console.error('Не вдалося завантажити /api/workers:', e);
  } finally {
    hideLoader();
  }

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
  const renderTarget = getWorkersRenderMode();
  const emptyBlock = document.getElementById('workersEmpty');

  if (!renderTarget.root) {
    console.warn('Не знайдено контейнер для рендеру робітників (workersCardsList/workersTbody).');
    if (emptyBlock) emptyBlock.classList.remove('hidden');
    return;
  }

  renderTarget.root.innerHTML = '';

  if (!workers.length) {
    if (emptyBlock) emptyBlock.classList.remove('hidden');

    if (renderTarget.mode === 'table') {
      renderTarget.root.innerHTML = '<tr><td colspan="3" class="workers-empty">Нічого не знайдено</td></tr>';
    }
    return;
  }

  if (emptyBlock) emptyBlock.classList.add('hidden');

  workers.forEach(worker => {
    if (renderTarget.mode === 'table') {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>
          <div class="worker-main">
            <div class="worker-avatar">${worker.avatar_path
              ? `<img src="/uploads/${worker.avatar_path}" alt="${worker.name || 'Користувач'}" class="worker-avatar-img" />`
              : `<span class="worker-avatar-letter">${(worker.name || worker.username || '?')[0].toUpperCase()}</span>`}
            </div>
            <div class="worker-info">
              <div class="worker-name">${worker.name || '—'}</div>
            </div>
          </div>
        </td>
        <td><span class="worker-phone">${worker.phone_number || '—'}</span></td>
        <td><span class="worker-role-badge ${worker.is_admin ? 'worker-role-admin' : 'worker-role-user'}">${worker.position || 'Не вказано'}</span></td>
      `;
      renderTarget.root.appendChild(row);
      return;
    }

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

    renderTarget.root.appendChild(card);
  });
}

const workersSearchEl = document.getElementById('workersSearch');
if (workersSearchEl) workersSearchEl.addEventListener('input', debounceLoadWorkers);

const workersPositionEl = document.getElementById('workersPositionFilter');
if (workersPositionEl) workersPositionEl.addEventListener('change', loadWorkers);

(async function initWorkersPage() {
  const ok = await ensureAuthenticated();
  if (!ok) return;
  await loadWorkers();
})();
