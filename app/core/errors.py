"""把各种报错翻译成用户能看懂的中文。"""
from __future__ import annotations


class UserFacingError(Exception):
    """已经是中文、可以直接显示给用户的错误。"""


class Cancelled(Exception):
    """用户主动取消。"""


def friendly_message(e: BaseException) -> str:
    """把任意异常转成一句中文说明（含原因和建议）。"""
    if isinstance(e, UserFacingError):
        return str(e)
    if isinstance(e, Cancelled):
        return "已取消。"

    name = type(e).__name__
    text = str(e)

    # ---- OpenAI ----
    try:
        import openai
        if isinstance(e, openai.AuthenticationError):
            return "OpenAI 的 API Key 不对或已失效。请到右上角「设置 → API Key」检查。"
        if isinstance(e, openai.PermissionDeniedError):
            return "OpenAI 拒绝了这个请求：这个 Key 没有权限用这个模型，或账号所在地区不支持。"
        if isinstance(e, openai.RateLimitError):
            if "insufficient_quota" in text or "quota" in text:
                return "OpenAI 账号余额不足或没有开通付费。请到 OpenAI 网站充值后再试。"
            return "OpenAI 请求太频繁，被暂时限流。稍等一分钟再试。"
        if isinstance(e, openai.NotFoundError):
            return f"OpenAI 找不到这个模型（{_extract_model(text)}）。请在主页「识别模型」里换一个名称。"
        if isinstance(e, openai.BadRequestError):
            return f"OpenAI 拒绝了请求（参数有问题）：{_short(text)}"
        if isinstance(e, openai.APIConnectionError):
            return "连不上 OpenAI 服务器。请检查网络、代理或 VPN。"
        if isinstance(e, openai.APIStatusError):
            return f"OpenAI 服务器返回错误（{e.status_code}）：{_short(text)}"
    except ImportError:
        pass

    # ---- Anthropic ----
    try:
        import anthropic
        if isinstance(e, anthropic.AuthenticationError):
            return "Anthropic 的 API Key 不对或已失效。请到右上角「设置 → API Key」检查。"
        if isinstance(e, anthropic.PermissionDeniedError):
            return "Anthropic 拒绝了这个请求：这个 Key 没有权限，或账号所在地区不支持。"
        if isinstance(e, anthropic.RateLimitError):
            return "Anthropic 请求太频繁或余额不足，被暂时限流。稍等一分钟再试，或检查账号余额。"
        if isinstance(e, anthropic.NotFoundError):
            return f"Anthropic 找不到这个模型（{_extract_model(text)}）。请在主页「翻译模型」里换一个名称。"
        if isinstance(e, anthropic.BadRequestError):
            if "credit balance" in text.lower():
                return "Anthropic 账号余额不足。请到 Anthropic 网站充值后再试。"
            return f"Anthropic 拒绝了请求（参数有问题）：{_short(text)}"
        if isinstance(e, anthropic.APIConnectionError):
            return "连不上 Anthropic 服务器。请检查网络、代理或 VPN。"
        if isinstance(e, anthropic.APIStatusError):
            return f"Anthropic 服务器返回错误（{e.status_code}）：{_short(text)}"
    except ImportError:
        pass

    if isinstance(e, FileNotFoundError):
        return f"找不到文件：{text}"
    if isinstance(e, PermissionError):
        return f"没有权限读写文件：{text}"
    if isinstance(e, MemoryError):
        return "内存不够了。请关掉其他程序，或换一段短一点的视频。"
    return f"出了点问题（{name}）：{_short(text)}"


def _short(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def _extract_model(text: str) -> str:
    import re
    m = re.search(r"model[^A-Za-z0-9_.-]*([A-Za-z0-9_.-]+)", text)
    return m.group(1) if m else "未知"
