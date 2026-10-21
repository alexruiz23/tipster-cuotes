# 004 — Persistencia: SQLite detrás de repositorios

**Estado:** Propuesta, pendiente de D7 · **Fecha:** 2026-10-21

## Contexto

Se pide SQLite con una capa de repositorios que permita migrar a PostgreSQL. El stack acordado
no incluye un ORM.

## Opciones

1. `sqlite3` de la librería estándar, protocolos de repositorio y migraciones en SQL numeradas.
2. SQLAlchemy Core: una sola implementación para SQLite y PostgreSQL.
3. ORM (SQLAlchemy ORM o SQLModel).

## Decisión (propuesta)

Opción 1. Los repositorios son `Protocol` tipados y su implementación SQLite usa SQL explícito y
portable: sin funciones propias de SQLite, fechas en texto ISO-8601 UTC y tipos
`INTEGER/REAL/TEXT`. Las migraciones son ficheros `NNNN_descripcion.sql` que se aplican en
orden y quedan anotados en una tabla de versión.

## Consecuencias

- Ninguna dependencia nueva; el SQL se lee y se revisa directamente.
- Migrar a PostgreSQL significa escribir otra implementación de los mismos protocolos (con
  psycopg) y adaptar las migraciones. Si prefieres no pagar ese coste más adelante, la opción 2
  lo evita a cambio de una dependencia: es la decisión D7.
- Los tests de repositorios corren contra una SQLite temporal y se reutilizarían contra
  PostgreSQL.
