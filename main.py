import logging
import re
import time
import emoji
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from config import *
from database import db

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO if not DEBUG else logging.DEBUG
)

def is_emoji_only(text: str) -> bool:
    if not text: return False
    cleaned = re.sub(r'[\s\.\,\!\?\(\)\[\]\{\}\-\_\:\;]', '', text)
    if not cleaned: return False
    
    if cleaned in ['🎰', '🎲', '🎯', '🏀', '⚽', '🎳']:
        return True

    remaining = emoji.replace_emoji(cleaned, replace='')
    
    return len(remaining) == 0

def can_mute_user(muter_id: int, target_id: int) -> bool:
    if target_id in SENIOR_ADMIN_IDS:
        return False
    return db.get_user_level(muter_id) > db.get_user_level(target_id)

def can_ban_user(banner_id: int, target_id: int) -> bool:
    if target_id in SENIOR_ADMIN_IDS:
        return False
    banner_level = db.get_user_level(banner_id)
    target_level = db.get_user_level(target_id)
    return banner_level >= 4 and banner_level > target_level

def can_change_level(changer_id: int, target_id: int, new_level: int) -> tuple:
    if target_id in SENIOR_ADMIN_IDS and changer_id != target_id:
        return False, "Нельзя менять уровень старших админов"
    
    changer_level = db.get_user_level(changer_id)
    target_level = db.get_user_level(target_id)
    
    if changer_level <= target_level and changer_id != target_id:
        return False, "У вас недостаточно прав"
    
    if new_level >= changer_level and changer_id != target_id:
        return False, "Нельзя установить уровень выше или равный своему"
    
    if new_level > 6:
        return False, "Максимальный уровень - 6"
    
    return True, ""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    owner_id = await db.update_chat_owner_level(chat_id, context.bot)
    
    db.set_user_level(
        user_id,
        db.get_user_level(user_id),
        user.username,
        user.first_name
    )
    db.add_user_to_chat(user_id, chat_id)
    
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for admin in admins:
            admin_user = admin.user
            level = 6 if admin.status == 'creator' else db.get_user_level(admin_user.id)
            db.set_user_level(admin_user.id, level, admin_user.username, admin_user.first_name)
            db.add_user_to_chat(admin_user.id, chat_id)
    except:
        pass
    
    level = db.get_user_level(user_id)
    await update.message.reply_text(
        f"🤖 Бот-модератор с уровнями!\n"
        f"Ваш уровень: {LEVELS[level]}\n"
        f"Используйте /help для списка команд"
    )

async def mylevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    await db.update_chat_owner_level(chat_id, context.bot)
    
    db.set_user_level(
        user_id,
        db.get_user_level(user_id),
        user.username,
        user.first_name
    )
    
    level = db.get_user_level(user_id)
    stats = db.get_user_stats(user_id)
    
    if level == 6:
        message = f"👑 Вы - Старший админ!\nID: {user_id}\n"
    else:
        message = f"📊 Ваш уровень: {LEVELS[level]}\nID: {user_id}\n"
    
    message += f"📨 Сообщений: {stats['total_messages']}\n"
    message += f"🎨 Стикеров: {stats['total_stickers']}\n"
    message += f"⚠️ Муты: {stats['total_mutes']}\n"
    message += f"🔨 Баны: {stats['total_bans']}"
    
    await update.message.reply_text(message)

async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    try:
        await db.update_chat_owner_level(chat_id, context.bot)
        
        level_users = {level: [] for level in range(6, 0, -1)}
        chat_users = db.get_chat_users(chat_id)
        
        for user_data in chat_users:
            level = user_data['level']
            username = f"@{user_data['username']}" if user_data['username'] else user_data['first_name'] or f"ID: {user_data['user_id']}"
            level_users[level].append(username)
        
        message_lines = [f"📋 Участники чата (ID: {chat_id}):\n"]
        
        for level in range(6, 0, -1):
            users_list = level_users[level]
            if users_list:
                users = ", ".join(users_list[:15])
                if len(users_list) > 15:
                    users += f" и еще {len(users_list) - 15}"
                
                message_lines.append(f"\n{LEVELS[level]} ({len(users_list)}):\n{users}")
        
        if len(message_lines) == 1:
            await update.message.reply_text("📭 В этом чате пока нет зарегистрированных участников")
        else:
            await update.message.reply_text("".join(message_lines))
            
    except Exception as e:
        logging.error(f"Error in list_cmd: {e}")
        await update.message.reply_text("❌ Ошибка получения списка")

