document.addEventListener('DOMContentLoaded', function() { 
    // Инициализация Video.js плеера
    var player = videojs('hls-player', {
      // Основные настройки
      fluid: true,
      responsive: true,
      aspectRatio: '16:9',
      
      // Настройки воспроизведения
      preload: 'auto',
      autoplay: false,
      muted: false,
      
      // Скорости воспроизведения
      playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 2],
      
      // HLS настройки
      html5: {
        hls: {
          enableLowInitialPlaylist: true,
          smoothQualityChange: true,
          overrideNative: true
        }
      },
      
      // Настройки интерфейса
      controls: true,
      bigPlayButton: true,
      
      // Языковые настройки
      language: 'ru',
      
      // Плагины
      plugins: {
        qualityLevels: {},
        hlsQualitySelector: {
          displayCurrentQuality: true
        }
      }
    });
    
    // Событие готовности плеера
    player.ready(function() {
      console.log('Video.js плеер готов к работе');
      
      // Добавляем кастомную тему
      player.addClass('vjs-theme-dark');
      
      // Настройки качества видео
      var qualityLevels = player.qualityLevels();
      
      qualityLevels.on('addqualitylevel', function(event) {
        var qualityLevel = event.qualityLevel;
        console.log('Добавлен уровень качества:', qualityLevel.height + 'p');
      });
      
      // Автоматическое управление качеством
      qualityLevels.on('change', function() {
        console.log('Уровень качества изменен на:', qualityLevels[qualityLevels.selectedIndex].height + 'p');
      });
    });
    
    // Обработка ошибок
    player.on('error', function() {
      var error = player.error();
      console.error('Ошибка плеера:', error);
      
      // Показать пользователю понятное сообщение об ошибке
      var errorMessages = {
        1: 'Загрузка видео была прервана',
        2: 'Произошла сетевая ошибка при загрузке видео',
        3: 'Ошибка декодирования видео',
        4: 'Видео недоступно для воспроизведения'
      };
      
      var message = errorMessages[error.code] || 'Произошла неизвестная ошибка';
      player.error({
        code: error.code,
        message: message
      });
    });
    
    // Обработка событий воспроизведения
    player.on('play', function() {
      console.log('Воспроизведение начато');
    });
    
    player.on('pause', function() {
      console.log('Воспроизведение приостановлено');
    });
    
    player.on('ended', function() {
      console.log('Воспроизведение завершено');
    });
    
    player.on('loadstart', function() {
      console.log('Начата загрузка видео');
    });
    
    player.on('canplay', function() {
      console.log('Видео готово к воспроизведению');
    });
    
    // Управление с клавиатуры
    player.on('keydown', function(event) {
      switch(event.which) {
        case 32: // Пробел - пауза/воспроизведение
          event.preventDefault();
          if (player.paused()) {
            player.play();
          } else {
            player.pause();
          }
          break;
        case 37: // Стрелка влево - перемотка назад на 5 сек
          event.preventDefault();
          player.currentTime(player.currentTime() - 5);
          break;
        case 39: // Стрелка вправо - перемотка вперед на 5 сек
          event.preventDefault();
          player.currentTime(player.currentTime() + 5);
          break;
        case 38: // Стрелка вверх - увеличить громкость
          event.preventDefault();
          player.volume(Math.min(1, player.volume() + 0.1));
          break;
        case 40: // Стрелка вниз - уменьшить громкость
          event.preventDefault();
          player.volume(Math.max(0, player.volume() - 0.1));
          break;
        case 70: // F - полноэкранный режим
          event.preventDefault();
          if (player.isFullscreen()) {
            player.exitFullscreen();
          } else {
            player.requestFullscreen();
          }
          break;
        case 77: // M - выключить/включить звук
          event.preventDefault();
          player.muted(!player.muted());
          break;
      }
    });
    
    // Очистка при уходе со страницы
    window.addEventListener('beforeunload', function() {
      if (player) {
        player.dispose();
      }
    });
    
    // Глобальная переменная для доступа к плееру из консоли разработчика
    window.videoPlayer = player;
  }); 