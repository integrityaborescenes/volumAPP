import sys
from PyQt5 import QtWidgets, QtCore, QtGui


class SearchBar(QtWidgets.QWidget):
    """Панель поиска, которая появляется при нажатии на кнопку поиска"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.current_match = -1
        self.matches = []

        # Настройка внешнего вида
        self.setStyleSheet("background-color: #d9d9d9; border-radius: 10px;")
        self.setFixedHeight(40)

        # Основной макет
        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)
        self.layout.setSpacing(5)

        # Поле ввода
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Поиск в сообщениях")
        self.search_input.setStyleSheet(
            "background-color: white; border-radius: 15px; padding: 5px 10px;"
        )
        self.search_input.textChanged.connect(self.search_text)

        # Счетчик совпадений
        self.counter_label = QtWidgets.QLabel("0/0")
        self.counter_label.setStyleSheet("color: #666;")

        # Кнопки навигации
        self.prev_btn = QtWidgets.QPushButton("▲")
        self.prev_btn.setFixedSize(30, 30)
        self.prev_btn.setStyleSheet(
            "background-color: #e0e0e0; border-radius: 15px;"
        )
        self.prev_btn.clicked.connect(self.go_to_prev_match)

        self.next_btn = QtWidgets.QPushButton("▼")
        self.next_btn.setFixedSize(30, 30)
        self.next_btn.setStyleSheet(
            "background-color: #e0e0e0; border-radius: 15px;"
        )
        self.next_btn.clicked.connect(self.go_to_next_match)

        # Кнопка закрытия
        self.close_btn = QtWidgets.QPushButton("✕")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet(
            "background-color: #e0e0e0; border-radius: 15px;"
        )
        self.close_btn.clicked.connect(self.close_search)

        # Добавляем элементы в макет
        self.layout.addWidget(self.search_input)
        self.layout.addWidget(self.counter_label)
        self.layout.addWidget(self.prev_btn)
        self.layout.addWidget(self.next_btn)
        self.layout.addWidget(self.close_btn)

        # Скрываем панель по умолчанию
        self.hide()

    def search_text(self):
        """Поиск текста в диалоге (работает как для личных чатов, так и для групп)"""
        search_text = self.search_input.text().strip().lower()

        # Если текст пустой, очищаем результаты
        if not search_text:
            self.clear_highlights()
            self.counter_label.setText("0/0")
            self.current_match = -1
            self.matches = []
            return

        # Проверяем, есть ли активный чат (личный или групповой)
        if not (self.parent.current_chat_with or self.parent.current_group):
            self.counter_label.setText("Нет активного чата")
            return

        # Получаем текстовый документ
        document = self.parent.text_display.document()

        # Очищаем предыдущие выделения
        self.clear_highlights()

        # Список для хранения позиций совпадений
        self.matches = []

        # Регулярные выражения для определения даты и времени
        import re
        time_patterns = [
            r'\d{1,2}:\d{2}',  # Формат ЧЧ:ММ или Ч:ММ
            r'\d{1,2}:\d{2}:\d{2}',  # Формат ЧЧ:ММ:СС
        ]
        date_patterns = [
            r'\d{1,2}\.\d{1,2}\.\d{2,4}',  # Формат ДД.ММ.ГГГГ или ДД.ММ.ГГ
            r'\d{1,2}/\d{1,2}/\d{2,4}',  # Формат ДД/ММ/ГГГГ
            r'\d{4}-\d{1,2}-\d{1,2}',  # Формат ГГГГ-ММ-ДД
        ]

        # Объединяем все шаблоны
        all_patterns = time_patterns + date_patterns

        # Перебираем все блоки текста в документе
        for block_num in range(document.blockCount()):
            block = document.findBlockByNumber(block_num)
            block_text = block.text()
            block_text_lower = block_text.lower()

            # Пропускаем пустые блоки
            if not block_text_lower:
                continue

            # Создаем копию текста блока для обработки
            processed_text = block_text_lower

            # Находим и маскируем все даты и времена в тексте
            for pattern in all_patterns:
                for match in re.finditer(pattern, processed_text):
                    start, end = match.span()
                    # Заменяем найденную дату/время на пробелы
                    processed_text = processed_text[:start] + ' ' * (end - start) + processed_text[end:]

            # Теперь ищем совпадения в обработанном тексте
            search_pos = 0
            while True:
                match_pos = processed_text.find(search_text, search_pos)
                if match_pos == -1:
                    break

                # Проверяем, не находится ли совпадение рядом с шаблонами даты/времени
                surrounding_start = max(0, match_pos - 3)
                surrounding_end = min(len(processed_text), match_pos + len(search_text) + 3)
                surrounding_text = block_text_lower[surrounding_start:surrounding_end]

                # Проверяем, содержит ли окружающий текст шаблоны даты/времени
                has_time_pattern = False
                for pattern in all_patterns:
                    if re.search(pattern, surrounding_text):
                        has_time_pattern = True
                        break

                # Если совпадение не рядом с шаблоном даты/времени
                if not has_time_pattern:
                    # Вычисляем позицию в документе
                    global_pos = block.position() + match_pos
                    self.matches.append(global_pos)

                # Продолжаем поиск с позиции после текущего совпадения
                search_pos = match_pos + len(search_text)

        # Сортируем совпадения по позиции
        self.matches.sort()

        # Обновляем счетчик
        match_count = len(self.matches)
        if match_count > 0:
            self.current_match = 0
            # Определяем тип чата для отображения
            chat_type = "группе" if self.parent.current_group else "чате"
            self.counter_label.setText(f"1/{match_count} в {chat_type}")
            self.highlight_current_match()
        else:
            self.counter_label.setText("0/0")
            self.show_no_matches_message()

    def highlight_current_match(self):
        """Выделяет текущее совпадение"""
        if not self.matches or self.current_match < 0 or self.current_match >= len(self.matches):
            return

        # Получаем позицию текущего совпадения
        position = self.matches[self.current_match]

        # Создаем курсор и выделяем текст
        cursor = QtGui.QTextCursor(self.parent.text_display.document())
        cursor.setPosition(position)
        cursor.movePosition(
            QtGui.QTextCursor.Right,
            QtGui.QTextCursor.KeepAnchor,
            len(self.search_input.text())
        )

        # Устанавливаем формат выделения
        format = QtGui.QTextCharFormat()
        format.setBackground(QtGui.QColor("yellow"))
        cursor.mergeCharFormat(format)

        # Устанавливаем курсор и прокручиваем к выделенному тексту
        self.parent.text_display.setTextCursor(cursor)
        self.parent.text_display.ensureCursorVisible()

    def clear_highlights(self):
        """Очищает все выделения"""
        # Сбрасываем формат всего текста
        cursor = QtGui.QTextCursor(self.parent.text_display.document())
        cursor.select(QtGui.QTextCursor.Document)
        format = QtGui.QTextCharFormat()
        format.setBackground(QtGui.QColor("transparent"))
        cursor.mergeCharFormat(format)

    def go_to_next_match(self):
        """Переход к следующему совпадению"""
        if not self.matches:
            return

        # Очищаем предыдущее выделение
        self.clear_highlights()

        # Переходим к следующему совпадению
        self.current_match = (self.current_match + 1) % len(self.matches)

        # Обновляем счетчик с указанием типа чата
        chat_type = "группе" if self.parent.current_group else "чате"
        self.counter_label.setText(f"{self.current_match + 1}/{len(self.matches)} в {chat_type}")

        # Выделяем текущее совпадение
        self.highlight_current_match()

    def go_to_prev_match(self):
        """Переход к предыдущему совпадению"""
        if not self.matches:
            return

        # Очищаем предыдущее выделение
        self.clear_highlights()

        # Переходим к предыдущему совпадению
        self.current_match = (self.current_match - 1) % len(self.matches)

        # Обновляем счетчик с указанием типа чата
        chat_type = "группе" if self.parent.current_group else "чате"
        self.counter_label.setText(f"{self.current_match + 1}/{len(self.matches)} в {chat_type}")

        # Выделяем текущее совпадение
        self.highlight_current_match()

    def close_search(self):
        """Закрывает панель поиска"""
        # Очищаем выделения
        self.clear_highlights()

        # Скрываем панель
        self.hide()

        # Возвращаем фокус на текстовое поле
        self.parent.text_display.setFocus()

    def show_no_matches_message(self):
        """Показывает сообщение, что совпадения не найдены"""
        self.counter_label.setText("Совпадения не найдены")
        self.counter_label.setStyleSheet("color: red;")

        # Через 2 секунды возвращаем обычный стиль
        QtCore.QTimer.singleShot(2000, lambda: self.counter_label.setStyleSheet("color: #666;"))


# Функция для добавления кнопки поиска и панели поиска в ChatWindow
def add_search_functionality(chat_window):
    # Создаем кнопку поиска
    search_btn = QtWidgets.QPushButton("🔍")
    search_btn.setFixedSize(30, 30)
    search_btn.setFont(QtGui.QFont("Arial", 12))
    search_btn.setStyleSheet("background: transparent; border: none;")
    search_btn.setToolTip("Поиск по сообщениям")

    # Создаем панель поиска
    search_bar = SearchBar(chat_window)

    # Подключаем кнопку к показу панели поиска
    search_btn.clicked.connect(lambda: toggle_search_bar(search_bar))

    # Добавляем кнопку в верхнюю панель перед кнопкой уведомлений
    chat_window.top_bar_layout.insertWidget(
        chat_window.top_bar_layout.indexOf(chat_window.notification_btn),
        search_btn
    )

    # Добавляем панель поиска в макет чата
    # Вставляем панель поиска после заголовка чата и перед областью сообщений
    chat_window.chat_layout.insertWidget(0, search_bar)

    # Сохраняем ссылки на кнопку и панель поиска
    chat_window.search_btn = search_btn
    chat_window.search_bar = search_bar

    return search_btn, search_bar


def toggle_search_bar(search_bar):
    """Показывает или скрывает панель поиска"""
    if search_bar.isVisible():
        search_bar.hide()
    else:
        search_bar.show()
        search_bar.search_input.setFocus()
        search_bar.search_input.clear()

