"""LLM-based reranking of search results using the DeepSeek API."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from backend.search_engine import SearchResult

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_CANDIDATES = 20


class LlmRerankError(Exception):
    """Raised when LLM reranking fails or cannot be configured."""


def _get_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        logger.error("DEEPSEEK_API_KEY is not set; LLM reranking unavailable")
        raise LlmRerankError("DEEPSEEK_API_KEY 环境变量未设置，无法使用 LLM 重排功能")
    logger.debug("DEEPSEEK_API_KEY loaded (length=%d)", len(key))
    return key


def _build_candidate_text(index: int, result: SearchResult) -> str:
    record = result.record
    parts = [
        f"编号：{index}",
        f"姓名：{record.name or '未知'}",
        f"学院：{record.college or '未知'}",
        f"职称：{record.career or '未知'}",
    ]
    if record.research:
        parts.append(f"研究方向：{record.research[:120]}")
    if record.representative_works:
        works_text = "\n".join(record.representative_works)
        parts.append(f"代表论文：{works_text[:220]}")
    if record.intro:
        parts.append(f"简介：{record.intro[:220]}")
    return "\n".join(parts)


def _build_prompt(query: str, candidates: list[SearchResult]) -> str:
    candidate_texts = [
        _build_candidate_text(i, candidate) for i, candidate in enumerate(candidates)
    ]
    return (
        "你是一位信息检索专家。请根据用户查询，对下列候选导师进行相关性排序。"
        "最相关的候选排在最前面。请只输出一个 JSON 对象，不要包含任何解释。\n\n"
        "EXAMPLE JSON OUTPUT:\n"
        '{"ranking": [0, 2, 1, 3]}\n\n'
        "数组中的数字是候选编号，按相关性从高到低排列，必须包含所有候选编号。"
        "输出必须是合法的 json 字符串。\n\n"
        f"用户查询：{query}\n\n" + "\n\n".join(candidate_texts) + "\n\nJSON 输出："
    )


def _parse_ranking_response(response_text: str, candidate_count: int) -> list[int]:
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("响应中未找到 JSON 对象")

    try:
        data: dict[str, Any] = json.loads(response_text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"响应 JSON 解析失败：{exc}") from exc

    try:
        ranking = [int(i) for i in data.get("ranking", [])]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"排序结果包含非整数编号：{exc}") from exc

    if len(ranking) != candidate_count:
        raise ValueError(
            f"排序结果数量不匹配：期望 {candidate_count} 个，实际 {len(ranking)} 个"
        )
    if set(ranking) != set(range(candidate_count)):
        raise ValueError("排序结果未包含所有候选编号，或包含无效编号")
    return ranking


def rerank(
    query: str,
    candidates: list[SearchResult],
    *,
    model: str = DEFAULT_MODEL,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    timeout: float = DEFAULT_TIMEOUT,
    api_key: str | None = None,
) -> list[SearchResult]:
    """Rerank ``candidates`` for ``query`` using the DeepSeek API.

    Args:
        query: The original search query.
        candidates: Baseline ranked search results (must be sorted by descending
            relevance already; the first ``max_candidates`` items are sent to
            the LLM).
        model: DeepSeek model name to use.
        max_candidates: Maximum number of candidates to rerank. The remainder
            are appended unchanged after the reranked portion.
        timeout: HTTP request timeout in seconds.
        api_key: Optional DeepSeek API key. If not provided, the value of the
            ``DEEPSEEK_API_KEY`` environment variable is used.

    Returns:
        A new list of ``SearchResult`` objects ordered by the LLM.

    Raises:
        LlmRerankError: If the API key is missing or the API call / response
            parsing fails.
    """
    if not candidates:
        logger.info("LLM rerank skipped: no candidates for query=%r", query)
        return []

    logger.info(
        "LLM rerank requested: query=%r total_candidates=%d max_candidates=%d",
        query,
        len(candidates),
        max_candidates,
    )

    if api_key is None:
        api_key = _get_api_key()

    to_rerank = candidates[:max_candidates]
    prompt = _build_prompt(query, to_rerank)
    logger.debug(
        "LLM rerank prompt: query=%r prompt_length=%d candidates=%d",
        query,
        len(prompt),
        len(to_rerank),
    )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert information retrieval assistant. "
                    "The user will provide a query and a list of candidate teacher records. "
                    "Please output a valid JSON object containing the ranking. "
                    'EXAMPLE JSON OUTPUT: {"ranking": [0, 2, 1, 3]}. '
                    "The array must contain every candidate index exactly once, "
                    "ordered from most relevant to least relevant."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
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
        raise LlmRerankError(
            f"DeepSeek API 返回错误 {exc.code}: {detail or exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        logger.error(
            "DeepSeek API connection error: query=%r error=%s", query, exc.reason
        )
        raise LlmRerankError(f"无法连接 DeepSeek API: {exc.reason}") from exc
    except TimeoutError as exc:
        logger.error("DeepSeek API timeout: query=%r timeout=%.1fs", query, timeout)
        raise LlmRerankError("DeepSeek API 请求超时") from exc

    try:
        content = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error(
            "DeepSeek API response malformed: query=%r data=%s", query, response_data
        )
        raise LlmRerankError(f"DeepSeek API 响应格式异常：{exc}") from exc

    if not content:
        logger.error("DeepSeek API returned empty content: query=%r", query)
        raise LlmRerankError("DeepSeek API 返回内容为空")

    logger.debug("DeepSeek API raw content: query=%r content=%r", query, content)
    try:
        ranking = _parse_ranking_response(content, len(to_rerank))
    except ValueError as exc:
        logger.error(
            "LLM ranking parse failed: query=%r content=%r error=%s",
            query,
            content,
            exc,
        )
        raise LlmRerankError(f"解析 LLM 排序结果失败：{exc}") from exc

    logger.info(
        "LLM rerank completed: query=%r reranked_count=%d ranking=%s",
        query,
        len(to_rerank),
        ranking,
    )
    reranked = [to_rerank[i] for i in ranking]
    return reranked + candidates[max_candidates:]
