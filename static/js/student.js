// Student Dashboard JavaScript
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
        setTimeout(() => { t.style.opacity='0'; setTimeout(()=>t.remove(),300); }, 4500);
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
        overview:  ['My Attendance',        'Overall attendance summary and recent records'],
        subjects:  ['Subject-wise Breakdown','Attendance percentage per subject'],
        history:   ['Attendance History',   'Complete attendance record timeline'],
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
            if (tab === 'subjects' && !subjectsLoaded) loadSubjects();
            if (tab === 'history'  && !historyLoaded)  loadHistory();
        });
    });

    let subjectsLoaded = false, historyLoaded = false;

    // ── Overview ──────────────────────────────────────────────────────────────
    async function loadOverview() {
        try {
            const d = await api('/api/student/dashboard');
            if (!d.success) {
                if (d.message && d.message.includes('profile not found')) {
                    // No student profile linked
                    document.getElementById('page-subtitle').textContent =
                        'Your account is not linked to a student record. Contact your administrator.';
                    return;
                }
                showToast('Error', d.message || 'Failed to load dashboard', 'danger');
                return;
            }

            document.getElementById('student-name').textContent = data.student_name || '—';
            document.getElementById('student-roll').textContent = data.roll_no || '—';
            const courseEl = document.getElementById('student-course');
            if (courseEl) courseEl.textContent = data.course_name || '—';
            const classEl = document.getElementById('student-class');
            if (classEl) classEl.textContent = data.class_name || '—';
            document.getElementById('page-subtitle').textContent = `Roll No: ${data.roll_no || '—'} ${data.course_name ? '· ' + data.course_name : ''} ${data.class_name ? '· ' + data.class_name : ''}`;

            const pct = data.overall_percentage || 0;

            // Ring
            const ring = document.getElementById('att-ring-fill');
            const circumference = 2 * Math.PI * 64; // 402.12
            const offset = circumference - (pct / 100) * circumference;
            ring.style.strokeDashoffset = offset;

            // Color ring by health
            if (pct >= 75) {
                ring.style.stroke = 'var(--status-present)';
            } else if (pct >= 60) {
                ring.style.stroke = 'var(--status-late)';
            } else {
                ring.style.stroke = 'var(--status-absent)';
            }

            document.getElementById('ring-pct').textContent = pct.toFixed(1) + '%';
            document.getElementById('stat-present').textContent = data.present;
            document.getElementById('stat-absent').textContent  = data.absent;
            document.getElementById('stat-late').textContent    = data.late;
            document.getElementById('stat-total').textContent   = data.total_classes;

            // Low att alert
            if (pct < 75) {
                document.getElementById('low-att-alert').classList.remove('hidden');
                document.getElementById('low-att-msg').textContent =
                    `Your attendance is ${pct.toFixed(1)}%. You need to reach 75% to avoid academic penalties.`;
            }

            // Recent records
            const tbody = document.getElementById('recent-tbody');
            const recent = data.recent_records || [];
            if (recent.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted);text-align:center;padding:24px;">No attendance records yet.</td></tr>';
            } else {
                const statusMap = {
                    present: { color:'var(--status-present)', label:'Present' },
                    absent:  { color:'var(--status-absent)',  label:'Absent'  },
                    late:    { color:'var(--status-late)',    label:'Late'    },
                };
                tbody.innerHTML = recent.map(r => {
                    const s = statusMap[r.status] || { color:'var(--text-muted)', label: r.status };
                    return `<tr>
                        <td style="color:var(--text-secondary);">${esc(r.date)}</td>
                        <td style="font-weight:600;color:var(--text-primary);">${esc(r.subject||'—')}</td>
                        <td style="color:var(--text-muted);">${esc(r.time)}</td>
                        <td><span style="color:${s.color};font-weight:600;">${s.label}</span></td>
                    </tr>`;
                }).join('');
            }

        } catch(e) {
            console.error(e);
            showToast('Error', 'Could not load attendance data', 'danger');
        }

        // Warning check
        try {
            const w = await api('/api/student/attendance/warning');
            if (w.success && w.data.classes_needed > 0) {
                const alert = document.getElementById('low-att-alert');
                const msg = document.getElementById('low-att-msg');
                alert.classList.remove('hidden');
                msg.textContent = w.data.message;
            }
        } catch(e) { /* Optional warning */ }

        // Load notifications
        loadNotifications();
    }

    // ── Notifications ────────────────────────────────────────────────────────
    async function loadNotifications() {
        try {
            const res = await api('/api/student/notifications');
            if (res.success && res.notifications.length) {
                const badge = document.getElementById('notif-badge');
                badge.textContent = res.notifications.length;
                badge.style.display = 'inline-block';

                const list = document.getElementById('notif-list');
                list.innerHTML = res.notifications.map(n => `
                    <div style="padding:10px 12px;border-radius:8px;background:var(--surface);border:1px solid var(--border-subtle);">
                        <div style="font-size:12px;font-weight:600;color:${n.type==='warning'?'var(--status-absent)':n.type==='danger'?'var(--status-late)':'var(--accent)'}">${esc(n.title)}</div>
                        <div style="font-size:12px;color:var(--text-secondary);margin-top:2px;">${esc(n.message)}</div>
                        <div style="font-size:10px;color:var(--text-muted);margin-top:4px;">${esc(n.date)}</div>
                    </div>
                `).join('');
            }
        } catch(e) { console.error(e); }
    }

    const btnNotif = document.getElementById('btn-notifications');
    const panelNotif = document.getElementById('notif-panel');
    const btnCloseNotif = document.getElementById('btn-close-notif');
    if (btnNotif && panelNotif) {
        btnNotif.addEventListener('click', () => {
            panelNotif.style.display = panelNotif.style.display === 'none' ? 'block' : 'none';
        });
        btnCloseNotif.addEventListener('click', () => {
            panelNotif.style.display = 'none';
        });
    }


    // ── Subjects ──────────────────────────────────────────────────────────────
    async function loadSubjects() {
        subjectsLoaded = true;
        const container = document.getElementById('subjects-list');
        container.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:32px;">Loading subjects...</div>';
        try {
            const d = await api('/api/student/reports/semester-summary');
            if (!d.success) {
                container.innerHTML = `<div style="color:var(--text-muted);text-align:center;padding:32px;">${esc(d.message||'No subject data available.')}</div>`;
                return;
            }
            const subjects = d.data.subject_wise_summary || [];
            if (subjects.length === 0) {
                container.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:32px;">No attendance data by subject yet.</div>';
                return;
            }
            container.innerHTML = subjects.map(sub => {
                const pct = sub.percentage;
                const cls = pct >= 75 ? 'good' : pct >= 60 ? 'warn' : 'bad';
                return `<div class="subject-row">
                    <div class="subject-info" style="flex:1;">
                        <div class="subject-name">${esc(sub.subject_name)}</div>
                        <div class="subject-code">${esc(sub.subject_code)}</div>
                    </div>
                    <div style="font-size:12px;color:var(--text-muted);min-width:120px;text-align:right;margin-right:12px;">
                        ${sub.present}P / ${sub.absent}A / ${sub.late}L — ${sub.total} classes
                    </div>
                    <div class="subject-bar-wrap">
                        <div class="subject-bar">
                            <div class="subject-bar-fill ${cls}" style="width:${Math.min(100,pct)}%"></div>
                        </div>
                    </div>
                    <span class="subject-pct ${cls}">${pct}%</span>
                </div>`;
            }).join('');
        } catch(e) {
            container.innerHTML = `<div style="color:var(--text-muted);text-align:center;padding:32px;">Error loading subject data.</div>`;
        }
    }

    // ── History ───────────────────────────────────────────────────────────────
    async function loadHistory() {
        historyLoaded = true;
        const tbody = document.getElementById('history-tbody');
        tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:24px;">Loading history...</td></tr>';
        try {
            const d = await api('/api/student/reports/attendance?format=json');
            if (!d.success || !d.data.report.length) {
                tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:24px;">No attendance history found.</td></tr>';
                return;
            }
            const statusColor = {
                Present: 'var(--status-present)',
                Absent:  'var(--status-absent)',
                Late:    'var(--status-late)',
            };
            tbody.innerHTML = d.data.report.map(r => `<tr>
                <td style="color:var(--text-secondary);">${esc(r.Date)}</td>
                <td style="font-weight:600;color:var(--text-primary);">${esc(r.Class||'—')}</td>
                <td style="color:var(--text-secondary);">${esc(r.Subject||'—')}</td>
                <td style="color:var(--text-muted);">${esc(r.Time||'—')}</td>
                <td><span style="font-weight:600;color:${statusColor[r.Status]||'var(--text-muted)'};">${esc(r.Status)}</span></td>
                <td style="color:var(--text-muted);font-size:12px;">${esc(r.Notes||'—')}</td>
            </tr>`).join('');
        } catch(e) {
            tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:24px;">Error loading history.</td></tr>';
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

    // Fix ring SVG position — it sits absolutely
    const ringWrap = document.querySelector('.ring-wrap');
    if (ringWrap) ringWrap.style.position = 'relative';

    // Boot
    loadOverview();
});
