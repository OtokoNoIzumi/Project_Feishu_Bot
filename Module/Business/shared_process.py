"""
和业务、上下文或鉴权无关的辅助函数
"""

import pprint


def debug_dict_print(data):
    """
    调试字典的详细信息输出
    """
    pprint.pprint(data, indent=2, width=120)


def safe_parse_number(value, as_int: bool = False) -> float:
    """
    安全解析数值

    Args:
        value: 数值字符串或数值
        as_int: 是否返回整数

    Returns:
        float/int: 解析后的数值，失败返回0
    """
    if value is None or value == "":
        return 0

    try:
        result = float(value)
        return int(result) if as_int else result
    except (ValueError, TypeError):
        return 0


def hex_to_hsl(hex_color: str) -> tuple:
    """
    将十六进制颜色转换为HSL

    Args:
        hex_color: 十六进制颜色值，如 "#1456F0"

    Returns:
        tuple: (H, S, L) HSL值
    """
    # 先转换为RGB
    r, g, b = hex_to_rgb(hex_color)

    # 转换为0-1范围
    r, g, b = r / 255.0, g / 255.0, b / 255.0

    # 计算HSL
    max_val = max(r, g, b)
    min_val = min(r, g, b)
    delta = max_val - min_val

    # 计算亮度
    l = (max_val + min_val) / 2.0

    # 计算饱和度
    if delta == 0:
        s = 0
    else:
        s = delta / (1 - abs(2 * l - 1))

    # 计算色相
    if delta == 0:
        h = 0
    elif max_val == r:
        h = 60 * (((g - b) / delta) % 6)
    elif max_val == g:
        h = 60 * ((b - r) / delta + 2)
    else:  # max_val == b
        h = 60 * ((r - g) / delta + 4)

    # 确保色相在0-360范围内
    h = h % 360

    return (h, s, l)


def hex_to_rgb(hex_color: str) -> tuple:
    """
    将十六进制颜色转换为RGB

    Args:
        hex_color: 十六进制颜色值，如 "#1456F0"

    Returns:
        tuple: (R, G, B) RGB值
    """
    hex_str = hex_color.lstrip("#")
    return tuple(int(hex_str[i : i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """
    将RGB值转换为十六进制颜色

    Args:
        r, g, b: RGB值

    Returns:
        str: 十六进制颜色值
    """
    return f"#{r:02x}{g:02x}{b:02x}".upper()


def hsl_to_hex(h: float, s: float, l: float) -> str:
    """
    将HSL值转换为十六进制颜色

    Args:
        h, s, l: HSL值

    Returns:
        str: 十六进制颜色值
    """
    # 确保值在正确范围内
    h = h % 360
    s = max(0, min(1, s))
    l = max(0, min(1, l))

    # 转换为RGB
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2

    if 0 <= h < 60:
        r, g, b = c, x, 0
    elif 60 <= h < 120:
        r, g, b = x, c, 0
    elif 120 <= h < 180:
        r, g, b = 0, c, x
    elif 180 <= h < 240:
        r, g, b = 0, x, c
    elif 240 <= h < 300:
        r, g, b = x, 0, c
    else:  # 300 <= h < 360
        r, g, b = c, 0, x

    # 转换为0-255范围
    r = int((r + m) * 255)
    g = int((g + m) * 255)
    b = int((b + m) * 255)

    return rgb_to_hex(r, g, b)


def format_time_label(minutes: int) -> str:
    """
    格式化时间标签

    Args:
        minutes: 分钟数

    Returns:
        str: 格式化后的时间标签
    """
    if minutes > 1440:
        days = int(minutes // 1440)
        hours = round((minutes % 1440) / 60, 1)
        return f"{days}天{hours}小时"
    elif minutes > 60:
        hours = int(minutes // 60)
        minutes = int(minutes % 60)
        return f"{hours}小时{minutes}分钟"
    else:
        return f"{int(minutes)}分钟"
