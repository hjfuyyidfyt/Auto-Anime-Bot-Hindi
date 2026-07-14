import re
from calendar import month_name
from datetime import datetime
from random import choice
from asyncio import sleep as asleep
from aiohttp import ClientSession
import xml.etree.ElementTree as ET
from anitopy import parse
from bot.core.bot_instance import bot, ani_cache
from config import Var, LOGS
from .ffencoder import ffargs
from .func_utils import handle_logs
from .reporter import rep

async def get_prequels_of_id(ani_id: int) -> list:
    query = """
    query ($id: Int) {
      Media (id: $id, type: ANIME) {
        relations {
          edges {
            relationType
            node {
              id
              type
            }
          }
        }
      }
    }
    """
    for attempt in range(5):
        try:
            async with ClientSession() as sess:
                async with sess.post("https://graphql.anilist.co", json={'query': query, 'variables': {'id': ani_id}}) as resp:
                    if resp.status == 200:
                        resp_json = await resp.json()
                        media = resp_json.get('data', {}).get('Media', {}) or {}
                        relations = media.get('relations', {}).get('edges', [])
                        prequels = []
                        for edge in relations:
                            if edge.get('relationType') == 'PREQUEL':
                                node = edge.get('node', {})
                                if node.get('type') == 'ANIME':
                                    prequels.append(node.get('id'))
                        return prequels
                    elif resp.status == 429:
                        retry_after = int(resp.headers.get('Retry-After', 5))
                        LOGS.warning(f"AniList Rate Limited for get_prequels_of_id({ani_id}), waiting {retry_after}s (attempt {attempt+1}/5)...")
                        await asleep(retry_after + 1)
                    else:
                        await asleep(2)
        except Exception as e:
            LOGS.error(f"Error in get_prequels_of_id({ani_id}) attempt {attempt+1}: {e}")
            await asleep(2)
    return []

async def get_all_related_ids(ani_id: int) -> list:
    query = """
    query ($id: Int) {
      Media (id: $id, type: ANIME) {
        relations {
          edges {
            relationType
            node {
              id
              type
            }
          }
        }
      }
    }
    """
    visited = {ani_id}
    queue = [ani_id]
    
    while queue:
        current_id = queue.pop(0)
        for attempt in range(5):
            try:
                async with ClientSession() as sess:
                    async with sess.post("https://graphql.anilist.co", json={'query': query, 'variables': {'id': current_id}}) as resp:
                        if resp.status == 200:
                            resp_json = await resp.json()
                            media = resp_json.get('data', {}).get('Media', {}) or {}
                            relations = media.get('relations', {}).get('edges', [])
                            for edge in relations:
                                rtype = edge.get('relationType')
                                if rtype in ('PREQUEL', 'SEQUEL'):
                                    node = edge.get('node', {})
                                    if node.get('type') == 'ANIME':
                                        nid = node.get('id')
                                        if nid not in visited:
                                            visited.add(nid)
                                            queue.append(nid)
                            break
                        elif resp.status == 429:
                            retry_after = int(resp.headers.get('Retry-After', 5))
                            LOGS.warning(f"AniList Rate Limited for get_all_related_ids({current_id}), waiting {retry_after}s (attempt {attempt+1}/5)...")
                            await asleep(retry_after + 1)
                        else:
                            await asleep(2)
            except Exception as e:
                LOGS.error(f"Error in get_all_related_ids({current_id}) attempt {attempt+1}: {e}")
                await asleep(2)
    return list(visited)

