import discord
from discord.ext import commands
import youtube_dl
import asyncio
import nacl
import ffmpeg
import os


# Set up the discord client   FIXME: Production Bot shouldn't have all intents
intents = discord.Intents.all()
intents.members = True
client = commands.Bot(command_prefix='!', intents=intents)

# Bot Discord ID -Not Sensitive-
botId = "924079497412767844"

# Set up youtube_dl options for playing audio
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.command()
async def play(ctx, *, song: str):
    print("Command called")
    # Get the voice channel that the user requesting the song is in
    channel = ctx.author.voice.channel
    if channel is not None:
        # Join the voice channel
        mId = []
        for m in channel.members:
            mId.append(m.id)

        # if not client.is_connected():
        vc = await channel.connect() # FIXME: Shid aint workin

        # Download the song using youtube_dl
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(song, download=False)
            url = info['formats'][0]['url']

        # Play the song
        vc.play(discord.FFmpegPCMAudio(url), after=lambda e: print('done', e))
        vc.source = discord.PCMVolumeTransformer(vc.source)
        vc.source.volume = 0.07

        # Wait until the song has finished playing
        while vc.is_playing():
            await asyncio.sleep(1)

        # Disconnect from the voice channel
        await vc.disconnect()
    else:
        await ctx.send("You are not in a voice channel.")

# Run the bot
TOKEN = os.getenv("TOKEN")
client.run(TOKEN)