async def setlevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if db.get_user_level(user_id) < 5:
        await update.message.reply_text("❌ Только админы могут использовать эту команду!")
        return
    
    if not context.args or len(context.args) != 2:
        await update.message.reply_text("❌ Формат: /setlevel @username уровень")
        return
    
    username = context.args[0].lstrip('@')
    try:
        new_level = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Уровень должен быть числом от 1 до 6")
        return
    
    if new_level < 1 or new_level > 6:
        await update.message.reply_text("❌ Уровень должен быть от 1 до 6")
        return
    
    target_user_data = None
    if username.isdigit():
        target_id = int(username)
    else:
        target_user_data = db.get_user_by_username(username)
        if target_user_data:
            target_id = target_user_data['user_id']
        else:
            await update.message.reply_text("❌ Пользователь не найден в базе данных. Он должен хотя бы раз написать боту.")
            return
    
    can_change, reason = can_change_level(user_id, target_id, new_level)
    if not can_change:
        await update.message.reply_text(f"❌ {reason}")
        return
    
    old_level = db.get_user_level(target_id)
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id, target_id)
        target_username = chat_member.user.username
        target_first_name = chat_member.user.first_name
    except:
        if target_user_data:
            target_username = target_user_data['username']
            target_first_name = target_user_data['first_name']
        else:
            target_username = username
            target_first_name = f"ID: {target_id}"

    db.set_user_level(
        target_id,
        new_level,
        target_username,
        target_first_name
    )
    
    action = "повышен" if new_level > old_level else "понижен"
    await update.message.reply_text(
        f"✅ Пользователь @{target_username or target_id} {action}!\n"
        f"{LEVELS[old_level]} → {LEVELS[new_level]}"
    )

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if db.get_user_level(user_id) < 3:
        await update.message.reply_text("❌ Только модераторы и выше могут размучивать!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажите @username пользователя")
        return
    
    username = context.args[0].lstrip('@')
    
    target_id = None
    target_username = None
    
    if username.isdigit():
        target_id = int(username)
        target_username = f"ID: {target_id}"
    else:
        user_data = db.get_user_by_username(username)
        if user_data:
            target_id = user_data['user_id']
            target_username = f"@{user_data['username']}"
        else:
            await update.message.reply_text("❌ Пользователь не найден в базе данных.")
            return
    
    if not target_id:
        await update.message.reply_text("❌ Пользователь не найден")
        return
    
    if user_id != target_id and db.get_user_level(user_id) <= db.get_user_level(target_id):
        await update.message.reply_text("❌ Нельзя размучивать пользователей выше или равного вам уровня!")
        return
    
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=True)
        )
        
        await update.message.reply_text(f"✅ Пользователь {target_username} размьючен!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при размуте: {str(e)}")

