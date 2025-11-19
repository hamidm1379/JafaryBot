import os
import telebot
from telebot import types
from yt_dlp import YoutubeDL
import json
import time
import threading
import tempfile
import shutil
import asyncio

# تلاش برای import کردن Pyrogram (اختیاری)
try:
    from pyrogram import Client
    from pyrogram.errors import FloodWait, RPCError
    PYROGRAM_AVAILABLE = True
except ImportError:
    PYROGRAM_AVAILABLE = False
    print("⚠️ Pyrogram نصب نشده است. برای ارسال فایل‌های بزرگ، Pyrogram را نصب کنید: pip install pyrogram")

# توکن ربات تلگرام
TELEGRAM_TOKEN = "8212407334:AAFux0h8ZL-9lnNscQOQkeynMTKg-9lWH5o"
ADMIN_ID = 6097462059

# تنظیمات UserBot (Pyrogram) - برای ارسال فایل‌های بزرگ
# برای دریافت API_ID و API_HASH به https://my.telegram.org/apps بروید
USERBOT_API_ID = 30880278  # API ID خود را اینجا وارد کنید
USERBOT_API_HASH = "1cdd9d628295a59fe9982ae52a208424"  # API Hash خود را اینجا وارد کنید
USERBOT_SESSION_NAME = "userbot_session"  # نام session
USE_USERBOT_FOR_LARGE_FILES = True  # استفاده از UserBot برای همه فایل‌ها (بدون محدودیت 50MB)
USERBOT_THRESHOLD_MB = 0  # حداقل حجم فایل برای استفاده از UserBot (MB) - 0 یعنی همه فایل‌ها

# فایل‌های ذخیره
SETTINGS_FILE = "bot_settings.json"
USERS_FILE = "bot_users.json"
STATS_FILE = "bot_stats.json"

# ایجاد bot
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# کلاینت UserBot (Pyrogram) - در صورت نیاز ایجاد می‌شود
userbot_client = None

# دیکشنری برای ذخیره state کاربران
user_states = {}
user_data = {}

# حالت‌های مختلف
STATE_NONE = 0
STATE_WAITING_LINK = 1
STATE_WAITING_NAME = 2
STATE_WAITING_CHANNEL_1 = 3
STATE_WAITING_CHANNEL_2 = 4
STATE_WAITING_AD_MEDIA = 5
STATE_WAITING_AD_TEXT = 6
STATE_WAITING_AD_USER_IDS = 7

# ==================== توابع مدیریت فایل ====================

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

def load_stats():
    """بارگذاری آمار"""
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'total_downloads': 0}

def save_stats(stats):
    """ذخیره آمار"""
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

def increment_download():
    """افزایش تعداد دانلودها"""
    stats = load_stats()
    stats['total_downloads'] = stats.get('total_downloads', 0) + 1
    save_stats(stats)

def add_user(user_id):
    """اضافه کردن کاربر جدید"""
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        save_users(users)

def normalize_channel_id(channel):
    """تبدیل URL کانال به شناسه"""
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

def get_download_path():
    """دریافت مسیر دانلود با اطمینان از وجود پوشه"""
    # استفاده از پوشه موقت سیستم
    download_dir = os.path.join(tempfile.gettempdir(), 'bot_downloads')
    
    # اگر پوشه وجود نداشت ایجاد کن
    if not os.path.exists(download_dir):
        try:
            os.makedirs(download_dir, exist_ok=True)
            print(f'✅ پوشه دانلود ایجاد شد: {download_dir}')
        except Exception as e:
            print(f'❌ خطا در ایجاد پوشه: {e}')
            # fallback به دایرکتوری جاری
            download_dir = os.path.join(os.getcwd(), 'downloads')
            os.makedirs(download_dir, exist_ok=True)
    
    return download_dir

def cleanup_old_files(download_dir, max_age_hours=1):
    """پاک‌سازی فایل‌های قدیمی"""
    try:
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for filename in os.listdir(download_dir):
            filepath = os.path.join(download_dir, filename)
            
            if os.path.isfile(filepath):
                file_age = current_time - os.path.getmtime(filepath)
                
                if file_age > max_age_seconds:
                    try:
                        os.remove(filepath)
                        print(f'🗑 فایل قدیمی پاک شد: {filename}')
                    except:
                        pass
    except Exception as e:
        print(f'خطا در پاک‌سازی: {e}')

# ==================== مدیریت UserBot (Pyrogram) ====================

def init_userbot():
    """ایجاد و راه‌اندازی UserBot"""
    global userbot_client
    
    if not PYROGRAM_AVAILABLE:
        return False
    
    if not USERBOT_API_ID or not USERBOT_API_HASH:
        print("⚠️ API_ID یا API_HASH تنظیم نشده است. UserBot غیرفعال است.")
        return False
    
    try:
        userbot_client = Client(
            USERBOT_SESSION_NAME,
            api_id=USERBOT_API_ID,
            api_hash=USERBOT_API_HASH
        )
        userbot_client.start()
        print("✅ UserBot با موفقیت راه‌اندازی شد!")
        return True
    except Exception as e:
        print(f"❌ خطا در راه‌اندازی UserBot: {e}")
        return False

def send_file_with_userbot(chat_id, file_path, caption, is_video=False, duration=None):
    """ارسال فایل با استفاده از UserBot (Pyrogram)"""
    global userbot_client
    
    if not PYROGRAM_AVAILABLE or not userbot_client:
        return False, "UserBot در دسترس نیست"
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def send():
            try:
                if is_video:
                    sent_message = await userbot_client.send_video(
                        chat_id=chat_id,
                        video=file_path,
                        caption=caption,
                        supports_streaming=True,
                        duration=duration if duration else None
                    )
                else:
                    sent_message = await userbot_client.send_document(
                        chat_id=chat_id,
                        document=file_path,
                        caption=caption
                    )
                return True, "موفق"
            except FloodWait as e:
                return False, f"FloodWait: {e.value} ثانیه"
            except RPCError as e:
                return False, str(e)
            except Exception as e:
                return False, str(e)
        
        success, message = loop.run_until_complete(send())
        loop.close()
        return success, message
        
    except Exception as e:
        return False, str(e)