async def get_absolute_season_by_relations(ani_id: int) -> int:
    # 1. Try to get cached timeline from local database
    try:
        from bot.core.database import db
        cached_nodes = await db.get_cached_timeline(ani_id)
        if cached_nodes:
            for node in cached_nodes:
                if node.get('id') == ani_id:
                    return node.get('absolute_season', 1)
    except Exception as e:
        LOGS.error(f"Error checking cached timeline for {ani_id}: {e}")

    # 2. Cache miss: Fetch all related IDs bidirectionally
    related_ids = await get_all_related_ids(ani_id)
    
    # 3. Fetch metadata for all nodes in the timeline
    chain_nodes = []
    for rid in related_ids:
        node_media = await get_anime_by_id(rid)
        if node_media:
            chain_nodes.append(node_media)
            
    # 4. Sort nodes chronologically by release date (startDate)
    def get_start_date_key(node):
        sd = node.get('startDate') or {}
        year = sd.get('year') or 9999
        month = sd.get('month') or 12
        day = sd.get('day') or 31
        return (year, month, day)
        
    chain_nodes.sort(key=get_start_date_key)
    
    if not chain_nodes:
        return 1
        
    # 5. Calculate absolute season values
    season_counter = 1
    timeline_nodes = []
    saved_related_ids = []
    
    for idx, node in enumerate(chain_nodes):
        node_id = node.get('id')
        saved_related_ids.append(node_id)
        
        title = node.get('title', {}).get('english') or node.get('title', {}).get('romaji')
        fmt = node.get('format', '')
        
        if idx == 0:
            season_val = 1
        else:
            curr_title = (title or "").lower()
            curr_format = (fmt or "").upper()
            is_same_season = False
            if curr_format in ('OVA', 'SPECIAL', 'MOVIE'):
                is_same_season = True
            elif 'special' in curr_title or 'ryusui' in curr_title or 'episode' in curr_title:
                is_same_season = True
            elif any(part in curr_title for part in ('part 2', 'part 3', 'part 4', 'cour 2', 'cour 3', 'cour 4')):
                is_same_season = True
            elif ('part' in curr_title or 'cour' in curr_title) and ('part 1' not in curr_title and 'cour 1' not in curr_title):
                is_same_season = True
                
            if not is_same_season:
                season_counter += 1
            season_val = season_counter
            
        timeline_nodes.append({
            'id': node_id,
            'title': node.get('title'),
            'format': fmt,
            'absolute_season': season_val
        })
        
    try:
        from bot.core.database import db
        await db.save_cached_timeline(saved_related_ids, timeline_nodes)
        LOGS.info(f"Saved cached timeline for base ID {saved_related_ids[0]} with {len(timeline_nodes)} related IDs.")
    except Exception as e:
        LOGS.error(f"Error saving timeline cache for {ani_id}: {e}")
        
    for node in timeline_nodes:
        if node.get('id') == ani_id:
            return node.get('absolute_season', 1)
    return 1


CAPTION_FORMAT = """
<b>◆ <i>{title}</i> ◆</b>
<b>{season_info_line}</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>⌬ Audio:</b> <i>{audio_lang} [ESub]</i>  
<b>⌬ Status:</b> <i>{status}</i>  
<b>⌬ Total Episodes:</b> <i>{t_eps}</i>

<b>✦ Genres:</b> <i>{genres}</i>
<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>✧ Powered By:</b> <i>{cred}</i>
"""

GENRES_EMOJI = {
    "Action": "👊", "Adventure": choice(['🪂', '🧗‍♀️', '🗺️']), "Comedy": "🤣",
    "Drama": "🎭", "Ecchi": choice(['💋', '🥵']), "Fantasy": choice(['🧞', '🧙‍♂️', '🐉', '🌗']),
    "Hentai": "🔞", "Horror": "☠️", "Mahou Shoujo": "☯️", "Mecha": "🤖", "Mystery": "🔮",
    "Psychological": "♟️", "Romance": "💞", "Sci-Fi": "🛸", "Slice of Life": choice(['☘️', '🍁']),
    "Sports": "⚽️", "Supernatural": "🫧", "Thriller": choice(['🥶', '🔪', '🤯']),
    "Isekai": choice(['🌌', '🌀', '🧙']), "Historical": "🏯", "Music": "🎶", "Martial Arts": "🥋",
    "School": "🏫", "Military": "🎖️", "Demons": "😈", "Vampire": "🧛‍♂️", "Space": "🚀",
    "Game": "🎮", "Crime": "🚓", "Parody": "😂", "Detective": "🕵️‍♂️", "Tragedy": "💔",
    "Yaoi": "👨‍❤️‍👨", "Yuri": "👩‍❤️‍👩", "Kids": "🧒", "Harem": "👸", "Music & Idol": "🎤",
    "Post-Apocalyptic": "☢️", "Cyberpunk": "💽", "Samurai": "🗡️", "Time Travel": "⏳"
}

