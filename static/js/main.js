/* SmartOLT Cloud — Main JavaScript */

document.addEventListener('DOMContentLoaded', function () {

  // =================== SIDEBAR TOGGLE ===================
  const sidebar = document.getElementById('sidebar');
  const mainContent = document.getElementById('mainContent');
  const toggleBtns = [document.getElementById('sidebarToggle'), document.getElementById('sidebarToggleBtn')];

  function toggleSidebar() {
    if (!sidebar) return;
    sidebar.classList.toggle('collapsed');
    if (mainContent) mainContent.classList.toggle('expanded');
    localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
  }

  toggleBtns.forEach(btn => { if (btn) btn.addEventListener('click', toggleSidebar); });

  // Restore sidebar state
  if (localStorage.getItem('sidebarCollapsed') === 'true' && sidebar) {
    sidebar.classList.add('collapsed');
    if (mainContent) mainContent.classList.add('expanded');
  }

  // =================== NAV GROUP COLLAPSE ===================
  document.querySelectorAll('.nav-group-header').forEach(header => {
    header.addEventListener('click', function () {
      const groupId = this.getAttribute('data-group');
      const groupItems = document.getElementById(`group-${groupId}`);
      if (!groupItems) return;
      const arrow = this.querySelector('.nav-arrow');
      const isOpen = groupItems.classList.contains('show');
      groupItems.classList.toggle('show', !isOpen);
      if (arrow) arrow.style.transform = isOpen ? '' : 'rotate(180deg)';
    });
  });

  // Restore open state for active groups
  document.querySelectorAll('.nav-group-header.active').forEach(header => {
    const arrow = header.querySelector('.nav-arrow');
    if (arrow) arrow.style.transform = 'rotate(180deg)';
  });

  // =================== LIVE CLOCK ===================
  const timeEl = document.getElementById('liveTime');
  function updateTime() {
    if (!timeEl) return;
    const now = new Date();
    timeEl.textContent = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  updateTime();
  setInterval(updateTime, 1000);

  // =================== AUTO-DISMISS ALERTS ===================
  setTimeout(() => {
    document.querySelectorAll('.messages-container .alert').forEach(alert => {
      if (alert && bootstrap) {
        const bsAlert = new bootstrap.Alert(alert);
        bsAlert.close();
      }
    });
  }, 5000);

  // =================== CRITICAL EVENTS BADGE ===================
  function refreshCriticalCount() {
    fetch('/api/stats/')
      .then(r => r.json())
      .then(data => {
        const badge = document.querySelector('.top-navbar .position-absolute.badge');
        if (badge) {
          badge.textContent = data.critical_alerts || '';
          badge.style.display = data.critical_alerts > 0 ? '' : 'none';
        }
      })
      .catch(() => {});
  }
  setInterval(refreshCriticalCount, 60000);

  // =================== CSRF HELPER ===================
  window.getCsrfToken = function () {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
      document.cookie.split('; ').find(r => r.startsWith('csrftoken='))?.split('=')[1] || '';
  };

  // =================== CONFIRM DANGEROUS ACTIONS ===================
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', function (e) {
      if (!confirm(this.dataset.confirm)) e.preventDefault();
    });
  });

  // =================== TOOLTIP INIT ===================
  const tooltipEls = document.querySelectorAll('[title]');
  tooltipEls.forEach(el => {
    if (typeof bootstrap !== 'undefined') {
      new bootstrap.Tooltip(el, { placement: 'top', trigger: 'hover' });
    }
  });

  // =================== CHART DEFAULTS ===================
  if (typeof Chart !== 'undefined') {
    Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.animation.duration = 600;
  }
});
