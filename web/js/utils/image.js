/**
 * 图片处理工具函数
 * 
 * 从 dashboard.js 抽取的纯工具函数
 * 这些函数无副作用，不依赖 Dashboard 状态
 */

const ImageUtils = {
    // 文件转 Base64（纯数据部分，不含 data:xxx 前缀）
    fileToBase64(file) {
        return new Promise(resolve => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(',')[1]);
            reader.readAsDataURL(file);
        });
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
                console.error('[ImageUtils] Hash calculation failed:', e);
                // 回退方案：使用长度
                hashes.push(`fallback_${img.base64.length}`);
            }
        }
        return hashes;
    },
};

// 挂载到全局
window.ImageUtils = ImageUtils;
