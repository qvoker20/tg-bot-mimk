async function loadProfile() {
  const r = await fetch('/api/me');
  const data = await r.json();
  if (!data.ok) {
    window.location.href = '/login';
    return;
  }
  const u = data.user;
  document.getElementById('profileName').value = u.name || '';
  document.getElementById('profilePhone').textContent = u.phone_number || '—';
  document.getElementById('profileUsername').textContent = u.username ? '@' + u.username : '—';
  document.getElementById('profileRole').textContent = u.role === 'admin' ? 'Адмін' : 'Користувач';

  // Аватар — перша літера імені
  const letter = (u.name || u.username || '?')[0].toUpperCase();
  document.getElementById('avatarLetter').textContent = letter;
}

document.getElementById('saveNameBtn').addEventListener('click', async () => {
  const name = document.getElementById('profileName').value.trim();
  if (!name) { showToast("Ім'я не може бути порожнім", 'error'); return; }
  showLoader();
  const r = await fetch('/api/profile', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name })
  });
  const data = await r.json();
  hideLoader();
  if (data.ok) {
    showToast('Ім\'я збережено!', 'success');
    document.getElementById('avatarLetter').textContent = name[0].toUpperCase();
  } else {
    showToast(data.error || 'Помилка', 'error');
  }
});

document.getElementById('logoutBtn').addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' });
  window.location.href = '/login';
});

loadProfile();