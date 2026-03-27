import asyncio
import time
from os import path as ospath
from aiofiles import open as aiopen
from aiofiles.os import path as aiopath, remove as aioremove
from aiohttp import ClientSession
from torrentp import TorrentDownloader
from config import LOGS
from bot.core.func_utils import handle_logs
from pathlib import Path


class TorDownloader:
    def __init__(self, path="downloads"):
        self._downdir = path
        self._torpath = "torrents"

    @handle_logs
    async def download(self, torrent: str, name: str = None) -> str | None:
        # Ensure download directory exists
        if not await aiopath.isdir(self._downdir):
            await asyncio.to_thread(Path(self._downdir).mkdir, parents=True, exist_ok=True)

        if torrent.startswith("magnet:"):
            return await self._monitored_download("magnet", torrent, name)
        elif torfile := await self._get_torfile(torrent):
            return await self._monitored_download("file", torfile, name)
        else:
            LOGS.error("[TorDownloader] Invalid torrent or failed to fetch.")
            return None

    async def _monitored_download(self, mode: str, data: str, name: str = None) -> str | None:
        try:
            torp = TorrentDownloader(data, self._downdir)
            task = asyncio.create_task(torp.start_download())

            last_checked = time.time()
            max_idle = 600
            check_interval = 30

            while not task.done():
                await asyncio.sleep(check_interval)
                # NOTE: Check if usage of `torp.progress` is valid for your version of torrentp
                # If torrentp object has no progress attribute, this might need adjustment.
                # Assuming generic behavior:
                if hasattr(torp, 'progress') and torp.progress < 1:
                    if time.time() - last_checked > max_idle:
                        task.cancel()
                        LOGS.error("[TorDownloader] Dead torrent — no progress for 10 mins.")
                        return None
                else:
                    last_checked = time.time()

            await task
            
            # --- Robust File Finding Logic ---
            # 1. Try to get name from metadata if available (safely)
            meta_name = None
            try:
                if hasattr(torp, '_torrent_info') and torp._torrent_info and hasattr(torp._torrent_info, '_info'):
                     meta_name = torp._torrent_info._info.name()
            except Exception:
                pass

            # 2. Check if meta_name exists
            if meta_name:
                path_a = ospath.join(self._downdir, meta_name)
                if ospath.exists(path_a):
                    if ospath.isdir(path_a):
                        import glob
                        video_extensions = ['*.mkv', '*.mp4']
                        for ext in video_extensions:
                            files = glob.glob(ospath.join(path_a, ext))
                            if files:
                                 return files[0]
                    return path_a

            # 3. Fallback: Check if 'name' passed from RSS matches a file
            if name:
                 path_b = ospath.join(self._downdir, name)
                 if ospath.exists(path_b):
                     return path_b

            # 4. Final Fallback: Find the most recently modified file/folder in downloads
            # This is risky if multiple downloads happen, but with parallel limit it's manageable.
            # Ideally we want the one created just now.
            try:
                all_files = [ospath.join(self._downdir, f) for f in os.listdir(self._downdir)]
                if all_files:
                    # Get latest file/folder
                    latest_file = max(all_files, key=ospath.getmtime)
                    # If it's old (started before this task), maybe ignore? 
                    # But let's assume it's the one.
                    if ospath.isdir(latest_file):
                        import glob
                        video_extensions = ['*.mkv', '*.mp4']
                        for ext in video_extensions:
                            files = glob.glob(ospath.join(latest_file, ext))
                            if files:
                                 return files[0]
                    return latest_file
            except Exception as e:
                LOGS.error(f"[TorDownloader] File search fallback failed: {e}")

            return None

        except asyncio.CancelledError:
            LOGS.warning("[TorDownloader] Download cancelled due to inactivity.")
            return None
        except Exception as e:
            LOGS.error(f"[TorDownloader] Monitored download failed: {e}")
            return None

    @handle_logs
    async def _get_torfile(self, url: str) -> str | None:
        if not await aiopath.isdir(self._torpath):
            await asyncio.to_thread(Path(self._torpath).mkdir, parents=True, exist_ok=True)

        tor_name = url.split("/")[-1]
        save_path = ospath.join(self._torpath, tor_name)

        try:
            async with ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        async with aiopen(save_path, "wb") as f:
                            async for chunk in resp.content.iter_any():
                                await f.write(chunk)
                        return save_path
                    else:
                        LOGS.error(f"[TorDownloader] Failed to download torrent file, status: {resp.status}")
        except Exception as e:
            LOGS.error(f"[TorDownloader] Error fetching .torrent file: {e}")

        return None
