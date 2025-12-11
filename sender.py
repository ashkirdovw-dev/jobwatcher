# sender.py
import asyncio
import json
import time
from typing import List, Dict, Optional, Any, Callable
from formatter import format_post_block
# from templates import POST_TEMPLATE, SUMMARY_TEMPLATE


DEFAULT_MESSAGE_LIMIT = 4000
DEFAULT_PAUSE_SEC = 1.2
BATCH_SEPARATOR = "\n\n"

# Default ordering for labels in summary (high -> low quality)
DEFAULT_LABEL_ORDER = [
    "good",
    "possible",
    "neutral",
    "negative",
    "strong_negative",
    "ignore",
    "other",
]

def _safe_msg_link(channel: str, msg_id: Any) -> str:
    """Return telegram link like https://t.me/channel/123 or fallback."""
    if not channel:
        return str(msg_id or "")
    channel_name = channel.replace("@", "")
    if msg_id:
        return f"https://t.me/{channel_name}/{msg_id}"
    return channel

def _derive_label_from_final(final: Optional[int]) -> str:
    """
    Fallback mapping from numeric final -> label.
    - None -> ignore
    - >=2 -> good
    - ==1 -> possible
    - ==0 -> neutral
    - ==-1 -> negative
    - <=-2 -> strong_negative
    """
    if final is None:
        return "ignore"
    try:
        v = int(final)
    except Exception:
        return "other"
    if v >= 2:
        return "good"
    if v == 1:
        return "possible"
    if v == 0:
        return "neutral"
    if v == -1:
        return "negative"
    if v <= -2:
        return "strong_negative"
    return "other"

def _group_results(results: List[Dict], strategy: str) -> List[List[Dict]]:
    """
    Return list-of-groups (each group is list of items) according to strategy:
      - 'length' -> single group (we will batch by length later)
      - 'none' -> each item its own group
      - 'by_channel' -> group by channel
      - 'by_label' -> group by label (uses item['label'] or derived)
    """
    if not results:
        return []

    if strategy == "none":
        return [[r] for r in results]

    if strategy == "by_channel":
        groups = {}
        for r in results:
            key = r.get("channel") or "unknown_channel"
            groups.setdefault(key, []).append(r)
        return list(groups.values())

    if strategy == "by_label":
        groups = {}
        for r in results:
            label = r.get("label") or _derive_label_from_final(r.get("final"))
            groups.setdefault(label, []).append(r)
        return list(groups.values())

    # default 'length' or unknown -> single group with all results
    return [results]

def _truncate_block_preserving_preview(block: str, limit: int) -> str:
    """
    If block longer than limit, try to truncate in Preview area or cut with ellipsis.
    Simple heuristic: look for 'Preview:' marker (case-sensitive). If found, keep header and a chunk of preview.
    """
    if len(block) <= limit:
        return block
    marker = "Preview:"
    idx = block.find(marker)
    if idx == -1:
        return block[: max(0, limit - 3)].rstrip() + "..."
    preview_start = idx + len(marker)
    header = block[:preview_start]
    preview_content = block[preview_start:]
    avail = limit - len(header) - 3
    if avail <= 0:
        return header[: max(0, limit - 3)].rstrip() + "..."
    shortened = preview_content[:avail].rstrip()
    last_sp = shortened.rfind(" ")
    if last_sp > int(len(shortened) * 0.6):
        shortened = shortened[:last_sp]
    return header + shortened + "..."

async def _send_text(client, target_chat: str, text: str) -> bool:
    """Send one message via Telethon client; catch exceptions and return success flag."""
    try:
        await client.send_message(target_chat, text)
        return True
    except Exception as e:
        print(f"[sender] send_message failed: {e}")
        return False

def _build_summary_text(
    results: List[Dict],
    run_meta: Optional[Dict] = None,
    label_order: Optional[List[str]] = None,
    message_limit: int = DEFAULT_MESSAGE_LIMIT,
) -> str:
    """
    Build the debug summary text (one message). If exceeds message_limit it will be truncated by caller.
    Structure:
      - header with start_ts (if provided), period_hours, channels
      - stats: total_checked, found_count, truncated_count (if present in items)
      - grouped lists by label in label_order
    """
    if label_order is None:
        label_order = DEFAULT_LABEL_ORDER

    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    header_lines = [f"JobWatcher — сводка ({now})"]
    if run_meta:
        start = run_meta.get("start_ts")
        if start:
            header_lines.append(f"Запуск: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start))}")
        period = run_meta.get("period_hours")
        if period:
            header_lines.append(f"Период (часы): {period}")
        chans = run_meta.get("channels")
        if chans:
            if isinstance(chans, (list, tuple)):
                header_lines.append("Каналы: " + ", ".join(chans))
            else:
                header_lines.append(f"Каналы: {chans}")

    total = len(results)
    found = sum(1 for r in results if r.get("final") is not None)
    truncated = sum(1 for r in results if r.get("truncated"))
    ignored = sum(1 for r in results if (r.get("final") is None))
    header_lines.append(f"Проверено: {total} | Найдено(accepted): {found} | Игнор: {ignored} | Обрезано: {truncated}")
    header_lines.append("")  # blank

    # group results by label
    groups = {}
    for r in results:
        label = r.get("label") or _derive_label_from_final(r.get("final"))
        groups.setdefault(label, []).append(r)

    body_lines = []
    for lbl in label_order:
        items = groups.get(lbl)
        if not items:
            continue
        body_lines.append(f"=== {lbl} — {len(items)} ===")
        for it in items:
            ch = it.get("channel", "")
            msg_id = it.get("msg_id") or it.get("msg_id_str") or ""
            link = _safe_msg_link(ch, msg_id)
            body_lines.append(f"{ch} / {link}")
        body_lines.append("")  # separator between groups

    # add any labels not in label_order at the end
    other_labels = [k for k in groups.keys() if k not in label_order]
    for lbl in other_labels:
        items = groups.get(lbl, [])
        if not items:
            continue
        body_lines.append(f"=== {lbl} — {len(items)} ===")
        for it in items:
            ch = it.get("channel", "")
            msg_id = it.get("msg_id") or ""
            link = _safe_msg_link(ch, msg_id)
            body_lines.append(f"{ch} / {link}")
        body_lines.append("")

    text = "\n".join(header_lines + body_lines)
    if len(text) <= message_limit:
        return text
    # truncate summary gracefully
    return text[: max(0, message_limit - 3)].rstrip() + "..."

