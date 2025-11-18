import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from yt_dlp import YoutubeDL
import asyncio
import json
import requests
from bs4 import BeautifulSoup

# توکن ربات تلگرام خود را اینجا قرار دهید
TELEGRAM_TOKEN = "8212407334:AAFux0h8ZL-9lnNscQOQkeynMTKg-9lWH5o"

# آی‌دی ادمین (آی‌دی عددی تلگرام خود را اینجا قرار دهید)
ADMIN_ID = 6097462059  # آی‌دی خود را اینجا بگذارید

# فایل ذخیره تنظیمات و کاربران
SETTINGS_FILE = "bot_settings.json"
USERS_FILE = "bot_users.json"

# حالت های ربات
WAITING_FOR_CHOICE = 0
WAITING_FOR_LINK = 1
WAITING_FOR_NAME = 2
WAITING_FOR_CHANNEL_1 = 3
WAITING_FOR_CHANNEL_2 = 4
WAITING_FOR_AD_MEDIA = 5
WAITING_FOR_AD_TEXT = 6
WAITING_FOR_AD_USER_IDS = 7

def load_settings():
    """بارگذاری تنظیمات"""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'channels': [], 'lock_enabled': False}

def save_settings(settings):
    """ذخیره تنظیمات"""
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def load_users():
    """بارگذاری لیست کاربران"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_users(users):
    """ذخیره لیست کاربران"""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def add_user(user_id):
    """اضافه کردن کاربر جدید"""
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        save_users(users)

def normalize_channel_id(channel):
    """تبدیل URL کانال به شناسه کانال"""
    if channel.startswith('https://t.me/'):
        username = channel.replace('https://t.me/', '').strip('/')
        return f'@{username}'
    elif channel.startswith('http://t.me/'):
        username = channel.replace('http://t.me/', '').strip('/')
        return f'@{username}'
    elif channel.startswith('t.me/'):
        username = channel.replace('t.me/', '').strip('/')
        return f'@{username}'
    return channel

async def search_vimeo(query_text):
    """جستجو در ویمئو"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'nocheckcertificate': True,
        }
        
        # جستجو با yt-dlp در ویمئو (استفاده از گوگل برای یافتن ویدیوهای ویمئو)
        results = []
        
        # روش دیگر: استفاده از ytsearch و فیلتر کردن نتایج
        with YoutubeDL(ydl_opts) as ydl:
            # جستجوی بیشتر در یوتیوب و یافتن لینک‌های مرتبط
            search_query = f'ytsearch10:{query_text} music video'
            info = ydl.extract_info(search_query, download=False)
            
            if info and 'entries' in info:
                count = 0
                for entry in info['entries']:
                    if entry and count < 5:
                        title = entry.get('title', 'بدون عنوان')
                        duration = entry.get('duration', 0)
                        url = entry.get('url', '') or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                        
                        # فقط ویدیوهایی که "music video" یا مرتبط با موزیک هستند
                        if any(keyword in title.lower() for keyword in ['music', 'official', 'video', 'mv', 'clip']):
                            if duration and duration > 0:
                                duration = int(duration)
                                minutes = duration // 60
                                seconds = duration % 60
                                duration_str = f"{minutes}:{seconds:02d}"
                            else:
                                duration_str = "نامشخص"
                            
                            results.append({
                                'title': title,
                                'url': url,
                                'duration': duration_str,
                                'platform': 'youtube_mv'
                            })
                            count += 1
        
        return results
    except Exception as e:
        print(f"خطا در جستجوی موزیک ویدیو: {e}")
        return []

