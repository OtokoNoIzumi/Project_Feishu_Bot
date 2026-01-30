/**
 * Analysis 模块
 *
 * 负责处理核心分析流程、API 调用、版本管理和建议生成
 * 采用 Mixin 模式挂载到 Dashboard 实例运行
 */
const AnalysisModule = {

    async reAnalyze() {
        if (!this.currentSession) {
            this.addMessage('请先选择一个分析会话', 'assistant');
            return;
        }

        const session = this.currentSession;
        // 重新分析：直接使用当前输入框内容（已包含 user_note，不再二次拼接）
        const fullNote = document.getElementById('additional-note')?.value.trim() || '';
        const fallbackNote = session.sourceUserNote || session.text || '';
        const effectiveNote = fullNote || fallbackNote;
        const hasImages = (session.images && session.images.length > 0) ||
            (session.sourceImagesB64 && session.sourceImagesB64.length > 0);
        if (!effectiveNote && !hasImages) {
            this.addMessage('缺少原始图片或文本，无法重新分析，请重新上传。', 'assistant');
            return;
        }

        // 执行分析（使用原始附件）
        await this.executeAnalysis(session, effectiveNote);
    },

    async retryLastAnalysis() {
        const session = this.currentSession;
        if (!session) return;

        // 使用上次尝试时的输入，如果没有则回退 to session 原始文本
        const userNote = session._lastUserNote !== undefined ? session._lastUserNote : (session.text || '');
        this.addMessage('正在重试...', 'assistant');
        await this.executeAnalysis(session, userNote);
    },

    async executeAnalysis(session, userNote) {
        if (Auth.isDemoMode()) {
            if (window.Dashboard?.checkDemoLimit && window.Dashboard.checkDemoLimit()) return;
            return;
        }
        session._lastUserNote = userNote; // 保存以备重试
        session.lastError = null; // 清除之前的错误状态
        this.showLoading();


        try {
            if ((!session.images || session.images.length === 0) && (session.sourceImagesB64 || []).length > 0) {
                session.images = session.sourceImagesB64.map(b64 => ({ base64: b64, preview: '', file: null }));
            }
            let imagesB64 = (session.images || []).map(img => img.base64);
            if (imagesB64.length === 0 && (session.imageUrls || []).length > 0) {
                imagesB64 = await this._loadImagesFromUris(session.imageUrls);
                if (imagesB64.length > 0) {
                    session.images = imagesB64.map(b64 => ({ base64: b64, preview: '', file: null }));
                }
            }
            if ((!session.sourceImagesB64 || session.sourceImagesB64.length === 0) && imagesB64.length > 0) {
                session.sourceImagesB64 = imagesB64;
            }
            if (!session.sourceUserNote && userNote) {
                session.sourceUserNote = userNote;
            }
            let result;

            if (session.mode === 'diet') {
                result = await API.analyzeDiet(userNote, imagesB64);
            } else {
                // Keep 模式使用 unified analyze
                result = await API.analyzeKeep(userNote, imagesB64);
            }

            console.log('[Dashboard] API result:', result);

            if (!result.success) {
                // 同样使用统一错误处理并回到 Draft 状态
                const errorInfo = window.ErrorHandlerModule
                    ? window.ErrorHandlerModule.getFriendlyError(result.error || '分析失败')
                    : { title: '分析失败', message: result.error || '未知错误', level: 'error', action: 'retry' };

                session.lastError = errorInfo;
                this.renderDraftState(session);
                return;
            }

            // 添加新版本
            const version = {
                number: session.versions.length + 1,
                createdAt: new Date(),
                userNote: userNote,
                rawResult: result.result,
                parsedData: ParserModule.parseResult(result.result, session.mode),
                advice: null,
                adviceError: null,
                adviceLoading: false,
            };
            session.versions.push(version);
            session.currentVersion = version.number;

            // 更新消息卡片标题 (UI)
            this.updateSessionCard(session);

            // ================== 持久化逻辑 (Draft First) ==================
            // 只有当有 dialogueId 时才进行持久化
            if (session.dialogueId) {
                if (!session.cardCreated) {
                    this.addMessage('分析结果卡片尚未建立，无法更新。', 'assistant');
                    return;
                }
                // 1. 生成或使用现有的 Card ID (如果是新 Session，生成 UUID; 如果已存在，沿用)
                // 注意：Session ID 本身是 Date.now()，这里我们为后端生成一个 UUID
                if (!session.persistentCardId) {
                    session.persistentCardId = crypto.randomUUID ? crypto.randomUUID() : `card-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                }
                const cardId = session.persistentCardId;

                // 2. 构造 ResultCard 对象
                // 先保存 Hashes 到 Session (构建 Card 需要)
                session.imageHashes = result.result.image_hashes || [];
                const cardData = this._buildCardData(session);

                // 3. 调用 API 保存 Card
                // 使用 queueMicrotask 或非阻塞调用，但为了数据一致性最好 await
                await API.updateCard(cardId, cardData).catch(e => console.error("Auto-update card failed:", e));

                // 4. 回填 User Message (Attachments + Card Link)
                if (session.lastUserMessage && session.lastUserMessage.id) {
                    const messageTitle = this._generateMessageTitle(version.parsedData);
                    const msgPayload = {
                        ...session.lastUserMessage,
                        title: messageTitle,
                        attachments: result.result.image_hashes || [],
                        linked_card_id: cardId
                    };
                    session.lastUserMessage = msgPayload;
                    API.updateMessage(session.dialogueId, msgPayload).catch(e => console.error("Update user msg failed:", e));
                }

                // 5. 刷新侧边栏
                if (window.SidebarModule) window.SidebarModule.loadDialogues();
            }
            // ==========================================================

            // 渲染结果 (UI)
            this.renderResult(session);
            if (this.isMobile()) this.setResultPanelOpen(true);

            // Limit updated, trigger refresh
            if (window.ProfileModule) {
                ProfileModule.refreshLimits();
            }

            this.addMessage('分析完成！', 'assistant');

            // 自动触发 advice 请求（仅饮食模式）
            if (session.mode === 'diet' && this.currentDishes?.length > 0) {
                this.autoFetchAdvice();
            }

        } catch (error) {
            this.updateStatus('');  // 停止加载状态
            console.error("Execute analysis error:", error);

            // 1. 统一错误处理
            const errorInfo = window.ErrorHandlerModule
                ? window.ErrorHandlerModule.getFriendlyError(error)
                : { title: '分析失败', message: error.message || '未知错误', level: 'error', action: 'retry' };

            // 2. 将错误暂存到 Session (用于 UI 渲染)
            session.lastError = errorInfo;

            // 3. 渲染带有错误信息的 Draft 状态
            // 这样用户可以看到之前上传的图片/文字，直接修改后重试
            this.renderDraftState(session);

            // 4. (可选) 也发送一条简短的消息到聊天区，避免用户没看右边
            // 但如果错误是引导付费类的，还是需要特定 Action Button
            const actions = [];
            if (errorInfo.action === 'profile_code') {
                actions.push({
                    text: '🔑 去输入激活码',
                    class: 'btn-primary',
                    onClick: () => Dashboard.switchView('profile')
                });
            } else if (errorInfo.action === 'retry') {
                actions.push({
                    text: '🔄 重试',
                    class: 'btn-ghost',
                    onClick: () => this.retryDraft(session.id) // 重试 Draft
                });
            }

            // 防抖：如果最后一条已经是这个错误，就不发了
            const messagesContainer = document.getElementById('chat-messages');
            if (messagesContainer) {
                const assistantMsgs = messagesContainer.querySelectorAll('.message.assistant');
                const lastMsg = assistantMsgs.length > 0 ? assistantMsgs[assistantMsgs.length - 1] : null;
                const lastContentRaw = lastMsg?.querySelector('.message-text')?.innerText || '';
                const cleanLast = lastContentRaw.replace(/\s+/g, '');
                const cleanNew = errorInfo.message.replace(/<br\s*\/?>/gi, '').replace(/\s+/g, '');

                if (lastMsg && cleanLast.includes(cleanNew)) {
                    if (window.ToastUtils) {
                        ToastUtils.show(errorInfo.message.split('\n')[0], errorInfo.level || 'error');
                        return; // Skip adding message
                    }
                }
            }

            // 发送消息
            this.addMessage(`${errorInfo.title}: ${errorInfo.message}`, 'assistant', { actions });

            // Toast 提示
            if (window.ToastUtils && errorInfo.level === 'error') {
                ToastUtils.show(errorInfo.title, 'error');
            }
        }

    },

    async updateAdvice() {
        if (!this.currentSession) return;

        const session = this.currentSession;
        const currentVersion = session.versions[session.currentVersion - 1];
        if (!currentVersion) return;

        if (session.mode !== 'diet') {
            this.addMessage('Keep 模式暂不支持建议生成', 'assistant');
            return;
        }

        let loadingMsg = null;
        const btn = document.getElementById('update-advice-btn');

        try {
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = `⏳ 生成中...`;
            }
            loadingMsg = this.addMessage('正在根据最新数据更新建议...', 'assistant', { isLoading: true });

            // Collect facts
            const facts = this.collectEditedData();
            const userNote = document.getElementById('additional-note')?.value.trim() || '';

            // Reset advice state
            currentVersion.advice = '';
            currentVersion.adviceError = null;
            // No need to set loading=true on version because we want to see the text appear immediately
            // But for UI status indicator, we might want loading style.
            currentVersion.adviceLoading = true;

            // Initial render (empty/loading state)
            this.renderAdvice('', true);

            await API.getDietAdviceStream(
                facts,
                userNote,
                null,
                [],
                (chunk) => {
                    // On Chunk
                    currentVersion.advice += chunk;
                    // Update UI
                    this.renderAdvice(currentVersion.advice, true);
                }
            );

            // Stream Done
            currentVersion.adviceLoading = false;
            this.renderAdvice(currentVersion.advice, false); // Final render

            if (loadingMsg) loadingMsg.remove();
            this.addMessage('建议已更新', 'assistant');

            if (window.ProfileModule) {
                ProfileModule.refreshLimits();
            }

            // Persistence
            if (session.persistentCardId) {
                const cardData = this._buildCardData(session);
                if (cardData) API.updateCard(session.persistentCardId, cardData).catch(console.warn);
            }

        } catch (error) {
            if (loadingMsg) loadingMsg.remove();
            currentVersion.adviceLoading = false;
            currentVersion.adviceError = error.message;

            // Error handling logic (copied from previous)
            const errorCode = error.message?.includes('DAILY_LIMIT') ? 'DAILY_LIMIT_REACHED' : 'UNKNOWN';

            let userTip = `建议更新失败: ${error.message}`;
            let actions = [];

            if (errorCode === 'DAILY_LIMIT_REACHED') {
                userTip = `每日定制建议生成次数已耗尽。请升级会员继续使用。`;
                actions.push({
                    text: '🔑 去输入激活码',
                    class: 'btn-primary',
                    onClick: () => Dashboard.switchView('profile')
                });
            } else {
                actions.push({
                    text: '🔄 重试',
                    class: 'btn-ghost',
                    onClick: () => this.updateAdvice()
                });
            }

            this.addMessage(userTip, 'assistant', { actions });
            this.renderAdviceError(error.message);

        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<img src="css/icons/sparkle.png" class="icon-stamp" alt="Update"> 更新建议`;
            }
        }
    },

    // 自动获取建议（分析完成后调用，不阻塞 UI）
    async autoFetchAdvice() {
        if (!this.currentSession || this.currentSession.mode !== 'diet') return;

        const session = this.currentSession;
        const currentVersion = session.versions[session.currentVersion - 1];
        if (!currentVersion || currentVersion.advice) return; // 已有建议则跳过

        try {
            // Clean state
            currentVersion.advice = '';
            currentVersion.adviceError = null;
            currentVersion.adviceLoading = true;
            this.renderAdvice('', true); // Show loading spinner

            // Collect facts
            const facts = this.collectEditedData();
            const userNote = document.getElementById('additional-note')?.value.trim() || '';

            await API.getDietAdviceStream(
                facts,
                userNote,
                null,
                [],
                (chunk) => {
                    currentVersion.advice += chunk;
                    this.renderAdvice(currentVersion.advice, true);
                }
            );

            // Done
            currentVersion.adviceLoading = false;
            this.renderAdvice(currentVersion.advice, false);
            // Limit updated
            if (window.ProfileModule) {
                ProfileModule.refreshLimits();
            }

            // Persistence
            if (session.persistentCardId) {
                const cardData = this._buildCardData(session);
                if (cardData) API.updateCard(session.persistentCardId, cardData).catch(console.warn);
            }
        } catch (error) {
            currentVersion.adviceLoading = false;
            currentVersion.adviceError = error.message;
            this.renderAdviceError(error.message);
        }
    },

    // ========== Independent Advice Mode (顾问模式) ==========

    async startAdviceChat(userNote) {
        // Capture images
        const images = [...this.pendingImages];
        const imageUrls = images.map(img => img.preview);
        const imagesB64 = images.map(img => img.base64);

        if (!userNote && images.length === 0) return;

        console.log('[startAdviceChat] currentDialogueId:', this.currentDialogueId);

        // 1. 确保有通过 Dashboard 创建的 Dialogue
        if (!this.currentDialogueId) {
            const title = userNote ? userNote.slice(0, 15) : (images.length ? `${images.length}张图片` : '顾问咨询');
            try {
                const dialogue = await API.createDialogue(title);
                this.currentDialogueId = dialogue.id;
                if (window.SidebarModule) window.SidebarModule.loadDialogues();
            } catch (e) { console.error(e); }
        }

        // 2. 显示用户消息
        this.addMessage(userNote || (images.length > 0 ? '[图片]' : ''), 'user', { images: imageUrls });

        // 清理输入框
        if (this.el.chatInput) this.el.chatInput.value = '';
        this.pendingImages = [];
        this.renderPreviews();
        this.updateSendButton();

        // 2b. 立即持久化用户消息 (Fix: Write BEFORE API call to ensure order)
        if (this.currentDialogueId && (userNote || images.length > 0)) {
            const now = new Date();
            const usrMsgId = now.getTime().toString();
            // Fire and forget, but it's sent before advice request
            API.appendMessage(this.currentDialogueId, {
                id: usrMsgId,
                role: 'user',
                content: userNote || (images.length > 0 ? '[图片]' : ''),
                timestamp: now.toISOString(),
                attachments: [] // Attachments logic for images if needed in future
            }).catch(console.warn);
        }

        const loadingMsg = this.addMessage('思考中...', 'assistant', { isLoading: true });

        // 3. 调用 Advice API (Mixed Input)
        // Independent Mode: facts is empty
        const facts = {};

        try {
            // Note: API.getDietAdvice takes (facts, userNote, dialogueId, imagesB64)
            // ... (comments kept)

            const response = await API.getDietAdvice(facts, userNote, this.currentDialogueId, imagesB64);

            if (loadingMsg) loadingMsg.remove();

            let resultText = '';
            if (response.success && response.result?.advice_text) {
                resultText = response.result.advice_text;
            } else {
                resultText = response.error || '无法获取建议';
            }

            // Render HTML
            const html = this.simpleMarkdownToHtml(resultText);
            this.addMessage(html, 'assistant', { isHtml: true });

            // Limit updated, trigger refresh
            if (window.ProfileModule) {
                ProfileModule.refreshLimits();
            }

            // 持久化 Assistant Msg
            if (this.currentDialogueId) {
                const aiNow = new Date();
                const msgId = aiNow.getTime().toString(); // simplified
                const msgPayload = {
                    id: msgId,
                    role: 'assistant',
                    content: resultText,
                    timestamp: aiNow.toISOString(),
                    attachments: [],
                };
                API.appendMessage(this.currentDialogueId, msgPayload).catch(console.warn);
            }

        } catch (e) {
            if (loadingMsg) loadingMsg.remove();
            this.addMessage(`出错了: ${e.message}`, 'assistant');
        }
    },

    // ========== Helpers ==========

    _buildCardData(session) {
        if (!session || !session.persistentCardId) return null;

        // 获取最新的编辑数据
        let currentData = null;
        if (session.mode === 'diet' && typeof this.collectEditedData === 'function') {
            currentData = this.collectEditedData();
        }

        // 深度复制 versions
        const updatedVersions = JSON.parse(JSON.stringify(session.versions));

        // 如果有编辑数据，更新当前版本
        // 注意：session.currentVersion 是 1-based index
        if (currentData && updatedVersions.length >= session.currentVersion) {
            const currentVer = updatedVersions[session.currentVersion - 1];

            if (session.mode === 'diet') {
                // 1. 更新 Summary
                currentVer.rawResult.meal_summary = currentData.meal_summary;
                // 2. 更新 Dishes
                currentVer.rawResult.dishes = currentData.dishes;
                // 3. 更新 Labels
                currentVer.rawResult.captured_labels = currentData.captured_labels;

                // Update parsedData for consistency
                currentVer.parsedData.summary.totalEnergy = currentData.meal_summary.total_energy_kj;
                currentVer.parsedData.dishes = currentData.dishes;
            }
        }

        // 找到最新版本的 parsedData 用于生成 Title
        const latestVersion = updatedVersions[session.currentVersion - 1];

        return {
            id: session.persistentCardId,
            dialogue_id: session.dialogueId,
            mode: session.mode,
            title: this._generateCardTitle(latestVersion?.parsedData),
            user_id: 'placeholder',
            source_user_note: session.sourceUserNote || session.text || '',
            image_uris: (session.imageUrls || []).filter(url => url && !url.startsWith('blob:') && !url.startsWith('data:')),
            image_hashes: session.imageHashes || [],
            saved_record_id: session.savedRecordId || null,
            versions: updatedVersions.map(v => ({
                created_at: v.createdAt, // Assume string or Date handled by JSON.stringify eventually, but better keep original format if possible. Previous code used toISOString()
                user_note: v.userNote,
                raw_result: v.rawResult,
                advice: v.advice,
                adviceError: v.adviceError
            })),
            current_version: session.currentVersion,
            status: session.isSaved ? 'saved' : 'draft',
            created_at: session.createdAt instanceof Date ? session.createdAt.toISOString() : session.createdAt,
            updated_at: new Date().toISOString()
        };
    },

    _generateCardTitle(parsedData) {
        if (!parsedData) return '未命名分析结果';

        // Helper to get helper methods from Dashboard context if valid
        const getUnit = () => (this.getEnergyUnit ? this.getEnergyUnit() : 'kJ');
        const toKcal = (v) => (this.kJToKcal ? this.kJToKcal(v) : v / 4.184);

        const dateStr = window.DateFormatter ? window.DateFormatter.formatSmart(new Date()) : '';

        if (parsedData.type === 'diet') {
            const timeMap = {
                'snack': '加餐', 'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐'
            };
            const time = timeMap[parsedData.summary.dietTime] || '饮食';
            const unit = getUnit();

            // Energy
            let energy = parsedData.summary.totalEnergy || 0;
            if (unit === 'kcal') {
                energy = toKcal(energy);
            }
            const energyStr = `${Math.round(energy)}${unit}`;

            // Weight
            const totalWeight = (parsedData.dishes || []).reduce((sum, d) => sum + (d.weight_g || 0), 0);
            const weightStr = totalWeight > 0 ? `${totalWeight}g` : '';

            return `${dateStr} ${time} ${energyStr} ${weightStr}`.trim();
        } else {
            const count = (parsedData.scaleEvents?.length || 0) +
                (parsedData.sleepEvents?.length || 0) +
                (parsedData.bodyMeasureEvents?.length || 0);
            return `${dateStr} Keep记录 ${count}项`.trim();
        }
    },

    _generateCardSummary(parsedData) {
        if (!parsedData) return '分析完成';

        if (parsedData.type === 'diet') {
            const unit = 'kJ'; // 默认后端存的都是 kJ，前端展示再转换
            // 这里为了 Summary 简短，直接用 totalEnergy
            const val = Math.round(parsedData.summary.totalEnergy || 0);
            const count = parsedData.dishes ? parsedData.dishes.length : 0;
            return `饮食结果: ${val} kJ · ${count}种食物`;
        } else {
            // Keep mode
            let count = 0;
            if (parsedData.scaleEvents) count += parsedData.scaleEvents.length;
            if (parsedData.sleepEvents) count += parsedData.sleepEvents.length;
            if (parsedData.bodyMeasureEvents) count += parsedData.bodyMeasureEvents.length;
            return `Keep识别: 发现 ${count} 项数据`;
        }
    },

    _generateMessageTitle(parsedData) {
        if (!parsedData) return '';

        if (parsedData.type === 'diet') {
            const unit = (ProfileModule.getCurrentProfile()?.diet?.energy_unit) || 'kJ';
            const energy = parsedData.summary.totalEnergy || 0;
            const val = unit === 'kcal' ? Math.round(energy) : Math.round(EnergyUtils.kcalToKJ(energy));
            const count = parsedData.dishes ? parsedData.dishes.length : 0;
            return `${val} ${unit} - ${count}种食物`;
        }

        const eventCount = (parsedData.scaleEvents?.length || 0) +
            (parsedData.sleepEvents?.length || 0) +
            (parsedData.bodyMeasureEvents?.length || 0);
        return `Keep - ${eventCount}条记录`;
    },

    _setAdviceLoading(version, isLoading) {
        if (!version) return;
        version.adviceLoading = Boolean(isLoading);
        const contentEl = document.getElementById('advice-content');
        const statusEl = document.getElementById('advice-status');
        if (!contentEl || !statusEl) return;

        // Update status class
        statusEl.className = 'advice-status';
        if (version.adviceLoading) {
            statusEl.classList.add('loading');
        } else if (version.adviceError) {
            statusEl.classList.add('error');
        }

        // Generate content using shared renderer
        // Note: Assuming AnalysisModule is mixed into Dashboard alongside DietRenderModule
        if (typeof this.generateAdviceHtml === 'function') {
            contentEl.innerHTML = this.generateAdviceHtml(version);
        } else {
            console.warn('generateAdviceHtml not found on this context');
        }
    },

    async _loadImagesFromUris(imageUris) {
        const results = [];
        for (const uri of imageUris || []) {
            if (!uri) continue;
            if (uri.startsWith('data:image')) {
                const parts = uri.split(',');
                if (parts.length > 1) results.push(parts[1]);
                continue;
            }
            try {
                const res = await fetch(uri);
                if (!res.ok) continue;
                const blob = await res.blob();
                const b64 = await new Promise(resolve => {
                    const reader = new FileReader();
                    reader.onload = () => {
                        const text = String(reader.result || '');
                        resolve(text.split(',')[1] || '');
                    };
                    reader.readAsDataURL(blob);
                });
                if (b64) results.push(b64);
            } catch (e) {
                console.warn('[Analysis] Failed to fetch image uri:', uri, e);
            }
        }
        return results;
    },
    renderDraftState(session) {
        const container = this.el.resultContent;
        if (!container) return;

        // 初始化草稿图片状态，确保使用完整 Data URI 或 URL
        if (!session._draftImages) {
            this._initDraftImages(session);
        }
        const draftImages = session._draftImages || [];

        let imagesHtml = '';
        const iconHtml = window.IconManager ? window.IconManager.render('pencil', 'xl') : '📝';

        // 图片网格
        imagesHtml = `
            <div class="preview-grid" id="draft-image-grid" style="margin-bottom:16px;">
                ${draftImages.map((img, idx) => `
                    <div class="preview-item">
                        <img src="${img.src}" style="width:100%; height:100%; border-radius:12px; border:1px solid var(--color-border); object-fit: cover;">
                        <button class="preview-remove" data-index="${idx}">×</button>
                    </div>
                `).join('')}
                <div class="preview-item upload-zone-mini" id="draft-add-btn" style="display:flex; align-items:center; justify-content:center; border:2px dashed var(--color-border); cursor:pointer; background:var(--color-bg-tertiary);">
                    <img src="css/icons/add.png" style="width:24px; height:24px; opacity:0.5;">
                    <input type="file" id="draft-image-upload" accept="image/*" multiple hidden>
                </div>
            </div>
        `;

        const note = session.sourceUserNote || session.text || '';

        // 错误提示 HTML
        let errorHtml = '';
        if (session.lastError) {
            const err = session.lastError;
            errorHtml = `
                <div class="draft-error-banner" style="margin-bottom: 16px; padding: 12px; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 8px; position: relative;">
                    <div style="display: flex; align-items: flex-start; gap: 10px;">
                        <span style="font-size: 1.2rem;">⚠️</span>
                        <div style="flex: 1;">
                            <div style="font-weight: 650; color: #b91c1c; font-size: 0.9rem;">${err.title}</div>
                            <div style="font-size: 0.85rem; color: #7f1d1d; margin-top: 2px; line-height: 1.4;">${err.message}</div>
                        </div>
                        <button onclick="event.stopPropagation(); Dashboard.currentSession.lastError=null; Dashboard.renderDraftState(Dashboard.currentSession);" 
                                style="background:transparent; border:none; cursor:pointer; font-size:1.2rem; color:#b91c1c; padding:0 4px; line-height:1;">×</button>
                    </div>
                </div>
            `;
        }

        container.innerHTML = `
            <div class="result-card" id="draft-card-container" style="position:relative;">
                <div class="result-card-header">
                    <div class="result-icon-container">
                        ${iconHtml}
                    </div>
                    <div>
                        <div class="result-card-title">待处理记录</div>
                        <div class="result-card-subtitle">草稿 / 分析未完成</div>
                    </div>
                </div>

                <div class="draft-content">
                    ${errorHtml}
                    ${imagesHtml}
                    <div class="note-section">
                        <div class="dishes-title">记录说明</div>
                        <textarea id="draft-note-input" class="input-field" rows="4" style="min-height:100px; resize:vertical;" placeholder="补充描述，或直接粘贴/拖拽图片...">${note}</textarea>
                    </div>
                </div>

                <!-- Drop Overlay -->
                <div id="draft-drop-overlay" style="position:absolute; top:0; left:0; width:100%; height:100%; background:rgba(255,255,255,0.9); z-index:100; border-radius:var(--radius-lg); display:none; flex-direction:column; align-items:center; justify-content:center; border:2px dashed var(--color-accent-primary);">
                    <div style="font-size:3rem; margin-bottom:16px;">📂</div>
                    <div style="font-size:1.2rem; color:var(--color-accent-primary); font-weight:600;">释放以添加图片</div>
                </div>
            </div>
        `;

        this.el.resultTitle.textContent = '记录预览';
        this.updateStatus('draft');

        // Explicitly show footer for draft actions
        if (this.el.resultFooter) {
            this.el.resultFooter.classList.remove('hidden');
            this.updateButtonStates(session);
        }


        // Bind Events (Drag & Drop, Paste, Remove, Add)
        this._bindDraftEvents(session);

        // Chat Input Sync
        if (this.el.chatInput) this.el.chatInput.value = note;
    },

    _initDraftImages(session) {
        let images = [];
        if (session.imageUrls && session.imageUrls.length > 0) {
            images = session.imageUrls.map(url => ({ src: url, type: 'url', base64: null }));
        } else if (session.images && session.images.length > 0) {
            images = session.images.map(img => ({
                src: img.preview || `data:image/jpeg;base64,${img.base64}`,
                type: 'base64',
                base64: img.base64
            }));
        } else if (session.sourceImagesB64 && session.sourceImagesB64.length > 0) {
            images = session.sourceImagesB64.map(b64 => ({
                src: `data:image/jpeg;base64,${b64}`,
                type: 'base64',
                base64: b64
            }));
        }
        session._draftImages = images;
    },

    _bindDraftEvents(session) {
        const card = document.getElementById('draft-card-container');
        const overlay = document.getElementById('draft-drop-overlay');
        const uploadInput = document.getElementById('draft-image-upload');
        const addBtn = document.getElementById('draft-add-btn');

        if (!card) return;

        // 1. Remove Buttons (Event Delegation)
        card.addEventListener('click', (e) => {
            if (e.target.classList.contains('preview-remove')) {
                const idx = parseInt(e.target.dataset.index);
                this.removeDraftImage(idx);
            }
        });

        // 2. Add Button
        if (addBtn && uploadInput) {
            addBtn.addEventListener('click', () => uploadInput.click());
            uploadInput.addEventListener('change', (e) => this._addDraftImages(e.target.files));
        }

        // 3. Drag & Drop
        let dragCounter = 0;
        card.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dragCounter++;
            if (overlay) overlay.style.display = 'flex';
        });

        card.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dragCounter--;
            if (dragCounter === 0 && overlay) overlay.style.display = 'none';
        });

        card.addEventListener('dragover', (e) => e.preventDefault());

        card.addEventListener('drop', (e) => {
            e.preventDefault();
            dragCounter = 0;
            if (overlay) overlay.style.display = 'none';
            if (e.dataTransfer && e.dataTransfer.files.length > 0) {
                this._addDraftImages(e.dataTransfer.files);
            }
        });

        // 4. Paste
        card.addEventListener('paste', (e) => {
            const items = (e.clipboardData || e.originalEvent.clipboardData).items;
            const files = [];
            for (let item of items) {
                if (item.kind === 'file' && item.type.startsWith('image/')) {
                    const file = item.getAsFile();
                    if (file) files.push(file);
                }
            }
            if (files.length > 0) {
                e.preventDefault(); // Prevent pasting image into textarea directly
                this._addDraftImages(files);
            }
        });

        // 5. Note Sync logic
        const noteInput = document.getElementById('draft-note-input');
        if (noteInput) {
            noteInput.addEventListener('input', (e) => {
                session.sourceUserNote = e.target.value;
                if (this.el.chatInput) this.el.chatInput.value = e.target.value;
            });
        }
    },

    async _addDraftImages(fileList) {
        if (!fileList || fileList.length === 0) return;
        const session = this.currentSession;
        if (!session) return;
        // Ensure initialized
        if (!session._draftImages) this._initDraftImages(session);

        for (const file of fileList) {
            try {
                // ImageUtils.fileToBase64 returns pure base64 string
                const b64 = await ImageUtils.fileToBase64(file);
                session._draftImages.push({
                    src: `data:${file.type || 'image/jpeg'};base64,${b64}`, // Construct full Data URI for preview
                    type: 'base64',
                    base64: b64
                });
            } catch (e) {
                console.error("Failed to read file", e);
            }
        }
        this.renderDraftState(session);
    },

    removeDraftImage(index) {
        if (!this.currentSession || !this.currentSession._draftImages) return;
        this.currentSession._draftImages.splice(index, 1);
        this.renderDraftState(this.currentSession);
    },

    async retryDraft(sessionId) {
        const session = this.currentSession;
        if (!session || session.id !== sessionId) return;

        // 1. Update Note
        const noteInput = document.getElementById('draft-note-input');
        if (noteInput && noteInput.value !== undefined) {
            session.sourceUserNote = noteInput.value.trim();
        }
        session.text = session.sourceUserNote;
        if (this.el.chatInput) this.el.chatInput.value = session.text;

        // 2. Consolidate Images (Mixed URL/Base64 -> Unified Base64 session.images)
        this.showLoading(); // Show loading earlier since fetching might take time

        try {
            if (session._draftImages && session._draftImages.length > 0) {
                const unifiedImages = [];
                for (const img of session._draftImages) {
                    if (img.type === 'base64' && img.base64) {
                        unifiedImages.push({ base64: img.base64, preview: img.src });
                    } else if (img.type === 'url') {
                        // Fetch remote URL to base64
                        const b64s = await this._loadImagesFromUris([img.src]);
                        if (b64s && b64s.length > 0) {
                            unifiedImages.push({ base64: b64s[0], preview: img.src });
                        }
                    }
                }
                session.images = unifiedImages;
                session.sourceImagesB64 = unifiedImages.map(i => i.base64);
                // Clear legacy fields to avoid confusion during executeAnalysis
                session.imageUrls = [];
            } else {
                // If all images removed
                session.images = [];
                session.sourceImagesB64 = [];
                session.imageUrls = [];
            }

            // 3. Execute
            const effectiveNote = session.sourceUserNote || session.text || '';
            await this.executeAnalysis(session, effectiveNote);

        } catch (e) {
            console.error("Retry preparation failed", e);
            const errorInfo = window.ErrorHandlerModule
                ? window.ErrorHandlerModule.getFriendlyError(e)
                : { title: '分析重试失败', message: e.message || '图片处理失败', level: 'error', action: 'retry' };

            session.lastError = errorInfo;
            this.renderDraftState(session);
        }
    },

};

window.AnalysisModule = AnalysisModule;
