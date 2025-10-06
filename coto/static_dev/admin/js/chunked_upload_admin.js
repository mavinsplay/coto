// static/admin/js/chunked_upload_admin.js
(function () {
  /* ------------------ Helpers ------------------ */
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  const csrftoken = getCookie("csrftoken");

  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }
  function humanTime(s) {
    if (!isFinite(s) || s < 0) return "--:--";
    const sec = Math.floor(s % 60);
    const min = Math.floor((s / 60) % 60);
    const hr = Math.floor(s / 3600);
    return (hr ? hr + ":" : "") + (min < 10 ? "0" + min : min) + ":" + (sec < 10 ? "0" + sec : sec);
  }

  function speedToMBps(bytesPerSec) {
    const mb = bytesPerSec / (1024 * 1024);
    return mb.toFixed(2) + " MB/s";
  }

  /* ------------------ Theme helpers ------------------ */
  const THEME_KEY = "chunked_upload_theme"; // values: "light" | "dark"
  function applyThemeToWidget(root, theme) {
    if (!root) return;
    if (theme === "dark") root.classList.add("theme-dark");
    else root.classList.remove("theme-dark");
    root.setAttribute("data-theme", theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) {}
  }
  function detectInitialTheme() {
    try {
      const saved = localStorage.getItem(THEME_KEY);
      if (saved === "light" || "dark") return saved;
    } catch (e) {}
    // fallback to prefers-color-scheme
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
    return "light";
  }

  /* ------------------ Existing uploader logic (chunked) ------------------ */

  function ensureSparkMD5() {
    if (window.SparkMD5) return Promise.resolve(window.SparkMD5);
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://cdnjs.cloudflare.com/ajax/libs/spark-md5/3.0.2/spark-md5.min.js";
      s.async = true;
      s.onload = () => (window.SparkMD5 ? resolve(window.SparkMD5) : reject(new Error("SparkMD5 load failed")));
      s.onerror = () => reject(new Error("SparkMD5 load failed"));
      document.head.appendChild(s);
    });
  }

  function computeFileMD5(file, onProgress) {
    return new Promise(async (resolve, reject) => {
      try {
        const Spark = await ensureSparkMD5();
        const chunkSize = 2 * 1024 * 1024;
        const chunks = Math.ceil(file.size / chunkSize);
        let current = 0;
        const spark = new Spark.ArrayBuffer();
        const reader = new FileReader();
        reader.onerror = () => reject(new Error("FileReader error"));
        reader.onload = (e) => {
          spark.append(e.target.result);
          current++;
          if (onProgress) onProgress(current, chunks);
          if (current < chunks) loadNext();
          else resolve(spark.end());
        };
        function loadNext() {
          const start = current * chunkSize;
          const end = Math.min(start + chunkSize, file.size);
          const slice = file.slice(start, end);
          reader.readAsArrayBuffer(slice);
        }
        loadNext();
      } catch (err) { reject(err); }
    });
  }

  function createChunkedUploader(file) {
    const CHUNK_SIZE = 2 * 1024 * 1024;
    const urlBase = window.location.origin + "/upload/";
    let uploadId = null;
    let offset = 0;
    let aborted = false;
    let controller = null;

    async function sendChunk(start, end) {
      if (aborted) throw new Error("aborted");
      const chunk = file.slice(start, end);
      const form = new FormData();
      form.append("file", chunk, file.name);
      if (uploadId) form.append("upload_id", uploadId);

      const headers = new Headers();
      headers.append("X-CSRFToken", csrftoken);
      headers.append("Content-Range", `bytes ${start}-${end - 1}/${file.size}`);

      controller = new AbortController();
      const resp = await fetch(urlBase + "chunked-upload/", {
        method: "POST",
        headers: headers,
        body: form,
        credentials: "same-origin",
        signal: controller.signal,
      });

      const text = await resp.text().catch(() => "");
      let data = null;
      try { data = text ? JSON.parse(text) : null; } catch (e) {}

      if (!resp.ok) {
        throw { status: resp.status, text, data };
      }
      if (data && data.upload_id) uploadId = data.upload_id;
      if (data && typeof data.offset !== "undefined") offset = data.offset;
      return data;
    }

    async function finalize(md5) {
      if (aborted) throw new Error("aborted");
      const form = new FormData();
      form.append("upload_id", uploadId || "");
      if (md5) form.append("md5", md5);

      const headers = new Headers();
      headers.append("X-CSRFToken", csrftoken);

      const resp = await fetch(urlBase + "chunked-upload/complete/", {
        method: "POST",
        headers: headers,
        body: form,
        credentials: "same-origin",
      });
      const text = await resp.text().catch(() => "");
      let data = null;
      try { data = text ? JSON.parse(text) : null; } catch (e) {}
      return { resp, text, data };
    }

    async function start(onProgress) {
      const total = file.size;
      let pos = 0;
      let lastTime = performance.now();
      let lastUploaded = 0;

      while (pos < total) {
        const end = Math.min(pos + CHUNK_SIZE, total);
        await sendChunk(pos, end);
        pos = offset || end;

        const now = performance.now();
        const dt = (now - lastTime) / 1000 || 0.001;
        const dbytes = pos - lastUploaded;
        const speed = dbytes / dt; // bytes/sec
        const pct = Math.floor((pos / total) * 100);

        lastTime = now;
        lastUploaded = pos;

        if (onProgress) onProgress({ uploaded: pos, total, pct, speed });
      }

      if (!uploadId) throw new Error("No upload id from server");

      let finish = await finalize(null);
      if (!finish.resp.ok) {
        const txt = (finish.text || "").toLowerCase();
        if (txt.includes("md5") || (finish.data && finish.data.error && finish.data.error.toLowerCase().includes("md5"))) {
          if (onProgress) onProgress({ md5Phase: true });
          const md5 = await computeFileMD5(file, (cur, chunks) => {
            if (onProgress) onProgress({ md5Percent: Math.round((cur / chunks) * 100) });
          });
          finish = await finalize(md5);
        } else {
          throw { status: finish.resp.status, text: finish.text, data: finish.data };
        }
      }

      if (!finish.resp.ok) throw { status: finish.resp.status, text: finish.text, data: finish.data };

      return finish.data;
    }

    function cancel() {
      aborted = true;
      if (controller) controller.abort();
    }

    return { start, cancel };
  }

  /* ------------------ UI wiring & themes ------------------ */
  function initChunkedWidget(widgetRoot) {
    const fileInput = widgetRoot.querySelector('.chunked-file-input');
    const pathInput = widgetRoot.querySelector('.chunked-path-input');
    const form = widgetRoot.closest('form');

    // Блокируем стандартную отправку файла при наличии chunked_path
    if (form) {
        form.addEventListener('submit', (e) => {
            if (pathInput && pathInput.value) {
                // Отключаем file input чтобы предотвратить его отправку
                if (fileInput) {
                    fileInput.disabled = true;
                    fileInput.value = '';
                }
            }
        });
    }

    // После успешной загрузки чанками
    uploader.on('complete', (response) => {
        if (response && response.chunked_path) {
            // Записываем путь в hidden input
            if (pathInput) {
                pathInput.value = response.chunked_path;
            }
            // Отключаем нативный file input
            if (fileInput) {
                fileInput.disabled = true;
                fileInput.value = '';
            }
        }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".chunked-upload-widget").forEach(initChunkedWidget);
  });

})();
