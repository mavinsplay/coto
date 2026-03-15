document.addEventListener('DOMContentLoaded', () => {
  const playlistItems = document.querySelectorAll('.playlist-item');
  const currentEpisodeLabel = document.getElementById('current-episode');

  if (playlistItems.length === 0) return;

  // Ожидаем, что window.player и window.hls (если Hls.js поддерживается)
  // уже инициализированы (например, в sync_player.js или на странице).
  function playVideo(item) {
    // Снимаем выделение у всех
    playlistItems.forEach(i => i.classList.remove('active'));

    // Выделяем текущий
    item.classList.add('active');

    // Получаем URL и метаданные
    const hlsUrl = item.getAttribute('data-hls-url');
    const season = item.getAttribute('data-season');
    const episode = item.getAttribute('data-episode');
    const title = item.getAttribute('data-title');

    // Если Hls.js инициализирован
    if (window.hls && typeof Hls !== 'undefined' && Hls.isSupported()) {
      window.hls.loadSource(hlsUrl);
    } else {
      // Иначе используем нативную поддержку браузером
      const videoEl = document.getElementById("hls-player") || document.getElementById("video-player");
      if (videoEl) {
        videoEl.src = hlsUrl;
      }
    }

    // Запускаем воспроизведение
    if (window.player) {
      window.player.play().catch(e => console.warn('Autoplay blocked:', e));
    }

    // Обновляем метку
    if (currentEpisodeLabel) {
      currentEpisodeLabel.textContent = `Сезон ${season}, Серия ${episode} — ${title}`;
    }
  }

  // Навешиваем обработчик клика
  playlistItems.forEach(item => {
    item.addEventListener('click', () => playVideo(item));
  });

  // Автозапуск первой серии обрабатывается на стороне sync_player,
  // поэтому здесь больше ничего не делаем.
});
  