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

// ─── NAVBAR / MOBILE MENU ───
function setupNavbar() {
  const navbar = document.querySelector('.navbar');
  if (!navbar) return;

  document.body.classList.add('has-navbar');

  const navRight = navbar.querySelector('.navbar-right');
  if (!navRight) return;

  if (!navbar.querySelector('.mobile-nav-toggle')) {
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'mobile-nav-toggle';
    toggle.setAttribute('aria-label', 'Відкрити меню');
    toggle.innerHTML = '<span class="material-icons-round">menu</span>';
    navbar.appendChild(toggle);
  }

  if (!document.querySelector('.mobile-nav-backdrop')) {
    const backdrop = document.createElement('div');
    backdrop.className = 'mobile-nav-backdrop hidden';
    document.body.appendChild(backdrop);
  }

  const toggleBtn = navbar.querySelector('.mobile-nav-toggle');
  const backdrop = document.querySelector('.mobile-nav-backdrop');

  const closeMenu = () => {
    navRight.classList.remove('mobile-open');
    if (backdrop) backdrop.classList.add('hidden');
    toggleBtn?.setAttribute('aria-label', 'Відкрити меню');
    const icon = toggleBtn?.querySelector('.material-icons-round');
    if (icon) icon.textContent = 'menu';
    syncBodyLockState();
  };

  const openMenu = () => {
    navRight.classList.add('mobile-open');
    if (backdrop) backdrop.classList.remove('hidden');
    toggleBtn?.setAttribute('aria-label', 'Закрити меню');
    const icon = toggleBtn?.querySelector('.material-icons-round');
    if (icon) icon.textContent = 'close';
    syncBodyLockState();
  };

  toggleBtn?.addEventListener('click', () => {
    if (navRight.classList.contains('mobile-open')) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  backdrop?.addEventListener('click', closeMenu);

  navRight.querySelectorAll('a.nav-btn').forEach((link) => {
    link.addEventListener('click', closeMenu);
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 900) {
      closeMenu();
    }
  });
}

// ─── BODY SCROLL LOCK ───
function syncBodyLockState() {
  const modalOpen = !!document.querySelector('.modal:not(.hidden)');
  const menuOpen = !!document.querySelector('.navbar-right.mobile-open');
  document.body.classList.toggle('lock-scroll', modalOpen || menuOpen);
}

function setupModalObserver() {
  const observer = new MutationObserver(syncBodyLockState);
  observer.observe(document.body, {
    attributes: true,
    childList: true,
    subtree: true,
    attributeFilter: ['class'],
  });
  syncBodyLockState();
}

document.addEventListener('DOMContentLoaded', () => {
  setupNavbar();
  setupModalObserver();
});