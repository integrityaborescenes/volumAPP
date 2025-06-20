import sys
import os
from PyQt5 import QtWidgets, QtCore, QtGui
from avatar_editor import AvatarEditorDialog
from group_invite_dialog import GroupInviteDialog


class GroupSettingsDialog(QtWidgets.QDialog):
    group_updated = QtCore.pyqtSignal(dict)  # Сигнал об обновлении группы
    group_deleted = QtCore.pyqtSignal(int)  # Сигнал об удалении группы
    group_left = QtCore.pyqtSignal(int)  # Сигнал о выходе из группы
    member_excluded = QtCore.pyqtSignal(str, str)

    def __init__(self, connection, username, group_data, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.username = username
        self.group_data = group_data.copy()  # Копируем данные группы
        self.original_group_data = group_data.copy()  # Сохраняем оригинальные данные
        self.new_avatar_path = None
        self.members_to_remove = []  # Список участников для исключения

        # Сохраняем ссылку на родительское окно для отправки уведомлений
        self.parent_window = parent

        self.setWindowTitle(f"Настройки группы: {group_data['name']}")
        self.resize(500, 700)
        self.setStyleSheet("background-color: #e0e0e0;")

        # Проверяем права пользователя
        self.user_role = self.get_user_role()
        self.is_admin = self.user_role in ['admin', 'creator']

        self.setup_ui()
        self.load_group_members()

    def get_user_role(self):
        """Получает роль текущего пользователя в группе"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT role FROM group_members WHERE group_id = %s AND username = %s",
                (self.group_data['id'], self.username)
            )
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else 'member'
        except Exception as e:
            print(f"[ERROR] Failed to get user role: {e}")
            return 'member'

    def load_user_avatar(self, username, avatar_label, size=35):
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

    def setup_ui(self):
        """Настраивает пользовательский интерфейс"""
        # Основной макет
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        # Заголовок
        self.title_label = QtWidgets.QLabel("Настройки группы")
        self.title_label.setFont(QtGui.QFont("Arial", 16, QtGui.QFont.Bold))
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.title_label)

        # Создаем прокручиваемую область
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("background-color: transparent; border: none;")

        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(20)

        # Аватар группы
        self.setup_avatar_section(scroll_layout)

        # Название группы
        self.setup_name_section(scroll_layout)

        # Описание группы
        self.setup_description_section(scroll_layout)

        # Участники группы
        self.setup_members_section(scroll_layout)

        # Секция выхода из группы для обычных участников
        if not self.is_admin and self.user_role != 'creator':
            self.setup_leave_group_section(scroll_layout)

        # Опасная зона (удаление группы) - только для админов
        if self.is_admin:
            self.setup_danger_zone(scroll_layout)

        scroll_area.setWidget(scroll_widget)
        self.layout.addWidget(scroll_area)

        # Кнопки
        self.setup_buttons()

    def setup_leave_group_section(self, layout):
        """Настраивает секцию выхода из группы для обычных участников"""
        leave_section = QtWidgets.QVBoxLayout()

        leave_label = QtWidgets.QLabel("Покинуть группу")
        leave_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        leave_label.setStyleSheet("color: #ff9800;")
        leave_section.addWidget(leave_label)

        leave_frame = QtWidgets.QFrame()
        leave_frame.setStyleSheet("""
            background-color: #fff3e0;
            border: 2px solid #ff9800;
            border-radius: 8px;
            padding: 15px;
        """)

        leave_layout = QtWidgets.QVBoxLayout(leave_frame)

        warning_label = QtWidgets.QLabel("⚠️ Вы покинете эту группу")
        warning_label.setFont(QtGui.QFont("Arial", 11, QtGui.QFont.Bold))
        warning_label.setStyleSheet("color: #ff9800;")
        leave_layout.addWidget(warning_label)

        warning_text = QtWidgets.QLabel(
            "После выхода из группы вы больше не сможете видеть сообщения и участвовать в обсуждениях. "
            "Чтобы вернуться, вам потребуется новое приглашение от администратора."
        )
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet("color: #666; font-size: 11px;")
        leave_layout.addWidget(warning_text)

        self.leave_group_btn = QtWidgets.QPushButton("Покинуть группу")
        self.leave_group_btn.setStyleSheet("""
            background-color: #ff9800;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-weight: bold;
        """)
        self.leave_group_btn.clicked.connect(self.confirm_leave_group)
        leave_layout.addWidget(self.leave_group_btn)

        leave_section.addWidget(leave_frame)
        layout.addLayout(leave_section)

    def confirm_leave_group(self):
        """Показывает диалог подтверждения выхода из группы"""
        confirm_dialog = QtWidgets.QMessageBox(self)
        confirm_dialog.setWindowTitle("Подтверждение выхода")
        confirm_dialog.setText(f"Вы уверены, что хотите покинуть группу '{self.group_data['name']}'?")
        confirm_dialog.setInformativeText(
            "После выхода из группы вы больше не сможете видеть сообщения и участвовать в обсуждениях. "
            "Чтобы вернуться, вам потребуется новое приглашение от администратора."
        )
        confirm_dialog.setIcon(QtWidgets.QMessageBox.Warning)
        confirm_dialog.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        confirm_dialog.setDefaultButton(QtWidgets.QMessageBox.No)

        # Настраиваем стиль кнопок
        yes_button = confirm_dialog.button(QtWidgets.QMessageBox.Yes)
        yes_button.setText("Да, покинуть")
        yes_button.setStyleSheet("background-color: #ff9800; color: white;")

        no_button = confirm_dialog.button(QtWidgets.QMessageBox.No)
        no_button.setText("Отмена")

        result = confirm_dialog.exec_()

        if result == QtWidgets.QMessageBox.Yes:
            self.leave_group()

    def leave_group(self):
        """Выполняет выход пользователя из группы"""
        try:
            cursor = self.connection.cursor()

            # Удаляем пользователя из участников группы
            cursor.execute(
                "DELETE FROM group_members WHERE group_id = %s AND username = %s",
                (self.group_data['id'], self.username)
            )

            # Добавляем системное сообщение о выходе пользователя
            cursor.execute(
                """
                INSERT INTO group_messages (group_id, sender, content) 
                VALUES (%s, 'Система', %s)
                """,
                (self.group_data['id'], f"{self.username} покинул(а) группу")
            )

            self.connection.commit()
            cursor.close()

            QtWidgets.QMessageBox.information(
                self,
                "Выход из группы",
                f"Вы успешно покинули группу '{self.group_data['name']}'."
            )

            # Отправляем сигнал о выходе из группы
            self.group_left.emit(self.group_data['id'])
            self.accept()

        except Exception as e:
            self.connection.rollback()
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось покинуть группу: {str(e)}"
            )
            if cursor:
                cursor.close()

    def setup_avatar_section(self, layout):
        """Настраивает секцию аватара"""
        avatar_section = QtWidgets.QVBoxLayout()

        avatar_label = QtWidgets.QLabel("Аватар группы")
        avatar_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        avatar_section.addWidget(avatar_label)

        # Контейнер для аватара
        avatar_container = QtWidgets.QHBoxLayout()

        self.avatar_frame = QtWidgets.QLabel()
        self.avatar_frame.setFixedSize(120, 120)
        self.avatar_frame.setStyleSheet("""
            background-color: #d8c4eb;
            border-radius: 60px;
            border: 2px solid #9370DB;
        """)
        self.avatar_frame.setAlignment(QtCore.Qt.AlignCenter)
        self.avatar_frame.setText("👥")
        self.avatar_frame.setFont(QtGui.QFont("Arial", 50))

        # Загружаем текущий аватар
        if self.group_data.get('avatar_path') and os.path.exists(self.group_data['avatar_path']):
            self.load_avatar(self.group_data['avatar_path'])

        avatar_buttons_layout = QtWidgets.QVBoxLayout()
        avatar_buttons_layout.setSpacing(10)

        self.change_avatar_btn = QtWidgets.QPushButton("Изменить аватар")
        self.change_avatar_btn.setStyleSheet("""
            background-color: #9370DB;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: bold;
        """)
        self.change_avatar_btn.clicked.connect(self.change_avatar)
        self.change_avatar_btn.setEnabled(self.is_admin)

        self.remove_avatar_btn = QtWidgets.QPushButton("Удалить аватар")
        self.remove_avatar_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999;
            border-radius: 8px;
            padding: 8px 16px;
        """)
        self.remove_avatar_btn.clicked.connect(self.remove_avatar)
        self.remove_avatar_btn.setEnabled(self.is_admin)

        avatar_buttons_layout.addWidget(self.change_avatar_btn)
        avatar_buttons_layout.addWidget(self.remove_avatar_btn)
        avatar_buttons_layout.addStretch()

        avatar_container.addWidget(self.avatar_frame)
        avatar_container.addSpacing(20)
        avatar_container.addLayout(avatar_buttons_layout)
        avatar_container.addStretch()

        avatar_section.addLayout(avatar_container)
        layout.addLayout(avatar_section)

    def setup_name_section(self, layout):
        """Настраивает секцию названия"""
        name_section = QtWidgets.QVBoxLayout()
        name_label = QtWidgets.QLabel("Название группы")
        name_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        name_section.addWidget(name_label)

        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setText(self.group_data.get('name', ''))
        self.name_input.setPlaceholderText("Введите название группы")
        self.name_input.setStyleSheet("""
            background-color: white;
            border: 2px solid #ddd;
            border-radius: 8px;
            padding: 12px;
            font-size: 14px;
        """)
        self.name_input.setMaxLength(100)
        self.name_input.setEnabled(self.is_admin)
        name_section.addWidget(self.name_input)

        layout.addLayout(name_section)

    def setup_description_section(self, layout):
        """Настраивает секцию описания"""
        desc_section = QtWidgets.QVBoxLayout()
        desc_label = QtWidgets.QLabel("Описание группы")
        desc_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        desc_section.addWidget(desc_label)

        self.description_input = QtWidgets.QTextEdit()
        self.description_input.setPlainText(self.group_data.get('description', ''))
        self.description_input.setPlaceholderText("Краткое описание группы...")
        self.description_input.setStyleSheet("""
            background-color: white;
            border: 2px solid #ddd;
            border-radius: 8px;
            padding: 12px;
            font-size: 14px;
        """)
        self.description_input.setMaximumHeight(80)
        self.description_input.setEnabled(self.is_admin)
        desc_section.addWidget(self.description_input)

        layout.addLayout(desc_section)

    def setup_members_section(self, layout):
        """Настраивает секцию участников"""
        members_section = QtWidgets.QVBoxLayout()

        members_header = QtWidgets.QHBoxLayout()
        members_label = QtWidgets.QLabel("Участники группы")
        members_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        members_header.addWidget(members_label)
        members_header.addStretch()

        # Кнопка приглашения друзей (только для админов)
        if self.is_admin:
            self.invite_friends_btn = QtWidgets.QPushButton("Пригласить друзей")
            self.invite_friends_btn.setStyleSheet("""
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
            """)
            self.invite_friends_btn.clicked.connect(self.open_invite_dialog)
            members_header.addWidget(self.invite_friends_btn)

        self.members_count_label = QtWidgets.QLabel()
        self.members_count_label.setStyleSheet("color: #666; font-size: 11px;")
        members_header.addWidget(self.members_count_label)

        members_section.addLayout(members_header)

        # Область списка участников
        self.members_area = QtWidgets.QScrollArea()
        self.members_area.setWidgetResizable(True)
        self.members_area.setStyleSheet("background-color: #ffffff; border-radius: 8px;")
        self.members_area.setMaximumHeight(200)

        self.members_widget = QtWidgets.QWidget()
        self.members_layout = QtWidgets.QVBoxLayout(self.members_widget)
        self.members_layout.setAlignment(QtCore.Qt.AlignTop)
        self.members_layout.setContentsMargins(10, 10, 10, 10)
        self.members_layout.setSpacing(5)

        self.members_area.setWidget(self.members_widget)
        members_section.addWidget(self.members_area)

        layout.addLayout(members_section)

    def setup_danger_zone(self, layout):
        """Настраивает опасную зону (удаление группы)"""
        danger_section = QtWidgets.QVBoxLayout()

        danger_label = QtWidgets.QLabel("Опасная зона")
        danger_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        danger_label.setStyleSheet("color: #d32f2f;")
        danger_section.addWidget(danger_label)

        danger_frame = QtWidgets.QFrame()
        danger_frame.setStyleSheet("""
            background-color: #ffebee;
            border: 2px solid #f44336;
            border-radius: 8px;
            padding: 15px;
        """)

        danger_layout = QtWidgets.QVBoxLayout(danger_frame)

        warning_label = QtWidgets.QLabel("⚠️ Удаление группы необратимо!")
        warning_label.setFont(QtGui.QFont("Arial", 11, QtGui.QFont.Bold))
        warning_label.setStyleSheet("color: #d32f2f;")
        danger_layout.addWidget(warning_label)

        warning_text = QtWidgets.QLabel(
            "При удалении группы будут удалены все сообщения, файлы и история. "
            "Все участники будут исключены из группы."
        )
        warning_text.setWordWrap(True)
        warning_text.setStyleSheet("color: #666; font-size: 11px;")
        danger_layout.addWidget(warning_text)

        self.delete_group_btn = QtWidgets.QPushButton("Удалить группу")
        self.delete_group_btn.setStyleSheet("""
            background-color: #f44336;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-weight: bold;
        """)
        self.delete_group_btn.clicked.connect(self.confirm_delete_group)
        danger_layout.addWidget(self.delete_group_btn)

        danger_section.addWidget(danger_frame)
        layout.addLayout(danger_section)

    def setup_buttons(self):
        """Настраивает кнопки внизу диалога"""
        self.buttons_layout = QtWidgets.QHBoxLayout()
        self.buttons_layout.setSpacing(10)

        self.cancel_btn = QtWidgets.QPushButton("Отмена")
        self.cancel_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999;
            border-radius: 8px;
            padding: 12px 24px;
            font-size: 14px;
        """)
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QtWidgets.QPushButton("Сохранить")
        self.save_btn.setStyleSheet("""
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 24px;
            font-size: 14px;
            font-weight: bold;
        """)
        self.save_btn.clicked.connect(self.save_changes)
        self.save_btn.setEnabled(self.is_admin)

        self.buttons_layout.addWidget(self.cancel_btn)
        self.buttons_layout.addWidget(self.save_btn)

        self.layout.addLayout(self.buttons_layout)

    def open_invite_dialog(self):
        """Открывает диалог приглашения друзей в группу"""
        invite_dialog = GroupInviteDialog(self.connection, self.username, self.group_data, self)
        invite_dialog.invite_sent.connect(self.on_invite_sent)
        invite_dialog.exec_()

    def on_invite_sent(self, friend_username, group_name):
        """Обработчик отправки приглашения"""
        print(f"[GROUP INVITE] Sent invite to {friend_username} for group {group_name}")

    def load_group_members(self):
        """Загружает список участников группы"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                SELECT username, role, joined_at 
                FROM group_members 
                WHERE group_id = %s 
                ORDER BY 
                    CASE role 
                        WHEN 'creator' THEN 1 
                        WHEN 'admin' THEN 2 
                        ELSE 3 
                    END, 
                    joined_at ASC
                """,
                (self.group_data['id'],)
            )
            members = cursor.fetchall()
            cursor.close()

            # Очищаем текущий список
            while self.members_layout.count():
                item = self.members_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

            # Обновляем счетчик участников
            self.members_count_label.setText(f"Участников: {len(members)}")

            # Добавляем участников
            for member_data in members:
                username, role, joined_at = member_data
                self.add_member_widget(username, role)

        except Exception as e:
            print(f"[ERROR] Failed to load group members: {e}")

    def add_member_widget(self, username, role):
        """Добавляет виджет участника"""
        member_widget = QtWidgets.QWidget()
        member_widget.setStyleSheet("background-color: #f9f9f9; border-radius: 5px;")
        member_widget.setMinimumHeight(50)

        member_layout = QtWidgets.QHBoxLayout(member_widget)
        member_layout.setContentsMargins(10, 5, 10, 5)

        # Аватар участника
        avatar_frame = QtWidgets.QFrame()
        avatar_frame.setFixedSize(35, 35)
        avatar_frame.setStyleSheet("background-color: #d8c4eb; border-radius: 17px; border: 1px solid #9370DB;")

        avatar_layout = QtWidgets.QVBoxLayout(avatar_frame)
        avatar_layout.setContentsMargins(0, 0, 0, 0)

        avatar = QtWidgets.QLabel("👤")
        avatar.setAlignment(QtCore.Qt.AlignCenter)
        avatar.setFont(QtGui.QFont("Arial", 15))
        avatar.setStyleSheet("border: none;")
        avatar_layout.addWidget(avatar)

        # Загружаем аватар пользователя из базы данных
        has_avatar = self.load_user_avatar(username, avatar, size=35)

        # Если у пользователя есть аватар, убираем цветной фон
        if has_avatar:
            avatar_frame.setStyleSheet("background-color: transparent; border-radius: 17px; border: 1px solid #9370DB;")

        member_layout.addWidget(avatar_frame)

        # Информация об участнике
        info_layout = QtWidgets.QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QtWidgets.QLabel(username)
        name_label.setFont(QtGui.QFont("Arial", 11, QtGui.QFont.Bold))
        info_layout.addWidget(name_label)

        role_text = {
            'creator': 'Создатель',
            'admin': 'Администратор',
            'member': 'Участник'
        }.get(role, 'Участник')

        role_label = QtWidgets.QLabel(role_text)
        role_label.setStyleSheet("color: #666; font-size: 10px;")
        info_layout.addWidget(role_label)

        member_layout.addLayout(info_layout)
        member_layout.addStretch()

        # Кнопка исключения (только для админов и не для создателя)
        if (self.is_admin and
                username != self.username and
                role != 'creator' and
                username not in self.members_to_remove):
            remove_btn = QtWidgets.QPushButton("Исключить")
            remove_btn.setStyleSheet("""
                background-color: #FF5252;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 10px;
            """)
            remove_btn.clicked.connect(lambda: self.mark_member_for_removal(username, member_widget))
            member_layout.addWidget(remove_btn)

        self.members_layout.addWidget(member_widget)

    def mark_member_for_removal(self, username, widget):
        """Помечает участника для исключения"""
        self.members_to_remove.append(username)

        # Визуально помечаем участника как исключенного
        widget.setStyleSheet("background-color: #ffcdd2; border-radius: 5px;")

        # Находим и отключаем кнопку исключения
        for i in range(widget.layout().count()):
            item = widget.layout().itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QtWidgets.QPushButton):
                button = item.widget()
                if button.text() == "Исключить":
                    button.setText("Исключен")
                    button.setEnabled(False)
                    button.setStyleSheet("""
                        background-color: #999;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        padding: 5px 10px;
                        font-size: 10px;
                    """)
                    break

    def change_avatar(self):
        """Изменяет аватар группы"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Выбрать изображение",
            "",
            "Изображения (*.png *.jpg *.jpeg *.gif *.bmp)"
        )

        if file_path:
            try:
                # Открываем редактор аватара
                editor = AvatarEditorDialog(file_path, self)
                if editor.exec_() == QtWidgets.QDialog.Accepted:
                    # Получаем обработанное изображение
                    processed_image = editor.get_processed_image()

                    # Создаем директорию для аватаров групп
                    avatar_dir = os.path.join("group_avatars")
                    os.makedirs(avatar_dir, exist_ok=True)

                    # Генерируем уникальное имя файла
                    import uuid
                    avatar_filename = f"group_{uuid.uuid4().hex[:8]}.png"
                    avatar_path = os.path.join(avatar_dir, avatar_filename)

                    # Сохраняем аватар
                    processed_image.save(avatar_path, "PNG")

                    # Обновляем аватар в интерфейсе
                    self.new_avatar_path = avatar_path
                    self.load_avatar(avatar_path)
            except ImportError:
                # Если нет редактора аватара, просто копируем файл
                avatar_dir = os.path.join("group_avatars")
                os.makedirs(avatar_dir, exist_ok=True)

                import uuid
                import shutil
                file_ext = os.path.splitext(file_path)[1]
                avatar_filename = f"group_{uuid.uuid4().hex[:8]}{file_ext}"
                avatar_path = os.path.join(avatar_dir, avatar_filename)

                shutil.copy2(file_path, avatar_path)
                self.new_avatar_path = avatar_path
                self.load_avatar(avatar_path)

    def load_avatar(self, path):
        """Загружает аватар из указанного пути"""
        try:
            pixmap = QtGui.QPixmap(path)
            if not pixmap.isNull():
                # Масштабируем и обрезаем до круга
                pixmap = pixmap.scaled(
                    120, 120,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                )

                # Создаем круглую маску
                mask = QtGui.QPixmap(120, 120)
                mask.fill(QtCore.Qt.transparent)
                painter = QtGui.QPainter(mask)
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setBrush(QtCore.Qt.white)
                painter.drawEllipse(0, 0, 120, 120)
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
                self.avatar_frame.setPixmap(rounded_pixmap)
                self.avatar_frame.setText("")

                # Убираем цветной фон
                self.avatar_frame.setStyleSheet("""
                    background-color: transparent;
                    border-radius: 60px;
                    border: 2px solid #9370DB;
                """)
        except Exception as e:
            print(f"[ERROR] Failed to load avatar: {e}")

    def remove_avatar(self):
        """Удаляет аватар группы"""
        self.new_avatar_path = ""  # Пустая строка означает удаление аватара

        # Сбрасываем аватар в интерфейсе
        self.avatar_frame.setPixmap(QtGui.QPixmap())
        self.avatar_frame.setText("👥")
        self.avatar_frame.setFont(QtGui.QFont("Arial", 50))
        self.avatar_frame.setStyleSheet("""
            background-color: #d8c4eb;
            border-radius: 60px;
            border: 2px solid #9370DB;
        """)

    def confirm_delete_group(self):
        """Показывает диалог подтверждения удаления группы"""
        confirm_dialog = QtWidgets.QMessageBox(self)
        confirm_dialog.setWindowTitle("Подтверждение удаления")
        confirm_dialog.setText(f"Вы уверены, что хотите удалить группу '{self.group_data['name']}'?")
        confirm_dialog.setInformativeText(
            "Это действие необратимо. Все сообщения, файлы и история группы будут удалены. "
            "Все участники будут исключены из группы."
        )
        confirm_dialog.setIcon(QtWidgets.QMessageBox.Warning)
        confirm_dialog.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        confirm_dialog.setDefaultButton(QtWidgets.QMessageBox.No)

        # Настраиваем стиль кнопок
        yes_button = confirm_dialog.button(QtWidgets.QMessageBox.Yes)
        yes_button.setText("Да, удалить")
        yes_button.setStyleSheet("background-color: #f44336; color: white;")

        no_button = confirm_dialog.button(QtWidgets.QMessageBox.No)
        no_button.setText("Отмена")

        result = confirm_dialog.exec_()

        if result == QtWidgets.QMessageBox.Yes:
            self.delete_group()

    def delete_group(self):
        """Удаляет группу"""
        try:
            cursor = self.connection.cursor()

            # Удаляем приглашения в группу
            cursor.execute("DELETE FROM group_invites WHERE group_id = %s", (self.group_data['id'],))

            # Удаляем сообщения группы
            cursor.execute("DELETE FROM group_messages WHERE group_id = %s", (self.group_data['id'],))

            # Удаляем участников группы
            cursor.execute("DELETE FROM group_members WHERE group_id = %s", (self.group_data['id'],))

            # Удаляем саму группу
            cursor.execute("DELETE FROM groups WHERE id = %s", (self.group_data['id'],))

            self.connection.commit()
            cursor.close()

            # Удаляем аватар группы, если он существует
            if self.group_data.get('avatar_path') and os.path.exists(self.group_data['avatar_path']):
                try:
                    os.remove(self.group_data['avatar_path'])
                except Exception as e:
                    print(f"[WARNING] Failed to delete group avatar: {e}")

            QtWidgets.QMessageBox.information(
                self,
                "Группа удалена",
                f"Группа '{self.group_data['name']}' была успешно удалена."
            )

            # Отправляем сигнал об удалении группы
            self.group_deleted.emit(self.group_data['id'])
            self.accept()

        except Exception as e:
            self.connection.rollback()
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось удалить группу: {str(e)}"
            )
            if cursor:
                cursor.close()

    def save_changes(self):
        """Сохраняет изменения в группе"""
        try:
            cursor = self.connection.cursor()
            changes_made = False

            # Проверяем изменения в названии
            new_name = self.name_input.text().strip()
            if new_name != self.original_group_data.get('name', ''):
                cursor.execute(
                    "UPDATE groups SET name = %s WHERE id = %s",
                    (new_name, self.group_data['id'])
                )
                self.group_data['name'] = new_name
                changes_made = True

            # Проверяем изменения в описании
            new_description = self.description_input.toPlainText().strip()
            if new_description != self.original_group_data.get('description', ''):
                cursor.execute(
                    "UPDATE groups SET description = %s WHERE id = %s",
                    (new_description, self.group_data['id'])
                )
                self.group_data['description'] = new_description
                changes_made = True

            # Проверяем изменения в аватаре
            if self.new_avatar_path is not None:
                old_avatar = self.original_group_data.get('avatar_path')
                if old_avatar and os.path.exists(old_avatar):
                    try:
                        os.remove(old_avatar)
                    except Exception as e:
                        print(f"[WARNING] Failed to delete old avatar: {e}")

                cursor.execute(
                    "UPDATE groups SET avatar_path = %s WHERE id = %s",
                    (self.new_avatar_path if self.new_avatar_path else None, self.group_data['id'])
                )
                self.group_data['avatar_path'] = self.new_avatar_path
                changes_made = True

            # Исключаем участников и отправляем уведомления
            for username in self.members_to_remove:
                cursor.execute(
                    "DELETE FROM group_members WHERE group_id = %s AND username = %s",
                    (self.group_data['id'], username)
                )

                # Добавляем системное сообщение в группу об исключении
                cursor.execute(
                    """
                    INSERT INTO group_messages (group_id, sender, content) 
                    VALUES (%s, 'Система', %s)
                    """,
                    (self.group_data['id'], f"{username} был(а) исключен(а) из группы")
                )

                # Отправляем уведомление об исключении через клиент
                if self.parent_window and hasattr(self.parent_window, 'client'):
                    exclusion_message = f"GROUP_EXCLUSION:{username}:{self.group_data['name']}:{self.group_data['id']}"
                    self.parent_window.client.send_message(exclusion_message)
                    print(f"[GROUP] Sent exclusion notification for {username} from group {self.group_data['name']}")

                changes_made = True

            if changes_made:
                self.connection.commit()

                QtWidgets.QMessageBox.information(
                    self,
                    "Изменения сохранены",
                    "Изменения в настройках группы были успешно сохранены."
                )

                self.group_updated.emit(self.group_data)
                self.accept()
            else:
                self.reject()

            cursor.close()

        except Exception as e:
            self.connection.rollback()
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось сохранить изменения: {str(e)}"
            )
            if cursor:
                cursor.close()