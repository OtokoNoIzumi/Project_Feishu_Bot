/**
 * Diet 渲染模块
 *
 * 负责 Diet 分析结果的 HTML 渲染
 * 包括：桌面端表格、移动端列表、营养标签区域等
 * 挂载到 Dashboard 实例运行
 */

const DietRenderModule = {
  renderDietResult(session, version) {
    const data = version.parsedData;
    const summary = data.summary;

    // 缓存当前 dishes 用于编辑
    this.currentDishes = [...data.dishes];
    this.currentLabels = [...(data.capturedLabels || [])];  // 缓存营养标签用于编辑
    this.currentDietMeta = {
      mealName: summary.mealName || '饮食记录',
      dietTime: summary.dietTime || '',
      occurredAt: (() => {
        // 1. 优先使用 Card 数据，其次回退到 Session 创建时间
        let val = data.occurredAt;
        if (!val && session.createdAt) {
          val = session.createdAt;
        }
        if (!val) return null;

        // 2. 格式清洗：如果是 UTC 格式 (Z 或 +00:00)，转为本地时间字符串
        // 这能修复旧数据被污染为 UTC 格式的问题，也能处理 session.createdAt 是 UTC 的情况
        if (typeof val === 'string' && (val.endsWith('Z') || val.includes('+00:00'))) {
          try {
            const dt = new Date(val);
            // 简单粗暴：利用 toISOString 的时区偏移技巧获取本地时间的 string representation
            const offset = dt.getTimezoneOffset() * 60000;
            const local = new Date(dt.getTime() - offset);
            return local.toISOString().slice(0, -1);
          } catch (e) {
            return val; // 解析失败则原样返回
          }
        }
        return val;
      })(),
    };

    // [Fix] 同步基准数据：如果 savedData 中的 occurred_at 为空（旧卡片），
    // 强制同步为刚刚计算出的本地时间，避免页面一加载就显示 "更新记录"
    if (session.savedData && !session.savedData.occurred_at && this.currentDietMeta.occurredAt) {
      session.savedData.occurred_at = this.currentDietMeta.occurredAt;
    }

    // [Fix] 历史卡片首次加载时 savedData 可能为空，导致被误判为 "已修改"
    // 此时应立即构建 savedData 作为基准
    if (session.isSaved && !session.savedData && typeof this.collectEditedData === 'function') {
      // 必须先计算 currentDietTotals，否则 collectEditedData 拿不到总数据
      this.recalculateDietSummary(false);
      try {
        session.savedData = JSON.parse(JSON.stringify(this.collectEditedData()));
      } catch (e) {
        console.warn('Failed to init savedData:', e);
      }
    } else {
      this.recalculateDietSummary(false);
    }

    // 获取当前版本的 user_note
    const currentNote = version.userNote || session.text || '';

    const unit = this.getEnergyUnit();
    // currentDietTotals.totalEnergy 内部统一为 kcal，这里只做显示换算
    // 强制取整：无论是 kcal 还是 kJ，都显示整数
    const displayTotalEnergy = unit === 'kcal'
      ? Math.round(Number(this.currentDietTotals.totalEnergy) || 0)
      : Math.round(EnergyUtils.kcalToKJ(Number(this.currentDietTotals.totalEnergy) || 0));

    this.el.resultContent.innerHTML = `
      <div class="result-card">
        <div class="result-card-header">
          <div class="result-icon-container">${window.IconManager ? window.IconManager.render('meal') : '<img src="css/icons/bowl.png" class="hand-icon icon-sticker">'}</div>
          <div>
            <div class="result-card-title">${summary.mealName}</div>
            <div class="result-card-subtitle" id="diet-subtitle" style="display:flex; flex-wrap:wrap; align-items:center; column-gap: 8px; row-gap: 6px; margin-top: 4px;">
              <span id="diet-dish-count" style="white-space:nowrap;">${this.currentDishes.length} 种食物</span>
              <span style="color:var(--color-text-muted); opacity: 0.5;">·</span>
              ${this.renderMealTypeSelector(summary.mealName, summary.dietTime)}
              <button class="btn-text-icon" onclick="ProteinReportModule.render(Dashboard.currentDietTotals)" title="查看蛋白质价值评估" style="font-size: 0.85em; color: var(--color-accent-primary, #d97757); background: rgba(217, 119, 87, 0.1); padding: 2px 8px; border-radius: 12px; border:none; cursor: pointer; white-space:nowrap;">
                📊 蛋白效力图
              </button>
            </div>
          </div>
          ${session.versions.length > 1 ? `
            <div class="version-nav">
              <button class="version-btn" onclick="Dashboard.switchVersion(-1)" ${session.currentVersion <= 1 ? 'disabled' : ''}>◀</button>
              <span class="version-label">v${version.number || '?'}/${session.versions.length}</span>
              <button class="version-btn" onclick="Dashboard.switchVersion(1)" ${session.currentVersion >= session.versions.length ? 'disabled' : ''}>▶</button>
            </div>
          ` : ''}
        </div>

        <div class="nutrition-summary-compact">
          <div class="summary-energy">
            <div class="value">
              <span id="sum-total-energy">${displayTotalEnergy}</span>
              <span id="sum-energy-unit">${unit}</span>
            </div>
            <div class="label">本次总能量</div>
          </div>
          <div class="summary-macros-inline">
            <span class="macro-chip"><span class="k">蛋白</span><span class="v" id="sum-total-protein">${this.currentDietTotals.totalProtein}</span>g</span>
            <span class="macro-chip"><span class="k">脂肪</span><span class="v" id="sum-total-fat">${this.currentDietTotals.totalFat}</span>g</span>
            <span class="macro-chip"><span class="k">碳水</span><span class="v" id="sum-total-carb">${this.currentDietTotals.totalCarb}</span>g</span>
            <span class="macro-chip"><span class="k">纤维</span><span class="v" id="sum-total-fiber">${this.currentDietTotals.totalFiber}</span>g</span>
            <span class="macro-chip"><span class="k">钠</span><span class="v" id="sum-total-sodium">${this.currentDietTotals.totalSodiumMg}</span>mg</span>
            <span class="macro-chip"><span class="k">重量</span><span class="v" id="sum-total-weight">${this.currentDietTotals.totalWeightG}</span>g</span>
          </div>
        </div>

        <div id="nutrition-section" class="nutrition-chart-container">
          <div id="nutrition-chart-header" class="nutrition-chart-header">
            <span class="nutrition-chart-title">
              ${window.IconManager ? window.IconManager.render('chart', 'sm') : ''} 营养进度
            </span>
            <div class="nutrition-chart-actions">
              <span class="nutrition-chart-hint">点击图例可切换显示</span>
              <button class="section-toggle-btn" id="nutrition-toggle-btn" onclick="Dashboard.toggleNutritionSection(event)" title="折叠/展开" aria-label="折叠/展开">▼</button>
            </div>
          </div>
          <div class="section-wrapper">
             <div class="section-body">
                <div id="nutrition-chart" class="nutrition-chart-canvas"></div>
             </div>
          </div>
        </div>


        <div id="advice-section" class="advice-section">
          <div class="advice-header">
            <div class="dishes-title" style="display: flex; align-items: center; gap: 8px;">
              ${window.IconManager ? window.IconManager.render('lightbulb') : '<img src="css/icons/lightbulb.png" class="hand-icon icon-stamp">'}
              <span style="position: relative; top: 1px;">AI 营养点评</span>
            </div>
            <div class="advice-header-right">
              <span id="advice-status" class="advice-status ${version.advice ? '' : (version.adviceError ? 'error' : (version.adviceLoading ? 'loading' : ''))}"></span>
              <button class="section-toggle-btn" id="advice-toggle-btn" onclick="Dashboard.toggleAdviceSection(event)" title="折叠/展开" aria-label="折叠/展开">▼</button>
            </div>
          </div>
          <div class="section-wrapper">
             <div class="section-body">
                <div id="advice-content" class="advice-content">
                    ${this.generateAdviceHtml(version)}
                </div>
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

        ${data.capturedLabels && data.capturedLabels.length > 0 ? `
        <div class="labels-section">
          <div class="labels-header" onclick="Dashboard.toggleLabelsSection()">
            <div class="dishes-title">营养标签 (${data.capturedLabels.length})</div>
            <span class="labels-toggle" id="labels-toggle-icon">▼</span>
          </div>
          <div id="labels-content" class="labels-content collapsed">
            ${data.capturedLabels.map((lb, idx) => `
              <div class="label-card" data-label-index="${idx}">
                <div class="label-edit-row">
                  <div class="label-edit-field label-edit-primary">
                    <label>产品名称</label>
                    <input type="text" class="label-input" value="${lb.productName}" placeholder="产品名称" oninput="Dashboard.updateLabel(${idx}, 'productName', this.value)">
                  </div>
                  <div class="label-edit-field">
                    <label>品牌</label>
                    <input type="text" class="label-input" value="${lb.brand}" placeholder="品牌" oninput="Dashboard.updateLabel(${idx}, 'brand', this.value)">
                  </div>
                </div>
                <div class="label-edit-row">
                  <div class="label-edit-field">
                    <label>规格/口味</label>
                    <input type="text" class="label-input" value="${lb.variant}" placeholder="如：无糖/低脂" oninput="Dashboard.updateLabel(${idx}, 'variant', this.value)">
                  </div>
                  <div class="label-edit-field">
                    <label>每份</label>
                    <input type="text" class="label-input label-input-sm" value="${lb.servingSize}" placeholder="100g" oninput="Dashboard.updateLabel(${idx}, 'servingSize', this.value)">
                  </div>
                </div>
                <div class="label-macros-display">
                  <span class="label-macro"><span class="k">能量</span><span class="v">${Math.round(lb.energyKjPerServing)} kJ</span></span>
                  <span class="label-macro"><span class="k">蛋白</span><span class="v">${lb.proteinGPerServing}g</span></span>
                  <span class="label-macro"><span class="k">脂肪</span><span class="v">${lb.fatGPerServing}g</span></span>
                  <span class="label-macro"><span class="k">碳水</span><span class="v">${lb.carbsGPerServing}g</span></span>
                  <span class="label-macro"><span class="k">钠</span><span class="v">${lb.sodiumMgPerServing}mg</span></span>
                  ${lb.fiberGPerServing > 0 ? `<span class="label-macro"><span class="k">纤维</span><span class="v">${lb.fiberGPerServing}g</span></span>` : ''}
                </div>
                <div class="label-edit-field label-edit-full">
                  <label>备注</label>
                  <input type="text" class="label-input" value="${lb.customNote}" placeholder="如：密度 1.033, 实测数据等" oninput="Dashboard.updateLabel(${idx}, 'customNote', this.value)">
                </div>
              </div>
            `).join('')}
          </div>
        </div>
        ` : ''}
      </div>
    `;

    this.renderDietDishes();
    this.el.resultTitle.textContent = '饮食分析结果';
    this.updateStatus(session.isSaved ? 'saved' : '');

    // 渲染营养图表
    if (typeof NutritionChartModule !== 'undefined') {
      // 从解析数据中获取 context（today_so_far + user_target）
      if (data.context) {
        NutritionChartModule.setContext(data.context);
      }
      NutritionChartModule.render(
        'nutrition-chart',
        this.currentDietTotals,
        this.getEnergyUnit()
      );
    }

    // 恢复营养进度折叠状态（需要图表初始化后再折叠，避免容器高度为 0）
    if (typeof this.restoreNutritionState === 'function') {
      this.restoreNutritionState();
    }

    // 恢复营养点评折叠状态
    this.restoreAdviceState();
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
                  <tr data-dish-index="${i}">
                    <td><input type="text" class="cell-input" value="${d.name}" oninput="Dashboard.updateDish(${i}, 'name', this.value)"></td>
                    <td><input type="text" class="cell-input num cell-readonly js-energy-display" value="${energyText}" readonly tabindex="-1"></td>
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

    const r1 = (x) => Math.round((Number(x) || 0) * 10) / 10;
    const r0 = (x) => Math.round(Number(x) || 0);

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
        <span class="diet-stat" data-stat-type="energy"><span class="k">能量</span><span class="v">${energyText} ${unit}</span></span>
        <span class="diet-stat" data-stat-type="protein"><span class="k">蛋白</span><span class="v">${r1(totals.protein)}g</span></span>
        <span class="diet-stat" data-stat-type="fat"><span class="k">脂肪</span><span class="v">${r1(totals.fat)}g</span></span>
        <span class="diet-stat" data-stat-type="carb"><span class="k">碳水</span><span class="v">${r1(totals.carb)}g</span></span>
        <span class="diet-stat" data-stat-type="fiber"><span class="k">纤维</span><span class="v">${r1(totals.fiber)}g</span></span>
        <span class="diet-stat" data-stat-type="sodium"><span class="k">钠</span><span class="v">${r0(totals.sodium_mg)}mg</span></span>
        <span class="diet-stat" data-stat-type="weight"><span class="k">重量</span><span class="v">${r1(totals.weight)}g</span></span>
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
                      <tr data-ing-index="${j}">
                        <td><input type="text" class="cell-input cell-readonly" value="${ing.name_zh || ''}" ${ro}></td>
                        <td><input type="text" class="cell-input num cell-readonly js-energy-display" value="${e}" ${ro}></td>
                        <td><input type="number" class="cell-input num js-ing-field" data-field="protein_g" value="${ing.macros?.protein_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'protein_g', this.value)"></td>
                        <td><input type="number" class="cell-input num js-ing-field" data-field="fat_g" value="${ing.macros?.fat_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'fat_g', this.value)"></td>
                        <td><input type="number" class="cell-input num js-ing-field" data-field="carbs_g" value="${ing.macros?.carbs_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'carbs_g', this.value)"></td>
                        <td><input type="number" class="cell-input num js-ing-field" data-field="fiber_g" value="${ing.macros?.fiber_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'fiber_g', this.value)"></td>
                        <td><input type="number" class="cell-input num js-ing-field" data-field="sodium_mg" value="${ing.macros?.sodium_mg ?? 0}" min="0" step="1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'sodium_mg', this.value)"></td>
                        <td><input type="number" class="cell-input num js-ing-field" data-field="weight_g" value="${ing.weight_g ?? 0}" min="0" step="0.1" ${dis} oninput="Dashboard.updateIngredient(${i}, ${j}, 'weight_g', this.value)"></td>
                        <td><button class="scale-toggle-btn ${ing._proportionalScale ? 'active' : ''}" onclick="Dashboard.toggleProportionalScale(${i}, ${j})" title="${ing._proportionalScale ? '比例模式：修改重量会等比调整营养素' : '独立模式：点击开启比例联动'}">${ing._proportionalScale ? '⚖' : '⚖'}</button></td>
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
      <div class="diet-dish-block ${disableInputs ? 'disabled' : ''}" data-dish-index="${i}">
        ${dishHeaderHtml}
        ${ingredientsHtml}
      </div>
    `;
  },

  renderDietDishesMobile() {
    // 注入样式
    if (!document.getElementById('mobile-dish-editor-style')) {
      const style = document.createElement('style');
      style.id = 'mobile-dish-editor-style';
      style.textContent = `
            .mobile-dish-card {
                background: var(--color-bg-secondary, #fff);
                border: 1px solid var(--color-border, #eee);
                padding: 12px 16px;
                border-radius: 12px;
                margin-bottom: 10px;
                cursor: pointer;
                transition: transform 0.1s;
                position: relative;
            }
            .mobile-dish-card:active { transform: scale(0.98); }
            .mobile-dish-row { display: flex; justify-content: space-between; align-items: center; }
            .mobile-dish-name { font-weight: 600; color: var(--color-text-primary); font-size: 1rem; }
            .mobile-dish-energy { font-weight: bold; color: var(--color-accent-primary); font-size: 1rem; font-family: 'Patrick Hand', cursive; }
            .mobile-dish-details { margin-top: 8px; color: var(--color-text-secondary); font-size: 0.85rem; display: flex; gap: 12px; }
            .mobile-dish-macros { color: var(--color-text-muted); font-size: 0.8rem; flex: 1; }
            .mobile-edit-icon { color: var(--color-accent-primary); opacity: 0.8; font-size: 0.9em; display: flex; align-items: center; gap: 4px; }
            
            .user-dish-controls { display:flex; justify-content:flex-end; padding:0 4px 12px 4px; }
            .btn-text-remove { color: var(--color-text-tertiary); font-size: 0.85rem; background:none; border:none; padding:4px 8px; }
            
            .diet-mobile-editor-overlay {
                position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0,0,0,0.6); z-index: 10000;
                display: flex; align-items: center; justify-content: center;
                backdrop-filter: blur(4px);
                animation: fadeIn 0.15s;
            }
            .diet-mobile-editor {
                background: var(--color-bg-secondary, #fff);
                width: 85%; max-width: 360px;
                padding: 24px;
                border-radius: 20px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                animation: slideUp 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);
            }
            .editor-title { font-size: 1.2rem; font-weight: bold; margin-bottom: 20px; color: var(--color-text-primary); text-align: center; }
            .editor-field-group { margin-bottom: 16px; }
            /* Removed uppercase transform */
            .editor-label { display: block; font-size: 0.8rem; color: var(--color-text-muted); margin-bottom: 6px; letter-spacing: 0.5px; }
            .editor-input { 
                width: 100%; padding: 12px; font-size: 1rem; 
                border: 1px solid var(--color-border); border-radius: 12px; 
                background: var(--color-bg-tertiary); color: var(--color-text-primary);
                box-sizing: border-box; 
            }
            .editor-input:focus { border-color: var(--color-accent-primary); outline: none; background: var(--color-bg-secondary); }
            .editor-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
            
            .editor-btn-row { display: flex; gap: 12px; margin-top: 24px; }
            .editor-btn { flex: 1; padding: 14px; border-radius: 12px; border: none; font-weight: 600; cursor: pointer; font-size: 1rem; }
            .btn-save { background: var(--color-accent-primary, #d97757); color: white; box-shadow: 0 4px 12px rgba(217, 119, 87, 0.3); }
            .btn-cancel { background: var(--color-bg-tertiary, #f5f5f5); color: var(--color-text-secondary); }
            
            @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
            @keyframes slideUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        `;
      document.head.appendChild(style);
    }

    return `
      ${this.currentDishes.map((d, i) => {
      const unit = this.getEnergyUnit();
      const r = (v) => Math.round(Number(v) || 0);

      // --- 手动添加的菜品 (User) ---
      if (d.source === 'user') {
        const e = this.formatEnergyFromMacros(d.protein, d.fat, d.carb);
        const macros = `蛋白:${r(d.protein)} 脂肪:${r(d.fat)} 碳水:${r(d.carb)}`;

        return `
             <div class="diet-mobile-group">
                 <div class="mobile-dish-card user-dish" onclick="Dashboard.openMobileUserDishEditor(${i})">
                     <div class="mobile-dish-row">
                          <span class="mobile-dish-name">${d.name || '新添加菜品'}</span>
                          <span class="mobile-dish-energy">${e} ${unit}</span>
                     </div>
                     <div class="mobile-dish-details">
                          <span style="font-weight:600; color:var(--color-text-primary)">${d.weight || 0}g</span>
                          <span class="mobile-dish-macros">${macros}</span>
                          <span class="mobile-edit-icon">✎</span>
                     </div>
                 </div>
                 <div class="user-dish-controls">
                     <button class="btn-text-remove" onclick="event.stopPropagation(); Dashboard.removeDish(${i})">删除此条目</button>
                 </div>
             </div>
            `;
      }

      // --- AI 识别的菜品 (Ingredients) ---
      const ingredients = d.ingredients || [];
      if (ingredients.length === 0) return '';

      // 标题优先使用 name，其次 meal_name
      const title = d.name || d.meal_name || '菜品';

      return `
            <div class="diet-mobile-group" style="margin-bottom: 20px;">
                <div class="dishes-title" style="margin-bottom: 10px; padding-left: 4px;">${title}</div>
                ${ingredients.map((ing, j) => {
        const m = ing.macros || {};
        const e = this.formatEnergyFromMacros(m.protein_g, m.fat_g, m.carbs_g);
        // 中文宏量标签
        const macrosSummary = `蛋白:${r(m.protein_g)} 脂肪:${r(m.fat_g)} 碳水:${r(m.carbs_g)}`;

        return `
                    <div class="mobile-dish-card" onclick="Dashboard.openMobileDishEditor(${i}, ${j})">
                        <div class="mobile-dish-row">
                            <span class="mobile-dish-name">${ing.name_zh || '未命名'}</span>
                            <span class="mobile-dish-energy">${e} ${unit}</span>
                        </div>
                        <div class="mobile-dish-details">
                             <span style="font-weight:600; color:var(--color-text-primary)">${ing.weight_g || 0}g</span>
                             <span class="mobile-dish-macros">${macrosSummary}</span>
                             <span class="mobile-edit-icon">
                                ${window.IconManager ? window.IconManager.render('pencil', '14px') : '✎'}
                                编辑
                             </span>
                        </div>
                    </div>
                   `;
      }).join('')}
            </div>
        `;
    }).join('')}
    `;
  },

  // 编辑 AI 食材
  openMobileDishEditor(dishIdx, ingIdx) {
    this._editingIndices = { dishIdx, ingIdx, type: 'ai' };
    const dish = this.currentDishes[dishIdx];
    const ing = dish.ingredients[ingIdx];
    const m = ing.macros || {};

    // 强制开启等比缩放
    ing._proportionalScale = true;

    // 总是根据当前数值刷新密度，确保联动准确
    // 注意：如果重量为0，无法计算密度，则可能无法联动
    if (Number(ing.weight_g) > 0) {
      const w = Number(ing.weight_g);
      ing._density = {
        protein_per_g: (Number(m.protein_g) || 0) / w,
        fat_per_g: (Number(m.fat_g) || 0) / w,
        carbs_per_g: (Number(m.carbs_g) || 0) / w,
        sodium_per_g: (Number(m.sodium_mg) || 0) / w,
        fiber_per_g: (Number(m.fiber_g) || 0) / w,
      };
    }

    this._renderMobileEditor({
      title: `编辑 ${ing.name_zh || '食材'}`,
      name: ing.name_zh,
      weight: ing.weight_g,
      protein: m.protein_g,
      fat: m.fat_g,
      carbs: m.carbs_g,
      fiber: m.fiber_g,
      sodium: m.sodium_mg
    });
  },

  // 编辑手动菜品
  openMobileUserDishEditor(dishIdx) {
    this._editingIndices = { dishIdx, type: 'user' };
    const dish = this.currentDishes[dishIdx];

    this._renderMobileEditor({
      title: `编辑 ${dish.name || '菜品'}`,
      name: dish.name,
      weight: dish.weight,
      protein: dish.protein,
      fat: dish.fat,
      carbs: dish.carb, // 注意属性名差异 carb vs carbs_g
      fiber: dish.fiber,
      sodium: dish.sodium_mg
    });
  },

  _renderMobileEditor(data) {
    const overlay = document.createElement('div');
    overlay.className = 'diet-mobile-editor-overlay';
    overlay.id = 'diet-mobile-editor';
    // 点击遮罩关闭
    overlay.onclick = (e) => { if (e.target === overlay) this.closeMobileDishEditor(); };

    // 只有 AI 菜品才启用联动逻辑
    const onWeightInput = (this._editingIndices && this._editingIndices.type === 'ai')
      ? 'oninput="Dashboard.handleMobileWeightChange(this.value)"'
      : '';

    // 调试 ID
    const randomId = Math.random().toString(36).substring(7);

    overlay.innerHTML = `
        <div class="diet-mobile-editor" data-uid="${randomId}">
            <div class="editor-title">${data.title}</div>
            
            <div class="editor-field-group">
                <label class="editor-label">名称</label>
                <input id="me-name" class="editor-input" value="${data.name || ''}">
            </div>
            
             <div class="editor-row editor-field-group">
                <div>
                     <label class="editor-label">总重量 (g)</label>
                     <input id="me-weight" type="number" class="editor-input" value="${data.weight || 0}" ${onWeightInput}>
                </div>
                 <div>
                     <label class="editor-label">钠 (mg)</label>
                     <input id="me-sodium" type="number" class="editor-input" value="${data.sodium || 0}">
                </div>
            </div>

            <div class="editor-row editor-field-group">
                <div>
                     <label class="editor-label">蛋白质 (g)</label>
                     <input id="me-protein" type="number" class="editor-input" value="${data.protein || 0}">
                </div>
                 <div>
                     <label class="editor-label">脂肪 (g)</label>
                     <input id="me-fat" type="number" class="editor-input" value="${data.fat || 0}">
                </div>
            </div>
            
            <div class="editor-row editor-field-group">
                <div>
                     <label class="editor-label">碳水 (g)</label>
                     <input id="me-carbs" type="number" class="editor-input" value="${data.carbs || 0}">
                </div>
                 <div>
                     <label class="editor-label">膳食纤维 (g)</label>
                     <input id="me-fiber" type="number" class="editor-input" value="${data.fiber || 0}">
                </div>
            </div>

            <div class="editor-btn-row">
                <button class="editor-btn btn-cancel" onclick="Dashboard.closeMobileDishEditor()">取消</button>
                <button class="editor-btn btn-save" onclick="Dashboard.saveMobileDishEditor()">保存修改</button>
            </div>
        </div>
      `;
    document.body.appendChild(overlay);
  },

  handleMobileWeightChange(val) {
    if (!this._editingIndices || this._editingIndices.type !== 'ai') return;
    const { dishIdx, ingIdx } = this._editingIndices;
    const dish = this.currentDishes?.[dishIdx];
    const ing = dish?.ingredients?.[ingIdx];

    if (!ing || !ing._proportionalScale || !ing._density) return;

    const newWeight = parseFloat(val);
    if (isNaN(newWeight) || newWeight <= 0) return;

    const d = ing._density;
    const setVal = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.value = (Math.round(v * 100) / 100);
    };

    setVal('me-protein', d.protein_per_g * newWeight);
    setVal('me-fat', d.fat_per_g * newWeight);
    setVal('me-carbs', d.carbs_per_g * newWeight);
    setVal('me-fiber', d.fiber_per_g * newWeight);

    const elSod = document.getElementById('me-sodium');
    if (elSod) elSod.value = Math.round(d.sodium_per_g * newWeight);
  },

  closeMobileDishEditor() {
    const el = document.getElementById('diet-mobile-editor');
    if (el) el.remove();
    this._editingIndices = null;
  },

  saveMobileDishEditor() {
    if (!this._editingIndices) return;
    const { dishIdx, ingIdx, type } = this._editingIndices;

    const name = document.getElementById('me-name').value;
    const weight = parseFloat(document.getElementById('me-weight').value) || 0;
    const protein = parseFloat(document.getElementById('me-protein').value) || 0;
    const fat = parseFloat(document.getElementById('me-fat').value) || 0;
    const carbs = parseFloat(document.getElementById('me-carbs').value) || 0;
    const fiber = parseFloat(document.getElementById('me-fiber').value) || 0;
    const sodium = parseFloat(document.getElementById('me-sodium').value) || 0;

    if (type === 'ai') {
      const dish = this.currentDishes[dishIdx];
      const ing = dish.ingredients[ingIdx];
      ing.name_zh = name;
      ing.weight_g = weight;
      if (!ing.macros) ing.macros = {};
      ing.macros.protein_g = protein;
      ing.macros.fat_g = fat;
      ing.macros.carbs_g = carbs;
      ing.macros.fiber_g = fiber;
      ing.macros.sodium_mg = sodium;
    } else {
      // User Dish
      const dish = this.currentDishes[dishIdx];
      dish.name = name;
      dish.weight = weight;
      dish.protein = protein;
      dish.fat = fat;
      dish.carb = carbs;
      dish.fiber = fiber;
      dish.sodium_mg = sodium;
      // Mark as saved/modified manually if needed
    }

    this.recalculateDietSummary();

    const session = this.currentSession;
    if (session && session.versions) {
      const version = session.versions[session.currentVersion - 1];
      this.renderDietResult(session, version);
    }

    this.closeMobileDishEditor();

    this.updateStatus('');
  },

  // 调用 EnergyUtils，自动传入当前单位
  formatEnergyFromMacros(proteinG, fatG, carbsG) {
    return EnergyUtils.formatEnergyFromMacros(proteinG, fatG, carbsG, this.getEnergyUnit());
  },

  /**
   * 生成建议部分的 HTML
   * 提取为公共方法以供 AnalysisModule._setAdviceLoading 复用，避免逻辑不一致
   */
  generateAdviceHtml(version) {
    const data = version.parsedData || {};
    // Ensure simpleMarkdownToHtml is available (mixed in or on this)
    const md = (text) => this.simpleMarkdownToHtml ? this.simpleMarkdownToHtml(text) : text;

    const processContent = data.userNoteProcess ? md(data.userNoteProcess) : '';
    const adviceContent = version.advice ? md(version.advice) : '';
    const quickAdviceContent = data.advice ? md(data.advice) : '';

    let html = '';

    // 1. Process Logic (Hidden Details)
    if (processContent) {
      if (version.advice) {
        html += `
              <details class="advice-process-details" style="margin-bottom: 12px; border-bottom: 1px dashed var(--color-border, #eee); padding-bottom: 12px;">
                  <summary style="cursor: pointer; color: var(--color-text-tertiary, #999); font-size: 0.8rem; display: flex; align-items: center; gap: 6px; user-select: none;">
                      <span style="opacity: 0.8;">AI测算方法 (点击展开)</span>
                  </summary>
                  <div class="advice-intermediate-section" style="margin-top: 12px; opacity: 0.95">
                        <div class="advice-text" style="font-size: 0.9em; line-height: 1.5;">${processContent}</div>
                  </div>
              </details>`;
      } else {
        html += `
              <div class="advice-intermediate-section">
                  <div class="advice-intermediate-label">AI测算方法</div>
                  <div class="advice-text">${processContent}</div>
              </div>`;
      }
    }

    // 2. Advice Content (Partial or Full)
    if (version.advice) {
      html += `<div class="advice-text">${adviceContent}</div>`;
    } else if (quickAdviceContent) {
      // Fallback to quick advice if no explicit advice text
      html += `
          <div class="advice-intermediate-section">
              <div class="advice-intermediate-label">📝 单餐点评</div>
              <div class="advice-text">${quickAdviceContent}</div>
          </div>`;
    }

    // 3. Loading Indicator
    if (version.adviceLoading) {
      // If we already have some advice text, showing a cursor is appropriate.
      // But if user only sees "Method" or "Quick Advice" blocks above, and the main advice area is empty,
      // a lonely cursor looks weird. We should show "Generating..." text until the first chunk of advice arrives.
      if (version.advice && version.advice.length > 0) {
        html += `<span class="streaming-cursor" style="display:inline-block; width:8px; height:1em; background:currentColor; margin-left:2px; vertical-align:text-bottom; animation: blink 1s step-end infinite;"></span>
              <style>@keyframes blink {0%, 100% { opacity: 1; } 50% {opacity: 0; } }</style>`;
      } else {
        html += '<div class="advice-loading" style="margin-top: 12px;"><span class="loading-spinner"></span><span style="margin-left:8px">正在撰写详细建议...</span></div>';
      }
    }

    // 4. Error State (Can coexist with partial advice)
    if (version.adviceError) {
      // Append error below partial text
      html += `<div class="advice-error">⚠️ 定制建议获取失败：${version.adviceError}</div>`;
    }

    // 5. Empty State
    if (html.trim()) {
      return html;
    }

    return '<div class="advice-empty">暂无建议</div>';
  },
  // 渲染餐食类型选择器 (Stealth Select)
  renderMealTypeSelector(name, timeStr) {
    const raw = (name || '').toLowerCase().trim();
    let selected = 'snack'; // default fallback

    // 1. 尝试映射已知类型
    if (raw.includes('break') || raw.includes('早')) selected = 'breakfast';
    else if (raw.includes('lunch') || raw.includes('午')) selected = 'lunch';
    else if (raw.includes('din') || raw.includes('晚')) selected = 'dinner';
    else if (raw.includes('snack') || raw.includes('加') || raw.includes('零')) selected = 'snack';
    else {
      // 2. 如果 name 无法识别（可能是空或时间），尝试从 timeStr 推断
      // 这里简单处理：如果有 name 就保留 name 作为自定义值，否则推断
      // 为了简化，若无法识别则根据当前时间段推断（暂略，直接默认为午餐或保持原样）
      if (!name && timeStr) {
        const h = parseInt(timeStr.split(':')[0]);
        if (!isNaN(h)) {
          if (h >= 5 && h < 10) selected = 'breakfast';
          else if (h >= 10 && h < 16) selected = 'lunch';
          else if (h >= 16 && h < 22) selected = 'dinner';
        }
      }
    }

    const options = [
      { v: 'breakfast', l: '早餐' },
      { v: 'lunch', l: '午餐' },
      { v: 'dinner', l: '晚餐' },
      { v: 'snack', l: '加餐/零食' }
    ];

    // 样式：增加轻量背景和清晰箭头，提升可交互感
    const style = `
appearance: none; -webkit-appearance: none;
background-color: rgba(0, 0, 0, 0.04);
border: 1px solid rgba(0, 0, 0, 0.08);
border-radius: 6px;
font-family: inherit; font-size: inherit; color: inherit;
font-weight: 600; cursor: pointer;
padding: 2px 24px 2px 8px; margin-left: 4px;
background-image: url("data:image/svg+xml;charset=US-ASCII,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%2212%22%20viewBox%3D%220%200%2024%2024%22%3E%3Cpath%20fill%3D%22%23666%22%20d%3D%22M7%2010l5%205%205-5z%22%2F%3E%3C%2Fsvg%3E");
background-repeat: no-repeat; background-position: right 4px center;
transition: all 0.2s;
`;

    return `
        <select onchange="Dashboard.updateMealType(this.value, this.options[this.selectedIndex].text)" style="${style.replace(/\n/g, '')}" title="点击切换餐段">
            ${options.map(o => `<option value="${o.v}" ${o.v === selected ? 'selected' : ''}>${o.l}</option>`).join('')}
        </select>
    `;
  },
};

window.DietRenderModule = DietRenderModule;
