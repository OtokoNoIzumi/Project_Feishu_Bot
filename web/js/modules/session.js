/**
 * Session 管理模块
 * 
 * 负责左侧聊天/会话列表的渲染和 DOM 管理
 * 不包含具体的业务逻辑（如能量计算、API调用）
 */
const SessionModule = {
    // 创建基础 Session 对象
    createSession(mode, text, images) {
        return {
            id: Date.now().toString(),
            mode: mode,
            createdAt: new Date(),
            text: text,
            images: images, // { file, base64, preview }
            imageUrls: images.map(img => img.preview),
            imageHashes: [],
            versions: [],
            currentVersion: 0,
            isSaved: false,
            savedRecordId: null,
            savedData: null,
        };
    },

    // 向容器添加消息/卡片
    renderMessage(container, content, role, options = {}) {
        const msg = document.createElement('div');
        msg.className = `message ${role}`;

        // 加载状态
        if (options.isLoading) {
            msg.classList.add('loading');
        }

        if (options.sessionId) {
            msg.dataset.sessionId = options.sessionId;
            msg.classList.add('session-card');

            // 绑定点击事件
            if (typeof options.onClick === 'function') {
                msg.onclick = () => options.onClick(options.sessionId);
            }
        }

        // 图片预览
        if (options.images && options.images.length > 0) {
            const imgContainer = document.createElement('div');
            imgContainer.className = 'message-images';
            options.images.forEach(url => {
                const img = document.createElement('img');
                img.src = url;
                imgContainer.appendChild(img);
            });
            msg.appendChild(imgContainer);
        }

        // 标题区域 (Header)
        // 只要有 title 或 sessionId，就渲染 Header，保证布局一致
        if (options.title || options.sessionId || (options.version && options.version > 1)) {
            const headerEl = document.createElement('div');
            headerEl.className = 'message-header';

            // 标题
            const titleEl = document.createElement('div');
            titleEl.className = 'message-title';
            titleEl.textContent = options.title || '';
            headerEl.appendChild(titleEl);

            // 版本标签
            if (options.version && options.version > 1) {
                const versionEl = document.createElement('span');
                versionEl.className = 'version-badge';
                versionEl.textContent = `v${options.version}`;
                headerEl.appendChild(versionEl);
            }

            msg.appendChild(headerEl);
        }

        // 文字内容
        if (content) {
            const textEl = document.createElement('div');
            textEl.className = 'message-text';
            // 支持 HTML 内容（用于渲染 markdown）
            if (options.isHtml) {
                textEl.innerHTML = content;
            } else {
                textEl.textContent = content;
            }
            msg.appendChild(textEl);
        }

        if (container) {
            container.appendChild(msg);
            container.scrollTop = container.scrollHeight;
        }

        return msg;
    },

    // 更新 Session 卡片的视觉状态（标题、版本标）
    updateCardVisuals(sessionId, title, versionInfo = null) {
        const card = document.querySelector(`[data-session-id="${sessionId}"]`);
        if (!card) return;

        // 1. 更新标题
        if (title) {
            let titleEl = card.querySelector('.message-title');
            if (!titleEl) {
                // 如果结构缺失，尝试重建 Header
                let header = card.querySelector('.message-header');
                if (!header) {
                    header = document.createElement('div');
                    header.className = 'message-header';
                    // 插入到最前面
                    card.insertBefore(header, card.firstChild);
                }
                titleEl = document.createElement('div');
                titleEl.className = 'message-title';
                header.appendChild(titleEl);
            }
            titleEl.textContent = title;
        }

        // 2. 更新版本 Badge
        if (versionInfo && versionInfo.total > 1) {
            const header = card.querySelector('.message-header');
            if (header) {
                let badge = header.querySelector('.version-badge');
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'version-badge';
                    header.appendChild(badge);
                }

                badge.textContent = `v${versionInfo.current}/${versionInfo.total}`;

                if (versionInfo.isLatest) {
                    badge.style.opacity = '1';
                    badge.title = '最新版本';
                } else {
                    badge.style.opacity = '0.7';
                    badge.title = '历史版本';
                }
            }
        }
    },

    // 高亮当前选中的 Session
    highlightSession(sessionId) {
        document.querySelectorAll('.session-card').forEach(el => {
            el.classList.toggle('active', el.dataset.sessionId === String(sessionId));
        });
    }
};

window.SessionModule = SessionModule;
