from django.urls import path
from . import views

urlpatterns = [
    path('', views.store, name="store"),
    path('category/<slug:category_slug>/', views.store, name='product_by_category'),
    path('category/<slug:category_slug>/<slug:product_slug>/', views.product_detail, name='product_detail'),
    path('search/', views.search, name='search'),
    path('submit_review/<int:product_id>/', views.submit_review, name='submit_review'),
    
    # ========== NUEVAS URLs PARA FILTRO DE PRECIOS ==========
    path('api/price-range/', views.get_price_range_api, name='get_price_range'),
    path('api/filter-by-price/', views.filter_products_by_price, name='filter_by_price'),
]