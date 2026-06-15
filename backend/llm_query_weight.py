"""LLM-based query term weighting using the DeepSeek API.

Given a user search query and its tokenized terms, this module asks an LLM to
assign an importance weight to each term so that more relevant aspects of the
query contribute more to BM25 / TF-IDF scoring.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_TIMEOUT = 15.0


class LlmQueryWeightError(Exception):
    """Raised when LLM query-term weighting fails."""


def _get_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        logger.error("DEEPSEEK_API_KEY is not set; LLM query weighting unavailable")
        raise LlmQueryWeightError(
            "DEEPSEEK_API_KEY 环境变量未设置，无法使用 LLM 查询加权功能"
        )
    return key


def _build_prompt(query: str, tokens: list[str]) -> str:
    token_list = "、".join(f'"{t}"' for t in tokens)
    return (
        f"用户搜索查询：{query}\n"
        f"分词结果：{token_list}\n\n"
        "请根据查询意图，为每个词分配一个重要性权重。权重范围为 0.1 到 3.0，"
        "其中 1.0 表示正常重要性。核心关键词应赋予更高权重（如 1.5–3.0），"
        "辅助词或常见词应赋予较低权重（如 0.1–0.8）。\n\n"
        "请只输出一个 JSON 对象，格式如下，不要包含任何解释：\n"
        '{"weights": {"词1": 1.5, "词2": 0.5, ...}}\n\n'
        "JSON 输出："
    )


def _parse_weights_response(
    response_text: str, tokens: list[str]
) -> dict[str, float]:
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("响应中未找到 JSON 对象")

    try:
        data: dict[str, Any] = json.loads(response_text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"响应 JSON 解析失败：{exc}") from exc

    raw_weights = data.get("weights")
    if not isinstance(raw_weights, dict):
        raise ValueError("响应中缺少 weights 字典")

    weights: dict[str, float] = {}
    for token in tokens:
        value = raw_weights.get(token, 1.0)
        try:
            w = float(value)
        except (TypeError, ValueError):
            w = 1.0
        weights[token] = max(0.1, min(3.0, w))

    return weights


def compute_query_weights(
    query: str,
    tokens: list[str],
    *,
    model: str = DEFAULT_MODEL,
    timeout: float = DEFAULT_TIMEOUT,
    api_key: str | None = None,
) -> dict[str, float]:
    """Ask the LLM to assign importance weights to each query token.

    Args:
        query: The original search query string.
        tokens: Deduplicated list of tokens from the query.
        model: DeepSeek model name.
        timeout: HTTP timeout in seconds.
        api_key: Optional API key override.

    Returns:
        A dict mapping each token to its weight (0.1–3.0).

    Raises:
        LlmQueryWeightError: On API or parsing failure.
    """
    if not tokens:
        return {}

    unique_tokens = list(dict.fromkeys(tokens))

    logger.info(
        "LLM query weighting requested: query=%r tokens=%s", query, unique_tokens
    )

    if api_key is None:
        api_key = _get_api_key()

    prompt = _build_prompt(query, unique_tokens)

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert information retrieval assistant. "
                    "The user will provide a search query and its tokenized terms. "
                    "Assign an importance weight (0.1–3.0) to each token based on "
                    "how central it is to the query intent. "
                    "Output ONLY a valid JSON object with a \"weights\" key."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        logger.error(
            "DeepSeek API HTTP error: query=%r status=%d detail=%s",
            query,
            exc.code,
            detail,
        )
        raise LlmQueryWeightError(
            f"DeepSeek API 返回错误 {exc.code}: {detail or exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        logger.error(
            "DeepSeek API connection error: query=%r error=%s", query, exc.reason
        )
        raise LlmQueryWeightError(f"无法连接 DeepSeek API: {exc.reason}") from exc
    except TimeoutError as exc:
        logger.error("DeepSeek API timeout: query=%r timeout=%.1fs", query, timeout)
        raise LlmQueryWeightError("DeepSeek API 请求超时") from exc

    try:
        content = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error(
            "DeepSeek API response malformed: query=%r data=%s", query, response_data
        )
        raise LlmQueryWeightError(f"DeepSeek API 响应格式异常：{exc}") from exc

    if not content:
        logger.error("DeepSeek API returned empty content: query=%r", query)
        raise LlmQueryWeightError("DeepSeek API 返回内容为空")

    logger.debug("DeepSeek query weight raw content: query=%r content=%r", query, content)
    try:
        weights = _parse_weights_response(content, unique_tokens)
    except ValueError as exc:
        logger.error(
            "LLM weight parse failed: query=%r content=%r error=%s",
            query,
            content,
            exc,
        )
        raise LlmQueryWeightError(f"解析 LLM 权重结果失败：{exc}") from exc

    logger.info("LLM query weighting completed: query=%r weights=%s", query, weights)
    return weights
