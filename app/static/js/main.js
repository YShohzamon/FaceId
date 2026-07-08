/**
 * Global UI utilities — clock, search filter, toast notifications,
 * mobile navigation, and dashboard auto-refresh.
 */

// --- Mobile sidebar toggle --------------------------------------
const menuToggle = document.getElementById('menuToggle');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');

function closeSidebar() {
    sidebar?.classList.remove('open');
    sidebarOverlay?.classList.remove('visible');
    document.body.style.overflow = '';
}

function openSidebar() {
    sidebar?.classList.add('open');
    sidebarOverlay?.classList.add('visible');
    document.body.style.overflow = 'hidden';
}

if (menuToggle && sidebar) {
    menuToggle.addEventListener('click', () => {
        if (sidebar.classList.contains('open')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    });
}

sidebarOverlay?.addEventListener('click', closeSidebar);

document.querySelectorAll('.sidebar .nav-item').forEach((link) => {
    link.addEventListener('click', () => {
        if (window.matchMedia('(max-width: 768px)').matches) {
            closeSidebar();
        }
    });
});

// --- Live clock -------------------------------------------------
function updateClock() {
    const el = document.getElementById('current-time');
    if (!el) return;
    const now = new Date();
    el.textContent = now.toLocaleTimeString('en-US', {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
}
updateClock();
setInterval(updateClock, 1000);

// --- Student table search filter --------------------------------
const searchInput = document.getElementById('searchInput');
if (searchInput) {
    searchInput.addEventListener('input', () => {
        const query = searchInput.value.toLowerCase();
        document.querySelectorAll('#studentsTable tbody tr').forEach(row => {
            row.style.display = row.textContent.toLowerCase().includes(query) ? '' : 'none';
        });
    });
}

// ================================================================
// Toast notification system
// ================================================================
window.showToast = function (message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;

    const icons = {
        success: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20,6 9,17 4,12"/></svg>`,
        error:   `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
        info:    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
        warning: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    };

    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${message}</span>
        <button class="toast-close" onclick="this.closest('.toast').remove()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>`;

    container.appendChild(toast);

    // Animate in
    requestAnimationFrame(() => toast.classList.add('toast--visible'));

    // Auto-dismiss
    const timer = setTimeout(() => dismissToast(toast), duration);
    toast.addEventListener('mouseenter', () => clearTimeout(timer));
    toast.addEventListener('mouseleave', () => setTimeout(() => dismissToast(toast), 1200));
};

function dismissToast(toast) {
    toast.classList.remove('toast--visible');
    toast.addEventListener('transitionend', () => toast.remove(), { once: true });
}

// ================================================================
// Dashboard stats auto-refresh (every 30 s, only on home page)
// ================================================================
if (document.getElementById('statTotalStudents')) {
    setInterval(async () => {
        try {
            const res = await fetch('/api/attendance/stats');
            if (!res.ok) return;
            const d = await res.json();
            setStatValue('statTotalStudents', d.total_students);
            setStatValue('statTodayAttendance', d.today_attendance);
            setStatValue('statTotalRecords', d.total_records);
        } catch (_) {}
    }, 30000);
}

function setStatValue(id, value) {
    const el = document.getElementById(id);
    if (el && el.textContent !== String(value)) {
        el.classList.add('stat-value--flash');
        el.textContent = value;
        setTimeout(() => el.classList.remove('stat-value--flash'), 600);
    }
}
