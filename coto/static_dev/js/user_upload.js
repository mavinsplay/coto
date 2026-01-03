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
        existingVideos: [],  // Существующие видео в плейлисте
        selectedPlaylistId: null,  // ID выбранного плейлиста
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

        getCookie(name) {
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
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
    // Управление плейлистами
    const playlistManager = {
        async loadPlaylistVideos(playlistId) {
            try {
                const response = await fetch(`/upload/my/playlist/${playlistId}/videos/`, {
                    method: 'GET',
                    headers: {
                        'X-CSRFToken': utils.getCookie('csrftoken'),
                    },
                });

                if (!response.ok) {
                    throw new Error('Ошибка загрузки видео из плейлиста');
                }

                const data = await response.json();
                
                if (data.success) {
                    state.existingVideos = data.videos;
                    fileManager.render();
                    
                    // Обновляем поля сезон/серия на основе последнего видео
                    if (data.videos.length > 0) {
                        const lastVideo = data.videos[data.videos.length - 1];
                        const seasonInput = document.getElementById('season-number');
                        const episodeInput = document.getElementById('start-episode');
                        
                        if (seasonInput) {
                            seasonInput.value = lastVideo.season_number;
                        }
                        if (episodeInput) {
                            episodeInput.value = lastVideo.episode_number + 1;
                        }
                    }
                } else {
                    console.error('Ошибка:', data.error);
                    alert('Ошибка при загрузке видео: ' + data.error);
                }
            } catch (error) {
                console.error('Ошибка при загрузке видео из плейлиста:', error);
                alert('Не удалось загрузить видео из плейлиста');
            }
        },

        async updateOrder(playlistId, items) {
            try {
                const response = await fetch('/upload/my/playlist/update-order/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': utils.getCookie('csrftoken'),
                    },
                    body: JSON.stringify({
                        playlist_id: playlistId,
                        items: items,
                    }),
                });

                if (!response.ok) {
                    throw new Error('Ошибка обновления порядка');
                }

                const data = await response.json();
                
                if (!data.success) {
                    throw new Error(data.error || 'Неизвестная ошибка');
                }
                
                return true;
            } catch (error) {
                console.error('Ошибка при обновлении порядка:', error);
                alert('Не удалось обновить порядок видео: ' + error.message);
                return false;
            }
        },
    };

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
                    // Метаданные для плейлиста
                    seasonNumber: null,
                    episodeNumber: null,
                    order: null,
                    // Метаданные для видео
                    title: file.name.replace(/\.[^/.]+$/, ''), // Название без расширения
                    description: '',
                    thumbnail: null, // Файл превью
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

        toggleMetadataEdit(fileId) {
            const metadataDiv = document.getElementById(`metadata-${fileId}`);
            if (metadataDiv) {
                const isVisible = metadataDiv.style.display !== 'none';
                metadataDiv.style.display = isVisible ? 'none' : 'block';
            }
        },

        toggleExistingMetadata(videoId) {
            const metadataDiv = document.getElementById(`metadata-existing-${videoId}`);
            if (metadataDiv) {
                const isVisible = metadataDiv.style.display !== 'none';
                metadataDiv.style.display = isVisible ? 'none' : 'block';
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

            // Показываем секцию если есть файлы или существующие видео
            const hasContent = state.files.length > 0 || state.existingVideos.length > 0;
            
            if (!hasContent) {
                listSection.style.display = 'none';
                uploadBtn.disabled = true;
                return;
            }

            listSection.style.display = 'block';
            uploadBtn.disabled = state.files.length === 0;

            // Автоматически присваиваем порядок и номера серий если в режиме плейлиста
            if (state.uploadMode === 'playlist') {
                const seasonInput = document.getElementById('season-number');
                const episodeInput = document.getElementById('start-episode');
                const seasonNumber = seasonInput ? (parseInt(seasonInput.value) || 1) : 1;
                const startEpisode = episodeInput ? (parseInt(episodeInput.value) || 1) : 1;
                
                state.files.forEach((file, index) => {
                    if (file.seasonNumber === null) file.seasonNumber = seasonNumber;
                    if (file.episodeNumber === null) file.episodeNumber = startEpisode + index;
                    if (file.order === null) file.order = (state.existingVideos.length + index + 1);
                });
            }

            // Создаем HTML для существующих видео
            const existingVideosHtml = state.existingVideos.map((video) => `
                <div class="file-card existing-video" data-video-id="${video.id}" data-existing="true" draggable="true">
                    <div class="file-info">
                        ${state.uploadMode === 'playlist' ? `
                            <div class="drag-handle">
                                <i class="bi bi-grip-vertical"></i>
                            </div>
                        ` : ''}
                        <div class="file-icon">
                            <i class="bi bi-camera-video-fill text-success"></i>
                        </div>
                        <div class="file-details">
                            <div class="file-name" title="${video.title}">${video.title}</div>
                            <div class="file-size">
                                <span class="badge bg-success">Загружено</span>
                                ${video.file_size ? utils.formatFileSize(video.file_size) : ''}
                            </div>
                        </div>
                        <div class="file-actions">
                            <button type="button" class="btn btn-sm btn-outline-primary me-2" 
                                    onclick="fileManager.toggleExistingMetadata(${video.id})"
                                    title="Редактировать метаданные">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <span class="text-muted small">ID: ${video.video_id}</span>
                        </div>
                    </div>
                    
                    <!-- Метаданные существующего видео -->
                    <div class="video-metadata" id="metadata-existing-${video.id}" style="display: none;">
                        <div class="metadata-fields">
                            <div class="metadata-field">
                                <label for="title-existing-${video.id}">Название видео</label>
                                <input type="text" 
                                       id="title-existing-${video.id}" 
                                       class="form-control form-control-sm video-title-existing" 
                                       value="${video.title || ''}" 
                                       data-video-id="${video.id}"
                                       placeholder="Название видео">
                            </div>
                            <div class="metadata-field">
                                <label for="description-existing-${video.id}">Описание</label>
                                <textarea id="description-existing-${video.id}" 
                                          class="form-control form-control-sm video-description-existing" 
                                          rows="2"
                                          data-video-id="${video.id}"
                                          placeholder="Описание видео">${video.description || ''}</textarea>
                            </div>
                            <div class="metadata-field">
                                <label for="thumbnail-existing-${video.id}">Превью (изображение)</label>
                                <input type="file" 
                                       id="thumbnail-existing-${video.id}" 
                                       class="form-control form-control-sm video-thumbnail-existing" 
                                       accept="image/*"
                                       data-video-id="${video.id}">
                                <small class="text-muted">Загрузите новое превью</small>
                            </div>
                        </div>
                    </div>
                    
                    ${state.uploadMode === 'playlist' ? `
                        <div class="episode-fields">
                            <div class="episode-field">
                                <label for="season-existing-${video.id}">Сезон</label>
                                <input type="number" 
                                       id="season-existing-${video.id}" 
                                       class="episode-season-existing" 
                                       value="${video.season_number}" 
                                       min="1"
                                       data-video-id="${video.id}">
                            </div>
                            <div class="episode-field">
                                <label for="episode-existing-${video.id}">Серия</label>
                                <input type="number" 
                                       id="episode-existing-${video.id}" 
                                       class="episode-number-existing" 
                                       value="${video.episode_number}" 
                                       min="1"
                                       data-video-id="${video.id}">
                            </div>
                            <div class="episode-field">
                                <label for="order-existing-${video.id}">Порядок</label>
                                <input type="number" 
                                       id="order-existing-${video.id}" 
                                       class="episode-order-existing" 
                                       value="${video.order}" 
                                       min="1"
                                       data-video-id="${video.id}">
                            </div>
                        </div>
                    ` : ''}
                </div>
            `).join('');

            // Создаем HTML для новых файлов
            const newFilesHtml = state.files.map((file, index) => `
                <div class="file-card" data-file-id="${file.id}" draggable="${file.status === 'pending'}">
                    <div class="file-info">
                        ${file.status === 'pending' && state.uploadMode === 'playlist' ? `
                            <div class="drag-handle">
                                <i class="bi bi-grip-vertical"></i>
                            </div>
                        ` : ''}
                        <div class="file-icon">
                            <i class="bi bi-file-earmark-play-fill"></i>
                        </div>
                        <div class="file-details">
                            <div class="file-name" title="${file.name}">${file.name}</div>
                            <div class="file-size">${utils.formatFileSize(file.size)}</div>
                        </div>
                        <div class="file-actions">
                            ${file.status === 'pending' ? `
                                <button type="button" class="btn btn-sm btn-outline-primary me-2" 
                                        onclick="fileManager.toggleMetadataEdit('${file.id}')"
                                        title="Редактировать метаданные">
                                    <i class="bi bi-pencil"></i>
                                </button>
                                <button type="button" class="btn btn-sm btn-outline-danger" onclick="fileManager.removeFile('${file.id}')">
                                    <i class="bi bi-trash"></i>
                                </button>
                            ` : ''}
                        </div>
                    </div>
                    
                    <!-- Метаданные видео -->
                    <div class="video-metadata" id="metadata-${file.id}" style="display: none;">
                        <div class="metadata-fields">
                            <div class="metadata-field">
                                <label for="title-${file.id}">Название видео</label>
                                <input type="text" 
                                       id="title-${file.id}" 
                                       class="form-control form-control-sm video-title" 
                                       value="${file.title || ''}" 
                                       data-file-id="${file.id}"
                                       placeholder="Название видео">
                            </div>
                            <div class="metadata-field">
                                <label for="description-${file.id}">Описание</label>
                                <textarea id="description-${file.id}" 
                                          class="form-control form-control-sm video-description" 
                                          rows="2"
                                          data-file-id="${file.id}"
                                          placeholder="Описание видео">${file.description || ''}</textarea>
                            </div>
                            <div class="metadata-field">
                                <label for="thumbnail-${file.id}">Превью</label>
                                <input type="file" 
                                       id="thumbnail-${file.id}" 
                                       class="form-control form-control-sm video-thumbnail" 
                                       accept="image/*"
                                       data-file-id="${file.id}">
                                ${file.thumbnail ? `<small class="text-success">✓ Превью выбрано</small>` : ''}
                            </div>
                        </div>
                    </div>
                    
                    ${state.uploadMode === 'playlist' && file.status === 'pending' ? `
                        <div class="episode-fields">
                            <div class="episode-field">
                                <label for="season-${file.id}">Сезон</label>
                                <input type="number" 
                                       id="season-${file.id}" 
                                       class="episode-season" 
                                       value="${file.seasonNumber || 1}" 
                                       min="1"
                                       data-file-id="${file.id}">
                            </div>
                            <div class="episode-field">
                                <label for="episode-${file.id}">Серия</label>
                                <input type="number" 
                                       id="episode-${file.id}" 
                                       class="episode-number" 
                                       value="${file.episodeNumber || 1}" 
                                       min="1"
                                       data-file-id="${file.id}">
                            </div>
                            <div class="episode-field">
                                <label for="order-${file.id}">Порядок</label>
                                <input type="number" 
                                       id="order-${file.id}" 
                                       class="episode-order" 
                                       value="${file.order || (index + 1)}" 
                                       min="1"
                                       data-file-id="${file.id}">
                            </div>
                        </div>
                    ` : ''}
                </div>
            `).join('');
            
            // Объединяем существующие видео и новые файлы
            container.innerHTML = existingVideosHtml + newFilesHtml;
            
            // Добавляем обработчики для изменения полей
            this.attachFieldHandlers();
            
            // Добавляем обработчики drag-and-drop
            if (state.uploadMode === 'playlist') {
                this.attachDragHandlers();
            }
        },

        attachFieldHandlers() {
            // Обработчики для метаданных видео (название, описание, превью)
            document.querySelectorAll('.video-title, .video-description').forEach(input => {
                input.addEventListener('change', (e) => {
                    const fileId = e.target.dataset.fileId;
                    const file = state.files.find(f => f.id === fileId);
                    if (file) {
                        if (e.target.classList.contains('video-title')) {
                            file.title = e.target.value;
                        } else if (e.target.classList.contains('video-description')) {
                            file.description = e.target.value;
                        }
                    }
                });
            });

            // Обработчики для превью
            document.querySelectorAll('.video-thumbnail').forEach(input => {
                input.addEventListener('change', (e) => {
                    const fileId = e.target.dataset.fileId;
                    const file = state.files.find(f => f.id === fileId);
                    if (file && e.target.files.length > 0) {
                        file.thumbnail = e.target.files[0];
                        this.render();
                    }
                });
            });

            // Обработчики для полей сезон/серия/порядок новых файлов
            document.querySelectorAll('.episode-season, .episode-number, .episode-order').forEach(input => {
                input.addEventListener('change', (e) => {
                    const fileId = e.target.dataset.fileId;
                    const file = state.files.find(f => f.id === fileId);
                    if (file) {
                        if (e.target.classList.contains('episode-season')) {
                            file.seasonNumber = parseInt(e.target.value) || 1;
                        } else if (e.target.classList.contains('episode-number')) {
                            file.episodeNumber = parseInt(e.target.value) || 1;
                        } else if (e.target.classList.contains('episode-order')) {
                            file.order = parseInt(e.target.value) || 1;
                        }
                        
                        // Проверяем на дубликаты сезон/серия
                        this.checkForDuplicates();
                    }
                });
            });
            
            // Обработчики для полей существующих видео (плейлист)
            document.querySelectorAll('.episode-season-existing, .episode-number-existing, .episode-order-existing').forEach(input => {
                input.addEventListener('change', (e) => {
                    const videoId = e.target.dataset.videoId;
                    const video = state.existingVideos.find(v => v.id === parseInt(videoId));
                    if (video) {
                        if (e.target.classList.contains('episode-season-existing')) {
                            video.season_number = parseInt(e.target.value) || 1;
                        } else if (e.target.classList.contains('episode-number-existing')) {
                            video.episode_number = parseInt(e.target.value) || 1;
                        } else if (e.target.classList.contains('episode-order-existing')) {
                            video.order = parseInt(e.target.value) || 1;
                        }
                        
                        // Автоматически сохраняем изменения
                        this.saveExistingVideoChanges();
                    }
                });
            });

            // Обработчики для метаданных существующих видео (название, описание)
            document.querySelectorAll('.video-title-existing, .video-description-existing').forEach(input => {
                input.addEventListener('change', async (e) => {
                    const videoId = e.target.dataset.videoId;
                    const video = state.existingVideos.find(v => v.id === parseInt(videoId));
                    if (video) {
                        const updates = {};
                        if (e.target.classList.contains('video-title-existing')) {
                            updates.title = e.target.value;
                            video.title = e.target.value;
                        } else if (e.target.classList.contains('video-description-existing')) {
                            updates.description = e.target.value;
                            video.description = e.target.value;
                        }
                        
                        // Сохраняем изменения на сервере
                        await this.updateVideoMetadata(video.video_id, updates);
                    }
                });
            });

            // Обработчики для превью существующих видео
            document.querySelectorAll('.video-thumbnail-existing').forEach(input => {
                input.addEventListener('change', async (e) => {
                    const videoId = e.target.dataset.videoId;
                    const video = state.existingVideos.find(v => v.id === parseInt(videoId));
                    if (video && e.target.files.length > 0) {
                        await this.updateVideoThumbnail(video.video_id, e.target.files[0]);
                    }
                });
            });
        },

        async updateVideoMetadata(videoId, updates) {
            try {
                const response = await fetch(`/upload/my/video/${videoId}/update/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': utils.getCookie('csrftoken'),
                    },
                    body: JSON.stringify(updates),
                });

                if (!response.ok) {
                    throw new Error('Ошибка обновления метаданных');
                }

                const data = await response.json();
                
                if (data.success) {
                    // Показываем уведомление об успехе
                    this.showNotification('Метаданные обновлены', 'success');
                } else {
                    throw new Error(data.error || 'Неизвестная ошибка');
                }
            } catch (error) {
                console.error('Ошибка при обновлении метаданных:', error);
                this.showNotification('Не удалось обновить метаданные: ' + error.message, 'error');
            }
        },

        async updateVideoThumbnail(videoId, thumbnailFile) {
            try {
                const formData = new FormData();
                formData.append('thumbnail', thumbnailFile);

                const response = await fetch(`/upload/my/video/${videoId}/update/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': utils.getCookie('csrftoken'),
                    },
                    body: formData,
                });

                if (!response.ok) {
                    throw new Error('Ошибка загрузки превью');
                }

                const data = await response.json();
                
                if (data.success) {
                    this.showNotification('Превью обновлено', 'success');
                } else {
                    throw new Error(data.error || 'Неизвестная ошибка');
                }
            } catch (error) {
                console.error('Ошибка при загрузке превью:', error);
                this.showNotification('Не удалось загрузить превью: ' + error.message, 'error');
            }
        },

        showNotification(message, type = 'info') {
            // Простое уведомление через alert (можно улучшить позже)
            if (type === 'success') {
                console.log('✓', message);
            } else if (type === 'error') {
                console.error('✗', message);
                alert(message);
            }
        },

        async saveExistingVideoChanges() {
            if (!state.selectedPlaylistId) return;
            
            // Собираем данные для обновления
            const items = state.existingVideos.map(video => ({
                id: video.id,
                order: video.order,
                season_number: video.season_number,
                episode_number: video.episode_number,
            }));
            
            // Отправляем на сервер
            await playlistManager.updateOrder(state.selectedPlaylistId, items);
        },

        checkForDuplicates() {
            // Проверка на дубликаты сезон/серия
            const seasonEpisodePairs = new Map();
            const duplicates = [];
            
            state.files.forEach(file => {
                const key = `${file.seasonNumber}-${file.episodeNumber}`;
                if (seasonEpisodePairs.has(key)) {
                    duplicates.push({ season: file.seasonNumber, episode: file.episodeNumber });
                }
                seasonEpisodePairs.set(key, file.id);
            });
            
            // Удаляем старые предупреждения
            document.querySelectorAll('.duplicate-warning').forEach(el => el.remove());
            
            if (duplicates.length > 0) {
                // Показываем предупреждение
                const uniqueDuplicates = [...new Set(duplicates.map(d => `Сезон ${d.season}, Серия ${d.episode}`))];
                const warning = document.createElement('div');
                warning.className = 'alert alert-warning duplicate-warning mt-3';
                warning.innerHTML = `
                    <strong><i class="bi bi-exclamation-triangle"></i> Внимание!</strong>
                    Найдены дубликаты сезон/серия: ${uniqueDuplicates.join('; ')}
                    <br><small>Это может привести к ошибке при загрузке. Пожалуйста, исправьте номера серий.</small>
                `;
                document.getElementById('files-list').insertBefore(warning, document.getElementById('files-container'));
            }
        },

        attachDragHandlers() {
            const cards = document.querySelectorAll('.file-card[draggable="true"]');
            
            cards.forEach(card => {
                card.addEventListener('dragstart', (e) => {
                    card.classList.add('dragging');
                    e.dataTransfer.effectAllowed = 'move';
                    e.dataTransfer.setData('text/html', card.innerHTML);
                });

                card.addEventListener('dragend', (e) => {
                    card.classList.remove('dragging');
                });

                card.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    const draggingCard = document.querySelector('.dragging');
                    if (draggingCard && draggingCard !== card) {
                        card.classList.add('drag-over-file');
                    }
                });

                card.addEventListener('dragleave', (e) => {
                    card.classList.remove('drag-over-file');
                });

                card.addEventListener('drop', (e) => {
                    e.preventDefault();
                    card.classList.remove('drag-over-file');
                    
                    const draggingCard = document.querySelector('.dragging');
                    if (draggingCard && draggingCard !== card) {
                        // Определяем типы карточек (существующие или новые)
                        const fromIsExisting = draggingCard.dataset.existing === 'true';
                        const toIsExisting = card.dataset.existing === 'true';
                        
                        if (fromIsExisting && toIsExisting) {
                            // Перемещаем существующие видео
                            const fromId = parseInt(draggingCard.dataset.videoId);
                            const toId = parseInt(card.dataset.videoId);
                            this.reorderExistingVideos(fromId, toId);
                        } else if (!fromIsExisting && !toIsExisting) {
                            // Перемещаем новые файлы
                            const fromId = draggingCard.dataset.fileId;
                            const toId = card.dataset.fileId;
                            this.reorderFiles(fromId, toId);
                        }
                        // Смешанное перемещение не поддерживается
                    }
                });
            });
        },

        reorderFiles(fromId, toId) {
            const fromIndex = state.files.findIndex(f => f.id === fromId);
            const toIndex = state.files.findIndex(f => f.id === toId);
            
            if (fromIndex !== -1 && toIndex !== -1) {
                // Перемещаем элемент
                const [movedFile] = state.files.splice(fromIndex, 1);
                state.files.splice(toIndex, 0, movedFile);
                
                // Обновляем порядок с учетом существующих видео
                state.files.forEach((file, index) => {
                    file.order = state.existingVideos.length + index + 1;
                });
                
                this.render();
            }
        },

        async reorderExistingVideos(fromId, toId) {
            const fromIndex = state.existingVideos.findIndex(v => v.id === fromId);
            const toIndex = state.existingVideos.findIndex(v => v.id === toId);
            
            if (fromIndex !== -1 && toIndex !== -1) {
                // Перемещаем элемент
                const [movedVideo] = state.existingVideos.splice(fromIndex, 1);
                state.existingVideos.splice(toIndex, 0, movedVideo);
                
                // Обновляем порядок
                state.existingVideos.forEach((video, index) => {
                    video.order = index + 1;
                });
                
                // Также обновляем порядок новых файлов
                state.files.forEach((file, index) => {
                    file.order = state.existingVideos.length + index + 1;
                });
                
                this.render();
                
                // Сохраняем изменения на сервере
                await this.saveExistingVideoChanges();
            }
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
                    // Если это File (превью), добавляем как файл
                    if (value instanceof File) {
                        formData.append(key, value);
                    } else {
                        formData.append(key, value);
                    }
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
                        
                        // Используем индивидуальные значения из полей редактирования
                        fileMetadata.season_number = fileInfo.seasonNumber || 1;
                        fileMetadata.episode_number = fileInfo.episodeNumber || 1;
                        fileMetadata.order = fileInfo.order || 1;
                        fileMetadata.title = fileInfo.title || fileInfo.name.replace(/\.[^/.]+$/, '');
                        fileMetadata.description = fileInfo.description || '';
                    } else {
                        fileMetadata.title = fileInfo.title || metadata.title || fileInfo.name.replace(/\.[^/.]+$/, '');
                        fileMetadata.description = fileInfo.description || metadata.description || '';
                    }
                    
                    // Добавляем превью если есть
                    if (fileInfo.thumbnail) {
                        fileMetadata.thumbnail = fileInfo.thumbnail;
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
                
                const seasonInput = document.getElementById('season-number');
                const episodeInput = document.getElementById('start-episode');
                metadata.season_number = seasonInput ? seasonInput.value : '1';
                metadata.episode_number = episodeInput ? parseInt(episodeInput.value) : 1;
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
                
                // Очищаем существующие видео при переключении на новый плейлист
                if (e.target.id === 'new-playlist') {
                    state.existingVideos = [];
                    state.selectedPlaylistId = null;
                    fileManager.render();
                }
            });
        });

        // Обработчик выбора существующего плейлиста
        const playlistSelect = document.getElementById('playlist-select');
        if (playlistSelect) {
            playlistSelect.addEventListener('change', async (e) => {
                const playlistId = e.target.value;
                if (playlistId) {
                    state.selectedPlaylistId = playlistId;
                    await playlistManager.loadPlaylistVideos(playlistId);
                } else {
                    state.existingVideos = [];
                    state.selectedPlaylistId = null;
                    fileManager.render();
                }
            });
        }

        // Автоматическое обновление полей при изменении глобального сезона/серии
        const seasonNumberInput = document.getElementById('season-number');
        const startEpisodeInput = document.getElementById('start-episode');
        
        if (seasonNumberInput) {
            seasonNumberInput.addEventListener('change', (e) => {
                if (state.uploadMode === 'playlist' && state.files.length > 0) {
                    const newSeason = parseInt(e.target.value) || 1;
                    state.files.forEach(file => {
                        file.seasonNumber = newSeason;
                    });
                    fileManager.render();
                }
            });
        }

        if (startEpisodeInput) {
            startEpisodeInput.addEventListener('change', (e) => {
                if (state.uploadMode === 'playlist' && state.files.length > 0) {
                    const startEpisode = parseInt(e.target.value) || 1;
                    state.files.forEach((file, index) => {
                        file.episodeNumber = startEpisode + index;
                    });
                    fileManager.render();
                }
            });
        }

        // Drag & Drop для одиночного файла
        setupDropZone('single-drop-zone', 'single-file-input', false);
        
        // Drag & Drop для плейлиста
        setupDropZone('playlist-drop-zone', 'playlist-file-input', true);

        // Кнопки выбора файлов
        document.getElementById('single-file-btn').addEventListener('click', (e) => {
            e.stopPropagation(); // Предотвращаем всплытие к drop-zone
            document.getElementById('single-file-input').click();
        });

        document.getElementById('playlist-file-btn').addEventListener('click', (e) => {
            e.stopPropagation(); // Предотвращаем всплытие к drop-zone
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

        zone.addEventListener('click', (e) => {
            // Не открываем диалог, если кликнули на кнопку или input
            if (e.target.tagName === 'BUTTON' || e.target.tagName === 'INPUT' || e.target.closest('button')) {
                return;
            }
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
            
            // Проверка на дубликаты сезон/серия
            const seasonEpisodePairs = new Map();
            for (const file of state.files) {
                const key = `${file.seasonNumber}-${file.episodeNumber}`;
                if (seasonEpisodePairs.has(key)) {
                    alert(`Обнаружены дубликаты: Сезон ${file.seasonNumber}, Серия ${file.episodeNumber}\n\nПожалуйста, исправьте номера серий перед загрузкой.`);
                    return false;
                }
                seasonEpisodePairs.set(key, file.id);
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
