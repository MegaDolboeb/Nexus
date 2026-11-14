"""Виды задач. Каждая задача — маленькие шаги; один шаг = одно узкое поручение модели.
Шаг получает прошлую контрольную точку и возвращает новую. Модель ничего не решает:
что делать и в каком порядке, задаёт код.
"""
from __future__ import annotations

import json

from .config import RESEARCH_MODES
from .research.digest import LANGUAGE_INSTRUCTION


class ProbeJob:
    """Проверочная задача: N коротких абзацев, по одному за шаг.
    Нужна, чтобы проверить уступку приоритетной программе и продолжение с контрольной точки на настоящей модели."""

    kind = "probe"

    def step(self, ctx, payload: dict, checkpoint: dict) -> tuple[dict, bool]:
        parts = list(checkpoint.get("parts", []))
        total = int(payload.get("parts", 5))
        if len(parts) >= total:
            return checkpoint, True
        topic = payload.get("topic", "роботы")
        prompt = (f"Напиши один короткий абзац (3–4 предложения) на русском о теме «{topic}», "
                  f"часть {len(parts) + 1} из {total}. Только абзац, без заголовка.")
        text = ctx.chat([{"role": "user", "content": prompt}], num_predict=200)
        parts.append(text.strip())
        return {"parts": parts}, len(parts) >= total


class TriageJob:
    """Оценка кандидатов моделью: один материал за шаг. Ответ модели — только числа по схеме;
    изучать или нет, решает код (research.select.decide)."""

    kind = "triage"

    def __init__(self, items, topics, sources):
        self.items = items
        self.topics = {t.id: t for t in topics}
        self.sources = {s.id: s for s in sources}

    def step(self, ctx, payload: dict, checkpoint: dict) -> tuple[dict, bool]:
        from .research.select import TRIAGE_SCHEMA, decide, parse_scores, triage_messages
        done = list(checkpoint.get("done", []))
        failed = list(checkpoint.get("failed", []))
        todo = [i for i in payload.get("item_ids", []) if i not in done and i not in failed]
        if not todo:
            return checkpoint, True
        item_id = todo[0]
        it = self.items.item(item_id)
        tops = [t for t in self.items.topics_of(item_id) if t[0] in self.topics]
        if not tops:
            self.items.set_state(item_id, "SKIPPED")
            done.append(item_id)
        else:
            topic = self.topics[tops[0][0]]
            src = self.sources.get(it["source_id"])
            msgs = triage_messages(topic, src.name if src else it["source_id"], it["title"], it["summary"])
            try:
                scores = parse_scores(ctx.chat(msgs, num_predict=200, fmt=TRIAGE_SCHEMA, temperature=0.1))
                self.items.save_score(item_id, topic.id, scores, ctx.model, decide(scores, topic.id))
                done.append(item_id)
            except (ValueError, KeyError, TypeError):
                failed.append(item_id)                       # кривой ответ модели: не выдумываем оценку
                self.items.set_state(item_id, "TRIAGE_FAILED")
        cp = {"done": done, "failed": failed}
        return cp, len(done) + len(failed) >= len(payload.get("item_ids", []))


class DigestJob:
    """Выжимка: один материал за шаг. Читает саму статью по ссылке, затем просит модель пересказать её
    по правилу подачи темы. Если статья не читается (сайт недоступен, нужен JavaScript и т. п.) —
    материал помечается FETCH_FAILED и пропускается, без выдуманной выжимки."""

    kind = "digest"

    def __init__(self, items, topics, sources, fetch_text=None):
        from .research.fetch_article import fetch_article_text
        self.items = items
        self.topics = {t.id: t for t in topics}
        self.sources = {s.id: s for s in sources}
        self.fetch_text = fetch_text or fetch_article_text

    def step(self, ctx, payload: dict, checkpoint: dict) -> tuple[dict, bool]:
        from .research.digest import digest_messages
        done = list(checkpoint.get("done", []))
        failed = list(checkpoint.get("failed", []))
        todo = [i for i in payload.get("item_ids", []) if i not in done and i not in failed]
        if not todo:
            return checkpoint, True
        item_id = todo[0]
        it = self.items.item(item_id)
        topic_id = payload.get("topics", {}).get(str(item_id))
        topic = self.topics.get(topic_id)
        if topic is None:
            self.items.set_state(item_id, "SKIPPED")
            done.append(item_id)
        else:
            try:
                text = self.fetch_text(it["url"])
            except Exception as e:                                   # noqa: BLE001 - один сайт не валит остальные
                self.items.set_state(item_id, "FETCH_FAILED")
                failed.append(item_id)
            else:
                src = self.sources.get(it["source_id"])
                mode = RESEARCH_MODES.get(ctx.settings.research_mode, RESEARCH_MODES["balanced"])
                msgs = digest_messages(topic, src.name if src else it["source_id"], it["title"], text,
                                       custom_instruction=ctx.settings.custom_instruction,
                                       language=getattr(ctx.settings, "language", "ru"))
                report = ctx.chat(msgs, num_predict=mode["digest_predict"], temperature=0.3)
                self.items.save_report(item_id, topic.id, report, ctx.model, "DIGESTED")
                done.append(item_id)
        cp = {"done": done, "failed": failed}
        return cp, len(done) + len(failed) >= len(payload.get("item_ids", []))


