
from pyrogram import Client 
from bot.core.bot_instance import bot
from config import Var
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.core.database import *
from bot.Script import botmaker

@bot.on_callback_query()
async def cb_handler(client: bot, query: CallbackQuery):
    data = query.data

    if data == "help":
        await query.message.edit_text(
            text=botmaker.HELP_TXT.format(first=query.from_user.first_name),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('ʜᴏᴍᴇ', callback_data='start'),
                 InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data='close')]
            ])
        )

    elif data == "about":
        try:
            chat = await client.get_chat(-1004406391637)
            backup_link = chat.invite_link or await client.export_chat_invite_link(-1004406391637)
        except Exception:
            backup_link = "https://t.me/c/4406391637"
        await query.message.edit_text(
            text=botmaker.ABOUT_TXT.format(first=query.from_user.first_name, backup_link=backup_link),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('ʜᴏᴍᴇ', callback_data='start'),
                 InlineKeyboardButton('ᴄʟᴏꜱᴇ', callback_data='close')]
            ])
        )

    elif data == "start":
        await query.message.edit_text(
            text=botmaker.START_MSG.format(first=query.from_user.first_name),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("ʜᴇʟᴘ", callback_data='help'),
                 InlineKeyboardButton("ᴀʙᴏᴜᴛ", callback_data='about')]
            ])
        )

    elif data == "close":
        await query.message.delete()
        try:
            await query.message.reply_to_message.delete()
        except:
            pass

    elif data.startswith("rfs_ch_"):
        cid = int(data.split("_")[2])
        try:
            chat = await client.get_chat(cid)
            mode = await db.get_channel_mode(cid)
            status = "🟢 ᴏɴ" if mode == "on" else "🔴 ᴏғғ"
            new_mode = "ᴏғғ" if mode == "on" else "on"
            buttons = [
                [InlineKeyboardButton(f"ʀᴇǫ ᴍᴏᴅᴇ {'OFF' if mode == 'on' else 'ON'}", callback_data=f"rfs_toggle_{cid}_{new_mode}")],
                [InlineKeyboardButton("‹ ʙᴀᴄᴋ", callback_data="fsub_back")]
            ]
            await query.message.edit_text(
                f"Channel: {chat.title}\nCurrent Force-Sub Mode: {status}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception:
            await query.answer("Failed to fetch channel info", show_alert=True)

    elif data.startswith("rfs_toggle_"):
        cid, action = data.split("_")[2:]
        cid = int(cid)
        mode = "on" if action == "on" else "off"

        await db.set_channel_mode(cid, mode)
        await query.answer(f"Force-Sub set to {'ON' if mode == 'on' else 'OFF'}")

        # Refresh the same channel's mode view
        chat = await client.get_chat(cid)
        status = "🟢 ON" if mode == "on" else "🔴 OFF"
        new_mode = "off" if mode == "on" else "on"
        buttons = [
            [InlineKeyboardButton(f"ʀᴇǫ ᴍᴏᴅᴇ {'OFF' if mode == 'on' else 'ON'}", callback_data=f"rfs_toggle_{cid}_{new_mode}")],
            [InlineKeyboardButton("‹ ʙᴀᴄᴋ", callback_data="fsub_back")]
        ]
        await query.message.edit_text(
            f"Channel: {chat.title}\nCurrent Force-Sub Mode: {status}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data == "fsub_back":
        channels = await db.show_channels()
        buttons = []
        for cid in channels:
            try:
                chat = await client.get_chat(cid)
                mode = await db.get_channel_mode(cid)
                status = "🟢" if mode == "on" else "🔴"
                buttons.append([InlineKeyboardButton(f"{status} {chat.title}", callback_data=f"rfs_ch_{cid}")])
            except:
                continue

        if not buttons:
            buttons.append([InlineKeyboardButton("Add Channel ➕", callback_data="addchnl_prompt")])
            await query.message.edit_text(
                "❌ <b>No force-sub channels found.</b>",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            buttons.append([
                InlineKeyboardButton("Add Channel ➕", callback_data="addchnl_prompt"),
                InlineKeyboardButton("Close ✖️", callback_data="close")
            ])
            await query.message.edit_text(
                "⚡ <b>Select a channel to toggle Force-Sub Mode:</b>",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

    elif data.startswith("delmap_"):
        ani_id = int(data.split("_")[1])
        await db.delete_anime_channel(ani_id)
        await query.answer("Mapping deleted successfully!")
        
        # Refresh mappings
        mappings = await db.get_all_anime_channels()
        if not mappings:
            buttons = [[InlineKeyboardButton("Set Mapping ➕", callback_data="setmap_prompt")]]
            await query.message.edit_text("⚠️ Nᴏ ᴀɴɪᴍᴇ ᴄʜᴀɴɴᴇʟs ᴍᴀᴘᴘᴇᴅ ʏᴇᴛ.", reply_markup=InlineKeyboardMarkup(buttons))
            return

        text = "• <b>Aɴɪᴍᴇ ᴄʜᴀɴɴᴇʟ ᴍᴀᴘᴘɪɴɢ:</b>\n\n"
        buttons = []
        from bot.core.text_utils import get_anime_by_id
        for mapping in mappings:
            aid = mapping["ani_id"]
            channel_id = mapping["channel_id"]
            anime_name = mapping.get("anime_name")
            if not anime_name:
                try:
                    ani_data = await get_anime_by_id(aid)
                    anime_name = (ani_data.get('title') or {}).get('romaji') or (ani_data.get('title') or {}).get('english') or f"Anime {aid}"
                    await db.set_anime_channel(aid, channel_id, anime_name)
                except Exception:
                    anime_name = f"Anime {aid}"

            text += f"• id:<code>{aid}</code> (name: <code>{anime_name}</code>) ➡️ <code>{channel_id}</code>\n"
            buttons.append([InlineKeyboardButton(f"❌ Remove {anime_name[:25]}", callback_data=f"delmap_{aid}")])

        buttons.append([
            InlineKeyboardButton("Set Mapping ➕", callback_data="setmap_prompt"),
            InlineKeyboardButton("Close ✖️", callback_data="close")
        ])
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "setmap_prompt":
        from config import LOGS
        LOGS.info(f"User {query.from_user.id} clicked setmap_prompt")
        bot.user_states[query.from_user.id] = "waiting_for_setchannel"
        await query.message.reply("📢 <b>Please send the mapping details:</b>\nFormat: <code><Anime Name or ID> <Channel ID></code>\nExample: <code>DAN DA DAN -1002812370717</code>", quote=False)
        await query.answer()

    elif data.startswith("delrss_"):
        index = int(data.split("_")[1])
        from bot.core.bot_instance import ani_cache
        feeds = sorted(list(ani_cache.get("custom_rss", [])))
        if 0 <= index < len(feeds):
            url = feeds[index]
            ani_cache["custom_rss"].remove(url)
            await query.answer("RSS feed deleted successfully!")
        else:
            await query.answer("Feed not found!", show_alert=True)

        # Refresh RSS Feeds
        feeds = sorted(list(ani_cache.get("custom_rss", [])))
        if not feeds:
            buttons = [[InlineKeyboardButton("Add RSS ➕", callback_data="addrss_prompt")]]
            await query.message.edit_text("⚠️ No custom RSS links added yet.", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            text = "📡 <b>Custom RSS Feeds:</b>\n\n"
            buttons = []
            for idx, url in enumerate(feeds):
                text += f"<b>{idx + 1}.</b> <code>{url}</code>\n"
                buttons.append([InlineKeyboardButton(f"❌ Delete Feed {idx + 1}", callback_data=f"delrss_{idx}")])
            buttons.append([
                InlineKeyboardButton("Add RSS ➕", callback_data="addrss_prompt"),
                InlineKeyboardButton("Close ✖️", callback_data="close")
            ])
            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

    elif data == "addrss_prompt":
        from config import LOGS
        LOGS.info(f"User {query.from_user.id} clicked addrss_prompt")
        bot.user_states[query.from_user.id] = "waiting_for_addrss"
        await query.message.reply("📡 <b>Please send the custom RSS feed URL to add:</b>", quote=False)
        await query.answer()

    elif data.startswith("delchnl_"):
        ch_id = int(data.split("_")[1])
        await db.rem_channel(ch_id)
        await query.answer("Force-sub channel deleted successfully!")

        # Refresh channels list
        channels = await db.show_channels()
        if not channels:
            buttons = [[InlineKeyboardButton("Add Channel ➕", callback_data="addchnl_prompt")]]
            await query.message.edit_text("<b>❌ No force-sub channels found.</b>", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            result = "<b>⚡ Force-sub Channels:</b>\n\n"
            buttons = []
            for cid in channels:
                try:
                    chat = await client.get_chat(cid)
                    link = chat.invite_link or await client.export_chat_invite_link(chat.id)
                    result += f"<b>•</b> <a href='{link}'>{chat.title}</a> [<code>{cid}</code>]\n"
                    buttons.append([InlineKeyboardButton(f"❌ Remove {chat.title}", callback_data=f"delchnl_{cid}")])
                except Exception as e:
                    result += f"<b>•</b> <code>{cid}</code> — <i>Unavailable</i>\n"
                    buttons.append([InlineKeyboardButton(f"❌ Remove ID: {cid}", callback_data=f"delchnl_{cid}")])

            buttons.append([
                InlineKeyboardButton("Add Channel ➕", callback_data="addchnl_prompt"),
                InlineKeyboardButton("Close ✖️", callback_data="close")
            ])
            await query.message.edit_text(result, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

    elif data == "addchnl_prompt":
        from config import LOGS
        LOGS.info(f"User {query.from_user.id} clicked addchnl_prompt")
        bot.user_states[query.from_user.id] = "waiting_for_addchnl"
        await query.message.reply("📢 <b>Please send the Channel ID (e.g. -100xxxxxxxxxx) that you want to add to force-sub:</b>", quote=False)
        await query.answer()

    elif data.startswith("settitle_"):
        parts = data.split("_")
        cid = int(parts[1])
        idx = int(parts[2])
        presets = {
            1: "⚡ MAIN HUB ⚡",
            2: "📢 BACKUP CHANNEL 📢",
            3: "🔥 JOIN MAIN CHANNEL 🔥",
            4: "💫 VIP ANIME HUB 💫"
        }
        title = presets.get(idx, "")
        await db.set_channel_title(cid, title)
        bot.user_states[query.from_user.id] = None
        disp = title if title else "Default Telegram Title"
        await query.message.edit_text(f"<b>✅ Custom display title set successfully!</b>\n\n<b>Channel ID:</b> <code>{cid}</code>\n<b>Button Title:</b> {disp}")
        await query.answer()

    else:
        from pyrogram import ContinuePropagation
        raise ContinuePropagation
