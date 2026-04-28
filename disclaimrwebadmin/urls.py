from django.urls import path

from .views import (
    DirectoryServerAttributesView,
    DirectoryServerTestView,
    DirectoryServerVocabularyView,
    DisclaimerPreviewView,
    SignatureImageQuickUploadView,
    SignatureTestView,
)

app_name = "disclaimrwebadmin"

urlpatterns = [
    path(
        "disclaimer/preview/",
        DisclaimerPreviewView.as_view(),
        name="disclaimer-preview",
    ),
    path(
        "signatureimage/quick-upload/",
        SignatureImageQuickUploadView.as_view(),
        name="signatureimage-quick-upload",
    ),
    path(
        "signature-test/",
        SignatureTestView.as_view(),
        name="signature-test",
    ),
    path(
        "directoryserver/<int:pk>/test/",
        DirectoryServerTestView.as_view(),
        name="directoryserver-test",
    ),
    path(
        "directoryserver/<int:pk>/attributes/",
        DirectoryServerAttributesView.as_view(),
        name="directoryserver-attributes",
    ),
    path(
        "directoryserver/vocabulary/",
        DirectoryServerVocabularyView.as_view(),
        name="directoryserver-vocabulary",
    ),
]
