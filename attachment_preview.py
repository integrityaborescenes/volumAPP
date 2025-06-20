import os
from PyQt5 import QtWidgets, QtCore, QtGui


class AttachmentPreview(QtWidgets.QWidget):
    removed = QtCore.pyqtSignal()

    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.file_size = os.path.getsize(file_path)
        self.file_ext = os.path.splitext(file_path)[1].lower()

        self.setStyleSheet("background-color: #e0e0e0; border-radius: 10px;")
        self.setMaximumHeight(60)

        # Основной макет
        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)

        # Иконка файла
        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setAlignment(QtCore.Qt.AlignCenter)

        # Устанавливаем иконку в зависимости от типа файла
        if self.file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            self.set_image_preview()
            self.icon_text = "🖼️"
        elif self.file_ext in ['.pdf', '.doc', '.docx', '.txt']:
            self.icon_text = "📄"
        elif self.file_ext in ['.mp3', '.wav', '.ogg']:
            self.icon_text = "🎵"
        elif self.file_ext in ['.mp4', '.avi', '.mov', '.wmv']:
            self.icon_text = "🎬"
        else:
            self.icon_text = "📎"

        self.icon_label.setText(self.icon_text)
        self.icon_label.setFont(QtGui.QFont("Arial", 16))
        self.layout.addWidget(self.icon_label)

        # Информация о файле
        self.info_layout = QtWidgets.QHBoxLayout()
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_layout.setSpacing(5)

        # Создаем вертикальный макет для имени и размера
        self.text_layout = QtWidgets.QVBoxLayout()
        self.text_layout.setContentsMargins(0, 0, 0, 0)
        self.text_layout.setSpacing(2)

        self.name_label = QtWidgets.QLabel(self.file_name)
        self.name_label.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Bold))

        self.size_label = QtWidgets.QLabel(self.format_size(self.file_size))
        self.size_label.setFont(QtGui.QFont("Arial", 8))
        self.size_label.setStyleSheet("color: #666;")

        self.text_layout.addWidget(self.name_label)
        self.text_layout.addWidget(self.size_label)

        self.info_layout.addLayout(self.text_layout)
        self.info_layout.addStretch()

        self.layout.addLayout(self.info_layout)
        self.layout.addStretch()

        # Кнопка удаления
        self.remove_btn = QtWidgets.QPushButton("✕")
        self.remove_btn.setFixedSize(30, 30)
        self.remove_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border-radius: 15px;
            font-size: 14px;
            font-weight: bold;
        """)
        self.remove_btn.clicked.connect(self.removed.emit)
        self.layout.addWidget(self.remove_btn)

    def set_image_preview(self):
        try:
            pixmap = QtGui.QPixmap(self.file_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(36, 36, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                self.icon_label.setPixmap(pixmap)
                return
        except Exception as e:
            print(f"Ошибка загрузки превью изображения: {e}")

        # Запасной вариант - текстовая иконка
        self.icon_label.setText("🖼️")

    def format_size(self, size_bytes):
        # Конвертируем байты в читаемый формат
        if size_bytes < 1024:
            return f"{size_bytes} Б"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} КБ"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} МБ"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} ГБ"
