import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatMemberStatus, ChatType
from bot.core.bot_instance import bot, ani_cache
from bot.core.database import db
from bot.core.text_utils import TextEditor, get_anime_by_id, CAPTION_FORMAT, GENRES_EMOJI
from helper_func import admin, encode, get_fsub_link
from config import Var, LOGS

logger = logging.getLogger(__name__)

btn_formatter = {'480': '480p HEVC', '720': '720p HEVC', '1080': '1080p HEVC', 'HDRip': 'HDRip'}

@bot.on_message(filters.command(['repost', 'rebuild']) & filters.private & admin)
async def repost_cmd(client: Client, message: Message):
    mappings = await db.get_all_anime_channels()
    if not mappings:
        return await message.reply("❌ <b>No mapped anime channels found!</b>")

    buttons = []
    for m in mappings:
        ani_id = m.get('ani_id')
        name = m.get('anime_name')
        if not name or name.startswith("ID:"):
            anime_data = await get_anime_by_id(ani_id)
            if anime_data:
                titles = anime_data.get('title', {})
                name = titles.get('english') or titles.get('romaji') or f"ID: {ani_id}"
            else:
                name = f"ID: {ani_id}"
        buttons.append([InlineKeyboardButton(f"🎬 {name[:40]}", callback_data=f"rp_sel_{ani_id}")])
    
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close")])
    await message.reply("⚡ <b>Choose the anime you want to repost/reorder:</b>", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex(r"^rp_back$"))
async def rp_back_query(client: Client, query: CallbackQuery):
    mappings = await db.get_all_anime_channels()
    if not mappings:
        return await query.message.edit_text("❌ <b>No mapped anime channels found!</b>")

    buttons = []
    for m in mappings:
        ani_id = m.get('ani_id')
        name = m.get('anime_name')
        if not name or name.startswith("ID:"):
            anime_data = await get_anime_by_id(ani_id)
            if anime_data:
                titles = anime_data.get('title', {})
                name = titles.get('english') or titles.get('romaji') or f"ID: {ani_id}"
            else:
                name = f"ID: {ani_id}"
        buttons.append([InlineKeyboardButton(f"🎬 {name[:40]}", callback_data=f"rp_sel_{ani_id}")])
    
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close")])
    await query.message.edit_text("⚡ <b>Choose the anime you want to repost/reorder:</b>", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex(r"^rp_sel_(\d+)$"))
async def rp_select_query(client: Client, query: CallbackQuery):
    ani_id = query.data.split("_")[2]
    buttons = [
        [InlineKeyboardButton("1 Post per Episode (Default)", callback_data=f"rp_sty_{ani_id}_def")],
        [InlineKeyboardButton("1 Post per Season (New Style)", callback_data=f"rp_sty_{ani_id}_new")],
        [InlineKeyboardButton("⬅️ Back", callback_data="rp_back"), InlineKeyboardButton("❌ Cancel", callback_data="close")]
    ]
    await query.message.edit_text(f"✨ <b>Select repost style for ID:</b> <code>{ani_id}</code>", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex(r"^rp_sty_(\d+)_(\w+)$"))
