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

            // 将保存状态回写到 Card，避免重复保存
            if (session.persistentCardId && typeof this._buildCardData === 'function') {
                const cardData = this._buildCardData(session);
                if (cardData) {
                    cardData.status = 'saved';
                    cardData.saved_record_id = session.savedRecordId || null;
                    cardData.updated_at = new Date().toISOString();
                    await API.updateCard(session.persistentCardId, cardData).catch(e => {
                        console.warn('Update card save status failed:', e);
                    });
                }
            }

            this.updateStatus('saved');
            this.addMessage(isUpdate ? '✓ 记录已更新' : '✓ 记录已保存', 'assistant');
            this.updateButtonStates(session);

            // 刷新 Sidebar 以显示新保存的记录
            if (window.SidebarModule) {
                // 重新加载最近卡片 (包括刚保存的)
                window.SidebarModule.loadRecentCards();
                // 如果是新创建的 Record 且关联了 Dialogue，可能需要刷新 Dialogue List 或 Sidebar 状态
                // 但通常 loadRecentCards 足够刷新顶部 "最近分析记录"
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

    // Legacy Methods (Phase 1) - Deprecated
    loadHistory() {
        // No-op in Phase 2
    },

    addHistoryItem(session) {
        // No-op in Phase 2
    },
};

window.StorageModule = StorageModule;
