import logging
from pyrogram import Client, filters, StopPropagation
from pyrogram.types import Message
from pyrogram.enums import ChatType, ChatMemberStatus
from bot.core.bot_instance import bot, ani_cache
from bot.core.database import db
from bot.core.text_utils import TextEditor
from helper_func import admin

logger = logging.getLogger(__name__)

# Filter to match if user has an active state
async def has_active_state(_, client, message: Message):
    if not message.from_user:
        return False
    user_id = message.from_user.id
    state = getattr(bot, "user_states", {}).get(user_id)
    return bool(state)

state_filter = filters.create(has_active_state)

@bot.on_message(filters.private & admin & state_filter & ~filters.command("cancel"), group=-1)
async def handle_admin_states(client: Client, message: Message):
    user_id = message.from_user.id
    state = bot.user_states.get(user_id)
    text = message.text.strip() if message.text else ""

    if not text:
        await message.reply("⚠️ <b>Please send text input or send /cancel to cancel.</b>")
        raise StopPropagation

    if state == "waiting_for_setchannel":
        parts = text.split()
        if len(parts) < 2:
            await message.reply("⚠️ <b>Invalid format. Please send:</b> <code><Anime Name or ID> <Channel ID></code>")
            raise StopPropagation
        
        anime_name = " ".join(parts[:-1])
        try:
            channel_id = int(parts[-1])
        except ValueError:
            await message.reply("⚠️ <b>Channel ID must be a numeric ID (e.g. -100xxxxxxxxxx). Please try again:</b>")
            raise StopPropagation

        # Load anime info
        ani_info = TextEditor(anime_name)
        await ani_info.load_anilist()
        ani_id = ani_info.adata.get('id')

        if not ani_id:
            if anime_name.isdigit():
                ani_id = int(anime_name)
            else:
                await message.reply(f"⚠️ <b>Anime not found: '{anime_name}'. Please check the name and try again:</b>")
                raise StopPropagation

        real_title = (ani_info.adata.get('title') or {}).get('romaji') or (ani_info.adata.get('title') or {}).get('english') or anime_name
        await db.set_anime_channel(ani_id, channel_id, real_title)
        bot.user_states[user_id] = None
        await message.reply(f"<b><blockquote>✅ <u>Aɴɪᴍᴇ</u> : {real_title} (ID: {ani_id}) \n<u>Sᴇᴛ ᴛᴏ ᴄʜᴀɴɴᴇʟ</u> : {channel_id} successfully mapped!</blockquote></b>")

    elif state == "waiting_for_addrss":
        if not text.startswith("http"):
            await message.reply("⚠️ <b>Invalid URL format. Please send a valid http/https RSS URL:</b>")
            raise StopPropagation

        ani_cache["custom_rss"].add(text)
        bot.user_states[user_id] = None
        await message.reply(f"<b>✅ Custom RSS feed added successfully:</b>\n<code>{text}</code>")

    elif state == "waiting_for_addchnl":
        try:
            channel_id = int(text)
        except ValueError:
            await message.reply("⚠️ <b>Invalid Channel ID. Channel ID must be a numeric ID (e.g., -100xxxxxxxxxx):</b>")
            raise StopPropagation

        all_channels = await db.show_channels()
        channel_ids_only = [cid if isinstance(cid, int) else cid[0] for cid in all_channels]
        if channel_id in channel_ids_only:
            bot.user_states[user_id] = None
            await message.reply(f"⚠️ <b>Channel already exists in force-sub list:</b> <code>{channel_id}</code>")
            raise StopPropagation

        try:
            chat = await client.get_chat(channel_id)
            if chat.type != ChatType.CHANNEL:
                await message.reply("⚠️ <b>Only public or private channels are allowed. Please try again:</b>")
                raise StopPropagation

            member = await client.get_chat_member(chat.id, "me")
            if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                await message.reply("⚠️ <b>Bot must be an administrator in that channel. Please promote the bot and try again:</b>")
                raise StopPropagation

            await db.add_channel(channel_id)
            bot.user_states[user_id] = f"waiting_for_chnltitle_{channel_id}"
            
            try:
                link = await client.export_chat_invite_link(chat.id)
            except Exception:
                link = f"https://t.me/{chat.username}" if chat.username else f"https://t.me/c/{str(chat.id)[4:]}"

            from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            buttons = [
                [InlineKeyboardButton("⚡ MAIN HUB ⚡", callback_data=f"settitle_{channel_id}_1"),
                 InlineKeyboardButton("📢 BACKUP CHANNEL 📢", callback_data=f"settitle_{channel_id}_2")],
                [InlineKeyboardButton("🔥 JOIN MAIN CHANNEL 🔥", callback_data=f"settitle_{channel_id}_3"),
                 InlineKeyboardButton("💫 VIP ANIME HUB 💫", callback_data=f"settitle_{channel_id}_4")],
                [InlineKeyboardButton(f"Default ({chat.title[:15]})", callback_data=f"settitle_{channel_id}_0")]
            ]

            await message.reply(
                f"<b>✅ Channel Verified:</b> <a href='{link}'>{chat.title}</a>\n"
                f"<b>ID:</b> <code>{channel_id}</code>\n\n"
                f"🎨 <b>Select a customized button title below, or type your own custom display title in chat:</b>",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            logger.error(f"Failed to add channel {channel_id} from prompt: {e}")
            await message.reply(f"⚠️ <b>Failed to add channel:</b>\n<code>{channel_id}</code>\n\n<i>Error: {e}</i>\n\nPlease try again:")

    elif state and state.startswith("waiting_for_chnltitle_"):
        channel_id = int(state.split("_")[3])
        await db.set_channel_title(channel_id, text)
        bot.user_states[user_id] = None
        await message.reply(f"<b>✅ Custom display title set successfully!</b>\n\n<b>Channel ID:</b> <code>{channel_id}</code>\n<b>Button Title:</b> {text}")
    raise StopPropagation

@bot.on_message(filters.private & admin & filters.command("cancel"))
async def cancel_admin_state(client: Client, message: Message):
    user_id = message.from_user.id
    if bot.user_states.get(user_id):
        bot.user_states[user_id] = None
        await message.reply("❌ <b>Interactive prompt cancelled. State cleared.</b>")
    else:
        await message.reply("ℹ️ <b>No active prompt session to cancel.</b>")
