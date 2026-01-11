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

  // 待上传的图片
  pendingImages: [],

  // 分析会话列表 (每个会话可以有多个版本)
  sessions: [],

  // 当前选中的 session
  currentSession: null,

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
    };
  },

  bindEvents() {
    // 模式切换
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.addEventListener('click', () => this.switchMode(btn.dataset.mode));
    });

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
  },

  switchMode(mode) {
    this.mode = mode;
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    // 切换模式时清空右侧
    this.clearResult();
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

    // 获取附加的文字说明
    const additionalNote = document.getElementById('additional-note')?.value.trim() || '';
    const fullNote = [session.text, additionalNote].filter(Boolean).join('\n');

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

    const dishes = [];

    (data.dishes || []).forEach((dish, i) => {
      let dishWeight = 0;
      let dishEnergy = 0;
      let dishProtein = 0;
      let dishFat = 0;
      let dishCarb = 0;

      (dish.ingredients || []).forEach(ing => {
        const weight = ing.weight_g || 0;
        dishWeight += weight;

        if (ing.macros) {
          dishProtein += ing.macros.protein_g || 0;
          dishFat += ing.macros.fat_g || 0;
          dishCarb += ing.macros.carbs_g || 0;
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
        energy: Math.round(dishEnergy),
        protein: Math.round(dishProtein * 10) / 10,
        fat: Math.round(dishFat * 10) / 10,
        carb: Math.round(dishCarb * 10) / 10,
      });

      totalEnergy += dishEnergy;
      totalProtein += dishProtein;
      totalFat += dishFat;
      totalCarb += dishCarb;
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

    // 获取当前版本的 user_note
    const currentNote = version.userNote || session.text || '';

    this.el.resultContent.innerHTML = `
      <div class="result-card">
        <div class="result-card-header">
          <div class="result-icon">🍽️</div>
          <div>
            <div class="result-card-title">${summary.mealName}</div>
            <div class="result-card-subtitle">${this.currentDishes.length} 种食物 · ${summary.dietTime || ''}</div>
          </div>
          ${session.versions.length > 1 ? `
            <div class="version-nav">
              <button class="version-btn" onclick="Dashboard.switchVersion(-1)" ${session.currentVersion <= 1 ? 'disabled' : ''}>◀</button>
              <span class="version-label">v${version.number}/${session.versions.length}</span>
              <button class="version-btn" onclick="Dashboard.switchVersion(1)" ${session.currentVersion >= session.versions.length ? 'disabled' : ''}>▶</button>
            </div>
          ` : ''}
        </div>
        
        <div class="nutrition-grid">
          <div class="nutrition-item">
            <input type="number" class="nutrition-input" id="total-energy" value="${summary.totalEnergy}" onchange="Dashboard.markModified()">
            <div class="nutrition-label">千卡</div>
          </div>
          <div class="nutrition-item">
            <input type="number" class="nutrition-input" id="total-protein" value="${summary.totalProtein}" step="0.1" onchange="Dashboard.markModified()">
            <div class="nutrition-label">蛋白质 (g)</div>
          </div>
          <div class="nutrition-item">
            <input type="number" class="nutrition-input" id="total-fat" value="${summary.totalFat}" step="0.1" onchange="Dashboard.markModified()">
            <div class="nutrition-label">脂肪 (g)</div>
          </div>
          <div class="nutrition-item">
            <input type="number" class="nutrition-input" id="total-carb" value="${summary.totalCarb}" step="0.1" onchange="Dashboard.markModified()">
            <div class="nutrition-label">碳水 (g)</div>
          </div>
        </div>
        
        <div class="dishes-section">
          <div class="dishes-title">食物明细</div>
          <div id="dishes-list"></div>
          <button class="add-dish-btn" onclick="Dashboard.addDish()">+ 添加食物</button>
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

    this.renderDishList();
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

  renderDishList() {
    const container = document.getElementById('dishes-list');
    if (!container || !this.currentDishes) return;

    container.innerHTML = this.currentDishes.map((d, i) => `
      <div class="dish-row" data-index="${i}">
        <input type="text" class="dish-input name" value="${d.name}" onchange="Dashboard.updateDish(${i}, 'name', this.value)">
        <input type="number" class="dish-input number" value="${d.weight}" placeholder="克" onchange="Dashboard.updateDish(${i}, 'weight', this.value)">
        <input type="number" class="dish-input number" value="${d.energy}" placeholder="kcal" onchange="Dashboard.updateDish(${i}, 'energy', this.value)">
        <button class="dish-remove" onclick="Dashboard.removeDish(${i})">×</button>
      </div>
    `).join('');
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
      this.currentDishes[index][field] = field === 'name' ? value : parseFloat(value) || 0;
      this.markModified();
    }
  },

  addDish() {
    if (!this.currentDishes) this.currentDishes = [];
    this.currentDishes.push({ id: Date.now(), name: '新食物', weight: 0, energy: 0 });
    this.renderDishList();
    this.markModified();
  },

  removeDish(index) {
    if (this.currentDishes) {
      this.currentDishes.splice(index, 1);
      this.renderDishList();
      this.markModified();
    }
  },

  markModified() {
    if (this.currentSession) {
      this.currentSession.isSaved = false;
    }
    this.updateStatus('modified');
    this.updateButtonStates(this.currentSession);
  },

  collectEditedData() {
    return {
      meal_summary: {
        total_energy: parseFloat(document.getElementById('total-energy')?.value) || 0,
        total_protein: parseFloat(document.getElementById('total-protein')?.value) || 0,
        total_fat: parseFloat(document.getElementById('total-fat')?.value) || 0,
        total_carb: parseFloat(document.getElementById('total-carb')?.value) || 0,
      },
      dishes: (this.currentDishes || []).map(d => ({
        name: d.name,
        estimated_weight: d.weight,
        estimated_energy: d.energy,
      })),
    };
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
    this.el.resultContent.innerHTML = `
      <div class="empty-state">
        <div class="loading-spinner"></div>
        <p style="margin-top: 16px;">正在分析中...</p>
      </div>
    `;
    this.el.resultFooter.classList.add('hidden');
    this.updateStatus('');
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
    this.el.resultContent.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📊</div>
        <h3>等待分析</h3>
        <p>上传图片或输入描述开始分析</p>
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
