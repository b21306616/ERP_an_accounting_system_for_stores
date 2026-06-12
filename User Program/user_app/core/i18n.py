"""Runtime Russian/Turkmen translations for the endpoint client."""

from __future__ import annotations

from dataclasses import dataclass

from user_app.core.config import LanguageCode


TRANSLATIONS: dict[LanguageCode, dict[str, str]] = {
    "ru": {
        "app.title": "ERP учетная система",
        "login.title": "Вход в систему",
        "login.server": "Адрес сервера",
        "login.username": "Пользователь",
        "login.password": "Пароль",
        "login.language": "Язык",
        "login.submit": "Войти",
        "login.status.ready": "Введите адрес сервера и учетные данные.",
        "login.status.connecting": "Подключение к серверу...",
        "login.status.failed": "Вход не выполнен",
        "main.logout": "Выйти",
        "main.connected": "Подключено",
        "nav.dashboard": "Дашборд",
        "nav.users": "Пользователи",
        "nav.roles": "Роли и права",
        "nav.settings": "Настройки",
        "nav.hardware": "Оборудование",
        "nav.catalog": "Товары",
        "nav.warehouse": "Склад",
        "nav.purchase": "Закупки",
        "nav.pricing": "Цены",
        "nav.sales": "Продажи",
        "nav.cashier": "Касса",
        "nav.reports": "Отчеты",
        "dashboard.title": "Состояние сервера",
        "dashboard.refresh": "Обновить",
        "dashboard.server_time": "Время сервера",
        "dashboard.current_user": "Текущий пользователь",
        "dashboard.permissions": "Права",
        "users.title": "Пользователи",
        "users.refresh": "Обновить",
        "users.create": "Создать пользователя",
        "roles.title": "Роли и права",
        "settings.title": "Настройки организации",
        "settings.save": "Сохранить",
        "hardware.title": "Симулятор оборудования",
        "hardware.scan": "Сканировать штрихкод",
        "hardware.print": "Печать чека",
        "hardware.drawer": "Открыть ящик",
        "hardware.scale": "Весы",
        "hardware.fiscal": "Фискальная операция",
        "placeholder.title": "Модуль будет добавлен следующим слоем",
        "placeholder.body": "Серверная логика для этого раздела еще не реализована.",
        "common.error": "Ошибка",
        "common.success": "Готово",
    },
    "tk": {
        "app.title": "ERP hasap ulgamy",
        "login.title": "Ulgama giriş",
        "login.server": "Serwer salgysy",
        "login.username": "Ulanyjy",
        "login.password": "Açar söz",
        "login.language": "Dil",
        "login.submit": "Girmek",
        "login.status.ready": "Serwer salgysyny we ulanyjy maglumatlaryny giriziň.",
        "login.status.connecting": "Serwere birikdirilýär...",
        "login.status.failed": "Giriş ýerine ýetmedi",
        "main.logout": "Çykmak",
        "main.connected": "Birikdirildi",
        "nav.dashboard": "Dolandyryş paneli",
        "nav.users": "Ulanyjylar",
        "nav.roles": "Rollar we hukuklar",
        "nav.settings": "Sazlamalar",
        "nav.hardware": "Enjamlar",
        "nav.catalog": "Harytlar",
        "nav.warehouse": "Ammar",
        "nav.purchase": "Satyn alyş",
        "nav.pricing": "Bahalar",
        "nav.sales": "Satuwlar",
        "nav.cashier": "Kassa",
        "nav.reports": "Hasabatlar",
        "dashboard.title": "Serwer ýagdaýy",
        "dashboard.refresh": "Täzelemek",
        "dashboard.server_time": "Serwer wagty",
        "dashboard.current_user": "Häzirki ulanyjy",
        "dashboard.permissions": "Hukuklar",
        "users.title": "Ulanyjylar",
        "users.refresh": "Täzelemek",
        "users.create": "Ulanyjy döretmek",
        "roles.title": "Rollar we hukuklar",
        "settings.title": "Gurama sazlamalary",
        "settings.save": "Ýatda saklamak",
        "hardware.title": "Enjam simulýatory",
        "hardware.scan": "Ştrih-kody skanirlemek",
        "hardware.print": "Çegi çap etmek",
        "hardware.drawer": "Guty açmak",
        "hardware.scale": "Tereziler",
        "hardware.fiscal": "Fiskal amal",
        "placeholder.title": "Modul indiki gatlakda goşular",
        "placeholder.body": "Bu bölüm üçin serwer logikasy entek ýerine ýetirilmedi.",
        "common.error": "Ýalňyşlyk",
        "common.success": "Taýýar",
    },
}


@dataclass(slots=True)
class Translator:
    """Small runtime translator for UI labels."""

    language: LanguageCode = "ru"

    def set_language(self, language: LanguageCode) -> None:
        """Switch the active language."""

        if language in TRANSLATIONS:
            self.language = language

    def text(self, key: str) -> str:
        """Return a translated label, falling back to the key itself."""

        return TRANSLATIONS.get(self.language, TRANSLATIONS["ru"]).get(key, key)