GENRE_NORMALIZATION = {
    "Action & Adventure": "Action",
    "Romantic Comedy": "Comedy",
    "Shounen": "Action",
    "Shoujo": "Romance",
    "Seinen": "Drama",
    "Josei": "Drama",
    "Slice-of-Life": "Slice of Life",
    "Magical Girl": "Mahou Shoujo",
    "Science Fiction": "Sci-Fi",
    "Psychological Thriller": "Psychological",
    "Suspense": "Thriller",
    "Martial-Arts": "Martial Arts",
    "Fantasy Adventure": "Fantasy",
    "Post Apocalypse": "Post-Apocalyptic",
    "Cyber Punk": "Cyberpunk",
    "Historical Drama": "Historical",
    "Romance Comedy": "Romance",
    "Action Comedy": "Action",
    "Super Power": "Supernatural",
    "Game Based": "Game",
    "Music Idol": "Music & Idol",
    "Sports Drama": "Sports",
    "Military Sci-Fi": "Military",
    "Time-Travel": "Time Travel",
    "Detective Mystery": "Detective"
}

ANIME_GRAPHQL_QUERY = """
query ($id: Int, $search: String, $seasonYear: Int) {
  Media(id: $id, type: ANIME, format_not_in: [MUSIC, MANGA, NOVEL, ONE_SHOT], search: $search, seasonYear: $seasonYear) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    type
    format
    status(version: 2)
    description(asHtml: false)
    startDate {
      year
      month
      day
    }
    endDate {
      year
      month
      day
    }
    season
    seasonYear
    episodes
    duration
    chapters
    volumes
    countryOfOrigin
    source
    hashtag
    trailer {
      id
      site
      thumbnail
    }
    updatedAt
    coverImage {
      large
    }
    bannerImage
    genres
    synonyms
    averageScore
    meanScore
    popularity
    trending
    favourites
    studios {
      nodes {
        name
        siteUrl
      }
    }
    isAdult
    nextAiringEpisode {
      airingAt
      timeUntilAiring
      episode
    }
    airingSchedule {
      edges {
        node {
          airingAt
          timeUntilAiring
          episode
        }
      }
    }
    externalLinks {
      url
      site
    }
    siteUrl
  }
}
"""

def normalize_genres(genres: list) -> list:
    normalized = []
    for genre in genres or []:
        genre_key = GENRE_NORMALIZATION.get(genre, genre)
        if genre_key in GENRES_EMOJI:
            normalized.append(genre_key)
    return normalized

class AniLister:
    def __init__(self, anime_name: str, year: int) -> None:
        self.__api = "https://graphql.anilist.co"
        self.__ani_name = anime_name
        self.__ani_year = year
        self.__vars = {'search': self.__ani_name, 'seasonYear': self.__ani_year}

    def __update_vars(self, year: bool = True) -> None:
        if year:
            self.__ani_year -= 1
            self.__vars['seasonYear'] = self.__ani_year
        else:
            self.__vars = {'search': self.__ani_name}

    async def post_data(self):
        async with ClientSession() as sess:
            async with sess.post(self.__api, json={'query': ANIME_GRAPHQL_QUERY, 'variables': self.__vars}) as resp:
                return (resp.status, await resp.json(), resp.headers)

    async def get_anidata(self):
        orig_name = self.__ani_name
        orig_year = self.__ani_year
        cache_key = f"{orig_name}:{orig_year}"
        if cache_key in ani_cache:
            return ani_cache[cache_key]
        res_code, resp_json, res_heads = await self.post_data()
        while res_code == 404 and self.__ani_year > 2020:
            self.__update_vars()
            await rep.report(f"AniList Query Name: {self.__ani_name}, Retrying with {self.__ani_year}", "warning", log=False)
            res_code, resp_json, res_heads = await self.post_data()
        if res_code == 404:
            self.__update_vars(year=False)
            res_code, resp_json, res_heads = await self.post_data()
        if res_code == 200:
            data = resp_json.get('data', {}).get('Media', {}) or {}
            ani_cache[cache_key] = data
            final_key = f"{self.__ani_name}:{self.__ani_year}"
            ani_cache[final_key] = data
            return data
        elif res_code == 429:
            retry_after = int(res_heads.get('Retry-After', 10))
            await asleep(retry_after * 1.5)
            return await self.get_anidata()
        elif res_code in [500, 501, 502]:
            await asleep(5)
            return await self.get_anidata()
        await rep.report(f"AniList API Error: {res_code}", "error", log=False)
        if res_code == 404:
            ani_cache[cache_key] = {}
        return {}

