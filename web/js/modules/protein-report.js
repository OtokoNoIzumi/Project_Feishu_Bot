/**
 * Protein Report Module
 * 进阶功能：蛋白质价值评估报告
 * 
 * Update 2026-01-31 (v7):
 * - Collision Logic: Implemented "Right-to-Left" greedy selection to prevent over-hiding.
 * - Legend: Clean style (Dot + Name only). No emoji, no "Red Dot" emoji.
 * - Chart Labels: Restore Emojis (Icon + Name).
 */
const ProteinReportModule = {
    showAllLabels: false,
    _lastTotals: null,

    rawFoodData: [
        {
            id: 'combo_oat_milk',
            name: '燕麦奶',
            icon: '🥛',
            measure_mode: 'per_serving',
            unit_price: 2.72,
            serving_weight: 314,
            label_macros: { e: 998.1, p: 14.41, f: 3.64 },
            color: '#55efc4', text: '#00b894',
            isSystem: true
        },
        {
            id: 'chicken_breast',
            name: '鸡胸',
            icon: '🍗',
            measure_mode: 'per_100g',
            unit_price: 2.45,
            serving_weight: 50,
            label_macros: { e: 450, p: 23.7, f: 1.0 },
            color: '#a29bfe', text: '#6c5ce7',
            isSystem: true
        },
        {
            id: 'chicken_leg',
            name: '鸡腿',
            icon: '🍗',
            measure_mode: 'per_100g',
            unit_price: 4.1,
            serving_weight: 80,
            label_macros: { e: 629, p: 23.6, f: 5.0 },
            color: '#74b9ff', text: '#0984e3',
            isSystem: true
        },
        {
            id: 'beef',
            name: '牛肉',
            icon: '🥩',
            measure_mode: 'per_100g',
            unit_price: 6.7,
            serving_weight: 50,
            label_macros: { e: 552, p: 29.4, f: 1.4 },
            color: '#ff7675', text: '#d63031',
            isSystem: true
        },
        {
            id: 'egg_braised',
            name: '卤蛋',
            icon: '🥚',
            measure_mode: 'per_100g',
            unit_price: 0.87,
            serving_weight: 33,
            label_macros: { e: 741, p: 15.7, f: 10.8 },
            color: '#ffd93d', text: '#f39c12',
            isSystem: true
        }
    ],

    markPrice(session) {
        if (window.MealsDataModule && window.MealsDataModule.showPriceInputModal) {
            window.MealsDataModule.showPriceInputModal(session, (price) => {
                if (window.ToastUtils) ToastUtils.show(`已标记金额: ${price}`, 'success');
                // TODO: Save this price to session logic (e.g. session.markedPrice = price; API.save...)
            });
        } else {
            // 无 Modal 模块时，显示提示
            if (window.ToastUtils) ToastUtils.show('金额标记功能暂不可用', 'info');
        }
    },

    injectStyles() {
        if (document.getElementById('pr-styles')) return;
        const css = `
            .pr-modal-overlay {
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background: rgba(0,0,0,0.5); z-index: 2000;
                display: flex; justify-content: center; align-items: center;
                backdrop-filter: blur(4px);
                opacity: 0; animation: pr-fade-in 0.3s forwards;
            }
            .pr-container {
                background: white; border-radius: 12px; padding: 24px;
                max-width: 800px; width: 95%; max-height: 90vh; overflow-y: auto;
                box-shadow: 0 10px 30px rgba(0,0,0,0.15);
                position: relative; transform: translateY(20px);
                animation: pr-slide-up 0.3s forwards;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            .pr-close-btn {
                position: absolute; top: 16px; right: 16px;
                background: none; border: none; font-size: 24px; color: #999;
                cursor: pointer; transition: color 0.2s; line-height: 1;
            }
            .pr-close-btn:hover { color: #333; }
            
            .pr-h2 {
                font-size: 18px; color: #333; margin-bottom: 24px;
                display: flex; align-items: center; gap: 8px; font-weight: 600;
            }
            
            .pr-metric-group { margin-bottom: 56px; position: relative; }
            .pr-metric-title { font-size: 14px; color: #666; margin-bottom: 30px; font-weight: 500; }
            
            .pr-axis-container { position: relative; height: 90px; margin-bottom: 8px; user-select: none; }
            .pr-axis-line {
                position: absolute; top: 40px; left: 0; right: 0;
                height: 2px; background: #e0e0e0; border-radius: 1px;
            }
            
            .pr-data-point {
                position: absolute; transform: translateX(-50%);
                display: flex; flex-direction: column; align-items: center;
                cursor: pointer; transition: all 0.2s;
                top: 40px; 
            }
            .pr-data-point:hover { z-index: 100 !important; }
            .pr-data-point:hover .pr-point-marker { transform: scale(1.3); }
            
            .pr-point-marker {
                width: 12px; height: 12px; border-radius: 50%;
                border: 2px solid white;
                box-shadow: 0 2px 4px rgba(0,0,0,0.15);
                transition: transform 0.2s;
                position: absolute; top: -6px;
            }
            
            .pr-point-label {
                position: absolute; font-size: 11px; white-space: nowrap; color: #666;
                transition: top 0.2s;
            }
            .pr-point-value {
                position: absolute; font-size: 12px; font-weight: 600;
                transition: top 0.2s;
            }

            .pr-layout-bottom .pr-point-label { top: 12px; }
            .pr-layout-bottom .pr-point-value { top: 28px; }

            .pr-layout-top .pr-point-label { top: -28px; }
            .pr-layout-top .pr-point-value { top: -46px; }
            
            .pr-meal-point { z-index: 50; }
            .pr-meal-point .pr-point-marker { 
                width: 16px; height: 16px; top: -8px;
                background: #ff6b6b; border: 3px solid white;
                box-shadow: 0 2px 6px rgba(255, 107, 107, 0.4);
            }
            .pr-meal-point .pr-point-label { color: #ff6b6b; font-weight: 700; }
            .pr-meal-point .pr-point-value { font-weight: 800; color: #ff6b6b; font-size: 13px; }

            .pr-tip-box {
                position: absolute; 
                background: rgba(0,0,0,0.8); color: white;
                padding: 0; border-radius: 6px; font-size: 12px;
                pointer-events: none; opacity: 0; transition: opacity 0.2s;
                z-index: 200; white-space: nowrap;
                top: -50px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(0,0,0,0.2);
                min-width: 140px;
            }
            .pr-align-center .pr-tip-box { left: 50%; transform: translateX(-50%); }
            .pr-align-left .pr-tip-box { left: -10px; transform: none; }
            .pr-align-right .pr-tip-box { right: -10px; transform: none; }

            .pr-data-point:hover .pr-tip-box { opacity: 1; }
            
            .pr-tip-header {
                padding: 6px 10px; font-weight: 600; 
                display: flex; align-items: center; gap: 6px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .pr-tip-body { padding: 8px 10px; }
            .pr-tip-row { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 2px; }
            
            .pr-footer {
                margin-top: 10px; padding-top: 16px; border-top: 1px solid #eee;
                display: flex; flex-direction: column; gap: 12px;
            }
            .pr-footer-row {
                display: flex; justify-content: space-between; align-items: center;
                flex-wrap: wrap; gap: 12px;
            }
            
            .pr-toggle-label { font-size: 12px; color: #666; margin-right: 8px; cursor: pointer;}
            .pr-toggle-switch {
                position: relative; width: 36px; height: 20px;
                background: #ccc; border-radius: 20px; cursor: pointer; transition: background 0.2s;
            }
            .pr-toggle-switch.active { background: #ff6b6b; }
            .pr-toggle-dot {
                position: absolute; top: 2px; left: 2px;
                width: 16px; height: 16px; background: white; border-radius: 50%; transition: transform 0.2s;
            }
            .pr-toggle-switch.active .pr-toggle-dot { transform: translateX(16px); }

            .pr-legend { 
                display: flex; gap: 12px 16px; flex-wrap: wrap; 
                padding-right: 8px;
            }
            .pr-legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #666; white-space: nowrap; }
            .pr-legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

            .pr-hint {
                font-size: 12px; color: #95a5a6; 
                background: #f8f9fa; border-radius: 6px; display: inline-block;
                padding: 8px 12px; margin-top: 8px;
                width: 100%; box-sizing: border-box;
            }

            @keyframes pr-fade-in { from { opacity: 0; } to { opacity: 1; } }
            @keyframes pr-slide-up { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
            
            @media (max-width: 600px) { 
                .pr-container { padding: 16px; padding-bottom: 24px; } 
                .pr-footer-row { flex-direction: column-reverse; align-items: flex-start; gap: 16px; }
                .pr-controls-container { align-self: flex-end; }
                .pr-legend { gap: 8px 12px; }
            }
        `;
        const style = document.createElement('style');
        style.id = 'pr-styles';
        style.textContent = css;
        document.head.appendChild(style);
    },

    getNormalizedAnchors() {
        return this.rawFoodData.map(item => {
            let p_g = 0;
            const { e, p, f } = item.label_macros;

            if (item.measure_mode === 'per_100g') {
                const ratio = item.serving_weight / 100;
                p_g = p * ratio;
            } else {
                p_g = p;
            }

            let pe = e > 0 ? (p / (e / 100)) : 0;
            let pf = f > 0 ? (p / f) : (p > 0 ? 99 : 0);
            const pricePerGProtein = p_g > 0 ? (item.unit_price / p_g) : 999;

            return {
                ...item,
                pe: parseFloat(pe.toFixed(2)),
                pf: parseFloat(pf.toFixed(2)),
                pricePerGProtein
            };
        });
    },

    calculateMealMetrics(totals) {
        const p = Number(totals.totalProtein) || 0;
        const f = Number(totals.totalFat) || 0;
        const e_kj = Number(totals.totalEnergyKJ) || 0;

        let pe = e_kj > 0 ? (p / (e_kj / 100)) : 0;
        let pf = f > 0 ? (p / f) : (p > 0 ? 24.0 : 0);

        return {
            pe: parseFloat(pe.toFixed(2)),
            pf: parseFloat(pf.toFixed(2)),
            p_total: p
        };
    },

    toggleShowAll() {
        this.showAllLabels = !this.showAllLabels;
        if (this._lastTotals) this.render(this._lastTotals, true);
    },

    resolveCollisions(points) {
        if (this.showAllLabels) return points;

        // List-Order Priority Strategy (First-Come-First-Served)
        // Item appearing earlier in the list has higher priority.
        // We iterate effectively in the list order (since points are mapped from rawFoodData).

        const visiblePoints = [];

        // 1. Determine visibility based on Priority Order
        // 移动端屏幕窄，需要更大的防重叠阈值 (14%)，PC端保持 6%
        const threshold = window.innerWidth < 600 ? 14 : 6;

        for (const p of points) {
            let isCollision = false;
            for (const v of visiblePoints) {
                // Check distance against already visible (higher priority) points
                if (Math.abs(p.pct - v.pct) < threshold) {
                    isCollision = true;
                    break;
                }
            }

            if (!isCollision) {
                p.hidden = false;
                visiblePoints.push(p);
            } else {
                p.hidden = true;
            }
        }

        // 2. Sort by PCT for consistent Left-to-Right DOM rendering
        // (Visual layout is absolute, but DOM order helps with z-index/debugging)
        points.sort((a, b) => a.pct - b.pct);

        return points;
    },

    render(totals, isUpdate = false) {
        if (!totals) return;
        this._lastTotals = totals;

        if (!isUpdate) this.injectStyles();

        const anchors = this.getNormalizedAnchors();
        const metrics = this.calculateMealMetrics(totals);

        // Track which items are actually visible across all charts
        const visibleIds = new Set();

        const html = `
            ${!isUpdate ? `<div class="pr-modal-overlay" onclick="ProteinReportModule.close(event)"><div class="pr-container" onclick="event.stopPropagation()">` : ''}
                    ${!isUpdate ? `<button class="pr-close-btn" onclick="ProteinReportModule.close()">&times;</button>` : ''}
                    <div class="pr-h2">🎯 蛋白质价值评估</div>
                    
                    ${this.renderChartSection(
            '📊 蛋白质/能量比 (g/100kJ) - 越高越优',
            anchors, metrics.pe, 'pe',
            { min: 1.0, max: 6.0 },
            (item, meal) => this.getTipContent(item, meal, '倍'),
            visibleIds
        )}
                    
                    ${this.renderChartSection(
            '💪 蛋白质/脂肪比 (g:g) - 越高越增肌',
            anchors, metrics.pf, 'pf',
            { min: 0, max: 25.0 },
            (item, meal) => this.getTipContent(item, meal, '倍'),
            visibleIds
        )}
                    
                    ${this.renderPriceSection(anchors, metrics.p_total, visibleIds)}

                    <div class="pr-footer">
                        <div class="pr-footer-row">
                             <div class="pr-legend">
                                 <div class="pr-legend-item">
                                    <div class="pr-legend-dot" style="background: #ff6b6b"></div>
                                    <span>本餐</span>
                                </div>
                                <div class="pr-legend-item"><span style="color:#eee">|</span></div>
                                ${anchors.map(a => {
            if (!visibleIds.has(a.id)) return '';
            return `
                                    <div class="pr-legend-item">
                                        <div class="pr-legend-dot" style="background: ${a.color}"></div>
                                        <span>${a.name}</span>
                                    </div>
                                `;
        }).join('')}
                            </div>
                            
                            <div class="pr-controls-container" style="display:flex; align-items:center" onclick="ProteinReportModule.toggleShowAll()">
                                <span class="pr-toggle-label">展示全部标签</span>
                                <div class="pr-toggle-switch ${this.showAllLabels ? 'active' : ''}">
                                    <div class="pr-toggle-dot"></div>
                                </div>
                            </div>
                        </div>
                    </div>
            ${!isUpdate ? `</div></div>` : ''}
        `;

        if (isUpdate) {
            const container = document.querySelector('.pr-container');
            if (container) container.innerHTML = html;
        } else {
            this.close();
            const div = document.createElement('div');
            div.id = 'protein-report-modal';
            div.innerHTML = html;
            document.body.appendChild(div);
        }
    },

    close(e) {
        const el = document.getElementById('protein-report-modal');
        if (el) el.remove();
        this.showAllLabels = false;
    },

    getAlignClass(pct) {
        if (pct < 15) return 'pr-align-left';
        if (pct > 85) return 'pr-align-right';
        return 'pr-align-center';
    },

    getTipContent(item, mealVal, suffix = '') {
        const baseVal = item.val;
        const ratio = mealVal > 0 ? (baseVal / mealVal).toFixed(1) : '-';
        return `
            <div class="pr-tip-header" style="background: ${item.color}33; color: ${item.text}">
                <span>${item.icon} ${item.name}</span>
            </div>
            <div class="pr-tip-body">
                <div class="pr-tip-row"><span>本餐数值:</span> <span>${mealVal}</span></div>
                <div class="pr-tip-row"><span>基准数值:</span> <span>${baseVal}</span></div>
                <div style="margin-top:4px; color:#ddd; font-style:italic">
                    ${baseVal > mealVal ? `基准比本餐高 ${ratio}${suffix}` : `本餐比基准高 ${(mealVal / baseVal).toFixed(1)}${suffix}`}
                </div>
            </div>
        `;
    },

    renderChartSection(title, anchors, mealVal, key, range, tipGenFn, visibleIds) {
        const { min, max } = range;

        let anchorPoints = anchors.map(a => ({
            ...a,
            val: a[key],
            pct: this.getPct(a[key], min, max),
        }));

        this.resolveCollisions(anchorPoints);

        // Track visible items
        if (visibleIds) {
            anchorPoints.forEach(p => {
                if (!p.hidden) visibleIds.add(p.id);
            });
        }

        const anchorHtml = anchorPoints.map(p => {
            if (p.hidden) return '';
            const alignClass = this.getAlignClass(p.pct);
            return `
                <div class="pr-data-point pr-layout-bottom ${alignClass}" style="left: ${p.pct}%">
                    <div class="pr-tip-box">${tipGenFn(p, mealVal)}</div>
                    <div class="pr-point-label">${p.icon} ${p.name}</div>
                    <div class="pr-point-value" style="color: ${p.text}">${p.val}</div>
                    <div class="pr-point-marker" style="background: ${p.color}"></div>
                </div>
            `;
        }).join('');

        const mealPct = this.getPct(mealVal, min, max);
        const mealHtml = `
            <div class="pr-data-point pr-meal-point pr-layout-top" style="left: ${mealPct}%">
                <div class="pr-point-value">${mealVal}</div>
                <div class="pr-point-label">本餐</div>
                <div class="pr-point-marker"></div>
            </div>
        `;

        return `
            <div class="pr-metric-group">
                <div class="pr-metric-title">${title}</div>
                <div class="pr-axis-container">
                    <div class="pr-axis-line"></div>
                    ${anchorHtml}
                    ${mealHtml}
                </div>
            </div>
        `;
    },

    renderPriceSection(anchors, currentProteinG, visibleIds) {
        const targetP = currentProteinG > 0 ? currentProteinG : 52.7;

        let anchorPoints = anchors.map(a => {
            const equivPrice = parseFloat((a.pricePerGProtein * targetP).toFixed(1));
            return {
                ...a,
                val: equivPrice,
            };
        });

        // Dynamic Range Calculation
        const values = anchorPoints.map(p => p.val);
        let dataMin = Math.min(...values);
        let dataMax = Math.max(...values);

        // 防止范围过小
        if (dataMax - dataMin < 2) {
            dataMin -= 1;
            dataMax += 1;
        } else {
            const padding = (dataMax - dataMin) * 0.1;
            dataMin -= padding;
            dataMax += padding;
        }

        const axisMin = Math.max(0, dataMin);
        const axisMax = Math.max(axisMin + 0.1, dataMax);

        anchorPoints.forEach(p => p.pct = this.getPct(p.val, axisMin, axisMax));
        this.resolveCollisions(anchorPoints);

        // Track visible items
        if (visibleIds) {
            anchorPoints.forEach(p => {
                if (!p.hidden) visibleIds.add(p.id);
            });
        }

        const anchorHtml = anchorPoints.map(p => {
            if (p.hidden) return '';
            const alignClass = this.getAlignClass(p.pct);

            const tip = `
                 <div class="pr-tip-header" style="background: ${p.color}33; color: ${p.text}">
                    <span>${p.icon} ${p.name}</span>
                </div>
                <div class="pr-tip-body">
                    <div class="pr-tip-row"><span>等价花费:</span> <span>${p.val}元</span></div>
                    <div style="margin-top:2px; color:#aaa; font-size:10px">获得 ${Math.round(targetP)}g 蛋白质</div>
                </div>
            `;
            return `
                <div class="pr-data-point pr-layout-bottom ${alignClass}" style="left: ${p.pct}%">
                    <div class="pr-tip-box">${tip}</div>
                    <div class="pr-point-marker" style="background: ${p.color}"></div>
                    <div class="pr-point-label">${p.icon} ${p.name}</div>
                    <div class="pr-point-value" style="color: ${p.text}">${p.val}</div>
                </div>
            `;
        }).join('');

        return `
            <div class="pr-metric-group" style="margin-bottom: 24px;">
                <div class="pr-metric-title">💰 等价价格（基于本餐蛋白质${Math.round(targetP)}g）- 越低越划算</div>
                <div class="pr-axis-container">
                    <div class="pr-axis-line"></div>
                    ${anchorHtml}
                </div>
            </div>
        `;
    },

    getPct(val, min, max) {
        let pct = (val - min) / (max - min) * 100;
        if (pct < 2) pct = 2;
        if (pct > 98) pct = 98;
        return pct.toFixed(1);
    }
};

window.ProteinReportModule = ProteinReportModule;