async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if db.get_user_level(user_id) < 3:
        await update.message.reply_text("❌ Только модераторы и выше могут мутить!")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("❌ Формат: /mute @username [время в секундах]\nПример: /mute @username 3600")
        return
    
    username = context.args[0].lstrip('@')
    
    mute_time = DEFAULT_MUTE_TIME
    if len(context.args) > 1:
        try:
            mute_time = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Время должно быть числом в секундах")
            return
    
    target_id = None
    target_username = None
    
    if username.isdigit():
        target_id = int(username)
        target_username = f"ID: {target_id}"
    else:
        user_data = db.get_user_by_username(username)
        if user_data:
            target_id = user_data['user_id']
            target_username = f"@{user_data['username']}"
        else:
            await update.message.reply_text("❌ Пользователь не найден в базе данных.")
            return
    
    if not target_id:
        await update.message.reply_text("❌ Пользователь не найден")
        return
    
    if not can_mute_user(user_id, target_id):
        await update.message.reply_text("❌ Нельзя замутить этого пользователя!")
        return
    
    try:
        mute_until = time.time() + mute_time
        
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until
        )
        
        db.add_mute_record(target_id, f"Мут от @{update.effective_user.username or update.effective_user.first_name}", user_id, mute_until)
        
        hours = mute_time // 3600
        minutes = (mute_time % 3600) // 60
        
        time_str = ""
        if hours > 0:
            time_str += f"{hours} час "
        if minutes > 0:
            time_str += f"{minutes} мин"
        
        if time_str:
            await update.message.reply_text(f"✅ Пользователь {target_username} замьючен на {time_str.strip()}!")
        else:
            await update.message.reply_text(f"✅ Пользователь {target_username} замьючен!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при муте: {str(e)}")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if db.get_user_level(user_id) < 4:
        await update.message.reply_text("❌ Только модераторы 4+ уровня могут банить!")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("❌ Формат: /ban @username [причина]\nПример: /ban @username спам")
        return
    
    username = context.args[0].lstrip('@')
    
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Без указания причины"
    
    target_id = None
    target_username = None
    
    if username.isdigit():
        target_id = int(username)
        target_username = f"ID: {target_id}"
    else:
        user_data = db.get_user_by_username(username)
        if user_data:
            target_id = user_data['user_id']
            target_username = f"@{user_data['username']}"
        else:
            await update.message.reply_text("❌ Пользователь не найден в базе данных.")
            return
    
    if not target_id:
        await update.message.reply_text("❌ Пользователь не найден")
        return
    
    if not can_ban_user(user_id, target_id):
        await update.message.reply_text("❌ Нельзя забанить этого пользователя!")
        return
    
    try:
        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=target_id
        )
        
        db.add_ban_record(target_id, reason, user_id)
        
        await update.message.reply_text(f"✅ Пользователь {target_username} забанен!\nПричина: {reason}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при бане: {str(e)}")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if db.get_user_level(user_id) < 4:
        await update.message.reply_text("❌ Только модераторы 4+ уровня могут разбанивать!")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("❌ Формат: /unban @username или /unban [user_id]\nПример: /unban @username")
        return
    
    identifier = context.args[0]
    
    target_id = None
    
    if identifier.startswith('@'):
        username = identifier.lstrip('@')
        try:
            async for member in context.bot.get_chat_members(chat_id):
                if member.user.username and member.user.username.lower() == username.lower():
                    target_id = member.user.id
                    break
        except:
            await update.message.reply_text("❌ Пользователь не найден в чате")
            return
    else:
        try:
            target_id = int(identifier)
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Используйте @username или user_id")
            return
    
    if not target_id:
        await update.message.reply_text("❌ Пользователь не найден")
        return
    
    try:
        await context.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=target_id
        )
        
        db.remove_ban_record(target_id)
        
        await update.message.reply_text(f"✅ Пользователь ID: {target_id} разбанен!")
    except Exception as e:
        error_msg = str(e)
        if "user not found" in error_msg.lower() or "chat not found" in error_msg.lower():
            await update.message.reply_text("✅ Пользователь уже не в бане или не найден в чате")
        else:
            await update.message.reply_text(f"❌ Ошибка при разбане: {error_msg}")

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение, которое хотите пожаловаться!")
        return
    
    reporter_id = update.effective_user.id
    reported_user_id = update.message.reply_to_message.from_user.id
    message_id = update.message.reply_to_message.message_id
    chat_id = update.effective_chat.id
    
    if reporter_id == reported_user_id:
        await update.message.reply_text("❌ Нельзя жаловаться на самого себя!")
        return
    
    reason = " ".join(context.args) if context.args else "Без указания причины"
    
    report_id = db.add_report(reporter_id, reported_user_id, message_id, chat_id, reason)
    
    reporter_name = update.effective_user.username or update.effective_user.first_name
    reported_name = update.message.reply_to_message.from_user.username or update.message.reply_to_message.from_user.first_name
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👁️ Просмотрено", callback_data=f"report_view:{report_id}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"report_delete:{report_id}")
        ],
        [
            InlineKeyboardButton("🔇 Мут на час", callback_data=f"report_mute:{report_id}"),
            InlineKeyboardButton("🔨 Бан", callback_data=f"report_ban:{report_id}")
        ]
    ])
    
    report_text = (
        f"🚨 **НОВЫЙ РЕПОРТ**\n\n"
        f"👤 **От:** @{reporter_name} (ID: {reporter_id})\n"
        f"👥 **На:** @{reported_name} (ID: {reported_user_id})\n"
        f"📝 **Причина:** {reason}\n"
        f"🔗 **Сообщение:** [Перейти](https://t.me/c/{str(chat_id)[4:]}/{message_id})\n"
        f"🆔 **ID репорта:** {report_id}"
    )
    
    await update.message.reply_text("✅ Жалоба отправлена модераторам!")
    
    try:
        chat_admins = await context.bot.get_chat_administrators(chat_id)
        moderators_notified = 0
        
        for admin in chat_admins:
            admin_user = admin.user
            admin_id = admin_user.id
            admin_level = db.get_user_level(admin_id)
            
            if admin_level >= 3:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=report_text,
                        parse_mode='Markdown',
                        reply_markup=keyboard
                    )
                    moderators_notified += 1
                except:
                    continue
        
        if moderators_notified > 0:
            await update.message.reply_text(f"📢 Уведомление отправлено {moderators_notified} модераторам")
        else:
            await update.message.reply_text("⚠️ Не удалось уведомить модераторов")
            
    except Exception as e:
        await update.message.reply_text("❌ Ошибка отправки уведомления")