class CredibilityJob:
    """Достоверность для групп из 2+ материалов разных источников: одна группа за шаг.
    Счётный статус (assess) код ставит сразу; модель отвечает только на узкий вопрос
    «тот же случай и расходятся ли факты», и только если это может изменить статус на ОСПАРИВАЕТСЯ."""

    kind = "credibility"

    def __init__(self, items, sources):
        self.items = items
        self.sources = {s.id: s for s in sources}

    def step(self, ctx, payload: dict, checkpoint: dict) -> tuple[dict, bool]:
        from .research.credibility import DISPUTE_SCHEMA, DISPUTED, assess, dispute_messages, parse_dispute
        clusters = payload.get("clusters", [])
        done = list(checkpoint.get("done", []))
        todo = [i for i in range(len(clusters)) if i not in done]
        if not todo:
            return checkpoint, True
        idx = todo[0]
        c = clusters[idx]
        ids = c["item_ids"]
        members = [self.items.item(i) for i in ids]
        status, reason, low = assess(members, self.sources)
        distinct_sources = {m["source_id"] for m in members}
        mode = RESEARCH_MODES.get(ctx.settings.research_mode, RESEARCH_MODES["balanced"])
        if mode["recheck_disputes"] and len(ids) >= 2 and len(distinct_sources) >= 2:
            a, b = self.items.item(ids[0]), self.items.item(ids[1])
            ra, rb = self.items.report(ids[0]), self.items.report(ids[1])
            try:
                d = parse_dispute(ctx.chat(
                    dispute_messages(a["title"], ra["text"] if ra else a["title"],
                                     b["title"], rb["text"] if rb else b["title"]),
                    num_predict=200, fmt=DISPUTE_SCHEMA, temperature=0.1))
                if d["same_event"] and d["contradicts"]:
                    status, reason = DISPUTED, d["why"] or "источники расходятся в фактах"
            except (ValueError, KeyError, TypeError):
                pass          # не смогли сравнить — остаётся счётный статус, расхождение не выдумываем
        self.items.save_credibility(c["topic_id"], status, reason, low, ids)
        done.append(idx)
        return {"done": done}, len(done) >= len(clusters)


class MemoryJob:
    """Память (Этап 5): один материал за шаг. Эмбеддинг решает, похож ли он по смыслу на уже известную
    тему (merge/relate/new — nexus.memory.consolidate). При объединении модель узко пересказывает
    выводы заново, код решает, новая это тема или нет."""

    kind = "memory"

    def __init__(self, items, memory, topics):
        self.items = items
        self.memory = memory
        self.topics = {t.id: t for t in topics}

    def step(self, ctx, payload: dict, checkpoint: dict) -> tuple[dict, bool]:
        from .memory.consolidate import MERGE, RELATE, decide, merge_messages
        done = list(checkpoint.get("done", []))
        todo = [i for i in payload.get("item_ids", []) if i not in done]
        if not todo:
            return checkpoint, True
        item_id = todo[0]
        it = self.items.item(item_id)
        report = self.items.report(item_id)
        cred = self.items.credibility_of(item_id)
        raw_topic_id = report["topic_id"] if report else "unknown"
        text = (report["text"] if report else it["title"])
        embedding = ctx.embed(f"{it['title']}\n{text[:1000]}")
        candidates = [(t.id, t.embedding) for t in self.memory.all_for_interest(raw_topic_id)]
        action, match_id, _ = decide(embedding, candidates)
        status = cred["status"] if cred else None
        low = bool(cred and cred["low_reliability"])
        if action == MERGE and match_id is not None:
            old = self.memory.get(match_id)
            lang = getattr(getattr(ctx, "settings", None), "language", "ru") or "ru"
            updated = ctx.chat(merge_messages(old.title, old.conclusions, text, language=lang),
                               num_predict=400, temperature=0.2)
            self.memory.update(match_id, old.gist, updated, old.report + f"\n\n--- {it['title']} ---\n{text}",
                               status or old.credibility_status, low or old.low_reliability, embedding, item_id,
                               reason=f"новые сведения: {it['title']}")
        else:
            mid = self.memory.create(raw_topic_id, it["title"], text[:300], text[:300],
                                     f"--- {it['title']} ---\n{text}", status, low, embedding, item_id)
            if action == RELATE and match_id is not None:
                self.memory.link_related(mid, match_id)
        done.append(item_id)
        return {"done": done}, len(done) >= len(payload.get("item_ids", []))


