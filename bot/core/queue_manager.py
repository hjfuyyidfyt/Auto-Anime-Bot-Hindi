import asyncio
import urllib.parse
from bot.core.bot_instance import bot_loop, active_priority_tasks
from bot.core.database import db
from bot.core.text_utils import TextEditor
from bot.core.func_utils import search_nyaa_all_pages, is_hindi_release
from bot.core.auto_animes import get_animes
from bot.core.reporter import rep
from config import Var, LOGS

async def background_sync_worker():
    await asyncio.sleep(10)  # Let the bot startup settle down
    await rep.report("Background sync worker started!", "info", log=True)
    
    # Reset any stuck 'processing' tasks to 'pending' on startup
    try:
        stuck_tasks = await db.sync_queue.find({'status': 'processing'}).to_list(length=None)
        if stuck_tasks:
            for task in stuck_tasks:
                await db.update_task_status(task['_id'], 'pending')
            await rep.report(f"Reset {len(stuck_tasks)} stuck processing tasks to pending", "info", log=True)
    except Exception as startup_err:
        LOGS.error(f"Failed to reset stuck tasks on startup: {startup_err}")
    
    while True:
        try:
            # 1. Pause checking: yield if priority tasks are active
            while active_priority_tasks:
                await asyncio.sleep(15)
                
            # 2. Get next pending task from DB
            task = await db.get_next_pending_task()
            if not task:
                await asyncio.sleep(30)
                continue
                
            anime_name = task.get('anime_name')
            task_id = task.get('_id')
            
            await rep.report(f"Background worker processing task: '{anime_name}'", "info", log=True)
            await db.update_task_status(task_id, 'processing')
            
            # 3. Search Nyaa.si using multi-page scraper
            entries = await search_nyaa_all_pages(anime_name, max_pages=10)
            if not entries:
                await rep.report(f"Background Worker: No Hindi/Multi episodes found on Nyaa.si for: '{anime_name}'", "warning", log=True)
                await db.update_task_status(task_id, 'completed')
                continue
                
            found_episodes = []
            for entry in entries:
                if not is_hindi_release(entry.title):
                    continue
                entry_info = TextEditor(entry.title)
                entry_title = entry_info.pdata.get("anime_title")
                
                # Check match
                if entry_title and (anime_name.lower() in entry_title.lower() or entry_title.lower() in anime_name.lower()):
                    try:
                        # Extract season
                        season_raw = entry_info.pdata.get("anime_season", "1")
                        if isinstance(season_raw, list):
                            season_str = str(season_raw[-1]) if season_raw else "1"
                        else:
                            season_str = str(season_raw)
                        season_str = ''.join(c for c in season_str if c.isdigit())
                        season_val = int(season_str) if season_str else 1
                        
                        # Extract episode
                        ep_str = entry_info.pdata.get("episode_number")
                        if not ep_str:
                            continue
                        if isinstance(ep_str, list):
                            ep_str = str(ep_str[-1]) if ep_str else "1"
                        else:
                            ep_str = str(ep_str)
                        ep_val = float(ep_str)
                        
                        found_episodes.append((season_val, ep_val, ep_str, entry.title, entry.link, entry_info))
                    except (TypeError, ValueError):
                        continue
                        
            if not found_episodes:
                await rep.report(f"Background Worker: No matching episodes found for: '{anime_name}'", "warning", log=True)
                await db.update_task_status(task_id, 'completed')
                continue
                
            # Sort episodes chronologically by season first, then by episode number
            found_episodes.sort(key=lambda x: (x[0], x[1]))
            
            # Loop through episodes chronologically
            for season_val, ep_val, ep_str, ep_title, ep_link, entry_info in found_episodes:
                # PAUSE CHECK: check before starting EACH episode
                while active_priority_tasks:
                    await rep.report("Background worker paused: High priority tasks are active", "info", log=True)
                    await asyncio.sleep(15)
                
                # Fetch AniList ID dynamically for each episode
                await entry_info.load_anilist()
                ani_id = entry_info.adata.get('id')
                
                if not ani_id:
                    await rep.report(f"Background Worker: Failed to fetch AniList ID for episode: '{ep_title}'", "error", log=True)
                    continue
                
                ani_data = await db.get_anime(ani_id)
                qual_data = ani_data.get(ep_str) if ani_data else None
                
                if not ani_data or not qual_data or not all(qual_data.get(qual) for qual in Var.QUALS):
                    await rep.report(f"Background Worker starting: {ep_title}", "info", log=True)
                    try:
                        await get_animes(ep_title, ep_link, force=True, is_priority=False)
                    except Exception as e:
                        await rep.report(f"Background Worker failed episode {ep_title}: {e}", "error", log=True)
                        
            await db.update_task_status(task_id, 'completed')
            await rep.report(f"Background worker completed task: '{anime_name}'", "info", log=True)
            
        except Exception as err:
            LOGS.error(f"Error in background sync worker: {err}")
            if 'task_id' in locals():
                try:
                    await db.update_task_status(task_id, 'failed')
                except Exception as db_err:
                    LOGS.error(f"Failed to update task status to failed: {db_err}")
            await asyncio.sleep(30)

