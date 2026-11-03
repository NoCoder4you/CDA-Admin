import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from COGS import NameChange
from COGS.RoleUpdater import AutoRoleUpdater


class NameChangeRoleRefreshTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "server.json"
        self.path.write_text(
            json.dumps({"verified_users": [{"user_id": "101", "habbo": "OldHabbo"}]}),
            encoding="utf-8",
        )
        path_patch = patch.object(NameChange, "SERVER_JSON_PATH", self.path)
        path_patch.start()
        self.addCleanup(path_patch.stop)

        self.member = MagicMock()
        self.member.edit = AsyncMock()
        self.guild = MagicMock()
        self.guild.get_member.return_value = self.member
        self.role_updater = MagicMock()
        self.role_updater.update_member_roles = AsyncMock(return_value=True)
        self.client = MagicMock()
        self.client.cogs = {}
        self.client.get_cog.return_value = self.role_updater

        self.interaction = MagicMock()
        self.interaction.user.roles = [SimpleNamespace(name="Discord Admins")]
        self.interaction.response.defer = AsyncMock()
        self.interaction.followup.send = AsyncMock()
        self.interaction.guild = self.guild
        self.interaction.client = self.client

    async def approve(self):
        view = NameChange.NameChangeView(101, "OldHabbo", "NewHabbo")
        view.update_embed = AsyncMock()
        await view.approve(self.interaction, None)
        return view

    async def test_approval_checks_roles_immediately_using_new_habbo_name(self):
        view = await self.approve()
        self.role_updater.update_member_roles.assert_awaited_once_with(
            self.member, "NewHabbo"
        )
        self.member.edit.assert_awaited_once_with(nick="NewHabbo")
        self.assertEqual(
            "NewHabbo",
            json.loads(self.path.read_text(encoding="utf-8"))["verified_users"][0]["habbo"],
        )
        view.update_embed.assert_awaited_once_with(
            self.interaction, "approved", self.interaction.user
        )
        self.interaction.followup.send.assert_not_awaited()

    async def test_failed_role_check_does_not_undo_approved_name(self):
        self.role_updater.update_member_roles.side_effect = RuntimeError("API unavailable")
        view = await self.approve()
        self.assertEqual(
            "NewHabbo",
            json.loads(self.path.read_text(encoding="utf-8"))["verified_users"][0]["habbo"],
        )
        view.update_embed.assert_awaited_once()
        self.interaction.followup.send.assert_awaited_once()
        self.assertTrue(self.interaction.followup.send.await_args.kwargs["ephemeral"])


class SingleMemberRoleUpdaterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "server.json"
        self.path.write_text(
            json.dumps({"verified_users": [{"user_id": "101", "habbo": "NewHabbo"}]}),
            encoding="utf-8",
        )

        # Avoid starting the scheduled Discord loop in the constructor.
        self.updater = AutoRoleUpdater.__new__(AutoRoleUpdater)
        self.updater._member_role_locks = {}
        self.updater.server_data_path = self.path
        self.updater._get_habbo_user_and_groups = AsyncMock(
            return_value=({"motto": "CDA"}, [{"id": "group-1"}])
        )
        self.updater.assign_roles = AsyncMock(return_value=(["New Role"], ["Old Role"]))
        self.log_channel = MagicMock()
        self.log_channel.send = AsyncMock()
        self.guild = MagicMock()
        self.guild.get_channel.return_value = self.log_channel
        self.member = SimpleNamespace(
            id=101, guild=self.guild, mention="<@101>"
        )

    async def test_refresh_uses_current_profile_and_logs_changes(self):
        result = await self.updater.update_member_roles(
            self.member, "NewHabbo", session=object()
        )
        self.assertTrue(result)
        self.updater._get_habbo_user_and_groups.assert_awaited_once()
        self.assertEqual(
            "NewHabbo",
            self.updater._get_habbo_user_and_groups.await_args.args[1],
        )
        self.updater.assign_roles.assert_awaited_once_with(
            self.member, [{"id": "group-1"}], self.guild, "CDA"
        )
        self.log_channel.send.assert_awaited_once()

    async def test_stale_name_never_reassigns_roles(self):
        result = await self.updater.update_member_roles(
            self.member, "OldHabbo", session=object()
        )
        self.assertFalse(result)
        self.updater._get_habbo_user_and_groups.assert_not_awaited()
        self.updater.assign_roles.assert_not_awaited()

    async def test_habbo_outage_does_not_remove_roles(self):
        self.updater._get_habbo_user_and_groups.return_value = (None, None)
        result = await self.updater.update_member_roles(
            self.member, "NewHabbo", session=object()
        )
        self.assertFalse(result)
        self.updater.assign_roles.assert_not_awaited()
        self.log_channel.send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
