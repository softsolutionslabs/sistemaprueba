import os
import google.generativeai as genai
from django.conf import settings
from store.models import Product, Category
from orders.models import Order, OrderProduct, Payment
from django.contrib.auth import get_user_model
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
import io
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Avg, F, Q, Count
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Para evitar problemas con GUI
import base64
import json
import pandas as pd
import seaborn as sns
from io import BytesIO

class ChatBotUtils:

    def __init__(self):
        # Configurar Google AI - LEE DESDE SETTINGS
        
        # Intenta obtener la API Key de settings primero, luego de variables de entorno
        self.api_key = getattr(settings, 'GOOGLE_AI_API_KEY', None)
        
        if not self.api_key:
            # Si no está en settings, busca en variables de entorno
            self.api_key = os.getenv('GOOGLE_AI_API_KEY')
        
        if not self.api_key:
            raise ValueError(
                "GOOGLE_AI_API_KEY no está configurada. "
                "Por favor, agrega GOOGLE_AI_API_KEY a tu archivo .env"
            )
        
        # Configurar Google Generative AI
        genai.configure(api_key=self.api_key)
        
        # Usar modelo estable directamente (gemini-pro-latest es el más confiable)
        try:
            self.model = genai.GenerativeModel('models/gemini-pro-latest')
            print("✅ Modelo gemini-pro-latest cargado correctamente")
        except Exception as e:
            print(f"❌ Error cargando gemini-pro-latest: {e}")
            
            # Fallback a gemini-pro si falla
            try:
                self.model = genai.GenerativeModel('models/gemini-pro')
                print("✅ Modelo gemini-pro cargado como fallback")
            except Exception as e2:
                print(f"❌ Error también con gemini-pro: {e2}")
                
                # Último intento con cualquier modelo disponible
                try:
                    available_models = self.list_available_models()
                    if available_models:
                        model_name = available_models[0]
                        self.model = genai.GenerativeModel(model_name)
                        print(f"✅ Modelo {model_name} cargado como último recurso")
                    else:
                        self.model = None
                        print("⚠️  No hay modelos disponibles, usando solo sistema de fallback")
                except Exception as e3:
                    self.model = None
                    print(f"❌ Error crítico: No se pudo cargar ningún modelo: {e3}")

    def list_available_models(self):
        """Lista los modelos disponibles para generateContent"""
        try:
            models = genai.list_models()
            available_models = []
            for model in models:
                if 'generateContent' in model.supported_generation_methods:
                    available_models.append(model.name)
            return available_models
        except Exception as e:
            print(f"Error al listar modelos: {e}")
            return ['gemini-pro']  # Fallback
    
    def get_system_prompt(self):
        """Define el prompt del sistema para el asistente"""
        return """
        Eres un asistente virtual especializado para un e-commerce. Tu propósito es ayudar a los usuarios con:

        1. Información de productos: precios, stock, descripciones, características
        2. Proceso de compra: cómo realizar pedidos, métodos de pago, envíos
        3. Estado de pedidos: seguimiento, historial
        4. Gestión de cuenta: inicio de sesión, registro, actualización de perfil, contraseñas
        5. Categorías de productos y búsqueda
        6. Políticas de la tienda: devoluciones, garantías, términos de servicio
        7. **ANÁLISIS ESTADÍSTICOS**: ventas, gráficos, métricas de negocio

        Reglas importantes:
        - Sé amable, profesional y útil
        - Si no tienes información suficiente, pide más detalles
        - Para consultas sobre stock específico o precios, verifica en la base de datos
        - Ignora mensajes sin sentido o no relacionados con la tienda
        - Para comparaciones de productos, proporciona información clara y objetiva
        - Siempre ofrece seguir ayudando después de cada respuesta
        - Responde en español
        - Sé conciso pero informativo
        - Para análisis estadísticos, utiliza las funciones especializadas disponibles
        """
    
    def get_product_info(self):
        """Obtiene información actualizada de productos para el contexto"""
        products = Product.objects.all().select_related('category')
        product_info = []
        
        for product in products:
            product_info.append({
                'id': product.id,
                'name': product.product_name,
                'price': float(product.price),
                'stock': product.stock,
                'category': product.category.category_name,
                'description': product.description
            })
        
        return product_info
    
    def get_categories_info(self):
        """Obtiene información de categorías"""
        categories = Category.objects.all()
        return [{
            'id': cat.id,
            'name': cat.category_name,
            'description': cat.description
        } for cat in categories]
    
    def generate_google_ai_response(self, user_message, conversation_history):
        """Genera respuesta usando Google AI API - Versión mejorada"""
        try:
            # Información actualizada de la tienda
            product_info = self.get_product_info()
            categories_info = self.get_categories_info()
            
            # Verificar si es una consulta de análisis estadístico
            if self._is_statistical_query(user_message):
                statistical_response = self._handle_statistical_query(user_message)
                if statistical_response:
                    return statistical_response
            
            # Construir prompt más efectivo
            prompt = f"""
            Eres un asistente virtual especializado en e-commerce. Responde ÚNICAMENTE en español.
            
            INFORMACIÓN ACTUAL DE LA TIENDA:
            - Productos disponibles: {len(product_info)}
            - Categorías: {[cat['name'] for cat in categories_info]}
            - Datos de productos: {product_info}
            
            CONTEXTO DE USUARIO:
            - El usuario está en una tienda online real
            - Puedes acceder a información actualizada de productos, precios y stock
            - Debes ser útil, preciso y amable
            
            PREGUNTA DEL USUARIO: "{user_message}"
            
            Responde de manera:
            - Útil y específica basándote en los datos reales de la tienda
            - En español claro y natural
            - Incluye información relevante de productos si aplica
            - Ofrece seguir ayudando
            
            RESPUESTA:
            """
            
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=1000,
                    temperature=0.7,
                )
            )
            
            return response.text.strip()
            
        except Exception as e:
            print(f"Error con Google AI, usando fallback: {e}")
            return self.generate_fallback_response(user_message)
    
    def _is_statistical_query(self, user_message):
        """Determina si la consulta es sobre análisis estadístico - VERSIÓN MEJORADA"""
        statistical_keywords = [
            'estadística', 'estadisticas', 'gráfico', 'grafico', 'chart', 
            'ventas', 'análisis', 'analisis', 'métricas', 'metricas',
            'historial de ventas', 'reporte', 'tendencia', 'comparar ventas',
            'productos más vendidos', 'ingresos', 'ganancias', 'utilidades',
            'diagrama', 'barras', 'líneas', 'lineas', 'circular', 'pastel'
        ]
        user_message_lower = user_message.lower()
        return any(keyword in user_message_lower for keyword in statistical_keywords)
    
    def _handle_statistical_query(self, user_message):
        """Maneja consultas de análisis estadístico"""
        try:
            message_lower = user_message.lower()
            
            # Análisis de ventas por período
            if any(word in message_lower for word in ['ventas', 'ingresos', 'ganancias']):
                if 'últimos 7 días' in message_lower or 'última semana' in message_lower:
                    return self._get_sales_analysis(days=7)
                elif 'últimos 30 días' in message_lower or 'último mes' in message_lower:
                    return self._get_sales_analysis(days=30)
                elif 'últimos 90 días' in message_lower or 'último trimestre' in message_lower:
                    return self._get_sales_analysis(days=90)
                else:
                    return self._get_sales_analysis(days=30)  # Por defecto 30 días
            
            # Productos más vendidos
            elif 'más vendidos' in message_lower or 'populares' in message_lower:
                return self._get_top_products()
            
            # Métricas generales de negocio
            elif any(word in message_lower for word in ['métricas', 'metricas', 'kpi', 'indicadores']):
                return self._get_business_metrics()
            
            # Gráficos específicos
            elif any(word in message_lower for word in ['gráfico', 'grafico', 'chart']):
                return self._handle_chart_request(user_message)
            
            return None  # Dejar que la IA normal maneje otros casos
            
        except Exception as e:
            print(f"Error en análisis estadístico: {e}")
            return None
    
    def _get_sales_analysis(self, days=30):
        """Genera análisis de ventas para un período específico"""
        try:
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)
            
            # Obtener pedidos completados en el período
            orders = Order.objects.filter(
                created_at__range=[start_date, end_date],
                status='Completed'
            )
            
            # Métricas básicas
            total_orders = orders.count()
            total_revenue = orders.aggregate(total=Sum('order_total'))['total'] or 0
            avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
            
            # Ventas por día
            sales_by_day = orders.extra({
                'date': "DATE(created_at)"
            }).values('date').annotate(
                daily_sales=Sum('order_total'),
                order_count=Count('id')
            ).order_by('date')
            
            # Productos más vendidos en el período
            order_products = OrderProduct.objects.filter(
                order__in=orders,
                ordered=True
            ).values('product__product_name').annotate(
                total_quantity=Sum('quantity'),
                total_revenue=Sum(F('quantity') * F('product_price'))
            ).order_by('-total_quantity')[:5]
            
            # Construir respuesta
            response = f"📊 **Análisis de Ventas - Últimos {days} días**\n\n"
            response += f"• **Total de Pedidos:** {total_orders}\n"
            response += f"• **Ingresos Totales:** ${total_revenue:,.2f}\n"
            response += f"• **Valor Promedio por Pedido:** ${avg_order_value:,.2f}\n\n"
            
            if sales_by_day:
                response += "**Tendencia de Ventas:**\n"
                for day in sales_by_day:
                    response += f"  {day['date']}: ${day['daily_sales'] or 0:,.2f} ({day['order_count']} pedidos)\n"
            
            if order_products:
                response += f"\n**🏆 Top {len(order_products)} Productos Más Vendidos:**\n"
                for i, product in enumerate(order_products, 1):
                    response += f"{i}. {product['product__product_name']} - {product['total_quantity']} unidades (${product['total_revenue']:,.2f})\n"
            
            response += f"\n¿Quieres un gráfico específico o más detalles?"
            
            return response
            
        except Exception as e:
            return f"❌ Error al generar análisis de ventas: {str(e)}"
    
    def _get_top_products(self, limit=10):
        """Obtiene los productos más vendidos"""
        try:
            top_products = OrderProduct.objects.filter(
                ordered=True
            ).values(
                'product__product_name', 
                'product__category__category_name'
            ).annotate(
                total_sold=Sum('quantity'),
                total_revenue=Sum(F('quantity') * F('product_price'))
            ).order_by('-total_sold')[:limit]
            
            response = f"🏆 **Top {len(top_products)} Productos Más Vendidos**\n\n"
            
            for i, product in enumerate(top_products, 1):
                response += f"{i}. **{product['product__product_name']}**\n"
                response += f"   📦 Vendidos: {product['total_sold']}\n"
                response += f"   💰 Ingresos: ${product['total_revenue']:,.2f}\n"
                response += f"   📂 Categoría: {product['product__category__category_name']}\n\n"
            
            return response
            
        except Exception as e:
            return f"❌ Error al obtener productos más vendidos: {str(e)}"
    
    def _get_business_metrics(self):
        """Obtiene métricas generales del negocio"""
        try:
            # Métricas de pedidos
            total_orders = Order.objects.count()
            completed_orders = Order.objects.filter(status='Completed').count()
            cancelled_orders = Order.objects.filter(status='Cancelled').count()
            
            # Métricas de ingresos
            total_revenue = Order.objects.filter(status='Completed').aggregate(
                total=Sum('order_total')
            )['total'] or 0
            
            # Métricas de productos
            total_products = Product.objects.count()
            available_products = Product.objects.filter(is_available=True).count()
            low_stock_products = Product.objects.filter(stock__lte=10, is_available=True).count()
            
            # Métricas de usuarios
            total_users = get_user_model().objects.count()
            users_with_orders = get_user_model().objects.filter(order__isnull=False).distinct().count()
            
            response = "📈 **Métricas del Negocio**\n\n"
            
            response += "**📦 PEDIDOS:**\n"
            response += f"• Total de Pedidos: {total_orders}\n"
            response += f"• Pedidos Completados: {completed_orders}\n"
            response += f"• Pedidos Cancelados: {cancelled_orders}\n"
            response += f"• Tasa de Completación: {(completed_orders/total_orders*100) if total_orders > 0 else 0:.1f}%\n\n"
            
            response += "**💰 INGRESOS:**\n"
            response += f"• Ingresos Totales: ${total_revenue:,.2f}\n"
            response += f"• Ingreso Promedio por Pedido: ${(total_revenue/completed_orders) if completed_orders > 0 else 0:,.2f}\n\n"
            
            response += "**🛍️ PRODUCTOS:**\n"
            response += f"• Total de Productos: {total_products}\n"
            response += f"• Productos Disponibles: {available_products}\n"
            response += f"• Productos con Stock Bajo: {low_stock_products}\n\n"
            
            response += "**👥 USUARIOS:**\n"
            response += f"• Total de Usuarios: {total_users}\n"
            response += f"• Usuarios con Compras: {users_with_orders}\n"
            response += f"• Tasa de Conversión: {(users_with_orders/total_users*100) if total_users > 0 else 0:.1f}%\n"
            
            return response
            
        except Exception as e:
            return f"❌ Error al obtener métricas del negocio: {str(e)}"
    
    def _handle_chart_request(self, user_message):
        """Maneja solicitudes de generación de gráficos - VERSIÓN CORREGIDA"""
        try:
            message_lower = user_message.lower()
            
            # DETECCIÓN MEJORADA de solicitudes de gráficos
            if any(word in message_lower for word in ['gráfico', 'grafico', 'chart', 'diagrama']):
                if 'barras' in message_lower:
                    chart_data = self._generate_sales_bar_chart()
                    if chart_data:
                        return f"📊 **Gráfico de Barras Generado:**\n\n{chart_data['analysis']}\n\n*El gráfico está listo para descargar.*"
                elif 'línea' in message_lower or 'linea' in message_lower:
                    chart_data = self._generate_sales_line_chart()
                    if chart_data:
                        return f"📈 **Gráfico de Líneas Generado:**\n\n{chart_data['analysis']}\n\n*El gráfico está listo para descargar.*"
                elif 'circular' in message_lower or 'pastel' in message_lower or 'pie' in message_lower:
                    chart_data = self._generate_category_pie_chart()
                    if chart_data:
                        return f"🥧 **Gráfico Circular Generado:**\n\n{chart_data['analysis']}\n\n*El gráfico está listo para descargar.*"
                else:
                    # Por defecto, generar gráfico de líneas
                    chart_data = self._generate_sales_line_chart()
                    if chart_data:
                        return f"📊 **Gráfico de Ventas Generado:**\n\n{chart_data['analysis']}\n\n*El gráfico está listo para descargar.*"
            
            return None  # Dejar que la IA normal maneje otros casos
                    
        except Exception as e:
            print(f"Error en _handle_chart_request: {e}")
            return f"❌ Error al generar gráfico: {str(e)}"
    
    def _generate_sales_bar_chart(self):
        """Genera gráfico de barras de ventas"""
        try:
            # Obtener datos de ventas de los últimos 30 días
            end_date = timezone.now()
            start_date = end_date - timedelta(days=30)
            
            sales_data = Order.objects.filter(
                created_at__range=[start_date, end_date],
                status='Completed'
            ).extra({
                'date': "DATE(created_at)"
            }).values('date').annotate(
                daily_sales=Sum('order_total')
            ).order_by('date')
            
            if not sales_data:
                return None
            
            # Preparar datos para el gráfico
            dates = [item['date'].strftime('%m-%d') for item in sales_data]
            sales = [float(item['daily_sales'] or 0) for item in sales_data]
            
            # Crear gráfico
            plt.figure(figsize=(12, 6))
            plt.bar(dates, sales, color='skyblue', alpha=0.7)
            plt.title('Ventas de los Últimos 30 Días', fontsize=14, fontweight='bold')
            plt.xlabel('Fecha')
            plt.ylabel('Ventas ($)')
            plt.xticks(rotation=45)
            plt.grid(axis='y', alpha=0.3)
            plt.tight_layout()
            
            # Guardar en buffer
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            
            # Convertir a base64 para mostrar en HTML si es necesario
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            analysis = self._analyze_sales_trend(sales_data)
            
            return {
                'chart_type': 'bar',
                'image_base64': image_base64,
                'analysis': analysis,
                'buffer': buffer
            }
            
        except Exception as e:
            print(f"Error generando gráfico de barras: {e}")
            return None
    
    def _generate_sales_line_chart(self):
        """Genera gráfico de líneas de tendencia de ventas - VERSIÓN MEJORADA"""
        try:
            # Obtener datos de los últimos 30 días
            end_date = timezone.now()
            start_date = end_date - timedelta(days=30)
            
            sales_data = Order.objects.filter(
                created_at__range=[start_date, end_date],
                status='Completed'
            ).extra({
                'date': "DATE(created_at)"
            }).values('date').annotate(
                daily_sales=Sum('order_total')
            ).order_by('date')
            
            if not sales_data:
                return None
            
            # CORRECIÓN: Manejo seguro de fechas
            dates = []
            sales = []
            
            for item in sales_data:
                # Verificar que la fecha existe y formatear
                if item['date']:
                    dates.append(item['date'].strftime('%m-%d'))
                    sales.append(float(item['daily_sales'] or 0))
            
            if not dates:  # Si no hay fechas válidas
                return None
                
            plt.figure(figsize=(12, 6))
            plt.plot(dates, sales, marker='o', linewidth=2, markersize=4, color='green')
            plt.title('Tendencia de Ventas - Últimos 30 Días', fontsize=14, fontweight='bold')
            plt.xlabel('Fecha')
            plt.ylabel('Ventas ($)')
            plt.xticks(rotation=45)
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            analysis = self._analyze_sales_trend(sales_data)
            
            return {
                'chart_type': 'line',
                'image_base64': image_base64,
                'analysis': analysis,
                'buffer': buffer
            }
            
        except Exception as e:
            print(f"Error generando gráfico de líneas: {e}")
            return None

    def _generate_category_pie_chart(self):
        """Genera gráfico circular de productos por categoría"""
        try:
            categories = Category.objects.annotate(
                product_count=Count('product')
            ).values('category_name', 'product_count')
            
            if not categories:
                return None
            
            category_names = [cat['category_name'] for cat in categories]
            product_counts = [cat['product_count'] for cat in categories]
            
            plt.figure(figsize=(10, 8))
            plt.pie(product_counts, labels=category_names, autopct='%1.1f%%', startangle=90)
            plt.title('Distribución de Productos por Categoría', fontsize=14, fontweight='bold')
            plt.axis('equal')
            
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            plt.close()
            buffer.seek(0)
            
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            analysis = "**Distribución de Productos por Categoría:**\n"
            for cat in categories:
                analysis += f"• {cat['category_name']}: {cat['product_count']} productos\n"
            
            return {
                'chart_type': 'pie',
                'image_base64': image_base64,
                'analysis': analysis,
                'buffer': buffer
            }
            
        except Exception as e:
            print(f"Error generando gráfico circular: {e}")
            return None
    
    def _analyze_sales_trend(self, sales_data):
        """Analiza la tendencia de ventas - VERSIÓN CORREGIDA"""
        try:
            if not sales_data:
                return "No hay datos suficientes para el análisis."
            
            # CORRECIÓN: Extraer valores numéricos correctamente
            sales_values = []
            for item in sales_data:
                # Manejar valores None o vacíos
                sales_value = float(item['daily_sales'] or 0)
                sales_values.append(sales_value)
            
            total_sales = sum(sales_values)
            avg_sales = total_sales / len(sales_values) if sales_values else 0
            max_sales = max(sales_values) if sales_values else 0
            min_sales = min(sales_values) if sales_values else 0
            
            analysis = "**📈 Análisis de Tendencia:**\n"
            analysis += f"• Ventas Totales: ${total_sales:,.2f}\n"
            analysis += f"• Promedio Diario: ${avg_sales:,.2f}\n"
            analysis += f"• Día Pico: ${max_sales:,.2f}\n"
            analysis += f"• Día Más Bajo: ${min_sales:,.2f}\n"
            
            # Análisis de tendencia simple
            if len(sales_values) >= 7:  # Solo si hay al menos 7 días
                first_week_avg = sum(sales_values[:7]) / 7
                last_week_avg = sum(sales_values[-7:]) / 7
                
                if last_week_avg > first_week_avg * 1.1:
                    analysis += "• 📈 Tendencia: **ALCISTA** en las últimas semanas\n"
                elif last_week_avg < first_week_avg * 0.9:
                    analysis += "• 📉 Tendencia: **BAJISTA** en las últimas semanas\n"
                else:
                    analysis += "• ➡️ Tendencia: **ESTABLE** en las últimas semanas\n"
            else:
                analysis += "• ℹ️ Se necesitan más datos para análisis de tendencia\n"
            
            return analysis
            
        except Exception as e:
            return f"Análisis de tendencia no disponible: {str(e)}"

    def generate_fallback_response(self, user_message):
        """Genera una respuesta de fallback más inteligente cuando la IA no funciona"""
        try:
            user_message_lower = user_message.lower()
            
            # 1. Consultas sobre productos por categoría
            if any(word in user_message_lower for word in ['categoría', 'categoria', 'computadoras', 'ropa', 'música', 'muebles', 'accesorios']):
                if 'computadora' in user_message_lower:
                    products = Product.objects.filter(category__category_name__icontains='computadora', is_available=True)
                    if products.exists():
                        product_list = "\n".join([f"• **{p.product_name}** - ${p.price} (Stock: {p.stock})" for p in products])
                        return f"🖥️ **Productos en Computadoras:**\n\n{product_list}\n\n¿Te interesa alguno de estos productos?"
                    else:
                        return "❌ No hay productos disponibles en la categoría Computadoras."
                
                # Para otras categorías
                categories = Category.objects.all()
                category_list = "\n".join([f"• {cat.category_name}" for cat in categories])
                return f"📂 **Categorías disponibles:**\n\n{category_list}\n\n" \
                    f"Puedo mostrarte los productos de cualquier categoría. ¿Cuál te interesa?"
            
            # 2. Consultas sobre presupuesto
            elif any(word in user_message_lower for word in ['presupuesto', 'gs', 'guaraníes', '200.000', '200000', 'dinero']):
                budget = 200000
                affordable_products = Product.objects.filter(price__lte=budget, is_available=True).order_by('price')
                
                if affordable_products.exists():
                    product_list = "\n".join([f"• **{p.product_name}** - ${p.price} (Stock: {p.stock})" for p in affordable_products])
                    return f"💰 **Productos dentro de tu presupuesto de {budget:,} GS:**\n\n{product_list}\n\n" \
                        f"¿Te gustaría más información de algún producto en particular?"
                else:
                    return f"❌ No hay productos dentro de tu presupuesto de {budget:,} GS. " \
                        f"El producto más económico cuesta ${Product.objects.filter(is_available=True).order_by('price').first().price}"
            
            # 3. Consultas sobre ayuda de cuenta
            elif any(word in user_message_lower for word in ['contraseña', 'password', 'cambiar contraseña', 'olvidé contraseña']):
                return "🔐 **Para cambiar tu contraseña:**\n\n" \
                    "1. Ve a 'Mi Cuenta' en el menú superior\n" \
                    "2. Haz clic en 'Cambiar Contraseña'\n" \
                    "3. Ingresa tu contraseña actual y la nueva\n" \
                    "4. Confirma los cambios\n\n" \
                    "Si olvidaste tu contraseña, haz clic en '¿Olvidaste tu contraseña?' en la página de login."
            
            # 4. Consultas sobre proceso de compra
            elif any(word in user_message_lower for word in ['comprar', 'pedido', 'carrito', 'pago', 'envío']):
                return "🛒 **Proceso de compra:**\n\n" \
                    "1. **Agregar productos**: Haz clic en 'Agregar al Carrito'\n" \
                    "2. **Ver carrito**: Ve a 'Carrito' en el menú\n" \
                    "3. **Checkout**: Haz clic en 'Proceder al Pago'\n" \
                    "4. **Envío**: Elige dirección y método de envío\n" \
                    "5. **Pago**: Selecciona tu método de pago\n" \
                    "6. **Confirmación**: Recibirás un email de confirmación\n\n" \
                    "¿En qué paso necesitas ayuda?"
            
            # 5. Consultas sobre stock específico
            elif any(word in user_message_lower for word in ['stock', 'disponible', 'cantidad', 'unidades']):
                products = Product.objects.all().order_by('-stock')
                if products.exists():
                    top_products = products[:3]  # Top 3 productos con más stock
                    product_list = "\n".join([f"• **{p.product_name}** - {p.stock} unidades" for p in top_products])
                    return f"📦 **Productos con mayor stock:**\n\n{product_list}\n\n" \
                        f"¿Quieres información detallada de algún producto?"
            
            # 6. Consultas estadísticas (nuevo)
            elif any(word in user_message_lower for word in ['estadística', 'estadisticas', 'ventas', 'métricas']):
                return self._get_business_metrics()
            
            # 7. Consulta general mejorada
            else:
                product_count = Product.objects.count()
                category_count = Category.objects.count()
                total_products = Product.objects.filter(is_available=True)
                
                # Productos destacados
                featured_products = total_products.order_by('?')[:3]  # 3 productos aleatorios
                
                featured_list = "\n".join([f"• **{p.product_name}** - ${p.price}" for p in featured_products])
                
                return f"¡Hola! Soy tu asistente virtual. 😊\n\n" \
                    f"**Resumen de la tienda:**\n" \
                    f"• {product_count} productos disponibles\n" \
                    f"• {category_count} categorías\n\n" \
                    f"**Algunos productos destacados:**\n{featured_list}\n\n" \
                    f"**Puedo ayudarte con:**\n" \
                    f"• 🛍️ Información de productos y stock\n" \
                    f"• 💰 Precios y presupuestos\n" \
                    f"• 🛒 Proceso de compra\n" \
                    f"• 🔐 Gestión de cuenta\n" \
                    f"• 📦 Seguimiento de pedidos\n" \
                    f"• 🔄 Comparación de productos\n" \
                    f"• 📊 **Análisis estadísticos y gráficos**\n\n" \
                    f"¿En qué necesitas ayuda específicamente?"
                            
        except Exception as e:
            return "¡Hola! Estoy aquí para ayudarte con información sobre nuestros productos, stock, precios, proceso de compra, gestión de tu cuenta y **análisis estadísticos**. ¿En qué puedo asistirte hoy?"
    
    def generate_stock_pdf(self):
        """Genera PDF con el stock de productos"""
        try:
            buffer = io.BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=letter)
            
            # Encabezado
            pdf.setTitle("Reporte de Stock - E-commerce")
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(100, 750, "Reporte de Stock de Productos")
            pdf.setFont("Helvetica", 10)
            pdf.drawString(100, 735, f"Generado el: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
            
            # Información de productos
            products = Product.objects.all().select_related('category').order_by('category__category_name', 'product_name')
            y_position = 700
            
            current_category = None
            for product in products:
                # Nueva categoría
                if product.category.category_name != current_category:
                    current_category = product.category.category_name
                    y_position -= 20
                    if y_position < 50:
                        pdf.showPage()
                        y_position = 750
                    pdf.setFont("Helvetica-Bold", 12)
                    pdf.drawString(100, y_position, f"Categoría: {current_category}")
                    y_position -= 15
                
                # Información del producto
                if y_position < 50:
                    pdf.showPage()
                    y_position = 750
                
                pdf.setFont("Helvetica", 10)
                product_line = f"  {product.product_name} - Stock: {product.stock} - Precio: ${product.price}"
                pdf.drawString(120, y_position, product_line)
                y_position -= 15
            
            pdf.save()
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            raise Exception(f"Error al generar PDF: {str(e)}")
    
    def compare_products(self, product_ids):
        """Compara productos usando IA cuando está disponible"""
        try:
            products = Product.objects.filter(id__in=product_ids).select_related('category')
            
            if len(products) < 2:
                return "Se necesitan al menos 2 productos para comparar"
            
            # Intentar con IA primero
            comparison_data = []
            for product in products:
                comparison_data.append({
                    'nombre': product.product_name,
                    'precio': float(product.price),
                    'categoría': product.category.category_name,
                    'stock': product.stock,
                    'descripción': product.description,
                })
            
            prompt = f"""
            Como experto en e-commerce, compara estos productos de manera útil:
            
            {comparison_data}
            
            Responde en español con:
            1. Similitudes clave
            2. Diferencias principales (precio, características)
            3. Recomendación según diferentes necesidades
            4. Mejor opción por categoría (valor, características)
            
            Sé objetivo y útil para el cliente:
            """
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            print(f"Error en comparación con IA: {e}")
            # Fallback a comparación manual
            return self._manual_product_comparison(product_ids)
        



    def _detect_chart_type(self, user_message):
        """Detecta qué tipo de gráfico generar basado en la consulta"""
        message_lower = user_message.lower()
        
        chart_types = {
            'barras': ['barras', 'barra', 'columnas', 'column'],
            'lineas': ['líneas', 'lineas', 'tendencia', 'evolución'],
            'pastel': ['pastel', 'circular', 'pie', 'porcentaje'],
            'dispersion': ['dispersión', 'scatter', 'correlación']
        }
        
        for chart_type, keywords in chart_types.items():
            if any(keyword in message_lower for keyword in keywords):
                return chart_type
        
        return 'barras'  # Por defecto

    def _detect_chart_subject(self, user_message):
        """Detecta el tema del gráfico"""
        message_lower = user_message.lower()
        
        if any(word in message_lower for word in ['ventas', 'ingresos', 'ganancias']):
            return 'ventas'
        elif any(word in message_lower for word in ['productos', 'stock', 'inventario']):
            return 'productos'
        elif any(word in message_lower for word in ['categoría', 'categoria', 'categorias']):
            return 'categorias'
        elif any(word in message_lower for word in ['usuarios', 'clientes']):
            return 'usuarios'
        
        return 'ventas'  # Por defecto

    def _extract_filters(self, user_message):
        """Extrae filtros específicos de la consulta - VERSIÓN MEJORADA"""
        try:
            filters = {}
            message_lower = user_message.lower()
            
            # Detectar categoría específica - MEJORADO
            categories = Category.objects.all()
            for category in categories:
                category_name_lower = category.category_name.lower()
                if category_name_lower in message_lower:
                    filters['category'] = category
                    break
            
            # Detectar período de tiempo - MEJORADO
            time_keywords = {
                'week': ['semana', '7 días', 'siete días'],
                'month': ['mes', '30 días', 'treinta días'],
                'year': ['año', 'anual', '365 días']
            }
            
            for period, keywords in time_keywords.items():
                if any(keyword in message_lower for keyword in keywords):
                    filters['period'] = period
                    break
            else:
                filters['period'] = 'month'  # Por defecto
            
            # Detectar tipo específico de datos
            if 'stock' in message_lower:
                filters['data_type'] = 'stock'
            elif 'precio' in message_lower or 'precios' in message_lower:
                filters['data_type'] = 'price'
            
            return filters
            
        except Exception as e:
            print(f"Error en _extract_filters: {e}")
            return {'period': 'month'}  # Filtros por defecto en caso de error

    def generate_dynamic_chart(self, user_message):
        """Genera gráfico dinámicamente basado en la consulta - VERSIÓN CORREGIDA"""
        try:
            print(f"🔍 Procesando consulta: {user_message}")
            
            chart_type = self._detect_chart_type(user_message)
            chart_subject = self._detect_chart_subject(user_message)
            filters = self._extract_filters(user_message)
            
            print(f"📊 Tipo: {chart_type}, Tema: {chart_subject}, Filtros: {filters}")
            
            # Generar datos REALES según el tema
            if chart_subject == 'ventas':
                chart_data = self._generate_sales_chart_data(filters)
                title = f"Ventas - {filters.get('category', 'Todas las categorías')}"
            elif chart_subject == 'productos':
                chart_data = self._generate_products_chart_data(filters)
                category_name = filters.get('category', 'Todas las categorías')
                if hasattr(category_name, 'category_name'):
                    category_name = category_name.category_name
                title = f"Productos - {category_name}"
            elif chart_subject == 'categorias':
                chart_data = self._generate_categories_chart_data(filters)
                title = "Distribución por Categorías"
            else:
                chart_data = self._generate_sales_chart_data(filters)
                title = f"Ventas - {filters.get('category', 'Todas las categorías')}"
            
            print(f"📈 Datos obtenidos: {len(chart_data)} elementos")
            
            if not chart_data:
                return {
                    'success': False,
                    'error': 'No se encontraron datos para generar el gráfico.'
                }
            
            # Generar gráfico
            chart_result = self._create_chart(chart_data, chart_type, title)
            
            if not chart_result:
                return {
                    'success': False,
                    'error': 'Error al crear el gráfico con los datos obtenidos.'
                }
            
            return {
                'success': True,
                'chart_type': chart_type,
                'chart_subject': chart_subject,
                'title': title,
                'chart_data': chart_result,
                'analysis': self._analyze_chart_data(chart_data, chart_subject)
            }
            
        except Exception as e:
            print(f"❌ Error en generate_dynamic_chart: {e}")
            return {
                'success': False,
                'error': f"Error generando gráfico: {str(e)}"
            }

    def _generate_sales_chart_data(self, filters):
        """Genera datos REALES de ventas para gráficos - VERSIÓN CORREGIDA"""
        try:
            from datetime import datetime, timedelta
            
            # Definir período según filtros
            end_date = timezone.now()
            if filters.get('period') == 'week':
                start_date = end_date - timedelta(days=7)
            elif filters.get('period') == 'year':
                start_date = end_date - timedelta(days=365)
            else:  # month por defecto
                start_date = end_date - timedelta(days=30)
            
            # Consulta REAL a la base de datos
            orders = Order.objects.filter(
                created_at__range=[start_date, end_date],
                status='Completed'
            )
            
            # Si hay filtro de categoría, aplicar
            if 'category' in filters:
                orders = orders.filter(
                    orderproduct__product__category=filters['category']
                ).distinct()
            
            # Agrupar por fecha
            sales_data = orders.extra({
                'date': "DATE(created_at)"
            }).values('date').annotate(
                total_sales=Sum('order_total'),
                order_count=Count('id')
            ).order_by('date')
            
            return list(sales_data)
            
        except Exception as e:
            print(f"Error en _generate_sales_chart_data: {e}")
            return []

    def _generate_products_chart_data(self, filters):
        """Genera datos REALES de productos para gráficos - VERSIÓN CORREGIDA"""
        try:
            # Consulta base
            products = Product.objects.filter(is_available=True)
            
            # Aplicar filtro de categoría si existe
            if 'category' in filters:
                products = products.filter(category=filters['category'])
            
            # Obtener productos con más stock o por precio
            products_data = products.values(
                'id', 'product_name', 'stock', 'price', 'category__category_name'
            ).order_by('-stock')[:10]  # Top 10 por stock
            
            return list(products_data)
            
        except Exception as e:
            print(f"Error en _generate_products_chart_data: {e}")
            return []

    def _generate_categories_chart_data(self, filters):
        """Genera datos REALES de categorías para gráficos - VERSIÓN MEJORADA"""
        try:
            print("📊 Generando datos REALES de categorías...")
            
            # Consulta REAL: productos por categoría con datos completos
            categories_data = Category.objects.annotate(
                product_count=Count('product'),
                total_stock=Sum('product__stock'),
                avg_price=Avg('product__price'),
                available_products=Count('product', filter=Q(product__is_available=True))
            ).values(
                'id', 'category_name', 'product_count', 'total_stock', 'avg_price', 'available_products'
            ).order_by('-product_count')  # Ordenar por cantidad de productos
            
            result = list(categories_data)
            print(f"✅ Datos de categorías obtenidos: {len(result)} categorías")
            
            # Mostrar los datos para debug
            for cat in result[:3]:  # Mostrar solo las primeras 3 para no saturar
                print(f"   📁 {cat['category_name']}: {cat['product_count']} productos")
            
            return result
            
        except Exception as e:
            print(f"❌ Error en _generate_categories_chart_data: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _create_chart(self, data, chart_type, title):
        """Crea el gráfico según el tipo"""
        plt.figure(figsize=(10, 6))
        
        if chart_type == 'barras':
            self._create_bar_chart(data, title)
        elif chart_type == 'lineas':
            self._create_line_chart(data, title)
        elif chart_type == 'pastel':
            self._create_pie_chart(data, title)
        elif chart_type == 'dispersion':
            self._create_scatter_chart(data, title)
        
        # Guardar gráfico en buffer
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        plt.close()
        buffer.seek(0)
        
        # Convertir a base64 para mostrar en HTML
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return {
            'image_base64': image_base64,
            'buffer': buffer,
            'data_points': len(data)
        }

    def _create_pie_chart(self, data, title):
        """Crea gráfico circular (pie chart) con datos REALES - VERSIÓN CORREGIDA"""
        try:
            if not data:
                print("❌ No hay datos para el gráfico circular")
                return
            
            print(f"📊 Datos recibidos para pie chart: {data}")
            
            # VERIFICAR la estructura real de los datos
            if data and isinstance(data[0], dict):
                # Datos de categorías (vienen de _generate_categories_chart_data)
                if 'category_name' in data[0] and 'product_count' in data[0]:
                    labels = [item['category_name'] for item in data]
                    values = [item['product_count'] for item in data]
                    print(f"✅ Usando datos de categorías: {labels} - {values}")
                
                # Datos de productos (vienen de _generate_products_chart_data)  
                elif 'product_name' in data[0] and 'stock' in data[0]:
                    labels = [item['product_name'][:20] for item in data]  # Limitar longitud
                    values = [item['stock'] for item in data]
                    print(f"✅ Usando datos de productos: {labels} - {values}")
                
                # Datos de ventas por producto
                elif 'product__product_name' in data[0] and 'total_sales' in data[0]:
                    labels = [item['product__product_name'][:20] for item in data]
                    values = [float(item.get('total_sales', 0) or 0) for item in data]
                    print(f"✅ Usando datos de ventas: {labels} - {values}")
                
                else:
                    # Si no reconoce la estructura, usar datos genéricos PERO con nombres reales
                    print(f"⚠️ Estructura no reconocida, claves disponibles: {list(data[0].keys())}")
                    
                    # Intentar extraer nombres y valores de cualquier manera
                    labels = []
                    values = []
                    
                    for i, item in enumerate(data):
                        # Buscar cualquier campo que pueda ser nombre
                        name_fields = [key for key in item.keys() if 'name' in key.lower() or 'product' in key.lower()]
                        if name_fields:
                            label = str(item.get(name_fields[0], f'Item {i+1}'))
                        else:
                            label = f'Categoría {i+1}'
                        
                        # Buscar cualquier campo numérico
                        value_fields = [key for key in item.keys() if key not in name_fields and isinstance(item[key], (int, float))]
                        if value_fields:
                            value = float(item.get(value_fields[0], 1))
                        else:
                            value = 1
                        
                        labels.append(label[:25])  # Limitar longitud
                        values.append(value)
                    
                    print(f"🔄 Usando datos genéricos extraídos: {labels} - {values}")
            else:
                # Datos en formato no esperado
                print(f"❌ Formato de datos no soportado: {type(data[0]) if data else 'vacío'}")
                labels = [f"Item {i+1}" for i in range(len(data))]
                values = [1] * len(data)
            
            # FILTRAR datos vacíos o cero
            filtered_data = []
            filtered_labels = []
            for label, value in zip(labels, values):
                if value > 0:  # Solo incluir valores positivos
                    filtered_labels.append(label)
                    filtered_data.append(value)
            
            if not filtered_data:
                print("❌ No hay datos válidos después del filtrado")
                return
            
            print(f"🎯 Datos finales para gráfico: {filtered_labels} - {filtered_data}")
            
            # Crear gráfico circular con datos REALES
            plt.figure(figsize=(12, 8))
            
            # Colores más atractivos
            colors = plt.cm.Set3(range(len(filtered_data)))
            
            # Crear el pie chart
            wedges, texts, autotexts = plt.pie(
                filtered_data, 
                labels=filtered_labels, 
                autopct='%1.1f%%', 
                startangle=90, 
                colors=colors,
                textprops={'fontsize': 10}
            )
            
            # Mejorar la apariencia de los porcentajes
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
            
            plt.title(title, fontsize=16, fontweight='bold', pad=20)
            plt.axis('equal')  # Para que sea circular
            
            # Añadir leyenda si hay muchos elementos
            if len(filtered_data) > 5:
                plt.legend(wedges, filtered_labels, title="Categorías", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
            
            plt.tight_layout()
            
            print("✅ Gráfico circular creado exitosamente")
            
        except Exception as e:
            print(f"❌ Error en _create_pie_chart: {e}")
            import traceback
            traceback.print_exc()

    def _create_scatter_chart(self, data, title):
        """Crea gráfico de dispersión"""
        if not data:
            return
        
        # Para scatter plot necesitamos dos variables numéricas
        if 'price' in data[0] and 'stock' in data[0]:
            x = [item['price'] for item in data]
            y = [item['stock'] for item in data]
            labels = [item.get('product_name', f'Product {i+1}') for i, item in enumerate(data)]
            
            plt.scatter(x, y, alpha=0.6)
            plt.title(title)
            plt.xlabel('Precio')
            plt.ylabel('Stock')
            
            # Agregar etiquetas
            for i, label in enumerate(labels):
                plt.annotate(label, (x[i], y[i]), xytext=(5, 5), textcoords='offset points', fontsize=8)
        else:
            # Datos genéricos si no hay las columnas esperadas
            x = range(len(data))
            y = [i * 10 for i in range(len(data))]
            plt.scatter(x, y)
            plt.title(title)
            plt.xlabel('Índice')
            plt.ylabel('Valor')

    def _create_line_chart(self, data, title):
        """Crea gráfico de líneas - VERSIÓN MEJORADA"""
        if not data:
            return
        
        # Diferentes tipos de datos para líneas
        if 'period' in data[0]:
            # Datos temporales
            periods = [item['period'] for item in data]
            values = [float(item.get('total', 0) or 0) for item in data]
            plt.plot(periods, values, marker='o', linewidth=2)
            plt.title(title)
            plt.xlabel('Período')
            plt.ylabel('Total')
            plt.xticks(rotation=45)
        elif 'product__product_name' in data[0]:
            # Datos de productos
            products = [item['product__product_name'][:15] + '...' for item in data]
            values = [float(item.get('total_sales', 0) or 0) for item in data]
            plt.plot(products, values, marker='s', linewidth=2)
            plt.title(title)
            plt.xlabel('Productos')
            plt.ylabel('Ventas')
            plt.xticks(rotation=45)
        else:
            # Datos genéricos
            x = range(len(data))
            y = [float(item.get('value', 0) or 0) for item in data]
            plt.plot(x, y, marker='o', linewidth=2)
            plt.title(title)
            plt.xlabel('Índice')
            plt.ylabel('Valor')
        
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

    def _create_bar_chart(self, data, title):
        """Crea gráfico de barras"""
        if not data:
            return
        
        # Extraer labels y valores
        if 'product__product_name' in data[0]:
            labels = [item['product__product_name'][:15] + '...' for item in data]
            values = [float(item['total_sales'] or 0) for item in data]
            ylabel = 'Ventas (Gs.)'
        else:
            labels = [item['category_name'] for item in data]
            values = [item['product_count'] for item in data]
            ylabel = 'Cantidad'
        
        plt.bar(labels, values, color='skyblue')
        plt.title(title)
        plt.xlabel('Categorías/Productos')
        plt.ylabel(ylabel)
        plt.xticks(rotation=45)
        plt.tight_layout()

    def _analyze_chart_data(self, data, chart_subject):
        """Analiza los datos y genera insights"""
        if not data:
            return "No hay datos suficientes para el análisis."
        
        analysis = f"**📊 Análisis del Gráfico ({chart_subject}):**\n\n"
        
        if chart_subject == 'ventas':
            total_ventas = sum(float(item.get('total_sales', 0) or 0) for item in data)
            analysis += f"• **Ventas Totales:** Gs. {total_ventas:,.0f}\n"
            
            if len(data) > 0:
                max_venta = max(data, key=lambda x: float(x.get('total_sales', 0) or 0))
                analysis += f"• **Producto Más Vendido:** {max_venta.get('product__product_name', 'N/A')}\n"
        
        elif chart_subject == 'productos':
            total_stock = sum(item.get('stock', 0) for item in data)
            analysis += f"• **Stock Total:** {total_stock} unidades\n"
        
        analysis += f"• **Datos Analizados:** {len(data)} elementos\n"
        analysis += "\n💡 *Puedes descargar el gráfico usando el botón 'Ver Gráfico'*"
        
        return analysis
    
    def _manual_product_comparison(self, product_ids):
        """Comparación manual de productos cuando falla la IA"""
        try:
            products = Product.objects.filter(id__in=product_ids).select_related('category')
            
            comparison = "🔍 **Comparación Manual de Productos:**\n\n"
            
            for i, product in enumerate(products, 1):
                comparison += f"**Producto {i}: {product.product_name}**\n"
                comparison += f"• Precio: Gs. {product.price:,}\n"
                comparison += f"• Stock: {product.stock} unidades\n"
                comparison += f"• Categoría: {product.category.category_name}\n"
                comparison += f"• Descripción: {product.description}\n\n"
            
            # Análisis comparativo simple
            prices = [p.price for p in products]
            comparison += "**📊 Análisis Comparativo:**\n"
            comparison += f"• Producto más económico: {products[prices.index(min(prices))].product_name} (Gs. {min(prices):,})\n"
            comparison += f"• Producto más caro: {products[prices.index(max(prices))].product_name} (Gs. {max(prices):,})\n"
            comparison += f"• Diferencia de precio: Gs. {max(prices) - min(prices):,}\n\n"
            
            comparison += "💡 *Recomendación: Considera tu presupuesto y necesidades específicas para elegir el producto adecuado.*"
            
            return comparison
            
        except Exception as e:
            return f"❌ Error en comparación manual: {str(e)}"