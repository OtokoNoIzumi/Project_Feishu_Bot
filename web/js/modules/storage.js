/**
 * Storage 存储模块
 * 
 * 处理记录保存、历史列表管理
 * 挂载到 Dashboard 实例运行
 */

const StorageModule = {
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
                // 获取最新版本的结果
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
                // 保存一份副本用于 isDataUnchanged 对比
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
            console.error('Save error:', error);
            this.addMessage(`${isUpdate ? '更新' : '保存'}失败: ${error.message}`, 'assistant');
        } finally {
            if (this.el.saveBtn) {
                this.el.saveBtn.disabled = false;
            }
            this.updateButtonStates(session);
        }
    },

    // 确定 Keep 事件类型
    determineKeepEventType(parsedData) {
        // 由于现在默认使用 Unified Keep API，返回的数据结构总是包含 scale_events/sleep_events 等列表
        // 因此统一使用 'unified' 类型进行保存，让后端负责把这些列表拆包存入数据库
        // 这样可以同时支持单张图里包含多条数据（如同时有体重和睡眠）的情况
        return 'unified';
    },

    loadHistory() {
        const today = new Date().toLocaleDateString('zh-CN');
        if (this.el.historyList) {
            this.el.historyList.innerHTML = `
        <div class="history-section-title">今天 ${today}</div>
        <div class="history-item placeholder">暂无记录</div>
        `;
        }
    },

    addHistoryItem(session) {
        if (!this.el.historyList) return;

        const list = this.el.historyList;
        const placeholder = list.querySelector('.placeholder');
        if (placeholder) placeholder.remove();

        const item = document.createElement('div');
        item.className = 'history-item';
        item.dataset.sessionId = session.id;

        if (session.mode === 'diet') {
            const ver = session.versions[session.versions.length - 1];
            const unit = this.getEnergyUnit();
            // 这里 ver.parsedData 可能未定义，如果保存时处于 loading 状态（不应该发生）
            // 假设已分析完成
            if (ver && ver.parsedData) {
                const val = unit === 'kcal'
                    ? Math.round(Number(ver.parsedData.summary.totalEnergy))
                    : Math.round(this.kcalToKJ(Number(ver.parsedData.summary.totalEnergy)));
                item.textContent = `${val} ${unit}`;
            } else {
                item.textContent = 'Diet 记录';
            }
        } else {
            item.textContent = 'Keep 记录';
        }

        item.onclick = () => this.selectSession(session.id);
        list.appendChild(item);
    },
};

window.StorageModule = StorageModule;
