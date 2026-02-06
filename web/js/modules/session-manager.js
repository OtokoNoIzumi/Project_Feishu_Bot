/**
 * Session Manager Module
 * 
 * 负责管理会话生命周期、对话加载、卡片同步
 * 挂载到 Dashboard 实例运行
 */
const SessionManagerModule = {
    createSession(text, images, mode = null) {
        const targetMode = mode || this.mode;
        const session = SessionModule.createSession(targetMode, text, images);

        // 异步计算 SHA-256 哈希
        this.calculateImageHashes(images).then(hashes => {
            session.imageHashes = hashes;
        });

        this.sessions.unshift(session);
        return session;
    },

    // 委托给 ImageUtils
    calculateImageHashes: ImageUtils.calculateImageHashes,

    selectSession(sessionId) {
        const session = this.sessions.find(s => s.id === sessionId);
        if (!session) return;

        this.currentSession = session;
        SessionModule.highlightSession(sessionId);

        // 渲染最新版本或 Draft 状态
        if (session.versions.length > 0) {
            this.renderResult(session);
            if (this.isMobile()) this.setResultPanelOpen(true);
        } else {
            // Phase 2: 如果是 Draft（无分析结果），显示输入预览页
            this.renderDraftState(session);
            if (this.isMobile()) this.setResultPanelOpen(true);
        }
    },

    /**
     * 将后端卡片数据转换为前端 Session 对象
     */
    createSessionFromCard(cardData) {
        if (!cardData) return null;

        const versions = (cardData.versions || []).map((v, i) => ({
            number: i + 1,
            createdAt: new Date(v.created_at || new Date()),
            userNote: v.user_note || '',
            rawResult: v.raw_result || {},
            parsedData: ParserModule.parseResult(v.raw_result || {}, cardData.mode),
            advice: v.advice,
            adviceError: v.adviceError,
            adviceLoading: false
        }));

        const sourceUserNote = cardData.source_user_note || versions[0]?.userNote || '';
        const imageUrls = cardData.image_uris || [];

        return {
            id: cardData.id,
            persistentCardId: cardData.id,
            dialogueId: cardData.dialogue_id,
            mode: cardData.mode,
            createdAt: new Date(cardData.created_at || Date.now()),
            text: sourceUserNote,
            sourceUserNote: sourceUserNote,
            sourceImagesB64: [],
            cardCreated: true,
            images: [],
            imageUrls: imageUrls,
            imageHashes: cardData.image_hashes || [],
            versions: versions,
            currentVersion: cardData.current_version || (versions.length > 0 ? versions.length : 0),
            isSaved: cardData.status === 'saved',
            isQuickRecord: versions.some(v => v.rawResult && v.rawResult.meta && v.rawResult.meta.is_quick_record),
            savedRecordId: cardData.saved_record_id,
            savedData: null
        };
    },

    /**
     * 加载后端卡片 (Phase 2)
     */
    async loadCard(cardId) {
        try {
            if (this.el.resultStatus) this.el.resultStatus.textContent = '加载中...';

            const cardData = await API.getCard(cardId);

            // 尝试并在本地 sessions 查找，避免重复创建
            let session = this.sessions.find(s => s.id === cardData.id);

            if (!session) {
                // 使用提取的方法构造 Session
                session = this.createSessionFromCard(cardData);
                this.sessions.push(session);
            }

            this.selectSession(session.id);
            if (this.el.resultStatus) this.el.resultStatus.textContent = '';

        } catch (e) {
            console.error("Failed to load card", e);
            this.addMessage(`加载分析结果失败: ${e.message}`, 'assistant');
        }
    },

    /**
     * 加载对话并还原消息列表
     */
    async loadDialogue(dialogueId, _preloadedMessages = null) {
        if (!dialogueId) return;

        try {
            const dialogue = _preloadedMessages ? { id: dialogueId, messages: _preloadedMessages } : await API.getDialogue(dialogueId);
            this.currentDialogueId = dialogue.id;
            this.currentSession = null;

            if (this.el.chatMessages) {
                this.el.chatMessages.innerHTML = '';
            }

            const messages = (dialogue.messages || []).slice().sort((a, b) => {
                return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
            });

            if (messages.length === 0) {
                this.addMessage('暂无对话内容', 'assistant');
                return;
            }

            const isImageUrl = (url) => {
                if (typeof url !== 'string') return false;
                return url.startsWith('assets/') || url.startsWith('http') || url.startsWith('data:image') || url.startsWith('/');
            };

            const resolveMessageImages = (msg) => {
                const attachments = (msg.attachments || []).filter(isImageUrl);
                if (attachments.length > 0) return attachments;
                if (Auth.isDemoMode() && msg.linked_card_id && window.DemoScenario?.cards?.[msg.linked_card_id]) {
                    const card = window.DemoScenario.cards[msg.linked_card_id];
                    return (card.image_uris || []).filter(isImageUrl);
                }
                return [];
            };

            messages.forEach(msg => {
                const hasCard = Boolean(msg.linked_card_id);
                const titleHint = msg.title || ((!msg.content && (msg.attachments || []).length > 0)
                    ? `${msg.attachments.length}张图片`
                    : '');
                const options = {
                    title: titleHint,
                    subtitle: msg.subtitle || ''
                };
                const images = resolveMessageImages(msg);
                if (images.length > 0) {
                    options.images = images;
                }
                if (hasCard) {
                    options.sessionId = msg.linked_card_id;
                    options.onClick = () => this.loadCard(msg.linked_card_id);
                }

                SessionModule.renderMessage(
                    this.el.chatMessages,
                    msg.content || '',
                    msg.role || 'user',
                    options
                );
            });
        } catch (e) {
            console.error('[SessionManager] Load dialogue failed:', e);
            this.addMessage(`加载对话失败: ${e.message}`, 'assistant');
        }
    },

    /**
     * 创建新对话 (Phase 2)
     */
    async createNewDialogue() {
        try {
            const dialogue = await API.createDialogue("新对话");
            if (window.SidebarModule) {
                SidebarModule.loadDialogues();
            }
            this.addMessage('已创建新对话', 'assistant');
        } catch (e) {
            console.error("Create dialogue failed", e);
        }
    },

    updateSessionCard(session) {
        const latest = session.versions.length > 0 ? session.versions[session.versions.length - 1] : null;

        let title = '';
        if (latest && latest.parsedData) {
            // 优先使用工具函数，否则回退到内联逻辑
            if (window.CardDisplayUtils?.generateTitle) {
                title = window.CardDisplayUtils.generateTitle(latest.parsedData);
            } else {
                // Fallback: 内联逻辑
                const pd = latest.parsedData;
                if (pd.type === 'diet') {
                    const timeMap = { 'snack': '加餐', 'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐' };
                    const mealTime = timeMap[pd.summary?.dietTime] || '饮食';
                    const dishes = pd.dishes || [];
                    if (dishes.length === 0) {
                        title = mealTime;
                    } else if (dishes.length === 1) {
                        title = `${mealTime} ${dishes[0].name || '未命名'}`;
                    } else {
                        title = `${mealTime} ${dishes[0].name || '未命名'}等${dishes.length}个`;
                    }
                } else if (pd.type === 'keep') {
                    const count = (pd.scaleEvents?.length || 0) + (pd.sleepEvents?.length || 0) + (pd.bodyMeasureEvents?.length || 0);
                    title = `Keep - ${count}条记录`;
                }
            }
        }

        SessionModule.updateCardVisuals(session.id, title, {
            current: session.currentVersion,
            total: session.versions.length,
            isLatest: session.currentVersion === session.versions.length
        });
    },

    // 版本切换
    switchVersion(delta) {
        if (!this.currentSession) return;

        const session = this.currentSession;
        const newVersion = session.currentVersion + delta;

        if (newVersion < 1 || newVersion > session.versions.length) return;

        session.currentVersion = newVersion;
        this.renderResult(session);
    }
};

window.SessionManagerModule = SessionManagerModule;
