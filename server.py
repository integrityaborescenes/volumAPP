import socket
import threading
import pg8000
import datetime
import time
import os

# Database configuration
DB_CONFIG = {
    "user": "postgres",
    "password": "12345",
    "database": "postgres",
    "host": "127.0.0.1",
    "port": 5432
}

clients = {} # словарь для хранения информации о звонках
calls = {} # словарь для хранения соединений демонстрации экрана
screen_sharing_connections = {}
group_clients = {}  # Словарь для хранения соединений группового чата
group_calls = {}  # Словарь для хранения активных групповых звонков
group_call_clients = {}  # Словарь для хранения соединений групповых звонков
user_status = {}  # {username: "online"/"offline"}

class ClientConnection:
    """управления соединениями клиента"""
    def __init__(self, main_socket, addr, username=None):
        self.main_socket = main_socket
        self.screen_socket = None
        self.addr = addr
        self.username = username
        self.is_in_call = False
        self.call_partner = None
        self.is_in_group_call = False
        self.current_group_call_id = None

def handle_group_call_client(client_socket, addr, db_connection):
    """Обработчик клиентов группового звонка на порту 5558"""
    print(f"[GROUP CALL CONNECTION] {addr} connected to group call server.")
    username = None

    while True:
        try:
            data = client_socket.recv(8192)
            if not data:
                break

            try:
                message = data.decode('utf-8')
                messages = message.strip().split('\n')

                for msg in messages:
                    if msg:
                        if msg.startswith("GROUP_CALL_AUTH:"):
                            handle_group_call_auth(msg, client_socket, db_connection)
                        elif msg.startswith("GROUP_CALL_JOIN:"):
                            handle_group_call_join(msg, client_socket, db_connection)
                        elif msg.startswith("GROUP_CALL_LEAVE:"):
                            handle_group_call_leave(msg, client_socket, db_connection)

            except UnicodeDecodeError:
                # Обработка аудиоданных для групповых звонков
                if client_socket in group_call_clients:
                    forward_group_call_audio(data, client_socket)

        except Exception as e:
            print(f"[GROUP CALL ERROR] {e}")
            break

    # Очистка при отключении
    cleanup_group_call_connection(client_socket)
    client_socket.close()
    print(f"[GROUP CALL DISCONNECT] {addr} disconnected from group call server.")


def handle_group_call_auth(message, client_socket, db_connection):
    """Аутентификация для группового звонка"""
    try:
        # Формат: GROUP_CALL_AUTH:username
        parts = message.split(":", 1)
        if len(parts) < 2:
            return

        username = parts[1]
        print(f"[GROUP CALL AUTH] Authenticating {username} for group calls")

        # Сохраняем соединение
        group_call_clients[client_socket] = {
            'username': username,
            'current_group_call': None
        }

        # Отправляем подтверждение
        client_socket.send("GROUP_CALL_AUTH_SUCCESS\n".encode('utf-8'))

    except Exception as e:
        print(f"[GROUP CALL AUTH ERROR] {e}")


def handle_group_call_join(message, client_socket, db_connection):
    """Присоединение к групповому звонку"""
    try:
        # Формат: GROUP_CALL_JOIN:group_id
        parts = message.split(":", 1)
        if len(parts) < 2:
            return

        group_id = int(parts[1])

        if client_socket not in group_call_clients:
            return

        username = group_call_clients[client_socket]['username']

        # Проверяем членство в группе
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT 1 FROM group_members WHERE group_id = %s AND username = %s",
            (group_id, username)
        )

        if cursor.fetchone():
            # Добавляем к активному звонку
            if group_id not in group_calls:
                group_calls[group_id] = {
                    'participants': {},
                    'start_time': time.time(),
                    'status': 'active'
                }

            group_calls[group_id]['participants'][username] = client_socket
            group_call_clients[client_socket]['current_group_call'] = group_id

            # Отправляем подтверждение
            client_socket.send(f"GROUP_CALL_JOINED:{group_id}\n".encode('utf-8'))
            print(f"[GROUP CALL] {username} joined call in group {group_id}")

            # Обновляем статус звонка
            broadcast_group_call_status_to_call_clients(group_id)

        cursor.close()

    except Exception as e:
        print(f"[GROUP CALL JOIN ERROR] {e}")


def handle_group_call_leave(message, client_socket, db_connection):
    try:
        parts = message.split(":", 1)
        if len(parts) < 2:
            return

        group_id = int(parts[1])

        if client_socket not in group_call_clients:
            return

        username = group_call_clients[client_socket]['username']

        # Удаляем из звонка
        if group_id in group_calls and username in group_calls[group_id]['participants']:
            del group_calls[group_id]['participants'][username]
            group_call_clients[client_socket]['current_group_call'] = None

            # Обновляем состояние клиента
            if client_socket in clients:
                client_connection = clients[client_socket]
                if hasattr(client_connection, 'is_in_group_call'):
                    client_connection.is_in_group_call = False
                    client_connection.current_group_call_id = None
                    # Не сбрасываем is_in_call здесь, если это личный звонок

            # Если участников не осталось, завершаем звонок
            if not group_calls[group_id]['participants']:
                del group_calls[group_id]
                print(f"[GROUP CALL] Ended call in group {group_id} - no participants left")

            client_socket.send(f"GROUP_CALL_LEFT:{group_id}\\n".encode('utf-8'))
            print(f"[GROUP CALL] {username} left call in group {group_id}")

            # Обновляем статус для участников группы
            broadcast_group_call_status(group_id, db_connection)

    except Exception as e:
        print(f"[GROUP CALL LEAVE ERROR] {e}")

def forward_group_call_audio(data, sender_socket):
    """Пересылка аудио в групповом звонке через отдельный сокет"""
    try:
        if sender_socket not in group_call_clients:
            return

        sender_info = group_call_clients[sender_socket]
        group_id = sender_info['current_group_call']

        if not group_id or group_id not in group_calls:
            return

        sender_username = sender_info['username']
        participants = group_calls[group_id]['participants']

        print(f"[GROUP CALL AUDIO] Forwarding audio from {sender_username} to {len(participants) - 1} participants")

        # Пересылаем аудио всем участникам кроме отправителя
        forwarded_count = 0
        for participant_username, participant_socket in list(participants.items()):
            if participant_username != sender_username and participant_socket != sender_socket:
                try:
                    if participant_socket in group_call_clients:
                        participant_socket.sendall(data)
                        forwarded_count += 1
                        print(f"[GROUP CALL AUDIO] ✓ Forwarded to {participant_username}")
                except Exception as e:
                    print(f"[GROUP CALL AUDIO ERROR] Failed to forward to {participant_username}: {e}")
                    # Удаляем отключенного участника
                    try:
                        del participants[participant_username]
                        if participant_socket in group_call_clients:
                            group_call_clients[participant_socket]['current_group_call'] = None
                    except:
                        pass

        print(f"[GROUP CALL AUDIO] Successfully forwarded to {forwarded_count} participants")

    except Exception as e:
        print(f"[GROUP CALL AUDIO ERROR] Error forwarding audio: {e}")


def broadcast_group_call_status_to_call_clients(group_id):
    """Рассылает статус группового звонка участникам через сокет звонков"""
    try:
        # Формируем сообщение о статусе звонка
        if group_id in group_calls:
            participants = list(group_calls[group_id]['participants'].keys())
            status_message = f"GROUP_CALL_STATUS:{group_id}:active:{','.join(participants)}"
        else:
            status_message = f"GROUP_CALL_STATUS:{group_id}:inactive:"

        # Отправляем всем участникам звонка
        if group_id in group_calls:
            for participant_username, participant_socket in group_calls[group_id]['participants'].items():
                try:
                    participant_socket.send(f"{status_message}\n".encode('utf-8'))
                except Exception as e:
                    print(f"[GROUP CALL ERROR] Failed to send status to {participant_username}: {e}")

    except Exception as e:
        print(f"[GROUP CALL ERROR] Error broadcasting status: {e}")


def cleanup_group_call_connection(client_socket):
    """Очищает соединение группового звонка"""
    if client_socket in group_call_clients:
        username = group_call_clients[client_socket]['username']
        group_id = group_call_clients[client_socket]['current_group_call']

        # Удаляем из активного звонка
        if group_id and group_id in group_calls:
            if username in group_calls[group_id]['participants']:
                del group_calls[group_id]['participants'][username]

                # Если участников не осталось, завершаем звонок
                if not group_calls[group_id]['participants']:
                    del group_calls[group_id]
                    print(f"[GROUP CALL] Ended call in group {group_id} - participant disconnected")
                else:
                    broadcast_group_call_status_to_call_clients(group_id)

        del group_call_clients[client_socket]
        print(f"[GROUP CALL] Cleaned up connection for {username}")

def handle_group_call_signal(message, client_socket, db_connection):
    """функция обработки сигналов групповых звонков"""
    try:
        parts = message.split(':', 4)
        if len(parts) < 5:
            print(f"[ERROR] Invalid group call signal format: {message}")
            return

        action = parts[1]
        group_id = int(parts[2])
        username = parts[3]
        timestamp = float(parts[4])

        print(f"[GROUP CALL] {action} from {username} in group {group_id}")

        # Получаем соединение клиента
        client_connection = clients.get(client_socket)
        if not client_connection:
            print(f"[ERROR] Client connection not found for {username}")
            return

        # Проверяем членство в группе
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT 1 FROM group_members WHERE group_id = %s AND username = %s",
            (group_id, username)
        )
        if not cursor.fetchone():
            print(f"[GROUP CALL ERROR] User {username} is not a member of group {group_id}")
            cursor.close()
            return
        cursor.close()

        if action == "start":
            # Начинаем новый групповой звонок
            if group_id not in group_calls:
                group_calls[group_id] = {
                    'participants': {},
                    'start_time': timestamp,
                    'status': 'active',
                    'initiator': username
                }

            # Добавляем участника
            group_calls[group_id]['participants'][username] = client_socket
            client_connection.is_in_group_call = True
            client_connection.current_group_call_id = group_id

            print(f"[GROUP CALL] Started/joined group call in group {group_id} by {username}")
            broadcast_group_call_status(group_id, db_connection)

        elif action == "join":
            # Присоединение к активному звонку
            if group_id in group_calls and group_calls[group_id]['status'] == 'active':
                group_calls[group_id]['participants'][username] = client_socket
                client_connection.is_in_group_call = True
                client_connection.current_group_call_id = group_id

                print(f"[GROUP CALL] {username} joined call in group {group_id}")
                broadcast_group_call_status(group_id, db_connection)
            else:
                print(f"[GROUP CALL ERROR] No active call in group {group_id}")

        elif action == "leave":
            # Покидание звонка
            if group_id in group_calls and username in group_calls[group_id]['participants']:
                del group_calls[group_id]['participants'][username]
                client_connection.is_in_group_call = False
                client_connection.current_group_call_id = None

                print(f"[GROUP CALL] {username} left call in group {group_id}")

                # Если участников не осталось, завершаем звонок
                if not group_calls[group_id]['participants']:
                    del group_calls[group_id]
                    print(f"[GROUP CALL] Ended call in group {group_id} - no participants left")

                # Обновляем статус для участников группы
                broadcast_group_call_status(group_id, db_connection)

        elif action == "end":
            # Завершение звонка
            if group_id in group_calls:
                # Уведомляем всех участников о завершении
                for participant_username, participant_socket in group_calls[group_id]['participants'].items():
                    participant_connection = clients.get(participant_socket)
                    if participant_connection:
                        participant_connection.is_in_group_call = False
                        participant_connection.current_group_call_id = None

                del group_calls[group_id]
                print(f"[GROUP CALL] Call ended in group {group_id} by {username}")
                # Обновляем статус для ВСЕХ участников группы
                broadcast_group_call_status(group_id, db_connection)

    except Exception as e:
        print(f"[GROUP CALL ERROR] {e}")


