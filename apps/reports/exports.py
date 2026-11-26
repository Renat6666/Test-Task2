"""Stock report export, built with pandas.

Decimals are rendered as strings so neither CSV nor JSON ever shows float
rounding noise.
"""

from django.http import HttpResponse
from django.utils import timezone

import pandas as pd

COLUMNS = [
    'product_id',
    'sku',
    'name',
    'base_price',
    'min_stock_level',
    'total_stock',
    'total_value',
    'is_low_stock',
]

DECIMAL_COLUMNS = ['base_price', 'min_stock_level', 'total_stock', 'total_value']


def stock_dataframe(rows: list[dict]) -> pd.DataFrame:
    """Build the stock report frame from selector rows."""
    frame = pd.DataFrame(rows, columns=COLUMNS)
    for column in DECIMAL_COLUMNS:
        frame[column] = frame[column].map(lambda value: '' if value is None else str(value))
    frame['is_low_stock'] = frame['is_low_stock'].astype(bool)
    return frame


def _filename(extension: str) -> str:
    stamp = timezone.now().strftime('%Y%m%d-%H%M%S')
    return f'stock-report-{stamp}.{extension}'


def csv_response(frame: pd.DataFrame) -> HttpResponse:
    """Render the frame as a downloadable CSV file."""
    response = HttpResponse(
        frame.to_csv(index=False),
        content_type='text/csv; charset=utf-8',
    )
    response['Content-Disposition'] = f'attachment; filename="{_filename("csv")}"'
    return response


def json_response(frame: pd.DataFrame) -> HttpResponse:
    """Render the frame as a downloadable JSON file."""
    response = HttpResponse(
        frame.to_json(orient='records', indent=2),
        content_type='application/json',
    )
    response['Content-Disposition'] = f'attachment; filename="{_filename("json")}"'
    return response


#: Supported values of the ``file_format`` query parameter.
RENDERERS = {'csv': csv_response, 'json': json_response}
