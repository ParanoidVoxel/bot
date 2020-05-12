import asyncio
import aiohttp
import base64
import copy
import datetime
import discord
import logging
import motor
from youtube_dl import YoutubeDL
import requests
import time

from modules.voice import Voice

import utils.config

logging.basicConfig(level=logging.INFO)

db_client = motor.motor_tornado.MotorClient(utils.config.MONGO)

voice_state = {}

clips_db = db_client.clips

discord_client = discord.Client()


async def url_to_b64(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            print(resp.status)
            return await resp.read()


async def add_uploader(member):
    avatar_bytes = await url_to_b64(member.avatar_url)
    avatar_b64 = base64.b64encode(avatar_bytes)
    uploader = {
        "name": member.name,
        "snowflake": str(member.id),
        "avatar_url": member.avatar_url,
        "created_at": member.created_at,
        "avatar_blob": avatar_b64,
        "clips": []
    }
    oid = await clips_db.uploaders.insert_one(uploader)
    return oid


async def add_uploader_clip(uploader_id, clip_id):
    clips_db.uploaders.update_one({"_id": uploader_id}, {"$push": {"clips": clip_id}})


async def get_uploader(member):
    uploader = await clips_db.uploaders.find_one({"snowflake": str(member.id)})
    if(uploader is None):
        uploader_id = await add_uploader(member)
    else:
        uploader_id = uploader["_id"]
    return uploader_id


async def connect_voice(guild_id, voice_channel):
    if not(guild_id in voice_state):
        voice_state[guild_id] = {
            "voice_instance": False,
            "voice_client": False,
            "channel": False
            }
    if not(voice_state[guild_id]["voice_instance"]):
        voice_state[guild_id]["voice_instance"] = await Voice.create(
            guild_id,
            voice_channel,
            discord_client)
        voice_state[guild_id]["voice_client"] = await voice_state[
                guild_id]["voice_instance"].connect()
        voice_state[guild_id]["channel"] = voice_channel.id
    if not(voice_state[guild_id]["channel"] == voice_channel.id):
        await voice_state[guild_id]["voice_instance"].move_to(voice_channel)
    return voice_state[guild_id]["voice_instance"]


async def addfile(message):
    if(len(message.content[1:].split()) == 2):
        uploader_id = get_uploader(message.author)
        name = message.content[1:].split()[1]
        guild = message.guild.id
        if(len(message.attachments) == 1):
            exists = await clips_db[str(guild)].find_one({"name": {"$eq": name}})
            if(exists is not None):  # ERR: If command with name already exists
                await message.channel.send(
                    f"{utils.config.ERROR_PREFIX}A command with the name `{name}` already exists.")
            elif(message.attachments[0].url.split(".")[-1] == "mp3"):
                document = {
                    "url": message.attachments[0].url,
                    "name": name,
                    "stats": {
                        "count": 0,
                    },
                    "added_by": str(uploader_id),
                    "time_added": time.time(),
                    "settings": {
                        "volume": "1",
                        "last_changed_by": str(uploader_id),
                    }
                }
                new = await clips_db[str(guild)].insert_one(document)
                with open(f"{utils.config.SOUND_PATH}/{new.inserted_id}.mp3", "wb+") as f:
                    f.write(requests.get(document["url"]).content)
                await message.channel.send(f"File added with name `{name}`.")
            else:
                # ERR: If not mp3 file
                await message.channel.send(
                    f"{utils.config.ERROR_PREFIX}Only attachments of type `mp3` is permitted.")
        elif(len(message.attachments) > 1):
            # ERR: If too many attachments
            await message.channel.send(
                f"{utils.config.ERROR_PREFIX}Only one attachment per `addfile` command is permitted.")
        else:
            # ERR: If no attachments
            await message.channel.send(
                f"{utils.config.ERROR_PREFIX}Please attach a file to add a command.")
    else:
        # ERR: If not two args
        await message.channel.send(
            f"{utils.config.ERROR_PREFIX}Please specify a name for the clip. `{utils.config.COMMAND_PREFIX}addfile <name>`.")


async def play_sound(metadata, channel, mode="instant", extra_params=None):
    voice_client = await connect_voice(str(channel.guild.id), channel)
    if(mode == "queue"):
        await voice_client.queue(metadata, "sound", extra_params=extra_params)
    else:
        await voice_client.play_now(metadata, extra_params=extra_params)


async def get_params(string):
    if("[" in string and "]" in string):
        try:
            return string.replace(" ", "")[
                string.index("[")+1:
                string.index("]")
                ].strip(")]").split("),")
        except Exception:
            raise
    return None


async def get_sound(message):
    params = await get_params(message.content)
    if(params is None):
        command_name = message.content[1:]
    else:
        command_name = message.content[1:message.content.index("[")]
    sound_metadata = await clips_db[str(message.guild.id)].find_one(
        {"name": {"$eq": command_name}})

    if(sound_metadata is None or message.author.voice.channel is None):
        return
    else:
        if(params is not None):
            await play_sound(sound_metadata,
                             message.author.voice.channel,
                             extra_params=params)
        else:
            await play_sound(sound_metadata, message.author.voice.channel)
        await clips_db[str(message.guild.id)].update_one(
                {"_id": sound_metadata["_id"]},
                {"$inc": {'stats.count': 1}})


async def is_valid_volume(string):
    try:
        float(string)
        return True
    except ValueError:
        return False


async def setvolume(message):
    args = message.content[1:].split()
    if(len(args) == 3):
        metadata = await clips_db[str(message.guild.id)].find_one(
            {"name": {"$eq": args[1]}})
        valid = await is_valid_volume(args[2])
        if(metadata is None):
            # ERR: The command doesn't exist
            await message.channel.send(
                f"{utils.config.ERROR_PREFIX}The clip `{args[1]}` doesn't exist")
        elif not(valid):
            await message.channel.send(
                f"{utils.config.ERROR_PREFIX}`{args[2]}` is not a number.")
        else:
            uploder_id = await get_uploader(message.author)
            await clips_db[str(message.guild.id)].update_one(
                {"_id": metadata["_id"]},
                {
                    "$set": {
                        'settings': {
                            "last_changed_by": uploder_id,
                            "volume": args[2]
                            }
                    }
                })
            await message.channel.send(f"Volume of {args[1]} is now `{args[2]}`")
    else:
        # ERR: There aren't enough/too many args
        await message.channel.send(
            f"{utils.config.ERROR_PREFIX}Please provide two arguments. `{utils.config.COMMAND_PREFIX}addfile <clip name> <volume>`.")


async def get_random(guild_id, count=1):
    for doc in clips_db[str(guild_id)].aggregate([{"$sample": {"size": 1}}]):
        return doc


async def play_random(message):
    params = await get_params(message.content)
    if(message.author.voice.channel is None):
        return
    random_selection = await get_random(message.guild.id)
    await play_sound(random_selection,
                     message.author.voice.channel,
                     extra_params=params)


async def _list(message):
    await message.channel.send(f"Command list: https://bot.thvxl.pw/ui/guild/{str(message.guild.id)}")


async def youtube(message):
    ydl_opts = {
        "extractaudio": True,
        "audioquality": 9,
        "audioformat": "bestaudio/best"
        }
    args = message.content.split()
    if(args[1].startswith("http")):
        video = args[1]
    else:
        video = "ytsearch:" + " ".join(args[1:])
    with YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(video, download=False)
        if(video == args[1]):
            url = info_dict['formats'][0]['url']
            thumbnail = info_dict['thumbnail']
            title = info_dict['title']
        else:
            url = info_dict['entries'][0]['formats'][0]['url']
            thumbnail = info_dict['entries'][0]['thumbnail']
            title = info_dict['entries'][0]['title']
        voice_client = await connect_voice(str(message.guild.id),
                                           message.author.voice.channel)
        await voice_client.queue(url, "yt")
        embed = discord.Embed(title="YouTube",
                              colour=discord.Colour(0xa22b8c),
                              description=f"Currently playing in channel `#{message.channel.name}`",
                              timestamp=datetime.datetime.utcfromtimestamp(time.time()))
        embed.set_image(url=thumbnail)
        embed.set_thumbnail(url=discord_client.user.avatar_url)
        embed.set_author(name="RadonBot",
                         url="https://discordapp.com",
                         icon_url=discord_client.user.avatar_url)
        embed.set_footer(text="RadonBot",
                         icon_url=discord_client.user.avatar_url)
        embed.add_field(name="Title", value=title)
        await message.channel.send(content="Now Playing", embed=embed)


async def parse_command_queue(message):
    commands = message.content.split(utils.config.SOUND_PREFIX)[2:]
    for command in commands:
        if(not command[-2:] == "[]"):
            # If parameters aren't blank, resent and don't copy from previous
            params = await get_params(command)
        if(params is not None):
            command = command[:command.index("[")]
        if(command == "r"):
            sound_metadata = await get_random(message.guild.id)
        else:
            sound_metadata = await clips_db[str(message.guild.id)].find_one({"name": {"$eq": command}})
        if(sound_metadata is None or message.author.voice.channel is None):
            pass
        else:
            await play_sound(sound_metadata, message.author.voice.channel, "queue", extra_params=params)
            await clips_db[str(message.guild.id)].update_one(
                {"_id": sound_metadata["_id"]}, {"$inc": {'stats.count': 1}})


async def skip(message):
    voice_client = await connect_voice(
        str(message.guild.id),
        message.author.voice.channel)
    await voice_client.skip()


commands = {
    "addfile": addfile,
    "setvolume": setvolume,
    "list": _list,
    "yt": youtube,
    "skip": skip,
}


async def should_parse_message():
    try:
        if(discord_client.user.voice.mute):
            return False
        else:
            return True
    except(Exception):
        return True


async def parse_message(message):
    if(await should_parse_message()):
        if(message.author == discord_client.user):
            return
        elif(message.content == f"{utils.config.SOUND_PREFIX}r"):
            await play_random(message)
        elif(message.content.startswith(utils.config.SOUND_PREFIX*2)):
            await parse_command_queue(message)
        elif(message.content.startswith(utils.config.SOUND_PREFIX)):
            await get_sound(message)
        elif(message.content.startswith(utils.config.COMMAND_PREFIX)):
            if(message.content[1:].split()[0] in commands):
                await commands[message.content[1:].split()[0]](message)

@discord_client.event
async def on_ready():
    print(f"Bot started as user: {discord_client.user}")


@discord_client.event
async def on_message(message):
    await parse_message(message)


@discord_client.event
async def on_message_edit(before, after):
    await parse_message(after)


discord_client.run(utils.config.API_KEY)