async def check_user_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی عضویت کاربر در کانال‌ها"""
    settings = load_settings()
    
    if not settings.get('lock_enabled') or not settings.get('channels'):
        return True
    
    user_id = update.effective_user.id
    
    if user_id == ADMIN_ID:
        return True
    
    not_member_channels = []
    
    for channel in settings['channels']:
        try:
            normalized_channel = normalize_channel_id(channel)
            member = await context.bot.get_chat_member(normalized_channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                not_member_channels.append(channel)
        except Exception as e:
            print(f"Error checking {channel} for user {user_id}: {e}")
            not_member_channels.append(channel)
    
    if not_member_channels:
        keyboard = []
        for i, channel in enumerate(not_member_channels, 1):
            normalized_channel = normalize_channel_id(channel)
            
            if normalized_channel.startswith('@'):
                channel_username = normalized_channel[1:]
                channel_url = f"https://t.me/{channel_username}"
            elif normalized_channel.startswith('-100'):
                keyboard.append([InlineKeyboardButton(
                    f"📢 کانال {i} (لطفا دستی عضو شوید)", 
                    callback_data=f'info_{i}'
                )])
                continue
            elif channel.startswith('https://t.me/') or channel.startswith('http://t.me/') or channel.startswith('t.me/'):
                channel_url = channel if channel.startswith('http') else f"https://{channel}"
                channel_username = channel.replace('https://t.me/', '').replace('http://t.me/', '').replace('t.me/', '').strip('/')
            else:
                channel_username = channel
                channel_url = f"https://t.me/{channel_username}"
            
            keyboard.append([InlineKeyboardButton(
                f"📢 عضویت در کانال {i}", 
                url=channel_url
            )])
        
        keyboard.append([InlineKeyboardButton("✅ عضو شدم", callback_data='check_membership')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        channels_list = '\n'.join([f"کانال {i}: {ch}" for i, ch in enumerate(not_member_channels, 1)])
        
        await update.message.reply_text(
            '⚠️ برای استفاده از ربات باید در کانال‌های زیر عضو شوید:\n\n'
            f'{channels_list}\n\n'
            'بعد از عضویت روی "✅ عضو شدم" کلیک کنید.',
            reply_markup=reply_markup
        )
        return False
    
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیام خوش‌آمدگویی و منوی اصلی"""
    user_id = update.effective_user.id
    add_user(user_id)
    
    if not await check_user_membership(update, context):
        return
    
    if user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link')],
            [InlineKeyboardButton("🔍 جستجوی یوتیوب", callback_data='download_name')],
            [InlineKeyboardButton("🔐 مدیریت قفل کانال", callback_data='admin_lock')],
            [InlineKeyboardButton("📢 ارسال تبلیغ", callback_data='admin_broadcast')]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link')],
            [InlineKeyboardButton("🔍 جستجوی یوتیوب", callback_data='download_name')]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        '🎬 به ربات دانلود خوش آمدید!\n\n'
        'لطفا یکی از گزینه‌های زیر را انتخاب کنید:',
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های منو"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == 'check_membership':
        settings = load_settings()
        not_member = []
        
        for channel in settings.get('channels', []):
            try:
                normalized_channel = normalize_channel_id(channel)
                member = await context.bot.get_chat_member(normalized_channel, user_id)
                if member.status in ['left', 'kicked']:
                    not_member.append(channel)
            except Exception as e:
                print(f"Error checking {channel} for user {user_id}: {e}")
                not_member.append(channel)
        
        if not_member:
            await query.answer('❌ هنوز در همه کانال‌ها عضو نشده‌اید!', show_alert=True)
        else:
            await query.answer('✅ عضویت تایید شد!', show_alert=True)
            if user_id == ADMIN_ID:
                keyboard = [
                    [InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link')],
                    [InlineKeyboardButton("🔍 جستجوی یوتیوب", callback_data='download_name')],
                    [InlineKeyboardButton("🔐 مدیریت قفل کانال", callback_data='admin_lock')],
                    [InlineKeyboardButton("📢 ارسال تبلیغ", callback_data='admin_broadcast')]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link')],
                    [InlineKeyboardButton("🔍 جستجوی یوتیوب", callback_data='download_name')]
                ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.edit_text(
                '🎬 به ربات دانلود خوش آمدید!\n\n'
                'لطفا یکی از گزینه‌های زیر را انتخاب کنید:',
                reply_markup=reply_markup
            )
        return
    
    if query.data == 'admin_lock':
        if user_id != ADMIN_ID:
            await query.answer('❌ شما ادمین نیستید!', show_alert=True)
            return
        
        settings = load_settings()
        lock_status = "🔓 غیرفعال" if not settings.get('lock_enabled') else "🔐 فعال"
        channels_text = "\n".join(settings.get('channels', [])) if settings.get('channels') else "هیچ کانالی تنظیم نشده"
        
        keyboard = [
            [InlineKeyboardButton("➕ افزودن کانال", callback_data='add_channel')],
            [InlineKeyboardButton("🗑 حذف کانال‌ها", callback_data='remove_channels')],
            [InlineKeyboardButton(f"{'🔓 غیرفعال کردن' if settings.get('lock_enabled') else '🔐 فعال کردن'}", callback_data='toggle_lock')],
            [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(
            f'🔐 مدیریت قفل کانال\n\n'
            f'وضعیت: {lock_status}\n\n'
            f'کانال‌های تنظیم شده:\n{channels_text}',
            reply_markup=reply_markup
        )
    
    elif query.data == 'add_channel':
        if user_id != ADMIN_ID:
            return
        
        context.user_data['mode'] = WAITING_FOR_CHANNEL_1
        await query.message.edit_text(
            '📢 لطفا آی‌دی کانال اول را ارسال کنید:\n\n'
            '✅ فرمت صحیح:\n'
            '• با یوزرنیم: @channelname\n'
            '• یا آی‌دی عددی: -1001234567890\n'
            '• یا لینک: https://t.me/channelname\n\n'
            '💡 نکات مهم:\n'
            '1️⃣ ربات باید عضو کانال باشد\n'
            '2️⃣ ربات باید ادمین کانال باشد\n'
            '3️⃣ فرمت @ یا -100 یا لینک را فراموش نکنید'
        )
    
    elif query.data == 'remove_channels':
        if user_id != ADMIN_ID:
            return
        
        settings = load_settings()
        settings['channels'] = []
        save_settings(settings)
        
        await query.answer('✅ همه کانال‌ها حذف شدند!', show_alert=True)
        await query.message.edit_text('✅ کانال‌ها حذف شدند.')
        
        await asyncio.sleep(1)
        keyboard = [
            [InlineKeyboardButton("➕ افزودن کانال", callback_data='add_channel')],
            [InlineKeyboardButton("🗑 حذف کانال‌ها", callback_data='remove_channels')],
            [InlineKeyboardButton(f"{'🔓 غیرفعال کردن' if settings.get('lock_enabled') else '🔐 فعال کردن'}", callback_data='toggle_lock')],
            [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            '🔐 مدیریت قفل کانال\n\nکانال‌های تنظیم شده: هیچ کانالی تنظیم نشده',
            reply_markup=reply_markup
        )
    
    elif query.data == 'toggle_lock':
        if user_id != ADMIN_ID:
            return
        
        settings = load_settings()
        settings['lock_enabled'] = not settings.get('lock_enabled', False)
        save_settings(settings)
        
        status = "فعال" if settings['lock_enabled'] else "غیرفعال"
        await query.answer(f'✅ قفل کانال {status} شد!', show_alert=True)
        
        lock_status = "🔓 غیرفعال" if not settings.get('lock_enabled') else "🔐 فعال"
        channels_text = "\n".join(settings.get('channels', [])) if settings.get('channels') else "هیچ کانالی تنظیم نشده"
        
        keyboard = [
            [InlineKeyboardButton("➕ افزودن کانال", callback_data='add_channel')],
            [InlineKeyboardButton("🗑 حذف کانال‌ها", callback_data='remove_channels')],
            [InlineKeyboardButton(f"{'🔓 غیرفعال کردن' if settings.get('lock_enabled') else '🔐 فعال کردن'}", callback_data='toggle_lock')],
            [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(
            f'🔐 مدیریت قفل کانال\n\n'
            f'وضعیت: {lock_status}\n\n'
            f'کانال‌های تنظیم شده:\n{channels_text}',
            reply_markup=reply_markup
        )
    
    elif query.data == 'admin_broadcast':
        if user_id != ADMIN_ID:
            await query.answer('❌ شما ادمین نیستید!', show_alert=True)
            return
        
        users = load_users()
        total_users = len(users)
        
        keyboard = [
            [InlineKeyboardButton("👥 10 کاربر اول", callback_data='broadcast_first_10')],
            [InlineKeyboardButton("👥 10 کاربر آخر", callback_data='broadcast_last_10')],
            [InlineKeyboardButton("👥 100 کاربر اول", callback_data='broadcast_first_100')],
            [InlineKeyboardButton("👥 100 کاربر آخر", callback_data='broadcast_last_100')],
            [InlineKeyboardButton("👥 1000 کاربر اول", callback_data='broadcast_first_1000')],
            [InlineKeyboardButton("👥 1000 کاربر آخر", callback_data='broadcast_last_1000')],
            [InlineKeyboardButton("👥 همه کاربران", callback_data='broadcast_all')],
            [InlineKeyboardButton("🎯 کاربران خاص", callback_data='broadcast_custom')],
            [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(
            f'📢 ارسال تبلیغ\n\n'
            f'تعداد کل کاربران: {total_users}\n\n'
            'لطفا تعداد کاربران مورد نظر را انتخاب کنید:',
            reply_markup=reply_markup
        )
    
    elif query.data.startswith('broadcast_'):
        if user_id != ADMIN_ID:
            return
        
        broadcast_type = query.data.replace('broadcast_', '')
        
        if broadcast_type == 'custom':
            # نمایش لیست کاربران
            users = load_users()
            users_info = []
            
            msg = await query.message.edit_text('⏳ در حال دریافت اطلاعات کاربران...')
            
            for user_id_item in users[:50]:  # محدود به 50 کاربر اول برای جلوگیری از پیام طولانی
                try:
                    chat = await context.bot.get_chat(user_id_item)
                    username = f"@{chat.username}" if chat.username else "بدون یوزرنیم"
                    first_name = chat.first_name or ""
                    last_name = chat.last_name or ""
                    full_name = f"{first_name} {last_name}".strip()
                    
                    users_info.append({
                        'id': user_id_item,
                        'username': username,
                        'name': full_name
                    })
                except Exception:
                    users_info.append({
                        'id': user_id_item,
                        'username': 'نامشخص',
                        'name': 'نامشخص'
                    })
            
            context.user_data['users_info'] = users_info
            context.user_data['mode'] = WAITING_FOR_AD_USER_IDS
            
            users_list = "\n".join([
                f"{idx+1}. {u['name']} - {u['username']} (ID: {u['id']})"
                for idx, u in enumerate(users_info)
            ])
            
            await msg.edit_text(
                f'🎯 لیست کاربران:\n\n'
                f'{users_list}\n\n'
                'لطفا یوزرنیم (@username) یا آی‌دی عددی کاربران را با ویرگول جدا کنید:\n\n'
                'مثال با یوزرنیم:\n'
                '@user1, @user2, @user3\n\n'
                'مثال با آی‌دی:\n'
                '123456789, 987654321\n\n'
                'یا ترکیبی:\n'
                '@user1, 123456789, @user3'
            )
        else:
            context.user_data['broadcast_type'] = broadcast_type
            context.user_data['mode'] = WAITING_FOR_AD_MEDIA
            
            if broadcast_type == 'first_10':
                target_text = '10 کاربر اول'
            elif broadcast_type == 'last_10':
                target_text = '10 کاربر آخر'
            elif broadcast_type == 'first_100':
                target_text = '100 کاربر اول'
            elif broadcast_type == 'last_100':
                target_text = '100 کاربر آخر'
            elif broadcast_type == 'first_1000':
                target_text = '1000 کاربر اول'
            elif broadcast_type == 'last_1000':
                target_text = '1000 کاربر آخر'
            else:
                target_text = 'همه کاربران'
            
            await query.message.edit_text(
                f'📢 ارسال تبلیغ به {target_text}\n\n'
                '1️⃣ لطفا عکس یا ویدیوی تبلیغ را ارسال کنید:\n\n'
                '💡 اگر نمیخواهید مدیا ارسال کنید، /skip بزنید.'
            )
    
    elif query.data == 'download_link':
        context.user_data['mode'] = WAITING_FOR_LINK
        await query.message.reply_text(
            '🔗 لطفا لینک ویدیو را ارسال کنید:\n\n'
            '🎬 یوتیوب: https://www.youtube.com/watch?v=...\n'
            '📷 اینستاگرام: https://www.instagram.com/p/...\n'
            '📷 ریل: https://www.instagram.com/reel/...'
        )
    
    elif query.data == 'download_name':
        context.user_data['mode'] = WAITING_FOR_NAME
        await query.message.reply_text(
            '🔍 لطفا نام ویدیو را وارد کنید:\n\n'
            'مثال: موزیک ویدیو جدید'
        )
    
    elif query.data.startswith('dl_'):
        # دکمه‌های جدید بدون جداسازی
        video_index = int(query.data.split('_')[1])
        search_results = context.user_data.get('search_results', [])
        
        if video_index < len(search_results):
            video = search_results[video_index]
            context.user_data['video_url'] = video['url']
            context.user_data['video_platform'] = 'youtube'  # همه به عنوان یوتیوب
            
            keyboard = [
                [InlineKeyboardButton("📹 4K (2160p)", callback_data='quality_2160p')],
                [InlineKeyboardButton("📹 Full HD (1080p)", callback_data='quality_1080p')],
                [InlineKeyboardButton("📹 HD (720p)", callback_data='quality_720p')],
                [InlineKeyboardButton("📹 SD (480p)", callback_data='quality_480p')],
                [InlineKeyboardButton("📹 Low (360p)", callback_data='quality_360p')],
                [InlineKeyboardButton("🔙 بازگشت به نتایج", callback_data='back_to_search')]
            ]
            
            platform_emoji = '🎬' if video['platform'] == 'youtube' else '🎵'
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.edit_text(
                f'{platform_emoji} یوتیوب\n\n'
                f'{video["title"][:60]}...\n'
                f'⏱ مدت: {video["duration"]}\n\n'
                '📊 لطفا کیفیت دانلود را انتخاب کنید:',
                reply_markup=reply_markup
            )

async def search_youtube(query_text, update, context):
    """جستجو در یوتیوب (عادی + موزیک ویدیو) و نمایش نتایج"""
    try:
        msg = await update.message.reply_text('🔍 در حال جستجو در یوتیوب...')
        
        # جستجو در یوتیوب
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'cookiefile': 'cookies.txt',
            'nocheckcertificate': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        youtube_results = []
        with YoutubeDL(ydl_opts) as ydl:
            search_query = f'ytsearch5:{query_text}'
            info = ydl.extract_info(search_query, download=False)
            
            if info and 'entries' in info:
                for entry in info['entries'][:5]:
                    if entry:
                        title = entry.get('title', 'بدون عنوان')
                        duration = entry.get('duration', 0)
                        url = entry.get('url', '') or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                        
                        if duration and duration > 0:
                            duration = int(duration)
                            minutes = duration // 60
                            seconds = duration % 60
                            duration_str = f"{minutes}:{seconds:02d}"
                        else:
                            duration_str = "نامشخص"
                        
                        youtube_results.append({
                            'title': title,
                            'url': url,
                            'duration': duration_str,
                            'platform': 'youtube'
                        })
        
        # جستجوی موزیک ویدیو (نتایج بیشتر)
        musicvideo_results = await search_vimeo(query_text)
        
        if not youtube_results and not musicvideo_results:
            await msg.edit_text('❌ نتیجه‌ای پیدا نشد. لطفا کلمه دیگری جستجو کنید.')
            await show_main_menu(update, context)
            return
        
        # ترکیب نتایج (بدون جداسازی)
        all_results = []
        for yt in youtube_results:
            all_results.append(yt)
        for mv in musicvideo_results:
            all_results.append(mv)
        
        context.user_data['search_results'] = all_results
        context.user_data['last_search_query'] = query_text
        
        keyboard = []
        
        # دکمه‌ها بدون جداسازی
        for idx, result in enumerate(all_results):
            if result['platform'] == 'youtube':
                platform_emoji = '🎬'
            else:  # youtube_mv
                platform_emoji = '🎵'
            button_text = f"{platform_emoji} {result['title'][:35]}... ({result['duration']})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f'dl_{idx}')])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data='back_to_menu')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f'🔍 نتایج جستجو برای: <b>{query_text}</b>\n\n'
            f'📊 {len(youtube_results)} نتیجه عمومی + {len(musicvideo_results)} موزیک ویدیو = {len(all_results)} نتیجه\n\n'
            'روی ویدیو مورد نظر کلیک کنید:',
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        await update.message.reply_text(
            f'❌ خطا در جستجو:\n{str(e)}\n\n'
            'لطفا دوباره تلاش کنید.'
        )
        await show_main_menu(update, context)

async def download_video(url, update, context):
    """دانلود ویدیو (تشخیص خودکار پلتفرم)"""
    try:
        if 'instagram.com' in url:
            platform = 'instagram'
            msg = await update.message.reply_text('⏳ در حال آماده‌سازی...')
            await download_by_url(url, msg, context, platform, 'best')
            await show_main_menu(update, context)
        else:
            # همه لینک‌ها به عنوان یوتیوب در نظر گرفته میشن
            platform = 'youtube'
            context.user_data['video_url'] = url
            context.user_data['video_platform'] = platform
            
            keyboard = [
                [InlineKeyboardButton("📹 4K (2160p)", callback_data='quality_2160p')],
                [InlineKeyboardButton("📹 Full HD (1080p)", callback_data='quality_1080p')],
                [InlineKeyboardButton("📹 HD (720p)", callback_data='quality_720p')],
                [InlineKeyboardButton("📹 SD (480p)", callback_data='quality_480p')],
                [InlineKeyboardButton("📹 Low (360p)", callback_data='quality_360p')],
                [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_menu')]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                '🎬 یوتیوب\n\n'
                '📊 لطفا کیفیت دانلود را انتخاب کنید:',
                reply_markup=reply_markup
            )
            
    except Exception as e:
        await update.message.reply_text(
            f'❌ خطا:\n{str(e)}\n\n'
            'لطفا لینک صحیح وارد کنید یا دوباره تلاش کنید.'
        )
        await show_main_menu(update, context)

async def download_by_url(url, message, context, platform='youtube', quality='best'):
    """تابع اصلی دانلود ویدیو"""
    try:
        last_update_time = 0
        
        def progress_hook(d):
            nonlocal last_update_time
            import time
            
            current_time = time.time()
            if current_time - last_update_time < 2:
                return
            last_update_time = current_time
            
            if d['status'] == 'downloading':
                try:
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    speed = d.get('speed', 0)
                    eta = d.get('eta', 0)
                    
                    if total > 0:
                        percent = (downloaded / total) * 100
                        filled = int(percent / 5)
                        bar = '█' * filled + '░' * (20 - filled)
                        downloaded_mb = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        speed_mb = (speed / (1024 * 1024)) if speed else 0
                        eta_str = f"{eta}s" if eta else "..."
                        
                        emoji = '🎬' if platform == 'youtube' else '📷'
                        
                        text = (
                            f"{emoji} در حال دانلود...\n\n"
                            f"{bar} {percent:.1f}%\n\n"
                            f"📊 {downloaded_mb:.1f} MB / {total_mb:.1f} MB\n"
                            f"⚡️ {speed_mb:.1f} MB/s\n"
                            f"⏱ باقیمانده: {eta_str}"
                        )
                        
                        asyncio.create_task(message.edit_text(text))
                except Exception:
                    pass
        
        if quality == 'audio':
            format_str = 'bestaudio[ext=m4a]/bestaudio'
            is_audio = True
        elif quality == 'best':
            format_str = 'best'
            is_audio = False
        elif quality == '2160p':
            format_str = 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160]'
            is_audio = False
        elif quality == '1080p':
            format_str = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]'
            is_audio = False
        elif quality == '720p':
            format_str = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]'
            is_audio = False
        elif quality == '480p':
            format_str = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]'
            is_audio = False
        elif quality == '360p':
            format_str = 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]'
            is_audio = False
        else:
            format_str = 'best[height<=720][ext=mp4]/best[height<=480][ext=mp4]/best'
            is_audio = False
        
        ydl_opts = {
            'format': format_str,
            'outtmpl': f'downloads/%(id)s.%(ext)s',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'cookiefile': 'cookies.txt',
            'nocheckcertificate': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'progress_hooks': [progress_hook],
        }
        
        if is_audio:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        os.makedirs('downloads', exist_ok=True)
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if is_audio:
                filename = ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'
            else:
                filename = ydl.prepare_filename(info)
            
            title = info.get('title', 'ویدیو')
            duration = info.get('duration', 0)
            filesize = os.path.getsize(filename)
            
            max_size = 50 * 1024 * 1024
            if filesize > max_size:
                os.remove(filename)
                await message.edit_text(
                    f'❌ حجم فایل بیش از 50 مگابایت است!\n\n'
                    f'📹 {title}\n'
                    f'📊 حجم: {filesize / (1024*1024):.1f} MB\n\n'
                    'لطفا کیفیت پایین‌تری انتخاب کنید.'
                )
                return
            
            upload_start_time = asyncio.get_event_loop().time()
            upload_cancelled = False
            
            async def upload_animation():
                nonlocal upload_cancelled
                animations = ['⬆️', '⬆️⬆️', '⬆️⬆️⬆️', '⬆️⬆️⬆️⬆️']
                idx = 0
                while not upload_cancelled:
                    elapsed = int(asyncio.get_event_loop().time() - upload_start_time)
                    emoji = '🎬' if platform == 'youtube' else '📷'
                    
                    await message.edit_text(
                        f'✅ دانلود کامل!\n\n'
                        f'{emoji} {title[:50]}...\n'
                        f'📊 {filesize / (1024*1024):.1f} MB\n\n'
                        f'📤 در حال ارسال {animations[idx % 4]}\n'
                        f'⏱ زمان: {elapsed}s'
                    )
                    idx += 1
                    await asyncio.sleep(1)
            
            animation_task = asyncio.create_task(upload_animation())
            
            try:
                with open(filename, 'rb') as file:
                    if is_audio:
                        await message.reply_audio(
                            audio=file,
                            caption=f'🎵 {title}',
                            duration=duration if duration else None,
                            read_timeout=600,
                            write_timeout=600,
                            connect_timeout=60,
                            pool_timeout=60
                        )
                    else:
                        await message.reply_video(
                            video=file,
                            caption=f'{"🎵" if platform == "soundcloud" else "🎬" if platform == "youtube" else "📷"} {title}',
                            supports_streaming=True,
                            duration=duration if duration else None,
                            read_timeout=600,
                            write_timeout=600,
                            connect_timeout=60,
                            pool_timeout=60
                        )
            finally:
                upload_cancelled = True
                animation_task.cancel()
                try:
                    await animation_task
                except asyncio.CancelledError:
                    pass
            
            upload_time = int(asyncio.get_event_loop().time() - upload_start_time)
            os.remove(filename)
            
            emoji = '🎬' if platform == 'youtube' else '📷'
            
            await message.edit_text(
                f'✅ ارسال موفق!\n\n'
                f'{emoji} {title[:50]}...\n'
                f'📊 {filesize / (1024*1024):.1f} MB\n'
                f'⏱ زمان آپلود: {upload_time}s'
            )
            
            await asyncio.sleep(3)
            await message.delete()
            
    except Exception as e:
        await message.edit_text(f'❌ خطا: {str(e)}')

async def show_main_menu(update, context):
    """نمایش منوی اصلی"""
    user_id = update.effective_user.id
    
    if user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link')],
            [InlineKeyboardButton("🔍 جستجوی یوتیوب", callback_data='download_name')],
            [InlineKeyboardButton("🔐 مدیریت قفل کانال", callback_data='admin_lock')],
            [InlineKeyboardButton("📢 ارسال تبلیغ", callback_data='admin_broadcast')]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link')],
            [InlineKeyboardButton("🔍 جستجوی یوتیوب", callback_data='download_name')]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        'عملیات بعدی:',
        reply_markup=reply_markup
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت پیام‌های ارسالی"""
    user_id = update.effective_user.id
    user_mode = context.user_data.get('mode', WAITING_FOR_CHOICE)
    
    if user_id != ADMIN_ID and user_mode in [WAITING_FOR_LINK, WAITING_FOR_NAME]:
        if not await check_user_membership(update, context):
            return
    
    if user_mode == WAITING_FOR_LINK:
        url = update.message.text
        await download_video(url, update, context)
        context.user_data['mode'] = WAITING_FOR_CHOICE
        
    elif user_mode == WAITING_FOR_NAME:
        query = update.message.text
        await search_youtube(query, update, context)
        context.user_data['mode'] = WAITING_FOR_CHOICE
    
    elif user_mode == WAITING_FOR_CHANNEL_1:
        if user_id != ADMIN_ID:
            return
        
        channel = update.message.text.strip()
        
        is_valid_format = (
            channel.startswith('@') or 
            channel.startswith('-100') or
            channel.startswith('https://t.me/') or
            channel.startswith('http://t.me/') or
            channel.startswith('t.me/')
        )
        
        if not is_valid_format:
            await update.message.reply_text(
                '❌ فرمت اشتباه است!\n\n'
                '✅ فرمت صحیح:\n'
                '• با @: @channelname\n'
                '• یا آی‌دی عددی: -1001234567890\n'
                '• یا لینک: https://t.me/channelname\n\n'
                'لطفا دوباره ارسال کنید:'
            )
            return
        
        try:
            normalized_channel = normalize_channel_id(channel)
            await context.bot.get_chat(normalized_channel)
            context.user_data['temp_channel_1'] = channel
            context.user_data['mode'] = WAITING_FOR_CHANNEL_2
            
            await update.message.reply_text(
                f'✅ کانال اول: {channel}\n\n'
                '📢 لطفا آی‌دی کانال دوم را ارسال کنید:\n\n'
                '✅ فرمت صحیح:\n'
                '• با @: @channelname\n'
                '• یا آی‌دی عددی: -1001234567890\n'
                '• یا لینک: https://t.me/channelname\n\n'
                '💡 اگر نمیخواهید کانال دوم اضافه کنید، /skip بزنید.'
            )
        except Exception as e:
            await update.message.reply_text(
                f'❌ خطا در اتصال به کانال!\n\n'
                f'دلیل: {str(e)}\n\n'
                '💡 مطمئن شوید:\n'
                '1️⃣ ربات را به کانال اضافه کرده‌اید\n'
                '2️⃣ ربات ادمین کانال است\n'
                '3️⃣ فرمت کانال صحیح است (@channelname یا لینک)\n\n'
                'لطفا دوباره تلاش کنید:'
            )
    
    elif user_mode == WAITING_FOR_CHANNEL_2:
        if user_id != ADMIN_ID:
            return
        
        channel2 = update.message.text.strip()
        
        is_valid_format = (
            channel2.startswith('@') or 
            channel2.startswith('-100') or
            channel2.startswith('https://t.me/') or
            channel2.startswith('http://t.me/') or
            channel2.startswith('t.me/')
        )
        
        if not is_valid_format:
            await update.message.reply_text(
                '❌ فرمت اشتباه است!\n\n'
                '✅ فرمت صحیح:\n'
                '• با @: @channelname\n'
                '• یا آی‌دی عددی: -1001234567890\n'
                '• یا لینک: https://t.me/channelname\n\n'
                '💡 یا /skip برای رد کردن\n\n'
                'لطفا دوباره ارسال کنید:'
            )
            return
        
        try:
            normalized_channel2 = normalize_channel_id(channel2)
            await context.bot.get_chat(normalized_channel2)
            
            settings = load_settings()
            channel1 = context.user_data.get('temp_channel_1', '')
            
            settings['channels'] = [channel1, channel2]
            save_settings(settings)
            context.user_data['mode'] = WAITING_FOR_CHOICE
            
            await update.message.reply_text(
                f'✅ کانال‌ها با موفقیت تنظیم شدند:\n'
                f'1️⃣ {channel1}\n'
                f'2️⃣ {channel2}\n\n'
                '🔐 برای فعال کردن قفل، به بخش "مدیریت قفل کانال" بروید.'
            )
            await show_main_menu(update, context)
            
        except Exception as e:
            await update.message.reply_text(
                f'❌ خطا در اتصال به کانال دوم!\n\n'
                f'دلیل: {str(e)}\n\n'
                '💡 مطمئن شوید:\n'
                '1️⃣ ربات را به کانال اضافه کرده‌اید\n'
                '2️⃣ ربات ادمین کانال است\n'
                '3️⃣ فرمت کانال صحیح است (@channelname یا لینک)\n\n'
                'لطفا دوباره تلاش کنید:'
            )
    
    elif user_mode == WAITING_FOR_AD_USER_IDS:
        if user_id != ADMIN_ID:
            return
        
        user_input = update.message.text.strip()
        users_info = context.user_data.get('users_info', [])
        
        try:
            target_users = []
            inputs = [x.strip() for x in user_input.split(',')]
            
            for inp in inputs:
                if inp.startswith('@'):
                    # جستجوی با یوزرنیم
                    found = False
                    for u in users_info:
                        if u['username'] == inp:
                            target_users.append(u['id'])
                            found = True
                            break
                    if not found:
                        await update.message.reply_text(f'❌ کاربر {inp} پیدا نشد!')
                        return
                else:
                    # آی‌دی عددی
                    try:
                        target_users.append(int(inp))
                    except ValueError:
                        await update.message.reply_text(f'❌ فرمت اشتباه: {inp}')
                        return
            
            context.user_data['custom_user_ids'] = target_users
            context.user_data['broadcast_type'] = 'custom'
            context.user_data['mode'] = WAITING_FOR_AD_MEDIA
            
            await update.message.reply_text(
                f'✅ تعداد {len(target_users)} کاربر انتخاب شد\n\n'
                '1️⃣ لطفا عکس یا ویدیوی تبلیغ را ارسال کنید:\n\n'
                '💡 اگر نمیخواهید مدیا ارسال کنید، /skip بزنید.'
            )
        except Exception as e:
            await update.message.reply_text(
                f'❌ خطا: {str(e)}\n\n'
                'لطفا دوباره تلاش کنید.'
            )
    
    elif user_mode == WAITING_FOR_AD_MEDIA:
        if user_id != ADMIN_ID:
            return
        
        if update.message.photo:
            context.user_data['ad_media_type'] = 'photo'
            context.user_data['ad_media'] = update.message.photo[-1].file_id
        elif update.message.video:
            context.user_data['ad_media_type'] = 'video'
            context.user_data['ad_media'] = update.message.video.file_id
        else:
            context.user_data['ad_media_type'] = None
            context.user_data['ad_media'] = None
        
        context.user_data['mode'] = WAITING_FOR_AD_TEXT
        await update.message.reply_text(
            '✅ مدیا دریافت شد!\n\n'
            '2️⃣ حالا متن تبلیغ را ارسال کنید:\n\n'
            '💡 میتوانید از HTML استفاده کنید:\n'
            '<b>متن بولد</b>\n'
            '<i>متن ایتالیک</i>\n'
            '<a href="https://example.com">لینک</a>'
        )
    
    elif user_mode == WAITING_FOR_AD_TEXT:
        if user_id != ADMIN_ID:
            return
        
        ad_text = update.message.text
        ad_media = context.user_data.get('ad_media')
        ad_media_type = context.user_data.get('ad_media_type')
        broadcast_type = context.user_data.get('broadcast_type', 'all')
        
        users = load_users()
        
        if broadcast_type == 'custom':
            target_users = context.user_data.get('custom_user_ids', [])
        elif broadcast_type == 'first_10':
            target_users = users[:10]
        elif broadcast_type == 'last_10':
            target_users = users[-10:]
        elif broadcast_type == 'first_100':
            target_users = users[:100]
        elif broadcast_type == 'last_100':
            target_users = users[-100:]
        elif broadcast_type == 'first_1000':
            target_users = users[:1000]
        elif broadcast_type == 'last_1000':
            target_users = users[-1000:]
        else:
            target_users = users
        
        success_count = 0
        fail_count = 0
        
        progress_msg = await update.message.reply_text(
            f'📢 در حال ارسال تبلیغ...\n\n'
            f'تعداد کاربران هدف: {len(target_users)}\n'
            f'✅ موفق: 0\n'
            f'❌ ناموفق: 0'
        )
        
        for idx, user_id_to_send in enumerate(target_users):
            try:
                if ad_media and ad_media_type == 'photo':
                    await context.bot.send_photo(
                        chat_id=user_id_to_send,
                        photo=ad_media,
                        caption=ad_text,
                        parse_mode='HTML'
                    )
                elif ad_media and ad_media_type == 'video':
                    await context.bot.send_video(
                        chat_id=user_id_to_send,
                        video=ad_media,
                        caption=ad_text,
                        parse_mode='HTML'
                    )
                else:
                    await context.bot.send_message(
                        chat_id=user_id_to_send,
                        text=ad_text,
                        parse_mode='HTML'
                    )
                success_count += 1
            except Exception:
                fail_count += 1
            
            if (idx + 1) % 10 == 0 or (idx + 1) == len(target_users):
                await progress_msg.edit_text(
                    f'📢 در حال ارسال تبلیغ...\n\n'
                    f'تعداد کاربران هدف: {len(target_users)}\n'
                    f'✅ موفق: {success_count}\n'
                    f'❌ ناموفق: {fail_count}'
                )
            
            await asyncio.sleep(0.05)
        
        context.user_data['mode'] = WAITING_FOR_CHOICE
        
        await progress_msg.edit_text(
            f'✅ ارسال تبلیغ تکمیل شد!\n\n'
            f'تعداد هدف: {len(target_users)}\n'
            f'✅ موفق: {success_count}\n'
            f'❌ ناموفق: {fail_count}'
        )
        
        await show_main_menu(update, context)
    
    else:
        await update.message.reply_text('لطفا از دکمه‌های منو استفاده کنید.')

async def skip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دستور skip"""
    user_id = update.effective_user.id
    user_mode = context.user_data.get('mode', WAITING_FOR_CHOICE)
    
    if user_id != ADMIN_ID:
        return
    
    if user_mode == WAITING_FOR_CHANNEL_1:
        await update.message.reply_text('❌ باید حداقل یک کانال وارد کنید!')
    
    elif user_mode == WAITING_FOR_CHANNEL_2:
        settings = load_settings()
        channel1 = context.user_data.get('temp_channel_1', '')
        settings['channels'] = [channel1]
        save_settings(settings)
        context.user_data['mode'] = WAITING_FOR_CHOICE
        
        await update.message.reply_text(
            f'✅ فقط یک کانال تنظیم شد:\n{channel1}\n\n'
            '🔐 برای فعال کردن قفل، به بخش "مدیریت قفل کانال" بروید.'
        )
        await show_main_menu(update, context)
    
    elif user_mode == WAITING_FOR_AD_MEDIA:
        context.user_data['ad_media_type'] = None
        context.user_data['ad_media'] = None
        context.user_data['mode'] = WAITING_FOR_AD_TEXT
        
        await update.message.reply_text(
            '✅ بدون مدیا!\n\n'
            '2️⃣ حالا متن تبلیغ را ارسال کنید:\n\n'
            '💡 میتوانید از HTML استفاده کنید:\n'
            '<b>متن بولد</b>\n'
            '<i>متن ایتالیک</i>\n'
            '<a href="https://example.com">لینک</a>'
        )

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت callback queryها"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_menu':
        user_id = query.from_user.id
        
        if user_id == ADMIN_ID:
            keyboard = [
                [InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link')],
                [InlineKeyboardButton("🔍 جستجوی یوتیوب", callback_data='download_name')],
                [InlineKeyboardButton("🔐 مدیریت قفل کانال", callback_data='admin_lock')],
                [InlineKeyboardButton("📢 ارسال تبلیغ", callback_data='admin_broadcast')]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link')],
                [InlineKeyboardButton("🔍 جستجوی یوتیوب", callback_data='download_name')]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            '🎬 منوی اصلی:\n\nلطفا یکی از گزینه‌ها را انتخاب کنید:',
            reply_markup=reply_markup
        )
    
    elif query.data == 'back_to_search':
        search_results = context.user_data.get('search_results', [])
        last_search_query = context.user_data.get('last_search_query', '')
        
        if search_results:
            keyboard = []
            
            # دکمه‌ها بدون جداسازی
            for idx, result in enumerate(search_results):
                platform_emoji = '🎬' if result['platform'] == 'youtube' else '🎵'
                button_text = f"{platform_emoji} {result['title'][:35]}... ({result['duration']})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f'dl_{idx}')])
            
            keyboard.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data='back_to_menu')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            youtube_count = sum(1 for r in search_results if r['platform'] == 'youtube')
            mv_count = sum(1 for r in search_results if r['platform'] == 'youtube_mv')
            
            await query.message.edit_text(
                f'🔍 نتایج جستجو برای: <b>{last_search_query}</b>\n\n'
                f'📊 {youtube_count} نتیجه عمومی + {mv_count} موزیک ویدیو = {len(search_results)} نتیجه\n\n'
                'روی ویدیو مورد نظر کلیک کنید:',
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await query.message.edit_text('❌ نتایج جستجو پیدا نشد.')
    
    elif query.data.startswith('quality_'):
        quality = query.data.replace('quality_', '')
        url = context.user_data.get('video_url')
        platform = context.user_data.get('video_platform', 'youtube')
        
        if url:
            await query.message.edit_text('⏳ در حال آماده‌سازی...')
            await download_by_url(url, query.message, context, platform, quality)
            
            user_id = query.from_user.id
            if user_id == ADMIN_ID:
                keyboard = [
                    [InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link')],
                    [InlineKeyboardButton("🔍 جستجوی یوتیوب", callback_data='download_name')],
                    [InlineKeyboardButton("🔐 مدیریت قفل کانال", callback_data='admin_lock')],
                    [InlineKeyboardButton("📢 ارسال تبلیغ", callback_data='admin_broadcast')]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link')],
                    [InlineKeyboardButton("🔍 جستجوی یوتیوب", callback_data='download_name')]
                ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(
                'عملیات بعدی:',
                reply_markup=reply_markup
            )
    
    else:
        await button_handler(update, context)

def main():
    """راه‌اندازی ربات"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("skip", skip_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print('🤖 ربات شروع به کار کرد...')
    app.run_polling()

if __name__ == '__main__':
    main()