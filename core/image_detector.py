#!/usr/bin/env python3
"""
Модуль для детектирования изображений на экране
"""

import cv2
import time
import numpy as np
import pyautogui
from PIL import ImageGrab
from pathlib import Path


class ImageDetector:
    """Класс для поиска шаблонов изображений на экране"""
    
    def __init__(self, template_path="resources/templates", threshold=0.8):
        self.template_path = Path(template_path)
        self.threshold = threshold
        
    def find_template(self, template_path, screenshot=None, region=None):
        """
        Поиск шаблона на экране
        
        Args:
            template_path (str): Путь к файлу шаблона
            screenshot (numpy.ndarray, optional): Скриншот для поиска
            region (tuple, optional): Область поиска (x, y, width, height)
            
        Returns:
            dict: Результат поиска с полями found, position, confidence
        """
        try:
            # Загрузка шаблона
            # OpenCV's narrow-path imread can fail on Cyrillic Windows folders.
            template = cv2.imdecode(np.fromfile(str(template_path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if template is None:
                return {"found": False, "position": None, "confidence": 0.0, "error": True}
                
            # Получение скриншота
            if screenshot is None:
                if region:
                    x, y, width, height = region
                    screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True)
                else:
                    screenshot = pyautogui.screenshot()
                    
                # Конвертация скриншота в numpy array
                screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                
            # Поиск шаблона
            if screenshot.shape[0] < template.shape[0] or screenshot.shape[1] < template.shape[1]:
                return {"found": False, "position": None, "confidence": 0.0, "error": True}
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            # Проверка порога
            if max_val >= self.threshold:
                # Координаты центра найденного шаблона
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                offset_x, offset_y = region[:2] if region else (0, 0)
                
                return {
                    "found": True,
                    "position": (center_x + offset_x, center_y + offset_y),
                    "confidence": max_val,
                    "top_left": (max_loc[0] + offset_x, max_loc[1] + offset_y),
                    "bottom_right": (max_loc[0] + w + offset_x, max_loc[1] + h + offset_y)
                }
            else:
                return {"found": False, "position": None, "confidence": max_val}
                
        except Exception as e:
            print(f"Ошибка при поиске шаблона {template_path}: {str(e)}")
            return {"found": False, "position": None, "confidence": 0.0, "error": True}
            
    def find_multiple_templates(self, template_paths, region=None):
        """
        Поиск нескольких шаблонов
        
        Args:
            template_paths (list): Список путей к файлам шаблонов
            region (tuple, optional): Область поиска
            
        Returns:
            list: Список найденных шаблонов
        """
        results = []
        
        # Делаем один скриншот для всех шаблонов
        if region:
            x, y, width, height = region
            screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True)
        else:
            screenshot = pyautogui.screenshot()
            
        screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        for template_path in template_paths:
            result = self.find_template(template_path, screenshot, region=region)
            if result["found"]:
                results.append({
                    "template": template_path,
                    "position": result["position"],
                    "confidence": result["confidence"]
                })
                
        return results
        
    def wait_for_template(self, template_path, timeout=30, interval=1):
        """
        Ожидание появления шаблона на экране
        
        Args:
            template_path (str): Путь к файлу шаблона
            timeout (int): Таймаут ожидания в секундах
            interval (int): Интервал проверки в секундах
            
        Returns:
            dict: Результат поиска
        """
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            result = self.find_template(template_path)
            if result["found"]:
                return result
            time.sleep(interval)
            
        return {"found": False, "position": None, "confidence": 0.0}
        
    def set_threshold(self, threshold):
        """Установка порога чувствительности"""
        self.threshold = threshold
        
    def get_threshold(self):
        """Получение текущего порога чувствительности"""
        return self.threshold
