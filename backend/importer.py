"""Read Discord's official data package and the legacy cleaner preview.

Archive entries are parsed in memory and are NEVER extracted to disk. The
account/payment/session files in a Discord data package are intentionally
ignored: only message data is imported.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any, BinaryIO


MAX_ZIP_FILES = 20_000
MAX_UNCOMPRESSED = 1_000_000_000
MAX_SINGLE_FILE = 128_000_000
ID = re.compile(r"^\d{15,25}$")


def _value(item: dict[str, Any], *keys: str) -> Any:
    lowered = {str(k).lower(): v for k, v in item.items()}
    for key in keys:
        val = lowered.get(key.lower())
        if val is not None:
            return val
    return None


def _attachments(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, TypeError):
            pass
        return [{"url": link} for link in re.findall(r"https?://[^\s,]+", value)]
    return []


def _kind(meta: dict[str, Any], guild_id: str | None) -> str:
    type_id = meta.get("type")
    if isinstance(type_id, str) and type_id.isdigit():
        type_id = int(type_id)
    if type_id == 1:
        return "dm"
    if type_id == 3:
        return "group_dm"
    if type_id in (10, 11, 12):
        return "thread"
    if guild_id:
        return "guild"
    return "unknown"


def _channel_from_meta(
    channel_id: str, meta: dict[str, Any], fallback: str | None = None
) -> dict[str, Any]:
    guild = meta.get("guild")
    guild_id = _value(meta, "guild_id", "guildid")
    guild_name = _value(meta, "guild_name", "guildname")
    if isinstance(guild, dict):
        guild_id = guild_id or guild.get("id")
        guild_name = guild_name or guild.get("name")
    channel_name = _value(meta, "name", "channel_name", "channelname") or fallback or channel_id
    return {
        "id": channel_id,
        "guild_id": str(guild_id) if guild_id else None,
        "guild_name": str(guild_name) if guild_name else None,
        "name": str(channel_name),
        "kind": _kind(meta, str(guild_id) if guild_id else None),
        "metadata": {
            "type": meta.get("type"),
            "recipient_ids": meta.get("recipients") or meta.get("recipient_ids"),
        },
    }


def _normalize_message(
    item: dict[str, Any], channel_id: str
) -> dict[str, Any] | None:
    msg_id = str(_value(item, "id", "message_id") or "").strip()
    if not ID.fullmatch(msg_id):
        return None
    resolved_channel = str(_value(item, "channel_id") or channel_id)
    pinned = _value(item, "pinned")
    if isinstance(pinned, str):
        pinned = pinned.strip().lower() == "true"
    return {
        "id": msg_id,
        "channel_id": resolved_channel,
        "timestamp": str(_value(item, "timestamp", "created_at") or ""),
        "content": str(_value(item, "contents", "content") or ""),
        "attachments": _attachments(_value(item, "attachments")),
        "pinned": pinned,
        "metadata": {
            "edited_timestamp": _value(item, "edited_timestamp"),
            "type": _value(item, "type"),
        },
    }


def parse_preview(data: dict[str, Any]) -> tuple[list[dict], list[dict], str]:
    if data.get("format") != "dsc-preview-v1" or not isinstance(data.get("messages"), list):
        raise ValueError("不是受支持的旧版清理器预览 JSON。")
    options = data.get("options") or {}
    guild_id = str(options.get("guildId") or "")
    names = data.get("channels") or {}
    channels: dict[str, dict] = {}
    messages: list[dict] = []
    for item in data["messages"]:
        if not isinstance(item, dict):
            continue
        channel_id = str(item.get("channel_id") or "")
        message = _normalize_message(item, channel_id)
        if not message:
            continue
        messages.append(message)
        channels[channel_id] = {
            "id": channel_id,
            "name": str(names.get(channel_id) or channel_id),
            "guild_id": guild_id if guild_id != "@me" else None,
            "guild_name": None,
            "kind": "dm" if guild_id == "@me" else "guild",
            "metadata": {},
        }
    return list(channels.values()), messages, "preview-json"


def parse_json_document(raw: bytes) -> tuple[list[dict], list[dict], str]:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("JSON 无法解析。") from exc
    if not isinstance(data, dict):
        raise ValueError("请导入 Discord 数据包 ZIP 或旧版预览 JSON。")
    return parse_preview(data)


def parse_discord_zip(stream: BinaryIO) -> tuple[list[dict], list[dict], str]:
    try:
        archive = zipfile.ZipFile(stream)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("不是有效的 ZIP 压缩包。") from exc
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_FILES:
            raise ValueError("ZIP 内文件数量异常，已拒绝导入。")
        if sum(info.file_size for info in entries) > MAX_UNCOMPRESSED:
            raise ValueError("ZIP 解压后超过 1GB 安全上限，请拆分后再导入。")
        if any(info.file_size > MAX_SINGLE_FILE for info in entries):
            raise ValueError("ZIP 包含超过 128MB 的单个文件。")

        def read_json(info: zipfile.ZipInfo) -> Any:
            with archive.open(info) as handle:
                raw = handle.read(MAX_SINGLE_FILE + 1)
            if len(raw) > MAX_SINGLE_FILE:
                raise ValueError("归档内容过大。")
            return json.loads(raw.decode("utf-8-sig"))

        # Support a ZIP that contains only a legacy preview JSON.
        for info in entries:
            if PurePosixPath(info.filename).name.lower().startswith("discord-preview-") and info.filename.lower().endswith(".json"):
                parsed = read_json(info)
                if isinstance(parsed, dict) and parsed.get("format") == "dsc-preview-v1":
                    return parse_preview(parsed)

        channel_meta: dict[str, dict] = {}
        name_index: dict[str, str] = {}
        message_files: list[tuple[zipfile.ZipInfo, str]] = []
        for info in entries:
            if info.is_dir():
                continue
            # No extraction is performed, but reject surprising names anyway.
            if "\\" in info.filename or ".." in PurePosixPath(info.filename).parts:
                raise ValueError("ZIP 包含不安全的文件路径。")
            parts = PurePosixPath(info.filename).parts
            lowered = [part.lower() for part in parts]
            if "messages" not in lowered:
                continue
            idx = lowered.index("messages")
            relative = parts[idx + 1:]
            if len(relative) == 1 and relative[0].lower() == "index.json":
                index_obj = read_json(info)
                if isinstance(index_obj, dict):
                    name_index = {str(k): str(v) for k, v in index_obj.items() if isinstance(v, str)}
                continue
            if len(relative) != 2:
                continue
            folder, basename = relative
            channel_id = folder[1:] if folder.lower().startswith("c") else folder
            if not ID.fullmatch(channel_id):
                continue
            basename = basename.lower()
            if basename == "channel.json":
                meta = read_json(info)
                if isinstance(meta, dict):
                    channel_meta[channel_id] = meta
            elif basename in ("messages.json", "messages.csv"):
                message_files.append((info, channel_id))

        if not message_files:
            raise ValueError("未找到 Discord 消息文件。请确认 ZIP 包含 messages 文件夹。")

        channels: dict[str, dict] = {}
        messages: list[dict] = []
        for info, channel_id in message_files:
            channels[channel_id] = _channel_from_meta(
                channel_id, channel_meta.get(channel_id, {}), name_index.get(channel_id)
            )
            if info.filename.lower().endswith(".json"):
                parsed = read_json(info)
                if isinstance(parsed, dict):
                    parsed = parsed.get("messages") or parsed.get("Messages")
                if not isinstance(parsed, list):
                    raise ValueError("消息 JSON 格式与预期不符。")
                records = parsed
            else:
                with archive.open(info) as handle:
                    text = handle.read(MAX_SINGLE_FILE + 1).decode("utf-8-sig")
                records = list(csv.DictReader(io.StringIO(text)))
            for row in records:
                if isinstance(row, dict):
                    msg = _normalize_message(row, channel_id)
                    if msg:
                        messages.append(msg)
        return list(channels.values()), messages, "discord-export"
