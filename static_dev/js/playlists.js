document.addEventListener('DOMContentLoaded', () => {
    const playlistItems = document.querySelectorAll('.playlist-item');
    const currentEpisodeLabel = document.getElementById('current-episode');
  
    if (playlistItems.length === 0) return;
  
    // Инициализируем Video.js плеер
    const player = videojs('hls-player');
  
    // Функция переключения видео
    function playVideo(item) {
      // Снимаем выделение у всех
      playlistItems.forEach(i => i.classList.remove('active'));
  
      // Выделяем текущий
      item.classList.add('active');
  
      // Получаем URL m3u8
      const hlsUrl = item.getAttribute('data-hls-url');
      const season = item.getAttribute('data-season');
      const episode = item.getAttribute('data-episode');
      const title = item.getAttribute('data-title');
  
      // Меняем источник у плеера
      player.src({
        src: hlsUrl,
        type: 'application/x-mpegURL',
      });
  
      // Автозапуск
      player.play();
  
      // Обновляем текущую серию
      currentEpisodeLabel.textContent = `Сезон ${season}, Серия ${episode} — ${title}`;
    }
  
    // Навешиваем обработчик клика
    playlistItems.forEach(item => {
      item.addEventListener('click', () => playVideo(item));
    });
  
    // Автозапуск первой серии
    playVideo(playlistItems[0]);
  });
  