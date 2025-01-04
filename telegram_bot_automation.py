import re
import random
import time
import json
import os
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, WebDriverException, TimeoutException, StaleElementReferenceException
from utils import get_max_games, stop_event
from urllib.parse import unquote, parse_qs
from browser_manager import BrowserManager
from colorama import Fore, Style
import logging
# Настроим логирование (если не было настроено ранее)
logger = logging.getLogger("application_logger")


class TelegramBotAutomation:
    MAX_RETRIES = 3

    def __init__(self, serial_number, settings):
        # max_games сохраняем в атрибут объекта
        self.daily_clicks_file = "daily_clicks.json"
        self.daily_click_data = {}
        self.max_games = get_max_games(settings)
        self.remaining_games = None
        self.serial_number = serial_number
        self.username = None  # Initialize username as None
        self.balance = 0.0  # Initialize balance as 0.0
        self.browser_manager = BrowserManager(serial_number)
        self.settings = settings
        self.driver = None
        self.first_game_start = True
        self.logged_farm_time = False
        self.is_limited = False  # Attribute to track limitation status
        logger.debug(
            f"#{self.serial_number}: Initializing automation for account.")

        # Ожидание завершения предыдущей сессии браузера
        if not self.browser_manager.wait_browser_close():
            logger.error(
                f"#{self.serial_number}: Failed to close previous browser session.")
            raise RuntimeError("Failed to close previous browser session")

        # Запуск браузера
        if not self.browser_manager.start_browser():
            logger.error(f"#{self.serial_number}: Failed to start browser.")
            raise RuntimeError("Failed to start browser")

        # Сохранение экземпляра драйвера
        self.driver = self.browser_manager.driver

        logger.debug(
            f"#{self.serial_number}: Automation initialization completed successfully.")

    def wait_for_page_load(self, timeout=30):
        """
        Ожидание полной загрузки страницы с помощью проверки document.readyState.

        :param driver: WebDriver Selenium.
        :param timeout: Максимальное время ожидания.
        """
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script(
                "return document.readyState") == "complete"
        )

    def safe_click(self, element):
        """
        Безопасный клик по элементу.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Attempting to scroll to element.")
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element)
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(element))
            element.click()
            logger.debug(
                f"#{self.serial_number}: Element clicked successfully.")
        except (WebDriverException, StaleElementReferenceException) as e:
            error_message = str(e).splitlines()[0]
            logger.debug(
                f"#{self.serial_number}: Error during safe click: {error_message}")
            try:
                logger.debug(
                    f"#{self.serial_number}: Attempting JavaScript click as fallback.")
                self.driver.execute_script("arguments[0].click();", element)
                logger.debug(
                    f"#{self.serial_number}: JavaScript click succeeded.")
            except (WebDriverException, StaleElementReferenceException) as e:
                error_message = str(e).splitlines()[0]
                logger.error(
                    f"#{self.serial_number}: JavaScript click failed: {error_message}")
            except Exception as e:
                logger.error(
                    f"#{self.serial_number}: Unexpected error during fallback click: {e}")
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error during safe click: {e}")

    def navigate_to_bot(self):
        """
        Очищает кэш браузера, загружает Telegram Web и закрывает лишние окна.
        """
        logger.debug(
            f"#{self.serial_number}: Starting navigation to Telegram web.")
        self.clear_browser_cache_and_reload()

        if stop_event.is_set():  # Проверка перед выполнением долгих операций
            return False

        retries = 0
        while retries < self.MAX_RETRIES and not stop_event.is_set():
            try:
                logger.debug(
                    f"#{self.serial_number}: Attempting to load Telegram web (attempt {retries + 1}).")
                self.driver.get('https://web.telegram.org/k/')

                if stop_event.is_set():  # Проверка после загрузки страницы
                    return False

                logger.debug(
                    f"#{self.serial_number}: Telegram web loaded successfully.")
                logger.debug(f"#{self.serial_number}: Closing extra windows.")
                self.close_extra_windows()

                # Эмуляция ожидания с проверкой stop_event
                sleep_time = random.randint(5, 7)
                logger.debug(
                    f"#{self.serial_number}: Sleeping for {sleep_time} seconds.")
                for _ in range(sleep_time):
                    if stop_event.is_set():
                        logger.debug(
                            f"#{self.serial_number}: Stopping sleep due to stop_event.")
                        return False
                    # Короткий sleep для проверки stop_event
                    stop_event.wait(1)

                return True

            except (WebDriverException, TimeoutException) as e:
                error_message = str(e).splitlines()[0]
                logger.warning(
                    f"#{self.serial_number}: Exception in navigating to Telegram bot (attempt {retries + 1}): {error_message}")
                retries += 1

                # Проверка во время ожидания перед повторной попыткой
                for _ in range(5):
                    if stop_event.is_set():
                        logger.debug(
                            f"#{self.serial_number}: Stopping retry sleep due to stop_event.")
                        return False
                    stop_event.wait(1)

        logger.error(
            f"#{self.serial_number}: Failed to navigate to Telegram web after {self.MAX_RETRIES} attempts.")
        return False

    def close_extra_windows(self):
        """
        Закрывает все дополнительные окна, кроме текущего.
        """
        try:
            current_window = self.driver.current_window_handle
            all_windows = self.driver.window_handles

            logger.debug(
                f"#{self.serial_number}: Current window handle: {current_window}")
            logger.debug(
                f"#{self.serial_number}: Total open windows: {len(all_windows)}")

            for window in all_windows:
                if window != current_window:
                    logger.debug(
                        f"#{self.serial_number}: Closing window: {window}")
                    self.driver.switch_to.window(window)
                    self.driver.close()
                    logger.debug(
                        f"#{self.serial_number}: Window {window} closed successfully.")

            # Переключаемся обратно на исходное окно
            self.driver.switch_to.window(current_window)
            logger.debug(
                f"#{self.serial_number}: Switched back to the current window: {current_window}")
        except WebDriverException as e:
            error_message = str(e).splitlines()[0]
            logger.debug(
                f"#{self.serial_number}: Exception while closing extra windows: {error_message}")
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error during closing extra windows: {e}")

    def send_message(self):
        """
        Отправляет сообщение в указанный Telegram-групповой чат.
        """
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                logger.debug(
                    f"#{self.serial_number}: Attempt {retries + 1} to send message.")

                # Находим область ввода сообщения
                chat_input_area = self.wait_for_element(
                    By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/input[1]'
                )
                if chat_input_area:
                    logger.debug(
                        f"#{self.serial_number}: Chat input area found.")
                    chat_input_area.click()
                    group_url = self.settings.get(
                        'TELEGRAM_GROUP_URL', 'https://t.me/CryptoProjects_sbt'
                    )
                    logger.debug(
                        f"#{self.serial_number}: Typing group URL: {group_url}")
                    chat_input_area.send_keys(group_url)
                else:
                    logger.warning(
                        f"#{self.serial_number}: Chat input area not found.")
                    retries += 1
                    stop_event.wait(5)
                    continue

                # Находим область поиска
                search_area = self.wait_for_element(
                    By.XPATH, '/html/body/div[1]/div[1]/div[1]/div[1]/div[1]/div[3]/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/div[2]/ul[1]/a[1]/div[1]'
                )
                if search_area:
                    logger.debug(f"#{self.serial_number}: Search area found.")
                    search_area.click()
                    logger.debug(
                        f"#{self.serial_number}: Group search clicked.")
                else:
                    logger.warning(
                        f"#{self.serial_number}: Search area not found.")
                    retries += 1
                    stop_event.wait(5)
                    continue

                # Добавляем задержку перед завершением
                sleep_time = random.randint(5, 7)
                logger.debug(
                    f"{Fore.LIGHTBLACK_EX}Sleeping for {sleep_time} seconds.{Style.RESET_ALL}")
                stop_event.wait(sleep_time)
                logger.debug(
                    f"#{self.serial_number}: Message successfully sent to the group.")
                return True
            except (NoSuchElementException, WebDriverException) as e:
                error_message = str(e).splitlines()[0]
                logger.warning(
                    f"#{self.serial_number}: Failed to perform action (attempt {retries + 1}): {error_message}")
                retries += 1
                stop_event.wait(5)
            except Exception as e:
                logger.error(f"#{self.serial_number}: Unexpected error: {e}")
                break

        logger.error(
            f"#{self.serial_number}: Failed to send message after {self.MAX_RETRIES} attempts.")
        return False

    def click_link(self):
        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                logger.debug(
                    f"#{self.serial_number}: Attempt {retries + 1} to click link.")

                # Получаем ссылку из настроек
                bot_link = self.settings.get(
                    'BOT_LINK', 'https://t.me/TVerse?startapp=galaxy-0005d5bdb20004615f720004f50b2f')
                logger.debug(f"#{self.serial_number}: Bot link: {bot_link}")

                # Поиск элемента ссылки
                link = self.wait_for_element(
                    By.CSS_SELECTOR, f"a[href*='{bot_link}']")
                if link:
                    logger.debug(
                        f"#{self.serial_number}: Link found. Scrolling to the link.")

                    # Скроллинг к ссылке
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({ behavior: 'smooth', block: 'center' });", link)
                    # Небольшая задержка для завершения скроллинга
                    stop_event.wait(1)

                    # Клик по ссылке
                    link.click()
                    logger.debug(
                        f"#{self.serial_number}: Link clicked successfully.")
                    stop_event.wait(2)

                # Поиск и клик по кнопке запуска
                launch_button = self.wait_for_element(
                    By.CSS_SELECTOR, "button.popup-button.btn.primary.rp", timeout=5)
                if launch_button:
                    logger.debug(
                        f"#{self.serial_number}: Launch button found. Clicking it.")
                    launch_button.click()
                    logger.debug(
                        f"#{self.serial_number}: Launch button clicked.")

                # Проверка iframe
                if self.check_iframe_src():
                    logger.info(
                        f"#{self.serial_number}: App loaded successfully.")

                    # Случайная задержка перед переключением на iframe
                    sleep_time = random.randint(3, 5)
                    logger.debug(
                        f"#{self.serial_number}: Sleeping for {sleep_time} seconds before switching to iframe.")
                    stop_event.wait(sleep_time)

                    # Переключение на iframe
                    self.switch_to_iframe()
                    logger.debug(
                        f"#{self.serial_number}: Switched to iframe successfully.")
                    return True
                else:
                    logger.warning(
                        f"#{self.serial_number}: Iframe did not load expected content.")
                    raise Exception("Iframe content validation failed.")

            except (NoSuchElementException, WebDriverException, TimeoutException) as e:
                logger.warning(
                    f"#{self.serial_number}: Failed to click link or interact with elements (attempt {retries + 1}): {str(e).splitlines()[0]}")
                retries += 1
                stop_event.wait(5)
            except Exception as e:
                logger.error(
                    f"#{self.serial_number}: Unexpected error during click_link: {str(e).splitlines()[0]}")
                break

        logger.error(
            f"#{self.serial_number}: All attempts to click link failed after {self.MAX_RETRIES} retries.")
        return False

    def wait_for_element(self, by, value, timeout=10):
        """
        Ожидает, пока элемент станет кликабельным, в течение указанного времени.

        :param by: Метод локатора (например, By.XPATH, By.ID).
        :param value: Значение локатора.
        :param timeout: Время ожидания в секундах (по умолчанию 10).
        :return: Найденный элемент, если он кликабельный, иначе None.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Waiting for element by {by} with value '{value}' for up to {timeout} seconds.")
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
            logger.debug(
                f"#{self.serial_number}: Element found and clickable: {value}")
            return element
        except TimeoutException:
            logger.debug(
                f"#{self.serial_number}: Element not found or not clickable within {timeout} seconds: {value}")
            return None
        except (WebDriverException, StaleElementReferenceException) as e:
            logger.debug(
                f"#{self.serial_number}: Error while waiting for element {value}: {str(e).splitlines()[0]}")
            return None
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error while waiting for element: {str(e)}")
            return None

    def clear_browser_cache_and_reload(self):
        """
        Очищает кэш браузера и перезагружает текущую страницу.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Attempting to clear browser cache.")

            # Очистка кэша через CDP команду
            self.driver.execute_cdp_cmd("Network.clearBrowserCache", {})
            logger.debug(
                f"#{self.serial_number}: Browser cache successfully cleared.")

            # Перезагрузка текущей страницы
            logger.debug(f"#{self.serial_number}: Refreshing the page.")
            self.driver.refresh()
            logger.debug(
                f"#{self.serial_number}: Page successfully refreshed.")
        except WebDriverException as e:
            logger.warning(
                f"#{self.serial_number}: WebDriverException while clearing cache or reloading page: {str(e).splitlines()[0]}")
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error during cache clearing or page reload: {str(e)}")

    def preparing_account(self):
        """
        Подготавливает аккаунт, проверяя доступность прогресс бара и кликая на элемент в верхнем правом углу.
        Возвращает True, если выполнение успешно, иначе False.
        """
        retries = 0

        while retries < self.MAX_RETRIES:
            if stop_event.is_set():
                logger.debug(
                    f"#{self.serial_number}: Stop event detected. Exiting preparing_account.")
                return False  # Завершаем с неуспешным результатом

            try:
                # Проверяем наличие прогресс бара через get_time
                remaining_time = self.get_time()
                if remaining_time:
                    logger.debug(
                        f"#{self.serial_number}: Progress bar is available. Skipping account preparation.")
                    return True  # Прогресс бар доступен, подготовка не требуется

                # Уточняем селектор для элемента в верхнем правом углу
                button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "div#ui-top-right a.ui-link.blur svg")
                    )
                )
                button.click()
                logger.debug(
                    f"#{self.serial_number}: Successfully clicked on the top-right button.")
                return True  # Успешное выполнение
            except TimeoutException:
                retries += 1
                logger.debug(
                    f"#{self.serial_number}: Top-right button not found within timeout (attempt {retries}/{self.MAX_RETRIES}).")
            except WebDriverException as e:
                retries += 1
                logger.debug(
                    f"#{self.serial_number}: Failed to click top-right button (attempt {retries}/{self.MAX_RETRIES}): {str(e).splitlines()[0]}")
            finally:
                if retries < self.MAX_RETRIES:
                    # Проверяем stop_event во время паузы между попытками
                    for _ in range(5):
                        if stop_event.is_set():
                            logger.debug(
                                f"#{self.serial_number}: Stop event detected during retry. Exiting preparing_account.")
                            return False
                        stop_event.wait(1)

        logger.debug(
            f"#{self.serial_number}: Failed to prepare account after {self.MAX_RETRIES} retries.")
        return False  # На случай, если цикл завершится без успешного клика

    def check_iframe_src(self):
        iframe_name = "app.tonverse.app"
        """
        Проверяет, загружен ли правильный iframe по URL в атрибуте src с ожиданием.
        """
        try:
            logger.debug(
                f"#{self.serial_number}: Waiting for iframe to appear...")

            # Ждем появления iframe в течение 20 секунд
            iframe = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "iframe"))
            )
            logger.debug(
                f"#{self.serial_number}: Iframe detected. Checking src attribute.")

            iframe_src = iframe.get_attribute("src")

            # Проверяем, соответствует ли src ожидаемому значению
            if iframe_name in iframe_src and "tgWebAppData" in iframe_src:
                logger.debug(
                    f"#{self.serial_number}: Iframe src is valid: {iframe_src}")
                return True
            else:
                logger.warning(
                    f"#{self.serial_number}: Unexpected iframe src: {iframe_src}")
                return False
        except TimeoutException:
            logger.error(
                f"#{self.serial_number}: Iframe not found within the timeout period.")
            return False
        except (WebDriverException, Exception) as e:
            logger.warning(
                f"#{self.serial_number}: Error while checking iframe src: {str(e).splitlines()[0]}")
            return False

    def get_username(self):
        """
        Извлечение имени пользователя из sessionStorage.
        """
        if stop_event.is_set():
            logger.debug(
                f"#{self.serial_number}: Stop event detected. Exiting get_username.")
            return None

        try:
            # Извлекаем __telegram__initParams из sessionStorage
            logger.debug(
                f"#{self.serial_number}: Attempting to retrieve '__telegram__initParams' from sessionStorage.")
            init_params = self.driver.execute_script(
                "return sessionStorage.getItem('__telegram__initParams');"
            )
            if not init_params:
                raise Exception("InitParams not found in sessionStorage.")

            # Преобразуем данные JSON в Python-объект
            init_data = json.loads(init_params)
            logger.debug(
                f"#{self.serial_number}: InitParams successfully retrieved.")

            # Получаем tgWebAppData
            tg_web_app_data = init_data.get("tgWebAppData")
            if not tg_web_app_data:
                raise Exception("tgWebAppData not found in InitParams.")

            # Декодируем tgWebAppData
            decoded_data = unquote(tg_web_app_data)
            logger.debug(
                f"#{self.serial_number}: Decoded tgWebAppData: {decoded_data}")

            # Парсим строку параметров
            parsed_data = parse_qs(decoded_data)
            logger.debug(
                f"#{self.serial_number}: Parsed tgWebAppData: {parsed_data}")

            # Извлекаем параметр 'user' и преобразуем в JSON
            user_data = parsed_data.get("user", [None])[0]
            if not user_data:
                raise Exception("User data not found in tgWebAppData.")

            # Парсим JSON и извлекаем username
            user_info = json.loads(user_data)
            username = user_info.get("username")
            logger.debug(
                f"#{self.serial_number}: Username successfully extracted: {username}")

            return username

        except Exception as e:
            # Логируем ошибку без громоздкого Stacktrace
            error_message = str(e).splitlines()[0]
            logger.debug(
                f"#{self.serial_number}: Error extracting Telegram username: {error_message}")
            return None

    def get_balance(self):
        """
        Открывает профиль, извлекает баланс звезд и закрывает окно профиля.
        """
        try:
            # Открытие окна профиля
            logger.debug(
                f"#{self.serial_number}: Navigating to profile section.")
            profile_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "div#ui-top-right a.ui-link.blur"))
            )
            profile_button.click()

            # Поиск строки с ресурсами
            logger.debug(
                f"#{self.serial_number}: Searching for resources row.")
            resources_row = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class, 'details-row') and (.//i[text()='Ресурсы' or text()='Assets'])]"
                ))
            )

            # Извлечение данных из блока ресурсов
            logger.debug(
                f"#{self.serial_number}: Extracting star balance from resources row.")
            balance_text = resources_row.find_element(
                By.XPATH,
                ".//b/span[contains(text(), 'Звезд') or contains(text(), 'Stars')]/preceding-sibling::span[1]"
            ).text.strip()

            logger.debug(
                f"#{self.serial_number}: Found star balance text: '{balance_text}'")

            # Парсинг числового значения
            balance = int(balance_text.replace(",", "")) if balance_text else 0
            logger.debug(
                f"#{self.serial_number}: Extracted star balance: {balance}")

            # Закрытие окна профиля
            logger.debug(f"#{self.serial_number}: Closing profile window.")
            profile_close_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "div.content-footer a.ui-link.blur.close"))
            )
            profile_close_button.click()
            logger.debug(f"#{self.serial_number}: Profile window closed.")

            return balance
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Error retrieving balance: {str(e)}")
            return 0

    def get_time(self):
        """
        Получает оставшееся время до завершения прогресса на основе универсального поиска элемента.
        Если прогресс завершен, возвращает '00:00:00'.
        """
        retries = 0
        total_time_seconds = 3600  # 1 час = 3600 секунд

        while retries < self.MAX_RETRIES:
            if stop_event.is_set():
                logger.debug(
                    f"#{self.serial_number}: Stop event detected. Exiting get_time.")
                return None

            try:
                # Поиск всех элементов `<a>` с классом `ui-link blur`
                logger.debug(
                    f"#{self.serial_number}: Searching for progress elements.")
                progress_blocks = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "a.ui-link.blur"))
                )

                for block in progress_blocks:
                    # Логируем текст кнопки
                    block_text = block.text.strip()
                    logger.debug(
                        f"#{self.serial_number}: Found progress block text: '{block_text}'")

                    # Если текст содержит статус завершения
                    if "Собрать пыль" in block_text:
                        return "00:00:00"  # Прогресс завершен

                    # Поиск процентов внутри дочерних элементов
                    span_elements = block.find_elements(
                        By.CSS_SELECTOR, "span.font-mono")
                    for span in span_elements:
                        span_text = span.text.strip()
                        logger.debug(
                            f"#{self.serial_number}: Checking span text: '{span_text}'")

                        percentage_pattern = r"(\d+)%"
                        match = re.search(percentage_pattern, span_text)

                        if match:
                            progress_percentage = int(match.group(1))
                            logger.debug(
                                f"#{self.serial_number}: Current progress percentage: {progress_percentage}%")

                            # Расчет оставшегося времени
                            remaining_seconds = total_time_seconds * \
                                (1 - progress_percentage / 100)

                            # Форматирование времени в HH:MM:SS
                            hours = int(remaining_seconds // 3600)
                            minutes = int((remaining_seconds % 3600) // 60)
                            seconds = int(remaining_seconds % 60)
                            formatted_time = f"{hours:02}:{minutes:02}:{seconds:02}"

                            logger.debug(
                                f"#{self.serial_number}: Remaining time: {formatted_time}")
                            return formatted_time

                logger.debug(
                    f"#{self.serial_number}: No valid progress or completion blocks found.")
                return None

            except (NoSuchElementException, TimeoutException):
                retries += 1
                logger.debug(
                    f"#{self.serial_number}: Element not found or timeout (attempt {retries}/{self.MAX_RETRIES})."
                )
                stop_event.wait(1)

            except Exception as e:
                logger.error(
                    f"#{self.serial_number}: Unexpected error in get_time: {e}")
                return None

        logger.debug(
            f"#{self.serial_number}: Failed to retrieve progress after {self.MAX_RETRIES} retries.")
        return None

    def farming(self):
        """
        Функция автоматизации сбора пыли и создания звезд.
        """
        try:
            # Получаем оставшееся время
            logger.debug(f"#{self.serial_number}: Checking progress status.")
            remaining_time = self.get_time()

            if remaining_time == "00:00:00" or int(remaining_time.split(":")[1]) <= 6:
                logger.info(
                    f"#{self.serial_number}: Progress >= 90% or completed. Attempting to collect dust.")

                # Поиск кнопки "Собрать пыль"
                logger.debug(
                    f"#{self.serial_number}: Searching for 'Collect Dust' button.")
                progress_blocks = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "a.ui-link.blur"))
                )

                for block in progress_blocks:
                    block_text = block.text.strip()
                    logger.debug(
                        f"#{self.serial_number}: Found block with text: '{block_text}'")

                    # Условие для определения кнопки "Собрать пыль"
                    if "Собрать пыль" in block_text or (
                        "%" in block_text and int(
                            block_text.replace("%", "").strip()) >= 90
                    ):
                        logger.debug(
                            f"#{self.serial_number}: Clicking 'Collect Dust' button. Found block with text: '{block_text}'")

                        # Попытка обычного клика
                        try:
                            block.click()
                            logger.debug(
                                f"#{self.serial_number}: Dust collected successfully.")
                        except Exception as e:
                            logger.warning(
                                f"#{self.serial_number}: Click failed with error: {e}. Trying JavaScript.")
                            self.driver.execute_script(
                                "arguments[0].click();", block)
                            logger.debug(
                                f"#{self.serial_number}: Dust collected using JavaScript.")

                        # Завершаем цикл после успешного клика
                        break
                else:
                    logger.warning(
                        f"#{self.serial_number}: 'Collect Dust' button not found.")
            else:
                logger.info(
                    f"#{self.serial_number}: Progress < 90%. No action taken.")

        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Error in farming function: {str(e)}", exc_info=True)

    def create_stars(self):
        """
        Процесс создания звезд с повторным открытием окна и проверкой баланса.
        """
        try:
            logger.info(
                f"#{self.serial_number}: Starting 'Create Stars' process.")
            for attempt in range(5):  # Максимум 5 попыток
                try:
                    # Открытие окна создания звезд
                    create_stars_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, "div#ui-bottom a.ui-link.blur svg + span"))
                    )
                    create_stars_button.click()

                    # Проверяем стоимость
                    price_block = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "label.details.d-flex.justify-content-between"))
                    )

                    # Извлечение основного баланса
                    main_balance_element = price_block.find_element(
                        By.XPATH, ".//span[1]"
                    )
                    main_balance_text = main_balance_element.text.strip()
                    main_balance = int(main_balance_text.replace(
                        ",", "")) if main_balance_text.replace(",", "").isdigit() else 0

                    # Извлечение дополнительного баланса
                    additional_balance_element = price_block.find_elements(
                        By.XPATH, ".//span[contains(text(), '+')]/following-sibling::span[1]"
                    )
                    additional_balance = int(additional_balance_element[0].text.strip().replace(
                        ",", "")) if additional_balance_element else 0

                    logger.debug(
                        f"#{self.serial_number}: Extracted balances - Main: {main_balance}, Additional: {additional_balance}"
                    )

                    # Логика проверки
                    if main_balance == 0:
                        logger.info(
                            f"#{self.serial_number}: 'Create Stars' process stopped due to main balance being 0."
                        )
                        # Закрываем окно
                        close_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable(
                                (By.CSS_SELECTOR, "div.content-footer a.ui-link.blur.close"))
                        )
                        close_button.click()
                        break

                    if additional_balance > 0:
                        logger.info(
                            f"#{self.serial_number}: 'Create Stars' process stopped due to additional balance ({additional_balance})."
                        )
                        # Закрываем окно
                        close_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable(
                                (By.CSS_SELECTOR, "div.content-footer a.ui-link.blur.close"))
                        )
                        close_button.click()
                        break

                    # Если основная логика пройдена, создаем звезды
                    create_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, "div.content-body .buttons-row button.ui-button"))
                    )
                    create_button.click()

                    # Ожидание закрытия окна
                    WebDriverWait(self.driver, 10).until(
                        EC.invisibility_of_element(
                            (By.CSS_SELECTOR, "div.content-body"))
                    )
                    logger.info(
                        f"#{self.serial_number}: Stars created successfully.")
                    break
                except TimeoutException:
                    logger.debug(
                        f"#{self.serial_number}: Timeout during 'Create Stars' process. Retrying..."
                    )
                except Exception as e:
                    logger.debug(
                        f"#{self.serial_number}: Unexpected issue during 'Create Stars' process: {str(e)}. Retrying..."
                    )
                finally:
                    if attempt == 4:
                        logger.info(
                            f"#{self.serial_number}: Reached maximum attempts for 'Create Stars' process."
                        )
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Error in 'Create Stars' process: {str(e)}", exc_info=False
            )

    def switch_to_iframe(self):
        """
        Switches to the first iframe on the page, if available.
        """
        try:
            # Возвращаемся к основному контенту страницы
            logger.debug(
                f"#{self.serial_number}: Switching to the default content.")
            self.driver.switch_to.default_content()

            # Ищем все iframes на странице
            logger.debug(
                f"#{self.serial_number}: Looking for iframes on the page.")
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            logger.debug(
                f"#{self.serial_number}: Found {len(iframes)} iframes on the page.")

            if iframes:
                # Переключаемся на первый iframe
                self.driver.switch_to.frame(iframes[0])
                logger.debug(
                    f"#{self.serial_number}: Successfully switched to the first iframe.")
                return True
            else:
                logger.warning(
                    f"#{self.serial_number}: No iframes found to switch.")
                return False
        except NoSuchElementException:
            logger.warning(
                f"#{self.serial_number}: No iframe element found on the page.")
            return False
        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Unexpected error while switching to iframe: {str(e)}")
            return False

    def load_click_data(self):
        """
        Загружает данные из JSON-файла или создает пустую структуру, если файл отсутствует.
        """
        if os.path.exists(self.daily_clicks_file):
            try:
                with open(self.daily_clicks_file, "r") as file:
                    data = json.load(file)

                # Убедимся, что ключи уникальны
                unique_data = {}
                for key, value in data.items():
                    unique_data[str(key)] = value
                logger.debug(f"Loaded click data: {unique_data}")
                return unique_data
            except Exception as e:
                logger.error(
                    f"Failed to load click data: {str(e)}. Resetting data.")
                return {}
        logger.debug("Click data file not found. Returning empty data.")
        return {}

    def update_click_data(self, serial_number, current_date, increment_click=False):
        """
        Обновляет данные кликов для заданного серийного номера и текущей даты.
        Если increment_click=True, увеличивает количество кликов.
        """
        serial_number = str(serial_number)  # Убедимся, что ключ всегда строка
        logger.debug(
            f"Updating click data for serial_number={serial_number}, current_date={current_date}, increment_click={increment_click}")

        if serial_number not in self.daily_click_data:
            # Если данные для этого аккаунта отсутствуют, создаём запись
            self.daily_click_data[serial_number] = {
                "clicks": 0, "date": current_date
            }
            logger.debug(
                f"Created new click data for serial_number={serial_number}.")
        elif self.daily_click_data[serial_number]["date"] != current_date:
            # Если дата изменилась, сбрасываем клики
            self.daily_click_data[serial_number] = {
                "clicks": 0, "date": current_date
            }
            logger.debug(
                f"Date changed. Reset clicks for serial_number={serial_number}.")

        if increment_click:
            self.daily_click_data[serial_number]["clicks"] += 1
            logger.debug(
                f"Incremented clicks for serial_number={serial_number}. Current clicks: {self.daily_click_data[serial_number]['clicks']}")

        # Сохраняем данные
        self.save_click_data()

    def save_click_data(self):
        """
        Сохраняет данные в JSON-файл.
        """
        try:
            # Гарантируем уникальность данных перед сохранением
            unique_data = {}
            for key, value in self.daily_click_data.items():
                unique_data[str(key)] = value

            with open(self.daily_clicks_file, "w") as file:
                json.dump(unique_data, file, indent=4)
            logger.debug(f"Saved click data: {unique_data}")
        except Exception as e:
            logger.error(f"Failed to save click data: {str(e)}")

    def reset_daily_clicks(self, serial_number):
        """
        Сбрасывает счетчик кликов для указанного аккаунта.
        """
        self.daily_click_data[serial_number] = {
            "clicks": 0,
            "date": datetime.now().strftime("%Y-%m-%d")
        }
        self.save_click_data()

    def create_quests(self):
        """
        Выполняет процесс нажатия кнопок для создания квестов с учетом ограничения в 10 кликов в сутки.
        """
        try:
            logger.info(
                f"#{self.serial_number}: Starting 'Quests' process.")

            # Загружаем данные из JSON
            self.daily_click_data = self.load_click_data()

            # Проверяем и обновляем данные
            current_date = datetime.now().strftime("%Y-%m-%d")
            # Преобразуем serial_number в строку
            serial_number_str = str(self.serial_number)
            self.update_click_data(serial_number_str, current_date)

            # Проверка лимита кликов
            if self.daily_click_data.get(serial_number_str, {}).get("clicks", 0) >= 10:
                logger.info(
                    f"#{self.serial_number}: Daily limit of 10 clicks reached. Exiting.")
                return

            for attempt in range(15):
                if stop_event.is_set():
                    logger.debug(
                        f"#{self.serial_number}: Stop event detected. Exiting 'Quests' process.")
                    break

                if self.daily_click_data[serial_number_str]["clicks"] >= 10:
                    logger.info(
                        f"#{self.serial_number}: Reached daily limit of 10 clicks. Exiting.")
                    break

                try:
                    top_left_button = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, "div#ui-top-left a.ui-link.blur svg"))
                    )
                    top_left_button.click()
                    logger.debug(
                        f"#{self.serial_number}: Clicked top-left button.")

                    try:
                        elki_igalki_button = WebDriverWait(self.driver, 4).until(
                            EC.element_to_be_clickable(
                                (By.XPATH,
                                 "//a[contains(., 'Ёлки-иголки!') or contains(., 'Collect needles')]")
                            )
                        )
                        elki_igalki_button.click()
                        self.update_click_data(
                            serial_number_str, current_date, increment_click=True)
                        logger.info(
                            f"#{self.serial_number}: Clicked 'Ёлки-иголки!' button. Total clicks today: {self.daily_click_data[serial_number_str]['clicks']}"
                        )
                    except TimeoutException:
                        logger.debug(
                            f"#{self.serial_number}: 'Ёлки-иголки!' button not found. Continuing attempts...")

                except TimeoutException:
                    logger.debug(
                        f"#{self.serial_number}: Top-left button not found. Retrying...")
                except Exception as e:
                    logger.error(
                        f"#{self.serial_number}: Unexpected error during 'Quests' process: {str(e)}")
                    break

                stop_event.wait(1)

            logger.info(
                f"#{self.serial_number}: Returning home after quest creation.")
            self.preparing_account()

        except Exception as e:
            logger.error(
                f"#{self.serial_number}: Error in 'Quests' process: {str(e)}")
