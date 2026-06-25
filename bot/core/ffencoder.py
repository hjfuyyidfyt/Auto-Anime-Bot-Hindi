from re import findall 
from math import floor
from time import time
from os import path as ospath, makedirs
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, rename as aiorename
from shlex import split as ssplit
from asyncio import sleep as asleep, gather, create_subprocess_shell, create_task
from asyncio.subprocess import PIPE, DEVNULL

from bot.core.bot_instance import bot_loop, ffpids_cache
from .func_utils import mediainfo, convertBytes, convertTime, sendMessage, editMessage
from .reporter import rep
from config import Var, LOGS

ffargs = {
    'HDRip': Var.FFCODE_HDRip,
    '1080': Var.FFCODE_1080,
    '720': Var.FFCODE_720,
    '480': Var.FFCODE_480,
    '360': Var.FFCODE_360,
}

class FFEncoder:
    def __init__(self, message, path, name, qual):
        self.__proc = None
        self.is_cancelled = False
        self.message = message
        self.__name = name
        self.__qual = qual
        self.dl_path = path
        self.__total_time = None
        self.out_path = ospath.join("encode", name)
        self.__prog_file = 'prog.txt'
        self.__start_time = time()

    async def progress(self):
        self.__total_time = await mediainfo(self.dl_path, get_duration=True)
        if isinstance(self.__total_time, str):
            self.__total_time = 1.0
        while not (self.__proc is None or self.is_cancelled):
            if self.__proc.returncode is not None:
                break
            async with aiopen(self.__prog_file, 'r+') as p:
                text = await p.read()
            if text:
                time_done = floor(int(t[-1]) / 1000000) if (t := findall("out_time_ms=(\d+)", text)) else 1
                ensize = int(s[-1]) if (s := findall(r"total_size=(\d+)", text)) else 0
                
                diff = time() - self.__start_time
                speed = ensize / diff
                percent = round((time_done/self.__total_time)*100, 2)
                tsize = ensize / (max(percent, 0.01)/100)
                eta = (tsize-ensize)/max(speed, 0.01)
    
                bar = floor(percent/8)*"█" + (12 - floor(percent/8))*"▒"
                
                progress_str = f"""‣ <b>Aɴɪᴍᴇ Nᴀᴍᴇ :</b>\n<blockquote><b><i>{self.__name}</i></b></blockquote>
<blockquote>‣ <b>Sᴛᴀᴛᴜs :</b> <i>Encoding</i>
    <code>[{bar}]</code> {percent}%</blockquote> 
<blockquote>   ‣ <b>Size :</b> {convertBytes(ensize)} out of ~ {convertBytes(tsize)}
    ‣ <b>Sᴘᴇᴇᴅ :</b> {convertBytes(speed)}/s
    ‣ <b>Tɪᴍᴇ Tᴏᴏᴋ :</b> {convertTime(diff)}
    ‣ <b>Tɪᴍᴇ Lᴇғᴛ :</b> {convertTime(eta)}</blockquote>
<blockquote>‣ <b>Fɪʟᴇ(s) Eɴᴄᴏᴅᴇᴅ:</b> <code>{Var.QUALS.index(self.__qual)} / {len(Var.QUALS)}</code></blockquote>"""
            
                await editMessage(self.message, progress_str)
                if (prog := findall(r"progress=(\w+)", text)) and prog[-1] == 'end':
                    break
            await asleep(8)
    
    async def start_encode(self):
        makedirs("encode", exist_ok=True)
        if ospath.exists(self.__prog_file):
            await aioremove(self.__prog_file)
    
        async with aiopen(self.__prog_file, 'w+'):
            LOGS.info("Progress Temp Generated !")
            pass
        
        dl_npath, out_npath = ospath.join("encode", "ffanimeadvin.mkv"), ospath.join("encode", "ffanimeadvout.mkv")
        await aiorename(self.dl_path, dl_npath)
        
        err_file = ospath.join("encode", "ffmpeg_err.txt")
        if ospath.exists(err_file):
            try:
                await aioremove(err_file)
            except:
                pass
        
        raw_code = ffargs[self.__qual].format(dl_npath, self.__prog_file, out_npath)
        
        # Determine mapping options dynamically to prevent FFmpeg failures on missing tracks
        audio_map = await get_audio_mapping_arg(dl_npath)
        sub_map = await get_subtitle_mapping_arg(dl_npath)
        
        if "-map 0:a:m:language:hin" in raw_code:
            raw_code = raw_code.replace("-map 0:a:m:language:hin", audio_map)
        if "-map 0:s:m:language:eng" in raw_code:
            raw_code = raw_code.replace("-map 0:s:m:language:eng", sub_map)
            
        ffcode = raw_code + f" 2> '{err_file}'"
        
        LOGS.info(f'FFCode: {ffcode}')
        self.__proc = await create_subprocess_shell(ffcode, stdout=DEVNULL)
        proc_pid = self.__proc.pid
        ffpids_cache.append(proc_pid)
        _, return_code = await gather(create_task(self.progress()), self.__proc.wait())
        ffpids_cache.remove(proc_pid)
        
        await aiorename(dl_npath, self.dl_path)
        
        if self.is_cancelled:
            return
        
        if return_code == 0:
            if ospath.exists(out_npath):
                await aiorename(out_npath, self.out_path)
            return self.out_path
        else:
            err_text = ""
            if ospath.exists(err_file):
                try:
                    async with aiopen(err_file, 'r') as ef:
                        err_text = await ef.read()
                except Exception as e:
                    err_text = f"Could not read error file: {e}"
            await rep.report(err_text, "error")
            raise Exception(f"FFmpeg failed: {err_text}")
            
    async def cancel_encode(self):
        self.is_cancelled = True
        if self.__proc is not None:
            try:
                self.__proc.kill()
            except:
                pass


