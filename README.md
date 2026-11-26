# Inventory Management API

REST API for warehouse stock management: products, warehouses and stock
movements (receipts, shipments, transfers) with balances that are **always
derived from the transaction history**, never stored.

Django · Django REST Framework · PostgreSQL · Redis · django-filter · pandas ·
python-dotenv · session authentication · OpenAPI/Swagger · Docker Compose.

---

## Quick start

No Dockerfile, no local Python install — the stack is three images and a bind
mount:

```bash
cp .env.example .env     # the only configuration step
docker compose up
```

That starts PostgreSQL, Redis and the API on <http://localhost:8000>. On the
first start the dependencies from `requirements.txt` are installed into the
named volume `pydeps` (later starts reuse it) and the migrations are applied
automatically.

**Interactive documentation: <http://localhost:8000/api/docs/>**

```bash
docker compose run --rm tests                        # run the test suite
docker compose exec api python manage.py createsuperuser
docker compose logs -f api                           # outgoing emails show up here
docker compose down -v                               # wipe everything
```

### Configuration: `.env` and nothing else

| File | Committed | Role |
| --- | --- | --- |
| [`.env.example`](.env.example) | yes | Template with safe development defaults, documented key by key |
| `.env` | **no** (gitignored) | The configuration actually used, including real credentials |

`.env` is the single source of configuration. The file is read by
**python-dotenv**; [`config/env.py`](config/env.py) wraps it with the two rules
the project relies on:

* **no defaults in Python** — every value is declared in `.env`, so the file is
  an exhaustive, always-accurate description of how the project is configured;
  there is no second place a value could quietly come from;
* **typed, fail-fast reads** — `ImproperlyConfigured` names any key that is
  missing, or not a valid boolean/integer.

Everything reads that one file: **Compose** passes it into every container
(`env_file`) and resolves the published ports from it, and **Django** loads it
through `config/env.py`, which `settings.py`, `manage.py`, `wsgi.py` and
`asgi.py` all call — so `manage.py` and `pytest` behave identically inside and
outside Docker. Even `DJANGO_SETTINGS_MODULE` comes from there.

Values already present in the real environment are left alone (dotenv's
`override=False`), which is what lets Compose inject the file and lets one value
be overridden for a single command:

```bash
USE_SQLITE=1 pytest          # run the suite without PostgreSQL
```

### Using the API from the shell

Authentication is Django's session + cookie stack, so keep a cookie jar:

```bash
# Register (creates the company as well) and sign in
curl -sc jar.txt -X POST localhost:8000/api/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"clerk","email":"clerk@acme.io","password":"a-strong-pass-42","company_name":"Acme"}'

curl -sc jar.txt -X POST localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"login":"clerk","password":"a-strong-pass-42"}'

# Unsafe requests need the CSRF token that login returned (or GET /api/auth/csrf/)
CSRF=$(curl -sb jar.txt localhost:8000/api/auth/csrf/ | python -c 'import json,sys;print(json.load(sys.stdin)["csrf_token"])')

curl -sb jar.txt -c jar.txt -X POST localhost:8000/api/products/ \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
  -d '{"sku":"SKU-1","name":"Blue widget","base_price":"10.00","min_stock_level":"5"}'
```

The browsable DRF interface at <http://localhost:8000/api/> works too — sign in
via <http://localhost:8000/api/auth/browsable/login/>.

---

## API documentation

