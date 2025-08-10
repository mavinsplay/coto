document.addEventListener("DOMContentLoaded", function () {
    const roomId = document.getElementById("chat-container").dataset.roomId;
    const chatMessages = document.getElementById("chat-messages");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const participantsList = document.getElementById("participants-list");

    const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
    const chatSocket = new WebSocket(`${wsScheme}://${window.location.host}/ws/room/${roomId}/`);

    function formatTime(date) {
        const hours = String(date.getHours()).padStart(2, "0");
        const minutes = String(date.getMinutes()).padStart(2, "0");
        return `${hours}:${minutes}`;
    }

    function appendMessage(username, message, system = false, timestamp = null) {
        const div = document.createElement("div");
        div.classList.add("chat-message");

        const timeText = timestamp
            ? new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : formatTime(new Date());

        if (system) {
            div.classList.add("system");
            div.textContent = message;
        } else if (username === window.currentUser) {
            div.classList.add("self");
            div.innerHTML = `<strong>${username}:</strong> ${message}<span class="message-meta">${timeText}</span>`;
        } else {
            div.classList.add("other");
            div.innerHTML = `<strong>${username}:</strong> ${message}<span class="message-meta">${timeText}</span>`;
        }

        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    chatSocket.onmessage = function (e) {
        let data;
        try {
            data = JSON.parse(e.data);
        } catch {
            handleVideoSync(e.data);
            return;
        }

        if (data.type === "message") {
            appendMessage(data.username, data.message, data.system, data.timestamp);
        }

        if (data.type === "participants") {
            participantsList.innerHTML = "";
            data.participants.forEach(user => {
                const li = document.createElement("li");
                li.textContent = user;
                participantsList.appendChild(li);
            });
        }

        if (data.type === "history") {
            data.messages.forEach(msg => {
                appendMessage(msg.username, msg.message, msg.system, msg.timestamp);
            });
        }
    };

    chatSocket.onclose = function () {
        console.error("Чат отключён");
    };

    chatForm.addEventListener("submit", function (e) {
        e.preventDefault();
        const message = chatInput.value.trim();
        if (message) {
            chatSocket.send(JSON.stringify({
                type: "chat",
                message: message,
                timestamp: new Date().toISOString()
            }));
            chatInput.value = "";
        }
    });
});