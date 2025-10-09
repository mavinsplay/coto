// static/upload/js/chunked_admin.js
(function () {
  const DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024;

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

  function bytesToMB(b) {
    return (b / (1024 * 1024)).toFixed(2);
  }

  (function ensureSpark() {
    if (window.SparkMD5) return;
    const s = document.createElement("script");
    s.src = "/static/upload/js/spark-md5.min.js";
    s.async = true;
    s.onload = () => console.debug("SparkMD5 loaded");
    s.onerror = () => console.warn("Не удалось загрузить SparkMD5 по /static/upload/js/spark-md5.min.js");
    document.head.appendChild(s);
  })();

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".chunked-uploader").forEach((root) => {
      try {
        const START_URL = root.dataset.startUrl || "/chunked-upload/start/";
        const COMPLETE_URL = root.dataset.completeUrl || "/chunked-upload/complete/";
        const CHUNK_SIZE = Number(root.dataset.chunkSize) || DEFAULT_CHUNK_SIZE;

        const input = root.querySelector(".chunked-input");
        const hiddenUploadId = root.querySelector(".chunked-upload-id");
        const drop = root.querySelector(".drop-area");
        const status = root.querySelector(".upload-status");
        const progressBar = root.querySelector(".progress-bar");
        const uploadedEl = root.querySelector(".uploaded");
        const totalEl = root.querySelector(".total");
        const speedEl = root.querySelector(".speed");
        const etaEl = root.querySelector(".eta");
        const cancelBtn = root.querySelector(".btn.cancel");
        const pauseBtn = root.querySelector(".btn.pause");

        if (!input || !drop) {
          console.warn("chunked-uploader: missing required elements (input/drop) in", root);
          return;
        }

        const originalInputName = input.getAttribute("name");

        let controller = { canceled: false, paused: false };

        ["dragenter", "dragover"].forEach(ev =>
          drop.addEventListener(ev, (e) => { 
            e.preventDefault(); 
            e.stopPropagation(); 
            drop.classList.add("dragover"); 
          })
        );
        
        ["dragleave", "drop"].forEach(ev =>
          drop.addEventListener(ev, (e) => { 
            e.preventDefault(); 
            e.stopPropagation(); 
            drop.classList.remove("dragover"); 
          })
        );
        
        drop.addEventListener("drop", (e) => {
          const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
          if (f) startUpload(f);
        });

        drop.addEventListener("click", () => {
          try { 
            input.click(); 
          } catch (err) { 
            console.error("Не удалось вызвать input.click():", err); 
          }
        });

        input.addEventListener("change", (e) => {
          const f = e.target.files && e.target.files[0];
          if (f) startUpload(f);
        });

        if (cancelBtn) {
          cancelBtn.addEventListener("click", () => {
            controller.canceled = true;
            cleanup(true);
          });
        }

        if (pauseBtn) {
          pauseBtn.addEventListener("click", () => {
            controller.paused = !controller.paused;
            pauseBtn.textContent = controller.paused ? "Продолжить" : "Пауза";
          });
        }

        function cleanup(restoreName = false) {
          controller.canceled = false;
          controller.paused = false;
          if (status) status.hidden = true;
          if (progressBar) progressBar.style.width = "0%";
          if (speedEl) speedEl.textContent = "0 MB/s";
          if (etaEl) etaEl.textContent = "—";
          if (uploadedEl) uploadedEl.textContent = "0 MB";
          if (totalEl) totalEl.textContent = "0 MB";

          if (restoreName && input && originalInputName) {
            input.setAttribute("name", originalInputName);
          }
          
          if (hiddenUploadId) {
            hiddenUploadId.value = "";
          }
        }

        async function sendChunk(slice, isFirst, start, end, total, upload_id) {
          const fd = new FormData();
          fd.append("file", slice, slice.name || "blob");
          if (!isFirst && upload_id) fd.append("upload_id", upload_id);

          const contentRange = `bytes ${start}-${end - 1}/${total}`;
          const headers = { "X-CSRFToken": csrftoken, "Content-Range": contentRange };

          let resp;
          let textBody = null;
          try {
            resp = await fetch(START_URL, {
              method: "POST",
              credentials: "same-origin",
              headers,
              body: fd,
            });
          } catch (networkErr) {
            console.error("Network error while sending chunk:", networkErr);
            throw networkErr;
          }

          try {
            textBody = await resp.text();
            let json = null;
            try { 
              json = JSON.parse(textBody); 
            } catch (e) { 
              /* not JSON */ 
            }
            console.debug("chunk response", resp.status, json ?? textBody);
            if (!resp.ok) {
              throw new Error(`HTTP ${resp.status} — ${textBody}`);
            }
            return json;
          } catch (err) {
            console.error("Ошибка при отправке чанка:", err, "response body:", textBody);
            throw err;
          }
        }

        async function startUpload(file) {
          try {
            controller.canceled = false;
            controller.paused = false;
            if (status) status.hidden = false;
            const total = file.size;
            if (totalEl) totalEl.textContent = bytesToMB(total) + " MB";

            let offset = 0;
            let upload_id = null;
            let bytesSent = 0;
            let lastTime = performance.now();
            let lastBytes = 0;

            while (offset < total) {
              if (controller.canceled) throw new Error("canceled");
              if (controller.paused) {
                await new Promise(resolve => {
                  const check = setInterval(() => {
                    if (!controller.paused) {
                      clearInterval(check);
                      resolve();
                    }
                  }, 200);
                });
              }

              const end = Math.min(offset + CHUNK_SIZE, total);
              const slice = file.slice(offset, end);
              const isFirst = offset === 0;

              const json = await sendChunk(slice, isFirst, offset, end, total, upload_id);
              if (json && json.upload_id) upload_id = json.upload_id;

              offset = end;
              bytesSent = offset;

              if (progressBar) {
                const pct = Math.round((bytesSent / total) * 100);
                progressBar.style.width = pct + "%";
              }
              if (uploadedEl) uploadedEl.textContent = bytesToMB(bytesSent) + " MB";

              const now = performance.now();
              const dt = (now - lastTime) / 1000;
              if (dt > 0.25) {
                const db = bytesSent - lastBytes;
                const speedBps = db / dt;
                const speedMBs = (speedBps / (1024 * 1024)).toFixed(2);
                if (speedEl) speedEl.textContent = `${speedMBs} MB/s`;
                const remaining = total - bytesSent;
                const etaSec = remaining / (speedBps || 1);
                const mins = Math.floor(etaSec / 60);
                const secs = Math.floor(etaSec % 60);
                if (etaEl) etaEl.textContent = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                lastTime = now;
                lastBytes = bytesSent;
              }
            }

            let md5 = "";
            try { 
              md5 = await computeMD5(file); 
            } catch (e) { 
              console.warn("Не удалось посчитать MD5 (продолжаем без него):", e); 
            }

            const fd = new FormData();
            if (upload_id) fd.append("upload_id", upload_id);
            if (md5) fd.append("md5", md5);
            fd.append("title", file.name);

            const finalizeResp = await fetch(COMPLETE_URL, {
              method: "POST",
              credentials: "same-origin",
              headers: { "X-CSRFToken": csrftoken },
              body: fd,
            });

            if (!finalizeResp.ok) {
              const t = await finalizeResp.text();
              throw new Error("Ошибка финализации: " + finalizeResp.status + " — " + t);
            }
            const resJson = await finalizeResp.json();

            const uid = resJson.video_id || resJson.upload_id || resJson.id || null;
            if (uid && hiddenUploadId) {
              hiddenUploadId.value = uid;
            }

            try {
              input.value = "";
              if (originalInputName) {
                input.removeAttribute("name");
              }
            } catch (e) { 
              /* ignore */ 
            }

            if (progressBar) progressBar.style.width = "100%";
            if (speedEl) speedEl.textContent = "Завершено";
            if (etaEl) etaEl.textContent = "0s";
            console.info("Upload complete:", resJson);
          } catch (err) {
            if (err.message === "canceled") {
              console.info("Upload canceled by user");
            } else {
              console.error("Upload error:", err);
              if (status) status.hidden = false;
              if (originalInputName) input.setAttribute("name", originalInputName);
            }
          }
        }

        function computeMD5(file) {
          return new Promise((resolve, reject) => {
            if (!window.SparkMD5) {
              return reject("SparkMD5 not loaded");
            }
            const chunkSize = 4 * 1024 * 1024;
            const spark = new SparkMD5.ArrayBuffer();
            const reader = new FileReader();
            let cursor = 0;

            reader.onerror = () => reject("Ошибка чтения файла для md5");
            reader.onload = (e) => {
              spark.append(e.target.result);
              cursor += chunkSize;
              if (cursor < file.size) {
                readNext();
              } else {
                const hex = spark.end();
                resolve(hex);
              }
            };

            function readNext() {
              const slice = file.slice(cursor, Math.min(cursor + chunkSize, file.size));
              reader.readAsArrayBuffer(slice);
            }

            readNext();
          });
        }

      } catch (err) {
        console.error("Ошибка инициализации chunked-uploader для root:", root, err);
      }
    });
  });
})();