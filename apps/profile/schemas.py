from pydantic import BaseModel, Field
from typing import Optional, Dict, List

class DietTarget(BaseModel):
    """饮食目标设定。所有字段可空，表示用户未设置。"""
    energy_unit: str = "kJ"  # UI 偏好设置，有默认值
    goal: str = "fat_loss"  # fat_loss, maintain, muscle_gain, health - 默认减脂
    daily_energy_kj_target: Optional[int] = None
    protein_g_target: Optional[int] = None
    fat_g_target: Optional[int] = None
    carbs_g_target: Optional[int] = None
    fiber_g_target: Optional[int] = None
    sodium_mg_target: Optional[int] = None

class KeepTarget(BaseModel):
    """Keep 目标设定。所有字段可空，表示用户未设置。"""
    weight_kg_target: Optional[float] = None
    body_fat_pct_target: Optional[float] = None
    # 围度目标：key 为维度名（waist/bust/hip_circ 等），value 为目标值 (cm)
    dimensions_target: Optional[Dict[str, float]] = Field(default_factory=dict)

class UserProfile(BaseModel):
    """
    用户 Profile 配置。
    基础信息 (gender/age) 为空表示新用户，未填写过基础信息。
    """
    # 基础信息：默认为空，需用户填写
    gender: Optional[str] = None
    # age 用于 API 传输，前端直接读写；后端存储时转为 birth_date
    age: int = 25
    # 存储生日 yyyy-mm-dd，后端计算 BMR 时动态推算真实年龄
    birth_date: Optional[str] = None
    activity_level: str = "sedentary"  # 默认久坐
    
    timezone: str = "Asia/Shanghai"
    diet: DietTarget = Field(default_factory=DietTarget)
    keep: KeepTarget = Field(default_factory=KeepTarget)
    
    # 用户关键主张：存储用户提出的影响分析的重要信息
    # 例如："虽然是 male 但想要 female 的身材围度"
    user_info: Optional[str] = None
    
    # 预估达成目标的月数（LLM 推算）
    estimated_months: Optional[int] = None

    # ========== 账户管理字段 ==========
    registered_at: Optional[str] = None  # ISO format datetime
    nid: Optional[int] = None  # Display ID (e.g. 10001)
    
    # 新版：多级订阅系统
    # 格式: {"basic": "2025-12-31T23:59:59", "pro": "2025-06-01T..."}
    subscriptions: Dict[str, str] = Field(default_factory=dict)

    whitelist_features: list[str] = Field(default_factory=list)

class MetricsOverride(BaseModel):
    """身体指标覆盖（前端编辑的身高/体重）"""
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None

class ProfileAnalyzeRequest(BaseModel):
    user_note: str
    target_months: Optional[int] = None  # 用户期望的达成时间（月），可选输入
    auto_save: bool = False
    profile_override: Optional[UserProfile] = None  # 前端当前编辑的 Profile（优先使用）
    metrics_override: Optional[MetricsOverride] = None  # 前端编辑的身高/体重
    images_b64: List[str] = []

class ProfileAnalyzeResponse(BaseModel):
    advice: str
    suggested_profile: UserProfile
    estimated_months: Optional[int] = None  # LLM 推算的达成时间（月）
    saved: bool
    warning: Optional[str] = None
