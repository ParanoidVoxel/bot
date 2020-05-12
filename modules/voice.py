import asyncio
import discord

class Voice:
    @classmethod
    async def create(cls, guild, channel, client):
        self = Voice()
        self.guild = guild
        self.channel = channel
        self.queues = {"sound": asyncio.Queue(), "yt": asyncio.Queue()}
        self.client = client
        return self

    async def move_to(self, channel):
        await self.voice_client.move_to(channel)

    async def connect(self):
        self.voice_client = await self.channel.connect()
        return self.voice_client

    async def is_playing(self):
        return self.voice_client.is_playing()

    def _after(self, error):
        coro = self.play_next_sound(error)
        fut = asyncio.run_coroutine_threadsafe(coro, self.client.loop)
        try:
            fut.result()
        except(Exception):
            pass

    async def parse_params(self, filter_list):
        filter_string_list = []
        for f in filter_list:   # Ignore spaces
            f = f.strip(")")
            name = f.split("(")[0]
            if(name in FILTERS):
                params = f.split("(")[1].split(",")
                if(FILTERS[name]["type"] == "boolean"):
                    filter_string_list.append(
                        FILTERS[name]["string"])
                else:
                    if("=" in f):   # There are named parameters
                        param_dict = copy.deepcopy(
                            FILTERS[name]["default_values"])
                        for p in params:
                            if("=" in p):
                                # Multiple parameters for filter specified?
                                if(p.split("=")[0] in param_dict):
                                    # Valid Param?
                                    param_dict[
                                        p.split("=")[0]
                                        ] = p.split("=")[1].strip(")")
                        filter_string_list.append(
                            FILTERS[name]["string"].format(
                                **param_dict
                                ))
                    elif(len(params) > 0):
                        params[0] = params[0].strip(")")
                        filter_string_list.append(
                            FILTERS[name]["string"].format(
                                params[0]
                                ))
        string = ",".join(filter_string_list)
        print("FFMPEG-FILTER-STRING: " + string)
        return string

    async def create_audio_source(self, metadata, _type="audio", params=None):
        if(params is not None):
            param_string = await self.parse_params(params)
        if(_type == "audio"):
            if(params is not None):
                audio_source = discord.FFmpegPCMAudio(
                    f"{utils.config.SOUND_PATH}/{metadata['_id']}.mp3",
                    options=f"-filter_complex '{param_string}'")
            else:
                audio_source = discord.FFmpegPCMAudio(
                    f"{utils.config.SOUND_PATH}/{metadata['_id']}.mp3",
                    options=f"-filter:a 'volume={str(metadata['settings']['volume'])}'")
        else:
            audio_source = discord.FFmpegPCMAudio(metadata)
        return audio_source

    async def play_next_video(self, error):
        if not(self.queues["yt"].empty()):
            audio = await self.queues["yt"].get()
            audio_source = await self.create_audio_source(
                audio["metadata"], _type="video")
            self.voice_client.play(audio_source, after=self._after)

    async def play_next_sound(self, error):
        if not(self.queues["sound"].empty()):
            audio = await self.queues["sound"].get()
            audio_source = await self.create_audio_source(
                audio["metadata"], params=audio["params"])
            self.voice_client.play(audio_source, after=self._after)

    async def play_now(self, metadata, extra_params=None):
        self.queues["sound"] = asyncio.Queue()
        self.queues["yt"] = asyncio.Queue()
        audio_source = await self.create_audio_source(
            metadata, params=extra_params)
        if(await self.is_playing()):
            self.voice_client.stop()
        self.voice_client.play(audio_source)

    async def queue(self, metadata, _type, extra_params=None):
        await self.queues[_type].put(
            {"metadata": metadata, "params": extra_params})
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