def broadcast_group_call_status(group_id, db_connection):
    """функция рассылки статуса группового звонка всем участникам группы"""
    try:
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT username FROM group_members WHERE group_id = %s",
            (group_id,)
        )
        group_members = [row[0] for row in cursor.fetchall()]
        cursor.close()

        # Формируем сообщение о статусе звонка
        if group_id in group_calls:
            participants = list(group_calls[group_id]['participants'].keys())
            status_message = f"GROUP_CALL_STATUS:{group_id}:active:{','.join(participants)}"
        else:
            # отправляем статус "inactive" ВСЕМ участникам группы
            status_message = f"GROUP_CALL_STATUS:{group_id}:inactive:"

        print(f"[GROUP CALL] Broadcasting status: {status_message}")

        # Отправляем статус участникам группы, а не только участникам звонка
        for member_username in group_members:
            for client_socket, client_data in clients.items():
                if hasattr(client_data, 'username') and client_data.username == member_username:
                    try:
                        client_socket.send(f"{status_message}\n".encode('utf-8'))
                        print(f"[GROUP CALL] Sent status to group member {member_username}")
                    except Exception as e:
                        print(f"[GROUP CALL ERROR] Failed to send status to {member_username}: {e}")
                    break

    except Exception as e:
        print(f"[GROUP CALL ERROR] Error broadcasting status: {e}")

def forward_group_audio_data(data, sender_socket):
    """функция пересылки группового аудио"""
    try:
        sender_connection = clients.get(sender_socket)
        if not sender_connection or not sender_connection.is_in_group_call:
            print("[GROUP AUDIO] Sender not in group call")
            return

        group_id = sender_connection.current_group_call_id
        if group_id not in group_calls:
            print(f"[GROUP AUDIO] Group {group_id} not found in active calls")
            return

        sender_username = sender_connection.username
        participants = group_calls[group_id]['participants']

        print(f"[GROUP AUDIO] Forwarding audio from {sender_username} to {len(participants) - 1} participants")

        # Пересылаем аудио всем участникам кроме отправителя
        forwarded_count = 0
        for participant_username, participant_socket in list(participants.items()):
            if participant_username != sender_username and participant_socket != sender_socket:
                try:
                    if participant_socket in clients:
                        participant_socket.sendall(data)
                        forwarded_count += 1
                        print(f"[GROUP AUDIO] ✓ Forwarded to {participant_username}")
                    else:
                        print(f"[GROUP AUDIO] ✗ Socket not found for {participant_username}")
                except Exception as e:
                    print(f"[GROUP AUDIO ERROR] Failed to forward to {participant_username}: {e}")
                    # Удаляем отключенного участника
                    try:
                        del participants[participant_username]
                        participant_connection = clients.get(participant_socket)
                        if participant_connection:
                            participant_connection.is_in_group_call = False
                            participant_connection.current_group_call_id = None
                    except:
                        pass

        print(f"[GROUP AUDIO] Successfully forwarded to {forwarded_count} participants")

    except Exception as e:
        print(f"[GROUP AUDIO ERROR] Error forwarding audio: {e}")

def handle_screen_sharing_connection(screen_socket, addr, db_connection):
    """Обрабатывает отдельное соединение для демонстрации экрана"""
    print(f"[SCREEN] New screen sharing connection from {addr}")

    screen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)
    screen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)

    buffer = ""
    screen_data_buffers = {}

    try:
        while True:
            try:
                data = screen_socket.recv(65536)
                if not data:
                    break

                try:
                    # Пытаемся декодировать как текст
                    buffer += data.decode('utf-8')
                    messages = buffer.split('\n')
                    buffer = messages[-1]

                    for message in messages[:-1]:
                        if message:
                            print(f"[SCREEN] Received message: {message[:50]}...")

                            if message.startswith("SCREEN_AUTH:"):
                                handle_screen_auth(message, screen_socket, db_connection)
                            elif message.startswith("SCREEN_CONTROL:"):
                                handle_screen_control(message, screen_socket, db_connection)
                            elif message.startswith("SCREEN_DATA_START:"):
                                handle_screen_data_start(message, screen_socket, db_connection)
                            elif message.startswith("SCREEN_DATA_CHUNK:"):
                                handle_screen_data_chunk(message, screen_socket, db_connection)
                            elif message.startswith("SCREEN_DATA_END:"):
                                handle_screen_data_end(message, screen_socket, db_connection)
                            elif message.startswith("GROUP_SCREEN_DATA_START:"):
                                handle_group_screen_data_start(message, screen_socket, db_connection)
                            elif message.startswith("GROUP_SCREEN_DATA_CHUNK:"):
                                handle_group_screen_data_chunk(message, screen_socket, db_connection)
                            elif message.startswith("GROUP_SCREEN_DATA_END:"):
                                handle_group_screen_data_end(message, screen_socket, db_connection)

                except UnicodeDecodeError:
                    # Это бинарные данные
                    handle_binary_screen_data(data, screen_socket, db_connection)

            except socket.timeout:
                continue
            except ConnectionResetError:
                print(f"[SCREEN] Connection reset by peer {addr}")
                break
            except Exception as e:
                print(f"[SCREEN ERROR] {e}")
                break

    except Exception as e:
        print(f"[SCREEN ERROR] {e}")
    finally:
        cleanup_screen_connection(screen_socket)
        screen_socket.close()
        print(f"[SCREEN] Screen sharing connection {addr} closed")


def handle_group_client(client_socket, addr, db_connection):
    """Модифицированный обработчик группового чата с поддержкой файлов"""
    print(f"[GROUP CONNECTION] {addr} connected to group chat.")
    username = None

    while True:
        try:
            data = client_socket.recv(8192)  # Увеличиваем буфер для файлов
            if not data:
                break

            try:
                message = data.decode('utf-8')
                messages = message.strip().split('\n')

                for msg in messages:
                    if msg:
                        if msg.startswith("GROUP_AUTH:"):
                            handle_group_auth(msg, client_socket, db_connection)
                        elif msg.startswith("GROUP_MESSAGE:"):
                            handle_group_message(msg, client_socket, db_connection)
                        elif msg.startswith("GROUP_EDIT_MESSAGE:"):
                            handle_group_edit_message(msg, client_socket, db_connection)
                        elif msg.startswith("GROUP_DELETE_MESSAGE:"):
                            handle_group_delete_message(msg, client_socket, db_connection)
                        elif msg.startswith("GROUP_JOIN:"):
                            handle_group_join(msg, client_socket, db_connection)
                        elif msg.startswith("GROUP_LEAVE:"):
                            handle_group_leave(msg, client_socket, db_connection)
                        # Обработка групповых файлов
                        elif msg.startswith("GROUP_FILE_TRANSFER:"):
                            handle_group_file_transfer(msg, client_socket, db_connection)

            except UnicodeDecodeError:
                # Обработка бинарных данных если нужно
                pass

        except Exception as e:
            print(f"[GROUP ERROR] {e}")
            break

    # Очистка при отключении
    cleanup_group_connection(client_socket)
    client_socket.close()
    print(f"[GROUP DISCONNECT] {addr} disconnected from group chat.")


def handle_group_auth(message, client_socket, db_connection):
    """Обрабатывает аутентификацию для группового чата"""
    try:
        # Формат: GROUP_AUTH:username
        parts = message.split(":", 1)
        if len(parts) < 2:
            return

        username = parts[1]
        print(f"[GROUP AUTH] Authenticating {username} for group chat")

        # Сохраняем соединение
        group_clients[client_socket] = {
            'username': username,
            'joined_groups': set()
        }

        # Отправляем подтверждение
        client_socket.send("GROUP_AUTH_SUCCESS\n".encode('utf-8'))

    except Exception as e:
        print(f"[GROUP AUTH ERROR] {e}")


def handle_group_join(message, client_socket, db_connection):
    """Обрабатывает присоединение к группе"""
    try:
        # Формат: GROUP_JOIN:group_id
        parts = message.split(":", 1)
        if len(parts) < 2:
            return

        group_id = int(parts[1])

        if client_socket not in group_clients:
            return

        username = group_clients[client_socket]['username']

        # Проверяем, является ли пользователь участником группы
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT 1 FROM group_members WHERE group_id = %s AND username = %s",
            (group_id, username)
        )

        if cursor.fetchone():
            # Добавляем группу к активным группам пользователя
            group_clients[client_socket]['joined_groups'].add(group_id)

            # Отправляем подтверждение
            client_socket.send(f"GROUP_JOINED:{group_id}\n".encode('utf-8'))
            print(f"[GROUP JOIN] {username} joined group {group_id}")

        cursor.close()

    except Exception as e:
        print(f"[GROUP JOIN ERROR] {e}")


def handle_group_leave(message, client_socket, db_connection):
    """Обрабатывает выход из группы"""
    try:
        # Формат: GROUP_LEAVE:group_id
        parts = message.split(":", 1)
        if len(parts) < 2:
            return

        group_id = int(parts[1])

        if client_socket not in group_clients:
            return

        username = group_clients[client_socket]['username']

        # Удаляем группу из активных групп пользователя
        if group_id in group_clients[client_socket]['joined_groups']:
            group_clients[client_socket]['joined_groups'].remove(group_id)

            # Отправляем подтверждение
            client_socket.send(f"GROUP_LEFT:{group_id}\n".encode('utf-8'))
            print(f"[GROUP LEAVE] {username} left group {group_id}")


    except Exception as e:
        print(f"[GROUP LEAVE ERROR] {e}")


