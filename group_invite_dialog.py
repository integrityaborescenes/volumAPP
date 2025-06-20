import sys
from PyQt5 import QtWidgets, QtCore, QtGui
import os
import uuid


class GroupInviteDialog(QtWidgets.QDialog):
    invite_sent = QtCore.pyqtSignal(str, str)  # Сигнал об отправке приглашения (friend_username, group_name)

    def __init__(self, connection, current_username, group_data, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.current_username = current_username
        self.group_data = group_data
        self.parent = parent

        self.setWindowTitle(f"Пригласить в группу: {group_data['name']}")
        self.resize(400, 500)
        self.setStyleSheet("background-color: #e0e0e0;")

        self.setup_ui()
        self.load_friends()

    def setup_ui(self):
        """Настраивает пользовательский интерфейс"""
        # Основной макет
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # Заголовок
        self.title_label = QtWidgets.QLabel(f"Пригласить друзей в группу")
        self.title_label.setFont(QtGui.QFont("Arial", 16, QtGui.QFont.Bold))
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.title_label)

        # Информация о группе
        group_info_frame = QtWidgets.QFrame()
        group_info_frame.setStyleSheet("""
            background-color: #f0f0f0;
            border-radius: 10px;
            padding: 10px;
        """)
        group_info_layout = QtWidgets.QHBoxLayout(group_info_frame)

        # Аватар группы
        group_avatar = QtWidgets.QLabel()
        group_avatar.setFixedSize(50, 50)
        group_avatar.setStyleSheet("background-color: #d8c4eb; border-radius: 25px;")
        group_avatar.setAlignment(QtCore.Qt.AlignCenter)
        group_avatar.setText("👥")
        group_avatar.setFont(QtGui.QFont("Arial", 20))

        # Загружаем аватар группы, если есть
        if self.group_data.get('avatar_path') and os.path.exists(self.group_data['avatar_path']):
            self.load_group_avatar(group_avatar)

        group_info_layout.addWidget(group_avatar)

        # Информация о группе
        group_details = QtWidgets.QVBoxLayout()
        group_name = QtWidgets.QLabel(self.group_data['name'])
        group_name.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        group_details.addWidget(group_name)

        if self.group_data.get('description'):
            group_desc = QtWidgets.QLabel(self.group_data['description'])
            group_desc.setStyleSheet("color: #666; font-size: 11px;")
            group_desc.setWordWrap(True)
            group_details.addWidget(group_desc)

        group_info_layout.addLayout(group_details)
        group_info_layout.addStretch()

        self.layout.addWidget(group_info_frame)

        # Поисковая строка
        self.search_layout = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Поиск друзей для приглашения")
        self.search_input.setStyleSheet(
            "background-color: #ffffff; border-radius: 15px; padding: 10px; font-size: 14px;"
        )
        self.search_input.setMinimumHeight(40)
        self.search_input.textChanged.connect(self.filter_friends)

        self.search_btn = QtWidgets.QPushButton("🔍")
        self.search_btn.setFixedSize(40, 40)
        self.search_btn.setStyleSheet(
            "background-color: #d9d9d9; border-radius: 15px; font-size: 16px;"
        )

        self.search_layout.addWidget(self.search_input)
        self.search_layout.addWidget(self.search_btn)
        self.layout.addLayout(self.search_layout)

        # Область списка друзей
        self.friends_area = QtWidgets.QScrollArea()
        self.friends_area.setWidgetResizable(True)
        self.friends_area.setStyleSheet("background-color: #ffffff; border-radius: 15px;")

        self.friends_widget = QtWidgets.QWidget()
        self.friends_layout = QtWidgets.QVBoxLayout(self.friends_widget)
        self.friends_layout.setAlignment(QtCore.Qt.AlignTop)
        self.friends_layout.setContentsMargins(10, 10, 10, 10)
        self.friends_layout.setSpacing(10)

        self.friends_area.setWidget(self.friends_widget)
        self.layout.addWidget(self.friends_area)

        # Кнопки
        self.buttons_layout = QtWidgets.QHBoxLayout()
        self.buttons_layout.setSpacing(10)

        self.cancel_btn = QtWidgets.QPushButton("Отмена")
        self.cancel_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999;
            border-radius: 10px;
            padding: 12px 24px;
            font-size: 14px;
        """)
        self.cancel_btn.clicked.connect(self.reject)

        self.close_btn = QtWidgets.QPushButton("Закрыть")
        self.close_btn.setStyleSheet("""
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 10px;
            padding: 12px 24px;
            font-size: 14px;
            font-weight: bold;
        """)
        self.close_btn.clicked.connect(self.accept)

        self.buttons_layout.addWidget(self.cancel_btn)
        self.buttons_layout.addWidget(self.close_btn)

        self.layout.addLayout(self.buttons_layout)

    def load_group_avatar(self, avatar_label):
        """Загружает аватар группы"""
        try:
            pixmap = QtGui.QPixmap(self.group_data['avatar_path'])
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
                avatar_label.setStyleSheet("background-color: transparent; border-radius: 25px;")
        except Exception as e:
            print(f"[ERROR] Failed to load group avatar: {e}")

    def load_user_avatar(self, username, avatar_label, size=40):
        """Загружает аватар пользователя из базы данных"""
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
                    pixmap = pixmap.scaled(
                        size, size,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation
                    )

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

                    # Устанавливаем аватар
                    avatar_label.setPixmap(rounded_pixmap)
                    avatar_label.setText("")
                    return True
            return False
        except Exception as e:
            print(f"[ERROR] Failed to load avatar for {username}: {e}")
            return False

    def load_friends(self, filter_text=""):
        """Загружает список друзей, которых можно пригласить"""
        # Очищаем текущий список
        while self.friends_layout.count():
            item = self.friends_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        try:
            cursor = self.connection.cursor()

            # Получаем список друзей, которые еще не в группе
            cursor.execute(
                """
                SELECT 
                    CASE 
                        WHEN user1 = %s THEN user2 
                        ELSE user1 
                    END as friend
                FROM friends 
                WHERE (user1 = %s OR user2 = %s)
                AND (
                    CASE 
                        WHEN user1 = %s THEN user2 
                        ELSE user1 
                    END
                ) NOT IN (
                    SELECT username FROM group_members WHERE group_id = %s
                )
                """,
                (self.current_username, self.current_username, self.current_username,
                 self.current_username, self.group_data['id'])
            )
            friends = cursor.fetchall()
            cursor.close()

            if not friends:
                no_friends = QtWidgets.QLabel("Все ваши друзья уже в группе или у вас нет друзей для приглашения")
                no_friends.setAlignment(QtCore.Qt.AlignCenter)
                no_friends.setStyleSheet("color: #666; font-size: 14px;")
                no_friends.setWordWrap(True)
                self.friends_layout.addWidget(no_friends)
            else:
                # Фильтруем друзей по введенному тексту
                filtered_friends = []
                for friend in friends:
                    friend_name = friend[0]
                    if filter_text.lower() in friend_name.lower():
                        filtered_friends.append(friend_name)

                if not filtered_friends:
                    no_results = QtWidgets.QLabel(f"Нет друзей, соответствующих запросу '{filter_text}'")
                    no_results.setAlignment(QtCore.Qt.AlignCenter)
                    no_results.setStyleSheet("color: #666; font-size: 14px;")
                    self.friends_layout.addWidget(no_results)
                else:
                    for friend_name in filtered_friends:
                        self.add_friend_widget(friend_name)

        except Exception as e:
            print(f"[ERROR] Failed to load friends for invitation: {e}")
            error_label = QtWidgets.QLabel(f"Ошибка загрузки списка друзей: {str(e)}")
            error_label.setStyleSheet("color: red;")
            self.friends_layout.addWidget(error_label)

    def add_friend_widget(self, friend_name):
        """Добавляет виджет друга для приглашения"""
        friend_widget = QtWidgets.QWidget()
        friend_widget.setStyleSheet("background-color: #f0f0f0; border-radius: 10px;")
        friend_widget.setMinimumHeight(70)

        friend_layout = QtWidgets.QHBoxLayout(friend_widget)
        friend_layout.setContentsMargins(10, 5, 10, 5)

        # Аватар друга
        avatar_frame = QtWidgets.QFrame()
        avatar_frame.setFixedSize(40, 40)
        avatar_frame.setStyleSheet("background-color: #d8c4eb; border-radius: 20px;")

        avatar_layout = QtWidgets.QVBoxLayout(avatar_frame)
        avatar_layout.setContentsMargins(0, 0, 0, 0)

        avatar = QtWidgets.QLabel("👤")
        avatar.setAlignment(QtCore.Qt.AlignCenter)
        avatar.setFont(QtGui.QFont("Arial", 18))
        avatar_layout.addWidget(avatar)

        # Загружаем аватар пользователя
        has_avatar = self.load_user_avatar(friend_name, avatar, size=40)
        if has_avatar:
            avatar_frame.setStyleSheet("background-color: transparent; border-radius: 20px;")

        friend_layout.addWidget(avatar_frame)

        # Имя друга
        name_label = QtWidgets.QLabel(friend_name)
        name_label.setFont(QtGui.QFont("Arial", 12))
        friend_layout.addWidget(name_label)
        friend_layout.addStretch()

        # Кнопка приглашения
        invite_btn = QtWidgets.QPushButton("Пригласить")
        invite_btn.setStyleSheet("""
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 15px;
            padding: 8px 16px;
            font-weight: bold;
        """)
        invite_btn.clicked.connect(lambda: self.send_invite(friend_name, invite_btn))
        friend_layout.addWidget(invite_btn)

        self.friends_layout.addWidget(friend_widget)

    def send_invite(self, friend_name, button):
        """Отправляет приглашение в группу"""
        try:
            cursor = self.connection.cursor()

            # Проверяем, есть ли уже приглашение
            cursor.execute(
                """
                SELECT id FROM group_invites 
                WHERE group_id = %s AND inviter = %s AND invitee = %s AND status = 'pending'
                """,
                (self.group_data['id'], self.current_username, friend_name)
            )
            existing_invite = cursor.fetchone()

            if existing_invite:
                QtWidgets.QMessageBox.information(
                    self,
                    "Приглашение уже отправлено",
                    f"Вы уже отправили приглашение пользователю {friend_name}"
                )
                cursor.close()
                return

            # Создаем новое приглашение
            invite_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO group_invites (id, group_id, inviter, invitee, status, created_at)
                VALUES (%s, %s, %s, %s, 'pending', CURRENT_TIMESTAMP)
                """,
                (invite_id, self.group_data['id'], self.current_username, friend_name)
            )

            self.connection.commit()
            cursor.close()

            # Обновляем кнопку
            button.setText("Приглашен")
            button.setEnabled(False)
            button.setStyleSheet("""
                background-color: #999;
                color: white;
                border: none;
                border-radius: 15px;
                padding: 8px 16px;
                font-weight: bold;
            """)

            # Отправляем сигнал об отправке приглашения
            self.invite_sent.emit(friend_name, self.group_data['name'])

            QtWidgets.QMessageBox.information(
                self,
                "Приглашение отправлено",
                f"Приглашение в группу '{self.group_data['name']}' отправлено пользователю {friend_name}"
            )

        except Exception as e:
            print(f"[ERROR] Failed to send group invite: {e}")
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось отправить приглашение: {str(e)}"
            )
            if cursor:
                cursor.close()

    def filter_friends(self):
        """Фильтрует список друзей по введенному тексту"""
        filter_text = self.search_input.text().strip()
        self.load_friends(filter_text)
