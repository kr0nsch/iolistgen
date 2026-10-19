# -*- coding: utf-8 -*-
"""Импорт объектов Persistent Variables из PLCopenXML в приложение проекта (CODESYS Scripting, IronPython 2.7).

Скрипт выполняет CODESYS без окна, его запускает ``tools_project/codesys_pvl.py`` (вручную не
запускается). Задание — JSON, путь к нему — в переменной окружения ``CDS_JOB``::

    {
      "tools_codesys": "<repo>/tools/codesys",   общие модули CODESYS шаблона (только импорт)
      "project": "<путь>.project",               проект cds.py
      "objects": [{"name": "GVL_Persist", "xml": "<путь>.xml"}],
      "result": "<путь>.json"                    итог (пишет cds.py: run_codesys)
    }

Объект, который уже есть в приложении (любая папка), не трогается; недостающий импортируется
``Application.import_xml`` и проверяется поиском по дереву. Проект сохраняется, только если что-то
создано. Синтаксис — общее подмножество Python 2.7 и 3.x.
"""

from __future__ import absolute_import, print_function, unicode_literals

import io
import json
import os
import sys
import traceback

JOB_ENV = 'CDS_JOB'


def load_job():
    path = os.environ.get(JOB_ENV)
    if not path or not os.path.isfile(path):
        raise RuntimeError('нет файла задания (переменная %s): запускайте через tools_project/codesys_pvl.py' % JOB_ENV)
    with io.open(path, encoding='utf-8') as handle:
        return json.loads(handle.read())


JOB = load_job()
sys.path.insert(0, JOB['tools_codesys'])

import cds_common as C  # noqa: E402

SE = C.api()


class Reporter(SE.ImportReporter):
    """Сообщения импорта PLCopenXML; конфликт имён — пропуск (объект уже есть)."""

    def __init__(self):
        self.messages = []

    def error(self, message):
        self.messages.append({'level': 'error', 'text': C._text(message)})

    def warning(self, message):
        self.messages.append({'level': 'warning', 'text': C._text(message)})

    def resolve_conflict(self, obj):
        self.messages.append({'level': 'conflict', 'text': C.obj_name(obj)})
        return SE.ConflictResolve.Skip

    def added(self, obj):
        self.messages.append({'level': 'added', 'text': C.obj_name(obj)})

    def replaced(self, obj):
        self.messages.append({'level': 'replaced', 'text': C.obj_name(obj)})

    def skipped(self, objectname):
        self.messages.append({'level': 'skipped', 'text': C._text(objectname)})

    @property
    def aborting(self):
        return False


def find_persistent(container, name):
    """Объект Persistent Variables с именем name где угодно под container (без учёта регистра)."""
    for obj in C.children(container):
        if C.kind_of(obj) == C.K_PVL and C.obj_name(obj).lower() == name.lower():
            return obj
        found = find_persistent(obj, name)
        if found is not None:
            return found
    return None


def main():
    result = {'ok': False, 'created': [], 'existing': [], 'messages': []}
    code = 1
    proj = None
    try:
        path = JOB['project']
        C.check_project_lock(path)
        C.remove_precompile_cache(path)
        proj = SE.projects.open(path)
        C.load_object_tree(proj)
        app = C.application(proj)
        for item in JOB['objects']:
            name = item['name']
            if find_persistent(app, name) is not None:
                result['existing'].append(name)
                continue
            reporter = Reporter()
            app.import_xml(reporter, item['xml'], True)
            result['messages'].extend(reporter.messages)
            if find_persistent(app, name) is None:
                raise RuntimeError('после импорта %s объекта Persistent Variables %s в приложении нет' % (item['xml'], name))
            result['created'].append(name)
        if result['created']:
            proj.save()
        result['ok'] = True
        code = 0
    except Exception:
        result['error'] = C._text(traceback.format_exc())
    finally:
        if proj is not None:
            try:
                proj.close()
            except Exception:
                pass
        result['exit_code'] = code
        C.write_json(JOB['result'], result)
    sys.exit(code)


main()
