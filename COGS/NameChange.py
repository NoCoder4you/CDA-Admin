import discord
from discord.ext import commands
from discord import app_commands, Interaction, ui
import json
from pathlib import Path

from COGS.paths import data_path

SERVER_JSON_PATH = data_path("JSON/server.json")
REQUEST_CHANNEL_ID = 1249491219348852828  # Channel to send the request embed

def load_server_json():
    with open(SERVER_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_server_json(data):
    with open(SERVER_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def sync_server_data(bot, data):
    for cog in bot.cogs.values():
        server_data_path = getattr(cog, "server_data_path", None)
        if server_data_path is None:
            continue
        if Path(server_data_path).resolve() == Path(SERVER_JSON_PATH).resolve():
            cog.server_data = data

def get_discord_admin_role(guild: discord.Guild):
    return discord.utils.get(guild.roles, name="Discord Admin")


def has_discord_admin_role(member: discord.Member):
    return any(role.name.lower() == "discord admin" for role in member.roles)


def discord_admin_role_label(guild: discord.Guild):
    role = get_discord_admin_role(guild)
    return role.mention if role else "Discord Admin"

class NameChangeView(ui.View):
    def __init__(self, user_id: int, current_username: str, new_username: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.current_username = current_username
        self.new_username = new_username

    async def update_embed(self, interaction, status, mod: discord.Member):
        color = discord.Color.orange()
        approved_by = None
        rejected_by = None
        if status == "approved":
            color = discord.Color.green()
            approved_by = mod.mention
        elif status == "rejected":
            color = discord.Color.red()
            rejected_by = mod.mention

        embed = discord.Embed(
            title="Username Change Request",
            color=color,
        )
        embed.add_field(name="Current Username", value=self.current_username, inline=False)
        embed.add_field(name="Requested New Username", value=self.new_username, inline=False)
        if approved_by:
            embed.add_field(name="Approved By", value=approved_by, inline=False)
        elif rejected_by:
            embed.add_field(name="Rejected By", value=rejected_by, inline=False)
        else:
            embed.set_footer(text="Pending Approval")

        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    @ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: Interaction, button: ui.Button):
        if not has_discord_admin_role(interaction.user):
            await interaction.response.send_message(
                (
                    "You do not have permission to approve. "
                    f"Only {discord_admin_role_label(interaction.guild)} can approve."
                ),
                ephemeral=True,
            )
            return

        data = load_server_json()
        verified_users = data.setdefault("verified_users", [])
        found = False
        for user in verified_users:
            if str(user.get("user_id")) == str(self.user_id):
                user["habbo"] = self.new_username
                found = True
                break
        if not found:
            verified_users.append({"user_id": str(self.user_id), "habbo": self.new_username})
        save_server_json(data)
        sync_server_data(interaction.client, data)
        
        # Attempt to change nickname in the guild
        guild = interaction.guild
        if guild:
            member = guild.get_member(self.user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(self.user_id)
                except Exception:
                    member = None
            if member:
                try:
                    await member.edit(nick=self.new_username)
                except Exception:
                    pass  # Silently ignore errors (lack of permissions, etc.)

        await self.update_embed(interaction, "approved", interaction.user)

    @ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: Interaction, button: ui.Button):
        if not has_discord_admin_role(interaction.user):
            await interaction.response.send_message(
                (
                    "You do not have permission to reject. "
                    f"Only {discord_admin_role_label(interaction.guild)} can reject."
                ),
                ephemeral=True,
            )
            return
        await self.update_embed(interaction, "rejected", interaction.user)

class NameChangeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="namechange",
        description="Input New Username"
    )
    @app_commands.describe(username="The new username you want to set.")
    async def namechange(self, interaction: discord.Interaction, username: str):
        user_id = str(interaction.user.id)
        data = load_server_json()
        user_entry = next(
            (user for user in data.get("verified_users", []) if str(user.get("user_id")) == user_id),
            None,
        )

        if not user_entry:
            await interaction.response.send_message("You are not a verified user.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        current_username = user_entry["habbo"]
        embed = discord.Embed(
            title="Username Change Request",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Current Username", value=current_username, inline=False)
        embed.add_field(name="Requested New Username", value=username, inline=False)
        embed.add_field(
            name="Required Role",
            value=discord_admin_role_label(interaction.guild),
            inline=False,
        )
        embed.set_footer(text="Pending Approval")

        view = NameChangeView(user_id=int(user_id), current_username=current_username, new_username=username)

        request_channel = interaction.client.get_channel(REQUEST_CHANNEL_ID)
        if request_channel is None:
            request_channel = await interaction.client.fetch_channel(REQUEST_CHANNEL_ID)
        if request_channel is None:
            await interaction.followup.send(
                "Failed to send request: Could not find the request channel.",
                ephemeral=True,
            )
            return

        await request_channel.send(embed=embed, view=view)
        await interaction.followup.send(
            f"Your name change request has been sent to <#{REQUEST_CHANNEL_ID}> for approval.",
            ephemeral=True,
        )

async def setup(bot):
    await bot.add_cog(NameChangeCog(bot))
