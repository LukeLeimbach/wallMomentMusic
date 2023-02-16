from discord.ext import commands
from dotenv import load_dotenv
import discord, asyncio, nacl, ffmpeg, os, pickle, threading, youtube_dl, queue, re, urllib.request
import youtube_dl, queue


# Set up the discord client   FIXME: Production Bot shouldn't have all intents
intents = discord.Intents.all()
intents.members = True
client = commands.Bot(command_prefix='!', intents=intents)

# Bot Discord ID    NOTE: -Not Sensitive-
botId = 924079497412767844

# Global Variables
pklfile_textChannel = "textChannel"
pklfile_maxQue = "maxQue"
maxQue = 100
textChannel = 0
ytLinkQue = queue.Queue()
mainEmbed = discord.Embed()
currentlyPlaying = False


# Set up youtube_dl options for playing audio
ydl_opts = {
    'format': 'bestaudio/best',
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 1',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}


@client.event
async def on_ready():
    global maxQue
    global textChannel

    # Retrieve Max Que
    try:
        maxQue = load(pklfile_maxQue)
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

    # Check every second for new music que
    while True:
        # If que is not empty and there is no music playing, play music
        if not ytLinkQue.empty() and not isMusicPlaying():
            await play()

        await asyncio.sleep(1)


# Sets channel ID and pickles it
@client.command()
async def set_channel(ctx):
    global textChannel

    textChannel = ctx.message.channel.id
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
            await ctx.send(f"> Max que must be number `(0 for infinite)`, not `{m}`.")
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
    global mainEmbed

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
                    # Passes this to play() if the que is empty and no music is playing
                    if ytLinkQue.empty() and not isMusicPlaying():
                        ytLinkQue.put(message)
                    
                    # Adds youtube link to que as [link, author]
                    ytLink = queryToYtLink(content)
                    await message.channel.send(ytLink)               # NOTE: added for testing

                    ytLinkQue.put([ytLink, message.author])

    await client.process_commands(message)

# --------------------------------------------------------------------------------------------------------------------------------------------
@client.command()
async def _play(ctx, *, song: str):
    # Get the voice channel that the user requesting the song is in
    channel = ctx.author.voice.channel
    if channel is not None:
        # if not client.is_connected():
        vc = await channel.connect() # FIXME: Shid aint workin

        # Download the song using youtube_dl
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(song, download=False)
            url = info['formats'][0]['url']

        # Play the song
        vc.source = discord.PCMVolumeTransformer(vc.source)
        vc.source.volume = 0.2
        vc.play(discord.FFmpegPCMAudio(url), after=lambda e: print('done', e))

        # Wait until the song has finished playing
        musicPlay()
        while vc.is_playing():
            await asyncio.sleep(1)
        musicStop()

        # Disconnect from the voice channel
        await vc.disconnect()
    else:
        await ctx.send("> You are not in a voice channel.")
# --------------------------------------------------------------------------------------------------------------------------------------------


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
    print("Play Called")
    musicPlay()
    # Get message object from initial request
    message = ytLinkQue.get()
    voiceChannel = message.author.voice.channel
    vc = await voiceChannel.connect()
    
    while not ytLinkQue.empty():
        # FIXME: Update embed here

        # Get current song
        currentSong = ytLinkQue.get()[0]

        # Get song from Youtube
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(currentSong, download=False)
            url = info['formats'][0]['url']

        # Play Song
        vc.play(discord.FFmpegPCMAudio(url), after=lambda e: print('done', e)) # FIXME: Add volume command

        # Wait until the song has finished playing
        while vc.is_playing():
            await asyncio.sleep(1)
    
    await vc.disconnect()
    musicStop()


# Creates embed
def create_main_embed():
    return


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


# FOR PAUSE: https://discordpy.readthedocs.io/en/stable/api.html#discord.Message


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