def handle_group_message(message, client_socket, db_connection):
    """Обрабатывает сообщения в группе"""
    try:
        # Формат: GROUP_MESSAGE:group_id:sender:content
        parts = message.split(":", 3)
        if len(parts) < 4:
            print(f"[GROUP MESSAGE ERROR] Invalid format: {message}")
            return

        group_id = int(parts[1])
        sender = parts[2]
        content = parts[3]

        if client_socket not in group_clients:
            return

        username = group_clients[client_socket]['username']

        # Проверяем, что отправитель соответствует аутентифицированному пользователю
        if sender != username:
            print(f"[GROUP MESSAGE ERROR] Sender mismatch: {sender} != {username}")
            return

        # Проверяем, что пользователь присоединился к группе
        if group_id not in group_clients[client_socket]['joined_groups']:
            print(f"[GROUP MESSAGE ERROR] User {username} not joined to group {group_id}")
            return

        # Проверяем, является ли пользователь участником группы в БД
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT 1 FROM group_members WHERE group_id = %s AND username = %s",
            (group_id, username)
        )

        if not cursor.fetchone():
            print(f"[GROUP MESSAGE ERROR] User {username} is not a member of group {group_id}")
            cursor.close()
            return

        # Сохраняем сообщение в БД
        cursor.execute(
            """
            INSERT INTO group_messages (group_id, sender, content)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (group_id, sender, content)
        )
        message_id = cursor.fetchone()[0]
        db_connection.commit()
        cursor.close()

        print(f"[GROUP MESSAGE] Saved message from {sender} in group {group_id}: {content}")

        # Рассылаем сообщение в оригинальном формате БЕЗ ID
        # ID нужен только для редактирования/удаления, но не для отображения
        broadcast_to_group(group_id, f"GROUP_MESSAGE:{group_id}:{sender}:{content}", exclude_socket=None)

    except Exception as e:
        print(f"[GROUP MESSAGE ERROR] {e}")
        if 'cursor' in locals():
            db_connection.rollback()
            cursor.close()


def handle_group_edit_message(message, client_socket, db_connection):
    """Обрабатывает редактирование сообщений в группе"""
    try:
        # Формат: GROUP_EDIT_MESSAGE:group_id:sender:new_content:message_id
        parts = message.split(":", 4)
        if len(parts) < 5:
            print(f"[GROUP EDIT ERROR] Invalid format: {message}")
            return

        group_id = int(parts[1])
        sender = parts[2]
        new_content = parts[3]
        message_id = int(parts[4])

        if client_socket not in group_clients:
            return

        username = group_clients[client_socket]['username']

        # Проверяем, что отправитель соответствует аутентифицированному пользователю
        if sender != username:
            print(f"[GROUP EDIT ERROR] Sender mismatch: {sender} != {username}")
            return

        # Проверяем, что пользователь присоединился к группе
        if group_id not in group_clients[client_socket]['joined_groups']:
            print(f"[GROUP EDIT ERROR] User {username} not joined to group {group_id}")
            return

        # Проверяем, является ли пользователь владельцем сообщения
        cursor = db_connection.cursor()
        cursor.execute(
            """
            SELECT 1 FROM group_messages 
            WHERE id = %s AND group_id = %s AND sender = %s
            """,
            (message_id, group_id, username)
        )

        if not cursor.fetchone():
            print(f"[GROUP EDIT ERROR] User {username} is not the owner of message {message_id}")
            cursor.close()
            return

        # Обновляем сообщение в БД
        cursor.execute(
            """
            UPDATE group_messages 
            SET content = %s, edited = TRUE 
            WHERE id = %s AND sender = %s
            """,
            (new_content, message_id, username)
        )
        db_connection.commit()
        cursor.close()

        print(f"[GROUP EDIT] Updated message {message_id} from {sender} in group {group_id}: {new_content}")

        # Рассылаем уведомление об обновлении всем участникам группы
        broadcast_to_group(group_id, f"GROUP_MESSAGE_EDITED:{group_id}:{sender}:{message_id}", exclude_socket=None)

    except Exception as e:
        print(f"[GROUP EDIT ERROR] {e}")
        if 'cursor' in locals():
            db_connection.rollback()
            cursor.close()


def handle_group_delete_message(message, client_socket, db_connection):
    """Обрабатывает удаление сообщений в группе"""
    try:
        # Формат: GROUP_DELETE_MESSAGE:group_id:sender:message_id
        parts = message.split(":", 3)
        if len(parts) < 4:
            print(f"[GROUP DELETE ERROR] Invalid format: {message}")
            return

        group_id = int(parts[1])
        sender = parts[2]
        message_id = int(parts[3])

        if client_socket not in group_clients:
            return

        username = group_clients[client_socket]['username']

        # Проверяем, что отправитель соответствует аутентифицированному пользователю
        if sender != username:
            print(f"[GROUP DELETE ERROR] Sender mismatch: {sender} != {username}")
            return

        # Проверяем, что пользователь присоединился к группе
        if group_id not in group_clients[client_socket]['joined_groups']:
            print(f"[GROUP DELETE ERROR] User {username} not joined to group {group_id}")
            return

        # Проверяем, является ли пользователь владельцем сообщения или администратором группы
        cursor = db_connection.cursor()

        # Проверяем роль пользователя в группе
        cursor.execute(
            """
            SELECT role FROM group_members 
            WHERE group_id = %s AND username = %s
            """,
            (group_id, username)
        )
        role_result = cursor.fetchone()

        if not role_result:
            print(f"[GROUP DELETE ERROR] User {username} is not a member of group {group_id}")
            cursor.close()
            return

        user_role = role_result[0]

        # Проверяем владельца сообщения
        cursor.execute(
            """
            SELECT sender FROM group_messages 
            WHERE id = %s AND group_id = %s
            """,
            (message_id, group_id)
        )
        message_owner_result = cursor.fetchone()

        if not message_owner_result:
            print(f"[GROUP DELETE ERROR] Message {message_id} not found in group {group_id}")
            cursor.close()
            return

        message_owner = message_owner_result[0]

        # Разрешаем удаление только владельцу сообщения или администратору/создателю группы
        if message_owner != username and user_role not in ['admin', 'creator']:
            print(f"[GROUP DELETE ERROR] User {username} cannot delete message {message_id} owned by {message_owner}")
            cursor.close()
            return

        # Обновляем сообщение в БД
        cursor.execute(
            """
            UPDATE group_messages 
            SET content = 'Сообщение удалено', deleted = TRUE 
            WHERE id = %s AND group_id = %s
            """,
            (message_id, group_id)
        )
        db_connection.commit()
        cursor.close()

        print(f"[GROUP DELETE] Deleted message {message_id} from {message_owner} in group {group_id}")

        # Рассылаем уведомление об удалении всем участникам группы
        broadcast_to_group(group_id, f"GROUP_MESSAGE_DELETED:{group_id}:{message_owner}:{message_id}",
                           exclude_socket=None)

    except Exception as e:
        print(f"[GROUP DELETE ERROR] {e}")
        if 'cursor' in locals():
            db_connection.rollback()
            cursor.close()


def handle_group_file_transfer(message, client_socket, db_connection):
    """Обрабатывает передачу файлов в группах"""
    try:
        parts = message.split(":", 5)
        if len(parts) < 5:
            print(f"[ERROR] Invalid group file transfer format: {message}")
            return
        action = parts[1]  # START, CHUNK, END
        if action not in ["START", "CHUNK", "END"]:
            print(f"[ОШИБКА] Неизвестное действие в передаче файла: {action}")
            return
        sender = parts[2]
        group_id = int(parts[3])

        if client_socket not in group_clients:
            return

        username = group_clients[client_socket]['username']

        # Проверяем, что отправитель соответствует аутентифицированному пользователю
        if sender != username:
            print(f"[GROUP FILE ERROR] Sender mismatch: {sender} != {username}")
            return

        # Проверяем, что пользователь присоединился к группе
        if group_id not in group_clients[client_socket]['joined_groups']:
            print(f"[GROUP FILE ERROR] User {username} not joined to group {group_id}")
            return

        # Проверяем, является ли пользователь участником группы в БД
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT 1 FROM group_members WHERE group_id = %s AND username = %s",
            (group_id, username)
        )

        if not cursor.fetchone():
            print(f"[GROUP FILE ERROR] User {username} is not a member of group {group_id}")
            cursor.close()
            return

        if action == "START":
            file_info = parts[4].split(":", 1)
            file_name = file_info[0]
            file_size = file_info[1] if len(file_info) > 1 else "0"

            print(f"[GROUP FILE] Starting transfer of {file_name} from {sender} to group {group_id}")

            # Не сохраняем сообщение о начале передачи файла в БД
            # Это будет сделано только при завершении передачи

        elif action == "END":
            file_name = parts[4]

            print(f"[GROUP FILE] Completed transfer of {file_name} from {sender} to group {group_id}")

            # Определяем тип файла
            file_extension = os.path.splitext(file_name)[1].lower()
            is_image = file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']

            # Сохраняем сообщение о завершении передачи файла в БД
            if is_image:
                content = f"[Вложение: {file_name}]"
            else:
                content = f"[Файл получен: {file_name}]"

            cursor.execute(
                """
                INSERT INTO group_messages (group_id, sender, content)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (group_id, sender, content)
            )
            message_id = cursor.fetchone()[0]
            db_connection.commit()

            # Рассылаем сообщение о файле всем участникам группы
            broadcast_to_group(group_id, f"GROUP_MESSAGE:{group_id}:{sender}:{content}", exclude_socket=None)

        cursor.close()

        # Пересылаем сообщение о передаче файла всем участникам группы
        broadcast_to_group(group_id, message, exclude_socket=client_socket)

    except Exception as e:
        print(f"[GROUP FILE ERROR] {e}")
        if 'cursor' in locals():
            db_connection.rollback()
            cursor.close()


def broadcast_to_group(group_id, message, exclude_socket=None):
    """Рассылает сообщение всем участникам группы """
    try:
        # Находим всех подключенных участников группы
        for client_socket, client_data in group_clients.items():
            if (group_id in client_data['joined_groups'] and
                client_socket != exclude_socket):
                try:
                    client_socket.send(f"{message}\n".encode('utf-8'))
                except Exception as e:
                    print(f"[BROADCAST ERROR] Failed to send to client: {e}")
    except Exception as e:
        print(f"[BROADCAST ERROR] {e}")


def cleanup_group_connection(client_socket):
    """Очищает соединение группового чата"""
    if client_socket in group_clients:
        username = group_clients[client_socket]['username']
        joined_groups = group_clients[client_socket]['joined_groups'].copy()


        del group_clients[client_socket]

def cleanup_screen_connection(screen_socket):
    """Очищает соединение демонстрации экрана"""
    # Удаляем из screen_sharing_connections
    if screen_socket in screen_sharing_connections:
        del screen_sharing_connections[screen_socket]

    # Находим и очищаем связь в clients
    for client_socket, client_data in clients.items():
        if isinstance(client_data, ClientConnection) and client_data.screen_socket == screen_socket:
            client_data.screen_socket = None
            break


def handle_screen_auth(message, screen_socket, db_connection):
    """аутентификация соединения демонстрации экрана"""
    try:
        parts = message.split(":", 1)
        if len(parts) < 2:
            return

        username = parts[1]
        print(f"[SCREEN] Authenticating screen connection for {username}")

        # Находим основное соединение пользователя
        found_client = False
        for client_socket, client_data in clients.items():
            if isinstance(client_data, ClientConnection) and client_data.username == username:
                client_data.screen_socket = screen_socket
                screen_sharing_connections[screen_socket] = client_data
                found_client = True
                print(f"[SCREEN] ✓ Linked screen connection to user {username}")
                break

        if not found_client:
            print(f"[SCREEN] ✗ Warning: No main connection found for user {username}")

        # Отладочная информация
        debug_connections()

    except Exception as e:
        print(f"[SCREEN ERROR] Error in screen auth: {e}")


def debug_connections():
    """Функция для отладки соединений"""
    print("\n[DEBUG] Current connections:")
    print(f"[DEBUG] Main clients: {len(clients)}")
    for socket, client_data in clients.items():
        if hasattr(client_data, 'username'):
            screen_status = "✓" if hasattr(client_data, 'screen_socket') and client_data.screen_socket else "✗"
            print(f"[DEBUG]   - {client_data.username}: screen_socket {screen_status}")

    print(f"[DEBUG] Screen connections: {len(screen_sharing_connections)}")
    for socket, client_data in screen_sharing_connections.items():
        if hasattr(client_data, 'username'):
            print(f"[DEBUG]   - {client_data.username}")

    print(f"[DEBUG] Group clients: {len(group_clients)}")
    for socket, client_data in group_clients.items():
        if 'username' in client_data:
            print(f"[DEBUG]   - {client_data['username']}")

def handle_binary_screen_data(data, sender_socket, db_connection):
    """Обрабатывает бинарные данные демонстрации экрана"""
    try:
        if sender_socket not in screen_sharing_connections:
            return

        sender_connection = screen_sharing_connections[sender_socket]
        if not sender_connection.username or not sender_connection.is_in_call:
            return

        recipient_username = sender_connection.call_partner
        if not recipient_username:
            return

        recipient_connection = None
        for client_socket, client_data in clients.items():
            if isinstance(client_data, ClientConnection) and client_data.username == recipient_username:
                recipient_connection = client_data
                break

        if recipient_connection and recipient_connection.screen_socket:
            try:
                recipient_connection.screen_socket.sendall(data)
            except Exception as e:
                print(f"[SCREEN ERROR] Failed to forward binary screen data: {e}")

    except Exception as e:
        print(f"[SCREEN ERROR] Error handling binary screen data: {e}")


def handle_screen_control(message, sender_socket, db_connection):
    """Обрабатывает сигналы управления демонстрацией экрана"""
    try:
        parts = message.split(":", 3)
        if len(parts) < 4:
            print(f"[ERROR] Invalid screen control format: {message}")
            return

        sender = parts[1]
        recipient = parts[2]
        action = parts[3]

        print(f"[SCREEN] {action} screen sharing from {sender} to {recipient}")

        # Проверяем дружбу
        try:
            cursor = db_connection.cursor()
            cursor.execute(
                """
                SELECT 1 FROM friends 
                WHERE (user1 = %s AND user2 = %s) OR (user1 = %s AND user2 = %s)
                """,
                (sender, recipient, recipient, sender)
            )
            are_friends = cursor.fetchone() is not None
            cursor.close()

            if not are_friends:
                print(f"[FILTER] Blocked screen sharing from {sender} to non-friend {recipient}")
                return
        except Exception as e:
            print(f"[ERROR] Failed to check friendship for screen sharing: {e}")
            return

        # Ищем соединение получателя
        recipient_connection = None
        for client_socket, client_data in clients.items():
            if isinstance(client_data, ClientConnection) and client_data.username == recipient:
                recipient_connection = client_data
                break

        if recipient_connection and recipient_connection.screen_socket:
            try:
                recipient_connection.screen_socket.send(f"{message}\n".encode('utf-8'))
                print(f"[SCREEN] Sent {action} signal to {recipient}")
            except Exception as e:
                print(f"[ERROR] Failed to send screen control signal: {e}")
        else:
            print(f"[ERROR] Recipient {recipient} screen connection not found")

    except Exception as e:
        print(f"[ERROR] Error handling screen control: {e}")

