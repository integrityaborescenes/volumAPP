import sys
import os
from PyQt5 import QtWidgets, QtCore, QtGui
import pg8000
import bcrypt
from avatar_editor import AvatarEditorDialog


class ProfileDialog(QtWidgets.QDialog):
    profile_updated = QtCore.pyqtSignal(dict)  # Сигнал об обновлении профиля

    def __init__(self, connection, username, client=None, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.username = username
        self.client = client
        self.avatar_path = None
        self.avatar_changed = False

        self.setWindowTitle("Управление аккаунтом")
        self.resize(400, 500)
        self.setStyleSheet("background-color: #e0e0e0;")

        # Основной макет
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # Заголовок
        self.title_label = QtWidgets.QLabel("Управление аккаунтом")
        self.title_label.setFont(QtGui.QFont("Arial", 16, QtGui.QFont.Bold))
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.title_label)

        # Создаем вкладки
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #999;
                border-radius: 5px;
                background-color: #d9d9d9;
            }
            QTabBar::tab {
                background-color: #c0c0c0;
                border: 1px solid #999;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #d9d9d9;
                border-bottom: none;
            }
        """)

        # Вкладка профиля
        self.profile_tab = QtWidgets.QWidget()
        self.create_profile_tab()
        self.tabs.addTab(self.profile_tab, "Профиль")

        # Вкладка безопасности
        self.security_tab = QtWidgets.QWidget()
        self.create_security_tab()
        self.tabs.addTab(self.security_tab, "Безопасность")

        self.layout.addWidget(self.tabs)

        # Кнопки внизу
        self.buttons_layout = QtWidgets.QHBoxLayout()
        self.buttons_layout.setSpacing(10)

        self.cancel_btn = QtWidgets.QPushButton("Отмена")
        self.cancel_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999;
            border-radius: 5px;
            padding: 8px 16px;
        """)
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QtWidgets.QPushButton("Сохранить")
        self.save_btn.setStyleSheet("""
            background-color: #9370DB;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 16px;
        """)
        self.save_btn.clicked.connect(self.save_changes)

        self.buttons_layout.addWidget(self.cancel_btn)
        self.buttons_layout.addWidget(self.save_btn)

        self.layout.addLayout(self.buttons_layout)

        # Загружаем данные профиля
        self.load_profile_data()

    def create_profile_tab(self):
        """Создает содержимое вкладки профиля"""
        layout = QtWidgets.QVBoxLayout(self.profile_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Аватар
        avatar_layout = QtWidgets.QHBoxLayout()

        self.avatar_frame = QtWidgets.QLabel()
        self.avatar_frame.setFixedSize(100, 100)
        self.avatar_frame.setStyleSheet("""
            background-color: #d8c4eb;
            border-radius: 50px;
            border: 2px solid #9370DB;
        """)
        self.avatar_frame.setAlignment(QtCore.Qt.AlignCenter)
        self.avatar_frame.setText("👤")
        self.avatar_frame.setFont(QtGui.QFont("Arial", 40))

        avatar_buttons_layout = QtWidgets.QVBoxLayout()
        avatar_buttons_layout.setSpacing(10)

        self.change_avatar_btn = QtWidgets.QPushButton("Изменить аватар")
        self.change_avatar_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999;
            border-radius: 5px;
            padding: 8px 16px;
        """)
        self.change_avatar_btn.clicked.connect(self.change_avatar)

        self.remove_avatar_btn = QtWidgets.QPushButton("Удалить аватар")
        self.remove_avatar_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999;
            border-radius: 5px;
            padding: 8px 16px;
        """)
        self.remove_avatar_btn.clicked.connect(self.remove_avatar)

        avatar_buttons_layout.addWidget(self.change_avatar_btn)
        avatar_buttons_layout.addWidget(self.remove_avatar_btn)
        avatar_buttons_layout.addStretch()

        avatar_layout.addWidget(self.avatar_frame)
        avatar_layout.addSpacing(15)
        avatar_layout.addLayout(avatar_buttons_layout)
        avatar_layout.addStretch()

        layout.addLayout(avatar_layout)

        # Информация о пользователе
        form_layout = QtWidgets.QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(QtCore.Qt.AlignRight)

        self.username_label = QtWidgets.QLabel(self.username)
        self.username_label.setFont(QtGui.QFont("Arial", 12))
        form_layout.addRow("Имя пользователя:", self.username_label)

        self.email_input = QtWidgets.QLineEdit()
        self.email_input.setStyleSheet("""
            background-color: white;
            border: 1px solid #999;
            border-radius: 5px;
            padding: 8px;
        """)
        form_layout.addRow("Email:", self.email_input)

        layout.addLayout(form_layout)
        layout.addStretch()

    def create_security_tab(self):
        """Создает содержимое вкладки безопасности"""
        layout = QtWidgets.QVBoxLayout(self.security_tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Заголовок
        security_title = QtWidgets.QLabel("Изменение пароля")
        security_title.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
        layout.addWidget(security_title)

        # Форма изменения пароля
        form_layout = QtWidgets.QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(QtCore.Qt.AlignRight)

        self.current_password = QtWidgets.QLineEdit()
        self.current_password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.current_password.setStyleSheet("""
            background-color: white;
            border: 1px solid #999;
            border-radius: 5px;
            padding: 8px;
        """)
        form_layout.addRow("Текущий пароль:", self.current_password)

        self.new_password = QtWidgets.QLineEdit()
        self.new_password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.new_password.setStyleSheet("""
            background-color: white;
            border: 1px solid #999;
            border-radius: 5px;
            padding: 8px;
        """)
        form_layout.addRow("Новый пароль:", self.new_password)

        self.confirm_password = QtWidgets.QLineEdit()
        self.confirm_password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.confirm_password.setStyleSheet("""
            background-color: white;
            border: 1px solid #999;
            border-radius: 5px;
            padding: 8px;
        """)
        form_layout.addRow("Подтвердите пароль:", self.confirm_password)

        layout.addLayout(form_layout)

        # Кнопка изменения пароля
        self.change_password_btn = QtWidgets.QPushButton("Изменить пароль")
        self.change_password_btn.setStyleSheet("""
            background-color: #9370DB;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 16px;
            margin-top: 10px;
        """)
        self.change_password_btn.clicked.connect(self.change_password)

        password_btn_layout = QtWidgets.QHBoxLayout()
        password_btn_layout.addStretch()
        password_btn_layout.addWidget(self.change_password_btn)
        password_btn_layout.addStretch()

        layout.addLayout(password_btn_layout)
        layout.addStretch()

    def load_profile_data(self):
        """Загружает данные профиля из базы данных"""
        try:
            cursor = self.connection.cursor()

            # Проверяем, есть ли колонка email в таблице users
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'email'
            """)
            has_email_column = cursor.fetchone() is not None

            # Проверяем, есть ли таблица user_profiles
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'user_profiles'
                )
            """)
            has_profile_table = cursor.fetchone()[0]

            # Получаем данные пользователя
            if has_email_column:
                cursor.execute("SELECT email FROM users WHERE username = %s", (self.username,))
                result = cursor.fetchone()
                if result and result[0]:
                    self.email_input.setText(result[0])

            # Если есть таблица профилей, загружаем аватар
            if has_profile_table:
                cursor.execute(
                    "SELECT avatar_path FROM user_profiles WHERE username = %s",
                    (self.username,)
                )
                result = cursor.fetchone()
                if result and result[0]:
                    avatar_path = result[0]

                    # Загружаем аватар
                    if avatar_path and os.path.exists(avatar_path):
                        self.avatar_path = avatar_path
                        self.load_avatar(avatar_path)

            cursor.close()
        except Exception as e:
            print(f"[ERROR] Failed to load profile data: {e}")
            QtWidgets.QMessageBox.warning(
                self,
                "Ошибка",
                f"Не удалось загрузить данные профиля: {str(e)}"
            )

    def load_avatar(self, path):
        """Загружает аватар из указанного пути"""
        try:
            pixmap = QtGui.QPixmap(path)
            if not pixmap.isNull():
                # Масштабируем и обрезаем до круга
                size = min(pixmap.width(), pixmap.height())
                pixmap = pixmap.scaled(
                    100, 100,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                )

                # Создаем круглую маску
                mask = QtGui.QPixmap(100, 100)
                mask.fill(QtCore.Qt.transparent)
                painter = QtGui.QPainter(mask)
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setBrush(QtCore.Qt.white)
                painter.drawEllipse(0, 0, 100, 100)
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

                # Убираем цветной фон, если есть аватар
                self.avatar_frame.setStyleSheet("""
                    background-color: transparent;
                    border-radius: 50px;
                    border: 2px solid #9370DB;
                """)
        except Exception as e:
            print(f"[ERROR] Failed to load avatar: {e}")

    def change_avatar(self):
        """Открывает диалог выбора и редактирования аватара"""
        # Сначала выбираем файл
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Выбрать изображение",
            "",
            "Изображения (*.png *.jpg *.jpeg *.gif *.bmp)"
        )

        if file_path:
            # Открываем редактор аватара
            editor = AvatarEditorDialog(file_path, self)
            if editor.exec_() == QtWidgets.QDialog.Accepted:
                # Получаем обработанное изображение
                processed_image = editor.get_processed_image()

                # Создаем директорию для аватаров, если она не существует
                avatar_dir = os.path.join("avatars")
                os.makedirs(avatar_dir, exist_ok=True)

                # Сохраняем аватар
                avatar_path = os.path.join(avatar_dir, f"{self.username}_avatar.png")
                processed_image.save(avatar_path, "PNG")

                # Обновляем аватар в интерфейсе
                self.avatar_path = avatar_path
                self.load_avatar(avatar_path)
                self.avatar_changed = True

    def remove_avatar(self):
        """Удаляет текущий аватар"""
        if self.avatar_path and os.path.exists(self.avatar_path):
            reply = QtWidgets.QMessageBox.question(
                self,
                "Подтверждение",
                "Вы уверены, что хотите удалить аватар?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )

            if reply == QtWidgets.QMessageBox.Yes:
                # Удаляем файл аватара
                try:
                    os.remove(self.avatar_path)
                except Exception as e:
                    print(f"[ERROR] Failed to delete avatar file: {e}")

                # Сбрасываем аватар в интерфейсе
                self.avatar_frame.setPixmap(QtGui.QPixmap())
                self.avatar_frame.setText("👤")
                self.avatar_frame.setFont(QtGui.QFont("Arial", 40))
                self.avatar_frame.setStyleSheet("""
                    background-color: #d8c4eb;
                    border-radius: 50px;
                    border: 2px solid #9370DB;
                """)
                self.avatar_path = None
                self.avatar_changed = True

                # Немедленно отправляем сигнал об обновлении профиля
                profile_data = {
                    "username": self.username,
                    "avatar_path": None,
                    "email": self.email_input.text() if hasattr(self, "email_input") else ""
                }
                self.profile_updated.emit(profile_data)

    def change_password(self):
        """Изменяет пароль пользователя"""
        current_password = self.current_password.text()
        new_password = self.new_password.text()
        confirm_password = self.confirm_password.text()

        if not current_password or not new_password or not confirm_password:
            QtWidgets.QMessageBox.warning(
                self,
                "Ошибка",
                "Пожалуйста, заполните все поля."
            )
            return

        if new_password != confirm_password:
            QtWidgets.QMessageBox.warning(
                self,
                "Ошибка",
                "Новый пароль и подтверждение не совпадают."
            )
            return

        try:
            cursor = self.connection.cursor()

            # Проверяем текущий пароль
            cursor.execute("SELECT password FROM users WHERE username = %s", (self.username,))
            result = cursor.fetchone()

            if result:
                stored_hashed_password = result[0]
                if bcrypt.checkpw(current_password.encode('utf-8'), stored_hashed_password.encode('utf-8')):
                    # Хешируем новый пароль
                    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

                    # Обновляем пароль в базе данных
                    cursor.execute(
                        "UPDATE users SET password = %s WHERE username = %s",
                        (hashed_password, self.username)
                    )
                    self.connection.commit()

                    QtWidgets.QMessageBox.information(
                        self,
                        "Успех",
                        "Пароль успешно изменен."
                    )

                    # Очищаем поля
                    self.current_password.clear()
                    self.new_password.clear()
                    self.confirm_password.clear()
                else:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Ошибка",
                        "Неверный текущий пароль."
                    )
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Ошибка",
                    "Пользователь не найден."
                )

            cursor.close()
        except Exception as e:
            print(f"[ERROR] Failed to change password: {e}")
            self.connection.rollback()
            QtWidgets.QMessageBox.warning(
                self,
                "Ошибка",
                f"Не удалось изменить пароль: {str(e)}"
            )

    def save_changes(self):
        """Сохраняет изменения профиля"""
        email = self.email_input.text()

        try:
            cursor = self.connection.cursor()

            # Проверяем, есть ли колонка email в таблице users
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'email'
            """)
            has_email_column = cursor.fetchone() is not None

            # Проверяем, есть ли таблица user_profiles
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'user_profiles'
                )
            """)
            has_profile_table = cursor.fetchone()[0]

            # Если нет таблицы профилей, создаем ее
            if not has_profile_table:
                print("[DATABASE] Creating user_profiles table")
                cursor.execute("""
                    CREATE TABLE user_profiles (
                        username VARCHAR(50) PRIMARY KEY REFERENCES users(username),
                        avatar_path VARCHAR(255)
                    )
                """)
                self.connection.commit()
                print("[DATABASE] Created user_profiles table")

            # Обновляем email, если есть такая колонка
            if has_email_column and email:
                cursor.execute(
                    "UPDATE users SET email = %s WHERE username = %s",
                    (email, self.username)
                )

            # Обновляем профиль пользователя
            cursor.execute(
                """
                INSERT INTO user_profiles (username, avatar_path)
                VALUES (%s, %s)
                ON CONFLICT (username) 
                DO UPDATE SET avatar_path = %s
                """,
                (self.username, self.avatar_path, self.avatar_path)
            )

            self.connection.commit()

            # Отправляем сигнал об обновлении профиля
            profile_data = {
                "username": self.username,
                "avatar_path": self.avatar_path,
                "email": email
            }
            self.profile_updated.emit(profile_data)

            QtWidgets.QMessageBox.information(
                self,
                "Успех",
                "Профиль успешно обновлен."
            )

            self.accept()

            cursor.close()
        except Exception as e:
            print(f"[ERROR] Failed to save profile changes: {e}")
            self.connection.rollback()
            QtWidgets.QMessageBox.warning(
                self,
                "Ошибка",
                f"Не удалось сохранить изменения: {str(e)}"
            )