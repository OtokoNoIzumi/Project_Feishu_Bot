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

    // 初始化 Footer 模块
    if (window.FooterModule) {
      window.FooterModule.init();
    }

    // 初始化 Auth（非阻塞）

    console.log(`${getLogTime()} calling Auth.init()`);
    Auth.init();

    // 注册 Auth 就绪后的回调
    Auth.onInit(() => {
      console.log(`${getLogTime()} Auth.onInit callback triggered`);
      if (!Auth.isSignedIn()) {
        console.log(`${getLogTime()} User not signed in, redirecting...`);
        window.location.href = 'index.html';
        return;
      }
      Auth.mountUserButton('#user-button');

      console.log(`${getLogTime()} Loading history...`);
      // Phase 2: Use SidebarModule instead of old StorageModule
      if (window.SidebarModule) {
        SidebarModule.init();
      } else {
        this.loadHistory();
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

  cacheElements() {
    this.el = {
      chatMessages: document.getElementById('chat-messages'),
      chatInput: document.getElementById('chat-input'),
      sendBtn: document.getElementById('send-btn'),
      uploadBtn: document.getElementById('upload-btn'),
      fileInput: document.getElementById('file-input'),
      inputBox: document.getElementById('input-box'),
      previewContainer: document.getElementById('preview-container'),
      resultTitle: document.getElementById('result-title'),
      resultContent: document.getElementById('result-content'),
      resultFooter: document.getElementById('result-footer'),
      resultStatus: document.getElementById('result-status'),
      saveBtn: document.getElementById('save-btn'),
      reAnalyzeBtn: document.getElementById('re-analyze-btn'),
      updateAdviceBtn: document.getElementById('update-advice-btn'),
      historyList: document.getElementById('history-list'),
      sideMenu: document.getElementById('side-menu'),
      toggleResultBtn: document.getElementById('toggle-result-btn'),
      openProfileBtn: document.getElementById('open-profile-btn'),
      resultCloseBtn: document.getElementById('result-close-btn'),
      resultOverlay: document.getElementById('result-overlay'),
    };
  },

  bindEvents() {
    // 左侧菜单：分析 / Profile
    this.el.sideMenu?.querySelectorAll('.side-menu-item')?.forEach(btn => {
      btn.addEventListener('click', () => this.switchView(btn.dataset.view));
    });

    // 模式切换
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.addEventListener('click', () => this.switchMode(btn.dataset.mode));
    });

    // 移动端：打开/折叠确认面板
    this.el.toggleResultBtn?.addEventListener('click', () => {
      this.setResultPanelOpen(!this.isResultPanelOpen);
    });
    this.el.resultCloseBtn?.addEventListener('click', () => this.setResultPanelOpen(false));
    this.el.resultOverlay?.addEventListener('click', () => this.setResultPanelOpen(false));

    // 移动端快捷入口：Profile
    this.el.openProfileBtn?.addEventListener('click', () => this.switchView('profile'));

    // 上传
    this.el.uploadBtn?.addEventListener('click', () => this.el.fileInput?.click());
    this.el.fileInput?.addEventListener('change', e => this.handleFiles(e.target.files));

    // 拖拽
    this.el.inputBox?.addEventListener('dragover', e => {
      e.preventDefault();
      this.el.inputBox.classList.add('dragover');
    });
    this.el.inputBox?.addEventListener('dragleave', () => {
      this.el.inputBox.classList.remove('dragover');
    });
    this.el.inputBox?.addEventListener('drop', e => {
      e.preventDefault();
      this.el.inputBox.classList.remove('dragover');
      this.handleFiles(e.dataTransfer.files);
    });

    // 输入
    this.el.chatInput?.addEventListener('input', () => this.updateSendButton());
    this.el.chatInput?.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.startNewAnalysis();
      }
    });

    // 发送（新建分析）
    this.el.sendBtn?.addEventListener('click', () => this.startNewAnalysis());

    // NOTE: reAnalyzeBtn, updateAdviceBtn, saveBtn 的事件由 FooterModule 统一管理


    // 初始化 Profile
    this.profile = this.loadProfile();
  },

  switchMode(mode) {
    this.mode = mode;
    // this.currentDialogueId = null; // Do NOT clear dialogue ID on mode switch to allow context resume
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    // 切换模式时清空右侧 (但保留 ID)
    this.clearResult();
  },

  // ========== 视图 / 面板 ==========

  isMobile() {
    return window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
  },

  // 统一的能量显示单位：kJ / kcal（默认 kJ）
  // 【重构】统一使用 ProfileModule 作为唯一数据源
  getEnergyUnit() {
    const p = typeof ProfileModule !== 'undefined' ? ProfileModule.getCurrentProfile() : null;
    const u = p?.diet?.energy_unit;
    return u === 'kcal' ? 'kcal' : 'kJ';
  },

  // 能量转换函数 - 委托给 EnergyUtils（保持 this.xxx() 调用兼容）
  kcalToKJ: EnergyUtils.kcalToKJ,
  kJToKcal: EnergyUtils.kJToKcal,
  macrosToKcal: EnergyUtils.macrosToKcal,

  setResultPanelOpen(open) {
    this.isResultPanelOpen = Boolean(open);
    const panel = document.querySelector('.result-panel');
    if (panel) {
      panel.classList.toggle('mobile-open', this.isResultPanelOpen && this.isMobile());
    }
    if (this.el.resultOverlay) {
      this.el.resultOverlay.classList.toggle('hidden', !(this.isResultPanelOpen && this.isMobile()));
    }
  },

  switchView(view) {
    // 确保 Auth 已初始化
    if (!Auth.isSignedIn()) {
      // 不直接阻断，而是显示加载中或登录提示 (响应用户需求4)
      console.warn('[Dashboard] Auth not ready, but allowing view switch to show status');
    }

    const next = view === 'profile' ? 'profile' : 'analysis';
    const prev = this.view;
    this.view = next;

    // 左侧菜单高亮
    this.el.sideMenu?.querySelectorAll('.side-menu-item')?.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === next);
    });

    // 聊天模式切换
    const modeSwitch = document.querySelector('.mode-switch');
    if (next === 'profile') {
      // Profile 模式：隐藏 diet/keep 切换，显示"档案沟通"
      if (modeSwitch) {
        this._savedModeSwitch = modeSwitch.innerHTML;
        modeSwitch.innerHTML = '<button class="mode-btn active" style="cursor: default; pointer-events: none;">档案沟通</button>';
      }
      this.renderProfileView();
      if (this.isMobile()) this.setResultPanelOpen(true);
      return;
    }

    // 切出 Profile 模式：还原聊天窗口状态
    if (prev === 'profile' && modeSwitch && this._savedModeSwitch) {
      modeSwitch.innerHTML = this._savedModeSwitch;
      this.bindModeSwitch(); // 重新绑定事件
    }

    // 切出 Profile 时隐藏其 footer 按钮
    if (prev === 'profile') {
      this.el.resultFooter.classList.add('hidden');
    }

    // 回到分析视图
    if (this.currentSession && this.currentSession.versions.length > 0) {
      this.renderResult(this.currentSession);
    } else {
      // 如果没有 Session 但有 Dialogue ID，尝试重新加载对话 state (修复 Profile 回来消失的问题)
      if (this.currentDialogueId) {
        this.loadDialogue(this.currentDialogueId);
      } else {
        this.clearResult();
      }
    }
    // 刷新 Sidebar 标题 (确保单位变更实时生效)
    if (window.SidebarModule) {
      window.SidebarModule.render();
    }
    // 刷新所有会话卡片标题（确保能量单位等设置生效）
    this.sessions.forEach(s => this.updateSessionCard(s));
    if (this.isMobile()) this.setResultPanelOpen(true);
  },

  // 绑定模式切换按钮事件
  bindModeSwitch() {
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.mode = btn.dataset.mode;
      });
    });
  },

  // ========== 图片处理 ==========

  async handleFiles(files) {
    const images = Array.from(files).filter(f => f.type.startsWith('image/'));
    for (const file of images) {
      const base64 = await this.fileToBase64(file);
      this.pendingImages.push({
        file,
        base64,
        preview: URL.createObjectURL(file)
      });
    }
    this.renderPreviews();
    this.updateSendButton();
  },

  // 委托给 ImageUtils
  fileToBase64: ImageUtils.fileToBase64,

  renderPreviews() {
    const container = this.el.previewContainer;
    if (!container) return;

    if (this.pendingImages.length === 0) {
      container.classList.add('hidden');
      container.innerHTML = '';
      return;
    }

    container.classList.remove('hidden');
    container.innerHTML = this.pendingImages.map((img, i) => `
      <div class="preview-item">
        <img src="${img.preview}" alt="Preview">
        <button class="preview-remove" onclick="Dashboard.removeImage(${i})">×</button>
      </div>
    `).join('');
  },

  removeImage(index) {
    URL.revokeObjectURL(this.pendingImages[index].preview);
    this.pendingImages.splice(index, 1);
    this.renderPreviews();
    this.updateSendButton();
  },

  updateSendButton() {
    const hasContent = this.pendingImages.length > 0 || this.el.chatInput?.value.trim();
    this.el.sendBtn.disabled = !hasContent;
  },

  // ========== 消息显示 ==========

  addMessage(content, role, options = {}) {
    if (options.sessionId) {
      options.onClick = (id) => this.selectSession(id);
    }
    return SessionModule.renderMessage(this.el.chatMessages, content, role, options);
  },

  // ========== Session 管理 ==========

  createSession(text, images) {
    const session = SessionModule.createSession(this.mode, text, images);

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
   * 加载后端卡片 (Phase 2)
   */
  async loadCard(cardId) {
    try {
      if (this.el.resultStatus) this.el.resultStatus.textContent = '加载中...';

      const cardData = await API.getCard(cardId);

      // 尝试并在本地 sessions 查找，避免重复创建
      let session = this.sessions.find(s => s.id === cardData.id);

      if (!session) {
        // 构造 Session 对象
        // 注意: 后端 ResultCard.versions 结构需与前端对齐
        // 这里假设 version item 就是 parsedData 的超集
        const versions = (cardData.versions || []).map((v, i) => ({
          number: i + 1,
          createdAt: new Date(v.created_at || new Date()),
          userNote: v.user_note || '',
          rawResult: v.raw_result || {},
          parsedData: this.parseResult(v.raw_result || {}, cardData.mode),
          advice: v.advice,
          adviceError: v.adviceError,
          adviceLoading: false
        }));
        const sourceUserNote = cardData.source_user_note || versions[0]?.userNote || '';
        const imageUrls = cardData.image_uris || [];

        session = {
          id: cardData.id,
          persistentCardId: cardData.id, // 重要：确保再次分析时复用 Card ID
          dialogueId: cardData.dialogue_id, // 关联 Dialogue
          mode: cardData.mode,
          createdAt: new Date(cardData.created_at),
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
          savedRecordId: cardData.saved_record_id,
          savedData: null
        };
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
  async loadDialogue(dialogueId) {
    if (!dialogueId) return;
    try {
      const dialogue = await API.getDialogue(dialogueId);
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

      messages.forEach(msg => {
        const hasCard = Boolean(msg.linked_card_id);
        const titleHint = msg.title || ((!msg.content && (msg.attachments || []).length > 0)
          ? `${msg.attachments.length}张图片`
          : '');
        const options = {
          title: titleHint
        };
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
      console.error('Load dialogue failed:', e);
      this.addMessage(`加载对话失败: ${e.message}`, 'assistant');
    }
  },

  /**
   * 创建新对话 (Phase 2)
   */
  async createNewDialogue() {
    try {
      // 默认标题，后端会处理
      const dialogue = await API.createDialogue("新对话");
      // 刷新 Sidebar
      if (window.SidebarModule) {
        SidebarModule.loadDialogues();
        // TODO: 选中该 dialogue
      }
      this.addMessage('已创建新对话', 'assistant');
    } catch (e) {
      console.error("Create dialogue failed", e);
    }
  },

  // ========== 分析流程 ==========

  async startNewAnalysis() {
    const text = this.el.chatInput?.value.trim() || '';
    if (!text && this.pendingImages.length === 0) return;

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
        const initialTitle = text ? text.slice(0, 15) : (this.pendingImages.length ? `${this.pendingImages.length}张图片` : '分析中');
        const cardData = {
          id: session.persistentCardId,
          dialogue_id: session.dialogueId,
          mode: session.mode,
          title: initialTitle,
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
   * Profile 模式下的分析
   */
  async startProfileAnalysis(userNote) {
    // 添加用户消息
    this.addMessage(userNote, 'user');

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

    // 调用 Profile 分析（传入 targetMonths）
    const result = await ProfileModule.analyze(userNote, targetMonths);

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

  // 版本切换
  switchVersion(delta) {
    if (!this.currentSession) return;

    const session = this.currentSession;
    const newVersion = session.currentVersion + delta;

    if (newVersion < 1 || newVersion > session.versions.length) return;

    session.currentVersion = newVersion;
    this.renderResult(session);
  },

  // ========== 建议更新 ==========

  // 委托给 AnalysisModule
  updateAdvice: AnalysisModule.updateAdvice,
  autoFetchAdvice: AnalysisModule.autoFetchAdvice,

  // ========== 数据解析 ==========

  // 委托给 ParserModule
  parseResult: ParserModule.parseResult,
  parseDietResult: ParserModule.parseDietResult,
  parseKeepResult: ParserModule.parseKeepResult,

  // ========== 结果渲染 ==========

  updateSessionCard(session) {
    let title = '';
    const latest = session.versions.length > 0 ? session.versions[session.versions.length - 1] : null;

    if (latest) {
      if (latest.parsedData.type === 'diet') {
        const unit = this.getEnergyUnit();
        const energy = latest.parsedData.summary.totalEnergy;
        // 强制取整
        const val = unit === 'kcal' ? Math.round(energy) : Math.round(this.kcalToKJ(energy));
        title = `${val} ${unit} - ${latest.parsedData.dishes.length}种食物`;
      } else {
        const eventCount = latest.parsedData.scaleEvents.length +
          latest.parsedData.sleepEvents.length +
          latest.parsedData.bodyMeasureEvents.length;
        title = `Keep - ${eventCount}条记录`;
      }
    }

    SessionModule.updateCardVisuals(session.id, title, {
      current: session.currentVersion,
      total: session.versions.length,
      isLatest: session.currentVersion === session.versions.length
    });
  },

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

  renderAdvice(adviceText) {
    const contentEl = document.getElementById('advice-content');
    const statusEl = document.getElementById('advice-status');
    if (contentEl) {
      // 简单的 markdown 转 HTML
      const html = this.simpleMarkdownToHtml(adviceText);
      contentEl.innerHTML = `<div class="advice-text">${html}</div>`;
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
    if (contentEl) {
      contentEl.innerHTML = `<div class="advice-error">⚠️ 建议获取失败：${errorMsg}</div>`;
    }
    if (statusEl) {
      statusEl.className = 'advice-status error';
      statusEl.textContent = '';
    }
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

    // 在 footer 显示操作按钮
    this.el.resultFooter.classList.remove('hidden');
    this.el.resultFooter.innerHTML = ProfileRenderModule.renderFooterButtons();
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

  showLoading() {
    // 仅状态提示：不遮挡/不替换整个确认面板内容
    this.updateStatus('loading');
    if (window.FooterModule) {
      window.FooterModule.update(FooterState.HIDDEN);
    } else if (this.el.resultFooter) {
      this.el.resultFooter.classList.add('hidden');
    }
  },

  showError(error) {
    this.updateStatus('');
    const errorInfo = window.ErrorHandlerModule
      ? window.ErrorHandlerModule.getFriendlyError(error)
      : { title: '分析失败', message: (error.message || error || '未知错误') };

    // 默认展示逻辑：只要存在当前会话，就认为是分析流错误，回到 Draft 态展示错误横幅
    if (this.currentSession && typeof this.renderDraftState === 'function') {
      this.currentSession.lastError = errorInfo;
      this.renderDraftState(this.currentSession);
      return;
    }

    // 兜底：无活跃会话时的简洁提示
    if (window.ToastUtils) {
      ToastUtils.show(`${errorInfo.title}: ${errorInfo.message}`, 'error');
    }

    this.el.resultContent.innerHTML = `
      <div class="empty-state">
        <div style="font-size:1.5rem; margin-bottom:12px;">⚠️</div>
        <p class="text-error" style="font-weight:650;">${errorInfo.title}</p>
        <p style="font-size:0.9rem; color:var(--color-text-secondary);">${errorInfo.message}</p>
      </div>
    `;

    if (window.FooterModule) {
      window.FooterModule.update(FooterState.HIDDEN);
    }
  },

  clearResult() {
    // 轻量占位：不做大面积遮挡
    this.el.resultContent.innerHTML = `
      <div class="result-card" style="padding: 16px;">
        <div class="text-secondary" style="font-weight: 600; margin-bottom: 6px;">分析面板</div>
        <div class="text-muted" style="font-size: 0.875rem;">
          上传图片或输入描述后点击发送开始分析。分析过程中这里会显示状态与可编辑结果。
        </div>
      </div>
    `;
    if (window.FooterModule) {
      window.FooterModule.update(FooterState.HIDDEN); // Or EMPTY
    } else if (this.el.resultFooter) {
      this.el.resultFooter.classList.add('hidden');
    }
    this.el.resultTitle.textContent = '分析结果';
    this.updateStatus('');
  },

  updateStatus(status) {
    const el = this.el.resultStatus;
    if (!el) return;
    el.className = 'result-status';
    if (status === 'saved') {
      el.textContent = '✓ 已保存';
      el.classList.add('saved');
    } else if (status === 'loading') {
      el.innerHTML = `<span class="loading-spinner" style="display:inline-block; width:14px; height:14px; vertical-align: -2px; margin-right:6px;"></span>分析中...`;
      el.classList.add('loading');
    } else if (status === 'modified') {
      el.textContent = '● 已修改';
      el.classList.add('modified');
    } else {
      el.textContent = '';
    }
  },

  updateButtonStates(session) {
    if (!window.FooterModule) return;

    if (!session) {
      window.FooterModule.update(FooterState.HIDDEN);
      return;
    }

    // Draft 状态特殊处理
    if (!session.versions || session.versions.length === 0) {
      window.FooterModule.update(FooterState.DRAFT, session);
      return;
    }

    // Determine mode
    if (session.mode === 'diet') {
      window.FooterModule.update(FooterState.ANALYSIS_DIET, session);
    } else {
      window.FooterModule.update(FooterState.ANALYSIS_KEEP, session);
    }
  },

  isDataUnchanged(session) {
    if (!session.savedData) return false;
    const current = this.collectEditedData();
    return JSON.stringify(current) === JSON.stringify(session.savedData);
  },

  // ========== 历史 ==========

  // 委托给 StorageModule
  loadHistory: StorageModule.loadHistory,
  addHistoryItem: StorageModule.addHistoryItem, // 恢复这一行委托
};

// Mixin Modules
Object.assign(Dashboard, AnalysisModule);
Object.assign(Dashboard, ProfileRenderModule);
Object.assign(Dashboard, DietRenderModule);
Object.assign(Dashboard, KeepRenderModule);
Object.assign(Dashboard, StorageModule);

document.addEventListener('DOMContentLoaded', () => Dashboard.init());
