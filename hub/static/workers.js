async function loadWorkers() {
  showLoader();
  const meResp = await fetch('/api/me');
  const meData = await meResp.json();
  if (!meData.ok) {
    hideLoader();
    window.location.href = '/login';
    return;
  }

  const search = (document.getElementById('workersSearch')?.value || '').trim();
  const position = (document.getElementById('workersPositionFilter')?.value || '').trim();
  const params = new URLSearchParams();
  if (search) params.append('search', search);
  if (position) params.append('position', position);

  const r = await fetch('/api/workers?' + params.toString());
  const data = await r.json();
  hideLoader();

  const tbody = document.getElementById('workersTbody');
  tbody.innerHTML = '';
  if (!data.ok) {
    tbody.innerHTML = '<tr><td colspan="3" class="workers-empty">Не вдалося завантажити список</td></tr>';
    return;
  }

  fillPositionFilter(data.workers);

  if (!data.workers.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="workers-empty">Нічого не знайдено</td></tr>';
    return;
  }

  data.workers.forEach(w => {
    const row = document.createElement('tr');

    const avatarHtml = w.avatar_path
      ? `<img src="/uploads/${w.avatar_path}" alt="${w.name || 'Користувач'}" class="worker-avatar-img" />`
      : `<span class="worker-avatar-letter">${(w.name || w.username || '?')[0].toUpperCase()}</span>`;

    const positionLabel = w.position || 'Не вказано';

    row.innerHTML = `
      <td>
        <div class="worker-main">
        <div class="worker-avatar">${avatarHtml}</div>
        <div class="worker-info">
          <div class="worker-name">${w.name || '—'}</div>
        </div>
        </div>
      </td>
      <td><span class="worker-phone">${w.phone_number || '—'}</span></td>
      <td><span class="worker-role-badge ${w.is_admin ? 'worker-role-admin' : 'worker-role-user'}">${positionLabel}</span></td>
    `;

    tbody.appendChild(row);
  });
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

document.getElementById('workersSearch').addEventListener('input', loadWorkers);
document.getElementById('workersPositionFilter').addEventListener('change', loadWorkers);

loadWorkers();