class ErrandJob:
    """Поручение из Дирижёра (раздел 7.3): свободный текст от Давида. Сначала узкий вопрос модели —
    изучение или подготовка вреда (nexus.research.guardrails) — код решает по его ответу, не выдумывая;
    если разрешено, один ответ по делу. Поручения важнее обычных планов Nexus (приоритет у задачи выше)."""

    kind = "errand"

    def step(self, ctx, payload: dict, checkpoint: dict) -> tuple[dict, bool]:
        from .research.guardrails import ALLOW, VERDICT_SCHEMA, classify
        if checkpoint.get("done"):
            return checkpoint, True
        text = payload["text"]

        def ask_model(messages):
            return ctx.chat(messages, num_predict=150, fmt=VERDICT_SCHEMA, temperature=0.1)
        verdict = classify(text, ask_model)
        if verdict.decision != ALLOW:
            return {"done": True, "decision": verdict.decision, "why": verdict.reason, "answer": ""}, True
        style = f" {ctx.settings.custom_instruction}" if ctx.settings.custom_instruction else ""
        mode = RESEARCH_MODES.get(ctx.settings.research_mode, RESEARCH_MODES["balanced"])
        lang_rule = LANGUAGE_INSTRUCTION.get(getattr(ctx.settings, "language", "ru"), LANGUAGE_INSTRUCTION["ru"])
        answer = ctx.chat([
            {"role": "system", "content": f"Ты помогаешь исследователю. {lang_rule} По делу. "
                                          "Если чего-то не знаешь точно — так и скажи, не выдумывай." + style},
            {"role": "user", "content": text},
        ], num_predict=mode["digest_predict"], temperature=0.4)
        return {"done": True, "decision": "allow", "why": verdict.reason, "answer": answer}, True


class SourceReviewJob:
    """Проверка нового источника перед добавлением (раздел 10): один источник — один шаг,
    подсказка модели по тому, что мы ей показали; решение всегда за Давидом."""

    kind = "source_review"

    def step(self, ctx, payload: dict, checkpoint: dict) -> tuple[dict, bool]:
        if checkpoint.get("done"):
            return checkpoint, True
        from .research.source_review import VERDICT_SCHEMA, parse_verdict, review_messages
        from .sources import feeds
        name, url, note = payload["name"], payload["url"], payload.get("note", "")
        titles: list[str] = []
        fetch_error = ""
        try:
            entries = feeds.parse_feed(feeds.fetch(url))
            titles = [e.title for e in entries[:8]]
        except Exception as e:                                       # noqa: BLE001 - одна лента не роняет проверку
            fetch_error = f"{type(e).__name__}: {e}"
        try:
            raw = ctx.chat(review_messages(name, url, note, titles), num_predict=200,
                           fmt=VERDICT_SCHEMA, temperature=0.2)
            verdict = parse_verdict(raw)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            verdict = {"verdict": "unclear", "why": "не удалось получить оценку модели"}
        return {"done": True, "verdict": verdict["verdict"], "why": verdict["why"],
                "fetch_error": fetch_error, "titles": titles[:5]}, True


class OverviewJob:
    """Короткая общая выжимка по уже готовым материалам (раздел 10) — один запрос, один шаг."""

    kind = "overview"

    def __init__(self, items):
        self.items = items

    def step(self, ctx, payload: dict, checkpoint: dict) -> tuple[dict, bool]:
        if checkpoint.get("done"):
            return checkpoint, True
        from .research.overview import overview_messages
        materials = []
        for item_id in payload.get("item_ids", []):
            r = self.items.report(item_id)
            if not r:
                continue
            try:
                it = self.items.item(item_id)
            except KeyError:
                continue
            materials.append({"title": it["title"], "text": r["text"]})
        if not materials:
            return {"done": True, "text": "Нечего суммировать."}, True
        text = ctx.chat(overview_messages(materials, language=getattr(ctx.settings, "language", "ru")),
                        num_predict=400, temperature=0.3)
        return {"done": True, "text": text}, True


class PullModelJob:
    """Скачать модель в свою папку (раздел 5/9) — не трогает видеокарту, но всё равно идёт через
    общую очередь задач, поэтому ждёт своей очереди как обычная задача (см. _Ctx.pull)."""

    kind = "pull_model"

    def step(self, ctx, payload: dict, checkpoint: dict) -> tuple[dict, bool]:
        if checkpoint.get("done"):
            return checkpoint, True
        model = payload["model"]
        from .engine import Cancelled
        try:
            ctx.pull(model)
            return {"done": True, "ok": True, "error": ""}, True
        except Cancelled:
            raise
        except Exception as e:                                     # noqa: BLE001 - не роняем задачу молча
            return {"done": True, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}, True


def make_jobs(items=None, topics=None, sources=None, memory=None) -> dict:
    jobs = [ProbeJob(), ErrandJob(), SourceReviewJob(), PullModelJob()]
    if items is not None:
        jobs.append(TriageJob(items, topics or [], sources or []))
        jobs.append(DigestJob(items, topics or [], sources or []))
        jobs.append(CredibilityJob(items, sources or []))
        jobs.append(OverviewJob(items))
        if memory is not None:
            jobs.append(MemoryJob(items, memory, topics or []))
    return {j.kind: j for j in jobs}


JOBS = make_jobs()