The schema is generated from the code by
[drf-spectacular](https://drf-spectacular.readthedocs.io), so it cannot drift
away from the implementation.

| URL | What |
| --- | --- |
| [`/api/docs/`](http://localhost:8000/api/docs/) | **Swagger UI** — browse and call every endpoint |
| [`/api/redoc/`](http://localhost:8000/api/redoc/) | ReDoc — a reading-oriented rendering |
| [`/api/schema/`](http://localhost:8000/api/schema/) | OpenAPI 3 document (YAML; `?format=json` for JSON) |

All three are public; the endpoints they describe still require a session.

**"Try it out" works for writes too.** Opening `/api/docs/` sets the CSRF
cookie, and the Swagger UI request interceptor copies it into the `X-CSRFToken`
header — so after calling `POST /api/auth/login/` from the page itself, every
`POST`/`PATCH`/`DELETE` button works with your session.

The UI assets are vendored (`drf-spectacular-sidecar`) rather than loaded from a
CDN, so the docs work offline and inside Docker.

Exporting the document, e.g. for a client generator:

```bash
docker compose exec api python manage.py spectacular --file schema.yml
```

`tests/test_schema.py` asserts the schema generates with **zero warnings**, that
every operation carries a summary, and that the documented shapes match what the
endpoints really return.

---

## Endpoints

### Authentication — `/api/auth/`

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `register/` | Create an employee (and their company) |
| POST | `login/` | Open a session, returns the CSRF token |
| POST | `logout/` | End the session |
| GET | `me/` | The signed-in employee |
| GET | `csrf/` | Hand out the CSRF cookie/token |
| POST | `password-reset/` | Email a reset link |
| POST | `password-reset/confirm/` | Set a new password from `uid` + `token` |
| POST | `password-change/` | Change your own password |

### Resources

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/api/warehouses/` | List / create warehouses |
| GET/PUT/PATCH/DELETE | `/api/warehouses/{id}/` | Warehouse detail |
| GET | `/api/warehouses/{id}/stock/` | Products held there, balances scoped to it |
| GET | `/api/warehouses/{id}/low-stock/` | Articles running out there |
| GET/POST | `/api/products/` | List / create products |
| GET/PUT/PATCH/DELETE | `/api/products/{id}/` | Product detail (`DELETE` = soft delete) |
| POST | `/api/products/{id}/restore/` | Undo a soft delete |
| GET | `/api/products/{id}/stock/` | Per-warehouse breakdown |
| GET/POST | `/api/transactions/` | List / record stock movements |
| GET | `/api/transactions/{id}/` | Movement with its ledger entries |
| GET | `/api/companies/current/` | Your company |
| GET | `/api/employees/` | Your colleagues (pick a warehouse manager) |

### Documentation

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/docs/` | Swagger UI |
| GET | `/api/redoc/` | ReDoc |
| GET | `/api/schema/` | OpenAPI 3 document |

### Reports — `/api/reports/`

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `warehouse-value/` | Total stock value per warehouse — **cached in Redis** |
| GET | `stock/` | Current stock of every product |
| GET | `stock/export/?file_format=csv\|json` | Download the stock report (pandas) |
| GET | `low-stock/` | Products at or below `min_stock_level` |

`warehouse-value/` accepts `?refresh=true` and reports whether the answer came
from the cache (`"cached": true|false`).

### Search, filtering, sorting, pagination

Every list endpoint is paginated (`?page=`, `?page_size=`, max 200).

```
# Products
/api/products/?search=widget                 name or SKU, case insensitive
/api/products/?min_price=10&max_price=50
/api/products/?low_stock=true                at or below min_stock_level
/api/products/?in_stock=true
/api/products/?include_deleted=true
/api/products/?ordering=-total_stock         also: total_value, base_price, name, sku

# Transactions
/api/transactions/?transaction_type=OUT&transaction_type=TRANSFER
/api/transactions/?warehouse=3               source or destination
/api/transactions/?source_warehouse=3&destination_warehouse=4
/api/transactions/?product=7  |  ?sku=SKU-001
/api/transactions/?date_from=2026-01-01T00:00:00Z&date_to=2026-02-01T00:00:00Z
/api/transactions/?ordering=occurred_at

# Warehouses
/api/warehouses/?search=central&is_active=true&ordering=-total_value
```

---

## Architecture

```
config/                     settings, .env loading, root urlconf + OpenAPI routes
apps/
  common/                   fields, pagination, permissions, exceptions, cache, base view sets
  companies/                tenant
  users/                    employees, session auth, password reset
  warehouses/               warehouses + their totals
  products/                 catalogue, soft delete, calculated stock
  transactions/             the ledger: movements + entries
  reports/                  aggregates, Redis cache, pandas export
tests/                      API test suite
```

Each app follows the same layering:

| Layer | File | Responsibility |
| --- | --- | --- |
| **ViewSet** | `views.py` | HTTP only: validate with a write serializer, call a service, render with a read serializer |
| **Service** | `services.py` | Every write, and every business rule |
| **Selector** | `selectors.py` | Every read: querysets, annotations, aggregates |
| Serializer | `serializers.py` | Payload shape and field validation |
| Filter | `filters.py` | django-filter filter sets |

`apps/common/viewsets.py` holds the base classes that keep this consistent:
`ServiceModelViewSet` turns `create/update/destroy` into `create_object`,
`update_object` and `delete_object` hooks that delegate to services, and
re-reads the object through the selector afterwards so the response always
carries the calculated fields. No view touches the ORM.

### The ledger: why there are two models

```
InventoryTransaction   what an employee did      ("move 10 pcs from A to B")
InventoryEntry         the signed effect of it   (-10 on A, +10 on B)
```

A balance is therefore `SUM(inventory_entries.quantity_delta)` filtered by
product and warehouse — one expression that is correct for `IN`, `OUT` and
`TRANSFER` alike, with no per-type branching anywhere in the query layer. A
transfer nets out to zero company wide, which is exactly right.

The ledger is append only: there is no `PUT`/`PATCH`/`DELETE` on
`/api/transactions/` (and the admin refuses edits), because every number the
API reports is derived from these rows.

### Dynamic balances (no stored stock)

`apps/transactions/selectors.stock_expression()` builds a correlated subquery:

```python
Product.objects.annotate(total_stock=stock_expression())
               .annotate(total_value=F('total_stock') * F('base_price'))
```

A correlated subquery rather than a `JOIN` + `GROUP BY` so that it composes
with other annotations and with pagination without multiplying rows, and so the
whole product page costs **one** query (asserted in
`tests/test_stock_calculation.py`). Because `total_stock` and `total_value` are
real SQL expressions, they can also be filtered (`?low_stock=true`) and sorted
(`?ordering=-total_value`) by the database.

`tests/test_stock_calculation.py` additionally asserts that no stock column
exists on any model or table.

### Validation of a movement

1. The serializer narrows `product` / `source_warehouse` /
   `destination_warehouse` to the requesting employee's company, so another
   company's ids simply do not resolve.
2. `services.create_inventory_transaction` checks ownership, the
   type ↔ warehouse combination, and that the source warehouse really holds
   enough stock. The product row is locked with `select_for_update()` for the
   duration, so two concurrent shipments cannot both pass the stock check and
   overdraw a warehouse.
3. Database check constraints (`transaction_quantity_positive`,
   `transaction_warehouse_validation`) are the last line of defence.

### Redis

Redis does three jobs:

* **Rate limit** — `TransactionCreateThrottle` (`UserRateThrottle`, scope
  `transaction_create`, 50/min) counts per employee in the Django cache, so the
  limit holds across every worker process. Only `POST /api/transactions/` is
  throttled; reads are not. The credential endpoints have their own `30/min`
  per-IP throttle.
* **Report cache** — the warehouse value report aggregates the whole ledger, so
  the payload is cached under
  `reports:v1:warehouse-value:company:{id}`. It is *invalidated eagerly* from
  `transaction.on_commit` whenever stock moves, a price changes, a product is
  soft deleted or a warehouse changes, so a stale number can never be served.
  `REPORT_CACHE_TTL` (default 300s) is only a safety net.
* **Sessions** — `cached_db` session backend.

### Soft delete

`DELETE /api/products/{id}/` sets `is_deleted`/`deleted_at`. The row stays, so
past shipments keep resolving to a real article. A soft deleted product leaves
the catalogue, the stock report and the value report, but stays reachable at its
detail URL and in the transaction history. The SKU uniqueness constraint is
conditional (`condition=Q(is_deleted=False)`), so a code can be reused once the
old article is gone, and `POST /api/products/{id}/restore/` brings it back.

### Multi-tenancy

Every employee belongs to a company; `IsCompanyEmployee` requires one and every
selector filters by it. Cross-company reads return `404`, cross-company
references in a payload are rejected as unknown ids.

### Low stock alerts (bonus task)

After an `OUT` movement, if the balance on the source warehouse drops below the
product's `min_stock_level`, an email goes to the warehouse's `manager` (falling
back to the company's staff accounts). It is queued from
`transaction.on_commit`, so a rolled back movement never sends mail and a broken
mail server never fails a valid shipment. With the default console backend the
message appears in `docker compose logs api`.

---

## Tests

```bash
docker compose run --rm tests          # inside the stack
```

Locally, against the running Redis and a throwaway SQLite file:

```bash
USE_SQLITE=1 REDIS_URL=redis://127.0.0.1:6379/0 pytest -q
```

172 tests covering:

| File | Covers |
| --- | --- |
| `test_auth.py` | registration, session login/logout, password reset + change, access control |
| `test_warehouses.py` | CRUD, scoping, totals, retire-instead-of-delete, filters |
| `test_products.py` | CRUD, soft delete + restore, SKU reuse, search, filters, ordering, pagination |
| `test_transactions.py` | `IN`/`OUT`/`TRANSFER`, every validation rule, append-only ledger, filters, rate limit |
| `test_stock_calculation.py` | no stored balance anywhere, derived balances, query count |
| `test_reports.py` | warehouse value report, cache hit/miss/invalidation, CSV + JSON export |
| `test_low_stock_alerts.py` | the bonus email, and when it must *not* fire |
| `test_schema.py` | OpenAPI schema generates clean, documents what the API really does |

The suite talks to a real Redis (database index 15, flushed per test) so the
throttle counters and the report cache are exercised for real, not mocked.

`USE_SQLITE=1` is a convenience for running the suite without a PostgreSQL
instance; PostgreSQL is the target database and what `docker compose` uses.

---

## Configuration

Every key is documented in [`.env.example`](.env.example); the table is the
quick reference. All of them are **required** — the template value is what you
get after `cp .env.example .env`.

| Variable | Template value | Meaning |
| --- | --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings` | Settings module, read from `.env` too |
| `DJANGO_SECRET_KEY` | dev key | Secret key |
| `DJANGO_DEBUG` | `1` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma separated hosts |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Comma separated origins |
| `TIME_ZONE` / `LOG_LEVEL` | `UTC` / `INFO` | |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `0` | Turn on behind https |
| `PASSWORD_RESET_TIMEOUT` | `86400` | Reset link lifetime, seconds |
| `POSTGRES_{DB,USER,PASSWORD,HOST,PORT}` | `inventory`, host `db` | Database |
| `DB_CONN_MAX_AGE` | `60` | Connection reuse, seconds |
| `USE_SQLITE` | `0` | Use SQLite instead (tests only) |
| `REDIS_URL` / `REDIS_KEY_PREFIX` | `redis://redis:6379/0` | Cache / throttle / sessions |
| `TRANSACTION_THROTTLE_RATE` | `50/min` | Transactions per employee per minute |
| `AUTH_THROTTLE_RATE` | `30/min` | Credential endpoint attempts per IP |
| `REPORT_CACHE_TTL` | `300` | Report cache TTL in seconds |
| `API_PAGE_SIZE` | `20` | Default page size |
| `EMAIL_BACKEND` | console | Swap for `...smtp.EmailBackend` to send mail |
| `EMAIL_{HOST,PORT,USE_TLS,HOST_USER,HOST_PASSWORD}` | commented out | Only read with the SMTP backend |
| `DEFAULT_FROM_EMAIL` | `inventory@example.com` | Sender |
| `PASSWORD_RESET_URL_TEMPLATE` | API confirm URL | Link template, `{uid}` / `{token}` |
| `{API,POSTGRES,REDIS}_PUBLISHED_PORT` | `8000`, `5432`, `6379` | Host ports (Compose only) |
| `PYTHONUSERBASE` | `/pydeps` | Where `pip install --user` puts the deps |

---

## Notes on a few decisions

* **Registration creates or joins a company by name.** The first employee of a
  company creates it; a later employee giving the same name joins it. A
  production system would replace the joining half with an invitation flow —
  `apps/companies/services.get_or_create_company` is the single place to change.
* **The export parameter is `file_format`, not `format`**, because DRF reserves
  `format` for content negotiation.
* **A warehouse that appears in the ledger cannot be deleted** (`409`); it is
  retired with `PATCH {"is_active": false}`. Deleting it would rewrite history.
* **Email is configured through `MAILERS`**, the replacement for the now
  deprecated `EMAIL_*` settings in this Django version.
* **Quantities are decimals** (`14,3`), not integers, so the system also handles
  articles sold by weight or length.
