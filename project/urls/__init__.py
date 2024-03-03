from django.urls import include, path
from rest_framework import routers

from .cycle import urlpatterns as cycle_urls
from .estimate import urlpatterns as estimate_urls
from .external import urlpatterns as external_urls
from .issue import urlpatterns as issue_urls
from .module import urlpatterns as module_urls
from .page import urlpatterns as page_urls
from .project import urlpatterns as project_urls
from .search import urlpatterns as search_urls
from .state import urlpatterns as state_urls
from .views import urlpatterns as view_urls

urlpatterns = []

router = routers.DefaultRouter(trailing_slash=False)

urlpatterns = [
    path("", include(router.urls)),
    *cycle_urls,
    *estimate_urls,
    *external_urls,
    *issue_urls,
    *module_urls,
    *page_urls,
    *project_urls,
    *search_urls,
    *state_urls,
    *view_urls,
]