def handle_group_screen_sharing(message, sender_socket, db_connection):
    """обработка групповой демонстрации экрана"""
    try:
        # Формат: GROUP_SCREEN_CONTROL:action:group_id:sender:timestamp
        parts = message.split(":", 4)
        if len(parts) < 5:
            print(f"[ERROR] Invalid group screen control format: {message}")
            return

        action = parts[1]  # start, stop
        group_id = int(parts[2])
        sender = parts[3]
        timestamp = float(parts[4])

        print(f"[GROUP SCREEN] {action} from {sender} in group {group_id}")

        # Проверяем членство в группе
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT 1 FROM group_members WHERE group_id = %s AND username = %s",
            (group_id, sender)
        )
        if not cursor.fetchone():
            print(f"[GROUP SCREEN ERROR] User {sender} is not a member of group {group_id}")
            cursor.close()
            return

        # Получаем всех участников группы, которые сейчас онлайн
        cursor.execute(
            "SELECT username FROM group_members WHERE group_id = %s AND username != %s",
            (group_id, sender)
        )
        group_members = [row[0] for row in cursor.fetchall()]
        cursor.close()

        print(f"[GROUP SCREEN] Broadcasting to {len(group_members)} group members")

        # Отправляем сигнал всем онлайн участникам группы
        sent_count = 0
        for member_username in group_members:
            for client_socket, client_data in clients.items():
                if (hasattr(client_data, 'username') and
                    client_data.username == member_username):
                    try:
                        # Отправляем через основной сокет
                        signal = f"GROUP_SCREEN_SIGNAL:{action}:{group_id}:{sender}:{timestamp}"
                        client_socket.send(f"{signal}\n".encode('utf-8'))
                        sent_count += 1
                        print(f"[GROUP SCREEN] ✓ Sent {action} signal to {member_username}")
                    except Exception as e:
                        print(f"[GROUP SCREEN ERROR] Failed to send signal to {member_username}: {e}")
                    break

        print(f"[GROUP SCREEN] Successfully sent signals to {sent_count} participants")

    except Exception as e:
        print(f"[GROUP SCREEN ERROR] {e}")
        import traceback
        traceback.print_exc()


def handle_group_screen_data(data, sender_socket, group_id):
    """Пересылает данные экрана всем участникам группового звонка"""
    try:
        sender_connection = clients.get(sender_socket)
        if not sender_connection or not hasattr(sender_connection, 'username'):
            return

        sender_username = sender_connection.username

        # Проверяем, что отправитель в групповом звонке
        if group_id not in group_calls:
            return

        participants = group_calls[group_id]['participants']
        if sender_username not in participants:
            return

        print(f"[GROUP SCREEN DATA] Forwarding screen data from {sender_username} to group {group_id}")

        # Пересылаем данные всем участникам кроме отправителя
        forwarded_count = 0
        for participant_username, participant_socket in list(participants.items()):
            if participant_username != sender_username:
                try:
                    if participant_socket in clients:
                        # Отправляем через screen_socket если он есть
                        participant_connection = clients[participant_socket]
                        if hasattr(participant_connection, 'screen_socket') and participant_connection.screen_socket:
                            participant_connection.screen_socket.sendall(data)
                            forwarded_count += 1
                            print(f"[GROUP SCREEN DATA] ✓ Forwarded to {participant_username}")
                except Exception as e:
                    print(f"[GROUP SCREEN DATA ERROR] Failed to forward to {participant_username}: {e}")

        print(f"[GROUP SCREEN DATA] Successfully forwarded to {forwarded_count} participants")

    except Exception as e:
        print(f"[GROUP SCREEN DATA ERROR] Error forwarding screen data: {e}")


def handle_screen_data_start(message, sender_socket, db_connection):
    """Обрабатывает начало передачи кадра"""
    try:
        parts = message.split(":", 4)
        if len(parts) >= 5:
            sender = parts[1]
            recipient = parts[2]

            # Находим получателя и пересылаем сообщение
            recipient_connection = None
            for client_socket, client_data in clients.items():
                if isinstance(client_data, ClientConnection) and client_data.username == recipient:
                    recipient_connection = client_data
                    break

            if recipient_connection and recipient_connection.screen_socket:
                try:
                    recipient_connection.screen_socket.send(f"{message}\n".encode('utf-8'))
                    print(f"[SCREEN] Forwarded data start to {recipient}")
                except Exception as e:
                    print(f"[ERROR] Failed to forward screen data start: {e}")

    except Exception as e:
        print(f"[SCREEN ERROR] Error handling screen data start: {e}")


def handle_screen_data_chunk(message, sender_socket, db_connection):
    """Обрабатывает часть кадра"""
    try:
        parts = message.split(":", 5)
        if len(parts) >= 6:
            sender = parts[1]
            recipient = parts[2]

            # Находим получателя и пересылаем сообщение
            recipient_connection = None
            for client_socket, client_data in clients.items():
                if isinstance(client_data, ClientConnection) and client_data.username == recipient:
                    recipient_connection = client_data
                    break

            if recipient_connection and recipient_connection.screen_socket:
                try:
                    recipient_connection.screen_socket.send(f"{message}\n".encode('utf-8'))
                except Exception as e:
                    print(f"[ERROR] Failed to forward screen data chunk: {e}")

    except Exception as e:
        print(f"[SCREEN ERROR] Error handling screen data chunk: {e}")


def handle_screen_data_end(message, sender_socket, db_connection):
    """Обрабатывает завершение передачи кадра"""
    try:
        parts = message.split(":", 3)
        if len(parts) >= 4:
            sender = parts[1]
            recipient = parts[2]

            # Находим получателя и пересылаем сообщение
            recipient_connection = None
            for client_socket, client_data in clients.items():
                if isinstance(client_data, ClientConnection) and client_data.username == recipient:
                    recipient_connection = client_data
                    break

            if recipient_connection and recipient_connection.screen_socket:
                try:
                    recipient_connection.screen_socket.send(f"{message}\n".encode('utf-8'))
                    print(f"[SCREEN] Forwarded data end to {recipient}")
                except Exception as e:
                    print(f"[ERROR] Failed to forward screen data end: {e}")

    except Exception as e:
        print(f"[SCREEN ERROR] Error handling screen data end: {e}")

def handle_screen_data(message, sender_socket, db_connection):
    """Обрабатывает данные демонстрации экрана"""
    try:
        # Извлекаем информацию о получателе из сообщения
        parts = message.split(":", 3)
        if len(parts) >= 3:
            sender = parts[1]
            recipient = parts[2]

            # Ищем соединение получателя
            recipient_connection = None
            for client_socket, client_data in clients.items():
                if isinstance(client_data, ClientConnection) and client_data.username == recipient:
                    recipient_connection = client_data
                    break

            if recipient_connection and recipient_connection.screen_socket:
                try:
                    # Пересылаем данные получателю через соединение демонстрации экрана
                    recipient_connection.screen_socket.send(f"{message}\n".encode('utf-8'))
                except Exception as e:
                    print(f"[ERROR] Failed to send screen data: {e}")
            else:
                print(f"[ERROR] Recipient {recipient} screen connection not found")
    except Exception as e:
        print(f"[ERROR] Error handling screen data: {e}")


def handle_client(client_socket, addr, db_connection):
    print(f"[NEW CONNECTION] {addr} connected.")
    username = None
    client_connection = ClientConnection(client_socket, addr)

    audio_buffer = b""
    expecting_group_audio = False
    group_audio_id = None

    while True:
        try:
            data = client_socket.recv(1024)
            if not data:
                break

            try:
                # Сначала проверяем, ожидаем ли мы групповые аудиоданные
                if expecting_group_audio:
                    # аудиоданные для группового звонка
                    print(f"[GROUP AUDIO] Received audio data for group {group_audio_id}")
                    forward_group_audio_data(data, client_socket)
                    expecting_group_audio = False
                    group_audio_id = None
                    continue

                message = data.decode('utf-8')
                messages = message.strip().split('\n')
                for msg in messages:
                    if msg:
                        # Обработка статусов
                        if msg.startswith("STATUS_ONLINE:"):
                            handle_status_online(msg, client_socket, db_connection)
                            continue
                        elif msg.startswith("STATUS_OFFLINE:"):
                            handle_status_offline(msg, client_socket, db_connection)
                            continue
                        elif msg.startswith("STATUS_REQUEST:"):
                            handle_status_request(msg, client_socket, db_connection)
                            continue
                        # Убираем обработку старых сообщений о статусе
                        if ": в сети" in msg or ": вышел из сети" in msg:
                            continue  # Игнорируем старые сообщения о статусе
                        if msg.startswith("GROUP_SCREEN_DATA_START:"):
                           handle_group_screen_data_start(msg, client_socket, db_connection)
                           continue
                        if msg.startswith("GROUP_SCREEN_DATA_CHUNK:"):
                           handle_group_screen_data_chunk(msg, client_socket, db_connection)
                           continue
                        if msg.startswith("GROUP_SCREEN_DATA_END:"):
                            handle_group_screen_data_end(msg, client_socket, db_connection)
                            continue
                        if msg.startswith("GROUP_CALL_AUDIO:"):
                            parts = msg.split(":", 1)
                            if len(parts) >= 2:
                                group_audio_id = int(parts[1])
                                expecting_group_audio = True
                                print(f"[GROUP AUDIO] Expecting audio data for group {group_audio_id}")
                                continue
                        elif msg.startswith("CALL_SIGNAL:"):
                            handle_call_signal(msg, client_socket, db_connection)
                            continue
                        if msg.startswith("GROUP_CALL_SIGNAL:"):
                            handle_group_call_signal(msg, client_socket, db_connection)
                            continue
                        elif msg.startswith("GROUP_SCREEN_CONTROL:"):
                            handle_group_screen_sharing(msg, client_socket, db_connection)
                            continue
                        # Обработка уведомлений об исключении из группы
                        if msg.startswith("GROUP_EXCLUSION:"):
                            handle_group_exclusion(msg, client_socket, db_connection)
                            continue
                        elif msg.startswith("EDIT_MESSAGE:"):
                            handle_edit_message(msg, client_socket, db_connection)
                            continue
                        elif msg.startswith("DELETE_MESSAGE:"):
                            handle_delete_message(msg, client_socket, db_connection)
                            continue
                        elif msg.startswith("FILE_TRANSFER:"):
                            handle_file_transfer(msg, client_socket, db_connection)
                            continue
                        # Обработка личных сообщений с явным указанием получателя
                        elif msg.startswith("DIRECT_MESSAGE:"):
                            handle_direct_message(msg, client_socket, db_connection)
                            continue
                        elif ":" in msg:
                            parts = msg.split(":", 1)
                            sender_username = parts[0].strip()
                            content = parts[1].strip()

                            if client_socket not in clients:
                                client_connection.username = sender_username
                                clients[client_socket] = client_connection
                                username = sender_username
                                print(f"[NEW USER] {sender_username} connected")
                            elif clients[client_socket].username != sender_username:
                                clients[client_socket].username = sender_username
                                username = sender_username
                                print(f"[UPDATE] User {sender_username} updated their username")

                            # логика обработки сообщений
                            if sender_username != "Система" or not content.startswith("Чат с "):
                                receiver = None
                                for sock, client_data in clients.items():
                                    if isinstance(client_data, ClientConnection) and sock != client_socket and client_data.username != sender_username:
                                        receiver = client_data.username
                                        break

                                if not receiver and ":" in content:
                                    try:
                                        cursor = db_connection.cursor()
                                        cursor.execute(
                                            "SELECT username FROM users WHERE username != %s",
                                            (sender_username,)
                                        )
                                        potential_receivers = cursor.fetchall()
                                        for potential_receiver in potential_receivers:
                                            potential_name = potential_receiver[0]
                                            if f"@{potential_name}" in content or potential_name in content:
                                                receiver = potential_name
                                                break
                                        cursor.close()
                                    except Exception as e:
                                        print(f"[ERROR] Failed to find receiver: {e}")

                                if not receiver:
                                    try:
                                        cursor = db_connection.cursor()
                                        cursor.execute(
                                            """
                                            SELECT receiver FROM messages 
                                            WHERE sender = %s 
                                            ORDER BY timestamp DESC 
                                            LIMIT 1
                                            """,
                                            (sender_username,)
                                        )
                                        last_receiver = cursor.fetchone()
                                        if last_receiver:
                                            receiver = last_receiver[0]
                                        else:
                                            cursor.execute(
                                                """
                                                SELECT sender FROM messages 
                                                WHERE receiver = %s 
                                                ORDER BY timestamp DESC 
                                                LIMIT 1
                                                """,
                                                (sender_username,)
                                            )
                                            last_sender = cursor.fetchone()
                                            if last_sender:
                                                receiver = last_sender[0]
                                        cursor.close()
                                    except Exception as e:
                                        print(f"[ERROR] Failed to find receiver from history: {e}")

                                if receiver:
                                    try:
                                        save_message(db_connection, sender_username, receiver, content)
                                        print(f"[DATABASE] Saved message from {sender_username} to {receiver}: {content}")
                                    except Exception as e:
                                        print(f"[ERROR] Failed to save message: {e}")
                                else:
                                    print(f"[WARNING] Could not determine receiver for message: {msg}")

                            broadcast_message(msg, client_socket, db_connection)
                        else:
                            broadcast_message(msg, client_socket, db_connection)
            except UnicodeDecodeError:
                # Это бинарные аудиоданные
                client_connection = clients.get(client_socket)
                if client_connection:
                    if client_connection.is_in_group_call:
                        # групповой звонок
                        print(f"[GROUP AUDIO] Processing group audio from {client_connection.username}")
                        forward_group_audio_data(data, client_socket)
                    elif client_connection.is_in_call:
                        # Личный звонок
                        forward_audio_data(data, client_socket)

        except Exception as e:
            print(f"[ERROR] {e}")
            break

    if client_socket in clients:
        client_data = clients[client_socket]
        username = client_data.username if isinstance(client_data, ClientConnection) else client_data
        del clients[client_socket]

        if username and db_connection:
            try:
                cursor = db_connection.cursor()
                cursor.execute(
                    """
                    SELECT 
                        CASE 
                            WHEN user1 = %s THEN user2 
                            ELSE user1 
                        END as friend
                    FROM friends 
                    WHERE user1 = %s OR user2 = %s
                    """,
                    (username, username, username)
                )
                friends = [friend[0] for friend in cursor.fetchall()]
                cursor.close()

                for sock, client_data in clients.items():
                    client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
                    if client_name in friends:
                        try:
                            print(f"[SYSTEM] Sent leave notification to friend {client_name}")
                        except Exception as e:
                            print(f"[ERROR] Failed to send leave notification to {client_name}: {e}")
            except Exception as e:
                print(f"[ERROR] Failed to get friends for leave notification: {e}")

        end_user_calls(username, db_connection)

    print(f"[DISCONNECT] {addr} disconnected.")
    if client_socket in clients:
        client_data = clients[client_socket]
        username = client_data.username if isinstance(client_data, ClientConnection) else client_data

        # Обрабатываем отключение
        handle_client_disconnect(client_socket, username, db_connection)

        del clients[client_socket]
        end_user_calls(username, db_connection)
    client_socket.close()


