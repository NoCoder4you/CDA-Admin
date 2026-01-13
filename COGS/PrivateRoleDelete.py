import discord
import json
import os
from discord.ext import commands

from COGS.paths import data_path

SERVER_DATA_FILE = data_path("JSON/server.json")

class RoleDeletionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        """Triggered when a role is deleted"""
        if not os.path.exists(SERVER_DATA_FILE):
            return

        # Load JSON data
        with open(SERVER_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "user_roles" not in data:
            return

        # Find the role in stored data
        deleted_role = next((r for r in data["user_roles"] if r["role_id"] == role.id), None)

        if deleted_role:
            # Remove role from JSON data
            data["user_roles"] = [r for r in data["user_roles"] if r["role_id"] != role.id]

            # Save updated JSON
            with open(SERVER_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

async def setup(bot):
    await bot.add_cog(RoleDeletionCog(bot))
