/**
 * Toast Notification Utility
 * 
 * Provides a lightweight toast notification system.
 */

const ToastUtils = {
    /**
     * Show a toast message
     * @param {string} message - Text content
     * @param {string} type - 'success', 'error', 'info'
     * @param {number} duration - Duration in ms (default 3000)
     */
    show(message, type = 'info', duration = 3000) {
        // Create container if not exists
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }

        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        let icon = '';
        if (type === 'success') icon = '✓';
        if (type === 'error') icon = '⚠️';
        if (type === 'info') icon = 'ℹ️';

        toast.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-message">${this.escapeHtml(message)}</span>`;

        // Add to container
        container.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        // Auto remove
        setTimeout(() => {
            toast.classList.remove('show');
            toast.addEventListener('transitionend', () => {
                toast.remove();
                if (container.children.length === 0) {
                    container.remove();
                }
            });
        }, duration);
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

// Global mount
window.ToastUtils = ToastUtils;