async def get_audio_mapping_arg(file_path):
    info = await mediainfo(file_path, get_json=True)
    if not info or 'media' not in info or 'track' not in info['media']:
        return "-map 0:a:0"
    
    tracks = info['media']['track']
    if not isinstance(tracks, list):
        tracks = [tracks]
        
    audio_tracks = [t for t in tracks if t.get('@type') == 'Audio']
    if not audio_tracks:
        return "-map 0:a:0"
    
    # 1. Look for Hindi audio
    for idx, t in enumerate(audio_tracks):
        lang = str(t.get('Language', '')).lower()
        if lang in ('hi', 'hin', 'hindi'):
            return f"-map 0:a:{idx}"
            
    # 2. Look for English audio
    for idx, t in enumerate(audio_tracks):
        lang = str(t.get('Language', '')).lower()
        if lang in ('en', 'eng', 'english'):
            return f"-map 0:a:{idx}"
            
    # 3. Look for Japanese audio
    for idx, t in enumerate(audio_tracks):
        lang = str(t.get('Language', '')).lower()
        if lang in ('ja', 'jpn', 'japanese'):
            return f"-map 0:a:{idx}"
            
    return "-map 0:a:0"


async def get_subtitle_mapping_arg(file_path):
    info = await mediainfo(file_path, get_json=True)
    if not info or 'media' not in info or 'track' not in info['media']:
        return "-map 0:s:0?"
    
    tracks = info['media']['track']
    if not isinstance(tracks, list):
        tracks = [tracks]
        
    sub_tracks = [t for t in tracks if t.get('@type') == 'Subtitle']
    if not sub_tracks:
        return ""
    
    # 1. Look for English subtitles
    for idx, t in enumerate(sub_tracks):
        lang = str(t.get('Language', '')).lower()
        if lang in ('en', 'eng', 'english'):
            return f"-map 0:s:{idx}"
            
    # 2. Look for Hindi subtitles
    for idx, t in enumerate(sub_tracks):
        lang = str(t.get('Language', '')).lower()
        if lang in ('hi', 'hin', 'hindi'):
            return f"-map 0:s:{idx}"
            
    return "-map 0:s:0?"
