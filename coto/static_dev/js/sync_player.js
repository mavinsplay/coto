// static/js/sync_player.js

document.addEventListener("DOMContentLoaded", () => {
    const player = videojs("hls-player", {
      fluid: true,
      responsive: true,
      playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 2],
      plugins: {
        qualityLevels: {},
        hlsQualitySelector: { displayCurrentQuality: true },
      },
    });
  
    const videoEl = player.el();
    const roomId  = videoEl.dataset.roomId;
    const isHost  = videoEl.dataset.isHost === "true";
    const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
    const socket  = new WebSocket(`${wsScheme}://${window.location.host}/ws/room/${roomId}/`);
  
    let suppressEvent  = false;
    let lastSeekSent   = 0;
  
    socket.onopen    = () => console.log("🔌 WS connected");
    socket.onclose   = () => console.log("🔌 WS disconnected");
    socket.onerror   = e => console.error("🔌 WS error", e);
  
    // Функция для отправки команд из любых клиентов
    function sendCmd(type) {
      if (suppressEvent || socket.readyState !== WebSocket.OPEN) {
        suppressEvent = false;
        return;
      }
      const msg = { type, time: player.currentTime(), ts: Date.now() };
      socket.send(JSON.stringify(msg));
    }
  
    // Все клиенты шлют свои команды
    player.on("play",  () => sendCmd("play"));
    player.on("pause", () => sendCmd("pause"));
    player.on("seeked", () => {
      const now = Date.now();
      if (now - lastSeekSent < 500) return;
      lastSeekSent = now;
      sendCmd("seek");
    });
  
    // Host шлёт ключевые кадры для выравнивания дрейфа
    if (isHost) {
      setInterval(() => {
        if (!player.paused() && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({
            type: "keyframe",
            time: player.currentTime(),
            ts: Date.now()
          }));
        }
      }, 5000);
    }
  
    // Приём и применение команд
    socket.onmessage = ({ data }) => {
      let msg;
      try { msg = JSON.parse(data); } catch { return; }
  
      // Рассчитываем задержку сети (в секундах)
      const latency = (Date.now() - msg.ts) / 1000;
      const target  = msg.time + latency;
  
      // Подавляем своё событие при применении входящего
      suppressEvent = true;
  
      switch (msg.type) {
        case "play":
          player.currentTime(target);
          player.play();
          break;
  
        case "pause":
          // Сначала устанавливаем время, затем паузу
          player.currentTime(target);
          player.pause();
          break;
  
        case "seek":
        case "keyframe":
          // Коррекция дрейфа, если рассинхрон >0.5 сек
          if (Math.abs(player.currentTime() - msg.time) > 0.5) {
            player.currentTime(msg.time);
          }
          break;
      }
  
      // Сбросим suppressEvent, чтобы следующий локальный клик отправился
      setTimeout(() => { suppressEvent = false; }, 50);
    };
  
    // Очистка
    window.addEventListener("beforeunload", () => {
      socket.close();
      player.dispose();
    });
  });
  