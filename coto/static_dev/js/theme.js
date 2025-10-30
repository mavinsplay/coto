/**
 * Theme Management System
 * Handles light/dark theme switching with local storage persistence
 */

(function() {
    'use strict';
  
    const THEME_KEY = 'coto-theme';
    const THEME_LIGHT = 'light';
    const THEME_DARK = 'dark';
  
    // Apply theme IMMEDIATELY before anything else
    (function applyThemeBeforeLoad() {
      const savedTheme = (() => {
        try {
          return localStorage.getItem(THEME_KEY);
        } catch (e) {
          return null;
        }
      })();
      
      const systemTheme = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? THEME_DARK : THEME_LIGHT;
      const initialTheme = savedTheme || systemTheme;
      
      // Apply immediately to html element
      document.documentElement.setAttribute('data-bs-theme', initialTheme);
      
      // Add styles to prevent any transitions during load
      const style = document.createElement('style');
      style.id = 'theme-loading-style';
      style.textContent = `
        * {
          transition: none !important;
          animation-duration: 0s !important;
        }
      `;
      document.head.appendChild(style);
    })();
  
    class ThemeManager {
      constructor() {
        this.currentTheme = this.getSavedTheme() || this.getSystemTheme();
        this.init();
      }
  
      /**
       * Initialize theme manager
       */
      init() {
        // Remove loading styles after a short delay
        setTimeout(() => {
          const loadingStyle = document.getElementById('theme-loading-style');
          if (loadingStyle) {
            loadingStyle.remove();
          }
        }, 150);
        
        this.setupToggleButton();
        this.watchSystemTheme();
      }
  
      /**
       * Get saved theme from localStorage
       */
      getSavedTheme() {
        try {
          return localStorage.getItem(THEME_KEY);
        } catch (e) {
          console.warn('localStorage not available:', e);
          return null;
        }
      }
  
      /**
       * Save theme to localStorage
       */
      saveTheme(theme) {
        try {
          localStorage.setItem(THEME_KEY, theme);
        } catch (e) {
          console.warn('Failed to save theme:', e);
        }
      }
  
      /**
       * Get system preferred theme
       */
      getSystemTheme() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
          return THEME_DARK;
        }
        return THEME_LIGHT;
      }
  
      /**
       * Apply theme to document with animation
       */
      applyTheme(theme) {
        const html = document.documentElement;
        
        if (theme === THEME_DARK) {
          html.setAttribute('data-bs-theme', 'dark');
        } else {
          html.setAttribute('data-bs-theme', 'light');
        }
  
        this.currentTheme = theme;
        this.updateToggleButton();
      }
  
      /**
       * Toggle between light and dark theme
       */
      toggleTheme() {
        const newTheme = this.currentTheme === THEME_LIGHT ? THEME_DARK : THEME_LIGHT;
        this.applyTheme(newTheme);
        this.saveTheme(newTheme);
        
        // Dispatch custom event for other scripts
        window.dispatchEvent(new CustomEvent('themeChanged', { 
          detail: { theme: newTheme } 
        }));
      }
  
      /**
       * Setup toggle button in navbar
       */
      setupToggleButton() {
        const toggleBtn = document.getElementById('theme-toggle');
        if (!toggleBtn) {
          console.warn('Theme toggle button not found');
          return;
        }
  
        toggleBtn.addEventListener('click', (e) => {
          e.preventDefault();
          this.toggleTheme();
          
          // Add animation effect
          toggleBtn.style.transform = 'rotate(180deg)';
          setTimeout(() => {
            toggleBtn.style.transform = '';
          }, 300);
        });
  
        this.updateToggleButton();
      }
  
      /**
       * Update toggle button icon
       */
      updateToggleButton() {
        const toggleBtn = document.getElementById('theme-toggle');
        if (!toggleBtn) return;
  
        const icon = toggleBtn.querySelector('i');
        if (!icon) return;
  
        if (this.currentTheme === THEME_DARK) {
          icon.className = 'bi bi-sun-fill';
          toggleBtn.setAttribute('aria-label', 'Переключить на светлую тему');
          toggleBtn.setAttribute('title', 'Светлая тема');
        } else {
          icon.className = 'bi bi-moon-stars-fill';
          toggleBtn.setAttribute('aria-label', 'Переключить на тёмную тему');
          toggleBtn.setAttribute('title', 'Тёмная тема');
        }
      }
  
      /**
       * Watch for system theme changes
       */
      watchSystemTheme() {
        if (!window.matchMedia) return;
  
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        
        // Modern browsers
        if (mediaQuery.addEventListener) {
          mediaQuery.addEventListener('change', (e) => {
            // Only auto-switch if user hasn't manually set a preference
            if (!this.getSavedTheme()) {
              const newTheme = e.matches ? THEME_DARK : THEME_LIGHT;
              this.applyTheme(newTheme);
            }
          });
        }
        // Legacy browsers
        else if (mediaQuery.addListener) {
          mediaQuery.addListener((e) => {
            if (!this.getSavedTheme()) {
              const newTheme = e.matches ? THEME_DARK : THEME_LIGHT;
              this.applyTheme(newTheme);
            }
          });
        }
      }
  
      /**
       * Get current theme
       */
      getTheme() {
        return this.currentTheme;
      }
    }
  
    // Initialize theme manager when DOM is ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        window.themeManager = new ThemeManager();
      });
    } else {
      window.themeManager = new ThemeManager();
    }
  
    // Expose theme manager globally
    window.ThemeManager = ThemeManager;
  
  })();