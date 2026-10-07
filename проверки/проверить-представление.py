"""Проверка краткой версии, PDF и схем. Только локальные файлы."""
from __future__ import annotations

import hashlib
import html
import json
import re
import runpy
from pathlib import Path
from urllib.parse import unquote, urlparse

import fitz

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def plain(text: str) -> str:
    return re.sub(r'\s+', '', html.unescape(re.sub(r'<[^>]+>', '', text)))


def main() -> None:
    original = runpy.run_path(str(ROOT / 'проверки/проверить.py'))
    builder = runpy.run_path(str(ROOT / 'представление/собрать.py'))
    data = json.loads((ROOT / 'примеры/02-данные.json').read_text(encoding='utf-8'))
    require(not original['validate'](data), 'Некорректны исходные данные')
    expected = original['metrics'](data)
    manifest = json.loads((ROOT / 'представление/проверка-сборки.json').read_text(encoding='utf-8'))
    values = builder['values'](data)
    require(manifest['показатели'] == values, 'Показатели сборки устарели')
    for key, value in values.items():
        require(expected[key] == value, f'Расчёт показателя расходится: {key}')
    require(manifest['страниц'] == 5, 'Ожидалось пять страниц')
    for name, checksum in manifest['файлы'].items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT) and path.is_file(), f'Нет файла: {name}')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == checksum, f'Файл изменён после сборки: {name}')
    content = builder['pages'](values, data)
    text = (ROOT / 'представление/кейс.md').read_text(encoding='utf-8')
    require(text == builder['export_markdown'](content), 'Краткая версия не соответствует исходнику')
    # Подробный пример не должен незаметно измениться относительно рассказа.
    row = next(r for r in data['арм'] if r['номер'] == 'DEMO-ARM-004')
    require(row['конфигурация'] == 'Astra + Windows' and row['работа']['состояние'] == 'Завершена', 'Изменилось исходное состояние DEMO-ARM-004')
    removal = row['вывод_windows']
    require(removal['номер'] == 'DEMO-WIN-004' and removal['состояние'] == 'Ожидание готовности ПО', 'Изменилась задача вывода Windows')
    require([d['готово'] for d in removal['зависимости']] == [True, False], 'Изменились зависимости примера')
    require(original['example_tests'](data) == 17, 'Изменилось число проверок; обновите представление')
    pdf_path = ROOT / 'представление' / builder['PDF_NAME']
    require(pdf_path.stat().st_size < 2_000_000, 'PDF слишком велик для краткого приложения')
    links = 0
    with fitz.open(pdf_path) as pdf:
        require(len(pdf) == 5, 'Неверное число страниц PDF')
        require(pdf.metadata['author'] == 'Даниил Рогулин', 'Неверный автор документа')
        for i, page in enumerate(pdf):
            extracted = plain(page.get_text())
            require('\ufffd' not in extracted and len(extracted) > 300, f'Проблема извлечения текста: страница {i + 1}')
            for block in content[i]:
                if block[0] in {'title', 'lead', 'p', 'h2', 'small', 'note'}:
                    require(plain(block[1]) in extracted, f'Потерян текст на странице {i + 1}: {block[1][:45]}')
                elif block[0] == 'table':
                    for cells in block[1]:
                        for cell in cells:
                            require(plain(cell) in extracted, f'Нет значения таблицы: {cell}')
            for x0, y0, x1, y1, word, *_ in page.get_text('words'):
                require(x0 >= 15 and y0 >= 10 and x1 <= page.rect.width - 15 and y1 <= page.rect.height - 10, f'Текст выходит за край страницы {i + 1}: {word}')
            for link in page.get_links():
                uri = link.get('uri', '')
                require(uri.startswith(builder['REPO']), f'Непредусмотренная ссылка в PDF: {uri}')
                parsed = unquote(urlparse(uri).path)
                marker = '/case-01/blob/main/'
                if marker in parsed:
                    target = (ROOT / parsed.split(marker, 1)[1]).resolve()
                    require(target.is_relative_to(ROOT) and target.is_file(), f'Ссылка PDF не найдена: {uri}')
                links += 1
            # Проверка возможности отрисовки; визуальный просмотр выполняется отдельно.
            require(page.get_pixmap().width > 0, 'Не удалось отрисовать страницу')
    require(links >= 8, 'В PDF отсутствуют ссылки на подробные материалы')
    for name in ('01-модель-учёта', '02-процесс-работ'):
        require((ROOT / f'схемы/{name}.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'), f'Повреждено изображение: {name}')
        require('<svg' in (ROOT / f'схемы/{name}.svg').read_text(encoding='utf-8'), f'Повреждено векторное изображение: {name}')
    print(f'Представление проверено: 5 страниц; ссылок PDF: {links}; показатели, текст и контрольные суммы согласованы.')
    print(f'SHA-256 PDF: {hashlib.sha256(pdf_path.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
