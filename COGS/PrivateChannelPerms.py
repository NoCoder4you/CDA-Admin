import discord
from discord.ext import commands
import json
from fuzzywuzzy import process

# Load server.json data
with open("/home/pi/discord-bots/bots/CDA Admin/server.json", "r") as f:
    server_data = json.load(f)


class ChannelSettingsCog(commands.Cog):
    """Handles 'channel settings' commands and user interactions."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        user_id = str(message.author.id)
        
        # Ensure message is inside a valid category
        private_category_name = "Private Channels"
        if message.channel.category and message.channel.category.name != private_category_name:
            return  # Ignore messages outside the "Private Channels" category

        # Refresh the server data dynamically
        with open("/home/pi/discord-bots/bots/CDA Admin/server.json", "r") as f:
            server_data = json.load(f)

        if user_id in server_data["user_channels"]:
            user_channels = server_data["user_channels"][user_id]["text"]

            if message.channel.id in user_channels and message.content.lower() == "channel settings":
                await message.channel.send(" ", view=ChannelSettingsView(message.channel, user_id))





class ChannelSettingsView(discord.ui.View):
    """View for main channel settings with Permissions & Users buttons."""

    def __init__(self, channel: discord.TextChannel, owner_id):
        super().__init__(timeout=180)
        self.channel = channel
        self.owner_id = owner_id

    @discord.ui.button(label="Permissions", style=discord.ButtonStyle.primary)
    async def permissions(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(view=PermissionsView(self.channel, self.owner_id, interaction.guild), ephemeral=True)

    @discord.ui.button(label="Users", style=discord.ButtonStyle.secondary)
    async def users(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(view=UserSettingsView(self.channel, self.owner_id, interaction.guild), ephemeral=True)

class PermissionsView(discord.ui.View):
    """Lists all invited users as buttons to modify their permissions."""

    def __init__(self, channel: discord.TextChannel, owner_id, guild: discord.Guild):
        super().__init__(timeout=180)
        self.channel = channel
        self.owner_id = owner_id
        self.guild = guild

        owner_id_str = str(owner_id)
        invited_users = server_data["user_channels"].get(owner_id_str, {}).get("invited_users", [])

        if not invited_users:
            self.add_item(discord.ui.Button(label="No invited users", disabled=True))

        for user_id in invited_users:
            user = guild.get_member(user_id)
            if user:
                self.add_item(UserPermissionButton(user, channel))


class UserPermissionButton(discord.ui.Button):
    """Button that opens the permission toggle view for a user."""

    def __init__(self, user: discord.Member, channel: discord.TextChannel):
        super().__init__(label=user.display_name, style=discord.ButtonStyle.secondary)
        self.user = user
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Modify {self.user.display_name}'s permissions:", 
            view=UserPermissionsToggleView(self.channel, self.user), ephemeral=True
        )


class UserPermissionsToggleView(discord.ui.View):
    """View for toggling user permissions in a channel."""

    def __init__(self, channel: discord.TextChannel, target_user: discord.Member):
        super().__init__(timeout=180)
        self.channel = channel
        self.target_user = target_user

        permissions = [
            "Send Messages",
            "Attach Files",
            "Embed Links",
            "Use External Emojis",
            "Mention Everyone",
            "Add Reactions"
        ]

        for perm in permissions:
            self.add_item(PermissionToggleButton(perm, self.channel, self.target_user))


class PermissionToggleButton(discord.ui.Button):
    """Toggles a specific permission for a user."""

    def __init__(self, perm_name: str, channel: discord.TextChannel, target_user: discord.Member):
        self.perm_name = perm_name
        self.channel = channel
        self.target_user = target_user
        self.permission_mapping = {
            "Send Messages": "send_messages",
            "Attach Files": "attach_files",
            "Embed Links": "embed_links",
            "Use External Emojis": "external_emojis",
            "Mention Everyone": "mention_everyone",
            "Add Reactions": "add_reactions"
        }

        # Get current permission state
        overwrite = channel.overwrites_for(target_user)
        perm_status = getattr(overwrite, self.permission_mapping[perm_name], None)

        button_style = discord.ButtonStyle.success if perm_status else discord.ButtonStyle.danger
        super().__init__(label=f"{perm_name} \u2705" if perm_status else f"{perm_name} \u274C", style=button_style)

    async def callback(self, interaction: discord.Interaction):
        overwrite = self.channel.overwrites_for(self.target_user)
        perm_attr = self.permission_mapping[self.perm_name]
        current_status = getattr(overwrite, perm_attr, None)

        # Toggle the permission
        new_status = not current_status if current_status is not None else True
        setattr(overwrite, perm_attr, new_status)

        # Apply the new permission settings
        await self.channel.set_permissions(self.target_user, overwrite=overwrite)

        # Update the button label and style
        self.label = f"{self.perm_name} " if new_status else f"{self.perm_name}"
        self.style = discord.ButtonStyle.success if new_status else discord.ButtonStyle.danger
        await interaction.response.edit_message(view=self.view)

class InviteUserModal(discord.ui.Modal, title="Invite User"):
    """Modal form to invite users by name."""
    
    username = discord.ui.TextInput(label="Enter Username or Nickname", placeholder="e.g. JohnDoe123", required=True)

    def __init__(self, channel, owner_id):
        super().__init__()
        self.channel = channel
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.owner_id):
            await interaction.response.send_message("Only the channel owner can invite users.", ephemeral=True)
            return

        search_name = self.username.value.lower()

        all_users = {member: (member.name.lower(), member.display_name.lower()) for member in interaction.guild.members}
        all_names = [name for user in all_users for name in all_users[user]]

        best_match, score = process.extractOne(search_name, all_names)

        if score < 60:
            await interaction.response.send_message(f"No close match found for `{search_name}`. Try again.", ephemeral=True)
            return

        matched_users = [user for user, names in all_users.items() if best_match in names]

        invited_user = matched_users[0] if len(matched_users) == 1 else None

        if not invited_user:
            await interaction.response.send_message("Multiple users found. Please be more specific.", ephemeral=True)
            return

        owner_id_str = str(self.owner_id)
        if "invited_users" not in server_data["user_channels"][owner_id_str]:
            server_data["user_channels"][owner_id_str]["invited_users"] = []

        if invited_user.id not in server_data["user_channels"][owner_id_str]["invited_users"]:
            server_data["user_channels"][owner_id_str]["invited_users"].append(invited_user.id)

            with open("../server.json", "w") as f:
                json.dump(server_data, f, indent=4)

            await self.channel.set_permissions(invited_user, read_messages=True, send_messages=True)
            await interaction.response.send_message(f"{invited_user.display_name} has been invited.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{invited_user.display_name} is already in the channel.", ephemeral=True)

class RemoveUserModal(discord.ui.Modal, title="Remove User"):
    """Modal form to remove users by name."""
    
    username = discord.ui.TextInput(label="Enter Username or Nickname", placeholder="e.g. JohnDoe123", required=True)

    def __init__(self, channel, owner_id):
        super().__init__()
        self.channel = channel
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.owner_id):
            await interaction.response.send_message("Only the channel owner can remove users.", ephemeral=True)
            return

        search_name = self.username.value.lower()

        # Get all server members and their names
        all_users = {member: (member.name.lower(), member.display_name.lower()) for member in interaction.guild.members}
        all_names = [name for user in all_users for name in all_users[user]]

        # Use fuzzy search to find the closest match
        best_match, score = process.extractOne(search_name, all_names)

        if score < 60:
            await interaction.response.send_message(f"No close match found for `{search_name}`. Try again.", ephemeral=True)
            return

        matched_users = [user for user, names in all_users.items() if best_match in names]

        removed_user = matched_users[0] if len(matched_users) == 1 else None

        if not removed_user:
            await interaction.response.send_message("Multiple users found. Please be more specific.", ephemeral=True)
            return

        if removed_user.id == int(self.owner_id):
            await interaction.response.send_message("You cannot remove yourself from your own channel.", ephemeral=True)
            return

        owner_id_str = str(self.owner_id)
        if "invited_users" in server_data["user_channels"][owner_id_str] and removed_user.id in server_data["user_channels"][owner_id_str]["invited_users"]:
            server_data["user_channels"][owner_id_str]["invited_users"].remove(removed_user.id)

            with open("../server.json", "w") as f:
                json.dump(server_data, f, indent=4)

            # Revoke permissions to remove user from the channel
            await self.channel.set_permissions(removed_user, overwrite=None)

            await interaction.response.send_message(f"{removed_user.display_name} has been removed from the channel.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{removed_user.display_name} is not in the channel.", ephemeral=True)


class UserSettingsView(discord.ui.View):
    """View for managing users (Permissions, Invite, Remove)."""

    def __init__(self, channel: discord.TextChannel, owner_id, guild: discord.Guild):
        super().__init__(timeout=180)
        self.channel = channel
        self.owner_id = owner_id
        self.guild = guild

    @discord.ui.button(label="Invite", style=discord.ButtonStyle.success)
    async def invite_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InviteUserModal(self.channel, self.owner_id))

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger)
    async def remove_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveUserModal(self.channel, self.owner_id))


async def setup(bot):
    await bot.add_cog(ChannelSettingsCog(bot))
