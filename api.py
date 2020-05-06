from aiohttp import web

import json
import asyncio
import bson.json_util
import motor
import discord
import utils.config

db_client = motor.motor_tornado.MotorClient(utils.config.MONGO)

discord_client = discord.Client()

@discord_client.event
async def on_ready():
    print(f'Logged on as {discord_client.user}!')

async def get_user(request):
    user_id = request.match_info.get('user_id', 'false')
    user = await discord_client.fetch_user(int(user_id))
    response = web.json_response({
        "username": user.name,
        "avatar_url": str(user.avatar_url)
    })
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

async def handle(request):
    guild_id = request.match_info.get('guild_id', "false")
    response = web.json_response({"commands": json.loads(bson.json_util.dumps(await db_client["clips"][guild_id].find().to_list(length=1000)))})
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

app = web.Application()
app.router.add_get('/guild/{guild_id}', handle)
app.router.add_get("/user/{user_id}", get_user)

bot_task = discord_client.loop.create_task(discord_client.start(utils.config.API_KEY))

web.run_app(app)
