// ─── THEME (always dark) ───
document.documentElement.setAttribute('data-theme', 'dark');

// ─── TOAST ───
function createToastContainer() {
  let el = document.getElementById('toast-container');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast-container';
    document.body.appendChild(el);
  }
  return el;
}

function showToast(message, type = 'info', duration = 3000) {
  const container = createToastContainer();
  const toast = document.createElement('div');
  const icon = type === 'success' ? 'check_circle' : type === 'error' ? 'error' : 'info';
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span class="material-icons-round" style="font-size:18px">${icon}</span>${message}`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toastOut 0.3s forwards';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ─── LOADER ───
function showLoader() {
  let el = document.getElementById('loaderOverlay');
  if (!el) {
    el = document.createElement('div');
    el.id = 'loaderOverlay';
    el.className = 'loader-overlay';
    el.innerHTML = '<div class="loader"></div>';
    document.body.appendChild(el);
  }
  el.classList.remove('hidden');
}

function hideLoader() {
  const el = document.getElementById('loaderOverlay');
  if (el) el.classList.add('hidden');
}