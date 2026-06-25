from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.core.bot_instance import bot, bot_loop
from bot.core.auto_animes import get_animes
from helper_func import admin
import urllib.parse
import feedparser
import asyncio
import hashlib

# Simple in-memory cache for search results: {hash: {'title': title, 'link': link}}
search_cache = {}

def parse_rss(url):
    return feedparser.parse(url)

@bot.on_message(filters.command("post") & filters.private & admin)
async def search_anime_nyaa(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("<b>Usage:</b> <code>/post One Piece 1000</code>")
    
    query = " ".join(message.command[1:])
    encoded_query = urllib.parse.quote(query)
    # Nyaa RSS - Filter: Trusted Only (2), Category: Anime - English-translated (1_2)
    rss_url = f"https://nyaa.si/?page=rss&q={encoded_query}&c=1_2&f=0"
    
    msg = await message.reply("<i>Searching Nyaa...</i>")
    
    feed = await asyncio.get_event_loop().run_in_executor(None, parse_rss, rss_url)
    
    if not feed.entries:
        return await msg.edit(f"<b>No results found for:</b> <code>{query}</code>")
    
    buttons = []
    # Limit to top 8 results
    for entry in feed.entries[:8]:
        title = entry.title
        link = entry.link
        
        # Create unique hash for this entry to use in callback
        entry_id = hashlib.md5(link.encode()).hexdigest()[:10]
        search_cache[entry_id] = {'title': title, 'link': link}
        
        # Truncate title for button visibility
        display_title = (title[:40] + '..') if len(title) > 40 else title
        
        # Callback format: up_nyaa|HASH
        buttons.append([InlineKeyboardButton(f"⬆️ {display_title}", callback_data=f"up_nyaa|{entry_id}")])

    await msg.edit(
        f"<b>Found {len(feed.entries)} results for:</b> <code>{query}</code>\nSelect one to upload:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@bot.on_callback_query(filters.regex(r"^up_nyaa\|"))
async def upload_nyaa_callback(client: Client, callback: CallbackQuery):
    entry_id = callback.data.split("|")[1]
    
    entry = search_cache.get(entry_id)
    if not entry:
        return await callback.answer("Link expired or not found in cache!", show_alert=True)
    
    title = entry['title']
    link = entry['link']
    
    await callback.answer("Starting Upload...", show_alert=False)
    await callback.message.edit(f"<b>Starting Upload for:</b>\n<code>{title}</code>")
    
    # Trigger the download/encode/upload process
    # force=True ensures we process it even if it was done before
    bot_loop.create_task(get_animes(title, link, force=True))

@bot.on_message(filters.command("sync") & filters.private & admin)
async def manual_sync_anime(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("<b>Usage:</b> <code>/sync Anime Name</code>")
    
    anime_title = " ".join(message.command[1:])
    msg = await message.reply(f"<i>Manual Auto-Sync triggered for: {anime_title}...</i>")
    
    # Run the sync logic in the background
    asyncio.create_task(run_manual_sync(anime_title, msg))

async def run_manual_sync(anime_title, msg):
    from bot.core.func_utils import get_all_feed_entries
    from bot.core.database import db
    from bot.core.text_utils import TextEditor
    from config import Var
    
    # 1. Search Nyaa.si for [Anime Name] Hindi
    query = f"{anime_title} Hindi"
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://nyaa.si/?page=rss&q={encoded_query}&c=1_2&f=0"
    
    entries = await get_all_feed_entries(rss_url)
    if not entries:
        await msg.edit(f"❌ No Hindi episodes found on Nyaa.si for: <code>{anime_title}</code>")
        return
        
    # Filter and match titles to ensure they match the requested anime title
    found_episodes = []
    for entry in entries:
        if "hindi" not in entry.title.lower():
            continue
        entry_info = TextEditor(entry.title)
        entry_title = entry_info.pdata.get("anime_title")
        
        # Simple match check
        if entry_title and (anime_title.lower() in entry_title.lower() or entry_title.lower() in anime_title.lower()):
            try:
                ep_val = float(entry_info.pdata.get("episode_number"))
                ep_str = entry_info.pdata.get("episode_number")
                found_episodes.append((ep_val, ep_str, entry.title, entry.link, entry_info))
            except (TypeError, ValueError):
                continue
                
    if not found_episodes:
        await msg.edit(f"❌ No matching episodes found for: <code>{anime_title}</code>")
        return
        
    found_episodes.sort(key=lambda x: x[0])
    
    await msg.edit(f"✅ Found {len(found_episodes)} episodes for <code>{anime_title}</code>. Starting database check...")
    
    # Load first anime ID to fetch database
    first_info = found_episodes[0][4]
    await first_info.load_anilist()
    ani_id = first_info.adata.get('id')
    
    if not ani_id:
        await msg.edit(f"❌ Failed to fetch AniList ID for: <code>{anime_title}</code>")
        return
        
    ani_data = await db.get_anime(ani_id)
    
    synced_count = 0
    skipped_count = 0
    
    for ep_val, ep_str, ep_title, ep_link, _ in found_episodes:
        qual_data = ani_data.get(ep_str) if ani_data else None
        
        # Check if all qualities are uploaded
        if not ani_data or not qual_data or not all(qual_data.get(qual) for qual in Var.QUALS):
            synced_count += 1
            # Trigger download
            asyncio.create_task(get_animes(ep_title, ep_link, force=True))
        else:
            skipped_count += 1
            
    await msg.edit(f"📊 <b>Sync report for {anime_title}:</b>\n- Synced/Queued: {synced_count} episode(s)\n- Skipped (already in DB): {skipped_count} episode(s)")


# --- BACKGROUND SYNC QUEUE COMMANDS ---

from bot.core.database import db

active_qadd_sessions = {}

async def in_qadd_session_filter(_, __, message: Message):
    return message.from_user and message.from_user.id in active_qadd_sessions

qadd_session_filter = filters.create(in_qadd_session_filter)

@bot.on_message(filters.private & admin & qadd_session_filter & filters.text & ~filters.regex(r"^/"))
async def handle_qadd_input(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    if not text:
        return
    
    # Split by newlines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if not lines:
        return
        
    added_names = []
    for line in lines:
        if line not in active_qadd_sessions[user_id]:
            active_qadd_sessions[user_id].append(line)
            added_names.append(line)
            
    if len(lines) == 1:
        await message.reply(f"✅ Added: <code>{lines[0]}</code>\nTotal in session: <b>{len(active_qadd_sessions[user_id])}</b>\nSend another, or send /done to save.")
    else:
        added_list = "\n".join([f"• <code>{name}</code>" for name in added_names])
        await message.reply(f"✅ Added {len(added_names)} anime(s):\n{added_list}\n\nTotal in session: <b>{len(active_qadd_sessions[user_id])}</b>\nSend another, or send /done to save.")

@bot.on_message(filters.command("qadd") & filters.private & admin)
async def qadd_command(client: Client, message: Message):
    user_id = message.from_user.id
    active_qadd_sessions[user_id] = []
    await message.reply(
        "📥 <b>Queue-Adding Session Started!</b>\n\n"
        "Please send the names of the anime one-by-one, or paste a newline-delimited list of names.\n\n"
        "Send /done when you are finished."
    )

@bot.on_message(filters.command("done") & filters.private & admin)
async def done_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in active_qadd_sessions:
        return await message.reply("⚠️ No active queue-adding session. Send /qadd to start one.")
        
    anime_list = active_qadd_sessions.pop(user_id)
    if not anime_list:
        return await message.reply("⚠️ No anime names were added. Session closed.")
        
    added_count = 0
    skipped_count = 0
    for name in anime_list:
        success = await db.add_to_queue(name)
        if success:
            added_count += 1
        else:
            skipped_count += 1
            
    await message.reply(
        f"📊 <b>Queue Session Closed & Saved!</b>\n"
        f"- Added to queue: <b>{added_count}</b> new anime(s)\n"
        f"- Skipped (already in queue/processing): <b>{skipped_count}</b> anime(s)"
    )

@bot.on_message(filters.command("qlist") & filters.private & admin)
async def qlist_command(client: Client, message: Message):
    tasks = await db.get_all_queue_tasks()
    if not tasks:
        return await message.reply("📭 The sync queue is currently empty.")
        
    processing = []
    pending = []
    completed = []
    failed = []
    
    for task in tasks:
        status = task.get('status', 'pending')
        name = task.get('anime_name')
        if status == 'processing':
            processing.append(name)
        elif status == 'pending':
            pending.append(name)
        elif status == 'completed':
            completed.append(name)
        elif status == 'failed':
            failed.append(name)
            
    report = "📋 <b>Sync Queue List</b>\n\n"
    
    if processing:
        report += "🔄 <b>Processing:</b>\n"
        report += "\n".join([f"• <code>{name}</code>" for name in processing]) + "\n\n"
        
    if pending:
        report += f"⏳ <b>Pending ({len(pending)}):</b>\n"
        report += "\n".join([f"• <code>{name}</code>" for name in pending]) + "\n\n"
        
    if completed:
        report += f"✅ <b>Completed ({len(completed)}):</b>\n"
        report += "\n".join([f"• <code>{name}</code>" for name in completed[-5:]])
        if len(completed) > 5:
            report += f"\n<i>... and {len(completed) - 5} more completed.</i>"
        report += "\n\n"
        
    if failed:
        report += f"❌ <b>Failed ({len(failed)}):</b>\n"
        report += "\n".join([f"• <code>{name}</code>" for name in failed[-5:]])
        if len(failed) > 5:
            report += f"\n<i>... and {len(failed) - 5} more failed.</i>"
        report += "\n"
        
    await message.reply(report)

@bot.on_message(filters.command("qclear") & filters.private & admin)
async def qclear_command(client: Client, message: Message):
    deleted_count = await db.clear_pending_queue()
    await message.reply(f"🗑️ <b>Cleared all pending tasks!</b>\nRemoved <b>{deleted_count}</b> pending task(s) from the sync queue.")
