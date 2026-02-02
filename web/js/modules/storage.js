/**
 * Storage 存储模块
 * 
 * 处理记录保存、历史列表管理
 * 挂载到 Dashboard 实例运行
 */

const StorageModule = {
    async saveRecord() {
        if (!this.currentSession) return;
        if (typeof Auth !== 'undefined' && Auth.isDemoMode()) {
            if (typeof this.checkDemoLimit === 'function' && this.checkDemoLimit()) return;
            if (window.ToastUtils) {
                ToastUtils.show('演示模式下无法保存，注册即可免费体验 3 天', 'info');
            }
            if (window.Auth && typeof window.Auth.openSignUp === 'function') {
                window.Auth.openSignUp();
            }
            return;
        }

        const session = this.currentSession;
        const isUpdate = !!session.savedRecordId;

        try {


            this.updateStatus('');


            // UI Update: Disable buttons implicitly via loading status or let user wait
            // FooterModule operations should be handled by updateButtonStates at the end


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
            // 兼容 Diet (result.saved_record.record_id) 和 Keep (result.record_id)
            if (result.saved_record && result.saved_record.record_id) {
                session.savedRecordId = result.saved_record.record_id;
            } else if (result.record_id) {
                session.savedRecordId = result.record_id;
            }

            // [Fix] 同步后端确定的 occurred_at，防止后续更新时时间被重置
            // 注意：API.saveDiet 可能直接返回 RecordService 的结果，或者包装了一层
            // 直接检查 result 或 result.saved_record (取决于 API 包装)
            const savedTime = result.occurred_at || (result.saved_record && result.saved_record.occurred_at);

            if (savedTime && session.mode === 'diet' && this.currentDietMeta) {
                this.currentDietMeta.occurredAt = savedTime;
                // 同时更新当前 Version 的 parsedData，确保持久化 Card 时带上时间
                const currentVer = session.versions[session.currentVersion - 1];
                if (currentVer && currentVer.parsedData) {
                    currentVer.parsedData.occurredAt = savedTime;
                }
            }

            session.isSaved = true;
            if (session.mode === 'diet') {
                // 保存一份副本用于 isDataUnchanged 对比
                session.savedData = JSON.parse(JSON.stringify(this.collectEditedData()));
            }

            // 确保持久化 (并将 Quick Record 转正)
            if (typeof this._ensureCardPersisted === 'function') {
                await this._ensureCardPersisted(session);
            } else if (session.persistentCardId && typeof this._buildCardData === 'function') {
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
            this.renderResult(session); // Re-render to show Header Buttons (State 2.3)
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
            this.updateStatus('');

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
