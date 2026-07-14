"""
MovieBox Fallback Downloader
Downloads anime episodes from MovieBox when Nyaa.si torrents fail.
Only downloads Hindi-dubbed releases. Skips if no Hindi version found.
"""

import os
import asyncio
import aiohttp
from config import LOGS
from bot.core.reporter import rep


class MovieBoxFallback:
    """Fallback downloader using MovieBox (aoneroom.com) API via moviebox-api library."""

    def __init__(self, download_dir="downloads"):
        self._download_dir = download_dir
        self._client = None

    async def search_hindi(self, anime_name: str) -> dict | None:
        """Search MovieBox for a Hindi version of the anime.
        
        Args:
            anime_name: Clean English anime title (e.g. "Dandadan")
            
        Returns:
            dict with subjectId and title if Hindi version found, else None
        """
        try:
            from moviebox_api.v3.http_client import MovieBoxHttpClient
            from moviebox_api.v3.core import Homepage, Search
            from moviebox_api.v3.constants import SubjectType

            async with MovieBoxHttpClient() as client:
                # Initialize token
                hp = Homepage(client_session=client)
                await hp.get_content()

                # Search for the anime
                search = Search(client_session=client, query=anime_name, subject_type=SubjectType.ALL)
                res = await search.get_content()
                items = res.get("items", [])

                if not items:
                    LOGS.info(f"[MovieBox] No results found for: {anime_name}")
                    return None

                # Find the Hindi version — look for [Hindi] in title
                for item in items:
                    title = item.get("title", "")
                    subject_type = item.get("subjectType", 0)
                    # Support both movies (type=1) and TV series (type=2)
                    if subject_type in [1, 2] and "[hindi]" in title.lower():
                        LOGS.info(f"[MovieBox] Found Hindi version: {title} (id={item.get('subjectId')})")
                        return {
                            "subjectId": item.get("subjectId"),
                            "title": title,
                        }

                LOGS.info(f"[MovieBox] No Hindi version found for: {anime_name}")
                return None

        except Exception as e:
            LOGS.error(f"[MovieBox] Search error: {e}")
            return None

    async def get_episode_url(self, subject_id: str, season: int, episode: int, ani_id: int = None) -> dict | None:
        """Get download URL for a specific episode.
        
        Args:
            subject_id: MovieBox subject ID
            season: Season number (1-based)
            episode: Episode number (1-based)
            ani_id: Optional AniList ID
            
        Returns:
            dict with url, resolution, size, codec if found, else None
        """
        try:
            from moviebox_api.v3.http_client import MovieBoxHttpClient
            from moviebox_api.v3.core import Homepage, DownloadableVideoFilesDetail
            from moviebox_api.v3.constants import CustomResolutionType

            # Custom mapping for Dr. Stone [Hindi]
            target_season = season
            target_episode = episode
            if subject_id == "7286600935022149664":  # Dr. Stone [Hindi]
                if season == 2:
                    target_season = 3
                    target_episode = episode
                elif season == 3:
                    if ani_id == 131518:  # New World Part 1
                        target_season = 3
                        target_episode = episode + 11
                    elif ani_id == 162670:  # New World Part 2
                        target_season = 4
                        target_episode = episode
                elif season == 4:
                    target_season = 4
                    target_episode = episode + 11

            async with MovieBoxHttpClient() as client:
                # Initialize token
                hp = Homepage(client_session=client)
                await hp.get_content()

                # Get downloadable files
                file_list = []
                page = 1
                while True:
                    dl_detail = DownloadableVideoFilesDetail(
                        client_session=client,
                        resolution=CustomResolutionType.BEST,
                        page=page,
                        per_page=20
                    )
                    dl_data = await dl_detail.get_content(subject_id)
                    curr_list = dl_data.get("list", [])
                    if not curr_list:
                        break
                    file_list.extend(curr_list)
                    if len(curr_list) < 20:
                        break
                    page += 1

                if not file_list:
                    LOGS.info(f"[MovieBox] No downloadable files for subject {subject_id}")
                    return None

                # Find the matching episode
                for f in file_list:
                    f_season = int(f.get("se", 0))
                    f_episode = int(f.get("ep", 0))
                    if f_season == target_season and f_episode == target_episode:
                        url = f.get("resourceLink", "")
                        if url:
                            return {
                                "url": url,
                                "resolution": int(f.get("resolution", 0)),
                                "size": int(f.get("size", 0)),
                                "codec": f.get("codecName", "unknown"),
                            }

                LOGS.info(f"[MovieBox] Episode S{season}E{episode} (mapped to S{target_season}E{target_episode}) not found in subject {subject_id}")
                return None

        except Exception as e:
            LOGS.error(f"[MovieBox] Get episode URL error: {e}")
            return None

    async def download_file(self, url: str, filename: str) -> str | None:
        """Download a file from MovieBox CDN via async HTTP.
        
        Args:
            url: Direct MP4 download URL
            filename: Desired output filename
            
        Returns:
            Full path to downloaded file, or None on failure
        """
        try:
            os.makedirs(self._download_dir, exist_ok=True)
            filepath = os.path.join(self._download_dir, filename)

            timeout = aiohttp.ClientTimeout(total=600)  # 10 min max
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        LOGS.error(f"[MovieBox] Download failed with status {resp.status}")
                        return None

                    total_size = int(resp.headers.get("content-length", 0))
                    downloaded = 0

                    with open(filepath, "wb") as f:
                        async for chunk in resp.content.iter_chunked(1024 * 1024):  # 1MB chunks
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                if downloaded % (10 * 1024 * 1024) < (1024 * 1024):  # Log every ~10MB
                                    LOGS.info(f"[MovieBox] Download progress: {progress:.1f}% ({downloaded / (1024*1024):.0f}MB / {total_size / (1024*1024):.0f}MB)")

            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                LOGS.info(f"[MovieBox] Download complete: {filepath} ({os.path.getsize(filepath) / (1024*1024):.1f}MB)")
                return filepath
            else:
                LOGS.error(f"[MovieBox] Downloaded file is empty or missing: {filepath}")
                return None

        except asyncio.TimeoutError:
            LOGS.error(f"[MovieBox] Download timed out after 10 minutes")
            return None
        except Exception as e:
            LOGS.error(f"[MovieBox] Download error: {e}")
            return None

    async def try_fallback(self, anime_name: str, season: int, episode: int, filename: str, ani_id: int = None) -> str | None:
        """Full fallback flow: search -> find episode -> download.
        
        Args:
            anime_name: Clean English anime title
            season: Season number
            episode: Episode number
            filename: Desired output filename for the downloaded file
            ani_id: Optional AniList ID
            
        Returns:
            Path to downloaded MP4 file, or None if fallback failed
        """
        await rep.report(f"⚡ [MovieBox Fallback] Searching for: {anime_name} S{season}E{episode} (Hindi)", "warning", log=True)

        # 1. Search for Hindi version
        result = await self.search_hindi(anime_name)
        if not result:
            await rep.report(f"⚡ [MovieBox Fallback] No Hindi version found for: {anime_name}", "warning", log=True)
            return None

        # 2. Get episode download URL
        ep_info = await self.get_episode_url(result["subjectId"], season, episode, ani_id=ani_id)
        if not ep_info:
            await rep.report(f"⚡ [MovieBox Fallback] Episode S{season}E{episode} not available on MovieBox", "warning", log=True)
            return None

        await rep.report(
            f"⚡ [MovieBox Fallback] Found: {result['title']} S{season}E{episode} "
            f"({ep_info['resolution']}p, {ep_info['size'] / (1024*1024):.0f}MB, {ep_info['codec']})",
            "warning", log=True
        )

        # 3. Download the file
        dl_path = await self.download_file(ep_info["url"], filename)
        if dl_path:
            await rep.report(f"⚡ [MovieBox Fallback] Downloaded successfully: {filename}", "warning", log=True)
        else:
            await rep.report(f"⚡ [MovieBox Fallback] Download failed for: {filename}", "error", log=True)

        return dl_path
