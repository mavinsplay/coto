// static/js/sync_player.js

// === ReconnectingWebSocket (built-in) ===
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
      if (ev.code === 4003) {
        console.warn('🔒 WS closed: not authenticated (4003). Reconnect suppressed.');
        this.opts.autoReconnect = false;
        return;
      }
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
          try { if (this.ws) this.ws.close(); } catch (e) { }
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

// === Main sync_player code ===
document.addEventListener("DOMContentLoaded", () => {
  const videoEl = document.getElementById("hls-player");
  if (!videoEl) return;

  const roomId = videoEl.dataset.roomId;
  const isHost = videoEl.dataset.isHost === "true";

  // ── Sync state variables (initialized early to avoid TDZ) ────────────────
  let waitingForInitialState = true;
  let suppressEvent = false;
  let lastSeekSent = 0;

  // Drift correction state
  let _lastKeyframeTime = null;
  let _lastKeyframeTs = 0;
  let _keyframeTimeout = null;
  let _hostAlive = true;

  const player = new Plyr(videoEl, {
    controls: ['play-large', 'play', 'progress', 'current-time', 'mute', 'volume', 'settings', 'fullscreen'],
    settings: ['quality'],
    speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
    quality: { default: 2160, options: [4320, 2880, 2160, 1440, 1080, 720, 480, 360, 240, 144] },
    i18n: {
      restart: 'Начать заново',
      rewind: 'Перемотать на {seektime}с',
      play: 'Воспроизвести',
      pause: 'Пауза',
      fastForward: 'Вперед на {seektime}с',
      seek: 'Искать',
      seekLabel: '{currentTime} из {duration}',
      played: 'Проиграно',
      buffered: 'Буферизовано',
      currentTime: 'Текущее время',
      duration: 'Общая длительность',
      volume: 'Громкость',
      mute: 'Убрать звук',
      unmute: 'Включить звук',
      enableCaptions: 'Включить субтитры',
      disableCaptions: 'Выключить субтитры',
      download: 'Скачать',
      enterFullscreen: 'Полноэкранный режим',
      exitFullscreen: 'Выйти из полноэкранного режима',
      frameTitle: 'Плеер для {title}',
      captions: 'Субтитры',
      settings: 'Настройки',
      pip: 'Картинка в картинке',
      menuBack: 'Назад к предыдущему меню',
      speed: 'Скорость',
      normal: 'Обычная',
      quality: 'Качество',
      loop: 'Зациклить',
      start: 'Старт',
      end: 'Конец',
      all: 'Все',
      reset: 'Сбросить',
      disabled: 'Отключено',
      enabled: 'Включено',
      advertisement: 'Реклама',
    },
  });
  window.videoPlayer = player;

  // ── Sync UI state handling ──────────────────────────────────────────────
  function setSyncingUI(isSyncing) {
    const container = videoEl.closest('.plyr');
    const loader = document.getElementById('custom-loader') || document.querySelector('.plyr-video-loader');
    if (container) {
      if (isSyncing) {
        container.classList.add('plyr--syncing');
        if (loader) loader.classList.add('active');
      } else {
        container.classList.remove('plyr--syncing');
        if (loader) loader.classList.remove('active');
      }
    }
  }

  setSyncingUI(true);

  // Fail-safe: unlock if sync takes too long (> 5s)
  const syncTimeout = setTimeout(() => {
    if (waitingForInitialState) {
      console.warn("⚠️ Sync timeout, unlocking player...");
      waitingForInitialState = false;
      setSyncingUI(false);
    }
  }, 5000);

  // ── Hidden audio element (for DASH – separate video + audio streams) ──
  let audioEl = document.getElementById('external-audio');
  if (!audioEl) {
    audioEl = document.createElement('audio');
    audioEl.id = 'external-audio';
    // no crossorigin — YouTube CDN may not send CORS headers,
    // but basic <audio> playback works without them.
    audioEl.style.cssText = 'position:absolute;width:1px;height:1px;opacity:0;pointer-events:none';
    document.body.appendChild(audioEl);
  }

  // Smooth sync: nudge audio playbackRate instead of seeking (avoids pops)
  let _audioSyncTimer = setInterval(() => {
    if (!audioEl.src || !videoEl.src) return;
    const drift = audioEl.currentTime - videoEl.currentTime;
    if (Math.abs(drift) > 0.5) {
      audioEl.playbackRate = drift > 0 ? 0.95 : 1.05;
      setTimeout(() => { audioEl.playbackRate = 1.0; }, 3000);
    }
  }, 5000);

  // Forward Plyr play/pause to the DASH audio element
  player.on('play', () => { if (audioEl.src) audioEl.play().catch(() => {}); });
  player.on('pause', () => { if (audioEl.src) audioEl.pause(); });
  player.on('seeked', () => {
    if (audioEl.src) audioEl.currentTime = videoEl.currentTime;
  });

  // ── Custom controls (effects + quality) ─────────────────────────────────
  let effectsManager = null;
  let qualityManager = null;
  let qualityBtn = null;
  let effectsBtn = null;

  function _injectCustomButtons() {
    const controls = player.elements.controls;
    if (!controls || qualityBtn) return; // already injected

    qualityBtn = document.createElement('button');
    qualityBtn.type = 'button';
    qualityBtn.className = 'plyr__control plyr__control--quality';
    qualityBtn.style.display = 'none';
    qualityBtn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
        <path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h3A1.5 1.5 0 0 1 7 2.5v3A1.5 1.5 0 0 1 5.5 7h-3A1.5 1.5 0 0 1 1 5.5v-3zM2.5 2a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3zm6.5.5A1.5 1.5 0 0 1 10.5 1h3A1.5 1.5 0 0 1 15 2.5v3A1.5 1.5 0 0 1 13.5 7h-3A1.5 1.5 0 0 1 9 5.5v-3zm1.5-.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3zM1 10.5A1.5 1.5 0 0 1 2.5 9h3A1.5 1.5 0 0 1 7 10.5v3A1.5 1.5 0 0 1 5.5 15h-3A1.5 1.5 0 0 1 1 13.5v-3zm1.5-.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3zm6.5.5A1.5 1.5 0 0 1 10.5 9h3a1.5 1.5 0 0 1 1.5 1.5v3a1.5 1.5 0 0 1-1.5 1.5h-3A1.5 1.5 0 0 1 9 13.5v-3zm1.5-.5a.5.5 0 0 0-.5.5v3a.5.5 0 0 0 .5.5h3a.5.5 0 0 0 .5-.5v-3a.5.5 0 0 0-.5-.5h-3z"/>
      </svg>
      <span class="plyr__tooltip">Качество</span>
    `;

    qualityBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (qualityManager) {
        const sb = controls.querySelector('[data-plyr="settings"]');
        if (sb && sb.getAttribute('aria-expanded') === 'true') sb.click();
        qualityManager.togglePanel();
        if (effectsManager) effectsManager.hidePanel();
      }
    });

    effectsBtn = document.createElement('button');
    effectsBtn.type = 'button';
    effectsBtn.className = 'plyr__control plyr__control--effects';
    effectsBtn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" class="bi bi-stars" viewBox="0 0 16 16">
        <path d="M7.657 6.247c.11-.33.576-.33.686 0l.645 1.937a2.89 2.89 0 0 0 1.882 1.882l1.937.645c.33.11.33.576 0 .686l-1.937.645a2.89 2.89 0 0 0-1.882 1.882l-.645 1.937c-.11.33-.576.33-.686 0l-.645-1.937a2.89 2.89 0 0 0-1.882-1.882l-1.937-.645c-.33-.11-.33-.576 0-.686l1.937-.645a2.89 2.89 0 0 0 1.882-1.882l.645-1.937zM4.333 2.667c.06-.18.313-.18.373 0l.35 1.05a1.577 1.577 0 0 0 1.027 1.027l1.05.35c.18.06.18.313 0 .373l-1.05.35a1.577 1.577 0 0 0-1.027 1.027l-.35 1.05c-.06.18-.313.18-.373 0l-.35-1.05a1.577 1.577 0 0 0-1.027-1.027l-1.05-.35c-.06-.18-.18-.313 0-.373l1.05-.35a1.577 1.577 0 0 0 1.027-1.027l.35-1.05zM12.333 1.333c.06-.18.313-.18.373 0l.35 1.05a1.577 1.577 0 0 0 1.027 1.027l1.05.35c.18.06.18.313 0 .373l-1.05.35a1.577 1.577 0 0 0-1.027 1.027l-.35 1.05c-.06.18-.313.18-.373 0l-.35-1.05a1.577 1.577 0 0 0-1.027-1.027l-1.05-.35c-.06-.18-.18-.313 0-.373l1.05-.35a1.577 1.577 0 0 0 1.027-1.027l.35-1.05z"/>
      </svg>
      <span class="plyr__tooltip">Эффекты</span>
    `;

    effectsBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (effectsManager) {
        const sb = controls.querySelector('[data-plyr="settings"]');
        if (sb && sb.getAttribute('aria-expanded') === 'true') sb.click();
        effectsManager.togglePanel();
        if (qualityManager) qualityManager.hidePanel();
      }
    });

    // Insert effects before fullscreen, quality before effects
    const fsBtn = controls.querySelector('[data-plyr="fullscreen"]');
    if (fsBtn && fsBtn.parentNode === controls) {
      controls.insertBefore(effectsBtn, fsBtn);
      controls.insertBefore(qualityBtn, effectsBtn);
    } else {
      const refBtn = controls.querySelector('[data-plyr="settings"]');
      if (refBtn && refBtn.parentNode === controls) {
        controls.insertBefore(effectsBtn, refBtn);
        controls.insertBefore(qualityBtn, refBtn);
      } else {
        controls.appendChild(qualityBtn);
        controls.appendChild(effectsBtn);
      }
    }

    player.on('settings:opened', () => {
      if (effectsManager) effectsManager.hidePanel();
      if (qualityManager) qualityManager.hidePanel();
    });

    const settingsBtn = controls.querySelector('[data-plyr="settings"]');
    if (settingsBtn) {
      settingsBtn.addEventListener('click', () => {
        if (effectsManager) effectsManager.hidePanel();
        if (qualityManager) qualityManager.hidePanel();
      }, true);
    }

    controls.addEventListener('click', (e) => {
      const inside = e.target.closest('.plyr__control--effects, .plyr__control--quality');
      if (!inside) {
        if (effectsManager) effectsManager.hidePanel();
        if (qualityManager) qualityManager.hidePanel();
      }
    }, true);
  }

  // Try injecting via ready event, with a polling fallback
  if (player.elements.controls) {
    _injectCustomButtons();
  } else {
    player.on('ready', _injectCustomButtons);
    // Fallback: some Plyr setups never fire 'ready', poll for controls
    let _pollTimer = setInterval(() => {
      if (player.elements.controls && !qualityBtn) {
        _injectCustomButtons();
      }
      if (qualityBtn) clearInterval(_pollTimer);
    }, 200);
    // Safety stop after 10s
    setTimeout(() => clearInterval(_pollTimer), 10000);
  }

  // Helper: re-attempt button injection whenever we set up a new source.
  // Idempotent — _injectCustomButtons guards with "if (qualityBtn) return".
  function _ensureCustomButtons() {
    if (player.elements.controls && !qualityBtn) _injectCustomButtons();
  }

  // Forward Plyr volume changes to the DASH audio element
  player.on('volumechange', () => {
    audioEl.volume = videoEl.volume;
  });

  // ── HLS setup — tuned for long-form content stability ───────────────────
  let hls = null;
  if (Hls.isSupported()) {
    hls = window.hls = new Hls({
      maxBufferLength: 60,
      maxMaxBufferLength: 120,
      startFragPrefetch: true,
      lowLatencyMode: false,
      enableWorker: true,
      manifestLoadingMaxRetry: 4,
      manifestLoadingRetryDelay: 1000,
      levelLoadingMaxRetry: 4,
      levelLoadingRetryDelay: 1000,
      fragLoadingMaxRetry: 6,
      fragLoadingRetryDelay: 1000,
      startLevel: -1,
      abrEwmaDefaultEstimate: 1000000,
      nudgeOffset: 0.1,
      nudgeMaxRetry: 5,
    });
    hls.attachMedia(videoEl);

    hls.on(Hls.Events.ERROR, (event, data) => {
      if (!data.fatal) return;
      console.warn('🎬 Fatal HLS error:', data.type, data.details);
      if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
        hls.startLoad();
      } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
        hls.recoverMediaError();
      } else {
        const currentSrc = videoEl.src;
        hls.destroy();
        hls = window.hls = new Hls({ maxBufferLength: 60, maxMaxBufferLength: 120, startLevel: -1 });
        hls.attachMedia(videoEl);
        if (currentSrc) hls.loadSource(currentSrc);
      }
    });
  }

  // ── QualityManager ─────────────────────────────────────────────────────
  class QualityManager {
    constructor(player, qualities, roomId, defaultLabel) {
      this.player = player;
      this.qualities = qualities;
      this.roomId = roomId;
      this.currentLabel = defaultLabel || qualities[0]?.label;
      this.panel = null;
      this.onToggle = null;
      // Called with (height) when user selects a different quality.
      // Should fetch a fresh URL from the backend and apply it.
      this.onSelect = null;
      this.init();
    }

    init() {
      this.panel = document.createElement('div');
      this.panel.className = 'plyr__quality-panel';
      this.panel.innerHTML = `
        <div class="plyr__quality-list">
          ${this.qualities.map(q => `
            <div class="quality-option${q.label === this.currentLabel ? ' active' : ''}" data-height="${q.height}" data-label="${q.label}">
              <span class="quality-label">${q.label}</span>
              <span class="quality-check">${q.label === this.currentLabel ? '✓' : ''}</span>
            </div>
          `).join('')}
        </div>
      `;

      this.panel.querySelectorAll('.quality-option').forEach(opt => {
        opt.addEventListener('click', () => this._select(opt.dataset.label, Number(opt.dataset.height)));
      });

      document.addEventListener('click', (e) => {
        if (!this.panel.contains(e.target) && !e.target.closest('.plyr__control--quality')) {
          this.panel.classList.remove('active');
        }
      });

      const wrapper = this.player.elements.container;
      wrapper.appendChild(this.panel);
    }

    _select(label, height) {
      if (label === this.currentLabel) { this.hidePanel(); return; }
      this.currentLabel = label;

      this.panel.querySelectorAll('.quality-option').forEach(opt => {
        const active = opt.dataset.label === label;
        opt.classList.toggle('active', active);
        opt.querySelector('.quality-check').textContent = active ? '✓' : '';
      });

      this.hidePanel();
      if (this.onSelect) this.onSelect(height);
    }

    togglePanel() {
      this.panel.classList.toggle('active');
      if (this.onToggle) this.onToggle();
    }

    hidePanel() { this.panel.classList.remove('active'); }
    destroy() { if (this.panel) this.panel.remove(); }
  }

  // ── External URL handling (YouTube / Google Drive) ──────────────────────
  // Simplified: backend returns a single URL with combined audio+video.
  // No separate audio element, no fragile audio syncer.
  const externalUrl = videoEl.dataset.externalUrl;

  let _urlRefreshTimer = null;
  let _refreshingUrl = false;

  let _currentQualityHeight = null;  // set when user switches quality

  async function _refreshStreamUrl() {
    if (_refreshingUrl) return;
    _refreshingUrl = true;
    try {
      let url = `/rooms/${roomId}/stream/?refresh=1`;
      if (_currentQualityHeight && _currentQualityHeight > 360) {
        url += `&quality=${_currentQualityHeight}`;
      }
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.url && data.url !== videoEl.src) {
        const ct = player.currentTime;
        const wasPaused = player.paused;
        if (data.url.includes('.m3u8') && hls) {
          hls.loadSource(data.url);
        } else {
          videoEl.src = data.url;
        }
        // Refresh DASH audio if present
        if (data.audio_url && data.audio_url !== audioEl.src) {
          audioEl.src = data.audio_url;
          audioEl.currentTime = ct;
          if (!wasPaused) audioEl.play().catch(() => {});
        } else if (!data.audio_url) {
          audioEl.src = '';
        }
        videoEl.currentTime = ct;
        if (!wasPaused) player.play().catch(() => {});
      }
      if (data.expires_at) _scheduleUrlRefresh(data.expires_at);
    } catch (err) {
      console.error('URL refresh failed:', err);
      setTimeout(_refreshStreamUrl, 30000);
    } finally {
      _refreshingUrl = false;
    }
  }

  function _scheduleUrlRefresh(expiresAt) {
    if (_urlRefreshTimer) { clearTimeout(_urlRefreshTimer); _urlRefreshTimer = null; }
    if (!expiresAt) return;
    const delay = (expiresAt * 1000) - Date.now() - 90000;
    if (delay <= 0) { _refreshStreamUrl(); return; }
    _urlRefreshTimer = setTimeout(_refreshStreamUrl, delay);
  }

  if (externalUrl) {
    fetch(`/rooms/${roomId}/stream/`)
      .then(res => res.json())
      .then(data => {
        if (data.url) {
          // Retry button injection now that Plyr controls definitely exist
          _ensureCustomButtons();

          if (data.url.includes('.m3u8') && hls) {
            hls.loadSource(data.url);
          } else {
            videoEl.src = data.url;
          }
          if (data.expires_at) _scheduleUrlRefresh(data.expires_at);

          // Init quality selector if multiple qualities available
          if (data.qualities && data.qualities.length > 1 && qualityBtn) {
            qualityBtn.style.display = '';
            const defLabel = (data.default_height)
              ? `${data.default_height}p`
              : data.qualities[data.qualities.length - 1]?.label;
            qualityManager = new QualityManager(player, data.qualities, roomId, defLabel);
            qualityManager.onToggle = () => { if (effectsManager) effectsManager.hidePanel(); };
            qualityManager.onSelect = async (height) => {
              _currentQualityHeight = height;
              const ct = player.currentTime;
              const wasPaused = player.paused;
              suppressEvent = true;
              setTimeout(() => { suppressEvent = false; }, 600);
              try {
                const res = await fetch(`/rooms/${roomId}/stream/?refresh=1&quality=${height}`);
                const qData = await res.json();
                if (!qData.url) return;

                function resumePlayback() {
                  videoEl.currentTime = ct;
                  if (!wasPaused) player.play().catch(() => {});
                  // Sync audio position after video metadata loads
                  if (qData.audio_url && audioEl.src) {
                    audioEl.currentTime = ct;
                  }
                }

                if (qData.url.includes('.m3u8') && hls) {
                  hls.loadSource(qData.url);
                } else {
                  videoEl.src = qData.url;
                  if (qData.audio_url) {
                    audioEl.muted = true;
                    audioEl.volume = videoEl.volume;
                    audioEl.src = qData.audio_url;
                    audioEl.play().catch(() => {});  // muted autoplay always allowed
                    audioEl.addEventListener('canplay', () => {
                      audioEl.currentTime = ct;
                      audioEl.muted = false;
                    }, { once: true });
                  } else {
                    audioEl.pause();
                    audioEl.src = '';
                  }
                }

                // Wait for video metadata before seeking; fallback after 5s
                const loadTimeout = setTimeout(() => {
                  videoEl.removeEventListener('loadedmetadata', resumePlayback);
                  resumePlayback();
                }, 5000);
                videoEl.addEventListener('loadedmetadata', () => {
                  clearTimeout(loadTimeout);
                  resumePlayback();
                }, { once: true });
              } catch (e) {
                console.error('Quality switch failed:', e);
              }
            };
          }

          if (window.pendingPlayerState) {
            _applyPendingState();
          } else {
            setTimeout(() => { waitingForInitialState = false; setSyncingUI(false); }, 500);
          }
        } else {
          console.error('External stream error:', data.error || 'No URL');
          waitingForInitialState = false;
          setSyncingUI(false);
        }
      })
      .catch(err => {
        console.error('External URL fetch failed:', err);
        waitingForInitialState = false;
        setSyncingUI(false);
      });

    function _applyPendingState() {
      const st = window.pendingPlayerState;
      window.pendingPlayerState = null;
      const latency = st.ts ? (Date.now() - st.ts) / 1000 : 0;
      const target = st.target !== undefined ? st.target : (st.time + latency);
      if (target !== null) videoEl.currentTime = target;
      if (st.isPlaying) {
        player.play().catch(() => {});
      } else {
        player.pause();
      }
      waitingForInitialState = false;
      setSyncingUI(false);
    }
  }

  const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${wsScheme}://${window.location.host}/ws/room/${roomId}/`;

  const socket = new ReconnectingWebSocket(wsUrl, [], {
    minDelay: 500,
    maxDelay: 25000,
    jitter: 0.25,
    heartbeatInterval: 20000,
    heartbeatTimeout: 8000,
    clientId: uuidv4(),
    requestStateOnOpen: true,
  });
  window.roomSocket = socket;

  effectsManager = new EffectsManager(player, socket);

  const playlistItems = document.querySelectorAll(".playlist-item");
  const currentEpisodeLabel = document.getElementById("current-episode");

  socket.addEventListener('open', () => console.log("🔌 WS connected"));
  socket.addEventListener('close', (ev) => {
    console.log("🔌 WS disconnected, code:", ev.code);
    if (ev.code === 4003) {
      const wrapper = videoEl.closest('.video-wrapper') || videoEl.parentElement;
      if (wrapper) {
        let overlay = wrapper.querySelector('.auth-overlay');
        if (!overlay) {
          overlay = document.createElement('div');
          overlay.className = 'auth-overlay';
          overlay.innerHTML = `
            <div class="auth-overlay-content">
              <i class="bi bi-lock-fill"></i>
              <p>Для просмотра необходимо <a href="/accounts/login/?next=${encodeURIComponent(window.location.pathname)}">войти в аккаунт</a></p>
            </div>`;
          wrapper.style.position = 'relative';
          wrapper.appendChild(overlay);
        }
      }
    }
  });
  socket.addEventListener('error', e => console.error("🔌 WS error", e));

  function sendCmd(type) {
    if (waitingForInitialState || suppressEvent || socket.readyState !== WebSocket.OPEN) return;
    const msg = { type, time: player.currentTime, ts: Date.now() };
    socket.sendSafe(msg);
  }

  player.on("play", () => { if (!suppressEvent) sendCmd("play"); });
  player.on("pause", () => { if (!suppressEvent) sendCmd("pause"); });
  player.on("seeked", () => {
    if (suppressEvent) return;
    const now = Date.now();
    if (now - lastSeekSent < 400) return;
    lastSeekSent = now;
    sendCmd("seek");
  });

  // ── Host keyframe broadcaster (2s interval) ──────────────────────────────
  if (isHost) {
    setInterval(() => {
      if (!player.paused && socket.readyState === WebSocket.OPEN) {
        socket.sendSafe({ type: "keyframe", time: player.currentTime, ts: Date.now() });
      }
    }, 2000);
  }

  // ── Drift correction ─────────────────────────────────────────────────────
  // δ < 4s  → no action (tolerate network jitter)
  // 4–10s   → smooth seek (no jarring stops)
  // > 10s   → hard seek
  function applyTimeCorrection(targetTime) {
    if (waitingForInitialState) return;
    const delta = targetTime - player.currentTime;
    const absDelta = Math.abs(delta);

    if (absDelta < 4.0) return;

    if (absDelta > 10.0) {
      videoEl.currentTime = targetTime;
      return;
    }

    // Smooth seek: jump close then let buffer catch up
    const seekTarget = player.currentTime + (delta * 0.6);
    videoEl.currentTime = seekTarget;
  }

  // ── Playlist helpers ─────────────────────────────────────────────────────
  function highlightItem(item) {
    playlistItems.forEach(i => i.classList.remove("active"));
    if (item) item.classList.add("active");
  }
  function setCurrentLabel(season, episode, title) {
    if (!currentEpisodeLabel) return;
    currentEpisodeLabel.textContent = `Сезон ${season}, Серия ${episode} — ${title}`;
  }

  async function applyPlaylistChangeLocally(item, { play = true } = {}) {
    if (!item) return;
    const hlsUrl = item.dataset.hlsUrl || item.getAttribute("data-hls-url");
    const season = item.dataset.season;
    const episode = item.dataset.episode;
    const title = item.dataset.title;

    suppressEvent = true;
    setTimeout(() => { suppressEvent = false; }, 800);
    if (Hls.isSupported() && hls) {
      hls.loadSource(hlsUrl);
    } else {
      videoEl.src = hlsUrl;
    }
    highlightItem(item);
    setCurrentLabel(season, episode, title);
    if (play && !waitingForInitialState) {
      setTimeout(async () => {
        try { await player.play(); } catch (e) { console.warn("autoplay blocked", e); }
      }, 200);
    }
  }

  let pendingPlaylistItemId = null;

  function sendPlaylistSelect(item) {
    const itemId = item.dataset.videoId || item.dataset.hlsUrl || item.getAttribute("data-hls-url");
    pendingPlaylistItemId = itemId;

    if (socket.readyState !== WebSocket.OPEN) {
      applyPlaylistChangeLocally(item);
      return;
    }
    const payload = {
      type: "playlist_select",
      ts: Date.now(),
      client_id: socket.opts ? socket.opts.clientId : undefined,
      item: {
        video_id: item.dataset.videoId,
        hls_url: item.dataset.hlsUrl || item.getAttribute("data-hls-url"),
        season: item.dataset.season,
        episode: item.dataset.episode,
        title: item.dataset.title
      }
    };
    socket.sendSafe(payload);
    applyPlaylistChangeLocally(item, { play: true });
  }

  playlistItems.forEach(item => {
    item.style.cursor = "pointer";
    item.addEventListener("click", () => sendPlaylistSelect(item));
  });

  // ── Keyframe timeout (host failover detection) ─────────────────────────
  function _resetKeyframeTimeout() {
    if (_keyframeTimeout) clearTimeout(_keyframeTimeout);
    _keyframeTimeout = setTimeout(() => {
      _hostAlive = false;
      console.warn('No keyframes for 10s — host may be disconnected');
    }, 10000);
  }

  // ── Central message handler ──────────────────────────────────────────────
  socket.addEventListener('message', (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }

    if (msg.type === "player_state") {
      const st = msg.state;

      clearTimeout(syncTimeout);

      if (!st) {
        waitingForInitialState = false;
        setSyncingUI(false);
        return;
      }

      const latency = st.ts ? (Date.now() - st.ts) / 1000 : 0;
      const target = (typeof st.time === "number") ? (st.time + latency) : null;

      if (st.hls_url) {
        if (Hls.isSupported() && hls) {
          hls.loadSource(st.hls_url);
        } else {
          videoEl.src = st.hls_url;
        }
      }

      if (target !== null) {
        if (videoEl.src === "" && externalUrl) {
          window.pendingPlayerState = { time: st.time, ts: st.ts, target: target, isPlaying: st.is_playing };
          return;
        }
        suppressEvent = true;
        setTimeout(() => { suppressEvent = false; }, 600);
        player.currentTime = target;
      }

      if (st.is_playing) {
        player.play().catch(() => {});
      } else {
        player.pause();
      }

      waitingForInitialState = false;
      setSyncingUI(false);

      let targetEl = null;
      if (st.video_id) {
        targetEl = document.querySelector(`.playlist-item[data-video-id="${st.video_id}"]`);
      }
      if (!targetEl && st.hls_url) {
        targetEl = Array.from(playlistItems).find(pi =>
          (pi.dataset.hlsUrl === st.hls_url) || (pi.getAttribute("data-hls-url") === st.hls_url)
        );
      }
      if (targetEl) {
        highlightItem(targetEl);
        setCurrentLabel(targetEl.dataset.season, targetEl.dataset.episode, targetEl.dataset.title);
      } else if (st.hls_url) {
        setCurrentLabel("-", "-", "Видео");
      }
      return;
    }

    if (msg.type === "playlist_change") {
      const it = msg.item || {};
      const echoId = it.video_id || it.hls_url;
      if (pendingPlaylistItemId && pendingPlaylistItemId === echoId) {
        pendingPlaylistItemId = null;
        return;
      }
      pendingPlaylistItemId = null;

      let targetItem = null;
      if (it.video_id) targetItem = document.querySelector(`.playlist-item[data-video-id="${it.video_id}"]`);
      if (!targetItem && it.hls_url) {
        targetItem = Array.from(playlistItems).find(pi =>
          (pi.dataset.hlsUrl === it.hls_url) || (pi.getAttribute("data-hls-url") === it.hls_url)
        );
      }
      if (targetItem) {
        applyPlaylistChangeLocally(targetItem, { play: true });
      } else if (it.hls_url) {
        if (Hls.isSupported() && hls) hls.loadSource(it.hls_url);
        else videoEl.src = it.hls_url;
        setTimeout(() => player.play().catch(() => {}), 200);
        setCurrentLabel(it.season || "-", it.episode || "-", it.title || "Видео");
      }
      return;
    }

    if (["play", "pause", "seek", "keyframe"].includes(msg.type)) {
      if (waitingForInitialState) return;

      const latency = msg.ts ? (Date.now() - msg.ts) / 1000 : 0;
      const target = (typeof msg.time === "number") ? (msg.time + latency) : null;

      switch (msg.type) {
        case "play":
          suppressEvent = true;
          setTimeout(() => { suppressEvent = false; }, 300);
          if (target !== null) player.currentTime = target;
          player.play().catch(() => {});
          break;

        case "pause":
          suppressEvent = true;
          setTimeout(() => { suppressEvent = false; }, 300);
          if (target !== null) player.currentTime = target;
          player.pause();
          break;

        case "seek":
          if (target !== null && Math.abs(player.currentTime - target) > 0.5) {
            suppressEvent = true;
            setTimeout(() => { suppressEvent = false; }, 400);
            player.currentTime = target;
          }
          break;

        case "keyframe":
          _hostAlive = true;
          _resetKeyframeTimeout();
          _lastKeyframeTime = target;
          _lastKeyframeTs = Date.now();
          if (target !== null && !player.paused) {
            applyTimeCorrection(target);
          }
          break;
      }
      return;
    }

    if (msg.type === "effect") {
      if (effectsManager) effectsManager.handleEffect(msg);
      return;
    }
  });

  // ── Fallback: load first playlist item if no state received ──────────────
  if (playlistItems.length > 0) {
    setTimeout(() => {
      if (!waitingForInitialState) return;
      const hasSrc = videoEl && videoEl.src && videoEl.src !== "" && videoEl.src !== window.location.href;
      if (!hasSrc) {
        applyPlaylistChangeLocally(playlistItems[0], { play: false });
      }
      waitingForInitialState = false;
    }, 1500);
  }

  window.addEventListener("beforeunload", () => {
    try { socket.close(); } catch (e) { }
    try { if (player && typeof player.destroy === "function") player.destroy(); } catch (e) { }
    try { if (hls) hls.destroy(); } catch (e) { }
    if (qualityManager) qualityManager.destroy();
    if (_urlRefreshTimer) clearTimeout(_urlRefreshTimer);
    if (_keyframeTimeout) clearTimeout(_keyframeTimeout);
    if (_audioSyncTimer) clearInterval(_audioSyncTimer);
    if (audioEl) { audioEl.pause(); audioEl.src = ''; }
  });
});