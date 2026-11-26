"""Pagination used by every list endpoint."""

from rest_framework import pagination


class PageNumberPagination(pagination.PageNumberPagination):
    """Page number pagination with a client controlled page size."""

    page_size_query_param = 'page_size'
    max_page_size = 200