# ==================== بررسی عضویت ====================

def check_user_membership(user_id):
    """بررسی عضویت در کانال‌ها"""
    settings = load_settings()
    
    if not settings.get('lock_enabled') or not settings.get('channels'):
        return True, []
    
    if user_id == ADMIN_ID:
        return True, []
    
    not_member_channels = []
    
    for channel in settings['channels']:
        try:
            normalized_channel = normalize_channel_id(channel)
            member = bot.get_chat_member(normalized_channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                not_member_channels.append(channel)
        except Exception as e:
            print(f"Error checking {channel}: {e}")
            not_member_channels.append(channel)
    
    return len(not_member_channels) == 0, not_member_channels

# ==================== جستجو ====================

def search_youtube(query_text):
    """جستجو در یوتیوب"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'nocheckcertificate': True,
            'no_check_certificate': True,
            'geo_bypass': True,
            'socket_timeout': 30,
        }
        
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
        
        results = []
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
                            minutes = int(duration // 60)
                            seconds = int(duration % 60)
                            duration_str = f"{minutes}:{seconds:02d}"
                        else:
                            duration_str = "نامشخص"
                        
                        results.append({
                            'title': title,
                            'url': url,
                            'duration': duration_str,
                            'platform': 'youtube'
                        })
        
        return results
    except Exception as e:
        print(f"خطا در جستجو: {e}")
        return None

def search_music_video(query_text):
    """جستجوی موزیک ویدیو"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'nocheckcertificate': True,
            'no_check_certificate': True,
            'geo_bypass': True,
            'socket_timeout': 30,
        }
        
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
        
        results = []
        with YoutubeDL(ydl_opts) as ydl:
            search_query = f'ytsearch10:{query_text} music video'
            info = ydl.extract_info(search_query, download=False)
            
            if info and 'entries' in info:
                count = 0
                for entry in info['entries']:
                    if entry and count < 5:
                        title = entry.get('title', 'بدون عنوان')
                        duration = entry.get('duration', 0)
                        url = entry.get('url', '') or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                        
                        if any(keyword in title.lower() for keyword in ['music', 'official', 'video', 'mv', 'clip']):
                            if duration and duration > 0:
                                minutes = int(duration // 60)
                                seconds = int(duration % 60)
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
        print(f"خطا در جستجو: {e}")
        return None

# ==================== دانلود ====================

def download_video(url, message, quality='720p'):
    """دانلود ویدیو با ارسال هوشمند (Video/Document)"""
    filename = None
    try:
        # تشخیص user_id
        if hasattr(message, 'from_user'):
            user_id = message.from_user.id
        else:
            chat_id = message.chat.id
            user_id = None
            for uid, data in user_data.items():
                if data.get('download_user_id') and chat_id:
                    user_id = uid
                    break
            if not user_id:
                user_id = chat_id
        
        # انتخاب فرمت بر اساس کیفیت
        if quality == '2160p':
            format_str = 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160]'
        elif quality == '1080p':
            format_str = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]'
        elif quality == '720p':
            format_str = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]'
        elif quality == '480p':
            format_str = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]'
        elif quality == '360p':
            format_str = 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]'
        else:
            format_str = 'best[height<=720]'
        
        last_update_time = [0]
        download_started = [False]
        
        def progress_hook(d):
            try:
                current_time = time.time()
                if current_time - last_update_time[0] < 2:
                    return
                last_update_time[0] = current_time
                
                if d['status'] == 'downloading':
                    download_started[0] = True
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
                        
                        text = (
                            f"🎬 در حال دانلود...\n\n"
                            f"{bar} {percent:.1f}%\n\n"
                            f"📊 {downloaded_mb:.1f} MB / {total_mb:.1f} MB\n"
                            f"⚡️ {speed_mb:.1f} MB/s\n"
                            f"⏱ باقیمانده: {eta_str}"
                        )
                        
                        try:
                            bot.edit_message_text(text, message.chat.id, message.message_id)
                        except:
                            pass
            except:
                pass

        # دریافت مسیر دانلود
        download_dir = get_download_path()
        
        # پاک‌سازی فایل‌های قدیمی
        cleanup_old_files(download_dir)
        
        print(f'📁 مسیر دانلود: {download_dir}')

        ydl_opts = {
            'format': format_str,
            'outtmpl': os.path.join(download_dir, '%(id)s.%(ext)s'),
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'no_check_certificate': True,
            'geo_bypass': True,
            'socket_timeout': 300,  # افزایش timeout برای فایل‌های بزرگ
            'retries': 10,
            'fragment_retries': 10,
            'progress_hooks': [progress_hook],
            'http_chunk_size': 10485760,  # 10MB chunks برای دانلود بهتر فایل‌های بزرگ
        }
        
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
        
        print('📥 شروع دانلود...')
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            title = info.get('title', 'ویدیو')
            duration = info.get('duration', 0)
            
            print(f'✅ دانلود کامل: {filename}')
            
            # بررسی وجود فایل
            if not os.path.exists(filename):
                raise Exception(f'فایل دانلود نشد: {filename}')
            
            filesize = os.path.getsize(filename)
            print(f'📊 حجم فایل: {filesize / (1024*1024):.2f} MB')
            
            # محدودیت تلگرام: 1500 مگابایت (1.5 GB) برای جلوگیری از خطای 413
            # در عمل تلگرام ممکن است فایل‌های بالای 1.5 GB را رد کند
            max_size = 1500 * 1024 * 1024
            
            if filesize > max_size:
                os.remove(filename)
                bot.edit_message_text(
                    f'❌ حجم فایل بیش از 1.5 GB!\n\n'
                    f'📹 {title}\n'
                    f'📊 حجم: {filesize / (1024*1024):.1f} MB\n\n'
                    '💡 محدودیت تلگرام برای ارسال فایل 1.5 GB است.\n'
                    'لطفا کیفیت پایین‌تری انتخاب کنید.',
                    message.chat.id,
                    message.message_id
                )
                return
            
            # تصمیم‌گیری: استفاده از UserBot یا ربات عادی
            # استفاده از UserBot برای همه فایل‌ها (بدون محدودیت حجم)
            use_userbot = (
                USE_USERBOT_FOR_LARGE_FILES and 
                PYROGRAM_AVAILABLE and 
                userbot_client
            )
            
            # تصمیم‌گیری هوشمند: Video یا Document
            # با UserBot: همه ویدیوها به صورت ویدیو ارسال می‌شوند (بدون محدودیت 50MB)
            # با ربات عادی: فایل‌های بالای 50MB به صورت Document ارسال می‌شوند
            if use_userbot:
                # با UserBot می‌توانیم همه ویدیوها را به صورت ویدیو ارسال کنیم
                send_as_document = False
            else:
                # با ربات عادی، فایل‌های بالای 50MB باید به صورت document ارسال شوند
                send_as_document = filesize > 50 * 1024 * 1024
            
            # هشدار برای فایل‌های بزرگ (فقط برای ربات عادی)
            if send_as_document and not use_userbot:
                try:
                    bot.edit_message_text(
                        f'📁 فایل بزرگ است!\n\n'
                        f'📹 {title[:50]}...\n'
                        f'📊 حجم: {filesize / (1024*1024):.1f} MB\n\n'
                        f'💡 به صورت فایل ارسال میشه\n'
                        f'⏳ چند دقیقه صبر کنید...',
                        message.chat.id,
                        message.message_id
                    )
                    time.sleep(2)
                except:
                    pass
            
            upload_cancelled = [False]
            
            def upload_animation():
                animations = ['⬆️', '⬆️⬆️', '⬆️⬆️⬆️', '⬆️⬆️⬆️⬆️']
                idx = 0
                start_time = time.time()
                
                while not upload_cancelled[0]:
                    try:
                        elapsed = int(time.time() - start_time)
                        file_type = "📁 فایل" if send_as_document else "🎬 ویدیو"
                        bot_used = "🤖 UserBot" if use_userbot else "🤖 ربات"
                        bot.edit_message_text(
                            f'✅ دانلود کامل!\n\n'
                            f'{file_type}: {title[:40]}...\n'
                            f'📊 {filesize / (1024*1024):.1f} MB\n'
                            f'{bot_used}\n\n'
                            f'📤 در حال ارسال {animations[idx % 4]}\n'
                            f'⏱ زمان: {elapsed}s',
                            message.chat.id,
                            message.message_id
                        )
                    except:
                        pass
                    idx += 1
                    time.sleep(1)
            
            upload_thread = threading.Thread(target=upload_animation)
            upload_thread.daemon = True
            upload_thread.start()
            
            upload_start_time = time.time()
            
            print(f'📤 شروع آپلود به صورت {"Document" if send_as_document else "Video"}...')
            
            if use_userbot:
                print(f'🤖 استفاده از UserBot برای ارسال فایل {filesize / (1024*1024):.1f} MB')
                try:
                    caption = f'📁 {title}\n\n📊 حجم: {filesize / (1024*1024):.1f} MB\n\n💡 فایل رو دانلود کنید و پخش کنید\n\n@DanceMoviebot' if send_as_document else f'🎬 {title}\n\n📊 حجم: {filesize / (1024*1024):.1f} MB\n@DanceMoviebot'
                    
                    success, error_msg = send_file_with_userbot(
                        message.chat.id,
                        filename,
                        caption,
                        is_video=(not send_as_document),
                        duration=duration if duration else None
                    )
                    
                    if success:
                        print('✅ آپلود موفق با UserBot')
                        upload_cancelled[0] = True
                    else:
                        print(f'⚠️ خطا در ارسال با UserBot: {error_msg}')
                        print('🔄 تلاش با ربات عادی...')
                        use_userbot = False  # fallback به ربات عادی
                except Exception as e:
                    print(f'⚠️ خطا در UserBot: {e}')
                    print('🔄 تلاش با ربات عادی...')
                    use_userbot = False
            
            if not use_userbot:
                # استفاده از ربات عادی (pyTelegramBotAPI)
                try:
                    # Timeout بر اساس حجم - برای فایل‌های بزرگ timeout بیشتر
                    if filesize > 500 * 1024 * 1024:  # بالای 500 MB
                        upload_timeout = 1800  # 30 دقیقه
                    elif filesize > 100 * 1024 * 1024:  # بالای 100 MB
                        upload_timeout = 1200  # 20 دقیقه
                    elif filesize > 50 * 1024 * 1024:  # بالای 50 MB
                        upload_timeout = 900  # 15 دقیقه
                    else:
                        upload_timeout = 600  # 10 دقیقه
                    
                    # استفاده از InputFile برای فایل‌های بزرگ
                    # برای فایل‌های بزرگ، از مسیر فایل مستقیم استفاده می‌کنیم
                    if send_as_document:
                        # ارسال به صورت فایل (Document) - استفاده از مسیر فایل
                        with open(filename, 'rb') as file:
                            bot.send_document(
                                message.chat.id,
                                file,
                                caption=f'📁 {title}\n\n📊 حجم: {filesize / (1024*1024):.1f} MB\n\n💡 فایل رو دانلود کنید و پخش کنید\n\n@DanceMoviebot',
                                timeout=upload_timeout,
                                visible_file_name=f'{title[:50]}.mp4'
                            )
                    else:
                        # ارسال به صورت ویدیو (پخش مستقیم)
                        with open(filename, 'rb') as file:
                            bot.send_video(
                                message.chat.id,
                                file,
                                caption=f'🎬 {title}\n\n📊 حجم: {filesize / (1024*1024):.1f} MB\n@DanceMoviebot',
                                supports_streaming=True,
                                duration=duration if duration else None,
                                timeout=upload_timeout
                            )
                    
                    print('✅ آپلود موفق')
                    upload_cancelled[0] = True
                except Exception as upload_error:
                    error_str = str(upload_error)
                    error_code = getattr(upload_error, 'error_code', None)
                    
                    # لاگ خطا برای دیباگ
                    print(f'❌ خطا در آپلود: {error_str}')
                    print(f'📊 کد خطا: {error_code}')
                    print(f'📁 حجم فایل: {filesize / (1024*1024):.2f} MB')
                    
                    upload_cancelled[0] = True
                    
                    # بررسی خطای 413 (Request Entity Too Large)
                    if '413' in error_str or (error_code and error_code == 413) or 'Request Entity Too Large' in error_str or 'entity too large' in error_str.lower():
                        try:
                            if filename and os.path.exists(filename):
                                os.remove(filename)
                        except:
                            pass
                        
                        bot.edit_message_text(
                            f'❌ خطا: فایل خیلی بزرگ است!\n\n'
                            f'📹 {title[:50]}...\n'
                            f'📊 حجم: {filesize / (1024*1024):.1f} MB\n\n'
                            f'💡 تلگرام نمی‌تواند این فایل را بپذیرد.\n\n'
                            f'راه حل:\n'
                            f'1️⃣ کیفیت پایین‌تری انتخاب کنید (480p یا 360p)\n'
                            f'2️⃣ ویدیو کوتاه‌تری انتخاب کنید\n'
                            f'3️⃣ چند دقیقه صبر کنید و دوباره تلاش کنید',
                            message.chat.id,
                            message.message_id
                        )
                        return
                    else:
                        # برای خطاهای دیگر، پیام مناسب نمایش بده
                        try:
                            if filename and os.path.exists(filename):
                                os.remove(filename)
                        except:
                            pass
                        
                        # نمایش پیام خطا با جزئیات
                        error_msg = error_str[:200] if len(error_str) > 200 else error_str
                        bot.edit_message_text(
                            f'❌ خطا در ارسال فایل!\n\n'
                            f'📹 {title[:50]}...\n'
                            f'📊 حجم: {filesize / (1024*1024):.1f} MB\n\n'
                            f'💡 خطا: {error_msg}\n\n'
                            f'راه حل:\n'
                            f'1️⃣ چند دقیقه صبر کنید و دوباره تلاش کنید\n'
                            f'2️⃣ کیفیت پایین‌تری انتخاب کنید\n'
                            f'3️⃣ لینک دیگری امتحان کنید',
                            message.chat.id,
                            message.message_id
                        )
                        return
                finally:
                    if not upload_cancelled[0]:
                        upload_cancelled[0] = True
                    time.sleep(0.5)
            
            upload_time = int(time.time() - upload_start_time)
            
            # پاک کردن فایل
            try:
                if filename and os.path.exists(filename):
                    os.remove(filename)
                    print('🗑 فایل پاک شد')
            except Exception as e:
                print(f'خطا در پاک کردن فایل: {e}')
            
            try:
                file_type_emoji = "📁" if send_as_document else "🎬"
                bot.edit_message_text(
                    f'✅ ارسال موفق!\n\n'
                    f'{file_type_emoji} {title[:50]}...\n'
                    f'📊 {filesize / (1024*1024):.1f} MB\n'
                    f'⏱ زمان آپلود: {upload_time}s',
                    message.chat.id,
                    message.message_id
                )
                
                time.sleep(2)
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            
            increment_download()
            
            show_main_menu(message.chat.id, user_id)
            
    except Exception as e:
        error_message = str(e)
        print(f'❌ خطا در دانلود: {error_message}')
        
        # پاک کردن فایل در صورت خطا
        try:
            if filename and os.path.exists(filename):
                os.remove(filename)
                print('🗑 فایل ناقص پاک شد')
        except:
            pass
        
        if any(x in error_message.lower() for x in ['timeout', 'timed out', 'connection', 'proxy', 'tunnel']):
            try:
                bot.edit_message_text(
                    f'❌ خطا در دانلود!\n\n'
                    f'💡 احتمالاً مشکل از اتصال به اینترنت است.\n\n'
                    f'راه حل:\n'
                    f'1️⃣ لینک دیگری امتحان کنید\n'
                    f'2️⃣ کیفیت پایین‌تر انتخاب کنید\n'
                    f'3️⃣ چند دقیقه دیگر تلاش کنید',
                    message.chat.id,
                    message.message_id
                )
            except:
                pass
        else:
            try:
                bot.edit_message_text(
                    f'❌ خطا در دانلود!\n\n'
                    f'جزئیات: {error_message[:100]}\n\n'
                    f'لطفا دوباره تلاش کنید.',
                    message.chat.id,
                    message.message_id
                )
            except:
                pass

