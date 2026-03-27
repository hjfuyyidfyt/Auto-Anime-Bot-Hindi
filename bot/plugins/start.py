import asyncio
import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pyrogram import Client, filters, __version__
from pyrogram.enums import ParseMode, ChatAction
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, ChatInviteLink, ChatPrivileges
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserNotParticipant
from bot.core.bot_instance import bot, bot_loop, ani_cache
from bot.Script import botmaker
from helper_func import *
from bot.core.database import db
from asyncio import sleep as asleep, gather
from pyrogram.filters import command, private, user
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram import filters
from pyrogram.types import Message
import subprocess
from config import Var
from bot.core.func_utils import decode, editMessage, sendMessage, new_task, convertTime, getfeed
from bot.core.auto_animes import get_animes
from bot.core.reporter import rep
import time
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram.types import Message

Var.BAN_SUPPORT = f"{Var.BAN_SUPPORT}"

logger = logging.getLogger(__name__)

chat_data_cache = {}

async def not_joined(client: Client, message: Message):
    temp = await message.reply("<b><i>ᴡᴀɪᴛ ᴀ sᴇᴄ..</i></b>")
    user_id = message.from_user.id
    buttons = []
    count = 0

    try:
        all_channels = await db.show_channels()
        for total, chat_id in enumerate(all_channels, start=1):
            mode = await db.get_channel_mode(chat_id)  # Fetch mode

            await message.reply_chat_action(ChatAction.TYPING)

            if not await is_sub(client, user_id, chat_id):  # Ensure is_sub is defined
                try:
                    if chat_id in chat_data_cache:
                        data = chat_data_cache[chat_id]
                    else:
                        data = await client.get_chat(chat_id)
                        chat_data_cache[chat_id] = data

                    name = data.title

                    if mode == "on" and not data.username:
                        invite = await client.create_chat_invite_link(
                            chat_id=chat_id,
                            creates_join_request=True,
                            expire_date=datetime.utcnow() + timedelta(seconds=Var.FSUB_LINK_EXPIRY) if Var.FSUB_LINK_EXPIRY else None
                        )
                        link = invite.invite_link
                    else:
                        if data.username:
                            link = f"https://t.me/{data.username}"
                        else:
                            invite = await client.create_chat_invite_link(
                                chat_id=chat_id,
                                expire_date=datetime.utcnow() + timedelta(seconds=Var.FSUB_LINK_EXPIRY) if Var.FSUB_LINK_EXPIRY else None
                            )
                            link= invite.invite_link

                    buttons.append([InlineKeyboardButton(text=name, url=link)])
                    count += 1
                    await temp.edit(f"<b>{'! ' * count}</b>")
                except Exception as e:
                    logger.error(f"Error with chat {chat_id}: {e}")
                    return await temp.edit(
                        f"<b><i>! Eʀʀᴏʀ, Cᴏɴᴛᴀᴄᴛ ᴅᴇᴠᴇʟᴏᴘᴇʀ ᴛᴏ sᴏʟᴠᴇ ᴛʜᴇ ɪssᴜᴇs @azaka7902</i></b>\n"
                        f"<blockquote expandable><b>Rᴇᴀsᴏɴ:</b> {e}</blockquote>"
                    )

        # Fetch bot's username
        me = await client.get_me()
        if not me.username:
            await temp.edit("<b>❌ Error: Bot username is not set.</b>")
            return

        if len(message.command) > 1:
            buttons.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{me.username}?start={message.command[1]}")])
        else:
            pass

        await message.reply_photo(
            photo=Var.FORCE_PIC,
            caption=botmaker.FORCE_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name,
                username=None if not message.from_user.username else '@' + message.from_user.username,
                mention=message.from_user.mention,
                id=message.from_user.id
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        await temp.delete()
    except Exception as e:
        logger.error(f"Final Error: {e}")
        await temp.edit(
            f"<b><i>! Eʀʀᴏʀ, Cᴏɴᴛᴀᴄᴛ ᴅᴇᴠᴇʟᴏᴘᴇʀ ᴛᴏ sᴏʟᴠᴇ ᴛʜᴇ ɪssᴜᴇs </i></b>\n"
            f"<blockquote expandable><b>Rᴇᴀsᴏɴ:</b> {e}</blockquote>"
        )

@bot.on_message(filters.command('start') & filters.private)
@new_task
async def start_msg(client: Client, message: Message):
    user_id = message.from_user.id
    from_user = message.from_user

    # Check if user is banned
    banned_users = await db.get_ban_users()
    if user_id in banned_users:
        return await message.reply_text(
            "<b>⛔️ You are Bᴀɴɴᴇᴅ from using this bot.</b>\n\n"
            "<i>Contact support if you think this is a mistake.</i>",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Contact Support", url=Var.BAN_SUPPORT)]]
            )
        )

    # Check Force Subscription
    if not await is_subscribed(client, user_id):  # Ensure is_subscribed is defined
        return await not_joined(client, message)

    txtargs = message.text.split()
    temp = await sendMessage(message, "<b>Pʟᴇᴀsᴇ ᴡᴀɪᴛ</b>")

    if len(txtargs) <= 1:
        await temp.delete()
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("•⚡️ ᴍᴀɪɴ ʜᴜʙ •", url=Var.MHCHANNEL_URL)],
                [
                    InlineKeyboardButton("• ᴀʙᴏᴜᴛ", callback_data="about"),
                    InlineKeyboardButton('ʜᴇʟᴘ •', callback_data="help")
                ]
            ]
        )
        await message.reply_photo(
            photo=Var.START_PIC,
            caption=botmaker.START_MSG.format(
                first=from_user.first_name,
                last=from_user.last_name,
                username=None if not message.from_user.username else '@' + message.from_user.username,
                mention=from_user.mention,
                id=from_user.id
            ),
            reply_markup=reply_markup,
            message_effect_id=5104841245755180586
        )
        return

    # Deep-link handling
    try:
        base64_string = txtargs[1]
        arg = (await decode(base64_string)).split('-')
        botmaker_msgs = []

        # Fetch bot's username
        me = await client.get_me()
        if not me.username:
            await editMessage(temp, "<b>❌ Error: Bot username is not set.</b>")
            return
    except Exception as e:
        await rep.report(f"User : {user_id} | Error : {str(e)}", "error")
        await editMessage(temp, "<b>Input Link Code Decode Failed !</b>")
        return

    if len(arg) in [2, 3]:
        try:
            # Validate configuration
            if not isinstance(Var.FILE_STORE, int) or Var.FILE_STORE == 0:
                logger.error("Var.FILE_STORE is invalid or zero")
                await editMessage(temp, "<b>❌ Error: Invalid configuration.</b>")
                return
            if not isinstance(client.db_channel.id, int) or client.db_channel.id == 0:
                logger.error("client.db_channel.id is invalid or zero")
                await editMessage(temp, "<b>❌ Error: Invalid configuration.</b>")
                return

            Var.FILE_AUTO_DELETE = await db.get_del_timer()  # Fetch deletion timer from database
            if len(arg) == 2 and arg[0] == 'get':
                fid = int(int(arg[1]) / abs(int(Var.FILE_STORE)))
                msg = await client.get_messages(Var.FILE_STORE, message_ids=fid)
                if msg.empty:
                    return await editMessage(temp, "<b>File Not Found !</b>")
                caption = (botmaker.CUSTOM_CAPTION.format(filename=msg.document.file_name) if bool(botmaker.CUSTOM_CAPTION) and bool(msg.document)
                           else ("" if not msg.caption else msg.caption.html))
                reply_markup = msg.reply_markup if not Var.DISABLE_CHANNEL_BUTTON else None
                nmsg = await msg.copy(message.chat.id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup, protect_content=Var.PROTECT_CONTENT)
                botmaker_msgs.append(nmsg)
                await temp.delete()
                if Var.FILE_AUTO_DELETE > 0:
                    notification_msg = await message.reply(
                        f"<b>Tʜɪs Fɪʟᴇ ᴡɪʟʟ ʙᴇ Dᴇʟᴇᴛᴇᴅ ɪɴ {get_exp_time(Var.FILE_AUTO_DELETE)}. Pʟᴇᴀsᴇ sᴀᴠᴇ ᴏʀ ғᴏʀᴡᴀʀᴅ ɪᴛ ᴛᴏ ʏᴏᴜʀ sᴀᴠᴇᴅ ᴍᴇssᴀɢᴇs ʙᴇғᴏʀᴇ ɪᴛ ɢᴇᴛs Dᴇʟᴇᴛᴇᴅ.</b>"
                    )
                    await asyncio.sleep(Var.FILE_AUTO_DELETE)
                    try:
                        await nmsg.delete()
                    except Exception as e:
                        logger.error(f"Error deleting message {nmsg.id}: {e}")
                    try:
                        reload_url = f"https://t.me/{me.username}?start={txtargs[1]}"
                        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("ɢᴇᴛ ғɪʟᴇ ᴀɢᴀɪɴ!", url=reload_url), InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data='close')]])
                        await notification_msg.edit(
                            "<b><u>Pʀᴇᴠɪᴏᴜs Mᴇssᴀɢᴇ ᴡᴀs Dᴇʟᴇᴛᴇᴅ 🗑</u></b><blockquote><b>\nIғ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ɢᴇᴛ ᴛʜᴇ ғɪʟᴇ(s) ᴀɢᴀɪɴ, ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ɢᴇᴛ ғɪʟᴇ ᴀɢᴀɪɴ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴇʟsᴇ ᴄʟᴏsᴇ ᴛʜɪs ᴍᴇssᴀɢᴇ ʙʏ ᴄʟɪᴄᴋ ᴏɴ ᴄʟᴏsᴇ.</b></blockquote>",
                            reply_markup=keyboard
                        )
                    except Exception as e:
                        logger.error(f"Error updating notification: {e}")
            elif len(arg) == 2 and arg[0] == 'batch':
                batch_id = arg[1]
                msg_ids = await db.get_batch(batch_id)
                if not msg_ids:
                    return await editMessage(temp, "<b>Batch Not Found or Expired!</b>")
                
                botmaker_msgs = []
                # Fetch messages in chunks of 200 (limit of get_messages)
                # But we can just use the loop logic below.
                # msg_ids is a list of integers.
                
                await temp.delete()
                
                for msg_id in msg_ids:
                    try:
                        # Assuming messages are in FILE_STORE.
                        # We need to confirm if msg_ids stored in DB are from FILE_STORE.
                        # Yes, TgUploader uploads to FILE_STORE (implied from context, need validation if it's not MAIN_CHANNEL).
                        # Actually TgUploader usage: `msg = await TgUploader(stat_msg).upload(out_path, qual)`
                        # If TgUploader uploads to channel, it returns that msg.
                        # Let's assume passed msg_ids are correct.
                        msg = await client.get_messages(Var.FILE_STORE, message_ids=int(msg_id))
                        if not msg or msg.empty:
                            continue
                            
                        caption = (botmaker.CUSTOM_CAPTION.format(filename=msg.document.file_name) if bool(botmaker.CUSTOM_CAPTION) and bool(msg.document)
                                    else ("" if not msg.caption else msg.caption.html))
                        reply_markup = msg.reply_markup if not Var.DISABLE_CHANNEL_BUTTON else None
                        
                        copied_msg = await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML,
                                                    reply_markup=reply_markup, protect_content=Var.PROTECT_CONTENT)
                        botmaker_msgs.append(copied_msg)
                        await asyncio.sleep(0.5) # Floodwait prevention
                    except FloodWait as e:
                        await asyncio.sleep(e.x)
                        # retry logic could be added here
                    except Exception as e:
                        logger.error(f"Error sending batch msg {msg_id}: {e}")
                
            elif len(arg) == 3:
                start = int(int(arg[1]) / abs(client.db_channel.id))
                end = int(int(arg[2]) / abs(client.db_channel.id))
                ids = range(start, end + 1) if start <= end else list(range(start, end - 1, -1))
                botmaker_msgs = []
                for msg_id in ids:
                    msg = await client.get_messages(client.db_channel.id, message_ids=msg_id)
                    if not msg.empty:
                        caption = (botmaker.CUSTOM_CAPTION.format(filename=msg.document.file_name) if bool(botmaker.CUSTOM_CAPTION) and bool(msg.document)
                                   else ("" if not msg.caption else msg.caption.html))
                        reply_markup = msg.reply_markup if not Var.DISABLE_CHANNEL_BUTTON else None
                        try:
                            copied_msg = await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML,
                                                        reply_markup=reply_markup, protect_content=Var.PROTECT_CONTENT)
                            botmaker_msgs.append(copied_msg)
                        except FloodWait as e:
                            await asyncio.sleep(e.x)
                            copied_msg = await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML,
                                                        reply_markup=reply_markup, protect_content=Var.PROTECT_CONTENT)
                            botmaker_msgs.append(copied_msg)
                await temp.delete()
                if Var.FILE_AUTO_DELETE > 0:
                    notification_msg = await message.reply(
                        f"<b>Tʜɪs Fɪʟᴇ ᴡɪʟʟ ʙᴇ Dᴇʟᴇᴛᴇᴅ ɪɴ {get_exp_time(Var.FILE_AUTO_DELETE)}. Pʟᴇᴀsᴇ sᴀᴠᴇ ᴏʀ ғᴏʀᴡᴀʀᴅ ɪᴛ ᴛᴏ ʏᴏᴜʀ sᴀᴠᴇᴅ ᴍᴇssᴀɢᴇs ʙᴇғᴏʀᴇ ɪᴛ ɢᴇᴛs Dᴇʟᴇᴛᴇᴅ.</b>"
                    )
                    await asyncio.sleep(Var.FILE_AUTO_DELETE)
                    for snt_msg in botmaker_msgs:
                        if snt_msg:
                            try:
                                await snt_msg.delete()
                            except Exception as e:
                                logger.error(f"Error deleting message {snt_msg.id}: {e}")
                    try:
                        reload_url = f"https://t.me/{me.username}?start={txtargs[1]}"
                        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("ɢᴇᴛ ғɪʟᴇ ᴀɢᴀɪɴ!", url=reload_url), InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data='close')]])
                        await notification_msg.edit(
                            "<b><u>Pʀᴇᴠɪᴏᴜs Mᴇssᴀɢᴇ ᴡᴀs Dᴇʟᴇᴛᴇᴅ 🗑</u></b><blockquote><b>\nIғ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ɢᴇᴛ ᴛʜᴇ ғɪʟᴇ(s) ᴀɢᴀɪɴ, ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ɢᴇᴛ ғɪʟᴇ ᴀɢᴀɪɴ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴇʟsᴇ ᴄʟᴏsᴇ ᴛʜɪs ᴍᴇssᴀɢᴇ ʙʏ ᴄʟɪᴄᴋ ᴏɴ ᴄʟᴏsᴇ.</b></blockquote>",
                            reply_markup=keyboard
                        )
                    except Exception as e:
                        logger.error(f"Error updating notification: {e}")
        except Exception as e:
            await rep.report(f"User : {user_id} | Error : {str(e)}", "error")
            await editMessage(temp, "<b>File Not Found !</b>")
    else:
        await editMessage(temp, "<b>Input Link is Invalid for Usage !</b>")

