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

        // 执行分析（使用原始附件）
        await this.executeAnalysis(session, fullNote);
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
            const imagesB64 = session.images.map(img => img.base64);
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
                userNote: userNote,  // 保存本次分析用的文字说明
                rawResult: result.result,
                parsedData: this.parseResult(result.result, session.mode),
                advice: null,  // 待调用 advice API 获取
                adviceError: null, // 新增：记录建议获取失败的原因
            };
            session.versions.push(version);
            session.currentVersion = version.number;

            // 更新消息卡片标题
            this.updateSessionCard(session);

            // 渲染结果
            this.renderResult(session);
            if (this.isMobile()) this.setResultPanelOpen(true);

            this.addMessage('分析完成！', 'assistant');

            // 自动触发 advice 请求（仅饮食模式）
            // 注意：this.currentDishes 是由 renderResult -> renderDietResult 填充的
            if (session.mode === 'diet' && this.currentDishes?.length > 0) {
                this.autoFetchAdvice();
            }


        } catch (error) {
            this.updateStatus('');  // 停止加载状态
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
            // 收集当前数据作为 facts
            // 注意：从 Dashboard 调用
            const facts = this.collectEditedData();
            const userNote = document.getElementById('additional-note')?.value.trim() || '';

            const response = await API.getDietAdvice(facts, userNote);

            // 后端返回 {success, result: {advice_text}} 结构
            if (response.success && response.result?.advice_text) {
                currentVersion.advice = response.result.advice_text;
                currentVersion.adviceError = null; // 清除错误
                this.renderAdvice(response.result.advice_text);
            } else if (response.error) {
                currentVersion.adviceError = response.error; // 记录错误
                this.renderAdviceError(response.error);
            } else {
                const msg = '未获取到建议内容';
                currentVersion.adviceError = msg; // 记录错误
                this.renderAdviceError(msg);
            }
        } catch (error) {
            currentVersion.adviceError = error.message; // 记录错误
            this.renderAdviceError(error.message);
        }
    },

};

window.AnalysisModule = AnalysisModule;
