"""Base view sets wiring the ``ViewSet -> Service -> Selector`` layering.

The rules the whole API follows:

* **Selectors** build querysets / read models. ``get_queryset()`` only ever
  delegates to a selector.
* **Services** perform every write and own the business rules.
* **ViewSets** validate input with a *write* serializer, hand the validated data
  to a service, then render the result with a *read* serializer.

The mixins below remove the boilerplate of that last step.
"""

from rest_framework import viewsets
from rest_framework.generics import get_object_or_404


class ReadWriteSerializerMixin:
    """Pick a serializer based on the direction of the request.

    ``read_serializer_class`` renders responses, ``write_serializer_class``
    validates incoming payloads. Write serializers render their response body
    with the read serializer, so a ``POST`` and a ``GET`` return the same shape.
    """

    read_serializer_class = None
    write_serializer_class = None
    write_actions = ('create', 'update', 'partial_update')

    def get_serializer_class(self):
        if self.action in self.write_actions and self.write_serializer_class:
            return self.write_serializer_class
        assert self.read_serializer_class is not None, (
            f'{self.__class__.__name__} must define `read_serializer_class`.'
        )
        return self.read_serializer_class

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if self.action in self.write_actions and self.write_serializer_class:
            serializer.read_serializer_class = self.read_serializer_class
        return serializer

    def get_read_serializer(self, instance, **kwargs):
        return self.read_serializer_class(
            instance, context=self.get_serializer_context(), **kwargs
        )


class CompanyScopedMixin:
    """Expose the company of the requesting employee to view and serializers."""

    @property
    def company(self):
        """The company of the requesting employee, ``None`` when anonymous.

        ``IsCompanyEmployee`` guarantees a company for real requests. The one
        caller without an employee attached is the OpenAPI schema generator,
        which introspects every view with an anonymous request.
        """
        return getattr(self.request.user, 'company', None)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['company'] = self.company
        return context


class CompanyScopedQuerysetMixin(CompanyScopedMixin):
    """Scope a model backed view to the employee's company.

    Subclasses implement :meth:`get_company_queryset` -- delegating to a
    selector -- instead of ``get_queryset()``, and can rely on ``self.company``
    being set.

    Without a company (schema generation) the declared ``queryset``
    (``Model.objects.none()``) is used instead, which gives the generator the
    model and the path parameter type without touching a real row.
    """

    def get_company_queryset(self):
        raise NotImplementedError

    def get_queryset(self):
        if self.company is None:
            return super().get_queryset()
        return self.get_company_queryset()


class ServiceModelViewSet(
    ReadWriteSerializerMixin,
    CompanyScopedQuerysetMixin,
    viewsets.ModelViewSet,
):
    """A ``ModelViewSet`` whose writes are delegated to the service layer.

    Subclasses implement the three ``*_object`` hooks and never touch the ORM
    directly.
    """

    def create_object(self, validated_data):
        raise NotImplementedError

    def update_object(self, instance, validated_data):
        raise NotImplementedError

    def delete_object(self, instance):
        raise NotImplementedError

    # DRF plumbing -----------------------------------------------------------

    def perform_create(self, serializer):
        instance = self.create_object(serializer.validated_data)
        # Re-read through the selector so the annotations (stock, value) are
        # present in the response body.
        serializer.instance = self.reload(instance)

    def perform_update(self, serializer):
        instance = self.update_object(serializer.instance, serializer.validated_data)
        serializer.instance = self.reload(instance)

    def perform_destroy(self, instance):
        self.delete_object(instance)

    def reload(self, instance):
        """Fetch ``instance`` again through ``get_queryset()``."""
        return get_object_or_404(self.get_queryset(), pk=instance.pk)
