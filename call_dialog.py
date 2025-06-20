import sys
from PyQt5 import QtWidgets, QtCore, QtGui
import pyaudio
import threading
import socket
import json
import time
import os
from screen_sharing_window import ScreenSharingWindow


class CallDialog(QtWidgets.QDialog):
    call_ended = QtCore.pyqtSignal(int)  # Сигнал с длительностью звонка в секундах
    call_accepted = QtCore.pyqtSignal()
    call_rejected = QtCore.pyqtSignal()
    mic_muted = QtCore.pyqtSignal(bool)  # Сигнал о состоянии микрофона
    speaker_muted = QtCore.pyqtSignal(bool)  # Сигнал о состоянии звука

    def __init__(self, username, friend_name, is_caller=True, parent=None):
        super().__init__(parent)
        self.username = username
        self.friend_name = friend_name
        self.is_caller = is_caller
        self.is_call_active = False
        self.screen_sharing_window = None
        self.is_screen_sharing = False
        self.is_mic_muted = False
        self.is_speaker_muted = False
        self.is_camera_on = False
        self.call_start_time = None
        self.call_duration = 0
        self.parent = parent  # родительский виджет для доступа к его методам

        self.setWindowTitle("Звонок")
        self.resize(400, 300)
        self.setStyleSheet("background-color: #d9d9d9; border-radius: 10px;")

        # Основной макет
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # Кнопка "Назад"
        self.back_btn = QtWidgets.QPushButton("←")
        self.back_btn.setFixedSize(30, 30)
        self.back_btn.setStyleSheet("""
            background-color: #333333;
            color: white;
            border-radius: 15px;
            font-size: 16px;
            font-weight: bold;
        """)
        self.back_btn.clicked.connect(self.close)

        back_layout = QtWidgets.QHBoxLayout()
        back_layout.addWidget(self.back_btn)
        back_layout.addStretch()
        self.layout.addLayout(back_layout)

        # Аватар пользователя
        self.avatar_frame = QtWidgets.QFrame()
        self.avatar_frame.setFixedSize(80, 80)
        self.avatar_frame.setStyleSheet("background-color: #4CAF50; border-radius: 40px; border: none;")

        avatar_layout = QtWidgets.QVBoxLayout(self.avatar_frame)
        avatar_layout.setContentsMargins(0, 0, 0, 0)

        self.avatar_icon = QtWidgets.QLabel()
        self.avatar_icon.setAlignment(QtCore.Qt.AlignCenter)
        self.avatar_icon.setStyleSheet("border: none; background: transparent;")
        self.avatar_icon.setText("👤")
        self.avatar_icon.setFont(QtGui.QFont("Arial", 30))
        avatar_layout.addWidget(self.avatar_icon)

        avatar_container = QtWidgets.QHBoxLayout()
        avatar_container.addStretch()
        avatar_container.addWidget(self.avatar_frame)
        avatar_container.addStretch()
        self.layout.addLayout(avatar_container)

        # Загрузка аватара пользователя, если родительский виджет имеет метод load_user_avatar
        if hasattr(parent, 'connection') and hasattr(parent, 'load_user_avatar'):
            has_avatar = parent.load_user_avatar(friend_name, self.avatar_icon, self.avatar_frame)
            if has_avatar:
                self.avatar_frame.setStyleSheet("background-color: transparent; border-radius: 40px;")

        # Имя пользователя
        self.name_label = QtWidgets.QLabel(self.friend_name)
        self.name_label.setAlignment(QtCore.Qt.AlignCenter)
        self.name_label.setFont(QtGui.QFont("Arial", 16, QtGui.QFont.Bold))
        self.name_label.setStyleSheet("color: #333333;")
        self.layout.addWidget(self.name_label)

        # Статус звонка
        self.status_label = QtWidgets.QLabel()
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_label.setFont(QtGui.QFont("Arial", 12))
        self.status_label.setStyleSheet("color: #666666;")
        self.layout.addWidget(self.status_label)

        # Таймер звонка
        self.timer_label = QtWidgets.QLabel("00:00")
        self.timer_label.setAlignment(QtCore.Qt.AlignCenter)
        self.timer_label.setFont(QtGui.QFont("Arial", 14))
        self.timer_label.setStyleSheet("color: #333333;")
        self.timer_label.hide()  # Скрыть до начала звонка
        self.layout.addWidget(self.timer_label)

        # Иконка микрофона
        self.mic_icon = QtWidgets.QLabel()
        self.mic_icon.setAlignment(QtCore.Qt.AlignCenter)
        self.mic_icon.setText("🎤")
        self.mic_icon.setFont(QtGui.QFont("Arial", 16))
        self.layout.addWidget(self.mic_icon)

        # Кнопка завершения звонка
        self.call_btn_frame = QtWidgets.QFrame()
        self.call_btn_frame.setFixedSize(60, 60)
        self.call_btn_frame.setStyleSheet("background-color: #FF5252; border-radius: 30px; border: none;")

        call_btn_layout = QtWidgets.QVBoxLayout(self.call_btn_frame)
        call_btn_layout.setContentsMargins(0, 0, 0, 0)

        call_icon = QtWidgets.QLabel()
        call_icon.setAlignment(QtCore.Qt.AlignCenter)
        call_icon.setStyleSheet("border: none;")
        call_icon.setText("📞")
        call_icon.setFont(QtGui.QFont("Arial", 24))
        call_btn_layout.addWidget(call_icon)

        call_btn_container = QtWidgets.QHBoxLayout()
        call_btn_container.addStretch()
        call_btn_container.addWidget(self.call_btn_frame)
        call_btn_container.addStretch()
        self.layout.addLayout(call_btn_container)

        # Кнопки управления звонком - создаем контейнер для них
        self.controls_container = QtWidgets.QWidget()
        self.controls_layout = QtWidgets.QHBoxLayout(self.controls_container)
        self.controls_layout.setSpacing(10)
        self.controls_layout.setAlignment(QtCore.Qt.AlignCenter)

        # Кнопка демонстрации экрана
        self.screen_btn = self.create_control_button("📺", "Демонстрация экрана")
        self.screen_btn.clicked.connect(self.toggle_screen_sharing)
        self.controls_layout.addWidget(self.screen_btn)

        # Кнопка звука
        self.sound_btn = self.create_control_button("🔊", "Звук")
        self.sound_btn.clicked.connect(self.toggle_speaker)
        self.controls_layout.addWidget(self.sound_btn)

        # Кнопка микрофона
        self.mic_btn = self.create_control_button("🎤", "Микрофон")
        self.mic_btn.clicked.connect(self.toggle_microphone)
        self.controls_layout.addWidget(self.mic_btn)

        self.layout.addWidget(self.controls_container)

        # Кнопки принять/отклонить для входящего звонка
        self.answer_container = QtWidgets.QWidget()
        self.answer_layout = QtWidgets.QHBoxLayout(self.answer_container)
        self.answer_layout.setSpacing(20)
        self.answer_layout.setAlignment(QtCore.Qt.AlignCenter)

        # Кнопка принять звонок
        self.accept_btn = QtWidgets.QPushButton()
        self.accept_btn.setFixedSize(60, 60)
        self.accept_btn.setStyleSheet("background-color: #4CAF50; border-radius: 30px;")
        accept_layout = QtWidgets.QVBoxLayout(self.accept_btn)
        accept_layout.setContentsMargins(0, 0, 0, 0)
        accept_icon = QtWidgets.QLabel("📞")
        accept_icon.setAlignment(QtCore.Qt.AlignCenter)
        accept_icon.setFont(QtGui.QFont("Arial", 24))
        accept_layout.addWidget(accept_icon)
        self.accept_btn.clicked.connect(self.accept_call)

        # Кнопка отклонить звонок
        self.reject_btn = QtWidgets.QPushButton()
        self.reject_btn.setFixedSize(60, 60)
        self.reject_btn.setStyleSheet("background-color: #FF5252; border-radius: 30px;")
        reject_layout = QtWidgets.QVBoxLayout(self.reject_btn)
        reject_layout.setContentsMargins(0, 0, 0, 0)
        reject_icon = QtWidgets.QLabel("📞")
        reject_icon.setAlignment(QtCore.Qt.AlignCenter)
        reject_icon.setFont(QtGui.QFont("Arial", 24))
        reject_layout.addWidget(reject_icon)
        self.reject_btn.clicked.connect(self.reject_call)

        self.answer_layout.addWidget(self.accept_btn)
        self.answer_layout.addWidget(self.reject_btn)

        self.layout.addWidget(self.answer_container)

        # Настраиваем начальное состояние в зависимости от типа звонка
        if is_caller:
            # Исходящий звонок
            self.status_label.setText("Вызов...")
            self.answer_container.hide()  # Скрываем кнопки принять/отклонить
            self.controls_container.hide()  # Скрываем кнопки управления до начала звонка
            self.call_btn_frame.mousePressEvent = lambda event: self.end_call()
        else:
            # Входящий звонок
            self.status_label.setText("Входящий вызов")
            self.call_btn_frame.hide()  # Скрываем кнопку завершения
            self.controls_container.hide()  # Скрываем кнопки управления

        # Таймер для обновления длительности звонка
        self.call_timer = QtCore.QTimer(self)
        self.call_timer.timeout.connect(self.update_call_duration)

        # Подключаем обработчик закрытия окна
        self.finished.connect(self.on_dialog_closed)

    def create_control_button(self, icon_text, tooltip):
        """Создает кнопку управления звонком"""
        btn = QtWidgets.QPushButton()
        btn.setFixedSize(50, 50)
        btn.setStyleSheet("""
        background-color: #e0e0e0; 
        border-radius: 25px; 
        border: 1px solid #999;
    """)
        btn.setToolTip(tooltip)

        layout = QtWidgets.QVBoxLayout(btn)
        layout.setContentsMargins(0, 0, 0, 0)

        icon = QtWidgets.QLabel(icon_text)
        icon.setAlignment(QtCore.Qt.AlignCenter)
        icon.setFont(QtGui.QFont("Arial", 16))
        layout.addWidget(icon)

        return btn

    def toggle_microphone(self):
        """Включение/выключение микрофона"""
        self.is_mic_muted = not self.is_mic_muted
        if self.is_mic_muted:
            self.mic_btn.setStyleSheet("background-color: #FF5252; border-radius: 25px; border: 1px solid #999;")
            # Обновляем иконку микрофона, чтобы показать, что он выключен
            self.mic_icon.setText("🎤❌")
        else:
            self.mic_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 25px; border: 1px solid #999;")
            # Возвращаем обычную иконку микрофона
            self.mic_icon.setText("🎤")
        # Отправляем сигнал о состоянии микрофона
        self.mic_muted.emit(self.is_mic_muted)

    def toggle_speaker(self):
        """Включение/выключение звука"""
        self.is_speaker_muted = not self.is_speaker_muted
        if self.is_speaker_muted:
            self.sound_btn.setStyleSheet("background-color: #FF5252; border-radius: 25px; border: 1px solid #999;")
            # Обновляем текст кнопки звука
            child = self.sound_btn.findChild(QtWidgets.QLabel)
            if child:
                child.setText("🔇")
        else:
            self.sound_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 25px; border: 1px solid #999;")
            # Возвращаем обычный текст кнопки звука
            child = self.sound_btn.findChild(QtWidgets.QLabel)
            if child:
                child.setText("🔊")
        # Отправляем сигнал о состоянии звука
        self.speaker_muted.emit(self.is_speaker_muted)

    def toggle_camera(self):
        """Включение/выключение камеры"""
        self.is_camera_on = not self.is_camera_on
        if self.is_camera_on:
            self.camera_btn.setStyleSheet("background-color: #4CAF50; border-radius: 25px; border: 1px solid #999;")
        else:
            self.camera_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 25px; border: 1px solid #999;")

    def toggle_screen_sharing(self):
        """Включение/выключение демонстрации экрана через отдельное соединение"""
        self.is_screen_sharing = not self.is_screen_sharing

        if self.is_screen_sharing:
            # Начинаем демонстрацию экрана
            self.screen_btn.setStyleSheet("background-color: #4CAF50; border-radius: 25px; border: 1px solid #999;")

            # Отправляем сигнал о начале демонстрации через отдельное соединение
            if hasattr(self.parent, 'client') and hasattr(self.parent.client, 'call_recipient'):
                self.parent.client.send_screen_control_signal("start")

                # Создаем и показываем окно демонстрации экрана
                self.screen_sharing_window = ScreenSharingWindow(
                    self.username,
                    self.parent.client.call_recipient,
                    is_sender=True,
                    parent=self
                )
                self.screen_sharing_window.start_sharing(self.parent.client.get_screen_socket())
                self.screen_sharing_window.show()
        else:
            # Завершаем демонстрацию экрана
            self.screen_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 25px; border: 1px solid #999;")

            # Отправляем сигнал о завершении демонстрации через отдельное соединение
            if hasattr(self.parent, 'client'):
                self.parent.client.send_screen_control_signal("stop")

            # Закрываем окно демонстрации экрана
            if self.screen_sharing_window:
                self.screen_sharing_window.close()
                self.screen_sharing_window = None

    def accept_call(self):
        """Принять входящий звонок"""
        self.is_call_active = True
        self.answer_container.hide()
        self.call_btn_frame.show()
        self.controls_container.show()
        self.status_label.setText("Звонок начался")

        # Запускаем таймер звонка
        self.call_start_time = time.time()
        self.timer_label.show()
        self.call_timer.start(1000)  # Обновляем каждую секунду

        # Настраиваем кнопку завершения звонка для принимающего
        self.call_btn_frame.mousePressEvent = lambda event: self.end_call()

        # Отправляем сигнал о принятии звонка
        self.call_accepted.emit()

    def call_was_accepted(self):
        """Вызывается, когда собеседник принял звонок"""
        self.is_call_active = True
        self.status_label.setText("Звонок начался")
        self.controls_container.show()

        # Запускаем таймер звонка
        self.call_start_time = time.time()
        self.timer_label.show()
        self.call_timer.start(1000)  # Обновляем каждую секунду

    def reject_call(self):
        """Отклонить входящий звонок"""
        self.call_rejected.emit()
        self.close()

    def end_call(self):
        """Завершить активный звонок"""
        if self.is_call_active:
            # Останавливаем таймер
            self.call_timer.stop()
            # Вычисляем длительность звонка
            self.call_duration = int(time.time() - self.call_start_time)
        else:
            # Если звонок не был активен, устанавливаем длительность 0
            self.call_duration = 0

        # Завершаем демонстрацию экрана при завершении звонка
        if self.is_screen_sharing:
            self.toggle_screen_sharing()

        # Сбрасываем статусы mute
        self.is_mic_muted = False
        self.is_speaker_muted = False
        self.mic_muted.emit(False)  # Уведомляем клиент о сбросе микрофона
        self.speaker_muted.emit(False)  # Уведомляем клиент о сбросе звука

        self.is_call_active = False
        self.call_ended.emit(self.call_duration)
        self.close()

    def update_call_duration(self):
        """Обновляет отображение длительности звонка"""
        if self.call_start_time:
            duration = int(time.time() - self.call_start_time)
            minutes = duration // 60
            seconds = duration % 60
            self.timer_label.setText(f"{minutes:02d}:{seconds:02d}")
            self.call_duration = duration

    def on_dialog_closed(self):
        """Обработчик закрытия диалога"""
        self.call_timer.stop()
        if self.is_call_active:
            self.end_call()
        else:
            # Если звонок не был активен, но диалог закрывается, отправляем сигнал с нулевой длительностью
            self.call_ended.emit(0)


