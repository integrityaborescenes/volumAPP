import sys
import os
import random
import string
from PyQt5 import QtWidgets, QtCore, QtGui
from avatar_editor import AvatarEditorDialog


class CreateGroupDialog(QtWidgets.QDialog):
    group_created = QtCore.pyqtSignal(dict)  # Сигнал о создании группы

    def __init__(self, connection, username, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.username = username
        self.avatar_path = None

        self.setWindowTitle("Создать группу")
        self.resize(450, 600)
        self.setStyleSheet("background-color: #e0e0e0;")

        # Основной макет
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        # Заголовок
        self.title_label = QtWidgets.QLabel("Создание новой группы")
        self.title_label.setFont(QtGui.QFont("Arial", 16, QtGui.QFont.Bold))
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.title_label)

        # Аватар группы
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

        avatar_buttons_layout = QtWidgets.QVBoxLayout()
        avatar_buttons_layout.setSpacing(10)

        self.change_avatar_btn = QtWidgets.QPushButton("Выбрать аватар")
        self.change_avatar_btn.setStyleSheet("""
            background-color: #9370DB;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: bold;
        """)
        self.change_avatar_btn.clicked.connect(self.change_avatar)

        self.remove_avatar_btn = QtWidgets.QPushButton("Удалить аватар")
        self.remove_avatar_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999;
            border-radius: 8px;
            padding: 8px 16px;
        """)
        self.remove_avatar_btn.clicked.connect(self.remove_avatar)

        avatar_buttons_layout.addWidget(self.change_avatar_btn)
        avatar_buttons_layout.addWidget(self.remove_avatar_btn)
        avatar_buttons_layout.addStretch()

        avatar_container.addWidget(self.avatar_frame)
        avatar_container.addSpacing(20)
        avatar_container.addLayout(avatar_buttons_layout)
        avatar_container.addStretch()

        avatar_section.addLayout(avatar_container)
        self.layout.addLayout(avatar_section)

        # Название группы
        name_section = QtWidgets.QVBoxLayout()
        name_label = QtWidgets.QLabel("Название группы")
        name_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        name_section.addWidget(name_label)

        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("Введите название группы")
        self.name_input.setStyleSheet("""
            background-color: white;
            border: 2px solid #ddd;
            border-radius: 8px;
            padding: 12px;
            font-size: 14px;
        """)
        self.name_input.setMaxLength(100)
        name_section.addWidget(self.name_input)

        self.layout.addLayout(name_section)

        # Уникальная ссылка
        link_section = QtWidgets.QVBoxLayout()
        link_label = QtWidgets.QLabel("Уникальная ссылка")
        link_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        link_section.addWidget(link_label)

        # Контейнер для ссылки и кнопки генерации
        link_container = QtWidgets.QHBoxLayout()

        self.link_input = QtWidgets.QLineEdit()
        self.link_input.setPlaceholderText("введите-уникальную-ссылку")
        self.link_input.setStyleSheet("""
            background-color: white;
            border: 2px solid #ddd;
            border-radius: 8px;
            padding: 12px;
            font-size: 14px;
        """)
        self.link_input.setMaxLength(50)

        self.generate_link_btn = QtWidgets.QPushButton("🎲")
        self.generate_link_btn.setFixedSize(45, 45)
        self.generate_link_btn.setStyleSheet("""
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 18px;
        """)
        self.generate_link_btn.setToolTip("Сгенерировать случайную ссылку")
        self.generate_link_btn.clicked.connect(self.generate_random_link)

        link_container.addWidget(self.link_input)
        link_container.addWidget(self.generate_link_btn)

        link_section.addLayout(link_container)

        # Подсказка для ссылки
        link_hint = QtWidgets.QLabel("Ссылка должна содержать только буквы, цифры и дефисы")
        link_hint.setStyleSheet("color: #666; font-size: 11px;")
        link_section.addWidget(link_hint)

        self.layout.addLayout(link_section)

        # Описание группы (опционально)
        desc_section = QtWidgets.QVBoxLayout()
        desc_label = QtWidgets.QLabel("Описание группы (необязательно)")
        desc_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        desc_section.addWidget(desc_label)

        self.description_input = QtWidgets.QTextEdit()
        self.description_input.setPlaceholderText("Краткое описание группы...")
        self.description_input.setStyleSheet("""
            background-color: white;
            border: 2px solid #ddd;
            border-radius: 8px;
            padding: 12px;
            font-size: 14px;
        """)
        self.description_input.setMaximumHeight(80)
        desc_section.addWidget(self.description_input)

        self.layout.addLayout(desc_section)

        # Кнопки
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

        self.create_btn = QtWidgets.QPushButton("Создать группу")
        self.create_btn.setStyleSheet("""
            background-color: #9370DB;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 24px;
            font-size: 14px;
            font-weight: bold;
        """)
        self.create_btn.clicked.connect(self.create_group)

        self.buttons_layout.addWidget(self.cancel_btn)
        self.buttons_layout.addWidget(self.create_btn)

        self.layout.addLayout(self.buttons_layout)

        # Валидация ввода
        self.name_input.textChanged.connect(self.validate_input)
        self.link_input.textChanged.connect(self.validate_input)

        # Генерируем начальную ссылку
        self.generate_random_link()

    def generate_random_link(self):
        """Генерирует случайную уникальную ссылку"""
        # Генерируем случайную строку из букв и цифр
        characters = string.ascii_lowercase + string.digits
        random_part = ''.join(random.choice(characters) for _ in range(8))

        # Добавляем префикс для читаемости
        link = f"group-{random_part}"

        self.link_input.setText(link)

    def validate_input(self):
        """Валидация введенных данных"""
        name = self.name_input.text().strip()
        link = self.link_input.text().strip()

        # Проверяем название
        name_valid = len(name) >= 3

        # Проверяем ссылку (только буквы, цифры и дефисы)
        import re
        link_valid = bool(re.match(r'^[a-zA-Z0-9-]+$', link)) and len(link) >= 3

        # Активируем кнопку создания только если все поля валидны
        self.create_btn.setEnabled(name_valid and link_valid)

        # Меняем цвет рамки в зависимости от валидности
        if name:
            name_color = "#4CAF50" if name_valid else "#FF5252"
            self.name_input.setStyleSheet(f"""
                background-color: white;
                border: 2px solid {name_color};
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
            """)

        if link:
            link_color = "#4CAF50" if link_valid else "#FF5252"
            self.link_input.setStyleSheet(f"""
                background-color: white;
                border: 2px solid {link_color};
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
            """)

    def change_avatar(self):
        """Открывает диалог выбора и редактирования аватара"""
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
                    self.avatar_path = avatar_path
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
                self.avatar_path = avatar_path
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
        """Удаляет текущий аватар"""
        if self.avatar_path and os.path.exists(self.avatar_path):
            try:
                os.remove(self.avatar_path)
            except Exception as e:
                print(f"[ERROR] Failed to delete avatar file: {e}")

        # Сбрасываем аватар в интерфейсе
        self.avatar_frame.setPixmap(QtGui.QPixmap())
        self.avatar_frame.setText("👥")
        self.avatar_frame.setFont(QtGui.QFont("Arial", 50))
        self.avatar_frame.setStyleSheet("""
            background-color: #d8c4eb;
            border-radius: 60px;
            border: 2px solid #9370DB;
        """)
        self.avatar_path = None

    def create_group(self):
        """Создает новую группу"""
        name = self.name_input.text().strip()
        link = self.link_input.text().strip()
        description = self.description_input.toPlainText().strip()

        if not name or not link:
            QtWidgets.QMessageBox.warning(
                self,
                "Ошибка",
                "Пожалуйста, заполните название и ссылку группы."
            )
            return

        try:
            cursor = self.connection.cursor()

            # Проверяем уникальность ссылки
            cursor.execute("SELECT id FROM groups WHERE invite_link = %s", (link,))
            if cursor.fetchone():
                QtWidgets.QMessageBox.warning(
                    self,
                    "Ошибка",
                    "Группа с такой ссылкой уже существует. Выберите другую ссылку."
                )
                cursor.close()
                return

            # Создаем группу
            cursor.execute(
                """
                INSERT INTO groups (name, invite_link, avatar_path, creator_username, description)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (name, link, self.avatar_path, self.username, description)
            )

            group_id = cursor.fetchone()[0]

            # Добавляем создателя как администратора группы
            cursor.execute(
                """
                INSERT INTO group_members (group_id, username, role)
                VALUES (%s, %s, 'admin')
                """,
                (group_id, self.username)
            )

            self.connection.commit()
            cursor.close()

            # Отправляем сигнал о создании группы
            group_data = {
                'id': group_id,
                'name': name,
                'invite_link': link,
                'avatar_path': self.avatar_path,
                'description': description,
                'creator': self.username
            }

            self.group_created.emit(group_data)
            self.accept()

        except Exception as e:
            self.connection.rollback()
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось создать группу: {str(e)}"
            )
            if cursor:
                cursor.close()