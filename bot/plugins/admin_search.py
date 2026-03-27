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
