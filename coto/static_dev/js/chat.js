document.addEventListener("DOMContentLoaded", function () {
    const roomId = document.getElementById("chat-container").dataset.roomId;
    const chatMessages = document.getElementById("chat-messages");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const participantsList = document.getElementById("participants-list");

    let chatSocket = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 10;
    const reconnectDelay = 3000; // 3 секунды
    let reconnectTimeout = null;
    let messageQueue = []; // Очередь сообщений для отправки при переподключении

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
            : "";

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

    function connectWebSocket() {
        if (chatSocket && (chatSocket.readyState === WebSocket.CONNECTING || chatSocket.readyState === WebSocket.OPEN)) {
            return; // Уже подключены или подключаемся
        }

        const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
        chatSocket = new WebSocket(`${wsScheme}://${window.location.host}/ws/room/${roomId}/`);

        chatSocket.onopen = function() {
            console.log("WebSocket подключён");
            reconnectAttempts = 0;
            
            // Отправляем сообщения из очереди
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
            
                const countElement = document.getElementById("participants-count");
                if (countElement && typeof data.count !== "undefined") {
                    countElement.textContent = data.count;
                }
            }

            if (data.type === "history") {
                data.messages.forEach(msg => {
                    appendMessage(msg.username, msg.message, msg.system, msg.timestamp);
                });
            }
        };

        chatSocket.onerror = function(error) {
            console.error("WebSocket ошибка:", error);
        };

        chatSocket.onclose = function (e) {
            console.log("WebSocket отключён. Код:", e.code, "Причина:", e.reason);
            
            // Пытаемся переподключиться
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                const delay = reconnectDelay * Math.min(reconnectAttempts, 5); // Экспоненциальная задержка
                console.log(`Попытка переподключения ${reconnectAttempts}/${maxReconnectAttempts} через ${delay}ms`);
                
                reconnectTimeout = setTimeout(connectWebSocket, delay);
            } else {
                console.error("Превышено максимальное количество попыток переподключения");
                appendMessage("Система", "Не удалось восстановить соединение. Обновите страницу.", true);
            }
        };
    }

    // Первоначальное подключение
    connectWebSocket();

    // Обработка отправки сообщений
    chatForm.addEventListener("submit", function (e) {
        e.preventDefault();
        const message = chatInput.value.trim();
        if (message) {
            const messageData = JSON.stringify({
                type: "chat",
                message: message,
                timestamp: new Date().toISOString()
            });

            if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
                chatSocket.send(messageData);
            } else {
                // Добавляем в очередь, если нет подключения
                messageQueue.push(messageData);
                appendMessage("Система", "Сообщение будет отправлено при восстановлении соединения...", true);
                
                // Пытаемся переподключиться, если не подключены
                if (!chatSocket || chatSocket.readyState === WebSocket.CLOSED) {
                    connectWebSocket();
                }
            }
            
            chatInput.value = "";
        }
    });

    // Очистка при закрытии страницы
    window.addEventListener("beforeunload", function() {
        if (reconnectTimeout) {
            clearTimeout(reconnectTimeout);
        }
        if (chatSocket) {
            chatSocket.close();
        }
    });

    // Обработка видимости страницы (переподключение при возвращении на вкладку)
    document.addEventListener("visibilitychange", function() {
        if (!document.hidden && chatSocket && chatSocket.readyState === WebSocket.CLOSED) {
            console.log("Страница стала видимой, переподключаемся...");
            reconnectAttempts = 0; // Сбрасываем счётчик при возвращении на вкладку
            connectWebSocket();
        }
    });
});