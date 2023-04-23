#!/usr/bin/env python
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp as youtube_dl
import discord
import asyncio
import nacl
import ffmpeg
import os
import pickle
import re
import urllib.request
import queue


# Set up the discord client   FIXME: Production Bot shouldn't have all intents
intents = discord.Intents.all()
client = commands.Bot(command_prefix='!', intents=intents)

# Bot Discord ID    NOTE: -Not Sensitive-
idDict = {
    "client": 924079497412767844,
    "frank": 264225001492840448,
}

# Global Variables
pklfile_textChannel = "textChannel"
pklfile_maxQue = "maxQue"
maxQue = 100
textChannel = None
ytLinkQue = queue.Queue()
currentlyPlaying = False
voiceClient = None
mainEmbed = None
isLoop = False
isSkip = False

# Set up youtube_dl options for playing audio
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
    }


@client.event
async def on_ready():
    global maxQue
    global textChannel
    global mainEmbed

    # Retrieve Max Que
    try:
        maxQue = getMaxQue()
        print(f"Max que: {maxQue}")
    except FileNotFoundError as e:
        print("Unable to load Max Que. Default set to 100. New Pickle Dumped.")
        maxQue = 100
        dump(maxQue, pklfile_maxQue)

    try:
        textChannel = getTextChannel()
        print(f"Text Channel: {textChannel}")
    except FileNotFoundError as e:
        print("Unable to load Text Channel. A new text channel must be set.")
    
    print(f'{client.user} is ready.')

    # textChannelObject = discord.uitls.get(textChannel)
    # await textChannelObject.send(embed=mainEmbed)

#  DEBUG COMMANDS ================================================================
@client.command()
async def getinfo(ctx):
    await ctx.send(f"Que size: {ytLinkQue.qsize()}")
    await ctx.send(f"isLoop: {isLoop}")
    await ctx.send(f"isSkip: {isSkip}")

@client.command()
async def enableloop(ctx):
    loopMusic()
    await ctx.send(f"Loop Statis now: {isLoop}")
#  DEBUG COMMANDS ================================================================


# Sets channel ID and pickles it
@client.command()
async def set_channel(ctx):
    global textChannel

    if ctx.message.author.id != idDict["frank"]:
        await ctx.send(f"> Hol up, convince me that you're frank and I'll let you do the command.")

    textChannel = ctx.message.channel
    dump(textChannel, pklfile_textChannel)

    # FIXME: Can remove for production
    print(f"Text Channel set to {getTextChannel()} by {ctx.message.author.display_name}.")


@client.command()
async def set_max_que(ctx, m):
    if ctx.message.channel.id == getTextChannel():
        # Only accept integers
        try:
            m = int(m)
        except ValueError as e:
            print(f"WARNING: Max que attempted to be set to {m} by {ctx.author.display_name}.\nError:\n{e}")
            await ctx.send(f"> Max que must be number `(0 for max)`, not `{m}`.")
            return
        
        # Check for bounds of que limit
        if m == 0:
            m = 100
        elif m < 0:
            print(f"WARNING: Max que attempted to be set to {m} by {ctx.author.display_name}.\nError:\nNegative value.")
            await ctx.send(f"> Max que must be positive, not `{m}`.")
            return
        elif m > 100:
            m = 100

        # Pickle que and respond
        dump(m, pklfile_maxQue)
        print(f"Max Que has been set to {m} by {ctx.message.author.display_name}")
        await ctx.send(f"> Max que has been set to `{m}`.")


# Waits for message to add to que
@client.event
async def on_message(message):
    global textChannel
    global ytLinkQue

    # Converts content to youtube link and adds to queue
    content = message.content

    # Message must not be from bot
    if not message.author.bot:
        # Message must be in designated text channel
        if message.channel.id == textChannel:
            # Message must not be a command
            if not content.startswith("!"):
                # Member must be connected to a voice channel
                try:
                    voiceChannel = message.author.voice.channel
                except AttributeError as e:
                    voiceChannel = None
                    await message.channel.send(f"> {message.author.display_name}, you must be connected to a voice channel to add songs to the que.")

                if voiceChannel is not None:
                    # Adds youtube link to que as [link, author]
                    ytLink = queryToYtLink(content)
                    # await message.channel.send(ytLink)               # NOTE: added for testing

                    ytLinkQue.put([ytLink, message])

                    await message.delete(delay=0.5)

                    if not ytLinkQue.empty() and not isMusicPlaying():
                        await play()

    await client.process_commands(message)


# NOTE: Process of getting from query to que
# Once a query get sent in bot channel (assuming its for music),
# if its the first in the que, the message object is passed to play(),
# otherwise, the que is expanded.
#
# Once there is music in the que for the first time, the play() function
# is called which takes the message to do all the playing stuff.
# 
# When it's done playing, currently playing is false


