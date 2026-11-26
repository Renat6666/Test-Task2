"""Serializer base classes."""

from rest_framework import serializers


class WriteSerializer(serializers.Serializer):
    """Validates an incoming payload; it never saves anything itself.

    Persistence is the service layer's responsibility, so ``create``/``update``
    are deliberately not implemented. The response body is rendered with the
    view's ``read_serializer_class`` (injected by ``ServiceModelViewSet``) which
    keeps request and response shapes decoupled.
    """

    read_serializer_class = None

    def create(self, validated_data):  # pragma: no cover - never called
        raise NotImplementedError('Writes go through the service layer.')

    def update(self, instance, validated_data):  # pragma: no cover
        raise NotImplementedError('Writes go through the service layer.')

    def to_representation(self, instance):
        if self.read_serializer_class is not None:
            return self.read_serializer_class(instance, context=self.context).data
        return super().to_representation(instance)
