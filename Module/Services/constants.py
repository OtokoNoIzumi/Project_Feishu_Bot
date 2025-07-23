"""
服务层常量定义

集中管理所有硬编码字符串，避免分散在各处的字符串字面量
"""

# ========== 服务名称常量 ==========
class ServiceNames:
    CONFIG = "config"
    PENDING_CACHE = "pending_cache"
    IMAGE = "image"
    AUDIO = "audio"
    NOTION = "notion"
    SCHEDULER = "scheduler"
    ROUTER = "router"
    LLM = "llm"
    CACHE = "cache"
    MESSAGE_AGGREGATION = "message_aggregation"
    USER_BUSINESS_PERMISSION = "user_business_permission"
    BILI_ADSKIP = "bili_adskip"

# ========== UI类型常量 ==========
class UITypes:
    INTERACTIVE_CARD = "interactive_card"
    PAGE = "page"
    DIALOG = "dialog"


# ========== 操作类型常量 (operation_type) ==========
class OperationTypes:
    """业务操作类型，用于区分不同的业务逻辑"""
    UPDATE_USER = "update_user"
    UPDATE_ADS = "update_ads"
    BILI_VIDEO = "bili_video_menu"

# ========== 默认动作常量 ==========
class DefaultActions:
    CONFIRM = "confirm"
    CANCEL = "cancel"

# ========== 消息类型常量 ==========
class MessageTypes:
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    MENU_CLICK = "menu_click"
    CARD_ACTION = "card_action"

class MenuClickTypes:
    GET_BILI_URL = "get_bili_url"
    NEW_ROUTINE = "new_routine_record"

# ---------- Buisiness层常量--------------
# ========== ProcessResult类型常量 ==========
class ResponseTypes:
    ADMIN_CARD_SEND = "admin_card_send"
    ADMIN_CARD_UPDATE = "admin_card_update"
    BILI_CARD_UPDATE = "bili_card_update"
    BILI_VIDEO_CARD = "bili_video_card"
    SCHEDULER_CARD_UPDATE_BILI_BUTTON = "scheduler_card_update_bili_button"
    DESIGN_PLAN_SUBMIT = "design_plan_submit"
    DESIGN_PLAN_CANCEL = "design_plan_cancel"
    DESIGN_PLAN_CARD = "design_plan_card"
    DESIGN_PLAN_ACTION = "design_plan_action"

    RICH_TEXT = "rich_text"
    IMAGE_LIST = "image_list"
    BILI_VIDEO_DATA = "bili_video_data"
    INTERACTIVE = "interactive"
    TOAST = "toast"
    NO_REPLY = "no_reply"
    ERROR = "error"
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    ASYNC_ACTION = "async_action"

class ProcessResultConstKeys:
    NEXT_ACTION = "next_action"

class ProcessResultNextAction:
    PROCESS_TTS = "process_tts"
    PROCESS_IMAGE_GENERATION = "process_image_generation"
    PROCESS_IMAGE_CONVERSION = "process_image_conversion"
    PROCESS_BILI_VIDEO = "process_bili_video"

# ========== 用户界面元素常量 ==========
class UIElements:
    """用户界面元素类型"""
    BUTTON = "button"
    SELECT_STATIC = "select_static"
    INPUT = "input"

# ========== 数据字段名常量 ==========
class FieldNames:
    """数据结构字段名称"""
    USER_ID = "user_id"
    USER_TYPE = "user_type"
    ADMIN_INPUT = "admin_input"
    HOLD_TIME = "hold_time"
    FINISHED = "finished"
    RESULT = "result"
    OPERATION_TYPE = "operation_type"
    ACTION = "action"
    VALUE = "value"
    OPTION = "option"
    TAG = "tag"
    OPEN_MESSAGE_ID = "open_message_id"
    OPEN_CHAT_ID = "open_chat_id"

