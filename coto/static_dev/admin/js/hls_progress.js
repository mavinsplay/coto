function updateHlsProgress(vid, percent, status, filesize) {
    // Основной прогресс-блок
    const bar = document.querySelector("#hls-bar");
    const text = document.querySelector("#hls-percent-text");
    const statusEl = document.querySelector("#hls-status");
    const logEl = document.querySelector("#hls-log");

    if (bar) bar.style.width = percent + "%";
    if (text) text.textContent = percent + "%";
    if (statusEl) statusEl.textContent = status;

    if (percent >= 100) {
        if (bar) bar.classList.add("hls-success");
        if (text) text.textContent = "Success";
        if (statusEl) statusEl.textContent = "Success";
    }

    // Обновляем отдельные поля статуса и размера файла
    const statusField = document.querySelector('#hls-status-field[data-video-id="' + vid + '"]');
    if (statusField) {
        const statusBadge = statusField.querySelector('.hls-status-badge');
        if (statusBadge) {
            statusBadge.textContent = status || "—";
            // Обновляем CSS класс для стилизации
            statusBadge.className = 'hls-status-badge hls-status-' + (status || "unknown").toLowerCase().replace(/\s+/g, "-");
        }
    }

    const filesizeField = document.querySelector('#hls-filesize-field[data-video-id="' + vid + '"]');
    if (filesizeField) {
        const filesizeValue = filesizeField.querySelector('.hls-filesize-value');
        if (filesizeValue && filesize !== undefined) {
            filesizeValue.textContent = filesize;
        }
    }

    // Мини-полоски в списке
    const miniBars = document.querySelectorAll('.hls-mini-bar[data-video-id="' + vid + '"]');
    miniBars.forEach(el => {
        const fill = el.querySelector(".hls-mini-fill");
        const miniStatus = el.querySelector(".hls-mini-status");
        const miniFilesize = el.querySelector(".hls-mini-filesize");

        if (fill) { 
            fill.style.width = percent + "%"; 
            fill.textContent = percent + "%"; 
        }
        if (miniStatus) miniStatus.textContent = status || "—";
        if (miniFilesize && filesize !== undefined) miniFilesize.textContent = filesize;
    });
}

(function() {
    function q(sel, root) { return (root || document).querySelector(sel); }

    function startPolling(videoId, root) {
        const url = window.location.pathname.replace(/\/$/, "") + videoId + "/hls_progress/";

        function fetchOnce() {
            fetch(url, { credentials: "same-origin" })
            .then(resp => { if(!resp.ok) throw resp; return resp.json(); })
            .then(data => {
                const percent = data.progress || 0;
                const status = data.status || "";
                const filesize = data.filesize || "";
                const log = data.log_tail || "";

                // обновляем все поля
                updateHlsProgress(videoId, percent, status, filesize);

                const logElem = q("#hls-log", root);
                if (logElem) logElem.innerHTML = log.replace(/\n/g, "<br/>");

                // Продолжаем polling только если процесс не завершен
                if (status && status !== "done" && status !== "error" && status !== "completed" && percent < 100) {
                    setTimeout(fetchOnce, 2000);
                }
            })
            .catch(err => {
                console.error("Could not fetch hls progress", err);
                // Retry с увеличенным интервалом при ошибке
                setTimeout(fetchOnce, 4000);
            });
        }

        fetchOnce();
    }

    function startPollingForListView(videoId) {
        const url = "/admin/upload/video/" + videoId + "/hls_progress/";

        function fetchOnce() {
            fetch(url, { credentials: "same-origin" })
            .then(resp => { if(!resp.ok) throw resp; return resp.json(); })
            .then(data => {
                const percent = data.progress || 0;
                const status = data.status || "";
                const filesize = data.filesize || "";

                updateHlsProgress(videoId, percent, status, filesize);

                // Продолжаем polling только если процесс не завершен
                if (status && status !== "done" && status !== "error" && status !== "completed" && percent < 100) {
                    setTimeout(fetchOnce, 5000);
                }
            })
            .catch(err => {
                console.error("Could not fetch hls progress for video", videoId, err);
                setTimeout(fetchOnce, 8000);
            });
        }

        fetchOnce();
    }

    document.addEventListener("DOMContentLoaded", function() {
        // Polling для детальной страницы
        const root = document.getElementById("hls-progress-root");
        if (root) {
            const vid = root.getAttribute("data-video-id");
            if (vid) startPolling(vid, document);
        }

        // Polling для отдельных полей статуса и размера файла
        const statusFields = document.querySelectorAll('#hls-status-field[data-video-id]');
        const filesizeFields = document.querySelectorAll('#hls-filesize-field[data-video-id]');
        
        // Собираем уникальные video ID из всех полей
        const videoIds = new Set();
        
        statusFields.forEach(el => {
            const vid = el.getAttribute("data-video-id");
            if (vid) videoIds.add(vid);
        });
        
        filesizeFields.forEach(el => {
            const vid = el.getAttribute("data-video-id");
            if (vid) videoIds.add(vid);
        });

        // Запускаем polling для каждого unique video ID
        videoIds.forEach(vid => {
            startPollingForListView(vid);
        });

        // Polling для мини-полосок в списке
        document.querySelectorAll('.hls-mini-bar[data-video-id]').forEach(el => {
            const vid = el.getAttribute("data-video-id");
            if (vid && !videoIds.has(vid)) {
                startPollingForListView(vid);
            }
        });
    });
})();

