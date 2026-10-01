/**
 * AttendAI Centralized AI Chatbot Controller
 * Provides seamless, role-aware AI interactions across Teacher, Faculty, Student, and Admin portals.
 */

(function() {
    'use strict';

    // State
    let conversationId = sessionStorage.getItem('attendai_chat_conv_id') || '';
    let currentUserRole = 'student';
    let currentUserName = 'User';
    let isConfigured = true;
    let isSending = false;
    let isOpen = false;

    // DOM References
    let launcherBtn, chatWindow, closeBtn, newBtn, clearBtn, sendBtn, inputEl;
    let messagesContainer, chipsContainer, typingIndicator, alertBanner;
    let roleBadgeEl, modelPillEl;

    // Role-specific suggested questions
    const SUGGESTIONS_BY_ROLE = {
        admin: [
            "How many students are registered?",
            "Show available courses",
            "How many teachers are registered?",
            "How does student registration work?",
            "Show today's attendance summary"
        ],
        teacher: [
            "How many students are present today?",
            "Show today's attendance",
            "How does face recognition attendance work?",
            "How do I register a student?",
            "What is today's attendance rate?"
        ],
        faculty: [
            "Show my assigned classes",
            "How many students are in my department?",
            "Show today's attendance",
            "What is the department attendance rate?"
        ],
        student: [
            "What is my attendance?",
            "What course am I registered in?",
            "What is my roll number?",
            "How can I check my attendance?",
            "Is my face registered for attendance?"
        ]
    };

    /**
     * Escape HTML special characters to prevent XSS.
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Parse lightweight Markdown safely into formatted HTML.
     */
    function parseMarkdown(rawText) {
        if (!rawText) return '';
        let escaped = escapeHtml(rawText);

        // Code blocks: ```code```
        escaped = escaped.replace(/```([\s\S]*?)```/g, (match, p1) => {
            return `<pre><code>${p1.trim()}</code></pre>`;
        });

        // Inline code: `code`
        escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Bold: **text**
        escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Italic: *text*
        escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        // Process line by line for bullet points and lists
        const lines = escaped.split('\n');
        let inList = false;
        let formattedLines = [];

        for (let line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                if (!inList) {
                    inList = true;
                    formattedLines.push('<ul>');
                }
                formattedLines.push(`<li>${trimmed.substring(2)}</li>`);
            } else {
                if (inList) {
                    inList = false;
                    formattedLines.push('</ul>');
                }
                if (trimmed.length > 0) {
                    formattedLines.push(`<p>${line}</p>`);
                }
            }
        }
        if (inList) {
            formattedLines.push('</ul>');
        }

        return formattedLines.join('');
    }

    /**
     * Format a timestamp into clean HH:MM string.
     */
    function formatTime(isoStr) {
        const date = isoStr ? new Date(isoStr) : new Date();
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    /**
     * Initialize DOM elements and bind event listeners.
     */
    function init() {
        launcherBtn = document.getElementById('chatbot-launcher-btn');
        chatWindow = document.getElementById('chatbot-window');
        closeBtn = document.getElementById('chatbot-btn-close');
        newBtn = document.getElementById('chatbot-btn-new');
        clearBtn = document.getElementById('chatbot-btn-clear');
        sendBtn = document.getElementById('chatbot-btn-send');
        inputEl = document.getElementById('chatbot-input');
        messagesContainer = document.getElementById('chatbot-messages');
        chipsContainer = document.getElementById('chatbot-chips-list');
        typingIndicator = document.getElementById('chatbot-typing-indicator');
        alertBanner = document.getElementById('chatbot-alert-banner');
        roleBadgeEl = document.getElementById('chatbot-role-badge');
        modelPillEl = document.getElementById('chatbot-model-pill');

        if (!launcherBtn || !chatWindow) {
            console.warn('[AttendAI Chatbot] Required DOM elements not found.');
            return;
        }

        // Event listeners
        launcherBtn.addEventListener('click', toggleChatbot);
        if (closeBtn) closeBtn.addEventListener('click', closeChatbot);
        if (newBtn) newBtn.addEventListener('click', startNewChat);
        if (clearBtn) clearBtn.addEventListener('click', clearCurrentChat);
        if (sendBtn) sendBtn.addEventListener('click', sendMessage);

        if (inputEl) {
            inputEl.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });

            inputEl.addEventListener('input', function() {
                // Auto resize
                inputEl.style.height = 'auto';
                inputEl.style.height = Math.min(inputEl.scrollHeight, 80) + 'px';
                // Toggle send button state
                if (sendBtn) {
                    sendBtn.disabled = !inputEl.value.trim() || isSending;
                }
            });
        }

        // Close on Escape
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && isOpen) {
                closeChatbot();
            }
        });

        // Load configuration and history
        fetchChatConfig();
    }

    /**
     * Fetch public chatbot configuration and user identity.
     */
    async function fetchChatConfig() {
        try {
            const res = await fetch('/api/chat/config');
            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    currentUserRole = (data.role || 'student').toLowerCase();
                    currentUserName = data.user_name || 'User';
                    isConfigured = data.configured !== false;

                    updateRoleUI(currentUserRole, currentUserName, data.model);
                    renderSuggestions(currentUserRole);

                    if (!isConfigured) {
                        showAlert("AI Assistant is offline (API key not configured in .env).");
                    }
                }
            } else if (res.status === 401) {
                // Not logged in or session expired
                console.info('[AttendAI Chatbot] User is not authenticated.');
            }
        } catch (e) {
            console.warn('[AttendAI Chatbot] Config load error:', e);
        }

        // Load existing history if available
        if (conversationId) {
            loadConversationHistory(conversationId);
        } else {
            renderWelcome();
        }
    }

    /**
     * Update header UI with role and model indicators.
     */
    function updateRoleUI(role, name, model) {
        if (roleBadgeEl) {
            roleBadgeEl.textContent = role.toUpperCase();
            roleBadgeEl.className = `role-pill ${role}`;
        }
        if (modelPillEl && model) {
            modelPillEl.textContent = model;
        }
    }

    /**
     * Render role-tailored suggestion chips.
     */
    function renderSuggestions(role) {
        if (!chipsContainer) return;
        chipsContainer.innerHTML = '';
        const list = SUGGESTIONS_BY_ROLE[role] || SUGGESTIONS_BY_ROLE['student'];

        list.forEach(promptText => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'chip-btn';
            btn.textContent = promptText;
            btn.addEventListener('click', () => {
                if (inputEl) {
                    inputEl.value = promptText;
                    inputEl.style.height = 'auto';
                    inputEl.style.height = Math.min(inputEl.scrollHeight, 80) + 'px';
                    if (sendBtn) sendBtn.disabled = false;
                    sendMessage();
                }
            });
            chipsContainer.appendChild(btn);
        });
    }

    /**
     * Render welcome message when conversation is empty.
     */
    function renderWelcome() {
        if (!messagesContainer) return;
        messagesContainer.innerHTML = `
            <div class="chatbot-welcome-card">
                <p>Hello <strong>${escapeHtml(currentUserName)}</strong>! I am your <strong>AttendAI Assistant</strong>.</p>
                <p>Ask me questions about attendance records, face recognition scanning, class rosters, or system instructions. Your responses are grounded in real-time AttendAI data.</p>
            </div>
        `;
    }

    /**
     * Load previous messages for the active conversation.
     */
    async function loadConversationHistory(convId) {
        try {
            const res = await fetch(`/api/chat/history?conversation_id=${encodeURIComponent(convId)}`);
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.messages && data.messages.length > 0) {
                    messagesContainer.innerHTML = '';
                    data.messages.forEach(msg => {
                        appendMessage(msg.sender, msg.message, msg.timestamp, false);
                    });
                    scrollToBottom();
                    return;
                }
            }
        } catch (e) {
            console.warn('[AttendAI Chatbot] History fetch error:', e);
        }
        renderWelcome();
    }

    /**
     * Toggle Chatbot Window visibility.
     */
    function toggleChatbot() {
        if (isOpen) {
            closeChatbot();
        } else {
            openChatbot();
        }
    }

    function openChatbot() {
        chatWindow.classList.remove('hidden');
        isOpen = true;
        if (inputEl) {
            setTimeout(() => inputEl.focus(), 150);
        }
        scrollToBottom();
    }

    function closeChatbot() {
        chatWindow.classList.add('hidden');
        isOpen = false;
    }

    /**
     * Show notification alert banner.
     */
    function showAlert(msg) {
        if (!alertBanner) return;
        alertBanner.textContent = msg;
        alertBanner.classList.remove('hidden');
    }

    function hideAlert() {
        if (!alertBanner) return;
        alertBanner.classList.add('hidden');
    }

    /**
     * Scroll messages viewport to bottom.
     */
    function scrollToBottom() {
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    /**
     * Append a message row to the messages container.
     */
    function appendMessage(sender, text, timestamp = null, scroll = true) {
        if (!messagesContainer) return;

        const row = document.createElement('div');
        row.className = `chat-message-row ${sender}`;

        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble';

        if (sender === 'assistant') {
            bubble.innerHTML = parseMarkdown(text);
        } else {
            bubble.textContent = text;
        }

        const timeSpan = document.createElement('span');
        timeSpan.className = 'msg-time';
        timeSpan.textContent = formatTime(timestamp);
        bubble.appendChild(timeSpan);

        row.appendChild(bubble);
        messagesContainer.appendChild(row);

        if (scroll) {
            scrollToBottom();
        }
    }

    /**
     * Send message to centralized POST /api/chat endpoint.
     */
    async function sendMessage() {
        if (isSending || !inputEl) return;
        const text = inputEl.value.trim();
        if (!text) return;

        // Clear and reset input field
        inputEl.value = '';
        inputEl.style.height = 'auto';
        if (sendBtn) sendBtn.disabled = true;
        hideAlert();

        // Optimistically append user message
        appendMessage('user', text);
        isSending = true;

        // Show typing indicator
        if (typingIndicator) {
            typingIndicator.classList.remove('hidden');
            scrollToBottom();
        }

        try {
            const payload = {
                message: text,
                conversation_id: conversationId || undefined
            };

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (data.conversation_id) {
                conversationId = data.conversation_id;
                sessionStorage.setItem('attendai_chat_conv_id', conversationId);
            }

            if (response.ok && data.success) {
                appendMessage('assistant', data.message);
            } else {
                const errMsg = data.message || 'Unable to process your request at this moment.';
                appendMessage('assistant', `⚠️ ${errMsg}`);
                if (response.status === 429) {
                    showAlert("Rate limit reached. Please wait a moment before sending more queries.");
                } else if (response.status === 503) {
                    showAlert("AI Assistant is offline. Please verify AI_API_KEY settings.");
                }
            }
        } catch (err) {
            console.error('[AttendAI Chatbot] Send error:', err);
            appendMessage('assistant', '⚠️ Connection to AI service failed. Please verify network and server connectivity.');
        } finally {
            isSending = false;
            if (typingIndicator) {
                typingIndicator.classList.add('hidden');
            }
            if (sendBtn) {
                sendBtn.disabled = !inputEl.value.trim();
            }
            scrollToBottom();
        }
    }

    /**
     * Start a fresh new chat session.
     */
    async function startNewChat() {
        try {
            const res = await fetch('/api/chat/new', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    conversationId = data.conversation_id;
                    sessionStorage.setItem('attendai_chat_conv_id', conversationId);
                }
            }
        } catch (e) {
            conversationId = 'conv_' + Date.now();
            sessionStorage.setItem('attendai_chat_conv_id', conversationId);
        }

        hideAlert();
        renderWelcome();
    }

    /**
     * Clear messages for current conversation.
     */
    async function clearCurrentChat() {
        if (!conversationId) {
            renderWelcome();
            return;
        }

        if (!confirm("Are you sure you want to clear this conversation?")) {
            return;
        }

        try {
            await fetch('/api/chat/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conversation_id: conversationId })
            });
        } catch (e) {
            console.warn('[AttendAI Chatbot] Clear error:', e);
        }

        renderWelcome();
    }

    // Auto initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
