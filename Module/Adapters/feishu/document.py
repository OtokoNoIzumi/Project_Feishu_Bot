"""
飞书云文档模块

注意：
- 当前实现为“同步调用 + 指数退避重试”的版本，明确移除了本模块内的线程与 Future 异步返回。
- 这样做是为了：
  1) 避免返回值语义不清造成的上层 NoneType 访问错误；
  2) 减少异步回调与 UI 构建的时序错位问题；
  3) 保持行为可预期，便于后续若切换到异步客户端时统一重构。
- 若未来需要非阻塞行为，请在“调用方”层面采用异步客户端或任务队列统一调度，不要在本模块内重新引入线程。
"""

import os
import time
import asyncio
from typing import Dict, Any, List, Callable, Optional

from Module.Common.scripts.common import debug_utils
from Module.Services.constants import ServiceNames
from Module.Services.service_decorators import require_service

from lark_oapi.api.drive.v1 import (
    CreateFolderFileRequest,
    CreateFolderFileRequestBody,
    CreateFolderFileResponse,
    ListFileRequest,
    ListFileResponse,
    CreatePermissionMemberRequest,
    BaseMember,
    CreatePermissionMemberResponse,
)

from lark_oapi.api.docx.v1 import (
    CreateDocumentRequest,
    CreateDocumentRequestBody,
    CreateDocumentResponse,
    CreateDocumentBlockDescendantRequest,
    CreateDocumentBlockDescendantResponse,
)