class GroupCallDialog:
    """Диалог группового звонка"""

    def __init__(self, group_data, username, client, parent=None):
        self.group_data = group_data
        self.username = username
        self.client = client
        self.parent = parent
        self.participants = set()
        self.is_in_call = False
        self.is_mic_muted = False
        self.is_speaker_muted = False
        self.audio_started = False
        self.audio_active = False
        self.is_screen_sharing = False
        self.screen_sharing_window = None

        # Создаем окно группового звонка
        self.dialog = QtWidgets.QDialog(parent)
        self.dialog.setWindowTitle(f"Групповой звонок - {group_data['name']}")
        self.dialog.resize(400, 500)
        self.setup_ui()

    def setup_ui(self):
        """Настройка интерфейса группового звонка"""
        layout = QtWidgets.QVBoxLayout(self.dialog)

        # Заголовок с названием группы
        title = QtWidgets.QLabel(f"🎤 {self.group_data['name']}")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setFont(QtGui.QFont("Arial", 16, QtGui.QFont.Bold))
        layout.addWidget(title)

        # Список участников звонка
        self.participants_label = QtWidgets.QLabel("Участники звонка:")
        self.participants_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        layout.addWidget(self.participants_label)

        self.participants_list = QtWidgets.QListWidget()
        self.participants_list.setMaximumHeight(150)
        layout.addWidget(self.participants_list)

        # Кнопки управления
        controls_layout = QtWidgets.QHBoxLayout()

        # Кнопка микрофона
        self.mic_btn = QtWidgets.QPushButton("🎤")
        self.mic_btn.setFixedSize(50, 50)
        self.mic_btn.setStyleSheet("background-color: #4CAF50; border-radius: 25px;")
        self.mic_btn.clicked.connect(self.toggle_microphone)
        controls_layout.addWidget(self.mic_btn)

        # Кнопка звука
        self.speaker_btn = QtWidgets.QPushButton("🔊")
        self.speaker_btn.setFixedSize(50, 50)
        self.speaker_btn.setStyleSheet("background-color: #4CAF50; border-radius: 25px;")
        self.speaker_btn.clicked.connect(self.toggle_speaker)
        controls_layout.addWidget(self.speaker_btn)

        # Кнопка демонстрации экрана
        self.screen_btn = QtWidgets.QPushButton("📺")
        self.screen_btn.setFixedSize(50, 50)
        self.screen_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 25px;")
        self.screen_btn.setToolTip("Демонстрация экрана")
        self.screen_btn.clicked.connect(self.toggle_group_screen_sharing)
        controls_layout.addWidget(self.screen_btn)

        # Кнопка завершения звонка
        self.end_btn = QtWidgets.QPushButton("📞")
        self.end_btn.setFixedSize(50, 50)
        self.end_btn.setStyleSheet("background-color: #FF5252; border-radius: 25px;")
        self.end_btn.clicked.connect(self.leave_call)
        controls_layout.addWidget(self.end_btn)

        layout.addLayout(controls_layout)

    def start_group_call_audio(self):
        """Запуск аудио для группового звонка"""
        if not self.audio_started:
            self.client.start_group_call_audio(self.group_data['id'])
            self.audio_started = True
            print(f"[GROUP CALL] Started audio for group {self.group_data['name']}")

    def stop_group_call_audio(self):
        """Остановка аудио группового звонка"""
        if self.audio_started:
            self.client.stop_group_call_audio()
            self.audio_started = False
            print(f"[GROUP CALL] Stopped audio for group {self.group_data['name']}")

    def toggle_group_screen_sharing(self):
        """Переключает демонстрацию экрана в групповом звонке"""
        self.is_screen_sharing = not self.is_screen_sharing

        if self.is_screen_sharing:
            # Начинаем демонстрацию экрана для группы
            self.screen_btn.setStyleSheet("background-color: #4CAF50; border-radius: 25px;")

            # Отправляем сигнал через основной сокет
            signal = f"GROUP_SCREEN_CONTROL:start:{self.group_data['id']}:{self.username}:{time.time()}"
            self.client.send_message(signal)
            print(f"[GROUP SCREEN] Sent start signal: {signal}")

            # Создаем окно демонстрации экрана
            from screen_sharing_window import ScreenSharingWindow
            self.screen_sharing_window = ScreenSharingWindow(
                self.username,
                f"Группа: {self.group_data['name']}",
                is_sender=True,
                parent=self.dialog
            )

            # Запускаем демонстрацию для группы
            self.screen_sharing_window.start_group_sharing(
                self.client.get_screen_socket(),
                self.group_data['id']
            )
            self.screen_sharing_window.show()

        else:
            # Завершаем демонстрацию экрана
            self.screen_btn.setStyleSheet("background-color: #e0e0e0; border-radius: 25px;")

            # Отправляем сигнал остановки
            signal = f"GROUP_SCREEN_CONTROL:stop:{self.group_data['id']}:{self.username}:{time.time()}"
            self.client.send_message(signal)
            print(f"[GROUP SCREEN] Sent stop signal: {signal}")

            # Закрываем окно демонстрации экрана
            if self.screen_sharing_window:
                self.screen_sharing_window.close()
                self.screen_sharing_window = None

    def update_participants(self, participants_list):
        """Обновляет список участников звонка"""
        self.participants = set(participants_list)
        self.participants_list.clear()

        for participant in sorted(participants_list):
            item = QtWidgets.QListWidgetItem(f"🎤 {participant}")
            if participant == self.username:
                item.setText(f"🎤 {participant} (вы)")
                item.setBackground(QtGui.QColor(200, 255, 200))
            self.participants_list.addItem(item)

        # Обновляем заголовок с количеством участников
        count = len(participants_list)
        self.participants_label.setText(f"Участники звонка ({count}):")

    def toggle_microphone(self):
        """переключение микрофона"""
        self.is_mic_muted = not self.is_mic_muted
        if self.is_mic_muted:
            self.mic_btn.setStyleSheet("background-color: #FF5252; border-radius: 25px;")
            self.mic_btn.setText("🎤❌")
            print(f"[GROUP CALL] Microphone MUTED for {self.username}")
        else:
            self.mic_btn.setStyleSheet("background-color: #4CAF50; border-radius: 25px;")
            self.mic_btn.setText("🎤")
            print(f"[GROUP CALL] Microphone UNMUTED for {self.username}")

        # Уведомляем клиент о состоянии микрофона
        if hasattr(self.client, 'set_mic_muted'):
            self.client.set_mic_muted(self.is_mic_muted)

    def toggle_speaker(self):
        """переключение звука"""
        self.is_speaker_muted = not self.is_speaker_muted
        if self.is_speaker_muted:
            self.speaker_btn.setStyleSheet("background-color: #FF5252; border-radius: 25px;")
            self.speaker_btn.setText("🔇")
            print(f"[GROUP CALL] Speaker MUTED for {self.username}")
        else:
            self.speaker_btn.setStyleSheet("background-color: #4CAF50; border-radius: 25px;")
            self.speaker_btn.setText("🔊")
            print(f"[GROUP CALL] Speaker UNMUTED for {self.username}")

        # Уведомляем клиент о состоянии звука
        if hasattr(self.client, 'set_speaker_muted'):
            self.client.set_speaker_muted(self.is_speaker_muted)

    def leave_call(self):
        if self.is_screen_sharing:
            self.toggle_group_screen_sharing()
        if self.is_in_call:
            print(f"[GROUP CALL] {self.username} leaving call in group {self.group_data['name']}")

            # Сначала останавливаем аудио
            if hasattr(self.client, 'stop_group_call_audio'):
                self.client.stop_group_call_audio()

            # Отправляем сигнал о выходе
            signal = f"GROUP_CALL_SIGNAL:leave:{self.group_data['id']}:{self.username}:{time.time()}"
            self.client.send_message(signal)

            # Принудительно сбрасываем все флаги звонка
            self.client.is_in_call = False
            self.client.is_in_group_call = False
            self.client.current_group_call_id = None

        # Сбрасываем статусы mute
        self.is_mic_muted = False
        self.is_speaker_muted = False
        if hasattr(self.client, 'set_mic_muted'):
            self.client.set_mic_muted(False)  # Уведомляем клиент о сбросе микрофона
        if hasattr(self.client, 'set_speaker_muted'):
            self.client.set_speaker_muted(False)  # Уведомляем клиент о сбросе звука

        self.is_in_call = False
        self.dialog.close()

    def show(self):
        """Показать диалог"""
        self.dialog.show()

    def close(self):
        """Закрыть диалог"""
        self.leave_call()