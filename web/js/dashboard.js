/**
 * Dashboard 主逻辑
 *
 * 架构设计：
 * - 每个分析作为一个 Session，支持多版本(v1, v2...)
 * - Session 包含：原始附件、文字说明、多个版本的分析结果
 * - 右侧展示当前选中 Session 的最新版本，可切换查看历史版本
 */

const Dashboard = {
  // 模式：diet / keep
  mode: 'diet',

  // 右侧（移动端抽屉）展示内容：analysis / profile
  view: 'analysis',

  // 待上传的图片
  pendingImages: [],

  // 分析会话列表 (每个会话可以有多个版本)
  sessions: [],

  // 当前选中的 session
  currentSession: null,

  // 当前关联的后端 Dialogue ID (Phase 2)
  currentDialogueId: null,

  // 移动端：确认面板（结果面板）是否打开
  isResultPanelOpen: false,

  // Profile（前端先行：本地存储 + 占位请求）
  profile: null,

  // Diet：AI 菜式的 ingredients 折叠状态（默认折叠）
  dietIngredientsCollapsed: {},

  // DOM 元素缓存
  el: {},

  async init() {
    const getLogTime = () => {
      const now = new Date();
      const pad = (n) => n.toString().padStart(2, '0');
      return `[AI_second_me ${pad(now.getMonth() + 1)}/${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}]`;
    };

    console.log(`${getLogTime()} [Dashboard] init started`);

    this.cacheElements();
    this.bindEvents();

    // 保存原始 footer HTML（用于从 Profile 切回时恢复）
    this._originalFooterHtml = this.el.resultFooter?.innerHTML || '';

    if (window.FooterModule) {
      window.FooterModule.init();
    }

    // 初始化 UI 状态 (Empty State with Tips)
    if (window.GlobalSearchManager) window.GlobalSearchManager.init();
    this.clearResult();

    // 初始化 Auth（非阻塞）

    console.log(`${getLogTime()} calling Auth.init()`);
    Auth.init();

    // 注册 Auth 就绪后的回调
    Auth.onInit(() => {
      console.log(`${getLogTime()} Auth.onInit callback triggered`);

      // [Demo Mode]
      if (Auth.isDemoMode()) {
        console.log(`${getLogTime()} Dashboard initialized in DEMO MODE`);
        // Note: Sidebar init moved to runDemoSequence to handle progressive loading

        // Run Sequence
        this.runDemoSequence();

        // Update Profile View
        if (this.view === 'profile' && this.el.resultContent.querySelector('.auth-loading-state')) {
          this.renderProfileView();
        }
        return;
      }

      if (!Auth.isSignedIn()) {
        console.log(`${getLogTime()} User not signed in, redirecting...`);
        window.location.href = 'index.html';
        return;
      }
      Auth.mountUserButton('#user-button');
      Auth.mountUserButton('#user-button-mobile');
      // Show sidebar footer only for logged-in users (matches result-footer height)
      const sidebarFooter = document.querySelector('.history-footer');
      if (sidebarFooter) sidebarFooter.classList.add('visible');

      console.log(`${getLogTime()} Loading history...`);
      // Phase 2: Use SidebarModule instead of old StorageModule
      if (window.SidebarModule) {
        SidebarModule.init();
        if (window.QuickInputModule && window.QuickInputModule.init) {
          window.QuickInputModule.init();
        }
        // 加载 dish library 用于名称自动补全
        if (window.EditableNameModule && window.EditableNameModule.init) {
          window.EditableNameModule.init();
        }
      } else {
        this.loadHistory();
      }

      // Pre-load Profile to get limits info
      if (window.ProfileModule && window.ChatUIModule) {
        ProfileModule.loadFromServer().then(() => {
          if (ProfileModule.limitsInfo) {
            ChatUIModule.updateLimitStatus(ProfileModule.limitsInfo);
          }
        });
      }

      // 如果当前停留在 Profile 视图且显示的是加载态，则刷新
      if (this.view === 'profile' && this.el.resultContent.querySelector('.auth-loading-state')) {
        console.log(`${getLogTime()} Updating Profile view from loading state`);
        this.renderProfileView();
      }
    });

    console.log(`${getLogTime()} Initialized (Auth pending)`);

    window.Dashboard = this;
  },





  // ========== 图片处理 ==========

  // 委托给 ImageUtils
  fileToBase64: ImageUtils.fileToBase64,







  // ========== 分析流程 ==========

  async startNewAnalysis() {
    if (Auth.isDemoMode()) {
      if (this.checkDemoLimit && this.checkDemoLimit()) return;
    }
    const text = this.el.chatInput?.value.trim() || '';
    if (!text && this.pendingImages.length === 0) return;

    // Quick Input Interception
    if (!this.pendingImages.length && window.QuickInputModule && window.QuickInputModule.handleQuickInput) {
      const handled = await window.QuickInputModule.handleQuickInput(text);
      if (handled) {
        this.el.chatInput.value = '';
        return;
      }
    }

    // Profile 模式：调用 ProfileModule.analyze
    if (this.view === 'profile') {
      await this.startProfileAnalysis(text);
      return;
    }

    // Advice 模式：调用 AnalysisModule.startAdviceChat
    if (this.mode === 'advice') {
      await this.startAdviceChat(text);
      return;
    }

    // 1. 确保有后端 Dialogue (Phase 2)
    if (!this.currentDialogueId) {
      try {
        // 自动标题：文本前15字 或 图片提示
        const title = text.slice(0, 15) || (this.pendingImages.length ? `${this.pendingImages.length}张图片` : '新对话');
        const dialogue = await API.createDialogue(title);
        this.currentDialogueId = dialogue.id;

        // 刷新左侧栏
        if (window.SidebarModule) window.SidebarModule.loadDialogues();
      } catch (e) {
        console.error("Failed to create dialogue", e);
      }
    }

    // 创建新 Session (前端展示用)
    const session = this.createSession(text, [...this.pendingImages]);
    session.dialogueId = this.currentDialogueId; // 关联 ID
    this.currentSession = session;
    if (!session.persistentCardId) {
      session.persistentCardId = window.DateFormatter ? window.DateFormatter.generateId('card') : `card-${Date.now()}`;
    }

    // 2. 持久化用户消息 (异步)
    if (this.currentDialogueId) {
      const msgId = Date.now().toString();
      const msgPayload = {
        id: msgId,
        role: 'user',
        content: text || (this.pendingImages.length > 0 ? '[图片]' : ''),
        timestamp: new Date().toISOString(),
        attachments: [],
        linked_card_id: session.persistentCardId
      };
      session.lastUserMessage = msgPayload; // 记录以便后续更新

      API.appendMessage(this.currentDialogueId, msgPayload).catch(e => console.warn('Msg save failed', e));
    }

    // 3. Raw Input 阶段先创建 Card（严格解耦）
    if (this.currentDialogueId) {
      try {
        const nowIso = new Date().toISOString();
        const cardData = {
          id: session.persistentCardId,
          dialogue_id: session.dialogueId,
          mode: session.mode,
          user_id: 'placeholder',
          source_user_note: text || '',
          image_uris: [],
          image_hashes: [],
          versions: [],
          current_version: 1,
          status: 'analyzing',
          created_at: nowIso,
          updated_at: nowIso
        };
        await API.createCard(cardData);
        session.cardCreated = true;
      } catch (e) {
        console.error('Create card failed:', e);
        this.addMessage(`创建分析结果失败: ${e.message}`, 'assistant');
        return;
      }
    }

    // 添加消息卡片到 UI
    const initialTitle = text ? '' : (this.pendingImages.length > 0 ? `${this.pendingImages.length}张图片` : '');
    this.addMessage(text || '', 'user', {
      sessionId: session.id,
      images: session.imageUrls,
      title: initialTitle,
    });

    // 清空输入
    this.el.chatInput.value = '';
    this.pendingImages = [];
    this.renderPreviews();
    this.updateSendButton();

    // 执行分析
    await this.executeAnalysis(session, text);

    // 3. 持久化逻辑已移至 executeAnalysis 中 (Draft First Strategy)
    // if (this.currentDialogueId) { ... }
  },

  /**
   * 快捷输入模式：直接创建一个空的草稿会话
   */
  async startQuickInput() {
    // Demo 模式下阻断快捷记录功能
    if (this.checkDemoLimit && this.checkDemoLimit()) return;

    // 1. 确保有后端 Dialogue
    if (!this.currentDialogueId) {
      try {
        const dialogue = await API.createDialogue("快捷记录");
        this.currentDialogueId = dialogue.id;
        if (window.SidebarModule) window.SidebarModule.loadDialogues();
      } catch (e) {
        console.error("Failed to create dialogue", e);
        return;
      }
    }

    // 2. 调用快捷输入模块
    if (window.QuickInputModule) {
      window.QuickInputModule.start();
    } else {
      console.error('QuickInputModule not loaded');
      this.addMessage('模块加载失败，请刷新重试', 'assistant');
    }
  },

  /**
   * Profile 模式下的分析
   */
  async startProfileAnalysis(userNote) {
    // Capture images before clearing
    const images = [...this.pendingImages];
    const imageUrls = images.map(img => img.preview);

    // 添加用户消息
    this.addMessage(userNote || (images.length > 0 ? '[图片]' : ''), 'user', { images: imageUrls });

    // 清空输入
    this.el.chatInput.value = '';
    this.pendingImages = [];
    this.renderPreviews();
    this.updateSendButton();

    // 显示加载状态
    const loadingMsg = this.addMessage('正在分析...', 'assistant', { isLoading: true });

    // 从当前 Profile 读取预期达成时间（优先从 DOM 读取最新值）
    const monthsInput = document.getElementById('estimated_months');
    let targetMonths = monthsInput ? parseInt(monthsInput.value) : null;
    if (!targetMonths || isNaN(targetMonths)) {
      const currentProfile = ProfileModule.getCurrentProfile();
      targetMonths = currentProfile.estimated_months || null;
    }

    // 调用 Profile 分析（传入 targetMonths 和 images）
    const result = await ProfileModule.analyze(userNote, targetMonths, images);

    // 移除加载消息
    if (loadingMsg) loadingMsg.remove();

    if (result.success) {
      // 显示分析建议（使用 marked 解析 markdown）
      let adviceHtml = result.advice || '分析完成';
      if (typeof marked !== 'undefined' && marked.parse) {
        adviceHtml = marked.parse(adviceHtml);
      } else {
        adviceHtml = TextUtils.simpleMarkdownToHtml(adviceHtml);
      }
      this.addMessage(adviceHtml, 'assistant', { isHtml: true });

      // 刷新 Profile 视图（显示暂存值）
      this.renderProfileView();
    } else {
      // 结构化错误处理
      let userTip = `分析失败: ${result.error}`;
      let options = {};

      if (result.errorCode === 'DAILY_LIMIT_REACHED') {
        const limit = result.metadata?.limit || 5;
        userTip = `每日档案建议次数已耗尽 (${limit}/${limit})。<br>请在左侧输入激活码升级会员继续使用，或等待次日重置。`;
        options.isHtml = true;
      } else if (result.errorCode === 'SUBSCRIPTION_EXPIRED') {
        userTip = `订阅已过期，请在下方输入激活码续费。`;
      }

      // Check for duplicate content against the LAST ASSISTANT message
      const assistantMsgs = this.el.chatMessages.querySelectorAll('.message.assistant');
      const lastMsg = assistantMsgs.length > 0 ? assistantMsgs[assistantMsgs.length - 1] : null;

      const lastContentRaw = lastMsg?.querySelector('.message-text')?.innerText || '';
      const cleanLast = lastContentRaw.replace(/\s+/g, '');
      const cleanNew = userTip.replace(/<br\s*\/?>/gi, '').replace(/\s+/g, '');

      if (lastMsg && cleanLast === cleanNew) {
        if (window.ToastUtils) {
          // Normalize new message content for comparison (handle HTML breaks)
          const normalizedTip = userTip.replace(/<br\s*\/?>/gi, '\n').trim();
          // Toast a simplified version (first sentence)
          const shortMsg = normalizedTip.split('\n')[0].replace(/\(\d+\/\d+\)/, '');
          ToastUtils.show(shortMsg, 'info');
          return;
        }
      }

      this.addMessage(userTip, 'assistant', options);
    }
  },

  // 委托给 AnalysisModule
  reAnalyze: AnalysisModule.reAnalyze,
  retryLastAnalysis: AnalysisModule.retryLastAnalysis,
  executeAnalysis: AnalysisModule.executeAnalysis,
  startAdviceChat: AnalysisModule.startAdviceChat, // Added delegation for startAdviceChat
  _generateCardTitle: AnalysisModule._generateCardTitle,
  _generateCardSummary: AnalysisModule._generateCardSummary,
  _generateMessageTitle: AnalysisModule._generateMessageTitle,
  _setAdviceLoading: AnalysisModule._setAdviceLoading,
  _buildCardData: AnalysisModule._buildCardData,

  // 委托给 DemoModule
  checkDemoLimit: function () { return window.DemoModule && window.DemoModule.checkDemoLimit ? window.DemoModule.checkDemoLimit() : false; },

  renderResult(session) {
    if (!session || session.versions.length === 0) {
      this.clearResult();
      return;
    }

    const version = session.versions[session.currentVersion - 1];
    const data = version.parsedData;

    if (data.type === 'diet') {
      this.renderDietResult(session, version);
    } else {
      this.renderKeepResult(session, version);
    }

    this.updateButtonStates(session);
    // Show close button on desktop when result is rendered
    this.showSessionControls();

    // Mobile: Ensure panel is open (e.g. for Quick Input which bypasses selectSession)
    if (this.isMobile && this.isMobile() && this.setResultPanelOpen) {
      this.setResultPanelOpen(true);
    }
  },



  // 委托给 DietRenderModule
  renderDietResult: DietRenderModule.renderDietResult,

  // 委托给 KeepRenderModule
  renderKeepResult: KeepRenderModule.renderKeepResult,

  // 委托给 DietRenderModule
  renderDietDishes: DietRenderModule.renderDietDishes,
  renderUserDishesTable: DietRenderModule.renderUserDishesTable,
  renderDietDishBlockDesktop: DietRenderModule.renderDietDishBlockDesktop,
  renderDietDishesMobile: DietRenderModule.renderDietDishesMobile,
  formatEnergyFromMacros: DietRenderModule.formatEnergyFromMacros,

  // 委托给 DietEditModule
  toggleDishEnabled: DietEditModule.toggleDishEnabled,
  updateDishName: DietEditModule.updateDishName.bind(DietEditModule),
  updateMealName: DietEditModule.updateMealName.bind(DietEditModule),

  renderAdvice(adviceText, isLoading = false) {
    const contentEl = document.getElementById('advice-content');
    const statusEl = document.getElementById('advice-status');
    const session = this.currentSession;
    const version = session?.versions?.[session.currentVersion - 1];

    if (version) {
      version.advice = adviceText;
      version.adviceLoading = isLoading;
      version.adviceError = null;
    }

    if (contentEl) {
      let html = '';
      if (typeof this.generateAdviceHtml === 'function' && version) {
        html = this.generateAdviceHtml(version);
      } else {
        const md = this.simpleMarkdownToHtml ? this.simpleMarkdownToHtml(adviceText) : adviceText;
        html = `<div class="advice-text">${md}</div>`;
      }
      contentEl.innerHTML = html;
    }
    if (statusEl) {
      statusEl.className = 'advice-status';
      statusEl.textContent = '';
    }
    // 恢复折叠状态
    this.restoreAdviceState();
  },

  // 营养点评折叠切换
  toggleAdviceSection(event) {
    if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
    const section = document.getElementById('advice-section');
    if (!section) return;

    section.classList.toggle('collapsed');
  },

  // 恢复营养点评折叠状态
  restoreAdviceState() {
    // 需求：默认展开；仅用户手动点击时收起，不做持久化记忆
    const section = document.getElementById('advice-section');
    if (section) section.classList.remove('collapsed');
  },

  // 营养进度折叠切换（右上角按钮）
  toggleNutritionSection(event) {
    if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
    const section = document.getElementById('nutrition-section');
    if (!section) return;

    section.classList.toggle('collapsed');
    const isCollapsed = section.classList.contains('collapsed');
    sessionStorage.setItem('dk_nutrition_collapsed', isCollapsed ? '1' : '0');

    // 展开后 ECharts 需要 resize
    if (!isCollapsed && typeof NutritionChartModule !== 'undefined' && NutritionChartModule.chartInstance) {
      setTimeout(() => {
        try {
          NutritionChartModule.chartInstance.resize();
        } catch (e) {
          // ignore
        }
      }, 60);
    }
  },

  // 恢复营养进度折叠状态
  restoreNutritionState() {
    const collapsed = sessionStorage.getItem('dk_nutrition_collapsed') === '1';
    const section = document.getElementById('nutrition-section');
    if (collapsed && section) {
      section.classList.add('collapsed');
    }
  },

  // 简单的 markdown 转 HTML（支持换行、粗体、列表）
  // 委托给 TextUtils
  simpleMarkdownToHtml: TextUtils.simpleMarkdownToHtml,

  renderAdviceError(errorMsg) {
    const contentEl = document.getElementById('advice-content');
    const statusEl = document.getElementById('advice-status');
    const session = this.currentSession;
    const version = session?.versions?.[session.currentVersion - 1];

    if (version) {
      version.adviceError = errorMsg;
      version.adviceLoading = false;
    }

    if (contentEl) {
      // 优先使用 generateAdviceHtml 以包含中间过程和快捷点评
      if (version && typeof this.generateAdviceHtml === 'function') {
        contentEl.innerHTML = this.generateAdviceHtml(version);
      } else {
        contentEl.innerHTML = `<div class="advice-error">⚠️ 定制建议获取失败：${errorMsg}</div>`;
      }
    }
    if (statusEl) {
      statusEl.className = 'advice-status error';
      statusEl.textContent = '';
    }
    // Error时也确保展开，方便用户看到报错
    this.restoreAdviceState();
  },

  // 切换营养标签区域的折叠状态
  // ========== 编辑操作 ==========

  // 委托给 DietEditModule
  toggleLabelsSection: DietEditModule.toggleLabelsSection,
  updateLabel: DietEditModule.updateLabel,
  updateDish: DietEditModule.updateDish,
  updateIngredient: DietEditModule.updateIngredient,
  toggleIngredients: DietEditModule.toggleIngredients,
  toggleProportionalScale: DietEditModule.toggleProportionalScale,

  // 委托给 DietEditModule
  addDish: DietEditModule.addDish,
  removeDish: DietEditModule.removeDish,
  recalculateDietSummary: DietEditModule.recalculateDietSummary,

  // 委托给 DietEditModule
  markModified: DietEditModule.markModified,
  collectEditedData: DietEditModule.collectEditedData,
  getDishTotals: DietEditModule.getDishTotals,
  updateDishDOM: DietEditModule.updateDishDOM,
  updateDishRowDOM: DietEditModule.updateDishRowDOM,

  // 委托给 EnergyUtils
  getMacroEnergyRatio: EnergyUtils.getMacroEnergyRatio,

  // ========== Profile（前端先行） ==========
  // 委托给 ProfileUtils（保持 this.xxx() 调用兼容）
  getDefaultProfile: ProfileUtils.getDefaultProfile,

  loadProfile() {
    this.profile = ProfileUtils.loadFromStorage();
    return this.profile;
  },

  saveProfileLocal(profile) {
    ProfileUtils.saveToStorage(profile);
    this.profile = profile;
  },

  async renderProfileView() {
    const hasChanges = ProfileModule.hasChanges();
    this.el.resultTitle.innerHTML = hasChanges
      ? 'Profile 设置 <span class="unsaved-status">● 更新未保存</span>'
      : 'Profile 设置';
    this.updateStatus('');

    // 如果 Auth 尚未初始化完成，显示加载占位
    if (!Auth.initialized) {
      this.el.resultContent.innerHTML = `
            <div class="empty-state auth-loading-state">
              <div class="loading-spinner"></div>
              <p>正在同步账户信息...</p>
            </div>
        `;
      this.el.resultFooter.classList.add('hidden');
      return;
    }

    // 首次加载时从后端获取数据
    if (!ProfileModule.serverProfile) {
      this.el.resultContent.innerHTML = `
        <div class="empty-state">
          <div class="loading-spinner"></div>
          <p>加载中...</p>
        </div>
      `;
      this.el.resultFooter.classList.add('hidden');
      await ProfileModule.loadFromServer();
    }

    // 使用新的渲染模块（不含操作按钮）

    this.el.resultContent.innerHTML = ProfileRenderModule.renderContent();

    // 更新 Footer 为 Profile 模式
    if (window.FooterModule && window.FooterState) {
      FooterModule.update(FooterState.PROFILE);
    }
  },

  // 委托给 ProfileUtils
  renderTimezoneOptions: ProfileUtils.renderTimezoneOptions,
  renderDietGoalOptions: ProfileUtils.renderDietGoalOptions,

  async saveProfile() {
    const getNum = (id) => parseFloat(document.getElementById(id)?.value) || 0;
    const getStr = (id) => String(document.getElementById(id)?.value || '');

    const currentUnit = getStr('energy-unit') || 'kJ';
    const rawEnergyTarget = getNum('diet-energy-kj');
    const energyTargetKj = currentUnit === 'kcal' ? Math.round(this.kcalToKJ(rawEnergyTarget)) : rawEnergyTarget;

    const profile = {
      timezone: getStr('profile-timezone'),
      diet: {
        energy_unit: currentUnit,
        goal: getStr('diet-goal'),
        daily_energy_kj_target: energyTargetKj,
        protein_g_target: getNum('diet-protein-g'),
        fat_g_target: getNum('diet-fat-g'),
        carbs_g_target: getNum('diet-carbs-g'),
        sodium_mg_target: getNum('diet-sodium-mg'),
        fiber_g_target: getNum('diet-fiber-g'),
      },
      keep: {
        weight_kg_target: getNum('keep-weight-kg'),
        body_fat_pct_target: getNum('keep-bodyfat-pct'),
        dimensions_target: {
          bust: getNum('keep-bust'),
          waist: getNum('keep-waist'),
          hip_circ: getNum('keep-hip-circ'),
        }
      }
    };

    this.saveProfileLocal(profile);
    this.addMessage('✓ Profile 已在本地保存', 'assistant');

    // 占位提交（后端业务尚未实现）
    try {
      await API.post('/profile/save', {
        user_id: Auth.getUserId() || 'anonymous',
        profile
      });
      this.addMessage('✓ Profile 已提交到后端', 'assistant');
    } catch (e) {
      this.addMessage('后端 Profile 接口尚未接入（已本地保存）', 'assistant');
    }
  },

  setEnergyUnit(unit) {
    const u = unit === 'kcal' ? 'kcal' : 'kJ';

    // 【重构】通过 ProfileModule 更新，立即生效（无需保存）
    if (typeof ProfileModule !== 'undefined') {
      ProfileModule.updateField('diet.energy_unit', u);
    }

    // 立即刷新 Profile 视图本身
    if (this.view === 'profile') {
      this.renderProfileView();
    }

    // Phase 2: 如果使用新版侧边栏，直接调用其 render 方法刷新标题
    if (window.SidebarModule) {
      window.SidebarModule.render();
      // 同时更新 dashboard 内部 sessions 的 visual (如果需要)
      // 但其实 SidebarModule 是动态从 card 数据读 title，不需要这里 updateSessionCard 改 DOM
    } else {
      // Legacy: 旧版侧边栏逻辑
      this.sessions.forEach(s => this.updateSessionCard(s));
      this.loadHistory(); // 清空并重置头
      this.sessions.filter(s => s.isSaved).forEach(s => this.addHistoryItem(s));
    }

    // 如果当前正在查看 Analysis 视图且有数据，立即重绘 Dish 列表以更新单位
    if (this.view === 'analysis' && this.currentSession && this.currentSession.versions.length > 0) {
      this.recalculateDietSummary(false);
      this.renderDietDishes();
    }
  },

  // ========== 保存 ==========

  // ========== 保存 ==========

  // 委托给 StorageModule
  saveRecord: StorageModule.saveRecord,
  saveCard() { return this.saveRecord(); }, // Alias for FooterModule compatibility
  determineKeepEventType: StorageModule.determineKeepEventType,

  // ========== 状态管理 ==========



  isDataUnchanged(session) {
    if (!session.savedData) return false;
    const current = this.collectEditedData();
    const savedStr = JSON.stringify(session.savedData);
    const currentStr = JSON.stringify(current);

    if (savedStr !== currentStr) {
      // console.warn('[DataDiff] Data modified. Diff details:');
      // try {
      //   const saved = session.savedData;
      //   // 简单的一层对比，如果有深层差异再看 total_energy 等关键字段
      //   const allKeys = new Set([...Object.keys(saved), ...Object.keys(current)]);
      //   allKeys.forEach(key => {
      //     const v1 = JSON.stringify(saved[key]);
      //     const v2 = JSON.stringify(current[key]);
      //     if (v1 !== v2) {
      //       console.warn(`Field [${key}] changed:\n  Old: ${v1}\n  New: ${v2}`);
      //     }
      //   });
      // } catch (e) { console.error(e); }
      return false;
    }
    return true;
  },

  // ========== 历史 ==========

  // 委托给 StorageModule
  loadHistory: StorageModule.loadHistory,
  addHistoryItem: StorageModule.addHistoryItem, // 恢复这一行委托

  // ========== Global Search Actions ==========

  async createRecordFromProduct(product) {
    console.log('[Dashboard] Delegating createRecordFromProduct to QuickInputModule');
    if (window.QuickInputModule && window.QuickInputModule.executeProduct) {
      await window.QuickInputModule.executeProduct(product);
    } else {
      console.error('QuickInputModule.executeProduct not available');
    }
  },

  async createRecordFromHistory(cardId) {
    console.log('[Dashboard] Delegating createRecordFromHistory to QuickInputModule');
    if (window.QuickInputModule && window.QuickInputModule.executeFavorite) {
      await window.QuickInputModule.executeFavorite(cardId);
    } else {
      console.error('QuickInputModule.executeFavorite not available');
    }
  },
};

// Mixin Modules
Object.assign(Dashboard, AnalysisModule);
Object.assign(Dashboard, ProfileRenderModule);
Object.assign(Dashboard, DietRenderModule);
Object.assign(Dashboard, DietEditModule);
Object.assign(Dashboard, KeepRenderModule);
Object.assign(Dashboard, StorageModule);
Object.assign(Dashboard, DemoModule);
Object.assign(Dashboard, ChatUIModule);
Object.assign(Dashboard, SessionManagerModule);
Object.assign(Dashboard, DashboardUIModule);


document.addEventListener('DOMContentLoaded', () => Dashboard.init());
