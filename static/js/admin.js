// Admin Dashboard JavaScript
document.addEventListener('DOMContentLoaded', () => {

    // ── Helpers ──────────────────────────────────────────────────────────────
    function esc(v) {
        return String(v ?? '')
            .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
    }
    function fmtDate(iso) {
        if (!iso) return '—';
        return new Date(iso).toLocaleString('en-IN', { dateStyle:'medium', timeStyle:'short' });
    }
    function showToast(title, msg, type='success') {
        const tc = document.getElementById('toast-container');
        if (!tc) return;
        const t = document.createElement('div');
        t.className = `toast ${type}`;
        t.innerHTML = `<div class="toast-icon">${type==='success'?'✓':'✕'}</div>
            <div class="toast-content"><h4>${esc(title)}</h4><p>${esc(msg)}</p></div>`;
        tc.appendChild(t);
        setTimeout(() => { t.style.opacity='0'; setTimeout(()=>t.remove(),300); }, 4000);
    }
    async function api(url, method='GET', body=null) {
        const opts = { method, headers: { 'Content-Type':'application/json' } };
        if (body) opts.body = JSON.stringify(body);
        const r = await fetch(url, opts);
        return r.json();
    }

    // ── Date ──────────────────────────────────────────────────────────────────
    const dateEl = document.getElementById('current-date');
    if (dateEl) {
        dateEl.textContent = new Date().toLocaleDateString('en-IN', { weekday:'short', year:'numeric', month:'short', day:'numeric' });
    }

    // ── Logout ────────────────────────────────────────────────────────────────
    document.getElementById('btn-logout')?.addEventListener('click', async () => {
        try {
            await api('/api/logout', 'POST');
        } catch (e) {
            console.warn('Logout API error:', e);
        }
        window.location.href = '/login?tab=teacher';
    });

    // ── Current User ──────────────────────────────────────────────────────────
    api('/api/me').then(d => {
        if (d && d.name) {
            const adminNameEl = document.getElementById('admin-name');
            if (adminNameEl) adminNameEl.textContent = d.name;
        }
    });

    // ── Clean Database Action ────────────────────────────────────────────────
    document.getElementById('btn-clean-db')?.addEventListener('click', async () => {
        const confirmed = confirm(
            "RESET DATABASE TO CLEAN SLATE?\n\n" +
            "This will remove all courses, classes, registered students, face data, and attendance records.\n" +
            "Your Admin account will remain intact.\n\n" +
            "Proceed with clean reset?"
        );
        if (!confirmed) return;

        try {
            const res = await api('/api/admin/clean-database', 'POST');
            if (res.success) {
                showToast("Database Reset", res.message);
                loadOverview();
                const activeTab = document.querySelector('.menu-item.active')?.dataset.tab || 'overview';
                loaders[activeTab]?.();
            } else {
                showToast("Reset Failed", res.message || "Failed to clean database", "danger");
            }
        } catch (err) {
            showToast("Error", err.message, "danger");
        }
    });

    // ── Tabs ──────────────────────────────────────────────────────────────────
    const tabTitles = {
        overview:    ['System Overview',      'Full system statistics and central catalog'],
        courses:     ['Course Management',   'Create and manage centralized courses and degrees'],
        classes:     ['Classes',             'Manage classes and years connected to courses'],
        students:    ['Student Directory',   'Central student records and face enrollment status'],
        departments: ['Departments',         'Manage academic departments'],
        users:       ['User Management',     'Create, edit, and deactivate user accounts'],
        attendance:  ['Attendance Records',  'View and export all centralized attendance data'],
        audit:       ['Audit Logs',          'Track all system activity and administrative changes'],
    };

    document.querySelectorAll('.menu-item').forEach(item => {
        item.addEventListener('click', e => {
            e.preventDefault();
            const tab = item.dataset.tab;
            document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active'));
            item.classList.add('active');
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            const panel = document.getElementById(`tab-${tab}`);
            if (panel) panel.classList.add('active');
            const [title, sub] = tabTitles[tab] || [tab, ''];
            const pt = document.getElementById('page-title');
            const ps = document.getElementById('page-subtitle');
            if (pt) pt.textContent = title;
            if (ps) ps.textContent = sub;
            loaders[tab]?.();
        });
    });

    // ── Loaders ───────────────────────────────────────────────────────────────
    const loaders = {
        overview:    loadOverview,
        courses:     loadCourses,
        classes:     loadClasses,
        students:    loadStudents,
        departments: loadDepts,
        users:       loadUsers,
        attendance:  loadAttendance,
        audit:       loadAudit,
    };

    // ── Overview ──────────────────────────────────────────────────────────────
    async function loadOverview() {
        try {
            const d = await api('/api/admin/dashboard');
            if (d.success) {
                const setText = (id, val) => {
                    const el = document.getElementById(id);
                    if (el) el.textContent = (val !== undefined && val !== null) ? val : '0';
                };
                setText('stat-courses',  d.structure.courses || 0);
                setText('stat-classes',  d.structure.classes || 0);
                setText('stat-students', d.users.students || 0);
                setText('stat-teachers', d.users.teachers || 0);
                setText('stat-faculty',  d.users.faculty || 0);
                setText('stat-depts',    d.structure.departments || 0);
                setText('stat-sessions', d.sessions.total || 0);
                setText('stat-users',    d.users.total || 0);
            }
        } catch(e) { console.error("Error fetching overview stats:", e); }

        // Recent students
        try {
            const s = await api('/api/students');
            const tbody = document.getElementById('recent-students-body');
            if (tbody) {
                const recent = (s.students || []).slice(0, 8);
                if (recent.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-muted);text-align:center;padding:20px;">No students registered yet</td></tr>';
                } else {
                    tbody.innerHTML = recent.map(st => `<tr>
                        <td style="font-weight:600;color:var(--text-primary);">${esc(st.name)}</td>
                        <td style="color:var(--text-muted);">${esc(st.registered_at || '—')}</td>
                        <td>${st.photo_url ? `<a href="${esc(st.photo_url)}" target="_blank" style="color:var(--accent);font-size:12px;">View photo</a>` : '—'}</td>
                    </tr>`).join('');
                }
            }
        } catch(e) { console.error("Error loading recent students:", e); }
    }

    // ── Courses Management ────────────────────────────────────────────────────
    async function loadCourses() {
        const tbody = document.getElementById('courses-tbody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text-muted);text-align:center;padding:24px;">Loading courses...</td></tr>';

        try {
            const d = await api('/api/admin/courses');
            if (!d.success) throw new Error(d.message);

            if (!d.courses || d.courses.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text-muted);text-align:center;padding:24px;">No courses added yet</td></tr>';
                return;
            }

            tbody.innerHTML = d.courses.map(c => `<tr>
                <td style="color:var(--text-muted);font-weight:600;">#${c.id}</td>
                <td style="font-weight:600;color:var(--text-primary);">${esc(c.name)}</td>
                <td><span class="role-badge admin">${esc(c.code)}</span></td>
                <td>
                    <span class="status-dot ${c.status==='active'?'active':'inactive'}"></span>
                    <span style="font-size:12px;font-weight:600;color:${c.status==='active'?'var(--status-present)':'var(--text-muted)'};">${c.status==='active'?'Active':'Inactive'}</span>
                </td>
                <td style="color:var(--text-secondary);">${c.class_count || 0}</td>
                <td style="color:var(--text-secondary);">${c.student_count || 0}</td>
                <td>
                    <div class="action-row">
                        <button class="btn btn-secondary btn-xs btn-toggle-course" data-id="${c.id}" data-status="${c.status}">${c.status==='active'?'Deactivate':'Activate'}</button>
                        <button class="btn btn-secondary btn-xs btn-edit-course" data-id="${c.id}" data-name="${esc(c.name)}" data-code="${esc(c.code)}" data-desc="${esc(c.description||'')}">Edit</button>
                        <button class="btn btn-danger btn-xs btn-delete-course" data-id="${c.id}" data-name="${esc(c.name)}">Delete</button>
                    </div>
                </td>
            </tr>`).join('');

            bindCourseActions();
        } catch(e) {
            tbody.innerHTML = `<tr><td colspan="7" style="color:var(--status-absent);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
        }
    }

    function bindCourseActions() {
        // Toggle status
        document.querySelectorAll('.btn-toggle-course').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.id;
                const currentStatus = btn.dataset.status;
                const newStatus = currentStatus === 'active' ? 'inactive' : 'active';
                const res = await api(`/api/admin/courses/${id}/status`, 'PUT', { status: newStatus });
                if (res.success) {
                    showToast('Course Updated', res.message);
                    loadCourses();
                    loadOverview();
                } else {
                    showToast('Error', res.message, 'danger');
                }
            });
        });

        // Edit course
        document.querySelectorAll('.btn-edit-course').forEach(btn => {
            btn.addEventListener('click', () => {
                document.getElementById('edit-course-id').value = btn.dataset.id;
                document.getElementById('edit-course-name').value = btn.dataset.name;
                document.getElementById('edit-course-code').value = btn.dataset.code;
                document.getElementById('edit-course-desc').value = btn.dataset.desc;
                const wrap = document.getElementById('edit-course-form-wrap');
                wrap.style.display = 'block';
                wrap.scrollIntoView({ behavior: 'smooth' });
            });
        });

        // Delete course
        document.querySelectorAll('.btn-delete-course').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm(`Delete course "${btn.dataset.name}"?\nThis can only succeed if no classes or students are linked.`)) return;
                const res = await api(`/api/admin/courses/${btn.dataset.id}`, 'DELETE');
                if (res.success) {
                    showToast('Course Deleted', res.message);
                    loadCourses();
                    loadOverview();
                } else {
                    showToast('Cannot Delete', res.message, 'danger');
                }
            });
        });
    }

    // New Course Form Handlers
    document.getElementById('btn-new-course')?.addEventListener('click', () => {
        document.getElementById('new-course-form-wrap').style.display = 'block';
    });
    document.getElementById('btn-cancel-course')?.addEventListener('click', () => {
        document.getElementById('new-course-form-wrap').style.display = 'none';
    });
    document.getElementById('btn-create-course')?.addEventListener('click', async () => {
        const name = document.getElementById('new-course-name').value.trim();
        const code = document.getElementById('new-course-code').value.trim();
        const desc = document.getElementById('new-course-desc').value.trim();
        if (!name) {
            showToast('Required', 'Please enter a course name.', 'danger');
            return;
        }
        const res = await api('/api/admin/courses', 'POST', { name, code, description: desc });
        if (res.success) {
            showToast('Course Created', res.message);
            document.getElementById('new-course-form-wrap').style.display = 'none';
            ['new-course-name','new-course-code','new-course-desc'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
            loadCourses();
            loadOverview();
        } else {
            showToast('Error', res.message, 'danger');
        }
    });

    // Edit Course Form Handlers
    document.getElementById('btn-cancel-edit-course')?.addEventListener('click', () => {
        document.getElementById('edit-course-form-wrap').style.display = 'none';
    });
    document.getElementById('btn-save-edit-course')?.addEventListener('click', async () => {
        const id = document.getElementById('edit-course-id').value;
        const name = document.getElementById('edit-course-name').value.trim();
        const code = document.getElementById('edit-course-code').value.trim();
        const desc = document.getElementById('edit-course-desc').value.trim();
        if (!name) {
            showToast('Required', 'Course name cannot be empty.', 'danger');
            return;
        }
        const res = await api(`/api/admin/courses/${id}`, 'PUT', { name, code, description: desc });
        if (res.success) {
            showToast('Course Updated', res.message);
            document.getElementById('edit-course-form-wrap').style.display = 'none';
            loadCourses();
            loadOverview();
        } else {
            showToast('Error', res.message, 'danger');
        }
    });

    // ── Classes ───────────────────────────────────────────────────────────────
    async function loadClasses() {
        const tbody = document.getElementById('classes-tbody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text-muted);text-align:center;padding:24px;">Loading...</td></tr>';
        try {
            const d = await api('/api/admin/classes');
            if (!d.success) throw new Error(d.message);
            if (!d.classes || d.classes.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="color:var(--text-muted);text-align:center;padding:24px;">No classes added yet</td></tr>';
                return;
            }
            tbody.innerHTML = d.classes.map(c => `<tr>
                <td style="font-weight:600;color:var(--text-primary);">${esc(c.name)}</td>
                <td><span class="role-badge admin">${esc(c.code)}</span></td>
                <td style="color:var(--text-primary);font-weight:500;">${esc(c.course_name||'—')}</td>
                <td style="color:var(--text-secondary);">${c.capacity || 60}</td>
                <td style="color:var(--text-secondary);">${c.student_count || 0}</td>
                <td>
                    <span class="status-dot ${c.status==='active'?'active':'inactive'}"></span>
                    <span style="font-size:12px;color:${c.status==='active'?'var(--status-present)':'var(--text-muted)'};">${c.status==='active'?'Active':'Inactive'}</span>
                </td>
                <td>
                    <div class="action-row">
                        <button class="btn btn-secondary btn-xs btn-toggle-class" data-id="${c.id}" data-status="${c.status}">${c.status==='active'?'Deactivate':'Activate'}</button>
                        <button class="btn btn-danger btn-xs btn-delete-class" data-id="${c.id}" data-name="${esc(c.name)}">Delete</button>
                    </div>
                </td>
            </tr>`).join('');

            bindClassActions();
        } catch(e) {
            tbody.innerHTML = `<tr><td colspan="7" style="color:var(--status-absent);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
        }
    }

    function bindClassActions() {
        document.querySelectorAll('.btn-toggle-class').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.id;
                const newStatus = btn.dataset.status === 'active' ? 'inactive' : 'active';
                const res = await api(`/api/admin/classes/${id}/status`, 'PUT', { status: newStatus });
                if (res.success) {
                    showToast('Class Updated', res.message);
                    loadClasses();
                } else {
                    showToast('Error', res.message, 'danger');
                }
            });
        });

        document.querySelectorAll('.btn-delete-class').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm(`Delete class "${btn.dataset.name}"?`)) return;
                const res = await api(`/api/admin/classes/${btn.dataset.id}`, 'DELETE');
                if (res.success) { showToast('Deleted', res.message); loadClasses(); loadOverview(); }
                else showToast('Cannot Delete', res.message, 'danger');
            });
        });
    }

    // Populate course dropdown in class form
    async function populateCourseSelectForClass() {
        const sel = document.getElementById('new-class-course');
        if (!sel) return;
        sel.innerHTML = '<option value="">-- Select Course --</option>';
        const d = await api('/api/admin/courses');
        if (d.success && d.courses && d.courses.length > 0) {
            d.courses.forEach(crs => {
                const opt = document.createElement('option');
                opt.value = crs.id;
                opt.textContent = `${crs.name} (${crs.code})`;
                sel.appendChild(opt);
            });
        } else {
            const opt = document.createElement('option');
            opt.value = "";
            opt.textContent = "No courses available. Create a Course first!";
            opt.disabled = true;
            sel.appendChild(opt);
        }
    }

    document.getElementById('btn-new-class')?.addEventListener('click', async () => {
        const wrap = document.getElementById('new-class-form-wrap');
        wrap.style.display = 'block';
        await populateCourseSelectForClass();
    });
    document.getElementById('btn-cancel-class')?.addEventListener('click', () => {
        document.getElementById('new-class-form-wrap').style.display = 'none';
    });
    document.getElementById('btn-create-class')?.addEventListener('click', async () => {
        const name     = document.getElementById('new-class-name').value.trim();
        const code     = document.getElementById('new-class-code').value.trim();
        const course_id = parseInt(document.getElementById('new-class-course').value);
        const capacity = parseInt(document.getElementById('new-class-capacity').value) || 60;
        if (!name || !course_id) {
            showToast('Missing fields', 'Class name and Course selection are required.', 'danger');
            return;
        }
        const res = await api('/api/admin/classes', 'POST', { name, code, course_id, capacity });
        if (res.success) {
            showToast('Class Created', res.message);
            document.getElementById('new-class-form-wrap').style.display = 'none';
            ['new-class-name','new-class-code'].forEach(id => document.getElementById(id).value='');
            loadClasses();
            loadOverview();
        } else {
            showToast('Error', res.message, 'danger');
        }
    });

    // ── Students ──────────────────────────────────────────────────────────────
    async function loadStudents() {
        const tbody = document.getElementById('students-tbody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:24px;">Loading students...</td></tr>';

        try {
            const d = await api('/api/admin/students');
            if (!d.success) throw new Error(d.message);
            if (!d.students || d.students.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:24px;">No students registered yet</td></tr>';
                return;
            }

            tbody.innerHTML = d.students.map(s => `<tr>
                <td style="font-weight:700;color:var(--accent);">${esc(s.roll_no)}</td>
                <td style="font-weight:600;color:var(--text-primary);">${esc(s.name)}</td>
                <td style="color:var(--text-primary);">${esc(s.course_name || '—')}</td>
                <td style="color:var(--text-secondary);">${esc(s.class_name || '—')}</td>
                <td>
                    ${s.face_registered
                        ? '<span style="color:var(--status-present);font-weight:600;">✓ Face Registered</span>'
                        : '<span style="color:var(--text-muted);">Not Registered</span>'}
                </td>
                <td style="color:var(--text-muted);">${fmtDate(s.created_at)}</td>
            </tr>`).join('');
        } catch(e) {
            tbody.innerHTML = `<tr><td colspan="6" style="color:var(--status-absent);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
        }
    }

    // ── Users ─────────────────────────────────────────────────────────────────
    async function loadUsers() {
        const tbody = document.getElementById('users-tbody');
        tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:24px;">Loading...</td></tr>';
        try {
            const d = await api('/api/admin/users');
            if (!d.success) throw new Error(d.message);
            if (!d.users || d.users.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:24px;">No users found</td></tr>';
                return;
            }
            tbody.innerHTML = d.users.map(u => `<tr>
                <td style="font-weight:600;color:var(--text-primary);">${esc(u.name)}</td>
                <td style="color:var(--text-secondary);">${esc(u.email)}</td>
                <td><span class="role-badge ${esc(u.role)}">${esc(u.role)}</span></td>
                <td><span class="status-dot ${u.is_active?'active':'inactive'}"></span>${u.is_active?'Active':'Inactive'}</td>
                <td style="color:var(--text-muted);">${fmtDate(u.last_login)}</td>
                <td>
                    <div class="action-row">
                        <button class="btn btn-secondary btn-xs btn-toggle-user" data-id="${u.id}" data-active="${u.is_active}">${u.is_active?'Deactivate':'Activate'}</button>
                        ${['admin@school.edu', 'admin@attendai.edu', 'teacher@school.edu'].includes(u.email) || u.role === 'admin' 
                            ? `<span style="color:var(--text-muted);font-size:11px;padding:2px 6px;">Protected</span>`
                            : `<button class="btn btn-danger btn-xs btn-delete-user" data-id="${u.id}" data-name="${esc(u.name)}">Delete</button>`}
                    </div>
                </td>
            </tr>`).join('');
            bindUserActions();
        } catch(e) {
            tbody.innerHTML = `<tr><td colspan="6" style="color:var(--status-absent);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
        }
    }

    function bindUserActions() {
        document.querySelectorAll('.btn-toggle-user').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.id;
                const nowActive = btn.dataset.active === 'true';
                const res = await api(`/api/admin/users/${id}`, 'PUT', { is_active: !nowActive });
                if (res.success) { showToast('User updated', res.message); loadUsers(); }
                else showToast('Error', res.message, 'danger');
            });
        });
        document.querySelectorAll('.btn-delete-user').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm(`Delete user "${btn.dataset.name}"? This cannot be undone.`)) return;
                const res = await api(`/api/admin/users/${btn.dataset.id}`, 'DELETE');
                if (res.success) { showToast('Deleted', res.message); loadUsers(); loadOverview(); }
                else showToast('Error', res.message, 'danger');
            });
        });
    }

    // New user form
    document.getElementById('btn-new-user')?.addEventListener('click', () => {
        document.getElementById('new-user-form-wrap').style.display = 'block';
    });
    document.getElementById('btn-cancel-user')?.addEventListener('click', () => {
        document.getElementById('new-user-form-wrap').style.display = 'none';
    });
    document.getElementById('btn-create-user')?.addEventListener('click', async () => {
        const name     = document.getElementById('new-user-name').value.trim();
        const email    = document.getElementById('new-user-email').value.trim();
        const password = document.getElementById('new-user-password').value.trim();
        const role     = document.getElementById('new-user-role').value;
        if (!name || !email || !password) { showToast('Missing fields', 'All fields are required.', 'danger'); return; }
        const res = await api('/api/admin/users', 'POST', { name, email, password, role });
        if (res.success) {
            showToast('User created', res.message);
            document.getElementById('new-user-form-wrap').style.display = 'none';
            ['new-user-name','new-user-email','new-user-password'].forEach(id => document.getElementById(id).value = '');
            loadUsers();
            loadOverview();
        } else {
            showToast('Error', res.message, 'danger');
        }
    });

    // ── Departments ───────────────────────────────────────────────────────────
    async function loadDepts() {
        const tbody = document.getElementById('depts-tbody');
        tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text-muted);text-align:center;padding:24px;">Loading...</td></tr>';
        try {
            const d = await api('/api/admin/departments');
            if (!d.success) throw new Error(d.message);
            if (!d.departments || d.departments.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text-muted);text-align:center;padding:24px;">No departments found</td></tr>';
                return;
            }
            tbody.innerHTML = d.departments.map(dep => `<tr>
                <td style="font-weight:600;color:var(--text-primary);">${esc(dep.name)}</td>
                <td><span class="role-badge admin">${esc(dep.code)}</span></td>
                <td style="color:var(--text-secondary);">${dep.class_count}</td>
                <td style="color:var(--text-muted);">${esc(dep.description||'—')}</td>
                <td>
                    <div class="action-row">
                        <button class="btn btn-danger btn-xs btn-delete-dept" data-id="${dep.id}" data-name="${esc(dep.name)}">Delete</button>
                    </div>
                </td>
            </tr>`).join('');
            document.querySelectorAll('.btn-delete-dept').forEach(btn => {
                btn.addEventListener('click', async () => {
                    if (!confirm(`Delete department "${btn.dataset.name}"?`)) return;
                    const res = await api(`/api/admin/departments/${btn.dataset.id}`, 'DELETE');
                    if (res.success) { showToast('Deleted', res.message); loadDepts(); loadOverview(); }
                    else showToast('Error', res.message, 'danger');
                });
            });
        } catch(e) {
            tbody.innerHTML = `<tr><td colspan="5" style="color:var(--status-absent);text-align:center;padding:24px;">${esc(e.message)}</td></tr>`;
        }
    }

    document.getElementById('btn-new-dept')?.addEventListener('click', () => {
        document.getElementById('new-dept-form-wrap').style.display = 'block';
    });
    document.getElementById('btn-cancel-dept')?.addEventListener('click', () => {
        document.getElementById('new-dept-form-wrap').style.display = 'none';
    });
    document.getElementById('btn-create-dept')?.addEventListener('click', async () => {
        const name = document.getElementById('new-dept-name').value.trim();
        const code = document.getElementById('new-dept-code').value.trim();
        const desc = document.getElementById('new-dept-desc').value.trim();
        if (!name || !code) { showToast('Missing fields', 'Name and code are required.', 'danger'); return; }
        const res = await api('/api/admin/departments', 'POST', { name, code, description: desc });
        if (res.success) {
            showToast('Created', res.message);
            document.getElementById('new-dept-form-wrap').style.display = 'none';
            ['new-dept-name','new-dept-code','new-dept-desc'].forEach(id => document.getElementById(id).value='');
            loadDepts();
            loadOverview();
        } else {
            showToast('Error', res.message, 'danger');
        }
    });

    // ── Attendance Records State & Logic ───────────────────────────────────────
    let allAttendanceRecords = [];
    let adminAvailableCourses = [];
    let adminAvailableClasses = [];
    let attendanceFiltersInitialized = false;

    async function loadAcademicFilters(force = false) {
        if (attendanceFiltersInitialized && !force && adminAvailableCourses.length > 0) return;
        try {
            const [cRes, clRes] = await Promise.all([
                api('/api/courses'),
                api('/api/classes')
            ]);
            adminAvailableCourses = cRes.courses || [];
            adminAvailableClasses = clRes.classes || [];
            populateAdminCourseFilter();
            populateAdminClassFilter();
            attendanceFiltersInitialized = true;
        } catch (e) {
            console.error("Failed to load academic courses/classes for attendance:", e);
        }
    }

    function populateAdminCourseFilter() {
        const sel = document.getElementById('attendance-course-filter');
        if (!sel) return;
        const currentVal = sel.value;
        sel.innerHTML = '<option value="">All Courses</option>';
        adminAvailableCourses.forEach(c => {
            const codePart = c.code ? ` (${c.code})` : '';
            sel.innerHTML += `<option value="${c.id}">${esc(c.name)}${esc(codePart)}</option>`;
        });
        if (currentVal && adminAvailableCourses.some(c => String(c.id) === String(currentVal))) {
            sel.value = currentVal;
        }
    }

    function populateAdminClassFilter(courseId = null) {
        const sel = document.getElementById('attendance-class-filter');
        if (!sel) return;
        const currentVal = sel.value;
        let classesToShow = adminAvailableClasses;

        if (courseId) {
            classesToShow = adminAvailableClasses.filter(cl => String(cl.course_id) === String(courseId));
            if (classesToShow.length === 0) {
                sel.innerHTML = '<option value="">No classes in this course</option>';
                return;
            }
            sel.innerHTML = `<option value="">All Classes (${classesToShow.length})</option>`;
        } else {
            sel.innerHTML = '<option value="">All Classes</option>';
        }

        classesToShow.forEach(cl => {
            const label = cl.course_name ? `${cl.name} (${cl.course_name})` : cl.name;
            sel.innerHTML += `<option value="${cl.id}">${esc(label)}</option>`;
        });

        if (currentVal && classesToShow.some(cl => String(cl.id) === String(currentVal))) {
            sel.value = currentVal;
        } else {
            sel.value = '';
        }
    }

    async function loadAttendance() {
        const tbody = document.getElementById('attendance-tbody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="8" style="color:var(--text-muted);text-align:center;padding:28px;">Loading attendance records...</td></tr>';
        }
        
        // Ensure academic dropdowns are populated
        await loadAcademicFilters(true);

        try {
            const d = await api('/api/attendance');
            allAttendanceRecords = d.records || [];
            renderAttendanceRecords();
        } catch(e) {
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="8" style="color:var(--status-absent);text-align:center;padding:24px;">Error: ${esc(e.message)}</td></tr>`;
            }
        }
    }

    function renderAttendanceRecords() {
        const tbody = document.getElementById('attendance-tbody');
        if (!tbody) return;

        const query = document.getElementById('attendance-search-input')?.value.toLowerCase().trim() || "";
        const courseId = document.getElementById('attendance-course-filter')?.value || "";
        const classId = document.getElementById('attendance-class-filter')?.value || "";
        const dateVal = document.getElementById('attendance-date-filter')?.value || "";

        let filtered = allAttendanceRecords;

        if (query) {
            filtered = filtered.filter(l => 
                (l.name && l.name.toLowerCase().includes(query)) ||
                (l.roll_no && String(l.roll_no).toLowerCase().includes(query))
            );
        }
        if (dateVal) {
            filtered = filtered.filter(l => l.date === dateVal);
        }
        if (courseId) {
            const selectedCourse = adminAvailableCourses.find(c => String(c.id) === String(courseId));
            filtered = filtered.filter(l => 
                String(l.course_id) === String(courseId) ||
                (selectedCourse && l.course_name && (
                    l.course_name.toLowerCase() === selectedCourse.name.toLowerCase() ||
                    (selectedCourse.code && l.course_name.toLowerCase() === selectedCourse.code.toLowerCase())
                ))
            );
        }
        if (classId) {
            const selectedClass = adminAvailableClasses.find(cl => String(cl.id) === String(classId));
            filtered = filtered.filter(l => 
                String(l.class_id) === String(classId) ||
                (selectedClass && l.class_name && (
                    l.class_name.toLowerCase() === selectedClass.name.toLowerCase() ||
                    (selectedClass.code && l.class_name.toLowerCase() === selectedClass.code.toLowerCase())
                ))
            );
        }

        // Update Record Count Badge
        const countBadge = document.getElementById('attendance-count-badge');
        if (countBadge) {
            if (filtered.length === allAttendanceRecords.length) {
                countBadge.textContent = `${allAttendanceRecords.length} Records`;
            } else {
                countBadge.textContent = `Showing ${filtered.length} of ${allAttendanceRecords.length}`;
            }
        }

        // Update Active Filter Banner
        const banner = document.getElementById('attendance-active-filter-banner');
        const bannerText = document.getElementById('attendance-active-filter-text');
        const activeFilters = [];
        if (courseId) {
            const cObj = adminAvailableCourses.find(c => String(c.id) === String(courseId));
            activeFilters.push(`Course: <strong>${esc(cObj ? cObj.name : courseId)}</strong>`);
        }
        if (classId) {
            const clObj = adminAvailableClasses.find(cl => String(cl.id) === String(classId));
            activeFilters.push(`Class: <strong>${esc(clObj ? clObj.name : classId)}</strong>`);
        }
        if (dateVal) {
            activeFilters.push(`Date: <strong>${esc(dateVal)}</strong>`);
        }
        if (query) {
            activeFilters.push(`Search: <strong>"${esc(query)}"</strong>`);
        }

        if (banner && bannerText) {
            if (activeFilters.length > 0) {
                bannerText.innerHTML = activeFilters.join(' &nbsp;•&nbsp; ');
                banner.style.display = 'flex';
            } else {
                banner.style.display = 'none';
            }
        }

        // Update Export CSV Link with active query params
        const exportBtn = document.getElementById('btn-export-attendance-csv');
        if (exportBtn) {
            const params = new URLSearchParams();
            if (courseId) params.append('course_id', courseId);
            if (classId) params.append('class_id', classId);
            if (dateVal) params.append('date', dateVal);
            if (query) params.append('search', query);
            const qs = params.toString();
            exportBtn.href = `/api/attendance/download${qs ? '?' + qs : ''}`;
        }

        // Render Table Rows
        if (filtered.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="color:var(--text-muted);text-align:center;padding:36px;"><div style="font-size:14px;font-weight:600;margin-bottom:4px;color:var(--text-primary);">No attendance records found</div><div>No records match the selected class, course, or date filters.</div></td></tr>';
            return;
        }

        const statusStyle = {
            Present: 'background:rgba(52,211,153,.12);color:var(--status-present);',
            Absent:  'background:rgba(239,68,68,.12);color:var(--status-absent);',
            Late:    'background:rgba(251,191,36,.12);color:var(--status-late);'
        };

        tbody.innerHTML = filtered.map(r => {
            const roll = esc(r.roll_no || '—');
            const name = esc(r.name || 'Unknown');
            const className = esc(r.class_name || '—');
            const courseName = esc(r.course_name || '—');
            const date = esc(r.date || '');
            const time = esc(r.time || '');
            const status = esc(r.status || 'Present');
            const recStatus = esc(r.recognition_status || 'Recognized');
            const sStyle = statusStyle[r.status] || 'background:rgba(255,255,255,.05);color:var(--text-secondary);';

            return `<tr>
                <td style="color:var(--accent);font-weight:600;">${roll}</td>
                <td style="font-weight:600;color:var(--text-primary);">${name}</td>
                <td><span class="role-badge" style="background:rgba(167,139,250,.12);color:#A78BFA;">${className}</span></td>
                <td><span class="role-badge" style="background:rgba(34,211,238,.12);color:#22D3EE;">${courseName}</span></td>
                <td style="color:var(--text-secondary);">${date}</td>
                <td style="color:var(--text-secondary);">${time}</td>
                <td><span class="role-badge" style="${sStyle}">${status}</span></td>
                <td><span style="font-size:11px;color:var(--text-muted);background:rgba(255,255,255,.04);padding:2px 8px;border-radius:6px;border:1px solid var(--border-subtle);">${recStatus}</span></td>
            </tr>`;
        }).join('');
    }

    // Set up filter event listeners
    function initAttendanceFilterEvents() {
        const courseFilter = document.getElementById('attendance-course-filter');
        const classFilter = document.getElementById('attendance-class-filter');
        const searchInput = document.getElementById('attendance-search-input');
        const dateFilter = document.getElementById('attendance-date-filter');
        const resetBtn = document.getElementById('btn-attendance-reset');
        const quickClearBtn = document.getElementById('btn-quick-clear-filter');
        const refreshBtn = document.getElementById('btn-refresh-attendance');
        const clearLogsBtn = document.getElementById('btn-clear-attendance-records');

        courseFilter?.addEventListener('change', () => {
            const courseId = courseFilter.value;
            populateAdminClassFilter(courseId);
            renderAttendanceRecords();
        });

        classFilter?.addEventListener('change', () => {
            renderAttendanceRecords();
        });

        searchInput?.addEventListener('input', () => {
            renderAttendanceRecords();
        });

        dateFilter?.addEventListener('change', () => {
            renderAttendanceRecords();
        });

        const resetAllFilters = () => {
            if (searchInput) searchInput.value = '';
            if (courseFilter) courseFilter.value = '';
            populateAdminClassFilter(null);
            if (classFilter) classFilter.value = '';
            if (dateFilter) dateFilter.value = '';
            renderAttendanceRecords();
        };

        resetBtn?.addEventListener('click', resetAllFilters);
        quickClearBtn?.addEventListener('click', resetAllFilters);

        refreshBtn?.addEventListener('click', async () => {
            showToast('Refreshing', 'Reloading attendance records...', 'info');
            await loadAttendance();
            showToast('Refreshed', 'Attendance records updated.');
        });

        clearLogsBtn?.addEventListener('click', async () => {
            const confirmed = confirm(
                "CLEAR ALL ATTENDANCE LOGS?\n\n" +
                "This will permanently delete all attendance history from the database and Attendance.csv.\n\n" +
                "Are you sure you want to proceed?"
            );
            if (!confirmed) return;

            try {
                const res = await api('/api/attendance', 'DELETE');
                if (res.success) {
                    showToast('Cleared', res.message || 'All attendance records cleared.');
                    await loadAttendance();
                    loadOverview();
                } else {
                    showToast('Error', res.message || 'Failed to clear records', 'danger');
                }
            } catch (err) {
                showToast('Error', err.message, 'danger');
            }
        });
    }

    // ── Audit Logs ────────────────────────────────────────────────────────────
    async function loadAudit() {
        const list = document.getElementById('audit-list');
        list.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:32px;">Loading...</div>';
        try {
            const d = await api('/api/admin/audit-logs?limit=100');
            if (!d.success) { list.innerHTML = `<div style="color:var(--text-muted);padding:24px;">${esc(d.message||'No audit log route available')}</div>`; return; }
            const logs = d.logs || [];
            if (logs.length === 0) { list.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:32px;">No audit logs yet.</div>'; return; }
            list.innerHTML = logs.map(l => `<div class="audit-entry">
                <span class="audit-time">${fmtDate(l.timestamp)}</span>
                <span class="audit-action">${esc(l.action)}</span>
                <span style="color:var(--text-secondary);flex:1;">${esc(l.details||'')}</span>
                <span style="color:var(--text-muted);">${esc(l.user_name||'System')}</span>
            </div>`).join('');
        } catch(e) {
            list.innerHTML = `<div style="color:var(--text-muted);text-align:center;padding:24px;">Audit log endpoint not available.</div>`;
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

    // ── Boot: initialize filters and load first tab ───────────────
    initAttendanceFilterEvents();
    loadOverview();
});
