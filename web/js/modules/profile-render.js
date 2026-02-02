/**
 * Profile 渲染模块
 *
 * 负责 Profile 视图的 HTML 渲染
 */

const ProfileRenderModule = {
    // ========== 字段配置 ==========

    // 下拉选项映射（用于显示修改前的值）
    optionLabels: {
        gender: { female: '女', male: '男' },
        'diet.goal': { fat_loss: '减脂', maintain: '维持', muscle_gain: '增肌', health: '健康' },
        activity_level: {
            sedentary: '久坐',
            light: '轻度活动',
            moderate: '中度活动',
            active: '高度活动',
            very_active: '非常活跃',
        },
        timezone: {
            'Asia/Shanghai': 'UTC+8 (北京/上海)',
            'Asia/Tokyo': 'UTC+9 (东京/首尔)',
            'Asia/Singapore': 'UTC+8 (新加坡)',
            'Asia/Bangkok': 'UTC+7 (曼谷)',
            'Asia/Kolkata': 'UTC+5:30 (印度)',
            'Asia/Dubai': 'UTC+4 (迪拜)',
            'Europe/London': 'UTC+0/+1 (伦敦)',
            'Europe/Paris': 'UTC+1/+2 (巴黎)',
            'Europe/Moscow': 'UTC+3 (莫斯科)',
            'America/New_York': 'UTC-5/-4 (纽约)',
            'America/Chicago': 'UTC-6/-5 (芝加哥)',
            'America/Denver': 'UTC-7/-6 (丹佛)',
            'America/Los_Angeles': 'UTC-8/-7 (洛杉矶)',
            'America/Sao_Paulo': 'UTC-3 (圣保罗)',
            'Australia/Sydney': 'UTC+10/+11 (悉尼)',
            'Pacific/Auckland': 'UTC+12/+13 (奥克兰)',
        },
    },

    // 获取选项的显示标签
    getOptionLabel(fieldKey, value) {
        const map = this.optionLabels[fieldKey];
        if (map && map[value]) return map[value];
        return value ?? '-';
    },

    // 获取时区选项列表（单一数据源）
    getTimezoneOptions() {
        const tzMap = this.optionLabels.timezone;
        return Object.entries(tzMap).map(([value, label]) => ({ value, label }));
    },

    // ========== 主渲染 ==========

    render() {
        const p = ProfileModule.getCurrentProfile();
        const dm = ProfileModule.pendingMetrics || ProfileModule.dynamicMetrics || {};
        const { canAnalyze, missing } = ProfileModule.canAnalyze();

        const userName = Auth.user?.firstName || Auth.user?.fullName || Auth.user?.username || '用户';
        const unit = p.diet?.energy_unit || 'kJ';

        // 计算显示的能量目标值
        const rawEnergyTarget = p.diet?.daily_energy_kj_target;
        const displayEnergyTarget = rawEnergyTarget
            ? (unit === 'kcal' ? Math.round(EnergyUtils.kJToKcal(rawEnergyTarget)) : rawEnergyTarget)
            : '';

        return `
            ${this.renderStyles()}
            <style>
                .profile-field-input, .profile-field textarea, .profile-field select {
                    font-family: inherit !important;
                }
            </style>
            <div class="profile-container">
                ${!canAnalyze ? this.renderMissingInfoBanner(missing) : ''}

                <!-- 档案信息 -->
                ${this.renderProfileSection(p, dm, userName, unit)}

                <!-- Diet 目标 -->
                ${this.renderDietSection(p, unit, displayEnergyTarget)}

                <!-- Keep 目标 -->
                ${this.renderKeepSection(p)}

                <!-- 用户关键主张 -->
                ${this.renderUserInfoSection(p)}
            </div>
        `;
    },

    /**
     * 只渲染内容区域（不含操作按钮）
     */
    renderContent() {
        return this.render();
    },



    renderMissingInfoBanner(missing) {
        return `
            <div class="profile-banner profile-banner-warning">
                <div class="profile-banner-icon">${window.IconManager ? window.IconManager.render('pencil', 'xl') : '👤'}</div>
                <div class="profile-banner-content">
                    <div class="profile-banner-title">请完善基础信息</div>
                    <div class="profile-banner-text">
                        缺少：${missing.join('、')}。完善后可使用 AI 对话优化个人目标功能。
                    </div>
                </div>
            </div>
        `;
    },

    // ========== 档案信息 ==========

    // ========== Diet 目标 ==========

    renderDietSection(p, unit, displayEnergyTarget) {
        const diet = p.diet || {};

        return `
            <div class="profile-section">
                <div class="profile-section-header">
                    <div class="profile-section-icon">${window.IconManager ? window.IconManager.render('meal', 'xl') : '🍽️'}</div>
                    <div>
                        <div class="profile-section-title">Diet 目标</div>
                        <div class="profile-section-subtitle">每日营养摄入目标</div>
                    </div>
                </div>
                <div class="profile-grid profile-grid-3">
                    ${this.renderNumberField('diet.protein_g_target', '蛋白质 (g)', diet.protein_g_target)}
                    ${this.renderNumberField('diet.fat_g_target', '脂肪 (g)', diet.fat_g_target)}
                    ${this.renderNumberField('diet.carbs_g_target', '碳水 (g)', diet.carbs_g_target)}
                </div>
                <div class="profile-grid profile-grid-3" style="margin-top: 12px;">
                    ${this.renderNumberField('diet.daily_energy_kj_target', `能量 (${unit})`, displayEnergyTarget)}
                    ${this.renderNumberField('diet.fiber_g_target', '纤维 (g)', diet.fiber_g_target)}
                    ${this.renderNumberField('diet.sodium_mg_target', '钠 (mg)', diet.sodium_mg_target, 1)}
                </div>
            </div>
        `;
    },

    // ========== Keep 目标 ==========

    renderKeepSection(p) {
        const keep = p.keep || {};
        const dims = keep.dimensions_target || {};

        return `
            <div class="profile-section">
                <div class="profile-section-header">
                    <div class="profile-section-icon">${window.IconManager ? window.IconManager.render('heart', 'xl') : '💪'}</div>
                    <div>
                        <div class="profile-section-title">Keep 目标</div>
                        <div class="profile-section-subtitle">体重与体态目标</div>
                    </div>
                </div>
                <div class="profile-grid profile-grid-4">
                    ${this.renderNumberField('keep.weight_kg_target', '目标体重 (kg)', keep.weight_kg_target)}
                    ${this.renderNumberField('keep.body_fat_pct_target', '目标体脂 (%)', keep.body_fat_pct_target)}
                    ${this.renderNumberField('keep.dimensions_target.bust', '胸围 (cm)', dims.bust)}
                    ${this.renderNumberField('keep.dimensions_target.waist', '腰围 (cm)', dims.waist)}
                    ${this.renderNumberField('keep.dimensions_target.hip_circ', '臀围 (cm)', dims.hip_circ)}
                    ${this.renderNumberField('keep.dimensions_target.thigh', '大腿围 (cm)', dims.thigh)}
                    ${this.renderNumberField('keep.dimensions_target.calf', '小腿围 (cm)', dims.calf)}
                    ${this.renderNumberField('keep.dimensions_target.arm', '上臂围 (cm)', dims.arm)}
                </div>
            </div>
        `;
    },

    // ========== 用户关键主张 ==========

    renderUserInfoSection(p) {
        const diffResult = ProfileModule.getUserInfoDiff();
        const userInfo = p.user_info || '';

        return `
            <div class="profile-section">
                <div class="profile-section-header">
                    <div class="profile-section-icon">${window.IconManager ? window.IconManager.render('comment', 'xl') : '💬'}</div>
                    <div>
                        <div class="profile-section-title">关键主张</div>
                        <div class="profile-section-subtitle">
                            影响分析的重要信息
                            ${diffResult.hasDiff ? '<span class="change-indicator" title="有变化">●</span>' : ''}
                        </div>
                    </div>
                    ${diffResult.hasDiff ? `
                        <button class="btn btn-xs btn-ghost" onclick="ProfileRenderModule.showUserInfoDiff()" title="查看变化">
                            Diff
                        </button>
                        <button class="btn btn-xs btn-ghost" onclick="ProfileRenderModule.revertField('user_info')" title="还原">
                            ↩
                        </button>
                    ` : ''}
                </div>
                ${this.renderTextField('user_info', userInfo, '这里的记录也会作为优化的上下文提交给AI')}
                ${diffResult.hasDiff ? `
                    <div id="user-info-diff" class="user-info-diff hidden">
                        ${this.renderUserInfoDiffContent(diffResult.diff)}
                    </div>
                ` : ''}
            </div>
        `;
    },

    renderUserInfoDiffContent(diff) {
        if (!diff || diff.length === 0) return '无变化';
        return `
            <div class="diff-lines">
                ${diff.map(d => `
                    <div class="diff-line diff-${d.type}">
                        <span class="diff-prefix">${d.type === 'added' ? '+' : d.type === 'removed' ? '-' : ' '}</span>
                        ${d.text}
                    </div>
                `).join('')}
            </div>
        `;
    },

    // ========== 组件化表单元素 ==========

    /**
     * 渲染数字输入框
     * @param {number} step - 步长 (默认 0.1)
     */
    renderNumberField(fieldKey, label, value, step = 0.1) {
        const change = ProfileModule.getFieldChange(fieldKey);
        const hasChange = change.hasChange;
        const inputId = fieldKey.replace(/\./g, '-');
        const displayValue = value ?? '';

        // 能量目标的原始值需要按当前单位转换显示
        let originalDisplayValue = change.original ?? '-';
        if (fieldKey === 'diet.daily_energy_kj_target' && change.original) {
            const unit = ProfileModule.getCurrentProfile()?.diet?.energy_unit || 'kJ';
            originalDisplayValue = (unit === 'kcal')
                ? Math.round(EnergyUtils.kJToKcal(change.original))
                : change.original;
        }

        const originalDisplay = hasChange
            ? `<span class="field-original-inline">修改前: ${originalDisplayValue}</span>`
            : '';

        // 如果步长是 1，则强制解析为整数
        const parseFn = step === 1 ? 'parseInt' : 'parseFloat';

        return `
            <div class="profile-field ${hasChange ? 'has-change' : ''}">
                <label class="profile-field-label">
                    ${label}
                    ${originalDisplay}
                    ${hasChange ? this.renderRevertBtn(fieldKey) : ''}
                </label>
                <input id="${inputId}" type="number" class="profile-field-input"
                    value="${displayValue}" step="${step}" placeholder="-"
                    onchange="ProfileRenderModule.onFieldChange('${fieldKey}', ${parseFn}(this.value) || null)">
            </div>
        `;
    },

    /**
     * 渲染下拉选择框
     */
    renderSelectField(fieldKey, label, options, selectedValue) {
        const change = ProfileModule.getFieldChange(fieldKey);
        const hasChange = change.hasChange;
        const inputId = fieldKey.replace(/\./g, '-');

        // 使用标签而非原始值显示修改前
        const originalLabel = this.getOptionLabel(fieldKey, change.original);
        const originalDisplay = hasChange
            ? `<span class="field-original-inline">修改前: ${originalLabel}</span>`
            : '';

        const optionsHtml = options.map(o =>
            `<option value="${o.value}" ${o.value === (selectedValue || '') ? 'selected' : ''}>${o.label}</option>`
        ).join('');

        return `
            <div class="profile-field ${hasChange ? 'has-change' : ''}">
                <label class="profile-field-label">
                    ${label}
                    ${originalDisplay}
                    ${hasChange ? this.renderRevertBtn(fieldKey) : ''}
                </label>
                <select id="${inputId}" class="profile-field-input"
                    onchange="ProfileRenderModule.onFieldChange('${fieldKey}', this.value)">
                    ${optionsHtml}
                </select>
            </div>
        `;
    },

    /**
     * 渲染能量单位选择器 - 特殊处理
     * 调用 Dashboard.setEnergyUnit() 立即刷新所有视图
     */
    renderEnergyUnitField(currentUnit) {
        const change = ProfileModule.getFieldChange('diet.energy_unit');
        const hasChange = change.hasChange;

        const kJSelected = currentUnit === 'kJ' ? 'selected' : '';
        const kcalSelected = currentUnit === 'kcal' ? 'selected' : '';

        const originalDisplay = hasChange
            ? `<span class="field-original-inline">修改前: ${change.original === 'kcal' ? 'kcal (大卡)' : 'kJ (千焦)'}</span>`
            : '';

        return `
            <div class="profile-field ${hasChange ? 'has-change' : ''}">
                <label class="profile-field-label">
                    能量单位
                    ${originalDisplay}
                    ${hasChange ? this.renderRevertBtn('diet.energy_unit') : ''}
                </label>
                <select id="diet-energy_unit" class="profile-field-input"
                    onchange="Dashboard.setEnergyUnit(this.value)">
                    <option value="kJ" ${kJSelected}>kJ (千焦)</option>
                    <option value="kcal" ${kcalSelected}>kcal (大卡)</option>
                </select>
            </div>
        `;
    },

    /**
     * 渲染文本域
     */
    renderTextField(fieldKey, value, placeholder = '') {
        const inputId = fieldKey.replace(/\./g, '-');

        return `
            <div class="profile-field">
                <textarea id="${inputId}" class="profile-field-input profile-textarea"
                    placeholder="${placeholder}"
                    onchange="ProfileRenderModule.onFieldChange('${fieldKey}', this.value)">${value || ''}</textarea>
            </div>
        `;
    },

    renderRevertBtn(fieldPath) {
        return `<button class="btn-revert" onclick="ProfileRenderModule.revertField('${fieldPath}')" title="还原">↩</button>`;
    },

    // ========== 操作按钮 ==========

    renderActionButtons() {
        const hasChanges = ProfileModule.hasChanges();

        return `
            <div class="profile-actions">
                ${hasChanges ? `
                    <button class="btn btn-ghost" onclick="ProfileRenderModule.revertAll()">
                        ↩ 还原全部
                    </button>
                ` : ''}
                <button class="btn btn-secondary" onclick="Dashboard.switchView('analysis')">
                    返回
                </button>
                <button class="btn btn-primary" onclick="ProfileRenderModule.saveProfile()" ${!hasChanges ? 'disabled' : ''}>
                    ${window.IconManager ? window.IconManager.render('save') : ''} 保存档案
                </button>
            </div>
        `;
    },

    renderStyles() {
        // 通用样式已移至 css/components/common-cards.css
        // 此处只保留 Profile 特有的表单样式
        return `
            <style>
                /* Profile 特有样式 */
                .profile-field { display: flex; flex-direction: column; gap: 6px; position: relative; }
                .profile-field.has-change { background: rgba(59, 130, 246, 0.08); border-radius: 6px; padding: 8px; margin: -8px; }

                .profile-field-label {
                    font-size: 0.8rem; font-weight: 600; color: var(--color-text-secondary);
                    display: flex; align-items: center; gap: 6px;
                    flex-wrap: wrap;
                }

                /* 原值显示 */
                .field-original-inline {
                    font-size: 0.7rem;
                    color: var(--color-text-muted);
                    font-style: italic;
                    background: rgba(0,0,0,0.05);
                    padding: 1px 6px;
                    border-radius: 3px;
                }

                .profile-field-input {
                    background: var(--color-bg-tertiary);
                    border: 1px solid var(--color-border);
                    border-radius: 4px;
                    padding: 10px 12px;
                    font-size: 0.95rem;
                    font-family: var(--font-handwritten);
                    color: var(--color-text-primary);
                    width: 100%;
                    box-sizing: border-box;
                }
                .profile-field-input:focus { outline: none; border-color: var(--color-accent-primary); background: #fff; }
                .profile-field-input select { font-family: var(--font-body); }
                .profile-textarea { min-height: 80px; resize: vertical; font-family: var(--font-body); }

                .btn-revert {
                    background: none; border: none; cursor: pointer;
                    color: var(--color-accent-secondary); font-size: 0.8rem;
                    padding: 2px 4px; border-radius: 3px;
                    margin-left: auto;
                }
                .btn-revert:hover { background: rgba(0,0,0,0.05); }

                .change-indicator { color: var(--color-accent-primary); font-size: 0.6rem; margin-left: 4px; }

                /* Unsaved Status in Title */
                .unsaved-status {
                    display: inline-block;
                    font-size: 0.75rem;
                    font-weight: normal;
                    color: #d97706;
                    background: #fef3c7;
                    padding: 2px 8px;
                    border-radius: 12px;
                    margin-left: 8px;
                    vertical-align: middle;
                    animation: pulse-opacity 2s infinite;
                }
                @keyframes pulse-opacity {
                    0% { opacity: 0.7; }
                    50% { opacity: 1; }
                    100% { opacity: 0.7; }
                }

                /* Character Diff Styles */
                .user-info-diff { margin-top: 8px; padding: 12px; background: #fff; border: 1px dashed var(--color-border); border-radius: 4px; font-family: monospace; font-size: 0.85rem; white-space: pre-wrap; word-break: break-all; }
                .diff-char-add { background: #bbf7d0; color: #14532d; text-decoration: none; }
                .diff-char-remove { background: #fecaca; color: #991b1b; text-decoration: line-through; }

                .profile-actions {
                    display: flex;
                    justify-content: flex-end;
                    gap: 12px;
                }

                .hidden { display: none !important; }
            </style>
        `;
    },

    /**
     * 生成随机角度的胶带（委托给 UIComponents）
     */
    renderTape(right = '50px', rotation = null) {
        if (window.UIComponents) {
            return window.UIComponents.renderTape(right, rotation);
        }
        // Fallback
        const deg = rotation !== null ? rotation : (Math.random() * 6 - 3).toFixed(1);
        return `<div class="tape-sticker" style="right: ${right}; transform: rotate(${deg}deg);"></div>`;
    },

    // ========== 档案信息 (Merged User Info) ==========

    // ========== 拆分后的局部渲染方法 (Header & Body) ==========

    _renderHeader(p, userName) {
        return `
            <div class="profile-section-header">
                <div class="profile-section-icon">
                    ${window.Clerk?.user?.imageUrl
                ? `<img src="${window.Clerk.user.imageUrl}?width=160" class="cl-avatarImage" style="width: 100%; height: 100%; border-radius: 50%; object-fit: cover;" alt="Avatar">`
                : (() => {
                    const genderValue = p.gender;
                    const fallbackIcon = genderValue === 'male'
                        ? 'profile_man'
                        : genderValue === 'female'
                            ? 'profile_woman'
                            : 'bookmark';
                    return window.IconManager ? window.IconManager.render(fallbackIcon, 'xl') : '👤';
                })()
            }
                </div>
                <div>
                    <div class="profile-section-title">
                        ${userName} 的档案
                        ${(() => {
                if (!p.nid) return '';
                const nid = Number(p.nid);
                const isPremium = Number.isFinite(nid) && nid < 10000;
                if (!isPremium) {
                    return `<span style="font-size:0.8em; color:#9ca3af; margin-left:8px; font-weight:normal;">id ${p.nid}</span>`;
                }
                return `<span style="font-size:0.8em; margin-left:8px; font-weight:600; color:#d4b36a; background:rgba(212,179,106,0.12); border:1px solid rgba(212,179,106,0.4); padding:1px 6px; border-radius:10px; letter-spacing:0.3px;">id ${p.nid}</span>`;
            })()}
                        ${(() => {
                // 前端计算当前最高有效等级
                const levels = ['basic', 'pro', 'ultra']; // 低 -> 高
                const levelNames = {
                    'basic': '基础会员',
                    'pro': 'PRO',
                    'ultra': 'ULTRA'
                };
                const subs = p.subscriptions || {};
                const now = new Date();
                let currentLvl = 'expired';

                // 日期格式化函数 (使用 Profile 时区)
                const userTz = p.timezone || 'Asia/Shanghai';
                const formatDateTime = (dt) => {
                    try {
                        return dt.toLocaleString('zh-CN', {
                            timeZone: userTz,
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                            hour12: false
                        }).replace(/\//g, '-');
                    } catch (e) {
                        // Fallback if timezone invalid
                        const y = dt.getFullYear();
                        const mo = String(dt.getMonth() + 1).padStart(2, '0');
                        const d = String(dt.getDate()).padStart(2, '0');
                        const h = String(dt.getHours()).padStart(2, '0');
                        const mi = String(dt.getMinutes()).padStart(2, '0');
                        return `${y}-${mo}-${d} ${h}:${mi}`;
                    }
                };

                // 收集所有等级的过期时间 (从高到低)
                const subData = [];
                for (let i = levels.length - 1; i >= 0; i--) {
                    const lvl = levels[i];
                    const expStr = subs[lvl];
                    if (expStr) {
                        const dt = new Date(expStr);
                        subData.push({ lvl, dt, isActive: dt > now });
                        if (dt > now && currentLvl === 'expired') {
                            currentLvl = lvl;
                        }
                    }
                }

                // 构建时间线折叠显示
                const tooltipLines = [];
                let prevEndDate = null;

                for (const item of subData) {
                    const { lvl, dt, isActive } = item;

                    if (prevEndDate === null) {
                        // 最高等级，直接显示结束日期
                        tooltipLines.push(`${levelNames[lvl]}: ${formatDateTime(dt)}${isActive ? '' : ' (已过期)'}`);
                    } else {
                        // 检查是否被上级覆盖
                        if (dt <= prevEndDate) {
                            // 完全被覆盖，不显示
                        } else {
                            // 显示增量时间段
                            tooltipLines.push(`${levelNames[lvl]}: ${formatDateTime(prevEndDate)} ~ ${formatDateTime(dt)}${isActive ? '' : ' (已过期)'}`);
                        }
                    }
                    // 更新 prevEndDate 为当前等级和之前的最大值
                    if (prevEndDate === null || dt > prevEndDate) {
                        prevEndDate = dt;
                    }
                }

                if (tooltipLines.length === 0) {
                    tooltipLines.push('无订阅信息');
                }

                const badgeColor = {
                    'basic': '#0369a1',
                    'pro': '#7c3aed',
                    'ultra': '#be123c',
                    'expired': '#dc2626'
                }[currentLvl] || '#9ca3af';

                const badgeBg = {
                    'basic': '#e0f2fe',
                    'pro': '#ede9fe',
                    'ultra': '#ffe4e6',
                    'expired': '#fef2f2'
                }[currentLvl] || '#f3f4f6';

                // 检测是否为试用状态: basic 且到期时间 ≈ 注册时间 + 3天
                let isTrial = false;
                if (currentLvl === 'basic' && p.registered_at && subs.basic) {
                    const regDate = new Date(p.registered_at);
                    const basicExpiry = new Date(subs.basic);
                    const expectedTrialEnd = new Date(regDate.getTime() + 3 * 24 * 60 * 60 * 1000);
                    // 差距小于 1 分钟则认为是试用
                    if (Math.abs(basicExpiry - expectedTrialEnd) < 60 * 1000) {
                        isTrial = true;
                    }
                }

                let displayName = currentLvl === 'expired' ? '已过期' : (levelNames[currentLvl] || currentLvl.toUpperCase());
                if (isTrial) {
                    displayName += ' (试用)';
                }

                // 使用自定义 CSS tooltip
                return `<span class="level-badge-wrap"><span class="level-badge" style="background:${badgeBg}; color:${badgeColor};">${displayName}</span><span class="level-badge-tooltip">${tooltipLines.join('<br>')}</span></span>`;
            })()}
                    </div>
                    <div class="profile-section-subtitle">个人基础信息</div>
                </div>
            </div>`;
    },

    _renderBody(p, dm, unit, diffResult) {
        return `
                <div class="profile-grid profile-grid-3">
                    ${this.renderSelectField('gender', '性别', [
            { value: '', label: '请选择' },
            { value: 'female', label: '女' },
            { value: 'male', label: '男' },
        ], p.gender)}
                    ${this.renderSelectField('timezone', '时区', this.getTimezoneOptions(), p.timezone)}
                    ${this.renderEnergyUnitField(unit)}
                </div>
                <div class="profile-grid profile-grid-3" style="margin-top: 12px;">
                    ${this.renderNumberField('age', '年龄', p.age, 1)}
                    ${this.renderNumberField('_metrics.height_cm', '身高 (cm)', dm.height_cm, 0.1)}
                    ${this.renderNumberField('_metrics.weight_kg', '体重 (kg)', dm.weight_kg, 0.1)}
                </div>
                <div class="profile-grid profile-grid-3" style="margin-top: 12px;">
                    ${this.renderSelectField('diet.goal', '目标', [
            { value: 'fat_loss', label: '减脂' },
            { value: 'maintain', label: '维持' },
            { value: 'muscle_gain', label: '增肌' },
            { value: 'health', label: '健康' },
        ], p.diet?.goal)}
                    ${this.renderSelectField('activity_level', '活动水平', [
            { value: 'sedentary', label: '久坐' },
            { value: 'light', label: '轻度活动' },
            { value: 'moderate', label: '中度活动' },
            { value: 'active', label: '高度活动' },
            { value: 'very_active', label: '非常活跃' },
        ], p.activity_level)}
                    ${this.renderNumberField('estimated_months', '预期达成 (月)', p.estimated_months, 1)}
                </div>

                <!-- Invitation Code -->
                <div class="profile-invite-area" style="margin-top: 16px; border-top: 1px dashed var(--color-border); padding-top: 12px;">
                    <label class="profile-field-label">激活码兑换 / Invitation Code</label>
                    <div style="display:flex; gap:8px; margin-top:4px;">
                        <input type="text" id="invite-code-input" class="profile-field-input" placeholder="输入激活码 (Account / NID)..." style="flex:1;">
                        <button class="btn btn-secondary" onclick="ProfileRenderModule.redeemCode()">兑换</button>
                    </div>
                </div>


                    <!-- User Info (Key Claims) merged here -->
                    <div class="profile-grid-full" style="margin-top: 12px; border-top: 1px dashed var(--color-border); padding-top: 12px;">
                        <label class="profile-field-label" style="justify-content: space-between; margin-bottom: 8px;">
                            <span>
                                关键主张
                                <span style="font-weight: normal; color: var(--color-text-muted); font-size: 0.75rem;">(将会作为 AI 分析和优化档案的上下文)</span>
                                ${diffResult.hasDiff ? '<span class="change-indicator" title="有变化">●</span>' : ''}
                            </span>
                            ${diffResult.hasDiff ? `
                                <div>
                                    <button class="btn btn-xs btn-ghost" onclick="ProfileRenderModule.showUserInfoDiff()" title="查看精确差异">Diff</button>
                                    <button class="btn btn-xs btn-ghost" onclick="ProfileRenderModule.revertField('user_info')" title="还原">↩</button>
                                </div>
                            ` : ''}
                        </label>
                        ${this.renderTextField('user_info', p.user_info || '', '这里的摘要AI也会更新，但未必完全代表你的意思，请及时维护。')}
                        ${diffResult.hasDiff ? `
                            <div id="user-info-diff" class="user-info-diff hidden">
                                ${this.renderUserInfoDiffContent(diffResult.diff)}
                            </div>
                        ` : ''}
                    </div>
                </div>`;
    },

    renderProfileSection(p, dm, userName, unit) {
        // User Info Diff Logic
        const diffResult = ProfileModule.getUserInfoDiff();

        return `
            <div class="profile-section">
                ${this.renderTape('60px', 2)}
                <div id="profile-header-container">
                    ${this._renderHeader(p, userName)}
                </div>
                <div id="profile-body-container">
                    ${this._renderBody(p, dm, unit, diffResult)}
                </div>
            </div>
        `;
    },

    // ========== Diet 目标 ==========

    renderDietSection(p, unit, displayEnergyTarget) {
        const diet = p.diet || {};
        return `
            <div class="profile-section">
                ${this.renderTape('45px', -1.5)}
                <div class="profile-section-header">
                    <div class="profile-section-icon">${window.IconManager ? window.IconManager.render('meal', 'xl') : '🍽️'}</div>
                    <div>
                        <div class="profile-section-title">Diet 目标</div>
                        <div class="profile-section-subtitle">每日营养摄入目标</div>
                    </div>
                </div>
                <div class="profile-grid profile-grid-3">
                    ${this.renderNumberField('diet.protein_g_target', '蛋白质 (g)', diet.protein_g_target, 0.1)}
                    ${this.renderNumberField('diet.fat_g_target', '脂肪 (g)', diet.fat_g_target, 0.1)}
                    ${this.renderNumberField('diet.carbs_g_target', '碳水 (g)', diet.carbs_g_target, 0.1)}
                </div>
                <div class="profile-grid profile-grid-3" style="margin-top: 12px;">
                    ${this.renderNumberField('diet.daily_energy_kj_target', `能量 (${unit})`, displayEnergyTarget, 1)}
                    ${this.renderNumberField('diet.fiber_g_target', '膳食纤维 (g)', diet.fiber_g_target, 0.1)}
                    ${this.renderNumberField('diet.sodium_mg_target', '钠 (mg)', diet.sodium_mg_target, 1)}
                </div>
            </div>
        `;
    },

    // ========== Keep 目标 ==========

    renderKeepSection(p) {
        const keep = p.keep || {};
        const dims = keep.dimensions_target || {};
        return `
            <div class="profile-section">
                ${this.renderTape('55px', 1)}
                <div class="profile-section-header">
                    <div class="profile-section-icon">${window.IconManager ? window.IconManager.render('heart', 'xl') : '💪'}</div>
                    <div>
                        <div class="profile-section-title">Keep 目标</div>
                        <div class="profile-section-subtitle">体重与体态目标</div>
                    </div>
                </div>
                <div class="profile-grid profile-grid-4">
                    ${this.renderNumberField('keep.weight_kg_target', '目标体重 (kg)', keep.weight_kg_target)}
                    ${this.renderNumberField('keep.body_fat_pct_target', '目标体脂 (%)', keep.body_fat_pct_target)}
                    ${this.renderNumberField('keep.dimensions_target.bust', '胸围 (cm)', dims.bust)}
                    ${this.renderNumberField('keep.dimensions_target.waist', '腰围 (cm)', dims.waist)}
                    ${this.renderNumberField('keep.dimensions_target.hip_circ', '臀围 (cm)', dims.hip_circ)}
                    ${this.renderNumberField('keep.dimensions_target.thigh', '大腿围 (cm)', dims.thigh)}
                    ${this.renderNumberField('keep.dimensions_target.calf', '小腿围 (cm)', dims.calf)}
                    ${this.renderNumberField('keep.dimensions_target.arm', '上臂围 (cm)', dims.arm)}
                </div>
            </div>
        `;
    },

    // ========== Users Info (Removed Separate Section) ==========

    renderUserInfoSection(p) {
        return ''; // Integrated into renderProfileSection
    },

    /**
     * 渲染 Diff 内容 (Character Level)
     * Diff structure: [{ type: 'equal'|'add'|'remove', value: '...' }]
     */
    renderUserInfoDiffContent(diff) {
        if (!diff || diff.length === 0) return '无变化';

        return diff.map(part => {
            if (part.type === 'add') {
                return `<span class="diff-char-add">${this.escapeHtml(part.value)}</span>`;
            } else if (part.type === 'remove') {
                return `<span class="diff-char-remove">${this.escapeHtml(part.value)}</span>`;
            } else {
                return this.escapeHtml(part.value);
            }
        }).join('');
    },

    escapeHtml(text) {
        if (!text) return '';
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },

    rotateTape(el) {
        // 委托给 UIComponents
        if (window.UIComponents) {
            window.UIComponents.rotateTape(el);
        }
    },

    // ========== 事件处理 ==========

    onFieldChange(fieldPath, value) {
        // 处理身体指标字段（保存到 Keep）
        if (fieldPath.startsWith('_metrics.')) {
            const key = fieldPath.replace('_metrics.', '');
            ProfileModule.updateMetric(key, value);
        } else if (fieldPath === 'diet.daily_energy_kj_target') {
            // 能量目标特殊处理：根据当前单位转换
            // 显示时是按单位展示的，保存时需要转回 kJ
            const unit = ProfileModule.getCurrentProfile()?.diet?.energy_unit || 'kJ';
            const valueInKJ = (unit === 'kcal' && value) ? Math.round(EnergyUtils.kcalToKJ(value)) : value;
            ProfileModule.updateField(fieldPath, valueInKJ);
        } else {
            ProfileModule.updateField(fieldPath, value);
        }
        this.refreshView();
    },

    revertField(fieldPath) {
        if (fieldPath.startsWith('_metrics.')) {
            const key = fieldPath.replace('_metrics.', '');
            ProfileModule.revertMetric(key);
        } else {
            ProfileModule.revertField(fieldPath);
        }

        // 能量单位特殊处理：需要刷新所有视图
        if (fieldPath === 'diet.energy_unit') {
            const p = ProfileModule.getCurrentProfile();
            Dashboard.setEnergyUnit(p?.diet?.energy_unit || 'kJ');
        } else {
            this.refreshView();
        }
    },

    async redeemCode() {
        if (Auth.isDemoMode()) {
            if (window.ToastUtils) ToastUtils.show('演示模式下不可兑换激活码，请注册后使用', 'info');
            if (window.Auth && typeof window.Auth.openSignUp === 'function') {
                window.Auth.openSignUp();
            }
            return;
        }
        const input = document.getElementById('invite-code-input');
        const code = input?.value?.trim();
        if (!code) {
            if (window.ToastUtils) ToastUtils.show('请输入激活码', 'info');
            return;
        }

        const btn = document.querySelector('.profile-invite-area button');
        const originalText = btn ? btn.innerText : '兑换';
        if (btn) {
            btn.innerText = '...';
            btn.disabled = true;
        }

        try {
            const resp = await API.post('/user/invitation/redeem', { code });
            if (window.ToastUtils) ToastUtils.show('兑换成功！' + (resp.message || '已应用'), 'success');

            await ProfileModule.loadFromServer();
            Dashboard.renderProfileView();
        } catch (e) {
            console.error(e);
            let msg = e.message || '未知错误';
            if (e.detail) {
                if (typeof e.detail === 'object') msg = e.detail.message || JSON.stringify(e.detail);
                else msg = e.detail;
            } else if (e.response && e.response.data && e.response.data.detail) {
                msg = e.response.data.detail;
            }

            if (window.ToastUtils) ToastUtils.show('兑换失败: ' + msg, 'error');
        } finally {
            if (btn) {
                btn.innerText = originalText;
                btn.disabled = false;
            }
        }
    },

    revertAll() {
        ProfileModule.revertAll();
        this.refreshView();
    },

    showUserInfoDiff() {
        const el = document.getElementById('user-info-diff');
        if (el) el.classList.toggle('hidden');
    },

    async saveProfile() {
        if (Auth.isDemoMode()) {
            if (window.ToastUtils) ToastUtils.show('演示模式下无法保存档案，请注册后使用', 'info');
            if (window.Auth && typeof window.Auth.openSignUp === 'function') {
                window.Auth.openSignUp();
            }
            return;
        }
        const result = await ProfileModule.saveToServer();
        if (result.success) {
            Dashboard.addMessage('✓ 个人档案已保存', 'assistant');
            this.refreshView();
        } else {
            Dashboard.addMessage(`保存失败: ${result.error}`, 'assistant');
        }
    },

    refreshView() {
        if (Dashboard.view === 'profile') {
            // 尝试局部更新以防止头像闪烁
            const formContainer = document.getElementById('profile-body-container');
            const headerContainer = document.getElementById('profile-header-container');

            if (formContainer && headerContainer) {
                const p = ProfileModule.getCurrentProfile();
                const dm = ProfileModule.dynamicMetrics || {};
                const unit = p.diet?.energy_unit || 'kJ';
                let userName = '用户';
                if (typeof Auth !== 'undefined' && Auth.user) {
                    userName = Auth.user.firstName || Auth.user.fullName || Auth.user.username || '用户';
                } else if (p.name) {
                    userName = p.name;
                }
                const diffResult = ProfileModule.getUserInfoDiff();

                // 1. Update Body (Form) - Always update content
                formContainer.innerHTML = this._renderBody(p, dm, unit, diffResult);

                // 2. Update Header - Only if content changed (Simple Diff)
                const newHeader = this._renderHeader(p, userName);
                if (headerContainer.innerHTML !== newHeader) {
                    headerContainer.innerHTML = newHeader;
                }
            } else {
                Dashboard.renderProfileView();
            }
        }

        // Refresh Sidebar (解决 Sidebar 性别图标不刷新问题)
        if (window.SidebarModule && window.SidebarModule.render) {
            window.SidebarModule.render();
        }
    },
};

// 挂载到全局
window.ProfileRenderModule = ProfileRenderModule;