def handle_client_disconnect(client_socket, username, db_connection):
    """Обрабатывает отключение клиента"""
    if username:
        # Устанавливаем статус "не в сети"
        user_status[username] = "offline"

        # Уведомляем друзей
        notify_friends_status_change(username, "offline", db_connection)

        print(f"[DISCONNECT] {username} went offline")

def handle_status_online(message, client_socket, db_connection):
    """Обрабатывает установку статуса 'в сети'"""
    try:
        # Формат: STATUS_ONLINE:username
        parts = message.split(":", 1)
        if len(parts) < 2:
            return

        username = parts[1]
        user_status[username] = "online"

        # Регистрируем пользователя в clients если еще не зарегистрирован
        if client_socket not in clients:
            client_connection = ClientConnection(client_socket, None, username)
            clients[client_socket] = client_connection
        else:
            clients[client_socket].username = username

        print(f"[STATUS] {username} is now online")

        # Уведомляем друзей о смене статуса
        notify_friends_status_change(username, "online", db_connection)

    except Exception as e:
        print(f"[STATUS ERROR] Error handling status online: {e}")


def handle_status_offline(message, client_socket, db_connection):
    """Обрабатывает установку статуса 'не в сети'"""
    try:
        # Формат: STATUS_OFFLINE:username
        parts = message.split(":", 1)
        if len(parts) < 2:
            return

        username = parts[1]
        user_status[username] = "offline"

        print(f"[STATUS] {username} is now offline")

        # Уведомляем друзей о смене статуса
        notify_friends_status_change(username, "offline", db_connection)

    except Exception as e:
        print(f"[STATUS ERROR] Error handling status offline: {e}")


def handle_status_request(message, client_socket, db_connection):
    """Обрабатывает запрос статуса пользователя"""
    try:
        # Формат: STATUS_REQUEST:requester:target_username
        parts = message.split(":", 2)
        if len(parts) < 3:
            return

        requester = parts[1]
        target_username = parts[2]

        # Проверяем, являются ли пользователи друзьями
        cursor = db_connection.cursor()
        cursor.execute(
            """
            SELECT 1 FROM friends 
            WHERE (user1 = %s AND user2 = %s) OR (user1 = %s AND user2 = %s)
            """,
            (requester, target_username, target_username, requester)
        )
        are_friends = cursor.fetchone() is not None
        cursor.close()

        if not are_friends:
            print(f"[STATUS] Blocked status request from {requester} for non-friend {target_username}")
            return

        # Получаем статус пользователя
        status = user_status.get(target_username, "offline")

        # Отправляем ответ
        response = f"STATUS_RESPONSE:{target_username}:{status}"
        client_socket.send(f"{response}\n".encode('utf-8'))

        print(f"[STATUS] Sent status of {target_username} ({status}) to {requester}")

    except Exception as e:
        print(f"[STATUS ERROR] Error handling status request: {e}")


def notify_friends_status_change(username, status, db_connection):
    """Уведомляет друзей об изменении статуса пользователя"""
    try:
        # Получаем список друзей
        cursor = db_connection.cursor()
        cursor.execute(
            """
            SELECT 
                CASE 
                    WHEN user1 = %s THEN user2 
                    ELSE user1 
                END as friend
            FROM friends 
            WHERE user1 = %s OR user2 = %s
            """,
            (username, username, username)
        )
        friends = [friend[0] for friend in cursor.fetchall()]
        cursor.close()

        # Отправляем уведомление всем онлайн друзьям
        status_update = f"STATUS_UPDATE:{username}:{status}"

        for friend_username in friends:
            for client_socket, client_data in clients.items():
                if isinstance(client_data, ClientConnection) and client_data.username == friend_username:
                    try:
                        client_socket.send(f"{status_update}\n".encode('utf-8'))
                        print(f"[STATUS] Notified {friend_username} about {username}'s status change to {status}")
                    except Exception as e:
                        print(f"[STATUS ERROR] Failed to notify {friend_username}: {e}")
                    break

    except Exception as e:
        print(f"[STATUS ERROR] Error notifying friends: {e}")

def handle_group_screen_data_start(message, sender_socket, db_connection):
    """обработка начала передачи группового кадра"""
    try:
        # Формат: GROUP_SCREEN_DATA_START:sender:group_id:frame_id:chunks_count
        parts = message.split(":", 4)
        if len(parts) >= 5:
            sender = parts[1]
            group_id = int(parts[2])
            frame_id = parts[3]
            chunks_count = int(parts[4])

            print(f"[GROUP SCREEN DATA] Start from {sender} for group {group_id}, frame {frame_id}, {chunks_count} chunks")

            # Находим всех участников группы из БД
            cursor = db_connection.cursor()
            cursor.execute(
                "SELECT username FROM group_members WHERE group_id = %s AND username != %s",
                (group_id, sender)
            )
            group_members = [row[0] for row in cursor.fetchall()]
            cursor.close()

            print(f"[GROUP SCREEN DATA] Found {len(group_members)} group members: {group_members}")

            # Пересылаем всем участникам группы кроме отправителя
            forwarded_count = 0
            for member_username in group_members:
                # Ищем клиента среди основных соединений
                for client_socket, client_data in clients.items():
                    if (hasattr(client_data, 'username') and
                        client_data.username == member_username):
                        # Проверяем наличие screen_socket
                        if (hasattr(client_data, 'screen_socket') and
                            client_data.screen_socket):
                            try:
                                client_data.screen_socket.send(f"{message}\n".encode('utf-8'))
                                forwarded_count += 1
                                print(f"[GROUP SCREEN DATA] ✓ Forwarded start to {member_username}")
                            except Exception as e:
                                print(f"[GROUP SCREEN DATA ERROR] Failed to send to {member_username}: {e}")
                        else:
                            print(f"[GROUP SCREEN DATA] No screen socket for {member_username}")
                        break
                else:
                    print(f"[GROUP SCREEN DATA] Member {member_username} not found online")

            print(f"[GROUP SCREEN DATA] Forwarded start to {forwarded_count}/{len(group_members)} participants")

    except Exception as e:
        print(f"[GROUP SCREEN ERROR] Error handling data start: {e}")
        import traceback
        traceback.print_exc()


def handle_group_screen_data_chunk(message, sender_socket, db_connection):
    """обработка части группового кадра"""
    try:
        # Формат: GROUP_SCREEN_DATA_CHUNK:sender:group_id:frame_id:chunk_id:chunk_data
        parts = message.split(":", 5)
        if len(parts) >= 6:
            sender = parts[1]
            group_id = int(parts[2])
            frame_id = parts[3]
            chunk_id = int(parts[4])

            # Находим всех участников группы из БД
            cursor = db_connection.cursor()
            cursor.execute(
                "SELECT username FROM group_members WHERE group_id = %s AND username != %s",
                (group_id, sender)
            )
            group_members = [row[0] for row in cursor.fetchall()]
            cursor.close()

            # Пересылаем всем участникам группы кроме отправителя
            forwarded_count = 0
            for member_username in group_members:
                for client_socket, client_data in clients.items():
                    if (hasattr(client_data, 'username') and
                        client_data.username == member_username and
                        hasattr(client_data, 'screen_socket') and
                        client_data.screen_socket):
                        try:
                            client_data.screen_socket.send(f"{message}\n".encode('utf-8'))
                            forwarded_count += 1
                            # Логируем только каждый 10-й chunk чтобы не засорять логи
                            if int(chunk_id) % 10 == 0:
                                print(f"[GROUP SCREEN DATA] ✓ Forwarded chunk {chunk_id} to {member_username}")
                        except Exception as e:
                            print(f"[GROUP SCREEN DATA ERROR] Failed to send chunk to {member_username}: {e}")
                        break

            # Логируем только для первого и последнего chunk
            if chunk_id == "0" or forwarded_count == 0:
                print(f"[GROUP SCREEN DATA] Forwarded chunk {chunk_id} to {forwarded_count} participants")

    except Exception as e:
        print(f"[GROUP SCREEN ERROR] Error handling data chunk: {e}")


def handle_group_screen_data_end(message, sender_socket, db_connection):
    """обработка завершения передачи группового кадра"""
    try:
        # Формат: GROUP_SCREEN_DATA_END:sender:group_id:frame_id
        parts = message.split(":", 3)
        if len(parts) >= 4:
            sender = parts[1]
            group_id = int(parts[2])
            frame_id = parts[3]

            print(f"[GROUP SCREEN DATA] End from {sender} for group {group_id}, frame {frame_id}")

            # Находим всех участников группы из БД
            cursor = db_connection.cursor()
            cursor.execute(
                "SELECT username FROM group_members WHERE group_id = %s AND username != %s",
                (group_id, sender)
            )
            group_members = [row[0] for row in cursor.fetchall()]
            cursor.close()

            # Пересылаем всем участникам группы кроме отправителя
            forwarded_count = 0
            for member_username in group_members:
                for client_socket, client_data in clients.items():
                    if (hasattr(client_data, 'username') and
                        client_data.username == member_username and
                        hasattr(client_data, 'screen_socket') and
                        client_data.screen_socket):
                        try:
                            client_data.screen_socket.send(f"{message}\n".encode('utf-8'))
                            forwarded_count += 1
                            print(f"[GROUP SCREEN DATA] ✓ Forwarded end to {member_username}")
                        except Exception as e:
                            print(f"[GROUP SCREEN DATA ERROR] Failed to send end to {member_username}: {e}")
                        break

            print(f"[GROUP SCREEN DATA] Forwarded end to {forwarded_count} participants")

    except Exception as e:
        print(f"[GROUP SCREEN ERROR] Error handling data end: {e}")

