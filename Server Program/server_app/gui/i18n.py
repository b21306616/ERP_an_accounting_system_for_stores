"""Small GUI localization layer for the server desktop app."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from server_app.core.network import PortCheckResult, PortCheckStatus, normalize_bind_host
from server_app.core.paths import get_config_dir


DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "ru", "tk")
PREFERENCES_FILE_NAME = "gui_preferences.json"


@dataclass(frozen=True)
class LanguageOption:
    """One selectable GUI language."""

    code: str
    label: str


LANGUAGE_OPTIONS = (
    LanguageOption("en", "English"),
    LanguageOption("ru", "Русский"),
    LanguageOption("tk", "Türkmençe"),
)


TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "app.title": "ERP Accounting Server",
        "language.label": "Language",
        "common.back": "Back",
        "common.next": "Next",
        "common.save": "Save",
        "common.cancel": "Cancel",
        "common.yes": "Yes",
        "common.no": "No",
        "common.not_set": "Not set",
        "common.saved_hidden": "Saved (hidden)",
        "common.configured_hidden": "Configured (hidden)",
        "common.unknown_field": "Unknown update field: {field_id}",
        "field.sql_server": "SQL Server host/instance",
        "field.database": "Database name",
        "field.odbc_driver": "ODBC driver",
        "field.authentication": "Authentication",
        "field.sql_username": "SQL username",
        "field.sql_password": "SQL password",
        "field.trust_certificate": "Trust SQL Server certificate",
        "field.bind_host": "Bind host/IP",
        "field.port": "Port",
        "field.username": "Username",
        "field.full_name": "Full name",
        "field.password": "Password",
        "field.current_password": "Current password",
        "field.new_password": "New password",
        "field.confirm_new_password": "Confirm new password",
        "auth.windows": "Windows Authentication",
        "auth.sql": "SQL Login",
        "section.mssql": "MSSQL connection",
        "section.api": "API server",
        "section.super_admin": "Super Admin account",
        "setup.window_title": "ERP Accounting Server - First Setup",
        "setup.subtitle": "First setup",
        "setup.card_title": "Setup",
        "setup.ready": "Ready to configure",
        "setup.failed": "Setup failed",
        "setup.working": "Working...",
        "setup.step_counter": "Step {current} of {total}",
        "setup.mssql_help": "Connect the server program to the Microsoft SQL Server database used by the ERP system.",
        "setup.api_help": "Choose where the FastAPI service will listen for client computers on the local network.",
        "setup.admin_help": "Set the fixed Super Admin password used to administer the whole ERP server.",
        "setup.port_hint": "If setup fails on this port, another program may already be using it. Try 5000 or 8080.",
        "setup.create": "Create database and start Windows service",
        "setup.creating": "Creating database, running migrations, and preparing Windows service...",
        "setup.db_ready": "Database is ready. Installing and starting Windows service...",
        "setup.invalid_title": "Invalid setup values",
        "setup.port_unavailable_title": "API port unavailable",
        "setup.required": "{field} is required.",
        "validation.database_name": "Database name is invalid: {message}",
        "validation.sql_username_required": "SQL username is required for SQL Login mode.",
        "validation.sql_password_required": "SQL password is required for SQL Login mode.",
        "validation.admin_password_length": "Super Admin password must contain at least 6 characters.",
        "validation.admin_password_match": "Super Admin password and confirmation do not match.",
        "validation.current_admin_required": "Current Super Admin password is required.",
        "validation.odbc_driver_required": "ODBC driver is required.",
        "validation.api_port_range": "API port must be between 1 and 65535.",
        "validation.page_ok": "Looks good.",
        "summary.window_title": "ERP Accounting Server - {state}",
        "summary.subtitle_starting": "Starting",
        "summary.subtitle_stopping": "Stopping",
        "summary.connection": "Connection",
        "summary.api_base_url": "API base URL",
        "summary.swagger_docs": "Swagger docs",
        "summary.copy": "Copy",
        "summary.copied": "Copied!",
        "summary.update_field": "Update this field",
        "summary.start_connection": "Start Connection",
        "summary.stop_connection": "Stop Connection",
        "summary.status.running": "Running",
        "summary.status.starting": "Starting...",
        "summary.status.stopping": "Stopping...",
        "summary.status.stopped": "Stopped",
        "summary.status.stopped_disabled": "Stopped (disabled)",
        "summary.status.needs_repair": "Stopped (service needs repair)",
        "summary.status.not_installed": "Not installed",
        "summary.status.error": "Error",
        "summary.update_invalid_title": "Invalid update",
        "summary.password_invalid_title": "Invalid password update",
        "summary.update_saved": "Configuration updated.",
        "summary.update_stopping": "Configuration updated. Stopping Windows service before restart...",
        "summary.update_stopped": "Update saved. Use Start Connection to run with the latest settings.",
        "summary.password_updating": "Updating Super Admin password...",
        "summary.password_updated": "Super Admin password updated.",
        "summary.password_stopping": "Super Admin password updated. Stopping Windows service before restart...",
        "summary.password_failed": "Super Admin password could not be updated: {message}",
        "summary.service_stop_failed_status": "Service stop failed: {message}",
        "summary.service_stop_failed": "Update was saved, but the Windows service could not be stopped. {message}",
        "dialog.update_sql_server": "Update SQL Server host/instance",
        "dialog.update_database": "Update database name",
        "dialog.update_driver": "Update ODBC driver",
        "dialog.update_auth": "Update authentication",
        "dialog.update_sql_username": "Update SQL username",
        "dialog.update_sql_password": "Update SQL password",
        "dialog.update_certificate": "Update certificate trust",
        "dialog.update_api_host": "Update API bind host/IP",
        "dialog.update_api_port": "Update API port",
        "dialog.update_admin_password": "Update Super Admin password",
        "dialog.sql_password_placeholder": "Leave blank to clear when Windows Authentication is used",
        "coordinator.load_config_failed": "Could not load saved config: {message}",
        "coordinator.port_no_longer_available": "Database is ready, but the API port is no longer available. {message}",
        "coordinator.config_save_failed": "Database is ready, but config could not be saved: {message}",
        "coordinator.config_save_failed_short": "Config could not be saved: {message}",
        "coordinator.saved_config_failed": "Saved configuration could not start: {message}",
        "coordinator.bind_failed_after_save": "Database and config were saved, but the API bind settings are not usable. {message} Choose a different local host/IP or port and run setup again.",
        "coordinator.api_failed_after_save": "Database and config were saved, but the API did not start. {message}",
        "coordinator.another_update_running": "Another database update is already running.",
        "coordinator.config_save_update_failed": "Configuration could not be saved: {message}",
        "port.available": "Port {port} is available on {host}.",
        "port.invalid_port": "API port must be between 1 and 65535.",
        "port.invalid_host": "API bind host '{host}' is not a valid host name or IP address.",
        "port.host_not_local": "Windows cannot bind the API to {host}:{port} because that address is not assigned to this PC. Use 0.0.0.0, 127.0.0.1, or a local network IP.",
        "port.in_use": "Port {port} is already in use on {host}. Close the other program or choose a different port, such as 5000 or 8080.",
        "port.access_denied": "Windows denied access to port {port} on {host}. The port may be reserved by Windows, blocked by policy, or owned by a protected listener. Choose a different port, such as 5000 or 8080.",
        "port.unknown": "Windows could not verify port {port} on {host}.{detail} Choose a different port or check the host/IP value.",
        "port.last_error": " Last error: {error}.",
        "port.diagnostic": "To diagnose: netstat -ano | findstr :{port}",
    },
    "ru": {
        "app.title": "ERP Accounting Server",
        "language.label": "Язык",
        "common.back": "Назад",
        "common.next": "Далее",
        "common.save": "Сохранить",
        "common.cancel": "Отмена",
        "common.yes": "Да",
        "common.no": "Нет",
        "common.not_set": "Не задано",
        "common.saved_hidden": "Сохранено (скрыто)",
        "common.configured_hidden": "Настроено (скрыто)",
        "common.unknown_field": "Неизвестное поле обновления: {field_id}",
        "field.sql_server": "Хост/экземпляр SQL Server",
        "field.database": "Имя базы данных",
        "field.odbc_driver": "ODBC-драйвер",
        "field.authentication": "Аутентификация",
        "field.sql_username": "Пользователь SQL",
        "field.sql_password": "Пароль SQL",
        "field.trust_certificate": "Доверять сертификату SQL Server",
        "field.bind_host": "Хост/IP привязки",
        "field.port": "Порт",
        "field.username": "Имя пользователя",
        "field.full_name": "Полное имя",
        "field.password": "Пароль",
        "field.current_password": "Текущий пароль",
        "field.new_password": "Новый пароль",
        "field.confirm_new_password": "Подтвердите новый пароль",
        "auth.windows": "Аутентификация Windows",
        "auth.sql": "SQL-логин",
        "section.mssql": "Подключение MSSQL",
        "section.api": "API-сервер",
        "section.super_admin": "Учетная запись Super Admin",
        "setup.window_title": "ERP Accounting Server - первая настройка",
        "setup.subtitle": "Первая настройка",
        "setup.card_title": "Настройка",
        "setup.ready": "Готово к настройке",
        "setup.failed": "Настройка не удалась",
        "setup.working": "Выполняется...",
        "setup.step_counter": "Шаг {current} из {total}",
        "setup.mssql_help": "Подключите серверную программу к базе Microsoft SQL Server, используемой ERP-системой.",
        "setup.api_help": "Выберите, где FastAPI-сервис будет принимать подключения клиентских компьютеров в локальной сети.",
        "setup.admin_help": "Задайте фиксированный пароль Super Admin для администрирования всего ERP-сервера.",
        "setup.port_hint": "Если настройка не пройдет на этом порту, возможно, его уже использует другая программа. Попробуйте 5000 или 8080.",
        "setup.create": "Создать базу данных и запустить службу Windows",
        "setup.creating": "Создание базы данных, выполнение миграций и подготовка службы Windows...",
        "setup.db_ready": "База данных готова. Установка и запуск службы Windows...",
        "setup.invalid_title": "Некорректные значения настройки",
        "setup.port_unavailable_title": "API-порт недоступен",
        "setup.required": "Поле «{field}» обязательно.",
        "validation.database_name": "Некорректное имя базы данных: {message}",
        "validation.sql_username_required": "Для режима SQL-логина требуется пользователь SQL.",
        "validation.sql_password_required": "Для режима SQL-логина требуется пароль SQL.",
        "validation.admin_password_length": "Пароль Super Admin должен содержать минимум 6 символов.",
        "validation.admin_password_match": "Пароль Super Admin и подтверждение не совпадают.",
        "validation.current_admin_required": "Текущий пароль Super Admin обязателен.",
        "validation.odbc_driver_required": "ODBC-драйвер обязателен.",
        "validation.api_port_range": "API-порт должен быть от 1 до 65535.",
        "validation.page_ok": "Все в порядке.",
        "summary.window_title": "ERP Accounting Server - {state}",
        "summary.subtitle_starting": "Запуск",
        "summary.subtitle_stopping": "Остановка",
        "summary.connection": "Подключение",
        "summary.api_base_url": "Базовый URL API",
        "summary.swagger_docs": "Документация Swagger",
        "summary.copy": "Копировать",
        "summary.copied": "Скопировано!",
        "summary.update_field": "Изменить поле",
        "summary.start_connection": "Запустить подключение",
        "summary.stop_connection": "Остановить подключение",
        "summary.status.running": "Работает",
        "summary.status.starting": "Запускается...",
        "summary.status.stopping": "Останавливается...",
        "summary.status.stopped": "Остановлено",
        "summary.status.stopped_disabled": "Остановлено (отключено)",
        "summary.status.needs_repair": "Остановлено (служба требует восстановления)",
        "summary.status.not_installed": "Не установлена",
        "summary.status.error": "Ошибка",
        "summary.update_invalid_title": "Некорректное обновление",
        "summary.password_invalid_title": "Некорректное обновление пароля",
        "summary.update_saved": "Конфигурация обновлена.",
        "summary.update_stopping": "Конфигурация обновлена. Остановка службы Windows перед перезапуском...",
        "summary.update_stopped": "Обновление сохранено. Используйте «Запустить подключение», чтобы применить новые настройки.",
        "summary.password_updating": "Обновление пароля Super Admin...",
        "summary.password_updated": "Пароль Super Admin обновлен.",
        "summary.password_stopping": "Пароль Super Admin обновлен. Остановка службы Windows перед перезапуском...",
        "summary.password_failed": "Не удалось обновить пароль Super Admin: {message}",
        "summary.service_stop_failed_status": "Не удалось остановить службу: {message}",
        "summary.service_stop_failed": "Обновление сохранено, но службу Windows не удалось остановить. {message}",
        "dialog.update_sql_server": "Изменить хост/экземпляр SQL Server",
        "dialog.update_database": "Изменить имя базы данных",
        "dialog.update_driver": "Изменить ODBC-драйвер",
        "dialog.update_auth": "Изменить аутентификацию",
        "dialog.update_sql_username": "Изменить пользователя SQL",
        "dialog.update_sql_password": "Изменить пароль SQL",
        "dialog.update_certificate": "Изменить доверие сертификату",
        "dialog.update_api_host": "Изменить хост/IP API",
        "dialog.update_api_port": "Изменить API-порт",
        "dialog.update_admin_password": "Изменить пароль Super Admin",
        "dialog.sql_password_placeholder": "Оставьте пустым, чтобы очистить при аутентификации Windows",
        "coordinator.load_config_failed": "Не удалось загрузить сохраненную конфигурацию: {message}",
        "coordinator.port_no_longer_available": "База данных готова, но API-порт больше недоступен. {message}",
        "coordinator.config_save_failed": "База данных готова, но конфигурацию не удалось сохранить: {message}",
        "coordinator.config_save_failed_short": "Не удалось сохранить конфигурацию: {message}",
        "coordinator.saved_config_failed": "Сохраненная конфигурация не запустилась: {message}",
        "coordinator.bind_failed_after_save": "База данных и конфигурация сохранены, но параметры привязки API непригодны. {message} Выберите другой локальный хост/IP или порт и повторите настройку.",
        "coordinator.api_failed_after_save": "База данных и конфигурация сохранены, но API не запустился. {message}",
        "coordinator.another_update_running": "Уже выполняется другое обновление базы данных.",
        "coordinator.config_save_update_failed": "Не удалось сохранить конфигурацию: {message}",
        "port.available": "Порт {port} доступен на {host}.",
        "port.invalid_port": "API-порт должен быть от 1 до 65535.",
        "port.invalid_host": "Хост привязки API «{host}» не является допустимым именем хоста или IP-адресом.",
        "port.host_not_local": "Windows не может привязать API к {host}:{port}, потому что этот адрес не назначен этому ПК. Используйте 0.0.0.0, 127.0.0.1 или локальный сетевой IP.",
        "port.in_use": "Порт {port} уже используется на {host}. Закройте другую программу или выберите другой порт, например 5000 или 8080.",
        "port.access_denied": "Windows запретила доступ к порту {port} на {host}. Порт может быть зарезервирован Windows, заблокирован политикой или занят защищенным слушателем. Выберите другой порт, например 5000 или 8080.",
        "port.unknown": "Windows не смогла проверить порт {port} на {host}.{detail} Выберите другой порт или проверьте хост/IP.",
        "port.last_error": " Последняя ошибка: {error}.",
        "port.diagnostic": "Диагностика: netstat -ano | findstr :{port}",
    },
    "tk": {
        "app.title": "ERP Accounting Server",
        "language.label": "Dil",
        "common.back": "Yza",
        "common.next": "Indiki",
        "common.save": "Ýatda sakla",
        "common.cancel": "Ýatyr",
        "common.yes": "Hawa",
        "common.no": "Ýok",
        "common.not_set": "Bellenmedi",
        "common.saved_hidden": "Ýatda saklanan (gizlin)",
        "common.configured_hidden": "Sazlanan (gizlin)",
        "common.unknown_field": "Näbelli täzelenýän meýdan: {field_id}",
        "field.sql_server": "SQL Server hosty/instansy",
        "field.database": "Maglumat bazasynyň ady",
        "field.odbc_driver": "ODBC draýweri",
        "field.authentication": "Autentifikasiýa",
        "field.sql_username": "SQL ulanyjysy",
        "field.sql_password": "SQL paroly",
        "field.trust_certificate": "SQL Server sertifikatyna ynan",
        "field.bind_host": "Baglanjak host/IP",
        "field.port": "Port",
        "field.username": "Ulanyjy ady",
        "field.full_name": "Doly ady",
        "field.password": "Parol",
        "field.current_password": "Häzirki parol",
        "field.new_password": "Täze parol",
        "field.confirm_new_password": "Täze paroly tassykla",
        "auth.windows": "Windows autentifikasiýasy",
        "auth.sql": "SQL login",
        "section.mssql": "MSSQL birikmesi",
        "section.api": "API serweri",
        "section.super_admin": "Super Admin hasaby",
        "setup.window_title": "ERP Accounting Server - ilkinji sazlama",
        "setup.subtitle": "Ilkinji sazlama",
        "setup.card_title": "Sazlama",
        "setup.ready": "Sazlamaga taýýar",
        "setup.failed": "Sazlama başa barmady",
        "setup.working": "Işlenýär...",
        "setup.step_counter": "{total} ädimden {current}-nji",
        "setup.mssql_help": "Serwer programmasyny ERP ulgamynyň ulanýan Microsoft SQL Server maglumat bazasyna birikdiriň.",
        "setup.api_help": "FastAPI hyzmatynyň ýerli tordaky müşderi kompýuterlerinden nirä birikmeleri kabul etjegini saýlaň.",
        "setup.admin_help": "ERP serwerini dolandyrmak üçin hemişelik Super Admin parolyny belläň.",
        "setup.port_hint": "Bu portda sazlama başa barmasa, ony başga programma ulanýan bolmagy mümkin. 5000 ýa-da 8080 synap görüň.",
        "setup.create": "Maglumat bazasyny döret we Windows hyzmatyny başlat",
        "setup.creating": "Maglumat bazasy döredilýär, migrasiýalar ýerine ýetirilýär we Windows hyzmaty taýýarlanýar...",
        "setup.db_ready": "Maglumat bazasy taýýar. Windows hyzmaty gurulýar we başladylýar...",
        "setup.invalid_title": "Sazlama bahalary nädogry",
        "setup.port_unavailable_title": "API porty elýeterli däl",
        "setup.required": "{field} hökmany.",
        "validation.database_name": "Maglumat bazasynyň ady nädogry: {message}",
        "validation.sql_username_required": "SQL login režimi üçin SQL ulanyjysy hökmany.",
        "validation.sql_password_required": "SQL login režimi üçin SQL paroly hökmany.",
        "validation.admin_password_length": "Super Admin paroly azyndan 6 nyşandan ybarat bolmaly.",
        "validation.admin_password_match": "Super Admin paroly we tassyklama gabat gelenok.",
        "validation.current_admin_required": "Häzirki Super Admin paroly hökmany.",
        "validation.odbc_driver_required": "ODBC draýweri hökmany.",
        "validation.api_port_range": "API porty 1 bilen 65535 aralygynda bolmaly.",
        "validation.page_ok": "Hemmesi dogry.",
        "summary.window_title": "ERP Accounting Server - {state}",
        "summary.subtitle_starting": "Başladylýar",
        "summary.subtitle_stopping": "Durdurylýar",
        "summary.connection": "Birikme",
        "summary.api_base_url": "API esasy URL",
        "summary.swagger_docs": "Swagger dokumentasiýasy",
        "summary.copy": "Göçür",
        "summary.copied": "Göçürildi!",
        "summary.update_field": "Meýdany üýtget",
        "summary.start_connection": "Birikmäni başlat",
        "summary.stop_connection": "Birikmäni duruz",
        "summary.status.running": "Işleýär",
        "summary.status.starting": "Başladylýar...",
        "summary.status.stopping": "Durdurylýar...",
        "summary.status.stopped": "Durduryldy",
        "summary.status.stopped_disabled": "Durduryldy (öçürilen)",
        "summary.status.needs_repair": "Durduryldy (hyzmaty abatlamaly)",
        "summary.status.not_installed": "Gurulmady",
        "summary.status.error": "Ýalňyşlyk",
        "summary.update_invalid_title": "Täzelenme nädogry",
        "summary.password_invalid_title": "Parol täzelenmesi nädogry",
        "summary.update_saved": "Konfigurasiýa täzelendi.",
        "summary.update_stopping": "Konfigurasiýa täzelendi. Täzeden başlamazdan öň Windows hyzmaty duruzylýar...",
        "summary.update_stopped": "Täzelenme ýatda saklandy. Täze sazlamalar bilen işletmek üçin Birikmäni başlat düwmesini ulanyň.",
        "summary.password_updating": "Super Admin paroly täzelenýär...",
        "summary.password_updated": "Super Admin paroly täzelendi.",
        "summary.password_stopping": "Super Admin paroly täzelendi. Täzeden başlamazdan öň Windows hyzmaty duruzylýar...",
        "summary.password_failed": "Super Admin parolyny täzeläp bolmady: {message}",
        "summary.service_stop_failed_status": "Hyzmaty duruzyp bolmady: {message}",
        "summary.service_stop_failed": "Täzelenme ýatda saklandy, ýöne Windows hyzmatyny duruzyp bolmady. {message}",
        "dialog.update_sql_server": "SQL Server hostuny/instansyny üýtget",
        "dialog.update_database": "Maglumat bazasynyň adyny üýtget",
        "dialog.update_driver": "ODBC draýwerini üýtget",
        "dialog.update_auth": "Autentifikasiýany üýtget",
        "dialog.update_sql_username": "SQL ulanyjysyny üýtget",
        "dialog.update_sql_password": "SQL parolyny üýtget",
        "dialog.update_certificate": "Sertifikata ynamy üýtget",
        "dialog.update_api_host": "API host/IP üýtget",
        "dialog.update_api_port": "API portuny üýtget",
        "dialog.update_admin_password": "Super Admin parolyny üýtget",
        "dialog.sql_password_placeholder": "Windows autentifikasiýasynda arassalamak üçin boş goýuň",
        "coordinator.load_config_failed": "Ýatda saklanan konfigurasiýany ýükläp bolmady: {message}",
        "coordinator.port_no_longer_available": "Maglumat bazasy taýýar, ýöne API porty indi elýeterli däl. {message}",
        "coordinator.config_save_failed": "Maglumat bazasy taýýar, ýöne konfigurasiýany ýatda saklap bolmady: {message}",
        "coordinator.config_save_failed_short": "Konfigurasiýany ýatda saklap bolmady: {message}",
        "coordinator.saved_config_failed": "Ýatda saklanan konfigurasiýa başlamady: {message}",
        "coordinator.bind_failed_after_save": "Maglumat bazasy we konfigurasiýa ýatda saklandy, ýöne API baglanyş sazlamalary ulanyp bolmaýar. {message} Başga ýerli host/IP ýa-da port saýlap, sazlamany gaýtadan işlediň.",
        "coordinator.api_failed_after_save": "Maglumat bazasy we konfigurasiýa ýatda saklandy, ýöne API başlamady. {message}",
        "coordinator.another_update_running": "Başga maglumat bazasy täzelenmesi eýýäm işleýär.",
        "coordinator.config_save_update_failed": "Konfigurasiýany ýatda saklap bolmady: {message}",
        "port.available": "{host} üstünde {port} porty elýeterli.",
        "port.invalid_port": "API porty 1 bilen 65535 aralygynda bolmaly.",
        "port.invalid_host": "API baglanyş hosty '{host}' dogry host ady ýa-da IP salgy däl.",
        "port.host_not_local": "Windows API-ni {host}:{port} salgysyna baglap bilmeýär, sebäbi bu salgy şu PK-a degişli däl. 0.0.0.0, 127.0.0.1 ýa-da ýerli tor IP-sini ulanyň.",
        "port.in_use": "{host} üstünde {port} porty eýýäm ulanylýar. Başga programmany ýapyň ýa-da 5000 ýa-da 8080 ýaly başga port saýlaň.",
        "port.access_denied": "Windows {host} üstünde {port} portuna rugsat bermedi. Port Windows tarapyndan rezerwlenen, syýasat bilen bloklanan ýa-da goralan diňleýji tarapyndan eýelenen bolup biler. 5000 ýa-da 8080 ýaly başga port saýlaň.",
        "port.unknown": "Windows {host} üstünde {port} portuny barlap bilmedi.{detail} Başga port saýlaň ýa-da host/IP bahasyny barlaň.",
        "port.last_error": " Soňky ýalňyşlyk: {error}.",
        "port.diagnostic": "Diagnostika: netstat -ano | findstr :{port}",
    },
}


def get_gui_preferences_path():
    """Return the JSON file that stores GUI-only preferences."""

    return get_config_dir() / PREFERENCES_FILE_NAME


def normalize_language(language: str | None) -> str:
    """Return a supported language code, falling back to English."""

    if language in SUPPORTED_LANGUAGES:
        return str(language)
    return DEFAULT_LANGUAGE


def load_language_preference() -> str:
    """Load the saved language preference, falling back to English."""

    path = get_gui_preferences_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_LANGUAGE
    return normalize_language(data.get("language"))


def save_language_preference(language: str) -> None:
    """Persist the selected GUI language."""

    path = get_gui_preferences_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {"language": normalize_language(language)}
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)
    except OSError:
        return


_current_language = load_language_preference()


def get_language() -> str:
    """Return the active GUI language code."""

    return _current_language


def set_language(language: str, *, persist: bool = True) -> str:
    """Set the active GUI language and optionally save it."""

    global _current_language
    _current_language = normalize_language(language)
    if persist:
        save_language_preference(_current_language)
    return _current_language


def tr(key: str, **values: object) -> str:
    """Translate a key using the active language."""

    table = TRANSLATIONS.get(_current_language, TRANSLATIONS[DEFAULT_LANGUAGE])
    text = table.get(key, TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key))
    if values:
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            return text
    return text


def _display_bind_host(host: str) -> str:
    return normalize_bind_host(host) or "0.0.0.0"


def format_port_check_message(result: PortCheckResult, *, include_diagnostic: bool = False) -> str:
    """Return a localized user-facing message for a port check result."""

    host = _display_bind_host(result.host)
    port = result.port
    if result.status == PortCheckStatus.AVAILABLE:
        message = tr("port.available", host=host, port=port)
    elif result.status == PortCheckStatus.INVALID_PORT:
        message = tr("port.invalid_port")
    elif result.status == PortCheckStatus.INVALID_HOST:
        message = tr("port.invalid_host", host=result.host)
    elif result.status == PortCheckStatus.HOST_NOT_LOCAL:
        message = tr("port.host_not_local", host=host, port=port)
    elif result.status == PortCheckStatus.IN_USE:
        message = tr("port.in_use", host=host, port=port)
    elif result.status == PortCheckStatus.ACCESS_DENIED_OR_RESERVED:
        message = tr("port.access_denied", host=host, port=port)
    else:
        detail = tr("port.last_error", error=result.error) if result.error else ""
        message = tr("port.unknown", host=host, port=port, detail=detail)

    if include_diagnostic and result.status in {
        PortCheckStatus.IN_USE,
        PortCheckStatus.ACCESS_DENIED_OR_RESERVED,
    }:
        return f"{message} {tr('port.diagnostic', port=port)}"
    if include_diagnostic and result.diagnostic:
        return f"{message} {result.diagnostic}"
    return message
