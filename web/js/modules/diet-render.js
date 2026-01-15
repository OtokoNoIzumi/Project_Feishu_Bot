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
      occurredAt: data.occurredAt || null,  // AI 识别的发生时间
    };
    this.recalculateDietSummary(false);

    // 获取当前版本的 user_note
    const currentNote = version.userNote || session.text || '';

    const unit = this.getEnergyUnit();
    // currentDietTotals.totalEnergy 内部统一为 kcal，这里只做显示换算
    const displayTotalEnergy = unit === 'kcal'
      ? (Number(this.currentDietTotals.totalEnergy) || 0)
      : Math.round(this.kcalToKJ(Number(this.currentDietTotals.totalEnergy) || 0));

    this.el.resultContent.innerHTML = `
      <div class="result-card">
        <div class="result-card-header">
          <div class="result-icon-container">${window.IconManager ? window.IconManager.render('meal') : '<img src="css/icons/bowl.png" class="hand-icon icon-sticker">'}</div>
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
          <div id="nutrition-chart" class="nutrition-chart-canvas"></div>
        </div>


        <div id="advice-section" class="advice-section">
          <div class="advice-header">
            <div class="dishes-title" style="display: flex; align-items: center; gap: 8px;">
              ${window.IconManager ? window.IconManager.render('lightbulb') : '<img src="css/icons/lightbulb.png" class="hand-icon icon-stamp">'}
              <span style="position: relative; top: 1px;">AI 营养点评</span>
            </div>
            <div class="advice-header-right">
              <span id="advice-status" class="advice-status ${version.advice ? '' : 'loading'}"></span>
              <button class="section-toggle-btn" id="advice-toggle-btn" onclick="Dashboard.toggleAdviceSection(event)" title="折叠/展开" aria-label="折叠/展开">▼</button>
            </div>
          </div>
          <div id="advice-content" class="advice-content">
            ${version.advice
        ? `<div class="advice-text">${this.simpleMarkdownToHtml(version.advice)}</div>`
        : '<div class="advice-loading"><span class="loading-spinner"></span>正在生成点评...</div>'
      }
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
        <span class="diet-stat"><span class="k">能量</span><span class="v">${energyText} ${unit}</span></span>
        <span class="diet-stat"><span class="k">蛋白</span><span class="v">${r1(totals.protein)}g</span></span>
        <span class="diet-stat"><span class="k">脂肪</span><span class="v">${r1(totals.fat)}g</span></span>
        <span class="diet-stat"><span class="k">碳水</span><span class="v">${r1(totals.carb)}g</span></span>
        <span class="diet-stat"><span class="k">纤维</span><span class="v">${r1(totals.fiber)}g</span></span>
        <span class="diet-stat"><span class="k">钠</span><span class="v">${r0(totals.sodium_mg)}mg</span></span>
        <span class="diet-stat"><span class="k">重量</span><span class="v">${r1(totals.weight)}g</span></span>
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
      const r1 = (x) => Math.round((Number(x) || 0) * 10) / 10;
      const r0 = (x) => Math.round(Number(x) || 0);

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
                  <div class="keep-main" style="gap: 8px; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                      <span class="keep-sub">${ing.name_zh || ''}</span>
                      <span class="keep-details"><span>能量 ${ie} ${unit}</span></span>
                    </div>
                    <button class="scale-toggle-btn ${ing._proportionalScale ? 'active' : ''}" onclick="Dashboard.toggleProportionalScale(${i}, ${j})" title="${ing._proportionalScale ? '比例模式' : '独立模式'}">${ing._proportionalScale ? '⚖' : '⚖'}</button>
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
                <span>蛋白 ${r1(totals.protein)}g</span>
                <span>脂肪 ${r1(totals.fat)}g</span>
                <span>碳水 ${r1(totals.carb)}g</span>
                <span>纤维 ${r1(totals.fiber)}g</span>
                <span>钠 ${r0(totals.sodium_mg)}mg</span>
                <span>重量 ${r1(totals.weight)}g</span>
              </div>
            </div>

            ${d.source === 'user' ? userEditor : aiIngredients}
          </div>
        `;
    }).join('')}
    `;
  },


  // 调用 EnergyUtils，自动传入当前单位
  formatEnergyFromMacros(proteinG, fatG, carbsG) {
    return EnergyUtils.formatEnergyFromMacros(proteinG, fatG, carbsG, this.getEnergyUnit());
  },
};

window.DietRenderModule = DietRenderModule;
