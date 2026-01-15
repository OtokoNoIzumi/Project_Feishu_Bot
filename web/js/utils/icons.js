/**
 * Centralized Icon Management System for Warm Notebook Theme
 * Manages hand-drawn icon assets (stickers/stamps) to replace emojis.
 */

const ICONS = {
    // Stickers (Colorful, object-like)
    'logo': { src: 'apple.png', type: 'sticker', defaultClass: 'lg' },
    'save': { src: 'pin.png', type: 'sticker', defaultClass: '' },
    'add': { src: 'add.png', type: 'sticker', defaultClass: '' }, // Actually this might be a stamp? No, colorful plus is nice.
    'meal': { src: 'bowl.png', type: 'sticker', defaultClass: '' },
    'chart': { src: 'chart.png', type: 'sticker', defaultClass: '' }, // Wait, chart is colored now? Yes.
    'heart': { src: 'heart.png', type: 'sticker', defaultClass: '' },

    // Stamps (Monochrome/Ink, functional)
    'analysis': { src: 'notepad.png', type: 'stamp', defaultClass: '' },
    'profile': { src: 'gear.png', type: 'stamp', defaultClass: '' },
    'refresh': { src: 'refresh.png', type: 'stamp', defaultClass: '' },
    'update': { src: 'sparkle.png', type: 'stamp', defaultClass: '' },
    'settings': { src: 'gear.png', type: 'stamp', defaultClass: '' },
    'empty': { src: 'bowl.png', type: 'stamp', defaultClass: 'xl' }, // Use bowl as stamp for empty state? Or colored? Let's use colored for empty state actually.
    'list': { src: 'notepad.png', type: 'stamp', defaultClass: '' },
    'lightbulb': { src: 'lightbulb.png', type: 'stamp', defaultClass: '' },
    'check': { src: 'check.png', type: 'stamp', defaultClass: '' },
    'pencil': { src: 'pencil.png', type: 'stamp', defaultClass: '' },
};

/**
 * Returns the HTML string for an icon.
 * @param {string} name - The key name of the icon (e.g., 'logo', 'save').
 * @param {string} extraClasses - Additional CSS classes (e.g., 'lg', 'xl').
 * @returns {string} HTML string for the img tag.
 */
function getIconIndex(name) {
    return ICONS[name] || null;
}

const ICON_VERSION = 'v=fixed_center_01';

export const IconManager = {

    /**
     * Get the full IMG tag for an icon
     */
    render: (name, extraClasses = '') => {
        const config = ICONS[name];
        if (!config) {
            console.warn(`Icon not found: ${name}`);
            return `<span>?</span>`;
        }

        // Base class: icon-sticker or icon-stamp
        const baseClass = `icon-${config.type}`;
        // Combine classes
        const classes = `hand-icon ${baseClass} ${config.defaultClass} ${extraClasses}`.trim();

        return `<img src="css/icons/${config.src}?${ICON_VERSION}" class="${classes}" alt="${name}">`;
    },

    /**
     * Get just the src URL for an icon
     */
    getSrc: (name) => {
        const config = ICONS[name];
        return config ? `css/icons/${config.src}?${ICON_VERSION}` : '';
    },

    /**
     * Apply icons to specific DOM elements automatically (optional helper)
     */
    replaceEmojis: () => {
        // Implementation for scanning [data-icon="name"] if we move to that system
    }
};

// Make it globally available for legacy non-module scripts if needed
window.IconManager = IconManager;
