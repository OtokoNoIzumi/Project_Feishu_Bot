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
        session._lastUserNote = userNote; // 保存以备重试
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
                this.showError(result.error || '分析失败');
                return;
            }

            // 添加新版本
            const version = {
                number: session.versions.length + 1,
                createdAt: new Date(),
                userNote: userNote,
                rawResult: result.result,
                parsedData: this.parseResult(result.result, session.mode),
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
                    this.addMessage('卡片尚未建立，无法更新分析结果。', 'assistant');
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

            this.addMessage('分析完成！', 'assistant');

            // 自动触发 advice 请求（仅饮食模式）
            if (session.mode === 'diet' && this.currentDishes?.length > 0) {
                this.autoFetchAdvice();
            }

        } catch (error) {
            this.updateStatus('');  // 停止加载状态
            console.error("Execute analysis error:", error);

            // 从 APIError 获取结构化数据
            const errorCode = error.data?.detail?.code;
            const metadata = error.data?.detail?.metadata || {};
            const errorMsg = error.message || '未知错误';

            // 本地化提示
            let userTip = `分析失败: ${errorMsg}`;
            let actions = [];

            if (errorCode === 'DAILY_LIMIT_REACHED') {
                const limit = metadata.limit || 5;
                userTip = `每日分析次数已耗尽 (${limit}/${limit})。请升级会员继续使用。`;
                actions.push({
                    text: '🔑 去输入激活码',
                    class: 'btn-primary',
                    onClick: () => Dashboard.switchView('profile')
                });
            } else if (errorCode === 'SUBSCRIPTION_EXPIRED') {
                userTip = `订阅已过期，请续费。`;
                actions.push({
                    text: '🔑 去输入激活码',
                    class: 'btn-primary',
                    onClick: () => Dashboard.switchView('profile')
                });
            } else {
                // 普通错误，提供重试
                actions.push({
                    text: '🔄 重试',
                    class: 'btn-ghost',
                    onClick: () => this.retryLastAnalysis()
                });
            }

            const messagesContainer = document.getElementById('chat-messages');

            // Check for duplicate message content against the LAST ASSISTANT message
            if (messagesContainer) {
                const assistantMsgs = messagesContainer.querySelectorAll('.message.assistant');
                const lastMsg = assistantMsgs.length > 0 ? assistantMsgs[assistantMsgs.length - 1] : null;

                const lastContentRaw = lastMsg?.querySelector('.message-text')?.innerText || '';
                const cleanLast = lastContentRaw.replace(/\s+/g, '');
                const cleanNew = userTip.replace(/<br\s*\/?>/gi, '').replace(/\s+/g, '');

                if (lastMsg && cleanLast === cleanNew) {
                    if (window.ToastUtils) {
                        const shortMsg = userTip.replace(/<br\s*\/?>/gi, '').split(/[\n。]/)[0] + '。';
                        ToastUtils.show(shortMsg, 'info');
                        return;
                    }
                }
            }

            // Hide previous "Go to Profile" buttons to avoid clutter
            if (errorCode === 'DAILY_LIMIT_REACHED' || errorCode === 'SUBSCRIPTION_EXPIRED') {
                const buttons = messagesContainer?.querySelectorAll('button');
                buttons?.forEach(btn => {
                    if (btn.innerText.includes('去输入激活码')) {
                        btn.style.display = 'none';
                    }
                });
            }

            // 发送错误消息卡片
            this.addMessage(userTip, 'assistant', { actions });

            // 仅在非引导类错误时弹窗，避免打断
            if (!errorCode || !['DAILY_LIMIT_REACHED', 'SUBSCRIPTION_EXPIRED'].includes(errorCode)) {
                if (window.ToastUtils) ToastUtils.show(errorMsg, 'error');
            }
        }
    },

    async updateAdvice() {
        if (!this.currentSession) return;

        const session = this.currentSession;
        const currentVersion = session.versions[session.currentVersion - 1];
        if (!currentVersion) return;

        // 只有饮食模式有建议
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

            // 收集当前编辑的数据作为 facts
            const facts = this.collectEditedData();
            const userNote = document.getElementById('additional-note')?.value.trim() || '';

            const response = await API.getDietAdvice(facts, userNote);

            if (loadingMsg) loadingMsg.remove();

            // 后端返回 {success, result: {advice_text}} 结构
            if (response.success && response.result?.advice_text) {
                currentVersion.advice = response.result.advice_text;
                currentVersion.adviceError = null; // 清除错误
                this.renderAdvice(response.result.advice_text);
                this.addMessage('建议已更新', 'assistant');

                // 持久化更新
                if (session.persistentCardId) {
                    const cardData = this._buildCardData(session);
                    if (cardData) API.updateCard(session.persistentCardId, cardData).catch(console.warn);
                }
            } else if (response.error) {
                currentVersion.adviceError = response.error; // 记录错误
                this.addMessage(`建议生成失败: ${response.error}`, 'assistant');
            }


        } catch (error) {
            if (loadingMsg) loadingMsg.remove();

            currentVersion.adviceError = error.message;

            // 从 APIError 获取结构化数据
            const errorCode = error.data?.detail?.code;
            const metadata = error.data?.detail?.metadata || {};

            // 本地化提示
            let userTip = `建议更新失败: ${error.message}`;
            let actions = [];

            if (errorCode === 'DAILY_LIMIT_REACHED') {
                const limit = metadata.limit || 5;
                userTip = `每日建议生成次数已耗尽 (${limit}/${limit})。请升级会员继续使用。`;
                actions.push({
                    text: '🔑 去输入激活码',
                    class: 'btn-primary',
                    onClick: () => Dashboard.switchView('profile')
                });
            } else if (errorCode === 'SUBSCRIPTION_EXPIRED') {
                userTip = `订阅已过期，请续费。`;
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



            const messagesContainer = document.getElementById('chat-messages');

            // Check for duplicate message content against the LAST ASSISTANT message
            if (messagesContainer) {
                const assistantMsgs = messagesContainer.querySelectorAll('.message.assistant');
                const lastMsg = assistantMsgs.length > 0 ? assistantMsgs[assistantMsgs.length - 1] : null;

                const lastContentRaw = lastMsg?.querySelector('.message-text')?.innerText || '';
                const cleanLast = lastContentRaw.replace(/\s+/g, '');
                const cleanNew = userTip.replace(/<br\s*\/?>/gi, '').replace(/\s+/g, '');

                if (lastMsg && cleanLast === cleanNew) {
                    if (window.ToastUtils) {
                        const shortMsg = userTip.replace(/<br\s*\/?>/gi, '').split(/[\n。]/)[0] + '。';
                        ToastUtils.show(shortMsg, 'info');
                        return;
                    }
                }
            }

            // Hide previous "Go to Profile" buttons
            if (errorCode === 'DAILY_LIMIT_REACHED' || errorCode === 'SUBSCRIPTION_EXPIRED') {
                const buttons = messagesContainer?.querySelectorAll('button');
                buttons?.forEach(btn => {
                    if (btn.innerText.includes('去输入激活码')) {
                        btn.style.display = 'none';
                    }
                });
            }

            this.addMessage(userTip, 'assistant', { actions });

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
            this._setAdviceLoading(currentVersion, true);
            // 收集当前数据作为 facts
            // 注意：从 Dashboard 调用
            const facts = this.collectEditedData();
            const userNote = document.getElementById('additional-note')?.value.trim() || '';

            const response = await API.getDietAdvice(facts, userNote);

            // 后端返回 {success, result: {advice_text}} 结构
            if (response.success && response.result?.advice_text) {
                currentVersion.advice = response.result.advice_text;
                currentVersion.adviceError = null; // 清除错误
                this._setAdviceLoading(currentVersion, false);
                this.renderAdvice(response.result.advice_text);

                // 持久化更新
                if (session.persistentCardId) {
                    const cardData = this._buildCardData(session);
                    if (cardData) API.updateCard(session.persistentCardId, cardData).catch(console.warn);
                }

            } else if (response.error) {
                currentVersion.adviceError = response.error; // 记录错误
                this._setAdviceLoading(currentVersion, false);
                this.renderAdviceError(response.error);
            } else {
                const msg = '未获取到建议内容';
                currentVersion.adviceError = msg; // 记录错误
                this._setAdviceLoading(currentVersion, false);
                this.renderAdviceError(msg);
            }
        } catch (error) {
            currentVersion.adviceError = error.message; // 记录错误
            this._setAdviceLoading(currentVersion, false);
            this.renderAdviceError(error.message);
        }
    },

    // ========== Helpers ==========

    _buildCardData(session) {
        if (!session.persistentCardId) return null;

        // 找到最新版本的 parsedData 用于生成 Title
        const latestVersion = session.versions[session.currentVersion - 1];

        return {
            id: session.persistentCardId,
            dialogue_id: session.dialogueId,
            mode: session.mode,
            title: this._generateCardTitle(latestVersion?.parsedData),
            user_id: 'placeholder', // 后端会自动覆盖/忽略(若设为Optional)
            source_user_note: session.sourceUserNote || session.text || '',
            image_uris: (session.imageUrls || []).filter(url => url && !url.startsWith('blob:') && !url.startsWith('data:')),
            image_hashes: session.imageHashes || [],
            versions: session.versions.map(v => ({
                created_at: v.createdAt.toISOString(),
                user_note: v.userNote,
                raw_result: v.rawResult,
                // 这里关键：要把 advice 存进去！
                advice: v.advice,
                adviceError: v.adviceError
            })),
            current_version: session.currentVersion,
            status: 'draft',
            created_at: session.createdAt.toISOString(),
            updated_at: new Date().toISOString()
        };
    },

    _generateCardTitle(parsedData) {
        if (!parsedData) return '未命名卡片';

        if (parsedData.type === 'diet') {
            const time = parsedData.summary.dietTime ?
                (parsedData.summary.dietTime === 'snack' ? '加餐' :
                    parsedData.summary.dietTime === 'breakfast' ? '早餐' :
                        parsedData.summary.dietTime === 'lunch' ? '午餐' :
                            parsedData.summary.dietTime === 'dinner' ? '晚餐' : '饮食记录')
                : '饮食记录';
            return `${time}分析`;
        } else {
            return 'Keep记录';
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
            const unit = this.getEnergyUnit();
            const energy = parsedData.summary.totalEnergy || 0;
            const val = unit === 'kcal' ? Math.round(energy) : Math.round(this.kcalToKJ(energy));
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

        if (version.adviceLoading) {
            statusEl.className = 'advice-status loading';
            contentEl.innerHTML = '<div class="advice-loading"><span class="loading-spinner"></span>正在生成点评...</div>';
            return;
        }

        statusEl.className = 'advice-status';
        if (version.advice) {
            contentEl.innerHTML = `<div class="advice-text">${this.simpleMarkdownToHtml(version.advice)}</div>`;
        } else if (version.adviceError) {
            contentEl.innerHTML = `<div class="advice-error">⚠️ 建议获取失败：${version.adviceError}</div>`;
            statusEl.classList.add('error');
        } else {
            contentEl.innerHTML = '<div class="advice-empty">暂无建议</div>';
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

};

window.AnalysisModule = AnalysisModule;
