"""
URL configuration for APAC_BarrierFreeJourney project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from main.views.TravelCandidates import TravelCandidatesListView, TravelCandidatesSelectView
from main.views.TravelRequest import TravelRequestCreateView, TravelRequestDetailView
from main.views.TravelSchedule import TravelScheduleCreateView, TravelScheduleListView,TravelScheduleDetailView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('travel/request/', TravelRequestCreateView.as_view(), name='travel-request-create'),
    path('travel/request/<int:request_id>/', TravelRequestDetailView.as_view(), name='travel-request-detail'),
    path('travel/schedule/',TravelScheduleCreateView.as_view(), name='travel-schedule-create'),
    path('travel/schedule/<int:request_id>/', TravelScheduleListView.as_view(), name='travel-schedule-list'),
    path('travel/schedule/<int:request_id>/<int:version>/', TravelScheduleDetailView.as_view(), name='travel-schedule-detail'),
    path('travel/schedule/candidates/<int:request_id>/', TravelCandidatesListView.as_view(), name='travel-candidate-list'),
    path('travel/schedule/select/<int:request_id>/', TravelCandidatesSelectView.as_view(), name='travel-candidate-select'),


    ]
