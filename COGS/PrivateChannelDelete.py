import discord
import json
from discord.ext import commands

from COGS.paths import data_path

SERVER_JSON_PATH = data_path("JSON/server.json")  # Path to the uploaded file

class ChannelCleanupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def load_json(self):
        """Loads the server.json file."""
        with open(SERVER_JSON_PATH, "r", encoding="utf-8") as file:
            return json.load(file)

    def save_json(self, data):
        """Saves changes to the server.json file."""
        with open(SERVER_JSON_PATH, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Triggered when a channel is deleted; removes it from the JSON file."""
        data = self.load_json()
        user_channels = data.get("user_channels", {})

        # Iterate through users and remove the deleted channel from their list
        for user_id, channels in user_channels.items():
            if "text" in channels and channel.id in channels["text"]:
                channels["text"].remove(channel.id)
                if not channels["text"]:  # If empty, remove the text key
                    del channels["text"]

            if "voice" in channels and channel.id in channels["voice"]:
                channels["voice"].remove(channel.id)
                if not channels["voice"]:  # If empty, remove the voice key
                    del channels["voice"]

            # If user has no channels left, remove the entry
            if not channels:
                del user_channels[user_id]
                break  # Stop loop since user ID is removed

        # Save the updated data
        data["user_channels"] = user_channels
        self.save_json(data)

        print(f"Deleted channel {channel.id} removed from JSON.")

async def setup(bot):
    await bot.add_cog(ChannelCleanupCog(bot))