async def rp_style_query(client: Client, query: CallbackQuery):
    ani_id = int(query.data.split("_")[2])
    style = query.data.split("_")[3]

    await query.answer("🔄 Rebuilding channel posts...", show_alert=False)
    await query.message.edit_text(f"⏳ <b>Processing repost for ID {ani_id}... Please wait.</b>")

    # Resolve/build timeline cache first to ensure we know all related seasons
    from bot.core.text_utils import get_absolute_season_by_relations
    timeline_doc = await db.timelines.find_one({'related_ids': ani_id})
    if not timeline_doc:
        await get_absolute_season_by_relations(ani_id)
        timeline_doc = await db.timelines.find_one({'related_ids': ani_id})

    mapping = await db.anime_channels.find_one({'ani_id': ani_id})
    if not mapping:
        lookup_id = timeline_doc.get('_id') if timeline_doc else ani_id
        mapping = await db.anime_channels.find_one({'ani_id': lookup_id})
        if not mapping:
            return await query.message.edit_text("❌ <b>Anime mapping not found in database!</b>")

    channel_id = mapping.get('channel_id')
    anime_name = mapping.get('anime_name') or "N/A"

    # Get all related IDs in the timeline
    related_ids = timeline_doc.get('related_ids') if timeline_doc else [ani_id]
    timeline_nodes = timeline_doc.get('timeline_nodes', []) if timeline_doc else []
    season_map = {node.get('id'): node.get('absolute_season', 1) for node in timeline_nodes}

    # Collect episodes from all related seasons
    episodes_list = []
    for rid in related_ids:
        ep_dict = await db.get_anime(rid)
        if ep_dict:
            s_no = season_map.get(rid, 1)
            for ep_str, ep_data in ep_dict.items():
                try:
                    ep_val = float(ep_str)
                    episodes_list.append({
                        'ep_no': ep_val,
                        'ep_str': ep_str,
                        'ep_data': ep_data,
                        'orig_ani_id': rid,
                        'season_no': s_no
                    })
                except (ValueError, TypeError):
                    continue

    if not episodes_list:
        return await query.message.edit_text("❌ <b>No episode file records found for this anime series!</b>")

    # 1. DELETE OLD POSTS IF SAVED
    # Delete season card if New Style was used previously
    old_season_posts = mapping.get('season_posts', {})
    if old_season_posts:
        for s_num, msg_id in old_season_posts.items():
            try:
                await client.delete_messages(chat_id=channel_id, message_ids=int(msg_id))
            except Exception:
                pass
        await db.anime_channels.update_one({'ani_id': mapping['ani_id']}, {'$unset': {'season_posts': ''}})

    old_main_season_posts = mapping.get('main_season_posts', {})
    if old_main_season_posts:
        for s_num, msg_id in old_main_season_posts.items():
            try:
                await client.delete_messages(chat_id=Var.MAIN_CHANNEL, message_ids=int(msg_id))
            except Exception:
                pass
        await db.anime_channels.update_one({'ani_id': mapping['ani_id']}, {'$unset': {'main_season_posts': ''}})

    # Delete episode posts if Default Style was used previously
    for ep_item in episodes_list:
        old_spec_msg_id = ep_item['ep_data'].get('spec_post_id')
        if old_spec_msg_id:
            try:
                await client.delete_messages(chat_id=channel_id, message_ids=int(old_spec_msg_id))
            except Exception:
                pass
        old_main_msg_id = ep_item['ep_data'].get('post_id')
        if old_main_msg_id:
            try:
                await client.delete_messages(chat_id=Var.MAIN_CHANNEL, message_ids=int(old_main_msg_id))
            except Exception:
                pass

    # 2. REPOST ACCORDING TO SELECTED STYLE
    if style == "def":
        # DEFAULT STYLE: 1 Post per Episode
        # Sort episodes by season number first, then episode number (chronologically)
        episodes_list.sort(key=lambda x: (x['season_no'], x['ep_no']))
        count = 0
        for ep_item in episodes_list:
            ep_str = ep_item['ep_str']
            ep_data = ep_item['ep_data']
            orig_ani_id = ep_item['orig_ani_id']

            # Fetch metadata for this specific season
            orig_adata = await get_anime_by_id(orig_ani_id)
            if not orig_adata:
                continue

            orig_editor = TextEditor(anime_name)
            orig_editor.adata = orig_adata

            # Get correct season string
            ep_season_str = await orig_editor.get_season()

            # Format caption dynamically
            ep_editor = TextEditor(f"{anime_name} - S{ep_season_str}E{ep_str}")
            ep_editor.adata = orig_adata
            ep_editor.pdata = {"anime_title": anime_name, "anime_season": ep_season_str, "episode_number": ep_str}
            caption = await ep_editor.get_caption()

            photo_url = f"https://img.anili.st/media/{orig_ani_id}"

            # Build quality buttons for specified channel
            specific_btns = []
            row = []
            for qual in Var.QUALS:
                m_id = ep_data.get('ids', {}).get(qual)
                if m_id:
                    link = f"https://telegram.me/{(await bot.get_me()).username}?start={await encode('get-'+str(m_id * abs(Var.FILE_STORE)))}"
                    btn = InlineKeyboardButton(f"{btn_formatter[qual]}", url=link)
                    row.append(btn)
                    if len(row) == 2:
                        specific_btns.append(row)
                        row = []
            if row:
                specific_btns.append(row)

            # Repost to specified channel
            try:
                msg = await client.send_photo(
                    chat_id=channel_id,
                    photo=photo_url,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(specific_btns) if specific_btns else None
                )
                
                # If specified channel is different from main channel, also post to main channel with watch redirect buttons
                main_msg = None
                if int(channel_id) != int(Var.MAIN_CHANNEL):
                    main_btns = []
                    try:
                        from helper_func import get_fsub_link
                        channel_invite = await get_fsub_link(bot, channel_id)
                        spec_chat = await bot.get_chat(channel_id)
                        if spec_chat.username:
                            watch_url = f"https://t.me/{spec_chat.username}/{msg.id}"
                        else:
                            watch_url = f"https://t.me/c/{str(channel_id)[4:]}/{msg.id}"
                        main_btns = [[
                            InlineKeyboardButton("• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •", url=channel_invite),
                            InlineKeyboardButton("• ᴡᴀᴛᴄʜ ᴀɴɪᴍᴇ •", url=watch_url)
                        ]]
                    except Exception as e:
                        logger.error(f"Failed to build main channel buttons: {e}")
                    
                    try:
                        main_msg = await client.send_photo(
                            chat_id=Var.MAIN_CHANNEL,
                            photo=photo_url,
                            caption=caption,
                            reply_markup=InlineKeyboardMarkup(main_btns) if main_btns else None
                        )
                    except Exception as e:
                        logger.error(f"Failed to post to main channel: {e}")

                # Save the new spec_post_id and post_id in DB under the original ID
                for qual in Var.QUALS:
                    m_id = ep_data.get('ids', {}).get(qual)
                    if m_id:
                        await db.save_anime(
                            orig_ani_id, ep_str, qual, 
                            file_msg_id=m_id, 
                            spec_post_id=msg.id,
                            post_id=main_msg.id if main_msg else None
                        )
                count += 1
            except Exception as e:
                logger.error(f"Failed to repost episode {ep_str} for ID {orig_ani_id}: {e}")

        await query.message.edit_text(f"✅ <b>Successfully reposted {count} episodes!</b>")

    else:
        # NEW STYLE: 1 Post per Season with simple resolution buttons
        # Group episodes by original season ID
        grouped_seasons = {}
        for ep_item in episodes_list:
            rid = ep_item['orig_ani_id']
            if rid not in grouped_seasons:
                grouped_seasons[rid] = []
            grouped_seasons[rid].append(ep_item)

        count = 0
        # Post a season card for each season
        for rid, eps in grouped_seasons.items():
            orig_adata = await get_anime_by_id(rid)
            if not orig_adata:
                continue

            orig_editor = TextEditor(anime_name)
            orig_editor.adata = orig_adata

            ep_season_str = await orig_editor.get_season()
            ep_season_no = int(ep_season_str) if ep_season_str.isdigit() else 1

            # Check available qualities in this season
            available_quals = set()
            for ep_item in eps:
                for qual in Var.QUALS:
                    if ep_item['ep_data'].get('ids', {}).get(qual):
                        available_quals.add(qual)

            # Build simple resolution buttons for specified channel
            row = []
            for qual in sorted(list(available_quals)):
                link = f"https://t.me/{(await client.get_me()).username}?start=batch_{rid}_{ep_season_no}_{qual}"
                row.append(InlineKeyboardButton(f"{qual}p", url=link))
            
            buttons_markup = [row] if row else []

            # Format Season Card Caption
            title = (orig_adata.get('title') or {}).get('english') or (orig_adata.get('title') or {}).get('romaji') or "N/A"
            total_episodes = len(eps)
            status = orig_adata.get("status") or "FINISHED"
            genres = ", ".join(f"{GENRES_EMOJI[x]} #{x.replace(' ', '_').replace('-', '_')}" for x in (orig_adata.get('genres') or []))
            audio_lang = "Hindi"

            caption = f"""<b>◆ <i>{title}</i> ◆</b>
<b>Season {ep_season_str} [Complete]</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>⌬ Audio:</b> <i>{audio_lang} [ESub]</i>  
<b>⌬ Status:</b> <i>{status}</i>  
<b>⌬ Total Episodes:</b> <i>{total_episodes}</i>

<b>✦ Genres:</b> <i>{genres}</i>
<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>✧ Powered By:</b> <i>{Var.BRAND_UNAME}</i>"""

            photo_url = f"https://img.anili.st/media/{rid}"

            try:
                # Send season card to specified channel
                msg = await client.send_photo(
                    chat_id=channel_id,
                    photo=photo_url,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(buttons_markup) if buttons_markup else None
                )
                
                # Save season post ID under the base ID mapping
                await db.anime_channels.update_one({'ani_id': mapping['ani_id']}, {'$set': {f'season_posts.{ep_season_str}': msg.id}})

                # If specified channel is different from main channel, also post card to main channel with watch redirection button
                if int(channel_id) != int(Var.MAIN_CHANNEL):
                    main_btns = []
                    try:
                        from helper_func import get_fsub_link
                        channel_invite = await get_fsub_link(bot, channel_id)
                        spec_chat = await bot.get_chat(channel_id)
                        if spec_chat.username:
                            watch_url = f"https://t.me/{spec_chat.username}/{msg.id}"
                        else:
                            watch_url = f"https://t.me/c/{str(channel_id)[4:]}/{msg.id}"
                        main_btns = [[
                            InlineKeyboardButton("• ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ •", url=channel_invite),
                            InlineKeyboardButton("• ᴡᴀᴛᴄʜ ꜱᴇᴀꜱᴏɴ •", url=watch_url)
                        ]]
                    except Exception as e:
                        logger.error(f"Failed to build main channel buttons: {e}")

                    try:
                        main_msg = await client.send_photo(
                            chat_id=Var.MAIN_CHANNEL,
                            photo=photo_url,
                            caption=caption,
                            reply_markup=InlineKeyboardMarkup(main_btns) if main_btns else None
                        )
                        # Save main season post ID under mapping
                        await db.anime_channels.update_one({'ani_id': mapping['ani_id']}, {'$set': {f'main_season_posts.{ep_season_str}': main_msg.id}})
                    except Exception as e:
                        logger.error(f"Failed to post season card to main channel: {e}")

                count += 1
            except Exception as e:
                logger.error(f"Failed to post season card for ID {rid}: {e}")

        await query.message.edit_text(f"✅ <b>Successfully reposted {count} Season Cards!</b>")
