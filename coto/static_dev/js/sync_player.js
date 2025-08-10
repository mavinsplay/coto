// static/js/sync_player.js

// === ReconnectingWebSocket (встроенный) ===
function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }
  
  class ReconnectingWebSocket {
    constructor(url, protocols = [], opts = {}) {
      this.url = url;
      this.protocols = protocols;
      this.opts = Object.assign({
        maxRetries: 50,
        minDelay: 500,
        maxDelay: 30000,
        jitter: 0.2,
        heartbeatInterval: 20000,
        heartbeatTimeout: 10000,
        autoReconnect: true,
        clientId: uuidv4(),
        requestStateOnOpen: true,
      }, opts);
  
      this.ws = null;
      this.forcedClose = false;
      this.retryCount = 0;
      this.messageQueue = [];
      this.openHandlers = [];
      this.closeHandlers = [];
      this.messageHandlers = [];
      this.errorHandlers = [];
      this._heartbeatTimer = null;
      this._heartbeatTimeoutTimer = null;
  
      this._handleVisibility = this._handleVisibility.bind(this);
      this._handleOnline = this._handleOnline.bind(this);
      this._handleOffline = this._handleOffline.bind(this);
  
      window.addEventListener('visibilitychange', this._handleVisibility);
      window.addEventListener('online', this._handleOnline);
      window.addEventListener('offline', this._handleOffline);
  
      this.connect();
    }
  
    get readyState() {
      return this.ws ? this.ws.readyState : WebSocket.CLOSED;
    }
  
    connect() {
      if (!this.opts.autoReconnect) return;
      if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
  
      try {
        this.ws = this.protocols.length ? new WebSocket(this.url, this.protocols) : new WebSocket(this.url);
      } catch (e) {
        console.error('WS ctor failed', e);
        this._scheduleReconnect();
        return;
      }
  
      this.ws.onopen = (ev) => {
        this.retryCount = 0;
        this._startHeartbeat();
        this.openHandlers.forEach(h => h.call(this, ev));
        this._flushQueue();
  
        if (this.opts.requestStateOnOpen) {
          setTimeout(() => {
            this.sendSafe({ type: 'request_state', client_id: this.opts.clientId, ts: Date.now() });
          }, 120);
        }
      };
  
      this.ws.onmessage = (ev) => {
        this._resetHeartbeatTimeout();
        this.messageHandlers.forEach(h => h.call(this, ev));
      };
  
      this.ws.onclose = (ev) => {
        this._stopHeartbeat();
        this.closeHandlers.forEach(h => h.call(this, ev));
        if (!this.forcedClose && this.opts.autoReconnect) this._scheduleReconnect();
      };
  
      this.ws.onerror = (ev) => {
        this.errorHandlers.forEach(h => h.call(this, ev));
      };
    }
  
    _scheduleReconnect() {
      if (!this.opts.autoReconnect) return;
      if (this.retryCount >= this.opts.maxRetries) {
        console.warn('ReconnectingWebSocket: max retries reached');
        return;
      }
      const base = this.opts.minDelay * Math.pow(1.5, this.retryCount);
      const delay = Math.min(this.opts.maxDelay, base);
      const jitter = delay * this.opts.jitter * (Math.random() * 2 - 1);
      const finalDelay = Math.max(0, Math.round(delay + jitter));
  
      this.retryCount += 1;
      console.info(`ReconnectingWebSocket: reconnect attempt #${this.retryCount} in ${finalDelay} ms`);
      setTimeout(() => {
        if (navigator.onLine === false) return;
        this.connect();
      }, finalDelay);
    }
  
    send(data) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(data);
        return true;
      }
      this.messageQueue.push(data);
      return false;
    }
  
    sendSafe(data) {
      let out = data;
      try {
        if (typeof data === 'object') {
          const copy = Object.assign({}, data);
          if (!copy.client_id) copy.client_id = this.opts.clientId;
          out = JSON.stringify(copy);
        } else {
          try {
            const obj = JSON.parse(data);
            if (obj && typeof obj === 'object') {
              if (!obj.client_id) obj.client_id = this.opts.clientId;
              out = JSON.stringify(obj);
            }
          } catch (_) {
            out = data;
          }
        }
      } catch (e) { out = data; }
      return this.send(out);
    }
  
    _flushQueue() {
      while (this.messageQueue.length && this.ws && this.ws.readyState === WebSocket.OPEN) {
        const msg = this.messageQueue.shift();
        try { this.ws.send(msg); } catch (e) { console.warn('flush send failed', e); this.messageQueue.unshift(msg); break; }
      }
    }
  
    close(code = 1000, reason) {
      this.forcedClose = true;
      this.opts.autoReconnect = false;
      this._stopHeartbeat();
      if (this.ws) this.ws.close(code, reason);
      window.removeEventListener('visibilitychange', this._handleVisibility);
      window.removeEventListener('online', this._handleOnline);
      window.removeEventListener('offline', this._handleOffline);
    }
  
    _startHeartbeat() {
      this._stopHeartbeat();
      if (!this.opts.heartbeatInterval) return;
      this._heartbeatTimer = setInterval(() => {
        try {
          this.sendSafe({ type: 'ping', client_id: this.opts.clientId, ts: Date.now() });
          this._heartbeatTimeoutTimer = setTimeout(() => {
            console.warn('heartbeat timeout, forcing reconnect');
            try { if (this.ws) this.ws.close(); } catch (e) {}
          }, this.opts.heartbeatTimeout);
        } catch (e) { console.warn('heartbeat send failed', e); }
      }, this.opts.heartbeatInterval);
    }
  
    _resetHeartbeatTimeout() {
      if (this._heartbeatTimeoutTimer) {
        clearTimeout(this._heartbeatTimeoutTimer);
        this._heartbeatTimeoutTimer = null;
      }
    }
  
    _stopHeartbeat() {
      if (this._heartbeatTimer) { clearInterval(this._heartbeatTimer); this._heartbeatTimer = null; }
      if (this._heartbeatTimeoutTimer) { clearTimeout(this._heartbeatTimeoutTimer); this._heartbeatTimeoutTimer = null; }
    }
  
    _handleVisibility() {
      if (document.visibilityState === 'visible') this.connect();
    }
    _handleOnline() { this.connect(); }
    _handleOffline() { console.info('network offline'); }
  
    addEventListener(type, handler) {
      if (type === 'open') this.openHandlers.push(handler);
      if (type === 'close') this.closeHandlers.push(handler);
      if (type === 'message') this.messageHandlers.push(handler);
      if (type === 'error') this.errorHandlers.push(handler);
    }
  }
  
  // === main sync_player code ===
  document.addEventListener("DOMContentLoaded", () => {
    const player = videojs("hls-player", {
      fluid: true,
      responsive: true,
      playbackRates: [0.5,0.75,1,1.25,1.5,2],
      plugins: { qualityLevels: {}, hlsQualitySelector: { displayCurrentQuality: true } }
    });
  
    const videoEl = player.el();
    const roomId  = videoEl.dataset.roomId;
    const isHost  = videoEl.dataset.isHost === "true";
    const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${wsScheme}://${window.location.host}/ws/room/${roomId}/`;
  
    // ReconnectingWebSocket instance
    const socket = new ReconnectingWebSocket(wsUrl, [], {
      minDelay: 500,
      maxDelay: 25000,
      jitter: 0.25,
      heartbeatInterval: 20000,
      heartbeatTimeout: 8000,
      clientId: uuidv4(),
      requestStateOnOpen: true,
    });
  
    const playlistItems = document.querySelectorAll(".playlist-item");
    const currentEpisodeLabel = document.getElementById("current-episode");
  
    let suppressEvent = false;
    let lastSeekSent = 0;
    let waitingForInitialState = true;
  
    socket.addEventListener('open', () => console.log("🔌 WS connected (reconnect-aware)"));
    socket.addEventListener('close', () => console.log("🔌 WS disconnected"));
    socket.addEventListener('error', e => console.error("🔌 WS error", e));
  
    function sendCmd(type) {
      if (suppressEvent || socket.readyState !== WebSocket.OPEN) { suppressEvent = false; return; }
      const msg = { type, time: player.currentTime(), ts: Date.now() };
      socket.sendSafe(msg);
    }
  
    player.on("play",  () => sendCmd("play"));
    player.on("pause", () => sendCmd("pause"));
    player.on("seeked", () => {
      const now = Date.now();
      if (now - lastSeekSent < 500) return;
      lastSeekSent = now;
      sendCmd("seek");
    });
  
    if (isHost) {
      setInterval(() => {
        if (!player.paused() && socket.readyState === WebSocket.OPEN) {
          socket.sendSafe({ type: "keyframe", time: player.currentTime(), ts: Date.now() });
        }
      }, 5000);
    }
  
    function highlightItem(item) {
      playlistItems.forEach(i => i.classList.remove("active"));
      if (item) item.classList.add("active");
    }
    function setCurrentLabel(season, episode, title) {
      if (!currentEpisodeLabel) return;
      currentEpisodeLabel.textContent = `Сезон ${season}, Серия ${episode} — ${title}`;
    }
  
    async function applyPlaylistChangeLocally(item, { play=true, suppressSend=true } = {}) {
      if (!item) return;
      const hlsUrl = item.dataset.hlsUrl || item.getAttribute("data-hls-url");
      const season = item.dataset.season;
      const episode = item.dataset.episode;
      const title = item.dataset.title;
  
      suppressEvent = !!suppressSend;
      player.src({ src: hlsUrl, type: "application/x-mpegURL" });
      try { if (play) await player.play(); } catch(e){ console.warn("autoplay blocked", e); }
      highlightItem(item);
      setCurrentLabel(season, episode, title);
      setTimeout(()=>{ suppressEvent = false; }, 200);
    }
  
    function sendPlaylistSelect(item) {
      if (socket.readyState !== WebSocket.OPEN) {
        applyPlaylistChangeLocally(item);
        return;
      }
      const payload = {
        type: "playlist_select",
        ts: Date.now(),
        item: {
          video_id: item.dataset.videoId,
          hls_url: item.dataset.hlsUrl || item.getAttribute("data-hls-url"),
          season: item.dataset.season,
          episode: item.dataset.episode,
          title: item.dataset.title
        }
      };
      socket.sendSafe(payload);
      applyPlaylistChangeLocally(item, { play: true, suppressSend: true });
    }
  
    playlistItems.forEach(item => {
      item.style.cursor = "pointer";
      item.addEventListener("click", () => sendPlaylistSelect(item));
    });
  
    // central message handler
    socket.addEventListener('message', (ev) => {
      const data = ev.data;
      let msg;
      try { msg = JSON.parse(data); } catch(e){ return; }
  
      if (msg.type === "player_state" && msg.state) {
        const st = msg.state;
        waitingForInitialState = false;
  
        const latency = st.ts ? (Date.now() - st.ts) / 1000 : 0;
        const target = (typeof st.time === "number") ? (st.time + latency) : null;
  
        if (st.hls_url) {
          suppressEvent = true;
          player.src({ src: st.hls_url, type: "application/x-mpegURL" });
        }
        if (target !== null) {
          player.currentTime(target);
        }
        if (st.is_playing) {
          player.play().catch(()=>{});
        } else {
          player.pause();
        }
  
        let targetEl = null;
        if (st.video_id) {
          targetEl = document.querySelector(`.playlist-item[data-video-id="${st.video_id}"]`);
        }
        if (!targetEl && st.hls_url) {
          targetEl = Array.from(playlistItems).find(pi => (pi.dataset.hlsUrl === st.hls_url) || (pi.getAttribute("data-hls-url") === st.hls_url));
        }
        if (targetEl) {
          highlightItem(targetEl);
          setCurrentLabel(targetEl.dataset.season, targetEl.dataset.episode, targetEl.dataset.title);
        } else if (st.hls_url) {
          setCurrentLabel("-", "-", "Видео");
        }
        setTimeout(()=>{ suppressEvent = false; }, 150);
        return;
      }
  
      if (msg.type === "playlist_change") {
        const it = msg.item || {};
        let target = null;
        if (it.video_id) target = document.querySelector(`.playlist-item[data-video-id="${it.video_id}"]`);
        if (!target && it.hls_url) {
          target = Array.from(playlistItems).find(pi => (pi.dataset.hlsUrl === it.hls_url) || (pi.getAttribute("data-hls-url") === it.hls_url));
        }
        if (target) {
          applyPlaylistChangeLocally(target, { play: true, suppressSend: true });
        } else if (it.hls_url) {
          suppressEvent = true;
          player.src({ src: it.hls_url, type: "application/x-mpegURL" });
          player.play().catch(()=>{});
          setTimeout(()=>{ suppressEvent = false; }, 200);
          setCurrentLabel(it.season || "-", it.episode || "-", it.title || "Видео");
        }
        waitingForInitialState = false;
        return;
      }
  
      if (["play","pause","seek","keyframe"].includes(msg.type)) {
        const latency = msg.ts ? (Date.now() - msg.ts) / 1000 : 0;
        const target = (typeof msg.time === "number") ? (msg.time + latency) : null;
        suppressEvent = true;
        switch (msg.type) {
          case "play":
            if (target !== null) player.currentTime(target);
            player.play().catch(()=>{});
            break;
          case "pause":
            if (target !== null) player.currentTime(target);
            player.pause();
            break;
          case "seek":
          case "keyframe":
            if (typeof msg.time === "number" && Math.abs(player.currentTime() - msg.time) > 0.5) {
              player.currentTime(msg.time);
            }
            break;
        }
        setTimeout(()=>{ suppressEvent = false; }, 50);
        waitingForInitialState = false;
        return;
      }
  
      // other types (chat/participants/history) ignored here — keep existing handlers elsewhere
    });
  
    // fallback: если сервер не прислал состояние за 1500ms -> локальный автозапуск первого
    if (playlistItems.length > 0) {
      setTimeout(() => {
        if (!waitingForInitialState) return;
        const srcs = player.currentSources && player.currentSources();
        const hasSrc = Array.isArray(srcs) && srcs.length && (srcs[0].src || player.currentType());
        if (!hasSrc) {
          applyPlaylistChangeLocally(playlistItems[0], { play: true, suppressSend: false });
        }
        waitingForInitialState = false;
      }, 1500);
    }
  
    window.addEventListener("beforeunload", () => {
      try { socket.close(); } catch(e) {}
      try { player.dispose(); } catch(e){}
    });
  });
  