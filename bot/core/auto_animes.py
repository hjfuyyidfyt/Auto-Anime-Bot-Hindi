from asyncio import gather, create_task, sleep as asleep, Event
from asyncio.subprocess import PIPE
from os import path as ospath, system
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove
from traceback import format_exc
from base64 import urlsafe_b64encode
from time import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import Var
from bot.core.bot_instance import bot, bot_loop, ani_cache, ffQueue, ffLock, ff_queued, active_priority_tasks
from .tordownload import TorDownloader
from .database import db
from .func_utils import getfeed, encode, editMessage, sendMessage, convertBytes, search_nyaa_all_pages, is_hindi_release
from .text_utils import TextEditor
from .ffencoder import FFEncoder
from .tguploader import TgUploader
from .reporter import rep
from .fallback_downloader import MovieBoxFallback

btn_formatter = {
    'HDRip': '𝗛𝗗𝗥𝗶𝗽',
    '1080': '𝟭𝟬𝟴𝟬𝗣',
    '720': '𝟳𝟮𝟬𝗣',
    '480': '𝟰𝟴𝟬𝗣',
    '360': '𝟯𝟲𝟬𝗣'
}

@bot.on_message(filters.command("add_rss") & filters.user(Var.ADMINS))
async def add_custom_rss(client, message: Message):
    if len(message.command) < 2:
        bot.user_states[message.from_user.id] = "waiting_for_addrss"
        await message.reply_text("📡 <b>Please send the custom RSS feed URL to add:</b>", quote=True)
        return

    url = message.command[1]
    if not url.startswith("http"):
        await message.reply_text("⚠️ Invalid URL format.")
        await rep.report(f"Invalid RSS URL: {url}", "error", log=True)
        return

    ani_cache["custom_rss"].add(url)
    await message.reply_text(f"✅ RSS feed added:\n<code>{url}</code>")
    await rep.report(f"RSS feed added: {url}", "info", log=True)

@bot.on_message(filters.command("list_rss") & filters.user(Var.ADMINS))
async def list_rss(client, message: Message):
    feeds = sorted(list(ani_cache.get("custom_rss", [])))
    if not feeds:
        buttons = [[InlineKeyboardButton("Add RSS ➕", callback_data="addrss_prompt")]]
        await message.reply_text("⚠️ No custom RSS links added yet.", reply_markup=InlineKeyboardMarkup(buttons))
        await rep.report("No custom RSS links found.", "warning", log=True)
    else:
        text = "📡 <b>Custom RSS Feeds:</b>\n\n"
        buttons = []
        for index, url in enumerate(feeds):
            text += f"<b>{index + 1}.</b> <code>{url}</code>\n"
            buttons.append([InlineKeyboardButton(f"❌ Delete Feed {index + 1}", callback_data=f"delrss_{index}")])
        buttons.append([
            InlineKeyboardButton("Add RSS ➕", callback_data="addrss_prompt"),
            InlineKeyboardButton("Close ✖️", callback_data="close")
        ])
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
        await rep.report("Listed custom RSS feeds.", "info", log=True)

