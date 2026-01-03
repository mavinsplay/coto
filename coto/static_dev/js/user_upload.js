// Chunked Upload для пользователей
(function() {
    'use strict';

    // Конфигурация
    const CONFIG = {
        chunkSize: 1024 * 1024 * 5, // 5MB chunks для быстрой загрузки
        maxRetries: 3,
        retryDelay: 1000,
        maxFileSize: 1024 * 1024 * 1024 * 5, // 5GB
        allowedExtensions: ['mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v', 'mpg', 'mpeg', '3gp', 'ogv'],
        uploadUrl: '/upload/my/chunked/start/',
        completeUrl: '/upload/my/chunked/complete/',
    };

    // Состояние
    const state = {
        uploadMode: 'single',
        files: [],
        uploads: new Map(),
    };

    // Утилиты
    const utils = {
        formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        },

        getCSRFToken() {
            return document.querySelector('[name=csrfmiddlewaretoken]').value;
        },

        generateId() {
            return Math.random().toString(36).substr(2, 9);
        },

        async calculateMD5(file, onProgress) {
            return new Promise((resolve, reject) => {
                const chunkSize = 1024 * 1024 * 5; // 5MB для быстрого MD5
                const chunks = Math.ceil(file.size / chunkSize);
                const spark = new SparkMD5.ArrayBuffer();
                const fileReader = new FileReader();
                let currentChunk = 0;

                fileReader.onload = (e) => {
                    spark.append(e.target.result);
                    currentChunk++;
                    
                    if (onProgress) {
                        onProgress(Math.round((currentChunk / chunks) * 100));
                    }

                    if (currentChunk < chunks) {
                        loadNext();
                    } else {
                        resolve(spark.end());
                    }
                };

                fileReader.onerror = () => {
                    reject(new Error('Ошибка чтения файла'));
                };

                function loadNext() {
                    const start = currentChunk * chunkSize;
                    const end = Math.min(start + chunkSize, file.size);
                    fileReader.readAsArrayBuffer(file.slice(start, end));
                }

                loadNext();
            });
        }
    };

    // Управление файлами
    const fileManager = {
        addFiles(files) {
            const validFiles = [];
            const errors = [];

            Array.from(files).forEach(file => {
                // Проверка расширения
                const extension = file.name.split('.').pop().toLowerCase();
                if (!CONFIG.allowedExtensions.includes(extension)) {
                    errors.push(`${file.name}: недопустимый формат. Разрешены: ${CONFIG.allowedExtensions.join(', ')}`);
                    return;
                }

                // Проверка размера
                if (file.size > CONFIG.maxFileSize) {
                    errors.push(`${file.name}: файл слишком большой (максимум ${utils.formatFileSize(CONFIG.maxFileSize)})`);
                    return;
                }

                validFiles.push({
                    id: utils.generateId(),
                    file: file,
                    name: file.name,
                    size: file.size,
                    status: 'pending',
                    progress: 0,
                    error: null,
                });
            });

            // Показываем ошибки
            if (errors.length > 0) {
                alert('Некоторые файлы не могут быть загружены:\n\n' + errors.join('\n'));
            }

            if (validFiles.length === 0) {
                return;
            }

            const newFiles = validFiles;

            if (state.uploadMode === 'single') {
                state.files = [newFiles[0]];
            } else {
                state.files.push(...newFiles);
            }

            this.render();
        },

        removeFile(fileId) {
            const index = state.files.findIndex(f => f.id === fileId);
            if (index !== -1) {
                state.files.splice(index, 1);
                this.render();
            }
        },

        clearFiles() {
            state.files = [];
            this.render();
        },

        render() {
            const container = document.getElementById('files-container');
            const listSection = document.getElementById('files-list');
            const uploadBtn = document.getElementById('upload-btn');

            if (state.files.length === 0) {
                listSection.style.display = 'none';
                uploadBtn.disabled = true;
                return;
            }

            listSection.style.display = 'block';
            uploadBtn.disabled = false;

            container.innerHTML = state.files.map(file => `
                <div class="file-card" data-file-id="${file.id}">
                    <div class="file-info">
                        <div class="file-icon">
                            <i class="bi bi-file-earmark-play-fill"></i>
                        </div>
                        <div class="file-details">
                            <div class="file-name" title="${file.name}">${file.name}</div>
                            <div class="file-size">${utils.formatFileSize(file.size)}</div>
                        </div>
                        <div class="file-actions">
                            ${file.status === 'pending' ? `
                                <button type="button" class="btn btn-sm btn-outline-danger" onclick="fileManager.removeFile('${file.id}')">
                                    <i class="bi bi-trash"></i>
                                </button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `).join('');
        }
    };

    // Chunked Upload
    class ChunkedUpload {
        constructor(fileInfo, metadata) {
            this.fileInfo = fileInfo;
            this.file = fileInfo.file;
            this.metadata = metadata;
            this.uploadId = null;
            this.offset = 0;
            this.chunks = Math.ceil(this.file.size / CONFIG.chunkSize);
            this.currentChunk = 0;
            this.retries = 0;
        }

        async start() {
            try {
                this.startTime = Date.now(); // Запоминаем время начала
                this.updateStatus('Подготовка...');
                
                // Начинаем загрузку (БЕЗ MD5 сначала, как в админке)
                this.updateStatus('Загрузка...');
                await this.uploadChunks();
                
                // ПОСЛЕ загрузки вычисляем MD5
                this.updateStatus('Вычисление контрольной суммы...');
                const md5 = await utils.calculateMD5(this.file, (progress) => {
                    const md5Progress = 90 + (progress * 0.08); // 90-98%
                    this.updateProgress(md5Progress);
                });
                
                // Завершаем
                this.updateStatus('Обработка...');
                this.updateProgress(98);
                const result = await this.complete(md5);
                
                this.updateStatus('Готово!');
                this.updateProgress(100); // Показываем 100%
                this.fileInfo.status = 'success';
                this.fileInfo.result = result;
                this.updateFileCard('success');
                
                return result;

            } catch (error) {
                console.error('Upload error:', error);
                this.fileInfo.status = 'error';
                this.fileInfo.error = error.message;
                this.updateStatus('Ошибка: ' + error.message);
                this.updateFileCard('error');
                throw error;
            }
        }

        async uploadChunks() {
            while (this.offset < this.file.size) {
                try {
                    const end = Math.min(this.offset + CONFIG.chunkSize, this.file.size);
                    const chunk = this.file.slice(this.offset, end);
                    const isFirst = this.offset === 0;
                    
                    const data = await this.uploadChunk(chunk, isFirst, this.offset, end, this.file.size);
                    
                    // Получаем upload_id из первого ответа
                    if (data && data.upload_id) {
                        this.uploadId = data.upload_id;
                    }
                    
                    // Обновляем offset как в админке
                    this.offset = end;
                    this.currentChunk++;
                    
                    const progress = (this.offset / this.file.size) * 90; // 0-90%
                    // Плавное обновление без скачков
                    requestAnimationFrame(() => this.updateProgress(progress));
                    
                    this.retries = 0;
                } catch (error) {
                    // Для ошибок пытаемся повторить
                    if (this.retries < CONFIG.maxRetries) {
                        this.retries++;
                        console.log('[WARN] Retry', this.retries, 'of', CONFIG.maxRetries);
                        await this.sleep(CONFIG.retryDelay);
                        continue;
                    }
                    throw error;
                }
            }
        }

        async uploadChunk(chunk, isFirst, start, end, total) {
            const formData = new FormData();
            formData.append('file', chunk, this.file.name); // Используем реальное имя файла
            
            // Добавляем upload_id только если это НЕ первый чанк
            if (!isFirst && this.uploadId) {
                formData.append('upload_id', this.uploadId);
            }

            // Content-Range как в админке
            const contentRange = `bytes ${start}-${end - 1}/${total}`;
            
            const response = await fetch(CONFIG.uploadUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': utils.getCSRFToken(),
                    'Content-Range': contentRange,
                },
                body: formData,
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error('[ERROR] Upload failed:', {
                    status: response.status,
                    statusText: response.statusText,
                    contentRange: contentRange,
                    body: errorText
                });
                throw new Error(`Ошибка загрузки (${response.status}): ${response.statusText}`);
            }

            const data = await response.json();
            return data;
        }

        async complete(md5) {
            const formData = new FormData();
            formData.append('upload_id', this.uploadId);
            formData.append('md5', md5);
            
            // Добавляем метаданные
            Object.entries(this.metadata).forEach(([key, value]) => {
                if (value !== null && value !== undefined && value !== '') {
                    formData.append(key, value);
                }
            });

            const response = await fetch(CONFIG.completeUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': utils.getCSRFToken(),
                },
                body: formData,
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error('[ERROR] Complete failed:', {
                    status: response.status,
                    statusText: response.statusText,
                    body: errorText
                });
                throw new Error(`Ошибка завершения (${response.status}): ${response.statusText}`);
            }

            return await response.json();
        }

        updateProgress(percent) {
            this.fileInfo.progress = Math.round(percent);
            
            // Вычисляем оставшееся время и данные
            const now = Date.now();
            const elapsed = (now - this.startTime) / 1000; // секунды
            const uploadedBytes = (percent / 100) * this.file.size;
            const speed = uploadedBytes / elapsed; // байт в секунду
            const remainingBytes = this.file.size - uploadedBytes;
            const remainingTime = remainingBytes / speed; // секунды
            
            this.fileInfo.uploadedMB = (uploadedBytes / 1024 / 1024).toFixed(1);
            this.fileInfo.totalMB = (this.file.size / 1024 / 1024).toFixed(1);
            this.fileInfo.speedMBps = (speed / 1024 / 1024).toFixed(1);
            this.fileInfo.remainingTime = this.formatTime(remainingTime);
            
            this.updateProgressBar();
        }
        
        formatTime(seconds) {
            if (!isFinite(seconds) || seconds < 0) return '--:--';
            
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = Math.floor(seconds % 60);
            
            if (hours > 0) {
                return `${hours}ч ${minutes}м`;
            } else if (minutes > 0) {
                return `${minutes}м ${secs}с`;
            } else {
                return `${secs}с`;
            }
        }

        updateStatus(status) {
            this.fileInfo.statusText = status;
            this.updateProgressBar();
        }

        updateProgressBar() {
            // Ищем карточку в progress секции (не в files-list)
            let card = document.querySelector(`#progress-container [data-file-id="${this.fileInfo.id}"]`);
            
            // Если не нашли, попробуем в files-list
            if (!card) {
                card = document.querySelector(`#files-container [data-file-id="${this.fileInfo.id}"]`);
            }
            
            if (!card) {
                console.warn('Card not found for file:', this.fileInfo.id);
                return;
            }

            let progressHtml = card.querySelector('.file-progress');
            if (!progressHtml) {
                progressHtml = document.createElement('div');
                progressHtml.className = 'file-progress mt-3';
                card.appendChild(progressHtml);
            }

            const detailsHtml = this.fileInfo.uploadedMB ? 
                `<small class="text-muted">
                    ${this.fileInfo.uploadedMB} / ${this.fileInfo.totalMB} MB • 
                    ${this.fileInfo.speedMBps} MB/s • 
                    Осталось: ${this.fileInfo.remainingTime}
                </small>` : '';
            
            progressHtml.innerHTML = `
                <div class="progress-label">
                    <span class="progress-status">${this.fileInfo.statusText || 'Загрузка...'}</span>
                    <span class="progress-percentage">${this.fileInfo.progress}%</span>
                </div>
                <div class="progress mb-2">
                    <div class="progress-bar bg-primary" 
                         role="progressbar" 
                         style="width: ${this.fileInfo.progress}%; transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);"
                         aria-valuenow="${this.fileInfo.progress}" 
                         aria-valuemin="0" 
                         aria-valuemax="100">
                    </div>
                </div>
                ${detailsHtml}
            `;
        }

        updateFileCard(status) {
            const card = document.querySelector(`[data-file-id="${this.fileInfo.id}"]`);
            if (card) {
                card.className = `file-card ${status}`;
            }
        }

        sleep(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }
    }

    // Управление загрузкой
    const uploadManager = {
        async startUpload() {
            if (state.files.length === 0) return;

            // Скрываем форму, показываем прогресс
            document.getElementById('upload-form').style.display = 'none';
            document.getElementById('upload-progress-section').style.display = 'block';

            // Получаем метаданные
            const metadata = this.getMetadata();
            
            // Копируем файлы в прогресс секцию
            this.renderProgressSection();

            const results = [];
            let currentEpisode = metadata.episode_number || 1;
            let createdPlaylistId = null; // Для хранения ID созданного плейлиста

            for (const fileInfo of state.files) {
                try {
                    fileInfo.status = 'uploading';
                    
                    const fileMetadata = { ...metadata };
                    
                    if (state.uploadMode === 'playlist') {
                        // Если создали новый плейлист при первой загрузке, используем его для остальных
                        if (createdPlaylistId) {
                            fileMetadata.playlist_id = createdPlaylistId;
                            delete fileMetadata.playlist_title;
                            delete fileMetadata.playlist_description;
                        }
                        
                        fileMetadata.episode_number = currentEpisode++;
                        fileMetadata.title = fileInfo.name.replace(/\.[^/.]+$/, '');
                    } else {
                        fileMetadata.title = metadata.title || fileInfo.name.replace(/\.[^/.]+$/, '');
                        fileMetadata.description = metadata.description || '';
                    }

                    const upload = new ChunkedUpload(fileInfo, fileMetadata);
                    state.uploads.set(fileInfo.id, upload);
                    
                    const result = await upload.start();
                    
                    // Сохраняем ID созданного плейлиста для последующих видео
                    if (state.uploadMode === 'playlist' && result.playlist && result.playlist.id && !createdPlaylistId) {
                        createdPlaylistId = result.playlist.id;
                    }
                    
                    results.push({ success: true, file: fileInfo, result });

                } catch (error) {
                    results.push({ success: false, file: fileInfo, error: error.message });
                }
            }

            this.showResults(results);
        },

        getMetadata() {
            const metadata = {};

            if (state.uploadMode === 'single') {
                metadata.title = document.getElementById('single-title').value;
                metadata.description = document.getElementById('single-description').value;
            } else {
                const playlistChoice = document.querySelector('input[name="playlist-choice"]:checked').id;
                
                if (playlistChoice === 'existing-playlist') {
                    metadata.playlist_id = document.getElementById('playlist-select').value;
                } else {
                    metadata.playlist_title = document.getElementById('new-playlist-title').value;
                    metadata.playlist_description = document.getElementById('new-playlist-description').value;
                }
                
                metadata.season_number = document.getElementById('season-number').value;
                metadata.episode_number = parseInt(document.getElementById('start-episode').value);
            }

            return metadata;
        },

        renderProgressSection() {
            const container = document.getElementById('progress-container');
            container.innerHTML = state.files.map(file => `
                <div class="file-card" data-file-id="${file.id}">
                    <div class="file-info">
                        <div class="file-icon">
                            <i class="bi bi-file-earmark-play-fill"></i>
                        </div>
                        <div class="file-details">
                            <div class="file-name" title="${file.name}">${file.name}</div>
                            <div class="file-size">${utils.formatFileSize(file.size)}</div>
                        </div>
                    </div>
                    <!-- Здесь будет прогресс-бар -->
                </div>
            `).join('');
        },

        showResults(results) {
            document.getElementById('upload-progress-section').style.display = 'none';
            document.getElementById('upload-results-section').style.display = 'block';

            const container = document.getElementById('results-container');
            const successCount = results.filter(r => r.success).length;
            const totalCount = results.length;

            container.innerHTML = `
                <div class="alert ${successCount === totalCount ? 'alert-success' : 'alert-warning'} mb-4">
                    <strong>Загружено ${successCount} из ${totalCount} файлов</strong>
                </div>
                ${results.map(r => `
                    <div class="result-item">
                        <div class="result-icon ${r.success ? 'success' : 'error'}">
                            <i class="bi bi-${r.success ? 'check-circle-fill' : 'x-circle-fill'}"></i>
                        </div>
                        <div class="result-details">
                            <div class="result-title">${r.file.name}</div>
                            <div class="result-meta">
                                ${r.success 
                                    ? `Видео "${r.result.title}" успешно загружено` 
                                    : `Ошибка: ${r.error}`
                                }
                            </div>
                        </div>
                    </div>
                `).join('')}
            `;
        }
    };

    // Инициализация UI
    function initUI() {
        // Проверяем сохраненный режим из sessionStorage
        const savedMode = sessionStorage.getItem('uploadMode');
        if (savedMode) {
            state.uploadMode = savedMode;
            const radioId = savedMode === 'single' ? 'single-mode' : 'playlist-mode';
            const radio = document.getElementById(radioId);
            if (radio) {
                radio.checked = true;
            }
            document.getElementById('single-upload-section').style.display = 
                state.uploadMode === 'single' ? 'block' : 'none';
            document.getElementById('playlist-upload-section').style.display = 
                state.uploadMode === 'playlist' ? 'block' : 'none';
            // Очищаем после использования
            sessionStorage.removeItem('uploadMode');
        }

        // Переключение режима загрузки
        document.querySelectorAll('input[name="upload-mode"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                state.uploadMode = e.target.id === 'single-mode' ? 'single' : 'playlist';
                document.getElementById('single-upload-section').style.display = 
                    state.uploadMode === 'single' ? 'block' : 'none';
                document.getElementById('playlist-upload-section').style.display = 
                    state.uploadMode === 'playlist' ? 'block' : 'none';
                fileManager.clearFiles();
            });
        });

        // Переключение выбора плейлиста
        document.querySelectorAll('input[name="playlist-choice"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                document.getElementById('existing-playlist-section').style.display = 
                    e.target.id === 'existing-playlist' ? 'block' : 'none';
                document.getElementById('new-playlist-section').style.display = 
                    e.target.id === 'new-playlist' ? 'block' : 'none';
            });
        });

        // Drag & Drop для одиночного файла
        setupDropZone('single-drop-zone', 'single-file-input', false);
        
        // Drag & Drop для плейлиста
        setupDropZone('playlist-drop-zone', 'playlist-file-input', true);

        // Кнопки выбора файлов
        document.getElementById('single-file-btn').addEventListener('click', () => {
            document.getElementById('single-file-input').click();
        });

        document.getElementById('playlist-file-btn').addEventListener('click', () => {
            document.getElementById('playlist-file-input').click();
        });

        // Изменение файлов
        document.getElementById('single-file-input').addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                fileManager.addFiles(e.target.files);
            }
        });

        document.getElementById('playlist-file-input').addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                fileManager.addFiles(e.target.files);
            }
        });

        // Форма загрузки
        document.getElementById('upload-form').addEventListener('submit', (e) => {
            e.preventDefault();
            
            if (!validateForm()) {
                return;
            }
            
            uploadManager.startUpload();
        });
    }

    function setupDropZone(zoneId, inputId, multiple) {
        const zone = document.getElementById(zoneId);
        const input = document.getElementById(inputId);

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            zone.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            zone.addEventListener(eventName, () => {
                zone.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach(eventName => {
            zone.addEventListener(eventName, () => {
                zone.classList.remove('drag-over');
            });
        });

        zone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                if (!multiple && files.length > 1) {
                    input.files = new DataTransfer().files;
                    const dt = new DataTransfer();
                    dt.items.add(files[0]);
                    input.files = dt.files;
                } else {
                    input.files = files;
                }
                fileManager.addFiles(input.files);
            }
        });

        zone.addEventListener('click', () => {
            input.click();
        });
    }

    function validateForm() {
        if (state.files.length === 0) {
            alert('Пожалуйста, выберите файл(ы) для загрузки');
            return false;
        }

        if (state.uploadMode === 'single') {
            const title = document.getElementById('single-title').value.trim();
            if (!title) {
                alert('Пожалуйста, введите название видео');
                return false;
            }
        } else {
            const playlistChoice = document.querySelector('input[name="playlist-choice"]:checked').id;
            
            if (playlistChoice === 'existing-playlist') {
                const playlistId = document.getElementById('playlist-select').value;
                if (!playlistId) {
                    alert('Пожалуйста, выберите плейлист');
                    return false;
                }
            } else {
                const title = document.getElementById('new-playlist-title').value.trim();
                if (!title) {
                    alert('Пожалуйста, введите название плейлиста');
                    return false;
                }
            }
        }

        return true;
    }

    // Экспорт в глобальную область
    window.fileManager = fileManager;

    // Инициализация при загрузке
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initUI);
    } else {
        initUI();
    }

})();
