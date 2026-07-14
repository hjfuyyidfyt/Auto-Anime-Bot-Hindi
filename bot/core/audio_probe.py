import asyncio
import json
import logging
from config import LOGS

async def has_hindi_audio(file_path: str) -> bool:
    """
    Probe the downloaded video file using ffprobe to check if it contains a Hindi audio track.
    Checks the language tags and track titles of all audio streams.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index:stream_tags=language,title",
        "-of", "json",
        file_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            LOGS.error(f"ffprobe failed for {file_path} with exit code {proc.returncode}. Stderr: {stderr.decode().strip()}")
            # If ffprobe fails, we fallback to True to avoid deleting valid files in case of system tool issues
            return True
            
        data = json.loads(stdout.decode())
        streams = data.get("streams", [])
        
        if not streams:
            LOGS.warning(f"No audio streams found in file: {file_path}")
            return False
            
        for stream in streams:
            tags = stream.get("tags", {})
            lang = tags.get("language", "").lower()
            title = tags.get("title", "").lower()
            
            if "hin" in lang or "hindi" in lang or "hin" in title or "hindi" in title:
                LOGS.info(f"Detected Hindi audio stream at index {stream.get('index')} in {file_path} (lang={lang}, title={title})")
                return True
                
        LOGS.warning(f"No Hindi audio stream detected in: {file_path}. Streams: {streams}")
        return False
        
    except Exception as e:
        LOGS.error(f"Error probing audio for {file_path}: {e}")
        return True
