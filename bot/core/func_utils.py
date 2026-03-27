from multiprocessing import cpu_count
from concurrent.futures import ThreadPoolExecutor
from functools import partial, wraps
from json import loads as jloads
from re import findall
from math import floor
from os import path as ospath
from time import time, sleep
from traceback import format_exc
from asyncio import sleep as asleep, create_subprocess_shell, wait_for, TimeoutError
from asyncio.subprocess import PIPE
from base64 import urlsafe_b64encode, urlsafe_b64decode

from aiohttp import ClientSession
from aiofiles import open as aiopen
from aioshutil import rmtree as aiormtree
from feedparser import parse as feedparse
from pyrogram.types import InlineKeyboardButton
from pyrogram.errors import MessageNotModified, FloodWait, ReplyMarkupInvalid, MessageIdInvalid

from bot.core.bot_instance import bot, bot_loop
from config import Var, LOGS
from .reporter import rep

def handle_logs(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception:
            await rep.report(format_exc(), "error")
    return wrapper

async def sync_to_async(func, *args, wait=True, **kwargs):
    pfunc = partial(func, *args, **kwargs)
    future = bot_loop.run_in_executor(ThreadPoolExecutor(max_workers=cpu_count() * 10), pfunc)
    return await future if wait else future

def new_task(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return bot_loop.create_task(func(*args, **kwargs))
    return wrapper

async def getfeed(link, index=0, max_retries=3, timeout=10):
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml'
            }
            feed = await wait_for(
                sync_to_async(
                    lambda: feedparse(link, 
                                    agent=headers['User-Agent'],
                                    request_headers=headers)
                ),
                timeout=timeout
            )
            if feed and feed.entries:
                return feed.entries[index]
            LOGS.error(f"No entries found for {link}")
            return None
        except TimeoutError:
            LOGS.error(f"Timeout after {timeout}s for {link}")
            if attempt < max_retries - 1:
                await asleep(retry_delay)
                retry_delay *= 2
                continue
            return None
        except IndexError:
            LOGS.error(f"IndexError for {link}: No entry at index {index}")
            return None
        except Exception as e:
            LOGS.error(f"Attempt {attempt + 1} failed for {link}: {str(e)}")
            if attempt < max_retries - 1:
                await asleep(retry_delay)
                retry_delay *= 2
                continue
            LOGS.error(format_exc())
            return None

@handle_logs
async def aio_urldownload(link):
    async with ClientSession() as sess:
        async with sess.get(link) as data:
            image = await data.read()
    path = f"thumbs/{link.split('/')[-1]}"
    if not path.endswith((".jpg", ".png")):
        path += ".jpg"
    async with aiopen(path, "wb") as f:
        await f.write(image)
    return path

@handle_logs
async def get_telegraph(out):
    from telegraph import Telegraph
    client = Telegraph()
    client.create_account(short_name="Mediainfo")
    uname = Var.BRAND_UNAME.lstrip('@')
    page = client.create_page(
        title="Mediainfo",
        author_name=uname,
        author_url=f"https://t.me/{uname}",
        html_content=f"""<pre>
{out}
</pre>
""",
    )
    return page.get("url")

async def sendMessage(chat, text, buttons=None, get_error=False, **kwargs):
    try:
        if isinstance(chat, int):
            return await bot.send_message(chat_id=chat, text=text, disable_web_page_preview=True,
                                        disable_notification=False, reply_markup=buttons, **kwargs)
        else:
            return await chat.reply(text=text, quote=True, disable_web_page_preview=True, disable_notification=False,
                                  reply_markup=buttons, **kwargs)
    except FloodWait as f:
        await rep.report(f, "warning")
        sleep(f.value * 1.2)
        return await sendMessage(chat, text, buttons, get_error, **kwargs)
    except ReplyMarkupInvalid:
        return await sendMessage(chat, text, None, get_error, **kwargs)
    except Exception as e:
        await rep.report(format_exc(), "error")
        if get_error:
            raise e
        return str(e)

async def editMessage(msg, text, buttons=None, get_error=False, **kwargs):
    try:
        if not msg:
            return None
        kwargs.pop("reply_markup", None)
        return await msg.edit_text(
            text=text,
            disable_web_page_preview=True,
            reply_markup=buttons,
            **kwargs
        )
    except FloodWait as f:
        await rep.report(f, "warning")
        sleep(f.value * 1.2)
        return await editMessage(msg, text, buttons, get_error, **kwargs)
    except (MessageNotModified, MessageIdInvalid):
        pass
    except Exception as e:
        await rep.report(format_exc(), "error")
        if get_error:
            raise e
        return str(e)
def extract_title_from_magnet(magnet_link):
    try:
        qs = parse_qs(urlparse(magnet_link).query)
        return unquote(qs.get("dn", ["Magnet Task"])[0])
    except Exception:
        return "Magnet Task"


async def extract_title_from_torrent(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    info = bencodepy.decode(data)[b'info']
                    return info[b'name'].decode()
    except Exception as e:
        print(f"Failed to parse torrent: {e}")
    return "Torrent Task"
    
async def encode(string):
    return (urlsafe_b64encode(string.encode("ascii")).decode("ascii")).strip("=")

async def decode(b64_str):
    return urlsafe_b64decode((b64_str.strip("=") + "=" * (-len(b64_str.strip("=")) % 4)).encode("ascii")).decode("ascii")

async def mediainfo(file, get_json=False, get_duration=False):
    try:
        outformat = "HTML"
        if get_duration or get_json:
            outformat = "JSON"
        process = await create_subprocess_shell(f"mediainfo '''{file}''' --Output={outformat}", stdout=PIPE, stderr=PIPE)
        stdout, _ = await process.communicate()
        if get_duration:
            try:
                return float(jloads(stdout.decode())['media']['track'][0]['Duration'])
            except Exception:
                return 1440
        return await get_telegraph(stdout.decode())
    except Exception as err:
        await rep.report(format_exc(), "error")
        return ""

async def clean_up():
    try:
        for dirtree in ("downloads", "thumbs", "encode"):
            await aiormtree(dirtree)
    except Exception as e:
        LOGS.error(str(e))

def convertTime(s: int) -> str:
    m, s = divmod(int(s), 60)
    hr, m = divmod(m, 60)
    days, hr = divmod(hr, 24)
    convertedTime = (f"{int(days)}d, " if days else "") + \
          (f"{int(hr)}h, " if hr else "") + \
          (f"{int(m)}m, " if m else "") + \
          (f"{int(s)}s, " if s else "")
    return convertedTime[:-2]

def convertBytes(sz) -> str:
    if not sz: 
        return ""
    sz = int(sz)
    ind = 0
    Units = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T', 5: 'P'}
    while sz > 2**10:
        sz /= 2**10
        ind += 1
    return f"{round(sz, 2)} {Units[ind]}B"
