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

  // 移动端：确认面板（结果面板）是否打开
  isResultPanelOpen: false,

  // Profile（前端先行：本地存储 + 占位请求）
  profile: null,

  // Diet：AI 菜式的 ingredients 折叠状态（默认折叠）
  dietIngredientsCollapsed: {},

  // DOM 元素缓存
  el: {},

  async init() {
    this.cacheElements();
    this.bindEvents();

    await Auth.init();
    if (!Auth.isSignedIn()) {
      window.location.href = 'index.html';
      return;
    }
    Auth.mountUserButton('#user-button');
    this.loadHistory();
    console.log('[Dashboard] Initialized');

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

    // 重新分析（在当前 session 上添加新版本）
    this.el.reAnalyzeBtn?.addEventListener('click', () => this.reAnalyze());

    // 更新建议（调用 advice API）
    this.el.updateAdviceBtn?.addEventListener('click', () => this.updateAdvice());

    // 保存记录
    this.el.saveBtn?.addEventListener('click', () => this.saveRecord());

    // 初始化 Profile
    this.profile = this.loadProfile();
  },

  switchMode(mode) {
    this.mode = mode;
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    // 切换模式时清空右侧
    this.clearResult();
  },

  // ========== 视图 / 面板 ==========

  isMobile() {
    return window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
  },

  // 统一的能量显示单位：kJ / kcal（默认 kJ）
  getEnergyUnit() {
    const u = this.profile?.diet?.energy_unit;
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
    const next = view === 'profile' ? 'profile' : 'analysis';
    this.view = next;

    // 左侧菜单高亮
    this.el.sideMenu?.querySelectorAll('.side-menu-item')?.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === next);
    });

    if (next === 'profile') {
      this.renderProfileView();
      if (this.isMobile()) this.setResultPanelOpen(true);
      return;
    }

    // 回到分析视图
    if (this.currentSession && this.currentSession.versions.length > 0) {
      this.renderResult(this.currentSession);
    } else {
      this.clearResult();
    }
    if (this.isMobile()) this.setResultPanelOpen(true);
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

    // 渲染最新版本
    if (session.versions.length > 0) {
      this.renderResult(session);
      if (this.isMobile()) this.setResultPanelOpen(true);
    }
  },

  // ========== 分析流程 ==========

  async startNewAnalysis() {
    const text = this.el.chatInput?.value.trim() || '';
    if (!text && this.pendingImages.length === 0) return;

    // 创建新 Session
    const session = this.createSession(text, [...this.pendingImages]);
    this.currentSession = session;

    // 添加消息卡片
    // 逻辑：如果有文字，标题留空（后续更新）；如果只有图片无文字，标题显示图片数量
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
  },

  // 委托给 AnalysisModule
  reAnalyze: AnalysisModule.reAnalyze,
  executeAnalysis: AnalysisModule.executeAnalysis,

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
        const val = unit === 'kcal' ? energy : Math.round(this.kcalToKJ(energy));
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

    this.el.resultFooter.classList.remove('hidden');
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

  renderProfileView() {
    const p = this.profile || this.getDefaultProfile();
    this.el.resultTitle.textContent = 'Profile 设置';
    this.updateStatus('');
    this.el.resultFooter.classList.add('hidden');

    const unit = this.getEnergyUnit();
    // 计算显示的能量目标值
    const rawEnergyTarget = p.diet?.daily_energy_kj_target ?? 0;
    const displayEnergyTarget = unit === 'kcal' ? Math.round(this.kJToKcal(rawEnergyTarget)) : rawEnergyTarget;

    const userName = Auth.user?.firstName || Auth.user?.fullName || Auth.user?.username || '用户';

    this.el.resultContent.innerHTML = `
      <style>
        .profile-container { display: flex; flex-direction: column; gap: 20px; }
        .profile-section {
          background: var(--color-bg-secondary);
          border: 1px solid var(--color-border);
          border-radius: 16px;
          padding: 20px 24px;
        }
        .profile-section-header {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 20px;
          padding-bottom: 16px;
          border-bottom: 1px solid var(--color-border);
        }
        .profile-section-icon {
          width: 40px;
          height: 40px;
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.25rem;
          flex-shrink: 0;
        }
        .profile-section-icon.user { background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); }
        .profile-section-icon.diet { background: linear-gradient(135deg, #10b981 0%, #34d399 100%); }
        .profile-section-icon.keep { background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%); }
        .profile-section-title {
          font-size: 1rem;
          font-weight: 600;
          color: var(--color-text-primary);
        }
        .profile-section-subtitle {
          font-size: 0.75rem;
          color: var(--color-text-muted);
          margin-top: 2px;
        }
        .profile-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 16px;
        }
        .profile-field {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .profile-field-label {
          font-size: 0.75rem;
          font-weight: 500;
          color: var(--color-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .profile-field-input {
          background: var(--color-bg-tertiary);
          border: 1px solid var(--color-border);
          border-radius: 10px;
          padding: 12px 14px;
          font-size: 0.9rem;
          color: var(--color-text-primary);
          transition: all 0.2s ease;
          width: 100%;
          box-sizing: border-box;
        }
        .profile-field-input:hover {
          border-color: rgba(99, 102, 241, 0.4);
        }
        .profile-field-input:focus {
          outline: none;
          border-color: var(--color-accent-primary);
          box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
        }
        .profile-field-input[type="number"] {
          font-variant-numeric: tabular-nums;
        }
        .profile-actions {
          display: flex;
          justify-content: flex-end;
          gap: 12px;
          margin-top: 8px;
        }
        .profile-btn {
          padding: 12px 24px;
          border-radius: 10px;
          font-size: 0.875rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .profile-btn-secondary {
          background: var(--color-bg-tertiary);
          border: 1px solid var(--color-border);
          color: var(--color-text-secondary);
        }
        .profile-btn-secondary:hover {
          background: var(--color-bg-glass);
          border-color: var(--color-text-muted);
        }
        .profile-btn-primary {
          background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
          border: none;
          color: white;
        }
        .profile-btn-primary:hover {
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
        }
        .profile-macro-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 12px;
        }
        @media (max-width: 768px) {
          .profile-grid { grid-template-columns: 1fr; }
          .profile-macro-grid { grid-template-columns: repeat(2, 1fr); }
        }
      </style>

      <div class="profile-container">
        <!-- 用户信息 -->
        <div class="profile-section">
          <div class="profile-section-header">
            <div class="profile-section-icon user">👤</div>
            <div>
              <div class="profile-section-title">${userName} 的档案</div>
              <div class="profile-section-subtitle">个人设置与目标配置</div>
            </div>
          </div>
          <div class="profile-grid">
            <div class="profile-field">
              <label class="profile-field-label">时区</label>
              <select id="profile-timezone" class="profile-field-input">
                ${this.renderTimezoneOptions(p.timezone)}
              </select>
            </div>
            <div class="profile-field">
              <label class="profile-field-label">能量显示单位</label>
              <select id="energy-unit" class="profile-field-input" onchange="Dashboard.setEnergyUnit(this.value)">
                <option value="kJ" ${unit === 'kJ' ? 'selected' : ''}>kJ（默认）</option>
                <option value="kcal" ${unit === 'kcal' ? 'selected' : ''}>kcal</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Diet 目标 -->
        <div class="profile-section">
          <div class="profile-section-header">
            <div class="profile-section-icon diet">🍽️</div>
            <div>
              <div class="profile-section-title">Diet 目标</div>
              <div class="profile-section-subtitle">每日营养摄入目标设置</div>
            </div>
          </div>
          <div class="profile-grid" style="margin-bottom: 16px;">
            <div class="profile-field">
              <label class="profile-field-label">目标类型</label>
              <select id="diet-goal" class="profile-field-input">
                ${this.renderDietGoalOptions(p.diet?.goal)}
              </select>
            </div>
            <div class="profile-field">
              <label class="profile-field-label">每日能量目标 (${unit})</label>
              <input id="diet-energy-kj" type="number" class="profile-field-input" value="${displayEnergyTarget}">
            </div>
          </div>
          <div class="profile-macro-grid">
            <div class="profile-field">
              <label class="profile-field-label">蛋白质 (g)</label>
              <input id="diet-protein-g" type="number" class="profile-field-input" value="${p.diet?.protein_g_target ?? 0}" step="0.1">
            </div>
            <div class="profile-field">
              <label class="profile-field-label">脂肪 (g)</label>
              <input id="diet-fat-g" type="number" class="profile-field-input" value="${p.diet?.fat_g_target ?? 0}" step="0.1">
            </div>
            <div class="profile-field">
              <label class="profile-field-label">碳水 (g)</label>
              <input id="diet-carbs-g" type="number" class="profile-field-input" value="${p.diet?.carbs_g_target ?? 0}" step="0.1">
            </div>
            <div class="profile-field">
              <label class="profile-field-label">纤维 (g)</label>
              <input id="diet-fiber-g" type="number" class="profile-field-input" value="${p.diet?.fiber_g_target ?? 0}" step="0.1">
            </div>
          </div>
          <div class="profile-grid" style="margin-top: 16px;">
            <div class="profile-field">
              <label class="profile-field-label">钠 (mg)</label>
              <input id="diet-sodium-mg" type="number" class="profile-field-input" value="${p.diet?.sodium_mg_target ?? 0}" step="1">
            </div>
          </div>
        </div>

        <!-- Keep 目标 -->
        <div class="profile-section">
          <div class="profile-section-header">
            <div class="profile-section-icon keep">💪</div>
            <div>
              <div class="profile-section-title">Keep 目标</div>
              <div class="profile-section-subtitle">体重与体态目标设置</div>
            </div>
          </div>
          <div class="profile-grid" style="margin-bottom: 16px;">
            <div class="profile-field">
              <label class="profile-field-label">目标体重 (kg)</label>
              <input id="keep-weight-kg" type="number" class="profile-field-input" value="${p.keep?.weight_kg_target ?? 0}" step="0.1">
            </div>
            <div class="profile-field">
              <label class="profile-field-label">目标体脂率 (%)</label>
              <input id="keep-bodyfat-pct" type="number" class="profile-field-input" value="${p.keep?.body_fat_pct_target ?? 0}" step="0.1">
            </div>
          </div>
          <div class="profile-macro-grid" style="grid-template-columns: repeat(3, 1fr);">
            <div class="profile-field">
              <label class="profile-field-label">胸围 (cm)</label>
              <input id="keep-chest-cm" type="number" class="profile-field-input" value="${p.keep?.dimensions_cm_target?.chest_cm ?? 0}" step="0.1">
            </div>
            <div class="profile-field">
              <label class="profile-field-label">腰围 (cm)</label>
              <input id="keep-waist-cm" type="number" class="profile-field-input" value="${p.keep?.dimensions_cm_target?.waist_cm ?? 0}" step="0.1">
            </div>
            <div class="profile-field">
              <label class="profile-field-label">臀围 (cm)</label>
              <input id="keep-hips-cm" type="number" class="profile-field-input" value="${p.keep?.dimensions_cm_target?.hips_cm ?? 0}" step="0.1">
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="profile-actions">
          <button class="profile-btn profile-btn-secondary" onclick="Dashboard.switchView('analysis')">返回分析</button>
          <button class="profile-btn profile-btn-primary" onclick="Dashboard.saveProfile()">💾 保存档案</button>
        </div>
      </div>
    `;
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
        dimensions_cm_target: {
          chest_cm: getNum('keep-chest-cm'),
          waist_cm: getNum('keep-waist-cm'),
          hips_cm: getNum('keep-hips-cm'),
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
    const next = this.profile || this.getDefaultProfile();
    next.diet = next.diet || {};
    next.diet.energy_unit = u;
    this.saveProfileLocal(next);

    // 立即生效
    if (this.view === 'profile') {
      this.renderProfileView();
    }

    // 更新所有会话卡片 Title
    this.sessions.forEach(s => this.updateSessionCard(s));

    // 更新历史列表
    this.loadHistory(); // 清空并重置头
    this.sessions.filter(s => s.isSaved).forEach(s => this.addHistoryItem(s));

    if (this.view === 'analysis' && this.currentSession && this.currentSession.versions.length > 0) {
      this.recalculateDietSummary(false);
      this.renderDietDishes();
    }
  },

  // ========== 保存 ==========

  // 委托给 StorageModule
  saveRecord: StorageModule.saveRecord,
  determineKeepEventType: StorageModule.determineKeepEventType,

  // ========== 状态管理 ==========

  showLoading() {
    // 仅状态提示：不遮挡/不替换整个确认面板内容
    this.updateStatus('loading');
    if (this.el.resultFooter) {
      this.el.resultFooter.classList.add('hidden');
    }
  },

  showError(message) {
    this.updateStatus('');
    this.el.resultContent.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">⚠️</div>
        <h3>分析失败</h3>
        <p>${message}</p>
      </div>
    `;
    this.el.resultFooter.classList.add('hidden');
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
    this.el.resultFooter.classList.add('hidden');
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
    if (!session) return;

    // 更新建议按钮（只对 diet 模式有效）
    if (this.el.updateAdviceBtn) {
      this.el.updateAdviceBtn.disabled = session.mode !== 'diet';
    }

    // 保存按钮状态
    if (this.el.saveBtn) {
      if (session.isSaved && this.isDataUnchanged(session)) {
        this.el.saveBtn.disabled = true;
        this.el.saveBtn.textContent = '💾 已保存';
      } else if (session.isSaved) {
        this.el.saveBtn.disabled = false;
        this.el.saveBtn.textContent = '💾 更新记录';
      } else {
        this.el.saveBtn.disabled = false;
        this.el.saveBtn.textContent = '💾 保存记录';
      }
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
  addHistoryItem: StorageModule.addHistoryItem,
};

document.addEventListener('DOMContentLoaded', () => Dashboard.init());
