import sys
from PyQt5 import QtWidgets, QtCore, QtGui
import pg8000
import os


class NotificationDialog(QtWidgets.QDialog):
    friendsUpdated = QtCore.pyqtSignal()
    openChatRequested = QtCore.pyqtSignal(str)  # Сигнал для открытия чата
    groupsUpdated = QtCore.pyqtSignal()
    def __init__(self, connection, current_username):
        super().__init__()
        self.connection = connection
        self.current_username = current_username
        self.setWindowTitle("Notifications")
        self.resize(400, 500)
        self.setStyleSheet("background-color: #e0e0e0;")

        # Флаг для отслеживания состояния уведомлений
        self.notifications_enabled = True
        self.load_notification_settings()

        # основа
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # хидер с настройками
        header_layout = QtWidgets.QHBoxLayout()

        # тайтл
        self.title_label = QtWidgets.QLabel("Уведомления")
        self.title_label.setFont(QtGui.QFont("Arial", 16, QtGui.QFont.Bold))
        header_layout.addWidget(self.title_label)

        # кнопка настроек иконка
        self.settings_btn = QtWidgets.QPushButton()
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #d0d0d0;
                border-radius: 15px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #c0c0c0;
            }
        """)
        # Создаем текстовую метку с символом шестеренки
        settings_icon = QtWidgets.QLabel("⚙️")
        settings_icon.setAlignment(QtCore.Qt.AlignCenter)
        settings_icon.setFont(QtGui.QFont("Arial", 14))
        settings_layout = QtWidgets.QVBoxLayout(self.settings_btn)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.addWidget(settings_icon)
        self.settings_btn.setToolTip("Настройки уведомлений")
        self.settings_btn.clicked.connect(self.show_settings)
        header_layout.addWidget(self.settings_btn)

        self.layout.addLayout(header_layout)

        # Создаем вкладки для разных типов уведомлений
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #999;
                border-radius: 5px;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #d0d0d0;
                border: 1px solid #999;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                border-bottom: none;
            }
        """)

        # Вкладка запросов в друзья
        self.friend_requests_tab = QtWidgets.QWidget()
        self.friend_requests_layout = QtWidgets.QVBoxLayout(self.friend_requests_tab)
        self.friend_requests_layout.setContentsMargins(10, 10, 10, 10)
        self.friend_requests_layout.setSpacing(10)

        # Создаем область прокрутки для запросов в друзья
        self.requests_area = QtWidgets.QScrollArea()
        self.requests_area.setWidgetResizable(True)
        self.requests_area.setStyleSheet("background-color: #ffffff; border-radius: 15px;")

        self.requests_widget = QtWidgets.QWidget()
        self.requests_layout = QtWidgets.QVBoxLayout(self.requests_widget)
        self.requests_layout.setAlignment(QtCore.Qt.AlignTop)
        self.requests_layout.setContentsMargins(10, 10, 10, 10)
        self.requests_layout.setSpacing(10)

        self.requests_area.setWidget(self.requests_widget)
        self.friend_requests_layout.addWidget(self.requests_area)

        # Вкладка приглашений в группы
        self.group_invites_tab = QtWidgets.QWidget()
        self.group_invites_layout = QtWidgets.QVBoxLayout(self.group_invites_tab)
        self.group_invites_layout.setContentsMargins(10, 10, 10, 10)
        self.group_invites_layout.setSpacing(10)

        # Создаем область прокрутки для приглашений в группы
        self.group_invites_area = QtWidgets.QScrollArea()
        self.group_invites_area.setWidgetResizable(True)
        self.group_invites_area.setStyleSheet("background-color: #ffffff; border-radius: 15px;")

        self.group_invites_widget = QtWidgets.QWidget()
        self.group_invites_layout_inner = QtWidgets.QVBoxLayout(self.group_invites_widget)
        self.group_invites_layout_inner.setAlignment(QtCore.Qt.AlignTop)
        self.group_invites_layout_inner.setContentsMargins(10, 10, 10, 10)
        self.group_invites_layout_inner.setSpacing(10)

        self.group_invites_area.setWidget(self.group_invites_widget)
        self.group_invites_layout.addWidget(self.group_invites_area)

        # Вкладка пропущенных звонков
        self.missed_calls_tab = QtWidgets.QWidget()
        self.missed_calls_layout = QtWidgets.QVBoxLayout(self.missed_calls_tab)
        self.missed_calls_layout.setContentsMargins(10, 10, 10, 10)
        self.missed_calls_layout.setSpacing(10)

        # Создаем область прокрутки для пропущенных звонков
        self.missed_calls_area = QtWidgets.QScrollArea()
        self.missed_calls_area.setWidgetResizable(True)
        self.missed_calls_area.setStyleSheet("background-color: #ffffff; border-radius: 15px;")

        self.missed_calls_widget = QtWidgets.QWidget()
        self.missed_calls_layout_inner = QtWidgets.QVBoxLayout(self.missed_calls_widget)
        self.missed_calls_layout_inner.setAlignment(QtCore.Qt.AlignTop)
        self.missed_calls_layout_inner.setContentsMargins(10, 10, 10, 10)
        self.missed_calls_layout_inner.setSpacing(10)

        self.missed_calls_area.setWidget(self.missed_calls_widget)
        self.missed_calls_layout.addWidget(self.missed_calls_area)

        # Вкладка непрочитанных сообщений
        self.unread_messages_tab = QtWidgets.QWidget()
        self.unread_messages_layout = QtWidgets.QVBoxLayout(self.unread_messages_tab)
        self.unread_messages_layout.setContentsMargins(10, 10, 10, 10)
        self.unread_messages_layout.setSpacing(10)

        # Создаем область прокрутки для непрочитанных сообщений
        self.unread_messages_area = QtWidgets.QScrollArea()
        self.unread_messages_area.setWidgetResizable(True)
        self.unread_messages_area.setStyleSheet("background-color: #ffffff; border-radius: 15px;")

        self.unread_messages_widget = QtWidgets.QWidget()
        self.unread_messages_layout_inner = QtWidgets.QVBoxLayout(self.unread_messages_widget)
        self.unread_messages_layout_inner.setAlignment(QtCore.Qt.AlignTop)
        self.unread_messages_layout_inner.setContentsMargins(10, 10, 10, 10)
        self.unread_messages_layout_inner.setSpacing(10)

        self.unread_messages_area.setWidget(self.unread_messages_widget)
        self.unread_messages_layout.addWidget(self.unread_messages_area)

        # Добавляем вкладки
        self.tabs.addTab(self.friend_requests_tab, "Запросы в друзья")
        self.tabs.addTab(self.group_invites_tab, "Приглашения в группы")  # НОВАЯ ВКЛАДКА
        self.tabs.addTab(self.missed_calls_tab, "Пропущенные звонки")
        self.tabs.addTab(self.unread_messages_tab, "Непрочитанные сообщения")

        self.layout.addWidget(self.tabs)

        # "Clear all" кнопка
        self.clear_all_btn = QtWidgets.QPushButton("Очистить все")
        self.clear_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #d0d0d0;
                border: 1px solid #999999;
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c0c0c0;
            }
        """)
        self.clear_all_btn.clicked.connect(self.confirm_clear_all)
        self.layout.addWidget(self.clear_all_btn)

        # загрузка уведомлений
        self.load_friend_requests()
        self.load_group_invites()
        self.load_missed_calls()
        self.load_unread_messages()

    def load_notification_settings(self):
        """Загружает настройки уведомлений из базы данных"""
        try:
            cursor = self.connection.cursor()

            # Проверяем, существует ли таблица notification_settings
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'notification_settings'
                )
            """)
            table_exists = cursor.fetchone()[0]

            if not table_exists:
                # Создаем таблицу, если она не существует
                cursor.execute("""
                    CREATE TABLE notification_settings (
                        username VARCHAR(50) PRIMARY KEY REFERENCES users(username),
                        enabled BOOLEAN DEFAULT TRUE
                    )
                """)
                self.connection.commit()

                # Вставляем настройки по умолчанию для текущего пользователя
                cursor.execute(
                    "INSERT INTO notification_settings (username, enabled) VALUES (%s, %s)",
                    (self.current_username, True)
                )
                self.connection.commit()
                self.notifications_enabled = True
            else:
                # Получаем настройки пользователя
                cursor.execute(
                    "SELECT enabled FROM notification_settings WHERE username = %s",
                    (self.current_username,)
                )
                result = cursor.fetchone()

                if result is None:
                    # Если настроек нет, создаем их
                    cursor.execute(
                        "INSERT INTO notification_settings (username, enabled) VALUES (%s, %s)",
                        (self.current_username, True)
                    )
                    self.connection.commit()
                    self.notifications_enabled = True
                else:
                    self.notifications_enabled = result[0]

        except Exception as e:
            print(f"[ERROR] Failed to load notification settings: {e}")
            self.notifications_enabled = True
        finally:
            cursor.close()

    def save_notification_settings(self):
        """Сохраняет настройки уведомлений в базу данных"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE notification_settings SET enabled = %s WHERE username = %s",
                (self.notifications_enabled, self.current_username)
            )
            self.connection.commit()
        except Exception as e:
            print(f"[ERROR] Failed to save notification settings: {e}")
            self.connection.rollback()
        finally:
            cursor.close()

    def show_settings(self):
        """Показывает окно настроек уведомлений"""
        settings_dialog = QtWidgets.QDialog(self)
        settings_dialog.setWindowTitle("Настройки уведомлений")
        settings_dialog.setFixedSize(300, 150)
        settings_dialog.setStyleSheet("background-color: #e0e0e0;")

        layout = QtWidgets.QVBoxLayout(settings_dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Заголовок
        title = QtWidgets.QLabel("Настройки уведомлений")
        title.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        # Переключатель (тумблер)
        toggle_layout = QtWidgets.QHBoxLayout()
        toggle_label = QtWidgets.QLabel("Показывать счетчик уведомлений:")
        toggle_layout.addWidget(toggle_label)

        self.toggle_switch = QtWidgets.QCheckBox()
        self.toggle_switch.setChecked(self.notifications_enabled)
        self.toggle_switch.stateChanged.connect(self.toggle_notifications)
        toggle_layout.addWidget(self.toggle_switch)

        layout.addLayout(toggle_layout)
        layout.addStretch()

        # Кнопка закрытия
        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999999;
            border-radius: 10px;
            padding: 8px 16px;
        """)
        close_btn.clicked.connect(settings_dialog.accept)
        layout.addWidget(close_btn)

        settings_dialog.exec_()

    def toggle_notifications(self, state):
        """Включает или выключает отображение счетчика уведомлений"""
        self.notifications_enabled = state == QtCore.Qt.Checked
        self.save_notification_settings()

        # Показываем уведомление о смене статуса
        status = "включено" if self.notifications_enabled else "отключено"
        QtWidgets.QMessageBox.information(
            self,
            "Настройки уведомлений",
            f"Отображение счетчика уведомлений {status}."
        )

    def confirm_clear_all(self):
        """Показывает диалог подтверждения очистки всех уведомлений"""
        confirm_dialog = QtWidgets.QMessageBox(self)
        confirm_dialog.setIcon(QtWidgets.QMessageBox.Question)
        confirm_dialog.setWindowTitle("Подтверждение")
        confirm_dialog.setText(
            "Вы действительно хотите очистить все уведомления о пропущенных звонках и непрочитанных сообщениях?")
        confirm_dialog.setInformativeText("Запросы в друзья и приглашения в группы не будут очищены.")
        confirm_dialog.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        confirm_dialog.setDefaultButton(QtWidgets.QMessageBox.No)

        if confirm_dialog.exec_() == QtWidgets.QMessageBox.Yes:
            self.clear_all_notifications()

    def clear_all_notifications(self):
        """Очищает все уведомления"""
        try:
            cursor = self.connection.cursor()

            # Помечаем пропущенные звонки как просмотренные
            cursor.execute(
                """
                UPDATE call_logs 
                SET notification_seen = TRUE 
                WHERE recipient = %s AND status = 'missed' AND notification_seen = FALSE
                """,
                (self.current_username,)
            )

            # Помечаем непрочитанные сообщения как прочитанные
            cursor.execute(
                """
                UPDATE messages 
                SET read = TRUE 
                WHERE receiver = %s AND read = FALSE
                """,
                (self.current_username,)
            )

            self.connection.commit()

            # Очищаем интерфейс только для звонков и сообщений
            self.clear_tab_content(self.missed_calls_layout_inner)
            self.clear_tab_content(self.unread_messages_layout_inner)

            # Добавляем сообщения об отсутствии уведомлений
            self.add_no_notifications_label(self.missed_calls_layout_inner)
            self.add_no_notifications_label(self.unread_messages_layout_inner)

            QtWidgets.QMessageBox.information(
                self,
                "Уведомления очищены",
                "Уведомления о пропущенных звонках и непрочитанных сообщениях были успешно удалены."
            )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось очистить уведомления: {str(e)}"
            )
            self.connection.rollback()
        finally:
            cursor.close()

    def clear_tab_content(self, layout):
        """Очищает содержимое вкладки"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def add_no_notifications_label(self, layout):
        """Добавляет метку об отсутствии уведомлений"""
        no_notifications = QtWidgets.QLabel("Нет уведомлений")
        no_notifications.setAlignment(QtCore.Qt.AlignCenter)
        no_notifications.setStyleSheet("color: #666; font-size: 14px;")
        layout.addWidget(no_notifications)

    def load_friend_requests(self):
        """Загружает запросы в друзья"""
        # Clear previous requests
        self.clear_tab_content(self.requests_layout)

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT id, sender, timestamp FROM friend_requests WHERE receiver = %s AND status = 'pending'",
                (self.current_username,)
            )
            requests = cursor.fetchall()

            if not requests:
                self.add_no_notifications_label(self.requests_layout)
            else:
                for request in requests:
                    request_id, sender, timestamp = request
                    self.add_request_widget(request_id, sender, timestamp)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load friend requests: {str(e)}")
        finally:
            cursor.close()

    def load_group_invites(self):
        """Загружает приглашения в группы"""
        self.clear_tab_content(self.group_invites_layout_inner)

        try:
            cursor = self.connection.cursor()

            # Проверяем существование таблицы group_invites
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'group_invites'
                )
            """)
            table_exists = cursor.fetchone()[0]

            if not table_exists:
                # Создаем таблицу group_invites
                cursor.execute("""
                    CREATE TABLE group_invites (
                        id VARCHAR(50) PRIMARY KEY,
                        group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
                        inviter VARCHAR(50) REFERENCES users(username),
                        invitee VARCHAR(50) REFERENCES users(username),
                        status VARCHAR(20) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        responded_at TIMESTAMP
                    )
                """)
                self.connection.commit()
                self.add_no_notifications_label(self.group_invites_layout_inner)
                return

            # Получаем приглашения в группы
            cursor.execute(
                """
                SELECT gi.id, gi.group_id, gi.inviter, g.name, g.description, g.avatar_path, gi.created_at
                FROM group_invites gi
                JOIN groups g ON gi.group_id = g.id
                WHERE gi.invitee = %s AND gi.status = 'pending'
                ORDER BY gi.created_at DESC
                """,
                (self.current_username,)
            )
            invites = cursor.fetchall()

            if not invites:
                self.add_no_notifications_label(self.group_invites_layout_inner)
            else:
                for invite in invites:
                    invite_id, group_id, inviter, group_name, group_desc, group_avatar, timestamp = invite
                    self.add_group_invite_widget(invite_id, group_id, inviter, group_name, group_desc, group_avatar, timestamp)

        except Exception as e:
            print(f"[ERROR] Failed to load group invites: {e}")
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load group invites: {str(e)}")
        finally:
            cursor.close()

    def add_group_invite_widget(self, invite_id, group_id, inviter, group_name, group_desc, group_avatar, timestamp):
        """Добавляет виджет приглашения в группу"""
        # Форматируем время
        formatted_time = timestamp.strftime("%d.%m.%Y %H:%M") if hasattr(timestamp, "strftime") else "Неизвестно"

        # Создаем виджет приглашения
        invite_widget = QtWidgets.QWidget()
        invite_widget.setStyleSheet("background-color: #f0f0f0; border-radius: 10px;")
        invite_widget.setMinimumHeight(120)

        invite_layout = QtWidgets.QVBoxLayout(invite_widget)
        invite_layout.setContentsMargins(15, 10, 15, 10)

        # Заголовок с информацией о группе
        header_layout = QtWidgets.QHBoxLayout()

        # Аватар группы
        group_avatar_frame = QtWidgets.QFrame()
        group_avatar_frame.setFixedSize(50, 50)
        group_avatar_frame.setStyleSheet("background-color: #d8c4eb; border-radius: 25px;")

        group_avatar_layout = QtWidgets.QVBoxLayout(group_avatar_frame)
        group_avatar_layout.setContentsMargins(0, 0, 0, 0)

        group_avatar_label = QtWidgets.QLabel("👥")
        group_avatar_label.setAlignment(QtCore.Qt.AlignCenter)
        group_avatar_label.setFont(QtGui.QFont("Arial", 20))
        group_avatar_layout.addWidget(group_avatar_label)

        # Загружаем аватар группы, если есть
        if group_avatar and os.path.exists(group_avatar):
            self.load_group_avatar(group_avatar, group_avatar_label, group_avatar_frame)

        header_layout.addWidget(group_avatar_frame)

        # Информация о группе
        group_info = QtWidgets.QVBoxLayout()
        group_name_label = QtWidgets.QLabel(group_name)
        group_name_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        group_info.addWidget(group_name_label)

        if group_desc:
            group_desc_label = QtWidgets.QLabel(group_desc)
            group_desc_label.setStyleSheet("color: #666; font-size: 11px;")
            group_desc_label.setWordWrap(True)
            group_info.addWidget(group_desc_label)

        time_label = QtWidgets.QLabel(formatted_time)
        time_label.setStyleSheet("color: #666; font-size: 10px;")
        group_info.addWidget(time_label)

        header_layout.addLayout(group_info)
        header_layout.addStretch()

        invite_layout.addLayout(header_layout)

        # Сообщение о приглашении
        message = QtWidgets.QLabel(f"{inviter} приглашает вас в группу '{group_name}'")
        message.setStyleSheet("color: #333; font-size: 14px; margin-top: 5px;")
        message.setWordWrap(True)
        invite_layout.addWidget(message)

        # Кнопки
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(10)

        accept_btn = QtWidgets.QPushButton("Принять")
        accept_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; border-radius: 15px; padding: 5px 15px;"
        )
        accept_btn.clicked.connect(lambda: self.handle_group_invite(invite_id, group_id, "accepted"))

        reject_btn = QtWidgets.QPushButton("Отклонить")
        reject_btn.setStyleSheet(
            "background-color: #FF5722; color: white; border-radius: 15px; padding: 5px 15px;"
        )
        reject_btn.clicked.connect(lambda: self.handle_group_invite(invite_id, group_id, "rejected"))

        buttons_layout.addStretch()
        buttons_layout.addWidget(accept_btn)
        buttons_layout.addWidget(reject_btn)

        invite_layout.addLayout(buttons_layout)

        self.group_invites_layout_inner.addWidget(invite_widget)

    def load_group_avatar(self, avatar_path, avatar_label, avatar_frame):
        """Загружает аватар группы"""
        try:
            pixmap = QtGui.QPixmap(avatar_path)
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

                avatar_label.setPixmap(rounded_pixmap)
                avatar_label.setText("")
                avatar_frame.setStyleSheet("background-color: transparent; border-radius: 25px;")
        except Exception as e:
            print(f"[ERROR] Failed to load group avatar: {e}")

    def handle_group_invite(self, invite_id, group_id, status):
        """Обрабатывает ответ на приглашение в группу"""
        try:
            cursor = self.connection.cursor()

            # Обновляем статус приглашения
            cursor.execute(
                "UPDATE group_invites SET status = %s, responded_at = CURRENT_TIMESTAMP WHERE id = %s",
                (status, invite_id)
            )

            if status == "accepted":
                # Добавляем пользователя в группу
                cursor.execute(
                    "INSERT INTO group_members (group_id, username, role) VALUES (%s, %s, 'member')",
                    (group_id, self.current_username)
                )

                # Получаем название группы для уведомления
                cursor.execute("SELECT name FROM groups WHERE id = %s", (group_id,))
                group_name = cursor.fetchone()[0]

                QtWidgets.QMessageBox.information(
                    self,
                    "Приглашение принято",
                    f"Вы успешно присоединились к группе '{group_name}'"
                )

                # Эмитируем сигнал для обновления списка групп
                self.groupsUpdated.emit()

            else:
                QtWidgets.QMessageBox.information(
                    self,
                    "Приглашение отклонено",
                    "Приглашение в группу было отклонено"
                )

            self.connection.commit()

            # Перезагружаем приглашения в группы
            self.load_group_invites()

        except Exception as e:
            self.connection.rollback()
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось обработать приглашение: {str(e)}"
            )
        finally:
            cursor.close()

    def load_missed_calls(self):
        """Загружает пропущенные звонки"""
        self.clear_tab_content(self.missed_calls_layout_inner)

        try:
            cursor = self.connection.cursor()

            # Проверяем существование таблицы call_logs
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'call_logs'
                )
            """)
            call_logs_exists = cursor.fetchone()[0]

            if not call_logs_exists:
                # Создаем таблицу call_logs с дополнительными полями
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
                self.connection.commit()
                self.add_no_notifications_label(self.missed_calls_layout_inner)
                return

            # Проверяем наличие колонки notification_seen
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'call_logs' AND column_name = 'notification_seen'
                )
            """)
            has_notification_seen = cursor.fetchone()[0]

            if not has_notification_seen:
                # Добавляем колонку notification_seen
                cursor.execute("""
                    ALTER TABLE call_logs 
                    ADD COLUMN notification_seen BOOLEAN DEFAULT FALSE
                """)
                self.connection.commit()

            # Проверяем наличие колонки status
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'call_logs' AND column_name = 'status'
                )
            """)
            has_status = cursor.fetchone()[0]

            if not has_status:
                # Добавляем колонку status
                cursor.execute("""
                    ALTER TABLE call_logs 
                    ADD COLUMN status VARCHAR(20) DEFAULT 'ended'
                """)
                self.connection.commit()

            # Получаем пропущенные звонки
            cursor.execute(
                """
                SELECT id, caller, end_time 
                FROM call_logs 
                WHERE recipient = %s AND status = 'missed' AND notification_seen = FALSE
                ORDER BY end_time DESC
                """,
                (self.current_username,)
            )
            missed_calls = cursor.fetchall()

            if not missed_calls:
                self.add_no_notifications_label(self.missed_calls_layout_inner)
            else:
                for call in missed_calls:
                    call_id, caller, timestamp = call
                    self.add_missed_call_widget(call_id, caller, timestamp)

        except Exception as e:
            print(f"[ERROR] Failed to load missed calls: {e}")
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load missed calls: {str(e)}")
        finally:
            cursor.close()

    def load_unread_messages(self):
        """Загружает непрочитанные сообщения"""
        self.clear_tab_content(self.unread_messages_layout_inner)

        try:
            cursor = self.connection.cursor()

            # Проверяем наличие колонки read в таблице messages
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'messages' AND column_name = 'read'
                )
            """)
            has_read_column = cursor.fetchone()[0]

            if not has_read_column:
                # Добавляем колонку read
                cursor.execute("""
                    ALTER TABLE messages 
                    ADD COLUMN read BOOLEAN DEFAULT TRUE
                """)
                self.connection.commit()

            # Получаем непрочитанные сообщения
            cursor.execute(
                """
                SELECT id, sender, content, timestamp 
                FROM messages 
                WHERE receiver = %s AND read = FALSE
                ORDER BY timestamp DESC
                """,
                (self.current_username,)
            )
            unread_messages = cursor.fetchall()

            if not unread_messages:
                self.add_no_notifications_label(self.unread_messages_layout_inner)
            else:
                for message in unread_messages:
                    message_id, sender, content, timestamp = message
                    self.add_unread_message_widget(message_id, sender, content, timestamp)

        except Exception as e:
            print(f"[ERROR] Failed to load unread messages: {e}")
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load unread messages: {str(e)}")
        finally:
            cursor.close()

    def add_request_widget(self, request_id, sender, timestamp):
        # дата время
        formatted_time = timestamp.strftime("%d.%m.%Y %H:%M")

        request_widget = QtWidgets.QWidget()
        request_widget.setStyleSheet("background-color: #f0f0f0; border-radius: 10px;")
        request_widget.setMinimumHeight(100)

        request_layout = QtWidgets.QVBoxLayout(request_widget)
        request_layout.setContentsMargins(15, 10, 15, 10)

        # ник время
        header_layout = QtWidgets.QHBoxLayout()

        # аватар
        avatar_frame = QtWidgets.QFrame()
        avatar_frame.setFixedSize(50, 50)
        avatar_frame.setStyleSheet("background-color: #d8c4eb; border-radius: 25px;")

        avatar_layout = QtWidgets.QVBoxLayout(avatar_frame)
        avatar_layout.setContentsMargins(0, 0, 0, 0)

        avatar = QtWidgets.QLabel("👤")
        avatar.setAlignment(QtCore.Qt.AlignCenter)
        avatar.setFont(QtGui.QFont("Arial", 20))
        avatar_layout.addWidget(avatar)

        # Загружаем аватар пользователя
        has_avatar = self.load_user_avatar(sender, avatar)

        # Если у пользователя есть аватар, убираем цветной фон
        if has_avatar:
            avatar_frame.setStyleSheet("background-color: transparent; border-radius: 25px;")

        header_layout.addWidget(avatar_frame)

        # инфа о пользователе
        user_info = QtWidgets.QVBoxLayout()
        name_label = QtWidgets.QLabel(sender)
        name_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))

        time_label = QtWidgets.QLabel(formatted_time)
        time_label.setStyleSheet("color: #666; font-size: 12px;")

        user_info.addWidget(name_label)
        user_info.addWidget(time_label)

        header_layout.addLayout(user_info)
        header_layout.addStretch()

        request_layout.addLayout(header_layout)

        # сообщение
        message = QtWidgets.QLabel(f"{sender} хочет добавить вас в друзья!")
        message.setStyleSheet("color: #333; font-size: 14px; margin-top: 5px;")
        request_layout.addWidget(message)

        # кнопка
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(10)

        accept_btn = QtWidgets.QPushButton("Принять")
        accept_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; border-radius: 15px; padding: 5px 15px;"
        )
        accept_btn.clicked.connect(lambda: self.handle_request(request_id, "accepted"))

        reject_btn = QtWidgets.QPushButton("Отказаться")
        reject_btn.setStyleSheet(
            "background-color: #FF5722; color: white; border-radius: 15px; padding: 5px 15px;"
        )
        reject_btn.clicked.connect(lambda: self.handle_request(request_id, "rejected"))

        buttons_layout.addStretch()
        buttons_layout.addWidget(accept_btn)
        buttons_layout.addWidget(reject_btn)

        request_layout.addLayout(buttons_layout)

        self.requests_layout.addWidget(request_widget)

    def add_missed_call_widget(self, call_id, caller, timestamp):
        """Добавляет виджет пропущенного звонка"""
        # Форматируем время
        formatted_time = timestamp.strftime("%d.%m.%Y %H:%M") if hasattr(timestamp, "strftime") else "Неизвестно"

        # Создаем виджет пропущенного звонка
        call_widget = QtWidgets.QWidget()
        call_widget.setStyleSheet("background-color: #f0f0f0; border-radius: 10px;")
        call_widget.setMinimumHeight(80)

        call_layout = QtWidgets.QVBoxLayout(call_widget)
        call_layout.setContentsMargins(15, 10, 15, 10)

        # Заголовок с именем пользователя и временем
        header_layout = QtWidgets.QHBoxLayout()

        # Аватар пользователя
        avatar_frame = QtWidgets.QFrame()
        avatar_frame.setFixedSize(50, 50)
        avatar_frame.setStyleSheet("background-color: #d8c4eb; border-radius: 25px;")

        avatar_layout = QtWidgets.QVBoxLayout(avatar_frame)
        avatar_layout.setContentsMargins(0, 0, 0, 0)

        avatar = QtWidgets.QLabel("👤")
        avatar.setAlignment(QtCore.Qt.AlignCenter)
        avatar.setFont(QtGui.QFont("Arial", 20))
        avatar_layout.addWidget(avatar)

        # Загружаем аватар пользователя
        has_avatar = self.load_user_avatar(caller, avatar)

        # Если у пользователя есть аватар, убираем цветной фон
        if has_avatar:
            avatar_frame.setStyleSheet("background-color: transparent; border-radius: 25px;")

        header_layout.addWidget(avatar_frame)

        # Информация о пользователе
        user_info = QtWidgets.QVBoxLayout()
        name_label = QtWidgets.QLabel(caller)
        name_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))

        time_label = QtWidgets.QLabel(formatted_time)
        time_label.setStyleSheet("color: #666; font-size: 12px;")

        user_info.addWidget(name_label)
        user_info.addWidget(time_label)

        header_layout.addLayout(user_info)
        header_layout.addStretch()

        # Иконка пропущенного звонка
        call_icon = QtWidgets.QLabel("📞")
        call_icon.setFont(QtGui.QFont("Arial", 20))
        call_icon.setStyleSheet("color: #FF5722;")
        header_layout.addWidget(call_icon)

        call_layout.addLayout(header_layout)

        # Сообщение
        message = QtWidgets.QLabel(f"Пропущенный звонок от {caller}")
        message.setStyleSheet("color: #333; font-size: 14px; margin-top: 5px;")
        call_layout.addWidget(message)

        # Кнопки
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(10)

        # Заменяем кнопку "Перезвонить" на "Открыть чат"
        open_chat_btn = QtWidgets.QPushButton("Открыть чат")
        open_chat_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; border-radius: 15px; padding: 5px 15px;"
        )
        open_chat_btn.clicked.connect(lambda: self.request_open_chat(caller, "call", call_id))

        mark_seen_btn = QtWidgets.QPushButton("Отметить как просмотренное")
        mark_seen_btn.setStyleSheet(
            "background-color: #2196F3; color: white; border-radius: 15px; padding: 5px 15px;"
        )
        mark_seen_btn.clicked.connect(lambda: self.mark_call_as_seen(call_id))

        buttons_layout.addStretch()
        buttons_layout.addWidget(open_chat_btn)
        buttons_layout.addWidget(mark_seen_btn)

        call_layout.addLayout(buttons_layout)

        self.missed_calls_layout_inner.addWidget(call_widget)

    def add_unread_message_widget(self, message_id, sender, content, timestamp):
        """Добавляет виджет непрочитанного сообщения"""
        # Форматируем время
        formatted_time = timestamp.strftime("%d.%m.%Y %H:%M") if hasattr(timestamp, "strftime") else "Неизвестно"

        # Создаем виджет непрочитанного сообщения
        message_widget = QtWidgets.QWidget()
        message_widget.setStyleSheet("background-color: #f0f0f0; border-radius: 10px;")
        message_widget.setMinimumHeight(80)

        message_layout = QtWidgets.QVBoxLayout(message_widget)
        message_layout.setContentsMargins(15, 10, 15, 10)

        # Заголовок с именем пользователя и временем
        header_layout = QtWidgets.QHBoxLayout()

        # Аватар пользователя
        avatar_frame = QtWidgets.QFrame()
        avatar_frame.setFixedSize(50, 50)
        avatar_frame.setStyleSheet("background-color: #d8c4eb; border-radius: 25px;")

        avatar_layout = QtWidgets.QVBoxLayout(avatar_frame)
        avatar_layout.setContentsMargins(0, 0, 0, 0)

        avatar = QtWidgets.QLabel("👤")
        avatar.setAlignment(QtCore.Qt.AlignCenter)
        avatar.setFont(QtGui.QFont("Arial", 20))
        avatar_layout.addWidget(avatar)

        # Загружаем аватар пользователя
        has_avatar = self.load_user_avatar(sender, avatar)

        # Если у пользователя есть аватар, убираем цветной фон
        if has_avatar:
            avatar_frame.setStyleSheet("background-color: transparent; border-radius: 25px;")

        header_layout.addWidget(avatar_frame)

        # Информация о пользователе
        user_info = QtWidgets.QVBoxLayout()
        name_label = QtWidgets.QLabel(sender)
        name_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))

        time_label = QtWidgets.QLabel(formatted_time)
        time_label.setStyleSheet("color: #666; font-size: 12px;")

        user_info.addWidget(name_label)
        user_info.addWidget(time_label)

        header_layout.addLayout(user_info)
        header_layout.addStretch()

        message_layout.addLayout(header_layout)

        # Сообщение
        # Ограничиваем длину сообщения для отображения
        max_length = 100
        display_content = content if len(content) <= max_length else content[:max_length] + "..."

        message_label = QtWidgets.QLabel(display_content)
        message_label.setStyleSheet("color: #333; font-size: 14px; margin-top: 5px;")
        message_label.setWordWrap(True)
        message_layout.addWidget(message_label)

        # Кнопки
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(10)

        open_chat_btn = QtWidgets.QPushButton("Открыть чат")
        open_chat_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; border-radius: 15px; padding: 5px 15px;"
        )
        open_chat_btn.clicked.connect(lambda: self.request_open_chat(sender, "message", message_id))

        mark_read_btn = QtWidgets.QPushButton("Отметить как прочитанное")
        mark_read_btn.setStyleSheet(
            "background-color: #2196F3; color: white; border-radius: 15px; padding: 5px 15px;"
        )
        mark_read_btn.clicked.connect(lambda: self.mark_message_as_read(message_id))

        buttons_layout.addStretch()
        buttons_layout.addWidget(open_chat_btn)
        buttons_layout.addWidget(mark_read_btn)

        message_layout.addLayout(buttons_layout)

        self.unread_messages_layout_inner.addWidget(message_widget)

    def load_user_avatar(self, username, avatar_label):
        """Загружает аватар пользователя из базы данных и устанавливает его в указанный QLabel"""
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
                        50, 50,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation
                    )

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

                    # Устанавливаем аватар
                    avatar_label.setPixmap(rounded_pixmap)
                    avatar_label.setText("")
                    return True
            return False
        except Exception as e:
            print(f"[ERROR] Failed to load avatar for {username}: {e}")
            return False

    def handle_request(self, request_id, status):
        try:
            cursor = self.connection.cursor()

            # реквест статус
            cursor.execute(
                "UPDATE friend_requests SET status = %s WHERE id = %s",
                (status, request_id)
            )

            if status == "accepted":
                # никнейм отправителя вытащить
                cursor.execute(
                    "SELECT sender FROM friend_requests WHERE id = %s",
                    (request_id,)
                )
                sender = cursor.fetchone()[0]

                # добавить в таблицу друзей
                cursor.execute(
                    "INSERT INTO friends (user1, user2) VALUES (%s, %s)",
                    (self.current_username, sender)
                )

                QtWidgets.QMessageBox.information(self, "Success", f"You are now friends with {sender}")
                # сигнал для обновленяи списка друзей
                self.friendsUpdated.emit()
            else:
                QtWidgets.QMessageBox.information(self, "Success", "Friend request rejected")

            self.connection.commit()

            # обновление списка
            self.load_friend_requests()

        except Exception as e:
            self.connection.rollback()
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to process request: {str(e)}")
        finally:
            cursor.close()

    def request_open_chat(self, username, notification_type=None, notification_id=None):
        """Отправляет сигнал для открытия чата с указанным пользователем и отмечает уведомление как прочитанное/просмотренное"""
        # Проверяем, является ли пользователь другом
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                SELECT 1 FROM friends 
                WHERE (user1 = %s AND user2 = %s) OR (user1 = %s AND user2 = %s)
                """,
                (self.current_username, username, username, self.current_username)
            )
            are_friends = cursor.fetchone() is not None

            if are_friends:
                # Если передан ID уведомления, отмечаем его как прочитанное/просмотренное
                if notification_id is not None:
                    if notification_type == "message":
                        cursor.execute(
                            "UPDATE messages SET read = TRUE WHERE id = %s",
                            (notification_id,)
                        )
                    elif notification_type == "call":
                        cursor.execute(
                            "UPDATE call_logs SET notification_seen = TRUE WHERE id = %s",
                            (notification_id,)
                        )
                    self.connection.commit()

                # Закрываем диалог уведомлений
                self.accept()

                # Отправляем сигнал для открытия чата
                self.openChatRequested.emit(username)
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Предупреждение",
                    f"Пользователь {username} не находится в вашем списке друзей."
                )
        except Exception as e:
            print(f"[ERROR] Failed to check friendship or update notification: {e}")
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось проверить статус дружбы или обновить уведомление: {str(e)}"
            )
        finally:
            cursor.close()

    def mark_call_as_seen(self, call_id):
        """Отмечает пропущенный звонок как просмотренный"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE call_logs SET notification_seen = TRUE WHERE id = %s",
                (call_id,)
            )
            self.connection.commit()

            # Перезагружаем список пропущенных звонков
            self.load_missed_calls()

        except Exception as e:
            print(f"[ERROR] Failed to mark call as seen: {e}")
            self.connection.rollback()
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to mark call as seen: {str(e)}")
        finally:
            cursor.close()

    def mark_message_as_read(self, message_id):
        """Отмечает сообщение как прочитанное"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE messages SET read = TRUE WHERE id = %s",
                (message_id,)
            )
            self.connection.commit()

            # Перезагружаем список непрочитанных сообщений
            self.load_unread_messages()

        except Exception as e:
            print(f"[ERROR] Failed to mark message as read: {e}")
            self.connection.rollback()
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to mark message as read: {str(e)}")
        finally:
            cursor.close()
