// chat.js — handles chat, participants rendering, and resume-position tracking

document.addEventListener("DOMContentLoaded", function () {

    // ── DOM ───────────────────────────────────────────────────────────────
    const chatContainer   = document.getElementById("chat-container");
    if (!chatContainer) return;

    const roomId          = chatContainer.dataset.roomId;
    const chatMessages    = document.getElementById("chat-messages");
    const chatForm        = document.getElementById("chat-form");
    const chatInput       = document.getElementById("chat-input");
    const participantsList = document.getElementById("participants-list");

    // ── Helpers ───────────────────────────────────────────────────────────
    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    /** Format seconds → "H:MM:SS" or "M:SS" */
    function formatDuration(secs) {
        const s = Math.floor(secs);
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        const sec = s % 60;
        if (h > 0) return `${h}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
        return `${m}:${String(sec).padStart(2,"0")}`;
    }

    function formatTime(date) {
        return `${String(date.getHours()).padStart(2,"0")}:${String(date.getMinutes()).padStart(2,"0")}`;
    }

    // ── Resume position (localStorage) ───────────────────────────────────
    const RESUME_KEY = `room_position_${roomId}`;

    function savePosition(time, label) {
        if (!time || time < 5) return;
        const data = { time, label: label || null, savedAt: Date.now() };
        try { localStorage.setItem(RESUME_KEY, JSON.stringify(data)); } catch(e) {}
    }

    function loadPosition() {
        try {
            const raw = localStorage.getItem(RESUME_KEY);
            if (!raw) return null;
            return JSON.parse(raw);
        } catch(e) { return null; }
    }

    // Show resume banner inside the room if we have a saved position
    function showResumeBanner() {
        const pos = loadPosition();
        if (!pos || pos.time < 5) return;

        // Don't show if saved more than 7 days ago
        if (Date.now() - pos.savedAt > 7 * 24 * 3600 * 1000) return;

        const banner = document.createElement("div");
        banner.id = "resume-banner";
        banner.className = "resume-banner";
        banner.innerHTML = `
            <div class="resume-banner-inner">
                <i class="bi bi-clock-history me-2"></i>
                <span>Вы смотрели до <strong>${formatDuration(pos.time)}</strong>${pos.label ? " · " + escapeHtml(pos.label) : ""}</span>
                <button class="btn btn-sm btn-primary ms-3" id="resume-btn">Продолжить</button>
                <button class="btn btn-sm btn-ghost-secondary ms-1" id="resume-dismiss">✕</button>
            </div>
        `;

        // Insert before room header or at top of content
        const container = document.querySelector(".container.py-4") || document.body;
        const firstChild = container.firstElementChild;
        if (firstChild) container.insertBefore(banner, firstChild);
        else container.appendChild(banner);

        document.getElementById("resume-btn").addEventListener("click", () => {
            // Seek video player to saved position
            const player = window.videoPlayer || window.player;
            if (player) {
                try {
                    player.currentTime = pos.time;
                    player.play().catch(() => {});
                } catch(e) {}
            }
            banner.remove();
        });

        document.getElementById("resume-dismiss").addEventListener("click", () => {
            banner.remove();
        });
    }

    showResumeBanner();

    // Auto-save position every 15 seconds while playing, and on pause/beforeunload
    let saveIntervalId = null;
    function startSavingPosition() {
        if (saveIntervalId) return;
        saveIntervalId = setInterval(() => {
            const player = window.videoPlayer || window.player;
            if (player && !player.paused && player.currentTime > 5) {
                // Try to get current episode label if available
                const epEl = document.getElementById("current-episode");
                const label = epEl ? epEl.textContent.trim() : null;
                savePosition(player.currentTime, label);
            }
        }, 15000);
    }

    // Trigger saving setup after player is ready
    setTimeout(() => {
        const player = window.videoPlayer || window.player;
        if (!player) return;

        player.on("pause", () => {
            const epEl = document.getElementById("current-episode");
            savePosition(player.currentTime, epEl ? epEl.textContent.trim() : null);
        });
        player.on("play", startSavingPosition);
        player.on("ended", () => {
            // Clear position when video ends
            try { localStorage.removeItem(RESUME_KEY); } catch(e) {}
        });
    }, 600);

    window.addEventListener("beforeunload", () => {
        const player = window.videoPlayer || window.player;
        if (player && player.currentTime > 5) {
            const epEl = document.getElementById("current-episode");
            savePosition(player.currentTime, epEl ? epEl.textContent.trim() : null);
        }
    });

    // ── Chat messages ─────────────────────────────────────────────────────
    function appendMessage(username, message, system = false, timestamp = null) {
        const div = document.createElement("div");
        div.classList.add("chat-message");

        const timeText = timestamp
            ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
            : "";

        if (system) {
            div.classList.add("system");
            div.textContent = message;
        } else if (username === window.currentUser) {
            div.classList.add("self");
            div.innerHTML = `<strong>${escapeHtml(username)}:</strong> ${escapeHtml(message)}<span class="message-meta">${timeText}</span>`;
        } else {
            div.classList.add("other");
            div.innerHTML = `<strong>${escapeHtml(username)}:</strong> ${escapeHtml(message)}<span class="message-meta">${timeText}</span>`;
        }

        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // ── Participants rendering ─────────────────────────────────────────────
    function renderParticipants(participants, count) {
        console.log("Rendering participants:", participants);
        if (!participantsList) return;
        participantsList.innerHTML = "";

        if (!Array.isArray(participants)) {
            console.error("Participants is not an array:", participants);
            return;
        }

        participants.forEach(entry => {
            try {
                // Support BOTH formats:
                //  • string  (from views.py broadcast)         → always online
                //  • object  (from consumers.py participants_update) → has .online flag
                let username, isOnline;
                if (typeof entry === "object" && entry !== null) {
                    username = String(entry.username || "Anonymous");
                    isOnline = Boolean(entry.online);
                } else {
                    username = String(entry || "Anonymous");
                    isOnline = true; // old format assumes online
                }

                const li = document.createElement("li");
                li.className = "participant-item";
                li.innerHTML = `
                    <span class="status-dot ${isOnline ? "online" : "offline"}" title="${isOnline ? "В комнате" : "Не в сети"}"></span>
                    <span class="participant-name">${escapeHtml(username)}</span>
                    <span class="participant-status-label">${isOnline ? "В комнате" : "Не в сети"}</span>
                `;
                participantsList.appendChild(li);
            } catch (err) {
                console.error("Error rendering participant entry:", entry, err);
            }
        });

        const countEl = document.getElementById("participants-count");
        if (countEl) {
            const n = (typeof count !== "undefined") ? count : participants.length;
            countEl.textContent = n;
        }
    }

    // ── WebSocket ─────────────────────────────────────────────────────────
    let chatSocket = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 10;
    const reconnectDelay = 3000;
    let reconnectTimeout = null;
    let messageQueue = [];

    function connectWebSocket() {
        if (chatSocket && (chatSocket.readyState === WebSocket.CONNECTING || chatSocket.readyState === WebSocket.OPEN)) {
            return;
        }

        const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
        chatSocket = new WebSocket(`${wsScheme}://${window.location.host}/ws/room/${roomId}/`);

        chatSocket.onopen = function () {
            console.log("Chat WS connected");
            reconnectAttempts = 0;
            while (messageQueue.length > 0) {
                const msg = messageQueue.shift();
                chatSocket.send(msg);
            }
        };

        chatSocket.onmessage = function (e) {
            let data;
            try {
                data = JSON.parse(e.data);
            } catch {
                return; // ignore non-JSON (handled by sync_player.js's own WS)
            }

            if (data.type === "message") {
                appendMessage(data.username, data.message, data.system, data.timestamp);
            }

            if (data.type === "participants") {
                renderParticipants(data.participants, data.count);
            }

            if (data.type === "history") {
                data.messages.forEach(msg => {
                    appendMessage(msg.username, msg.message, msg.system, msg.timestamp);
                });
            }

            // Ignore player_state / playlist_change / keyframe / play / pause etc.
            // Those are handled exclusively by sync_player.js
        };

        chatSocket.onerror = function (error) {
            console.error("Chat WS error:", error);
        };

        chatSocket.onclose = function (e) {
            console.log("Chat WS disconnected, code:", e.code);

            // code 4003 = not authenticated, do not retry
            if (e.code === 4003) {
                console.warn("Chat WS: not authenticated, reconnect suppressed.");
                return;
            }

            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                const delay = reconnectDelay * Math.min(reconnectAttempts, 5);
                reconnectTimeout = setTimeout(connectWebSocket, delay);
            } else {
                appendMessage("Система", "Не удалось восстановить соединение. Обновите страницу.", true);
            }
        };
    }

    connectWebSocket();

    // ── Chat form ─────────────────────────────────────────────────────────
    if (chatForm) {
        chatForm.addEventListener("submit", function (e) {
            e.preventDefault();
            const message = chatInput.value.trim();
            if (!message) return;

            const msgData = JSON.stringify({
                type: "chat",
                message,
                timestamp: new Date().toISOString(),
            });

            if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
                chatSocket.send(msgData);
            } else {
                messageQueue.push(msgData);
                appendMessage("Система", "Сообщение будет отправлено при восстановлении соединения...", true);
                if (!chatSocket || chatSocket.readyState === WebSocket.CLOSED) {
                    connectWebSocket();
                }
            }
            chatInput.value = "";
        });
    }

    // ── Cleanup ───────────────────────────────────────────────────────────
    window.addEventListener("beforeunload", function () {
        if (reconnectTimeout) clearTimeout(reconnectTimeout);
        if (chatSocket) chatSocket.close();
    });

    document.addEventListener("visibilitychange", function () {
        if (!document.hidden && chatSocket && chatSocket.readyState === WebSocket.CLOSED) {
            reconnectAttempts = 0;
            connectWebSocket();
        }
    });
});