import asyncio
import datetime
import discord
import logging
import motor
from youtube_dl import YoutubeDL
import requests
import time
import utils.config

logging.basicConfig(level=logging.INFO)

db_client = motor.motor_tornado.MotorClient(utils.config.MONGO)

voice_state = {}

class Voice:
    @classmethod
    async def create(cls, guild, channel, client):
        self = Voice()
        self.guild = guild
        self.channel = channel
        self.queues = {"sound": asyncio.Queue(), "yt": asyncio.Queue()}
        self.limiter = True
        self.limiter_string = "alimiter=level_out=0.4:limit=0.5"
        self.client = client
        return self
        
    async def move_to(self, channel):
        await self.voice_client.move_to(channel)

    async def connect(self):
        self.voice_client = await self.channel.connect()

    async def is_playing(self):
        return self.voice_client.is_playing()

    def _after(self, error):
        coro = self.play_next_sound(error)
        fut = asyncio.run_coroutine_threadsafe(coro, self.client.loop)
        try:
            fut.result()
        except:
            pass

    async def create_audio_source(self, metadata, _type="audio"):
        if(_type == "audio"):
            if(self.limiter):
                audio_source = discord.FFmpegPCMAudio(f"{utils.config.SOUND_PATH}/{metadata['_id']}.mp3", options=f"-filter:a 'volume={str(metadata['settings']['volume'])},{self.limiter_string}'")
            else:
                audio_source = discord.FFmpegPCMAudio(f"{utils.config.SOUND_PATH}/{audio['metadata']['_id']}.mp3", options=f"-filter:a 'volume={str(audio['metadata']['settings']['volume'])}'")
        else:
            audio_source = discord.FFmpegPCMAudio(metadata)
        return audio_source

    async def play_next_video(self, error):
        if not(self.queues["yt"].empty()):
            audio = await self.queues["yt"].get()
            audio_source = await self.create_audio_source(audio["metadata"], _type="video")
            self.voice_client.play(audio_source, after=self._after)

    async def play_next_sound(self, error):
        if not(self.queues["sound"].empty()):
            audio = await self.queues["sound"].get()
            audio_source = await self.create_audio_source(audio["metadata"])
            self.voice_client.play(audio_source, after=self._after)

    async def play_now(self, metadata):
        self.queues["sound"] = asyncio.Queue()
        self.queues["yt"] = asyncio.Queue()
        audio_source = await self.create_audio_source(metadata)
        if(await self.is_playing()):
            self.voice_client.stop()
        self.voice_client.play(audio_source)


    async def queue(self, metadata, _type):
        await self.queues[_type].put({"metadata": metadata})
        if(_type == "sound"):
            if not(await self.is_playing()):
                await self.play_next_sound(None)
        else:
            if not(await self.is_playing()):
                await self.play_next_video(None)

    async def skip(self, _type="yt"):
        if (await self.is_playing()):
            self.voice_client.stop()
            if(_type == "yt"):
                await self.play_next_video(None)
            else:
                await self.play_next_sound(None)

clips_db = db_client.clips

discord_client = discord.Client()

async def connect_voice(guild_id, voice_channel):
    if not(guild_id in voice_state):
        voice_state[guild_id] = {"voice_instance": False, "voice_client": False, "channel": False}

    if not(voice_state[guild_id]["voice_instance"]):
        voice_state[guild_id]["voice_instance"] = await Voice.create(guild_id, voice_channel, discord_client)
        voice_state[guild_id]["voice_client"] = await voice_state[guild_id]["voice_instance"].connect()
        voice_state[guild_id]["channel"] = voice_channel.id

    if not(voice_state[guild_id]["channel"] == voice_channel.id):
        await voice_state[guild_id]["voice_instance"].move_to(voice_channel)
    return voice_state[guild_id]["voice_instance"]

async def addfile(message):
    if(len(message.content[1:].split()) == 2):
        name = message.content[1:].split()[1]
        guild = message.guild.id
        if(len(message.attachments) == 1):
            exists = await clips_db[str(guild)].find_one({"name": {"$eq": name}})
            if(exists is not None): # ERR: If command with name already exists
                await message.channel.send(f"{utils.config.ERROR_PREFIX}A command with the name `{name}` already exists.")
            elif(message.attachments[0].url.split(".")[-1] == "mp3"):
                document = {
                    "url": message.attachments[0].url,
                    "name": name,
                    "stats": {
                        "count": 0,
                    },
                    "added_by": str(message.author.id),
                    "time_added": time.time(),
                    "settings": {
                        "volume": "1",
                        "last_changed_by": str(message.author.id)
                    }
                }
                new = await clips_db[str(guild)].insert_one(document)
                with open(f"{utils.config.SOUND_PATH}/{new.inserted_id}.mp3", "wb+") as f:
                    f.write(requests.get(document["url"]).content)
                await message.channel.send(f"File added with name `{name}`.")
            else: # ERR: If not mp3 file
                await message.channel.send(f"{utils.config.ERROR_PREFIX}Only attachments of type `mp3` is permitted.")
        elif(len(message.attachments) > 1): # ERR: If too many attachments
            await message.channel.send(f"{utils.config.ERROR_PREFIX}Only one attachment per `addfile` command is permitted.")
        else: # ERR: If no attachments
            await message.channel.send(f"{utils.config.ERROR_PREFIX}Please attach a file to add a command.")
    else: # ERR: If not two args
        await message.channel.send(f"{utils.config.ERROR_PREFIX}Please specify a name for the clip. `{utils.config.COMMAND_PREFIX}addfile <name>`.")