@bot.on_message(filters.command("remove_rss") & filters.user(Var.ADMINS))
async def remove_rss(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("❗ Usage:\n<code>/remove_rss https://example.com/rss</code>\n\nOr use /list_rss to delete via buttons.")
        return

    url = message.command[1]
    if url in ani_cache.get("custom_rss", set()):
        ani_cache["custom_rss"].remove(url)
        await message.reply_text(f"❌ Removed:\n<code>{url}</code>")
        await rep.report(f"RSS feed removed: {url}", "info", log=True)
    else:
        await message.reply_text("⚠️ RSS link not found in custom list.")
        await rep.report(f"RSS link not found: {url}", "warning", log=True)

@bot.on_message(filters.command("setchannel") & filters.user(Var.ADMINS))
async def set_channel(client, message: Message):
    if len(message.command) < 3:
        bot.user_states[message.from_user.id] = "waiting_for_setchannel"
        await message.reply_text("📢 <b>Please send the mapping details:</b>\nFormat: <code><Anime Name or ID> <Channel ID></code>\nExample: <code>DAN DA DAN -1002812370717</code>", quote=True)
        return

    anime_name = " ".join(message.command[1:-1])
    try:
        channel_id = int(message.command[-1])
    except ValueError:
        await message.reply_text("⚠️ Iɴᴠᴀʟɪᴅ ᴄʜᴀɴɴᴇʟ ID. Pʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ɴᴜᴍᴇʀɪᴄ ᴄʜᴀᴛ ID.")
        return

    ani_info = TextEditor(anime_name)
    await ani_info.load_anilist()
    ani_id = ani_info.adata.get('id')

    if not ani_id:
        if anime_name.isdigit():
            ani_id = int(anime_name)
        else:
            await message.reply_text(f"⚠️ Aɴɪᴍᴇ ɴᴏᴛ ғᴏᴜɴᴅ : {anime_name}")
            return

    await db.set_anime_channel(ani_id, channel_id)
    await message.reply_text(f"<b><blockquote>✅ <u>Aɴɪᴍᴇ ID</u> : {ani_id} \n<u>Sᴇᴛ ᴛᴏ ᴄʜᴀɴɴᴇʟ</u> : {channel_id}</blockquote></b>")
    await rep.report(f"Anime {anime_name} (ID: {ani_id}) set to channel {channel_id}", "info", log=True)

@bot.on_message(filters.command("delchannel") & filters.user(Var.ADMINS))
async def del_channel(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("❗ Usage:\n<code>/delchannel <anime_name_or_id></code>\n\nOr use /listchannels to delete via buttons.")
        return

    anime_name = " ".join(message.command[1:])
    ani_info = TextEditor(anime_name)
    await ani_info.load_anilist()
    ani_id = ani_info.adata.get('id')

    if not ani_id:
        if anime_name.isdigit():
            ani_id = int(anime_name)
        else:
            await message.reply_text(f"⚠️ Anime not found: {anime_name}")
            return

    res = await db.delete_anime_channel(ani_id)
    if res:
        await message.reply_text(f"✅ Mapping for ID <code>{ani_id}</code> removed successfully.")
    else:
        await message.reply_text(f"⚠️ No mapping found for ID <code>{ani_id}</code>.")

@bot.on_message(filters.command("setsticker") & filters.user(Var.ADMINS))
async def set_sticker(client, message: Message):
    sticker_id = None
    if message.reply_to_message and message.reply_to_message.sticker:
        sticker_id = message.reply_to_message.sticker.file_id
    elif len(message.command) >= 2:
        sticker_id = message.command[1]
    
    if not sticker_id:
        await message.reply_text("<u>Usᴇ ɪᴛ ʟɪᴋᴇ ᴛʜɪs</u> : \n<b><blockquote expandable>/setsticker <sᴛɪᴄᴋᴇʀ_ɪᴅ> ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ sᴛɪᴄᴋᴇʀ</blockquote></b>")
        await rep.report("⚠️ Iɴᴠᴀʟɪᴅ /setsticker ᴄᴏᴍᴍᴀɴᴅ : Nᴏ ɪᴅ ᴘʀᴏᴠɪᴅᴇᴅ ᴀɴᴅ ᴜsᴇʀ ɴᴏᴛ ʀᴇᴘʟɪᴇᴅ", "error", log=True)
        return

    try:
        await bot.send_sticker(chat_id=message.chat.id, sticker=sticker_id)
    except Exception as e:
        await message.reply_text(f"⚠️ Iɴᴠᴀʟɪᴅ Sᴛɪᴄᴋᴇʀ ɪᴅ : {str(e)}")
        await rep.report(f"⚠️ Iɴᴠᴀʟɪᴅ Sᴛɪᴄᴋᴇʀ ɪᴅ : {sticker_id}, Error: {str(e)}", "error", log=True)
        return

    await db.set_sticker(sticker_id)
    await message.reply_text(f"✅ Sᴛɪᴄᴋᴇʀ sᴇᴛ : {sticker_id}")
    await rep.report(f"Sᴛɪᴄᴋᴇʀ sᴇᴛ : {sticker_id}", "info", log=True)

@bot.on_message(filters.command("listchannels") & filters.user(Var.ADMINS))
async def list_channels(client, message: Message):
    try:
        mappings = await db.get_all_anime_channels()
        if not mappings:
            buttons = [[InlineKeyboardButton("Set Mapping ➕", callback_data="setmap_prompt")]]
            await message.reply_text("⚠️ Nᴏ ᴀɴɪᴍᴇ ᴄʜᴀɴɴᴇʟs ᴍᴀᴘᴘᴇᴅ ʏᴇᴛ.", reply_markup=InlineKeyboardMarkup(buttons))
            await rep.report("Nᴏ ᴀɴɪᴍᴇ ᴄʜᴀɴɴᴇʟs ᴍᴀᴘᴘᴇᴅ ʏᴇT.", "warning", log=True)
            return

        text = "• <b>Aɴɪᴍᴇ ᴄʜᴀɴɴᴇʟ ᴍᴀᴘᴘɪɴɢ:</b>\n\n"
        buttons = []
        from bot.core.text_utils import get_anime_by_id
        for mapping in mappings:
            ani_id = mapping["ani_id"]
            channel_id = mapping["channel_id"]
            anime_name = mapping.get("anime_name")
            if not anime_name:
                try:
                    ani_data = await get_anime_by_id(ani_id)
                    anime_name = (ani_data.get('title') or {}).get('romaji') or (ani_data.get('title') or {}).get('english') or f"Anime {ani_id}"
                    await db.set_anime_channel(ani_id, channel_id, anime_name)
                except Exception:
                    anime_name = f"Anime {ani_id}"
            
            text += f"• id:<code>{ani_id}</code> (name: <code>{anime_name}</code>) ➡️ <code>{channel_id}</code>\n"
            buttons.append([InlineKeyboardButton(f"❌ Remove {anime_name[:25]}", callback_data=f"delmap_{ani_id}")])

        buttons.append([
            InlineKeyboardButton("Set Mapping ➕", callback_data="setmap_prompt"),
            InlineKeyboardButton("Close ✖️", callback_data="close")
        ])
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        await rep.report(f"Listed {len(mappings)} anime channel mappings", "info", log=True)
    except Exception as e:
        await message.reply_text("⚠️ Eʀʀᴏʀ ғᴇᴛᴄʜɪɴɢ ᴀɴɪᴍᴇ ᴄʜᴀɴɴᴇʟ ᴍᴀᴘᴘɪɴɢs.")
        await rep.report(f"Error in list_channels: {str(e)}", "error", log=True)
    except Exception as e:
        await message.reply_text("⚠️ Eʀʀᴏʀ ғᴇᴛᴄʜɪɴɢ ᴀɴɪᴍᴇ ᴄʜᴀɴɴᴇʟ ᴍᴀᴘᴘɪɴɢs.")
        await rep.report(f"Error in list_channels: {str(e)}", "error", log=True)

async def fetch_animes():
    await rep.report("Fetching Anime Started !!!", "info", log=True)
    processed_links = set()
    active_tasks = []
    max_tasks = 5
    while True:
        await asleep(30)
        if ani_cache['fetch_animes']:
            all_rss = Var.RSS_ITEMS + list(ani_cache.get("custom_rss", []))
            for link in all_rss:
                if len(active_tasks) >= max_tasks:
                    await gather(*active_tasks)
                    active_tasks = []
                if (info := await getfeed(link, 0)):
                    if info.link in processed_links:
                        continue
                    processed_links.add(info.link)
                    task = bot_loop.create_task(get_animes(info.title, info.link))
                    active_tasks.append(task)
            active_tasks = [task for task in active_tasks if not task.done()]

async def get_animes(name, torrent, force=False, is_priority=True):
    task_key = (name, torrent)
    if is_priority:
        active_priority_tasks.add(task_key)
    ani_id = None
    local_thumb = None
    try:
        if not is_hindi_release(name):
            return
        ani_info = TextEditor(name)
        await ani_info.load_anilist()
        ani_id, ep_no = ani_info.adata.get('id'), ani_info.pdata.get("episode_number")
        if not ani_id or not ep_no:
            if ani_id and (ani_info.adata.get('format') == 'MOVIE' or ani_info.adata.get('episodes') == 1):
                ep_no = "1"
            else:
                await rep.report(f"Invalid anime data for {name}: ID or episode number missing", "error", log=True)
                return

        # Auto-Sync Entire Series logic
        if 'synced_animes' not in ani_cache:
            ani_cache['synced_animes'] = set()
            
        if ani_id not in ani_cache['synced_animes'] and not force:
            is_synced = await db.is_anime_synced(ani_id)
            if is_synced:
                ani_cache['synced_animes'].add(ani_id)
            else:
                ani_cache['synced_animes'].add(ani_id)
                await db.add_synced_anime(ani_id)
                anime_title = ani_info.adata.get('title', {}).get('english') or ani_info.adata.get('title', {}).get('romaji')
                if anime_title:
                    await rep.report(f"Auto-Sync triggered for anime: {anime_title}", "info", log=True)
                    entries = await search_nyaa_all_pages(anime_title, max_pages=10)
                
                found_episodes = []
                parent_title = ani_info.pdata.get("anime_title")
                for entry in entries:
                    if not is_hindi_release(entry.title):
                        continue
                    entry_info = TextEditor(entry.title)
                    entry_title = entry_info.pdata.get("anime_title")
                    
                    # Verify title matches to avoid API call
                    if entry_title and parent_title and entry_title.lower() == parent_title.lower():
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
                            
                            found_episodes.append((season_val, ep_val, ep_str, entry.title, entry.link))
                        except (TypeError, ValueError):
                            continue
                
                # Sort episodes chronologically by season first, then by episode number
                found_episodes.sort(key=lambda x: (x[0], x[1]))
                
                if found_episodes:
                    await rep.report(f"Auto-Sync found {len(found_episodes)} episodes for '{anime_title}'. Syncing...", "info", log=True)
                    for season_val, ep_val, ep_str, ep_title, ep_link in found_episodes:
                        ep_entry_info = TextEditor(ep_title)
                        await ep_entry_info.load_anilist()
                        ep_ani_id = ep_entry_info.adata.get('id')
                        if not ep_ani_id:
                            continue
                        
                        ani_data = await db.get_anime(ep_ani_id)
                        qual_data = ani_data.get(ep_str) if ani_data else None
                        
                        if not ani_data or not qual_data or not all(qual_data.get(qual) for qual in Var.QUALS):
                            await rep.report(f"Sync Processing: {ep_title}", "info", log=True)
                            try:
                                await get_animes(ep_title, ep_link, force=True, is_priority=False)
                            except Exception as sync_err:
                                await rep.report(f"Failed to sync {ep_title}: {sync_err}", "error", log=True)
                    
        if ani_id not in ani_cache['ongoing']:
            ani_cache['ongoing'].add(ani_id)
        elif not force:
            return
        ani_data = await db.get_anime(ani_id)
        qual_data = ani_data.get(ep_no) if ani_data else None
        if force or not ani_data or not qual_data or not all(qual_data.get(qual) for qual in Var.QUALS):
            if "[Batch]" in name:
                await rep.report(f"Torrent Skipped!\n\n{name}", "warning", log=True)
                return
            await rep.report(f"New Anime Torrent Found!\n\n{name}", "info", log=True)
            anime_name = name
            photo_url = None
            if Var.ANIME in anime_name:
                photo_url = Var.CUSTOM_BANNER
            else:
                photo_url = await ani_info.get_poster()
            
            specific_channel_id = await db.get_anime_channel(ani_id)
            main_caption = await ani_info.get_caption()
            
            await asleep(1.5)
            stat_msg = await sendMessage(Var.FILE_STORE, f"‣ <b>Aɴɪᴍᴇ Nᴀᴍᴇ :</b>\n<blockquote><b><i>{name}</i></b></blockquote>\n\n<blockquote><i>Dᴏᴡɴʟᴏᴀᴅɪɴɢ....</i></blockquote>")
            dl = await TorDownloader("./downloads").download(torrent, name)
            is_moviebox_dl = False  # Flag to track if download came from MovieBox
            if not dl or not ospath.exists(dl):
                # === MovieBox Fallback ===
                try:
                    await bot.send_message(
                        chat_id=Var.LOG_CHANNEL,
                        text=f"<b>⚡ Torrent failed, trying MovieBox...</b>\n\n<b>• Anime:</b> <code>{name}</code>"
                    )
                except Exception as log_err:
                    LOGS.error(f"Failed to send torrent failed log: {log_err}")
                titles = ani_info.adata.get('title', {})
                clean_name = titles.get('english') or titles.get('romaji') or ''
                # Extract season and episode numbers
                fb_season = int(await ani_info.get_season())
                try:
                    ep_raw = ani_info.pdata.get('episode_number', '1')
                    fb_episode = int(ep_raw) if not isinstance(ep_raw, list) else int(ep_raw[-1])
                except (ValueError, TypeError):
                    fb_episode = 1
                fb_filename = f"moviebox_{clean_name.replace(' ', '_')}_S{fb_season}E{fb_episode}.mp4"
                
                fallback = MovieBoxFallback("./downloads")
                dl = await fallback.try_fallback(clean_name, fb_season, fb_episode, fb_filename, ani_id=ani_info.adata.get('id'))
                if dl and ospath.exists(dl):
                    is_moviebox_dl = True
                else:
                    await rep.report(f"File Download Incomplete (Torrent + MovieBox both failed)", "error", log=True)
                    await stat_msg.delete()
                    return
            # === Audio stream language verification layer ===
            from bot.core.audio_probe import has_hindi_audio
            if not await has_hindi_audio(dl):
                await rep.report(f"⚠️ Skipping: Downloaded file has no Hindi audio track! Filename: {ospath.basename(dl)}", "warning", log=True)
                try:
                    await bot.send_message(
                        chat_id=Var.LOG_CHANNEL,
                        text=f"<b>⚠️ Skipping Encode (No Hindi Audio Track)</b>\n\n<b>• Anime:</b> <code>{name}</code>\n<b>• Filename:</b> <code>{ospath.basename(dl)}</code>"
                    )
                except Exception:
                    pass
                try:
                    await aioremove(dl)
                except Exception:
                    pass
                await stat_msg.delete()
                return

            # Use unique task identifier for the lock queue
            post_id = f"{ani_id}_{ep_no}"
            
            # === Multi-Quality Encoding Flow ===
            ffEvent = Event()
            ff_queued[post_id] = ffEvent
            if ffLock.locked():
                await editMessage(stat_msg, f"‣ <b>Aɴɪᴍᴇ Nᴀᴍᴇ :</b>\n<blockquote><b><i>{name}</i></b></blockquote>\n\n<blockquote><i>Qᴜᴇᴜᴇᴅ ᴛᴏ Eɴᴄᴏᴅᴇ...</i></blockquote>")
                await rep.report("Aᴅᴅᴇᴅ Tᴀsᴋ ᴛᴏ Qᴜᴇᴜᴇ...", "info", log=True)
            await ffQueue.put(post_id)
            await ffEvent.wait()
            await ffLock.acquire()
            
            uploaded_qual_msg_ids = {}
            local_thumb = None
            
            # Download poster image for video thumbnail
            if photo_url:
                if ospath.exists(photo_url):
                    local_thumb = photo_url
                else:
                    try:
                        import os
                        os.makedirs("thumbs", exist_ok=True)
                        from bot.core.func_utils import aio_urldownload
                        local_thumb = await aio_urldownload(photo_url)
                    except Exception as e:
                        LOGS.error(f"Failed to download poster for thumbnail: {e}")
            
            for qual in Var.QUALS:
                filename = await ani_info.get_upname(qual)
                await editMessage(stat_msg, f"‣ <b>Aɴɪᴍᴇ Nᴀᴍᴇ :</b>\n<blockquote><b><i>{name}</i></b></blockquote>\n\n<blockquote><i>Rᴇᴀᴅʏ ᴛᴏ Eɴᴄᴏᴅᴇ...</i></blockquote>")
                await asleep(1.5)
                await rep.report("Sᴛᴀʀᴛɪɴɢ Eɴᴄᴏᴅᴇ...", "info", log=True)
                
                try:
                    out_path = await FFEncoder(stat_msg, dl, filename, qual).start_encode()
                except Exception as e:
                    await rep.report(f"Error: {e}, Cancelled, Retry Again !", "error", log=True)
                    await stat_msg.delete()
                    ffLock.release()
                    return
                
                await rep.report("Sᴜᴄᴄᴇsғᴜʟʟʏ Cᴏᴍᴘʀᴇssᴇᴅ Nᴏᴡ Gᴏɪɴɢ Tᴏ Uᴘʟᴏᴀᴅ...", "info", log=True)
                await editMessage(stat_msg, f"‣ <b>Aɴɪᴍᴇ Nᴀᴍᴇ :</b>\n<blockquote><b><i>{filename}</i></b></blockquote>\n\n<blockquote><i>Rᴇᴀᴅʏ ᴛᴏ Uᴘʟᴏᴀᴅ...</i></blockquote>")
                await asleep(1.5)
                
                try:
                    msg = await TgUploader(stat_msg).upload(out_path, qual, thumb=local_thumb)
                except Exception as e:
                    await rep.report(f"Error: {e}, Cancelled, Retry Again !", "error", log=True)
                    await stat_msg.delete()
                    ffLock.release()
                    return
                
                await rep.report("Sᴜᴄᴄᴇssғᴜʟʟʏ Uᴘʟᴏᴀᴅᴇᴅ Fɪʟᴇ ɪɴᴛᴏ Cʜᴀɴɴᴇʟ...", "info", log=True)
                msg_id = msg.id
                uploaded_qual_msg_ids[qual] = msg_id
                
                # Save progress to database immediately under file_msg_id
                await db.save_anime(ani_id, ep_no, qual, post_id=None, file_msg_id=msg_id)
                
                try:
                    await aioremove(out_path)
                except:
                    pass

            # Build quality button markups
            specific_btns = []
            main_btns = []
            
            for qual in Var.QUALS:
                m_id = uploaded_qual_msg_ids.get(qual)
                if m_id:
                    link = f"https://telegram.me/{(await bot.get_me()).username}?start={await encode('get-'+str(m_id * abs(Var.FILE_STORE)))}"
                    btn = InlineKeyboardButton(f"{btn_formatter[qual]}", url=link)
                    
                    if specific_channel_id:
                        if specific_btns and len(specific_btns[-1]) == 1:
                            specific_btns[-1].append(btn)
                        else:
                            specific_btns.append([btn])
                    else:
                        if main_btns and len(main_btns[-1]) == 1:
                            main_btns[-1].append(btn)
                        else:
                            main_btns.append([btn])

            # 1. Post to specific channel if mapped
            specific_post_msg = None
            if specific_channel_id:
                try:
                    if photo_url and ospath.exists(photo_url):
                        with open(photo_url, 'rb') as photo_file:
                            specific_post_msg = await bot.send_photo(
                                specific_channel_id,
                                photo=photo_file,
                                caption=main_caption,
                                reply_markup=InlineKeyboardMarkup(specific_btns) if specific_btns else None
                            )
                    else:
                        specific_post_msg = await bot.send_photo(
                            specific_channel_id,
                            photo=photo_url or "https://ibb.co/5xjBCXKp",
                            caption=main_caption,
                            reply_markup=InlineKeyboardMarkup(specific_btns) if specific_btns else None
                        )
                except Exception as e:
                    await rep.report(f"Failed to send to specific channel {specific_channel_id} for {name}: {str(e)}", "error", log=True)

            # 2. Setup main channel buttons (Watch button pointing directly to specific channel post if mapped)
            if specific_channel_id and specific_post_msg:
                try:
                    from helper_func import get_fsub_link
                    channel_invite = await get_fsub_link(bot, specific_channel_id)
                    spec_chat = await bot.get_chat(specific_channel_id)
                    if spec_chat.username:
                        watch_url = f"https://t.me/{spec_chat.username}/{specific_post_msg.id}"
                    else:
                        watch_url = f"https://t.me/c/{str(specific_channel_id)[4:]}/{specific_post_msg.id}"

                    main_btns = [
                        [
                            InlineKeyboardButton("• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •", url=channel_invite),
                            InlineKeyboardButton("• ᴡᴀᴛᴄʜ ᴀɴɪᴍᴇ •", url=watch_url)
                        ]
                    ]
                except Exception as e:
                    await rep.report(f"Failed to get invite link for channel {specific_channel_id}: {str(e)}", "warning", log=True)

            # 3. Post to main channel
            try:
                if photo_url and ospath.exists(photo_url):
                    with open(photo_url, 'rb') as photo_file:
                        main_post_msg = await bot.send_photo(
                            Var.MAIN_CHANNEL,
                            photo=photo_file,
                            caption=main_caption,
                            reply_markup=InlineKeyboardMarkup(main_btns) if main_btns else None
                        )
                else:
                    main_post_msg = await bot.send_photo(
                        Var.MAIN_CHANNEL,
                        photo=photo_url or "https://ibb.co/5xjBCXKp",
                        caption=main_caption,
                        reply_markup=InlineKeyboardMarkup(main_btns) if main_btns else None
                    )
            except Exception as e:
                await rep.report(f"Failed to send to main channel for {name}: {str(e)}", "error", log=True)
                ffLock.release()
                return

            # Save the final main channel post ID under msg_id/post_id in DB
            for qual in Var.QUALS:
                m_id = uploaded_qual_msg_ids.get(qual)
                if m_id:
                    await db.save_anime(
                        ani_id, ep_no, qual, 
                        post_id=main_post_msg.id, 
                        file_msg_id=m_id,
                        spec_post_id=specific_post_msg.id if specific_post_msg else None
                    )

            # Log a single combined summary to LOG_CHANNEL
            try:
                source_str = "Manual Command / Sync" if force else "Auto-Sync Feed"
                qualities_str = ", ".join(uploaded_qual_msg_ids.keys())
                log_text = f"""<b>📥 New Video Uploaded (Multi-Quality)</b>
<b>• Anime:</b> <code>{name}</code>
<b>• Episode:</b> <code>{ep_no}</code>
<b>• Qualities:</b> <code>{qualities_str}</code>
<b>• Source:</b> <code>{source_str}</code>
<b>• Torrent Link:</b> <a href="{torrent}">Click Here</a>
<b>• Main Post ID:</b> <code>{main_post_msg.id}</code>"""
                await bot.send_message(chat_id=Var.LOG_CHANNEL, text=log_text, disable_web_page_preview=True)
            except Exception as log_err:
                LOGS.error(f"Failed to send log message to LOG_CHANNEL: {log_err}")

            # Send sticker
            sticker_id = await db.get_sticker()
            if sticker_id:
                try:
                    await bot.send_sticker(Var.MAIN_CHANNEL, sticker=sticker_id)
                    await rep.report(f"Sticker {sticker_id} sent to main channel for {name}", "info", log=True)
                    if specific_channel_id and specific_post_msg:
                        await bot.send_sticker(specific_channel_id, sticker=sticker_id)
                        await rep.report(f"Sticker {sticker_id} sent to specific channel {specific_channel_id} for {name}", "info", log=True)
                except Exception as e:
                    await rep.report(f"Failed to send sticker {sticker_id}: {str(e)}", "error", log=True)
            
            ffLock.release()
            await stat_msg.delete()
            await aioremove(dl)
        else:
            await rep.report(f"Anime {name} already processed or completed", "info", log=True)
    except Exception as error:
        await rep.report(f"Error in get_animes for {name}: {format_exc()}", "error", log=True)
        return
    finally:
        if is_priority:
            active_priority_tasks.discard(task_key)
        if ani_id:
            ani_cache['completed'].add(ani_id)
        if local_thumb and local_thumb != Var.CUSTOM_BANNER and not local_thumb.startswith("thumb.jpg") and ospath.exists(local_thumb):
            try:
                import os
                os.remove(local_thumb)
            except Exception:
                pass

async def extra_utils(msg_id, out_path):
    msg = await bot.get_messages(Var.FILE_STORE, message_ids=msg_id)
    if Var.BACKUP_CHANNEL != 0:
        for chat_id in str(Var.BACKUP_CHANNEL).split():
            await msg.copy(int(chat_id))