# ==================== کیبوردها ====================

def main_menu_keyboard(user_id):
    """کیبورد منوی اصلی"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📥 دانلود با لینک", callback_data='download_link'),
        types.InlineKeyboardButton("🔍 جست و جوی موزیک ویدیو", callback_data='download_name')
    )
    
    if user_id == ADMIN_ID:
        markup.add(
            types.InlineKeyboardButton("🔐 مدیریت قفل کانال", callback_data='admin_lock'),
            types.InlineKeyboardButton("📢 ارسال تبلیغ", callback_data='admin_broadcast'),
            types.InlineKeyboardButton("📊 وضعیت کاربران", callback_data='admin_stats')
        )
    
    return markup

def reply_keyboard_menu(user_id):
    """کیبورد ثابت پایین صفحه"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("🏠 منو اصلی"))
    return markup

def quality_keyboard():
    """کیبورد انتخاب کیفیت"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📹 4K (2160p)", callback_data='quality_2160p'),
        types.InlineKeyboardButton("📹 Full HD (1080p)", callback_data='quality_1080p'),
        types.InlineKeyboardButton("📹 HD (720p)", callback_data='quality_720p'),
        types.InlineKeyboardButton("📹 SD (480p)", callback_data='quality_480p'),
        types.InlineKeyboardButton("📹 Low (360p)", callback_data='quality_360p'),
        types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data='back_to_menu')
    )
    return markup

def show_main_menu(chat_id, user_id, text='🎬 عملیات بعدی:\n\nلطفا یکی از گزینه‌ها را انتخاب کنید:'):
    """نمایش منوی اصلی"""
    if isinstance(user_id, int):
        actual_user_id = user_id
    else:
        actual_user_id = chat_id
    
    bot.send_message(chat_id, text, reply_markup=main_menu_keyboard(actual_user_id))

# ==================== Handlers ====================

@bot.message_handler(commands=['start'])
def start_command(message):
    """دستور start"""
    user_id = message.from_user.id
    add_user(user_id)
    
    bot.send_message(
        message.chat.id,
        '✅ کیبورد منو فعال شد!',
        reply_markup=reply_keyboard_menu(user_id)
    )
    
    is_member, not_member_channels = check_user_membership(user_id)
    
    if not is_member:
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for i, channel in enumerate(not_member_channels, 1):
            normalized_channel = normalize_channel_id(channel)
            
            if normalized_channel.startswith('@'):
                channel_username = normalized_channel[1:]
                channel_url = f"https://t.me/{channel_username}"
            else:
                channel_url = channel if channel.startswith('http') else f"https://t.me/{channel}"
            
            markup.add(types.InlineKeyboardButton(f"📢 عضویت در کانال {i}", url=channel_url))
        
        markup.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data='check_membership'))
        
        bot.send_message(
            message.chat.id,
            '⚠️ برای استفاده از ربات باید در کانال‌های زیر عضو شوید:\n\n'
            'بعد از عضویت روی "✅ عضو شدم" کلیک کنید.',
            reply_markup=markup
        )
        return
    
    bot.send_message(
        message.chat.id,
        '🎬 به ربات Dance Movie خوش آمدید!\n\n'
        'لطفا یکی از گزینه‌های زیر را انتخاب کنید:',
        reply_markup=main_menu_keyboard(user_id)
    )

@bot.message_handler(commands=['skip'])
def skip_command(message):
    """دستور skip"""
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        return
    
    state = user_states.get(user_id, STATE_NONE)
    
    if state == STATE_WAITING_CHANNEL_2:
        settings = load_settings()
        channel1 = user_data.get(user_id, {}).get('temp_channel_1', '')
        settings['channels'] = [channel1]
        save_settings(settings)
        user_states[user_id] = STATE_NONE
        
        bot.send_message(message.chat.id, f'✅ فقط یک کانال تنظیم شد: {channel1}')
        show_main_menu(message.chat.id, user_id)
    
    elif state == STATE_WAITING_AD_MEDIA:
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['ad_media_type'] = None
        user_data[user_id]['ad_media'] = None
        user_states[user_id] = STATE_WAITING_AD_TEXT
        
        bot.send_message(
            message.chat.id,
            '✅ بدون مدیا!\n\n'
            '2️⃣ حالا متن تبلیغ را ارسال کنید:\n\n'
            '💡 میتوانید از HTML استفاده کنید:\n'
            '<b>متن بولد</b>\n'
            '<i>متن ایتالیک</i>'
        )

@bot.message_handler(func=lambda message: message.text == '🏠 منو اصلی')
def keyboard_menu_handler(message):
    """مدیریت دکمه کیبورد ثابت"""
    user_id = message.from_user.id
    
    if user_id in user_states:
        user_states[user_id] = STATE_NONE
    
    bot.send_message(
        message.chat.id,
        '🎬 منوی اصلی:\n\nلطفا یکی از گزینه‌ها را انتخاب کنید:',
        reply_markup=main_menu_keyboard(user_id)
    )

@bot.message_handler(content_types=['text'])
def text_handler(message):
    """مدیریت پیام‌های متنی"""
    user_id = message.from_user.id
    state = user_states.get(user_id, STATE_NONE)
    
    if user_id != ADMIN_ID and state in [STATE_WAITING_LINK, STATE_WAITING_NAME]:
        is_member, _ = check_user_membership(user_id)
        if not is_member:
            start_command(message)
            return
    
    if state == STATE_WAITING_LINK:
        url = message.text
        msg = bot.send_message(message.chat.id, '⏳ در حال آماده‌سازی...')
        
        if 'instagram.com' in url:
            download_video(url, msg, 'best')
        else:
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]['video_url'] = url
            
            bot.edit_message_text(
                '🎬 یوتیوب\n\n'
                '📊 لطفا کیفیت دانلود را انتخاب کنید:',
                message.chat.id,
                msg.message_id,
                reply_markup=quality_keyboard()
            )
        
        user_states[user_id] = STATE_NONE
    
    elif state == STATE_WAITING_NAME:
        query = message.text
        msg = bot.send_message(message.chat.id, '🔍 در حال جستجو...')
        
        youtube_results = search_youtube(query)
        musicvideo_results = search_music_video(query)
        
        if youtube_results is None or musicvideo_results is None:
            bot.edit_message_text(
                '❌ متأسفانه نمی‌تونه به یوتیوب دسترسی داشته باشه!\n\n'
                '💡 راه حل:\n'
                '1️⃣ از "📥 دانلود با لینک" استفاده کنید\n'
                '2️⃣ لینک یوتیوب رو کپی کنید و بفرستید',
                message.chat.id,
                msg.message_id
            )
            user_states[user_id] = STATE_NONE
            return
        
        if not youtube_results and not musicvideo_results:
            bot.edit_message_text(
                '❌ نتیجه‌ای پیدا نشد.\n\n'
                '💡 بجای جستجو، لینک ویدیو رو مستقیم بفرستید:',
                message.chat.id,
                msg.message_id
            )
            user_states[user_id] = STATE_NONE
            return
        
        all_results = youtube_results + musicvideo_results
        
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['search_results'] = all_results
        user_data[user_id]['last_search_query'] = query
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for idx, result in enumerate(all_results):
            platform_emoji = '🎬' if result['platform'] == 'youtube' else '🎵'
            button_text = f"{platform_emoji} {result['title'][:35]}... ({result['duration']})"
            markup.add(types.InlineKeyboardButton(button_text, callback_data=f'dl_{idx}'))
        
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data='back_to_menu'))
        
        bot.edit_message_text(
            f'🔍 نتایج جستجو برای: <b>{query}</b>\n\n'
            f'📊 {len(youtube_results)} نتیجه عمومی + {len(musicvideo_results)} موزیک ویدیو = {len(all_results)} نتیجه\n\n'
            'روی ویدیو مورد نظر کلیک کنید:',
            message.chat.id,
            msg.message_id,
            reply_markup=markup,
            parse_mode='HTML'
        )
        
        user_states[user_id] = STATE_NONE
    
    elif state == STATE_WAITING_CHANNEL_1:
        if user_id != ADMIN_ID:
            return
        
        channel = message.text.strip()
        
        is_valid_format = (
            channel.startswith('@') or 
            channel.startswith('-100') or
            channel.startswith('https://t.me/') or
            channel.startswith('http://t.me/') or
            channel.startswith('t.me/')
        )
        
        if not is_valid_format:
            bot.send_message(
                message.chat.id,
                '❌ فرمت اشتباه است!\n\n'
                '✅ فرمت صحیح:\n'
                '• با @: @channelname\n'
                '• یا آی‌دی عددی: -1001234567890\n'
                '• یا لینک: https://t.me/channelname'
            )
            return
        
        try:
            normalized_channel = normalize_channel_id(channel)
            bot.get_chat(normalized_channel)
            
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]['temp_channel_1'] = channel
            user_states[user_id] = STATE_WAITING_CHANNEL_2
            
            bot.send_message(
                message.chat.id,
                f'✅ کانال اول: {channel}\n\n'
                '📢 لطفا آی‌دی کانال دوم را ارسال کنید یا /skip بزنید:'
            )
        except Exception as e:
            bot.send_message(
                message.chat.id,
                f'❌ خطا: {str(e)}\n\nلطفا دوباره تلاش کنید.'
            )
    
    elif state == STATE_WAITING_CHANNEL_2:
        if user_id != ADMIN_ID:
            return
        
        channel2 = message.text.strip()
        
        try:
            normalized_channel2 = normalize_channel_id(channel2)
            bot.get_chat(normalized_channel2)
            
            settings = load_settings()
            channel1 = user_data.get(user_id, {}).get('temp_channel_1', '')
            settings['channels'] = [channel1, channel2]
            save_settings(settings)
            user_states[user_id] = STATE_NONE
            
            bot.send_message(
                message.chat.id,
                f'✅ کانال‌ها تنظیم شدند:\n1️⃣ {channel1}\n2️⃣ {channel2}'
            )
            
            show_main_menu(message.chat.id, user_id)
            
        except Exception as e:
            bot.send_message(
                message.chat.id,
                f'❌ خطا: {str(e)}'
            )
    
    elif state == STATE_WAITING_AD_TEXT:
        if user_id != ADMIN_ID:
            return
        
        ad_text = message.text
        ad_media = user_data.get(user_id, {}).get('ad_media')
        ad_media_type = user_data.get(user_id, {}).get('ad_media_type')
        broadcast_type = user_data.get(user_id, {}).get('broadcast_type', 'all')
        
        users = load_users()
        
        if broadcast_type == 'first_10':
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
        
        progress_msg = bot.send_message(
            message.chat.id,
            f'📢 در حال ارسال تبلیغ...\n\n'
            f'تعداد کاربران هدف: {len(target_users)}\n'
            f'✅ موفق: 0\n'
            f'❌ ناموفق: 0'
        )
        
        for idx, user_id_to_send in enumerate(target_users):
            try:
                if ad_media and ad_media_type == 'photo':
                    bot.send_photo(
                        user_id_to_send,
                        ad_media,
                        caption=ad_text,
                        parse_mode='HTML'
                    )
                elif ad_media and ad_media_type == 'video':
                    bot.send_video(
                        user_id_to_send,
                        ad_media,
                        caption=ad_text,
                        parse_mode='HTML'
                    )
                else:
                    bot.send_message(
                        user_id_to_send,
                        ad_text,
                        parse_mode='HTML'
                    )
                success_count += 1
            except:
                fail_count += 1
            
            if (idx + 1) % 10 == 0 or (idx + 1) == len(target_users):
                bot.edit_message_text(
                    f'📢 در حال ارسال تبلیغ...\n\n'
                    f'تعداد کاربران هدف: {len(target_users)}\n'
                    f'✅ موفق: {success_count}\n'
                    f'❌ ناموفق: {fail_count}',
                    message.chat.id,
                    progress_msg.message_id
                )
            
            time.sleep(0.05)
        
        user_states[user_id] = STATE_NONE
        
        bot.edit_message_text(
            f'✅ ارسال تبلیغ تکمیل شد!\n\n'
            f'تعداد هدف: {len(target_users)}\n'
            f'✅ موفق: {success_count}\n'
            f'❌ ناموفق: {fail_count}',
            message.chat.id,
            progress_msg.message_id
        )
        
        show_main_menu(message.chat.id, user_id)

@bot.message_handler(content_types=['photo', 'video'])
def media_handler(message):
    """مدیریت رسانه‌ها"""
    user_id = message.from_user.id
    state = user_states.get(user_id, STATE_NONE)
    
    if state == STATE_WAITING_AD_MEDIA and user_id == ADMIN_ID:
        if message.photo:
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]['ad_media_type'] = 'photo'
            user_data[user_id]['ad_media'] = message.photo[-1].file_id
        elif message.video:
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]['ad_media_type'] = 'video'
            user_data[user_id]['ad_media'] = message.video.file_id
        
        user_states[user_id] = STATE_WAITING_AD_TEXT
        
        bot.send_message(
            message.chat.id,
            '✅ مدیا دریافت شد!\n\n'
            '2️⃣ حالا متن تبلیغ را ارسال کنید:'
        )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """مدیریت callback queryها"""
    user_id = call.from_user.id
    
    if call.data == 'check_membership':
        is_member, _ = check_user_membership(user_id)
        
        if is_member:
            bot.answer_callback_query(call.id, '✅ عضویت تایید شد!')
            bot.edit_message_text(
                '🎬 به ربات دانلود خوش آمدید!\n\n'
                'لطفا یکی از گزینه‌های زیر را انتخاب کنید:',
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_menu_keyboard(user_id)
            )
        else:
            bot.answer_callback_query(call.id, '❌ هنوز در همه کانال‌ها عضو نشده‌اید!', show_alert=True)
    
    elif call.data == 'download_link':
        user_states[user_id] = STATE_WAITING_LINK
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data='back_to_menu'))
        
        bot.send_message(
            call.message.chat.id,
            '🔗 لطفا لینک موزیک ویدیو را ارسال کنید:\n\n'
            '🎬 یوتیوب: https://www.youtube.com/watch?v=...\n'
            '📷 اینستاگرام: https://www.instagram.com/...',
            reply_markup=markup
        )
    
    elif call.data == 'download_name':
        user_states[user_id] = STATE_WAITING_NAME
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data='back_to_menu'))
        
        bot.send_message(
            call.message.chat.id,
            '🔍 لطفا نام موزیک ویدیو مورد نظرتون رو وارد کنید :',
            reply_markup=markup
        )
    
    elif call.data == 'admin_lock':
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, '❌ شما ادمین نیستید!', show_alert=True)
            return
        
        settings = load_settings()
        lock_status = "🔐 فعال" if settings.get('lock_enabled') else "🔓 غیرفعال"
        channels_text = "\n".join(settings.get('channels', [])) if settings.get('channels') else "هیچ کانالی تنظیم نشده"
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("➕ افزودن کانال", callback_data='add_channel'),
            types.InlineKeyboardButton("🗑 حذف کانال‌ها", callback_data='remove_channels'),
            types.InlineKeyboardButton(f"{'🔓 غیرفعال کردن' if settings.get('lock_enabled') else '🔐 فعال کردن'}", callback_data='toggle_lock'),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_menu')
        )
        
        bot.edit_message_text(
            f'🔐 مدیریت قفل کانال\n\n'
            f'(ابتدا ربات رو به عنوان ادمین عضو کانال مد نظر کنید سپس دسترسی عضو کردن رو به ربات بدید)\n\n'
            f'وضعیت: {lock_status}\n\n'
            f'کانال‌های تنظیم شده:\n{channels_text}',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data == 'add_channel':
        if user_id != ADMIN_ID:
            return
        
        user_states[user_id] = STATE_WAITING_CHANNEL_1
        bot.edit_message_text(
            '📢 لطفا آی‌دی کانال اول را ارسال کنید:\n\n'
            '✅ فرمت صحیح:\n'
            '• با @: @channelname\n'
            '• یا آی‌دی عددی: -1001234567890\n'
            '• یا لینک: https://t.me/channelname',
            call.message.chat.id,
            call.message.message_id
        )
    
    elif call.data == 'remove_channels':
        if user_id != ADMIN_ID:
            return
        
        settings = load_settings()
        settings['channels'] = []
        save_settings(settings)
        
        bot.answer_callback_query(call.id, '✅ همه کانال‌ها حذف شدند!')
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data='back_to_menu'))
        
        bot.edit_message_text(
            '✅ کانال‌ها حذف شدند.',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data == 'toggle_lock':
        if user_id != ADMIN_ID:
            return
        
        settings = load_settings()
        settings['lock_enabled'] = not settings.get('lock_enabled', False)
        save_settings(settings)
        
        status = "فعال" if settings['lock_enabled'] else "غیرفعال"
        bot.answer_callback_query(call.id, f'✅ قفل کانال {status} شد!')
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data='back_to_menu'))
        
        bot.edit_message_text(
            f'✅ قفل کانال {status} شد!',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data == 'admin_broadcast':
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, '❌ شما ادمین نیستید!', show_alert=True)
            return
        
        users = load_users()
        total_users = len(users)
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("👥 10 کاربر اول", callback_data='broadcast_first_10'),
            types.InlineKeyboardButton("👥 10 کاربر آخر", callback_data='broadcast_last_10'),
            types.InlineKeyboardButton("👥 100 کاربر اول", callback_data='broadcast_first_100'),
            types.InlineKeyboardButton("👥 100 کاربر آخر", callback_data='broadcast_last_100'),
            types.InlineKeyboardButton("👥 1000 کاربر اول", callback_data='broadcast_first_1000'),
            types.InlineKeyboardButton("👥 1000 کاربر آخر", callback_data='broadcast_last_1000'),
            types.InlineKeyboardButton("👥 همه کاربران", callback_data='broadcast_all'),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_menu')
        )
        
        bot.edit_message_text(
            f'📢 ارسال تبلیغ\n\n'
            f'تعداد کل کاربران: {total_users}\n\n'
            'لطفا تعداد کاربران مورد نظر را انتخاب کنید:',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data.startswith('broadcast_'):
        if user_id != ADMIN_ID:
            return
        
        broadcast_type = call.data.replace('broadcast_', '')
        
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['broadcast_type'] = broadcast_type
        user_states[user_id] = STATE_WAITING_AD_MEDIA
        
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
        
        bot.edit_message_text(
            f'📢 ارسال تبلیغ به {target_text}\n\n'
            '1️⃣ لطفا عکس یا ویدیوی تبلیغ را ارسال کنید:\n\n'
            '💡 اگر نمیخواهید مدیا ارسال کنید، /skip بزنید.',
            call.message.chat.id,
            call.message.message_id
        )
    
    elif call.data == 'admin_stats':
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, '❌ شما ادمین نیستید!', show_alert=True)
            return
        
        users = load_users()
        stats = load_stats()
        total_users = len(users)
        total_downloads = stats.get('total_downloads', 0)
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📥 دریافت لیست کاربران", callback_data='export_users'),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_menu')
        )
        
        bot.edit_message_text(
            f'📊 وضعیت کاربران\n\n'
            f'👥 تعداد کل کاربران: {total_users}\n'
            f'📥 تعداد کل دانلودها: {total_downloads}\n\n'
            f'💡 برای دریافت لیست کامل کاربران روی دکمه زیر کلیک کنید:',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif call.data == 'export_users':
        if user_id != ADMIN_ID:
            return
        
        users = load_users()
        
        txt_content = "لیست کاربران ربات\n"
        txt_content += "=" * 50 + "\n\n"
        txt_content += f"تعداد کل کاربران: {len(users)}\n\n"
        txt_content += "=" * 50 + "\n\n"
        
        for idx, user_id_item in enumerate(users, 1):
            try:
                chat = bot.get_chat(user_id_item)
                username = f"@{chat.username}" if chat.username else "بدون یوزرنیم"
                first_name = chat.first_name or ""
                last_name = chat.last_name or ""
                full_name = f"{first_name} {last_name}".strip() or "بدون نام"
                
                txt_content += f"{idx}. {full_name}\n"
                txt_content += f"   یوزرنیم: {username}\n"
                txt_content += f"   آی‌دی: {user_id_item}\n"
                txt_content += "-" * 50 + "\n\n"
            except Exception as e:
                txt_content += f"{idx}. کاربر نامشخص\n"
                txt_content += f"   آی‌دی: {user_id_item}\n"
                txt_content += f"   خطا: {str(e)}\n"
                txt_content += "-" * 50 + "\n\n"
        
        filename = 'users_list.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(txt_content)
        
        with open(filename, 'rb') as f:
            bot.send_document(
                call.message.chat.id,
                f,
                caption=f'📋 لیست کاربران\n\nتعداد: {len(users)} نفر'
            )
        
        try:
            os.remove(filename)
        except:
            pass
        
        bot.answer_callback_query(call.id, '✅ فایل ارسال شد!')
    
    elif call.data == 'back_to_menu':
        if user_id in user_states:
            user_states[user_id] = STATE_NONE
        
        bot.edit_message_text(
            '🎬 منوی اصلی:\n\nلطفا یکی از گزینه‌ها را انتخاب کنید:',
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_menu_keyboard(user_id)
        )
    
    elif call.data == 'back_to_search':
        search_results = user_data.get(user_id, {}).get('search_results', [])
        last_search_query = user_data.get(user_id, {}).get('last_search_query', '')
        
        if search_results:
            markup = types.InlineKeyboardMarkup(row_width=1)
            
            for idx, result in enumerate(search_results):
                platform_emoji = '🎬' if result['platform'] == 'youtube' else '🎵'
                button_text = f"{platform_emoji} {result['title'][:35]}... ({result['duration']})"
                markup.add(types.InlineKeyboardButton(button_text, callback_data=f'dl_{idx}'))
            
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data='back_to_menu'))
            
            youtube_count = sum(1 for r in search_results if r['platform'] == 'youtube')
            mv_count = sum(1 for r in search_results if r['platform'] == 'youtube_mv')
            
            bot.edit_message_text(
                f'🔍 نتایج جستجو برای: <b>{last_search_query}</b>\n\n'
                f'📊 {youtube_count} نتیجه عمومی + {mv_count} موزیک ویدیو = {len(search_results)} نتیجه\n\n'
                'روی ویدیو مورد نظر کلیک کنید:',
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='HTML'
            )
    
    elif call.data.startswith('dl_'):
        video_index = int(call.data.split('_')[1])
        search_results = user_data.get(user_id, {}).get('search_results', [])
        
        if video_index < len(search_results):
            video = search_results[video_index]
            
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]['video_url'] = video['url']
            
            platform_emoji = '🎬' if video['platform'] == 'youtube' else '🎵'
            
            bot.edit_message_text(
                f'{platform_emoji} یوتیوب\n\n'
                f'{video["title"][:60]}...\n'
                f'⏱ مدت: {video["duration"]}\n\n'
                '📊 لطفا کیفیت دانلود را انتخاب کنید:',
                call.message.chat.id,
                call.message.message_id,
                reply_markup=quality_keyboard()
            )
    
    elif call.data.startswith('quality_'):
        quality = call.data.replace('quality_', '')
        url = user_data.get(user_id, {}).get('video_url')
        
        if url:
            bot.edit_message_text(
                '⏳ در حال آماده‌سازی...',
                call.message.chat.id,
                call.message.message_id
            )
            
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]['download_user_id'] = user_id
            
            thread = threading.Thread(target=download_video, args=(url, call.message, quality))
            thread.start()

# ==================== اجرای ربات ====================

def main():
    """راه‌اندازی ربات"""
    try:
        # ایجاد پوشه دانلود در ابتدا
        download_dir = get_download_path()
        print(f'📁 مسیر دانلود: {download_dir}')
        
        print('🤖 ربات با pyTelegramBotAPI شروع به کار کرد...')
        print('✅ این نسخه با Python 3.13 سازگار است!')
        print('💾 مدیریت فایل بهبود یافته!')
        print('📦 پشتیبانی از فایل‌های تا 2GB!')
        
        # راه‌اندازی UserBot (اختیاری)
        if USE_USERBOT_FOR_LARGE_FILES:
            print('\n🤖 در حال راه‌اندازی UserBot...')
            if init_userbot():
                print('✅ UserBot فعال است - همه فایل‌ها با UserBot ارسال می‌شوند (بدون محدودیت 50MB)')
            else:
                print('⚠️ UserBot غیرفعال است - از ربات عادی استفاده می‌شود')
                print('💡 برای فعال‌سازی UserBot:')
                print('   1. pip install pyrogram')
                print('   2. API_ID و API_HASH را از https://my.telegram.org/apps دریافت کنید')
                print('   3. USERBOT_API_ID و USERBOT_API_HASH را در کد تنظیم کنید')
        
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f'❌ خطا: {e}')
        print('\n💡 راه حل:')
        print('1️⃣ نصب کتابخانه‌ها:')
        print('   pip3 install pyTelegramBotAPI --user')
        print('   pip3 install yt-dlp --user')
        print('   pip3 install pyrogram --user  # برای UserBot (اختیاری)')
        print('2️⃣ اجرای ربات:')
        print('   python3 main.py')

if __name__ == '__main__':
    main()