import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests
import telegram
from dotenv import load_dotenv

from exceptions import ApiError

load_dotenv()

PRACTICUM_TOKEN: Optional[str] = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN: Optional[str] = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")

RETRY_TIME = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}

HOMEWORK_STATUSES = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}

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
        response = requests.get(url=ENDPOINT, params=params, headers=HEADERS)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        raise ApiError(f"Эндпоинт {ENDPOINT} недоступен - {error}")
    except requests.exceptions.RequestException as error:
        if not isinstance(requests.exceptions.HTTPError, str):
            raise ApiError(f"Сбой запроса эндпоинта {ENDPOINT} - {error}")
    else:
        return response.json()


def check_response(response: Dict) -> List[Dict]:
    """
    Проверяет ответ API на корректность.

    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python. Если ответ API соответствует ожиданиям,
    то функция должна вернуть список домашних работ (он может быть и пустым),
    доступный в ответе API по ключу `homeworks`.
    """
    try:
        return response["homeworks"]
    except KeyError:
        message = "Не удалось получить работы из ответа API."
        logger.error(message)
        send_message(telegram_bot, message)

        return []


def parse_status(homework: Dict[str, Any]) -> Optional[str]:
    """
    Извлекает из информации о конкретной домашней работе статус этой работы.

    В качестве параметра функция получает только
    один элемент из списка домашних работ.
    В случае успеха, функция возвращает подготовленную для отправки в Telegram
    строку, содержащую один из вердиктов словаря HOMEWORK_STATUSES.
    """
    try:
        homework_name = homework["homework_name"]
        homework_status = homework["status"]
    except KeyError:
        message = f"Не удалось извлечь информацию из работы: {homework}"
        logger.error(message)
        send_message(telegram_bot, message)

        return None

    try:
        verdict = HOMEWORK_STATUSES[homework_status]
    except KeyError:
        message = f"Непредвиденный статус работы: {homework_status}"
        logger.error(message)
        send_message(telegram_bot, message)

        return None

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """
    Проверяет доступность переменных окружения, которые необходимы для работы.

    Если отсутствует хотя бы одна переменная окружения — функция должна
    вернуть False, иначе — True.
    """
    for env in [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]:
        if not env:
            return False

    return True


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

            for homework in homeworks:
                status = parse_status(homework)

                if status:
                    send_message(telegram_bot, status)

        except Exception as error:
            message = f"Сбой в работе программы: {error}"

            logger.error(message)

            if last_error_message != message:
                send_message(telegram_bot, message)
                last_error_message = message

        else:
            logger.info("Отправлен запрос к API.")

            if len(homeworks) == 0:
                logger.debug("В ответе API отсутствуют новые статусы заданий.")

        time.sleep(RETRY_TIME)


if __name__ == "__main__":
    main()