# ========== 错误和提示消息常量 ==========
class Messages:
    """错误和提示消息"""
    # 错误消息
    NEW_MESSAGE_SEND_FAILED = "❌ 新消息发送失败"
    IMAGE_GENERATING = "正在生成图片，请稍候..."
    OPERATION_SUCCESS = "操作成功"
    OPERATION_FAILED = "操作失败"
    OPERATION_CANCELLED = "❌ 操作已取消"
    VIDEO_MARKED_READ = "视频成功设置为已读"

    # 命令提示
    HELP_COMMAND = "帮助"
    GREETING_COMMAND = "你好"
    RICH_TEXT_COMMAND = "富文本"
    IMAGE_COMMAND = "图片"
    WALLPAPER_COMMAND = "壁纸"
    BILI_COMMAND = "B站"
    VIDEO_COMMAND = "视频"
    TTS_PREFIX = "配音"
    IMAGE_GEN_PREFIX = "生图"
    AI_DRAW_PREFIX = "AI画图"

# ========== 环境变量名常量 ==========
class EnvVars:
    """环境变量名称"""
    FEISHU_APP_MESSAGE_ID = "FEISHU_APP_MESSAGE_ID"
    FEISHU_APP_MESSAGE_SECRET = "FEISHU_APP_MESSAGE_SECRET"
    ADMIN_ID = "ADMIN_ID"
    BILI_API_BASE = "BILI_API_BASE"
    ADMIN_SECRET_KEY = "ADMIN_SECRET_KEY"

# ========== 配置键名常量 ==========
class ConfigKeys:
    """配置文件键名"""
    ADMIN_ID = "admin_id"
    UPDATE_CONFIG_TRIGGER = "update_config_trigger"
    CARDS = "cards"
    DEFAULT = "default"

# ========== 回复模式常量 ==========
class ReplyModes:
    """消息回复模式"""
    NEW = "new"
    REPLY = "reply"
    THREAD = "thread"

# ========== 聊天类型常量 ==========
class ChatTypes:
    """聊天类型"""
    GROUP = "group"
    PRIVATE = "p2p"

# ========== 接收者ID类型常量 ==========
class ReceiverIdTypes:
    """接收者ID类型"""
    OPEN_ID = "open_id"
    CHAT_ID = "chat_id"

# ========== Toast类型常量 ==========
class ToastTypes:
    """Toast提示类型"""
    SUCCESS = "success"
    ERROR = "error"
    INFO = "info"
    WARNING = "warning"

# ========== 默认值常量 ==========
class DefaultValues:
    """默认值常量"""
    UNKNOWN_USER = "用户_未知"
    UNKNOWN_ACTION = "unknown_action"
    UNKNOWN_INPUT_ACTION = "unknown_input_action"
    DEFAULT_BILI_API_BASE = "https://localhost:3000"
    DEFAULT_ADMIN_SECRET = "izumi_the_beauty"
    DEFAULT_UPDATE_TRIGGER = "whisk令牌"
    SINGLE_SPACE = " "
    EMPTY_STRING = ""

# ========== 业务常量 ==========
class BusinessConstants:
    """业务相关常量"""
    # 用户类型
    USER_TYPE_NORMAL = 0
    USER_TYPE_SUPPORTER = 1
    USER_TYPE_INVITED = 2

    # 用户类型显示名称
    USER_TYPE_NAMES = {
        0: "普通用户",
        1: "支持者",
        2: "受邀用户"
    }

    # 操作超时时间 (秒) - 注意：具体业务超时时间已移至配置化管理
    DEFAULT_OPERATION_TIMEOUT = 30  # 仅作为配置缺失时的备用默认值

# ---------- 服务层常量 ----------
# ========== Scheduler常量 ==========
class SchedulerTaskTypes:
    DAILY_SCHEDULE = "daily_schedule"
    BILI_UPDATES = "bili_updates"
    PERSONAL_STATUS_EVAL = "personal_status_eval"  # 个人状态评估
    WEEKLY_REVIEW = "weekly_review"               # 周度盘点
    MONTHLY_REVIEW = "monthly_review"             # 月度盘点

