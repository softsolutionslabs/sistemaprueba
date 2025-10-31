from django.urls import path
from . import views

urlpatterns = [
    path('place_order/', views.place_order, name='place_order'),
    path('payments/', views.payments, name='payments'),
    path('api/paypal/order/create/', views.paypal_create_order, name='paypal_create_order'),
    path('api/paypal/order/<str:order_id>/capture/', views.paypal_capture_order, name='paypal_capture_order'),
    path('order_complete/<str:order_number>/', views.order_complete, name='order_complete'),
    path('invoice/<str:order_number>/', views.generate_invoice_pdf, name='generate_invoice'),
]