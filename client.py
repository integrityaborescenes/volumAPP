import socket
import threading
import pyaudio
import sys
import datetime
import time
import base64
import os
from PyQt5 import QtCore, QtGui, QtWidgets, Qt
from friend_search import FriendSearchDialog
from notification_dialog import NotificationDialog
from call_dialog import CallDialog, GroupCallDialog
from attachment_dialog import AttachmentDialog
from attachment_preview import AttachmentPreview
from profile_dialog import ProfileDialog
from friends_dialog import FriendsDialog
from inline_search import SearchBar
from screen_sharing_window import ScreenSharingWindow
from group_settings_dialog import GroupSettingsDialog
import struct
import zlib
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication



class ChatClient:
    def __init__(self, host, port):
        # Основное соединение
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.connect((host, port))

        # Отдельное соединение для демонстрации экрана с увеличенными буферами
        self.screen_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.screen_client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)  # 1MB
        self.screen_client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)  # 1MB
        self.screen_client.connect((host, port + 1))

        # Отдельное соединение для группового чата
        self.group_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.group_client.connect((host, port + 2))  # Порт 5557
        self.is_in_group_call = False
        self.current_group_call_id = None
        self.chat_window = None
        # Отдельное соединение для групповых звонков
        self.group_call_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.group_call_client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)
        self.group_call_client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)
        self.group_call_client.connect((host, port + 3))  # Порт 5558

        self.username = None
        self.current_call = None
        self.call_recipient = None

        self.group_screen_sharing = False
        self.group_screen_viewers = set()  # Участники, которые смотрят демонстрацию

        self.p = pyaudio.PyAudio()
        self.stream_input = None
        self.stream_output = None
        self.is_recording = False
        self.is_in_call = False
        self.audio_thread = None
        self.is_mic_muted = False
        self.is_speaker_muted = False

        # Флаги для демонстрации экрана
        self.is_sharing_screen = False
        self.is_receiving_screen = False
        self.screen_thread = None

        self.init_audio_streams()

    def authenticate_group_call_connection(self):
        """Аутентифицирует соединение для групповых звонков"""
        if self.username:
            auth_message = f"GROUP_CALL_AUTH:{self.username}"
            try:
                self.group_call_client.send(f"{auth_message}\n".encode('utf-8'))
                print(f"[GROUP CALL] Authenticated group call connection for {self.username}")
            except Exception as e:
                print(f"[GROUP CALL ERROR] Failed to authenticate: {e}")

    def send_group_screen_control_signal(self, action, group_id):
        """Отправляет сигнал управления групповой демонстрацией экрана"""
        if not group_id:
            return

        signal = f"GROUP_SCREEN_CONTROL:{action}:{group_id}:{self.username}:{time.time()}"
        self.send_message(signal)
        print(f"[GROUP SCREEN] Sent {action} signal for group {group_id}")

    def start_group_screen_sharing(self, group_id):
        """Начинает групповую демонстрацию экрана"""
        self.group_screen_sharing = True
        self.send_group_screen_control_signal("start", group_id)

    def stop_group_screen_sharing(self, group_id):
        """Останавливает групповую демонстрацию экрана"""
        self.group_screen_sharing = False
        self.group_screen_viewers.clear()
        self.send_group_screen_control_signal("stop", group_id)

    def handle_group_screen_signal(self, message, callback):
        """Обрабатывает сигналы групповой демонстрации экрана"""
        try:
            print(f"[GROUP SCREEN] Processing signal: {message}")

            parts = message.split(":", 4)
            if len(parts) < 5:
                print(f"[GROUP SCREEN ERROR] Invalid signal format: {message}")
                return

            action = parts[1]
            group_id = int(parts[2])
            sender = parts[3]
            timestamp = float(parts[4])

            print(f"[GROUP SCREEN] Signal details - action: {action}, group: {group_id}, sender: {sender}")

            #  Проверяем, что это наша текущая группа
            if not hasattr(self, 'chat_window') or not self.chat_window:
                print(f"[GROUP SCREEN] No chat window available")
                return

            if not self.chat_window.current_group or self.chat_window.current_group['id'] != group_id:
                print(f"[GROUP SCREEN] Not our current group")
                return

            # Не обрабатываем собственные сигналы
            if sender == self.username:
                print(f"[GROUP SCREEN] Ignoring own signal")
                return

            # Передаем обработку в ChatWindow
            if callback:
                callback(message)

        except Exception as e:
            print(f"[GROUP SCREEN ERROR] Error handling signal: {e}")
            import traceback
            traceback.print_exc()

    def handle_group_screen_start(self, sender, group_id):
        """Обрабатывает начало групповой демонстрации экрана"""
        try:
            print(f"[GROUP SCREEN] {sender} started screen sharing in group {group_id}")

            # Проверяем, что это текущая группа
            if not self.current_group or self.current_group['id'] != group_id:
                print(f"[GROUP SCREEN] Not current group: {group_id}")
                return

            # Проверяем, что это не мы сами
            if sender == self.username:
                print(f"[GROUP SCREEN] Ignoring own screen sharing")
                return

            # Показываем уведомление в чате
            self.display_message(f"Система: {sender} начал(а) демонстрацию экрана в группе")

            # Создаем окно для просмотра демонстрации экрана
            if hasattr(self, 'group_screen_window') and self.group_screen_window:
                self.group_screen_window.close()

            from screen_sharing_window import ScreenSharingWindow
            self.group_screen_window = ScreenSharingWindow(
                self.username,
                f"Группа: {self.current_group['name']} - Демонстрация от {sender}",
                is_sender=False,
                parent=self
            )

            # Настраиваем для группового приема
            self.group_screen_window.setup_group_receiving(group_id, sender)
            self.group_screen_window.show()

            print(f"[GROUP SCREEN] Created and showed viewing window for {sender}")

        except Exception as e:
            print(f"[GROUP SCREEN ERROR] Error in handle_group_screen_start: {e}")
            import traceback
            traceback.print_exc()

    def handle_group_screen_stop(self, group_id, sender):
        """Обрабатывает завершение групповой демонстрации экрана"""
        # Проверяем, что это текущая группа
        if not self.current_group or self.current_group['id'] != group_id:
            return

        print(f"[GROUP SCREEN] {sender} stopped screen sharing in group {group_id}")

        # Показываем уведомление в чате
        self.display_message(f"Система: {sender} завершил(а) демонстрацию экрана в группе")

        # Закрываем окно демонстрации экрана
        if hasattr(self, 'group_screen_window') and self.group_screen_window:
            self.group_screen_window.close()
            self.group_screen_window = None

    def handle_group_screen_data(self, message):
        """Обрабатывает данные групповой демонстрации экрана"""
        try:
            # Передаем обработку в ChatWindow, если он существует
            if hasattr(self, 'chat_window') and self.chat_window:
                self.chat_window.handle_group_screen_data(message)
            else:
                print(f"[GROUP SCREEN] No chat window available for data")
        except Exception as e:
            print(f"[GROUP SCREEN ERROR] Error handling data: {e}")

    def start_group_call_audio(self, group_id):
        """Запуск группового аудио через отдельный сокет"""
        print(f"[GROUP CALL AUDIO] Starting group call audio for group {group_id}")

        # Присоединяемся к групповому звонку
        join_message = f"GROUP_CALL_JOIN:{group_id}"
        try:
            self.group_call_client.send(f"{join_message}\n".encode('utf-8'))
        except Exception as e:
            print(f"[GROUP CALL ERROR] Failed to join call: {e}")
            return

        self.is_in_group_call = True
        self.current_group_call_id = group_id
        self.is_in_call = True  # Для работы send_audio
        self.start_audio()

    def stop_group_call_audio(self):
        print("[GROUP CALL AUDIO] Stopping group call audio")

        if self.current_group_call_id:
            leave_message = f"GROUP_CALL_LEAVE:{self.current_group_call_id}"
            try:
                self.group_call_client.send(f"{leave_message}\\n".encode('utf-8'))
            except Exception as e:
                print(f"[GROUP CALL ERROR] Failed to leave call: {e}")

        # Полный сброс состояния
        self.is_in_group_call = False
        self.current_group_call_id = None
        self.is_in_call = False  # Важно! Сбрасываем общий флаг звонка

        # Принудительно останавливаем и перезапускаем аудиопотоки
        self.stop_audio()

        # Небольшая задержка для корректного завершения потоков
        import time
        time.sleep(0.1)

        # Переинициализируем аудиопотоки для личных звонков
        try:
            if self.stream_input:
                self.stream_input.close()
            if self.stream_output:
                self.stream_output.close()
            self.init_audio_streams()
            print("[AUDIO FIX] Audio streams reinitialized after group call")
        except Exception as e:
            print(f"[AUDIO FIX ERROR] Failed to reinitialize audio: {e}")

    def init_audio_streams(self):
        try:
            self.stream_input = self.p.open(format=pyaudio.paInt16,
                                            channels=1,
                                            rate=44100,
                                            input=True,
                                            frames_per_buffer=1024)
            self.stream_output = self.p.open(format=pyaudio.paInt16,
                                             channels=1,
                                             rate=44100,
                                             output=True,
                                             frames_per_buffer=1024)
        except Exception as e:
            print(f"Ошибка инициализации аудиопотоков: {e}")

    def reset_audio_state(self):
        '''Полный сброс состояния аудио после группового звонка'''
        print("[AUDIO RESET] Resetting audio state")

        # Останавливаем все аудиопотоки
        self.stop_audio()

        # Сбрасываем все флаги
        self.is_in_call = False
        self.is_in_group_call = False
        self.current_group_call_id = None
        self.is_recording = False

        # Закрываем и переоткрываем аудиопотоки
        try:
            if self.stream_input and not self.stream_input.is_stopped():
                self.stream_input.stop_stream()
                self.stream_input.close()
            if self.stream_output and not self.stream_output.is_stopped():
                self.stream_output.stop_stream()
                self.stream_output.close()
        except Exception as e:
            print(f"[AUDIO RESET] Error closing streams: {e}")

        # Переинициализируем потоки
        import time
        time.sleep(0.2)  # Даем время на освобождение ресурсов
        self.init_audio_streams()

        print("[AUDIO RESET] Audio state reset complete")

    def authenticate_screen_connection(self):
        if self.username:
            auth_message = f"SCREEN_AUTH:{self.username}"
            try:
                self.screen_client.send(f"{auth_message}\n".encode('utf-8'))  # Добавлен \n
                print(f"[SCREEN] Authenticated screen connection for {self.username}")
            except Exception as e:
                print(f"[SCREEN ERROR] Failed to authenticate: {e}")

    def authenticate_group_connection(self):
        """Аутентифицирует соединение для группового чата"""
        if self.username:
            auth_message = f"GROUP_AUTH:{self.username}"
            try:
                self.group_client.send(f"{auth_message}\n".encode('utf-8'))
                print(f"[GROUP] Authenticated group connection for {self.username}")
            except Exception as e:
                print(f"[GROUP ERROR] Failed to authenticate: {e}")

    def send_direct_message(self, recipient, message):
        """Отправляет личное сообщение конкретному получателю"""
        try:
            direct_message = f"DIRECT_MESSAGE:{self.username}:{recipient}:{message}"
            self.client.send(f"{direct_message}\n".encode("utf-8"))
            print(f"[DIRECT] Sent direct message to {recipient}: {message}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to send direct message: {e}")
            return False

    def join_group_chat(self, group_id):
        """Присоединяется к групповому чату"""
        try:
            join_message = f"GROUP_JOIN:{group_id}"
            self.group_client.send(f"{join_message}\n".encode('utf-8'))
            print(f"[GROUP] Joining group {group_id}")
        except Exception as e:
            print(f"[GROUP ERROR] Failed to join group: {e}")

    def leave_group_chat(self, group_id):
        """Покидает групповой чат"""
        try:
            leave_message = f"GROUP_LEAVE:{group_id}"
            self.group_client.send(f"{leave_message}\n".encode('utf-8'))
            print(f"[GROUP] Leaving group {group_id}")
        except Exception as e:
            print(f"[GROUP ERROR] Failed to leave group: {e}")

    def send_group_file(self, group_id, file_path):
        """Отправляет файл в группу (идентично личным сообщениям)"""
        try:
            # Получаем информацию о файле
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            print(f"[GROUP FILE] Sending {file_name} to group {group_id}")

            # Уведомляем о начале передачи файла в группу
            file_info = f"GROUP_FILE_TRANSFER:START:{self.username}:{group_id}:{file_name}:{file_size}"
            self.group_client.send(f"{file_info}\n".encode('utf-8'))

            # Читаем и отправляем файл по частям (идентично личным сообщениям)
            with open(file_path, 'rb') as f:
                chunk_size = 4096  # 4KB части
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                    # Кодируем часть в base64 (идентично личным сообщениям)
                    import base64
                    encoded_chunk = base64.b64encode(chunk).decode('utf-8').replace('\n', '')

                    # Разбиваем большие части на более мелкие (идентично личным сообщениям)
                    max_msg_size = 900
                    for i in range(0, len(encoded_chunk), max_msg_size):
                        sub_chunk = encoded_chunk[i:i + max_msg_size]
                        chunk_msg = f"GROUP_FILE_TRANSFER:CHUNK:{self.username}:{group_id}:{sub_chunk}"
                        self.group_client.send(f"{chunk_msg}\n".encode('utf-8'))

                        # Небольшая задержка (идентично личным сообщениям)
                        import time

            # Уведомляем о завершении (идентично личным сообщениям)
            end_msg = f"GROUP_FILE_TRANSFER:END:{self.username}:{group_id}:{file_name}"
            self.group_client.send(f"{end_msg}\n".encode('utf-8'))

            print(f"[GROUP FILE] Sent {file_name} to group {group_id}")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to send group file: {e}")
            return False

    def send_group_message(self, group_id, message):
        """Отправляет сообщение в группу"""
        try:
            group_message = f"GROUP_MESSAGE:{group_id}:{self.username}:{message}"
            self.group_client.send(f"{group_message}\n".encode('utf-8'))
            print(f"[GROUP] Sent message to group {group_id}: {message}")
        except Exception as e:
            print(f"[GROUP ERROR] Failed to send group message: {e}")

    def send_message(self, message):
        try:
            self.client.send(f"{message}\n".encode("utf-8"))
        except Exception as e:
            print(f"Ошибка отправки сообщения: {e}")

    def send_screen_message(self, message):
        """Отправляет сообщение через соединение демонстрации экрана"""
        try:
            self.screen_client.send(f"{message}\n".encode("utf-8"))
        except Exception as e:
            print(f"Ошибка отправки сообщения демонстрации экрана: {e}")

    def send_call_signal(self, signal_type, recipient=None, duration=0):
        recipient = recipient or self.call_recipient
        signal = f"CALL_SIGNAL:{signal_type}:{self.username}:{recipient}:{time.time()}:{duration}"
        self.send_message(signal)
        print(f"[CLIENT] Sent call signal: {signal_type} to {recipient}")

    def send_screen_control_signal(self, signal_type):
        """Отправляет сигнал управления демонстрацией экрана через отдельное соединение"""
        if not self.call_recipient or not self.is_in_call:
            return

        signal = f"SCREEN_CONTROL:{self.username}:{self.call_recipient}:{signal_type}"
        self.send_screen_message(signal)
        print(f"[CLIENT] Sent screen control signal: {signal_type} to {self.call_recipient}")


    def get_screen_socket(self):
        """Возвращает сокет для демонстрации экрана"""
        return self.screen_client

    def receive_messages(self, callback):
        def handle_main_messages():
            """Обрабатывает сообщения из основного соединения"""
            buffer = ""
            while True:
                try:
                    data = self.client.recv(1024)
                    if not data:
                        print("[CLIENT] Main connection closed by server")
                        break

                    try:
                        buffer += data.decode("utf-8")
                        messages = buffer.split('\n')
                        buffer = messages[-1]
                        for message in messages[:-1]:
                            if message:
                                if message.startswith("GROUP_SCREEN_SIGNAL:"):
                                    self.handle_group_screen_signal(message, callback)
                                elif message.startswith("CALL_SIGNAL:"):
                                    self.handle_call_signal(message, callback)
                                elif message.startswith("FILE_TRANSFER:"):
                                    callback(message)
                                else:
                                    callback(message)
                    except UnicodeDecodeError:
                        # Аудиоданные
                        if self.is_in_call and self.stream_output and not self.is_speaker_muted:
                            try:
                                self.stream_output.write(data)
                            except Exception as e:
                                print(f"Ошибка воспроизведения аудио: {e}")
                except Exception as e:
                    print(f"Ошибка получения сообщений: {e}")
                    break

        def handle_screen_messages():
            """Обрабатывает сообщения из соединения демонстрации экрана"""
            buffer = ""
            screen_data_buffers = {}

            while True:
                try:
                    data = self.screen_client.recv(65536)
                    if not data:
                        print("[CLIENT] Screen connection closed by server")
                        break

                    try:
                        # Пытаемся декодировать как текст
                        buffer += data.decode("utf-8")
                        messages = buffer.split('\n')
                        buffer = messages[-1]
                        for message in messages[:-1]:
                            if message:
                                if message.startswith("SCREEN_CONTROL:"):
                                    self.handle_screen_control_signal(message, callback)
                                elif message.startswith("SCREEN_DATA_START:"):
                                    self.handle_screen_data_start(message, screen_data_buffers)
                                elif message.startswith("SCREEN_DATA_CHUNK:"):
                                    self.handle_screen_data_chunk(message, screen_data_buffers)
                                elif message.startswith("SCREEN_DATA_END:"):
                                    self.handle_screen_data_end(message, screen_data_buffers, callback)
                                    # Обработка групповых данных экрана
                                elif message.startswith("GROUP_SCREEN_DATA_START:"):
                                    print(f"[GROUP SCREEN CLIENT] Received START: {message}")
                                    if hasattr(self, 'chat_window') and self.chat_window:
                                        self.chat_window.handle_group_screen_data(message)
                                elif message.startswith("GROUP_SCREEN_DATA_CHUNK:"):
                                    # Не логируем каждый chunk чтобы не засорять логи
                                    if hasattr(self, 'chat_window') and self.chat_window:
                                        self.chat_window.handle_group_screen_data(message)
                                elif message.startswith("GROUP_SCREEN_DATA_END:"):
                                    print(f"[GROUP SCREEN CLIENT] Received END: {message}")
                                    if hasattr(self, 'chat_window') and self.chat_window:
                                        self.chat_window.handle_group_screen_data(message)
                    except UnicodeDecodeError:
                        # Это бинарные данные демонстрации экрана
                        if self.is_receiving_screen:
                            try:
                                # Распаковываем данные
                                decompressed_data = zlib.decompress(data)
                                callback(f"SCREEN_DATA:{decompressed_data}")
                            except Exception as e:
                                print(f"[SCREEN ERROR] Error decompressing screen data: {e}")
                except Exception as e:
                    print(f"Ошибка получения сообщений демонстрации экрана: {e}")
                    break

        def handle_group_call_messages():
            """Обрабатывает сообщения из соединения групповых звонков"""
            buffer = ""
            while True:
                try:
                    data = self.group_call_client.recv(8192)
                    if not data:
                        print("[CLIENT] Group call connection closed by server")
                        break

                    try:
                        buffer += data.decode("utf-8")
                        messages = buffer.split('\n')
                        buffer = messages[-1]
                        for message in messages[:-1]:
                            if message:
                                if message.startswith("GROUP_CALL_AUTH_SUCCESS"):
                                    print("[GROUP CALL] Authentication successful")
                                elif message.startswith("GROUP_CALL_JOINED:"):
                                    group_id = message.split(":", 1)[1]
                                    print(f"[GROUP CALL] Joined call in group {group_id}")
                                elif message.startswith("GROUP_CALL_LEFT:"):
                                    group_id = message.split(":", 1)[1]
                                    print(f"[GROUP CALL] Left call in group {group_id}")
                                elif message.startswith("GROUP_CALL_STATUS:"):
                                    callback(message)
                    except UnicodeDecodeError:
                        # Аудиоданные для групповых звонков
                        if self.is_in_group_call and self.stream_output and not self.is_speaker_muted:
                            try:
                                self.stream_output.write(data)
                                print("[GROUP CALL AUDIO] Received and played audio")
                            except Exception as e:
                                print(f"[GROUP CALL AUDIO ERROR] Error playing audio: {e}")
                except Exception as e:
                    print(f"Ошибка получения сообщений групповых звонков: {e}")
                    break

        def handle_group_messages():
            """Обрабатывает сообщения из группового чата"""
            buffer = ""
            while True:
                try:
                    data = self.group_client.recv(1024)
                    if not data:
                        print("[CLIENT] Group connection closed by server")
                        break

                    try:
                        buffer += data.decode("utf-8")
                        messages = buffer.split('\n')
                        buffer = messages[-1]
                        for message in messages[:-1]:
                            if message:
                                if message.startswith("GROUP_AUTH_SUCCESS"):
                                    print("[GROUP] Authentication successful")
                                elif message.startswith("GROUP_JOINED:"):
                                    group_id = message.split(":", 1)[1]
                                    callback(f"GROUP_JOINED:{group_id}")
                                elif message.startswith("GROUP_LEFT:"):
                                    group_id = message.split(":", 1)[1]
                                    callback(f"GROUP_LEFT:{group_id}")
                                elif message.startswith("GROUP_MESSAGE:"):
                                    callback(message)
                    except UnicodeDecodeError:
                        pass
                except Exception as e:
                    print(f"Ошибка получения групповых сообщений: {e}")
                    break

        # Запускаем оба потока
        main_thread = threading.Thread(target=handle_main_messages)
        main_thread.daemon = True
        main_thread.start()

        screen_thread = threading.Thread(target=handle_screen_messages)
        screen_thread.daemon = True
        screen_thread.start()

        # Запускаем поток для группового чата
        group_thread = threading.Thread(target=handle_group_messages)
        group_thread.daemon = True
        group_thread.start()

        # поток для групповых звонков
        group_call_thread = threading.Thread(target=handle_group_call_messages)
        group_call_thread.daemon = True
        group_call_thread.start()

    def handle_screen_data_start(self, message, screen_data_buffers):
        """Обрабатывает начало передачи кадра"""
        try:
            parts = message.split(":")
            if len(parts) >= 5:
                sender = parts[1]
                recipient = parts[2]
                frame_id = parts[3]
                chunks_count = int(parts[4])

                if recipient == self.username:
                    screen_data_buffers[frame_id] = {
                        'chunks': [''] * chunks_count,
                        'received': 0
                    }
        except Exception as e:
            print(f"[SCREEN ERROR] Error handling screen data start: {e}")



    def handle_screen_data_chunk(self, message, screen_data_buffers):
        """Обрабатывает часть кадра"""
        try:
            parts = message.split(":", 5)
            if len(parts) >= 6:
                sender = parts[1]
                recipient = parts[2]
                frame_id = parts[3]
                chunk_id = int(parts[4])
                chunk_data = parts[5]

                if recipient == self.username and frame_id in screen_data_buffers:
                    screen_data_buffers[frame_id]['chunks'][chunk_id] = chunk_data
                    screen_data_buffers[frame_id]['received'] += 1
        except Exception as e:
            print(f"[SCREEN ERROR] Error handling screen data chunk: {e}")

    def handle_screen_data_end(self, message, screen_data_buffers, callback):
        """Обрабатывает завершение передачи кадра"""
        try:
            parts = message.split(":")
            if len(parts) >= 4:
                sender = parts[1]
                recipient = parts[2]
                frame_id = parts[3]

                if recipient == self.username and frame_id in screen_data_buffers:
                    buffer = screen_data_buffers[frame_id]
                    if buffer['received'] == len(buffer['chunks']):
                        complete_data = ''.join(buffer['chunks'])
                        callback(f"SCREEN_DATA_COMPLETE:{complete_data}")
                    del screen_data_buffers[frame_id]
        except Exception as e:
            print(f"[SCREEN ERROR] Error handling screen data end: {e}")

    def handle_group_file_transfer(self, message):
        """Обрабатывает передачу файлов в группах с безопасностью потоков"""
        try:
            parts = message.split(":", 4)
            if len(parts) < 5:
                print(f"[ERROR] Invalid group file transfer format: {message}")
                return

            action = parts[1]  # START, CHUNK, END
            sender = parts[2]
            group_id = int(parts[3])

            # Проверяем, что это наша текущая группа
            if not self.current_group or self.current_group['id'] != group_id:
                return

            # Обрабатываем только если мы НЕ отправитель
            if sender == self.username:
                return

            if action == "START":
                file_info = parts[4].split(":", 1)
                file_name = file_info[0]
                try:
                    file_size = int(file_info[1])
                except ValueError:
                    file_size = 0

                # Создаем временный файл для входящих данных
                self.incoming_group_file = {
                    "name": file_name,
                    "size": file_size,
                    "sender": sender,
                    "group_id": group_id,
                    "data": bytearray(),
                    "path": os.path.join("downloads", file_name)
                }

                # Создаем директорию, если не существует
                os.makedirs("downloads", exist_ok=True)

                print(f"[GROUP FILE] Starting to receive {file_name} from {sender}")

            elif action == "CHUNK" and hasattr(self, "incoming_group_file"):
                # Декодируем и добавляем часть файла
                encoded_chunk = parts[4]
                try:
                    encoded_chunk = encoded_chunk.replace(' ', '').replace('\n', '').replace('\r', '')
                    padding = 4 - (len(encoded_chunk) % 4) if len(encoded_chunk) % 4 != 0 else 0
                    encoded_chunk += '=' * padding

                    import base64
                    chunk_data = base64.b64decode(encoded_chunk)
                    self.incoming_group_file["data"].extend(chunk_data)
                except Exception as e:
                    print(f"[ERROR] Failed to decode group file chunk: {e}")

            elif action == "END" and hasattr(self, "incoming_group_file"):
                file_name = parts[4]

                try:
                    # Сохраняем полный файл
                    with open(self.incoming_group_file["path"], "wb") as f:
                        f.write(self.incoming_group_file["data"])

                    print(f"[GROUP FILE] Saved file {file_name} from {sender}")

                    # Проверяем, является ли файл изображением
                    is_image = file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))

                    # Используем сигнал для безопасного обновления UI
                    if is_image:
                        # Создаем уменьшенную копию в фоновом потоке
                        scaled_path = self.create_scaled_image_safe(self.incoming_group_file["path"])

                    # Используем сигнал для обновления UI из главного потока
                    # Эмитируем сигнал для обновления отображения файлов
                    self.update_ui_signal.emit("refresh_file_display", None)

                except Exception as e:
                    print(f"[ERROR] Failed to save group file: {e}")

                # Очищаем
                del self.incoming_group_file

        except Exception as e:
            print(f"[ERROR] Error handling group file transfer: {e}")

    def handle_screen_control_signal(self, message, callback):
        """Обрабатывает сигналы управления демонстрацией экрана"""
        try:
            parts = message.split(":")
            if len(parts) < 4:
                print(f"[ERROR] Invalid screen control signal format: {message}")
                return

            sender = parts[1]
            recipient = parts[2]
            action = parts[3]

            print(f"[CLIENT] Received screen control signal: {action} from {sender} to {recipient}")

            # Проверяем, относится ли сигнал к текущему звонку
            if (recipient == self.username and sender == self.call_recipient) or \
                    (sender == self.username and recipient == self.call_recipient):

                if action == "start":
                    # Если мы получатель сигнала, начинаем прием демонстрации
                    if recipient == self.username:
                        self.is_receiving_screen = True
                        callback(f"SCREEN_SHARE_START:{sender}")

                elif action == "stop":
                    # Если мы получатель сигнала, останавливаем прием демонстрации
                    if recipient == self.username:
                        self.is_receiving_screen = False
                        callback(f"SCREEN_SHARE_STOP:{sender}")

        except Exception as e:
            print(f"Ошибка обработки сигнала управления демонстрацией экрана: {e}")

    def handle_call_signal(self, message, callback):
        try:
            signal_data = message[12:]
            parts = signal_data.split(':')
            if len(parts) < 4:
                print(f"[ERROR] Invalid call signal format: {signal_data}")
                return

            signal_type = parts[0]
            sender = parts[1]
            recipient = parts[2]
            timestamp = float(parts[3])
            duration = int(parts[4]) if len(parts) > 4 else 0

            print(f"[CLIENT] Received call signal: {signal_type} from {sender} to {recipient}")

            # Обрабатываем входящие звонки
            if signal_type == "incoming_call":
                # Если мы получатель звонка
                if recipient == self.username:
                    print(f"[CLIENT] Showing incoming call from {sender}")
                    callback(f"INCOMING_CALL:{sender}")
                # Если мы звонящий, обновляем UI
                elif sender == self.username:
                    print(f"[CLIENT] Outgoing call to {recipient}")
                    callback(f"OUTGOING_CALL:{recipient}")
            # Обрабатываем принятие звонка
            elif signal_type == "call_accepted":
                if (sender == self.username and recipient == self.call_recipient) or \
                        (recipient == self.username and sender == self.call_recipient):
                    callback(f"CALL_ACCEPTED:{sender if recipient == self.username else recipient}")
            # Обрабатываем отклонение звонка
            elif signal_type == "call_rejected":
                if (sender == self.username and recipient == self.call_recipient) or \
                        (recipient == self.username and sender == self.call_recipient):
                    callback(f"CALL_REJECTED:{sender if recipient == self.username else recipient}")
                if sender == self.username:
                    self.call_recipient = None
            # Обрабатываем завершение звонка
            elif signal_type == "call_ended":
                if self.call_recipient == sender or self.username == recipient or sender == self.call_recipient:
                    callback(f"CALL_ENDED:{sender}:{duration}")
                    self.call_recipient = None
                    self.is_in_call = False
                    self.stop_audio()
                    # Останавливаем демонстрацию экрана при завершении звонка
                    self.is_sharing_screen = False
                    self.is_receiving_screen = False
                # Если звонок завершен до того, как мы его приняли/отклонили, также обрабатываем
                elif (sender == self.username and recipient == self.call_recipient) or \
                        (recipient == self.username and sender == self.call_recipient):
                    callback(f"CALL_ENDED:{sender}:{duration}")
                    self.call_recipient = None
                    self.is_in_call = False
                    self.stop_audio()
                    self.is_sharing_screen = False
                    self.is_receiving_screen = False
        except Exception as e:
            print(f"Ошибка обработки сигнала звонка: {e}")

    def send_audio(self):
        """метод отправки аудио"""
        while self.is_recording and (self.is_in_call or self.is_in_group_call):
            try:
                if not self.is_mic_muted:
                    data = self.stream_input.read(1024, exception_on_overflow=False)

                    if self.is_in_group_call and self.current_group_call_id:
                        # Отправляем аудио через отдельный сокет групповых звонков
                        try:
                            self.group_call_client.send(data)
                            print(f"[GROUP CALL AUDIO] Sent audio to group {self.current_group_call_id}")
                        except Exception as e:
                            print(f"[GROUP CALL AUDIO ERROR] Failed to send audio: {e}")
                            break
                    else:
                        # Обычный личный звонок через основной сокет
                        self.client.send(data)
                else:
                    time.sleep(0.1)
            except Exception as e:
                print(f"Ошибка отправки аудио: {e}")
                break

    def start_audio(self):
        if not self.is_recording:
            self.is_recording = True
            self.audio_thread = threading.Thread(target=self.send_audio)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            print("[CLIENT] Started audio stream")

    def stop_audio(self):
        self.is_recording = False
        if self.audio_thread:
            self.audio_thread.join(timeout=1.0)
            self.audio_thread = None
            print("[CLIENT] Stopped audio stream")

    def set_mic_muted(self, is_muted):
        self.is_mic_muted = is_muted
        print(f"[CLIENT] Microphone {'muted' if is_muted else 'unmuted'}")

    def set_speaker_muted(self, is_muted):
        self.is_speaker_muted = is_muted
        if is_muted:
            if self.stream_output and self.stream_output.is_active():
                try:
                    self.stream_output.stop_stream()
                except Exception as e:
                    print(f"[ERROR] Failed to stop audio stream: {e}")
        else:
            if self.stream_output and not self.stream_output.is_active():
                try:
                    self.stream_output.start_stream()
                except Exception as e:
                    print(f"[ERROR] Failed to start audio stream: {e}")
        print(f"[CLIENT] Speaker {'muted' if is_muted else 'unmuted'}")

    def start_call(self, recipient):
        if self.is_in_call:
            return False
        self.call_recipient = recipient
        self.send_call_signal("incoming_call", recipient)
        return True

    def accept_call(self, caller):
        if self.is_in_call:
            return False
        self.call_recipient = caller
        self.is_in_call = True
        self.send_call_signal("call_accepted", caller)
        self.start_audio()
        return True

    def reject_call(self, caller):
        self.send_call_signal("call_rejected", caller)

    def end_call(self, duration=0):
        if self.call_recipient:
            self.send_call_signal("call_ended", self.call_recipient, duration)
            self.is_in_call = False
            self.stop_audio()
            self.is_sharing_screen = False
            self.is_receiving_screen = False
            self.call_recipient = None