def handle_direct_message(message, sender_socket, db_connection):
    """Обрабатывает личные сообщения с явным указанием получателя"""
    try:
        # Формат: DIRECT_MESSAGE:sender:receiver:content
        parts = message.split(":", 3)
        if len(parts) < 4:
            print(f"[ERROR] Invalid direct message format: {message}")
            return

        sender = parts[1]
        receiver = parts[2]
        content = parts[3]

        print(f"[DIRECT] Message from {sender} to {receiver}: {content}")

        # Проверяем, является ли отправитель владельцем сокета
        if sender_socket in clients:
            client_data = clients[sender_socket]
            socket_username = client_data.username if isinstance(client_data, ClientConnection) else client_data

            if socket_username != sender:
                print(f"[SECURITY] Username mismatch: {socket_username} != {sender}")
                return

            # Проверяем, являются ли пользователи друзьями
            cursor = db_connection.cursor()
            cursor.execute(
                """
                SELECT 1 FROM friends 
                WHERE (user1 = %s AND user2 = %s) OR (user1 = %s AND user2 = %s)
                """,
                (sender, receiver, receiver, sender)
            )
            are_friends = cursor.fetchone() is not None
            cursor.close()

            if not are_friends:
                print(f"[FILTER] Blocked direct message from {sender} to non-friend {receiver}")
                return

            # Сохраняем сообщение в базе данных
            save_message(db_connection, sender, receiver, content)

            # Находим сокет получателя и отправляем сообщение
            recipient_socket = None
            for sock, client_data in clients.items():
                client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
                if client_name == receiver:
                    recipient_socket = sock
                    break

            if recipient_socket:
                # Отправляем сообщение в формате, который будет обработан как личное сообщение
                formatted_message = f"{sender}: {content}\n"
                recipient_socket.send(formatted_message.encode('utf-8'))
                print(f"[DIRECT] Sent message to {receiver}")
            else:
                print(f"[DIRECT] Recipient {receiver} is offline, message saved to database")

    except Exception as e:
        print(f"[ERROR] Error handling direct message: {e}")
        if 'cursor' in locals():
            db_connection.rollback()
            cursor.close()

def handle_group_exclusion(message, sender_socket, db_connection):
    """Обрабатывает уведомления об исключении участника из группы"""
    try:
        # Формат: GROUP_EXCLUSION:excluded_username:group_name:group_id
        parts = message.split(":", 3)
        if len(parts) < 4:
            print(f"[ERROR] Invalid group exclusion format: {message}")
            return

        excluded_username = parts[1]
        group_name = parts[2]
        group_id = parts[3]

        print(f"[GROUP EXCLUSION] User {excluded_username} excluded from group {group_name}")

        # Находим исключенного пользователя среди подключенных клиентов
        excluded_client_socket = None
        for client_socket, client_data in clients.items():
            if isinstance(client_data, ClientConnection) and client_data.username == excluded_username:
                excluded_client_socket = client_socket
                break

        # Если исключенный пользователь онлайн, отправляем ему уведомление
        if excluded_client_socket:
            try:
                exclusion_notification = f"GROUP_EXCLUDED:{group_name}:{group_id}\n"
                excluded_client_socket.send(exclusion_notification.encode('utf-8'))
                print(f"[GROUP EXCLUSION] Sent exclusion notification to {excluded_username}")
            except Exception as e:
                print(f"[ERROR] Failed to send exclusion notification to {excluded_username}: {e}")

    except Exception as e:
        print(f"[ERROR] Error handling group exclusion: {e}")

def handle_edit_message(message, sender_socket, db_connection):
    """Обрабатывает команду редактирования сообщения"""
    try:
        # Формат: EDIT_MESSAGE:<sender>:<receiver>:<new_content>:<message_id>
        parts = message.split(":", 4)
        if len(parts) < 4:
            print(f"[ERROR] Invalid edit message format: {message}")
            return

        command = parts[0]  # EDIT_MESSAGE
        sender = parts[1]
        receiver = parts[2]
        new_content = parts[3]
        message_id = parts[4] if len(parts) > 4 else None

        print(f"[EDIT] User {sender} is editing a message for {receiver}: {new_content}")

        # Проверяем, является ли отправитель владельцем сообщения
        if db_connection and message_id:
            try:
                cursor = db_connection.cursor()

                # Проверяем наличие колонки edited в таблице messages
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'messages' AND column_name = 'edited'
                    )
                """)
                has_edited_column = cursor.fetchone()[0]

                if not has_edited_column:
                    # Добавляем колонку edited
                    cursor.execute("ALTER TABLE messages ADD COLUMN edited BOOLEAN DEFAULT FALSE")
                    db_connection.commit()
                    print("[DATABASE] Added 'edited' column to messages table")

                # Обновляем сообщение в базе данных
                cursor.execute(
                    """
                    UPDATE messages 
                    SET content = %s, edited = TRUE 
                    WHERE id = %s AND sender = %s
                    RETURNING id
                    """,
                    (new_content, message_id, sender)
                )
                updated_id = cursor.fetchone()
                db_connection.commit()

                if updated_id:
                    print(f"[DATABASE] Updated message {message_id} with content: {new_content}")

                    # Отправляем уведомление получателю о редактировании сообщения
                    notification = f"Система: Пользователь {sender} отредактировал сообщение\n"

                    # Находим сокет получателя
                    for sock, client_data in clients.items():
                        client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
                        if client_name == receiver:
                            try:
                                sock.send(notification.encode('utf-8'))
                                print(f"[NOTIFICATION] Sent edit notification to {receiver}")
                            except Exception as e:
                                print(f"[ERROR] Failed to send edit notification to {receiver}: {e}")
                            break
                else:
                    print(f"[WARNING] No message updated. Message ID {message_id} not found or not owned by {sender}")

                cursor.close()
            except Exception as e:
                print(f"[ERROR] Failed to update message: {e}")
                db_connection.rollback()
        else:
            print(f"[WARNING] No message ID provided for editing")
    except Exception as e:
        print(f"[ERROR] Error handling edit message: {e}")


def handle_delete_message(message, sender_socket, db_connection):
    """Обрабатывает команду удаления сообщения"""
    try:
        # Формат: DELETE_MESSAGE:<sender>:<receiver>:<message_id>
        parts = message.split(":", 3)
        if len(parts) < 3:
            print(f"[ERROR] Invalid delete message format: {message}")
            return

        command = parts[0]  # DELETE_MESSAGE
        sender = parts[1]
        receiver = parts[2]
        message_id = parts[3] if len(parts) > 3 else None

        print(f"[DELETE] User {sender} is deleting a message for {receiver}")

        # Проверяем, является ли отправитель владельцем сообщения
        if db_connection and message_id:
            try:
                cursor = db_connection.cursor()

                # Проверяем наличие колонки deleted в таблице messages
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'messages' AND column_name = 'deleted'
                    )
                """)
                has_deleted_column = cursor.fetchone()[0]

                if not has_deleted_column:
                    # Добавляем колонку deleted
                    cursor.execute("ALTER TABLE messages ADD COLUMN deleted BOOLEAN DEFAULT FALSE")
                    db_connection.commit()
                    print("[DATABASE] Added 'deleted' column to messages table")

                # Обновляем сообщение в базе данных
                cursor.execute(
                    """
                    UPDATE messages 
                    SET content = 'Сообщение удалено', deleted = TRUE 
                    WHERE id = %s AND sender = %s
                    RETURNING id
                    """,
                    (message_id, sender)
                )
                updated_id = cursor.fetchone()
                db_connection.commit()

                if updated_id:
                    print(f"[DATABASE] Marked message {message_id} as deleted")

                    # Отправляем уведомление получателю об удалении сообщения
                    notification = f"Система: Пользователь {sender} удалил сообщение\n"

                    # Находим сокет получателя
                    for sock, client_data in clients.items():
                        client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
                        if client_name == receiver:
                            try:
                                sock.send(notification.encode('utf-8'))
                                print(f"[NOTIFICATION] Sent delete notification to {receiver}")
                            except Exception as e:
                                print(f"[ERROR] Failed to send delete notification to {receiver}: {e}")
                            break
                else:
                    print(f"[WARNING] No message deleted. Message ID {message_id} not found or not owned by {sender}")

                cursor.close()
            except Exception as e:
                print(f"[ERROR] Failed to delete message: {e}")
                db_connection.rollback()
        else:
            print(f"[WARNING] No message ID provided for deletion")
    except Exception as e:
        print(f"[ERROR] Error handling delete message: {e}")


def handle_file_transfer(message, sender_socket, db_connection):
    """Обрабатывает сообщения передачи файлов"""
    try:
        parts = message.split(":", 4)
        if len(parts) < 5:
            print(f"[ОШИБКА] Неверный формат передачи файла: {message}")
            return
        action = parts[1]
        # Проверяем, что формат сообщения корректный
        if action not in ["START", "CHUNK", "END"]:
            print(f"[ОШИБКА] Неизвестное действие в передаче файла: {action}")
            return

        sender = parts[2]
        recipient = parts[3]

        # Ищем сокет получателя
        recipient_socket = None
        for sock, name in clients.items():
            if name.lower() == recipient.lower():
                recipient_socket = sock
                break

        if not recipient_socket:
            print(f"[ОШИБКА] Получатель {recipient} не найден для передачи файла")
            # Уведомляем отправителя, что получатель недоступен
            return

        # Пересылаем сообщение получателю без изменений
        try:
            # Добавляем \n в конец сообщения для правильного разделения
            if not message.endswith('\n'):
                message += '\n'
            recipient_socket.send(message.encode('utf-8'))

            # Логируем действие
            if action == "START":
                file_info = parts[4].split(":", 1)
                file_name = file_info[0]
                file_size = file_info[1] if len(file_info) > 1 else "unknown"
                print(f"[ФАЙЛ] Начата передача файла {file_name} ({file_size} байт) от {sender} к {recipient}")
            elif action == "END":
                file_name = parts[4]
                print(f"[ФАЙЛ] Завершена передача файла {file_name} от {sender} к {recipient}")

            # Логируем начало/конец передачи файла в базе данных
            if action in ["START", "END"] and db_connection:
                try:
                    cursor = db_connection.cursor()

                    if action == "START":
                        file_info = parts[4].split(":", 1)
                        file_name = file_info[0]

                        # Сохраняем как сообщение
                        cursor.execute(
                            "INSERT INTO messages (sender, receiver, content) VALUES (%s, %s, %s)",
                            (sender, recipient)
                        )

                    elif action == "END":
                        file_name = parts[4]

                        # Определяем тип файла по расширению
                        file_extension = os.path.splitext(file_name)[1].lower()
                        is_image = file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']

                        # Добавляем сообщение о завершении
                        if is_image:
                            content = f"[Вложение: {file_name}]"
                        else:
                            content = f"[Файл получен: {file_name}]"

                        cursor.execute(
                            "INSERT INTO messages (sender, receiver, content) VALUES (%s, %s, %s)",
                            (sender, recipient, content)
                        )

                    db_connection.commit()
                except Exception as e:
                    print(f"[ОШИБКА] Не удалось записать передачу файла: {e}")
                    db_connection.rollback()
                finally:
                    cursor.close()

        except Exception as e:
            print(f"[ОШИБКА] Не удалось переслать сообщение о передаче файла: {e}")
            # Если это начало передачи, уведомляем отправителя
            if action == "START":
                sender_socket.send(
                    f"Система: Ошибка отправки файла пользователю {recipient}: {str(e)}\n".encode('utf-8'))

    except Exception as e:
        print(f"[ОШИБКА] Ошибка обработки передачи файла: {e}")


