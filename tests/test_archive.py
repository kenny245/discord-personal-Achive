import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.ai import chunk_messages, summarize_messages, validate_endpoint
from backend.importer import parse_discord_zip, parse_json_document
from backend.storage import ArchiveDB


ME = "123456789012345678"
GUILD = "223456789012345678"
CHANNEL = "323456789012345678"
DM = "423456789012345678"
M1 = "523456789012345678"
M2 = "523456789012345679"
M3 = "523456789012345680"


def example_zip():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("messages/index.json", json.dumps({CHANNEL: "general", DM: "Alice"}))
        archive.writestr(
            f"messages/c{CHANNEL}/channel.json",
            json.dumps({"id": CHANNEL, "name": "general", "type": 0,
                        "guild": {"id": GUILD, "name": "Demo Guild"}}),
        )
        archive.writestr(
            f"messages/c{CHANNEL}/messages.json",
            json.dumps([
                {"ID": M1, "Timestamp": "2026-10-01T12:00:00+00:00",
                 "Contents": "决定采用 Python 重写索引服务", "Attachments": []},
                {"ID": M2, "Timestamp": "2026-10-02T12:00:00+00:00",
                 "Contents": "下周测试新的摘要流水线", "Attachments": []},
            ], ensure_ascii=False),
        )
        archive.writestr(f"messages/c{DM}/channel.json", json.dumps({"id": DM, "type": 1, "name": "Alice"}))
        archive.writestr(
            f"messages/c{DM}/messages.csv",
            "ID,Timestamp,Contents,Attachments\n"
            f"{M3},2026-10-03T12:00:00+00:00,你好,https://example.com/demo.png\n",
        )
        # Sensitive account data must not be imported or interpreted.
        archive.writestr("account/user.json", '{"token":"SENSITIVE-DO-NOT-READ"}')
    raw.seek(0)
    return raw


class ImporterTests(unittest.TestCase):
    def test_official_zip_json_csv_and_dm(self):
        channels, messages, source = parse_discord_zip(example_zip())
        self.assertEqual(source, "discord-export")
        self.assertEqual(len(messages), 3)
        self.assertEqual({c["kind"] for c in channels}, {"guild", "dm"})
        self.assertEqual(messages[0]["content"], "决定采用 Python 重写索引服务")
        self.assertEqual(messages[-1]["attachments"][0]["url"], "https://example.com/demo.png")
        self.assertNotIn("SENSITIVE-DO-NOT-READ", json.dumps(messages))

    def test_preview_json(self):
        raw = json.dumps({
            "format": "dsc-preview-v1",
            "options": {"guildId": GUILD},
            "messages": [{"id": M1, "channel_id": CHANNEL, "content": "保留此想法",
                          "timestamp": "2026-10-01T00:00:00Z", "pinned": True}],
        }).encode("utf-8")
        channels, messages, source = parse_json_document(raw)
        self.assertEqual(source, "preview-json")
        self.assertTrue(messages[0]["pinned"])
        self.assertEqual(channels[0]["guild_id"], GUILD)

    def test_reject_oversized_or_unrelated_archives(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            archive.writestr("account/user.json", '{"email":"private"}')
        raw.seek(0)
        with self.assertRaisesRegex(ValueError, "未找到 Discord 消息文件"):
            parse_discord_zip(raw)


class StorageTests(unittest.TestCase):
    def test_import_dedup_search_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            db = ArchiveDB(Path(temp) / "archive.sqlite")
            channels, messages, kind = parse_discord_zip(example_zip())
            first = db.import_batch(channels, messages, kind, "demo.zip")
            second = db.import_batch(channels, messages, kind, "demo.zip")
            self.assertEqual(first, {"added": 3, "updated": 0})
            self.assertEqual(second, {"added": 0, "updated": 3})
            self.assertEqual(db.stats()["messages"], 3)
            self.assertEqual(db.stats()["channels"], 2)
            self.assertEqual(db.messages(query="Python")["total"], 1)
            self.assertEqual(db.messages(channel_id=DM)["total"], 1)
            summary_id = db.save_summary("测试摘要", "channel", CHANNEL, "ollama", "demo", 2,
                                         "关键决定：使用 Python", [M1, M2])
            self.assertEqual(db.summaries()[0]["id"], summary_id)


class SummarizationTests(unittest.TestCase):
    def test_provider_urls(self):
        self.assertEqual(validate_endpoint("ollama", "http://127.0.0.1:11434"),
                         "http://127.0.0.1:11434")
        self.assertEqual(validate_endpoint("openai", "https://api.example.com/v1"),
                         "https://api.example.com/v1")
        with self.assertRaises(ValueError):
            validate_endpoint("openai", "http://untrusted.example/v1")
        with self.assertRaises(ValueError):
            validate_endpoint("ollama", "https://remote.example")

    def test_mock_ai_pipeline_has_message_evidence(self):
        raw = [{"id": M1, "timestamp": "2026-10-01", "channel_name": "general",
                "content": "Python 索引架构"}]
        chunks = chunk_messages(raw)
        self.assertIn(M1, chunks[0])
        calls = []
        def mock_call(provider, model, endpoint, key, prompt):
            calls.append((provider, model, prompt))
            return "关键技术：Python 索引架构 [消息ID:" + M1 + "]"
        result = summarize_messages(
            raw, "ollama", "test", "http://127.0.0.1:11434", "",
            caller=mock_call,
        )
        self.assertIn(M1, result)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