@bot.on_message(filters.command('pause') & filters.private & admin)  # Ensure admin filter is defined
async def pause_fetch(client, message):
    ani_cache['fetch_animes'] = False
    await sendMessage(message, "Successfully Paused Fetching Anime...")

@bot.on_message(filters.command('resume') & filters.private & admin)  # Ensure admin filter is defined
async def resume_fetch(client, message):
    ani_cache['fetch_animes'] = True
    await sendMessage(message, "Successfully Resumed Fetching Anime...")

@bot.on_message(filters.command('addlink') & filters.private & admin)  # Ensure admin filter is defined
@new_task
async def add_link(client, message):
    if len(args := message.text.split()) <= 1:
        return await sendMessage(message, "<b>No Link Found to Add</b>")
    
    Var.RSS_ITEMS.append(args[1])
    await sendMessage(message, f"<code>Global Link Added Successfully!</code>\n\n<b> • All Link(s) :</b> {', '.join(Var.RSS_ITEMS)[:-2]}")

@bot.on_message(filters.command('addtask') & filters.private & admin)  # Ensure admin filter is defined
@new_task
async def add_task(client, message):
    if len(args := message.text.split()) <= 1:
        return await sendMessage(message, "<b>No Task Found to Add</b>")
    
    index = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0
    if not (taskInfo := await getfeed(args[1], index)):
        return await sendMessage(message, "<b>No Task Found to Add for the Provided Link</b>")
    
    ani_task = bot_loop.create_task(get_animes(taskInfo.title, taskInfo.link, True))
    await sendMessage(message, f"<i><b>Task Added Successfully!</b></i>\n\n    • <b>Task Name :</b> {taskInfo.title}\n    • <b>Task Link :</b> {args[1]}")

@bot.on_message(filters.command('commands') & filters.private & admin)  # Ensure admin filter is defined
async def bcmd(client: Client, message: Message):        
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("• ᴄʟᴏsᴇ •", callback_data="close")]])
    await message.reply(text=botmaker.CMD_TXT, reply_markup=reply_markup, quote=True)