def handle_call_signal(message, sender_socket, db_connection):
    """Обработка сигналов звонка"""
    try:
        # Формат: CALL_SIGNAL:<type>:<sender>:<recipient>:<timestamp>:<duration>
        signal_data = message[12:]  # Убираем префикс "CALL_SIGNAL:"
        parts = signal_data.split(':')
        if len(parts) < 4:
            print(f"[ERROR] Invalid call signal format: {signal_data}")
            return

        signal_type = parts[0]
        sender = parts[1]
        recipient = parts[2]
        timestamp = float(parts[3])
        duration = int(parts[4]) if len(parts) > 4 else 0

        print(f"[CALL SIGNAL] {signal_type} from {sender} to {recipient}")

        # Обновляем информацию о звонке в соединениях
        sender_connection = None
        recipient_connection = None

        for sock, client_data in clients.items():
            if isinstance(client_data, ClientConnection):
                if client_data.username == sender:
                    sender_connection = client_data
                elif client_data.username == recipient:
                    recipient_connection = client_data

        # Проверяем, являются ли пользователи друзьями для входящих звонков
        if signal_type == "incoming_call":
            try:
                cursor = db_connection.cursor()
                cursor.execute(
                    """
                    SELECT 1 FROM friends 
                    WHERE (user1 = %s AND user2 = %s) OR (user1 = %s AND user2 = %s)
                    """,
                    (sender, recipient, recipient, sender)
                )
                are_friends = cursor.fetchone() is not None
                cursor.close()

                if not are_friends:
                    print(f"[FILTER] Blocked call from {sender} to non-friend {recipient}")
                    sender_socket.send(
                        f"Система: Невозможно позвонить пользователю {recipient}. Вы не в списке друзей.\n".encode(
                            'utf-8'))
                    return
            except Exception as e:
                print(f"[ERROR] Failed to check friendship: {e}")

        # Проверяем, есть ли получатель в списке подключенных клиентов
        recipient_socket = None
        recipient_found = False

        for sock, client_data in clients.items():
            client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
            if client_name.lower() == recipient.lower():
                recipient_socket = sock
                recipient = client_name
                recipient_found = True
                break

        if not recipient_found and signal_type == "incoming_call":
            print(f"[ERROR] Recipient {recipient} not found or not connected")

            try:
                cursor = db_connection.cursor()
                cursor.execute("SELECT 1 FROM users WHERE username = %s", (recipient,))
                user_exists = cursor.fetchone() is not None

                if user_exists:
                    # Создаем таблицу call_logs если не существует
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'call_logs'
                        )
                    """)
                    call_logs_exists = cursor.fetchone()[0]

                    if not call_logs_exists:
                        cursor.execute("""
                            CREATE TABLE call_logs (
                                id SERIAL PRIMARY KEY,
                                caller VARCHAR(50) REFERENCES users(username),
                                recipient VARCHAR(50) REFERENCES users(username),
                                start_time TIMESTAMP,
                                end_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                duration INTEGER NOT NULL,
                                status VARCHAR(20) DEFAULT 'ended',
                                timestamp BIGINT,
                                notification_seen BOOLEAN DEFAULT FALSE
                            )
                        """)
                        db_connection.commit()

                    # Регистрируем пропущенный звонок
                    cursor.execute(
                        """
                        INSERT INTO call_logs 
                        (caller, recipient, start_time, end_time, duration, status, timestamp, notification_seen) 
                        VALUES (%s, %s, to_timestamp(%s), CURRENT_TIMESTAMP, 0, 'missed', %s, FALSE)
                        """,
                        (sender, recipient, timestamp, int(timestamp))
                    )
                    db_connection.commit()
                    print(f"[CALL] Registered missed call from {sender} to {recipient}")

                    sender_socket.send(f"Система: Пользователь {recipient} не в сети.\n".encode('utf-8'))
                else:
                    sender_socket.send(f"Система: Пользователь {recipient} не найден.\n".encode('utf-8'))

                # Автоматически завершаем звонок
                end_time = time.time()
                end_signal = f"CALL_SIGNAL:call_ended:{sender}:{recipient}:{end_time}:0\n"
                sender_socket.send(end_signal.encode('utf-8'))

                cursor.close()
            except Exception as e:
                print(f"[ERROR] Failed to check user existence: {e}")
                sender_socket.send(f"Система: Ошибка при поиске пользователя {recipient}.\n".encode('utf-8'))

            return

        # Обрабатываем различные типы сигналов
        if signal_type == "incoming_call":
            call_id = f"{sender}_{recipient}_{timestamp}"
            calls[call_id] = {
                "caller": sender,
                "recipient": recipient,
                "start_time": timestamp,
                "status": "ringing"
            }

            # Устанавливаем информацию о звонке в соединениях
            if sender_connection:
                sender_connection.is_in_call = True
                sender_connection.call_partner = recipient
            if recipient_connection:
                recipient_connection.is_in_call = True
                recipient_connection.call_partner = sender

            if recipient_socket:
                try:
                    recipient_socket.send(f"{message}\n".encode('utf-8'))
                    print(f"[CALL] Sent incoming call signal to {recipient}")
                except Exception as e:
                    print(f"[ERROR] Failed to send call signal: {e}")

        elif signal_type == "call_accepted":
            for call_id, call_info in calls.items():
                if call_info["caller"] == recipient and call_info["recipient"] == sender:
                    call_info["status"] = "active"
                    call_info["accept_time"] = timestamp
                    break

            caller_socket = None
            for sock, client_data in clients.items():
                client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
                if client_name.lower() == recipient.lower():
                    caller_socket = sock
                    break

            if caller_socket:
                try:
                    caller_socket.send(f"{message}\n".encode('utf-8'))
                    print(f"[CALL] Sent call accepted signal to {recipient}")
                except Exception as e:
                    print(f"[ERROR] Failed to send call accepted signal: {e}")

        elif signal_type == "call_rejected":
            for call_id, call_info in calls.items():
                if call_info["caller"] == recipient and call_info["recipient"] == sender:
                    call_info["status"] = "rejected"
                    break

            # Сбрасываем информацию о звонке в соединениях
            if sender_connection:
                sender_connection.is_in_call = False
                sender_connection.call_partner = None
            if recipient_connection:
                recipient_connection.is_in_call = False
                recipient_connection.call_partner = None

            caller_socket = None
            for sock, client_data in clients.items():
                client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
                if client_name.lower() == recipient.lower():
                    caller_socket = sock
                    break

            if caller_socket:
                try:
                    caller_socket.send(f"{message}\n".encode('utf-8'))
                    print(f"[CALL] Sent call rejected signal to {recipient}")
                except Exception as e:
                    print(f"[ERROR] Failed to send call rejected signal: {e}")

        elif signal_type == "call_ended":
            active_call = None
            active_call_id = None

            for call_id, call_info in calls.items():
                if (call_info["caller"].lower() == sender.lower() and call_info[
                    "recipient"].lower() == recipient.lower()) or \
                        (call_info["caller"].lower() == recipient.lower() and call_info[
                            "recipient"].lower() == sender.lower()):
                    if call_info["status"] == "active" or call_info["status"] == "ringing":
                        active_call = call_info
                        active_call_id = call_id
                        break

            # Сбрасываем информацию о звонке в соединениях
            if sender_connection:
                sender_connection.is_in_call = False
                sender_connection.call_partner = None
            if recipient_connection:
                recipient_connection.is_in_call = False
                recipient_connection.call_partner = None

            if active_call:
                if duration == 0 and active_call["status"] == "active" and "accept_time" in active_call:
                    duration = int(timestamp - active_call["accept_time"])

                active_call["status"] = "ended"
                active_call["end_time"] = timestamp
                active_call["duration"] = duration

                caller_socket = None
                recipient_socket = None
                for sock, client_data in clients.items():
                    client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
                    if client_name.lower() == active_call["caller"].lower():
                        caller_socket = sock
                    elif client_name.lower() == active_call["recipient"].lower():
                        recipient_socket = sock

                signal_message = f"CALL_SIGNAL:call_ended:{sender}:{recipient}:{timestamp}:{duration}\n"

                minutes = duration // 60
                seconds = duration % 60
                duration_str = f"{minutes:02d}:{seconds:02d}"
                current_time = datetime.datetime.now().strftime("%H:%M")
                caller_system_message = f"Система: Звонок с {active_call['recipient']} завершен в {current_time}. Длительность: {duration_str}\n"
                recipient_system_message = f"Система: Звонок с {active_call['caller']} завершен в {current_time}. Длительность: {duration_str}\n"

                # Сохраняем сообщения в базу данных
                try:
                    cursor = db_connection.cursor()
                    call_end_message = f"Звонок с {active_call['recipient']} завершен в {current_time}. Длительность: {duration_str}"
                    recipient_call_end_message = f"Звонок с {active_call['caller']} завершен в {current_time}. Длительность: {duration_str}"

                    cursor.execute(
                        "INSERT INTO messages (sender, receiver, content, read) VALUES (%s, %s, %s, %s)",
                        ("Система", active_call['caller'], call_end_message, True)
                    )

                    cursor.execute(
                        "INSERT INTO messages (sender, receiver, content, read) VALUES (%s, %s, %s, %s)",
                        ("Система", active_call['recipient'], recipient_call_end_message, True)
                    )

                    # Проверяем существование таблицы call_logs
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'call_logs'
                        )
                    """)
                    call_logs_exists = cursor.fetchone()[0]

                    if not call_logs_exists:
                        cursor.execute("""
                            CREATE TABLE call_logs (
                                id SERIAL PRIMARY KEY,
                                caller VARCHAR(50) REFERENCES users(username),
                                recipient VARCHAR(50) REFERENCES users(username),
                                start_time TIMESTAMP,
                                end_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                duration INTEGER NOT NULL,
                                status VARCHAR(20) DEFAULT 'ended',
                                timestamp BIGINT,
                                notification_seen BOOLEAN DEFAULT FALSE
                            )
                        """)
                        db_connection.commit()

                    cursor.execute(
                        """
                        INSERT INTO call_logs (caller, recipient, start_time, end_time, duration, status, timestamp, notification_seen) 
                        VALUES (%s, %s, to_timestamp(%s), CURRENT_TIMESTAMP, %s, 'ended', %s, TRUE)
                        """,
                        (active_call['caller'], active_call['recipient'],
                         active_call.get('accept_time', active_call['start_time']),
                         duration, int(timestamp))
                    )

                    db_connection.commit()
                    print(
                        f"[DATABASE] Saved call end messages for {active_call['caller']} and {active_call['recipient']}")
                except Exception as e:
                    print(f"[ERROR] Failed to save call end messages: {e}")
                    db_connection.rollback()
                finally:
                    cursor.close()

                # Отправляем сигнал и системное сообщение
                if caller_socket:
                    try:
                        caller_socket.send(signal_message.encode('utf-8'))
                        caller_socket.send(caller_system_message.encode('utf-8'))
                        print(f"[CALL] Sent call ended signal and system message to {active_call['caller']}")
                    except Exception as e:
                        print(f"[ERROR] Failed to send to caller: {e}")

                if recipient_socket and recipient_socket != caller_socket:
                    try:
                        recipient_socket.send(signal_message.encode('utf-8'))
                        recipient_socket.send(recipient_system_message.encode('utf-8'))
                        print(f"[CALL] Sent call ended signal and system message to {active_call['recipient']}")
                    except Exception as e:
                        print(f"[ERROR] Failed to send to recipient: {e}")

                if active_call_id in calls:
                    del calls[active_call_id]

    except Exception as e:
        print(f"Ошибка обработки сигнала звонка: {e}")


def forward_audio_data(data, sender_socket):
    """Пересылает аудиоданные получателю звонка"""
    try:
        sender_connection = clients.get(sender_socket)
        if not sender_connection or not isinstance(sender_connection, ClientConnection):
            return

        sender = sender_connection.username
        if not sender or not sender_connection.is_in_call:
            return

        recipient = sender_connection.call_partner
        if not recipient:
            return

        recipient_socket = None
        for sock, client_data in clients.items():
            if isinstance(client_data, ClientConnection) and client_data.username.lower() == recipient.lower():
                recipient_socket = sock
                break

        if recipient_socket and recipient_socket != sender_socket:
            try:
                recipient_socket.sendall(data)
            except Exception as e:
                print(f"[ERROR] Failed to forward audio data: {e}")
    except Exception as e:
        print(f"Ошибка пересылки аудиоданных: {e}")


def end_user_calls(username, db_connection=None):
    """Завершает все активные звонки пользователя при отключении"""
    for call_id, call_info in list(calls.items()):
        if call_info["caller"].lower() == username.lower() or call_info["recipient"].lower() == username.lower():
            if call_info["status"] == "active" or call_info["status"] == "ringing":
                other_user = call_info["recipient"] if call_info["caller"].lower() == username.lower() else call_info[
                    "caller"]
                end_time = time.time()
                duration = 0
                if call_info["status"] == "active" and "accept_time" in call_info:
                    duration = int(end_time - call_info["accept_time"])

                signal = f"CALL_SIGNAL:call_ended:{username}:{other_user}:{end_time}:{duration}\n"
                minutes = duration // 60
                seconds = duration % 60
                duration_str = f"{minutes:02d}:{seconds:02d}"
                current_time = datetime.datetime.now().strftime("%H:%M")
                system_message = f"Система: Звонок с {username} завершен в {current_time}. Длительность: {duration_str}\n"

                for sock, client_data in clients.items():
                    client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
                    if client_name.lower() == other_user.lower():
                        try:
                            sock.send(signal.encode('utf-8'))
                            sock.send(system_message.encode('utf-8'))
                            print(f"[CALL] Sent call ended signal and system message to {other_user}")
                        except Exception as e:
                            print(f"[ERROR] Failed to send call ended signal: {e}")
                        break

                if db_connection:
                    try:
                        cursor = db_connection.cursor()
                        system_message_content = f"Звонок с {username} завершен в {current_time}. Длительность: {duration_str}"

                        cursor.execute(
                            "INSERT INTO messages (sender, receiver, content) VALUES (%s, %s, %s)",
                            ("Система", other_user, system_message_content)
                        )

                        cursor.execute("""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_name = 'call_logs'
                            )
                        """)
                        call_logs_exists = cursor.fetchone()[0]

                        if call_logs_exists:
                            cursor.execute(
                                """
                                INSERT INTO call_logs (caller, recipient, start_time, end_time, duration, status, timestamp) 
                                VALUES (%s, %s, to_timestamp(%s), CURRENT_TIMESTAMP, %s, 'ended', %s)
                                """,
                                (username if call_info["caller"].lower() == username.lower() else other_user,
                                 other_user if call_info["caller"].lower() == username.lower() else username,
                                 call_info.get('accept_time', call_info['start_time']),
                                 duration, int(end_time))
                            )

                        db_connection.commit()
                        print(f"[DATABASE] Saved call end message for {other_user}")
                    except Exception as e:
                        print(f"[ERROR] Failed to save call end message: {e}")
                        db_connection.rollback()
                    finally:
                        cursor.close()

                call_info["status"] = "ended"
                call_info["end_time"] = end_time
                call_info["duration"] = duration
                del calls[call_id]


