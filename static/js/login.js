// Login Page JavaScript
document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("login-form");
    const emailInput = document.getElementById("teacher-email");
    const passwordInput = document.getElementById("teacher-password");
    const loginBtn = document.getElementById("btn-login");
    const loginSpinner = document.getElementById("login-spinner");
    const togglePasswordBtn = document.getElementById("toggle-password-btn");
    const authMessage = document.getElementById("auth-message");
    const rememberMeCheckbox = document.getElementById("remember-me");
    const toastContainer = document.getElementById("toast-container");

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function validateEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    // --- Toast Notification System ---
    function showToast(title, message, type = "success") {
        if (!toastContainer) return;
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        
        const icon = type === "success" ? "✓" : "✕";
        const safeTitle = escapeHtml(title);
        const safeMessage = escapeHtml(message);
        
        toast.innerHTML = `
            <div class="toast-icon">${icon}</div>
            <div class="toast-content">
                <h4>${safeTitle}</h4>
                <p>${safeMessage}</p>
            </div>
        `;
        
        toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = "slideIn 0.35s reverse forwards";
            setTimeout(() => {
                toast.remove();
            }, 350);
        }, 4000);
    }

    // --- Password Toggle ---
    if (togglePasswordBtn && passwordInput) {
        togglePasswordBtn.addEventListener("click", (e) => {
            e.preventDefault();
            const type = passwordInput.type === "password" ? "text" : "password";
            passwordInput.type = type;
            togglePasswordBtn.classList.toggle("active");
        });
    }

    // --- Role Switching Configuration ---
    const roleTabs = document.querySelectorAll(".role-tab");
    const portalTitle = document.getElementById("portal-title");
    const portalDesc = document.getElementById("portal-desc");
    const demoEmail = document.getElementById("demo-email");
    const demoPassword = document.getElementById("demo-password");
    const demoCredsCard = document.getElementById("demo-creds-card");
    const themeBtn = document.getElementById("btn-theme-toggle");
    const themeLabel = document.getElementById("theme-label");
    const emailLoginSection = document.getElementById("email-login-section");
    const studentLoginSection = document.getElementById("student-login-section");

    const roleConfigs = {
        teacher: {
            title: "Teacher Portal",
            desc: "Sign in to manage attendance and recognize students",
            email: "teacher@school.edu",
            password: "password123"
        },
        faculty: {
            title: "Faculty Portal",
            desc: "Sign in for department overview and class analytics",
            email: "faculty@school.edu",
            password: "faculty123"
        },
        student: {
            title: "Student Portal",
            desc: "Sign in to view your attendance history and reports"
        },
        admin: {
            title: "Admin Portal",
            desc: "Sign in for full system configuration and user management",
            email: "admin@school.edu",
            password: "admin123"
        }
    };

    function switchRole(roleKey, autoFill = true) {
        const config = roleConfigs[roleKey] || roleConfigs.teacher;
        
        roleTabs.forEach(tab => {
            const isMatch = tab.dataset.role === roleKey;
            tab.classList.toggle("active", isMatch);
            tab.setAttribute("aria-selected", isMatch ? "true" : "false");
        });

        if (portalTitle) portalTitle.textContent = config.title;
        if (portalDesc) portalDesc.textContent = config.desc;

        if (roleKey === "student") {
            if (emailLoginSection) emailLoginSection.style.display = "none";
            if (studentLoginSection) studentLoginSection.style.display = "block";
        } else {
            if (studentLoginSection) studentLoginSection.style.display = "none";
            if (emailLoginSection) emailLoginSection.style.display = "block";

            if (demoEmail && config.email) demoEmail.textContent = config.email;
            if (demoPassword && config.password) demoPassword.textContent = config.password;

            if (autoFill && emailInput && passwordInput && config.email) {
                emailInput.value = config.email;
                passwordInput.value = config.password;
            }
        }
    }

    roleTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const role = tab.dataset.role;
            switchRole(role, role !== "student");
        });
    });

    if (demoCredsCard) {
        demoCredsCard.addEventListener("click", () => {
            const activeTab = document.querySelector(".role-tab.active");
            const activeRole = activeTab ? activeTab.dataset.role : "teacher";
            if (activeRole !== "student") {
                switchRole(activeRole, true);
                showToast("Credentials Filled", "Demo credentials inserted into form.", "success");
            }
        });
    }

    // --- Theme Toggle ---
    function applyLoginTheme(theme) {
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

    const currentTheme = localStorage.getItem('appTheme') || 'dark';
    applyLoginTheme(currentTheme);

    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const isDark = document.documentElement.classList.contains('dark-theme');
            applyLoginTheme(isDark ? 'light' : 'dark');
        });
    }

    // --- Load Saved Email ---
    function loadSavedEmail() {
        const savedEmail = localStorage.getItem("teacher_email");
        if (savedEmail) {
            emailInput.value = savedEmail;
            rememberMeCheckbox.checked = true;
        }
    }
    loadSavedEmail();

    // --- Handle Login Form Submission ---
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const email = emailInput.value.trim();
        const password = passwordInput.value.trim();

        if (!email || !password) {
            authMessage.className = "auth-message error";
            authMessage.textContent = "Please enter both email and password.";
            return;
        }

        if (!validateEmail(email)) {
            authMessage.className = "auth-message error";
            authMessage.textContent = "Please enter a valid email address.";
            return;
        }

        if (password.length < 6) {
            authMessage.className = "auth-message error";
            authMessage.textContent = "Password must be at least 6 characters long.";
            return;
        }

        // Disable button and show spinner
        loginBtn.disabled = true;
        loginSpinner.classList.remove("hidden");
        authMessage.className = "auth-message";
        authMessage.textContent = "";

        try {
            const response = await fetch("/api/login", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ email, password })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                // Save email if checked
                if (rememberMeCheckbox.checked) {
                    localStorage.setItem("teacher_email", email);
                } else {
                    localStorage.removeItem("teacher_email");
                }

                authMessage.className = "auth-message success";
                authMessage.textContent = "Login successful! Redirecting...";
                showToast("Welcome", `Hello ${data.user_name || data.teacher_name}!`, "success");

                // Role-based redirect
                const role = (data.user_role || 'teacher').toLowerCase();
                const redirectMap = {
                    admin:   '/admin',
                    faculty: '/faculty',
                    student: '/student',
                    teacher: '/'
                };
                const dest = redirectMap[role] || '/';
                setTimeout(() => {
                    window.location.href = dest;
                }, 1200);
            } else {
                authMessage.className = "auth-message error";
                authMessage.textContent = data.message || "Login failed. Please try again.";
                showToast("Login Failed", data.message || "Invalid credentials.", "danger");
            }
        } catch (error) {
            console.error("Login error:", error);
            authMessage.className = "auth-message error";
            authMessage.textContent = "Server error. Please try again later.";
            showToast("Server Error", "Unable to connect to the server.", "danger");
        } finally {
            // Re-enable button and hide spinner
            loginBtn.disabled = false;
            loginSpinner.classList.add("hidden");
        }
    });

    // --- Enter key to submit ---
    passwordInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            loginForm.dispatchEvent(new Event("submit"));
        }
    });

    // Check URL query parameters for default tab (?tab=student) or URL path
    const urlParams = new URLSearchParams(window.location.search);
    const initialTab = urlParams.get("tab");
    if (initialTab === "student" || window.location.pathname.includes("student-login")) {
        switchRole("student", false);
    } else if (initialTab && roleConfigs[initialTab]) {
        switchRole(initialTab, true);
    }

    // ========================================================================
    // Student Login Form Handling
    // ========================================================================
    const studentForm = document.getElementById("student-login-form");
    const studentCourseSelect = document.getElementById("student-course");
    const studentClassSelect = document.getElementById("student-class");
    const studentRollInput = document.getElementById("student-roll-no");
    const studentLoginBtn = document.getElementById("btn-student-login");
    const studentSpinner = document.getElementById("student-login-spinner");
    const studentErrorBox = document.getElementById("student-login-error");
    const studentErrorText = document.getElementById("student-error-text");
    const studentDemoCard = document.getElementById("student-demo-card");

    // Dynamic Class Filtering on Course Change
    if (studentCourseSelect && studentClassSelect) {
        studentCourseSelect.addEventListener("change", () => {
            const selectedCourseId = studentCourseSelect.value;
            const classOptions = studentClassSelect.querySelectorAll("option");
            
            classOptions.forEach(opt => {
                if (!opt.value) {
                    opt.hidden = false;
                    return;
                }
                const optCourseId = opt.dataset.courseId;
                if (!selectedCourseId || !optCourseId || optCourseId === selectedCourseId) {
                    opt.hidden = false;
                } else {
                    opt.hidden = true;
                }
            });

            // If currently selected class is now hidden, reset to placeholder
            const selectedOpt = studentClassSelect.selectedOptions[0];
            if (selectedOpt && selectedOpt.hidden) {
                studentClassSelect.value = "";
            }
        });
    }

    // Auto-fill Student Demo Card
    if (studentDemoCard) {
        studentDemoCard.addEventListener("click", () => {
            if (studentCourseSelect) {
                for (let i = 0; i < studentCourseSelect.options.length; i++) {
                    const opt = studentCourseSelect.options[i];
                    if (opt.text.toLowerCase().includes("artificial intelligence") || opt.dataset.default === "true") {
                        studentCourseSelect.selectedIndex = i;
                        studentCourseSelect.dispatchEvent(new Event("change"));
                        break;
                    }
                }
            }
            if (studentClassSelect) {
                for (let i = 0; i < studentClassSelect.options.length; i++) {
                    const opt = studentClassSelect.options[i];
                    if (opt.text.toLowerCase().includes("3rd year") || opt.dataset.default === "true") {
                        studentClassSelect.selectedIndex = i;
                        break;
                    }
                }
            }
            if (studentRollInput) {
                studentRollInput.value = "01";
            }
            if (studentErrorBox) {
                studentErrorBox.style.display = "none";
            }
            showToast("Credentials Filled", "Sample student profile auto-filled.", "success");
        });
    }

    // Submit Student Login Form
    if (studentForm) {
        studentForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (studentErrorBox) studentErrorBox.style.display = "none";

            const courseId = studentCourseSelect ? studentCourseSelect.value : "";
            const classId = studentClassSelect ? studentClassSelect.value : "";
            const rollNo = studentRollInput ? studentRollInput.value.trim() : "";

            if (!courseId || !classId || !rollNo) {
                if (studentErrorText) {
                    studentErrorText.textContent = "Please fill in all three fields: Course, Class/Year, and Roll Number.";
                }
                if (studentErrorBox) studentErrorBox.style.display = "flex";
                return;
            }

            if (studentLoginBtn) studentLoginBtn.disabled = true;
            studentSpinner?.classList.remove("hidden");

            try {
                const res = await fetch("/api/student-login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        course_id: courseId,
                        class_id: classId,
                        roll_no: rollNo
                    })
                });

                const data = await res.json();

                if (res.ok && data.success) {
                    if (data.token) {
                        localStorage.setItem("authToken", data.token);
                    }
                    if (data.student) {
                        localStorage.setItem("studentUser", JSON.stringify(data.student));
                    }
                    showToast("Login Successful", `Welcome ${data.student?.name || 'Student'}!`, "success");
                    setTimeout(() => {
                        window.location.href = data.redirect_url || "/student/attendance";
                    }, 500);
                } else {
                    const errorMsg = data.message || "No student found with these details. Please check your Course, Class/Year, and Roll Number.";
                    if (studentErrorText) studentErrorText.textContent = errorMsg;
                    if (studentErrorBox) studentErrorBox.style.display = "flex";
                    showToast("Login Failed", errorMsg, "danger");
                }
            } catch (err) {
                console.error("Student login request error:", err);
                const netError = "Network error. Unable to verify student credentials. Please try again.";
                if (studentErrorText) studentErrorText.textContent = netError;
                if (studentErrorBox) studentErrorBox.style.display = "flex";
                showToast("Server Error", netError, "danger");
            } finally {
                if (studentLoginBtn) studentLoginBtn.disabled = false;
                studentSpinner?.classList.add("hidden");
            }
        });
    }
});
