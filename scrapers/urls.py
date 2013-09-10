from django.conf.urls import patterns, include, url

# URL's for berkeley
urlpatterns = patterns('berkeley.views',
    (r'^scrape/berkeley/$','scrape'),
)
