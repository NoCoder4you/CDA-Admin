import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from COGS.ServerVerify import HabboVerifyCog


class VerificationJoinTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        directory = Path(self.temp_dir.name)

        # Avoid starting the production cleanup loop when testing the listener.
        self.cog = HabboVerifyCog.__new__(HabboVerifyCog)
        self.cog.server_data_path = directory / "server.json"
        self.cog.verification_prompts_path = directory / "verification_prompts.json"

        self.channel = SimpleNamespace(
            id=1234,
            send=AsyncMock(return_value=SimpleNamespace(id=4567)),
            get_partial_message=MagicMock(),
        )
        self.delete = AsyncMock()
        self.channel.get_partial_message.return_value = SimpleNamespace(
            delete=self.delete
        )
        self.guild = SimpleNamespace(
            id=9000, get_channel=MagicMock(return_value=self.channel)
        )
        self.member = SimpleNamespace(
            id=101, mention="<@101>", guild=self.guild, bot=False
        )
        self.bot = SimpleNamespace(
            tree=SimpleNamespace(
                fetch_commands=AsyncMock(
                    return_value=[SimpleNamespace(name="verify", id=8000)]
                )
            ),
            fetch_channel=AsyncMock(return_value=self.channel),
        )
        self.cog.bot = self.bot
        self.write_server([])

    def write_server(self, verified_users):
        self.cog.server_data_path.write_text(
            json.dumps(
                {
                    "verified_users": verified_users,
                    "channels": {"verification": self.channel.id},
                }
            ),
            encoding="utf-8",
        )

    async def test_unverified_member_gets_ping_and_clickable_instructions(self):
        await self.cog.on_member_join(self.member)

        self.channel.send.assert_awaited_once()
        kwargs = self.channel.send.await_args.kwargs
        self.assertEqual("<@101>", kwargs["content"])
        embed = kwargs["embed"]
        self.assertEqual("Verify Your Habbo Account", embed.title)
        self.assertEqual(
            ["Step 1", "Step 2", "Step 3", "Need Help"],
            [field.name for field in embed.fields],
        )
        self.assertIn("</verify:8000>", embed.fields[0].value)
        self.assertIn("Habbo Motto", embed.fields[1].value)

        prompts = json.loads(
            self.cog.verification_prompts_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            {"channel_id": 1234, "message_id": 4567},
            prompts["9000:101"],
        )

    async def test_member_already_in_server_json_is_not_prompted(self):
        self.write_server([{"user_id": "101", "habbo": "AlreadyVerified"}])
        await self.cog.on_member_join(self.member)
        self.channel.send.assert_not_awaited()
        self.bot.tree.fetch_commands.assert_not_awaited()

    async def test_bot_accounts_are_not_prompted(self):
        self.member.bot = True
        await self.cog.on_member_join(self.member)
        self.channel.send.assert_not_awaited()

    async def test_verify_cleanup_deletes_saved_embed_after_restart(self):
        await self.cog.on_member_join(self.member)

        # Simulate a restarted cog with the same on-disk prompt records.
        restarted = HabboVerifyCog.__new__(HabboVerifyCog)
        restarted.verification_prompts_path = self.cog.verification_prompts_path
        restarted.bot = self.bot
        await restarted._delete_verification_prompt(self.member)

        self.channel.get_partial_message.assert_called_once_with(4567)
        self.delete.assert_awaited_once()
        self.assertEqual(
            {}, json.loads(restarted.verification_prompts_path.read_text())
        )

    async def test_rejoin_removes_previous_instructions(self):
        await self.cog.on_member_join(self.member)
        await self.cog.on_member_join(self.member)
        self.delete.assert_awaited_once()
        self.assertEqual(2, self.channel.send.await_count)

    async def test_unsynced_command_uses_fallback(self):
        self.bot.tree.fetch_commands.return_value = []
        await self.cog.on_member_join(self.member)
        self.assertIn(
            "/verify",
            self.channel.send.await_args.kwargs["embed"].fields[0].value,
        )


if __name__ == "__main__":
    unittest.main()
