// ─── THEME ───
const savedTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', savedTheme);

function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  const btn = document.getElementById('themeToggle');
  if (btn) btn.querySelector('.material-icons-round').textContent = next === 'dark' ? 'light_mode' : 'dark_mode';
}

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('themeToggle');
  if (btn) {
    const cur = document.documentElement.getAttribute('data-theme');
    btn.querySelector('.material-icons-round').textContent = cur === 'dark' ? 'light_mode' : 'dark_mode';
    btn.addEventListener('click', toggleTheme);
  }
});

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