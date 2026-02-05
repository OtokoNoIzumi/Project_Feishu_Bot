/**
 * Demo 演示模块
 *
 * 负责处理演示模式的引导、遮罩和限制逻辑
 * 挂载到 Dashboard 实例运行 (Object.assign)
 */
const DemoModule = {
    async runDemoSequence() {
        // [Fix] Demo 模式下隐藏 "餐食" 侧边栏入口
        const mealsNav = document.querySelector('[data-view="meals"]');
        if (mealsNav) mealsNav.style.display = 'none';

        // [Demo] 禁用侧边栏搜索与新增
        const searchInput = document.getElementById('global-search-input');
        if (searchInput) {
            searchInput.value = '';
            searchInput.setAttribute('disabled', 'disabled');
            searchInput.setAttribute('title', '注册登录后\n可在此搜索并快速添加已记录的数据');
            searchInput.style.cursor = 'not-allowed';
            searchInput.style.background = 'rgba(255,255,255,0.4)';
        }
        const searchResults = document.getElementById('global-search-results');
        if (searchResults) {
            searchResults.innerHTML = '';
            searchResults.classList.remove('visible');
            searchResults.classList.add('hidden');
        }
        const newBtn = document.getElementById('new-dialogue-btn');
        if (newBtn) {
            newBtn.setAttribute('disabled', 'disabled');
            newBtn.style.cursor = 'not-allowed';
            newBtn.style.opacity = '0.4';
        }

        // [Fix] 预加载 Profile 数据，确保侧边栏性别图标正确
        if (window.ProfileModule && !ProfileModule.serverProfile) {
            await ProfileModule.loadFromServer();
        }

        const cardId = 'card_20260127_dfe803ab';

        // 1. Initial State: Hide Card 3 via Filter
        window._DEMO_HIDDEN_CARD_ID = cardId;

        // Init Sidebar (Shows only card 1 & 2 because card 3 is filtered in API)
        if (window.SidebarModule) {
            SidebarModule.init();
            // [Fix] 延迟刷新 Sidebar 以确保 Profile 性别数据已就绪
            setTimeout(() => window.SidebarModule.render(), 200);
        }

        // Load early messages
        const fullMessages = DemoScenario.messages || [];
        const targetMsgIndex = fullMessages.findIndex(m => m.content && m.content.includes('吃虾'));
        const initialMessages = targetMsgIndex >= 0 ? fullMessages.slice(0, targetMsgIndex) : fullMessages;

        this.currentDialogueId = DemoScenario.dialogueId;
        await this.loadDialogue(DemoScenario.dialogueId, initialMessages);

        this.renderDemoMask();

        // 2. Start Animation (Wait 1s, then send)
        if (targetMsgIndex >= 0) {
            const userMsg = fullMessages[targetMsgIndex];
            // No typing effect, just wait
            await this.delay(1000);

            const options = {
                title: userMsg.title,
                images: userMsg.attachments // Pass images from message
            };

            // Render User Message with IMAGES (capture element)
            const userMsgEl = SessionModule.renderMessage(this.el.chatMessages, userMsg.content, 'user', options);

            // Simulate Analysis & Update Status
            if (this.el.resultStatus) this.updateStatus('loading');
            // const loadingMsg = this.addMessage('正在分析...', 'assistant', { isLoading: true });

            await this.delay(2000); // Analysis delay

            // loadingMsg.remove();

            // 3. Analysis Done: Reveal Card 3
            window._DEMO_HIDDEN_CARD_ID = null; // Clear filter

            // Upgrade message to clickable card
            if (userMsgEl && userMsg.linked_card_id) {
                userMsgEl.dataset.sessionId = userMsg.linked_card_id;
                userMsgEl.classList.add('session-card');
                userMsgEl.onclick = () => this.loadCard(userMsg.linked_card_id);
            }

            // Refresh Sidebar to show new card (Data layer will now return all cards)
            if (window.SidebarModule) {
                // [Fix] Sync dialogue ID to Sidebar to prevent it from auto-loading messages again
                // causing duplicate rendering (Sidebar thinks no dialogue is active)
                if (this.currentDialogueId) {
                    SidebarModule.currentDialogueId = this.currentDialogueId;
                }
                SidebarModule.render();
                SidebarModule.loadDialogues();
            }

            await this.loadCard(cardId);
            if (this.el.resultStatus) this.el.resultStatus.textContent = ''; // Clear status

            // Simulate Advice Generation Stage (Extended)
            if (this.currentSession) {
                const sess = this.currentSession;
                const v = sess.versions[sess.currentVersion - 1];
                if (v && v.advice) {
                    const finalAdvice = v.advice;
                    // Temporarily hide advice to show loading state
                    v.advice = null;
                    v.adviceLoading = true;
                    this.renderResult(sess);

                    // [Important] Trigger detailed loading state with intermediate data (Process reasoning)
                    if (typeof this._setAdviceLoading === 'function') {
                        this._setAdviceLoading(v, true);
                    }

                    // Wait longer for user to read intermediate info
                    await this.delay(6000);

                    // Reveal Advice
                    v.advice = finalAdvice;
                    v.adviceLoading = false;
                    this.renderResult(sess);
                }
            }
        }
    },

    async typeEffect(text) {
        // Deprecated in new demo flow
    },

    delay(ms) { return new Promise(r => setTimeout(r, ms)); },

    // [New] Render Demo Mask
    renderDemoMask() {
        // 1. Cover Input Area Only
        const inputSection = document.querySelector('.input-area');
        if (inputSection) {
            // Remove existing mask if any
            const existingMask = inputSection.querySelector('.demo-mask');
            if (existingMask) existingMask.remove();

            // Determine text based on view
            const isProfile = this.view === 'profile';
            const title = isProfile ? '🔓 解锁 AI 训练顾问' : '🔓 解锁 AI 营养顾问';
            const subtitle = isProfile ? '和 AI 一起探讨如何设定目标' : '注册后即可自由对话';

            const mask = document.createElement('div');
            mask.className = 'demo-mask';
            // Adjust style for smaller area
            mask.style.position = 'absolute';
            mask.style.borderRadius = '0';
            mask.innerHTML = `
            <div class="demo-mask-content">
                <h3>${title}</h3>
                <p>${subtitle}</p>
                <button class="btn btn-primary" onclick="window.location.href='index.html'">立即免费注册</button>
            </div>
          `;
            // Prevent interactions
            mask.addEventListener('click', (e) => {
                if (e.target.tagName !== 'BUTTON') {
                    window.location.href = 'index.html';
                }
            });

            const computedStyle = window.getComputedStyle(inputSection);
            if (computedStyle.position === 'static') {
                inputSection.style.position = 'relative';
            }
            inputSection.appendChild(mask);
        }
    },


    // [New] Intercept Demo Action
    checkDemoLimit() {
        if (Auth.isDemoMode()) {
            if (window.ToastUtils) {
                ToastUtils.show('注册即可免费体验 3 天完整分析功能！', 'info');
            }
            // setTimeout(() => window.location.href = 'index.html', 1500); // Removed: Allow stay
            return true; // Blocked
        }
        return false;
    }

};

window.DemoModule = DemoModule;
