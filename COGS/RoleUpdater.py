import discord
import aiohttp
import json
import os
import time
from discord.ext import commands, tasks
from COGS.paths import data_path

class AutoRoleUpdater(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.roles_file_path = data_path("JSON/rolesbadges.json")
        self.server_data_path = data_path("JSON/server.json")
        self.roles_data = self.load_roles_data()
        self.server_data = self.load_server_data()
        self.verified_role_id = 1277489459226738808
        self.awaiting_verification_role_id = 1248310200939581594

        self.update_roles_task.start()  # Start the automatic update task

    def load_roles_data(self):
        """Load the role mapping from JSON."""
        if os.path.exists(self.roles_file_path):
            try:
                with open(self.roles_file_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    return data.get("roles", {})
            except json.JSONDecodeError:
                print(f"Error decoding {self.roles_file_path}. Ensure it's valid JSON.")
                return {}
        return {}

    def load_server_data(self):
        """Load the list of verified users from JSON."""
        if os.path.exists(self.server_data_path):
            try:
                with open(self.server_data_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    return data if "verified_users" in data else {"verified_users": []}
            except json.JSONDecodeError:
                print(f"Error decoding {self.server_data_path}. Ensure it's valid JSON.")
                return {"verified_users": []}
        return {"verified_users": []}

    @tasks.loop(minutes=10)  # Runs every 10 minutes
    async def update_roles_task(self):
        """Automatically check and update roles for all verified users."""
        guild = self.bot.get_guild(1248307521119060028)  # Replace with your server's ID

        if not guild:
            print("Guild not found.")
            return

        async with aiohttp.ClientSession() as session:
            for user_data in self.server_data["verified_users"]:
                user_id = int(user_data["user_id"])
                habbo_name = user_data["habbo"]

                member = guild.get_member(user_id)
                if not member:
                    continue  # Skip if user is not found in the server

                # Fetch Habbo data
                user_url = f"https://www.habbo.com/api/public/users?name={habbo_name}"
                async with session.get(user_url) as user_response:
                    if user_response.status == 200:
                        user_json = await user_response.json()
                        habbo_id = user_json.get("uniqueId")

                        groups_url = f"https://www.habbo.com/api/public/users/{habbo_id}/groups"
                        async with session.get(groups_url) as groups_response:
                            if groups_response.status == 200:
                                groups_data = await groups_response.json()

                                # Assign roles only if needed
                                added_roles, removed_roles = await self.assign_roles(member, groups_data, guild)

                                # Skip logging or updating if no changes are needed
                                if added_roles is None and removed_roles is None:
                                    continue

                                # Log role updates if they occurred
                                log_channel = guild.get_channel(1248316058520260713)  # Replace with your log channel ID
                                if log_channel:
                                    embed = discord.Embed(title="Roles Updated", color=discord.Color.green())
                                    embed.add_field(name="User", value=f"{member.mention}", inline=False)
                                    if added_roles:
                                        embed.add_field(name="Added Roles", value="\n".join(added_roles), inline=False)
                                    if removed_roles:
                                        embed.add_field(name="Removed Roles", value="\n".join(removed_roles), inline=False)
                                    await log_channel.send(embed=embed)

    async def assign_roles(self, member, groups_data, guild):
        """
        Assign roles based on Habbo groups:
        - EmployeeRoles: assign ONLY the single highest role (based on JSON order).
        - DonatorRoles/Misc/SpecialUnits: additive.
        - 'CDA Employee' and 'iC' umbrella flags come from ANY matched employee role.
        """
        roles_data = self.roles_data
        added_roles = []
        removed_roles = []

        cda_employee_role_id = 1248313244481884220
        ic_member_role_id = 1249819550015426571

        current_roles = {role.id for role in member.roles}
        expected_roles = set()

        # Track all managed role IDs so we can remove ones users shouldn't have
        valid_role_ids = set()
        for category in ["EmployeeRoles", "DonatorRoles", "Misc", "SpecialUnits"]:
            for role_data in roles_data.get(category, []):
                rid = role_data.get("role_id")
                if rid:
                    valid_role_ids.add(rid)

        # Build a set of Habbo group IDs for quick lookups
        group_ids = {g.get("id") for g in groups_data if isinstance(g, dict) and g.get("id")}

        # Employee roles: collect all matches, then pick the highest by JSON order (first match)
        employee_roles = roles_data.get("EmployeeRoles", [])
        matched_employee_roles = [rd for rd in employee_roles if rd.get("group_id") in group_ids]
        highest_employee_role = matched_employee_roles[0] if matched_employee_roles else None

        has_cda_employee = False
        has_ic_role = False

        # Add ONLY the highest employee role
        if highest_employee_role:
            role = guild.get_role(highest_employee_role.get("role_id"))
            if role:
                expected_roles.add(role.id)

        # Umbrella flags from ANY matched employee role
        for emp_role in matched_employee_roles:
            if emp_role.get("cdaemployee") == "yes":
                has_cda_employee = True
            if emp_role.get("iC") == "yes":
                has_ic_role = True

        # Other categories (additive)
        for category in ["DonatorRoles", "Misc", "SpecialUnits"]:
            for role_data in roles_data.get(category, []):
                if role_data.get("group_id") in group_ids:
                    role = guild.get_role(role_data.get("role_id"))
                    if role:
                        expected_roles.add(role.id)

        # Add/remove umbrella roles
        if has_cda_employee:
            expected_roles.add(cda_employee_role_id)
        else:
            valid_role_ids.add(cda_employee_role_id)

        if has_ic_role:
            expected_roles.add(ic_member_role_id)
        else:
            valid_role_ids.add(ic_member_role_id)

        # Compute diffs
        roles_to_add = expected_roles - current_roles
        roles_to_remove = (current_roles - expected_roles) & valid_role_ids
        roles_to_remove -= roles_to_add  # avoid race if role is both in add/remove due to timing

        # Motto guard for CDA removal
        # Get Habbo name from server_data
        habbo_name = None
        for entry in self.server_data.get("verified_users", []):
            if int(entry.get("user_id", 0)) == member.id:
                habbo_name = entry.get("habbo")
                break

        motto = ""
        if habbo_name:
            try:
                async with aiohttp.ClientSession() as session:
                    user_url = f"https://www.habbo.com/api/public/users?name={habbo_name}"
                    async with session.get(user_url) as response:
                        if response.status == 200:
                            user_json = await response.json()
                            motto = user_json.get("motto", "")
            except Exception:
                motto = ""

        if cda_employee_role_id in roles_to_remove and "cda" in motto.lower():
            roles_to_remove.remove(cda_employee_role_id)

        # If nothing to do, return early
        if not roles_to_add and not roles_to_remove:
            return None, None

        try:
            # Add needed roles
            for role_id in roles_to_add:
                role = guild.get_role(role_id)
                if role:
                    await member.add_roles(role, reason="AutoRoleUpdater: add")
                    added_roles.append(role.name)

            # Remove unneeded roles
            for role_id in roles_to_remove:
                role = guild.get_role(role_id)
                if role:
                    await member.remove_roles(role, reason="AutoRoleUpdater: remove")
                    removed_roles.append(role.name)

        except discord.Forbidden:
            print(f"Skipping {member.name} - Missing permissions to update roles.")
            return None, None
        except Exception as e:
            print(f"Unexpected error while updating roles for {member.name}: {e}")
            return None, None

        return added_roles, removed_roles

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Runs the moment someone joins the guild."""
        # Are they in server.json ? verified_users?
        entry = next((
            u for u in self.server_data.get("verified_users", [])
            if int(u["user_id"]) == member.id
        ), None)

        if entry is None:
            return  # not a verified user, leave them alone

        # 1) nickname ? Habbo name
        try:
            await member.edit(nick=entry["habbo"])
        except discord.Forbidden:
            pass  # lacking manage-nicknames permission is not fatal

        # 2) remove "Awaiting Verification", add "Verified"
        guild = member.guild
        await member.remove_roles(
            guild.get_role(self.awaiting_verification_role_id),
            reason="User is verified"
        )
        await member.add_roles(
            guild.get_role(self.verified_role_id),
            reason="User is verified"
        )

        # 3) give all other appropriate roles immediately
        async with aiohttp.ClientSession() as session:
            # replicated from update_roles_task ? get Habbo groups
            user_url = f"https://www.habbo.com/api/public/users?name={entry['habbo']}"
            async with session.get(user_url) as r:
                if r.status != 200:
                    return
                habbo_id = (await r.json()).get("uniqueId")

            groups_url = f"https://www.habbo.com/api/public/users/{habbo_id}/groups"
            async with session.get(groups_url) as r:
                if r.status != 200:
                    return
                groups_data = await r.json()

        await self.assign_roles(member, groups_data, guild)

    @update_roles_task.before_loop
    async def before_update_roles_task(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(AutoRoleUpdater(bot))
