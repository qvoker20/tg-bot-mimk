// ─── LOGIN PAGE ───
const sendCodeBtn = document.getElementById('sendCodeBtn');
const loginBtn = document.getElementById('loginBtn');

if (sendCodeBtn) {
  const phoneEl = document.getElementById('phone');
  const codeEl = document.getElementById('code');
  const msgEl = document.getElementById('msg');
  const codeBlockEl = document.getElementById('codeBlock');

  sendCodeBtn.addEventListener('click', async () => {
    msgEl.textContent = '';
    sendCodeBtn.disabled = true;
    sendCodeBtn.textContent = 'Надсилаю...';
    const phone_number = phoneEl.value.trim();
    const r = await fetch('/api/auth/request-code', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ phone_number })
    });
    const data = await r.json();
    sendCodeBtn.disabled = false;
    sendCodeBtn.textContent = 'Надіслати код';
    if (!data.ok) {
      msgEl.textContent = data.error || 'Помилка';
      msgEl.style.color = '#e53935';
      return;
    }
    codeBlockEl.classList.remove('hidden');
    msgEl.textContent = '✅ Код надіслано у Telegram';
    msgEl.style.color = '#2e7d32';
  });

  document.getElementById('loginBtn').addEventListener('click', async () => {
    msgEl.textContent = '';
    const phone_number = phoneEl.value.trim();
    const code = codeEl.value.trim();
    const btn = document.getElementById('loginBtn');
    btn.disabled = true;
    btn.textContent = 'Вхід...';
    const r = await fetch('/api/auth/verify', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ phone_number, code })
    });
    const data = await r.json();
    btn.disabled = false;
    btn.textContent = 'Увійти';
    if (!data.ok) {
      msgEl.textContent = data.error || 'Помилка';
      msgEl.style.color = '#e53935';
      return;
    }
    window.location.href = '/';
  });
}

// ─── MAIN PAGE ───
const siteCards = document.getElementById('siteCards');
const sheetCards = document.getElementById('sheetCards');

