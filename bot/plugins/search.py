from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.core.bot_instance import bot
from bot.core.database import db
from bot.core.text_utils import TextEditor
from helper_func import encode

@bot.on_message(filters.command("search"))
async def search_anime_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /search <anime_name>")
    
    query = " ".join(message.command[1:])
    m = await message.reply("Searching...")
    
    try:
        # 1. Search Anilist to get ID
        te = TextEditor(query)
        await te.load_anilist()
        ani_id = te.adata.get('id')
        
        if not ani_id:
            return await m.edit("Anime not found on AniList.")
        
        title = te.adata.get('title', {}).get('romaji', query)
        
        # 2. Search DB
        anime_data = await db.get_anime(ani_id) # returns episodes dict
        if not anime_data:
            return await m.edit(f"No episodes found in database for <b>{title}</b>.")
            
        # 3. Format result
        buttons = []
        # eps is a dict: "1": {"1080": T/F...}, "2": ...
        # Sort by episode number
        def safe_float(x):
            try:
                return float(x)
            except:
                return 9999
        sorted_eps = sorted(anime_data.keys(), key=safe_float)
        
        # Batch Collection
        all_msg_ids = []
        
        # Create Episode Buttons (Grid of 4)
        ep_buttons_grid = []
        row = []
        for ep in sorted_eps:
            ep_info = anime_data[ep]
            
            # Collect IDs for batch
            ids = ep_info.get("ids", {})
            if ids:
                for q, mid in ids.items():
                    if mid:
                        all_msg_ids.append(mid)
            
            # For specific episode button, we need a link too.
            # We can use the SAME batch logic but for single episode? 
            # OR use the 'get-MSGID' logic existing in start.py.
            # Use the "Highest Quality" available for the direct button?
            # Or make the button open a menu?
            # For simplicity: Button -> "get-MSGID" of highest quality.
            
            if ids:
                # Find best quality
                best_mid = None
                for q in ["1080", "720", "480", "360", "HDRip"]: # Priority order
                    if q in ids:
                        best_mid = ids[q]
                        break
                if not best_mid and ids:
                    best_mid = list(ids.values())[0]
                    
                if best_mid:
                    # encode payload: get-MSGID * FILE_STORE... no wait.
                    # start.py logic: 'get-FILEID' implies FILEID = MSGID * abs(FILE_STORE)
                    # We need Var.FILE_STORE.
                    from config import Var
                    # Verify FILE_STORE is int
                    file_store_id = int(Var.FILE_STORE)
                    payload = f"get-{best_mid * abs(file_store_id)}"
                    b64_payload = await encode(payload)
                    me = await client.get_me()
                    link = f"https://t.me/{me.username}?start={b64_payload}"
                    
                    row.append(InlineKeyboardButton(f"{ep}", url=link))
            
            if len(row) == 4:
                ep_buttons_grid.append(row)
                row = []
        
        if row:
            ep_buttons_grid.append(row)
            
        buttons.extend(ep_buttons_grid)
        
        # Add Batch Button
        if all_msg_ids:
            # Create a batch
            batch_id = await db.create_batch(all_msg_ids)
            if batch_id:
                me = await client.get_me()
                link = f"https://t.me/{me.username}?start=batch-{batch_id}"
                buttons.append([InlineKeyboardButton("📦 Download Full Season (Batch)", url=link)])
            
        await m.edit(f"<b>Anime Found:</b> {title}\n\nSelect an episode or download full season:", reply_markup=InlineKeyboardMarkup(buttons))
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        await m.edit(f"Error: {e}")
