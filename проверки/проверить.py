"""Проверка вымышленного примера. Нет сети, установки ОС и изменения файлов.

Запуск из любой папки: python путь/к/репозиторию/проверки/проверить.py
Python 3.10 или новее; используются только стандартные библиотеки.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = {"Windows", "Astra + Windows", "Только Astra", "Не подтверждено"}
ASTRA = {"Astra + Windows", "Только Astra"}
TASK_STATES = {"Запланирована", "Удалённая установка", "Ручные работы", "Ожидание решения", "Завершена", "Прекращена"}
FINAL_TASK = {"Завершена", "Прекращена"}
REMOVAL_STATES = {"Ожидание готовности ПО", "Готово к организации работ", "Запланировано", "Выполняется", "Ожидание устранения препятствия", "Завершено"}
NEEDS_COMMAND = {"Готово к организации работ", "Запланировано", "Выполняется", "Завершено"}
EVENT_TYPES = {"Установка", "Сверка", "Восстановление", "Вывод Windows"}


def moment(value: str) -> datetime:
    """Разобрать время; часовой пояс обязателен для однозначного сравнения."""
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("В дате не указан часовой пояс")
    return result


def validate(data: dict[str, Any]) -> list[str]:
    """Проверить именно сокращённую схему примера, не реальный Service Desk."""
    errors: list[str] = []
    if data.get("версия_формата") != 1:
        return ["Неподдерживаемая версия формата"]
    for key in ("арм", "события", "инциденты"):
        if not isinstance(data.get(key), list):
            errors.append(f"Поле {key}: требуется список")
    if not isinstance(data.get("волна"), dict) or errors:
        return errors or ["Отсутствует описание волны"]
    cutoff = moment(data["момент_среза"])
    arms = data["арм"]
    ids = [row["номер"] for row in arms]
    known = set(ids)
    if len(ids) != len(known):
        errors.append("Дубль АРМ в составе волны")
    wave = data["волна"]
    if wave.get("число_арм") != len(arms):
        errors.append("Объём версии волны не совпадает с числом строк")
    if not wave.get("основание") or not wave.get("номер") or not isinstance(wave.get("версия"), int):
        errors.append("Не заполнены источник, номер или версия волны")

    def check_time(value: Any, label: str, past: bool = False) -> datetime | None:
        try:
            parsed = moment(value)
        except (TypeError, ValueError):
            errors.append(f"{label}: нет корректного времени с часовым поясом")
            return None
        if past and parsed > cutoff:
            errors.append(f"{label}: событие позже среза")
        return parsed

    def next_action(record: dict[str, Any], label: str) -> None:
        if not record.get("группа"):
            errors.append(f"{label}: нет группы следующего действия")
        if not record.get("следующее_действие"):
            errors.append(f"{label}: нет следующего действия")
        check_time(record.get("контроль"), f"{label}: контроль")

    event_ids = [e["номер"] for e in data["события"]]
    if len(event_ids) != len(set(event_ids)):
        errors.append("Дубль события")
    events = {e["номер"]: e for e in data["события"]}
    event_times: dict[str, datetime] = {}
    for number, event in events.items():
        if event.get("арм") not in known:
            errors.append(f"{number}: неизвестное АРМ в событии")
        if event.get("тип") not in EVENT_TYPES:
            errors.append(f"{number}: неизвестный тип события")
        if event.get("конфигурация") not in CONFIGS - {"Не подтверждено"}:
            errors.append(f"{number}: недопустимая подтверждённая конфигурация")
        if not event.get("источник"):
            errors.append(f"{number}: нет источника подтверждения")
        timestamp = check_time(event.get("время"), number, past=True)
        if timestamp is not None:
            event_times[number] = timestamp
        if event.get("тип") == "Установка":
            if event.get("конфигурация") not in ASTRA or not event.get("задача"):
                errors.append(f"{number}: установка не подтверждает Astra и связанную задачу")
        if event.get("тип") == "Вывод Windows" and event.get("конфигурация") != "Только Astra":
            errors.append(f"{number}: вывод Windows не подтверждён")

    task_ids: set[str] = set()
    for row in arms:
        number = row["номер"]
        config = row.get("конфигурация")
        if config not in CONFIGS:
            errors.append(f"{number}: неизвестная конфигурация")
        basis = events.get(row.get("основание"))
        if config == "Не подтверждено":
            if row.get("основание") is not None:
                errors.append(f"{number}: неподтверждённое состояние имеет активное подтверждение")
        elif basis is None:
            errors.append(f"{number}: нет основания конфигурации")
        else:
            if basis.get("арм") != number or basis.get("конфигурация") != config:
                errors.append(f"{number}: основание не совпадает с конфигурацией или АРМ")
            available = [e for e in events.values() if e.get("арм") == number and e["номер"] in event_times and event_times[e["номер"]] <= cutoff]
            if available:
                latest = max(available, key=lambda e: event_times[e["номер"]])
                if basis["номер"] != latest["номер"]:
                    errors.append(f"{number}: выбрано не последнее подтверждение конфигурации")

        task = row["работа"]
        task_number = task["номер"]
        if task_number in task_ids:
            errors.append(f"{number}: дубль номера задачи")
        task_ids.add(task_number)
        if task.get("состояние") not in TASK_STATES:
            errors.append(f"{task_number}: неизвестное состояние работы")
        if task.get("состояние") not in FINAL_TASK:
            next_action(task, task_number)
        if task.get("состояние") == "Ожидание решения" and not task.get("причина"):
            errors.append(f"{task_number}: ожидание без причины")
        if task.get("состояние") == "Прекращена" and not task.get("основание_прекращения"):
            errors.append(f"{task_number}: прекращение без решения")
        if task.get("состояние") == "Завершена":
            proof = events.get(task.get("подтверждение"))
            if not proof or proof.get("тип") != "Установка" or proof.get("арм") != number or proof.get("задача") != task_number:
                errors.append(f"{task_number}: нет подтверждения установки для этой задачи")

        removal = row.get("вывод_windows")
        if config == "Astra + Windows" and not removal:
            errors.append(f"{number}: нет задачи вывода Windows")
        if removal is None:
            continue
        removal_number = removal["номер"]
        if removal_number in task_ids:
            errors.append(f"{number}: дубль номера задачи вывода Windows")
        task_ids.add(removal_number)
        state = removal.get("состояние")
        if state not in REMOVAL_STATES:
            errors.append(f"{removal_number}: неизвестное состояние вывода Windows")
        if state != "Завершено":
            next_action(removal, removal_number)
        dependencies = removal.get("зависимости", [])
        if not dependencies:
            errors.append(f"{removal_number}: не учтена причина сохранения Windows")
        dep_ids = [d["номер"] for d in dependencies]
        if len(dep_ids) != len(set(dep_ids)):
            errors.append(f"{removal_number}: дубль зависимости")
        for dep in dependencies:
            if not dep.get("причина") or not dep.get("группа") or not isinstance(dep.get("готово"), bool):
                errors.append(f"{removal_number}: неполное описание зависимости")
            if dep.get("готово") and not dep.get("основание"):
                errors.append(f"{removal_number}: зависимость снята без основания")
        command = removal.get("команда")
        command_time = None
        if state in NEEDS_COMMAND:
            if not dependencies or not all(d.get("готово") is True for d in dependencies):
                errors.append(f"{removal_number}: осталась неснятая зависимость")
            if not command:
                errors.append(f"{removal_number}: отсутствует команда сопровождения ПО")
            else:
                if not command.get("номер") or command.get("источник") != "Сопровождение ПО":
                    errors.append(f"{removal_number}: не подтверждён источник команды")
                if number not in command.get("арм", []):
                    errors.append(f"{removal_number}: команда не относится к этому АРМ")
                if not set(dep_ids).issubset(set(command.get("зависимости", []))):
                    errors.append(f"{removal_number}: команда не покрывает все зависимости")
                command_time = check_time(command.get("время"), removal_number, past=True)
        if state == "Завершено":
            result = events.get(removal.get("результат"))
            if config != "Только Astra" or not result or result.get("тип") != "Вывод Windows" or result.get("арм") != number or row.get("основание") != removal.get("результат"):
                errors.append(f"{removal_number}: вывод Windows не подтверждён")
            elif command_time is not None and event_times.get(result["номер"], command_time) < command_time:
                errors.append(f"{removal_number}: результат получен до команды")

    incident_ids = [i["номер"] for i in data["инциденты"]]
    if len(incident_ids) != len(set(incident_ids)):
        errors.append("Дубль инцидента")
    for incident in data["инциденты"]:
        label = incident["номер"]
        affected = incident.get("арм", [])
        if not affected or not set(affected).issubset(known):
            errors.append(f"{label}: неизвестное или отсутствующее АРМ инцидента")
        if incident.get("состояние") == "Открыт":
            next_action(incident, label)
        elif incident.get("состояние") == "Завершён":
            if incident.get("основание_восстановления") not in events:
                errors.append(f"{label}: нет основания восстановления в примере")
        else:
            errors.append(f"{label}: неизвестное состояние инцидента")
    return errors


def metrics(data: dict[str, Any]) -> dict[str, int]:
    """Рассчитать один срез одной волны после успешной проверки данных."""
    rows = data["арм"]
    current = Counter(row["конфигурация"] for row in rows)
    historical = {e["арм"] for e in data["события"] if e["тип"] == "Установка"}
    opened = [i for i in data["инциденты"] if i["состояние"] == "Открыт"]
    removals = [r["вывод_windows"] for r in rows if r.get("вывод_windows") and r["вывод_windows"]["состояние"] != "Завершено"]
    return {
        "всего": len(rows), "астра": current["Только Astra"], "двойная": current["Astra + Windows"],
        "windows": current["Windows"], "неизвестно": current["Не подтверждено"],
        "установлено": current["Только Astra"] + current["Astra + Windows"], "история": len(historical),
        "возврат": sum(r["номер"] in historical and r["конфигурация"] == "Windows" for r in rows),
        "инциденты": len(opened), "затронуто": len({a for i in opened for a in i["арм"]}),
        "работы": sum(r["работа"]["состояние"] not in FINAL_TASK for r in rows),
        "вывод": len(removals), "ожидание_по": sum(r["состояние"] == "Ожидание готовности ПО" for r in removals),
        "вывод_план": sum(r["состояние"] == "Запланировано" for r in removals),
    }


def percent(part: int, total: int) -> str:
    return "не применяется" if total == 0 else f"{100 * part / total:.1f}%".replace(".", ",")


def report_table(values: dict[str, int]) -> str:
    n = values["всего"]
    rows = [
        ("АРМ в волне", n), ("Только Astra", values["астра"]), ("Astra + Windows", values["двойная"]),
        ("Только Windows", values["windows"]), ("Конфигурация не подтверждена", values["неизвестно"]),
        ("Astra установлена сейчас", f'{values["установлено"]} из {n} — {percent(values["установлено"], n)}'),
        ("Только Astra, доля от волны", f'{values["астра"]} из {n} — {percent(values["астра"], n)}'),
        ("Исторически установка подтверждалась", values["история"]),
        ("Вернулись к Windows после установки Astra", values["возврат"]),
        ("Открытые инциденты", values["инциденты"]), ("АРМ с открытыми инцидентами", values["затронуто"]),
        ("Незавершённые задачи установки", values["работы"]), ("Открытые задачи вывода Windows", values["вывод"]),
        ("Из них ожидают готовности ПО", values["ожидание_по"]), ("Из них запланированы", values["вывод_план"]),
    ]
    return "\n".join(["| Показатель | Значение |", "|---|---:|"] + [f"| {name} | {value} |" for name, value in rows])


def check_links() -> tuple[int, list[str]]:
    errors: list[str] = []
    count = 0
    for source in sorted(ROOT.rglob("*.md")):
        text = source.read_text(encoding="utf-8")
        if len(re.findall(r"^```", text, re.MULTILINE)) % 2:
            errors.append(f"{source.relative_to(ROOT)}: незакрытый блок кода")
        for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", text):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            path = unquote(target.split("#", 1)[0])
            resolved = (source.parent / path).resolve()
            count += 1
            if not resolved.is_relative_to(ROOT) or not resolved.is_file():
                errors.append(f"{source.relative_to(ROOT)}: ссылка не найдена — {target}")
    return count, errors


def example_tests(original: dict[str, Any]) -> int:
    """Отрицательные и положительные проверки копий, без записи на диск."""
    checked = 0

    def reject(name: str, change: Callable[[dict[str, Any]], Any], fragment: str) -> None:
        nonlocal checked
        trial = deepcopy(original)
        change(trial)
        found = validate(trial)
        if not any(fragment in item for item in found):
            raise ValueError(f"Не обнаружена ошибка: {name}; получено: {found}")
        checked += 1

    reject("повтор АРМ", lambda d: d["арм"].append(deepcopy(d["арм"][0])), "Дубль АРМ")
    reject("повтор события", lambda d: d["события"].append(deepcopy(d["события"][0])), "Дубль события")
    reject("завершение без подтверждения", lambda d: d["арм"][0]["работа"].pop("подтверждение"), "нет подтверждения установки")
    reject("двойная загрузка без обязательства", lambda d: d["арм"][2].update({"вывод_windows": None}), "нет задачи вывода Windows")
    reject("частичная готовность ПО", lambda d: d["арм"][3]["вывод_windows"].update({"состояние": "Запланировано"}), "неснятая зависимость")
    reject("нет команды", lambda d: d["арм"][8]["вывод_windows"].update({"команда": None}), "отсутствует команда")
    reject("команда для другого АРМ", lambda d: d["арм"][8]["вывод_windows"]["команда"].update({"арм": ["DEMO-ARM-001"]}), "команда не относится")
    reject("команда не покрывает зависимость", lambda d: d["арм"][8]["вывод_windows"]["команда"].update({"зависимости": []}), "не покрывает")
    reject("преждевременный вывод Windows", lambda d: d["арм"][8]["вывод_windows"].update({"состояние": "Завершено"}), "вывод Windows не подтверждён")
    reject("ожидание без ответственного", lambda d: d["арм"][5]["работа"].update({"группа": ""}), "нет группы")
    reject("неизвестное превращено в Windows", lambda d: d["арм"][6].update({"конфигурация": "Windows"}), "нет основания конфигурации")
    reject("событие из будущего среза", lambda d: d["события"][0].update({"время": "2026-10-09T12:00:00+03:00"}), "позже среза")
    reject("игнорирование возврата Windows", lambda d: d["арм"][11].update({"конфигурация": "Только Astra", "основание": "DEMO-EVT-012"}), "не последнее")
    reject("неизвестное АРМ инцидента", lambda d: d["инциденты"][0].update({"арм": ["DEMO-NOT-FOUND"]}), "неизвестное или отсутствующее")

    # Один инцидент может затрагивать несколько АРМ, включая успешно установленные.
    common = deepcopy(original)
    common["инциденты"][0]["арм"].append("DEMO-ARM-001")
    if validate(common) or metrics(common)["инциденты"] != 1 or metrics(common)["затронуто"] != 2:
        raise ValueError("Не пройдена проверка общего инцидента")
    checked += 1

    # Пустой список не вызывает деление на ноль и не превращается в 100%.
    empty = deepcopy(original)
    empty.update({"арм": [], "события": [], "инциденты": []})
    empty["волна"]["число_арм"] = 0
    if validate(empty) or metrics(empty)["всего"] != 0 or percent(0, 0) != "не применяется":
        raise ValueError("Не пройдена проверка пустой волны")
    checked += 1

    # Полное завершение после команды: новое событие, а не переименование старого.
    finished = deepcopy(original)
    row = finished["арм"][8]
    event = {"номер": "DEMO-EVT-009-FINISH", "арм": row["номер"], "тип": "Вывод Windows", "конфигурация": "Только Astra", "время": "2026-10-08T11:50:00+03:00", "источник": "Инженер сопровождения"}
    finished["события"].append(event)
    row.update({"конфигурация": "Только Astra", "основание": event["номер"]})
    row["вывод_windows"].update({"состояние": "Завершено", "результат": event["номер"]})
    if validate(finished) or metrics(finished)["вывод"] != 2 or metrics(finished)["астра"] != 5:
        raise ValueError("Не пройдена проверка подтверждённого вывода Windows")
    checked += 1
    return checked


def main() -> int:
    try:
        data = json.loads((ROOT / "примеры/02-данные.json").read_text(encoding="utf-8"))
        errors = validate(data)
        link_count, link_errors = check_links()
        errors.extend(link_errors)
        if errors:
            print("Проверка не пройдена:")
            for error in errors:
                print(f"- {error}")
            return 1
        values = metrics(data)
        table = report_table(values)
        report = (ROOT / "примеры/03-сводка.md").read_text(encoding="utf-8")
        if table not in report:
            raise ValueError("Таблица сводки не совпадает с расчётом по исходным данным")
        tests = example_tests(data)
        print(f"Проверено ссылок между файлами: {link_count}")
        print(f"Дополнительных проверок примеров пройдено: {tests}")
        print("Данные, подтверждения и таблица сводки согласованы.")
        print(table)
        return 0
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as error:
        print(f"Ошибка проверки: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
