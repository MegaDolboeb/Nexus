"""Запуск Nexus из командной строки (пока без панели).

  python -m nexus run [--segment 1500] [--rest 300] [--after 180] [--duration 0]
                                                                       работать (Ctrl+C — остановиться с сохранением)
  python -m nexus add-probe [частей] [тема]                            добавить проверочную задачу
  python -m nexus status                                               задачи и их состояние
  python -m nexus collect                                              один проход по всем источникам
  python -m nexus sources                                              состояние источников
  python -m nexus match [-n 20]                                        дешёвый отбор по темам (без модели)
  python -m nexus top [-n 20] [--all]                                  материалы, оценённые моделью
  python -m nexus reports [-n 10] [--topic ai]                         готовые выжимки
  python -m nexus credibility [-n 20]                                  группы материалов и их достоверность
  python -m nexus check "текст темы или поручения"                     проверка на подготовку вреда
  python -m nexus memory [-n 20] [--topic ai]                          темы в памяти
  python -m nexus memory-show <id>                                     одна тема: выводы, отчёт, история
  python -m nexus search "запрос" [-n 5] [--words-only]                поиск по памяти (смысл + слова)
  python -m nexus backup                                                резервная копия базы и настроек сейчас
  python -m nexus panel                                                 окно программы и иконка в трее
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from . import backup, config
from .engine import Engine, EngineBusy
from .memory.search import search as memory_search
from .memory.store import MemoryStore
from .priority_watch import PriorityWatch
from .safety import writable
from .sources.collector import Collector, load_sources
from .sources.store import ItemStore
from .jobs import make_jobs
from .research.credibility import LOW_RELIABILITY_BADGE
from .research.match import load_topics
from .research.planner import plan, plan_credibility, plan_digest, plan_memory
from .research.select import run_matching
from .supervisor import Supervisor
from .tasks import TaskStore


def setup_logging():
    path = writable(config.LOGS_DIR / "nexus.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S")
    file = logging.FileHandler(path, encoding="utf-8")
    file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file)
    root.addHandler(console)


def cmd_run(a):
    s = config.Settings(segment_s=a.segment, rest_s=a.rest, after_priority_s=a.after)
    store = TaskStore()
    n = store.recover_after_restart()
    if n:
        logging.info("после перезапуска прерванных задач: %d (продолжатся с контрольной точки)", n)
    watch = PriorityWatch(settings=s)
    try:
        engine = Engine(s).claim()
    except EngineBusy:
        logging.error("движком уже пользуется другая программа Nexus (замер или второй Nexus). Выход.")
        return
    items, sources, topics, memory = ItemStore(), load_sources(), load_topics(), MemoryStore()
    sup = Supervisor(store, watch, engine, settings=s, jobs=make_jobs(items, topics, sources, memory))
    collector = Collector(items, sources)
    logging.info("Nexus работает. Отрезок %.0f с, пауза %.0f с, после занятости ждём %.0f с. Ctrl+C — стоп.",
                 s.segment_s, s.rest_s, s.after_priority_s)
    end = time.monotonic() + a.duration if a.duration else None
    next_collect = 0.0
    try:
        while end is None or time.monotonic() < end:
            sup.tick()
            if time.monotonic() >= next_collect:
                next_collect = time.monotonic() + 60
                for sid, msg in collector.run_due(lambda: watch.check().may_work).items():
                    logging.info("источник %s: %s", sid, msg)
                counts = run_matching(items, topics, sources)
                if counts["MATCHED"]:
                    logging.info("отбор по темам: подошло %d, мимо %d", counts["MATCHED"], counts["SKIPPED"])
                tid = plan(store, items)
                if tid:
                    logging.info("новая задача оценки: %d", tid)
                did = plan_digest(store, items)
                if did:
                    logging.info("новая задача выжимки: %d", did)
                cid = plan_credibility(store, items, sources)
                if cid:
                    logging.info("новая задача достоверности: %d", cid)
                mid = plan_memory(store, items, memory)
                if mid:
                    logging.info("новая задача памяти: %d", mid)
                if backup.due():
                    out = backup.backup_now()
                    logging.info("резервная копия сохранена: %s", out)
            time.sleep(s.watch_every_s)
        logging.info("время работы вышло, остановка с сохранением…")
        sup.shutdown("заданное время работы вышло")
    except KeyboardInterrupt:
        logging.info("остановка с сохранением…")
        sup.shutdown("Давид остановил Nexus")
    for y in sup.yields:
        logging.info("уступка: %-40s %.1f с, видеопамять %s", y.reason, y.total_s, "свободна" if y.released else "НЕ подтверждена")


def cmd_collect(a):
    """Один проход по источникам (всем, а не только тем, кому пора), с проверкой приоритетной программы."""
    store = ItemStore()
    watch = PriorityWatch()
    collector = Collector(store, load_sources())
    for s in collector.sources:
        if not watch.check().may_work:
            print("приоритетная программа занята — сбор остановлен")
            break
        print(f"{s.name:<32} {collector.run_one(s)}")
    print(f"всего в базе: {store.count()}")


def cmd_sources(a):
    store = ItemStore()
    for s in load_sources():
        st = store.status(s.id)
        when = time.strftime("%d.%m %H:%M", time.localtime(st.last_ok)) if st.last_ok else "никогда"
        print(f"{s.name:<32} {'ok ' if st.ok else 'ОШИБКА'} последний успех: {when:<12} материалов: {store.count(s.id):<4} {st.error}")


def cmd_match(a):
    """Дешёвый отбор по темам для всех новых материалов (без модели) и лучшие кандидаты."""
    items = ItemStore()
    print(run_matching(items, load_topics(), load_sources()))
    print("состояния:", items.state_counts())
    for c in items.top_matched(limit=a.n):
        print(f"{c['score']:.2f} {c['topic_id']:<12} {c['source_id']:<16} {c['title'][:90]}")


def cmd_top(a):
    """Оценённые моделью материалы."""
    for r in ItemStore().scored(state=None if a.all else "SELECTED", limit=a.n):
        print(f"{r['state']:<9} {r['topic_id']:<12} знач {r['significance']} нов {r['novelty']} "
              f"тема {r['relevance']} слож {r['complexity']} | {r['title'][:70]}\n{'':10}{r['why']}")


def cmd_reports(a):
    """Готовые выжимки."""
    for r in ItemStore().reports(topic_id=a.topic, limit=a.n):
        when = time.strftime("%d.%m %H:%M", time.localtime(r["at"]))
        print(f"--- {r['title']} ({r['source_id']}, {when}) {r['url']}")
        print(r["text"])
        print()


def cmd_credibility(a):
    """Группы материалов с их статусом достоверности."""
    for r in ItemStore().credibility_report(limit=a.n):
        when = time.strftime("%d.%m %H:%M", time.localtime(r["at"]))
        badge = f" [{LOW_RELIABILITY_BADGE}]" if r["low_reliability"] else ""
        print(f"{r['status']:<13}{badge} {r['topic_id']:<12} {when} — {r['reason']}")
        for m in r["members"]:
            print(f"    {m['source_id']:<16} {m['title'][:80]}")


def cmd_check(a):
    """Проверка свободной темы/поручения на подготовку вреда — разовый вызов, как инструмент замера:
    сам занимает движок (если нужна модель) и уважает приоритетную программу, но не через фоновый
    цикл Supervisor."""
    from .research.guardrails import VERDICT_SCHEMA, classify

    def ask_model(messages):
        if not PriorityWatch().check().may_work:
            raise RuntimeError("приоритетная программа сейчас занята — проверка отложена, попробуйте чуть позже")
        try:
            eng = Engine().claim()
        except EngineBusy as e:
            raise RuntimeError(f"движок Nexus занят: {e}") from e
        try:
            eng.start()
            model = config.Settings().work_model
            out = []
            for piece in eng.chat_stream(model, messages, {"temperature": 0.1, "num_predict": 150},
                                         keep_alive="0", fmt=VERDICT_SCHEMA):
                out.append(piece)
            return "".join(out)
        finally:
            try:
                eng.unload_all()
            except Exception:                                   # noqa: BLE001
                pass
            eng.stop()

    try:
        v = classify(a.text, ask_model)
    except RuntimeError as e:
        print(str(e))
        return
    print(f"{v.decision} ({v.source}): {v.reason}")


def cmd_memory(a):
    """Темы в памяти."""
    store = MemoryStore()
    rows = store.all_for_interest(a.topic) if a.topic else store.all(limit=a.n)
    for t in rows[:a.n]:
        badge = f" [{LOW_RELIABILITY_BADGE}]" if t.low_reliability else ""
        when = time.strftime("%d.%m %H:%M", time.localtime(t.updated))
        print(f"{t.id:>4} {t.interest_topic_id:<10} {t.credibility_status or '?':<13}{badge} {when} — {t.title[:70]}")
        print(f"     {t.conclusions[:200]}")
        if t.related:
            print(f"     связано с: {t.related}")


def cmd_memory_show(a):
    store = MemoryStore()
    t = store.get(a.id)
    print(f"# {t.title}\n\nТема: {t.interest_topic_id}  Достоверность: {t.credibility_status}"
          f"{' [' + LOW_RELIABILITY_BADGE + ']' if t.low_reliability else ''}\n")
    print("## Выводы\n" + t.conclusions)
    print("\n## Подробный отчёт\n" + t.report)
    hist = store.history(a.id)
    if hist:
        print(f"\n## История изменений ({len(hist)})")
        for at, gist, concl, reason in hist:
            print(f"- {time.strftime('%d.%m %H:%M', time.localtime(at))}: {reason}")


def cmd_search(a):
    """Поиск по памяти: по смыслу и по словам. Эмбеддинг запроса — разовый вызов движка, как nexus check."""
    store = MemoryStore()
    embedding = []

    def embed_query():
        if not PriorityWatch().check().may_work:
            print("приоритетная программа сейчас занята — поищу пока только по словам")
            return []
        try:
            eng = Engine().claim()
        except EngineBusy:
            print("движок Nexus занят — поищу пока только по словам")
            return []
        try:
            eng.start()
            vecs = eng.embed(config.Settings().embed_model, [a.query], keep_alive="0")
            return vecs[0] if vecs else []
        finally:
            try:
                eng.unload_all()
            except Exception:                                   # noqa: BLE001
                pass
            eng.stop()

    if not a.words_only:
        embedding = embed_query()
    outcome = memory_search(store, a.query, embedding or None, limit=a.n)
    if outcome.ambiguous:
        print(outcome.question)
    for r in outcome.results:
        print(f"{r.score:.2f} ({r.via}) #{r.topic.id} {r.topic.title[:80]}")


def cmd_panel(a):
    """Окно программы и иконка в трее (настоящее окно Windows, не браузер)."""
    from .panel.window import run as run_window
    run_window()


def cmd_backup(a):
    out = backup.backup_now()
    print("резервная копия сохранена:", out)


def cmd_lock_integrity(a):
    """Зафиксировать текущие контрольные суммы защищённых файлов как «правильные».
    Запускать после КАЖДОГО настоящего изменения этих файлов."""
    from . import integrity
    integrity.write_lock()
    print("замок обновлён:", integrity.LOCK_FILE)
    for rel in integrity.PROTECTED_FILES:
        print(" ", rel)


def cmd_add_probe(a):
    tid = TaskStore().add("probe", f"Проверка: {a.topic}", {"parts": a.parts, "topic": a.topic})
    print(f"добавлена задача {tid}")


def cmd_status(a):
    for t in TaskStore().all():
        print(f"{t.id:>3} {t.state:<12} {t.title:<35} частей готово: {len(t.checkpoint.get('parts', []))}  {t.reason}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="nexus")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--segment", type=float, default=config.Settings.segment_s)
    r.add_argument("--rest", type=float, default=config.Settings.rest_s)
    r.add_argument("--after", type=float, default=config.Settings.after_priority_s)
    r.add_argument("--duration", type=float, default=0, help="секунд работы, потом остановка с сохранением")
    r.set_defaults(f=cmd_run)
    ap = sub.add_parser("add-probe")
    ap.add_argument("parts", type=int, nargs="?", default=5)
    ap.add_argument("topic", nargs="?", default="гуманоидные роботы")
    ap.set_defaults(f=cmd_add_probe)
    sub.add_parser("status").set_defaults(f=cmd_status)
    sub.add_parser("collect").set_defaults(f=cmd_collect)
    sub.add_parser("sources").set_defaults(f=cmd_sources)
    m = sub.add_parser("match")
    m.add_argument("-n", type=int, default=20)
    m.set_defaults(f=cmd_match)
    tp = sub.add_parser("top")
    tp.add_argument("-n", type=int, default=20)
    tp.add_argument("--all", action="store_true")
    tp.set_defaults(f=cmd_top)
    rp = sub.add_parser("reports")
    rp.add_argument("-n", type=int, default=10)
    rp.add_argument("--topic", default=None)
    rp.set_defaults(f=cmd_reports)
    cp = sub.add_parser("credibility")
    cp.add_argument("-n", type=int, default=20)
    cp.set_defaults(f=cmd_credibility)
    ck = sub.add_parser("check")
    ck.add_argument("text")
    ck.set_defaults(f=cmd_check)
    mp = sub.add_parser("memory")
    mp.add_argument("-n", type=int, default=20)
    mp.add_argument("--topic", default=None)
    mp.set_defaults(f=cmd_memory)
    ms = sub.add_parser("memory-show")
    ms.add_argument("id", type=int)
    ms.set_defaults(f=cmd_memory_show)
    sr = sub.add_parser("search")
    sr.add_argument("query")
    sr.add_argument("-n", type=int, default=5)
    sr.add_argument("--words-only", action="store_true", help="без эмбеддинга, только по словам")
    sr.set_defaults(f=cmd_search)
    sub.add_parser("backup").set_defaults(f=cmd_backup)
    sub.add_parser("panel").set_defaults(f=cmd_panel)
    sub.add_parser("lock-integrity").set_defaults(f=cmd_lock_integrity)
    a = p.parse_args(argv)
    if a.cmd == "run":
        setup_logging()
    a.f(a)


if __name__ == "__main__":
    main()
