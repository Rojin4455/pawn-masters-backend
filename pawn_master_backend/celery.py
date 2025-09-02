import os
from celery import Celery

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pawn_master_backend.settings')

app = Celery('pawn_master_backend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes
app.config_from_object('django.conf:settings', namespace='CELERY')

# Improved Celery Configuration for Better Load Distribution
app.conf.update(
    # Task routing - distribute tasks across different queues
    task_routes={
        # Contacts tasks - distribute across workers
        'accounts_management_app.tasks.async_fetch_all_contacts': {'queue': 'data_sync'},
        
        # Conversations - can go to general queue for load balancing
        'accounts_management_app.tasks.async_sync_conversations_with_messages': {'queue': 'celery'},
        
        # Calls - priority queue (these seem to be the heaviest tasks)
        'accounts_management_app.tasks.async_sync_conversations_with_calls': {'queue': 'priority'},
        
        # Sequential processing - distribute based on location
        'accounts_management_app.tasks.sync_location_data_sequential': {'queue': 'data_sync'},
        
        # Completion marking - any queue is fine
        'accounts_management_app.tasks.mark_location_synced': {'queue': 'celery'},
        
        # API calls - priority queue
        'core.tasks.make_api_call': {'queue': 'priority'},
    },
    
    # Worker configuration for better distribution
    worker_prefetch_multiplier=1,  # Critical: Only take 1 task at a time
    task_acks_late=True,  # Acknowledge tasks only after completion
    worker_disable_rate_limits=False,
    
    # Task result configuration
    result_backend='redis://localhost:6379/0',
    

    
    # Error handling
    task_reject_on_worker_lost=True,
    task_track_started=True,
    
    # Load balancing improvements
    task_default_queue='celery',
    task_default_exchange_type='direct',
    task_default_routing_key='celery',
    
    timezone='UTC',
)

# Load task modules from all registered Django app configs
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
