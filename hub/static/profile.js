let avatarCropper = null;
let croppedAvatarBlob = null;

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

  const avatarImg = document.getElementById('profileAvatarImg');
  const avatarLetter = document.getElementById('avatarLetter');
  if (u.avatar_path) {
    avatarImg.src = '/uploads/' + u.avatar_path;
    avatarImg.classList.remove('hidden');
    avatarLetter.classList.add('hidden');
  } else {
    avatarImg.classList.add('hidden');
    avatarLetter.classList.remove('hidden');
  }
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

document.getElementById('profileAvatar').addEventListener('change', async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;

  const imageEl = document.getElementById('avatarCropImage');
  const modal = document.getElementById('avatarCropModal');
  imageEl.src = URL.createObjectURL(file);
  modal.classList.remove('hidden');

  await new Promise(resolve => {
    imageEl.onload = resolve;
  });

  if (avatarCropper) avatarCropper.destroy();
  avatarCropper = new Cropper(imageEl, {
    aspectRatio: 1,
    viewMode: 1,
    dragMode: 'move',
    autoCropArea: 1,
    background: false,
    responsive: true,
  });
});

document.getElementById('closeAvatarCropBtn').addEventListener('click', () => {
  const modal = document.getElementById('avatarCropModal');
  modal.classList.add('hidden');
  if (avatarCropper) {
    avatarCropper.destroy();
    avatarCropper = null;
  }
  document.getElementById('profileAvatar').value = '';
});

document.getElementById('saveAvatarCropBtn').addEventListener('click', async () => {
  if (!avatarCropper) return;

  const canvas = avatarCropper.getCroppedCanvas({
    width: 512,
    height: 512,
    imageSmoothingQuality: 'high'
  });

  canvas.toBlob(async (blob) => {
    if (!blob) {
      showToast('Не вдалося підготувати фото', 'error');
      return;
    }
    croppedAvatarBlob = blob;
    document.getElementById('avatarCropModal').classList.add('hidden');
    avatarCropper.destroy();
    avatarCropper = null;
  }, 'image/jpeg', 0.92);
});

document.getElementById('saveAvatarBtn').addEventListener('click', async () => {
  if (!croppedAvatarBlob) {
    showToast('Оберіть фото і застосуйте обрізку', 'error');
    return;
  }

  const input = document.getElementById('profileAvatar');
  const fd = new FormData();
  fd.append('avatar', croppedAvatarBlob, 'avatar.jpg');

  showLoader();
  const r = await fetch('/api/profile/avatar', {
    method: 'PUT',
    body: fd
  });
  const data = await r.json();
  hideLoader();

  if (!data.ok) {
    showToast(data.error || 'Помилка завантаження', 'error');
    return;
  }

  const avatarImg = document.getElementById('profileAvatarImg');
  document.getElementById('avatarLetter').classList.add('hidden');
  avatarImg.src = '/uploads/' + data.avatar_path;
  avatarImg.classList.remove('hidden');
  input.value = '';
  croppedAvatarBlob = null;
  showToast('Фото оновлено', 'success');
});

document.getElementById('logoutBtn').addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' });
  window.location.href = '/login';
});

loadProfile();