# Begins playing music | NOTE: play() will only get called when que is not empty and music is not playing
async def play():
    global voiceClient
    global mainEmbed
    global isLoop
    global isSkip

    currentSongLink = None

    print("Play Called")
    musicPlay()

    # Get message object from initial request and deque first song
    firstCall = True
    currentSongLink, message = deque(reque=isLoop)
    channel = message.author.voice.channel
    voiceClient = await channel.connect()
    
    while True:
        # Redundant check
        if not isMusicPlaying():
            break
        
        # deques music in while only after first call
        if not firstCall:
            currentSongLink, message = deque(reque=isLoop)

        firstCall = False

        # if currentSongLink is None:
        #     continue

        # Get current song
        if not voiceClient.is_connected():
            voiceClient = await channel.connect()

        # Get song from Youtube
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(currentSongLink, download=False)
            song = info['url']

            # Send embed message
            if mainEmbed is None:
                mainEmbed = await send_embed(update=False, message=message, ytinfo=info)
            else:
                await send_embed(update=True, message=message, ytinfo=info)

            # Play Song
            voiceClient.play(discord.FFmpegPCMAudio(song, **FFMPEG_OPTIONS), after=lambda e: print(f'Song done'))

            # Wait until the song has finished playing
            while voiceClient.is_playing() or voiceClient.is_paused():
                if isSkip:
                    voiceClient.stop()
                    break
                await asyncio.sleep(1)
            
            isSkip = False

            if ytLinkQue.empty():
                musicStop()
                await voiceClient.disconnect()
                print("Play cycle completed")
                break


# Sets up buttons for embed
class Menu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.value = None

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.blurple)
    async def pauseAndResume(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if voiceClient.is_paused():
            resumeMusic()
        else:
            pauseMusic()

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.blurple)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if isMusicPlaying():
            skipMusic()
        if voiceClient.is_paused():
            resumeMusic()

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.blurple, disabled=False)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        loopMusic()  # FIXME: When queing, message object is passed instead of song and 'channel = message.author.voice.channel' tries to read it
    
    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if voiceClient.is_playing():
            stopMusic()


# Creates / updates embed
async def send_embed(*, update=False, message=None, ytinfo=None):
    global mainEmbed

    # Default embed with no arguments required
    if message == None:
        print("WARNING: Pass message object in generate_embed()")
        return
    
    view = Menu()
    bannerFile=discord.File("img/banner.png", filename="banner.png")
    thumbnailFile=discord.File("img/defaultThumbnail.png")

    defaultEmbed=discord.Embed(title="Wall Music", color=0xd400ff)
    defaultEmbed.set_image(url="attachment://banner.png")
    defaultEmbed.set_footer(text=f"!set_channel -> set music channel | !set_max_que -> set max size of que\nTo que song, type the song in chat")
    defaultEmbed.set_thumbnail(url="attachment://defaultThumbnail.png")
    defaultEmbed.set_thumbnail(url=message.author.display_avatar) # When this is in on_ready(), it goes back to update
    ytVideoTitle = ytinfo["title"]
    ytVideoAuthor = ytinfo["channel"]
    
    defaultEmbed.add_field(name=f"{ytVideoTitle}", value=f"By: {ytVideoAuthor}", inline=False)

    if not update:
        embedMessage = await message.channel.send(embed=defaultEmbed, files=[bannerFile])
        await message.channel.send(view=view)
        return embedMessage
    elif update: # FIXME: Make sure when len(defaultEmbed) >= 6000, shorten que field    
        await mainEmbed.edit(embed=defaultEmbed)


# Returns boolean if music is playing
def isMusicPlaying():
    return currentlyPlaying

# Starts music playing
def musicPlay():
    global currentlyPlaying

    currentlyPlaying = True

# Stops music playing
def musicStop():
    global currentlyPlaying

    currentlyPlaying = False


def pauseMusic():
    print("Pause Called")
    voiceClient.pause()
    return


def resumeMusic():
    print("Resume Called")
    voiceClient.resume()
    return


def stopMusic():
    print("Stop Called")
    musicStop()
    voiceClient.stop()
    return


def loopMusic():
    global isLoop

    print("Loop Called")
    if isLoop:
        isLoop = False
    else:
        isLoop = True
    return


def skipMusic():
    global isSkip

    print("Skip Called")
    isSkip = True
    return


def deque(reque=False):
    global ytLinkQue

    print("Deque Called")

    s = ytLinkQue.get()
    if reque:
        ytLinkQue.put(s)
    return s


# Pickle Dump
def dump(obj, file):
    ofile = open(file, "wb")
    pickle.dump(obj, ofile)
    ofile.close()


# Pickle Read
def load(file):
    ifile = open(file, "rb")
    try:
        o = pickle.load(ifile)
    except pickle.UnpicklingError as e:
        print(f"Unable to unpickle file {file} due to corruption or security violation.")
    ifile.close()
    return o


# Returns set text channel for bot
def getTextChannel():
    return load(pklfile_textChannel)


def getMaxQue():
    return load(pklfile_maxQue)


# Converts query to youtube link   NOTE: could add functionality to optimize
def queryToYtLink(query):
    html = urllib.request.urlopen("https://www.youtube.com/results?search_query=" + query.replace(" ", ""))
    video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
    return "https://www.youtube.com/watch?v=" + video_ids[0]


# Load .env File
load_dotenv()

# Run the bot
TOKEN = os.getenv("TOKEN")
client.run(TOKEN)