class ChatWindow(QtWidgets.QWidget):
    group_screen_start_signal = QtCore.pyqtSignal(str, int)  # sender, group_id
    group_screen_stop_signal = QtCore.pyqtSignal(str, int)  # sender, group_id
    group_screen_data_signal = QtCore.pyqtSignal(str)  # message
    update_ui_signal = QtCore.pyqtSignal(str, object)
    # сигнал для обновления чата
    refresh_chat_signal = QtCore.pyqtSignal()

    def __init__(self, client, username, connection=None):
        super().__init__()
        self.client = client
        self.client.username = username
        self.username = username
        self.connection = connection
        self.current_chat_with = None
        self.notification_count = 0
        self.friends = []
        self.call_dialog = None
        self.call_start_time = None
        self.chat_initialized = {}
        # свойства для вложений
        self.current_attachment = None
        self.attachment_preview = None
        self.client.chat_window = self

        self.client.authenticate_group_call_connection()

        self.group_screen_start_signal.connect(self.handle_group_screen_start_safe)
        self.group_screen_stop_signal.connect(self.handle_group_screen_stop_safe)
        self.group_screen_data_signal.connect(self.handle_group_screen_data_safe)
        self.group_call_dialog = None
        self.group_call_status = {}  # {group_id: {'active': bool, 'participants': list}}
        self.client.send_message(f"STATUS_ONLINE:{username}")

        self.client.authenticate_group_connection()
        self.current_group = None
        self.screen_sharing_window = None
        self.group_screen_window = None
        # Максимальные размеры для изображений в чате
        self.max_image_width = 300
        self.max_image_height = 200

        # Кэш для масштабированных изображений
        self.scaled_image_cache = {}

        # Подключаем сигналы
        self.update_ui_signal.connect(self.update_ui)

        # Подключаем сигнал для обновления чата
        self.refresh_chat_signal.connect(self.refresh_chat_safe)

        # Аутентифицируем соединение демонстрации экрана
        self.client.authenticate_screen_connection()

        # Отправляем сообщение серверу, чтобы зарегистрировать наше имя пользователя
        self.client.send_message(f"{username}: в сети")

        self.client.receive_messages(self.handle_message)
        self.ping = 23
        self.server = "Moscow"

        self.setWindowTitle("Voice Chat")
        self.resize(1200, 700)
        self.setStyleSheet("background-color: #e0e0e0;")

        self.main_layout = QtWidgets.QHBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(0)

        self.left_sidebar = QtWidgets.QWidget()
        self.left_sidebar.setFixedWidth(120)
        self.left_sidebar_layout = QtWidgets.QVBoxLayout(self.left_sidebar)
        self.left_sidebar_layout.setAlignment(QtCore.Qt.AlignTop)
        self.left_sidebar_layout.setContentsMargins(5, 5, 5, 5)
        self.left_sidebar_layout.setSpacing(5)

        self.avatar_frame = QtWidgets.QFrame()
        self.avatar_frame.setFixedSize(80, 80)
        self.avatar_frame.setStyleSheet("background-color: #d8c4eb; border-radius: 15px; border: 2px solid #9370DB;")
        self.avatar_layout = QtWidgets.QVBoxLayout(self.avatar_frame)
        self.avatar_layout.setContentsMargins(5, 5, 5, 5)

        self.avatar_icon = QtWidgets.QLabel()
        self.avatar_icon.setAlignment(QtCore.Qt.AlignCenter)
        self.avatar_icon.setStyleSheet("border: none;")
        self.avatar_icon.setText("👤")
        self.avatar_icon.setFont(QtGui.QFont("Arial", 30))
        self.avatar_layout.addWidget(self.avatar_icon)

        # Делаем аватар кликабельным
        self.avatar_frame.mousePressEvent = self.open_profile_dialog
        self.avatar_frame.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        self.left_sidebar_layout.addWidget(self.avatar_frame, 0, QtCore.Qt.AlignHCenter)

        self.nickname_label = QtWidgets.QLabel(self.username)
        self.nickname_label.setAlignment(QtCore.Qt.AlignCenter)
        self.nickname_label.setFont(QtGui.QFont("Arial", 12))
        self.nickname_label.setStyleSheet("color: #333;")
        self.left_sidebar_layout.addWidget(self.nickname_label)

        self.left_sidebar_layout.addStretch()

        self.ping_layout = QtWidgets.QHBoxLayout()
        self.ping_icon = QtWidgets.QLabel("🔗")
        self.ping_icon.setFont(QtGui.QFont("Arial", 12))
        self.ping_layout.addWidget(self.ping_icon)

        self.ping_info = QtWidgets.QVBoxLayout()
        self.ping_label = QtWidgets.QLabel(f"Ping {self.ping} ms")
        self.ping_label.setFont(QtGui.QFont("Arial", 9))
        self.server_label = QtWidgets.QLabel(f"Server {self.server}")
        self.server_label.setFont(QtGui.QFont("Arial", 9))
        self.ping_info.addWidget(self.ping_label)
        self.ping_info.addWidget(self.server_label)

        self.ping_layout.addLayout(self.ping_info)
        self.left_sidebar_layout.addLayout(self.ping_layout)

        self.load_user_avatar(self.username, self.avatar_icon, self.avatar_frame)
        if self.connection:
            self.load_friends()
            self.check_notifications()
            self.notification_timer = QtCore.QTimer()
            self.notification_timer.timeout.connect(self.check_notifications)
            self.notification_timer.start(10000)

        self.center_content = QtWidgets.QWidget()
        self.center_layout = QtWidgets.QVBoxLayout(self.center_content)
        self.center_layout.setContentsMargins(10, 10, 10, 10)
        self.center_layout.setSpacing(10)

        self.top_bar = QtWidgets.QWidget()
        self.top_bar.setFixedHeight(60)
        self.top_bar.setStyleSheet("background-color: #d9d9d9; border-radius: 20px;")
        self.top_bar_layout = QtWidgets.QHBoxLayout(self.top_bar)
        self.top_bar_layout.setContentsMargins(15, 5, 15, 5)

        self.settings_btn = QtWidgets.QPushButton("⚙️")
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setFont(QtGui.QFont("Arial", 12))
        self.settings_btn.setStyleSheet("background: transparent; border: none;")
        # Подключаем обработчик для кнопки настроек
        self.settings_btn.clicked.connect(self.open_profile_dialog)
        self.top_bar_layout.addWidget(self.settings_btn)

        self.top_bar_layout.addStretch()

        self.group_icon = QtWidgets.QPushButton("👥")
        self.group_icon.setFixedSize(30, 30)
        self.group_icon.setFont(QtGui.QFont("Arial", 12))
        self.group_icon.setStyleSheet("background: transparent; border: none;")
        self.group_icon.clicked.connect(self.open_friends_dialog)
        self.top_bar_layout.addWidget(self.group_icon)

        self.friends_layout = QtWidgets.QHBoxLayout()
        self.friends_layout.setSpacing(5)
        self.top_bar_layout.addLayout(self.friends_layout)

        self.add_user_btn = QtWidgets.QPushButton("👥+")
        self.add_user_btn.setFixedSize(30, 30)
        self.add_user_btn.setFont(QtGui.QFont("Arial", 12))
        self.add_user_btn.setStyleSheet("background: transparent; border: none;")
        self.add_user_btn.clicked.connect(self.open_friend_search)
        self.top_bar_layout.addWidget(self.add_user_btn)

        self.top_bar_layout.addStretch()

        self.notification_btn = QtWidgets.QPushButton("🔔")
        self.notification_btn.setFixedSize(30, 30)
        self.notification_btn.setFont(QtGui.QFont("Arial", 12))
        self.notification_btn.setStyleSheet("background: transparent; border: none;")
        self.notification_btn.clicked.connect(self.open_notifications)
        self.top_bar_layout.addWidget(self.notification_btn)

        self.center_layout.addWidget(self.top_bar)

        # Создаем компактную панель с именем собеседника
        self.chat_header_panel = QtWidgets.QWidget()
        self.chat_header_panel.setFixedHeight(40)
        self.chat_header_panel.setStyleSheet("background-color: #d9d9d9; border-radius: 10px;")
        self.chat_header_layout = QtWidgets.QHBoxLayout(self.chat_header_panel)
        self.chat_header_layout.setContentsMargins(10, 5, 10, 5)
        self.chat_header_layout.setAlignment(QtCore.Qt.AlignCenter)

        self.chat_header = QtWidgets.QLabel("")
        self.chat_header.setAlignment(QtCore.Qt.AlignCenter)
        self.chat_header.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
        self.chat_header.setStyleSheet("color: #333333;")
        self.chat_header_layout.addWidget(self.chat_header)

        # Скрываем панель по умолчанию, она будет показываться только при активном чате
        self.chat_header_panel.hide()

        self.center_layout.addWidget(self.chat_header_panel)

        # Создаем панель поиска
        self.search_bar = SearchBar(self)
        self.search_bar.hide()  # Скрываем по умолчанию
        self.center_layout.addWidget(self.search_bar)

        # Создаем стек виджетов для переключения между стартовым экраном и чатом
        self.content_stack = QtWidgets.QStackedWidget()

        # Создаем стартовый экран с логотипом
        self.welcome_screen = QtWidgets.QWidget()
        self.welcome_layout = QtWidgets.QVBoxLayout(self.welcome_screen)
        self.welcome_layout.setAlignment(QtCore.Qt.AlignCenter)

        # Логотип приложения
        self.logo_frame = QtWidgets.QFrame()
        self.logo_frame.setFixedSize(200, 200)
        self.logo_frame.setStyleSheet("border-radius: 100px;")  # без фона
        self.logo_layout = QtWidgets.QVBoxLayout(self.logo_frame)
        self.logo_layout.setContentsMargins(20, 20, 20, 20)

        # Создать метку логотипа
        self.logo_icon = QtWidgets.QLabel()
        self.logo_icon.setAlignment(QtCore.Qt.AlignCenter)
        self.logo_icon.setStyleSheet("border: none;")

        logo_pixmap = QtGui.QPixmap("logo\logo.png")  # ссылка на файл с логотипом

        # Проверить, удалось ли загрузить изображение
        if logo_pixmap.isNull():
            print("Ошибка: не удалось загрузить изображение логотипа")
            self.logo_icon.setText("Volum")  # Запасной вариант — текст, если изображение не загрузилось
            self.logo_icon.setFont(QtGui.QFont("Arial", 80, QtGui.QFont.Bold))
            self.logo_icon.setStyleSheet("border: none; color: #333;")
        else:
            # Масштабировать изображение до нужного размера
            logo_pixmap = logo_pixmap.scaled(100, 100, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.logo_icon.setPixmap(logo_pixmap)

        # Добавить логотип
        self.logo_layout.addWidget(self.logo_icon)

        # Текстовая метка под логотипом
        self.logo_text = QtWidgets.QLabel("Volum")
        self.logo_text.setAlignment(QtCore.Qt.AlignCenter)
        self.logo_text.setFont(QtGui.QFont("Arial", 24, QtGui.QFont.Bold))
        self.logo_text.setStyleSheet("color: #333; margin-top: 10px;")
        self.logo_layout.addWidget(self.logo_text)

        # отступ над логотипом
        self.welcome_layout.addStretch(1)   # гибкое пространство сверху, чтобы прижать логотип вверх
        self.welcome_layout.addWidget(self.logo_frame, 0, QtCore.Qt.AlignCenter)
        self.welcome_layout.addStretch(2)

        # Создаем виджет чата
        self.chat_widget = QtWidgets.QWidget()
        self.chat_layout = QtWidgets.QVBoxLayout(self.chat_widget)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.setSpacing(10)

        self.text_display = QtWidgets.QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setStyleSheet("background-color: #e0e0e0; border: none; font-size: 14px;")
        self.chat_layout.addWidget(self.text_display)
        self.setup_text_display()

        self.bottom_bar = QtWidgets.QWidget()
        self.bottom_bar.setFixedHeight(70)
        self.bottom_bar.setStyleSheet("background-color: #d9d9d9; border-radius: 20px;")
        self.bottom_bar_layout = QtWidgets.QHBoxLayout(self.bottom_bar)
        self.bottom_bar_layout.setContentsMargins(10, 10, 10, 10)

        self.call_btn = QtWidgets.QPushButton()
        self.call_btn.setFixedSize(50, 50)
        self.call_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")
        call_layout = QtWidgets.QVBoxLayout(self.call_btn)
        call_layout.setContentsMargins(5, 5, 5, 5)
        self.call_icon = QtWidgets.QLabel("📞")
        self.call_icon.setAlignment(QtCore.Qt.AlignCenter)
        self.call_icon.setFont(QtGui.QFont("Arial", 20))
        call_layout.addWidget(self.call_icon)
        self.call_btn.clicked.connect(self.handle_call_button)
        self.bottom_bar_layout.addWidget(self.call_btn)

        self.message_input = QtWidgets.QLineEdit()
        self.message_input.setPlaceholderText("Enter the text")
        self.message_input.setStyleSheet(
            "background-color: #e0e0e0; border-radius: 15px; padding: 10px; font-size: 14px;")
        self.message_input.setMinimumHeight(50)
        self.bottom_bar_layout.addWidget(self.message_input)

        self.attach_btn = QtWidgets.QPushButton()
        self.attach_btn.setFixedSize(50, 50)
        self.attach_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")
        attach_layout = QtWidgets.QVBoxLayout(self.attach_btn)
        attach_layout.setContentsMargins(5, 5, 5, 5)
        attach_icon = QtWidgets.QLabel("📎")
        attach_icon.setAlignment(QtCore.Qt.AlignCenter)
        attach_icon.setFont(QtGui.QFont("Arial", 20))
        attach_layout.addWidget(attach_icon)
        self.attach_btn.clicked.connect(self.open_attachment_dialog)  # Подключаем обработчик для кнопки вложений
        self.bottom_bar_layout.addWidget(self.attach_btn)

        self.send_btn = QtWidgets.QPushButton()
        self.send_btn.setFixedSize(50, 50)
        self.send_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")
        send_layout = QtWidgets.QVBoxLayout(self.send_btn)
        send_layout.setContentsMargins(5, 5, 5, 5)
        send_icon = QtWidgets.QLabel("➤")
        send_icon.setAlignment(QtCore.Qt.AlignCenter)
        send_icon.setFont(QtGui.QFont("Arial", 20))
        send_layout.addWidget(send_icon)
        self.send_btn.clicked.connect(self.send_message)
        self.bottom_bar_layout.addWidget(self.send_btn)

        self.chat_layout.addWidget(self.bottom_bar)

        # Добавляем оба экрана в стек и устанавливаем стартовый экран по умолчанию
        self.content_stack.addWidget(self.welcome_screen)
        self.content_stack.addWidget(self.chat_widget)
        self.content_stack.setCurrentIndex(0)  # Показываем стартовый экран

        self.center_layout.addWidget(self.content_stack)

        self.right_sidebar = QtWidgets.QWidget()
        self.right_sidebar.setFixedWidth(80)
        self.right_sidebar_layout = QtWidgets.QVBoxLayout(self.right_sidebar)
        self.right_sidebar_layout.setAlignment(QtCore.Qt.AlignTop)
        self.right_sidebar_layout.setContentsMargins(5, 5, 5, 5)
        self.right_sidebar_layout.setSpacing(15)


        self.right_sidebar_layout.addStretch()

        if self.connection:
            self.load_user_groups()
        self.add_server_btn = QtWidgets.QPushButton()
        self.add_server_btn.setFixedSize(60, 60)
        self.add_server_btn.setStyleSheet("background-color: #d9d9d9; border-radius: 15px; border: 2px solid #999;")
        add_server_layout = QtWidgets.QVBoxLayout(self.add_server_btn)
        add_server_layout.setContentsMargins(5, 5, 5, 5)
        add_server_icon = QtWidgets.QLabel("+")
        add_server_icon.setAlignment(QtCore.Qt.AlignCenter)
        add_server_icon.setFont(QtGui.QFont("Arial", 20))
        add_server_layout.addWidget(add_server_icon)
        self.right_sidebar_layout.addWidget(self.add_server_btn)
        self.add_server_btn.clicked.connect(self.open_create_group_dialog)

        self.main_layout.addWidget(self.left_sidebar)
        self.main_layout.addWidget(self.center_content)
        self.main_layout.addWidget(self.right_sidebar)

        self.message_input.returnPressed.connect(self.send_message)

        if self.connection:
            self.load_friends()
            self.check_notifications()
            self.notification_timer = QtCore.QTimer()
            self.notification_timer.timeout.connect(self.check_notifications)
            self.notification_timer.start(10000)


        if hasattr(self, 'connection') and self.connection:
            self.load_user_groups()

    def setup_text_display(self):
        """Настраивает QTextEdit для отображения изображений и обработки кликов по файлам"""
        # Разрешаем отображение изображений и других ресурсов
        self.text_display.document().setDefaultStyleSheet("""
        img { max-width: 300px; max-height: 200px; }
        a { color: #2196F3; text-decoration: none; }
        """)

        # Разрешаем HTML-форматирование
        self.text_display.setHtml("")

        # Создаем директорию downloads, если она не существует
        os.makedirs("downloads", exist_ok=True)

        # Создаем директорию для уменьшенных изображений
        os.makedirs(os.path.join("downloads", "scaled"), exist_ok=True)

        # Подключаем обработчик событий для отслеживания кликов мыши
        self.text_display.mousePressEvent = self.text_display_mouse_press_event

        # Добавляем обработчик контекстного меню
        self.text_display.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.text_display.customContextMenuRequested.connect(self.show_context_menu)

        # Сохраняем оригинальный обработчик событий мыши
        self.original_mouse_press_event = QtWidgets.QTextEdit.mousePressEvent

    def show_context_menu(self, position):
        """Показывает контекстное меню при правом клике на сообщение"""
        try:
            # Получаем курсор в позиции клика
            cursor = self.text_display.cursorForPosition(position)

            # Получаем текущий блок (строку)
            current_block = cursor.block()

            # Получаем текст текущего блока
            current_text = current_block.text()

            # Проверяем, является ли текущий блок сообщением или заголовком с именем пользователя
            is_header = False
            is_message = False
            username = None

            # Проверяем, содержит ли текущая строка временную метку (формат ЧЧ:ММ)
            import re
            time_match = re.search(r'\d{2}:\d{2}', current_text)

            # Проверяем, является ли это системным сообщением
            if "Система" in current_text or "Звонок" in current_text or "в сети" in current_text or "вышел из сети" in current_text:
                # Не показываем контекстное меню для системных сообщений
                return

            if time_match:
                # Это заголовок сообщения с именем пользователя
                is_header = True
                # Извлекаем имя пользователя (текст до первого пробела)
                username_match = re.search(r'^(\S+)', current_text)
                if username_match:
                    username = username_match.group(1)

                    # Проверяем, не является ли это системным сообщением
                    if username == "Система":
                        return

                # Переходим к следующему блоку, который содержит текст сообщения
                next_block = current_block.next()
                if next_block.isValid():
                    message_text = next_block.text()
                    is_message = True
                    message_block = next_block
            else:
                # Проверяем, может быть это текст сообщения, а заголовок выше
                prev_block = current_block.previous()
                if prev_block.isValid():
                    prev_text = prev_block.text()
                    time_match = re.search(r'\d{2}:\d{2}', prev_text)
                    if time_match:
                        # Предыдущий блок - заголовок
                        username_match = re.search(r'^(\S+)', prev_text)
                        if username_match:
                            username = username_match.group(1)

                            # Проверяем, не является ли это системным сообщение
                            if username == "Система":
                                return

                        message_text = current_text
                        is_message = True
                        message_block = current_block

            # Если это сообщение текущего пользователя, показываем контекстное меню
            if is_message and username == self.username:
                # Проверяем, не является ли сообщение уже удаленным
                if message_text == "Сообщение удалено":
                    return

                # Сохраняем текущий блок и текст сообщения для последующего редактирования/удаления
                self.current_selected_header_block = current_block if is_header else prev_block
                self.current_selected_message_block = message_block
                self.current_message_text = message_text

                # Создаем контекстное меню
                context_menu = QtWidgets.QMenu(self)

                # Добавляем действия
                edit_action = context_menu.addAction("Редактировать")
                delete_action = context_menu.addAction("Удалить")

                # Подключаем обработчики в зависимости от типа чата (личный или групповой)
                if self.current_group:
                    edit_action.triggered.connect(self.edit_group_message)
                    delete_action.triggered.connect(self.delete_group_message)
                else:
                    edit_action.triggered.connect(self.edit_message)
                    delete_action.triggered.connect(self.delete_message)

                # Показываем меню
                context_menu.exec_(self.text_display.mapToGlobal(position))
        except Exception as e:
            print(f"[ERROR] Error showing context menu: {e}")

    def find_message_id_in_database(self, message_text):
        """Ищет ID сообщения в базе данных по тексту сообщения"""
        if not self.connection or not self.current_chat_with:
            return None

        try:
            cursor = self.connection.cursor()

            # Получаем все сообщения от текущего пользователя к текущему собеседнику
            cursor.execute(
                """
                SELECT id, content FROM messages 
                WHERE sender = %s AND receiver = %s
                ORDER BY timestamp DESC
                """,
                (self.username, self.current_chat_with)
            )
            all_messages = cursor.fetchall()
            cursor.close()

            # Ищем сообщение с наиболее похожим содержимым
            best_match_id = None

            # Сначала ищем точное совпадение
            for msg_id, content in all_messages:
                if content == message_text:
                    return msg_id

            # Если точное совпадение не найдено, ищем по содержимому без учета регистра
            for msg_id, content in all_messages:
                if content.lower() == message_text.lower():
                    return msg_id

            # Если и это не помогло, ищем по первым словам
            words = message_text.split()
            if words:
                first_word = words[0]
                for msg_id, content in all_messages:
                    if content.startswith(first_word):
                        return msg_id

            # Если все методы не сработали, возвращаем None
            return None
        except Exception as e:
            return None

    def find_group_message_id_in_database(self, message_text):
        """Ищет ID сообщения группы в базе данных по тексту сообщения"""
        if not self.connection or not self.current_group:
            return None

        try:
            cursor = self.connection.cursor()

            # Очищаем текст сообщения от пометки "(изменено)"
            clean_text = message_text.replace(" (изменено)", "").strip()

            # Получаем все сообщения от текущего пользователя в текущей группе
            cursor.execute(
                """
                SELECT id, content FROM group_messages 
                WHERE sender = %s AND group_id = %s AND deleted = FALSE
                ORDER BY timestamp DESC
                """,
                (self.username, self.current_group['id'])
            )
            all_messages = cursor.fetchall()
            cursor.close()

            print(f"[DEBUG] Looking for message: '{clean_text}'")
            print(f"[DEBUG] Found {len(all_messages)} messages from user")

            # Сначала ищем точное совпадение
            for msg_id, content in all_messages:
                # Также очищаем содержимое из БД от пометки "(изменено)"
                clean_content = content.replace(" (изменено)", "").strip()
                print(f"[DEBUG] Comparing with: '{clean_content}' (ID: {msg_id})")
                if clean_content == clean_text:
                    print(f"[DEBUG] Found exact match: ID {msg_id}")
                    return msg_id

            # Если точное совпадение не найдено, ищем по содержимому без учета регистра
            for msg_id, content in all_messages:
                clean_content = content.replace(" (изменено)", "").strip()
                if clean_content.lower() == clean_text.lower():
                    print(f"[DEBUG] Found case-insensitive match: ID {msg_id}")
                    return msg_id

            # Если и это не помогло, ищем по первым словам
            words = clean_text.split()
            if words:
                first_word = words[0]
                for msg_id, content in all_messages:
                    clean_content = content.replace(" (изменено)", "").strip()
                    if clean_content.startswith(first_word):
                        print(f"[DEBUG] Found partial match: ID {msg_id}")
                        return msg_id

            print(f"[DEBUG] No match found for message: '{clean_text}'")
            return None
        except Exception as e:
            print(f"[ERROR] Error finding group message ID: {e}")
            return None

    def edit_group_message(self):
        """Подготавливает сообщение группы к редактированию"""
        if hasattr(self, 'current_message_text') and self.current_group:
            # Ищем ID сообщения в базе данных
            message_id = self.find_group_message_id_in_database(self.current_message_text)

            if not message_id:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Предупреждение",
                    "Не удалось найти сообщение в базе данных."
                )
                return

            # Копируем текст сообщения в строку ввода
            # Удаляем пометку "(изменено)" если она есть
            clean_text = self.current_message_text.replace(" (изменено)", "")
            self.message_input.setText(clean_text)
            self.message_input.setFocus()

            # Сохраняем информацию о том, что мы редактируем сообщение группы
            self.is_editing_group = True
            self.editing_header_block = self.current_selected_header_block
            self.editing_message_block = self.current_selected_message_block
            self.editing_message_text = self.current_message_text
            self.editing_message_id = message_id

            # Изменяем кнопку отправки, чтобы показать, что мы в режиме редактирования
            self.send_btn.setStyleSheet("background-color: #4CAF50; border-radius: 15px;")

            # Отключаем кнопку вложения во время редактирования
            self.attach_btn.setEnabled(False)

            # Создаем кнопку отмены редактирования, если её еще нет
            if not hasattr(self, 'cancel_edit_btn'):
                self.cancel_edit_btn = QtWidgets.QPushButton()
                self.cancel_edit_btn.setFixedSize(50, 50)
                self.cancel_edit_btn.setStyleSheet("background-color: #e74c3c; border-radius: 15px;")
                cancel_layout = QtWidgets.QVBoxLayout(self.cancel_edit_btn)
                cancel_layout.setContentsMargins(5, 5, 5, 5)
                cancel_icon = QtWidgets.QLabel("✕")
                cancel_icon.setAlignment(QtCore.Qt.AlignCenter)
                cancel_icon.setFont(QtGui.QFont("Arial", 20))
                cancel_layout.addWidget(cancel_icon)
                self.cancel_edit_btn.clicked.connect(self.cancel_editing)
                self.bottom_bar_layout.insertWidget(self.bottom_bar_layout.count() - 1, self.cancel_edit_btn)
            else:
                self.cancel_edit_btn.show()

    def edit_message(self):
        """Подготавливает сообщение к редактированию, копируя его в строку ввода"""
        if hasattr(self, 'current_message_text'):
            # Ищем ID сообщения в базе данных
            message_id = self.find_message_id_in_database(self.current_message_text)

            if not message_id:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Предупреждение",
                    "Не удалось найти сообщение в базе данных."
                )
                return

            # Копируем текст сообщения в строку ввода
            # Удаляем пометку "(изменено)" если она есть
            clean_text = self.current_message_text.replace(" (изменено)", "")
            self.message_input.setText(clean_text)
            self.message_input.setFocus()

            # Сохраняем информацию о том, что мы редактируем сообщение
            self.is_editing = True
            self.editing_header_block = self.current_selected_header_block
            self.editing_message_block = self.current_selected_message_block
            self.editing_message_text = self.current_message_text
            self.editing_message_id = message_id

            # Изменяем кнопку отправки, чтобы показать, что мы в режиме редактирования
            self.send_btn.setStyleSheet("background-color: #4CAF50; border-radius: 15px;")

            # Отключаем кнопку вложения во время редактирования
            self.attach_btn.setEnabled(False)

            # Создаем кнопку отмены редактирования, если её еще нет
            if not hasattr(self, 'cancel_edit_btn'):
                self.cancel_edit_btn = QtWidgets.QPushButton()
                self.cancel_edit_btn.setFixedSize(50, 50)
                self.cancel_edit_btn.setStyleSheet("background-color: #e74c3c; border-radius: 15px;")
                cancel_layout = QtWidgets.QVBoxLayout(self.cancel_edit_btn)
                cancel_layout.setContentsMargins(5, 5, 5, 5)
                cancel_icon = QtWidgets.QLabel("✕")
                cancel_icon.setAlignment(QtCore.Qt.AlignCenter)
                cancel_icon.setFont(QtGui.QFont("Arial", 20))
                cancel_layout.addWidget(cancel_icon)
                self.cancel_edit_btn.clicked.connect(self.cancel_editing)
                self.bottom_bar_layout.insertWidget(self.bottom_bar_layout.count() - 1, self.cancel_edit_btn)
            else:
                self.cancel_edit_btn.show()

    def cancel_editing(self):
        """Отменяет редактирование сообщения"""
        if hasattr(self, 'is_editing') and self.is_editing:
            # Сбрасываем режим редактирования
            self.is_editing = False
            self.send_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")
            self.attach_btn.setEnabled(True)
            self.message_input.clear()

            # Скрываем кнопку отмены
            if hasattr(self, 'cancel_edit_btn'):
                self.cancel_edit_btn.hide()

            # Очищаем сохраненные блоки
            if hasattr(self, 'editing_header_block'):
                delattr(self, 'editing_header_block')
            if hasattr(self, 'editing_message_block'):
                delattr(self, 'editing_message_block')

    def open_create_group_dialog(self):
        """Открывает диалог создания новой группы"""
        if self.connection:
            from create_group_dialog import CreateGroupDialog

            dialog = CreateGroupDialog(self.connection, self.username, self)
            dialog.group_created.connect(self.on_group_created)
            dialog.exec_()

    def delete_group_message(self):
        """Удаляет выбранное сообщение группы"""
        # Запрашиваем подтверждение
        reply = QtWidgets.QMessageBox.question(
            self,
            'Подтверждение',
            'Вы уверены, что хотите удалить это сообщение?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes and self.current_group:
            try:
                # Получаем текст сообщения
                message_text = self.current_message_text

                # Ищем ID сообщения в базе данных
                message_id = self.find_group_message_id_in_database(message_text)

                if message_id:
                    # Отправляем команду удаления на сервер
                    delete_command = f"GROUP_DELETE_MESSAGE:{self.current_group['id']}:{self.username}:{message_id}"
                    self.client.group_client.send(f"{delete_command}\n".encode('utf-8'))

                    # Обновляем отображение чата
                    QtCore.QTimer.singleShot(500, self.refresh_group_chat)
                else:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Предупреждение",
                        "Не удалось найти сообщение в базе данных."
                    )

            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Ошибка",
                    f"Не удалось удалить сообщение: {str(e)}"
                )

    def on_group_created(self, group_data):
        """Обработчик создания новой группы"""
        print(f"[GROUP] Created new group: {group_data['name']}")

        # Загружаем и отображаем созданные группы
        # Убираем дублирующий вызов load_user_groups()
        self.load_user_groups()

        # Показать уведомление
        QtWidgets.QMessageBox.information(
            self,
            "Группа создана",
            f"Группа '{group_data['name']}' успешно создана!\nСсылка для приглашения: {group_data['invite_link']}"
        )

    def add_group_button(self, group_data):
        """Добавляет кнопку группы в правую панель"""
        group_btn = QtWidgets.QPushButton()
        group_btn.setFixedSize(60, 60)
        group_btn.setStyleSheet("background-color: #d9d9d9; border-radius: 15px; border: 2px solid #999;")
        group_btn.setToolTip(f"{group_data['name']}\nРоль: {group_data['role']}")

        # Сохраняем данные группы в кнопке для последующего удаления
        group_btn.group_data = group_data

        group_layout = QtWidgets.QVBoxLayout(group_btn)
        group_layout.setContentsMargins(5, 5, 5, 5)

        if group_data['avatar_path'] and os.path.exists(group_data['avatar_path']):
            # Загружаем аватар группы
            pixmap = QtGui.QPixmap(group_data['avatar_path'])
            if not pixmap.isNull():
                pixmap = pixmap.scaled(50, 50, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

                # Создаем круглую маску
                mask = QtGui.QPixmap(50, 50)
                mask.fill(QtCore.Qt.transparent)
                painter = QtGui.QPainter(mask)
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setBrush(QtCore.Qt.white)
                painter.drawEllipse(0, 0, 50, 50)
                painter.end()

                # Применяем маску
                rounded_pixmap = QtGui.QPixmap(pixmap.size())
                rounded_pixmap.fill(QtCore.Qt.transparent)
                painter = QtGui.QPainter(rounded_pixmap)
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
                painter.drawPixmap(0, 0, mask)
                painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
                painter.drawPixmap(0, 0, pixmap)
                painter.end()

                group_icon = QtWidgets.QLabel()
                group_icon.setPixmap(rounded_pixmap)
                group_icon.setAlignment(QtCore.Qt.AlignCenter)
                group_layout.addWidget(group_icon)
        else:
            # Используем стандартную иконку
            group_icon = QtWidgets.QLabel("👥")
            group_icon.setAlignment(QtCore.Qt.AlignCenter)
            group_icon.setFont(QtGui.QFont("Arial", 20))
            group_layout.addWidget(group_icon)

        # Более безопасный поиск позиции кнопки "+"
        add_btn_index = -1
        if hasattr(self, 'add_server_btn'):
            for i in range(self.right_sidebar_layout.count()):
                item = self.right_sidebar_layout.itemAt(i)
                if item and item.widget() == self.add_server_btn:
                    add_btn_index = i
                    break

        if add_btn_index >= 0:
            self.right_sidebar_layout.insertWidget(add_btn_index, group_btn)
        else:
            # Если кнопка "+" не найдена, добавляем в конец
            self.right_sidebar_layout.addWidget(group_btn)

        # Подключаем обработчик клика
        group_btn.clicked.connect(lambda: self.open_group_chat(group_data))

    def open_group_chat(self, group_data):
        """Открывает чат группы и закрывает личный чат"""
        print(f"[GROUP] Opening group chat: {group_data['name']}")

        # Закрываем личный чат при открытии группового
        if self.current_chat_with:
            print(f"[CHAT] Closing personal chat with {self.current_chat_with} to open group chat")
            self.current_chat_with = None

        # Переключаемся на экран чата
        if self.content_stack.currentIndex() == 0:
            self.content_stack.setCurrentIndex(1)

        # Покидаем предыдущую группу, если была открыта
        if self.current_group and self.current_group['id'] != group_data['id']:
            self.client.leave_group_chat(self.current_group['id'])

        # Устанавливаем текущую группу
        self.current_group = group_data

        # Присоединяемся к групповому чату
        self.client.join_group_chat(group_data['id'])

        # Обновляем заголовок чата
        self.update_chat_header_for_group(group_data)

        # Очищаем текстовое поле и загружаем сообщения группы
        self.text_display.clear()
        self.load_group_messages(group_data['id'])

        self.setWindowTitle(f"Группа: {group_data['name']}")

    def load_group_messages(self, group_id):
        """Загружает сообщения группы"""
        if not self.connection:
            return

        try:
            cursor = self.connection.cursor()

            # Получаем сообщения группы
            cursor.execute(
                """
                SELECT sender, content, timestamp, edited, deleted
                FROM group_messages
                WHERE group_id = %s
                ORDER BY timestamp ASC
                """,
                (group_id,)
            )

            messages = cursor.fetchall()
            cursor.close()

            # Отображаем сообщения
            for msg in messages:
                sender, content, timestamp, edited, deleted = msg

                # Если сообщение удалено, заменяем содержимое
                if deleted:
                    content = "Сообщение удалено"
                elif edited and not "(изменено)" in content:
                    content = f"{content} (изменено)"

                # Создаем временное сообщение в формате "sender: content"
                temp_message = f"{sender}: {content}"
                formatted_message = self.format_chat_message(temp_message, timestamp)
                self.text_display.append(formatted_message)

            # Прокручиваем до конца после загрузки всех сообщений группы
            self.text_display.verticalScrollBar().setValue(
                self.text_display.verticalScrollBar().maximum()
            )

        except Exception as e:
            print(f"[ERROR] Failed to load group messages: {e}")
            self.text_display.append(f"<div style='color: red;'>Ошибка при загрузке сообщений группы: {str(e)}</div>")

    def update_chat_header_for_group(self, group_data):
        """Обновляет заголовок чата для группы (уже существующий метод)"""
        # Очищаем текущий макет заголовка
        while self.chat_header_layout.count():
            item = self.chat_header_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Создаем новый макет для заголовка группы
        self.chat_header = QtWidgets.QLabel(f"👥 {group_data['name']}")
        self.chat_header.setAlignment(QtCore.Qt.AlignCenter)
        self.chat_header.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
        self.chat_header.setStyleSheet("color: #333333;")

        # Добавляем кнопку поиска для групп
        self.header_search_btn = QtWidgets.QPushButton("🔍")
        self.header_search_btn.setFixedSize(30, 30)
        self.header_search_btn.setFont(QtGui.QFont("Arial", 12))
        self.header_search_btn.setStyleSheet("background: transparent; border: none;")
        self.header_search_btn.setToolTip("Поиск по сообщениям группы")
        self.header_search_btn.clicked.connect(self.toggle_search_bar)

        # Добавляем кнопку настроек группы
        self.group_settings_btn = QtWidgets.QPushButton("⚙️")
        self.group_settings_btn.setFixedSize(30, 30)
        self.group_settings_btn.setFont(QtGui.QFont("Arial", 12))
        self.group_settings_btn.setStyleSheet("background: transparent; border: none;")
        self.group_settings_btn.setToolTip("Настройки группы")
        self.group_settings_btn.clicked.connect(lambda: self.open_group_settings(group_data))

        # Добавляем элементы в макет заголовка
        self.chat_header_layout.addWidget(self.group_settings_btn)
        self.chat_header_layout.addStretch()
        self.chat_header_layout.addWidget(self.chat_header)
        self.chat_header_layout.addStretch()
        self.chat_header_layout.addWidget(self.header_search_btn)

        self.chat_header_panel.show()
        # Проверяем, есть ли активный групповой звонок
        group_id = group_data['id']
        if group_id in self.group_call_status and self.group_call_status[group_id]['active']:
            # Делаем кнопку звонка зеленой
            self.call_btn.setStyleSheet("background-color: #4CAF50; border-radius: 15px;")
        else:
            # Обычный цвет кнопки
            self.call_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")

    def open_group_settings(self, group_data):
        """Открывает диалог настроек группы"""
        if self.connection:
            dialog = GroupSettingsDialog(self.connection, self.username, group_data, self)
            dialog.group_updated.connect(self.on_group_updated)
            dialog.group_deleted.connect(self.on_group_deleted)
            # Подключаем обработчик выхода из группы
            dialog.group_left.connect(self.on_group_left)
            dialog.exec_()

    def on_group_left(self, group_id):
        """Обработчик выхода из группы"""
        print(f"[GROUP] Left group: {group_id}")

        # Если покинутая группа была открыта, закрываем чат
        if self.current_group and self.current_group['id'] == group_id:
            self.close_current_chat()
            self.current_group = None

        # Перезагружаем список групп
        self.load_user_groups()

        # Показываем уведомление
        QtWidgets.QMessageBox.information(
            self,
            "Выход из группы",
            "Вы успешно покинули группу."
        )

    def on_group_updated(self, updated_group_data):
        """Обработчик обновления группы"""
        print(f"[GROUP] Group updated: {updated_group_data['name']}")

        # Обновляем текущую группу, если она открыта
        if self.current_group and self.current_group['id'] == updated_group_data['id']:
            self.current_group = updated_group_data
            self.update_chat_header_for_group(updated_group_data)

        # Перезагружаем список групп
        self.load_user_groups()

    def on_group_deleted(self, group_id):
        """Обработчик удаления группы"""
        print(f"[GROUP] Group deleted: {group_id}")

        # Если удаленная группа была открыта, закрываем чат
        if self.current_group and self.current_group['id'] == group_id:
            self.close_current_chat()
            self.current_group = None

        # Перезагружаем список групп
        self.load_user_groups()

    def handle_group_screen_start_safe(self, sender, group_id):
        """обработчик начала групповой демонстрации в главном потоке"""
        try:
            print(f"[GROUP SCREEN SAFE] Handling screen start from {sender} for group {group_id}")

            # Проверяем, что это текущая группа
            if not self.current_group or self.current_group['id'] != group_id:
                print(f"[GROUP SCREEN SAFE] Not our current group: {group_id}")
                return

            # Проверяем, что это не мы сами
            if sender == self.username:
                print(f"[GROUP SCREEN SAFE] Ignoring our own screen sharing signal")
                return

            # Показываем уведомление в чате
            self.display_message(f"Система: {sender} начал(а) демонстрацию экрана в группе")

            # Закрываем предыдущее окно, если оно есть
            if hasattr(self, 'group_screen_window') and self.group_screen_window:
                self.group_screen_window.close()
                self.group_screen_window = None

            # Создаем окно в главном потоке
            from screen_sharing_window import ScreenSharingWindow
            self.group_screen_window = ScreenSharingWindow(
                self.username,
                f"Группа: {self.current_group['name']} - Демонстрация от {sender}",
                is_sender=False,
                parent=self
            )

            # Правильно настраиваем для группового приема
            self.group_screen_window.setup_group_receiving(group_id, sender)

            # Получаем сокет для демонстрации экрана и настраиваем прием
            if hasattr(self.client, 'get_screen_socket'):
                screen_socket = self.client.get_screen_socket()
                if screen_socket:
                    self.group_screen_window.receive_sharing(screen_socket)
                    print(f"[GROUP SCREEN SAFE] Set up screen socket for receiving")
                else:
                    print(f"[GROUP SCREEN SAFE] No screen socket available")

            self.group_screen_window.show()
            print(f"[GROUP SCREEN SAFE] Created and showed viewing window for {sender}")

        except Exception as e:
            print(f"[GROUP SCREEN SAFE ERROR] Error in safe handler: {e}")
            import traceback
            traceback.print_exc()

    def handle_group_screen_stop_safe(self, sender, group_id):
        """обработчик остановки групповой демонстрации в главном потоке"""
        try:
            print(f"[GROUP SCREEN SAFE] Stopping screen sharing from {sender} for group {group_id}")

            # Показываем уведомление в чате
            self.display_message(f"Система: {sender} завершил(а) демонстрацию экрана в группе")

            # Закрываем окно демонстрации экрана
            if self.group_screen_window:
                self.group_screen_window.close()
                self.group_screen_window = None
                print(f"[GROUP SCREEN SAFE] Closed viewing window for {sender}")

        except Exception as e:
            print(f"[GROUP SCREEN ERROR] Error in safe stop handler: {e}")

    def handle_group_screen_data_safe(self, message):
        """обработчик данных групповой демонстрации в главном потоке"""
        try:
            if self.group_screen_window and hasattr(self.group_screen_window, 'process_group_screen_data'):
                self.group_screen_window.process_group_screen_data(message)
        except Exception as e:
            print(f"[GROUP SCREEN ERROR] Error handling data safely: {e}")

    def delete_message(self):
        """Удаляет выбранное сообщение"""
        # Запрашиваем подтверждение
        reply = QtWidgets.QMessageBox.question(
            self,
            'Подтверждение',
            'Вы уверены, что хотите удалить это сообщение?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            try:
                # Получаем текст сообщения
                message_text = self.current_message_text

                # Ищем ID сообщения в базе данных
                message_id = self.find_message_id_in_database(message_text)

                if message_id:
                    # Обновляем сообщение в БД
                    cursor = self.connection.cursor()
                    cursor.execute(
                        "UPDATE messages SET content = %s WHERE id = %s",
                        ("Сообщение удалено", message_id)
                    )
                    self.connection.commit()
                    cursor.close()

                    # Отправляем уведомление об удалении на сервер для синхронизации с другими клиентами
                    delete_notification = f"DELETE_MESSAGE:{self.username}:{self.current_chat_with}:{message_id}"
                    self.client.send_message(delete_notification)

                    # Обновляем отображение чата
                    self.refresh_chat()
                else:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Предупреждение",
                        "Не удалось найти сообщение в базе данных."
                    )

            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Ошибка",
                    f"Не удалось удалить сообщение: {str(e)}"
                )

    def refresh_group_chat(self):
        """Обновляет отображение группового чата"""
        if not self.current_group or not self.connection:
            return

        try:
            print(f"[DEBUG] Refreshing group chat for group {self.current_group['id']}")

            # Очищаем текстовое поле
            self.text_display.clear()

            # Загружаем сообщения группы заново
            self.load_group_messages(self.current_group['id'])
        except Exception as e:
            print(f"[ERROR] Error refreshing group chat: {e}")

    def refresh_chat_safe(self):
        """Безопасно обновляет чат в UI потоке"""
        if not self.current_chat_with or not self.connection:
            return

        try:
            # Очищаем текущее отображение
            self.text_display.clear()

            cursor = self.connection.cursor()

            # Получаем сообщения для текущего чата
            cursor.execute(
                """
                SELECT id, sender, content, timestamp, edited, deleted, is_deleted 
                FROM messages 
                WHERE (sender = %s AND receiver = %s) OR (sender = %s AND receiver = %s)
                ORDER BY timestamp ASC
                """,
                (self.username, self.current_chat_with, self.current_chat_with, self.username)
            )
            messages = cursor.fetchall()

            # Получаем информацию о звонках
            cursor.execute(
                """
                SELECT caller, recipient, duration, end_time
                FROM call_logs
                WHERE (caller = %s AND recipient = %s) OR (caller = %s AND recipient = %s)
                ORDER BY end_time ASC
                """,
                (self.username, self.current_chat_with, self.current_chat_with, self.username)
            )
            call_logs = cursor.fetchall()

            # Закрываем курсор базы данных после выполнения всех запросов
            cursor.close()

            # Объединяем обычные сообщения и информацию о звонках
            all_messages = []

            for msg in messages:
                msg_id, sender, content, timestamp, edited, deleted, is_deleted = msg

                # Если сообщение удалено, заменяем его содержимое
                if deleted or is_deleted:
                    content = "Сообщение удалено"
                # Если сообщение отредактировано и не содержит пометку, добавляем её
                elif edited and not "(изменено)" in content:
                    content = f"{content} (изменено)"

                # Убедимся, что timestamp является offset-naive
                if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is not None:
                    timestamp = timestamp.replace(tzinfo=None)

                all_messages.append((msg_id, sender, content, timestamp))

            for log in call_logs:
                caller, recipient, duration, end_time = log
                # Убедимся, что end_time является offset-naive
                if hasattr(end_time, 'tzinfo') and end_time.tzinfo is not None:
                    end_time = end_time.replace(tzinfo=None)

                minutes = duration // 60
                seconds = duration % 60
                duration_str = f"{minutes:02d}:{seconds:02d}"
                formatted_time = end_time.strftime("%H:%M") if hasattr(end_time, "strftime") else "00:00"

                # Определяем, кто с кем разговаривал
                if caller == self.username:
                    call_message = f"Звонок с {recipient} завершен в {formatted_time}. Длительность: {duration_str}"
                else:
                    call_message = f"Звонок с {caller} завершен в {formatted_time}. Длительность: {duration_str}"

                all_messages.append((None, "Система", call_message, end_time))

            # Сортируем все сообщения по времени
            all_messages.sort(key=lambda x: x[3] if x[3] is not None else datetime.datetime.min)

            # Отображаем все сообщения
            for msg in all_messages:
                msg_id, sender, content, timestamp = msg
                # Создаем временное сообщение в формате "sender: content"
                temp_message = f"{sender}: {content}"
                # Передаем timestamp в метод format_chat_message
                formatted_message = self.format_chat_message(temp_message, timestamp)
                self.text_display.append(formatted_message)

                # Сохраняем ID сообщения в блоке для последующего редактирования/удаления
                if msg_id is not None:
                    # Находим последний добавленный блок
                    text_cursor = self.text_display.textCursor()
                    text_cursor.movePosition(QtGui.QTextCursor.End)
                    block = text_cursor.block()

                    # Создаем класс для хранения данных сообщения
                    class MessageData(QtGui.QTextBlockUserData):
                        def __init__(self, message_id):
                            super().__init__()
                            self.message_id = message_id

                    # Сохраняем ID сообщения в свойствах блока
                    block.setUserData(MessageData(msg_id))

            # Прокручиваем до конца после загрузки всех сообщений
            self.text_display.verticalScrollBar().setValue(
                self.text_display.verticalScrollBar().maximum()
            )

        except Exception as e:
            print(f"[ERROR] Ошибка при обновлении чата: {e}")
            self.text_display.append(f"<div style='color: red;'>Ошибка при загрузке сообщений: {str(e)}</div>")

    def refresh_chat(self):
        """Обновляет отображение чата, безопасно для многопоточности"""
        # Эмитируем сигнал для обновления чата в UI потоке
        self.refresh_chat_signal.emit()

    # Добавляем метод для переключения видимости панели поиска
    def toggle_search_bar(self):
        """Показывает или скрывает панель поиска"""
        if self.search_bar.isVisible():
            self.search_bar.hide()
            # Очищаем выделения при скрытии панели поиска
            self.search_bar.clear_highlights()
        else:
            # Показываем панель поиска если есть активный чат (личный или групповой)
            if self.current_chat_with or self.current_group:
                self.search_bar.show()
                self.search_bar.search_input.setFocus()
                self.search_bar.search_input.clear()
            else:
                # Если нет активного чата, показываем сообщение
                QtWidgets.QMessageBox.information(
                    self,
                    "Поиск недоступен",
                    "Для поиска необходимо открыть чат с пользователем или группу."
                )

    def update_ui(self, action, data):
        print(f"[UI] Updating UI: {action} with data: {data}")
        if action == "group_excluded":
            group_name, group_id = data
            self.handle_group_exclusion(group_name, group_id)
        if action == "incoming_call":
            self.show_incoming_call(data)
        elif action == "outgoing_call":
            self.show_outgoing_call(data)
        elif action == "call_accepted":
            self.call_accepted(data)
        elif action == "call_rejected":
            self.call_rejected(data)
        elif action == "call_ended":
            sender, duration = data
            self.call_ended(int(duration))
        elif action == "incoming_message":
            sender, content = data
            self.handle_incoming_message(sender, content)
        elif action == "display_message":
            self.display_message(data)
        elif action == "screen_share_start":
            self.start_screen_sharing_receiver(data)
        elif action == "screen_share_stop":
            self.stop_screen_sharing_receiver()
        elif action == "screen_data":
            self.process_screen_data(data)

    def handle_group_exclusion(self, group_name, group_id):
        """Обрабатывает исключение пользователя из группы"""
        print(f"[GROUP EXCLUSION] Excluded from group: {group_name} (ID: {group_id})")

        # Если исключенная группа была открыта, закрываем чат
        if self.current_group and self.current_group['id'] == group_id:
            self.close_current_chat()
            self.current_group = None

        # Обновляем список групп
        self.load_user_groups()

        # Показываем уведомление пользователю
        QtWidgets.QMessageBox.warning(
            self,
            "Исключение из группы",
            f"Вы были исключены из группы '{group_name}'"
        )

    def handle_group_call_button(self):
        """Обработка нажатия кнопки группового звонка"""
        if not self.current_group:
            return

        group_id = self.current_group['id']

        # Проверяем, есть ли активный групповой звонок
        if group_id in self.group_call_status and self.group_call_status[group_id]['active']:
            # Присоединяемся к существующему звонку
            self.join_group_call()
        else:
            # Начинаем новый групповой звонок
            self.start_group_call()

    def handle_group_screen_start(self, sender, group_id):
        """Обрабатывает начало групповой демонстрации экрана"""
        try:
            print(f"[GROUP SCREEN] Handling screen start from {sender} for group {group_id}")

            # Проверяем, что это текущая группа
            if not self.current_group or self.current_group['id'] != group_id:
                print(f"[GROUP SCREEN] Not our current group: {group_id}")
                return

            # Проверяем, что это не мы сами
            if sender == self.username:
                print(f"[GROUP SCREEN] Ignoring our own screen sharing signal")
                return

            # Показываем уведомление в чате
            self.display_message(f"Система: {sender} начал(а) демонстрацию экрана в группе")

            # Создаем окно для просмотра демонстрации экрана
            if not hasattr(self, 'group_screen_window') or not self.group_screen_window:
                from screen_sharing_window import ScreenSharingWindow
                self.group_screen_window = ScreenSharingWindow(
                    self.username,
                    f"Группа: {self.current_group['name']} - Демонстрация от {sender}",
                    is_sender=False,
                    parent=self
                )

                # Настраиваем окно для приема групповой демонстрации
                self.group_screen_window.setup_group_receiving(group_id, sender)

                # Получаем сокет для демонстрации экрана
                if hasattr(self.client, 'get_screen_socket'):
                    screen_socket = self.client.get_screen_socket()
                    if screen_socket:
                        self.group_screen_window.receive_sharing(screen_socket)

                self.group_screen_window.show()
                print(f"[GROUP SCREEN] Created viewing window for {sender}")
        except Exception as e:
            print(f"[GROUP SCREEN ERROR] Error in handle_group_screen_start: {e}")
            import traceback
            traceback.print_exc()

    def handle_group_screen_stop(self, sender, group_id):
        """Обрабатывает остановку групповой демонстрации экрана"""
        try:
            print(f"[GROUP SCREEN] Stopping screen sharing from {sender} for group {group_id}")

            # Закрываем окно демонстрации экрана
            if hasattr(self, 'group_screen_window') and self.group_screen_window:
                self.group_screen_window.close()
                self.group_screen_window = None
                print(f"[GROUP SCREEN] Closed viewing window for {sender}")

        except Exception as e:
            print(f"[GROUP SCREEN ERROR] Error in handle_group_screen_stop: {e}")

    def start_group_call(self):
        """метод запуска группового звонка"""
        if not self.current_group:
            return

        group_id = self.current_group['id']

        # Отправляем сигнал о начале группового звонка через основной сокет
        signal = f"GROUP_CALL_SIGNAL:start:{group_id}:{self.username}:{time.time()}"
        self.client.send_message(signal)

        # Создаем диалог группового звонка
        self.group_call_dialog = GroupCallDialog(
            self.current_group,
            self.username,
            self.client,
            self
        )
        self.group_call_dialog.is_in_call = True
        self.group_call_dialog.show()

        # Запускаем групповое аудио через отдельный сокет
        self.client.start_group_call_audio(group_id)

        print(f"[GROUP CALL] Started group call in {self.current_group['name']} via port 5558")

    def join_group_call(self):
        """метод присоединения к групповому звонку"""
        if not self.current_group:
            return

        group_id = self.current_group['id']

        # Отправляем сигнал о присоединении к звонку
        signal = f"GROUP_CALL_SIGNAL:join:{group_id}:{self.username}:{time.time()}"
        self.client.send_message(signal)

        # Создаем диалог группового звонка
        self.group_call_dialog = GroupCallDialog(
            self.current_group,
            self.username,
            self.client,
            self
        )
        self.group_call_dialog.is_in_call = True

        # Обновляем список участников
        if group_id in self.group_call_status:
            participants = self.group_call_status[group_id]['participants']
            self.group_call_dialog.update_participants(participants)

        self.group_call_dialog.show()

        # Запускаем групповое аудио
        self.client.start_group_call_audio(group_id)

        print(f"[GROUP CALL] Joined group call in {self.current_group['name']}")

    def handle_group_call_status(self, message):
        """функция обработки статуса группового звонка"""
        try:
            # Формат: GROUP_CALL_STATUS:group_id:status:participants
            parts = message.split(':', 3)
            if len(parts) < 4:
                return

            group_id = int(parts[1])
            status = parts[2]  # active/inactive
            participants_str = parts[3]

            print(f"[GROUP CALL STATUS] Group {group_id}: {status}, participants: {participants_str}")

            if status == "active":
                participants = participants_str.split(',') if participants_str else []
                self.group_call_status[group_id] = {
                    'active': True,
                    'participants': participants
                }

                # Обновляем кнопку звонка в группе (делаем зеленой)
                if self.current_group and self.current_group['id'] == group_id:
                    self.call_btn.setStyleSheet("background-color: #4CAF50; border-radius: 15px;")
                    print(f"[GROUP CALL] Set call button GREEN for active call in group {group_id}")

                # Если у нас открыт диалог группового звонка, обновляем участников
                if self.group_call_dialog and self.group_call_dialog.is_in_call:
                    self.group_call_dialog.update_participants(participants)

            else:  # inactive
                #  Удаляем статус звонка
                if group_id in self.group_call_status:
                    del self.group_call_status[group_id]

                # Возвращаем обычный цвет кнопки звонка для ВСЕХ групп
                if self.current_group and self.current_group['id'] == group_id:
                    self.call_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")
                    print(f"[GROUP CALL] Set call button WHITE for inactive call in group {group_id}")

                # Закрываем диалог группового звонка, если он открыт для этой группы
                if (self.group_call_dialog and
                        hasattr(self.group_call_dialog, 'group_data') and
                        self.group_call_dialog.group_data['id'] == group_id):
                    self.group_call_dialog.close()
                    self.group_call_dialog = None
                    print(f"[GROUP CALL] Closed group call dialog for group {group_id}")

        except Exception as e:
            print(f"[GROUP CALL ERROR] Error handling status: {e}")


    def start_screen_sharing_receiver(self, sender):
        """Начинает прием демонстрации экрана"""
        # Закрываем предыдущее окно, если оно существует
        if self.screen_sharing_window:
            self.screen_sharing_window.close()
            self.screen_sharing_window = None

        # Создаем окно для приема демонстрации
        self.screen_sharing_window = ScreenSharingWindow(
            self.username,
            sender,
            is_sender=False,
            parent=self
        )
        self.screen_sharing_window.receive_sharing(self.client.get_screen_socket())
        self.screen_sharing_window.show()

        # Отображаем сообщение в чате
        self.display_message(f"Система: {sender} начал(а) демонстрацию экрана")

    def stop_screen_sharing_receiver(self):
        """Останавливает прием демонстрации экрана"""
        if self.screen_sharing_window:
            self.screen_sharing_window.close()
            self.screen_sharing_window = None

        # Отображаем сообщение в чате
        self.display_message(f"Система: Демонстрация экрана завершена")

    def process_screen_data(self, data):
        """Обрабатывает полученные данные экрана"""
        if self.screen_sharing_window and not self.screen_sharing_window.is_sender:
            # Передаем данные в окно демонстрации
            try:
                # Извлекаем бинарные данные из строки
                if data.startswith("SCREEN_DATA_COMPLETE:"):
                    screen_data = data[21:]  # Убираем префикс "SCREEN_DATA_COMPLETE:"
                    self.screen_sharing_window.process_screen_data(screen_data)
                elif data.startswith("SCREEN_DATA:"):
                    screen_data = data[12:]  # Убираем префикс "SCREEN_DATA:"
                    self.screen_sharing_window.process_screen_data(screen_data)
            except Exception as e:
                print(f"[SCREEN ERROR] Error processing screen data: {e}")

    def open_friends_dialog(self):
        """Открывает диалог управления друзьями"""
        if self.connection:
            dialog = FriendsDialog(self.connection, self.username, self)
            dialog.friendsUpdated.connect(self.load_friends)
            dialog.exec_()

    def handle_call_ended(self, duration):
        if self.client.is_in_call:
            self.client.end_call(duration)
            self.call_ended(duration)

    def call_ended(self, duration=0):
        if self.call_dialog:
            self.call_dialog.close()
            self.call_dialog = None
        self.call_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")
        self.client.is_in_call = False

        # Закрываем окно демонстрации экрана при завершении звонка
        if self.screen_sharing_window:
            self.screen_sharing_window.close()
            self.screen_sharing_window = None

    def handle_message(self, message):
        # Добавить в начало метода handle_message:
        if message.startswith("STATUS_RESPONSE:"):
            parts = message.split(":", 2)
            if len(parts) >= 3:
                username = parts[1]
                status = parts[2]
                self.update_user_status(username, status)
            return

        if message.startswith("STATUS_UPDATE:"):
            parts = message.split(":", 2)
            if len(parts) >= 3:
                username = parts[1]
                status = parts[2]
                self.update_user_status(username, status)
            return

        # Убираем обработку сообщений о входе/выходе из сети
        if ": в сети" in message or ": вышел из сети" in message:
            # Извлекаем имя пользователя и статус
            if ":" in message:
                parts = message.split(":", 1)
                username = parts[0].strip()
                content = parts[1].strip()

                if content == "в сети":
                    self.update_user_status(username, "online")
                elif content == "вышел из сети":
                    self.update_user_status(username, "offline")
            return  # Не отображаем эти сообщения в чате
        if message.startswith("GROUP_SCREEN_SIGNAL:"):
            parts = message.split(":", 4)
            if len(parts) >= 5:
                action = parts[1]
                group_id = int(parts[2])
                sender = parts[3]

                print(f"[GROUP SCREEN] Received signal: {action} from {sender} for group {group_id}")

                # Используем сигналы для безопасной работы с потоками
                if action == "start":
                    self.group_screen_start_signal.emit(sender, group_id)
                elif action == "stop":
                    self.group_screen_stop_signal.emit(sender, group_id)
            return
        elif message.startswith("GROUP_SCREEN_DATA_"):
            # Используем сигнал для безопасной передачи данных
            self.group_screen_data_signal.emit(message)
            return
        if message.startswith("GROUP_CALL_STATUS:"):
            self.handle_group_call_status(message)
            return
        if message.startswith("GROUP_SCREEN_DATA_START:") or message.startswith(
                "GROUP_SCREEN_DATA_CHUNK:") or message.startswith("GROUP_SCREEN_DATA_END:"):
            self.handle_group_screen_data(message)
        # Обработка групповых файлов
        if message.startswith("GROUP_FILE_TRANSFER:"):
            self.handle_group_file_transfer(message)
            return
        # Обработка групповых сообщений
        if message.startswith("GROUP_MESSAGE:"):
            self.handle_group_message(message)
            return
        elif message.startswith("GROUP_MESSAGE_EDITED:"):
            parts = message.split(":", 3)
            if len(parts) >= 4:
                group_id = int(parts[1])
                sender = parts[2]
                message_id = int(parts[3])

                print(f"[GROUP] Message {message_id} edited by {sender} in group {group_id}")

                # Обновляем отображение чата, если это текущая группа
                if self.current_group and self.current_group['id'] == group_id:
                    QtCore.QTimer.singleShot(500, self.refresh_group_chat)
            return
        elif message.startswith("GROUP_MESSAGE_DELETED:"):
            parts = message.split(":", 3)
            if len(parts) >= 4:
                group_id = int(parts[1])
                sender = parts[2]
                message_id = int(parts[3])

                print(f"[GROUP] Message {message_id} deleted by {sender} in group {group_id}")

                # Обновляем отображение чата, если это текущая группа
                if self.current_group and self.current_group['id'] == group_id:
                    QtCore.QTimer.singleShot(500, self.refresh_group_chat)
            return
        if message.startswith("GROUP_SCREEN_START:"):
            parts = message.split(":", 2)
            if len(parts) >= 3:
                group_id = int(parts[1])
                sender = parts[2]
                self.handle_group_screen_start(group_id, sender)
            return

        elif message.startswith("GROUP_SCREEN_STOP:"):
            parts = message.split(":", 2)
            if len(parts) >= 3:
                group_id = int(parts[1])
                sender = parts[2]
                self.handle_group_screen_stop(group_id, sender)
            return
        elif message.startswith("GROUP_JOINED:"):
            group_id = message.split(":", 1)[1]
            print(f"[GROUP] Successfully joined group {group_id}")
            return
        elif message.startswith("GROUP_LEFT:"):
            group_id = message.split(":", 1)[1]
            print(f"[GROUP] Successfully left group {group_id}")
            return

        # Остальная обработка сообщений
        # Обработка уведомлений об исключении из группы
        if message.startswith("GROUP_EXCLUDED:"):
            parts = message.split(":", 2)
            if len(parts) >= 3:
                group_name = parts[1]
                group_id = int(parts[2])
                self.update_ui_signal.emit("group_excluded", (group_name, group_id))
            return

        # Обработка сообщений передачи файлов
        if message.startswith("FILE_TRANSFER:"):
            parts = message.split(":", 4)
            if len(parts) < 5:
                print(f"[ОШИБКА] Неверный формат передачи файла: {message}")
                return

            action = parts[1]
            sender = parts[2]
            recipient = parts[3]

            # Обрабатываем только если мы получатель
            if recipient == self.username:
                if action == "START":
                    file_info = parts[4].split(":", 1)
                    file_name = file_info[0]
                    try:
                        file_size = int(file_info[1])
                    except ValueError:
                        print(f"[ОШИБКА] Неверный формат размера файла: {file_info[1]}")
                        file_size = 0

                    # Создаем временный файл для хранения входящих данных
                    self.incoming_file = {
                        "name": file_name,
                        "size": file_size,
                        "sender": sender,
                        "data": bytearray(),
                        "path": os.path.join("downloads", file_name)
                    }

                    # Убеждаемся, что директория downloads существует
                    os.makedirs("downloads", exist_ok=True)

                    # Уведомляем UI
                    self.update_ui_signal.emit("display_message",
                                               f"Система: Получение файла {file_name} от {sender}...")

                elif action == "CHUNK" and hasattr(self, "incoming_file"):
                    # Декодируем и добавляем часть файла
                    encoded_chunk = parts[4]
                    try:
                        # Удаляем все пробелы и переносы строк, которые могли появиться при передаче
                        encoded_chunk = encoded_chunk.replace(' ', '').replace('\n', '').replace('\r', '')

                        # Проверяем, что длина строки кратна 4, иначе дополняем символами '='
                        padding = 4 - (len(encoded_chunk) % 4) if len(encoded_chunk) % 4 != 0 else 0
                        encoded_chunk += '=' * padding

                        # Декодируем данные
                        try:
                            chunk_data = base64.b64decode(encoded_chunk)
                            self.incoming_file["data"].extend(chunk_data)
                        except Exception as e:
                            print(f"[ОШИБКА] Не удалось декодировать часть файла: {e}")
                            print(f"Длина части: {len(encoded_chunk)}, Первые 20 символов: {encoded_chunk[:20]}")
                    except Exception as e:
                        print(f"[ОШИБКА] Ошибка обработки части файла: {e}")

                elif action == "END" and hasattr(self, "incoming_file"):
                    file_name = parts[4]

                    # Убеждаемся, что директория downloads существует
                    os.makedirs("downloads", exist_ok=True)

                    try:
                        # Сохраняем полный файл
                        with open(self.incoming_file["path"], "wb") as f:
                            f.write(self.incoming_file["data"])

                        print(f"[ФАЙЛ] Сохранен файл {file_name} от {sender} в {self.incoming_file['path']}")

                        # Проверяем, является ли файл изображением
                        is_image = file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))

                        # Уведомляем UI
                        if is_image:
                            self.update_ui_signal.emit("display_message",
                                                       f"Система: Изображение {file_name} от {sender} получено")
                            # Отправляем сообщение о полученном изображении
                            self.update_ui_signal.emit("display_message",
                                                       f"{sender}: [Вложение: {file_name}]")

                            # Создаем уменьшенную копию изображения
                            self.create_scaled_image(self.incoming_file["path"])
                        else:
                            self.update_ui_signal.emit("display_message",
                                                       f"Система: Файл {file_name} от {sender} получен и сохранен в папке downloads")
                            # Отправляем сообщение о полученном файле
                            self.update_ui_signal.emit("display_message",
                                                       f"{sender}: [Файл получен: {file_name}]")
                    except Exception as e:
                        print(f"[ОШИБКА] Не удалось сохранить файл: {e}")
                        self.update_ui_signal.emit("display_message",
                                                   f"Система: Ошибка при сохранении файла {file_name}: {str(e)}")

                    # Очищаем
                    del self.incoming_file

            return

        # Обработка уведомлений о редактировании и удалении сообщений
        if message.startswith("Система: Пользователь") and (
                "отредактировал сообщение" in message or "удалил сообщение" in message):
            # Обновляем отображение чата, чтобы показать изменения
            # Используем сигнал для безопасного обновления UI
            self.refresh_chat_signal.emit()
            return

        if message.startswith("EDIT_MESSAGE:") or message.startswith("DELETE_MESSAGE:"):
            self.refresh_chat_signal.emit()
            return
        if message.startswith("INCOMING_CALL:"):
            caller = message.split(":", 1)[1]
            self.update_ui_signal.emit("incoming_call", caller)
        elif message.startswith("OUTGOING_CALL:"):
            recipient = message.split(":", 1)[1]
            self.update_ui_signal.emit("outgoing_call", recipient)
        elif message.startswith("CALL_ACCEPTED:"):
            recipient = message.split(":", 1)[1]
            self.update_ui_signal.emit("call_accepted", recipient)
        elif message.startswith("CALL_REJECTED:"):
            recipient = message.split(":", 1)[1]
            self.update_ui_signal.emit("call_rejected", recipient)
        elif message.startswith("CALL_ENDED:"):
            parts = message.split(":")
            sender = parts[1]
            duration = parts[2] if len(parts) > 2 else "0"
            self.update_ui_signal.emit("call_ended", (sender, duration))
        elif message.startswith("SCREEN_SHARE_START:"):
            sender = message.split(":", 1)[1]
            self.update_ui_signal.emit("screen_share_start", sender)
        elif message.startswith("SCREEN_SHARE_STOP:"):
            self.update_ui_signal.emit("screen_share_stop", None)
        elif message.startswith("SCREEN_DATA_COMPLETE:") or message.startswith("SCREEN_DATA:"):
            self.update_ui_signal.emit("screen_data", message)
        else:
            # Проверяем, является ли это сообщением от пользователя
            if ":" in message:
                parts = message.split(":", 1)
                sender = parts[0].strip()
                content = parts[1].strip()

                # Если это сообщение от другого пользователя, обрабатываем его
                if sender != self.username and sender != "Система":
                    self.update_ui_signal.emit("incoming_message", (sender, content))

            self.update_ui_signal.emit("display_message", message)

    def display_message(self, message):
        """Отображает сообщение в чате с улучшенной фильтрацией"""
        # УЛУЧШЕНО: Строгая проверка активного чата
        if not self.current_chat_with and not self.current_group:
            return

        # Убеждаемся, что одновременно активен только один тип чата
        if self.current_chat_with and self.current_group:
            print("[WARNING] Both personal and group chat active - prioritizing group")
            self.current_chat_with = None

        def auto_scroll():
            """Функция для автоматической прокрутки"""
            scrollbar = self.text_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            QtCore.QTimer.singleShot(10, lambda: scrollbar.setValue(scrollbar.maximum()))

        if ":" in message:
            parts = message.split(":", 1)
            sender = parts[0].strip()
            content = parts[1].strip()

            # Системные сообщения
            if sender == "Система":
                # Отображаем только если относится к текущему чату
                if (self.current_chat_with and (self.current_chat_with in content or self.username in content)) or \
                        (self.current_group and self.current_group['name'] in content):
                    formatted_message = self.format_chat_message(message)
                    self.text_display.append(formatted_message)
                    auto_scroll()
                    QtCore.QTimer.singleShot(50, auto_scroll)

            # Сообщения в личном чате
            elif self.current_chat_with and not self.current_group:
                if sender == self.current_chat_with or sender == self.username:
                    if sender == "Система" or sender == self.username or sender in self.friends:
                        formatted_message = self.format_chat_message(message)
                        self.text_display.append(formatted_message)
                        auto_scroll()
                        QtCore.QTimer.singleShot(50, auto_scroll)
                        if self.current_chat_with not in self.chat_initialized:
                            self.chat_initialized[self.current_chat_with] = True

            # Уведомления о новых сообщениях от друзей (только если нет активного чата с ними)
            elif sender != self.username and sender in self.friends:
                if sender != self.current_chat_with:
                    notification_message = f"Новое сообщение от {sender}: {content}"
                    print(f"[NOTIFICATION] {notification_message}")

                    if sender not in self.chat_initialized:
                        self.chat_initialized[sender] = True
        else:
            # Сообщения без формата "имя: содержание"
            if self.current_chat_with or self.current_group:
                formatted_message = self.format_chat_message(message)
                self.text_display.append(formatted_message)
                auto_scroll()
                QtCore.QTimer.singleShot(50, auto_scroll)

    def create_scaled_image(self, image_path):
        """Создает уменьшенную копию изображения и сохраняет ее в кэше"""
        try:
            # Проверяем, существует ли файл
            if not os.path.exists(image_path):
                print(f"[ОШИБКА] Файл не найден: {image_path}")
                return None

            # Создаем директорию для уменьшенных изображений, если она не существует
            scaled_dir = os.path.join("downloads", "scaled")
            os.makedirs(scaled_dir, exist_ok=True)

            # Формируем путь для уменьшенной копии
            file_name = os.path.basename(image_path)
            scaled_path = os.path.join(scaled_dir, f"scaled_{file_name}")

            # Проверяем, есть ли уже уменьшенная копия
            if os.path.exists(scaled_path):
                self.scaled_image_cache[image_path] = scaled_path
                return scaled_path

            # Загружаем изображение
            pixmap = QtGui.QPixmap(image_path)
            if pixmap.isNull():
                print(f"[ОШИБКА] Не удалось загрузить изображение: {image_path}")
                return None

            # Масштабируем изображение с сохранением пропорций
            scaled_pixmap = pixmap.scaled(
                self.max_image_width,
                self.max_image_height,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )

            # Сохраняем уменьшенную копию
            scaled_pixmap.save(scaled_path)

            # Добавляем в кэш
            self.scaled_image_cache[image_path] = scaled_path

            print(f"[ИЗОБРАЖЕНИЕ] Создана уменьшенная копия: {scaled_path}")
            return scaled_path

        except Exception as e:
            print(f"[ОШИБКА] Не удалось создать уменьшенную копию изображения: {e}")
            return None

    def get_scaled_image_path(self, original_path):
        """Возвращает путь к уменьшенной копии изображения"""
        # Проверяем, есть ли изображение в кэше
        if original_path in self.scaled_image_cache:
            return self.scaled_image_cache[original_path]

        # Если нет, создаем уменьшенную копию
        scaled_path = self.create_scaled_image(original_path)
        if scaled_path:
            return scaled_path

        # Если не удалось создать уменьшенную копию, возвращаем оригинальный путь
        return original_path

    def handle_group_screen_data(self, message):
        """обработка данных групповой демонстрации экрана"""
        try:
            print(f"[GROUP SCREEN CLIENT] Received data: {message[:100]}...")

            # Проверяем, есть ли окно для просмотра групповой демонстрации
            if not hasattr(self, 'group_screen_window') or not self.group_screen_window:
                print(f"[GROUP SCREEN CLIENT] No group screen window available")
                return

            # Проверяем формат сообщения
            if not message.startswith("GROUP_SCREEN_DATA_"):
                print(f"[GROUP SCREEN CLIENT] Invalid message format: {message[:50]}")
                return

            # Парсим сообщение для проверки группы
            parts = message.split(":", 3)
            if len(parts) >= 3:
                sender = parts[1]
                try:
                    group_id = int(parts[2])
                except ValueError:
                    print(f"[GROUP SCREEN CLIENT] Invalid group_id in message: {parts[2]}")
                    return

                # Проверяем, что это наша текущая группа
                if not self.current_group or self.current_group['id'] != group_id:
                    print(
                        f"[GROUP SCREEN CLIENT] Message for different group: {group_id} vs {self.current_group['id'] if self.current_group else 'None'}")
                    return

                # Проверяем, что это не мы сами
                if sender == self.username:
                    print(f"[GROUP SCREEN CLIENT] Ignoring own screen data")
                    return

                print(f"[GROUP SCREEN CLIENT] Processing data from {sender} for group {group_id}")

                # Передаем данные в окно демонстрации
                self.group_screen_window.process_group_screen_data(message)

            else:
                print(f"[GROUP SCREEN CLIENT] Invalid message format: {message}")

        except Exception as e:
            print(f"[GROUP SCREEN CLIENT ERROR] Error handling data: {e}")
            import traceback
            traceback.print_exc()

    def format_chat_message(self, message, timestamp=None):
        # Используем переданный timestamp или текущее время
        if timestamp is None:
            current_time = datetime.datetime.now().strftime("%H:%M")
            current_date = datetime.datetime.now().strftime("%d.%m.%Y")
        else:
            current_time = timestamp.strftime("%H:%M")
            current_date = timestamp.strftime("%d.%m.%Y")

        if ":" in message:
            parts = message.split(":", 1)
            username = parts[0].strip()
            content = parts[1].strip() if len(parts) > 1 else ""

            # Убираем цветные ники, делаем все черными и жирными
            color = "#000000"

            if "[Вложение:" in content or "[Файл получен:" in content or "[Файл:" in content:
                # Извлекаем имя файла
                import re
                file_match = re.search(r'\[(Вложение|Файл получен|Файл): ([^\]]+)\]', content)

                if file_match:
                    file_name = file_match.group(2)

                    # Теперь все файлы хранятся в downloads без префиксов
                    file_path = os.path.join("downloads", file_name)

                    # Проверяем расширение файла для определения типа
                    file_ext = os.path.splitext(file_name)[1].lower()

                    # Удаляем информацию о вложении из текста
                    clean_content = content.replace(file_match.group(0), "").strip()

                    # Создаем HTML для отображения вложения в зависимости от типа файла
                    if file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                        # Изображения
                        if os.path.exists(file_path):
                            # Получаем путь к уменьшенной копии изображения
                            scaled_path = self.get_scaled_image_path(file_path)

                            attachment_html = f"""
                            <div style="margin-top: 10px; max-width: 300px; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">
                                <a href="file:{file_path}">
                                    <img src="{scaled_path}" style="max-width: 300px; max-height: 200px; display: block;">
                                </a>
                                <div style="padding: 8px;">
                                    <div style="font-weight: bold; font-size: 13px; overflow: hidden; text-overflow: ellipsis;">{file_name}</div>
                                    <div style="font-size: 11px; color: #666;">Нажмите, чтобы открыть</div>
                                </div>
                            </div>
                            """
                        else:
                            attachment_html = f"""
                            <div style="margin-top: 10px; padding: 10px; border-radius: 10px; background-color: #ffebee;">
                                <div style="display: flex; align-items: center;">
                                    <span style="font-size: 24px; margin-right: 10px;">🖼️</span>
                                    <div>
                                        <div style="font-weight: bold;">{file_name}</div>
                                        <div style="font-size: 12px; color: #666;">Изображение загружается...</div>
                                    </div>
                                </div>
                            </div>
                            """
                    elif file_ext in ['.pdf']:
                        # PDF документы
                        attachment_html = f"""
                        <div style="margin-top: 10px; padding: 12px; border-radius: 10px; display: flex; align-items: center;">
                            <span style="font-size: 24px; margin-right: 12px;">📄</span>
                            <div style="flex-grow: 1; overflow: hidden;">
                                <div style="font-weight: bold; overflow: hidden; text-overflow: ellipsis;">
                                    <a href="file:{file_path}" style="color: #333; text-decoration: none;">{file_name}</a>
                                </div>
                                <div style="font-size: 12px; color: #666;">Нажмите, чтобы открыть</div>
                            </div>
                        </div>
                        """
                    elif file_ext in ['.doc', '.docx']:
                        # Word документы
                        attachment_html = f"""
                        <div style="margin-top: 10px; padding: 12px; border-radius: 10px; display: flex; align-items: center;">
                            <span style="font-size: 24px; margin-right: 12px;">📄</span>
                            <div style="flex-grow: 1; overflow: hidden;">
                                <div style="font-weight: bold; overflow: hidden; text-overflow: ellipsis;">
                                    <a href="file:{file_path}" style="color: #333; text-decoration: none;">{file_name}</a>
                                </div>
                                <div style="font-size: 12px; color: #666;">Нажмите, чтобы открыть</div>
                            </div>
                        </div>
                        """
                    elif file_ext in ['.mp3', '.wav', '.ogg', '.flac']:
                        # Аудио файлы
                        attachment_html = f"""
                        <div style="margin-top: 10px; padding: 12px; border-radius: 10px; display: flex; align-items: center;">
                            <span style="font-size: 24px; margin-right: 12px;">🎵</span>
                            <div style="flex-grow: 1; overflow: hidden;">
                                <div style="font-weight: bold; overflow: hidden; text-overflow: ellipsis;">
                                    <a href="file:{file_path}" style="color: #333; text-decoration: none;">{file_name}</a>
                                </div>
                                <div style="font-size: 12px; color: #666;">Аудиофайл • Нажмите, чтобы открыть</div>
                            </div>
                        </div>
                        """
                    elif file_ext in ['.mp4', '.avi', '.mov', '.wmv', '.mkv']:
                        # Видео файлы
                        attachment_html = f"""
                        <div style="margin-top: 10px; padding: 12px; border-radius: 10px; display: flex; align-items: center;">
                            <span style="font-size: 24px; margin-right: 12px;">🎬</span>
                            <div style="flex-grow: 1; overflow: hidden;">
                                <div style="font-weight: bold; overflow: hidden; text-overflow: ellipsis;">
                                    <a href="file:{file_path}" style="color: #333; text-decoration: none;">{file_name}</a>
                                </div>
                                <div style="font-size: 12px; color: #666;">Видеофайл • Нажмите, чтобы открыть</div>
                            </div>
                        </div>
                        """
                    else:
                        # Другие типы файлов
                        attachment_html = f"""
                        <div style="margin-top: 10px; padding: 12px;  border-radius: 10px; display: flex; align-items: center;">
                            <span style="font-size: 24px; margin-right: 12px;">📎</span>
                            <div style="flex-grow: 1; overflow: hidden;">
                                <div style="font-weight: bold; overflow: hidden; text-overflow: ellipsis;">
                                    <a href="file:{file_path}" style="color: #333; text-decoration: none;">{file_name}</a>
                                </div>
                                <div style="font-size: 12px; color: #666;">Файл • Нажмите, чтобы открыть</div>
                            </div>
                        </div>
                        """

                    # Если есть дополнительный текст, добавляем его
                    content_html = f"<div style='margin-top: 3px;'>{clean_content}</div>" if clean_content else ""

                    return f"""
                    <div style='margin: 10px 0; text-align: left;'>
                        <div style='display: inline-block; vertical-align: top; max-width: 80%;'>
                            <span style='font-weight: bold; color: {color};'>{username}</span>
                            <span style='font-size: 11px; color: #666; margin-left: 5px;'>{current_time}</span>
                            <span style='font-size: 11px; color: #666; margin-left: 5px;'>{current_date}</span>
                            {content_html}
                            {attachment_html}
                        </div>
                    </div>
                    """

            # Модифицируем формат сообщения, чтобы сохранить двухстрочную структуру
            return f"""
            <div style='margin: 10px 0; text-align: left;'>
                <div style='display: inline-block; vertical-align: top; max-width: 80%;'>
                    <div>
                        <span style='font-weight: bold; color: {color};'>{username}</span>
                        <span style='font-size: 11px; color: #666; margin-left: 5px;'>{current_time}</span>
                        <span style='font-size: 11px; color: #666; margin-left: 5px;'>{current_date}</span>
                    </div>
                    <div style='margin-top: 3px;'>{content}</div>
                </div>
            </div>
            """
        else:
            return f"""
            <div style='margin: 10px 0; text-align: left;'>
                <div style='font-size: 11px; color: #666;'>{current_time} {current_date}</div>
                <div>{message}</div>
            </div>
            """

    def setup_text_display(self):
        """Настраивает QTextEdit для отображения изображений и обработки кликов по файлам"""
        # Разрешаем отображение изображений и других ресурсов
        self.text_display.document().setDefaultStyleSheet("""
        img { max-width: 300px; max-height: 200px; }
        a { color: #2196F3; text-decoration: none; }
        """)

        # Разрешаем HTML-форматирование
        self.text_display.setHtml("")

        # Создаем директорию downloads, если она не существует
        os.makedirs("downloads", exist_ok=True)

        # Создаем директорию для уменьшенных изображений
        os.makedirs(os.path.join("downloads", "scaled"), exist_ok=True)

        # Подключаем обработчик событий для отслеживания кликов мыши
        self.text_display.mousePressEvent = self.text_display_mouse_press_event

        # Добавляем обработчик контекстного меню
        self.text_display.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.text_display.customContextMenuRequested.connect(self.show_context_menu)

        # Сохраняем обработчик событий мыши
        self.original_mouse_press_event = QtWidgets.QTextEdit.mousePressEvent

    def refresh_file_display(self):
        """Обновляет отображение файлов в текущем чате"""
        if self.current_chat_with:
            # Для личных чатов
            QtCore.QTimer.singleShot(200, self.refresh_chat)
        elif self.current_group:
            # Для групповых чатов
            QtCore.QTimer.singleShot(200, self.refresh_group_chat)

    def text_display_mouse_press_event(self, event):
        """Обрабатывает клики мыши в QTextEdit для открытия файлов"""
        # Вызываем оригинальный обработчик событий
        self.original_mouse_press_event(self.text_display, event)

        # Получаем позицию курсора в месте клика
        cursor = self.text_display.cursorForPosition(event.pos())

        # Проверяем, находится ли курсор на ссылке
        cursor.select(QtGui.QTextCursor.WordUnderCursor)
        selected_text = cursor.selectedText()

        # Проверяем, является ли выделенный текст ссылкой
        if selected_text.startswith("file:"):
            file_path = selected_text[5:]  # Убираем префикс "file:"
            self.open_file(file_path)

        # Также проверяем, есть ли ссылка в формате HTML
        cursor = self.text_display.cursorForPosition(event.pos())
        char_format = cursor.charFormat()
        if char_format.isAnchor():
            href = char_format.anchorHref()
            if href.startswith("file:"):
                file_path = href[5:]  # Убираем префикс "file:"
                self.open_file(file_path)

    def open_file(self, file_path):
        """Открывает файл с помощью системного приложения по умолчанию"""
        try:
            # Нормализуем путь
            normalized_path = os.path.normpath(file_path)

            # Проверяем, что файл существует
            if not os.path.exists(normalized_path):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Файл не найден",
                    f"Файл не найден: {normalized_path}"
                )
                return

            # Открываем файл с помощью системного приложения по умолчанию
            url = QtCore.QUrl.fromLocalFile(normalized_path)
            QtGui.QDesktopServices.openUrl(url)
            print(f"[FILE] Открыт файл: {normalized_path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось открыть файл: {str(e)}"
            )
            print(f"[ERROR] Ошибка при открытии файла: {e}")

    def send_message(self):
        """Отправляет сообщение или сохраняет отредактированное сообщение"""
        message = self.message_input.text()

        # Проверяем, находимся ли мы в режиме редактирования личного сообщения
        if hasattr(self, 'is_editing') and self.is_editing:
            if message and self.current_chat_with:
                try:
                    # Добавляем пометку "(изменено)" если её еще нет
                    if not "(изменено)" in message:
                        new_message = f"{message} (изменено)"
                    else:
                        new_message = message

                    # Проверяем наличие ID сообщения для редактирования
                    if not hasattr(self, 'editing_message_id'):
                        QtWidgets.QMessageBox.warning(
                            self,
                            "Ошибка редактирования",
                            "Не удалось определить ID сообщения для редактирования."
                        )
                        self.cancel_editing()
                        return

                    # Обновляем сообщение в БД
                    cursor = self.connection.cursor()
                    cursor.execute(
                        "UPDATE messages SET content = %s WHERE id = %s",
                        (new_message, self.editing_message_id)
                    )
                    self.connection.commit()
                    cursor.close()

                    # Отправляем обновленное сообщение на сервер для синхронизации с другими клиентами
                    edit_notification = f"EDIT_MESSAGE:{self.username}:{self.current_chat_with}:{new_message}:{self.editing_message_id}"
                    self.client.send_message(edit_notification)

                    # Обновляем отображение чата
                    self.refresh_chat()

                    # Сбрасываем режим редактирования
                    self.is_editing = False
                    self.send_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")
                    self.attach_btn.setEnabled(True)
                    self.message_input.clear()

                    # Скрываем кнопку отмены
                    if hasattr(self, 'cancel_edit_btn'):
                        self.cancel_edit_btn.hide()

                    # Очищаем сохраненные блоки и текст
                    if hasattr(self, 'editing_header_block'):
                        delattr(self, 'editing_header_block')
                    if hasattr(self, 'editing_message_block'):
                        delattr(self, 'editing_message_block')
                    if hasattr(self, 'editing_message_text'):
                        delattr(self, 'editing_message_text')
                    if hasattr(self, 'editing_message_id'):
                        delattr(self, 'editing_message_id')
                except Exception as e:
                    QtWidgets.QMessageBox.critical(
                        self,
                        "Ошибка",
                        f"Не удалось отредактировать сообщение: {str(e)}"
                    )
                    # Сбрасываем режим редактирования при ошибке
                    self.cancel_editing()
            else:
                # Если сообщение пустое, отменяем редактирование
                self.cancel_editing()
        # Проверяем, находимся ли мы в режиме редактирования группового сообщения
        elif hasattr(self, 'is_editing_group') and self.is_editing_group:
            if message and self.current_group:
                try:
                    # Добавляем пометку "(изменено)" если её еще нет
                    if not "(изменено)" in message:
                        new_message = f"{message} (изменено)"
                    else:
                        new_message = message

                    # Проверяем наличие ID сообщения для редактирования
                    if not hasattr(self, 'editing_message_id'):
                        QtWidgets.QMessageBox.warning(
                            self,
                            "Ошибка редактирования",
                            "Не удалось определить ID сообщения для редактирования."
                        )
                        self.cancel_editing()
                        return

                    # Отправляем команду редактирования на сервер
                    edit_command = f"GROUP_EDIT_MESSAGE:{self.current_group['id']}:{self.username}:{new_message}:{self.editing_message_id}"
                    self.client.group_client.send(f"{edit_command}\n".encode('utf-8'))

                    # Обновляем отображение чата
                    QtCore.QTimer.singleShot(500, self.refresh_group_chat)

                    # Сбрасываем режим редактирования
                    self.is_editing_group = False
                    self.send_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")
                    self.attach_btn.setEnabled(True)
                    self.message_input.clear()

                    # Скрываем кнопку отмены
                    if hasattr(self, 'cancel_edit_btn'):
                        self.cancel_edit_btn.hide()

                    # Очищаем сохраненные блоки и текст
                    if hasattr(self, 'editing_header_block'):
                        delattr(self, 'editing_header_block')
                    if hasattr(self, 'editing_message_block'):
                        delattr(self, 'editing_message_block')
                    if hasattr(self, 'editing_message_text'):
                        delattr(self, 'editing_message_text')
                    if hasattr(self, 'editing_message_id'):
                        delattr(self, 'editing_message_id')
                except Exception as e:
                    QtWidgets.QMessageBox.critical(
                        self,
                        "Ошибка",
                        f"Не удалось отредактировать сообщение: {str(e)}"
                    )
                    # Сбрасываем режим редактирования при ошибке
                    self.cancel_editing()
            else:
                # Если сообщение пустое, отменяем редактирование
                self.cancel_editing()
        else:
            # Обычная отправка сообщения
            if (message or self.current_attachment):
                # Проверяем, отправляем ли в группу или в личный чат
                if self.current_group:
                    # Отправка в группу
                    if self.current_attachment:
                        # Безопасная обработка вложений для группы
                        file_name = os.path.basename(self.current_attachment)

                        # Копируем файл в downloads ДО отправки
                        os.makedirs("downloads", exist_ok=True)
                        destination_path = os.path.join("downloads", file_name)

                        if not os.path.exists(destination_path):
                            try:
                                import shutil
                                shutil.copy2(self.current_attachment, destination_path)
                                print(f"[GROUP FILE] Copied {self.current_attachment} to {destination_path}")

                                # Создаем уменьшенную копию через сигнал
                                if file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                                    self.update_ui_signal.emit("create_scaled_image", {
                                        "original_path": destination_path,
                                        "scaled_path": os.path.join("downloads", "scaled", f"scaled_{file_name}"),
                                        "max_width": 300,
                                        "max_height": 200
                                    })
                            except Exception as e:
                                print(f"[ERROR] Failed to copy group file: {e}")
                                return

                        # Формируем содержимое сообщения
                        if message:
                            content = f"{message} [Вложение: {file_name}]"
                        else:
                            content = f"[Вложение: {file_name}]"

                        # Потом отправляем файл
                        success = self.client.send_group_file(self.current_group['id'], self.current_attachment)
                        if not success:
                            print(f"[ERROR] Failed to send file to group {self.current_group['id']}")

                        self.remove_attachment()
                    else:
                        # Обычное текстовое сообщение в группу
                        if message:
                            self.client.send_group_message(self.current_group['id'], message)

                    self.message_input.clear()

                elif self.current_chat_with:
                    # Отправка в личный чат
                    # Проверяем, является ли получатель другом
                    if self.current_chat_with not in self.friends:
                        self.text_display.append(f"""
                                    <div style='margin: 10px 0; text-align: center; color: red;'>
                                        Невозможно отправить сообщение. Пользователь {self.current_chat_with} не в вашем списке друзей.
                                    </div>
                                    """)
                        return

                    # Метод для отправки личных сообщений
                    if self.current_attachment:
                        # Сначала копируем файл, потом отправляем сообщение
                        file_name = os.path.basename(self.current_attachment)

                        # Убеждаемся, что директория downloads существует
                        os.makedirs("downloads", exist_ok=True)

                        # Копируем файл в downloads ДО отправки сообщения
                        destination_path = os.path.join("downloads", file_name)
                        if not os.path.exists(destination_path):
                            try:
                                import shutil
                                shutil.copy2(self.current_attachment, destination_path)
                                print(f"[FILE] Copied {self.current_attachment} to {destination_path}")

                                # Если это изображение, создаем уменьшенную копию
                                if file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                                    self.create_scaled_image(destination_path)
                            except Exception as e:
                                print(f"[ERROR] Failed to copy file: {e}")
                                QtWidgets.QMessageBox.critical(
                                    self,
                                    "Ошибка",
                                    f"Не удалось подготовить файл для отправки: {str(e)}"
                                )
                                return

                        # Теперь отправляем сообщение
                        if message:
                            content = f"{message} [Вложение: {file_name}]"
                        else:
                            content = f"[Вложение: {file_name}]"

                        # Отправляем сообщение напрямую получателю
                        self.client.send_direct_message(self.current_chat_with, content)

                        # Отображаем сообщение в своем чате
                        full_message = f"{self.username}: {content}"
                        self.display_message(full_message)

                        # Отправляем файл
                        self.send_file(self.current_attachment, self.current_chat_with)
                        self.remove_attachment()
                    else:
                        # Обычное текстовое сообщение
                        # Отправляем сообщение напрямую получателю
                        self.client.send_direct_message(self.current_chat_with, message)

                        # Отображаем сообщение в своем чате
                        full_message = f"{self.username}: {message}"
                        self.display_message(full_message)

                    self.message_input.clear()

                    if self.current_chat_with not in self.chat_initialized:
                        self.chat_initialized[self.current_chat_with] = True
                else:
                    # Нет активного чата или группы
                    QtWidgets.QMessageBox.information(
                        self,
                        "Информация",
                        "Выберите друга или группу для отправки сообщения."
                    )

    def cancel_editing(self):
        """Отменяет редактирование сообщения"""
        if (hasattr(self, 'is_editing') and self.is_editing) or (
                hasattr(self, 'is_editing_group') and self.is_editing_group):
            # Сбрасываем режим редактирования
            if hasattr(self, 'is_editing'):
                self.is_editing = False
            if hasattr(self, 'is_editing_group'):
                self.is_editing_group = False

            self.send_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")
            self.attach_btn.setEnabled(True)
            self.message_input.clear()

            # Скрываем кнопку отмены
            if hasattr(self, 'cancel_edit_btn'):
                self.cancel_edit_btn.hide()

            # Очищаем сохраненные блоки
            if hasattr(self, 'editing_header_block'):
                delattr(self, 'editing_header_block')
            if hasattr(self, 'editing_message_block'):
                delattr(self, 'editing_message_block')
            if hasattr(self, 'editing_message_text'):
                delattr(self, 'editing_message_text')
            if hasattr(self, 'editing_message_id'):
                delattr(self, 'editing_message_id')

    def send_file(self, file_path, recipient):
        """Отправляет файл получателю"""
        try:
            # Получаем информацию о файле
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            # Создаем директорию downloads, если она не существует
            os.makedirs("downloads", exist_ok=True)

            # Копируем файл в директорию downloads, если он еще не там
            if not file_path.startswith(os.path.join(os.getcwd(), "downloads")):
                destination = os.path.join("downloads", file_name)
                import shutil
                shutil.copy2(file_path, destination)
                print(f"[ФАЙЛ] Скопирован файл {file_path} в {destination}")

                # Если это изображение, создаем уменьшенную копию
                if file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    self.create_scaled_image(destination)

            # Уведомляем получателя о входящем файле
            file_info = f"FILE_TRANSFER:START:{self.username}:{recipient}:{file_name}:{file_size}"
            self.client.send_message(file_info)

            # Читаем и отправляем файл по частям
            with open(file_path, 'rb') as f:
                chunk_size = 4096  # 4KB части
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                # Кодируем часть в base64, убедившись что нет переносов строк
                encoded_chunk = base64.b64encode(chunk).decode('utf-8').replace('\n', '')

                # Разбиваем большие части на более мелкие для надежной передачи
                max_msg_size = 900  # Максимальный размер сообщения
                for i in range(0, len(encoded_chunk), max_msg_size):
                    sub_chunk = encoded_chunk[i:i + max_msg_size]
                    chunk_msg = f"FILE_TRANSFER:CHUNK:{self.username}:{recipient}:{sub_chunk}"
                    self.client.send_message(chunk_msg)

                    # Добавляем небольшую задержку, чтобы не перегружать сеть
                    QtCore.QThread.msleep(20)

            # Уведомляем о завершении
            end_msg = f"FILE_TRANSFER:END:{self.username}:{recipient}:{file_name}"
            self.client.send_message(end_msg)

            print(f"[ФАЙЛ] Отправлен {file_name} пользователю {recipient}")

        except Exception as e:
            print(f"[ОШИБКА] Не удалось отправить файл: {e}")
            self.text_display.append(f"""
        <div style='margin: 10px 0; text-align: center; color: red;'>
            Не удалось отправить файл: {str(e)}
        </div>
        """)

    def open_attachment_dialog(self):
        """Открывает диалог выбора вложения"""
        dialog = AttachmentDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.set_attachment(dialog.selected_file)

    def set_attachment(self, file_path):
        """Устанавливает выбранное вложение и показывает его превью"""
        # Удаляем предыдущее вложение, если оно есть
        self.remove_attachment()

        # Создаем и добавляем превью вложения
        self.current_attachment = file_path
        self.attachment_preview = AttachmentPreview(file_path, self)
        self.attachment_preview.removed.connect(self.remove_attachment)

        # Добавляем превью над панелью ввода сообщения
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, self.attachment_preview)

    def remove_attachment(self):
        """Удаляет текущее вложение"""
        if self.attachment_preview:
            self.attachment_preview.deleteLater()
            self.attachment_preview = None
            self.current_attachment = None

    def handle_link_clicked(self, url):
        """Обрабатывает клики по ссылкам в сообщениях"""
        try:
            # Проверяем, является ли это локальным файлом
            if url.scheme() == "file":
                file_path = url.toLocalFile()
                # Нормализуем путь
                normalized_path = os.path.normpath(file_path)

                # Проверяем, что файл существует
                if not os.path.exists(normalized_path):
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Файл не найден",
                        f"Файл не найден: {normalized_path}"
                    )
                    return

                # Открываем файл с помощью системного приложения по умолчанию
                QtGui.QDesktopServices.openUrl(url)
                print(f"[FILE] Открыт файл: {normalized_path}")
            else:
                # Открываем внешние ссылки в браузере
                QtGui.QDesktopServices.openUrl(url)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось открыть файл: {str(e)}"
            )
            print(f"[ERROR] Ошибка при обработке ссылки: {e}")

    def handle_call_button(self):
        if self.current_group:
            # Групповой звонок
            self.handle_group_call_button()
        elif self.current_chat_with:
            # Личный звонок (существующая логика)
            if self.client.is_in_call:
                if self.call_dialog:
                    self.call_dialog.end_call()
            else:
                self.start_call(self.current_chat_with)

    def start_call(self, recipient):
        if recipient not in self.chat_initialized:
            self.initialize_chat(recipient)
            QtCore.QTimer.singleShot(500, lambda: self._start_call_after_init(recipient))
            return
        self._start_call_after_init(recipient)

    def _start_call_after_init(self, recipient):
        if self.client.start_call(recipient):
            self.show_outgoing_call(recipient)

    def initialize_chat(self, friend_name):
        self.chat_initialized[friend_name] = True

    def show_incoming_call(self, caller):
        print(f"[CALL] Showing incoming call from {caller}")

        # Если уже в звонке или уже есть диалог звонка, отклоняем новый звонок
        if self.client.is_in_call or self.call_dialog:
            self.client.reject_call(caller)
            return

        # Сохраняем текущий чат, чтобы вернуться к нему после звонка
        previous_chat = self.current_chat_with

        # Инициализируем чат, если он еще не инициализирован
        if caller not in self.chat_initialized:
            self.initialize_chat(caller)

        # Открываем чат с звонящим
        self.open_chat_with(caller)

        # Создаем диалог звонка
        self.call_dialog = CallDialog(self.username, caller, is_caller=False, parent=self)
        self.call_dialog.call_accepted.connect(lambda: self.accept_incoming_call(caller))
        self.call_dialog.call_rejected.connect(lambda: self.reject_incoming_call(caller, previous_chat))
        self.call_dialog.call_ended.connect(self.handle_call_ended)
        self.call_dialog.mic_muted.connect(self.handle_mic_muted)
        self.call_dialog.speaker_muted.connect(self.handle_speaker_muted)

        # Устанавливаем флаг, чтобы окно всегда было поверх других окон
        self.call_dialog.setWindowFlags(self.call_dialog.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.call_dialog.show()

        # Активируем окно приложения, чтобы пользователь увидел входящий звонок
        self.activateWindow()
        self.raise_()

        # Воспроизводим звук звонка
        try:
            # звук звонка сюда добавить потом если успеем
            pass
        except Exception as e:
            print(f"[ERROR] Failed to play ringtone: {e}")

    def show_outgoing_call(self, recipient):
        print(f"[CALL] Showing outgoing call to {recipient}")

        # Если уже есть диалог звонка, ничего не делаем
        if self.call_dialog:
            return

        # Если чат с получателем не открыт, открываем его
        if self.current_chat_with != recipient:
            self.open_chat_with(recipient)

        # Создаем диалог звонка
        self.call_dialog = CallDialog(self.username, recipient, is_caller=True, parent=self)
        self.call_dialog.call_ended.connect(self.handle_call_ended)
        self.call_dialog.call_accepted.connect(self.client.start_audio)
        self.call_dialog.mic_muted.connect(self.handle_mic_muted)
        self.call_dialog.speaker_muted.connect(self.handle_speaker_muted)
        self.call_dialog.show()
        self.call_btn.setStyleSheet("background-color: #FFC107; border-radius: 15px;")

    def handle_group_message(self, message):
        """Обрабатывает групповые сообщения с проверкой активного чата"""
        try:
            # Формат: GROUP_MESSAGE:group_id:sender:content
            parts = message.split(":", 3)
            if len(parts) < 4:
                print(f"[GROUP ERROR] Invalid group message format: {message}")
                return

            group_id = int(parts[1])
            sender = parts[2]
            content = parts[3]

            # Отображаем только если это текущая группа И нет активного личного чата
            if (self.current_group and
                    self.current_group['id'] == group_id and
                    not self.current_chat_with):
                temp_message = f"{sender}: {content}"
                formatted_message = self.format_chat_message(temp_message)
                self.text_display.append(formatted_message)

                def scroll_to_end():
                    cursor = self.text_display.textCursor()
                    cursor.movePosition(QtGui.QTextCursor.End)
                    self.text_display.setTextCursor(cursor)
                    self.text_display.ensureCursorVisible()
                    scrollbar = self.text_display.verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())

                scroll_to_end()
                QtCore.QTimer.singleShot(10, scroll_to_end)
                QtCore.QTimer.singleShot(100, scroll_to_end)

        except Exception as e:
            print(f"[GROUP ERROR] Error handling group message: {e}")

    def accept_incoming_call(self, caller):
        if self.client.accept_call(caller):
            self.call_btn.setStyleSheet("background-color: #4CAF50; border-radius: 15px;")
            self.call_start_time = time.time()
            if caller in self.friends and self.current_chat_with != caller:
                self.open_chat_with(caller)

    def reject_incoming_call(self, caller, previous_chat=None):
        self.client.reject_call(caller)
        if self.call_dialog:
            self.call_dialog.close()
            self.call_dialog = None

        # Возвращаемся к предыдущему чату, если он был указан
        if previous_chat and previous_chat != caller:
            QtCore.QTimer.singleShot(100, lambda: self.open_chat_with(previous_chat))

    def call_accepted(self, recipient):
        if self.call_dialog:
            self.client.is_in_call = True
            self.client.start_audio()
            self.call_dialog.call_was_accepted()
            self.call_btn.setStyleSheet("background-color: #4CAF50; border-radius: 15px;")
            self.call_start_time = time.time()

    def call_rejected(self, recipient):
        self.display_message(f"Система: {recipient} отклонил(а) ваш звонок")
        if self.call_dialog:
            self.call_dialog.close()
            self.call_dialog = None
        self.call_btn.setStyleSheet("background-color: #e0e0e0 :self.call_dialog = None;")
        self.call_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 15px;")
        self.client.is_in_call = False


    def load_user_groups(self):
        """Загружает группы пользователя из базы данных"""
        if not self.connection:
            return

        try:
            cursor = self.connection.cursor()

            # Получаем группы, в которых состоит пользователь
            cursor.execute(
                """
                SELECT g.id, g.name, g.invite_link, g.avatar_path, g.description, gm.role
                FROM groups g
                JOIN group_members gm ON g.id = gm.group_id
                WHERE gm.username = %s
                ORDER BY gm.joined_at DESC
                """,
                (self.username,)
            )

            groups = cursor.fetchall()
            cursor.close()


            # Проходим по всем элементам в обратном порядке
            for i in range(self.right_sidebar_layout.count() - 1, -1, -1):
                item = self.right_sidebar_layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    # Проверяем, является ли это кнопкой группы
                    # Добавляем проверку на существование add_server_btn
                    if (hasattr(widget, 'group_data') and
                            hasattr(self, 'add_server_btn') and
                            widget != self.add_server_btn):
                        # Удаляем из layout и помечаем для удаления
                        self.right_sidebar_layout.removeWidget(widget)
                        widget.setParent(None)
                        widget.deleteLater()

            # Добавляем кнопки для каждой группы
            for group in groups:
                group_id, name, invite_link, avatar_path, description, role = group
                group_data = {
                    'id': group_id,
                    'name': name,
                    'invite_link': invite_link,
                    'avatar_path': avatar_path,
                    'description': description,
                    'role': role
                }
                self.add_group_button(group_data)

        except Exception as e:
            print(f"[ERROR] Failed to load user groups: {e}")


    def load_user_avatar(self, username, avatar_label, size=50):
        """Загружает аватар пользователя из базы данных и устанавливает его в указанный QLabel"""
        if not self.connection:
            return

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT avatar_path FROM user_profiles WHERE username = %s", (username,))
            result = cursor.fetchone()
            cursor.close()

            if result and result[0] and os.path.exists(result[0]):
                pixmap = QtGui.QPixmap(result[0])
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

                    # Создаем круглую маску
                    mask = QtGui.QPixmap(size, size)
                    mask.fill(QtCore.Qt.transparent)
                    painter = QtGui.QPainter(mask)
                    painter.setRenderHint(QtGui.QPainter.Antialiasing)
                    painter.setBrush(QtCore.Qt.white)
                    painter.drawEllipse(0, 0, size, size)
                    painter.end()

                    # Применяем маску
                    rounded_pixmap = QtGui.QPixmap(pixmap.size())
                    rounded_pixmap.fill(QtCore.Qt.transparent)
                    painter = QtGui.QPainter(rounded_pixmap)
                    painter.setRenderHint(QtGui.QPainter.Antialiasing)
                    painter.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
                    painter.drawPixmap(0, 0, mask)
                    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
                    painter.drawPixmap(0, 0, pixmap)
                    painter.end()

                    avatar_label.setPixmap(rounded_pixmap)
                    avatar_label.setText("")
                    return True
        except Exception as e:
            print(f"[ERROR] Failed to load user avatar: {e}")

        return False

    def handle_mic_muted(self, is_muted):
        if self.client.is_in_call:
            self.client.set_mic_muted(is_muted)

    def handle_speaker_muted(self, is_muted):
        if self.client.is_in_call:
            self.client.set_speaker_muted(is_muted)

    def open_friend_search(self):
        if self.connection:
            dialog = FriendSearchDialog(self.connection, self.username)
            dialog.exec_()
            self.load_friends()

    def open_notifications(self):
        if self.connection:
            dialog = NotificationDialog(self.connection, self.username)
            dialog.friendsUpdated.connect(self.load_friends)

            # Подключаем сигнал для открытия чата
            dialog.openChatRequested.connect(self.open_chat_with)

            # Подключаем сигнал для обновления групп
            dialog.groupsUpdated.connect(self.load_user_groups)
            dialog.exec_()
            self.notification_count = 0
            self.notification_btn.setText("🔔")
            self.check_notifications()

    def check_notifications(self):
        if not self.connection:
            return
        try:
            cursor = self.connection.cursor()

            # Получаем настройки уведомлений
            cursor.execute(
                "SELECT enabled FROM notification_settings WHERE username = %s",
                (self.username,)
            )
            result = cursor.fetchone()
            notifications_enabled = True

            if result is not None:
                notifications_enabled = result[0]

            # Запросы в друзья
            cursor.execute(
                "SELECT COUNT(*) FROM friend_requests WHERE receiver = %s AND status = 'pending'",
                (self.username,)
            )
            friend_requests_count = cursor.fetchone()[0]

            # Приглашения в группы
            # Проверяем существование таблицы group_invites
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'group_invites'
                )
            """)
            group_invites_table_exists = cursor.fetchone()[0]

            group_invites_count = 0
            if group_invites_table_exists:
                cursor.execute(
                    "SELECT COUNT(*) FROM group_invites WHERE invitee = %s AND status = 'pending'",
                    (self.username,)
                )
                group_invites_count = cursor.fetchone()[0]

            # Пропущенные звонки
            # Проверяем существование таблицы call_logs и колонки notification_seen
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'call_logs'
                )
            """)
            call_logs_exists = cursor.fetchone()[0]

            missed_calls_count = 0
            if call_logs_exists:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'call_logs' AND column_name = 'notification_seen'
                    )
                """)
                has_notification_seen = cursor.fetchone()[0]

                if has_notification_seen:
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM call_logs 
                        WHERE recipient = %s AND status = 'missed' AND notification_seen = FALSE
                        """,
                        (self.username,)
                    )
                    missed_calls_count = cursor.fetchone()[0]

            # Непрочитанные сообщения
            # Проверяем наличие колонки read в таблице messages
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'messages' AND column_name = 'read'
                )
            """)
            has_read_column = cursor.fetchone()[0]

            unread_messages_count = 0
            if has_read_column:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM messages 
                    WHERE receiver = %s AND read = FALSE
                    """,
                    (self.username,)
                )
                unread_messages_count = cursor.fetchone()[0]

            # Общее количество уведомлений
            total_count = friend_requests_count + group_invites_count + missed_calls_count + unread_messages_count
            self.notification_count = total_count

            # Обновляем иконку уведомлений
            if notifications_enabled and total_count > 0:
                self.notification_btn.setText(f"🔔{total_count}")
            else:
                self.notification_btn.setText("🔔")

        except Exception as e:
            print(f"Error checking notifications: {e}")
        finally:
            cursor.close()

    def closeEvent(self, event):
        """Обрабатывает закрытие приложения"""
        # Отправляем статус "не в сети" при закрытии
        if hasattr(self, 'client') and hasattr(self.client, 'send_message'):
            self.client.send_message(f"STATUS_OFFLINE:{self.username}")
        event.accept()

    def load_friends(self):
        if not self.connection:
            return
        try:
            cursor = self.connection.cursor()
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
                (self.username, self.username, self.username)
            )
            friends = cursor.fetchall()
            while self.friends_layout.count():
                item = self.friends_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            self.friends = [friend[0] for friend in friends]
            for friend in self.friends:
                self.add_friend_button(friend)
        except Exception as e:
            print(f"Error loading friends: {e}")
        finally:
            cursor.close()

    def load_user_avatar(self, username, avatar_label, avatar_frame=None):
        """Загружает аватар пользователя из базы данных и устанавливает его в указанный QLabel"""
        if not self.connection:
            return False

        try:
            cursor = self.connection.cursor()

            # Проверяем, есть ли таблица user_profiles
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'user_profiles'
                )
            """)
            has_profile_table = cursor.fetchone()[0]

            if not has_profile_table:
                cursor.close()
                return False

            # Получаем путь к аватару пользователя
            cursor.execute(
                "SELECT avatar_path FROM user_profiles WHERE username = %s",
                (username,)
            )
            result = cursor.fetchone()
            cursor.close()

            if result and result[0] and os.path.exists(result[0]):
                avatar_path = result[0]

                # Загружаем и устанавливаем аватар
                pixmap = QtGui.QPixmap(avatar_path)
                if not pixmap.isNull():
                    # Масштабируем и обрезаем до круга
                    size = min(pixmap.width(), pixmap.height())
                    pixmap = pixmap.scaled(
                        80, 80,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation
                    )

                    # Создаем круглую маску
                    mask = QtGui.QPixmap(80, 80)
                    mask.fill(QtCore.Qt.transparent)
                    painter = QtGui.QPainter(mask)
                    painter.setRenderHint(QtGui.QPainter.Antialiasing)
                    painter.setBrush(QtCore.Qt.white)
                    painter.drawEllipse(0, 0, 80, 80)
                    painter.end()

                    # Применяем маску
                    rounded_pixmap = QtGui.QPixmap(pixmap.size())
                    rounded_pixmap.fill(QtCore.Qt.transparent)
                    painter = QtGui.QPainter(rounded_pixmap)
                    painter.setRenderHint(QtGui.QPainter.Antialiasing)
                    painter.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
                    painter.drawPixmap(0, 0, mask)
                    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
                    painter.drawPixmap(0, 0, pixmap)
                    painter.end()

                    # Устанавливаем аватар
                    avatar_label.setPixmap(rounded_pixmap)
                    avatar_label.setText("")

                    # Если передан frame, убираем цветной фон
                    if avatar_frame:
                        avatar_frame.setStyleSheet(
                            "background-color: transparent; border-radius: 15px; border: 2px solid #333;")

                    return True
            return False
        except Exception as e:
            print(f"[ERROR] Failed to load avatar for {username}: {e}")
            return False

    def add_friend_button(self, friend_name):
        import random
        colors = ["#4CAF50", "#FF5722", "#FFC107", "#2196F3", "#9C27B0"]
        color = random.choice(colors)

        # Создаем кнопку друга
        friend_btn = QtWidgets.QPushButton()
        friend_btn.setFixedSize(40, 40)

        # Устанавливаем стиль по умолчанию
        friend_btn.setStyleSheet(f"background-color: {color}; border-radius: 15px; border: 2px solid #333;")
        friend_btn.setToolTip(friend_name)

        icon_layout = QtWidgets.QVBoxLayout(friend_btn)
        icon_layout.setContentsMargins(2, 2, 2, 2)

        user_icon = QtWidgets.QLabel("👤")
        user_icon.setAlignment(QtCore.Qt.AlignCenter)
        user_icon.setStyleSheet("border: none;")
        user_icon.setFont(QtGui.QFont("Arial", 15))

        icon_layout.addWidget(user_icon)

        # Пытаемся загрузить аватар пользователя
        has_avatar = self.load_user_avatar(friend_name, user_icon)

        # Если у пользователя есть аватар, убираем цветной фон
        if has_avatar:
            friend_btn.setStyleSheet("background-color: transparent; border-radius: 25px; border: 2px solid #333;")

        friend_btn.clicked.connect(lambda: self.open_chat_with(friend_name))
        self.friends_layout.addWidget(friend_btn)

    def open_chat_with(self, friend_name):
        """Открывает чат с указанным пользователем и закрывает групповой чат"""
        print(f"[CHAT] Opening personal chat with {friend_name}")

        # Проверяем, является ли пользователь другом
        if friend_name not in self.friends:
            print(f"[ERROR] Cannot open chat with non-friend {friend_name}")
            return

        # Закрываем групповой чат при открытии личного
        if self.current_group:
            print(f"[CHAT] Leaving group {self.current_group['name']} to open personal chat")
            self.client.leave_group_chat(self.current_group['id'])
            self.current_group = None

        # Переключаемся на экран чата, если был открыт стартовый экран
        if self.content_stack.currentIndex() == 0:
            self.content_stack.setCurrentIndex(1)

        self.current_chat_with = friend_name
        # Обновляем заголовок чата с именем собеседника
        self.update_chat_header(friend_name)
        self.text_display.clear()
        self.setWindowTitle(f"Chat with {friend_name}")

        # Всегда инициализируем чат при открытии
        self.chat_initialized[friend_name] = True
        # Убедимся, что директория downloads существует
        os.makedirs("downloads", exist_ok=True)

        # Обновляем отображение чата
        self.refresh_chat()

    def open_group_chat(self, group_data):
        """Открывает чат группы и закрывает личный чат"""
        print(f"[GROUP] Opening group chat: {group_data['name']}")

        # Закрываем личный чат при открытии группового
        if self.current_chat_with:
            print(f"[CHAT] Closing personal chat with {self.current_chat_with} to open group chat")
            self.current_chat_with = None

        # Переключаемся на экран чата
        if self.content_stack.currentIndex() == 0:
            self.content_stack.setCurrentIndex(1)

        # Покидаем предыдущую группу, если была открыта
        if self.current_group and self.current_group['id'] != group_data['id']:
            self.client.leave_group_chat(self.current_group['id'])

        # Устанавливаем текущую группу
        self.current_group = group_data

        # Присоединяемся к групповому чату
        self.client.join_group_chat(group_data['id'])

        # Обновляем заголовок чата
        self.update_chat_header_for_group(group_data)

        # Очищаем текстовое поле и загружаем сообщения группы
        self.text_display.clear()
        self.load_group_messages(group_data['id'])

        self.setWindowTitle(f"Группа: {group_data['name']}")

    def update_chat_header(self, friend_name):
        """Обновляет заголовок чата с именем собеседника, статусом с цветным индикатором и кнопкой поиска"""
        if friend_name:
            # Очищаем текущий макет заголовка
            while self.chat_header_layout.count():
                item = self.chat_header_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

            # Создаем контейнер для имени и статуса
            name_status_widget = QtWidgets.QWidget()
            name_status_layout = QtWidgets.QVBoxLayout(name_status_widget)
            name_status_layout.setContentsMargins(0, 0, 0, 0)
            name_status_layout.setSpacing(2)

            # Имя пользователя
            self.chat_header = QtWidgets.QLabel(f"{friend_name}")
            self.chat_header.setAlignment(QtCore.Qt.AlignCenter)
            self.chat_header.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
            self.chat_header.setStyleSheet("color: #333333;")

            # Контейнер для статуса с индикатором
            status_container = QtWidgets.QWidget()
            status_layout = QtWidgets.QHBoxLayout(status_container)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setSpacing(5)
            status_layout.setAlignment(QtCore.Qt.AlignCenter)

            # Цветной индикатор статуса (кружок)
            self.status_indicator = QtWidgets.QLabel("●")
            self.status_indicator.setFont(QtGui.QFont("Arial", 12))
            self.status_indicator.setStyleSheet("color: #FF5722;")  # Красный по умолчанию (не в сети)

            # Текст статуса
            self.status_label = QtWidgets.QLabel("не в сети")
            self.status_label.setAlignment(QtCore.Qt.AlignCenter)
            self.status_label.setFont(QtGui.QFont("Arial", 10))
            self.status_label.setStyleSheet("color: #666666;")

            # Добавляем индикатор и текст в контейнер статуса
            status_layout.addWidget(self.status_indicator)
            status_layout.addWidget(self.status_label)

            name_status_layout.addWidget(self.chat_header)
            name_status_layout.addWidget(status_container)

            # Добавляем кнопку поиска
            self.header_search_btn = QtWidgets.QPushButton("🔍")
            self.header_search_btn.setFixedSize(30, 30)
            self.header_search_btn.setFont(QtGui.QFont("Arial", 12))
            self.header_search_btn.setStyleSheet("background: transparent; border: none;")
            self.header_search_btn.setToolTip("Поиск по сообщениям")
            self.header_search_btn.clicked.connect(self.toggle_search_bar)

            # Добавляем элементы в макет заголовка
            self.chat_header_layout.addStretch()
            self.chat_header_layout.addWidget(name_status_widget)
            self.chat_header_layout.addStretch()
            self.chat_header_layout.addWidget(self.header_search_btn)

            self.chat_header_panel.show()

            # Запрашиваем текущий статус пользователя
            self.request_user_status(friend_name)
        else:
            self.chat_header.clear()
            self.chat_header_panel.hide()

    def request_user_status(self, username):
        """Запрашивает статус пользователя у сервера"""
        status_request = f"STATUS_REQUEST:{self.username}:{username}"
        self.client.send_message(status_request)

    def update_user_status(self, username, status):
        """Обновляет отображение статуса пользователя с цветным индикатором"""
        if (hasattr(self, 'status_label') and hasattr(self, 'status_indicator') and
                self.current_chat_with == username):

            if status == "online":
                # Зеленый кружок и текст для статуса "в сети"
                self.status_indicator.setStyleSheet("color: #4CAF50;")  # Зеленый
                self.status_label.setText("в сети")
                self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            else:
                # Красный кружок и серый текст для статуса "не в сети"
                self.status_indicator.setStyleSheet("color: #FF5722;")  # Красный
                self.status_label.setText("не в сети")
                self.status_label.setStyleSheet("color: #666666;")

    def close_current_chat(self):
        """Закрывает текущий чат и показывает стартовый экран"""
        # Скрываем панель поиска при закрытии чата
        if hasattr(self, 'search_bar') and self.search_bar.isVisible():
            self.search_bar.hide()
            self.search_bar.clear_highlights()

        # разделяем закрытие группового и личного чата
        if self.current_group:
            print(f"[CHAT] Leaving group: {self.current_group['name']}")
            self.client.leave_group_chat(self.current_group['id'])
            self.current_group = None

        if self.current_chat_with:
            print(f"[CHAT] Closing personal chat with: {self.current_chat_with}")
            self.current_chat_with = None

        self.text_display.clear()
        self.setWindowTitle("Voice Chat")
        self.content_stack.setCurrentIndex(0)
        self.update_chat_header(None)
        self.chat_header_panel.hide()

    def handle_incoming_message(self, sender, content):
        print(f"[INCOMING] Message from {sender}: {content}")

        # Проверяем, является ли отправитель другом
        if sender not in self.friends:
            print(f"[FILTER] Ignored message from non-friend {sender}")
            return

        # Если это новый чат, инициализируем его
        if sender not in self.chat_initialized:
            self.chat_initialized[sender] = True
            print(f"[CHAT] Initialized chat with {sender}")

    def open_profile_dialog(self, event=None):
        """Открывает диалог управления профилем"""
        if self.connection:
            dialog = ProfileDialog(self.connection, self.username, self.client, self)
            dialog.profile_updated.connect(self.update_profile)
            dialog.exec_()

    def update_profile(self, profile_data):
        """Обновляет профиль пользователя в интерфейсе"""
        # Обновляем аватар, если он был изменен
        if profile_data.get("avatar_path") and os.path.exists(profile_data["avatar_path"]):
            try:
                pixmap = QtGui.QPixmap(profile_data["avatar_path"])
                if not pixmap.isNull():
                    # Масштабируем и обрезаем до круга
                    pixmap = pixmap.scaled(
                        80, 80,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation
                    )

                    # Создаем круглую маску
                    mask = QtGui.QPixmap(80, 80)
                    mask.fill(QtCore.Qt.transparent)
                    painter = QtGui.QPainter(mask)
                    painter.setRenderHint(QtGui.QPainter.Antialiasing)
                    painter.setBrush(QtCore.Qt.white)
                    painter.drawEllipse(0, 0, 80, 80)
                    painter.end()

                    # Применяем маску
                    rounded_pixmap = QtGui.QPixmap(pixmap.size())
                    rounded_pixmap.fill(QtCore.Qt.transparent)
                    painter = QtGui.QPainter(rounded_pixmap)
                    painter.setRenderHint(QtGui.QPainter.Antialiasing)
                    painter.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
                    painter.drawPixmap(0, 0, mask)
                    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
                    painter.drawPixmap(0, 0, pixmap)
                    painter.end()

                    # Устанавливаем аватар
                    self.avatar_icon.setPixmap(rounded_pixmap)
                    self.avatar_icon.setText("")

                    # Устанавливаем прозрачный фон для аватара
                    self.avatar_frame.setStyleSheet(
                        "background-color: transparent; border-radius: 15px; border: 2px solid #9370DB;")
            except Exception as e:
                print(f"[ERROR] Failed to update avatar: {e}")
        else:
            # Если аватар был удален или не существует, сбрасываем на стандартный
            self.avatar_icon.setPixmap(QtGui.QPixmap())
            self.avatar_icon.setText("👤")
            self.avatar_icon.setFont(QtGui.QFont("Arial", 30))
            self.avatar_frame.setStyleSheet(
                "background-color: #d8c4eb; border-radius: 15px; border: 2px solid #9370DB;")


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 5555
    app = QtWidgets.QApplication(sys.argv)
    username = "User"
    if len(sys.argv) > 1:
        username = sys.argv[1]
    client = ChatClient(host, port)
    window = ChatWindow(client, username)
    window.show()
    sys.exit(app.exec_())