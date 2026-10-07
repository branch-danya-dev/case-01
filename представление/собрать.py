"""Собрать краткий кейс, PDF и изображения из одного описания.

Зависимости: ReportLab 4.4.9, PyMuPDF 1.26.7; шрифты DejaVu Sans.
Исходные данные читаются только из вымышленного примера. Сетевых обращений нет.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import fitz
from reportlab import rl_config
from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'представление'
ASSETS = ROOT / 'схемы'
PDF_NAME = 'Рогулин-Даниил-кейс-Astra-Linux.pdf'
REPO = 'https://github.com/branch-danya-dev/case-01'
INK = colors.HexColor('#182F45')
ACCENT = colors.HexColor('#146A70')
MUTED = colors.HexColor('#536779')
PALE = colors.HexColor('#EEF4F5')
BORDER = colors.HexColor('#CFDCE2')
rl_config.invariant = 1


def fonts() -> None:
    folder = Path(os.environ.get('CASE_FONT_DIR', '/usr/share/fonts/truetype/dejavu'))
    for name, file in [('Case', 'DejaVuSans.ttf'), ('Case-Bold', 'DejaVuSans-Bold.ttf')]:
        path = folder / file
        if not path.is_file():
            raise FileNotFoundError(f'Нет шрифта {path}. Укажите папку в CASE_FONT_DIR.')
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily('Case', normal='Case', bold='Case-Bold', italic='Case', boldItalic='Case-Bold')


def values(data: dict) -> dict:
    """Показатели берутся из примера, а не из закрытых задач установки."""
    rows = data['арм']
    counts = Counter(row['конфигурация'] for row in rows)
    historical = {e['арм'] for e in data['события'] if e['тип'] == 'Установка'}
    return {
        'всего': len(rows), 'астра': counts['Только Astra'],
        'двойная': counts['Astra + Windows'], 'windows': counts['Windows'],
        'неизвестно': counts['Не подтверждено'],
        'установлено': counts['Только Astra'] + counts['Astra + Windows'],
        'история': len(historical),
        'инциденты': sum(i['состояние'] == 'Открыт' for i in data['инциденты']),
    }


def wrap(text: str, width: float, size: float, font: str = 'Case') -> list[str]:
    result, line = [], ''
    for word in text.split():
        trial = f'{line} {word}'.strip()
        if pdfmetrics.stringWidth(trial, font, size) > width and line:
            result.append(line)
            line = word
        else:
            line = trial
    return result + ([line] if line else [])


def label(d: Drawing, x: float, y: float, text: str, size: float = 20, bold: bool = False, color=INK) -> None:
    d.add(String(x, y, text, fontName='Case-Bold' if bold else 'Case', fontSize=size, fillColor=color))


def card(d: Drawing, x: float, y: float, width: float, height: float, title: str, lines: list[str]) -> None:
    d.add(Rect(x, y, width, height, rx=10, ry=10, fillColor=PALE, strokeColor=BORDER))
    cursor = y + height - 35
    for text in wrap(title, width - 32, 22, 'Case-Bold'):
        label(d, x + 16, cursor, text, 22, True, ACCENT)
        cursor -= 27
    cursor -= 9
    for text in lines:
        for part in wrap(text, width - 32, 19):
            if cursor < y + 14:
                raise ValueError(f'Переполнение схемы: {title}')
            label(d, x + 16, cursor, part, 19)
            cursor -= 26
        cursor -= 7


def diagrams() -> dict[str, Drawing]:
    overview = Drawing(960, 385)
    label(overview, 12, 348, 'Одно рабочее место — независимый учёт', 29, True)
    for x, title, lines in [
        (12, 'Конфигурация', ['Какие ОС установлены', 'Windows / Astra + Windows / только Astra', 'Нет сведений — отдельное состояние']),
        (332, 'Работы', ['Установка Astra', 'Отдельный вывод Windows', 'Причина ожидания, исполнитель и контроль']),
        (652, 'Инциденты', ['Какая функция нарушена', 'Кто восстанавливает работу', 'Собственные сроки и подтверждение решения']),
    ]:
        card(overview, x, 51, 296, 265, title, lines)
    label(overview, 12, 16, 'Закрытие установки не закрывает другие обязательства.', 23, True, ACCENT)
    process = Drawing(960, 550)
    steps = [
        ('01', 'Список волны и связанные задачи', 'Аналитик сверяет сведения и связи записей.'),
        ('02', 'Удалённая установка или ручные работы', 'Автоматизация устанавливает удалённо; инженер — вручную.'),
        ('03', 'Подтверждение установленной Astra', 'Фиксируются результат, источник и время, а не отправка задания.'),
        ('04', 'Учёт сохранённой Windows', 'При двойной загрузке остаётся отдельная задача вывода Windows.'),
        ('05', 'Контроль оставшихся обязательств', 'Инциденты — отдельно. Вывод Windows — по команде сопровождения ПО.'),
    ]
    for i, (number, title, detail) in enumerate(steps):
        y = 458 - i * 108
        process.add(Rect(78, y, 870, 83, rx=8, ry=8, fillColor=PALE, strokeColor=BORDER))
        label(process, 12, y + 36, number, 29, True, ACCENT)
        label(process, 96, y + 51, title, 23, True)
        label(process, 96, y + 19, detail, 19)
        if i < 4:
            process.add(Line(506, y, 506, y - 20, strokeColor=ACCENT, strokeWidth=2))
            process.add(Polygon([500, y - 14, 512, y - 14, 506, y - 22], fillColor=ACCENT, strokeColor=ACCENT))
    return {'01-модель-учёта': overview, '02-процесс-работ': process}


def pages(v: dict, data: dict) -> list[list[tuple]]:
    total = v['всего']
    share = 'не применяется' if not total else f"{100 * v['установлено'] / total:.1f}%".replace('.', ',')
    stamp = datetime.fromisoformat(data['момент_среза']).strftime('%d.%m.%Y, %H:%M')
    return [
        [
            ('title', 'Сопровождение миграции на Astra Linux'),
            ('lead', 'Даниил Рогулин · Кейс системного аналитика'),
            ('note', 'Проектное решение по заданным условиям. Банк и площадки обезличены; производственное внедрение и фактический эффект не заявлены.'),
            ('h2', 'Задача и исходные условия'),
            ('p', 'Организовать учёт работ и взаимодействие подразделений при переходе рабочих мест с Windows на Astra Linux. Первые списки уже выданы, сроки сжаты, площадки различаются по пользователям и ограничениям.'),
            ('p', '<b>Контур задачи:</b> головные офисы Москвы, включая удалённые рабочие места в этих офисах. Заданный диапазон — от 1 до 10 000 АРМ; это граница масштаба, а не выполненный объём.'),
            ('h2', 'Главная неоднозначность'),
            ('p', 'По исходному критерию установка Astra завершает миграцию даже при сохранении Windows. Такой результат нельзя приравнять ни к полному переходу, ни к отсутствию нарушений работы.'),
            ('h2', 'Выполненная аналитическая работа'),
            ('table', [['Что разработано', 'Для чего'], ['Модель объектов и состояний', 'Разделить конфигурацию, работы и инциденты.'], ['Требования и условия проверки', 'Сделать передачу работ и завершение задач однозначными.'], ['Правила отчётности и примеры', 'Показывать установленную Astra отдельно от остатка Windows.']]),
            ('p', '<b>Роль в решении:</b> анализ учёта, контроль исполнения и связь подразделений. Ресурсами семи кураторов управляет начальник; архитектуру и совместимость определяют профильные команды.'),
            ('small', '<b>Термины:</b> АРМ — автоматизированное рабочее место; ОС — операционная система; ПО — программное обеспечение. Service Desk — условное название существующей системы учёта и обработки обращений.'),
        ],
        [
            ('title', 'Процесс и ответственность'),
            ('lead', 'Общий учёт — без одинакового способа работы для всех площадок'),
            ('diagram', '02-процесс-работ', 'Схема последовательности действий. Специальная система обозначений не используется.'),
            ('p', '<b>Ручные работы:</b> инженеру передаются причина, сведения о предыдущей попытке и требуемое действие. Организация ресурсов проходит через начальника и куратора; согласованный ручной маршрут возможен сразу.'),
            ('p', '<b>Нет результата:</b> автоматизация уточняет состояние текущей попытки. Отсутствие ответа не служит основанием ни для закрытия установки, ни для автоматического повтора операции.'),
            ('p', '<b>Нарушена работа:</b> регистрируется связанный инцидент по действующим правилам. Передача обращения другой группе не означает восстановления сервиса.'),
            ('small', 'Площадки сохраняют свои способы выполнения работ. Для закрытого контура в общую сводку попадают только разрешённые сведения; при удалённой работе учитывается целевое АРМ, а не устройство подключения.'),
            ('links', [('Полный процесс', 'документы/03-процесс-работ.md'), ('Участники и ответственность', 'документы/02-участники-и-ответственность.md')]),
        ],
        [
            ('title', 'Модель учёта'),
            ('lead', 'Установка завершена — другие задачи могут оставаться открытыми'),
            ('diagram', '01-модель-учёта', 'Связи реализуются штатными средствами Service Desk. Новая информационная система не предлагается.'),
            ('h2', 'Что меняется в учёте'),
            ('table', [['Объект', 'Правило'], ['Участие АРМ в волне', 'Пара «волна + АРМ» уникальна. Повторная попытка не увеличивает число мигрированных мест.'], ['Фактическая конфигурация', 'Есть источник и время подтверждения. Неизвестное состояние не записывается как Windows.'], ['Задача вывода Windows', 'Связана с АРМ, причинами сохранения Windows, решением сопровождения ПО и результатом работ.'], ['Инцидент', 'Имеет собственные сроки и подтверждение восстановления. Может затрагивать несколько АРМ.']]),
            ('h2', 'Почему не одна задача со статусом «Готово»'),
            ('p', 'Один общий статус смешивает разные факты: ОС установлена, Windows сохранена, рабочая функция нарушена. Раздельный учёт позволяет завершить установку по исходному критерию и сохранить контроль оставшихся обязательств.'),
            ('small', '<b>Dualboot — двойная загрузка:</b> на компьютере сохранены обе операционные системы. Полный переход подтверждается состоянием «только Astra», а не фактом выдачи команды.'),
            ('links', [('Объекты и состояния', 'документы/04-учёт-и-состояния.md'), ('Контроль двойной загрузки', 'документы/06-двойная-загрузка.md')]),
        ],
        [
            ('title', 'От риска к проверяемому правилу'),
            ('lead', 'Вымышленный пример DEMO-ARM-004: две зависимости от ПО'),
            ('p', '<b>Исходная ситуация:</b> Astra и Windows установлены вместе. Приложение А готово к работе в новой среде, по Приложению Б готовность не подтверждена. Задача установки завершена.'),
            ('table', [['Шаг анализа', 'Решение в кейсе'], ['Риск', 'Закрытая установка скроет незавершённый переход; готовность одного приложения ошибочно примут за готовность всего АРМ.'], ['Выбор', 'Отдельная задача вывода Windows и отдельный учёт каждой зависимости.'], ['Почему не общий признак', 'Поле «ПО готово» не показывает, какая именно функция ещё требует Windows.'], ['Проверка', 'Попытка запланировать вывод Windows при неснятой зависимости должна быть отклонена проверкой примера.']]),
            ('h2', 'Связь с требованиями'),
            ('table', [['Код', 'Проверяемое правило'], ['ТР-08', 'Задача вывода Windows остаётся открытой после завершения установки.'], ['ТР-09', 'У одного АРМ может быть несколько независимых причин сохранения Windows.'], ['ТР-10', 'Команда сопровождения ПО применима к этому АРМ и нужным зависимостям.'], ['ТР-11', 'Завершение подтверждается результатом работ, а не командой.']]),
            ('note', 'Результат для DEMO-ARM-004: установка завершена; конфигурация — Astra + Windows; задача DEMO-WIN-004 ожидает готовности ПО. Следующее действие — получить решение по Приложению Б.'),
            ('small', 'Отдельно проверяются отсутствие команды, команда для другого АРМ и преждевременное закрытие вывода Windows. Это проверки логики примера, а не испытания банковской системы.'),
            ('links', [('Все требования', 'документы/05-требования.md'), ('Разборы ситуаций', 'примеры/01-разборы-ситуаций.md'), ('Программа проверки', 'документы/10-проверка-правил.md')]),
        ],
        [
            ('title', 'Результат подготовки и проверка'),
            ('lead', 'Подготовленное решение, не заявленный эффект внедрения'),
            ('p', 'Результат — согласованная между документами модель процесса, объектов, состояний и требований. Рабочие формы показывают, какие сведения нужны участникам; программа сверяет пример и расчёт сводки.'),
            ('h2', 'Демонстрационная сводка'),
            ('small', f'Срез вымышленной волны: {stamp} (часовой пояс +03:00). Это не данные банка.'),
            ('table', [['Показатель', 'Значение'], ['АРМ в волне', str(total)], ['Только Astra', str(v['астра'])], ['Astra + Windows', str(v['двойная'])], ['Только Windows', str(v['windows'])], ['Конфигурация не подтверждена', str(v['неизвестно'])], ['Astra установлена сейчас', f"{v['установлено']} из {total} — {share}"], ['Исторически установка подтверждалась', str(v['история'])], ['Открытые инциденты', str(v['инциденты'])]]),
            ('p', 'Историческая установка не подменяет текущую конфигурацию: в примере одно АРМ вернулось к Windows. Инциденты считаются отдельно и не складываются с количеством установленных ОС.'),
            ('h2', 'Как проверено'),
            ('p', 'Проверка исходного кейса сверяет ссылки, данные и сводку, а также выполняет 17 положительных и отрицательных проверок примера. Проверка представления дополнительно сверяет показатели PDF с исходными данными, ссылки, число страниц и целостность файлов.'),
            ('h2', 'Границы доказательства'),
            ('p', 'Подтверждена логика подготовленных материалов. Не заявлены настройка реального Service Desk, проверка совместимости Astra, миграция 10 000 АРМ или измеренное сокращение простоев. Производственное применение требует согласований владельцев процессов.'),
            ('links', [('Репозиторий и автор', ''), ('Исходные данные', 'примеры/02-данные.json'), ('Полная сводка', 'примеры/03-сводка.md'), ('Обоснование и ограничения', 'документы/11-представление-кейса.md')]),
        ],
    ]


def href(path: str) -> str:
    return REPO if not path else REPO + '/blob/main/' + quote(path, safe='/')


def markdown(text: str) -> str:
    return html.unescape(text.replace('<b>', '**').replace('</b>', '**'))


def export_markdown(content: list[list[tuple]]) -> str:
    lines = ['<!-- Создано программой собрать.py; содержимое задаётся в функции pages. -->', '']
    for i, page in enumerate(content):
        if i:
            lines += ['---', '']
        for block in page:
            kind = block[0]
            if kind in {'title', 'h2'}:
                lines += [('## ' if kind == 'h2' or i else '# ') + block[1], '']
            elif kind == 'table':
                rows = block[1]
                lines += ['| ' + ' | '.join(markdown(x) for x in rows[0]) + ' |', '|' + '---|' * len(rows[0])]
                lines += ['| ' + ' | '.join(markdown(x) for x in row) + ' |' for row in rows[1:]]
                lines += ['']
            elif kind == 'diagram':
                lines += [f'![{block[2]}](../схемы/{block[1]}.png)', '', block[2], '']
            elif kind == 'links':
                lines += [' · '.join(f'[{title}]({"../" + path if path else "../README.md"})' for title, path in block[1]), '']
            else:
                lines += [('> ' if kind == 'note' else '') + markdown(block[1]), '']
    return '\n'.join(lines)


def build_pdf(content: list[list[tuple]], figures: dict[str, Drawing], destination: Path) -> None:
    width, height = A4
    body_width = width - 84
    styles = {
        'title': ParagraphStyle('Title', fontName='Case-Bold', fontSize=24, leading=29, textColor=INK, spaceAfter=11),
        'lead': ParagraphStyle('Lead', fontName='Case', fontSize=11, leading=16, textColor=ACCENT, spaceAfter=16),
        'h2': ParagraphStyle('H2', fontName='Case-Bold', fontSize=13, leading=18, textColor=INK, spaceBefore=10, spaceAfter=7, keepWithNext=True),
        'p': ParagraphStyle('Body', fontName='Case', fontSize=10, leading=15, textColor=INK, spaceAfter=9),
        'small': ParagraphStyle('Small', fontName='Case', fontSize=8.7, leading=12.5, textColor=MUTED, spaceAfter=9),
        'note': ParagraphStyle('Note', fontName='Case', fontSize=10, leading=15, textColor=INK, borderColor=BORDER, borderWidth=.7, borderPadding=10, backColor=PALE, spaceBefore=9, spaceAfter=16),
        'cell': ParagraphStyle('Cell', fontName='Case', fontSize=9, leading=13, textColor=INK),
        'head': ParagraphStyle('Head', fontName='Case-Bold', fontSize=9, leading=13, textColor=colors.white),
    }
    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(ACCENT)
        canvas.rect(42, height - 34, 25, 3, stroke=0, fill=1)
        canvas.setFont('Case', 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(76, height - 34, 'ДАНИИЛ РОГУЛИН  /  СИСТЕМНЫЙ АНАЛИЗ')
        canvas.setStrokeColor(BORDER)
        canvas.line(42, 42, width - 42, 42)
        canvas.drawString(42, 28, 'Astra Linux · Обезличенное проектное решение')
        canvas.drawRightString(width - 42, 28, f'{doc.page} / {len(content)}')
        canvas.restoreState()
    doc = BaseDocTemplate(str(destination), pagesize=A4, title='Даниил Рогулин — сопровождение миграции на Astra Linux', author='Даниил Рогулин', subject='Портфельный кейс системного аналитика. Проектное решение.', pageCompression=1)
    doc.addPageTemplates(PageTemplate(id='case', frames=[Frame(42, 57, body_width, height - 115, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=decorate))
    story = []
    for i, page in enumerate(content):
        if i:
            story.append(PageBreak())
        for block in page:
            kind = block[0]
            if kind in styles:
                story.append(Paragraph(block[1], styles[kind]))
            elif kind == 'table':
                cells = [[Paragraph(text, styles['head'] if r == 0 else styles['cell']) for text in row] for r, row in enumerate(block[1])]
                table = Table(cells, colWidths=[body_width * .34, body_width * .66], hAlign='LEFT')
                table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), INK), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PALE]), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7), ('LINEBELOW', (0, -1), (-1, -1), .5, BORDER)]))
                story.extend([table, Spacer(1, 10)])
            elif kind == 'diagram':
                drawing = figures[block[1]].copy()
                scale = body_width / drawing.width
                drawing.scale(scale, scale)
                drawing.width *= scale
                drawing.height *= scale
                story.extend([drawing, Paragraph(block[2], styles['small']), Spacer(1, 5)])
            elif kind == 'links':
                text = ' · '.join(f'<link href="{href(path)}" color="#146A70"><u>{html.escape(title)}</u></link>' for title, path in block[1])
                story.append(Paragraph(text, styles['small']))
    doc.build(story)
    with fitz.open(destination) as pdf:
        if len(pdf) != len(content):
            raise ValueError(f'Ожидалось {len(content)} страниц, получилось {len(pdf)}; проверьте компоновку.')


def main() -> None:
    fonts()
    OUT.mkdir(exist_ok=True)
    ASSETS.mkdir(exist_ok=True)
    data = json.loads((ROOT / 'примеры/02-данные.json').read_text(encoding='utf-8'))
    result = values(data)
    content = pages(result, data)
    figures = diagrams()
    for name, drawing in figures.items():
        renderSVG.drawToFile(drawing, str(ASSETS / f'{name}.svg'))
        with fitz.open(stream=renderPDF.drawToString(drawing), filetype='pdf') as image_pdf:
            image_pdf[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(ASSETS / f'{name}.png')
    (OUT / 'кейс.md').write_text(export_markdown(content), encoding='utf-8')
    build_pdf(content, figures, OUT / PDF_NAME)
    paths = [OUT / PDF_NAME, OUT / 'кейс.md'] + [ASSETS / f'{name}.{ext}' for name in figures for ext in ('svg', 'png')]
    manifest = {'страниц': len(content), 'показатели': result, 'файлы': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (OUT / 'проверка-сборки.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Создан PDF: {PDF_NAME}; страниц: {len(content)}. Созданы краткий текст и две схемы в SVG/PNG.')


if __name__ == '__main__':
    main()
