import sys
from PyQt5 import QtWidgets, QtCore, QtGui
import pg8000
import bcrypt
from client import ChatClient, ChatWindow

# Настройки подключения к базе данных
DB_CONFIG = {
    "user": "postgres",
    "password": "12345",
    "database": "postgres",
    "host": "127.0.0.1",
    "port": 5432
}

SERVER_HOST = "127.0.0.1"  # Адрес сервера чата
SERVER_PORT = 5555  # Порт сервера чата


class AuthWindow(QtWidgets.QWidget):
    def __init__(self, connection):
        super().__init__()
        self.connection = connection
        self.setWindowTitle("Chat App")
        self.resize(400, 500)

        # Основной стек виджетов для переключения между экранами
        self.stacked_widget = QtWidgets.QStackedWidget(self)

        # Экраны входа и регистрации
        self.login_screen = self.create_login_screen()
        self.register_screen = self.create_register_screen()

        # Экраны в стек
        self.stacked_widget.addWidget(self.login_screen)
        self.stacked_widget.addWidget(self.register_screen)

        # Устанавливаем экран входа как начальный
        self.stacked_widget.setCurrentIndex(0)

        # Основной макет
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.stacked_widget)

        self.setLayout(main_layout)

    def create_login_screen(self):
        """Создание экрана входа"""
        login_widget = QtWidgets.QWidget()
        login_layout = QtWidgets.QVBoxLayout(login_widget)
        login_layout.setContentsMargins(0, 0, 0, 0)
        login_layout.setSpacing(0)

        # Основное содержимое
        content = QtWidgets.QWidget()
        content.setStyleSheet("""
            background-color: #d9d9d9;
            border-radius: 10px;
        """)
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.setSpacing(15)

        # Логотип
        logo_label = QtWidgets.QLabel()
        logo_pixmap = QtGui.QPixmap("logo\logo.png")
        if logo_pixmap.isNull():
            print("Ошибка: не удалось загрузить логотип")
        else:
            logo_pixmap = logo_pixmap.scaled(64, 64, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)
        logo_label.setStyleSheet("background-color: transparent;")
        logo_label.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.addWidget(logo_label)
        content_layout.addSpacing(20)

        # Поля ввода
        self.login_username = QtWidgets.QLineEdit()
        self.login_username.setPlaceholderText("Login")
        self.login_username.setStyleSheet("""
            background-color: white;
            border: none;
            border-radius: 5px;
            padding: 8px;
            font-size: 14px;
            min-height: 20px;
            max-width: 200px;
        """)
        content_layout.addWidget(self.login_username, 0, QtCore.Qt.AlignCenter)

        self.login_password = QtWidgets.QLineEdit()
        self.login_password.setPlaceholderText("Password")
        self.login_password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.login_password.setStyleSheet("""
            background-color: white;
            border: none;
            border-radius: 5px;
            padding: 8px;
            font-size: 14px;
            min-height: 20px;
            max-width: 200px;
        """)
        content_layout.addWidget(self.login_password, 0, QtCore.Qt.AlignCenter)

        content_layout.addSpacing(20)

        # Кнопки
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.setAlignment(QtCore.Qt.AlignCenter)

        login_btn = QtWidgets.QPushButton("Login")
        login_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999999;
            border-radius: 10px;
            padding: 5px 15px;
            font-size: 14px;
            min-width: 80px;
        """)
        login_btn.clicked.connect(self.handle_login)
        buttons_layout.addWidget(login_btn)

        register_btn = QtWidgets.QPushButton("Register")
        register_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999999;
            border-radius: 10px;
            padding: 5px 15px;
            font-size: 14px;
            min-width: 80px;
        """)
        register_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        buttons_layout.addWidget(register_btn)

        content_layout.addLayout(buttons_layout)
        content_layout.addSpacing(30)

        # Добавляем содержимое в основной макет
        login_layout.addWidget(content)

        return login_widget

    def create_register_screen(self):
        """Создание экрана регистрации"""
        register_widget = QtWidgets.QWidget()
        register_layout = QtWidgets.QVBoxLayout(register_widget)
        register_layout.setContentsMargins(0, 0, 0, 0)
        register_layout.setSpacing(0)

        # Основное содержимое
        content = QtWidgets.QWidget()
        content.setStyleSheet("""
            background-color: #d9d9d9;
            border-radius: 10px;
        """)
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.setSpacing(15)

        # Логотип
        logo_label = QtWidgets.QLabel()
        logo_pixmap = QtGui.QPixmap("logo\logo.png")
        if logo_pixmap.isNull():
            print("Ошибка: не удалось загрузить логотип")
        else:
            logo_pixmap = logo_pixmap.scaled(64, 64, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)
        logo_label.setStyleSheet("background-color: transparent;")
        logo_label.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.addWidget(logo_label)
        content_layout.addSpacing(20)


        self.register_username = QtWidgets.QLineEdit()
        self.register_username.setPlaceholderText("Nickname")
        self.register_username.setStyleSheet("""
            background-color: white;
            border: none;
            border-radius: 5px;
            padding: 8px;
            font-size: 14px;
            min-height: 20px;
            max-width: 200px;
        """)
        content_layout.addWidget(self.register_username, 0, QtCore.Qt.AlignCenter)

        self.register_password = QtWidgets.QLineEdit()
        self.register_password.setPlaceholderText("Password")
        self.register_password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.register_password.setStyleSheet("""
            background-color: white;
            border: none;
            border-radius: 5px;
            padding: 8px;
            font-size: 14px;
            min-height: 20px;
            max-width: 200px;
        """)
        content_layout.addWidget(self.register_password, 0, QtCore.Qt.AlignCenter)

        self.register_email = QtWidgets.QLineEdit()
        self.register_email.setPlaceholderText("E-mail")
        self.register_email.setStyleSheet("""
            background-color: white;
            border: none;
            border-radius: 5px;
            padding: 8px;
            font-size: 14px;
            min-height: 20px;
            max-width: 200px;
        """)
        content_layout.addWidget(self.register_email, 0, QtCore.Qt.AlignCenter)

        content_layout.addSpacing(20)

        # Кнопки
        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.setAlignment(QtCore.Qt.AlignCenter)

        register_btn = QtWidgets.QPushButton("Register")
        register_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999999;
            border-radius: 10px;
            padding: 5px 15px;
            font-size: 14px;
            min-width: 80px;
        """)
        register_btn.clicked.connect(self.handle_registration)
        buttons_layout.addWidget(register_btn)

        back_btn = QtWidgets.QPushButton("Back")
        back_btn.setStyleSheet("""
            background-color: #d0d0d0;
            border: 1px solid #999999;
            border-radius: 10px;
            padding: 5px 15px;
            font-size: 14px;
            min-width: 80px;
        """)
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        buttons_layout.addWidget(back_btn)

        content_layout.addLayout(buttons_layout)
        content_layout.addSpacing(30)

        # Добавляем содержимое в основной макет
        register_layout.addWidget(content)

        return register_widget

    def open_chat_window(self, username):
        """Открытие окна чата с передачей логина"""
        self.close()  # Закрываем текущее окно
        chat_client = ChatClient(SERVER_HOST, SERVER_PORT)  # Создаём клиент для чата
        self.chat_window = ChatWindow(chat_client, username, self.connection)  # Передаём логин и соединение с БД
        self.chat_window.show()

    def handle_login(self):
        """Обработка входа пользователя"""
        username = self.login_username.text()
        password = self.login_password.text()

        if not username or not password:
            self.show_error_message("Please fill in all fields.")
            return

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT password FROM users WHERE username = %s", (username,))
            result = cursor.fetchone()

            if result:
                stored_hashed_password = result[0]
                if bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password.encode('utf-8')):
                    self.open_chat_window(username)  # Передаем логин в окно чата
                else:
                    self.show_error_message("Invalid username or password.")
            else:
                self.show_error_message("Invalid username or password.")
        except Exception as e:
            self.show_error_message(f"Database error: {str(e)}")
        finally:
            cursor.close()

    def handle_registration(self):
        """Обработка регистрации пользователя"""
        username = self.register_username.text()
        password = self.register_password.text()
        email = self.register_email.text()

        if not username or not password:
            self.show_error_message("Username and password are required.")
            return

        try:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            cursor = self.connection.cursor()
            # Проверяем, существует ли таблица с полем email
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'email'
            """)
            has_email_column = cursor.fetchone() is not None

            if has_email_column:
                cursor.execute(
                    "INSERT INTO users (username, password, email) VALUES (%s, %s, %s)",
                    (username, hashed_password, email)
                )
            else:
                cursor.execute(
                    "INSERT INTO users (username, password) VALUES (%s, %s)",
                    (username, hashed_password)
                )

            self.connection.commit()
            self.open_chat_window(username)  # Передаем логин в окно чата
        except pg8000.errors.IntegrityError:
            self.connection.rollback()
            self.show_error_message("Username already exists.")
        except Exception as e:
            self.connection.rollback()
            self.show_error_message(f"Database error: {str(e)}")
        finally:
            cursor.close()

    def show_error_message(self, message):
        """Отображение сообщения об ошибке"""
        error_box = QtWidgets.QMessageBox(self)
        error_box.setIcon(QtWidgets.QMessageBox.Warning)
        error_box.setWindowTitle("Error")
        error_box.setText(message)
        error_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        error_box.exec_()


def main():
    """Основная функция запуска"""
    app = QtWidgets.QApplication(sys.argv)

    try:
        # Подключение к базе данных
        connection = pg8000.connect(**DB_CONFIG)

        # Создание окна аутентификации
        window = AuthWindow(connection)
        window.show()

        # Запуск приложение
        sys.exit(app.exec_())
    finally:
        connection.close()  # Закрываем соединение с базой данных при завершении


if __name__ == "__main__":
    main()
