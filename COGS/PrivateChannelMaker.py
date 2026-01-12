import discord
import json
from discord.ext import commands
from discord import ui

CATEGORY_NAME = "Private Channels"
HUB_CHANNEL_NAME = "the-hub"
from COGS.paths import data_path

SERVER_JSON_PATH = data_path("server.json")  # Path to the uploaded file

# Role-based limits for text channels
ROLE_TEXT_LIMITS = {
    1344659660711526420: 5,  # Higher Role: 5 text channels
    1344659098205028383: 2,  # Medium Role: 2 text channels
    1268955216380825620: 1   # Lower Role: 1 text channel
}

MAX_VOICE_CHANNELS = 1  # Max voice channels per user

# Allowed user ID who can always create channels (and speak in hub)
ALLOWED_USER_ID = 298121351871594497

def load_json():
    """Loads the server.json file."""
    with open(SERVER_JSON_PATH, "r", encoding="utf-8") as file:
        return json.load(file)

def save_json(data):
    """Saves changes to the server.json file."""
    with open(SERVER_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

def load_verified_users():
    """Loads the verified users from server.json."""
    data = load_json()
    return {entry["user_id"]: entry["habbo"] for entry in data.get("verified_users", [])}

VERIFIED_USERS = load_verified_users()

class PrivateChannelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_or_create_category(self, guild):
        """Finds or creates the 'Private Channels' category with restricted access."""
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if category is None:
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
            category = await guild.create_category(CATEGORY_NAME, overwrites=overwrites)
        return category

    async def delete_existing_hub(self, guild):
        """Deletes the existing hub channel if it exists."""
        existing_channel = discord.utils.get(guild.text_channels, name=HUB_CHANNEL_NAME)
        if existing_channel:
            await existing_channel.delete()

    async def create_hub_channel(self, guild):
        """Creates the hub channel and keeps it at the top."""
        category = await self.get_or_create_category(guild)

        # Build overwrites so the roles in ROLE_TEXT_LIMITS can see but not speak,
        # and ALLOWED_USER_ID can see/speak. Everyone else is denied access.
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }

        for role_id in ROLE_TEXT_LIMITS:
            role = guild.get_role(role_id)
            if role:
                # Can see, but cannot send messages or add reactions
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    add_reactions=False
                )

        allowed_user = guild.get_member(ALLOWED_USER_ID)
        if allowed_user:
            # Allowed user can see, speak, and add reactions
            overwrites[allowed_user] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                add_reactions=True
            )

        hub_channel = await guild.create_text_channel(
            HUB_CHANNEL_NAME,
            category=category,
            overwrites=overwrites
        )
        await hub_channel.edit(position=0)

        embed = discord.Embed(
            title="Private Channels",
            description="Click the buttons below to create a private **Text** or **Voice** channel",
            color=discord.Color.blue()
        )

        view = PrivateChannelButton()
        await hub_channel.send(embed=embed, view=view)

    @commands.command(name="refresh")
    async def refresh_hub(self, ctx):
        """Deletes the hub channel and recreates it at the top."""
        await self.delete_existing_hub(ctx.guild)
        await self.create_hub_channel(ctx.guild)
        await ctx.send("Hub channel refreshed!", delete_after=5)

class PrivateChannelButton(discord.ui.View):
    """Buttons for creating private channels."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Custom Text Channel", style=discord.ButtonStyle.green, custom_id="create_text")
    async def create_text_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_channel(interaction, "text")

    @discord.ui.button(label="Custom Voice Channel", style=discord.ButtonStyle.blurple, custom_id="create_voice")
    async def create_voice_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_channel(interaction, "voice")

    async def create_channel(self, interaction: discord.Interaction, channel_type: str):
        user_id = str(interaction.user.id)
        user_roles = [role.id for role in interaction.user.roles]

        # Check if the user has a required role or is the allowed user
        if not any(role in ROLE_TEXT_LIMITS for role in user_roles) and interaction.user.id != ALLOWED_USER_ID:
            await interaction.response.send_message("? You do not have permission to create private channels.", ephemeral=True)
            return

        # Determine user's max text channels based on roles
        max_text_channels = max((ROLE_TEXT_LIMITS.get(role, 0) for role in user_roles), default=0)

        # Load JSON data
        data = load_json()
        user_channels = data.get("user_channels", {})

        # Check text channel limit
        if channel_type == "text":
            if user_id in user_channels and len(user_channels[user_id].get("text", [])) >= max_text_channels:
                await interaction.response.send_message(
                    f"You can only have up to {max_text_channels} private text channels!",
                    ephemeral=True
                )
                return

        # Check voice channel limit
        if channel_type == "voice":
            if user_id in user_channels and len(user_channels[user_id].get("voice", [])) >= MAX_VOICE_CHANNELS:
                await interaction.response.send_message(
                    f"You can only have 1 private voice channel!",
                    ephemeral=True
                )
                return

        await interaction.response.send_modal(PrivateChannelModal(user_id, channel_type))

class PrivateChannelModal(ui.Modal):
    """Modal to get user input for channel creation."""
    def __init__(self, user_id: str, channel_type: str):
        super().__init__(title="Create Your Private Channel")
        self.user_id = user_id
        self.channel_type = channel_type

    name = ui.TextInput(label="Channel Name", placeholder="Enter a unique name", max_length=25)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(CATEGORY_NAME)

        # Load JSON data
        data = load_json()
        user_channels = data.setdefault("user_channels", {})

        # Ensure user's entry exists
        if self.user_id not in user_channels:
            user_channels[self.user_id] = {}

        # Ensure text list exists before appending
        if self.channel_type == "text":
            user_channels[self.user_id].setdefault("text", [])

        # Get user's Habbo name or fallback to username
        habbo_name = VERIFIED_USERS.get(self.user_id, interaction.user.name)
        habbo_avatar_url = f"https://www.habbo.com/habbo-imaging/avatarimage?user={habbo_name}&direction=2&head_direction=3&gesture=sml&size=m"

        # Create private channel (text or voice)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True)
        }

        if self.channel_type == "text":
            channel = await guild.create_text_channel(self.name.value, category=category, overwrites=overwrites)
            user_channels[self.user_id]["text"].append(channel.id)  # Append new text channel ID
        else:
            channel = await guild.create_voice_channel(self.name.value, category=category, overwrites=overwrites)
            user_channels[self.user_id]["voice"] = [channel.id]  # Only 1 voice channel

        data["user_channels"] = user_channels
        save_json(data)

        # Embed announcement
        embed = discord.Embed(
            title=f"{self.name.value}",
            description=f"Owner: {interaction.user.mention}",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=habbo_avatar_url)
        await channel.send(embed=embed)

        await interaction.response.send_message(
            f"Your private {self.channel_type} channel [{channel.mention}] has been created!",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(PrivateChannelCog(bot))
