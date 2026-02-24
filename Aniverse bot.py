import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
import datetime
import sqlite3
import re
import math

# Конфигурация
VK_TOKEN = "vk1.a.niwLTYj0OoJ0UdULM3MTnvexSLVsLuYr4_jH2Zr10SCDmyg79AjugdUmmkn6Ju-4s2Std7s-gCkYkafqtiGf79vChqjYa2Mk-IloP1HDd7A4NfypIQ1L_SngypDjKearC5O0_haOMXhYnsmkPRYL_kCuiZW92lhPdVmZ1ghcpj_c1AUvSeE0p8Je8K6kLlTeqwGSb7DltcrY0vm0AaOvdg"
GROUP_ID = 218666977
TARGET_POST_ID = 439  # ID поста с игрой
SECRET_CODE = "3461687"

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('game_data.db')
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  is_subscriber INTEGER DEFAULT 0,
                  attempts_today INTEGER DEFAULT 0,
                  last_attempt_date TEXT,
                  guessed_numbers TEXT DEFAULT '',
                  last_hint_threshold INTEGER DEFAULT 0)''')
    
    # Таблица попыток (история)
    c.execute('''CREATE TABLE IF NOT EXISTS attempts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  attempt_number TEXT,
                  attempt_date TEXT,
                  correct INTEGER DEFAULT 0)''')
    
    conn.commit()
    conn.close()

# Класс бота
class VKBot:
    def __init__(self, token):
        self.vk_session = vk_api.VkApi(token=token)
        self.vk = self.vk_session.get_api()
        self.longpoll = VkLongPoll(self.vk_session)
        
    def send_message(self, user_id, message):
        """Отправка сообщения пользователю"""
        try:
            self.vk.messages.send(
                user_id=user_id,
                random_id=get_random_id(),
                message=message
            )
        except Exception as e:
            print(f"Ошибка отправки сообщения: {e}")
    
    def send_comment_reply(self, post_id, comment_id, message):
        """Ответ на комментарий"""
        try:
            self.vk.wall.createComment(
                post_id=post_id,
                comment_id=comment_id,
                message=message
            )
        except Exception as e:
            print(f"Ошибка ответа на комментарий: {e}")
    
    def get_user_info(self, user_id):
        """Получение информации о пользователе"""
        try:
            user = self.vk.users.get(user_ids=user_id)[0]
            return f"{user['first_name']} {user['last_name']}"
        except:
            return f"User{user_id}"
    
    def check_subscription(self, user_id):
        """Проверка подписки на группу"""
        try:
            result = self.vk.groups.isMember(group_id=GROUP_ID, user_id=user_id)
            return result == 1
        except:
            return False
    
    def check_repost(self, user_id, post_id):
        """Проверка репоста записи"""
        try:
            # Проверяем, есть ли запись на стене пользователя
            wall = self.vk.wall.get(owner_id=user_id, count=10)
            for item in wall['items']:
                if 'copy_history' in item:
                    for copy in item['copy_history']:
                        if copy.get('id') == post_id and abs(copy.get('owner_id')) == GROUP_ID:
                            return True
            return False
        except:
            return False
    
    def check_like(self, user_id, post_id):
        """Проверка лайка на посте"""
        try:
            result = self.vk.likes.isLiked(
                user_id=user_id,
                type='post',
                owner_id=-GROUP_ID,
                item_id=post_id
            )
            return result['liked'] == 1
        except:
            return False
    
    def get_daily_attempts(self, user_id):
        """Получение количества попыток на сегодня"""
        conn = sqlite3.connect('game_data.db')
        c = conn.cursor()
        
        today = datetime.date.today().isoformat()
        
        # Получаем пользователя
        c.execute("SELECT attempts_today, last_attempt_date FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        
        if result:
            attempts_today, last_date = result
            # Если последняя попытка была не сегодня, обнуляем счетчик
            if last_date != today:
                attempts_today = 0
                c.execute("UPDATE users SET attempts_today = 0, last_attempt_date = ? WHERE user_id = ?", 
                         (today, user_id))
        else:
            # Новый пользователь
            username = self.get_user_info(user_id)
            c.execute("INSERT INTO users (user_id, username, attempts_today, last_attempt_date) VALUES (?, ?, 0, ?)",
                     (user_id, username, today))
            attempts_today = 0
        
        conn.commit()
        conn.close()
        
        return attempts_today
    
    def calculate_total_attempts(self, user_id, post_id):
        """Расчет общего количества доступных попыток"""
        base_attempts = 3  # базовые попытки
        
        # Проверка подписки
        if self.check_subscription(user_id):
            base_attempts += 7
        
        # Проверка репоста
        if self.check_repost(user_id, post_id):
            base_attempts += 15
        
        # Проверка лайка
        if self.check_like(user_id, post_id):
            base_attempts += 5
        
        return base_attempts
    
    def save_attempt(self, user_id, attempt, correct=False):
        """Сохранение попытки в базу"""
        conn = sqlite3.connect('game_data.db')
        c = conn.cursor()
        
        today = datetime.date.today().isoformat()
        now = datetime.datetime.now().isoformat()
        
        # Обновляем счетчик попыток
        c.execute("UPDATE users SET attempts_today = attempts_today + 1 WHERE user_id = ?", (user_id,))
        
        # Сохраняем историю попыток
        c.execute("INSERT INTO attempts (user_id, attempt_number, attempt_date, correct) VALUES (?, ?, ?, ?)",
                 (user_id, attempt, now, 1 if correct else 0))
        
        # Обновляем список угаданных чисел
        c.execute("SELECT guessed_numbers FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        guessed = result[0] if result[0] else ""
        
        if attempt not in guessed:
            if guessed:
                guessed += f",{attempt}"
            else:
                guessed = attempt
            
            c.execute("UPDATE users SET guessed_numbers = ? WHERE user_id = ?", (guessed, user_id))
        
        conn.commit()
        
        # Проверяем, нужно ли дать подсказку (после каждых 50 попыток)
        self.check_and_give_hint(user_id, attempt, correct)
        
        conn.close()
    
    def check_and_give_hint(self, user_id, last_attempt, was_correct):
        """Проверка и выдача подсказки после каждых 50 попыток"""
        if was_correct:
            return  # Не даем подсказку если угадал
        
        conn = sqlite3.connect('game_data.db')
        c = conn.cursor()
        
        # Получаем общее количество попыток пользователя
        c.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (user_id,))
        total_attempts = c.fetchone()[0]
        
        # Получаем последний порог, на котором давали подсказку
        c.execute("SELECT last_hint_threshold FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        last_hint_threshold = result[0] if result and result[0] else 0
        
        # Проверяем, достигнут ли новый порог в 50 попыток
        current_threshold = math.floor(total_attempts / 50) * 50
        
        if current_threshold >= 50 and current_threshold > last_hint_threshold:
            # Обновляем порог подсказок
            c.execute("UPDATE users SET last_hint_threshold = ? WHERE user_id = ?", (current_threshold, user_id))
            conn.commit()
            
            # Определяем подсказку
            if int(last_attempt) > int(SECRET_CODE):
                hint = f"📊 Ты сделал {total_attempts} попыток! Подсказка: твой последний код {last_attempt} БОЛЬШЕ загаданного"
            elif int(last_attempt) < int(SECRET_CODE):
                hint = f"📊 Ты сделал {total_attempts} попыток! Подсказка: твой последний код {last_attempt} МЕНЬШЕ загаданного"
            else:
                hint = f"📊 Ты сделал {total_attempts} попыток! Продолжай в том же духе!"
            
            # Отправляем подсказку в личные сообщения
            try:
                self.send_message(user_id, hint)
                print(f"Подсказка отправлена пользователю {user_id} после {total_attempts} попыток")
            except Exception as e:
                print(f"Не удалось отправить подсказку: {e}")
        
        conn.close()
    
    def get_guessed_numbers(self, user_id):
        """Получение списка попыток пользователя"""
        conn = sqlite3.connect('game_data.db')
        c = conn.cursor()
        
        c.execute("SELECT guessed_numbers FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        
        conn.close()
        
        if result and result[0]:
            return result[0].split(',')
        return []
    
    def handle_comment(self, event):
        """Обработка комментария к посту"""
        user_id = event.user_id
        post_id = event.post_id
        comment_id = event.comment_id
        text = event.text.strip()
        
        # Играем только в конкретном посте
        if post_id != TARGET_POST_ID:
            return
        
        # Проверяем, является ли комментарий 7-значным числом
        if re.match(r'^\d{7}$', text):
            attempts_today = self.get_daily_attempts(user_id)
            total_available = self.calculate_total_attempts(user_id, post_id)
            
            if attempts_today >= total_available:
                self.send_comment_reply(post_id, comment_id, 
                    f"❌ У тебя закончились попытки на сегодня! Использовано: {attempts_today}/{total_available}")
                return
            
            # Проверяем код
            if text == SECRET_CODE:
                self.save_attempt(user_id, text, correct=True)
                self.send_comment_reply(post_id, comment_id, 
                    f"🎉 ПОЗДРАВЛЯЮ! Ты отгадал код! Это действительно {SECRET_CODE}!")
                # Отправляем поздравление в личку
                self.send_message(user_id, f"🎉 Поздравляю с победой! Код {SECRET_CODE} разгадан! Обратись к администратору за призом.")
            else:
                self.save_attempt(user_id, text, correct=False)
                attempts_left = total_available - attempts_today - 1
                self.send_comment_reply(post_id, comment_id, 
                    f"❌ Неверный код! Осталось попыток на сегодня: {attempts_left}")
    
    def handle_private_message(self, event):
        """Обработка личных сообщений"""
        user_id = event.user_id
        text = event.text.lower().strip()
        
        if text == "попытки":
            guessed = self.get_guessed_numbers(user_id)
            if guessed:
                numbers_str = ", ".join(guessed)
                # Получаем общее количество попыток
                conn = sqlite3.connect('game_data.db')
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (user_id,))
                total = c.fetchone()[0]
                conn.close()
                
                self.send_message(user_id, f"📝 Всего попыток: {total}\nТвои попытки: {numbers_str}")
            else:
                self.send_message(user_id, "📝 Ты еще не пробовал отгадывать код")
        
        elif text == "шанс":
            # Проверяем общее количество попыток
            conn = sqlite3.connect('game_data.db')
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (user_id,))
            total_attempts = c.fetchone()[0]
            conn.close()
            
            next_hint = (math.floor(total_attempts / 50) + 1) * 50
            
            self.send_message(user_id, 
                f"🔢 Команда 'шанс' активна после каждых 50 попыток!\n"
                f"Сейчас у тебя {total_attempts} попыток.\n"
                f"Следующая подсказка будет через {next_hint - total_attempts} попыток.\n"
                f"Подсказки приходят автоматически в личные сообщения!")
    
    def run(self):
        """Запуск бота"""
        print("Бот запущен...")
        print(f"ID группы: {GROUP_ID}")
        print(f"ID поста: {TARGET_POST_ID}")
        print(f"Загаданный код: {SECRET_CODE}")
        print("Ожидание комментариев...")
        
        for event in self.longpoll.listen():
            try:
                # Обработка комментариев к постам
                if event.type == VkEventType.WALL_REPLY_NEW:
                    self.handle_comment(event)
                
                # Обработка личных сообщений
                elif event.type == VkEventType.MESSAGE_NEW and event.to_me:
                    self.handle_private_message(event)
                    
            except Exception as e:
                print(f"Ошибка: {e}")

if __name__ == "__main__":
    init_db()
    bot = VKBot(VK_TOKEN)
    bot.run()
