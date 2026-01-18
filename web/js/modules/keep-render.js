/**
 * Keep 渲染模块
 *
 * 负责 Keep 数据（体重、睡眠、围度）的 HTML 渲染
 * 挂载到 Dashboard 实例运行
 */

const KeepRenderModule = {
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
      const metricsFields = [
        { key: 'neck', label: '颈围', unit: 'cm' },
        { key: 'bust', label: '胸围', unit: 'cm' },
        { key: 'bust_padded', label: '带义乳胸围', unit: 'cm' },
        { key: 'underbust', label: '下胸围', unit: 'cm' },
        { key: 'shoulder_circ', label: '肩围', unit: 'cm' },
        { key: 'shoulder_width', label: '肩宽', unit: 'cm' },
        { key: 'arm', label: '上臂', unit: 'cm' },
        { key: 'forearm', label: '前臂', unit: 'cm' },
        { key: 'wrist', label: '手腕', unit: 'cm' },
        { key: 'ltorso', label: '坐姿躯干长', unit: 'cm' },
        { key: 'waist', label: '腰围', unit: 'cm' },
        { key: 'upper_hip', label: '上臀围', unit: 'cm' },
        { key: 'hip_circ', label: '臀围', unit: 'cm' },
        { key: 'hip_width', label: '胯宽', unit: 'cm' },
        { key: 'hip_padded', label: '带垫臀围', unit: 'cm' },
        { key: 'thigh', label: '大腿', unit: 'cm' },
        { key: 'calf', label: '小腿', unit: 'cm' },
        { key: 'ankle', label: '脚踝', unit: 'cm' },
        { key: 'legs', label: '内腿长', unit: 'cm' },
        { key: 'feet', label: '脚长', unit: 'cm' },
        { key: 'height', label: '身高', unit: 'cm' },
      ];

      html += `<div class="keep-section"><div class="dishes-title">📏 围度记录</div>`;
      data.bodyMeasureEvents.forEach(e => {
        const detailSpans = metricsFields
          .filter(field => e[field.key] !== undefined && e[field.key] !== null)
          .map(field => `<span>${field.label} ${e[field.key]}${field.unit}</span>`)
          .join('');

        html += `
          <div class="keep-item">
            <div class="keep-details">
              ${detailSpans}
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
};

window.KeepRenderModule = KeepRenderModule;