async def send_results(
    client,
    results: List[Dict],
    target_chat: str,
    pause_sec: Optional[float] = None,
    message_limit: Optional[int] = None,
    cfg: Optional[Dict] = None,
    run_meta: Optional[Dict] = None,
    send_summary_first: bool = True,
    merge_strategy: Optional[str] = None,
    verbosity: int = 1,
) -> Dict[str, int]:
    """
    Main sender entrypoint.

    Parameters:
      - client: telethon client (async)
      - results: list of item dicts (expects keys like 'channel','msg_id','final','label','preview','raw_text','truncated' optional)
      - target_chat: target chat id or username
      - pause_sec, message_limit: optional overrides
      - cfg: optional config dict; if provided, values override defaults and kwargs
          cfg keys used: 'message_limit', 'pause_sec', 'merge_strategy', 'label_order'
      - run_meta: optional dict for summary (start_ts, period_hours, channels)
      - send_summary_first: if True, send run summary as first message
      - merge_strategy: 'length'|'none'|'by_channel'|'by_label' (overrides cfg)
      - verbosity: currently reserved for future detail levels

    Returns dict with counts: {'sent': int, 'failed': int, 'truncated': int}
    """
    # resolve config
    if cfg is None:
        cfg = {}
    message_limit = int(message_limit or cfg.get("message_limit", DEFAULT_MESSAGE_LIMIT))
    pause_sec = float(pause_sec or cfg.get("pause_sec", DEFAULT_PAUSE_SEC))
    merge_strategy = merge_strategy or cfg.get("merge_strategy", "length")
    label_order = cfg.get("label_order", DEFAULT_LABEL_ORDER)

    sent = 0
    failed = 0
    truncated_count = 0

    # Optionally send summary first
    if send_summary_first:
        summary_text = _build_summary_text(results, run_meta=run_meta, label_order=label_order, message_limit=message_limit)
        ok = await _send_text(client, target_chat, summary_text)
        if ok:
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(pause_sec)

    # Build groups according to merge strategy
    groups = _group_results(results, merge_strategy)

    # For each group, build blocks and send with length-based batching inside group
    for group in groups:
        # Make list of text blocks for this group
        blocks = []
        for item in group:
            # format using formatter.py
            try:
                block = format_post_block(item)
            except Exception as e:
                # fallback minimal block
                print(f"[sender] formatter failed for item {item.get('msg_id')}: {e}")
                ch = item.get("channel", "")
                mid = item.get("msg_id", "")
                link = _safe_msg_link(ch, mid)
                block = f"{ch} / {link}"
            # if block too long -> truncate and mark truncated
            if len(block) > message_limit:
                block = _truncate_block_preserving_preview(block, message_limit)
                item["truncated"] = True
                truncated_count += 1
            blocks.append(block)

        # Depending on merge_strategy 'none' we send each block separately; otherwise batch by length
        if merge_strategy == "none":
            for blk in blocks:
                ok = await _send_text(client, target_chat, blk)
                if ok:
                    sent += 1
                else:
                    failed += 1
                await asyncio.sleep(pause_sec)
            continue

        # Batch by length with separator
        current_parts: List[str] = []
        current_len = 0
        for blk in blocks:
            part_len = len(blk) + (len(BATCH_SEPARATOR) if current_parts else 0)
            if current_parts and (current_len + part_len > message_limit):
                batch_text = BATCH_SEPARATOR.join(current_parts)
                ok = await _send_text(client, target_chat, batch_text)
                if ok:
                    sent += 1
                else:
                    failed += 1
                await asyncio.sleep(pause_sec)
                current_parts = []
                current_len = 0
            current_parts.append(blk)
            current_len += part_len

        if current_parts:
            batch_text = BATCH_SEPARATOR.join(current_parts)
            ok = await _send_text(client, target_chat, batch_text)
            if ok:
                sent += 1
            else:
                failed += 1
            await asyncio.sleep(pause_sec)

    # final summary message (short)
    final_summary = f"Отправлено: {sent}, Неудач: {failed}, Обрезано: {truncated_count}."
    try:
        if len(final_summary) <= message_limit:
            await _send_text(client, target_chat, final_summary)
        else:
            await _send_text(client, target_chat, final_summary[: message_limit - 3] + "...")
    except Exception:
        pass

    return {"sent": sent, "failed": failed, "truncated": truncated_count}
