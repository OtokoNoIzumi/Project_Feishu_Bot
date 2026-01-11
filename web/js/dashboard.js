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

  // kcal -> kJ
  kcalToKJ(kcal) {
    return (Number(kcal) || 0) * 4.184;
  },

  // kJ -> kcal
  kJToKcal(kj) {
    return (Number(kj) || 0) / 4.184;
  },

  // 宏量 -> kcal（P/C=4,F=9）
  macrosToKcal(proteinG, fatG, carbsG) {
    const p = Number(proteinG) || 0;
    const f = Number(fatG) || 0;
    const c = Number(carbsG) || 0;
    return p * 4 + f * 9 + c * 4;
  },

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

  fileToBase64(file) {
    return new Promise(resolve => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.readAsDataURL(file);
    });
  },

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
    const msg = document.createElement('div');
    msg.className = `message ${role}`;

    if (options.sessionId) {
      msg.dataset.sessionId = options.sessionId;
      msg.classList.add('session-card');
      msg.onclick = () => this.selectSession(options.sessionId);
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

    // 标题
    if (options.title) {
      const titleEl = document.createElement('div');
      titleEl.className = 'message-title';
      titleEl.textContent = options.title;
      msg.appendChild(titleEl);
    }

    // 版本标签
    if (options.version && options.version > 1) {
      const versionEl = document.createElement('span');
      versionEl.className = 'version-badge';
      versionEl.textContent = `v${options.version}`;
      msg.appendChild(versionEl);
    }

    // 文字内容
    if (content) {
      const textEl = document.createElement('div');
      textEl.className = 'message-text';
      textEl.textContent = content;
      msg.appendChild(textEl);
    }

    this.el.chatMessages?.appendChild(msg);
    this.el.chatMessages.scrollTop = this.el.chatMessages.scrollHeight;

    return msg;
  },

  // ========== Session 管理 ==========

  createSession(text, images) {
    const session = {
      id: Date.now().toString(),
      mode: this.mode,
      createdAt: new Date(),
      text: text,                    // 初始文字说明
      images: images,                // 原始附件 (base64)
      imageUrls: images.map(img => img.preview),  // 预览 URL
      imageHashes: [],               // 图片哈希，异步计算后填充
      versions: [],                  // 分析版本列表
      currentVersion: 0,
      isSaved: false,
      savedRecordId: null,           // 后端返回的记录ID，用于更新
      savedData: null,               // 保存时的数据快照
    };

    // 异步计算 SHA-256 哈希
    this.calculateImageHashes(images).then(hashes => {
      session.imageHashes = hashes;
    });

    this.sessions.unshift(session);
    return session;
  },

  // 使用 Web Crypto API 计算 SHA-256 哈希
  async calculateImageHashes(images) {
    const hashes = [];
    for (const img of images) {
      try {
        // 将 base64 转换为 ArrayBuffer
        const binary = atob(img.base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
          bytes[i] = binary.charCodeAt(i);
        }

        // 使用 SHA-256 计算哈希
        const hashBuffer = await crypto.subtle.digest('SHA-256', bytes);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        hashes.push(hashHex);
      } catch (e) {
        console.error('[Dashboard] Hash calculation failed:', e);
        // 回退方案：使用长度
        hashes.push(`fallback_${img.base64.length}`);
      }
    }
    return hashes;
  },

  selectSession(sessionId) {
    const session = this.sessions.find(s => s.id === sessionId);
    if (!session) return;

    this.currentSession = session;

    // 高亮选中的卡片
    document.querySelectorAll('.session-card').forEach(el => {
      el.classList.toggle('active', el.dataset.sessionId === sessionId);
    });

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
    const title = this.generateTitle(text, this.pendingImages.length);
    this.addMessage(text || '', 'user', {
      sessionId: session.id,
      images: session.imageUrls,
      title: title,
    });

    // 清空输入
    this.el.chatInput.value = '';
    this.pendingImages = [];
    this.renderPreviews();
    this.updateSendButton();

    // 执行分析
    await this.executeAnalysis(session, text);
  },

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

  async executeAnalysis(session, userNote) {
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
      };
      session.versions.push(version);
      session.currentVersion = version.number;

      // 更新消息卡片标题
      this.updateSessionCard(session);

      // 渲染结果
      this.renderResult(session);
      if (this.isMobile()) this.setResultPanelOpen(true);

      this.addMessage('分析完成！', 'assistant');

    } catch (error) {
      console.error('[Dashboard] Analysis failed:', error);
      this.addMessage(`分析失败: ${error.message}`, 'assistant');
      this.showError(error.message);
    }
  },

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

    try {
      this.el.updateAdviceBtn.disabled = true;
      this.el.updateAdviceBtn.textContent = '⏳ 生成中...';

      // 收集当前编辑的数据作为 facts
      const facts = this.collectEditedData();
      const userNote = document.getElementById('additional-note')?.value.trim() || '';

      const adviceResult = await API.getDietAdvice(facts, userNote);

      if (adviceResult.advice_text) {
        currentVersion.advice = adviceResult.advice_text;
        this.renderAdvice(adviceResult.advice_text);
        this.addMessage('建议已更新', 'assistant');
      } else if (adviceResult.error) {
        this.addMessage(`建议生成失败: ${adviceResult.error}`, 'assistant');
      }

    } catch (error) {
      this.addMessage(`建议更新失败: ${error.message}`, 'assistant');
    } finally {
      this.el.updateAdviceBtn.disabled = false;
      this.el.updateAdviceBtn.textContent = '✨ 更新建议';
    }
  },

  // ========== 数据解析 ==========

  parseResult(rawResult, mode) {
    if (mode === 'diet') {
      return this.parseDietResult(rawResult);
    } else {
      return this.parseKeepResult(rawResult);
    }
  },

  parseDietResult(data) {
    const summary = data.meal_summary || {};

    let totalEnergy = 0;
    let totalProtein = 0;
    let totalFat = 0;
    let totalCarb = 0;
    let totalSodiumMg = 0;
    let totalFiberG = 0;

    const dishes = [];

    (data.dishes || []).forEach((dish, i) => {
      let dishWeight = 0;
      let dishEnergy = 0;
      let dishProtein = 0;
      let dishFat = 0;
      let dishCarb = 0;
      let dishSodiumMg = 0;
      let dishFiberG = 0;

      (dish.ingredients || []).forEach(ing => {
        const weight = ing.weight_g || 0;
        dishWeight += weight;

        if (ing.macros) {
          dishProtein += ing.macros.protein_g || 0;
          dishFat += ing.macros.fat_g || 0;
          dishCarb += ing.macros.carbs_g || 0;
          dishSodiumMg += ing.macros.sodium_mg || 0;
          dishFiberG += ing.macros.fiber_g || 0;
        }

        // 计算能量
        if (ing.energy_kj) {
          dishEnergy += ing.energy_kj / 4.184;
        } else if (ing.macros) {
          const m = ing.macros;
          dishEnergy += (m.protein_g || 0) * 4 + (m.fat_g || 0) * 9 + (m.carbs_g || 0) * 4;
        }
      });

      dishes.push({
        id: i,
        name: dish.standard_name || '未知',
        weight: Math.round(dishWeight),
        enabled: true,
        source: 'ai',
        ingredients: (dish.ingredients || []).map(ing => ({
          name_zh: ing.name_zh,
          weight_g: Number(ing.weight_g) || 0,
          weight_method: ing.weight_method,
          data_source: ing.data_source,
          energy_kj: Number(ing.energy_kj) || 0,
          macros: {
            protein_g: Number(ing.macros?.protein_g) || 0,
            fat_g: Number(ing.macros?.fat_g) || 0,
            carbs_g: Number(ing.macros?.carbs_g) || 0,
            sodium_mg: Number(ing.macros?.sodium_mg) || 0,
            fiber_g: Number(ing.macros?.fiber_g) || 0,
          },
        })),
      });

      totalEnergy += dishEnergy;
      totalProtein += dishProtein;
      totalFat += dishFat;
      totalCarb += dishCarb;
      totalSodiumMg += dishSodiumMg;
      totalFiberG += dishFiberG;
    });

    return {
      type: 'diet',
      summary: {
        mealName: summary.meal_name || '饮食记录',
        dietTime: summary.diet_time || '',
        totalEnergy: Math.round(totalEnergy),
        totalProtein: Math.round(totalProtein * 10) / 10,
        totalFat: Math.round(totalFat * 10) / 10,
        totalCarb: Math.round(totalCarb * 10) / 10,
        totalFiber: Math.round(totalFiberG * 10) / 10,
        totalSodiumMg: Math.round(totalSodiumMg),
      },
      dishes: dishes,
      advice: summary.advice || '',
    };
  },

  parseKeepResult(data) {
    // Keep 返回的是 scale_events, sleep_events, body_measure_events
    const result = {
      type: 'keep',
      scaleEvents: data.scale_events || [],
      sleepEvents: data.sleep_events || [],
      bodyMeasureEvents: data.body_measure_events || [],
    };

    return result;
  },

  // ========== 结果渲染 ==========

  generateTitle(text, imageCount) {
    if (text && text.length > 20) {
      return text.substring(0, 20) + '...';
    } else if (text) {
      return text;
    } else if (imageCount > 0) {
      return `${imageCount}张图片`;
    }
    return '新分析';
  },

  updateSessionCard(session) {
    const card = document.querySelector(`[data-session-id="${session.id}"]`);
    if (!card) return;

    const titleEl = card.querySelector('.message-title');
    if (titleEl && session.versions.length > 0) {
      const latest = session.versions[session.versions.length - 1];
      if (latest.parsedData.type === 'diet') {
        titleEl.textContent = `${latest.parsedData.summary.totalEnergy} kcal - ${latest.parsedData.dishes.length}种食物`;
      } else {
        const eventCount = latest.parsedData.scaleEvents.length +
          latest.parsedData.sleepEvents.length +
          latest.parsedData.bodyMeasureEvents.length;
        titleEl.textContent = `Keep - ${eventCount}条记录`;
      }
    }

    // 更新版本标签
    if (session.versions.length > 1) {
      let badge = card.querySelector('.version-badge');
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'version-badge';
        card.appendChild(badge);
      }
      badge.textContent = `v${session.currentVersion}/${session.versions.length}`;
    }
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

  renderDietResult(session, version) {
    const data = version.parsedData;
    const summary = data.summary;

    // 缓存当前 dishes 用于编辑
    this.currentDishes = [...data.dishes];
    this.currentDietMeta = {
      mealName: summary.mealName || '饮食记录',
      dietTime: summary.dietTime || '',
    };
    this.recalculateDietSummary(false);

    // 获取当前版本的 user_note
    const currentNote = version.userNote || session.text || '';

    this.el.resultContent.innerHTML = `
      <div class="result-card">
        <div class="result-card-header">
          <div class="result-icon">🍽️</div>
          <div>
            <div class="result-card-title">${summary.mealName}</div>
            <div class="result-card-subtitle" id="diet-subtitle">${this.currentDishes.length} 种食物 · ${summary.dietTime || ''}</div>
          </div>
          ${session.versions.length > 1 ? `
            <div class="version-nav">
              <button class="version-btn" onclick="Dashboard.switchVersion(-1)" ${session.currentVersion <= 1 ? 'disabled' : ''}>◀</button>
              <span class="version-label">v${version.number}/${session.versions.length}</span>
              <button class="version-btn" onclick="Dashboard.switchVersion(1)" ${session.currentVersion >= session.versions.length ? 'disabled' : ''}>▶</button>
            </div>
          ` : ''}
        </div>

        <div class="nutrition-summary">
          <div class="summary-energy">
            <div class="value">
              <span id="sum-total-energy">${this.currentDietTotals.totalEnergy}</span>
              <span id="sum-energy-unit">${this.getEnergyUnit()}</span>
            </div>
            <div class="label">总能量（自动加总）</div>
          </div>
          <div class="summary-macros">
            <div class="summary-macro-item">
              <div class="value"><span id="sum-total-protein">${this.currentDietTotals.totalProtein}</span> g</div>
              <div class="label">蛋白质</div>
            </div>
            <div class="summary-macro-item">
              <div class="value"><span id="sum-total-fat">${this.currentDietTotals.totalFat}</span> g</div>
              <div class="label">脂肪</div>
            </div>
            <div class="summary-macro-item">
              <div class="value"><span id="sum-total-carb">${this.currentDietTotals.totalCarb}</span> g</div>
              <div class="label">碳水</div>
            </div>
            <div class="summary-macro-item">
              <div class="value"><span id="sum-total-fiber">${this.currentDietTotals.totalFiber}</span> g</div>
              <div class="label">膳食纤维</div>
            </div>
            <div class="summary-macro-item">
              <div class="value"><span id="sum-total-sodium">${this.currentDietTotals.totalSodiumMg}</span> mg</div>
              <div class="label">钠</div>
            </div>
            <div class="summary-macro-item">
              <div class="value"><span id="sum-total-weight">${this.currentDietTotals.totalWeightG}</span> g</div>
              <div class="label">总重量</div>
            </div>
          </div>
        </div>

        <div class="dishes-section">
          <div class="dishes-title">食物明细</div>
          <div id="diet-dishes-container"></div>
          <button class="add-dish-btn" onclick="Dashboard.addDish()">+ 添加菜式</button>
        </div>

        <div class="note-section">
          <div class="dishes-title">文字说明</div>
          <textarea id="additional-note" class="note-input" placeholder="补充或修正说明...">${currentNote}</textarea>
        </div>

        <div id="advice-section" class="advice-section ${version.advice ? '' : 'hidden'}">
          <div class="dishes-title">AI 建议</div>
          <p class="advice-text" id="advice-text">${version.advice || ''}</p>
        </div>
      </div>
    `;

    this.renderDietDishes();
    this.el.resultTitle.textContent = '饮食分析结果';
    this.updateStatus(session.isSaved ? 'saved' : '');
  },

  renderKeepResult(session, version) {
    const data = version.parsedData;

    let html = `<div class="result-card">
      <div class="result-card-header">
        <div class="result-icon">💪</div>
        <div>
          <div class="result-card-title">Keep 数据</div>
          <div class="result-card-subtitle">
            ${data.scaleEvents.length ? `体重×${data.scaleEvents.length} ` : ''}
            ${data.sleepEvents.length ? `睡眠×${data.sleepEvents.length} ` : ''}
            ${data.bodyMeasureEvents.length ? `围度×${data.bodyMeasureEvents.length}` : ''}
          </div>
        </div>
      </div>
    `;

    // 体重事件
    if (data.scaleEvents.length > 0) {
      html += `<div class="keep-section"><div class="dishes-title">⚖️ 体重记录</div>`;
      data.scaleEvents.forEach(e => {
        // unified schema 返回的是直接的对象，不包含 scale_event 包裹层
        html += `
          <div class="keep-item">
            <div class="keep-main">
              <span class="keep-value">${e.weight_kg || '?'} kg</span>
              ${e.body_fat_pct ? `<span class="keep-sub">体脂 ${e.body_fat_pct}%</span>` : ''}
            </div>
            <div class="keep-details">
              ${e.bmi ? `<span>BMI ${e.bmi}</span>` : ''}
              ${e.muscle_kg ? `<span>肌肉 ${e.muscle_kg}kg</span>` : ''}
              ${e.bmr_kcal_per_day ? `<span>基代 ${e.bmr_kcal_per_day}kcal</span>` : ''}
            </div>
            <span class="keep-meta">${e.measured_at_local || ''}</span>
          </div>
        `;
      });
      html += `</div>`;
    }

    // 睡眠事件
    if (data.sleepEvents.length > 0) {
      html += `<div class="keep-section"><div class="dishes-title">😴 睡眠记录</div>`;
      data.sleepEvents.forEach(e => {
        const hours = e.total_duration_minutes ? Math.floor(e.total_duration_minutes / 60) : 0;
        const mins = e.total_duration_minutes ? e.total_duration_minutes % 60 : 0;
        const durationStr = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;

        html += `
          <div class="keep-item">
            <div class="keep-main">
              <span class="keep-value">${durationStr}</span>
              ${e.score ? `<span class="keep-sub">评分 ${e.score}</span>` : ''}
            </div>
            <div class="keep-details">
              ${e.deep_sleep_minutes ? `<span>深睡 ${e.deep_sleep_minutes}m</span>` : ''}
              ${e.light_sleep_minutes ? `<span>浅睡 ${e.light_sleep_minutes}m</span>` : ''}
              ${e.rem_sleep_minutes ? `<span>REM ${e.rem_sleep_minutes}m</span>` : ''}
            </div>
            <span class="keep-meta">${e.date_str || ''} ${e.sleep_start_time || ''}-${e.sleep_end_time || ''}</span>
          </div>
        `;
      });
      html += `</div>`;
    }

    // 围度事件
    if (data.bodyMeasureEvents.length > 0) {
      html += `<div class="keep-section"><div class="dishes-title">📏 围度记录</div>`;
      data.bodyMeasureEvents.forEach(e => {
        html += `
          <div class="keep-item">
            <div class="keep-details">
              ${e.chest_cm ? `<span>胸围 ${e.chest_cm}cm</span>` : ''}
              ${e.waist_cm ? `<span>腰围 ${e.waist_cm}cm</span>` : ''}
              ${e.hips_cm ? `<span>臀围 ${e.hips_cm}cm</span>` : ''}
              ${e.thigh_cm ? `<span>大腿 ${e.thigh_cm}cm</span>` : ''}
              ${e.calf_cm ? `<span>小腿 ${e.calf_cm}cm</span>` : ''}
              ${e.arm_cm ? `<span>上臂 ${e.arm_cm}cm</span>` : ''}
              ${e.shoulder_cm ? `<span>肩宽 ${e.shoulder_cm}cm</span>` : ''}
            </div>
            <span class="keep-meta">${e.measured_at_local || ''}</span>
          </div>
        `;
      });
      html += `</div>`;
    }

    html += `
      <div class="note-section">
        <div class="dishes-title">文字说明</div>
        <textarea id="additional-note" class="note-input" placeholder="补充说明...">${session.text || ''}</textarea>
      </div>
    </div>`;

    this.el.resultContent.innerHTML = html;
    this.el.resultTitle.textContent = 'Keep 分析结果';
    this.updateStatus(session.isSaved ? 'saved' : '');
  },

  renderDietDishes() {
    const wrap = document.getElementById('diet-dishes-container');
    if (!wrap || !this.currentDishes) return;

    if (this.isMobile()) {
      wrap.innerHTML = this.renderDietDishesMobile();
      return;
    }

    // Desktop: AI 菜式各自渲染为 block，用户菜式共享一个表格
    const aiDishes = this.currentDishes.map((d, i) => ({ ...d, originalIndex: i })).filter(d => d.source === 'ai');
    const userDishes = this.currentDishes.map((d, i) => ({ ...d, originalIndex: i })).filter(d => d.source === 'user');

    let html = '';

    // 渲染 AI 菜式
    html += aiDishes.map(d => this.renderDietDishBlockDesktop(d, d.originalIndex)).join('');

    // 渲染用户菜式（共享一个表格）
    if (userDishes.length > 0) {
      html += this.renderUserDishesTable(userDishes);
    }

    wrap.innerHTML = html;
  },

  // 用户菜式共享表格渲染
  renderUserDishesTable(userDishes) {
    const unit = this.getEnergyUnit();
    return `
      <div class="diet-user-dishes-table">
        <div class="dish-table-wrap" style="min-width: 0;">
          <table class="dish-table ingredients-table" style="min-width: 0; table-layout: fixed;">
            <thead>
              <tr>
                <th>菜式名称</th>
                <th class="num">能量(${unit})</th>
                <th class="num">蛋白(g)</th>
                <th class="num">脂肪(g)</th>
                <th class="num">碳水(g)</th>
                <th class="num">纤维(g)</th>
                <th class="num">钠(mg)</th>
                <th class="num">重量(g)</th>
                <th style="width: 36px;"></th>
              </tr>
            </thead>
            <tbody>
              ${userDishes.map(d => {
      const i = d.originalIndex;
      const energyText = this.formatEnergyFromMacros(d.protein, d.fat, d.carb);
      return `
                  <tr>
                    <td><input type="text" class="cell-input" value="${d.name}" oninput="Dashboard.updateDish(${i}, 'name', this.value)"></td>
                    <td><input type="text" class="cell-input num cell-readonly" value="${energyText}" readonly tabindex="-1"></td>
                    <td><input type="number" class="cell-input num" value="${d.protein ?? 0}" min="0" step="0.1" oninput="Dashboard.updateDish(${i}, 'protein', this.value)"></td>
                    <td><input type="number" class="cell-input num" value="${d.fat ?? 0}" min="0" step="0.1" oninput="Dashboard.updateDish(${i}, 'fat', this.value)"></td>
                    <td><input type="number" class="cell-input num" value="${d.carb ?? 0}" min="0" step="0.1" oninput="Dashboard.updateDish(${i}, 'carb', this.value)"></td>
                    <td><input type="number" class="cell-input num" value="${d.fiber ?? 0}" min="0" step="0.1" oninput="Dashboard.updateDish(${i}, 'fiber', this.value)"></td>
                    <td><input type="number" class="cell-input num" value="${d.sodium_mg ?? 0}" min="0" step="1" oninput="Dashboard.updateDish(${i}, 'sodium_mg', this.value)"></td>
                    <td><input type="number" class="cell-input num" value="${d.weight ?? 0}" min="0" step="0.1" oninput="Dashboard.updateDish(${i}, 'weight', this.value)"></td>
                    <td><button class="cell-remove" onclick="Dashboard.removeDish(${i})">×</button></td>
                  </tr>
                `;
    }).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  renderDietDishBlockDesktop(d, i) {
    const enabled = d.enabled !== false;
    const disableInputs = !enabled;
    const unit = this.getEnergyUnit();
    const totals = this.getDishTotals(d);
    const energyText = this.formatEnergyFromMacros(totals.protein, totals.fat, totals.carb);

    const ratio = this.getMacroEnergyRatio(totals.protein, totals.fat, totals.carb);
    const ratioHtml = ratio.total_kcal > 0
      ? `<span class="diet-chip">P ${ratio.p_pct}%</span><span class="diet-chip">F ${ratio.f_pct}%</span><span class="diet-chip">C ${ratio.c_pct}%</span>`
      : '';

    // AI 菜式展开/收起按钮
    const collapsed = d.source === 'ai' ? (this.dietIngredientsCollapsed?.[d.id] !== false) : false;
    const toggleBtnHtml = d.source === 'ai'
      ? `<button class="diet-toggle-btn" onclick="Dashboard.toggleIngredients(${d.id})">${collapsed ? '展开' : '收起'}</button>`
      : '';

    // 合并为单行：checkbox + 菜式名称 + 汇总统计 + P/F/C 比例 + 展开按钮
    const dishHeaderHtml = `
      <div class="diet-dish-header-combined">
        <input type="checkbox" ${enabled ? 'checked' : ''} onchange="Dashboard.toggleDishEnabled(${i}, this.checked)">
        <div class="diet-dish-name">${d.name}</div>
        <span class="diet-stat"><span class="k">能量</span><span class="v">${energyText} ${unit}</span></span>
        <span class="diet-stat"><span class="k">蛋白</span><span class="v">${totals.protein}g</span></span>
        <span class="diet-stat"><span class="k">脂肪</span><span class="v">${totals.fat}g</span></span>
        <span class="diet-stat"><span class="k">碳水</span><span class="v">${totals.carb}g</span></span>
        <span class="diet-stat"><span class="k">纤维</span><span class="v">${totals.fiber}g</span></span>
        <span class="diet-stat"><span class="k">钠</span><span class="v">${totals.sodium_mg}mg</span></span>
        <span class="diet-stat"><span class="k">重量</span><span class="v">${totals.weight}g</span></span>
        <span class="diet-chips">${ratioHtml}</span>
        ${toggleBtnHtml}
      </div>
    `;

    // Ingredients 表格（末尾列放 AI 标签）
    let ingredientsHtml = '';
    if (d.source === 'ai') {
      const hiddenClass = collapsed ? 'collapsed' : '';
      ingredientsHtml = `
        <div class="diet-ingredients-wrap ${disableInputs ? 'disabled' : ''}">
          <div class="diet-ingredients-body ${hiddenClass}">
            <div class="dish-table-wrap" style="min-width: 0;">
              <table class="dish-table ingredients-table" style="min-width: 0; table-layout: fixed;">
                <thead>
                  <tr>
                    <th>成分</th>
                    <th class="num">能量(${unit})</th>
                    <th class="num">蛋白(g)</th>
                    <th class="num">脂肪(g)</th>
                    <th class="num">碳水(g)</th>
                    <th class="num">纤维(g)</th>
                    <th class="num">钠(mg)</th>
                    <th class="num">重量(g)</th>
                    <th style="width: 36px;"></th>
                  </tr>
                </thead>
                <tbody>
                  ${(d.ingredients || []).map((ing, j) => {
        const e = this.formatEnergyFromMacros(ing.macros?.protein_g, ing.macros?.fat_g, ing.macros?.carbs_g);
        const ro = 'readonly tabindex="-1"';
        const dis = disableInputs ? 'disabled' : '';
        return `
                      <tr>
                        <td><input type="text" class="cell-input cell-readonly" value="${ing.name_zh || ''}" ${ro}></td>
                        <td><input type="text" class="cell-input num cell-readonly" value="${e}" ${ro}></td>
                        <td><input type="number" class="cell-input num" value="${ing.macros?.protein_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'protein_g', this.value)"></td>
                        <td><input type="number" class="cell-input num" value="${ing.macros?.fat_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'fat_g', this.value)"></td>
                        <td><input type="number" class="cell-input num" value="${ing.macros?.carbs_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'carbs_g', this.value)"></td>
                        <td><input type="number" class="cell-input num" value="${ing.macros?.fiber_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'fiber_g', this.value)"></td>
                        <td><input type="number" class="cell-input num" value="${ing.macros?.sodium_mg ?? 0}" min="0" step="1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'sodium_mg', this.value)"></td>
                        <td><input type="number" class="cell-input num" value="${ing.weight_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'weight_g', this.value)"></td>
                        <td><span class="diet-level-tag">AI</span></td>
                      </tr>
                    `;
      }).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      `;
    }

    return `
      <div class="diet-dish-block ${disableInputs ? 'disabled' : ''}">
        ${dishHeaderHtml}
        ${ingredientsHtml}
      </div>
    `;
  },

  renderDietDishesMobile() {
    return `
      ${this.currentDishes.map((d, i) => {
      const enabled = d.enabled !== false;
      const totals = this.getDishTotals(d);
      const unit = this.getEnergyUnit();
      const energyText = this.formatEnergyFromMacros(totals.protein, totals.fat, totals.carb);
      const disableInputs = !enabled;
      const canRemove = d.source === 'user';
      const dis = disableInputs ? 'disabled' : '';

      // AI：菜式头只读 + ingredients 可编辑
      const collapsed = this.dietIngredientsCollapsed?.[d.id] !== false;
      const toggleText = collapsed ? '展开' : '收起';
      const aiIngredients = d.source === 'ai'
        ? `
            <div class="dishes-title" style="margin-top: 10px;">Ingredients（可编辑）</div>
            <button class="diet-toggle-btn" style="margin: 6px 0 10px 0;" onclick="Dashboard.toggleIngredients(${d.id})">${toggleText}</button>
            <div class="${collapsed ? 'diet-ingredients-body collapsed' : 'diet-ingredients-body'}">
            ${(d.ingredients || []).map((ing, j) => {
          const ie = this.formatEnergyFromMacros(ing.macros?.protein_g, ing.macros?.fat_g, ing.macros?.carbs_g);
          return `
                <div class="keep-item" style="border-bottom: none; padding: 10px 0 6px 0;">
                  <div class="keep-main" style="gap: 8px;">
                    <span class="keep-sub">${ing.name_zh || ''}</span>
                    <span class="keep-details"><span>能量 ${ie} ${unit}</span></span>
                  </div>
                </div>
                <div class="dish-row" style="grid-template-columns: repeat(3, 1fr); gap: 8px; border-bottom: none;">
                  <input type="number" class="dish-input number" placeholder="蛋白(g)" value="${ing.macros?.protein_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'protein_g', this.value)">
                  <input type="number" class="dish-input number" placeholder="脂肪(g)" value="${ing.macros?.fat_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'fat_g', this.value)">
                  <input type="number" class="dish-input number" placeholder="碳水(g)" value="${ing.macros?.carbs_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'carbs_g', this.value)">
                </div>
                <div class="dish-row" style="grid-template-columns: repeat(3, 1fr); gap: 8px; border-bottom: none;">
                  <input type="number" class="dish-input number" placeholder="纤维(g)" value="${ing.macros?.fiber_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'fiber_g', this.value)">
                  <input type="number" class="dish-input number" placeholder="钠(mg)" value="${ing.macros?.sodium_mg ?? 0}" min="0" step="1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'sodium_mg', this.value)">
                  <input type="number" class="dish-input number" placeholder="重量(g)" value="${ing.weight_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'weight_g', this.value)">
                </div>
              `;
        }).join('')}
            </div>
          `
        : '';

      // 用户新增：保持汇总编辑
      const userEditor = d.source === 'user'
        ? `
            <div class="dish-row" style="grid-template-columns: repeat(3, 1fr); gap: 8px; border-bottom: none; padding-top: 10px;">
              <input type="number" class="dish-input number" placeholder="蛋白(g)" value="${d.protein ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateDish(${i}, 'protein', this.value)">
              <input type="number" class="dish-input number" placeholder="脂肪(g)" value="${d.fat ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateDish(${i}, 'fat', this.value)">
              <input type="number" class="dish-input number" placeholder="碳水(g)" value="${d.carb ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateDish(${i}, 'carb', this.value)">
            </div>
            <div class="dish-row" style="grid-template-columns: repeat(3, 1fr); gap: 8px; border-bottom: none;">
              <input type="number" class="dish-input number" placeholder="纤维(g)" value="${d.fiber ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateDish(${i}, 'fiber', this.value)">
              <input type="number" class="dish-input number" placeholder="钠(mg)" value="${d.sodium_mg ?? 0}" min="0" step="1" ${dis} oninput="Dashboard.updateDish(${i}, 'sodium_mg', this.value)">
              <input type="number" class="dish-input number" placeholder="重量(g)" value="${d.weight ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateDish(${i}, 'weight', this.value)">
            </div>
          `
        : '';

      return `
          <div class="keep-section" style="${disableInputs ? 'opacity: 0.55;' : ''}">
            <div style="display:flex; align-items:center; justify-content: space-between; gap: 10px;">
              <div style="display:flex; align-items:center; gap: 10px; min-width: 0;">
                <input type="checkbox" ${enabled ? 'checked' : ''} onchange="Dashboard.toggleDishEnabled(${i}, this.checked)">
                ${d.source === 'user'
          ? `<input type="text" class="dish-input name" style="flex:1; min-width: 0;" value="${d.name}" ${dis} oninput="Dashboard.updateDish(${i}, 'name', this.value)">`
          : `<div style="flex:1; min-width: 0; font-weight: 600; overflow:hidden; text-overflow: ellipsis; white-space: nowrap;">${d.name}</div>`
        }
              </div>
              ${canRemove ? `<button class="cell-remove" onclick="Dashboard.removeDish(${i})">×</button>` : `<span class="text-muted" style="font-size:0.75rem;">AI</span>`}
            </div>

            <div class="keep-item" style="border-bottom:none; padding-bottom: 0;">
              <div class="keep-details" style="gap: 8px;">
                <span>能量 ${energyText} ${unit}</span>
                <span>蛋白 ${totals.protein}g</span>
                <span>脂肪 ${totals.fat}g</span>
                <span>碳水 ${totals.carb}g</span>
                <span>纤维 ${totals.fiber}g</span>
                <span>钠 ${totals.sodium_mg}mg</span>
                <span>重量 ${totals.weight}g</span>
              </div>
            </div>

            ${d.source === 'user' ? userEditor : aiIngredients}
          </div>
        `;
    }).join('')}
    `;
  },

  formatEnergyFromMacros(proteinG, fatG, carbsG) {
    const kcal = this.macrosToKcal(proteinG, fatG, carbsG);
    const unit = this.getEnergyUnit();
    if (unit === 'kcal') return String(Math.round(kcal));
    return String(Math.round(this.kcalToKJ(kcal)));
  },

  toggleDishEnabled(index, enabled) {
    if (this.currentDishes && this.currentDishes[index]) {
      this.currentDishes[index].enabled = Boolean(enabled);
      this.recalculateDietSummary(true);
      this.renderDietDishes();
    }
  },

  renderAdvice(adviceText) {
    const section = document.getElementById('advice-section');
    const textEl = document.getElementById('advice-text');
    if (section && textEl) {
      textEl.textContent = adviceText;
      section.classList.remove('hidden');
    }
  },

  // ========== 编辑操作 ==========

  updateDish(index, field, value) {
    if (this.currentDishes && this.currentDishes[index]) {
      // AI 菜式：菜式层级不可编辑（只允许编辑 ingredients）
      if (this.currentDishes[index].source === 'ai') {
        return;
      }
      this.currentDishes[index][field] = field === 'name' ? value : (parseFloat(value) || 0);
      this.recalculateDietSummary(true);
      // 重新渲染以更新能量显示
      this.renderDietDishes();
    }
  },

  updateIngredient(dishIndex, ingIndex, field, value) {
    const dish = this.currentDishes?.[dishIndex];
    if (!dish || dish.source !== 'ai') return;
    const ing = dish.ingredients?.[ingIndex];
    if (!ing) return;

    if (field === 'weight_g') {
      ing.weight_g = parseFloat(value) || 0;
    } else {
      ing.macros = ing.macros || {};
      ing.macros[field] = parseFloat(value) || 0;
    }

    this.recalculateDietSummary(true);
    this.renderDietDishes();
  },

  toggleIngredients(dishId) {
    const curr = this.dietIngredientsCollapsed?.[dishId];
    // 默认折叠：undefined 视为 true
    const next = curr === false ? true : false;
    this.dietIngredientsCollapsed[dishId] = next;
    this.renderDietDishes();
  },

  addDish() {
    if (!this.currentDishes) this.currentDishes = [];
    this.currentDishes.push({
      id: Date.now(),
      name: '新菜式',
      weight: 0,
      protein: 0,
      fat: 0,
      carb: 0,
      fiber: 0,
      sodium_mg: 0,
      enabled: true,
      source: 'user',
    });
    this.renderDietDishes();
    this.recalculateDietSummary(true);
  },

  removeDish(index) {
    if (this.currentDishes) {
      const d = this.currentDishes[index];
      if (d && d.source !== 'user') {
        this.addMessage('AI 识别的菜式不支持删除，可取消勾选以停用', 'assistant');
        return;
      }
      this.currentDishes.splice(index, 1);
      this.renderDietDishes();
      this.recalculateDietSummary(true);
    }
  },

  recalculateDietSummary(markModified) {
    const dishes = this.currentDishes || [];
    const totals = {
      totalEnergyKcal: 0,
      totalProtein: 0,
      totalFat: 0,
      totalCarb: 0,
      totalFiber: 0,
      totalSodiumMg: 0,
      totalWeightG: 0,
    };

    for (const d of dishes) {
      if (d.enabled === false) continue;

      const t = this.getDishTotals(d);
      totals.totalEnergyKcal += this.macrosToKcal(t.protein, t.fat, t.carb);
      totals.totalProtein += t.protein;
      totals.totalFat += t.fat;
      totals.totalCarb += t.carb;
      totals.totalFiber += t.fiber;
      totals.totalSodiumMg += t.sodium_mg;
      totals.totalWeightG += t.weight;
    }

    // 统一保留位数：热量/钠为整数；其他为 0.1
    const unit = this.getEnergyUnit();
    const totalEnergyDisplay = unit === 'kcal'
      ? Math.round(totals.totalEnergyKcal)
      : Math.round(this.kcalToKJ(totals.totalEnergyKcal));

    this.currentDietTotals = {
      totalEnergy: totalEnergyDisplay,
      totalProtein: Math.round(totals.totalProtein * 10) / 10,
      totalFat: Math.round(totals.totalFat * 10) / 10,
      totalCarb: Math.round(totals.totalCarb * 10) / 10,
      totalFiber: Math.round(totals.totalFiber * 10) / 10,
      totalSodiumMg: Math.round(totals.totalSodiumMg),
      totalWeightG: Math.round(totals.totalWeightG),
    };

    // 更新总览 DOM
    const setText = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.textContent = String(v);
    };
    setText('sum-total-energy', this.currentDietTotals.totalEnergy);
    setText('sum-energy-unit', unit);
    setText('sum-total-protein', this.currentDietTotals.totalProtein);
    setText('sum-total-fat', this.currentDietTotals.totalFat);
    setText('sum-total-carb', this.currentDietTotals.totalCarb);
    setText('sum-total-fiber', this.currentDietTotals.totalFiber);
    setText('sum-total-sodium', this.currentDietTotals.totalSodiumMg);
    setText('sum-total-weight', this.currentDietTotals.totalWeightG);

    const subtitle = document.getElementById('diet-subtitle');
    if (subtitle && this.currentDietMeta) {
      subtitle.textContent = `${dishes.length} 种食物 · ${this.currentDietMeta.dietTime || ''}`;
    }

    if (markModified) this.markModified();
  },

  markModified() {
    if (this.currentSession) {
      this.currentSession.isSaved = false;
    }
    this.updateStatus('modified');
    this.updateButtonStates(this.currentSession);
  },

  collectEditedData() {
    // 目前只对 diet 结果做“确认面板编辑”
    if (this.mode !== 'diet') return {};

    if (!this.currentDietTotals) {
      this.recalculateDietSummary(false);
    }

    const totals = this.currentDietTotals || {};
    const mealName = this.currentDietMeta?.mealName || '饮食记录';
    const dietTime = this.currentDietMeta?.dietTime || '';
    const unit = this.getEnergyUnit();
    const totalEnergyKcal = unit === 'kcal'
      ? (Number(totals.totalEnergy) || 0)
      : this.kJToKcal(Number(totals.totalEnergy) || 0);

    const editedDishes = (this.currentDishes || []).filter(d => d.enabled !== false).map(d => {
      // A. AI 识别菜式：保留 ingredients 结构，直接保存“逐成分编辑后的数据”
      if (d.source === 'ai' && Array.isArray(d.ingredients) && d.ingredients.length > 0) {
        return {
          standard_name: d.name,
          ingredients: (d.ingredients || []).map(ing => ({
            name_zh: ing.name_zh,
            weight_g: Number(ing.weight_g) || 0,
            weight_method: ing.weight_method,
            data_source: ing.data_source,
            energy_kj: Math.round(this.kcalToKJ(this.macrosToKcal(
              ing.macros?.protein_g,
              ing.macros?.fat_g,
              ing.macros?.carbs_g
            )) * 1000) / 1000,
            macros: {
              protein_g: Number(ing.macros?.protein_g) || 0,
              fat_g: Number(ing.macros?.fat_g) || 0,
              carbs_g: Number(ing.macros?.carbs_g) || 0,
              fiber_g: Number(ing.macros?.fiber_g) || 0,
              sodium_mg: Number(ing.macros?.sodium_mg) || 0,
            },
          })),
        };
      }

      // B. 用户新增菜式：用单一 ingredient 表示（结构保持一致）
      return {
        standard_name: d.name,
        ingredients: [
          {
            name_zh: d.name,
            weight_g: Number(d.weight) || 0,
            weight_method: "user_edit",
            data_source: "user_edit",
            energy_kj: Math.round(this.kcalToKJ(this.macrosToKcal(d.protein, d.fat, d.carb)) * 1000) / 1000,
            macros: {
              protein_g: Number(d.protein) || 0,
              fat_g: Number(d.fat) || 0,
              carbs_g: Number(d.carb) || 0,
              fiber_g: Number(d.fiber) || 0,
              sodium_mg: Number(d.sodium_mg) || 0,
            },
          }
        ],
      };
    });

    return {
      meal_summary: {
        meal_name: mealName,
        diet_time: dietTime,
        total_energy_kj: Math.round(this.kcalToKJ(totalEnergyKcal) * 1000) / 1000,
        total_protein_g: Number(totals.totalProtein) || 0,
        total_fat_g: Number(totals.totalFat) || 0,
        total_carbs_g: Number(totals.totalCarb) || 0,
        total_fiber_g: Number(totals.totalFiber) || 0,
        total_sodium_mg: Number(totals.totalSodiumMg) || 0,
      },
      dishes: editedDishes,
    };
  },

  getDishTotals(dish) {
    // AI：按 ingredients 加总；User：按 dish 汇总字段
    if (dish?.source === 'ai') {
      const ings = dish.ingredients || [];
      const sum = (fn) => ings.reduce((a, x) => a + (fn(x) || 0), 0);
      const w = sum(x => Number(x.weight_g) || 0);
      const p = sum(x => Number(x.macros?.protein_g) || 0);
      const f = sum(x => Number(x.macros?.fat_g) || 0);
      const c = sum(x => Number(x.macros?.carbs_g) || 0);
      const fib = sum(x => Number(x.macros?.fiber_g) || 0);
      const na = sum(x => Number(x.macros?.sodium_mg) || 0);
      return {
        weight: Math.round(w * 10) / 10,
        protein: Math.round(p * 10) / 10,
        fat: Math.round(f * 10) / 10,
        carb: Math.round(c * 10) / 10,
        fiber: Math.round(fib * 10) / 10,
        sodium_mg: Math.round(na),
      };
    }
    return {
      weight: Math.round((Number(dish?.weight) || 0) * 10) / 10,
      protein: Math.round((Number(dish?.protein) || 0) * 10) / 10,
      fat: Math.round((Number(dish?.fat) || 0) * 10) / 10,
      carb: Math.round((Number(dish?.carb) || 0) * 10) / 10,
      fiber: Math.round((Number(dish?.fiber) || 0) * 10) / 10,
      sodium_mg: Math.round(Number(dish?.sodium_mg) || 0),
    };
  },

  getMacroEnergyRatio(proteinG, fatG, carbsG) {
    const p = (Number(proteinG) || 0) * 4;
    const f = (Number(fatG) || 0) * 9;
    const c = (Number(carbsG) || 0) * 4;
    const t = p + f + c;
    if (t <= 0) {
      return { total_kcal: 0, p_pct: 0, f_pct: 0, c_pct: 0 };
    }
    return {
      total_kcal: t,
      p_pct: Math.round((p / t) * 100),
      f_pct: Math.round((f / t) * 100),
      c_pct: Math.round((c / t) * 100),
    };
  },

  // ========== Profile（前端先行） ==========

  getDefaultProfile() {
    return {
      timezone: 'Asia/Shanghai',
      diet: {
        energy_unit: 'kJ',
        goal: 'fat_loss',
        daily_energy_kj_target: 6273,
        protein_g_target: 110,
        fat_g_target: 50,
        carbs_g_target: 150,
        sodium_mg_target: 2000,
      },
      keep: {
        weight_kg_target: 0,
        body_fat_pct_target: 0,
        dimensions_cm_target: {
          chest_cm: 0,
          waist_cm: 0,
          hips_cm: 0,
        }
      }
    };
  },

  loadProfile() {
    try {
      const raw = localStorage.getItem('dk_profile_v1');
      if (!raw) return this.getDefaultProfile();
      const parsed = JSON.parse(raw);
      return Object.assign(this.getDefaultProfile(), parsed || {});
    } catch (e) {
      return this.getDefaultProfile();
    }
  },

  saveProfileLocal(profile) {
    localStorage.setItem('dk_profile_v1', JSON.stringify(profile));
    this.profile = profile;
  },

  renderProfileView() {
    const p = this.profile || this.getDefaultProfile();
    this.el.resultTitle.textContent = 'Profile 设置';
    this.updateStatus('');
    this.el.resultFooter.classList.add('hidden');

    this.el.resultContent.innerHTML = `
      <div class="result-card">
        <div class="result-card-header">
          <div class="result-icon">👤</div>
          <div>
            <div class="result-card-title">用户 Profile</div>
            <div class="result-card-subtitle">前端先行：本地保存 + 占位提交请求（后端业务稍后接入）</div>
          </div>
        </div>

        <div class="dish-row" style="grid-template-columns: 1fr 1fr; gap: 12px;">
          <div>
            <div class="dishes-title">时区</div>
            <select id="profile-timezone" class="dish-input" style="width: 100%;">
              ${this.renderTimezoneOptions(p.timezone)}
            </select>
          </div>
          <div>
            <div class="dishes-title">能量显示单位</div>
            <select id="energy-unit" class="dish-input" style="width: 100%;" onchange="Dashboard.setEnergyUnit(this.value)">
              <option value="kJ" ${this.getEnergyUnit() === 'kJ' ? 'selected' : ''}>kJ（默认）</option>
              <option value="kcal" ${this.getEnergyUnit() === 'kcal' ? 'selected' : ''}>kcal</option>
            </select>
          </div>
        </div>

        <div class="dishes-title">Diet 目标</div>
        <div class="dish-row" style="grid-template-columns: 1fr 1fr; gap: 12px;">
          <div>
            <div class="nutrition-label" style="text-align:left;">目标类型</div>
            <select id="diet-goal" class="dish-input" style="width: 100%;">
              ${this.renderDietGoalOptions(p.diet?.goal)}
            </select>
          </div>
          <div>
            <div class="nutrition-label" style="text-align:left;">每日能量目标 (kJ)</div>
            <input id="diet-energy-kj" type="number" class="dish-input number" value="${p.diet?.daily_energy_kj_target ?? 0}">
          </div>
        </div>
        <div class="dish-row" style="grid-template-columns: repeat(3, 1fr); gap: 12px;">
          <div>
            <div class="nutrition-label" style="text-align:left;">蛋白质 (g)</div>
            <input id="diet-protein-g" type="number" class="dish-input number" value="${p.diet?.protein_g_target ?? 0}" step="0.1">
          </div>
          <div>
            <div class="nutrition-label" style="text-align:left;">脂肪 (g)</div>
            <input id="diet-fat-g" type="number" class="dish-input number" value="${p.diet?.fat_g_target ?? 0}" step="0.1">
          </div>
          <div>
            <div class="nutrition-label" style="text-align:left;">碳水 (g)</div>
            <input id="diet-carbs-g" type="number" class="dish-input number" value="${p.diet?.carbs_g_target ?? 0}" step="0.1">
          </div>
        </div>
        <div class="dish-row" style="grid-template-columns: 1fr 1fr; gap: 12px;">
          <div>
            <div class="nutrition-label" style="text-align:left;">钠 (mg)</div>
            <input id="diet-sodium-mg" type="number" class="dish-input number" value="${p.diet?.sodium_mg_target ?? 0}" step="1">
          </div>
          <div>
            <div class="nutrition-label" style="text-align:left;">（预留）膳食纤维 (g)</div>
            <input id="diet-fiber-g" type="number" class="dish-input number" value="${p.diet?.fiber_g_target ?? 0}" step="0.1">
          </div>
        </div>

        <div class="dishes-title" style="margin-top: 18px;">Keep 目标</div>
        <div class="dish-row" style="grid-template-columns: 1fr 1fr; gap: 12px;">
          <div>
            <div class="nutrition-label" style="text-align:left;">体重 (kg)</div>
            <input id="keep-weight-kg" type="number" class="dish-input number" value="${p.keep?.weight_kg_target ?? 0}" step="0.1">
          </div>
          <div>
            <div class="nutrition-label" style="text-align:left;">体脂率 (%)</div>
            <input id="keep-bodyfat-pct" type="number" class="dish-input number" value="${p.keep?.body_fat_pct_target ?? 0}" step="0.1">
          </div>
        </div>

        <div class="dishes-title" style="margin-top: 12px;">围度目标 (cm)</div>
        <div class="dish-row" style="grid-template-columns: repeat(3, 1fr); gap: 12px;">
          <div>
            <div class="nutrition-label" style="text-align:left;">胸围</div>
            <input id="keep-chest-cm" type="number" class="dish-input number" value="${p.keep?.dimensions_cm_target?.chest_cm ?? 0}" step="0.1">
          </div>
          <div>
            <div class="nutrition-label" style="text-align:left;">腰围</div>
            <input id="keep-waist-cm" type="number" class="dish-input number" value="${p.keep?.dimensions_cm_target?.waist_cm ?? 0}" step="0.1">
          </div>
          <div>
            <div class="nutrition-label" style="text-align:left;">臀围</div>
            <input id="keep-hips-cm" type="number" class="dish-input number" value="${p.keep?.dimensions_cm_target?.hips_cm ?? 0}" step="0.1">
          </div>
        </div>

        <div class="result-footer" style="padding: 0; border-top: none; margin-top: 18px; justify-content: flex-end;">
          <button class="btn btn-secondary" onclick="Dashboard.switchView('analysis')">返回分析</button>
          <button class="btn btn-primary" onclick="Dashboard.saveProfile()">保存 Profile</button>
        </div>
      </div>
    `;
  },

  renderTimezoneOptions(selected) {
    const zones = [
      { value: 'Asia/Shanghai', label: '中国（Asia/Shanghai）' },
      { value: 'Asia/Hong_Kong', label: '中国香港（Asia/Hong_Kong）' },
      { value: 'Asia/Taipei', label: '中国台北（Asia/Taipei）' },
      { value: 'Asia/Tokyo', label: '日本（Asia/Tokyo）' },
      { value: 'Asia/Singapore', label: '新加坡（Asia/Singapore）' },
      { value: 'Europe/London', label: '英国（Europe/London）' },
      { value: 'Europe/Berlin', label: '德国（Europe/Berlin）' },
      { value: 'America/Los_Angeles', label: '美国西海岸（America/Los_Angeles）' },
      { value: 'America/New_York', label: '美国东海岸（America/New_York）' },
    ];
    return zones.map(z => `<option value="${z.value}" ${z.value === selected ? 'selected' : ''}>${z.label}</option>`).join('');
  },

  renderDietGoalOptions(selected) {
    const goals = [
      { value: 'fat_loss', label: '减脂' },
      { value: 'maintain', label: '维持' },
      { value: 'muscle_gain', label: '增肌' },
      { value: 'health', label: '健康' },
    ];
    const sel = selected || 'fat_loss';
    return goals.map(g => `<option value="${g.value}" ${g.value === sel ? 'selected' : ''}>${g.label}</option>`).join('');
  },

  async saveProfile() {
    const getNum = (id) => parseFloat(document.getElementById(id)?.value) || 0;
    const getStr = (id) => String(document.getElementById(id)?.value || '');

    const profile = {
      timezone: getStr('profile-timezone'),
      diet: {
        energy_unit: getStr('energy-unit') || 'kJ',
        goal: getStr('diet-goal'),
        daily_energy_kj_target: getNum('diet-energy-kj'),
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

    // 立即生效：若在分析视图，更新汇总与明细能量显示
    if (this.view !== 'analysis') return;
    if (this.currentSession && this.currentSession.versions.length > 0) {
      this.recalculateDietSummary(false);
      this.renderDietDishes();
    }
  },

  // ========== 保存 ==========

  async saveRecord() {
    if (!this.currentSession) return;

    const session = this.currentSession;
    const isUpdate = session.isSaved && session.savedRecordId;

    try {
      this.el.saveBtn.disabled = true;
      this.el.saveBtn.textContent = isUpdate ? '更新中...' : '保存中...';

      let result;

      if (session.mode === 'diet') {
        // Diet 模式
        const editedData = this.collectEditedData();
        editedData.image_hashes = session.imageHashes || [];
        if (isUpdate) {
          editedData.record_id = session.savedRecordId;
        }
        result = await API.saveDiet(editedData);
      } else {
        // Keep 模式
        const version = session.versions[session.currentVersion - 1];
        if (!version) {
          throw new Error('没有可保存的分析结果');
        }

        const keepData = {
          ...version.rawResult,
          image_hashes: session.imageHashes || [],
        };
        if (isUpdate) {
          keepData.record_id = session.savedRecordId;
        }

        // 确定事件类型
        const eventType = this.determineKeepEventType(version.parsedData);
        result = await API.saveKeep(keepData, eventType);
      }

      // 如果后端返回了 record_id，保存它
      if (result.saved_record && result.saved_record.record_id) {
        session.savedRecordId = result.saved_record.record_id;
      }

      session.isSaved = true;
      if (session.mode === 'diet') {
        session.savedData = JSON.parse(JSON.stringify(this.collectEditedData()));
      }

      this.updateStatus('saved');
      this.addMessage(isUpdate ? '✓ 记录已更新' : '✓ 记录已保存', 'assistant');
      this.updateButtonStates(session);

      // 只有首次保存才添加历史项
      if (!isUpdate) {
        this.addHistoryItem(session);
      }

    } catch (error) {
      this.addMessage(`${isUpdate ? '更新' : '保存'}失败: ${error.message}`, 'assistant');
    } finally {
      this.el.saveBtn.disabled = false;
      this.updateButtonStates(session);
    }
  },

  // 确定 Keep 事件类型
  determineKeepEventType(parsedData) {
    if (parsedData.scaleEvents && parsedData.scaleEvents.length > 0) {
      return 'scale';
    }
    if (parsedData.sleepEvents && parsedData.sleepEvents.length > 0) {
      return 'sleep';
    }
    if (parsedData.bodyMeasureEvents && parsedData.bodyMeasureEvents.length > 0) {
      return 'dimensions';
    }
    return 'scale';  // 默认
  },

  // ========== 状态管理 ==========

  showLoading() {
    // 仅状态提示：不遮挡/不替换整个确认面板内容
    this.updateStatus('loading');
    if (this.el.resultFooter) {
      this.el.resultFooter.classList.add('hidden');
    }
  },

  showError(message) {
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

  loadHistory() {
    const today = new Date().toLocaleDateString('zh-CN');
    this.el.historyList.innerHTML = `
      <div class="history-section-title">今天 ${today}</div>
      <div class="history-item placeholder">暂无记录</div>
    `;
  },

  addHistoryItem(session) {
    const list = this.el.historyList;
    const placeholder = list.querySelector('.placeholder');
    if (placeholder) placeholder.remove();

    const item = document.createElement('div');
    item.className = 'history-item';
    item.dataset.sessionId = session.id;

    if (session.mode === 'diet') {
      const ver = session.versions[session.versions.length - 1];
      item.textContent = `${ver.parsedData.summary.totalEnergy} kcal`;
    } else {
      item.textContent = 'Keep 记录';
    }

    item.onclick = () => this.selectSession(session.id);
    list.appendChild(item);
  },
};

document.addEventListener('DOMContentLoaded', () => Dashboard.init());
