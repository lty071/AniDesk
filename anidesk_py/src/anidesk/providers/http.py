from __future__ import annotations

import httpx


class ProviderError(RuntimeError):
    pass


def checked_response(response: httpx.Response, service: str) -> httpx.Response:
    if response.status_code == 429:
        raise ProviderError(f"{service} 请求过于频繁，请稍后重试")
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise ProviderError(f"{service} 返回 {response.status_code}") from error
    return response


def translate_http_error(error: Exception, service: str) -> ProviderError:
    if isinstance(error, ProviderError):
        return error
    if isinstance(error, httpx.TimeoutException):
        return ProviderError(f"{service} 请求超时")
    if isinstance(error, httpx.HTTPError):
        return ProviderError(f"无法连接 {service}，请检查网络")
    return ProviderError(f"{service} 数据格式无效")
