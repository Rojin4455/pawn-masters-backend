import os
from celery import Celery

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pawn_master_backend.settings')

app = Celery('pawn_master_backend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes
app.config_from_object('django.conf:settings', namespace='CELERY')

# ADD THIS SECTION - Celery Configuration for Sequential Processing
app.conf.update(
    # Task routing - send data sync tasks to dedicated queues
    task_routes={
        'accounts_management_app.tasks.async_fetch_all_contacts': {'queue': 'data_sync'},
        'accounts_management_app.tasks.async_sync_conversations_with_messages': {'queue': 'data_sync'},
        'accounts_management_app.tasks.async_sync_conversations_with_calls': {'queue': 'data_sync'},
        'accounts_management_app.tasks.sync_location_data_sequential': {'queue': 'data_sync'},
        'accounts_management_app.tasks.mark_location_synced': {'queue': 'data_sync'},
    },
    
    # Worker configuration - CRITICAL for preventing task hoarding
    worker_prefetch_multiplier=1,  # Important: prevents workers from prefetching tasks
    task_acks_late=True,  # Acknowledge tasks only after completion
    worker_disable_rate_limits=False,
    
    # Task result configuration (adjust Redis URL as needed)
    result_backend='redis://localhost:6379/0',  # Update this to match your Redis setup
    result_expires=3600,  # Results expire after 1 hour
    
    # Task timeout settings - IMPORTANT for long-running tasks
    task_soft_time_limit=7200,  # 2 hours soft limit (120 minutes)
    task_time_limit=9000,       # 2.5 hours hard limit (150 minutes)
    
    # Error handling
    task_reject_on_worker_lost=True,
    task_track_started=True,
    
    # Optional: Beat schedule for periodic sync
    # beat_schedule={
    #     'daily-data-sync': {
    #         'task': 'accounts_management_app.tasks.trigger_all_locations_sync',
    #         'schedule': 86400.0,  # Every 24 hours
    #     },
    # },
    timezone='UTC',
)

# Load task modules from all registered Django app configs
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')