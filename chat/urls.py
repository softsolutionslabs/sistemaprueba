from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    # URLs existentes (se mantienen igual)
    path('', views.ChatView.as_view(), name='chat'),
    path('api/send-message/', views.ChatView.as_view(), name='send_message'),
    path('api/products-by-category/', views.ProductsByCategoryView.as_view(), name='products_by_category'),
    path('stock/pdf/', views.GenerateStockPDFView.as_view(), name='generate_stock_pdf'),
    path('api/compare-products/', views.CompareProductsView.as_view(), name='compare_products'),
    path('api/stock-list/', views.get_stock_list, name='get_stock_list'),
    
    # URLs para análisis estadísticos
    path('api/sales-analysis/', views.SalesAnalysisView.as_view(), name='sales_analysis'),
    path('api/generate-chart/', views.GenerateChartView.as_view(), name='generate_chart'),
    path('api/business-metrics/', views.BusinessMetricsView.as_view(), name='business_metrics'),
    path('api/sales-data/', views.get_sales_data, name='sales_data'),
    
    # ========== NUEVAS URLs PARA GRÁFICOS INTELIGENTES ==========
    path('api/generate-dynamic-chart/', views.GenerateDynamicChartView.as_view(), name='generate_dynamic_chart'),
    path('api/download-chart/', views.DownloadChartView.as_view(), name='download_chart'),
    path('api/preview-chart/', views.PreviewChartView.as_view(), name='preview_chart'),
]