class SchedulerConstKeys:
    SCHEDULER_TYPE = "scheduler_type"
    ADMIN_ID = "admin_id"

# ---------- 卡片模块 ----------
# ========== 卡片配置类型常量 (card_config_type) ==========
class CardConfigKeys:
    """卡片配置键名，与配置文件card_configs对应"""
    USER_UPDATE = "user_update"
    ADS_UPDATE = "ads_update"
    BILIBILI_VIDEO_INFO = "bilibili_video_info"
    DESIGN_PLAN = "design_plan"
    ROUTINE_QUICK_SELECT = "routine_quick_select"
    ROUTINE_QUERY = "routine_query"
    ROUTINE_RECORD = "routine_record"

    ROUTINE_RECORD_OLD = "routine_record_old"

# ========== 卡片操作类型常量 ==========
class CardOperationTypes:
    SEND = "send"
    UPDATE_RESPONSE = "update_response"

# ========== 卡片动作名称常量 ==========
class CardActions:
    """卡片按钮动作名称"""
    # 通用动作
    CANCEL = "cancel"
    CONFIRM = "confirm"

    # AI路由动作
    EDIT_CONTENT = "edit_content"

    # B站视频动作
    MARK_BILI_READ = "mark_bili_read"

    # 管理员动作 - 用户管理--待配合admin一起改，遗留部分
    CONFIRM_USER_UPDATE = "confirm_user_update"
    CANCEL_USER_UPDATE = "cancel_user_update"
    UPDATE_USER_TYPE = "update_user_type"

    # 管理员动作 - 广告管理
    CONFIRM_ADS_UPDATE = "confirm_ads_update"
    CANCEL_ADS_UPDATE = "cancel_ads_update"
    ADTIME_EDITOR_CHANGE = "adtime_editor_change"

    # 设计方案动作
    CONFIRM_DESIGN_PLAN = "confirm_design_plan"
    CANCEL_DESIGN_PLAN = "cancel_design_plan"

# ========== 设计方案相关常量 ==========
class DesignPlanConstants:
    """设计方案业务常量"""
    # 快速拔插开关（测试用）
    CARD_ENABLED = True

    # 表单字段映射
    FORM_FIELD_MAP = {
        'customer_name': 'AISmart_Input_custom_name',
        'phone_number': 'AISmart_Input_custom_contact',
        'address': 'AISmart_Input_address',
        'address_detail': 'AISmart_Input_address_house_detail',
        'room_type': 'AISmart_Select_room_type',
        'brand_type': 'AISmart_Select_brand_type',
        'set_type': 'AISmart_Select_set_type',
        'install_type': 'AISmart_Select_install_type',
        'service_type': 'AISmart_Select_service_type',
        'room_status': 'AISmart_Select_room_status'
    }

# =adpter常量=
class AdapterNames:
    FEISHU = "feishu"

# ========== 路由类型常量 ==========
class RouteTypes:
    BILI_VIDEO_CARD = "bili_video_card"

    # Routine相关路由类型
    ROUTINE_NEW_EVENT_CARD = "routine_new_event_card"
    ROUTINE_QUICK_SELECT_CARD = "routine_quick_select_card"
    ROUTINE_QUERY_RESULTS_CARD = "routine_query_results_card"
    ROUTINE_RECORD_CARD = "routine_record_card"

# ========== 日常事项类型常量 ==========
class RoutineTypes:
    INSTANT = "instant"
    START = "start"
    END = "end"
    ONGOING = "ongoing"
    FUTURE = "future"

class RoutineCheckCycle:
    DAILY = "天"
    WEEKLY = "周"
    MONTHLY = "月"
    SEASONALLY = "季"  # 保持与业务层一致
    YEARLY = "年"

class RoutineProgressTypes:
    NONE = "none"
    VALUE = "value"
    MODIFY = "modify"

class RoutineTargetTypes:
    TIME = "time"
    COUNT = "count"

class RoutineReminderModes:
    """直接记录提醒模式"""
    OFF = "none"
    TIME = "time"
    RELATIVE = "relative"
