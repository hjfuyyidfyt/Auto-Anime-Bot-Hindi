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
from bot.core.bot_instance import bot, bot_loop, ani_cache, ffQueue, ffLock, ff_queued
from .tordownload import TorDownloader
from .database import db
from .func_utils import getfeed, encode, editMessage, sendMessage, convertBytes
from .text_utils import TextEditor
from .ffencoder import FFEncoder
from .tguploader import TgUploader
from .reporter import rep

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
        await message.reply_text("❗ Usage:\n<code>/addrss https://example.com/rss</code>")
        await rep.report("Invalid /addrss command: Missing URL", "error", log=True)
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
    feeds = list(ani_cache.get("custom_rss", []))
    if not feeds:
        await message.reply_text("⚠️ No custom RSS links added yet.")
        await rep.report("No custom RSS links found.", "warning", log=True)
    else:
        await message.reply_text("📡 Custom RSS Feeds:\n" + "\n".join([f"• {f}" for f in feeds]))
        await rep.report("Listed custom RSS feeds.", "info", log=True)

@bot.on_message(filters.command("remove_rss") & filters.user(Var.ADMINS))
async def remove_rss(client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("❗ Usage:\n<code>/removerss https://example.com/rss</code>")
        await rep.report("Invalid /removerss command: Missing URL", "error", log=True)
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
        await message.reply_text("<u>Usᴇ ɪᴛ ʟɪᴋᴇ ᴛʜɪs</u> : \n<blockquote expandable>/setchannel <ᴀɴɪᴍᴇ_ɴᴀᴍᴇ> <ᴄʜᴀɴɴᴇʟ_ɪᴅ></blockquote>")
        await rep.report("<blockquote>Iɴᴠᴀʟɪᴅ /setchannel ᴄᴏᴍᴍᴀɴᴅ: Mɪssɪɴɢ ᴀɴɪᴍᴇ ɴᴀᴍᴇ ᴏʀ ᴄʜᴀɴɴᴇʟ ID</blockquote>", "error", log=True)
        return

    anime_name = " ".join(message.command[1:-1])
    try:
        channel_id = int(message.command[-1])
    except ValueError:
        await message.reply_text("⚠️ Iɴᴠᴀʟɪᴅ ᴄʜᴀɴɴᴇʟ ID. Pʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ɴᴜᴍᴇʀɪᴄ ᴄʜᴀᴛ ID.")
        await rep.report(f"⚠️ Iɴᴠᴀʟɪᴅ ᴄʜᴀɴɴᴇʟ ID {message.command[-1]}", "error", log=True)
        return

    ani_info = TextEditor(anime_name)
    await ani_info.load_anilist()
    ani_id = ani_info.adata.get('id')

    if not ani_id:
        await message.reply_text(f"⚠️ Aɴɪᴍᴇ ɴᴏᴛ ғᴏᴜɴᴅ : {anime_name}")
        await rep.report(f"⚠️ Aɴɪᴍᴇ ɴᴏᴛ ғᴏᴜɴᴅ : {anime_name}", "error", log=True)
        return

    await db.set_anime_channel(ani_id, channel_id)
    await message.reply_text(f"<b><blockquote>✅ <u>Aɴɪᴍᴇ</u> : {anime_name} \n<u>Iᴅ</u> : {ani_id} Sᴜᴄᴄᴇssғᴜʟʟʏ sᴇᴛ ᴛᴏ ᴄʜᴀɴɴᴇʟ {channel_id}</blockquote></b>")
    await rep.report(f"Anime {anime_name} (ID: {ani_id}) set to channel {channel_id}", "info", log=True)

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
            await message.reply_text("⚠️ Nᴏ ᴀɴɪᴍᴇ ᴄʜᴀɴɴᴇʟs ᴍᴀᴘᴘᴇᴅ ʏᴇᴛ.")
            await rep.report("Nᴏ ᴀɴɪᴍᴇ ᴄʜᴀɴɴᴇʟs ᴍᴀᴘᴘᴇᴅ ʏᴇT.", "warning", log=True)
            return

        response = "• Aɴɪᴍᴇ ᴄʜᴀɴɴᴇʟ ᴍᴀᴘᴘɪɴɢ :\n\n"
        for mapping in mappings:
            ani_id = mapping["ani_id"]
            channel_id = mapping["channel_id"]
            try:
                ani_info = TextEditor(f"id:{ani_id}")
                await ani_info.load_anilist()
                anime_name = ani_info.adata.get('title', {}).get('romaji', f"Unknown (ID: {ani_id})")
                response += f"• {anime_name}: {channel_id}\n"
            except Exception as e:
                await rep.report(f"Failed to fetch anime name for ani_id={ani_id}: {str(e)}", "error", log=True)
                response += f"• Unknown (ID: {ani_id}): {channel_id}\n"

        await message.reply_text(response)
        await rep.report(f"Listed {len(mappings)} anime channel mappings", "info", log=True)
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

async def get_animes(name, torrent, force=False):
    try:
        ani_info = TextEditor(name)
        await ani_info.load_anilist()
        ani_id, ep_no = ani_info.adata.get('id'), ani_info.pdata.get("episode_number")
        if not ani_id or not ep_no:
            await rep.report(f"Invalid anime data for {name}: ID or episode number missing", "error", log=True)
            return
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
            
            # Send to main channel
            if photo_url and ospath.exists(photo_url):
                with open(photo_url, 'rb') as photo_file:
                    main_post_msg = await bot.send_photo(
                        Var.MAIN_CHANNEL,
                        photo=photo_file,
                        caption=main_caption
                    )
            else:
                main_post_msg = await bot.send_photo(
                    Var.MAIN_CHANNEL,
                    photo=photo_url or "https://ibb.co/5xjBCXKp",
                    caption=main_caption
                )
            
            # Send to specific channel if mapped
            specific_post_msg = None
            if specific_channel_id:
                try:
                    if photo_url and ospath.exists(photo_url):
                        with open(photo_url, 'rb') as photo_file:
                            specific_post_msg = await bot.send_photo(
                                specific_channel_id,
                                photo=photo_file,
                                caption=main_caption
                            )
                    else:
                        specific_post_msg = await bot.send_photo(
                            specific_channel_id,
                            photo=photo_url or "https://ibb.co/5xjBCXKp",
                            caption=main_caption
                        )
                except Exception as e:
                    await rep.report(f"Failed to send to specific channel {specific_channel_id} for {name}: {str(e)}", "error", log=True)
            
            await asleep(1.5)
            stat_msg = await sendMessage(Var.MAIN_CHANNEL, f"‣ <b>Aɴɪᴍᴇ Nᴀᴍᴇ :</b>\n<blockquote><b><i>{name}</i></b></blockquote>\n\n<blockquote><i>Dᴏᴡɴʟᴏᴀᴅɪɴɢ....</i></blockquote>")
            dl = await TorDownloader("./downloads").download(torrent, name)
            if not dl or not ospath.exists(dl):
                await rep.report(f"File Download Incomplete, Try Again", "error", log=True)
                await stat_msg.delete()
                return
            
            post_id = main_post_msg.id
            ffEvent = Event()
            ff_queued[post_id] = ffEvent
            if ffLock.locked():
                await editMessage(stat_msg, f"‣ <b>Aɴɪᴍᴇ Nᴀᴍᴇ :</b>\n<blockquote><b><i>{name}</i></b></blockquote>\n\n<blockquote><i>Qᴜᴇᴜᴇᴅ ᴛᴏ Eɴᴄᴏᴅᴇ...</i></blockquote>")
                await rep.report("Aᴅᴅᴇᴅ Tᴀsᴋ ᴛᴏ Qᴜᴇᴜᴇ...", "info", log=True)
            await ffQueue.put(post_id)
            await ffEvent.wait()
            await ffLock.acquire()
            
            main_btns = []
            specific_btns = []
            
            # Initialize main channel buttons with Join Channel and Watch if specific channel exists
            if specific_channel_id:
                try:
                    channel_invite = await bot.export_chat_invite_link(specific_channel_id)
                    main_btns.append([
                        InlineKeyboardButton("• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •", url=channel_invite),
                        InlineKeyboardButton("• ᴡᴀᴛᴄʜ ᴀɴɪᴍᴇ •", url=f"https://t.me/c/{str(specific_channel_id)[4:]}/{specific_post_msg.id if specific_post_msg else 0}")
                    ])
                    await editMessage(main_post_msg, main_post_msg.caption.html if main_post_msg.caption else "", InlineKeyboardMarkup(main_btns))
                except Exception as e:
                    await rep.report(f"Failed to get invite link for channel {specific_channel_id}: {str(e)}", "warning", log=True)
            
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
                    msg = await TgUploader(stat_msg).upload(out_path, qual)
                except Exception as e:
                    await rep.report(f"Error: {e}, Cancelled, Retry Again !", "error", log=True)
                    await stat_msg.delete()
                    ffLock.release()
                    return
                
                await rep.report("Sᴜᴄᴄᴇssғᴜʟʟʏ Uᴘʟᴏᴀᴅᴇᴅ Fɪʟᴇ ɪɴᴛᴏ Cʜᴀɴɴᴇʟ...", "info", log=True)
                msg_id = msg.id
                link = f"https://telegram.me/{(await bot.get_me()).username}?start={await encode('get-'+str(msg_id * abs(Var.FILE_STORE)))}"
                
                # Only add quality buttons to specific channel if mapped, otherwise to main channel
                if specific_channel_id:
                    if specific_btns and len(specific_btns[-1]) == 1:
                        specific_btns[-1].insert(1, InlineKeyboardButton(f"{btn_formatter[qual]}", url=link))
                    else:
                        specific_btns.append([InlineKeyboardButton(f"{btn_formatter[qual]}", url=link)])
                    # Update specific channel post immediately
                    if specific_post_msg:
                        await editMessage(specific_post_msg, specific_post_msg.caption.html if specific_post_msg.caption else "", InlineKeyboardMarkup(specific_btns))
                        # Update main channel with Watch button pointing to specific channel post
                        main_btns[0][1] = InlineKeyboardButton("• ᴡᴀᴛᴄʜ ᴀɴɪᴍᴇ •", url=f"https://t.me/c/{str(specific_channel_id)[4:]}/{specific_post_msg.id}")
                        await editMessage(main_post_msg, main_post_msg.caption.html if main_post_msg.caption else "", InlineKeyboardMarkup(main_btns))
                else:
                    if main_btns and len(main_btns[-1]) == 1:
                        main_btns[-1].insert(1, InlineKeyboardButton(f"{btn_formatter[qual]}", url=link))
                    else:
                        main_btns.append([InlineKeyboardButton(f"{btn_formatter[qual]}", url=link)])
                    # Update main channel post immediately
                    await editMessage(main_post_msg, main_post_msg.caption.html if main_post_msg.caption else "", InlineKeyboardMarkup(main_btns))
                
                await db.save_anime(ani_id, ep_no, qual, post_id, file_msg_id=msg_id)
            
            # Remove final main channel update since buttons are updated incrementally
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
        if ani_id:
            ani_cache['completed'].add(ani_id)

async def extra_utils(msg_id, out_path):
    msg = await bot.get_messages(Var.FILE_STORE, message_ids=msg_id)
    if Var.BACKUP_CHANNEL != 0:
        for chat_id in str(Var.BACKUP_CHANNEL).split():
            await msg.copy(int(chat_id))
