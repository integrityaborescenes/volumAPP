import sys
from PyQt5 import QtWidgets, QtCore, QtGui


class AvatarEditorDialog(QtWidgets.QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.processed_image = None

        self.setWindowTitle("Редактирование аватара")
        self.resize(400, 350)
        self.setStyleSheet("background-color: #e0e0e0;")

        # Загружаем изображение
        self.original_pixmap = QtGui.QPixmap(image_path)
        if self.original_pixmap.isNull():
            QtWidgets.QMessageBox.warning(
                self,
                "Ошибка",
                "Не удалось загрузить изображение."
            )
            self.reject()
            return

        # Масштабируем изображение, если оно слишком большое
        max_size = 800
        if self.original_pixmap.width() > max_size or self.original_pixmap.height() > max_size:
            self.original_pixmap = self.original_pixmap.scaled(
                max_size, max_size,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )

        # Создаем копию для отображения
        self.working_pixmap = self.original_pixmap.copy()

        # Основной макет
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # Заголовок
        self.title_label = QtWidgets.QLabel("Редактирование аватара")
        self.title_label.setFont(QtGui.QFont("Arial", 16, QtGui.QFont.Bold))
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.title_label)

        # Область предпросмотра
        self.preview_area = QtWidgets.QLabel()
        self.preview_area.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_area.setMinimumSize(200, 200)
        self.preview_area.setStyleSheet("background-color: #d9d9d9; border: 1px solid #999;")

        # Создаем круглую версию изображения для предпросмотра
        self.preview_pixmap = self.create_circular_pixmap(self.working_pixmap, 200)
        self.preview_area.setPixmap(self.preview_pixmap)

        self.layout.addWidget(self.preview_area)

        # Кнопки внизу
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(10)

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
        self.save_btn.clicked.connect(self.accept)

        buttons_layout.addWidget(self.cancel_btn)
        buttons_layout.addWidget(self.save_btn)

        self.layout.addLayout(buttons_layout)

    def create_circular_pixmap(self, source_pixmap, size):
        """Создает круглую версию изображения с улучшенным качеством"""
        # Создаем квадратное изображение, обрезая его по центру
        square_size = min(source_pixmap.width(), source_pixmap.height())
        x_offset = (source_pixmap.width() - square_size) // 2
        y_offset = (source_pixmap.height() - square_size) // 2

        # Обрезаем изображение до квадрата
        square_pixmap = source_pixmap.copy(
            x_offset, y_offset, square_size, square_size
        )

        # Масштабируем квадратное изображение до нужного размера
        scaled_pixmap = square_pixmap.scaled(
            size, size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )

        # Создаем пустое изображение с прозрачным фоном
        result_pixmap = QtGui.QPixmap(size, size)
        result_pixmap.fill(QtCore.Qt.transparent)

        # Создаем объект QPainter для рисования
        painter = QtGui.QPainter(result_pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)

        # Создаем круглый путь
        path = QtGui.QPainterPath()
        path.addEllipse(0, 0, size, size)

        # Устанавливаем отсечение по круглому пути
        painter.setClipPath(path)

        # Рисуем изображение
        painter.drawPixmap(0, 0, scaled_pixmap)

        # Добавляем круглую рамку
        pen = QtGui.QPen(QtGui.QColor(150, 150, 150, 100), 2)
        painter.setPen(pen)
        painter.drawEllipse(1, 1, size - 2, size - 2)

        painter.end()

        return result_pixmap

    def get_processed_image(self):
        """Возвращает обработанное изображение"""
        # Создаем круглую версию изображения для сохранения
        avatar_size = 200
        return self.create_circular_pixmap(self.working_pixmap, avatar_size)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    # ТЕСТ
    test_image = QtGui.QPixmap(300, 200)
    test_image.fill(QtGui.QColor(200, 200, 255))

    painter = QtGui.QPainter(test_image)
    painter.setPen(QtGui.QPen(QtCore.Qt.blue, 5))
    painter.drawEllipse(50, 30, 200, 140)
    painter.setPen(QtGui.QPen(QtCore.Qt.red, 5))
    painter.drawRect(100, 50, 100, 100)
    painter.end()

    test_image_path = "test_avatar.png"
    test_image.save(test_image_path)

    dialog = AvatarEditorDialog(test_image_path)
    if dialog.exec_() == QtWidgets.QDialog.Accepted:
        processed_image = dialog.get_processed_image()
        processed_image.save("processed_avatar.png")
        print("Аватар сохранен как processed_avatar.png")

    import os

    if os.path.exists(test_image_path):
        os.remove(test_image_path)