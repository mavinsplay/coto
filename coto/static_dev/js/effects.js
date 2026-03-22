/**
 * EffectsManager handles the UI and logic for emoji reactions and blur effects.
 */
class EffectsManager {
    constructor(player, socket) {
        this.player = player;
        this.socket = socket;
        this.container = null;
        this.panel = null;
        this.blurEnabled = false;
        this.init();
    }

    init() {
        // Create container for floating emojis if not exists
        const wrapper = this.player.elements.container;
        this.container = document.createElement('div');
        this.container.id = 'effects-container';
        wrapper.appendChild(this.container);

        // Create effects panel
        this.createPanel();

        // Listen for blur toggle local event
        document.addEventListener('toggle-blur', () => this.toggleBlur());
    }

    createPanel() {
        this.panel = document.createElement('div');
        this.panel.className = 'plyr__effects-panel';
        this.panel.innerHTML = `
            <div class="plyr__effects-grid">
                <div class="effect-btn" data-emoji="❤️">❤️</div>
                <div class="effect-btn" data-emoji="😂">😂</div>
                <div class="effect-btn" data-emoji="🔥">🔥</div>
                <div class="effect-btn" data-emoji="👍">👍</div>
                <div class="effect-btn" data-emoji="😮">😮</div>
                <div class="effect-btn" data-emoji="🎉">🎉</div>
            </div>
            <div class="blur-toggle-container">
                <span class="blur-label">Размытие</span>
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="blur-switch">
                </div>
            </div>
        `;

        const wrapper = this.player.elements.container;
        wrapper.appendChild(this.panel);

        // Emoji click handlers
        this.panel.querySelectorAll('.effect-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const emoji = btn.dataset.emoji;
                this.sendEffect('emoji', { emoji });
                this.showEmoji(emoji);
            });
        });

        // Blur switch handler
        const blurSwitch = this.panel.querySelector('#blur-switch');
        blurSwitch.addEventListener('change', (e) => {
            this.toggleBlur(e.target.checked);
        });

        // Close panel when clicking outside
        document.addEventListener('click', (e) => {
            if (!this.panel.contains(e.target) && !e.target.closest('.plyr__control--effects')) {
                this.panel.classList.remove('active');
            }
        });
    }

    togglePanel() {
        this.panel.classList.toggle('active');
    }

    sendEffect(subType, data) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.sendSafe({
                type: 'effect',
                subType,
                ...data,
                ts: Date.now()
            });
        }
    }

    handleEffect(msg) {
        if (msg.subType === 'emoji') {
            this.showEmoji(msg.emoji);
        } else if (msg.subType === 'blur') {
            this.toggleBlur(msg.enabled, false); // false to avoid recursive broadcast
        }
    }

    showEmoji(emoji) {
        const span = document.createElement('span');
        span.className = 'floating-emoji';
        span.textContent = emoji;
        
        // Randomize position and rotation
        const left = Math.random() * 80 + 10; // 10% to 90%
        const rot = (Math.random() - 0.5) * 40; // -20deg to 20deg
        
        span.style.left = `${left}%`;
        span.style.setProperty('--rand-rot', `${rot}deg`);
        
        this.container.appendChild(span);
        
        // Remove after animation
        setTimeout(() => {
            span.remove();
        }, 3000);
    }

    toggleBlur(force, shouldBroadcast = true) {
        this.blurEnabled = typeof force !== 'undefined' ? force : !this.blurEnabled;
        const videoWrapper = this.player.elements.container;
        
        if (this.blurEnabled) {
            videoWrapper.classList.add('video-blur');
        } else {
            videoWrapper.classList.remove('video-blur');
        }
        
        // Sync switch state if it was toggled externally
        const blurSwitch = this.panel.querySelector('#blur-switch');
        if (blurSwitch && blurSwitch.checked !== this.blurEnabled) {
            blurSwitch.checked = this.blurEnabled;
        }

        // Broadcast to others
        if (shouldBroadcast) {
            this.sendEffect('blur', { enabled: this.blurEnabled });
        }
    }
}

// Export for use in sync_player.js
window.EffectsManager = EffectsManager;
