from django.contrib import admin
from django.urls import path
from tracker import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('scrape/<str:league_code>/', views.scrape_league, name='scrape_league'),
    path('scrape-all/', views.scrape_all, name='scrape_all'),
]
