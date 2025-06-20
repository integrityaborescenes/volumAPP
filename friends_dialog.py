import sys
from PyQt5 import QtWidgets, QtCore, QtGui
import os


class FriendsDialog(QtWidgets.QDialog):
    friendsUpdated = QtCore.pyqtSignal()

    def __init__(self, connection, current_username, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.current_username = current_username
        self.parent = parent
        self.setWindowTitle("Друзья")
        self.resize(400, 500)
        self.setStyleSheet("background-color: #e0e0e0;")

        # Основной макет
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # Заголовок
        self.title_label = QtWidgets.QLabel("Мои друзья")
        self.title_label.setFont(QtGui.QFont("Arial", 16, QtGui.QFont.Bold))
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.title_label)

        # Поисковая строка
        self.search_layout = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Поиск друзей")
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
        self.search_btn.clicked.connect(self.filter_friends)

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

        # Загружаем список друзей
        self.load_friends()

    def load_friends(self, filter_text=""):
        """Загружает список друзей из базы данных"""
        # Очищаем текущий список
        while self.friends_layout.count():
            item = self.friends_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                SELECT 
                    CASE 
                        WHEN user1 = %s THEN user2 
                        ELSE user1 
                    END as friend
                FROM friends 
                WHERE user1 = %s OR user2 = %s
                """,
                (self.current_username, self.current_username, self.current_username)
            )
            friends = cursor.fetchall()
            cursor.close()

            if not friends:
                no_friends = QtWidgets.QLabel("У вас пока нет друзей")
                no_friends.setAlignment(QtCore.Qt.AlignCenter)
                no_friends.setStyleSheet("color: #666; font-size: 14px;")
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
            print(f"[ERROR] Failed to load friends: {e}")
            error_label = QtWidgets.QLabel(f"Ошибка загрузки списка друзей: {str(e)}")
            error_label.setStyleSheet("color: red;")
            self.friends_layout.addWidget(error_label)

    def add_friend_widget(self, friend_name):
        """Добавляет виджет друга в список"""
        friend_widget = QtWidgets.QWidget()
        friend_widget.setStyleSheet("background-color: #f0f0f0; border-radius: 10px;")
        friend_widget.setMinimumHeight(70)

        friend_layout = QtWidgets.QHBoxLayout(friend_widget)
        friend_layout.setContentsMargins(10, 5, 10, 5)

        # Аватар друга
        avatar_frame = QtWidgets.QFrame()
        avatar_frame.setFixedSize(50, 50)
        avatar_frame.setStyleSheet("background-color: #d8c4eb; border-radius: 25px;")

        avatar_layout = QtWidgets.QVBoxLayout(avatar_frame)
        avatar_layout.setContentsMargins(0, 0, 0, 0)

        avatar = QtWidgets.QLabel("👤")
        avatar.setAlignment(QtCore.Qt.AlignCenter)
        avatar.setFont(QtGui.QFont("Arial", 20))
        avatar_layout.addWidget(avatar)

        # Загружаем аватар пользователя, если есть родительский виджет с методом load_user_avatar
        if self.parent and hasattr(self.parent, 'load_user_avatar'):
            has_avatar = self.parent.load_user_avatar(friend_name, avatar)
            if has_avatar:
                avatar_frame.setStyleSheet(
                    "background-color: transparent; border-radius: 25px;")

        friend_layout.addWidget(avatar_frame)

        # Имя друга
        name_label = QtWidgets.QLabel(friend_name)
        name_label.setFont(QtGui.QFont("Arial", 12))
        friend_layout.addWidget(name_label)
        friend_layout.addStretch()

        # Кнопка удаления
        remove_btn = QtWidgets.QPushButton("Удалить из друзей")
        remove_btn.setStyleSheet(
            "background-color: #FF5252; color: white; border-radius: 15px; padding: 5px 15px;"
        )
        remove_btn.clicked.connect(lambda: self.confirm_remove_friend(friend_name))
        friend_layout.addWidget(remove_btn)

        self.friends_layout.addWidget(friend_widget)

    def filter_friends(self):
        """Фильтрует список друзей по введенному тексту"""
        filter_text = self.search_input.text().strip()
        self.load_friends(filter_text)

    def confirm_remove_friend(self, friend_name):
        """Показывает диалог подтверждения удаления друга"""
        confirm_dialog = QtWidgets.QMessageBox(self)
        confirm_dialog.setWindowTitle("Подтверждение")
        confirm_dialog.setText(f"Вы уверены, что хотите удалить {friend_name} из друзей?")
        confirm_dialog.setIcon(QtWidgets.QMessageBox.Question)
        confirm_dialog.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        confirm_dialog.setDefaultButton(QtWidgets.QMessageBox.No)

        result = confirm_dialog.exec_()

        if result == QtWidgets.QMessageBox.Yes:
            self.remove_friend(friend_name)

    def remove_friend(self, friend_name):
        """Удаляет друга из списка друзей и очищает историю запросов"""
        try:
            cursor = self.connection.cursor()

            # 1. Удаляем запись из таблицы friends
            cursor.execute(
                """
                DELETE FROM friends 
                WHERE (user1 = %s AND user2 = %s) OR (user1 = %s AND user2 = %s)
                """,
                (self.current_username, friend_name, friend_name, self.current_username)
            )

            # 2. Удаляем все запросы в друзья между этими пользователями
            cursor.execute(
                """
                DELETE FROM friend_requests 
                WHERE (sender = %s AND receiver = %s) OR (sender = %s AND receiver = %s)
                """,
                (self.current_username, friend_name, friend_name, self.current_username)
            )

            self.connection.commit()
            cursor.close()

            QtWidgets.QMessageBox.information(
                self,
                "Успех",
                f"Пользователь {friend_name} удален из списка друзей"
            )

            # Обновляем список друзей
            self.load_friends(self.search_input.text().strip())

            # Отправляем сигнал об обновлении списка друзей
            self.friendsUpdated.emit()

        except Exception as e:
            print(f"[ERROR] Failed to remove friend: {e}")
            self.connection.rollback()
            QtWidgets.QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось удалить друга: {str(e)}"
            )


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    connection = None

    dialog = FriendsDialog(connection, "TestUser")
    dialog.show()

    sys.exit(app.exec_())