async def play_sound(metadata, channel, mode="instant"):
    voice_client = await connect_voice(str(channel.guild.id), channel)
    #audio_source = discord.FFmpegPCMAudio(f"{utils.config.SOUND_PATH}/{metadata['_id']}.mp3", options=f"-filter:a 'volume={str(metadata['settings']['volume'])}'")
    if(mode == "queue"):
        await voice_client.queue(metadata, "sound")
    else:
        await voice_client.play_now(metadata)

async def get_sound(message):
    sound_metadata = await clips_db[str(message.guild.id)].find_one({"name": {"$eq": message.content[1:]}})
    if(sound_metadata is None or message.author.voice.channel is None):
        return
    else:
        await play_sound(sound_metadata, message.author.voice.channel)
        await clips_db[str(message.guild.id)].update_one({"_id": sound_metadata["_id"]}, {"$inc": {'stats.count':1}})

async def is_valid_volume(string):
    try:
        float(string)
        return True
    except ValueError:
        return False

async def setvolume(message):
    args = message.content[1:].split()
    if(len(args) == 3):
        metadata = await clips_db[str(message.guild.id)].find_one({"name": {"$eq": args[1]}})
        valid = await is_valid_volume(args[2])
        if(metadata is None): # ERR: If the command doesn't exist
            await message.channel.send(f"{utils.config.ERROR_PREFIX}The clip `{args[1]}` doesn't exist")
        elif not(valid):
            await message.channel.send(f"{utils.config.ERROR_PREFIX}`{args[2]}` is not a number.")
        else:
            await clips_db[str(message.guild.id)].update_one({"_id": metadata["_id"]}, {"$set": {'settings': {"last_changed_by": str(message.author.id), "volume": args[2]}}})
            await message.channel.send(f"Volume of {args[1]} is now `{args[2]}`")
    else: # ERR: if there aren't enough/too many args
        await message.channel.send(f"{utils.config.ERROR_PREFIX}Please provide two arguments. `{utils.config.COMMAND_PREFIX}addfile <clip name> <volume>`.")

async def play_random(message):
    if(message.author.voice.channel is None):
        return
    async for doc in clips_db[str(message.guild.id)].aggregate([{"$sample": {"size": 1}}]):
        await play_sound(doc, message.author.voice.channel)


async def _list(message):
    await message.channel.send(f"Command list: https://bot.thvxl.pw/ui/guild/{str(message.guild.id)}")

async def youtube(message):
    ydl_opts = {"extractaudio": True, "audioquality": 9, "audioformat": "bestaudio/best"}
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
        voice_client = await connect_voice(str(message.guild.id), message.author.voice.channel)
        await voice_client.queue(url, "yt")

        embed = discord.Embed(title="YouTube", colour=discord.Colour(0xa22b8c), description=f"Currently playing in channel `#{message.channel.name}`", timestamp=datetime.datetime.utcfromtimestamp(time.time()))

        embed.set_image(url=thumbnail)
        embed.set_thumbnail(url=discord_client.user.avatar_url)
        embed.set_author(name="RadonBot", url="https://discordapp.com", icon_url=discord_client.user.avatar_url)
        embed.set_footer(text="RadonBot", icon_url=discord_client.user.avatar_url)
        embed.add_field(name="Title", value=title)
        await message.channel.send(content="Now Playing", embed=embed)
    
async def parse_command_queue(message):
    commands = message.content.split(utils.config.SOUND_PREFIX)[2:]
    for command in commands:
        if(command == "r"):
            async for doc in clips_db[str(message.guild.id)].aggregate([{"$sample": {"size": 1}}]):
                sound_metadata = doc
        else:
            sound_metadata = await clips_db[str(message.guild.id)].find_one({"name": {"$eq": command}})
        if(sound_metadata is None or message.author.voice.channel is None):
            pass
        else:
            await play_sound(sound_metadata, message.author.voice.channel, "queue")
            await clips_db[str(message.guild.id)].update_one({"_id": sound_metadata["_id"]}, {"$inc": {'stats.count':1}})

async def skip(message):
    voice_client = await connect_voice(str(message.guild.id), message.author.voice.channel)
    await voice_client.skip()


commands = {
    "addfile": addfile,
    "setvolume": setvolume,
    "list": _list,
    "yt": youtube,
    "skip": skip,
}

@discord_client.event
async def on_ready():
    print(f"Bot started as user: {discord_client.user}")

@discord_client.event
async def on_message(message):
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

discord_client.run(utils.config.API_KEY)
