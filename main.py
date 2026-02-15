import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import yt_dlp
import instaloader
from dotenv import load_dotenv
import json
from collections import defaultdict

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS').split(',')))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Хранилище данных
class Storage:
    def __init__(self):
        self.channels = []
        self.clicks = defaultdict(int)
        self.load()
    
    def load(self):
        try:
            with open('data.json', 'r') as f:
                data = json.load(f)
                self.channels = data.get('channels', [])
                self.clicks = defaultdict(int, data.get('clicks', {}))
        except:
            self.channels = []
            self.clicks = defaultdict(int)
    
    def save(self):
        with open('data.json', 'w') as f:
            json.dump({
                'channels': self.channels,
                'clicks': dict(self.clicks)
            }, f)
    
    def add_channel(self, channel):
        if channel not in self.channels:
            self.channels.append(channel)
            self.save()
            return True
        return False
    
    def remove_channel(self, channel):
        if channel in self.channels:
            self.channels.remove(channel)
            self.save()
            return True
        return False

storage = Storage()

# Функция проверки подписки
def check_subscription(user_id):
    if not storage.channels:
        return True, []
    
    not_subscribed = []
    for channel in storage.channels:
        try:
            member = bot.get_chat_member(chat_id=f"@{channel}", user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append(channel)
        except:
            not_subscribed.append(channel)
    return len(not_subscribed) == 0, not_subscribed

# АДМИН ПАНЕЛЬ (только по команде /admin)
def get_admin_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📋 Список каналов", callback_data="admin_list"),
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("➕ Добавить канал", callback_data="admin_add"),
        InlineKeyboardButton("➖ Удалить канал", callback_data="admin_remove"),
        InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")
    )
    return keyboard

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply(
        "👋 **Видео Загрузчик**\n\n"
        "Отправь ссылку на видео из:\n"
        "• Instagram (reels, посты)\n"
        "• YouTube (видео, shorts)\n\n"
        "Команды:\n"
        "/admin - админ панель",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message_handler(commands=['admin'])
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ Доступ запрещен")
        return
    
    text = (
        "⚙️ **Админ панель**\n\n"
        f"📢 Каналов: {len(storage.channels)}\n"
        f"👥 Переходов: {sum(storage.clicks.values())}"
    )
    
    await message.reply(text, reply_markup=get_admin_keyboard(), parse_mode=ParseMode.MARKDOWN)

# Обработчики админки
@dp.callback_query_handler(lambda c: c.data.startswith('admin_'))
async def admin_callbacks(callback_query: types.CallbackQuery):
    if callback_query.from_user.id not in ADMIN_IDS:
        await bot.answer_callback_query(callback_query.id, "Не админ")
        return
    
    action = callback_query.data
    
    if action == 'admin_list':
        if not storage.channels:
            text = "📭 Нет каналов"
        else:
            text = "📋 **Список каналов:**\n\n"
            for ch in storage.channels:
                clicks = storage.clicks.get(ch, 0)
                text += f"• @{ch} — {clicks} переходов\n"
        
        await bot.edit_message_text(
            text,
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif action == 'admin_stats':
        text = "📊 **Статистика:**\n\n"
        text += f"📢 Всего каналов: {len(storage.channels)}\n"
        text += f"👥 Всего переходов: {sum(storage.clicks.values())}\n\n"
        
        if storage.clicks:
            text += "**По каналам:**\n"
            for ch, cnt in sorted(storage.clicks.items(), key=lambda x: x[1], reverse=True):
                text += f"• @{ch}: {cnt}\n"
        
        await bot.edit_message_text(
            text,
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif action == 'admin_add':
        await bot.edit_message_text(
            "➕ **Добавление канала**\n\n"
            "Отправь команду:\n`/add @channel`\n\n"
            "Например: `/add @moy_channel`",
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif action == 'admin_remove':
        if not storage.channels:
            await bot.edit_message_text(
                "❌ Нет каналов для удаления",
                chat_id=callback_query.message.chat.id,
                message_id=callback_query.message.message_id,
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
                )
            )
            return
        
        # Клавиатура с каналами для удаления
        keyboard = InlineKeyboardMarkup(row_width=1)
        for ch in storage.channels:
            keyboard.add(InlineKeyboardButton(f"❌ @{ch}", callback_data=f"remove_{ch}"))
        keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
        
        await bot.edit_message_text(
            "🗑 **Выбери канал для удаления:**",
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif action == 'admin_back':
        text = (
            "⚙️ **Админ панель**\n\n"
            f"📢 Каналов: {len(storage.channels)}\n"
            f"👥 Переходов: {sum(storage.clicks.values())}"
        )
        await bot.edit_message_text(
            text,
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            reply_markup=get_admin_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif action == 'admin_close':
        await bot.delete_message(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id
        )

@dp.callback_query_handler(lambda c: c.data.startswith('remove_'))
async def remove_channel_callback(callback_query: types.CallbackQuery):
    if callback_query.from_user.id not in ADMIN_IDS:
        return
    
    channel = callback_query.data.replace('remove_', '')
    
    if storage.remove_channel(channel):
        await bot.answer_callback_query(callback_query.id, f"✅ Канал @{channel} удален")
    else:
        await bot.answer_callback_query(callback_query.id, f"❌ Ошибка")
    
    # Возврат в меню удаления
    await admin_callbacks(types.CallbackQuery(
        id=callback_query.id,
        from_user=callback_query.from_user,
        data='admin_remove',
        message=callback_query.message
    ))

# Команды для админа (просто на всякий случай)
@dp.message_handler(commands=['add'])
async def add_channel_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        channel = message.text.split()[1].replace('@', '')
        if storage.add_channel(channel):
            await message.reply(f"✅ Канал @{channel} добавлен")
        else:
            await message.reply(f"⚠️ Канал @{channel} уже есть")
    except:
        await message.reply("Используй: /add @channel")

@dp.message_handler(commands=['remove'])
async def remove_channel_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        channel = message.text.split()[1].replace('@', '')
        if storage.remove_channel(channel):
            await message.reply(f"✅ Канал @{channel} удален")
        else:
            await message.reply(f"❌ Канал @{channel} не найден")
    except:
        await message.reply("Используй: /remove @channel")

# ОСНОВНАЯ ЛОГИКА - СКАЧИВАНИЕ ВИДЕО
@dp.message_handler()
async def handle_video(message: types.Message):
    user_id = message.from_user.id
    url = message.text.strip()
    
    # Проверка подписки
    ok, not_sub = check_subscription(user_id)
    if not ok and storage.channels:
        # Считаем показы кнопок (для статистики)
        for ch in not_sub:
            storage.clicks[ch] += 1
        storage.save()
        
        # Отправляем ссылки на каналы
        text = "🔒 **Для скачивания подпишись:**\n\n"
        for ch in not_sub:
            text += f"• https://t.me/{ch}\n"
        await message.reply(text, parse_mode=ParseMode.MARKDOWN)
        return
    
    # Скачивание видео
    msg = await message.reply("🔄 **Загружаю...**", parse_mode=ParseMode.MARKDOWN)
    
    try:
        if 'instagram.com' in url:
            await msg.edit_text("📥 **Instagram...**", parse_mode=ParseMode.MARKDOWN)
            
            if not os.path.exists('downloads'):
                os.makedirs('downloads')
            
            # Парсим ссылку
            if '/reel/' in url:
                shortcode = url.split('/reel/')[1].split('/')[0]
            elif '/p/' in url:
                shortcode = url.split('/p/')[1].split('/')[0]
            else:
                await msg.edit_text("❌ Неверная ссылка Instagram")
                return
            
            # Скачиваем
            L = instaloader.Instaloader(dirname_pattern='downloads', filename_pattern=shortcode)
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            
            if post.is_video:
                L.download_post(post, target=shortcode)
                
                # Ищем файл
                for f in os.listdir('downloads'):
                    if f.endswith('.mp4') and shortcode in f:
                        with open(os.path.join('downloads', f), 'rb') as video:
                            await message.reply_video(video)
                        os.remove(os.path.join('downloads', f))
                        await msg.delete()
                        return
                await msg.edit_text("❌ Видео не найдено")
            else:
                await msg.edit_text("❌ Это не видео")
        
        elif 'youtube.com' in url or 'youtu.be' in url:
            await msg.edit_text("📥 **YouTube...**", parse_mode=ParseMode.MARKDOWN)
            
            if not os.path.exists('downloads'):
                os.makedirs('downloads')
            
            # Настройки скачивания
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': 'downloads/%(title)s.%(ext)s',
                'quiet': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Проверяем расширение
                if not os.path.exists(filename):
                    filename = filename.replace('.mp4', '.webm')
                if not os.path.exists(filename):
                    filename = filename.replace('.webm', '.mkv')
                
                if os.path.exists(filename):
                    with open(filename, 'rb') as video:
                        await message.reply_video(video)
                    os.remove(filename)
                    await msg.delete()
                else:
                    await msg.edit_text("❌ Видео не найдено")
        else:
            await msg.edit_text("❌ Только Instagram или YouTube")
            
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

if __name__ == '__main__':
    print("="*50)
    print("🚀 БОТ ЗАПУЩЕН")
    print("="*50)
    print(f"👑 Админ ID: {ADMIN_IDS}")
    print(f"📢 Каналов: {len(storage.channels)}")
    print("="*50)
    executor.start_polling(dp, skip_updates=True)