async def get_anime_by_id(ani_id: int):
    cache_key = f"ani_id:{ani_id}"
    if cache_key in ani_cache:
        val = ani_cache[cache_key]
        if val:
            return val
    for attempt in range(5):
        try:
            async with ClientSession() as sess:
                async with sess.post("https://graphql.anilist.co", json={'query': ANIME_GRAPHQL_QUERY, 'variables': {'id': ani_id}}) as resp:
                    if resp.status == 200:
                        resp_json = await resp.json()
                        data = resp_json.get('data', {}).get('Media', {}) or {}
                        if data:
                            ani_cache[cache_key] = data
                        return data
                    elif resp.status == 429:
                        retry_after = int(resp.headers.get('Retry-After', 5))
                        LOGS.warning(f"AniList Rate Limited for get_anime_by_id({ani_id}), waiting {retry_after}s (attempt {attempt+1}/5)...")
                        await asleep(retry_after + 1)
                    else:
                        await asleep(2)
        except Exception as e:
            LOGS.error(f"Error in get_anime_by_id({ani_id}) attempt {attempt+1}: {e}")
            await asleep(2)
    return {}

    @handle_logs
    async def _parse_anilist_data(self, data):
        if not data or not data.get("data", {}).get("Media"):
            return {}
        anime = data["data"]["Media"]
        genres = normalize_genres(anime.get("genres", []))
        return {
            "id": anime.get("id"),
            "idMal": anime.get("idMal"),
            "title": anime.get("title", {}),
            "status": anime.get("status", "").replace("_", " ").title(),
            "description": anime.get("description"),
            "startDate": anime.get("startDate", {}),
            "endDate": anime.get("endDate", {}),
            "episodes": anime.get("episodes"),
            "genres": genres,
            "averageScore": anime.get("averageScore"),
            "coverImage": anime.get("coverImage", {})
        }

    @handle_logs
    async def get_anilist_id(self, mal_id: int = None, name: str = None, year: int = None):
        if mal_id:
            variables = {'idMal': mal_id}
        else:
            variables = {'search': name, 'seasonYear': year} if year else {'search': name}
        res_code, resp_json, res_heads = await self.post_data()
        if res_code == 200 and resp_json.get('data', {}).get('Media'):
            return resp_json['data']['Media']['id']
        elif res_code == 429:
            f_timer = int(res_heads.get('Retry-After', 10))
            await rep.report(f"AniList ID Fetch Rate Limit: Sleeping for {f_timer}s", "error")
            await asleep(f_timer)
            return await self.get_anilist_id(mal_id, name, year)
        await rep.report(f"Failed to fetch AniList ID for {name or mal_id}", "error")
        return None

