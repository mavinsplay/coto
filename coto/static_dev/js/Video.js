// Video.js — Plyr event listeners + кастомный лоадер с видео

/**
 * Инициализирует видео-лоадер поверх плеера.
 * Показывает reload.MP4 вместо стандартного спиннера при буферизации.
 */
function initPlyrLoader(videoEl) {
  // Ищем ближайший контейнер плеера
  const wrapper = videoEl.closest('.plyr__video-wrapper') ||
    videoEl.closest('.video-wrapper') ||
    videoEl.closest('.video-player-wrapper') ||
    videoEl.parentElement;

  if (!wrapper) return;

  // Создаём оверлей
  const loaderEl = document.createElement('div');
  loaderEl.className = 'plyr-video-loader';
  loaderEl.innerHTML = `
    <video autoplay loop muted playsinline>
      <source src="/static/video/reload.webm" type="video/webm">
    </video>
  `;
  wrapper.appendChild(loaderEl);

  function showLoader() { loaderEl.classList.add('active'); }
  function hideLoader() { loaderEl.classList.remove('active'); }

  // Показываем лоадер при bufering / ожидании данных
  videoEl.addEventListener('waiting', showLoader);
  videoEl.addEventListener('loadstart', showLoader);

  // Скрываем, когда видео готово к воспроизведению
  videoEl.addEventListener('canplay', hideLoader);
  videoEl.addEventListener('canplaythrough', hideLoader);
  videoEl.addEventListener('playing', hideLoader);
  videoEl.addEventListener('error', hideLoader);

  return loaderEl;
}

document.addEventListener('DOMContentLoaded', function () {
  // Небольшая задержка, чтобы Plyr/HLS успели инициализироваться
  setTimeout(() => {
    const player = window.player || window.videoPlayer;
    if (!player) return;

    // Получаем нативный <video> элемент из объекта Plyr
    const videoEl = player.media || document.getElementById('hls-player') || document.getElementById('video-player');
    if (videoEl) {
      initPlyrLoader(videoEl);
    }

    console.log('Plyr плеер готов к работе');

    player.on('play', () => console.log('Воспроизведение начато'));
    player.on('pause', () => console.log('Воспроизведение приостановлено'));
    player.on('ended', () => console.log('Воспроизведение завершено'));
    player.on('error', (e) => console.error('Ошибка плеера:', e));

  }, 500);
});