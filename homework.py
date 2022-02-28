import logging
import os
import sys
import time
from http import HTTPStatus
from typing import Any, Dict, List

import requests
import telegram
from dotenv import load_dotenv

import settings
from exceptions import ApiError

load_dotenv()

PRACTICUM_TOKEN: str = os.getenv(
    "PRACTICUM_TOKEN", default="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
TELEGRAM_TOKEN: str = os.getenv(
    "TELEGRAM_TOKEN", default="1111111111:AAAAAAAAAAAAAAAAAAAAAAAAAAA-AAAAAAA"
)
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", default="11111111")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.DEBUG,
)

logger = logging.getLogger(__name__)
logger_handler = logging.StreamHandler()
logger_handler.setStream(sys.stdout)
logger.addHandler(logger_handler)

telegram_bot = telegram.Bot(token=TELEGRAM_TOKEN)


def send_message(bot: telegram.Bot, message: str):
    """
    Отправляет сообщение в Telegram чат.

    Определяемый переменной окружения TELEGRAM_CHAT_ID.
    Принимает на вход два параметра: экземпляр класса Bot
    и строку с текстом сообщения.
    """
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except telegram.error.TelegramError:
        logging.error(f"Бот не смог отправить сообщение: {message}")
    else:
        logging.info(f"Бот отправил сообщение: {message}")


def get_api_answer(current_timestamp: int) -> Dict:
    """
    Делает запрос к единственному эндпоинту API-сервиса.

    В качестве параметра функция получает временную метку.
    В случае успешного запроса должна вернуть ответ API,
    преобразовав его из формата JSON к типам данных Python.
    """
    timestamp = current_timestamp or int(time.time())
    params = {"from_date": timestamp}

    try:
        response = requests.get(
            url=settings.ENDPOINT,
            params=params,
            headers={"Authorization": f"OAuth {PRACTICUM_TOKEN}"},
        )

        if response.status_code != HTTPStatus.OK:
            raise ApiError(
                f"Эндпоинт {settings.ENDPOINT} недоступен. "
                f"Код ответа API: {response.status_code}"
            )
    except requests.exceptions.RequestException as error:
        raise ApiError(f"Сбой запроса эндпоинта {settings.ENDPOINT} - {error}")
    else:
        try:
            return response.json()
        except ValueError:
            raise ApiError("Ошибка в формате JSON.")


def check_response(response: Dict) -> List[Dict]:
    """
    Проверяет ответ API на корректность.

    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python. Если ответ API соответствует ожиданиям,
    то функция должна вернуть список домашних работ (он может быть и пустым),
    доступный в ответе API по ключу `homeworks`.
    """
    try:
        homeworks = response["homeworks"]
    except KeyError:
        raise ApiError("Не удалось получить работы из ответа API.")

    if not isinstance(homeworks, list):
        raise ApiError("Неверный формат ответа списка заданий API.")

    return homeworks


def parse_status(homework: Dict[str, Any]) -> str:
    """
    Извлекает из информации о конкретной домашней работе статус этой работы.

    В качестве параметра функция получает только
    один элемент из списка домашних работ.
    В случае успеха, функция возвращает подготовленную для отправки в Telegram
    строку, содержащую один из вердиктов словаря HOMEWORK_STATUSES.
    """
    for key in settings.API_EXPECTED_KEYS:
        if key not in homework:
            raise KeyError(f"Отсутствует ключ {key} работы: {homework}")

    try:
        verdict = settings.HOMEWORK_STATUSES[homework["status"]]
    except KeyError:
        raise KeyError(f"Непредвиденный статус работы: {homework['status']}")

    homework_name = homework["homework_name"]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """
    Проверяет доступность переменных окружения, которые необходимы для работы.

    Если отсутствует хотя бы одна переменная окружения — функция должна
    вернуть False, иначе — True.
    """
    env_expected = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]

    return all(env_expected)


def main():
    """
    Основная логика работы бота.

    - Сделать запрос к API.
    - Проверить ответ.
    - Если есть обновления — получить статус работы из обновления
      и отправить сообщение в Telegram.
    - Подождать некоторое время и сделать новый запрос.
    """
    current_timestamp = int(time.time())
    last_error_message = None

    if not check_tokens():
        logger.critical(
            "Отсутствует одна из обязательных переменных окружения."
        )

        raise RuntimeError

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            current_timestamp = int(time.time())

            if len(homeworks) != 0:
                for homework in homeworks:
                    status = parse_status(homework)

                    send_message(telegram_bot, status)
            else:
                logger.debug("В ответе API отсутствуют новые статусы заданий.")

            logger.info("Отправлен запрос к API.")

        except Exception as error:
            message = f"Сбой в работе программы: {error}"

            logger.error(message)

            if last_error_message != message:
                send_message(telegram_bot, message)
                last_error_message = message

        time.sleep(settings.RETRY_TIME)


if __name__ == "__main__":
    main()