class TextEditor:
    def __init__(self, name):
        self.__name = name
        self.adata = {}
        self.pdata = parse(name)
        self.anilister = AniLister(self.__name, datetime.now().year)

    async def load_anilist(self):
        if self.__name in ani_cache:
            self.adata = ani_cache[self.__name]
            return

        # Determine the start year based on parsed year if available
        anime_year = self.pdata.get("anime_year")
        if anime_year:
            year_str = str(anime_year[-1]) if isinstance(anime_year, list) else str(anime_year)
            year_clean = ''.join(c for c in year_str if c.isdigit())
            start_year = int(year_clean) if year_clean else datetime.now().year
        else:
            start_year = datetime.now().year

        cache_names = set()
        # Add a final fallback: Search by cleaned title only (without Season/Year logic)
        variations = [(False, False), (False, True), (True, False), (True, True), "clean"]
        
        for var in variations:
            if var == "clean":
                ani_name = self.pdata.get("anime_title")
            else:
                no_s, no_y = var
                ani_name = await self.parse_name(no_s, no_y)
            
            if not ani_name or ani_name in cache_names:
                continue
            cache_names.add(ani_name)
            
            # Create a fresh AniLister instance for each variation to avoid year pollution
            anilister = AniLister(ani_name, start_year)
            self.adata = await anilister.get_anidata()
            if self.adata:
                break
        
        if not self.adata:
            # Try to resolve a dummy ID from name hash to support non-AniList shows (like Indian cartoons)
            anime_title = self.pdata.get("anime_title") or self.__name
            import hashlib
            h = hashlib.md5(anime_title.encode()).hexdigest()
            dummy_id = int(h[:7], 16)
            self.adata = {
                'id': dummy_id,
                'title': {'english': anime_title, 'romaji': anime_title},
                'is_dummy': True
            }
        if self.adata and not self.adata.get('is_dummy'):
            parsed_season_raw = self.pdata.get("anime_season")
            if parsed_season_raw:
                s_str = str(parsed_season_raw[-1]) if isinstance(parsed_season_raw, list) else str(parsed_season_raw)
                s_clean = ''.join(c for c in s_str if c.isdigit())
                if s_clean:
                    parsed_season = int(s_clean)
                    absolute_season = await get_absolute_season_by_relations(self.adata.get('id'))
                    if absolute_season != parsed_season:
                        # Fetch the timeline doc containing all related nodes
                        try:
                            from bot.core.database import db
                            timeline_doc = await db.timelines.find_one({'related_ids': self.adata.get('id')})
                            if timeline_doc:
                                matched_node = None
                                for node in timeline_doc.get('timeline_nodes', []):
                                    if node.get('absolute_season') == parsed_season:
                                        matched_node = node
                                        break
                                if matched_node:
                                    matched_data = await get_anime_by_id(matched_node.get('id'))
                                    if matched_data:
                                        self.adata = matched_data
                        except Exception as e:
                            LOGS.error(f"Error resolving season mismatch: {e}")
        
        # Cache the result under the full release title to skip all variations in the future
        ani_cache[self.__name] = self.adata

    @handle_logs
    async def parse_name(self, no_s=False, no_y=False):
        anime_name = self.pdata.get("anime_title") or self.__name
        anime_season = self.pdata.get("anime_season")
        anime_year = self.pdata.get("anime_year")
        if anime_name:
            pname = anime_name
            if not no_s and self.pdata.get("episode_number") and anime_season:
                s_str = str(anime_season[-1]) if isinstance(anime_season, list) else str(anime_season)
                s_clean = ''.join(c for c in s_str if c.isdigit())
                if s_clean and int(s_clean) > 1:
                    pname += f" {int(s_clean)}"
            if not no_y and anime_year:
                pname += f" {anime_year}"
            return pname
        return anime_name

    @handle_logs
    async def get_poster(self):
        anime_id = self.adata.get("id")
        if anime_id and str(anime_id).isdigit() and not self.adata.get("is_dummy"):
            return f"https://img.anili.st/media/{anime_id}"
        return "https://ibb.co/5xjBCXKp"

    async def get_season(self):
        """Get season number: first try absolute season from prequel relations, then AniList title, then synonyms, then anitopy."""
        ani_id = self.adata.get("id")
        if ani_id and str(ani_id).isdigit() and not self.adata.get("is_dummy"):
            try:
                cache_key = f"abs_season:{ani_id}"
                if cache_key in ani_cache:
                    abs_season = ani_cache[cache_key]
                else:
                    abs_season = await get_absolute_season_by_relations(int(ani_id))
                    ani_cache[cache_key] = abs_season
                if abs_season > 1:
                    return str(abs_season).zfill(2)
            except Exception as e:
                LOGS.error(f"Error calculating absolute season for ID {ani_id}: {e}")

        # Fallback 1: Try to extract from AniList English or Romaji title
        for key in ('english', 'romaji'):
            title = (self.adata.get('title') or {}).get(key) or ''
            m = re.search(r'(?:Season|S)\s*(\d+)', title, re.IGNORECASE)
            if m:
                return str(m.group(1)).zfill(2)

        # Fallback 2: Try AniList synonyms for patterns like "3rd Season"
        for syn in (self.adata.get('synonyms') or []):
            m = re.search(r'(\d+)(?:st|nd|rd|th)\s*Season', syn, re.IGNORECASE)
            if m:
                return str(m.group(1)).zfill(2)

        # Fallback 3: Fall back to anitopy's anime_season
        ani_s = self.pdata.get('anime_season', '01')
        raw = str(ani_s[-1]) if isinstance(ani_s, list) else str(ani_s)
        digits = ''.join(c for c in raw if c.isdigit())
        return digits.zfill(2) if digits else '01'

    def _get_season(self):
        # Synchronous fallback if needed
        for key in ('english', 'romaji'):
            title = (self.adata.get('title') or {}).get(key) or ''
            m = re.search(r'(?:Season|S)\s*(\d+)', title, re.IGNORECASE)
            if m:
                return str(m.group(1)).zfill(2)
        for syn in (self.adata.get('synonyms') or []):
            m = re.search(r'(\d+)(?:st|nd|rd|th)\s*Season', syn, re.IGNORECASE)
            if m:
                return str(m.group(1)).zfill(2)
        ani_s = self.pdata.get('anime_season', '01')
        raw = str(ani_s[-1]) if isinstance(ani_s, list) else str(ani_s)
        digits = ''.join(c for c in raw if c.isdigit())
        return digits.zfill(2) if digits else '01'

    @handle_logs
    async def get_upname(self, qual=""):
        anime_name = self.pdata.get("anime_title")
        codec = 'HEVC' if 'libx265' in ffargs[qual] else 'AV1' if 'libaom-av1' in ffargs[qual] else ''
        lang = 'SUB' if 'sub' in self.__name.lower() else 'Sub'
        anime_season = await self.get_season()
        if anime_name and self.pdata.get("episode_number"):
            titles = self.adata.get('title', {})
            return f"""[S{anime_season}-{'E'+str(self.pdata.get('episode_number')) if self.pdata.get('episode_number') else ''}] {titles.get('english') or titles.get('romaji') or titles.get('native')} {'['+qual+'p]' if qual else ''} {'['+codec.upper()+'] ' if codec else ''}{'['+lang+']'} {Var.BRAND_UNAME}.mkv"""
        return None

    @handle_logs
    async def get_caption(self):
        sd = self.adata.get('startDate', {})
        try:
            month_idx = int(sd.get('month')) if sd.get('month') else None
            startdate = f"{month_name[month_idx]} {sd['day']}, {sd['year']}" if sd.get('day') and sd.get('year') and month_idx else "N/A"
        except (ValueError, TypeError):
            startdate = "N/A"
        ed = self.adata.get('endDate', {})
        try:
            month_idx = int(ed.get('month')) if ed.get('month') else None
            enddate = f"{month_name[month_idx]} {ed['day']}, {sd['year']}" if ed.get('day') and ed.get('year') and month_idx else "N/A"
        except (ValueError, TypeError):
            enddate = "N/A"
        titles = self.adata.get("title", {})
        
        # Determine Audio Language
        audio_lang = "Hindi"
        lower_name = self.__name.lower()
        if "multi" in lower_name:
            audio_lang = "Multi Audio"
        elif "dual" in lower_name:
            audio_lang = "Dual Audio"
        elif "hindi" in lower_name:
            audio_lang = "Hindi"
        elif "english" in lower_name or "dub" in lower_name:
            audio_lang = "English"
        elif "japanese" in lower_name or "sub" in lower_name:
            audio_lang = "Japanese"

        # Dynamic Subtitles and Parts/Cours parsing
        main_title = titles.get('english') or titles.get('romaji') or titles.get('native') or "N/A"
        sub_title = ""
        if ":" in main_title:
            sub_title = main_title.split(":")[1].strip()
            sub_title = re.sub(r'(?i)\b(part|cour|season)\s*\d+\b', '', sub_title).strip()
            sub_title = re.sub(r'\s+', ' ', sub_title).strip(" -")
            
        part_str = ""
        part_match = re.search(r'(?i)\b(part|cour)\s*(\d+)\b', main_title)
        if part_match:
            part_name = part_match.group(1).title()
            part_num = part_match.group(2)
            part_str = f" • {part_name} {part_num}"
            
        anime_season = await self.get_season()
        ep_no = self.pdata.get("episode_number") or "N/A"
        
        if self.adata.get("format") == "MOVIE":
            season_info_line = "Movie"
        elif sub_title:
            season_info_line = f"Season {anime_season} ({sub_title}){part_str} • Episode {ep_no}"
        else:
            season_info_line = f"Season {anime_season}{part_str} • Episode {ep_no}"

        return CAPTION_FORMAT.format(
            title=main_title,
            form=self.adata.get("format") or "N/A",
            genres=", ".join(f"{GENRES_EMOJI[x]} #{x.replace(' ', '_').replace('-', '_')}" for x in (self.adata.get('genres') or [])),
            avg_score=f"{sc}%" if (sc := self.adata.get('averageScore')) else "N/A",
            status=self.adata.get("status") or "N/A",
            start_date=startdate,
            end_date=enddate,
            t_eps=self.adata.get("episodes") or "N/A",
            season_info_line=season_info_line,
            plot=(desc if (desc := self.adata.get("description") or "N/A") and len(desc) < 200 else desc[:200] + "...") if self.adata.get("description") else "N/A",
            cred=Var.BRAND_UNAME,
            audio_lang=audio_lang
        )
