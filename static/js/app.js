document.addEventListener("DOMContentLoaded", () => {
    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // State Variables
    let currentTab = "dashboard";
    let isCameraActive = false;
    let cameraLifecycleState = "IDLE"; // IDLE, INITIALIZING, ACTIVE, STOPPING, ERROR
    let registeredStudents = [];
    let attendanceLogs = [];
    let knownLogIds = new Set();
    let sessionLogsCount = 0;
    let initialLoad = true;

    // Elements
    const menuItems = document.querySelectorAll(".menu-item");
    const tabContents = document.querySelectorAll(".tab-content");
    const pageTitle = document.getElementById("page-title");
    const pageSubtitle = document.getElementById("page-subtitle");
    const dateTimeDisplay = document.getElementById("current-date-time");
    const btnLogout = document.getElementById("btn-logout");

    // Camera elements
    const btnToggleCamera = document.getElementById("btn-toggle-camera");
    const btnToggleCameraText = document.getElementById("btn-toggle-camera-text");
    const cameraStream = document.getElementById("camera-stream");
    const cameraPlaceholder = document.getElementById("camera-placeholder");
    const liveIndicator = document.getElementById("live-indicator");
    const btnStartCameraPlaceholder = document.getElementById("btn-start-camera-placeholder");
    const systemStatusIndicator = document.getElementById("system-status-indicator");
    const systemStatusText = document.getElementById("system-status-text");
    let lastProcessedEventTime = Date.now() / 1000 - 10;
    let alreadyMarkedToastCooldown = {};

    // Modal elements
    const registerModal = document.getElementById("register-modal");
    const btnOpenRegisterModal = document.getElementById("btn-open-register-modal");
    const btnOpenCameraRegister = document.getElementById("btn-open-camera-register");
    const btnCloseModal = document.getElementById("btn-close-modal");
    const btnCancelModal = document.getElementById("btn-cancel-modal");
    const registerForm = document.getElementById("register-student-form");
    const uploadArea = document.getElementById("upload-area");
    const fileInput = document.getElementById("student-photo");
    const uploadPlaceholder = document.getElementById("upload-placeholder");
    const uploadPreview = document.getElementById("upload-preview");
    const previewImg = document.getElementById("preview-img");
    const btnRemovePreview = document.getElementById("btn-remove-preview");
    const btnOpenCameraLive = document.getElementById("btn-open-camera-live");
    const btnTakeCameraPhoto = document.getElementById("btn-take-camera-photo");
    const btnCloseCameraLive = document.getElementById("btn-close-camera-live");
    const btnClearCapturePhoto = document.getElementById("btn-clear-capture-photo");
    const cameraCaptureArea = document.getElementById("camera-capture-area");
    const cameraLiveWrapper = document.getElementById("camera-live-wrapper");
    const cameraVideo = document.getElementById("camera-video");
    const cameraOverlay = document.getElementById("camera-overlay");
    const cameraServerStream = document.getElementById("camera-server-stream");
    let activeCameraMode = "browser";
    const capturedPhotoWrapper = document.getElementById("captured-photo-wrapper");
    const capturedPhotoImg = document.getElementById("captured-photo-img");
    const cameraInstructions = document.getElementById("camera-instructions");
    const cameraControlActions = document.getElementById("camera-control-actions");
    const btnRetakePhoto = document.getElementById("btn-retake-photo");
    const btnUsePhoto = document.getElementById("btn-use-photo");
    const btnSubmitRegistration = document.getElementById("btn-submit-registration");
    const registrationSpinner = document.getElementById("registration-spinner");
    let capturedBlob = null;
    let activePreviewUrl = null;
    let localCameraStream = null;
    let pendingCaptureDataUrl = null;
    let localFaceDetected = false;
    let faceDetector = null;
    let cameraDetectionFrame = null;
    let detectionInProgress = false;
    const cameraAnalysisCanvas = document.createElement("canvas");
    cameraAnalysisCanvas.width = 160;
    cameraAnalysisCanvas.height = 120;

    // Dashboard metrics
    const statTotalStudents = document.getElementById("stat-total-students");
    const statPresentToday = document.getElementById("stat-present-today");
    const statAbsentToday = document.getElementById("stat-absent-today");
    const statLastActive = document.getElementById("stat-last-active");

    // Lists & Tables
    const liveLogsContainer = document.getElementById("live-logs-container");
    const liveLogsEmpty = document.getElementById("live-logs-empty");
    const sessionCountBadge = document.getElementById("session-count-badge");
    const studentGrid = document.getElementById("student-grid");
    const attendanceTableBody = document.getElementById("attendance-table-body");
    const logsEmptyState = document.getElementById("logs-empty-state");

    // Filters & Academic Elements
    const studentSearchInput = document.getElementById("student-search-input");
    const studentCourseFilter = document.getElementById("student-course-filter");
    const studentClassFilter = document.getElementById("student-class-filter");
    const btnCaptureFace = document.getElementById("btn-capture-face");
    const cameraDeviceWrapper = document.getElementById("camera-device-wrapper");
    const cameraDeviceSelect = document.getElementById("camera-device-select");
    let selectedCameraDeviceId = "";
    const logSearchInput = document.getElementById("log-search-input");
    const logDateFilter = document.getElementById("log-date-filter");
    const logCourseFilter = document.getElementById("log-course-filter");
    const logClassFilter = document.getElementById("log-class-filter");
    const btnClearDateFilter = document.getElementById("btn-clear-date-filter");
    const btnClearLogs = document.getElementById("btn-clear-logs");

    // Teacher & Student Course/Class selection
    const teacherCourseSelect = document.getElementById("teacher-course-select");
    const teacherClassSelect = document.getElementById("teacher-class-select");
    const btnApplySessionFilter = document.getElementById("btn-apply-session-filter");
    const activeFilterText = document.getElementById("active-filter-text");

    const studentRollNoInput = document.getElementById("student-roll-no");
    const studentCourseSelect = document.getElementById("student-course");
    const studentClassSelect = document.getElementById("student-class");

    let availableCourses = [];
    let availableClasses = [];

    // Analytics elements
    const progressRing = document.getElementById("analytics-progress-ring");
    const analyticsPercentage = document.getElementById("analytics-percentage");
    const analyticsPresentCount = document.getElementById("analytics-present-count");
    const analyticsAbsentCount = document.getElementById("analytics-absent-count");
    const analyticsTotalCount = document.getElementById("analytics-total-count");

    // Toast container
    const toastContainer = document.getElementById("toast-container");

    // --- Web Audio API Synth Sound ---
    function playSuccessChime() {
        try {
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            
            // Note 1 (D5)
            const osc1 = audioCtx.createOscillator();
            const gain1 = audioCtx.createGain();
            osc1.type = "sine";
            osc1.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
            gain1.gain.setValueAtTime(0, audioCtx.currentTime);
            gain1.gain.linearRampToValueAtTime(0.2, audioCtx.currentTime + 0.05);
            gain1.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.25);
            osc1.connect(gain1);
            gain1.connect(audioCtx.destination);
            osc1.start();
            osc1.stop(audioCtx.currentTime + 0.3);

            // Note 2 (A5) after a small delay
            setTimeout(() => {
                const osc2 = audioCtx.createOscillator();
                const gain2 = audioCtx.createGain();
                osc2.type = "sine";
                osc2.frequency.setValueAtTime(880.00, audioCtx.currentTime); // A5
                gain2.gain.setValueAtTime(0, audioCtx.currentTime);
                gain2.gain.linearRampToValueAtTime(0.25, audioCtx.currentTime + 0.05);
                gain2.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.35);
                osc2.connect(gain2);
                gain2.connect(audioCtx.destination);
                osc2.start();
                osc2.stop(audioCtx.currentTime + 0.4);
            }, 100);

        } catch (e) {
            console.warn("AudioContext chime failed:", e);
        }
    }

    // --- Real-Time Date Clock ---
    function updateClock() {
        const now = new Date();
        const options = { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' };
        const dateStr = now.toLocaleDateString('en-US', options);
        const timeStr = now.toLocaleTimeString('en-US', { hour12: true, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        dateTimeDisplay.textContent = `${dateStr} | ${timeStr}`;
    }
    setInterval(updateClock, 1000);
    updateClock();

    // --- Toast Notification System ---
    function showToast(title, message, type = "success") {
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        
        const icon = type === "success" ? "✓" : type === "danger" ? "✕" : "ℹ";
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
        
        // Remove toast after animation completes (4s display)
        setTimeout(() => {
            toast.style.animation = "fadeIn 0.35s reverse forwards";
            setTimeout(() => {
                toast.remove();
            }, 350);
        }, 4000);
    }

    // --- Theme Toggle ---
    const themeToggleBtn = document.getElementById("btn-theme-toggle");
    const themeLabel = document.getElementById("theme-label");

    function applyTheme(theme) {
        if (theme === "light") {
            document.documentElement.classList.remove("dark-theme");
            document.documentElement.classList.add("light-theme");
            themeLabel.textContent = "Light";
            localStorage.setItem("appTheme", "light");
        } else {
            document.documentElement.classList.remove("light-theme");
            document.documentElement.classList.add("dark-theme");
            themeLabel.textContent = "Dark";
            localStorage.setItem("appTheme", "dark");
        }
    }

    themeToggleBtn?.addEventListener("click", () => {
        const currentTheme = document.documentElement.classList.contains("light-theme") ? "light" : "dark";
        applyTheme(currentTheme === "dark" ? "light" : "dark");
        showToast("Theme Updated", `Switched to ${themeLabel.textContent} mode.`, "success");
    });

    const savedTheme = localStorage.getItem("appTheme") || "dark";
    applyTheme(savedTheme);

    // --- Dynamic Navigation ---
    menuItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const tabName = item.getAttribute("data-tab");
            
            // Toggle active sidebar link
            menuItems.forEach(mi => mi.classList.remove("active"));
            item.classList.add("active");
            
            // Toggle viewport tabs
            tabContents.forEach(content => content.classList.remove("active"));
            document.getElementById(`tab-${tabName}`).classList.add("active");
            
            currentTab = tabName;
            
            // Change page title & labels
            if (tabName === "dashboard") {
                pageTitle.textContent = "Dashboard";
                pageSubtitle.textContent = "Real-time attendance tracking and face scanning.";
            } else if (tabName === "students") {
                pageTitle.textContent = "Student Directory";
                pageSubtitle.textContent = "Manage registered students and facial data.";
                fetchStudents();
            } else if (tabName === "logs") {
                pageTitle.textContent = "Attendance Records";
                pageSubtitle.textContent = "View, filter, and export CSV logs.";
                fetchAttendanceLogs();
            } else if (tabName === "analytics") {
                pageTitle.textContent = "System Analytics";
                pageSubtitle.textContent = "Visualize presence rates and metrics.";
                updateDashboardStats();
                updateAnalyticsRing();
            }

            // Stop camera if user navigates away from the face recognition dashboard
            if (tabName !== "dashboard" && (isCameraActive || cameraLifecycleState === "ACTIVE")) {
                toggleCamera("stop");
            }
            // Stop student registration preview camera if active
            if (typeof stopLocalCamera === "function" && localCameraStream) {
                stopLocalCamera();
            }
        });
    });

    // --- Academic Structure (Course & Class) Handling ---
    async function fetchAcademicData() {
        try {
            const [cRes, clRes] = await Promise.all([
                fetch("/api/courses"),
                fetch("/api/classes")
            ]);
            const cData = await cRes.json();
            const clData = await clRes.json();
            
            availableCourses = cData.courses || [];
            availableClasses = clData.classes || [];

            populateCourseSelects();
            populateClassSelects();
        } catch (err) {
            console.error("Failed to load academic courses/classes:", err);
        }
    }

    function populateCourseSelects() {
        if (teacherCourseSelect) {
            if (availableCourses.length === 0) {
                teacherCourseSelect.innerHTML = '<option value="">No courses available</option>';
            } else {
                teacherCourseSelect.innerHTML = '<option value="">All Courses</option>';
                availableCourses.forEach(c => {
                    teacherCourseSelect.innerHTML += `<option value="${c.id}">${escapeHtml(c.name)}</option>`;
                });
            }
        }
        if (studentCourseFilter) {
            if (availableCourses.length === 0) {
                studentCourseFilter.innerHTML = '<option value="">All Courses</option>';
            } else {
                studentCourseFilter.innerHTML = '<option value="">All Courses</option>';
                availableCourses.forEach(c => {
                    studentCourseFilter.innerHTML += `<option value="${c.id}">${escapeHtml(c.name)}</option>`;
                });
            }
        }
        if (studentCourseSelect) {
            if (availableCourses.length === 0) {
                studentCourseSelect.innerHTML = '<option value="">No courses available</option>';
            } else {
                studentCourseSelect.innerHTML = '<option value="">-- Select Course --</option>';
                availableCourses.forEach(c => {
                    studentCourseSelect.innerHTML += `<option value="${c.id}">${escapeHtml(c.name)}</option>`;
                });
            }
        }
        if (logCourseFilter) {
            if (availableCourses.length === 0) {
                logCourseFilter.innerHTML = '<option value="">No courses available</option>';
            } else {
                logCourseFilter.innerHTML = '<option value="">All Courses</option>';
                availableCourses.forEach(c => {
                    logCourseFilter.innerHTML += `<option value="${c.id}">${escapeHtml(c.name)}</option>`;
                });
            }
        }
    }

    function populateClassSelects(courseId = null, targetSelect = null) {
        let classesToShow = availableClasses;
        let placeholder = "-- Select Class / Year --";

        if (courseId) {
            classesToShow = availableClasses.filter(cl => String(cl.course_id) === String(courseId));
            if (classesToShow.length === 0) {
                placeholder = "No classes available for this course";
            }
        } else {
            if (availableClasses.length === 0) {
                placeholder = "No classes available";
            }
        }

        const buildOptions = (defaultLabel) => {
            let opts = `<option value="">${defaultLabel}</option>`;
            classesToShow.forEach(cl => {
                const label = cl.course_name ? `${cl.name} (${cl.course_name})` : cl.name;
                opts += `<option value="${cl.id}">${escapeHtml(label)}</option>`;
            });
            return opts;
        };

        if (targetSelect) {
            const isFilter = targetSelect === teacherClassSelect || targetSelect === logClassFilter || targetSelect === studentClassFilter;
            const label = classesToShow.length === 0 ? placeholder : (isFilter ? "All Classes" : "-- Select Class / Year --");
            targetSelect.innerHTML = buildOptions(label);
            return;
        }

        if (teacherClassSelect) {
            const label = classesToShow.length === 0 ? placeholder : "All Classes";
            teacherClassSelect.innerHTML = buildOptions(label);
        }
        if (studentClassFilter) {
            const label = classesToShow.length === 0 ? placeholder : "All Classes";
            studentClassFilter.innerHTML = buildOptions(label);
        }
        if (studentClassSelect) {
            studentClassSelect.innerHTML = buildOptions(placeholder);
        }
        if (logClassFilter) {
            const label = classesToShow.length === 0 ? placeholder : "All Classes";
            logClassFilter.innerHTML = buildOptions(label);
        }
    }

    teacherCourseSelect?.addEventListener("change", () => {
        const cId = teacherCourseSelect.value;
        populateClassSelects(cId, teacherClassSelect);
    });

    studentCourseFilter?.addEventListener("change", () => {
        const cId = studentCourseFilter.value;
        populateClassSelects(cId, studentClassFilter);
        renderStudentsGrid();
    });

    studentClassFilter?.addEventListener("change", () => {
        renderStudentsGrid();
    });

    studentCourseSelect?.addEventListener("change", () => {
        const cId = studentCourseSelect.value;
        populateClassSelects(cId, studentClassSelect);
    });

    logCourseFilter?.addEventListener("change", () => {
        const cId = logCourseFilter.value;
        populateClassSelects(cId, logClassFilter);
        renderLogsTable();
    });

    logClassFilter?.addEventListener("change", renderLogsTable);

    btnApplySessionFilter?.addEventListener("click", async () => {
        const cId = teacherCourseSelect.value ? parseInt(teacherCourseSelect.value) : null;
        const clId = teacherClassSelect.value ? parseInt(teacherClassSelect.value) : null;

        try {
            const res = await fetch("/api/camera/session-filter", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ course_id: cId, class_id: clId })
            });
            const data = await res.json();
            if (data.success) {
                let label = "All Courses / All Classes";
                if (data.filter.course_name && data.filter.class_name) {
                    label = `${data.filter.course_name} / ${data.filter.class_name}`;
                } else if (data.filter.course_name) {
                    label = `${data.filter.course_name} (All Classes)`;
                } else if (data.filter.class_name) {
                    label = `${data.filter.class_name} (All Courses)`;
                }
                if (activeFilterText) activeFilterText.textContent = label;
                showToast("Session Target Active", `Recognition scoped to: ${label}`, "success");
            }
        } catch (err) {
            console.error("Error setting session filter:", err);
            showToast("Filter Error", "Failed to update camera session filter.", "danger");
        }
    });

    // --- Camera Control functions ---
    function setCameraUIState(state) {
        if (typeof state === "boolean") {
            state = state ? "ACTIVE" : "IDLE";
        }
        cameraLifecycleState = state;
        isCameraActive = (state === "ACTIVE");

        if (state === "ACTIVE") {
            btnToggleCamera.disabled = false;
            btnStartCameraPlaceholder.disabled = false;
            cameraStream.classList.add("active");
            cameraPlaceholder.classList.add("hidden");
            liveIndicator.style.display = "flex";
            btnToggleCamera.className = "btn btn-secondary btn-icon";
            btnToggleCameraText.textContent = "Stop Face Recognition";
            
            systemStatusIndicator.className = "status-pulse";
            systemStatusText.textContent = "Camera Stream Active";
            
            // Connect to feed if not already pointing to it
            if (!cameraStream.src || !cameraStream.src.includes("/video_feed")) {
                cameraStream.src = "/video_feed?" + new Date().getTime();
            }
        } else if (state === "INITIALIZING") {
            btnToggleCamera.disabled = true;
            btnStartCameraPlaceholder.disabled = true;
            btnToggleCameraText.textContent = "Starting Camera...";
            systemStatusIndicator.className = "status-pulse warning";
            systemStatusText.textContent = "Initializing Camera...";
        } else if (state === "STOPPING") {
            btnToggleCamera.disabled = true;
            btnStartCameraPlaceholder.disabled = true;
            btnToggleCameraText.textContent = "Stopping Camera...";
            systemStatusIndicator.className = "status-pulse warning";
            systemStatusText.textContent = "Stopping Camera...";
        } else {
            // IDLE or ERROR
            btnToggleCamera.disabled = false;
            btnStartCameraPlaceholder.disabled = false;
            cameraStream.classList.remove("active");
            cameraPlaceholder.classList.remove("hidden");
            liveIndicator.style.display = "none";
            btnToggleCamera.className = "btn btn-primary btn-icon";
            btnToggleCameraText.textContent = "Start Face Recognition";
            
            systemStatusIndicator.className = "status-pulse inactive";
            systemStatusText.textContent = "Camera Stream Halted";
            
            cameraStream.src = "";
        }
    }

    async function checkCameraStatus() {
        try {
            const res = await fetch("/api/camera/status");
            const data = await res.json();
            if (data.camera_active) {
                setCameraUIState("ACTIVE");
            } else {
                setCameraUIState("IDLE");
            }
        } catch (err) {
            console.error("Error checking camera status:", err);
            setCameraUIState("IDLE");
        }
    }

    async function toggleCamera(action) {
        if (cameraLifecycleState === "INITIALIZING" || cameraLifecycleState === "STOPPING") {
            console.log("Camera transition in progress, ignoring duplicate request.");
            return;
        }

        const targetAction = (action === "toggle")
            ? (isCameraActive ? "stop" : "start")
            : action;

        if (targetAction === "start") {
            setCameraUIState("INITIALIZING");
        } else {
            setCameraUIState("STOPPING");
        }

        try {
            const res = await fetch("/api/camera/toggle", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: targetAction })
            });
            const data = await res.json();
            if (data.camera_active) {
                setCameraUIState("ACTIVE");
                showToast("Camera Active", "Face recognition camera has been turned ON.", "success");
            } else {
                setCameraUIState("IDLE");
                showToast("Camera Off", "Face recognition camera has been turned OFF.", "neutral");
            }
        } catch (err) {
            console.error("Camera toggle failed:", err);
            setCameraUIState("IDLE");
            showToast("Camera Error", "Unable to communicate with the camera backend.", "danger");
        }
    }

    btnToggleCamera.addEventListener("click", () => toggleCamera("toggle"));
    btnStartCameraPlaceholder.addEventListener("click", () => toggleCamera("start"));

    // --- Student Directory Functions ---
    async function fetchStudents() {
        try {
            const res = await fetch("/api/students");
            const data = await res.json();
            registeredStudents = data.students;

            // Render warning banner if any training issue
            const warningBanner = document.getElementById("model-training-warning");
            const warningText = document.getElementById("model-training-warning-text");
            if (data.training_error) {
                warningBanner.classList.remove("hidden");
                warningText.textContent = data.training_error;
                
                systemStatusIndicator.className = "status-pulse warning";
                systemStatusText.textContent = "Model Alert: " + data.training_error;
            } else {
                warningBanner.classList.add("hidden");
            }

            renderStudentsGrid();
            
            // Update Dashboard Counters
            statTotalStudents.textContent = data.students.length;
            
        } catch (err) {
            console.error("Failed to load students:", err);
            showToast("Database Error", "Failed to retrieve student directory.", "danger");
        }
    }

    function renderStudentsGrid() {
        const query = studentSearchInput ? studentSearchInput.value.toLowerCase().trim() : "";
        const selectedCourseId = studentCourseFilter ? studentCourseFilter.value : "";
        const selectedClassId = studentClassFilter ? studentClassFilter.value : "";

        const filtered = registeredStudents.filter(s => {
            const matchQuery = !query || 
                (s.name && s.name.toLowerCase().includes(query)) ||
                (s.roll_no && String(s.roll_no).toLowerCase().includes(query));
            
            const matchCourse = !selectedCourseId || String(s.course_id) === String(selectedCourseId);
            const matchClass = !selectedClassId || String(s.class_id) === String(selectedClassId);

            return matchQuery && matchCourse && matchClass;
        });
        
        studentGrid.innerHTML = "";
        
        if (filtered.length === 0) {
            const emptyDiv = document.createElement("div");
            emptyDiv.className = "empty-state";
            emptyDiv.innerHTML = `
                <div class="empty-icon">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
                </div>
                <h3>No Students Found</h3>
                <p>${registeredStudents.length === 0 ? "Get started by adding a student and capturing their face photo." : "No registered students matched your search and filter criteria."}</p>
                <div style="display:flex;gap:8px;margin-top:12px;justify-content:center;">
                    <button type="button" class="btn btn-primary btn-sm" id="btn-add-student-empty">Add Student</button>
                    <button type="button" class="btn btn-secondary btn-sm" id="btn-capture-face-empty">Capture Face</button>
                </div>
            `;
            studentGrid.appendChild(emptyDiv);
            document.getElementById("btn-add-student-empty")?.addEventListener("click", () => openRegisterModal(false));
            document.getElementById("btn-capture-face-empty")?.addEventListener("click", () => openRegisterModal(true));
            return;
        }

        // Group students by Course -> Class
        const grouped = {};
        filtered.forEach(s => {
            const courseKey = s.course_name || "General Course";
            const classKey = s.class_name || "General Class";
            if (!grouped[courseKey]) {
                grouped[courseKey] = {
                    courseName: courseKey,
                    totalCount: 0,
                    classes: {}
                };
            }
            grouped[courseKey].totalCount += 1;
            if (!grouped[courseKey].classes[classKey]) {
                grouped[courseKey].classes[classKey] = [];
            }
            grouped[courseKey].classes[classKey].push(s);
        });

        const container = document.createElement("div");
        container.className = "directory-group-container";

        Object.keys(grouped).forEach(courseName => {
            const courseGroup = grouped[courseName];
            const courseCard = document.createElement("div");
            courseCard.className = "course-group-card";

            courseCard.innerHTML = `
                <div class="course-group-header">
                    <div class="course-group-title">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10v6M2 10l10-5 10 5-10 5z"></path><path d="M6 12v5c3 3 9 3 12 0v-5"></path></svg>
                        <span>${escapeHtml(courseName)}</span>
                    </div>
                    <span class="course-group-badge">${courseGroup.totalCount} ${courseGroup.totalCount === 1 ? 'Student' : 'Students'}</span>
                </div>
                <div class="course-group-body" style="display:flex;flex-direction:column;gap:16px;"></div>
            `;

            const courseBody = courseCard.querySelector(".course-group-body");

            Object.keys(courseGroup.classes).forEach(className => {
                const studentsInClass = courseGroup.classes[className];
                const classCard = document.createElement("div");
                classCard.className = "class-group-card";

                classCard.innerHTML = `
                    <div class="class-group-header">
                        <div class="class-group-title">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
                            <span>${escapeHtml(className)}</span>
                        </div>
                        <span class="class-group-badge">${studentsInClass.length} ${studentsInClass.length === 1 ? 'Student' : 'Students'}</span>
                    </div>
                    <div class="class-student-grid"></div>
                `;

                const grid = classCard.querySelector(".class-student-grid");
                studentsInClass.forEach(student => {
                    const card = document.createElement("div");
                    card.className = "student-card";
                    const safeName = escapeHtml(student.name);
                    const safePhoto = escapeHtml(student.photo_url || '');
                    const safeFilename = escapeHtml(student.filename || '');
                    const safeRoll = escapeHtml(student.roll_no || 'N/A');
                    const safeCourse = escapeHtml(student.course_name || 'General');
                    const safeClass = escapeHtml(student.class_name || 'Standard');
                    card.innerHTML = `
                        <div class="student-photo-wrapper">
                            <img src="${safePhoto}" alt="${safeName}" onerror="this.src='https://placehold.co/200x200?text=No+Photo'">
                        </div>
                        <div class="student-info">
                            <h3>${safeName}</h3>
                            <div style="font-size: 12px; color: var(--accent); margin: 2px 0 4px 0; font-weight: 600;">
                                Roll No: ${safeRoll}
                            </div>
                            <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 6px;">
                                <span>${safeCourse}</span> &bull; <span>${safeClass}</span>
                            </div>
                            <span>Registered: ${escapeHtml((student.registered_at || '').split(' ')[0])}</span>
                            <div class="student-actions">
                                <button class="btn btn-danger btn-sm delete-btn" data-filename="${safeFilename}">
                                    Delete Profile
                                </button>
                            </div>
                        </div>
                    `;
                    grid.appendChild(card);
                });

                courseBody.appendChild(classCard);
            });

            container.appendChild(courseCard);
        });

        studentGrid.appendChild(container);

        // Set up delete event listeners
        studentGrid.querySelectorAll(".delete-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const filename = e.target.getAttribute("data-filename");
                if (confirm(`Are you sure you want to delete this student profile?`)) {
                    deleteStudent(filename);
                }
            });
        });
    }

    async function deleteStudent(filename) {
        try {
            const res = await fetch(`/api/students/${filename}`, { method: "DELETE" });
            const data = await res.json();
            if (data.success) {
                showToast("Profile Deleted", data.message, "success");
                fetchStudents();
                updateDashboardStats();
            } else {
                showToast("Deletion Failed", data.message, "danger");
            }
        } catch (err) {
            showToast("Server Error", "Could not complete deletion request.", "danger");
        }
    }

    studentSearchInput.addEventListener("input", renderStudentsGrid);

    // --- Modal Registration Operations ---
    function openRegisterModal(openCamera = false) {
        const shouldOpenCamera = (typeof openCamera === 'boolean' && openCamera === true);
        registerModal.classList.add("active");
        registerForm.reset();
        clearUploadPreview();
        closeCameraPreview();
        populateClassSelects("", studentClassSelect);

        // Buttons initial state: Start Camera enabled, Capture & Stop disabled
        if (btnOpenCameraLive) btnOpenCameraLive.disabled = false;
        if (btnTakeCameraPhoto) btnTakeCameraPhoto.disabled = true;
        if (btnCloseCameraLive) btnCloseCameraLive.disabled = true;

        if (shouldOpenCamera) {
            openCameraPreview();
        }
    }

    function closeRegisterModal() {
        registerModal.classList.remove("active");
        clearUploadPreview();
        closeCameraPreview();
    }

    function updatePreviewFromBlob(blob) {
        capturedBlob = blob;
        if (activePreviewUrl) {
            URL.revokeObjectURL(activePreviewUrl);
        }
        activePreviewUrl = URL.createObjectURL(blob);
        previewImg.src = activePreviewUrl;
        uploadPlaceholder.classList.add("hidden");
        uploadPreview.classList.remove("hidden");
    }

    function setCameraInstruction(message, warning = false) {
        cameraInstructions.textContent = message;
        cameraInstructions.classList.toggle("warning", warning);
    }

    function stopServerCamera() {
        if (cameraServerStream) {
            cameraServerStream.src = "";
            cameraServerStream.classList.add("hidden");
        }
        if (activeCameraMode === "server") {
            activeCameraMode = "browser";
            fetch("/api/camera/release-lock", { method: "POST" }).catch(() => {});
        }
    }

    async function startServerCamera() {
        activeCameraMode = "server";

        // Stop any browser media stream tracks
        if (localCameraStream) {
            localCameraStream.getTracks().forEach(track => {
                try { track.stop(); } catch(e) {}
            });
            localCameraStream = null;
        }
        if (cameraVideo) {
            try { cameraVideo.pause(); } catch(e) {}
            cameraVideo.srcObject = null;
            cameraVideo.classList.add("hidden");
        }
        if (cameraOverlay) {
            cameraOverlay.classList.add("hidden");
        }

        // Make sure live preview container is shown
        cameraCaptureArea.classList.remove("hidden");
        cameraLiveWrapper.classList.remove("hidden");
        capturedPhotoWrapper.classList.add("hidden");
        cameraControlActions.classList.add("hidden");

        if (cameraServerStream) {
            cameraServerStream.classList.remove("hidden");
            // Set MJPEG source with cache-busting timestamp
            cameraServerStream.src = `/api/camera/registration-feed?t=${Date.now()}`;
        }

        if (btnOpenCameraLive) btnOpenCameraLive.disabled = true;
        if (btnTakeCameraPhoto) btnTakeCameraPhoto.disabled = false;
        if (btnCloseCameraLive) btnCloseCameraLive.disabled = false;
        setCameraInstruction("Hardware Server Webcam active. Position face and click 'Capture Photo'.");
        return true;
    }

    function stopLocalCamera() {
        stopServerCamera();

        if (cameraDetectionFrame) {
            cancelAnimationFrame(cameraDetectionFrame);
            cameraDetectionFrame = null;
        }
        if (localCameraStream) {
            localCameraStream.getTracks().forEach(track => {
                try {
                    track.stop();
                } catch (e) {
                    console.warn("[Camera] Error stopping local track:", e);
                }
            });
            localCameraStream = null;
        }
        if (cameraVideo) {
            try {
                cameraVideo.pause();
            } catch (e) {}
            if (cameraVideo.srcObject && typeof cameraVideo.srcObject.getTracks === "function") {
                cameraVideo.srcObject.getTracks().forEach(track => {
                    try {
                        track.stop();
                    } catch (e) {}
                });
            }
            cameraVideo.srcObject = null;
            cameraVideo.classList.remove("hidden");
        }
        if (cameraOverlay) {
            cameraOverlay.classList.remove("hidden");
        }
        localFaceDetected = false;
        detectionInProgress = false;

        // Reset button states
        if (btnOpenCameraLive) btnOpenCameraLive.disabled = false;
        if (btnTakeCameraPhoto) btnTakeCameraPhoto.disabled = true;
        if (btnCloseCameraLive) btnCloseCameraLive.disabled = true;
    }

    async function startLocalCamera(deviceId = null) {
        if (deviceId === "server-default" || selectedCameraDeviceId === "server-default") {
            return await startServerCamera();
        }

        // 1. Origin & Secure Context Check (HTTPS or localhost required for getUserMedia)
        const isLocalOrigin = location.hostname === "localhost" || location.hostname === "127.0.0.1" || location.hostname === "::1";
        if (!window.isSecureContext && !isLocalOrigin) {
            const secureMsg = `Camera access requires a Secure Context (HTTPS or http://localhost:5000). Current origin (${location.origin}) is insecure HTTP.`;
            console.error("[Camera] Insecure Context Error:", secureMsg);
            showToast("Switching to Server Webcam", "Browser camera requires localhost/HTTPS. Switching to hardware server webcam...", "warning");
            const serverOk = await startServerCamera();
            if (serverOk) {
                if (cameraDeviceSelect) cameraDeviceSelect.value = "server-default";
                return true;
            }
            showToast("HTTPS / Localhost Required", secureMsg, "danger");
            setCameraInstruction("Browser policy blocks camera on non-localhost HTTP. Access via http://localhost:5000 or HTTPS.", true);
            if (btnOpenCameraLive) btnOpenCameraLive.disabled = false;
            return false;
        }

        // 2. MediaDevices API availability
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            const unsuppMsg = "MediaDevices.getUserMedia is not supported or is blocked in this browser environment.";
            console.error("[Camera] Unsupported API:", unsuppMsg);
            showToast("Switching to Server Webcam", "Browser getUserMedia unavailable. Switching to hardware server webcam...", "warning");
            const serverOk = await startServerCamera();
            if (serverOk) {
                if (cameraDeviceSelect) cameraDeviceSelect.value = "server-default";
                return true;
            }
            showToast("Camera Unsupported", unsuppMsg, "danger");
            setCameraInstruction("Camera API not supported in this browser. Try Chrome/Edge on http://localhost:5000.", true);
            if (btnOpenCameraLive) btnOpenCameraLive.disabled = false;
            return false;
        }

        // 3. Permission query check (if supported)
        try {
            if (navigator.permissions && navigator.permissions.query) {
                const permStatus = await navigator.permissions.query({ name: "camera" });
                console.log("[Camera] Permission query state:", permStatus.state);
                if (permStatus.state === "denied") {
                    const deniedMsg = "Camera permission was previously blocked in browser.";
                    console.error("[Camera] Permission Denied Error:", deniedMsg);
                    showToast("Switching to Server Webcam", "Browser camera permission blocked. Switching to hardware server webcam...", "warning");
                    const serverOk = await startServerCamera();
                    if (serverOk) {
                        if (cameraDeviceSelect) cameraDeviceSelect.value = "server-default";
                        return true;
                    }
                    showToast("Camera Permission Denied", "Camera permission blocked. Click lock icon in URL bar to allow.", "danger");
                    setCameraInstruction("Camera permission blocked in browser. Reset in site settings or use server webcam.", true);
                    if (btnOpenCameraLive) btnOpenCameraLive.disabled = false;
                    return false;
                }
            }
        } catch (permErr) {
            console.log("[Camera] Permission status query skipped:", permErr?.message);
        }

        // 4. Multiple camera stream protection: clean up active stream first
        stopLocalCamera();

        // If sidebar feed is running, halt it so hardware is available
        if (isCameraActive) {
            setCameraUIState("IDLE");
        }

        // Disable start button while initializing
        if (btnOpenCameraLive) btnOpenCameraLive.disabled = true;
        if (btnTakeCameraPhoto) btnTakeCameraPhoto.disabled = true;
        if (btnCloseCameraLive) btnCloseCameraLive.disabled = true;
        setCameraInstruction("Initializing camera device...");

        // 5. Release backend lock if attendance video feed was open
        try {
            await fetch("/api/camera/release-lock", { method: "POST" });
            await new Promise(r => setTimeout(r, 150));
        } catch (e) {
            console.warn("[Camera] Could not release backend camera lock:", e);
        }

        // 6. Discover camera devices
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const videoInputs = devices.filter(d => d.kind === "videoinput");
            if (cameraDeviceSelect) {
                const currentVal = deviceId || selectedCameraDeviceId || "browser-default";
                let optionsHtml = `<option value="browser-default" ${currentVal === "browser-default" ? "selected" : ""}>Browser Webcam (Default)</option>`;
                videoInputs.forEach((d, idx) => {
                    optionsHtml += `<option value="${d.deviceId}" ${d.deviceId === currentVal ? "selected" : ""}>${escapeHtml(d.label || `Camera ${idx + 1}`)}</option>`;
                });
                optionsHtml += `<option value="server-default" ${currentVal === "server-default" ? "selected" : ""}>Server Webcam (Direct Hardware)</option>`;
                cameraDeviceSelect.innerHTML = optionsHtml;
            }
        } catch (e) {
            console.warn("[Camera] Device enumeration error:", e);
        }

        const activeDeviceId = (deviceId && deviceId !== "browser-default" && deviceId !== "server-default") ? deviceId : 
                               (selectedCameraDeviceId && selectedCameraDeviceId !== "browser-default" && selectedCameraDeviceId !== "server-default") ? selectedCameraDeviceId : null;

        // 7. Progressive camera constraints with guaranteed fallback
        const constraintCandidates = [];
        if (activeDeviceId) {
            constraintCandidates.push({ video: { deviceId: { exact: activeDeviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
            constraintCandidates.push({ video: { deviceId: { ideal: activeDeviceId }, width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
            constraintCandidates.push({ video: { deviceId: { ideal: activeDeviceId } }, audio: false });
        }
        constraintCandidates.push({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
        constraintCandidates.push({ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
        constraintCandidates.push({ video: true, audio: false });

        let stream = null;
        let lastErr = null;

        for (const constraints of constraintCandidates) {
            try {
                console.log("[Camera] Attempting getUserMedia with constraints:", JSON.stringify(constraints));
                stream = await navigator.mediaDevices.getUserMedia(constraints);
                if (stream) {
                    console.log("[Camera] Successfully obtained stream tracks:", stream.getVideoTracks().map(t => ({ label: t.label, enabled: t.enabled, readyState: t.readyState })));
                    break;
                }
            } catch (err) {
                lastErr = err;
                console.error(`[Camera] getUserMedia failed for constraint:`, constraints, `Error: [${err.name}] ${err.message}`);
                // Stop loop early on permission or security errors since retry will not succeed
                if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError" || err.name === "SecurityError") {
                    break;
                }
            }
        }

        // If NotReadableError occurred, wait 300ms and try one more generic attempt (helps if OpenCV was just released)
        if (!stream && lastErr && (lastErr.name === "NotReadableError" || lastErr.name === "TrackStartError")) {
            console.log("[Camera] Hardware busy, attempting one fallback retry in 300ms...");
            await new Promise(r => setTimeout(r, 300));
            try {
                stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
                if (stream) {
                    console.log("[Camera] Retry successfully obtained stream!");
                }
            } catch (retryErr) {
                console.error(`[Camera] Retry failed: [${retryErr.name}] ${retryErr.message}`);
                lastErr = retryErr;
            }
        }

        if (!stream) {
            console.error(`[Camera Error] Browser camera failed: [${lastErr?.name}] ${lastErr?.message}. Falling back to Server Webcam...`, lastErr);
            let userReason = "Browser camera unavailable";
            if (lastErr) {
                if (lastErr.name === "NotAllowedError" || lastErr.name === "PermissionDeniedError") {
                    userReason = "Permission blocked in browser";
                } else if (lastErr.name === "NotFoundError" || lastErr.name === "DevicesNotFoundError") {
                    userReason = "No browser webcam found";
                } else if (lastErr.name === "NotReadableError" || lastErr.name === "TrackStartError") {
                    userReason = "Webcam busy or in use";
                }
            }

            showToast("Switching to Server Webcam", `${userReason}. Activating hardware server webcam preview...`, "warning");
            const serverStarted = await startServerCamera();
            if (serverStarted) {
                if (cameraDeviceSelect) cameraDeviceSelect.value = "server-default";
                return true;
            }

            // Both failed
            showToast("Camera Error", "Neither browser nor server could access the webcam. Check physical connection.", "danger");
            setCameraInstruction("Could not access webcam. Please check your webcam connection or select an image file to upload.", true);
            if (btnOpenCameraLive) btnOpenCameraLive.disabled = false;
            if (btnTakeCameraPhoto) btnTakeCameraPhoto.disabled = false; // still allow snapshot attempt
            if (btnCloseCameraLive) btnCloseCameraLive.disabled = true;
            return false;
        }

        activeCameraMode = "browser";
        localCameraStream = stream;
        if (cameraVideo) {
            cameraVideo.classList.remove("hidden");
            if (cameraOverlay) cameraOverlay.classList.remove("hidden");
            if (cameraServerStream) cameraServerStream.classList.add("hidden");

            cameraVideo.srcObject = stream;
            cameraVideo.onloadedmetadata = () => {
                updateCameraCanvasSize();
                cameraVideo.play().catch(e => console.warn("[Camera] Video play onloadedmetadata error:", e));
            };
            try {
                await cameraVideo.play();
            } catch (e) {
                console.warn("[Camera] Video play error:", e);
            }
            updateCameraCanvasSize();
        }

        if (btnOpenCameraLive) btnOpenCameraLive.disabled = true;
        if (btnTakeCameraPhoto) btnTakeCameraPhoto.disabled = false;
        if (btnCloseCameraLive) btnCloseCameraLive.disabled = false;
        setCameraInstruction("Camera active. Align face inside the box and click 'Capture Photo'.");
        return true;
    }

    function updateCameraCanvasSize() {
        if (!cameraVideo || !cameraOverlay) return;
        cameraOverlay.width = cameraVideo.videoWidth || 640;
        cameraOverlay.height = cameraVideo.videoHeight || 480;
        cameraOverlay.style.width = "100%";
        cameraOverlay.style.height = "100%";
    }

    function getAverageBrightness() {
        try {
            const ctx = cameraAnalysisCanvas.getContext("2d");
            ctx.drawImage(cameraVideo, 0, 0, cameraAnalysisCanvas.width, cameraAnalysisCanvas.height);
            const imageData = ctx.getImageData(0, 0, cameraAnalysisCanvas.width, cameraAnalysisCanvas.height).data;
            let total = 0;
            let count = 0;
            for (let i = 0; i < imageData.length; i += 4) {
                total += (imageData[i] * 0.299 + imageData[i + 1] * 0.587 + imageData[i + 2] * 0.114);
                count += 1;
            }
            return total / count;
        } catch (err) {
            return null;
        }
    }

    function renderFaceGuide(face, brightness) {
        const ctx = cameraOverlay.getContext("2d");
        const width = cameraOverlay.width;
        const height = cameraOverlay.height;
        ctx.clearRect(0, 0, width, height);

        if (face) {
            ctx.strokeStyle = "#5eead4";
            ctx.lineWidth = 3;
            ctx.strokeRect(face.x, face.y, face.width, face.height);
            ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
            ctx.fillRect(0, 0, width, 34);
            ctx.fillStyle = "#fff";
            ctx.font = "16px Inter, sans-serif";
            ctx.fillText("Face detected. Align it inside the box.", 14, 22);

            const centerX = face.x + face.width / 2;
            const centerY = face.y + face.height / 2;
            const horizontalOffset = Math.abs(centerX - width / 2);
            const verticalOffset = Math.abs(centerY - height / 2);
            const faceRatio = face.width / width;

            if (brightness !== null && brightness < 70) {
                setCameraInstruction("Move to a brighter area.", true);
            } else if (brightness !== null && brightness > 220) {
                setCameraInstruction("Avoid strong backlight.", true);
            } else if (faceRatio < 0.18) {
                setCameraInstruction("Move closer so the face fills more of the frame.", true);
            } else if (faceRatio > 0.55) {
                setCameraInstruction("Move farther away so the face fits better.", true);
            } else if (horizontalOffset > width * 0.14 || verticalOffset > height * 0.14) {
                setCameraInstruction("Keep your face centered in the frame.", true);
            } else {
                setCameraInstruction("Face detected. Keep your face straight and clearly visible.");
            }
            localFaceDetected = true;
        } else {
            ctx.strokeStyle = "rgba(255,255,255,0.55)";
            ctx.lineWidth = 2;
            const padding = 26;
            ctx.setLineDash([8, 6]);
            ctx.strokeRect(padding, padding, width - padding * 2, height - padding * 2);
            ctx.setLineDash([]);
            ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
            ctx.fillRect(0, 0, width, 34);
            ctx.fillStyle = "#fff";
            ctx.font = "16px Inter, sans-serif";
            ctx.fillText("Face not detected yet. Position your face inside the frame.", 14, 22);

            if (brightness !== null && brightness < 70) {
                setCameraInstruction("Move to a brighter area. Keep your face inside the frame.", true);
            } else if (brightness !== null && brightness > 220) {
                setCameraInstruction("Avoid strong backlight and keep the face visible.", true);
            } else {
                setCameraInstruction("Position your face inside the frame.");
            }
            localFaceDetected = false;
        }
    }

    async function runCameraDetectionLoop() {
        if (!cameraLiveWrapper.classList.contains("hidden") && localCameraStream) {
            if (!detectionInProgress && window.FaceDetector) {
                detectionInProgress = true;
                try {
                    if (!faceDetector) {
                        faceDetector = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 1 });
                    }
                    const faces = await faceDetector.detect(cameraVideo);
                    const brightness = getAverageBrightness();
                    const face = faces && faces.length ? faces[0].boundingBox : null;
                    renderFaceGuide(face, brightness);
                } catch (err) {
                    const brightness = getAverageBrightness();
                    renderFaceGuide(null, brightness);
                } finally {
                    detectionInProgress = false;
                }
            } else if (!window.FaceDetector) {
                const brightness = getAverageBrightness();
                renderFaceGuide(null, brightness);
            }
            cameraDetectionFrame = requestAnimationFrame(runCameraDetectionLoop);
        }
    }

    async function openCameraPreview() {
        cameraCaptureArea.classList.remove("hidden");
        cameraLiveWrapper.classList.remove("hidden");
        capturedPhotoWrapper.classList.add("hidden");
        cameraControlActions.classList.add("hidden");
        setCameraInstruction("Opening camera preview... Position face and click Capture Photo.");

        const started = await startLocalCamera();
        if (started) {
            updateCameraCanvasSize();
            runCameraDetectionLoop();
        }
    }

    function closeCameraPreview() {
        cameraCaptureArea.classList.add("hidden");
        cameraLiveWrapper.classList.add("hidden");
        capturedPhotoWrapper.classList.add("hidden");
        cameraControlActions.classList.add("hidden");
        setCameraInstruction("Open the camera and position the face inside the frame before capturing.");
        stopLocalCamera();
    }

    async function captureFromCamera() {
        // Mode 1: Local browser media stream
        if (localCameraStream && !cameraVideo.paused && !cameraVideo.ended) {
            const captureCanvas = document.createElement("canvas");
            captureCanvas.width = cameraVideo.videoWidth || 640;
            captureCanvas.height = cameraVideo.videoHeight || 480;
            const ctx = captureCanvas.getContext("2d");
            ctx.drawImage(cameraVideo, 0, 0, captureCanvas.width, captureCanvas.height);

            // Optional client-side single face validation if FaceDetector API available
            if (window.FaceDetector) {
                try {
                    const detector = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 5 });
                    const detectedFaces = await detector.detect(captureCanvas);
                    if (!detectedFaces || detectedFaces.length === 0) {
                        showToast("No Face Detected", "No face detected. Please position your face inside the camera frame.", "danger");
                        setCameraInstruction("No face detected. Please position your face inside the camera frame.", true);
                        return;
                    } else if (detectedFaces.length > 1) {
                        showToast("Multiple Faces", "Multiple faces detected. Please ensure only one student is visible.", "danger");
                        setCameraInstruction("Multiple faces detected. Please ensure only one student is visible.", true);
                        return;
                    }
                } catch (e) {
                    // Fall back to server-side SFace validation
                }
            }

            const dataUrl = captureCanvas.toDataURL("image/jpeg", 0.95);
            pendingCaptureDataUrl = dataUrl;
            capturedPhotoImg.src = dataUrl;

            captureCanvas.toBlob(blob => {
                capturedBlob = blob;
            }, "image/jpeg", 0.95);

            cameraLiveWrapper.classList.add("hidden");
            capturedPhotoWrapper.classList.remove("hidden");
            cameraControlActions.classList.remove("hidden");

            // Requirement 8: Stop camera immediately after photo is captured
            stopLocalCamera();

            setCameraInstruction("Photo captured! Click 'Use This Photo' to confirm or 'Retake' to try again.", false);
            return;
        }

        // Mode 2: Server-side camera snapshot fallback if browser stream not active
        try {
            setCameraInstruction("Capturing snapshot from camera...");
            const res = await fetch("/api/camera/snapshot");
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.message || "Failed to capture snapshot from webcam.");
            }
            const blob = await res.blob();
            capturedBlob = blob;

            const reader = new FileReader();
            reader.onload = (e) => {
                pendingCaptureDataUrl = e.target.result;
                capturedPhotoImg.src = e.target.result;
                cameraCaptureArea.classList.remove("hidden");
                cameraLiveWrapper.classList.add("hidden");
                capturedPhotoWrapper.classList.remove("hidden");
                cameraControlActions.classList.remove("hidden");
                stopLocalCamera();
                setCameraInstruction("Webcam photo captured! Click 'Use This Photo' to confirm or 'Retake' to try again.", false);
                showToast("Photo Captured", "Webcam photo ready for preview.", "success");
            };
            reader.readAsDataURL(blob);
        } catch (err) {
            console.error("Camera capture error:", err);
            showToast("Capture Error", err.message || "Could not capture frame from webcam.", "danger");
            setCameraInstruction("Capture failed. Make sure camera is active.", true);
        }
    }

    async function useCapturedPhoto() {
        if (!pendingCaptureDataUrl && !capturedBlob) {
            showToast("No Photo", "Capture an image before using it.", "danger");
            return;
        }

        if (!capturedBlob && pendingCaptureDataUrl) {
            const response = await fetch(pendingCaptureDataUrl);
            capturedBlob = await response.blob();
        }

        if (activePreviewUrl) {
            URL.revokeObjectURL(activePreviewUrl);
        }
        activePreviewUrl = URL.createObjectURL(capturedBlob);
        previewImg.src = activePreviewUrl;
        uploadPlaceholder.classList.add("hidden");
        uploadPreview.classList.remove("hidden");

        setCameraInstruction("Captured photo saved. Enter student details and submit.");
        closeCameraPreview();
        showToast("Photo Selected", "Webcam photo ready for registration.", "success");
    }

    async function retakeCameraPhoto() {
        capturedBlob = null;
        pendingCaptureDataUrl = null;
        capturedPhotoWrapper.classList.add("hidden");
        cameraControlActions.classList.add("hidden");
        await openCameraPreview();
    }

    function clearUploadPreview() {
        uploadPreview.classList.add("hidden");
        uploadPlaceholder.classList.remove("hidden");
        previewImg.src = "";
        fileInput.value = "";
        capturedBlob = null;
        if (activePreviewUrl) {
            URL.revokeObjectURL(activePreviewUrl);
            activePreviewUrl = null;
        }
    }

    btnOpenRegisterModal.addEventListener("click", () => openRegisterModal(false));
    btnCaptureFace?.addEventListener("click", () => openRegisterModal(true));
    btnOpenCameraRegister?.addEventListener("click", () => openRegisterModal(true));
    btnCloseModal.addEventListener("click", closeRegisterModal);
    btnCancelModal.addEventListener("click", closeRegisterModal);

    // Close modal when clicking on dark backdrop overlay or pressing Escape
    registerModal?.addEventListener("click", (e) => {
        if (e.target === registerModal) {
            closeRegisterModal();
        }
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && registerModal?.classList.contains("active")) {
            closeRegisterModal();
        }
    });

    window.addEventListener("beforeunload", () => {
        stopLocalCamera();
    });

    // File Drag & Drop preview logic
    uploadArea.addEventListener("dragover", (e) => {
        e.preventDefault();
        uploadArea.classList.add("dragover");
    });
    uploadArea.addEventListener("dragleave", () => {
        uploadArea.classList.remove("dragover");
    });
    uploadArea.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadArea.classList.remove("dragover");
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length) {
            handleFileSelect(e.target.files[0]);
        }
    });

    btnOpenCameraLive?.addEventListener("click", openCameraPreview);
    btnTakeCameraPhoto?.addEventListener("click", captureFromCamera);
    btnCloseCameraLive?.addEventListener("click", closeCameraPreview);
    btnClearCapturePhoto?.addEventListener("click", () => {
        clearUploadPreview();
        closeCameraPreview();
    });
    btnRetakePhoto?.addEventListener("click", retakeCameraPhoto);
    btnUsePhoto?.addEventListener("click", useCapturedPhoto);

    cameraDeviceSelect?.addEventListener("change", async (e) => {
        selectedCameraDeviceId = e.target.value;
        if (selectedCameraDeviceId === "server-default") {
            await startServerCamera();
        } else {
            await startLocalCamera(selectedCameraDeviceId === "browser-default" ? null : selectedCameraDeviceId);
        }
    });

    function handleFileSelect(file) {
        if (!file.type.startsWith("image/")) {
            showToast("File Error", "Please select a valid image file (JPG, PNG).", "danger");
            return;
        }
        capturedBlob = null;
        const reader = new FileReader();
        reader.onload = (e) => {
            if (activePreviewUrl) {
                URL.revokeObjectURL(activePreviewUrl);
                activePreviewUrl = null;
            }
            previewImg.src = e.target.result;
            uploadPlaceholder.classList.add("hidden");
            uploadPreview.classList.remove("hidden");
        };
        reader.readAsDataURL(file);
    }

    btnRemovePreview.addEventListener("click", (e) => {
        e.stopPropagation();
        clearUploadPreview();
    });

    registerForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const rollVal = (document.getElementById("student-roll-no")?.value || "").trim();
        const nameVal = (document.getElementById("student-name")?.value || "").trim();
        const courseVal = document.getElementById("student-course")?.value;
        const classVal = document.getElementById("student-class")?.value;
        const file = fileInput.files[0];
        const imageSource = capturedBlob || file;

        if (!rollVal) {
            showToast("Validation Error", "Please enter a valid Student Roll Number.", "danger");
            document.getElementById("student-roll-no")?.focus();
            return;
        }
        if (!nameVal) {
            showToast("Validation Error", "Please enter Student Full Name.", "danger");
            document.getElementById("student-name")?.focus();
            return;
        }
        if (!courseVal) {
            showToast("Validation Error", "Please select a Course.", "danger");
            document.getElementById("student-course")?.focus();
            return;
        }
        if (!classVal) {
            showToast("Validation Error", "Please select a Class / Year.", "danger");
            document.getElementById("student-class")?.focus();
            return;
        }
        if (!imageSource) {
            showToast("Validation Error", "Please upload or capture a student face photo.", "danger");
            return;
        }

        // Show spinner / loading state
        btnSubmitRegistration.disabled = true;
        registrationSpinner.classList.remove("hidden");

        const formData = new FormData();
        formData.append("roll_no", rollVal);
        formData.append("name", nameVal);
        formData.append("course_id", courseVal);
        formData.append("class_id", classVal);
        if (capturedBlob) {
            formData.append("image", capturedBlob, "camera-capture.jpg");
        } else {
            formData.append("image", file);
        }

        try {
            const res = await fetch("/api/students", {
                method: "POST",
                body: formData
            });
            const data = await res.json();
            
            if (data.success) {
                showToast("Student Registered", data.message, "success");
                closeRegisterModal();
                fetchStudents();
                updateDashboardStats();
            } else {
                showToast("Registration Failed", data.message || "Failed to register student.", "danger");
            }
        } catch (err) {
            showToast("Server Error", "An error occurred during submission.", "danger");
        } finally {
            btnSubmitRegistration.disabled = false;
            registrationSpinner.classList.add("hidden");
        }
    });

    // --- Historical Logs Filtering & Display ---
    async function fetchAttendanceLogs() {
        try {
            const res = await fetch("/api/attendance");
            const data = await res.json();
            attendanceLogs = data.records;
            renderLogsTable();
        } catch (err) {
            console.error("Failed to fetch attendance logs:", err);
            showToast("Error loading logs", "Unable to load attendance data.", "danger");
        }
    }

    function renderLogsTable() {
        const query = logSearchInput.value.toLowerCase().trim();
        const dateVal = logDateFilter.value; // YYYY-MM-DD
        const courseVal = logCourseFilter ? logCourseFilter.value : "";
        const classVal = logClassFilter ? logClassFilter.value : "";
        
        let filtered = attendanceLogs;
        
        if (query) {
            filtered = filtered.filter(l => 
                (l.name && l.name.toLowerCase().includes(query)) ||
                (l.roll_no && String(l.roll_no).toLowerCase().includes(query))
            );
        }
        if (dateVal) {
            filtered = filtered.filter(l => l.date === dateVal);
        }
        if (courseVal) {
            filtered = filtered.filter(l => 
                String(l.course_id) === String(courseVal) ||
                (availableCourses.find(c => String(c.id) === String(courseVal))?.name === l.course_name)
            );
        }
        if (classVal) {
            filtered = filtered.filter(l => 
                String(l.class_id) === String(classVal) ||
                (availableClasses.find(cl => String(cl.id) === String(classVal))?.name === l.class_name)
            );
        }

        attendanceTableBody.innerHTML = "";
        
        if (filtered.length === 0) {
            logsEmptyState.classList.remove("hidden");
            return;
        }
        
        logsEmptyState.classList.add("hidden");
        
        filtered.forEach((log) => {
            const row = document.createElement("tr");
            const safeRoll = escapeHtml(log.roll_no || 'N/A');
            const safeName = escapeHtml(log.name || 'Unknown');
            const safeClass = escapeHtml(log.class_name || 'Standard');
            const safeCourse = escapeHtml(log.course_name || 'General');
            const safeDate = escapeHtml(log.date || '');
            const safeTime = escapeHtml(log.time || '');
            const safeStatus = escapeHtml(log.status || 'Present');
            const safeRecStatus = escapeHtml(log.recognition_status || 'Recognized');
            row.innerHTML = `
                <td class="col-roll" title="${safeRoll}" style="font-weight:600; color: var(--accent);">${safeRoll}</td>
                <td class="col-name" title="${safeName}" style="font-weight:600; color: white;">${safeName}</td>
                <td class="col-class" title="${safeClass}">${safeClass}</td>
                <td class="col-course" title="${safeCourse}">${safeCourse}</td>
                <td class="col-date">${safeDate}</td>
                <td class="col-time">${safeTime}</td>
                <td class="col-status"><span class="badge" style="background: var(--status-present-bg); color: var(--status-present);">${safeStatus}</span></td>
                <td class="col-rec"><span class="badge" title="${safeRecStatus}" style="background: rgba(99, 102, 241, 0.15); color: var(--accent); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block;">${safeRecStatus}</span></td>
            `;
            attendanceTableBody.appendChild(row);
        });
    }

    logSearchInput.addEventListener("input", renderLogsTable);
    logDateFilter.addEventListener("change", renderLogsTable);
    
    btnClearDateFilter.addEventListener("click", () => {
        logSearchInput.value = "";
        logDateFilter.value = "";
        if (logCourseFilter) logCourseFilter.value = "";
        if (logClassFilter) {
            populateClassSelects("", logClassFilter);
            logClassFilter.value = "";
        }
        renderLogsTable();
    });

    btnClearLogs.addEventListener("click", async () => {
        if (confirm("Are you sure you want to permanently delete all historical attendance records? This cannot be undone.")) {
            try {
                const res = await fetch("/api/attendance", { method: "DELETE" });
                const data = await res.json();
                if (data.success) {
                    showToast("Logs Cleared", data.message, "success");
                    fetchAttendanceLogs();
                    updateDashboardStats();
                    // Clear session logs too
                    liveLogsContainer.innerHTML = "";
                    liveLogsContainer.appendChild(liveLogsEmpty);
                    liveLogsEmpty.style.display = "flex";
                    sessionCountBadge.textContent = "0 Logs";
                    sessionLogsCount = 0;
                } else {
                    showToast("Action Failed", data.message, "danger");
                }
            } catch (err) {
                showToast("Error resetting logs", "Server error resetting CSV log database.", "danger");
            }
        }
    });

    // --- Dashboard Metrics & Background Polling ---
    async function updateDashboardStats() {
        try {
            const res = await fetch("/api/stats");
            const stats = await res.json();
            
            // Dashboard counters
            statTotalStudents.textContent = stats.total_students;
            statPresentToday.textContent = stats.total_present_today;
            statAbsentToday.textContent = stats.total_absent_today;
            statLastActive.textContent = stats.last_active || stats.last_student || "N/A";

            // Analytics values
            analyticsPresentCount.textContent = stats.total_present_today;
            analyticsAbsentCount.textContent = stats.total_absent_today;
            analyticsTotalCount.textContent = stats.total_students;
            analyticsPercentage.textContent = `${stats.attendance_rate}%`;

            updateAnalyticsRing();

        } catch (err) {
            console.error("Error polling metrics stats:", err);
        }
    }

    function updateAnalyticsRing() {
        if (!progressRing || !analyticsPercentage) return;
        const percentText = analyticsPercentage.textContent;
        const percent = parseInt(percentText) || 0;
        
        // Circular ring calculation
        const radius = progressRing.r.baseVal.value;
        const circumference = radius * 2 * Math.PI;
        const offset = circumference - (percent / 100) * circumference;
        
        progressRing.style.strokeDasharray = `${circumference} ${circumference}`;
        progressRing.style.strokeDashoffset = offset;
    }

    async function pollLiveLogs() {
        if (!isCameraActive) return;

        // 1. Poll real-time stream events for live feedback & overlay positioning
        try {
            const eventRes = await fetch(`/api/camera/stream-events?since=${lastProcessedEventTime}`);
            if (eventRes.ok) {
                const eventData = await eventRes.json();
                const events = eventData.events || [];
                events.forEach(ev => {
                    if (ev.timestamp && ev.timestamp > lastProcessedEventTime) {
                        lastProcessedEventTime = Math.max(lastProcessedEventTime, ev.timestamp);

                        console.log(`[ATTENDANCE-CHAIN] Step 5: Real-time UI event received [${ev.type}] for '${ev.name}' (Roll: ${ev.roll_no}) [${ev.confidence}%]`);

                        if (ev.type === "marked") {
                            playSuccessChime();
                            showToast("Attendance Marked", `${escapeHtml(ev.name)} (Roll: ${escapeHtml(ev.roll_no)}) marked PRESENT [${ev.confidence}%].`, "success");
                            updateDashboardStats();
                        } else if (ev.type === "already_marked") {
                            const nowMs = Date.now();
                            const lastToast = alreadyMarkedToastCooldown[ev.name] || 0;
                            if (nowMs - lastToast > 12000) {
                                alreadyMarkedToastCooldown[ev.name] = nowMs;
                                showToast("Already Marked", `${escapeHtml(ev.name)} (Roll: ${escapeHtml(ev.roll_no)}) is already marked PRESENT for today.`, "info");
                            }
                        } else if (ev.type === "error") {
                            showToast("Attendance Error", escapeHtml(ev.message || "Failed to record attendance in database."), "danger");
                        }
                    }
                });
            }
        } catch (eventErr) {
            console.warn("[ATTENDANCE-CHAIN] Stream events sync skipped:", eventErr);
        }

        // 2. Poll /api/attendance for table and session logs
        try {
            const res = await fetch("/api/attendance");
            if (!res.ok) {
                console.error("[ATTENDANCE-CHAIN] /api/attendance returned HTTP", res.status);
                if (res.status === 401) {
                    showToast("Session Expired", "Please log in again to continue recording attendance.", "danger");
                }
                return;
            }

            const data = await res.json();
            const allLogs = data.records || [];

            if (allLogs.length === 0) return;

            // Detect new attendance items since last check
            let newRecords = [];
            
            // Reverse loop to check chronologically (oldest to newest)
            for (let i = allLogs.length - 1; i >= 0; i--) {
                const log = allLogs[i];
                const uid = `${log.name}_${log.date}_${log.time}`;
                
                if (!knownLogIds.has(uid)) {
                    knownLogIds.add(uid);
                    newRecords.push(log);
                }
            }

            if (newRecords.length > 0) {
                // If it is the very first page load, we just populate the cache without playing notification chime
                if (initialLoad) {
                    initialLoad = false;
                    return;
                }

                console.log(`[ATTENDANCE-CHAIN] Step 5: Adding ${newRecords.length} new log(s) to Marked Attendance (Session)`);

                // Add elements to the Session logs list
                newRecords.forEach(log => {
                    sessionLogsCount++;
                    sessionCountBadge.textContent = `${sessionLogsCount} Logs`;
                    
                    // Hide empty placeholder
                    if (liveLogsEmpty) {
                        liveLogsEmpty.style.display = "none";
                    }

                    const logEl = document.createElement("div");
                    logEl.className = "log-item";
                    
                    const safeName = escapeHtml(log.name || 'Unknown');
                    const safeRoll = escapeHtml(log.roll_no || 'N/A');
                    const safeCourse = escapeHtml(log.course_name || '');
                    const safeClass = escapeHtml(log.class_name || '');
                    const initials = (log.name || 'Unknown').split(' ').map(n => n[0]).join('').substring(0, 2);
                    
                    logEl.innerHTML = `
                        <div class="log-left">
                            <div class="log-avatar">${escapeHtml(initials)}</div>
                            <div class="log-info">
                                <h4>${safeName} <span style="font-size: 11px; color: var(--accent); font-weight: 600;">(Roll: ${safeRoll})</span></h4>
                                <span>${safeCourse ? safeCourse + ' • ' : ''}${safeClass ? safeClass + ' • ' : ''}Logged: ${escapeHtml(log.time || '')}</span>
                            </div>
                        </div>
                        <div class="log-right">
                            <span class="badge" style="background: var(--status-present-bg); color: var(--status-present);">Present</span>
                        </div>
                    `;
                    
                    // Insert at top of session logs container
                    liveLogsContainer.insertBefore(logEl, liveLogsContainer.firstChild);
                    
                    // Trigger sound chime & toast notice if not already fired by real-time event
                    playSuccessChime();
                    showToast("Attendance Marked", `${safeName} (Roll: ${safeRoll}) has been marked PRESENT.`, "success");
                });

                // Update counts immediately
                updateDashboardStats();
            }

        } catch (err) {
            console.error("[ATTENDANCE-CHAIN] Error polling attendance logs:", err);
        }
    }

    // --- Logout Handler ---
    async function handleLogout() {
        if (confirm("Are you sure you want to sign out?")) {
            try {
                // Ensure all client and backend cameras are completely stopped
                stopLocalCamera();
                if (cameraStream) {
                    cameraStream.src = "";
                }
                setCameraUIState("IDLE");

                await fetch("/api/camera/toggle", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ action: "stop" })
                }).catch(() => {});

                await fetch("/api/logout", { method: "POST" });
                showToast("Signed Out", "You have been logged out successfully.", "success");
                setTimeout(() => {
                    window.location.replace("/login");
                }, 500);
            } catch (err) {
                showToast("Logout Error", "Unable to sign out. Please try again.", "danger");
            }
        }
    }

    btnLogout?.addEventListener("click", handleLogout);

    // --- App Initialization ---
    async function init() {
        // Initial setup
        await checkCameraStatus();
        await fetchAcademicData();
        await fetchStudents();
        await updateDashboardStats();
        
        // Cache initial attendance logs so we don't treat them as "new marks"
        try {
            const res = await fetch("/api/attendance");
            const data = await res.json();
            data.records.forEach(log => {
                const uid = `${log.name}_${log.date}_${log.time}`;
                knownLogIds.add(uid);
            });
        } catch (e) {
            console.error("Failed to load initial records:", e);
        }

        initialLoad = false;

        // Start background polling intervals
        // Poll for dashboard metrics every 5 seconds
        setInterval(updateDashboardStats, 5000);
        
        // Poll for new live attendance records scan every 2 seconds
        setInterval(pollLiveLogs, 2000);
    }

    init();
});
