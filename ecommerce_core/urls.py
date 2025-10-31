from django.contrib import admin
from django.urls import path, include
from . import views
from django.conf.urls.static import static
from django.conf import settings
from django.http import HttpResponse
from django.http import JsonResponse

def healthcheck(request):
    return JsonResponse({"status": "ok"})

urlpatterns = [

    path('health/', healthcheck),

    path('supersecurelogin/', admin.site.urls),
    path('', views.home, name='home'),
    path('store/', include('store.urls')),
    path('carts/', include('carts.urls')),
    path('accounts/', include('accounts.urls')),
    path('orders/', include('orders.urls')),
    path('chat/', include('chat.urls')),
    path('admin-panel/', include('admin_panel.urls')),
    path('ayuda/', include('help_center.urls')),

    path('health/', lambda request: HttpResponse("OK")),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

