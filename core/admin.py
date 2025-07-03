from django.contrib import admin
from core.models import GHLAuthCredentials, FirebaseToken, IdentityToolkitAuth, LeadConnectorAuth, CallReport

admin.site.register(GHLAuthCredentials)
admin.site.register(IdentityToolkitAuth)
admin.site.register(FirebaseToken)
admin.site.register(LeadConnectorAuth)
admin.site.register(CallReport)

# Register your models here.
