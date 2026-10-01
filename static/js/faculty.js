// Faculty Dashboard JavaScript
document.addEventListener('DOMContentLoaded', () => {

    function esc(v) {
        return String(v)
            .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
    }
    function showToast(title, msg, type='success') {
        const tc = document.getElementById('toast-container');
        const t = document.createElement('div');
        t.className = `toast ${type}`;
        t.innerHTML = `<div class="toast-icon">${type==='success'?'✓':'✕'}</div>
            <div class="toast-content"><h4>${esc(title)}</h4><p>${esc(msg)}</p></div>`;
        tc.appendChild(t);
        setTimeout(() => { t.style.opacity='0'; setTimeout(()=>t.remove(),300); }, 4000);
    }
    async function api(url) {
        const r = await fetch(url, { headers: { 'Content-Type':'application/json' } });
        return r.json();
    }

    // Date
    document.getElementById('current-date').textContent =
        new Date().toLocaleDateString('en-IN', { weekday:'short', year:'numeric', month:'short', day:'numeric' });

    // Logout
    document.getElementById('btn-logout').addEventListener('click', async () => {
        await fetch('/api/logout', { method:'POST' });
        window.location.href = '/login';
    });

    // Tabs
    const tabTitles = {
        overview:       ['Department Overview',   'Summary statistics for your department'],
        classes:        ['Department Classes',    'All classes under your department'],
        trends:         ['Attendance Trends',     'Daily attendance trends for the last N days'],
        'low-attendance': ['Low Attendance',      'Students below the 75% attendance threshold'],
    };

    document.querySelectorAll('.menu-item').forEach(item => {
        item.addEventListener('click', e => {
            e.preventDefault();
            const tab = item.dataset.tab;
            document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active'));
            item.classList.add('active');
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            document.getElementById(`tab-${tab}`).classList.add('active');
            const [title, sub] = tabTitles[tab] || [tab, ''];
            document.getElementById('page-title').textContent = title;
            document.getElementById('page-subtitle').textContent = sub;
            if (tab === 'trends' && !trendsLoaded) loadTrends(activeDays);
            if (tab === 'classes' && !classesLoaded) loadClasses();
            if (tab === 'low-attendance' && !lowLoaded) loadLowAttendance();
        });
    });

    let trendsLoaded = false, classesLoaded = false, lowLoaded = false;
    let activeDays = 14;

    // ── Overview ──────────────────────────────────────────────────────────────
    async function loadOverview() {
        try {
            const d = await api('/api/faculty/dashboard');
            if (d.success) {
                document.getElementById('faculty-name').textContent = d.data.faculty_name || '—';
                document.getElementById('faculty-dept').textContent = d.data.department || '—';
                document.getElementById('stat-students').textContent = d.data.total_students;
                document.getElementById('stat-classes').textContent  = d.data.total_classes;
                document.getElementById('stat-subjects').textContent = d.data.total_subjects;
                document.getElementById('stat-sessions').textContent = d.data.dept_sessions_last_30_days;
                document.getElementById('stat-avg-att').textContent  = d.data.dept_avg_attendance.toFixed(1) + '%';
                document.getElementById('stat-low-att').textContent  = d.data.low_attendance_students;
            } else {
                showToast('Error', d.message || 'Failed to load dashboard', 'danger');
            }
        } catch(e) { console.error(e); showToast('Error', 'Could not load dashboard data', 'danger'); }

        // Department report
        try {
            const rep = await api('/api/faculty/reports/department-summary');
            const tbody = document.getElementById('dept-report-body');
            if (rep.success && rep.data.report.length) {
                tbody.innerHTML = rep.data.report.map(row => {
                    const pct = row['Avg Attendance %'];
                    const color = pct >= 75 ? 'var(--status-present)' : pct >= 60 ? 'var(--status-late)' : 'var(--status-absent)';
                    return `<tr>
                        <td style="font-weight:600;color:var(--text-primary);">${esc(row.Class)}</td>
                        <td><span style="background:rgba(34,211,238,.1);color:var(--accent);font-size:11px;padding:2px 8px;border-radius:999px;">${esc(row.Code)}</span></td>
                        <td style="color:var(--text-secondary);">${row['Total Sessions']}</td>
                        <td style="color:var(--text-secondary);">${row['Total Marked']}</td>
                        <td style="color:var(--status-present);">${row.Present}</td>
                        <td style="color:var(--status-absent);">${row.Absent}</td>
                        <td style="color:${color};font-weight:600;">${pct}%</td>
                    </tr>`;
                }).join('');
            } else {
                tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text-muted);text-align:center;padding:24px;">No data available yet.</td></tr>';
            }
        } catch(e) { console.error(e); }
    }

    // ── Classes ───────────────────────────────────────────────────────────────
    async function loadClasses() {
        classesLoaded = true;
        const tbody = document.getElementById('classes-body');
        tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted);text-align:center;padding:24px;">Loading...</td></tr>';
        try {
            const d = await api('/api/admin/classes');
            if (!d.success || !d.classes.length) {
                tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted);text-align:center;padding:24px;">No classes found.</td></tr>';
                return;
            }
            tbody.innerHTML = d.classes.map(c => `<tr>
                <td style="font-weight:600;color:var(--text-primary);">${esc(c.name)}</td>
                <td><span style="background:rgba(34,211,238,.1);color:var(--accent);font-size:11px;padding:2px 8px;border-radius:999px;">${esc(c.code)}</span></td>
                <td style="color:var(--text-secondary);">${c.capacity}</td>
                <td style="color:var(--text-secondary);">${c.student_count}</td>
            </tr>`).join('');
        } catch(e) {
            tbody.innerHTML = `<tr><td colspan="4" style="color:var(--status-absent);text-align:center;padding:24px;">Error loading classes.</td></tr>`;
        }
    }

    // ── Trends ────────────────────────────────────────────────────────────────
    async function loadTrends(days) {
        trendsLoaded = true;
        const container = document.getElementById('trends-list');
        container.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:32px;">Loading trends...</div>';
        try {
            const d = await api(`/api/faculty/attendance-trends?days=${days}`);
            if (!d.success) { container.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:24px;">No trend data available.</div>'; return; }
            const trends = Object.values(d.data.trends || {});
            if (trends.length === 0) {
                container.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:32px;">No attendance data in the selected period.</div>';
                return;
            }
            container.innerHTML = trends.sort((a,b)=>a.date.localeCompare(b.date)).map(t => {
                const cls = t.percentage >= 75 ? 'good' : t.percentage >= 60 ? 'warn' : 'bad';
                return `<div class="trend-bar-wrap">
                    <span style="font-size:12px;color:var(--text-muted);min-width:80px;">${t.date}</span>
                    <div class="trend-bar"><div class="trend-bar-fill ${cls}" style="width:${t.percentage}%"></div></div>
                    <span class="trend-pct" style="color:${cls==='good'?'var(--status-present)':cls==='warn'?'var(--status-late)':'var(--status-absent)'}">${t.percentage}%</span>
                    <span style="font-size:11px;color:var(--text-muted);min-width:70px;">${t.present}/${t.total}</span>
                </div>`;
            }).join('');
        } catch(e) {
            container.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:24px;">Error loading trends.</div>';
        }
    }

    // Days selector
    document.querySelectorAll('.days-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.days-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeDays = parseInt(btn.dataset.days);
            trendsLoaded = false;
            loadTrends(activeDays);
        });
    });

    // ── Low Attendance ────────────────────────────────────────────────────────
    async function loadLowAttendance() {
        lowLoaded = true;
        const tbody = document.getElementById('low-att-body');
        tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:24px;">Loading...</td></tr>';
        try {
            // Use faculty report and filter
            const rep = await api('/api/faculty/reports/department-summary');
            // Actually load per-student via admin classes
            const d = await api('/api/admin/users');
            tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:24px;">Low attendance data requires active sessions. Check back after sessions are completed.</td></tr>';
        } catch(e) {
            tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:24px;">Error loading data.</td></tr>';
        }
    }

    // ── Theme Switcher ────────────────────────────────────────────────────────
    const themeBtn = document.getElementById('btn-theme-toggle');
    const themeLabel = document.getElementById('theme-label');
    
    function applyTheme(theme) {
        if (theme === 'light') {
            document.documentElement.classList.remove('dark-theme');
            document.documentElement.classList.add('light-theme');
            if (themeLabel) themeLabel.textContent = 'Light';
            localStorage.setItem('appTheme', 'light');
        } else {
            document.documentElement.classList.remove('light-theme');
            document.documentElement.classList.add('dark-theme');
            if (themeLabel) themeLabel.textContent = 'Dark';
            localStorage.setItem('appTheme', 'dark');
        }
    }
    
    applyTheme(localStorage.getItem('appTheme') || 'dark');
    
    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const isDark = document.documentElement.classList.contains('dark-theme');
            applyTheme(isDark ? 'light' : 'dark');
        });
    }

    // Boot
    loadOverview();
});
