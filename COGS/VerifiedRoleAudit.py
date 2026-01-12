import asyncio
import discord
from discord.ext import commands

VERIFIED_ROLE_NAME = "Verified"
EMPLOYEE_ROLE_NAME = "Employee"
SPECIAL_VISITOR_ROLE_NAME = "Special Visitor"
ALERT_CHANNEL_NAME = "⚡｜butt-kicking"
KICK_REASON = "Kicked from Server - Verified Without Employee or Special Visitor"

RATE_LIMIT_DELAY = 2.5
EMBED_TITLE = "Role Compliance Check"


def _has_role(member: discord.Member, role_name: str) -> bool:
    return any(role.name.lower() == role_name.lower() for role in member.roles)


def _needs_action(member: discord.Member) -> bool:
    has_verified = _has_role(member, VERIFIED_ROLE_NAME)
    has_employee = _has_role(member, EMPLOYEE_ROLE_NAME)
    has_special = _has_role(member, SPECIAL_VISITOR_ROLE_NAME)
    return has_verified and not (has_employee or has_special)


class ActionView(discord.ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id

    @discord.ui.button(label="Ignore", style=discord.ButtonStyle.secondary)
    async def ignore_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger)
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("You don't have permission to kick members.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Guild not found.", ephemeral=True)
            return

        member = guild.get_member(self.target_user_id)
        if member is None:
            await interaction.response.send_message("User is no longer in the server.", ephemeral=True)
            return

        if not _needs_action(member):
            await interaction.response.send_message(
                "User already has the required role(s).",
                ephemeral=True,
            )
            return

        try:
            await member.kick(reason=KICK_REASON)
            await interaction.response.send_message(f"✅ {member.mention} has been kicked.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to kick that member.", ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message("Failed to kick the member due to an HTTP error.", ephemeral=True)


class VerifiedRoleAudit(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ready_once = False
        self._alerted_users: set[int] = set()
        self._lock = asyncio.Lock()

    def _get_alert_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        return discord.utils.get(guild.text_channels, name=ALERT_CHANNEL_NAME)

    async def _already_alerted(self, channel: discord.abc.Messageable, user_id: int) -> bool:
        if user_id in self._alerted_users:
            return True

        mention_a = f"<@{user_id}>"
        mention_b = f"<@!{user_id}>"
        try:
            async for msg in channel.history(limit=200):
                if msg.author.id != self.bot.user.id:
                    continue
                if (mention_a in msg.content) or (mention_b in msg.content):
                    if msg.embeds and msg.embeds[0].title == EMBED_TITLE:
                        self._alerted_users.add(user_id)
                        return True
        except Exception:
            pass
        return False

    async def _post_alert(self, member: discord.Member):
        channel = self._get_alert_channel(member.guild)
        if channel is None:
            return

        async with self._lock:
            if await self._already_alerted(channel, member.id):
                return

            embed = discord.Embed(
                title=EMBED_TITLE,
                description=(
                    f"{member.mention} has **{VERIFIED_ROLE_NAME}** but has neither "
                    f"**{EMPLOYEE_ROLE_NAME}** nor **{SPECIAL_VISITOR_ROLE_NAME}**."
                ),
                color=discord.Color.orange(),
            )
            view = ActionView(target_user_id=member.id)
            await channel.send(content=member.mention, embed=embed, view=view)
            self._alerted_users.add(member.id)

    async def _scan_guild(self, guild: discord.Guild):
        for member in guild.members:
            if _needs_action(member):
                await self._post_alert(member)
                await asyncio.sleep(RATE_LIMIT_DELAY)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._ready_once:
            return
        self._ready_once = True
        for guild in self.bot.guilds:
            await self._scan_guild(guild)
            await asyncio.sleep(RATE_LIMIT_DELAY)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if _needs_action(after) and not _needs_action(before):
            await asyncio.sleep(RATE_LIMIT_DELAY)
            await self._post_alert(after)

    @commands.command(name="rolescan")
    async def manual_scan(self, ctx: commands.Context):
        await self._scan_guild(ctx.guild)
        await ctx.reply("Scan complete.", mention_author=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VerifiedRoleAudit(bot))