if (siteCards) {
  let currentRole = 'user';

  async function loadMe() {
    showLoader();
    const r = await fetch('/api/me');
    const data = await r.json();
    hideLoader();
    if (!data.ok) { window.location.href = '/login'; return; }
    currentRole = data.user.role;
    document.getElementById('navName').textContent = data.user.name || data.user.username;
    if (currentRole === 'admin') {
      document.getElementById('adminLink').classList.remove('hidden');
      document.getElementById('fabAdd').classList.remove('hidden');
    }
    loadContracts();
  }

  async function loadContracts() {
    showLoader();
    const r = await fetch('/api/contracts');
    const data = await r.json();
    hideLoader();
    if (!data.ok) return;
    allContracts = data.contracts;
    const q = document.getElementById('serviceSearch') ? document.getElementById('serviceSearch').value : '';
    renderAll(q);
  }

  let allContracts = [];
  let sitePage = 0;
  let sheetPage = 0;
  const PER_PAGE = 8;

  function renderAll(query) {
    const q = query.trim().toLowerCase();
    const sites = allContracts.filter(c => c.service_type !== 'sheet' && (!q || c.name.toLowerCase().includes(q)));
    const sheets = allContracts.filter(c => c.service_type === 'sheet' && (!q || c.name.toLowerCase().includes(q)));
    if (q) { sitePage = 0; sheetPage = 0; }
    renderSection('site', sites);
    renderSection('sheet', sheets);
  }

  function renderSection(type, contracts) {
    const gridEl = document.getElementById(type === 'site' ? 'siteCards' : 'sheetCards');
    const infoEl = document.getElementById(type === 'site' ? 'sitePageInfo' : 'sheetPageInfo');
    const prevBtn = document.getElementById(type === 'site' ? 'sitePrev' : 'sheetPrev');
    const nextBtn = document.getElementById(type === 'site' ? 'siteNext' : 'sheetNext');
    const page = type === 'site' ? sitePage : sheetPage;
    const totalPages = Math.max(1, Math.ceil(contracts.length / PER_PAGE));
    const safePage = Math.min(page, totalPages - 1);
    if (type === 'site') sitePage = safePage;
    else sheetPage = safePage;

    const slice = contracts.slice(safePage * PER_PAGE, safePage * PER_PAGE + PER_PAGE);
    gridEl.innerHTML = '';
    if (!slice.length) {
      gridEl.innerHTML = '<p class="cards-empty">Нічого не знайдено</p>';
    } else {
      slice.forEach(c => gridEl.appendChild(createCard(c)));
    }

    infoEl.textContent = contracts.length ? `${safePage + 1} / ${totalPages}` : '';
    prevBtn.disabled = safePage === 0;
    nextBtn.disabled = safePage >= totalPages - 1 || !contracts.length;

    prevBtn.onclick = () => {
      if (type === 'site') sitePage = Math.max(0, sitePage - 1);
      else sheetPage = Math.max(0, sheetPage - 1);
      renderSection(type, contracts);
    };
    nextBtn.onclick = () => {
      if (type === 'site') sitePage = Math.min(totalPages - 1, sitePage + 1);
      else sheetPage = Math.min(totalPages - 1, sheetPage + 1);
      renderSection(type, contracts);
    };
  }

  function createCard(c) {
    const card = document.createElement('div');
    card.className = 'contract-card';
    card.innerHTML = `
      ${c.image ? `<div class="card-img-wrap"><img src="/uploads/${c.image}" alt="${c.name}"></div>` : '<div class="card-no-img"><span class="material-icons-round">dns</span></div>'}
      <div class="card-body">
        <span class="card-type-badge">${c.service_type === 'sheet' ? '<span class="material-icons-round" style="font-size:12px">table_chart</span> Таблиця' : '<span class="material-icons-round" style="font-size:12px">language</span> Сайт'}</span>
        <h4>${c.name}</h4>
        ${c.description ? `<p>${c.description}</p>` : ''}
      </div>
      <div class="card-footer">
        <span class="card-open-hint"><span class="material-icons-round" style="font-size:13px">touch_app</span> Натисни щоб відкрити</span>
      </div>
    `;
    card.addEventListener('click', (e) => openCardDetail(c, card));
    return card;
  }

  let _currentCardId = null;
  let _openCardEl = null;

  function openCardDetail(c, cardEl) {
    _currentCardId = c.id;
    _openCardEl = cardEl;
    const modal = document.getElementById('cardDetailModal');
    const modalContent = modal.querySelector('.modal-content');
    const imgWrap = document.getElementById('cardDetailImage');
    const img = document.getElementById('cardDetailImg');
    const typeEl = document.getElementById('cardDetailType');
    const nameEl = document.getElementById('cardDetailName');
    const descEl = document.getElementById('cardDetailDesc');
    const linkEl = document.getElementById('cardDetailLink');
    const credsBtn = document.getElementById('cardDetailCredsBtn');
    const adminActions = document.getElementById('cardDetailAdminActions');

    if (c.image) {
      img.src = '/uploads/' + c.image;
      imgWrap.classList.remove('hidden');
    } else {
      imgWrap.classList.add('hidden');
    }

    typeEl.innerHTML = c.service_type === 'sheet'
      ? '<span class="material-icons-round" style="font-size:14px">table_chart</span> Гугл таблиця'
      : '<span class="material-icons-round" style="font-size:14px">language</span> Сайт';

    nameEl.textContent = c.name;
    descEl.textContent = c.description || '';

    if (c.url) {
      linkEl.href = c.url;
      linkEl.classList.remove('hidden');
    } else {
      linkEl.classList.add('hidden');
    }

    // Reset inline creds panel on open
    const credsPanel = document.getElementById('cardDetailCredsPanel');
    credsPanel.classList.add('hidden');
    document.getElementById('cardDetailCredsLogin').textContent = '';
    document.getElementById('cardDetailCredsPassword').textContent = '';

    if (c.service_type === 'sheet') {
      credsBtn.classList.add('hidden');
      credsPanel.classList.add('hidden');
      credsBtn.onclick = null;
    } else {
      credsBtn.classList.remove('hidden');
      credsBtn.setAttribute('data-open', '0');
      credsBtn.innerHTML = '<span class="material-icons-round" style="font-size:16px">key</span> Мої дані';
      credsBtn.onclick = async (e) => {
        e.stopPropagation();
        if (credsBtn.getAttribute('data-open') === '1') {
          credsPanel.classList.add('hidden');
          credsBtn.setAttribute('data-open', '0');
          credsBtn.innerHTML = '<span class="material-icons-round" style="font-size:16px">key</span> Мої дані';
          return;
        }
        showLoader();
        const r = await fetch('/api/my-service/' + c.id);
        const data = await r.json();
        hideLoader();
        if (!data.ok) { showToast('Немає даних для цього сервісу', 'error'); return; }
        document.getElementById('cardDetailCredsLogin').textContent = data.login || '—';
        document.getElementById('cardDetailCredsPassword').textContent = data.password || '—';
        credsPanel.classList.remove('hidden');
        credsBtn.setAttribute('data-open', '1');
        credsBtn.innerHTML = '<span class="material-icons-round" style="font-size:16px">visibility_off</span> Сховати';
      };
    }

    if (currentRole === 'admin') {
      adminActions.classList.remove('hidden');
      document.getElementById('cardDetailEditBtn').onclick = (e) => {
        e.stopPropagation();
        closeCardDetail();
        setTimeout(() => openEditModal(c.id, escape(c.name), escape(c.url || ''), escape(c.description || ''), c.service_type), 360);
      };
      document.getElementById('cardDetailDeleteBtn').onclick = async (e) => {
        e.stopPropagation();
        closeCardDetail();
        setTimeout(() => deleteContract(c.id), 360);
      };
    } else {
      adminActions.classList.add('hidden');
    }

    // ─── HERO ANIMATION ───
    const rect = cardEl.getBoundingClientRect();
    const vpCx = window.innerWidth / 2;
    const vpCy = window.innerHeight / 2;
    const cardCx = rect.left + rect.width / 2;
    const cardCy = rect.top + rect.height / 2;

    // final modal size (approximate)
    const finalW = Math.min(500, window.innerWidth - 32);
    const finalH = modalContent.offsetHeight || 520;

    const scaleX = rect.width / finalW;
    const scaleY = rect.height / Math.max(finalH, 300);
    const scale = Math.max(scaleX, scaleY);
    const tx = cardCx - vpCx;
    const ty = cardCy - vpCy;

    // start: modal positioned at card, scaled down
    modalContent.style.transition = 'none';
    modalContent.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    modalContent.style.opacity = '0';
    modalContent.style.borderRadius = getComputedStyle(cardEl).borderRadius;

    // backdrop start
    modal.style.transition = 'none';
    modal.style.background = 'rgba(10,12,30,0)';
    modal.style.backdropFilter = 'blur(0px)';
    modal.classList.remove('hidden');

    // force reflow
    void modalContent.offsetWidth;

    // animate to final
    modalContent.style.transition = 'transform 0.5s cubic-bezier(0.34,1.15,0.64,1), opacity 0.3s ease, border-radius 0.45s ease';
    modal.style.transition = 'background 0.4s ease, backdrop-filter 0.4s ease';

    requestAnimationFrame(() => {
      modalContent.style.transform = 'translate(0,0) scale(1)';
      modalContent.style.opacity = '1';
      modalContent.style.borderRadius = '24px';
      modal.style.background = 'rgba(10,12,30,0.55)';
      modal.style.backdropFilter = 'blur(8px)';
    });
  }

  function closeCardDetail() {
    const modal = document.getElementById('cardDetailModal');
    const modalContent = modal.querySelector('.modal-content');

    modalContent.style.transition = 'transform 0.42s cubic-bezier(0.4,0,0.8,1), opacity 0.3s ease, border-radius 0.4s ease';
    modal.style.transition = 'background 0.35s ease, backdrop-filter 0.35s ease';
    modal.style.background = 'rgba(10,12,30,0)';
    modal.style.backdropFilter = 'blur(0px)';

    if (_openCardEl) {
      const rect = _openCardEl.getBoundingClientRect();
      const vpCx = window.innerWidth / 2;
      const vpCy = window.innerHeight / 2;
      const cardCx = rect.left + rect.width / 2;
      const cardCy = rect.top + rect.height / 2;
      const finalW = Math.min(500, window.innerWidth - 32);
      const finalH = modalContent.offsetHeight || 520;
      const scaleX = rect.width / finalW;
      const scaleY = rect.height / Math.max(finalH, 300);
      const scale = Math.max(scaleX, scaleY);
      const tx = cardCx - vpCx;
      const ty = cardCy - vpCy;
      modalContent.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
      modalContent.style.borderRadius = getComputedStyle(_openCardEl).borderRadius;
    } else {
      modalContent.style.transform = 'scale(0.85)';
    }
    modalContent.style.opacity = '0';

    setTimeout(() => {
      modal.classList.add('hidden');
      modalContent.style.transition = '';
      modalContent.style.transform = '';
      modalContent.style.opacity = '';
      modalContent.style.borderRadius = '';
      modal.style.background = '';
      modal.style.backdropFilter = '';
      _openCardEl = null;
    }, 420);
  }

  document.getElementById('closeCardDetail').addEventListener('click', closeCardDetail);
  document.getElementById('cardDetailModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('cardDetailModal')) closeCardDetail();
  });

  document.getElementById('fabAdd').addEventListener('click', () => {
    document.getElementById('addModal').classList.remove('hidden');
  });
  document.getElementById('closeModal').addEventListener('click', () => {
    document.getElementById('addModal').classList.add('hidden');
  });

  document.getElementById('addContractForm').addEventListener('submit', async e => {
    e.preventDefault();
    showLoader();
    const fd = new FormData(e.target);
    const r = await fetch('/api/contracts', { method: 'POST', body: fd });
    const data = await r.json();
    hideLoader();
    if (data.ok) {
      e.target.reset();
      document.getElementById('addModal').classList.add('hidden');
      showToast('Сервіс додано!', 'success');
      loadContracts();
    } else {
      showToast(data.error || 'Помилка', 'error');
    }
  });

  document.getElementById('contractName').addEventListener('input', async e => {
    const q = e.target.value;
    const suggestions = document.getElementById('suggestions');
    suggestions.innerHTML = '';
    if (!q) return;
    const r = await fetch('/api/contracts/search?q=' + encodeURIComponent(q));
    const data = await r.json();
    if (data.ok && data.names.length) {
      data.names.forEach(name => {
        const span = document.createElement('span');
        span.textContent = name;
        span.onclick = () => { document.getElementById('contractName').value = name; suggestions.innerHTML = ''; };
        suggestions.appendChild(span);
      });
    }
  });

  window.openEditModal = function(id, name, url, description, service_type) {
    document.getElementById('editId').value = id;
    document.getElementById('editName').value = unescape(name);
    document.getElementById('editUrl').value = unescape(url);
    document.getElementById('editDescription').value = unescape(description);
    document.getElementById('editServiceType').value = service_type;
    document.getElementById('editModal').classList.remove('hidden');
    loadConnectedUsers(id);
  };
  document.getElementById('closeEditModal').addEventListener('click', () => {
    document.getElementById('editModal').classList.add('hidden');
  });

  document.getElementById('editContractForm').addEventListener('submit', async e => {
    e.preventDefault();
    showLoader();
    const id = document.getElementById('editId').value;
    const fd = new FormData(e.target);
    const r = await fetch('/api/contracts/' + id, { method: 'PUT', body: fd });
    const data = await r.json();
    hideLoader();
    if (data.ok) {
      document.getElementById('editModal').classList.add('hidden');
      showToast('Збережено!', 'success');
      loadContracts();
    } else {
      showToast(data.error || 'Помилка', 'error');
    }
  });

  async function loadConnectedUsers(contractId) {
    const countEl = document.getElementById('editUsersCount');
    const listEl = document.getElementById('editUsersList');
    if (!countEl || !listEl) return;

    listEl.textContent = 'Завантаження...';
    const r = await fetch('/api/contracts/' + contractId + '/users');
    const data = await r.json();

    if (!data.ok) {
      countEl.textContent = '0';
      listEl.textContent = 'Не вдалося завантажити';
      return;
    }

    countEl.textContent = data.count || 0;
    if (!data.users || !data.users.length) {
      listEl.textContent = 'Немає підключень';
      return;
    }

    listEl.innerHTML = data.users
      .map(user => {
        const name = user.name || '—';
        const phone = user.phone_number || '';
        return `<div class="service-users-item"><span>${name}</span><span>${phone}</span></div>`;
      })
      .join('');
  }

  window.deleteContract = async function(id) {
    if (!confirm('Видалити сервіс?')) return;
    showLoader();
    const r = await fetch('/api/contracts/' + id, { method: 'DELETE' });
    const data = await r.json();
    hideLoader();
    if (data.ok) {
      showToast('Видалено!', 'success');
      loadContracts();
    } else {
      showToast(data.error || 'Помилка', 'error');
    }
  };

  window.showMyCredentials = async function(contractId, contractName) {
    showLoader();
    const r = await fetch('/api/my-service/' + contractId);
    const data = await r.json();
    hideLoader();
    if (!data.ok) {
      showToast('Немає даних для цього сервісу', 'error');
      return;
    }
    document.getElementById('credsTitle').textContent = contractName;
    document.getElementById('credsLogin').textContent = data.login || '—';
    document.getElementById('credsPassword').textContent = data.password || '—';
    document.getElementById('credsModal').classList.remove('hidden');
  };

  document.getElementById('closeCredsModal').addEventListener('click', () => {
    document.getElementById('credsModal').classList.add('hidden');
  });

  window.copyText = function(elId) {
    const text = document.getElementById(elId).textContent;
    navigator.clipboard.writeText(text).then(() => showToast('Скопійовано!', 'success'));
  };

  // ─── SEARCH ───
  const serviceSearchEl = document.getElementById('serviceSearch');
  const searchClearEl = document.getElementById('searchClear');
  serviceSearchEl.addEventListener('input', () => {
    const q = serviceSearchEl.value;
    searchClearEl.classList.toggle('hidden', !q);
    renderAll(q);
  });
  searchClearEl.addEventListener('click', () => {
    serviceSearchEl.value = '';
    searchClearEl.classList.add('hidden');
    renderAll('');
    serviceSearchEl.focus();
  });

  loadMe();
}

window.copyText = function(elId) {
  const text = document.getElementById(elId).textContent;
  navigator.clipboard.writeText(text).then(() => alert('Скопійовано!'));
};