def broadcast_message(message, sender_socket, db_connection):
    try:
        if ":" in message:
            parts = message.split(":", 1)
            sender_name = parts[0].strip()
            content = parts[1].strip()

            # Не отправляем сообщение о начале чата другим пользователям
            if sender_name == "Система" and content.startswith("Чат с "):
                return

            # Убираем обработку сообщений об обновлении аватара
            if sender_name == "Система" and "обновил аватар" in content:
                return

            # Системные сообщения отправляем всем
            if sender_name == "Система":
                for client_socket, client_data in clients.items():
                    if client_socket != sender_socket:
                        try:
                            client_socket.send(f"{message}\n".encode('utf-8'))
                            client_name = client_data.username if isinstance(client_data,
                                                                             ClientConnection) else client_data
                            print(f"[MESSAGE] Sent system message to {client_name}")
                        except Exception as e:
                            print(f"[ERROR] Failed to send message: {e}")
                            client_socket.close()
                return

            # Для обычных сообщений отправляем только конкретному получателю
            if sender_socket in clients:
                sender_data = clients[sender_socket]
                sender_username = sender_data.username if isinstance(sender_data, ClientConnection) else sender_data

                # Ищем получателя в истории сообщений
                receiver = None
                try:
                    cursor = db_connection.cursor()
                    cursor.execute(
                        """
                        SELECT receiver FROM messages 
                        WHERE sender = %s 
                        ORDER BY timestamp DESC 
                        LIMIT 1
                        """,
                        (sender_username,)
                    )
                    last_receiver = cursor.fetchone()
                    if last_receiver:
                        receiver = last_receiver[0]
                    else:
                        cursor.execute(
                            """
                            SELECT sender FROM messages 
                            WHERE receiver = %s 
                            ORDER BY timestamp DESC 
                            LIMIT 1
                            """,
                            (sender_username,)
                        )
                        last_sender = cursor.fetchone()
                        if last_sender:
                            receiver = last_sender[0]
                    cursor.close()
                except Exception as e:
                    print(f"[ERROR] Failed to find receiver from history: {e}")

                if receiver:
                    # Находим сокет получателя
                    for client_socket, client_data in clients.items():
                        client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
                        if client_name == receiver:
                            try:
                                # Проверяем, являются ли пользователи друзьями
                                cursor = db_connection.cursor()
                                cursor.execute(
                                    """
                                    SELECT 1 FROM friends 
                                    WHERE (user1 = %s AND user2 = %s) OR (user1 = %s AND user2 = %s)
                                    """,
                                    (sender_username, client_name, client_name, sender_username)
                                )
                                are_friends = cursor.fetchone() is not None
                                cursor.close()

                                if are_friends:
                                    client_socket.send(f"{message}\n".encode('utf-8'))
                                    print(f"[MESSAGE] Sent message from {sender_username} to friend {client_name}")
                                else:
                                    print(
                                        f"[FILTER] Blocked message from {sender_username} to non-friend {client_name}")
                            except Exception as e:
                                print(f"[ERROR] Failed to send message to {client_name}: {e}")
                                client_socket.close()
                            break
        else:
            # Для сообщений без формата "имя: содержание"
            for client in clients:
                if client != sender_socket:
                    try:
                        client.send(f"{message}\n".encode('utf-8'))
                    except Exception as e:
                        print(f"[ERROR] Failed to broadcast message: {e}")
                        client.close()
    except Exception as e:
        print(f"[ERROR] Error in broadcast_message: {e}")

def save_message(connection, sender, receiver, content):
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM users WHERE username = %s", (receiver,))
        user_exists = cursor.fetchone() is not None

        if user_exists:
            # Проверяем наличие колонки read в таблице messages
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'messages' AND column_name = 'read'
                )
            """)
            has_read_column = cursor.fetchone()[0]

            if not has_read_column:
                cursor.execute("""
                    ALTER TABLE messages 
                    ADD COLUMN read BOOLEAN DEFAULT TRUE
                """)
                connection.commit()

            # Проверяем, находится ли получатель в сети
            is_online = False
            for sock, client_data in clients.items():
                client_name = client_data.username if isinstance(client_data, ClientConnection) else client_data
                if client_name.lower() == receiver.lower():
                    is_online = True
                    break

            is_read = is_online and sender != "Система"

            cursor.execute(
                "INSERT INTO messages (sender, receiver, content, read) VALUES (%s, %s, %s, %s)",
                (sender, receiver, content, is_read)
            )
            connection.commit()
            print(f"[DATABASE] Message saved: {sender} -> {receiver}: {content} (read: {is_read})")
        else:
            print(f"Warning: Attempted to save message to non-existent user '{receiver}'")
    except Exception as e:
        print(f"Error saving message: {e}")
        connection.rollback()
    finally:
        cursor.close()


def start_server():
    global db_connection
    try:
        db_connection = pg8000.connect(**DB_CONFIG)
        print("[DATABASE] Connected to PostgreSQL database")

        cursor = db_connection.cursor()

        # Создаем необходимые таблицы
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'users'
            )
        """)
        users_table_exists = cursor.fetchone()[0]

        if not users_table_exists:
            print("[DATABASE] Creating users table")
            cursor.execute("""
                CREATE TABLE users (
                    username VARCHAR(50) PRIMARY KEY,
                    password VARCHAR(100) NOT NULL,
                    email VARCHAR(100)
                )
            """)
            db_connection.commit()

        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'messages'
            )
        """)
        messages_table_exists = cursor.fetchone()[0]

        if not messages_table_exists:
            print("[DATABASE] Creating messages table")
            cursor.execute("""
                CREATE TABLE messages (
                    id SERIAL PRIMARY KEY,
                    sender VARCHAR(50) REFERENCES users(username),
                    receiver VARCHAR(50) REFERENCES users(username),
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db_connection.commit()

        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'friends'
            )
        """)
        friends_table_exists = cursor.fetchone()[0]

        if not friends_table_exists:
            print("[DATABASE] Creating friends table")
            cursor.execute("""
                CREATE TABLE friends (
                    id SERIAL PRIMARY KEY,
                    user1 VARCHAR(50) REFERENCES users(username),
                    user2 VARCHAR(50) REFERENCES users(username),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user1, user2)
                )
            """)
            db_connection.commit()

        # Таблица групп
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'groups'
            )
        """)
        groups_table_exists = cursor.fetchone()[0]

        if not groups_table_exists:
            print("[DATABASE] Creating groups table")
            cursor.execute("""
                CREATE TABLE groups (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    invite_link VARCHAR(50) UNIQUE NOT NULL,
                    avatar_path VARCHAR(255),
                    creator_username VARCHAR(50) REFERENCES users(username),
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db_connection.commit()

        # Таблица участников групп
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'group_members'
            )
        """)
        group_members_table_exists = cursor.fetchone()[0]

        if not group_members_table_exists:
            print("[DATABASE] Creating group_members table")
            cursor.execute("""
                CREATE TABLE group_members (
                    id SERIAL PRIMARY KEY,
                    group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
                    username VARCHAR(50) REFERENCES users(username),
                    role VARCHAR(20) DEFAULT 'member',
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(group_id, username)
                )
            """)
            db_connection.commit()

        # Таблица сообщений групп
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'group_messages'
            )
        """)
        group_messages_table_exists = cursor.fetchone()[0]

        if not group_messages_table_exists:
            print("[DATABASE] Creating group_messages table")
            cursor.execute("""
                CREATE TABLE group_messages (
                    id SERIAL PRIMARY KEY,
                    group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
                    sender VARCHAR(50) REFERENCES users(username),
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    edited BOOLEAN DEFAULT FALSE,
                    deleted BOOLEAN DEFAULT FALSE
                )
            """)
            db_connection.commit()

        cursor.close()
    except Exception as e:
        print(f"[DATABASE ERROR] {e}")
        return

    # Создаем основной сервер для текстового чата и аудио
    main_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    main_server.bind(("127.0.0.1", 5555))
    main_server.listen(5)
    print("[SERVER] Main server is running on 127.0.0.1:5555")

    # Создаем отдельный сервер для демонстрации экрана
    screen_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    screen_server.bind(("127.0.0.1", 5556))
    screen_server.listen(5)
    print("[SERVER] Screen sharing server is running on 127.0.0.1:5556")

    # Создаем отдельный сервер для группового чата
    group_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    group_server.bind(("127.0.0.1", 5557))
    group_server.listen(5)
    print("[SERVER] Group chat server is running on 127.0.0.1:5557")

    # Создаем сервер для групповых звонков
    group_call_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    group_call_server.bind(("127.0.0.1", 5558))
    group_call_server.listen(5)
    print("[SERVER] Group call server is running on 127.0.0.1:5558")

    def accept_main_connections():
        """Принимает основные соединения"""
        while True:
            try:
                client_socket, addr = main_server.accept()
                thread = threading.Thread(target=handle_client, args=(client_socket, addr, db_connection))
                thread.daemon = True
                thread.start()
                print(f"[MAIN] New main connection from {addr}")
            except Exception as e:
                print(f"[ERROR] Error accepting main connection: {e}")


    def accept_screen_connections():
        """Принимает соединения для демонстрации экрана"""
        while True:
            try:
                screen_socket, addr = screen_server.accept()
                thread = threading.Thread(target=handle_screen_sharing_connection,
                                          args=(screen_socket, addr, db_connection))
                thread.daemon = True
                thread.start()
                print(f"[SCREEN] New screen sharing connection from {addr}")
            except Exception as e:
                print(f"[ERROR] Error accepting screen connection: {e}")

    def accept_group_connections():
        """Принимает соединения для группового чата"""
        while True:
            try:
                client_socket, addr = group_server.accept()
                thread = threading.Thread(target=handle_group_client,
                                          args=(client_socket, addr, db_connection))
                thread.daemon = True
                thread.start()
                print(f"[GROUP] New group connection from {addr}")
            except Exception as e:
                print(f"[ERROR] Error accepting group connection: {e}")

    def accept_group_call_connections():
        """Принимает соединения для групповых звонков"""
        while True:
            try:
                client_socket, addr = group_call_server.accept()
                thread = threading.Thread(target=handle_group_call_client,
                                          args=(client_socket, addr, db_connection))
                thread.daemon = True
                thread.start()
                print(f"[GROUP CALL] New group call connection from {addr}")
            except Exception as e:
                print(f"[ERROR] Error accepting group call connection: {e}")

    # Запускаем оба сервера в отдельных потоках
    main_thread = threading.Thread(target=accept_main_connections)
    main_thread.daemon = True
    main_thread.start()

    screen_thread = threading.Thread(target=accept_screen_connections)
    screen_thread.daemon = True
    screen_thread.start()

    #Запускаем сервер группового чата
    group_thread = threading.Thread(target=accept_group_connections)
    group_thread.daemon = True
    group_thread.start()

    # Запускаем сервер групповых звонков в отдельном потоке
    group_call_thread = threading.Thread(target=accept_group_call_connections)
    group_call_thread.daemon = True
    group_call_thread.start()


    try:
        print("[SERVER] Both servers are running. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[SERVER] Servers are shutting down...")
    finally:
        db_connection.close()
        main_server.close()
        screen_server.close()
        group_server.close()

if __name__ == "__main__":
    start_server()