import os
from PyQt5 import QtWidgets, QtCore, QtGui


class AttachmentDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить вложение")
        self.resize(400, 300)
        self.setStyleSheet("background-color: #d9d9d9; border-radius: 10px;")
        self.selected_file = None

        # Основной макет
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # Заголовок
        self.title_label = QtWidgets.QLabel("Добавить вложение")
        self.title_label.setFont(QtGui.QFont("Arial", 16, QtGui.QFont.Bold))
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.title_label)

        # Сетка типов файлов
        self.types_grid = QtWidgets.QGridLayout()
        self.types_grid.setSpacing(10)

        # Создаем кнопки для типов файлов
        self.create_type_button("Изображения", "🖼️", 0, 0, self.select_image)
        self.create_type_button("Документы", "📄", 0, 1, self.select_document)
        self.create_type_button("Аудио", "🎵", 1, 0, self.select_audio)
        self.create_type_button("Видео", "🎬", 1, 1, self.select_video)

        self.layout.addLayout(self.types_grid)
        self.layout.addStretch()

        # Область для перетаскивания файлов
        self.drop_area = QtWidgets.QLabel("Или перетащите файлы сюда")
        self.drop_area.setAlignment(QtCore.Qt.AlignCenter)
        self.drop_area.setStyleSheet("""
            background-color: #e0e0e0;
            border: 2px dashed #999;
            border-radius: 10px;
            padding: 20px;
        """)
        self.drop_area.setMinimumHeight(100)
        self.layout.addWidget(self.drop_area)

        # Включаем поддержку перетаскивания
        self.setAcceptDrops(True)

    def create_type_button(self, text, icon, row, col, slot):
        button = QtWidgets.QPushButton()
        button.setFixedSize(150, 80)
        button.setStyleSheet("""
            background-color: #e0e0e0;
            border-radius: 10px;
            padding: 10px;
        """)

        layout = QtWidgets.QVBoxLayout(button)
        layout.setAlignment(QtCore.Qt.AlignCenter)

        icon_label = QtWidgets.QLabel(icon)
        icon_label.setFont(QtGui.QFont("Arial", 24))
        icon_label.setAlignment(QtCore.Qt.AlignCenter)

        text_label = QtWidgets.QLabel(text)
        text_label.setAlignment(QtCore.Qt.AlignCenter)

        layout.addWidget(icon_label)
        layout.addWidget(text_label)

        button.clicked.connect(slot)
        self.types_grid.addWidget(button, row, col)

    def select_image(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Выбрать изображение", "", "Изображения (*.png *.jpg *.jpeg *.gif *.bmp)"
        )
        if file_path:
            self.accept_file(file_path)

    def select_document(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Выбрать документ", "", "Документы (*.pdf *.doc *.docx *.txt)"
        )
        if file_path:
            self.accept_file(file_path)

    def select_audio(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Выбрать аудио", "", "Аудио (*.mp3 *.wav *.ogg)"
        )
        if file_path:
            self.accept_file(file_path)

    def select_video(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Выбрать видео", "", "Видео (*.mp4 *.avi *.mov *.wmv)"
        )
        if file_path:
            self.accept_file(file_path)

    def accept_file(self, file_path):
        self.selected_file = file_path
        self.accept()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            self.drop_area.setStyleSheet("""
                background-color: #d8c4eb;
                border: 2px dashed #9370DB;
                border-radius: 10px;
                padding: 20px;
            """)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_area.setStyleSheet("""
            background-color: #e0e0e0;
            border: 2px dashed #999;
            border-radius: 10px;
            padding: 20px;
        """)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                self.accept_file(file_path)
        else:
            event.ignore()
