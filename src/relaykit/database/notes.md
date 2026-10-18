-- this is how the sequence goes by 

1. async_session_factory() creates Session A
2. Session A remembers our engine
3. No database connection is necessarily taken yet
4. session.execute() needs PostgreSQL
5. Session A asks the engine for a connection
6. Engine checks out an available connection from its pool
7. Session A uses that connection during its transaction
8. Commit, rollback, or session close finishes the work
9. Connection is returned to the pool

```
Session factory
    └── permanently knows the engine

Session
    └── temporarily belongs to one request/task

Connection
    └── temporarily checked out by a session transaction

Pool
    └── owns and reuses database connections
```

NEXT: declaration of the project level - Base

#Architecture

```
Endpoint Python class
        │ inherits from
        v
       Base
        │ registers table in
        v
   Base.metadata
        │ inspected by
        v
      Alembic
        │ creates migration
        v
 PostgreSQL schema

```
--> Base provides Base.metadata that is a SQLalchemy's in memory descriptive db schema, it has something like

```
Base.metadata
└── endpoints
    ├── id
    ├── name
    ├── url
    ├── status
    └── created_at
```