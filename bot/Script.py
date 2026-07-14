import os

class botmaker(object):
    START_MSG = """<b>Bᴀᴋᴀᴀᴀ!!!....{first}\n\n<blockquote>ɪ ᴀᴍ ғɪʟᴇ sᴛᴏʀᴇ + Aᴜᴛᴏ Aɴɪᴍᴇ ʙᴏᴛ, ɪ ᴄᴀɴ sᴛᴏʀᴇ ᴘʀɪᴠᴀᴛᴇ ғɪʟᴇs ɪɴ sᴘᴇᴄɪғɪᴇᴅ ᴄʜᴀɴɴᴇʟ ᴀɴᴅ ᴏᴛʜᴇʀ ᴜsᴇʀs ᴄᴀɴ ᴀᴄᴄᴇss ɪᴛ ғʀᴏᴍ sᴘᴇᴄɪᴀʟ ʟɪɴᴋ.</blockquote></b>"""

    FORCE_MSG = """ʜᴇʟʟᴏ {first}\n\n<b>ᴊᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟs ᴀɴᴅ ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ʀᴇʟᴏᴀᴅ button ᴛᴏ ɢᴇᴛ ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛᴇᴅ ꜰɪʟᴇ.</b>"""

    HELP_TXT = """<b><blockquote>ᴛʜɪs ɪs ᴀɴ ғɪʟᴇ ᴛᴏ ʟɪɴᴋ ʙᴏᴛ ᴡᴏʀᴋɪɴɢ ғᴏʀ @Z5Tech_BD

❏ ʙᴏᴛ ᴄᴏᴍᴍᴀɴᴅs
├ /start : sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ
├ /about : ᴏᴜʀ Iɴғᴏʀᴍᴀᴛɪᴏɴ
└ /help : ʜᴇʟᴘ ʀᴇʟᴀᴛᴇᴅ ʙᴏᴛ

sɪᴍᴘʟʏ ᴄʟɪᴄᴋ ᴏɴ ʟɪɴᴋ ᴀɴᴅ sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ, ᴊᴏɪɴ ʙᴏᴛʜ ᴄʜᴀɴɴᴇʟs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ — ᴛʜᴀᴛ'ꜱ ɪᴛ.....!</blockquote></b>"""

    ABOUT_TXT = """<b><blockquote>
◈ ᴄʀᴇᴀᴛᴏʀ: <a href="https://t.me/Z5Tech_BD">ESHAN</a>
◈ ʙᴀᴄᴋᴜᴘ ᴄʜᴀɴɴᴇʟ: <a href="{backup_link}">Crunchyroll backup</a>
◈ Oɴɢᴏɪɴɢ Eɴɢ sᴜʙ/Hindi ᴅᴜʙ: <a href="https://t.me/crunchyroll100">Crunchyroll</a>
</blockquote></b>"""

    CMD_TXT = """<b>📜 <u>MASTER ADMIN COMMAND LIST</u></b>

<blockquote><b>🛑 <u>Process & Encoding Control</u></b></blockquote>
<b>››</b> <code>/cancel_all</code> <b>:</b> Stop active encodes, clear queues & free storage  
<b>››</b> <code>/pause</code> <b>:</b> Pause background anime fetching  
<b>››</b> <code>/resume</code> <b>:</b> Resume background anime fetching  
<b>››</b> <code>/restart</code> <b>:</b> Restart the bot  

<blockquote><b>📥 <u>Manual Search & Sync Queue</u></b></blockquote>
<b>››</b> <code>/qadd</code> <i>{name}</i> <b>:</b> Add anime to background sync queue  
<b>››</b> <code>/qlist</code> <b>:</b> View pending & completed sync tasks  
<b>››</b> <code>/qclear</code> <b>:</b> Clear pending queue tasks  
<b>››</b> <code>/search</code> <i>{query}</i> <b>:</b> Search Nyaa/MovieBox directly  

<blockquote><b>🗺 <u>Anime Channel Mapping</u></b></blockquote>
<b>››</b> <code>/setchannel</code> <b>:</b> Interactive prompt to map anime to channel  
<b>››</b> <code>/delchannel</code> <b>:</b> Remove anime channel mapping  
<b>››</b> <code>/listchannels</code> <b>:</b> View all mapped anime channels  

<blockquote><b>🛡 <u>Force-Sub & Security</u></b></blockquote>
<b>››</b> <code>/addchnl</code> <b>:</b> Add force-sub channel  
<b>››</b> <code>/delchnl</code> <b>:</b> Remove force-sub channel  
<b>››</b> <code>/listchnl</code> <b>:</b> View force-sub channels  
<b>››</b> <code>/fsub_mode</code> <b>:</b> Toggle force-sub mode  
<b>››</b> <code>/dlt_time</code> <i>{sec}</i> <b>:</b> Set auto-delete timer for file downloads  
<b>››</b> <code>/check_dlt_time</code> <b>:</b> Check current auto-delete timer  

<blockquote><b>📡 <u>RSS Automation</u></b></blockquote>
<b>››</b> <code>/add_rss</code> <b>:</b> Add custom RSS feed URL  
<b>››</b> <code>/list_rss</code> <b>:</b> View configured RSS feeds  
<b>››</b> <code>/remove_rss</code> <b>:</b> Remove an RSS feed  

<blockquote><b>📊 <u>Analytics & Users</u></b></blockquote>
<b>››</b> <code>/stats</code> <b>:</b> View bot uptime & system stats  
<b>››</b> <code>/users</code> <b>:</b> Check total bot user count  
<b>››</b> <code>/broadcast</code> <b>:</b> Broadcast text message to users  
<b>››</b> <code>/pbroadcast</code> <b>:</b> Broadcast photo to users  
<b>››</b> <code>/dbroadcast</code> <b>:</b> Broadcast video/doc to users  
<b>››</b> <code>/ban</code> & <code>/unban</code> <b>:</b> Ban or unban a user  
<b>››</b> <code>/admins</code> <b>:</b> Manage bot admin list  
"""

    BOT_STATS_TEXT = "<b>BOT UPTIME</b>\n{uptime}"

    # ✅ Custom Caption from environment
    CUSTOM_CAPTION = os.getenv("CUSTOM_CAPTION", None)
