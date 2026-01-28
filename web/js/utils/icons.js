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
    'bookmark': { src: 'bookmark.png', type: 'stamp', defaultClass: '' },
    'profile_woman': { src: 'profile_alt.png', type: 'stamp', defaultClass: '' },
    'profile_man': { src: 'profile.png', type: 'stamp', defaultClass: '' },
    'comment': { src: 'notepad.png', type: 'stamp', defaultClass: '' }, // Reusing notepad for comment
    'undo': { src: 'refresh.png', type: 'stamp', defaultClass: '' }, // Reusing refresh for undo
    'arrow_left': { src: 'arrow_left.png', type: 'stamp', defaultClass: '' }, // Assuming arrow_left.png exists or fallback
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


/**
 * Placeholder Emoji Icons
 * 临时使用 Emoji，后续可替换为手绘图标
 * 具体图标待设计，这里只做语义映射
 */
const EMOJI_ICONS = {
    // Sidebar 状态
    'status-saved': '✅',
    'status-draft': '📝',
    'status-analyzing': '⏳',
    'status-error': '❌',

    // 类型标识
    'type-diet': '🍽️',
    'type-keep': '🏋️',
    'type-dialogue': '💬',

    // 操作
    'action-expand': '▼',
    'action-collapse': '►',
    'action-more': '...',
    'action-search': '🔍',

    // Demo
    'demo-badge': '🎯',
};

// 映射表：Emoji Icon Name -> Hand-Drawn Icon Name
const EMOJI_TO_HAND_DRAWN = {
    'status-saved': 'check',
    'status-draft': 'pencil',
    // ... 后续填充
};

export const EmojiIcon = {
    /**
     * 渲染 Emoji (未来可替换为 IconManager.render)
     */
    render: (name) => {
        const emoji = EMOJI_ICONS[name];
        if (!emoji) {
            console.warn(`Emoji icon not found: ${name}`);
            return '<span>?</span>';
        }
        // 用 span 包裹，便于后续用 CSS 隐藏或替换
        return `<span class="emoji-icon" data-icon="${name}">${emoji}</span>`;
    },

    /**
     * 批量替换：将所有 [data-icon] 的 emoji 换成手绘图标
     * 后续实现时调用
     */
    replaceAll: () => {
        document.querySelectorAll('.emoji-icon[data-icon]').forEach(el => {
            const name = el.dataset.icon;
            // 检查是否有对应的手绘图标
            const mappedIcon = EMOJI_TO_HAND_DRAWN[name];
            if (mappedIcon && ICONS[mappedIcon]) {
                el.outerHTML = IconManager.render(mappedIcon);
            }
        });
    }
};

window.EmojiIcon = EmojiIcon;
