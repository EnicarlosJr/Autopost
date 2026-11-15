import os
from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    "autopost",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    # Os resultados das tarefas nunca são lidos: não guardar no Redis.
    task_ignore_result=True,
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    # Nenhuma tarefa pode ficar presa indefinidamente.
    task_soft_time_limit=120,
    task_time_limit=180,
    beat_schedule={
        "release-scheduled-publications": {"task": "publications.release_due", "schedule": 30.0},
        "recover-stuck-items": {"task": "maintenance.recover_stuck", "schedule": 120.0},
        "cleanup-old-logs": {"task": "maintenance.cleanup_logs", "schedule": crontab(hour=4, minute=17)},
        # Atualiza o catálogo de categorias do Mercado Livre uma vez por semana (se o servidor tiver acesso).
        "refresh-ml-categories": {"task": "catalog.refresh", "schedule": crontab(day_of_week=1, hour=5, minute=23)},
    },
    imports=("app.workers.tasks",),
)
