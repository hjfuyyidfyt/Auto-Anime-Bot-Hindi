import asyncio
import urllib.parse
from bot.core.bot_instance import bot_loop, active_priority_tasks
from bot.core.database import db
from bot.core.text_utils import TextEditor
from bot.core.func_utils import get_all_feed_entries
from bot.core.auto_animes import get_animes
from bot.core.reporter import rep
from config import Var, LOGS

async def background_sync_worker():
    await asyncio.sleep(10)  # Let the bot startup settle down
    await rep.report("Background sync worker started!", "info", log=True)
    
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
            
            # 3. Search Nyaa.si for [Anime Name] Hindi
            query = f"{anime_name} Hindi"
            encoded_query = urllib.parse.quote(query)
            rss_url = f"https://nyaa.si/?page=rss&q={encoded_query}&c=1_2&f=0"
            
            entries = await get_all_feed_entries(rss_url)
            if not entries:
                await rep.report(f"Background Worker: No Hindi episodes found on Nyaa.si for: '{anime_name}'", "warning", log=True)
                await db.update_task_status(task_id, 'completed')
                continue
                
            found_episodes = []
            for entry in entries:
                if "hindi" not in entry.title.lower():
                    continue
                entry_info = TextEditor(entry.title)
                entry_title = entry_info.pdata.get("anime_title")
                
                # Check match
                if entry_title and (anime_name.lower() in entry_title.lower() or entry_title.lower() in anime_name.lower()):
                    try:
                        ep_val = float(entry_info.pdata.get("episode_number"))
                        ep_str = entry_info.pdata.get("episode_number")
                        found_episodes.append((ep_val, ep_str, entry.title, entry.link, entry_info))
                    except (TypeError, ValueError):
                        continue
                        
            if not found_episodes:
                await rep.report(f"Background Worker: No matching episodes found for: '{anime_name}'", "warning", log=True)
                await db.update_task_status(task_id, 'completed')
                continue
                
            # Sort episodes chronologically
            found_episodes.sort(key=lambda x: x[0])
            
            # Load first anime ID to fetch database
            first_info = found_episodes[0][4]
            await first_info.load_anilist()
            ani_id = first_info.adata.get('id')
            
            if not ani_id:
                await rep.report(f"Background Worker: Failed to fetch AniList ID for: '{anime_name}'", "error", log=True)
                await db.update_task_status(task_id, 'failed')
                continue
                
            # Loop through episodes chronologically
            for ep_val, ep_str, ep_title, ep_link, _ in found_episodes:
                # PAUSE CHECK: check before starting EACH episode
                while active_priority_tasks:
                    await rep.report("Background worker paused: High priority tasks are active", "info", log=True)
                    await asyncio.sleep(15)
                
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
