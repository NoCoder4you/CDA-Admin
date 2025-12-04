import discord
import json
import os
from discord.ext import commands
from discord import ui

SERVER_DATA_FILE = "server.json"

# Define role limits (role_id: max roles a user with that role can create)
ROLE_LIMITS = {
    1344659660711526420: 3,  # Example Role ID: 3 roles allowed
    1344659098205028383: 2,  # Example Role ID: 2 roles allowed
    1268955216380825620: 1   # Example Role ID: 1 role allowed
}

class RoleModal(ui.Modal, title="Create Custom Role"):
    role_name = ui.TextInput(label="Role Name", placeholder="Enter the role name")
    role_color = ui.TextInput(label="Role Hex Color", placeholder="#3498db", required=True)

    def __init__(self, guild: discord.Guild, user: discord.Member):
        super().__init__()
        self.guild = guild
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        role_name = self.role_name.value
        hex_color = self.role_color.value.lstrip("#")

        # Validate hex color
        try:
            color = discord.Color(int(hex_color, 16))
        except ValueError:
            await interaction.response.send_message("? Invalid hex color! Use a format like `#3498db`.", ephemeral=True)
            return

        # Create the role
        role = await self.guild.create_role(name=role_name, color=color)

        # Assign the role to the user
        await self.user.add_roles(role)
        await interaction.response.send_message(f"? Role `{role_name}` created & assigned to you!", ephemeral=True)

        # Store role in JSON
        self.store_role(role.id, role_name, f"#{hex_color}", self.user.id)

    def store_role(self, role_id, role_name, hex_color, user_id):
        """Store the created role in server.json"""
        if not os.path.exists(SERVER_DATA_FILE):
            with open(SERVER_DATA_FILE, "w") as f:
                json.dump({"user_roles": []}, f)

        with open(SERVER_DATA_FILE, "r") as f:
            data = json.load(f)

        if "user_roles" not in data:
            data["user_roles"] = []

        data["user_roles"].append({
            "role_id": role_id,
            "role_name": role_name,
            "hex_color": hex_color,
            "created_by": user_id
        })

        with open(SERVER_DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)


class RoleButton(ui.View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.guild = guild

    @ui.button(label="Create Custom Role", style=discord.ButtonStyle.green)
    async def create_role(self, interaction: discord.Interaction, button: ui.Button):
        user = interaction.user

        # Check if user can create a role before opening modal
        max_roles = 0

        for role in user.roles:
            if role.id in ROLE_LIMITS:
                max_roles = max(max_roles, ROLE_LIMITS[role.id])

        if max_roles == 0:
            await interaction.response.send_message(
                "? You do not have permission to create custom roles.", ephemeral=True
            )
            return

        user_created_roles = self.get_user_role_count(user.id)

        if user_created_roles >= max_roles:
            await interaction.response.send_message(
                f"? You have reached your limit of {max_roles} custom roles.", ephemeral=True
            )
            return

        # Open modal if the user is within their limit
        await interaction.response.send_modal(RoleModal(self.guild, user))

    def get_user_role_count(self, user_id):
        """Retrieve the number of roles a user has already created"""
        if not os.path.exists(SERVER_DATA_FILE):
            return 0

        with open(SERVER_DATA_FILE, "r") as f:
            data = json.load(f)

        if "user_roles" not in data:
            return 0

        return sum(1 for role in data["user_roles"] if role["created_by"] == user_id)


class PrivateChannelsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if channel.name == "the-hub" and isinstance(channel, discord.TextChannel):
            embed = discord.Embed(
                title="Custom Role Creator",
                description="Click the button below to create a custom role!\n"
                            "You will be automatically assigned to the role you create.\n"
                            "Role creation is limited based on your highest role.",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Enter a role name and a hex color code.")

            view = RoleButton(channel.guild)
            await channel.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(PrivateChannelsCog(bot))
