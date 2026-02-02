/**
 * UI Components - 通用 UI 组件
 * 封装可复用的 UI 元素，避免各模块重复定义
 */

const UIComponents = {
    /**
     * 渲染胶带装饰
     * @param {string} right - 右侧距离，如 '50px'
     * @param {number} rotation - 旋转角度，如 2 或 -1.5
     * @returns {string} HTML 字符串
     */
    renderTape(right = '50px', rotation = null) {
        const deg = rotation !== null ? rotation : (Math.random() * 6 - 3).toFixed(1);
        return `<div class="tape-sticker" style="right:${right}; transform:rotate(${deg}deg);" onclick="UIComponents.rotateTape(this)"></div>`;
    },

    /**
     * 点击胶带时旋转（带 scale 动画）
     * @param {HTMLElement} el - 胶带元素
     */
    rotateTape(el) {
        const newDeg = (Math.random() * 12 - 6).toFixed(1);
        el.style.transform = `rotate(${newDeg}deg) scale(1.1)`;
        setTimeout(() => {
            el.style.transform = `rotate(${newDeg}deg) scale(1)`;
        }, 200);
    },

    /**
     * 渲染卡片 Section 头部
     * @param {Object} options - 配置项
     * @param {string} options.icon - 图标 HTML 或 emoji
     * @param {string} options.iconBg - 图标背景色
     * @param {string} options.iconColor - 图标颜色
     * @param {string} options.title - 标题文字
     * @param {string} options.subtitle - 副标题文字
     * @param {string} options.rightContent - 右侧内容 HTML（可选）
     * @returns {string} HTML 字符串
     */
    renderSectionHeader(options) {
        const { icon = '', iconBg = '#f3f4f6', iconColor = '#666', title = '', subtitle = '', rightContent = '' } = options;
        return `
            <div class="profile-section-header">
                <div class="profile-section-icon" style="background:${iconBg}; color:${iconColor}; border-radius:50%;">
                    ${icon}
                </div>
                <div style="flex:1">
                    <div class="profile-section-title">${title}</div>
                    ${subtitle ? `<div class="profile-section-subtitle">${subtitle}</div>` : ''}
                </div>
                ${rightContent}
            </div>
        `;
    },

    /**
     * 渲染完整的卡片 Section
     * @param {Object} options - 配置项
     * @param {string} options.tapeRight - 胶带右侧距离
     * @param {number} options.tapeRotation - 胶带旋转角度
     * @param {string} options.headerIcon - 图标 HTML
     * @param {string} options.headerIconBg - 图标背景色
     * @param {string} options.headerIconColor - 图标颜色
     * @param {string} options.headerTitle - 标题
     * @param {string} options.headerSubtitle - 副标题
     * @param {string} options.headerRight - 头部右侧内容
     * @param {string} options.content - 内容区域 HTML
     * @returns {string} HTML 字符串
     */
    renderSection(options) {
        const {
            tapeRight = '50px',
            tapeRotation = null,
            headerIcon = '',
            headerIconBg = '#f3f4f6',
            headerIconColor = '#666',
            headerTitle = '',
            headerSubtitle = '',
            headerRight = '',
            content = ''
        } = options;

        return `
            <div class="profile-section">
                ${this.renderTape(tapeRight, tapeRotation)}
                ${this.renderSectionHeader({
            icon: headerIcon,
            iconBg: headerIconBg,
            iconColor: headerIconColor,
            title: headerTitle,
            subtitle: headerSubtitle,
            rightContent: headerRight
        })}
                ${content}
            </div>
        `;
    }
};

window.UIComponents = UIComponents;
