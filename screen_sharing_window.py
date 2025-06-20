import sys
from PyQt5 import QtWidgets, QtCore, QtGui
import numpy as np
import cv2
import pyautogui
import time
import threading
import socket
import struct
import zlib
import base64


class ScreenSharingWindow(QtWidgets.QDialog):
    def __init__(self, username, friend_name, is_sender=False, parent=None):
        super().__init__(parent)
        self.username = username
        self.friend_name = friend_name
        self.is_sender = is_sender
        self.is_active = False
        self.capture_thread = None
        self.client_socket = None
        self.parent = parent

        self.is_group_sharing = False
        self.group_id = None

        # Настройки захвата экрана
        self.fps = 15  # Снижаем FPS
        self.quality = 30  # Снижаем качество сжатия JPEG
        self.scale_factor = 0.5  # Уменьшаем масштаб
        self.frame_counter = 0
        self.chunk_size = 2000
        self.is_group_receiver = False
        self.group_id = None
        self.screen_sender = None
        self.group_screen_buffers = {}
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Демонстрация экрана")
        self.resize(800, 600)
        self.setStyleSheet("background-color: #333333;")

        # Основной макет
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Метка для отображения экрана
        self.screen_label = QtWidgets.QLabel()
        self.screen_label.setAlignment(QtCore.Qt.AlignCenter)
        self.screen_label.setStyleSheet("background-color: #000000; border-radius: 5px;")
        self.layout.addWidget(self.screen_label)

        # Панель управления
        self.control_panel = QtWidgets.QWidget()
        self.control_panel.setFixedHeight(50)
        self.control_panel.setStyleSheet("background-color: #444444; border-radius: 10px;")
        self.control_layout = QtWidgets.QHBoxLayout(self.control_panel)

        # Информация о трансляции
        self.info_label = QtWidgets.QLabel()
        if self.is_sender:
            self.info_label.setText(f"Вы демонстрируете экран для {self.friend_name}")
        else:
            self.info_label.setText(f"{self.friend_name} демонстрирует экран")
        self.info_label.setStyleSheet("color: white; font-size: 14px;")
        self.control_layout.addWidget(self.info_label)

        self.control_layout.addStretch()

        # Кнопка завершения демонстрации (только для отправителя)
        if self.is_sender:
            self.stop_btn = QtWidgets.QPushButton("Завершить демонстрацию")
            self.stop_btn.setStyleSheet("""
                background-color: #FF5252; 
                color: white; 
                border-radius: 5px; 
                padding: 8px 15px;
                font-weight: bold;
            """)
            self.stop_btn.clicked.connect(self.stop_sharing)
            self.control_layout.addWidget(self.stop_btn)

        self.layout.addWidget(self.control_panel)

        # Обработчик закрытия окна
        self.finished.connect(self.on_dialog_closed)

    def start_sharing(self, client_socket):
        """Начинает демонстрацию экрана"""
        if self.is_sender:
            self.client_socket = client_socket
            self.is_active = True
            self.capture_thread = threading.Thread(target=self.capture_and_send_screen)
            self.capture_thread.daemon = True
            self.capture_thread.start()

    def capture_and_send_group_screen(self):
        """Захватывает экран и отправляет его всем участникам группы"""
        retry_count = 0
        max_retries = 3

        try:
            while self.is_active and self.is_group_sharing:
                try:
                    start_time = time.time()

                    # Захват экрана
                    screenshot = pyautogui.screenshot()
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                    # Масштабирование
                    h, w = frame.shape[:2]
                    frame = cv2.resize(frame, (int(w * self.scale_factor), int(h * self.scale_factor)))

                    # Отображение в окне отправителя
                    self.display_frame(frame)

                    # Сжатие
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
                    data = buffer.tobytes()

                    # Проверяем размер данных
                    if len(data) > 100000:  # Если больше 100KB, пропускаем кадр
                        print(f"[GROUP SCREEN] Skipping large frame: {len(data)} bytes")
                        time.sleep(1.0 / self.fps)
                        continue

                    encoded_data = base64.b64encode(data).decode('utf-8')
                    chunks = [encoded_data[i:i + self.chunk_size] for i in range(0, len(encoded_data), self.chunk_size)]

                    frame_id = self.frame_counter
                    self.frame_counter += 1

                    # Отправляем с проверкой соединения
                    try:
                        start_msg = f"GROUP_SCREEN_DATA_START:{self.username}:{self.group_id}:{frame_id}:{len(chunks)}"
                        self.client_socket.send(start_msg.encode('utf-8') + b'\n')

                        for i, chunk in enumerate(chunks):
                            if not self.is_active or not self.is_group_sharing:
                                break

                            chunk_msg = f"GROUP_SCREEN_DATA_CHUNK:{self.username}:{self.group_id}:{frame_id}:{i}:{chunk}"
                            self.client_socket.send(chunk_msg.encode('utf-8') + b'\n')
                            time.sleep(0.01)

                        if self.is_active and self.is_group_sharing:
                            end_msg = f"GROUP_SCREEN_DATA_END:{self.username}:{self.group_id}:{frame_id}"
                            self.client_socket.send(end_msg.encode('utf-8') + b'\n')

                        retry_count = 0

                    except ConnectionError as e:
                        print(f"[GROUP SCREEN ERROR] Connection error: {e}")
                        retry_count += 1
                        if retry_count >= max_retries:
                            print(f"[GROUP SCREEN ERROR] Max retries reached, stopping")
                            break
                        time.sleep(1)
                        continue

                    # Поддержание FPS
                    elapsed = time.time() - start_time
                    sleep_time = max(0, 1.0 / self.fps - elapsed)
                    time.sleep(sleep_time)

                except Exception as e:
                    print(f"[GROUP SCREEN ERROR] Frame capture error: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        break
                    time.sleep(1)

        except Exception as e:
            print(f"Ошибка группового захвата экрана: {e}")
        finally:
            self.is_active = False
            self.is_group_sharing = False

    def setup_group_receiving(self, group_id, sender):
        """настройка окна для приема групповой демонстрации"""
        try:
            print(f"[GROUP SCREEN WINDOW] Setting up receiving from {sender} for group {group_id}")

            # Проверяем, что мы в главном потоке
            from PyQt5.QtCore import QThread
            from PyQt5.QtWidgets import QApplication
            if not QThread.currentThread() == QApplication.instance().thread():
                print(f"[GROUP SCREEN WINDOW ERROR] setup_group_receiving called from wrong thread!")
                return

            self.group_id = group_id
            self.screen_sender = sender
            self.is_group_receiver = True
            self.is_active = True

            # Инициализируем буферы для приема данных
            self.group_screen_buffers = {}

            # Обновляем информационную метку
            if hasattr(self, 'info_label'):
                self.info_label.setText(f"Демонстрация экрана от {sender} в группе")

            print(f"[GROUP SCREEN WINDOW] Setup complete for receiving from {sender}")

        except Exception as e:
            print(f"[GROUP SCREEN WINDOW ERROR] Error in setup_group_receiving: {e}")
            import traceback
            traceback.print_exc()

    def start_group_sharing(self, client_socket, group_id):
        """Начинает групповую демонстрацию экрана"""
        if self.is_sender:
            self.client_socket = client_socket
            self.group_id = group_id
            self.is_group_sharing = True
            self.is_active = True

            # Обновляем информационную метку
            self.info_label.setText(f"Вы демонстрируете экран для группы")

            self.capture_thread = threading.Thread(target=self.capture_and_send_group_screen)
            self.capture_thread.daemon = True
            self.capture_thread.start()

    def receive_sharing(self, client_socket):
        """Начинает прием демонстрации экрана"""
        if not self.is_sender:
            self.client_socket = client_socket
            self.is_active = True

    def capture_and_send_screen(self):
        """Захватывает экран и отправляет его получателю"""
        retry_count = 0
        max_retries = 3

        try:
            while self.is_active:
                try:
                    start_time = time.time()

                    # Захват экрана
                    screenshot = pyautogui.screenshot()
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                    # Масштабирование
                    h, w = frame.shape[:2]
                    frame = cv2.resize(frame, (int(w * self.scale_factor), int(h * self.scale_factor)))

                    # Отображение в окне отправителя
                    self.display_frame(frame)

                    # Сжатие
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
                    data = buffer.tobytes()

                    # Проверяем размер данных
                    if len(data) > 100000:  # Если больше 100KB, пропускаем кадр
                        print(f"[SCREEN] Skipping large frame: {len(data)} bytes")
                        time.sleep(1.0 / self.fps)
                        continue

                    encoded_data = base64.b64encode(data).decode('utf-8')
                    chunks = [encoded_data[i:i + self.chunk_size] for i in range(0, len(encoded_data), self.chunk_size)]

                    frame_id = self.frame_counter
                    self.frame_counter += 1

                    # Отправляем с проверкой соединения
                    try:
                        start_msg = f"SCREEN_DATA_START:{self.username}:{self.friend_name}:{frame_id}:{len(chunks)}"
                        self.client_socket.send(start_msg.encode('utf-8') + b'\n')

                        for i, chunk in enumerate(chunks):
                            if not self.is_active:  # Проверяем, не остановлена ли передача
                                break

                            chunk_msg = f"SCREEN_DATA_CHUNK:{self.username}:{self.friend_name}:{frame_id}:{i}:{chunk}"
                            self.client_socket.send(chunk_msg.encode('utf-8') + b'\n')
                            time.sleep(0.01)  # Увеличили задержку между частями

                        if self.is_active:
                            end_msg = f"SCREEN_DATA_END:{self.username}:{self.friend_name}:{frame_id}"
                            self.client_socket.send(end_msg.encode('utf-8') + b'\n')

                        retry_count = 0  # Сбрасываем счетчик при успешной отправке

                    except ConnectionError as e:
                        print(f"[SCREEN ERROR] Connection error: {e}")
                        retry_count += 1
                        if retry_count >= max_retries:
                            print(f"[SCREEN ERROR] Max retries reached, stopping")
                            break
                        time.sleep(1)  # Ждем перед повтором
                        continue

                    # Поддержание FPS
                    elapsed = time.time() - start_time
                    sleep_time = max(0, 1.0 / self.fps - elapsed)
                    time.sleep(sleep_time)

                except Exception as e:
                    print(f"[SCREEN ERROR] Frame capture error: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        break
                    time.sleep(1)

        except Exception as e:
            print(f"Ошибка захвата экрана: {e}")
        finally:
            self.is_active = False

    def process_group_screen_data(self, message):
        """обработка данных групповой демонстрации экрана"""
        try:
            # Проверяем, активно ли окно
            if not hasattr(self, 'is_active') or not self.is_active:
                print(f"[GROUP SCREEN WINDOW] Window not active, ignoring data")
                return

            # Проверяем, настроено ли окно для групповой демонстрации
            if not hasattr(self, 'is_group_receiver') or not self.is_group_receiver:
                print(f"[GROUP SCREEN WINDOW] Not set up for group receiving, ignoring data")
                return

            print(f"[GROUP SCREEN WINDOW] Processing data: {message[:100]}...")

            if message.startswith("GROUP_SCREEN_DATA_START:"):
                # Обработка начала кадра
                parts = message.split(":", 4)
                if len(parts) >= 5:
                    sender = parts[1]
                    group_id = int(parts[2])
                    frame_id = parts[3]
                    chunks_count = int(parts[4])

                    print(
                        f"[GROUP SCREEN WINDOW] START - sender: {sender}, group: {group_id}, frame: {frame_id}, chunks: {chunks_count}")

                    # Проверяем, что это наша группа и отправитель
                    if not hasattr(self, 'group_id') or self.group_id != group_id:
                        print(
                            f"[GROUP SCREEN WINDOW] Wrong group: expected {getattr(self, 'group_id', 'None')}, got {group_id}")
                        return

                    if not hasattr(self, 'screen_sender') or self.screen_sender != sender:
                        print(
                            f"[GROUP SCREEN WINDOW] Wrong sender: expected {getattr(self, 'screen_sender', 'None')}, got {sender}")
                        return

                    # Создаем буфер для кадра
                    if not hasattr(self, 'group_screen_buffers'):
                        self.group_screen_buffers = {}

                    self.group_screen_buffers[frame_id] = {
                        'chunks': [''] * chunks_count,
                        'received': 0,
                        'total_chunks': chunks_count
                    }
                    print(f"[GROUP SCREEN WINDOW] Created buffer for frame {frame_id} with {chunks_count} chunks")

            elif message.startswith("GROUP_SCREEN_DATA_CHUNK:"):
                # Обработка части кадра
                parts = message.split(":", 5)
                if len(parts) >= 6:
                    sender = parts[1]
                    group_id = int(parts[2])
                    frame_id = parts[3]
                    chunk_id = int(parts[4])
                    chunk_data = parts[5]

                    # Проверяем, что это наша группа и отправитель
                    if not hasattr(self, 'group_id') or self.group_id != group_id:
                        return

                    if not hasattr(self, 'screen_sender') or self.screen_sender != sender:
                        return

                    # Добавляем часть в буфер
                    if hasattr(self, 'group_screen_buffers') and frame_id in self.group_screen_buffers:
                        buffer = self.group_screen_buffers[frame_id]
                        chunk_id_int = int(chunk_id)
                        if 0 <= chunk_id_int < len(buffer['chunks']):
                            buffer['chunks'][chunk_id_int] = chunk_data
                            buffer['received'] += 1

                            # Логируем прогресс для отладки
                            if chunk_id_int % 10 == 0 or buffer['received'] == buffer['total_chunks']:
                                print(
                                    f"[GROUP SCREEN WINDOW] Frame {frame_id}: received {buffer['received']}/{buffer['total_chunks']} chunks")
                    else:
                        print(f"[GROUP SCREEN WINDOW] No buffer for frame {frame_id}")

            elif message.startswith("GROUP_SCREEN_DATA_END:"):
                # Обработка завершения кадра
                parts = message.split(":", 3)
                if len(parts) >= 4:
                    sender = parts[1]
                    group_id = int(parts[2])
                    frame_id = parts[3]

                    print(f"[GROUP SCREEN WINDOW] END - sender: {sender}, group: {group_id}, frame: {frame_id}")

                    # Проверяем, что это наша группа и отправитель
                    if not hasattr(self, 'group_id') or self.group_id != group_id:
                        return

                    if not hasattr(self, 'screen_sender') or self.screen_sender != sender:
                        return

                    # Проверяем, есть ли у нас буфер для этого кадра
                    if hasattr(self, 'group_screen_buffers') and frame_id in self.group_screen_buffers:
                        buffer = self.group_screen_buffers[frame_id]
                        print(
                            f"[GROUP SCREEN WINDOW] Frame {frame_id} complete check: {buffer['received']}/{buffer['total_chunks']}")

                        if buffer['received'] == buffer['total_chunks']:
                            # Собираем полный кадр
                            complete_data = ''.join(buffer['chunks'])
                            print(
                                f"[GROUP SCREEN WINDOW] Assembled complete frame {frame_id}, data length: {len(complete_data)}")

                            # Декодируем и отображаем
                            try:
                                import base64
                                import numpy as np
                                import cv2

                                decoded_data = base64.b64decode(complete_data)
                                np_arr = np.frombuffer(decoded_data, np.uint8)
                                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                                if frame is not None:
                                    self.display_frame(frame)
                                    print(f"[GROUP SCREEN WINDOW] ✓ Displayed frame {frame_id}")
                                else:
                                    print(f"[GROUP SCREEN WINDOW] ✗ Failed to decode frame {frame_id}")

                            except Exception as e:
                                print(f"[GROUP SCREEN WINDOW ERROR] Error decoding frame {frame_id}: {e}")

                            # Удаляем буфер
                            del self.group_screen_buffers[frame_id]
                        else:
                            print(
                                f"[GROUP SCREEN WINDOW] Frame {frame_id} incomplete: {buffer['received']}/{buffer['total_chunks']} chunks")
                    else:
                        print(f"[GROUP SCREEN WINDOW] No buffer found for frame {frame_id}")

        except Exception as e:
            print(f"[GROUP SCREEN WINDOW ERROR] Error processing data: {e}")
            import traceback
            traceback.print_exc()

    def process_screen_data(self, frame_data):
        """Обрабатывает полученные данные экрана"""
        try:
            # Декодируем данные из base64
            decoded_data = base64.b64decode(frame_data)

            # Преобразуем в изображение
            np_arr = np.frombuffer(decoded_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is not None:
                self.display_frame(frame)
        except Exception as e:
            print(f"Ошибка обработки данных экрана: {e}")

    def display_frame(self, frame):
        """функция отображения кадра"""
        try:
            if frame is None:
                print(f"[GROUP SCREEN WINDOW] Cannot display None frame")
                return

            h, w = frame.shape[:2]
            if h == 0 or w == 0:
                print(f"[GROUP SCREEN WINDOW] Invalid frame dimensions: {w}x{h}")
                return

            bytes_per_line = 3 * w

            # Преобразуем BGR (OpenCV) в RGB (Qt)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Создаем QImage из данных numpy
            from PyQt5.QtGui import QImage, QPixmap
            from PyQt5.QtCore import Qt

            q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)

            # Получаем размеры label
            if hasattr(self, 'screen_label'):
                label_size = self.screen_label.size()

                # Масштабируем изображение, сохраняя пропорции
                pixmap = QPixmap.fromImage(q_img)
                scaled_pixmap = pixmap.scaled(
                    label_size.width(),
                    label_size.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                # Устанавливаем изображение
                self.screen_label.setPixmap(scaled_pixmap)
                print(
                    f"[GROUP SCREEN WINDOW] Frame displayed: {w}x{h} -> {scaled_pixmap.width()}x{scaled_pixmap.height()}")
            else:
                print(f"[GROUP SCREEN WINDOW] No screen_label available")

        except Exception as e:
            print(f"[GROUP SCREEN WINDOW ERROR] Error displaying frame: {e}")
            import traceback
            traceback.print_exc()

    def stop_sharing(self):
        """Останавливает демонстрацию экрана"""
        self.is_active = False
        self.is_group_sharing = False

        if self.capture_thread:
            self.capture_thread.join(timeout=1.0)
            self.capture_thread = None

        # Отправляем сигнал о завершении демонстрации
        if self.is_sender and self.client_socket:
            try:
                if self.group_id:
                    # Групповая демонстрация
                    stop_signal = f"GROUP_SCREEN_CONTROL:{self.group_id}:{self.username}:{time.time()}:stop"
                else:
                    # Личная демонстрация (существующий код)
                    stop_signal = f"SCREEN_CONTROL:{self.username}:{self.friend_name}:stop"

                self.client_socket.send(stop_signal.encode('utf-8') + b'\n')
            except Exception as e:
                print(f"Ошибка отправки сигнала завершения демонстрации: {e}")

        # Обновляем кнопку демонстрации экрана в родительском диалоге
        if self.parent and hasattr(self.parent, 'screen_btn'):
            self.parent.screen_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 25px;")
            if hasattr(self.parent, 'is_screen_sharing'):
                self.parent.is_screen_sharing = False

        self.close()

    def on_dialog_closed(self):
        """Обработчик закрытия диалога"""
        self.stop_sharing()