class FeishuDocument:
    """
    飞书云文档模块
    负责飞书云文档、文件夹的创建、更新、删除等操作，文档tokens的新建与读取
    """

    def __init__(self, client, app_controller=None, sender=None):
        """
        初始化飞书云文档模块

        Args:
            client: 飞书SDK客户端
            app_controller: 应用控制器，用于获取配置
        """
        self.client = client
        self.app_controller = app_controller
        self.sender = sender

    # region 基础方法

    def create_folder(self, folder_name: str, folder_token: str):
        """
        创建文件夹
        """
        request: CreateFolderFileRequest = (
            CreateFolderFileRequest.builder()
            .request_body(
                CreateFolderFileRequestBody.builder()
                .name(folder_name)
                .folder_token(folder_token)
                .build()
            )
            .build()
        )
        # 发起请求
        response: CreateFolderFileResponse = self.client.drive.v1.file.create_folder(
            request
        )
        if not response.success():
            debug_utils.log_and_print(
                f"创建文件夹失败: {response.code} - {response.msg}", log_level="ERROR"
            )
            return {}

        return response.data

    def authorize_user_root_folder(self, user_id: str, root_folder_token: str):
        """
        授予用户根目录文件夹所有权限
        """

        request: CreatePermissionMemberRequest = (
            CreatePermissionMemberRequest.builder()
            .token(root_folder_token)
            .type("folder")
            .need_notification(False)
            .request_body(
                BaseMember.builder()
                .member_type("openid")
                .member_id(user_id)
                .perm("full_access")
                .perm_type("container")
                .type("user")
                .build()
            )
            .build()
        )

        # 发起请求
        response: CreatePermissionMemberResponse = (
            self.client.drive.v1.permission_member.create(request)
        )
        if not response.success():
            debug_utils.log_and_print(
                f"授予用户根目录文件夹所有权限失败: {response.code} - {response.msg}",
                log_level="ERROR",
            )
            return False

        return True

    def get_file_list(self, folder_token: str = ""):
        """
        获取文件列表
        """
        request: ListFileRequest = (
            ListFileRequest.builder()
            .page_token(folder_token)
            .order_by("EditedTime")
            .direction("DESC")
            .build()
        )

        # 发起请求
        response: ListFileResponse = self.client.drive.v1.file.list(request)
        if not response.success():
            debug_utils.log_and_print(
                f"获取文件列表失败: {response.code} - {response.msg}", log_level="ERROR"
            )
            return []

        return response.data.files

    def create_document(self, folder_token: str = "", document_title: str = ""):
        """
        创建文档（同步调用，带指数退避重试）

        备注：此方法为同步阻塞，若需要非阻塞，请在更高层使用异步客户端或统一任务调度。

        Args:
            folder_token: 文件夹token
            document_title: 文档标题

        Returns:
            Any: SDK 返回的 data（成功）或 {}（失败）
        """
        request: CreateDocumentRequest = (
            CreateDocumentRequest.builder()
            .request_body(
                CreateDocumentRequestBody.builder()
                .folder_token(folder_token)
                .title(document_title)
                .build()
            )
            .build()
        )

        def call():
            return self.client.docx.v1.document.create(request)

        def is_retryable(result: Optional[Any], exc: Optional[Exception]) -> bool:
            if result is not None:
                # 飞书限频错误码
                return hasattr(result, "code") and str(result.code) == "99991400"
            return False

        describe = f"创建文档【{document_title if document_title else '无标题'}】"
        response: CreateDocumentResponse = self._backoff_retry_sync(
            call,
            is_retryable=is_retryable,
            describe=describe,
        )

        if response and hasattr(response, "success") and response.success():
            return response.data

        if response is not None:
            debug_utils.log_and_print(
                f"{describe}失败: {getattr(response,'code', '')} - {getattr(response,'msg','')}",
                log_level="ERROR",
            )

        return {}

    def create_document_block_descendant(
        self,
        document_id: str,
        block_data: Dict[str, Any],
        block_id: str = "",
        document_title: str = "",
    ):
        """
        创建文档块的子嵌套块（同步调用，带指数退避重试）

        备注：此方法为同步阻塞，若需要非阻塞，请在更高层使用异步客户端或统一任务调度。
        """
        if not block_id:
            # 文档根节点可以省略block_id
            block_id = document_id

        request: CreateDocumentBlockDescendantRequest = (
            CreateDocumentBlockDescendantRequest.builder()
            .document_id(document_id)
            .block_id(block_id)
            .document_revision_id(-1)
            .request_body(block_data)
            .build()
        )

        def call():
            return self.client.docx.v1.document_block_descendant.create(request)

        def is_retryable(result: Optional[Any], exc: Optional[Exception]) -> bool:
            if result is not None:
                # 飞书限频错误码
                return hasattr(result, "code") and str(result.code) == "99991400"
            return False

        response: CreateDocumentBlockDescendantResponse = self._backoff_retry_sync(
            call,
            is_retryable=is_retryable,
            describe=f"创建文档【{document_title}】的内容",
        )

        if response and hasattr(response, "success") and response.success():
            return response.data
        if response is not None:
            debug_utils.log_and_print(
                f"创建文档【{document_title}】的内容失败: {response.code} - {response.msg}",
                log_level="ERROR",
            )
        return {}

    # endregion

    # region 块内容枚举方法

    def create_descendant_block_body(
        self, index: int = 0, children: List[str] = [], descendants: List[str] = []
    ):
        """
        创建块内容，用于创建块的子嵌套块
        """
        block_data = {
            "index": index,
            "children_id": children,
            "descendants": descendants,
        }
        return block_data

    def create_table_block(
        self,
        row_size: int,
        column_size: int,
        block_id: str = "",
        children: List[str] = [],
        column_width: List[int] = [],
        header_row: bool = False,
        header_column: bool = False,
    ):
        """
        创建表格块
        """
        block_data = {
            "block_id": block_id,
            "block_type": 31,
            "table": {
                "property": {
                    "row_size": row_size,
                    "column_size": column_size,
                    "column_width": column_width,
                    "header_row": header_row,
                    "header_column": header_column,
                }
            },
            "children": children,
        }
        return block_data

    def create_table_cell_block(self, block_id: str = "", children: List[str] = []):
        """
        创建表格单元格块
        """
        block_data = {
            "block_id": block_id,
            "block_type": 32,
            "table_cell": {},
            "children": children,
        }
        return block_data

    def create_text_block(
        self,
        block_id: str = "",
        text: str = "",
        background_color: int = -1,
        align: int = 1,
    ):
        """
        创建文本块
        """

        block_data = {
            "block_id": block_id,
            "block_type": 2,
            "text": {
                "elements": [
                    {
                        "text_run": {
                            "content": text,
                        },
                    }
                ],
            },
            "children": [],
        }
        if background_color != -1:
            block_data["text"]["elements"][0]["text_run"]["text_element_style"] = {
                "background_color": background_color,
            }
        if align != 1:
            block_data["text"]["style"] = {
                "align": align,
            }
        return block_data

    FORMATED_TEXT_BLOCK_TYPE = {
        "heading1": 3,
        "heading2": 4,
        "heading3": 5,
        "heading4": 6,
        "heading5": 7,
        "heading6": 8,
        "heading7": 9,
        "heading8": 10,
        "heading9": 11,
    }

    def create_formated_text_block(
        self,
        block_id: str = "",
        text: str = "",
        background_color: int = -1,
        block_type: str = "heading1",
    ):
        """
        创建格式化文本块
        """
        block_data = {
            "block_id": block_id,
            "block_type": self.FORMATED_TEXT_BLOCK_TYPE[block_type],
            block_type: {
                "elements": [
                    {
                        "text_run": {
                            "content": text,
                        },
                    }
                ],
            },
            "children": [],
        }
        if background_color != -1:
            block_data["text"]["elements"][0]["text_run"]["text_element_style"] = {
                "background_color": background_color,
            }
        return block_data

    def create_quote_block(self, block_id: str = "", children: List[str] = []):
        """
        创建引用块
        """
        block_data = {
            "block_id": block_id,
            "block_type": 34,
            "quote_container": {},
            "children": children,
        }
        return block_data

    # endregion

    # region 用户文件夹管理

    def create_user_root_folder(self, user_id: str):
        """
        创建用户根目录文件夹并储存tokens
        """
        folder_name = f"{user_id}的根目录"
        folder_token = ""
        result = self.create_folder(folder_name, folder_token)
        if result:
            self.authorize_user_root_folder(user_id, result.token)
            return result

        return None

    def create_user_business_folder(
        self, root_folder_token: str, business_folder_name: str
    ):
        """
        创建用户业务目录文件夹，并储存tokens
        """
        folder_name = business_folder_name
        folder_token = root_folder_token
        result = self.create_folder(folder_name, folder_token)
        if result:
            return result

        return None

    def get_user_root_folder_token(self, user_id: str):
        """
        获取用户根目录文件夹token
        """

        files = self.get_file_list()
        for file in files:
            if (file.name == f"{user_id}的根目录") and (file.type == "folder"):
                return file.token

        folder_info = self.create_user_root_folder(user_id)
        return folder_info.token

    def get_user_business_folder_token(
        self, user_id: str, business_folder_name: str, root_folder_token: str = ""
    ):
        """
        获取用户业务目录文件夹token
        """

        if not root_folder_token:
            root_folder_token = self.get_user_root_folder_token(user_id)

        files = self.get_file_list(root_folder_token)
        for file in files:
            if (file.name == business_folder_name) and (file.type == "folder"):
                return file.token

        folder_info = self.create_user_business_folder(
            root_folder_token, business_folder_name
        )
        return folder_info.token

    # endregion

    # region 辅助方法

    # 同步退避重试为唯一实现；移除本模块的线程/Future 异步封装

    # 组合型同步方法已移除：仅保留原子化API（create_document 与 create_document_block_descendant）

    # 通用：同步重试退避（仅用于后台线程内调用）
    def _backoff_retry_sync(
        self,
        call: Callable[[], Any],
        *,
        max_retries: int = 5,
        initial_backoff: int = 1,
        max_backoff: int = 16,
        is_retryable: Optional[
            Callable[[Optional[Any], Optional[Exception]], bool]
        ] = None,
        describe: str = "",
    ) -> Any:
        backoff = initial_backoff
        for attempt in range(max_retries):
            try:
                result = call()
                if is_retryable and is_retryable(result, None):
                    debug_utils.log_and_print(
                        f"{describe}限频，{backoff}秒后重试（{attempt+1}/{max_retries}）",
                        log_level="WARNING",
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
                    continue
                return result
            except Exception as e:
                if is_retryable and is_retryable(None, e):
                    debug_utils.log_and_print(
                        f"{describe}异常可重试：{str(e)}，{backoff}秒后重试（{attempt+1}/{max_retries}）",
                        log_level="WARNING",
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
                    continue
                debug_utils.log_and_print(
                    f"{describe}异常: {str(e)}", log_level="ERROR"
                )
                return None
        debug_utils.log_and_print(f"{describe}多次限频重试后仍失败", log_level="ERROR")
        return None

    # endregion

    # 这是一些功能逻辑规划
    # 创建用户根目录文件夹并储存tokens，但documents模块本身不管理tokens，由用户模块来实现
    # 授予用户根目录文件夹所有权限
    # 创建用户业务目录文件夹，并储存tokens
    # 在业务目录文件夹下创建文档