async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("report_"):
        return
    
    action, report_id_str = data.split(":")
    report_id = int(report_id_str)
    
    try:
        pending_reports = db.get_pending_reports()
        report = None
        for r in pending_reports:
            if r['id'] == report_id:
                report = r
                break
        
        if not report:
            await query.edit_message_text("❌ Репорт не найден или уже обработан")
            return
        
        reported_user_id = report['reported_user_id']
        message_id = report['message_id']
        chat_id = report['chat_id']
        reporter_name = report['reporter_username'] or f"ID: {report['reporter_id']}"
        reported_name = report['reported_username'] or f"ID: {reported_user_id}"
        reason = report['reason'] or "Без указания причины"
        
        action_text = ""
        
        if action == "report_view":
            action_text = "👁️ Помечено как просмотрено"
            db.update_report_status(report_id, "viewed")
        
        elif action == "report_delete":
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                action_text = f"🗑️ Сообщение от @{reported_name} удалено"
            except:
                action_text = f"❌ Не удалось удалить сообщение от @{reported_name}"
            db.update_report_status(report_id, "deleted")
        
        elif action == "report_mute":
            try:
                mute_until = time.time() + DEFAULT_MUTE_TIME
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=reported_user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=mute_until
                )
                
                db.add_mute_record(reported_user_id, f"Мут по репорту от @{reporter_name}: {reason}", query.from_user.id, mute_until)
                
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    action_text = f"🔇 @{reported_name} замьючен на час, сообщение удалено"
                except:
                    action_text = f"🔇 @{reported_name} замьючен на час"
            except:
                action_text = f"❌ Не удалось замутить @{reported_name}"
            db.update_report_status(report_id, "muted")
        
        elif action == "report_ban":
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=reported_user_id)
                db.add_ban_record(reported_user_id, f"Бан по репорту от @{reporter_name}: {reason}", query.from_user.id)
                
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    action_text = f"🔨 @{reported_name} забанен, сообщение удалено"
                except:
                    action_text = f"🔨 @{reported_name} забанен"
            except:
                action_text = f"❌ Не удалось забанить @{reported_name}"
            db.update_report_status(report_id, "banned")
        
        result_text = (
            f"✅ **Действие выполнено**\n\n"
            f"👤 **На:** @{reported_name}\n"
            f"👮 **Модератор:** @{query.from_user.username or query.from_user.first_name}\n"
            f"📝 **Действие:** {action_text}\n"
            f"📄 **Причина репорта:** {reason}"
        )
        
        await query.edit_message_text(result_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка обработки репорта: {str(e)}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_users = db.get_all_users()
    total_users = len(all_users)
    
    level_counts = {level: 0 for level in range(1, 7)}
    for user_data in all_users:
        level = user_data['level']
        if level in level_counts:
            level_counts[level] += 1
    
    pending_reports = len(db.get_pending_reports())
    
    message = "📊 Статистика бота:\n\n"
    message += f"👥 Всего пользователей: {total_users}\n"
    message += f"🚨 Ожидающих репортов: {pending_reports}\n"
    message += "📈 Распределение по уровням:\n"
    
    for level in range(6, 0, -1):
        message += f"{LEVELS[level]}: {level_counts[level]} пользователей\n"
    
    await update.message.reply_text(message)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 **Команды бота-модератора:**

📋 **Для всех:**
/start - Информация о боте
/mylevel - Узнать свой уровень
/list - Список пользователей по уровням
/stats - Статистика бота
/help - Эта справка
/report [причина] - Ответьте на сообщение для жалобы

🛡️ **Для модераторов (уровень 3+):**
/unmute @username - Размутить пользователя
/mute @username [секунды] - Замутить пользователя (по умолчанию 1 час)

🛡️ **Для модераторов (уровень 4+):**
/ban @username [причина] - Забанить пользователя
/unban @username или /unban [user_id] - Разбанить пользователя

👑 **Для админов (уровень 5+):**
/setlevel @username уровень - Установить уровень
повысить @username уровень - Повысить уровень (в сообщении)
понизить @username уровень - Понизить уровень (в сообщении)

📊 **Система уровней:**
1. 👤 Обычный пользователь
2. 💰 Донатер
3. 🛡️ Младший модератор
4. 🛡️ Модератор
5. 👑 Младший админ
6. 👑 Старший админ

🔒 **Антиспам:**
• 2 сообщения только с эмодзи подряд → мут
• 3 стикера за 10 секунд → мут
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        if user_id == context.bot.id:
            return
        
        db.set_user_level(
            user_id,
            db.get_user_level(user_id),
            user.username,
            user.first_name
        )
        
        await db.update_chat_owner_level(chat_id, context.bot)
        
        if update.message.sticker:
            await handle_sticker(update, context, user_id, "стикер")
            return
        elif update.message.animation:
            await handle_sticker(update, context, user_id, "гифка")
            return
        elif update.message.dice:
            # Handle dice/emoji animations like slots
            await handle_text(update, context, user_id, chat_id, update.message.dice.emoji)
            return
            
        message_text = update.message.text or update.message.caption
        if message_text:
            db.add_user_to_chat(user_id, chat_id) # Ensure user is linked to chat on message
            await handle_text(update, context, user_id, chat_id, message_text)
            return
            
    except Exception as e:
        logging.error(f"Error in handle_message: {e}")

async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, media_type: str = "стикер"):
    if user_id in SENIOR_ADMIN_IDS:
        return
    
    user_level = db.get_user_level(user_id)
    if user_level < 3:
        db.add_sticker_record(user_id)
        
        sticker_count = db.get_recent_stickers(user_id, STICKER_TIME_WINDOW)
        
        if sticker_count >= STICKER_SPAM_THRESHOLD:
            if can_mute_user(context.bot.id, user_id):
                reason = f"спам {media_type}ми"
                await mute_user(update, context, user_id, reason)
                try:
                    await update.message.delete()
                except:
                    pass
                db.clear_user_history(user_id)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                     user_id: int, chat_id: int, message_text: str):
    
    await db.update_chat_owner_level(chat_id, context.bot)
    
    if message_text.startswith('/'):
        return

    if message_text.lower().startswith(('повысить', 'понизить')):
        parts = message_text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Формат: повысить @username уровень")
            return
        
        username = parts[1].lstrip('@')
        try:
            new_level = int(parts[2])
        except ValueError:
            await update.message.reply_text("❌ Уровень должен быть числом от 1 до 6")
            return
        
        if db.get_user_level(user_id) < 5:
            await update.message.reply_text("❌ Только админы могут менять уровни!")
            return
        
        target_user = None
        try:
            async for member in context.bot.get_chat_members(chat_id):
                if member.user.username and member.user.username.lower() == username.lower():
                    target_user = member.user
                    break
        except:
            await update.message.reply_text("❌ Ошибка при поиске пользователя")
            return
        
        if not target_user:
            await update.message.reply_text("❌ Пользователь не найден в чате")
            return
        
        target_id = target_user.id
        
        can_change, reason = can_change_level(user_id, target_id, new_level)
        if not can_change:
            await update.message.reply_text(f"❌ {reason}")
            return
        
        old_level = db.get_user_level(target_id)
        db.set_user_level(
            target_id,
            new_level,
            target_user.username,
            target_user.first_name
        )
        
        action = "повышен" if new_level > old_level else "понижен"
        await update.message.reply_text(
            f"✅ Пользователь @{target_user.username} {action}!\n"
            f"{LEVELS[old_level]} → {LEVELS[new_level]}"
        )
        return
    
    user_level = db.get_user_level(user_id)
    if user_level < 3 and user_id not in SENIOR_ADMIN_IDS:
        is_spam = is_emoji_only(message_text)
        
        if not is_spam and update.message.entities:
            custom_emoji_entities = [e for e in update.message.entities if e.type in ('custom_emoji', 'premium_animation')]
            if custom_emoji_entities:
                # If message is just whitespace + custom emojis, count as spam
                text_without_entities = message_text
                # This is a bit complex to strip perfectly, but if entities cover significant part:
                is_spam = True # Assume it's a spam message if it has custom emojis for now
        
        db.add_message_record(user_id, is_spam)
        
        if is_spam:
            recent_messages = db.get_recent_spam_messages(user_id, SPAM_THRESHOLD)
            
            if len(recent_messages) >= SPAM_THRESHOLD:
                if can_mute_user(context.bot.id, user_id):
                    await mute_user(update, context, user_id, "спам эмодзи")
                    await update.message.delete()
                    db.clear_user_history(user_id)

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                   user_id: int, reason: str):
    try:
        chat_id = update.effective_chat.id
        mute_until = time.time() + MUTE_DURATION
        
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until
        )
        
        db.add_mute_record(user_id, reason, context.bot.id, mute_until)
        
        user_name = update.effective_user.first_name
        
        if "стикер" in reason:
            message_text = f"🚫 Пользователь {user_name} замьючен на {MUTE_DURATION//60} минут за спам стикерами!"
        elif "гифка" in reason:
            message_text = f"🚫 Пользователь {user_name} замьючен на {MUTE_DURATION//60} минут за спам гифками!"
        else:
            message_text = f"🚫 Пользователь {user_name} замьючен на {MUTE_DURATION//60} минут за спам эмодзи!"
        
        await context.bot.send_message(chat_id=chat_id, text=message_text)
        
        db.clear_user_history(user_id)
        
    except Exception as e:
        pass

def main():
    print("="*50)
    print("🤖 Telegram Moderator Bot")
    print("="*50)
    
    try:
        app = Application.builder().token(BOT_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("mylevel", mylevel))
        app.add_handler(CommandHandler("list", list_cmd))
        app.add_handler(CommandHandler("setlevel", setlevel))
        app.add_handler(CommandHandler("unmute", unmute))
        app.add_handler(CommandHandler("mute", mute_cmd))
        app.add_handler(CommandHandler("ban", ban_cmd))
        app.add_handler(CommandHandler("unban", unban_cmd))
        app.add_handler(CommandHandler("report", report_cmd))
        app.add_handler(CommandHandler("stats", stats_cmd))
        app.add_handler(CommandHandler("help", help_cmd))
        
        app.add_handler(CallbackQueryHandler(report_callback))
        
        app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
        
        print("✅ Бот запущен. Ctrl+C для остановки")
        print("="*50)
        
        app.run_polling()
        
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
        db.close()
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        db.close()
        raise

if __name__ == "__main__":
    main()
